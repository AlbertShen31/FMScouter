"""Server-side Role Scores view cache.

Keeps scored shortlist rows (and optional page markdown) in process memory so
Dash Stores / DataTable props do not round-trip 10k+ player matrices on every
filter or formation-role focus change.
"""

from __future__ import annotations

import itertools
import threading
from typing import Any

_LOCK = threading.Lock()
_VIEWS: dict[str, dict[str, Any]] = {}
_ORDER: list[str] = []
_MAX_VIEWS = 6
_seq = itertools.count(1)

# Identity / filter / finance fields retained when projecting cached role matrices.
BASE_ROW_KEYS = frozenset(
    {
        "Name",
        "Unique ID",
        "Age",
        "Club",
        "Position",
        "Division",
        "Nation",
        "Second Nation",
        "second_nation",
        "Based In",
        "based_in",
        "Best Pos",
        "Sec. Position",
        "Feet",
        "Left Foot",
        "Right Foot",
        "Injury",
        "Personality",
        "PersonalityTier",
        "Transfer Value",
        "Salary",
        "transfer_value",
        "salary",
        "transfer_value_numeric",
        "transfer_value_min",
        "transfer_value_max",
        "salary_numeric",
        "salary_currency",
        "multi_year",
        "multi_year_status",
        "years_present",
        "_export_source",
        "_source_file_id",
        "Status",
    }
)


def _touch(cache_id: str) -> None:
    try:
        _ORDER.remove(cache_id)
    except ValueError:
        pass
    _ORDER.append(cache_id)
    while len(_ORDER) > _MAX_VIEWS:
        old = _ORDER.pop(0)
        _VIEWS.pop(old, None)


def put_rows(
    rows: list[dict[str, Any]],
    *,
    meta: dict[str, Any] | None = None,
) -> str:
    """Store projected scored rows; return cache_id for the slim Dash payload."""
    with _LOCK:
        cache_id = f"rsv-{next(_seq)}"
        _VIEWS[cache_id] = {
            "rows": rows,
            "meta": dict(meta or {}),
            "markdown_sig": None,
            "markdown_by_key": {},
            "tips_by_key": {},
        }
        _touch(cache_id)
        return cache_id


def get(cache_id: str | None) -> dict[str, Any] | None:
    cid = str(cache_id or "").strip()
    if not cid:
        return None
    with _LOCK:
        view = _VIEWS.get(cid)
        if view is None:
            return None
        _touch(cid)
        return view


def rows_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Resolve scored rows from a slim cache handle or legacy inline ``rows``."""
    if not isinstance(payload, dict):
        return []
    inline = payload.get("rows")
    if isinstance(inline, list) and inline:
        return inline
    view = get(payload.get("cache_id"))
    if not view:
        return []
    rows = view.get("rows")
    return rows if isinstance(rows, list) else []


def payload_has_scores(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("cache_id"):
        return True
    rows = payload.get("rows")
    return isinstance(rows, list)


def project_role_rows(
    rows: list[dict[str, Any]],
    *,
    role_labels: list[str],
    extra_keys: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Copy rows keeping identity/finance + requested role/set-piece columns."""
    keep = set(BASE_ROW_KEYS)
    if extra_keys:
        keep.update(extra_keys)
    for label in role_labels:
        text = str(label or "").strip()
        if not text:
            continue
        keep.add(text)
        keep.add(f"{text} eligible")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append({key: row[key] for key in keep if key in row})
    return out


def clear_markdown(cache_id: str | None) -> None:
    view = get(cache_id)
    if not view:
        return
    view["markdown_sig"] = None
    view["markdown_by_key"] = {}
    view["tips_by_key"] = {}
