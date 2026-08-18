"""Settings page: score bands, filter tiers, histogram bins, and colors."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, html, no_update, register_page
import dash_bootstrap_components as dbc

import ui_settings as us

register_page(__name__, path="/settings", name="Settings")

BAND_LABELS = (
    ("elite", "Elite"),
    ("good", "Good"),
    ("ok", "OK"),
    ("poor", "Poor"),
)


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
                        dbc.Input(
                            id={"type": "st-color", "band": band, "part": part},
                            type="text",
                            value=colors[part],
                            debounce=True,
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
    return [
        dbc.Card(
            [
                dbc.CardHeader("Filter dropdowns"),
                dbc.CardBody(
                    [
                        html.P(
                            "These populate the Max age and Min score menus on Role scores. "
                            "Any is always included.",
                            className="text-muted",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.Label("Age tiers"),
                                        dbc.Input(
                                            id="st-age-tiers",
                                            value=us.format_list(settings["age_tiers"]),
                                            debounce=True,
                                        ),
                                        html.Small(
                                            "Comma-separated maximum ages.",
                                            className="text-muted",
                                        ),
                                    ],
                                    md=6,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Min score tiers"),
                                        dbc.Input(
                                            id="st-min-score-tiers",
                                            value=us.format_list(settings["min_score_tiers"]),
                                            debounce=True,
                                        ),
                                        html.Small(
                                            "Comma-separated floors, e.g. 11, 12, 12.5, 13.",
                                            className="text-muted",
                                        ),
                                    ],
                                    md=6,
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
                                        html.Label("Elite ≥"),
                                        dbc.Input(
                                            id="st-band-elite",
                                            type="number",
                                            min=0,
                                            max=20,
                                            step=0.5,
                                            value=bands["elite"],
                                        ),
                                    ],
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Good ≥"),
                                        dbc.Input(
                                            id="st-band-good",
                                            type="number",
                                            min=0,
                                            max=20,
                                            step=0.5,
                                            value=bands["good"],
                                        ),
                                    ],
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("OK ≥"),
                                        dbc.Input(
                                            id="st-band-ok",
                                            type="number",
                                            min=0,
                                            max=20,
                                            step=0.5,
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
                dbc.CardHeader("Histogram bins"),
                dbc.CardBody(
                    [
                        html.Label("Cut points"),
                        dbc.Input(
                            id="st-hist-edges",
                            value=us.format_list(settings["hist_edges"]),
                            debounce=True,
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
            className="mb-3",
        ),
        html.Div(
            [
                dbc.Button("Save settings", id="st-save", color="primary", className="me-2"),
                dbc.Button("Reset defaults", id="st-reset", color="secondary", outline=True),
                html.Span(id="st-status", className="st-status"),
            ],
            className="st-actions mb-4",
        ),
    ]


layout = dbc.Container(
    [
        html.H1("Settings"),
        html.P(
            "Control the Role scores magic numbers: filter menus, score bands, "
            "histogram bins, and colors.",
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
    values = []
    for spec in specs:
        ident = spec["id"]
        values.append(settings["colors"][ident["band"]][ident["part"]])
    return values


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
    Output("ui-settings", "data"),
    Output("st-status", "children"),
    Output("st-age-tiers", "value"),
    Output("st-min-score-tiers", "value"),
    Output("st-band-elite", "value"),
    Output("st-band-good", "value"),
    Output("st-band-ok", "value"),
    Output("st-hist-edges", "value"),
    Output({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    Input("st-save", "n_clicks"),
    Input("st-reset", "n_clicks"),
    State("st-age-tiers", "value"),
    State("st-min-score-tiers", "value"),
    State("st-band-elite", "value"),
    State("st-band-good", "value"),
    State("st-band-ok", "value"),
    State("st-hist-edges", "value"),
    State({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    prevent_initial_call=True,
)
def save_settings(
    save_n,
    reset_n,
    ages,
    mins,
    elite,
    good,
    ok,
    edges,
    color_values,
):
    if not ctx.triggered_id:
        return (no_update,) * 9
    specs = ctx.states_list[-1] if ctx.states_list else []
    if ctx.triggered_id == "st-reset":
        settings = us.save(us.DEFAULTS)
        status = "Restored default thresholds and colors."
    else:
        settings = us.save(
            {
                "age_tiers": ages,
                "min_score_tiers": mins,
                "bands": {"elite": elite, "good": good, "ok": ok},
                "hist_edges": edges,
                "colors": _colors_from_state(color_values),
            }
        )
        status = "Saved."
    return (
        settings,
        status,
        us.format_list(settings["age_tiers"]),
        us.format_list(settings["min_score_tiers"]),
        settings["bands"]["elite"],
        settings["bands"]["good"],
        settings["bands"]["ok"],
        us.format_list(settings["hist_edges"]),
        _color_values_for(settings, specs),
    )
