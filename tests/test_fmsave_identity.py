"""Unit tests for fmsave identity columns (nations, blank list)."""
from __future__ import annotations

from types import SimpleNamespace

import services.fmsave_export as fms


def test_competition_name_map_reads_three_column_csv(tmp_path, monkeypatch):
    # data/competition-names.csv is gitignored; the extra `type` column is ours.
    csv_path = tmp_path / "competition-names.csv"
    csv_path.write_text(
        "database_id,name,type\n"
        "7540024,Liga I,league\n"
        "11,Premier League,league\n"
        "bad,Skip Me,league\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fms, "COMPETITION_NAMES_PATH", csv_path)
    fms.competition_name_map.cache_clear()
    try:
        names = fms.competition_name_map()
        assert names == {7540024: "Liga I", 11: "Premier League"}
    finally:
        fms.competition_name_map.cache_clear()


def test_nation_name_map_includes_known_ids():
    names = fms.nation_name_map()
    assert names[164] == "Romania"
    assert names[159] == "Northern Ireland"
    assert names[167] == "Scotland"
    assert names[139] == "England"


def test_identity_columns_fill_nation_fields():
    player = SimpleNamespace(
        name="Alex Example",
        unique_id=123,
        age=24,
        club_name="FC Romania",
        on_loan=False,
        loan_parent_club_name=None,
        nation_id=164,
        second_nation_ids=(139, 175),
        club_nation_id=164,
        club_fa_nation_id=164,
        natural_positions=("DC",),
        accomplished_positions=(),
        height_cm=185,
        left_foot=8,
        right_foot=20,
        ability=SimpleNamespace(current=140, potential=150),
        reputation=SimpleNamespace(world=5000),
    )
    cols = fms._identity_columns(player, division="Liga I")
    assert cols["Nation"] == "ROU"
    assert cols["Based In"] == "Romania"
    assert cols["2nd Nat"] == "ENG/WAL"
    assert cols["Division"] == "Liga I"
    assert cols["Club"] == "FC Romania"
    assert "Nation" not in fms.BLANK_COLUMNS
    assert "Based In" not in fms.BLANK_COLUMNS
    assert "2nd Nat" not in fms.BLANK_COLUMNS


def test_based_in_prefers_fa_nation_for_cross_border_clubs():
    player = SimpleNamespace(
        name="Cross Border",
        unique_id=1,
        age=22,
        club_name="Swansea",
        on_loan=False,
        loan_parent_club_name=None,
        nation_id=175,
        second_nation_ids=(),
        club_nation_id=139,
        club_fa_nation_id=175,
        natural_positions=("AML",),
        accomplished_positions=(),
        height_cm=178,
        left_foot=20,
        right_foot=10,
        ability=None,
        reputation=None,
    )
    cols = fms._identity_columns(player)
    assert cols["Based In"] == "Wales"
    assert cols["Nation"] == "WAL"


def test_club_display_shows_loan_parent_in_parens():
    loaned = SimpleNamespace(
        club_name="Spezia",
        on_loan=True,
        loan_parent_club_name="AS Roma",
    )
    assert fms._format_club_display(loaned) == "Spezia (AS Roma)"
    assert fms._format_club_display(
        SimpleNamespace(club_name="AS Roma", on_loan=False, loan_parent_club_name=None)
    ) == "AS Roma"
    assert fms._format_club_display(
        SimpleNamespace(
            club_name="AS Roma",
            on_loan=True,
            loan_parent_club_name="AS Roma",
        )
    ) == "AS Roma"


def test_club_contains_matches_loan_parent():
    player = SimpleNamespace(
        age=22,
        height_cm=180,
        club_name="Spezia",
        on_loan=True,
        loan_parent_club_name="AS Roma",
        club_nation_id=114,
        nation_id=114,
        natural_positions=("ST",),
    )
    prepared = fms.prepare_filters({"club_contains": "roma"})
    assert fms._passes_filters(player, prepared) is True
    prepared_miss = fms.prepare_filters({"club_contains": "napoli"})
    assert fms._passes_filters(player, prepared_miss) is False


def test_identity_columns_loan_club_format():
    player = SimpleNamespace(
        name="Loanee",
        unique_id=9,
        age=21,
        club_name="Spezia",
        on_loan=True,
        loan_parent_club_name="AS Roma",
        nation_id=114,
        second_nation_ids=(),
        club_nation_id=114,
        club_fa_nation_id=114,
        natural_positions=("ST",),
        accomplished_positions=(),
        height_cm=180,
        left_foot=12,
        right_foot=20,
        ability=None,
        reputation=None,
    )
    cols = fms._identity_columns(player)
    assert cols["Club"] == "Spezia (AS Roma)"
