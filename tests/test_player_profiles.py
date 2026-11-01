"""Profile libraries, identity matching, and role depth ranking."""
from __future__ import annotations

import pytest

import services.formations as fm
import services.player_profiles as pp


def _isolate_profiles(monkeypatch, tmp_path):
    root = tmp_path / "profiles"
    packs = root / "packs"
    backups = root / "backups"
    packs.mkdir(parents=True)
    monkeypatch.setattr(pp, "PROFILES_DIR", root)
    monkeypatch.setattr(pp, "PROFILES_PACKS_DIR", packs)
    monkeypatch.setattr(pp, "PROFILES_ACTIVE_PATH", root / "active.json")
    monkeypatch.setattr(pp, "PROFILES_BACKUPS_DIR", backups)
    monkeypatch.setattr(pp, "PROFILES_INDEX_PATH", root / "index.json")
    monkeypatch.setattr(pp, "_LEGACY_SLOT_DEPTH_PATH", root / "slot_depth.json")
    monkeypatch.setattr(fm, "exists", lambda _fid: True)
    monkeypatch.setattr(fm, "load", lambda _fid, persist=False: {"name": "5-1-4-0 Dracula"})
    monkeypatch.setattr(fm, "active_id", lambda: "5-1-4-0-dracula")
    return root


def _role_item(name: str, uid: str, role: str, score: float, *, overall: float = 80):
    return {
        "player_key": f"{name}|{uid}",
        "role_column": role,
        "row": {
            "Name": name,
            "Unique ID": uid,
            "Club": "City",
            "Role": role,
            "Score": score,
            "overall": overall,
        },
    }


def test_identity_helpers_prefer_unique_id():
    assert pp.split_player_key("Ada|1844") == ("Ada", "1844")
    assert pp.split_player_key("Ada") == ("Ada", "")
    profile = {
        "player_key": "Ada|1844",
        "row": {"Name": "Ada Popescu", "Unique ID": "1844", "Club": "CFR"},
    }
    assert pp.profile_identity(profile) == ("Ada Popescu", "CFR")
    assert pp._profile_unique_id(profile) == "1844"
    legacy = {"player_key": "Ada|CFR", "row": {}}
    assert pp.profile_identity(legacy) == ("Ada", "CFR")
    assert pp.profile_upsert_key({"player_key": "Ada|1", "role_column": "BPD"}) == (
        "Ada|1",
        "BPD",
    )
    assert pp._slugify("5-1-4-0 Dracula!") == "5-1-4-0-dracula"


def test_create_list_switch_and_delete_libraries(tmp_path, monkeypatch):
    _isolate_profiles(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="profile name"):
        pp.create_library("", "4-3-3")
    with pytest.raises(ValueError, match="formation"):
        pp.create_library("Home", "")
    first = pp.create_library("Home", "4-3-3")
    assert first["name"] == "Home"
    assert first["formation_id"] == "4-3-3"
    assert pp.active_library_id() == first["id"]
    second = pp.create_library("Away", "4-4-2", activate=False)
    assert pp.active_library_id() == first["id"]
    pp.set_active_library(second["id"])
    assert pp.active_library_id() == second["id"]
    labels = [item["label"] for item in pp.library_options()]
    assert any("Home" in label and "Dracula" in label for label in labels)
    assert pp.delete_library(first["id"]) is True
    with pytest.raises(ValueError, match="only"):
        pp.delete_library(second["id"])


def test_save_upsert_rank_and_delete_profiles(tmp_path, monkeypatch):
    _isolate_profiles(monkeypatch, tmp_path)
    pp.create_library("Home", "4-3-3")
    saved = pp.save_profile_rows(
        [
            _role_item("Ada", "1", "BPD", 14.2, overall=70),
            _role_item("Ben", "2", "BPD", 16.1, overall=60),
            _role_item("Cara", "3", "VOL", 11.0),
        ],
        saved_from="role_scores",
        stage_exports=False,
        reinstate_slots=False,
    )
    assert len(saved) == 3
    assert len(pp.list_role_profiles()) == 3
    ranked = pp.auto_rank_role_by_score("BPD")
    assert ranked == 2
    ordered = pp.ordered_profiles_for_role("BPD")
    assert [pp.profile_identity(entry)[0] for entry in ordered] == ["Ben", "Ada"]
    assert ordered[0]["depth_rank"] == 1
    updated = pp.save_profile_rows(
        [_role_item("Ada", "1", "BPD", 17.0, overall=90)],
        saved_from="role_scores",
        stage_exports=False,
        reinstate_slots=False,
    )
    assert updated[0]["id"] == saved[0]["id"]
    assert updated[0]["row"]["Score"] == 17.0
    assert pp.role_score_from_profile(updated[0])["score"] == pytest.approx(17.0)
    assert pp.delete_profile(saved[1]["id"]) is True
    assert len(pp.list_role_profiles()) == 2


def test_match_file_player_by_uid_then_name_club():
    by_uid = {"1844": {"name": "Ada", "club": "CFR"}}
    by_name = {
        "ada": [
            {"name": "Ada", "club": "Rapid"},
            {"name": "Ada", "club": "CFR"},
        ]
    }
    club_of = lambda item: item["club"]
    hit = pp._match_file_player(
        {"row": {"Unique ID": "1844", "Name": "Ada", "Club": "CFR"}},
        by_uid=by_uid,
        by_name=by_name,
        club_of=club_of,
    )
    assert hit["club"] == "CFR"
    name_hit = pp._match_file_player(
        {"player_key": "Ada|CFR", "row": {"Name": "Ada", "Club": "CFR"}},
        by_uid={},
        by_name=by_name,
        club_of=club_of,
    )
    assert name_hit["club"] == "CFR"
