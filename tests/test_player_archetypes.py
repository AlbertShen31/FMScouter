"""Archetype definitions, filters, tiers, and stamped matching."""
from __future__ import annotations

import scoring.player_archetypes as arch


def _midfielder(*, minutes: float = 900, stats: dict | None = None) -> dict:
    return {
        "name": "Ada",
        "unique_id": "1",
        "minutes": minutes,
        "position": "M (C)",
        "best_pos": "MC",
        "pos_group": "mid",
        "stats": dict(stats or {"goals": 0.4, "assists": 0.3, "key_passes": 2.0}),
    }


def test_defs_filters_and_tier_helpers():
    defs = arch.archetype_defs()
    assert defs
    assert all(not item.get("archived") for item in defs)
    options = {item["value"] for item in arch.archetype_filter_options()}
    assert "shot_stopper" in options
    assert arch.normalize_archetype_filter(["shot_stopper", "nope", "shot_stopper"]) == [
        "shot_stopper"
    ]
    assert arch.normalize_archetype_filter("shot_stopper") == []
    floors = arch.default_tier_floors()
    assert floors == {"bronze": 70.0, "silver": 80.0, "gold": 90.0}
    assert arch.default_tier_ceilings()["rust"] == 30.0
    assert arch.tier_label("gold") == "Gold"
    assert arch.tier_polarity("rust") == "low"
    assert arch.group_abbr("mid") == "MID"
    assert arch._high_tier_for_percentiles([92, 88], floors) == "gold"
    assert arch._high_tier_for_percentiles([82, 84], floors) == "silver"
    assert arch._high_tier_for_percentiles([71], floors) == "bronze"
    assert arch._high_tier_for_percentiles([60], floors) is None
    assert arch._low_tier_for_percentiles([10, 20], {"rust": 30}) == "rust"
    assert arch._low_tier_for_percentiles([40], {"rust": 30}) is None


def test_pos_group_and_eligible_groups():
    mid = _midfielder()
    assert arch.resolve_archetype_pos_group(mid) == "mid"
    assert arch.resolve_archetype_pos_group(mid, preferred="fwd") == "fwd"
    assert arch.archetype_pos_group_options(mid) == [
        ("def", "DEF"),
        ("mid", "MID"),
        ("fwd", "FWD"),
    ]
    gk = {
        "name": "Ion",
        "minutes": 900,
        "position": "GK",
        "best_pos": "GK",
        "pos_group": "gk",
        "stats": {"save_percentage": 75},
    }
    assert arch.resolve_archetype_pos_group(gk) == "gk"
    assert arch.archetype_pos_group_options(gk) == [("gk", "GK")]
    assert arch.eligible_stats_groups(mid) == ["mid"]
    assert arch.eligible_stats_groups(gk) == ["gk"]
    assert arch.stamped_field_for_pct_basis("current") == arch.HIGH_ARCHETYPES_CURRENT_FIELD
    assert arch.stamped_field_for_pct_basis("multiyear") == arch.HIGH_ARCHETYPES_FIELD


def test_evaluate_uses_percentile_floors(monkeypatch):
    monkeypatch.setattr(arch, "band_metric", lambda *args, **kwargs: {"percentile": 95.0})
    monkeypatch.setattr(arch, "_metric_in_group", lambda *args, **kwargs: "possession")
    monkeypatch.setattr(arch, "metric_is_unavailable", lambda *args, **kwargs: False)
    earned = arch.high_archetype_ids_for_player(
        _midfielder(),
        min_minutes=600,
        only_ids=None,
        settings_normalized=False,
    )
    assert earned
    assert arch.high_archetype_ids_for_player(_midfielder(minutes=10), min_minutes=600) == set()
    assert arch.evaluate_archetypes(None) == []
    results = arch.evaluate_archetypes(_midfielder(), min_minutes=600, pos_group="mid")
    assert results
    assert all(item.get("id") for item in results)


def test_stamp_and_matching_use_stamped_ids():
    player = _midfielder()
    player[arch.HIGH_ARCHETYPES_FIELD] = ["box_to_box_midfielder"]
    player[arch.HIGH_ARCHETYPES_CURRENT_FIELD] = ["creator"]
    mapped = arch.archetype_map_from_players(
        [player],
        key_fn=lambda p: f"{p['name']}|{p['unique_id']}",
    )
    assert mapped["Ada|1"] == ["box_to_box_midfielder"]
    keys = arch.matching_archetype_keys(
        [player],
        ["box_to_box_midfielder"],
        key_fn=lambda p: f"{p['name']}|{p['unique_id']}",
    )
    assert keys == {"Ada|1"}
    current = arch.matching_archetype_keys(
        [player],
        ["creator"],
        pct_basis="current",
        key_fn=lambda p: f"{p['name']}|{p['unique_id']}",
    )
    assert current == {"Ada|1"}
    assert arch.matching_archetype_keys([player], []) is None
