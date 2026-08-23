"""Role scores page: upload an FM attribute CSV, pick roles, filter, export."""
from __future__ import annotations

import re
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dash_table,
    dcc,
    html,
    no_update,
    register_page,
)
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import plotly.graph_objects as go

from components.pack_picker import pack_picker_bar, section_card_header
from components.player_filters import help_icon, player_filters
from components.scouting_shell import (
    as_list,
    clicked,
    hist_block,
    parsed_historical_players,
    pattern_matching_stubs,
    register_hist_toggle,
    register_library_select_callbacks,
    register_marks_callbacks,
    register_pos_foot_callbacks,
    register_upload_callbacks,
    upload_card,
)
from scoring.comparison import score_display
from scoring.role_scorer import (
    COMBO_IP_WEIGHT,
    COMBO_OOP_WEIGHT,
    GROUP_DEFS,
    POS_CARDS,
    SET_PIECE_PROFILES,
    apply_combos,
    combo_column,
    combo_column_labels,
    combo_meta,
    combo_score_labels,
    expand_view_role_columns,
    foot_match,
    group_abbr_tone,
    normalize_combos,
    parse_combo_id,
    parse_export,
    planned_squad_csv,
    planned_squad_export_rows,
    planned_squad_fieldnames,
    player_role_highlights,
    player_row_key,
    role_meta,
    role_options,
    score_band,
    score_players,
    scored_csv,
    to_int,
    set_piece_columns,
    set_piece_filter_columns,
    set_piece_formula,
    set_piece_header,
    set_piece_hint,
    set_piece_sort_column,
)
from components.player_modal import player_detail_body, player_modal
from components.player_table import (
    IDENTITY_LEFT_COLS,
    IDENTITY_TEXT_COLS,
    feet_cell,
    feet_sort_key,
    identity_data_styles,
    identity_header_name,
    identity_header_tooltips,
    injury_cell,
    injury_tooltip_entry,
    is_dark_theme,
    player_data_table,
    rec_sort_key,
    style_cell,
    style_cell_conditional,
    style_header,
    style_header_conditional,
    style_table,
    table_caption_row,
    table_css,
)
from components.attr_columns import attr_grid, attr_group_columns, attr_row
import services.formations as fm
import services.role_config as rc
import services.ui_settings as us

register_page(__name__, path="/", name="Role scores")

register_upload_callbacks(
    "rs",
    parse_fn=parse_export,
    pack_store=False,
    reveal_ids=[],
    pulse_ids=["rs-results-wrap"],
    bad_file_message="Upload the CSV from FM Player Export, not the HTML file.",
)
register_library_select_callbacks(
    "rs",
    parse_fn=parse_export,
    library_page="role_scores",
    pack_store=False,
    reveal_ids=[],
)
register_pos_foot_callbacks(
    "rs",
    pos_store="rs-pos-filter",
    foot_store="rs-foot-filter",
    pos_id_attr="pos",
)
register_marks_callbacks(
    "rs",
    marked_store="rs-squad-marked",
    clear_button="rs-squad-clear-btn",
)
register_hist_toggle("rs", use_open_store=True)


PERSIST_DEFAULTS = {
    "roles": [],
    "combos": [],
    "formation": None,
    "role_mode": "formations",
    "set_pieces": [],
    "hybrids_only": False,
    "pos_match": "yes",
    "focus_role": [],
    "search": "",
    "max_age": "99",
    "min_score": None,
    "min_score_mode": "all",
    "pos_filter": "all",
    "foot_filter": "",
    "phase": "all",
    "group": "all",
    "page_size": None,
    "set_piece_min_score": None,
}


def _persist_has_state(persist: dict | None, settings: dict | None = None) -> bool:
    p = {**PERSIST_DEFAULTS, **(persist or {})}
    if (
        _as_list(p.get("roles"))
        or normalize_combos(p.get("combos"))
        or p.get("formation")
        or _as_list(p.get("set_pieces"))
        or _as_list(p.get("focus_role"))
        or p.get("hybrids_only")
        or _normalize_pos_match(p.get("pos_match")) != "yes"
        or (p.get("role_mode") or "formations") != "formations"
    ):
        return True
    if (p.get("search") or "").strip():
        return True
    if str(p.get("max_age") or "99") != "99":
        return True
    settings = us.normalize(settings)
    ok_floor = settings["bands"]["ok"]
    min_score = p.get("min_score")
    if min_score is not None:
        try:
            if abs(float(min_score) - float(ok_floor)) > 1e-9:
                return True
        except (TypeError, ValueError):
            return True
    if (p.get("min_score_mode") or "all") != "all":
        return True
    if (p.get("pos_filter") or "all") != "all":
        return True
    if p.get("foot_filter"):
        return True
    if (p.get("phase") or "all") != "all":
        return True
    if (p.get("group") or "all") != "all":
        return True
    page_size = p.get("page_size")
    if page_size is not None:
        from components.player_table import default_page_size_value

        if str(page_size) != str(default_page_size_value(settings)):
            return True
    if p.get("set_piece_min_score") is not None:
        return True
    return False


def _persist_min_score(value, settings: dict | None = None):
    """Store None when min score matches the layout default (OK band)."""
    if value is None or value == "":
        return None
    settings = us.normalize(settings)
    try:
        if abs(float(value) - float(settings["bands"]["ok"])) <= 1e-9:
            return None
    except (TypeError, ValueError):
        pass
    return value


def _persist_page_size(value, settings: dict | None = None):
    """Store None when page size matches the settings default."""
    if value is None or value == "":
        return None
    from components.player_table import default_page_size_value

    settings = us.normalize(settings)
    if str(value) == str(default_page_size_value(settings)):
        return None
    return value


def _changed_or_skip(value, default):
    """Avoid Dash prop updates when restoring an unchanged layout default."""
    if value is None and default is None:
        return no_update
    if value == default:
        return no_update
    return value

POS_MATCH_OPTIONS = [
    {"value": "yes", "label": "Full match only (green)"},
    {"value": "partial", "label": "At least partial (yellow + green)"},
    {"value": "no", "label": "Any (includes red)"},
]
POS_MATCH_VALUES = {opt["value"] for opt in POS_MATCH_OPTIONS}


def _normalize_pos_match(value) -> str:
    """Map persisted filter value; migrate legacy eligible bool / Any."""
    if value in POS_MATCH_VALUES:
        return value
    if value is True or value == "eligible":
        return "yes"
    if value is False or value == "any":
        return "no"
    return "yes"


def _passes_pos_match(pos_elig: str, pos_match: str) -> bool:
    """Threshold filter: green ⊂ yellow ⊂ red/any."""
    if pos_match == "yes":
        return pos_elig == "yes"
    if pos_match == "partial":
        return pos_elig in ("yes", "partial")
    return True


def _band_legend(settings=None) -> html.Div:
    settings = us.normalize(settings)
    bands = settings["bands"]
    chips = []
    for band, label, text in (
        ("elite", "Elite", f"≥ {us.format_cut(bands['elite'])}"),
        ("good", "Good", f"≥ {us.format_cut(bands['good'])}"),
        ("ok", "OK", f"≥ {us.format_cut(bands['ok'])}"),
        ("poor", "Poor", f"< {us.format_cut(bands['ok'])}"),
    ):
        chips.append(
            html.Span(
                [
                    html.Span(label, className="rs-legend-name"),
                    html.Span(text, className="rs-legend-op"),
                ],
                className=f"rs-legend-chip {band}",
            )
        )
    return html.Div(chips, className="rs-depth-legend")


def _is_dark(theme) -> bool:
    return is_dark_theme(theme)


def _chart_layout(theme, *, height=240, showlegend=False) -> dict:
    dark = _is_dark(theme)
    font = "#e8eef6" if dark else "#212529"
    grid = "rgba(255,255,255,0.08)" if dark else "#dee2e6"
    return dict(
        height=height,
        margin=dict(l=40, r=20, t=20, b=40),
        font=dict(color=font, family="Inter, Segoe UI, sans-serif"),
        xaxis=dict(title="Score band", gridcolor=grid, zeroline=False, color=font),
        yaxis=dict(title="Player count", gridcolor=grid, zeroline=False, color=font),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        barmode="group",
        legend_title_text="Displayed role",
        showlegend=showlegend,
    )


def _blank_fig(theme):
    fig = go.Figure()
    fig.update_layout(**_chart_layout(theme, height=220))
    return fig


def _hist_figure(rows: list[dict], view_roles: list[str], bins: list, theme) -> go.Figure:
    fig = go.Figure()
    for role in view_roles:
        values = [float(row.get(role) or 0) for row in rows]
        counts = []
        for _label, lo, hi in bins:
            if hi == 99:
                counts.append(sum(1 for v in values if v >= lo))
            else:
                counts.append(sum(1 for v in values if lo <= v < hi))
        fig.add_bar(x=[b[0] for b in bins], y=counts, name=role)
    fig.update_layout(**_chart_layout(theme, showlegend=len(view_roles) > 1))
    return fig


BLANK_FIG = _blank_fig("dark")

HYBRID_HELP = (
    "Hybrid score = (IP weight × in possession + OOP weight × out of possession) "
    "÷ total. Both part scores stay in the table. "
    "A player is eligible if they can play either part."
)


def _hybrid_help(settings=None) -> str:
    weights = us.hybrid_weights(settings)
    total = weights["ip"] + weights["oop"]
    return (
        f"Hybrid score = ({weights['ip']:g}× in possession + {weights['oop']:g}× out of possession) "
        f"÷ {total:g}. Both part scores stay in the table. "
        "A player is eligible if they can play either part."
    )

ROLE_MODE_DATA = [
    {"label": "Single roles", "value": "single"},
    {"label": "Hybrid roles", "value": "hybrid"},
    {"label": "Formations", "value": "formations"},
]


def _help_icon(tip: str, help_id: str) -> list:
    return help_icon(tip, help_id)


def _field_label(
    text: str,
    *,
    primary: bool = False,
    tip: str | None = None,
    help_id: str | None = None,
) -> html.Div:
    label = html.Span(text, className="rs-field-label" + (" primary" if primary else ""))
    parts: list = [label]
    if tip:
        parts.extend(_help_icon(tip, help_id or f"rs-help-{text.lower().replace(' ', '-')}"))
    return html.Div(parts, className="rs-field-label-row")


def _find_parsed_player(parsed, name: str, club: str) -> dict | None:
    if not parsed or not parsed.get("players"):
        return None
    name = (name or "").strip()
    club = (club or "").strip()
    club_key = "" if club in ("", "-") else club
    for player in parsed["players"]:
        if (player.get("name") or "").strip() != name:
            continue
        player_club = (player.get("club") or "").strip()
        if player_club == club_key or (not player_club and not club_key):
            return player
    return None


def _player_is_gk(player: dict) -> bool:
    """True when the player is a keeper (pos card is GK, not lowercase role group)."""
    groups = {str(g) for g in (player.get("pos_groups") or [])}
    if groups & {"GK", "gk"}:
        return True
    for field in ("best_pos", "position"):
        text = str(player.get(field) or "").upper()
        if re.search(r"\bGK\b", text) or "GOALKEEPER" in text:
            return True
    return False


def _player_attr_row(code: str, label: str, attrs: dict, bands: dict):
    value = attrs.get(code)
    if value is None:
        return attr_row(label, "—", value_class="none", title=code)
    band = score_band(float(value), **bands)
    return attr_row(
        label,
        str(value),
        value_class=f"score rs-band-{band}",
        title=code,
    )


def _player_attributes(player: dict, bands: dict) -> html.Div:
    """Same attribute columns component as Role configs."""
    attrs = player.get("attrs") or {}
    columns = attr_group_columns(
        is_gk=_player_is_gk(player),
        make_row=lambda code, label: _player_attr_row(code, label, attrs, bands),
    )
    return html.Div(
        [
            html.Div("Attributes", className="rs-player-attrs-title"),
            attr_grid(columns),
        ],
        className="rs-player-attrs",
    )


def _role_highlight_row(phase: str, pick: dict | None, bands: dict) -> html.Div | None:
    if not pick:
        return None
    band = score_band(float(pick["score"]), **bands)
    return html.Div(
        [
            html.Span(phase, className=f"rs-role-fit-phase is-{phase.lower()}"),
            html.Span(
                pick.get("compact") or pick.get("name") or pick.get("code") or "—",
                className="rs-role-fit-name",
                title=pick.get("column") or "",
            ),
            html.Span(
                f"{float(pick['score']):.2f}",
                className=f"rs-role-fit-score rs-band-{band}",
            ),
        ],
        className="rs-role-fit-row",
    )


def _player_role_fit_section(player: dict, settings=None) -> html.Div | None:
    """Best IP/OOP roles for Best Pos, plus best IP/OOP in other available positions."""
    settings = us.normalize(settings)
    bands = settings["bands"]
    highlights = player_role_highlights(
        player,
        tier_weights=us.tier_weights(settings),
    )
    blocks = []
    in_best_rows = [
        row
        for row in (
            _role_highlight_row("IP", highlights["in_best"].get("IP"), bands),
            _role_highlight_row("OOP", highlights["in_best"].get("OOP"), bands),
        )
        if row is not None
    ]
    if in_best_rows:
        best_label = highlights.get("best_group_label") or "Best position"
        best_pos = (player.get("best_pos") or "").strip()
        subtitle = best_label
        if best_pos and best_pos != "-":
            subtitle = f"{best_label} · {best_pos}"
        blocks.append(
            html.Div(
                [
                    html.Div(subtitle, className="rs-role-fit-subtitle"),
                    html.Div(in_best_rows, className="rs-role-fit-rows"),
                ],
                className="rs-role-fit-block",
            )
        )
    other_rows = [
        row
        for row in (
            _role_highlight_row("IP", highlights["other"].get("IP"), bands),
            _role_highlight_row("OOP", highlights["other"].get("OOP"), bands),
        )
        if row is not None
    ]
    if other_rows:
        blocks.append(
            html.Div(
                [
                    html.Div(
                        "Other available positions",
                        className="rs-role-fit-subtitle",
                    ),
                    html.Div(other_rows, className="rs-role-fit-rows"),
                ],
                className="rs-role-fit-block",
            )
        )
    if not blocks:
        return None
    return html.Div(
        [
            html.Div("Role fit", className="rs-player-id-section-title"),
            *blocks,
        ],
        className="rs-player-id-section rs-role-fit-section",
    )


def _player_detail_card(
    player: dict,
    settings=None,
    *,
    position_eligible: str | None = None,
) -> html.Div:
    settings = us.normalize(settings)
    return player_detail_body(
        player,
        id_prefix="rs",
        position_eligible=position_eligible,
        modal_fields=us.modal_identity_fields_for("role_scores", settings),
        after_identity=_player_role_fit_section(player, settings),
        bottom=_player_attributes(player, settings["bands"]),
    )


def _combo_columns_by_label(combos) -> dict[str, dict]:
    return {
        combo_meta(item["ip"], item["oop"])["column"]: combo_meta(item["ip"], item["oop"])
        for item in normalize_combos(combos)
    }


def _role_match_level(row: dict, role_column: str, combo_by_col: dict | None = None) -> str:
    """How well Position matches one viewed column: full, partial, or none.

    Hybrids require both IP and OOP parts for full; one part is partial.
    """
    meta = (combo_by_col or {}).get(role_column)
    if meta:
        ip_ok = bool(row.get(f"{meta['ip_column']} eligible"))
        oop_ok = bool(row.get(f"{meta['oop_column']} eligible"))
        if ip_ok and oop_ok:
            return "full"
        if ip_ok or oop_ok:
            return "partial"
        return "none"
    if bool(row.get(f"{role_column} eligible")):
        return "full"
    return "none"


def _position_eligibility(
    row: dict,
    roles: list[str],
    combos=None,
    *,
    combo_by_col: dict | None = None,
) -> str | None:
    """Pos highlight: yes (all full), partial (some), no (none)."""
    if not roles:
        return None
    lookup = combo_by_col if combo_by_col is not None else _combo_columns_by_label(combos)
    levels = [_role_match_level(row, role, lookup) for role in roles]
    if all(level == "full" for level in levels):
        return "yes"
    if any(level != "none" for level in levels):
        return "partial"
    return "no"


def _sort_by_focus(focus_roles) -> list[dict]:
    focused = _focus_roles(focus_roles)
    if not focused:
        return []
    return [{"column_id": focused[-1], "direction": "desc"}]


def _find_scored_row(payload, name: str, club: str) -> dict | None:
    if not isinstance(payload, dict):
        return None
    name = (name or "").strip()
    club = (club or "").strip()
    club_key = "" if club in ("", "-") else club
    for row in payload.get("rows") or []:
        if str(row.get("Name") or "").strip() != name:
            continue
        row_club = str(row.get("Club") or "").strip()
        if row_club in ("", "-"):
            row_club = ""
        if row_club == club_key:
            return row
    return None


def _group_buttons(active: str = "all") -> list:
    buttons = [
        html.Button(
            "All",
            id={"type": "rs-group", "group": "all"},
            n_clicks=0,
            className="rs-chip" + (" active" if active == "all" else ""),
        )
    ]
    for group, label, _roles in GROUP_DEFS:
        buttons.append(
            html.Button(
                label,
                id={"type": "rs-group", "group": group},
                n_clicks=0,
                className="rs-chip" + (" active" if active == group else ""),
            )
        )
    return buttons


def _phase_buttons(active: str = "all") -> list:
    buttons = []
    for value, label in (
        ("all", "All"),
        ("IP", "In possession (IP)"),
        ("OOP", "Out of possession (OOP)"),
    ):
        buttons.append(
            html.Button(
                label,
                id={"type": "rs-phase", "phase": value},
                n_clicks=0,
                className="rs-chip" + (" active" if value == active else ""),
            )
        )
    return buttons


def _set_piece_check_label(profile: dict) -> str:
    if profile["id"] == "dfk":
        return "DFK (shot)"
    if profile["id"] == "ifk":
        return "IFK (cross)"
    return profile["label"]


def _colored_group_abbr(abbr: str, *, css: str = "rs-pill-groups"):
    if not abbr:
        return []
    parts = []
    for index, token in enumerate(abbr.split("/")):
        if index:
            parts.append(html.Span("/", className=f"{css}-sep"))
        tone = group_abbr_tone(token)
        class_name = f"{css} {tone}".strip() if tone else css
        parts.append(html.Span(token, className=class_name))
    return html.Span(parts, className="rs-group-abbr")


def _set_piece_panel(settings=None) -> html.Details:
    weights = us.tier_weights(settings)
    profiles = us.set_piece_profiles(settings)
    lines = []
    for profile in profiles:
        lines.append(
            html.Div(
                [
                    html.Span(profile["label"], className="rs-set-piece-name"),
                    html.Span(profile.get("detail") or "", className="rs-set-piece-detail"),
                    html.Span(
                        set_piece_formula(profile, weights),
                        className="rs-set-piece-formula",
                    ),
                ],
                className="rs-set-piece-line",
            )
        )
    return html.Details(
        [
            html.Summary(
                [
                    html.Div(
                        [
                            html.Span(
                                "Additional player metrics",
                                className="rs-metrics-summary-text",
                            ),
                            html.Span(
                                "Set-piece columns & optional filters",
                                className="rs-metrics-summary-hint",
                            ),
                        ],
                        className="rs-metrics-summary-copy",
                    ),
                    *_help_icon(
                        "Check a type to add its computed score column to the table. "
                        "Min score filters out anyone below that on every checked type.",
                        "rs-help-metrics",
                    ),
                ],
                className="rs-metrics-summary-row",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("Add columns", className="rs-metrics-section-label"),
                                    html.P(
                                        "Show computed set-piece scores in the shortlist.",
                                        className="rs-metrics-section-hint",
                                    ),
                                ],
                                className="rs-metrics-section-head",
                            ),
                            dmc.CheckboxGroup(
                                id="rs-set-pieces",
                                value=[],
                                children=[
                                    dmc.Checkbox(
                                        label=_set_piece_check_label(profile),
                                        value=profile["id"],
                                    )
                                    for profile in SET_PIECE_PROFILES
                                ],
                                className="rs-set-piece-checks",
                            ),
                        ],
                        className="rs-metrics-section rs-metrics-columns",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("Min score filter", className="rs-metrics-section-label"),
                                    html.P(
                                        "Leave blank for any. Applies to every checked type.",
                                        className="rs-metrics-section-hint",
                                    ),
                                ],
                                className="rs-metrics-section-head",
                            ),
                            html.Div(
                                dmc.NumberInput(
                                    id="rs-set-piece-min-score",
                                    label="Minimum score",
                                    placeholder="Any",
                                    min=0,
                                    max=20,
                                    step=0.1,
                                    decimalScale=1,
                                    value=None,
                                    className="rs-set-piece-min-dd",
                                ),
                                className="rs-metrics-filter-field",
                            ),
                        ],
                        className="rs-metrics-section rs-metrics-filter",
                    ),
                    html.Details(
                        [
                            html.Summary(
                                "Formulas & descriptions",
                                className="rs-set-piece-formulas-toggle",
                                title=set_piece_hint(us.tier_weights(settings)),
                            ),
                            html.Div(lines, className="rs-set-piece-formulas"),
                        ],
                        className="rs-set-piece-formulas-details",
                    ),
                ],
                className="rs-metrics-body",
            ),
        ],
        className="rs-metrics-details",
    )


def _role_pills(role_ids: list[str]) -> list:
    pills = []
    for role_id in role_ids:
        meta = role_meta(role_id)
        pills.append(
            html.Button(
                [
                    _colored_group_abbr(meta["group_abbr"]),
                    html.Span(meta["name"], className="rs-pill-code"),
                    html.Span(
                        meta["phase"],
                        className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                    ),
                    html.Span("×", className="rs-pill-x"),
                ],
                id={"type": "rs-pill", "role": role_id},
                n_clicks=0,
                title=meta["compact"],
                className="rs-role-pill",
            )
        )
    return pills


def _hybrid_roles_panel(settings=None) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    _field_label(
                        "Hybrid roles",
                        primary=True,
                        tip=_hybrid_help(settings),
                        help_id="rs-help-hybrid",
                    ),
                    html.Div(
                        [
                            dmc.Select(
                                id="rs-combo-ip",
                                label="In possession (IP) role",
                                data=role_options(phase="IP"),
                                placeholder="Choose an in possession role",
                                clearable=True,
                                searchable=True,
                                className="rs-combo-field",
                            ),
                            dmc.Select(
                                id="rs-combo-oop",
                                label="Out of possession (OOP) role",
                                data=role_options(phase="OOP"),
                                placeholder="Choose an out of possession role",
                                clearable=True,
                                searchable=True,
                                className="rs-combo-field",
                            ),
                            dmc.Button(
                                "Add combined",
                                id="rs-combo-add",
                                n_clicks=0,
                                variant="light",
                            ),
                            dmc.Button(
                                "Clear",
                                id={"type": "rs-clear-roles", "loc": "hybrid"},
                                n_clicks=0,
                                variant="subtle",
                            ),
                        ],
                        className="rs-combo-row",
                    ),
                    html.Div(
                        id="rs-combo-pills",
                        className="rs-selected-roles rs-pill-row mt-2",
                    ),
                ],
                className="rs-hybrid-body",
            ),
        ],
        id="rs-hybrid-panel",
        className="rs-role-mode-panel",
        hidden=True,
    )


def _combo_pills(combos: list[dict] | None, settings=None) -> list:
    weights = us.hybrid_weights(settings)
    pills = []
    for item in normalize_combos(combos):
        meta = combo_meta(item["ip"], item["oop"])
        pills.append(
            html.Button(
                [
                    _colored_group_abbr(meta["group_abbr"]),
                    html.Span(meta["short_label"], className="rs-pill-code"),
                    html.Span(meta["phase"], className="rs-phase-tag combo"),
                    html.Span("×", className="rs-pill-x"),
                ],
                id={"type": "rs-combo-pill", "combo": meta["id"]},
                n_clicks=0,
                title=(
                    f"{meta['name']} · {weights['ip']:g}× IP + {weights['oop']:g}× OOP"
                ),
                className="rs-role-pill combo",
            )
        )
    return pills


def _depth_id_column(role_key: str) -> str | None:
    parsed = parse_combo_id(role_key)
    if parsed:
        return combo_column(*parsed)
    if role_key and role_key != "_":
        return role_meta(role_key)["column"]
    return None


def _first_combo_column(combos: list[dict] | None) -> str | None:
    items = normalize_combos(combos)
    if not items:
        return None
    return combo_column(items[0]["ip"], items[0]["oop"])


def _focus_roles(value) -> list[str]:
    """Normalize squad-depth focus store to a list of score column labels."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _resolved_view_roles(payload: dict | None, focus_roles) -> list[str]:
    """Table/export columns: focused depth roles, or every role scored in section 2."""
    if not payload:
        return []
    labels = list(payload.get("roles") or [])
    if not labels:
        return []
    focused = [role for role in _focus_roles(focus_roles) if role in labels]
    return focused or labels


def _no_match_placeholder(
    *,
    pos_match: str,
    pos_filter: str,
    foot_filter: str,
    min_score: float,
    set_piece_min: float,
    query: str,
    max_age: int,
) -> html.Div:
    tips: list[str] = []
    if pos_match == "yes":
        tips.append(
            "Set Position match to “At least partial” or “Any” — Full match only "
            "requires every focused role, and both parts of a hybrid."
        )
    elif pos_match == "partial":
        tips.append(
            "Set Position match to Any — At least partial still hides red (no match)."
        )
    if pos_filter != "all":
        tips.append("Select All in the position bar above.")
    if foot_filter:
        tips.append("Clear the Footedness filter.")
    if min_score > 0:
        tips.append("Lower or clear Min score.")
    if set_piece_min > 0:
        tips.append("Lower or clear the set-piece min score.")
    if max_age < 99:
        tips.append("Raise Max age to Any.")
    if query:
        tips.append("Clear the search box.")
    if not tips:
        tips.append("Loosen any active shortlist filters and try again.")
    return html.Div(
        [
            html.Div("No players match these filters", className="rs-empty-title"),
            html.P(
                "Roles are selected, but nobody meets every criterion. "
                "Try loosening the filters.",
                className="rs-empty-copy",
            ),
            html.Ul(
                [html.Li(tip) for tip in tips],
                className="rs-empty-tips",
            ),
        ],
        className="rs-table-empty-inner",
    )


def _hybrid_only_roles(view_roles: list[str], combos, hybrids_only: bool) -> list[str]:
    if not hybrids_only:
        return view_roles
    combo_cols = combo_column_labels(combos)
    if not combo_cols:
        return view_roles
    allowed = set(combo_cols)
    kept = [role for role in view_roles if role in allowed]
    return kept or combo_cols


def _table_role_columns(view_roles: list[str], combos, hybrids_only: bool) -> list[str]:
    return expand_view_role_columns(
        view_roles,
        combos,
        include_parts=not hybrids_only,
    )


def layout():
    settings = us.load()
    return dbc.Container(
    [
        dcc.Store(id="rs-rows"),
        dcc.Store(id="rs-phase", data="all"),
        dcc.Store(id="rs-group", data="all"),
        dcc.Store(id="rs-pos-filter", data="all"),
        dcc.Store(id="rs-foot-filter", data=""),
        dcc.Store(id="rs-combos", data=[]),
        dcc.Store(id="rs-squad-marked", data=[]),
        dcc.Store(id="rs-hist-open", data=False),
        dcc.Store(id="rs-focus-role", data=[]),
        dcc.Store(id="rs-set-pieces-prev", data=[]),
        dcc.Store(id="rs-table-cols-sig", data=""),
        dcc.Store(id="rs-hydrated", data=False),
        dcc.Store(id="rs-persist-boot"),
        dcc.Store(id="rs-role-mode-prev", data=None),
        dcc.Interval(id="rs-hydrate-tick", interval=50, max_intervals=1),
        player_modal(prefix="rs"),
        pattern_matching_stubs(
            "rs",
            [
                {"type": "pos", "pos": "_"},
                {"type": "foot", "foot": "_"},
                {"type": "depth", "role": "_"},
                {"type": "pill", "role": "_"},
                {"type": "group", "group": "_"},
                {"type": "combo-pill", "combo": "_"},
                {"type": "clear-roles", "loc": "_"},
            ],
        ),
        dcc.Download(id="rs-download-csv"),
        dcc.Download(id="rs-download-squad"),
        html.H1("FM26 role scores", className="mt-2 mb-3"),
        upload_card("rs", "1. Upload export", library_page="role_scores"),
        html.Div(
            [
        dbc.Card(
            [
                section_card_header(
                    "2. Scored roles",
                    next_badge=True,
                    trailing=pack_picker_bar(
                        select_id="rs-config",
                        label="Scoring weights",
                        options=rc.pack_options(),
                        value=rc.active_pack_id(),
                        edit_href="/role-config",
                        edit_title="Open the Role configs page to edit and save weights.",
                        select_title=(
                            "Scores use this file’s key / preferred / useful weights. "
                            "Edit and Save a config on the Role configs page."
                        ),
                        select_wrap_class="pack-picker-dd rs-config-dd",
                        interval_id="rs-config-tick",
                    ),
                ),
                dbc.CardBody(
                    [
                        html.Div(
                            [
                        html.Div(
                            dmc.SegmentedControl(
                                id="rs-role-mode",
                                value="formations",
                                data=ROLE_MODE_DATA,
                                fullWidth=True,
                                size="md",
                                radius="md",
                                className="rs-role-mode-control",
                            ),
                            className="rs-role-mode-wrap",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Span("Phase", className="rs-chip-label"),
                                                html.Div(
                                                    _phase_buttons("all"),
                                                    id="rs-phase-row",
                                                    className="rs-chip-row",
                                                ),
                                            ],
                                            className="rs-filter-row",
                                            id="rs-phase-filter-wrap",
                                        ),
                                        html.Div(
                                            [
                                                html.Span("Group", className="rs-chip-label"),
                                                html.Div(
                                                    _group_buttons("all"),
                                                    id="rs-group-row",
                                                    className="rs-chip-row wrap",
                                                ),
                                            ],
                                            className="rs-filter-row",
                                        ),
                                    ],
                                    className="rs-role-toolbar",
                                ),
                            ],
                            id="rs-filter-toolbar",
                            className="rs-filter-toolbar",
                            hidden=True,
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        _field_label(
                                            "Scored roles",
                                            primary=True,
                                            tip="Every player is scored against the roles you pick here.",
                                            help_id="rs-help-scored-roles",
                                        ),
                                        html.Div(
                                            [
                                                dmc.MultiSelect(
                                                    id="rs-roles",
                                                    data=role_options(),
                                                    value=[],
                                                    placeholder="Choose scored roles",
                                                    searchable=True,
                                                    clearable=True,
                                                    maxDropdownHeight=280,
                                                    w="100%",
                                                    className="rs-primary-control",
                                                ),
                                                html.Div(
                                                    [
                                                        dmc.Button(
                                                            "Add all",
                                                            id="rs-add-all-roles",
                                                            n_clicks=0,
                                                            variant="light",
                                                            size="sm",
                                                            className="rs-add-all-roles",
                                                            buttonProps={
                                                                "title": (
                                                                    "Select every role matching the Phase and "
                                                                    "Group filters above."
                                                                ),
                                                            },
                                                        ),
                                                        dmc.Button(
                                                            "Clear",
                                                            id={"type": "rs-clear-roles", "loc": "single"},
                                                            n_clicks=0,
                                                            variant="subtle",
                                                            size="sm",
                                                            className="rs-clear-roles",
                                                        ),
                                                    ],
                                                    className="rs-roles-select-actions",
                                                ),
                                            ],
                                            className="rs-roles-select-row",
                                        ),
                                        html.Div(
                                            id="rs-role-pills",
                                            className="rs-selected-roles rs-pill-row",
                                        ),
                                    ],
                                    id="rs-single-panel",
                                    className="rs-role-mode-panel",
                                    hidden=True,
                                ),
                                _hybrid_roles_panel(settings),
                                html.Div(
                                    [
                                        _field_label(
                                            "Formation",
                                            primary=True,
                                            tip=(
                                                "Loads the hybrid in/out-of-possession pairs from a "
                                                "saved lineup. Squad depth shows those hybrid roles only."
                                            ),
                                            help_id="rs-help-formation",
                                        ),
                                        html.Div(
                                            [
                                                dmc.Select(
                                                    id="rs-formation",
                                                    data=fm.pack_options(),
                                                    placeholder="Load a saved formation",
                                                    clearable=True,
                                                    searchable=True,
                                                    size="md",
                                                    className="rs-formation-dd",
                                                ),
                                                dcc.Link(
                                                    "Edit",
                                                    href="/formations",
                                                    className="rs-weights-edit",
                                                    title="Open the Formations page to create or edit lineups.",
                                                ),
                                            ],
                                            className="rs-formation-row",
                                        ),
                                        dcc.Interval(id="rs-formation-tick", interval=2500),
                                    ],
                                    id="rs-formation-panel",
                                    className="rs-role-mode-panel rs-formation-bar",
                                ),
                            ],
                            className="rs-role-mode-panels",
                        ),
                            ],
                            id="rs-roles-body",
                            className="rs-roles-body rs-roles-body-formations",
                        ),
                    ]
                ),
            ],
            id="rs-roles-card",
            className="mb-3 rs-section-card",
        ),
            ],
            id="rs-setup-wrap",
            hidden=True,
        ),
        html.Div(
            [
                html.Div(
                    "Choose at least one scored role",
                    className="rs-gate-title",
                ),
            ],
            id="rs-need-roles",
            className="rs-gate",
            hidden=True,
        ),
        html.Div(
            [
        dbc.Card(
            [
                dbc.CardHeader("3. Shortlist"),
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Span(
                                                    "Squad depth",
                                                    className="rs-depth-heading-label",
                                                ),
                                                html.Span(
                                                    "Click cards to focus the table on one or more roles. "
                                                    "Click again to remove a role; clear all to show every role. "
                                                    "Click a player name in the shortlist for full details.",
                                                    className="rs-depth-heading-hint",
                                                ),
                                            ],
                                            className="rs-depth-heading-copy",
                                        ),
                                        html.Div(_band_legend(settings), id="rs-band-legend"),
                                    ],
                                    className="rs-depth-heading",
                                ),
                                html.Div(id="rs-summary", className="rs-depth-grid"),
                            ],
                            id="rs-depth-wrap",
                            className="rs-depth-panel",
                            hidden=True,
                        ),
                        html.Div(
                            [
                                html.Div(id="rs-pos-bar"),
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Label("Search", className="rs-field-label"),
                                                dmc.TextInput(
                                                    id="rs-search",
                                                    placeholder="Name, club, position",
                                                ),
                                            ],
                                            className="rs-filter-search",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("Max age", className="rs-field-label"),
                                                dmc.Select(
                                                    id="rs-age",
                                                    data=us.age_options(settings),
                                                    value="99",
                                                    clearable=False,
                                                    searchable=False,
                                                ),
                                            ],
                                            className="rs-filter-age",
                                        ),
                                        html.Div(
                                            [
                                                _field_label(
                                                    "Min score",
                                                    tip=(
                                                        "Uses scored roles from section 2, or the "
                                                        "roles focused in squad depth. Leave blank for any."
                                                    ),
                                                    help_id="rs-help-min-score",
                                                ),
                                                html.Div(
                                                    [
                                                        dmc.NumberInput(
                                                            id="rs-min-score",
                                                            placeholder="Any",
                                                            min=0,
                                                            max=20,
                                                            step=0.1,
                                                            decimalScale=1,
                                                            value=settings["bands"]["ok"],
                                                        ),
                                                        dmc.Select(
                                                            id="rs-min-score-mode",
                                                            data=[
                                                                {
                                                                    "label": "Every selected role",
                                                                    "value": "all",
                                                                },
                                                                {
                                                                    "label": (
                                                                        "At least one selected role"
                                                                    ),
                                                                    "value": "any",
                                                                },
                                                            ],
                                                            value="all",
                                                            clearable=False,
                                                            searchable=False,
                                                            className="rs-min-score-mode",
                                                        ),
                                                    ],
                                                    className="rs-min-score-fields",
                                                ),
                                            ],
                                            className="rs-filter-score",
                                        ),
                                        html.Div(
                                            [
                                                _field_label(
                                                    "Position match",
                                                    tip=(
                                                        "Same green / yellow / red rules as the "
                                                        "Position column. Full = green only; "
                                                        "At least partial = yellow + green; "
                                                        "Any = includes red. Hybrids need both "
                                                        "parts for green."
                                                    ),
                                                    help_id="rs-help-pos-match",
                                                ),
                                                dmc.Select(
                                                    id="rs-pos-match",
                                                    data=POS_MATCH_OPTIONS,
                                                    value="yes",
                                                    clearable=False,
                                                    searchable=False,
                                                ),
                                            ],
                                            className="rs-filter-pos-match",
                                        ),
                                        dmc.Switch(
                                            id="rs-hybrids-only",
                                            label="Show only hybrid roles",
                                            checked=False,
                                            className="rs-filter-hybrids",
                                        ),
                                    ],
                                    className="rs-shortlist-filters-row",
                                ),
                            ],
                            className="rs-shortlist-filters mb-2",
                        ),
                        html.Div(_set_piece_panel(settings), className="rs-special-scores"),
                        html.Div(
                            [
                                html.Div(
                                    id="rs-table-empty",
                                    className="rs-table-empty",
                                    hidden=True,
                                ),
                                player_data_table(
                                    prefix="rs",
                                    page_size=us.page_size(settings),
                                    style_cell_props=style_cell(text_align="right"),
                                    style_cell_conditional_rules=style_cell_conditional(),
                                    style_header_props=style_header(),
                                    style_header_conditional_rules=style_header_conditional(),
                                    style_data_conditional_rules=[
                                        {
                                            "if": {"filter_query": '{Injury} contains "rs-injury-cell"'},
                                            "backgroundColor": "#fff3cd",
                                        }
                                    ],
                                    css=table_css(center_non_identity=True),
                                ),
                            ],
                            className="rs-table-area",
                        ),
                        html.Div(id="rs-table-layout-nudge", hidden=True),
                        table_caption_row(
                            prefix="rs",
                            clear_button_id="rs-squad-clear-btn",
                            settings=settings,
                        ),
                        hist_block(
                            "rs",
                            blank_figure=BLANK_FIG,
                            toggle_title=(
                                "Score band on the horizontal axis; player count on "
                                "the vertical axis. One series per displayed role."
                            ),
                        ),
                    ]
                ),
            ],
            className="mb-3 rs-section-card",
        ),
        dbc.Card(
            [
                dbc.CardHeader("4. Export"),
                dbc.CardBody(
                    [
                        dmc.Button(
                            "Download scored CSV",
                            id="rs-csv-btn",
                            className="me-2",
                        ),
                        html.Hr(className="my-3"),
                        html.Div(
                            [
                                html.Span("Planned squad", className="rs-export-subhead"),
                                *_help_icon(
                                    "Mark players in the shortlist table, then download a CSV "
                                    "with identity fields, displayed scores, and any set-piece "
                                    "columns you checked.",
                                    "rs-help-planned-squad",
                                ),
                            ],
                            className="rs-export-subhead-row",
                        ),
                        html.Div(id="rs-squad-preview", className="rs-squad-preview"),
                        dmc.Button(
                            "Download planned squad CSV",
                            id="rs-squad-btn",
                            color="green",
                            className="mt-2",
                            disabled=True,
                        ),
                    ]
                ),
            ],
            className="mb-4 rs-section-card",
        ),
            ],
            id="rs-results-wrap",
            hidden=True,
        ),
    ],
    className="rs-page",
    fluid=True,
)


def _labels(role_ids: list[str]) -> list[str]:
    return [role_meta(role_id)["column"] for role_id in role_ids]


def _as_list(value) -> list:
    return as_list(value)


def _cell_number(value) -> float:
    if value in (None, "", "-"):
        return 0.0
    text = str(value)
    if "<" in text:
        text = re.sub(r"<[^>]+>", "", text).strip()
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace("%", ""))
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return 0.0


TABLE_TEXT_COLS = IDENTITY_TEXT_COLS
TABLE_MARKDOWN_COLS = {"Feet", "Injury"}


def _column_sort_key(column_id: str, value, row: dict | None = None):
    if column_id == "Feet" and row is not None:
        return feet_sort_key(row)
    if column_id == "Rec":
        return rec_sort_key(value)
    blank = value in (None, "", "-")
    if column_id not in TABLE_TEXT_COLS:
        return (1, float("inf")) if blank else (0, _cell_number(value))
    return (1, "\uffff") if blank else (0, str(value).casefold())


def _sort_table_rows(rows: list[dict], sort_by, view_roles: list[str], min_score_mode: str) -> None:
    if sort_by:
        item = sort_by[0]
        column = item.get("column_id")
        reverse = item.get("direction") == "desc"
        rows.sort(
            key=lambda row: _column_sort_key(column, row.get(column), row),
            reverse=reverse,
        )
        return
    rows.sort(
        key=lambda row: (
            max(float(row.get(role) or 0) for role in view_roles)
            if min_score_mode == "any"
            else min(float(row.get(role) or 0) for role in view_roles)
        ),
        reverse=True,
    )


def _is_hybrid_column(col_id: str) -> bool:
    """Hybrid score columns are `IPLabel+OOPLabel` (not identity text cols)."""
    return (
        isinstance(col_id, str)
        and "+" in col_id
        and col_id not in TABLE_TEXT_COLS
    )


_PHASE_DISPLAY_SUFFIXES = ("-IP", "-OOP", "-GK")
_HEADER_LEFT_COLS = IDENTITY_LEFT_COLS
_COLUMN_TONE_BY_ID: dict[str, str] | None = None


def _strip_phase_suffix(label: str) -> str:
    """Drop -IP / -OOP / -GK from a display label (data id stays unchanged)."""
    for suffix in _PHASE_DISPLAY_SUFFIXES:
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _column_display_name(col_id: str) -> str:
    """Short headers: CF not CF-IP; hybrids wrap as CF+\\nCM; set pieces as COR/AER/…"""
    if col_id in TABLE_TEXT_COLS:
        return identity_header_name(col_id)
    piece = set_piece_header(col_id)
    if piece != col_id:
        return piece
    if _is_hybrid_column(col_id):
        ip, _, oop = col_id.partition("+")
        if not ip or not oop:
            return col_id
        return f"{_strip_phase_suffix(ip)}+\n{_strip_phase_suffix(oop)}"
    return _strip_phase_suffix(col_id)


_ROLE_COLUMN_FULL_NAMES: dict[str, str] | None = None


def _role_column_full_names() -> dict[str, str]:
    """Map score column id → full role name with phase."""
    global _ROLE_COLUMN_FULL_NAMES
    if _ROLE_COLUMN_FULL_NAMES is None:
        import config.role_weights.fm26_role_weight_config as pc

        names: dict[str, str] = {}
        for role_id in pc.all_positions:
            meta = role_meta(role_id)
            phase = meta.get("phase") or ""
            names[meta["column"]] = (
                f"{meta['name']} ({phase})" if phase else meta["name"]
            )
        _ROLE_COLUMN_FULL_NAMES = names
    return _ROLE_COLUMN_FULL_NAMES


def _column_full_name(col_id: str, *, combos=None) -> str | None:
    """Human-readable name for abbreviated score / set-piece headers."""
    if col_id in TABLE_TEXT_COLS:
        return None
    for profile in SET_PIECE_PROFILES:
        if profile.get("score") == col_id:
            label = profile.get("label") or col_id
            detail = profile.get("detail")
            return f"{label} · {detail}" if detail else label
    if _is_hybrid_column(col_id):
        for item in normalize_combos(combos):
            meta = combo_meta(item["ip"], item["oop"])
            if meta["column"] == col_id:
                return meta["name"]
        ip, _, oop = col_id.partition("+")
        names = _role_column_full_names()
        left = names.get(ip) or _strip_phase_suffix(ip)
        right = names.get(oop) or _strip_phase_suffix(oop)
        return f"{left} + {right}"
    return _role_column_full_names().get(col_id)


def _header_tooltips(col_ids: list[str], *, combos=None) -> dict[str, str]:
    """tooltip_header map for abbreviated identity + score columns."""
    tips = identity_header_tooltips(*col_ids)
    for col in col_ids:
        full = _column_full_name(col, combos=combos)
        if full:
            tips[col] = full
    return tips


def _column_tone_map() -> dict[str, str]:
    """Map score column id → phase tone (ip / oop / gk)."""
    global _COLUMN_TONE_BY_ID
    if _COLUMN_TONE_BY_ID is None:
        import config.role_weights.fm26_role_weight_config as pc

        _COLUMN_TONE_BY_ID = {
            role_meta(role_id)["column"]: role_meta(role_id)["tone"]
            for role_id in pc.all_positions
        }
    return _COLUMN_TONE_BY_ID


def _score_column_tone(col_id: str) -> str:
    if col_id in TABLE_TEXT_COLS:
        return ""
    if _is_hybrid_column(col_id):
        return "combo"
    return _column_tone_map().get(col_id, "")


def _header_phase_colors(theme: str | None = None) -> dict[str, str]:
    dark = _is_dark(theme)
    return {
        "ip": "#3dff88" if dark else "#15803d",
        "oop": "#f87171" if dark else "#b91c1c",
        "gk": "#fbbf24" if dark else "#b45309",
        "combo": "#c4b5fd" if dark else "#6d28d9",
    }


def _table_columns(col_ids: list[str]) -> list[dict]:
    columns = []
    for col in col_ids:
        spec = {"name": _column_display_name(col), "id": col}
        if col in TABLE_MARKDOWN_COLS or col not in TABLE_TEXT_COLS:
            # Score / set-piece cells may include HTML deltas; Feet uses colored HTML.
            spec["presentation"] = "markdown"
        columns.append(spec)
    return columns


def _score_column_styles(role_labels: list[str]) -> list[dict]:
    """Center score cells; give short role/score cols a stable min width."""
    rules = []
    for label in role_labels:
        if _is_hybrid_column(label):
            rules.append(
                {
                    "if": {"column_id": label},
                    "textAlign": "center",
                    "verticalAlign": "middle",
                    "minWidth": "64px",
                    "width": "72px",
                    "maxWidth": "80px",
                    "paddingLeft": "4px",
                    "paddingRight": "4px",
                    "paddingTop": "6px",
                    "paddingBottom": "6px",
                    "whiteSpace": "normal",
                    "lineHeight": "1.2",
                }
            )
        else:
            rules.append(
                {
                    "if": {"column_id": label},
                    "textAlign": "center",
                    "verticalAlign": "middle",
                    "minWidth": "64px",
                    "width": "72px",
                    "maxWidth": "80px",
                    "paddingLeft": "4px",
                    "paddingRight": "4px",
                    "paddingTop": "6px",
                    "paddingBottom": "6px",
                    "whiteSpace": "normal",
                    "lineHeight": "1.2",
                }
            )
    return rules


def _score_header_styles(role_labels: list[str], theme: str | None = None) -> list[dict]:
    """Left-align identity headers; color IP green / OOP red / hybrid purple."""
    rules = [
        {"if": {"column_id": col}, "textAlign": "left"}
        for col in _HEADER_LEFT_COLS
    ]
    colors = _header_phase_colors(theme)
    for label in role_labels:
        tone = _score_column_tone(label)
        color = colors.get(tone)
        if not color:
            continue
        rules.append(
            {
                "if": {"column_id": label},
                "color": color,
                "textAlign": "center",
                "fontWeight": "700",
            }
        )
    return rules


def _score_header_css(role_labels: list[str], theme: str | None = None) -> list[dict]:
    """Per-column header colors with !important (covers codes without -IP/-OOP)."""
    colors = _header_phase_colors(theme)
    rules = []
    for label in role_labels:
        tone = _score_column_tone(label)
        color = colors.get(tone)
        if not color:
            continue
        # Escape quotes in column ids for CSS attribute selectors.
        safe = str(label).replace("\\", "\\\\").replace('"', '\\"')
        rules.append(
            {
                "selector": (
                    f'th.dash-header[data-dash-column="{safe}"], '
                    f'th.dash-header[data-dash-column="{safe}"] .column-header-name'
                ),
                "rule": f"color: {color} !important; font-weight: 700;",
            }
        )
    return rules


def _table_css(role_labels: list[str] | None = None, theme: str | None = None) -> list[dict]:
    """Shared table CSS plus phase-colored score headers."""
    return table_css(
        center_non_identity=True,
        extra=_score_header_css(role_labels or [], theme),
    )


def _column_signature(columns: list[dict]) -> str:
    return "|".join(str(col.get("id") or "") for col in columns)


def _table_style_table(_row_count: int = 0, _page_size: int = 50) -> dict:
    return style_table()


def _table_page_state(columns: list[dict], prev_sig: str | None) -> tuple[int | object, str]:
    sig = _column_signature(columns)
    if sig != (prev_sig or ""):
        return 0, sig
    return no_update, sig


def _clicked(n_clicks) -> bool:
    return clicked(n_clicks)


MIN_SCORE_MODES = {
    "all": "every selected role",
    "any": "at least one selected role",
}


def _passes_min_score(row: dict, roles: list[str], min_score: float, mode: str) -> bool:
    if min_score <= 0 or not roles:
        return True
    scores = [float(row.get(role) or 0) for role in roles]
    if mode == "any":
        return any(score >= min_score for score in scores)
    return all(score >= min_score for score in scores)


def _table_base_styles(theme: str | None = None) -> list[dict]:
    return identity_data_styles(theme, position_eligibility=True)


def _score_styles(role_labels: list[str], settings=None, theme: str | None = None) -> list[dict]:
    rules = _table_base_styles(theme)
    rules.extend(_score_column_styles(role_labels))
    return rules


_STYLE_CACHE: dict = {}


def _cached_table_chrome(
    score_cols: list[str], settings, theme: str | None
) -> tuple[list, list, list]:
    """Reuse style/css objects when score columns + theme + bands are unchanged."""
    settings = us.normalize(settings)
    bands = settings["bands"]
    key = (
        tuple(score_cols),
        theme or "dark",
        bands.get("elite"),
        bands.get("good"),
        bands.get("ok"),
    )
    cached = _STYLE_CACHE.get(key)
    if cached is not None:
        return cached
    pack = (
        _score_styles(score_cols, settings, theme),
        _score_header_styles(score_cols, theme),
        _table_css(score_cols, theme),
    )
    _STYLE_CACHE.clear()
    _STYLE_CACHE[key] = pack
    return pack


def _pos_bar(rows: list[dict], active: str, foot: str, foot_thresholds=None) -> html.Div:
    counts = {"all": len(rows)}
    for key, _name, _code, _css in POS_CARDS[1:]:
        counts[key] = sum(1 for row in rows if key in (row.get("PosGroups") or []))
    groups = [
        {
            "key": key,
            "label": name,
            "code": code,
            "css": css,
            "count": counts.get(key, 0),
        }
        for key, name, code, css in POS_CARDS
    ]
    return player_filters(
        prefix="rs",
        pos_groups=groups,
        active_pos=active,
        active_foot=foot or "",
        foot_thresholds=foot_thresholds,
        pos_id_attr="pos",
        foot_inline=True,
    )


def _depth_card_stats(meta: dict, rows: list[dict], bands: dict) -> dict | None:
    column = meta["column"]
    eligible = [row for row in rows if row.get(f"{column} eligible")]
    if not eligible:
        return None
    scores = [float(row.get(column) or 0) for row in eligible]
    avg = sum(scores) / len(scores)
    counts = {"elite": 0, "good": 0, "ok": 0, "poor": 0}
    for score in scores:
        counts[score_band(score, **bands)] += 1
    total = len(scores) or 1
    top = sorted(eligible, key=lambda row: float(row.get(column) or 0), reverse=True)[:3]
    names = " · ".join(player.get("Name", "") for player in top)
    return {
        "meta": meta,
        "avg": avg,
        "counts": counts,
        "total": total,
        "names": names,
    }


def _depth_card_from_stats(stats: dict, focus_roles, bands: dict) -> html.Button:
    meta = stats["meta"]
    column = meta["column"]
    avg = stats["avg"]
    counts = stats["counts"]
    total = stats["total"]
    active = " active" if column in _focus_roles(focus_roles) else ""
    label = meta.get("short_label") or meta["name"]
    children = [
        html.Span("Focused", className="rs-depth-focus-badge"),
        html.Div(
            [
                html.Div(
                    [
                        _colored_group_abbr(meta["group_abbr"], css="rs-depth-code"),
                        html.Span(
                            meta["phase"],
                            className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                        ),
                    ],
                    className="rs-depth-meta",
                ),
                html.Span(label, className="rs-depth-name"),
            ],
            className="rs-depth-title",
        ),
        html.Div(
            [
                html.Span("Avg", className="rs-depth-avg-label"),
                html.Span(
                    f"{avg:.1f}",
                    className=f"rs-depth-avg rs-band-{score_band(avg, **bands)}",
                ),
            ],
            className="rs-depth-avg-row",
        ),
        html.Div(
            [
                html.Div(
                    className=f"rs-depth-seg {band}",
                    style={"width": f"{counts[band] / total * 100:.1f}%"},
                )
                for band in ("elite", "good", "ok", "poor")
                if counts[band]
            ],
            className="rs-depth-bar",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(str(counts[band]), className=f"rs-tier-val {band}"),
                        html.Div(tier_label, className="rs-tier-lbl"),
                    ],
                    className="rs-tier",
                )
                for band, tier_label in (
                    ("elite", "Elite"),
                    ("good", "Good"),
                    ("ok", "OK"),
                    ("poor", "Poor"),
                )
            ],
            className="rs-depth-tiers",
        ),
        html.Div(stats["names"], className="rs-depth-players"),
    ]
    return html.Button(
        children,
        id={"type": "rs-depth", "role": meta["id"]},
        n_clicks=0,
        className="rs-depth-card" + active,
        title=meta.get("compact") or meta["name"],
        **{"data-rs-role": column},
    )


_DEPTH_STATS_CACHE: dict = {"sig": None, "stats": []}


def _depth_panel(
    rows: list[dict],
    role_ids: list[str],
    focus_roles,
    bands: dict | None = None,
    combos: list[dict] | None = None,
    *,
    hybrids_only: bool = False,
) -> list:
    """Cards for every role scored in section 2; focus_roles drives table + active highlight."""
    if not rows or not (role_ids or combos):
        return []
    bands = us.normalize(bands)["bands"]
    combo_items = normalize_combos(combos)
    sig = (
        id(rows),
        tuple(role_ids),
        tuple((item["ip"], item["oop"]) for item in combo_items),
        bool(hybrids_only),
        bands.get("elite"),
        bands.get("good"),
        bands.get("ok"),
    )
    if _DEPTH_STATS_CACHE["sig"] != sig:
        stats_list = []
        combo_parts = set()
        for item in combo_items:
            combo_parts.add(item["ip"])
            combo_parts.add(item["oop"])
            payload = _depth_card_stats(
                combo_meta(item["ip"], item["oop"]), rows, bands
            )
            if payload:
                stats_list.append(payload)
        if not hybrids_only:
            for role_id in role_ids:
                if role_id in combo_parts:
                    continue
                payload = _depth_card_stats(role_meta(role_id), rows, bands)
                if payload:
                    stats_list.append(payload)
        _DEPTH_STATS_CACHE["sig"] = sig
        _DEPTH_STATS_CACHE["stats"] = stats_list
    return [
        _depth_card_from_stats(stats, focus_roles, bands)
        for stats in _DEPTH_STATS_CACHE["stats"]
    ]


@callback(
    Output("rs-persist", "data"),
    Input("rs-roles", "value"),
    Input("rs-combos", "data"),
    Input("rs-formation", "value"),
    Input("rs-role-mode", "value"),
    Input("rs-set-pieces", "value"),
    Input("rs-pos-match", "value"),
    Input("rs-hybrids-only", "checked"),
    Input("rs-focus-role", "data"),
    Input("rs-search", "value"),
    Input("rs-age", "value"),
    Input("rs-min-score", "value"),
    Input("rs-min-score-mode", "value"),
    Input("rs-pos-filter", "data"),
    Input("rs-foot-filter", "data"),
    Input("rs-phase", "data"),
    Input("rs-group", "data"),
    Input("rs-page-size", "value"),
    Input("rs-set-piece-min-score", "value"),
    State("rs-hydrated", "data"),
    prevent_initial_call=True,
)
def save_page_persist(
    roles,
    combos,
    formation,
    role_mode,
    set_pieces,
    pos_match,
    hybrids_only,
    focus_role,
    search,
    max_age,
    min_score,
    min_score_mode,
    pos_filter,
    foot_filter,
    phase,
    group,
    page_size,
    set_piece_min_score,
    hydrated,
):
    if not hydrated:
        return no_update
    settings = us.load()
    return {
        "roles": _as_list(roles),
        "combos": normalize_combos(combos),
        "formation": formation or None,
        "role_mode": role_mode or "formations",
        "set_pieces": _as_list(set_pieces),
        "hybrids_only": bool(hybrids_only),
        "pos_match": _normalize_pos_match(pos_match),
        "focus_role": _as_list(focus_role),
        "search": (search or "").strip(),
        "max_age": str(max_age or "99"),
        "min_score": _persist_min_score(min_score, settings),
        "min_score_mode": min_score_mode or "all",
        "pos_filter": pos_filter or "all",
        "foot_filter": foot_filter or "",
        "phase": phase or "all",
        "group": group or "all",
        "page_size": _persist_page_size(page_size, settings),
        "set_piece_min_score": set_piece_min_score,
    }


# Copy session-stored UI state without Input/State on rs-persist (avoids a Dash dependency cycle).
clientside_callback(
    """
    function(n) {
        if (!n) {
            return window.dash_clientside.no_update;
        }
        try {
            const raw = window.sessionStorage.getItem("rs-persist");
            if (raw == null || raw === "") {
                return {};
            }
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (e) {
            return {};
        }
    }
    """,
    Output("rs-persist-boot", "data"),
    Input("rs-hydrate-tick", "n_intervals"),
)


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-roles", "data", allow_duplicate=True),
    Output("rs-combos", "data", allow_duplicate=True),
    Output("rs-role-mode", "value", allow_duplicate=True),
    Output("rs-formation", "value", allow_duplicate=True),
    Output("rs-set-pieces", "value"),
    Output("rs-pos-match", "value"),
    Output("rs-hybrids-only", "checked"),
    Output("rs-focus-role", "data", allow_duplicate=True),
    Output("rs-hydrated", "data"),
    Output("rs-role-mode-prev", "data"),
    Output("rs-table", "sort_by", allow_duplicate=True),
    Output("rs-search", "value"),
    Output("rs-age", "value", allow_duplicate=True),
    Output("rs-min-score", "value"),
    Output("rs-min-score-mode", "value"),
    Output("rs-pos-filter", "data", allow_duplicate=True),
    Output("rs-foot-filter", "data", allow_duplicate=True),
    Output("rs-phase", "data", allow_duplicate=True),
    Output("rs-phase-row", "children", allow_duplicate=True),
    Output("rs-group", "data", allow_duplicate=True),
    Output("rs-group-row", "children", allow_duplicate=True),
    Output("rs-page-size", "value", allow_duplicate=True),
    Output("rs-set-piece-min-score", "value"),
    Input("rs-persist-boot", "data"),
    State("rs-hydrated", "data"),
    prevent_initial_call=True,
)
def hydrate_page_persist(persist, hydrated):
    _skip = (no_update,) * 24
    if hydrated:
        return _skip
    raw = persist or {}
    persist = {**PERSIST_DEFAULTS, **raw}
    settings = us.load()
    if not _persist_has_state(raw, settings):
        return (
            *(no_update,) * 9,
            True,
            persist.get("role_mode") or "formations",
            no_update,
            *(no_update,) * 12,
        )
    roles = _as_list(persist.get("roles"))
    combos = normalize_combos(persist.get("combos"))
    mode = persist.get("role_mode") or "formations"
    formation = persist.get("formation") or None
    set_pieces = _as_list(persist.get("set_pieces"))
    if "pos_match" in raw:
        pos_match = _normalize_pos_match(persist.get("pos_match"))
    else:
        pos_match = _normalize_pos_match(persist.get("eligible", True))
    hybrids_only = bool(persist.get("hybrids_only", False))
    focus = _as_list(persist.get("focus_role"))
    phase = persist.get("phase") or "all"
    group = persist.get("group") or "all"
    search = persist.get("search") or ""
    max_age = str(persist.get("max_age") or "99")
    min_score = persist.get("min_score")
    if min_score is None:
        min_score_out = no_update
    else:
        min_score_out = min_score
    min_score_mode = persist.get("min_score_mode") or "all"
    pos_filter = persist.get("pos_filter") or "all"
    foot_filter = persist.get("foot_filter") or ""
    page_size = _persist_page_size(persist.get("page_size"), settings)
    set_piece_min = persist.get("set_piece_min_score")
    # Skip writing role options here — filter_role_options owns that Output.
    # Only write controls that differ from layout defaults to avoid cascading
    # render_shortlist / rescore runs.
    return (
        roles if roles else no_update,
        no_update,
        combos if combos else no_update,
        _changed_or_skip(mode, "formations"),
        formation if formation else no_update,
        set_pieces if set_pieces else no_update,
        _changed_or_skip(pos_match, "yes"),
        hybrids_only if hybrids_only else no_update,
        focus if focus else no_update,
        True,
        mode,
        _sort_by_focus(focus) if focus else no_update,
        _changed_or_skip(search, ""),
        _changed_or_skip(max_age, "99"),
        min_score_out,
        _changed_or_skip(min_score_mode, "all"),
        _changed_or_skip(pos_filter, "all"),
        _changed_or_skip(foot_filter, ""),
        _changed_or_skip(phase, "all"),
        _phase_buttons(phase) if phase != "all" else no_update,
        _changed_or_skip(group, "all"),
        _group_buttons(group) if group != "all" else no_update,
        page_size if page_size is not None else no_update,
        set_piece_min if set_piece_min is not None else no_update,
    )


def _workflow_visibility(parsed, payload):
    has_csv = bool(parsed and parsed.get("players"))
    has_scores = isinstance(payload, dict) and "rows" in payload
    setup_hidden = not has_csv
    results_hidden = not has_scores
    placeholder_hidden = not (has_csv and not has_scores)
    roles_class = "mb-3 rs-next-step" if has_csv and not has_scores else "mb-3"
    return setup_hidden, results_hidden, placeholder_hidden, roles_class


@callback(
    Output("rs-setup-wrap", "hidden"),
    Output("rs-results-wrap", "hidden"),
    Output("rs-need-roles", "hidden"),
    Output("rs-roles-card", "className"),
    Input("rs-parsed", "data"),
    Input("rs-rows", "data"),
)
def reveal_workflow(parsed, payload):
    return _workflow_visibility(parsed, payload)


@callback(
    Output("rs-player-modal", "is_open"),
    Output("rs-player-modal-title", "children"),
    Output("rs-player-modal-body", "children"),
    Output("rs-table", "active_cell"),
    Input("rs-table", "active_cell"),
    Input("rs-player-modal-close", "n_clicks"),
    Input("rs-player-modal", "is_open"),
    State("rs-table", "derived_viewport_data"),
    State("rs-parsed", "data"),
    State("rs-rows", "data"),
    State("rs-focus-role", "data"),
    State("rs-hybrids-only", "checked"),
    State("rs-config", "value"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def open_player_modal(
    active_cell,
    _close_clicks,
    is_open,
    viewport,
    parsed,
    payload,
    focus_role,
    hybrids_only,
    pack_id,
    settings,
):
    if ctx.triggered_id == "rs-player-modal":
        # Backdrop / Escape / header X — keep Dash in sync when the modal closes itself.
        if not is_open:
            return False, no_update, no_update, None
        return no_update, no_update, no_update, no_update
    if ctx.triggered_id == "rs-player-modal-close":
        return False, no_update, no_update, None
    if not active_cell or active_cell.get("column_id") != "Name":
        return no_update, no_update, no_update, no_update
    row_idx = active_cell.get("row")
    if not isinstance(viewport, list) or row_idx is None:
        return no_update, no_update, no_update, no_update
    try:
        row_idx = int(row_idx)
    except (TypeError, ValueError):
        return no_update, no_update, no_update, no_update
    if row_idx < 0 or row_idx >= len(viewport):
        return no_update, no_update, no_update, no_update
    row = viewport[row_idx] or {}
    name = str(row.get("Name") or "").strip()
    club = str(row.get("Club") or "").strip()
    player = _find_parsed_player(parsed, name, club)
    if not player:
        return (
            True,
            name or "Player",
            html.Div(
                "Could not load full player details from the uploaded CSV.",
                className="rs-player-missing",
            ),
            None,
        )
    if pack_id:
        rc.load_pack(pack_id)
    view_roles = _hybrid_only_roles(
        _resolved_view_roles(payload, focus_role),
        (payload or {}).get("combos"),
        hybrids_only,
    )
    scored = _find_scored_row(payload, name, club)
    position_eligible = None
    if scored is not None and view_roles:
        position_eligible = _position_eligibility(
            scored,
            view_roles,
            (payload or {}).get("combos"),
        )
    title = player.get("name") or name or "Player"
    return (
        True,
        title,
        _player_detail_card(
            player,
            settings,
            position_eligible=position_eligible,
        ),
        None,
    )


@callback(
    Output("rs-phase", "data"),
    Output("rs-phase-row", "children"),
    Input({"type": "rs-phase", "phase": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_phase(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    phase = ctx.triggered_id["phase"]
    return phase, _phase_buttons(phase)


@callback(
    Output("rs-single-panel", "hidden"),
    Output("rs-hybrid-panel", "hidden"),
    Output("rs-formation-panel", "hidden"),
    Output("rs-filter-toolbar", "hidden"),
    Output("rs-phase-filter-wrap", "hidden"),
    Output("rs-roles-body", "className"),
    Input("rs-role-mode", "value"),
)
def sync_role_mode(mode):
    mode = mode or "formations"
    body = "rs-roles-body"
    if mode == "formations":
        body += " rs-roles-body-formations"
    return (
        mode != "single",
        mode != "hybrid",
        mode != "formations",
        mode == "formations",
        mode != "single",
        body,
    )


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-combos", "data", allow_duplicate=True),
    Output("rs-formation", "value", allow_duplicate=True),
    Output("rs-focus-role", "data", allow_duplicate=True),
    Output("rs-combo-ip", "value", allow_duplicate=True),
    Output("rs-combo-oop", "value", allow_duplicate=True),
    Output("rs-squad-marked", "data", allow_duplicate=True),
    Output("rs-role-mode-prev", "data", allow_duplicate=True),
    Output("rs-table", "sort_by", allow_duplicate=True),
    Input("rs-role-mode", "value"),
    State("rs-role-mode-prev", "data"),
    prevent_initial_call=True,
)
def clear_on_role_mode_change(mode, prev_mode):
    """Reset scored-role selections when switching Single / Hybrid / Formations."""
    mode = mode or "formations"
    if prev_mode == mode:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            mode,
            no_update,
        )
    if prev_mode is None:
        # Seed after hydrate/layout without wiping restored selections.
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            mode,
            no_update,
        )
    return [], [], None, [], None, None, [], mode, []


@callback(
    Output("rs-group", "data"),
    Output("rs-group-row", "children"),
    Input({"type": "rs-group", "group": ALL}, "n_clicks"),
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
    Output("rs-roles", "data"),
    Input("rs-phase", "data"),
    Input("rs-group", "data"),
    Input("rs-roles", "value"),
    Input("rs-combos", "data"),
)
def filter_role_options(phase, group, selected, combos):
    keep = _as_list(selected)
    for item in normalize_combos(combos):
        keep.extend((item["ip"], item["oop"]))
    return role_options(phase=phase, group=group, keep=keep) or []


@callback(
    Output("rs-combo-ip", "data"),
    Output("rs-combo-oop", "data"),
    Input("rs-group", "data"),
    Input("rs-combo-ip", "value"),
    Input("rs-combo-oop", "value"),
)
def filter_combo_role_options(group, ip, oop):
    group = group or "all"
    return (
        role_options(phase="IP", group=group, keep=_as_list(ip)) or [],
        role_options(phase="OOP", group=group, keep=_as_list(oop)) or [],
    )


@callback(
    Output("rs-role-pills", "children"),
    Input("rs-roles", "value"),
)
def render_pills(role_ids):
    return _role_pills(_as_list(role_ids))


@callback(
    Output("rs-combo-pills", "children"),
    Input("rs-combos", "data"),
    Input("ui-settings", "data"),
)
def render_combo_pills(combos, settings):
    return _combo_pills(combos, settings)


@callback(
    Output("rs-combos", "data"),
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-roles", "data", allow_duplicate=True),
    Output("rs-combo-ip", "value"),
    Output("rs-combo-oop", "value"),
    Input("rs-combo-add", "n_clicks"),
    State("rs-combo-ip", "value"),
    State("rs-combo-oop", "value"),
    State("rs-combos", "data"),
    State("rs-roles", "value"),
    State("rs-phase", "data"),
    State("rs-group", "data"),
    prevent_initial_call=True,
)
def add_combo(_clicks, ip, oop, combos, selected, phase, group):
    if not ip or not oop:
        return no_update, no_update, no_update, no_update, no_update
    current = normalize_combos(combos)
    incoming = normalize_combos([{"ip": ip, "oop": oop}])
    if not incoming:
        return no_update, no_update, no_update, None, None
    pair = incoming[0]
    if any(item["ip"] == pair["ip"] and item["oop"] == pair["oop"] for item in current):
        return current, no_update, no_update, None, None
    current.append(pair)
    roles = _as_list(selected)
    for role_id in (pair["ip"], pair["oop"]):
        if role_id not in roles:
            roles.append(role_id)
    keep = list(roles)
    for item in current:
        keep.extend((item["ip"], item["oop"]))
    options = role_options(phase=phase, group=group, keep=keep) or []
    return current, roles, options, None, None


@callback(
    Output("rs-combos", "data", allow_duplicate=True),
    Input({"type": "rs-combo-pill", "combo": ALL}, "n_clicks"),
    State("rs-combos", "data"),
    prevent_initial_call=True,
)
def remove_combo(n_clicks, combos):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    target = ctx.triggered_id.get("combo")
    if not target or target == "_":
        return no_update
    parsed = parse_combo_id(target)
    if not parsed:
        return no_update
    ip, oop = parsed
    return [
        item
        for item in normalize_combos(combos)
        if not (item["ip"] == ip and item["oop"] == oop)
    ]


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-combos", "data", allow_duplicate=True),
    Input({"type": "rs-pill", "role": ALL}, "n_clicks"),
    State("rs-roles", "value"),
    State("rs-combos", "data"),
    prevent_initial_call=True,
)
def remove_role(n_clicks, selected, combos):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    role_id = ctx.triggered_id["role"]
    if role_id == "_":
        return no_update, no_update
    remaining = [item for item in _as_list(selected) if item != role_id]
    kept = [
        item
        for item in normalize_combos(combos)
        if item["ip"] in remaining and item["oop"] in remaining
    ]
    return remaining, kept


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Input("rs-add-all-roles", "n_clicks"),
    State("rs-phase", "data"),
    State("rs-group", "data"),
    State("rs-roles", "value"),
    prevent_initial_call=True,
)
def add_all_filtered_roles(n_clicks, phase, group, selected):
    """Add every role matching the current Phase / Group chip filters."""
    if not n_clicks:
        return no_update
    matching = [
        opt["value"]
        for opt in role_options(phase=phase, group=group, keep=[])
    ]
    if not matching:
        return no_update
    current = _as_list(selected)
    # Union: keep any already-selected roles, then append newly matched ones.
    merged = list(dict.fromkeys([*current, *matching]))
    return merged


@callback(
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-combos", "data", allow_duplicate=True),
    Input({"type": "rs-clear-roles", "loc": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def clear_roles(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    if ctx.triggered_id.get("loc") == "_":
        return no_update, no_update
    return [], []


@callback(
    Output("rs-age", "data"),
    Output("rs-age", "value", allow_duplicate=True),
    Output("rs-band-legend", "children"),
    Input("ui-settings", "data"),
    State("rs-age", "value"),
    prevent_initial_call="initial_duplicate",
)
def apply_ui_settings(settings, age):
    settings = us.normalize(settings)
    ages = us.age_options(settings)
    return ages, us.clamp_choice(age, ages, "99"), _band_legend(settings)


@callback(
    Output("rs-focus-role", "data", allow_duplicate=True),
    Output("rs-table", "sort_by", allow_duplicate=True),
    Input({"type": "rs-depth", "role": ALL}, "n_clicks"),
    State("rs-focus-role", "data"),
    prevent_initial_call=True,
)
def focus_view_role(n_clicks, current_focus):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    role = ctx.triggered_id["role"]
    if role == "_":
        return no_update, no_update
    column = _depth_id_column(role)
    if not column:
        return no_update, no_update
    selected = _focus_roles(current_focus)
    if column in selected:
        next_focus = [item for item in selected if item != column]
    else:
        next_focus = selected + [column]
    # Update focus + sort together so render_shortlist runs once (not twice).
    return next_focus, _sort_by_focus(next_focus)


@callback(
    Output("rs-table", "sort_by"),
    Output("rs-set-pieces-prev", "data"),
    Input("rs-set-pieces", "value"),
    State("rs-set-pieces-prev", "data"),
    prevent_initial_call=True,
)
def sync_table_sort(set_pieces, prev_pieces):
    selected_pieces = _as_list(set_pieces)
    prev = _as_list(prev_pieces)
    added = [piece for piece in selected_pieces if piece not in prev]
    if added:
        column = set_piece_sort_column(added[-1])
        if column:
            return [{"column_id": column, "direction": "desc"}], selected_pieces
    return no_update, selected_pieces


@callback(
    Output("rs-config", "data"),
    Input("rs-config-tick", "n_intervals"),
)
def refresh_config_options(_n):
    return rc.pack_options()


@callback(
    Output("rs-formation", "data"),
    Output("rs-formation", "value"),
    Input("rs-formation-tick", "n_intervals"),
    State("rs-formation", "value"),
)
def refresh_formation_options(_n, current):
    options = fm.pack_options()
    allowed = {opt["value"] for opt in options}
    if current and current not in allowed:
        return options, None
    return options, no_update


@callback(
    Output("rs-combos", "data", allow_duplicate=True),
    Output("rs-roles", "value", allow_duplicate=True),
    Output("rs-roles", "data", allow_duplicate=True),
    Output("rs-role-mode", "value"),
    Output("rs-focus-role", "data", allow_duplicate=True),
    Output("rs-table", "sort_by", allow_duplicate=True),
    Input("rs-formation", "value"),
    State("rs-phase", "data"),
    State("rs-group", "data"),
    State("rs-combos", "data"),
    prevent_initial_call=True,
)
def load_formation(formation_id, phase, group, current_combos):
    if not formation_id or not fm.exists(formation_id):
        return no_update, no_update, no_update, no_update, no_update, no_update
    formation = fm.load(formation_id, persist=False)
    combos = fm.combos_from_formation(formation)
    keep = []
    for item in combos:
        keep.extend((item["ip"], item["oop"]))
    options = role_options(phase=phase, group=group, keep=keep) or []
    # Hydrate restores formation + combos together; skip all writes when unchanged.
    if normalize_combos(current_combos) == normalize_combos(combos):
        return no_update, no_update, no_update, no_update, no_update, no_update
    first = _first_combo_column(combos)
    focus = [first] if first else []
    return combos, [], options, "formations", focus, _sort_by_focus(focus)


@callback(
    Output("rs-page-size", "data"),
    Output("rs-page-size", "value"),
    Input("ui-settings", "data"),
    State("rs-page-size", "value"),
)
def sync_rs_page_size_from_settings(settings, page_size):
    from components.player_table import default_page_size_value, page_size_select_data

    settings = us.normalize(settings)
    data = page_size_select_data(settings)
    default = default_page_size_value(settings)
    return data, us.clamp_choice(page_size, data, default)


@callback(
    Output("rs-rows", "data"),
    Output("rs-focus-role", "data"),
    Output("rs-table", "sort_by", allow_duplicate=True),
    Input("rs-parsed", "data"),
    Input("rs-parsed-historical", "data"),
    Input("rs-roles", "value"),
    Input("rs-combos", "data"),
    Input("rs-config", "value"),
    Input("ui-settings", "data"),
    State("rs-focus-role", "data"),
    prevent_initial_call="initial_duplicate",
)
def rescore(parsed, hist_parsed, role_ids, combos, pack_id, settings, current_focus):
    if pack_id:
        rc.load_pack(pack_id)
    if not parsed or not parsed.get("players"):
        return None, no_update, no_update
    settings = us.normalize(settings)
    tier_w = us.tier_weights(settings)
    hybrid_w = us.hybrid_weights(settings)
    profiles = us.set_piece_profiles(settings)
    combos = normalize_combos(combos)
    role_ids = _as_list(role_ids)
    needed = list(role_ids)
    for item in combos:
        for role_id in (item["ip"], item["oop"]):
            if role_id not in needed:
                needed.append(role_id)
    if not needed:
        return None, no_update, no_update
    rows = apply_combos(
        score_players(
            parsed["players"],
            needed,
            tier_weights=tier_w,
            set_piece_profiles=profiles,
        ),
        combos,
        ip_weight=hybrid_w["ip"],
        oop_weight=hybrid_w["oop"],
    )
    historical_by_key: dict[str, dict] = {}
    hist_players = parsed_historical_players(hist_parsed)
    if hist_players:
        hist_rows = apply_combos(
            score_players(
                hist_players,
                needed,
                tier_weights=tier_w,
                set_piece_profiles=profiles,
            ),
            combos,
            ip_weight=hybrid_w["ip"],
            oop_weight=hybrid_w["oop"],
        )
        historical_by_key = {
            player_row_key(row): row for row in hist_rows if player_row_key(row)
        }
    labels = combo_score_labels(needed, combos)
    selected = _focus_roles(current_focus)
    kept = [role for role in selected if role in labels]
    if kept and kept == selected:
        focus = no_update
        sort = no_update
    elif ctx.triggered_id == "rs-combos":
        first = _first_combo_column(combos)
        focus = [first] if first in labels else []
        sort = _sort_by_focus(focus)
    else:
        focus = kept
        sort = _sort_by_focus(focus)
    return (
        {
            "filename": parsed.get("filename", "export.csv"),
            "rows": rows,
            "roles": labels,
            "role_ids": needed,
            "combos": combos,
            "historical_by_key": historical_by_key,
        },
        focus,
        sort,
    )


@callback(
    Output("rs-pos-bar", "children"),
    Output("rs-summary", "children"),
    Output("rs-depth-wrap", "hidden"),
    Output("rs-table", "data"),
    Output("rs-table", "columns"),
    Output("rs-table", "tooltip_header"),
    Output("rs-table", "tooltip_data"),
    Output("rs-table", "style_data_conditional"),
    Output("rs-table", "style_header_conditional"),
    Output("rs-table", "css"),
    Output("rs-table", "style_table"),
    Output("rs-table", "page_size"),
    Output("rs-table", "page_current"),
    Output("rs-table", "selected_row_ids"),
    Output("rs-table-cols-sig", "data"),
    Output("rs-hist", "figure"),
    Output("rs-table-caption", "children"),
    Output("rs-table-empty", "children"),
    Output("rs-table-empty", "hidden"),
    Output("rs-table-shell", "hidden"),
    Input("rs-rows", "data"),
    Input("rs-focus-role", "data"),
    Input("rs-search", "value"),
    Input("rs-age", "value"),
    Input("rs-min-score", "value"),
    Input("rs-min-score-mode", "value"),
    Input("rs-pos-match", "value"),
    Input("rs-hybrids-only", "checked"),
    Input("rs-set-pieces", "value"),
    Input("rs-set-piece-min-score", "value"),
    Input("rs-squad-marked", "data"),
    Input("rs-pos-filter", "data"),
    Input("rs-foot-filter", "data"),
    Input("rs-page-size", "value"),
    Input("rs-table", "sort_by"),
    Input("theme", "data"),
    Input("rs-hist-open", "data"),
    Input("ui-settings", "data"),
    Input("rs-hydrated", "data"),
    State("rs-table-cols-sig", "data"),
)
def render_shortlist(
    payload,
    focus_role,
    query,
    max_age,
    min_score,
    min_score_mode,
    pos_match,
    hybrids_only,
    set_pieces,
    set_piece_min,
    squad_marked,
    pos_filter,
    foot_filter,
    page_size,
    sort_by,
    theme,
    hist_open,
    settings,
    hydrated,
    cols_sig,
):
    # Wait for persist hydrate so filters are restored before the first table build.
    if not hydrated:
        return (no_update,) * 20
    settings = us.normalize(settings)
    bands = settings["bands"]
    foot_thresholds = settings["foot_thresholds"]
    bins = us.hist_bins(settings)
    historical_by_key = (payload or {}).get("historical_by_key") or {}
    compare = bool(historical_by_key)
    empty_cols = [{"name": "Name", "id": "Name"}]
    empty_style = _score_styles([], settings, theme)
    empty_header = _score_header_styles([], theme)
    empty_css = _table_css([], theme)
    hybrids_only = bool(hybrids_only)
    page_size = int(page_size or 50)
    empty_table_style = _table_style_table(0, page_size)
    empty_page, empty_sig = _table_page_state(empty_cols, cols_sig)
    hist_open = bool(hist_open)
    pos_filter = pos_filter or "all"
    foot_filter = foot_filter or ""
    if not payload or not payload.get("rows"):
        return (
            None,
            [],
            True,
            [],
            empty_cols,
            {},
            [],
            empty_style,
            empty_header,
            empty_css,
            empty_table_style,
            page_size,
            empty_page,
            [],
            empty_sig,
            _blank_fig(theme) if hist_open else no_update,
            "Upload a file and pick at least one role in section 2.",
            None,
            True,
            False,
        )
    rows = payload["rows"]
    role_ids = payload.get("role_ids") or []
    combos = normalize_combos(payload.get("combos"))
    view_roles = _hybrid_only_roles(
        _resolved_view_roles(payload, focus_role),
        combos,
        hybrids_only,
    )
    if not view_roles:
        cards = _depth_panel(
            rows, role_ids, [], bands, combos, hybrids_only=hybrids_only
        )
        return (
            _pos_bar(rows, pos_filter, foot_filter, foot_thresholds),
            cards,
            not cards,
            [],
            empty_cols,
            {},
            [],
            empty_style,
            empty_header,
            empty_css,
            empty_table_style,
            page_size,
            empty_page,
            [],
            empty_sig,
            no_update if not hist_open else _blank_fig(theme),
            "Pick at least one role in section 2.",
            None,
            True,
            False,
        )
    query = (query or "").strip().lower()
    max_age = 99 if max_age is None else int(max_age)
    min_score = us.parse_score_floor(min_score)
    min_score_mode = min_score_mode if min_score_mode in MIN_SCORE_MODES else "all"
    set_piece_min = us.parse_score_floor(set_piece_min)
    pos_match = _normalize_pos_match(pos_match)
    chosen_pieces = _as_list(set_pieces)
    marked_keys = set(_as_list(squad_marked))
    combo_by_col = _combo_columns_by_label(combos)

    filtered = []
    for row in rows:
        if pos_filter != "all" and pos_filter not in (row.get("PosGroups") or []):
            continue
        if foot_filter and not foot_match(row, foot_filter, foot_thresholds):
            continue
        pos_elig = (
            _position_eligibility(row, view_roles, combo_by_col=combo_by_col) or "no"
        )
        if not _passes_pos_match(pos_elig, pos_match):
            continue
        if to_int(row.get("Age")) > max_age:
            continue
        if not _passes_min_score(row, view_roles, min_score, min_score_mode):
            continue
        if set_piece_min > 0 and chosen_pieces:
            piece_cols = [
                set_piece_filter_columns(piece_id)
                for piece_id in chosen_pieces
            ]
            if any(
                _cell_number(row.get(col)) < set_piece_min
                for col in piece_cols
                if col
            ):
                continue
        if query:
            blob = f"{row.get('Name','')} {row.get('Club','')} {row.get('Position','')} {row.get('Division','')}".lower()
            if query not in blob:
                continue
        row = dict(row)
        row["_PosEligible"] = pos_elig
        filtered.append(row)

    _sort_table_rows(filtered, sort_by, view_roles, min_score_mode)

    table_role_cols = _table_role_columns(view_roles, combos, hybrids_only)
    fig = _hist_figure(filtered, view_roles, bins, theme) if hist_open else no_update

    piece_cols = set_piece_columns(set_pieces, us.set_piece_profiles(settings))
    chosen = set(chosen_pieces)
    score_cols = [
        profile["score"]
        for profile in us.set_piece_profiles(settings)
        if profile["id"] in chosen and profile.get("score")
    ] + table_role_cols
    table_cols = list(us.shortlist_columns_for("role_scores", settings))
    table_cols.extend(piece_cols)
    table_cols.extend(table_role_cols)
    columns = _table_columns(table_cols)
    header_tips = _header_tooltips(table_cols, combos=combos)
    table_rows = []
    tooltip_data = []
    for row in filtered:
        row_key = player_row_key(row)
        hist_row = historical_by_key.get(row_key) if compare else None
        item = {}
        tip_row: dict[str, str] = {}
        for key in table_cols:
            if key in score_cols:
                raw = row.get(key)
                band = None
                try:
                    if raw is not None and raw not in {"-", "—", ""}:
                        band = score_band(float(raw), **bands)
                except (TypeError, ValueError):
                    band = None
                item[key] = score_display(
                    raw,
                    hist_row.get(key) if hist_row else None,
                    enabled=compare,
                    color=us.band_text_color(band, settings, theme=theme)
                    if band
                    else None,
                )
            else:
                if key == "Feet":
                    item[key] = feet_cell(row)
                elif key == "Injury":
                    raw = row.get(key)
                    item[key] = injury_cell(raw)
                    tip_row = injury_tooltip_entry(raw)
                else:
                    item[key] = row.get(key, "-")
        item["PosEligible"] = row.get("_PosEligible") or "no"
        item["DivisionTier"] = row.get("DivisionTier") or ""
        if row_key:
            item["id"] = row_key
            item["_key"] = row_key
        table_rows.append(item)
        tooltip_data.append(tip_row)
    page_keys = [str(row.get("id") or "").strip() for row in table_rows]
    selected_rows = [key for key in page_keys if key in marked_keys]
    extras = []
    if pos_filter != "all":
        extras.append(pos_filter)
    if foot_filter:
        extras.append({"foot-L": "left foot", "foot-R": "right foot", "foot-B": "both feet"}[foot_filter])
    extra = f" Position/foot: {', '.join(extras)}." if extras else ""
    piece_note = ""
    if chosen_pieces and set_piece_min > 0:
        piece_note = f" Set-piece min {set_piece_min:g}+ on all checked types."
    mark_note = f" {len(marked_keys)} marked for planned squad." if marked_keys else ""
    min_note = ""
    if min_score > 0:
        role_list = ", ".join(view_roles)
        min_note = (
            f" Min score {min_score:g}+ on {MIN_SCORE_MODES[min_score_mode]}: {role_list}."
        )
    focused = [role for role in _focus_roles(focus_role) if role in view_roles]
    focus_note = f" Focused: {', '.join(focused)}." if focused else ""
    hybrid_note = " Hybrids only." if hybrids_only and combo_column_labels(combos) else ""
    caption = (
        f"{len(filtered)} of {len(rows)} players"
        f"{focus_note}{hybrid_note}{min_note}{extra}{piece_note}{mark_note}"
        f" · {payload.get('filename')}."
    )
    cards = _depth_panel(
        rows,
        role_ids,
        _focus_roles(focus_role),
        bands,
        combos,
        hybrids_only=hybrids_only,
    )
    page_current, new_sig = _table_page_state(columns, cols_sig)
    no_matches = not table_rows
    empty_panel = (
        _no_match_placeholder(
            pos_match=pos_match,
            pos_filter=pos_filter,
            foot_filter=foot_filter,
            min_score=min_score,
            set_piece_min=set_piece_min,
            query=query,
            max_age=max_age,
        )
        if no_matches
        else None
    )
    # Focus/sort clicks should not rebuild the position bar or remount depth cards.
    # Card active state is synced clientside from rs-focus-role.
    triggered_props = {item.get("prop_id", "") for item in (ctx.triggered or [])}
    focus_sort_only = bool(triggered_props) and triggered_props.issubset(
        {"rs-focus-role.data", "rs-table.sort_by"}
    )
    sort_only = triggered_props == {"rs-table.sort_by"}
    same_cols = new_sig == cols_sig
    pos_bar = (
        no_update
        if focus_sort_only
        else _pos_bar(rows, pos_filter, foot_filter, foot_thresholds)
    )
    depth_cards = no_update if focus_sort_only else cards
    depth_hidden = no_update if focus_sort_only else (not cards)
    style_data, style_header, table_css_rules = _cached_table_chrome(
        score_cols, settings, theme
    )
    if focus_sort_only and same_cols:
        # Column set unchanged (typical pure sort) — keep DataTable chrome.
        out_columns = no_update
        out_tips = no_update
        out_style_data = no_update
        out_style_header = no_update
        out_css = no_update
        out_sig = no_update
        out_page = no_update
    else:
        out_columns = columns
        out_tips = header_tips
        out_style_data = style_data
        out_style_header = style_header
        out_css = table_css_rules
        out_sig = new_sig
        out_page = page_current
    if sort_only and same_cols:
        # Sorting alone: still refresh row order/selection, skip chrome + depth.
        depth_cards = no_update
        depth_hidden = no_update
    return (
        pos_bar,
        depth_cards,
        depth_hidden,
        table_rows,
        out_columns,
        out_tips,
        tooltip_data,
        out_style_data,
        out_style_header,
        out_css,
        _table_style_table(len(table_rows), page_size),
        page_size,
        out_page,
        selected_rows,
        out_sig,
        fig,
        caption,
        empty_panel,
        not no_matches,
        no_matches,
    )


clientside_callback(
    """
    function(focusRoles) {
        const focused = new Set(
            (Array.isArray(focusRoles) ? focusRoles : [])
                .map(function(r) { return String(r || ""); })
                .filter(Boolean)
        );
        const cards = document.querySelectorAll("#rs-summary .rs-depth-card");
        cards.forEach(function(card) {
            const role = card.getAttribute("data-rs-role") || "";
            const on = role && focused.has(role);
            card.classList.toggle("active", !!on);
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("rs-summary", "className"),
    Input("rs-focus-role", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(_sig) {
        requestAnimationFrame(function() {
            window.dispatchEvent(new Event("resize"));
        });
        return "";
    }
    """,
    Output("rs-table-layout-nudge", "children"),
    Input("rs-table-cols-sig", "data"),
    prevent_initial_call=True,
)


SQUAD_PREVIEW_MAX_ROWS = 8


def _squad_preview_panel(
    marked, payload, view_roles, set_pieces, *, hybrids_only: bool = False
) -> html.Div:
    view_roles = _as_list(view_roles)
    if not payload or not view_roles:
        return html.P("Score roles in section 2 first.", className="text-muted mb-0")
    marked = _as_list(marked)
    if not marked:
        return html.P("No players marked yet.", className="text-muted mb-0")
    rows = payload.get("rows") or []
    combos = normalize_combos(payload.get("combos"))
    include_parts = not hybrids_only
    export_rows = planned_squad_export_rows(
        rows,
        marked,
        view_roles,
        combos,
        _as_list(set_pieces),
        include_parts=include_parts,
    )
    if not export_rows:
        return html.P("Marked players are not in the current data.", className="text-muted mb-0")
    fieldnames = planned_squad_fieldnames(
        view_roles, combos, _as_list(set_pieces), include_parts=include_parts
    )
    preview_rows = export_rows[:SQUAD_PREVIEW_MAX_ROWS]
    extra = len(export_rows) - len(preview_rows)
    parts = [f"{len(export_rows)} player(s) marked", f"{len(fieldnames)} columns"]
    if set_pieces:
        parts.append(f"set pieces: {', '.join(_as_list(set_pieces))}")
    if extra > 0:
        parts.append(f"showing first {len(preview_rows)}")
    return html.Div(
        [
            html.Div(" · ".join(parts), className="rs-squad-preview-note"),
            dash_table.DataTable(
                columns=[{"name": col, "id": col} for col in fieldnames],
                data=preview_rows,
                page_action="none",
                style_table={"overflowX": "auto"},
                style_cell={
                    "fontFamily": "Inter, Segoe UI, sans-serif",
                    "fontSize": "12px",
                    "padding": "6px",
                    "whiteSpace": "nowrap",
                    "backgroundColor": "transparent",
                    "color": "inherit",
                },
                style_header={
                    "fontWeight": "600",
                    "fontSize": "11px",
                    "textTransform": "uppercase",
                    "backgroundColor": "transparent",
                    "color": "inherit",
                },
            ),
        ]
    )


@callback(
    Output("rs-squad-clear-btn", "disabled"),
    Input("rs-squad-marked", "data"),
)
def toggle_clear_marks_btn(marked):
    return not _as_list(marked)


@callback(
    Output("rs-squad-preview", "children"),
    Output("rs-squad-btn", "disabled"),
    Input("rs-squad-marked", "data"),
    Input("rs-rows", "data"),
    Input("rs-focus-role", "data"),
    Input("rs-set-pieces", "value"),
    Input("rs-hybrids-only", "checked"),
)
def render_squad_preview(marked, payload, focus_role, set_pieces, hybrids_only):
    marked_list = _as_list(marked)
    triggered = {
        (t.get("prop_id") or "").split(".")[0]
        for t in (ctx.triggered or [])
        if t.get("prop_id")
    }
    # Focus-only with nothing marked: skip rebuilding the empty preview panel.
    if triggered == {"rs-focus-role"} and not marked_list:
        return no_update, True
    combos = normalize_combos((payload or {}).get("combos"))
    hybrids_only = bool(hybrids_only)
    view_roles = _hybrid_only_roles(
        _resolved_view_roles(payload, focus_role), combos, hybrids_only
    )
    export_rows = []
    if payload and view_roles and marked_list:
        export_rows = planned_squad_export_rows(
            payload.get("rows") or [],
            marked_list,
            view_roles,
            combos,
            _as_list(set_pieces),
            include_parts=not hybrids_only,
        )
    return (
        _squad_preview_panel(
            marked, payload, view_roles, set_pieces, hybrids_only=hybrids_only
        ),
        not export_rows,
    )


@callback(
    Output("rs-download-squad", "data"),
    Input("rs-squad-btn", "n_clicks"),
    State("rs-squad-marked", "data"),
    State("rs-rows", "data"),
    State("rs-focus-role", "data"),
    State("rs-set-pieces", "value"),
    State("rs-hybrids-only", "checked"),
    prevent_initial_call=True,
)
def download_squad_csv(n_clicks, marked, payload, focus_role, set_pieces, hybrids_only):
    if not n_clicks or not payload or not payload.get("rows"):
        return no_update
    hybrids_only = bool(hybrids_only)
    combos = normalize_combos(payload.get("combos"))
    view_roles = _hybrid_only_roles(
        _resolved_view_roles(payload, focus_role), combos, hybrids_only
    )
    marked = _as_list(marked)
    if not view_roles or not marked:
        return no_update
    name = (payload.get("filename") or "role_scores").rsplit(".", 1)[0]
    text = planned_squad_csv(
        payload["rows"],
        marked,
        view_roles,
        combos,
        _as_list(set_pieces),
        include_parts=not hybrids_only,
    )
    return dict(content=text, filename=f"{name}_planned_squad.csv")


@callback(
    Output("rs-download-csv", "data"),
    Input("rs-csv-btn", "n_clicks"),
    State("rs-rows", "data"),
    State("rs-focus-role", "data"),
    State("rs-hybrids-only", "checked"),
    prevent_initial_call=True,
)
def download_csv(n_clicks, payload, focus_role, hybrids_only):
    if not n_clicks or not payload or not payload.get("rows"):
        return no_update
    hybrids_only = bool(hybrids_only)
    combos = normalize_combos(payload.get("combos"))
    view_roles = _hybrid_only_roles(
        _resolved_view_roles(payload, focus_role), combos, hybrids_only
    )
    if not view_roles:
        return no_update
    role_labels = _table_role_columns(view_roles, combos, hybrids_only)
    name = (payload.get("filename") or "role_scores").rsplit(".", 1)[0]
    text = scored_csv(payload["rows"], role_labels)
    return dict(content=text, filename=f"{name}_role_scores.csv")

