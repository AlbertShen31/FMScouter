"""Player statistics page: Moneyball stats CSV vs MustermannFM benchmarks."""
from __future__ import annotations

import base64
import csv
import io
import re

from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    dash_table,
    dcc,
    html,
    no_update,
    register_page,
)
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import plotly.graph_objects as go

from role_scorer import foot_filter_help, foot_filter_hints, foot_match, to_int
from stats_scorer import (
    POS_GROUPS,
    band_metric,
    benchmarks,
    categories_for_group,
    default_category_for_group,
    default_minutes_required,
    is_gk_category,
    is_gk_group,
    metric_defs,
    metrics_for,
    minutes_color,
    minutes_status,
    parse_stats_export,
    passes_minutes_filter,
    player_key,
)
import ui_settings as us

register_page(__name__, path="/stats", name="Player stats")

BLANK_FIG = go.Figure()
BLANK_FIG.update_layout(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=20, b=40),
    height=240,
)


def _help_icon(tip: str, help_id: str) -> list:
    return [
        html.Span("ⓘ", id=help_id, className="rs-help", role="img", **{"aria-label": "Help"}),
        dbc.Tooltip(tip, target=help_id, placement="top", class_name="rs-help-tooltip"),
    ]


def _upload_status(count: int, filename: str) -> list:
    return [
        html.Span("✓", className="rs-upload-ok"),
        html.Span(f"{count:,} players loaded", className="rs-upload-count"),
        html.Span("·", className="rs-upload-sep"),
        html.Span(filename, className="rs-upload-name", title=filename),
        html.Span("·", className="rs-upload-sep"),
    ]


def _upload_error(message: str) -> html.Div:
    return html.Div(message, className="rs-upload-error")


def _decode_upload(contents: str) -> str:
    _ctype, _, payload = contents.partition(",")
    return base64.b64decode(payload).decode("utf-8-sig", errors="replace")


def _colored_cell(text: str, color: str | None) -> str:
    if not color:
        return text
    return (
        f'<span style="color:{color};font-weight:650;font-variant-numeric:tabular-nums">'
        f"{text}</span>"
    )


def _strip_cell(value) -> str:
    text = "" if value is None else str(value)
    if "<" in text:
        text = re.sub(r"<[^>]+>", "", text)
    return text


TABLE_TEXT_COLS = {"Name", "Position", "Club"}


def _cell_number(value) -> float:
    """Parse a display cell (plain or colored markdown) as a float."""
    text = _strip_cell(value).strip().replace("%", "").replace(",", "").replace(" ", "")
    if not text or text in ("-", "—"):
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _column_sort_key(column_id: str, value) -> tuple:
    if column_id in TABLE_TEXT_COLS:
        text = _strip_cell(value).strip()
        if not text or text in ("-", "—"):
            return (1, "\uffff")
        return (0, text.casefold())
    number = _cell_number(value)
    if number != number:  # NaN
        return (1, float("inf"))
    return (0, number)


def _sort_table_rows(rows: list[dict], sort_by) -> None:
    if not sort_by:
        return
    item = sort_by[0]
    column = item.get("column_id")
    reverse = item.get("direction") == "desc"
    rows.sort(
        key=lambda row: _column_sort_key(column, row.get(column)),
        reverse=reverse,
    )


def _resolve_category(group: str, category: str) -> tuple[str, str]:
    """Pick a valid category for the active position filter.

    GK and outfield categories never map onto each other. Switching into
    Goalkeepers resets to the first GK category when needed; switching to
    any outfield filter (including All) resets to the first outfield one.
    """
    g = "gk" if is_gk_group(group) else (group if group in ("def", "mid", "fwd") else "def")
    cats = categories_for_group(g)
    if any(c["id"] == category for c in cats):
        return g, category
    return g, default_category_for_group(g)


def _band_group_cat(player: dict, view_group: str, view_cat: str) -> tuple[str | None, str | None]:
    """Benchmark group/category for one player under the current view.

    Keepers only use GK categories; outfielders only use outfield ones.
    No cross-domain remapping (e.g. Possession ↛ GK Possession).
    """
    pg = player.get("pos_group") or "mid"
    if view_group not in ("", "all"):
        # Filtered to one pos card — columns already match that domain.
        if is_gk_group(view_group):
            return ("gk", view_cat) if is_gk_group(pg) else (None, None)
        return (pg, view_cat) if not is_gk_group(pg) else (None, None)

    # All players: score each row with its own group, but only when the
    # selected category belongs to that player's domain.
    if is_gk_category(view_cat):
        return ("gk", view_cat) if is_gk_group(pg) else (None, None)
    if is_gk_group(pg):
        return None, None
    return pg, view_cat


def _pos_bar(players: list[dict], active: str) -> html.Div:
    counts = {"all": len(players)}
    for key, _label, _css in POS_GROUPS[1:]:
        counts[key] = sum(1 for p in players if p.get("pos_group") == key)
    cards = []
    for key, label, css in POS_GROUPS:
        class_name = f"rs-pos-card {css}" + (" active" if active == key else "")
        cards.append(
            html.Button(
                [
                    html.Span(label, className="rs-pos-name"),
                    html.Span(str(counts.get(key, 0)), className="rs-pos-count"),
                ],
                id={"type": "st-pos", "key": key},
                n_clicks=0,
                className=class_name,
            )
        )
    return html.Div(
        [html.Div(cards, className="rs-pos-cards")],
        className="rs-pos-bar",
    )


def _category_tabs(group: str, active: str) -> html.Div:
    _g, active = _resolve_category(group, active)
    g = "gk" if is_gk_group(group) else (group if group in ("def", "mid", "fwd") else "def")
    cards = [
        html.Button(
            html.Span(cat["label"], className="rs-pos-name"),
            id={"type": "st-cat", "key": cat["id"]},
            n_clicks=0,
            className="rs-pos-card" + (" active" if cat["id"] == active else ""),
        )
        for cat in categories_for_group(g)
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        html.Span("Category"),
                        className="rs-foot-label",
                    ),
                    html.Div(cards, className="rs-pos-cards"),
                ],
                className="rs-pos-utils",
            )
        ],
        className="rs-pos-bar st-cat-bar",
    )


def _clicked(n_clicks) -> bool:
    return bool(n_clicks) and any(n_clicks)


def _foot_bar(active: str, foot_thresholds) -> html.Div:
    hints = foot_filter_hints(foot_thresholds)
    foot_btns = []
    for key, label in (
        ("foot-L", "Left Foot"),
        ("foot-B", "Both Feet"),
        ("foot-R", "Right Foot"),
    ):
        foot_btns.append(
            html.Button(
                label,
                id={"type": "st-foot", "foot": key},
                n_clicks=0,
                title=hints.get(key, ""),
                className="rs-foot-btn" + (" active" if active == key else ""),
            )
        )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Footedness"),
                            *_help_icon(
                                foot_filter_help(foot_thresholds),
                                "st-help-foot",
                            ),
                        ],
                        className="rs-foot-label",
                    ),
                    html.Div(foot_btns, className="rs-foot-btns"),
                ],
                className="rs-pos-utils",
            )
        ],
        className="rs-pos-bar st-foot-bar",
    )


def _table_css() -> list[dict]:
    return [
        {
            "selector": (
                "td:hover, tr:hover td, tr:hover th, th:hover, "
                "td.focused, td.cell--selected, th.focused, "
                "th.cell--selected"
            ),
            "rule": (
                "background-color: var(--table-hover-bg) !important; "
                "color: var(--table-hover-fg) !important;"
            ),
        },
        {
            "selector": "a",
            "rule": (
                "color: inherit !important; text-decoration: underline; "
                "text-underline-offset: 3px; cursor: pointer;"
            ),
        },
    ]


def _table_base_styles(theme: str | None = None) -> list[dict]:
    dark = (theme or "dark") != "light"
    zebra = "rgba(255,255,255,0.03)" if dark else "rgba(0,0,0,0.025)"
    selected_bg = "rgba(61, 255, 136, 0.14)" if dark else "rgba(34, 139, 87, 0.12)"
    plain = "#f1f5f9" if dark else "#0f172a"
    return [
        {"if": {"row_index": "odd"}, "backgroundColor": zebra},
        {
            "if": {"state": "selected"},
            "backgroundColor": selected_bg,
            "border": "1px solid var(--app-accent)",
        },
        {
            "if": {"column_id": "Name"},
            "fontWeight": "600",
            "textAlign": "left",
            "minWidth": "168px",
            "maxWidth": "240px",
            "borderRight": "1px solid var(--app-line)",
            "cursor": "pointer",
            "color": "var(--app-accent)",
            "textDecoration": "underline",
            "textUnderlineOffset": "3px",
        },
        {
            "if": {"column_id": "Club"},
            "color": plain,
            "textAlign": "left",
            "maxWidth": "200px",
        },
        {
            "if": {"column_id": "Position"},
            "textAlign": "left",
            "color": plain,
        },
        {
            "if": {"column_id": "Age"},
            "color": plain,
            "textAlign": "center",
            "minWidth": "52px",
            "width": "56px",
            "maxWidth": "64px",
        },
        {
            "if": {"column_id": "Minutes"},
            "textAlign": "center",
            "minWidth": "72px",
            "fontWeight": "650",
            "fontVariantNumeric": "tabular-nums",
        },
    ]


def _table_columns(group: str, category: str) -> list[dict]:
    g, cat = _resolve_category(group, category)
    cols = [
        {"name": "Name", "id": "Name"},
        {"name": "Age", "id": "Age"},
        {"name": "Club", "id": "Club"},
        {"name": "Position", "id": "Position"},
        {"name": "Minutes", "id": "Minutes", "presentation": "markdown"},
    ]
    for mid in metrics_for(g, cat):
        abbr = metric_defs()[mid]["abbr"]
        cols.append({"name": abbr, "id": abbr, "presentation": "markdown"})
    return cols


def _build_rows(players, *, group, category, minutes_required) -> list[dict]:
    g, cat = _resolve_category(group, category)
    metric_ids = metrics_for(g, cat)
    rows = []
    for p in players:
        if group not in ("", "all") and p.get("pos_group") != group:
            continue
        status = minutes_status(p.get("minutes"), minutes_required)
        mins = p.get("minutes")
        mins_text = "—" if mins is None else f"{mins:.0f}"
        name = p.get("name") or ""
        row = {
            "Name": name,
            "Age": p.get("age") or "—",
            "Club": p.get("club") or "—",
            "Position": p.get("position") or "—",
            "Minutes": _colored_cell(mins_text, minutes_color(status)),
            "_key": player_key(p),
        }
        stats = p.get("stats") or {}
        bg, bc = _band_group_cat(p, group, cat)
        for mid in metric_ids:
            abbr = metric_defs()[mid]["abbr"]
            if bg is None or bc is None:
                row[abbr] = "—"
                continue
            use_g, use_c = (g, cat) if group not in ("", "all") else (bg, bc)
            if mid not in metrics_for(use_g, use_c):
                row[abbr] = "—"
                continue
            band = band_metric(use_g, use_c, mid, stats.get(mid))
            row[abbr] = _colored_cell(band["display"], band["color"])
        rows.append(row)
    return rows


def _player_modal_body(player: dict, minutes_required: float) -> html.Div:
    g = player.get("pos_group") or "mid"
    status = minutes_status(player.get("minutes"), minutes_required)
    identity = []
    for label, key in (
        ("Age", "age"),
        ("Club", "club"),
        ("Division", "division"),
        ("Nation", "nation"),
        ("Position", "position"),
        ("Best pos", "best_pos"),
        ("Style", "style"),
        ("Minutes", "minutes"),
    ):
        val = player.get(key)
        if val in (None, "", "-"):
            continue
        style = {"color": minutes_color(status)} if key == "minutes" else None
        if key == "minutes":
            text = str(int(val)) if float(val) == int(float(val)) else str(val)
        else:
            text = str(val)
        identity.append(
            html.Div(
                [
                    html.Span(label, className="rs-player-id-label"),
                    html.Span(text, className="rs-player-id-value", style=style),
                ],
                className="rs-player-id-item",
            )
        )
    sections = []
    for cat in categories_for_group(g):
        items = []
        for mid in metrics_for(g, cat["id"]):
            band = band_metric(g, cat["id"], mid, (player.get("stats") or {}).get(mid))
            meta = metric_defs()[mid]
            tip = (
                f"~{band['percentile']:.0f}th percentile"
                if band.get("percentile") is not None
                else None
            )
            items.append(
                html.Div(
                    [
                        html.Span(meta["label"], className="rs-player-id-label"),
                        html.Span(
                            band["display"],
                            className="rs-player-id-value",
                            style={"color": band["color"]} if band["color"] else None,
                            title=tip,
                        ),
                    ],
                    className="rs-player-id-item",
                )
            )
        sections.append(
            html.Div(
                [
                    html.Div(cat["label"], className="rs-player-id-section-title"),
                    html.Div(items, className="rs-player-identity"),
                ],
                className="rs-player-id-section",
            )
        )
    return html.Div(
        [html.Div(identity, className="rs-player-identity"), *sections],
        className="rs-player-detail",
    )


def _filter_players(
    players,
    *,
    pos,
    search,
    max_age,
    minutes_match,
    minutes_required,
    foot,
    foot_thresholds,
):
    q = (search or "").strip().casefold()
    max_age = 99 if max_age is None else int(max_age)
    out = []
    for p in players:
        if pos not in ("", "all") and p.get("pos_group") != pos:
            continue
        if q:
            blob = " ".join(
                str(p.get(k) or "")
                for k in ("name", "club", "position", "best_pos", "division")
            ).casefold()
            if q not in blob:
                continue
        if max_age < 99 and to_int(p.get("age")) > max_age:
            continue
        status = minutes_status(p.get("minutes"), minutes_required)
        if not passes_minutes_filter(status, minutes_match or "any"):
            continue
        row = {
            "Left Foot": p.get("left_foot") or "",
            "Right Foot": p.get("right_foot") or "",
        }
        if foot and not foot_match(row, foot, foot_thresholds):
            continue
        out.append(p)
    return out


def layout(**_kwargs):
    settings = us.load()
    mins_req = default_minutes_required()
    foot_thresholds = settings["foot_thresholds"]
    return html.Div(
        [
            dcc.Interval(id="st-hydrate-tick", interval=50, max_intervals=1),
            dcc.Store(id="st-pos", data="all"),
            dcc.Store(id="st-category", data="defending"),
            dcc.Store(id="st-foot", data=""),
            dcc.Store(id="st-marked", data=[]),
            dcc.Download(id="st-download"),
            html.Div(
                [
                    html.Button(id={"type": "st-pos", "key": "_"}, n_clicks=0),
                    html.Button(id={"type": "st-cat", "key": "_"}, n_clicks=0),
                    html.Button(id={"type": "st-foot", "foot": "_"}, n_clicks=0),
                ],
                hidden=True,
            ),            dbc.Card(
                [
                    dbc.CardHeader("1. Upload statistics export"),
                    dbc.CardBody(
                        [
                            html.Div(
                                dcc.Upload(
                                    id="st-upload",
                                    children=html.Div(
                                        [
                                            "Drag and drop or ",
                                            html.A("select a Moneyball stats CSV"),
                                        ]
                                    ),
                                    className="rs-upload",
                                    multiple=False,
                                ),
                                id="st-upload-wrap",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        id="st-upload-status",
                                        className="rs-upload-status",
                                    ),
                                    html.Div(
                                        dcc.Upload(
                                            id="st-upload-replace",
                                            children=html.Span(
                                                "Replace",
                                                className="rs-upload-replace",
                                            ),
                                            className="rs-upload-replace-wrap",
                                            multiple=False,
                                        ),
                                        id="st-upload-replace-wrap",
                                        hidden=True,
                                    ),
                                ],
                                className="rs-upload-status-row",
                            ),
                            html.P(
                                f"Use the statistics Moneyball export. Benchmarks: {benchmarks()['name']}.",
                                className="text-muted small mb-0 mt-2",
                            ),
                        ]
                    ),
                ],
                className="mb-3 rs-section-card",
            ),
            html.Div(
                [
                    dbc.Card(
                        [
                            dbc.CardHeader("2. Shortlist"),
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div(id="st-pos-bar"),
                                            html.Div(id="st-cat-tabs"),
                                            html.Div(
                                                _foot_bar("", foot_thresholds),
                                                id="st-foot-bar",
                                            ),
                                        ],
                                        className="st-filter-stack",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label("Search", className="rs-field-label"),
                                                    dmc.TextInput(
                                                        id="st-search",
                                                        placeholder="Name, club, position",
                                                    ),
                                                ],
                                                className="rs-filter-search",
                                            ),
                                            html.Div(
                                                [
                                                    html.Label("Max age", className="rs-field-label"),
                                                    dmc.Select(
                                                        id="st-age",
                                                        data=us.age_options(settings),
                                                        value="99",
                                                        clearable=False,
                                                        searchable=False,
                                                    ),
                                                ],
                                                className="rs-filter-age",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Minutes",
                                                                className="rs-field-label",
                                                            ),
                                                            *_help_icon(
                                                                f"Default requirement {mins_req} min. "
                                                                "Green=meet, yellow=≥half, red=below half.",
                                                                "st-help-minutes",
                                                            ),
                                                        ],
                                                        className="rs-field-label-row",
                                                    ),
                                                    html.Div(
                                                        [
                                                            dmc.Select(
                                                                id="st-minutes-match",
                                                                data=[
                                                                    {
                                                                        "label": "Any",
                                                                        "value": "any",
                                                                    },
                                                                    {
                                                                        "label": "Half or more",
                                                                        "value": "half",
                                                                    },
                                                                    {
                                                                        "label": "Meets requirements",
                                                                        "value": "meet",
                                                                    },
                                                                ],
                                                                value="any",
                                                                clearable=False,
                                                                searchable=False,
                                                            ),
                                                            dmc.NumberInput(
                                                                id="st-minutes-required",
                                                                value=mins_req,
                                                                min=0,
                                                                max=20000,
                                                                step=90,
                                                            ),
                                                        ],
                                                        className="st-minutes-fields",
                                                    ),
                                                ],
                                                className="rs-filter-pos-match st-filter-minutes",
                                            ),
                                        ],
                                        className="rs-shortlist-filters-row",
                                    ),
                                    html.Div(
                                        dash_table.DataTable(
                                            id="st-table",
                                            columns=_table_columns("def", "defending"),
                                            data=[],
                                            page_size=50,
                                            page_action="native",
                                            sort_action="custom",
                                            sort_mode="single",
                                            sort_by=[],
                                            sort_as_null=["-", "—", ""],
                                            row_selectable="multi",
                                            selected_rows=[],
                                            filter_action="none",
                                            fill_width=True,
                                            markdown_options={"html": True},
                                            style_table={
                                                "overflowX": "auto",
                                                "borderRadius": "12px",
                                                "width": "100%",
                                                "minWidth": "100%",
                                            },
                                            css=_table_css(),
                                            style_cell={
                                                "fontFamily": "Inter, Segoe UI, sans-serif",
                                                "fontSize": "14px",
                                                "padding": "10px 12px",
                                                "whiteSpace": "nowrap",
                                                "backgroundColor": "transparent",
                                                "color": "var(--app-text)",
                                                "border": "1px solid transparent",
                                                "textAlign": "right",
                                            },
                                            style_cell_conditional=[
                                                {
                                                    "if": {"column_id": "Name"},
                                                    "textAlign": "left",
                                                    "cursor": "pointer",
                                                    "color": "var(--app-accent)",
                                                    "fontWeight": "600",
                                                    "textDecoration": "underline",
                                                    "textUnderlineOffset": "3px",
                                                },
                                                {
                                                    "if": {"column_id": "Position"},
                                                    "textAlign": "left",
                                                },
                                                {
                                                    "if": {"column_id": "Club"},
                                                    "textAlign": "left",
                                                },
                                                {
                                                    "if": {"column_id": "Minutes"},
                                                    "textAlign": "center",
                                                },
                                            ],
                                            style_header={
                                                "fontWeight": "600",
                                                "textTransform": "uppercase",
                                                "fontSize": "12px",
                                                "letterSpacing": "0.04em",
                                                "backgroundColor": "transparent",
                                                "color": "var(--app-text)",
                                                "cursor": "pointer",
                                                "padding": "10px 28px 10px 10px",
                                                "height": "auto",
                                                "minHeight": "46px",
                                                "whiteSpace": "pre-line",
                                                "lineHeight": "1.15",
                                                "verticalAlign": "middle",
                                                "textAlign": "center",
                                                "borderBottom": "2px solid var(--app-line)",
                                            },
                                            style_header_conditional=[
                                                {
                                                    "if": {"column_id": col},
                                                    "textAlign": "left",
                                                }
                                                for col in ("Name", "Position", "Club")
                                            ],
                                            style_data_conditional=_table_base_styles("dark"),
                                        ),
                                        id="st-table-shell",
                                        className="rs-table-shell mt-2",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(id="st-table-caption", className="text-muted"),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Rows per page",
                                                                className="rs-field-label",
                                                            ),
                                                            dmc.Select(
                                                                id="st-page-size",
                                                                data=[
                                                                    {"label": x, "value": x}
                                                                    for x in ("25", "50", "100")
                                                                ],
                                                                value="50",
                                                                clearable=False,
                                                                searchable=False,
                                                            ),
                                                        ],
                                                        className="rs-table-page-size",
                                                    ),
                                                    dmc.Button(
                                                        "Clear marked rows",
                                                        id="st-clear-marks",
                                                        size="sm",
                                                        variant="light",
                                                        disabled=True,
                                                        className="rs-squad-clear-btn",
                                                    ),
                                                ],
                                                className="rs-table-caption-actions",
                                            ),
                                        ],
                                        className="rs-table-caption-row mt-2",
                                    ),
                                    html.Div(
                                        [
                                            dmc.Button(
                                                "Show score distribution",
                                                id="st-hist-toggle",
                                                n_clicks=0,
                                                variant="light",
                                                className="rs-hist-toggle",
                                            ),
                                            html.Div(
                                                dcc.Graph(
                                                    id="st-hist",
                                                    figure=BLANK_FIG,
                                                    config={"displayModeBar": False},
                                                    responsive=True,
                                                    style={"width": "100%", "height": "240px"},
                                                ),
                                                id="st-hist-wrap",
                                                className="rs-hist-wrap",
                                                hidden=True,
                                            ),
                                        ],
                                        className="rs-hist-block",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            dbc.CardHeader("3. Export"),
                            dbc.CardBody(
                                [
                                    dmc.Button(
                                        "Download stats CSV",
                                        id="st-csv-btn",
                                        className="me-2",
                                    ),
                                    dmc.Button(
                                        "Download marked CSV",
                                        id="st-marked-csv-btn",
                                        variant="light",
                                        disabled=True,
                                    ),
                                    html.Div(
                                        id="st-marked-preview",
                                        className="mt-2 text-muted",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                ],
                id="st-main",
                hidden=True,
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle(id="st-player-modal-title")),
                    dbc.ModalBody(
                        id="st-player-modal-body",
                        className="rs-player-modal-body",
                    ),
                    dbc.ModalFooter(
                        dmc.Button(
                            "Close",
                            id="st-player-modal-close",
                            variant="light",
                        )
                    ),
                ],
                id="st-player-modal",
                is_open=False,
                size="lg",
                className="rs-player-modal",
            ),
        ],
        className="rs-page st-page",
    )


@callback(
    Output("st-parsed", "data"),
    Output("st-upload-status", "children"),
    Output("st-upload-wrap", "hidden"),
    Output("st-upload-replace-wrap", "hidden"),
    Output("st-main", "hidden"),
    Input("st-upload", "contents"),
    Input("st-upload-replace", "contents"),
    State("st-upload", "filename"),
    State("st-upload-replace", "filename"),
    prevent_initial_call=True,
)
def on_upload(upload_contents, replace_contents, upload_name, replace_name):
    if ctx.triggered_id == "st-upload-replace":
        contents = replace_contents
        name = replace_name or "upload.csv"
    elif ctx.triggered_id == "st-upload":
        contents = upload_contents
        name = upload_name or "upload.csv"
    else:
        contents = replace_contents or upload_contents
        name = (replace_name or upload_name) or "upload.csv"
    if not contents:
        return no_update, no_update, no_update, no_update, no_update
    if not name.lower().endswith(".csv"):
        return (
            None,
            _upload_error("Upload a Moneyball statistics CSV export."),
            False,
            True,
            True,
        )
    try:
        players = parse_stats_export(_decode_upload(contents))
    except Exception as exc:
        return None, _upload_error(str(exc)), False, True, True
    return (
        {"players": players, "filename": name},
        _upload_status(len(players), name),
        True,
        False,
        False,
    )


@callback(
    Output("st-upload-status", "children", allow_duplicate=True),
    Output("st-upload-wrap", "hidden", allow_duplicate=True),
    Output("st-upload-replace-wrap", "hidden", allow_duplicate=True),
    Output("st-main", "hidden", allow_duplicate=True),
    Input("st-parsed", "data"),
    Input("st-hydrate-tick", "n_intervals"),
    prevent_initial_call="initial_duplicate",
)
def restore_upload_ui(parsed, _tick):
    """Re-show upload status when session-stored CSV survives page navigation."""
    if not parsed or not parsed.get("players"):
        return no_update, no_update, no_update, no_update
    filename = parsed.get("filename") or "export.csv"
    return (
        _upload_status(len(parsed["players"]), filename),
        True,
        False,
        False,
    )


@callback(
    Output("st-pos", "data"),
    Input({"type": "st-pos", "key": ALL}, "n_clicks"),
    State("st-pos", "data"),
    prevent_initial_call=True,
)
def set_pos(n_clicks, current):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    key = ctx.triggered_id.get("key")
    if key == "_":
        return no_update
    return key or current or "all"


@callback(
    Output("st-category", "data"),
    Input({"type": "st-cat", "key": ALL}, "n_clicks"),
    Input("st-pos", "data"),
    State("st-category", "data"),
    prevent_initial_call=True,
)
def set_category(n_clicks, pos, current):
    triggered = ctx.triggered_id
    if triggered == "st-pos" or (
        isinstance(triggered, dict) and triggered.get("type") == "st-pos"
    ):
        _g, cat = _resolve_category(pos or "all", current or "")
        return cat
    if not isinstance(triggered, dict) or not _clicked(n_clicks):
        return no_update
    key = triggered.get("key") or current or ""
    if key == "_":
        return no_update
    _g, cat = _resolve_category(pos or "all", key)
    return cat


@callback(
    Output("st-foot", "data"),
    Input({"type": "st-foot", "foot": ALL}, "n_clicks"),
    State("st-foot", "data"),
    prevent_initial_call=True,
)
def set_foot(n_clicks, current):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    chosen = ctx.triggered_id.get("foot")
    if chosen == "_":
        return no_update
    # Off by default; click the active foot again to clear.
    return "" if current == chosen else chosen


@callback(
    Output("st-age", "data"),
    Output("st-age", "value"),
    Input("ui-settings", "data"),
    State("st-age", "value"),
)
def apply_age_settings(settings, age):
    settings = us.normalize(settings)
    ages = us.age_options(settings)
    return ages, us.clamp_choice(age, ages, "99")


@callback(
    Output("st-pos-bar", "children"),
    Output("st-cat-tabs", "children"),
    Output("st-foot-bar", "children"),
    Output("st-table", "columns"),
    Output("st-table", "data"),
    Output("st-table", "style_data_conditional"),
    Output("st-table", "page_size"),
    Output("st-table", "selected_rows"),
    Output("st-table-caption", "children"),
    Output("st-clear-marks", "disabled"),
    Output("st-marked-csv-btn", "disabled"),
    Output("st-marked-preview", "children"),
    Output("st-hist", "figure"),
    Input("st-parsed", "data"),
    Input("st-pos", "data"),
    Input("st-category", "data"),
    Input("st-search", "value"),
    Input("st-age", "value"),
    Input("st-minutes-match", "value"),
    Input("st-minutes-required", "value"),
    Input("st-foot", "data"),
    Input("st-page-size", "value"),
    Input("st-marked", "data"),
    Input("st-table", "sort_by"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
)
def refresh_table(
    parsed,
    pos,
    category,
    search,
    max_age,
    minutes_match,
    minutes_required,
    foot,
    page_size,
    marked,
    sort_by,
    settings,
    theme,
):
    players = (parsed or {}).get("players") or []
    pos = pos or "all"
    settings = us.normalize(settings)
    minutes_required = float(minutes_required or default_minutes_required())
    g, category = _resolve_category(pos, category or "")

    filtered = _filter_players(
        players,
        pos=pos,
        search=search,
        max_age=max_age,
        minutes_match=minutes_match,
        minutes_required=minutes_required,
        foot=foot or "",
        foot_thresholds=settings["foot_thresholds"],
    )
    rows = _build_rows(
        filtered, group=pos, category=category, minutes_required=minutes_required
    )
    _sort_table_rows(rows, sort_by)
    cols = _table_columns(pos, category)
    marked_set = set(marked or [])
    selected = [i for i, r in enumerate(rows) if r.get("_key") in marked_set]
    page_size_i = int(page_size or 50)
    style_data = _table_base_styles(theme)

    caption = f"{len(rows):,} players"
    if marked_set:
        caption += f" · {len(marked_set)} marked"

    fig = BLANK_FIG
    mids = metrics_for(g, category)
    if mids and filtered:
        mid = mids[0]
        values = [
            float(v)
            for p in filtered
            if (v := (p.get("stats") or {}).get(mid)) is not None
        ]
        if values:
            fig = go.Figure(
                data=[go.Histogram(x=values, nbinsx=20, marker_color="#3b82f6")]
            )
            fig.update_layout(
                template="plotly_dark" if (theme or "dark") != "light" else "plotly_white",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=40, r=20, t=30, b=40),
                height=240,
                title=dict(text=metric_defs()[mid]["label"], font=dict(size=12)),
                xaxis_title=metric_defs()[mid]["abbr"],
                yaxis_title="Players",
            )

    preview = (
        f"{len(marked_set)} player(s) marked"
        if marked_set
        else "No players marked yet."
    )
    foot_filter = foot or ""
    return (
        _pos_bar(players, pos),
        _category_tabs(pos, category),
        _foot_bar(foot_filter, settings["foot_thresholds"]),
        cols,
        rows,
        style_data,
        page_size_i,
        selected,
        caption,
        not bool(marked_set),
        not bool(marked_set),
        preview,
        fig,
    )


@callback(
    Output("st-hist-wrap", "hidden"),
    Output("st-hist-toggle", "children"),
    Input("st-hist-toggle", "n_clicks"),
    State("st-hist-wrap", "hidden"),
)
def toggle_hist(n, hidden):
    if not n:
        return True, "Show score distribution"
    opened = bool(hidden)
    return (not opened), (
        "Hide score distribution" if opened else "Show score distribution"
    )


@callback(
    Output("st-marked", "data", allow_duplicate=True),
    Input("st-clear-marks", "n_clicks"),
    prevent_initial_call=True,
)
def clear_marks(_n):
    return []


@callback(
    Output("st-marked", "data", allow_duplicate=True),
    Input("st-table", "selected_rows"),
    State("st-table", "data"),
    State("st-marked", "data"),
    prevent_initial_call=True,
)
def sync_marks(selected_rows, table_data, marked):
    table_data = table_data or []
    keys_on_page = [r.get("_key") for r in table_data if r.get("_key")]
    marked_set = set(marked or [])
    expected = {i for i, key in enumerate(keys_on_page) if key in marked_set}
    selected = set(selected_rows or [])
    if selected == expected:
        return no_update
    marked_set -= set(keys_on_page)
    for i in selected:
        if 0 <= i < len(keys_on_page) and keys_on_page[i]:
            marked_set.add(keys_on_page[i])
    return sorted(marked_set)


@callback(
    Output("st-player-modal", "is_open"),
    Output("st-player-modal-title", "children"),
    Output("st-player-modal-body", "children"),
    Input("st-table", "active_cell"),
    Input("st-player-modal-close", "n_clicks"),
    State("st-table", "derived_viewport_data"),
    State("st-parsed", "data"),
    State("st-minutes-required", "value"),
    prevent_initial_call=True,
)
def open_player(active_cell, _close, viewport, parsed, minutes_required):
    if ctx.triggered_id == "st-player-modal-close":
        return False, no_update, no_update
    if not active_cell or active_cell.get("column_id") != "Name":
        return no_update, no_update, no_update
    rows = viewport or []
    idx = active_cell.get("row")
    if idx is None or idx >= len(rows):
        return no_update, no_update, no_update
    key = rows[idx].get("_key")
    players = (parsed or {}).get("players") or []
    player = next((p for p in players if player_key(p) == key), None)
    if not player:
        return True, "Player", html.Div("Player not found.")
    return (
        True,
        player.get("name"),
        _player_modal_body(
            player, float(minutes_required or default_minutes_required())
        ),
    )


def _csv_payload(fieldnames, rows) -> dict:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return dict(content=buf.getvalue(), filename="fm_stats_export.csv")


@callback(
    Output("st-download", "data"),
    Input("st-csv-btn", "n_clicks"),
    Input("st-marked-csv-btn", "n_clicks"),
    State("st-parsed", "data"),
    State("st-pos", "data"),
    State("st-category", "data"),
    State("st-search", "value"),
    State("st-age", "value"),
    State("st-minutes-match", "value"),
    State("st-minutes-required", "value"),
    State("st-foot", "data"),
    State("st-marked", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def download_csv(
    _all,
    _marked,
    parsed,
    pos,
    category,
    search,
    max_age,
    minutes_match,
    minutes_required,
    foot,
    marked,
    settings,
):
    players = (parsed or {}).get("players") or []
    if not players:
        return no_update
    settings = us.normalize(settings)
    minutes_required = float(minutes_required or default_minutes_required())
    pos = pos or "all"
    _g, category = _resolve_category(pos, category or "")
    filtered = _filter_players(
        players,
        pos=pos,
        search=search,
        max_age=max_age,
        minutes_match=minutes_match,
        minutes_required=minutes_required,
        foot=foot or "",
        foot_thresholds=settings["foot_thresholds"],
    )
    if ctx.triggered_id == "st-marked-csv-btn":
        marked_set = set(marked or [])
        filtered = [p for p in filtered if player_key(p) in marked_set]
    table_rows = _build_rows(
        filtered, group=pos, category=category, minutes_required=minutes_required
    )
    fieldnames = [c["id"] for c in _table_columns(pos, category)]
    export_rows = [{k: _strip_cell(r.get(k)) for k in fieldnames} for r in table_rows]
    return _csv_payload(fieldnames, export_rows)
