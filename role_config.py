"""Load, inspect, and persist FM26 role weight configs.

Python defaults in `config/fm26_role_weight_config.py` stay the source of
truth. Named JSON packs in `config/packs/` overlay those defaults so the
config editor and role scores page share one live set of weights.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path

import config.fm26_role_weight_config as pc

ROOT = Path(__file__).resolve().parent
PACKS_DIR = ROOT / "config" / "packs"
ACTIVE_PATH = ROOT / "config" / "active_pack.json"
LEGACY_OVERRIDE_PATH = ROOT / "config" / "role_overrides.json"

BUILTIN = "builtin"
WORKING = "working"

TIER_CYCLE = ("none", "key", "green", "blue")
NEXT_TIER = {"none": "key", "key": "green", "green": "blue", "blue": "none"}
TIER_WEIGHT = {"none": 0, "key": pc.KEY_WEIGHT, "green": pc.GREEN_WEIGHT, "blue": pc.BLUE_WEIGHT}

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

_DEFAULTS: dict | None = None
_LOADED = False
_ACTIVE = BUILTIN


def _attr_lists(cfg: dict) -> tuple[list[str], list[str], list[str]]:
    return (
        list(cfg.get("key_attrs") or []),
        list(cfg.get("green_attrs") or []),
        list(cfg.get("blue_attrs") or []),
    )


def recompute_divisor(cfg: dict) -> int:
    key_attrs, green_attrs, blue_attrs = _attr_lists(cfg)
    return (
        pc.KEY_WEIGHT * len(key_attrs)
        + pc.GREEN_WEIGHT * len(green_attrs)
        + pc.BLUE_WEIGHT * len(blue_attrs)
    )


def _apply_lists(cfg: dict, key_attrs: list[str], green_attrs: list[str], blue_attrs: list[str]) -> None:
    cfg["key_attrs"] = list(key_attrs)
    cfg["green_attrs"] = list(green_attrs)
    cfg["blue_attrs"] = list(blue_attrs)
    cfg["key_weight"] = pc.KEY_WEIGHT
    cfg["green_weight"] = pc.GREEN_WEIGHT
    cfg["blue_weight"] = pc.BLUE_WEIGHT
    cfg["divisor"] = recompute_divisor(cfg)


def _restore_defaults() -> None:
    assert _DEFAULTS is not None
    pc.all_positions.clear()
    pc.all_positions.update(copy.deepcopy(_DEFAULTS))


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


def _pack_path(pack_id: str) -> Path:
    return PACKS_DIR / f"{pack_id}.json"


def snapshot() -> dict:
    ensure_loaded()
    roles = {}
    for role_id, cfg in pc.all_positions.items():
        roles[role_id] = {
            "key_attrs": list(cfg.get("key_attrs") or []),
            "green_attrs": list(cfg.get("green_attrs") or []),
            "blue_attrs": list(cfg.get("blue_attrs") or []),
        }
    return roles


def _apply_roles(roles: dict) -> None:
    for role_id, overlay in roles.items():
        if role_id not in pc.all_positions or not isinstance(overlay, dict):
            continue
        _apply_lists(
            pc.all_positions[role_id],
            overlay.get("key_attrs") or [],
            overlay.get("green_attrs") or [],
            overlay.get("blue_attrs") or [],
        )


def _write_pack(pack_id: str, name: str, roles: dict) -> None:
    _atomic_write(_pack_path(pack_id), {"name": name, "roles": roles})


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


def _migrate_legacy() -> None:
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    if not LEGACY_OVERRIDE_PATH.exists() or _pack_path(WORKING).exists():
        return
    name, roles = _roles_from_payload(_read_json(LEGACY_OVERRIDE_PATH))
    if not roles:
        return
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


def ensure_loaded() -> None:
    """Snapshot Python defaults, then load the last selected pack."""
    global _DEFAULTS, _LOADED, _ACTIVE
    if _LOADED:
        return
    _DEFAULTS = copy.deepcopy(pc.all_positions)
    _LOADED = True
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
    if role_phase(role_id) == "GK":
        return GK_ATTR_GROUPS
    return OUTFIELD_ATTR_GROUPS


def attr_tier(cfg: dict, attr: str) -> str:
    if attr in (cfg.get("key_attrs") or []):
        return "key"
    if attr in (cfg.get("green_attrs") or []):
        return "green"
    if attr in (cfg.get("blue_attrs") or []):
        return "blue"
    return "none"


def is_modified(role_id: str) -> bool:
    ensure_loaded()
    default = (_DEFAULTS or {}).get(role_id)
    if not default or role_id not in pc.all_positions:
        return False
    cfg = pc.all_positions[role_id]
    return (
        set(cfg.get("key_attrs") or []) != set(default.get("key_attrs") or [])
        or set(cfg.get("green_attrs") or []) != set(default.get("green_attrs") or [])
        or set(cfg.get("blue_attrs") or []) != set(default.get("blue_attrs") or [])
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
            _name, roles = _roles_from_payload(_read_json(path))
            _apply_roles(roles)
        else:
            chosen = BUILTIN
    if persist:
        _write_active_id(chosen)
    else:
        global _ACTIVE
        _ACTIVE = chosen
    return chosen


def persist_live() -> str:
    """Write the live weights to the active pack. Copy-on-write from builtin."""
    ensure_loaded()
    pack_id = _ACTIVE or BUILTIN
    if pack_id == BUILTIN:
        pack_id = WORKING
        name = "Working copy"
    else:
        name = _pack_label(pack_id, pack_id)
    _write_pack(pack_id, name, snapshot())
    _write_active_id(pack_id)
    return pack_id


def save_pack_as(name: str | None) -> dict:
    ensure_loaded()
    label = (name or "").strip() or f"Config {datetime.now().strftime('%Y-%m-%d %H%M')}"
    pack_id = _unique_slug(label)
    _write_pack(pack_id, label, snapshot())
    _write_active_id(pack_id)
    return {"id": pack_id, "name": label}


def cycle_attr(role_id: str, attr: str) -> str:
    """Promote one attribute through Off → Key → Green → Blue and persist."""
    ensure_loaded()
    if role_id not in pc.all_positions or attr not in ATTR_LABELS:
        return "none"
    cfg = pc.all_positions[role_id]
    nxt = NEXT_TIER[attr_tier(cfg, attr)]
    key_attrs, green_attrs, blue_attrs = _attr_lists(cfg)
    key_attrs = [item for item in key_attrs if item != attr]
    green_attrs = [item for item in green_attrs if item != attr]
    blue_attrs = [item for item in blue_attrs if item != attr]
    if nxt == "key":
        key_attrs.append(attr)
    elif nxt == "green":
        green_attrs.append(attr)
    elif nxt == "blue":
        blue_attrs.append(attr)
    _apply_lists(cfg, key_attrs, green_attrs, blue_attrs)
    persist_live()
    return nxt


def reset_role(role_id: str) -> None:
    ensure_loaded()
    if not _DEFAULTS or role_id not in _DEFAULTS:
        return
    pc.all_positions[role_id] = copy.deepcopy(_DEFAULTS[role_id])
    if _ACTIVE != BUILTIN:
        persist_live()


def reset_all() -> None:
    ensure_loaded()
    _restore_defaults()
    if _ACTIVE != BUILTIN:
        persist_live()
