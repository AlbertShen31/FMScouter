"""Staff role scores from FM24 Pre-Game Editor attribute weights."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "staff_weights.json"


@lru_cache(maxsize=1)
def load_staff_weights() -> dict[str, Any]:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def roles() -> list[dict[str, str]]:
    return list(load_staff_weights().get("roles") or [])


def attributes() -> list[dict[str, Any]]:
    return list(load_staff_weights().get("attributes") or [])


def attribute_map() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in attributes() if item.get("id")}


def role_weights(role_id: str) -> dict[str, int]:
    raw = (load_staff_weights().get("weights") or {}).get(role_id) or {}
    out: dict[str, int] = {}
    for attr_id, weight in raw.items():
        try:
            w = int(weight)
        except (TypeError, ValueError):
            continue
        if w > 0:
            out[str(attr_id)] = w
    return out


# FM staff attribute word ratings → numeric midpoints for scoring.
STAFF_BANDS: tuple[dict[str, Any], ...] = (
    {"id": "elite", "label": "Elite", "lo": 20, "hi": 20, "score": 20.0},
    {"id": "outstanding", "label": "Outstanding", "lo": 18, "hi": 19, "score": 18.5},
    {"id": "very_good", "label": "Very Good", "lo": 15, "hi": 17, "score": 16.0},
    {"id": "good", "label": "Good", "lo": 12, "hi": 14, "score": 13.0},
    {"id": "average", "label": "Average", "lo": 10, "hi": 11, "score": 10.5},
    {"id": "competent", "label": "Competent", "lo": 7, "hi": 9, "score": 8.0},
    {"id": "reasonable", "label": "Reasonable", "lo": 4, "hi": 6, "score": 5.0},
    {"id": "unsuited", "label": "Unsuited", "lo": 1, "hi": 3, "score": 2.0},
)
DEFAULT_BAND_ID = "unsuited"
_BAND_BY_ID = {str(band["id"]): band for band in STAFF_BANDS}


def staff_band_options() -> list[dict[str, str]]:
    options = []
    for band in STAFF_BANDS:
        lo = int(band["lo"])
        hi = int(band["hi"])
        span = str(lo) if lo == hi else f"{lo}–{hi}"
        options.append(
            {
                "value": str(band["id"]),
                "label": f"{band['label']} ({span})",
            }
        )
    return options


def band_score(band_id: Any) -> float:
    band = _BAND_BY_ID.get(str(band_id or ""))
    if not band:
        return float(_BAND_BY_ID[DEFAULT_BAND_ID]["score"])
    return float(band["score"])


def band_for_value(value: Any) -> str:
    num = parse_attr_value(value)
    if num is None:
        return DEFAULT_BAND_ID
    for band in STAFF_BANDS:
        if float(band["lo"]) <= num <= float(band["hi"]):
            return str(band["id"])
    return DEFAULT_BAND_ID


def parse_attr_value(value: Any) -> float | None:
    """Parse a 1–20 attribute. Blank / band ids resolve to a numeric score."""
    if value is None or value == "":
        return 1.0
    if isinstance(value, str) and value in _BAND_BY_ID:
        return band_score(value)
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 1.0
    if num != num:  # NaN
        return 1.0
    return max(1.0, min(20.0, num))


def score_role(
    role_id: str,
    attrs: dict[str, Any],
    *,
    require_all: bool = False,
) -> dict[str, Any]:
    """Weighted average for one role.

    Blank attributes count as 1. ``require_all`` still withholds a score when a
    weighted attribute cannot be read as a number and was not defaulted.
    """
    weights = role_weights(role_id)
    labels = attribute_map()
    contributions: list[dict[str, Any]] = []
    weighted_sum = 0.0
    used_weight = 0
    total_weight = sum(weights.values())
    missing: list[str] = []

    for attr_id, weight in weights.items():
        meta = labels.get(attr_id) or {}
        label = str(meta.get("label") or attr_id)
        value = parse_attr_value(attrs.get(attr_id))
        if value is None:
            missing.append(attr_id)
            contributions.append(
                {
                    "id": attr_id,
                    "label": label,
                    "weight": weight,
                    "value": None,
                    "product": None,
                    "filled": False,
                }
            )
            continue
        product = value * weight
        weighted_sum += product
        used_weight += weight
        contributions.append(
            {
                "id": attr_id,
                "label": label,
                "weight": weight,
                "value": value,
                "product": product,
                "filled": True,
            }
        )

    contributions.sort(key=lambda row: (-int(row["weight"]), str(row["label"])))

    if require_all and missing:
        score = None
    elif used_weight <= 0:
        score = None
    else:
        score = weighted_sum / used_weight

    coverage = (used_weight / total_weight) if total_weight else 0.0
    return {
        "role_id": role_id,
        "score": score,
        "weighted_sum": weighted_sum,
        "used_weight": used_weight,
        "total_weight": total_weight,
        "coverage": coverage,
        "missing": missing,
        "contributions": contributions,
    }


def score_all_roles(
    attrs: dict[str, Any],
    *,
    require_all: bool = False,
) -> list[dict[str, Any]]:
    role_meta = {r["id"]: r for r in roles()}
    rows: list[dict[str, Any]] = []
    for role in roles():
        role_id = str(role["id"])
        result = score_role(role_id, attrs, require_all=require_all)
        result["label"] = str(role_meta.get(role_id, {}).get("label") or role_id)
        rows.append(result)
    rows.sort(
        key=lambda row: (
            row["score"] is None,
            -(row["score"] or 0.0),
            str(row["label"]),
        )
    )
    return rows


def attrs_from_lists(attr_ids: list[str], values: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for attr_id, value in zip(attr_ids, values):
        if not attr_id:
            continue
        out[str(attr_id)] = value
    return out
