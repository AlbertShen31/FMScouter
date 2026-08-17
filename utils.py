from typing import Dict, List, Union
import logging

logger = logging.getLogger(__name__)


def calculate_score(
    data: Dict[str, Union[str, int]],
    key_attrs: List[str],
    green_attrs: List[str],
    blue_attrs: List[str],
    key_weight: float,
    green_weight: float,
    blue_weight: float,
    divisor: float,
) -> float:
    """Calculate position score based on attributes and weights."""
    try:
        processed_data = {}
        for attr in key_attrs + green_attrs + blue_attrs:
            value = data.get(attr, 0)
            if value == "-" or value == "":
                processed_data[attr] = 0
            elif isinstance(value, str) and "-" in value:
                processed_data[attr] = int(value.split("-")[0])
            else:
                processed_data[attr] = int(value)

        key_score = sum(processed_data[attr] for attr in key_attrs)
        green_score = sum(processed_data[attr] for attr in green_attrs)
        blue_score = sum(processed_data[attr] for attr in blue_attrs)

        total_score = (
            key_score * key_weight + green_score * green_weight + blue_score * blue_weight
        ) / divisor
        return round(total_score, 1)
    except Exception as e:
        logger.error(f"Error calculating score: {e}")
        return 0.0
