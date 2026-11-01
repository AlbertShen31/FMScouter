"""Recency-weighted multi-year merge, presence, and growth-field helpers."""
from __future__ import annotations

import pytest

import scoring.multi_year as my
from services.export_library import DEFAULT_YEAR_WEIGHTS, YEAR_KEYS


def _player(
    name: str,
    uid: str,
    *,
    minutes: float,
    stats: dict | None = None,
    **extra,
) -> dict:
    row = {
        "name": name,
        "unique_id": uid,
        "Name": name,
        "Unique ID": uid,
        "club": "City",
        "minutes": minutes,
        "stats": dict(stats or {}),
    }
    row.update(extra)
    return row


def test_newest_year_key_and_pct_basis():
    assert my.newest_year_key({"1": {}, "3": {}}) == "3"
    assert my.newest_year_key({"2": {}}, years_present=["2"]) == "2"
    assert my.newest_year_key({}) is None
    assert my.normalize_pct_basis("Current Year") == "current"
    assert my.normalize_pct_basis("multi-year") == "multiyear"
    assert my.normalize_pct_basis("nope") == "current"


def test_overlay_current_year_replaces_rates():
    player = _player(
        "Ada",
        "1",
        minutes=1800,
        stats={"goals": 0.4},
        years_present=["1", "3"],
        by_year={
            "1": {"minutes": 900, "stats": {"goals": 0.2}, "division": "Liga II"},
            "3": {"minutes": 900, "stats": {"goals": 0.8}, "division": "Liga I"},
        },
    )
    current = my.overlay_player_pct_basis(player, pct_basis="current")
    assert current["stats"]["goals"] == 0.8
    assert current["minutes"] == 900
    assert current["division"] == "Liga I"
    assert my.overlay_player_pct_basis(player, pct_basis="multiyear") is player
    assert my.overlay_player_pct_basis(None) is None


def test_presence_status_patterns():
    years = list(YEAR_KEYS)
    assert my.presence_status(years, years) == "continuous"
    assert my.presence_status(years, ["3"]) == "new"
    assert my.presence_status(years, ["1", "2"]) == "departed"
    assert my.presence_status(years, ["2", "3"]) == "partial"
    assert my.presence_status(years, ["1", "3"]) == "partial"
    assert my.presence_status(["3"], ["3"]) is None
    assert my.status_label("continuous") == "Continuous"
    assert my.status_label(None) == ""


def test_merge_per90_is_minutes_and_weight_weighted():
    year_players = {
        "1": _player("Ada", "1", minutes=900, stats={"goals": 0.5}),
        "3": _player("Ada", "1", minutes=900, stats={"goals": 1.0}),
    }
    weights = {"1": 0.5, "3": 1.0}
    merged, _sp, total_mins, eff_mins, unavail, limited = my.merge_stats_for_player(
        year_players, weights
    )
    assert total_mins == pytest.approx(1800)
    assert eff_mins == pytest.approx(1350)
    assert merged["goals"] == pytest.approx((0.5 * 0.5 * 10 + 1.0 * 10) / (1350 / 90))
    assert unavail == []
    assert limited is False


def test_combined_role_scores_renormalize_per_role():
    scores = my.combined_role_scores(
        {"1": {"BPD": 10.0, "VOL": 8.0}, "3": {"BPD": 16.0}},
        {"1": 0.5, "3": 1.0},
    )
    assert scores["BPD"] == pytest.approx(14.0)
    assert scores["VOL"] == pytest.approx(8.0)


def test_merge_year_maps_presence_and_stats():
    ada_y1 = _player(
        "Ada",
        "1",
        minutes=900,
        stats={"goals": 0.3},
        position="M (C)",
        best_pos="MC",
        attrs={"Pac": 12},
    )
    ada_y3 = _player(
        "Ada",
        "1",
        minutes=900,
        stats={"goals": 0.9},
        position="M (C)",
        best_pos="MC",
        division="Liga I",
        limited_division_tracking=True,
    )
    players, limited = my.merge_year_maps(
        role_by_year={"1": [ada_y1], "3": [ada_y3]},
        stats_by_year={"1": [ada_y1], "3": [ada_y3]},
        configured=list(YEAR_KEYS),
        weights=DEFAULT_YEAR_WEIGHTS,
    )
    assert len(players) == 1
    merged = players[0]
    assert merged["years_present"] == ["1", "3"]
    assert merged["multi_year_status"] == "partial"
    assert merged["by_year"]["3"]["stats"]["goals"] == 0.9
    assert merged["stats"]["goals"] == pytest.approx(
        (0.3 * 0.5 * 10 + 0.9 * 10) / ((900 * 0.5 + 900 * 1.0) / 90)
    )
    assert "Liga I" in limited


def test_growth_fields_and_pack_signature():
    record = {
        "name": "Ada",
        "by_year": {"3": {"minutes": 900}},
        "role_scores_by_year": {"3": {"BPD": 12}},
        "role_scores_combined": {"BPD": 12},
    }
    growth = my.growth_fields_of(record)
    assert set(growth) == set(my.GROWTH_FIELD_KEYS)
    slim = my.without_growth_fields(record)
    assert "by_year" not in slim
    assert slim["name"] == "Ada"
    assert my.list_without_growth_fields([record, "skip"]) == [slim]
    bits = my.pack_signature_bits(
        {
            "years": {"1": "a", "3": "c"},
            "weights": {"1": 0.4, "2": 0.7, "3": 1.2},
        }
    )
    assert bits["multi_year"] is True
    assert bits["years"] == {"1": "a", "3": "c"}
    assert bits["weights"]["3"] == pytest.approx(1.2)
