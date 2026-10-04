"""Thread-safe progress snapshot for long export / upload precompute jobs.

Dash callbacks are request-scoped, so mid-job UI updates come from a
``dcc.Interval`` poll that reads :func:`snapshot` while the worker thread
runs the heavy compute.
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_depth = 0
_state: dict[str, Any] = {
    "active": False,
    "phase": "",
    "message": "",
    "done": 0,
    "total": 0,
}


def begin(message: str = "", *, phase: str = "") -> None:
    """Start (or nest) a user-visible job."""
    global _depth
    with _lock:
        _depth += 1
        _state["active"] = True
        phase_text = str(phase or message or "").strip()
        message_text = str(message or "").strip()
        if phase_text:
            _state["phase"] = phase_text
        # Keep message for secondary context (filename); skip when it only
        # duplicates the phase label.
        if message_text and message_text != phase_text:
            _state["message"] = message_text
        elif _depth == 1:
            _state["message"] = ""
        if _depth == 1:
            _state["done"] = 0
            _state["total"] = 0


def update(
    *,
    phase: str | None = None,
    message: str | None = None,
    done: int | None = None,
    total: int | None = None,
) -> None:
    """Patch the current progress snapshot (no-op fields stay unchanged)."""
    global _depth
    with _lock:
        if not _state["active"]:
            # Allow compute helpers to publish even if the page forgot begin().
            _state["active"] = True
            _depth = max(_depth, 1)
        if phase is not None:
            _state["phase"] = str(phase)
        if message is not None:
            _state["message"] = str(message)
        if total is not None:
            try:
                _state["total"] = max(0, int(total))
            except (TypeError, ValueError):
                pass
        if done is not None:
            try:
                _state["done"] = max(0, int(done))
            except (TypeError, ValueError):
                pass


def tick(done: int, total: int, *, phase: str | None = None, message: str | None = None) -> None:
    """Convenience for player-loop progress."""
    update(done=done, total=total, phase=phase, message=message)


def end() -> None:
    """Finish one nested job; clears active state at depth 0."""
    global _depth
    with _lock:
        _depth = max(0, _depth - 1)
        if _depth == 0:
            _state["active"] = False
            _state["phase"] = ""
            _state["message"] = ""
            _state["done"] = 0
            _state["total"] = 0


def snapshot() -> dict[str, Any]:
    """Return a shallow copy safe for callbacks / JSON."""
    with _lock:
        return dict(_state)


def reset() -> None:
    """Clear progress state (tests / recovery)."""
    global _depth
    with _lock:
        _depth = 0
        _state["active"] = False
        _state["phase"] = ""
        _state["message"] = ""
        _state["done"] = 0
        _state["total"] = 0


def ui_props(snap: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map a snapshot to busy-overlay label / bar / detail props."""
    snap = snap if snap is not None else snapshot()
    phase = str(snap.get("phase") or "").strip()
    message = str(snap.get("message") or "").strip()
    label = phase or message or "Working…"
    try:
        done = max(0, int(snap.get("done") or 0))
    except (TypeError, ValueError):
        done = 0
    try:
        total = max(0, int(snap.get("total") or 0))
    except (TypeError, ValueError):
        total = 0

    if total > 0:
        pct = min(100.0, (100.0 * done) / total)
        detail = f"{done:,} / {total:,} players"
        if message and message != phase:
            detail = f"{detail} · {message}"
        return {
            "label": label,
            "track_class": "rs-busy-progress",
            "bar_style": {"width": f"{pct:.1f}%"},
            "detail": detail,
            "active": bool(snap.get("active")),
        }

    detail = message if message and message != label else ""
    return {
        "label": label,
        "track_class": "rs-busy-progress is-indeterminate",
        "bar_style": {"width": "40%"},
        "detail": detail,
        "active": bool(snap.get("active")),
    }
