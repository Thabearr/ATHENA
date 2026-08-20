import math
import unittest

from domain.score_matrix import (
    DEFAULT_TAIL_TOLERANCE,
    NORMALIZATION_METHOD,
    build_score_matrix,
)
from intelligence.match_analyst import build_viable_market_candidates


class NormalizedScoreMatrixTests(unittest.TestCase):
    def setUp(self):
        self.home_xg = 1.65
        self.away_xg = 1.10
        self.matrix = build_score_matrix(self.home_xg, self.away_xg)

    def test_matrix_is_normalized_with_bounded_omitted_tail(self):
        self.assertAlmostEqual(
            math.fsum(self.matrix.probabilities.values()),
            1.0,
            places=14,
        )
        self.assertLessEqual(
            self.matrix.omitted_tail_mass,
            DEFAULT_TAIL_TOLERANCE,
        )
        self.assertEqual(
            self.matrix.normalization_method,
            NORMALIZATION_METHOD,
        )

    def test_match_result_probabilities_partition_matrix(self):
        self.assertAlmostEqual(
            self.matrix.home_win
            + self.matrix.draw
            + self.matrix.away_win,
            1.0,
            places=14,
        )

    def test_btts_probabilities_partition_matrix(self):
        self.assertAlmostEqual(
            self.matrix.btts_yes + self.matrix.btts_no,
            1.0,
            places=14,
        )

    def test_double_chance_is_exact_result_sum(self):
        self.assertAlmostEqual(
            self.matrix.double_chance_home_or_draw,
            self.matrix.home_win + self.matrix.draw,
            places=15,
        )
        self.assertAlmostEqual(
            self.matrix.double_chance_draw_or_away,
            self.matrix.draw + self.matrix.away_win,
            places=15,
        )
        self.assertAlmostEqual(
            self.matrix.double_chance_home_or_away,
            self.matrix.home_win + self.matrix.away_win,
            places=15,
        )

    def test_raw_zero_zero_matches_independent_poisson_identity(self):
        self.assertAlmostEqual(
            self.matrix.raw_probability(0, 0),
            math.exp(-(self.home_xg + self.away_xg)),
            places=15,
        )

    def test_total_goals_agree_with_combined_poisson_distribution(self):
        total_xg = self.home_xg + self.away_xg
        analytic_under_25 = math.exp(-total_xg) * (
            1.0 + total_xg + (total_xg ** 2) / 2.0
        )
        self.assertAlmostEqual(
            self.matrix.under(2.5),
            analytic_under_25,
            delta=DEFAULT_TAIL_TOLERANCE * 2,
        )
        self.assertAlmostEqual(
            self.matrix.over(2.5),
            1.0 - analytic_under_25,
            delta=DEFAULT_TAIL_TOLERANCE * 2,
        )

    def test_result_or_over_25_uses_union_with_overlap_removed(self):
        over_25 = self.matrix.over(2.5)
        result_predicates = {
            "HOME": lambda home, away: home > away,
            "DRAW": lambda home, away: home == away,
            "AWAY": lambda home, away: away > home,
        }
        result_probabilities = {
            "HOME": self.matrix.home_win,
            "DRAW": self.matrix.draw,
            "AWAY": self.matrix.away_win,
        }
        for result, result_predicate in result_predicates.items():
            overlap = self.matrix.sum_where(
                lambda home, away, predicate=result_predicate: (
                    predicate(home, away) and home + away > 2
                )
            )
            expected_union = (
                result_probabilities[result] + over_25 - overlap
            )
            with self.subTest(result=result):
                self.assertAlmostEqual(
                    self.matrix.result_or_over(result),
                    expected_union,
                    places=14,
                )

    def test_win_to_nil_contains_only_correct_scorelines(self):
        expected_home = math.fsum(
            probability
            for (home, away), probability
            in self.matrix.probabilities.items()
            if home > 0 and away == 0
        )
        expected_away = math.fsum(
            probability
            for (home, away), probability
            in self.matrix.probabilities.items()
            if away > 0 and home == 0
        )
        self.assertAlmostEqual(
            self.matrix.home_win_to_nil,
            expected_home,
            places=15,
        )
        self.assertAlmostEqual(
            self.matrix.away_win_to_nil,
            expected_away,
            places=15,
        )
        self.assertNotIn((0, 0), {
            score
            for score, probability in self.matrix.probabilities.items()
            if probability
            and score[0] > 0
            and score[1] == 0
        })

    def test_high_expected_goals_expand_beyond_five(self):
        high_scoring = build_score_matrix(8.0, 7.0)

        self.assertGreater(high_scoring.max_home_goal, 5)
        self.assertGreater(high_scoring.max_away_goal, 5)
        self.assertLessEqual(
            high_scoring.omitted_tail_mass,
            DEFAULT_TAIL_TOLERANCE,
        )

    def test_omitted_scorelines_are_not_reported_as_zero_probability(self):
        with self.assertRaises(KeyError):
            self.matrix.probability(
                self.matrix.max_home_goal + 1,
                self.matrix.max_away_goal + 1,
            )

    def test_invalid_expected_goals_are_rejected(self):
        invalid_values = [
            float("nan"),
            float("inf"),
            float("-inf"),
            -0.01,
            True,
            False,
        ]
        for invalid in invalid_values:
            with self.subTest(home=invalid):
                with self.assertRaises(ValueError):
                    build_score_matrix(invalid, 1.0)
            with self.subTest(away=invalid):
                with self.assertRaises(ValueError):
                    build_score_matrix(1.0, invalid)

    def test_handicap_half_goal_lines_match_score_matrix_sums(self):
        for side in ("HOME", "AWAY"):
            for line in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5):
                if side == "HOME":
                    expected = self.matrix.sum_where(
                        lambda home, away, handicap=line: (
                            home + handicap > away
                        )
                    )
                else:
                    expected = self.matrix.sum_where(
                        lambda home, away, handicap=line: (
                            away + handicap > home
                        )
                    )
                with self.subTest(side=side, line=line):
                    self.assertAlmostEqual(
                        self.matrix.asian_handicap_cover(side, line),
                        expected,
                        places=15,
                    )

    def test_handicap_integer_lines_are_rejected(self):
        for line in (-2, -1, 0, 1, 2):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    self.matrix.asian_handicap_cover("HOME", line)

    def test_handicap_quarter_lines_are_rejected(self):
        for line in (-1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    self.matrix.asian_handicap_cover("AWAY", line)

    def test_handicap_invalid_numeric_values_are_rejected(self):
        for line in (
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            False,
        ):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    self.matrix.asian_handicap_cover("HOME", line)

    def test_ranking_boost_cannot_rescue_negative_baseline_delta(self):
        candidates = build_viable_market_candidates(
            {"DC_1X": 0.70},
            {"DC_1X": 0.50},
        )

        self.assertEqual(candidates, [])

    def test_ranking_boost_cannot_create_selection_authority(self):
        probabilities = {
            "DC_1X": 0.74,
            "DC_X2": 0.65,
        }
        unboosted = build_viable_market_candidates(probabilities, {})
        boosted = build_viable_market_candidates(
            probabilities,
            {"DC_1X": 0.02},
        )

        self.assertEqual(unboosted, [])
        self.assertEqual(boosted, [])

    def test_ranking_boost_does_not_promote_analytical_probability(self):
        unboosted = build_viable_market_candidates(
            {"DC_1X": 0.73},
            {},
        )
        boosted = build_viable_market_candidates(
            {"DC_1X": 0.73},
            {"DC_1X": 0.20},
        )

        self.assertEqual(unboosted, [])
        self.assertEqual(boosted, [])


if __name__ == "__main__":
    unittest.main()
