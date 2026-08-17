from __future__ import annotations

import base64
from dash import (
    dcc,
    html,
    callback,
    Input,
    Output,
    State,
    register_page,
    dash_table,
    no_update,
)
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from utils import format_position_name
from role_scorer import (
    DEFAULT_ROLES,
    parse_export,
    role_options,
    score_players,
    scored_csv,
)
from canvas_export import build_canvas

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

BLANK_FIG = go.Figure()
BLANK_FIG.update_layout(
    height=220,
    margin=dict(l=40, r=20, t=20, b=40),
    xaxis_title="Score band",
    yaxis_title="Player count",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)

layout = dbc.Container(
    [
        dcc.Store(id="rs-parsed"),
        dcc.Store(id="rs-rows"),
        dcc.Download(id="rs-download-csv"),
        dcc.Download(id="rs-download-canvas"),
        html.H1("Role scores", className="mt-2 mb-1"),
        html.P(
            "Upload an FM attribute CSV, pick roles, then filter the shortlist. "
            "You can download a scored sheet or a Cursor canvas from the same results.",
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
                dbc.CardHeader("2. Roles to evaluate"),
                dbc.CardBody(
                    [
                        dcc.Dropdown(
                            id="rs-roles",
                            options=role_options(),
                            value=DEFAULT_ROLES,
                            multi=True,
                            placeholder="Select roles and duties",
                        ),
                        html.Small(
                            "Default shortlist: SK(S), BPD(D), WB(S), CM(S), MEZ(S), IF(A).",
                            className="text-muted",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        html.Div(id="rs-summary"),
        dbc.Card(
            [
                dbc.CardHeader("3. Shortlist"),
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
                                    md=2,
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
                            page_size=30,
                            sort_action="native",
                            filter_action="none",
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "fontFamily": "Inter, Segoe UI, sans-serif",
                                "fontSize": "13px",
                                "padding": "8px",
                                "whiteSpace": "nowrap",
                            },
                            style_header={"fontWeight": "600", "backgroundColor": "#f8f9fa"},
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
                dbc.CardHeader("4. Export"),
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
    return [format_position_name(role_id) for role_id in role_ids]


def _as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


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
    Output("rs-rows", "data"),
    Output("rs-view-role", "options"),
    Output("rs-view-role", "value"),
    Input("rs-parsed", "data"),
    Input("rs-roles", "value"),
    State("rs-view-role", "value"),
)
def rescore(parsed, role_ids, current_view):
    if not parsed or not parsed.get("players"):
        return None, [], None
    role_ids = role_ids or []
    if not role_ids:
        return None, [], None
    rows = score_players(parsed["players"], role_ids)
    labels = _labels(role_ids)
    options = [{"label": label, "value": label} for label in labels]
    kept = [role for role in _as_list(current_view) if role in labels]
    view = kept or labels
    return {"filename": parsed.get("filename", "export.csv"), "rows": rows, "roles": labels}, options, view


@callback(
    Output("rs-summary", "children"),
    Output("rs-table", "data"),
    Output("rs-table", "columns"),
    Output("rs-hist", "figure"),
    Output("rs-table-caption", "children"),
    Input("rs-rows", "data"),
    Input("rs-view-role", "value"),
    Input("rs-search", "value"),
    Input("rs-age", "value"),
    Input("rs-min-score", "value"),
    Input("rs-eligible", "value"),
)
def render_shortlist(payload, view_role, query, max_age, min_score, eligible):
    empty_cols = [{"name": "Name", "id": "Name"}]
    view_roles = _as_list(view_role)
    if not payload or not payload.get("rows") or not view_roles:
        return (
            None,
            [],
            empty_cols,
            BLANK_FIG,
            "Upload a file and pick at least one view role.",
        )
    rows = payload["rows"]
    roles = payload["roles"]
    query = (query or "").strip().lower()
    max_age = 99 if max_age is None else int(max_age)
    min_score = 0 if min_score is None else float(min_score)
    elig_only = "yes" in (eligible or [])

    filtered = []
    for row in rows:
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

    top_cards = []
    for role in roles:
        eligible_rows = [r for r in rows if r.get(f"{role} eligible")]
        eligible_rows.sort(key=lambda r: float(r.get(role) or 0), reverse=True)
        if not eligible_rows:
            continue
        best = eligible_rows[0]
        top_cards.append(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Div(role, className="text-muted"),
                            html.H3(f"{float(best.get(role) or 0):.1f}", className="mb-0"),
                            html.Div(
                                f"{best.get('Name')} · {best.get('Age')}",
                                className="small",
                            ),
                        ]
                    )
                ),
                md=2,
            )
        )
    summary = dbc.Row(top_cards, className="g-2 mb-3") if top_cards else None

    ordered_roles = view_roles + [role for role in roles if role not in view_roles]
    table_cols = ["Name", "Age", "Position", "Club", "Rec", "Injury"] + ordered_roles
    columns = [{"name": col, "id": col} for col in table_cols]
    role_list = ", ".join(view_roles)
    caption = (
        f"{len(filtered)} of {len(rows)} players meeting min score and eligibility "
        f"on all of: {role_list}. Sorted by the lowest of those scores. "
        f"Source: {payload.get('filename')}."
    )
    return summary, filtered, columns, fig, caption


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
