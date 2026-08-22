"""Persisted UI thresholds and colors for Role scores and Player stats.

Named JSON packs live in `config/settings/packs/`. Default uses built-in
values; edits are saved to `default-overrides.json`. Named packs save to
their own files. New creates a named copy.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from config.paths import (
    SETTINGS_ACTIVE_PATH,
    SETTINGS_DEFAULTS_PATH,
    SETTINGS_PACKS_DIR,
)

PACKS_DIR = SETTINGS_PACKS_DIR
ACTIVE_PATH = SETTINGS_ACTIVE_PATH
DEFAULT_OVERRIDES_PATH = SETTINGS_DEFAULTS_PATH

BUILTIN = "default"

BAND_KEYS = ("elite", "good", "ok", "poor")
COLOR_PARTS = ("bg", "fg", "bar")

DEFAULTS: dict[str, Any] = {
    "id": BUILTIN,
    "name": "Default",
    "age_tiers": [21, 25, 30],
    "bands": {"elite": 14.0, "good": 12.0, "ok": 10.0},
    # Left / Right default to Very Strong (6); Both to Fairly Strong (4).
    "foot_thresholds": {"left": 6, "both": 4, "right": 6},
    "hist_edges": [10.0, 11.0, 12.0, 13.0, 14.0],
    "colors": {
        "elite": {"bg": "#dcfce7", "fg": "#15803d", "bar": "#22c55e"},
        "good": {"bg": "#dbeafe", "fg": "#1d4ed8", "bar": "#3b82f6"},
        "ok": {"bg": "#fef3c7", "fg": "#b45309", "bar": "#f59e0b"},
        "poor": {"bg": "#fee2e2", "fg": "#b91c1c", "bar": "#ef4444"},
    },
    # Filled from stats_benchmarks.json on normalize; empty means built-in.
    "stats_thresholds": {},
}


def _as_float(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


def _clamp_score(value, default: float) -> float:
    return round(max(0.0, min(20.0, _as_float(value, default))) * 2) / 2


def format_cut(number: float) -> str:
    number = _clamp_score(number, 0.0)
    return str(int(number)) if number == int(number) else f"{number:.1f}"


def format_age(number) -> str:
    return str(int(number))


def format_list(values: list, *, kind: str = "score") -> str:
    if kind == "age":
        return ", ".join(format_age(value) for value in values)
    return ", ".join(format_cut(value) for value in values)


def parse_number_list(text, *, integer: bool = False) -> list[float]:
    values: list[float] = []
    seen: set[float] = set()
    if isinstance(text, (list, tuple)):
        parts = [str(item) for item in text]
    else:
        parts = str(text or "").replace(";", ",").split(",")
    for part in parts:
        token = part.strip()
        if not token:
            continue
        try:
            number = float(token)
        except ValueError:
            continue
        if number != number:
            continue
        number = int(round(number)) if integer else round(number * 2) / 2
        if number in seen:
            continue
        seen.add(number)
        values.append(float(number))
    values.sort()
    return values


def normalize_foot_threshold(value, default: int = 4) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(1, min(6, number))


def normalize_foot_thresholds(raw=None) -> dict[str, int]:
    """Normalize left/both/right thresholds; migrate legacy `foot_threshold` → both."""
    raw = raw or {}
    defaults = DEFAULTS["foot_thresholds"]
    src = raw.get("foot_thresholds") if isinstance(raw.get("foot_thresholds"), dict) else {}
    legacy = raw.get("foot_threshold")
    both_fallback = legacy if legacy is not None else defaults["both"]
    return {
        "left": normalize_foot_threshold(src.get("left"), defaults["left"]),
        "both": normalize_foot_threshold(
            src.get("both", both_fallback), defaults["both"]
        ),
        "right": normalize_foot_threshold(src.get("right"), defaults["right"]),
    }


def parse_score_floor(value) -> float:
    if value in (None, "", "any", "Any"):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number <= 0:
        return 0.0
    return number


def _hex_color(value, default: str) -> str:
    text = str(value or "").strip()
    if text.startswith("#") and len(text) == 7:
        body = text[1:]
        if all(ch in "0123456789abcdefABCDEF" for ch in body):
            return "#" + body.lower()
    if text.startswith("#") and len(text) == 4:
        body = text[1:]
        if all(ch in "0123456789abcdefABCDEF" for ch in body):
            return "#" + "".join(ch * 2 for ch in body.lower())
    return default


def default_stats_thresholds() -> dict[str, Any]:
    """Built-in MustermannFM cut-points copied from stats_benchmarks.json."""
    from stats_scorer import benchmarks

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


def normalize_stats_thresholds(raw=None) -> dict[str, Any]:
    """Merge optional overrides onto the built-in benchmark threshold tree."""
    base = default_stats_thresholds()
    if not isinstance(raw, dict) or not raw:
        return base
    for group, cats in base.items():
        src_group = raw.get(group)
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
    return base


def stats_thresholds_differ(tree: dict[str, Any] | None) -> bool:
    """True when `tree` differs from the built-in benchmark cut-points."""
    current = normalize_stats_thresholds(tree)
    return current != default_stats_thresholds()


def normalize_bands(raw, edited: str | None = None) -> dict[str, float]:
    raw = raw or {}
    elite = _clamp_score(raw.get("elite"), DEFAULTS["bands"]["elite"])
    good = _clamp_score(raw.get("good"), DEFAULTS["bands"]["good"])
    ok = _clamp_score(raw.get("ok"), DEFAULTS["bands"]["ok"])
    if edited == "elite":
        if good >= elite:
            good = max(0.5, elite - 0.5)
        if ok >= good:
            ok = max(0.0, good - 0.5)
    elif edited == "ok":
        if ok >= good:
            good = min(19.5, ok + 0.5)
        if good >= elite:
            elite = min(20.0, good + 0.5)
    else:
        if good >= elite:
            elite = min(20.0, good + 0.5)
        if ok >= good:
            ok = max(0.0, good - 0.5)
    ok = min(ok, 19.0)
    good = min(max(good, ok + 0.5), 19.5)
    elite = min(max(elite, good + 0.5), 20.0)
    return {"elite": elite, "good": good, "ok": max(0.0, ok)}


def normalize(raw=None, *, pack_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    raw = raw or {}
    ages = parse_number_list(raw.get("age_tiers", DEFAULTS["age_tiers"]), integer=True)
    ages = [int(age) for age in ages if 1 <= age <= 99]
    if not ages:
        ages = list(DEFAULTS["age_tiers"])

    edges = parse_number_list(raw.get("hist_edges", DEFAULTS["hist_edges"]))
    edges = [value for value in edges if 0 < value <= 20]
    if not edges:
        edges = list(DEFAULTS["hist_edges"])

    colors: dict[str, dict[str, str]] = {}
    raw_colors = raw.get("colors") or {}
    for band in BAND_KEYS:
        src = raw_colors.get(band) or {}
        fallback = DEFAULTS["colors"][band]
        colors[band] = {
            part: _hex_color(src.get(part), fallback[part]) for part in COLOR_PARTS
        }

    pack_id = pack_id or raw.get("id") or BUILTIN
    label = name if name is not None else raw.get("name") or (
        "Default" if pack_id == BUILTIN else pack_id
    )
    return {
        "id": pack_id,
        "name": label,
        "age_tiers": ages,
        "bands": normalize_bands(raw.get("bands") or raw),
        "foot_thresholds": normalize_foot_thresholds(raw),
        "hist_edges": edges,
        "colors": colors,
        "stats_thresholds": normalize_stats_thresholds(raw.get("stats_thresholds")),
    }


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug or "settings"


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


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _active_id() -> str:
    pack_id = str(_read_json(ACTIVE_PATH).get("id") or BUILTIN)
    if pack_id != BUILTIN and not _pack_path(pack_id).exists():
        return BUILTIN
    return pack_id


def _set_active(pack_id: str) -> None:
    _write_json(ACTIVE_PATH, {"id": pack_id})


def _default_settings() -> dict[str, Any]:
    base = copy.deepcopy(DEFAULTS)
    overrides = _read_json(DEFAULT_OVERRIDES_PATH)
    if not overrides:
        return base
    merged = {**base, **overrides}
    if overrides.get("bands"):
        merged["bands"] = {**base["bands"], **overrides["bands"]}
    if overrides.get("foot_thresholds") or overrides.get("foot_threshold") is not None:
        merged["foot_thresholds"] = {
            **base["foot_thresholds"],
            **(overrides.get("foot_thresholds") or {}),
        }
        if overrides.get("foot_threshold") is not None and "both" not in (
            overrides.get("foot_thresholds") or {}
        ):
            merged["foot_thresholds"]["both"] = overrides["foot_threshold"]
    if overrides.get("colors"):
        merged["colors"] = {
            band: {**base["colors"].get(band, {}), **(overrides["colors"].get(band) or {})}
            for band in BAND_KEYS
        }
    if overrides.get("stats_thresholds"):
        merged["stats_thresholds"] = overrides["stats_thresholds"]
    return normalize(merged, pack_id=BUILTIN, name="Default")


def has_default_overrides() -> bool:
    return DEFAULT_OVERRIDES_PATH.exists()


def clear_default_overrides() -> None:
    if DEFAULT_OVERRIDES_PATH.exists():
        DEFAULT_OVERRIDES_PATH.unlink()


def _pack_from_file(pack_id: str) -> dict[str, Any]:
    if pack_id == BUILTIN:
        return _default_settings()
    path = _pack_path(pack_id)
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    payload = _read_json(path)
    return normalize(payload, pack_id=pack_id, name=payload.get("name") or pack_id)


def read_pack(pack_id: str | None = None) -> dict[str, Any]:
    return _pack_from_file(pack_id or _active_id())


def pack_options() -> list[dict]:
    default_label = "Default (customized)" if has_default_overrides() else "Default"
    options = [{"label": default_label, "value": BUILTIN}]
    if not PACKS_DIR.exists():
        return options
    for path in sorted(PACKS_DIR.glob("*.json")):
        payload = _read_json(path)
        label = payload.get("name") or path.stem
        options.append({"label": label, "value": path.stem})
    return options


def active_id() -> str:
    return _active_id()


def load(pack_id: str | None = None) -> dict[str, Any]:
    chosen = pack_id or _active_id()
    settings = _pack_from_file(chosen)
    if pack_id:
        _set_active(settings["id"] if chosen != BUILTIN else BUILTIN)
    return settings


def save(raw, pack_id: str | None = None) -> dict[str, Any]:
    current = pack_id or raw.get("id") or _active_id()
    if current == BUILTIN:
        settings = normalize(raw, pack_id=BUILTIN, name="Default")
        settings["id"] = BUILTIN
        settings["name"] = "Default"
        payload = {
            "age_tiers": settings["age_tiers"],
            "bands": settings["bands"],
            "foot_thresholds": settings["foot_thresholds"],
            "hist_edges": settings["hist_edges"],
            "colors": settings["colors"],
        }
        if stats_thresholds_differ(settings.get("stats_thresholds")):
            payload["stats_thresholds"] = settings["stats_thresholds"]
        _write_json(DEFAULT_OVERRIDES_PATH, payload)
        _set_active(BUILTIN)
        return settings
    settings = normalize(raw, pack_id=current, name=raw.get("name"))
    settings["id"] = current
    _write_json(_pack_path(current), settings)
    _set_active(current)
    return settings


def create_pack(name: str, raw) -> dict[str, Any]:
    label = str(name or "").strip() or "Settings"
    pack_id = _unique_id(label)
    settings = normalize(raw, pack_id=pack_id, name=label)
    settings["id"] = pack_id
    settings["name"] = label
    _write_json(_pack_path(pack_id), settings)
    _set_active(pack_id)
    return settings


def is_builtin(pack_id: str | None) -> bool:
    return (pack_id or BUILTIN) == BUILTIN


def age_options(settings=None) -> list[dict]:
    settings = normalize(settings)
    options = [{"label": "Any", "value": "99"}]
    for age in settings["age_tiers"]:
        if age != 99:
            options.append({"label": str(age), "value": str(int(age))})
    return options


def clamp_choice(value, options: list[dict], fallback):
    allowed = {str(opt["value"]) for opt in options}
    if value is not None and str(value) in allowed:
        return str(value)
    try:
        number = str(int(float(value)))
    except (TypeError, ValueError):
        return str(fallback)
    if number in allowed:
        return number
    return str(fallback)


def hist_bins(settings=None) -> list[tuple[str, float, float]]:
    settings = normalize(settings)
    edges = settings["hist_edges"]
    bins = [(f"<{format_cut(edges[0])}", 0.0, float(edges[0]))]
    for lo, hi in zip(edges, edges[1:]):
        bins.append((f"{format_cut(lo)}–{format_cut(hi)}", float(lo), float(hi)))
    last = edges[-1]
    bins.append((f"{format_cut(last)}+", float(last), 99.0))
    return bins


def hist_preview(settings=None) -> str:
    return " · ".join(label for label, _lo, _hi in hist_bins(settings))


def score_colors(settings=None) -> dict[str, tuple[str, str]]:
    settings = normalize(settings)
    return {
        band: (settings["colors"][band]["bg"], settings["colors"][band]["fg"])
        for band in BAND_KEYS
    }


def css_vars(settings=None) -> dict[str, str]:
    settings = normalize(settings)
    vars_: dict[str, str] = {}
    for band in BAND_KEYS:
        colors = settings["colors"][band]
        vars_[f"--band-{band}-bg"] = colors["bg"]
        vars_[f"--band-{band}-fg"] = colors["fg"]
        vars_[f"--band-{band}-bar"] = colors["bar"]
    return vars_
