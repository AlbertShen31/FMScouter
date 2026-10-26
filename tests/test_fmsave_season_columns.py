"""Unit tests for fmsave Moneyball season-stat column mapping."""
from __future__ import annotations

from types import SimpleNamespace

import services.fmsave_export as fms


def _sample_stats(**overrides):
    base = dict(
        starts=10,
        substitute_appearances=2,
        minutes=900,
        goals=5,
        goals_per_90=0.5,
        assists=3,
        assists_per_90=0.3,
        expected_goals=6.5,
        expected_goals_per_90=0.65,
        non_penalty_expected_goals=5.8,
        non_penalty_expected_goals_per_90=0.58,
        expected_assists=2.1,
        expected_assists_per_90=0.21,
        shots=20,
        shots_per_90=2.0,
        shots_on_target=8,
        shots_on_target_per_90=0.8,
        conversion_percent=25.0,
        key_passes=10,
        key_passes_per_90=1.0,
        dribbles=4,
        dribbles_per_90=0.4,
        passes_attempted=400,
        passes_attempted_per_90=40.0,
        pass_completion_percent=85.0,
        progressive_passes=30,
        progressive_passes_per_90=3.0,
        possession_won_per_90=5.0,
        possession_lost_per_90=7.5,
        interceptions=12,
        interceptions_per_90=1.2,
        clearances=8,
        clearances_per_90=0.8,
        blocks=2,
        blocks_per_90=0.2,
        headers_won=15,
        headers_won_per_90=1.5,
        aerial_challenges_attempted=30,
        aerial_challenges_attempted_per_90=3.0,
        headers_won_percent=50.0,
        tackles_attempted=20,
        tackles_completed=14,
        tackles_completed_per_90=1.4,
        tackle_completion_percent=70.0,
        pressures_completed=25,
        pressures_completed_per_90=2.5,
        pressures_attempted=40,
        pressures_attempted_per_90=4.0,
        crosses_completed=5,
        open_play_crosses_completed=3,
        open_play_crosses_completed_per_90=0.3,
        high_intensity_sprints=50,
        high_intensity_sprints_per_90=5.0,
        goals_allowed=0,
        expected_goals_prevented=0.0,
        expected_goals_prevented_per_90=0.0,
        average_rating=7.1,
        yellow_cards=2,
        red_cards=0,
        fouls_made=9,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_season_columns_maps_new_fmsave_fields():
    cols = fms._season_columns(_sample_stats())
    assert cols["xG-OP"] == "-1.5"
    assert cols["NP-xG"] == "5.8"
    assert cols["NP-xG/90"] == "0.58"
    assert cols["Possession Lost per 90"] == "7.5"
    assert cols["PsP"] == "30"
    assert cols["Blk"] == "2"
    assert cols["Sprints"] == "50"
    assert cols["Open Play Crosses Completed"] == "3"
    assert cols["Headers Attempted"] == "30"
    assert cols["Fouls Made per 90"] == "0.9"


def test_season_columns_empty_when_missing():
    cols = fms._season_columns(None)
    assert cols["xG-OP"] == ""
    assert cols["NP-xG"] == ""
    assert cols["NP-xG/90"] == ""
    assert cols["Possession Lost per 90"] == ""


def test_pick_history_row_prefers_newest_same_club():
    older = SimpleNamespace(club_uid=1, season_year=2027, minutes=2000)
    newer_other = SimpleNamespace(club_uid=2, season_year=2028, minutes=900)
    newer_same = SimpleNamespace(club_uid=1, season_year=2028, minutes=800)
    picked = fms._pick_history_row(
        [older, newer_other, newer_same],
        club_uid=1,
    )
    assert picked is newer_same


def test_pick_history_row_skips_zero_minute_rows():
    empty = SimpleNamespace(club_uid=1, season_year=2028, minutes=0)
    prior = SimpleNamespace(club_uid=1, season_year=2027, minutes=1200)
    assert fms._pick_history_row([empty, prior], club_uid=1) is prior
    assert not fms._season_has_minutes(empty)
    assert fms._season_has_minutes(prior)
