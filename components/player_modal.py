"""Shared player detail modal: identity, exclusive detail filter, personality, shell.

Page-specific content (attribute grid, stats charts) is passed as `bottom`
and optional `after_identity` children. Detail categories (international,
contract, career, season, discipline) are behind a one-at-a-time filter;
personality, archetypes, and page content always stay visible below.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc
from dash_iconify import DashIconify

from scoring.personality_ranges import attr_help, estimate_hidden_ranges, range_color
from scoring.personality_tiers import (
    classify_personality,
    personality_tier_style,
    tier_description,
    tier_label,
)
from scoring.player_archetypes import (
    archetype_pos_group_options,
    evaluate_archetypes,
    resolve_archetype_pos_group,
)
import services.ui_settings as us

# FM26 Moneyball export: star ratings are unreliable — never show in the UI.
STAR_ATTRIBUTES_BROKEN = frozenset({"ability", "potential", "world_reputation"})

# Optional identity fields hidden by default (personality section covers personality/media).
PLAYER_IDENTITY_HIDDEN = frozenset(
    {
        "personality",
        "media_handling",
    }
)

MODAL_EXTRA_FIELD_DEFS = (
    ("Personality", "personality"),
    ("Media handling", "media_handling"),
    ("Based in", "based_in"),
    ("Home grown", "home_grown_status"),
    ("Picked", "picked"),
    ("Position/role", "position_role"),
)

CAREER_MODAL_FIELDS = (
    ("Career apps", "at_apps"),
    ("Career goals", "at_gls"),
    ("League apps", "at_league_apps"),
    ("League goals", "at_league_goals"),
)

PLAYING_TIME_MODAL_FIELDS = (
    ("Appearances", "appearances"),
    ("Minutes", "minutes"),
    ("Avg rating", "avg_rating_club"),
    ("Last 5", "last_5_club"),
)

DISCIPLINE_MODAL_FIELDS = (
    ("Yellow cards", "yellow_cards"),
    ("Red cards", "red_cards"),
    ("Fouls made", "fouls_made"),
    ("Fouls against", "fouls_against"),
)

# Row 1 = transfer / fee-related; row 2 = contract wages & clauses.
# Empty values are omitted at render time (same as other modal sections).
FINANCE_MODAL_ROWS = (
    [
        ("Transfer value", "transfer_value"),
        ("Transfer status", "transfer_status"),
        ("Loan status", "loan_status"),
        ("Release clause", "min_release_clause"),
        ("Work permit", "work_permit_required"),
        ("WP needed", "wp_needed"),
    ],
    [
        ("Salary", "salary"),
        ("Contract expires", "contract_expires"),
        ("FFP contribution", "ffp_contribution"),
        ("Appearance fee", "appearance_fee"),
        ("Unused sub fee", "unused_sub_fee"),
        ("Goal bonus", "goal_bonus"),
        ("Assist bonus", "assist_bonus"),
        ("Shutout bonus", "shutout_bonus"),
        ("Int cap bonus", "int_cap_bonus"),
        ("Yearly raise", "yearly_salary_raise"),
        ("Promotion raise", "promotion_salary_raise"),
        ("Top-tier promotion raise", "top_division_promotion_salary_raise"),
        ("Relegation drop", "relegation_salary_drop"),
        ("Top-tier relegation drop", "top_division_relegation_salary_drop"),
    ],
)

FINANCE_MODAL_FIELDS = tuple(
    field for row in FINANCE_MODAL_ROWS for field in row
)

_CLAUSE_RAW_KEYS = {
    "yearly_salary_raise": "yearly_salary_raise_raw",
    "promotion_salary_raise": "promotion_salary_raise_raw",
    "top_division_promotion_salary_raise": "top_division_promotion_salary_raise_raw",
    "relegation_salary_drop": "relegation_salary_drop_raw",
    "top_division_relegation_salary_drop": "top_division_relegation_salary_drop_raw",
}

PLAYER_IDENTITY_SECTIONS = [
    (
        None,
        [
            [
                ("Age", "age"),
                ("Club", "club"),
                ("Division", "division"),
                ("Height", "height"),
                ("Left foot", "left_foot"),
                ("Right foot", "right_foot"),
                ("Rec", "rec"),
                ("Inf", "inf"),
                ("Injury", "injury"),
                ("Recurring injury", "recurring_injury"),
            ],
            [
                ("Position", "position"),
                ("Best pos", "best_pos"),
                ("Best role", "best_role"),
                ("Style", "style"),
            ],
        ],
    ),
    (
        "International & youth",
        [
            [
                ("Nationality", "nation"),
                ("Second nationality", "second_nation"),
                ("National team", "national_team"),
            ],
            [
                ("Int apps", "int_apps"),
                ("Int goals", "int_gls"),
                ("Int assists", "int_assists"),
                ("Int goals conceded", "int_goals_conceded"),
                ("Youth apps", "yth_apps"),
                ("Youth goals", "yth_gls"),
            ],
            [
                ("Int apps (season)", "int_apps_season"),
                ("Int rating", "avg_rating_int"),
                ("Last 5 int", "last_5_int"),
            ],
            [
                ("Int form", "form_int"),
            ],
        ],
    ),
]

_POS_ELIG_TIPS = {
    "yes": "Eligible for every focused / viewed role (hybrids need both parts)",
    "partial": "Only matches some of the focused / viewed roles (or one hybrid part)",
    "no": "Not eligible for the focused / viewed role(s)",
}

FieldFormatter = Callable[[object], str]


def identity_value_present(value) -> bool:
    text = str(value if value is not None else "").strip()
    return text not in ("", "-")


def iter_modal_field_defs() -> list[tuple[str, str, str]]:
    """All configurable modal fields as (label, key, section)."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for title, rows in PLAYER_IDENTITY_SECTIONS:
        section = "international" if title else "identity"
        for row in rows:
            for label, key in row:
                if key not in seen:
                    out.append((label, key, section))
                    seen.add(key)
    for label, key in MODAL_EXTRA_FIELD_DEFS:
        if key not in seen and key not in STAR_ATTRIBUTES_BROKEN:
            out.append((label, key, "identity"))
            seen.add(key)
    for label, key in FINANCE_MODAL_FIELDS:
        if key not in seen:
            out.append((label, key, "finance"))
            seen.add(key)
    return out


def _identity_section_rows(title: str | None) -> list[list[str]]:
    """Field keys per visual row for a section title (None = main identity block)."""
    for section_title, rows in PLAYER_IDENTITY_SECTIONS:
        if section_title == title:
            return [[key for _label, key in row] for row in rows]
    return []


def _identity_row_items(
    keys: Sequence[str],
    field_map: Mapping[str, str],
    player: dict,
    *,
    position_eligible: str | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> list:
    items = []
    for key in keys:
        label = field_map.get(key)
        if not label:
            continue
        item = player_identity_item(
            label,
            key,
            player,
            position_eligible=position_eligible,
            field_styles=field_styles,
            field_formatters=field_formatters,
            theme=theme,
            limited_divisions=limited_divisions,
        )
        if item is not None:
            items.append(item)
    return items


def player_identity_sections(
    player: dict,
    *,
    position_eligible: str | None = None,
    fields: Sequence[tuple[str, str, str]] | None = None,
    extra_identity_fields: Sequence[tuple[str, str]] | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    include_sections: Sequence[str] | None = None,
) -> list:
    """Build identity and/or international section nodes (no personality).

    ``include_sections`` defaults to both ``identity`` and ``international``.
    """
    wanted = set(include_sections) if include_sections is not None else {
        "identity",
        "international",
    }
    configured = [
        (label, key, section)
        for label, key, section in (fields or [])
        if key not in STAR_ATTRIBUTES_BROKEN and section in wanted
    ]
    if extra_identity_fields and "identity" in wanted:
        configured.extend(
            (label, key, "identity")
            for label, key in extra_identity_fields
            if key not in STAR_ATTRIBUTES_BROKEN
        )
    if not configured:
        return []

    by_section: dict[str | None, list[tuple[str, str]]] = {}
    section_titles = {"identity": None, "international": "International & youth"}
    for label, key, section in configured:
        title = section_titles.get(section, section)
        by_section.setdefault(title, []).append((label, key))

    sections = []
    title_order = []
    if "identity" in wanted:
        title_order.append(None)
    if "international" in wanted:
        title_order.append("International & youth")
    for title in title_order:
        if title not in by_section:
            continue
        field_map = {key: label for label, key in by_section[title]}
        row_nodes: list = []
        placed: set[str] = set()
        for keys_in_row in _identity_section_rows(title):
            items = _identity_row_items(
                keys_in_row,
                field_map,
                player,
                position_eligible=position_eligible,
                field_styles=field_styles,
                field_formatters=field_formatters,
                theme=theme,
                limited_divisions=limited_divisions,
            )
            if items:
                row_nodes.append(html.Div(items, className="rs-player-identity"))
            placed.update(keys_in_row)

        leftover_keys = [key for _label, key in by_section[title] if key not in placed]
        if leftover_keys:
            items = _identity_row_items(
                leftover_keys,
                field_map,
                player,
                position_eligible=position_eligible,
                field_styles=field_styles,
                field_formatters=field_formatters,
                theme=theme,
                limited_divisions=limited_divisions,
            )
            if items:
                row_nodes.append(html.Div(items, className="rs-player-identity"))

        if not row_nodes:
            continue
        if title:
            sections.append(
                html.Div(
                    [
                        html.Div(title, className="rs-player-id-section-title"),
                        *row_nodes,
                    ],
                    className="rs-player-id-section",
                )
            )
        else:
            sections.append(
                html.Div(row_nodes, className="rs-player-identity-block")
            )
    return sections


# Exclusive modal detail categories (shown one-at-a-time via the section filter).
# Default (nothing selected): personality + archetypes + page content.
MODAL_EXTRA_SECTION_DEFS: tuple[tuple[str, str], ...] = (
    ("international", "International"),
    ("finance", "Contract & finance"),
    ("career", "Career totals"),
    ("season", "Season stats"),
    ("discipline", "Discipline"),
)


def player_international_section(
    player: dict,
    *,
    fields: Sequence[tuple[str, str, str]] | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    **_kwargs,
) -> html.Div | None:
    """International & youth block for the modal section filter."""
    nodes = player_identity_sections(
        player,
        fields=fields,
        field_styles=field_styles,
        field_formatters=field_formatters,
        theme=theme,
        limited_divisions=limited_divisions,
        include_sections=("international",),
    )
    if not nodes:
        return None
    if len(nodes) == 1:
        return nodes[0]
    return html.Div(nodes, className="rs-player-id-section")


def _modal_extra_section_nodes(
    player: dict,
    *,
    modal_fields: Sequence[tuple[str, str, str]] | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    settings=None,
) -> list[tuple[str, str, html.Div]]:
    """Build available (key, button_label, node) rows for the exclusive filter."""
    kwargs = {
        "field_styles": field_styles,
        "field_formatters": field_formatters,
        "theme": theme,
        "limited_divisions": limited_divisions,
    }
    builders = {
        "international": lambda: player_international_section(
            player, fields=modal_fields, **kwargs
        ),
        "finance": lambda: player_finance_section(player, **kwargs),
        "career": lambda: player_career_section(player, **kwargs),
        "season": lambda: player_playing_time_section(
            player, settings=settings, **kwargs
        ),
        "discipline": lambda: player_discipline_section(player, **kwargs),
    }
    out: list[tuple[str, str, html.Div]] = []
    for key, label in MODAL_EXTRA_SECTION_DEFS:
        node = builders[key]()
        if node is not None:
            out.append((key, label, node))
    return out


def _modal_section_filter(
    *,
    id_prefix: str,
    options: Sequence[tuple[str, str]],
    active: str | None = None,
) -> html.Div:
    buttons = [
        html.Button(
            label,
            id={"type": f"{id_prefix}-modal-extra-btn", "section": key},
            n_clicks=0,
            type="button",
            className="st-player-seg-btn"
            + (" active" if key == active else ""),
        )
        for key, label in options
    ]
    return html.Div(
        [
            html.Span("Details", className="st-player-switch-label"),
            html.Div(
                buttons,
                id=f"{id_prefix}-modal-extra-btns",
                className="st-player-seg rs-modal-section-seg",
            ),
            dcc.Store(id=f"{id_prefix}-modal-extra-sel", data=active),
        ],
        className="rs-modal-section-filter",
    )


def _as_field_rows(
    field_defs: Sequence[tuple[str, str]] | Sequence[Sequence[tuple[str, str]]],
) -> list[Sequence[tuple[str, str]]]:
    """Normalize flat field defs or pre-grouped visual rows."""
    if not field_defs:
        return []
    first = field_defs[0]
    # Nested rows: ((label, key), …) / [(label, key), …]
    if isinstance(first, (list, tuple)) and first and isinstance(first[0], (list, tuple)):
        return list(field_defs)  # type: ignore[arg-type]
    return [field_defs]  # type: ignore[list-item]


def player_record_section(
    player: dict,
    title: str,
    field_defs: Sequence[tuple[str, str]] | Sequence[Sequence[tuple[str, str]]],
    *,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> html.Div | None:
    """Career totals, discipline, finance, etc. from the stats export.

    ``field_defs`` may be a flat list of (label, key) or a sequence of visual
    rows (each a list of fields), matching identity-section layout.
    """
    row_nodes: list = []
    for field_row in _as_field_rows(field_defs):
        items = [
            item
            for item in (
                player_identity_item(
                    label,
                    key,
                    player,
                    field_styles=field_styles,
                    field_formatters=field_formatters,
                    theme=theme,
                    limited_divisions=limited_divisions,
                )
                for label, key in field_row
            )
            if item is not None
        ]
        if items:
            row_nodes.append(html.Div(items, className="rs-player-identity"))
    if not row_nodes:
        return None
    return html.Div(
        [
            html.Div(title, className="rs-player-id-section-title"),
            *row_nodes,
        ],
        className="rs-player-id-section",
    )


def player_career_section(player: dict, **kwargs) -> html.Div | None:
    return player_record_section(player, "Career totals", CAREER_MODAL_FIELDS, **kwargs)


def _current_season_player(player: dict) -> dict:
    """Season stats always use newest-year apps/mins, ignoring the Year toggle."""
    if not isinstance(player, dict):
        return player
    by_year = player.get("by_year")
    if not isinstance(by_year, dict) or not by_year:
        return player
    try:
        from components.multi_year_ui import stats_player_for_pct_basis
    except Exception:
        return player
    overlay = stats_player_for_pct_basis(player, pct_basis="current")
    return overlay if isinstance(overlay, dict) else player


def player_playing_time_section(player: dict, **kwargs) -> html.Div | None:
    season_player = _current_season_player(player)
    settings = kwargs.pop("settings", None)
    # Identity minutes follow the Year toggle; recolor from current-season mins.
    if (
        season_player.get("minutes") != player.get("minutes")
        and kwargs.get("field_styles")
    ):
        try:
            from scoring.stats_scorer import minutes_color, minutes_status

            req = float(us.default_minutes_required(settings))
            styles = dict(kwargs["field_styles"])
            styles["minutes"] = {
                "color": minutes_color(
                    minutes_status(season_player.get("minutes"), req)
                )
            }
            kwargs = {**kwargs, "field_styles": styles}
        except Exception:
            pass
    return player_record_section(
        season_player,
        "Season stats",
        PLAYING_TIME_MODAL_FIELDS,
        **kwargs,
    )


def player_discipline_section(player: dict, **kwargs) -> html.Div | None:
    return player_record_section(player, "Discipline", DISCIPLINE_MODAL_FIELDS, **kwargs)


def player_finance_section(player: dict, **kwargs) -> html.Div | None:
    return player_record_section(player, "Contract & finance", FINANCE_MODAL_ROWS, **kwargs)


def player_identity_item(
    label: str,
    key: str,
    player: dict,
    *,
    position_eligible: str | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> html.Div | None:
    display_key = key
    raw_key = _CLAUSE_RAW_KEYS.get(key)
    if raw_key and identity_value_present(player.get(raw_key)):
        display_key = raw_key
    elif raw_key:
        # Resolved finance rows store $ amounts; skip empty clauses.
        try:
            if float(player.get(key) or 0) == 0:
                return None
        except (TypeError, ValueError):
            pass
    if not identity_value_present(player.get(display_key)):
        return None
    value_class = "rs-player-id-value"
    tip = None
    if key == "position" and position_eligible in _POS_ELIG_TIPS:
        value_class += {
            "yes": " is-eligible",
            "partial": " is-partial",
            "no": " is-ineligible",
        }[position_eligible]
        tip = _POS_ELIG_TIPS[position_eligible]
    raw = player.get(display_key)
    formatter = (field_formatters or {}).get(key)
    text = formatter(raw) if formatter else str(raw or "—")
    style = dict((field_styles or {}).get(key) or {})
    if key == "rec":
        from components.player_table import rec_identity_style

        rec_style = rec_identity_style(text, theme)
        if rec_style:
            value_class += " rs-identity-pill"
            style = {**rec_style, **style}
    if key in ("avg_rating_club", "avg_rating_int", "last_5_club", "last_5_int"):
        from components.player_table import avg_rating_identity_style

        rating_style = avg_rating_identity_style(raw, theme)
        if rating_style:
            value_class += " rs-identity-pill"
            style = {**rating_style, **style}
    if key == "division":
        from components.player_table import division_identity_style

        div_style = division_identity_style(
            player,
            theme=theme,
            limited_divisions=limited_divisions,
        )
        if div_style:
            value_class += " rs-identity-pill"
            style = {**div_style, **style}
    return html.Div(
        [
            html.Span(label, className="rs-player-id-label"),
            html.Span(
                text,
                className=value_class,
                title=tip,
                style=style or None,
            ),
        ],
        className="rs-player-id-item",
    )


def player_personality_section(
    player: dict,
    *,
    id_prefix: str = "rs",
    settings=None,
) -> html.Div | None:
    """Estimated hidden-attribute ranges from Personality + Media Handling."""
    attrs = player.get("attrs") or {}
    det = attrs.get("Det")
    estimate = estimate_hidden_ranges(
        player.get("personality"),
        player.get("media_handling"),
        determination=int(det) if det not in (None, "") else None,
    )
    if not estimate["matched"]:
        return None

    personality_name = estimate["personality"] or player.get("personality")
    media_name = estimate["media_handling"] or player.get("media_handling")
    tier = classify_personality(personality_name)
    colors = us.personality_tier_colors(settings)
    chip_style = personality_tier_style(tier, colors)

    subtitle_children: list = []
    if personality_name:
        chip_bits: list = [str(personality_name)]
        formal = tier_label(tier)
        desc = tier_description(tier)
        if formal:
            chip_bits.append(
                html.Span(formal, className="rs-personality-tier-label")
            )
        tip = " — ".join(part for part in (formal, desc) if part) or None
        subtitle_children.append(
            html.Span(
                chip_bits,
                className="rs-personality-name-chip",
                style=chip_style,
                title=tip,
            )
        )
    if media_name:
        subtitle_children.append(html.Span(str(media_name)))

    items = []
    for attr, info in estimate["hidden"].items():
        tip_bits = []
        if info.get("from_personality"):
            tip_bits.append(f"Personality {info['from_personality']}")
        if info.get("from_media"):
            tip_bits.append(f"Media {info['from_media']}")
        color = range_color(attr, info.get("range"))
        help_id = f"{id_prefix}-pers-help-{attr.lower()}"
        help_info = attr_help(attr)
        label_children: list = [
            html.Span(attr, id=help_id, className="rs-player-id-label rs-pers-attr-label"),
        ]
        if help_info:
            label_children.append(
                dbc.Tooltip(
                    [
                        html.Div(help_info["definition"], className="rs-pers-tip-def"),
                        html.Div(
                            [html.Strong("High: "), help_info["high"]],
                            className="rs-pers-tip-line",
                        ),
                        html.Div(
                            [html.Strong("Low: "), help_info["low"]],
                            className="rs-pers-tip-line",
                        ),
                    ],
                    target=help_id,
                    placement="top",
                    trigger="hover",
                    delay={"show": 0, "hide": 0},
                    class_name="rs-help-tooltip rs-pers-attr-tooltip",
                )
            )
        items.append(
            html.Div(
                [
                    html.Div(label_children, className="rs-pers-attr-label-wrap"),
                    html.Span(
                        info["label"],
                        className=(
                            "rs-player-id-value rs-personality-range"
                            + (" is-conflict" if info.get("range") is None else "")
                        ),
                        style={"color": color} if color else None,
                        title=" · ".join(tip_bits) if tip_bits else "No constraint (1–20)",
                    ),
                ],
                className="rs-player-id-item",
            )
        )

    notes = []
    ldr_info = estimate["visible"].get("Leadership") or {}
    if ldr_info.get("label"):
        ldr = attrs.get("Ldr")
        actual = f" (actual {ldr})" if ldr is not None else ""
        notes.append(
            html.Div(
                f"Leadership expected {ldr_info['label']}{actual}",
                className="rs-personality-note",
            )
        )

    children = [
        html.Div("Personality", className="rs-player-id-section-title"),
    ]
    if subtitle_children:
        children.append(
            html.Div(subtitle_children, className="rs-personality-subtitle")
        )
    desc = tier_description(tier) if tier else ""
    if desc:
        children.append(html.Div(desc, className="rs-personality-tier-desc"))
    children.append(
        html.Div(items, className="rs-player-identity rs-personality-ranges")
    )
    children.extend(notes)
    return html.Div(children, className="rs-player-id-section rs-personality-section")


def _archetype_chip_elements(
    awards: Sequence[Mapping[str, Any]],
    *,
    id_prefix: str,
    pos_group: str | None,
) -> list:
    """Build archetype chips for one position group (or empty-state note)."""
    group = str(pos_group or "").strip().lower()
    filtered = [
        award
        for award in awards
        if str(award.get("group") or "").strip().lower() == group
    ]
    if not filtered:
        from scoring.player_archetypes import group_abbr

        label = group_abbr(group) if group else "—"
        return [
            html.Div(
                f"No {label} archetypes earned.",
                className="rs-arch-empty text-muted small",
            )
        ]

    chips = []
    for i, award in enumerate(filtered):
        chip_id = (
            f"{id_prefix}-arch-{award.get('id')}-{award.get('group')}-"
            f"{award.get('tier')}-{i}"
        )
        tier = str(award.get("tier") or "bronze")
        polarity = str(award.get("polarity") or "high")
        metric_lines = []
        for m in award.get("metrics") or []:
            pct = m.get("percentile")
            pct_txt = f"{pct:.0f}" if pct is not None else "—"
            metric_lines.append(
                html.Div(
                    f"{m.get('abbr') or m.get('label')}: {pct_txt}",
                    className="rs-arch-tip-metric",
                )
            )
        tip_kind = "High" if polarity == "high" else "Low"
        chips.append(
            html.Span(
                [
                    DashIconify(
                        icon=str(award.get("icon") or "game-icons:soccer-ball"),
                        width=24,
                        height=24,
                        className="rs-arch-icon",
                    ),
                    html.Span(
                        str(award.get("group_label") or ""),
                        className="rs-arch-group",
                    ),
                    dbc.Tooltip(
                        [
                            html.Div(
                                f"{award.get('label')} · {award.get('tier_label')} · "
                                f"{award.get('group_label')} ({tip_kind})",
                                className="rs-arch-tip-title",
                            ),
                            *metric_lines,
                        ],
                        target=chip_id,
                        placement="top",
                        trigger="hover",
                        delay={"show": 450, "hide": 500},
                        fade=False,
                        class_name="rs-help-tooltip rs-arch-tooltip",
                    ),
                ],
                id=chip_id,
                className=f"rs-arch-chip is-{tier} is-{polarity}",
            )
        )
    return chips


def _archetype_group_buttons(
    *,
    id_prefix: str,
    options: Sequence[tuple[str, str]],
    active: str | None,
) -> list:
    return [
        html.Button(
            label,
            id={"type": f"{id_prefix}-arch-group", "group": key},
            n_clicks=0,
            type="button",
            className="st-player-seg-btn"
            + (" active" if key == active else ""),
        )
        for key, label in options
    ]


def _archetype_group_switcher(
    *,
    id_prefix: str,
    options: Sequence[tuple[str, str]],
    active: str | None,
) -> html.Div | None:
    if len(options) <= 1:
        return None
    return html.Div(
        [
            html.Span("Group", className="st-player-switch-label"),
            html.Div(
                _archetype_group_buttons(
                    id_prefix=id_prefix, options=options, active=active
                ),
                id=f"{id_prefix}-arch-group-btns",
                className="st-player-seg",
            ),
        ],
        className="rs-arch-group-filter",
    )


def player_archetypes_section(
    player: dict,
    *,
    id_prefix: str = "rs",
    settings=None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    cohort_players: list[dict] | None = None,
    banding_ctx=None,
    value_mode: str = "raw",
    pos_group: str | None = None,
) -> html.Div | None:
    """Icon chips for earned archetypes, filtered by position group.

    Default group is Best Pos (via ``pos_group`` / player ``pos_group``). Profiles
    pass the depth-slot phase so the filter opens on that group.
    """
    if not player or not (player.get("stats") or player.get("minutes")):
        return None

    settings = us.normalize(settings)
    threshold_overrides = None
    metric_p0 = None
    metric_p100 = None
    if banding_ctx is not None:
        threshold_overrides, metric_p0, metric_p100 = us.banding_for_player(
            banding_ctx, player, settings=settings
        )
    elif cohort_players is not None:
        banding_ctx = us.build_stats_banding_context(
            settings,
            cohort_players,
            limited_divisions=limited_divisions,
        )
        threshold_overrides, metric_p0, metric_p100 = us.banding_for_player(
            banding_ctx, player, settings=settings
        )

    options = archetype_pos_group_options(player, preferred=pos_group)
    awards = evaluate_archetypes(
        player,
        settings=settings,
        threshold_overrides=threshold_overrides,
        metric_p0=metric_p0,
        metric_p100=metric_p100,
        limited_divisions=limited_divisions,
        value_mode=value_mode,
        include_groups=[key for key, _ in options] or None,
    )
    if not awards and not options:
        return None

    active = resolve_archetype_pos_group(player, preferred=pos_group)
    if active is None and options:
        active = options[0][0]
    chips = _archetype_chip_elements(
        awards, id_prefix=id_prefix, pos_group=active
    )
    switcher = _archetype_group_switcher(
        id_prefix=id_prefix, options=options, active=active
    )
    header_children: list = [
        html.Div("Archetypes", className="rs-player-id-section-title"),
    ]
    if switcher is not None:
        header_children.append(switcher)
    else:
        # Keep a stable target for the group-switch callback when only one group.
        header_children.append(
            html.Div(id=f"{id_prefix}-arch-group-btns", style={"display": "none"})
        )
    return html.Div(
        [
            html.Div(header_children, className="rs-arch-section-header"),
            html.Div(
                chips,
                id=f"{id_prefix}-arch-chips",
                className="rs-arch-chip-row",
            ),
            dcc.Store(id=f"{id_prefix}-arch-awards", data=list(awards)),
            dcc.Store(id=f"{id_prefix}-arch-group", data=active),
            dcc.Store(
                id=f"{id_prefix}-arch-group-opts",
                data=[{"id": key, "label": label} for key, label in options],
            ),
        ],
        className="rs-player-id-section rs-archetypes-section",
    )


def register_archetype_group_callbacks(prefix: str) -> None:
    """Switch archetype position-group filter inside the player modal."""
    from components.scouting_shell import clicked

    awards_id = f"{prefix}-arch-awards"
    group_id = f"{prefix}-arch-group"
    opts_id = f"{prefix}-arch-group-opts"
    chips_id = f"{prefix}-arch-chips"
    btns_id = f"{prefix}-arch-group-btns"
    btn_type = f"{prefix}-arch-group"

    @callback(
        Output(chips_id, "children"),
        Output(group_id, "data"),
        Output(btns_id, "children"),
        Input({"type": btn_type, "group": ALL}, "n_clicks"),
        State(awards_id, "data"),
        State(group_id, "data"),
        State(opts_id, "data"),
        prevent_initial_call=True,
    )
    def _switch_archetype_group(n_clicks, awards, current, opts):
        if not ctx.triggered_id or not clicked(n_clicks):
            return no_update, no_update, no_update
        group = str(ctx.triggered_id.get("group") or "").strip().lower()
        if not group or group == "_":
            return no_update, no_update, no_update
        if group == str(current or "").strip().lower():
            return no_update, no_update, no_update
        award_rows = awards if isinstance(awards, list) else []
        options: list[tuple[str, str]] = []
        for item in opts or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or "").strip().lower()
            if not key:
                continue
            label = str(item.get("label") or key).strip() or key.upper()
            options.append((key, label))
        if group not in {key for key, _ in options}:
            return no_update, no_update, no_update
        chips = _archetype_chip_elements(
            award_rows, id_prefix=prefix, pos_group=group
        )
        buttons = _archetype_group_buttons(
            id_prefix=prefix, options=options, active=group
        )
        return chips, group, buttons

    register_modal_section_callbacks(prefix)


def register_modal_section_callbacks(prefix: str) -> None:
    """Exclusive detail filter: one of international / contract / career / season / discipline."""
    from components.scouting_shell import clicked

    btn_type = f"{prefix}-modal-extra-btn"
    panel_type = f"{prefix}-modal-extra-panel"
    sel_id = f"{prefix}-modal-extra-sel"
    extras_id = f"{prefix}-modal-extras"

    @callback(
        Output(sel_id, "data"),
        Output(extras_id, "hidden"),
        Output({"type": btn_type, "section": ALL}, "className"),
        Output({"type": panel_type, "section": ALL}, "hidden"),
        Input({"type": btn_type, "section": ALL}, "n_clicks"),
        State(sel_id, "data"),
        State({"type": btn_type, "section": ALL}, "id"),
        State({"type": panel_type, "section": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _switch_modal_extra_section(n_clicks, current, btn_ids, panel_ids):
        if not ctx.triggered_id or not clicked(n_clicks):
            return (no_update,) * 4
        section = str(ctx.triggered_id.get("section") or "").strip().lower()
        if not section:
            return (no_update,) * 4
        cur = str(current or "").strip().lower() or None
        new = None if section == cur else section
        btn_classes = [
            "st-player-seg-btn"
            + (
                " active"
                if isinstance(bid, dict)
                and str(bid.get("section") or "").strip().lower() == (new or "")
                else ""
            )
            for bid in (btn_ids or [])
        ]
        panel_hidden = [
            not (
                isinstance(pid, dict)
                and new is not None
                and str(pid.get("section") or "").strip().lower() == new
            )
            for pid in (panel_ids or [])
        ]
        return new, new is None, btn_classes, panel_hidden


def player_detail_body(
    player: dict,
    *,
    id_prefix: str = "rs",
    position_eligible: str | None = None,
    modal_fields: Sequence[tuple[str, str, str]] | None = None,
    extra_identity_fields: Sequence[tuple[str, str]] | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    after_identity=None,
    bottom=None,
    settings=None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
    cohort_players: list[dict] | None = None,
    banding_ctx=None,
    value_mode: str = "raw",
    show_archetypes: bool = True,
    arch_pos_group: str | None = None,
) -> html.Div:
    """Shared modal body.

    Always: player identity, then personality / archetypes / page content.
    Optional exclusive filter only toggles international / contract / career /
    season / discipline above that content.
    """
    effective_theme = theme
    if effective_theme is None and settings:
        effective_theme = us.preferred_theme(settings)
    children: list = [
        *player_identity_sections(
            player,
            position_eligible=position_eligible,
            fields=modal_fields,
            extra_identity_fields=extra_identity_fields,
            field_styles=field_styles,
            field_formatters=field_formatters,
            theme=effective_theme,
            limited_divisions=limited_divisions,
            include_sections=("identity",),
        ),
    ]

    extra_sections = _modal_extra_section_nodes(
        player,
        modal_fields=modal_fields,
        field_styles=field_styles,
        field_formatters=field_formatters,
        theme=effective_theme,
        limited_divisions=limited_divisions,
        settings=settings,
    )
    if extra_sections:
        children.append(
            _modal_section_filter(
                id_prefix=id_prefix,
                options=[(key, label) for key, label, _node in extra_sections],
            )
        )
        children.append(
            html.Div(
                [
                    html.Div(
                        node,
                        id={
                            "type": f"{id_prefix}-modal-extra-panel",
                            "section": key,
                        },
                        hidden=True,
                        className="rs-modal-extra-panel",
                    )
                    for key, _label, node in extra_sections
                ],
                id=f"{id_prefix}-modal-extras",
                className="rs-modal-extras",
                hidden=True,
            )
        )
    else:
        # Stable targets for the section-filter callback when a player has none.
        children.append(
            html.Div(
                dcc.Store(id=f"{id_prefix}-modal-extra-sel", data=None),
                id=f"{id_prefix}-modal-extras",
                className="rs-modal-extras",
                hidden=True,
            )
        )

    main_children: list = [
        player_personality_section(player, id_prefix=id_prefix, settings=settings),
    ]
    if show_archetypes:
        main_children.append(
            player_archetypes_section(
                player,
                id_prefix=id_prefix,
                settings=settings,
                limited_divisions=limited_divisions,
                cohort_players=cohort_players,
                banding_ctx=banding_ctx,
                value_mode=value_mode,
                pos_group=arch_pos_group,
            )
        )
    if after_identity is not None:
        if isinstance(after_identity, (list, tuple)):
            main_children.extend(after_identity)
        else:
            main_children.append(after_identity)
    if bottom is not None:
        if isinstance(bottom, (list, tuple)):
            main_children.extend(bottom)
        else:
            main_children.append(bottom)

    children.append(
        html.Div(
            [child for child in main_children if child is not None],
            className="rs-modal-main rs-player-detail-stack",
        )
    )
    return html.Div(
        [child for child in children if child is not None],
        className="rs-player-detail rs-player-detail-stack",
    )


def player_modal(*, prefix: str) -> dbc.Modal:
    """Reusable modal shell. IDs: `{prefix}-player-modal[-title|-body|-close]`."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(id=f"{prefix}-player-modal-title"),
                close_button=True,
            ),
            dbc.ModalBody(
                id=f"{prefix}-player-modal-body",
                className="rs-player-modal-body",
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id=f"{prefix}-player-modal-close",
                    n_clicks=0,
                    className="rs-player-modal-close",
                )
            ),
        ],
        id=f"{prefix}-player-modal",
        is_open=False,
        size="xl",
        centered=True,
        scrollable=False,
        backdrop=True,
        keyboard=True,
        className="rs-player-modal",
        content_class_name="rs-player-modal-content",
    )
