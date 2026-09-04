"""Formations page: save up to 11 hybrid IP/OOP role slots."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon
import services.formations as fm
from scoring.role_scorer import canonical_role_ref, combo_meta, role_options

register_page(__name__, path="/formations", name="Formations")

FM_PAGE_TIP = (
    "Save up to 11 hybrid roles. Slot names update from IP positions (duplicate CBs become "
    "RCB/LCB). IP position filters both role lists unless you set a separate OOP position. "
    "Optional left/right foot minimum strengths gate which players Profiles can load into a "
    "slot. Save writes a new file if none is selected."
)
FM_HYBRID_SLOTS_TIP = (
    "IP position is required. Leave OOP position blank to use the IP position for both role lists. "
    "Roles that span position buckets (e.g. Wing Back as FB or WB) appear once per bucket in the "
    "role lists; the slot position picks the default bucket. Left/right foot picks a minimum "
    "strength (Weak–Very strong); leave as None for no gate."
)

POS_OPTIONS = fm.position_options()
FOOT_REQ_OPTIONS = fm.foot_req_options()
_FORM_OUTPUT_COUNT = 15


def _slot_row(index: int, slot: dict) -> html.Div:
    ip_pos = slot.get("ip_pos") or fm.DEFAULT_SLOT_POSITIONS[index]
    oop_pos = slot.get("oop_pos") or None
    ip_group, oop_group = fm.role_filter_groups(ip_pos, oop_pos)
    label = str(slot.get("label") or "").strip() or "—"
    foot_left = slot.get("foot_left") or fm.FOOT_REQ_NONE
    foot_right = slot.get("foot_right") or fm.FOOT_REQ_NONE
    return html.Div(
        [
            html.Span(str(index + 1), className="fm-slot-index"),
            html.Span(
                label,
                id={"type": "fm-slot-label", "index": index},
                className="fm-slot-label",
                title="Auto slot name from IP positions",
            ),
            dmc.Select(
                id={"type": "fm-slot-ip-pos", "index": index},
                data=POS_OPTIONS,
                value=ip_pos,
                placeholder="IP pos",
                clearable=False,
                searchable=False,
                className="fm-slot-pos",
            ),
            dmc.Select(
                id={"type": "fm-slot-oop-pos", "index": index},
                data=POS_OPTIONS,
                value=oop_pos,
                placeholder="Same as IP",
                clearable=True,
                searchable=False,
                className="fm-slot-pos",
            ),
            dmc.Select(
                id={"type": "fm-slot-ip", "index": index},
                data=role_options(phase="IP", group=ip_group, keep=slot.get("ip")) or [],
                value=slot.get("ip") or None,
                placeholder="In possession role",
                clearable=True,
                searchable=True,
                className="fm-slot-role",
            ),
            dmc.Select(
                id={"type": "fm-slot-oop", "index": index},
                data=role_options(phase="OOP", group=oop_group, keep=slot.get("oop")) or [],
                value=slot.get("oop") or None,
                placeholder="Out of possession role",
                clearable=True,
                searchable=True,
                className="fm-slot-role",
            ),
            dmc.Select(
                id={"type": "fm-slot-foot-left", "index": index},
                data=FOOT_REQ_OPTIONS,
                value=foot_left,
                placeholder="L foot",
                clearable=False,
                searchable=False,
                className="fm-slot-foot",
            ),
            dmc.Select(
                id={"type": "fm-slot-foot-right", "index": index},
                data=FOOT_REQ_OPTIONS,
                value=foot_right,
                placeholder="R foot",
                clearable=False,
                searchable=False,
                className="fm-slot-foot",
            ),
            html.Div(id={"type": "fm-slot-preview", "index": index}, className="fm-slot-preview"),
        ],
        className="fm-slot-row",
    )


def _slot_values(formation: dict) -> tuple[list, list, list, list, list, list]:
    slots = formation.get("slots") or []
    ip_pos = [slot.get("ip_pos") or None for slot in slots]
    oop_pos = [slot.get("oop_pos") or None for slot in slots]
    ips = [slot.get("ip") or None for slot in slots]
    oops = [slot.get("oop") or None for slot in slots]
    foot_left = [slot.get("foot_left") or fm.FOOT_REQ_NONE for slot in slots]
    foot_right = [slot.get("foot_right") or fm.FOOT_REQ_NONE for slot in slots]
    return ip_pos, oop_pos, ips, oops, foot_left, foot_right


def _by_index(specs, values) -> dict[int, object]:
    mapped = {}
    for spec, value in zip(specs or [], values or []):
        mapped[spec["id"]["index"]] = value
    return mapped


def _collect_slots(ip_pos, oop_pos, ips, oops, foot_left, foot_right) -> list[dict]:
    specs = ctx.states_list[-6:] if ctx.states_list else [[], [], [], [], [], []]
    ip_pos_map = _by_index(specs[0] if len(specs) > 0 else [], ip_pos)
    oop_pos_map = _by_index(specs[1] if len(specs) > 1 else [], oop_pos)
    ip_map = _by_index(specs[2] if len(specs) > 2 else [], ips)
    oop_map = _by_index(specs[3] if len(specs) > 3 else [], oops)
    foot_left_map = _by_index(specs[4] if len(specs) > 4 else [], foot_left)
    foot_right_map = _by_index(specs[5] if len(specs) > 5 else [], foot_right)
    slots = []
    for index in range(fm.MAX_SLOTS):
        slots.append(
            {
                "ip_pos": ip_pos_map.get(index) or "",
                "oop_pos": oop_pos_map.get(index) or "",
                "ip": ip_map.get(index) or "",
                "oop": oop_map.get(index) or "",
                "foot_left": foot_left_map.get(index) or fm.FOOT_REQ_NONE,
                "foot_right": foot_right_map.get(index) or fm.FOOT_REQ_NONE,
            }
        )
    return slots


def _draft(
    name, shape, notes, ip_pos, oop_pos, ips, oops, foot_left, foot_right, pack_id=""
) -> dict:
    return {
        "id": pack_id,
        "name": name,
        "shape": shape,
        "notes": notes,
        "slots": _collect_slots(ip_pos, oop_pos, ips, oops, foot_left, foot_right),
    }


def _form_outputs(formation: dict, status: str):
    ip_pos, oop_pos, ips, oops, foot_left, foot_right = _slot_values(formation)
    pack_id = formation.get("id") or None
    has_pack = bool(pack_id)
    return (
        fm.pack_options(),
        pack_id,
        formation.get("name") or "New formation",
        formation.get("shape") or "",
        formation.get("notes") or "",
        ip_pos,
        oop_pos,
        ips,
        oops,
        foot_left,
        foot_right,
        status,
        False,
        not has_pack,
        not has_pack,
    )


def layout():
    formation = fm.blank()
    return dbc.Container(
        [
            html.Div(
                [
                    html.H1("Formations", className="mb-0"),
                    *help_icon(FM_PAGE_TIP, "fm-help-page"),
                ],
                className="rs-page-title-row mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader("Saved formations"),
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dmc.Select(
                                            id="fm-pack",
                                            data=fm.pack_options(),
                                            value=None,
                                            placeholder="New formation",
                                            clearable=True,
                                            searchable=True,
                                        ),
                                        md=5,
                                    ),
                                    dbc.Col(
                                        [
                                            dmc.Button(
                                                "New",
                                                id="fm-new",
                                                variant="light",
                                                className="me-2",
                                            ),
                                            dmc.Button(
                                                "Save",
                                                id="fm-save",
                                                className="me-2",
                                            ),
                                            dmc.Button(
                                                "Duplicate",
                                                id="fm-duplicate",
                                                variant="light",
                                                className="me-2",
                                                disabled=True,
                                            ),
                                            dmc.Button(
                                                "Delete",
                                                id="fm-delete",
                                                variant="light",
                                                color="red",
                                                disabled=True,
                                            ),
                                        ],
                                        md=7,
                                    ),
                                ],
                                className="g-2 align-items-end",
                            ),
                            html.Div(
                                "Editing a new formation. Save to keep it.",
                                id="fm-status",
                                className="st-status mt-2",
                            ),
                        ]
                    ),
                ],
                className="mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader("Formation details"),
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dmc.TextInput(
                                            id="fm-name",
                                            label="Name",
                                            value=formation.get("name") or "New formation",
                                        ),
                                        md=6,
                                    ),
                                    dbc.Col(
                                        dmc.TextInput(
                                            id="fm-shape",
                                            label="Shape",
                                            value=formation.get("shape") or "",
                                            placeholder="4-2-3-1",
                                        ),
                                        md=6,
                                    ),
                                ],
                                className="g-3 mb-3",
                            ),
                            dmc.TextInput(
                                id="fm-notes",
                                label="Notes",
                                value=formation.get("notes") or "",
                                placeholder="Optional tactic notes",
                            ),
                        ]
                    ),
                ],
                className="mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader(
                        html.Div(
                            [
                                html.Span("Hybrid slots"),
                                *help_icon(FM_HYBRID_SLOTS_TIP, "fm-help-hybrid-slots"),
                            ],
                            className="rs-card-header-title",
                        ),
                        className="fm-slots-header",
                    ),
                    dbc.CardBody(
                        [
                            html.Div(
                                [
                                    html.Span("#", className="fm-slot-index"),
                                    html.Span("Slot", className="fm-slot-col-label"),
                                    html.Span("IP position", className="fm-slot-col-label"),
                                    html.Span("OOP position", className="fm-slot-col-label"),
                                    html.Span("In possession role", className="fm-slot-col-label"),
                                    html.Span("Out of possession role", className="fm-slot-col-label"),
                                    html.Span("Left foot", className="fm-slot-col-label"),
                                    html.Span("Right foot", className="fm-slot-col-label"),
                                    html.Span("Hybrid", className="fm-slot-col-label"),
                                ],
                                className="fm-slot-row fm-slot-head",
                            ),
                            html.Div(
                                [
                                    _slot_row(index, slot)
                                    for index, slot in enumerate(formation.get("slots") or [])
                                ],
                                id="fm-slots",
                                className="fm-slots",
                            ),
                        ]
                    ),
                ],
                className="mb-4",
            ),
        ],
        className="rs-page fm-page",
        fluid=True,
    )


@callback(
    Output({"type": "fm-slot-ip", "index": ALL}, "data"),
    Output({"type": "fm-slot-oop", "index": ALL}, "data"),
    Input({"type": "fm-slot-ip-pos", "index": ALL}, "value"),
    Input({"type": "fm-slot-oop-pos", "index": ALL}, "value"),
    State({"type": "fm-slot-ip", "index": ALL}, "value"),
    State({"type": "fm-slot-oop", "index": ALL}, "value"),
)
def filter_slot_roles(ip_pos, oop_pos, ips, oops):
    ip_pos_specs = ctx.inputs_list[0] if ctx.inputs_list else []
    oop_pos_map = _by_index(ctx.inputs_list[1] if len(ctx.inputs_list) > 1 else [], oop_pos)
    ip_pos_map = _by_index(ip_pos_specs, ip_pos)
    ip_keep = _by_index(ctx.states_list[0] if ctx.states_list else [], ips)
    oop_keep = _by_index(ctx.states_list[1] if len(ctx.states_list) > 1 else [], oops)
    ip_data = []
    oop_data = []
    for spec in ip_pos_specs:
        index = spec["id"]["index"]
        ip_group, oop_group = fm.role_filter_groups(
            ip_pos_map.get(index),
            oop_pos_map.get(index),
        )
        keep_ip = [ip_keep.get(index)] if ip_keep.get(index) else []
        keep_oop = [oop_keep.get(index)] if oop_keep.get(index) else []
        ip_data.append(role_options(phase="IP", group=ip_group, keep=keep_ip) or [])
        oop_data.append(role_options(phase="OOP", group=oop_group, keep=keep_oop) or [])
    return ip_data, oop_data


@callback(
    Output({"type": "fm-slot-ip", "index": ALL}, "value", allow_duplicate=True),
    Output({"type": "fm-slot-oop", "index": ALL}, "value", allow_duplicate=True),
    Input({"type": "fm-slot-ip-pos", "index": ALL}, "value"),
    Input({"type": "fm-slot-oop-pos", "index": ALL}, "value"),
    State({"type": "fm-slot-ip", "index": ALL}, "value"),
    State({"type": "fm-slot-oop", "index": ALL}, "value"),
    prevent_initial_call=True,
)
def sync_slot_role_buckets(ip_pos, oop_pos, ips, oops):
    """Re-pin cross-bucket role picks when the slot position changes."""
    ip_pos_specs = ctx.inputs_list[0] if ctx.inputs_list else []
    oop_pos_specs = ctx.inputs_list[1] if len(ctx.inputs_list) > 1 else []
    ip_pos_map = _by_index(ip_pos_specs, ip_pos)
    oop_pos_map = _by_index(oop_pos_specs, oop_pos)
    ip_map = _by_index(ctx.states_list[0] if ctx.states_list else [], ips)
    oop_map = _by_index(ctx.states_list[1] if len(ctx.states_list) > 1 else [], oops)
    new_ips = []
    new_oops = []
    changed = False
    for index in range(fm.MAX_SLOTS):
        ip_group = fm.group_for_position(ip_pos_map.get(index))
        oop_group = fm.group_for_position(oop_pos_map.get(index) or ip_pos_map.get(index))
        ip_value = ip_map.get(index) or ""
        oop_value = oop_map.get(index) or ""
        next_ip = canonical_role_ref(ip_value, position_group=ip_group) if ip_value else ""
        next_oop = canonical_role_ref(oop_value, position_group=oop_group) if oop_value else ""
        new_ips.append(next_ip or None)
        new_oops.append(next_oop or None)
        if next_ip != ip_value or next_oop != oop_value:
            changed = True
    if not changed:
        skip = [no_update] * fm.MAX_SLOTS
        return skip, skip
    return new_ips, new_oops


@callback(
    Output({"type": "fm-slot-label", "index": ALL}, "children"),
    Input({"type": "fm-slot-ip-pos", "index": ALL}, "value"),
)
def update_slot_labels(ip_pos):
    specs = ctx.inputs_list[0] if ctx.inputs_list else []
    pos_map = _by_index(specs, ip_pos)
    positions = [
        pos_map.get(index) or fm.DEFAULT_SLOT_POSITIONS[index]
        for index in range(fm.MAX_SLOTS)
    ]
    autos = fm.auto_slot_labels(positions)
    return [autos[spec["id"]["index"]] for spec in specs]


@callback(
    Output({"type": "fm-slot-preview", "index": ALL}, "children"),
    Input({"type": "fm-slot-ip", "index": ALL}, "value"),
    Input({"type": "fm-slot-oop", "index": ALL}, "value"),
)
def preview_slots(ips, oops):
    previews = []
    ip_specs = ctx.inputs_list[0] if ctx.inputs_list else []
    oop_by_index = _by_index(ctx.inputs_list[1] if len(ctx.inputs_list) > 1 else [], oops)
    ip_by_index = _by_index(ip_specs, ips)
    for spec in ip_specs:
        index = spec["id"]["index"]
        ip = ip_by_index.get(index) or ""
        oop = oop_by_index.get(index) or ""
        combos = fm.combos_from_formation({"slots": [{"ip": ip, "oop": oop}]})
        if combos:
            meta = combo_meta(combos[0]["ip"], combos[0]["oop"])
            previews.append(html.Span(meta["short_label"], className="fm-slot-hybrid"))
        elif ip or oop:
            previews.append(html.Span("Needs IP + OOP roles", className="fm-slot-warn"))
        else:
            previews.append(html.Span("Empty", className="fm-slot-empty"))
    return previews


@callback(
    Output("fm-pack", "data"),
    Output("fm-pack", "value"),
    Output("fm-name", "value"),
    Output("fm-shape", "value"),
    Output("fm-notes", "value"),
    Output({"type": "fm-slot-ip-pos", "index": ALL}, "value"),
    Output({"type": "fm-slot-oop-pos", "index": ALL}, "value"),
    Output({"type": "fm-slot-ip", "index": ALL}, "value"),
    Output({"type": "fm-slot-oop", "index": ALL}, "value"),
    Output({"type": "fm-slot-foot-left", "index": ALL}, "value"),
    Output({"type": "fm-slot-foot-right", "index": ALL}, "value"),
    Output("fm-status", "children"),
    Output("fm-save", "disabled"),
    Output("fm-duplicate", "disabled"),
    Output("fm-delete", "disabled"),
    Input("fm-pack", "value"),
    Input("fm-new", "n_clicks"),
    Input("fm-save", "n_clicks"),
    Input("fm-duplicate", "n_clicks"),
    Input("fm-delete", "n_clicks"),
    State("fm-name", "value"),
    State("fm-shape", "value"),
    State("fm-notes", "value"),
    State({"type": "fm-slot-ip-pos", "index": ALL}, "value"),
    State({"type": "fm-slot-oop-pos", "index": ALL}, "value"),
    State({"type": "fm-slot-ip", "index": ALL}, "value"),
    State({"type": "fm-slot-oop", "index": ALL}, "value"),
    State({"type": "fm-slot-foot-left", "index": ALL}, "value"),
    State({"type": "fm-slot-foot-right", "index": ALL}, "value"),
    prevent_initial_call=True,
)
def handle_formations(
    pack_id,
    _new,
    _save,
    _dup,
    _delete,
    name,
    shape,
    notes,
    ip_pos,
    oop_pos,
    ips,
    oops,
    foot_left,
    foot_right,
):
    triggered = ctx.triggered_id
    if not triggered:
        return (no_update,) * _FORM_OUTPUT_COUNT

    def finish(formation, status):
        return _form_outputs(formation, status)

    if triggered == "fm-pack":
        if not pack_id:
            return finish(fm.blank(), "Editing a new formation. Save to keep it.")
        formation = fm.load(pack_id)
        return finish(formation, f"Loaded {formation['name']}.")

    draft = _draft(
        name,
        shape,
        notes,
        ip_pos,
        oop_pos,
        ips,
        oops,
        foot_left,
        foot_right,
        pack_id or "",
    )
    if triggered == "fm-new":
        return finish(fm.blank(), "Editing a new formation. Save to keep it.")
    if triggered == "fm-duplicate":
        if not pack_id:
            return (no_update,) * 11 + (
                "Select a saved formation to duplicate.",
                no_update,
                no_update,
                no_update,
            )
        source_name = str(name or "").strip() or "Formation"
        formation = fm.duplicate(pack_id, f"{source_name} copy")
        return finish(
            formation,
            f"Duplicated as {formation['name']}.",
        )
    if triggered == "fm-save":
        existed = bool(pack_id) and fm.exists(pack_id)
        formation = fm.save(draft, pack_id if existed else None)
        verb = "Saved" if existed else "Created"
        return finish(formation, f"{verb} {formation['name']}.")
    if triggered == "fm-delete":
        if not pack_id:
            return (no_update,) * 11 + (
                "Select a saved formation to delete.",
                no_update,
                no_update,
                no_update,
            )
        label = draft.get("name") or pack_id
        fm.delete(pack_id)
        return finish(fm.blank(), f"Deleted {label}. Editing a new formation.")
    return (no_update,) * _FORM_OUTPUT_COUNT
