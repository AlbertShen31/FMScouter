"""Unit tests for FM save path defaults and picker initial directory."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

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


def test_default_fm_games_dirs_prefers_existing_fm27(tmp_path: Path):
    fm26 = tmp_path / "Football Manager 26" / "games"
    fm27 = tmp_path / "Football Manager 27" / "games"
    fm26.mkdir(parents=True)
    fm27.mkdir(parents=True)

    def _fake(edition: str) -> Path | None:
        if edition.endswith("27"):
            return fm27
        if edition.endswith("26"):
            return fm26
        return None

    with patch.object(fms, "_fm_games_dir_for_edition", side_effect=_fake):
        assert fms.default_fm_games_dirs() == (fm27, fm26)
        assert fms.default_fm_games_dir() == fm27
        assert fms.default_fm26_games_dir() == fm27


def test_default_save_path_picks_newest_across_editions(tmp_path: Path):
    fm26 = tmp_path / "fm26" / "games"
    fm27 = tmp_path / "fm27" / "games"
    fm26.mkdir(parents=True)
    fm27.mkdir(parents=True)
    older = fm26 / "old.fm"
    newer = fm27 / "new.fm"
    older.write_text("a", encoding="utf-8")
    newer.write_text("b", encoding="utf-8")
    older_mtime = older.stat().st_mtime
    import os

    os.utime(newer, (older_mtime + 10, older_mtime + 10))

    with patch.object(fms, "default_fm_games_dirs", return_value=(fm27, fm26)):
        assert fms.default_save_path() == str(newer)


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
