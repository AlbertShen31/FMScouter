"""Upload library: save CSVs on disk and inspect page eligibility."""
from __future__ import annotations

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
from components.scouting_shell import decode_upload, upload_error
import services.export_library as lib
import services.upload_cache as upload_cache
from scoring.stats_availability import limited_tracking_tooltip

register_page(__name__, path="/uploads", name="Uploads")

UP_PAGE_TIP = (
    "Save CSV exports on this machine. Role scores and Player stats load from this library; "
    "Squad finance can also upload manually. Rename files and add notes so the dropdowns stay "
    "readable. Files stay under data/uploads/ (not published as static assets). Moneyball / "
    "finance exports include contracts and wages — encrypt the host disk or delete CSVs you "
    "do not need. Multi-year packs combine seasons with recency weights on Uploads."
)
UP_VIEW_TIP = (
    "Download the custom views pack, put the .fmf files in Football Manager’s views folder, "
    "then Import View on Squad, Player Search, National Squad, and National Team. One export "
    "shape covers attributes, Moneyball stats, salary/fees, and player identity."
)
UP_ELIGIBILITY_TIP = (
    "Eligible means the file has Name/Player, enough player info (Club/Age/Position), plus: "
    "attributes for Role scores; stats markers for Player stats; Salary and match fees for "
    "Squad finance. Upload precomputes all role scores and stats percentiles using current "
    "Settings / role packs (including high archetype badges for fast filters), and records "
    "leagues with incomplete advanced match stats (shown striped on Player stats / Profiles). "
    "If you change those settings, click Compute to refresh. Pages then load from the cache "
    "instead of rescoring."
)
UP_COMPUTE_ALL_TIP = (
    "Recompute role scores, stats percentiles, and archetype filter fields for every eligible "
    "saved file."
)


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


def _yes_no(ok: bool) -> html.Span:
    return html.Span(
        "Yes" if ok else "No",
        className="up-elig yes" if ok else "up-elig no",
    )


def _cache_status_cell(entry: dict, *, sig_key: str | None = None) -> html.Span:
    status = upload_cache.cache_status_light(entry, sig_key=sig_key)
    tone = {
        "ready": "up-cache ready",
        "stale": "up-cache stale",
        "missing": "up-cache missing",
        "error": "up-cache error",
        "n/a": "up-cache na",
    }.get(status["status"], "up-cache")
    return html.Span(
        status["label"],
        className=tone,
        title=status.get("detail") or "",
    )


def _any_computable() -> bool:
    return any(e.get("role_scores") or e.get("stats") for e in lib.list_files())


def _limited_tooltip(entry: dict, limited: list[str]) -> str:
    raw = entry.get("limited_tracking_by_nation") or []
    nation_counts = None
    if isinstance(raw, list) and raw:
        nation_counts = [
            (str(item.get("nation") or "").strip(), int(item.get("count") or 0))
            for item in raw
            if isinstance(item, dict) and str(item.get("nation") or "").strip()
        ] or None
    return limited_tracking_tooltip(limited, nation_counts=nation_counts)


def _limited_count_cell(entry: dict, limited: list[str]) -> dmc.Tooltip:
    tip_style = {
        "backgroundColor": "var(--app-elev)",
        "color": "var(--app-text)",
        "border": "1px solid var(--app-line)",
        "fontSize": "0.8125rem",
        "lineHeight": "1.45",
        "padding": "0.55rem 0.7rem",
        "maxWidth": "24rem",
        "whiteSpace": "pre-line",
        "boxShadow": "0 10px 28px rgba(0, 0, 0, 0.38)",
    }
    return dmc.Tooltip(
        html.Span(str(len(limited)), className="up-limited-count"),
        label=_limited_tooltip(entry, limited),
        styles={
            "tooltip": tip_style,
            "arrow": {
                "backgroundColor": "var(--app-elev)",
                "border": "1px solid var(--app-line)",
            },
        },
        withArrow=True,
        position="top",
        openDelay=200,
        multiline=True,
        maw=420,
        withinPortal=True,
    )


UP_MULTI_YEAR_TIP = (
    "Combine 1–3 season CSVs already in the library. Year 3 is the most recent "
    "(weight 1.0), Year 2 mid (0.75), Year 1 oldest (0.5). Stats are pooled from "
    "raw totals with those weights; identity and attributes come from the newest "
    "year each player appears in. A pack with only Year 3 behaves like a single season. "
    "To swap a season later, Edit the pack in the saved-files table and change that year."
)


def _source_select_data(*, page: str | None = None) -> list[dict[str, str]]:
    opts = [{"value": "", "label": "— None —"}]
    for entry in lib.list_single_files(page=page):
        label = lib.display_label(entry)
        when = (entry.get("saved_at") or "")[:10]
        bits = []
        if entry.get("role_scores"):
            bits.append("Roles")
        if entry.get("stats"):
            bits.append("Stats")
        elig = f" · {', '.join(bits)}" if bits else ""
        opts.append(
            {
                "value": entry["id"],
                "label": f"{label}" + (f" · {when}" if when else "") + elig,
            }
        )
    return opts


def _kind_cell(entry: dict) -> html.Span:
    if lib.is_multi_year(entry):
        years = lib.configured_years(entry)
        slots = "+".join(f"Y{k}" for k in lib.YEAR_KEYS if k in years)
        return html.Span(
            f"Multi-year ({slots})",
            className="up-kind multi",
            title="Recency-weighted merge of season files",
        )
    return html.Span("Single", className="up-kind single")


def _files_table(entries: list[dict] | None = None) -> html.Div:
    entries = entries if entries is not None else lib.list_files()
    if not entries:
        return html.Div(
            "No saved files yet. Upload one or more CSVs above.",
            className="text-muted small",
        )
    header = html.Tr(
        [
            html.Th("Name"),
            html.Th("Type"),
            html.Th("Saved"),
            html.Th("Role scores"),
            html.Th("Player stats"),
            html.Th("Squad finance"),
            html.Th("Precompute"),
            html.Th("Limited leagues"),
            html.Th("Note"),
            html.Th(""),
        ]
    )
    rows = []
    sig_key = upload_cache.signature_key() if entries else None
    for entry in entries:
        file_id = entry["id"]
        label = lib.display_label(entry)
        original = entry.get("original_name") or ""
        user_note = (entry.get("user_note") or "").strip()
        limited = [
            str(x).strip()
            for x in (entry.get("limited_tracking_divisions") or [])
            if str(x).strip()
        ]
        elig = entry.get("eligibility_notes") or []
        if isinstance(elig, str):
            elig = [elig] if elig else []
        note_bits = []
        if user_note:
            note_bits.append(html.Div(user_note, className="up-user-note"))
        if elig:
            note_bits.append(
                html.Div("; ".join(elig), className="up-elig-note text-muted")
            )
        if not note_bits:
            note_bits = [html.Span("—", className="text-muted")]
        if limited:
            limited_cell = _limited_count_cell(entry, limited)
        else:
            limited_cell = html.Span("—", className="text-muted")
        title = original if original and original != label else entry.get("stored_name") or ""
        if lib.is_multi_year(entry):
            years = lib.configured_years(entry)
            title = " · ".join(
                f"Y{k}: {lib.display_label(lib.get_file(fid))}"
                for k, fid in years.items()
            )
        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            html.Div(label, className="up-file-name"),
                            html.Div(
                                original,
                                className="up-file-original text-muted",
                            )
                            if original and original != label and not lib.is_multi_year(entry)
                            else None,
                        ],
                        title=title,
                    ),
                    html.Td(_kind_cell(entry)),
                    html.Td((entry.get("saved_at") or "")[:19].replace("T", " ")),
                    html.Td(_yes_no(bool(entry.get("role_scores")))),
                    html.Td(_yes_no(bool(entry.get("stats")))),
                    html.Td(
                        _yes_no(bool(entry.get("squad_finance")))
                        if not lib.is_multi_year(entry)
                        else html.Span("—", className="text-muted")
                    ),
                    html.Td(_cache_status_cell(entry, sig_key=sig_key)),
                    html.Td(limited_cell),
                    html.Td(note_bits, className="up-notes"),
                    html.Td(
                        html.Div(
                            [
                                dmc.Button(
                                    "Compute",
                                    id={"type": "up-compute", "id": file_id},
                                    size="xs",
                                    variant="light",
                                    n_clicks=0,
                                    className="me-1",
                                    disabled=not (
                                        entry.get("role_scores") or entry.get("stats")
                                    ),
                                ),
                                dmc.Button(
                                    "Edit",
                                    id={"type": "up-edit", "id": file_id},
                                    size="xs",
                                    variant="light",
                                    n_clicks=0,
                                    className="me-1",
                                ),
                                dmc.Button(
                                    "Delete",
                                    id={"type": "up-delete", "id": file_id},
                                    size="xs",
                                    variant="light",
                                    color="red",
                                    n_clicks=0,
                                ),
                            ],
                            className="up-row-actions",
                        )
                    ),
                ]
            )
        )
    return html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(rows)],
            className="up-files-table",
        ),
        className="up-files-wrap",
    )


def _multi_year_panel() -> html.Div:
    src = _source_select_data()
    year_fields = []
    labels = {
        "3": ("Year 3 (most recent)", "weight 1.0"),
        "2": ("Year 2", "weight 0.75"),
        "1": ("Year 1 (oldest)", "weight 0.5"),
    }
    for key in ("3", "2", "1"):
        title, hint = labels[key]
        year_fields.append(
            html.Div(
                [
                    html.Label(
                        [title, html.Span(f" · {hint}", className="text-muted")],
                        className="rs-field-label",
                    ),
                    dmc.Select(
                        id=f"up-my-year-{key}",
                        data=src,
                        value="",
                        clearable=True,
                        searchable=True,
                        placeholder="Select a saved CSV…",
                        className="up-my-select",
                    ),
                ],
                className="up-my-year-field mb-3",
            )
        )
    return html.Div(
        [
            html.P(
                "Assign season files already saved above. At least Year 3 is enough "
                "for a single-season pack; add Year 2 / Year 1 to merge.",
                className="text-muted small mb-3",
            ),
            html.Label("Pack name", className="rs-field-label"),
            dmc.TextInput(
                id="up-my-name",
                placeholder="e.g. Liga I 2023–26",
                className="mb-3 up-my-name",
            ),
            *year_fields,
            html.Label("Note", className="rs-field-label"),
            dbc.Textarea(
                id="up-my-note",
                placeholder="Optional note",
                rows=2,
                className="up-my-note mb-3",
            ),
            html.Div(
                [
                    dmc.Button(
                        "Create multi-year pack",
                        id="up-my-create",
                        n_clicks=0,
                    ),
                ],
                className="up-my-actions",
            ),
            html.Div(id="up-my-status", className="mt-2"),
        ]
    )


def _view_panel() -> html.Div:
    views = lib.list_view_files()
    if views:
        names = html.Ul(
            [html.Li(html.Code(p.name)) for p in views],
            className="up-view-file-list mb-2",
        )
        status = html.Div(
            [
                html.P(
                    [
                        f"{len(views)} view file"
                        f"{'' if len(views) == 1 else 's'} ready to download:"
                    ],
                    className="mb-1",
                ),
                names,
            ]
        )
        disabled = False
    else:
        status = html.P(
            [
                "No view files found yet. Place FM custom views (",
                html.Code(".fmf"),
                ") in ",
                html.Code("data/views/"),
                ", then refresh this page.",
            ],
            className="mb-2 text-muted",
        )
        disabled = True

    install = html.Div(
        [
            html.P("After downloading:", className="mb-1 fw-semibold"),
            html.Ol(
                [
                    html.Li(
                        [
                            "Extract the zip and move the ",
                            html.Code(".fmf"),
                            " files into your FM views folder:",
                            html.Ul(
                                [
                                    html.Li(
                                        [
                                            "Windows: ",
                                            html.Code(
                                                "Documents\\Sports Interactive\\"
                                                "Football Manager 26\\views\\"
                                            ),
                                        ]
                                    ),
                                    html.Li(
                                        [
                                            "Mac: ",
                                            html.Code(
                                                "~/Library/Application Support/Sports Interactive/"
                                                "Football Manager 26/views/"
                                            ),
                                        ]
                                    ),
                                ],
                                className="up-view-path-list mt-1 mb-1",
                            ),
                            "Create the folder if it does not exist.",
                        ]
                    ),
                    html.Li(
                        "In-game, open Squad, Player Search, National Squad, or National Team."
                    ),
                    html.Li(
                        [
                            "Right-click any column header → ",
                            html.Strong("Import View"),
                            ", then load the matching custom view.",
                        ]
                    ),
                ],
                className="up-view-install mb-3",
            ),
        ],
        className="up-view-install-block",
    )

    return html.Div(
        [
            status,
            install,
            html.Div(
                [
                    dmc.Button(
                        "Download FM export views",
                        id="up-view-download-btn",
                        disabled=disabled,
                    ),
                ],
                className="up-view-actions",
            ),
        ]
    )


def _edit_year_fields() -> html.Div:
    """Year source pickers shown only when editing a multi-year pack."""
    labels = {
        "3": ("Year 3 (most recent)", "weight 1.0"),
        "2": ("Year 2", "weight 0.75"),
        "1": ("Year 1 (oldest)", "weight 0.5"),
    }
    fields = []
    for key in ("3", "2", "1"):
        title, hint = labels[key]
        fields.append(
            html.Div(
                [
                    html.Label(
                        [title, html.Span(f" · {hint}", className="text-muted")],
                        className="rs-field-label",
                    ),
                    dmc.Select(
                        id=f"up-edit-year-{key}",
                        data=[],
                        value="",
                        clearable=True,
                        searchable=True,
                        placeholder="Select a saved CSV…",
                        className="up-edit-year-select",
                        # Bootstrap modal sits ~1055; portal dropdown must clear it.
                        comboboxProps={"withinPortal": True, "zIndex": 10000},
                    ),
                ],
                className="up-edit-year-field mb-3",
            )
        )
    return html.Div(
        [
            html.P(
                "Replace any season file below. Saving recomputes the pack cache.",
                className="text-muted small mb-3",
            ),
            *fields,
        ],
        id="up-edit-years",
        className="up-edit-years",
        style={"display": "none"},
    )


def _edit_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(id="up-edit-title", children="Edit saved file"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    dcc.Store(id="up-edit-id"),
                    dcc.Store(id="up-edit-kind", data="single"),
                    dcc.Store(id="up-edit-last-clicks", data={}),
                    dcc.Store(id="up-edit-recompute"),
                    html.Label("Name", className="rs-field-label"),
                    dmc.TextInput(
                        id="up-edit-name",
                        placeholder="Display name",
                        className="mb-3 up-edit-name",
                    ),
                    _edit_year_fields(),
                    html.Label("Note", className="rs-field-label"),
                    dbc.Textarea(
                        id="up-edit-note",
                        placeholder="Optional note (e.g. season, scout date, league)",
                        rows=3,
                        className="up-edit-note",
                    ),
                    html.Div(id="up-edit-error", className="up-edit-error mt-2"),
                ]
            ),
            dbc.ModalFooter(
                [
                    dmc.Button(
                        "Cancel",
                        id="up-edit-cancel",
                        variant="default",
                        n_clicks=0,
                        className="me-2",
                    ),
                    dmc.Button(
                        "Save",
                        id="up-edit-save",
                        n_clicks=0,
                    ),
                ]
            ),
        ],
        id="up-edit-modal",
        className="up-edit-modal",
        is_open=False,
        centered=True,
    )


def layout(**_kwargs):
    lib.ensure_dirs()
    return dbc.Container(
        [
            dcc.Download(id="up-view-download"),
            dcc.Store(id="up-rev", data=0),
            html.Div(
                [
                    dmc.Button(
                        id={"type": "up-delete", "id": "_"},
                        n_clicks=0,
                        children="stub",
                    ),
                    dmc.Button(
                        id={"type": "up-edit", "id": "_"},
                        n_clicks=0,
                        children="stub",
                    ),
                    dmc.Button(
                        id={"type": "up-compute", "id": "_"},
                        n_clicks=0,
                        children="stub",
                    ),
                ],
                hidden=True,
            ),
            _edit_modal(),
            html.Div(
                [
                    html.H1("Uploads", className="mt-2 mb-0"),
                    *help_icon(UP_PAGE_TIP, "up-help-page"),
                ],
                className="rs-page-title-row mb-3",
            ),
            dbc.Card(
                [
                    _card_header("1. FM export views", UP_VIEW_TIP, "up-help-view"),
                    dbc.CardBody(_view_panel()),
                ],
                className="mb-3 rs-section-card",
            ),
            html.Div(
                [
                    dbc.Card(
                        [
                            dbc.CardHeader("2. Upload CSV files"),
                            dbc.CardBody(
                                [
                                    dcc.Upload(
                                        id="up-upload",
                                        children=html.Div(
                                            [
                                                "Drag and drop CSVs here, or ",
                                                html.A("browse"),
                                                " (multiple allowed)",
                                            ]
                                        ),
                                        className="rs-upload",
                                        multiple=True,
                                    ),
                                    html.Div(id="up-upload-status", className="mt-2"),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            _card_header(
                                "3. Multi-year pack",
                                UP_MULTI_YEAR_TIP,
                                "up-help-multi-year",
                            ),
                            dbc.CardBody(_multi_year_panel()),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            _card_header(
                                "4. Saved files & page eligibility",
                                UP_ELIGIBILITY_TIP,
                                "up-help-eligibility",
                            ),
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            dmc.Button(
                                                "Compute All",
                                                id="up-compute-all",
                                                size="sm",
                                                variant="light",
                                                n_clicks=0,
                                                disabled=not _any_computable(),
                                            ),
                                            *help_icon(UP_COMPUTE_ALL_TIP, "up-help-compute-all"),
                                        ],
                                        className="up-compute-all-row mb-3",
                                    ),
                                    html.Div(id="up-files-table", children=_files_table()),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    html.Div(
                        [
                            html.Div(
                                className="rs-shortlist-busy-spinner",
                                **{"aria-hidden": "true"},
                            ),
                            html.Span(
                                "Saving and precomputing…",
                                className="rs-shortlist-busy-label",
                            ),
                        ],
                        id="up-busy",
                        className="rs-shortlist-busy",
                        role="status",
                        **{"aria-live": "polite"},
                    ),
                ],
                className="rs-shortlist-busy-host up-busy-host",
            ),
        ],
        fluid=True,
        className="rs-page up-page",
    )


@callback(
    Output("up-upload-status", "children"),
    Output("up-files-table", "children"),
    Output("up-rev", "data"),
    Output("up-compute-all", "disabled"),
    Output("up-my-year-1", "data"),
    Output("up-my-year-2", "data"),
    Output("up-my-year-3", "data"),
    Input("up-upload", "contents"),
    State("up-upload", "filename"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def save_uploads(contents_list, filenames, rev):
    if not contents_list:
        return tuple([no_update] * 7)
    if isinstance(contents_list, str):
        contents_list = [contents_list]
        filenames = [filenames]
    filenames = filenames or []
    messages = []
    for i, contents in enumerate(contents_list):
        name = (filenames[i] if i < len(filenames) else None) or f"export_{i + 1}.csv"
        if not str(name).lower().endswith(".csv"):
            messages.append(upload_error(f"{name}: not a CSV file."))
            continue
        try:
            text = decode_upload(contents, strict=False)
            entry = lib.save_upload(name, text)
            pages = entry.get("pages") or []
            page_txt = (
                ", ".join(lib.PAGE_LABELS[p] for p in pages) if pages else "none"
            )
            cache = upload_cache.cache_status(entry.get("id") or "", entry)
            messages.append(
                html.Div(
                    [
                        html.Span("✓ ", className="rs-upload-ok"),
                        html.Span(lib.display_label(entry)),
                        html.Span(f" · eligible: {page_txt}", className="text-muted"),
                        html.Span(
                            f" · precompute: {cache['label']}",
                            className="text-muted",
                        ),
                    ],
                    className="up-save-row",
                )
            )
        except Exception as exc:
            messages.append(upload_error(f"{name}: {exc}"))
    if not messages:
        return tuple([no_update] * 7)
    src = _source_select_data()
    return (
        html.Div(messages),
        _files_table(),
        int(rev or 0) + 1,
        not _any_computable(),
        src,
        src,
        src,
    )


@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Output("up-my-year-1", "data", allow_duplicate=True),
    Output("up-my-year-2", "data", allow_duplicate=True),
    Output("up-my-year-3", "data", allow_duplicate=True),
    Input({"type": "up-delete", "id": ALL}, "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def delete_saved(n_clicks, rev):
    if not ctx.triggered_id or not any(n_clicks or []):
        return tuple([no_update] * 6)
    file_id = ctx.triggered_id.get("id")
    if not file_id or file_id == "_":
        return tuple([no_update] * 6)
    if not any((n or 0) > 0 for n in (n_clicks or [])):
        return tuple([no_update] * 6)
    lib.delete_file(file_id)
    src = _source_select_data()
    return (
        _files_table(),
        int(rev or 0) + 1,
        not _any_computable(),
        src,
        src,
        src,
    )


@callback(
    Output("up-my-status", "children"),
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Output("up-my-name", "value"),
    Output("up-my-note", "value"),
    Output("up-my-year-1", "value"),
    Output("up-my-year-2", "value"),
    Output("up-my-year-3", "value"),
    Input("up-my-create", "n_clicks"),
    State("up-my-name", "value"),
    State("up-my-note", "value"),
    State("up-my-year-1", "value"),
    State("up-my-year-2", "value"),
    State("up-my-year-3", "value"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def create_multi_year_pack(n_clicks, name, note, y1, y2, y3, rev):
    if not n_clicks:
        return tuple([no_update] * 9)
    years = {"1": y1 or "", "2": y2 or "", "3": y3 or ""}
    try:
        entry = lib.save_multi_year_pack(
            display_name=name or "",
            years=years,
            user_note=note or "",
        )
        cache = upload_cache.cache_status(entry.get("id") or "", entry)
        msg = html.Div(
            [
                html.Span("✓ ", className="rs-upload-ok"),
                html.Span(f"Created {lib.display_label(entry)}"),
                html.Span(f" · precompute: {cache['label']}", className="text-muted"),
            ],
            className="up-save-row",
        )
        return (
            msg,
            _files_table(),
            int(rev or 0) + 1,
            not _any_computable(),
            "",
            "",
            "",
            "",
            "",
        )
    except Exception as exc:
        return (
            upload_error(str(exc)),
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )

@callback(
    Output("up-edit-modal", "is_open"),
    Output("up-edit-id", "data"),
    Output("up-edit-kind", "data"),
    Output("up-edit-title", "children"),
    Output("up-edit-name", "value"),
    Output("up-edit-note", "value"),
    Output("up-edit-error", "children"),
    Output("up-edit-years", "style"),
    Output("up-edit-year-1", "data"),
    Output("up-edit-year-2", "data"),
    Output("up-edit-year-3", "data"),
    Output("up-edit-year-1", "value"),
    Output("up-edit-year-2", "value"),
    Output("up-edit-year-3", "value"),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-edit-last-clicks", "data"),
    Output("up-edit-recompute", "data"),
    Input({"type": "up-edit", "id": ALL}, "n_clicks"),
    Input("up-edit-cancel", "n_clicks"),
    Input("up-edit-save", "n_clicks"),
    State("up-edit-id", "data"),
    State("up-edit-kind", "data"),
    State("up-edit-name", "value"),
    State("up-edit-note", "value"),
    State("up-edit-year-1", "value"),
    State("up-edit-year-2", "value"),
    State("up-edit-year-3", "value"),
    State("up-rev", "data"),
    State("up-edit-last-clicks", "data"),
    prevent_initial_call=True,
)
def edit_modal(
    edit_clicks,
    cancel_clicks,
    save_clicks,
    edit_id,
    edit_kind,
    name,
    note,
    y1,
    y2,
    y3,
    rev,
    last_clicks,
):
    triggered = ctx.triggered_id
    if not triggered:
        return tuple([no_update] * 17)

    years_hidden = {"display": "none"}
    years_shown = {"display": "block"}
    last_clicks = dict(last_clicks or {})

    if triggered == "up-edit-cancel":
        return (
            False,
            None,
            "single",
            "Edit saved file",
            "",
            "",
            None,
            years_hidden,
            no_update,
            no_update,
            no_update,
            "",
            "",
            "",
            no_update,
            last_clicks,
            no_update,
        )

    if triggered == "up-edit-save":
        if not edit_id:
            return (
                False,
                None,
                "single",
                "Edit saved file",
                "",
                "",
                None,
                years_hidden,
                no_update,
                no_update,
                no_update,
                "",
                "",
                "",
                no_update,
                last_clicks,
                no_update,
            )
        pending_recompute = None
        try:
            if edit_kind == lib.KIND_MULTI_YEAR:
                # Metadata only here so the modal can close immediately; pack
                # cache recompute runs in recompute_after_multi_year_edit.
                lib.save_multi_year_pack(
                    display_name=name or "",
                    years={"1": y1 or "", "2": y2 or "", "3": y3 or ""},
                    user_note=note or "",
                    pack_id=edit_id,
                    recompute=False,
                )
                pending_recompute = edit_id
            else:
                lib.update_file_meta(
                    edit_id, display_name=name or "", user_note=note or ""
                )
        except (ValueError, FileNotFoundError) as exc:
            # Bump rev so the busy overlay clears after a failed multi-year save.
            return (
                True,
                edit_id,
                edit_kind or "single",
                no_update,
                name,
                note,
                html.Div(str(exc), className="rs-upload-error"),
                years_shown if edit_kind == lib.KIND_MULTI_YEAR else years_hidden,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                int(rev or 0) + 1,
                last_clicks,
                no_update,
            )
        return (
            False,
            None,
            "single",
            "Edit saved file",
            "",
            "",
            None,
            years_hidden,
            no_update,
            no_update,
            no_update,
            "",
            "",
            "",
            # Keep busy on for multi-year until deferred recompute finishes.
            no_update,
            last_clicks,
            pending_recompute if pending_recompute else no_update,
        )

    if isinstance(triggered, dict) and triggered.get("type") == "up-edit":
        file_id = triggered.get("id")
        if not file_id or file_id == "_":
            return tuple([no_update] * 17)
        # Table rebuild after save remounts Edit buttons and re-fires this Input
        # with the same n_clicks — ignore unless the user actually clicked again.
        try:
            raw_clicks = ctx.triggered[0]["value"] if ctx.triggered else None
            clicks = int(raw_clicks or 0)
        except (TypeError, ValueError):
            clicks = 0
        if clicks <= int(last_clicks.get(file_id) or 0):
            return tuple([no_update] * 17)
        entry = lib.get_file(file_id)
        if not entry:
            return tuple([no_update] * 17)
        last_clicks[file_id] = clicks
        if lib.is_multi_year(entry):
            years = lib.configured_years(entry)
            src = _source_select_data()
            return (
                True,
                file_id,
                lib.KIND_MULTI_YEAR,
                "Edit multi-year pack",
                lib.display_label(entry),
                entry.get("user_note") or "",
                None,
                years_shown,
                src,
                src,
                src,
                years.get("1") or "",
                years.get("2") or "",
                years.get("3") or "",
                no_update,
                last_clicks,
                no_update,
            )
        return (
            True,
            file_id,
            "single",
            "Edit saved file",
            lib.display_label(entry),
            entry.get("user_note") or "",
            None,
            years_hidden,
            no_update,
            no_update,
            no_update,
            "",
            "",
            "",
            no_update,
            last_clicks,
            no_update,
        )

    return tuple([no_update] * 17)

@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Input("up-edit-modal", "is_open"),
    prevent_initial_call=True,
)
def refresh_table_after_edit(is_open):
    # Refresh when the edit modal closes after a save/cancel.
    # Do not bump up-rev here: multi-year save keeps the busy overlay on until
    # recompute_after_multi_year_edit finishes and bumps rev itself.
    if is_open:
        return no_update
    return _files_table()


@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-edit-recompute", "data", allow_duplicate=True),
    Output("up-upload-status", "children", allow_duplicate=True),
    Input("up-edit-recompute", "data"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def recompute_after_multi_year_edit(pack_id, rev):
    """Finish multi-year edit: recompute cache after the modal already closed."""
    if not pack_id:
        return no_update, no_update, no_update, no_update
    entry = lib.get_file(pack_id)
    label = lib.display_label(entry) if entry else pack_id
    try:
        upload_cache.compute_file(pack_id)
        status = upload_cache.cache_status(pack_id)
        msg = html.Div(
            [
                html.Span("✓ ", className="rs-upload-ok"),
                html.Span(f"Updated {label}"),
                html.Span(f" · {status['detail']}", className="text-muted"),
            ],
            className="up-save-row",
        )
    except Exception as exc:
        msg = upload_error(f"Update failed: {exc}")
    return _files_table(), int(rev or 0) + 1, None, msg



@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-upload-status", "children", allow_duplicate=True),
    Input({"type": "up-compute", "id": ALL}, "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def compute_saved(n_clicks, rev):
    if not ctx.triggered_id or not any(n_clicks or []):
        return no_update, no_update, no_update
    file_id = ctx.triggered_id.get("id")
    if not file_id or file_id == "_":
        return no_update, no_update, no_update
    if not any((n or 0) > 0 for n in (n_clicks or [])):
        return no_update, no_update, no_update
    entry = lib.get_file(file_id)
    if not entry:
        return no_update, no_update, no_update
    try:
        upload_cache.compute_file(file_id)
        status = upload_cache.cache_status(file_id)
        msg = html.Div(
            [
                html.Span("✓ ", className="rs-upload-ok"),
                html.Span(f"Precomputed {lib.display_label(entry)}"),
                html.Span(f" · {status['detail']}", className="text-muted"),
            ],
            className="up-save-row",
        )
    except Exception as exc:
        msg = upload_error(f"Compute failed: {exc}")
    return _files_table(), int(rev or 0) + 1, msg


@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-upload-status", "children", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Input("up-compute-all", "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def compute_all_saved(n_clicks, rev):
    if not n_clicks:
        return no_update, no_update, no_update, no_update
    eligible = [
        entry
        for entry in lib.list_files()
        if entry.get("role_scores") or entry.get("stats")
    ]
    if not eligible:
        return (
            _files_table(),
            int(rev or 0) + 1,
            html.Div("No eligible files to precompute.", className="text-muted"),
            True,
        )
    ok = 0
    errors = []
    for entry in eligible:
        file_id = entry.get("id") or ""
        try:
            upload_cache.compute_file(file_id)
            ok += 1
        except Exception as exc:
            label = lib.display_label(entry)
            errors.append(f"{label}: {exc}")
    rows = [
        html.Div(
            [
                html.Span("✓ ", className="rs-upload-ok"),
                html.Span(
                    f"Precomputed {ok} of {len(eligible)} file"
                    f"{'' if len(eligible) == 1 else 's'}."
                ),
            ],
            className="up-save-row",
        )
    ]
    for err in errors:
        rows.append(upload_error(err))
    return _files_table(), int(rev or 0) + 1, html.Div(rows), not _any_computable()


@callback(
    Output("up-view-download", "data"),
    Input("up-view-download-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_view(n_clicks):
    if not n_clicks:
        return no_update
    payload = lib.views_zip_bytes()
    if not payload:
        return no_update
    return dcc.send_bytes(payload, "FMScouter-FM26-views.zip")


clientside_callback(
    """
    function(contents, computeClicks, computeAllClicks, packClicks, editSave, editKind) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return window.dash_clientside.no_update;
        }
        var prop = trig[0].prop_id || "";
        if (prop.indexOf("contents") !== -1 && !trig[0].value) {
            return window.dash_clientside.no_update;
        }
        if (prop.indexOf("up-compute-all") !== -1 && !computeAllClicks) {
            return window.dash_clientside.no_update;
        }
        if (prop.indexOf("up-my-create") !== -1 && !packClicks) {
            return window.dash_clientside.no_update;
        }
        if (prop.indexOf("up-edit-save") !== -1) {
            if (!editSave || editKind !== "multi_year") {
                return window.dash_clientside.no_update;
            }
        }
        if (prop.indexOf("up-compute") !== -1 && prop.indexOf("up-compute-all") === -1) {
            var clicks = computeClicks || [];
            var any = false;
            for (var i = 0; i < clicks.length; i++) {
                if (clicks[i]) { any = true; break; }
            }
            if (!any) {
                return window.dash_clientside.no_update;
            }
        }
        var label = document.querySelector("#up-busy .rs-shortlist-busy-label");
        if (label) {
            if (prop.indexOf("up-edit-save") !== -1) {
                label.textContent = "Updating multi-year pack…";
            } else if (prop.indexOf("up-my-create") !== -1) {
                label.textContent = "Creating multi-year pack…";
            } else if (prop.indexOf("up-compute-all") !== -1) {
                label.textContent = "Precomputing all files…";
            } else if (prop.indexOf("n_clicks") !== -1) {
                label.textContent = "Precomputing…";
            } else {
                label.textContent = "Saving and precomputing…";
            }
        }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("up-busy", "className"),
    Input("up-upload", "contents"),
    Input({"type": "up-compute", "id": ALL}, "n_clicks"),
    Input("up-compute-all", "n_clicks"),
    Input("up-my-create", "n_clicks"),
    Input("up-edit-save", "n_clicks"),
    State("up-edit-kind", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(deleteClicks) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return window.dash_clientside.no_update;
        }
        var clicks = deleteClicks || [];
        var any = false;
        for (var i = 0; i < clicks.length; i++) {
            if (clicks[i]) { any = true; break; }
        }
        if (!any) {
            return window.dash_clientside.no_update;
        }
        var label = document.querySelector("#up-busy .rs-shortlist-busy-label");
        if (label) {
            label.textContent = "Deleting…";
        }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("up-busy", "className", allow_duplicate=True),
    Input({"type": "up-delete", "id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(_rev) {
        var el = document.getElementById("up-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy";
    }
    """,
    Output("up-busy", "className", allow_duplicate=True),
    Input("up-rev", "data"),
    prevent_initial_call=True,
)
