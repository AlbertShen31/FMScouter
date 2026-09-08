"""Detect FM exports where advanced league stats are not collected.

Some leagues only supply basic counting stats in Moneyball exports; advanced
columns (key passes, interceptions, etc.) are written as ``0``. Those values
must not be banded or averaged as if they were real zeros.

Player-level: limited when basic stats exist and **all** advanced probes are
zero. Probes are metrics limited leagues do not fill (interceptions, key
passes, progressive passes, clearances). xA still appears in limited leagues.
Possession won is not tracked when zero in limited leagues but is kept when
the export value is > 0.

League-level (Division stripe): limited when minutes-weighted averages of
probe /90 rates across the division are near zero. A few leftover non-zeros
(transfers, continental comps) are treated as sparse noise and do not veto
the league. Players with no minutes do not affect the average.

See ``config/stats_availability.json`` for the canonical metric lists.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from scoring.role_scorer import pick
from scoring.stats_scorer import is_gk_group, parse_number

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "stats_availability.json"

LIMITED_TRACKING_NOTE = (
    "This player's league does not collect all advanced match stats in FM "
    "(e.g. key passes, interceptions, progressive passes). Unavailable metrics "
    "are excluded from category and overall averages and shown as Not tracked."
)

LIMITED_TRACKING_HINT = (
    "Some leagues do not collect all advanced stats in FM exports. When "
    "league-wide advanced probes are near zero (sparse leftovers allowed), "
    "those metrics are excluded from percentile averages. Division cells for "
    "those leagues use a striped highlight."
)

LIMITED_DIVISION_TITLE = (
    "Incomplete advanced match-stat tracking in FM for this league — some "
    "metrics are not collected and are excluded from percentile averages."
)

_MIN_ACTIVE_FOR_LEAGUE = 1
_MIN_MINUTES = 90.0
# Include any positive minutes in league aggregates; zero-minute rows add
# nothing. Require enough total time that a short single-player all-zero
# spell (e.g. 180 mins in Eredivisie) does not stripe a tracked league.
_MIN_MINUTES_FOR_LEAGUE_MEMBER = 1.0
_MIN_TOTAL_MINUTES_FOR_LEAGUE = 300.0
# Max minutes-weighted avg across probe /90 columns. Fully tracked leagues
# sit well above this; limited leagues are ~0 with sparse transfer noise.
_LEAGUE_PROBE_MAX_AVG = 0.25


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


def unavailable_when_zero_metrics() -> frozenset[str]:
    """Limited-league metrics that stay available when the parsed value is > 0."""
    cfg = availability_config().get("limited_tracking_unavailable_when_zero") or {}
    return frozenset(cfg.get("metrics") or [])


def _effective_unavailable(
    pool: frozenset[str],
    stats: dict[str, Any],
) -> frozenset[str]:
    """Drop zero-only metrics from the unavailable set when the player has data."""
    when_zero = unavailable_when_zero_metrics()
    if not when_zero:
        return pool
    keep = {
        mid
        for mid in pool
        if mid in when_zero and (stats.get(mid) or 0) > 0
    }
    if not keep:
        return pool
    return frozenset(mid for mid in pool if mid not in keep)


def _csv_value(row: dict[str, str], column: str) -> float | None:
    return parse_number(pick(row, [column]))


def _has_basic_tracking(
    row: dict[str, str],
    *,
    min_minutes: float = _MIN_MINUTES,
) -> bool:
    minutes = _csv_value(row, "Minutes")
    if minutes is None or minutes < min_minutes:
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


def _probe_rate_columns() -> list[str]:
    """Probe columns that are per-90 rates (used for league averages)."""
    return [
        col
        for col in availability_config()["detection"]["probe_csv_columns"]
        if "per 90" in col.lower() or "/90" in col.lower()
    ]


def detect_limited_tracking(
    row: dict[str, str],
    *,
    min_minutes: float = _MIN_MINUTES,
) -> bool:
    """True when basic stats exist but every advanced probe column is zero/missing."""
    if not _has_basic_tracking(row, min_minutes=min_minutes):
        return False
    return not _any_advanced_probe_nonzero(row)


def _division_key(row: dict[str, str]) -> str:
    raw = str(pick(row, ["Division", "Div"]) or "").strip()
    if not raw or raw in ("-", "—"):
        return ""
    return raw


def _league_probe_max_avg(members: list[dict[str, str]]) -> float:
    """Minutes-weighted max average across probe /90 columns."""
    rate_cols = _probe_rate_columns()
    if not members or not rate_cols:
        return 0.0
    total_minutes = 0.0
    weighted: dict[str, float] = {col: 0.0 for col in rate_cols}
    for row in members:
        minutes = _csv_value(row, "Minutes") or 0.0
        if minutes <= 0:
            continue
        total_minutes += minutes
        for col in rate_cols:
            weighted[col] += minutes * (_csv_value(row, col) or 0.0)
    if total_minutes <= 0:
        return 0.0
    return max(val / total_minutes for val in weighted.values())


def _division_is_limited_tracking(members: list[dict[str, str]]) -> bool:
    """True when league-wide probe rates are near zero (sparse noise allowed)."""
    if len(members) < _MIN_ACTIVE_FOR_LEAGUE:
        return False
    total_minutes = sum((_csv_value(r, "Minutes") or 0.0) for r in members)
    if total_minutes < _MIN_TOTAL_MINUTES_FOR_LEAGUE:
        return False
    # Need at least one player with basic counting stats so empty rows alone
    # cannot classify a division.
    if not any(_has_basic_tracking(r, min_minutes=_MIN_MINUTES_FOR_LEAGUE_MEMBER) for r in members):
        return False
    return _league_probe_max_avg(members) <= _LEAGUE_PROBE_MAX_AVG


def analyze_division_availability(
    rows: list[dict[str, str]],
) -> dict[str, frozenset[str]]:
    """Map division name → unavailable metric ids for this export.

    A division is limited when minutes-weighted averages of advanced probe
    /90 rates are near zero across everyone with minutes. Sparse non-zeros
    (e.g. one transfer with leftover clearances) do not veto the league.
    """
    by_div: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        minutes = _csv_value(row, "Minutes")
        if minutes is None or minutes < _MIN_MINUTES_FOR_LEAGUE_MEMBER:
            continue
        div = _division_key(row)
        if not div:
            continue
        by_div[div].append(row)

    out: dict[str, frozenset[str]] = {}
    pool = unavailable_metrics_for_group("mid") | unavailable_metrics_for_group("gk")

    for div, members in by_div.items():
        if _division_is_limited_tracking(members):
            out[div] = pool
    return out


def collect_limited_tracking_divisions(
    division_unavailable: dict[str, frozenset[str]] | None = None,
    *,
    rows: list[dict[str, str]] | None = None,
) -> list[str]:
    """Sorted division names with no advanced-stat tracking."""
    mapping = division_unavailable
    if mapping is None:
        mapping = analyze_division_availability(rows or [])
    return sorted(div for div, mids in mapping.items() if mids)


def apply_limited_tracking(
    player: dict[str, Any],
    row: dict[str, str],
    *,
    division_unavailable: dict[str, frozenset[str]] | None = None,
) -> None:
    """Set availability flags and strip unavailable metrics from ``player["stats"]``.

    Only full limited-tracking players (all advanced probes zero) lose the
    advanced metric pool. Players in a limited division inherit that pool
    even if a few leftover probe values remain (transfer/continental noise).
    """
    group = player.get("pos_group") or "mid"
    pool = unavailable_metrics_for_group(group)
    div = _division_key(row)
    unavailable: frozenset[str] = frozenset()
    if detect_limited_tracking(row):
        unavailable = pool
    elif division_unavailable is not None and div:
        unavailable = frozenset(division_unavailable.get(div) or ()) & pool
    stats = player.get("stats") or {}
    unavailable = _effective_unavailable(unavailable, stats)
    player["stats_limited_tracking"] = bool(unavailable)
    player["stats_unavailable"] = sorted(unavailable)
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


def division_has_limited_tracking(
    division: str | None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None,
) -> bool:
    raw = str(division or "").strip()
    if not raw or raw in ("-", "—") or not limited_divisions:
        return False
    return raw in set(limited_divisions)


def nation_counts_for_limited_divisions(
    limited_divisions: list[str] | None,
    players: list[dict[str, Any]] | None,
) -> list[tuple[str, int]]:
    """Count limited leagues per nation (Based In), highest minutes per division."""
    limited = [
        str(name).strip()
        for name in (limited_divisions or [])
        if str(name).strip() and str(name).strip() not in ("-", "—")
    ]
    if not limited:
        return []

    limited_set = set(limited)
    div_nation_minutes: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for player in players or []:
        div = str(player.get("division") or "").strip()
        if div not in limited_set:
            continue
        nation = str(player.get("based_in") or player.get("nation") or "").strip()
        if not nation or nation in ("-", "—"):
            nation = "Unknown"
        minutes = float(player.get("minutes") or 0.0)
        div_nation_minutes[div][nation] += minutes if minutes > 0 else 1.0

    nation_counts: dict[str, int] = defaultdict(int)
    for div in limited:
        votes = div_nation_minutes.get(div)
        if not votes:
            nation_counts["Unknown"] += 1
            continue
        nation_counts[max(votes.items(), key=lambda item: item[1])[0]] += 1

    return sorted(nation_counts.items(), key=lambda item: (-item[1], item[0].lower()))


def limited_tracking_tooltip(
    limited_divisions: list[str],
    *,
    nation_counts: list[tuple[str, int]] | None = None,
    players: list[dict[str, Any]] | None = None,
) -> str:
    """Hover text for uploads limited-league count."""
    divisions = [
        str(name).strip()
        for name in limited_divisions
        if str(name).strip() and str(name).strip() not in ("-", "—")
    ]
    if not divisions:
        return ""

    counts = nation_counts
    if counts is None:
        counts = nation_counts_for_limited_divisions(divisions, players)

    n = len(divisions)
    league_word = "league" if n == 1 else "leagues"
    lines = [f"Incomplete advanced match stats ({n} {league_word})"]
    if counts:
        by_nation = ", ".join(f"{nation} ({count})" for nation, count in counts)
        lines.append(f"By nation: {by_nation}")
    lines.append(", ".join(divisions))
    return "\n".join(lines)
