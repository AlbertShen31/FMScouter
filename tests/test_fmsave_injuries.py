"""Injury columns stay blank after save-export injury scan removal."""

from types import SimpleNamespace

import services.fmsave_export as fms


def test_injury_columns_are_blank():
    for col in ("Injury", "Injured On", "Time Missed", "Recurring Injury"):
        assert col in fms.BLANK_COLUMNS


def test_identity_columns_leave_injury_blank():
    player = SimpleNamespace(
        name="Test",
        unique_id=1,
        age=24,
        club_name="Club",
        loan_parent_club_name=None,
        club_nation_id=None,
        club_fa_nation_id=None,
        nation_id=None,
        second_nation_ids=(),
        natural_positions=(),
        accomplished_positions=(),
        height_cm=180,
        left_foot=None,
        right_foot=None,
        ability=None,
        reputation=None,
    )
    cols = fms._identity_columns(player)
    assert cols["Injury"] == ""
    assert cols["Injured On"] == ""
    assert cols["Time Missed"] == ""
    assert cols["Recurring Injury"] == ""
