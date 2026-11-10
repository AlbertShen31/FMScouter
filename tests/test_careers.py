"""Career containers, season classification, and snapshot import."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import services.career_import as career_import
import services.careers as careers


@pytest.fixture()
def career_root(tmp_path, monkeypatch):
    root = tmp_path / "careers"
    packs = root / "packs"
    packs.mkdir(parents=True)
    monkeypatch.setattr(careers, "CAREERS_DIR", root)
    monkeypatch.setattr(careers, "CAREERS_PACKS_DIR", packs)
    monkeypatch.setattr(careers, "CAREERS_ACTIVE_PATH", root / "active.json")
    return root


def test_season_from_game_date_jul_split():
    assert career_import.season_from_game_date(date(2026, 7, 1)) == {
        "id": "2026-2027",
        "label": "2026/27",
        "year_start": 2026,
        "year_end": 2027,
    }
    assert career_import.season_from_game_date(date(2027, 1, 15)) == {
        "id": "2026-2027",
        "label": "2026/27",
        "year_start": 2026,
        "year_end": 2027,
    }
    assert career_import.season_from_game_date(date(2026, 6, 30)) == {
        "id": "2025-2026",
        "label": "2025/26",
        "year_start": 2025,
        "year_end": 2026,
    }


@pytest.mark.parametrize(
    ("when", "slot"),
    [
        (date(2026, 12, 15), "mid"),
        (date(2026, 12, 31), "mid"),
        (date(2027, 1, 1), "mid"),
        (date(2026, 6, 15), "mid"),
        (date(2026, 7, 30), "mid"),
        (date(2026, 7, 31), "end"),
        (date(2026, 5, 1), "end"),
        (date(2026, 11, 1), "end"),
        (None, "end"),
    ],
)
def test_suggest_slot_windows(when, slot):
    assert career_import.suggest_slot(when) == slot


def test_create_list_active_delete(career_root):
    meta = careers.create_career("Romania Save")
    assert meta["id"] == "romania-save"
    assert meta["show_hidden_attrs"] is False
    assert careers.get_active()["career_id"] == "romania-save"

    careers.set_show_hidden_attrs("romania-save", True)
    assert careers.get_career("romania-save")["show_hidden_attrs"] is True

    careers.rename_career("romania-save", "Romania 26")
    assert careers.get_career("romania-save")["name"] == "Romania 26"

    careers.create_career("England")
    assert len(careers.list_careers()) == 2
    assert careers.delete_career("romania-save") is True
    assert careers.get_active()["career_id"] == "england"


def test_parse_picked_paths_multiline():
    import services.fmsave_export as fms

    assert fms._parse_picked_paths("") == []
    assert fms._parse_picked_paths('/a/one.fm\n/b/two.fm\n') == [
        "/a/one.fm",
        "/b/two.fm",
    ]
    assert fms._parse_picked_paths('/a/one.fm\x00/a/one.fm\x00/b/two.fm') == [
        "/a/one.fm",
        "/b/two.fm",
    ]


def test_batch_csv_imports_mid_and_end(career_root):
    careers.create_career("Batch Career")
    csv_text = "Player;Unique ID;Age\nAda;1;24\n"
    mid = career_import.import_csv_to_career(
        "batch-career",
        csv_text,
        source_name="mid.csv",
        game_date="2026-12-20",
    )
    end = career_import.import_csv_to_career(
        "batch-career",
        csv_text,
        source_name="end.csv",
        game_date="2027-05-20",
    )
    assert mid["ok"] is True and mid["slot"] == "mid"
    assert end["ok"] is True and end["slot"] == "end"
    season = careers.get_season("batch-career", "2026-2027")
    assert season["slots"]["mid"]["source_name"] == "mid.csv"
    assert season["slots"]["end"]["source_name"] == "end.csv"


def test_stage_then_assign_to_slot(career_root):
    careers.create_career("Stage Career")
    csv_text = "Player;Unique ID;Age\nAda;1;24\nBee;2;22\n"
    staged = career_import.stage_import(
        "stage-career",
        csv_text=csv_text,
        source_name="winter.csv",
        game_date_override="2026-12-20",
    )
    assert staged["ok"] is True
    item = staged["item"]
    assert item["suggested_slot"] == "mid"
    assert item["season_id"] == "2026-2027"
    assert item["player_count"] == 2
    assert len(careers.list_staging("stage-career")) == 1

    blocked = career_import.commit_staging_to_slot(
        "stage-career",
        item["id"],
        season_id="2026-2027",
        slot="mid",
        season_label="2026/27",
        year_start=2026,
        year_end=2027,
        replace=False,
    )
    # First assign should succeed (empty slot).
    assert blocked["ok"] is True
    assert careers.list_staging("stage-career") == []
    season = careers.get_season("stage-career", "2026-2027")
    assert season["slots"]["mid"]["player_count"] == 2

    # Stage another and require replace for occupied mid.
    staged2 = career_import.stage_import(
        "stage-career",
        csv_text=csv_text.replace("Ada", "Ada2"),
        source_name="winter2.csv",
        game_date_override="2026-12-21",
    )
    conflict = career_import.commit_staging_to_slot(
        "stage-career",
        staged2["item"]["id"],
        season_id="2026-2027",
        slot="mid",
        year_start=2026,
        year_end=2027,
        replace=False,
    )
    assert conflict["ok"] is False
    assert conflict["needs_replace"] is True
    assert len(careers.list_staging("stage-career")) == 1

    replaced = career_import.commit_staging_to_slot(
        "stage-career",
        staged2["item"]["id"],
        season_id="2026-2027",
        slot="mid",
        year_start=2026,
        year_end=2027,
        replace=True,
    )
    assert replaced["ok"] is True
    assert replaced["replaced"] is True
    assert careers.list_staging("stage-career") == []


def test_csv_import_mid_end_replace(career_root):
    careers.create_career("Test Career")
    csv_text = (
        "Player;Unique ID;Age;Club;Division;Nation;Pace;Acceleration;Minutes;Goals\n"
        "Ada;1001;24;CFR Cluj;Liga I;ROU;14;15;900;4\n"
        "Bea;1002;21;Farul;Liga I;ROU;12;13;720;1\n"
    )
    first = career_import.import_csv_to_career(
        "test-career",
        csv_text,
        source_name="mid.csv",
        game_date="2026-12-20",
        replace=False,
    )
    assert first["ok"] is True
    assert first["slot"] == "mid"
    assert first["season_id"] == "2026-2027"
    assert first["player_count"] == 2

    blocked = career_import.import_csv_to_career(
        "test-career",
        csv_text,
        source_name="mid2.csv",
        game_date="2026-12-21",
        replace=False,
    )
    assert blocked["ok"] is False
    assert blocked["needs_replace"] is True

    replaced = career_import.import_csv_to_career(
        "test-career",
        csv_text.replace("Ada", "Ada R"),
        source_name="mid3.csv",
        game_date="2026-12-22",
        replace=True,
    )
    assert replaced["ok"] is True
    assert replaced["replaced"] is True

    end = career_import.import_csv_to_career(
        "test-career",
        csv_text,
        source_name="end.csv",
        game_date="2027-05-20",
        replace=False,
    )
    assert end["ok"] is True
    assert end["slot"] == "end"
    assert end["season_id"] == "2026-2027"

    season = careers.get_season("test-career", "2026-2027")
    assert season is not None
    assert season["slots"]["mid"]["player_count"] == 2
    assert season["slots"]["end"]["player_count"] == 2

    snap = careers.load_snapshot("test-career", "2026-2027", "mid")
    assert snap is not None
    assert snap["player_count"] == 2
    assert snap["players"][0]["unique_id"] == "1001"
    assert snap["players"][0]["attrs"]["Pace"] == 14
    assert snap["players"][0]["stats"]["Minutes"] == 900

    careers.rename_season("test-career", "2026-2027", "2026/27 Romania")
    assert careers.get_season("test-career", "2026-2027")["label"] == "2026/27 Romania"
    assert careers.get_active() == {
        "career_id": "test-career",
        "season_id": "2026-2027",
    }


def test_manual_slot_override(career_root):
    careers.create_career("Override")
    csv_text = "Player;Unique ID;Age\nX;9;20\n"
    # Date suggests mid, but force end.
    result = career_import.import_csv_to_career(
        "override",
        csv_text,
        game_date="2026-12-20",
        slot="end",
        season_label="Custom 26/27",
    )
    assert result["ok"] is True
    assert result["slot"] == "end"
    assert result["season_label"] == "Custom 26/27"
    season = careers.get_season("override", "2026-2027")
    assert season["label"] == "Custom 26/27"
    assert season["slots"]["end"] is not None
    assert season["slots"]["mid"] is None


def test_peek_classification_uses_date_without_players():
    csv_text = (
        "Player;Unique ID;Age\n"
        "Ada;1001;24\n"
    )
    peek = career_import.peek_classification(
        csv_text=csv_text,
        source_name="mid.csv",
        game_date_override="2026-12-20",
    )
    assert peek["classification"]["label"] == "2026/27"
    assert peek["classification"]["slot"] == "mid"
    assert peek["classification"]["game_date"] == "2026-12-20"
    assert peek["meta"]["source"] == "csv"
    assert "players" not in peek
