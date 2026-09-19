"""Assign player archetypes from average group percentile floors/ceilings.

Game Icons attributions: https://game-icons.net (CC BY 3.0) via Iconify.
"""

from __future__ import annotations

import json
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

# Precomputed on cached stats players for fast archetype filters (not shown in UI).
HIGH_ARCHETYPES_FIELD = "high_archetypes"

ArchetypeTierId = Literal["bronze", "silver", "gold", "rust"]

# High awards first (gold…bronze), then the single low award (Rust).
TIER_RANK: dict[str, int] = {
    "gold": 4,
    "silver": 3,
    "bronze": 2,
    "rust": 1,
}
HIGH_TIERS = ("gold", "silver", "bronze")
LOW_TIERS = ("rust",)
GROUP_ORDER = ("gk", "def", "mid", "fwd")
GROUP_ABBR = {"gk": "GK", "def": "DEF", "mid": "MID", "fwd": "FWD"}


_data_mtime: float | None = None
_data_cache: dict[str, Any] | None = None


def _data() -> dict[str, Any]:
    """Load active archetype pack; reload when ``player_archetypes.json`` changes."""
    global _data_mtime, _data_cache
    try:
        mtime = DATA_PATH.stat().st_mtime
    except OSError:
        mtime = None
    if _data_cache is None or mtime != _data_mtime:
        _data_cache = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        _data_mtime = mtime
    return _data_cache


def archetype_defs() -> list[dict[str, Any]]:
    """Active (non-archived) archetype definitions for UI and scoring."""
    out: list[dict[str, Any]] = []
    for arch in _data().get("archetypes") or []:
        if not isinstance(arch, dict):
            continue
        if arch.get("archived"):
            continue
        out.append(arch)
    return out


def archetype_filter_categories() -> list[dict[str, str]]:
    """Ordered filter groups (GK / Defending / Possession / Final Third)."""
    raw = _data().get("filter_categories") or []
    out: list[dict[str, str]] = []
    for item in raw:
        cat_id = str(item.get("id") or "").strip()
        if not cat_id:
            continue
        out.append(
            {
                "id": cat_id,
                "label": str(item.get("label") or cat_id),
            }
        )
    return out


def archetypes_by_filter_category() -> list[tuple[dict[str, str], list[dict[str, Any]]]]:
    """(category, archetypes) pairs for filter UI; unknown categories last."""
    categories = archetype_filter_categories()
    by_id = {c["id"]: c for c in categories}
    buckets: dict[str, list[dict[str, Any]]] = {c["id"]: [] for c in categories}
    leftover: list[dict[str, Any]] = []
    for arch in archetype_defs():
        cat = str(arch.get("category") or "").strip()
        if cat in buckets:
            buckets[cat].append(arch)
        else:
            leftover.append(arch)
    grouped = [(by_id[c["id"]], buckets[c["id"]]) for c in categories if buckets[c["id"]]]
    if leftover:
        grouped.append(({"id": "other", "label": "Other"}, leftover))
    return grouped


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


def archetype_filter_options() -> list[dict[str, str]]:
    """MultiSelect options for high-tier archetype filters."""
    return [
        {
            "value": str(arch.get("id") or ""),
            "label": str(arch.get("label") or arch.get("id") or ""),
        }
        for arch in archetype_defs()
        if str(arch.get("id") or "").strip()
    ]


def normalize_archetype_filter(raw) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    allowed = {str(a.get("id") or "") for a in archetype_defs()}
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = str(item or "").strip()
        if key and key in allowed and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _read_stamped_high_archetypes(player: dict[str, Any] | None) -> set[str] | None:
    """Return stamped high archetype ids, or None when the field is absent."""
    if not player or HIGH_ARCHETYPES_FIELD not in player:
        return None
    raw = player.get(HIGH_ARCHETYPES_FIELD)
    if not isinstance(raw, (list, tuple)):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def high_archetype_ids_for_player(
    player: dict[str, Any] | None,
    *,
    settings: dict[str, Any] | None = None,
    threshold_overrides: dict[str, Any] | None = None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    value_mode: str = "raw",
    tier_floors: dict[str, float] | None = None,
    min_minutes: float | None = None,
    only_ids: set[str] | frozenset[str] | None = None,
    settings_normalized: bool = False,
) -> set[str]:
    """Bronze/Silver/Gold archetype ids only (no Rust). Faster than full evaluate."""
    if not player:
        return set()

    import services.ui_settings as us

    settings = (
        settings
        if settings_normalized and isinstance(settings, dict)
        else (us.normalize(settings) if settings is not None else us.normalize({}))
    )
    floors = us.normalize_archetype_tier_floors(
        tier_floors if tier_floors is not None else settings.get("archetype_tier_floors")
    )
    required = (
        float(min_minutes)
        if min_minutes is not None
        else float(us.default_minutes_required(settings))
    )
    if minutes_status(player.get("minutes"), required) != "meet":
        return set()

    if threshold_overrides is None:
        threshold_overrides = settings.get("stats_thresholds") or {}

    export_level = engine_detail_level_for_player(
        player,
        full_detail_divisions=settings.get("stats_full_detail_divisions"),
        limited_divisions=limited_divisions,
    )
    stats = scoring_stats(player)
    if not stats:
        return set()
    stats = stats_for_value_mode(
        stats,
        resolve_player_pos_group(player),
        export_level=export_level,
        value_mode=normalize_value_mode(value_mode),
    )

    wanted = set(only_ids) if only_ids is not None else None
    earned: set[str] = set()
    for group in eligible_stats_groups(player):
        for arch in archetype_defs():
            arch_id = str(arch.get("id") or "").strip()
            if not arch_id:
                continue
            if wanted is not None and arch_id not in wanted:
                continue
            allowed = {str(g).strip().lower() for g in (arch.get("groups") or [])}
            if group not in allowed:
                continue
            metric_ids = resolve_archetype_metrics(arch, group, threshold_overrides)
            if not metric_ids:
                continue

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
                band = band_metric(
                    group,
                    cat_id,
                    mid,
                    stats.get(mid),
                    threshold_overrides=threshold_overrides,
                    metric_p100=metric_p100,
                    metric_p0=metric_p0,
                )
                pct = band.get("percentile")
                if pct is None:
                    blocked = True
                    break
                percentiles.append(float(pct))

            if blocked:
                continue
            if _high_tier_for_percentiles(percentiles, floors):
                earned.add(arch_id)
                if wanted is not None and wanted <= earned:
                    return earned
    return earned


def earned_high_archetype_ids(
    player: dict[str, Any] | None,
    *,
    settings: dict[str, Any] | None = None,
    threshold_overrides: dict[str, Any] | None = None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    value_mode: str = "raw",
) -> set[str]:
    """Archetype ids earned at Bronze / Silver / Gold for this player."""
    return high_archetype_ids_for_player(
        player,
        settings=settings,
        threshold_overrides=threshold_overrides,
        metric_p100=metric_p100,
        metric_p0=metric_p0,
        limited_divisions=limited_divisions,
        value_mode=value_mode,
    )


def stamp_high_archetypes(
    players: list[dict[str, Any]] | None,
    *,
    settings: dict[str, Any] | None = None,
    banding_ctx=None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    value_mode: str = "raw",
    key_fn=None,
) -> dict[str, list[str]]:
    """Write ``high_archetypes`` onto each player; return player_key → ids."""
    from scoring.stats_scorer import player_key as default_key

    import services.ui_settings as us

    settings = us.normalize(settings) if settings is not None else us.normalize({})
    floors = us.normalize_archetype_tier_floors(settings.get("archetype_tier_floors"))
    min_minutes = float(us.default_minutes_required(settings))
    resolve_key = key_fn or default_key
    out: dict[str, list[str]] = {}
    for player in players or []:
        if not isinstance(player, dict):
            continue
        threshold_overrides = settings.get("stats_thresholds") or {}
        metric_p0 = None
        metric_p100 = None
        if banding_ctx is not None:
            threshold_overrides, metric_p0, metric_p100 = us.banding_for_player(
                banding_ctx, player, settings=settings
            )
        earned = high_archetype_ids_for_player(
            player,
            settings=settings,
            threshold_overrides=threshold_overrides,
            metric_p0=metric_p0,
            metric_p100=metric_p100,
            limited_divisions=limited_divisions,
            value_mode=value_mode,
            tier_floors=floors,
            min_minutes=min_minutes,
            settings_normalized=True,
        )
        ids = sorted(earned)
        player[HIGH_ARCHETYPES_FIELD] = ids
        key = str(resolve_key(player) or "").strip()
        if key and ids:
            out[key] = ids
    return out


def matching_archetype_keys(
    players: list[dict[str, Any]] | None,
    selected_ids,
    *,
    settings: dict[str, Any] | None = None,
    banding_ctx=None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    value_mode: str = "raw",
    key_fn=None,
    precomputed: dict[str, list[str] | tuple[str, ...]] | None = None,
) -> set[str] | None:
    """Keys of players earning any selected high archetype, or None if filter off.

    Prefers stamped ``high_archetypes`` / ``precomputed`` maps (raw mode) so filters
    stay cheap after upload precompute.
    """
    from scoring.stats_scorer import player_key as default_key

    wanted = set(normalize_archetype_filter(selected_ids))
    if not wanted:
        return None

    import services.ui_settings as us

    resolve_key = key_fn or default_key
    mode = normalize_value_mode(value_mode)

    if mode == "raw" and precomputed is not None:
        matched: set[str] = set()
        for key, ids in precomputed.items():
            key_s = str(key or "").strip()
            if not key_s:
                continue
            earned = {str(item).strip() for item in (ids or []) if str(item).strip()}
            if earned & wanted:
                matched.add(key_s)
        return matched

    if mode == "raw":
        stamped_ok = True
        matched = set()
        for player in players or []:
            earned = _read_stamped_high_archetypes(player)
            if earned is None:
                stamped_ok = False
                break
            if earned & wanted:
                key = str(resolve_key(player) or "").strip()
                if key:
                    matched.add(key)
        if stamped_ok:
            return matched

    settings = us.normalize(settings) if settings is not None else us.normalize({})
    floors = us.normalize_archetype_tier_floors(settings.get("archetype_tier_floors"))
    min_minutes = float(us.default_minutes_required(settings))
    matched = set()
    for player in players or []:
        threshold_overrides = settings.get("stats_thresholds") or {}
        metric_p0 = None
        metric_p100 = None
        if banding_ctx is not None:
            if mode == "raw":
                threshold_overrides, metric_p0, metric_p100 = us.banding_for_player(
                    banding_ctx, player, settings=settings
                )
            else:
                threshold_overrides, metric_p0, metric_p100 = us.banding_for_value_mode(
                    banding_ctx, player, mode
                )
        earned = high_archetype_ids_for_player(
            player,
            settings=settings,
            threshold_overrides=threshold_overrides,
            metric_p0=metric_p0,
            metric_p100=metric_p100,
            limited_divisions=limited_divisions,
            value_mode=mode,
            tier_floors=floors,
            min_minutes=min_minutes,
            only_ids=wanted,
            settings_normalized=True,
        )
        if earned:
            key = str(resolve_key(player) or "").strip()
            if key:
                matched.add(key)
    return matched


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
        if metric_id in metrics_for(
            group, cat_id, threshold_overrides, include_hidden=True
        ):
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
    """Mean of required metric percentiles ≥ floor → Bronze / Silver / Gold."""
    if not percentiles:
        return None
    average = sum(percentiles) / len(percentiles)
    for tier in HIGH_TIERS:
        floor = float(floors.get(tier, 0))
        if average >= floor:
            return tier  # type: ignore[return-value]
    return None


def _low_tier_for_percentiles(
    percentiles: list[float],
    ceilings: dict[str, float],
) -> ArchetypeTierId | None:
    """Mean of required metric percentiles ≤ ceiling → Rust."""
    if not percentiles:
        return None
    average = sum(percentiles) / len(percentiles)
    ceiling = float(ceilings.get("rust", 30))
    if average <= ceiling:
        return "rust"
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
