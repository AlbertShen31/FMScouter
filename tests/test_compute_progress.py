"""Unit tests for export / upload precompute progress snapshots."""
from __future__ import annotations

import services.compute_progress as cp


def setup_function(_fn):
    cp.reset()


def test_tick_builds_player_detail():
    cp.begin(phase="Scoring role scores…")
    try:
        cp.tick(25, 100, phase="Scoring role scores…")
        props = cp.ui_props()
        assert props["active"] is True
        assert props["label"] == "Scoring role scores…"
        assert props["detail"] == "25 / 100 players"
        assert props["track_class"] == "rs-busy-progress"
        assert props["bar_style"]["width"] == "25.0%"
    finally:
        cp.end()
    assert cp.snapshot()["active"] is False


def test_filename_message_shows_under_counts():
    cp.begin(phase="Precomputing…", message="Romania.csv")
    try:
        cp.update(message="Romania.csv")
        cp.tick(10, 50, phase="Computing player stats…")
        props = cp.ui_props()
        assert props["label"] == "Computing player stats…"
        assert props["detail"] == "10 / 50 players · Romania.csv"
    finally:
        cp.end()


def test_indeterminate_without_total():
    cp.begin(phase="Opening save…")
    try:
        props = cp.ui_props()
        assert "is-indeterminate" in props["track_class"]
        assert props["detail"] == ""
    finally:
        cp.end()


def test_multi_file_bar_resets_per_file():
    cp.begin(phase="Preparing…", file_done=0, file_total=3, context="a.fm")
    try:
        cp.update(
            phase="Building snapshots…",
            context="a.fm",
            file_done=0,
            file_total=3,
            done=25,
            total=100,
        )
        props = cp.ui_props()
        assert props["label"] == "File 1 of 3 · a.fm"
        assert "0/3 files done" in props["detail"]
        assert "25 / 100 players" in props["detail"]
        assert props["bar_style"]["width"] == "25.0%"

        # Next file starts: player counters clear → bar resets / indeterminate.
        cp.update(
            phase="Extracting players…",
            context="b.fm",
            file_done=1,
            file_total=3,
            done=0,
            total=0,
        )
        props = cp.ui_props()
        assert props["label"] == "File 2 of 3 · b.fm"
        assert "1/3 files done" in props["detail"]
        assert "is-indeterminate" in props["track_class"]

        cp.update(
            phase="Building snapshots…",
            context="b.fm",
            file_done=1,
            file_total=3,
            done=50,
            total=100,
        )
        props = cp.ui_props()
        assert props["label"] == "File 2 of 3 · b.fm"
        assert props["bar_style"]["width"] == "50.0%"
    finally:
        cp.end()
