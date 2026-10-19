"""Unit tests for FM save path defaults and picker initial directory."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import services.fmsave_export as fms


def test_dialog_initial_dir_prefers_existing_file_parent(tmp_path: Path):
    save = tmp_path / "career.fm"
    save.write_text("x", encoding="utf-8")
    assert fms._dialog_initial_dir(save) == tmp_path


def test_dialog_initial_dir_walks_up_missing_path(tmp_path: Path):
    missing = tmp_path / "games" / "missing.fm"
    assert fms._dialog_initial_dir(missing) == tmp_path


def test_dialog_initial_dir_falls_back_to_home_when_empty():
    found = fms._dialog_initial_dir("")
    assert found.is_dir()


def test_export_filename_includes_game_year_month():
    path = Path("/saves/FC Romania.fm")
    assert (
        fms._export_filename("squad", path, date(2029, 11, 15))
        == "fmsave_squad_FC Romania_2029-11.csv"
    )
    assert (
        fms._export_filename("all", path, date(2028, 6, 1))
        == "fmsave_all_FC Romania_2028-06.csv"
    )
    assert fms._export_filename("squad", path, None) == "fmsave_squad_FC Romania.csv"
