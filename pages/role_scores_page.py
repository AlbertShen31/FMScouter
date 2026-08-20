"""Role scores page: upload an FM attribute CSV, pick roles, filter, export."""
from __future__ import annotations

import base64
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
import plotly.graph_objects as go

from role_scorer import (
    COMBO_IP_WEIGHT,
    COMBO_OOP_WEIGHT,
    GROUP_DEFS,
    POS_CARDS,
    SET_PIECE_PROFILES,
    apply_combos,
    combo_column,
    combo_meta,
    combo_score_labels,
    foot_match,
    group_abbr_tone,
    normalize_combos,
    parse_combo_id,
    parse_export,
    planned_squad_csv,
    planned_squad_export_rows,
    planned_squad_fieldnames,
    player_row_key,
    role_meta,
    role_options,
    score_band,
    score_players,
    scored_csv,
    to_int,
    set_piece_columns,
    set_piece_filter_columns,
    set_piece_formula,
    set_piece_hint,
    expand_view_role_columns,
)
from canvas_export import build_canvas
import role_config as rc
import ui_settings as us

register_page(__name__, path="/", name="Role scores")


def _band_legend(settings=None) -> html.Div:
    settings = us.normalize(settings)
    bands = settings["bands"]
    chips = []
    for band, label, text in (
        ("elite", "Elite", f"≥ {us.format_cut(bands['elite'])}"),
        ("good", "Good", f"≥ {us.format_cut(bands['good'])}"),
        ("ok", "OK", f"≥ {us.format_cut(bands['ok'])}"),
        ("poor", "Poor", f"< {us.format_cut(bands['ok'])}"),
    ):
        chips.append(
            html.Span(
                [
                    html.Span(label, className="rs-legend-name"),
                    html.Span(text, className="rs-legend-op"),
                ],
                className=f"rs-legend-chip {band}",
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
        legend_title_text="Displayed role",
        showlegend=showlegend,
    )


def _blank_fig(theme):
    fig = go.Figure()
    fig.update_layout(**_chart_layout(theme, height=220))
    return fig


def _hist_figure(rows: list[dict], view_roles: list[str], bins: list, theme) -> go.Figure:
    fig = go.Figure()
    for role in view_roles:
        values = [float(row.get(role) or 0) for row in rows]
        counts = []
        for _label, lo, hi in bins:
            if hi == 99:
                counts.append(sum(1 for v in values if v >= lo))
            else:
                counts.append(sum(1 for v in values if lo <= v < hi))
        fig.add_bar(x=[b[0] for b in bins], y=counts, name=role)
    fig.update_layout(**_chart_layout(theme, showlegend=len(view_roles) > 1))
    return fig


BLANK_FIG = _blank_fig("dark")

HYBRID_HELP = (
    f"Hybrid score = ({COMBO_IP_WEIGHT:g}× in possession + {COMBO_OOP_WEIGHT:g}× out of possession) "
    f"÷ {COMBO_IP_WEIGHT + COMBO_OOP_WEIGHT:g}. Both part scores stay in the table. "
    "A player is eligible if they can play either part."
)


def _help_icon(tip: str, help_id: str) -> list:
    return [
        html.Span(
            "ⓘ",
            id=help_id,
            className="rs-help",
            role="img",
            **{"aria-label": "Help"},
        ),
        dbc.Tooltip(
            tip,
            target=help_id,
            placement="top",
            class_name="rs-help-tooltip",
        ),
    ]


def _field_label(
    text: str,
    *,
    primary: bool = False,
    tip: str | None = None,
    help_id: str | None = None,
) -> html.Div:
    label = html.Span(text, className="rs-field-label" + (" primary" if primary else ""))
    parts: list = [label]
    if tip:
        parts.extend(_help_icon(tip, help_id or f"rs-help-{text.lower().replace(' ', '-')}"))
    return html.Div(parts, className="rs-field-label-row")


def _upload_status_bar(count: int, filename: str) -> list:
    return [
        html.Span("✓", className="rs-upload-ok"),
        html.Span(f"{count:,} players loaded", className="rs-upload-count"),
        html.Span("·", className="rs-upload-sep"),
        html.Span(filename, className="rs-upload-name", title=filename),
        html.Span("·", className="rs-upload-sep"),
    ]


def _upload_error(message: str) -> html.Div:
    return html.Div(message, className="rs-upload-error")


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
    for value, label in (
        ("all", "All"),
        ("IP", "In possession (IP)"),
        ("OOP", "Out of possession (OOP)"),
    ):
        buttons.append(
            html.Button(
                label,
                id={"type": "rs-phase", "phase": value},
                n_clicks=0,
                className="rs-chip" + (" active" if value == active else ""),
            )
        )
    return buttons


def _set_piece_check_label(profile: dict) -> str:
    if profile["id"] == "dfk":
        return "DFK (shot)"
    if profile["id"] == "ifk":
        return "IFK (cross)"
    return profile["label"]


def _colored_group_abbr(abbr: str, *, css: str = "rs-pill-groups"):
    if not abbr:
        return []
    parts = []
    for index, token in enumerate(abbr.split("/")):
        if index:
            parts.append(html.Span("/", className=f"{css}-sep"))
        tone = group_abbr_tone(token)
        class_name = f"{css} {tone}".strip() if tone else css
        parts.append(html.Span(token, className=class_name))
    return html.Span(parts, className="rs-group-abbr")


def _set_piece_panel(settings=None) -> html.Details:
    lines = []
    for profile in SET_PIECE_PROFILES:
        lines.append(
            html.Div(
                [
                    html.Span(profile["label"], className="rs-set-piece-name"),
                    html.Span(profile.get("detail") or "", className="rs-set-piece-detail"),
                    html.Span(set_piece_formula(profile), className="rs-set-piece-formula"),
                ],
                className="rs-set-piece-line",
            )
        )
    return html.Details(
        [
            html.Summary(
                [
                    html.Span("Additional player metrics", className="rs-metrics-summary-text"),
                    *_help_icon(
                        "Check a type to add columns to the table. "
                        "Min score filters out anyone below that on every checked type.",
                        "rs-help-metrics",
                    ),
                ],
                className="rs-metrics-summary-row",
            ),
            html.Div(
                [
                    html.Div("Add columns", className="rs-chip-label"),
                    dbc.Checklist(
                        id="rs-set-pieces",
                        options=[
                            {
                                "label": _set_piece_check_label(profile),
                                "value": profile["id"],
                            }
                            for profile in SET_PIECE_PROFILES
                        ],
                        value=[],
                        inline=True,
                        className="rs-set-piece-checks",
                    ),
                    html.Div(
                        [
                            html.Span("Set-piece filters", className="rs-chip-label"),
                            html.Label("Min score", className="rs-set-piece-min-label"),
                            dbc.Input(
                                id="rs-set-piece-min-score",
                                type="number",
                                min=0,
                                max=20,
                                step=0.1,
                                placeholder="Any",
                                className="rs-set-piece-min-dd",
                            ),
                        ],
                        className="rs-set-piece-toolbar",
                    ),
                    html.Details(
                        [
                            html.Summary(
                                "Formulas & descriptions",
                                className="rs-set-piece-formulas-toggle",
                                title=set_piece_hint(),
                            ),
                            html.Div(lines, className="rs-set-piece-formulas"),
                        ],
                        className="rs-set-piece-formulas-details",
                    ),
                ],
                className="rs-metrics-body",
            ),
        ],
        className="rs-metrics-details",
    )


FOOT_FILTER_HINTS = {
    "foot-L": (
        "Left foot stronger than right, with the right foot fairly weak or weaker "
        "(reasonable, weak, or very weak)."
    ),
    "foot-B": "Both feet at least fairly strong.",
    "foot-R": (
        "Right foot stronger than left, with the left foot fairly weak or weaker "
        "(reasonable, weak, or very weak)."
    ),
}


def _role_pills(role_ids: list[str]) -> list:
    pills = []
    for role_id in role_ids:
        meta = role_meta(role_id)
        pills.append(
            html.Button(
                [
                    _colored_group_abbr(meta["group_abbr"]),
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


def _hybrid_summary_text(combos: list[dict] | None = None) -> str:
    count = len(normalize_combos(combos))
    return f"Hybrid roles ({count})" if count else "+ Create hybrid role"


def _hybrid_panel() -> html.Details:
    return html.Details(
        [
            html.Summary(
                [
                    html.Span(
                        _hybrid_summary_text(),
                        id="rs-hybrid-summary",
                        className="rs-hybrid-summary-text",
                    ),
                    *_help_icon(HYBRID_HELP, "rs-help-hybrid"),
                ],
                className="rs-hybrid-summary-row",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("In possession (IP) role", className="rs-field-label"),
                                    dcc.Dropdown(
                                        id="rs-combo-ip",
                                        options=role_options(phase="IP"),
                                        placeholder="Choose an in possession role",
                                        clearable=True,
                                    ),
                                ],
                                className="rs-combo-field",
                            ),
                            html.Div(
                                [
                                    html.Label("Out of possession (OOP) role", className="rs-field-label"),
                                    dcc.Dropdown(
                                        id="rs-combo-oop",
                                        options=role_options(phase="OOP"),
                                        placeholder="Choose an out of possession role",
                                        clearable=True,
                                    ),
                                ],
                                className="rs-combo-field",
                            ),
                            html.Button(
                                "Add combined",
                                id="rs-combo-add",
                                n_clicks=0,
                                className="rs-chip",
                            ),
                        ],
                        className="rs-combo-row",
                    ),
                    html.Div(id="rs-combo-pills", className="rs-selected-roles rs-pill-row mt-2"),
                ],
                className="rs-hybrid-body",
            ),
        ],
        id="rs-hybrid-details",
        className="rs-hybrid-details",
    )


def _combo_pills(combos: list[dict] | None) -> list:
    pills = []
    for item in normalize_combos(combos):
        meta = combo_meta(item["ip"], item["oop"])
        pills.append(
            html.Button(
                [
                    _colored_group_abbr(meta["group_abbr"]),
                    html.Span(meta["short_label"], className="rs-pill-code"),
                    html.Span(meta["phase"], className="rs-phase-tag combo"),
                    html.Span("×", className="rs-pill-x"),
                ],
                id={"type": "rs-combo-pill", "combo": meta["id"]},
                n_clicks=0,
                title=f"{meta['name']} · {COMBO_IP_WEIGHT:g}× IP + {COMBO_OOP_WEIGHT:g}× OOP",
                className="rs-role-pill combo",
            )
        )
    return pills


def _depth_id_column(role_key: str) -> str | None:
    parsed = parse_combo_id(role_key)
    if parsed:
        return combo_column(*parsed)
    if role_key and role_key != "_":
        return role_meta(role_key)["column"]
    return None


def layout():
    settings = us.load()
    return dbc.Container(
    [
        dcc.Store(id="rs-parsed"),
        dcc.Store(id="rs-rows"),
        dcc.Store(id="rs-phase", data="all"),
        dcc.Store(id="rs-group", data="all"),
        dcc.Store(id="rs-pos-filter", data="all"),
        dcc.Store(id="rs-foot-filter", data=""),
        dcc.Store(id="rs-combos", data=[]),
        dcc.Store(id="rs-squad-marked", data=[]),
        dcc.Store(id="rs-hist-open", data=False),
        html.Div(
            [
                html.Button(id={"type": "rs-pos", "pos": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-foot", "foot": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-depth", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-pill", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-group", "group": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-combo-pill", "combo": "_"}, n_clicks=0),
            ],
            hidden=True,
        ),
        dcc.Download(id="rs-download-csv"),
        dcc.Download(id="rs-download-canvas"),
        dcc.Download(id="rs-download-squad"),
        html.H1("FM26 role scores", className="mt-2 mb-3"),
        dbc.Card(
            [
                dbc.CardHeader("1. Upload export"),
                dbc.CardBody(
                    [
                        html.Div(
                            dcc.Upload(
                                id="rs-upload",
                                children=html.Div(
                                    ["Drag a CSV here, or ", html.A("browse")]
                                ),
                                className="rs-upload",
                                multiple=False,
                            ),
                            id="rs-upload-wrap",
                        ),
                        html.Div(
                            [
                                html.Div(id="rs-upload-status", className="rs-upload-status"),
                                html.Div(
                                    dcc.Upload(
                                        id="rs-upload-replace",
                                        children=html.Span(
                                            "Replace", className="rs-upload-replace"
                                        ),
                                        className="rs-upload-replace-wrap",
                                        multiple=False,
                                    ),
                                    id="rs-upload-replace-wrap",
                                    hidden=True,
                                ),
                            ],
                            className="rs-upload-status-row",
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
                dbc.CardHeader(
                    [
                        html.Div(
                            [
                                html.Span("2. Scored roles"),
                                html.Span("Next", className="rs-next-badge"),
                            ],
                            className="rs-card-header-title",
                        ),
                        html.Div(
                            [
                                html.Span("Scoring weights", className="rs-weights-label"),
                                html.Div(
                                    dcc.Dropdown(
                                        id="rs-config",
                                        options=rc.pack_options(),
                                        value=rc.active_pack_id(),
                                        clearable=False,
                                        placeholder="Select a weight config",
                                    ),
                                    className="rs-config-dd",
                                    title=(
                                        "Scores use this file’s key / preferred / useful weights. "
                                        "Edit and Save a config on the Role configs page."
                                    ),
                                ),
                                dcc.Link(
                                    "Edit",
                                    href="/role-config",
                                    className="rs-weights-edit",
                                    title="Open the Role configs page to edit and save weights.",
                                ),
                                dcc.Interval(id="rs-config-tick", interval=2500),
                            ],
                            className="rs-weights-bar",
                        ),
                    ],
                    className="rs-card-header-row",
                ),
                dbc.CardBody(
                    [
                        html.Div(
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
                                            ],
                                            className="rs-filter-cluster",
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
                                            className="rs-filter-cluster",
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
                            ],
                            className="rs-filter-toolbar",
                        ),
                        _field_label(
                            "Scored roles",
                            primary=True,
                            tip="Every player is scored against the roles you pick here.",
                            help_id="rs-help-scored-roles",
                        ),
                        html.Div(
                            dcc.Dropdown(
                                id="rs-roles",
                                options=role_options(),
                                value=[],
                                multi=True,
                                placeholder="Choose scored roles",
                            ),
                            className="rs-primary-control",
                        ),
                        html.Div(id="rs-role-pills", className="rs-selected-roles rs-pill-row"),
                        _hybrid_panel(),
                    ]
                ),
            ],
            id="rs-roles-card",
            className="mb-3 rs-section-card",
        ),
            ],
            id="rs-setup-wrap",
            hidden=True,
        ),
        html.Div(
            [
                html.Div(
                    "Choose at least one scored role",
                    className="rs-gate-title",
                ),
            ],
            id="rs-need-roles",
            className="rs-gate",
            hidden=True,
        ),
        html.Div(
            [
        html.Div(id="rs-pos-bar"),
        html.Div(
            [
                html.Div(
                    [
                        html.Span("Squad depth", className="rs-depth-heading-label"),
                        html.Div(_band_legend(settings), id="rs-band-legend"),
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
                dbc.CardHeader("3. Shortlist"),
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        _field_label(
                                            "Role scores to show",
                                            tip=(
                                                "Score columns in the table. Min score and "
                                                "eligibility filters use this selection."
                                            ),
                                            help_id="rs-help-view-roles",
                                        ),
                                        dcc.Dropdown(
                                            id="rs-view-role",
                                            multi=True,
                                            placeholder="Select roles for table columns",
                                        ),
                                    ],
                                    className="rs-filter-roles",
                                ),
                                html.Div(
                                    [
                                        html.Label("Search", className="rs-field-label"),
                                        dbc.Input(
                                            id="rs-search",
                                            type="search",
                                            placeholder="Name, club, position",
                                        ),
                                    ],
                                    className="rs-filter-search",
                                ),
                                html.Div(
                                    [
                                        html.Label("Max age", className="rs-field-label"),
                                        dcc.Dropdown(
                                            id="rs-age",
                                            options=us.age_options(settings),
                                            value=99,
                                            clearable=False,
                                        ),
                                    ],
                                    className="rs-filter-age",
                                ),
                                html.Div(
                                    [
                                        _field_label(
                                            "Min score",
                                            tip="Uses the roles selected above. Leave blank for any.",
                                            help_id="rs-help-min-score",
                                        ),
                                        dbc.Input(
                                            id="rs-min-score",
                                            type="number",
                                            min=0,
                                            max=20,
                                            step=0.1,
                                            placeholder="Any",
                                        ),
                                        dcc.Dropdown(
                                            id="rs-min-score-mode",
                                            options=[
                                                {
                                                    "label": "Every selected role",
                                                    "value": "all",
                                                },
                                                {
                                                    "label": "At least one selected role",
                                                    "value": "any",
                                                },
                                            ],
                                            value="all",
                                            clearable=False,
                                            className="rs-min-score-mode mt-1",
                                        ),
                                    ],
                                    className="rs-filter-score",
                                ),
                                html.Div(
                                    [
                                        dbc.Checklist(
                                            id="rs-eligible",
                                            options=[
                                                {
                                                    "label": (
                                                        "Only show players eligible for the "
                                                        "selected role(s)"
                                                    ),
                                                    "value": "yes",
                                                }
                                            ],
                                            value=["yes"],
                                            switch=True,
                                        ),
                                    ],
                                    className="rs-filter-elig",
                                ),
                                html.Div(
                                    [
                                        html.Label("Rows per page", className="rs-field-label"),
                                        dcc.Dropdown(
                                            id="rs-page-size",
                                            options=[
                                                {"label": "25", "value": 25},
                                                {"label": "50", "value": 50},
                                                {"label": "100", "value": 100},
                                            ],
                                            value=25,
                                            clearable=False,
                                        ),
                                    ],
                                    className="rs-filter-rows",
                                ),
                            ],
                            className="rs-shortlist-filters mb-2",
                        ),
                        html.Div(_set_piece_panel(settings), className="rs-special-scores"),
                        html.Div(
                            dash_table.DataTable(
                            id="rs-table",
                            page_size=50,
                            sort_action="custom",
                            sort_mode="single",
                            sort_by=[],
                            sort_as_null=["-", ""],
                            row_selectable="multi",
                            selected_rows=[],
                            filter_action="none",
                            fixed_columns={"headers": True, "data": 1},
                            style_table={
                                "overflowX": "auto",
                                "borderRadius": "12px",
                                "minWidth": "100%",
                            },
                            css=[
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
                                }
                            ],
                            style_cell={
                                "fontFamily": "Inter, Segoe UI, sans-serif",
                                "fontSize": "13px",
                                "padding": "10px 12px",
                                "whiteSpace": "nowrap",
                                "backgroundColor": "transparent",
                                "color": "inherit",
                                "border": "1px solid transparent",
                                "textAlign": "right",
                            },
                            style_cell_conditional=[
                                {
                                    "if": {"column_id": "Name"},
                                    "textAlign": "left",
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
                                    "if": {"column_id": "Injury"},
                                    "textAlign": "left",
                                },
                            ],
                            style_header={
                                "fontWeight": "600",
                                "textTransform": "uppercase",
                                "fontSize": "11px",
                                "letterSpacing": "0.04em",
                                "backgroundColor": "transparent",
                                "color": "inherit",
                                "cursor": "pointer",
                                "padding": "12px 28px 12px 10px",
                                "height": "46px",
                                "borderBottom": "2px solid var(--app-line)",
                            },
                            style_data_conditional=[
                                {
                                    "if": {"filter_query": '{Injury} != "-"'},
                                    "backgroundColor": "#fff3cd",
                                }
                            ],
                        ),
                            className="rs-table-shell",
                        ),
                        html.Div(
                            [
                                html.Div(id="rs-table-caption", className="text-muted"),
                                dbc.Button(
                                    "Clear marked rows",
                                    id="rs-squad-clear-btn",
                                    size="sm",
                                    color="secondary",
                                    outline=True,
                                    disabled=True,
                                    className="rs-squad-clear-btn",
                                ),
                            ],
                            className="rs-table-caption-row mt-2",
                        ),
                        html.Div(
                            [
                                html.Button(
                                    "Show score distribution",
                                    id="rs-hist-toggle",
                                    n_clicks=0,
                                    className="rs-hist-toggle",
                                    title=(
                                        "Score band on the horizontal axis; player count on "
                                        "the vertical axis. One series per displayed role."
                                    ),
                                ),
                                html.Div(
                                    [
                                        dcc.Graph(
                                            id="rs-hist",
                                            figure=BLANK_FIG,
                                            config={"displayModeBar": False},
                                            responsive=True,
                                            style={"width": "100%", "height": "240px"},
                                        ),
                                    ],
                                    id="rs-hist-wrap",
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
                            className="me-2",
                            title=(
                                "Opens beside chat in Cursor. Save to your workspace canvases "
                                "folder, or open the file directly."
                            ),
                        ),
                        html.Hr(className="my-3"),
                        html.Div(
                            [
                                html.Span("Planned squad", className="rs-export-subhead"),
                                *_help_icon(
                                    "Mark players in the shortlist table, then download a CSV "
                                    "with identity fields, displayed scores, and any set-piece "
                                    "columns you checked.",
                                    "rs-help-planned-squad",
                                ),
                            ],
                            className="rs-export-subhead-row",
                        ),
                        html.Div(id="rs-squad-preview", className="rs-squad-preview"),
                        dbc.Button(
                            "Download planned squad CSV",
                            id="rs-squad-btn",
                            color="success",
                            className="mt-2",
                            disabled=True,
                        ),
                    ]
                ),
            ],
            className="mb-4 rs-section-card",
        ),
            ],
            id="rs-results-wrap",
            hidden=True,
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


def _cell_number(value) -> float:
    if value in (None, "", "-"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


TABLE_TEXT_COLS = {"Name", "Age", "Height", "Position", "Club", "Rec", "Injury"}
_REC_SUFFIX = {"+": 0, "": 1, "-": 2}
_REC_PATTERN = re.compile(r"^([A-Za-z])\s*([+-])?$")


def rec_sort_key(value) -> tuple:
    """A+ before A before A- before B+, with blanks last."""
    text = str(value or "").strip()
    if not text or text in ("-", "—"):
        return (2, 99, 99, text)
    match = _REC_PATTERN.match(text)
    if not match:
        return (1, 99, 99, text.casefold())
    letter = match.group(1).upper()
    suffix = match.group(2) or ""
    return (0, ord(letter) - ord("A"), _REC_SUFFIX[suffix], text)


def _column_sort_key(column_id: str, value):
    if column_id == "Rec":
        return rec_sort_key(value)
    blank = value in (None, "", "-")
    if column_id not in TABLE_TEXT_COLS:
        return (1, float("inf")) if blank else (0, _cell_number(value))
    return (1, "\uffff") if blank else (0, str(value).casefold())


def _sort_table_rows(rows: list[dict], sort_by, view_roles: list[str], min_score_mode: str) -> None:
    if sort_by:
        item = sort_by[0]
        column = item.get("column_id")
        reverse = item.get("direction") == "desc"
        rows.sort(key=lambda row: _column_sort_key(column, row.get(column)), reverse=reverse)
        return
    rows.sort(
        key=lambda row: (
            max(float(row.get(role) or 0) for role in view_roles)
            if min_score_mode == "any"
            else min(float(row.get(role) or 0) for role in view_roles)
        ),
        reverse=True,
    )


def _table_columns(col_ids: list[str]) -> list[dict]:
    columns = []
    for col in col_ids:
        spec = {"name": col, "id": col}
        if col not in TABLE_TEXT_COLS:
            spec["type"] = "numeric"
        columns.append(spec)
    return columns


def _clicked(n_clicks) -> bool:
    return bool(n_clicks) and any(n_clicks)


MIN_SCORE_MODES = {
    "all": "every selected role",
    "any": "at least one selected role",
}


def _passes_min_score(row: dict, roles: list[str], min_score: float, mode: str) -> bool:
    if min_score <= 0 or not roles:
        return True
    scores = [float(row.get(role) or 0) for role in roles]
    if mode == "any":
        return any(score >= min_score for score in scores)
    return all(score >= min_score for score in scores)


def _table_base_styles(theme: str | None = None) -> list[dict]:
    dark = _is_dark(theme)
    zebra = "rgba(255,255,255,0.03)" if dark else "rgba(0,0,0,0.025)"
    selected_bg = "rgba(61, 255, 136, 0.14)" if dark else "rgba(34, 139, 87, 0.12)"
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
        },
        {
            "if": {"column_id": "Club"},
            "color": "var(--app-muted)",
            "maxWidth": "200px",
        },
        {
            "if": {"column_id": "Rec"},
            "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            "fontSize": "12px",
            "letterSpacing": "0.03em",
        },
        {
            "if": {"column_id": "Injury", "filter_query": '{Injury} != "-"'},
            "color": "#b45309" if not dark else "#fbbf24",
            "fontWeight": "600",
        },
    ]


def _score_styles(role_labels: list[str], settings=None, theme: str | None = None) -> list[dict]:
    settings = us.normalize(settings)
    bands = settings["bands"]
    colors = us.score_colors(settings)
    elite, good, ok = bands["elite"], bands["good"], bands["ok"]
    injury = "rgba(251, 191, 36, 0.18)" if _is_dark(theme) else "#fff3cd"
    rules = _table_base_styles(theme)
    rules.append(
        {
            "if": {"filter_query": '{Injury} != "-"'},
            "backgroundColor": injury,
        }
    )
    for label in role_labels:
        rules.extend(
            [
                {
                    "if": {"filter_query": f"{{{label}}} >= {elite}", "column_id": label},
                    "backgroundColor": colors["elite"][0],
                    "color": colors["elite"][1],
                    "fontWeight": "700",
                    "borderRadius": "6px",
                    "fontVariantNumeric": "tabular-nums",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= {good} && {{{label}}} < {elite}",
                        "column_id": label,
                    },
                    "backgroundColor": colors["good"][0],
                    "color": colors["good"][1],
                    "fontWeight": "700",
                    "fontVariantNumeric": "tabular-nums",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= {ok} && {{{label}}} < {good}",
                        "column_id": label,
                    },
                    "backgroundColor": colors["ok"][0],
                    "color": colors["ok"][1],
                    "fontWeight": "700",
                    "fontVariantNumeric": "tabular-nums",
                },
                {
                    "if": {"filter_query": f"{{{label}}} < {ok}", "column_id": label},
                    "backgroundColor": colors["poor"][0],
                    "color": colors["poor"][1],
                    "fontWeight": "700",
                    "fontVariantNumeric": "tabular-nums",
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
                title=FOOT_FILTER_HINTS.get(key, ""),
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


def _depth_card(meta: dict, rows: list[dict], view_roles: list[str], bands: dict) -> html.Button | None:
    column = meta["column"]
    eligible = [row for row in rows if row.get(f"{column} eligible")]
    if not eligible:
        return None
    scores = [float(row.get(column) or 0) for row in eligible]
    avg = sum(scores) / len(scores)
    counts = {"elite": 0, "good": 0, "ok": 0, "poor": 0}
    for score in scores:
        counts[score_band(score, **bands)] += 1
    total = len(scores) or 1
    top = sorted(eligible, key=lambda row: float(row.get(column) or 0), reverse=True)[:3]
    names = " · ".join(player.get("Name", "") for player in top)
    active = " active" if column in view_roles and len(view_roles) == 1 else ""
    label = meta.get("short_label") or meta["name"]
    return html.Button(
        [
            html.Div(
                [
                    html.Div(
                        [
                            _colored_group_abbr(meta["group_abbr"], css="rs-depth-code"),
                            html.Span(
                                meta["phase"],
                                className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                            ),
                        ],
                        className="rs-depth-meta",
                    ),
                    html.Span(label, className="rs-depth-name"),
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
        id={"type": "rs-depth", "role": meta["id"]},
        n_clicks=0,
        className="rs-depth-card" + active,
        title=meta.get("compact") or meta["name"],
    )


def _depth_panel(
    rows: list[dict],
    role_ids: list[str],
    focus_roles: list[str],
    bands: dict | None = None,
    combos: list[dict] | None = None,
) -> list:
    """Cards for every role scored in section 3; focus_roles only drives active highlight."""
    if not rows or not (role_ids or combos):
        return []
    bands = us.normalize(bands)["bands"]
    cards = []
    for item in normalize_combos(combos):
        card = _depth_card(combo_meta(item["ip"], item["oop"]), rows, focus_roles, bands)
        if card:
            cards.append(card)
    for role_id in role_ids:
        card = _depth_card(role_meta(role_id), rows, focus_roles, bands)
        if card:
            cards.append(card)
    return cards


@callback(
    Output("rs-parsed", "data"),
    Output("rs-upload-status", "children"),
    Output("rs-upload-wrap", "hidden"),
    Output("rs-upload-replace-wrap", "hidden"),
    Input("rs-upload", "contents"),
    Input("rs-upload-replace", "contents"),
    State("rs-upload", "filename"),
    State("rs-upload-replace", "filename"),
    prevent_initial_call=True,
)
def parse_uploaded(upload_contents, replace_contents, upload_name, replace_name):
    contents = upload_contents or replace_contents
    if not contents:
        return no_update, no_update, no_update, no_update
    name = (replace_name if replace_contents else upload_name) or "upload.csv"
    if not name.lower().endswith(".csv"):
        return (
            None,
            _upload_error("Upload the CSV from FM Player Export, not the HTML file."),
            False,
            True,
        )
    try:
        players = parse_export(_decode_upload(contents))
    except ValueError as exc:
        return None, _upload_error(str(exc)), False, True
    return (
        {"filename": name, "players": players},
        _upload_status_bar(len(players), name),
        True,
        False,
    )


def _workflow_visibility(parsed, payload):
    has_csv = bool(parsed and parsed.get("players"))
    has_scores = isinstance(payload, dict) and "rows" in payload
    setup_hidden = not has_csv
    results_hidden = not has_scores
    placeholder_hidden = not (has_csv and not has_scores)
    roles_class = "mb-3 rs-next-step" if has_csv and not has_scores else "mb-3"
    return setup_hidden, results_hidden, placeholder_hidden, roles_class


@callback(
    Output("rs-setup-wrap", "hidden"),
    Output("rs-results-wrap", "hidden"),
    Output("rs-need-roles", "hidden"),
    Output("rs-roles-card", "className"),
    Input("rs-parsed", "data"),
    Input("rs-rows", "data"),
)
def reveal_workflow(parsed, payload):
    return _workflow_visibility(parsed, payload)


@callback(
    Output("rs-hist-open", "data"),
    Output("rs-hist-wrap", "hidden"),
    Output("rs-hist-toggle", "children"),
    Input("rs-hist-toggle", "n_clicks"),
    State("rs-hist-open", "data"),
    prevent_initial_call=True,
)
def toggle_score_distribution(_clicks, opened):
    opened = not bool(opened)
    return (
        opened,
        not opened,
        "Hide score distribution" if opened else "Show score distribution",
    )


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
    Output("rs-hybrid-summary", "children"),
    Input("rs-combos", "data"),
)
def render_hybrid_summary(combos):
    return _hybrid_summary_text(combos)


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
    Input("rs-combos", "data"),
)
def filter_role_options(phase, group, selected, combos):
    keep = _as_list(selected)
    for item in normalize_combos(combos):
        keep.extend((item["ip"], item["oop"]))
    return role_options(phase=phase, group=group, keep=keep) or []


@callback(
    Output("rs-combo-ip", "options"),
    Output("rs-combo-oop", "options"),
    Input("rs-group", "data"),
    Input("rs-combo-ip", "value"),
    Input("rs-combo-oop", "value"),
)
def filter_combo_role_options(group, ip, oop):
    group = group or "all"
    return (
        role_options(phase="IP", group=group, keep=_as_list(ip)) or [],
        role_options(phase="OOP", group=group, keep=_as_list(oop)) or [],
    )


@callback(
    Output("rs-role-pills", "children"),
    Input("rs-roles", "value"),
)
def render_pills(role_ids):
    return _role_pills(_as_list(role_ids))


@callback(
    Output("rs-combo-pills", "children"),
    Input("rs-combos", "data"),
)
def render_combo_pills(combos):
    return _combo_pills(combos)


@callback(
    Output("rs-combos", "data"),
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-roles", "options", allow_duplicate=True),
    Output("rs-combo-ip", "value"),
    Output("rs-combo-oop", "value"),
    Input("rs-combo-add", "n_clicks"),
    State("rs-combo-ip", "value"),
    State("rs-combo-oop", "value"),
    State("rs-combos", "data"),
    State("rs-roles", "value"),
    State("rs-phase", "data"),
    State("rs-group", "data"),
    prevent_initial_call=True,
)
def add_combo(_clicks, ip, oop, combos, selected, phase, group):
    if not ip or not oop:
        return no_update, no_update, no_update, no_update, no_update
    current = normalize_combos(combos)
    incoming = normalize_combos([{"ip": ip, "oop": oop}])
    if not incoming:
        return no_update, no_update, no_update, None, None
    pair = incoming[0]
    if any(item["ip"] == pair["ip"] and item["oop"] == pair["oop"] for item in current):
        return current, no_update, no_update, None, None
    current.append(pair)
    roles = _as_list(selected)
    for role_id in (pair["ip"], pair["oop"]):
        if role_id not in roles:
            roles.append(role_id)
    keep = list(roles)
    for item in current:
        keep.extend((item["ip"], item["oop"]))
    options = role_options(phase=phase, group=group, keep=keep) or []
    return current, roles, options, None, None


@callback(
    Output("rs-combos", "data", allow_duplicate=True),
    Input({"type": "rs-combo-pill", "combo": ALL}, "n_clicks"),
    State("rs-combos", "data"),
    prevent_initial_call=True,
)
def remove_combo(n_clicks, combos):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    target = ctx.triggered_id.get("combo")
    if not target or target == "_":
        return no_update
    parsed = parse_combo_id(target)
    if not parsed:
        return no_update
    ip, oop = parsed
    return [
        item
        for item in normalize_combos(combos)
        if not (item["ip"] == ip and item["oop"] == oop)
    ]


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-combos", "data", allow_duplicate=True),
    Input({"type": "rs-pill", "role": ALL}, "n_clicks"),
    State("rs-roles", "value"),
    State("rs-combos", "data"),
    prevent_initial_call=True,
)
def remove_role(n_clicks, selected, combos):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    role_id = ctx.triggered_id["role"]
    if role_id == "_":
        return no_update, no_update
    remaining = [item for item in _as_list(selected) if item != role_id]
    kept = [
        item
        for item in normalize_combos(combos)
        if item["ip"] in remaining and item["oop"] in remaining
    ]
    return remaining, kept


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-combos", "data", allow_duplicate=True),
    Input("rs-clear-roles", "n_clicks"),
    prevent_initial_call=True,
)
def clear_roles(_clear):
    if not ctx.triggered_id:
        return no_update, no_update
    return [], []


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
    Output("rs-age", "options"),
    Output("rs-age", "value"),
    Output("rs-band-legend", "children"),
    Input("ui-settings", "data"),
    State("rs-age", "value"),
)
def apply_ui_settings(settings, age):
    settings = us.normalize(settings)
    ages = us.age_options(settings)
    return ages, us.clamp_choice(age, ages, 99), _band_legend(settings)


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
    column = _depth_id_column(role)
    if not column:
        return no_update
    return [column]


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
    Input("rs-combos", "data"),
    Input("rs-config", "value"),
    State("rs-view-role", "value"),
)
def rescore(parsed, role_ids, combos, pack_id, current_view):
    if pack_id:
        rc.load_pack(pack_id)
    if not parsed or not parsed.get("players"):
        return None, [], None
    combos = normalize_combos(combos)
    role_ids = _as_list(role_ids)
    needed = list(role_ids)
    for item in combos:
        for role_id in (item["ip"], item["oop"]):
            if role_id not in needed:
                needed.append(role_id)
    if not needed:
        return None, [], None
    rows = apply_combos(score_players(parsed["players"], needed), combos)
    labels = combo_score_labels(needed, combos)
    options = []
    seen = set()
    for item in combos:
        meta = combo_meta(item["ip"], item["oop"])
        if meta["column"] not in seen:
            options.append({"label": meta["compact"], "value": meta["column"]})
            seen.add(meta["column"])
    for role_id in needed:
        meta = role_meta(role_id)
        if meta["column"] in seen:
            continue
        options.append({"label": meta["compact"], "value": meta["column"]})
        seen.add(meta["column"])
    kept = [role for role in _as_list(current_view) if role in labels]
    view = kept or labels
    return (
        {
            "filename": parsed.get("filename", "export.csv"),
            "rows": rows,
            "roles": labels,
            "role_ids": needed,
            "combos": combos,
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
    Output("rs-table", "selected_rows"),
    Output("rs-hist", "figure"),
    Output("rs-table-caption", "children"),
    Input("rs-rows", "data"),
    Input("rs-view-role", "value"),
    Input("rs-search", "value"),
    Input("rs-age", "value"),
    Input("rs-min-score", "value"),
    Input("rs-min-score-mode", "value"),
    Input("rs-eligible", "value"),
    Input("rs-set-pieces", "value"),
    Input("rs-set-piece-min-score", "value"),
    Input("rs-squad-marked", "data"),
    Input("rs-pos-filter", "data"),
    Input("rs-foot-filter", "data"),
    Input("rs-page-size", "value"),
    Input("rs-table", "sort_by"),
    Input("theme", "data"),
    Input("rs-hist-open", "data"),
    State("ui-settings", "data"),
)
def render_shortlist(
    payload,
    view_role,
    query,
    max_age,
    min_score,
    min_score_mode,
    eligible,
    set_pieces,
    set_piece_min,
    squad_marked,
    pos_filter,
    foot_filter,
    page_size,
    sort_by,
    theme,
    hist_open,
    settings,
):
    settings = us.normalize(settings)
    bands = settings["bands"]
    bins = us.hist_bins(settings)
    empty_cols = [{"name": "Name", "id": "Name"}]
    empty_style = _score_styles([], settings, theme)
    view_roles = _as_list(view_role)
    page_size = int(page_size or 50)
    hist_open = bool(hist_open)
    pos_filter = pos_filter or "all"
    foot_filter = foot_filter or ""
    if not payload or not payload.get("rows"):
        return (
            None,
            [],
            True,
            [],
            empty_cols,
            empty_style,
            page_size,
            [],
            _blank_fig(theme) if hist_open else no_update,
            "Upload a file and pick at least one role score to show.",
        )
    rows = payload["rows"]
    role_ids = payload.get("role_ids") or []
    combos = normalize_combos(payload.get("combos"))
    if not view_roles:
        cards = _depth_panel(rows, role_ids, [], bands, combos)
        return (
            _pos_bar(rows, pos_filter, foot_filter),
            cards,
            not cards,
            [],
            empty_cols,
            empty_style,
            page_size,
            [],
            no_update if not hist_open else _blank_fig(theme),
            "Select at least one displayed role to filter the table.",
        )
    query = (query or "").strip().lower()
    max_age = 99 if max_age is None else int(max_age)
    min_score = us.parse_score_floor(min_score)
    min_score_mode = min_score_mode if min_score_mode in MIN_SCORE_MODES else "all"
    set_piece_min = us.parse_score_floor(set_piece_min)
    elig_only = "yes" in (eligible or [])
    chosen_pieces = _as_list(set_pieces)
    marked_keys = set(_as_list(squad_marked))

    filtered = []
    for row in rows:
        if pos_filter != "all" and pos_filter not in (row.get("PosGroups") or []):
            continue
        if foot_filter and not foot_match(row, foot_filter):
            continue
        if elig_only and not all(row.get(f"{role} eligible") for role in view_roles):
            continue
        if to_int(row.get("Age")) > max_age:
            continue
        if not _passes_min_score(row, view_roles, min_score, min_score_mode):
            continue
        if set_piece_min > 0 and chosen_pieces:
            piece_cols = [
                set_piece_filter_columns(piece_id)
                for piece_id in chosen_pieces
            ]
            if any(
                _cell_number(row.get(col)) < set_piece_min
                for col in piece_cols
                if col
            ):
                continue
        if query:
            blob = f"{row.get('Name','')} {row.get('Club','')} {row.get('Position','')} {row.get('Division','')}".lower()
            if query not in blob:
                continue
        filtered.append(row)

    _sort_table_rows(filtered, sort_by, view_roles, min_score_mode)

    table_role_cols = expand_view_role_columns(view_roles, combos)
    fig = _hist_figure(filtered, view_roles, bins, theme) if hist_open else no_update

    piece_cols = set_piece_columns(set_pieces)
    chosen = set(chosen_pieces)
    score_cols = [
        profile["score"]
        for profile in SET_PIECE_PROFILES
        if profile["id"] in chosen and profile.get("score")
    ] + table_role_cols
    table_cols = ["Name", "Age", "Height", "Position", "Club", "Rec", "Injury"]
    table_cols.extend(piece_cols)
    table_cols.extend(table_role_cols)
    columns = _table_columns(table_cols)
    table_rows = [{key: row.get(key, "-") for key in table_cols} for row in filtered]
    page_keys = [player_row_key(row) for row in table_rows]
    selected_rows = [i for i, key in enumerate(page_keys) if key in marked_keys]
    extras = []
    if pos_filter != "all":
        extras.append(pos_filter)
    if foot_filter:
        extras.append({"foot-L": "left foot", "foot-R": "right foot", "foot-B": "both feet"}[foot_filter])
    extra = f" Position/foot: {', '.join(extras)}." if extras else ""
    piece_note = ""
    if chosen_pieces and set_piece_min > 0:
        piece_note = f" Set-piece min {set_piece_min:g}+ on all checked types."
    mark_note = f" {len(marked_keys)} marked for planned squad." if marked_keys else ""
    min_note = ""
    if min_score > 0:
        min_note = (
            f" Min score {min_score:g}+ on {MIN_SCORE_MODES[min_score_mode]}: {role_list}."
        )
    caption = (
        f"{len(filtered)} of {len(rows)} players"
        f"{min_note}{extra}{piece_note}{mark_note}"
        f" · {payload.get('filename')}."
    )
    cards = _depth_panel(rows, role_ids, view_roles, bands, combos)
    return (
        _pos_bar(rows, pos_filter, foot_filter),
        cards,
        not cards,
        table_rows,
        columns,
        _score_styles(score_cols, settings, theme),
        page_size,
        selected_rows,
        fig,
        caption,
    )


SQUAD_PREVIEW_MAX_ROWS = 8


def _squad_preview_panel(marked, payload, view_roles, set_pieces) -> html.Div:
    view_roles = _as_list(view_roles)
    if not payload or not view_roles:
        return html.P("Pick role scores to show first.", className="text-muted mb-0")
    marked = _as_list(marked)
    if not marked:
        return html.P("No players marked yet.", className="text-muted mb-0")
    rows = payload.get("rows") or []
    combos = normalize_combos(payload.get("combos"))
    export_rows = planned_squad_export_rows(
        rows, marked, view_roles, combos, _as_list(set_pieces)
    )
    if not export_rows:
        return html.P("Marked players are not in the current data.", className="text-muted mb-0")
    fieldnames = planned_squad_fieldnames(view_roles, combos, _as_list(set_pieces))
    preview_rows = export_rows[:SQUAD_PREVIEW_MAX_ROWS]
    extra = len(export_rows) - len(preview_rows)
    parts = [f"{len(export_rows)} player(s) marked", f"{len(fieldnames)} columns"]
    if set_pieces:
        parts.append(f"set pieces: {', '.join(_as_list(set_pieces))}")
    if extra > 0:
        parts.append(f"showing first {len(preview_rows)}")
    return html.Div(
        [
            html.Div(" · ".join(parts), className="rs-squad-preview-note"),
            dash_table.DataTable(
                columns=[{"name": col, "id": col} for col in fieldnames],
                data=preview_rows,
                page_action="none",
                style_table={"overflowX": "auto"},
                style_cell={
                    "fontFamily": "Inter, Segoe UI, sans-serif",
                    "fontSize": "12px",
                    "padding": "6px",
                    "whiteSpace": "nowrap",
                    "backgroundColor": "transparent",
                    "color": "inherit",
                },
                style_header={
                    "fontWeight": "600",
                    "fontSize": "11px",
                    "textTransform": "uppercase",
                    "backgroundColor": "transparent",
                    "color": "inherit",
                },
            ),
        ]
    )


@callback(
    Output("rs-squad-clear-btn", "disabled"),
    Input("rs-squad-marked", "data"),
)
def toggle_clear_marks_btn(marked):
    return not _as_list(marked)


@callback(
    Output("rs-squad-marked", "data", allow_duplicate=True),
    Input("rs-squad-clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_squad_marks(n_clicks):
    if not n_clicks:
        return no_update
    return []


@callback(
    Output("rs-squad-marked", "data", allow_duplicate=True),
    Input("rs-table", "selected_rows"),
    State("rs-table", "data"),
    State("rs-squad-marked", "data"),
    prevent_initial_call=True,
)
def sync_squad_marks(selected_rows, table_data, marked):
    table_data = table_data or []
    marked_set = set(_as_list(marked))
    keys_on_page = [player_row_key(row) for row in table_data]
    expected = {i for i, key in enumerate(keys_on_page) if key in marked_set}
    actual = set(selected_rows or [])
    if actual == expected:
        return no_update
    marked_set -= set(keys_on_page)
    for index in selected_rows or []:
        if 0 <= index < len(keys_on_page):
            key = keys_on_page[index]
            if key:
                marked_set.add(key)
    return sorted(marked_set)


@callback(
    Output("rs-squad-marked", "data", allow_duplicate=True),
    Input("rs-parsed", "data"),
    prevent_initial_call=True,
)
def clear_squad_marks_on_upload(_parsed):
    return []


@callback(
    Output("rs-squad-preview", "children"),
    Output("rs-squad-btn", "disabled"),
    Input("rs-squad-marked", "data"),
    Input("rs-rows", "data"),
    Input("rs-view-role", "value"),
    Input("rs-set-pieces", "value"),
)
def render_squad_preview(marked, payload, view_roles, set_pieces):
    export_rows = []
    if payload and _as_list(view_roles) and _as_list(marked):
        export_rows = planned_squad_export_rows(
            payload.get("rows") or [],
            _as_list(marked),
            _as_list(view_roles),
            normalize_combos(payload.get("combos")),
            _as_list(set_pieces),
        )
    return _squad_preview_panel(marked, payload, view_roles, set_pieces), not export_rows


@callback(
    Output("rs-download-squad", "data"),
    Input("rs-squad-btn", "n_clicks"),
    State("rs-squad-marked", "data"),
    State("rs-rows", "data"),
    State("rs-view-role", "value"),
    State("rs-set-pieces", "value"),
    prevent_initial_call=True,
)
def download_squad_csv(n_clicks, marked, payload, view_roles, set_pieces):
    if not n_clicks or not payload or not payload.get("rows"):
        return no_update
    view_roles = _as_list(view_roles)
    marked = _as_list(marked)
    if not view_roles or not marked:
        return no_update
    name = (payload.get("filename") or "role_scores").rsplit(".", 1)[0]
    text = planned_squad_csv(
        payload["rows"],
        marked,
        view_roles,
        normalize_combos(payload.get("combos")),
        _as_list(set_pieces),
    )
    return dict(content=text, filename=f"{name}_planned_squad.csv")


@callback(
    Output("rs-download-csv", "data"),
    Input("rs-csv-btn", "n_clicks"),
    State("rs-rows", "data"),
    State("rs-view-role", "value"),
    prevent_initial_call=True,
)
def download_csv(n_clicks, payload, view_roles):
    if not n_clicks or not payload or not payload.get("rows"):
        return no_update
    view_roles = _as_list(view_roles)
    if not view_roles:
        return no_update
    role_labels = expand_view_role_columns(
        view_roles, normalize_combos(payload.get("combos"))
    )
    name = (payload.get("filename") or "role_scores").rsplit(".", 1)[0]
    text = scored_csv(payload["rows"], role_labels)
    return dict(content=text, filename=f"{name}_role_scores.csv")


@callback(
    Output("rs-download-canvas", "data"),
    Input("rs-canvas-btn", "n_clicks"),
    State("rs-rows", "data"),
    State("rs-view-role", "value"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def download_canvas(n_clicks, payload, view_roles, settings):
    if not n_clicks or not payload or not payload.get("rows"):
        return no_update
    view_roles = _as_list(view_roles)
    if not view_roles:
        return no_update
    role_labels = expand_view_role_columns(
        view_roles, normalize_combos(payload.get("combos"))
    )
    text = build_canvas(
        payload["rows"],
        role_labels,
        payload.get("filename") or "FM export",
        settings,
    )
    return dict(content=text, filename="fm26-role-scores.canvas.tsx")
