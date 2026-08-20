"""Settings page: score bands, age tiers, histogram bins, colors, and saved packs."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

import role_scorer as rs
import ui_settings as us

register_page(__name__, path="/settings", name="Settings")

BAND_LABELS = (
    ("elite", "Elite"),
    ("good", "Good"),
    ("ok", "OK"),
    ("poor", "Poor"),
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


def _form(settings: dict) -> list:
    bands = settings["bands"]
    default_note = (
        "Default uses built-in values until you save changes; those are stored locally "
        "and can be restored with Reset defaults."
        if us.is_builtin(settings.get("id"))
        else "Named packs save to their own files."
    )
    return [
        dbc.Card(
            [
                dbc.CardHeader("Saved settings"),
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
                                            "Save",
                                            id="st-save",
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
                        html.Div(id="st-status", className="st-status mt-2"),
                    ]
                ),
            ],
            className="mb-3",
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
                            "Comma-separated maximum ages for the Role scores Max age menu. Any is always included.",
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
                                    [
                                        dmc.NumberInput(
                                            id="st-band-elite",
                                            label="Elite ≥",
                                            min=0,
                                            max=20,
                                            step=0.5,
                                            decimalScale=1,
                                            value=bands["elite"],
                                        ),
                                    ],
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        dmc.NumberInput(
                                            id="st-band-good",
                                            label="Good ≥",
                                            min=0,
                                            max=20,
                                            step=0.5,
                                            decimalScale=1,
                                            value=bands["good"],
                                        ),
                                    ],
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        dmc.NumberInput(
                                            id="st-band-ok",
                                            label="OK ≥",
                                            min=0,
                                            max=20,
                                            step=0.5,
                                            decimalScale=1,
                                            value=bands["ok"],
                                        ),
                                    ],
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
                            "The threshold is the minimum rating that counts as a usable foot.",
                            className="text-muted",
                        ),
                        dmc.Select(
                            id="st-foot-threshold",
                            label="Usable-foot threshold",
                            data=rs.foot_strength_options(),
                            value=str(
                                settings.get("foot_threshold") or us.DEFAULTS["foot_threshold"]
                            ),
                            clearable=False,
                            searchable=False,
                        ),
                        html.Small(
                            id="st-foot-preview",
                            children=rs.foot_filter_help(settings.get("foot_threshold")),
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
                        html.P(
                            rs.set_piece_hint(),
                            className="text-muted",
                        ),
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
                    ]
                ),
            ],
            className="mb-4",
        ),
    ]


def layout():
    return dbc.Container(
        [
            html.H1("Settings"),
            html.P(
                "Control Role scores age menus, score bands, footedness, set-piece formulas, "
                "histogram bins, and colors. Save named versions so you can switch between them.",
                className="text-muted",
            ),
            *_form(us.load()),
        ],
        className="rs-page st-page",
        fluid=True,
    )


def _colors_from_state(color_values) -> dict[str, dict[str, str]]:
    color_map = {band: {} for band in us.BAND_KEYS}
    specs = ctx.states_list[-1] if ctx.states_list else []
    for spec, value in zip(specs, color_values or []):
        ident = spec["id"]
        color_map[ident["band"]][ident["part"]] = value
    return color_map


def _color_values_for(settings: dict, specs) -> list[str]:
    return [
        settings["colors"][spec["id"]["band"]][spec["id"]["part"]]
        for spec in specs
    ]


def _form_values(settings: dict, specs) -> tuple:
    return (
        settings,
        us.pack_options(),
        settings["id"],
        False,
        us.format_list(settings["age_tiers"], kind="age"),
        settings["bands"]["elite"],
        settings["bands"]["good"],
        settings["bands"]["ok"],
        str(settings.get("foot_threshold") or us.DEFAULTS["foot_threshold"]),
        us.format_list(settings["hist_edges"]),
        _color_values_for(settings, specs),
    )


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
    Input("st-foot-threshold", "value"),
)
def preview_foot(threshold):
    return rs.foot_filter_help(threshold)


@callback(
    Output("ui-settings", "data"),
    Output("st-pack", "data"),
    Output("st-pack", "value"),
    Output("st-save", "disabled"),
    Output("st-age-tiers", "value"),
    Output("st-band-elite", "value"),
    Output("st-band-good", "value"),
    Output("st-band-ok", "value"),
    Output("st-foot-threshold", "value"),
    Output("st-hist-edges", "value"),
    Output({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    Output("st-status", "children"),
    Output("st-new-name", "value"),
    Input("st-pack", "value"),
    Input("st-save", "n_clicks"),
    Input("st-new", "n_clicks"),
    Input("st-reset", "n_clicks"),
    State("st-new-name", "value"),
    State("st-age-tiers", "value"),
    State("st-band-elite", "value"),
    State("st-band-good", "value"),
    State("st-band-ok", "value"),
    State("st-foot-threshold", "value"),
    State("st-hist-edges", "value"),
    State({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    prevent_initial_call=True,
)
def handle_settings(
    pack_id,
    save_n,
    new_n,
    reset_n,
    new_name,
    ages,
    elite,
    good,
    ok,
    foot_threshold,
    edges,
    color_values,
):
    triggered = ctx.triggered_id
    if not triggered:
        return (no_update,) * 13
    specs = ctx.states_list[-1] if ctx.states_list else []
    draft = {
        "id": pack_id,
        "age_tiers": ages,
        "bands": {"elite": elite, "good": good, "ok": ok},
        "foot_threshold": foot_threshold,
        "hist_edges": edges,
        "colors": _colors_from_state(color_values),
    }
    status = ""
    clear_name = no_update
    update_pack = True
    if triggered == "st-pack":
        settings = us.load(pack_id)
        status = f"Loaded {settings['name']}."
    elif triggered == "st-reset":
        if pack_id == us.BUILTIN:
            us.clear_default_overrides()
            settings = us.load(us.BUILTIN)
            status = "Default restored to built-in values."
        else:
            settings = us.normalize(us.DEFAULTS, pack_id=pack_id, name=None)
            current = us.read_pack(pack_id)
            settings["id"] = current["id"]
            settings["name"] = current["name"]
            status = "Form reset to built-in defaults. Save to keep them on this pack."
        update_pack = False
    elif triggered == "st-new":
        label = str(new_name or "").strip()
        if not label:
            return (no_update,) * 11 + ("Enter a name to create a new settings file.", no_update)
        settings = us.create_pack(label, draft)
        status = f"Created {settings['name']}."
        clear_name = ""
    elif triggered == "st-save":
        if us.is_builtin(pack_id):
            settings = us.save(draft, pack_id)
            status = f"Saved {settings['name']} overrides."
            update_pack = True
        else:
            current = us.read_pack(pack_id)
            draft["name"] = current["name"]
            settings = us.save(draft, pack_id)
            status = f"Saved {settings['name']}."
            update_pack = False
    else:
        return (no_update,) * 13
    values = list(_form_values(settings, specs))
    if not update_pack:
        values[1] = no_update
        values[2] = no_update
    return (*values, status, clear_name)
