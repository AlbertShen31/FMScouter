"""Saved player profiles: named libraries of shortlist-style row snapshots.

Each library lives under ``data/profiles/packs/<id>/`` with ``meta.json``,
``index.json``, and ``slot_depth.json``. ``active.json`` points at the current
library. Legacy flat ``index.json`` / ``slot_depth.json`` are migrated once into
a Default library.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import (
    PROFILES_ACTIVE_PATH,
    PROFILES_DIR,
    PROFILES_INDEX_PATH,
    PROFILES_PACKS_DIR,
)
import services.export_library as lib
from scoring.role_scorer import player_row_key
from scoring.stats_scorer import player_key as stats_player_key

SAVED_FROM_LABELS = {
    "role_scores": "Role scores",
    "stats": "Player stats",
}

# Legacy flat path (pre multi-library); kept for migration only.
_LEGACY_SLOT_DEPTH_PATH = PROFILES_DIR / "slot_depth.json"

# Identity fields copied from a scored role shortlist row into the snapshot.
ROLE_IDENTITY_KEYS = (
    "Name",
    "Age",
    "Club",
    "Division",
    "Nation",
    "Position",
    "Best Pos",
    "Style",
    "Height",
    "Left Foot",
    "Right Foot",
    "Rec",
    "Inf",
    "Injury",
    "Squad",
)


def _slugify(name: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return text[:48] or "profile"


def _unique_library_id(name: str) -> str:
    base = _slugify(name)
    candidate = base
    index = 2
    while _library_dir(candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _library_dir(library_id: str) -> Path:
    safe = "".join(ch for ch in str(library_id or "") if ch.isalnum() or ch in "-_")
    return PROFILES_PACKS_DIR / safe


def _meta_path(library_id: str) -> Path:
    return _library_dir(library_id) / "meta.json"


def _index_path(library_id: str | None = None) -> Path:
    return _library_dir(_resolve_library_id(library_id)) / "index.json"


def _slot_depth_path(library_id: str | None = None) -> Path:
    return _library_dir(_resolve_library_id(library_id)) / "slot_depth.json"


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


def _normalize_meta(raw: Any, *, library_id: str) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    name = str(payload.get("name") or library_id or "Profile").strip() or "Profile"
    return {
        "id": library_id,
        "name": name,
        "formation_id": str(payload.get("formation_id") or "").strip(),
        "created_at": str(payload.get("created_at") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
    }


def _migrate_legacy_if_needed() -> None:
    """Move root index/slot_depth into packs/default once."""
    legacy_index = PROFILES_INDEX_PATH
    legacy_depth = _LEGACY_SLOT_DEPTH_PATH
    if not legacy_index.is_file() and not legacy_depth.is_file():
        return
    dest = _library_dir("default")
    if dest.exists() and (dest / "index.json").is_file():
        # Already have a default pack — archive leftovers if present.
        for path in (legacy_index, legacy_depth):
            if path.is_file():
                path.unlink()
        return
    dest.mkdir(parents=True, exist_ok=True)
    formation_id = ""
    if legacy_depth.is_file():
        depth = _read_json(legacy_depth, {})
        if isinstance(depth, dict) and depth:
            formation_id = str(next(iter(depth.keys())) or "").strip()
        target = dest / "slot_depth.json"
        if not target.exists():
            shutil.move(str(legacy_depth), str(target))
        elif legacy_depth.is_file():
            legacy_depth.unlink()
    else:
        _write_json(dest / "slot_depth.json", {})
    if legacy_index.is_file():
        target = dest / "index.json"
        if not target.exists():
            shutil.move(str(legacy_index), str(target))
        elif legacy_index.is_file():
            legacy_index.unlink()
    else:
        _write_json(dest / "index.json", [])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not formation_id:
        try:
            import services.formations as fm

            formation_id = fm.active_id() or ""
        except Exception:
            formation_id = ""
    _write_json(
        dest / "meta.json",
        {
            "id": "default",
            "name": "Default",
            "formation_id": formation_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    if not PROFILES_ACTIVE_PATH.is_file():
        _write_json(PROFILES_ACTIVE_PATH, {"id": "default"})


def ensure_dirs() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_PACKS_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_if_needed()
    ids = list_library_ids()
    if not ids:
        _bootstrap_default_library()
        ids = list_library_ids()
    active = str(_read_json(PROFILES_ACTIVE_PATH, {}).get("id") or "").strip()
    if ids and (not active or not _library_dir(active).is_dir()):
        _write_json(PROFILES_ACTIVE_PATH, {"id": ids[0]})


def _bootstrap_default_library() -> None:
    """Create an empty Default library without going through create_library."""
    dest = _library_dir("default")
    if dest.exists():
        return
    formation_id = ""
    try:
        import services.formations as fm

        formation_id = fm.active_id() or ""
    except Exception:
        formation_id = ""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dest.mkdir(parents=True, exist_ok=True)
    _write_json(
        dest / "meta.json",
        {
            "id": "default",
            "name": "Default",
            "formation_id": formation_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    _write_json(dest / "index.json", [])
    _write_json(dest / "slot_depth.json", {})
    _write_json(PROFILES_ACTIVE_PATH, {"id": "default"})


def list_library_ids() -> list[str]:
    if not PROFILES_PACKS_DIR.is_dir():
        return []
    return sorted(
        path.name
        for path in PROFILES_PACKS_DIR.iterdir()
        if path.is_dir() and (path / "meta.json").is_file()
    )


def _formation_display_name(formation_id: str) -> str:
    """Resolve a formation pack id to its stored display name."""
    fid = str(formation_id or "").strip()
    if not fid:
        return ""
    try:
        import services.formations as fm

        if not fm.exists(fid):
            return fid
        formation = fm.load(fid, persist=False)
        name = str((formation or {}).get("name") or "").strip()
        return name or fid
    except Exception:
        return fid


def library_options() -> list[dict[str, str]]:
    options = []
    for library_id in list_library_ids():
        meta = get_library(library_id)
        if not meta:
            continue
        formation_id = str(meta.get("formation_id") or "").strip()
        formation_label = _formation_display_name(formation_id) if formation_id else ""
        suffix = f" · {formation_label}" if formation_label else ""
        options.append(
            {
                "label": f"{meta.get('name') or library_id}{suffix}",
                "value": library_id,
            }
        )
    return options


def active_library_id() -> str:
    ensure_dirs()
    raw = _read_json(PROFILES_ACTIVE_PATH, {})
    library_id = str((raw or {}).get("id") or "").strip()
    if library_id and _library_dir(library_id).is_dir():
        return library_id
    ids = list_library_ids()
    return ids[0] if ids else ""


def set_active_library(library_id: str) -> str:
    ensure_dirs()
    lid = str(library_id or "").strip()
    if not lid or not _library_dir(lid).is_dir():
        raise ValueError("Profile library not found.")
    _write_json(PROFILES_ACTIVE_PATH, {"id": lid})
    return lid


def _resolve_library_id(library_id: str | None = None) -> str:
    lid = str(library_id or "").strip()
    if lid:
        if not _library_dir(lid).is_dir():
            raise ValueError(f"Profile library not found: {lid}")
        return lid
    active = active_library_id()
    if not active:
        raise ValueError("No profile library is active.")
    return active


def get_library(library_id: str | None = None) -> dict[str, Any] | None:
    ensure_dirs()
    try:
        lid = _resolve_library_id(library_id)
    except ValueError:
        return None
    path = _meta_path(lid)
    if not path.is_file():
        return None
    return _normalize_meta(_read_json(path, {}), library_id=lid)


def create_library(
    name: str,
    formation_id: str,
    *,
    library_id: str | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Create an empty profile library. Formation is required."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_PACKS_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_if_needed()
    label = str(name or "").strip()
    if not label:
        raise ValueError("Enter a profile name.")
    fid = str(formation_id or "").strip()
    if not fid:
        raise ValueError("Select a formation to create a profile.")
    try:
        import services.formations as fm

        if not fm.exists(fid):
            raise ValueError("Select a valid formation.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not validate formation: {exc}") from exc
    lid = str(library_id or "").strip() or _unique_library_id(label)
    dest = _library_dir(lid)
    if dest.exists():
        raise ValueError(f"A profile named “{lid}” already exists.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {
        "id": lid,
        "name": label,
        "formation_id": fid,
        "created_at": now,
        "updated_at": now,
    }
    dest.mkdir(parents=True, exist_ok=True)
    _write_json(dest / "meta.json", meta)
    _write_json(dest / "index.json", [])
    _write_json(dest / "slot_depth.json", {})
    if activate or not PROFILES_ACTIVE_PATH.is_file():
        set_active_library(lid)
    return _normalize_meta(meta, library_id=lid)


def update_library_formation(library_id: str | None, formation_id: str) -> dict[str, Any]:
    meta = get_library(library_id)
    if not meta:
        raise ValueError("Profile library not found.")
    fid = str(formation_id or "").strip()
    meta["formation_id"] = fid
    meta["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_json(_meta_path(meta["id"]), meta)
    return meta


def delete_library(library_id: str) -> bool:
    ensure_dirs()
    lid = str(library_id or "").strip()
    dest = _library_dir(lid)
    if not dest.is_dir():
        return False
    ids = list_library_ids()
    if len(ids) <= 1:
        raise ValueError("Cannot delete the only profile library.")
    shutil.rmtree(dest)
    if active_library_id() == lid:
        remaining = list_library_ids()
        if remaining:
            set_active_library(remaining[0])
    return True


def _read_slot_depth(library_id: str | None = None) -> dict[str, Any]:
    ensure_dirs()
    data = _read_json(_slot_depth_path(library_id), {})
    return data if isinstance(data, dict) else {}


def _write_slot_depth(payload: dict[str, Any], library_id: str | None = None) -> None:
    ensure_dirs()
    _write_json(_slot_depth_path(library_id), payload)


def _slot_key(slot_index: int | str) -> str:
    try:
        return str(int(slot_index))
    except (TypeError, ValueError):
        return str(slot_index or "").strip()


def get_slot_order_ids(
    formation_id: str | None,
    slot_index: int | str,
    role_column: str,
    *,
    seed: bool = True,
) -> list[str]:
    """Return ordered profile ids for one formation slot (seed from role depth)."""
    pack = str(formation_id or "").strip()
    role = str(role_column or "").strip()
    key = _slot_key(slot_index)
    if not pack or not role or key == "":
        return [
            str(entry.get("id") or "")
            for entry in ordered_profiles_for_role(role)
            if str(entry.get("id") or "")
        ]
    store = _read_slot_depth()
    pack_map = store.get(pack) if isinstance(store.get(pack), dict) else {}
    raw = pack_map.get(key)
    if isinstance(raw, list):
        valid = {str(entry.get("id") or "") for entry in list_role_profiles()}
        return [str(pid).strip() for pid in raw if str(pid or "").strip() in valid]
    if not seed:
        return []
    seeded = [
        str(entry.get("id") or "")
        for entry in ordered_profiles_for_role(role)
        if str(entry.get("id") or "")
    ]
    pack_map = dict(pack_map)
    pack_map[key] = seeded
    store[pack] = pack_map
    _write_slot_depth(store)
    return list(seeded)


def set_slot_order_ids(
    formation_id: str | None,
    slot_index: int | str,
    ordered_profile_ids: list[str],
) -> None:
    pack = str(formation_id or "").strip()
    key = _slot_key(slot_index)
    if not pack or key == "":
        return
    store = _read_slot_depth()
    pack_map = dict(store.get(pack) or {}) if isinstance(store.get(pack), dict) else {}
    pack_map[key] = [
        str(pid).strip() for pid in ordered_profile_ids if str(pid or "").strip()
    ]
    store[pack] = pack_map
    _write_slot_depth(store)


def ordered_profiles_for_slot(
    formation_id: str | None,
    slot_index: int | str,
    role_column: str,
) -> list[dict[str, Any]]:
    """Profiles for one formation slot in that slot’s depth order."""
    role = str(role_column or "").strip()
    ids = get_slot_order_ids(formation_id, slot_index, role, seed=True)
    by_id = {
        str(entry.get("id") or ""): entry
        for entry in list_role_profiles()
        if _entry_role(entry) == role
    }
    return [by_id[pid] for pid in ids if pid in by_id]


def profile_used_in_formation_slots(
    formation_id: str | None,
    profile_id: str,
    *,
    except_slot: int | str | None = None,
) -> bool:
    pack = str(formation_id or "").strip()
    pid = str(profile_id or "").strip()
    if not pack or not pid:
        return False
    store = _read_slot_depth()
    pack_map = store.get(pack) if isinstance(store.get(pack), dict) else {}
    skip = _slot_key(except_slot) if except_slot is not None else None
    for key, ids in pack_map.items():
        if skip is not None and str(key) == skip:
            continue
        if not isinstance(ids, list):
            continue
        if pid in {str(item).strip() for item in ids}:
            return True
    return False


def remove_from_slot_depth(
    formation_id: str | None,
    slot_index: int | str,
    profile_id: str,
    role_column: str,
) -> dict[str, Any] | None:
    """Remove a player from one slot’s depth only.

    Deletes the shortlist row only when no other slot in this formation still
    references the same profile id.
    """
    pack = str(formation_id or "").strip()
    role = str(role_column or "").strip()
    pid = str(profile_id or "").strip()
    if not pack or not role or not pid:
        return None
    entry = get_profile(pid)
    if not entry or _entry_role(entry) != role:
        # Still allow removing a stale id from the slot list.
        entry = None
    ids = get_slot_order_ids(pack, slot_index, role, seed=True)
    if pid not in ids:
        return None
    next_ids = [item for item in ids if item != pid]
    set_slot_order_ids(pack, slot_index, next_ids)
    deleted_from_table = False
    snapshot = dict(entry) if entry else {"id": pid, "role_column": role}
    if entry and not profile_used_in_formation_slots(
        pack, pid, except_slot=slot_index
    ):
        popped = pop_profile(pid)
        if popped:
            snapshot = popped
            deleted_from_table = True
    return {
        "formation_id": pack,
        "slot": int(_slot_key(slot_index)) if _slot_key(slot_index).isdigit() else slot_index,
        "role": role,
        "entries": [snapshot],
        "deleted_from_table": deleted_from_table,
    }


def delete_profile_with_slot_cleanup(
    profile_id: str,
    *,
    formation_id: str | None = None,
    formation_slots: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Delete a shortlist profile and strip it from formation slot lists.

    Returns an undo payload compatible with ``restore_to_slot_depth``.
    """
    pid = str(profile_id or "").strip()
    if not pid:
        return None
    entry = get_profile(pid)
    if not entry:
        return None
    role = _entry_role(entry)
    pack = str(formation_id or "").strip()
    slot_refs: list[dict[str, Any]] = []
    for slot in list(formation_slots or []):
        if not isinstance(slot, dict):
            continue
        slot_role = str(slot.get("column") or role or "").strip()
        if not pack or not slot_role:
            continue
        try:
            slot_index = slot["index"]
        except KeyError:
            continue
        ids = get_slot_order_ids(pack, slot_index, slot_role, seed=True)
        if pid not in ids:
            continue
        set_slot_order_ids(
            pack, slot_index, [item for item in ids if item != pid]
        )
        slot_refs.append(
            {
                "slot": int(_slot_key(slot_index))
                if _slot_key(slot_index).isdigit()
                else slot_index,
                "role": slot_role,
                "slot_label": str(
                    slot.get("display_label") or slot.get("label") or ""
                ).strip(),
            }
        )
    popped = pop_profile(pid)
    if not popped:
        return None
    primary = slot_refs[0] if slot_refs else None
    return {
        "formation_id": pack,
        "slot": primary["slot"] if primary else None,
        "role": (primary["role"] if primary else role) or role,
        "slot_label": (
            primary["slot_label"]
            if primary and primary.get("slot_label")
            else "Shortlist"
        ),
        "slot_refs": slot_refs,
        "entries": [popped],
        "deleted_from_table": True,
        "source": "table",
    }


def restore_to_slot_depth(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Restore undo item to the bottom of its formation slot depth."""
    if not isinstance(item, dict):
        return []
    pack = str(item.get("formation_id") or "").strip()
    role = str(item.get("role") or "").strip()
    slot_index = item.get("slot")
    entries = list(item.get("entries") or [])
    if not entries:
        return []
    if item.get("deleted_from_table"):
        restored = restore_profiles_at_depth_bottom(entries)
    else:
        restored = []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or "").strip()
            live = get_profile(pid) if pid else None
            if live is None:
                restored.extend(restore_profiles_at_depth_bottom([raw]))
            else:
                restored.append(dict(live))
    if not restored:
        return []

    refs = [
        ref
        for ref in list(item.get("slot_refs") or [])
        if isinstance(ref, dict) and ref.get("slot") is not None
    ]
    if not refs and slot_index is not None and role:
        refs = [{"slot": slot_index, "role": role}]
    if not pack or not refs:
        return restored

    for ref in refs:
        ref_role = str(ref.get("role") or role or "").strip()
        ref_slot = ref.get("slot")
        if not ref_role or ref_slot is None:
            continue
        ids = get_slot_order_ids(pack, ref_slot, ref_role, seed=True)
        for entry in restored:
            pid = str(entry.get("id") or "").strip()
            if not pid:
                continue
            ids = [item_id for item_id in ids if item_id != pid]
            ids.append(pid)
        set_slot_order_ids(pack, ref_slot, ids)
    return restored


def auto_rank_slot_by_score(
    formation_id: str | None,
    slot_index: int | str,
    role_column: str,
) -> int:
    """Reset one slot’s depth order from role Score ranking."""
    role = str(role_column or "").strip()
    if not role:
        return 0
    ordered = sorted(
        [entry for entry in list_role_profiles() if _entry_role(entry) == role],
        key=_score_name_sort_key,
    )
    ids = [str(entry.get("id") or "") for entry in ordered if entry.get("id")]
    set_slot_order_ids(formation_id, slot_index, ids)
    return len(ids)


def _read_index(library_id: str | None = None) -> list[dict[str, Any]]:
    ensure_dirs()
    path = _index_path(library_id)
    data = _read_json(path, [])
    return data if isinstance(data, list) else []


def _write_index(entries: list[dict[str, Any]], library_id: str | None = None) -> None:
    ensure_dirs()
    _write_json(_index_path(library_id), list(entries or []))


def split_player_key(key: str) -> tuple[str, str]:
    text = str(key or "").strip()
    if "|" in text:
        name, club = text.split("|", 1)
        return name.strip(), club.strip()
    return text, ""


def _norm_player_name(value: Any) -> str:
    return str(value or "").strip().casefold()


def _index_by_player_name(
    items: list[Any],
    *,
    name_of,
) -> dict[str, list[Any]]:
    """Group file rows/players by casefolded name (club transfers keep the same name)."""
    out: dict[str, list[Any]] = {}
    for item in items:
        name = _norm_player_name(name_of(item))
        if not name:
            continue
        out.setdefault(name, []).append(item)
    return out


def _pick_name_match(
    candidates: list[Any],
    *,
    preferred_club: str = "",
    club_of,
) -> Any | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    club = _norm_player_name(preferred_club)
    if club:
        for item in candidates:
            if _norm_player_name(club_of(item)) == club:
                return item
    return candidates[0]


def profile_identity(profile: dict[str, Any]) -> tuple[str, str]:
    row = profile.get("row") or {}
    name = str(row.get("Name") or "").strip()
    club = str(row.get("Club") or "").strip()
    if name:
        return name, club
    return split_player_key(profile.get("player_key") or "")


def profile_upsert_key(entry: dict[str, Any]) -> tuple[str, str]:
    """Dedup by player + role (role blank for stats/percentile saves)."""
    return (
        entry.get("player_key") or "",
        entry.get("role_column") or "",
    )


def _clean_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).strip()
    if text in ("", "-", "—"):
        return None
    return text


def _clean_snapshot_dict(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {key: _clean_cell(value) for key, value in row.items()}


def build_role_row_snapshot(
    scored_row: dict[str, Any],
    role_column: str,
    *,
    percentiles: dict[str, Any] | None = None,
    minutes: Any = None,
) -> dict[str, Any]:
    """Preserve the computed row and add normalized role snapshot fields."""
    out = _clean_snapshot_dict(scored_row)
    score = scored_row.get(role_column)
    try:
        score_f = float(score) if score not in (None, "", "-", "—") else None
    except (TypeError, ValueError):
        score_f = None
    out["Role"] = role_column
    out["Score"] = score_f
    out["Eligible"] = bool(scored_row.get(f"{role_column} eligible"))
    pct_keys = (
        "overall",
        "overall_color",
        "defending",
        "defending_color",
        "defending_label",
        "final_third",
        "final_third_color",
        "final_third_label",
        "possession",
        "possession_color",
        "possession_label",
        "Minutes",
    )
    if percentiles:
        for key in pct_keys:
            if key in percentiles:
                out[key] = percentiles.get(key)
    if minutes is not None and out.get("Minutes") in (None, ""):
        out["Minutes"] = minutes
    return out


def percentile_fields_from_stats_player(
    player: dict[str, Any] | None,
    *,
    settings=None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
    cohort_players: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Subset of ``build_stats_row_snapshot`` used when enriching role saves."""
    if not player:
        return {}
    snap = build_stats_row_snapshot(
        player,
        settings=settings,
        metric_p100=metric_p100,
        metric_p0=metric_p0,
        cohort_players=cohort_players,
    )
    keys = (
        "Minutes",
        "overall",
        "overall_color",
        "defending",
        "defending_color",
        "defending_label",
        "final_third",
        "final_third_color",
        "final_third_label",
        "possession",
        "possession_color",
        "possession_label",
        "percentile_phase",
        "percentile_phase_label",
    )
    return {k: snap[k] for k in keys if k in snap}


def build_stats_row_snapshot(
    player: dict[str, Any],
    *,
    settings=None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
    cohort_players: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One shortlist-style row: identity + overall / category percentiles."""
    import services.ui_settings as us
    from scoring.stats_scorer import (
        adaptive_metric_bound_maps,
        category_average_band,
        labeled_view_categories,
        overall_average_band,
        pos_group_label,
        resolve_player_pos_group,
        scoring_stats,
    )

    settings = us.normalize(settings)
    identity_cols = us.shortlist_columns_for("player_stats", settings)
    out: dict[str, Any] = {
        "Name": _clean_cell(player.get("name")),
        "Age": player.get("age"),
        "Club": _clean_cell(player.get("club")),
        "Division": _clean_cell(player.get("division")),
        "Nation": _clean_cell(player.get("nation")),
        "Position": _clean_cell(player.get("position")),
        "Best Pos": _clean_cell(player.get("best_pos")),
        "Height": _clean_cell(player.get("height")),
        "Left Foot": _clean_cell(player.get("left_foot")),
        "Right Foot": _clean_cell(player.get("right_foot")),
        "Rec": _clean_cell(player.get("rec")),
        "Injury": _clean_cell(player.get("injury")),
        "Minutes": player.get("minutes"),
    }
    # Keep only configured identity columns + core fields.
    keep = set(identity_cols) | {
        "Name",
        "Club",
        "Minutes",
        "overall",
        "defending",
        "final_third",
        "possession",
        "percentile_phase",
        "percentile_phase_label",
    }
    out = {k: v for k, v in out.items() if k in keep or k in ("Name", "Club")}

    stats = scoring_stats(player)
    group = resolve_player_pos_group(player)
    out["percentile_phase"] = group
    out["percentile_phase_label"] = pos_group_label(group)
    out["stats_limited_tracking"] = bool(player.get("stats_limited_tracking"))
    thresh = settings.get("stats_thresholds")
    if (metric_p100 is None or metric_p0 is None) and cohort_players is not None:
        auto_p0, auto_p100 = adaptive_metric_bound_maps(cohort_players, thresh)
        if metric_p0 is None:
            metric_p0 = auto_p0
        if metric_p100 is None:
            metric_p100 = auto_p100
    overall = overall_average_band(
        group,
        stats,
        threshold_overrides=thresh,
        metric_p100=metric_p100,
        metric_p0=metric_p0,
    )
    out["overall"] = overall.get("percentile")
    out["overall_color"] = overall.get("color")
    for section in labeled_view_categories(group=group, dual_final_third=False):
        cat_id = section["id"]
        band = category_average_band(
            group,
            cat_id,
            stats,
            threshold_overrides=thresh,
            metric_p100=metric_p100,
            metric_p0=metric_p0,
        )
        out[cat_id] = band.get("percentile")
        out[f"{cat_id}_color"] = band.get("color")
        out[f"{cat_id}_label"] = section.get("abbr") or section.get("label") or cat_id
    return out


def expand_role_profile_rows(
    player_keys: list[str],
    payload: dict[str, Any] | None,
    *,
    focus_roles,
    hybrids_only: bool,
    eligible_only: bool = True,
    role_players: list[dict[str, Any]] | None = None,
    stats_players: list[dict[str, Any]] | None = None,
    file_id: str = "",
    settings=None,
) -> list[dict[str, Any]]:
    """Build one snapshot entry dict per (player, eligible role) for saving.

    Each item includes ``row`` (shortlist fields + percentiles) and ``player``
    (single parsed role player for the Role scores modal).
    """
    from scoring.role_scorer import (
        combo_column_labels,
        expand_view_role_columns,
        normalize_combos,
    )

    if not player_keys:
        return []
    labels = list((payload or {}).get("roles") or [])
    if not labels:
        return []

    focused: list[str] = []
    if focus_roles is None or focus_roles == "":
        focused = []
    elif isinstance(focus_roles, str):
        text = focus_roles.strip()
        focused = [text] if text else []
    else:
        for item in focus_roles:
            text = str(item or "").strip()
            if text and text not in focused:
                focused.append(text)
    view_roles = [role for role in focused if role in labels] or labels

    combos = normalize_combos((payload or {}).get("combos"))
    if hybrids_only:
        combo_cols = combo_column_labels(combos)
        if combo_cols:
            allowed = set(combo_cols)
            view_roles = [role for role in view_roles if role in allowed] or combo_cols

    role_columns = expand_view_role_columns(
        view_roles, combos, include_parts=not hybrids_only
    )
    rows_by_key = {
        player_row_key(row): row
        for row in ((payload or {}).get("rows") or [])
        if player_row_key(row)
    }
    role_by_key = {
        player_row_key({"Name": p.get("name"), "Club": p.get("club")}): p
        for p in (role_players or [])
        if player_row_key({"Name": p.get("name"), "Club": p.get("club")})
    }
    stats_by_key = {
        stats_player_key(p): p
        for p in (stats_players or [])
        if stats_player_key(p)
    }
    from scoring.stats_scorer import adaptive_metric_bound_maps
    import services.ui_settings as us

    settings = us.normalize(settings)
    metric_p0, metric_p100 = adaptive_metric_bound_maps(
        stats_players, settings.get("stats_thresholds")
    )

    out: list[dict[str, Any]] = []
    for key in player_keys:
        scored = rows_by_key.get(key)
        if scored is None:
            continue
        player = role_by_key.get(key)
        stats_player = stats_by_key.get(key)
        pct = percentile_fields_from_stats_player(
            stats_player,
            settings=settings,
            metric_p100=metric_p100,
            metric_p0=metric_p0,
        )
        minutes = stats_player.get("minutes") if stats_player else None
        for role_col in role_columns:
            if eligible_only and not scored.get(f"{role_col} eligible"):
                continue
            out.append(
                {
                    "player_key": key,
                    "role_column": role_col,
                    "row": build_role_row_snapshot(
                        scored,
                        role_col,
                        percentiles=pct or None,
                        minutes=minutes,
                    ),
                    "player": player,
                    "stats_player": stats_player,
                    "file_id": file_id or "",
                }
            )
    return out


def load_stats_players_for_file(file_id: str) -> list[dict[str, Any]]:
    """Best-effort stats players for enriching role-score saves with percentiles."""
    if not file_id:
        return []
    try:
        import services.upload_cache as upload_cache
        from scoring.stats_scorer import parse_stats_export

        hit = upload_cache.try_stats_players(file_id)
        if hit:
            return hit[0]
        entry = lib.get_file(file_id)
        if not entry:
            return []
        text, _ = lib.read_text(file_id)
        if not text:
            return []
        # Try parsing even when the library flag is stale — combined exports
        # often include Minutes + per-90 columns for role-score saves.
        try:
            return parse_stats_export(text)
        except ValueError:
            if not entry.get("stats"):
                return []
            raise
    except Exception:
        return []


def _entry_looks_like_gk(entry: dict[str, Any] | None) -> bool:
    """True when a saved profile is a goalkeeper (stats group or position text)."""
    from scoring.stats_scorer import is_gk_group

    if not isinstance(entry, dict):
        return False
    for key in ("stats_player", "player"):
        blob = entry.get(key)
        if isinstance(blob, dict) and is_gk_group(blob.get("pos_group")):
            return True
    row = entry.get("row") or {}
    for field in ("Position", "Best Pos"):
        text = str(row.get(field) or "").strip().upper()
        if not text:
            continue
        if text == "GK" or text.startswith("GK ") or text.startswith("GK/"):
            return True
    return False


def refresh_profile_percentiles(settings=None) -> int:
    """Recompute stored overall/category percentiles with adaptive p0/p100 bounds.

    Profiles keep snapshot percentiles from save time; after adaptive floors /
    ceilings or phase scoping change, those snapshots stay stale until
    refreshed. Returns how many profiles were updated.
    """
    import services.ui_settings as us
    from scoring.stats_scorer import (
        adaptive_metric_bound_maps,
        resolve_player_pos_group,
    )

    settings = us.normalize(settings)
    thresh = settings.get("stats_thresholds")
    index = _read_index()
    if not index:
        return 0

    by_file: dict[str, list[dict[str, Any]]] = {}
    orphan: list[dict[str, Any]] = []
    for entry in index:
        if not isinstance(entry, dict):
            continue
        file_id = str(entry.get("file_id") or "").strip()
        if file_id:
            by_file.setdefault(file_id, []).append(entry)
        else:
            orphan.append(entry)

    cohort_cache: dict[str, list[dict[str, Any]]] = {}
    bounds_cache: dict[str, tuple[dict[str, float], dict[str, float]]] = {}
    updated = 0

    def _cohort(
        file_id: str,
    ) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, float]]:
        if file_id not in cohort_cache:
            players = load_stats_players_for_file(file_id)
            cohort_cache[file_id] = players
            bounds_cache[file_id] = adaptive_metric_bound_maps(players, thresh)
        p0_map, p100_map = bounds_cache[file_id]
        return cohort_cache[file_id], p0_map, p100_map

    def _stats_for(
        entry: dict[str, Any],
        cohort: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        by_key = {
            stats_player_key(player): player
            for player in cohort
            if stats_player_key(player)
        }
        hit = by_key.get(str(entry.get("player_key") or "").strip())
        if isinstance(hit, dict):
            return hit
        embedded = entry.get("stats_player")
        if isinstance(embedded, dict) and (
            embedded.get("stats") is not None or embedded.get("pos_group")
        ):
            return embedded
        return None

    def _apply(
        entry: dict[str, Any],
        cohort: list[dict[str, Any]],
        metric_p0: dict[str, float],
        metric_p100: dict[str, float],
    ) -> bool:
        stats_player = _stats_for(entry, cohort)
        if not isinstance(stats_player, dict):
            return False
        band_player = dict(stats_player)
        row = entry.get("row") or {}
        # Always re-resolve phase so Ovr/Def/F3/Poss use the right benchmark block.
        if not band_player.get("best_pos") and row.get("Best Pos"):
            band_player["best_pos"] = row.get("Best Pos")
        if not band_player.get("position") and row.get("Position"):
            band_player["position"] = row.get("Position")
        band_player["pos_group"] = resolve_player_pos_group(band_player)
        pct = percentile_fields_from_stats_player(
            band_player,
            settings=settings,
            metric_p100=metric_p100,
            metric_p0=metric_p0,
        )
        if not pct:
            return False
        next_row = dict(row)
        changed = False
        for key, value in pct.items():
            if next_row.get(key) != value:
                next_row[key] = value
                changed = True
        if not changed:
            entry["stats_player"] = band_player
            return True
        entry["row"] = next_row
        entry["stats_player"] = band_player
        return True

    def _apply_embedded_only(entry: dict[str, Any]) -> bool:
        """Recompute from the snapshot alone when the upload cohort is gone."""
        stats_player = entry.get("stats_player")
        if not isinstance(stats_player, dict):
            return False
        cohort = [stats_player]
        metric_p0, metric_p100 = adaptive_metric_bound_maps(cohort, thresh)
        return _apply(entry, cohort, metric_p0, metric_p100)

    for file_id, entries in by_file.items():
        cohort, metric_p0, metric_p100 = _cohort(file_id)
        if not cohort:
            for entry in entries:
                if _apply_embedded_only(entry):
                    updated += 1
            continue
        for entry in entries:
            if _stats_for(entry, cohort) is not None:
                if _apply(entry, cohort, metric_p0, metric_p100):
                    updated += 1
            elif _apply_embedded_only(entry):
                updated += 1

    for entry in orphan:
        if _apply_embedded_only(entry):
            updated += 1

    if updated:
        _write_index(index)
    return updated


def refresh_goalkeeper_percentiles(settings=None) -> int:
    """Backward-compatible alias for :func:`refresh_profile_percentiles`."""
    return refresh_profile_percentiles(settings)


def _column_to_role_id() -> dict[str, str]:
    import config.role_weights.fm26_role_weight_config as pc
    from scoring.role_scorer import column_label

    return {column_label(role_id): role_id for role_id in pc.all_positions}


def _resolve_profile_role_column(
    role_column: str,
    *,
    column_map: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, str] | None]:
    """Map a stored Role column to base role ids and an optional hybrid combo."""
    from scoring.role_scorer import combo_column

    col = str(role_column or "").strip()
    if not col:
        return [], None
    by_col = column_map if column_map is not None else _column_to_role_id()
    role_id = by_col.get(col)
    if role_id:
        return [role_id], None
    if "+" not in col:
        return [], None
    left, _, right = col.partition("+")
    ip = by_col.get(left.strip())
    oop = by_col.get(right.strip())
    if not ip or not oop:
        return [], None
    # Prefer the canonical combo column label when rebuilding scores.
    expected = combo_column(ip, oop)
    if expected != col and expected not in by_col:
        # Still accept the stored label; apply_combos writes meta["column"].
        pass
    return [ip, oop], {"ip": ip, "oop": oop}


def _load_role_score_bundle(
    file_id: str,
    *,
    role_ids: list[str],
    combos: list[dict[str, str]],
    settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(role_players, scored_rows)`` for the library file."""
    import services.ui_settings as us
    import services.upload_cache as upload_cache
    from scoring.role_scorer import apply_combos, parse_export, score_players

    settings = us.normalize(settings)
    hybrid_w = us.hybrid_weights(settings)
    role_players: list[dict[str, Any]] | None = None
    scored: list[dict[str, Any]] | None = None

    hit = upload_cache.try_role_players(file_id)
    if hit:
        role_players, _cache = hit
        scored = upload_cache.cached_role_rows(file_id)

    if role_players is None or scored is None:
        entry = lib.get_file(file_id)
        if not entry:
            raise FileNotFoundError("Saved file not found.")
        if not entry.get("role_scores"):
            return [], []
        text, _ = lib.read_text(file_id)
        role_players = parse_export(text)
        needed = list(dict.fromkeys(role_ids))
        for item in combos:
            for rid in (item.get("ip"), item.get("oop")):
                if rid and rid not in needed:
                    needed.append(rid)
        if not needed:
            import config.role_weights.fm26_role_weight_config as pc

            needed = list(pc.all_positions.keys())
        scored = score_players(
            role_players,
            needed,
            tier_weights=us.tier_weights(settings),
            set_piece_profiles=us.set_piece_profiles(settings),
        )

    if combos:
        scored = apply_combos(
            [dict(row) for row in scored],
            combos,
            ip_weight=hybrid_w["ip"],
            oop_weight=hybrid_w["oop"],
        )
    return role_players or [], scored or []


def replace_profiles_from_saved_file(
    file_id: str,
    *,
    settings=None,
) -> dict[str, Any]:
    """Replace profile personal info, role scores, and percentiles from a library file.

    Matches existing profiles by player **name** only (club can change mid-season).
    When several file rows share a name, prefers the profile's current club if present.
    Role profiles keep their ``role_column`` and profile ``id`` (depth/slots stay valid).
    Players missing from the file are left unchanged and reported under ``missing``.
    """
    import services.ui_settings as us
    from scoring.stats_scorer import adaptive_metric_bound_maps

    file_id = str(file_id or "").strip()
    if not file_id:
        raise ValueError("Choose a saved file.")
    entry = lib.get_file(file_id)
    if not entry:
        raise FileNotFoundError("Saved file not found.")

    settings = us.normalize(settings)
    source_label = lib.display_label(entry)
    role_entries = list_role_profiles()
    pct_entries = list_percentile_profiles()
    if not role_entries and not pct_entries:
        raise ValueError("No saved profiles to update.")

    column_map = _column_to_role_id()
    role_ids: list[str] = []
    combos: list[dict[str, str]] = []
    combo_seen: set[tuple[str, str]] = set()
    unresolved_roles: list[str] = []
    for prof in role_entries:
        col = str(prof.get("role_column") or (prof.get("row") or {}).get("Role") or "").strip()
        ids, combo = _resolve_profile_role_column(col, column_map=column_map)
        if not ids:
            if col:
                unresolved_roles.append(col)
            continue
        for rid in ids:
            if rid not in role_ids:
                role_ids.append(rid)
        if combo:
            key = (combo["ip"], combo["oop"])
            if key not in combo_seen:
                combo_seen.add(key)
                combos.append(combo)

    role_players, scored_rows = _load_role_score_bundle(
        file_id,
        role_ids=role_ids,
        combos=combos,
        settings=settings,
    )
    stats_players = load_stats_players_for_file(file_id)

    scored_by_name = _index_by_player_name(
        scored_rows,
        name_of=lambda row: row.get("Name"),
    )
    role_by_name = _index_by_player_name(
        role_players,
        name_of=lambda player: player.get("name"),
    )
    stats_by_name = _index_by_player_name(
        stats_players,
        name_of=lambda player: player.get("name"),
    )
    metric_p0, metric_p100 = adaptive_metric_bound_maps(
        stats_players, settings.get("stats_thresholds")
    )

    items: list[dict[str, Any]] = []
    missing: list[str] = []
    seen_missing: set[str] = set()

    def _mark_missing(label: str) -> None:
        text = str(label or "").strip()
        if text and text not in seen_missing:
            seen_missing.add(text)
            missing.append(text)

    def _profile_name_club(prof: dict[str, Any]) -> tuple[str, str]:
        return profile_identity(prof)

    for prof in role_entries:
        player_key_value = str(prof.get("player_key") or "").strip()
        role_col = str(
            prof.get("role_column") or (prof.get("row") or {}).get("Role") or ""
        ).strip()
        if not player_key_value or not role_col:
            continue
        name, club = _profile_name_club(prof)
        name_key = _norm_player_name(name)
        if not name_key:
            continue
        scored = _pick_name_match(
            scored_by_name.get(name_key) or [],
            preferred_club=club,
            club_of=lambda row: row.get("Club"),
        )
        player = _pick_name_match(
            role_by_name.get(name_key) or [],
            preferred_club=club,
            club_of=lambda p: p.get("club"),
        )
        stats_player = _pick_name_match(
            stats_by_name.get(name_key) or [],
            preferred_club=club,
            club_of=lambda p: p.get("club"),
        )
        if scored is None:
            _mark_missing(name or player_key_value)
            continue
        if role_col not in scored:
            continue
        scored_row = dict(scored)
        if player and player.get("personality") not in (None, "", "-"):
            scored_row["Personality"] = player.get("personality")
        if player and player.get("media_handling") not in (None, "", "-"):
            scored_row["Media Handling"] = player.get("media_handling")
        pct = percentile_fields_from_stats_player(
            stats_player,
            settings=settings,
            metric_p100=metric_p100,
            metric_p0=metric_p0,
            cohort_players=stats_players,
        )
        minutes = stats_player.get("minutes") if stats_player else None
        items.append(
            {
                "player_key": player_key_value,
                "role_column": role_col,
                "row": build_role_row_snapshot(
                    scored_row,
                    role_col,
                    percentiles=pct or None,
                    minutes=minutes,
                ),
                "player": player,
                "stats_player": stats_player,
                "file_id": file_id,
            }
        )

    for prof in pct_entries:
        player_key_value = str(prof.get("player_key") or "").strip()
        if not player_key_value:
            continue
        name, club = _profile_name_club(prof)
        name_key = _norm_player_name(name)
        if not name_key:
            continue
        stats_player = _pick_name_match(
            stats_by_name.get(name_key) or [],
            preferred_club=club,
            club_of=lambda p: p.get("club"),
        )
        if stats_player is None:
            _mark_missing(name or player_key_value)
            continue
        items.append(
            {
                "player_key": player_key_value,
                "role_column": "",
                "row": build_stats_row_snapshot(
                    stats_player,
                    settings=settings,
                    metric_p100=metric_p100,
                    metric_p0=metric_p0,
                    cohort_players=stats_players,
                ),
                "player": _pick_name_match(
                    role_by_name.get(name_key) or [],
                    preferred_club=club,
                    club_of=lambda p: p.get("club"),
                ),
                "stats_player": stats_player,
                "file_id": file_id,
            }
        )

    if not items:
        raise ValueError(
            "No saved profiles matched players in that file by name. "
            "Renamed players will not match."
        )

    saved_from = "role_scores" if role_entries else "stats"
    saved = save_profile_rows(
        items,
        saved_from=saved_from,
        source_label=source_label,
    )
    return {
        "updated": len(saved),
        "missing": missing,
        "unresolved_roles": sorted(set(unresolved_roles)),
        "source_label": source_label,
        "file_id": file_id,
    }


def list_profiles() -> list[dict[str, Any]]:
    entries = _read_index()
    entries.sort(key=lambda item: item.get("saved_at") or "", reverse=True)
    return entries


def list_role_profiles() -> list[dict[str, Any]]:
    return [
        entry
        for entry in list_profiles()
        if entry.get("role_column") or (entry.get("row") or {}).get("Role")
    ]


def list_percentile_profiles() -> list[dict[str, Any]]:
    """Stats / percentile snapshots (no role_column)."""
    return [
        entry
        for entry in list_profiles()
        if not entry.get("role_column") and not (entry.get("row") or {}).get("Role")
    ]


def get_profile(profile_id: str) -> dict[str, Any] | None:
    for entry in list_profiles():
        if entry.get("id") == profile_id:
            return entry
    return None


def save_profile_rows(
    items: list[dict[str, Any]],
    *,
    saved_from: str,
    source_label: str = "",
    note: str | None = None,
    library_id: str | None = None,
) -> list[dict[str, Any]]:
    """Upsert profile entries that already include a ``row`` snapshot."""
    if saved_from not in SAVED_FROM_LABELS:
        raise ValueError(f"Invalid saved_from: {saved_from}")
    note_text = str(note or "").strip()
    if len(note_text) > 500:
        raise ValueError("Note is too long (max 500 characters).")
    if not items:
        raise ValueError("No profile rows to save.")
    target = _resolve_library_id(library_id)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    index = _read_index(target)
    by_key: dict[tuple[str, str], dict[str, Any]] = {
        profile_upsert_key(entry): entry for entry in index
    }
    saved: list[dict[str, Any]] = []
    for item in items:
        player_key_value = str(item.get("player_key") or "").strip()
        role_column = str(item.get("role_column") or "").strip()
        row = item.get("row")
        player = item.get("player")
        stats_player = item.get("stats_player")
        file_id = str(item.get("file_id") or "").strip()
        if not player_key_value or not isinstance(row, dict):
            continue
        pair = (player_key_value, role_column)
        existing = by_key.get(pair)
        if existing:
            existing["saved_at"] = now
            existing["saved_from"] = saved_from
            existing["row"] = row
            # Keep player_key aligned with the latest Name|Club (club transfers).
            refreshed_key = player_row_key(row)
            if refreshed_key and refreshed_key != existing.get("player_key"):
                by_key.pop(pair, None)
                existing["player_key"] = refreshed_key
                by_key[(refreshed_key, role_column)] = existing
            if isinstance(player, dict):
                existing["player"] = player
            if isinstance(stats_player, dict):
                existing["stats_player"] = stats_player
            elif "stats_player" in existing and stats_player is None:
                existing.pop("stats_player", None)
            existing["source_label"] = source_label or existing.get("source_label") or ""
            if note is not None:
                existing["note"] = note_text
            if file_id:
                existing["file_id"] = file_id
            saved.append(dict(existing))
            continue
        entry = {
            "id": uuid.uuid4().hex[:12],
            "player_key": player_key_value,
            "role_column": role_column,
            "row": row,
            "source_label": source_label or "",
            "saved_from": saved_from,
            "saved_at": now,
            "note": note_text,
        }
        if isinstance(player, dict):
            entry["player"] = player
        if isinstance(stats_player, dict):
            entry["stats_player"] = stats_player
        if file_id:
            entry["file_id"] = file_id
        index.append(entry)
        by_key[pair] = entry
        saved.append(dict(entry))
    _write_index(index, target)
    meta = get_library(target)
    if meta:
        meta["updated_at"] = now
        _write_json(_meta_path(target), meta)
    return saved


def save_profiles(
    file_id: str,
    player_keys: list[str],
    *,
    saved_from: str,
    note: str | None = None,
    role_entries: list[tuple[str, str]] | None = None,
    payload: dict[str, Any] | None = None,
    players: list[dict[str, Any]] | None = None,
    settings=None,
    source_label: str = "",
) -> list[dict[str, Any]]:
    """Build row snapshots then upsert. Prefer ``save_profile_rows`` for new callers."""
    label = source_label
    if not label and file_id:
        entry = lib.get_file(file_id)
        if entry:
            label = lib.display_label(entry)

    if saved_from == "role_scores":
        if role_entries is None:
            raise ValueError("Role saves require role_entries or expand_role_profile_rows.")
        # Legacy path: role_entries only had keys — build from payload.
        if payload is not None:
            items = expand_role_profile_rows(
                player_keys,
                payload,
                focus_roles=None,
                hybrids_only=False,
                eligible_only=False,
            )
            # Filter to requested pairs
            wanted = {(str(a), str(b)) for a, b in role_entries}
            items = [
                item
                for item in items
                if (item["player_key"], item["role_column"]) in wanted
            ]
        else:
            raise ValueError("Role saves need the scored payload to attach row data.")
        return save_profile_rows(
            items, saved_from=saved_from, source_label=label, note=note
        )

    # Stats: one row snapshot per player.
    players = players or []
    by_key = {stats_player_key(p): p for p in players if stats_player_key(p)}
    items = []
    for key in player_keys:
        player = by_key.get(key)
        if not player:
            continue
        items.append(
            {
                "player_key": key,
                "role_column": "",
                "row": build_stats_row_snapshot(
                    player, settings=settings, cohort_players=players
                ),
            }
        )
    return save_profile_rows(
        items, saved_from=saved_from, source_label=label, note=note
    )


def delete_profile(profile_id: str) -> bool:
    return bool(pop_profile(profile_id))


def pop_profile(profile_id: str) -> dict[str, Any] | None:
    """Remove one profile and return a copy for undo."""
    pid = str(profile_id or "").strip()
    if not pid:
        return None
    index = _read_index()
    removed: dict[str, Any] | None = None
    kept: list[dict[str, Any]] = []
    for entry in index:
        if str(entry.get("id") or "").strip() == pid:
            removed = dict(entry)
            continue
        kept.append(entry)
    if removed is None:
        return None
    _write_index(kept)
    role = _entry_role(removed)
    if role:
        compact_depth_ranks(role)
    return removed


def pop_profiles_for_depth_remove(
    profile_id: str,
    *,
    related_role_columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Delete the clicked profile plus same-player profiles in related roles.

    Returns deleted entry copies (for the undo tray). Related roles typically come
    from the active formation so one remove clears every applicable formation role.
    """
    pid = str(profile_id or "").strip()
    if not pid:
        return []
    target = get_profile(pid)
    if not target:
        return []
    player_key = str(target.get("player_key") or "").strip()
    roles = {
        str(role).strip()
        for role in (related_role_columns or [])
        if str(role or "").strip()
    }
    roles.add(_entry_role(target))
    roles.discard("")

    index = _read_index()
    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    touched_roles: set[str] = set()
    for entry in index:
        entry_role = _entry_role(entry)
        same_player = player_key and str(entry.get("player_key") or "") == player_key
        if same_player and entry_role in roles:
            removed.append(dict(entry))
            if entry_role:
                touched_roles.add(entry_role)
            continue
        if str(entry.get("id") or "").strip() == pid:
            removed.append(dict(entry))
            if entry_role:
                touched_roles.add(entry_role)
            continue
        kept.append(entry)
    if not removed:
        return []
    _write_index(kept)
    for role in sorted(touched_roles):
        compact_depth_ranks(role)
    return removed


def restore_profiles_at_depth_bottom(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-insert profiles and place each at the bottom of its role depth chart."""
    if not entries:
        return []
    index = _read_index()
    by_key = {profile_upsert_key(entry): entry for entry in index}
    existing_ids = {str(entry.get("id") or "") for entry in index}
    restored: list[dict[str, Any]] = []
    bottom_by_role: dict[str, list[str]] = {}

    for raw in entries:
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        entry.pop("depth_excluded", None)
        entry.pop("depth_rank", None)
        player_key = str(entry.get("player_key") or "").strip()
        if not player_key or not isinstance(entry.get("row"), dict):
            continue
        key = profile_upsert_key(entry)
        existing = by_key.get(key)
        if existing is not None:
            # Refresh snapshot but keep living id for rank updates.
            for field in (
                "row",
                "player",
                "stats_player",
                "source_label",
                "saved_from",
                "saved_at",
                "note",
                "file_id",
                "role_column",
            ):
                if field in entry:
                    existing[field] = entry[field]
            existing.pop("depth_excluded", None)
            existing.pop("depth_rank", None)
            live = existing
        else:
            eid = str(entry.get("id") or "").strip()
            if not eid or eid in existing_ids:
                entry["id"] = uuid.uuid4().hex[:12]
            index.append(entry)
            by_key[key] = entry
            existing_ids.add(str(entry["id"]))
            live = entry
        restored.append(dict(live))
        role = _entry_role(live)
        if role:
            bottom_by_role.setdefault(role, []).append(str(live.get("id") or ""))

    if restored:
        _write_index(index)
    for role, append_ids in bottom_by_role.items():
        ordered = ordered_profiles_for_role(role)
        ids = [
            str(entry.get("id") or "")
            for entry in ordered
            if str(entry.get("id") or "") and str(entry.get("id") or "") not in append_ids
        ]
        for pid in append_ids:
            if pid and pid not in ids:
                ids.append(pid)
        set_depth_ranks(role, ids)
    return restored


def _entry_role(entry: dict[str, Any]) -> str:
    return str(
        entry.get("role_column") or (entry.get("row") or {}).get("Role") or ""
    ).strip()


def _parse_depth_rank(entry: dict[str, Any]) -> int | None:
    raw = entry.get("depth_rank")
    if raw in (None, "", "-", "—"):
        return None
    try:
        rank = int(raw)
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def _score_name_sort_key(entry: dict[str, Any]) -> tuple:
    """Sort key: Score desc, then overall % desc, then name. Missing values last."""
    row = entry.get("row") or {}
    score = row.get("Score")
    try:
        score_f = float(score) if score not in (None, "", "-", "—") else None
    except (TypeError, ValueError):
        score_f = None
    overall = row.get("overall")
    try:
        overall_f = (
            float(overall) if overall not in (None, "", "-", "—") else None
        )
    except (TypeError, ValueError):
        overall_f = None
    name, _club = profile_identity(entry)
    return (
        0 if score_f is not None else 1,
        -(score_f or 0.0),
        0 if overall_f is not None else 1,
        -(overall_f or 0.0),
        name.casefold(),
    )


def ordered_profiles_for_role(role_column: str) -> list[dict[str, Any]]:
    """Ranked profiles first (by depth_rank), then unranked by Score desc."""
    role = str(role_column or "").strip()
    if not role:
        return []
    entries = [entry for entry in list_role_profiles() if _entry_role(entry) == role]
    ranked: list[tuple[int, dict[str, Any]]] = []
    unranked: list[dict[str, Any]] = []
    for entry in entries:
        rank = _parse_depth_rank(entry)
        if rank is None:
            unranked.append(entry)
        else:
            ranked.append((rank, entry))
    ranked.sort(key=lambda item: (item[0], *_score_name_sort_key(item[1])))
    unranked.sort(key=_score_name_sort_key)
    return [entry for _rank, entry in ranked] + unranked


def set_depth_ranks(role_column: str, ordered_profile_ids: list[str]) -> None:
    """Rewrite contiguous 1…n for ``role_column``; clear ranks for omitted ids."""
    role = str(role_column or "").strip()
    if not role:
        return
    ordered_ids = [str(pid).strip() for pid in ordered_profile_ids if str(pid or "").strip()]
    id_to_rank = {pid: index + 1 for index, pid in enumerate(ordered_ids)}
    index = _read_index()
    for entry in index:
        if _entry_role(entry) != role:
            continue
        eid = str(entry.get("id") or "").strip()
        if eid in id_to_rank:
            entry["depth_rank"] = id_to_rank[eid]
        else:
            entry.pop("depth_rank", None)
    _write_index(index)


def compact_depth_ranks(role_column: str) -> None:
    """Renumber existing ranked entries for a role to contiguous 1…n."""
    role = str(role_column or "").strip()
    if not role:
        return
    ranked = [
        entry
        for entry in list_role_profiles()
        if _entry_role(entry) == role and _parse_depth_rank(entry) is not None
    ]
    if not ranked:
        return
    ranked.sort(key=lambda entry: (_parse_depth_rank(entry) or 0, *_score_name_sort_key(entry)))
    set_depth_ranks(role, [str(entry.get("id") or "") for entry in ranked])


def auto_rank_role_by_score(role_column: str) -> int:
    """Set depth_rank 1…n by Score desc, then overall % desc, then name."""
    role = str(role_column or "").strip()
    if not role:
        return 0
    entries = [entry for entry in list_role_profiles() if _entry_role(entry) == role]
    if not entries:
        return 0
    ordered = sorted(entries, key=_score_name_sort_key)
    set_depth_ranks(role, [str(entry.get("id") or "") for entry in ordered])
    return len(ordered)


def auto_rank_all_roles_by_score(role_columns: list[str] | None = None) -> int:
    if role_columns is not None:
        roles = [str(role).strip() for role in role_columns if str(role or "").strip()]
    else:
        roles = sorted(
            {
                role
                for entry in list_role_profiles()
                if (role := _entry_role(entry))
            }
        )
    total = 0
    for role in roles:
        total += auto_rank_role_by_score(role)
    return total


def move_depth_rank(profile_id: str, direction: int) -> bool:
    """Swap with neighbor in display order, then assign contiguous ranks for the role."""
    pid = str(profile_id or "").strip()
    if not pid or direction not in (-1, 1):
        return False
    profile = get_profile(pid)
    if not profile:
        return False
    role = _entry_role(profile)
    if not role:
        return False
    ordered = ordered_profiles_for_role(role)
    ids = [str(entry.get("id") or "") for entry in ordered]
    try:
        index = ids.index(pid)
    except ValueError:
        return False
    neighbor = index + int(direction)
    if neighbor < 0 or neighbor >= len(ids):
        return False
    ids[index], ids[neighbor] = ids[neighbor], ids[index]
    set_depth_ranks(role, ids)
    return True


def place_depth_rank(profile_id: str, target_rank: int) -> bool:
    """Move profile to a 1-based rank within its role, then renumber 1…n."""
    pid = str(profile_id or "").strip()
    try:
        want = int(target_rank)
    except (TypeError, ValueError):
        return False
    if not pid or want < 1:
        return False
    profile = get_profile(pid)
    if not profile:
        return False
    role = _entry_role(profile)
    if not role:
        return False
    ordered = ordered_profiles_for_role(role)
    ids = [str(entry.get("id") or "").strip() for entry in ordered]
    ids = [eid for eid in ids if eid]
    if pid not in ids:
        return False
    current = ids.index(pid) + 1
    if current == want:
        return False
    ids.remove(pid)
    insert_at = min(max(want, 1), len(ids) + 1) - 1
    ids.insert(insert_at, pid)
    set_depth_ranks(role, ids)
    return True


def role_score_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    row = profile.get("row") or {}
    role = profile.get("role_column") or row.get("Role") or ""
    score = row.get("Score")
    try:
        score_f = float(score) if score not in (None, "", "-") else None
    except (TypeError, ValueError):
        score_f = None
    return {
        "role": role,
        "score": score_f,
        "eligible": bool(row.get("Eligible")),
    }


def percentile_from_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    row = profile.get("row") or {}
    if "overall" not in row and "defending" not in row:
        return None
    categories = {}
    for cat_id in ("defending", "final_third", "possession"):
        if cat_id not in row:
            continue
        categories[cat_id] = {
            "label": row.get(f"{cat_id}_label") or cat_id,
            "percentile": row.get(cat_id),
            "color": row.get(f"{cat_id}_color"),
        }
    return {
        "overall": row.get("overall"),
        "overall_color": row.get("overall_color"),
        "categories": categories,
    }
