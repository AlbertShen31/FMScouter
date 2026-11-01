"""Squad wage parsing, contract projection, and matchday statements."""
from __future__ import annotations

from datetime import date

import pytest

import scoring.squad_finance as sf


def _row(
    name: str,
    salary: str,
    *,
    uid: str | None = None,
    position: str = "M (C)",
    best_pos: str = "MC",
    appearance: str = "$1K",
    expires: str | None = None,
    **clauses: str,
) -> dict:
    player = {
        "name": name,
        "unique_id": uid or name,
        "club": "City",
        "position": position,
        "best_pos": best_pos,
        "salary": salary,
        "appearance_fee": appearance,
    }
    if expires:
        player["contract_expires"] = expires
    player.update(clauses)
    return sf.finance_row(player)


def test_parse_money_suffixes_ranges_and_missing():
    assert sf.parse_money("$21.07M p/a") == pytest.approx(21_070_000)
    assert sf.parse_money("£68K") == pytest.approx(68_000)
    assert sf.parse_money("1,250,000") == pytest.approx(1_250_000)
    assert sf.parse_money("$1K - $9K") == pytest.approx(5_000)
    assert sf.parse_money("N/A") == 0.0
    assert sf.parse_money("-") is None
    assert sf.parse_money(None) is None
    assert sf.parse_money_bounds("$2M – $4M") == (2_000_000.0, 4_000_000.0)


def test_salary_period_detect_and_convert():
    assert sf.detect_salary_period("$10K p/w") == "weekly"
    assert sf.detect_salary_period("€8K per month") == "monthly"
    assert sf.detect_salary_period("$100K p/a") == "annual"
    assert sf.salary_to_annual(1_000, "weekly") == 52_000
    assert sf.salary_from_annual(12_000, "monthly") == 1_000
    assert sf.normalize_salary_period("WEEKLY") == "weekly"
    assert sf.normalize_salary_period("hourly") == "annual"
    assert sf.money_currency_symbol("£80K p/w") == "£"
    labels = {item["value"] for item in sf.salary_period_options()}
    assert labels == {"annual", "monthly", "weekly"}


def test_salary_clauses_percent_and_money():
    assert sf.parse_salary_clause("25%") == ("pct", 0.25)
    assert sf.parse_salary_clause("$250K") == ("money", 250_000.0)
    assert sf.parse_salary_clause("n/a") is None
    resolved = sf.resolve_salary_clause(200_000, "10%")
    assert resolved["kind"] == "pct"
    assert resolved["amount"] == pytest.approx(20_000)
    assert resolved["rate"] == pytest.approx(0.10)
    flat = sf.resolve_salary_clause(200_000, "$15K")
    assert flat == {"amount": 15_000.0, "kind": "money", "rate": 0.0, "raw": "$15K"}


def test_contract_expires_and_season_coverage():
    assert sf.parse_contract_expires("6/30/2030") == date(2030, 6, 30)
    assert sf.parse_contract_expires("2031-06-30") == date(2031, 6, 30)
    assert sf.parse_contract_expires("31/7/2029") == date(2029, 7, 31)
    assert sf.parse_contract_expires("-") is None
    assert sf.season_end_date(
        season_calendar="jul_jun", current_season_year=2028, year=1
    ) == date(2029, 6, 30)
    assert sf.season_end_date(
        season_calendar="jan_dec", current_season_year=2028, year=2
    ) == date(2029, 12, 31)
    row = {"contract_expires_date": "2029-06-30"}
    assert sf.contract_covers_season(
        row, season_calendar="jul_jun", current_season_year=2028, year=1
    )
    assert not sf.contract_covers_season(
        row, season_calendar="jul_jun", current_season_year=2028, year=2
    )
    assert sf.contract_covers_season(row, year=3)  # no season year → keep


def test_format_money_and_gk_flag():
    assert sf.format_money(1_500_000) == "$1.50M"
    assert sf.format_money(-2_500) == "-$2.5K"
    assert sf.format_signed_money(0) == "+$0"
    assert sf.format_signed_money(1_000) == "+$1.0K"
    assert sf.format_salary_for_period(52_000, period="weekly") == "$1.0K"
    assert sf.is_gk_player({"best_pos": "GK", "position": "GK"})
    assert not sf.is_gk_player({"best_pos": "MC", "position": "M (C)"})


def test_finance_row_resolves_clauses_and_wage_paths():
    row = _row(
        "Ada",
        "$100K p/a",
        expires="6/30/2030",
        yearly_salary_raise="10%",
        promotion_salary_raise="$20K",
        top_division_promotion_salary_raise="$50K",
        relegation_salary_drop="15%",
        top_division_relegation_salary_drop="$30K",
    )
    assert row["key"] == "Ada|Ada"
    assert row["salary"] == pytest.approx(100_000)
    assert row["yearly_salary_raise_kind"] == "pct"
    assert row["yearly_salary_raise"] == pytest.approx(10_000)
    assert row["is_gk"] is False
    assert sf.player_wage_after_division(row, "promo_normal") == pytest.approx(120_000)
    assert sf.player_wage_after_division(row, "promo_top") == pytest.approx(150_000)
    assert sf.player_wage_after_division(row, "releg_normal") == pytest.approx(85_000)
    assert sf.player_wage_after_division(row, "releg_top") == pytest.approx(70_000)
    assert sf.player_wage_for_year(row, 1, apply_yearly_raises=True) == pytest.approx(110_000)
    assert sf.player_wage_for_year(row, 2, apply_yearly_raises=True) == pytest.approx(121_000)
    expired = sf.player_wage_for_year(
        row,
        5,
        apply_yearly_raises=True,
        season_calendar="jul_jun",
        current_season_year=2028,
    )
    assert expired == 0.0


def test_projected_wages_fees_and_division_modes():
    ada = _row("Ada", "$100K p/a", appearance="$2K", yearly_salary_raise="$5K")
    ben = _row("Ben", "$50K p/a", uid="2", appearance="$1K")
    rows = [ada, ben]
    wages = sf.projected_annual_wages(rows, years=2, apply_yearly_raises=True)
    assert wages[0] == pytest.approx(155_000)
    assert wages[1] == pytest.approx(160_000)
    fees = sf.projected_annual_fees(rows, [ada["key"]], years=1, season_games=10)
    assert fees == [pytest.approx(20_000)]
    outlook = sf.player_wage_outlook(ada, years=2, apply_yearly_raises=True)
    assert outlook == [pytest.approx(105_000), pytest.approx(110_000)]
    totals = sf.squad_raise_totals(rows)
    assert totals["yearly"] == pytest.approx(5_000)
    raises = {
        "promotion": 10,
        "top_promotion": 20,
        "relegation": 3,
        "top_relegation": 7,
    }
    assert sf.promotion_raise_for_mode(raises, "normal") == 10
    assert sf.relegation_drop_for_mode(raises, "top") == 7
    assert sf.division_change_amounts(raises, "promo_top") == {
        "promotion": 20.0,
        "relegation": 0.0,
        "net": 20.0,
    }


def test_load_squad_finance_and_matchday_statement():
    text = (
        "Name,Unique ID,Club,Position,Best Pos,Salary,Appearance Fee,Expires,"
        "Yearly Salary Raise\n"
        "Ada,1,City,M (C),MC,$100K p/a,$2K,6/30/2030,10%\n"
        "Keeper,2,City,GK,GK,$40K p/a,$500,6/30/2031,\n"
        "Bench,3,City,D (C),DC,$20K p/a,$200,6/30/2029,\n"
    )
    rows = sf.load_squad_finance(text)
    assert [row["name"] for row in rows] == ["Ada", "Keeper", "Bench"]
    assert rows[0]["yearly_salary_raise_kind"] == "pct"
    starters, subs = sf.default_matchday_keys(rows)
    assert rows[1]["key"] in starters  # GK forced into XI
    assert rows[0]["key"] in starters
    restored = sf.restore_matchday_keys(rows, starters, subs)
    assert restored[0] == starters
    statement = sf.matchday_statement(
        rows, [rows[0]["key"], rows[1]["key"]], [], games=19, season_games=38
    )
    assert statement["starters"] == 2
    assert statement["reserves"] == 1
    assert statement["gk_starters"] == 1
    reserve = next(line for line in statement["lines"] if line["role"] == "reserve")
    assert reserve["match_fees"] == 0.0
    with pytest.raises(ValueError, match="empty"):
        sf.load_squad_finance("   ")
    with pytest.raises(ValueError, match="Name"):
        sf.load_squad_finance("Club,Age\nCity,22\n")


def test_club_sustainability_surplus_and_timeline():
    result = sf.club_sustainability(
        balance=1_000_000,
        income={"gate": 2_000_000},
        expenses={},
        squad_total=1_000_000,
        games=38,
        season_games=38,
        years=2,
    )
    assert result["annual_income"] == pytest.approx(2_000_000)
    assert result["annual_squad"] == pytest.approx(1_000_000)
    assert result["annual_net"] == pytest.approx(1_000_000)
    assert result["surplus"] == pytest.approx(3_000_000)
    assert result["sustainable"] is True
    assert [point["year"] for point in result["timeline"]] == [0, 1, 2]
