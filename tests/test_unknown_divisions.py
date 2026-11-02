"""Persist and merge unknown Division names for later catalog fills."""
from __future__ import annotations

import json

import services.unknown_divisions as ud


def _isolate(monkeypatch, tmp_path):
    path = tmp_path / "unknown_divisions.json"
    monkeypatch.setattr(ud, "UNKNOWN_DIVISIONS_PATH", path)
    monkeypatch.setattr(ud, "_PENDING", {})
    # Keep auto-flush from firing mid-test so pending can be asserted.
    monkeypatch.setattr(ud, "_LAST_FLUSH", ud.time.monotonic())
    return path


def test_blank_and_entry_key():
    assert ud._blank(None)
    assert ud._blank("-")
    assert ud._blank("—")
    assert not ud._blank("Liga III")
    assert ud._entry_key("Liga III", "Romania") == ud._entry_key("liga iii", "romania")


def test_record_skips_blank_and_counts_pending(monkeypatch, tmp_path):
    path = _isolate(monkeypatch, tmp_path)
    ud.record_unknown_division("", "Romania")
    ud.record_unknown_division("-", "Romania")
    assert ud._PENDING == {}

    ud.record_unknown_division("Liga III", "Romania")
    ud.record_unknown_division("Liga III", "Romania")
    ud.record_unknown_division("Liga III", "—")  # empty nation → separate key
    assert len(ud._PENDING) == 2
    keyed = {item["nation"]: item for item in ud._PENDING.values()}
    assert keyed["Romania"]["count"] == 2
    assert keyed[""]["count"] == 1


def test_flush_merges_file_and_pending(monkeypatch, tmp_path):
    path = _isolate(monkeypatch, tmp_path)
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "division": "Liga III",
                        "nation": "Romania",
                        "count": 3,
                        "last_seen": "2026-01-01T00:00:00+00:00",
                    },
                    {"division": "", "nation": "X"},
                    "skip-me",
                ]
            }
        ),
        encoding="utf-8",
    )
    ud.record_unknown_division("Liga III", "Romania")
    ud.record_unknown_division("Liga IV Arad", "Romania")
    ud.flush_unknown_divisions(force=True)

    payload = json.loads(path.read_text(encoding="utf-8"))
    by_div = {item["division"]: item for item in payload["entries"]}
    assert by_div["Liga III"]["count"] == 4
    assert by_div["Liga IV Arad"]["count"] == 1
    assert by_div["Liga IV Arad"]["nation"] == "Romania"
    assert ud._PENDING == {}


def test_load_file_handles_missing_and_corrupt(monkeypatch, tmp_path):
    path = _isolate(monkeypatch, tmp_path)
    assert ud._load_file(path) == []
    path.write_text("{not-json", encoding="utf-8")
    assert ud._load_file(path) == []
    path.write_text(json.dumps({"entries": "nope"}), encoding="utf-8")
    assert ud._load_file(path) == []


def test_flush_noops_when_empty_or_throttled(monkeypatch, tmp_path):
    path = _isolate(monkeypatch, tmp_path)
    ud.flush_unknown_divisions(force=True)
    assert not path.exists()

    ud.record_unknown_division("Mystery League", "Nowhere")
    monkeypatch.setattr(ud, "_LAST_FLUSH", ud.time.monotonic())
    ud.flush_unknown_divisions(force=False)
    assert not path.exists()
    assert ud._PENDING
    ud.flush_unknown_divisions(force=True)
    assert path.is_file()
