"""Shared scoring math used by `role_scorer`.

    score = (key_weight * sum(key) + preferred_weight * sum(preferred)
             + useful_weight * sum(useful)) / divisor
"""
from typing import Dict, List, Union
import logging

logger = logging.getLogger(__name__)


def calculate_score(
    data: Dict[str, Union[str, int]],
    key_attrs: List[str],
    preferred_attrs: List[str],
    useful_attrs: List[str],
    key_weight: float,
    preferred_weight: float,
    useful_weight: float,
    divisor: float,
) -> float:
    """Calculate position score based on attributes and weights."""
    try:
        processed_data = {}
        for attr in key_attrs + preferred_attrs + useful_attrs:
            value = data.get(attr, 0)
            if value == "-" or value == "":
                processed_data[attr] = 0
            elif isinstance(value, str) and "-" in value:
                processed_data[attr] = int(value.split("-")[0])
            else:
                processed_data[attr] = int(value)

        key_score = sum(processed_data[attr] for attr in key_attrs)
        preferred_score = sum(processed_data[attr] for attr in preferred_attrs)
        useful_score = sum(processed_data[attr] for attr in useful_attrs)

        if not divisor:
            return 0.0
        total_score = (
            key_score * key_weight
            + preferred_score * preferred_weight
            + useful_score * useful_weight
        ) / divisor
        return round(total_score, 1)
    except Exception as e:
        logger.error(f"Error calculating score: {e}")
        return 0.0
