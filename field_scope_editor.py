"""Shared order + page-scope field config helpers and settings table UI."""
from __future__ import annotations

from dash import html
import dash_mantine_components as dmc

FIELD_SCOPES = (
    {"label": "Both", "value": "both"},
    {"label": "Role scores", "value": "role_scores"},
    {"label": "Player stats", "value": "player_stats"},
    {"label": "Hidden", "value": "off"},
)


def move_in_order(order: list[str], item: str, direction: str) -> list[str]:
    """Swap item one step up/down in order (no-op at bounds)."""
    items = list(order or [])
    if item not in items:
        return items
    idx = items.index(item)
    if direction == "up" and idx > 0:
        items[idx - 1], items[idx] = items[idx], items[idx - 1]
    elif direction == "down" and idx < len(items) - 1:
        items[idx + 1], items[idx] = items[idx], items[idx + 1]
    return items


def scope_table(
    *,
    prefix: str,
    order: list[str],
    scopes: dict[str, str],
    labels: dict[str, str],
    fixed_top: list[tuple[str, str]] | None = None,
) -> html.Table:
    """Reorderable scope table: ↑↓ | label | segmented scope."""
    rows: list = []
    for label, note in fixed_top or []:
        rows.append(
            html.Tr(
                [
                    html.Td("", className="st-field-order-cell"),
                    html.Td(label, className="st-field-name-cell"),
                    html.Td(html.Span(note, className="text-muted")),
                ],
                className="st-field-scope-row is-fixed",
            )
        )
    for field_id in order:
        label = labels.get(field_id, field_id)
        rows.append(
            html.Tr(
                [
                    html.Td(
                        html.Div(
                            [
                                dmc.ActionIcon(
                                    "↑",
                                    id={"type": f"{prefix}-up", "field": field_id},
                                    variant="subtle",
                                    size="sm",
                                    className="st-field-order-btn",
                                    n_clicks=0,
                                ),
                                dmc.ActionIcon(
                                    "↓",
                                    id={"type": f"{prefix}-down", "field": field_id},
                                    variant="subtle",
                                    size="sm",
                                    className="st-field-order-btn",
                                    n_clicks=0,
                                ),
                            ],
                            className="st-field-order-btns",
                        ),
                        className="st-field-order-cell",
                    ),
                    html.Td(label, className="st-field-name-cell"),
                    html.Td(
                        dmc.SegmentedControl(
                            id={"type": f"{prefix}-scope", "field": field_id},
                            value=scopes.get(field_id, "off"),
                            data=list(FIELD_SCOPES),
                            size="xs",
                            fullWidth=True,
                            className="st-field-scope-control",
                        ),
                    ),
                ],
                className="st-field-scope-row",
            )
        )
    return html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Order", className="st-field-order-cell"),
                        html.Th("Field"),
                        html.Th("Show on"),
                    ]
                )
            ),
            html.Tbody(rows),
        ],
        className="st-field-scope-table",
    )


def _field_id_from_spec(spec) -> str | None:
    """Dash passes either a raw pattern id dict or a states_list entry."""
    if not isinstance(spec, dict):
        return None
    ident = spec.get("id")
    if isinstance(ident, dict) and ident.get("field") is not None:
        return str(ident["field"])
    if spec.get("field") is not None:
        return str(spec["field"])
    return None


def scopes_from_state(scope_values, scope_specs) -> dict[str, str]:
    out: dict[str, str] = {}
    for spec, value in zip(scope_specs or [], scope_values or []):
        field_id = _field_id_from_spec(spec)
        if field_id:
            out[field_id] = value or "off"
    return out
