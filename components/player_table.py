"""Shared player DataTable shell, identity styles, Feet cells, and Rec coloring."""
from __future__ import annotations

import re
from collections.abc import Sequence

from dash import dash_table, html
import dash_mantine_components as dmc

from scoring.role_scorer import FOOT_STRENGTH_NAMES, FootStrength, foot_strength

IDENTITY_TEXT_COLS = frozenset(
    {
        "Name",
        "Age",
        "Height",
        "Position",
        "Feet",
        "Club",
        "Rec",
        "Injury",
        "Division",
        "Nation",
        "Inf",
        "Best Pos",
    }
)
IDENTITY_LEFT_COLS = ("Name", "Position", "Club", "Division", "Nation", "Inf")

# Short table headers → full tooltip label (column id stays the key).
IDENTITY_HEADER_ABBR = {
    "Height": "Ht",
    "Best Pos": "BP",
    "Injury": "INJ",
}
IDENTITY_HEADER_TOOLTIPS = {
    "Height": "Height",
    "Minutes": "Minutes",
    "Best Pos": "Best position",
    "Inf": "Information / status",
    "Injury": "Injury",
    "Division": "Green = top tier · Yellow = professional lower · Red = semi-pro / amateur",
}

_REC_SUFFIX = {"+": 0, "": 1, "-": 2}
_REC_PATTERN = re.compile(r"^([A-Za-z])\s*([+-])?$")

FOOT_STRENGTH_COLORS = {
    FootStrength.VERY_WEAK: "#7f1d1d",
    FootStrength.WEAK: "#dc2626",
    FootStrength.REASONABLE: "#f59e0b",
    FootStrength.FAIRLY_STRONG: "#a3e635",
    FootStrength.STRONG: "#22c55e",
    FootStrength.VERY_STRONG: "#4ade80",
}
_FOOT_UNKNOWN = "#64748b"

PAGE_SIZE_OPTIONS = ("25", "50", "100")


def page_size_select_data(settings=None) -> list[dict[str, str]]:
    import services.ui_settings as us

    options = us.page_size_options(settings) if settings is not None else list(PAGE_SIZE_OPTIONS)
    if not options:
        options = list(PAGE_SIZE_OPTIONS)
    return [{"label": size, "value": size} for size in options]


def default_page_size_value(settings=None) -> str:
    import services.ui_settings as us

    if settings is None:
        return "50"
    return str(us.page_size(settings))


def is_dark_theme(theme: str | None) -> bool:
    return (theme or "dark") != "light"


def identity_header_name(column_id: str) -> str:
    """Display name for identity columns (abbreviations when configured)."""
    return IDENTITY_HEADER_ABBR.get(column_id, column_id)


def identity_header_tooltips(*column_ids: str) -> dict[str, str]:
    """tooltip_header entries for abbreviated identity columns present in `column_ids`."""
    tips: dict[str, str] = {}
    wanted = set(column_ids) if column_ids else set(IDENTITY_HEADER_TOOLTIPS)
    for col_id, label in IDENTITY_HEADER_TOOLTIPS.items():
        if col_id in wanted:
            tips[col_id] = label
    return tips


def foot_color(level: FootStrength | None) -> str:
    if level is None:
        return _FOOT_UNKNOWN
    return FOOT_STRENGTH_COLORS.get(level, _FOOT_UNKNOWN)


def footprint_svg(side: str, color: str, label: str) -> str:
    """Inline SVG sole+toes; `side` is L or R (R is mirrored inside a group)."""
    open_g = '<g transform="translate(24 0) scale(-1 1)">' if side == "R" else ""
    close_g = "</g>" if side == "R" else ""
    return (
        f'<svg class="rs-foot-icon" viewBox="0 0 24 36" width="16" height="24" '
        f'aria-label="{label}" role="img">'
        f"<title>{label}</title>"
        f"{open_g}"
        f'<ellipse cx="12" cy="23" rx="7.2" ry="10.5" fill="{color}"/>'
        f'<ellipse cx="6.2" cy="8.2" rx="2.1" ry="3.2" fill="{color}"/>'
        f'<ellipse cx="10.2" cy="6.4" rx="1.9" ry="3.0" fill="{color}"/>'
        f'<ellipse cx="14.0" cy="6.2" rx="1.8" ry="2.9" fill="{color}"/>'
        f'<ellipse cx="17.4" cy="7.4" rx="1.6" ry="2.6" fill="{color}"/>'
        f'<ellipse cx="19.8" cy="10.0" rx="1.35" ry="2.2" fill="{color}"/>'
        f"{close_g}"
        f"</svg>"
    )


def feet_cell(row: dict) -> str:
    left = foot_strength(row.get("Left Foot") or "")
    right = foot_strength(row.get("Right Foot") or "")
    left_label = FOOT_STRENGTH_NAMES.get(left, "Unknown") if left else "Unknown"
    right_label = FOOT_STRENGTH_NAMES.get(right, "Unknown") if right else "Unknown"
    tip = f"L: {left_label} · R: {right_label}"
    return (
        f'<div class="rs-feet-cell" title="{tip}">'
        f'<span class="rs-feet">'
        f'{footprint_svg("L", foot_color(left), f"Left foot: {left_label}")}'
        f'{footprint_svg("R", foot_color(right), f"Right foot: {right_label}")}'
        f"</span></div>"
    )


def injury_label(value) -> str:
    """Normalized injury text, or empty when the player is fit."""
    text = str(value or "").strip()
    if not text or text in ("-", "—"):
        return ""
    return text


def injury_cell(value) -> str:
    """Markdown cell: medical-cross icon, or empty when fit."""
    if not injury_label(value):
        return ""
    return (
        '<span class="rs-injury-cell">'
        '<svg class="rs-injury-icon" viewBox="0 0 24 24" width="16" height="16" '
        'role="img" aria-hidden="true">'
        '<rect x="10" y="4" width="4" height="16" rx="0.75" fill="currentColor"/>'
        '<rect x="4" y="10" width="16" height="4" rx="0.75" fill="currentColor"/>'
        "</svg></span>"
    )


def injury_tooltip_entry(value) -> dict[str, str]:
    """DataTable tooltip_data row fragment for the Injury column."""
    text = injury_label(value)
    return {"Injury": text} if text else {}


def feet_sort_key(row: dict) -> tuple:
    left = foot_strength(row.get("Left Foot") or "")
    right = foot_strength(row.get("Right Foot") or "")
    l_n = int(left) if left else 0
    r_n = int(right) if right else 0
    return (0, max(l_n, r_n), l_n + r_n) if (l_n or r_n) else (1, 0, 0)


def rec_sort_key(value) -> tuple:
    """A+ before A before A- before B+, with blanks last."""
    text = str(value or "").strip()
    if not text or text in ("-", "—"):
        return (2, 99, 99, text)
    match = _REC_PATTERN.match(text)
    if not match:
        return (1, 99, 99, text.casefold())
    letter = match.group(1).upper()
    suffix = match.group(2) or ""
    return (0, ord(letter) - ord("A"), _REC_SUFFIX[suffix], text)


def style_table() -> dict:
    return {
        "overflowX": "auto",
        "borderRadius": "12px",
        "width": "100%",
        "minWidth": "100%",
    }


def style_cell(*, text_align: str = "right") -> dict:
    return {
        "fontFamily": "Inter, Segoe UI, sans-serif",
        "fontSize": "14px",
        "padding": "8px 10px",
        "whiteSpace": "nowrap",
        "backgroundColor": "transparent",
        "color": "var(--app-text)",
        "border": "1px solid transparent",
        "textAlign": text_align,
        "verticalAlign": "middle",
        "lineHeight": "1.2",
    }


def style_header() -> dict:
    return {
        "fontWeight": "600",
        "textTransform": "uppercase",
        "fontSize": "12px",
        "letterSpacing": "0.04em",
        "backgroundColor": "transparent",
        "color": "var(--app-text)",
        "cursor": "pointer",
        "padding": "10px 28px 10px 10px",
        "height": "auto",
        "minHeight": "46px",
        "whiteSpace": "pre-line",
        "lineHeight": "1.15",
        "verticalAlign": "middle",
        "textAlign": "center",
        "borderBottom": "2px solid var(--app-line)",
    }


def style_cell_conditional(*, extra: Sequence[dict] | None = None) -> list[dict]:
    rules = [
        {
            "if": {"column_id": "Name"},
            "textAlign": "left",
            "cursor": "pointer",
            "color": "var(--app-accent)",
            "fontWeight": "600",
            "textDecoration": "underline",
            "textUnderlineOffset": "3px",
        },
        {"if": {"column_id": "Position"}, "textAlign": "left"},
        {
            "if": {"column_id": "Feet"},
            "textAlign": "center",
            "padding": "8px 10px",
            "minWidth": "84px",
            "width": "84px",
            "overflow": "visible",
        },
        {
            "if": {"column_id": "Injury"},
            "textAlign": "center",
            "minWidth": "44px",
            "width": "48px",
            "maxWidth": "56px",
            "padding": "0",
        },
        {"if": {"column_id": "Club"}, "textAlign": "left"},
    ]
    if extra:
        rules.extend(extra)
    return rules


def style_header_conditional(*, extra: Sequence[dict] | None = None) -> list[dict]:
    rules = [
        {"if": {"column_id": col}, "textAlign": "left"} for col in IDENTITY_LEFT_COLS
    ]
    if extra:
        rules.extend(extra)
    return rules


def _feet_css() -> list[dict]:
    return [
        {
            "selector": ".rs-feet-cell",
            "rule": (
                "display: block !important; width: 100% !important; "
                "text-align: center !important; line-height: 0 !important;"
            ),
        },
        {
            "selector": ".rs-feet",
            "rule": (
                "display: inline-flex !important; "
                "align-items: center; justify-content: center; "
                "gap: 1px; line-height: 0; vertical-align: middle;"
            ),
        },
        {
            "selector": ".rs-foot-icon",
            "rule": (
                "display: block !important; flex-shrink: 0; overflow: visible;"
            ),
        },
        {
            "selector": (
                'td.dash-cell[data-dash-column="Feet"] .dash-cell-value, '
                'td.dash-cell[data-dash-column="Feet"] .markdown, '
                'td.dash-cell[data-dash-column="Feet"] .markdown p'
            ),
            "rule": (
                "width: 100% !important; max-width: 100% !important; "
                "margin: 0 !important; padding: 0 !important; "
                "text-align: center !important; line-height: 0 !important;"
            ),
        },
        {
            "selector": 'td.dash-cell[data-dash-column="Feet"]',
            "rule": (
                "overflow: visible !important; "
                "min-width: 84px !important; "
                "width: 84px !important; "
                "text-align: center !important;"
            ),
        },
        {
            "selector": 'th.dash-header[data-dash-column="Feet"]',
            "rule": (
                "min-width: 84px !important; "
                "width: 84px !important; "
                "text-align: center !important;"
            ),
        },
        {
            "selector": 'td.dash-cell[data-dash-column="Injury"]',
            "rule": (
                "position: relative !important; "
                "text-align: center !important; "
                "min-width: 44px !important; "
                "width: 48px !important; "
                "max-width: 56px !important; "
                "vertical-align: middle !important; "
                "overflow: visible !important; "
                "padding: 0 !important;"
            ),
        },
        {
            "selector": (
                'td.dash-cell[data-dash-column="Injury"] .dash-cell-value, '
                'td.dash-cell[data-dash-column="Injury"] .markdown, '
                'td.dash-cell[data-dash-column="Injury"] .markdown p'
            ),
            "rule": (
                "position: absolute !important; inset: 0 !important; "
                "width: 100% !important; height: 100% !important; "
                "margin: 0 !important; padding: 0 !important; "
                "line-height: 0 !important; text-align: center !important;"
            ),
        },
        {
            "selector": ".rs-injury-cell",
            "rule": (
                "position: absolute !important; "
                "top: 50% !important; left: 50% !important; "
                "transform: translate(-50%, -50%) !important; "
                "display: flex !important; "
                "align-items: center !important; justify-content: center !important; "
                "margin: 0 !important; padding: 0 !important; "
                "line-height: 0 !important; cursor: help;"
            ),
        },
        {
            "selector": ".rs-injury-icon",
            "rule": (
                "display: block !important; color: #fbbf24; "
                "flex-shrink: 0;"
            ),
        },
    ]


def _center_non_identity_css() -> list[dict]:
    skip = (
        ':not([data-dash-column="Name"]):not([data-dash-column="Position"])'
        ':not([data-dash-column="Club"]):not([data-dash-column="Injury"])'
        ':not([data-dash-column="Feet"])'
    )
    return [
        {
            "selector": "td.dash-cell",
            "rule": "vertical-align: middle !important;",
        },
        {
            "selector": f"td.dash-cell{skip}",
            "rule": "text-align: center !important;",
        },
        {
            "selector": (
                f"td.dash-cell{skip} .dash-cell-value, "
                f"td.dash-cell{skip} .markdown, "
                f"td.dash-cell{skip} .markdown p, "
                f"td.dash-cell{skip} p, "
                f"td.dash-cell{skip} span"
            ),
            "rule": (
                "text-align: center !important; margin: 0 !important; "
                "padding: 0 !important; line-height: 1.2 !important;"
            ),
        },
        {
            "selector": (
                "td.dash-cell .dash-cell-value, "
                "td.dash-cell .markdown, "
                "td.dash-cell .markdown p"
            ),
            "rule": "margin: 0 !important; padding: 0 !important; line-height: 1.2 !important;",
        },
        {
            "selector": (
                'th.dash-header:not([data-dash-column="Name"])'
                ':not([data-dash-column="Position"])'
                ':not([data-dash-column="Club"])'
                ':not([data-dash-column="Injury"])'
            ),
            "rule": "text-align: center !important; vertical-align: middle !important;",
        },
    ]


def table_css(
    *,
    extra: Sequence[dict] | None = None,
    center_non_identity: bool = False,
) -> list[dict]:
    rules = [
        {
            "selector": (
                "td:hover, tr:hover td, tr:hover th, th:hover, "
                "td.focused, td.cell--selected, th.focused, "
                "th.cell--selected"
            ),
            "rule": (
                "background-color: var(--table-hover-bg) !important; "
                "color: var(--table-hover-fg) !important;"
            ),
        },
        {
            "selector": "a",
            "rule": (
                "color: inherit !important; text-decoration: underline; "
                "text-underline-offset: 3px; cursor: pointer;"
            ),
        },
        *_feet_css(),
    ]
    if center_non_identity:
        rules.extend(_center_non_identity_css())
    if extra:
        rules.extend(extra)
    return rules


def _rec_grades() -> list[str]:
    grades = [f"{letter}{suffix}" for letter in "ABCDE" for suffix in ("+", "", "-")]
    grades.append("F")
    return grades


def _lerp_channel(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def rec_highlight_styles(theme: str | None = None) -> list[dict]:
    """Color Rec from green (A+) to red (F)."""
    dark = is_dark_theme(theme)
    green_bg = (22, 101, 52) if dark else (220, 252, 231)
    red_bg = (127, 29, 29) if dark else (254, 226, 226)
    green_fg = (74, 222, 128) if dark else (21, 128, 61)
    red_fg = (252, 165, 165) if dark else (185, 28, 28)
    rules = []
    grades = _rec_grades()
    last = max(len(grades) - 1, 1)
    for index, grade in enumerate(grades):
        t = index / last
        bg = "#{:02x}{:02x}{:02x}".format(
            _lerp_channel(green_bg[0], red_bg[0], t),
            _lerp_channel(green_bg[1], red_bg[1], t),
            _lerp_channel(green_bg[2], red_bg[2], t),
        )
        fg = "#{:02x}{:02x}{:02x}".format(
            _lerp_channel(green_fg[0], red_fg[0], t),
            _lerp_channel(green_fg[1], red_fg[1], t),
            _lerp_channel(green_fg[2], red_fg[2], t),
        )
        rules.append(
            {
                "if": {
                    "filter_query": f'{{Rec}} = "{grade}"',
                    "column_id": "Rec",
                },
                "backgroundColor": bg,
                "color": fg,
            }
        )
    return rules


def identity_data_styles(
    theme: str | None = None,
    *,
    position_eligibility: bool = False,
    extra: Sequence[dict] | None = None,
) -> list[dict]:
    """Shared zebra / selection / identity column styles (+ optional PosEligible)."""
    dark = is_dark_theme(theme)
    zebra = "rgba(255,255,255,0.03)" if dark else "rgba(0,0,0,0.025)"
    selected_bg = "rgba(61, 255, 136, 0.14)" if dark else "rgba(34, 139, 87, 0.12)"
    plain = "#f1f5f9" if dark else "#0f172a"
    injury_bg = "rgba(251, 191, 36, 0.18)" if dark else "#fff3cd"
    rules: list[dict] = [
        {"if": {"row_index": "odd"}, "backgroundColor": zebra},
        {
            "if": {"state": "selected"},
            "backgroundColor": selected_bg,
            "border": "1px solid var(--app-accent)",
        },
        {
            "if": {"column_id": "Name"},
            "fontWeight": "600",
            "textAlign": "left",
            "minWidth": "168px",
            "maxWidth": "240px",
            "borderRight": "1px solid var(--app-line)",
            "cursor": "pointer",
            "color": "var(--app-accent)",
            "textDecoration": "underline",
            "textUnderlineOffset": "3px",
        },
        {
            "if": {"column_id": "Club"},
            "color": plain,
            "textAlign": "left",
            "maxWidth": "200px",
        },
        {
            "if": {"column_id": "Position"},
            "textAlign": "left",
            "color": plain,
        },
        {
            "if": {"column_id": "Division"},
            "textAlign": "left",
            "minWidth": "110px",
            "maxWidth": "200px",
            "fontWeight": "600",
        },
        {
            "if": {"column_id": "Feet"},
            "textAlign": "center",
            "padding": "8px 10px",
            "minWidth": "84px",
            "width": "84px",
            "overflow": "visible",
        },
        {
            "if": {"column_id": "Rec"},
            "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            "fontSize": "13px",
            "letterSpacing": "0.03em",
            "fontWeight": "700",
            "textAlign": "center",
            "minWidth": "56px",
            "width": "60px",
            "maxWidth": "72px",
        },
        {
            "if": {"column_id": "Age"},
            "color": plain,
            "textAlign": "center",
            "minWidth": "56px",
            "width": "60px",
            "maxWidth": "72px",
        },
        {
            "if": {"column_id": "Height"},
            "color": plain,
            "textAlign": "center",
            "minWidth": "52px",
            "width": "56px",
            "maxWidth": "64px",
        },
        {
            "if": {"column_id": "Injury"},
            "textAlign": "center",
            "minWidth": "44px",
            "width": "48px",
            "maxWidth": "56px",
            "padding": "0",
        },
        {
            "if": {"column_id": "Injury", "filter_query": '{Injury} contains "rs-injury-cell"'},
            "color": "#fbbf24" if dark else "#b45309",
        },
        {
            "if": {"filter_query": '{Injury} contains "rs-injury-cell"'},
            "backgroundColor": injury_bg,
        },
    ]
    if position_eligibility:
        eligible = "#3dff88" if dark else "#15803d"
        partial = "#fbbf24" if dark else "#a16207"
        ineligible = "#fb7185" if dark else "#be123c"
        rules.extend(
            [
                {
                    "if": {
                        "filter_query": '{PosEligible} = "yes"',
                        "column_id": "Position",
                    },
                    "color": eligible,
                    "fontWeight": "700",
                },
                {
                    "if": {
                        "filter_query": '{PosEligible} = "partial"',
                        "column_id": "Position",
                    },
                    "color": partial,
                    "fontWeight": "700",
                },
                {
                    "if": {
                        "filter_query": '{PosEligible} = "no"',
                        "column_id": "Position",
                    },
                    "color": ineligible,
                    "fontWeight": "600",
                },
            ]
        )
    rules.extend(rec_highlight_styles(theme))
    rules.extend(division_highlight_styles(theme))
    if extra:
        rules.extend(extra)
    return rules


def division_highlight_styles(theme: str | None = None) -> list[dict]:
    """Color Division: top (green), pro (yellow), semi-pro/amateur (red)."""
    from scoring.division_tiers import division_tier_colors

    colors = division_tier_colors(theme)
    rules = []
    for tier, (bg, fg) in colors.items():
        rules.append(
            {
                "if": {
                    "filter_query": f'{{DivisionTier}} = "{tier}"',
                    "column_id": "Division",
                },
                "backgroundColor": bg,
                "color": fg,
                "fontWeight": "700",
                "borderRadius": "6px",
            }
        )
    return rules


def player_data_table(
    *,
    prefix: str,
    columns: list[dict] | None = None,
    data: list[dict] | None = None,
    page_size: int = 50,
    page_action: str = "native",
    sort_as_null: Sequence[str] | None = None,
    css: list[dict] | None = None,
    style_cell_props: dict | None = None,
    style_cell_conditional_rules: list[dict] | None = None,
    style_header_props: dict | None = None,
    style_header_conditional_rules: list[dict] | None = None,
    style_data_conditional_rules: list[dict] | None = None,
    style_table_props: dict | None = None,
    tooltip_header: dict | None = None,
    shell_class_name: str = "rs-table-shell",
) -> html.Div:
    """Reusable DataTable shell. IDs: `{prefix}-table` and `{prefix}-table-shell`."""
    return html.Div(
        dash_table.DataTable(
            id=f"{prefix}-table",
            columns=columns or [],
            data=data or [],
            page_size=page_size,
            page_action=page_action,
            sort_action="custom",
            sort_mode="single",
            sort_by=[],
            sort_as_null=list(sort_as_null or ("-", "—", "")),
            row_selectable="multi",
            selected_rows=[],
            selected_row_ids=[],
            filter_action="none",
            fill_width=True,
            markdown_options={"html": True},
            tooltip_header=tooltip_header or {},
            tooltip_data=[],
            tooltip_delay=0,
            tooltip_duration=None,
            style_table=style_table_props if style_table_props is not None else style_table(),
            css=css if css is not None else table_css(),
            style_cell=style_cell_props if style_cell_props is not None else style_cell(),
            style_cell_conditional=(
                style_cell_conditional_rules
                if style_cell_conditional_rules is not None
                else style_cell_conditional()
            ),
            style_header=(
                style_header_props if style_header_props is not None else style_header()
            ),
            style_header_conditional=(
                style_header_conditional_rules
                if style_header_conditional_rules is not None
                else style_header_conditional()
            ),
            style_data_conditional=style_data_conditional_rules or [],
        ),
        id=f"{prefix}-table-shell",
        className=shell_class_name,
    )


def table_caption_row(
    *,
    prefix: str,
    clear_button_id: str,
    clear_label: str = "Clear marked rows",
    settings=None,
    select_all: bool = False,
) -> html.Div:
    """Caption + rows-per-page + clear-marks row used under both tables."""
    actions: list = [
        html.Div(
            [
                html.Label("Rows per page", className="rs-field-label"),
                dmc.Select(
                    id=f"{prefix}-page-size",
                    data=page_size_select_data(settings),
                    value=default_page_size_value(settings),
                    clearable=False,
                    searchable=False,
                ),
            ],
            className="rs-table-page-size",
        ),
    ]
    if select_all:
        actions.append(
            dmc.Button(
                "Select all",
                id=f"{prefix}-select-all",
                size="sm",
                variant="light",
                n_clicks=0,
                disabled=True,
            )
        )
    actions.append(
        dmc.Button(
            clear_label,
            id=clear_button_id,
            size="sm",
            variant="light",
            disabled=True,
            className="rs-squad-clear-btn",
        )
    )
    return html.Div(
        [
            html.Div(id=f"{prefix}-table-caption", className="text-muted"),
            html.Div(actions, className="rs-table-caption-actions"),
        ],
        className="rs-table-caption-row mt-2",
    )
