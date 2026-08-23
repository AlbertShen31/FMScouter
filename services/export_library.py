"""On-disk CSV library for Role scores / Player stats / Squad finance.

Files live under ``data/uploads/`` with metadata in ``index.json``. Eligibility is
inferred from CSV headers (same gates as each page's parser).
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import UPLOADS_DIR, UPLOADS_INDEX_PATH, VIEWS_DIR
from scoring.role_scorer import (
    FINANCE_CSV,
    IDENTITY,
    _has_attribute_columns,
    _has_name_column,
    sniff_delimiter,
    unique_headers,
)
from scoring.stats_scorer import _has_stats_columns

PAGE_LABELS = {
    "role_scores": "Role scores",
    "stats": "Player stats",
    "squad_finance": "Squad finance",
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def ensure_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    VIEWS_DIR.mkdir(parents=True, exist_ok=True)
    if not UPLOADS_INDEX_PATH.exists():
        UPLOADS_INDEX_PATH.write_text("[]\n", encoding="utf-8")


def _write_index(entries: list[dict[str, Any]]) -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_INDEX_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_index() -> list[dict[str, Any]]:
    ensure_dirs()
    if not UPLOADS_INDEX_PATH.exists():
        return []
    try:
        data = json.loads(UPLOADS_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _safe_filename(name: str) -> str:
    base = Path(name or "export.csv").name
    if not base.lower().endswith(".csv"):
        base = f"{base}.csv"
    stem = _SAFE_NAME.sub("_", Path(base).stem).strip("._") or "export"
    return f"{stem}.csv"


def _read_header(text: str) -> list[str]:
    if not text or not text.strip():
        raise ValueError("The file is empty.")
    delim = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        raw = next(reader)
    except StopIteration as exc:
        raise ValueError("The file has no header row.") from exc
    return unique_headers(raw)


def _header_bases(header: list[str]) -> set[str]:
    return {h.split(".")[0] for h in header}


def _has_aliases(header: list[str], aliases: list[str]) -> bool:
    keys = set(header)
    bases = _header_bases(header)
    return any(alias in keys or alias in bases for alias in aliases)


def _has_player_info(header: list[str]) -> bool:
    """Club / Age / Position (or Best Pos) — identity beyond Name."""
    club = _has_aliases(header, IDENTITY.get("Club", ["Club"]))
    age = _has_aliases(header, IDENTITY.get("Age", ["Age"]))
    pos = _has_aliases(header, IDENTITY.get("Position", ["Position"])) or _has_aliases(
        header, IDENTITY.get("BestPos", ["Best Pos"])
    )
    return sum(bool(x) for x in (club, age, pos)) >= 2


def _has_salary(header: list[str]) -> bool:
    return _has_aliases(header, FINANCE_CSV.get("salary", ["Salary"]))


def _has_fees(header: list[str]) -> bool:
    return _has_aliases(
        header, FINANCE_CSV.get("appearance_fee", ["Appearance Fee"])
    ) or _has_aliases(
        header, FINANCE_CSV.get("unused_sub_fee", ["Unused Substitute Fee"])
    )


def classify_eligibility(text: str) -> dict[str, Any]:
    """Return page eligibility flags from CSV text (header-based)."""
    header = _read_header(text)
    has_name = _has_name_column(header)
    has_attrs = _has_attribute_columns(header)
    has_stats = _has_stats_columns(header)
    has_info = _has_player_info(header)
    has_sal = _has_salary(header)
    has_fee = _has_fees(header)

    role_ok = has_name and has_attrs and has_info
    stats_ok = has_name and has_stats and has_info
    finance_ok = has_name and has_sal and has_fee and has_info

    notes: list[str] = []
    if not has_name:
        notes.append("Missing Name/Player")
    if has_name and not has_info:
        notes.append("Limited player info (need Club/Age/Position)")
    if has_name and not has_attrs and not has_stats and not has_sal:
        notes.append("No attributes, stats, or salary columns")

    return {
        "role_scores": role_ok,
        "stats": stats_ok,
        "squad_finance": finance_ok,
        "has_name": has_name,
        "has_attributes": has_attrs,
        "has_stats": has_stats,
        "has_player_info": has_info,
        "has_salary": has_sal,
        "has_fees": has_fee,
        "notes": notes,
        "pages": [
            key
            for key, ok in (
                ("role_scores", role_ok),
                ("stats", stats_ok),
                ("squad_finance", finance_ok),
            )
            if ok
        ],
    }


def display_label(entry: dict[str, Any] | None) -> str:
    """User-facing name for a saved file."""
    if not entry:
        return "export.csv"
    name = (entry.get("display_name") or "").strip()
    if name:
        return name
    return (
        entry.get("original_name")
        or entry.get("stored_name")
        or entry.get("id")
        or "export.csv"
    )


def list_files(*, page: str | None = None) -> list[dict[str, Any]]:
    """Return index entries newest-first. Optional ``page`` filters eligibility."""
    ensure_dirs()
    entries = []
    for entry in _read_index():
        path = UPLOADS_DIR / (entry.get("stored_name") or "")
        if not path.is_file():
            continue
        if page and page not in (entry.get("pages") or []):
            continue
        item = dict(entry)
        item.setdefault("display_name", item.get("original_name") or "")
        item.setdefault("user_note", "")
        # Legacy: ``notes`` was eligibility hints (list). Keep as eligibility_notes.
        if "eligibility_notes" not in item:
            legacy = item.get("notes")
            item["eligibility_notes"] = (
                list(legacy) if isinstance(legacy, list) else []
            )
        entries.append(item)
    entries.sort(key=lambda e: e.get("saved_at") or "", reverse=True)
    return entries


def get_file(file_id: str) -> dict[str, Any] | None:
    for entry in list_files():
        if entry.get("id") == file_id:
            return entry
    return None


def read_text(file_id: str) -> tuple[str, dict[str, Any]]:
    entry = get_file(file_id)
    if not entry:
        raise FileNotFoundError("Saved file not found.")
    path = UPLOADS_DIR / entry["stored_name"]
    if not path.is_file():
        raise FileNotFoundError("Saved file missing on disk.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return text, entry


def save_upload(filename: str, text: str) -> dict[str, Any]:
    """Persist CSV text and append an index entry."""
    ensure_dirs()
    eligibility = classify_eligibility(text)
    original = Path(filename or "export.csv").name
    safe = _safe_filename(original)
    file_id = uuid.uuid4().hex[:12]
    stored = f"{file_id}_{safe}"
    path = UPLOADS_DIR / stored
    path.write_text(text, encoding="utf-8")
    entry = {
        "id": file_id,
        "original_name": original,
        "display_name": original,
        "user_note": "",
        "stored_name": stored,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "size_bytes": path.stat().st_size,
        "pages": eligibility["pages"],
        "role_scores": eligibility["role_scores"],
        "stats": eligibility["stats"],
        "squad_finance": eligibility["squad_finance"],
        "has_attributes": eligibility["has_attributes"],
        "has_stats": eligibility["has_stats"],
        "has_salary": eligibility["has_salary"],
        "has_fees": eligibility["has_fees"],
        "has_player_info": eligibility["has_player_info"],
        "eligibility_notes": eligibility["notes"],
    }
    index = _read_index()
    index.append(entry)
    _write_index(index)
    return entry


def update_file_meta(
    file_id: str,
    *,
    display_name: str | None = None,
    user_note: str | None = None,
) -> dict[str, Any] | None:
    """Rename and/or set a user note for a saved file (metadata only)."""
    ensure_dirs()
    index = _read_index()
    updated = None
    for entry in index:
        if entry.get("id") != file_id:
            continue
        if display_name is not None:
            name = str(display_name).strip()
            if not name:
                raise ValueError("Name cannot be empty.")
            if len(name) > 120:
                raise ValueError("Name is too long (max 120 characters).")
            entry["display_name"] = name
        if user_note is not None:
            note = str(user_note).strip()
            if len(note) > 500:
                raise ValueError("Note is too long (max 500 characters).")
            entry["user_note"] = note
        updated = dict(entry)
        break
    if not updated:
        return None
    _write_index(index)
    return get_file(file_id) or updated


def delete_file(file_id: str) -> bool:
    ensure_dirs()
    index = _read_index()
    kept: list[dict[str, Any]] = []
    removed = None
    for entry in index:
        if entry.get("id") == file_id:
            removed = entry
        else:
            kept.append(entry)
    if not removed:
        return False
    path = UPLOADS_DIR / (removed.get("stored_name") or "")
    if path.is_file():
        path.unlink()
    _write_index(kept)
    return True


def select_options(*, page: str | None = None) -> list[dict[str, str]]:
    """Dash Select / Mantine options for eligible files."""
    opts = []
    for entry in list_files(page=page):
        name = display_label(entry)
        when = (entry.get("saved_at") or "")[:10]
        note = (entry.get("user_note") or "").strip()
        label = f"{name}" + (f" · {when}" if when else "")
        if note:
            short = note if len(note) <= 40 else note[:37] + "…"
            label = f"{label} — {short}"
        opts.append({"value": entry["id"], "label": label})
    return opts


def list_view_files() -> list[Path]:
    ensure_dirs()
    files = []
    for path in sorted(VIEWS_DIR.iterdir()):
        if path.is_file() and path.name not in (".gitkeep", "README.md"):
            files.append(path)
    return files


def primary_view_file() -> Path | None:
    files = list_view_files()
    return files[0] if files else None
