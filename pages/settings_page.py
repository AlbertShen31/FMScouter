"""Settings page: packs, Role scores options, and Player stats threshold packs."""
from __future__ import annotations

from urllib.parse import parse_qs

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

import role_scorer as rs
from stats_scorer import (
    benchmarks,
    metric_defs,
    percentile_marks,
)
import stats_threshold_packs as stp
import ui_settings as us

register_page(__name__, path="/settings", name="Settings")

BAND_LABELS = (
    ("elite", "Elite"),
    ("good", "Good"),
    ("ok", "OK"),
    ("poor", "Poor"),
)

THRESH_GROUPS = (
    ("gk", "Goalkeepers"),
    ("def", "Defenders"),
    ("mid", "Midfielders"),
    ("fwd", "Forwards"),
)

SETTINGS_SECTIONS = (
    ("general", "General"),
    ("role-scores", "Role scores"),
    ("player-stats", "Player stats"),
)


def _set_piece_formula_lines() -> list:
    lines = []
    for profile in rs.SET_PIECE_PROFILES:
        lines.append(
            html.Div(
                [
                    html.Span(profile["label"], className="rs-set-piece-name"),
                    html.Span(profile.get("detail") or "", className="rs-set-piece-detail"),
                    html.Span(rs.set_piece_formula(profile), className="rs-set-piece-formula"),
                ],
                className="rs-set-piece-line",
            )
        )
    return lines


def _color_row(band: str, label: str, colors: dict) -> html.Div:
    return html.Div(
        [
            html.Div(label, className="st-color-name"),
            html.Span(
                ["Preview", html.Span(className="st-swatch")],
                className=f"st-preview rs-legend-chip {band}",
            ),
            *[
                html.Div(
                    [
                        html.Label(part.upper(), className="st-mini-label"),
                        html.Span(
                            className="st-color-swatch",
                            style={"backgroundColor": colors[part]},
                        ),
                        dmc.TextInput(
                            id={"type": "st-color", "band": band, "part": part},
                            value=colors[part],
                            debounce=500,
                            className="st-color-text",
                            placeholder="#rrggbb",
                        ),
                    ],
                    className="st-color-field",
                )
                for part in us.COLOR_PARTS
            ],
        ],
        className="st-color-row",
    )


def _section_heading(title: str, blurb: str | None = None) -> html.Div:
    children: list = [html.H2(title, className="st-section-heading")]
    if blurb:
        children.append(html.P(blurb, className="text-muted st-section-blurb"))
    return html.Div(children, className="st-section-head")


def _section_save_row(save_id: str, status_id: str) -> html.Div:
    return html.Div(
        [
            dmc.Button("Save", id=save_id, className="st-section-save-btn"),
            html.Div(id=status_id, className="st-status"),
        ],
        className="st-section-save-row",
    )


def _category_options(group: str) -> list[dict[str, str]]:
    block = benchmarks()["benchmarks"].get(group) or {}
    labels = {}
    for domain in ("outfield", "gk"):
        for cat in benchmarks()["categories"].get(domain) or []:
            labels[cat["id"]] = cat["label"]
    return [
        {"value": cat_id, "label": labels.get(cat_id, cat_id)}
        for cat_id in block.keys()
    ]


def _default_thresh_category(group: str) -> str:
    options = _category_options(group)
    return options[0]["value"] if options else "defending"


def _threshold_editor(group: str, category: str, tree: dict) -> html.Div:
    marks = percentile_marks()
    metrics = ((tree.get(group) or {}).get(category) or {})
    if not metrics:
        return html.Div(
            "No metrics for this group and category.",
            className="text-muted",
        )
    defs = metric_defs()
    header = html.Div(
        [
            html.Span("Metric", className="st-thresh-metric-head"),
            *[html.Span(f"{mark}th", className="st-thresh-cut-head") for mark in marks],
        ],
        className="st-thresh-row st-thresh-header",
    )
    rows = []
    for metric_id, values in metrics.items():
        meta = defs.get(metric_id) or {}
        label = meta.get("label") or metric_id
        abbr = meta.get("abbr") or ""
        hib = bool(meta.get("higher_is_better", True))
        hint = "higher is better" if hib else "lower is better"
        cells = [
            html.Div(
                [
                    html.Span(label, className="st-thresh-metric-name"),
                    html.Span(
                        f"{abbr} · {hint}" if abbr else hint,
                        className="st-thresh-metric-meta",
                    ),
                ],
                className="st-thresh-metric",
            )
        ]
        for idx in range(4):
            cells.append(
                dmc.NumberInput(
                    id={
                        "type": "st-thresh",
                        "group": group,
                        "category": category,
                        "metric": metric_id,
                        "idx": idx,
                    },
                    value=float(values[idx]),
                    decimalScale=3,
                    hideControls=True,
                    debounce=400,
                    className="st-thresh-input",
                )
            )
        rows.append(html.Div(cells, className="st-thresh-row"))
    return html.Div([header, *rows], className="st-thresh-table")


def _settings_nav(active: str = "general") -> html.Nav:
    links = []
    for section_id, label in SETTINGS_SECTIONS:
        links.append(
            html.Button(
                label,
                id={"type": "st-settings-nav", "section": section_id},
                className=(
                    "st-settings-nav-link is-active"
                    if section_id == active
                    else "st-settings-nav-link"
                ),
                n_clicks=0,
                type="button",
            )
        )
    return html.Nav(links, className="st-settings-nav", **{"aria-label": "Settings sections"})


def _panel(section_id: str, children: list, *, active: bool) -> html.Div:
    return html.Div(
        children,
        id={"type": "st-settings-panel", "section": section_id},
        className="st-settings-panel is-active" if active else "st-settings-panel",
        hidden=not active,
    )


def _general_panel(settings: dict) -> list:
    default_note = (
        "Default uses built-in values until you save Role scores changes; those are stored "
        "locally and can be restored with Reset defaults."
        if us.is_builtin(settings.get("id"))
        else "Named Role scores packs save to their own files."
    )
    return [
        _section_heading(
            "General",
            "Manage the Role scores settings pack. Player stats percentiles use their own packs.",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Role scores settings pack"),
                dbc.CardBody(
                    [
                        html.P(default_note, className="text-muted"),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dmc.Select(
                                        id="st-pack",
                                        data=us.pack_options(),
                                        value=settings.get("id") or us.BUILTIN,
                                        clearable=False,
                                        searchable=False,
                                    ),
                                    md=4,
                                ),
                                dbc.Col(
                                    dmc.TextInput(
                                        id="st-new-name",
                                        placeholder="New settings name",
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        dmc.Button(
                                            "New",
                                            id="st-new",
                                            variant="light",
                                            className="me-2",
                                        ),
                                        dmc.Button(
                                            "Reset defaults",
                                            id="st-reset",
                                            variant="light",
                                        ),
                                    ],
                                    md=5,
                                ),
                            ],
                            className="g-2 align-items-center",
                        ),
                        _section_save_row("st-save-general", "st-status-general"),
                    ]
                ),
            ],
            className="mb-3",
        ),
    ]


def _role_panel(settings: dict) -> list:
    bands = settings["bands"]
    return [
        _section_heading(
            "Role scores",
            "Score bands, colors, histogram, set pieces, age menu, and footedness "
            "(age and footedness are also used on Player stats).",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Age filter"),
                dbc.CardBody(
                    [
                        dmc.TextInput(
                            id="st-age-tiers",
                            label="Age tiers",
                            value=us.format_list(settings["age_tiers"], kind="age"),
                            debounce=500,
                        ),
                        html.Small(
                            "Comma-separated maximum ages for the Max age menu. Any is always included.",
                            className="text-muted",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Score bands"),
                dbc.CardBody(
                    [
                        html.P(
                            "Used for squad-depth coloring, table cell colors, and the Poor cutoff.",
                            className="text-muted",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-band-elite",
                                        label="Elite ≥",
                                        min=0,
                                        max=20,
                                        step=0.5,
                                        decimalScale=1,
                                        value=bands["elite"],
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-band-good",
                                        label="Good ≥",
                                        min=0,
                                        max=20,
                                        step=0.5,
                                        decimalScale=1,
                                        value=bands["good"],
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-band-ok",
                                        label="OK ≥",
                                        min=0,
                                        max=20,
                                        step=0.5,
                                        decimalScale=1,
                                        value=bands["ok"],
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Poor"),
                                        html.Div(
                                            id="st-poor-cut",
                                            children=f"< {us.format_cut(bands['ok'])}",
                                            className="st-poor-cut",
                                        ),
                                    ],
                                    md=3,
                                ),
                            ],
                            className="g-3",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Footedness"),
                dbc.CardBody(
                    [
                        html.P(
                            "Strength scale is 1 (very weak) through 6 (very strong). "
                            "Each footedness filter uses its own minimum rating for that foot.",
                            className="text-muted",
                        ),
                        html.Div(
                            [
                                dmc.Select(
                                    id="st-foot-left",
                                    label="Left foot filter",
                                    data=rs.foot_strength_options(),
                                    value=str(settings["foot_thresholds"]["left"]),
                                    clearable=False,
                                    searchable=False,
                                ),
                                dmc.Select(
                                    id="st-foot-both",
                                    label="Both feet filter",
                                    data=rs.foot_strength_options(),
                                    value=str(settings["foot_thresholds"]["both"]),
                                    clearable=False,
                                    searchable=False,
                                ),
                                dmc.Select(
                                    id="st-foot-right",
                                    label="Right foot filter",
                                    data=rs.foot_strength_options(),
                                    value=str(settings["foot_thresholds"]["right"]),
                                    clearable=False,
                                    searchable=False,
                                ),
                            ],
                            className="st-foot-thresholds",
                        ),
                        html.Small(
                            id="st-foot-preview",
                            children=rs.foot_filter_help(settings["foot_thresholds"]),
                            className="text-muted d-block mt-2",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Set-piece formulas"),
                dbc.CardBody(
                    [
                        html.P(rs.set_piece_hint(), className="text-muted"),
                        html.Div(
                            _set_piece_formula_lines(),
                            className="rs-set-piece-formulas st-set-piece-formulas",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Histogram bins"),
                dbc.CardBody(
                    [
                        dmc.TextInput(
                            id="st-hist-edges",
                            label="Cut points",
                            value=us.format_list(settings["hist_edges"]),
                            debounce=500,
                        ),
                        html.Small(
                            "Comma-separated edges. The first value is the top of the lowest band "
                            "(so 10 makes that band <10). The last value starts the open-ended top bin.",
                            className="text-muted d-block mb-2",
                        ),
                        html.Div(
                            id="st-hist-preview",
                            children=us.hist_preview(settings),
                            className="st-preview-line",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Band colors"),
                dbc.CardBody(
                    [
                        html.P(
                            "Background and text color table cells and legend chips. "
                            "Bar is the squad-depth segment. Enter hex colors like #dcfce7.",
                            className="text-muted",
                        ),
                        html.Div(
                            [
                                _color_row(band, label, settings["colors"][band])
                                for band, label in BAND_LABELS
                            ],
                            className="st-color-list",
                        ),
                        _section_save_row("st-save-role", "st-status-role"),
                    ]
                ),
            ],
            className="mb-3",
        ),
    ]


def _player_panel(thresh_pack: dict) -> list:
    tree = thresh_pack["thresholds"]
    group0 = "mid"
    cat0 = _default_thresh_category(group0)
    note = (
        f"{stp.BUILTIN_NAME} is the shipped MustermannFM table. "
        "Create named packs for alternate cut-points."
        if stp.is_builtin(thresh_pack.get("id"))
        else "Named percentile packs save to their own files."
    )
    return [
        _section_heading(
            "Player stats",
            "Percentile cut-points for each statistic (20th / 40th / 60th / 80th). "
            "These drive estimated percentiles on the Player stats page.",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Percentile threshold pack"),
                dbc.CardBody(
                    [
                        html.P(note, className="text-muted"),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dmc.Select(
                                        id="st-thresh-pack",
                                        data=stp.pack_options(),
                                        value=thresh_pack.get("id") or stp.BUILTIN,
                                        clearable=False,
                                        searchable=False,
                                    ),
                                    md=4,
                                ),
                                dbc.Col(
                                    dmc.TextInput(
                                        id="st-thresh-new-name",
                                        placeholder="New pack name",
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        dmc.Button(
                                            "New",
                                            id="st-thresh-new",
                                            variant="light",
                                            className="me-2",
                                        ),
                                        dmc.Button(
                                            "Reset to MustermannFM",
                                            id="st-thresh-reset",
                                            variant="light",
                                        ),
                                    ],
                                    md=5,
                                ),
                            ],
                            className="g-2 align-items-center",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Statistic percentile thresholds"),
                dbc.CardBody(
                    [
                        html.P(
                            "Pick a position group and category, then edit the four cut-points. "
                            "Save this section to apply the active pack on Player stats.",
                            className="text-muted",
                        ),
                        html.Div(
                            [
                                dmc.Select(
                                    id="st-thresh-group",
                                    label="Position group",
                                    data=[
                                        {"value": key, "label": label}
                                        for key, label in THRESH_GROUPS
                                    ],
                                    value=group0,
                                    clearable=False,
                                    searchable=False,
                                ),
                                dmc.Select(
                                    id="st-thresh-category",
                                    label="Category",
                                    data=_category_options(group0),
                                    value=cat0,
                                    clearable=False,
                                    searchable=False,
                                ),
                            ],
                            className="st-thresh-filters",
                        ),
                        html.Div(
                            id="st-thresh-editor",
                            children=_threshold_editor(group0, cat0, tree),
                            className="st-thresh-editor mt-3",
                        ),
                        _section_save_row("st-save-thresh", "st-status-thresh"),
                    ]
                ),
            ],
            className="mb-3",
        ),
    ]


def layout(section: str | None = None, **_kwargs):
    settings = us.load()
    thresh_pack = stp.load()
    allowed = {sid for sid, _label in SETTINGS_SECTIONS}
    active = section if section in allowed else "general"
    return dbc.Container(
        [
            html.H1("Settings"),
            html.P(
                "Use the side nav to jump between sections. Each section has its own Save. "
                "Player stats percentiles are separate named packs "
                f"(built-in: {stp.BUILTIN_NAME}).",
                className="text-muted",
            ),
            dcc.Location(id="st-settings-url", refresh=False),
            dcc.Store(id="st-settings-section", data=active),
            dcc.Store(id="st-thresh-data", data=thresh_pack["thresholds"]),
            dcc.Store(id="st-thresh-revision", data=0),
            html.Div(
                [
                    html.Aside(
                        [
                            html.Div("Sections", className="st-settings-nav-title"),
                            _settings_nav(active),
                        ],
                        className="st-settings-sidebar",
                    ),
                    html.Div(
                        [
                            _panel(
                                "general",
                                _general_panel(settings),
                                active=active == "general",
                            ),
                            _panel(
                                "role-scores",
                                _role_panel(settings),
                                active=active == "role-scores",
                            ),
                            _panel(
                                "player-stats",
                                _player_panel(thresh_pack),
                                active=active == "player-stats",
                            ),
                        ],
                        className="st-settings-main",
                    ),
                ],
                className="st-settings-layout",
            ),
        ],
        className="rs-page st-page",
        fluid=True,
    )


def _section_from_search(search: str | None) -> str | None:
    qs = parse_qs((search or "").lstrip("?"))
    requested = (qs.get("section") or [None])[0]
    allowed = {sid for sid, _label in SETTINGS_SECTIONS}
    return requested if requested in allowed else None


def _section_view(section: str) -> tuple:
    ids = [sid for sid, _label in SETTINGS_SECTIONS]
    nav_classes = [
        "st-settings-nav-link is-active" if sid == section else "st-settings-nav-link"
        for sid in ids
    ]
    hidden = [sid != section for sid in ids]
    panel_classes = [
        "st-settings-panel is-active" if sid == section else "st-settings-panel"
        for sid in ids
    ]
    return section, nav_classes, hidden, panel_classes


def _colors_from_state(color_values, specs) -> dict[str, dict[str, str]]:
    color_map = {band: {} for band in us.BAND_KEYS}
    for spec, value in zip(specs or [], color_values or []):
        ident = spec["id"]
        color_map[ident["band"]][ident["part"]] = value
    return color_map


def _color_values_for(settings: dict, specs) -> list[str]:
    return [
        settings["colors"][spec["id"]["band"]][spec["id"]["part"]]
        for spec in specs
    ]


def _role_form_values(settings: dict, specs) -> tuple:
    feet = settings["foot_thresholds"]
    return (
        us.format_list(settings["age_tiers"], kind="age"),
        settings["bands"]["elite"],
        settings["bands"]["good"],
        settings["bands"]["ok"],
        str(feet["left"]),
        str(feet["both"]),
        str(feet["right"]),
        us.format_list(settings["hist_edges"]),
        _color_values_for(settings, specs),
    )


def _refresh_ui_settings(settings: dict) -> dict:
    """Re-attach the active stats-threshold tree after a pack change."""
    return us.normalize(settings)


@callback(
    Output("st-settings-section", "data"),
    Output({"type": "st-settings-nav", "section": ALL}, "className"),
    Output({"type": "st-settings-panel", "section": ALL}, "hidden"),
    Output({"type": "st-settings-panel", "section": ALL}, "className"),
    Input("st-settings-url", "search"),
    Input({"type": "st-settings-nav", "section": ALL}, "n_clicks"),
    State("st-settings-section", "data"),
)
def switch_settings_section(search, n_clicks, current):
    triggered = ctx.triggered_id
    if isinstance(triggered, dict) and triggered.get("type") == "st-settings-nav":
        if not any(n_clicks or []):
            return no_update, no_update, no_update, no_update
        section = triggered.get("section") or current or "general"
        return _section_view(section)
    from_url = _section_from_search(search)
    if from_url:
        return _section_view(from_url)
    if triggered == "st-settings-url" or triggered is None:
        return _section_view(current or "general")
    return no_update, no_update, no_update, no_update


@callback(
    Output("st-hist-preview", "children"),
    Input("st-hist-edges", "value"),
)
def preview_hist(edges):
    return us.hist_preview({"hist_edges": edges})


@callback(
    Output("st-poor-cut", "children"),
    Input("st-band-ok", "value"),
)
def preview_poor(ok):
    return f"< {us.format_cut(ok if ok is not None else us.DEFAULTS['bands']['ok'])}"


@callback(
    Output("st-foot-preview", "children"),
    Input("st-foot-left", "value"),
    Input("st-foot-both", "value"),
    Input("st-foot-right", "value"),
)
def preview_foot(left, both, right):
    return rs.foot_filter_help({"left": left, "both": both, "right": right})


@callback(
    Output("st-thresh-category", "data"),
    Output("st-thresh-category", "value"),
    Input("st-thresh-group", "value"),
    State("st-thresh-category", "value"),
    prevent_initial_call=True,
)
def sync_thresh_categories(group, current):
    group = group or "mid"
    options = _category_options(group)
    values = {opt["value"] for opt in options}
    value = current if current in values else (options[0]["value"] if options else None)
    return options, value


@callback(
    Output("st-thresh-editor", "children"),
    Input("st-thresh-group", "value"),
    Input("st-thresh-category", "value"),
    Input("st-thresh-revision", "data"),
    State("st-thresh-data", "data"),
)
def render_thresh_editor(group, category, _revision, tree):
    group = group or "mid"
    category = category or _default_thresh_category(group)
    tree = stp.normalize_thresholds(tree)
    return _threshold_editor(group, category, tree)


@callback(
    Output("st-thresh-data", "data", allow_duplicate=True),
    Input({"type": "st-thresh", "group": ALL, "category": ALL, "metric": ALL, "idx": ALL}, "value"),
    State("st-thresh-data", "data"),
    prevent_initial_call=True,
)
def update_thresh_draft(values, tree):
    if not ctx.inputs_list or not ctx.inputs_list[0]:
        return no_update
    tree = stp.normalize_thresholds(tree)
    changed = False
    for spec, value in zip(ctx.inputs_list[0], values or []):
        ident = spec["id"]
        group = ident["group"]
        category = ident["category"]
        metric = ident["metric"]
        idx = int(ident["idx"])
        block = tree.setdefault(group, {}).setdefault(category, {})
        row = list(block.get(metric) or [0.0, 0.0, 0.0, 0.0])
        if len(row) != 4:
            row = [0.0, 0.0, 0.0, 0.0]
        try:
            number = float(value) if value is not None else row[idx]
        except (TypeError, ValueError):
            continue
        if number != number:
            continue
        if row[idx] != number:
            row[idx] = number
            block[metric] = row
            changed = True
    return tree if changed else no_update


def _ui_draft_from_state(
    pack_id,
    ages,
    elite,
    good,
    ok,
    foot_left,
    foot_both,
    foot_right,
    edges,
    color_values,
    color_specs,
) -> dict:
    return {
        "id": pack_id,
        "age_tiers": ages,
        "bands": {"elite": elite, "good": good, "ok": ok},
        "foot_thresholds": {
            "left": foot_left,
            "both": foot_both,
            "right": foot_right,
        },
        "hist_edges": edges,
        "colors": _colors_from_state(color_values, color_specs),
    }


@callback(
    Output("ui-settings", "data"),
    Output("st-pack", "data"),
    Output("st-pack", "value"),
    Output("st-age-tiers", "value"),
    Output("st-band-elite", "value"),
    Output("st-band-good", "value"),
    Output("st-band-ok", "value"),
    Output("st-foot-left", "value"),
    Output("st-foot-both", "value"),
    Output("st-foot-right", "value"),
    Output("st-hist-edges", "value"),
    Output({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    Output("st-status-general", "children"),
    Output("st-status-role", "children"),
    Output("st-new-name", "value"),
    Input("st-pack", "value"),
    Input("st-new", "n_clicks"),
    Input("st-reset", "n_clicks"),
    Input("st-save-general", "n_clicks"),
    Input("st-save-role", "n_clicks"),
    State("st-new-name", "value"),
    State("st-age-tiers", "value"),
    State("st-band-elite", "value"),
    State("st-band-good", "value"),
    State("st-band-ok", "value"),
    State("st-foot-left", "value"),
    State("st-foot-both", "value"),
    State("st-foot-right", "value"),
    State("st-hist-edges", "value"),
    State({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    prevent_initial_call=True,
)
def handle_ui_settings(
    pack_id,
    new_n,
    reset_n,
    save_general_n,
    save_role_n,
    new_name,
    ages,
    elite,
    good,
    ok,
    foot_left,
    foot_both,
    foot_right,
    edges,
    color_values,
):
    triggered = ctx.triggered_id
    if not triggered:
        return (no_update,) * 15
    color_specs = ctx.states_list[-1] if ctx.states_list else []
    draft = _ui_draft_from_state(
        pack_id,
        ages,
        elite,
        good,
        ok,
        foot_left,
        foot_both,
        foot_right,
        edges,
        color_values,
        color_specs,
    )
    status_general = no_update
    status_role = no_update
    clear_name = no_update
    update_pack_options = True

    if triggered == "st-pack":
        settings = us.load(pack_id)
        status_general = f"Loaded {settings['name']}."
    elif triggered == "st-reset":
        if pack_id == us.BUILTIN:
            us.clear_default_overrides()
            settings = us.load(us.BUILTIN)
            status_general = "Default restored to built-in values."
        else:
            settings = us.normalize(us.DEFAULTS, pack_id=pack_id, name=None)
            current = us.read_pack(pack_id)
            settings["id"] = current["id"]
            settings["name"] = current["name"]
            status_general = (
                "Form reset to built-in defaults. Save Role scores to keep them on this pack."
            )
        update_pack_options = False
    elif triggered == "st-new":
        label = str(new_name or "").strip()
        if not label:
            return (
                (no_update,) * 12
                + ("Enter a name to create a new settings file.", no_update, no_update)
            )
        settings = us.create_pack(label, draft)
        status_general = f"Created {settings['name']}."
        clear_name = ""
    elif triggered == "st-save-general":
        # Pack metadata / persist current Role scores draft onto the active pack.
        if us.is_builtin(pack_id):
            settings = us.save(draft, pack_id)
            status_general = f"Saved {settings['name']} overrides."
        else:
            current = us.read_pack(pack_id)
            draft["name"] = current["name"]
            settings = us.save(draft, pack_id)
            status_general = f"Saved {settings['name']}."
            update_pack_options = False
    elif triggered == "st-save-role":
        if us.is_builtin(pack_id):
            settings = us.save(draft, pack_id)
            status_role = f"Saved Role scores to {settings['name']}."
        else:
            current = us.read_pack(pack_id)
            draft["name"] = current["name"]
            settings = us.save(draft, pack_id)
            status_role = f"Saved Role scores to {settings['name']}."
            update_pack_options = False
    else:
        return (no_update,) * 15

    settings = _refresh_ui_settings(settings)
    role_values = _role_form_values(settings, color_specs)
    pack_options = us.pack_options() if update_pack_options else no_update
    pack_value = settings["id"] if update_pack_options else no_update
    return (
        settings,
        pack_options,
        pack_value,
        *role_values,
        status_general,
        status_role,
        clear_name,
    )


@callback(
    Output("ui-settings", "data", allow_duplicate=True),
    Output("st-thresh-pack", "data"),
    Output("st-thresh-pack", "value"),
    Output("st-thresh-data", "data"),
    Output("st-thresh-revision", "data"),
    Output("st-status-thresh", "children"),
    Output("st-thresh-new-name", "value"),
    Input("st-thresh-pack", "value"),
    Input("st-thresh-new", "n_clicks"),
    Input("st-thresh-reset", "n_clicks"),
    Input("st-save-thresh", "n_clicks"),
    State("st-thresh-new-name", "value"),
    State("st-thresh-data", "data"),
    State("st-thresh-revision", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def handle_thresh_packs(
    pack_id,
    new_n,
    reset_n,
    save_n,
    new_name,
    thresh_data,
    revision,
    ui_settings,
):
    triggered = ctx.triggered_id
    if not triggered:
        return (no_update,) * 7
    draft = {"id": pack_id, "thresholds": thresh_data}
    clear_name = no_update
    update_options = True
    bump = True

    if triggered == "st-thresh-pack":
        pack = stp.load(pack_id)
        status = f"Loaded {pack['name']}."
    elif triggered == "st-thresh-reset":
        if pack_id == stp.BUILTIN:
            stp.clear_default_overrides()
            pack = stp.load(stp.BUILTIN)
            status = f"Restored {stp.BUILTIN_NAME}."
        else:
            pack = stp.normalize_pack(
                {"thresholds": stp.builtin_thresholds()},
                pack_id=pack_id,
                name=None,
            )
            current = stp.read_pack(pack_id)
            pack["id"] = current["id"]
            pack["name"] = current["name"]
            status = (
                f"Form reset to {stp.BUILTIN_NAME}. Save this section to keep it on the pack."
            )
        update_options = False
    elif triggered == "st-thresh-new":
        label = str(new_name or "").strip()
        if not label:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                "Enter a name to create a new percentile pack.",
                no_update,
            )
        pack = stp.create_pack(label, draft)
        status = f"Created {pack['name']}."
        clear_name = ""
    elif triggered == "st-save-thresh":
        if stp.is_builtin(pack_id):
            pack = stp.save(draft, pack_id)
            status = f"Saved {pack['name']}."
        else:
            current = stp.read_pack(pack_id)
            draft["name"] = current["name"]
            pack = stp.save(draft, pack_id)
            status = f"Saved {pack['name']}."
            update_options = False
    else:
        return (no_update,) * 7

    # Refresh ui-settings so Player stats picks up the active tree.
    settings = us.normalize(ui_settings or {})
    settings["stats_thresholds"] = pack["thresholds"]
    settings["stats_threshold_pack_id"] = pack["id"]
    return (
        settings,
        stp.pack_options() if update_options else no_update,
        pack["id"] if update_options else no_update,
        pack["thresholds"],
        int(revision or 0) + (1 if bump else 0),
        status,
        clear_name,
    )
