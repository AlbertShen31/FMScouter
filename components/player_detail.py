"""Shared player detail bodies for modals and the Profiles page."""
from __future__ import annotations

import re

from dash import html

from components.player_modal import player_detail_body
from scoring.role_scorer import player_role_highlights, score_band
from scoring.stats_scorer import (
    band_metric,
    categories_for_group,
    is_gk_group,
    metric_defs,
    metrics_for,
    minutes_color,
    minutes_status,
    percentile_color,
    scoring_stats,
)
import services.ui_settings as us
from components.attr_columns import attr_grid, attr_group_columns, attr_row


def find_parsed_player(parsed, name: str, club: str) -> dict | None:
    if not parsed or not parsed.get("players"):
        return None
    name = (name or "").strip()
    club = (club or "").strip()
    club_key = "" if club in ("", "-") else club
    for player in parsed["players"]:
        if (player.get("name") or "").strip() != name:
            continue
        player_club = (player.get("club") or "").strip()
        if player_club == club_key or (not player_club and not club_key):
            return player
    return None


def find_parsed_player_by_key(parsed, player_key: str) -> dict | None:
    from services.player_profiles import split_player_key

    name, club = split_player_key(player_key)
    return find_parsed_player(parsed, name, club)


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
        return attr_row(label, "—", value_class="none", title=code)
    band = score_band(float(value), **bands)
    return attr_row(
        label,
        str(value),
        value_class=f"score rs-band-{band}",
        title=code,
    )


def player_attributes(player: dict, bands: dict) -> html.Div:
    attrs = player.get("attrs") or {}
    columns = attr_group_columns(
        is_gk=player_is_gk(player),
        make_row=lambda code, label: _player_attr_row(code, label, attrs, bands),
    )
    return html.Div(
        [
            html.Div("Attributes", className="rs-player-attrs-title"),
            attr_grid(columns),
        ],
        className="rs-player-attrs",
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


def role_player_detail_card(
    player: dict,
    settings=None,
    *,
    position_eligible: str | None = None,
) -> html.Div:
    settings = us.normalize(settings)
    return player_detail_body(
        player,
        id_prefix="rs",
        position_eligible=position_eligible,
        modal_fields=us.modal_identity_fields_for("role_scores", settings),
        after_identity=player_role_fit_section(player, settings),
        bottom=player_attributes(player, settings["bands"]),
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
) -> html.Div:
    settings = us.normalize(settings)
    minutes_required = (
        float(minutes_required)
        if minutes_required is not None
        else us.default_minutes_required(settings)
    )
    sections = _player_metric_sections(player, threshold_overrides=threshold_overrides)
    status = minutes_status(player.get("minutes"), minutes_required)
    pcts = [
        float(m["percentile"])
        for cat in sections
        for m in cat["metrics"]
        if m.get("percentile") is not None
    ]
    overall_avg = sum(pcts) / len(pcts) if pcts else None
    after_identity = [
        html.Div(
            [
                html.Div("Overall average", className="st-player-switch-label"),
                html.Span(
                    f"~{overall_avg:.0f}th percentile" if overall_avg is not None else "—",
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
    ]
    return player_detail_body(
        player,
        id_prefix="st",
        extra_identity_fields=[("Minutes", "minutes")],
        modal_fields=us.modal_identity_fields_for("player_stats", settings),
        field_styles={
            "minutes": {"color": minutes_color(status)},
            "injury": {"color": "#fbbf24", "fontWeight": "600"},
        },
        field_formatters={"minutes": _format_minutes_identity},
        after_identity=after_identity,
        bottom=html.Div(_metrics_values(sections), className="st-player-metrics"),
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
        eligible = bool(role_row.get(f"{role_column} eligible"))
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
                                "Eligible" if eligible else "Not eligible",
                                className="pf-modal-role-elig"
                                + (" is-yes" if eligible else " is-no"),
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
        children.append(player_attributes(role_player, settings["bands"]))
    elif show_roles and file_entry.get("role_scores") and not role_column:
        children.append(
            _unavailable_section(
                "Role scores",
                "Role attributes not found in source CSV.",
            )
        )

    if show_stats and stats_player and stats_player.get("stats"):
        children.append(html.Hr(className="pf-section-divider"))
        sections = _player_metric_sections(stats_player)
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
