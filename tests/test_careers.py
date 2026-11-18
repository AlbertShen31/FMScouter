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
        "schedule": "summer_spring",
    }
    assert career_import.season_from_game_date(date(2027, 1, 15)) == {
        "id": "2026-2027",
        "label": "2026/27",
        "year_start": 2026,
        "year_end": 2027,
        "schedule": "summer_spring",
    }
    assert career_import.season_from_game_date(date(2026, 6, 30)) == {
        "id": "2025-2026",
        "label": "2025/26",
        "year_start": 2025,
        "year_end": 2026,
        "schedule": "summer_spring",
    }


def test_season_from_game_date_winter_fall():
    assert career_import.season_from_game_date(
        date(2026, 7, 1), schedule="winter_fall"
    ) == {
        "id": "2026",
        "label": "2026",
        "year_start": 2026,
        "year_end": 2026,
        "schedule": "winter_fall",
    }
    assert career_import.season_from_game_date(
        date(2026, 12, 20), schedule="winter_fall"
    ) == {
        "id": "2026",
        "label": "2026",
        "year_start": 2026,
        "year_end": 2026,
        "schedule": "winter_fall",
    }


def test_remap_summer_to_winter_splits_season():
    mid = career_import.remap_season_slot(
        year_start=2025,
        year_end=2026,
        slot="mid",
        from_schedule="summer_spring",
        to_schedule="winter_fall",
    )
    end = career_import.remap_season_slot(
        year_start=2025,
        year_end=2026,
        slot="end",
        from_schedule="summer_spring",
        to_schedule="winter_fall",
    )
    assert mid == {
        "id": "2025",
        "label": "2025",
        "year_start": 2025,
        "year_end": 2025,
        "slot": "end",
        "schedule": "winter_fall",
        "game_date": None,
    }
    assert end == {
        "id": "2026",
        "label": "2026",
        "year_start": 2026,
        "year_end": 2026,
        "slot": "mid",
        "schedule": "winter_fall",
        "game_date": None,
    }
    # Inverse restores the split season.
    assert career_import.remap_season_slot(
        year_start=2025,
        year_end=2025,
        slot="end",
        from_schedule="winter_fall",
        to_schedule="summer_spring",
    )["id"] == "2025-2026"
    assert career_import.remap_season_slot(
        year_start=2025,
        year_end=2025,
        slot="end",
        from_schedule="winter_fall",
        to_schedule="summer_spring",
    )["slot"] == "mid"
    assert career_import.remap_season_slot(
        year_start=2026,
        year_end=2026,
        slot="mid",
        from_schedule="winter_fall",
        to_schedule="summer_spring",
    )["slot"] == "end"


@pytest.mark.parametrize(
    ("when", "slot"),
    [
        (date(2026, 12, 15), "mid"),
        (date(2026, 12, 31), "mid"),
        (date(2027, 1, 1), "mid"),
        (date(2026, 6, 15), "end"),
        (date(2026, 7, 30), "end"),
        (date(2026, 7, 31), "end"),
        (date(2026, 5, 1), "end"),
        (date(2026, 11, 1), "end"),
        (None, "end"),
    ],
)
def test_suggest_slot_summer_spring(when, slot):
    assert career_import.suggest_slot(when, schedule="summer_spring") == slot


@pytest.mark.parametrize(
    ("when", "slot"),
    [
        (date(2026, 6, 15), "mid"),
        (date(2026, 7, 30), "mid"),
        (date(2026, 7, 31), "end"),
        (date(2026, 12, 20), "end"),
        (date(2027, 1, 1), "end"),
        (date(2026, 5, 1), "end"),
        (None, "end"),
    ],
)
def test_suggest_slot_winter_fall(when, slot):
    assert career_import.suggest_slot(when, schedule="winter_fall") == slot


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

    blocked = career_import.auto_assign_staged(
        "stage-career",
        item["id"],
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
    conflict = career_import.auto_assign_staged(
        "stage-career",
        staged2["item"]["id"],
        replace=False,
    )
    assert conflict["ok"] is False
    assert conflict["needs_replace"] is True
    assert len(careers.list_staging("stage-career")) == 1

    replaced = career_import.auto_assign_staged(
        "stage-career",
        staged2["item"]["id"],
        replace=True,
    )
    assert replaced["ok"] is True
    assert replaced["replaced"] is True
    assert careers.list_staging("stage-career") == []


def test_winter_fall_schedule_mid_and_end(career_root):
    careers.create_career("Calendar Career")
    careers.set_season_schedule("calendar-career", "winter_fall")
    csv_text = "Player;Unique ID;Age\nAda;1;24\n"
    mid = career_import.import_csv_to_career(
        "calendar-career",
        csv_text,
        source_name="mid.csv",
        game_date="2026-07-01",
    )
    end = career_import.import_csv_to_career(
        "calendar-career",
        csv_text,
        source_name="end.csv",
        game_date="2026-11-15",
    )
    assert mid["ok"] is True and mid["slot"] == "mid"
    assert mid["season_id"] == "2026"
    assert end["ok"] is True and end["slot"] == "end"
    assert end["season_id"] == "2026"
    season = careers.get_season("calendar-career", "2026")
    assert season["label"] == "2026"
    assert season["slots"]["mid"]["source_name"] == "mid.csv"
    assert season["slots"]["end"]["source_name"] == "end.csv"


def test_toggle_schedule_remaps_existing_snapshots(career_root):
    careers.create_career("Remap Career")
    csv_text = "Player;Unique ID;Age\nAda;1;24\n"
    # Summer→Spring: Dec mid + May end → 2026/27 mid+end
    career_import.import_csv_to_career(
        "remap-career",
        csv_text,
        source_name="winter-mid.csv",
        game_date="2026-12-20",
    )
    career_import.import_csv_to_career(
        "remap-career",
        csv_text,
        source_name="spring-end.csv",
        game_date="2027-05-20",
    )
    assert careers.get_season("remap-career", "2026-2027") is not None

    result = career_import.apply_season_schedule("remap-career", "winter_fall")
    assert result["changed"] is True
    assert result["moved"] == 2
    assert careers.get_season("remap-career", "2026-2027") is None
    season_2026 = careers.get_season("remap-career", "2026")
    season_2027 = careers.get_season("remap-career", "2027")
    assert season_2026 is not None
    assert season_2026["label"] == "2026"
    assert season_2026["slots"]["mid"] is None
    # Mid 2026/27 → end 2026
    assert season_2026["slots"]["end"]["source_name"] == "winter-mid.csv"
    assert season_2027 is not None
    # End 2026/27 → mid 2027
    assert season_2027["slots"]["mid"]["source_name"] == "spring-end.csv"
    assert season_2027["slots"]["end"] is None

    # Back to Summer→Spring restores split year + mid/end slots.
    back = career_import.apply_season_schedule("remap-career", "summer_spring")
    assert back["changed"] is True
    assert back["moved"] == 2
    season = careers.get_season("remap-career", "2026-2027")
    assert season is not None
    assert season["label"] == "2026/27"
    assert season["slots"]["mid"]["source_name"] == "winter-mid.csv"
    assert season["slots"]["end"]["source_name"] == "spring-end.csv"
    assert careers.list_staging("remap-career") == []


def test_toggle_winter_to_summer_splits_across_seasons(career_root):
    careers.create_career("Conflict Career")
    careers.set_season_schedule("conflict-career", "winter_fall")
    csv_text = "Player;Unique ID;Age\nAda;1;24\n"
    career_import.import_csv_to_career(
        "conflict-career",
        csv_text,
        source_name="july-mid.csv",
        game_date="2026-07-01",
    )
    career_import.import_csv_to_career(
        "conflict-career",
        csv_text,
        source_name="nov-end.csv",
        game_date="2026-11-15",
    )
    # Mid 2026 → end 2025/26; end 2026 → mid 2026/27 (no conflict).
    result = career_import.apply_season_schedule("conflict-career", "summer_spring")
    assert result["changed"] is True
    assert result["moved"] == 2
    assert result["conflict_staged"] == 0
    season_prev = careers.get_season("conflict-career", "2025-2026")
    season_next = careers.get_season("conflict-career", "2026-2027")
    assert season_prev["slots"]["end"]["source_name"] == "july-mid.csv"
    assert season_prev["slots"]["mid"] is None
    assert season_next["slots"]["mid"]["source_name"] == "nov-end.csv"
    assert season_next["slots"]["end"] is None
    assert careers.list_staging("conflict-career") == []


def test_toggle_removes_opposite_year_types(career_root):
    careers.create_career("Mixed Years")
    csv_text = "Player;Unique ID;Age\nAda;1;24\n"
    career_import.import_csv_to_career(
        "mixed-years",
        csv_text,
        source_name="split-mid.csv",
        game_date="2025-12-20",
    )
    # Stuck leftover full-year row while career is still on split schedule.
    careers.upsert_season(
        "mixed-years",
        season_id="2025",
        label="2025",
        year_start=2025,
        year_end=2025,
    )
    assert careers.get_season("mixed-years", "2025-2026") is not None
    assert careers.get_season("mixed-years", "2025") is not None

    to_winter = career_import.apply_season_schedule("mixed-years", "winter_fall")
    assert to_winter["changed"] is True
    winter_seasons = careers.list_seasons("mixed-years")
    assert winter_seasons
    assert all(s["year_start"] == s["year_end"] for s in winter_seasons)
    assert careers.get_season("mixed-years", "2025-2026") is None
    assert careers.get_season("mixed-years", "2025") is not None
    assert careers.get_season("mixed-years", "2025")["slots"]["end"]["source_name"] == (
        "split-mid.csv"
    )

    # Stuck leftover split-year row while on full-year schedule.
    careers.upsert_season(
        "mixed-years",
        season_id="2026-2027",
        label="2026/27",
        year_start=2026,
        year_end=2027,
    )
    to_summer = career_import.apply_season_schedule("mixed-years", "summer_spring")
    assert to_summer["changed"] is True
    summer_seasons = careers.list_seasons("mixed-years")
    assert summer_seasons
    assert all(s["year_start"] != s["year_end"] for s in summer_seasons)
    assert careers.get_season("mixed-years", "2025") is None
    assert careers.get_season("mixed-years", "2026") is None
    assert careers.get_season("mixed-years", "2025-2026") is not None


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
