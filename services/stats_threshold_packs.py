"""Named percentile-threshold packs for Player stats.

Built-in pack is ``MustermannFM percentiles`` (from ``stats_benchmarks.json``).
Named packs live in ``config/settings/stats_thresholds/packs/``. Edits to the
built-in pack are stored in ``default-overrides.json``.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from config.paths import (
    STATS_THRESHOLDS_ACTIVE_PATH,
    STATS_THRESHOLDS_DEFAULTS_PATH,
    STATS_THRESHOLDS_PACKS_DIR,
)

PACKS_DIR = STATS_THRESHOLDS_PACKS_DIR
ACTIVE_PATH = STATS_THRESHOLDS_ACTIVE_PATH
DEFAULT_OVERRIDES_PATH = STATS_THRESHOLDS_DEFAULTS_PATH

BUILTIN = "mustermann-fm"
BUILTIN_NAME = "MustermannFM percentiles"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def builtin_thresholds() -> dict[str, Any]:
    """MustermannFM cut-points from the shipped benchmarks file."""
    from scoring.stats_scorer import benchmarks

    return copy.deepcopy(benchmarks()["benchmarks"])


def _valid_threshold_row(value) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    out: list[float] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            return None
        if number != number:
            return None
        out.append(number)
    return out


def normalize_thresholds(raw=None) -> dict[str, Any]:
    """Merge optional overrides onto the MustermannFM benchmark tree.

    Extra metrics present in the pack (and defined in ``metric_defs``) are kept
    so packs like FM Stag can introduce additional statistics.
    """
    from scoring.stats_scorer import metric_defs

    base = builtin_thresholds()
    if not isinstance(raw, dict) or not raw:
        return base
    # Allow either a bare tree or a pack payload with a nested ``thresholds`` key.
    src_root = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else raw
    known = set(metric_defs())
    for group, cats in base.items():
        src_group = src_root.get(group)
        if not isinstance(src_group, dict):
            continue
        for cat, metrics in cats.items():
            src_cat = src_group.get(cat)
            if not isinstance(src_cat, dict):
                continue
            for metric_id in list(metrics.keys()):
                parsed = _valid_threshold_row(src_cat.get(metric_id))
                if parsed is not None:
                    metrics[metric_id] = parsed
            for metric_id, values in src_cat.items():
                if metric_id in metrics or metric_id not in known:
                    continue
                parsed = _valid_threshold_row(values)
                if parsed is not None:
                    metrics[metric_id] = parsed
    return base


def thresholds_differ(tree: dict[str, Any] | None) -> bool:
    return normalize_thresholds(tree) != builtin_thresholds()


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug or "thresholds"


def _unique_id(name: str) -> str:
    base = _slug(name)
    candidate = base
    index = 2
    while candidate == BUILTIN or _pack_path(candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _pack_path(pack_id: str) -> Path:
    return PACKS_DIR / f"{pack_id}.json"


def is_builtin(pack_id: str | None) -> bool:
    return (pack_id or BUILTIN) == BUILTIN


def has_default_overrides() -> bool:
    return DEFAULT_OVERRIDES_PATH.exists()


def clear_default_overrides() -> None:
    if DEFAULT_OVERRIDES_PATH.exists():
        DEFAULT_OVERRIDES_PATH.unlink()


def _active_id() -> str:
    pack_id = str(_read_json(ACTIVE_PATH).get("id") or BUILTIN)
    if pack_id != BUILTIN and not _pack_path(pack_id).exists():
        return BUILTIN
    return pack_id


def _set_active(pack_id: str) -> None:
    _write_json(ACTIVE_PATH, {"id": pack_id})


def active_id() -> str:
    return _active_id()


def normalize_pack(
    raw=None, *, pack_id: str | None = None, name: str | None = None
) -> dict[str, Any]:
    raw = raw or {}
    chosen = pack_id or raw.get("id") or BUILTIN
    label = name if name is not None else raw.get("name")
    if not label:
        label = BUILTIN_NAME if chosen == BUILTIN else chosen
    tree_src = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else raw
    return {
        "id": chosen,
        "name": label,
        "thresholds": normalize_thresholds(tree_src),
    }


def _builtin_pack() -> dict[str, Any]:
    base = {
        "id": BUILTIN,
        "name": BUILTIN_NAME,
        "thresholds": builtin_thresholds(),
    }
    overrides = _read_json(DEFAULT_OVERRIDES_PATH)
    if not overrides:
        return base
    tree = overrides.get("thresholds") if isinstance(overrides.get("thresholds"), dict) else overrides
    return normalize_pack(
        {"id": BUILTIN, "name": BUILTIN_NAME, "thresholds": tree},
        pack_id=BUILTIN,
        name=BUILTIN_NAME,
    )


def _pack_from_file(pack_id: str) -> dict[str, Any]:
    if pack_id == BUILTIN:
        return _builtin_pack()
    path = _pack_path(pack_id)
    if not path.exists():
        return normalize_pack({}, pack_id=BUILTIN, name=BUILTIN_NAME)
    payload = _read_json(path)
    return normalize_pack(payload, pack_id=pack_id, name=payload.get("name") or pack_id)


def read_pack(pack_id: str | None = None) -> dict[str, Any]:
    return _pack_from_file(pack_id or _active_id())


def pack_options() -> list[dict]:
    default_label = (
        f"{BUILTIN_NAME} (customized)"
        if has_default_overrides()
        else BUILTIN_NAME
    )
    options = [{"label": default_label, "value": BUILTIN}]
    if not PACKS_DIR.exists():
        return options
    for path in sorted(PACKS_DIR.glob("*.json")):
        payload = _read_json(path)
        label = payload.get("name") or path.stem
        options.append({"label": label, "value": path.stem})
    return options


def load(pack_id: str | None = None) -> dict[str, Any]:
    chosen = pack_id or _active_id()
    pack = _pack_from_file(chosen)
    if pack_id:
        _set_active(pack["id"] if chosen != BUILTIN else BUILTIN)
    return pack


def save(raw, pack_id: str | None = None) -> dict[str, Any]:
    current = pack_id or raw.get("id") or _active_id()
    if current == BUILTIN:
        pack = normalize_pack(raw, pack_id=BUILTIN, name=BUILTIN_NAME)
        pack["id"] = BUILTIN
        pack["name"] = BUILTIN_NAME
        if thresholds_differ(pack["thresholds"]):
            _write_json(
                DEFAULT_OVERRIDES_PATH,
                {"thresholds": pack["thresholds"]},
            )
        else:
            clear_default_overrides()
        _set_active(BUILTIN)
        return pack
    pack = normalize_pack(raw, pack_id=current, name=raw.get("name"))
    pack["id"] = current
    _write_json(_pack_path(current), pack)
    _set_active(current)
    return pack


def create_pack(name: str, raw) -> dict[str, Any]:
    label = str(name or "").strip() or "Percentiles"
    pack_id = _unique_id(label)
    pack = normalize_pack(raw, pack_id=pack_id, name=label)
    pack["id"] = pack_id
    pack["name"] = label
    _write_json(_pack_path(pack_id), pack)
    _set_active(pack_id)
    return pack


def load_tree(pack_id: str | None = None) -> dict[str, Any]:
    """Active (or chosen) threshold cut-point tree for banding."""
    return load(pack_id)["thresholds"]
