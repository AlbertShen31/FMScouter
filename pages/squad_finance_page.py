"""Squad finance page: Moneyball upload → matchday wage/fee statement."""
from __future__ import annotations

from dash import Input, Output, State, callback, dcc, html, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

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
    STARTERS,
    SUBS,
    club_sustainability,
    default_matchday_keys,
    format_money,
    load_squad_finance,
    matchday_statement,
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


def _money_field(field_id: str, label: str, *, tip: str, help_id: str, placeholder: str = "0") -> html.Div:
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
    """Club finance inputs are in millions; convert to currency units."""
    if value is None or value == "":
        return None
    try:
        return float(value) * 1_000_000.0
    except (TypeError, ValueError):
        return None


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
    verdict = (
        "Sustainable at current figures"
        if ok
        else "Not sustainable at current figures"
    )
    tone = "best" if ok else "worst"
    return html.Div(
        [
            html.H3("Club sustainability", className="sf-subhead"),
            html.P(
                "Funds available = balance + prorated annual income − prorated other "
                f"annual expenses (club figures entered in $M, wages prorated by games / "
                f"{DEFAULT_SEASON_GAMES}). Compared with XVI wages + appearance fees.",
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
            dcc.Interval(id="sf-hydrate-tick", interval=50, max_intervals=1),
            html.H1("Squad finance", className="mt-2 mb-2"),
            html.P(
                "Upload a Moneyball player export with salary and match fees, pick "
                f"{STARTERS} starters (including a GK) and {SUBS} substitutes, then set "
                "how many games to model. Every selected player is assumed to appear in "
                "every game. Optionally enter club balance / income / expenses in millions "
                "to check wage sustainability.",
                className="text-muted mb-3",
            ),
            upload_card(
                "sf",
                "1. Upload squad export",
                upload_label=html.Div(
                    ["Drag a CSV here, or ", html.A("browse")]
                ),
                hint=html.P(
                    "Uses Salary, Appearance Fee, and FFP Contribution columns. "
                    "FFP is shown for reference and is not included in totals.",
                    className="text-muted small mb-0 mt-2",
                ),
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
                                                            "fees use this count; wages and "
                                                            f"optional club P&L are prorated "
                                                            f"against a {DEFAULT_SEASON_GAMES}-game "
                                                            "season."
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
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    _field_label(
                                                        f"Starters ({STARTERS})",
                                                        tip=(
                                                            "Defaults include the highest-"
                                                            "wage GK when one is present "
                                                            "in the export."
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
                                                            "Bench players are also assumed "
                                                            "to appear in every game for "
                                                            "fee planning."
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
                                    html.Div(id="sf-selection-hint", className="sf-hint"),
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
                                        f"Enter figures in millions (one decimal, e.g. 25.5). "
                                        f"Annual income / expenses are prorated by games / "
                                        f"{DEFAULT_SEASON_GAMES}. Leave blank to skip the "
                                        "sustainability check.",
                                        className="sf-note",
                                    ),
                                    html.Div(
                                        [
                                            _money_field(
                                                "sf-balance",
                                                "Current balance ($M)",
                                                tip="Cash on hand, in millions.",
                                                help_id="sf-help-balance",
                                                placeholder="e.g. 25.5",
                                            ),
                                            _money_field(
                                                "sf-income",
                                                "Annual club income ($M)",
                                                tip=(
                                                    "Gate, commercial, prize money, and "
                                                    "other annual income in millions — "
                                                    "prorated over the modeled games."
                                                ),
                                                help_id="sf-help-income",
                                                placeholder="e.g. 80.0",
                                            ),
                                            _money_field(
                                                "sf-expenses",
                                                "Annual other expenses ($M)",
                                                tip=(
                                                    "Other annual club costs in millions, "
                                                    "excluding this XVI’s wages and "
                                                    "appearance fees."
                                                ),
                                                help_id="sf-help-expenses",
                                                placeholder="e.g. 40.0",
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
    Output("sf-starters", "data"),
    Output("sf-subs", "data"),
    Output("sf-starters", "value"),
    Output("sf-subs", "value"),
    Input("sf-parsed", "data"),
    Input("sf-data-rev", "data"),
)
def sync_player_options(parsed, _rev):
    rows = parsed_players(parsed)
    options = _player_options(rows)
    starters, subs = default_matchday_keys(rows)
    return options, options, starters, subs


@callback(
    Output("sf-selection-hint", "children"),
    Output("sf-summary", "children"),
    Output("sf-statement", "children"),
    Input("sf-parsed", "data"),
    Input("sf-starters", "value"),
    Input("sf-subs", "value"),
    Input("sf-games", "value"),
    Input("sf-balance", "value"),
    Input("sf-income", "value"),
    Input("sf-expenses", "value"),
)
def render_statement(parsed, starters, subs, games, balance, income, expenses):
    rows = parsed_players(parsed)
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
        _summary_card(
            f"Wages ({statement['games']} games)",
            statement["wage_period"],
        ),
        _summary_card("FFP contribution (period)", statement["ffp_period"]),
        _summary_card("Appearance fees", statement["match_fees"]),
        _summary_card("Total", statement["total"], tone="best"),
    ]
    note = html.P(
        [
            "Every selected player is assumed to appear in every game "
            "(appearance fee × games). Wages are annual salary prorated by "
            f"games / {DEFAULT_SEASON_GAMES}. Totals are wages + appearance fees; "
            "FFP is shown separately and not added in. "
            "Goal / assist / clean-sheet bonuses are not included.",
        ],
        className="sf-note",
    )
    children: list = [note, _statement_table(statement)]

    has_club_inputs = any(v is not None and v != "" for v in (balance, income, expenses))
    if has_club_inputs:
        sustain = club_sustainability(
            balance=_millions_to_cash(balance),
            annual_income=_millions_to_cash(income),
            annual_expenses=_millions_to_cash(expenses),
            squad_total=statement["total"],
            games=games_n,
            season_games=DEFAULT_SEASON_GAMES,
        )
        children.append(_sustainability_panel(sustain))

    return hint, summary, html.Div(children)
