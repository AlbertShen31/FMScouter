"""Squad wage / match-fee financial statements from Moneyball exports.

Uses annual ``salary`` plus per-match ``appearance_fee`` for a fixed
matchday of 11 starters + 5 substitutes. Remaining players are **reserves**:
their wages are included, appearance fees are not.
``ffp_contribution`` is shown for reference but excluded from totals.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from scoring.role_scorer import (
    IDENTITY,
    extract_finance_fields,
    pick,
    player_row_key,
    sniff_delimiter,
    unique_headers,
)

STARTERS = 11
SUBS = 5
MATCHDAY = STARTERS + SUBS
DEFAULT_GAMES = 38
DEFAULT_SEASON_GAMES = 38
SUSTAINABILITY_YEARS = 5

# Club P&L category keys (values are absolute currency, not millions).
INCOME_CATEGORIES = (
    ("gate", "Gate receipts"),
    ("sponsors", "Sponsors / commercial"),
    ("prize", "Prize money"),
    ("transfers_in", "Transfer fees in"),
    ("other_income", "Other income"),
)
EXPENSE_CATEGORIES = (
    ("transfers_out", "Transfer fees out"),
    ("agent_fees", "Agent fees"),
    ("other_expenses", "Other expenses"),
)

_MONEY_TOKEN = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<suffix>[kmb])?\b",
    re.IGNORECASE,
)
_PERCENT_TOKEN = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)
_GK_TOKEN = re.compile(r"\bGK\b", re.IGNORECASE)

_CLAUSE_KEYS = (
    "yearly_salary_raise",
    "promotion_salary_raise",
    "top_division_promotion_salary_raise",
    "relegation_salary_drop",
    "top_division_relegation_salary_drop",
)


def parse_money(text: str | None) -> float | None:
    """Parse FM money strings like ``$21.07M p/a``, ``£68K``, ``1,250,000``."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw in {"-", "—", "N/A", "n/a"}:
        return None
    if " - " in raw or "–" in raw:
        low_s, high_s = re.split(r"\s*[-–]\s*", raw, maxsplit=1)
        low, high = parse_money(low_s), parse_money(high_s)
        if low is None and high is None:
            return None
        if low is None:
            return high
        if high is None:
            return low
        return (low + high) / 2.0

    cleaned = raw.replace(",", "")
    match = _MONEY_TOKEN.search(cleaned)
    if not match:
        return None
    number = float(match.group("num").replace(",", "."))
    suffix = (match.group("suffix") or "").lower()
    mult = {"": 1.0, "k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}[suffix]
    return number * mult


def parse_salary_clause(text: str | None) -> tuple[str, float] | None:
    """Parse a raise/drop clause as ``("pct", fraction)`` or ``("money", amount)``.

    Moneyball exports percentages like ``25%`` (of the player's annual salary)
    and absolute figures like ``$250K``. Percentages return a 0–1 fraction.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw in {"-", "—", "N/A", "n/a"}:
        return None
    pct_match = _PERCENT_TOKEN.search(raw.replace(",", ""))
    if pct_match:
        number = float(pct_match.group("num").replace(",", "."))
        return ("pct", number / 100.0)
    money = parse_money(raw)
    if money is None:
        return None
    return ("money", money)


def resolve_salary_clause(salary: float, text: str | None) -> dict[str, float | str | None]:
    """Turn a raw clause into an absolute annual $ amount (and kind metadata)."""
    raw = None if text is None else str(text).strip()
    if raw in {"", "-", "—", "N/A", "n/a"}:
        raw = None
    parsed = parse_salary_clause(raw)
    if not parsed:
        return {"amount": 0.0, "kind": None, "rate": 0.0, "raw": raw}
    kind, value = parsed
    salary = max(0.0, float(salary or 0))
    if kind == "pct":
        return {
            "amount": salary * value,
            "kind": "pct",
            "rate": value,
            "raw": raw,
        }
    return {"amount": float(value), "kind": "money", "rate": 0.0, "raw": raw}


def format_money(value: float | None, *, currency: str = "$") -> str:
    if value is None:
        return "—"
    amount = float(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000_000:
        body = f"{amount / 1_000_000_000:.2f}B"
    elif amount >= 1_000_000:
        body = f"{amount / 1_000_000:.2f}M"
    elif amount >= 1_000:
        body = f"{amount / 1_000:.1f}K"
    else:
        body = f"{amount:,.0f}"
    return f"{sign}{currency}{body}"


def format_signed_money(value: float | None, *, currency: str = "$") -> str:
    """Format a delta with an explicit + / − sign (zero → ``+$0``)."""
    if value is None:
        return "—"
    amount = float(value)
    if amount > 0:
        return f"+{format_money(amount, currency=currency)}"
    if amount < 0:
        return format_money(amount, currency=currency)
    return f"+{currency}0"


def is_gk_player(player: dict[str, Any]) -> bool:
    """True when Best Pos / Position mentions GK."""
    text = f"{player.get('best_pos') or ''} {player.get('position') or ''}"
    return bool(_GK_TOKEN.search(text))


def finance_row(player: dict[str, Any]) -> dict[str, Any]:
    """Normalize one parsed player into planning fields."""
    salary = parse_money(player.get("salary")) or 0.0
    appearance = parse_money(player.get("appearance_fee"))
    unused = parse_money(player.get("unused_sub_fee"))
    ffp = parse_money(player.get("ffp_contribution"))
    if unused is None:
        unused = appearance
    name = player.get("name") or "—"
    club = player.get("club") or "—"
    position = player.get("position") or player.get("best_pos") or "—"
    best_pos = player.get("best_pos") or ""
    row: dict[str, Any] = {
        "key": player_row_key({"Name": name, "Club": club}),
        "name": name,
        "club": club,
        "position": position,
        "best_pos": best_pos,
        "is_gk": is_gk_player({"position": position, "best_pos": best_pos}),
        "salary_raw": player.get("salary") or "—",
        "appearance_raw": player.get("appearance_fee") or "—",
        "unused_raw": player.get("unused_sub_fee") or "—",
        "ffp_raw": player.get("ffp_contribution") or "—",
        "salary": salary,
        "appearance_fee": appearance or 0.0,
        "unused_sub_fee": unused or 0.0,
        "ffp_contribution": ffp or 0.0,
        "transfer_value": player.get("transfer_value") or "—",
        "contract_expires": player.get("contract_expires") or "—",
    }
    for key in _CLAUSE_KEYS:
        resolved = resolve_salary_clause(salary, player.get(key))
        amount = float(resolved["amount"] or 0)
        row[key] = amount
        row[f"{key}_raw"] = resolved["raw"]
        row[f"{key}_kind"] = resolved["kind"]
        row[f"{key}_rate"] = float(resolved["rate"] or 0)
    return row


def squad_raise_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Sum resolved contract raise / drop $ amounts across the uploaded squad.

    Percent clauses are already converted to ``salary × rate`` in ``finance_row``.
    """
    return {
        "yearly": sum(float(row.get("yearly_salary_raise") or 0) for row in rows),
        "promotion": sum(float(row.get("promotion_salary_raise") or 0) for row in rows),
        "top_promotion": sum(
            float(row.get("top_division_promotion_salary_raise") or 0) for row in rows
        ),
        "relegation": sum(
            float(row.get("relegation_salary_drop") or 0) for row in rows
        ),
        "top_relegation": sum(
            float(row.get("top_division_relegation_salary_drop") or 0) for row in rows
        ),
    }


def player_wage_after_division(
    row: dict[str, Any], division_mode: str | None
) -> float:
    """Annual wage after a one-time promotion raise or relegation drop."""
    salary = max(0.0, float(row.get("salary") or 0))
    key = (division_mode or "none").strip().lower()
    if key == "promo_normal":
        salary += float(row.get("promotion_salary_raise") or 0)
    elif key == "promo_top":
        salary += float(row.get("top_division_promotion_salary_raise") or 0)
    elif key == "releg_normal":
        salary -= float(row.get("relegation_salary_drop") or 0)
    elif key == "releg_top":
        salary -= float(row.get("top_division_relegation_salary_drop") or 0)
    return max(0.0, salary)


def player_wage_for_year(
    row: dict[str, Any],
    year: int,
    *,
    division_mode: str | None = "none",
    apply_yearly_raises: bool = False,
) -> float:
    """Project one player's annual wage for season ``year`` (1-indexed).

    Division change applies from year 1. Yearly raises (when enabled) apply after
    each completed year: percentage clauses compound on the post-division wage;
    absolute clauses add a flat amount each year.
    """
    base = player_wage_after_division(row, division_mode)
    year = max(1, int(year or 1))
    if not apply_yearly_raises or year <= 1:
        return base
    steps = year - 1
    kind = row.get("yearly_salary_raise_kind")
    if kind == "pct":
        rate = float(row.get("yearly_salary_raise_rate") or 0)
        return max(0.0, base * ((1.0 + rate) ** steps))
    bump = float(row.get("yearly_salary_raise") or 0)
    return max(0.0, base + steps * bump)


def projected_annual_wages(
    rows: list[dict[str, Any]],
    *,
    years: int = SUSTAINABILITY_YEARS,
    division_mode: str | None = "none",
    apply_yearly_raises: bool = False,
) -> list[float]:
    """Squad wage bill for each projected season (length ``years``)."""
    years = max(1, int(years or 1))
    return [
        sum(
            player_wage_for_year(
                row,
                year,
                division_mode=division_mode,
                apply_yearly_raises=apply_yearly_raises,
            )
            for row in rows
        )
        for year in range(1, years + 1)
    ]


def player_wage_outlook(
    row: dict[str, Any],
    *,
    years: int = SUSTAINABILITY_YEARS,
    division_mode: str | None = "none",
    apply_yearly_raises: bool = False,
) -> list[float]:
    """Annual wages for one player over ``years`` seasons on the current contract."""
    years = max(1, int(years or 1))
    return [
        player_wage_for_year(
            row,
            year,
            division_mode=division_mode,
            apply_yearly_raises=apply_yearly_raises,
        )
        for year in range(1, years + 1)
    ]


def promotion_raise_for_mode(
    raises: dict[str, float], mode: str | None
) -> float:
    """Pick the promotion bump for ``none`` / ``normal`` / ``top``."""
    key = (mode or "none").strip().lower()
    if key in {"normal", "promotion", "promo_normal"}:
        return float(raises.get("promotion") or 0)
    if key in {"top", "top_tier", "top-tier", "promo_top"}:
        return float(raises.get("top_promotion") or 0)
    return 0.0


def relegation_drop_for_mode(
    raises: dict[str, float], mode: str | None
) -> float:
    """Pick the relegation wage cut for ``none`` / ``normal`` / ``top``."""
    key = (mode or "none").strip().lower()
    if key in {"normal", "relegation", "releg_normal"}:
        return float(raises.get("relegation") or 0)
    if key in {"top", "top_tier", "top-tier", "releg_top"}:
        return float(raises.get("top_relegation") or 0)
    return 0.0


def division_change_amounts(
    raises: dict[str, float], mode: str | None
) -> dict[str, float]:
    """Resolve a combined division-change mode into promo / relegation / net.

    Modes: ``none``, ``promo_normal``, ``promo_top``, ``releg_normal``, ``releg_top``.
    Net is ``promotion − relegation`` (positive = wage bill up).
    """
    key = (mode or "none").strip().lower()
    promo = 0.0
    releg = 0.0
    if key == "promo_normal":
        promo = float(raises.get("promotion") or 0)
    elif key == "promo_top":
        promo = float(raises.get("top_promotion") or 0)
    elif key == "releg_normal":
        releg = float(raises.get("relegation") or 0)
    elif key == "releg_top":
        releg = float(raises.get("top_relegation") or 0)
    return {
        "promotion": promo,
        "relegation": releg,
        "net": promo - releg,
    }


def load_squad_finance(text: str) -> list[dict[str, Any]]:
    """Parse a Moneyball CSV into finance rows (attrs not required)."""
    if not text or not text.strip():
        raise ValueError("The file is empty.")
    delim = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise ValueError("The file has no header row.") from exc
    header = unique_headers(raw_header)
    name_aliases = IDENTITY["Name"]
    bases = {h.split(".")[0] for h in header}
    if not any(alias in header or alias in bases for alias in name_aliases):
        raise ValueError("CSV must include a Name or Player column.")

    players: list[dict[str, Any]] = []
    for raw in reader:
        if not raw or all(not str(cell).strip() for cell in raw):
            continue
        if len(raw) < len(header):
            raw = list(raw) + [""] * (len(header) - len(raw))
        elif len(raw) > len(header):
            raw = raw[: len(header)]
        row = dict(zip(header, raw))
        name = pick(row, name_aliases)
        if not name:
            continue
        finance = extract_finance_fields(row)
        players.append(
            {
                "name": name,
                "club": pick(row, IDENTITY["Club"]),
                "position": pick(row, IDENTITY["Position"]),
                "best_pos": pick(row, IDENTITY["BestPos"]),
                **finance,
            }
        )
    if not players:
        raise ValueError("No player rows found. Check that the file is an FM CSV export.")
    rows = [finance_row(player) for player in players]
    rows.sort(key=lambda row: (-row["salary"], row["name"].casefold()))
    return rows


def default_matchday_keys(rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Highest-wage XVI with at least one GK among the 11 starters when available."""
    if not rows:
        return [], []

    gks = [row for row in rows if row.get("is_gk")]
    outfield = [row for row in rows if not row.get("is_gk")]

    starters: list[dict[str, Any]] = []
    if gks:
        starters.append(gks[0])

    for row in outfield:
        if len(starters) >= STARTERS:
            break
        starters.append(row)

    used = {row["key"] for row in starters}
    if len(starters) < STARTERS:
        for row in rows:
            if row["key"] in used:
                continue
            starters.append(row)
            used.add(row["key"])
            if len(starters) >= STARTERS:
                break

    starters = starters[:STARTERS]
    used = {row["key"] for row in starters}
    subs = [row for row in rows if row["key"] not in used][:SUBS]
    return [row["key"] for row in starters], [row["key"] for row in subs]


def restore_matchday_keys(
    rows: list[dict[str, Any]],
    starter_keys: list[str] | None,
    sub_keys: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Keep cached starters/subs when still present; pad gaps from defaults."""
    if not rows:
        return [], []
    keys = {row["key"] for row in rows if row.get("key")}
    starters = [key for key in (starter_keys or []) if key in keys][:STARTERS]
    starter_set = set(starters)
    subs = [
        key
        for key in (sub_keys or [])
        if key in keys and key not in starter_set
    ][:SUBS]
    if len(starters) == STARTERS and len(subs) == SUBS:
        return starters, subs
    if not starters and not subs:
        return default_matchday_keys(rows)

    used = set(starters) | set(subs)
    default_starters, default_subs = default_matchday_keys(rows)
    for key in default_starters + default_subs:
        if len(starters) >= STARTERS:
            break
        if key not in used:
            starters.append(key)
            used.add(key)
    for key in default_subs + default_starters:
        if len(subs) >= SUBS:
            break
        if key not in used:
            subs.append(key)
            used.add(key)
    for row in rows:
        if len(starters) >= STARTERS and len(subs) >= SUBS:
            break
        key = row.get("key")
        if not key or key in used:
            continue
        if len(starters) < STARTERS:
            starters.append(key)
            used.add(key)
        elif len(subs) < SUBS:
            subs.append(key)
            used.add(key)
    return starters[:STARTERS], subs[:SUBS]


def _index_by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in rows if row.get("key")}


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def club_sustainability(
    *,
    balance: float | None,
    income: dict[str, float | None] | None,
    expenses: dict[str, float | None] | None,
    squad_total: float,
    games: int,
    season_games: int,
    debt: float | None = None,
    debt_payments: float | None = None,
    years: int = SUSTAINABILITY_YEARS,
    squad_wage_period: float | None = None,
    apply_yearly_raises: bool = False,
    yearly_raise_total: float = 0.0,
    promotion_raise_total: float = 0.0,
    relegation_drop_total: float = 0.0,
    squad_wages_by_year: list[float] | None = None,
) -> dict[str, Any]:
    """Project club cash over ``years`` at today's annual income / expenses.

    Income and expense category values should already be absolute annual currency
    (not millions). ``squad_total`` is the modeled-period squad outlay and is
    annualized to a full season before the multi-year projection.

    ``debt`` is outstanding liability (stock). ``debt_payments`` is the annual
    debt service and is included in annual expenses. Closing position starts from
    ``balance − debt``.

    Optional wage scenarios (from Moneyball contract clauses):
    - ``promotion_raise_total`` is a one-time wage bump from year 1 onward.
    - ``relegation_drop_total`` is a one-time wage cut from year 1 onward
      (wages floored at zero before fees).
    - ``yearly_raise_total`` (when ``apply_yearly_raises``) adds after each
      completed year: year 1 = base (+ promo − relegation), year 2 = that + 1×
      raise, and so on. Adjustments apply to wages only; appearance fees stay flat.
    - Prefer ``squad_wages_by_year`` (absolute annual wages per season) when
      clauses are percentage-based so compounding stays per-player accurate.
    """
    years = max(1, int(years or SUSTAINABILITY_YEARS))
    games = max(0, int(games or 0))
    season_games = max(1, int(season_games or DEFAULT_SEASON_GAMES))
    bal = _as_float(balance)
    debt_bal = _as_float(debt)
    annual_debt_payments = _as_float(debt_payments)
    income = income or {}
    expenses = expenses or {}

    annual_income = sum(_as_float(income.get(key)) for key, _ in INCOME_CATEGORIES)
    annual_club_expenses = sum(
        _as_float(expenses.get(key)) for key, _ in EXPENSE_CATEGORIES
    )
    # Scale the modeled squad bill (statement total) up to a full season.
    scale = (season_games / games) if games > 0 else 0.0
    annual_squad_base = _as_float(squad_total) * scale
    if squad_wage_period is None:
        annual_wages_base = annual_squad_base
        annual_fees = 0.0
    else:
        annual_wages_base = _as_float(squad_wage_period) * scale
        annual_fees = max(0.0, annual_squad_base - annual_wages_base)

    promo = max(0.0, _as_float(promotion_raise_total))
    releg = max(0.0, _as_float(relegation_drop_total))
    yearly = (
        max(0.0, _as_float(yearly_raise_total)) if apply_yearly_raises else 0.0
    )
    projected = None
    if squad_wages_by_year:
        projected = [
            max(0.0, _as_float(v)) for v in list(squad_wages_by_year)[:years]
        ]
        while len(projected) < years:
            projected.append(projected[-1] if projected else annual_wages_base)

    def squad_for_year(year: int) -> float:
        # year is 1-indexed season number within the projection.
        if projected is not None:
            wages = projected[year - 1]
        else:
            wages = annual_wages_base + promo - releg + max(0, year - 1) * yearly
        return max(0.0, wages) + annual_fees

    opening_net = bal - debt_bal
    cash = bal
    remaining_debt = debt_bal
    timeline: list[dict[str, float | int]] = [
        {"year": 0, "balance": cash, "debt": remaining_debt}
    ]
    surplus = opening_net
    annual_squad = squad_for_year(1)
    annual_expenses = annual_club_expenses + annual_squad + annual_debt_payments
    annual_net = annual_income - annual_expenses
    annual_squad_final = annual_squad
    annual_expenses_final = annual_expenses

    for year in range(1, years + 1):
        squad_y = squad_for_year(year)
        expenses_y = annual_club_expenses + squad_y + annual_debt_payments
        net_y = annual_income - expenses_y
        if year == 1:
            annual_squad = squad_y
            annual_expenses = expenses_y
            annual_net = net_y
        if year == years:
            annual_squad_final = squad_y
            annual_expenses_final = expenses_y
        surplus += net_y
        cash = cash + net_y
        remaining_debt = max(0.0, remaining_debt - annual_debt_payments)
        timeline.append(
            {"year": year, "balance": cash, "debt": remaining_debt}
        )

    return {
        "balance": bal,
        "debt": debt_bal,
        "debt_payments": annual_debt_payments,
        "opening_net": opening_net,
        "years": years,
        "annual_income": annual_income,
        "annual_club_expenses": annual_club_expenses,
        "annual_expenses": annual_expenses,
        "annual_expenses_final": annual_expenses_final,
        "annual_squad": annual_squad,
        "annual_squad_final": annual_squad_final,
        "annual_net": annual_net,
        "surplus": surplus,
        "sustainable": surplus >= 0,
        "timeline": timeline,
        "apply_yearly_raises": bool(
            apply_yearly_raises
            and (
                yearly > 0
                or (
                    projected is not None
                    and len(projected) > 1
                    and abs(projected[-1] - projected[0]) >= 0.5
                )
            )
        ),
        "yearly_raise_total": yearly,
        "promotion_raise_total": promo,
        "relegation_drop_total": releg,
    }


def matchday_statement(
    rows: list[dict[str, Any]],
    starter_keys: list[str],
    sub_keys: list[str],
    *,
    games: int = DEFAULT_GAMES,
    season_games: int = DEFAULT_SEASON_GAMES,
) -> dict[str, Any]:
    """Build club outlay for starters + subs + reserves over ``games`` matches.

    - Starters and subs: wages + appearance fees (assumed to play every game).
    - Reserves (everyone else): wages only — no appearance fees.
    - Wages are annual figures prorated by ``games / season_games``.
    - FFP contribution is prorated for display only (not in totals).
    """
    games = max(0, int(games or 0))
    season_games = max(1, int(season_games or DEFAULT_SEASON_GAMES))
    by_key = _index_by_key(rows)

    starters = [by_key[key] for key in starter_keys if key in by_key][:STARTERS]
    starter_set = {player["key"] for player in starters}
    subs = [
        by_key[key]
        for key in sub_keys
        if key in by_key and key not in starter_set
    ][:SUBS]
    matchday = starters + subs
    matchday_keys = {player["key"] for player in matchday}
    reserves = [row for row in rows if row.get("key") and row["key"] not in matchday_keys]
    share = games / season_games

    def player_lines(
        players: list[dict[str, Any]], *, role: str, charge_fees: bool
    ) -> list[dict[str, Any]]:
        lines = []
        for player in players:
            wage_share = player["salary"] * share
            ffp_share = player["ffp_contribution"] * share
            fees = player["appearance_fee"] * games if charge_fees else 0.0
            lines.append(
                {
                    "role": role,
                    "key": player["key"],
                    "name": player["name"],
                    "position": player["position"],
                    "club": player["club"],
                    "is_gk": player["is_gk"],
                    "salary_annual": player["salary"],
                    "wage_period": wage_share,
                    "ffp_period": ffp_share,
                    "appearance_fee": player["appearance_fee"],
                    "unused_sub_fee": player["unused_sub_fee"],
                    "match_fees": fees,
                    "total": wage_share + fees,
                }
            )
        return lines

    lines = (
        player_lines(starters, role="starter", charge_fees=True)
        + player_lines(subs, role="sub", charge_fees=True)
        + player_lines(reserves, role="reserve", charge_fees=False)
    )

    matchday_wage = sum(player["salary"] for player in matchday) * share
    reserve_wage = sum(player["salary"] for player in reserves) * share
    wage_period = matchday_wage + reserve_wage
    ffp_period = sum(player["ffp_contribution"] for player in rows) * share
    match_fees = sum(player["appearance_fee"] * games for player in matchday)
    gk_starters = sum(1 for player in starters if player.get("is_gk"))

    return {
        "games": games,
        "season_games": season_games,
        "starters": len(starters),
        "subs": len(subs),
        "reserves": len(reserves),
        "gk_starters": gk_starters,
        "matchday_wage_period": matchday_wage,
        "reserve_wage_period": reserve_wage,
        "wage_period": wage_period,
        "ffp_period": ffp_period,
        "match_fees": match_fees,
        "total": wage_period + match_fees,
        "lines": lines,
    }
