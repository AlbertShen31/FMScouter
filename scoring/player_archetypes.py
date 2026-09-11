"""Assign player archetypes from group percentile floors.

Game Icons attributions: https://game-icons.net (CC BY 3.0) via Iconify.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from scoring.role_scorer import (
    POS_CARD_GROUPS,
    best_pos_group,
    parse_positions,
    player_pos_groups,
)
from scoring.stats_availability import metric_is_unavailable
from scoring.stats_scorer import (
    band_metric,
    coerce_stats_pos_group,
    is_gk_group,
    metric_defs,
    metrics_for,
    minutes_status,
    resolve_player_pos_group,
    scoring_stats,
    stats_for_value_mode,
    view_categories,
)
from scoring.stats_detail_transform import (
    engine_detail_level_for_player,
    normalize_value_mode,
)

DATA_PATH = Path(__file__).resolve().parents[1] / "config" / "player_archetypes.json"

ArchetypeTierId = Literal["bronze", "silver", "gold", "rust", "slate", "ash"]

# High awards first (gold…bronze), then low awards (ash…rust = more severe first).
TIER_RANK: dict[str, int] = {
    "gold": 6,
    "silver": 5,
    "bronze": 4,
    "ash": 3,
    "slate": 2,
    "rust": 1,
}
HIGH_TIERS = ("gold", "silver", "bronze")
LOW_TIERS = ("ash", "slate", "rust")
GROUP_ORDER = ("gk", "def", "mid", "fwd")
GROUP_ABBR = {"gk": "GK", "def": "DEF", "mid": "MID", "fwd": "FWD"}


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def archetype_defs() -> list[dict[str, Any]]:
    return list(_data().get("archetypes") or [])


def default_tier_floors() -> dict[str, float]:
    raw = _data().get("default_floors") or {}
    return {
        "bronze": float(raw.get("bronze", 70)),
        "silver": float(raw.get("silver", 80)),
        "gold": float(raw.get("gold", 90)),
    }


def default_tier_ceilings() -> dict[str, float]:
    raw = _data().get("default_ceilings") or {}
    return {
        "rust": float(raw.get("rust", 30)),
        "slate": float(raw.get("slate", 20)),
        "ash": float(raw.get("ash", 10)),
    }


def tier_label(tier_id: str | None) -> str:
    key = str(tier_id or "").strip().lower()
    for tier in _data().get("tiers") or []:
        if str(tier.get("id") or "").strip().lower() == key:
            return str(tier.get("label") or key.title())
    return key.title() if key else ""


def tier_polarity(tier_id: str | None) -> str:
    key = str(tier_id or "").strip().lower()
    for tier in _data().get("tiers") or []:
        if str(tier.get("id") or "").strip().lower() == key:
            return str(tier.get("polarity") or "high")
    if key in LOW_TIERS:
        return "low"
    return "high"


def group_abbr(group: str | None) -> str:
    return GROUP_ABBR.get(str(group or "").strip().lower(), str(group or "").upper() or "—")


def eligible_stats_groups(player: dict[str, Any] | None) -> list[str]:
    """Coarse stats groups (gk/def/mid/fwd) the player may be evaluated in."""
    if not player:
        return []
    primary = resolve_player_pos_group(player)
    found: set[str] = set()

    positions = parse_positions(str(player.get("position") or ""))
    cards = set(player_pos_groups(positions))
    for card in cards:
        for role_g in POS_CARD_GROUPS.get(card, ()):
            sg = coerce_stats_pos_group(role_g)
            if sg:
                found.add(sg)

    bg = best_pos_group(str(player.get("best_pos") or "") or None)
    if bg:
        sg = coerce_stats_pos_group(bg)
        if sg:
            found.add(sg)

    if primary in GROUP_ORDER:
        found.add(primary)

    outfield_cards = cards - {"GK"}
    if is_gk_group(primary) or (cards and not outfield_cards):
        return ["gk"] if "gk" in found or is_gk_group(primary) else []

    found.discard("gk")
    return [g for g in GROUP_ORDER if g in found]


def _metric_in_group(
    group: str,
    metric_id: str,
    threshold_overrides: dict[str, Any] | None,
) -> str | None:
    """Return view category id when the metric exists under the group's thresholds."""
    for cat in view_categories():
        cat_id = cat["id"]
        if metric_id in metrics_for(group, cat_id, threshold_overrides):
            return cat_id
    return None


def resolve_archetype_metrics(
    archetype: dict[str, Any],
    group: str,
    threshold_overrides: dict[str, Any] | None,
) -> list[str]:
    """Primary metrics, or fallback when preferred metrics are absent from the pack."""
    primary = [str(m) for m in (archetype.get("metrics") or []) if str(m).strip()]
    if primary and all(
        _metric_in_group(group, mid, threshold_overrides) for mid in primary
    ):
        return primary
    fallback = [
        str(m) for m in (archetype.get("metrics_fallback") or []) if str(m).strip()
    ]
    if fallback and all(
        _metric_in_group(group, mid, threshold_overrides) for mid in fallback
    ):
        return fallback
    # Prefer primary when only some exist? Plan: missing blocks award — require full set.
    return primary


def _high_tier_for_percentiles(
    percentiles: list[float],
    floors: dict[str, float],
) -> ArchetypeTierId | None:
    """All metrics ≥ floor → Bronze / Silver / Gold (strict)."""
    if not percentiles:
        return None
    lowest = min(percentiles)
    for tier in HIGH_TIERS:
        floor = float(floors.get(tier, 0))
        if lowest >= floor:
            return tier  # type: ignore[return-value]
    return None


def _low_tier_for_percentiles(
    percentiles: list[float],
    ceilings: dict[str, float],
) -> ArchetypeTierId | None:
    """All metrics ≤ ceiling → Rust / Slate / Ash (strict; Ash is worst)."""
    if not percentiles:
        return None
    highest = max(percentiles)
    for tier in LOW_TIERS:
        ceiling = float(ceilings.get(tier, 100))
        if highest <= ceiling:
            return tier  # type: ignore[return-value]
    return None


def evaluate_archetypes(
    player: dict[str, Any] | None,
    *,
    settings: dict[str, Any] | None = None,
    threshold_overrides: dict[str, Any] | None = None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    value_mode: str = "raw",
    tier_floors: dict[str, float] | None = None,
    tier_ceilings: dict[str, float] | None = None,
    min_minutes: float | None = None,
) -> list[dict[str, Any]]:
    """Return earned archetypes tagged by group (high and/or low tiers)."""
    if not player:
        return []

    import services.ui_settings as us

    settings = us.normalize(settings) if settings is not None else us.normalize({})
    floors = us.normalize_archetype_tier_floors(
        tier_floors if tier_floors is not None else settings.get("archetype_tier_floors")
    )
    ceilings = us.normalize_archetype_tier_ceilings(
        tier_ceilings
        if tier_ceilings is not None
        else settings.get("archetype_tier_ceilings")
    )
    required = (
        float(min_minutes)
        if min_minutes is not None
        else float(us.default_minutes_required(settings))
    )
    if minutes_status(player.get("minutes"), required) != "meet":
        return []

    if threshold_overrides is None:
        threshold_overrides = settings.get("stats_thresholds") or {}

    export_level = engine_detail_level_for_player(
        player,
        full_detail_divisions=settings.get("stats_full_detail_divisions"),
        limited_divisions=limited_divisions,
    )
    stats = scoring_stats(player)
    if not stats:
        return []
    stats = stats_for_value_mode(
        stats,
        resolve_player_pos_group(player),
        export_level=export_level,
        value_mode=normalize_value_mode(value_mode),
    )

    awards: list[dict[str, Any]] = []
    defs = metric_defs()

    for group in eligible_stats_groups(player):
        for arch in archetype_defs():
            allowed = {str(g).strip().lower() for g in (arch.get("groups") or [])}
            if group not in allowed:
                continue
            metric_ids = resolve_archetype_metrics(arch, group, threshold_overrides)
            if not metric_ids:
                continue

            metric_pcts: list[dict[str, Any]] = []
            percentiles: list[float] = []
            blocked = False
            for mid in metric_ids:
                if metric_is_unavailable(player, mid):
                    blocked = True
                    break
                cat_id = _metric_in_group(group, mid, threshold_overrides)
                if not cat_id:
                    blocked = True
                    break
                value = stats.get(mid)
                band = band_metric(
                    group,
                    cat_id,
                    mid,
                    value,
                    threshold_overrides=threshold_overrides,
                    metric_p100=metric_p100,
                    metric_p0=metric_p0,
                )
                pct = band.get("percentile")
                if pct is None:
                    blocked = True
                    break
                meta = defs.get(mid) or {}
                metric_pcts.append(
                    {
                        "id": mid,
                        "label": meta.get("label") or mid,
                        "abbr": meta.get("abbr") or mid,
                        "percentile": float(pct),
                        "display": band.get("display"),
                    }
                )
                percentiles.append(float(pct))

            if blocked:
                continue

            for tier in (
                _high_tier_for_percentiles(percentiles, floors),
                _low_tier_for_percentiles(percentiles, ceilings),
            ):
                if not tier:
                    continue
                awards.append(
                    {
                        "id": str(arch.get("id") or ""),
                        "label": str(arch.get("label") or arch.get("id") or ""),
                        "icon": str(arch.get("icon") or "game-icons:soccer-ball"),
                        "tier": tier,
                        "tier_label": tier_label(tier),
                        "polarity": tier_polarity(tier),
                        "group": group,
                        "group_label": group_abbr(group),
                        "metrics": metric_pcts,
                    }
                )

    awards.sort(
        key=lambda a: (
            0 if a.get("polarity") == "high" else 1,
            -TIER_RANK.get(str(a.get("tier")), 0),
            str(a.get("label") or ""),
            GROUP_ORDER.index(a["group"]) if a.get("group") in GROUP_ORDER else 99,
        )
    )
    return awards
