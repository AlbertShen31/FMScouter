"""Estimate hidden personality-attribute ranges from Personality + Media Handling.

Ranges come from the FM Scout guide (Personality Descriptions / Media Handling
Style Descriptions). Combined estimate = intersection of both sources. Attributes
not constrained by either source stay 1–20.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parents[1] / "config" / "personality_ranges.json"

HIDDEN_ATTRS = (
    "Ambition",
    "Controversy",
    "Loyalty",
    "Pressure",
    "Professionalism",
    "Sportsmanship",
    "Temperament",
)
VISIBLE_ATTRS = ("Determination", "Leadership")
FULL_RANGE = (1, 20)

# From the FM Scout guide: higher is desirable except Controversy (mostly
# negative effects). Mid averages (~1–20) read as yellow.
ATTR_POLARITY = {
    "Ambition": 1,
    "Controversy": -1,
    "Loyalty": 1,
    "Pressure": 1,
    "Professionalism": 1,
    "Sportsmanship": 1,
    "Temperament": 1,
}

# Concise high/low meanings from the FM Scout personality guide.
ATTR_INFO: dict[str, dict[str, str]] = {
    "Ambition": {
        "definition": "How much the player wants to achieve success or break new ground.",
        "high": (
            "Pushes for trophies and progress; better training growth and tutoring. "
            "Also demands bigger contracts and higher-reputation clubs."
        ),
        "low": "More content with the current level; less driven to force moves or wage rises.",
    },
    "Controversy": {
        "definition": "How outspoken, brash, or feisty the player is.",
        "high": (
            "More likely to criticize the manager, react badly in talks/media, "
            "and ignore guidance on roles, training, traits, or tutoring."
        ),
        "low": "Keeps a lower profile with the media and staff; easier to manage publicly.",
    },
    "Loyalty": {
        "definition": "How strong the player’s allegiance is to their current club.",
        "high": (
            "More likely to stay, accept lower wages, and back transfer decisions — "
            "but harder to buy away from their club."
        ),
        "low": "More open to leaving; easier to unsettle or recruit from elsewhere.",
    },
    "Pressure": {
        "definition": "How well the player copes with demanding or high-pressure situations.",
        "high": (
            "Less rattled by pressure, criticism, or bad mental states; "
            "steadier body language and big-match performances."
        ),
        "low": "Needs a lighter touch; more likely to struggle when the heat is on.",
    },
    "Professionalism": {
        "definition": "Overall attitude to career, matches, and training.",
        "high": (
            "Works hard in training, progresses well, recovers and declines later, "
            "and reacts better to management and tutoring."
        ),
        "low": "Weaker training habits and attitude; more complaints and poorer development.",
    },
    "Sportsmanship": {
        "definition": "How ethical or sportsmanlike the player is.",
        "high": (
            "Respects opponents and supports decisions like tutoring — "
            "but may avoid the “dirty work” that wins tight games."
        ),
        "low": "More willing to bend ethics for an edge; less “sporting” in conduct.",
    },
    "Temperament": {
        "definition": "How disciplined the player stays when things go against them.",
        "high": (
            "Less frustration or aggression when struggling or decisions go against them; "
            "handles criticism and discipline better."
        ),
        "low": "Volatile under adversity; needs careful handling and is harder to discipline.",
    },
}

# Graduated red (1) → yellow (10.5) → green (20) — bright for dark UI.
_COLOR_RED = (255, 92, 92)
_COLOR_YELLOW = (255, 210, 64)
_COLOR_GREEN = (64, 220, 120)

# Guide / export label aliases → canonical keys in the JSON.
_PERSONALITY_ALIASES = {
    "very ambitions": "Very Ambitious",
    "devoted": "Devoted / Very Loyal",
    "very loyal": "Devoted / Very Loyal",
    "devoted / very loyal": "Devoted / Very Loyal",
}
_MEDIA_ALIASES = {
    "level headed": "Level-Headed",
    "level-headed": "Level-Headed",
    "media friendly": "Media-Friendly",
    "media-friendly": "Media-Friendly",
    "short tempered": "Short-Tempered",
    "short-tempered": "Short-Tempered",
}


def _norm_key(text: str) -> str:
    text = (text or "").strip().casefold()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _lookup(table: dict[str, dict], label: str, aliases: dict[str, str]) -> tuple[str | None, dict]:
    raw = (label or "").strip()
    if not raw:
        return None, {}
    key = _norm_key(raw)
    if key in aliases:
        name = aliases[key]
        return name, dict(table.get(name) or {})
    for name, ranges in table.items():
        if _norm_key(name) == key:
            return name, dict(ranges)
    # Strip parenthetical notes from CSV/guide variants.
    bare = re.sub(r"\s*\([^)]*\)\s*", "", raw).strip()
    if bare and bare != raw:
        return _lookup(table, bare, aliases)
    return None, {}


def resolve_personality(label: str) -> tuple[str | None, dict[str, list[int]]]:
    return _lookup(_data()["personalities"], label, _PERSONALITY_ALIASES)


def resolve_media_handling(label: str) -> tuple[str | None, dict[str, list[int]]]:
    return _lookup(_data()["media_handling"], label, _MEDIA_ALIASES)


def _as_range(value) -> tuple[int, int] | None:
    if not value or len(value) != 2:
        return None
    lo, hi = int(value[0]), int(value[1])
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def intersect_ranges(*ranges: tuple[int, int] | None) -> tuple[int, int] | None:
    """Intersect inclusive 1–20 ranges. None means unconstrained. Empty → None."""
    lo, hi = FULL_RANGE
    constrained = False
    for item in ranges:
        if item is None:
            continue
        constrained = True
        lo = max(lo, item[0])
        hi = min(hi, item[1])
        if lo > hi:
            return None
    if not constrained:
        return FULL_RANGE
    return lo, hi


def format_range(bounds: tuple[int, int] | None) -> str:
    if bounds is None:
        return "—"
    lo, hi = bounds
    return str(lo) if lo == hi else f"{lo}–{hi}"


def attr_help(attr: str) -> dict[str, str] | None:
    """Definition / high / low copy for tooltips, or None if unknown."""
    info = ATTR_INFO.get(attr)
    return dict(info) if info else None


def attr_help_text(attr: str) -> str:
    """Plain-text tooltip: definition plus high/low score meaning."""
    info = ATTR_INFO.get(attr)
    if not info:
        return attr
    return (
        f"{info['definition']}\n\n"
        f"High: {info['high']}\n\n"
        f"Low: {info['low']}"
    )


def _lerp_rgb(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _rgb_css(rgb: tuple[int, int, int]) -> str:
    return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"


def range_score(attr: str, bounds: tuple[int, int] | None) -> float | None:
    """Desirability score 1–20 from the range midpoint (Controversy inverted)."""
    if bounds is None:
        return None
    lo, hi = bounds
    avg = (lo + hi) / 2.0
    polarity = ATTR_POLARITY.get(attr, 1)
    if polarity < 0:
        avg = 21.0 - avg
    return max(1.0, min(20.0, avg))


def range_color(attr: str, bounds: tuple[int, int] | None) -> str | None:
    """CSS color for a range: 1 red → ~10.5 yellow → 20 bright green."""
    score = range_score(attr, bounds)
    if score is None:
        return None
    # Map 1..20 onto red→yellow (1..10.5) then yellow→green (10.5..20).
    mid = 10.5
    if score <= mid:
        t = (score - 1.0) / (mid - 1.0)
        return _rgb_css(_lerp_rgb(_COLOR_RED, _COLOR_YELLOW, t))
    t = (score - mid) / (20.0 - mid)
    return _rgb_css(_lerp_rgb(_COLOR_YELLOW, _COLOR_GREEN, t))


def estimate_hidden_ranges(
    personality: str | None,
    media_handling: str | None,
    *,
    determination: int | None = None,
) -> dict[str, Any]:
    """Combine personality + media handling into per-attribute estimated ranges.

    When Determination is known from the CSV, it must fall inside any personality
    Determination range; otherwise the personality match is marked inconsistent.
    """
    pers_name, pers_ranges = resolve_personality(personality or "")
    media_name, media_ranges = resolve_media_handling(media_handling or "")

    attrs: dict[str, dict[str, Any]] = {}
    for attr in HIDDEN_ATTRS:
        combined = intersect_ranges(
            _as_range(pers_ranges.get(attr)),
            _as_range(media_ranges.get(attr)),
        )
        attrs[attr] = {
            "range": combined,
            "label": format_range(combined),
            "from_personality": format_range(_as_range(pers_ranges.get(attr)))
            if attr in pers_ranges
            else None,
            "from_media": format_range(_as_range(media_ranges.get(attr)))
            if attr in media_ranges
            else None,
            "known": False,
        }

    visible: dict[str, dict[str, Any]] = {}
    for attr in VISIBLE_ATTRS:
        bounds = intersect_ranges(
            _as_range(pers_ranges.get(attr)),
            _as_range(media_ranges.get(attr)),
        )
        visible[attr] = {
            "range": bounds if attr in pers_ranges or attr in media_ranges else None,
            "label": format_range(bounds)
            if attr in pers_ranges or attr in media_ranges
            else None,
        }

    det_ok = True
    det_expected = _as_range(pers_ranges.get("Determination"))
    if determination is not None and det_expected is not None:
        det_ok = det_expected[0] <= determination <= det_expected[1]

    return {
        "personality": pers_name,
        "media_handling": media_name,
        "matched": bool(pers_name or media_name),
        "determination_ok": det_ok,
        "determination": determination,
        "hidden": attrs,
        "visible": visible,
    }
