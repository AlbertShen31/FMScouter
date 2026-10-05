"""Unit tests for FM save path defaults and picker initial directory."""
from __future__ import annotations

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
