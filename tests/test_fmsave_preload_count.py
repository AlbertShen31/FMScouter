"""Preload cache + live export player counts for Save export."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import services.fmsave_export as fms


def setup_function(_fn):
    fms.clear_preload_cache()


def _snap(**overrides):
    base = dict(
        age=24,
        height_cm=185,
        club_name="FC Romania",
        club_nation_id=164,
        nation_id=164,
        natural_positions=("DC",),
        club_uid=101,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _seed_cache(tmp_path: Path, players: list[SimpleNamespace], *, managed_club_uid=101):
    save = tmp_path / "career.fm"
    save.write_bytes(b"fm")
    key = fms._preload_cache_key(save)
    if managed_club_uid is None:
        squad_total = 0
    else:
        wanted = int(managed_club_uid)
        squad_total = sum(
            1
            for player in players
            if player.club_uid is not None and int(player.club_uid) == wanted
        )
    meta = {
        "ok": True,
        "save_path": str(save.resolve()),
        "save_total": len(players),
        "squad_total": squad_total,
        "managed_club_uid": managed_club_uid,
        "managed_club_name": None if managed_club_uid is None else "FC Romania",
    }
    squad = [
        player
        for player in players
        if managed_club_uid is not None
        and player.club_uid is not None
        and int(player.club_uid) == int(managed_club_uid)
    ]
    fms._preload_cache = {
        "key": key,
        "players": players,
        "by_scope": {"all": players, "squad": squad},
        "export_ready": False,
        "managed_club_uid": managed_club_uid,
        "meta": meta,
    }
    return save


def test_count_matching_players_scope_and_filters(tmp_path):
    players = [
        _snap(club_uid=101, age=22, height_cm=178),
        _snap(club_uid=101, age=30, height_cm=190),
        _snap(club_uid=202, age=22, height_cm=178, club_name="Other"),
    ]
    save = _seed_cache(tmp_path, players)

    squad = fms.count_matching_players(str(save), scope="squad", filters=None)
    assert squad["ok"] is True
    assert squad["matched"] == 2
    assert squad["scope_total"] == 2
    assert squad["save_total"] == 3

    filtered = fms.count_matching_players(
        str(save),
        scope="all",
        filters={"age_max": 25, "height_min_in": 70},
    )
    # 178cm → 70in; both age-22 rows pass age_max; height_min 70 keeps both 178cm
    assert filtered["matched"] == 2
    assert filtered["filters_active"] is True

    tall_only = fms.count_matching_players(
        str(save),
        scope="squad",
        filters={"height_min_in": 74},  # 190cm → ~75in
    )
    assert tall_only["matched"] == 1


def test_count_matching_players_requires_preload(tmp_path):
    save = tmp_path / "missing-cache.fm"
    save.write_bytes(b"fm")
    try:
        fms.count_matching_players(str(save), scope="squad")
        assert False, "expected LookupError"
    except LookupError:
        pass


def test_count_matching_players_no_managed_club(tmp_path):
    save = _seed_cache(tmp_path, [_snap(club_uid=202)], managed_club_uid=None)
    result = fms.count_matching_players(str(save), scope="squad")
    assert result["ok"] is False
    assert result["matched"] == 0
    assert "managed club" in result["error"].lower()
