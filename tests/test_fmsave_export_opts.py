"""Save-export optimizations: filter prep, preload reuse, scoped divisions, upload defer."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import services.export_library as lib
import services.fmsave_export as fms


def setup_function(_fn):
    fms.clear_preload_cache()


def test_prepare_filters_builds_sets_once():
    prepared = fms.prepare_filters(
        {
            "age_min": 20,
            "club_contains": "  Roma  ",
            "club_nation_ids": ["164", 139],
            "nation_ids": [164],
            "position_groups": ["DEF", "mid"],
        }
    )
    assert prepared is not None
    assert prepared["_prepared"] is True
    assert prepared["club_contains"] == "roma"
    assert prepared["club_nation_ids"] == frozenset({164, 139})
    assert prepared["nation_ids"] == frozenset({164})
    assert prepared["position_groups"] == ("def", "mid")
    assert fms.prepare_filters(prepared) is prepared


def test_passes_filters_uses_prepared_sets():
    player = SimpleNamespace(
        age=24,
        height_cm=180,
        club_name="AS Roma",
        club_nation_id=150,
        nation_id=164,
        natural_positions=("DC",),
    )
    prepared = fms.prepare_filters(
        {"club_nation_ids": [150], "nation_ids": [164], "position_groups": ["def"]}
    )
    assert fms._passes_filters(player, prepared) is True
    prepared_miss = fms.prepare_filters({"club_nation_ids": [139]})
    assert fms._passes_filters(player, prepared_miss) is False


def test_take_preloaded_export_players_reuses_full_records(tmp_path: Path):
    save = tmp_path / "career.fm"
    save.write_bytes(b"fm")
    attrs = SimpleNamespace(acceleration=10)
    players = [
        SimpleNamespace(
            uid=1,
            attributes=attrs,
            age=22,
            height_cm=180,
            club_name="A",
            club_nation_id=164,
            nation_id=164,
            natural_positions=("ST",),
            club_uid=101,
        ),
        SimpleNamespace(
            uid=2,
            attributes=attrs,
            age=30,
            height_cm=180,
            club_name="B",
            club_nation_id=164,
            nation_id=164,
            natural_positions=("ST",),
            club_uid=202,
        ),
    ]
    key = fms._preload_cache_key(save)
    fms._preload_cache = {
        "key": key,
        "players": players,
        "by_scope": {
            "all": players,
            "squad": [players[0]],
        },
        "export_ready": True,
        "managed_club_uid": 101,
        "meta": {"ok": True, "save_total": 2, "squad_total": 1},
    }
    squad = fms._take_preloaded_export_players(str(save), scope="squad", filters=None)
    assert squad == [players[0]]
    filtered = fms._take_preloaded_export_players(
        str(save),
        scope="all",
        filters={"age_max": 25},
    )
    assert filtered == [players[0]]


def test_build_club_divisions_scoped_skips_fixtures_when_named():
    class _Table:
        def __init__(self, name, clubs):
            self.competition_name = name
            self.club_count = len(clubs)
            self.rows = [
                SimpleNamespace(
                    team_slot=0,
                    club_uid=uid,
                    team_id=1000 + uid,
                    rounds_per_venue=len(clubs) - 1,
                )
                for uid in clubs
            ]

    career = SimpleNamespace(
        league_tables=lambda: [
            _Table("Liga I", [101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
        ],
        clubs=lambda: (),
        fixtures=mock.Mock(side_effect=AssertionError("fixtures should not run")),
    )
    out = fms._build_club_divisions(career, {101})
    assert out == {101: "Liga I"}
    career.fixtures.assert_not_called()


def test_save_upload_reuses_eligibility_and_skips_sync_precompute(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(lib, "UPLOADS_INDEX_PATH", tmp_path / "index.json")
    (tmp_path / "index.json").write_text("[]", encoding="utf-8")

    csv_text = "Player;Age;Club\nAda;20;FC\n"
    elig = lib.classify_eligibility(csv_text)
    called = {"compute": 0}

    def _boom(_file_id):
        called["compute"] += 1
        raise AssertionError("compute_file should not run when precompute=False")

    monkeypatch.setattr("services.upload_cache.compute_file", _boom)
    with mock.patch.object(lib, "count_csv_players", side_effect=AssertionError("count")):
        entry = lib.save_upload(
            "fmsave_test.csv",
            csv_text,
            export_source=lib.EXPORT_SOURCE_FMSAVE,
            eligibility=elig,
            player_count=1,
            precompute=False,
        )
    assert entry["player_count"] == 1
    assert entry["export_source"] == lib.EXPORT_SOURCE_FMSAVE
    assert called["compute"] == 0


def test_save_upload_async_schedules_compute(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(lib, "UPLOADS_INDEX_PATH", tmp_path / "index.json")
    (tmp_path / "index.json").write_text("[]", encoding="utf-8")

    scheduled: list[str] = []
    monkeypatch.setattr(lib, "schedule_upload_compute", scheduled.append)
    csv_text = "Player;Age;Club\nAda;20;FC\n"
    entry = lib.save_upload(
        "fmsave_async.csv",
        csv_text,
        precompute="async",
    )
    assert entry["cache"]["status"] == "computing"
    assert scheduled == [entry["id"]]
