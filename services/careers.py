"""Career game containers: seasons with mid/end player snapshots.

Separate from formation profile libraries under ``data/profiles/``.
Each career lives under ``data/careers/packs/<id>/`` with ``meta.json``,
``seasons.json``, stable ``snapshots/<file_id>.json.gz`` files, and optional
legacy ``seasons/<season_id>/{mid,end}.json.gz`` paths (migrated on touch).
Slot rows in ``seasons.json`` reference snapshots by ``file_id`` so schedule
remaps only rewrite labels/indexes. ``active.json`` points at the current
career + season.
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from config.paths import CAREERS_ACTIVE_PATH, CAREERS_DIR, CAREERS_PACKS_DIR

SlotName = Literal["mid", "end"]
SLOTS: tuple[SlotName, ...] = ("mid", "end")


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(name: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return text[:48] or "career"


def _safe_id(raw: str) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isalnum() or ch in "-_")


def _career_dir(career_id: str) -> Path:
    return CAREERS_PACKS_DIR / _safe_id(career_id)


def _meta_path(career_id: str) -> Path:
    return _career_dir(career_id) / "meta.json"


def _seasons_path(career_id: str) -> Path:
    return _career_dir(career_id) / "seasons.json"


def _season_dir(career_id: str, season_id: str) -> Path:
    return _career_dir(career_id) / "seasons" / _safe_id(season_id)


def _legacy_snapshot_path(career_id: str, season_id: str, slot: SlotName) -> Path:
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    return _season_dir(career_id, season_id) / f"{slot}.json.gz"


# Back-compat alias used by older call sites / tests.
_snapshot_path = _legacy_snapshot_path


def _snapshots_dir(career_id: str) -> Path:
    return _career_dir(career_id) / "snapshots"


def _stable_snapshot_path(career_id: str, file_id: str) -> Path:
    fid = _safe_id(file_id)
    if not fid:
        raise ValueError("file_id is required")
    return _snapshots_dir(career_id) / f"{fid}.json.gz"


def _new_file_id() -> str:
    return uuid.uuid4().hex


def _staging_dir(career_id: str) -> Path:
    return _career_dir(career_id) / "staging"


def _staging_index_path(career_id: str) -> Path:
    return _staging_dir(career_id) / "index.json"


def _staging_snapshot_path(career_id: str, staging_id: str) -> Path:
    return _staging_dir(career_id) / f"{_safe_id(staging_id)}.json.gz"


def _read_gzip_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with gzip.open(path, "rb") as fh:
            payload = json.loads(fh.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, EOFError, json.JSONDecodeError):
        return None


def _write_gzip_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(path, "wb") as fh:
        fh.write(raw)


def _unlink_snapshot_file(career_id: str, file_id: str | None) -> bool:
    fid = _safe_id(str(file_id or ""))
    if not fid:
        return False
    path = _stable_snapshot_path(career_id, fid)
    if path.is_file():
        path.unlink()
        return True
    return False


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _ensure_root() -> None:
    CAREERS_DIR.mkdir(parents=True, exist_ok=True)
    CAREERS_PACKS_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_season_schedule(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "summer_spring": "summer_spring",
        "summer_to_spring": "summer_spring",
        "summer": "summer_spring",
        "winter_fall": "winter_fall",
        "winter_to_fall": "winter_fall",
        "winter": "winter_fall",
    }
    return aliases.get(text, "summer_spring")


def _normalize_meta(raw: Any, *, career_id: str) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    name = str(payload.get("name") or career_id or "Career").strip() or "Career"
    return {
        "id": career_id,
        "name": name,
        "created_at": str(payload.get("created_at") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
        "show_hidden_attrs": bool(payload.get("show_hidden_attrs", False)),
        "season_schedule": _normalize_season_schedule(payload.get("season_schedule")),
        "managed_club_uid": payload.get("managed_club_uid"),
        "managed_club_name": (
            str(payload.get("managed_club_name") or "").strip() or None
        ),
        "notes": str(payload.get("notes") or "").strip(),
    }


def _normalize_snapshot_meta(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    file_id = _safe_id(str(raw.get("file_id") or "")) or None
    return {
        "file_id": file_id,
        "imported_at": str(raw.get("imported_at") or "").strip(),
        "source": str(raw.get("source") or "").strip() or "unknown",
        "source_name": str(raw.get("source_name") or "").strip(),
        "game_date": str(raw.get("game_date") or "").strip() or None,
        "player_count": int(raw.get("player_count") or 0),
        "managed_club_uid": raw.get("managed_club_uid"),
        "managed_club_name": (
            str(raw.get("managed_club_name") or "").strip() or None
        ),
    }


def _normalize_season(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    season_id = _safe_id(str(raw.get("id") or ""))
    if not season_id:
        return None
    slots_raw = raw.get("slots") if isinstance(raw.get("slots"), dict) else {}
    return {
        "id": season_id,
        "label": str(raw.get("label") or season_id).strip() or season_id,
        "year_start": int(raw.get("year_start") or 0),
        "year_end": int(raw.get("year_end") or 0),
        "slots": {
            "mid": _normalize_snapshot_meta(slots_raw.get("mid")),
            "end": _normalize_snapshot_meta(slots_raw.get("end")),
        },
    }


def _unique_career_id(name: str) -> str:
    base = _slugify(name)
    candidate = base
    index = 2
    while _career_dir(candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def list_career_ids() -> list[str]:
    _ensure_root()
    if not CAREERS_PACKS_DIR.is_dir():
        return []
    ids = [
        path.name
        for path in sorted(CAREERS_PACKS_DIR.iterdir())
        if path.is_dir() and (path / "meta.json").is_file()
    ]
    return ids


def list_careers() -> list[dict[str, Any]]:
    return [get_career(career_id) for career_id in list_career_ids()]


def get_career(career_id: str) -> dict[str, Any]:
    safe = _safe_id(career_id)
    meta = _normalize_meta(_read_json(_meta_path(safe), {}), career_id=safe)
    return meta


def get_active() -> dict[str, str | None]:
    raw = _read_json(CAREERS_ACTIVE_PATH, {})
    if not isinstance(raw, dict):
        return {"career_id": None, "season_id": None}
    career_id = _safe_id(str(raw.get("career_id") or "")) or None
    season_id = _safe_id(str(raw.get("season_id") or "")) or None
    if career_id and not _meta_path(career_id).is_file():
        return {"career_id": None, "season_id": None}
    return {"career_id": career_id, "season_id": season_id}


def set_active(*, career_id: str | None, season_id: str | None = None) -> dict[str, str | None]:
    _ensure_root()
    safe_career = _safe_id(career_id) if career_id else None
    safe_season = _safe_id(season_id) if season_id else None
    if safe_career and not _meta_path(safe_career).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    if safe_career and safe_season:
        seasons = {s["id"]: s for s in list_seasons(safe_career)}
        if safe_season not in seasons:
            raise ValueError(f"Unknown season: {season_id}")
    payload = {"career_id": safe_career, "season_id": safe_season}
    _write_json(CAREERS_ACTIVE_PATH, payload)
    return payload


def create_career(name: str, *, notes: str = "") -> dict[str, Any]:
    _ensure_root()
    cleaned = str(name or "").strip()
    if not cleaned:
        raise ValueError("Career name is required")
    career_id = _unique_career_id(cleaned)
    now = _utcnow()
    meta = {
        "id": career_id,
        "name": cleaned,
        "created_at": now,
        "updated_at": now,
        "show_hidden_attrs": False,
        "season_schedule": "summer_spring",
        "managed_club_uid": None,
        "managed_club_name": None,
        "notes": str(notes or "").strip(),
    }
    dest = _career_dir(career_id)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "seasons").mkdir(parents=True, exist_ok=True)
    _write_json(_meta_path(career_id), meta)
    _write_json(_seasons_path(career_id), {"seasons": []})
    active = get_active()
    if not active.get("career_id"):
        set_active(career_id=career_id, season_id=None)
    return meta


def rename_career(career_id: str, name: str) -> dict[str, Any]:
    safe = _safe_id(career_id)
    meta = get_career(safe)
    cleaned = str(name or "").strip()
    if not cleaned:
        raise ValueError("Career name is required")
    meta["name"] = cleaned
    meta["updated_at"] = _utcnow()
    _write_json(_meta_path(safe), meta)
    return meta


def set_show_hidden_attrs(career_id: str, enabled: bool) -> dict[str, Any]:
    safe = _safe_id(career_id)
    meta = get_career(safe)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    meta["show_hidden_attrs"] = bool(enabled)
    meta["updated_at"] = _utcnow()
    _write_json(_meta_path(safe), meta)
    return meta


def get_season_schedule(career_id: str) -> str:
    meta = get_career(career_id)
    return _normalize_season_schedule(meta.get("season_schedule"))


def set_season_schedule(career_id: str, schedule: str) -> dict[str, Any]:
    safe = _safe_id(career_id)
    meta = get_career(safe)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    meta["season_schedule"] = _normalize_season_schedule(schedule)
    meta["updated_at"] = _utcnow()
    _write_json(_meta_path(safe), meta)
    return meta


def update_managed_club(
    career_id: str,
    *,
    managed_club_uid: Any = None,
    managed_club_name: str | None = None,
) -> dict[str, Any]:
    safe = _safe_id(career_id)
    meta = get_career(safe)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    meta["managed_club_uid"] = managed_club_uid
    meta["managed_club_name"] = (
        str(managed_club_name or "").strip() or None
    )
    meta["updated_at"] = _utcnow()
    _write_json(_meta_path(safe), meta)
    return meta


def delete_career(career_id: str) -> bool:
    safe = _safe_id(career_id)
    dest = _career_dir(safe)
    if not dest.exists():
        return False
    # Read raw active before rmtree — get_active() clears a deleted id.
    raw_active = _read_json(CAREERS_ACTIVE_PATH, {})
    was_active = (
        isinstance(raw_active, dict)
        and _safe_id(str(raw_active.get("career_id") or "")) == safe
    )
    shutil.rmtree(dest)
    if was_active:
        remaining = list_career_ids()
        if remaining:
            set_active(career_id=remaining[0], season_id=None)
        else:
            set_active(career_id=None, season_id=None)
    return True


def list_seasons(career_id: str) -> list[dict[str, Any]]:
    safe = _safe_id(career_id)
    raw = _read_json(_seasons_path(safe), {"seasons": []})
    seasons_raw = raw.get("seasons") if isinstance(raw, dict) else []
    out: list[dict[str, Any]] = []
    if not isinstance(seasons_raw, list):
        return out
    for item in seasons_raw:
        season = _normalize_season(item)
        if season:
            out.append(season)
    out.sort(key=lambda s: (s.get("year_start") or 0, s.get("label") or ""))
    return out


def get_season(career_id: str, season_id: str) -> dict[str, Any] | None:
    safe_season = _safe_id(season_id)
    for season in list_seasons(career_id):
        if season["id"] == safe_season:
            return season
    return None


def _write_seasons(career_id: str, seasons: list[dict[str, Any]]) -> None:
    safe = _safe_id(career_id)
    _write_json(_seasons_path(safe), {"seasons": seasons})
    meta = get_career(safe)
    if _meta_path(safe).is_file():
        meta["updated_at"] = _utcnow()
        _write_json(_meta_path(safe), meta)


def upsert_season(
    career_id: str,
    *,
    season_id: str | None = None,
    label: str,
    year_start: int,
    year_end: int,
) -> dict[str, Any]:
    safe = _safe_id(career_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    seasons = list_seasons(safe)
    sid = _safe_id(season_id) if season_id else f"{int(year_start)}-{int(year_end)}"
    existing = next((s for s in seasons if s["id"] == sid), None)
    if existing is None:
        season = {
            "id": sid,
            "label": str(label or sid).strip() or sid,
            "year_start": int(year_start),
            "year_end": int(year_end),
            "slots": {"mid": None, "end": None},
        }
        seasons.append(season)
    else:
        existing["label"] = str(label or existing["label"]).strip() or existing["label"]
        existing["year_start"] = int(year_start)
        existing["year_end"] = int(year_end)
        season = existing
    _write_seasons(safe, seasons)
    return season


def rename_season(career_id: str, season_id: str, label: str) -> dict[str, Any]:
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    cleaned = str(label or "").strip()
    if not cleaned:
        raise ValueError("Season label is required")
    seasons = list_seasons(safe)
    found = None
    for season in seasons:
        if season["id"] == sid:
            season["label"] = cleaned
            found = season
            break
    if found is None:
        raise ValueError(f"Unknown season: {season_id}")
    _write_seasons(safe, seasons)
    return found


def slot_occupied(career_id: str, season_id: str, slot: SlotName) -> bool:
    season = get_season(career_id, season_id)
    if not season:
        return False
    return season["slots"].get(slot) is not None


def move_file(src: str | Path, dest: str | Path) -> Path:
    """Move a file into place, replacing any existing destination."""
    src_path = Path(src)
    dest_path = Path(dest)
    if not src_path.is_file():
        raise FileNotFoundError(f"Snapshot file missing: {src_path}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if src_path.resolve() == dest_path.resolve():
        return dest_path
    if dest_path.exists():
        dest_path.unlink()
    shutil.move(str(src_path), str(dest_path))
    return dest_path


def career_root(career_id: str) -> Path:
    return _career_dir(career_id)


def _set_slot_meta(
    career_id: str,
    season_id: str,
    slot: SlotName,
    meta: dict[str, Any],
) -> dict[str, Any]:
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    snap_meta = _normalize_snapshot_meta(meta) or {
        "file_id": None,
        "imported_at": _utcnow(),
        "source": "unknown",
        "source_name": "",
        "game_date": None,
        "player_count": 0,
        "managed_club_uid": None,
        "managed_club_name": None,
    }
    seasons = list_seasons(safe)
    found = False
    for item in seasons:
        if item["id"] == sid:
            item["slots"][slot] = snap_meta
            found = True
            break
    if not found:
        raise ValueError(f"Unknown season: {season_id}")
    _write_seasons(safe, seasons)
    update_managed_club(
        safe,
        managed_club_uid=snap_meta.get("managed_club_uid"),
        managed_club_name=snap_meta.get("managed_club_name"),
    )
    return snap_meta


def ensure_slot_file_id(
    career_id: str,
    season_id: str,
    slot: SlotName,
    meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Ensure slot meta has a stable file_id; migrate legacy path once if needed."""
    if not meta:
        return None
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    out = dict(meta)
    fid = _safe_id(str(out.get("file_id") or ""))
    stable = _stable_snapshot_path(safe, fid) if fid else None
    if fid and stable is not None and stable.is_file():
        out["file_id"] = fid
        return _normalize_snapshot_meta(out)

    legacy = _legacy_snapshot_path(safe, sid, slot)
    if not fid:
        fid = _new_file_id()
    dest = _stable_snapshot_path(safe, fid)
    if legacy.is_file():
        if not dest.is_file() or legacy.resolve() != dest.resolve():
            move_file(legacy, dest)
    elif not dest.is_file():
        return None
    out["file_id"] = fid
    return _normalize_snapshot_meta(out)


def resolve_slot_snapshot_path(
    career_id: str,
    season_id: str,
    slot: SlotName,
    meta: dict[str, Any] | None = None,
) -> Path | None:
    """Return the on-disk path for a season slot snapshot, if present."""
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    safe = _safe_id(career_id)
    slot_meta = meta
    if slot_meta is None:
        season = get_season(safe, season_id)
        slot_meta = (season or {}).get("slots", {}).get(slot) if season else None
    fid = _safe_id(str((slot_meta or {}).get("file_id") or ""))
    if fid:
        path = _stable_snapshot_path(safe, fid)
        if path.is_file():
            return path
    legacy = _legacy_snapshot_path(safe, season_id, slot)
    if legacy.is_file():
        return legacy
    return None


def place_snapshot_file(
    career_id: str,
    season_id: str,
    slot: SlotName,
    source_path: str | Path,
    *,
    meta: dict[str, Any],
    file_id: str | None = None,
) -> dict[str, Any]:
    """Move an existing gzip into the stable snapshot store and index the slot."""
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    season = get_season(safe, sid)
    if season is None:
        raise ValueError(f"Unknown season: {season_id}")

    src = Path(source_path)
    existing = (season.get("slots") or {}).get(slot) or {}
    old_fid = _safe_id(str(existing.get("file_id") or "")) or None

    fid = _safe_id(str(file_id or (meta or {}).get("file_id") or "")) or None
    if not fid and src.parent.resolve() == _snapshots_dir(safe).resolve():
        fid = _safe_id(src.stem) or None
    if not fid:
        fid = old_fid or _new_file_id()

    dest = _stable_snapshot_path(safe, fid)
    move_file(src, dest)
    if old_fid and old_fid != fid:
        _unlink_snapshot_file(safe, old_fid)

    snap_meta = dict(meta or {})
    snap_meta["file_id"] = fid
    return _set_slot_meta(safe, sid, slot, snap_meta)


def snapshot_file_path(career_id: str, season_id: str, slot: SlotName) -> Path:
    """Resolved path for a slot snapshot (stable file_id preferred)."""
    path = resolve_slot_snapshot_path(career_id, season_id, slot)
    if path is not None:
        return path
    # Fall back to stable destination for callers that need a path object.
    season = get_season(career_id, season_id)
    meta = (season or {}).get("slots", {}).get(slot) if season else None
    fid = _safe_id(str((meta or {}).get("file_id") or "")) or _new_file_id()
    return _stable_snapshot_path(career_id, fid)


def replace_seasons(career_id: str, seasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite seasons.json in one shot (snapshot files are left untouched)."""
    safe = _safe_id(career_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    normalized: list[dict[str, Any]] = []
    for raw in seasons:
        season = _normalize_season(raw)
        if season:
            normalized.append(season)
    normalized.sort(key=lambda s: (s.get("year_start") or 0, s.get("label") or ""))
    _write_seasons(safe, normalized)
    return normalized


def reset_season_slots(career_id: str) -> None:
    """Clear seasons.json indexes (snapshot files kept; legacy season dirs removed)."""
    safe = _safe_id(career_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    seasons_root = _career_dir(safe) / "seasons"
    if seasons_root.exists():
        shutil.rmtree(seasons_root)
    seasons_root.mkdir(parents=True, exist_ok=True)
    _write_seasons(safe, [])
    active = get_active()
    if active.get("career_id") == safe:
        set_active(career_id=safe, season_id=None)


def write_snapshot(
    career_id: str,
    season_id: str,
    slot: SlotName,
    snapshot: dict[str, Any],
    *,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Write gzip snapshot into stable store and update season slot meta."""
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    season = get_season(safe, sid)
    if season is None:
        raise ValueError(f"Unknown season: {season_id}")

    existing = (season.get("slots") or {}).get(slot) or {}
    file_id = (
        _safe_id(str((meta or {}).get("file_id") or existing.get("file_id") or ""))
        or _new_file_id()
    )
    path = _stable_snapshot_path(safe, file_id)
    payload = dict(snapshot)
    payload.setdefault("version", 1)
    _write_gzip_json(path, payload)

    # Clean legacy path if present so schedule remaps don't see stale files.
    legacy = _legacy_snapshot_path(safe, sid, slot)
    if legacy.is_file() and legacy.resolve() != path.resolve():
        legacy.unlink()

    snap_meta = {
        "file_id": file_id,
        "imported_at": (meta or {}).get("imported_at") or _utcnow(),
        "source": (meta or {}).get("source") or "unknown",
        "source_name": (meta or {}).get("source_name") or "",
        "game_date": (meta or {}).get("game_date"),
        "player_count": int(
            (meta or {}).get("player_count")
            or payload.get("player_count")
            or len(payload.get("players") or [])
        ),
        "managed_club_uid": (meta or {}).get("managed_club_uid"),
        "managed_club_name": (meta or {}).get("managed_club_name"),
    }
    return _set_slot_meta(safe, sid, slot, snap_meta)


def load_snapshot(
    career_id: str,
    season_id: str,
    slot: SlotName,
) -> dict[str, Any] | None:
    path = resolve_slot_snapshot_path(career_id, season_id, slot)
    return _read_gzip_json(path) if path is not None else None


def delete_slot(career_id: str, season_id: str, slot: SlotName) -> bool:
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    seasons = list_seasons(safe)
    changed = False
    existed = False
    for item in seasons:
        if item["id"] != sid:
            continue
        current = item["slots"].get(slot)
        if current is not None:
            existed = _unlink_snapshot_file(safe, current.get("file_id")) or existed
            item["slots"][slot] = None
            changed = True
        break
    legacy = _legacy_snapshot_path(safe, sid, slot)
    if legacy.is_file():
        legacy.unlink()
        existed = True
    if changed:
        _write_seasons(safe, seasons)
    return existed or changed


def delete_season(career_id: str, season_id: str) -> bool:
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    seasons = list_seasons(safe)
    target = next((s for s in seasons if s["id"] == sid), None)
    kept = [s for s in seasons if s["id"] != sid]
    if len(kept) == len(seasons):
        return False
    if target:
        for slot in SLOTS:
            meta = (target.get("slots") or {}).get(slot)
            if meta:
                _unlink_snapshot_file(safe, meta.get("file_id"))
    _write_seasons(safe, kept)
    season_path = _season_dir(safe, sid)
    if season_path.exists():
        shutil.rmtree(season_path)
    active = get_active()
    if active.get("career_id") == safe and active.get("season_id") == sid:
        next_id = kept[-1]["id"] if kept else None
        set_active(career_id=safe, season_id=next_id)
    return True


def career_options() -> list[dict[str, str]]:
    return [
        {"label": career["name"], "value": career["id"]}
        for career in list_careers()
    ]


def season_options(career_id: str) -> list[dict[str, str]]:
    return [
        {"label": season["label"], "value": season["id"]}
        for season in list_seasons(career_id)
    ]


def _normalize_staging_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    staging_id = _safe_id(str(raw.get("id") or ""))
    if not staging_id:
        return None
    suggested = str(raw.get("suggested_slot") or "end").strip().lower()
    if suggested not in SLOTS:
        suggested = "end"
    return {
        "id": staging_id,
        "file_id": _safe_id(str(raw.get("file_id") or "")) or None,
        "source": str(raw.get("source") or "").strip() or "unknown",
        "source_name": str(raw.get("source_name") or "").strip(),
        "game_date": str(raw.get("game_date") or "").strip() or None,
        "season_id": _safe_id(str(raw.get("season_id") or "")) or None,
        "season_label": str(raw.get("season_label") or "").strip() or None,
        "year_start": int(raw.get("year_start") or 0) or None,
        "year_end": int(raw.get("year_end") or 0) or None,
        "suggested_slot": suggested,
        "player_count": int(raw.get("player_count") or 0),
        "managed_club_uid": raw.get("managed_club_uid"),
        "managed_club_name": (
            str(raw.get("managed_club_name") or "").strip() or None
        ),
        "staged_at": str(raw.get("staged_at") or "").strip() or None,
    }


def _staging_payload_path(career_id: str, item: dict[str, Any]) -> Path | None:
    fid = _safe_id(str(item.get("file_id") or ""))
    if fid:
        path = _stable_snapshot_path(career_id, fid)
        if path.is_file():
            return path
    legacy = _staging_snapshot_path(career_id, item.get("id") or "")
    if legacy.is_file():
        return legacy
    return None


def list_staging(career_id: str) -> list[dict[str, Any]]:
    safe = _safe_id(career_id)
    out: list[dict[str, Any]] = []
    for item in _read_staging_index(safe):
        if _staging_payload_path(safe, item) is None:
            continue
        out.append(item)
    out.sort(key=lambda item: (item.get("staged_at") or "", item.get("id") or ""))
    return out


def get_staging_item(career_id: str, staging_id: str) -> dict[str, Any] | None:
    safe_id = _safe_id(staging_id)
    for item in list_staging(career_id):
        if item["id"] == safe_id:
            return item
    return None


def update_staging_classification(
    career_id: str,
    staging_id: str,
    *,
    season_id: str | None = None,
    season_label: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    suggested_slot: SlotName | str | None = None,
) -> dict[str, Any] | None:
    """Update season/slot suggestion fields on a staged item (snapshot unchanged)."""
    safe = _safe_id(career_id)
    sid = _safe_id(staging_id)
    items = _read_staging_index(safe)
    found = None
    for item in items:
        if item["id"] != sid:
            continue
        if season_id is not None:
            item["season_id"] = _safe_id(str(season_id)) or None
        if season_label is not None:
            item["season_label"] = str(season_label).strip() or None
        if year_start is not None:
            item["year_start"] = int(year_start) or None
        if year_end is not None:
            item["year_end"] = int(year_end) or None
        if suggested_slot is not None:
            slot = str(suggested_slot).strip().lower()
            item["suggested_slot"] = slot if slot in SLOTS else "end"
        found = item
        break
    if found is None:
        return None
    _write_json(_staging_index_path(safe), {"items": items})
    return found


def add_staging_item(
    career_id: str,
    *,
    players: list[dict[str, Any]],
    meta: dict[str, Any],
    season_id: str | None = None,
    season_label: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    suggested_slot: SlotName = "end",
) -> dict[str, Any]:
    """Persist an extracted snapshot into career staging (not a season slot yet)."""
    safe = _safe_id(career_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    if suggested_slot not in SLOTS:
        raise ValueError(f"Invalid slot: {suggested_slot}")

    staging_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    file_id = _new_file_id()
    snapshot = {
        "version": 1,
        "game_date": meta.get("game_date"),
        "source": meta.get("source"),
        "source_name": meta.get("source_name"),
        "managed_club_uid": meta.get("managed_club_uid"),
        "managed_club_name": meta.get("managed_club_name"),
        "player_count": len(players),
        "players": players,
    }
    path = _stable_snapshot_path(safe, file_id)
    _write_gzip_json(path, snapshot)

    item = _normalize_staging_item(
        {
            "id": staging_id,
            "file_id": file_id,
            "source": meta.get("source"),
            "source_name": meta.get("source_name"),
            "game_date": meta.get("game_date"),
            "season_id": season_id,
            "season_label": season_label,
            "year_start": year_start,
            "year_end": year_end,
            "suggested_slot": suggested_slot,
            "player_count": len(players),
            "managed_club_uid": meta.get("managed_club_uid"),
            "managed_club_name": meta.get("managed_club_name"),
            "staged_at": _utcnow(),
        }
    )
    if item is None:
        path.unlink(missing_ok=True)
        raise ValueError("Failed to create staging item")

    items = _read_staging_index(safe)
    items.append(item)
    _write_json(_staging_index_path(safe), {"items": items})
    return item


def load_staging_snapshot(career_id: str, staging_id: str) -> dict[str, Any] | None:
    item = get_staging_item(career_id, staging_id)
    if item is None:
        # Fall back to legacy path when index entry is missing.
        return _read_gzip_json(_staging_snapshot_path(career_id, staging_id))
    path = _staging_payload_path(career_id, item)
    return _read_gzip_json(path) if path is not None else None


def staging_snapshot_path(career_id: str, staging_id: str) -> Path:
    item = get_staging_item(career_id, staging_id)
    if item is not None:
        path = _staging_payload_path(career_id, item)
        if path is not None:
            return path
    return _staging_snapshot_path(career_id, staging_id)


def _read_staging_index(career_id: str) -> list[dict[str, Any]]:
    """Raw staging index entries (does not require snapshot files to exist)."""
    safe = _safe_id(career_id)
    raw = _read_json(_staging_index_path(safe), {"items": []})
    items_raw = raw.get("items") if isinstance(raw, dict) else []
    out: list[dict[str, Any]] = []
    if not isinstance(items_raw, list):
        return out
    for item in items_raw:
        normalized = _normalize_staging_item(item)
        if normalized:
            out.append(normalized)
    return out


def _pop_staging_index(
    career_id: str, staging_id: str
) -> dict[str, Any] | None:
    """Remove a staging index entry without deleting its snapshot file."""
    safe = _safe_id(career_id)
    sid = _safe_id(staging_id)
    items = _read_staging_index(safe)
    kept: list[dict[str, Any]] = []
    found: dict[str, Any] | None = None
    for item in items:
        if item["id"] == sid:
            found = item
            continue
        kept.append(item)
    if found is None:
        return None
    _write_json(_staging_index_path(safe), {"items": kept})
    return found


def place_staging_into_slot(
    career_id: str,
    staging_id: str,
    *,
    season_id: str,
    slot: SlotName,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Point a season slot at a staged snapshot file_id (index-only when possible)."""
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    safe = _safe_id(career_id)
    item = get_staging_item(safe, staging_id)
    if item is None:
        raise ValueError(f"Unknown staging item: {staging_id}")
    sid = _safe_id(season_id)
    season = get_season(safe, sid)
    if season is None:
        raise ValueError(f"Unknown season: {season_id}")

    file_id = _safe_id(str(item.get("file_id") or "")) or None
    src = _staging_payload_path(safe, item)
    if src is None:
        raise ValueError(f"Staging snapshot missing: {staging_id}")
    if not file_id:
        # Legacy staging/<id>.json.gz → stable snapshots/<file_id>.json.gz once.
        file_id = _new_file_id()
        move_file(src, _stable_snapshot_path(safe, file_id))

    existing = (season.get("slots") or {}).get(slot) or {}
    old_fid = _safe_id(str(existing.get("file_id") or "")) or None
    if old_fid and old_fid != file_id:
        _unlink_snapshot_file(safe, old_fid)

    snap_meta = dict(
        meta
        or {
            "imported_at": item.get("staged_at") or _utcnow(),
            "source": item.get("source"),
            "source_name": item.get("source_name"),
            "game_date": item.get("game_date"),
            "player_count": item.get("player_count") or 0,
            "managed_club_uid": item.get("managed_club_uid"),
            "managed_club_name": item.get("managed_club_name"),
        }
    )
    snap_meta["file_id"] = file_id
    written = _set_slot_meta(safe, sid, slot, snap_meta)
    _pop_staging_index(safe, item["id"])
    return written


def add_staging_ref(
    career_id: str,
    *,
    file_id: str,
    source: str | None = None,
    source_name: str | None = None,
    game_date: str | None = None,
    season_id: str | None = None,
    season_label: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    suggested_slot: SlotName = "end",
    player_count: int = 0,
    managed_club_uid: Any = None,
    managed_club_name: str | None = None,
) -> dict[str, Any]:
    """Register an existing stable snapshot file_id in staging (no file move)."""
    safe = _safe_id(career_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    if suggested_slot not in SLOTS:
        raise ValueError(f"Invalid slot: {suggested_slot}")
    fid = _safe_id(str(file_id or ""))
    if not fid:
        raise ValueError("file_id is required")
    if not _stable_snapshot_path(safe, fid).is_file():
        raise FileNotFoundError(f"Snapshot file missing: {fid}")

    staging_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    item = _normalize_staging_item(
        {
            "id": staging_id,
            "file_id": fid,
            "source": source,
            "source_name": source_name,
            "game_date": game_date,
            "season_id": season_id,
            "season_label": season_label,
            "year_start": year_start,
            "year_end": year_end,
            "suggested_slot": suggested_slot,
            "player_count": player_count,
            "managed_club_uid": managed_club_uid,
            "managed_club_name": managed_club_name,
            "staged_at": _utcnow(),
        }
    )
    if item is None:
        raise ValueError("Failed to create staging item")

    items = _read_staging_index(safe)
    items.append(item)
    _write_json(_staging_index_path(safe), {"items": items})
    return item


def add_staging_from_file(
    career_id: str,
    source_path: str | Path,
    *,
    source: str | None = None,
    source_name: str | None = None,
    game_date: str | None = None,
    season_id: str | None = None,
    season_label: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    suggested_slot: SlotName = "end",
    player_count: int = 0,
    managed_club_uid: Any = None,
    managed_club_name: str | None = None,
    file_id: str | None = None,
) -> dict[str, Any]:
    """Adopt an existing gzip into the stable store and register staging index."""
    safe = _safe_id(career_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    if suggested_slot not in SLOTS:
        raise ValueError(f"Invalid slot: {suggested_slot}")
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"Snapshot file missing: {src}")

    fid = _safe_id(str(file_id or "")) or None
    if not fid and src.parent.resolve() == _snapshots_dir(safe).resolve():
        fid = _safe_id(src.stem) or None
    if not fid:
        fid = _new_file_id()
    dest = _stable_snapshot_path(safe, fid)
    if src.resolve() != dest.resolve():
        move_file(src, dest)

    return add_staging_ref(
        safe,
        file_id=fid,
        source=source,
        source_name=source_name,
        game_date=game_date,
        season_id=season_id,
        season_label=season_label,
        year_start=year_start,
        year_end=year_end,
        suggested_slot=suggested_slot,
        player_count=player_count,
        managed_club_uid=managed_club_uid,
        managed_club_name=managed_club_name,
    )


def delete_staging_item(career_id: str, staging_id: str) -> bool:
    safe = _safe_id(career_id)
    sid = _safe_id(staging_id)
    popped = _pop_staging_index(safe, sid)
    existed = False
    if popped is not None:
        fid = popped.get("file_id")
        if fid:
            existed = _unlink_snapshot_file(safe, fid) or existed
    legacy = _staging_snapshot_path(safe, sid)
    if legacy.is_file():
        legacy.unlink()
        existed = True
    return popped is not None or existed


def clear_staging(career_id: str) -> int:
    safe = _safe_id(career_id)
    items = _read_staging_index(safe)
    for item in items:
        fid = item.get("file_id")
        if fid:
            _unlink_snapshot_file(safe, fid)
        legacy = _staging_snapshot_path(safe, item["id"])
        if legacy.is_file():
            legacy.unlink()
    index_path = _staging_index_path(safe)
    if index_path.is_file() or items:
        _write_json(index_path, {"items": []})
    return len(items)
