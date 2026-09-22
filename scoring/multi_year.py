"""Merge 1–3 season exports into a recency-weighted multi-year player set."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from scoring.role_scorer import player_row_key, score_players
from scoring.stats_scorer import metric_defs, set_piece_metric_defs
from services.export_library import (
    DEFAULT_YEAR_WEIGHTS,
    YEAR_KEYS,
    configured_years,
    year_weights,
)

# Percent metrics rebuilt from attempted/completed (or count) pairs when possible.
# Values are (attempted_metric_id | None, completed_metric_id | None).
# When completed is None, completed_raw ≈ (percent/100) * attempted_raw.
PERCENT_PAIRS: dict[str, tuple[str | None, str | None]] = {
    "pass_completion": ("passes_attempted", None),
    "header_win_rate": ("headers_attempted", "headers_won"),
    "tackle_win_rate": ("tackles_attempted", "tackles_completed"),
    "open_play_cross_completion": ("crosses_attempted", "crosses_completed"),
    "shots_on_target_pct": ("shots", "shots_on_target"),
    "penalties_saved_ratio": ("penalties_faced", "penalties_saved"),
    "penalties_scored_ratio": ("penalties_taken", "penalties_scored"),
}

# Ratio metrics rebuilt from numerator/denominator totals when both exist.
RATIO_PAIRS: dict[str, tuple[str, str]] = {
    "xg_per_shot": ("expected_goals", "shots"),
}

STATUS_LABELS = {
    "continuous": "Continuous",
    "new": "New",
    "returned": "Returned",
    "departed": "Departed",
    "partial": "Partial",
}

IDENTITY_COPY_KEYS = (
    "name",
    "unique_id",
    "age",
    "club",
    "division",
    "nation",
    "based_in",
    "second_nation",
    "position",
    "best_pos",
    "best_role",
    "position_role",
    "style",
    "personality",
    "media_handling",
    "world_reputation",
    "world_reputation_gold",
    "world_reputation_silver",
    "ability",
    "ability_gold",
    "ability_silver",
    "potential",
    "potential_gold",
    "potential_silver",
    "height",
    "left_foot",
    "right_foot",
    "rec",
    "inf",
    "injury",
    "injured_on",
    "time_missed",
    "squad",
    "picked",
    "home_grown_status",
    "national_team",
    "int_apps_season",
    "int_assists",
    "avg_rating_club",
    "avg_rating_int",
    "last_5_club",
    "last_5_int",
    "form_club",
    "form_int",
    "int_goals_conceded",
    "int_gls",
    "int_apps",
    "yth_apps",
    "yth_gls",
    "pos_group",
    "pos_groups",
    "pos_cards",
    "positions",
    "left_foot_n",
    "right_foot_n",
)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _minutes(player: dict[str, Any] | None) -> float:
    if not player:
        return 0.0
    mins = _safe_float(player.get("minutes"))
    return mins if mins is not None and mins > 0 else 0.0


def _raw_from_rate(rate: float | None, minutes: float) -> float | None:
    if rate is None or minutes <= 0:
        return None
    return float(rate) * (minutes / 90.0)


def _index_by_key(players: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for player in players:
        key = player_row_key(player)
        if key:
            out[key] = player
    return out


def presence_status(
    configured: list[str],
    present: set[str] | list[str],
) -> str | None:
    """Classify a player's multi-year presence pattern."""
    years = [y for y in YEAR_KEYS if y in configured]
    if len(years) <= 1:
        return None
    present_set = {str(y) for y in present if str(y) in years}
    if not present_set:
        return None
    newest = years[-1]
    if present_set.issuperset(years):
        return "continuous"
    if newest not in present_set:
        return "departed"
    older = years[:-1]
    older_present = [y for y in older if y in present_set]
    # New = present only in the most recent configured year.
    if not older_present:
        return "new"
    first_idx = next(i for i, y in enumerate(years) if y in present_set)
    last_idx = next(
        len(years) - 1 - i for i, y in enumerate(reversed(years)) if y in present_set
    )
    span = years[first_idx : last_idx + 1]
    if any(y not in present_set for y in span):
        return "returned"
    # Contiguous mid-pack arrival (e.g. Y2+Y3, missing Y1) — not New.
    return "partial"


def status_label(status: str | None) -> str:
    if not status:
        return ""
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def _year_snapshot(player: dict[str, Any]) -> dict[str, Any]:
    """Per-year payload for modal By-year cards and depth Current-year rates.

    Keep identity plus every scored metric present that year. A tiny outfield
    whitelist used to drop GK rates (xG prevented, goals conceded, save %, …),
    so Profiles depth → Current → Goalkeeping showed blanks while the modal
    (combined multi-year stats) still had percentiles. Omit full attrs to
    limit cache size.
    """
    known = set(_all_metric_ids())
    stats = player.get("stats") or {}
    sp_stats = player.get("set_piece_stats") or {}
    key_stats = {
        mid: stats[mid]
        for mid in known
        if mid in stats and stats[mid] is not None
    }
    key_sp = {
        mid: sp_stats[mid]
        for mid in known
        if mid in sp_stats and sp_stats[mid] is not None
    }
    out: dict[str, Any] = {
        "minutes": player.get("minutes"),
        "stats": key_stats,
        "club": player.get("club"),
        "age": player.get("age"),
        "division": player.get("division"),
        "position": player.get("position"),
        "best_pos": player.get("best_pos"),
    }
    if key_sp:
        out["set_piece_stats"] = key_sp
    if "stats_unavailable" in player:
        out["stats_unavailable"] = list(player.get("stats_unavailable") or [])
    if "stats_limited_tracking" in player:
        out["stats_limited_tracking"] = bool(player.get("stats_limited_tracking"))
    if "limited_division_tracking" in player:
        out["limited_division_tracking"] = bool(
            player.get("limited_division_tracking")
        )
    return out


def _metric_unit(metric_id: str) -> str | None:
    meta = metric_defs().get(metric_id) or set_piece_metric_defs().get(metric_id)
    if not meta:
        return None
    return str(meta.get("unit") or "") or None


def _all_metric_ids() -> list[str]:
    ids = list(metric_defs().keys())
    for mid in set_piece_metric_defs():
        if mid not in ids:
            ids.append(mid)
    return ids


def _stat_maps(
    year_players: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    return {
        y: dict(p.get("stats") or {}) | dict(p.get("set_piece_stats") or {})
        for y, p in year_players.items()
    }


def _merge_per90(
    metric_id: str,
    year_players: dict[str, dict[str, Any]],
    weights: dict[str, float],
    unavailable: dict[str, set[str]],
) -> float | None:
    num = 0.0
    den = 0.0
    for year, player in year_players.items():
        if metric_id in unavailable.get(year, set()):
            continue
        mins = _minutes(player)
        if mins <= 0:
            continue
        stats = player.get("stats") or {}
        sp = player.get("set_piece_stats") or {}
        rate = _safe_float(stats.get(metric_id))
        if rate is None:
            rate = _safe_float(sp.get(metric_id))
        raw = _raw_from_rate(rate, mins)
        if raw is None:
            continue
        w = float(weights.get(year) or 0.0)
        if w <= 0:
            continue
        num += raw * w
        den += mins * w
    if den <= 0:
        return None
    return num / (den / 90.0)


def _merge_count(
    metric_id: str,
    year_players: dict[str, dict[str, Any]],
    weights: dict[str, float],
    unavailable: dict[str, set[str]],
) -> float | None:
    """Weighted sum of counts (penalties etc.), renormalized by weight sum."""
    total = 0.0
    w_sum = 0.0
    for year, player in year_players.items():
        if metric_id in unavailable.get(year, set()):
            continue
        stats = player.get("stats") or {}
        sp = player.get("set_piece_stats") or {}
        val = _safe_float(stats.get(metric_id))
        if val is None:
            val = _safe_float(sp.get(metric_id))
        if val is None:
            continue
        w = float(weights.get(year) or 0.0)
        if w <= 0:
            continue
        total += val * w
        w_sum += w
    if w_sum <= 0:
        return None
    # Keep on a comparable scale to a single season: divide by max weight among
    # contributing years so a full 3-year presence ≈ recent-year magnitude.
    return total / w_sum


def _pair_raws(
    year: str,
    player: dict[str, Any],
    attempted_id: str | None,
    completed_id: str | None,
    percent_id: str,
    unavailable: set[str],
) -> tuple[float | None, float | None]:
    if percent_id in unavailable:
        return None, None
    mins = _minutes(player)
    stats = dict(player.get("stats") or {})
    stats.update(player.get("set_piece_stats") or {})
    attempted = None
    completed = None
    if attempted_id and attempted_id not in unavailable:
        unit = _metric_unit(attempted_id)
        val = _safe_float(stats.get(attempted_id))
        if val is not None:
            if unit == "per90":
                attempted = _raw_from_rate(val, mins)
            else:
                attempted = val
    if completed_id and completed_id not in unavailable:
        unit = _metric_unit(completed_id)
        val = _safe_float(stats.get(completed_id))
        if val is not None:
            if unit == "per90":
                completed = _raw_from_rate(val, mins)
            else:
                completed = val
    pct = _safe_float(stats.get(percent_id))
    if completed is None and attempted is not None and pct is not None:
        completed = (pct / 100.0) * attempted
    if attempted is None and completed is not None and pct is not None and pct > 0:
        attempted = completed / (pct / 100.0)
    return attempted, completed


def _merge_percent(
    metric_id: str,
    year_players: dict[str, dict[str, Any]],
    weights: dict[str, float],
    unavailable: dict[str, set[str]],
) -> float | None:
    pair = PERCENT_PAIRS.get(metric_id)
    if pair:
        att_id, comp_id = pair
        att_sum = 0.0
        comp_sum = 0.0
        any_pair = False
        for year, player in year_players.items():
            att, comp = _pair_raws(
                year,
                player,
                att_id,
                comp_id,
                metric_id,
                unavailable.get(year, set()),
            )
            w = float(weights.get(year) or 0.0)
            if w <= 0 or att is None or comp is None or att <= 0:
                continue
            att_sum += att * w
            comp_sum += comp * w
            any_pair = True
        if any_pair and att_sum > 0:
            return 100.0 * comp_sum / att_sum

    # Fallback: effective-minutes-weighted average of percentages.
    num = 0.0
    den = 0.0
    for year, player in year_players.items():
        if metric_id in unavailable.get(year, set()):
            continue
        mins = _minutes(player)
        w = float(weights.get(year) or 0.0)
        if mins <= 0 or w <= 0:
            continue
        stats = player.get("stats") or {}
        sp = player.get("set_piece_stats") or {}
        pct = _safe_float(stats.get(metric_id))
        if pct is None:
            pct = _safe_float(sp.get(metric_id))
        if pct is None:
            continue
        eff = mins * w
        num += pct * eff
        den += eff
    if den <= 0:
        return None
    return num / den


def _merge_ratio(
    metric_id: str,
    year_players: dict[str, dict[str, Any]],
    weights: dict[str, float],
    unavailable: dict[str, set[str]],
) -> float | None:
    pair = RATIO_PAIRS.get(metric_id)
    if pair:
        num_id, den_id = pair
        num_sum = 0.0
        den_sum = 0.0
        any_pair = False
        for year, player in year_players.items():
            unavail = unavailable.get(year, set())
            if num_id in unavail or den_id in unavail:
                continue
            mins = _minutes(player)
            w = float(weights.get(year) or 0.0)
            if mins <= 0 or w <= 0:
                continue
            stats = player.get("stats") or {}
            n_rate = _safe_float(stats.get(num_id))
            d_rate = _safe_float(stats.get(den_id))
            n_raw = _raw_from_rate(n_rate, mins)
            d_raw = _raw_from_rate(d_rate, mins)
            if n_raw is None or d_raw is None or d_raw <= 0:
                continue
            num_sum += n_raw * w
            den_sum += d_raw * w
            any_pair = True
        if any_pair and den_sum > 0:
            return num_sum / den_sum

    num = 0.0
    den = 0.0
    for year, player in year_players.items():
        if metric_id in unavailable.get(year, set()):
            continue
        mins = _minutes(player)
        w = float(weights.get(year) or 0.0)
        if mins <= 0 or w <= 0:
            continue
        stats = player.get("stats") or {}
        val = _safe_float(stats.get(metric_id))
        if val is None:
            continue
        eff = mins * w
        num += val * eff
        den += eff
    if den <= 0:
        return None
    return num / den


def merge_stats_for_player(
    year_players: dict[str, dict[str, Any]],
    weights: dict[str, float],
) -> tuple[dict[str, float], dict[str, float], float, float, list[str], bool]:
    """Return merged stats, set-piece stats, minutes, effective_minutes, unavailable, limited."""
    unavailable: dict[str, set[str]] = {}
    limited_any = False
    union_unavailable: set[str] = set()
    for year, player in year_players.items():
        unavail = {str(x) for x in (player.get("stats_unavailable") or []) if str(x)}
        unavailable[year] = unavail
        union_unavailable |= unavail
        if player.get("stats_limited_tracking") or player.get(
            "limited_division_tracking"
        ):
            limited_any = True

    merged: dict[str, float] = {}
    set_piece_ids = set(set_piece_metric_defs())
    sp_merged: dict[str, float] = {}

    for metric_id in _all_metric_ids():
        unit = _metric_unit(metric_id)
        if unit == "per90":
            val = _merge_per90(metric_id, year_players, weights, unavailable)
        elif unit == "percent":
            val = _merge_percent(metric_id, year_players, weights, unavailable)
        elif unit == "ratio":
            val = _merge_ratio(metric_id, year_players, weights, unavailable)
        elif unit == "count":
            val = _merge_count(metric_id, year_players, weights, unavailable)
        else:
            val = _merge_per90(metric_id, year_players, weights, unavailable)
        if val is None:
            continue
        if metric_id in set_piece_ids:
            sp_merged[metric_id] = val
        else:
            merged[metric_id] = val

    total_mins = sum(_minutes(p) for p in year_players.values())
    eff_mins = sum(
        _minutes(p) * float(weights.get(y) or 0.0) for y, p in year_players.items()
    )
    # Metric unavailable in every contributing year stays unavailable.
    still_unavail = [
        mid
        for mid in sorted(union_unavailable)
        if mid not in merged and mid not in sp_merged
    ]
    return merged, sp_merged, total_mins, eff_mins, still_unavail, limited_any


def combined_role_scores(
    scores_by_year: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> dict[str, float]:
    """Weighted average of per-year role scores (renormalized per role)."""
    role_ids: set[str] = set()
    for scores in scores_by_year.values():
        role_ids.update(scores.keys())
    out: dict[str, float] = {}
    for role_id in role_ids:
        num = 0.0
        den = 0.0
        for year, scores in scores_by_year.items():
            if role_id not in scores:
                continue
            w = float(weights.get(year) or 0.0)
            if w <= 0:
                continue
            num += float(scores[role_id]) * w
            den += w
        if den > 0:
            out[role_id] = num / den
    return out


def merge_player_bundle(
    *,
    key: str,
    year_players: dict[str, dict[str, Any]],
    configured: list[str],
    weights: dict[str, float],
    include_stats: bool,
    include_roles: bool,
) -> dict[str, Any]:
    """Build one merged player from per-year parsed players (same identity key)."""
    present = [y for y in YEAR_KEYS if y in year_players and y in configured]
    if not present:
        raise ValueError(f"No year data for {key}")
    # Most recent present year for identity / primary attrs.
    newest = present[-1]
    base = deepcopy(year_players[newest])

    by_year: dict[str, dict[str, Any]] = {}
    for year in present:
        src = year_players[year]
        by_year[year] = _year_snapshot(src)

    for field in IDENTITY_COPY_KEYS:
        if field in base:
            continue
        base[field] = year_players[newest].get(field)

    # Prefer full attrs from newest present year (role parse has full attrs).
    base["attrs"] = dict(year_players[newest].get("attrs") or {})

    status = presence_status(configured, present)
    base["multi_year"] = True
    base["years_present"] = list(present)
    base["multi_year_status"] = status
    base["by_year"] = by_year

    # Role scores use pos_groups; stats exports stamp pos_cards. Keep both filled.
    positions = list(base.get("positions") or [])
    if not positions and base.get("position"):
        from scoring.role_scorer import parse_positions

        positions = parse_positions(base.get("position"))
        base["positions"] = positions
    groups = list(base.get("pos_groups") or []) or list(base.get("pos_cards") or [])
    if not groups and positions:
        from scoring.role_scorer import player_pos_groups

        groups = player_pos_groups(positions)
    if groups:
        base["pos_groups"] = groups
        if not base.get("pos_cards"):
            base["pos_cards"] = list(groups)

    if include_stats:
        stats, sp_stats, total_mins, eff_mins, unavail, limited = merge_stats_for_player(
            {y: year_players[y] for y in present},
            weights,
        )
        base["stats"] = stats
        base["set_piece_stats"] = sp_stats
        base["minutes"] = total_mins
        base["effective_minutes"] = eff_mins
        base["stats_unavailable"] = unavail
        base["stats_limited_tracking"] = limited
        base["limited_division_tracking"] = any(
            bool(year_players[y].get("limited_division_tracking")) for y in present
        )
    else:
        base.pop("stats", None)
        base.pop("set_piece_stats", None)

    if include_roles:
        base["role_scores_by_year"] = {}
        base["role_scores_combined"] = {}
    return base


def _scores_from_row(row: dict[str, Any], role_ids: list[str]) -> dict[str, float]:
    from scoring.role_scorer import role_meta

    out: dict[str, float] = {}
    for role_ref in role_ids:
        val = row.get(role_ref)
        if val is None:
            try:
                col = role_meta(role_ref)["column"]
            except Exception:
                col = role_ref
            val = row.get(col)
        score = _safe_float(val)
        if score is not None:
            out[role_ref] = score
            try:
                out[role_meta(role_ref)["column"]] = score
            except Exception:
                pass
    return out


def attach_role_scores_by_year(
    players: list[dict[str, Any]],
    *,
    role_players_by_year: dict[str, list[dict[str, Any]]],
    role_ids: list[str],
    weights: dict[str, float],
    tier_weights: dict[str, float] | None = None,
    set_piece_profiles: list[dict] | None = None,
) -> None:
    """Batch-score each year's attrs and attach growth + combined scores in-place."""
    scores_index: dict[str, dict[str, dict[str, float]]] = {}
    for year, year_players in role_players_by_year.items():
        if not year_players:
            continue
        rows = score_players(
            year_players,
            role_ids,
            tier_weights=tier_weights,
            set_piece_profiles=set_piece_profiles,
        )
        by_key: dict[str, dict[str, float]] = {}
        for player, row in zip(year_players, rows):
            key = player_row_key(player)
            if not key:
                continue
            by_key[key] = _scores_from_row(row, role_ids)
        scores_index[year] = by_key

    for player in players:
        key = player_row_key(player)
        present = list(player.get("years_present") or [])
        by_year_scores: dict[str, dict[str, float]] = {}
        for year in present:
            scores = (scores_index.get(year) or {}).get(key) or {}
            if scores:
                by_year_scores[year] = scores
        player["role_scores_by_year"] = by_year_scores
        player["role_scores_combined"] = combined_role_scores(by_year_scores, weights)


def merge_year_maps(
    *,
    role_by_year: dict[str, list[dict[str, Any]]] | None,
    stats_by_year: dict[str, list[dict[str, Any]]] | None,
    configured: list[str],
    weights: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge role and/or stats year maps into one player list.

    Returns ``(players, limited_tracking_divisions)``. Role score growth is
    attached later via :func:`attach_role_scores_by_year`.
    """
    weights = dict(weights or DEFAULT_YEAR_WEIGHTS)
    configured = [y for y in YEAR_KEYS if y in configured]
    role_by_year = role_by_year or {}
    stats_by_year = stats_by_year or {}
    include_roles = bool(role_by_year)
    include_stats = bool(stats_by_year)

    role_idx = {y: _index_by_key(players) for y, players in role_by_year.items()}
    stats_idx = {y: _index_by_key(players) for y, players in stats_by_year.items()}

    all_keys: set[str] = set()
    for idx in list(role_idx.values()) + list(stats_idx.values()):
        all_keys.update(idx.keys())

    limited_divs: set[str] = set()
    merged_players: list[dict[str, Any]] = []

    for key in sorted(all_keys):
        year_players: dict[str, dict[str, Any]] = {}
        for year in configured:
            role_p = (role_idx.get(year) or {}).get(key)
            stats_p = (stats_idx.get(year) or {}).get(key)
            if not role_p and not stats_p:
                continue
            if role_p and stats_p:
                combined = deepcopy(stats_p)
                for field in IDENTITY_COPY_KEYS:
                    if combined.get(field) in (None, "", "-", []) and role_p.get(field) not in (
                        None,
                        "",
                        "-",
                        [],
                    ):
                        combined[field] = role_p.get(field)
                if role_p.get("attrs"):
                    combined["attrs"] = dict(role_p["attrs"])
                # Stats parse uses pos_cards; role parse uses pos_groups.
                if not combined.get("pos_groups") and role_p.get("pos_groups"):
                    combined["pos_groups"] = list(role_p["pos_groups"])
                if not combined.get("pos_cards") and combined.get("pos_groups"):
                    combined["pos_cards"] = list(combined["pos_groups"])
                year_players[year] = combined
            elif role_p:
                year_players[year] = deepcopy(role_p)
            else:
                year_players[year] = deepcopy(stats_p)

            src = year_players[year]
            div = str(src.get("division") or "").strip()
            if (
                src.get("limited_division_tracking")
                and div
                and div not in ("-", "—")
            ):
                limited_divs.add(div)

        if not year_players:
            continue
        merged_players.append(
            merge_player_bundle(
                key=key,
                year_players=year_players,
                configured=configured,
                weights=weights,
                include_stats=include_stats,
                include_roles=include_roles,
            )
        )

    return merged_players, sorted(limited_divs)


def pack_signature_bits(entry: dict[str, Any]) -> dict[str, Any]:
    """Extra cache-signature fields for a multi-year pack entry."""
    return {
        "multi_year": True,
        "years": configured_years(entry),
        "weights": year_weights(entry),
    }
