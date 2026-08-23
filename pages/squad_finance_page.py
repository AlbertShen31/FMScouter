"""Squad finance page: Moneyball upload → matchday wage/fee statement."""
from __future__ import annotations

from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import plotly.graph_objects as go

from components.pack_picker import section_card_header
from components.player_filters import help_icon
from components.scouting_shell import (
    parsed_players,
    register_upload_callbacks,
    upload_card,
)
from scoring.squad_finance import (
    DEFAULT_GAMES,
    DEFAULT_SEASON_GAMES,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    STARTERS,
    SUBS,
    SUSTAINABILITY_YEARS,
    club_sustainability,
    default_matchday_keys,
    format_money,
    load_squad_finance,
    matchday_statement,
    restore_matchday_keys,
)

register_page(__name__, path="/squad-finance", name="Squad finance")

register_upload_callbacks(
    "sf",
    parse_fn=load_squad_finance,
    pack_store=False,
    reveal_ids=["sf-main"],
    pulse_ids=["sf-main"],
    bad_file_message="Upload a Moneyball player CSV export.",
    decode_strict=False,
    catch_exceptions=True,
)

_ROLE_LABEL = {
    "starter": "Starter",
    "sub": "Sub",
    "reserve": "Reserve",
}

_INCOME_IDS = [f"sf-income-{key}" for key, _ in INCOME_CATEGORIES]
_EXPENSE_IDS = [f"sf-expense-{key}" for key, _ in EXPENSE_CATEGORIES]
_CLUB_FIELD_IDS = [
    "sf-balance",
    "sf-debt",
    "sf-debt-payments",
    *_INCOME_IDS,
    *_EXPENSE_IDS,
]

_CHART_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "staticPlot": False,
    "scrollZoom": False,
    "doubleClick": False,
    "showAxisDragHandles": False,
    "showAxisRangeEntryBoxes": False,
    "edits": {
        "shapePosition": False,
        "annotationPosition": False,
    },
}


def _to_millions(value: float) -> float:
    return float(value or 0.0) / 1_000_000.0


def _projection_figure(sustain: dict, theme: str | None) -> go.Figure:
    """Balance (green) and debt (red filled) from now through the projection horizon."""
    dark = (theme or "dark") != "light"
    timeline = list(sustain.get("timeline") or [])
    if not timeline:
        years = int(sustain.get("years") or SUSTAINABILITY_YEARS)
        timeline = [
            {
                "year": year,
                "balance": float(sustain.get("balance") or 0)
                + year * float(sustain.get("annual_net") or 0),
                "debt": max(
                    0.0,
                    float(sustain.get("debt") or 0)
                    - year * float(sustain.get("debt_payments") or 0),
                ),
            }
            for year in range(years + 1)
        ]

    labels = ["Now" if point["year"] == 0 else f"Year {point['year']}" for point in timeline]
    balances = [_to_millions(point["balance"]) for point in timeline]
    debts = [_to_millions(point["debt"]) for point in timeline]
    font = "#e8eef6" if dark else "#0f172a"
    muted = "#8b9bb0" if dark else "#64748b"
    grid = "rgba(139, 155, 176, 0.22)" if dark else "rgba(100, 116, 139, 0.25)"
    green = "#22c55e"
    red = "#ef4444"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=debts,
            name="Debt",
            mode="lines",
            line=dict(color=red, width=2.5, shape="linear"),
            fill="tozeroy",
            fillcolor="rgba(239, 68, 68, 0.28)",
            hovertemplate="Debt: $%{y:.1f}M<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=balances,
            name="Balance",
            mode="lines+markers",
            line=dict(color=green, width=3, shape="linear"),
            marker=dict(size=7, color=green),
            fill="tozeroy",
            fillcolor="rgba(34, 197, 94, 0.28)" if dark else "rgba(34, 197, 94, 0.22)",
            hovertemplate="Balance: $%{y:.1f}M<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=font, size=13, family="Inter, Segoe UI, sans-serif"),
        margin=dict(l=56, r=24, t=12, b=44),
        height=320,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        dragmode=False,
        hoverlabel=dict(
            bgcolor="#1a2430" if dark else "#ffffff",
            bordercolor="#4a6078" if dark else "#c5d0de",
            font=dict(
                color=font,
                size=13,
                family="Inter, Segoe UI, sans-serif",
            ),
            align="left",
        ),
        xaxis=dict(
            title=None,
            showgrid=False,
            fixedrange=True,
            tickfont=dict(color=muted, size=12),
        ),
        yaxis=dict(
            title="Millions ($)",
            zeroline=True,
            zerolinecolor=grid,
            zerolinewidth=1,
            gridcolor=grid,
            fixedrange=True,
            tickfont=dict(color=muted, size=12),
            tickformat=".1f",
            separatethousands=True,
        ),
    )
    return fig


def _help(tip: str, help_id: str) -> list:
    return help_icon(tip, help_id)


def _field_label(text: str, *, tip: str | None = None, help_id: str | None = None) -> html.Div:
    parts: list = [html.Span(text, className="rs-field-label")]
    if tip:
        parts.extend(_help(tip, help_id or f"sf-help-{text.lower().replace(' ', '-')}"))
    return html.Div(parts, className="rs-field-label-row")


def _player_options(rows: list[dict]) -> list[dict]:
    options = []
    for row in rows:
        salary = format_money(row.get("salary"))
        gk = " · GK" if row.get("is_gk") else ""
        label = f"{row['name']}{gk} · {row.get('position') or '—'} · {salary}/yr"
        options.append({"value": row["key"], "label": label})
    return options


def _money_cell(value: float | None) -> html.Span:
    return html.Span(format_money(value), className="sf-money")


def _summary_card(title: str, value: float, *, tone: str = "") -> html.Div:
    return html.Div(
        [
            html.Div(title, className="sf-summary-label"),
            html.Div(
                format_money(value),
                className=f"sf-summary-value{' is-' + tone if tone else ''}",
            ),
        ],
        className="sf-summary-card",
    )


def _status_card(title: str, body: str, *, tone: str = "") -> html.Div:
    return html.Div(
        [
            html.Div(title, className="sf-summary-label"),
            html.Div(
                body,
                className=(
                    f"sf-summary-value sf-status-value"
                    f"{' is-' + tone if tone else ''}"
                ),
            ),
        ],
        className="sf-summary-card",
    )


def _money_field(
    field_id: str,
    label: str,
    *,
    tip: str,
    help_id: str,
    placeholder: str = "0",
) -> html.Div:
    return html.Div(
        [
            _field_label(label, tip=tip, help_id=help_id),
            dmc.NumberInput(
                id=field_id,
                value=None,
                min=0,
                step=0.1,
                hideControls=False,
                thousandSeparator=",",
                allowDecimal=True,
                decimalScale=1,
                fixedDecimalScale=False,
                placeholder=placeholder,
                className="sf-number sf-number-wide",
            ),
        ],
        className="sf-field",
    )


def _millions_to_cash(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value) * 1_000_000.0
    except (TypeError, ValueError):
        return None


def _category_fields(
    prefix: str,
    categories: tuple[tuple[str, str], ...],
    *,
    tip_suffix: str,
) -> html.Div:
    fields = [
        _money_field(
            f"{prefix}-{key}",
            f"{label} ($M)",
            tip=f"{label} for the season, in millions. {tip_suffix}",
            help_id=f"sf-help-{prefix}-{key}",
            placeholder="e.g. 10.5",
        )
        for key, label in categories
    ]
    return html.Div(fields, className="sf-params-row")


def _statement_table(statement: dict) -> html.Div:
    header = html.Tr(
        [
            html.Th("Role"),
            html.Th("Player"),
            html.Th("Pos"),
            html.Th("Wage (period)"),
            html.Th("FFP (period)"),
            html.Th("Appearance fees"),
            html.Th("Total"),
        ]
    )
    body = []
    for line in statement.get("lines") or []:
        role = _ROLE_LABEL.get(line["role"], line["role"])
        name = line["name"]
        if line.get("is_gk"):
            name = f"{name} (GK)"
        body.append(
            html.Tr(
                [
                    html.Td(role),
                    html.Td(name),
                    html.Td(line["position"]),
                    html.Td(_money_cell(line["wage_period"])),
                    html.Td(_money_cell(line["ffp_period"])),
                    html.Td(_money_cell(line["match_fees"])),
                    html.Td(_money_cell(line["total"])),
                ],
                className=f"sf-row-{line['role']}",
            )
        )
    return html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(body)],
            className="sf-statement-table",
        ),
        className="sf-statement-wrap",
    )


def _sustainability_panel(sustain: dict, theme: str | None = None) -> html.Div:
    years = int(sustain.get("years") or SUSTAINABILITY_YEARS)
    ok = sustain["sustainable"]
    verdict = (
        f"Sustainable over {years} years"
        if ok
        else f"Not sustainable over {years} years"
    )
    tone = "best" if ok else "worst"
    return html.Div(
        [
            html.H3("Club sustainability", className="sf-subhead"),
            html.P(
                f"Projects {years} years at today’s annual income and expenses. "
                f"Annual expenses = club P&L (box 3) + debt payments + full-season "
                f"squad bill from the statement (box 4, scaled to {DEFAULT_SEASON_GAMES} "
                f"games). Closing position = (balance − debt) + {years} × "
                f"(income − expenses).",
                className="sf-note",
            ),
            html.Div(
                [
                    _summary_card("Annual income", sustain["annual_income"]),
                    _summary_card("Annual expenses", sustain["annual_expenses"]),
                    _summary_card(
                        f"{years}-year surplus",
                        sustain["surplus"],
                        tone="best" if ok else "worst",
                    ),
                    _status_card("Verdict", verdict, tone=tone),
                ],
                className="sf-summary-row",
            ),
            html.H4("Balance & debt outlook", className="sf-cat-head"),
            html.P(
                "Cash balance grows by annual net each year; outstanding debt falls "
                "by annual debt payments (floored at zero).",
                className="sf-note",
            ),
            dcc.Graph(
                figure=_projection_figure(sustain, theme),
                config=_CHART_CONFIG,
                className="sf-projection-chart",
            ),
        ],
        className="sf-sustainability",
    )


def _collapsible(
    title: str,
    *body,
    hint: str | None = None,
) -> html.Details:
    """Closed-by-default disclosure block (matches Role scores metrics details)."""
    copy: list = [html.Span(title, className="sf-details-summary-text")]
    if hint:
        copy.append(html.Span(hint, className="sf-details-summary-hint"))
    return html.Details(
        [
            html.Summary(
                html.Div(copy, className="sf-details-summary-copy"),
                className="sf-details-summary-row",
            ),
            html.Div(list(body), className="sf-details-body"),
        ],
        className="sf-details",
    )


def _empty_statement(message: str) -> html.Div:
    return html.Div(message, className="sf-empty")


def layout(**_kwargs):
    return dbc.Container(
        [
            dcc.Interval(id="sf-hydrate-tick", interval=50, max_intervals=1),
            html.H1("Squad finance", className="mt-2 mb-2"),
            html.P(
                "Upload a Moneyball player export with salary and match fees, pick "
                f"{STARTERS} starters (including a GK) and {SUBS} substitutes, then set "
                "how many games to model. Matchday players include appearance fees; "
                "everyone else is treated as a reserve (wages only). Optionally enter "
                "club finances by category in millions.",
                className="text-muted mb-3",
            ),
            upload_card(
                "sf",
                "1. Upload squad export",
                upload_label=html.Div(["Drag a CSV here, or ", html.A("browse")]),
                hint=html.P(
                    "Uses Salary, Appearance Fee, and FFP Contribution columns. "
                    "FFP is shown for reference and is not included in totals.",
                    className="text-muted small mb-0 mt-2",
                ),
                include_data_rev=False,
            ),
            html.Div(
                [
                    dbc.Card(
                        [
                            section_card_header("2. Matchday squad"),
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    _field_label(
                                                        "Games",
                                                        tip=(
                                                            "Matches to model. Appearance "
                                                            "fees use this count; wages are "
                                                            "prorated against a "
                                                            f"{DEFAULT_SEASON_GAMES}-game season. "
                                                            "Club income/expenses stay annual "
                                                            f"for the {SUSTAINABILITY_YEARS}-year "
                                                            "verdict."
                                                        ),
                                                        help_id="sf-help-games",
                                                    ),
                                                    dmc.NumberInput(
                                                        id="sf-games",
                                                        value=DEFAULT_GAMES,
                                                        min=1,
                                                        max=100,
                                                        step=1,
                                                        hideControls=False,
                                                        className="sf-number",
                                                    ),
                                                ],
                                                className="sf-field",
                                            ),
                                        ],
                                        className="sf-params-row",
                                    ),
                                    html.Div(id="sf-selection-hint", className="sf-hint"),
                                    _collapsible(
                                        "Starters & substitutes",
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        _field_label(
                                                            f"Starters ({STARTERS})",
                                                            tip=(
                                                                "Defaults include the highest-wage "
                                                                "GK when available. Selection is "
                                                                "kept in session cache across refresh."
                                                            ),
                                                            help_id="sf-help-starters",
                                                        ),
                                                        dmc.MultiSelect(
                                                            id="sf-starters",
                                                            data=[],
                                                            value=[],
                                                            placeholder=(
                                                                "Select 11 starters (incl. GK)"
                                                            ),
                                                            searchable=True,
                                                            clearable=True,
                                                            maxValues=STARTERS,
                                                            className="sf-multiselect",
                                                        ),
                                                    ],
                                                    className="sf-field sf-field-grow",
                                                ),
                                                html.Div(
                                                    [
                                                        _field_label(
                                                            f"Substitutes ({SUBS})",
                                                            tip=(
                                                                "Bench players charged appearance "
                                                                "fees for every game. Remaining "
                                                                "squad players become reserves."
                                                            ),
                                                            help_id="sf-help-subs",
                                                        ),
                                                        dmc.MultiSelect(
                                                            id="sf-subs",
                                                            data=[],
                                                            value=[],
                                                            placeholder="Select 5 substitutes",
                                                            searchable=True,
                                                            clearable=True,
                                                            maxValues=SUBS,
                                                            className="sf-multiselect",
                                                        ),
                                                    ],
                                                    className="sf-field sf-field-grow",
                                                ),
                                            ],
                                            className="sf-select-row",
                                        ),
                                        hint=(
                                            f"Pick {STARTERS} starters (incl. GK) and "
                                            f"{SUBS} substitutes"
                                        ),
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            section_card_header("3. Club finances (optional)"),
                            dbc.CardBody(
                                [
                                    html.P(
                                        f"Enter annual figures in millions (one decimal, "
                                        f"e.g. 25.5). The verdict holds today’s income and "
                                        f"expenses constant for {SUSTAINABILITY_YEARS} years. "
                                        "Leave blank to skip the sustainability check.",
                                        className="sf-note",
                                    ),
                                    _money_field(
                                        "sf-balance",
                                        "Current balance ($M)",
                                        tip="Opening cash on hand, in millions.",
                                        help_id="sf-help-balance",
                                        placeholder="e.g. 25.5",
                                    ),
                                    html.H4("Debt", className="sf-cat-head"),
                                    html.Div(
                                        [
                                            _money_field(
                                                "sf-debt",
                                                "Outstanding debt ($M)",
                                                tip=(
                                                    "Total club debt outstanding. "
                                                    "Subtracted from balance for the "
                                                    f"{SUSTAINABILITY_YEARS}-year opening "
                                                    "position."
                                                ),
                                                help_id="sf-help-debt",
                                                placeholder="e.g. 40.0",
                                            ),
                                            _money_field(
                                                "sf-debt-payments",
                                                "Annual debt payments ($M)",
                                                tip=(
                                                    "Yearly debt service (interest + "
                                                    "principal) at today’s rate, held "
                                                    f"for {SUSTAINABILITY_YEARS} years. "
                                                    "Included in annual expenses."
                                                ),
                                                help_id="sf-help-debt-payments",
                                                placeholder="e.g. 5.0",
                                            ),
                                        ],
                                        className="sf-params-row",
                                    ),
                                    html.H4("Income", className="sf-cat-head"),
                                    _category_fields(
                                        "sf-income",
                                        INCOME_CATEGORIES,
                                        tip_suffix=(
                                            "Annual amount at today’s rate "
                                            f"(held for {SUSTAINABILITY_YEARS} years)."
                                        ),
                                    ),
                                    html.H4("Expenses", className="sf-cat-head"),
                                    _category_fields(
                                        "sf-expense",
                                        EXPENSE_CATEGORIES,
                                        tip_suffix=(
                                            "Annual amount excluding squad wages and "
                                            "appearance fees (already modeled above)."
                                        ),
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            section_card_header("4. Financial statement"),
                            dbc.CardBody(
                                [
                                    html.Div(id="sf-summary", className="sf-summary-row"),
                                    html.Div(id="sf-statement"),
                                ]
                            ),
                        ],
                        className="mb-4 rs-section-card",
                    ),
                ],
                id="sf-main",
                hidden=True,
            ),
        ],
        fluid=True,
        className="sf-page",
    )


@callback(
    Output("sf-selection", "data"),
    Input("sf-data-rev", "data"),
    State("sf-parsed", "data"),
    prevent_initial_call=True,
)
def reset_selection_on_replace(rev, parsed):
    """Wage defaults after Replace file — app-layout IDs only."""
    if not (isinstance(rev, dict) and rev.get("replaced")):
        return no_update
    rows = parsed_players(parsed)
    if not rows:
        return {"starters": [], "subs": []}
    starters, subs = default_matchday_keys(rows)
    return {"starters": starters, "subs": subs}


@callback(
    Output("sf-starters", "data"),
    Output("sf-subs", "data"),
    Output("sf-starters", "value"),
    Output("sf-subs", "value"),
    Input("sf-parsed", "data"),
    Input("sf-selection", "data"),
    Input("sf-hydrate-tick", "n_intervals"),
)
def sync_player_options(parsed, cached, _tick):
    """Page Multiselects only — safe with page-local hydrate tick."""
    rows = parsed_players(parsed)
    options = _player_options(rows)
    if not rows:
        return no_update, no_update, no_update, no_update
    cached = cached or {}
    starters, subs = restore_matchday_keys(
        rows,
        cached.get("starters"),
        cached.get("subs"),
    )
    return options, options, starters, subs


@callback(
    Output("sf-selection", "data", allow_duplicate=True),
    Input("sf-starters", "value"),
    Input("sf-subs", "value"),
    State("sf-selection", "data"),
    prevent_initial_call=True,
)
def persist_selection(starters, subs, cached):
    if ctx.triggered_id not in {"sf-starters", "sf-subs"}:
        return no_update
    starters = list(starters or [])
    subs = list(subs or [])
    cached = cached or {}
    # Multiselect remounts empty before hydrate; don't wipe a good cache.
    if not starters and not subs and (cached.get("starters") or cached.get("subs")):
        return no_update
    return {
        **cached,
        "starters": starters,
        "subs": subs,
    }


def _club_payload(balance, debt, debt_payments, *category_values):
    n_income = len(_INCOME_IDS)
    income_vals = list(category_values[:n_income])
    expense_vals = list(category_values[n_income : n_income + len(_EXPENSE_IDS)])
    return {
        "balance": balance,
        "debt": debt,
        "debt_payments": debt_payments,
        "income": {
            key: val for (key, _), val in zip(INCOME_CATEGORIES, income_vals)
        },
        "expenses": {
            key: val for (key, _), val in zip(EXPENSE_CATEGORIES, expense_vals)
        },
    }


def _club_values(cached: dict | None) -> tuple:
    cached = cached or {}
    income = cached.get("income") or {}
    expenses = cached.get("expenses") or {}
    return (
        cached.get("balance"),
        cached.get("debt"),
        cached.get("debt_payments"),
        *[income.get(key) for key, _ in INCOME_CATEGORIES],
        *[expenses.get(key) for key, _ in EXPENSE_CATEGORIES],
    )


def _club_has_values(cached: dict | None) -> bool:
    if not cached:
        return False
    values = _club_values(cached)
    return any(v is not None and v != "" for v in values)


@callback(
    Output("sf-club", "data"),
    *[Input(field_id, "value") for field_id in _CLUB_FIELD_IDS],
    State("sf-club", "data"),
    prevent_initial_call=True,
)
def persist_club_finances(*args):
    *field_values, cached = args
    payload = _club_payload(*field_values)
    # NumberInputs remount empty before hydrate; keep prior session values.
    if not _club_has_values(payload) and _club_has_values(cached):
        return no_update
    return payload


@callback(
    *[Output(field_id, "value") for field_id in _CLUB_FIELD_IDS],
    Input("sf-hydrate-tick", "n_intervals"),
    State("sf-club", "data"),
)
def hydrate_club_finances(_tick, cached):
    if not _club_has_values(cached):
        return tuple(no_update for _ in _CLUB_FIELD_IDS)
    return _club_values(cached)


_RENDER_INPUTS = [
    Input("sf-parsed", "data"),
    Input("sf-starters", "value"),
    Input("sf-subs", "value"),
    Input("sf-games", "value"),
    Input("sf-balance", "value"),
    Input("sf-debt", "value"),
    Input("sf-debt-payments", "value"),
    *[Input(field_id, "value") for field_id in _INCOME_IDS],
    *[Input(field_id, "value") for field_id in _EXPENSE_IDS],
    Input("theme", "data"),
]


@callback(
    Output("sf-selection-hint", "children"),
    Output("sf-summary", "children"),
    Output("sf-statement", "children"),
    *_RENDER_INPUTS,
)
def render_statement(
    parsed,
    starters,
    subs,
    games,
    balance,
    debt,
    debt_payments,
    *rest,
):
    theme = rest[-1] if rest else "dark"
    category_values = rest[:-1]
    rows = parsed_players(parsed)
    starters = list(starters or [])
    subs = list(subs or [])
    by_key = {row["key"]: row for row in rows if row.get("key")}
    overlap = sorted(set(starters) & set(subs))
    starter_gks = sum(1 for key in starters if by_key.get(key, {}).get("is_gk"))

    n_income = len(_INCOME_IDS)
    income_vals = list(category_values[:n_income])
    expense_vals = list(category_values[n_income : n_income + len(_EXPENSE_IDS)])
    income_map = {
        key: _millions_to_cash(val)
        for (key, _), val in zip(INCOME_CATEGORIES, income_vals)
    }
    expense_map = {
        key: _millions_to_cash(val)
        for (key, _), val in zip(EXPENSE_CATEGORIES, expense_vals)
    }

    reserve_count = max(0, len(rows) - len(set(starters) | set(subs)))
    hint_bits = [
        f"{len(starters)}/{STARTERS} starters",
        f"{len(subs)}/{SUBS} substitutes",
        f"{starter_gks} GK in starters",
    ]
    if overlap:
        hint_bits.append(f"{len(overlap)} listed in both — counted once as starters")
        subs = [key for key in subs if key not in set(starters)]
        reserve_count = max(0, len(rows) - len(set(starters) | set(subs)))
    if starter_gks < 1 and starters:
        hint_bits.append("add at least one GK to starters")
    if rows:
        hint_bits.append(f"{reserve_count} reserves")
    hint = " · ".join(hint_bits)

    if not rows:
        return hint, [], _empty_statement("Upload a squad export to build the statement.")

    if len(starters) < STARTERS or len(subs) < SUBS:
        return (
            hint,
            [],
            _empty_statement(
                f"Select {STARTERS} starters and {SUBS} substitutes to build the statement."
            ),
        )

    games_n = int(games or DEFAULT_GAMES)
    statement = matchday_statement(
        rows,
        starters,
        subs,
        games=games_n,
        season_games=DEFAULT_SEASON_GAMES,
    )
    summary = [
        _summary_card("Matchday wages", statement["matchday_wage_period"]),
        _summary_card(
            f"Reserve wages ({statement['reserves']})",
            statement["reserve_wage_period"],
        ),
        _summary_card("Appearance fees", statement["match_fees"]),
        _summary_card("FFP (period)", statement["ffp_period"]),
        _summary_card("Total", statement["total"], tone="best"),
    ]
    note = html.P(
        [
            "Matchday starters and substitutes are assumed to appear in every game "
            "(appearance fee × games). Reserves include wages only — no appearance fees. "
            f"Wages are prorated by games / {DEFAULT_SEASON_GAMES}. "
            "Totals are all wages + matchday appearance fees; FFP is display-only.",
        ],
        className="sf-note",
    )
    children: list = [
        note,
        _collapsible(
            "Player wage details",
            _statement_table(statement),
            hint="Starter, substitute, and reserve lines",
        ),
    ]

    club_values = [balance, debt, debt_payments, *income_vals, *expense_vals]
    if any(v is not None and v != "" for v in club_values):
        sustain = club_sustainability(
            balance=_millions_to_cash(balance),
            debt=_millions_to_cash(debt),
            debt_payments=_millions_to_cash(debt_payments),
            income=income_map,
            expenses=expense_map,
            squad_total=statement["total"],
            games=games_n,
            season_games=DEFAULT_SEASON_GAMES,
        )
        children.append(_sustainability_panel(sustain, theme))

    return hint, summary, html.Div(children)
