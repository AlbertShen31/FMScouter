"""Career game containers: import mid/end season snapshots and switch seasons."""
from __future__ import annotations

from pathlib import Path

from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon
from components.scouting_shell import decode_upload, job_busy_overlay
import services.career_import as career_import
import services.careers as careers
import services.compute_progress as compute_progress
import services.fmsave_export as fms

register_page(__name__, path="/careers", name="Careers")

PAGE_TIP = (
    "Each Career is one Football Manager game. Stage .fm saves or Moneyball CSVs, "
    "then drag each into a mid/end season slot — at most two snapshots per season. "
    "Raw saves are not kept; only compact player attributes + OVERALL season stats. "
    "Switch seasons here; playground pages will use the active career/season later."
)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v is not None]
    return [value]


def _fm_paths_label(paths: list[str]) -> str:
    cleaned = [str(p).strip() for p in paths if str(p).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    names = [Path(p).name for p in cleaned]
    return f"{len(cleaned)} saves: " + ", ".join(names)


def _card_header(title: str, tip: str, help_id: str) -> dbc.CardHeader:
    return dbc.CardHeader(
        html.Div(
            [
                html.Span(title),
                *help_icon(tip, help_id),
            ],
            className="rs-card-header-title",
        )
    )


def _status_alert(message: str, *, color: str = "info") -> dbc.Alert:
    return dbc.Alert(
        message,
        color=color,
        className="cr-status-alert mb-0",
        dismissable=True,
        duration=12000 if color in {"success", "info"} else None,
    )


def _slot_badge(meta: dict | None, label: str) -> html.Span:
    if not meta:
        return html.Span(f"{label}: empty", className="cr-slot empty")
    count = int(meta.get("player_count") or 0)
    game_date = meta.get("game_date") or "—"
    return html.Span(
        f"{label}: {count:,} players · {game_date}",
        className="cr-slot filled",
    )


def _slot_drop_target(season: dict, slot: str, meta: dict | None) -> html.Div:
    label = "Mid" if slot == "mid" else "End"
    return html.Div(
        _slot_badge(meta, label),
        className="cr-slot-drop"
        + (" is-filled" if meta else " is-empty")
        + (" is-suggested" if season.get("suggested_slot") == slot else ""),
        **{
            "data-season-id": season["id"],
            "data-slot": slot,
            "data-label": season.get("label") or season["id"],
            "data-year-start": str(season.get("year_start") or ""),
            "data-year-end": str(season.get("year_end") or ""),
        },
    )


def _merge_seasons_with_staging(
    seasons: list[dict],
    staging_items: list[dict],
) -> list[dict]:
    by_id: dict[str, dict] = {}
    for season in seasons:
        by_id[season["id"]] = {
            **season,
            "phantom": False,
            "suggested_slot": None,
        }
    for item in staging_items:
        sid = item.get("season_id")
        if not sid:
            continue
        if sid not in by_id:
            by_id[sid] = {
                "id": sid,
                "label": item.get("season_label") or sid,
                "year_start": item.get("year_start") or 0,
                "year_end": item.get("year_end") or 0,
                "slots": {"mid": None, "end": None},
                "phantom": True,
                "suggested_slot": item.get("suggested_slot"),
            }
        elif by_id[sid].get("suggested_slot") is None:
            by_id[sid]["suggested_slot"] = item.get("suggested_slot")
    out = list(by_id.values())
    out.sort(key=lambda s: (s.get("year_start") or 0, s.get("label") or ""))
    return out


def _seasons_table(
    career_id: str | None,
    active_season_id: str | None,
    staging_items: list[dict] | None = None,
) -> html.Div:
    if not career_id:
        return html.P("Create or select a career first.", className="text-muted mb-0")
    seasons = _merge_seasons_with_staging(
        careers.list_seasons(career_id),
        staging_items if staging_items is not None else careers.list_staging(career_id),
    )
    if not seasons:
        return html.P(
            "No seasons yet — stage files, then drag them onto Mid/End slots "
            "(suggested seasons appear automatically).",
            className="text-muted mb-0",
        )
    rows = []
    for season in reversed(seasons):
        sid = season["id"]
        active = sid == active_season_id
        phantom = bool(season.get("phantom"))
        label_children = [
            html.Span(
                season["label"],
                className="cr-season-label"
                + (" is-active" if active else "")
                + (" is-phantom" if phantom else ""),
            )
        ]
        if phantom:
            label_children.append(
                html.Span("new", className="cr-season-phantom-tag")
            )
        rows.append(
            html.Tr(
                [
                    html.Td(html.Div(label_children, className="cr-season-label-wrap")),
                    html.Td(
                        _slot_drop_target(season, "mid", season["slots"].get("mid"))
                    ),
                    html.Td(
                        _slot_drop_target(season, "end", season["slots"].get("end"))
                    ),
                    html.Td(
                        dmc.Button(
                            "Active" if active else "Set active",
                            id={"type": "cr-set-season", "index": sid},
                            n_clicks=0,
                            size="xs",
                            variant="filled" if active else "default",
                            disabled=active or phantom,
                        )
                        if not phantom
                        else html.Span(
                            "Drop to create",
                            className="cr-season-drop-hint text-muted",
                        )
                    ),
                ],
                className="cr-season-row"
                + (" is-active" if active else "")
                + (" is-phantom" if phantom else ""),
            )
        )
    return dbc.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Season"),
                        html.Th("Mid"),
                        html.Th("End"),
                        html.Th(""),
                    ]
                )
            ),
            html.Tbody(rows),
        ],
        bordered=False,
        hover=True,
        size="sm",
        className="cr-seasons-table mb-0",
    )


def _staging_panel(career_id: str | None) -> html.Div:
    items = careers.list_staging(career_id) if career_id else []
    if not career_id:
        body: html.Div | html.P = html.P(
            "Select a career, then stage .fm / CSV files here.",
            className="text-muted mb-0",
        )
    elif not items:
        body = html.P(
            "Staging is empty. Choose saves or CSVs above, then click Stage.",
            className="text-muted mb-0",
        )
    else:
        cards = []
        for item in items:
            suggested = (
                f"{item.get('season_label') or item.get('season_id') or '—'} / "
                f"{item.get('suggested_slot') or '—'}"
            )
            cards.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span(
                                            item.get("source_name") or item["id"],
                                            className="cr-stage-name",
                                        ),
                                        html.Span(
                                            "⋮⋮",
                                            className="cr-stage-handle",
                                            title="Drag onto a Mid/End slot",
                                        ),
                                    ],
                                    className="cr-stage-card-top",
                                ),
                                html.Div(
                                    [
                                        html.Span(
                                            f"Suggested {suggested}",
                                            className="cr-stage-meta",
                                        ),
                                        html.Span(
                                            f"{int(item.get('player_count') or 0):,} players",
                                            className="cr-stage-meta",
                                        ),
                                        html.Span(
                                            f"date={item.get('game_date') or '—'}",
                                            className="cr-stage-meta",
                                        ),
                                    ],
                                    className="cr-stage-card-meta",
                                ),
                            ],
                            className="cr-stage-card-drag",
                            draggable="true",
                            title="Drag onto a Mid/End slot",
                            **{"data-staging-id": item["id"]},
                        ),
                        dmc.Button(
                            "Remove",
                            id={"type": "cr-stage-remove", "index": item["id"]},
                            n_clicks=0,
                            size="xs",
                            variant="subtle",
                            color="gray",
                            className="cr-stage-remove",
                        ),
                    ],
                    className="cr-stage-card"
                    + (
                        f" suggests-{item.get('suggested_slot')}"
                        if item.get("suggested_slot")
                        else ""
                    ),
                )
            )
        body = html.Div(cards, className="cr-stage-list")
    return html.Div(
        [
            body,
            html.Div(
                [
                    dmc.Button(
                        "Clear staging",
                        id="cr-stage-clear",
                        n_clicks=0,
                        size="xs",
                        variant="light",
                        color="gray",
                        disabled=not items,
                    ),
                    html.Span(
                        "Drag a card onto a Mid or End slot below.",
                        className="cr-stage-hint text-muted",
                    ),
                ],
                className="cr-stage-footer",
            ),
        ],
        className="cr-stage-panel",
    )


def _career_shell(active: dict | None = None) -> tuple:
    active = active or careers.get_active()
    career_id = active.get("career_id")
    options = careers.career_options()
    meta = careers.get_career(career_id) if career_id else {"show_hidden_attrs": False}
    staging_items = careers.list_staging(career_id) if career_id else []
    return (
        options,
        career_id,
        bool(meta.get("show_hidden_attrs")),
        active,
        _staging_panel(career_id),
        _seasons_table(career_id, active.get("season_id"), staging_items),
    )


def layout(**_kwargs):
    active = careers.get_active()
    career_id = active.get("career_id")
    season_id = active.get("season_id")
    options = careers.career_options()
    meta = careers.get_career(career_id) if career_id else None
    return dbc.Container(
        [
            dcc.Store(id="cr-rev", data=0),
            dcc.Store(id="cr-active", data=active),
            dcc.Store(id="cr-pending", data=None),
            dcc.Store(id="cr-fm-paths", data=[]),
            dcc.Store(id="cr-stage-drop", data=None),
            dcc.Store(id="cr-job-tick", data=0),
            dcc.Interval(
                id="cr-progress-poll",
                interval=800,
                n_intervals=0,
                disabled=True,
            ),
            html.H4("Careers", className="mb-2"),
            html.P(
                "Separate from Uploads and formation Profiles. One career per FM game. "
                "Stage extracts players into a holding area (can take a while), then drag "
                "each file onto a Mid/End season slot. A progress overlay covers this page "
                "while Stage / assign runs.",
                className="text-muted mb-3",
            ),
            html.Div(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                dbc.Card(
                                    [
                                        _card_header("1. Career", PAGE_TIP, "cr-tip"),
                                        dbc.CardBody(
                                            [
                                                html.Label(
                                                    "Active career",
                                                    className="rs-field-label",
                                                ),
                                                dmc.Select(
                                                    id="cr-career-select",
                                                    data=options,
                                                    value=career_id,
                                                    placeholder="Select a career",
                                                    clearable=False,
                                                    className="mb-3",
                                                ),
                                                html.Label(
                                                    "New career name",
                                                    className="rs-field-label",
                                                ),
                                                html.Div(
                                                    [
                                                        dmc.TextInput(
                                                            id="cr-create-name",
                                                            placeholder="e.g. Romania 2026",
                                                            className="cr-inline-input",
                                                        ),
                                                        dmc.Button(
                                                            "Create",
                                                            id="cr-create",
                                                            n_clicks=0,
                                                            variant="filled",
                                                        ),
                                                    ],
                                                    className="cr-inline-row mb-3",
                                                ),
                                                dmc.Switch(
                                                    id="cr-show-hidden",
                                                    label=(
                                                        "Show hidden attributes "
                                                        "(stored; UI later)"
                                                    ),
                                                    checked=bool(
                                                        (meta or {}).get(
                                                            "show_hidden_attrs"
                                                        )
                                                    ),
                                                    className="mb-2",
                                                ),
                                                html.Div(
                                                    [
                                                        dmc.Button(
                                                            "Rename…",
                                                            id="cr-rename-open",
                                                            n_clicks=0,
                                                            variant="default",
                                                            size="xs",
                                                        ),
                                                        dmc.Button(
                                                            "Delete career",
                                                            id="cr-delete",
                                                            n_clicks=0,
                                                            variant="light",
                                                            color="red",
                                                            size="xs",
                                                        ),
                                                    ],
                                                    className="cr-actions-row",
                                                ),
                                                html.Div(
                                                    id="cr-career-status",
                                                    className="mt-2",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-3",
                                ),
                                md=4,
                            ),
                            dbc.Col(
                                dbc.Card(
                                    [
                                        _card_header(
                                            "2. Stage files",
                                            "Choose one or more .fm saves (preferred) or "
                                            "Moneyball CSVs, then Stage to extract players "
                                            "into the holding area. Each file keeps its own "
                                            "suggested season/slot from the save date. "
                                            "Game date override applies only when staging a "
                                            "single file (needed for CSVs).",
                                            "cr-import-tip",
                                        ),
                                        dbc.CardBody(
                                            [
                                                html.Label(
                                                    "Save file(s) (.fm)",
                                                    className="rs-field-label",
                                                ),
                                                html.Div(
                                                    [
                                                        dmc.TextInput(
                                                            id="cr-fm-path",
                                                            value="",
                                                            placeholder="No save selected",
                                                            readOnly=True,
                                                            className="sx-path-input",
                                                        ),
                                                        dmc.Button(
                                                            "Choose files…",
                                                            id="cr-fm-browse",
                                                            n_clicks=0,
                                                            variant="default",
                                                        ),
                                                    ],
                                                    className="sx-path-row mb-2",
                                                ),
                                                html.Label(
                                                    "Or Moneyball CSV(s)",
                                                    className="rs-field-label",
                                                ),
                                                dcc.Upload(
                                                    id="cr-csv-upload",
                                                    children=html.Div(
                                                        "Drop CSV(s) here or click to select"
                                                    ),
                                                    className="cr-csv-drop mb-3",
                                                    multiple=True,
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Scope (.fm)",
                                                                    className="rs-field-label",
                                                                ),
                                                                dmc.SegmentedControl(
                                                                    id="cr-scope",
                                                                    data=[
                                                                        {
                                                                            "label": "All players",
                                                                            "value": "all",
                                                                        },
                                                                        {
                                                                            "label": "Managed squad",
                                                                            "value": "squad",
                                                                        },
                                                                    ],
                                                                    value="all",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Game date (CSV / override)",
                                                                    className="rs-field-label",
                                                                ),
                                                                dmc.TextInput(
                                                                    id="cr-game-date",
                                                                    placeholder="YYYY-MM-DD",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                    ],
                                                    className="mb-3 g-2",
                                                ),
                                                html.Div(
                                                    [
                                                        dmc.Button(
                                                            "Preview",
                                                            id="cr-preview",
                                                            n_clicks=0,
                                                            variant="default",
                                                        ),
                                                        dmc.Button(
                                                            "Stage",
                                                            id="cr-stage",
                                                            n_clicks=0,
                                                            variant="filled",
                                                        ),
                                                    ],
                                                    className="cr-actions-row mb-2",
                                                ),
                                                html.Div(id="cr-import-status"),
                                            ]
                                        ),
                                    ],
                                    className="mb-3",
                                ),
                                md=8,
                            ),
                        ]
                    ),
                    dbc.Card(
                        [
                            _card_header(
                                "3. Staging",
                                "Extracted snapshots wait here until you drag them onto "
                                "a Mid or End season slot. Suggested season rows appear "
                                "below automatically for new seasons.",
                                "cr-staging-tip",
                            ),
                            dbc.CardBody(
                                html.Div(
                                    id="cr-staging-body",
                                    children=_staging_panel(career_id),
                                )
                            ),
                        ],
                        className="mb-3",
                    ),
                    dbc.Card(
                        [
                            _card_header(
                                "4. Seasons",
                                "Drop staged files onto Mid/End slots. Occupied slots "
                                "ask before replace. Switch the active season for this "
                                "career — playground pages will read from it later.",
                                "cr-seasons-tip",
                            ),
                            dbc.CardBody(
                                [
                                    html.Div(
                                        id="cr-seasons-body",
                                        children=_seasons_table(career_id, season_id),
                                    ),
                                    html.Hr(className="my-3"),
                                    html.Label(
                                        "Rename active season label",
                                        className="rs-field-label",
                                    ),
                                    html.Div(
                                        [
                                            dmc.TextInput(
                                                id="cr-rename-season",
                                                placeholder="Season label",
                                                className="cr-inline-input",
                                            ),
                                            dmc.Button(
                                                "Save label",
                                                id="cr-rename-season-btn",
                                                n_clicks=0,
                                                variant="default",
                                            ),
                                        ],
                                        className="cr-inline-row",
                                    ),
                                    html.Div(id="cr-season-status", className="mt-2"),
                                ]
                            ),
                        ],
                        className="mb-4",
                    ),
                    job_busy_overlay(
                        "cr-busy",
                        prefix="cr",
                        initial_label="Working…",
                    ),
                ],
                className="rs-shortlist-busy-host",
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Replace season slot?")),
                    dbc.ModalBody(id="cr-replace-body"),
                    dbc.ModalFooter(
                        [
                            dmc.Button(
                                "Cancel",
                                id="cr-replace-cancel",
                                n_clicks=0,
                                variant="default",
                            ),
                            dmc.Button(
                                "Replace",
                                id="cr-replace-confirm",
                                n_clicks=0,
                                variant="filled",
                                color="red",
                            ),
                        ]
                    ),
                ],
                id="cr-replace-modal",
                is_open=False,
                centered=True,
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Rename career")),
                    dbc.ModalBody(
                        dmc.TextInput(id="cr-rename-input", placeholder="Career name")
                    ),
                    dbc.ModalFooter(
                        [
                            dmc.Button(
                                "Cancel",
                                id="cr-rename-cancel",
                                n_clicks=0,
                                variant="default",
                            ),
                            dmc.Button(
                                "Save",
                                id="cr-rename-save",
                                n_clicks=0,
                                variant="filled",
                            ),
                        ]
                    ),
                ],
                id="cr-rename-modal",
                is_open=False,
                centered=True,
            ),
        ],
        fluid=True,
        className="py-3 cr-page",
    )


@callback(
    Output("cr-career-select", "data"),
    Output("cr-career-select", "value"),
    Output("cr-show-hidden", "checked"),
    Output("cr-active", "data"),
    Output("cr-staging-body", "children"),
    Output("cr-seasons-body", "children"),
    Input("cr-rev", "data"),
)
def cr_refresh_shell(rev):
    return _career_shell()


@callback(
    Output("cr-rev", "data"),
    Output("cr-career-status", "children"),
    Output("cr-create-name", "value"),
    Input("cr-create", "n_clicks"),
    State("cr-create-name", "value"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_create_career(n_clicks, name, rev):
    if not n_clicks:
        return no_update, no_update, no_update
    try:
        meta = careers.create_career(name or "")
        careers.set_active(career_id=meta["id"], season_id=None)
        return (
            int(rev or 0) + 1,
            html.Span(f"Created “{meta['name']}”.", className="text-success"),
            "",
        )
    except Exception as exc:  # noqa: BLE001
        return no_update, html.Span(str(exc), className="text-danger"), no_update


@callback(
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-career-status", "children", allow_duplicate=True),
    Input("cr-delete", "n_clicks"),
    State("cr-career-select", "value"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_delete_career(n_clicks, career_id, rev):
    if not n_clicks:
        return no_update, no_update
    if not career_id:
        return no_update, html.Span("No career selected.", className="text-warning")
    careers.delete_career(career_id)
    return int(rev or 0) + 1, html.Span("Career deleted.", className="text-muted")


@callback(
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-career-status", "children", allow_duplicate=True),
    Input("cr-career-select", "value"),
    State("cr-active", "data"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_select_career(career_id, active_data, rev):
    if not career_id:
        return no_update, no_update
    current = careers.get_active()
    if current.get("career_id") == career_id:
        # Avoid rev loops when shell refresh rewrites the same select value.
        return no_update, no_update
    seasons = careers.list_seasons(career_id)
    prefer = (active_data or {}).get("season_id")
    if prefer and any(s["id"] == prefer for s in seasons):
        careers.set_active(career_id=career_id, season_id=prefer)
    else:
        season_id = seasons[-1]["id"] if seasons else None
        careers.set_active(career_id=career_id, season_id=season_id)
    return int(rev or 0) + 1, ""


@callback(
    Output("cr-career-status", "children", allow_duplicate=True),
    Input("cr-show-hidden", "checked"),
    State("cr-career-select", "value"),
    prevent_initial_call=True,
)
def cr_toggle_hidden(show_hidden, career_id):
    if not career_id:
        return html.Span("Select a career first.", className="text-warning")
    careers.set_show_hidden_attrs(career_id, bool(show_hidden))
    return html.Span(
        "Hidden attributes "
        + ("enabled" if show_hidden else "disabled")
        + " for this career.",
        className="text-muted",
    )


@callback(
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-season-status", "children"),
    Input("cr-rename-season-btn", "n_clicks"),
    State("cr-career-select", "value"),
    State("cr-active", "data"),
    State("cr-rename-season", "value"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_rename_season(n_clicks, career_id, active_data, label, rev):
    if not n_clicks:
        return no_update, no_update
    season_id = (active_data or {}).get("season_id")
    if not career_id or not season_id:
        return no_update, html.Span(
            "Select an active season first.", className="text-warning"
        )
    try:
        season = careers.rename_season(career_id, season_id, label or "")
    except Exception as exc:  # noqa: BLE001
        return no_update, html.Span(str(exc), className="text-danger")
    return (
        int(rev or 0) + 1,
        html.Span(
            f"Season label set to “{season['label']}”.", className="text-success"
        ),
    )


@callback(
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-season-status", "children", allow_duplicate=True),
    Input({"type": "cr-set-season", "index": ALL}, "n_clicks"),
    State("cr-career-select", "value"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_set_active_season(n_clicks_list, career_id, rev):
    if not any(n_clicks_list or []):
        return no_update, no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or not career_id:
        return no_update, no_update
    sid = triggered.get("index")
    if not sid:
        return no_update, no_update
    try:
        careers.set_active(career_id=career_id, season_id=sid)
    except Exception as exc:  # noqa: BLE001
        return no_update, html.Span(str(exc), className="text-danger")
    return int(rev or 0) + 1, html.Span(
        f"Active season → {sid}", className="text-success"
    )


@callback(
    Output("cr-fm-paths", "data"),
    Output("cr-fm-path", "value"),
    Input("cr-fm-browse", "n_clicks"),
    State("cr-fm-paths", "data"),
    State("cr-fm-path", "value"),
    prevent_initial_call=True,
)
def cr_browse_fm(n_clicks, current_paths, current_path):
    if not n_clicks:
        return no_update, no_update
    seed = ""
    existing = [str(p).strip() for p in _as_list(current_paths) if str(p).strip()]
    if existing:
        seed = existing[0]
    elif current_path:
        seed = str(current_path).strip()
    picked = fms.pick_fm_save_files(seed or fms.default_save_path(), multiple=True)
    if not picked:
        return no_update, no_update
    return picked, _fm_paths_label(picked)


@callback(
    Output("cr-fm-paths", "data", allow_duplicate=True),
    Output("cr-fm-path", "value", allow_duplicate=True),
    Input("cr-csv-upload", "contents"),
    prevent_initial_call=True,
)
def cr_clear_fm_on_csv(contents):
    if not contents:
        return no_update, no_update
    return [], ""


clientside_callback(
    """
    function(previewN, stageN, replaceN, dropData) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var prop = String(trig[0].prop_id || "");
        var labelText = "Working…";
        if (prop.indexOf("cr-preview") !== -1) {
            if (!previewN) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            labelText = "Reading save date…";
        } else if (prop.indexOf("cr-stage") !== -1 && prop.indexOf("cr-stage-drop") === -1) {
            if (!stageN) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            labelText = "Staging snapshot…";
        } else if (prop.indexOf("cr-stage-drop") !== -1) {
            if (!dropData) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            labelText = "Assigning to season slot…";
        } else if (prop.indexOf("cr-replace-confirm") !== -1) {
            if (!replaceN) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            labelText = "Replacing snapshot…";
        } else {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var label = document.getElementById("cr-busy-label");
        if (label) { label.textContent = labelText; }
        var detail = document.getElementById("cr-busy-detail");
        if (detail) { detail.textContent = ""; }
        var track = document.getElementById("cr-busy-track");
        if (track) {
            track.className = "rs-busy-progress is-indeterminate";
        }
        return ["rs-shortlist-busy is-on t-" + String(Date.now()), false];
    }
    """,
    Output("cr-busy", "className"),
    Output("cr-progress-poll", "disabled"),
    Input("cr-preview", "n_clicks"),
    Input("cr-stage", "n_clicks"),
    Input("cr-replace-confirm", "n_clicks"),
    Input("cr-stage-drop", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(_tick) {
        var el = document.getElementById("cr-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        return ["rs-shortlist-busy", true];
    }
    """,
    Output("cr-busy", "className", allow_duplicate=True),
    Output("cr-progress-poll", "disabled", allow_duplicate=True),
    Input("cr-job-tick", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("cr-busy-label", "children"),
    Output("cr-busy-track", "className"),
    Output("cr-busy-bar", "style"),
    Output("cr-busy-detail", "children"),
    Input("cr-progress-poll", "n_intervals"),
)
def cr_poll_progress(_n):
    props = compute_progress.ui_props()
    if not props.get("active"):
        return no_update, no_update, no_update, no_update
    return (
        props["label"],
        props["track_class"],
        props["bar_style"],
        props["detail"] or "",
    )


@callback(
    Output("cr-game-date", "value"),
    Output("cr-import-status", "children"),
    Output("cr-pending", "data"),
    Output("cr-replace-modal", "is_open"),
    Output("cr-replace-body", "children"),
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-job-tick", "data"),
    Input("cr-preview", "n_clicks"),
    Input("cr-stage", "n_clicks"),
    Input("cr-replace-confirm", "n_clicks"),
    Input("cr-replace-cancel", "n_clicks"),
    Input("cr-stage-drop", "data"),
    State("cr-fm-paths", "data"),
    State("cr-fm-path", "value"),
    State("cr-csv-upload", "contents"),
    State("cr-csv-upload", "filename"),
    State("cr-scope", "value"),
    State("cr-game-date", "value"),
    State("cr-career-select", "value"),
    State("cr-pending", "data"),
    State("cr-rev", "data"),
    State("cr-job-tick", "data"),
    prevent_initial_call=True,
)
def cr_preview_stage_or_assign(
    _preview_clicks,
    _stage_clicks,
    _replace_confirm,
    _replace_cancel,
    drop_data,
    fm_paths,
    fm_path,
    csv_contents,
    csv_filename,
    scope,
    game_date,
    career_id,
    pending,
    rev,
    job_tick,
):
    triggered = ctx.triggered_id
    next_tick = int(job_tick or 0) + 1

    if triggered == "cr-replace-cancel":
        return (
            no_update,
            _status_alert("Assign cancelled.", color="secondary"),
            None,
            False,
            no_update,
            no_update,
            next_tick,
        )

    def _resolve_fm_paths() -> list[str]:
        paths = [str(p).strip() for p in _as_list(fm_paths) if str(p).strip()]
        if paths:
            return paths
        single = str(fm_path or "").strip()
        if not single or " saves: " in single:
            return []
        if Path(single).suffix.lower() == ".fm" or Path(single).is_file():
            return [single]
        return []

    def _csv_items() -> list[tuple[str, str]]:
        contents_list = _as_list(csv_contents)
        names_list = _as_list(csv_filename)
        items: list[tuple[str, str]] = []
        for idx, contents in enumerate(contents_list):
            name = (
                names_list[idx]
                if idx < len(names_list) and names_list[idx]
                else f"upload-{idx + 1}.csv"
            )
            items.append((contents, str(name)))
        return items

    def _sources() -> list[dict]:
        paths = _resolve_fm_paths()
        if paths:
            return [{"kind": "fm", "path": path} for path in paths]
        csv_items = _csv_items()
        if csv_items:
            return [
                {"kind": "csv", "contents": contents, "filename": name}
                for contents, name in csv_items
            ]
        raise ValueError("Choose .fm save(s) or drop Moneyball CSV(s) first.")

    def _peek_one(source: dict, *, date_override: str | None):
        if source["kind"] == "fm":
            return career_import.peek_classification(
                save_path=source["path"],
                game_date_override=date_override,
            )
        text = decode_upload(source["contents"])
        return career_import.peek_classification(
            csv_text=text,
            source_name=source["filename"],
            game_date_override=date_override,
        )

    def _source_label(source: dict) -> str:
        if source["kind"] == "fm":
            return Path(source["path"]).name
        return source.get("filename") or "upload.csv"

    def _fail(message: str, *, pending_out=None, modal=False, body=no_update, color="danger"):
        return (
            no_update,
            _status_alert(str(message), color=color),
            pending if pending_out is None else pending_out,
            modal,
            body,
            no_update,
            next_tick,
        )

    def _assign_staging(*, replace: bool, payload: dict):
        staging_id = str(payload.get("staging_id") or "").strip()
        season_id = str(payload.get("season_id") or "").strip()
        slot = str(payload.get("slot") or "").strip().lower()
        if not career_id:
            return _fail("Select or create a career first.", color="warning")
        if not staging_id or not season_id or slot not in careers.SLOTS:
            return _fail("Invalid drop target.", color="warning")
        year_start = payload.get("year_start")
        year_end = payload.get("year_end")
        try:
            year_start_i = int(year_start) if year_start not in (None, "") else None
        except (TypeError, ValueError):
            year_start_i = None
        try:
            year_end_i = int(year_end) if year_end not in (None, "") else None
        except (TypeError, ValueError):
            year_end_i = None
        season_label = str(payload.get("season_label") or "").strip() or None
        compute_progress.begin(
            "Replacing snapshot…" if replace else "Assigning to season slot…",
            phase="Writing snapshot…",
        )
        try:
            result = career_import.commit_staging_to_slot(
                career_id,
                staging_id,
                season_id=season_id,
                slot=slot,
                season_label=season_label,
                year_start=year_start_i,
                year_end=year_end_i,
                replace=replace,
            )
        except Exception as exc:  # noqa: BLE001
            compute_progress.end()
            return _fail(str(exc))
        compute_progress.end()
        if result.get("needs_replace"):
            item = careers.get_staging_item(career_id, staging_id) or {}
            body = (
                f"The {slot} slot for season {season_id} already has a snapshot. "
                f"Replace it with “{item.get('source_name') or staging_id}”?"
            )
            return (
                no_update,
                _status_alert(
                    "Slot occupied — confirm replace in the dialog.",
                    color="warning",
                ),
                {
                    "staging_id": staging_id,
                    "season_id": season_id,
                    "slot": slot,
                    "season_label": season_label,
                    "year_start": year_start_i,
                    "year_end": year_end_i,
                },
                True,
                body,
                no_update,
                next_tick,
            )
        msg = (
            f"Assigned {result.get('player_count', 0):,} players to "
            f"{result.get('season_label')} / {result.get('slot')}"
            + (" (replaced)." if result.get("replaced") else ".")
        )
        return (
            no_update,
            _status_alert(msg, color="success"),
            None,
            False,
            no_update,
            int(rev or 0) + 1,
            next_tick,
        )

    if triggered == "cr-preview":
        compute_progress.begin("Reading save date…", phase="Opening save…")
        try:
            sources = _sources()
            single = len(sources) == 1
            peeks = []
            for idx, source in enumerate(sources, start=1):
                compute_progress.update(
                    phase=f"Reading {idx}/{len(sources)}: {_source_label(source)}",
                )
                peeks.append(
                    _peek_one(
                        source,
                        date_override=(game_date or None) if single else None,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            compute_progress.end()
            return _fail(str(exc), pending_out=None)
        compute_progress.end()

        if len(peeks) == 1:
            classification = peeks[0]["classification"]
            meta = peeks[0]["meta"]
            summary = (
                f"Preview complete — suggested {classification.get('label')} / "
                f"{classification.get('slot')} · "
                f"date={classification.get('game_date') or '—'} · "
                f"source={meta.get('source_name') or meta.get('source')}"
            )
            return (
                classification.get("game_date") or game_date or "",
                _status_alert(summary, color="info"),
                {
                    "classification": classification,
                    "source": meta.get("source"),
                },
                False,
                no_update,
                no_update,
                next_tick,
            )

        lines = [f"Preview complete — {len(peeks)} files:"]
        for source, peek in zip(sources, peeks):
            classification = peek["classification"]
            lines.append(
                f"• {_source_label(source)} → {classification.get('label')} / "
                f"{classification.get('slot')} · "
                f"date={classification.get('game_date') or '—'}"
            )
        lines.append("Stage to extract, then drag each into a Mid/End slot.")
        return (
            no_update,
            _status_alert("\n".join(lines), color="info"),
            {"batch": True, "count": len(peeks)},
            False,
            no_update,
            no_update,
            next_tick,
        )

    if triggered == "cr-stage":
        if not career_id:
            return _fail("Select or create a career first.", color="warning")
        compute_progress.begin("Staging snapshot…", phase="Opening save…")
        try:
            sources = _sources()
            single = len(sources) == 1
            staged = []
            for idx, source in enumerate(sources, start=1):
                compute_progress.update(
                    phase=f"Staging {idx}/{len(sources)}: {_source_label(source)}",
                )
                if source["kind"] == "fm":
                    result = career_import.stage_import(
                        career_id,
                        save_path=source["path"],
                        scope=scope or "all",
                        game_date_override=(game_date or None) if single else None,
                    )
                else:
                    text = decode_upload(source["contents"])
                    result = career_import.stage_import(
                        career_id,
                        csv_text=text,
                        source_name=source["filename"],
                        game_date_override=(game_date or None) if single else None,
                    )
                staged.append(result["item"])
        except Exception as exc:  # noqa: BLE001
            compute_progress.end()
            return _fail(str(exc))
        compute_progress.end()
        lines = [f"Staged {len(staged)} file(s) — drag onto Mid/End slots:"]
        for item in staged:
            lines.append(
                f"• {item.get('source_name') or item.get('id')} → "
                f"{item.get('season_label') or item.get('season_id')} / "
                f"{item.get('suggested_slot')} "
                f"({int(item.get('player_count') or 0):,} players)"
            )
        return (
            (staged[0].get("game_date") or game_date or "") if len(staged) == 1 else no_update,
            _status_alert("\n".join(lines), color="success"),
            None,
            False,
            no_update,
            int(rev or 0) + 1,
            next_tick,
        )

    if triggered == "cr-stage-drop":
        if not isinstance(drop_data, dict) or not drop_data.get("staging_id"):
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                next_tick,
            )
        return _assign_staging(replace=False, payload=drop_data)

    if triggered == "cr-replace-confirm":
        if not isinstance(pending, dict) or not pending.get("staging_id"):
            return _fail("Nothing pending to replace.", color="warning")
        return _assign_staging(replace=True, payload=pending)

    return (
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
    )


@callback(
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-import-status", "children", allow_duplicate=True),
    Input({"type": "cr-stage-remove", "index": ALL}, "n_clicks"),
    State("cr-career-select", "value"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_stage_remove(n_clicks_list, career_id, rev):
    if not any(n_clicks_list or []):
        return no_update, no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or not career_id:
        return no_update, no_update
    staging_id = triggered.get("index")
    if not staging_id:
        return no_update, no_update
    if careers.delete_staging_item(career_id, staging_id):
        return (
            int(rev or 0) + 1,
            _status_alert(f"Removed staged file {staging_id}.", color="secondary"),
        )
    return no_update, _status_alert("Staging item not found.", color="warning")


@callback(
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-import-status", "children", allow_duplicate=True),
    Input("cr-stage-clear", "n_clicks"),
    State("cr-career-select", "value"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_stage_clear(n_clicks, career_id, rev):
    if not n_clicks:
        return no_update, no_update
    if not career_id:
        return no_update, _status_alert("Select a career first.", color="warning")
    cleared = careers.clear_staging(career_id)
    return (
        int(rev or 0) + 1,
        _status_alert(f"Cleared {cleared} staged file(s).", color="secondary"),
    )


@callback(
    Output("cr-rename-modal", "is_open"),
    Output("cr-rename-input", "value"),
    Output("cr-rev", "data", allow_duplicate=True),
    Output("cr-career-status", "children", allow_duplicate=True),
    Input("cr-rename-open", "n_clicks"),
    Input("cr-rename-cancel", "n_clicks"),
    Input("cr-rename-save", "n_clicks"),
    State("cr-career-select", "value"),
    State("cr-rename-input", "value"),
    State("cr-rev", "data"),
    prevent_initial_call=True,
)
def cr_rename_career(
    _open_clicks,
    _cancel_clicks,
    _save_clicks,
    career_id,
    new_name,
    rev,
):
    triggered = ctx.triggered_id
    if triggered == "cr-rename-open":
        if not career_id:
            return (
                False,
                "",
                no_update,
                html.Span("Select a career first.", className="text-warning"),
            )
        meta = careers.get_career(career_id)
        return True, meta.get("name") or "", no_update, no_update
    if triggered == "cr-rename-cancel":
        return False, no_update, no_update, no_update
    if triggered == "cr-rename-save":
        try:
            meta = careers.rename_career(career_id, new_name or "")
        except Exception as exc:  # noqa: BLE001
            return True, no_update, no_update, html.Span(
                str(exc), className="text-danger"
            )
        return (
            False,
            meta["name"],
            int(rev or 0) + 1,
            html.Span(f"Renamed to “{meta['name']}”.", className="text-success"),
        )
    return no_update, no_update, no_update, no_update
