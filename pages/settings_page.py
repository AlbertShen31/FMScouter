"""Settings page: packs, Role scores options, and Player stats threshold packs."""
from __future__ import annotations

import copy
from urllib.parse import parse_qs

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon
import services.role_config as rc
import scoring.role_scorer as rs
from scoring.personality_tiers import tier_defs
from scoring.stats_scorer import (
    benchmarks,
    metric_defs,
    percentile_marks,
)
import services.stats_threshold_packs as stp
import services.ui_settings as us

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

# Shared display order for threshold-editor categories (storage ids vary by group).
_THRESH_CATEGORY_ORDER = {
    "defending": 0,
    "gk_def": 0,
    "final_third": 1,
    "goalkeeping": 1,
    "possession": 2,
    "gk_possession": 2,
}

SETTINGS_SECTIONS = (
    ("app-filters", "App & filters"),
    ("display", "Display"),
    ("role-scores", "Role scores"),
    ("player-stats", "Player stats"),
)

_LEGACY_SECTION_MAP = {
    "general": "app-filters",
}

SECTION_SAVE_KEYS: dict[str, tuple[str, ...]] = {
    "st-save-app-filters": (
        "preferred_theme",
        "page_size",
        "page_size_options",
        "depth_undo_max",
        "age_tiers",
        "foot_thresholds",
        "default_minutes_required",
        "exclude_limited_leagues_adaptive_bounds",
    ),
    "st-save-display": (
        "bands",
        "attribute_bands",
        "colors",
        "attribute_colors",
        "personality_tier_colors",
        "tier_badge_colors",
    ),
    "st-save-role": (
        "tier_weights",
        "hybrid_weights",
        "set_piece_profiles",
        "hist_edges",
    ),
}

def _card_header(title: str, tip: str | None = None, *, help_id: str | None = None) -> dbc.CardHeader:
    if not tip:
        return dbc.CardHeader(title)
    hid = help_id or (
        "st-help-"
        + title.lower().replace(" & ", "-").replace("&", "and").replace(" ", "-")
    )
    return dbc.CardHeader(
        html.Div(
            [html.Span(title), *help_icon(tip, hid)],
            className="rs-card-header-title",
        )
    )


def _section_heading(
    title: str,
    blurb: str | None = None,
    *,
    help_id: str | None = None,
) -> html.Div:
    row: list = [html.H2(title, className="st-section-heading")]
    if blurb:
        hid = help_id or f"st-help-section-{title.lower().replace(' ', '-')}"
        row.extend(help_icon(blurb, hid))
    return html.Div(
        html.Div(row, className="st-section-head-row"),
        className="st-section-head",
    )


def _set_piece_attr_options() -> list[dict[str, str]]:
    return [
        {"value": code, "label": f"{code} — {label}"}
        for code, label in sorted(rc.ATTR_LABELS.items(), key=lambda item: item[0])
    ]


def _set_piece_editor(settings: dict) -> html.Div:
    profiles = us.set_piece_profiles(settings)
    weights = us.tier_weights(settings)
    options = _set_piece_attr_options()
    rows = []
    for profile in profiles:
        pid = profile["id"]
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(profile["label"], className="rs-set-piece-name"),
                            html.Span(
                                profile.get("detail") or "",
                                className="rs-set-piece-detail",
                            ),
                        ],
                        className="st-sp-head",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                dmc.MultiSelect(
                                    id={"type": "st-sp-key", "profile": pid},
                                    label="Key",
                                    data=options,
                                    value=list(profile.get("key") or []),
                                    searchable=True,
                                    clearable=True,
                                ),
                                md=4,
                            ),
                            dbc.Col(
                                dmc.MultiSelect(
                                    id={"type": "st-sp-preferred", "profile": pid},
                                    label="Preferred",
                                    data=options,
                                    value=list(profile.get("preferred") or []),
                                    searchable=True,
                                    clearable=True,
                                ),
                                md=4,
                            ),
                            dbc.Col(
                                dmc.MultiSelect(
                                    id={"type": "st-sp-useful", "profile": pid},
                                    label="Useful",
                                    data=options,
                                    value=list(profile.get("useful") or []),
                                    searchable=True,
                                    clearable=True,
                                ),
                                md=4,
                            ),
                        ],
                        className="g-2",
                    ),
                    html.Div(
                        id={"type": "st-sp-formula", "profile": pid},
                        children=rs.set_piece_formula(profile, weights),
                        className="rs-set-piece-formula",
                    ),
                ],
                className="st-sp-profile",
            )
        )
    return html.Div(rows, className="rs-set-piece-formulas st-set-piece-formulas")


def _badge_color_row(tier: str, label: str, color: str) -> html.Div:
    return html.Div(
        [
            html.Div(label, className="st-color-name"),
            html.Div(
                [
                    html.Span(
                        className="st-color-swatch",
                        style={"backgroundColor": color},
                    ),
                    dmc.TextInput(
                        id={"type": "st-badge-color", "tier": tier},
                        value=color,
                        debounce=500,
                        className="st-color-text",
                        placeholder="#rrggbb",
                    ),
                ],
                className="st-color-controls",
            ),
        ],
        className="st-color-row st-badge-color-row",
    )


def _pers_color_row(tier: str, label: str, colors: dict, description: str = "") -> html.Div:
    label_row: list = [html.Div(label, className="st-color-name")]
    if description:
        label_row.extend(help_icon(description, f"st-help-pers-{tier}"))
    return html.Div(
        [
            html.Div(label_row, className="st-pers-tier-meta st-pers-tier-label-row"),
            html.Div(
                [
                    html.Span(
                        ["Preview", html.Span(className="st-swatch")],
                        className=f"st-preview rs-legend-chip pers-tier-{tier}",
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
                                    id={"type": "st-pers-color", "tier": tier, "part": part},
                                    value=colors[part],
                                    debounce=500,
                                    className="st-color-text",
                                    placeholder="#rrggbb",
                                ),
                            ],
                            className="st-color-field",
                        )
                        for part in us.PERSONALITY_TIER_COLOR_PARTS
                    ],
                ],
                className="st-color-controls",
            ),
        ],
        className="st-color-row st-pers-color-row",
    )


def _color_row(band: str, label: str, colors: dict, *, id_type: str = "st-color") -> html.Div:
    return html.Div(
        [
            html.Div(label, className="st-color-name"),
            html.Div(
                [
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
                                    id={"type": id_type, "band": band, "part": part},
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
                className="st-color-controls",
            ),
        ],
        className="st-color-row",
    )


def _section_save_row(save_id: str, status_id: str) -> html.Div:
    return html.Div(
        [
            dmc.Button("Save", id=save_id, className="st-section-save-btn"),
            html.Div(id=status_id, className="st-status"),
        ],
        className="st-section-save-row",
    )


def _settings_pack_bar(settings: dict) -> dbc.Card:
    default_note = (
        "Default uses built-in values until you save; those are stored "
        "locally and can be restored with Reset defaults."
        if us.is_builtin(settings.get("id"))
        else "Named settings packs save to their own files."
    )
    return dbc.Card(
        [
            _card_header("Settings pack", default_note, help_id="st-help-settings-pack"),
            dbc.CardBody(
                [
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
                ]
            ),
        ],
        className="mb-3 st-settings-pack-bar",
    )


def _category_options(group: str) -> list[dict[str, str]]:
    """Category choices for the threshold editor, ordered Defending → Final third/GK → Possession."""
    block = benchmarks()["benchmarks"].get(group) or {}
    labels: dict[str, str] = {}
    for domain in ("outfield", "gk"):
        for cat in benchmarks()["categories"].get(domain) or []:
            labels[cat["id"]] = cat["label"]
    options = [
        {"value": cat_id, "label": labels.get(cat_id, cat_id)}
        for cat_id in block.keys()
    ]
    options.sort(key=lambda opt: _THRESH_CATEGORY_ORDER.get(opt["value"], 99))
    return options


def _default_thresh_category(group: str) -> str:
    if (group or "").strip().lower() == "gk":
        return "goalkeeping"
    for opt in _category_options(group):
        if opt["value"] in ("defending", "gk_def"):
            return opt["value"]
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


def _app_filters_panel(settings: dict) -> list:
    return [
        _section_heading(
            "App & filters",
            "App shell and shared filter defaults for Role scores, Player stats, and Profiles.",
        ),
        dbc.Card(
            [
                _card_header(
                    "Appearance & tables",
                    "Preferred theme stays in sync with the navbar Light/Dark button "
                    "(also applied on Save and when loading a pack). Page size options are "
                    "comma-separated; the default must be one of them. Recently removed limit "
                    "is how many Profiles depth/shortlist deletes stay available to restore (1–50).",
                    help_id="st-help-appearance",
                ),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    dmc.Select(
                                        id={"type": "st-preferred-theme", "index": 0},
                                        label="Preferred theme",
                                        data=[
                                            {"label": "Dark", "value": "dark"},
                                            {"label": "Light", "value": "light"},
                                        ],
                                        value=settings.get("preferred_theme") or "dark",
                                        clearable=False,
                                        searchable=False,
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    dmc.Select(
                                        id="st-page-size-default",
                                        label="Default rows per page",
                                        data=[
                                            {"label": str(opt), "value": str(opt)}
                                            for opt in settings.get("page_size_options")
                                            or us.DEFAULTS["page_size_options"]
                                        ],
                                        value=str(settings.get("page_size") or 50),
                                        clearable=False,
                                        searchable=False,
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    dmc.TextInput(
                                        id="st-page-size-options",
                                        label="Page size options",
                                        value=us.format_page_size_options(settings),
                                        debounce=500,
                                        placeholder="25, 50, 100",
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-depth-undo-max",
                                        label="Recently removed limit",
                                        value=settings.get("depth_undo_max"),
                                        min=1,
                                        max=50,
                                        step=1,
                                    ),
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
                _card_header(
                    "Age filter",
                    "Comma-separated maximum ages for the Max age menu on Role scores "
                    "and Player stats. Any is always included.",
                    help_id="st-help-age-filter",
                ),
                dbc.CardBody(
                    [
                        dmc.TextInput(
                            id="st-age-tiers",
                            label="Age tiers",
                            value=us.format_list(settings["age_tiers"], kind="age"),
                            debounce=500,
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                _card_header(
                    "Footedness",
                    "Strength scale is 1 (very weak) through 6 (very strong). Each footedness "
                    "filter uses its own minimum rating for that foot (Role scores and Player stats).",
                    help_id="st-help-footedness",
                ),
                dbc.CardBody(
                    [
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
                _card_header(
                    "Minutes requirement",
                    "Default minutes used to seed the Player stats minutes filter, "
                    "adaptive percentile bounds (dataset min/max), and related Profiles views. "
                    "Limited-tracking leagues can be excluded from those bounds by default.",
                    help_id="st-help-minutes",
                ),
                dbc.CardBody(
                    [
                        dmc.NumberInput(
                            id="st-default-minutes",
                            label="Default minutes required",
                            value=settings.get("default_minutes_required"),
                            min=0,
                            max=20000,
                            step=90,
                        ),
                        dmc.Switch(
                            id="st-exclude-limited-adaptive",
                            label="Exclude limited data leagues from adaptive percentile bounds",
                            checked=settings.get(
                                "exclude_limited_leagues_adaptive_bounds", True
                            ),
                            className="mt-3",
                        ),
                        _section_save_row("st-save-app-filters", "st-status-app-filters"),
                    ]
                ),
            ],
            className="mb-3",
        ),
    ]


def _display_panel(settings: dict) -> list:
    bands = settings["bands"]
    attr_bands = settings["attribute_bands"]
    badge = settings["tier_badge_colors"]
    return [
        _section_heading(
            "Display",
            "Score and attribute bands, colors, and legend styling across Role scores, "
            "Player stats, Profiles, and Role configs.",
        ),
        dbc.Card(
            [
                _card_header(
                    "Score bands",
                    "Used for squad-depth coloring, table cell colors, and the Poor cutoff "
                    "across Role scores and Profiles.",
                    help_id="st-help-score-bands",
                ),
                dbc.CardBody(
                    [
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
                _card_header(
                    "Attribute bands",
                    "Used for attribute value highlighting in player modals on Role scores "
                    "and Profiles. FM attributes are whole numbers from 1–20; defaults "
                    "map to 16–20 (Elite), 11–15 (Good), 6–10 (OK), and 1–5 (Poor).",
                    help_id="st-help-attribute-bands",
                ),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-attr-band-elite",
                                        label="Elite ≥",
                                        min=1,
                                        max=20,
                                        step=1,
                                        value=attr_bands["elite"],
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-attr-band-good",
                                        label="Good ≥",
                                        min=1,
                                        max=20,
                                        step=1,
                                        value=attr_bands["good"],
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-attr-band-ok",
                                        label="OK ≥",
                                        min=1,
                                        max=20,
                                        step=1,
                                        value=attr_bands["ok"],
                                    ),
                                    md=3,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Poor"),
                                        html.Div(
                                            id="st-attr-poor-cut",
                                            children=f"< {attr_bands['ok']}",
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
                _card_header(
                    "Band colors",
                    "Background and text color table cells and legend chips. "
                    "Bar is the squad-depth segment. Enter hex colors like #dcfce7.",
                    help_id="st-help-band-colors",
                ),
                dbc.CardBody(
                    [
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
        dbc.Card(
            [
                _card_header(
                    "Attribute band colors",
                    "Background and text colors for attribute cells in player modals. "
                    "Defaults match score band colors until you change them.",
                    help_id="st-help-attribute-colors",
                ),
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                _color_row(
                                    band,
                                    label,
                                    settings["attribute_colors"][band],
                                    id_type="st-attr-color",
                                )
                                for band, label in BAND_LABELS
                            ],
                            className="st-color-list",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                _card_header(
                    "Personality tier colors",
                    "Background and text colors for Personality cells and modal labels. "
                    "Tiers follow the FM personality guide (Excellent → Poor).",
                    help_id="st-help-personality-colors",
                ),
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                _pers_color_row(
                                    tier["id"],
                                    tier["label"],
                                    settings["personality_tier_colors"][tier["id"]],
                                    tier.get("description") or "",
                                )
                                for tier in tier_defs()
                            ],
                            className="st-color-list",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                _card_header(
                    "Role config badge colors",
                    "Colors for key / preferred / useful on the Role configs page "
                    "(CSS variables --rc-key, --rc-green, --rc-blue). "
                    "The same values apply in dark and light themes — pick colors that work for both.",
                    help_id="st-help-badge-colors",
                ),
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                _badge_color_row("key", "Key", badge["key"]),
                                _badge_color_row("preferred", "Preferred", badge["preferred"]),
                                _badge_color_row("useful", "Useful", badge["useful"]),
                            ],
                            className="st-color-list",
                        ),
                        _section_save_row("st-save-display", "st-status-display"),
                    ]
                ),
            ],
            className="mb-3",
        ),
    ]


def _role_panel(settings: dict) -> list:
    tier_w = settings["tier_weights"]
    hybrid_w = settings["hybrid_weights"]
    return [
        _section_heading(
            "Role scores",
            "Role-only options: scoring weights, set-piece formulas, and histogram bins.",
        ),
        dbc.Card(
            [
                _card_header(
                    "Active scoring weights pack",
                    "Attribute key / preferred / useful weights used on Role scores. "
                    "Percentile threshold packs are managed under Player stats.",
                    help_id="st-help-scoring-weights-pack",
                ),
                dbc.CardBody(
                    [
                        dmc.Select(
                            id="st-role-weights-pack",
                            label="Scoring weights",
                            data=rc.pack_options(),
                            value=rc.active_pack_id(),
                            clearable=False,
                            searchable=False,
                        ),
                        html.Small(
                            [
                                dcc.Link("Edit on Role configs", href="/role-config"),
                                ".",
                            ],
                            className="text-muted d-block mt-1",
                        ),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                _card_header(
                    "Scoring weights",
                    "Tier multipliers for role and set-piece scores. "
                    "Hybrid weights combine IP and OOP part scores.",
                    help_id="st-help-scoring-weights",
                ),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-tier-key",
                                        label="Key ×",
                                        min=0.1,
                                        max=20,
                                        step=0.5,
                                        decimalScale=2,
                                        value=tier_w["key"],
                                    ),
                                    md=2,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-tier-preferred",
                                        label="Preferred ×",
                                        min=0.1,
                                        max=20,
                                        step=0.5,
                                        decimalScale=2,
                                        value=tier_w["preferred"],
                                    ),
                                    md=2,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-tier-useful",
                                        label="Useful ×",
                                        min=0.1,
                                        max=20,
                                        step=0.5,
                                        decimalScale=2,
                                        value=tier_w["useful"],
                                    ),
                                    md=2,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-hybrid-ip",
                                        label="Hybrid IP ×",
                                        min=0.1,
                                        max=20,
                                        step=0.5,
                                        decimalScale=2,
                                        value=hybrid_w["ip"],
                                    ),
                                    md=2,
                                ),
                                dbc.Col(
                                    dmc.NumberInput(
                                        id="st-hybrid-oop",
                                        label="Hybrid OOP ×",
                                        min=0.1,
                                        max=20,
                                        step=0.5,
                                        decimalScale=2,
                                        value=hybrid_w["oop"],
                                    ),
                                    md=2,
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
                _card_header(
                    "Set-piece formulas",
                    "Edit key / preferred / useful attributes per type. "
                    "Preview uses the scoring weights above.",
                    help_id="st-help-set-piece-formulas",
                ),
                dbc.CardBody(
                    [
                        html.P(
                            id="st-set-piece-hint",
                            children=rs.set_piece_hint(tier_w),
                            className="text-muted",
                        ),
                        _set_piece_editor(settings),
                    ]
                ),
            ],
            className="mb-3",
        ),
        dbc.Card(
            [
                _card_header(
                    "Histogram bins",
                    "Comma-separated edges. The first value is the top of the lowest band "
                    "(so 10 makes that band <10). The last value starts the open-ended top bin.",
                    help_id="st-help-histogram-bins",
                ),
                dbc.CardBody(
                    [
                        dmc.TextInput(
                            id="st-hist-edges",
                            label="Cut points",
                            value=us.format_list(settings["hist_edges"]),
                            debounce=500,
                        ),
                        html.Div(
                            id="st-hist-preview",
                            children=us.hist_preview(settings),
                            className="st-preview-line",
                        ),
                        _section_save_row("st-save-role", "st-status-role"),
                    ]
                ),
            ],
            className="mb-3",
        ),
    ]


def _player_panel(thresh_pack: dict, settings: dict | None = None) -> list:
    settings = us.normalize(settings)
    tree = thresh_pack["thresholds"]
    group0 = "gk"
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
                _card_header(
                    "Percentile threshold pack",
                    note,
                    help_id="st-help-percentile-pack",
                ),
                dbc.CardBody(
                    [
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
                _card_header(
                    "Statistic percentile thresholds",
                    "Pick a position group and category, then edit the four cut-points. "
                    "Categories are ordered Defending, Final third / Goalkeeping, then Possession. "
                    "Save this section to apply the active pack on Player stats.",
                    help_id="st-help-stat-thresholds",
                ),
                dbc.CardBody(
                    [
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
    active = section if section in allowed else _LEGACY_SECTION_MAP.get(section or "", "app-filters")
    if active not in allowed:
        active = "app-filters"
    return dbc.Container(
        [
            html.Div(
                [
                    html.H1("Settings", className="mb-0"),
                    *help_icon(
                        "Use the side nav to jump between sections. Each section has its own Save. "
                        "The settings pack applies across all tabs; Player stats percentiles use "
                        f"separate named packs (built-in: {stp.BUILTIN_NAME}).",
                        "st-help-page",
                    ),
                ],
                className="rs-page-title-row mb-3",
            ),
            dcc.Location(id="st-settings-url", refresh=False),
            dcc.Store(id="st-settings-section", data=active),
            dcc.Store(id="st-thresh-data", data=thresh_pack["thresholds"]),
            dcc.Store(id="st-thresh-revision", data=0),
            _settings_pack_bar(settings),
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
                                "app-filters",
                                _app_filters_panel(settings),
                                active=active == "app-filters",
                            ),
                            _panel(
                                "display",
                                _display_panel(settings),
                                active=active == "display",
                            ),
                            _panel(
                                "role-scores",
                                _role_panel(settings),
                                active=active == "role-scores",
                            ),
                            _panel(
                                "player-stats",
                                _player_panel(thresh_pack, settings),
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
    if requested in allowed:
        return requested
    if requested in _LEGACY_SECTION_MAP:
        return _LEGACY_SECTION_MAP[requested]
    return None


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


def _color_values_for(settings: dict, specs, *, colors_key: str = "colors") -> list[str]:
    colors = settings[colors_key]
    return [
        colors[spec["id"]["band"]][spec["id"]["part"]]
        for spec in specs
    ]


def _colors_from_state(color_values, specs, *, id_type: str = "st-color") -> dict[str, dict[str, str]]:
    color_map = {band: {} for band in us.BAND_KEYS}
    for spec, value in zip(specs or [], color_values or []):
        ident = spec["id"]
        if ident.get("type") != id_type:
            continue
        color_map[ident["band"]][ident["part"]] = value
    return color_map


def _badge_colors_from_state(values, specs) -> dict[str, str]:
    out = {}
    for spec, value in zip(specs or [], values or []):
        tier = spec["id"]["tier"]
        out[tier] = value
    return out


def _badge_values_for(settings: dict, specs) -> list[str]:
    colors = settings["tier_badge_colors"]
    return [colors[spec["id"]["tier"]] for spec in specs]


def _pers_colors_from_state(values, specs) -> dict[str, dict[str, str]]:
    color_map = {tier: {} for tier in us.PERSONALITY_TIER_KEYS}
    for spec, value in zip(specs or [], values or []):
        ident = spec["id"]
        color_map[ident["tier"]][ident["part"]] = value
    return color_map


def _pers_color_values_for(settings: dict, specs) -> list[str]:
    colors = settings["personality_tier_colors"]
    return [
        colors[spec["id"]["tier"]][spec["id"]["part"]]
        for spec in specs
    ]


def _set_piece_lists_from_state(values, specs) -> dict[str, list]:
    out: dict[str, list] = {}
    for spec, value in zip(specs or [], values or []):
        out[spec["id"]["profile"]] = list(value or [])
    return out


def _set_piece_profiles_from_state(key_map, pref_map, useful_map) -> list[dict]:
    profiles = []
    for builtin in rs.SET_PIECE_PROFILES:
        pid = builtin["id"]
        profiles.append(
            {
                "id": pid,
                "key": key_map.get(pid, list(builtin.get("key") or [])),
                "preferred": pref_map.get(pid, list(builtin.get("preferred") or [])),
                "useful": useful_map.get(pid, list(builtin.get("useful") or [])),
            }
        )
    return us.normalize_set_piece_profiles(profiles)


def _sp_values_for(settings: dict, specs, tier: str) -> list:
    profiles = {p["id"]: p for p in us.set_piece_profiles(settings)}
    return [list(profiles.get(spec["id"]["profile"], {}).get(tier) or []) for spec in specs]


def _role_form_values(
    settings: dict,
    color_specs,
    attr_color_specs,
    badge_specs,
    pers_specs,
    sp_key_specs,
    sp_pref_specs,
    sp_useful_specs,
) -> tuple:
    feet = settings["foot_thresholds"]
    tw = settings["tier_weights"]
    hw = settings["hybrid_weights"]
    page_opts = [
        {"label": opt, "value": opt} for opt in us.page_size_options(settings)
    ]
    return (
        us.format_list(settings["age_tiers"], kind="age"),
        settings["bands"]["elite"],
        settings["bands"]["good"],
        settings["bands"]["ok"],
        settings["attribute_bands"]["elite"],
        settings["attribute_bands"]["good"],
        settings["attribute_bands"]["ok"],
        str(feet["left"]),
        str(feet["both"]),
        str(feet["right"]),
        us.format_list(settings["hist_edges"]),
        _color_values_for(settings, color_specs),
        _color_values_for(settings, attr_color_specs, colors_key="attribute_colors"),
        tw["key"],
        tw["preferred"],
        tw["useful"],
        hw["ip"],
        hw["oop"],
        _badge_values_for(settings, badge_specs),
        _pers_color_values_for(settings, pers_specs),
        _sp_values_for(settings, sp_key_specs, "key"),
        _sp_values_for(settings, sp_pref_specs, "preferred"),
        _sp_values_for(settings, sp_useful_specs, "useful"),
        [settings["preferred_theme"]],
        page_opts,
        str(settings["page_size"]),
        us.format_page_size_options(settings),
        settings["default_minutes_required"],
        settings["depth_undo_max"],
        settings["exclude_limited_leagues_adaptive_bounds"],
    )


def _refresh_ui_settings(settings: dict) -> dict:
    """Re-attach the active stats-threshold tree after a pack change."""
    return us.normalize(settings)


def _preferred_theme_value(raw) -> str:
    if isinstance(raw, (list, tuple)):
        raw = (raw or [None])[0]
    return us.normalize_preferred_theme(raw)


def _save_settings_pack(pack_id: str, draft: dict, *, section: str | None = None) -> dict:
    """Persist the active settings pack, optionally updating one section only."""
    current = us.read_pack(pack_id)
    name = current.get("name")
    if section:
        keys = SECTION_SAVE_KEYS[section]
        patch = {key: draft[key] for key in keys}
        normalized = us.normalize({**current, **patch}, pack_id=pack_id, name=name)
        merged = copy.deepcopy(current)
        for key in keys:
            merged[key] = normalized[key]
        merged["id"] = pack_id
        if not us.is_builtin(pack_id):
            merged["name"] = name
        return us.save(merged, pack_id)
    payload = dict(draft)
    if not us.is_builtin(pack_id):
        payload["name"] = name
    return us.save(payload, pack_id)


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
        section = triggered.get("section") or current or "app-filters"
        return _section_view(section)
    from_url = _section_from_search(search)
    if from_url:
        return _section_view(from_url)
    if triggered == "st-settings-url" or triggered is None:
        return _section_view(current or "app-filters")
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
    Output("st-attr-poor-cut", "children"),
    Input("st-attr-band-ok", "value"),
)
def preview_attr_poor(ok):
    threshold = ok if ok is not None else us.DEFAULTS["attribute_bands"]["ok"]
    return f"< {int(threshold)}"


@callback(
    Output("st-foot-preview", "children"),
    Input("st-foot-left", "value"),
    Input("st-foot-both", "value"),
    Input("st-foot-right", "value"),
)
def preview_foot(left, both, right):
    return rs.foot_filter_help({"left": left, "both": both, "right": right})


@callback(
    Output("st-page-size-default", "data"),
    Output("st-page-size-default", "value", allow_duplicate=True),
    Input("st-page-size-options", "value"),
    State("st-page-size-default", "value"),
    prevent_initial_call=True,
)
def sync_page_size_choices(options_text, current):
    opts = us.normalize_page_size_options(options_text)
    data = [{"label": str(opt), "value": str(opt)} for opt in opts]
    value = str(us.normalize_page_size(current, opts))
    return data, value


@callback(
    Output("st-set-piece-hint", "children"),
    Output({"type": "st-sp-formula", "profile": ALL}, "children"),
    Input("st-tier-key", "value"),
    Input("st-tier-preferred", "value"),
    Input("st-tier-useful", "value"),
    Input({"type": "st-sp-key", "profile": ALL}, "value"),
    Input({"type": "st-sp-preferred", "profile": ALL}, "value"),
    Input({"type": "st-sp-useful", "profile": ALL}, "value"),
)
def preview_set_piece_formulas(key_w, pref_w, useful_w, keys, prefs, usefuls):
    weights = us.normalize_tier_weights(
        {"key": key_w, "preferred": pref_w, "useful": useful_w}
    )
    key_specs = ctx.inputs_list[3] if len(ctx.inputs_list) > 3 else []
    pref_specs = ctx.inputs_list[4] if len(ctx.inputs_list) > 4 else []
    useful_specs = ctx.inputs_list[5] if len(ctx.inputs_list) > 5 else []
    key_map = _set_piece_lists_from_state(keys, key_specs)
    pref_map = _set_piece_lists_from_state(prefs, pref_specs)
    useful_map = _set_piece_lists_from_state(usefuls, useful_specs)
    profiles = _set_piece_profiles_from_state(key_map, pref_map, useful_map) or [
        dict(p) for p in rs.SET_PIECE_PROFILES
    ]
    formula_specs = ctx.outputs_list[1] if len(ctx.outputs_list) > 1 else []
    by_id = {p["id"]: p for p in profiles}
    fallback = dict(rs.SET_PIECE_PROFILES[0])
    lines = [
        rs.set_piece_formula(by_id.get(spec["id"]["profile"]) or fallback, weights)
        for spec in formula_specs
    ]
    return rs.set_piece_hint(weights), lines


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
    attr_elite,
    attr_good,
    attr_ok,
    foot_left,
    foot_both,
    foot_right,
    edges,
    color_values,
    color_specs,
    attr_color_values,
    attr_color_specs,
    tier_key,
    tier_preferred,
    tier_useful,
    hybrid_ip,
    hybrid_oop,
    badge_values,
    badge_specs,
    pers_values,
    pers_specs,
    sp_keys,
    sp_key_specs,
    sp_prefs,
    sp_pref_specs,
    sp_usefuls,
    sp_useful_specs,
    preferred_theme,
    page_size_default,
    page_size_options,
    default_minutes,
    depth_undo_max,
    exclude_limited_adaptive,
) -> dict:
    key_map = _set_piece_lists_from_state(sp_keys, sp_key_specs)
    pref_map = _set_piece_lists_from_state(sp_prefs, sp_pref_specs)
    useful_map = _set_piece_lists_from_state(sp_usefuls, sp_useful_specs)
    return {
        "id": pack_id,
        "age_tiers": ages,
        "bands": {"elite": elite, "good": good, "ok": ok},
        "attribute_bands": {"elite": attr_elite, "good": attr_good, "ok": attr_ok},
        "foot_thresholds": {
            "left": foot_left,
            "both": foot_both,
            "right": foot_right,
        },
        "hist_edges": edges,
        "colors": _colors_from_state(color_values, color_specs, id_type="st-color"),
        "attribute_colors": _colors_from_state(
            attr_color_values, attr_color_specs, id_type="st-attr-color"
        ),
        "tier_weights": {
            "key": tier_key,
            "preferred": tier_preferred,
            "useful": tier_useful,
        },
        "hybrid_weights": {"ip": hybrid_ip, "oop": hybrid_oop},
        "tier_badge_colors": _badge_colors_from_state(badge_values, badge_specs),
        "personality_tier_colors": _pers_colors_from_state(pers_values, pers_specs),
        "set_piece_profiles": _set_piece_profiles_from_state(key_map, pref_map, useful_map),
        "preferred_theme": _preferred_theme_value(preferred_theme),
        "page_size": page_size_default,
        "page_size_options": page_size_options,
        "default_minutes_required": default_minutes,
        "depth_undo_max": depth_undo_max,
        "exclude_limited_leagues_adaptive_bounds": bool(exclude_limited_adaptive),
    }


@callback(
    Output("theme", "data", allow_duplicate=True),
    Output("ui-settings", "data", allow_duplicate=True),
    Input({"type": "st-preferred-theme", "index": ALL}, "value"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def apply_preferred_theme_select(preferred_values, current):
    """Keep Settings preferred theme and the navbar theme toggle in sync."""
    preferred = (preferred_values or [None])[0] if preferred_values else None
    if preferred is None:
        return no_update, no_update
    theme = us.normalize_preferred_theme(preferred)
    if theme == us.normalize_preferred_theme(current):
        return no_update, no_update
    settings = us.set_preferred_theme(theme)
    return theme, settings


@callback(
    Output("ui-settings", "data"),
    Output("st-pack", "data"),
    Output("st-pack", "value"),
    Output("st-age-tiers", "value"),
    Output("st-band-elite", "value"),
    Output("st-band-good", "value"),
    Output("st-band-ok", "value"),
    Output("st-attr-band-elite", "value"),
    Output("st-attr-band-good", "value"),
    Output("st-attr-band-ok", "value"),
    Output("st-foot-left", "value"),
    Output("st-foot-both", "value"),
    Output("st-foot-right", "value"),
    Output("st-hist-edges", "value"),
    Output({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    Output({"type": "st-attr-color", "band": ALL, "part": ALL}, "value"),
    Output("st-tier-key", "value"),
    Output("st-tier-preferred", "value"),
    Output("st-tier-useful", "value"),
    Output("st-hybrid-ip", "value"),
    Output("st-hybrid-oop", "value"),
    Output({"type": "st-badge-color", "tier": ALL}, "value"),
    Output({"type": "st-pers-color", "tier": ALL, "part": ALL}, "value"),
    Output({"type": "st-sp-key", "profile": ALL}, "value"),
    Output({"type": "st-sp-preferred", "profile": ALL}, "value"),
    Output({"type": "st-sp-useful", "profile": ALL}, "value"),
    Output({"type": "st-preferred-theme", "index": ALL}, "value"),
    Output("st-page-size-default", "data", allow_duplicate=True),
    Output("st-page-size-default", "value"),
    Output("st-page-size-options", "value"),
    Output("st-default-minutes", "value"),
    Output("st-depth-undo-max", "value"),
    Output("st-exclude-limited-adaptive", "checked"),
    Output("st-role-weights-pack", "data"),
    Output("st-role-weights-pack", "value"),
    Output("theme", "data", allow_duplicate=True),
    Output("st-status-app-filters", "children"),
    Output("st-status-display", "children"),
    Output("st-status-role", "children"),
    Output("st-new-name", "value"),
    Input("st-pack", "value"),
    Input("st-new", "n_clicks"),
    Input("st-reset", "n_clicks"),
    Input("st-save-app-filters", "n_clicks"),
    Input("st-save-display", "n_clicks"),
    Input("st-save-role", "n_clicks"),
    State("st-new-name", "value"),
    State("st-age-tiers", "value"),
    State("st-band-elite", "value"),
    State("st-band-good", "value"),
    State("st-band-ok", "value"),
    State("st-attr-band-elite", "value"),
    State("st-attr-band-good", "value"),
    State("st-attr-band-ok", "value"),
    State("st-foot-left", "value"),
    State("st-foot-both", "value"),
    State("st-foot-right", "value"),
    State("st-hist-edges", "value"),
    State({"type": "st-color", "band": ALL, "part": ALL}, "value"),
    State({"type": "st-attr-color", "band": ALL, "part": ALL}, "value"),
    State("st-tier-key", "value"),
    State("st-tier-preferred", "value"),
    State("st-tier-useful", "value"),
    State("st-hybrid-ip", "value"),
    State("st-hybrid-oop", "value"),
    State({"type": "st-badge-color", "tier": ALL}, "value"),
    State({"type": "st-pers-color", "tier": ALL, "part": ALL}, "value"),
    State({"type": "st-sp-key", "profile": ALL}, "value"),
    State({"type": "st-sp-preferred", "profile": ALL}, "value"),
    State({"type": "st-sp-useful", "profile": ALL}, "value"),
    State({"type": "st-preferred-theme", "index": ALL}, "value"),
    State("st-page-size-default", "value"),
    State("st-page-size-options", "value"),
    State("st-default-minutes", "value"),
    State("st-depth-undo-max", "value"),
    State("st-exclude-limited-adaptive", "checked"),
    State("st-role-weights-pack", "value"),
    prevent_initial_call=True,
)
def handle_ui_settings(
    pack_id,
    new_n,
    reset_n,
    save_app_filters_n,
    save_display_n,
    save_role_n,
    new_name,
    ages,
    elite,
    good,
    ok,
    attr_elite,
    attr_good,
    attr_ok,
    foot_left,
    foot_both,
    foot_right,
    edges,
    color_values,
    attr_color_values,
    tier_key,
    tier_preferred,
    tier_useful,
    hybrid_ip,
    hybrid_oop,
    badge_values,
    pers_values,
    sp_keys,
    sp_prefs,
    sp_usefuls,
    preferred_theme,
    page_size_default,
    page_size_options,
    default_minutes,
    depth_undo_max,
    exclude_limited_adaptive,
    role_weights_pack,
):
    triggered = ctx.triggered_id
    n_out = 40
    if not triggered:
        return (no_update,) * n_out

    states = ctx.states_list or []
    color_specs = states[12] if len(states) > 12 else []
    attr_color_specs = states[13] if len(states) > 13 else []
    badge_specs = states[19] if len(states) > 19 else []
    pers_specs = states[20] if len(states) > 20 else []
    sp_key_specs = states[21] if len(states) > 21 else []
    sp_pref_specs = states[22] if len(states) > 22 else []
    sp_useful_specs = states[23] if len(states) > 23 else []

    draft = _ui_draft_from_state(
        pack_id,
        ages,
        elite,
        good,
        ok,
        attr_elite,
        attr_good,
        attr_ok,
        foot_left,
        foot_both,
        foot_right,
        edges,
        color_values,
        color_specs,
        attr_color_values,
        attr_color_specs,
        tier_key,
        tier_preferred,
        tier_useful,
        hybrid_ip,
        hybrid_oop,
        badge_values,
        badge_specs,
        pers_values,
        pers_specs,
        sp_keys,
        sp_key_specs,
        sp_prefs,
        sp_pref_specs,
        sp_usefuls,
        sp_useful_specs,
        preferred_theme,
        page_size_default,
        page_size_options,
        default_minutes,
        depth_undo_max,
        exclude_limited_adaptive,
    )
    status_app_filters = no_update
    status_display = no_update
    status_role = no_update
    clear_name = no_update
    update_pack_options = True
    sync_theme = False

    if triggered == "st-pack":
        settings = us.load(pack_id)
        status_app_filters = f"Loaded {settings['name']}."
        sync_theme = True
    elif triggered == "st-reset":
        if pack_id == us.BUILTIN:
            us.clear_default_overrides()
            settings = us.load(us.BUILTIN)
            status_app_filters = "Default restored to built-in values."
        else:
            settings = us.normalize(us.DEFAULTS, pack_id=pack_id, name=None)
            current = us.read_pack(pack_id)
            settings["id"] = current["id"]
            settings["name"] = current["name"]
            status_app_filters = (
                "Form reset to built-in defaults. Save a section to keep them on this pack."
            )
        update_pack_options = False
        sync_theme = True
    elif triggered == "st-new":
        label = str(new_name or "").strip()
        if not label:
            return (
                (no_update,) * (n_out - 4)
                + ("Enter a name to create a new settings file.", no_update, no_update, no_update)
            )
        settings = us.create_pack(label, {**us.read_pack(pack_id), **draft})
        status_app_filters = f"Created {settings['name']}."
        clear_name = ""
        sync_theme = True
    elif triggered in ("st-save-app-filters", "st-save-display"):
        settings = _save_settings_pack(pack_id, draft, section=triggered)
        saved_msg = f"Saved {settings['name']}."
        if triggered == "st-save-app-filters":
            status_app_filters = saved_msg
        else:
            status_display = saved_msg
        sync_theme = True
        if role_weights_pack:
            rc.load_pack(role_weights_pack)
    elif triggered == "st-save-role":
        settings = _save_settings_pack(pack_id, draft, section=triggered)
        status_role = f"Saved Role scores to {settings['name']}."
        if role_weights_pack:
            rc.load_pack(role_weights_pack)
    else:
        return (no_update,) * n_out

    settings = _refresh_ui_settings(settings)
    role_values = _role_form_values(
        settings,
        color_specs,
        attr_color_specs,
        badge_specs,
        pers_specs,
        sp_key_specs,
        sp_pref_specs,
        sp_useful_specs,
    )
    pack_options = us.pack_options() if update_pack_options else no_update
    pack_value = settings["id"] if update_pack_options else no_update
    theme_value = settings["preferred_theme"] if sync_theme else no_update
    role_weights_options = rc.pack_options()
    role_weights_value = rc.active_pack_id()
    return (
        settings,
        pack_options,
        pack_value,
        *role_values,
        role_weights_options,
        role_weights_value,
        theme_value,
        status_app_filters,
        status_display,
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
    n_out = 7
    if not triggered:
        return (no_update,) * n_out
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
                (no_update,) * 5
                + ("Enter a name to create a new percentile pack.", no_update)
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
        return (no_update,) * n_out

    # Refresh ui-settings so Player stats picks up the active threshold tree.
    settings = us.normalize(ui_settings or {})
    settings["stats_thresholds"] = pack["thresholds"]
    settings["stats_threshold_pack_id"] = pack["id"]
    if triggered == "st-save-thresh":
        settings = us.save(settings, settings.get("id"))
    settings = _refresh_ui_settings(settings)
    return (
        settings,
        stp.pack_options() if update_options else no_update,
        pack["id"] if update_options else no_update,
        pack["thresholds"],
        int(revision or 0) + (1 if bump else 0),
        status,
        clear_name,
    )
