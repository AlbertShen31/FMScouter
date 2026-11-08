"""Save-export filters: age/height/club/nation/position — CA and club rep are cheats."""
from __future__ import annotations

from types import SimpleNamespace

import services.fmsave_export as fms


def _player(**overrides):
    base = dict(
        age=24,
        height_cm=185,
        club_name="FC Romania",
        club_nation_id=164,
        nation_id=164,
        natural_positions=("DC",),
        ability=SimpleNamespace(current=80, potential=120),
        club_reputation=2000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_passes_filters_ignores_ca_and_club_rep():
    player = _player()
    assert fms._passes_filters(
        player,
        {"min_ca": 150, "min_club_reputation": 10000},
    )
    assert fms._filters_active({"min_ca": 150, "min_club_reputation": 10000}) is False


def test_passes_filters_still_applies_age():
    player = _player(age=18)
    assert fms._passes_filters(player, {"age_min": 21}) is False
    assert fms._passes_filters(player, {"age_max": 20}) is True


def test_passes_filters_applies_height_ft_in():
    # 178 cm → round(178/2.54) = 70 in → 5'10"
    player = _player(height_cm=178)
    assert fms.height_bound_inches(5, 11) == 71
    assert fms._passes_filters(player, {"height_min_in": 71}) is False
    assert fms._passes_filters(player, {"height_max_in": 70}) is True
    assert fms._passes_filters(player, {"height_min_in": 70, "height_max_in": 72}) is True
    assert fms._filters_active({"height_min_in": 71}) is True


def test_height_bound_inches_empty_and_partial():
    assert fms.height_bound_inches(None, None) is None
    assert fms.height_bound_inches(6, None) == 72
    assert fms.height_bound_inches(None, 10) == 10
