"""Export Moneyball CSV from an FM26 / FM27 save via fmsave."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

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
    "Read FM26 or FM27 .fm save(s) with fmsave (0.9.3+) and write Moneyball-shaped CSV(s) "
    "(attributes + OVERALL season stats + contract finance). Injury columns stay blank. "
    "FM27 field meanings stay unconfirmed in fmsave; Pressures columns are empty on FM27. "
    "Choosing save(s) preloads the first for live filter counts; Generate exports every "
    "selected save with the same scope/filters. CSVs always go to Uploads (precompute "
    "continues in the background); optionally download a CSV (or a zip for multiple)."
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


def _resolve_save_paths(paths, path_label: str | None = None) -> list[str]:
    cleaned = [str(p).strip() for p in _as_list(paths) if str(p).strip()]
    if cleaned:
        return cleaned
    single = str(path_label or "").strip()
    if not single or " saves: " in single:
        return []
    if Path(single).suffix.lower() == ".fm" or Path(single).is_file():
        return [single]
    return []

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
    for nid, label in fms.nation_filter_options()
]
_HEIGHT_OPTIONS = fms.height_select_options()
_HEIGHT_MIN_DEFAULT = str(fms.HEIGHT_IN_MIN)
_HEIGHT_MAX_DEFAULT = str(fms.HEIGHT_IN_MAX)


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
    existing = fms.default_fm_games_dirs()
    if existing:
        labels = " · ".join(str(path) for path in existing)
        return f"Chooser prefers existing games folders: {labels}"
    games = fms.default_fm_games_dir()
    if games is None:
        return (
            "Choose a .fm save file (FM26 or FM27). "
            "Default games folder is unknown on this platform."
        )
    return f"Chooser opens in: {games} (FM26 / FM27)"


def layout(**_kwargs):
    return dbc.Container(
        [
            dcc.Download(id="sx-download"),
            dcc.Store(id="sx-rev", data=0),
            dcc.Store(id="sx-pick-rev", data=0),
            dcc.Store(id="sx-paths", data=[]),
            dcc.Store(id="sx-preload", data=None),
            dcc.Interval(
                id="sx-progress-poll",
                interval=800,
                n_intervals=0,
                disabled=True,
            ),
            html.H4("Save export", className="mb-2"),
            html.P(
                "Generate Moneyball-compatible CSV(s) from FM26 or FM27 save(s) for Role "
                "scores, Player stats, and Squad finance. Requires fmsave 0.9.3+.",
                className="text-muted mb-3",
            ),
            html.Div(
                [
                    dbc.Card(
                        [
                            _card_header("1. Save & scope", PAGE_TIP, "sx-tip"),
                            dbc.CardBody(
                                [
                                    html.Label(
                                        "Save file(s) (.fm)",
                                        className="rs-field-label",
                                    ),
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
                                                "Choose files…",
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
                                                        "Apply to every selected save "
                                                        "(Managed squad or All players)",
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
                                                                        debounce=300,
                                                                    ),
                                                                    dmc.NumberInput(
                                                                        id="sx-age-max",
                                                                        label="Age max",
                                                                        value=None,
                                                                        min=15,
                                                                        max=45,
                                                                        hideControls=False,
                                                                        debounce=300,
                                                                    ),
                                                                    dmc.Select(
                                                                        id="sx-height-min",
                                                                        label="Height min",
                                                                        data=_HEIGHT_OPTIONS,
                                                                        value=_HEIGHT_MIN_DEFAULT,
                                                                        searchable=True,
                                                                        allowDeselect=False,
                                                                        debounce=300,
                                                                    ),
                                                                    dmc.Select(
                                                                        id="sx-height-max",
                                                                        label="Height max",
                                                                        data=_HEIGHT_OPTIONS,
                                                                        value=_HEIGHT_MAX_DEFAULT,
                                                                        searchable=True,
                                                                        allowDeselect=False,
                                                                        debounce=300,
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
                                                                        debounce=300,
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
                                                                        debounce=300,
                                                                    ),
                                                                    dmc.MultiSelect(
                                                                        id="sx-player-nations",
                                                                        label="Nationality",
                                                                        data=_NATION_OPTIONS,
                                                                        value=[],
                                                                        searchable=True,
                                                                        clearable=True,
                                                                        placeholder="Any",
                                                                        debounce=300,
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
                                    html.Div(
                                        id="sx-match-count",
                                        className="sx-match-count mb-3",
                                        children="Select save(s) to preload players and preview export size.",
                                    ),
                                    html.Hr(className="my-3"),
                                    dmc.Checkbox(
                                        id="sx-download-csv",
                                        label="Also download CSV / zip",
                                        checked=False,
                                        className="mb-3",
                                    ),
                                    dmc.Button(
                                        "Generate export",
                                        id="sx-generate",
                                        n_clicks=0,
                                        disabled=True,
                                    ),
                                    html.P(
                                        "Always adds each CSV to Uploads (scoring continues "
                                        "in the background). Preload uses the first selected "
                                        "save for filter counts; Generate exports every "
                                        "selected save with the same filters.",
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
        className="py-3 sx-page",
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
    height_min,
    height_max,
    club_contains,
    club_nations,
    player_nations,
    pos_groups,
) -> dict:
    height_min_in, height_max_in = fms.normalize_height_bounds(height_min, height_max)
    return {
        "age_min": age_min,
        "age_max": age_max,
        "height_min_in": height_min_in,
        "height_max_in": height_max_in,
        "club_contains": club_contains or "",
        "club_nation_ids": _parse_nation_ids(club_nations),
        "nation_ids": _parse_nation_ids(player_nations),
        "position_groups": list(pos_groups or []),
    }


def _preload_status_children(meta: dict) -> list:
    club = meta.get("managed_club_name")
    club_bit = f" · managed club: {club}" if club else " · no managed club"
    game_bits = []
    if meta.get("game"):
        game_bits.append(str(meta["game"]))
    if meta.get("build"):
        game_bits.append(f"build {meta['build']}")
    if meta.get("game_date"):
        game_bits.append(str(meta["game_date"]))
    game_line = " · ".join(game_bits)
    summary = (
        f"Preloaded {meta.get('save_total', 0):,} players "
        f"({meta.get('squad_total', 0):,} in managed squad) "
        f"in {meta.get('elapsed_ms', 0)} ms{club_bit}."
    )
    children = [html.P(summary, className="mb-2")]
    if game_line:
        children.append(html.P(game_line, className="text-muted small mb-0"))
    return children


def _match_count_children(
    result: dict | None,
    *,
    preload: dict | None = None,
    path_count: int = 1,
):
    if not preload or not preload.get("ok"):
        if preload and preload.get("error"):
            return html.Span(
                str(preload.get("error")),
                className="sx-match-count-error",
            )
        return "Select save(s) to preload players and preview export size."
    if not result:
        return "Adjust scope or filters to preview export size."
    if not result.get("ok"):
        return html.Span(
            str(result.get("error") or "Could not count players."),
            className="sx-match-count-error",
        )
    matched = int(result.get("matched") or 0)
    scope_total = int(result.get("scope_total") or 0)
    save_total = int(result.get("save_total") or 0)
    scope_label = (
        "Managed squad" if result.get("scope") == "squad" else "All players"
    )
    if result.get("filters_active"):
        text = (
            f"Export will process {matched:,} of {scope_total:,} players "
            f"({scope_label}; {save_total:,} in save)."
        )
    else:
        text = (
            f"Export will process {matched:,} players "
            f"({scope_label}; {save_total:,} in save)."
        )
    if path_count > 1:
        first_name = Path(str(preload.get("save_path") or "")).name or "first save"
        text = (
            f"{text} Preview is for {first_name}; Generate exports all "
            f"{path_count} saves with the same filters."
        )
    return html.Span(text, className="sx-match-count-value")


def _batch_status_children(results: list[dict], *, uploads_notes: list[str]) -> list:
    lines = [f"Exported {len(results)} save(s):"]
    children: list = [html.P(lines[0], className="mb-2")]
    for meta, note in zip(results, uploads_notes):
        name = meta.get("source_name") or meta.get("filename") or "export.csv"
        summary = (
            f"{name}: {meta.get('row_count', 0):,} players · "
            f"{meta.get('elapsed_ms', 0)} ms · scope={meta.get('scope')}"
            + (" · filters on" if meta.get("filters_active") else "")
        )
        children.append(html.P(summary, className="mb-1"))
        if note:
            children.append(html.P(note, className="text-muted small mb-2"))
    return children


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
    game_bits = []
    if meta.get("game"):
        game_bits.append(str(meta["game"]))
    if meta.get("build"):
        game_bits.append(str(meta["build"]))
    if meta.get("known_build") is False:
        game_bits.append("unverified build")
    game_line = " · ".join(game_bits)
    summary = (
        f"{meta.get('row_count', 0)} players · {meta.get('column_count', 0)} columns · "
        f"{meta.get('elapsed_ms', 0)} ms · scope={meta.get('scope')}"
        + (" · filters on" if meta.get("filters_active") else "")
        + (" · reused preload" if meta.get("players_from_preload") else "")
    )
    if game_line:
        summary = f"{summary} · {game_line}"
    return [
        html.P(summary, className="mb-2"),
        html.Div(flag_spans, className="mb-2"),
        html.P(
            f"Blank / unavailable: {blank}",
            className="text-muted small mb-2",
        ),
        html.P(uploads_note, className="mb-0") if uploads_note else html.Span(),
    ]


clientside_callback(
    """
    function(n, paths, pickRev) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var prop = String(trig[0].prop_id || "");
        var fromGenerate = prop.indexOf("sx-generate") !== -1;
        var fromPick = prop.indexOf("sx-pick-rev") !== -1;
        var pathCount = Array.isArray(paths) ? paths.length : 0;
        if (fromGenerate && !n) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        if (!fromGenerate && !fromPick) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        if (fromPick && pathCount < 1) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var label = document.getElementById("sx-busy-label");
        if (label) {
            if (fromGenerate) {
                label.textContent = pathCount > 1
                    ? ("Exporting " + pathCount + " saves…")
                    : "Reading save…";
            } else {
                label.textContent = "Preloading save…";
            }
        }
        var detail = document.getElementById("sx-busy-detail");
        if (detail) {
            detail.textContent = (fromGenerate && pathCount > 1)
                ? ("0/" + pathCount + " files done")
                : "";
        }
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
    Input("sx-paths", "data"),
    Input("sx-pick-rev", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(_preload, _rev) {
        var el = document.getElementById("sx-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        return ["rs-shortlist-busy", true];
    }
    """,
    Output("sx-busy", "className", allow_duplicate=True),
    Output("sx-progress-poll", "disabled", allow_duplicate=True),
    Input("sx-preload", "data"),
    Input("sx-rev", "data"),
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
    Input("sx-preload", "data"),
    Input("sx-paths", "data"),
)
def sx_generate_enabled(preload, paths):
    resolved_paths = _resolve_save_paths(paths)
    if not resolved_paths:
        return True
    if not isinstance(preload, dict) or not preload.get("ok"):
        return True
    try:
        first = str(Path(resolved_paths[0]).expanduser().resolve())
    except OSError:
        return True
    return str(preload.get("save_path") or "") != first


@callback(
    Output("sx-paths", "data"),
    Output("sx-path", "value"),
    Output("sx-pick-rev", "data"),
    Input("sx-browse", "n_clicks"),
    State("sx-paths", "data"),
    State("sx-path", "value"),
    State("sx-pick-rev", "data"),
    prevent_initial_call=True,
)
def sx_browse(n_clicks, current_paths, current_path, pick_rev):
    if not n_clicks:
        return no_update, no_update, no_update
    seed = ""
    existing = _resolve_save_paths(current_paths, current_path)
    if existing:
        seed = existing[0]
    elif current_path:
        seed = str(current_path).strip()
    picked = fms.pick_fm_save_files(seed or fms.default_save_path(), multiple=True)
    if not picked:
        return no_update, no_update, no_update
    # Always bump pick-rev so re-choosing the same set retriggers preload.
    return picked, _fm_paths_label(picked), int(pick_rev or 0) + 1


@callback(
    Output("sx-preload", "data"),
    Output("sx-status", "children"),
    Input("sx-paths", "data"),
    Input("sx-pick-rev", "data"),
    prevent_initial_call=True,
)
def sx_preload_save(paths, _pick_rev):
    resolved = _resolve_save_paths(paths)
    if not resolved:
        return None, "Ready."

    # Filter preview / generate reuse need the first save in the single-slot
    # preload cache. Multi-file progress belongs on Generate (exports every path).
    save_path = resolved[0]
    name = Path(save_path).name
    total_files = len(resolved)
    compute_progress.begin(
        "Preloading save…",
        phase="Opening save…",
        context=name,
        file_done=0,
        file_total=1,
    )
    try:
        try:
            meta = fms.preload_save_players(save_path)
        except ImportError as exc:
            err = {
                "ok": False,
                "error": (
                    f"fmsave is not installed (needs Python 3.12+): {exc}. "
                    'Run: pip install "fmsave[pandas]"'
                ),
                "save_path": save_path,
            }
            return err, html.P(err["error"], className="text-danger mb-0")
        except Exception as exc:  # noqa: BLE001
            err = {"ok": False, "error": str(exc), "save_path": save_path}
            return err, html.P(str(exc), className="text-danger mb-0")
        status = _preload_status_children(meta)
        if total_files > 1:
            status = list(status) + [
                html.P(
                    f"{total_files} saves selected — match count preview uses "
                    f"{name}; Generate exports all with the same filters.",
                    className="text-muted small mb-0 mt-2",
                )
            ]
        return meta, status
    finally:
        compute_progress.end()


@callback(
    Output("sx-match-count", "children"),
    Input("sx-preload", "data"),
    Input("sx-paths", "data"),
    Input("sx-scope", "value"),
    Input("sx-age-min", "value"),
    Input("sx-age-max", "value"),
    Input("sx-height-min", "value"),
    Input("sx-height-max", "value"),
    Input("sx-club-contains", "value"),
    Input("sx-club-nations", "value"),
    Input("sx-player-nations", "value"),
    Input("sx-pos-groups", "value"),
)
def sx_match_count(
    preload,
    paths,
    scope,
    age_min,
    age_max,
    height_min,
    height_max,
    club_contains,
    club_nations,
    player_nations,
    pos_groups,
):
    path_count = len(_resolve_save_paths(paths))
    if not isinstance(preload, dict) or not preload.get("ok"):
        return _match_count_children(
            None,
            preload=preload if isinstance(preload, dict) else None,
            path_count=max(1, path_count),
        )
    save_path = preload.get("save_path") or ""
    filters = _filters_payload(
        age_min,
        age_max,
        height_min,
        height_max,
        club_contains,
        club_nations,
        player_nations,
        pos_groups,
    )
    try:
        result = fms.count_matching_players(
            save_path,
            scope=scope if scope in {"squad", "all"} else "squad",
            filters=filters,
        )
    except LookupError:
        return "Save preload expired — choose the save again."
    except Exception as exc:  # noqa: BLE001
        return html.Span(str(exc), className="sx-match-count-error")
    return _match_count_children(
        result,
        preload=preload,
        path_count=max(1, path_count),
    )


@callback(
    Output("sx-download", "data"),
    Output("sx-status", "children", allow_duplicate=True),
    Output("sx-rev", "data"),
    Input("sx-generate", "n_clicks"),
    State("sx-paths", "data"),
    State("sx-path", "value"),
    State("sx-scope", "value"),
    State("sx-age-min", "value"),
    State("sx-age-max", "value"),
    State("sx-height-min", "value"),
    State("sx-height-max", "value"),
    State("sx-club-contains", "value"),
    State("sx-club-nations", "value"),
    State("sx-player-nations", "value"),
    State("sx-pos-groups", "value"),
    State("sx-download-csv", "checked"),
    State("sx-rev", "data"),
    prevent_initial_call=True,
)
def sx_generate(
    n_clicks,
    paths,
    path_label,
    scope,
    age_min,
    age_max,
    height_min,
    height_max,
    club_contains,
    club_nations,
    player_nations,
    pos_groups,
    download_csv,
    rev,
):
    if not n_clicks:
        return no_update, no_update, no_update
    next_rev = int(rev or 0) + 1
    resolved = _resolve_save_paths(paths, path_label)
    if not resolved:
        return (
            no_update,
            html.P("Choose .fm save file(s) first.", className="text-danger mb-0"),
            next_rev,
        )
    scope_key = scope if scope in {"squad", "all"} else "squad"
    filters = _filters_payload(
        age_min,
        age_max,
        height_min,
        height_max,
        club_contains,
        club_nations,
        player_nations,
        pos_groups,
    )
    total_files = len(resolved)
    compute_progress.begin(
        "Exporting saves…" if total_files > 1 else "Reading save…",
        phase="Preparing…",
        file_done=0,
        file_total=total_files,
    )
    try:
        results: list[dict] = []
        uploads_notes: list[str] = []
        csv_by_name: list[tuple[str, str]] = []
        for idx, save_path in enumerate(resolved, start=1):
            name = Path(save_path).name
            compute_progress.update(
                phase="Opening save…",
                context=name,
                message=name,
                file_done=max(0, idx - 1),
                file_total=total_files,
                done=0,
                total=0,
            )
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
                )
            except Exception as exc:  # noqa: BLE001 — surface any fmsave / IO error
                return (
                    no_update,
                    html.P(
                        f"{name}: {exc}",
                        className="text-danger mb-0",
                    ),
                    next_rev,
                )

            meta = {
                **meta,
                "source_name": name,
            }
            filename = meta.get("filename") or f"fmsave_export_{idx}.csv"
            # Keep zip member names unique when scopes collide.
            if any(existing == filename for existing, _ in csv_by_name):
                stem = Path(filename).stem
                filename = f"{stem}_{idx}.csv"
            csv_by_name.append((filename, csv_text))

            uploads_note = ""
            try:
                compute_progress.update(
                    phase="Adding to Uploads…",
                    context=name,
                    message=filename,
                    file_done=max(0, idx - 1),
                    file_total=total_files,
                    done=0,
                    total=0,
                )
                entry = lib.save_upload(
                    filename,
                    csv_text,
                    export_source=lib.EXPORT_SOURCE_FMSAVE,
                    eligibility=meta.get("eligibility"),
                    player_count=meta.get("row_count"),
                    precompute="async",
                )
                pages = ", ".join(entry.get("pages") or []) or "none"
                uploads_note = (
                    f"Saved to Uploads as “{entry.get('display_name')}” "
                    f"(id={entry.get('id')}; pages: {pages}). "
                    "Precompute running in the background."
                )
            except Exception as exc:  # noqa: BLE001
                uploads_note = f"Export built, but Uploads save failed: {exc}"

            results.append(meta)
            uploads_notes.append(uploads_note)
            compute_progress.update(
                phase=f"Exported ({int(meta.get('row_count') or 0):,} players)",
                context=name,
                message=name,
                file_done=idx,
                file_total=total_files,
                done=0,
                total=0,
            )

        download = no_update
        if download_csv and csv_by_name:
            if len(csv_by_name) == 1:
                filename, csv_text = csv_by_name[0]
                download = dict(
                    content=csv_text,
                    filename=filename,
                    type="text/csv",
                )
            else:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for filename, csv_text in csv_by_name:
                        zf.writestr(filename, csv_text)
                download = dcc.send_bytes(buf.getvalue(), "fmsave_exports.zip")

        if len(results) == 1:
            status = _status_children(results[0], uploads_note=uploads_notes[0])
        else:
            status = _batch_status_children(results, uploads_notes=uploads_notes)
        return download, status, next_rev
    finally:
        compute_progress.end()
