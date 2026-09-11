"""Shared shortlist filters: position groups, footedness, optional stat category."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc
from dash_iconify import DashIconify

from scoring.role_scorer import foot_filter_help, foot_filter_hints

FOOT_OPTIONS = (
    ("foot-L", "Left Foot"),
    ("foot-B", "Both Feet"),
    ("foot-R", "Right Foot"),
)


def help_icon(tip: str, help_id: str) -> list:
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


def _pos_button(
    *,
    prefix: str,
    key: str,
    label: str,
    css: str,
    count: int | None,
    active: str,
    code: str = "",
    id_attr: str = "key",
) -> html.Button:
    class_name = f"rs-pos-card {css}" + (" active" if active == key else "")
    children: list = [html.Span(label, className="rs-pos-name")]
    if code:
        children.append(html.Span(code, className="rs-pos-code"))
    if count is not None:
        children.append(html.Span(str(count), className="rs-pos-count"))
    return html.Button(
        children,
        id={"type": f"{prefix}-pos", id_attr: key},
        n_clicks=0,
        className=class_name,
    )


def pos_cards(
    *,
    prefix: str,
    groups: Sequence[Mapping[str, Any]],
    active: str,
    id_attr: str = "key",
) -> html.Div:
    """Row of position-group cards.

    Each group mapping: ``key``, ``label``, ``css``, optional ``code``, optional ``count``.
    """
    cards = [
        _pos_button(
            prefix=prefix,
            key=str(item["key"]),
            label=str(item["label"]),
            css=str(item.get("css") or item["key"]),
            count=item.get("count"),
            active=active,
            code=str(item.get("code") or ""),
            id_attr=id_attr,
        )
        for item in groups
    ]
    return html.Div(cards, className="rs-pos-cards")


def footedness_controls(
    *,
    prefix: str,
    active: str,
    foot_thresholds=None,
) -> html.Div:
    """Footedness label + Left / Both / Right toggle buttons."""
    hints = foot_filter_hints(foot_thresholds)
    buttons = [
        html.Button(
            label,
            id={"type": f"{prefix}-foot", "foot": key},
            n_clicks=0,
            title=hints.get(key, ""),
            className="rs-foot-btn" + (" active" if active == key else ""),
        )
        for key, label in FOOT_OPTIONS
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Footedness"),
                    *help_icon(
                        foot_filter_help(foot_thresholds),
                        f"{prefix}-help-footedness",
                    ),
                ],
                className="rs-foot-label",
            ),
            html.Div(buttons, className="rs-foot-btns"),
        ],
        className="rs-pos-utils",
    )


def category_controls(
    *,
    prefix: str,
    categories: Sequence[Mapping[str, str]],
    active: str,
    label: str = "Category",
) -> html.Div:
    """Stat-category card row (All / Defending / …)."""
    cards = [
        html.Button(
            html.Span(cat["label"], className="rs-pos-name"),
            id={"type": f"{prefix}-cat", "key": cat["id"]},
            n_clicks=0,
            className="rs-pos-card" + (" active" if cat["id"] == active else ""),
        )
        for cat in categories
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Div(html.Span(label), className="rs-foot-label"),
                    html.Div(cards, className="rs-pos-cards"),
                ],
                className="rs-pos-utils",
            )
        ],
        className="rs-pos-bar st-cat-bar",
    )


def player_filters(
    *,
    prefix: str,
    pos_groups: Sequence[Mapping[str, Any]],
    active_pos: str,
    active_foot: str = "",
    foot_thresholds=None,
    categories: Sequence[Mapping[str, str]] | None = None,
    active_category: str | None = None,
    pos_id_attr: str = "key",
    foot_inline: bool = False,
) -> html.Div | list:
    """Build position + footedness filters (and optional category below foot).

    - ``foot_inline=True`` (Role scores): one bar with cards + footedness side by side.
    - ``foot_inline=False`` (Player stats): list of stacked bars for the filters host;
      category (if any) comes after footedness.
    """
    cards = pos_cards(
        prefix=prefix,
        groups=pos_groups,
        active=active_pos,
        id_attr=pos_id_attr,
    )
    feet = footedness_controls(
        prefix=prefix,
        active=active_foot or "",
        foot_thresholds=foot_thresholds,
    )
    if foot_inline:
        return html.Div(
            [cards, feet],
            className="rs-pos-bar",
        )

    stack: list = [
        html.Div([cards], className="rs-pos-bar"),
        html.Div([feet], className="rs-pos-bar st-foot-bar"),
    ]
    if categories is not None:
        stack.append(
            category_controls(
                prefix=prefix,
                categories=categories,
                active=active_category or "all",
            )
        )
    return stack


def player_filters_host(*, prefix: str, stacked: bool = False) -> html.Div:
    """Empty host node(s) filled by page callbacks."""
    if stacked:
        return html.Div(id=f"{prefix}-filters", className="st-filter-stack")
    return html.Div(id=f"{prefix}-pos-bar")


def archetype_filter_buttons(
    *,
    prefix: str,
    selected: Sequence[str] | None = None,
) -> list:
    """Grouped toggle buttons for high-tier archetype filter (icon-only)."""
    from scoring.player_archetypes import (
        archetypes_by_filter_category,
        normalize_archetype_filter,
    )
    from scoring.stats_scorer import metric_defs

    active = set(normalize_archetype_filter(selected))
    metrics_meta = metric_defs()
    groups = []
    for category, arches in archetypes_by_filter_category():
        buttons = []
        cat_label = str(category.get("label") or category.get("id") or "")
        for arch in arches:
            arch_id = str(arch.get("id") or "").strip()
            if not arch_id:
                continue
            label = str(arch.get("label") or arch_id)
            is_on = arch_id in active
            tip_id = f"{prefix}-arch-ftip-{arch_id}"
            metric_lines = []
            for mid in arch.get("metrics") or []:
                key = str(mid or "").strip()
                if not key:
                    continue
                meta = metrics_meta.get(key) or {}
                metric_lines.append(
                    html.Div(
                        str(meta.get("abbr") or meta.get("label") or key),
                        className="rs-arch-tip-metric",
                    )
                )
            tip_body = [
                html.Div(label, className="rs-arch-tip-title"),
                html.Div(cat_label, className="rs-arch-tip-cat"),
            ]
            description = str(arch.get("description") or "").strip()
            if description:
                tip_body.append(
                    html.Div(description, className="rs-arch-tip-desc")
                )
            if metric_lines:
                tip_body.append(
                    html.Div(metric_lines, className="rs-arch-tip-metrics")
                )
            buttons.append(
                html.Span(
                    [
                        html.Button(
                                    DashIconify(
                                        icon=str(arch.get("icon") or "game-icons:soccer-ball"),
                                        width=24,
                                        height=24,
                                        className="rs-arch-icon",
                                    ),
                            id={"type": f"{prefix}-archetype", "id": arch_id},
                            n_clicks=0,
                            type="button",
                            className="rs-arch-filter-btn"
                            + (" active" if is_on else ""),
                            **{
                                "aria-label": label,
                                "aria-pressed": "true" if is_on else "false",
                            },
                        ),
                        dbc.Tooltip(
                            tip_body,
                            target=tip_id,
                            placement="top",
                            class_name="rs-help-tooltip rs-arch-tooltip",
                        ),
                    ],
                    id=tip_id,
                    className="rs-arch-filter-tip-host",
                )
            )
        if not buttons:
            continue
        groups.append(
            html.Div(
                [
                    html.Span(cat_label, className="rs-arch-filter-cat-label"),
                    html.Div(buttons, className="rs-arch-filter-cat-btns"),
                ],
                className="rs-arch-filter-cat",
                **{"data-category": str(category.get("id") or "")},
            )
        )
    return groups


def archetype_filter_control(
    *,
    prefix: str,
    value: Sequence[str] | None = None,
) -> html.Div:
    """Icon toggles: keep players who earn any selected high-tier archetype."""
    from scoring.player_archetypes import normalize_archetype_filter

    selected = normalize_archetype_filter(value)
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Archetypes", className="rs-field-label"),
                    *help_icon(
                        "Click icons to keep players who earn any selected "
                        "archetype at Bronze, Silver, or Gold (low / opposite "
                        "tiers are ignored). Requires Moneyball stats and enough "
                        "minutes. Empty selection = any archetype.",
                        f"{prefix}-help-archetypes",
                    ),
                ],
                className="rs-field-label-row",
            ),
            html.Div(
                archetype_filter_buttons(prefix=prefix, selected=selected),
                id=f"{prefix}-archetype-btns",
                className="rs-arch-filter-btns",
                role="group",
                **{"aria-label": "Archetype filters"},
            ),
            dcc.Store(id=f"{prefix}-archetypes", data=selected),
        ],
        className="rs-filter-archetypes",
    )


def register_archetype_filter_callbacks(prefix: str) -> None:
    """Toggle archetype filter store and refresh icon button active states."""
    from components.scouting_shell import clicked
    from scoring.player_archetypes import normalize_archetype_filter

    store_id = f"{prefix}-archetypes"
    btn_host = f"{prefix}-archetype-btns"
    btn_type = f"{prefix}-archetype"

    @callback(
        Output(store_id, "data"),
        Input({"type": btn_type, "id": ALL}, "n_clicks"),
        State(store_id, "data"),
        prevent_initial_call=True,
    )
    def _toggle_archetype_filter(n_clicks, current):
        if not ctx.triggered_id or not clicked(n_clicks):
            return no_update
        arch_id = str(ctx.triggered_id.get("id") or "").strip()
        if not arch_id or arch_id == "_":
            return no_update
        selected = normalize_archetype_filter(current)
        if arch_id in selected:
            return [item for item in selected if item != arch_id]
        return [*selected, arch_id]

    @callback(
        Output(btn_host, "children"),
        Input(store_id, "data"),
    )
    def _render_archetype_filter_buttons(selected):
        return archetype_filter_buttons(prefix=prefix, selected=selected)
