import math
import unittest

from domain.score_matrix import build_score_matrix
from domain.score_matrix_settlement import (
    SettlementProbabilities,
    asian_handicap_settlement,
    draw_no_bet_settlement,
)


class ScoreMatrixSettlementTests(unittest.TestCase):
    def setUp(self):
        self.matrix = build_score_matrix(1.65, 1.10)

    def assertSettlementPartitions(self, settlement):
        self.assertAlmostEqual(settlement.total_probability, 1.0, places=14)
        self.assertAlmostEqual(
            settlement.effective_win_mass
            + settlement.effective_loss_mass
            + settlement.neutral_stake_mass,
            1.0,
            places=14,
        )

    def test_home_dnb_preserves_draw_as_explicit_push(self):
        settlement = draw_no_bet_settlement(self.matrix, "HOME")

        self.assertAlmostEqual(settlement.full_win, self.matrix.home_win, places=15)
        self.assertEqual(settlement.half_win, 0.0)
        self.assertAlmostEqual(settlement.push, self.matrix.draw, places=15)
        self.assertEqual(settlement.half_loss, 0.0)
        self.assertAlmostEqual(settlement.full_loss, self.matrix.away_win, places=15)
        self.assertAlmostEqual(
            settlement.settlement_adjusted_win_probability,
            self.matrix.home_win / (self.matrix.home_win + self.matrix.away_win),
            places=15,
        )
        self.assertSettlementPartitions(settlement)

    def test_away_dnb_is_exact_mirror(self):
        home = draw_no_bet_settlement(self.matrix, "HOME")
        away = draw_no_bet_settlement(self.matrix, "AWAY")

        self.assertAlmostEqual(home.full_win, away.full_loss, places=15)
        self.assertAlmostEqual(home.push, away.push, places=15)
        self.assertAlmostEqual(home.full_loss, away.full_win, places=15)
        self.assertAlmostEqual(
            home.settlement_adjusted_win_probability
            + away.settlement_adjusted_win_probability,
            1.0,
            places=15,
        )

    def test_all_draw_dnb_has_no_invented_action_probability(self):
        matrix = build_score_matrix(0.0, 0.0)
        settlement = draw_no_bet_settlement(matrix, "HOME")

        self.assertEqual(settlement.full_win, 0.0)
        self.assertEqual(settlement.push, 1.0)
        self.assertEqual(settlement.full_loss, 0.0)
        self.assertIsNone(settlement.settlement_adjusted_win_probability)
        self.assertIsNone(settlement.fair_decimal_odds)
        self.assertEqual(settlement.expected_profit(2.0), 0.0)

    def test_dnb_fair_odds_are_zero_expected_profit(self):
        settlement = draw_no_bet_settlement(self.matrix, "HOME")
        fair_odds = settlement.fair_decimal_odds

        self.assertIsNotNone(fair_odds)
        self.assertAlmostEqual(settlement.expected_profit(fair_odds), 0.0, places=14)
        self.assertGreater(settlement.expected_profit(fair_odds + 0.10), 0.0)
        self.assertLess(settlement.expected_profit(fair_odds - 0.10), 0.0)

    def test_half_goal_handicap_matches_existing_cover_probability(self):
        for side in ("HOME", "AWAY"):
            for line in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5):
                with self.subTest(side=side, line=line):
                    settlement = asian_handicap_settlement(self.matrix, side, line)
                    self.assertEqual(settlement.component_lines, (line,))
                    self.assertEqual(settlement.half_win, 0.0)
                    self.assertEqual(settlement.push, 0.0)
                    self.assertEqual(settlement.half_loss, 0.0)
                    self.assertAlmostEqual(
                        settlement.full_win,
                        self.matrix.asian_handicap_cover(side, line),
                        places=15,
                    )
                    self.assertSettlementPartitions(settlement)

    def test_zero_handicap_is_dnb_settlement_partition(self):
        ah = asian_handicap_settlement(self.matrix, "HOME", 0.0)
        dnb = draw_no_bet_settlement(self.matrix, "HOME")

        self.assertEqual(ah.component_lines, (0.0,))
        self.assertAlmostEqual(ah.full_win, dnb.full_win, places=15)
        self.assertAlmostEqual(ah.push, dnb.push, places=15)
        self.assertAlmostEqual(ah.full_loss, dnb.full_loss, places=15)
        self.assertAlmostEqual(
            ah.settlement_adjusted_win_probability,
            dnb.settlement_adjusted_win_probability,
            places=15,
        )

    def test_home_minus_quarter_turns_draw_into_half_loss(self):
        settlement = asian_handicap_settlement(self.matrix, "HOME", -0.25)

        self.assertEqual(settlement.component_lines, (-0.5, 0.0))
        self.assertAlmostEqual(settlement.full_win, self.matrix.home_win, places=15)
        self.assertEqual(settlement.half_win, 0.0)
        self.assertEqual(settlement.push, 0.0)
        self.assertAlmostEqual(settlement.half_loss, self.matrix.draw, places=15)
        self.assertAlmostEqual(settlement.full_loss, self.matrix.away_win, places=15)
        self.assertSettlementPartitions(settlement)

    def test_home_plus_quarter_turns_draw_into_half_win(self):
        settlement = asian_handicap_settlement(self.matrix, "HOME", 0.25)

        self.assertEqual(settlement.component_lines, (0.0, 0.5))
        self.assertAlmostEqual(settlement.full_win, self.matrix.home_win, places=15)
        self.assertAlmostEqual(settlement.half_win, self.matrix.draw, places=15)
        self.assertEqual(settlement.push, 0.0)
        self.assertEqual(settlement.half_loss, 0.0)
        self.assertAlmostEqual(settlement.full_loss, self.matrix.away_win, places=15)
        self.assertSettlementPartitions(settlement)

    def test_home_minus_three_quarters_has_half_win_at_one_goal_margin(self):
        settlement = asian_handicap_settlement(self.matrix, "HOME", -0.75)
        one_goal_home_win = self.matrix.sum_where(
            lambda home, away: home - away == 1
        )
        two_plus_home_win = self.matrix.sum_where(
            lambda home, away: home - away >= 2
        )
        not_home_win = self.matrix.sum_where(lambda home, away: home <= away)

        self.assertEqual(settlement.component_lines, (-1.0, -0.5))
        self.assertAlmostEqual(settlement.full_win, two_plus_home_win, places=15)
        self.assertAlmostEqual(settlement.half_win, one_goal_home_win, places=15)
        self.assertEqual(settlement.push, 0.0)
        self.assertEqual(settlement.half_loss, 0.0)
        self.assertAlmostEqual(settlement.full_loss, not_home_win, places=15)

    def test_home_plus_three_quarters_has_half_loss_when_losing_by_one(self):
        settlement = asian_handicap_settlement(self.matrix, "HOME", 0.75)
        home_not_losing = self.matrix.sum_where(lambda home, away: home >= away)
        one_goal_home_loss = self.matrix.sum_where(
            lambda home, away: away - home == 1
        )
        two_plus_home_loss = self.matrix.sum_where(
            lambda home, away: away - home >= 2
        )

        self.assertEqual(settlement.component_lines, (0.5, 1.0))
        self.assertAlmostEqual(settlement.full_win, home_not_losing, places=15)
        self.assertEqual(settlement.half_win, 0.0)
        self.assertEqual(settlement.push, 0.0)
        self.assertAlmostEqual(settlement.half_loss, one_goal_home_loss, places=15)
        self.assertAlmostEqual(settlement.full_loss, two_plus_home_loss, places=15)

    def test_opposite_side_and_opposite_line_are_settlement_mirrors(self):
        for line in (-2.0, -1.75, -1.0, -0.75, -0.25, 0.0, 0.25, 0.5, 1.25, 2.0):
            with self.subTest(line=line):
                home = asian_handicap_settlement(self.matrix, "HOME", line)
                away = asian_handicap_settlement(self.matrix, "AWAY", -line)
                self.assertAlmostEqual(home.full_win, away.full_loss, places=15)
                self.assertAlmostEqual(home.half_win, away.half_loss, places=15)
                self.assertAlmostEqual(home.push, away.push, places=15)
                self.assertAlmostEqual(home.half_loss, away.half_win, places=15)
                self.assertAlmostEqual(home.full_loss, away.full_win, places=15)

    def test_quarter_handicap_fair_odds_are_zero_expected_profit(self):
        for line in (-1.75, -0.75, -0.25, 0.25, 0.75, 1.25):
            with self.subTest(line=line):
                settlement = asian_handicap_settlement(self.matrix, "HOME", line)
                fair_odds = settlement.fair_decimal_odds
                self.assertIsNotNone(fair_odds)
                self.assertAlmostEqual(
                    settlement.expected_profit(fair_odds),
                    0.0,
                    places=14,
                )

    def test_non_quarter_handicap_lines_fail_closed(self):
        for line in (-0.10, 0.10, 0.30, 1.10, math.pi):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    asian_handicap_settlement(self.matrix, "HOME", line)

    def test_invalid_handicap_inputs_fail_closed(self):
        for line in (float("nan"), float("inf"), float("-inf"), True, False):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    asian_handicap_settlement(self.matrix, "HOME", line)
        for side in ("", "DRAW", None, 1):
            with self.subTest(side=side):
                with self.assertRaises(ValueError):
                    asian_handicap_settlement(self.matrix, side, 0.5)

    def test_expected_profit_rejects_invalid_decimal_odds(self):
        settlement = draw_no_bet_settlement(self.matrix, "HOME")
        for odds in (0.99, 0.0, -1.0, float("nan"), float("inf"), True, False):
            with self.subTest(odds=odds):
                with self.assertRaises(ValueError):
                    settlement.expected_profit(odds)

    def test_distribution_constructor_rejects_non_partition(self):
        with self.assertRaises(ValueError):
            SettlementProbabilities(
                full_win=0.4,
                half_win=0.0,
                push=0.2,
                half_loss=0.0,
                full_loss=0.3,
                method="test",
                side="HOME",
            )


if __name__ == "__main__":
    unittest.main()
