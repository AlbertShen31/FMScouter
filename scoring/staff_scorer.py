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


def parse_attr_value(value: Any) -> float | None:
    """Parse a 1–20 attribute. Blank values default to 1."""
    if value is None or value == "":
        return 1.0
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
