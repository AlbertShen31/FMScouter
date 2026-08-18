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
    DEFAULT_ROLES,
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

BLANK_FIG = go.Figure()
BLANK_FIG.update_layout(
    height=220,
    margin=dict(l=40, r=20, t=20, b=40),
    xaxis_title="Score band",
    yaxis_title="Player count",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)


def _phase_buttons(active: str = "all") -> list:
    buttons = []
    for value, label in (("all", "All"), ("IP", "IP"), ("OOP", "OOP"), ("GK", "GK")):
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
                    html.Span(meta["code"], className="rs-pill-code"),
                    html.Span(
                        meta["phase"],
                        className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                    ),
                    html.Span("×", className="rs-pill-x"),
                ],
                id={"type": "rs-pill", "role": role_id},
                n_clicks=0,
                title=f"{meta['name']} · {meta['phase']}",
                className="rs-role-pill",
            )
        )
    return pills


layout = dbc.Container(
    [
        dcc.Store(id="rs-parsed"),
        dcc.Store(id="rs-rows"),
        dcc.Store(id="rs-phase", data="all"),
        dcc.Store(id="rs-pos-filter", data="all"),
        dcc.Store(id="rs-foot-filter", data=""),
        html.Div(
            [
                html.Button(id={"type": "rs-pos", "pos": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-foot", "foot": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-depth", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-pill", "role": "_"}, n_clicks=0),
            ],
            hidden=True,
        ),
        dcc.Download(id="rs-download-csv"),
        dcc.Download(id="rs-download-canvas"),
        html.H1("FM26 role scores", className="mt-2 mb-1"),
        html.P(
            "Upload an FM attribute CSV and score FM26 roles (no duties — IP / OOP / GK). "
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
                                html.Span("Phase", className="rs-chip-label"),
                                html.Div(
                                    _phase_buttons("all"),
                                    id="rs-phase-row",
                                    className="rs-chip-row",
                                ),
                                html.Button(
                                    "Reset defaults",
                                    id="rs-reset-roles",
                                    n_clicks=0,
                                    className="rs-chip ghost",
                                ),
                                html.Button(
                                    "Clear",
                                    id="rs-clear-roles",
                                    n_clicks=0,
                                    className="rs-chip ghost",
                                ),
                            ],
                            className="rs-role-toolbar mb-2",
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
                            "Reset defaults loads SKP, BCB, WB, CM, CHM, IF. "
                            "Click a pill to remove it.",
                            className="text-muted",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        html.Div(id="rs-pos-bar"),
        html.Div(id="rs-summary"),
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
                            },
                            style_header={
                                "fontWeight": "600",
                                "backgroundColor": "#f8f9fa",
                                "textTransform": "uppercase",
                                "fontSize": "11px",
                                "letterSpacing": "0.04em",
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


def _score_styles(role_labels: list[str]) -> list[dict]:
    rules = [
        {
            "if": {"filter_query": '{Injury} != "-"'},
            "backgroundColor": "#fff3cd",
        }
    ]
    for label in role_labels:
        rules.extend(
            [
                {
                    "if": {"filter_query": f"{{{label}}} >= 14", "column_id": label},
                    "backgroundColor": SCORE_COLORS["elite"][0],
                    "color": SCORE_COLORS["elite"][1],
                    "fontWeight": "700",
                    "borderRadius": "6px",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= 11 && {{{label}}} < 14",
                        "column_id": label,
                    },
                    "backgroundColor": SCORE_COLORS["good"][0],
                    "color": SCORE_COLORS["good"][1],
                    "fontWeight": "700",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= 8 && {{{label}}} < 11",
                        "column_id": label,
                    },
                    "backgroundColor": SCORE_COLORS["ok"][0],
                    "color": SCORE_COLORS["ok"][1],
                    "fontWeight": "700",
                },
                {
                    "if": {"filter_query": f"{{{label}}} < 8", "column_id": label},
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
            html.Div(foot_btns, className="rs-pos-utils"),
        ],
        className="rs-pos-bar",
    )


def _depth_panel(rows: list[dict], role_ids: list[str], view_roles: list[str]) -> html.Div | None:
    if not rows or not role_ids:
        return None
    cards = []
    for role_id in role_ids:
        meta = role_meta(role_id)
        column = meta["column"]
        eligible = [row for row in rows if row.get(f"{column} eligible")]
        if not eligible:
            continue
        scores = [float(row.get(column) or 0) for row in eligible]
        avg = sum(scores) / len(scores)
        bands = {"elite": 0, "good": 0, "ok": 0, "poor": 0}
        for score in scores:
            bands[score_band(score)] += 1
        total = len(scores) or 1
        top = sorted(eligible, key=lambda row: float(row.get(column) or 0), reverse=True)[:3]
        names = " · ".join(player.get("Name", "") for player in top)
        active = " active" if column in view_roles and len(view_roles) == 1 else ""
        cards.append(
            html.Button(
                [
                    html.Div(
                        [
                            html.Span(meta["name"], className="rs-depth-name"),
                            html.Span(meta["code"], className="rs-depth-code"),
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
                                className=f"rs-depth-avg rs-band-{score_band(avg)}",
                            ),
                        ],
                        className="rs-depth-avg-row",
                    ),
                    html.Div(
                        [
                            html.Div(
                                className=f"rs-depth-seg {band}",
                                style={"width": f"{bands[band] / total * 100:.1f}%"},
                            )
                            for band in ("elite", "good", "ok", "poor")
                            if bands[band]
                        ],
                        className="rs-depth-bar",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(str(bands[band]), className=f"rs-tier-val {band}"),
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
    if not cards:
        return None
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Squad depth", className="rs-depth-heading-label"),
                    html.Span(
                        [
                            html.Span(className="rs-depth-dot elite"),
                            "Elite ≥14",
                            html.Span(className="rs-depth-dot good"),
                            "Good ≥11",
                            html.Span(className="rs-depth-dot ok"),
                            "OK ≥8",
                            html.Span(className="rs-depth-dot poor"),
                            "Poor <8",
                        ],
                        className="rs-depth-legend",
                    ),
                ],
                className="rs-depth-heading",
            ),
            html.Div(cards, className="rs-depth-grid"),
        ],
        className="rs-depth-panel",
    )


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
    Output("rs-roles", "options"),
    Input("rs-phase", "data"),
    Input("rs-roles", "value"),
)
def filter_role_options(phase, selected):
    return role_options(phase=phase, keep=_as_list(selected)) or []


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
    Input("rs-reset-roles", "n_clicks"),
    Input("rs-clear-roles", "n_clicks"),
    prevent_initial_call=True,
)
def reset_or_clear(_reset, _clear):
    if not ctx.triggered_id:
        return no_update
    if ctx.triggered_id == "rs-clear-roles":
        return []
    return DEFAULT_ROLES


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
        options.append({"label": f"{meta['name']} ({label})", "value": label})
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
)
def render_shortlist(
    payload, view_role, query, max_age, min_score, eligible, pos_filter, foot_filter, page_size
):
    empty_cols = [{"name": "Name", "id": "Name"}]
    empty_style = _score_styles([])
    view_roles = _as_list(view_role)
    page_size = int(page_size or 50)
    if not payload or not payload.get("rows") or not view_roles:
        return (
            None,
            None,
            [],
            empty_cols,
            empty_style,
            page_size,
            BLANK_FIG,
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
    fig.update_layout(
        height=240,
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis_title="Score band",
        yaxis_title="Player count",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        barmode="group",
        legend_title_text="View role",
        showlegend=len(view_roles) > 1,
    )

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
    return (
        _pos_bar(rows, pos_filter, foot_filter),
        _depth_panel(rows, role_ids, view_roles),
        table_rows,
        columns,
        _score_styles(ordered_roles),
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
