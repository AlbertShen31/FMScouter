"""Unit tests for fmsave player-decode progress hooks."""
from __future__ import annotations

from types import SimpleNamespace

import services.compute_progress as cp
import services.fmsave_export as fms


def setup_function(_fn):
    cp.reset()


def test_track_player_load_progress_ticks_from_hooks(monkeypatch):
    from fmsave._context import SaveContext
    from fmsave.readers.players import PlayerDecoder

    fake_records = SimpleNamespace(record_offsets=list(range(40)))

    def fake_build(_self):
        return fake_records

    def fake_decode(_self, *_args, **_kwargs):
        return ("player", None)

    monkeypatch.setattr(SaveContext, "_build_player_records", fake_build)
    monkeypatch.setattr(PlayerDecoder, "decode", fake_decode)

    cp.begin(phase="Reading save…")
    try:
        with fms._track_player_load_progress():
            SaveContext._build_player_records(object())
            props = cp.ui_props()
            assert props["label"] == "Loading players…"
            assert props["detail"] == "0 / 40 players"
            assert props["bar_style"]["width"] == "0.0%"

            for _ in range(40):
                PlayerDecoder.decode(
                    object(),
                    b"",
                    0,
                    0,
                    is_last_record=False,
                    suspension_entries=(),
                )

            props = cp.ui_props()
            assert props["detail"] == "40 / 40 players"
            assert props["bar_style"]["width"] == "100.0%"
            assert "is-indeterminate" not in props["track_class"]
    finally:
        cp.end()
