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

register_page(__name__, path="/uploads", name="Uploads")

UP_PAGE_TIP = (
    "Save CSV exports on this machine. Role scores and Player stats load from this library; "
    "Squad finance can also upload manually. Rename files and add notes so the dropdowns stay "
    "readable. Files stay under data/uploads/ (not published as static assets). Moneyball / "
    "finance exports include contracts and wages — encrypt the host disk or delete CSVs you "
    "do not need."
)
UP_VIEW_TIP = (
    "Use one custom view that includes attributes, Moneyball stats, salary/fees, and player "
    "identity columns so a single export works on every page."
)
UP_ELIGIBILITY_TIP = (
    "Eligible means the file has Name/Player, enough player info (Club/Age/Position), plus: "
    "attributes for Role scores; stats markers for Player stats; Salary and match fees for "
    "Squad finance. Upload precomputes all role scores and stats percentiles using current "
    "Settings / role packs, and records leagues with incomplete advanced match stats (shown "
    "striped on Player stats / Profiles). If you change those settings, click Compute to "
    "refresh. Pages then load from the cache instead of rescoring."
)
UP_COMPUTE_ALL_TIP = (
    "Recompute role scores and stats percentiles for every eligible saved file."
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


def _cache_status_cell(entry: dict) -> html.Span:
    status = upload_cache.cache_status(entry.get("id") or "", entry)
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
            limited_cell = html.Span(
                f"{len(limited)}",
                className="up-limited-count",
                title="Incomplete advanced match stats: " + ", ".join(limited),
            )
        else:
            limited_cell = html.Span("—", className="text-muted")
        title = original if original and original != label else entry.get("stored_name") or ""
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
                            if original and original != label
                            else None,
                        ],
                        title=title,
                    ),
                    html.Td((entry.get("saved_at") or "")[:19].replace("T", " ")),
                    html.Td(_yes_no(bool(entry.get("role_scores")))),
                    html.Td(_yes_no(bool(entry.get("stats")))),
                    html.Td(_yes_no(bool(entry.get("squad_finance")))),
                    html.Td(_cache_status_cell(entry)),
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


def _view_panel() -> html.Div:
    view = lib.primary_view_file()
    if view:
        status = html.P(
            [
                "View file ready: ",
                html.Strong(view.name),
                ". Download it and import into Football Manager’s view editor.",
            ],
            className="mb-2",
        )
        disabled = False
    else:
        status = html.P(
            [
                "No view file found yet. Place your FM custom view in ",
                html.Code("data/views/"),
                " (any file except README), then refresh this page.",
            ],
            className="mb-2 text-muted",
        )
        disabled = True
    return html.Div(
        [
            status,
            html.Div(
                [
                    dmc.Button(
                        "Download FM export view",
                        id="up-view-download-btn",
                        disabled=disabled,
                    ),
                ],
                className="up-view-actions",
            ),
        ]
    )


def _edit_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Edit saved file"), close_button=True),
            dbc.ModalBody(
                [
                    dcc.Store(id="up-edit-id"),
                    html.Label("Name", className="rs-field-label"),
                    dmc.TextInput(
                        id="up-edit-name",
                        placeholder="Display name",
                        className="mb-3 up-edit-name",
                    ),
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
                    _card_header("1. FM export view", UP_VIEW_TIP, "up-help-view"),
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
                                "3. Saved files & page eligibility",
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
    Input("up-upload", "contents"),
    State("up-upload", "filename"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def save_uploads(contents_list, filenames, rev):
    if not contents_list:
        return no_update, no_update, no_update, no_update
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
        return no_update, no_update, no_update, no_update
    return (
        html.Div(messages),
        _files_table(),
        int(rev or 0) + 1,
        not _any_computable(),
    )


@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Input({"type": "up-delete", "id": ALL}, "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def delete_saved(n_clicks, rev):
    if not ctx.triggered_id or not any(n_clicks or []):
        return no_update, no_update, no_update
    file_id = ctx.triggered_id.get("id")
    if not file_id or file_id == "_":
        return no_update, no_update, no_update
    if not any((n or 0) > 0 for n in (n_clicks or [])):
        return no_update, no_update, no_update
    lib.delete_file(file_id)
    return _files_table(), int(rev or 0) + 1, not _any_computable()


@callback(
    Output("up-edit-modal", "is_open"),
    Output("up-edit-id", "data"),
    Output("up-edit-name", "value"),
    Output("up-edit-note", "value"),
    Output("up-edit-error", "children"),
    Input({"type": "up-edit", "id": ALL}, "n_clicks"),
    Input("up-edit-cancel", "n_clicks"),
    Input("up-edit-save", "n_clicks"),
    State("up-edit-id", "data"),
    State("up-edit-name", "value"),
    State("up-edit-note", "value"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def edit_modal(
    edit_clicks,
    cancel_clicks,
    save_clicks,
    edit_id,
    name,
    note,
    rev,
):
    triggered = ctx.triggered_id
    if not triggered:
        return no_update, no_update, no_update, no_update, no_update

    if triggered == "up-edit-cancel":
        return False, None, "", "", None

    if triggered == "up-edit-save":
        if not edit_id:
            return False, None, "", "", None
        try:
            lib.update_file_meta(edit_id, display_name=name or "", user_note=note or "")
        except ValueError as exc:
            return True, edit_id, name, note, html.Div(str(exc), className="rs-upload-error")
        return False, None, "", "", None

    if isinstance(triggered, dict) and triggered.get("type") == "up-edit":
        file_id = triggered.get("id")
        if not file_id or file_id == "_":
            return no_update, no_update, no_update, no_update, no_update
        if not any((n or 0) > 0 for n in (edit_clicks or [])):
            return no_update, no_update, no_update, no_update, no_update
        entry = lib.get_file(file_id)
        if not entry:
            return no_update, no_update, no_update, no_update, no_update
        return (
            True,
            file_id,
            lib.display_label(entry),
            entry.get("user_note") or "",
            None,
        )

    return no_update, no_update, no_update, no_update, no_update


@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Input("up-edit-modal", "is_open"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def refresh_table_after_edit(is_open, rev):
    # Refresh when the edit modal closes after a save/cancel.
    if is_open:
        return no_update, no_update
    return _files_table(), int(rev or 0) + 1



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
    path = lib.primary_view_file()
    if not path:
        return no_update
    return dcc.send_file(str(path))


clientside_callback(
    """
    function(contents, computeClicks, computeAllClicks) {
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
            if (prop.indexOf("up-compute-all") !== -1) {
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
