"""Classify FM Personality labels into scouting tiers for table/modal highlights.

Tiers follow the Steam Community personality guide, with plain display names
(Excellent → Poor) instead of the guide’s informal section titles.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

DATA_PATH = Path(__file__).resolve().parents[1] / "config" / "personality_tiers.json"

PersonalityTierId = Literal[
    "exemplary",
    "commendable",
    "acceptable",
    "unpredictable",
    "formative",
    "unsuitable",
    "",
]

TIER_ORDER: tuple[PersonalityTierId, ...] = (
    "exemplary",
    "commendable",
    "acceptable",
    "unpredictable",
    "formative",
    "unsuitable",
)

# Aliases that map onto config personality names / combined labels.
_ALIASES: dict[str, str] = {
    "devoted": "Devoted / Very Loyal",
    "very loyal": "Devoted / Very Loyal",
    "devoted / very loyal": "Devoted / Very Loyal",
    "low self belief": "Low Self-Belief",
    "low self-belief": "Low Self-Belief",
    "light hearted": "Light-Hearted",
    "iron-willed": "Iron Willed",
    "ironwilled": "Iron Willed",
}


def _norm_key(label: str) -> str:
    text = (label or "").strip().lower()
    text = re.sub(r"[^\x00-\x7f]+", " ", text)
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text)
    text = re.sub(r"[^\w\s/\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _tier_meta() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for tier in _data().get("tiers") or []:
        tid = str(tier.get("id") or "").strip()
        if not tid:
            continue
        out[tid] = {
            "id": tid,
            "label": str(tier.get("label") or tid.title()),
            "guide_section": str(tier.get("guide_section") or ""),
        }
    return out


@lru_cache(maxsize=1)
def _personality_to_tier() -> dict[str, PersonalityTierId]:
    mapping: dict[str, PersonalityTierId] = {}
    for tier in _data().get("tiers") or []:
        tid = str(tier.get("id") or "").strip()
        if tid not in TIER_ORDER:
            continue
        for name in tier.get("personalities") or []:
            key = _norm_key(str(name))
            if key:
                mapping[key] = tid  # type: ignore[assignment]
    for alias, canon in _ALIASES.items():
        canon_key = _norm_key(canon)
        if canon_key in mapping:
            mapping[alias] = mapping[canon_key]
    return mapping


def tier_defs() -> list[dict[str, str]]:
    """Ordered tier metadata for settings UI / legends."""
    meta = _tier_meta()
    return [dict(meta[tid]) for tid in TIER_ORDER if tid in meta]


def tier_label(tier_id: str | None) -> str:
    if not tier_id:
        return ""
    return (_tier_meta().get(str(tier_id)) or {}).get("label") or str(tier_id)


def classify_personality(label: str | None) -> PersonalityTierId:
    """Return tier id for a Personality cell, or '' when unknown."""
    raw = (label or "").strip()
    if not raw or raw in {"-", "—"}:
        return ""
    key = _norm_key(raw)
    if not key:
        return ""
    hit = _personality_to_tier().get(key)
    if hit:
        return hit
    if key in _ALIASES:
        return _personality_to_tier().get(_norm_key(_ALIASES[key]), "")
    return ""


def apply_personality_tier(row: dict[str, Any]) -> None:
    """Set ``PersonalityTier`` on a table row from the Personality column."""
    row["PersonalityTier"] = classify_personality(row.get("Personality"))


def personality_tier_style(
    tier_id: str | None,
    colors: dict[str, dict[str, str]] | None,
) -> dict[str, str] | None:
    """Inline bg/color for a tier using settings colors."""
    if not tier_id or not isinstance(colors, dict):
        return None
    entry = colors.get(str(tier_id)) or {}
    bg = str(entry.get("bg") or "").strip()
    fg = str(entry.get("fg") or "").strip()
    if not bg and not fg:
        return None
    style: dict[str, str] = {"fontWeight": "700"}
    if bg:
        style["backgroundColor"] = bg
    if fg:
        style["color"] = fg
    return style
