"""Upload library: save CSVs on disk and inspect page eligibility."""
from __future__ import annotations

from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.scouting_shell import decode_upload, upload_error
import services.export_library as lib

register_page(__name__, path="/uploads", name="Uploads")


def _yes_no(ok: bool) -> html.Span:
    return html.Span(
        "Yes" if ok else "No",
        className="up-elig yes" if ok else "up-elig no",
    )


def _files_table(entries: list[dict] | None = None) -> html.Div:
    entries = entries if entries is not None else lib.list_files()
    if not entries:
        return html.Div(
            "No saved files yet. Upload one or more CSVs above.",
            className="text-muted small",
        )
    header = html.Tr(
        [
            html.Th("File"),
            html.Th("Saved"),
            html.Th("Role scores"),
            html.Th("Player stats"),
            html.Th("Squad finance"),
            html.Th("Notes"),
            html.Th(""),
        ]
    )
    rows = []
    for entry in entries:
        notes = "; ".join(entry.get("notes") or []) or "—"
        rows.append(
            html.Tr(
                [
                    html.Td(
                        entry.get("original_name") or entry.get("id"),
                        title=entry.get("stored_name") or "",
                    ),
                    html.Td((entry.get("saved_at") or "")[:19].replace("T", " ")),
                    html.Td(_yes_no(bool(entry.get("role_scores")))),
                    html.Td(_yes_no(bool(entry.get("stats")))),
                    html.Td(_yes_no(bool(entry.get("squad_finance")))),
                    html.Td(notes, className="up-notes"),
                    html.Td(
                        dmc.Button(
                            "Delete",
                            id={"type": "up-delete", "id": entry["id"]},
                            size="xs",
                            variant="light",
                            color="red",
                            n_clicks=0,
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
                        className="me-2",
                    ),
                    html.Span(
                        "Placeholder until you add the view file under data/views/.",
                        className="text-muted small",
                    ),
                ],
                className="up-view-actions",
            ),
        ]
    )


def layout(**_kwargs):
    lib.ensure_dirs()
    return dbc.Container(
        [
            dcc.Download(id="up-view-download"),
            dcc.Store(id="up-rev", data=0),
            html.Div(
                dmc.Button(
                    id={"type": "up-delete", "id": "_"},
                    n_clicks=0,
                    children="stub",
                ),
                hidden=True,
            ),
            html.H1("Uploads", className="mt-2 mb-3"),
            html.P(
                "Save CSV exports on this machine. Role scores, Player stats, and "
                "Squad finance can pick from this library or upload a file manually. "
                "The last choice (library or manual) is what each page keeps in cache.",
                className="text-muted mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader("1. FM export view"),
                    dbc.CardBody(
                        [
                            html.P(
                                "Use one custom view that includes attributes, "
                                "Moneyball stats, salary/fees, and player identity "
                                "columns so a single export works on every page.",
                                className="mb-2",
                            ),
                            _view_panel(),
                        ]
                    ),
                ],
                className="mb-3 rs-section-card",
            ),
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
                    dbc.CardHeader("3. Saved files & page eligibility"),
                    dbc.CardBody(
                        [
                            html.P(
                                "Eligible means the file has Name/Player, enough "
                                "player info (Club/Age/Position), plus: attributes "
                                "for Role scores; stats markers for Player stats; "
                                "Salary and match fees for Squad finance.",
                                className="text-muted small mb-3",
                            ),
                            html.Div(id="up-files-table", children=_files_table()),
                        ]
                    ),
                ],
                className="mb-3 rs-section-card",
            ),
        ],
        fluid=True,
        className="rs-page up-page",
    )


@callback(
    Output("up-upload-status", "children"),
    Output("up-files-table", "children"),
    Output("up-rev", "data"),
    Input("up-upload", "contents"),
    State("up-upload", "filename"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def save_uploads(contents_list, filenames, rev):
    if not contents_list:
        return no_update, no_update, no_update
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
            messages.append(
                html.Div(
                    [
                        html.Span("✓ ", className="rs-upload-ok"),
                        html.Span(entry.get("original_name") or name),
                        html.Span(f" · eligible: {page_txt}", className="text-muted"),
                    ],
                    className="up-save-row",
                )
            )
        except Exception as exc:
            messages.append(upload_error(f"{name}: {exc}"))
    if not messages:
        return no_update, no_update, no_update
    return html.Div(messages), _files_table(), int(rev or 0) + 1


@callback(
    Output("up-files-table", "children", allow_duplicate=True),
    Output("up-rev", "data", allow_duplicate=True),
    Input({"type": "up-delete", "id": ALL}, "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def delete_saved(n_clicks, rev):
    if not ctx.triggered_id or not any(n_clicks or []):
        return no_update, no_update
    file_id = ctx.triggered_id.get("id")
    if not file_id or file_id == "_":
        return no_update, no_update
    # Ignore initial stub / zero clicks on other buttons
    if not any((n or 0) > 0 for n in (n_clicks or [])):
        return no_update, no_update
    lib.delete_file(file_id)
    return _files_table(), int(rev or 0) + 1


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
