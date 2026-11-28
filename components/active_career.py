"""App-wide active career selector (navbar + shared store)."""
from __future__ import annotations

from dash import Input, Output, State, callback, dcc, html, no_update
import dash_mantine_components as dmc

import services.careers as careers

# Keep selects aligned without store↔value cycles (Dash DepGraph forbids those).
_NAV_SYNC_INTERVAL_MS = 1000


def initial_active_career_store() -> dict:
    """``{"career_id": None, "season_id": None}`` when unset."""
    return careers.get_active()


def navbar_active_career_control() -> html.Div:
    return html.Div(
        [
            html.Span("Career", className="app-nav-career-label"),
            dmc.Select(
                id="nav-active-career",
                data=careers.career_select_options(include_none=True),
                value=careers.select_value_for_active(),
                clearable=False,
                searchable=True,
                allowDeselect=False,
                size="xs",
                w=220,
                placeholder="No career",
                className="app-nav-career-select",
            ),
            dcc.Interval(
                id="nav-active-career-poll",
                interval=_NAV_SYNC_INTERVAL_MS,
                n_intervals=0,
            ),
        ],
        className="app-nav-career",
    )


def _ui_select_value(career_id: str | None) -> str:
    return careers.select_value_for_active(career_id)


def _activate_career(career_id: str, *, prefer_season_id: str | None = None) -> dict:
    """Persist active career, preferring ``prefer_season_id`` when it still exists."""
    cid = careers.normalize_career_id(career_id)
    if not cid:
        return careers.set_active(career_id=None, season_id=None)
    seasons = careers.list_seasons(cid)
    season_ids = {s["id"] for s in seasons}
    if prefer_season_id and prefer_season_id in season_ids:
        season_id = prefer_season_id
    else:
        season_id = seasons[-1]["id"] if seasons else None
    return careers.set_active(career_id=cid, season_id=season_id)


@callback(
    Output("nav-active-career", "data"),
    Input("nav-active-career-poll", "n_intervals"),
    Input("active-career", "data"),
    State("nav-active-career", "data"),
)
def refresh_nav_career_options(_n, _active, current_data):
    options = careers.career_select_options(include_none=True)
    if options == (current_data or []):
        return no_update
    return options


@callback(
    Output("nav-active-career", "value"),
    Input("nav-active-career-poll", "n_intervals"),
    State("active-career", "data"),
    State("nav-active-career", "value"),
)
def sync_nav_career_value_from_store(_n, store, current):
    """Poll-only mirror of the store → nav value.

    Must not Input ``active-career`` (that would cycle with nav → store).
    Careers-page create/delete write nav immediately; select relies on this poll.
    """
    want = _ui_select_value((store or {}).get("career_id"))
    if careers.normalize_career_id(current) == careers.normalize_career_id(want):
        return no_update
    return want


@callback(
    Output("active-career", "data"),
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-career-select", "value", allow_duplicate=True),
    Input("nav-active-career", "value"),
    State("active-career", "data"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def set_active_career_from_nav(value, current_store, rev):
    """Nav → store + Careers select. Careers → nav is poll/button only (no cycle)."""
    cid = careers.normalize_career_id(value)
    current = careers.get_active()
    current_id = current.get("career_id") or None
    store_now = current_store if isinstance(current_store, dict) else {}
    store_now_id = store_now.get("career_id") or None
    select_val = _ui_select_value(cid)
    if cid == (current_id or "") and cid == (store_now_id or ""):
        return no_update, no_update, no_update
    try:
        if cid != (current_id or ""):
            prefer = store_now.get("season_id") if cid == store_now_id else None
            payload = _activate_career(cid, prefer_season_id=prefer)
        else:
            payload = current
    except Exception:
        return no_update, no_update, no_update
    if cid == (current_id or ""):
        return payload, no_update, select_val
    return payload, int(rev or 0) + 1, select_val
