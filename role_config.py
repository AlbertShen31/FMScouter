"""Load, inspect, and persist FM26 role weight configs.

Python defaults in `config/role_weights/fm26_role_weight_config.py` stay the
source of truth. Named JSON packs in `config/role_weights/packs/` overlay
those defaults so the config editor and role scores page share one live set
of weights. Built-in is read-only; Save only writes a named pack. New configs
are either a copy of the selected pack or a blank slate.

Pack `group_schema` is 2. Older files omit the field (treated as 1) and
used `w` for wide midfielders and `wam` for wingers. Load maps those IDs
before applying overlays so a saved `w` is not read as the new Wingers
group. See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path

import config.fm26_role_weight_config as pc
from config.paths import (
    LEGACY_ROLE_ACTIVE_PATH,
    LEGACY_ROLE_DEFAULTS_PATH,
    LEGACY_ROLE_OVERRIDES_PATH,
    LEGACY_ROLE_PACKS_DIR,
    ROLE_WEIGHTS_ACTIVE_PATH,
    ROLE_WEIGHTS_DEFAULTS_PATH,
    ROLE_WEIGHTS_DIR,
    ROLE_WEIGHTS_PACKS_DIR,
)
from phases import phase_is_gk

PACKS_DIR = ROLE_WEIGHTS_PACKS_DIR
ACTIVE_PATH = ROLE_WEIGHTS_ACTIVE_PATH
DEFAULTS_PATH = ROLE_WEIGHTS_DEFAULTS_PATH
LEGACY_OVERRIDE_PATH = LEGACY_ROLE_OVERRIDES_PATH

BUILTIN = "builtin"
WORKING = "working"

TIER_CYCLE = ("none", "key", "preferred", "useful")
NEXT_TIER = {"none": "key", "key": "preferred", "preferred": "useful", "useful": "none"}


def tier_weight_map(settings=None) -> dict:
    """Current key/preferred/useful multipliers (from UI settings when available)."""
    try:
        import ui_settings as us

        weights = us.tier_weights(settings)
        return {
            "none": 0,
            "key": weights["key"],
            "preferred": weights["preferred"],
            "useful": weights["useful"],
        }
    except Exception:
        return {
            "none": 0,
            "key": pc.KEY_WEIGHT,
            "preferred": pc.PREFERRED_WEIGHT,
            "useful": pc.USEFUL_WEIGHT,
        }


# Backward-compatible default snapshot; prefer tier_weight_map() for live settings.
TIER_WEIGHT = {
    "none": 0,
    "key": pc.KEY_WEIGHT,
    "preferred": pc.PREFERRED_WEIGHT,
    "useful": pc.USEFUL_WEIGHT,
}

MENTAL_ATTRS = [
    ("Agg", "Aggression"),
    ("Ant", "Anticipation"),
    ("Bra", "Bravery"),
    ("Cmp", "Composure"),
    ("Cnt", "Concentration"),
    ("Dec", "Decisions"),
    ("Det", "Determination"),
    ("Fla", "Flair"),
    ("Ldr", "Leadership"),
    ("OtB", "Off the Ball"),
    ("Pos", "Positioning"),
    ("Tea", "Teamwork"),
    ("Vis", "Vision"),
    ("Wor", "Work Rate"),
]

PHYSICAL_ATTRS = [
    ("Acc", "Acceleration"),
    ("Agi", "Agility"),
    ("Bal", "Balance"),
    ("Jum", "Jumping Reach"),
    ("Nat", "Natural Fitness"),
    ("Pac", "Pace"),
    ("Sta", "Stamina"),
    ("Str", "Strength"),
]

SET_PIECE_ATTRS = [
    ("Cor", "Corners"),
    ("Fre", "Free Kick Taking"),
    ("LTh", "Long Throws"),
    ("Pen", "Penalty Taking"),
]

OUTFIELD_ATTR_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Technical",
        [
            ("Cro", "Crossing"),
            ("Dri", "Dribbling"),
            ("Fin", "Finishing"),
            ("Fir", "First Touch"),
            ("Hea", "Heading"),
            ("Lon", "Long Shots"),
            ("Mar", "Marking"),
            ("Pas", "Passing"),
            ("Tck", "Tackling"),
            ("Tec", "Technique"),
        ],
    ),
    ("Mental", MENTAL_ATTRS),
    ("Physical", PHYSICAL_ATTRS),
]

GK_ATTR_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Goalkeeping",
        [
            ("Aer", "Aerial Reach"),
            ("Cmd", "Command of Area"),
            ("Com", "Communication"),
            ("Ecc", "Eccentricity"),
            ("Fir", "First Touch"),
            ("Han", "Handling"),
            ("Kic", "Kicking"),
            ("1v1", "One on Ones"),
            ("Pas", "Passing"),
            ("Pun", "Punching (Tendency)"),
            ("Ref", "Reflexes"),
            ("TRO", "Rushing Out (Tendency)"),
            ("Thr", "Throwing"),
        ],
    ),
    ("Mental", MENTAL_ATTRS),
    ("Physical", PHYSICAL_ATTRS),
]

ATTR_GROUPS = OUTFIELD_ATTR_GROUPS
ATTR_LABELS = {
    code: label
    for groups in (OUTFIELD_ATTR_GROUPS, GK_ATTR_GROUPS, [("Set Pieces", SET_PIECE_ATTRS)])
    for _name, attrs in groups
    for code, label in attrs
}

_FACTORY: dict | None = None
_DEFAULTS: dict | None = None
_SAVED: dict | None = None
_LOADED = False
_ACTIVE = BUILTIN


def _attr_lists(cfg: dict) -> tuple[list[str], list[str], list[str]]:
    return (
        list(cfg.get("key_attrs") or []),
        list(cfg.get("preferred_attrs") or cfg.get("green_attrs") or []),
        list(cfg.get("useful_attrs") or cfg.get("blue_attrs") or []),
    )


def _overlay_attr_lists(overlay: dict) -> tuple[list[str], list[str], list[str]]:
    preferred = (
        overlay["preferred_attrs"]
        if "preferred_attrs" in overlay
        else overlay.get("green_attrs")
    )
    useful = overlay["useful_attrs"] if "useful_attrs" in overlay else overlay.get("blue_attrs")
    return (
        list(overlay.get("key_attrs") or []),
        list(preferred or []),
        list(useful or []),
    )


def recompute_divisor(cfg: dict, settings=None) -> float:
    key_attrs, preferred_attrs, useful_attrs = _attr_lists(cfg)
    weights = tier_weight_map(settings)
    return (
        weights["key"] * len(key_attrs)
        + weights["preferred"] * len(preferred_attrs)
        + weights["useful"] * len(useful_attrs)
    )


def _apply_lists(
    cfg: dict,
    key_attrs: list[str],
    preferred_attrs: list[str],
    useful_attrs: list[str],
    settings=None,
) -> None:
    weights = tier_weight_map(settings)
    cfg["key_attrs"] = list(key_attrs)
    cfg["preferred_attrs"] = list(preferred_attrs)
    cfg["useful_attrs"] = list(useful_attrs)
    cfg["key_weight"] = weights["key"]
    cfg["preferred_weight"] = weights["preferred"]
    cfg["useful_weight"] = weights["useful"]
    for old in ("green_attrs", "blue_attrs", "green_weight", "blue_weight"):
        cfg.pop(old, None)
    cfg["divisor"] = recompute_divisor(cfg, settings)


def _restore_defaults() -> None:
    assert _DEFAULTS is not None
    pc.all_positions.clear()
    pc.all_positions.update(copy.deepcopy(_DEFAULTS))


def _remember_saved() -> None:
    global _SAVED
    _SAVED = copy.deepcopy(pc.all_positions)


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _roles_from_payload(data: dict) -> tuple[str, dict]:
    if isinstance(data.get("roles"), dict):
        return str(data.get("name") or ""), data["roles"]
    return str(data.get("name") or ""), {
        key: value for key, value in data.items() if isinstance(value, dict)
    }


def _payload_schema(data: dict) -> int:
    try:
        return int(data.get("group_schema") or 1)
    except (TypeError, ValueError):
        return 1


def migrate_group_ids(groups: list | None, schema: int | None = None) -> list[str]:
    """Map saved group ids onto the current `wm` / `w` names.

    Schema 1 (or missing): `w` → `wm`, `wam` → `w`.
    Schema 2+: keep current ids; leftover `wam` still becomes `w`.
    """
    schema = pc.GROUP_SCHEMA if schema is None else schema
    mapping = pc.GROUP_ID_LEGACY if schema < pc.GROUP_SCHEMA else {"wam": "w"}
    out = []
    seen = set()
    for gid in groups or []:
        mapped = mapping.get(str(gid), str(gid))
        if mapped in pc.GROUP_IDS and mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out


def _rewrite_overlay_groups(roles: dict, schema: int) -> dict:
    for overlay in roles.values():
        if not isinstance(overlay, dict) or "groups" not in overlay:
            continue
        overlay["groups"] = migrate_group_ids(overlay.get("groups"), schema)
    return roles


def _pack_path(pack_id: str) -> Path:
    return PACKS_DIR / f"{pack_id}.json"


def _role_overlay(cfg: dict, role_id: str | None = None) -> dict:
    out = {
        "key_attrs": list(cfg.get("key_attrs") or []),
        "preferred_attrs": list(cfg.get("preferred_attrs") or []),
        "useful_attrs": list(cfg.get("useful_attrs") or []),
    }
    live_groups = list(cfg.get("groups") or [])
    if role_id and _FACTORY is not None:
        factory_groups = list((_FACTORY.get(role_id) or {}).get("groups") or [])
        if live_groups != factory_groups:
            out["groups"] = live_groups
    elif live_groups:
        out["groups"] = live_groups
    return out


def snapshot() -> dict:
    ensure_loaded()
    return {role_id: _role_overlay(cfg, role_id) for role_id, cfg in pc.all_positions.items()}


def _apply_overlay(cfg: dict, overlay: dict, schema: int | None = None) -> None:
    _apply_lists(cfg, *_overlay_attr_lists(overlay))
    if "groups" not in overlay:
        return
    groups = migrate_group_ids(overlay.get("groups") or [], schema)
    if groups:
        cfg["groups"] = groups


def _apply_roles(roles: dict, schema: int | None = None) -> None:
    for role_id, overlay in roles.items():
        if role_id not in pc.all_positions or not isinstance(overlay, dict):
            continue
        _apply_overlay(pc.all_positions[role_id], overlay, schema)


def _write_pack(pack_id: str, name: str, roles: dict) -> None:
    _atomic_write(
        _pack_path(pack_id),
        {"name": name, "group_schema": pc.GROUP_SCHEMA, "roles": roles},
    )


def _read_active_id() -> str:
    data = _read_json(ACTIVE_PATH)
    pack_id = str(data.get("pack") or BUILTIN)
    if pack_id == BUILTIN or _pack_path(pack_id).exists():
        return pack_id
    return BUILTIN


def _write_active_id(pack_id: str) -> None:
    global _ACTIVE
    _ACTIVE = pack_id
    _atomic_write(ACTIVE_PATH, {"pack": pack_id})


def _pack_label(pack_id: str, fallback: str = "") -> str:
    if pack_id == BUILTIN:
        return "Built-in defaults"
    if pack_id == WORKING:
        name = _roles_from_payload(_read_json(_pack_path(WORKING)))[0]
        return name or "Working copy"
    name, _roles = _roles_from_payload(_read_json(_pack_path(pack_id)))
    return name or fallback or pack_id.replace("-", " ").replace("_", " ")


def _migrate_layout() -> None:
    """Move pre-reorg role-weight files into ``config/role_weights/``."""
    ROLE_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_ROLE_PACKS_DIR.exists():
        for path in LEGACY_ROLE_PACKS_DIR.glob("*.json"):
            dest = PACKS_DIR / path.name
            if not dest.exists():
                path.replace(dest)
        leftover = [p for p in LEGACY_ROLE_PACKS_DIR.iterdir() if p.name != ".gitkeep"]
        if not leftover:
            for keep in LEGACY_ROLE_PACKS_DIR.glob(".gitkeep"):
                keep.unlink(missing_ok=True)
            try:
                LEGACY_ROLE_PACKS_DIR.rmdir()
            except OSError:
                pass
    if LEGACY_ROLE_ACTIVE_PATH.exists() and not ACTIVE_PATH.exists():
        LEGACY_ROLE_ACTIVE_PATH.replace(ACTIVE_PATH)
    elif LEGACY_ROLE_ACTIVE_PATH.exists() and ACTIVE_PATH.exists():
        LEGACY_ROLE_ACTIVE_PATH.unlink(missing_ok=True)
    if LEGACY_ROLE_DEFAULTS_PATH.exists() and not DEFAULTS_PATH.exists():
        LEGACY_ROLE_DEFAULTS_PATH.replace(DEFAULTS_PATH)
    elif LEGACY_ROLE_DEFAULTS_PATH.exists() and DEFAULTS_PATH.exists():
        LEGACY_ROLE_DEFAULTS_PATH.unlink(missing_ok=True)


def _migrate_legacy() -> None:
    _migrate_layout()
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    if not LEGACY_OVERRIDE_PATH.exists() or _pack_path(WORKING).exists():
        return
    payload = _read_json(LEGACY_OVERRIDE_PATH)
    name, roles = _roles_from_payload(payload)
    if not roles:
        return
    _rewrite_overlay_groups(roles, _payload_schema(payload))
    _write_pack(WORKING, name or "Working copy", roles)
    if not ACTIVE_PATH.exists():
        _write_active_id(WORKING)


def _unique_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "config"
    if base in {BUILTIN, WORKING}:
        base = f"{base}-custom"
    slug = base
    n = 2
    while _pack_path(slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _reload_user_defaults() -> None:
    global _DEFAULTS
    assert _FACTORY is not None
    _DEFAULTS = copy.deepcopy(_FACTORY)
    payload = _read_json(DEFAULTS_PATH)
    if not payload:
        return
    schema = _payload_schema(payload)
    _name, roles = _roles_from_payload(payload)
    for role_id, overlay in roles.items():
        if role_id not in _DEFAULTS or not isinstance(overlay, dict):
            continue
        _apply_overlay(_DEFAULTS[role_id], overlay, schema)


def ensure_loaded() -> None:
    """Snapshot Python factory defaults, apply user default overrides, then load the last pack."""
    global _FACTORY, _LOADED, _ACTIVE
    if _LOADED:
        return
    _FACTORY = copy.deepcopy(pc.all_positions)
    _LOADED = True
    _reload_user_defaults()
    _migrate_legacy()
    _ACTIVE = _read_active_id()
    load_pack(_ACTIVE, persist=False)


def has_role(role_id: str | None) -> bool:
    ensure_loaded()
    return bool(role_id) and role_id in pc.all_positions


def role_cfg(role_id: str) -> dict:
    ensure_loaded()
    return pc.all_positions[role_id]


def role_phase(role_id: str) -> str:
    return str(role_cfg(role_id).get("phase") or "")


def attr_groups_for(role_id: str) -> list[tuple[str, list[tuple[str, str]]]]:
    cfg = role_cfg(role_id)
    if phase_is_gk(cfg.get("phase"), role_id):
        return GK_ATTR_GROUPS
    return OUTFIELD_ATTR_GROUPS


def is_gk_role(role_id: str) -> bool:
    cfg = role_cfg(role_id)
    return phase_is_gk(cfg.get("phase"), role_id)


def attr_tier(cfg: dict, attr: str) -> str:
    if attr in (cfg.get("key_attrs") or []):
        return "key"
    if attr in (cfg.get("preferred_attrs") or cfg.get("green_attrs") or []):
        return "preferred"
    if attr in (cfg.get("useful_attrs") or cfg.get("blue_attrs") or []):
        return "useful"
    return "none"


def is_modified(role_id: str) -> bool:
    ensure_loaded()
    default = (_SAVED or _DEFAULTS or {}).get(role_id)
    if not default or role_id not in pc.all_positions:
        return False
    cfg = pc.all_positions[role_id]
    default_groups = list(default.get("groups") or [])
    live_groups = list(cfg.get("groups") or [])
    return (
        set(cfg.get("key_attrs") or []) != set(default.get("key_attrs") or [])
        or set(_attr_lists(cfg)[1]) != set(_attr_lists(default)[1])
        or set(_attr_lists(cfg)[2]) != set(_attr_lists(default)[2])
        or live_groups != default_groups
    )


def active_pack_id() -> str:
    ensure_loaded()
    return _ACTIVE


def pack_options() -> list[dict]:
    ensure_loaded()
    options = [{"label": "Built-in defaults", "value": BUILTIN}]
    seen = {BUILTIN}
    if _pack_path(WORKING).exists():
        options.append({"label": _pack_label(WORKING), "value": WORKING})
        seen.add(WORKING)
    if PACKS_DIR.exists():
        for path in sorted(PACKS_DIR.glob("*.json")):
            pack_id = path.stem
            if pack_id in seen:
                continue
            options.append({"label": _pack_label(pack_id), "value": pack_id})
    return options


def load_pack(pack_id: str | None, persist: bool = True) -> str:
    ensure_loaded()
    chosen = pack_id or BUILTIN
    _restore_defaults()
    if chosen != BUILTIN:
        path = _pack_path(chosen)
        if path.exists():
            payload = _read_json(path)
            _name, roles = _roles_from_payload(payload)
            _apply_roles(roles, _payload_schema(payload))
        else:
            chosen = BUILTIN
    if persist:
        _write_active_id(chosen)
    else:
        global _ACTIVE
        _ACTIVE = chosen
    _remember_saved()
    return chosen


def persist_live() -> str | None:
    """Write the live weights to the selected named pack. Built-in is read-only."""
    ensure_loaded()
    pack_id = _ACTIVE or BUILTIN
    if pack_id == BUILTIN:
        return None
    name = _pack_label(pack_id, pack_id)
    _write_pack(pack_id, name, snapshot())
    _write_active_id(pack_id)
    _remember_saved()
    return pack_id


def create_pack(name: str | None, source: str = "copy") -> dict:
    """Create a named pack from the live config or from a blank slate."""
    ensure_loaded()
    label = (name or "").strip() or f"Config {datetime.now().strftime('%Y-%m-%d %H%M')}"
    if source == "scratch":
        for cfg in pc.all_positions.values():
            _apply_lists(cfg, [], [], [])
    pack_id = _unique_slug(label)
    _write_pack(pack_id, label, snapshot())
    _write_active_id(pack_id)
    _remember_saved()
    return {"id": pack_id, "name": label, "source": "scratch" if source == "scratch" else "copy"}


def save_pack_as(name: str | None) -> dict:
    return create_pack(name, "copy")


def _defaults_payload() -> tuple[str, dict]:
    payload = _read_json(DEFAULTS_PATH)
    if not payload:
        return "User defaults", {}
    name, roles = _roles_from_payload(payload)
    return name or "User defaults", roles if isinstance(roles, dict) else {}


def _write_defaults(name: str, roles: dict) -> None:
    if not roles:
        if DEFAULTS_PATH.exists():
            DEFAULTS_PATH.unlink()
        return
    _atomic_write(
        DEFAULTS_PATH,
        {"name": name, "group_schema": pc.GROUP_SCHEMA, "roles": roles},
    )


def save_as_defaults() -> None:
    """Make the current live weights the Reset / Built-in baseline."""
    ensure_loaded()
    _write_defaults("User defaults", snapshot())
    global _DEFAULTS
    _DEFAULTS = copy.deepcopy(pc.all_positions)


def save_role_as_default(role_id: str) -> None:
    """Overwrite one role in user defaults; leave every other role alone."""
    ensure_loaded()
    if role_id not in pc.all_positions or _DEFAULTS is None:
        return
    name, roles = _defaults_payload()
    roles[role_id] = _role_overlay(pc.all_positions[role_id], role_id)
    _write_defaults(name, roles)
    _DEFAULTS[role_id] = copy.deepcopy(pc.all_positions[role_id])


def restore_factory_defaults() -> None:
    """Drop user default overrides and reload the Python factory weights."""
    ensure_loaded()
    if DEFAULTS_PATH.exists():
        DEFAULTS_PATH.unlink()
    global _DEFAULTS
    assert _FACTORY is not None
    _DEFAULTS = copy.deepcopy(_FACTORY)
    _restore_defaults()
    _write_active_id(BUILTIN)


def restore_role_factory(role_id: str) -> None:
    """Restore one role to Python factory weights and drop its user default."""
    ensure_loaded()
    if not _FACTORY or role_id not in _FACTORY:
        return
    pc.all_positions[role_id] = copy.deepcopy(_FACTORY[role_id])
    if _DEFAULTS is not None:
        _DEFAULTS[role_id] = copy.deepcopy(_FACTORY[role_id])
    name, roles = _defaults_payload()
    if role_id in roles:
        roles.pop(role_id)
        _write_defaults(name, roles)
    if _ACTIVE != BUILTIN:
        persist_live()


def has_user_defaults() -> bool:
    ensure_loaded()
    return DEFAULTS_PATH.exists()


def set_attr_tier(role_id: str, attr: str, tier: str) -> str:
    """Set one attribute to Off, Key, Preferred, or Useful."""
    ensure_loaded()
    if role_id not in pc.all_positions or attr not in ATTR_LABELS:
        return "none"
    if tier not in TIER_CYCLE:
        return attr_tier(pc.all_positions[role_id], attr)
    cfg = pc.all_positions[role_id]
    key_attrs, preferred_attrs, useful_attrs = _attr_lists(cfg)
    key_attrs = [item for item in key_attrs if item != attr]
    preferred_attrs = [item for item in preferred_attrs if item != attr]
    useful_attrs = [item for item in useful_attrs if item != attr]
    if tier == "key":
        key_attrs.append(attr)
    elif tier == "preferred":
        preferred_attrs.append(attr)
    elif tier == "useful":
        useful_attrs.append(attr)
    _apply_lists(cfg, key_attrs, preferred_attrs, useful_attrs)
    return tier


def cycle_attr(role_id: str, attr: str) -> str:
    """Promote one attribute through Off → Key → Preferred → Useful."""
    ensure_loaded()
    if role_id not in pc.all_positions:
        return "none"
    return set_attr_tier(role_id, attr, NEXT_TIER[attr_tier(pc.all_positions[role_id], attr)])


def clear_role(role_id: str) -> None:
    """Turn off every key / preferred / useful attribute. Groups stay."""
    ensure_loaded()
    if role_id not in pc.all_positions:
        return
    _apply_lists(pc.all_positions[role_id], [], [], [])


def reset_role(role_id: str) -> None:
    """Reload this role from the selected config’s last saved weights."""
    ensure_loaded()
    saved = (_SAVED or _DEFAULTS or {}).get(role_id)
    if not saved:
        return
    pc.all_positions[role_id] = copy.deepcopy(saved)


def reset_all() -> None:
    ensure_loaded()
    if _SAVED is not None:
        pc.all_positions.clear()
        pc.all_positions.update(copy.deepcopy(_SAVED))
        return
    _restore_defaults()


def toggle_role_group(role_id: str, group: str) -> list[str]:
    """Add or remove a position bucket. Keeps at least one group."""
    ensure_loaded()
    if role_id not in pc.all_positions or group not in pc.GROUP_IDS:
        return list((pc.all_positions.get(role_id) or {}).get("groups") or [])
    cfg = pc.all_positions[role_id]
    current = [g for g in (cfg.get("groups") or []) if g in pc.GROUP_IDS]
    if group in current:
        if len(current) == 1:
            return current
        current = [g for g in current if g != group]
    else:
        current.append(group)
    cfg["groups"] = current
    return current
