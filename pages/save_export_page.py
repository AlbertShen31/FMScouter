"""Test page: export Moneyball CSV from an FM26 save via fmsave."""
from __future__ import annotations

from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon
from components.scouting_shell import job_busy_overlay
import services.compute_progress as compute_progress
import services.export_library as lib
import services.fmsave_export as fms

register_page(__name__, path="/save-export", name="Save export")

PAGE_TIP = (
    "Read an FM26 .fm save with fmsave and write a Moneyball-shaped CSV "
    "(attributes + OVERALL season stats + contract finance). Upload the file "
    "on Uploads, or check “Also add to Uploads library” here. All players "
    "can take tens of seconds on a full career; optional filters narrow either scope."
)

_SCOPE_OPTIONS = [
    {"label": "Managed squad", "value": "squad"},
    {"label": "All players", "value": "all"},
]

_POS_OPTIONS = [
    {"label": "GK", "value": "gk"},
    {"label": "DEF", "value": "def"},
    {"label": "MID", "value": "mid"},
    {"label": "FWD", "value": "fwd"},
]

_NATION_OPTIONS = [
    {"label": label, "value": str(nid)}
    for nid, label in sorted(fms.CLUB_NATION_OPTIONS, key=lambda item: item[1].casefold())
]


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


def _default_path_hint() -> str:
    games = fms.default_fm26_games_dir()
    if games is None:
        return "Choose a .fm save file. Default games folder is unknown on this platform."
    return f"Chooser opens in: {games}"


def layout(**_kwargs):
    return dbc.Container(
        [
            dcc.Download(id="sx-download"),
            dcc.Store(id="sx-rev", data=0),
            dcc.Interval(
                id="sx-progress-poll",
                interval=1500,
                n_intervals=0,
                disabled=True,
            ),
            html.H4("Save export", className="mb-2"),
            html.P(
                "Generate a Moneyball-compatible CSV from an FM26 save for Role scores, "
                "Player stats, and Squad finance.",
                className="text-muted mb-3",
            ),
            html.Div(
                [
                    dbc.Card(
                        [
                            _card_header("1. Save & scope", PAGE_TIP, "sx-tip"),
                            dbc.CardBody(
                                [
                                    html.Label("Save file (.fm)", className="rs-field-label"),
                                    html.Div(
                                        [
                                            dmc.TextInput(
                                                id="sx-path",
                                                value="",
                                                placeholder="No save selected",
                                                readOnly=True,
                                                className="sx-path-input",
                                            ),
                                            dmc.Button(
                                                "Choose file…",
                                                id="sx-browse",
                                                n_clicks=0,
                                                variant="default",
                                            ),
                                        ],
                                        className="sx-path-row mb-1",
                                    ),
                                    html.P(
                                        _default_path_hint(),
                                        className="text-muted small mb-3",
                                    ),
                                    html.Label("Player scope", className="rs-field-label"),
                                    dmc.SegmentedControl(
                                        id="sx-scope",
                                        value="squad",
                                        data=_SCOPE_OPTIONS,
                                        fullWidth=True,
                                        className="sx-scope-control mb-3",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Optional filters",
                                                        className="sx-filters-title",
                                                    ),
                                                    html.Span(
                                                        "Apply to Managed squad or All players",
                                                        className="sx-filters-subtitle",
                                                    ),
                                                ],
                                                className="sx-filters-heading",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Div(
                                                                "Limits",
                                                                className="sx-filter-group-label",
                                                            ),
                                                            html.Div(
                                                                [
                                                                    dmc.NumberInput(
                                                                        id="sx-age-min",
                                                                        label="Age min",
                                                                        value=None,
                                                                        min=15,
                                                                        max=45,
                                                                        hideControls=False,
                                                                    ),
                                                                    dmc.NumberInput(
                                                                        id="sx-age-max",
                                                                        label="Age max",
                                                                        value=None,
                                                                        min=15,
                                                                        max=45,
                                                                        hideControls=False,
                                                                    ),
                                                                    dmc.NumberInput(
                                                                        id="sx-min-ca",
                                                                        label="Min CA",
                                                                        value=None,
                                                                        min=1,
                                                                        max=200,
                                                                        hideControls=False,
                                                                    ),
                                                                    dmc.NumberInput(
                                                                        id="sx-min-club-rep",
                                                                        label="Min club rep",
                                                                        value=None,
                                                                        min=0,
                                                                        max=20000,
                                                                        hideControls=False,
                                                                    ),
                                                                ],
                                                                className="sx-filter-fields sx-filter-fields-limits",
                                                            ),
                                                        ],
                                                        className="sx-filter-group",
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Div(
                                                                "Club & nationality",
                                                                className="sx-filter-group-label",
                                                            ),
                                                            html.Div(
                                                                [
                                                                    dmc.TextInput(
                                                                        id="sx-club-contains",
                                                                        label="Club name contains",
                                                                        placeholder="optional",
                                                                        className="sx-filter-club-contains",
                                                                    ),
                                                                    dmc.MultiSelect(
                                                                        id="sx-club-nations",
                                                                        label="Club nation (Based In)",
                                                                        data=_NATION_OPTIONS,
                                                                        value=[],
                                                                        searchable=True,
                                                                        clearable=True,
                                                                        placeholder="Any",
                                                                    ),
                                                                    dmc.MultiSelect(
                                                                        id="sx-player-nations",
                                                                        label="Nationality",
                                                                        data=_NATION_OPTIONS,
                                                                        value=[],
                                                                        searchable=True,
                                                                        clearable=True,
                                                                        placeholder="Any",
                                                                    ),
                                                                ],
                                                                className="sx-filter-fields sx-filter-fields-club",
                                                            ),
                                                        ],
                                                        className="sx-filter-group",
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Div(
                                                                "Positions",
                                                                className="sx-filter-group-label",
                                                            ),
                                                            dmc.CheckboxGroup(
                                                                children=[
                                                                    dmc.Checkbox(
                                                                        label=opt["label"],
                                                                        value=opt["value"],
                                                                    )
                                                                    for opt in _POS_OPTIONS
                                                                ],
                                                                id="sx-pos-groups",
                                                                value=[],
                                                                className="sx-pos-checks",
                                                            ),
                                                            html.P(
                                                                "Leave empty for all positions.",
                                                                className="sx-filter-hint mb-0",
                                                            ),
                                                        ],
                                                        className="sx-filter-group",
                                                    ),
                                                ],
                                                className="sx-filters-grid",
                                            ),
                                        ],
                                        id="sx-filters",
                                        className="sx-filters mb-3",
                                    ),
                                    html.Hr(className="my-3"),
                                    dmc.Checkbox(
                                        id="sx-to-uploads",
                                        label="Also add to Uploads library",
                                        checked=False,
                                        className="mb-3",
                                    ),
                                    dmc.Button(
                                        "Generate CSV",
                                        id="sx-generate",
                                        n_clicks=0,
                                        disabled=True,
                                    ),
                                    html.P(
                                        "All players can take a while — leave this tab open.",
                                        className="text-muted small mt-2 mb-0",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3",
                    ),
                    dbc.Card(
                        [
                            dbc.CardHeader("2. Status"),
                            dbc.CardBody(html.Div(id="sx-status", children="Ready.")),
                        ]
                    ),
                    job_busy_overlay(
                        "sx-busy",
                        prefix="sx",
                        initial_label="Reading save…",
                    ),
                ],
                className="rs-shortlist-busy-host",
            ),
        ],
        fluid=True,
        className="py-3",
    )


def _parse_nation_ids(values) -> list[int]:
    out: list[int] = []
    for raw in values or []:
        try:
            out.append(int(raw))
        except (TypeError, ValueError):
            continue
    return out


def _filters_payload(
    age_min,
    age_max,
    min_ca,
    min_club_rep,
    club_contains,
    club_nations,
    player_nations,
    pos_groups,
) -> dict:
    return {
        "age_min": age_min,
        "age_max": age_max,
        "min_ca": min_ca,
        "min_club_reputation": min_club_rep,
        "club_contains": club_contains or "",
        "club_nation_ids": _parse_nation_ids(club_nations),
        "nation_ids": _parse_nation_ids(player_nations),
        "position_groups": list(pos_groups or []),
    }


def _status_children(meta: dict, *, uploads_note: str = "") -> list:
    elig = meta.get("eligibility") or {}
    flags = [
        ("Role scores", elig.get("role_scores")),
        ("Player stats", elig.get("stats")),
        ("Squad finance", elig.get("squad_finance")),
    ]
    flag_spans = []
    for label, ok in flags:
        flag_spans.append(
            html.Span(
                f"{label}: {'Yes' if ok else 'No'}",
                className="up-elig yes me-3" if ok else "up-elig no me-3",
            )
        )
    blank = ", ".join(meta.get("blank_columns") or [])
    return [
        html.P(
            f"{meta.get('row_count', 0)} players · {meta.get('column_count', 0)} columns · "
            f"{meta.get('elapsed_ms', 0)} ms · scope={meta.get('scope')}"
            + (" · filters on" if meta.get("filters_active") else ""),
            className="mb-2",
        ),
        html.Div(flag_spans, className="mb-2"),
        html.P(
            f"Blank / unavailable: {blank}",
            className="text-muted small mb-2",
        ),
        html.P(uploads_note, className="mb-0") if uploads_note else html.Span(),
    ]


clientside_callback(
    """
    function(n) {
        if (!n) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var label = document.getElementById("sx-busy-label");
        if (label) { label.textContent = "Reading save…"; }
        var detail = document.getElementById("sx-busy-detail");
        if (detail) { detail.textContent = ""; }
        var track = document.getElementById("sx-busy-track");
        if (track) {
            track.className = "rs-busy-progress is-indeterminate";
        }
        return ["rs-shortlist-busy is-on t-" + String(Date.now()), false];
    }
    """,
    Output("sx-busy", "className"),
    Output("sx-progress-poll", "disabled"),
    Input("sx-generate", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output("sx-busy-label", "children"),
    Output("sx-busy-track", "className"),
    Output("sx-busy-bar", "style"),
    Output("sx-busy-detail", "children"),
    Input("sx-progress-poll", "n_intervals"),
)
def sx_poll_progress(_n):
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
    Output("sx-generate", "disabled"),
    Input("sx-path", "value"),
)
def sx_generate_enabled(path):
    return not bool((path or "").strip())


@callback(
    Output("sx-path", "value"),
    Output("sx-status", "children", allow_duplicate=True),
    Input("sx-browse", "n_clicks"),
    State("sx-path", "value"),
    prevent_initial_call=True,
)
def sx_browse(n_clicks, current_path):
    if not n_clicks:
        return no_update, no_update
    picked = fms.pick_fm_save_file(current_path or fms.default_save_path())
    if not picked:
        return no_update, no_update
    return picked, html.P(
        f"Selected: {picked}",
        className="text-muted mb-0",
    )


@callback(
    Output("sx-download", "data"),
    Output("sx-status", "children"),
    Output("sx-rev", "data"),
    Output("sx-busy", "className", allow_duplicate=True),
    Output("sx-progress-poll", "disabled", allow_duplicate=True),
    Input("sx-generate", "n_clicks"),
    State("sx-path", "value"),
    State("sx-scope", "value"),
    State("sx-age-min", "value"),
    State("sx-age-max", "value"),
    State("sx-min-ca", "value"),
    State("sx-min-club-rep", "value"),
    State("sx-club-contains", "value"),
    State("sx-club-nations", "value"),
    State("sx-player-nations", "value"),
    State("sx-pos-groups", "value"),
    State("sx-to-uploads", "checked"),
    State("sx-rev", "data"),
    prevent_initial_call=True,
)
def sx_generate(
    n_clicks,
    path,
    scope,
    age_min,
    age_max,
    min_ca,
    min_club_rep,
    club_contains,
    club_nations,
    player_nations,
    pos_groups,
    to_uploads,
    rev,
):
    if not n_clicks:
        return no_update, no_update, no_update, no_update, no_update
    next_rev = int(rev or 0) + 1
    save_path = (path or "").strip()
    if not save_path:
        return (
            no_update,
            html.P("Choose a .fm save file first.", className="text-danger mb-0"),
            next_rev,
            "rs-shortlist-busy",
            True,
        )
    scope_key = scope if scope in {"squad", "all"} else "squad"
    filters = _filters_payload(
        age_min,
        age_max,
        min_ca,
        min_club_rep,
        club_contains,
        club_nations,
        player_nations,
        pos_groups,
    )
    compute_progress.begin("Reading save…", phase="Reading save…")
    try:
        try:
            csv_text, meta = fms.export_moneyball_csv(
                save_path,
                scope=scope_key,
                filters=filters,
            )
        except ImportError as exc:
            return (
                no_update,
                html.P(
                    f"fmsave is not installed (needs Python 3.12+): {exc}. "
                    'Run: pip install "fmsave[pandas]"',
                    className="text-danger mb-0",
                ),
                next_rev,
                "rs-shortlist-busy",
                True,
            )
        except Exception as exc:  # noqa: BLE001 — surface any fmsave / IO error
            return (
                no_update,
                html.P(str(exc), className="text-danger mb-0"),
                next_rev,
                "rs-shortlist-busy",
                True,
            )

        uploads_note = ""
        if to_uploads:
            try:
                compute_progress.update(
                    phase="Adding to Uploads…",
                    message="Saving and precomputing…",
                    done=0,
                    total=0,
                )
                entry = lib.save_upload(
                    meta.get("filename") or "fmsave_export.csv", csv_text
                )
                pages = ", ".join(entry.get("pages") or []) or "none"
                uploads_note = (
                    f"Saved to Uploads as “{entry.get('display_name')}” "
                    f"(id={entry.get('id')}; pages: {pages})."
                )
            except Exception as exc:  # noqa: BLE001
                uploads_note = f"CSV generated, but Uploads save failed: {exc}"

        download = dict(
            content=csv_text,
            filename=meta.get("filename") or "fmsave_export.csv",
            type="text/csv",
        )
        return (
            download,
            _status_children(meta, uploads_note=uploads_note),
            next_rev,
            "rs-shortlist-busy",
            True,
        )
    finally:
        compute_progress.end()
