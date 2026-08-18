"""Persisted UI thresholds and colors for Role scores."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "config" / "ui_settings.json"

BAND_KEYS = ("elite", "good", "ok", "poor")
COLOR_PARTS = ("bg", "fg", "bar")

DEFAULTS: dict[str, Any] = {
    "age_tiers": [21, 23, 25, 27, 30, 35],
    "min_score_tiers": [11.0, 12.0, 12.5, 13.0],
    "bands": {"elite": 14.0, "good": 12.0, "ok": 10.0},
    "hist_edges": [10.0, 11.0, 12.0, 13.0, 14.0],
    "colors": {
        "elite": {"bg": "#dcfce7", "fg": "#15803d", "bar": "#22c55e"},
        "good": {"bg": "#dbeafe", "fg": "#1d4ed8", "bar": "#3b82f6"},
        "ok": {"bg": "#fef3c7", "fg": "#b45309", "bar": "#f59e0b"},
        "poor": {"bg": "#fee2e2", "fg": "#b91c1c", "bar": "#ef4444"},
    },
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


def format_list(values: list) -> str:
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


def normalize(raw=None) -> dict[str, Any]:
    raw = raw or {}
    ages = parse_number_list(raw.get("age_tiers", DEFAULTS["age_tiers"]), integer=True)
    ages = [int(age) for age in ages if 1 <= age <= 99]
    if not ages:
        ages = list(DEFAULTS["age_tiers"])

    mins = parse_number_list(raw.get("min_score_tiers", DEFAULTS["min_score_tiers"]))
    mins = [value for value in mins if 0 < value <= 20]
    if not mins:
        mins = list(DEFAULTS["min_score_tiers"])

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

    return {
        "age_tiers": ages,
        "min_score_tiers": mins,
        "bands": normalize_bands(raw.get("bands") or raw),
        "hist_edges": edges,
        "colors": colors,
    }


def load() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULTS)
    return normalize(payload)


def save(raw) -> dict[str, Any]:
    settings = normalize(raw)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings


def age_options(settings=None) -> list[dict]:
    settings = normalize(settings)
    options = [{"label": "Any", "value": 99}]
    for age in settings["age_tiers"]:
        if age != 99:
            options.append({"label": str(age), "value": int(age)})
    return options


def min_score_options(settings=None) -> list[dict]:
    settings = normalize(settings)
    options = [{"label": "Any", "value": 0}]
    for value in settings["min_score_tiers"]:
        options.append({"label": f"{format_cut(value)}+", "value": value})
    return options


def clamp_choice(value, options: list[dict], fallback):
    allowed = {opt["value"] for opt in options}
    if value in allowed:
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number in allowed:
        return number
    if int(number) in allowed:
        return int(number)
    return fallback


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
