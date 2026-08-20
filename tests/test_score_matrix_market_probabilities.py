import ast
import hashlib
import inspect
import math
from pathlib import Path
import unittest

from domain.markets import MarketId, OutcomeId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    CalibrationStatus,
    FreshConfirmationStatus,
    MODEL_STATUS_REGISTRY,
    PricingAuthority,
    ProbabilityInputNamespace,
    SelectionAuthority,
    SettlementCapability,
)
from domain.score_matrix import NORMALIZATION_METHOD, build_score_matrix
from domain.score_matrix_market_probabilities import (
    AnalyticalProjectionError,
    MarketTopology,
    canonical_score_matrix_market_projection_bytes,
    project_score_matrix_market,
    project_score_matrix_markets,
    sha256_score_matrix_market_projection,
)
from domain.score_matrix_settlement import (
    asian_handicap_settlement,
    draw_no_bet_settlement,
)
from intelligence.fixture_reasoner import FixtureOption, FixtureReasoner
from intelligence.match_analyst import build_viable_market_candidates


class ScoreMatrixMarketProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.matrix = build_score_matrix(1.65, 1.10)

    @staticmethod
    def probabilities(projection):
        return {
            item.outcome_id: item.probability
            for item in projection.event_probabilities
        }

    @staticmethod
    def settlements(projection):
        return {
            item.outcome_id: item.settlement
            for item in projection.settlement_distributions
        }

    def assertPartition(self, values):
        self.assertTrue(
            math.isclose(math.fsum(values), 1.0, rel_tol=0.0, abs_tol=1e-12)
        )

    def assertSettlementPartition(self, settlement):
        self.assertPartition((
            settlement.full_win,
            settlement.half_win,
            settlement.push,
            settlement.half_loss,
            settlement.full_loss,
        ))
        self.assertAlmostEqual(
            settlement.active_stake_mass + settlement.neutral_stake_mass,
            1.0,
            places=14,
        )

    def test_registry_is_exhaustive_and_capability_is_not_authority(self):
        self.assertEqual(set(MODEL_STATUS_REGISTRY), set(MarketId))
        self.assertEqual(len(MODEL_STATUS_REGISTRY), 15)
        available = {
            market
            for market, status in MODEL_STATUS_REGISTRY.items()
            if status.analytical_probability_capability
            is AnalyticalProbabilityCapability.AVAILABLE
        }
        self.assertEqual(set(MarketId) - available, set())
        for status in MODEL_STATUS_REGISTRY.values():
            self.assertIs(status.pricing_authority, PricingAuthority.NOT_AUTHORIZED)
            self.assertIs(
                status.selection_authority,
                SelectionAuthority.NOT_AUTHORIZED,
            )
            self.assertFalse(status.pricing_authorized)
            self.assertFalse(status.selectable)

    def test_calibration_and_fresh_confirmation_remain_unapproved(self):
        for status in MODEL_STATUS_REGISTRY.values():
            if status.analytically_available:
                if (
                    status.probability_input_namespace
                    is ProbabilityInputNamespace.SPECIALIZED_WEH_PRE_MATCH_FEATURES
                ):
                    self.assertIs(
                        status.calibration_status,
                        CalibrationStatus.FROZEN_STAGE_4B_CALIBRATION_RESEARCH_EVIDENCE,
                    )
                else:
                    self.assertIs(
                        status.calibration_status,
                        CalibrationStatus.MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED,
                    )
                self.assertIs(
                    status.fresh_confirmation_status,
                    FreshConfirmationStatus.ZERO_COMMITTED_OBSERVATIONS,
                )

    def test_match_result_and_btts_partition(self):
        result = self.probabilities(
            project_score_matrix_market(self.matrix, MarketId.MATCH_RESULT)
        )
        self.assertPartition(result.values())
        self.assertAlmostEqual(result[OutcomeId.HOME], self.matrix.home_win)
        self.assertAlmostEqual(result[OutcomeId.DRAW], self.matrix.draw)
        self.assertAlmostEqual(result[OutcomeId.AWAY], self.matrix.away_win)

        btts = self.probabilities(
            project_score_matrix_market(self.matrix, MarketId.BTTS)
        )
        self.assertPartition(btts.values())
        self.assertAlmostEqual(btts[OutcomeId.YES], self.matrix.btts_yes)
        self.assertAlmostEqual(btts[OutcomeId.NO], self.matrix.btts_no)

    def test_result_or_over_and_win_to_nil_binary_complements_partition(self):
        cases = {
            MarketId.DRAW_OR_OVER_2_5: self.matrix.result_or_over("DRAW"),
            MarketId.AWAY_OR_OVER_2_5: self.matrix.result_or_over("AWAY"),
            MarketId.HOME_OR_OVER_2_5: self.matrix.result_or_over("HOME"),
            MarketId.HOME_WIN_TO_NIL: self.matrix.home_win_to_nil,
            MarketId.AWAY_WIN_TO_NIL: self.matrix.away_win_to_nil,
        }
        for market, expected_yes in cases.items():
            with self.subTest(market=market):
                values = self.probabilities(
                    project_score_matrix_market(self.matrix, market)
                )
                self.assertPartition(values.values())
                self.assertAlmostEqual(values[OutcomeId.YES], expected_yes)
                self.assertAlmostEqual(values[OutcomeId.NO], 1.0 - expected_yes)

    def test_total_goals_accepts_only_exact_half_lines(self):
        for line in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
            with self.subTest(line=line):
                projection = project_score_matrix_market(
                    self.matrix, MarketId.TOTAL_GOALS, line=line
                )
                values = self.probabilities(projection)
                self.assertPartition(values.values())
                self.assertAlmostEqual(values[OutcomeId.OVER], self.matrix.over(line))
                self.assertAlmostEqual(values[OutcomeId.UNDER], self.matrix.under(line))
        for unsupported in (0.0, 1.0, 2.0, 2.25, 2.75, -0.5, True, math.inf):
            with self.subTest(unsupported=unsupported):
                with self.assertRaises(AnalyticalProjectionError):
                    project_score_matrix_market(
                        self.matrix, MarketId.TOTAL_GOALS, line=unsupported
                    )

    def test_double_chance_is_overlapping_not_a_partition(self):
        projection = project_score_matrix_market(
            self.matrix, MarketId.DOUBLE_CHANCE
        )
        values = self.probabilities(projection)
        self.assertIs(projection.topology, MarketTopology.OVERLAPPING_EVENTS)
        self.assertAlmostEqual(
            values[OutcomeId.HOME_OR_DRAW], self.matrix.home_win + self.matrix.draw
        )
        self.assertAlmostEqual(
            values[OutcomeId.DRAW_OR_AWAY], self.matrix.draw + self.matrix.away_win
        )
        self.assertAlmostEqual(
            values[OutcomeId.HOME_OR_AWAY], self.matrix.home_win + self.matrix.away_win
        )
        self.assertGreater(math.fsum(values.values()), 1.0)

    def test_dnb_preserves_complete_oriented_settlement(self):
        projection = project_score_matrix_market(self.matrix, MarketId.DRAW_NO_BET)
        self.assertIs(projection.topology, MarketTopology.SETTLEMENT_DISTRIBUTIONS)
        self.assertEqual(projection.event_probabilities, ())
        values = self.settlements(projection)
        home = values[OutcomeId.HOME]
        away = values[OutcomeId.AWAY]
        self.assertEqual(home, draw_no_bet_settlement(self.matrix, "HOME"))
        self.assertEqual(away, draw_no_bet_settlement(self.matrix, "AWAY"))
        self.assertAlmostEqual(home.full_win, away.full_loss)
        self.assertAlmostEqual(home.push, away.push)
        self.assertAlmostEqual(home.full_loss, away.full_win)
        self.assertSettlementPartition(home)
        self.assertSettlementPartition(away)
        self.assertIsNotNone(home.break_even_probability)
        self.assertIsNotNone(home.fair_decimal_odds)

    def test_asian_handicap_preserves_integer_half_and_quarter_settlement(self):
        for home_line in (-2.0, -1.5, -0.75, -0.25, 0.0, 0.25, 0.5, 1.75):
            with self.subTest(home_line=home_line):
                projection = project_score_matrix_market(
                    self.matrix, MarketId.ASIAN_HANDICAP, line=home_line
                )
                values = self.settlements(projection)
                home = values[OutcomeId.HOME]
                away = values[OutcomeId.AWAY]
                self.assertEqual(
                    home,
                    asian_handicap_settlement(self.matrix, "HOME", home_line),
                )
                self.assertEqual(
                    away,
                    asian_handicap_settlement(self.matrix, "AWAY", -home_line),
                )
                self.assertAlmostEqual(home.full_win, away.full_loss)
                self.assertAlmostEqual(home.half_win, away.half_loss)
                self.assertAlmostEqual(home.push, away.push)
                self.assertAlmostEqual(home.half_loss, away.half_win)
                self.assertAlmostEqual(home.full_loss, away.full_win)
                self.assertSettlementPartition(home)
                self.assertSettlementPartition(away)
        for invalid in (0.1, 0.3, -1.1, math.pi, True, math.nan):
            with self.subTest(invalid=invalid):
                with self.assertRaises(AnalyticalProjectionError):
                    project_score_matrix_market(
                        self.matrix, MarketId.ASIAN_HANDICAP, line=invalid
                    )

    def test_non_score_matrix_markets_receive_no_full_time_proxy(self):
        unsupported_by_this_projector = (
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
            MarketId.MATCH_RESULT_1UP,
            MarketId.MATCH_RESULT_2UP,
        )
        for market in unsupported_by_this_projector:
            with self.subTest(market=market):
                with self.assertRaises(AnalyticalProjectionError):
                    project_score_matrix_market(self.matrix, market)

    def test_all_supported_houses_project_without_blocked_markets(self):
        projections = project_score_matrix_markets(
            self.matrix,
            total_goal_lines=(1.5, 2.5, 3.5),
            asian_handicap_home_lines=(-0.25, 0.0, 0.5),
        )
        represented = {item.market_id for item in projections}
        self.assertEqual(
            represented,
            {
                market
                for market, status in MODEL_STATUS_REGISTRY.items()
                if status.analytically_available
                and status.probability_input_namespace
                is ProbabilityInputNamespace.GENERIC_FIXTURE_MODEL_FEATURES
            },
        )

    def test_projector_accepts_no_price_and_grants_no_authority(self):
        signature = inspect.signature(project_score_matrix_market)
        self.assertNotIn("bookmaker_odds", signature.parameters)
        self.assertNotIn("price", signature.parameters)
        projection = project_score_matrix_market(self.matrix, MarketId.MATCH_RESULT)
        self.assertTrue(projection.safety)
        self.assertTrue(all(value is False for value in projection.safety.values()))
        payload = projection.to_dict()
        self.assertNotIn("bookmaker_odds", payload)
        self.assertNotIn("kelly", payload)

    def test_canonical_projection_is_deterministic(self):
        projection = project_score_matrix_market(
            self.matrix, MarketId.ASIAN_HANDICAP, line=-0.25
        )
        first = canonical_score_matrix_market_projection_bytes(projection)
        second = canonical_score_matrix_market_projection_bytes(projection)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertFalse(first.endswith(b"\n\n"))
        self.assertEqual(
            sha256_score_matrix_market_projection(projection),
            hashlib.sha256(first).hexdigest(),
        )

    def test_existing_matrix_normalization_and_tail_contract_is_unchanged(self):
        self.assertEqual(self.matrix.normalization_method, NORMALIZATION_METHOD)
        self.assertAlmostEqual(math.fsum(self.matrix.probabilities.values()), 1.0)
        self.assertLessEqual(self.matrix.omitted_tail_mass, self.matrix.tail_tolerance)

    def test_legacy_candidate_builder_cannot_promote_analytical_capability(self):
        self.assertEqual(
            build_viable_market_candidates(
                {"DC_1X": 0.95, "GG_YES": 0.95, "AH_HOME_PLUS_15": 0.95},
                {},
            ),
            [],
        )

    def test_bare_bookmaker_odds_do_not_create_selection_authority(self):
        verdicts = FixtureReasoner().analyze([
            FixtureOption(
                "1X2",
                "Home Win",
                0.60,
                bookmaker_odds=2.1,
                market_id=MarketId.MATCH_RESULT,
            ),
            FixtureOption(
                "1X2",
                "Draw",
                0.20,
                bookmaker_odds=3.4,
                market_id=MarketId.MATCH_RESULT,
            ),
            FixtureOption(
                "1X2",
                "Away Win",
                0.20,
                bookmaker_odds=3.8,
                market_id=MarketId.MATCH_RESULT,
            ),
        ])
        self.assertTrue(
            all(item.status == "ANALYTICAL_CANDIDATE" for item in verdicts)
        )
        self.assertTrue(all(item.fair_prob is None for item in verdicts))
        self.assertTrue(all(item.edge_pp is None for item in verdicts))
        self.assertTrue(all(item.kelly_stake_pct is None for item in verdicts))

    def test_projector_static_boundary_excludes_prices_and_betting(self):
        source_path = (
            Path(__file__).resolve().parents[1]
            / "domain"
            / "score_matrix_market_probabilities.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        forbidden = {
            "domain.pricing",
            "intelligence.fixture_reasoner",
            "intelligence.prediction_engine",
            "services.betting_service",
            "requests",
            "sqlite3",
        }
        self.assertTrue(imported.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
