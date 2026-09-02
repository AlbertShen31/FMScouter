"""Shared player detail modal: identity, international, personality, shell.

Page-specific content (attribute grid, stats charts) is passed as `bottom`
and optional `after_identity` children.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from dash import html
import dash_bootstrap_components as dbc

from scoring.personality_ranges import attr_help, estimate_hidden_ranges, range_color
from scoring.personality_tiers import (
    classify_personality,
    personality_tier_style,
    tier_description,
    tier_label,
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

FINANCE_MODAL_FIELDS = (
    ("Transfer value", "transfer_value"),
    ("Salary", "salary"),
    ("Contract expires", "contract_expires"),
    ("FFP contribution", "ffp_contribution"),
    ("Release clause", "min_release_clause"),
    ("Work permit", "work_permit_required"),
    ("WP needed", "wp_needed"),
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
) -> list:
    """Build identity + international section nodes (no personality)."""
    configured = [
        (label, key, section)
        for label, key, section in (fields or [])
        if key not in STAR_ATTRIBUTES_BROKEN
    ]
    if extra_identity_fields:
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
    for title in (None, "International & youth"):
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


def player_record_section(
    player: dict,
    title: str,
    field_defs: Sequence[tuple[str, str]],
    *,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    theme: str | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> html.Div | None:
    """Career totals, discipline, etc. from the stats export."""
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
            for label, key in field_defs
        )
        if item is not None
    ]
    if not items:
        return None
    return html.Div(
        [
            html.Div(title, className="rs-player-id-section-title"),
            html.Div(items, className="rs-player-identity"),
        ],
        className="rs-player-id-section",
    )


def player_career_section(player: dict, **kwargs) -> html.Div | None:
    return player_record_section(player, "Career totals", CAREER_MODAL_FIELDS, **kwargs)


def player_playing_time_section(player: dict, **kwargs) -> html.Div | None:
    return player_record_section(player, "Season stats", PLAYING_TIME_MODAL_FIELDS, **kwargs)


def player_discipline_section(player: dict, **kwargs) -> html.Div | None:
    return player_record_section(player, "Discipline", DISCIPLINE_MODAL_FIELDS, **kwargs)


def player_finance_section(player: dict, **kwargs) -> html.Div | None:
    return player_record_section(player, "Contract & finance", FINANCE_MODAL_FIELDS, **kwargs)


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
) -> html.Div:
    """Shared modal body: identity → international → finance → career → season stats → discipline → personality → page content."""
    effective_theme = theme
    if effective_theme is None and settings:
        effective_theme = us.preferred_theme(settings)
    section_kwargs = {
        "field_styles": field_styles,
        "field_formatters": field_formatters,
        "theme": effective_theme,
        "limited_divisions": limited_divisions,
    }
    children = [
        *player_identity_sections(
            player,
            position_eligible=position_eligible,
            fields=modal_fields,
            extra_identity_fields=extra_identity_fields,
            field_styles=field_styles,
            field_formatters=field_formatters,
            theme=effective_theme,
            limited_divisions=limited_divisions,
        ),
        player_finance_section(player, **section_kwargs),
        player_career_section(player, **section_kwargs),
        player_playing_time_section(player, **section_kwargs),
        player_discipline_section(player, **section_kwargs),
        player_personality_section(player, id_prefix=id_prefix, settings=settings),
    ]
    if after_identity is not None:
        if isinstance(after_identity, (list, tuple)):
            children.extend(after_identity)
        else:
            children.append(after_identity)
    if bottom is not None:
        if isinstance(bottom, (list, tuple)):
            children.extend(bottom)
        else:
            children.append(bottom)
    return html.Div(
        [child for child in children if child is not None],
        className="rs-player-detail",
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
