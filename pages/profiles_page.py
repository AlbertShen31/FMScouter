"""Saved player profiles from Role scores and Player stats."""
from __future__ import annotations

from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_detail import role_player_detail_card
from components.player_modal import player_modal
from components.player_table import (
    feet_cell,
    identity_header_name,
    injury_cell,
    injury_tooltip_entry,
    player_data_table,
    style_cell,
    style_cell_conditional,
    style_header,
    style_header_conditional,
    table_css,
)
from scoring.comparison import score_display
from scoring.role_scorer import score_band
import services.player_profiles as profiles
import services.ui_settings as us

register_page(__name__, path="/profiles", name="Profiles")

VIEW_MODES = (
    ("roles", "Role scores"),
    ("percentiles", "Overall percentiles"),
)

PCT_COLS = ("overall", "defending", "final_third", "possession")
PCT_HEADERS = {
    "overall": "Ovr",
    "defending": "Def",
    "final_third": "Final third",
    "possession": "Possession",
}


def _pct_markdown(percentile, color=None) -> str:
    if percentile is None:
        return "—"
    text = f"{float(percentile):.0f}%"
    if not color:
        return (
            f'<span style="font-weight:750;font-variant-numeric:tabular-nums">'
            f"{text}</span>"
        )
    return (
        f'<span style="color:{color};font-weight:750;font-variant-numeric:tabular-nums">'
        f"{text}</span>"
    )


def _score_markdown(score, settings, theme=None) -> str:
    if score is None:
        return "—"
    settings = us.normalize(settings)
    try:
        band = score_band(float(score), **settings["bands"])
    except (TypeError, ValueError):
        return str(score)
    color = us.band_text_colors(settings, theme=theme).get(band)
    return score_display(score, None, enabled=False, color=color)


def _blank(value) -> str:
    if value in (None, "", "-", "—"):
        return "—"
    return str(value)


def _role_table_columns(settings) -> list[dict]:
    settings = us.normalize(settings)
    cols = []
    for col in us.shortlist_columns_for("role_scores", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col in ("Feet", "Injury"):
            spec["presentation"] = "markdown"
        cols.append(spec)
    cols.append({"name": "Role", "id": "Role"})
    cols.append({"name": "Score", "id": "Score", "presentation": "markdown"})
    for pct in PCT_COLS:
        cols.append(
            {
                "name": PCT_HEADERS[pct],
                "id": pct,
                "presentation": "markdown",
            }
        )
    return cols


def _percentile_table_columns(settings) -> list[dict]:
    settings = us.normalize(settings)
    cols = []
    for col in us.shortlist_columns_for("player_stats", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col in ("Feet", "Injury"):
            spec["presentation"] = "markdown"
        cols.append(spec)
    cols.append({"name": "Mins", "id": "Minutes"})
    for pct in PCT_COLS:
        cols.append(
            {
                "name": PCT_HEADERS[pct],
                "id": pct,
                "presentation": "markdown",
            }
        )
    return cols


def _build_role_table_rows(settings=None, theme=None) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    identity = us.shortlist_columns_for("role_scores", settings)
    rows = []
    tips = []
    for entry in profiles.list_role_profiles():
        raw = dict(entry.get("row") or {})
        if not raw.get("Role"):
            raw["Role"] = entry.get("role_column") or ""
        item: dict = {"id": entry.get("id") or "", "_key": entry.get("id") or ""}
        for col in identity:
            if col == "Feet":
                item[col] = feet_cell(raw)
            elif col == "Injury":
                item[col] = injury_cell(raw.get("Injury"))
            else:
                item[col] = _blank(raw.get(col))
        item["Role"] = _blank(raw.get("Role"))
        item["Score"] = _score_markdown(raw.get("Score"), settings, theme=theme)
        for pct in PCT_COLS:
            item[pct] = _pct_markdown(raw.get(pct), raw.get(f"{pct}_color"))
        rows.append(item)
        tips.append(injury_tooltip_entry(raw.get("Injury")))
    return rows, tips


def _build_percentile_table_rows(settings=None) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    identity = us.shortlist_columns_for("player_stats", settings)
    rows = []
    tips = []
    for entry in profiles.list_percentile_profiles():
        raw = dict(entry.get("row") or {})
        item: dict = {"id": entry.get("id") or "", "_key": entry.get("id") or ""}
        for col in identity:
            if col == "Feet":
                item[col] = feet_cell(raw)
            elif col == "Injury":
                item[col] = injury_cell(raw.get("Injury"))
            else:
                item[col] = _blank(raw.get(col))
        mins = raw.get("Minutes")
        if mins in (None, ""):
            item["Minutes"] = "—"
        else:
            try:
                item["Minutes"] = f"{int(float(mins)):,}"
            except (TypeError, ValueError):
                item["Minutes"] = _blank(mins)
        for pct in PCT_COLS:
            item[pct] = _pct_markdown(raw.get(pct), raw.get(f"{pct}_color"))
        rows.append(item)
        tips.append(injury_tooltip_entry(raw.get("Injury")))
    return rows, tips


def layout(**_kwargs):
    profiles.ensure_dirs()
    settings = us.load()
    return dbc.Container(
        [
            dcc.Store(id="pf-rev", data=0),
            dcc.Store(id="pf-view-mode", data="roles"),
            dcc.Store(id="pf-player-key", data=None),
            player_modal(prefix="pf"),
            html.H1("Profiles", className="mt-2 mb-3"),
            html.P(
                "Saved shortlist rows from Role scores (one row per evaluated role, "
                "with overall percentiles when the source file has stats) and from "
                "Player stats. Click a name for the Role scores player modal.",
                className="text-muted mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader(
                        html.Div(
                            [
                                html.Span("Saved players", className="me-3"),
                                dmc.SegmentedControl(
                                    id="pf-view-toggle",
                                    value="roles",
                                    data=[
                                        {"label": label, "value": value}
                                        for value, label in VIEW_MODES
                                    ],
                                    size="sm",
                                ),
                            ],
                            className="pf-view-header",
                        )
                    ),
                    dbc.CardBody(
                        [
                            html.Div(
                                id="pf-table-empty",
                                className="rs-table-empty",
                                hidden=True,
                            ),
                            player_data_table(
                                prefix="pf",
                                columns=_role_table_columns(settings),
                                page_size=us.page_size(settings),
                                style_cell_props=style_cell(text_align="right"),
                                style_cell_conditional_rules=style_cell_conditional(
                                    extra=[
                                        {
                                            "if": {"column_id": "Role"},
                                            "textAlign": "left",
                                            "fontWeight": "600",
                                        },
                                        {
                                            "if": {"column_id": "Score"},
                                            "textAlign": "center",
                                        },
                                    ]
                                    + [
                                        {
                                            "if": {"column_id": col},
                                            "textAlign": "center",
                                        }
                                        for col in PCT_COLS
                                    ]
                                ),
                                style_header_props=style_header(),
                                style_header_conditional_rules=style_header_conditional(
                                    extra=[
                                        {
                                            "if": {"column_id": "Score"},
                                            "textAlign": "center",
                                        },
                                    ]
                                    + [
                                        {
                                            "if": {"column_id": col},
                                            "textAlign": "center",
                                        }
                                        for col in PCT_COLS
                                    ]
                                ),
                                style_data_conditional_rules=[
                                    {
                                        "if": {
                                            "filter_query": '{Injury} contains "rs-injury-cell"'
                                        },
                                        "backgroundColor": "#fff3cd",
                                    }
                                ],
                                css=table_css(center_non_identity=True),
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        id="pf-table-caption",
                                        className="text-muted",
                                    ),
                                    dmc.Button(
                                        "Delete selected",
                                        id="pf-delete-selected",
                                        size="sm",
                                        variant="light",
                                        color="red",
                                        n_clicks=0,
                                        disabled=True,
                                    ),
                                ],
                                className="pf-table-toolbar mt-2",
                            ),
                        ]
                    ),
                ],
                className="mb-4 rs-section-card",
            ),
        ],
        fluid=True,
        className="rs-page pf-page",
    )


@callback(
    Output("pf-view-mode", "data"),
    Input("pf-view-toggle", "value"),
)
def set_view_mode(mode):
    return mode or "roles"


@callback(
    Output("pf-table", "columns"),
    Output("pf-table", "data"),
    Output("pf-table", "tooltip_data"),
    Output("pf-table", "selected_rows"),
    Output("pf-table", "selected_row_ids"),
    Output("pf-table-caption", "children"),
    Output("pf-table-empty", "children"),
    Output("pf-table-empty", "hidden"),
    Output("pf-delete-selected", "disabled"),
    Input("pf-view-mode", "data"),
    Input("pf-rev", "data"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
)
def refresh_profiles_table(view_mode, _rev, settings, theme):
    settings = us.normalize(settings)
    mode = view_mode or "roles"
    if mode == "percentiles":
        columns = _percentile_table_columns(settings)
        rows, tips = _build_percentile_table_rows(settings)
        empty_msg = (
            "No percentile profiles yet. Mark players on Player stats and save."
        )
    else:
        columns = _role_table_columns(settings)
        rows, tips = _build_role_table_rows(settings, theme=theme)
        empty_msg = (
            "No role profiles yet. Mark players on Role scores and save — "
            "one row per evaluated role, including overall percentiles when available."
        )
    n = len(rows)
    caption = f"{n:,} profile row{'s' if n != 1 else ''}"
    if not rows:
        return (
            columns,
            [],
            [],
            [],
            [],
            caption,
            html.Div(empty_msg, className="text-muted small"),
            False,
            True,
        )
    return columns, rows, tips, [], [], caption, None, True, True


@callback(
    Output("pf-delete-selected", "disabled", allow_duplicate=True),
    Input("pf-table", "selected_row_ids"),
    prevent_initial_call=True,
)
def toggle_delete_btn(selected_ids):
    return not bool(selected_ids)


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Input("pf-delete-selected", "n_clicks"),
    State("pf-table", "selected_row_ids"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def delete_selected(n_clicks, selected_ids, rev):
    if not n_clicks or not selected_ids:
        return no_update
    for profile_id in selected_ids:
        if profile_id:
            profiles.delete_profile(str(profile_id))
    return int(rev or 0) + 1


@callback(
    Output("pf-player-modal", "is_open"),
    Output("pf-player-modal-title", "children"),
    Output("pf-player-modal-body", "children"),
    Output("pf-player-key", "data"),
    Input("pf-table", "active_cell"),
    Input("pf-player-modal", "is_open"),
    Input("pf-player-modal-close", "n_clicks"),
    State("pf-table", "derived_viewport_data"),
    State("pf-player-modal", "is_open"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def open_profile_modal(
    active_cell,
    _modal_toggle,
    _close_clicks,
    viewport,
    is_open,
    settings,
):
    triggered = ctx.triggered_id
    if triggered == "pf-player-modal":
        if not is_open:
            return False, no_update, no_update, None
        return no_update, no_update, no_update, no_update
    if triggered == "pf-player-modal-close":
        return False, no_update, no_update, None
    if not active_cell or active_cell.get("column_id") != "Name":
        return no_update, no_update, no_update, no_update
    row_idx = active_cell.get("row")
    if not isinstance(viewport, list) or row_idx is None:
        return no_update, no_update, no_update, no_update
    try:
        row_idx = int(row_idx)
    except (TypeError, ValueError):
        return no_update, no_update, no_update, no_update
    if row_idx < 0 or row_idx >= len(viewport):
        return no_update, no_update, no_update, no_update
    row = viewport[row_idx] or {}
    profile_id = str(row.get("id") or row.get("_key") or "").strip()
    profile = profiles.get_profile(profile_id) if profile_id else None
    if not profile:
        return (
            True,
            str(row.get("Name") or "Player"),
            html.Div("Profile not found.", className="rs-player-missing"),
            None,
        )
    player = profile.get("player")
    name = (player or {}).get("name") or profiles.profile_identity(profile)[0] or "Player"
    role = profile.get("role_column") or (profile.get("row") or {}).get("Role") or ""
    title = f"{name} · {role}" if role else name
    if not isinstance(player, dict) or not player:
        return (
            True,
            title,
            html.Div(
                "Full player details were not stored with this profile. "
                "Re-save from Role scores to open the scout modal.",
                className="rs-player-missing",
            ),
            profile_id,
        )
    return (
        True,
        title,
        role_player_detail_card(player, settings),
        profile_id,
    )
