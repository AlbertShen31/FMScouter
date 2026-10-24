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
from components.player_table import default_page_size_value, page_size_select_data
from components.scouting_shell import decode_upload, job_busy_overlay, upload_error
import services.compute_progress as compute_progress
import services.export_library as lib
import services.ui_settings as us
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


def _any_files() -> bool:
    return bool(lib.list_files())


def _normalize_page_size(value, settings=None) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        size = us.page_size(settings)
    return max(1, size)


def _page_bounds(total: int, page, page_size: int) -> tuple[int, int, int]:
    """Return 1-indexed page, page count, and slice start."""
    page_count = max(1, (total + page_size - 1) // page_size) if total else 1
    try:
        page_idx = int(page or 1)
    except (TypeError, ValueError):
        page_idx = 1
    page_idx = max(1, min(page_idx, page_count))
    return page_idx, page_count, (page_idx - 1) * page_size


def _files_caption(total: int, page: int, page_size: int) -> str:
    if total <= 0:
        return ""
    if total == 1:
        return "1 file"
    start = (page - 1) * page_size + 1
    end = min(total, page * page_size)
    if start == 1 and end == total:
        return f"{total} files"
    return f"{start}–{end} of {total} files"


def _selected_file_ids(checked, ids) -> list[str]:
    out: list[str] = []
    for on, spec in zip(checked or [], ids or []):
        fid = spec.get("id") if isinstance(spec, dict) else None
        if on and fid and fid != "_":
            out.append(str(fid))
    return out


def _delete_preview_body(file_ids: list[str]) -> html.Div:
    preview = lib.preview_delete(file_ids)
    selected = preview["selected"]
    cascaded = preview["cascaded"]
    if not selected:
        return html.Div("No files selected.", className="text-muted")
    n = len(selected)
    names = [lib.display_label(entry) for entry in selected]
    shown = names[:12]
    extra = n - len(shown)
    items = [html.Li(name) for name in shown]
    if extra:
        items.append(html.Li(f"and {extra} more"))
    bits: list = [
        html.P(
            f"Delete {n} saved file{'' if n == 1 else 's'}? This cannot be undone.",
            className="mb-2",
        ),
        html.Ul(items, className="up-delete-list"),
    ]
    if cascaded:
        pack_names = ", ".join(lib.display_label(entry) for entry in cascaded)
        bits.append(
            html.P(
                "Also removes multi-year pack"
                f"{'' if len(cascaded) == 1 else 's'} that use the selected "
                f"CSV{'' if n == 1 else 's'}: {pack_names}.",
                className="text-muted small mt-3 mb-0",
            )
        )
    return html.Div(bits)


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
    "To swap a season later, Edit the pack in the saved-files table."
)
UP_ROLL_YEAR_TIP = (
    "Build a new multi-year pack from an existing one plus a newer season CSV. "
    "The source pack stays unchanged. On the new pack: new CSV → Year 3, former "
    "Year 3 → Year 2, Year 2 → Year 1, and former Year 1 is dropped."
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
                "label": (
                    f"{label}"
                    + lib.player_count_suffix(entry)
                    + (f" · {when}" if when else "")
                    + elig
                ),
            }
        )
    return opts


def _pack_select_data(*, page: str | None = None) -> list[dict[str, str]]:
    opts = [{"value": "", "label": "— Select a multi-year pack —"}]
    for entry in lib.list_multi_year_packs(page=page):
        years = lib.configured_years(entry)
        slots = "+".join(f"Y{k}" for k in lib.YEAR_KEYS if k in years)
        when = (entry.get("updated_at") or entry.get("saved_at") or "")[:10]
        label = lib.display_label(entry)
        suffix = (
            lib.player_count_suffix(entry)
            + f" · {slots}"
            + (f" · {when}" if when else "")
        )
        opts.append({"value": entry["id"], "label": f"{label}{suffix}"})
    return opts


def _year_slot_label(file_id: str | None) -> str:
    if not file_id:
        return "— empty —"
    entry = lib.get_file(file_id)
    if not entry:
        return f"(missing {file_id})"
    return lib.display_label(entry) + lib.player_count_suffix(entry)


def _roll_preview(pack_id: str | None, new_year_id: str | None) -> html.Div:
    if not pack_id:
        return html.Div(
            "Pick a source multi-year pack to preview the year shift.",
            className="text-muted small",
        )
    pack = lib.get_file(pack_id)
    if not pack or not lib.is_multi_year(pack):
        return html.Div("That pack was not found.", className="text-muted small")
    current = lib.configured_years(pack)
    rows = [
        html.Div(
            [
                html.Strong("Source: "),
                html.Span(
                    f"Y3 {_year_slot_label(current.get('3'))} · "
                    f"Y2 {_year_slot_label(current.get('2'))} · "
                    f"Y1 {_year_slot_label(current.get('1'))}"
                ),
            ],
            className="up-roll-preview-row",
        )
    ]
    if not new_year_id:
        rows.append(
            html.Div(
                "Pick the new latest season CSV to see the new pack layout.",
                className="text-muted small mt-1",
            )
        )
        return html.Div(rows, className="up-roll-preview")
    try:
        planned = lib.planned_roll_forward_years(current, new_year_id)
    except ValueError as exc:
        rows.append(html.Div(str(exc), className="rs-upload-error mt-1"))
        return html.Div(rows, className="up-roll-preview")
    dropped = current.get("1")
    rows.append(
        html.Div(
            [
                html.Strong("New pack: "),
                html.Span(
                    f"Y3 {_year_slot_label(planned.get('3'))} · "
                    f"Y2 {_year_slot_label(planned.get('2'))} · "
                    f"Y1 {_year_slot_label(planned.get('1'))}"
                ),
            ],
            className="up-roll-preview-row mt-1",
        )
    )
    if dropped:
        rows.append(
            html.Div(
                f"Dropped from source Year 1: {_year_slot_label(dropped)}",
                className="text-muted small mt-1",
            )
        )
    return html.Div(rows, className="up-roll-preview")


def _players_cell(entry: dict) -> html.Span:
    n = lib.player_count_of(entry)
    if n is None:
        return html.Span(
            "—",
            className="text-muted",
            title="Count appears after the file is on disk",
        )
    phrase = lib.player_count_phrase(n)
    return html.Span(
        f"{n:,}",
        className="up-player-count",
        title=phrase,
    )


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


def _files_table(
    entries: list[dict] | None = None,
    *,
    page: int = 1,
    page_size: int = 50,
) -> html.Div:
    entries = entries if entries is not None else lib.list_files()
    if not entries:
        return html.Div(
            "No saved files yet. Upload one or more CSVs above.",
            className="text-muted small",
        )
    page, _page_count, start = _page_bounds(len(entries), page, page_size)
    page_entries = entries[start : start + page_size]
    header = html.Tr(
        [
            html.Th("", className="up-select-col"),
            html.Th("Name"),
            html.Th("Type"),
            html.Th("Players"),
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
    sig_key = upload_cache.signature_key() if page_entries else None
    for entry in page_entries:
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
                        dmc.Checkbox(
                            id={"type": "up-select", "id": file_id},
                            checked=False,
                            size="xs",
                            className="up-select-check",
                            **{"aria-label": f"Select {label}"},
                        ),
                        className="up-select-col",
                    ),
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
                    html.Td(_players_cell(entry)),
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


def _roll_year_panel() -> html.Div:
    src = _source_select_data()
    packs = _pack_select_data()
    return html.Div(
        [
            html.P(
                "Creates a new multi-year pack. The source pack is left as-is. "
                "New CSV → Year 3, former Year 3 → Year 2, Year 2 → Year 1; "
                "former Year 1 is not included.",
                className="text-muted small mb-3",
            ),
            html.Label("Source multi-year pack", className="rs-field-label"),
            dmc.Select(
                id="up-roll-pack",
                data=packs,
                value="",
                clearable=True,
                searchable=True,
                placeholder="Select a multi-year pack…",
                className="mb-3 up-roll-pack",
            ),
            html.Label("New latest season", className="rs-field-label"),
            dmc.Select(
                id="up-roll-new-year",
                data=src,
                value="",
                clearable=True,
                searchable=True,
                placeholder="Select a saved CSV…",
                className="mb-3 up-roll-new-year",
            ),
            html.Label("New pack name", className="rs-field-label"),
            dmc.TextInput(
                id="up-roll-name",
                placeholder="e.g. Liga I 2024–27",
                className="mb-3 up-roll-name",
            ),
            html.Label("Note", className="rs-field-label"),
            dbc.Textarea(
                id="up-roll-note",
                placeholder="Optional note",
                rows=2,
                className="up-roll-note mb-3",
            ),
            html.Div(
                id="up-roll-preview",
                children=_roll_preview(None, None),
                className="mb-3",
            ),
            html.Div(
                [
                    dmc.Button(
                        "Create pack with latest year",
                        id="up-roll-apply",
                        n_clicks=0,
                    ),
                ],
                className="up-roll-actions",
            ),
            html.Div(id="up-roll-status", className="mt-2"),
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


def _delete_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Delete saved files"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    dcc.Store(id="up-delete-ids", data=[]),
                    html.Div(id="up-delete-modal-body"),
                ]
            ),
            dbc.ModalFooter(
                [
                    dmc.Button(
                        "Cancel",
                        id="up-delete-cancel",
                        variant="default",
                        n_clicks=0,
                        className="me-2",
                    ),
                    dmc.Button(
                        "Delete",
                        id="up-delete-confirm",
                        color="red",
                        n_clicks=0,
                    ),
                ]
            ),
        ],
        id="up-delete-modal",
        className="up-edit-modal up-delete-modal",
        is_open=False,
        centered=True,
    )


def layout(**_kwargs):
    lib.ensure_dirs()
    settings = us.load()
    page_size = us.page_size(settings)
    entries = lib.list_files()
    page, page_count, _start = _page_bounds(len(entries), 1, page_size)
    return dbc.Container(
        [
            dcc.Download(id="up-view-download"),
            dcc.Store(id="up-rev", data=0),
            dcc.Store(id="up-table-tick", data=0),
            dcc.Interval(
                id="up-progress-poll",
                interval=1500,
                n_intervals=0,
                disabled=True,
            ),
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
                    dmc.Checkbox(
                        id={"type": "up-select", "id": "_"},
                        checked=False,
                    ),
                ],
                hidden=True,
            ),
            _edit_modal(),
            _delete_modal(),
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
                                "3. Create multi-year pack",
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
                                "4. Add latest year",
                                UP_ROLL_YEAR_TIP,
                                "up-help-roll-year",
                            ),
                            dbc.CardBody(_roll_year_panel()),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            _card_header(
                                "5. Saved files & page eligibility",
                                UP_ELIGIBILITY_TIP,
                                "up-help-eligibility",
                            ),
                            dbc.CardBody(
                                [
                                    html.Div(
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
                                                    *help_icon(
                                                        UP_COMPUTE_ALL_TIP,
                                                        "up-help-compute-all",
                                                    ),
                                                ],
                                                className="up-files-actions",
                                            ),
                                            html.Div(
                                                [
                                                    dmc.Button(
                                                        "Select all",
                                                        id="up-select-all",
                                                        size="sm",
                                                        variant="light",
                                                        n_clicks=0,
                                                        disabled=not _any_files(),
                                                    ),
                                                    dmc.Button(
                                                        "Delete selected",
                                                        id="up-delete-selected",
                                                        size="sm",
                                                        variant="light",
                                                        color="red",
                                                        n_clicks=0,
                                                        disabled=True,
                                                        className="rs-squad-clear-btn",
                                                    ),
                                                ],
                                                className="up-bulk-actions",
                                            ),
                                        ],
                                        className="up-compute-all-row mb-3",
                                    ),
                                    html.Div(
                                        id="up-files-table",
                                        children=_files_table(
                                            entries,
                                            page=page,
                                            page_size=page_size,
                                        ),
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                id="up-table-caption",
                                                children=_files_caption(
                                                    len(entries), page, page_size
                                                ),
                                                className="up-files-caption text-muted",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Rows per page",
                                                                className="rs-field-label",
                                                            ),
                                                            dmc.Select(
                                                                id="up-page-size",
                                                                data=page_size_select_data(
                                                                    settings
                                                                ),
                                                                value=default_page_size_value(
                                                                    settings
                                                                ),
                                                                clearable=False,
                                                                searchable=False,
                                                            ),
                                                        ],
                                                        className="rs-table-page-size",
                                                    ),
                                                    dmc.Pagination(
                                                        id="up-pagination",
                                                        total=page_count,
                                                        value=page,
                                                        size="sm",
                                                        hideWithOnePage=True,
                                                        siblings=1,
                                                        boundaries=1,
                                                        className="up-pagination",
                                                    ),
                                                ],
                                                className="up-files-pager-actions",
                                            ),
                                        ],
                                        id="up-files-pager",
                                        className="up-files-pager",
                                        hidden=not bool(entries),
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    job_busy_overlay(
                        "up-busy",
                        prefix="up",
                        initial_label="Saving and precomputing…",
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
    Output("up-rev", "data"),
    Output("up-compute-all", "disabled"),
    Output("up-my-year-1", "data"),
    Output("up-my-year-2", "data"),
    Output("up-my-year-3", "data"),
    Output("up-roll-new-year", "data"),
    Output("up-roll-pack", "data"),
    Input("up-upload", "contents"),
    State("up-upload", "filename"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def save_uploads(contents_list, filenames, rev):
    if not contents_list:
        return tuple([no_update] * 8)
    if isinstance(contents_list, str):
        contents_list = [contents_list]
        filenames = [filenames]
    filenames = filenames or []
    messages = []
    compute_progress.begin("Saving and precomputing…", phase="Saving and precomputing…")
    try:
        total_files = len(contents_list)
        for i, contents in enumerate(contents_list):
            name = (filenames[i] if i < len(filenames) else None) or f"export_{i + 1}.csv"
            if total_files > 1:
                compute_progress.update(
                    phase=f"File {i + 1} of {total_files}",
                    message=str(name),
                )
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
    finally:
        compute_progress.end()
    if not messages:
        return tuple([no_update] * 8)
    src = _source_select_data()
    packs = _pack_select_data()
    return (
        html.Div(messages),
        int(rev or 0) + 1,
        not _any_computable(),
        src,
        src,
        src,
        src,
        packs,
    )


@callback(
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Output("up-my-year-1", "data", allow_duplicate=True),
    Output("up-my-year-2", "data", allow_duplicate=True),
    Output("up-my-year-3", "data", allow_duplicate=True),
    Output("up-roll-new-year", "data", allow_duplicate=True),
    Output("up-roll-pack", "data", allow_duplicate=True),
    Input({"type": "up-delete", "id": ALL}, "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def delete_saved(n_clicks, rev):
    if not ctx.triggered_id or not any(n_clicks or []):
        return tuple([no_update] * 7)
    file_id = ctx.triggered_id.get("id")
    if not file_id or file_id == "_":
        return tuple([no_update] * 7)
    if not any((n or 0) > 0 for n in (n_clicks or [])):
        return tuple([no_update] * 7)
    lib.delete_file(file_id)
    src = _source_select_data()
    packs = _pack_select_data()
    return (
        int(rev or 0) + 1,
        not _any_computable(),
        src,
        src,
        src,
        src,
        packs,
    )


@callback(
    Output({"type": "up-select", "id": ALL}, "checked"),
    Input("up-select-all", "n_clicks"),
    State({"type": "up-select", "id": ALL}, "id"),
    State({"type": "up-select", "id": ALL}, "checked"),
    prevent_initial_call=True,
)
def toggle_select_all(n_clicks, ids, checked):
    if not n_clicks:
        return no_update
    ids = ids or []
    checked = checked or []
    real_on = [
        bool(on)
        for spec, on in zip(ids, checked)
        if isinstance(spec, dict) and spec.get("id") not in (None, "_")
    ]
    turn_on = bool(real_on) and not all(real_on)
    return [
        (
            turn_on
            if isinstance(spec, dict) and spec.get("id") not in (None, "_")
            else False
        )
        for spec in ids
    ]


@callback(
    Output("up-delete-selected", "disabled"),
    Output("up-delete-selected", "children"),
    Output("up-select-all", "disabled"),
    Output("up-select-all", "children"),
    Input({"type": "up-select", "id": ALL}, "checked"),
    State({"type": "up-select", "id": ALL}, "id"),
)
def sync_bulk_delete_controls(checked, ids):
    selected = _selected_file_ids(checked, ids)
    n_real = sum(
        1
        for spec in (ids or [])
        if isinstance(spec, dict) and spec.get("id") not in (None, "_")
    )
    n_sel = len(selected)
    delete_label = "Delete selected" if n_sel == 0 else f"Delete selected ({n_sel})"
    select_label = "Clear selection" if n_real and n_sel == n_real else "Select all"
    return n_sel == 0, delete_label, n_real == 0, select_label


@callback(
    Output("up-delete-modal", "is_open"),
    Output("up-delete-modal-body", "children"),
    Output("up-delete-ids", "data"),
    Input("up-delete-selected", "n_clicks"),
    Input("up-delete-cancel", "n_clicks"),
    State({"type": "up-select", "id": ALL}, "checked"),
    State({"type": "up-select", "id": ALL}, "id"),
    prevent_initial_call=True,
)
def open_bulk_delete(n_delete, n_cancel, checked, ids):
    triggered = ctx.triggered_id
    if triggered == "up-delete-cancel":
        return False, no_update, no_update
    selected = _selected_file_ids(checked, ids)
    if not selected:
        return False, no_update, no_update
    return True, _delete_preview_body(selected), selected


@callback(
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Output("up-my-year-1", "data", allow_duplicate=True),
    Output("up-my-year-2", "data", allow_duplicate=True),
    Output("up-my-year-3", "data", allow_duplicate=True),
    Output("up-roll-new-year", "data", allow_duplicate=True),
    Output("up-roll-pack", "data", allow_duplicate=True),
    Output("up-delete-modal", "is_open", allow_duplicate=True),
    Output("up-upload-status", "children", allow_duplicate=True),
    Input("up-delete-confirm", "n_clicks"),
    State("up-delete-ids", "data"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def confirm_bulk_delete(n_clicks, file_ids, rev):
    if not n_clicks:
        return tuple([no_update] * 9)
    ids = [str(fid) for fid in (file_ids or []) if fid]
    if not ids:
        return tuple([no_update] * 7 + [False, no_update])
    result = lib.delete_files(ids)
    removed = int(result.get("removed") or 0)
    cascaded = int(result.get("cascaded") or 0)
    if removed:
        msg = f"Deleted {removed} saved file{'' if removed == 1 else 's'}."
        if cascaded:
            msg += (
                f" Also removed {cascaded} multi-year pack"
                f"{'' if cascaded == 1 else 's'} that used those CSVs."
            )
        status = html.Div(
            [
                html.Span("✓ ", className="rs-upload-ok"),
                html.Span(msg),
            ],
            className="up-save-row",
        )
    else:
        status = html.Div("No matching files to delete.", className="text-muted")
    src = _source_select_data()
    packs = _pack_select_data()
    return (
        int(rev or 0) + 1,
        not _any_computable(),
        src,
        src,
        src,
        src,
        packs,
        False,
        status,
    )


@callback(
    Output("up-my-status", "children"),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Output("up-my-name", "value"),
    Output("up-my-note", "value"),
    Output("up-my-year-1", "value"),
    Output("up-my-year-2", "value"),
    Output("up-my-year-3", "value"),
    Output("up-roll-pack", "data", allow_duplicate=True),
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
    compute_progress.begin(
        "Creating multi-year pack…",
        phase="Creating multi-year pack…",
    )
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
            int(rev or 0) + 1,
            not _any_computable(),
            "",
            "",
            "",
            "",
            "",
            _pack_select_data(),
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
    finally:
        compute_progress.end()


@callback(
    Output("up-roll-preview", "children"),
    Input("up-roll-pack", "value"),
    Input("up-roll-new-year", "value"),
)
def update_roll_preview(pack_id, new_year_id):
    return _roll_preview(pack_id or "", new_year_id or "")


@callback(
    Output("up-roll-name", "value", allow_duplicate=True),
    Output("up-roll-note", "value", allow_duplicate=True),
    Input("up-roll-pack", "value"),
    prevent_initial_call=True,
)
def prefill_roll_meta(pack_id):
    """Suggest a new-pack name/note from the source when the user picks one."""
    if not pack_id:
        return "", ""
    pack = lib.get_file(pack_id)
    if not pack or not lib.is_multi_year(pack):
        return no_update, no_update
    return lib.display_label(pack), pack.get("user_note") or ""


@callback(
    Output("up-roll-status", "children"),
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Output("up-roll-pack", "data", allow_duplicate=True),
    Output("up-roll-pack", "value"),
    Output("up-roll-new-year", "value"),
    Output("up-roll-name", "value"),
    Output("up-roll-note", "value"),
    Output("up-roll-preview", "children", allow_duplicate=True),
    Input("up-roll-apply", "n_clicks"),
    State("up-roll-pack", "value"),
    State("up-roll-new-year", "value"),
    State("up-roll-name", "value"),
    State("up-roll-note", "value"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def apply_roll_forward(n_clicks, pack_id, new_year_id, name, note, rev):
    if not n_clicks:
        return tuple([no_update] * 9)
    compute_progress.begin(
        "Creating pack with latest year…",
        phase="Creating pack with latest year…",
    )
    try:
        entry = lib.add_latest_year_to_pack(
            pack_id=pack_id or "",
            new_year_file_id=new_year_id or "",
            display_name=name or "",
            user_note=note or "",
        )
        cache = upload_cache.cache_status(entry.get("id") or "", entry)
        msg = html.Div(
            [
                html.Span("✓ ", className="rs-upload-ok"),
                html.Span(f"Created {lib.display_label(entry)} from latest year"),
                html.Span(f" · precompute: {cache['label']}", className="text-muted"),
            ],
            className="up-save-row",
        )
        packs = _pack_select_data()
        return (
            msg,
            int(rev or 0) + 1,
            not _any_computable(),
            packs,
            "",
            "",
            "",
            "",
            _roll_preview(None, None),
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
    finally:
        compute_progress.end()

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
    Output("up-table-tick", "data"),
    Input("up-edit-modal", "is_open"),
    State("up-table-tick", "data"),
    prevent_initial_call=True,
)
def refresh_table_after_edit(is_open, tick):
    # Refresh when the edit modal closes after a save/cancel.
    # Do not bump up-rev here: multi-year save keeps the busy overlay on until
    # recompute_after_multi_year_edit finishes and bumps rev itself.
    if is_open:
        return no_update
    return int(tick or 0) + 1


@callback(
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-edit-recompute", "data", allow_duplicate=True),
    Output("up-upload-status", "children", allow_duplicate=True),
    Output("up-roll-pack", "data", allow_duplicate=True),
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
    compute_progress.begin(
        f"Updating {label}…",
        phase="Updating multi-year pack…",
    )
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
    finally:
        compute_progress.end()
    return (
        int(rev or 0) + 1,
        None,
        msg,
        _pack_select_data(),
    )



@callback(
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-upload-status", "children", allow_duplicate=True),
    Input({"type": "up-compute", "id": ALL}, "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def compute_saved(n_clicks, rev):
    if not ctx.triggered_id or not any(n_clicks or []):
        return no_update, no_update
    file_id = ctx.triggered_id.get("id")
    if not file_id or file_id == "_":
        return no_update, no_update
    if not any((n or 0) > 0 for n in (n_clicks or [])):
        return no_update, no_update
    entry = lib.get_file(file_id)
    if not entry:
        return no_update, no_update
    compute_progress.begin(
        f"Precomputing {lib.display_label(entry)}…",
        phase="Precomputing…",
    )
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
    finally:
        compute_progress.end()
    return int(rev or 0) + 1, msg


@callback(
    Output("up-rev", "data", allow_duplicate=True),
    Output("up-upload-status", "children", allow_duplicate=True),
    Output("up-compute-all", "disabled", allow_duplicate=True),
    Input("up-compute-all", "n_clicks"),
    State("up-rev", "data"),
    prevent_initial_call=True,
)
def compute_all_saved(n_clicks, rev):
    if not n_clicks:
        return no_update, no_update, no_update
    eligible = [
        entry
        for entry in lib.list_files()
        if entry.get("role_scores") or entry.get("stats")
    ]
    if not eligible:
        return (
            int(rev or 0) + 1,
            html.Div("No eligible files to precompute.", className="text-muted"),
            True,
        )
    ok = 0
    errors = []
    compute_progress.begin("Precomputing all files…", phase="Precomputing all files…")
    try:
        for idx, entry in enumerate(eligible, start=1):
            file_id = entry.get("id") or ""
            label = lib.display_label(entry)
            compute_progress.update(
                phase=f"File {idx} of {len(eligible)}",
                message=str(label),
                done=0,
                total=0,
            )
            try:
                upload_cache.compute_file(file_id)
                ok += 1
            except Exception as exc:
                errors.append(f"{label}: {exc}")
    finally:
        compute_progress.end()
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
    return int(rev or 0) + 1, html.Div(rows), not _any_computable()


@callback(
    Output("up-files-table", "children"),
    Output("up-table-caption", "children"),
    Output("up-pagination", "total"),
    Output("up-pagination", "value"),
    Output("up-files-pager", "hidden"),
    Input("up-rev", "data"),
    Input("up-table-tick", "data"),
    Input("up-page-size", "value"),
    Input("up-pagination", "value"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def render_files_table(_rev, _tick, page_size, page, settings):
    size = _normalize_page_size(page_size, settings)
    requested = 1 if ctx.triggered_id == "up-page-size" else page
    entries = lib.list_files()
    page_idx, page_count, _start = _page_bounds(len(entries), requested, size)
    try:
        current = int(page or 1)
    except (TypeError, ValueError):
        current = 1
    page_out = page_idx if page_idx != current else no_update
    return (
        _files_table(entries, page=page_idx, page_size=size),
        _files_caption(len(entries), page_idx, size),
        page_count,
        page_out,
        not bool(entries),
    )


@callback(
    Output("up-page-size", "data"),
    Output("up-page-size", "value"),
    Input("ui-settings", "data"),
    State("up-page-size", "value"),
)
def sync_up_page_size_from_settings(settings, page_size):
    settings = us.normalize(settings)
    data = page_size_select_data(settings)
    default = default_page_size_value(settings)
    return data, us.clamp_choice(page_size, data, default)


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
    function(contents, computeClicks, computeAllClicks, packClicks, rollClicks, editSave, editKind) {
        var skip = [
            window.dash_clientside.no_update,
            window.dash_clientside.no_update,
        ];
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return skip;
        }
        var prop = trig[0].prop_id || "";
        if (prop.indexOf("contents") !== -1 && !trig[0].value) {
            return skip;
        }
        if (prop.indexOf("up-compute-all") !== -1 && !computeAllClicks) {
            return skip;
        }
        if (prop.indexOf("up-my-create") !== -1 && !packClicks) {
            return skip;
        }
        if (prop.indexOf("up-roll-apply") !== -1 && !rollClicks) {
            return skip;
        }
        if (prop.indexOf("up-edit-save") !== -1) {
            if (!editSave || editKind !== "multi_year") {
                return skip;
            }
        }
        if (prop.indexOf("up-compute") !== -1 && prop.indexOf("up-compute-all") === -1) {
            var clicks = computeClicks || [];
            var any = false;
            for (var i = 0; i < clicks.length; i++) {
                if (clicks[i]) { any = true; break; }
            }
            if (!any) {
                return skip;
            }
        }
        var label = document.getElementById("up-busy-label")
            || document.querySelector("#up-busy .rs-shortlist-busy-label");
        var text = "Saving and precomputing…";
        if (prop.indexOf("up-edit-save") !== -1) {
            text = "Updating multi-year pack…";
        } else if (prop.indexOf("up-roll-apply") !== -1) {
            text = "Creating pack with latest year…";
        } else if (prop.indexOf("up-my-create") !== -1) {
            text = "Creating multi-year pack…";
        } else if (prop.indexOf("up-compute-all") !== -1) {
            text = "Precomputing all files…";
        } else if (prop.indexOf("n_clicks") !== -1) {
            text = "Precomputing…";
        }
        if (label) { label.textContent = text; }
        var detail = document.getElementById("up-busy-detail");
        if (detail) { detail.textContent = ""; }
        var track = document.getElementById("up-busy-track");
        if (track) {
            track.className = "rs-busy-progress is-indeterminate";
        }
        return ["rs-shortlist-busy is-on t-" + String(Date.now()), false];
    }
    """,
    Output("up-busy", "className"),
    Output("up-progress-poll", "disabled"),
    Input("up-upload", "contents"),
    Input({"type": "up-compute", "id": ALL}, "n_clicks"),
    Input("up-compute-all", "n_clicks"),
    Input("up-my-create", "n_clicks"),
    Input("up-roll-apply", "n_clicks"),
    Input("up-edit-save", "n_clicks"),
    State("up-edit-kind", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(deleteClicks, confirmClicks) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var prop = String(trig[0].prop_id || "");
        var fromConfirm = prop.indexOf("up-delete-confirm") !== -1;
        var any = false;
        if (fromConfirm) {
            any = !!confirmClicks;
        } else {
            var clicks = deleteClicks || [];
            for (var i = 0; i < clicks.length; i++) {
                if (clicks[i]) { any = true; break; }
            }
        }
        if (!any) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var label = document.getElementById("up-busy-label")
            || document.querySelector("#up-busy .rs-shortlist-busy-label");
        if (label) {
            label.textContent = "Deleting…";
        }
        return ["rs-shortlist-busy is-on t-" + String(Date.now()), true];
    }
    """,
    Output("up-busy", "className", allow_duplicate=True),
    Output("up-progress-poll", "disabled", allow_duplicate=True),
    Input({"type": "up-delete", "id": ALL}, "n_clicks"),
    Input("up-delete-confirm", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(_rev) {
        var el = document.getElementById("up-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        return ["rs-shortlist-busy", true];
    }
    """,
    Output("up-busy", "className", allow_duplicate=True),
    Output("up-progress-poll", "disabled", allow_duplicate=True),
    Input("up-rev", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("up-busy-label", "children"),
    Output("up-busy-track", "className"),
    Output("up-busy-bar", "style"),
    Output("up-busy-detail", "children"),
    Input("up-progress-poll", "n_intervals"),
)
def up_poll_progress(_n):
    props = compute_progress.ui_props()
    if not props.get("active"):
        return no_update, no_update, no_update, no_update
    return (
        props["label"],
        props["track_class"],
        props["bar_style"],
        props["detail"] or "",
    )
