"""Role scores page: upload an FM attribute CSV, pick roles, filter, export."""
from __future__ import annotations

import base64
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
import plotly.graph_objects as go

from role_scorer import (
    GROUP_DEFS,
    POS_CARDS,
    foot_match,
    parse_export,
    role_meta,
    role_options,
    score_band,
    score_players,
    scored_csv,
)
from canvas_export import build_canvas
import role_config as rc

register_page(__name__, path="/", name="Role scores")

BINS = [
    ("<9", 0, 9),
    ("9–10", 9, 10),
    ("10–11", 10, 11),
    ("11–12", 11, 12),
    ("12–13", 12, 13),
    ("13–14", 13, 14),
    ("14+", 14, 99),
]

SCORE_COLORS = {
    "elite": ("#dcfce7", "#15803d"),
    "good": ("#dbeafe", "#1d4ed8"),
    "ok": ("#fef3c7", "#b45309"),
    "poor": ("#fee2e2", "#b91c1c"),
}

DEFAULT_BANDS = {"elite": 14.0, "good": 11.0, "ok": 8.0}


def _band_value(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return round(max(0.0, min(20.0, number)) * 2) / 2


def _fmt_cut(number: float) -> str:
    number = _band_value(number, 0.0)
    return str(int(number)) if number == int(number) else f"{number:.1f}"


def _normalize_bands(raw, edited: str | None = None) -> dict[str, float]:
    raw = raw or {}
    elite = _band_value(raw.get("elite"), DEFAULT_BANDS["elite"])
    good = _band_value(raw.get("good"), DEFAULT_BANDS["good"])
    ok = _band_value(raw.get("ok"), DEFAULT_BANDS["ok"])
    if edited == "rs-band-elite":
        if good >= elite:
            good = max(0.5, elite - 0.5)
        if ok >= good:
            ok = max(0.0, good - 0.5)
    elif edited == "rs-band-ok":
        if ok >= good:
            good = min(19.5, ok + 0.5)
        if good >= elite:
            elite = min(20.0, good + 0.5)
    else:
        if good >= elite:
            elite = min(20.0, good + 0.5)
        if ok >= good:
            ok = max(0.0, good - 0.5)
    ok = min(ok, 19.0)
    good = min(max(good, ok + 0.5), 19.5)
    elite = min(max(elite, good + 0.5), 20.0)
    return {"elite": elite, "good": good, "ok": max(0.0, ok)}


def _legend_input(band: str, value: float) -> dcc.Input:
    return dcc.Input(
        id=f"rs-band-{band}",
        type="number",
        value=value,
        min=0,
        max=20,
        step=0.5,
        debounce=True,
        className="rs-legend-input",
    )


def _band_legend(bands: dict | None = None) -> html.Div:
    bands = _normalize_bands(bands)
    chips = []
    for band, label, prefix, editable in (
        ("elite", "Elite", "≥", True),
        ("good", "Good", "≥", True),
        ("ok", "OK", "≥", True),
        ("poor", "Poor", "<", False),
    ):
        if editable:
            cut = [
                html.Span(prefix, className="rs-legend-op"),
                _legend_input(band, bands[band]),
            ]
        else:
            cut = [
                html.Span(
                    f"{prefix} {_fmt_cut(bands['ok'])}",
                    id="rs-poor-cut",
                    className="rs-legend-op",
                )
            ]
        chips.append(
            html.Label(
                [html.Span(label, className="rs-legend-name"), *cut],
                className=f"rs-legend-chip {band}",
                title="Minimum score for this band"
                if editable
                else "Anything below the OK cutoff",
            )
        )
    return html.Div(chips, className="rs-depth-legend")


def _is_dark(theme) -> bool:
    return (theme or "dark") != "light"


def _chart_layout(theme, *, height=240, showlegend=False) -> dict:
    dark = _is_dark(theme)
    font = "#e8eef6" if dark else "#212529"
    grid = "rgba(255,255,255,0.08)" if dark else "#dee2e6"
    return dict(
        height=height,
        margin=dict(l=40, r=20, t=20, b=40),
        font=dict(color=font, family="Inter, Segoe UI, sans-serif"),
        xaxis=dict(title="Score band", gridcolor=grid, zeroline=False, color=font),
        yaxis=dict(title="Player count", gridcolor=grid, zeroline=False, color=font),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        barmode="group",
        legend_title_text="View role",
        showlegend=showlegend,
    )


def _blank_fig(theme):
    fig = go.Figure()
    fig.update_layout(**_chart_layout(theme, height=220))
    return fig


BLANK_FIG = _blank_fig("dark")


def _group_buttons(active: str = "all") -> list:
    buttons = [
        html.Button(
            "All groups",
            id={"type": "rs-group", "group": "all"},
            n_clicks=0,
            className="rs-chip" + (" active" if active == "all" else ""),
        )
    ]
    for group, label, _roles in GROUP_DEFS:
        buttons.append(
            html.Button(
                label,
                id={"type": "rs-group", "group": group},
                n_clicks=0,
                className="rs-chip" + (" active" if active == group else ""),
            )
        )
    return buttons


def _phase_buttons(active: str = "all") -> list:
    buttons = []
    for value, label in (("all", "All"), ("IP", "IP"), ("OOP", "OOP")):
        buttons.append(
            html.Button(
                label,
                id={"type": "rs-phase", "phase": value},
                n_clicks=0,
                className="rs-chip" + (" active" if value == active else ""),
            )
        )
    return buttons


def _role_pills(role_ids: list[str]) -> list:
    pills = []
    for role_id in role_ids:
        meta = role_meta(role_id)
        pills.append(
            html.Button(
                [
                    html.Span(meta["group_abbr"], className="rs-pill-groups"),
                    html.Span(meta["name"], className="rs-pill-code"),
                    html.Span(
                        meta["phase"],
                        className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                    ),
                    html.Span("×", className="rs-pill-x"),
                ],
                id={"type": "rs-pill", "role": role_id},
                n_clicks=0,
                title=meta["compact"],
                className="rs-role-pill",
            )
        )
    return pills


layout = dbc.Container(
    [
        dcc.Store(id="rs-parsed"),
        dcc.Store(id="rs-rows"),
        dcc.Store(id="rs-phase", data="all"),
        dcc.Store(id="rs-group", data="all"),
        dcc.Store(id="rs-pos-filter", data="all"),
        dcc.Store(id="rs-foot-filter", data=""),
        dcc.Store(id="rs-bands", data=DEFAULT_BANDS),
        html.Div(
            [
                html.Button(id={"type": "rs-pos", "pos": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-foot", "foot": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-depth", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-pill", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-group", "group": "_"}, n_clicks=0),
            ],
            hidden=True,
        ),
        dcc.Download(id="rs-download-csv"),
        dcc.Download(id="rs-download-canvas"),
        html.H1("FM26 role scores", className="mt-2 mb-1"),
        html.P(
            "Upload an FM attribute CSV and score FM26 roles (no duties — IP / OOP). "
            "Filter by position, foot, and score band, then download a scored sheet or Cursor canvas.",
            className="text-muted",
        ),
        dbc.Card(
            [
                dbc.CardHeader("1. Upload export"),
                dbc.CardBody(
                    [
                        dcc.Upload(
                            id="rs-upload",
                            children=html.Div(
                                ["Drag a CSV here, or ", html.A("browse")]
                            ),
                            className="rs-upload",
                            multiple=False,
                        ),
                        html.Div(id="rs-upload-status", className="mt-2"),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("2. Weight config"),
                dbc.CardBody(
                    [
                        html.Label("Config file"),
                        dcc.Dropdown(
                            id="rs-config",
                            options=rc.pack_options(),
                            value=rc.active_pack_id(),
                            clearable=False,
                            placeholder="Select a weight config",
                        ),
                        dcc.Interval(id="rs-config-tick", interval=2500),
                        html.Small(
                            "Scores use this file’s key / preferred / useful weights. "
                            "Edit and Save a config on the Role configs page.",
                            className="text-muted",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("3. Roles to evaluate"),
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span("Phase", className="rs-chip-label"),
                                        html.Div(
                                            _phase_buttons("all"),
                                            id="rs-phase-row",
                                            className="rs-chip-row",
                                        ),
                                        html.Button(
                                            "Clear",
                                            id="rs-clear-roles",
                                            n_clicks=0,
                                            className="rs-chip ghost",
                                        ),
                                    ],
                                    className="rs-role-toolbar",
                                ),
                                html.Div(
                                    [
                                        html.Span("Group", className="rs-chip-label"),
                                        html.Div(
                                            _group_buttons("all"),
                                            id="rs-group-row",
                                            className="rs-chip-row wrap",
                                        ),
                                    ],
                                    className="rs-role-toolbar",
                                ),
                            ],
                            className="mb-2",
                        ),
                        dcc.Dropdown(
                            id="rs-roles",
                            options=role_options(),
                            value=[],
                            multi=True,
                            placeholder="Select FM26 roles",
                        ),
                        html.Div(id="rs-role-pills", className="rs-pill-row mt-2"),
                        html.Small(
                            "No roles are selected until you pick them. "
                            "Phase and group filters narrow the list; already-selected roles stay. "
                            "Click a pill to remove it.",
                            className="text-muted",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        html.Div(id="rs-pos-bar"),
        html.Div(
            [
                html.Div(
                    [
                        html.Span("Squad depth", className="rs-depth-heading-label"),
                        _band_legend(),
                    ],
                    className="rs-depth-heading",
                ),
                html.Div(id="rs-summary", className="rs-depth-grid"),
            ],
            id="rs-depth-wrap",
            className="rs-depth-panel",
            hidden=True,
        ),
        dbc.Card(
            [
                dbc.CardHeader("4. Shortlist"),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.Label("View / filter roles"),
                                        dcc.Dropdown(
                                            id="rs-view-role",
                                            multi=True,
                                            placeholder="Select roles to filter",
                                        ),
                                        html.Small(
                                            "Min score and eligible apply to every selected role.",
                                            className="text-muted",
                                        ),
                                    ],
                                    md=4,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Search"),
                                        dbc.Input(
                                            id="rs-search",
                                            type="search",
                                            placeholder="Name, club, position",
                                        ),
                                    ],
                                    md=2,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Max age"),
                                        dcc.Dropdown(
                                            id="rs-age",
                                            options=[
                                                {"label": "Any", "value": 99},
                                                {"label": "21", "value": 21},
                                                {"label": "23", "value": 23},
                                                {"label": "25", "value": 25},
                                                {"label": "27", "value": 27},
                                                {"label": "30", "value": 30},
                                                {"label": "35", "value": 35},
                                            ],
                                            value=99,
                                            clearable=False,
                                        ),
                                    ],
                                    md=2,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Min score"),
                                        dcc.Dropdown(
                                            id="rs-min-score",
                                            options=[
                                                {"label": "Any", "value": 0},
                                                {"label": "11+", "value": 11},
                                                {"label": "12+", "value": 12},
                                                {"label": "12.5+", "value": 12.5},
                                                {"label": "13+", "value": 13},
                                            ],
                                            value=0,
                                            clearable=False,
                                        ),
                                    ],
                                    md=2,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Eligible"),
                                        dbc.Checklist(
                                            id="rs-eligible",
                                            options=[
                                                {
                                                    "label": "Position eligible only",
                                                    "value": "yes",
                                                }
                                            ],
                                            value=["yes"],
                                            switch=True,
                                        ),
                                    ],
                                    md=1,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Rows"),
                                        dcc.Dropdown(
                                            id="rs-page-size",
                                            options=[
                                                {"label": "25", "value": 25},
                                                {"label": "50", "value": 50},
                                                {"label": "100", "value": 100},
                                                {"label": "All", "value": 1000},
                                            ],
                                            value=50,
                                            clearable=False,
                                        ),
                                    ],
                                    md=1,
                                ),
                            ],
                            className="g-2 mb-3",
                        ),
                        dcc.Graph(id="rs-hist", figure=BLANK_FIG, config={"displayModeBar": False}),
                        html.Small(
                            "Horizontal axis is score band; vertical axis is player count. "
                            "Each series is a view role, after the all-role filters.",
                            className="text-muted d-block mb-2",
                        ),
                        dash_table.DataTable(
                            id="rs-table",
                            page_size=50,
                            sort_action="native",
                            filter_action="none",
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "fontFamily": "Inter, Segoe UI, sans-serif",
                                "fontSize": "13px",
                                "padding": "8px",
                                "whiteSpace": "nowrap",
                                "backgroundColor": "transparent",
                                "color": "inherit",
                                "border": "1px solid transparent",
                            },
                            style_header={
                                "fontWeight": "600",
                                "textTransform": "uppercase",
                                "fontSize": "11px",
                                "letterSpacing": "0.04em",
                                "backgroundColor": "transparent",
                                "color": "inherit",
                            },
                            style_data_conditional=[
                                {
                                    "if": {"filter_query": '{Injury} != "-"'},
                                    "backgroundColor": "#fff3cd",
                                }
                            ],
                        ),
                        html.Div(id="rs-table-caption", className="text-muted mt-2"),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("5. Export"),
                dbc.CardBody(
                    [
                        dbc.Button(
                            "Download scored CSV",
                            id="rs-csv-btn",
                            color="primary",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Download Cursor canvas (.tsx)",
                            id="rs-canvas-btn",
                            color="secondary",
                            outline=True,
                        ),
                        html.P(
                            "The canvas file opens beside chat in Cursor. "
                            "Put it in this workspace’s canvases folder, or open the file directly.",
                            className="text-muted mt-2 mb-0",
                        ),
                    ]
                ),
            ],
            className="mb-4",
        ),
    ],
    className="rs-page",
    fluid=True,
)


def _decode_upload(contents: str) -> str:
    _header, _, payload = contents.partition(",")
    raw = base64.b64decode(payload)
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _labels(role_ids: list[str]) -> list[str]:
    return [role_meta(role_id)["column"] for role_id in role_ids]


def _as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _clicked(n_clicks) -> bool:
    return bool(n_clicks) and any(n_clicks)


def _score_styles(role_labels: list[str], bands: dict | None = None, theme: str | None = None) -> list[dict]:
    bands = _normalize_bands(bands)
    elite, good, ok = bands["elite"], bands["good"], bands["ok"]
    injury = "rgba(251, 191, 36, 0.18)" if _is_dark(theme) else "#fff3cd"
    rules = [
        {
            "if": {"filter_query": '{Injury} != "-"'},
            "backgroundColor": injury,
        }
    ]
    for label in role_labels:
        rules.extend(
            [
                {
                    "if": {"filter_query": f"{{{label}}} >= {elite}", "column_id": label},
                    "backgroundColor": SCORE_COLORS["elite"][0],
                    "color": SCORE_COLORS["elite"][1],
                    "fontWeight": "700",
                    "borderRadius": "6px",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= {good} && {{{label}}} < {elite}",
                        "column_id": label,
                    },
                    "backgroundColor": SCORE_COLORS["good"][0],
                    "color": SCORE_COLORS["good"][1],
                    "fontWeight": "700",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= {ok} && {{{label}}} < {good}",
                        "column_id": label,
                    },
                    "backgroundColor": SCORE_COLORS["ok"][0],
                    "color": SCORE_COLORS["ok"][1],
                    "fontWeight": "700",
                },
                {
                    "if": {"filter_query": f"{{{label}}} < {ok}", "column_id": label},
                    "backgroundColor": SCORE_COLORS["poor"][0],
                    "color": SCORE_COLORS["poor"][1],
                    "fontWeight": "700",
                },
            ]
        )
    return rules


def _pos_bar(rows: list[dict], active: str, foot: str) -> html.Div:
    counts = {"all": len(rows)}
    for key, _name, _code, _css in POS_CARDS[1:]:
        counts[key] = sum(1 for row in rows if key in (row.get("PosGroups") or []))
    cards = []
    for key, name, code, css in POS_CARDS:
        count = counts.get(key, 0)
        class_name = f"rs-pos-card {css}" + (" active" if active == key else "")
        children = [html.Span(name, className="rs-pos-name")]
        if code:
            children.append(html.Span(code, className="rs-pos-code"))
        children.append(html.Span(str(count), className="rs-pos-count"))
        cards.append(
            html.Button(
                children,
                id={"type": "rs-pos", "pos": key},
                n_clicks=0,
                className=class_name,
            )
        )
    foot_btns = []
    for key, label in (("foot-L", "Left Foot"), ("foot-B", "Both Feet"), ("foot-R", "Right Foot")):
        foot_btns.append(
            html.Button(
                label,
                id={"type": "rs-foot", "foot": key},
                n_clicks=0,
                className="rs-foot-btn" + (" active" if foot == key else ""),
            )
        )
    return html.Div(
        [
            html.Div(cards, className="rs-pos-cards"),
            html.Div(
                [
                    html.Span("Footedness", className="rs-foot-label"),
                    html.Div(foot_btns, className="rs-foot-btns"),
                ],
                className="rs-pos-utils",
            ),
        ],
        className="rs-pos-bar",
    )


def _depth_panel(
    rows: list[dict],
    role_ids: list[str],
    view_roles: list[str],
    bands: dict | None = None,
) -> list:
    if not rows or not role_ids:
        return []
    bands = _normalize_bands(bands)
    cards = []
    for role_id in role_ids:
        meta = role_meta(role_id)
        column = meta["column"]
        eligible = [row for row in rows if row.get(f"{column} eligible")]
        if not eligible:
            continue
        scores = [float(row.get(column) or 0) for row in eligible]
        avg = sum(scores) / len(scores)
        counts = {"elite": 0, "good": 0, "ok": 0, "poor": 0}
        for score in scores:
            counts[score_band(score, **bands)] += 1
        total = len(scores) or 1
        top = sorted(eligible, key=lambda row: float(row.get(column) or 0), reverse=True)[:3]
        names = " · ".join(player.get("Name", "") for player in top)
        active = " active" if column in view_roles and len(view_roles) == 1 else ""
        cards.append(
            html.Button(
                [
                    html.Div(
                        [
                            html.Span(meta["group_abbr"], className="rs-depth-code"),
                            html.Span(meta["name"], className="rs-depth-name"),
                            html.Span(
                                meta["phase"],
                                className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                            ),
                        ],
                        className="rs-depth-title",
                    ),
                    html.Div(
                        [
                            html.Span("Avg", className="rs-depth-avg-label"),
                            html.Span(
                                f"{avg:.1f}",
                                className=f"rs-depth-avg rs-band-{score_band(avg, **bands)}",
                            ),
                        ],
                        className="rs-depth-avg-row",
                    ),
                    html.Div(
                        [
                            html.Div(
                                className=f"rs-depth-seg {band}",
                                style={"width": f"{counts[band] / total * 100:.1f}%"},
                            )
                            for band in ("elite", "good", "ok", "poor")
                            if counts[band]
                        ],
                        className="rs-depth-bar",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(str(counts[band]), className=f"rs-tier-val {band}"),
                                    html.Div(label, className="rs-tier-lbl"),
                                ],
                                className="rs-tier",
                            )
                            for band, label in (
                                ("elite", "Elite"),
                                ("good", "Good"),
                                ("ok", "OK"),
                                ("poor", "Poor"),
                            )
                        ],
                        className="rs-depth-tiers",
                    ),
                    html.Div(names, className="rs-depth-players"),
                ],
                id={"type": "rs-depth", "role": role_id},
                n_clicks=0,
                className="rs-depth-card" + active,
            )
        )
    return cards


@callback(
    Output("rs-parsed", "data"),
    Output("rs-upload-status", "children"),
    Input("rs-upload", "contents"),
    State("rs-upload", "filename"),
    prevent_initial_call=True,
)
def parse_uploaded(contents, filename):
    if not contents:
        return no_update, no_update
    name = filename or "upload.csv"
    if not name.lower().endswith(".csv"):
        return None, dbc.Alert(
            "Upload the CSV from FM Player Export, not the HTML file.",
            color="warning",
        )
    try:
        players = parse_export(_decode_upload(contents))
    except ValueError as exc:
        return None, dbc.Alert(str(exc), color="danger")
    msg = dbc.Alert(
        f"Loaded {len(players)} players from {name}.",
        color="success",
        className="mb-0",
    )
    return {"filename": name, "players": players}, msg


@callback(
    Output("rs-phase", "data"),
    Output("rs-phase-row", "children"),
    Input({"type": "rs-phase", "phase": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_phase(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    phase = ctx.triggered_id["phase"]
    return phase, _phase_buttons(phase)


@callback(
    Output("rs-group", "data"),
    Output("rs-group-row", "children"),
    Input({"type": "rs-group", "group": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_group(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    group = ctx.triggered_id["group"]
    if group == "_":
        return no_update, no_update
    return group, _group_buttons(group)


@callback(
    Output("rs-roles", "options"),
    Input("rs-phase", "data"),
    Input("rs-group", "data"),
    Input("rs-roles", "value"),
)
def filter_role_options(phase, group, selected):
    return role_options(phase=phase, group=group, keep=_as_list(selected)) or []


@callback(
    Output("rs-role-pills", "children"),
    Input("rs-roles", "value"),
)
def render_pills(role_ids):
    return _role_pills(_as_list(role_ids))


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Input({"type": "rs-pill", "role": ALL}, "n_clicks"),
    State("rs-roles", "value"),
    prevent_initial_call=True,
)
def remove_role(n_clicks, selected):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    role_id = ctx.triggered_id["role"]
    if role_id == "_":
        return no_update
    return [item for item in _as_list(selected) if item != role_id]


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Input("rs-clear-roles", "n_clicks"),
    prevent_initial_call=True,
)
def clear_roles(_clear):
    if not ctx.triggered_id:
        return no_update
    return []


@callback(
    Output("rs-pos-filter", "data"),
    Input({"type": "rs-pos", "pos": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_pos_filter(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    pos = ctx.triggered_id["pos"]
    if pos == "_":
        return no_update
    return pos


@callback(
    Output("rs-foot-filter", "data"),
    Input({"type": "rs-foot", "foot": ALL}, "n_clicks"),
    State("rs-foot-filter", "data"),
    prevent_initial_call=True,
)
def set_foot_filter(n_clicks, current):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    chosen = ctx.triggered_id["foot"]
    if chosen == "_":
        return no_update
    return "" if current == chosen else chosen


@callback(
    Output("rs-bands", "data"),
    Output("rs-band-elite", "value"),
    Output("rs-band-good", "value"),
    Output("rs-band-ok", "value"),
    Output("rs-poor-cut", "children"),
    Input("rs-band-elite", "value"),
    Input("rs-band-good", "value"),
    Input("rs-band-ok", "value"),
    prevent_initial_call=True,
)
def set_bands(elite, good, ok):
    edited = ctx.triggered_id if ctx.triggered_id in {
        "rs-band-elite",
        "rs-band-good",
        "rs-band-ok",
    } else None
    bands = _normalize_bands({"elite": elite, "good": good, "ok": ok}, edited=edited)
    return (
        bands,
        bands["elite"],
        bands["good"],
        bands["ok"],
        f"< {_fmt_cut(bands['ok'])}",
    )


@callback(
    Output("rs-view-role", "value", allow_duplicate=True),
    Input({"type": "rs-depth", "role": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def focus_view_role(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    role = ctx.triggered_id["role"]
    if role == "_":
        return no_update
    return [role_meta(role)["column"]]


@callback(
    Output("rs-config", "options"),
    Input("rs-config-tick", "n_intervals"),
)
def refresh_config_options(_n):
    return rc.pack_options()


@callback(
    Output("rs-rows", "data"),
    Output("rs-view-role", "options"),
    Output("rs-view-role", "value"),
    Input("rs-parsed", "data"),
    Input("rs-roles", "value"),
    Input("rs-config", "value"),
    State("rs-view-role", "value"),
)
def rescore(parsed, role_ids, pack_id, current_view):
    if pack_id:
        rc.load_pack(pack_id)
    if not parsed or not parsed.get("players"):
        return None, [], None
    role_ids = role_ids or []
    if not role_ids:
        return None, [], None
    rows = score_players(parsed["players"], role_ids)
    labels = _labels(role_ids)
    options = []
    for role_id, label in zip(role_ids, labels):
        meta = role_meta(role_id)
        options.append({"label": meta["compact"], "value": label})
    kept = [role for role in _as_list(current_view) if role in labels]
    view = kept or labels
    return (
        {
            "filename": parsed.get("filename", "export.csv"),
            "rows": rows,
            "roles": labels,
            "role_ids": role_ids,
        },
        options,
        view,
    )


@callback(
    Output("rs-pos-bar", "children"),
    Output("rs-summary", "children"),
    Output("rs-depth-wrap", "hidden"),
    Output("rs-table", "data"),
    Output("rs-table", "columns"),
    Output("rs-table", "style_data_conditional"),
    Output("rs-table", "page_size"),
    Output("rs-hist", "figure"),
    Output("rs-table-caption", "children"),
    Input("rs-rows", "data"),
    Input("rs-view-role", "value"),
    Input("rs-search", "value"),
    Input("rs-age", "value"),
    Input("rs-min-score", "value"),
    Input("rs-eligible", "value"),
    Input("rs-pos-filter", "data"),
    Input("rs-foot-filter", "data"),
    Input("rs-page-size", "value"),
    Input("rs-bands", "data"),
    Input("theme", "data"),
)
def render_shortlist(
    payload,
    view_role,
    query,
    max_age,
    min_score,
    eligible,
    pos_filter,
    foot_filter,
    page_size,
    bands,
    theme,
):
    empty_cols = [{"name": "Name", "id": "Name"}]
    empty_style = _score_styles([], theme=theme)
    view_roles = _as_list(view_role)
    page_size = int(page_size or 50)
    bands = _normalize_bands(bands)
    if not payload or not payload.get("rows") or not view_roles:
        return (
            None,
            [],
            True,
            [],
            empty_cols,
            empty_style,
            page_size,
            _blank_fig(theme),
            "Upload a file and pick at least one view role.",
        )
    rows = payload["rows"]
    roles = payload["roles"]
    role_ids = payload.get("role_ids") or []
    query = (query or "").strip().lower()
    max_age = 99 if max_age is None else int(max_age)
    min_score = 0 if min_score is None else float(min_score)
    elig_only = "yes" in (eligible or [])
    pos_filter = pos_filter or "all"
    foot_filter = foot_filter or ""

    filtered = []
    for row in rows:
        if pos_filter != "all" and pos_filter not in (row.get("PosGroups") or []):
            continue
        if foot_filter and not foot_match(row, foot_filter):
            continue
        if elig_only and not all(row.get(f"{role} eligible") for role in view_roles):
            continue
        if int(row.get("Age") or 0) > max_age:
            continue
        if any(float(row.get(role) or 0) < min_score for role in view_roles):
            continue
        if query:
            blob = f"{row.get('Name','')} {row.get('Club','')} {row.get('Position','')} {row.get('Division','')}".lower()
            if query not in blob:
                continue
        filtered.append(row)
    filtered.sort(
        key=lambda row: min(float(row.get(role) or 0) for role in view_roles),
        reverse=True,
    )

    fig = go.Figure()
    for role in view_roles:
        values = [float(row.get(role) or 0) for row in filtered]
        counts = []
        for _label, lo, hi in BINS:
            if hi == 99:
                counts.append(sum(1 for v in values if v >= lo))
            else:
                counts.append(sum(1 for v in values if lo <= v < hi))
        fig.add_bar(x=[b[0] for b in BINS], y=counts, name=role)
    fig.update_layout(**_chart_layout(theme, showlegend=len(view_roles) > 1))

    ordered_roles = view_roles + [role for role in roles if role not in view_roles]
    table_cols = ["Name", "Age", "Position", "Club", "Rec", "Injury"] + ordered_roles
    columns = [{"name": col, "id": col} for col in table_cols]
    table_rows = [{key: row.get(key) for key in table_cols} for row in filtered]
    role_list = ", ".join(view_roles)
    extras = []
    if pos_filter != "all":
        extras.append(pos_filter)
    if foot_filter:
        extras.append({"foot-L": "left foot", "foot-R": "right foot", "foot-B": "both feet"}[foot_filter])
    extra = f" Position/foot: {', '.join(extras)}." if extras else ""
    caption = (
        f"{len(filtered)} of {len(rows)} players meeting min score and eligibility "
        f"on all of: {role_list}.{extra} Sorted by the lowest of those scores. "
        f"Source: {payload.get('filename')}."
    )
    cards = _depth_panel(rows, role_ids, view_roles, bands)
    return (
        _pos_bar(rows, pos_filter, foot_filter),
        cards,
        not cards,
        table_rows,
        columns,
        _score_styles(ordered_roles, bands, theme),
        page_size,
        fig,
        caption,
    )


@callback(
    Output("rs-download-csv", "data"),
    Input("rs-csv-btn", "n_clicks"),
    State("rs-rows", "data"),
    prevent_initial_call=True,
)
def download_csv(n_clicks, payload):
    if not n_clicks or not payload or not payload.get("rows"):
        return no_update
    name = (payload.get("filename") or "role_scores").rsplit(".", 1)[0]
    text = scored_csv(payload["rows"], payload["roles"])
    return dict(content=text, filename=f"{name}_role_scores.csv")


@callback(
    Output("rs-download-canvas", "data"),
    Input("rs-canvas-btn", "n_clicks"),
    State("rs-rows", "data"),
    prevent_initial_call=True,
)
def download_canvas(n_clicks, payload):
    if not n_clicks or not payload or not payload.get("rows"):
        return no_update
    text = build_canvas(
        payload["rows"],
        payload["roles"],
        payload.get("filename") or "FM export",
    )
    return dict(content=text, filename="fm26-role-scores.canvas.tsx")
