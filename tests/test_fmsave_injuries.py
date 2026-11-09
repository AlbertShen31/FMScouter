"""Unit tests for fmsave current-injury CSV columns."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import services.fmsave_export as fms


def test_format_time_missed_uses_days_and_weeks():
    assert fms._format_time_missed(None) == ""
    assert fms._format_time_missed(0) == ""
    assert fms._format_time_missed(1) == "1 day"
    assert fms._format_time_missed(10) == "10 days"
    assert fms._format_time_missed(7) == "1 week"
    assert fms._format_time_missed(14) == "2 weeks"


def test_build_current_injury_pairs_typed_with_history():
    game_date = date(2027, 4, 10)
    records = [
        SimpleNamespace(
            kind="history",
            player_uid=101,
            date=date(2027, 3, 20),
            type_name=None,
        ),
        SimpleNamespace(
            kind="typed",
            player_uid=101,
            date=date(2027, 4, 24),
            type_name="hamstring strain",
        ),
        # Recovered typed row must not count as current.
        SimpleNamespace(
            kind="typed",
            player_uid=202,
            date=date(2027, 4, 1),
            type_name="ankle sprain",
        ),
        SimpleNamespace(
            kind="history",
            player_uid=202,
            date=date(2027, 3, 15),
            type_name=None,
        ),
        # Unnamed type still marks the player injured.
        SimpleNamespace(
            kind="typed",
            player_uid=303,
            date=date(2027, 4, 10),
            type_name=None,
        ),
    ]
    career_save = SimpleNamespace(injuries=lambda: records)
    out = fms._build_current_injury_by_uid(
        career_save,
        game_date=game_date,
        uid_set=frozenset({101, 202, 303}),
    )
    assert 202 not in out
    assert out[101] == {
        "Injury": "hamstring strain",
        "Injured On": "3/20/2027",
        "Time Missed": "5 weeks",
        "Recurring Injury": "",
    }
    assert out[303]["Injury"] == "Injured"
    assert out[303]["Injured On"] == ""
    assert out[303]["Time Missed"] == ""


def test_player_row_includes_injury_columns():
    player = SimpleNamespace(
        name="Alex Example",
        uid=101,
        unique_id=101,
        age=24,
        club_name="FC Romania",
        nation_id=164,
        second_nation_ids=(),
        club_nation_id=164,
        club_fa_nation_id=164,
        natural_positions=("DC",),
        accomplished_positions=(),
        height_cm=185,
        left_foot=8,
        right_foot=20,
        ability=None,
        reputation=None,
        attributes=SimpleNamespace(
            **{field: 10 for field in fms.ATTR_FIELD_TO_CSV}
        ),
        contract=None,
        transfer_value=None,
    )
    injury_by_uid = {
        101: {
            "Injury": "hamstring strain",
            "Injured On": "3/20/2027",
            "Time Missed": "5 weeks",
            "Recurring Injury": "",
        }
    }
    row = fms._player_row(player, None, injury_by_uid=injury_by_uid)
    assert row["Injury"] == "hamstring strain"
    assert row["Injured On"] == "3/20/2027"
    assert row["Time Missed"] == "5 weeks"
    assert "Recurring Injury" in fms.BLANK_COLUMNS
    assert "Injury" not in fms.BLANK_COLUMNS
