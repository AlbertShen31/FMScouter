"""Validate player-stats parsing, percentiles, limited tracking, and banding."""
from __future__ import annotations

import unittest

import scoring.stats_availability as avail
import scoring.stats_detail_transform as detail
import scoring.stats_scorer as ss


def _csv(rows: list[dict[str, object]]) -> str:
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    lines = [",".join(keys)]
    for row in rows:
        lines.append(",".join(str(row.get(key, "")) for key in keys))
    return "\n".join(lines) + "\n"


def _all_metric_slots(*, include_hidden: bool = True):
    for group in ss.benchmarks()["groups"]:
        for category in ss.view_categories():
            for metric_id in ss.metrics_for(
                group, category["id"], include_hidden=include_hidden
            ):
                yield group, category["id"], metric_id


def _stats_at_cut(group: str, category: str, cut_index: int) -> dict[str, float]:
    stats: dict[str, float] = {}
    for metric_id in ss.metrics_for(group, category):
        cuts = ss.resolve_thresholds(group, category, metric_id)
        if cuts:
            stats[metric_id] = cuts[cut_index]
    return stats


def _outfield_limited_row(
    name: str,
    *,
    division: str = "Ligat Ha'Al",
    minutes: float = 900,
    leftover_key_passes: float = 0,
    possession_won: float = 0,
    xa: float = 0.2,
) -> dict[str, object]:
    return {
        "Name": name,
        "Division": division,
        "Best Pos": "MC",
        "Position": "M (C)",
        "Minutes": minutes,
        "Passes Attempted": 80,
        "Passes Attempted per 90": 8,
        "Shots": 4,
        "Shot/90": 0.4,
        "Tackles Attempted": 6,
        "Goals": 2,
        "Goals per 90 minutes": 0.2,
        "xA": xa,
        "Interceptions": 0,
        "Interceptions per 90": 0,
        "Key Passes": leftover_key_passes,
        "Key Passes per 90": leftover_key_passes,
        "Progressive Passes per 90": 0,
        "Clearances": 0,
        "Clearances per 90": 0,
        "Possession Won per 90": possession_won,
    }


class TestParseNumber(unittest.TestCase):
    def test_blank_and_dash_are_missing(self):
        for value in (None, "", "-", " - "):
            self.assertIsNone(ss.parse_number(value))

    def test_comma_percent_and_spaces(self):
        self.assertEqual(ss.parse_number("1,5"), 1.5)
        self.assertEqual(ss.parse_number("12.3%"), 12.3)
        self.assertEqual(ss.parse_number("  4  "), 4.0)


class TestPer90Derivation(unittest.TestCase):
    def test_total_over_minutes(self):
        self.assertEqual(ss._per90_from_total(9, 900), 0.9)
        self.assertEqual(ss._per90_from_total(10, 450), 2.0)

    def test_prefer_export_when_totals_look_broken(self):
        self.assertTrue(ss._should_prefer_export_per90(0.0, 0.4))
        self.assertTrue(ss._should_prefer_export_per90(0.1, 0.4))
        self.assertTrue(ss._should_prefer_export_per90(0.2, 0.3))
        self.assertFalse(ss._should_prefer_export_per90(0.4, 0.0))
        self.assertFalse(ss._should_prefer_export_per90(0.98, 1.0))

    def test_goals_recovered_from_xg_and_xg_op(self):
        row = {"xG": "4.2", "xG-OP": "1.8"}
        self.assertAlmostEqual(ss._goals_from_xg_overperformance(row), 6.0)
        self.assertIsNone(ss._goals_from_xg_overperformance({"xG": "4.2"}))

    def test_goals_per90_uses_xg_recovery_when_total_is_zero(self):
        row = {
            "Minutes": "900",
            "Goals": "0",
            "Goals per 90 minutes": "0.20",
            "xG": "4.2",
            "xG-OP": "1.8",
        }
        # 6 goals in 900 minutes → 0.6/90, not FM's rounded 0.20
        self.assertAlmostEqual(ss._pick_goals_per90(row, ["Goals", "Goals per 90 minutes"]), 0.6)

    def test_goals_per90_uses_healthy_total(self):
        row = {
            "Minutes": "900",
            "Goals": "10",
            "Goals per 90 minutes": "0.95",
        }
        self.assertAlmostEqual(ss._pick_goals_per90(row, ["Goals", "Goals per 90 minutes"]), 1.0)

    def test_generic_per90_falls_back_to_export_rate(self):
        row = {
            "Minutes": "900",
            "Assists": "0",
            "Asts/90": "0.31",
        }
        value = ss._pick_metric_raw(row, "assists")
        self.assertAlmostEqual(value, 0.31)

    def test_goals_allowed_converts_to_per90(self):
        row = {"Minutes": "900", "Goals Allowed": "12"}
        self.assertAlmostEqual(ss._pick_metric_raw(row, "goals_conceded"), 1.2)


class TestPercentileMath(unittest.TestCase):
    HIB = [1.0, 2.0, 3.0, 4.0]
    LIB = [4.0, 3.0, 2.0, 1.0]

    def test_exact_cuts_higher_is_better(self):
        for value, expected in zip(self.HIB, (20.0, 40.0, 60.0, 80.0)):
            self.assertEqual(
                ss.estimate_percentile(value, self.HIB, higher_is_better=True),
                expected,
            )

    def test_exact_cuts_lower_is_better(self):
        for value, expected in zip(self.LIB, (20.0, 40.0, 60.0, 80.0)):
            self.assertEqual(
                ss.estimate_percentile(value, self.LIB, higher_is_better=False),
                expected,
            )

    def test_interpolates_between_cuts(self):
        self.assertEqual(
            ss.estimate_percentile(1.5, self.HIB, higher_is_better=True),
            30.0,
        )
        self.assertEqual(
            ss.estimate_percentile(3.5, self.LIB, higher_is_better=False),
            30.0,
        )

    def test_default_tails(self):
        # p0 = t20 - |t20| = 0; value 0 → 0th
        self.assertEqual(ss.estimate_percentile(0.0, self.HIB, higher_is_better=True), 0.0)
        # p100 = t80 + |t80| = 8; value 6 → 90th
        self.assertEqual(ss.estimate_percentile(6.0, self.HIB, higher_is_better=True), 90.0)
        self.assertEqual(ss.estimate_percentile(8.0, self.HIB, higher_is_better=True), 100.0)
        # lower-is-better p100 = t80 - |t80| = 0; value 0 → 100th
        self.assertEqual(ss.estimate_percentile(0.0, self.LIB, higher_is_better=False), 100.0)

    def test_adaptive_p0_and_p100_stretch_tails(self):
        self.assertEqual(
            ss.estimate_percentile(0.0, self.HIB, higher_is_better=True, p0=-1.0),
            10.0,
        )
        self.assertEqual(
            ss.estimate_percentile(6.0, self.HIB, higher_is_better=True, p100=6.0),
            100.0,
        )

    def test_implied_floor_and_ceiling(self):
        self.assertEqual(ss.implied_percentile_ceiling(self.HIB, higher_is_better=True), 8.0)
        self.assertEqual(ss.implied_percentile_floor(self.HIB, higher_is_better=True), 0.0)
        self.assertEqual(ss.implied_percentile_ceiling(self.LIB, higher_is_better=False), 0.0)
        self.assertEqual(ss.implied_percentile_floor(self.LIB, higher_is_better=False), 8.0)

    def test_wrong_threshold_count_raises(self):
        with self.assertRaises(ValueError):
            ss.estimate_percentile(1.0, [1.0, 2.0, 3.0], higher_is_better=True)

    def test_percentile_color_endpoints(self):
        self.assertEqual(ss.percentile_color(0), "rgb(255, 92, 92)")
        self.assertEqual(ss.percentile_color(50), "rgb(255, 210, 64)")
        self.assertEqual(ss.percentile_color(100), "rgb(64, 220, 120)")
        self.assertIsNone(ss.percentile_color(None))


class TestBandEveryMetric(unittest.TestCase):
    def test_every_benchmark_metric_has_four_cuts(self):
        slots = list(_all_metric_slots())
        self.assertGreater(len(slots), 0)
        for group, category, metric_id in slots:
            with self.subTest(group=group, category=category, metric=metric_id):
                cuts = ss.resolve_thresholds(group, category, metric_id)
                self.assertIsNotNone(cuts)
                self.assertEqual(len(cuts), 4)

    def test_every_metric_scores_20_40_60_80_at_its_cuts(self):
        marks = (20.0, 40.0, 60.0, 80.0)
        for group, category, metric_id in _all_metric_slots():
            cuts = ss.resolve_thresholds(group, category, metric_id)
            # Tied cuts (e.g. 0 and 0) map to the first matching boundary.
            first_pct_for_cut = {}
            for cut, pct in zip(cuts, marks):
                first_pct_for_cut.setdefault(cut, pct)
            for cut, pct in first_pct_for_cut.items():
                band = ss.band_metric(group, category, metric_id, cut)
                with self.subTest(
                    group=group, category=category, metric=metric_id, cut=cut
                ):
                    self.assertAlmostEqual(band["percentile"], pct)
                    self.assertEqual(
                        band["higher_is_better"],
                        bool((ss.metric_defs()[metric_id]).get("higher_is_better", True)),
                    )

    def test_missing_value_is_unbanded(self):
        band = ss.band_metric("mid", "possession", "passes_attempted", None)
        self.assertIsNone(band["percentile"])
        self.assertEqual(band["display"], "—")

    def test_threshold_overrides_replace_builtin_cuts(self):
        overrides = {"mid": {"possession": {"passes_attempted": [1, 2, 3, 4]}}}
        self.assertEqual(
            ss.resolve_thresholds(
                "mid", "possession", "passes_attempted", threshold_overrides=overrides
            ),
            [1.0, 2.0, 3.0, 4.0],
        )
        band = ss.band_metric(
            "mid",
            "possession",
            "passes_attempted",
            2.0,
            threshold_overrides=overrides,
        )
        self.assertEqual(band["percentile"], 40.0)

    def test_gk_final_third_maps_to_goalkeeping_storage(self):
        self.assertEqual(ss.storage_category("gk", "final_third"), "goalkeeping")
        cuts = ss.resolve_thresholds("gk", "final_third", "xg_prevented")
        self.assertIsNotNone(cuts)
        band = ss.band_metric("gk", "final_third", "xg_prevented", cuts[3])
        self.assertEqual(band["percentile"], 80.0)


class TestCategoryAndOverallAverages(unittest.TestCase):
    def test_category_average_is_mean_of_metric_percentiles(self):
        for group in ss.benchmarks()["groups"]:
            for category in ss.view_categories():
                stats = _stats_at_cut(group, category["id"], 1)
                if not stats:
                    continue
                band = ss.category_average_band(group, category["id"], stats)
                with self.subTest(group=group, category=category["id"]):
                    self.assertAlmostEqual(band["percentile"], 40.0)

    def test_overall_average_is_mean_of_category_percentiles(self):
        for group in ss.benchmarks()["groups"]:
            stats: dict[str, float] = {}
            for category in ss.view_categories():
                stats.update(_stats_at_cut(group, category["id"], 2))
            band = ss.overall_average_band(group, stats)
            with self.subTest(group=group):
                self.assertAlmostEqual(band["percentile"], 60.0)

    def test_missing_metrics_are_skipped_not_treated_as_zero(self):
        cuts = ss.resolve_thresholds("mid", "final_third", "goals")
        band = ss.category_average_band("mid", "final_third", {"goals": cuts[3]})
        self.assertAlmostEqual(band["percentile"], 80.0)


class TestMinutesAndPosition(unittest.TestCase):
    def test_minutes_status(self):
        self.assertEqual(ss.minutes_status(900, 900), "meet")
        self.assertEqual(ss.minutes_status(450, 900), "half")
        self.assertEqual(ss.minutes_status(449, 900), "fail")
        self.assertEqual(ss.minutes_status(None, 900), "fail")
        self.assertEqual(ss.minutes_status(None, 0), "meet")

    def test_has_scorable_minutes(self):
        self.assertTrue(ss.has_scorable_minutes(1))
        self.assertFalse(ss.has_scorable_minutes(0))
        self.assertFalse(ss.has_scorable_minutes(None))

    def test_classify_best_pos(self):
        self.assertEqual(ss.classify_best_pos("GK"), "gk")
        self.assertEqual(ss.classify_best_pos("ST"), "fwd")
        self.assertEqual(ss.classify_best_pos("AM (L)"), "fwd")
        self.assertEqual(ss.classify_best_pos("D (C)"), "def")
        self.assertEqual(ss.classify_best_pos("WB"), "def")
        self.assertEqual(ss.classify_best_pos("M (C)"), "mid")
        self.assertEqual(ss.classify_best_pos("AM (C)"), "mid")
        self.assertEqual(ss.classify_best_pos(""), "mid")

    def test_scoring_stats_empty_without_minutes(self):
        self.assertEqual(ss.scoring_stats({"minutes": 0, "stats": {"goals": 1}}), {})
        self.assertEqual(
            ss.scoring_stats({"minutes": 900, "stats": {"goals": 1.0}}),
            {"goals": 1.0},
        )


class TestLimitedTracking(unittest.TestCase):
    def test_player_with_zero_probes_is_limited(self):
        row = {str(k): str(v) for k, v in _outfield_limited_row("Ada").items()}
        self.assertTrue(avail.detect_limited_tracking(row))

    def test_one_leftover_probe_still_limited(self):
        row = {
            str(k): str(v)
            for k, v in _outfield_limited_row("Ada", leftover_key_passes=3).items()
        }
        self.assertTrue(avail.detect_limited_tracking(row))

    def test_healthy_probes_are_not_limited(self):
        row = {
            str(k): str(v) for k, v in _outfield_limited_row("Ada", division="Eredivisie").items()
        }
        row["Interceptions per 90"] = "1.2"
        row["Key Passes per 90"] = "1.0"
        row["Progressive Passes per 90"] = "2.0"
        row["Clearances per 90"] = "0.8"
        self.assertFalse(avail.detect_limited_tracking(row))

    def test_xa_is_not_a_probe(self):
        row = {str(k): str(v) for k, v in _outfield_limited_row("Ada", xa=1.4).items()}
        self.assertTrue(avail.detect_limited_tracking(row))

    def test_short_minutes_are_not_player_limited(self):
        row = {str(k): str(v) for k, v in _outfield_limited_row("Ada", minutes=80).items()}
        self.assertFalse(avail.detect_limited_tracking(row))

    def test_possession_won_kept_when_positive(self):
        row = {
            str(k): str(v)
            for k, v in _outfield_limited_row("Ada", possession_won=1.4).items()
        }
        player = {
            "pos_group": "mid",
            "stats": {"goals": 0.2, "possession_won": 1.4, "key_passes": 0.0},
        }
        avail.apply_limited_tracking(player, row)
        self.assertTrue(player["stats_limited_tracking"])
        self.assertIn("possession_won", player["stats"])
        self.assertNotIn("key_passes", player["stats"])
        self.assertNotIn("possession_won", player["stats_unavailable"])

    def test_league_almost_all_near_zero_is_limited(self):
        rows = [
            {str(k): str(v) for k, v in _outfield_limited_row("Ada").items()},
            {str(k): str(v) for k, v in _outfield_limited_row("Bea").items()},
        ]
        mapping = avail.analyze_division_availability(rows)
        self.assertIn("Ligat Ha'Al", mapping)
        self.assertIn("key_passes", mapping["Ligat Ha'Al"])
        self.assertNotIn("expected_assists", mapping["Ligat Ha'Al"])

    def test_sparse_leftover_does_not_veto_league(self):
        leftover = _outfield_limited_row("Cal", leftover_key_passes=4)
        rows = [
            {str(k): str(v) for k, v in _outfield_limited_row("Ada").items()},
            {str(k): str(v) for k, v in leftover.items()},
        ]
        self.assertIn("Ligat Ha'Al", avail.analyze_division_availability(rows))

    def test_healthy_league_is_not_limited(self):
        row = {
            str(k): str(v)
            for k, v in _outfield_limited_row("Ada", division="Eredivisie").items()
        }
        row["Interceptions per 90"] = "1.1"
        row["Key Passes per 90"] = "0.9"
        row["Progressive Passes per 90"] = "2.2"
        row["Clearances per 90"] = "0.7"
        mapping = avail.analyze_division_availability([row])
        self.assertNotIn("Eredivisie", mapping)

    def test_below_300_minutes_does_not_stripe_division(self):
        row = {
            str(k): str(v)
            for k, v in _outfield_limited_row("Ada", minutes=180).items()
        }
        self.assertEqual(avail.analyze_division_availability([row]), {})


class TestDetailTransforms(unittest.TestCase):
    def test_linear_and_power_round_trip(self):
        linear = {"type": "linear", "scale": 0.6006, "offset": 0.0143}
        power = {"type": "power", "a": 0.5761, "b": 0.707}
        raw = 2.0
        self.assertAlmostEqual(
            detail.inverse_transform(detail.apply_transform(raw, linear), linear),
            raw,
        )
        self.assertAlmostEqual(
            detail.inverse_transform(detail.apply_transform(raw, power), power),
            raw,
            places=6,
        )

    def test_adjusted_mode_maps_export_into_full_detail(self):
        raw = 0.4
        adjusted = detail.metric_value_for_display(
            raw, "assists", "def", export_level="no_detail", value_mode="adjusted"
        )
        self.assertIsNotNone(adjusted)
        self.assertNotAlmostEqual(adjusted, raw)
        self.assertAlmostEqual(
            detail.metric_value_for_display(
                raw, "assists", "def", export_level="no_detail", value_mode="raw"
            ),
            raw,
        )

    def test_threshold_tree_moves_with_detail_level(self):
        tree = {"def": {"final_third": {"assists": [0.1, 0.2, 0.3, 0.4]}}}
        moved = detail.apply_detail_level_to_threshold_tree(
            tree, export_detail_level="no_detail"
        )
        self.assertNotEqual(moved["def"]["final_third"]["assists"], [0.1, 0.2, 0.3, 0.4])
        spec = {"type": "linear", "scale": 0.6006, "offset": 0.0143}
        expected = [round(detail.apply_transform(x, spec), 4) for x in (0.1, 0.2, 0.3, 0.4)]
        self.assertEqual(moved["def"]["final_third"]["assists"], expected)


class TestAdaptiveBounds(unittest.TestCase):
    def test_xg_prevented_p100_uses_max_of_settings_and_observed(self):
        cuts = ss.resolve_thresholds("gk", "final_third", "xg_prevented")
        setting = ss.implied_percentile_ceiling(cuts, higher_is_better=True)
        below = {
            "pos_group": "gk",
            "minutes": 900,
            "stats": {"xg_prevented": setting - 0.05},
        }
        above = {
            "pos_group": "gk",
            "minutes": 900,
            "stats": {"xg_prevented": setting + 0.15},
        }
        self.assertAlmostEqual(ss.xg_prevented_p100([below]), setting)
        self.assertAlmostEqual(ss.xg_prevented_p100([above]), setting + 0.15)

    def test_limited_league_players_excluded_from_adaptive_max(self):
        cuts = ss.resolve_thresholds("mid", "final_third", "goals")
        setting = ss.implied_percentile_ceiling(cuts, higher_is_better=True)
        limited = {
            "pos_group": "mid",
            "minutes": 900,
            "division": "Ligat Ha'Al",
            "limited_division_tracking": True,
            "stats": {"goals": setting + 5},
        }
        self.assertAlmostEqual(
            ss.adaptive_metric_p100(
                [limited],
                "goals",
                group="mid",
                category="final_third",
                limited_divisions={"Ligat Ha'Al"},
            ),
            setting,
        )


class TestParseStatsExport(unittest.TestCase):
    def test_parse_derives_goals_per90_and_position_group(self):
        text = _csv(
            [
                {
                    "Name": "Ada",
                    "Unique ID": "1",
                    "Best Pos": "ST",
                    "Position": "ST",
                    "Minutes": 900,
                    "Goals": 10,
                    "Goals per 90 minutes": 0.95,
                    "Passes Attempted": 90,
                    "Passes Attempted per 90": 9,
                }
            ]
        )
        players = ss.parse_stats_export(text)
        self.assertEqual(len(players), 1)
        player = players[0]
        self.assertEqual(player["pos_group"], "fwd")
        self.assertAlmostEqual(player["stats"]["goals"], 1.0)
        self.assertAlmostEqual(player["stats"]["passes_attempted"], 9.0)

    def test_zero_minutes_skips_stats(self):
        text = _csv(
            [
                {
                    "Name": "Ada",
                    "Best Pos": "MC",
                    "Minutes": 0,
                    "Goals": 4,
                    "Goals per 90 minutes": 0.4,
                    "Passes Attempted per 90": 8,
                }
            ]
        )
        player = ss.parse_stats_export(text)[0]
        self.assertEqual(player["stats"], {})

    def test_goals_poc_from_xg_overperformance(self):
        text = _csv(
            [
                {
                    "Name": "Ada",
                    "Best Pos": "ST",
                    "Minutes": 900,
                    "Goals": 0,
                    "Goals per 90 minutes": 0.20,
                    "xG": 4.2,
                    "xG-OP": 1.8,
                    "Passes Attempted per 90": 8,
                }
            ]
        )
        player = ss.parse_stats_export(text)[0]
        self.assertAlmostEqual(player["stats"]["goals"], 0.6)

    def test_limited_league_strips_advanced_keeps_universal(self):
        text = _csv([_outfield_limited_row("Ada"), _outfield_limited_row("Bea")])
        players, limited = ss.parse_stats_export_with_meta(text)
        self.assertEqual(limited, ["Ligat Ha'Al"])
        player = players[0]
        self.assertTrue(player["stats_limited_tracking"])
        self.assertTrue(player["limited_division_tracking"])
        self.assertIn("goals", player["stats"])
        self.assertNotIn("key_passes", player["stats"])
        self.assertIn("key_passes", player["stats_unavailable"])
        self.assertNotIn("expected_assists", player["stats_unavailable"])

    def test_set_piece_stats_extracted_by_group(self):
        text = _csv(
            [
                {
                    "Name": "Ada",
                    "Best Pos": "ST",
                    "Minutes": 900,
                    "Passes Attempted per 90": 8,
                    "Penalties Scored": 3,
                    "Penalties Taken": 4,
                    "Penalties Faced": 2,
                    "Penalties Saved": 1,
                }
            ]
        )
        player = ss.parse_stats_export(text)[0]
        self.assertEqual(player["set_piece_stats"]["penalties_scored"], 3.0)
        self.assertEqual(player["set_piece_stats"]["penalties_taken"], 4.0)
        self.assertNotIn("penalties_saved", player["set_piece_stats"])


class TestDisplayHelpers(unittest.TestCase):
    def test_format_metric_display(self):
        self.assertEqual(ss.format_metric_display(12.3, "percent"), "12.3%")
        self.assertEqual(ss.format_metric_display(4.0, "count"), "4")
        self.assertEqual(ss.format_metric_display(0.4, "per90"), "0.40")
        self.assertEqual(ss.format_metric_display(12.50, "per90"), "12.5")


if __name__ == "__main__":
    unittest.main()
