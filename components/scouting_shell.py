"""Shared upload → filter → table → hist → marks plumbing for scouting pages.

Layout builders and callback registrars used by Role scores and Player stats.
Domain scoring / column builders stay page-local.

Typical IDs (``prefix`` e.g. ``rs`` / ``st``):

- ``{prefix}-upload``, ``{prefix}-upload-replace``, ``{prefix}-upload-wrap``,
  ``{prefix}-upload-replace-wrap``, ``{prefix}-upload-status``
- ``{prefix}-parsed`` (often declared in ``app.py`` as a session store)
- ``{prefix}-parsed-historical`` (optional comparison export; page logic uses current only)
- ``{prefix}-upload-hist``, ``{prefix}-upload-hist-replace`` (historical slot)
- ``{prefix}-table``, ``{prefix}-hist``, ``{prefix}-hist-wrap``, ``{prefix}-hist-toggle``
- Pos/foot stores and pattern-matching buttons (configurable names)
- Marked-rows store + clear button (configurable)

Workflow gates:

- Stats: pass ``reveal_ids=["st-main"]`` so upload unhides the shortlist.
- Role scores: leave ``reveal_ids`` empty; page-owned ``reveal_workflow`` still
  gates setup vs results after roles are scored.
"""
from __future__ import annotations

import base64
import json
import zlib
from collections.abc import Callable, Sequence
from typing import Any

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
)
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon

ParseFn = Callable[[str], list]
RowKeyFn = Callable[[dict], str]


def as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def clicked(n_clicks) -> bool:
    return bool(n_clicks) and any(n_clicks)


def decode_upload(contents: str, *, strict: bool = False) -> str:
    """Decode a Dash Upload payload to text.

    ``strict=False`` (default) tries utf-8-sig / utf-8 / latin-1 then replaces.
    ``strict=True`` uses utf-8-sig with replacement only (stats-style).
    """
    _header, _, payload = contents.partition(",")
    raw = base64.b64decode(payload)
    if strict:
        return raw.decode("utf-8-sig", errors="replace")
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def pack_parsed(players: list, filename: str) -> dict:
    """Compress parsed players for sessionStorage (large exports)."""
    raw = json.dumps(
        {"players": players, "filename": filename},
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    blob = base64.b64encode(zlib.compress(raw, 6)).decode("ascii")
    return {
        "v": 1,
        "encoding": "zlib+b64",
        "filename": filename,
        "n": len(players),
        "payload": blob,
    }


def unpack_parsed(data) -> dict | None:
    """Return ``{players, filename}`` from a packed or plain session store."""
    if not data:
        return None
    if isinstance(data.get("players"), list):
        return data
    blob = data.get("payload")
    if not blob:
        return None
    try:
        raw = zlib.decompress(base64.b64decode(blob))
        packed = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(packed, dict) or not isinstance(packed.get("players"), list):
        return None
    packed.setdefault("filename", data.get("filename") or "export.csv")
    return packed


def parsed_players(data) -> list:
    unpacked = unpack_parsed(data)
    return list((unpacked or {}).get("players") or [])


def parsed_historical_players(data) -> list:
    """Players from the historical comparison slot (if uploaded)."""
    return parsed_players(data)


def upload_status_bar(
    count: int,
    filename: str,
    *,
    replaced: bool = False,
    slot_label: str | None = None,
) -> list:
    if replaced:
        lead = html.Span("Replaced", className="rs-upload-replaced")
        count_label = f"{count:,} players"
    else:
        lead = html.Span("✓", className="rs-upload-ok")
        count_label = f"{count:,} players loaded"
    parts: list = []
    if slot_label:
        parts.append(
            html.Span(slot_label, className="rs-upload-slot-tag")
        )
        parts.append(html.Span("·", className="rs-upload-sep"))
    parts.extend(
        [
            lead,
            html.Span(count_label, className="rs-upload-count"),
            html.Span("·", className="rs-upload-sep"),
            html.Span(filename, className="rs-upload-name", title=filename),
            html.Span("·", className="rs-upload-sep"),
        ]
    )
    return parts


def upload_error(message: str) -> html.Div:
    return html.Div(message, className="rs-upload-error")


def default_row_key(row: dict) -> str:
    return str(row.get("id") or row.get("_key") or "").strip()


# ── Layout builders ──────────────────────────────────────────────────────────


def _upload_slot(
    prefix: str,
    slot: str,
    *,
    title: str,
    subtitle: str,
    upload_label: Any,
    library_page: str | None = None,
    library_only: bool = False,
) -> html.Div:
    """One upload dropzone + status row. ``slot`` is ``current`` or ``hist``.

    When ``library_only`` is True, the dropzone/replace controls stay hidden
    (stub Upload components remain so Clear callbacks still have targets).
    """
    if slot == "current":
        upload_id = f"{prefix}-upload"
        replace_id = f"{prefix}-upload-replace"
        wrap_id = f"{prefix}-upload-wrap"
        replace_wrap_id = f"{prefix}-upload-replace-wrap"
        status_id = f"{prefix}-upload-status"
        lib_select_id = f"{prefix}-lib-select"
        lib_clear_id = f"{prefix}-lib-clear"
    else:
        upload_id = f"{prefix}-upload-hist"
        replace_id = f"{prefix}-upload-hist-replace"
        wrap_id = f"{prefix}-upload-hist-wrap"
        replace_wrap_id = f"{prefix}-upload-hist-replace-wrap"
        status_id = f"{prefix}-upload-hist-status"
        lib_select_id = f"{prefix}-lib-select-hist"
        lib_clear_id = f"{prefix}-lib-clear-hist"
    children: list = [
        html.Div(title, className="rs-upload-slot-title"),
        html.P(subtitle, className="rs-upload-slot-note"),
    ]
    if library_page:
        import services.export_library as lib

        lib.ensure_dirs()
        options = lib.select_options(page=library_page)
        children.append(
            html.Div(
                [
                    html.Label("Saved file", className="rs-field-label"),
                    dmc.Select(
                        id=lib_select_id,
                        data=options,
                        value=None,
                        placeholder=(
                            "Choose from Uploads library"
                            if options
                            else "No eligible saved files"
                        ),
                        clearable=True,
                        searchable=True,
                        disabled=not options,
                        className="rs-lib-select",
                    ),
                ],
                className="rs-lib-picker",
            )
        )
    # Keep Upload stubs in the tree so library Clear can reset contents/filename.
    children.extend(
        [
            html.Div(
                dcc.Upload(
                    id=upload_id,
                    children=None if library_only else upload_label,
                    className="rs-upload",
                    multiple=False,
                    disabled=library_only,
                ),
                id=wrap_id,
                className="rs-upload-drop-wrap",
                hidden=library_only,
            ),
            html.Div(
                [
                    html.Div(id=status_id, className="rs-upload-status"),
                    html.Div(
                        dcc.Upload(
                            id=replace_id,
                            children=(
                                None
                                if library_only
                                else html.Span(
                                    "Replace file",
                                    className="rs-upload-replace",
                                )
                            ),
                            className="rs-upload-replace-btn",
                            multiple=False,
                            disabled=library_only,
                        ),
                        id=replace_wrap_id,
                        hidden=True,
                        title="Choose a different CSV for this slot",
                    ),
                    dmc.Button(
                        "Clear",
                        id=lib_clear_id,
                        n_clicks=0,
                        size="xs",
                        variant="light",
                        color="red",
                        disabled=True,
                        className="rs-lib-clear",
                        buttonProps={
                            "title": (
                                "Remove this saved file from the page cache"
                                if library_only
                                else (
                                    "Remove this side’s export "
                                    "(manual upload or saved file) from the page cache"
                                )
                            )
                        },
                    ),
                ],
                className="rs-upload-status-row",
            ),
        ]
    )
    return html.Div(children, className="rs-upload-slot")


def upload_card(
    prefix: str,
    title: str,
    *,
    upload_label: Any = None,
    hint: Any = None,
    class_name: str = "mb-3 rs-section-card",
    include_data_rev: bool = True,
    include_historical: bool = True,
    library_page: str | None = None,
    library_only: bool = False,
) -> dbc.Card:
    """Standard current + optional historical upload controls.

    Set ``include_data_rev=False`` when ``{prefix}-data-rev`` already lives in the
    app layout (needed if another always-mounted store shares a callback with it).

    ``library_page`` is an export_library page key (``role_scores``, ``stats``,
    ``squad_finance``) to show a saved-file picker above the dropzone.

    When ``library_only`` is True, manual CSV dropzones are hidden and the page
    only loads files from the Uploads library (``library_page`` is required).

    Page logic should read ``{prefix}-parsed`` (current). Historical data is stored
    in ``{prefix}-parsed-historical`` for future comparison features.
    """
    if library_only and not library_page:
        raise ValueError("library_only=True requires library_page")
    if upload_label is None:
        upload_label = html.Div(["Drag a CSV here, or ", html.A("browse")])
    body_children: list = []
    if include_data_rev:
        body_children.append(
            dcc.Store(id=f"{prefix}-data-rev", data={"n": 0, "replaced": False})
        )
    body_children.append(html.Div(id=f"{prefix}-pulse-token", hidden=True))
    if include_historical:
        body_children.append(
            html.Div(
                [
                    _upload_slot(
                        prefix,
                        "current",
                        title="Current export",
                        subtitle=(
                            "Active data used by this page. Choose a saved file below."
                            if library_only
                            else "Active data used by this page."
                        ),
                        upload_label=upload_label,
                        library_page=library_page,
                        library_only=library_only,
                    ),
                    _upload_slot(
                        prefix,
                        "hist",
                        title="Historical export",
                        subtitle=(
                            "Comparison only — does not replace current. Choose a saved file below."
                            if library_only
                            else "Comparison only — does not replace current."
                        ),
                        upload_label=upload_label,
                        library_page=library_page,
                        library_only=library_only,
                    ),
                ],
                className="rs-upload-dual",
            )
        )
        if library_page:
            body_children.append(
                html.P(
                    [
                        (
                            "Choose a saved file for each slot (Ready = fast load from "
                            "precompute). Clear removes only that side from the page "
                            "cache. Add or compute files on "
                            if library_only
                            else (
                                "Selecting a saved file loads that slot. Labels show "
                                "cache status (Ready / Stale / Not computed). Clear "
                                "removes only that side’s export from the page cache. "
                                "Manage files on "
                            )
                        ),
                        html.A("Uploads", href="/uploads"),
                        ".",
                    ],
                    className="rs-lib-hint text-muted small mb-0 mt-2",
                )
            )
            if library_page in {"role_scores", "stats"}:
                body_children.append(
                    dcc.Interval(
                        id=f"{prefix}-lib-options-tick",
                        interval=250,
                        n_intervals=0,
                        max_intervals=1,
                    )
                )
    else:
        body_children.append(
            _upload_slot(
                prefix,
                "current",
                title="Export" if not library_only else "Saved export",
                subtitle=(
                    "Active data used by this page. Choose a saved file below."
                    if library_only
                    else "Active data used by this page."
                ),
                upload_label=upload_label,
                library_page=library_page,
                library_only=library_only,
            )
        )
        if library_page:
            body_children.append(
                html.P(
                    [
                        (
                            "Choose a saved file to load (Ready = fast load from "
                            "precompute). Clear removes it from this page’s cache. "
                            "Add or compute files on "
                            if library_only
                            else (
                                "Selecting a saved file loads it. Labels show cache "
                                "status (Ready / Stale / Not computed). Clear removes "
                                "the export from this page’s cache. Manage files on "
                            )
                        ),
                        html.A("Uploads", href="/uploads"),
                        ".",
                    ],
                    className="rs-lib-hint text-muted small mb-0 mt-2",
                )
            )
            if library_page in {"role_scores", "stats"}:
                body_children.append(
                    dcc.Interval(
                        id=f"{prefix}-lib-options-tick",
                        interval=250,
                        n_intervals=0,
                        max_intervals=1,
                    )
                )
    if hint is not None:
        body_children.append(hint)
    return dbc.Card(
        [dbc.CardHeader(title), dbc.CardBody(body_children)],
        className=class_name,
    )


def pattern_matching_stubs(
    prefix: str,
    stubs: Sequence[dict[str, str]],
) -> html.Div:
    """Hidden buttons so Dash pattern-matching callbacks always have a target.

    Each stub is a dict of id fields besides ``type``, e.g.
    ``{"type": "pos", "pos": "_"}`` → ``{"type": f"{prefix}-pos", "pos": "_"}``.
    """
    buttons = []
    for stub in stubs:
        stub = dict(stub)
        kind = stub.pop("type")
        buttons.append(
            html.Button(id={"type": f"{prefix}-{kind}", **stub}, n_clicks=0)
        )
    return html.Div(buttons, hidden=True)


def shortlist_busy_overlay(prefix: str) -> html.Div:
    """Blocking refresh overlay; toggle ``is-on`` via shortlist-busy clientside callbacks.

    Place as the last child of the shortlist host (``pulse_ids`` target) and keep
    ``rs-shortlist-busy-host`` on that host.
    """
    return html.Div(
        [
            html.Div(className="rs-shortlist-busy-spinner", **{"aria-hidden": "true"}),
            html.Span("Updating shortlist…", className="rs-shortlist-busy-label"),
        ],
        id=f"{prefix}-shortlist-busy",
        className="rs-shortlist-busy",
        role="status",
        **{"aria-live": "polite"},
    )


def hist_block(
    prefix: str,
    *,
    blank_figure,
    toggle_title: str | None = None,
) -> html.Div:
    """Show/hide score-distribution chart block."""
    button_props = {}
    if toggle_title:
        button_props["buttonProps"] = {"title": toggle_title}
    return html.Div(
        [
            dmc.Button(
                "Show score distribution",
                id=f"{prefix}-hist-toggle",
                n_clicks=0,
                variant="light",
                className="rs-hist-toggle",
                **button_props,
            ),
            html.Div(
                dcc.Graph(
                    id=f"{prefix}-hist",
                    figure=blank_figure,
                    config={"displayModeBar": False},
                    responsive=True,
                    style={"width": "100%", "height": "240px"},
                ),
                id=f"{prefix}-hist-wrap",
                className="rs-hist-wrap",
                hidden=True,
            ),
        ],
        className="rs-hist-block",
    )


# ── Callback registrars ──────────────────────────────────────────────────────


def register_upload_callbacks(
    prefix: str,
    *,
    parse_fn: ParseFn,
    pack_store: bool = False,
    reveal_ids: Sequence[str] | None = None,
    pulse_ids: Sequence[str] | None = None,
    busy_ready_id: str | None = None,
    busy_ready_prop: str = "data",
    bad_file_message: str = "Upload a CSV export from Football Manager.",
    decode_strict: bool = False,
    catch_exceptions: bool = False,
    include_historical: bool = True,
) -> None:
    """Parse Upload / Replace into ``{prefix}-parsed`` and toggle upload UI.

    When ``reveal_ids`` is set (e.g. ``["st-main"]``), those components' ``hidden``
    become False on success and True on error. Leave empty for pages that use a
    separate workflow gate (Role scores).

    ``pulse_ids`` are DOM ids that show a blocking shortlist refresh overlay while
    an export is loading, replacing, or clearing, until the shortlist finishes
    updating. ``busy_ready_id`` / ``busy_ready_prop`` name the component that
    signals the shortlist is done (default: ``{prefix}-table`` ``data``).

    With ``include_historical`` (default), also wires a second slot into
    ``{prefix}-parsed-historical`` for comparison exports. Page callbacks should
    keep using ``parsed_players({prefix}-parsed)`` for active data.
    """
    _register_upload_slot(
        prefix,
        slot="current",
        parse_fn=parse_fn,
        pack_store=pack_store,
        reveal_ids=reveal_ids,
        pulse_ids=pulse_ids,
        busy_ready_id=busy_ready_id,
        busy_ready_prop=busy_ready_prop,
        bad_file_message=bad_file_message,
        decode_strict=decode_strict,
        catch_exceptions=catch_exceptions,
        track_data_rev=True,
    )
    if include_historical:
        _register_upload_slot(
            prefix,
            slot="hist",
            parse_fn=parse_fn,
            pack_store=pack_store,
            reveal_ids=None,
            pulse_ids=None,
            bad_file_message=bad_file_message,
            decode_strict=decode_strict,
            catch_exceptions=catch_exceptions,
            track_data_rev=False,
            status_tag="Historical",
        )


def register_library_select_callbacks(
    prefix: str,
    *,
    parse_fn: ParseFn,
    library_page: str,
    pack_store: bool = False,
    reveal_ids: Sequence[str] | None = None,
    catch_exceptions: bool = False,
    include_historical: bool = True,
    library_only: bool = False,
) -> None:
    """Load saved library files on select; Clear wipes page session stores.

    When ``library_only`` is True, dropzone/replace wraps stay hidden after load
    and clear (manual upload UI is not used on the page).
    """
    reveal_ids = list(reveal_ids or [])

    def _wire_load(slot: str) -> None:
        if slot == "current":
            parsed_id = f"{prefix}-parsed"
            select_id = f"{prefix}-lib-select"
            status_id = f"{prefix}-upload-status"
            wrap_id = f"{prefix}-upload-wrap"
            replace_wrap_id = f"{prefix}-upload-replace-wrap"
            track_rev = True
            status_tag = None
        else:
            parsed_id = f"{prefix}-parsed-historical"
            select_id = f"{prefix}-lib-select-hist"
            status_id = f"{prefix}-upload-hist-status"
            wrap_id = f"{prefix}-upload-hist-wrap"
            replace_wrap_id = f"{prefix}-upload-hist-replace-wrap"
            track_rev = False
            status_tag = "Historical"

        slot_reveal = reveal_ids if slot == "current" else []
        load_outputs = [
            Output(parsed_id, "data", allow_duplicate=True),
            Output(status_id, "children", allow_duplicate=True),
            Output(wrap_id, "hidden", allow_duplicate=True),
            Output(replace_wrap_id, "hidden", allow_duplicate=True),
        ]
        if track_rev:
            load_outputs.append(
                Output(f"{prefix}-data-rev", "data", allow_duplicate=True)
            )
        load_outputs.extend(
            Output(rid, "hidden", allow_duplicate=True) for rid in slot_reveal
        )
        n_load = 4 + (1 if track_rev else 0) + len(slot_reveal)
        wrap_hidden_loaded = True
        replace_hidden_loaded = True if library_only else False

        def _already_loaded_row(parsed, file_id, entry, *, rev=None, _tag=None):
            """Reuse session data when remounting; only refresh status chrome."""
            import services.export_library as lib

            name = lib.display_label(entry)
            if pack_store:
                data = unpack_parsed(parsed) or {}
                count = int(parsed.get("n") or len(data.get("players") or []))
                name = data.get("filename") or parsed.get("filename") or name
            else:
                count = len((parsed or {}).get("players") or [])
                name = (parsed or {}).get("filename") or name
            row = [
                no_update,
                upload_status_bar(
                    count,
                    name,
                    replaced=True,
                    slot_label=_tag,
                ),
                wrap_hidden_loaded,
                replace_hidden_loaded,
            ]
            if track_rev:
                row.append(no_update)
            row.extend([False] * len(slot_reveal))
            return tuple(row)

        load_states = [State(parsed_id, "data")]
        if track_rev:
            load_states.insert(0, State(f"{prefix}-data-rev", "data"))

        @callback(
            *load_outputs,
            Input(select_id, "value"),
            *load_states,
            prevent_initial_call=True,
        )
        def _load_from_library(
            file_id,
            rev=None,
            parsed=None,
            _n_out=n_load,
            _reveal=slot_reveal,
            _tag=status_tag,
            _track_rev=track_rev,
        ):
            # Argument order: file_id, [rev,] parsed when track_rev else file_id, parsed
            if not _track_rev:
                parsed = rev
                rev = None
            if not file_id:
                return tuple([no_update] * _n_out)
            import services.export_library as lib

            try:
                entry = lib.get_file(file_id)
                if not entry:
                    raise FileNotFoundError("Saved file not found.")
                if library_page not in (entry.get("pages") or []):
                    raise ValueError(
                        "That file is not eligible for "
                        f"{lib.PAGE_LABELS.get(library_page, library_page)}."
                    )
                if (
                    isinstance(parsed, dict)
                    and parsed.get("file_id") == file_id
                    and _has_players(parsed)
                ):
                    return _already_loaded_row(
                        parsed, file_id, entry, rev=rev, _tag=_tag
                    )
                players = None
                cache_extra = {}
                try:
                    import services.upload_cache as upload_cache

                    if library_page == "role_scores":
                        hit = upload_cache.try_role_players(file_id)
                        if hit:
                            players, _cache = hit
                            cache_extra = {"from_cache": True}
                    elif library_page == "stats":
                        hit = upload_cache.try_stats_players(file_id)
                        if hit:
                            players, cache = hit
                            cache_extra = {
                                "from_cache": True,
                                "percentiles": (cache.get("stats") or {}).get(
                                    "percentiles"
                                )
                                or upload_cache.cached_stats_percentiles(file_id),
                            }
                except Exception:
                    players = None
                    cache_extra = {}
                if players is None:
                    text, entry = lib.read_text(file_id)
                    players = parse_fn(text)
                    cache_extra = {}
            except Exception as exc:
                if not catch_exceptions and not isinstance(
                    exc, (ValueError, FileNotFoundError, OSError)
                ):
                    raise
                row = [no_update, upload_error(str(exc)), no_update, no_update]
                if track_rev:
                    row.append(no_update)
                row.extend([no_update] * len(_reveal))
                return tuple(row)

            name = lib.display_label(entry)
            rev_payload = None
            if track_rev:
                prev_n = 0
                if isinstance(rev, dict):
                    prev_n = int(rev.get("n") or 0)
                elif rev:
                    prev_n = int(rev)
                rev_payload = {"n": prev_n + 1, "replaced": True}
            if pack_store:
                store = pack_parsed(players, name)
                if track_rev and rev_payload:
                    store["rev"] = rev_payload["n"]
            else:
                store = {"filename": name, "players": players}
                if track_rev and rev_payload:
                    store["rev"] = rev_payload["n"]
            store["file_id"] = file_id
            if cache_extra:
                store.update(cache_extra)
            row = [
                store,
                upload_status_bar(
                    len(players),
                    name,
                    replaced=True,
                    slot_label=_tag,
                ),
                True,
                True if library_only else False,
            ]
            if track_rev:
                row.append(rev_payload)
            row.extend([False] * len(_reveal))
            return tuple(row)

        sync_inputs = [Input(parsed_id, "data")]
        if library_page in {"role_scores", "stats"}:
            # Page remount does not re-fire session Store inputs; tick restores the
            # saved-file dropdown after navigating back with data still loaded.
            sync_inputs.append(Input(f"{prefix}-lib-options-tick", "n_intervals"))

        @callback(
            Output(select_id, "value", allow_duplicate=True),
            Output(status_id, "children", allow_duplicate=True),
            *sync_inputs,
            State(select_id, "value"),
            prevent_initial_call="initial_duplicate",
        )
        def _sync_lib_select_from_parsed(*args, _tag=status_tag):
            """Restore dropdown + status when navigating back with session data."""
            # args: parsed, [n_intervals,] current_value
            parsed = args[0] if args else None
            current_value = args[-1] if args else None
            if not isinstance(parsed, dict) or not _has_players(parsed):
                return no_update, no_update
            file_id = parsed.get("file_id")
            if not file_id:
                return no_update, no_update
            import services.export_library as lib

            entry = lib.get_file(file_id) or {}
            if pack_store:
                data = unpack_parsed(parsed) or {}
                count = int(parsed.get("n") or len(data.get("players") or []))
                name = (
                    data.get("filename")
                    or parsed.get("filename")
                    or lib.display_label(entry)
                    or "Saved file"
                )
            else:
                count = len(parsed.get("players") or [])
                name = parsed.get("filename") or lib.display_label(entry) or "Saved file"
            status = upload_status_bar(
                count,
                name,
                replaced=True,
                slot_label=_tag,
            )
            # Avoid re-firing load when the select already shows this file.
            if current_value == file_id:
                return no_update, status
            return file_id, status

    def _has_players(parsed) -> bool:
        if not parsed or not isinstance(parsed, dict):
            return False
        data = unpack_parsed(parsed) if pack_store else parsed
        if data and data.get("players"):
            return True
        # Packed / partial session payloads still count as a loaded export.
        return bool(parsed.get("players") or parsed.get("payload") or parsed.get("n"))

    _wire_load("current")
    if include_historical:
        _wire_load("hist")

    def _wire_clear(slot: str) -> None:
        if slot == "current":
            clear_id = f"{prefix}-lib-clear"
            parsed_id = f"{prefix}-parsed"
            status_id = f"{prefix}-upload-status"
            wrap_id = f"{prefix}-upload-wrap"
            replace_wrap_id = f"{prefix}-upload-replace-wrap"
            select_id = f"{prefix}-lib-select"
            upload_id = f"{prefix}-upload"
            replace_id = f"{prefix}-upload-replace"
            track_rev = True
            slot_reveal = reveal_ids
        else:
            clear_id = f"{prefix}-lib-clear-hist"
            parsed_id = f"{prefix}-parsed-historical"
            status_id = f"{prefix}-upload-hist-status"
            wrap_id = f"{prefix}-upload-hist-wrap"
            replace_wrap_id = f"{prefix}-upload-hist-replace-wrap"
            select_id = f"{prefix}-lib-select-hist"
            upload_id = f"{prefix}-upload-hist"
            replace_id = f"{prefix}-upload-hist-replace"
            track_rev = False
            slot_reveal = []

        clear_outputs = [
            Output(parsed_id, "data", allow_duplicate=True),
            Output(status_id, "children", allow_duplicate=True),
            Output(wrap_id, "hidden", allow_duplicate=True),
            Output(replace_wrap_id, "hidden", allow_duplicate=True),
            Output(select_id, "value", allow_duplicate=True),
            Output(upload_id, "contents", allow_duplicate=True),
            Output(replace_id, "contents", allow_duplicate=True),
            Output(upload_id, "filename", allow_duplicate=True),
            Output(replace_id, "filename", allow_duplicate=True),
        ]
        if track_rev:
            clear_outputs.append(
                Output(f"{prefix}-data-rev", "data", allow_duplicate=True)
            )
        clear_outputs.extend(
            Output(rid, "hidden", allow_duplicate=True) for rid in slot_reveal
        )
        n_clear = len(clear_outputs)

        @callback(
            *clear_outputs,
            Input(clear_id, "n_clicks"),
            *([State(f"{prefix}-data-rev", "data")] if track_rev else []),
            prevent_initial_call=True,
        )
        def _clear_slot(n_clicks, rev=None, _n_out=n_clear, _reveal=slot_reveal):
            if not n_clicks:
                return tuple([no_update] * _n_out)
            rev_payload = None
            if track_rev:
                prev_n = 0
                if isinstance(rev, dict):
                    prev_n = int(rev.get("n") or 0)
                elif rev:
                    prev_n = int(rev)
                rev_payload = {"n": prev_n + 1, "replaced": True}
            row: list = [
                None,
                [],
                True if library_only else False,
                True,
                None,
                None,
                None,
                None,
                None,
            ]
            if track_rev:
                row.append(rev_payload)
            row.extend([True] * len(_reveal))
            return tuple(row)

        @callback(
            Output(clear_id, "disabled"),
            Input(parsed_id, "data"),
            Input(status_id, "children"),
        )
        def _sync_clear_enabled(parsed, _status, _pack=pack_store):
            return not _has_players(parsed)

    _wire_clear("current")
    if include_historical:
        _wire_clear("hist")

    if library_only:
        # Upload callbacks normally own the busy overlay; library-only pages need it here.
        _register_shortlist_busy(prefix, [])

    # Refresh dropdown labels (Ready / Stale / …) shortly after mount so status
    # matches Uploads even if layout was built before a recent Compute.
    if library_page in {"role_scores", "stats"}:
        refresh_outputs = [Output(f"{prefix}-lib-select", "data")]
        if include_historical:
            refresh_outputs.append(Output(f"{prefix}-lib-select-hist", "data"))

        @callback(
            *refresh_outputs,
            Input(f"{prefix}-lib-options-tick", "n_intervals"),
            prevent_initial_call=False,
        )
        def _refresh_lib_options(_n, _page=library_page, _hist=include_historical):
            import services.export_library as lib

            opts = lib.select_options(page=_page)
            if _hist:
                return opts, opts
            return (opts,)


def _register_upload_slot(
    prefix: str,
    *,
    slot: str,
    parse_fn: ParseFn,
    pack_store: bool,
    reveal_ids: Sequence[str] | None,
    pulse_ids: Sequence[str] | None,
    bad_file_message: str,
    decode_strict: bool,
    catch_exceptions: bool,
    track_data_rev: bool,
    status_tag: str | None = None,
    busy_ready_id: str | None = None,
    busy_ready_prop: str = "data",
) -> None:
    reveal_ids = list(reveal_ids or [])
    pulse_ids = list(pulse_ids or [])
    if slot == "current":
        parsed_id = f"{prefix}-parsed"
        upload_id = f"{prefix}-upload"
        replace_id = f"{prefix}-upload-replace"
        wrap_id = f"{prefix}-upload-wrap"
        replace_wrap_id = f"{prefix}-upload-replace-wrap"
        status_id = f"{prefix}-upload-status"
    else:
        parsed_id = f"{prefix}-parsed-historical"
        upload_id = f"{prefix}-upload-hist"
        replace_id = f"{prefix}-upload-hist-replace"
        wrap_id = f"{prefix}-upload-hist-wrap"
        replace_wrap_id = f"{prefix}-upload-hist-replace-wrap"
        status_id = f"{prefix}-upload-hist-status"

    outputs = [
        Output(parsed_id, "data"),
        Output(status_id, "children"),
        Output(wrap_id, "hidden"),
        Output(replace_wrap_id, "hidden"),
    ]
    if track_data_rev:
        outputs.append(Output(f"{prefix}-data-rev", "data"))
    outputs.extend(Output(rid, "hidden") for rid in reveal_ids)
    n_base = 4 + (1 if track_data_rev else 0)

    def _fail(message: str):
        row = [None, upload_error(message), False, True]
        if track_data_rev:
            row.append(no_update)
        row.extend([True] * len(reveal_ids))
        return tuple(row)

    def _ok(store_data, count: int, filename: str, rev: dict | None, *, replaced: bool):
        row = [
            store_data,
            upload_status_bar(
                count,
                filename,
                replaced=replaced,
                slot_label=status_tag,
            ),
            True,
            False,
        ]
        if track_data_rev:
            row.append(rev)
        row.extend([False] * len(reveal_ids))
        return tuple(row)

    def _noop():
        return tuple([no_update] * (n_base + len(reveal_ids)))

    @callback(
        *outputs,
        Input(upload_id, "contents"),
        Input(replace_id, "contents"),
        State(upload_id, "filename"),
        State(replace_id, "filename"),
        *([State(f"{prefix}-data-rev", "data")] if track_data_rev else []),
        prevent_initial_call=True,
    )
    def _on_upload(upload_contents, replace_contents, upload_name, replace_name, rev=None):
        replaced = ctx.triggered_id == replace_id
        if replaced:
            contents = replace_contents
            name = replace_name or "upload.csv"
        elif ctx.triggered_id == upload_id:
            contents = upload_contents
            name = upload_name or "upload.csv"
        else:
            contents = replace_contents or upload_contents
            name = (replace_name or upload_name) or "upload.csv"
        if not contents:
            return _noop()
        if not name.lower().endswith(".csv"):
            return _fail(bad_file_message)
        try:
            players = parse_fn(decode_upload(contents, strict=decode_strict))
        except Exception as exc:
            if not catch_exceptions and not isinstance(exc, ValueError):
                raise
            return _fail(str(exc))
        rev_payload = None
        if track_data_rev:
            prev_n = 0
            if isinstance(rev, dict):
                prev_n = int(rev.get("n") or 0)
            elif rev:
                prev_n = int(rev)
            rev_payload = {"n": prev_n + 1, "replaced": replaced}
        if pack_store:
            store = pack_parsed(players, name)
            if track_data_rev and rev_payload:
                store["rev"] = rev_payload["n"]
        else:
            store = {"filename": name, "players": players}
            if track_data_rev and rev_payload:
                store["rev"] = rev_payload["n"]
        return _ok(store, len(players), name, rev_payload, replaced=replaced)

    restore_outputs = [
        Output(status_id, "children", allow_duplicate=True),
        Output(wrap_id, "hidden", allow_duplicate=True),
        Output(replace_wrap_id, "hidden", allow_duplicate=True),
    ]
    restore_outputs.extend(
        Output(rid, "hidden", allow_duplicate=True) for rid in reveal_ids
    )

    @callback(
        *restore_outputs,
        Input(f"{prefix}-hydrate-tick", "n_intervals"),
        State(parsed_id, "data"),
        prevent_initial_call="initial_duplicate",
    )
    def _restore_upload_ui(_tick, parsed):
        """Restore upload chrome from session on page load only."""
        data = unpack_parsed(parsed) if pack_store else parsed
        if not data or not data.get("players"):
            return tuple([no_update] * (3 + len(reveal_ids)))
        filename = data.get("filename") or "export.csv"
        row = [
            upload_status_bar(
                len(data["players"]),
                filename,
                slot_label=status_tag,
            ),
            True,
            False,
        ]
        row.extend([False] * len(reveal_ids))
        return tuple(row)

    if track_data_rev and pulse_ids:
        _register_shortlist_busy(
            prefix,
            pulse_ids,
            ready_id=busy_ready_id,
            ready_prop=busy_ready_prop,
        )


def _register_shortlist_busy(
    prefix: str,
    target_ids: Sequence[str],
    *,
    ready_id: str | None = None,
    ready_prop: str = "data",
) -> None:
    """Toggle ``{prefix}-shortlist-busy`` overlay during export load/clear.

    Uses a layout-owned overlay (see ``shortlist_busy_overlay``) so React re-renders
    do not wipe the spinner. ``target_ids`` is kept for call-site compatibility with
    ``pulse_ids``.
    """
    del target_ids
    overlay_id = f"{prefix}-shortlist-busy"
    status_id = f"{prefix}-upload-status"
    ready_id = ready_id or f"{prefix}-table"
    off_cls = "rs-shortlist-busy"

    clientside_callback(
        f"""
        function(clearClicks, libValue, uploadContents, replaceContents) {{
            var trig = window.dash_clientside.callback_context.triggered;
            if (!trig || !trig.length) {{
                return window.dash_clientside.no_update;
            }}
            var prop = trig[0].prop_id || "";
            if (prop.indexOf("n_clicks") !== -1 && !clearClicks) {{
                return window.dash_clientside.no_update;
            }}
            if (prop.indexOf("contents") !== -1 && !trig[0].value) {{
                return window.dash_clientside.no_update;
            }}
            window.__rsShortlistBusyAt = window.__rsShortlistBusyAt || {{}};
            window.__rsShortlistBusyAt["{prefix}"] = Date.now();
            return "rs-shortlist-busy is-on t-" + String(Date.now());
        }}
        """,
        Output(overlay_id, "className"),
        Input(f"{prefix}-lib-clear", "n_clicks"),
        Input(f"{prefix}-lib-select", "value"),
        Input(f"{prefix}-upload", "contents"),
        Input(f"{prefix}-upload-replace", "contents"),
        prevent_initial_call=True,
    )

    clientside_callback(
        f"""
        function(rev) {{
            if (!rev || !rev.n) {{
                return window.dash_clientside.no_update;
            }}
            var status = document.getElementById("{status_id}");
            if (rev.replaced && status) {{
                status.classList.remove("rs-upload-status-flash");
                void status.offsetWidth;
                status.classList.add("rs-upload-status-flash");
            }}
            // Do not toggle the overlay here: table-ready hide often runs in the
            // same update as data-rev and would clear a show from this callback.
            return window.dash_clientside.no_update;
        }}
        """,
        Output(f"{prefix}-pulse-token", "children"),
        Input(f"{prefix}-data-rev", "data"),
        prevent_initial_call=True,
    )

    clientside_callback(
        f"""
        function(_ready) {{
            var el = document.getElementById("{overlay_id}");
            if (!el || el.className.indexOf("is-on") === -1) {{
                return window.dash_clientside.no_update;
            }}
            return "{off_cls}";
        }}
        """,
        Output(overlay_id, "className", allow_duplicate=True),
        Input(ready_id, ready_prop),
        prevent_initial_call=True,
    )

    clientside_callback(
        f"""
        function(_statusChildren) {{
            var status = document.getElementById("{status_id}");
            if (!(status && status.querySelector(".rs-upload-error"))) {{
                return window.dash_clientside.no_update;
            }}
            return "{off_cls}";
        }}
        """,
        Output(overlay_id, "className", allow_duplicate=True),
        Input(status_id, "children"),
        prevent_initial_call=True,
    )


def register_pos_foot_callbacks(
    prefix: str,
    *,
    pos_store: str | None = None,
    foot_store: str | None = None,
    pos_id_attr: str = "key",
    pos_button_type: str | None = None,
    foot_button_type: str | None = None,
) -> None:
    """Toggle position-card and footedness filter stores.

    Role scores uses ``pos_id_attr="pos"`` and stores ``rs-pos-filter`` /
    ``rs-foot-filter``. Stats uses ``pos_id_attr="key"`` and ``st-pos`` / ``st-foot``.
    """
    pos_store = pos_store or f"{prefix}-pos"
    foot_store = foot_store or f"{prefix}-foot"
    pos_type = pos_button_type or f"{prefix}-pos"
    foot_type = foot_button_type or f"{prefix}-foot"

    @callback(
        Output(pos_store, "data"),
        Input({"type": pos_type, pos_id_attr: ALL}, "n_clicks"),
        State(pos_store, "data"),
        prevent_initial_call=True,
    )
    def _set_pos(n_clicks, current):
        if not ctx.triggered_id or not clicked(n_clicks):
            return no_update
        key = ctx.triggered_id.get(pos_id_attr)
        if key == "_":
            return no_update
        return key or current or "all"

    @callback(
        Output(foot_store, "data"),
        Input({"type": foot_type, "foot": ALL}, "n_clicks"),
        State(foot_store, "data"),
        prevent_initial_call=True,
    )
    def _set_foot(n_clicks, current):
        if not ctx.triggered_id or not clicked(n_clicks):
            return no_update
        chosen = ctx.triggered_id.get("foot")
        if chosen == "_":
            return no_update
        return "" if current == chosen else chosen


def register_marks_callbacks(
    prefix: str,
    *,
    marked_store: str | None = None,
    clear_button: str | None = None,
    parsed_id: str | None = None,
    row_key_fn: RowKeyFn | None = None,
    clear_on_upload: bool = True,
) -> None:
    """Sync DataTable ``selected_row_ids`` with a marked-keys store.

    Pages must put a stable ``id`` (and ideally ``_key``) on each table row.
    """
    marked_store = marked_store or f"{prefix}-marked"
    clear_button = clear_button or f"{prefix}-clear-marks"
    parsed_id = parsed_id or f"{prefix}-parsed"
    key_fn = row_key_fn or default_row_key

    @callback(
        Output(marked_store, "data", allow_duplicate=True),
        Input(f"{prefix}-table", "selected_row_ids"),
        State(f"{prefix}-table", "data"),
        State(marked_store, "data"),
        prevent_initial_call=True,
    )
    def _sync_marks(selected_ids, table_data, marked):
        table_data = table_data or []
        keys_on_page = [key_fn(row) for row in table_data]
        keys_on_page = [key for key in keys_on_page if key]
        marked_set = set(as_list(marked))
        expected = {key for key in keys_on_page if key in marked_set}
        selected = {str(key) for key in (selected_ids or []) if key}
        if selected == expected:
            return no_update
        marked_set -= set(keys_on_page)
        marked_set |= selected
        return sorted(marked_set)

    @callback(
        Output(marked_store, "data", allow_duplicate=True),
        Input(clear_button, "n_clicks"),
        prevent_initial_call=True,
    )
    def _clear_marks(n_clicks):
        if not n_clicks:
            return no_update
        return []

    if clear_on_upload:

        @callback(
            Output(marked_store, "data", allow_duplicate=True),
            Input(parsed_id, "data"),
            State(marked_store, "data"),
            prevent_initial_call=True,
        )
        def _clear_marks_on_upload(_parsed, marked):
            if not as_list(marked):
                return no_update
            return []


def register_hist_toggle(
    prefix: str,
    *,
    use_open_store: bool = False,
) -> None:
    """Toggle the hist wrap. Role scores also mirrors state into ``{prefix}-hist-open``."""
    if use_open_store:

        @callback(
            Output(f"{prefix}-hist-open", "data"),
            Output(f"{prefix}-hist-wrap", "hidden"),
            Output(f"{prefix}-hist-toggle", "children"),
            Input(f"{prefix}-hist-toggle", "n_clicks"),
            State(f"{prefix}-hist-open", "data"),
            prevent_initial_call=True,
        )
        def _toggle_hist(_clicks, opened):
            opened = not bool(opened)
            return (
                opened,
                not opened,
                "Hide score distribution" if opened else "Show score distribution",
            )

    else:

        @callback(
            Output(f"{prefix}-hist-wrap", "hidden"),
            Output(f"{prefix}-hist-toggle", "children"),
            Input(f"{prefix}-hist-toggle", "n_clicks"),
            State(f"{prefix}-hist-wrap", "hidden"),
        )
        def _toggle_hist(n, hidden):
            if not n:
                return True, "Show score distribution"
            opened = bool(hidden)
            return (not opened), (
                "Hide score distribution" if opened else "Show score distribution"
            )
