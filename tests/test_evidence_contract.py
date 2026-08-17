import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from domain.markets import (
    MARKET_REGISTRY,
    DecisionStatus,
    MarketId,
    OutcomeId,
    make_selection,
    resolve_legacy_selection,
)
from domain.model_status import (
    MODEL_STATUS_REGISTRY,
    MissingInputPolicy,
    ModelStatus,
)
from domain.pricing import parse_bookmaker_quotes, price_selection
from intelligence.match_analyst import (
    MatchAnalyst,
    build_viable_market_candidates,
)
from intelligence.fixture_reasoner import FixtureOption, FixtureReasoner
from intelligence.acca_filter import AccaFilter
from services.analysis_pipeline import AnalysisPipeline


class StubFormService:
    def __init__(self, form_score=0.60, live_ratio=1.0):
        self.form_score = form_score
        self.live_ratio = live_ratio

    def get_recent_form_score(self, team_id, match_date):
        return self.form_score

    def get_data_freshness(self, team_id, match_date):
        return {"live_ratio": self.live_ratio}

    def get_last_match_date(self, team_id, match_date):
        return None


class StubFatigueEngine:
    def analyze_fixture_fatigue_clash(
        self,
        home_id,
        away_id,
        match_date,
        home_last_date,
        away_last_date,
    ):
        return {"fatigue_differential": 0.0}


class StubRefereeEngine:
    def __init__(self, has_data=False):
        self.has_data = has_data

    def check_referee_anomaly(self, fixture_id):
        if self.has_data:
            return {
                "has_data": True,
                "high_volatility": False,
            }
        return {"has_data": False}


class EvidenceContractTests(unittest.TestCase):
    QUOTE_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

    def _analyst(
        self,
        *,
        form_score=0.60,
        live_ratio=1.0,
        referee_has_data=False,
    ):
        analyst = object.__new__(MatchAnalyst)
        analyst.form_eng = SimpleNamespace(
            form_service=StubFormService(form_score, live_ratio)
        )
        analyst.motivation_engine = object()
        analyst.weather_engine = object()
        analyst.fatigue_eng = StubFatigueEngine()
        analyst.injury_eng = object()
        analyst.ref_eng = StubRefereeEngine(referee_has_data)
        analyst.risk_eng = object()
        analyst.ml_eng = SimpleNamespace(
            predict=lambda *args, **kwargs: None
        )
        return analyst

    def _fixture_context(self):
        return {
            "fixture_id": "fixture-evidence-1",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "home_id": 101,
            "away_id": 202,
            "match_date": "2026-07-29T15:00:00",
            "data_source": "test_fixture",
            "is_knockout": False,
            "is_backtest": False,
            "home_pre_elo": 1520,
            "away_pre_elo": 1480,
        }

    def _compile(self, **analyst_kwargs):
        return self._analyst(**analyst_kwargs).compile_master_fixture_prediction(
            self._fixture_context()
        )

    @staticmethod
    def _quotes_for_selection(
        selection,
        odds=4.0,
        *,
        line=None,
        source="test_bookmaker",
        snapshot_id="snapshot-1",
        observed_at=None,
    ):
        quote_line = selection.line if line is None else line
        observed = observed_at or (
            EvidenceContractTests.QUOTE_NOW - timedelta(minutes=1)
        )
        return [
            {
                "market_id": selection.market_id.value,
                "outcome_id": outcome.value,
                "line": quote_line,
                "bookmaker_odds": odds,
                "source": source,
                "quote_snapshot_id": snapshot_id,
                "observed_at": observed.isoformat(),
                "is_genuine": True,
                "is_current": True,
            }
            for outcome in MARKET_REGISTRY[
                selection.market_id
            ].supported_outcomes
        ]

    @staticmethod
    def _evidence_by_field(result):
        return {
            item["field"]: item
            for item in result["evidence_report"]["evidence_items"]
        }

    def test_model_status_registry_covers_every_canonical_market(self):
        self.assertEqual(set(MODEL_STATUS_REGISTRY), set(MarketId))
        self.assertEqual(
            MODEL_STATUS_REGISTRY[
                MarketId.HOME_WIN_EITHER_HALF
            ].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.MATCH_RESULT_1UP].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.MATCH_RESULT_2UP].status,
            ModelStatus.DISABLED,
        )

    def test_missing_form_data_is_recorded_as_defaulted(self):
        result = self._compile(form_score=None)
        evidence = self._evidence_by_field(result)

        self.assertEqual(evidence["home_form"]["status"], "DEFAULTED")
        self.assertEqual(evidence["home_form"]["value"], 0.50)
        self.assertEqual(evidence["away_form"]["status"], "DEFAULTED")
        self.assertEqual(evidence["away_form"]["value"], 0.50)

    def test_missing_referee_data_is_recorded_as_missing(self):
        result = self._compile(referee_has_data=False)
        referee = self._evidence_by_field(result)["referee_data"]

        self.assertEqual(referee["status"], "MISSING")
        self.assertIsNone(referee["value"])

    def test_missing_elo_is_recorded_as_defaulted(self):
        fixture_context = self._fixture_context()
        fixture_context.pop("home_pre_elo")
        fixture_context.pop("away_pre_elo")
        with patch(
            "intelligence.match_analyst.os.path.exists",
            return_value=False,
        ):
            result = self._analyst().compile_master_fixture_prediction(
                fixture_context
            )
        evidence = self._evidence_by_field(result)

        self.assertEqual(evidence["home_elo"]["status"], "DEFAULTED")
        self.assertEqual(evidence["home_elo"]["value"], 1500)
        self.assertEqual(evidence["away_elo"]["status"], "DEFAULTED")
        self.assertEqual(evidence["away_elo"]["value"], 1500)

    def test_stale_live_data_is_recorded_as_stale(self):
        result = self._compile(live_ratio=0.20)
        freshness = self._evidence_by_field(result)[
            "live_data_freshness"
        ]

        self.assertEqual(freshness["status"], "STALE")
        self.assertEqual(freshness["value"], 0.20)

    def test_score_matrix_audit_is_attached_additively(self):
        result = self._compile()
        report = result["evidence_report"]
        audit = report["score_matrix_audit"]
        evidence = self._evidence_by_field(result)["score_matrix"]

        self.assertIsInstance(audit, dict)
        self.assertEqual(evidence["status"], "AVAILABLE")
        self.assertEqual(evidence["value"], audit)
        self.assertGreaterEqual(audit["max_home_goal_index"], 0)
        self.assertGreaterEqual(audit["max_away_goal_index"], 0)
        self.assertLessEqual(
            audit["omitted_tail_mass"],
            audit["tail_tolerance"],
        )
        self.assertEqual(
            audit["normalization_method"],
            "divide_by_retained_mass",
        )
        self.assertGreaterEqual(audit["home_expected_goals"], 0.0)
        self.assertGreaterEqual(audit["away_expected_goals"], 0.0)

    def test_serialized_score_market_probabilities_preserve_identities(self):
        result = self._compile()
        evaluations = {
            (
                evaluation["market_id"],
                evaluation["outcome_id"],
                evaluation["line"],
            ): evaluation["probability"]
            for evaluation in result["evidence_report"][
                "market_evaluations"
            ]
        }
        home = evaluations[(MarketId.MATCH_RESULT.value, "HOME", None)]
        draw = evaluations[(MarketId.MATCH_RESULT.value, "DRAW", None)]
        away = evaluations[(MarketId.MATCH_RESULT.value, "AWAY", None)]
        btts_yes = evaluations[(MarketId.BTTS.value, "YES", None)]
        btts_no = evaluations[(MarketId.BTTS.value, "NO", None)]

        self.assertAlmostEqual(home + draw + away, 1.0, places=14)
        self.assertAlmostEqual(btts_yes + btts_no, 1.0, places=14)
        self.assertAlmostEqual(
            evaluations[
                (MarketId.DOUBLE_CHANCE.value, "HOME_OR_DRAW", None)
            ],
            home + draw,
            places=14,
        )
        self.assertAlmostEqual(
            evaluations[
                (MarketId.DOUBLE_CHANCE.value, "DRAW_OR_AWAY", None)
            ],
            draw + away,
            places=14,
        )
        self.assertAlmostEqual(
            evaluations[
                (MarketId.DOUBLE_CHANCE.value, "HOME_OR_AWAY", None)
            ],
            home + away,
            places=14,
        )

    def test_missing_bookmaker_odds_leaves_edge_pp_null(self):
        result = self._compile()
        evaluations = result["evidence_report"]["market_evaluations"]
        bookmaker_evidence = self._evidence_by_field(result)[
            "bookmaker_odds"
        ]

        self.assertTrue(evaluations)
        self.assertEqual(bookmaker_evidence["status"], "MISSING")
        self.assertTrue(
            all(evaluation["bookmaker_odds"] is None for evaluation in evaluations)
        )
        self.assertTrue(
            all(evaluation["edge_pp"] is None for evaluation in evaluations)
        )
        self.assertEqual(
            result["decision_status"],
            DecisionStatus.ANALYTICAL_CANDIDATE.value,
        )
        self.assertTrue(
            all(
                evaluation["kelly_stake_pct"] is None
                for evaluation in evaluations
            )
        )

    def test_reciprocal_probability_is_only_model_fair_odds(self):
        result = self._compile()
        verdict = result["reasoning_verdicts"][0]

        self.assertAlmostEqual(
            verdict["model_fair_odds"],
            1.0 / verdict["model_probability"],
            places=3,
        )
        self.assertIsNone(verdict["bookmaker_odds"])
        self.assertIsNone(verdict["edge_pp"])
        self.assertIsNone(verdict["kelly_stake_pct"])

        reasoned = FixtureReasoner().analyze([
            FixtureOption("1X2", "Home Win", model_prob=0.60),
            FixtureOption("1X2", "Draw", model_prob=0.20),
            FixtureOption("1X2", "Away Win", model_prob=0.20),
        ])
        self.assertTrue(
            all(
                item.status == DecisionStatus.ANALYTICAL_CANDIDATE.value
                for item in reasoned
            )
        )
        self.assertTrue(all(item.fair_prob is None for item in reasoned))
        self.assertTrue(all(item.edge_pp is None for item in reasoned))
        self.assertTrue(
            all(item.kelly_stake_pct is None for item in reasoned)
        )
        self.assertAlmostEqual(
            reasoned[0].option.model_fair_odds,
            1.0 / 0.60,
        )

    def test_exact_complete_pricing_is_required_for_bet(self):
        analytical = self._compile()
        selection = resolve_legacy_selection(
            analytical["recommended_analytical_verdict"]
        )
        context = self._fixture_context()
        context["bookmaker_odds"] = self._quotes_for_selection(selection)

        priced = self._analyst().compile_master_fixture_prediction(
            context,
            quote_current_time=self.QUOTE_NOW,
        )

        self.assertEqual(priced["decision_status"], DecisionStatus.BET.value)
        candidate = priced["viable_markets"][0]
        self.assertEqual(candidate["market_id"], selection.market_id.value)
        self.assertEqual(candidate["outcome_id"], selection.outcome_id.value)
        self.assertEqual(candidate["line"], selection.line)
        self.assertIsNotNone(candidate["edge_pp"])
        self.assertIsNotNone(candidate["kelly_stake_pct"])
        self.assertTrue(candidate["edge_is_bookmaker_value"])
        self.assertTrue(priced["edge_is_bookmaker_value"])
        self.assertEqual(
            priced["accumulator_eligible_selection"]["verdict"],
            candidate["verdict"],
        )

    def test_odds_for_another_market_cannot_price_selected_market(self):
        analytical = self._compile()
        selected = resolve_legacy_selection(
            analytical["recommended_analytical_verdict"]
        )
        other_market = (
            MarketId.BTTS
            if selected.market_id != MarketId.BTTS
            else MarketId.MATCH_RESULT
        )
        other = type(selected)(
            market_id=other_market,
            outcome_id=MARKET_REGISTRY[other_market].supported_outcomes[0],
            line=None,
            display_label="Other",
            selection_display_name="Other",
        )
        context = self._fixture_context()
        context["bookmaker_odds"] = self._quotes_for_selection(other)

        result = self._analyst().compile_master_fixture_prediction(
            context,
            quote_current_time=self.QUOTE_NOW,
        )

        self.assertEqual(
            result["decision_status"],
            DecisionStatus.ANALYTICAL_CANDIDATE.value,
        )
        self.assertIsNone(result["viable_markets"][0]["bookmaker_odds"])
        self.assertIsNone(result["viable_markets"][0]["edge_pp"])
        self.assertFalse(
            result["viable_markets"][0]["edge_is_bookmaker_value"]
        )
        self.assertFalse(result["edge_is_bookmaker_value"])
        self.assertIsNone(result["accumulator_eligible_selection"])

    def test_wrong_line_cannot_price_selected_market(self):
        selection = make_selection(
            MarketId.TOTAL_GOALS,
            OutcomeId.UNDER,
            line=3.5,
        )
        quotes = parse_bookmaker_quotes(
            self._quotes_for_selection(
                selection,
                line=selection.line + 1.0,
            ),
            current_time=self.QUOTE_NOW,
        )
        pricing, reason = price_selection(selection, 0.70, quotes)

        self.assertIsNone(pricing)
        self.assertIn("exact market, outcome, and line", reason)

    def test_cross_bookmaker_outcomes_cannot_form_one_market(self):
        selection = make_selection(
            MarketId.MATCH_RESULT,
            OutcomeId.HOME,
        )
        raw_quotes = self._quotes_for_selection(selection)
        for index, quote in enumerate(raw_quotes):
            quote["source"] = f"bookmaker-{index}"
        quotes = parse_bookmaker_quotes(
            raw_quotes,
            current_time=self.QUOTE_NOW,
        )

        pricing, reason = price_selection(selection, 0.70, quotes)

        self.assertIsNone(pricing)
        self.assertIn("market is incomplete", reason)

    def test_cross_snapshot_outcomes_cannot_form_one_market(self):
        selection = make_selection(
            MarketId.MATCH_RESULT,
            OutcomeId.HOME,
        )
        raw_quotes = self._quotes_for_selection(selection)
        for index, quote in enumerate(raw_quotes):
            quote["quote_snapshot_id"] = f"snapshot-{index}"
        quotes = parse_bookmaker_quotes(
            raw_quotes,
            current_time=self.QUOTE_NOW,
        )

        pricing, reason = price_selection(selection, 0.70, quotes)

        self.assertIsNone(pricing)
        self.assertIn("market is incomplete", reason)

    def test_complete_single_bookmaker_snapshot_can_be_devigged(self):
        selection = make_selection(
            MarketId.MATCH_RESULT,
            OutcomeId.HOME,
        )
        quotes = parse_bookmaker_quotes(
            self._quotes_for_selection(selection),
            current_time=self.QUOTE_NOW,
        )

        pricing, reason = price_selection(selection, 0.70, quotes)

        self.assertEqual(reason, "")
        self.assertIsNotNone(pricing)
        self.assertEqual(
            pricing.bookmaker_quote.source,
            "test_bookmaker",
        )
        self.assertEqual(
            pricing.bookmaker_quote.quote_snapshot_id,
            "snapshot-1",
        )

    def test_duplicate_outcomes_across_sources_do_not_overwrite(self):
        selection = make_selection(
            MarketId.MATCH_RESULT,
            OutcomeId.HOME,
        )
        raw_quotes = self._quotes_for_selection(selection)
        home, draw, away = raw_quotes
        source_a = [home.copy(), draw.copy()]
        source_b = [home.copy(), away.copy()]
        for quote in source_a:
            quote["source"] = "bookmaker-a"
        for quote in source_b:
            quote["source"] = "bookmaker-b"
        quotes = parse_bookmaker_quotes(
            source_a + source_b,
            current_time=self.QUOTE_NOW,
        )

        pricing, reason = price_selection(selection, 0.70, quotes)

        self.assertIsNone(pricing)
        self.assertIn("market is incomplete", reason)

    def test_quote_freshness_requires_observed_at_within_max_age(self):
        selection = make_selection(MarketId.BTTS, OutcomeId.YES)
        stale_raw = self._quotes_for_selection(
            selection,
            observed_at=self.QUOTE_NOW - timedelta(minutes=30),
        )
        stale_quotes = parse_bookmaker_quotes(
            stale_raw,
            current_time=self.QUOTE_NOW,
            max_quote_age_seconds=600,
        )
        missing_timestamp = self._quotes_for_selection(selection)
        for quote in missing_timestamp:
            quote.pop("observed_at")
        missing_quotes = parse_bookmaker_quotes(
            missing_timestamp,
            current_time=self.QUOTE_NOW,
        )

        self.assertEqual(stale_quotes, ())
        self.assertEqual(missing_quotes, ())

    def test_model_requirements_separate_probability_and_pricing(self):
        for definition in MODEL_STATUS_REGISTRY.values():
            self.assertNotIn(
                "bookmaker_odds",
                definition.probability_inputs,
            )
            if definition.selectable:
                self.assertEqual(
                    definition.pricing_inputs,
                    ("bookmaker_odds",),
                )

    def test_accumulator_filter_preserves_exact_priced_selection(self):
        priced_selection = {
            "verdict": "HOME_WIN",
            "market_id": MarketId.MATCH_RESULT.value,
            "outcome_id": OutcomeId.HOME.value,
            "line": None,
            "category": "MATCH_RESULT",
            "edge": 0.10,
            "edge_above_baseline": 0.10,
            "edge_is_bookmaker_value": True,
            "edge_method": "multiplicative_devig",
            "prob": 0.70,
            "probability_method": "test_probability",
            "bookmaker_odds": 2.0,
            "bookmaker_quote": {"exact": True},
            "edge_pp": 20.0,
            "kelly_stake_pct": 2.0,
        }
        unpriced_diversity_preference = {
            "verdict": "DC_X2",
            "category": "DOUBLE_CHANCE",
            "edge": 0.50,
            "edge_above_baseline": 0.50,
            "edge_is_bookmaker_value": False,
            "bookmaker_odds": None,
        }
        fixture = {
            "fixture_id": "priced-selection",
            "fixture": "Alpha FC vs Beta FC",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "league": "Test League",
            "risk_score": 10.0,
            "decision_status": DecisionStatus.BET.value,
            "accumulator_eligible_selection": priced_selection,
            "viable_markets": [
                priced_selection,
                unpriced_diversity_preference,
            ],
        }
        acca_filter = AccaFilter()
        acca_filter.nlp_engine = SimpleNamespace(
            analyze_fixture=lambda *args, **kwargs: {}
        )

        result = acca_filter.build_filtered_acca(
            [fixture],
            target_size=1,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["verdict"], "HOME_WIN")
        self.assertEqual(
            result[0]["market_id"],
            MarketId.MATCH_RESULT.value,
        )
        self.assertEqual(result[0]["outcome_id"], OutcomeId.HOME.value)
        self.assertTrue(result[0]["edge_is_bookmaker_value"])

    def test_disabled_markets_are_reported_but_never_selected(self):
        result = self._compile()
        evaluations = result["evidence_report"]["market_evaluations"]
        disabled = [
            evaluation
            for evaluation in evaluations
            if evaluation["model_status"] == ModelStatus.DISABLED.value
        ]

        self.assertEqual(
            {evaluation["market_id"] for evaluation in disabled},
            {
                MarketId.HOME_WIN_EITHER_HALF.value,
                MarketId.AWAY_WIN_EITHER_HALF.value,
                MarketId.DRAW_NO_BET.value,
                MarketId.MATCH_RESULT_1UP.value,
                MarketId.MATCH_RESULT_2UP.value,
            },
        )
        self.assertTrue(all(not evaluation["selected"] for evaluation in disabled))
        self.assertTrue(
            all(evaluation["rejection_reasons"] for evaluation in disabled)
        )
        self.assertEqual(
            build_viable_market_candidates(
                {
                    "WIN_EITHER_HALF_HOME_YES": 0.90,
                    "1X2_1UP_HOME": 0.90,
                    "DNB_HOME": 0.90,
                    "DNB_AWAY": 0.90,
                },
                {},
            ),
            [],
        )
        dnb_status = MODEL_STATUS_REGISTRY[MarketId.DRAW_NO_BET]
        self.assertIsNone(dnb_status.probability_method)
        self.assertEqual(
            dnb_status.missing_input_policy,
            MissingInputPolicy.REJECT_MARKET,
        )

    def test_home_and_away_dnb_remain_visible_but_never_viable(self):
        result = self._compile()
        dnb_evaluations = [
            evaluation
            for evaluation in result["evidence_report"][
                "market_evaluations"
            ]
            if evaluation["market_id"] == MarketId.DRAW_NO_BET.value
        ]

        self.assertEqual(
            {evaluation["outcome_id"] for evaluation in dnb_evaluations},
            {OutcomeId.HOME.value, OutcomeId.AWAY.value},
        )
        self.assertTrue(
            all(
                evaluation["model_status"] == ModelStatus.DISABLED.value
                for evaluation in dnb_evaluations
            )
        )
        self.assertTrue(
            all(
                evaluation["probability_method"] is None
                for evaluation in dnb_evaluations
            )
        )
        self.assertTrue(
            all(not evaluation["selected"] for evaluation in dnb_evaluations)
        )
        self.assertFalse(
            any(
                market["verdict"] in {"DNB_HOME", "DNB_AWAY"}
                for market in result["viable_markets"]
            )
        )

    def test_no_bet_evidence_includes_explicit_decision_reasons(self):
        with patch(
            "intelligence.match_analyst.build_viable_market_candidates",
            return_value=[],
        ):
            result = self._compile()

        report = result["evidence_report"]
        self.assertEqual(result["decision_status"], DecisionStatus.NO_BET.value)
        self.assertEqual(
            report["final_decision"],
            DecisionStatus.NO_BET.value,
        )
        self.assertTrue(report["decision_reasons"])
        self.assertEqual(
            report["decision_reasons"],
            result["no_bet_reasons"],
        )

    def test_data_completeness_is_deterministic_for_the_same_input(self):
        first = self._compile(live_ratio=0.20, form_score=None)
        second = self._compile(live_ratio=0.20, form_score=None)

        self.assertEqual(
            first["evidence_report"]["data_quality"],
            second["evidence_report"]["data_quality"],
        )

    def test_pipeline_attaches_evidence_report_without_removing_fields(self):
        pipeline = object.__new__(AnalysisPipeline)
        pipeline.analyst = self._analyst()
        pipeline._resolve_team_id = lambda team_name: (
            101 if team_name == "Alpha FC" else 202
        )

        fixtures = [
            {
                "fixture_id": "fixture-evidence-1",
                "home_team": "Alpha FC",
                "away_team": "Beta FC",
                "league": "Test League",
                "match_date": "2026-07-29T15:00:00",
                "data_source": "test_fixture",
                "home_pre_elo": 1520,
                "away_pre_elo": 1480,
            }
        ]
        analyzed = pipeline.run_pipeline_snapshot(
            execution_limit=1,
            override_fixtures=fixtures,
        )

        self.assertEqual(len(analyzed), 1)
        self.assertIn("fixture", analyzed[0])
        self.assertIn("verdict", analyzed[0])
        self.assertIn("evidence_report", analyzed[0])
        self.assertEqual(
            analyzed[0]["evidence_report"]["fixture_id"],
            "fixture-evidence-1",
        )
        self.assertFalse(analyzed[0]["edge_is_bookmaker_value"])

    def test_pipeline_quarantines_legacy_bet_from_runtime_execution(self):
        eligible = {
            "verdict": "HOME_WIN",
            "market_id": MarketId.MATCH_RESULT.value,
            "outcome_id": OutcomeId.HOME.value,
            "line": None,
        }
        pipeline = object.__new__(AnalysisPipeline)
        pipeline.analyst = SimpleNamespace(
            compile_master_fixture_prediction=lambda context: {
                "decision_status": DecisionStatus.BET.value,
                "edge_differential": 0.10,
                "edge_is_bookmaker_value": True,
                "recommended_analytical_verdict": "HOME_WIN",
                "viable_markets": [eligible],
                "accumulator_eligible_selection": eligible,
            }
        )
        pipeline._resolve_team_id = lambda team_name: 101

        analyzed = pipeline.run_pipeline_snapshot(
            execution_limit=1,
            override_fixtures=[{
                "fixture_id": "pipeline-priced",
                "home_team": "Alpha FC",
                "away_team": "Beta FC",
                "league": "Test League",
                "match_date": "2026-07-29T15:00:00",
            }],
        )

        self.assertTrue(analyzed[0]["edge_is_bookmaker_value"])
        self.assertEqual(
            analyzed[0]["decision_status"],
            DecisionStatus.ANALYTICAL_CANDIDATE.value,
        )
        self.assertEqual(
            analyzed[0]["legacy_decision_status_before_runtime_gate"],
            DecisionStatus.BET.value,
        )
        self.assertIsNone(analyzed[0]["accumulator_eligible_selection"])
        self.assertIsNone(analyzed[0]["kelly_stake_pct"])
        self.assertTrue(analyzed[0]["runtime_authorization_reasons"])


if __name__ == "__main__":
    unittest.main()
