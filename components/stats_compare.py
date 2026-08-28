"""Two-player stats comparison modal and renderers."""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from components.stats_player_pane import (
    EVAL_GROUPS,
    EVAL_GROUPS_GK,
    EVAL_GROUPS_OUTFIELD,
    PLAYER_CHART_CONFIG,
    _chart_layout,
    _limited_tracking_note,
    _missing_metric_label,
    player_metric_sections,
)
from scoring.stats_availability import LIMITED_TRACKING_NOTE
from scoring.stats_scorer import (
    is_gk_group,
    percentile_color,
    pos_group_label,
    resolve_player_pos_group,
    scoring_stats,
)

COMPARE_VIEWS = ("values", "bars")


def normalize_compare_view(view: str | None) -> str:
    return view if view in COMPARE_VIEWS else "bars"


def _players_mixed_gk_outfield(player_a: dict, player_b: dict) -> bool:
    ga = (player_a or {}).get("pos_group") or "mid"
    gb = (player_b or {}).get("pos_group") or "mid"
    return is_gk_group(ga) != is_gk_group(gb)


def compare_eval_groups(
    player_a: dict | None, player_b: dict | None
) -> tuple[tuple[str, str], ...]:
    if _players_mixed_gk_outfield(player_a or {}, player_b or {}):
        return EVAL_GROUPS
    pg = (player_a or {}).get("pos_group") or (player_b or {}).get("pos_group") or "mid"
    return EVAL_GROUPS_GK if is_gk_group(pg) else EVAL_GROUPS_OUTFIELD


def normalize_compare_eval_group(
    group: str | None,
    player_a: dict,
    player_b: dict,
) -> str:
    options = compare_eval_groups(player_a, player_b)
    allowed = {key for key, _ in options}
    default = resolve_player_pos_group(player_a)
    if default not in allowed:
        default = options[0][0] if options else "mid"
    if group is None or str(group).strip() == "":
        return default
    g = str(group).strip()
    return g if g in allowed else default


def default_compare_eval_group(player_a: dict, player_b: dict) -> str:
    """Evaluate-as phase from player A's best position."""
    return normalize_compare_eval_group(None, player_a, player_b)


def _positions_display(player: dict) -> str:
    """Natural + secondary positions for compare chips."""
    positions = player.get("positions")
    if isinstance(positions, list) and positions:
        parts: list[str] = []
        seen: set[tuple[str, str]] = set()
        for item in positions:
            if not isinstance(item, dict):
                continue
            pos = str(item.get("position") or "").strip()
            area = str(item.get("area") or "").strip()
            if not pos:
                continue
            key = (pos, area)
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"{pos} ({area})" if area else pos)
        if parts:
            return ", ".join(parts)
    return str(player.get("position") or "").strip()


def _player_position_lines(player: dict) -> list[str]:
    """All position strings for compare header chips."""
    lines: list[str] = []
    pos_text = _positions_display(player)
    best = str(player.get("best_pos") or "").strip()
    role = str(player.get("position_role") or "").strip()
    if pos_text and pos_text not in ("-", ""):
        lines.append(pos_text)
    elif best and best not in ("-", ""):
        lines.append(best)
    if best and best not in ("-", "") and pos_text and pos_text not in ("-", ""):
        if best.upper() not in pos_text.upper().replace(" ", ""):
            lines.append(f"Best pos: {best}")
    if role and role not in ("-", ""):
        lines.append(role)
    return lines


def _player_chip(player: dict, *, label: str, side: str) -> html.Div:
    name = str(player.get("name") or label or "—")
    club = str(player.get("club") or "").strip()
    minutes = player.get("minutes")
    try:
        mins_txt = str(int(float(minutes))) if minutes not in (None, "", "-") else "—"
    except (TypeError, ValueError):
        mins_txt = str(minutes or "—")
    meta_lines: list[str] = []
    if club:
        meta_lines.append(club)
    meta_lines.extend(_player_position_lines(player))
    if mins_txt != "—":
        meta_lines.append(f"{mins_txt} min")
    return html.Div(
        [
            html.Div(name, className="st-compare-chip-name"),
            html.Div(
                [
                    html.Div(line, className="st-compare-chip-meta-line")
                    for line in meta_lines
                ]
                or [html.Div("—", className="st-compare-chip-meta-line")],
                className="st-compare-chip-meta",
            ),
        ],
        className=f"st-compare-chip st-compare-chip-{side}",
        title=name,
    )


def _compare_seg_switcher(
    *,
    prefix: str,
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


def compare_view_switcher(prefix: str, active: str) -> html.Div:
    return _compare_seg_switcher(
        prefix=prefix,
        options=[("values", "Values"), ("bars", "Bars")],
        active=normalize_compare_view(active),
        id_key="view",
        id_type=f"{prefix}-compare-view",
    )


def compare_group_switcher(
    prefix: str, active: str, player_a: dict, player_b: dict
) -> html.Div:
    return _compare_seg_switcher(
        prefix=prefix,
        options=list(compare_eval_groups(player_a, player_b)),
        active=active,
        id_key="group",
        id_type=f"{prefix}-compare-group",
    )


def _compare_header(
    player_a: dict,
    player_b: dict,
    *,
    label_a: str,
    label_b: str,
) -> html.Div:
    return html.Div(
        [
            _player_chip(player_a, label=label_a, side="a"),
            html.Span("vs", className="st-compare-vs"),
            _player_chip(player_b, label=label_b, side="b"),
        ],
        className="st-compare-header",
    )


def _compare_overall_banner(
    sections_a: list[dict],
    sections_b: list[dict],
    *,
    label_a: str,
    label_b: str,
    phase_label: str | None = None,
) -> html.Div:
    def _avg(sections: list[dict]) -> float | None:
        pcts = [
            float(cat["avg_percentile"])
            for cat in sections
            if cat.get("avg_percentile") is not None
        ]
        return sum(pcts) / len(pcts) if pcts else None

    avg_a = _avg(sections_a)
    avg_b = _avg(sections_b)
    children: list = [html.Span("Overall", className="st-overall-label")]
    for label, avg in ((label_a, avg_a), (label_b, avg_b)):
        if avg is None:
            children.append(
                html.Span(f"{label}: —", className="st-section-avg is-missing")
            )
        else:
            color = percentile_color(avg)
            children.append(
                html.Span(
                    f"{label}: ~{avg:.0f}th",
                    className="st-section-avg",
                    style={"color": color} if color else None,
                )
            )
    if phase_label:
        children.append(
            html.Span(f"vs {phase_label}", className="pf-percentile-phase-tag")
        )
    return html.Div(children, className="st-overall-avg st-compare-overall")


def _compare_section_title(
    cat_a: dict,
    cat_b: dict,
    *,
    label_a: str,
    label_b: str,
) -> html.Div:
    children: list = [
        html.Span(cat_a.get("label") or cat_b.get("label"), className="st-section-title-text")
    ]
    for label, cat in ((label_a, cat_a), (label_b, cat_b)):
        avg = cat.get("avg_percentile")
        if avg is None:
            children.append(html.Span(f"{label}: —", className="st-section-avg is-missing"))
        else:
            children.append(
                html.Span(
                    f"{label}: ~{avg:.0f}th",
                    className="st-section-avg",
                    style={"color": cat["avg_color"]} if cat.get("avg_color") else None,
                )
            )
    return html.Div(children, className="rs-player-id-section-title st-section-title")


def _compare_delta_tie(delta: float) -> bool:
    return abs(delta) < 0.5


def _format_compare_delta(delta: float) -> str:
    if _compare_delta_tie(delta):
        return "−0"
    arrow = "↑" if delta > 0 else "↓"
    return f"{arrow}{abs(delta):.0f}"


def _delta_badge(delta: float) -> html.Span:
    if _compare_delta_tie(delta):
        return html.Span(
            [
                html.Span("−", className="st-compare-delta-arrow", **{"aria-hidden": "true"}),
                html.Span("0", className="st-compare-delta-value"),
            ],
            className=(
                "st-compare-delta-badge st-compare-delta-pill st-compare-delta-tie"
            ),
            title="Same percentile (0 point difference)",
        )
    tone = "up" if delta > 0 else "down"
    arrow = "↑" if delta > 0 else "↓"
    return html.Span(
        [
            html.Span(arrow, className="st-compare-delta-arrow", **{"aria-hidden": "true"}),
            html.Span(
                f"{abs(delta):.0f}",
                className="st-compare-delta-value",
            ),
        ],
        className=(
            "st-compare-delta-badge st-compare-delta-pill "
            f"st-compare-delta-{tone}"
        ),
        title=f"{'+' if delta > 0 else ''}{delta:.0f} percentile points (left vs right player)",
    )


def _compare_player_notes(
    player_a: dict,
    player_b: dict,
    *,
    label_a: str,
    label_b: str,
) -> html.Div | None:
    notes: list = []
    for player, label in ((player_a, label_a), (player_b, label_b)):
        if not scoring_stats(player):
            notes.append(
                html.Div(
                    f"{label}: No stats in export (missing or zero minutes).",
                    className="st-compare-player-note is-missing",
                )
            )
            continue
        if _limited_tracking_note(player) is not None:
            notes.append(
                html.Div(
                    [
                        html.Strong(f"{label}: "),
                        LIMITED_TRACKING_NOTE,
                    ],
                    className="st-compare-player-note is-limited",
                )
            )
    if not notes:
        return None
    return html.Div(notes, className="st-compare-player-notes")


def _metric_ids_union(cat_a: dict, cat_b: dict) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for cat in (cat_a, cat_b):
        for metric in cat.get("metrics") or []:
            mid = metric.get("id")
            if mid and mid not in seen:
                seen.add(mid)
                ids.append(mid)
    return ids


def _empty_metric() -> dict:
    return {"missing": True, "unavailable": False, "label": "", "display": "No data"}


def _metric_cell(metric: dict) -> html.Div:
    if metric["missing"]:
        nodata_label = _missing_metric_label(metric)
        return html.Div(
            [
                html.Span(
                    nodata_label,
                    className="rs-player-id-value st-metric-nodata"
                    + (" is-unavailable" if metric.get("unavailable") else ""),
                ),
                html.Span("—", className="st-metric-pct is-missing"),
            ],
            className="st-metric-value-row",
        )
    pct = metric["percentile"]
    return html.Div(
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


def _metrics_compare_values(
    sections_a: list[dict],
    sections_b: list[dict],
    *,
    label_a: str,
    label_b: str,
) -> list:
    blocks = []
    for cat_a, cat_b in zip(sections_a, sections_b):
        metrics_a = {m["id"]: m for m in cat_a.get("metrics") or []}
        metrics_b = {m["id"]: m for m in cat_b.get("metrics") or []}
        metric_ids = _metric_ids_union(cat_a, cat_b)
        rows = []
        for mid in metric_ids:
            ma = metrics_a.get(mid) or _empty_metric()
            mb = metrics_b.get(mid) or _empty_metric()
            label = ma.get("label") or mb.get("label") or mid
            delta_node = html.Span("—", className="st-compare-delta is-missing")
            pa = ma.get("percentile")
            pb = mb.get("percentile")
            if pa is not None and pb is not None:
                delta = float(pa) - float(pb)
                delta_node = _delta_badge(delta)
            rows.append(
                html.Div(
                    [
                        html.Span(label, className="st-compare-values-label"),
                        html.Div(_metric_cell(ma), className="st-compare-values-col"),
                        html.Div(_metric_cell(mb), className="st-compare-values-col"),
                        html.Div(delta_node, className="st-compare-delta-col"),
                    ],
                    className="st-compare-values-row",
                )
            )
        section_body: list
        if rows:
            section_body = [
                html.Div(
                    [
                        html.Span("", className="st-compare-values-label"),
                        html.Span(label_a, className="st-compare-values-head"),
                        html.Span(label_b, className="st-compare-values-head"),
                        html.Span(
                            "↑↓",
                            className="st-compare-values-head st-compare-values-head-diff",
                            title="Percentile difference (left vs right)",
                        ),
                    ],
                    className="st-compare-values-row st-compare-values-head-row",
                ),
                *rows,
            ]
        else:
            section_body = [
                html.Div(
                    "No metrics in this category.",
                    className="st-compare-section-empty text-muted small",
                )
            ]
        blocks.append(
            html.Div(
                [
                    _compare_section_title(cat_a, cat_b, label_a=label_a, label_b=label_b),
                    html.Div(section_body, className="st-compare-values-grid"),
                ],
                className="rs-player-id-section",
            )
        )
    return blocks


def _align_metric_lists(
    metrics_a: list[dict], metrics_b: list[dict]
) -> tuple[list[dict], list[dict]]:
    cat_a = {"metrics": metrics_a}
    cat_b = {"metrics": metrics_b}
    ids = _metric_ids_union(cat_a, cat_b)
    map_a = {m["id"]: m for m in metrics_a if m.get("id")}
    map_b = {m["id"]: m for m in metrics_b if m.get("id")}
    aligned_a: list[dict] = []
    aligned_b: list[dict] = []
    for mid in ids:
        ma = map_a.get(mid)
        mb = map_b.get(mid)
        ref = ma or mb or _empty_metric()
        label = ref.get("label") or mid
        if ma:
            aligned_a.append(ma)
        else:
            aligned_a.append(
                {
                    **_empty_metric(),
                    "id": mid,
                    "label": label,
                    "abbr": ref.get("abbr") or mid,
                }
            )
        if mb:
            aligned_b.append(mb)
        else:
            aligned_b.append(
                {
                    **_empty_metric(),
                    "id": mid,
                    "label": label,
                    "abbr": ref.get("abbr") or mid,
                }
            )
    return aligned_a, aligned_b


def _bars_figure_compare(
    metrics_a: list[dict],
    metrics_b: list[dict],
    *,
    label_a: str,
    label_b: str,
    theme: str | None,
) -> go.Figure:
    metrics_a, metrics_b = _align_metric_lists(metrics_a, metrics_b)
    dark = (theme or "dark") != "light"
    label_color = "#f8fafc" if dark else "#0f172a"
    muted = "#cbd5e1" if dark else "#475569"
    up_color = "#4ade80" if dark else "#15803d"
    down_color = "#f87171" if dark else "#dc2626"
    tie_color = "#facc15" if dark else "#a16207"
    trace_a_color = "rgba(96, 165, 250, 0.92)" if dark else "rgba(37, 99, 235, 0.85)"
    trace_b_color = "rgba(251, 191, 36, 0.92)" if dark else "rgba(217, 119, 6, 0.85)"

    ordered_pairs = list(zip(metrics_a[::-1], metrics_b[::-1]))
    y_a: list[str] = []
    y_b: list[str] = []
    tick_vals: list[str] = []
    tick_text: list[str] = []
    pcts_a: list[float] = []
    pcts_b: list[float] = []
    texts_a: list[str] = []
    texts_b: list[str] = []
    hover_labels: list[str] = []

    for idx, (ma, mb) in enumerate(ordered_pairs):
        top_id = f"cmp-{idx}-a"
        bot_id = f"cmp-{idx}-b"
        metric_label = ma.get("label") or mb.get("label") or ""
        y_a.append(top_id)
        y_b.append(bot_id)
        tick_vals.extend([bot_id, top_id])
        tick_text.extend(["", metric_label])
        hover_labels.append(metric_label)

        if ma["missing"]:
            pcts_a.append(0)
            texts_a.append(_missing_metric_label(ma))
        else:
            pcts_a.append(float(ma["percentile"]))
            texts_a.append(ma["display"])

        if mb["missing"]:
            pcts_b.append(0)
            texts_b.append(_missing_metric_label(mb))
        else:
            pcts_b.append(float(mb["percentile"]))
            texts_b.append(mb["display"])

        if idx < len(ordered_pairs) - 1:
            tick_vals.append(f"cmp-{idx}-gap")
            tick_text.append("")

    annotations: list[dict] = []
    for idx, (ma, mb) in enumerate(ordered_pairs):
        pa = ma.get("percentile")
        pb = mb.get("percentile")
        if pa is None or pb is None:
            continue
        delta = float(pa) - float(pb)
        if _compare_delta_tie(delta):
            tone_color = tie_color
            pill_bg = "rgba(234, 179, 8, 0.18)" if dark else "rgba(234, 179, 8, 0.12)"
        elif delta > 0:
            tone_color = up_color
            pill_bg = "rgba(34, 197, 94, 0.18)" if dark else "rgba(21, 128, 61, 0.12)"
        else:
            tone_color = down_color
            pill_bg = "rgba(239, 68, 68, 0.18)" if dark else "rgba(220, 38, 38, 0.12)"
        annotations.append(
            dict(
                x=1,
                xref="paper",
                xanchor="right",
                y=f"cmp-{idx}-a",
                yref="y",
                text=_format_compare_delta(delta),
                showarrow=False,
                font=dict(
                    size=14,
                    color=tone_color,
                    family="IBM Plex Sans, Segoe UI, sans-serif",
                ),
                bgcolor=pill_bg,
                bordercolor=tone_color,
                borderwidth=1.5,
                borderpad=5,
            )
        )

    fig = go.Figure(
        data=[
            go.Bar(
                name=label_a,
                x=pcts_a,
                y=y_a,
                orientation="h",
                marker=dict(color=trace_a_color, line=dict(width=0)),
                width=0.82,
                text=texts_a,
                textposition="outside",
                textfont=dict(color=label_color, size=13),
                cliponaxis=False,
                customdata=hover_labels,
                hovertemplate=(
                    f"{label_a}<br>%{{customdata}}<br>"
                    "%{{x:.0f}}th pct · %{text}<extra></extra>"
                ),
            ),
            go.Bar(
                name=label_b,
                x=pcts_b,
                y=y_b,
                orientation="h",
                marker=dict(color=trace_b_color, line=dict(width=0)),
                width=0.82,
                text=texts_b,
                textposition="outside",
                textfont=dict(color=label_color, size=13),
                cliponaxis=False,
                customdata=hover_labels,
                hovertemplate=(
                    f"{label_b}<br>%{{customdata}}<br>"
                    "%{{x:.0f}}th pct · %{text}<extra></extra>"
                ),
            ),
        ]
    )
    group_count = max(len(ordered_pairs), 1)
    spacer_count = max(len(ordered_pairs) - 1, 0)
    row_count = group_count * 2 + spacer_count
    base_layout = _chart_layout(
        theme,
        height=max(260, 28 * row_count + 104),
        margin=dict(l=168, r=104, t=28, b=36),
    )
    base_layout["showlegend"] = True
    fig.update_layout(
        **base_layout,
        annotations=annotations,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(color=label_color, size=12),
            itemclick=False,
            itemdoubleclick=False,
        ),
        xaxis=dict(
            range=[0, 112],
            showgrid=True,
            gridcolor="rgba(148,163,184,0.22)",
            zeroline=False,
            fixedrange=True,
            tickfont=dict(color=muted, size=13),
            domain=[0.02, 1],
        ),
        yaxis=dict(
            type="category",
            categoryorder="array",
            categoryarray=tick_vals,
            tickmode="array",
            tickvals=tick_vals,
            ticktext=tick_text,
            automargin=True,
            fixedrange=True,
            tickfont=dict(color=label_color, size=14),
            ticksuffix="   ",
            ticklabelposition="outside",
            ticklabeloverflow="allow",
            ticklabelstandoff=18,
        ),
        bargap=0.05,
    )
    fig.update_xaxes(title_text="Percentile")
    return fig


def _metrics_compare_bars(
    sections_a: list[dict],
    sections_b: list[dict],
    *,
    label_a: str,
    label_b: str,
    theme: str | None,
) -> list:
    blocks = []
    for cat_a, cat_b in zip(sections_a, sections_b):
        metrics_a = cat_a.get("metrics") or []
        metrics_b = cat_b.get("metrics") or []
        chart_body: html.Div | dcc.Graph
        if not metrics_a and not metrics_b:
            chart_body = html.Div(
                "No metrics in this category.",
                className="st-compare-section-empty text-muted small",
            )
        else:
            chart_body = dcc.Graph(
                figure=_bars_figure_compare(
                    metrics_a,
                    metrics_b,
                    label_a=label_a,
                    label_b=label_b,
                    theme=theme,
                ),
                config=PLAYER_CHART_CONFIG,
                className="st-player-chart st-compare-chart",
            )
        blocks.append(
            html.Div(
                [
                    _compare_section_title(
                        cat_a, cat_b, label_a=label_a, label_b=label_b
                    ),
                    chart_body,
                ],
                className="rs-player-id-section st-player-chart-section",
            )
        )
    return blocks


def stats_compare_modal(*, prefix: str) -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(id=f"{prefix}-compare-modal-title"),
                close_button=True,
            ),
            dbc.ModalBody(
                id=f"{prefix}-compare-modal-body",
                className="rs-player-modal-body st-compare-modal-body",
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id=f"{prefix}-compare-modal-close",
                    n_clicks=0,
                    className="rs-player-modal-close",
                )
            ),
        ],
        id=f"{prefix}-compare-modal",
        is_open=False,
        size="xl",
        centered=False,
        scrollable=True,
        backdrop=True,
        keyboard=True,
        className="rs-player-modal rs-compare-modal",
        content_class_name="rs-player-modal-content rs-compare-modal-content",
    )


def stats_compare_body(
    player_a: dict,
    player_b: dict,
    *,
    label_a: str,
    label_b: str,
    view: str,
    eval_group: str,
    theme: str | None,
    threshold_overrides=None,
    metric_p100_a=None,
    metric_p0_a=None,
    metric_p100_b=None,
    metric_p0_b=None,
    cohort_note: str | None = None,
    prefix: str = "st",
) -> html.Div:
    view = normalize_compare_view(view)
    eval_group = normalize_compare_eval_group(eval_group, player_a, player_b)
    sections_a = player_metric_sections(
        player_a,
        eval_group,
        threshold_overrides=threshold_overrides,
        metric_p100=metric_p100_a,
        metric_p0=metric_p0_a,
    )
    sections_b = player_metric_sections(
        player_b,
        eval_group,
        threshold_overrides=threshold_overrides,
        metric_p100=metric_p100_b,
        metric_p0=metric_p0_b,
    )
    if view == "bars":
        metrics = _metrics_compare_bars(
            sections_a,
            sections_b,
            label_a=label_a,
            label_b=label_b,
            theme=theme,
        )
    else:
        metrics = _metrics_compare_values(
            sections_a,
            sections_b,
            label_a=label_a,
            label_b=label_b,
        )
    phase_label = pos_group_label(eval_group)
    children: list = [
        _compare_header(player_a, player_b, label_a=label_a, label_b=label_b),
        html.Div(
            [
                html.Div(
                    [
                        html.Div("Evaluate as", className="st-player-switch-label"),
                        compare_group_switcher(prefix, eval_group, player_a, player_b),
                    ],
                    className="st-player-switch-block",
                ),
                html.Div(
                    [
                        html.Div("Display", className="st-player-switch-label"),
                        compare_view_switcher(prefix, view),
                    ],
                    className="st-player-switch-block",
                ),
            ],
            className="st-compare-controls",
        ),
        html.Div(
            f"Percentiles vs {phase_label}",
            className="pf-percentile-phase-note",
            title=(
                f"Overall and category percentiles use {phase_label} benchmark thresholds "
                "and adaptive 0th/100th bounds from that phase cohort in the loaded file."
            ),
        ),
    ]
    player_notes = _compare_player_notes(
        player_a, player_b, label_a=label_a, label_b=label_b
    )
    if player_notes is not None:
        children.append(player_notes)
    children.append(
        _compare_overall_banner(
            sections_a,
            sections_b,
            label_a=label_a,
            label_b=label_b,
            phase_label=phase_label,
        )
    )
    if cohort_note:
        children.append(html.Div(cohort_note, className="st-compare-cohort-note"))
    children.append(html.Div(metrics, className="st-player-metrics st-compare-metrics"))
    return html.Div(children, className="st-compare-body")


def compare_title(label_a: str, label_b: str) -> str:
    a = (label_a or "Player A").strip()
    b = (label_b or "Player B").strip()
    return f"{a} vs {b}"


def compare_players_incompatible(player_a: dict, player_b: dict) -> str | None:
    """Return a user-facing reason when GK vs outfield compare is not allowed."""
    from scoring.stats_scorer import is_gk_group, resolve_player_pos_group

    ga = resolve_player_pos_group(player_a or {})
    gb = resolve_player_pos_group(player_b or {})
    if is_gk_group(ga) != is_gk_group(gb):
        return "Cannot compare a goalkeeper to an outfield player."
    return None


def compare_control_state(
    count: int,
    *,
    player_a: dict | None = None,
    player_b: dict | None = None,
) -> tuple[bool, str | None]:
    """Return (button_disabled, warning_message)."""
    if count <= 0:
        return True, None
    if count == 1:
        return True, "Select one more player to compare."
    if count > 2:
        return True, f"{count} players selected — compare supports exactly 2."
    reason = compare_players_incompatible(player_a or {}, player_b or {})
    if reason:
        return True, reason
    return False, None


def compare_status_children(message: str | None) -> html.Div | str:
    if not message:
        return ""
    return html.Div(message, className="st-compare-status is-warning")
