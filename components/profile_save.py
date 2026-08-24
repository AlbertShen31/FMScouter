"""Save marked shortlist players to the profiles library."""
from __future__ import annotations

from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.scouting_shell import as_list, parsed_players
import services.export_library as lib
import services.player_profiles as profiles
from scoring.stats_scorer import player_key as stats_player_key


def profile_save_panel(*, prefix: str, section_number: int) -> dbc.Card:
    return dbc.Card(
        [
            dbc.CardHeader(f"{section_number}. Profiles"),
            dbc.CardBody(
                [
                    html.P(
                        "Mark players in the shortlist, then save them here. From Role "
                        "scores, one profile row is created per evaluated role — each "
                        "save stores that shortlist row only (not the whole file).",
                        className="text-muted small mb-3",
                    ),
                    html.Div(id=f"{prefix}-profile-preview", className="pf-save-preview"),
                    dmc.Button(
                        "Save marked to profiles",
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
    )
    def _preview_marked(marked, parsed):
        marked_list = as_list(marked)
        has_data = bool(parsed_players(parsed) if parsed else [])
        if not marked_list:
            preview = html.P("No players marked yet.", className="text-muted mb-0")
        else:
            n = len(marked_list)
            preview = html.P(
                f"{n} player{'s' if n != 1 else ''} marked for save.",
                className="text-muted mb-0",
            )
        disabled = not marked_list or not has_data
        return preview, disabled

    @callback(
        Output(f"{prefix}-profile-status", "children"),
        Output(marked_store, "data", allow_duplicate=True),
        Input(f"{prefix}-profile-save-btn", "n_clicks"),
        State(marked_store, "data"),
        State(parsed_id, "data"),
        State("ui-settings", "data"),
        prevent_initial_call=True,
    )
    def _save_marked(n_clicks, marked, parsed, settings):
        if not n_clicks:
            return no_update, no_update
        marked_list = as_list(marked)
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
                            player, settings=settings
                        ),
                    }
                )
            if not items:
                raise ValueError("No marked players found in the current data.")
            saved = profiles.save_profile_rows(
                items,
                saved_from=saved_from,
                source_label=_source_label(parsed),
            )
            msg = html.Div(
                [
                    html.Span("✓ ", className="rs-upload-ok"),
                    html.Span(
                        f"Saved {len(saved)} player{'s' if len(saved) != 1 else ''} "
                        "to Profiles."
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
        Output(f"{prefix}-profile-preview", "children"),
        Output(f"{prefix}-profile-save-btn", "disabled"),
        Input(marked_store, "data"),
        Input(parsed_id, "data"),
        Input(rows_id, "data"),
        Input(focus_id, "data"),
        Input(hybrids_id, "checked"),
    )
    def _preview_marked(marked, parsed, payload, focus_role, hybrids_only):
        marked_list = as_list(marked)
        if not marked_list:
            preview = html.P("No players marked yet.", className="text-muted mb-0")
        else:
            items = profiles.expand_role_profile_rows(
                marked_list,
                payload if isinstance(payload, dict) else None,
                focus_roles=focus_role,
                hybrids_only=bool(hybrids_only),
            )
            n_players = len(marked_list)
            n_rows = len(items)
            preview = html.P(
                f"{n_players} player{'s' if n_players != 1 else ''} marked → "
                f"{n_rows} role profile row{'s' if n_rows != 1 else ''} to save.",
                className="text-muted mb-0",
            )
        disabled = not marked_list or not payload
        return preview, disabled

    @callback(
        Output(f"{prefix}-profile-status", "children"),
        Output(marked_store, "data", allow_duplicate=True),
        Input(f"{prefix}-profile-save-btn", "n_clicks"),
        State(marked_store, "data"),
        State(parsed_id, "data"),
        State(rows_id, "data"),
        State(focus_id, "data"),
        State(hybrids_id, "checked"),
        State("ui-settings", "data"),
        prevent_initial_call=True,
    )
    def _save_marked(
        n_clicks, marked, parsed, payload, focus_role, hybrids_only, settings
    ):
        if not n_clicks:
            return no_update, no_update
        marked_list = as_list(marked)
        if not marked_list or not payload:
            return no_update, no_update
        try:
            file_id = (parsed or {}).get("file_id") if isinstance(parsed, dict) else ""
            items = profiles.expand_role_profile_rows(
                marked_list,
                payload,
                focus_roles=focus_role,
                hybrids_only=bool(hybrids_only),
                role_players=parsed_players(parsed),
                stats_players=profiles.load_stats_players_for_file(file_id or ""),
                settings=settings,
            )
            if not items:
                raise ValueError(
                    "No eligible role rows to save for the marked players."
                )
            saved = profiles.save_profile_rows(
                items,
                saved_from="role_scores",
                source_label=_source_label(parsed),
            )
            msg = html.Div(
                [
                    html.Span("✓ ", className="rs-upload-ok"),
                    html.Span(
                        f"Saved {len(saved)} role profile row"
                        f"{'' if len(saved) == 1 else 's'} to Profiles."
                    ),
                ],
                className="up-save-row",
            )
        except Exception as exc:
            msg = html.Div(str(exc), className="text-danger small")
            return msg, no_update
        return msg, []
