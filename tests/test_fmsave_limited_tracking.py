"""fmsave exports skip limited-tracking detection."""
from __future__ import annotations

import services.export_library as lib


def test_is_fmsave_export_by_tag():
    assert lib.is_fmsave_export({"export_source": "fmsave"})
    assert lib.is_fmsave_export({"export_source": "FMSAVE"})
    assert not lib.is_fmsave_export({"export_source": "moneyball"})
    assert not lib.is_fmsave_export({})


def test_is_fmsave_export_by_filename():
    assert lib.is_fmsave_export(
        {"original_name": "fmsave_all_Leicester_Beta_2027-04.csv"}
    )
    assert lib.is_fmsave_export(
        {
            "stored_name": "f6d9b76b5982_fmsave_all_Leicester_Beta_2027-04.csv",
            "original_name": "other.csv",
        }
    )
    assert not lib.is_fmsave_export({"original_name": "Romania_2029-11.csv"})


def test_list_limited_tracking_skips_fmsave(monkeypatch):
    entries = [
        {
            "id": "a",
            "original_name": "Romania.csv",
            "limited_tracking_divisions": ["Ligat Ha'Al", "CSL"],
        },
        {
            "id": "b",
            "export_source": "fmsave",
            "original_name": "fmsave_all_X.csv",
            "limited_tracking_divisions": ["Premier League", "EFL Championship"],
        },
    ]
    monkeypatch.setattr(lib, "list_files", lambda: entries)
    monkeypatch.setattr(
        lib, "get_file", lambda fid: next((e for e in entries if e["id"] == fid), None)
    )
    assert lib.list_limited_tracking_divisions() == ["CSL", "Ligat Ha'Al"]
    assert lib.list_limited_tracking_divisions(file_id="b") == []
    assert lib.list_limited_tracking_divisions(file_id="a") == ["CSL", "Ligat Ha'Al"]
