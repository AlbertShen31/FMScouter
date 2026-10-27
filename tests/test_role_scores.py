"""Validate the role-score formula for every role, pack, set piece, and combo."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import config.fm26_role_weight_config as pc
import scoring.role_scorer as rs
import services.role_config as role_config
from scoring.phases import phase_tone
from scoring.utils import calculate_score

role_config.ensure_loaded()

DEFAULT_WEIGHTS = {
    "key": float(pc.KEY_WEIGHT),
    "preferred": float(pc.PREFERRED_WEIGHT),
    "useful": float(pc.USEFUL_WEIGHT),
}
CUSTOM_WEIGHTS = {"key": 4.0, "preferred": 2.0, "useful": 0.5}


def _independent_score(
    attrs: dict,
    key_attrs: list[str],
    preferred_attrs: list[str],
    useful_attrs: list[str],
    key_weight: float,
    preferred_weight: float,
    useful_weight: float,
    divisor: float,
) -> float:
    """Documented weighted-average contract (not the production helper)."""

    def attr_value(name: str) -> int:
        value = attrs.get(name, 0)
        if value in ("-", "", None):
            return 0
        if isinstance(value, str) and "-" in value:
            return int(value.split("-")[0])
        return int(value)

    if not divisor:
        return 0.0
    total = (
        sum(attr_value(name) for name in key_attrs) * key_weight
        + sum(attr_value(name) for name in preferred_attrs) * preferred_weight
        + sum(attr_value(name) for name in useful_attrs) * useful_weight
    ) / divisor
    return round(total, 1)


def _attr_lists(cfg: dict) -> tuple[list[str], list[str], list[str]]:
    return (
        list(cfg.get("key_attrs") or []),
        list(cfg.get("preferred_attrs") or cfg.get("green_attrs") or []),
        list(cfg.get("useful_attrs") or cfg.get("blue_attrs") or []),
    )


def _divisor(key_n: int, pref_n: int, useful_n: int, weights: dict[str, float]) -> float:
    return (
        weights["key"] * key_n
        + weights["preferred"] * pref_n
        + weights["useful"] * useful_n
    )


def _all_attr_codes() -> list[str]:
    codes = set(rs.ATTR_MAP.values())
    sources = [pc.all_positions]
    if role_config._FACTORY:
        sources.append(role_config._FACTORY)
    for roles in sources:
        for cfg in roles.values():
            for bucket in _attr_lists(cfg):
                codes.update(bucket)
    for profile in rs.SET_PIECE_PROFILES:
        for bucket in ("key", "preferred", "useful"):
            codes.update(profile.get(bucket) or ())
        if profile.get("raw"):
            codes.add(profile["raw"])
    return sorted(codes)


def _uniform_attrs(value: int) -> dict[str, int]:
    return {code: value for code in _all_attr_codes()}


def _mixed_attrs() -> dict[str, int]:
    return {code: (index % 20) + 1 for index, code in enumerate(_all_attr_codes())}


def _player(attrs: dict, **overrides) -> dict:
    row = {
        "name": "Test Player",
        "unique_id": "1",
        "age": "24",
        "club": "Test FC",
        "division": "Liga I",
        "nation": "ROU",
        "second_nation": "",
        "based_in": "Romania",
        "position": "DC",
        "best_pos": "DC",
        "style": "",
        "height": "185",
        "left_foot": "Reasonable",
        "right_foot": "Very Strong",
        "rec": "",
        "inf": "",
        "injury": "",
        "injured_on": "",
        "time_missed": "",
        "squad": "",
        "positions": rs.parse_positions("D (C)"),
        "attrs": attrs,
    }
    row.update(overrides)
    return row


def _pack_roles() -> list[tuple[str, dict]]:
    packs: list[tuple[str, dict]] = []
    factory = role_config._FACTORY or {}
    if factory:
        packs.append(("builtin", factory))
    packs_dir: Path = role_config.PACKS_DIR
    if packs_dir.exists():
        for path in sorted(packs_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            roles = payload.get("roles") if isinstance(payload, dict) else None
            if isinstance(roles, dict):
                packs.append((path.stem, roles))
    return packs


def _first_role(tone: str) -> str:
    for role_id, cfg in pc.all_positions.items():
        if phase_tone(cfg.get("phase")) == tone:
            return role_id
    raise AssertionError(f"no {tone} role loaded")


class TestCalculateScore(unittest.TestCase):
    def test_uniform_attributes_return_that_value(self):
        self.assertEqual(
            calculate_score({"Pas": 12, "Tec": 12, "Dec": 12}, ["Pas"], ["Tec"], ["Dec"], 5, 3, 1, 9),
            12.0,
        )

    def test_hand_calculated_weighted_average(self):
        # (5*20 + 3*10 + 1*5) / 9 = 135 / 9 = 15.0
        self.assertEqual(
            calculate_score({"Pas": 20, "Tec": 10, "Dec": 5}, ["Pas"], ["Tec"], ["Dec"], 5, 3, 1, 9),
            15.0,
        )

    def test_rounds_to_one_decimal(self):
        # (5*20 + 3*10 + 1*0) / 9 = 130 / 9 = 14.444… → 14.4
        self.assertEqual(
            calculate_score({"Pas": 20, "Tec": 10, "Dec": 0}, ["Pas"], ["Tec"], ["Dec"], 5, 3, 1, 9),
            14.4,
        )

    def test_missing_blank_and_range_attributes(self):
        attrs = {"Pas": "-", "Tec": "", "Dec": "12-15"}
        # (5*0 + 3*0 + 1*12) / 9 = 1.333… → 1.3
        self.assertEqual(
            calculate_score(attrs, ["Pas"], ["Tec"], ["Dec"], 5, 3, 1, 9),
            1.3,
        )
        self.assertEqual(
            calculate_score({}, ["Pas"], ["Tec"], ["Dec"], 5, 3, 1, 9),
            0.0,
        )

    def test_zero_divisor_returns_zero(self):
        self.assertEqual(
            calculate_score({"Pas": 20}, ["Pas"], [], [], 5, 3, 1, 0),
            0.0,
        )

    def test_zero_weights_return_zero(self):
        self.assertEqual(
            calculate_score({"Pas": 20, "Tec": 10}, ["Pas"], ["Tec"], [], 0, 0, 0, 0),
            0.0,
        )


class TestAllRoleCalculations(unittest.TestCase):
    def test_every_live_role_has_positive_divisor(self):
        self.assertGreater(len(pc.all_positions), 0)
        for role_id, cfg in pc.all_positions.items():
            with self.subTest(role_id=role_id):
                key, pref, useful = _attr_lists(cfg)
                self.assertGreater(
                    len(key) + len(pref) + len(useful),
                    0,
                    "role has no scored attributes",
                )
                expected = (
                    float(cfg["key_weight"]) * len(key)
                    + float(cfg["preferred_weight"]) * len(pref)
                    + float(cfg["useful_weight"]) * len(useful)
                )
                self.assertEqual(cfg["divisor"], expected)
                self.assertGreater(cfg["divisor"], 0)

    def test_uniform_attributes_score_that_value_for_every_role(self):
        for value in (0, 10, 14, 20):
            player = _player(_uniform_attrs(value))
            for role_id in pc.all_positions:
                with self.subTest(role_id=role_id, value=value):
                    self.assertEqual(rs.score_player_role(player, role_id), float(value))

    def test_mixed_attributes_match_formula_for_every_role(self):
        attrs = _mixed_attrs()
        player = _player(attrs)
        for role_id, cfg in pc.all_positions.items():
            key, pref, useful = _attr_lists(cfg)
            expected = _independent_score(
                attrs,
                key,
                pref,
                useful,
                cfg["key_weight"],
                cfg["preferred_weight"],
                cfg["useful_weight"],
                cfg["divisor"],
            )
            with self.subTest(role_id=role_id):
                self.assertEqual(rs.score_player_role(player, role_id), expected)

    def test_custom_tier_weights_for_every_role(self):
        attrs = _mixed_attrs()
        player = _player(attrs)
        for role_id, cfg in pc.all_positions.items():
            key, pref, useful = _attr_lists(cfg)
            divisor = _divisor(len(key), len(pref), len(useful), CUSTOM_WEIGHTS)
            expected = _independent_score(
                attrs,
                key,
                pref,
                useful,
                CUSTOM_WEIGHTS["key"],
                CUSTOM_WEIGHTS["preferred"],
                CUSTOM_WEIGHTS["useful"],
                divisor,
            )
            with self.subTest(role_id=role_id):
                self.assertEqual(
                    rs.score_player_role(player, role_id, tier_weights=CUSTOM_WEIGHTS),
                    expected,
                )
                self.assertEqual(
                    rs.score_player_role(
                        _player(_uniform_attrs(11)),
                        role_id,
                        tier_weights=CUSTOM_WEIGHTS,
                    ),
                    11.0,
                )

    def test_unknown_role_returns_none(self):
        self.assertIsNone(rs.score_player_role(_player(_uniform_attrs(10)), "Not_A_Role"))

    def test_score_players_matches_score_player_role_for_every_role(self):
        role_ids = list(pc.all_positions)
        player = _player(_mixed_attrs())
        rows = rs.score_players([player], role_ids)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        best_score = -1.0
        best_label = ""
        for role_id in role_ids:
            column = rs.role_meta(role_id)["column"]
            expected = rs.score_player_role(player, role_id)
            with self.subTest(role_id=role_id, column=column):
                self.assertEqual(row[column], expected)
            if expected is not None and expected > best_score:
                best_score = expected
                best_label = column
        self.assertEqual(row["Best Role"], best_label)
        self.assertEqual(row["Best Role Score"], best_score)


class TestRolePackFormulas(unittest.TestCase):
    def test_every_pack_role_matches_formula(self):
        attrs = _mixed_attrs()
        uniform = _uniform_attrs(13)
        packs = _pack_roles()
        self.assertGreater(len(packs), 0)
        for pack_id, roles in packs:
            self.assertGreater(len(roles), 0, pack_id)
            for role_id, overlay in roles.items():
                key, pref, useful = _attr_lists(overlay)
                divisor = _divisor(len(key), len(pref), len(useful), DEFAULT_WEIGHTS)
                expected_mixed = _independent_score(
                    attrs,
                    key,
                    pref,
                    useful,
                    DEFAULT_WEIGHTS["key"],
                    DEFAULT_WEIGHTS["preferred"],
                    DEFAULT_WEIGHTS["useful"],
                    divisor,
                )
                with self.subTest(pack=pack_id, role_id=role_id):
                    self.assertIn(role_id, pc.all_positions)
                    self.assertGreater(divisor, 0)
                    self.assertEqual(
                        calculate_score(
                            attrs,
                            key,
                            pref,
                            useful,
                            DEFAULT_WEIGHTS["key"],
                            DEFAULT_WEIGHTS["preferred"],
                            DEFAULT_WEIGHTS["useful"],
                            divisor,
                        ),
                        expected_mixed,
                    )
                    self.assertEqual(
                        calculate_score(
                            uniform,
                            key,
                            pref,
                            useful,
                            DEFAULT_WEIGHTS["key"],
                            DEFAULT_WEIGHTS["preferred"],
                            DEFAULT_WEIGHTS["useful"],
                            divisor,
                        ),
                        13.0,
                    )


class TestSetPieceScores(unittest.TestCase):
    def test_every_set_piece_profile_matches_formula(self):
        attrs = _mixed_attrs()
        row: dict = {}
        rs.apply_set_piece_scores(row, attrs)
        self.assertGreater(len(rs.SET_PIECE_PROFILES), 0)
        for profile in rs.SET_PIECE_PROFILES:
            key = list(profile.get("key") or ())
            pref = list(profile.get("preferred") or ())
            useful = list(profile.get("useful") or ())
            divisor = rs.set_piece_divisor(profile)
            expected = _independent_score(
                attrs,
                key,
                pref,
                useful,
                DEFAULT_WEIGHTS["key"],
                DEFAULT_WEIGHTS["preferred"],
                DEFAULT_WEIGHTS["useful"],
                divisor,
            )
            with self.subTest(profile=profile["id"]):
                self.assertEqual(row[profile["score"]], expected)
                raw = profile.get("raw")
                if raw:
                    self.assertEqual(row[raw], attrs[raw])

    def test_set_piece_uniform_and_custom_weights(self):
        row: dict = {}
        rs.apply_set_piece_scores(row, _uniform_attrs(16), tier_weights=CUSTOM_WEIGHTS)
        for profile in rs.SET_PIECE_PROFILES:
            with self.subTest(profile=profile["id"]):
                self.assertEqual(row[profile["score"]], 16.0)


class TestComboScores(unittest.TestCase):
    def test_combo_is_two_thirds_ip_plus_one_third_oop(self):
        ip = _first_role("ip")
        oop = _first_role("oop")
        meta = rs.combo_meta(ip, oop)
        rows = [
            {
                meta["ip_column"]: 12.0,
                meta["oop_column"]: 9.0,
                f"{meta['ip_column']} eligible": "full",
                f"{meta['oop_column']} eligible": "none",
            }
        ]
        rs.apply_combos(rows, [{"ip": ip, "oop": oop}])
        # (2*12 + 1*9) / 3 = 11.0
        self.assertEqual(rows[0][meta["column"]], 11.0)

    def test_combo_rounds_to_one_decimal(self):
        ip = _first_role("ip")
        oop = _first_role("oop")
        meta = rs.combo_meta(ip, oop)
        rows = [{meta["ip_column"]: 10.0, meta["oop_column"]: 11.0}]
        rs.apply_combos(rows, [{"ip": ip, "oop": oop}])
        # (2*10 + 11) / 3 = 10.333… → 10.3
        self.assertEqual(rows[0][meta["column"]], 10.3)


class TestParseThenScore(unittest.TestCase):
    def test_csv_attributes_feed_every_role_formula(self):
        codes = _all_attr_codes()
        values = _mixed_attrs()
        header = ["Name", "Position", "Best Pos", *codes]
        cells = ["Ada", "DC", "DC", *[str(values[code]) for code in codes]]
        text = ",".join(header) + "\n" + ",".join(cells) + "\n"
        players = rs.parse_export(text)
        self.assertEqual(len(players), 1)
        player = players[0]
        for role_id, cfg in pc.all_positions.items():
            key, pref, useful = _attr_lists(cfg)
            expected = _independent_score(
                player["attrs"],
                key,
                pref,
                useful,
                cfg["key_weight"],
                cfg["preferred_weight"],
                cfg["useful_weight"],
                cfg["divisor"],
            )
            with self.subTest(role_id=role_id):
                self.assertEqual(rs.score_player_role(player, role_id), expected)


if __name__ == "__main__":
    unittest.main()
