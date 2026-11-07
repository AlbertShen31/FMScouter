"""Staff scores: enter FM staff attributes → Pre-Game Editor weighted averages."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
import dash_mantine_components as dmc

from components.player_filters import help_icon
from scoring import staff_scorer as ss

register_page(__name__, path="/staff-scores", name="Staff scores")

_ATTRS = ss.attributes()
_ROLES = ss.roles()
_DEFAULT_ROLE = "coach"
_ROLE_CATEGORIES = ("Coaching", "Recruitment", "Medical")
_GROUP_ORDER = (
    "Coaching",
    "Goalkeeping",
    "Mental",
    "Knowledge",
    "Data",
    "Medical",
    "Other",
)

PAGE_TIP = (
    "Enter staff attributes on the 1–20 scale. Scores use Football Manager 2024 "
    "Pre-Game Editor role weights (hidden staff CA / valuation estimate). "
    "Blank fields count as 1. Coverage shows how much of the role’s weight "
    "is included. Adaptability and Level of Discipline have "
    "weight 0 for every role in the editor table."
)


def _roles_by_category() -> list[tuple[str, list[dict]]]:
    grouped: dict[str, list[dict]] = {cat: [] for cat in _ROLE_CATEGORIES}
    for role in _ROLES:
        cat = str(role.get("category") or "Coaching")
        grouped.setdefault(cat, []).append(role)
    return [(cat, roles) for cat, roles in grouped.items() if roles]


def _role_options() -> list[dict]:
    return [
        {
            "group": category,
            "items": [{"value": role["id"], "label": role["label"]} for role in roles],
        }
        for category, roles in _roles_by_category()
    ]


def _attr_input(attr: dict) -> html.Div:
    attr_id = str(attr["id"])
    label = str(attr["label"])
    if attr.get("abbr"):
        label = f"{label} ({attr['abbr']})"
    if attr.get("hidden"):
        label = f"{label} (hidden)"
    return html.Div(
        [
            html.Label(label, className="ss-attr-label", htmlFor=f"ss-attr-{attr_id}"),
            dmc.NumberInput(
                id={"type": "ss-attr", "attr": attr_id},
                min=1,
                max=20,
                step=1,
                decimalScale=0,
                hideControls=False,
                value=1,
                debounce=200,
                placeholder="1",
                className="ss-attr-input",
                size="sm",
            ),
            html.Span("", id={"type": "ss-weight-badge", "attr": attr_id}, className="ss-weight-badge"),
        ],
        className="ss-attr-row",
        id={"type": "ss-attr-wrap", "attr": attr_id},
    )


def _attr_groups() -> list[html.Div]:
    by_group: dict[str, list] = {g: [] for g in _GROUP_ORDER}
    for attr in _ATTRS:
        group = str(attr.get("group") or "Other")
        by_group.setdefault(group, []).append(attr)
    cards = []
    for group in _GROUP_ORDER:
        items = by_group.get(group) or []
        if not items:
            continue
        cards.append(
            html.Div(
                [
                    html.Div(group, className="ss-group-title"),
                    html.Div([_attr_input(attr) for attr in items], className="ss-group-body"),
                ],
                className="ss-group-card",
            )
        )
    return cards


def layout(**_kwargs):
    return html.Div(
        [
            dcc.Store(id="ss-role", data=_DEFAULT_ROLE),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Staff", className="ss-kicker"),
                            *help_icon(PAGE_TIP, "ss-page-help"),
                        ],
                        className="ss-kicker-row",
                    ),
                    html.H1("Staff scores", className="ss-title"),
                    html.P(
                        "Weighted averages by role from the FM24 Pre-Game Editor attribute table.",
                        className="ss-sub",
                    ),
                ],
                className="ss-hero",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Attributes", className="ss-panel-title"),
                                    html.Div(
                                        [
                                            html.Button(
                                                "Clear",
                                                id="ss-clear",
                                                n_clicks=0,
                                                className="ss-btn ghost",
                                            ),
                                        ],
                                        className="ss-panel-actions",
                                    ),
                                ],
                                className="ss-panel-head",
                            ),
                            html.Div(_attr_groups(), className="ss-attr-grid"),
                        ],
                        className="ss-panel ss-inputs",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Role focus", className="ss-panel-title"),
                                    dmc.Select(
                                        id="ss-role-select",
                                        data=_role_options(),
                                        value=_DEFAULT_ROLE,
                                        searchable=True,
                                        clearable=False,
                                        className="ss-role-select",
                                        size="sm",
                                    ),
                                ],
                                className="ss-panel-head",
                            ),
                            html.Div(id="ss-focus-score", className="ss-focus"),
                            html.Div(_role_buttons(), className="ss-role-list"),
                            html.Div("Contribution", className="ss-section-label"),
                            html.Div(id="ss-breakdown", className="ss-breakdown"),
                        ],
                        className="ss-panel ss-results",
                    ),
                ],
                className="ss-layout",
            ),
        ],
        className="ss-page",
    )


def _fmt_score(score: float | None) -> str:
    if score is None:
        return "—"
    return f"{score:.2f}"


def _coverage_label(coverage: float, used: int, total: int) -> str:
    pct = int(round(coverage * 100))
    return f"{pct}% weight filled ({used}/{total})"


def _focus_block(result: dict) -> html.Div:
    score = result.get("score")
    return html.Div(
        [
            html.Div(result.get("label") or result.get("role_id"), className="ss-focus-role"),
            html.Div(_fmt_score(score), className="ss-focus-value"),
            html.Div(
                _coverage_label(
                    float(result.get("coverage") or 0),
                    int(result.get("used_weight") or 0),
                    int(result.get("total_weight") or 0),
                ),
                className="ss-focus-meta",
            ),
            html.Div(
                "score = Σ (attribute × weight) / Σ weights used",
                className="ss-formula",
            ),
        ]
    )


def _role_button(role: dict) -> html.Button:
    role_id = str(role["id"])
    active = " active" if role_id == _DEFAULT_ROLE else ""
    return html.Button(
        [
            html.Span(role["label"], className="ss-role-name"),
            html.Span(
                "—",
                id={"type": "ss-role-score", "role": role_id},
                className="ss-role-score",
            ),
            html.Span(
                "0%",
                id={"type": "ss-role-cov", "role": role_id},
                className="ss-role-cov",
            ),
        ],
        id={"type": "ss-role-pick", "role": role_id},
        n_clicks=0,
        className="ss-role-item" + active,
        title="Show contribution for this role",
    )


def _role_buttons() -> list:
    """Stable buttons so attribute edits don't remount the list and steal focus."""
    items = []
    for category, roles in _roles_by_category():
        items.append(html.Div(category, className="ss-role-cat"))
        items.extend(_role_button(role) for role in roles)
    return items


def _breakdown(result: dict) -> html.Div:
    rows = []
    for item in result.get("contributions") or []:
        filled = bool(item.get("filled"))
        value = item.get("value")
        product = item.get("product")
        rows.append(
            html.Div(
                [
                    html.Span(item.get("label") or item.get("id"), className="ss-bd-name"),
                    html.Span(f"×{item.get('weight')}", className="ss-bd-w"),
                    html.Span("—" if value is None else f"{value:g}", className="ss-bd-v"),
                    html.Span(
                        "—" if product is None else f"{product:g}",
                        className="ss-bd-p",
                    ),
                ],
                className="ss-bd-row" + ("" if filled else " missing"),
            )
        )
    if not rows:
        return html.Div("No weighted attributes for this role.", className="ss-empty")
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Attribute", className="ss-bd-name head"),
                    html.Span("W", className="ss-bd-w head"),
                    html.Span("Val", className="ss-bd-v head"),
                    html.Span("Prod", className="ss-bd-p head"),
                ],
                className="ss-bd-row head",
            ),
            *rows,
        ]
    )


def _weight_badges(role_id: str) -> list:
    weights = ss.role_weights(role_id)
    outs = []
    for attr in _ATTRS:
        attr_id = str(attr["id"])
        w = weights.get(attr_id)
        text = f"×{w}" if w else ""
        outs.append(text)
    return outs


def _wrap_classes(role_id: str) -> list:
    weights = ss.role_weights(role_id)
    outs = []
    for attr in _ATTRS:
        attr_id = str(attr["id"])
        cls = "ss-attr-row"
        if attr_id in weights:
            cls += " is-weighted"
            if weights[attr_id] >= 4:
                cls += " is-key"
            elif weights[attr_id] >= 3:
                cls += " is-strong"
        else:
            cls += " is-unused"
        outs.append(cls)
    return outs


@callback(
    Output("ss-role", "data"),
    Output("ss-role-select", "value"),
    Input({"type": "ss-role-pick", "role": ALL}, "n_clicks"),
    Input("ss-role-select", "value"),
    State("ss-role", "data"),
    prevent_initial_call=True,
)
def sync_role(n_clicks, select_value, current):
    trigger = ctx.triggered_id
    current = current or _DEFAULT_ROLE
    if isinstance(trigger, dict) and trigger.get("type") == "ss-role-pick":
        fired = ctx.triggered[0].get("value") if ctx.triggered else None
        if not fired:
            return no_update, no_update
        role_id = str(trigger.get("role") or "")
        if not role_id or role_id == current:
            return no_update, no_update
        return role_id, role_id
    if trigger == "ss-role-select" and select_value and select_value != current:
        return select_value, no_update
    return no_update, no_update


@callback(
    Output({"type": "ss-attr", "attr": ALL}, "value"),
    Input("ss-clear", "n_clicks"),
    State({"type": "ss-attr", "attr": ALL}, "id"),
    prevent_initial_call=True,
)
def clear_attrs(n_clicks, ids):
    if not n_clicks:
        return no_update
    return [1] * len(ids or [])


@callback(
    Output("ss-focus-score", "children"),
    Output("ss-breakdown", "children"),
    Output({"type": "ss-role-score", "role": ALL}, "children"),
    Output({"type": "ss-role-cov", "role": ALL}, "children"),
    Output({"type": "ss-role-pick", "role": ALL}, "className"),
    Output({"type": "ss-weight-badge", "attr": ALL}, "children"),
    Output({"type": "ss-attr-wrap", "attr": ALL}, "className"),
    Input({"type": "ss-attr", "attr": ALL}, "value"),
    Input("ss-role", "data"),
    State({"type": "ss-attr", "attr": ALL}, "id"),
)
def recompute(values, role_id, ids):
    role_id = role_id or _DEFAULT_ROLE
    attr_ids = [str(item.get("attr") or "") for item in (ids or [])]
    attrs = ss.attrs_from_lists(attr_ids, values or [])
    rows = ss.score_all_roles(attrs)
    by_id = {row["role_id"]: row for row in rows}
    focus = by_id.get(role_id) or ss.score_role(role_id, attrs)
    if "label" not in focus:
        focus["label"] = next(
            (r["label"] for r in _ROLES if r["id"] == role_id),
            role_id,
        )
    scores = []
    coverages = []
    classes = []
    for _category, roles in _roles_by_category():
        for role in roles:
            rid = str(role["id"])
            row = by_id.get(rid) or {}
            cov = float(row.get("coverage") or 0)
            scores.append(_fmt_score(row.get("score")))
            coverages.append(f"{int(round(cov * 100))}%")
            classes.append("ss-role-item" + (" active" if rid == role_id else ""))
    return (
        _focus_block(focus),
        _breakdown(focus),
        scores,
        coverages,
        classes,
        _weight_badges(role_id),
        _wrap_classes(role_id),
    )
