"""Role config page: edit attribute tiers and position groups for each role."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page

import role_config as rc
from role_scorer import GROUP_DEFS, role_groups, role_meta
from phases import phase_matches, pretty_role_name

register_page(__name__, path="/role-config", name="Role configs")

rc.ensure_loaded()

DEFAULT_ROLE = "Sweeper_Keeper_OOP_GK"
TIER_HINT = {
    "none": "Off · click to set Key",
    "key": "Key ×5 · click to set Preferred",
    "preferred": "Preferred ×3 · click to set Useful",
    "useful": "Useful ×1 · click to clear",
}


def _all_roles() -> list[tuple[str, dict]]:
    roles = []
    seen = set()
    for _group, _label, group_roles in GROUP_DEFS:
        for role_id in group_roles:
            if role_id in seen:
                continue
            seen.add(role_id)
            roles.append((role_id, role_meta(role_id)))
    return roles


def _match(role_id: str, meta: dict, phase: str, group: str, query: str) -> bool:
    groups = role_groups(role_id) or [meta.get("group") or ""]
    if not phase_matches(meta.get("phase"), phase, role_id, "gk" if "gk" in groups else (groups[0] if groups else "")):
        return False
    if group not in ("", "all") and group not in groups:
        return False
    if query:
        blob = f"{meta['name']} {meta['code']} {role_id}".lower()
        if query not in blob:
            return False
    return True


def _phase_buttons(active: str) -> list:
    return [
        html.Button(
            label,
            id={"type": "rc-phase", "phase": value},
            n_clicks=0,
            className="rc-chip" + (" active" if active == value else ""),
        )
        for value, label in (("all", "All"), ("IP", "IP"), ("OOP", "OOP"), ("GK", "GK"))
    ]


def _new_mode_buttons(active: str) -> list:
    return [
        html.Button(
            label,
            id={"type": "rc-new-mode", "mode": value},
            n_clicks=0,
            className="rc-chip" + (" active" if active == value else ""),
            title=title,
        )
        for value, label, title in (
            ("copy", "Copy selected", "New config starts as a copy of the selected config"),
            ("scratch", "From scratch", "New config starts with every role’s attributes blank"),
        )
    ]


def _group_buttons(active: str) -> list:
    buttons = [
        html.Button(
            "All groups",
            id={"type": "rc-group", "group": "all"},
            n_clicks=0,
            className="rc-chip" + (" active" if active == "all" else ""),
        )
    ]
    for group, label, _roles in GROUP_DEFS:
        buttons.append(
            html.Button(
                label,
                id={"type": "rc-group", "group": group},
                n_clicks=0,
                className="rc-chip" + (" active" if active == group else ""),
            )
        )
    return buttons


def _role_list(selected: str, phase: str, group: str, query: str) -> list:
    items = []
    query = (query or "").strip().lower()
    phase = (phase or "all").upper() if phase != "all" else "all"
    for role_id, meta in _all_roles():
        if not _match(role_id, meta, phase, group or "all", query):
            continue
        dirty = rc.is_modified(role_id)
        active = " active" if role_id == selected else ""
        items.append(
            html.Button(
                [
                    html.Span(meta["code"], className="rc-list-code"),
                    html.Span(meta["name"], className="rc-list-name"),
                    html.Span(
                        meta["phase"],
                        className=f"rc-phase-tag {meta.get('tone') or 'gk'}",
                    ),
                    html.Span("•", className="rc-dirty") if dirty else None,
                ],
                id={"type": "rc-pick", "role": role_id},
                n_clicks=0,
                className="rc-list-item" + active,
                title=f"{meta['name']} ({meta['code']})",
            )
        )
    if not items:
        return [html.Div("No roles match.", className="rc-empty")]
    return items


def _info_row(label: str, value, value_class: str = "") -> html.Div:
    return html.Div(
        [
            html.Span(label, className="rc-info-label"),
            html.Div(value, className=f"rc-info-value {value_class}".strip()),
        ],
        className="rc-info-row",
    )


def _badge(value, css: str) -> html.Span:
    return html.Span(str(value), className=f"rc-badge {css}")


def _attr_pills(cfg: dict, tier: str) -> html.Div | None:
    attrs = list(cfg.get(f"{tier}_attrs") or [])
    if not attrs:
        return html.Div("None", className="rc-pill-empty")
    return html.Div(
        [
            html.Span(rc.ATTR_LABELS.get(attr, attr), className=f"rc-mini-pill {tier}")
            for attr in attrs
        ],
        className="rc-mini-pills",
    )


def _identity(role_id: str) -> html.Div:
    meta = role_meta(role_id)
    cfg = rc.role_cfg(role_id)
    key_n = len(cfg.get("key_attrs") or [])
    preferred_n = len(cfg.get("preferred_attrs") or [])
    useful_n = len(cfg.get("useful_attrs") or [])
    dirty = rc.is_modified(role_id)
    return html.Div(
        [
            html.Div(meta["name"], className="rc-role-name"),
            html.Div(
                [
                    html.Div(meta["code"], className=f"rc-monogram {meta.get('tone') or 'gk'}"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    _badge(key_n, "key"),
                                    _badge(preferred_n, "preferred"),
                                    _badge(useful_n, "useful"),
                                ],
                                className="rc-badge-row",
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        meta["phase"],
                                        className=f"rc-phase-tag {meta.get('tone') or 'gk'}",
                                    ),
                                    html.Span("Unsaved", className="rc-custom-tag")
                                    if dirty
                                    else html.Span("Saved", className="rc-default-tag"),
                                ],
                                className="rc-tag-row",
                            ),
                        ],
                        className="rc-id-meta",
                    ),
                ],
                className="rc-id-top",
            ),
            html.Div("This role", className="rc-section-kicker"),
            html.Div(
                [
                    html.Button(
                        "Clear this role",
                        id="rc-clear-role",
                        n_clicks=0,
                        className="rc-btn ghost danger",
                        title="Turn off every key, preferred, and useful attribute on this role",
                    ),
                    html.Button(
                        "Reset",
                        id="rc-reset-role",
                        n_clicks=0,
                        className="rc-btn ghost",
                        title="Reload this role from the selected config",
                    ),
                ],
                className="rc-role-actions",
            ),
            html.Div("Role info", className="rc-section-kicker"),
            html.Div(
                [
                    _info_row("Name", meta["name"]),
                    _info_row("Code", meta["code"]),
                    _info_row("Phase", meta["phase"] or "—"),
                    _info_row("Group", meta.get("group_label") or "—"),
                    _info_row("Key attrs", _badge(f"{key_n} × {rc.TIER_WEIGHT['key']}", "key")),
                    _info_row("Preferred attrs", _badge(f"{preferred_n} × {rc.TIER_WEIGHT['preferred']}", "preferred")),
                    _info_row("Useful attrs", _badge(f"{useful_n} × {rc.TIER_WEIGHT['useful']}", "useful")),
                    _info_row("Divisor", cfg.get("divisor") or 0),
                ],
                className="rc-info-list",
            ),
            html.Div("Positions", className="rc-section-kicker"),
            html.Div(
                "Player-position buckets this role can score in. A role can "
                "belong to more than one (Inside Winger is Wide midfielders "
                "and Wingers).",
                className="rc-hint",
            ),
            html.Div(
                [
                    html.Button(
                        label,
                        id={"type": "rc-rgroup", "group": gid},
                        n_clicks=0,
                        className="rc-group-toggle"
                        + (" active" if gid in role_groups(role_id) else ""),
                        title="Click to add or remove this position group",
                    )
                    for gid, label, _roles in GROUP_DEFS
                ],
                className="rc-group-toggles",
            ),
            html.Div("Key", className="rc-section-kicker"),
            _attr_pills(cfg, "key"),
            html.Div("Preferred", className="rc-section-kicker"),
            _attr_pills(cfg, "preferred"),
            html.Div("Useful", className="rc-section-kicker"),
            _attr_pills(cfg, "useful"),
            html.Div(
                "score = (5×key + 3×preferred + 1×useful) / divisor",
                className="rc-formula",
            ),
        ],
        className="rc-card rc-identity",
    )


def _attr_row(attr: str, label: str, cfg: dict) -> html.Button:
    tier = rc.attr_tier(cfg, attr)
    weight = rc.TIER_WEIGHT[tier]
    display = "—" if tier == "none" else str(weight)
    return html.Button(
        [
            html.Span(label, className="rc-attr-name"),
            html.Span(display, className=f"rc-attr-val {tier}"),
        ],
        id={"type": "rc-attr", "attr": attr},
        n_clicks=0,
        className="rc-attr-row",
        title=TIER_HINT[tier],
    )


def _attr_column(title: str, attrs: list[tuple[str, str]], cfg: dict, extra=None) -> html.Div:
    children = [
        html.Div(title, className="rc-col-head"),
        html.Div([_attr_row(code, label, cfg) for code, label in attrs], className="rc-col-body"),
    ]
    if extra:
        children.extend(extra)
    return html.Div(children, className="rc-attr-col")


def _attributes(role_id: str) -> html.Div:
    cfg = rc.role_cfg(role_id)
    columns = []
    for title, attrs in rc.attr_groups_for(role_id):
        extra = None
        if title == "Physical" and not rc.is_gk_role(role_id):
            extra = [
                html.Div("Set Pieces", className="rc-col-head nested"),
                html.Div(
                    [_attr_row(code, label, cfg) for code, label in rc.SET_PIECE_ATTRS],
                    className="rc-col-body",
                ),
            ]
        columns.append(_attr_column(title, attrs, cfg, extra=extra))
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Attributes", className="rc-attrs-title"),
                    html.Div(
                        [
                            html.Span("Key ×5", className="rc-legend key"),
                            html.Span("Preferred ×3", className="rc-legend preferred"),
                            html.Span("Useful ×1", className="rc-legend useful"),
                        ],
                        className="rc-legend-row",
                    ),
                ],
                className="rc-attrs-header",
            ),
            html.Div(
                "Click a value to cycle Key → Preferred → Useful → Off. Reset reloads this role from the selected config. Save writes a named config. Built-in is read-only — use New config to make a file.",
                className="rc-attrs-note",
            ),
            html.Div(columns, className="rc-attr-grid"),
        ],
        className="rc-card rc-attributes",
    )


def _profile(role_id: str | None) -> html.Div:
    if not rc.has_role(role_id):
        return html.Div("Select a role to view its config.", className="rc-empty")
    return html.Div(
        [_identity(role_id), _attributes(role_id)],
        className="rc-profile",
    )


def _clicked(n_clicks) -> bool:
    return bool(n_clicks) and any(n_clicks)


def _bar(title: str, children: list, extra: str = "") -> html.Div:
    return html.Div(
        [html.Span(title, className="rc-bar-title"), *children],
        className=f"rc-bar {extra}".strip(),
    )


def layout():
    return html.Div(
    [
        dcc.Store(id="rc-selected", data=DEFAULT_ROLE),
        dcc.Store(id="rc-phase", data="all"),
        dcc.Store(id="rc-group", data="all"),
        dcc.Store(id="rc-new-mode", data="copy"),
        dcc.Store(id="rc-rev", data=0),
        html.Div(
            [
                html.Button(id={"type": "rc-pick", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rc-attr", "attr": "_"}, n_clicks=0),
                html.Button(id={"type": "rc-phase", "phase": "_"}, n_clicks=0),
                html.Button(id={"type": "rc-group", "group": "_"}, n_clicks=0),
                html.Button(id={"type": "rc-rgroup", "group": "_"}, n_clicks=0),
                html.Button(id={"type": "rc-new-mode", "mode": "_"}, n_clicks=0),
            ],
            hidden=True,
        ),
        html.Div(
            [
                html.H1("Role configs", className="rc-page-title"),
                html.P(
                    "View and edit the key, preferred, and useful attributes used to score each FM26 role.",
                    className="rc-page-sub",
                ),
            ],
            className="rc-hero",
        ),
        html.Div(
            [
                _bar(
                    "Filters",
                    [
                        html.Span("Phase", className="rc-chip-label"),
                        html.Div(_phase_buttons("all"), id="rc-phase-row", className="rc-chip-row"),
                        html.Span("Group", className="rc-chip-label"),
                        html.Div(_group_buttons("all"), id="rc-group-row", className="rc-chip-row wrap"),
                        dcc.Input(
                            id="rc-search",
                            type="search",
                            placeholder="Search roles",
                            className="rc-search",
                        ),
                    ],
                ),
                _bar(
                    "Config",
                    [
                        html.Div(
                            dcc.Dropdown(
                                id="rc-pack",
                                options=rc.pack_options(),
                                value=rc.active_pack_id(),
                                clearable=False,
                                className="rc-pack-dd",
                            ),
                            className="rc-pack-wrap",
                        ),
                        html.Span(id="rc-pack-status", className="rc-pack-status"),
                        html.Span(className="rc-bar-split"),
                        dcc.Input(
                            id="rc-new-name",
                            type="text",
                            placeholder="New config name",
                            className="rc-search",
                        ),
                        html.Div(_new_mode_buttons("copy"), id="rc-new-mode-row", className="rc-chip-row"),
                        html.Button(
                            "New config",
                            id="rc-new-pack",
                            n_clicks=0,
                            className="rc-btn",
                            title="Create a named config from a copy of the selected one, or from scratch",
                        ),
                        html.Button(
                            "Save",
                            id="rc-save",
                            n_clicks=0,
                            className="rc-btn",
                            title="Write the current weights to the selected named config",
                        ),
                    ],
                ),
            ],
            className="rc-bars",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Div("Roles", className="rc-sidebar-head"),
                        html.Div(
                            _role_list(DEFAULT_ROLE, "all", "all", ""),
                            id="rc-sidebar",
                            className="rc-sidebar-list",
                        ),
                    ],
                    className="rc-sidebar",
                ),
                html.Div(_profile(DEFAULT_ROLE), id="rc-profile-wrap", className="rc-profile-wrap"),
            ],
            className="rc-shell",
        ),
    ],
    className="rc-page",
)


@callback(
    Output("rc-phase", "data"),
    Output("rc-phase-row", "children"),
    Input({"type": "rc-phase", "phase": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_phase(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    phase = ctx.triggered_id["phase"]
    if phase == "_":
        return no_update, no_update
    return phase, _phase_buttons(phase)


@callback(
    Output("rc-group", "data"),
    Output("rc-group-row", "children"),
    Input({"type": "rc-group", "group": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_group(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    group = ctx.triggered_id["group"]
    if group == "_":
        return no_update, no_update
    return group, _group_buttons(group)


@callback(
    Output("rc-new-mode", "data"),
    Output("rc-new-mode-row", "children"),
    Input({"type": "rc-new-mode", "mode": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_new_mode(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    mode = ctx.triggered_id["mode"]
    if mode not in ("copy", "scratch"):
        return no_update, no_update
    return mode, _new_mode_buttons(mode)


@callback(
    Output("rc-selected", "data"),
    Input({"type": "rc-pick", "role": ALL}, "n_clicks"),
    State("rc-selected", "data"),
    prevent_initial_call=True,
)
def pick_role(n_clicks, current):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    role_id = ctx.triggered_id["role"]
    if role_id == "_" or role_id == current:
        return no_update
    return role_id


@callback(
    Output("rc-rev", "data"),
    Output("rc-pack-status", "children"),
    Output("rc-pack", "value", allow_duplicate=True),
    Output("rc-pack", "options"),
    Input({"type": "rc-attr", "attr": ALL}, "n_clicks"),
    Input("rc-reset-role", "n_clicks"),
    Input("rc-clear-role", "n_clicks"),
    Input("rc-save", "n_clicks"),
    Input("rc-new-pack", "n_clicks"),
    Input({"type": "rc-rgroup", "group": ALL}, "n_clicks"),
    State("rc-selected", "data"),
    State("rc-rev", "data"),
    State("rc-new-name", "value"),
    State("rc-new-mode", "data"),
    prevent_initial_call=True,
)
def mutate_config(
    attr_clicks,
    reset_role,
    clear_role,
    save_clicks,
    new_pack,
    rgroup_clicks,
    role_id,
    rev,
    new_name,
    new_mode,
):
    trigger = ctx.triggered_id
    options = rc.pack_options()
    if trigger == "rc-save":
        if not save_clicks:
            return no_update, no_update, no_update, no_update
        pack_id = rc.persist_live()
        if not pack_id:
            return (
                int(rev or 0) + 1,
                "Create a new config to save changes",
                rc.active_pack_id(),
                options,
            )
        label = next((opt["label"] for opt in rc.pack_options() if opt["value"] == pack_id), pack_id)
        return int(rev or 0) + 1, f"Saved {label}", pack_id, rc.pack_options()
    if trigger == "rc-new-pack":
        if not new_pack:
            return no_update, no_update, no_update, no_update
        saved = rc.create_pack(new_name, new_mode or "copy")
        how = "from scratch" if saved["source"] == "scratch" else "from selected"
        return (
            int(rev or 0) + 1,
            f"Created “{saved['name']}” {how}",
            saved["id"],
            rc.pack_options(),
        )
    if isinstance(trigger, dict) and trigger.get("type") == "rc-rgroup":
        group = trigger.get("group")
        if not _clicked(rgroup_clicks) or not group or group == "_" or not role_id:
            return no_update, no_update, no_update, no_update
        rc.toggle_role_group(role_id, group)
        return int(rev or 0) + 1, "", rc.active_pack_id(), options
    if trigger == "rc-reset-role":
        if not reset_role or not role_id:
            return no_update, no_update, no_update, no_update
        rc.reset_role(role_id)
        return int(rev or 0) + 1, f"Reset {pretty_role_name(role_id)}", rc.active_pack_id(), options
    if trigger == "rc-clear-role":
        if not clear_role or not role_id:
            return no_update, no_update, no_update, no_update
        rc.clear_role(role_id)
        return (
            int(rev or 0) + 1,
            f"Cleared {pretty_role_name(role_id)}",
            rc.active_pack_id(),
            options,
        )
    if isinstance(trigger, dict) and trigger.get("type") == "rc-attr":
        attr = trigger.get("attr")
        if not _clicked(attr_clicks) or not attr or attr == "_" or not role_id:
            return no_update, no_update, no_update, no_update
        rc.cycle_attr(role_id, attr)
        return int(rev or 0) + 1, "", rc.active_pack_id(), options
    return no_update, no_update, no_update, no_update


@callback(
    Output("rc-rev", "data", allow_duplicate=True),
    Output("rc-pack-status", "children", allow_duplicate=True),
    Input("rc-pack", "value"),
    State("rc-rev", "data"),
    prevent_initial_call=True,
)
def on_pack_change(pack_id, rev):
    if not pack_id or pack_id == rc.active_pack_id():
        return no_update, no_update
    loaded = rc.load_pack(pack_id)
    label = next((opt["label"] for opt in rc.pack_options() if opt["value"] == loaded), loaded)
    return int(rev or 0) + 1, f"Loaded {label}"


@callback(
    Output("rc-sidebar", "children"),
    Output("rc-profile-wrap", "children"),
    Input("rc-selected", "data"),
    Input("rc-phase", "data"),
    Input("rc-group", "data"),
    Input("rc-search", "value"),
    Input("rc-rev", "data"),
)
def render_page(selected, phase, group, query, _rev):
    selected = selected or DEFAULT_ROLE
    phase = phase or "all"
    group = group or "all"
    return _role_list(selected, phase, group, query), _profile(selected)
