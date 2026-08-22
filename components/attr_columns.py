"""Shared attribute column grid (Role configs + player profile)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dash import html

import role_config as rc

RowBuilder = Callable[[str, str], Any]


def attr_row(
    label: str,
    value: str,
    *,
    value_class: str = "none",
    row_class: str = "",
    title: str | None = None,
    attr_id: str | None = None,
) -> html.Button | html.Div:
    """One attribute name + value row. Pass attr_id for the editable Role configs button."""
    children = [
        html.Span(label, className="rc-attr-name"),
        html.Span(value, className=f"rc-attr-val {value_class}"),
    ]
    classes = "rc-attr-row" + (f" {row_class}" if row_class else "")
    if attr_id is not None:
        return html.Button(
            children,
            id={"type": "rc-attr", "attr": attr_id},
            n_clicks=0,
            className=classes,
            title=title or "",
        )
    return html.Div(
        children,
        className=classes + " is-static",
        title=title or "",
    )


def attr_column(title: str, rows: list, extra=None) -> html.Div:
    children = [
        html.Div(title, className="rc-col-head"),
        html.Div(rows, className="rc-col-body"),
    ]
    if extra:
        children.extend(extra)
    return html.Div(children, className="rc-attr-col")


def attr_group_columns(*, is_gk: bool, make_row: RowBuilder) -> list[html.Div]:
    """Tech/GK · Mental · Physical columns; set pieces under Physical for outfield."""
    groups = rc.GK_ATTR_GROUPS if is_gk else rc.OUTFIELD_ATTR_GROUPS
    columns: list[html.Div] = []
    for title, attrs in groups:
        extra = None
        if title == "Physical" and not is_gk:
            extra = [
                html.Div("Set Pieces", className="rc-col-head nested"),
                html.Div(
                    [make_row(code, label) for code, label in rc.SET_PIECE_ATTRS],
                    className="rc-col-body",
                ),
            ]
        columns.append(
            attr_column(
                title,
                [make_row(code, label) for code, label in attrs],
                extra=extra,
            )
        )
    return columns


def attr_grid(columns: list) -> html.Div:
    return html.Div(columns, className="rc-attr-grid")
