"""Reusable pack selector + Edit link for card headers and toolbars."""
from __future__ import annotations

from typing import Any

from dash import dcc, html
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc


def pack_picker_bar(
    *,
    select_id: str,
    label: str,
    options: list[dict],
    value: Any = None,
    edit_href: str,
    edit_label: str = "Edit",
    edit_title: str | None = None,
    select_title: str | None = None,
    size: str = "sm",
    clearable: bool = False,
    searchable: bool = False,
    placeholder: str | None = None,
    interval_id: str | None = None,
    interval_ms: int = 2500,
    class_name: str = "pack-picker-bar",
    select_wrap_class: str = "pack-picker-dd",
) -> html.Div:
    """Label + Select + Edit link (optional poll interval), matching Role scores weights UI."""
    children: list = [
        html.Span(label, className="pack-picker-label"),
        html.Div(
            dmc.Select(
                id=select_id,
                data=options,
                value=value,
                clearable=clearable,
                searchable=searchable,
                placeholder=placeholder,
                size=size,
            ),
            className=select_wrap_class,
            title=select_title or "",
        ),
        dcc.Link(
            edit_label,
            href=edit_href,
            className="pack-picker-edit",
            title=edit_title or f"Open editor for {label.lower()}.",
        ),
    ]
    if interval_id:
        children.append(dcc.Interval(id=interval_id, interval=interval_ms))
    return html.Div(children, className=class_name)


def section_card_header(
    title: str,
    *,
    trailing: Any = None,
    next_badge: bool = False,
    class_name: str = "rs-card-header-row",
) -> dbc.CardHeader:
    """Card header with title on the left and optional trailing controls."""
    title_children: list = [html.Span(title)]
    if next_badge:
        title_children.append(html.Span("Next", className="rs-next-badge"))
    left = html.Div(title_children, className="rs-card-header-title")
    children: list = [left]
    if trailing is not None:
        children.append(trailing)
    return dbc.CardHeader(children, className=class_name)
