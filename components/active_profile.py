"""App-wide active profile library selector (navbar + shared store)."""
from __future__ import annotations

from dash import Input, Output, State, callback, dcc, html, no_update
import dash_mantine_components as dmc

import services.formations as fm
import services.player_profiles as profiles


def initial_active_profile_store():
    """``None`` when no profile is selected; otherwise the library id."""
    return profiles.active_library_id() or None


def navbar_active_profile_control() -> html.Div:
    return html.Div(
        [
            html.Span("Profile", className="app-nav-profile-label"),
            dmc.Select(
                id="nav-active-profile",
                data=profiles.library_select_options(include_none=True),
                value=profiles.select_value_for_active(),
                clearable=False,
                searchable=True,
                allowDeselect=False,
                size="xs",
                w=220,
                placeholder="No profile",
                className="app-nav-profile-select",
            ),
            dcc.Interval(
                id="nav-active-profile-poll",
                interval=3000,
                n_intervals=0,
            ),
        ],
        className="app-nav-profile",
    )


def _formation_outputs_for_library(library_id: str) -> tuple:
    """Formation select / store / focus updates when the active library changes."""
    lid = profiles.normalize_library_id(library_id)
    if not lid:
        return no_update, no_update, []
    meta = profiles.get_library(lid) or {}
    fid = str(meta.get("formation_id") or "").strip()
    if fid and fm.exists(fid):
        try:
            fm.load(fid, persist=True)
        except Exception:
            pass
    return (fid or no_update), (fid or no_update), []


@callback(
    Output("nav-active-profile", "data"),
    Input("nav-active-profile-poll", "n_intervals"),
    Input("active-profile", "data"),
    State("nav-active-profile", "data"),
)
def refresh_nav_profile_options(_n, _active, current_data):
    options = profiles.library_select_options(include_none=True)
    if options == (current_data or []):
        return no_update
    return options


@callback(
    Output("active-profile", "data"),
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-formation-select", "value", allow_duplicate=True),
    Output("pf-formation", "data", allow_duplicate=True),
    Output("pf-focus-role", "data", allow_duplicate=True),
    Input("nav-active-profile", "value"),
    State("active-profile", "data"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def set_active_profile_from_nav(value, current_store, rev):
    lid = profiles.normalize_library_id(value)
    current = profiles.active_library_id()
    store_next = lid or None
    store_now = current_store or None
    if lid == current and store_next == store_now:
        return no_update, no_update, no_update, no_update, no_update
    try:
        if lid != current:
            profiles.set_active_library(lid if lid else None)
    except Exception:
        return no_update, no_update, no_update, no_update, no_update
    if lid == current:
        # Store catch-up only (e.g. Profiles page already persisted).
        return store_next, no_update, no_update, no_update, no_update
    formation, formation_store, focus = _formation_outputs_for_library(lid)
    return store_next, int(rev or 0) + 1, formation, formation_store, focus


@callback(
    Output("nav-active-profile", "value"),
    Input("active-profile", "data"),
    State("nav-active-profile", "value"),
)
def sync_nav_profile_value(store, current):
    want = store if store else profiles.NONE_LIBRARY_VALUE
    if (current or profiles.NONE_LIBRARY_VALUE) == want:
        return no_update
    if profiles.normalize_library_id(current) == profiles.normalize_library_id(want):
        return want if current != want else no_update
    return want


@callback(
    Output("pf-library-select", "value", allow_duplicate=True),
    Input("active-profile", "data"),
    State("pf-library-select", "value"),
    prevent_initial_call=True,
)
def sync_profiles_page_select(store, current):
    want = store if store else profiles.NONE_LIBRARY_VALUE
    if profiles.normalize_library_id(current) == profiles.normalize_library_id(want):
        return no_update
    return want
