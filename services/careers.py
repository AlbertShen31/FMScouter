"""Career game containers: seasons with mid/end player snapshots.

Separate from formation profile libraries under ``data/profiles/``.
Each career lives under ``data/careers/packs/<id>/`` with ``meta.json``,
``seasons.json``, and optional ``seasons/<season_id>/{mid,end}.json.gz``.
``active.json`` points at the current career + season.
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
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


def _snapshot_path(career_id: str, season_id: str, slot: SlotName) -> Path:
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    return _season_dir(career_id, season_id) / f"{slot}.json.gz"


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


def _normalize_meta(raw: Any, *, career_id: str) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    name = str(payload.get("name") or career_id or "Career").strip() or "Career"
    return {
        "id": career_id,
        "name": name,
        "created_at": str(payload.get("created_at") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
        "show_hidden_attrs": bool(payload.get("show_hidden_attrs", False)),
        "managed_club_uid": payload.get("managed_club_uid"),
        "managed_club_name": (
            str(payload.get("managed_club_name") or "").strip() or None
        ),
        "notes": str(payload.get("notes") or "").strip(),
    }


def _normalize_snapshot_meta(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    return {
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


def write_snapshot(
    career_id: str,
    season_id: str,
    slot: SlotName,
    snapshot: dict[str, Any],
    *,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Write gzip snapshot and update season slot meta. Replaces if occupied."""
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    if not _meta_path(safe).is_file():
        raise ValueError(f"Unknown career: {career_id}")
    season = get_season(safe, sid)
    if season is None:
        raise ValueError(f"Unknown season: {season_id}")

    path = _snapshot_path(safe, sid, slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(snapshot)
    payload.setdefault("version", 1)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(path, "wb") as fh:
        fh.write(raw)

    snap_meta = _normalize_snapshot_meta(meta) or {
        "imported_at": _utcnow(),
        "source": "unknown",
        "source_name": "",
        "game_date": None,
        "player_count": int(payload.get("player_count") or len(payload.get("players") or [])),
        "managed_club_uid": None,
        "managed_club_name": None,
    }
    seasons = list_seasons(safe)
    for item in seasons:
        if item["id"] == sid:
            item["slots"][slot] = snap_meta
            break
    _write_seasons(safe, seasons)
    update_managed_club(
        safe,
        managed_club_uid=snap_meta.get("managed_club_uid"),
        managed_club_name=snap_meta.get("managed_club_name"),
    )
    return snap_meta


def load_snapshot(
    career_id: str,
    season_id: str,
    slot: SlotName,
) -> dict[str, Any] | None:
    path = _snapshot_path(career_id, season_id, slot)
    if not path.is_file():
        return None
    try:
        with gzip.open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except (OSError, EOFError, json.JSONDecodeError):
        return None


def delete_slot(career_id: str, season_id: str, slot: SlotName) -> bool:
    if slot not in SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    path = _snapshot_path(safe, sid, slot)
    existed = path.is_file()
    if existed:
        path.unlink()
    seasons = list_seasons(safe)
    changed = False
    for item in seasons:
        if item["id"] == sid:
            if item["slots"].get(slot) is not None:
                item["slots"][slot] = None
                changed = True
            break
    if changed:
        _write_seasons(safe, seasons)
    return existed or changed


def delete_season(career_id: str, season_id: str) -> bool:
    safe = _safe_id(career_id)
    sid = _safe_id(season_id)
    seasons = list_seasons(safe)
    kept = [s for s in seasons if s["id"] != sid]
    if len(kept) == len(seasons):
        return False
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
