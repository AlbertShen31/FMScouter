"""Player-stats modal pane: metric sections, bars/pizzas/values, view controls."""
from __future__ import annotations

from dash import dcc, html
import plotly.graph_objects as go

from scoring.stats_scorer import (
    POS_GROUPS,
    band_metric,
    categories_for_group,
    is_gk_group,
    metric_defs,
    metrics_for,
    percentile_color,
    scoring_stats,
)

EVAL_GROUPS = tuple((key, label) for key, label, _css in POS_GROUPS if key != "all")
EVAL_GROUPS_GK = tuple((key, label) for key, label in EVAL_GROUPS if key == "gk")
EVAL_GROUPS_OUTFIELD = tuple((key, label) for key, label in EVAL_GROUPS if key != "gk")


def _eval_groups_for_player(player: dict | None) -> tuple[tuple[str, str], ...]:
    pg = (player or {}).get("pos_group") or "mid"
    return EVAL_GROUPS_GK if is_gk_group(pg) else EVAL_GROUPS_OUTFIELD


def _normalize_eval_group(
    group: str | None,
    fallback: str | None = "mid",
    *,
    player: dict | None = None,
) -> str:
    options = _eval_groups_for_player(player) if player is not None else EVAL_GROUPS
    allowed = {key for key, _ in options}
    default = fallback or (options[0][0] if options else "mid")
    if default not in allowed:
        default = next(iter(allowed), "mid")
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
    # Present in some threshold packs but unused by Mustermann scoring — omit from
    # modal bars / pizzas / values so charts match the metrics that drive averages.
    skip_metrics = frozenset({"shots_on_target", "conversion_rate"})
    g = _normalize_eval_group(
        eval_group, player.get("pos_group") or "mid", player=player
    )
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
    """Category heading with average percentile badge when available."""
    avg = cat.get("avg_percentile")
    children: list = [html.Span(cat["label"], className="st-section-title-text")]
    if avg is None:
        children.append(
            html.Span("Avg —", className="st-section-avg is-missing")
        )
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


def _seg_switcher(
    *,
    options: list[tuple[str, str]],
    active: str,
    id_key: str,
    id_type: str,
) -> html.Div:
    buttons = []
    for value, label in options:
        buttons.append(
            html.Button(
                label,
                id={"type": id_type, id_key: value},
                n_clicks=0,
                className="st-player-seg-btn"
                + (" active" if active == value else ""),
            )
        )
    return html.Div(buttons, className="st-player-seg")


def _view_switcher(active: str) -> html.Div:
    return _seg_switcher(
        options=[("values", "Values"), ("bars", "Bars"), ("pizzas", "Pizzas")],
        active=active,
        id_key="view",
        id_type="st-player-view",
    )


def _group_switcher(active: str, player: dict | None = None) -> html.Div:
    return _seg_switcher(
        options=list(_eval_groups_for_player(player)),
        active=active,
        id_key="group",
        id_type="st-player-group",
    )

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
                    className="st-metric-value-row",
                )
            else:
                pct = metric["percentile"]
                value = html.Div(
                    [
                        html.Span(
                            metric["display"],
                            className="rs-player-id-value",
                            style={"color": metric["color"]} if metric["color"] else None,
                        ),
                        html.Span(
                            f"~{pct:.0f}th",
                            className="st-metric-pct",
                            title=f"~{pct:.0f}th percentile",
                        ),
                    ],
                    className="st-metric-value-row",
                )
            items.append(
                html.Div(
                    [
                        html.Span(metric["label"], className="rs-player-id-label"),
                        value,
                    ],
                    className="rs-player-id-item",
                )
            )
        blocks.append(
            html.Div(
                [
                    _section_title(cat),
                    html.Div(items, className="rs-player-identity"),
                ],
                className="rs-player-id-section",
            )
        )
    return blocks


PLAYER_CHART_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
    "doubleClick": False,
    "showAxisDragHandles": False,
    "showAxisRangeEntryBoxes": False,
}


def _normalize_player_view(view: str | None) -> str:
    return view if view in ("values", "bars", "pizzas") else "bars"


def _chart_layout(theme: str | None, *, height: int, margin: dict | None = None) -> dict:
    dark = (theme or "dark") != "light"
    return dict(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            color="#f8fafc" if dark else "#0f172a",
            size=14,
            family="IBM Plex Sans, Segoe UI, sans-serif",
        ),
        margin=margin or dict(l=130, r=72, t=12, b=36),
        height=height,
        showlegend=False,
        dragmode=False,
        hovermode="closest",
    )


def _bars_figure(metrics: list[dict], theme: str | None) -> go.Figure:
    dark = (theme or "dark") != "light"
    label_color = "#f8fafc" if dark else "#0f172a"
    muted = "#cbd5e1" if dark else "#475569"
    labels = [m["label"] for m in metrics][::-1]
    pcts = []
    colors = []
    texts = []
    for metric in metrics[::-1]:
        if metric["missing"]:
            pcts.append(0)
            colors.append("rgba(148, 163, 184, 0.35)")
            texts.append("No data")
        else:
            pcts.append(float(metric["percentile"]))
            colors.append(metric["color"] or "rgb(64, 220, 120)")
            texts.append(metric["display"])
    fig = go.Figure(
        go.Bar(
            x=pcts,
            y=labels,
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=texts,
            textposition="outside",
            textfont=dict(color=label_color, size=15),
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:.0f}th pct · %{text}<extra></extra>",
        )
    )
    fig.update_layout(
        **_chart_layout(
            theme,
            height=max(220, 42 * len(metrics) + 64),
            margin=dict(l=168, r=72, t=12, b=36),
        ),
        xaxis=dict(
            range=[0, 112],
            title=None,
            ticksuffix="",
            showgrid=True,
            gridcolor="rgba(148,163,184,0.22)",
            zeroline=False,
            fixedrange=True,
            tickfont=dict(color=muted, size=13),
            title_font=dict(color=muted, size=13),
            domain=[0.02, 1],
        ),
        yaxis=dict(
            automargin=True,
            fixedrange=True,
            tickfont=dict(color=label_color, size=14),
            ticksuffix="   ",
            ticklabelposition="outside",
            ticklabeloverflow="allow",
            ticklabelstandoff=18,
        ),
        bargap=0.18,
        bargroupgap=0.08,
    )
    fig.update_xaxes(title_text="Percentile")
    return fig


def _pizza_radius(percentile: float) -> float:
    """Map 0–100 percentile onto a visible polar radius (0th still a sliver).

    Tops out slightly under 100 so the outer 100% ring stays visible.
    """
    floor = 10.0
    ceiling = 96.0
    p = max(0.0, min(100.0, float(percentile)))
    return floor + (p / 100.0) * (ceiling - floor)


def _pizza_figure(metrics: list[dict], theme: str | None) -> go.Figure:
    dark = (theme or "dark") != "light"
    label_color = "#f8fafc" if dark else "#0f172a"
    muted = "#cbd5e1" if dark else "#475569"
    ring_color = "rgba(226, 232, 240, 0.85)" if dark else "rgba(71, 85, 105, 0.75)"
    missing_fill = "rgba(148, 163, 184, 0.18)" if dark else "rgba(148, 163, 184, 0.22)"
    if not metrics:
        fig = go.Figure()
        fig.update_layout(
            **_chart_layout(theme, height=320, margin=dict(l=40, r=40, t=20, b=20))
        )
        return fig

    n = len(metrics)
    # Full-width wedges so arcs meet with no gaps.
    width = 360.0 / n
    theta = []
    radius = []
    colors = []
    custom = []
    for i, metric in enumerate(metrics):
        theta.append(i * width)
        if metric["missing"]:
            radius.append(5.0)
            colors.append(missing_fill)
            custom.append(f"{metric['abbr']} · No data")
        else:
            pct = float(metric["percentile"])
            radius.append(_pizza_radius(pct))
            colors.append(metric["color"] or ("rgb(61, 255, 136)" if dark else "rgb(22, 163, 74)"))
            custom.append(f"{metric['abbr']} · {metric['display']}<br>{pct:.0f}th pct")

    tickvals = [i * width for i in range(n)]
    ticktext = [metric["abbr"] for metric in metrics]
    # Explicit closed ring at r=100 so the outer percentile bound is always visible.
    ring_theta = list(range(0, 361, 3))
    fig = go.Figure(
        data=[
            go.Barpolar(
                r=radius,
                theta=theta,
                width=[width] * n,
                base=0,
                marker=dict(
                    color=colors,
                    line=dict(
                        color="rgba(15, 23, 42, 0.45)" if dark else "rgba(255,255,255,0.75)",
                        width=1.25,
                    ),
                ),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=custom,
                name="Percentile",
            ),
            go.Scatterpolar(
                r=[100] * len(ring_theta),
                theta=ring_theta,
                mode="lines",
                line=dict(color=ring_color, width=2),
                hoverinfo="skip",
                showlegend=False,
                cliponaxis=False,
            ),
        ]
    )
    fig.update_layout(
        **_chart_layout(theme, height=360, margin=dict(l=48, r=48, t=36, b=36)),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            hole=0.08,
            radialaxis=dict(
                range=[0, 100],
                autorange=False,
                tickvals=[0, 25, 50, 75, 100],
                showticklabels=False,
                ticks="",
                gridcolor="rgba(148,163,184,0.32)",
                gridwidth=1,
                tickfont=dict(color=muted, size=11),
                showline=False,
            ),
            angularaxis=dict(
                rotation=90,
                direction="clockwise",
                period=360,
                tickmode="array",
                tickvals=tickvals,
                ticktext=ticktext,
                showticklabels=True,
                ticks="",
                gridcolor="rgba(148,163,184,0.18)",
                tickfont=dict(color=label_color, size=12),
                showline=False,
            ),
        ),
    )
    return fig


def _pizza_infobox(metrics: list[dict]) -> html.Div:
    rows = []
    for metric in metrics:
        swatch = metric["color"] or "rgba(148, 163, 184, 0.35)"
        if metric["missing"]:
            value = "No data"
            pct = "—"
        else:
            value = metric["display"]
            pct = f"~{metric['percentile']:.0f}th"
        rows.append(
            html.Div(
                [
                    html.Span(
                        className="st-pizza-swatch",
                        style={"background": swatch},
                    ),
                    html.Div(
                        [
                            html.Span(metric["abbr"], className="st-pizza-legend-abbr"),
                            html.Span(metric["label"], className="st-pizza-legend-name"),
                        ],
                        className="st-pizza-legend-text",
                    ),
                    html.Div(
                        [
                            html.Span(
                                value,
                                className="st-pizza-legend-val"
                                + (" is-missing" if metric["missing"] else ""),
                                style=(
                                    None
                                    if metric["missing"] or not metric["color"]
                                    else {"color": metric["color"]}
                                ),
                            ),
                            html.Span(pct, className="st-pizza-legend-pct"),
                        ],
                        className="st-pizza-legend-nums",
                    ),
                ],
                className="st-pizza-legend-row",
            )
        )
    return html.Div(
        [
            html.Div("Metrics", className="st-pizza-infobox-title"),
            html.Div(rows, className="st-pizza-legend"),
        ],
        className="st-pizza-infobox",
    )


def _metrics_bars(sections: list[dict], theme: str | None) -> list:
    blocks = []
    for cat in sections:
        if not cat["metrics"]:
            continue
        blocks.append(
            html.Div(
                [
                    _section_title(cat),
                    dcc.Graph(
                        figure=_bars_figure(cat["metrics"], theme),
                        config=PLAYER_CHART_CONFIG,
                        className="st-player-chart",
                    ),
                ],
                className="rs-player-id-section st-player-chart-section",
            )
        )
    return blocks


def _metrics_pizzas(sections: list[dict], theme: str | None) -> list:
    blocks = []
    for cat in sections:
        if not cat["metrics"]:
            continue
        blocks.append(
            html.Div(
                [
                    _section_title(cat),
                    html.Div(
                        [
                            dcc.Graph(
                                figure=_pizza_figure(cat["metrics"], theme),
                                config={
                                    **PLAYER_CHART_CONFIG,
                                    "staticPlot": True,
                                },
                                className="st-player-chart st-player-pizza",
                            ),
                            _pizza_infobox(cat["metrics"]),
                        ],
                        className="st-pizza-layout",
                    ),
                ],
                className="rs-player-id-section st-player-chart-section",
            )
        )
    return blocks


def _format_minutes_identity(value) -> str:
    if value in (None, "", "-"):
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(num)) if num == int(num) else str(num)


def _overall_avg_banner(sections: list[dict], *, phase_label: str | None = None) -> html.Div:
    """Modal summary: mean of the three category average percentiles."""
    pcts = [
        float(cat["avg_percentile"])
        for cat in sections
        if cat.get("avg_percentile") is not None
    ]
    phase = html.Span(
        f"vs {phase_label}" if phase_label else "",
        className="pf-percentile-phase-tag",
    ) if phase_label else None
    if not pcts:
        children = [
            html.Span("Overall", className="st-overall-label"),
            html.Span("Avg —", className="st-section-avg is-missing"),
        ]
        if phase is not None:
            children.append(phase)
        return html.Div(children, className="st-overall-avg")
    avg = sum(pcts) / len(pcts)
    color = percentile_color(avg)
    children = [
        html.Span("Overall", className="st-overall-label"),
        html.Span(
            f"Avg ~{avg:.0f}th",
            className="st-section-avg",
            style={"color": color} if color else None,
            title=(
                "Average of Defending, Final third / Goalkeeping, "
                "and Possession category averages"
                + (f" (banded as {phase_label})" if phase_label else "")
            ),
        ),
    ]
    if phase is not None:
        children.append(phase)
    return html.Div(children, className="st-overall-avg")


def _percentile_phase_note(eval_group: str) -> html.Div:
    from scoring.stats_scorer import pos_group_label

    label = pos_group_label(eval_group)
    return html.Div(
        f"Percentiles vs {label}",
        className="pf-percentile-phase-note",
        title=(
            f"Overall and category percentiles use {label} benchmark thresholds "
            "and adaptive 0th/100th bounds from that phase cohort in the loaded file."
        ),
    )


def _player_modal_body(
    player: dict,
    minutes_required: float,
    *,
    view: str = "bars",
    eval_group: str | None = None,
    theme: str | None = "dark",
    threshold_overrides=None,
    settings=None,
    metric_p100=None,
    metric_p0=None,
) -> html.Div:
    settings = us.normalize(settings)
    from scoring.stats_scorer import pos_group_label

    view = _normalize_player_view(view)
    eval_group = _normalize_eval_group(
        eval_group, player.get("pos_group") or "mid", player=player
    )
    sections = _player_metric_sections(
        player,
        eval_group,
        threshold_overrides=threshold_overrides,
        metric_p100=metric_p100,
        metric_p0=metric_p0,
    )
    if view == "bars":
        metrics = _metrics_bars(sections, theme)
    elif view == "pizzas":
        metrics = _metrics_pizzas(sections, theme)
    else:
        metrics = _metrics_values(sections)
    status = minutes_status(player.get("minutes"), minutes_required)
    return player_detail_body(
        player,
        id_prefix="st",
        extra_identity_fields=[("Minutes", "minutes")],
        modal_fields=us.modal_identity_fields_for("player_stats", settings) if settings else None,
        field_styles={
            "minutes": {"color": minutes_color(status)},
            "injury": {"color": "#fbbf24", "fontWeight": "600"},
        },
        field_formatters={"minutes": _format_minutes_identity},
        after_identity=[
            html.Div(
                [
                    html.Div("Evaluate as", className="st-player-switch-label"),
                    _group_switcher(eval_group, player),
                ],
                className="st-player-switch-block",
            ),
            html.Div(
                [
                    html.Div("Display", className="st-player-switch-label"),
                    _view_switcher(view),
                ],
                className="st-player-switch-block",
            ),
            _overall_avg_banner(sections, phase_label=pos_group_label(eval_group)),
        ],
        bottom=html.Div(metrics, className="st-player-metrics"),
    )


def stats_charts_bottom_pane(
    player: dict,
    *,
    theme: str | None = "dark",
    view: str = "bars",
    eval_group: str | None = None,
    threshold_overrides=None,
    settings=None,
    metric_p100=None,
    metric_p0=None,
    cohort_players=None,
) -> html.Div:
    """Build the charts portion (overall avg + bars/pizzas/values) for a player.

    This intentionally excludes the identity block so it can be embedded under the
    shared identity sections on the Profiles page.
    """
    # If the underlying profile doesn't have scorable stats (often missing when
    # the profile was created from Role-scores-only exports), show a clear empty
    # state instead of rendering an empty pane.
    if not scoring_stats(player):
        return html.Div(
            "Player stats not available for this profile (missing minutes/stats in source export).",
            className="text-muted small",
        )

    # settings is optional; we only use it as a convenience for callers that store
    # threshold packs there.
    if threshold_overrides is None and settings is not None:
        try:
            threshold_overrides = (settings or {}).get("stats_thresholds")
        except AttributeError:
            threshold_overrides = None

    if (metric_p100 is None or metric_p0 is None) and cohort_players is not None:
        from scoring.stats_scorer import adaptive_metric_bound_maps

        auto_p0, auto_p100 = adaptive_metric_bound_maps(
            cohort_players, threshold_overrides
        )
        if metric_p0 is None:
            metric_p0 = auto_p0
        if metric_p100 is None:
            metric_p100 = auto_p100

    view = _normalize_player_view(view)
    eval_group = _normalize_eval_group(
        eval_group, player.get("pos_group") or "mid", player=player
    )
    sections = _player_metric_sections(
        player,
        eval_group,
        threshold_overrides=threshold_overrides,
        metric_p100=metric_p100,
        metric_p0=metric_p0,
    )
    if view == "bars":
        metrics = _metrics_bars(sections, theme)
    elif view == "pizzas":
        metrics = _metrics_pizzas(sections, theme)
    else:
        metrics = _metrics_values(sections)

    from scoring.stats_scorer import pos_group_label

    phase_label = pos_group_label(eval_group)
    return html.Div(
        [
            _percentile_phase_note(eval_group),
            _overall_avg_banner(sections, phase_label=phase_label),
            html.Div(metrics, className="st-player-metrics"),
        ],
        className="pf-stats-charts-bottom",
    )
