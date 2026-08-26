"""Detect FM exports where advanced league stats are not collected.

Some leagues only supply basic counting stats in Moneyball exports; advanced
columns (xA, key passes, interceptions, etc.) are written as ``0``. Those values
must not be banded or averaged as if they were real zeros.

Leagues may also supply *partial* tracking (some advanced columns populated,
others always zero). When any advanced probe is non-zero, other advanced metrics
that are still zero are treated as unavailable.

See ``config/stats_availability.json`` for the canonical metric lists.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from scoring.role_scorer import pick
from scoring.stats_scorer import is_gk_group, metric_defs, parse_number

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "stats_availability.json"

LIMITED_TRACKING_NOTE = (
    "This player's league does not collect all advanced match stats in FM "
    "(e.g. xA, key passes, interceptions). Unavailable metrics are excluded "
    "from category and overall averages and shown as Not tracked."
)

LIMITED_TRACKING_HINT = (
    "Some leagues do not collect all advanced stats in FM exports. Unavailable "
    "metrics are excluded from percentile averages."
)


@lru_cache(maxsize=1)
def availability_config() -> dict[str, Any]:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def universal_metrics(*, group: str | None = None) -> frozenset[str]:
    cfg = availability_config()["universal_metrics"]
    if group and is_gk_group(group):
        return frozenset(cfg["gk"])
    if group:
        return frozenset(cfg["outfield"])
    return frozenset(cfg["outfield"]) | frozenset(cfg["gk"])


def unavailable_metrics_for_group(group: str | None) -> frozenset[str]:
    cfg = availability_config()["limited_tracking_unavailable"]
    if is_gk_group(group):
        return frozenset(cfg["gk"])
    return frozenset(cfg["outfield"])


def _csv_value(row: dict[str, str], column: str) -> float | None:
    return parse_number(pick(row, [column]))


def _has_basic_tracking(row: dict[str, str]) -> bool:
    minutes = _csv_value(row, "Minutes")
    if minutes is None or minutes <= 0:
        return False
    for column in availability_config()["detection"]["basic_csv_columns"]:
        val = _csv_value(row, column)
        if val is not None and val > 0:
            return True
    return False


def _probe_has_nonzero(row: dict[str, str], column: str) -> bool:
    val = _csv_value(row, column)
    return val is not None and val != 0


def _any_advanced_probe_nonzero(row: dict[str, str]) -> bool:
    for column in availability_config()["detection"]["probe_csv_columns"]:
        if _probe_has_nonzero(row, column):
            return True
    return False


def _metric_csv_all_zero(row: dict[str, str], metric_id: str) -> bool:
    """True when every CSV alias for the metric is missing or exactly zero."""
    meta = metric_defs().get(metric_id) or {}
    aliases = list(meta.get("csv") or [])
    if not aliases:
        return False
    if meta.get("derive") == "per90_from_total":
        total = None
        for alias in aliases:
            val = _csv_value(row, alias)
            if val is not None:
                total = val
                break
        if total is None:
            return True
        return total == 0
    seen = False
    for alias in aliases:
        val = _csv_value(row, alias)
        if val is None:
            continue
        seen = True
        if val != 0:
            return False
    return seen or not seen


def detect_limited_tracking(row: dict[str, str]) -> bool:
    """True when basic stats exist but every advanced probe column is zero/missing."""
    if not _has_basic_tracking(row):
        return False
    for column in availability_config()["detection"]["probe_csv_columns"]:
        if _probe_has_nonzero(row, column):
            return False
    return True


def detect_unavailable_metrics(row: dict[str, str], group: str | None) -> frozenset[str]:
    """Metrics to exclude from banding for this export row."""
    if not _has_basic_tracking(row):
        return frozenset()
    pool = unavailable_metrics_for_group(group)
    if detect_limited_tracking(row):
        return pool
    if not _any_advanced_probe_nonzero(row):
        return frozenset()
    return frozenset(
        mid for mid in pool if _metric_csv_all_zero(row, mid)
    )


def apply_limited_tracking(player: dict[str, Any], row: dict[str, str]) -> None:
    """Set availability flags and strip unavailable metrics from ``player["stats"]``."""
    group = player.get("pos_group") or "mid"
    unavailable = detect_unavailable_metrics(row, group)
    player["stats_limited_tracking"] = detect_limited_tracking(row)
    player["stats_unavailable"] = sorted(unavailable)
    stats = player.get("stats") or {}
    player["stats"] = {
        mid: val for mid, val in stats.items() if mid not in unavailable
    }


def has_limited_tracking(player: dict[str, Any] | None) -> bool:
    return bool(unavailable_stats(player))


def unavailable_stats(player: dict[str, Any] | None) -> frozenset[str]:
    raw = (player or {}).get("stats_unavailable") or []
    return frozenset(str(x) for x in raw)


def metric_is_unavailable(player: dict[str, Any] | None, metric_id: str) -> bool:
    return metric_id in unavailable_stats(player)
