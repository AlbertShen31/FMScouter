"""Named formations: up to 11 hybrid (IP + OOP) role slots.

JSON packs live in `config/formations/packs/`. Role scores can load a
formation into the hybrid-roles list.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from phases import phase_tone
import config.fm26_role_weight_config as pc
from config.paths import FORMATIONS_ACTIVE_PATH, FORMATIONS_PACKS_DIR
from role_scorer import normalize_combos

PACKS_DIR = FORMATIONS_PACKS_DIR
ACTIVE_PATH = FORMATIONS_ACTIVE_PATH

SCHEMA = 2
MAX_SLOTS = 11

# Display code → role group used by role_options().
SLOT_POSITIONS = (
    ("gk", "GK", "gk"),
    ("cb", "CB", "cb"),
    ("rb", "RB", "fb"),
    ("lb", "LB", "fb"),
    ("rwb", "RWB", "wb"),
    ("lwb", "LWB", "wb"),
    ("dm", "DM", "dm"),
    ("cm", "CM", "cm"),
    ("am", "AM", "am"),
    ("rm", "RM", "wm"),
    ("lm", "LM", "wm"),
    ("rw", "RW", "w"),
    ("lw", "LW", "w"),
    ("st", "ST", "st"),
)
SLOT_POSITION_IDS = {item[0] for item in SLOT_POSITIONS}
SLOT_POSITION_GROUP = {item[0]: item[2] for item in SLOT_POSITIONS}
SLOT_POSITION_LABEL = {item[0]: item[1] for item in SLOT_POSITIONS}
_LABEL_TO_POS = {item[1].upper(): item[0] for item in SLOT_POSITIONS}
_LABEL_TO_POS.update(
    {
        "RCB": "cb",
        "LCB": "cb",
        "FB": "rb",
        "WB": "rwb",
        "WM": "rm",
        "W": "rw",
        "CF": "st",
        "MC": "cm",
        "AMC": "am",
        "DMR": "dm",
        "DML": "dm",
    }
)
DEFAULT_SLOT_POSITIONS = (
    "gk",
    "rb",
    "cb",
    "cb",
    "lb",
    "dm",
    "cm",
    "am",
    "rw",
    "lw",
    "st",
)
DEFAULT_SLOT_LABELS = tuple(SLOT_POSITION_LABEL[pos] for pos in DEFAULT_SLOT_POSITIONS)


def position_options() -> list[dict]:
    return [{"label": label, "value": pos_id} for pos_id, label, _group in SLOT_POSITIONS]


def group_for_position(pos_id: str | None) -> str:
    return SLOT_POSITION_GROUP.get(str(pos_id or "").strip().lower(), "")


def role_filter_groups(ip_pos: str | None, oop_pos: str | None) -> tuple[str, str]:
    """IP group is required for filtering; missing OOP uses the IP group."""
    ip_group = group_for_position(ip_pos) or "all"
    oop_group = group_for_position(oop_pos) or ip_group
    return ip_group, oop_group


def _normalize_pos(value, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    key = text.lower()
    if key in SLOT_POSITION_IDS:
        return key
    mapped = _LABEL_TO_POS.get(text.upper())
    if mapped:
        return mapped
    return fallback


def _valid_ip(role_id: str) -> bool:
    return role_id in pc.all_positions and phase_tone(pc.all_positions[role_id].get("phase")) == "ip"


def _valid_oop(role_id: str) -> bool:
    return role_id in pc.all_positions and phase_tone(pc.all_positions[role_id].get("phase")) == "oop"


def _slot(raw, index: int) -> dict[str, str]:
    payload = raw if isinstance(raw, dict) else {}
    fallback = DEFAULT_SLOT_POSITIONS[index] if 0 <= index < MAX_SLOTS else "cm"
    ip_pos = _normalize_pos(payload.get("ip_pos") or payload.get("label"), fallback)
    oop_pos = _normalize_pos(payload.get("oop_pos"), "")
    ip = str(payload.get("ip") or "").strip()
    oop = str(payload.get("oop") or "").strip()
    if not _valid_ip(ip):
        ip = ""
    if not _valid_oop(oop):
        oop = ""
    return {
        "label": SLOT_POSITION_LABEL.get(ip_pos, ip_pos.upper()),
        "ip_pos": ip_pos,
        "oop_pos": oop_pos,
        "ip": ip,
        "oop": oop,
    }


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _pack_path(pack_id: str) -> Path:
    return PACKS_DIR / f"{pack_id}.json"


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug or "formation"


def _unique_id(name: str) -> str:
    base = _slug(name)
    candidate = base
    index = 2
    while _pack_path(candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def blank(name: str = "New formation") -> dict[str, Any]:
    return normalize({"name": name, "slots": []}, pack_id="", name=name)


def normalize(raw, pack_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    slots_raw = list(payload.get("slots") or [])
    slots = [_slot(slots_raw[i] if i < len(slots_raw) else {}, i) for i in range(MAX_SLOTS)]
    chosen_id = pack_id if pack_id is not None else str(payload.get("id") or "")
    label = name if name is not None else str(payload.get("name") or chosen_id or "New formation")
    return {
        "id": chosen_id,
        "name": label.strip() or "New formation",
        "schema": SCHEMA,
        "shape": str(payload.get("shape") or "").strip()[:40],
        "notes": str(payload.get("notes") or "").strip()[:400],
        "slots": slots,
    }


def combos_from_formation(formation) -> list[dict[str, str]]:
    formation = normalize(formation)
    return normalize_combos(
        [{"ip": slot["ip"], "oop": slot["oop"]} for slot in formation["slots"]]
    )


def roles_from_formation(formation) -> list[str]:
    roles: list[str] = []
    for item in combos_from_formation(formation):
        for role_id in (item["ip"], item["oop"]):
            if role_id not in roles:
                roles.append(role_id)
    return roles


def filled_count(formation) -> int:
    return len(combos_from_formation(formation))


def _from_file(pack_id: str) -> dict[str, Any] | None:
    path = _pack_path(pack_id)
    if not path.exists():
        return None
    payload = _read_json(path)
    return normalize(payload, pack_id=pack_id, name=payload.get("name") or pack_id)


def _active_id() -> str:
    pack_id = str(_read_json(ACTIVE_PATH).get("id") or "")
    if pack_id and _pack_path(pack_id).exists():
        return pack_id
    ids = list_ids()
    return ids[0] if ids else ""


def _set_active(pack_id: str) -> None:
    _write_json(ACTIVE_PATH, {"id": pack_id})


def list_ids() -> list[str]:
    if not PACKS_DIR.exists():
        return []
    return [path.stem for path in sorted(PACKS_DIR.glob("*.json"))]


def pack_options() -> list[dict]:
    options = []
    for pack_id in list_ids():
        formation = _from_file(pack_id)
        if not formation:
            continue
        shape = f" · {formation['shape']}" if formation.get("shape") else ""
        options.append(
            {
                "label": f"{formation['name']}{shape}",
                "value": pack_id,
            }
        )
    return options


def active_id() -> str:
    return _active_id()


def load(pack_id: str | None = None, persist: bool = True) -> dict[str, Any]:
    if pack_id:
        formation = _from_file(pack_id)
        if formation:
            if persist:
                _set_active(pack_id)
            return formation
        return blank()
    return blank()


def save(raw, pack_id: str | None = None) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    current = pack_id or payload.get("id") or ""
    if current and _pack_path(str(current)).exists():
        formation = normalize(payload, pack_id=current, name=payload.get("name"))
        formation["id"] = current
        _write_json(_pack_path(current), formation)
        _set_active(current)
        return formation
    return create(str(payload.get("name") or "New formation"), payload)


def create(name: str, raw=None) -> dict[str, Any]:
    label = str(name or "").strip() or "Formation"
    pack_id = _unique_id(label)
    formation = normalize(raw or {}, pack_id=pack_id, name=label)
    formation["id"] = pack_id
    formation["name"] = label
    _write_json(_pack_path(pack_id), formation)
    _set_active(pack_id)
    return formation


def duplicate(pack_id: str, name: str) -> dict[str, Any]:
    source = load(pack_id, persist=False)
    return create(name, source)


def delete(pack_id: str) -> dict[str, Any]:
    path = _pack_path(pack_id)
    if path.exists():
        path.unlink()
    remaining = list_ids()
    next_id = remaining[0] if remaining else ""
    _set_active(next_id)
    return load(next_id or None, persist=False)


def exists(pack_id: str | None) -> bool:
    return bool(pack_id) and _pack_path(str(pack_id)).exists()
