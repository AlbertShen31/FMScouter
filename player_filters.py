"""Shared shortlist filters: position groups, footedness, optional stat category."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dash import html
import dash_bootstrap_components as dbc

from role_scorer import foot_filter_help, foot_filter_hints

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
