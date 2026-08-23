"""Squad finance page: Moneyball upload → matchday wage/fee statement."""
from __future__ import annotations

from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.scouting_shell import decode_upload, upload_card
from scoring.squad_finance import (
    DEFAULT_GAMES,
    DEFAULT_SEASON_GAMES,
    STARTERS,
    SUBS,
    club_sustainability,
    default_matchday_keys,
    format_money,
    load_squad_finance,
    matchday_statement,
)

register_page(__name__, path="/squad-finance", name="Squad finance")


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


def _money_field(field_id: str, label: str, *, placeholder: str = "0") -> html.Div:
    return html.Div(
        [
            html.Label(label, className="rs-field-label"),
            dmc.NumberInput(
                id=field_id,
                value=None,
                min=0,
                step=100_000,
                hideControls=False,
                thousandSeparator=",",
                allowDecimal=True,
                decimalScale=0,
                placeholder=placeholder,
                className="sf-number sf-number-wide",
            ),
        ],
        className="sf-field",
    )


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
        role = "Starter" if line["role"] == "starter" else "Sub"
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
                ]
            )
        )
    return html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(body)],
            className="sf-statement-table",
        ),
        className="sf-statement-wrap",
    )


def _sustainability_panel(sustain: dict) -> html.Div:
    ok = sustain["sustainable"]
    verdict = "Sustainable at current figures" if ok else "Not sustainable at current figures"
    tone = "best" if ok else "worst"
    return html.Div(
        [
            html.H3("Club sustainability", className="sf-subhead"),
            html.P(
                "Funds available = balance + prorated annual income − prorated other "
                "annual expenses. Compared with XVI wages + appearance fees.",
                className="sf-note",
            ),
            html.Div(
                [
                    _summary_card("Funds available", sustain["funds_available"]),
                    _summary_card(
                        "Surplus",
                        sustain["surplus"],
                        tone="best" if ok else "worst",
                    ),
                    _status_card("Verdict", verdict, tone=tone),
                ],
                className="sf-summary-row",
            ),
        ],
        className="sf-sustainability",
    )


def _empty_statement(message: str) -> html.Div:
    return html.Div(message, className="sf-empty")


def layout(**_kwargs):
    return dbc.Container(
        [
            dcc.Store(id="sf-rows", data=[]),
            html.H1("Squad finance", className="mt-2 mb-2"),
            html.P(
                "Upload a Moneyball player export with salary, FFP contribution, and "
                f"match fees, pick {STARTERS} starters (including a GK) and {SUBS} "
                "substitutes, then set how many games to model. Every selected player "
                "is assumed to appear in every game. Optionally enter club balance / "
                "income / expenses to check wage sustainability.",
                className="text-muted mb-3",
            ),
            upload_card(
                "sf",
                "1. Upload squad export",
                hint=html.P(
                    "Uses Salary, FFP Contribution, and Appearance Fee columns.",
                    className="text-muted small mb-0 mt-2",
                ),
            ),
            html.Div(
                [
                    dbc.Card(
                        [
                            dbc.CardHeader("2. Matchday squad"),
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Games",
                                                        className="rs-field-label",
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
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Season games (wage proration)",
                                                        className="rs-field-label",
                                                    ),
                                                    dmc.NumberInput(
                                                        id="sf-season-games",
                                                        value=DEFAULT_SEASON_GAMES,
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
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label(
                                                        f"Starters ({STARTERS})",
                                                        className="rs-field-label",
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
                                                    html.Label(
                                                        f"Substitutes ({SUBS})",
                                                        className="rs-field-label",
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
                                    html.Div(id="sf-selection-hint", className="sf-hint"),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            dbc.CardHeader("3. Club finances (optional)"),
                            dbc.CardBody(
                                [
                                    html.P(
                                        "Income and other expenses are annual figures, "
                                        "prorated by games / season games. Leave blank to "
                                        "skip the sustainability check.",
                                        className="sf-note",
                                    ),
                                    html.Div(
                                        [
                                            _money_field(
                                                "sf-balance",
                                                "Current balance",
                                                placeholder="e.g. 25000000",
                                            ),
                                            _money_field(
                                                "sf-income",
                                                "Annual club income",
                                                placeholder="e.g. 80000000",
                                            ),
                                            _money_field(
                                                "sf-expenses",
                                                "Annual other expenses",
                                                placeholder="excl. this XVI",
                                            ),
                                        ],
                                        className="sf-params-row",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            dbc.CardHeader("4. Financial statement"),
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
    Output("sf-rows", "data"),
    Output("sf-upload-status", "children"),
    Output("sf-upload-wrap", "hidden"),
    Output("sf-upload-replace-wrap", "hidden"),
    Output("sf-main", "hidden"),
    Input("sf-upload", "contents"),
    Input("sf-upload-replace", "contents"),
    State("sf-upload", "filename"),
    State("sf-upload-replace", "filename"),
    prevent_initial_call=True,
)
def on_upload(upload_contents, replace_contents, upload_name, replace_name):
    if ctx.triggered_id == "sf-upload-replace":
        contents, name = replace_contents, replace_name or "squad.csv"
    else:
        contents, name = upload_contents, upload_name or "squad.csv"
    if not contents:
        return no_update, no_update, no_update, no_update, no_update
    if not str(name).lower().endswith(".csv"):
        return (
            [],
            html.Div("Upload a Moneyball CSV export.", className="rs-upload-error"),
            False,
            True,
            True,
        )
    try:
        rows = load_squad_finance(decode_upload(contents))
    except Exception as exc:
        return (
            [],
            html.Div(str(exc), className="rs-upload-error"),
            False,
            True,
            True,
        )
    if not rows:
        return (
            [],
            html.Div("No players found in that file.", className="rs-upload-error"),
            False,
            True,
            True,
        )
    with_pay = sum(
        1
        for row in rows
        if row["salary"] or row["appearance_fee"] or row["ffp_contribution"]
    )
    gk_count = sum(1 for row in rows if row.get("is_gk"))
    status = [
        html.Span("✓", className="rs-upload-ok"),
        html.Span(f"{len(rows):,} players", className="rs-upload-count"),
        html.Span("·", className="rs-upload-sep"),
        html.Span(
            f"{with_pay:,} with salary/fees/FFP",
            className="rs-upload-count",
        ),
        html.Span("·", className="rs-upload-sep"),
        html.Span(f"{gk_count:,} GK", className="rs-upload-count"),
        html.Span("·", className="rs-upload-sep"),
        html.Span(name, className="rs-upload-name", title=name),
    ]
    return rows, status, True, False, False


@callback(
    Output("sf-starters", "data"),
    Output("sf-subs", "data"),
    Output("sf-starters", "value"),
    Output("sf-subs", "value"),
    Input("sf-rows", "data"),
)
def sync_player_options(rows):
    rows = rows or []
    options = _player_options(rows)
    starters, subs = default_matchday_keys(rows)
    return options, options, starters, subs


@callback(
    Output("sf-selection-hint", "children"),
    Output("sf-summary", "children"),
    Output("sf-statement", "children"),
    Input("sf-rows", "data"),
    Input("sf-starters", "value"),
    Input("sf-subs", "value"),
    Input("sf-games", "value"),
    Input("sf-season-games", "value"),
    Input("sf-balance", "value"),
    Input("sf-income", "value"),
    Input("sf-expenses", "value"),
)
def render_statement(
    rows, starters, subs, games, season_games, balance, income, expenses
):
    rows = rows or []
    starters = list(starters or [])
    subs = list(subs or [])
    by_key = {row["key"]: row for row in rows if row.get("key")}
    overlap = sorted(set(starters) & set(subs))
    starter_gks = sum(1 for key in starters if by_key.get(key, {}).get("is_gk"))
    hint_bits = [
        f"{len(starters)}/{STARTERS} starters",
        f"{len(subs)}/{SUBS} substitutes",
        f"{starter_gks} GK in starters",
    ]
    if overlap:
        hint_bits.append(f"{len(overlap)} listed in both — counted once as starters")
        subs = [key for key in subs if key not in set(starters)]
    if starter_gks < 1 and starters:
        hint_bits.append("add at least one GK to starters")
    hint = " · ".join(hint_bits)

    if len(starters) < STARTERS or len(subs) < SUBS:
        return (
            hint,
            [],
            _empty_statement(
                f"Select {STARTERS} starters and {SUBS} substitutes to build the statement."
            ),
        )

    games_n = int(games or DEFAULT_GAMES)
    season_n = int(season_games or DEFAULT_SEASON_GAMES)
    statement = matchday_statement(
        rows,
        starters,
        subs,
        games=games_n,
        season_games=season_n,
    )
    summary = [
        _summary_card(
            f"Wages ({statement['games']}/{statement['season_games']} games)",
            statement["wage_period"],
        ),
        _summary_card("FFP contribution (period)", statement["ffp_period"]),
        _summary_card("Appearance fees", statement["match_fees"]),
        _summary_card("Total", statement["total"], tone="best"),
    ]
    note = html.P(
        [
            "Every selected player is assumed to appear in every game "
            "(appearance fee × games). Totals are wages + appearance fees; "
            "FFP is shown separately and not added in. "
            "Goal / assist / clean-sheet bonuses are not included.",
        ],
        className="sf-note",
    )
    children: list = [note, _statement_table(statement)]

    has_club_inputs = any(v is not None and v != "" for v in (balance, income, expenses))
    if has_club_inputs:
        sustain = club_sustainability(
            balance=balance,
            annual_income=income,
            annual_expenses=expenses,
            squad_total=statement["total"],
            games=games_n,
            season_games=season_n,
        )
        children.append(_sustainability_panel(sustain))

    return hint, summary, html.Div(children)
