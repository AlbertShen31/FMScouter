"""Shared player detail bodies for modals and the Profiles page."""
from __future__ import annotations

import re

from dash import html

from components.player_modal import player_detail_body
from scoring.role_scorer import (
    ELIGIBILITY_FULL,
    ELIGIBILITY_PARTIAL,
    apply_set_piece_scores,
    default_partial_adjacency,
    normalize_eligibility,
    player_role_highlights,
    score_band,
)
from scoring.stats_scorer import (
    band_metric,
    categories_for_group,
    format_set_piece_metric_display,
    is_gk_group,
    metric_defs,
    metrics_for,
    minutes_color,
    minutes_status,
    percentile_color,
    scoring_set_piece_stats,
    scoring_stats,
    set_piece_metric_defs,
    set_piece_metrics_for_group,
)
import services.ui_settings as us
from components.attr_columns import attr_grid, attr_group_columns, attr_row


def find_parsed_player(
    parsed,
    name: str,
    club: str = "",
    *,
    unique_id: str = "",
) -> dict | None:
    if not parsed or not parsed.get("players"):
        return None
    name = (name or "").strip()
    unique_id = (unique_id or "").strip()
    club = (club or "").strip()
    club_key = "" if club in ("", "-") else club
    if unique_id:
        for player in parsed["players"]:
            if str(player.get("unique_id") or "").strip() == unique_id:
                return player
    for player in parsed["players"]:
        if (player.get("name") or "").strip() != name:
            continue
        if unique_id and str(player.get("unique_id") or "").strip():
            continue
        player_club = (player.get("club") or "").strip()
        if player_club == club_key or (not player_club and not club_key):
            return player
    if name and not unique_id:
        for player in parsed["players"]:
            if (player.get("name") or "").strip() == name:
                return player
    return None


def find_parsed_player_by_key(parsed, player_key: str) -> dict | None:
    from scoring.stats_scorer import player_key as stats_player_key
    from services.player_profiles import split_player_key

    key = str(player_key or "").strip()
    if not key or not parsed or not parsed.get("players"):
        return None
    for player in parsed["players"]:
        if stats_player_key(player) == key:
            return player
    name, rest = split_player_key(key)
    # New keys: Name|Unique ID. Legacy keys: Name|Club.
    if rest and rest.isdigit():
        return find_parsed_player(parsed, name, unique_id=rest)
    return find_parsed_player(parsed, name, rest)


def player_is_gk(player: dict) -> bool:
    groups = {str(g) for g in (player.get("pos_groups") or [])}
    if groups & {"GK", "gk"}:
        return True
    for field in ("best_pos", "position"):
        text = str(player.get(field) or "").upper()
        if re.search(r"\bGK\b", text) or "GOALKEEPER" in text:
            return True
    return False


def _player_attr_row(code: str, label: str, attrs: dict, bands: dict):
    value = attrs.get(code)
    if value is None:
        return attr_row(label, "—", value_class="none")
    band = score_band(float(value), **bands)
    return attr_row(
        label,
        str(value),
        value_class=f"score rs-attr-band-{band}",
    )


def player_attributes(player: dict, settings=None) -> html.Div:
    settings = us.normalize(settings)
    bands = settings["attribute_bands"]
    attrs = player.get("attrs") or {}
    columns = attr_group_columns(
        is_gk=player_is_gk(player),
        make_row=lambda code, label: _player_attr_row(code, label, attrs, bands),
    )
    return html.Div(
        [
            html.Div("Attributes", className="rs-player-id-section-title"),
            attr_grid(columns),
        ],
        className="rs-player-attrs rs-player-id-section",
    )


def _role_highlight_row(phase: str, pick: dict | None, bands: dict) -> html.Div | None:
    if not pick:
        return None
    band = score_band(float(pick["score"]), **bands)
    return html.Div(
        [
            html.Span(phase, className=f"rs-role-fit-phase is-{phase.lower()}"),
            html.Span(
                pick.get("compact") or pick.get("name") or pick.get("code") or "—",
                className="rs-role-fit-name",
                title=pick.get("column") or "",
            ),
            html.Span(
                f"{float(pick['score']):.2f}",
                className=f"rs-role-fit-score rs-band-{band}",
            ),
        ],
        className="rs-role-fit-row",
    )


def player_role_fit_section(player: dict, settings=None) -> html.Div | None:
    settings = us.normalize(settings)
    bands = settings["bands"]
    highlights = player_role_highlights(
        player,
        tier_weights=us.tier_weights(settings),
        partial_adjacency=default_partial_adjacency(),
    )
    blocks = []
    in_best_rows = [
        row
        for row in (
            _role_highlight_row("IP", highlights["in_best"].get("IP"), bands),
            _role_highlight_row("OOP", highlights["in_best"].get("OOP"), bands),
        )
        if row is not None
    ]
    if in_best_rows:
        best_label = highlights.get("best_group_label") or "Best position"
        best_pos = (player.get("best_pos") or "").strip()
        subtitle = best_label
        if best_pos and best_pos != "-":
            subtitle = f"{best_label} · {best_pos}"
        blocks.append(
            html.Div(
                [
                    html.Div(subtitle, className="rs-role-fit-subtitle"),
                    html.Div(in_best_rows, className="rs-role-fit-rows"),
                ],
                className="rs-role-fit-block",
            )
        )
    other_rows = [
        row
        for row in (
            _role_highlight_row("IP", highlights["other"].get("IP"), bands),
            _role_highlight_row("OOP", highlights["other"].get("OOP"), bands),
        )
        if row is not None
    ]
    if other_rows:
        blocks.append(
            html.Div(
                [
                    html.Div(
                        "Other available positions",
                        className="rs-role-fit-subtitle",
                    ),
                    html.Div(other_rows, className="rs-role-fit-rows"),
                ],
                className="rs-role-fit-block",
            )
        )
    if not blocks:
        return None
    return html.Div(
        [
            html.Div("Role fit", className="rs-player-id-section-title"),
            *blocks,
        ],
        className="rs-player-id-section rs-role-fit-section",
    )


def _try_float_score(value) -> float | None:
    if value in (None, "", "-", "—"):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score:
        return None
    return score


def player_set_piece_scores_section(player: dict, settings=None) -> html.Div | None:
    """Computed set-piece scores (Corners, DFK, IFK, …) from player attributes."""
    attrs = player.get("attrs") or {}
    if not isinstance(attrs, dict) or not attrs:
        return None
    settings = us.normalize(settings)
    profiles = us.set_piece_profiles(settings)
    tier_weights = us.tier_weights(settings)
    bands = settings["bands"]
    scores: dict[str, float] = {}
    apply_set_piece_scores(
        scores,
        attrs,
        tier_weights=tier_weights,
        profiles=profiles,
    )
    rows: list[html.Div] = []
    seen_scores: set[str] = set()
    for profile in profiles:
        score_col = profile.get("score")
        if not score_col or score_col in seen_scores:
            continue
        seen_scores.add(score_col)
        score = _try_float_score(scores.get(score_col))
        if score is None or score <= 0:
            continue
        band = score_band(score, **bands)
        label = profile.get("abbr") or profile.get("label") or score_col
        rows.append(
            html.Div(
                [
                    html.Span(label, className="rs-player-id-label"),
                    html.Span(
                        f"{score:.2f}",
                        className=f"rs-player-id-value rs-set-piece-score-val rs-band-{band}",
                        title=profile.get("label") or "",
                    ),
                ],
                className="rs-player-id-item",
            )
        )
    if not rows:
        return None
    return html.Div(
        [
            html.Div("Set pieces", className="rs-player-id-section-title"),
            html.Div(rows, className="rs-player-identity"),
        ],
        className="rs-player-id-section rs-set-piece-scores-section",
    )


def player_set_piece_metrics_section(
    player: dict,
    *,
    eval_group: str | None = None,
) -> html.Div | None:
    """Set-piece stat counts from the Moneyball export (raw values, not percentiles)."""
    group = _normalize_eval_group(player, eval_group)
    stats = scoring_set_piece_stats(player)
    metric_ids = set_piece_metrics_for_group(group)
    if not metric_ids:
        return None
    items: list[html.Div] = []
    for metric_id in metric_ids:
        meta = set_piece_metric_defs().get(metric_id) or {}
        label = str(meta.get("label") or metric_id)
        raw = stats.get(metric_id)
        if raw is None:
            display = "—"
        else:
            display = format_set_piece_metric_display(
                float(raw), str(meta.get("unit") or "")
            )
        items.append(
            html.Div(
                [
                    html.Span(label, className="rs-player-id-label"),
                    html.Span(display, className="rs-player-id-value"),
                ],
                className="rs-player-id-item",
            )
        )
    return html.Div(
        [
            html.Div("Set pieces", className="rs-player-id-section-title"),
            html.Div(items, className="rs-player-identity"),
        ],
        className="rs-player-id-section rs-set-piece-metrics-section",
    )


def player_stats_modal_section(content) -> html.Div:
    """Shared shell for the stats-page chart area (title + controls + metrics)."""
    if isinstance(content, (list, tuple)):
        body_children = [child for child in content if child is not None]
    else:
        body_children = [content] if content is not None else []
    return html.Div(
        [
            html.Div("Player stats", className="rs-player-id-section-title"),
            html.Div(body_children, className="rs-player-stats-body"),
        ],
        className="rs-player-id-section rs-player-stats-section",
    )


def role_player_detail_card(
    player: dict,
    settings=None,
    *,
    position_eligible: str | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> html.Div:
    settings = us.normalize(settings)
    bottom_sections = [
        player_role_fit_section(player, settings),
        player_set_piece_scores_section(player, settings),
        player_attributes(player, settings),
    ]
    return player_detail_body(
        player,
        id_prefix="rs",
        position_eligible=position_eligible,
        modal_fields=us.modal_identity_fields_for("role_scores", settings),
        bottom=[section for section in bottom_sections if section is not None],
        settings=settings,
        theme=theme,
        limited_divisions=limited_divisions,
    )


def _normalize_eval_group(player: dict, group: str | None = None) -> str:
    pg = player.get("pos_group") or "mid"
    if is_gk_group(pg):
        allowed = {"gk"}
        default = "gk"
    else:
        allowed = {"def", "mid", "fwd"}
        default = pg if pg in allowed else "mid"
    g = group or default
    return g if g in allowed else default


def _player_metric_sections(
    player: dict,
    eval_group: str | None = None,
    *,
    threshold_overrides=None,
    metric_p100=None,
    metric_p0=None,
) -> list[dict]:
    skip_metrics = frozenset({"shots_on_target", "conversion_rate"})
    g = _normalize_eval_group(player, eval_group)
    stats = scoring_stats(player)
    sections = []
    for cat in categories_for_group(g):
        metrics = []
        for mid in metrics_for(g, cat["id"], threshold_overrides):
            if mid in skip_metrics:
                continue
            band = band_metric(
                g,
                cat["id"],
                mid,
                stats.get(mid),
                threshold_overrides=threshold_overrides,
                metric_p100=metric_p100,
                metric_p0=metric_p0,
            )
            meta = metric_defs()[mid]
            metrics.append(
                {
                    "id": mid,
                    "label": meta["label"],
                    "abbr": meta["abbr"],
                    "display": band["display"],
                    "percentile": band.get("percentile"),
                    "color": band.get("color"),
                    "missing": band.get("percentile") is None,
                }
            )
        pcts = [
            float(m["percentile"])
            for m in metrics
            if m.get("percentile") is not None
        ]
        avg = sum(pcts) / len(pcts) if pcts else None
        sections.append(
            {
                "id": cat["id"],
                "label": cat["label"],
                "metrics": metrics,
                "avg_percentile": avg,
                "avg_color": percentile_color(avg) if avg is not None else None,
            }
        )
    return sections


def _section_title(cat: dict) -> html.Div:
    avg = cat.get("avg_percentile")
    children: list = [html.Span(cat["label"], className="st-section-title-text")]
    if avg is None:
        children.append(html.Span("Avg —", className="st-section-avg is-missing"))
    else:
        children.append(
            html.Span(
                f"Avg ~{avg:.0f}th",
                className="st-section-avg",
                style={"color": cat.get("avg_color")} if cat.get("avg_color") else None,
                title=f"Average estimated percentile across metrics in {cat['label']}",
            )
        )
    return html.Div(children, className="rs-player-id-section-title st-section-title")


def _metrics_values(sections: list[dict]) -> list:
    blocks = []
    for cat in sections:
        items = []
        for metric in cat["metrics"]:
            if metric["missing"]:
                value = html.Div(
                    [
                        html.Span("No data", className="rs-player-id-value st-metric-nodata"),
                        html.Span("—", className="st-metric-pct is-missing"),
                    ],
                    className="st-metric-row",
                )
            else:
                value = html.Div(
                    [
                        html.Span(
                            metric["display"],
                            className="rs-player-id-value st-metric-val",
                            style={"color": metric["color"]} if metric.get("color") else None,
                        ),
                        html.Span(
                            f"~{metric['percentile']:.0f}th",
                            className="st-metric-pct",
                        ),
                    ],
                    className="st-metric-row",
                )
            items.append(
                html.Div(
                    [
                        html.Span(metric["abbr"], className="st-metric-abbr"),
                        html.Span(metric["label"], className="st-metric-name"),
                        value,
                    ],
                    className="st-metric-item",
                )
            )
        blocks.append(
            html.Div(
                [
                    _section_title(cat),
                    html.Div(items, className="st-metrics-values"),
                ],
                className="rs-player-id-section st-player-values-section",
            )
        )
    return blocks


def _format_minutes_identity(value) -> str:
    if value in (None, "", "-"):
        return "—"
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def stats_player_detail_card(
    player: dict,
    settings=None,
    *,
    minutes_required: float | None = None,
    threshold_overrides=None,
    metric_p100=None,
    metric_p0=None,
    cohort_players=None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> html.Div:
    settings = us.normalize(settings)
    minutes_required = (
        float(minutes_required)
        if minutes_required is not None
        else us.default_minutes_required(settings)
    )
    if (metric_p100 is None or metric_p0 is None) and cohort_players is not None:
        from scoring.stats_scorer import adaptive_bound_options, adaptive_metric_bound_maps

        auto_p0, auto_p100 = adaptive_metric_bound_maps(
            cohort_players,
            threshold_overrides
            if threshold_overrides is not None
            else settings.get("stats_thresholds"),
            **adaptive_bound_options(settings, min_minutes=minutes_required),
        )
        if metric_p0 is None:
            metric_p0 = auto_p0
        if metric_p100 is None:
            metric_p100 = auto_p100
    sections = _player_metric_sections(
        player,
        threshold_overrides=threshold_overrides,
        metric_p100=metric_p100,
        metric_p0=metric_p0,
    )
    status = minutes_status(player.get("minutes"), minutes_required)
    pcts = [
        float(m["percentile"])
        for cat in sections
        for m in cat["metrics"]
        if m.get("percentile") is not None
    ]
    overall_avg = sum(pcts) / len(pcts) if pcts else None
    after_identity: list = []
    set_piece_section = player_set_piece_metrics_section(player)
    if set_piece_section is not None:
        after_identity.append(set_piece_section)
    return player_detail_body(
        player,
        id_prefix="st",
        modal_fields=us.modal_identity_fields_for("player_stats", settings),
        field_styles={
            "minutes": {"color": minutes_color(status)},
            "injury": {"color": "#fbbf24", "fontWeight": "600"},
        },
        field_formatters={"minutes": _format_minutes_identity},
        after_identity=after_identity or None,
        bottom=player_stats_modal_section(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Overall average", className="st-player-switch-label"),
                            html.Span(
                                f"~{overall_avg:.0f}th percentile"
                                if overall_avg is not None
                                else "—",
                                className="st-overall-avg-val",
                                style=(
                                    {"color": percentile_color(overall_avg)}
                                    if overall_avg is not None
                                    else None
                                ),
                            ),
                        ],
                        className="st-overall-avg pf-stats-overall",
                    ),
                    html.Div(_metrics_values(sections), className="st-player-metrics"),
                ]
            )
        ),
        settings=settings,
        limited_divisions=limited_divisions,
    )


def _unavailable_section(title: str, message: str) -> html.Div:
    return html.Div(
        [
            html.Div(title, className="rs-player-id-section-title"),
            html.P(message, className="text-muted small mb-0"),
        ],
        className="rs-player-id-section pf-unavailable-section",
    )


def cache_status_badge(status: dict) -> html.Span:
    tone = {
        "ready": "up-cache ready",
        "stale": "up-cache stale",
        "missing": "up-cache missing",
        "error": "up-cache error",
        "orphan": "up-cache error",
        "n/a": "up-cache na",
    }.get(status.get("status") or "", "up-cache")
    return html.Span(
        status.get("label") or "—",
        className=tone,
        title=status.get("detail") or "",
    )


def profile_detail_body(
    resolved: dict,
    settings=None,
    *,
    view_mode: str = "roles",
) -> html.Div:
    """Compose identity + role + stats sections for the Profiles page modal."""
    settings = us.normalize(settings)
    status = resolved.get("cache_status") or {}
    file_entry = resolved.get("file_entry") or {}
    profile = resolved.get("profile") or {}
    role_column = profile.get("role_column") or resolved.get("role_column") or ""
    source_label = ""
    if file_entry:
        import services.export_library as lib

        source_label = lib.display_label(file_entry)

    header_bits = []
    if source_label:
        header_bits.append(html.Span(source_label, className="pf-source-label"))
    header_bits.append(cache_status_badge(status))
    children = [
        html.Div(header_bits, className="pf-source-row mb-3"),
    ]

    if resolved.get("status") == "orphan":
        children.append(
            html.P(
                "The source CSV was removed from the library. Delete this profile or "
                "re-upload the file and save again.",
                className="text-muted",
            )
        )
        return html.Div(children, className="rs-player-detail pf-player-detail")

    if resolved.get("status") == "player_missing":
        children.append(
            html.P(resolved.get("detail") or "Player not found.", className="text-muted")
        )
        return html.Div(children, className="rs-player-detail pf-player-detail")

    role_player = resolved.get("role_player")
    stats_player = resolved.get("stats_player")
    identity_player = role_player or stats_player
    if not identity_player:
        children.append(html.P("No player data available.", className="text-muted"))
        return html.Div(children, className="rs-player-detail pf-player-detail")

    identity = player_detail_body(
        identity_player,
        id_prefix="pf",
        modal_fields=us.modal_identity_fields_for("role_scores", settings),
        settings=settings,
    )
    children.append(identity)

    show_roles = view_mode != "percentiles"
    show_stats = view_mode != "roles" or not role_column

    if show_roles and role_column:
        role_row = resolved.get("role_row") or {}
        score = role_row.get(role_column)
        try:
            score_f = float(score) if score not in (None, "", "-") else None
        except (TypeError, ValueError):
            score_f = None
        band = score_band(float(score_f), **settings["bands"]) if score_f is not None else None
        elig_level = normalize_eligibility(role_row.get(f"{role_column} eligible"))
        if elig_level == ELIGIBILITY_FULL:
            elig_label, elig_class = "Eligible", " is-yes"
        elif elig_level == ELIGIBILITY_PARTIAL:
            elig_label, elig_class = "Partially eligible", " is-partial"
        else:
            elig_label, elig_class = "Not eligible", " is-no"
        children.append(html.Hr(className="pf-section-divider"))
        children.append(
            html.Div(
                [
                    html.Div("Saved role score", className="rs-player-id-section-title"),
                    html.Div(
                        [
                            html.Span(role_column, className="pf-modal-role-name"),
                            html.Span(
                                f"{score_f:.2f}" if score_f is not None else "—",
                                className=(
                                    f"pf-modal-role-score rs-band-{band}"
                                    if band
                                    else "pf-modal-role-score"
                                ),
                            ),
                            html.Span(
                                elig_label,
                                className="pf-modal-role-elig" + elig_class,
                            ),
                        ],
                        className="pf-modal-role-score-row",
                    ),
                ],
                className="rs-player-id-section pf-modal-role-block",
            )
        )

    if show_roles and role_player and role_player.get("attrs"):
        children.append(html.Hr(className="pf-section-divider"))
        fit = player_role_fit_section(role_player, settings)
        if fit:
            children.append(fit)
        children.append(player_attributes(role_player, settings))
    elif show_roles and file_entry.get("role_scores") and not role_column:
        children.append(
            _unavailable_section(
                "Role scores",
                "Role attributes not found in source CSV.",
            )
        )

    if show_stats and stats_player and stats_player.get("stats"):
        children.append(html.Hr(className="pf-section-divider"))
        cohort = resolved.get("stats_cohort") or None
        metric_p0 = None
        metric_p100 = None
        if cohort:
            from scoring.stats_scorer import adaptive_bound_options, adaptive_metric_bound_maps

            metric_p0, metric_p100 = adaptive_metric_bound_maps(
                cohort,
                settings.get("stats_thresholds"),
                **adaptive_bound_options(settings),
            )
        from scoring.stats_scorer import pos_group_label, resolve_player_pos_group

        stats_player = dict(stats_player)
        stats_player["pos_group"] = resolve_player_pos_group(stats_player)
        phase = resolve_player_pos_group(stats_player)
        phase_label = pos_group_label(phase)
        sections = _player_metric_sections(
            stats_player,
            eval_group=phase,
            metric_p100=metric_p100,
            metric_p0=metric_p0,
        )
        pcts = [
            float(m["percentile"])
            for cat in sections
            for m in cat["metrics"]
            if m.get("percentile") is not None
        ]
        overall_avg = sum(pcts) / len(pcts) if pcts else None
        children.append(
            html.Div(
                [
                    html.Div("Player stats", className="rs-player-id-section-title"),
                    html.Div(
                        f"Percentiles vs {phase_label}",
                        className="pf-percentile-phase-note",
                        title=(
                            f"Banded with {phase_label} thresholds and adaptive "
                            "0th/100th bounds from that phase cohort."
                        ),
                    ),
                    html.Div(
                        [
                            html.Div("Overall average", className="st-player-switch-label"),
                            html.Span(
                                f"~{overall_avg:.0f}th percentile"
                                if overall_avg is not None
                                else "—",
                                className="st-overall-avg-val",
                                style=(
                                    {"color": percentile_color(overall_avg)}
                                    if overall_avg is not None
                                    else None
                                ),
                            ),
                            html.Span(
                                f"vs {phase_label}",
                                className="pf-percentile-phase-tag",
                            ),
                        ],
                        className="st-overall-avg pf-stats-overall",
                    ),
                    html.Div(_metrics_values(sections), className="st-player-metrics"),
                ],
                className="pf-stats-body",
            )
        )
    elif show_stats and file_entry.get("stats"):
        children.append(
            _unavailable_section(
                "Player stats",
                "Stats columns not found in source CSV.",
            )
        )

    return html.Div(children, className="rs-player-detail pf-player-detail")
