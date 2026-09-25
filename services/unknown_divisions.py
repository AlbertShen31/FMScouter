"""Persist FM Division names with no known tier for later catalog fills."""
from __future__ import annotations

import atexit
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import UNKNOWN_DIVISIONS_PATH
from scoring.division_tiers import _fold

_LOCK = threading.Lock()
_PENDING: dict[str, dict[str, Any]] = {}
_LAST_FLUSH = 0.0
_FLUSH_INTERVAL_S = 2.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _blank(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text in ("-", "—")


def _entry_key(division: str, nation: str) -> str:
    return f"{_fold(nation)}\0{_fold(division)}"


def _load_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        division = str(raw.get("division") or "").strip()
        if _blank(division):
            continue
        nation = str(raw.get("nation") or "").strip()
        if nation in ("-", "—"):
            nation = ""
        out.append(
            {
                "division": division,
                "nation": nation,
                "count": max(1, int(raw.get("count") or 1)),
                "last_seen": str(raw.get("last_seen") or ""),
            }
        )
    return out


def _merge(existing: list[dict[str, Any]], pending: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in existing:
        key = _entry_key(item["division"], item.get("nation") or "")
        by_key[key] = dict(item)
    for key, pending_item in pending.items():
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = dict(pending_item)
            continue
        cur["count"] = int(cur.get("count") or 0) + int(pending_item.get("count") or 0)
        cur["last_seen"] = pending_item.get("last_seen") or cur.get("last_seen") or ""
        if pending_item.get("nation") and not cur.get("nation"):
            cur["nation"] = pending_item["nation"]
    return sorted(
        by_key.values(),
        key=lambda item: (_fold(item.get("nation") or ""), _fold(item.get("division") or "")),
    )


def flush_unknown_divisions(*, force: bool = False) -> None:
    """Write pending unknown divisions to disk."""
    global _LAST_FLUSH
    with _LOCK:
        if not _PENDING:
            return
        now = time.monotonic()
        if not force and (now - _LAST_FLUSH) < _FLUSH_INTERVAL_S:
            return
        pending = dict(_PENDING)
        _PENDING.clear()
        _LAST_FLUSH = now
        path = UNKNOWN_DIVISIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = _merge(_load_file(path), pending)
    payload = {"updated_at": _utc_now(), "entries": entries}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record_unknown_division(division: Any, nation: Any = "") -> None:
    """Remember a Division with no classified tier (skipped when blank)."""
    name = str(division or "").strip()
    if _blank(name):
        return
    nat = str(nation or "").strip()
    if nat in ("-", "—"):
        nat = ""
    key = _entry_key(name, nat)
    stamp = _utc_now()
    with _LOCK:
        cur = _PENDING.get(key)
        if cur is None:
            _PENDING[key] = {
                "division": name,
                "nation": nat,
                "count": 1,
                "last_seen": stamp,
            }
        else:
            cur["count"] = int(cur.get("count") or 0) + 1
            cur["last_seen"] = stamp
            if nat and not cur.get("nation"):
                cur["nation"] = nat
        due = (time.monotonic() - _LAST_FLUSH) >= _FLUSH_INTERVAL_S
    if due:
        flush_unknown_divisions()


atexit.register(lambda: flush_unknown_divisions(force=True))
