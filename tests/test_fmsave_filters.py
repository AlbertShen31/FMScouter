"""Save-export filters: age/club/nation/position only — CA and club rep are cheats."""
from __future__ import annotations

from types import SimpleNamespace

import services.fmsave_export as fms


def _player(**overrides):
    base = dict(
        age=24,
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
