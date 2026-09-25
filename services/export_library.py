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
import zipfile
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

KIND_SINGLE = "single"
KIND_MULTI_YEAR = "multi_year"
YEAR_KEYS = ("1", "2", "3")
DEFAULT_YEAR_WEIGHTS = {"1": 0.5, "2": 0.75, "3": 1.0}

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


def _has_transfer_value(header: list[str]) -> bool:
    return _has_aliases(
        header, FINANCE_CSV.get("transfer_value", ["Transfer Value"])
    )


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
    has_tv = _has_transfer_value(header)
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
        "has_transfer_value": has_tv,
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


def has_shortlist_finance(file_id: str | None) -> bool:
    """Whether a saved export has Transfer Value and/or Salary for shortlists."""
    fid = str(file_id or "").strip()
    if not fid:
        return False
    entry = get_file(fid)
    if not entry:
        return False
    if is_multi_year(entry):
        return any(
            has_shortlist_finance(src) for src in configured_years(entry).values()
        )
    if entry.get("has_transfer_value") or entry.get("has_salary"):
        return True
    # Legacy library rows predate has_transfer_value; Salary alone is enough.
    return bool(entry.get("has_salary"))


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


def is_multi_year(entry: dict[str, Any] | None) -> bool:
    return bool(entry) and entry.get("kind") == KIND_MULTI_YEAR


def configured_years(entry: dict[str, Any] | None) -> dict[str, str]:
    """Return year key → source file_id for slots that are filled."""
    if not entry:
        return {}
    raw = entry.get("years") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key in YEAR_KEYS:
        fid = str(raw.get(key) or "").strip()
        if fid:
            out[key] = fid
    return out


def year_weights(entry: dict[str, Any] | None) -> dict[str, float]:
    weights = dict(DEFAULT_YEAR_WEIGHTS)
    if not entry:
        return weights
    raw = entry.get("weights") or {}
    if isinstance(raw, dict):
        for key in YEAR_KEYS:
            try:
                val = float(raw.get(key, weights[key]))
            except (TypeError, ValueError):
                continue
            if val > 0:
                weights[key] = val
    return weights


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    item = dict(entry)
    item.setdefault("kind", KIND_SINGLE)
    item.setdefault("display_name", item.get("original_name") or "")
    item.setdefault("user_note", "")
    if "eligibility_notes" not in item:
        legacy = item.get("notes")
        item["eligibility_notes"] = list(legacy) if isinstance(legacy, list) else []
    return item


def _single_csv_exists(entry: dict[str, Any]) -> bool:
    path = UPLOADS_DIR / (entry.get("stored_name") or "")
    return path.is_file()


def _pack_sources_ok(entry: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> bool:
    years = configured_years(entry)
    if not years:
        return False
    for fid in years.values():
        src = by_id.get(fid)
        if not src or src.get("kind") == KIND_MULTI_YEAR:
            return False
        if not _single_csv_exists(src):
            return False
    return True


def list_files(*, page: str | None = None) -> list[dict[str, Any]]:
    """Return index entries newest-first. Optional ``page`` filters eligibility."""
    ensure_dirs()
    raw_index = _read_index()
    by_id = {e.get("id"): e for e in raw_index if e.get("id")}
    entries = []
    for entry in raw_index:
        if is_multi_year(entry):
            if not _pack_sources_ok(entry, by_id):
                continue
        elif not _single_csv_exists(entry):
            continue
        if page and page not in (entry.get("pages") or []):
            continue
        entries.append(_normalize_entry(entry))
    entries.sort(key=lambda e: e.get("saved_at") or "", reverse=True)
    return entries


def list_single_files(*, page: str | None = None) -> list[dict[str, Any]]:
    """Single CSV library rows only (for multi-year pack source pickers)."""
    return [e for e in list_files(page=page) if not is_multi_year(e)]


def get_file(file_id: str) -> dict[str, Any] | None:
    for entry in list_files():
        if entry.get("id") == file_id:
            return entry
    return None


def file_eligible_for(file_id: str, page: str) -> bool:
    """Whether a saved upload is eligible for a scouting page (header-based)."""
    entry = get_file(file_id)
    if not entry:
        return False
    return page in (entry.get("pages") or [])


STATS_REQUIRED_MSG = (
    "Profiles need a saved file eligible for Player stats "
    "(Moneyball statistics columns). Upload a combined export on Uploads, "
    "or pick one from the library dropdown."
)


def read_text(file_id: str) -> tuple[str, dict[str, Any]]:
    entry = get_file(file_id)
    if not entry:
        raise FileNotFoundError("Saved file not found.")
    if is_multi_year(entry):
        raise ValueError(
            "Multi-year packs have no single CSV. Load from cache or recompute on Uploads."
        )
    path = UPLOADS_DIR / entry["stored_name"]
    if not path.is_file():
        raise FileNotFoundError("Saved file missing on disk.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return text, entry


def _pack_eligibility(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Intersection of source capabilities; packs never include squad finance."""
    if not sources:
        raise ValueError("Pick at least one season file.")
    role_ok = all(bool(s.get("role_scores")) for s in sources)
    stats_ok = all(bool(s.get("stats")) for s in sources)
    notes: list[str] = []
    if not role_ok and not stats_ok:
        notes.append("Sources do not share Role scores or Player stats eligibility")
    elif not role_ok:
        notes.append("Not all sources are eligible for Role scores")
    elif not stats_ok:
        notes.append("Not all sources are eligible for Player stats")
    pages = [
        key
        for key, ok in (("role_scores", role_ok), ("stats", stats_ok))
        if ok
    ]
    return {
        "role_scores": role_ok,
        "stats": stats_ok,
        "squad_finance": False,
        "has_attributes": all(bool(s.get("has_attributes")) for s in sources),
        "has_stats": all(bool(s.get("has_stats")) for s in sources),
        "has_salary": False,
        "has_fees": False,
        "has_player_info": all(bool(s.get("has_player_info", True)) for s in sources),
        "eligibility_notes": notes,
        "pages": pages,
    }


def _normalize_year_map(years: dict[str, str] | None) -> dict[str, str | None]:
    raw = years or {}
    out: dict[str, str | None] = {key: None for key in YEAR_KEYS}
    seen: set[str] = set()
    for key in YEAR_KEYS:
        fid = str(raw.get(key) or "").strip() or None
        if fid:
            if fid in seen:
                raise ValueError("Each season file can only be assigned once.")
            seen.add(fid)
        out[key] = fid
    if not any(out.values()):
        raise ValueError("Assign at least one season (Year 3 = most recent).")
    return out


def save_multi_year_pack(
    *,
    display_name: str,
    years: dict[str, str] | None,
    user_note: str = "",
    pack_id: str | None = None,
) -> dict[str, Any]:
    """Create or update a multi-year pack entry (metadata only; no CSV on disk)."""
    ensure_dirs()
    name = str(display_name or "").strip()
    if not name:
        raise ValueError("Name cannot be empty.")
    if len(name) > 120:
        raise ValueError("Name is too long (max 120 characters).")
    note = str(user_note or "").strip()
    if len(note) > 500:
        raise ValueError("Note is too long (max 500 characters).")

    year_map = _normalize_year_map(years)
    sources: list[dict[str, Any]] = []
    for key in YEAR_KEYS:
        fid = year_map[key]
        if not fid:
            continue
        src = get_file(fid)
        if not src:
            raise ValueError(f"Year {key}: saved file not found.")
        if is_multi_year(src):
            raise ValueError(f"Year {key}: cannot nest multi-year packs.")
        sources.append(src)

    elig = _pack_eligibility(sources)
    if not elig["pages"]:
        raise ValueError(
            "Sources must share Role scores and/or Player stats eligibility."
        )

    index = _read_index()
    existing = None
    if pack_id:
        for entry in index:
            if entry.get("id") == pack_id:
                existing = entry
                break
        if not existing:
            raise FileNotFoundError("Multi-year pack not found.")
        if existing.get("kind") != KIND_MULTI_YEAR:
            raise ValueError("That id is not a multi-year pack.")

    file_id = pack_id or uuid.uuid4().hex[:12]
    entry = {
        "id": file_id,
        "kind": KIND_MULTI_YEAR,
        "original_name": name,
        "display_name": name,
        "user_note": note,
        "stored_name": "",
        "saved_at": (
            existing.get("saved_at")
            if existing
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "size_bytes": 0,
        "years": year_map,
        "weights": dict(DEFAULT_YEAR_WEIGHTS),
        "pages": elig["pages"],
        "role_scores": elig["role_scores"],
        "stats": elig["stats"],
        "squad_finance": False,
        "has_attributes": elig["has_attributes"],
        "has_stats": elig["has_stats"],
        "has_salary": False,
        "has_fees": False,
        "has_player_info": elig["has_player_info"],
        "eligibility_notes": elig["eligibility_notes"],
    }
    if existing:
        for i, item in enumerate(index):
            if item.get("id") == file_id:
                # Preserve cache meta until recompute overwrites it.
                if existing.get("cache"):
                    entry["cache"] = existing["cache"]
                if existing.get("limited_tracking_divisions") is not None:
                    entry["limited_tracking_divisions"] = existing[
                        "limited_tracking_divisions"
                    ]
                if existing.get("limited_tracking_by_nation") is not None:
                    entry["limited_tracking_by_nation"] = existing[
                        "limited_tracking_by_nation"
                    ]
                index[i] = entry
                break
    else:
        index.append(entry)
    _write_index(index)

    try:
        import services.upload_cache as upload_cache

        upload_cache.compute_file(file_id)
        entry = get_file(file_id) or entry
    except Exception as exc:
        entry = dict(entry)
        entry["cache"] = {
            "status": "error",
            "error": str(exc),
            "role_scores": False,
            "stats": False,
        }
        index = _read_index()
        for item in index:
            if item.get("id") == file_id:
                item["cache"] = entry["cache"]
                break
        _write_index(index)
    return entry


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
        "kind": KIND_SINGLE,
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
        "has_transfer_value": eligibility["has_transfer_value"],
        "has_fees": eligibility["has_fees"],
        "has_player_info": eligibility["has_player_info"],
        "eligibility_notes": eligibility["notes"],
    }
    index = _read_index()
    index.append(entry)
    _write_index(index)
    # Precompute role scores / stats percentiles for faster page loads.
    try:
        import services.upload_cache as upload_cache

        upload_cache.compute_file(file_id)
        # Refresh entry with cache metadata written by compute_file.
        entry = get_file(file_id) or entry
    except Exception as exc:
        entry = dict(entry)
        entry["cache"] = {
            "status": "error",
            "error": str(exc),
            "role_scores": False,
            "stats": False,
        }
        # Persist error status without failing the upload itself.
        index = _read_index()
        for item in index:
            if item.get("id") == file_id:
                item["cache"] = entry["cache"]
                break
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
    # Drop multi-year packs that referenced this source.
    if not is_multi_year(removed):
        still: list[dict[str, Any]] = []
        for entry in kept:
            if is_multi_year(entry) and file_id in configured_years(entry).values():
                try:
                    import services.upload_cache as upload_cache

                    upload_cache.delete_cache(str(entry.get("id") or ""))
                except Exception:
                    pass
                continue
            still.append(entry)
        kept = still
    stored = removed.get("stored_name") or ""
    if stored:
        path = UPLOADS_DIR / stored
        if path.is_file():
            path.unlink()
    try:
        import services.upload_cache as upload_cache

        upload_cache.delete_cache(file_id)
    except Exception:
        pass
    _write_index(kept)
    return True


def packs_referencing(file_id: str) -> list[dict[str, Any]]:
    """Multi-year packs that use ``file_id`` as a season source."""
    return [
        e
        for e in list_files()
        if is_multi_year(e) and file_id in configured_years(e).values()
    ]


def list_limited_tracking_divisions(
    *,
    file_id: str | None = None,
) -> list[str]:
    """Limited-stat leagues recorded on upload(s).

    When ``file_id`` is set, return that file's list. Otherwise union across the
    whole library (used by Profiles when snapshots span multiple exports).
    """
    if file_id:
        entry = get_file(file_id)
        if not entry:
            return []
        raw = entry.get("limited_tracking_divisions") or []
        if isinstance(raw, list):
            return sorted({str(x).strip() for x in raw if str(x).strip()})
        return []
    found: set[str] = set()
    for entry in list_files():
        raw = entry.get("limited_tracking_divisions") or []
        if not isinstance(raw, list):
            continue
        for name in raw:
            text = str(name).strip()
            if text and text not in ("-", "—"):
                found.add(text)
    return sorted(found)


def select_options(
    *,
    page: str | None = None,
    include_cache: bool = True,
) -> list[dict[str, str]]:
    """Dash Select / Mantine options for eligible files.

    When ``include_cache`` is True and ``page`` is ``role_scores`` or ``stats``,
    labels include Ready / Stale / Not computed from upload precompute status.
    Ready files are listed first.
    """
    entries = list_files(page=page)
    show_cache = bool(include_cache and page in {"role_scores", "stats"})
    sig_key = None
    status_by_id: dict[str, dict] = {}
    if show_cache:
        import services.upload_cache as upload_cache

        sig_key = upload_cache.signature_key()
        for entry in entries:
            status_by_id[str(entry.get("id") or "")] = upload_cache.cache_status_light(
                entry,
                page=page,
                sig_key=sig_key,
            )

    rank = {"ready": 0, "stale": 1, "missing": 2, "error": 3, "n/a": 4}

    def _status_rank(entry: dict) -> int:
        fid = str(entry.get("id") or "")
        st = (status_by_id.get(fid) or {}).get("status") or "n/a"
        return rank.get(st, 9)

    if show_cache:
        # Newest first within a status, then Ready → Stale → Not computed.
        entries = sorted(
            entries,
            key=lambda e: e.get("saved_at") or "",
            reverse=True,
        )
        entries = sorted(entries, key=_status_rank)

    opts = []
    for entry in entries:
        name = display_label(entry)
        when = (entry.get("saved_at") or "")[:10]
        note = (entry.get("user_note") or "").strip()
        label = f"{name}" + (f" · {when}" if when else "")
        if is_multi_year(entry):
            years = configured_years(entry)
            slots = "+".join(f"Y{k}" for k in YEAR_KEYS if k in years)
            label = f"{label} · Multi-year ({slots})"
        if note:
            short = note if len(note) <= 40 else note[:37] + "…"
            label = f"{label} — {short}"
        if show_cache:
            st = status_by_id.get(str(entry.get("id") or "")) or {}
            cache_label = st.get("label")
            if cache_label and cache_label != "—":
                label = f"{label} · {cache_label}"
        opts.append({"value": entry["id"], "label": label})
    return opts


def list_view_files() -> list[Path]:
    ensure_dirs()
    files = []
    for path in sorted(VIEWS_DIR.iterdir()):
        if path.is_file() and path.name not in (".gitkeep", "README.md"):
            files.append(path)
    return files


def views_zip_bytes() -> bytes | None:
    """Zip all custom view files for a single download."""
    files = list_view_files()
    if not files:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.name)
    return buf.getvalue()
