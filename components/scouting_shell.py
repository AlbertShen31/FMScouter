"""Shared upload → filter → table → hist → marks plumbing for scouting pages.

Layout builders and callback registrars used by Role scores and Player stats.
Domain scoring / column builders stay page-local.

Typical IDs (``prefix`` e.g. ``rs`` / ``st``):

- ``{prefix}-upload``, ``{prefix}-upload-replace``, ``{prefix}-upload-wrap``,
  ``{prefix}-upload-replace-wrap``, ``{prefix}-upload-status``
- ``{prefix}-parsed`` (often declared in ``app.py`` as a session store)
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


def upload_status_bar(count: int, filename: str, *, replaced: bool = False) -> list:
    if replaced:
        lead = html.Span("Replaced", className="rs-upload-replaced")
        count_label = f"{count:,} players"
    else:
        lead = html.Span("✓", className="rs-upload-ok")
        count_label = f"{count:,} players loaded"
    return [
        lead,
        html.Span(count_label, className="rs-upload-count"),
        html.Span("·", className="rs-upload-sep"),
        html.Span(filename, className="rs-upload-name", title=filename),
        html.Span("·", className="rs-upload-sep"),
    ]


def upload_error(message: str) -> html.Div:
    return html.Div(message, className="rs-upload-error")


def default_row_key(row: dict) -> str:
    return str(row.get("id") or row.get("_key") or "").strip()


# ── Layout builders ──────────────────────────────────────────────────────────


def upload_card(
    prefix: str,
    title: str,
    *,
    upload_label: Any = None,
    hint: Any = None,
    class_name: str = "mb-3 rs-section-card",
) -> dbc.Card:
    """Standard upload + status + Replace control."""
    if upload_label is None:
        upload_label = html.Div(["Drag a CSV here, or ", html.A("browse")])
    body_children: list = [
        dcc.Store(id=f"{prefix}-data-rev", data={"n": 0, "replaced": False}),
        html.Div(id=f"{prefix}-pulse-token", hidden=True),
        html.Div(
            dcc.Upload(
                id=f"{prefix}-upload",
                children=upload_label,
                className="rs-upload",
                multiple=False,
            ),
            id=f"{prefix}-upload-wrap",
        ),
        html.Div(
            [
                html.Div(id=f"{prefix}-upload-status", className="rs-upload-status"),
                html.Div(
                    dcc.Upload(
                        id=f"{prefix}-upload-replace",
                        children=html.Span(
                            "Replace file",
                            className="rs-upload-replace",
                        ),
                        className="rs-upload-replace-btn",
                        multiple=False,
                    ),
                    id=f"{prefix}-upload-replace-wrap",
                    hidden=True,
                    title="Choose a different CSV to refresh the shortlist",
                ),
            ],
            className="rs-upload-status-row",
        ),
    ]
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
    bad_file_message: str = "Upload a CSV export from Football Manager.",
    decode_strict: bool = False,
    catch_exceptions: bool = False,
) -> None:
    """Parse Upload / Replace into ``{prefix}-parsed`` and toggle upload UI.

    When ``reveal_ids`` is set (e.g. ``["st-main"]``), those components' ``hidden``
    become False on success and True on error. Leave empty for pages that use a
    separate workflow gate (Role scores).

    ``pulse_ids`` are DOM ids flashed when a file is replaced so the shortlist
    refresh is obvious.
    """
    reveal_ids = list(reveal_ids or [])
    pulse_ids = list(pulse_ids or [])
    parsed_id = f"{prefix}-parsed"
    outputs = [
        Output(parsed_id, "data"),
        Output(f"{prefix}-upload-status", "children"),
        Output(f"{prefix}-upload-wrap", "hidden"),
        Output(f"{prefix}-upload-replace-wrap", "hidden"),
        Output(f"{prefix}-data-rev", "data"),
    ]
    outputs.extend(Output(rid, "hidden") for rid in reveal_ids)
    n_base = 5

    def _fail(message: str):
        row = [None, upload_error(message), False, True, no_update]
        row.extend([True] * len(reveal_ids))
        return tuple(row)

    def _ok(store_data, count: int, filename: str, rev: dict, *, replaced: bool):
        row = [
            store_data,
            upload_status_bar(count, filename, replaced=replaced),
            True,
            False,
            rev,
        ]
        row.extend([False] * len(reveal_ids))
        return tuple(row)

    def _noop():
        return tuple([no_update] * (n_base + len(reveal_ids)))

    @callback(
        *outputs,
        Input(f"{prefix}-upload", "contents"),
        Input(f"{prefix}-upload-replace", "contents"),
        State(f"{prefix}-upload", "filename"),
        State(f"{prefix}-upload-replace", "filename"),
        State(f"{prefix}-data-rev", "data"),
        prevent_initial_call=True,
    )
    def _on_upload(upload_contents, replace_contents, upload_name, replace_name, rev):
        replaced = ctx.triggered_id == f"{prefix}-upload-replace"
        if replaced:
            contents = replace_contents
            name = replace_name or "upload.csv"
        elif ctx.triggered_id == f"{prefix}-upload":
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
        prev_n = 0
        if isinstance(rev, dict):
            prev_n = int(rev.get("n") or 0)
        elif rev:
            prev_n = int(rev)
        new_rev = {"n": prev_n + 1, "replaced": replaced}
        if pack_store:
            store = pack_parsed(players, name)
            # Force Store clients to treat each upload as new data.
            store["rev"] = new_rev["n"]
        else:
            store = {"filename": name, "players": players, "rev": new_rev["n"]}
        return _ok(store, len(players), name, new_rev, replaced=replaced)

    restore_outputs = [
        Output(f"{prefix}-upload-status", "children", allow_duplicate=True),
        Output(f"{prefix}-upload-wrap", "hidden", allow_duplicate=True),
        Output(f"{prefix}-upload-replace-wrap", "hidden", allow_duplicate=True),
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
        """Restore upload chrome from session on page load only.

        Do not also Input ``parsed`` — that races the upload callback and can
        clobber the Replaced status (and confuse shortlist refresh timing).
        """
        data = unpack_parsed(parsed) if pack_store else parsed
        if not data or not data.get("players"):
            return tuple([no_update] * (3 + len(reveal_ids)))
        filename = data.get("filename") or "export.csv"
        row = [upload_status_bar(len(data["players"]), filename), True, False]
        row.extend([False] * len(reveal_ids))
        return tuple(row)

    if pulse_ids:
        targets_js = ", ".join(f'"{tid}"' for tid in pulse_ids)
        clientside_callback(
            f"""
            function(rev) {{
                if (!rev || !rev.n || !rev.replaced) {{
                    return window.dash_clientside.no_update;
                }}
                const status = document.getElementById("{prefix}-upload-status");
                if (status) {{
                    status.classList.remove("rs-upload-status-flash");
                    void status.offsetWidth;
                    status.classList.add("rs-upload-status-flash");
                }}
                [{targets_js}].forEach(function(id) {{
                    const el = document.getElementById(id);
                    if (!el || el.hidden) return;
                    el.classList.remove("rs-data-flash");
                    void el.offsetWidth;
                    el.classList.add("rs-data-flash");
                }});
                return String(rev.n);
            }}
            """,
            Output(f"{prefix}-pulse-token", "children"),
            Input(f"{prefix}-data-rev", "data"),
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
