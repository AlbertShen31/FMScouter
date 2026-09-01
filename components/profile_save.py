"""Save marked shortlist players to a chosen profiles library."""
from __future__ import annotations

from dash import Input, Output, State, callback, dcc, html, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon
from components.scouting_shell import as_list, parsed_players
import services.export_library as lib
import services.player_profiles as profiles
from scoring.stats_scorer import player_key as stats_player_key


def profile_save_panel(*, prefix: str, section_number: int) -> dbc.Card:
    options = profiles.library_options()
    active = profiles.active_library_id() or (options[0]["value"] if options else None)
    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Span(f"{section_number}. Profiles"),
                        *help_icon(
                            "Mark players in the shortlist, then save them to a profile library. "
                            "Requires a saved library file eligible for Player stats. One row is "
                            "created per evaluated role — each save stores that shortlist row only "
                            "(not the whole file).",
                            f"{prefix}-help-profile-save",
                        ),
                    ],
                    className="rs-card-header-title",
                )
            ),
            dbc.CardBody(
                [
                    html.Div(
                        [
                            html.Label(
                                "Save to profile",
                                className="rs-field-label",
                            ),
                            dmc.Select(
                                id=f"{prefix}-profile-library",
                                data=options,
                                value=active,
                                clearable=False,
                                searchable=True,
                                placeholder="Select a profile",
                                size="sm",
                            ),
                            dcc.Interval(
                                id=f"{prefix}-profile-library-poll",
                                interval=3000,
                                n_intervals=0,
                            ),
                        ],
                        className="pf-save-library-field mb-3",
                    ),
                    html.Div(id=f"{prefix}-profile-preview", className="pf-save-preview"),
                    dmc.Button(
                        "Save marked to profile",
                        id=f"{prefix}-profile-save-btn",
                        className="me-2",
                        disabled=True,
                    ),
                    html.Div(id=f"{prefix}-profile-status", className="mt-2"),
                ]
            ),
        ],
        className="mb-4 rs-section-card",
    )


def _source_label(parsed) -> str:
    if not isinstance(parsed, dict):
        return ""
    file_id = parsed.get("file_id")
    if file_id:
        entry = lib.get_file(file_id)
        if entry:
            return lib.display_label(entry)
    return str(parsed.get("filename") or "").strip()


def _table_row_key(row) -> str:
    if not isinstance(row, dict):
        return ""
    key = str(row.get("id") or row.get("_key") or "").strip()
    if key:
        return key
    name = str(row.get("Name") or "").strip()
    club = str(row.get("Club") or "").strip()
    return f"{name}|{club}" if name else ""


def _effective_marked_keys(marked, selected_ids=None, table_data=None) -> list[str]:
    """Use current table selection immediately, without waiting for marked-store sync."""
    marked_set = {str(key) for key in as_list(marked) if key}
    selected = {str(key) for key in (selected_ids or []) if key}
    if not selected:
        return sorted(marked_set)
    page_keys = {_table_row_key(row) for row in (table_data or []) if _table_row_key(row)}
    if page_keys:
        marked_set -= page_keys
    marked_set |= selected
    return sorted(marked_set)


def _library_label(library_id: str | None) -> str:
    meta = profiles.get_library(library_id)
    if meta:
        return str(meta.get("name") or meta.get("id") or "Profiles")
    return "Profiles"


def _profiles_stats_eligible(parsed) -> bool:
    """Profiles need percentiles/charts from a stats-eligible saved upload."""
    if not isinstance(parsed, dict):
        return False
    file_id = str(parsed.get("file_id") or "").strip()
    if not file_id:
        return False
    return lib.file_eligible_for(file_id, "stats")


def register_profile_save_callbacks(
    prefix: str,
    *,
    marked_store: str,
    parsed_id: str,
    saved_from: str,
) -> None:
    @callback(
        Output(f"{prefix}-profile-preview", "children"),
        Output(f"{prefix}-profile-save-btn", "disabled"),
        Input(marked_store, "data"),
        Input(parsed_id, "data"),
        Input(f"{prefix}-table", "selected_row_ids"),
        Input(f"{prefix}-profile-library", "value"),
        State(f"{prefix}-table", "data"),
    )
    def _preview_marked(marked, parsed, selected_ids, library_id, table_data):
        marked_list = _effective_marked_keys(marked, selected_ids, table_data)
        has_data = bool(parsed_players(parsed) if parsed else [])
        has_library = bool(str(library_id or "").strip())
        if not marked_list:
            preview = html.P("No players marked yet.", className="text-muted mb-0")
        else:
            n = len(marked_list)
            preview = html.P(
                f"{n} player{'s' if n != 1 else ''} marked for "
                f"{_library_label(library_id)}.",
                className="text-muted mb-0",
            )
        disabled = not marked_list or not has_data or not has_library
        return preview, disabled

    @callback(
        Output(f"{prefix}-profile-status", "children"),
        Output(marked_store, "data", allow_duplicate=True),
        Input(f"{prefix}-profile-save-btn", "n_clicks"),
        State(marked_store, "data"),
        State(parsed_id, "data"),
        State("ui-settings", "data"),
        State(f"{prefix}-table", "selected_row_ids"),
        State(f"{prefix}-table", "data"),
        State(f"{prefix}-profile-library", "value"),
        prevent_initial_call=True,
    )
    def _save_marked(
        n_clicks, marked, parsed, settings, selected_ids, table_data, library_id
    ):
        if not n_clicks:
            return no_update, no_update
        marked_list = _effective_marked_keys(marked, selected_ids, table_data)
        players = parsed_players(parsed)
        if not marked_list or not players:
            return no_update, no_update
        try:
            items = []
            by_key = {stats_player_key(p): p for p in players if stats_player_key(p)}
            for key in marked_list:
                player = by_key.get(key)
                if not player:
                    continue
                items.append(
                    {
                        "player_key": key,
                        "role_column": "",
                        "row": profiles.build_stats_row_snapshot(
                            player,
                            settings=settings,
                            cohort_players=players,
                        ),
                    }
                )
            if not items:
                raise ValueError("No marked players found in the current data.")
            saved = profiles.save_profile_rows(
                items,
                saved_from=saved_from,
                source_label=_source_label(parsed),
                library_id=library_id,
            )
            msg = html.Div(
                [
                    html.Span("✓ ", className="rs-upload-ok"),
                    html.Span(
                        f"Saved {len(saved)} player{'s' if len(saved) != 1 else ''} "
                        f"to {_library_label(library_id)}."
                    ),
                ],
                className="up-save-row",
            )
        except Exception as exc:
            msg = html.Div(str(exc), className="text-danger small")
            return msg, no_update
        return msg, []


def register_role_profile_save_callbacks(
    prefix: str,
    *,
    marked_store: str,
    parsed_id: str,
    rows_id: str,
    focus_id: str,
    hybrids_id: str,
) -> None:
    @callback(
        Output(f"{prefix}-profile-library", "data"),
        Output(f"{prefix}-profile-library", "value"),
        Input(f"{prefix}-profile-library-poll", "n_intervals"),
        State(f"{prefix}-profile-library", "value"),
        State(f"{prefix}-profile-library", "data"),
    )
    def _refresh_library_options(_n, current, current_data):
        # Pick up libraries created on the Profiles page without a full reload.
        options = profiles.library_options()
        values = {opt["value"] for opt in options}
        active = profiles.active_library_id()
        if current in values:
            value = current
        elif active in values:
            value = active
        else:
            value = options[0]["value"] if options else None
        data_out = options if options != (current_data or []) else no_update
        value_out = value if value != current else no_update
        return data_out, value_out

    @callback(
        Output(f"{prefix}-profile-preview", "children"),
        Output(f"{prefix}-profile-save-btn", "disabled"),
        Input(marked_store, "data"),
        Input(parsed_id, "data"),
        Input(rows_id, "data"),
        Input(focus_id, "data"),
        Input(hybrids_id, "checked"),
        Input(f"{prefix}-table", "selected_row_ids"),
        Input(f"{prefix}-profile-library", "value"),
        State(f"{prefix}-table", "data"),
    )
    def _preview_marked(
        marked,
        parsed,
        payload,
        focus_role,
        hybrids_only,
        selected_ids,
        library_id,
        table_data,
    ):
        marked_list = _effective_marked_keys(marked, selected_ids, table_data)
        has_library = bool(str(library_id or "").strip())
        stats_ok = _profiles_stats_eligible(parsed)
        if not stats_ok:
            preview = html.P(lib.STATS_REQUIRED_MSG, className="text-muted mb-0")
        elif not marked_list:
            preview = html.P("No players marked yet.", className="text-muted mb-0")
        else:
            items = profiles.expand_role_profile_rows(
                marked_list,
                payload if isinstance(payload, dict) else None,
                focus_roles=focus_role,
                hybrids_only=bool(hybrids_only),
                eligible_only=False,
            )
            n_players = len(marked_list)
            n_rows = len(items)
            preview = html.P(
                f"{n_players} player{'s' if n_players != 1 else ''} marked → "
                f"{n_rows} role profile row{'s' if n_rows != 1 else ''} for "
                f"{_library_label(library_id)}.",
                className="text-muted mb-0",
            )
        disabled = not marked_list or not payload or not has_library or not stats_ok
        return preview, disabled

    @callback(
        Output(f"{prefix}-profile-status", "children"),
        Output(marked_store, "data", allow_duplicate=True),
        Output(f"{prefix}-table", "selected_row_ids", allow_duplicate=True),
        Input(f"{prefix}-profile-save-btn", "n_clicks"),
        State(marked_store, "data"),
        State(parsed_id, "data"),
        State(rows_id, "data"),
        State(focus_id, "data"),
        State(hybrids_id, "checked"),
        State("ui-settings", "data"),
        State(f"{prefix}-table", "selected_row_ids"),
        State(f"{prefix}-table", "data"),
        State(f"{prefix}-profile-library", "value"),
        prevent_initial_call=True,
    )
    def _save_marked(
        n_clicks,
        marked,
        parsed,
        payload,
        focus_role,
        hybrids_only,
        settings,
        selected_ids,
        table_data,
        library_id,
    ):
        if not n_clicks:
            return no_update, no_update, no_update
        marked_list = _effective_marked_keys(marked, selected_ids, table_data)
        if not marked_list or not payload:
            return no_update, no_update, no_update
        if not _profiles_stats_eligible(parsed):
            return html.Div(lib.STATS_REQUIRED_MSG, className="text-danger small"), no_update, no_update
        try:
            file_id = (parsed or {}).get("file_id") if isinstance(parsed, dict) else ""
            items = profiles.expand_role_profile_rows(
                marked_list,
                payload,
                focus_roles=focus_role,
                hybrids_only=bool(hybrids_only),
                eligible_only=False,
                role_players=parsed_players(parsed),
                stats_players=profiles.load_stats_players_for_file(file_id or ""),
                file_id=file_id or "",
                settings=settings,
            )
            if not items:
                raise ValueError(
                    "No role profile rows to save for the marked players."
                )
            saved = profiles.save_profile_rows(
                items,
                saved_from="role_scores",
                source_label=_source_label(parsed),
                library_id=library_id,
            )
            msg = html.Div(
                [
                    html.Span("✓ ", className="rs-upload-ok"),
                    html.Span(
                        f"Saved {len(saved)} role profile row"
                        f"{'' if len(saved) == 1 else 's'} to "
                        f"{_library_label(library_id)}."
                    ),
                ],
                className="up-save-row",
            )
        except Exception as exc:
            msg = html.Div(str(exc), className="text-danger small")
            return msg, no_update, no_update
        return msg, [], []
