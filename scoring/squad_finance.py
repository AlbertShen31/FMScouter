"""Squad wage / match-fee financial statements from Moneyball exports.

Uses annual ``salary`` plus per-match ``appearance_fee`` /
``unused_sub_fee`` for a fixed matchday of 11 starters + 5 substitutes.
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

_MONEY_TOKEN = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<suffix>[kmb])?\b",
    re.IGNORECASE,
)
_GK_TOKEN = re.compile(r"\bGK\b", re.IGNORECASE)


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


def is_gk_player(player: dict[str, Any]) -> bool:
    """True when Best Pos / Position mentions GK."""
    text = f"{player.get('best_pos') or ''} {player.get('position') or ''}"
    return bool(_GK_TOKEN.search(text))


def finance_row(player: dict[str, Any]) -> dict[str, Any]:
    """Normalize one parsed player into planning fields."""
    salary = parse_money(player.get("salary"))
    appearance = parse_money(player.get("appearance_fee"))
    unused = parse_money(player.get("unused_sub_fee"))
    ffp = parse_money(player.get("ffp_contribution"))
    if unused is None:
        unused = appearance
    name = player.get("name") or "—"
    club = player.get("club") or "—"
    position = player.get("position") or player.get("best_pos") or "—"
    best_pos = player.get("best_pos") or ""
    return {
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
        "salary": salary or 0.0,
        "appearance_fee": appearance or 0.0,
        "unused_sub_fee": unused or 0.0,
        "ffp_contribution": ffp or 0.0,
        "transfer_value": player.get("transfer_value") or "—",
        "contract_expires": player.get("contract_expires") or "—",
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
    annual_income: float | None,
    annual_expenses: float | None,
    squad_total: float,
    games: int,
    season_games: int,
) -> dict[str, Any]:
    """Compare opening balance + prorated P&L against squad outlay.

    ``annual_expenses`` should be other club costs (not the modeled XVI wages/fees).
    """
    games = max(0, int(games or 0))
    season_games = max(1, int(season_games or DEFAULT_SEASON_GAMES))
    share = games / season_games
    bal = _as_float(balance)
    income_period = _as_float(annual_income) * share
    expenses_period = _as_float(annual_expenses) * share
    funds = bal + income_period - expenses_period
    surplus = funds - squad_total
    return {
        "balance": bal,
        "income_period": income_period,
        "expenses_period": expenses_period,
        "funds_available": funds,
        "squad_total": squad_total,
        "surplus": surplus,
        "sustainable": surplus >= 0,
    }


def matchday_statement(
    rows: list[dict[str, Any]],
    starter_keys: list[str],
    sub_keys: list[str],
    *,
    games: int = DEFAULT_GAMES,
    season_games: int = DEFAULT_SEASON_GAMES,
) -> dict[str, Any]:
    """Build club outlay for 11 starters + 5 subs over ``games`` matches.

    Every selected player is assumed to appear in every game (appearance fee).
    Wages are annual figures prorated by ``games / season_games``.
    FFP contribution is prorated for display only (not in totals).
    """
    games = max(0, int(games or 0))
    season_games = max(1, int(season_games or DEFAULT_SEASON_GAMES))
    by_key = _index_by_key(rows)

    starters = [by_key[key] for key in starter_keys if key in by_key][:STARTERS]
    subs = [by_key[key] for key in sub_keys if key in by_key][:SUBS]
    squad = starters + subs
    share = games / season_games

    wage_annual = sum(player["salary"] for player in squad)
    wage_period = wage_annual * share
    ffp_annual = sum(player["ffp_contribution"] for player in squad)
    ffp_period = ffp_annual * share

    match_fees = sum(player["appearance_fee"] * games for player in squad)

    def player_lines(players: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
        lines = []
        for player in players:
            wage_share = player["salary"] * share
            ffp_share = player["ffp_contribution"] * share
            fees = player["appearance_fee"] * games
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

    lines = player_lines(starters, role="starter") + player_lines(subs, role="sub")
    gk_starters = sum(1 for player in starters if player.get("is_gk"))

    return {
        "games": games,
        "season_games": season_games,
        "starters": len(starters),
        "subs": len(subs),
        "gk_starters": gk_starters,
        "wage_annual": wage_annual,
        "wage_period": wage_period,
        "ffp_annual": ffp_annual,
        "ffp_period": ffp_period,
        "match_fees": match_fees,
        "total": wage_period + match_fees,
        "lines": lines,
    }
