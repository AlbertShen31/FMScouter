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
    parsed_historical_players,
    register_library_select_callbacks,
    register_upload_callbacks,
    shortlist_busy_overlay,
    upload_card,
)
from scoring.comparison import money_delta_span
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
    division_change_amounts,
    format_money,
    format_signed_money,
    load_squad_finance,
    matchday_statement,
    projected_annual_wages,
    player_wage_outlook,
    restore_matchday_keys,
    squad_raise_totals,
)

_DIVISION_MODE_BASE = (
    ("none", "No change"),
    ("promo_normal", "Promotion"),
    ("promo_top", "Top promo"),
    ("releg_normal", "Relegation"),
    ("releg_top", "Top releg"),
)
_DIVISION_MODE_OPTIONS = [
    {"value": value, "label": label} for value, label in _DIVISION_MODE_BASE
]
_PROJECTION_YEAR_OPTIONS = [
    {"value": "1", "label": "1"},
    {"value": str(SUSTAINABILITY_YEARS), "label": str(SUSTAINABILITY_YEARS)},
]
_PROJECTION_YEAR_CHOICES = {1, SUSTAINABILITY_YEARS}

register_page(__name__, path="/squad-finance", name="Squad finance")

register_upload_callbacks(
    "sf",
    parse_fn=load_squad_finance,
    pack_store=False,
    reveal_ids=["sf-main"],
    pulse_ids=["sf-main"],
    busy_ready_id="sf-statement",
    busy_ready_prop="children",
    bad_file_message="Upload a Moneyball player CSV export.",
    decode_strict=False,
    catch_exceptions=True,
)
register_library_select_callbacks(
    "sf",
    parse_fn=load_squad_finance,
    library_page="squad_finance",
    pack_store=False,
    reveal_ids=["sf-main"],
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
_WAGE_SCENARIO_IDS = [
    "sf-division-mode",
    "sf-projection-years",
]
_CLUB_PERSIST_IDS = [*_CLUB_FIELD_IDS, *_WAGE_SCENARIO_IDS]

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


def _money_cell(
    value: float | None,
    *,
    hist_value: float | None = None,
    compare: bool = False,
) -> html.Span:
    parts: list = [format_money(value)]
    if compare and value is not None and hist_value is not None:
        delta = money_delta_span(float(value) - float(hist_value), enabled=True)
        if delta is not None:
            parts.append(delta)
    return html.Span(parts, className="sf-money")


def _signed_delta(value: float | None) -> str | None:
    if value is None or abs(float(value)) < 0.5:
        return None
    return format_signed_money(value)


def _projection_years(value) -> int:
    try:
        years = int(value if value is not None else SUSTAINABILITY_YEARS)
    except (TypeError, ValueError):
        years = SUSTAINABILITY_YEARS
    if years in _PROJECTION_YEAR_CHOICES:
        return years
    # Legacy mid-range values → nearest allowed horizon.
    return 1 if years < 3 else SUSTAINABILITY_YEARS


def _pill_control(
    control_id: str,
    data: list[dict],
    *,
    value: str,
    class_name: str = "",
    full_width: bool = False,
) -> dmc.SegmentedControl:
    return dmc.SegmentedControl(
        id=control_id,
        data=data,
        value=value,
        fullWidth=full_width,
        size="sm",
        radius="xl",
        className=f"sf-pill-control {class_name}".strip(),
    )


def _migrate_division_mode(cached: dict | None) -> str:
    """Map legacy promo/releg fields onto the combined division-mode value."""
    cached = cached or {}
    if cached.get("division_mode"):
        return cached["division_mode"] or "none"
    promo = cached.get("promotion_mode") or "none"
    releg = cached.get("relegation_mode") or "none"
    if promo == "normal":
        return "promo_normal"
    if promo == "top":
        return "promo_top"
    if releg == "normal":
        return "releg_normal"
    if releg == "top":
        return "releg_top"
    return "none"


def _summary_card(
    title: str,
    value: float,
    *,
    tone: str = "",
    delta: float | None = None,
    compare: bool = False,
) -> html.Div:
    delta_txt = _signed_delta(delta) if not compare else None
    body = format_money(value)
    if compare and delta is not None and abs(float(delta)) >= 0.5:
        wage_delta = money_delta_span(float(delta), enabled=True)
        if wage_delta is not None:
            body_nodes: list = [body, wage_delta]
        else:
            body_nodes = [body]
    elif delta_txt:
        body = f"{body} ({delta_txt})"
        body_nodes = [body]
    else:
        body_nodes = [body]
    value_class = f"sf-summary-value{' is-' + tone if tone else ''}"
    if delta_txt and not compare:
        if float(delta or 0) > 0:
            value_class += " has-delta-up"
        elif float(delta or 0) < 0:
            value_class += " has-delta-down"
    return html.Div(
        [
            html.Div(title, className="sf-summary-label"),
            html.Div(body_nodes, className=value_class),
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


def _statement_table(
    statement: dict,
    *,
    rows_by_key: dict[str, dict] | None = None,
    hist_rows_by_key: dict[str, dict] | None = None,
    division_mode: str | None = "none",
    apply_yearly_raises: bool = False,
    outlook_years: int = SUSTAINABILITY_YEARS,
    hist_statement: dict | None = None,
    compare: bool = False,
) -> html.Div:
    years = max(1, int(outlook_years or SUSTAINABILITY_YEARS))
    header = html.Tr(
        [
            html.Th("Role"),
            html.Th("Player"),
            html.Th("Pos"),
            html.Th("Wage (period)"),
            html.Th("FFP (period)"),
            html.Th("Appearance fees"),
            html.Th("Total"),
            *[html.Th(f"Y{year}") for year in range(1, years + 1)],
        ]
    )
    body = []
    by_key = rows_by_key or {}
    hist_by_key = hist_rows_by_key or {}
    hist_lines = {
        line.get("key"): line for line in (hist_statement or {}).get("lines") or []
    }
    for line in statement.get("lines") or []:
        role = _ROLE_LABEL.get(line["role"], line["role"])
        name = line["name"]
        if line.get("is_gk"):
            name = f"{name} (GK)"
        player = by_key.get(line.get("key") or "")
        hist_line = hist_lines.get(line.get("key") or "")
        if player is None:
            outlook = [float(line.get("salary_annual") or 0)] * years
            hist_outlook = (
                [float(hist_line.get("salary_annual") or 0)] * years
                if hist_line
                else outlook
            )
        else:
            outlook = player_wage_outlook(
                player,
                years=years,
                division_mode=division_mode,
                apply_yearly_raises=apply_yearly_raises,
            )
            hist_player = hist_by_key.get(line.get("key") or "")
            if compare and hist_player:
                hist_outlook = player_wage_outlook(
                    hist_player,
                    years=years,
                    division_mode=division_mode,
                    apply_yearly_raises=apply_yearly_raises,
                )
            elif compare and hist_line:
                hist_outlook = [float(hist_line.get("salary_annual") or 0)] * years
            else:
                hist_outlook = outlook
        body.append(
            html.Tr(
                [
                    html.Td(role),
                    html.Td(name),
                    html.Td(line["position"]),
                    html.Td(
                        _money_cell(
                            line["wage_period"],
                            hist_value=(hist_line or {}).get("wage_period"),
                            compare=compare,
                        )
                    ),
                    html.Td(
                        _money_cell(
                            line["ffp_period"],
                            hist_value=(hist_line or {}).get("ffp_period"),
                            compare=compare,
                        )
                    ),
                    html.Td(
                        _money_cell(
                            line["match_fees"],
                            hist_value=(hist_line or {}).get("match_fees"),
                            compare=compare,
                        )
                    ),
                    html.Td(
                        _money_cell(
                            line["total"],
                            hist_value=(hist_line or {}).get("total"),
                            compare=compare,
                        )
                    ),
                    *[
                        html.Td(
                            _money_cell(
                                wage,
                                hist_value=hist_outlook[i]
                                if compare and i < len(hist_outlook)
                                else None,
                                compare=compare,
                            )
                        )
                        for i, wage in enumerate(outlook)
                    ],
                ],
                className=f"sf-row-{line['role']}",
            )
        )
    return html.Div(
        [
            html.P(
                f"Y1–Y{years} are expected annual salaries at the end of each "
                f"season if the player stays on this contract (division change plus "
                f"that year’s raise/drop applied).",
                className="sf-note sf-statement-outlook-note",
            ),
            html.Table(
                [html.Thead(header), html.Tbody(body)],
                className="sf-statement-table",
            ),
        ],
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
    scenario_bits: list[str] = []
    promo = float(sustain.get("promotion_raise_total") or 0)
    releg = float(sustain.get("relegation_drop_total") or 0)
    yearly = float(sustain.get("yearly_raise_total") or 0)
    wage_delta = promo - releg
    if promo > 0:
        scenario_bits.append(
            f"includes a one-time promotion wage bump of {format_money(promo)} from year 1"
        )
    if releg > 0:
        scenario_bits.append(
            f"includes a one-time relegation wage cut of {format_money(releg)} from year 1"
        )
    if sustain.get("apply_yearly_raises") and yearly > 0:
        scenario_bits.append(
            f"uses end-of-season wages including {format_money(yearly)} in "
            f"first-year raise effect (percent clauses compound each year; "
            f"cash clauses add flat)"
        )
    scenario_note = (
        (" Wage scenario: " + "; ".join(scenario_bits) + ".")
        if scenario_bits
        else ""
    )
    expense_label = "Year 1 expenses" if scenario_bits else "Annual expenses"
    # Year-1 expense delta vs an unadjusted squad bill (promo − releg only).
    expense_delta = wage_delta if abs(wage_delta) >= 0.5 else None
    cards = [
        _summary_card("Annual income", sustain["annual_income"]),
        _summary_card(
            expense_label,
            sustain["annual_expenses"],
            delta=expense_delta,
        ),
    ]
    if scenario_bits and abs(
        float(sustain.get("annual_expenses_final") or 0)
        - float(sustain.get("annual_expenses") or 0)
    ) > 0.5:
        cards.append(
            _summary_card(
                f"Year {years} expenses",
                sustain["annual_expenses_final"],
            )
        )
    cards.extend(
        [
            _summary_card(
                f"{years}-year surplus",
                sustain["surplus"],
                tone="best" if ok else "worst",
            ),
            _status_card("Verdict", verdict, tone=tone),
        ]
    )
    return html.Div(
        [
            html.H3("Club sustainability", className="sf-subhead"),
            html.P(
                f"Projects {years} years at today’s annual income and club expenses. "
                f"Expenses = club P&L (box 3) + debt payments + full-season "
                f"squad bill from the statement (box 4, scaled to {DEFAULT_SEASON_GAMES} "
                f"games). Closing position = (balance − debt) + sum of each year’s "
                f"(income − expenses).{scenario_note}",
                className="sf-note",
            ),
            html.Div(cards, className="sf-summary-row"),
            html.H4("Balance & debt outlook", className="sf-cat-head"),
            html.P(
                "Cash balance grows by each year’s net; outstanding debt falls "
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
                library_page="squad_finance",
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
                                                            "for the selected projection "
                                                            "horizon."
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
                                        "Enter annual figures in millions (e.g. 25.5). "
                                        "Income and expenses are held constant over the "
                                        "selected years. Leave blank to skip the "
                                        "sustainability check.",
                                        className="sf-note",
                                    ),
                                    html.Div(
                                        [
                                            html.H4(
                                                "Wage scenario",
                                                className="sf-cat-head",
                                            ),
                                            html.P(
                                                "Uses division-change and Yearly Salary "
                                                "Raise columns from the Moneyball export. "
                                                "Projected Y1–Yn salaries are end-of-season "
                                                "figures after raises and drops.",
                                                className="sf-note sf-note-tight",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            _field_label(
                                                                "Division change",
                                                                tip=(
                                                                    "One season outcome only — "
                                                                    "promotion or relegation "
                                                                    "from year 1 (not both). "
                                                                    "Percent clauses are of "
                                                                    "each player’s annual "
                                                                    "salary; cash clauses are "
                                                                    "absolute. Appearance fees "
                                                                    "are unchanged."
                                                                ),
                                                                help_id="sf-help-division",
                                                            ),
                                                            _pill_control(
                                                                "sf-division-mode",
                                                                _DIVISION_MODE_OPTIONS,
                                                                value="none",
                                                                class_name="sf-division-pills",
                                                                full_width=True,
                                                            ),
                                                        ],
                                                        className="sf-scenario-item",
                                                    ),
                                                    html.Div(
                                                        [
                                                            _field_label(
                                                                "Years",
                                                                tip=(
                                                                    "Projection length for "
                                                                    "expected player salaries "
                                                                    "and club sustainability "
                                                                    f"(1 or {SUSTAINABILITY_YEARS}). "
                                                                    "Each Yn column is the "
                                                                    "salary at the end of that "
                                                                    "season after division "
                                                                    "change and yearly raises."
                                                                ),
                                                                help_id="sf-help-projection-years",
                                                            ),
                                                            _pill_control(
                                                                "sf-projection-years",
                                                                _PROJECTION_YEAR_OPTIONS,
                                                                value=str(
                                                                    SUSTAINABILITY_YEARS
                                                                ),
                                                                class_name="sf-years-pills",
                                                            ),
                                                        ],
                                                        className="sf-scenario-item",
                                                    ),
                                                ],
                                                className="sf-scenario-stack",
                                            ),
                                        ],
                                        className="sf-club-block",
                                    ),
                                    html.Div(
                                        [
                                            html.H4(
                                                "Opening position",
                                                className="sf-cat-head",
                                            ),
                                            html.Div(
                                                [
                                                    _money_field(
                                                        "sf-balance",
                                                        "Current balance ($M)",
                                                        tip=(
                                                            "Opening cash on hand, "
                                                            "in millions."
                                                        ),
                                                        help_id="sf-help-balance",
                                                        placeholder="e.g. 25.5",
                                                    ),
                                                    _money_field(
                                                        "sf-debt",
                                                        "Outstanding debt ($M)",
                                                        tip=(
                                                            "Total club debt outstanding. "
                                                            "Subtracted from balance for the "
                                                            "opening position of the "
                                                            "projection."
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
                                                            "for the selected years. Included "
                                                            "in annual expenses."
                                                        ),
                                                        help_id="sf-help-debt-payments",
                                                        placeholder="e.g. 5.0",
                                                    ),
                                                ],
                                                className="sf-params-row sf-params-row-tight",
                                            ),
                                        ],
                                        className="sf-club-block",
                                    ),
                                    html.Div(
                                        [
                                            html.H4("Income", className="sf-cat-head"),
                                            _category_fields(
                                                "sf-income",
                                                INCOME_CATEGORIES,
                                                tip_suffix=(
                                                    "Annual amount at today’s rate "
                                                    "(held for the selected years)."
                                                ),
                                            ),
                                        ],
                                        className="sf-club-block",
                                    ),
                                    html.Div(
                                        [
                                            html.H4("Expenses", className="sf-cat-head"),
                                            _category_fields(
                                                "sf-expense",
                                                EXPENSE_CATEGORIES,
                                                tip_suffix=(
                                                    "Annual amount excluding squad wages "
                                                    "and appearance fees (already modeled "
                                                    "above)."
                                                ),
                                            ),
                                        ],
                                        className="sf-club-block sf-club-block-last",
                                    ),
                                ],
                                className="sf-club-body",
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
                    shortlist_busy_overlay("sf"),
                ],
                id="sf-main",
                className="rs-shortlist-busy-host",
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


def _club_payload(
    balance,
    debt,
    debt_payments,
    *category_values,
    division_mode="none",
    projection_years=SUSTAINABILITY_YEARS,
):
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
        "yearly_raises": True,
        "division_mode": (division_mode or "none"),
        "projection_years": _projection_years(projection_years),
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
        _migrate_division_mode(cached),
        str(_projection_years(cached.get("projection_years"))),
    )


def _club_has_values(cached: dict | None) -> bool:
    if not cached:
        return False
    values = _club_values(cached)
    # Money fields only — wage toggles alone shouldn't block remount wipe.
    money = values[: -len(_WAGE_SCENARIO_IDS)]
    return any(v is not None and v != "" for v in money)


@callback(
    Output("sf-club", "data"),
    *[Input(field_id, "value") for field_id in _CLUB_FIELD_IDS],
    Input("sf-division-mode", "value"),
    Input("sf-projection-years", "value"),
    State("sf-club", "data"),
    prevent_initial_call=True,
)
def persist_club_finances(*args):
    *field_values, division_mode, projection_years, cached = args
    payload = _club_payload(
        *field_values,
        division_mode=division_mode,
        projection_years=projection_years,
    )
    # NumberInputs remount empty before hydrate; keep prior session values.
    if not _club_has_values(payload) and _club_has_values(cached):
        # Still allow wage-scenario-only updates when money fields remount empty.
        if ctx.triggered_id in {
            "sf-division-mode",
            "sf-projection-years",
        }:
            cached = cached or {}
            return {
                **cached,
                "yearly_raises": True,
                "division_mode": division_mode or "none",
                "projection_years": _projection_years(projection_years),
            }
        return no_update
    return payload


@callback(
    *[Output(field_id, "value") for field_id in _CLUB_FIELD_IDS],
    Output("sf-division-mode", "value"),
    Output("sf-projection-years", "value"),
    Input("sf-hydrate-tick", "n_intervals"),
    State("sf-club", "data"),
)
def hydrate_club_finances(_tick, cached):
    if not cached:
        return tuple(no_update for _ in _CLUB_PERSIST_IDS)
    values = _club_values(cached)
    wage_only = (
        not _club_has_values(cached)
        and _migrate_division_mode(cached) == "none"
        and _projection_years(cached.get("projection_years")) == SUSTAINABILITY_YEARS
    )
    if wage_only:
        return tuple(no_update for _ in _CLUB_PERSIST_IDS)
    return values


def _hist_money_delta(current: float | None, hist: dict | None, key: str) -> float | None:
    if hist is None:
        return None
    return float(current or 0) - float(hist.get(key) or 0)


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
    Input("sf-division-mode", "value"),
    Input("sf-projection-years", "value"),
    Input("sf-parsed-historical", "data"),
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
    hist_parsed = rest[-2] if len(rest) >= 2 else None
    projection_years = _projection_years(rest[-3] if len(rest) >= 3 else SUSTAINABILITY_YEARS)
    division_mode = rest[-4] if len(rest) >= 4 else "none"
    category_values = rest[:-4] if len(rest) >= 4 else rest
    compare = bool(parsed_historical_players(hist_parsed))
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
    hist_rows = parsed_historical_players(hist_parsed) if compare else []
    hist_by_key = {row["key"]: row for row in hist_rows if row.get("key")}
    hist_statement = None
    if compare and hist_rows:
        hist_statement = matchday_statement(
            hist_rows,
            starters,
            subs,
            games=games_n,
            season_games=DEFAULT_SEASON_GAMES,
        )
    raises = squad_raise_totals(rows)
    division = division_change_amounts(raises, division_mode)
    # Period-scaled wage delta (fees unchanged) for summary parentheses.
    period_delta = division["net"] * (games_n / DEFAULT_SEASON_GAMES)
    wage_adjusted = statement["wage_period"] + period_delta
    total_adjusted = statement["total"] + period_delta
    show_delta = abs(period_delta) >= 0.5 and not compare

    if compare and hist_statement:
        summary = [
            _summary_card(
                "Matchday wages",
                statement["matchday_wage_period"],
                delta=_hist_money_delta(
                    statement["matchday_wage_period"],
                    hist_statement,
                    "matchday_wage_period",
                ),
                compare=True,
            ),
            _summary_card(
                f"Reserve wages ({statement['reserves']})",
                statement["reserve_wage_period"],
                delta=_hist_money_delta(
                    statement["reserve_wage_period"],
                    hist_statement,
                    "reserve_wage_period",
                ),
                compare=True,
            ),
            _summary_card(
                "Squad wages",
                statement["wage_period"],
                delta=_hist_money_delta(
                    statement["wage_period"], hist_statement, "wage_period"
                ),
                compare=True,
            ),
            _summary_card(
                "Appearance fees",
                statement["match_fees"],
                delta=_hist_money_delta(
                    statement["match_fees"], hist_statement, "match_fees"
                ),
                compare=True,
            ),
            _summary_card(
                "FFP (period)",
                statement["ffp_period"],
                delta=_hist_money_delta(
                    statement["ffp_period"], hist_statement, "ffp_period"
                ),
                compare=True,
            ),
            _summary_card(
                "Total",
                statement["total"],
                tone="best",
                delta=_hist_money_delta(statement["total"], hist_statement, "total"),
                compare=True,
            ),
        ]
    else:
        summary = [
            _summary_card("Matchday wages", statement["matchday_wage_period"]),
            _summary_card(
                f"Reserve wages ({statement['reserves']})",
                statement["reserve_wage_period"],
            ),
            _summary_card(
                "Squad wages",
                wage_adjusted if show_delta else statement["wage_period"],
                delta=period_delta if show_delta else None,
            ),
            _summary_card("Appearance fees", statement["match_fees"]),
            _summary_card("FFP (period)", statement["ffp_period"]),
            _summary_card(
                "Total",
                total_adjusted if show_delta else statement["total"],
                tone="best",
                delta=period_delta if show_delta else None,
            ),
        ]
    note_bits = [
        "Matchday starters and substitutes are assumed to appear in every game "
        "(appearance fee × games). Reserves include wages only — no appearance fees. "
        f"Wages are prorated by games / {DEFAULT_SEASON_GAMES}. "
        "Totals are all wages + matchday appearance fees; FFP is display-only."
    ]
    if show_delta:
        kind = "promotion" if period_delta > 0 else "relegation"
        note_bits.append(
            f" Squad wages and total include the selected {kind} adjustment "
            f"({format_signed_money(period_delta)} for this period)."
        )
    if compare and hist_statement:
        note_bits.append(
            " Green ↓ / red ↑ in parentheses compare this export to the historical "
            "upload (same starters and subs)."
        )
    note = html.P(note_bits, className="sf-note")
    children: list = [
        note,
        _collapsible(
            "Player wage details",
            _statement_table(
                statement,
                rows_by_key={row["key"]: row for row in rows if row.get("key")},
                hist_rows_by_key=hist_by_key,
                division_mode=division_mode,
                apply_yearly_raises=True,
                outlook_years=projection_years,
                hist_statement=hist_statement,
                compare=compare and bool(hist_statement),
            ),
            hint=(
                f"Period costs plus Y1–Y{projection_years} expected annual "
                "salary under Wage scenario filters"
            ),
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
            squad_wage_period=statement["wage_period"],
            games=games_n,
            season_games=DEFAULT_SEASON_GAMES,
            years=projection_years,
            apply_yearly_raises=True,
            yearly_raise_total=raises["yearly"],
            promotion_raise_total=division["promotion"],
            relegation_drop_total=division["relegation"],
            squad_wages_by_year=projected_annual_wages(
                rows,
                years=projection_years,
                division_mode=division_mode,
                apply_yearly_raises=True,
            ),
        )
        children.append(_sustainability_panel(sustain, theme))

    return hint, summary, html.Div(children)
