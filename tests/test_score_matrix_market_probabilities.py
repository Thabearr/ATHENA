import math
import unittest

from domain.markets import MarketId, OutcomeId
from domain.model_status import (
    AnalyticalAvailability,
    CalibrationStatus,
    MODEL_STATUS_REGISTRY,
    SettlementCapability,
)
from domain.score_matrix import build_score_matrix
from domain.score_matrix_market_probabilities import (
    MarketProjectionError,
    MarketTopology,
    SpecializedMarketModelRequired,
    project_score_matrix_market,
)


class MarketCapabilityRegistryTests(unittest.TestCase):
    def test_registry_covers_exact_15_market_ids(self):
        self.assertEqual(set(MODEL_STATUS_REGISTRY), set(MarketId))
        self.assertEqual(len(MODEL_STATUS_REGISTRY), 15)

    def test_analytical_capability_is_independent_of_downstream_authority(self):
        for market_id, status in MODEL_STATUS_REGISTRY.items():
            self.assertFalse(status.pricing_authorized, market_id.value)
            self.assertFalse(status.selection_authorized, market_id.value)
            self.assertFalse(status.bet_authorized, market_id.value)

        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.DRAW_NO_BET].analytical_availability,
            AnalyticalAvailability.AVAILABLE,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.DRAW_NO_BET].settlement_capability,
            SettlementCapability.SETTLEMENT_DISTRIBUTION,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.ASIAN_HANDICAP].analytical_availability,
            AnalyticalAvailability.AVAILABLE,
        )

    def test_weh_research_models_are_not_erased_by_legacy_disabled_state(self):
        for market_id in (
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
        ):
            status = MODEL_STATUS_REGISTRY[market_id]
            self.assertEqual(
                status.analytical_availability,
                AnalyticalAvailability.RESEARCH_MODEL_AVAILABLE,
            )
            self.assertEqual(
                status.calibration_status,
                CalibrationStatus.REVIEWED_RESEARCH_FINAL_TEST,
            )
            self.assertIsNotNone(status.probability_method)
            self.assertFalse(status.selection_authorized)

    def test_1up_2up_are_explicit_weekend_model_work_not_fake_proxies(self):
        for market_id in (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
            status = MODEL_STATUS_REGISTRY[market_id]
            self.assertEqual(
                status.analytical_availability,
                AnalyticalAvailability.PENDING_IMPLEMENTATION,
            )
            self.assertEqual(
                status.settlement_capability,
                SettlementCapability.PROVIDER_RULES_AND_PATH_MODEL_REQUIRED,
            )
            self.assertIsNone(status.probability_method)


class ScoreMatrixMarketProjectionTests(unittest.TestCase):
    def setUp(self):
        self.matrix = build_score_matrix(1.72, 1.08)

    @staticmethod
    def _probs(projection):
        return {
            item.outcome_id: item.probability
            for item in projection.outcomes
        }

    def test_match_result_is_a_partition(self):
        projection = project_score_matrix_market(
            self.matrix,
            MarketId.MATCH_RESULT,
        )
        probabilities = self._probs(projection)
        self.assertEqual(
            projection.topology,
            MarketTopology.MUTUALLY_EXCLUSIVE_PARTITION,
        )
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=14)
        self.assertAlmostEqual(probabilities[OutcomeId.HOME], self.matrix.home_win)
        self.assertAlmostEqual(probabilities[OutcomeId.DRAW], self.matrix.draw)
        self.assertAlmostEqual(probabilities[OutcomeId.AWAY], self.matrix.away_win)

    def test_btts_is_a_complement_pair(self):
        projection = project_score_matrix_market(self.matrix, MarketId.BTTS)
        probabilities = self._probs(projection)
        self.assertEqual(projection.topology, MarketTopology.COMPLEMENT_PAIR)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=14)
        self.assertAlmostEqual(probabilities[OutcomeId.YES], self.matrix.btts_yes)
        self.assertAlmostEqual(probabilities[OutcomeId.NO], self.matrix.btts_no)

    def test_result_or_over_pairs_are_exact_complements(self):
        for market_id, result in (
            (MarketId.HOME_OR_OVER_2_5, "HOME"),
            (MarketId.DRAW_OR_OVER_2_5, "DRAW"),
            (MarketId.AWAY_OR_OVER_2_5, "AWAY"),
        ):
            with self.subTest(market_id=market_id):
                projection = project_score_matrix_market(self.matrix, market_id)
                probabilities = self._probs(projection)
                self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=14)
                self.assertAlmostEqual(
                    probabilities[OutcomeId.YES],
                    self.matrix.result_or_over(result, 2.5),
                )

    def test_win_to_nil_pairs_are_exact_complements(self):
        for market_id, expected_yes in (
            (MarketId.HOME_WIN_TO_NIL, self.matrix.home_win_to_nil),
            (MarketId.AWAY_WIN_TO_NIL, self.matrix.away_win_to_nil),
        ):
            with self.subTest(market_id=market_id):
                projection = project_score_matrix_market(self.matrix, market_id)
                probabilities = self._probs(projection)
                self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=14)
                self.assertAlmostEqual(probabilities[OutcomeId.YES], expected_yes)

    def test_total_goals_half_line_partitions_without_push_mass(self):
        projection = project_score_matrix_market(
            self.matrix,
            MarketId.TOTAL_GOALS,
            line=2.5,
        )
        probabilities = self._probs(projection)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=14)
        self.assertAlmostEqual(probabilities[OutcomeId.OVER], self.matrix.over(2.5))
        self.assertAlmostEqual(probabilities[OutcomeId.UNDER], self.matrix.under(2.5))

    def test_total_goals_push_capable_line_fails_closed(self):
        with self.assertRaises(MarketProjectionError):
            project_score_matrix_market(
                self.matrix,
                MarketId.TOTAL_GOALS,
                line=2.0,
            )
        with self.assertRaises(MarketProjectionError):
            project_score_matrix_market(
                self.matrix,
                MarketId.TOTAL_GOALS,
                line=2.25,
            )

    def test_double_chance_is_overlapping_not_partitioned(self):
        projection = project_score_matrix_market(
            self.matrix,
            MarketId.DOUBLE_CHANCE,
        )
        probabilities = self._probs(projection)
        self.assertEqual(projection.topology, MarketTopology.OVERLAPPING_EVENTS)
        self.assertAlmostEqual(
            probabilities[OutcomeId.HOME_OR_DRAW],
            self.matrix.home_win + self.matrix.draw,
            places=14,
        )
        self.assertAlmostEqual(
            probabilities[OutcomeId.DRAW_OR_AWAY],
            self.matrix.draw + self.matrix.away_win,
            places=14,
        )
        self.assertAlmostEqual(
            probabilities[OutcomeId.HOME_OR_AWAY],
            self.matrix.home_win + self.matrix.away_win,
            places=14,
        )
        self.assertGreater(sum(probabilities.values()), 1.0)

    def test_dnb_preserves_win_push_loss_mass_and_orientation(self):
        projection = project_score_matrix_market(
            self.matrix,
            MarketId.DRAW_NO_BET,
        )
        self.assertEqual(
            projection.topology,
            MarketTopology.SETTLEMENT_DISTRIBUTIONS,
        )
        outcomes = {item.outcome_id: item.settlement for item in projection.outcomes}
        home = outcomes[OutcomeId.HOME]
        away = outcomes[OutcomeId.AWAY]
        self.assertAlmostEqual(home.full_win, self.matrix.home_win, places=14)
        self.assertAlmostEqual(home.push, self.matrix.draw, places=14)
        self.assertAlmostEqual(home.full_loss, self.matrix.away_win, places=14)
        self.assertAlmostEqual(away.full_win, self.matrix.away_win, places=14)
        self.assertAlmostEqual(away.push, self.matrix.draw, places=14)
        self.assertAlmostEqual(away.full_loss, self.matrix.home_win, places=14)
        self.assertAlmostEqual(home.total_probability, 1.0, places=12)
        self.assertAlmostEqual(away.total_probability, 1.0, places=12)

    def test_asian_handicap_preserves_integer_half_and_quarter_settlement(self):
        for line in (-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0):
            with self.subTest(line=line):
                projection = project_score_matrix_market(
                    self.matrix,
                    MarketId.ASIAN_HANDICAP,
                    line=line,
                )
                outcomes = {
                    item.outcome_id: item.settlement
                    for item in projection.outcomes
                }
                home = outcomes[OutcomeId.HOME]
                away = outcomes[OutcomeId.AWAY]
                self.assertAlmostEqual(home.total_probability, 1.0, places=12)
                self.assertAlmostEqual(away.total_probability, 1.0, places=12)
                self.assertEqual(home.line, line)
                self.assertEqual(away.line, -line)
                self.assertAlmostEqual(
                    home.effective_win_mass,
                    away.effective_loss_mass,
                    places=12,
                )
                self.assertAlmostEqual(
                    home.effective_loss_mass,
                    away.effective_win_mass,
                    places=12,
                )

    def test_asian_handicap_non_quarter_line_fails_closed(self):
        with self.assertRaises(ValueError):
            project_score_matrix_market(
                self.matrix,
                MarketId.ASIAN_HANDICAP,
                line=0.3,
            )

    def test_specialized_markets_cannot_receive_score_matrix_proxy(self):
        for market_id in (
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
            MarketId.MATCH_RESULT_1UP,
            MarketId.MATCH_RESULT_2UP,
        ):
            with self.subTest(market_id=market_id):
                with self.assertRaises(SpecializedMarketModelRequired):
                    project_score_matrix_market(self.matrix, market_id)

    def test_projector_never_grants_downstream_authority(self):
        projection = project_score_matrix_market(
            self.matrix,
            MarketId.MATCH_RESULT,
        )
        self.assertTrue(projection.analytical_available)
        self.assertFalse(projection.pricing_authorized)
        self.assertFalse(projection.selection_authorized)
        self.assertFalse(projection.bet_authorized)


if __name__ == "__main__":
    unittest.main()
