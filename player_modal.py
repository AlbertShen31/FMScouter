"""Shared player detail modal: identity, international, personality, shell.

Page-specific content (attribute grid, stats charts) is passed as `bottom`
and optional `after_identity` children.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from dash import html
import dash_bootstrap_components as dbc

from personality_ranges import attr_help, estimate_hidden_ranges, range_color

# Shown on the player modal. Parsed CSV fields listed here are hidden for now
# unless the user enables them via Settings → modal_extra_fields.
PLAYER_IDENTITY_HIDDEN = frozenset(
    {
        "world_reputation",
        "ability",
        "potential",
        "squad",
        "personality",
        "media_handling",
    }
)

MODAL_EXTRA_FIELD_DEFS = (
    ("Ability", "ability"),
    ("Potential", "potential"),
    ("World reputation", "world_reputation"),
    ("Squad", "squad"),
    ("Personality", "personality"),
    ("Media handling", "media_handling"),
)

PLAYER_IDENTITY_SECTIONS = [
    (
        None,
        [
            [
                ("Age", "age"),
                ("Club", "club"),
                ("Division", "division"),
                ("Nation", "nation"),
                ("Position", "position"),
                ("Best pos", "best_pos"),
                ("Best role", "best_role"),
                ("Style", "style"),
                ("Height", "height"),
                ("Left foot", "left_foot"),
                ("Right foot", "right_foot"),
                ("Rec", "rec"),
                ("Inf", "inf"),
                ("Injury", "injury"),
            ],
        ],
    ),
    (
        "International & youth",
        [
            [
                ("National team", "national_team"),
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


def is_identity_hidden(key: str, modal_extra_fields: Sequence[str] | None = None) -> bool:
    """Hide default-hidden keys unless the user opted them in via settings."""
    if key not in PLAYER_IDENTITY_HIDDEN:
        return False
    return key not in set(modal_extra_fields or ())


def player_identity_item(
    label: str,
    key: str,
    player: dict,
    *,
    position_eligible: str | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    modal_extra_fields: Sequence[str] | None = None,
) -> html.Div | None:
    if is_identity_hidden(key, modal_extra_fields) or not identity_value_present(
        player.get(key)
    ):
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
    raw = player.get(key)
    formatter = (field_formatters or {}).get(key)
    text = formatter(raw) if formatter else str(raw or "—")
    style = dict((field_styles or {}).get(key) or {})
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


def player_identity_sections(
    player: dict,
    *,
    position_eligible: str | None = None,
    extra_identity_fields: Sequence[tuple[str, str]] | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    modal_extra_fields: Sequence[str] | None = None,
) -> list:
    """Build identity + international section nodes (no personality)."""
    sections_spec = list(PLAYER_IDENTITY_SECTIONS)
    enabled_extra = set(modal_extra_fields or ())
    modal_fields = [
        (label, key) for label, key in MODAL_EXTRA_FIELD_DEFS if key in enabled_extra
    ]
    extras = list(extra_identity_fields or ()) + modal_fields
    if extras:
        # Append extras to the primary (untitled) identity row.
        title0, rows0 = sections_spec[0]
        primary = list(rows0[0]) + list(extras)
        sections_spec[0] = (title0, [primary, *rows0[1:]])

    sections = []
    for title, rows in sections_spec:
        row_blocks = []
        for fields in rows:
            items = [
                item
                for item in (
                    player_identity_item(
                        label,
                        key,
                        player,
                        position_eligible=position_eligible,
                        field_styles=field_styles,
                        field_formatters=field_formatters,
                        modal_extra_fields=modal_extra_fields,
                    )
                    for label, key in fields
                )
                if item is not None
            ]
            if items:
                row_blocks.append(html.Div(items, className="rs-player-identity"))
        if not row_blocks:
            continue
        if title:
            sections.append(
                html.Div(
                    [
                        html.Div(title, className="rs-player-id-section-title"),
                        *row_blocks,
                    ],
                    className="rs-player-id-section",
                )
            )
        else:
            sections.extend(row_blocks)
    return sections


def player_personality_section(
    player: dict,
    *,
    id_prefix: str = "rs",
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

    subtitle_parts = []
    if estimate["personality"]:
        subtitle_parts.append(estimate["personality"])
    elif player.get("personality"):
        subtitle_parts.append(str(player.get("personality")))
    if estimate["media_handling"]:
        subtitle_parts.append(estimate["media_handling"])
    elif player.get("media_handling"):
        subtitle_parts.append(str(player.get("media_handling")))

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
    if subtitle_parts:
        children.append(
            html.Div(" · ".join(subtitle_parts), className="rs-personality-subtitle")
        )
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
    extra_identity_fields: Sequence[tuple[str, str]] | None = None,
    field_styles: Mapping[str, dict] | None = None,
    field_formatters: Mapping[str, FieldFormatter] | None = None,
    modal_extra_fields: Sequence[str] | None = None,
    after_identity=None,
    bottom=None,
) -> html.Div:
    """Shared modal body: identity → international → personality → page content."""
    children = [
        *player_identity_sections(
            player,
            position_eligible=position_eligible,
            extra_identity_fields=extra_identity_fields,
            field_styles=field_styles,
            field_formatters=field_formatters,
            modal_extra_fields=modal_extra_fields,
        ),
        player_personality_section(player, id_prefix=id_prefix),
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
