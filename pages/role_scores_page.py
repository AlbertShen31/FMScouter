"""Role scores page: upload an FM attribute CSV, pick roles, filter, export."""
from __future__ import annotations

import base64
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

from role_scorer import (
    COMBO_IP_WEIGHT,
    COMBO_OOP_WEIGHT,
    FOOT_STRENGTH_NAMES,
    FootStrength,
    GROUP_DEFS,
    POS_CARDS,
    SET_PIECE_PROFILES,
    apply_combos,
    combo_column,
    combo_column_labels,
    combo_meta,
    combo_score_labels,
    expand_view_role_columns,
    foot_filter_help,
    foot_filter_hints,
    foot_match,
    foot_strength,
    group_abbr_tone,
    normalize_combos,
    parse_combo_id,
    parse_export,
    planned_squad_csv,
    planned_squad_export_rows,
    planned_squad_fieldnames,
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
    set_piece_hint,
    set_piece_sort_column,
)
from canvas_export import build_canvas
from attr_columns import attr_grid, attr_group_columns, attr_row
import formations as fm
import role_config as rc
import ui_settings as us

register_page(__name__, path="/", name="Role scores")

PERSIST_DEFAULTS = {
    "roles": [],
    "combos": [],
    "formation": None,
    "role_mode": "formations",
    "set_pieces": [],
    "hybrids_only": False,
    "pos_match": "yes",
    "focus_role": [],
}

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
    return (theme or "dark") != "light"


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
    f"Hybrid score = ({COMBO_IP_WEIGHT:g}× in possession + {COMBO_OOP_WEIGHT:g}× out of possession) "
    f"÷ {COMBO_IP_WEIGHT + COMBO_OOP_WEIGHT:g}. Both part scores stay in the table. "
    "A player is eligible if they can play either part."
)

ROLE_MODE_DATA = [
    {"label": "Single roles", "value": "single"},
    {"label": "Hybrid roles", "value": "hybrid"},
    {"label": "Formations", "value": "formations"},
]


def _help_icon(tip: str, help_id: str) -> list:
    return [
        html.Span(
            "ⓘ",
            id=help_id,
            className="rs-help",
            role="img",
            **{"aria-label": "Help"},
        ),
        dbc.Tooltip(
            tip,
            target=help_id,
            placement="top",
            class_name="rs-help-tooltip",
        ),
    ]


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


def _upload_status_bar(count: int, filename: str) -> list:
    return [
        html.Span("✓", className="rs-upload-ok"),
        html.Span(f"{count:,} players loaded", className="rs-upload-count"),
        html.Span("·", className="rs-upload-sep"),
        html.Span(filename, className="rs-upload-name", title=filename),
        html.Span("·", className="rs-upload-sep"),
    ]


def _upload_error(message: str) -> html.Div:
    return html.Div(message, className="rs-upload-error")


PLAYER_IDENTITY_FIELDS = [
    ("Age", "age"),
    ("Club", "club"),
    ("Division", "division"),
    ("Nation", "nation"),
    ("Position", "position"),
    ("Best pos", "best_pos"),
    ("Style", "style"),
    ("Height", "height"),
    ("Left foot", "left_foot"),
    ("Right foot", "right_foot"),
    ("Rec", "rec"),
    ("Inf", "inf"),
    ("Injury", "injury"),
    ("Squad", "squad"),
]


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


_POS_ELIG_TIPS = {
    "yes": "Eligible for every focused / viewed role (hybrids need both parts)",
    "partial": "Only matches some of the focused / viewed roles (or one hybrid part)",
    "no": "Not eligible for the focused / viewed role(s)",
}


def _player_detail_card(
    player: dict,
    settings=None,
    *,
    position_eligible: str | None = None,
) -> html.Div:
    settings = us.normalize(settings)
    bands = settings["bands"]
    identity = []
    for label, key in PLAYER_IDENTITY_FIELDS:
        if player.get(key) in (None, ""):
            continue
        value_class = "rs-player-id-value"
        tip = None
        if key == "position" and position_eligible in _POS_ELIG_TIPS:
            value_class += {
                "yes": " is-eligible",
                "partial": " is-partial",
                "no": " is-ineligible",
            }[position_eligible]
            tip = _POS_ELIG_TIPS[position_eligible]
        identity.append(
            html.Div(
                [
                    html.Span(label, className="rs-player-id-label"),
                    html.Span(
                        str(player.get(key) or "—"),
                        className=value_class,
                        title=tip,
                    ),
                ],
                className="rs-player-id-item",
            )
        )
    return html.Div(
        [
            html.Div(identity, className="rs-player-identity"),
            _player_attributes(player, bands),
        ],
        className="rs-player-detail",
    )


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
    lines = []
    for profile in SET_PIECE_PROFILES:
        lines.append(
            html.Div(
                [
                    html.Span(profile["label"], className="rs-set-piece-name"),
                    html.Span(profile.get("detail") or "", className="rs-set-piece-detail"),
                    html.Span(set_piece_formula(profile), className="rs-set-piece-formula"),
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
                                title=set_piece_hint(),
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


def _hybrid_roles_panel() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    _field_label(
                        "Hybrid roles",
                        primary=True,
                        tip=HYBRID_HELP,
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


def _combo_pills(combos: list[dict] | None) -> list:
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
                title=f"{meta['name']} · {COMBO_IP_WEIGHT:g}× IP + {COMBO_OOP_WEIGHT:g}× OOP",
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
        dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle(id="rs-player-modal-title"),
                    close_button=True,
                ),
                dbc.ModalBody(id="rs-player-modal-body", className="rs-player-modal-body"),
                dbc.ModalFooter(
                    dbc.Button(
                        "Close",
                        id="rs-player-modal-close",
                        n_clicks=0,
                        className="rs-player-modal-close",
                    )
                ),
            ],
            id="rs-player-modal",
            is_open=False,
            size="xl",
            centered=True,
            scrollable=False,
            backdrop=True,
            keyboard=True,
            className="rs-player-modal",
            content_class_name="rs-player-modal-content",
        ),
        html.Div(
            [
                html.Button(id={"type": "rs-pos", "pos": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-foot", "foot": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-depth", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-pill", "role": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-group", "group": "_"}, n_clicks=0),
                html.Button(id={"type": "rs-combo-pill", "combo": "_"}, n_clicks=0),
            ],
            hidden=True,
        ),
        dcc.Download(id="rs-download-csv"),
        dcc.Download(id="rs-download-canvas"),
        dcc.Download(id="rs-download-squad"),
        html.H1("FM26 role scores", className="mt-2 mb-3"),
        dbc.Card(
            [
                dbc.CardHeader("1. Upload export"),
                dbc.CardBody(
                    [
                        html.Div(
                            dcc.Upload(
                                id="rs-upload",
                                children=html.Div(
                                    ["Drag a CSV here, or ", html.A("browse")]
                                ),
                                className="rs-upload",
                                multiple=False,
                            ),
                            id="rs-upload-wrap",
                        ),
                        html.Div(
                            [
                                html.Div(id="rs-upload-status", className="rs-upload-status"),
                                html.Div(
                                    dcc.Upload(
                                        id="rs-upload-replace",
                                        children=html.Span(
                                            "Replace", className="rs-upload-replace"
                                        ),
                                        className="rs-upload-replace-wrap",
                                        multiple=False,
                                    ),
                                    id="rs-upload-replace-wrap",
                                    hidden=True,
                                ),
                            ],
                            className="rs-upload-status-row",
                        ),
                    ]
                ),
            ],
            className="mb-3 rs-section-card",
        ),
        html.Div(
            [
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.Div(
                            [
                                html.Span("2. Scored roles"),
                                html.Span("Next", className="rs-next-badge"),
                            ],
                            className="rs-card-header-title",
                        ),
                        html.Div(
                            [
                                html.Span("Scoring weights", className="rs-weights-label"),
                                html.Div(
                                    dmc.Select(
                                        id="rs-config",
                                        data=rc.pack_options(),
                                        value=rc.active_pack_id(),
                                        clearable=False,
                                        searchable=False,
                                        size="sm",
                                    ),
                                    className="rs-config-dd",
                                    title=(
                                        "Scores use this file’s key / preferred / useful weights. "
                                        "Edit and Save a config on the Role configs page."
                                    ),
                                ),
                                dcc.Link(
                                    "Edit",
                                    href="/role-config",
                                    className="rs-weights-edit",
                                    title="Open the Role configs page to edit and save weights.",
                                ),
                                dcc.Interval(id="rs-config-tick", interval=2500),
                            ],
                            className="rs-weights-bar",
                        ),
                    ],
                    className="rs-card-header-row",
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
                                        dmc.Button(
                                            "Clear",
                                            id="rs-clear-roles",
                                            n_clicks=0,
                                            variant="subtle",
                                            size="xs",
                                            className="rs-chip ghost",
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
                                        dmc.MultiSelect(
                                            id="rs-roles",
                                            data=role_options(),
                                            value=[],
                                            placeholder="Choose scored roles",
                                            searchable=True,
                                            clearable=True,
                                            maxDropdownHeight=280,
                                            className="rs-primary-control",
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
                                _hybrid_roles_panel(),
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
        html.Div(id="rs-pos-bar"),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span("Squad depth", className="rs-depth-heading-label"),
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
                                                            # Default: OK band floor (scores below = Poor).
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
                                                ),
                                            ],
                                            className="rs-filter-toggles",
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
                                html.Div(
                                    dash_table.DataTable(
                            id="rs-table",
                            page_size=50,
                            sort_action="custom",
                            sort_mode="single",
                            sort_by=[],
                            sort_as_null=["-", ""],
                            row_selectable="multi",
                            selected_rows=[],
                            filter_action="none",
                            fill_width=True,
                            markdown_options={"html": True},
                            style_table={
                                "overflowX": "auto",
                                "borderRadius": "12px",
                                "width": "100%",
                                "minWidth": "100%",
                            },
                            css=[
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
                                        "display: block !important; flex-shrink: 0; "
                                        "overflow: visible;"
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
                            ],
                            style_cell={
                                "fontFamily": "Inter, Segoe UI, sans-serif",
                                "fontSize": "14px",
                                "padding": "10px 12px",
                                "whiteSpace": "nowrap",
                                "backgroundColor": "transparent",
                                "color": "var(--app-text)",
                                "border": "1px solid transparent",
                                "textAlign": "right",
                            },
                            style_cell_conditional=[
                                {
                                    "if": {"column_id": "Name"},
                                    "textAlign": "left",
                                    "cursor": "pointer",
                                    "color": "var(--app-accent)",
                                    "fontWeight": "600",
                                    "textDecoration": "underline",
                                    "textUnderlineOffset": "3px",
                                },
                                {
                                    "if": {"column_id": "Position"},
                                    "textAlign": "left",
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
                                    "if": {"column_id": "Club"},
                                    "textAlign": "left",
                                },
                                {
                                    "if": {"column_id": "Injury"},
                                    "textAlign": "left",
                                },
                            ],
                            style_header={
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
                            },
                            style_header_conditional=[
                                {
                                    "if": {"column_id": col},
                                    "textAlign": "left",
                                }
                                for col in ("Name", "Position", "Club", "Injury")
                            ],
                            style_data_conditional=[
                                {
                                    "if": {"filter_query": '{Injury} != "-"'},
                                    "backgroundColor": "#fff3cd",
                                }
                            ],
                        ),
                                    id="rs-table-shell",
                                    className="rs-table-shell",
                                ),
                            ],
                            className="rs-table-area",
                        ),
                        html.Div(id="rs-table-layout-nudge", hidden=True),
                        html.Div(
                            [
                                html.Div(id="rs-table-caption", className="text-muted"),
                                html.Div(
                                    [
                                        html.Label("Rows per page", className="rs-field-label"),
                                        dmc.Select(
                                            id="rs-page-size",
                                            data=[
                                                {"label": "25", "value": "25"},
                                                {"label": "50", "value": "50"},
                                                {"label": "100", "value": "100"},
                                            ],
                                            value="50",
                                            clearable=False,
                                            searchable=False,
                                        ),
                                    ],
                                    className="rs-table-page-size",
                                ),
                                dmc.Button(
                                    "Clear marked rows",
                                    id="rs-squad-clear-btn",
                                    size="sm",
                                    variant="light",
                                    disabled=True,
                                    className="rs-squad-clear-btn",
                                ),
                            ],
                            className="rs-table-caption-row mt-2",
                        ),
                        html.Div(
                            [
                                dmc.Button(
                                    "Show score distribution",
                                    id="rs-hist-toggle",
                                    n_clicks=0,
                                    variant="light",
                                    className="rs-hist-toggle",
                                    buttonProps={
                                        "title": (
                                            "Score band on the horizontal axis; player count on "
                                            "the vertical axis. One series per displayed role."
                                        ),
                                    },
                                ),
                                html.Div(
                                    [
                                        dcc.Graph(
                                            id="rs-hist",
                                            figure=BLANK_FIG,
                                            config={"displayModeBar": False},
                                            responsive=True,
                                            style={"width": "100%", "height": "240px"},
                                        ),
                                    ],
                                    id="rs-hist-wrap",
                                    className="rs-hist-wrap",
                                    hidden=True,
                                ),
                            ],
                            className="rs-hist-block",
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
                        dmc.Button(
                            "Download Cursor canvas (.tsx)",
                            id="rs-canvas-btn",
                            variant="light",
                            className="me-2",
                            buttonProps={
                                "title": (
                                    "Opens beside chat in Cursor. Save to your workspace canvases "
                                    "folder, or open the file directly."
                                ),
                            },
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


def _decode_upload(contents: str) -> str:
    _header, _, payload = contents.partition(",")
    raw = base64.b64decode(payload)
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _labels(role_ids: list[str]) -> list[str]:
    return [role_meta(role_id)["column"] for role_id in role_ids]


def _as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _cell_number(value) -> float:
    if value in (None, "", "-"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


TABLE_TEXT_COLS = {"Name", "Age", "Height", "Position", "Feet", "Club", "Rec", "Injury"}
TABLE_MARKDOWN_COLS = {"Feet"}
_REC_SUFFIX = {"+": 0, "": 1, "-": 2}
_REC_PATTERN = re.compile(r"^([A-Za-z])\s*([+-])?$")

# Dark red (very weak) → bright green (very strong)
FOOT_STRENGTH_COLORS = {
    FootStrength.VERY_WEAK: "#7f1d1d",
    FootStrength.WEAK: "#dc2626",
    FootStrength.REASONABLE: "#f59e0b",
    FootStrength.FAIRLY_STRONG: "#a3e635",
    FootStrength.STRONG: "#22c55e",
    FootStrength.VERY_STRONG: "#4ade80",
}
_FOOT_UNKNOWN = "#64748b"


def _foot_color(level: FootStrength | None) -> str:
    if level is None:
        return _FOOT_UNKNOWN
    return FOOT_STRENGTH_COLORS.get(level, _FOOT_UNKNOWN)


def _footprint_svg(side: str, color: str, label: str) -> str:
    """Inline SVG sole+toes; `side` is L or R (R is mirrored inside a group)."""
    # Mirror via inner <g> so the SVG layout box stays 16×24 (root transform
    # shifts paint without updating the box, which breaks cell centering).
    open_g = '<g transform="translate(24 0) scale(-1 1)">' if side == "R" else ""
    close_g = "</g>" if side == "R" else ""
    return (
        f'<svg class="rs-foot-icon" viewBox="0 0 24 36" width="16" height="24" '
        f'aria-label="{label}" role="img">'
        f'<title>{label}</title>'
        f"{open_g}"
        # Heel / sole
        f'<ellipse cx="12" cy="23" rx="7.2" ry="10.5" fill="{color}"/>'
        # Toes (big toe on the inner side before mirror)
        f'<ellipse cx="6.2" cy="8.2" rx="2.1" ry="3.2" fill="{color}"/>'
        f'<ellipse cx="10.2" cy="6.4" rx="1.9" ry="3.0" fill="{color}"/>'
        f'<ellipse cx="14.0" cy="6.2" rx="1.8" ry="2.9" fill="{color}"/>'
        f'<ellipse cx="17.4" cy="7.4" rx="1.6" ry="2.6" fill="{color}"/>'
        f'<ellipse cx="19.8" cy="10.0" rx="1.35" ry="2.2" fill="{color}"/>'
        f"{close_g}"
        f"</svg>"
    )


def _feet_cell(row: dict) -> str:
    left = foot_strength(row.get("Left Foot") or "")
    right = foot_strength(row.get("Right Foot") or "")
    left_label = FOOT_STRENGTH_NAMES.get(left, "Unknown") if left else "Unknown"
    right_label = FOOT_STRENGTH_NAMES.get(right, "Unknown") if right else "Unknown"
    tip = f"L: {left_label} · R: {right_label}"
    # Full-width centered wrapper: Dash markdown nests <p> tags that break
    # parent flex centering, so use text-align + inline-flex instead.
    return (
        f'<div class="rs-feet-cell" title="{tip}">'
        f'<span class="rs-feet">'
        f'{_footprint_svg("L", _foot_color(left), f"Left foot: {left_label}")}'
        f'{_footprint_svg("R", _foot_color(right), f"Right foot: {right_label}")}'
        f"</span></div>"
    )


def _feet_sort_key(row: dict) -> tuple:
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


def _column_sort_key(column_id: str, value, row: dict | None = None):
    if column_id == "Feet" and row is not None:
        return _feet_sort_key(row)
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
_HEADER_LEFT_COLS = ("Name", "Position", "Club", "Injury")
_COLUMN_TONE_BY_ID: dict[str, str] | None = None


def _strip_phase_suffix(label: str) -> str:
    """Drop -IP / -OOP / -GK from a display label (data id stays unchanged)."""
    for suffix in _PHASE_DISPLAY_SUFFIXES:
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _column_display_name(col_id: str) -> str:
    """Short headers: CF not CF-IP; hybrids wrap as CF+\\nCM."""
    if col_id in TABLE_TEXT_COLS:
        return col_id
    if _is_hybrid_column(col_id):
        ip, _, oop = col_id.partition("+")
        if not ip or not oop:
            return col_id
        return f"{_strip_phase_suffix(ip)}+\n{_strip_phase_suffix(oop)}"
    return _strip_phase_suffix(col_id)


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
        if col in TABLE_MARKDOWN_COLS:
            spec["presentation"] = "markdown"
        elif col not in TABLE_TEXT_COLS:
            spec["type"] = "numeric"
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
                    "minWidth": "64px",
                    "width": "68px",
                    "maxWidth": "80px",
                    "paddingLeft": "6px",
                    "paddingRight": "6px",
                    "whiteSpace": "pre-line",
                }
            )
        else:
            # Short codes (CF, WB) and 2–3 digit scores — keep readable + sortable.
            rules.append(
                {
                    "if": {"column_id": label},
                    "textAlign": "center",
                    "minWidth": "58px",
                    "width": "62px",
                    "maxWidth": "76px",
                    "paddingLeft": "6px",
                    "paddingRight": "6px",
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
            }
        )
    return rules


def _column_signature(columns: list[dict]) -> str:
    return "|".join(str(col.get("id") or "") for col in columns)


def _table_style_table(_row_count: int = 0, _page_size: int = 50) -> dict:
    return {
        "overflowX": "auto",
        "borderRadius": "12px",
        "width": "100%",
        "minWidth": "100%",
    }


def _table_page_state(columns: list[dict], prev_sig: str | None) -> tuple[int | object, str]:
    sig = _column_signature(columns)
    if sig != (prev_sig or ""):
        return 0, sig
    return no_update, sig


def _clicked(n_clicks) -> bool:
    return bool(n_clicks) and any(n_clicks)


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
    dark = _is_dark(theme)
    zebra = "rgba(255,255,255,0.03)" if dark else "rgba(0,0,0,0.025)"
    selected_bg = "rgba(61, 255, 136, 0.14)" if dark else "rgba(34, 139, 87, 0.12)"
    eligible = "#3dff88" if dark else "#15803d"
    partial = "#fbbf24" if dark else "#a16207"
    ineligible = "#fb7185" if dark else "#be123c"
    # Brighter than muted so Age / Height / Club stay readable.
    plain = "#f1f5f9" if dark else "#0f172a"
    rules = [
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
        },
        {
            "if": {"column_id": "Club"},
            "color": plain,
            "maxWidth": "200px",
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
            "minWidth": "52px",
            "width": "56px",
            "maxWidth": "64px",
        },
        {
            "if": {"column_id": "Age"},
            "color": plain,
            "textAlign": "center",
            "minWidth": "52px",
            "width": "56px",
            "maxWidth": "64px",
        },
        {
            "if": {"column_id": "Height"},
            "color": plain,
            "textAlign": "center",
            "minWidth": "68px",
            "width": "72px",
            "maxWidth": "84px",
        },
        {
            "if": {"column_id": "Injury", "filter_query": '{Injury} != "-"'},
            "color": "#fbbf24" if dark else "#b45309",
            "fontWeight": "600",
        },
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
    rules.extend(_rec_highlight_styles(theme))
    return rules


def _rec_grades() -> list[str]:
    grades = [f"{letter}{suffix}" for letter in "ABCDE" for suffix in ("+", "", "-")]
    grades.append("F")
    return grades


def _lerp_channel(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _rec_highlight_styles(theme: str | None = None) -> list[dict]:
    """Color Rec from green (A+) to red (F)."""
    dark = _is_dark(theme)
    # Dark: bright fg on soft tinted bg. Light: deep fg on soft tinted bg.
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


def _score_styles(role_labels: list[str], settings=None, theme: str | None = None) -> list[dict]:
    settings = us.normalize(settings)
    bands = settings["bands"]
    colors = us.score_colors(settings)
    elite, good, ok = bands["elite"], bands["good"], bands["ok"]
    injury = "rgba(251, 191, 36, 0.18)" if _is_dark(theme) else "#fff3cd"
    rules = _table_base_styles(theme)
    rules.append(
        {
            "if": {"filter_query": '{Injury} != "-"'},
            "backgroundColor": injury,
        }
    )
    for label in role_labels:
        rules.extend(
            [
                {
                    "if": {"filter_query": f"{{{label}}} >= {elite}", "column_id": label},
                    "backgroundColor": colors["elite"][0],
                    "color": colors["elite"][1],
                    "fontWeight": "700",
                    "borderRadius": "6px",
                    "fontVariantNumeric": "tabular-nums",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= {good} && {{{label}}} < {elite}",
                        "column_id": label,
                    },
                    "backgroundColor": colors["good"][0],
                    "color": colors["good"][1],
                    "fontWeight": "700",
                    "fontVariantNumeric": "tabular-nums",
                },
                {
                    "if": {
                        "filter_query": f"{{{label}}} >= {ok} && {{{label}}} < {good}",
                        "column_id": label,
                    },
                    "backgroundColor": colors["ok"][0],
                    "color": colors["ok"][1],
                    "fontWeight": "700",
                    "fontVariantNumeric": "tabular-nums",
                },
                {
                    "if": {"filter_query": f"{{{label}}} < {ok}", "column_id": label},
                    "backgroundColor": colors["poor"][0],
                    "color": colors["poor"][1],
                    "fontWeight": "700",
                    "fontVariantNumeric": "tabular-nums",
                },
            ]
        )
    rules.extend(_score_column_styles(role_labels))
    return rules


def _pos_bar(rows: list[dict], active: str, foot: str, foot_thresholds=None) -> html.Div:
    counts = {"all": len(rows)}
    for key, _name, _code, _css in POS_CARDS[1:]:
        counts[key] = sum(1 for row in rows if key in (row.get("PosGroups") or []))
    cards = []
    for key, name, code, css in POS_CARDS:
        count = counts.get(key, 0)
        class_name = f"rs-pos-card {css}" + (" active" if active == key else "")
        children = [html.Span(name, className="rs-pos-name")]
        if code:
            children.append(html.Span(code, className="rs-pos-code"))
        children.append(html.Span(str(count), className="rs-pos-count"))
        cards.append(
            html.Button(
                children,
                id={"type": "rs-pos", "pos": key},
                n_clicks=0,
                className=class_name,
            )
        )
    hints = foot_filter_hints(foot_thresholds)
    foot_btns = []
    for key, label in (("foot-L", "Left Foot"), ("foot-B", "Both Feet"), ("foot-R", "Right Foot")):
        foot_btns.append(
            html.Button(
                label,
                id={"type": "rs-foot", "foot": key},
                n_clicks=0,
                title=hints.get(key, ""),
                className="rs-foot-btn" + (" active" if foot == key else ""),
            )
        )
    return html.Div(
        [
            html.Div(cards, className="rs-pos-cards"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Footedness"),
                            *_help_icon(foot_filter_help(foot_thresholds), "rs-help-footedness"),
                        ],
                        className="rs-foot-label",
                    ),
                    html.Div(foot_btns, className="rs-foot-btns"),
                ],
                className="rs-pos-utils",
            ),
        ],
        className="rs-pos-bar",
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
    if active:
        children.insert(0, html.Span("Focused", className="rs-depth-focus-badge"))
    return html.Button(
        children,
        id={"type": "rs-depth", "role": meta["id"]},
        n_clicks=0,
        className="rs-depth-card" + active,
        title=meta.get("compact") or meta["name"],
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
    Output("rs-parsed", "data"),
    Output("rs-upload-status", "children"),
    Output("rs-upload-wrap", "hidden"),
    Output("rs-upload-replace-wrap", "hidden"),
    Input("rs-upload", "contents"),
    Input("rs-upload-replace", "contents"),
    State("rs-upload", "filename"),
    State("rs-upload-replace", "filename"),
    prevent_initial_call=True,
)
def parse_uploaded(upload_contents, replace_contents, upload_name, replace_name):
    # Prefer the control that fired — initial upload contents stay set after Replace.
    if ctx.triggered_id == "rs-upload-replace":
        contents = replace_contents
        name = replace_name or "upload.csv"
    elif ctx.triggered_id == "rs-upload":
        contents = upload_contents
        name = upload_name or "upload.csv"
    else:
        contents = replace_contents or upload_contents
        name = (replace_name or upload_name) or "upload.csv"
    if not contents:
        return no_update, no_update, no_update, no_update
    if not name.lower().endswith(".csv"):
        return (
            None,
            _upload_error("Upload the CSV from FM Player Export, not the HTML file."),
            False,
            True,
        )
    try:
        players = parse_export(_decode_upload(contents))
    except ValueError as exc:
        return None, _upload_error(str(exc)), False, True
    return (
        {"filename": name, "players": players},
        _upload_status_bar(len(players), name),
        True,
        False,
    )


@callback(
    Output("rs-upload-status", "children", allow_duplicate=True),
    Output("rs-upload-wrap", "hidden", allow_duplicate=True),
    Output("rs-upload-replace-wrap", "hidden", allow_duplicate=True),
    Input("rs-parsed", "data"),
    prevent_initial_call="initial_duplicate",
)
def restore_upload_ui(parsed):
    """Re-show upload status when session-stored CSV survives page navigation."""
    if not parsed or not parsed.get("players"):
        return no_update, no_update, no_update
    filename = parsed.get("filename") or "export.csv"
    return (
        _upload_status_bar(len(parsed["players"]), filename),
        True,
        False,
    )


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
    hydrated,
):
    if not hydrated:
        return no_update
    return {
        "roles": _as_list(roles),
        "combos": normalize_combos(combos),
        "formation": formation or None,
        "role_mode": role_mode or "formations",
        "set_pieces": _as_list(set_pieces),
        "hybrids_only": bool(hybrids_only),
        "pos_match": _normalize_pos_match(pos_match),
        "focus_role": _as_list(focus_role),
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
    Input("rs-persist-boot", "data"),
    State("rs-hydrated", "data"),
    State("rs-phase", "data"),
    State("rs-group", "data"),
    prevent_initial_call=True,
)
def hydrate_page_persist(persist, hydrated, phase, group):
    if hydrated or persist is None:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )
    persist = {**PERSIST_DEFAULTS, **(persist or {})}
    roles = _as_list(persist.get("roles"))
    combos = normalize_combos(persist.get("combos"))
    mode = persist.get("role_mode") or "formations"
    formation = persist.get("formation") or None
    set_pieces = _as_list(persist.get("set_pieces"))
    # Prefer pos_match; fall back to legacy eligible bool.
    if "pos_match" in persist:
        pos_match = _normalize_pos_match(persist.get("pos_match"))
    else:
        pos_match = _normalize_pos_match(persist.get("eligible", True))
    hybrids_only = bool(persist.get("hybrids_only", False))
    focus = _as_list(persist.get("focus_role"))
    keep = list(roles)
    for item in combos:
        keep.extend((item["ip"], item["oop"]))
    options = role_options(phase=phase, group=group, keep=keep) or []
    has_state = bool(
        roles
        or combos
        or formation
        or set_pieces
        or focus
        or hybrids_only
        or pos_match != "yes"
        or mode != "formations"
    )
    if not has_state:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            True,
            mode,
            no_update,
        )
    return (
        roles,
        options,
        combos,
        mode,
        formation,
        set_pieces,
        pos_match,
        hybrids_only,
        focus,
        True,
        mode,
        _sort_by_focus(focus),
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
    Output("rs-hist-open", "data"),
    Output("rs-hist-wrap", "hidden"),
    Output("rs-hist-toggle", "children"),
    Input("rs-hist-toggle", "n_clicks"),
    State("rs-hist-open", "data"),
    prevent_initial_call=True,
)
def toggle_score_distribution(_clicks, opened):
    opened = not bool(opened)
    return (
        opened,
        not opened,
        "Hide score distribution" if opened else "Show score distribution",
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
)
def render_combo_pills(combos):
    return _combo_pills(combos)


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
    Output("rs-combos", "data", allow_duplicate=True),
    Input("rs-clear-roles", "n_clicks"),
    prevent_initial_call=True,
)
def clear_roles(_clear):
    if not ctx.triggered_id:
        return no_update, no_update
    return [], []


@callback(
    Output("rs-pos-filter", "data"),
    Input({"type": "rs-pos", "pos": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_pos_filter(n_clicks):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    pos = ctx.triggered_id["pos"]
    if pos == "_":
        return no_update
    return pos


@callback(
    Output("rs-foot-filter", "data"),
    Input({"type": "rs-foot", "foot": ALL}, "n_clicks"),
    State("rs-foot-filter", "data"),
    prevent_initial_call=True,
)
def set_foot_filter(n_clicks, current):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    chosen = ctx.triggered_id["foot"]
    if chosen == "_":
        return no_update
    return "" if current == chosen else chosen


@callback(
    Output("rs-age", "data"),
    Output("rs-age", "value"),
    Output("rs-band-legend", "children"),
    Input("ui-settings", "data"),
    State("rs-age", "value"),
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
    # Hydrate restores formation + combos together; skip resetting focus.
    if normalize_combos(current_combos) == normalize_combos(combos):
        return no_update, no_update, options, "formations", no_update, no_update
    first = _first_combo_column(combos)
    focus = [first] if first else []
    return combos, [], options, "formations", focus, _sort_by_focus(focus)


@callback(
    Output("rs-rows", "data"),
    Output("rs-focus-role", "data"),
    Output("rs-table", "sort_by", allow_duplicate=True),
    Input("rs-parsed", "data"),
    Input("rs-roles", "value"),
    Input("rs-combos", "data"),
    Input("rs-config", "value"),
    State("rs-focus-role", "data"),
    prevent_initial_call="initial_duplicate",
)
def rescore(parsed, role_ids, combos, pack_id, current_focus):
    if pack_id:
        rc.load_pack(pack_id)
    if not parsed or not parsed.get("players"):
        return None, no_update, no_update
    combos = normalize_combos(combos)
    role_ids = _as_list(role_ids)
    needed = list(role_ids)
    for item in combos:
        for role_id in (item["ip"], item["oop"]):
            if role_id not in needed:
                needed.append(role_id)
    if not needed:
        return None, no_update, no_update
    rows = apply_combos(score_players(parsed["players"], needed), combos)
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
    Output("rs-table", "style_data_conditional"),
    Output("rs-table", "style_header_conditional"),
    Output("rs-table", "style_table"),
    Output("rs-table", "page_size"),
    Output("rs-table", "page_current"),
    Output("rs-table", "selected_rows"),
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
    cols_sig,
):
    settings = us.normalize(settings)
    bands = settings["bands"]
    foot_thresholds = settings["foot_thresholds"]
    bins = us.hist_bins(settings)
    empty_cols = [{"name": "Name", "id": "Name"}]
    empty_style = _score_styles([], settings, theme)
    empty_header = _score_header_styles([], theme)
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
            empty_style,
            empty_header,
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
            empty_style,
            empty_header,
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

    piece_cols = set_piece_columns(set_pieces)
    chosen = set(chosen_pieces)
    score_cols = [
        profile["score"]
        for profile in SET_PIECE_PROFILES
        if profile["id"] in chosen and profile.get("score")
    ] + table_role_cols
    table_cols = ["Name", "Age", "Height", "Position", "Feet", "Club", "Rec", "Injury"]
    table_cols.extend(piece_cols)
    table_cols.extend(table_role_cols)
    columns = _table_columns(table_cols)
    table_rows = []
    for row in filtered:
        item = {
            key: (_feet_cell(row) if key == "Feet" else row.get(key, "-"))
            for key in table_cols
        }
        item["PosEligible"] = row.get("_PosEligible") or "no"
        table_rows.append(item)
    page_keys = [player_row_key(row) for row in table_rows]
    selected_rows = [i for i, key in enumerate(page_keys) if key in marked_keys]
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
    # Focus/sort clicks should not rebuild the position bar (same counts).
    triggered_props = {item.get("prop_id", "") for item in (ctx.triggered or [])}
    focus_sort_only = bool(triggered_props) and triggered_props.issubset(
        {"rs-focus-role.data", "rs-table.sort_by"}
    )
    pos_bar = (
        no_update
        if focus_sort_only
        else _pos_bar(rows, pos_filter, foot_filter, foot_thresholds)
    )
    return (
        pos_bar,
        cards,
        not cards,
        table_rows,
        columns,
        _score_styles(score_cols, settings, theme),
        _score_header_styles(score_cols, theme),
        _table_style_table(len(table_rows), page_size),
        page_size,
        page_current,
        selected_rows,
        new_sig,
        fig,
        caption,
        empty_panel,
        not no_matches,
        no_matches,
    )


clientside_callback(
    """
    function(_data, _columns, _sig) {
        requestAnimationFrame(function() {
            window.dispatchEvent(new Event("resize"));
        });
        return "";
    }
    """,
    Output("rs-table-layout-nudge", "children"),
    Input("rs-table", "data"),
    Input("rs-table", "columns"),
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
    Output("rs-squad-marked", "data", allow_duplicate=True),
    Input("rs-squad-clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_squad_marks(n_clicks):
    if not n_clicks:
        return no_update
    return []


@callback(
    Output("rs-squad-marked", "data", allow_duplicate=True),
    Input("rs-table", "selected_rows"),
    State("rs-table", "data"),
    State("rs-squad-marked", "data"),
    prevent_initial_call=True,
)
def sync_squad_marks(selected_rows, table_data, marked):
    table_data = table_data or []
    marked_set = set(_as_list(marked))
    keys_on_page = [player_row_key(row) for row in table_data]
    expected = {i for i, key in enumerate(keys_on_page) if key in marked_set}
    actual = set(selected_rows or [])
    if actual == expected:
        return no_update
    marked_set -= set(keys_on_page)
    for index in selected_rows or []:
        if 0 <= index < len(keys_on_page):
            key = keys_on_page[index]
            if key:
                marked_set.add(key)
    return sorted(marked_set)


@callback(
    Output("rs-squad-marked", "data", allow_duplicate=True),
    Input("rs-parsed", "data"),
    prevent_initial_call=True,
)
def clear_squad_marks_on_upload(_parsed):
    return []


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
    combos = normalize_combos((payload or {}).get("combos"))
    hybrids_only = bool(hybrids_only)
    view_roles = _hybrid_only_roles(
        _resolved_view_roles(payload, focus_role), combos, hybrids_only
    )
    export_rows = []
    if payload and view_roles and _as_list(marked):
        export_rows = planned_squad_export_rows(
            payload.get("rows") or [],
            _as_list(marked),
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


@callback(
    Output("rs-download-canvas", "data"),
    Input("rs-canvas-btn", "n_clicks"),
    State("rs-rows", "data"),
    State("rs-focus-role", "data"),
    State("ui-settings", "data"),
    State("rs-hybrids-only", "checked"),
    prevent_initial_call=True,
)
def download_canvas(n_clicks, payload, focus_role, settings, hybrids_only):
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
    text = build_canvas(
        payload["rows"],
        role_labels,
        payload.get("filename") or "FM export",
        settings,
    )
    return dict(content=text, filename="fm26-role-scores.canvas.tsx")
