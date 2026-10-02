"""Test page: export Moneyball CSV from an FM26 save via fmsave."""
from __future__ import annotations

from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon
import services.export_library as lib
import services.fmsave_export as fms

register_page(__name__, path="/save-export", name="Save export")

PAGE_TIP = (
    "Read an FM26 .fm save with fmsave and write a Moneyball-shaped CSV "
    "(attributes + OVERALL season stats + contract finance). Upload the file "
    "on Uploads, or check “Also add to Uploads library” here. All / Filtered "
    "scopes can take tens of seconds on a full career."
)

_SCOPE_OPTIONS = [
    {"label": "Managed squad", "value": "squad"},
    {"label": "All players", "value": "all"},
    {"label": "Filtered", "value": "filtered"},
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
        return "Paste a full path to a .fm save (OS games folder unknown on this platform)."
    return f"Default games folder: {games}"


def layout(**_kwargs):
    default_path = fms.default_save_path()
    return dbc.Container(
        [
            dcc.Download(id="sx-download"),
            dcc.Store(id="sx-rev", data=0),
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
                                    html.Label("Save path (.fm)", className="rs-field-label"),
                                    dmc.TextInput(
                                        id="sx-path",
                                        value=default_path,
                                        placeholder="/path/to/career.fm",
                                        className="mb-1",
                                    ),
                                    html.P(
                                        _default_path_hint(),
                                        className="text-muted small mb-3",
                                    ),
                                    html.Label("Player scope", className="rs-field-label"),
                                    dmc.RadioGroup(
                                        children=[
                                            dmc.Radio(
                                                label=opt["label"],
                                                value=opt["value"],
                                            )
                                            for opt in _SCOPE_OPTIONS
                                        ],
                                        id="sx-scope",
                                        value="squad",
                                        className="mb-3",
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Filters (Filtered scope only)",
                                                className="rs-field-label",
                                            ),
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        dmc.NumberInput(
                                                            id="sx-age-min",
                                                            label="Age min",
                                                            value=None,
                                                            min=15,
                                                            max=45,
                                                            hideControls=False,
                                                        ),
                                                        md=3,
                                                    ),
                                                    dbc.Col(
                                                        dmc.NumberInput(
                                                            id="sx-age-max",
                                                            label="Age max",
                                                            value=None,
                                                            min=15,
                                                            max=45,
                                                            hideControls=False,
                                                        ),
                                                        md=3,
                                                    ),
                                                    dbc.Col(
                                                        dmc.NumberInput(
                                                            id="sx-min-ca",
                                                            label="Min CA",
                                                            value=None,
                                                            min=1,
                                                            max=200,
                                                            hideControls=False,
                                                        ),
                                                        md=3,
                                                    ),
                                                    dbc.Col(
                                                        dmc.NumberInput(
                                                            id="sx-min-club-rep",
                                                            label="Min club rep",
                                                            value=None,
                                                            min=0,
                                                            max=20000,
                                                            hideControls=False,
                                                        ),
                                                        md=3,
                                                    ),
                                                ],
                                                className="g-2 mb-2",
                                            ),
                                            dmc.TextInput(
                                                id="sx-club-contains",
                                                label="Club name contains",
                                                placeholder="optional",
                                                className="mb-2",
                                            ),
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        dmc.MultiSelect(
                                                            id="sx-club-nations",
                                                            label="Club nation (Based In)",
                                                            data=_NATION_OPTIONS,
                                                            value=[],
                                                            searchable=True,
                                                            clearable=True,
                                                            placeholder="Any",
                                                        ),
                                                        md=6,
                                                    ),
                                                    dbc.Col(
                                                        dmc.MultiSelect(
                                                            id="sx-player-nations",
                                                            label="Nationality",
                                                            data=_NATION_OPTIONS,
                                                            value=[],
                                                            searchable=True,
                                                            clearable=True,
                                                            placeholder="Any",
                                                        ),
                                                        md=6,
                                                    ),
                                                ],
                                                className="g-2 mb-2",
                                            ),
                                            html.Label(
                                                "Position groups",
                                                className="rs-field-label",
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
                                            ),
                                        ],
                                        id="sx-filters",
                                        className="sx-filters",
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
                                    ),
                                    html.P(
                                        "All / Filtered can take a while — leave this tab open.",
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
                    html.Div(
                        [
                            html.Div(className="rs-shortlist-busy-spinner"),
                            html.Div(
                                "Reading save…",
                                className="rs-shortlist-busy-label",
                            ),
                        ],
                        id="sx-busy",
                        className="rs-shortlist-busy",
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
            f"{meta.get('elapsed_ms', 0)} ms · scope={meta.get('scope')}",
            className="mb-2",
        ),
        html.Div(flag_spans, className="mb-2"),
        html.P(
            f"Blank / unavailable: {blank}",
            className="text-muted small mb-2",
        ),
        html.P(uploads_note, className="mb-0") if uploads_note else html.Span(),
    ]


@callback(
    Output("sx-filters", "style"),
    Input("sx-scope", "value"),
)
def sx_toggle_filters(scope):
    if scope == "filtered":
        return {"display": "block"}
    return {"display": "none"}


clientside_callback(
    """
    function(n) {
        if (!n) { return window.dash_clientside.no_update; }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("sx-busy", "className"),
    Input("sx-generate", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output("sx-download", "data"),
    Output("sx-status", "children"),
    Output("sx-rev", "data"),
    Output("sx-busy", "className", allow_duplicate=True),
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
        return no_update, no_update, no_update, no_update
    next_rev = int(rev or 0) + 1
    save_path = (path or "").strip()
    if not save_path:
        return (
            no_update,
            html.P("Enter a path to a .fm save file.", className="text-danger mb-0"),
            next_rev,
            "rs-shortlist-busy",
        )
    scope_key = scope if scope in {"squad", "all", "filtered"} else "squad"
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
    try:
        csv_text, meta = fms.export_moneyball_csv(
            save_path,
            scope=scope_key,  # type: ignore[arg-type]
            filters=filters if scope_key == "filtered" else None,
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
        )
    except Exception as exc:  # noqa: BLE001 — surface any fmsave / IO error
        return (
            no_update,
            html.P(str(exc), className="text-danger mb-0"),
            next_rev,
            "rs-shortlist-busy",
        )

    uploads_note = ""
    if to_uploads:
        try:
            entry = lib.save_upload(meta.get("filename") or "fmsave_export.csv", csv_text)
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
    )
