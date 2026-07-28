import unittest
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
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.pricing import parse_bookmaker_quotes, price_selection
from intelligence.match_analyst import (
    MatchAnalyst,
    build_viable_market_candidates,
)
from intelligence.fixture_reasoner import FixtureOption, FixtureReasoner
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
    def _quotes_for_selection(selection, odds=4.0, *, line=None):
        quote_line = selection.line if line is None else line
        return [
            {
                "market_id": selection.market_id.value,
                "outcome_id": outcome.value,
                "line": quote_line,
                "bookmaker_odds": odds,
                "source": "test_bookmaker",
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

        priced = self._analyst().compile_master_fixture_prediction(context)

        self.assertEqual(priced["decision_status"], DecisionStatus.BET.value)
        candidate = priced["viable_markets"][0]
        self.assertEqual(candidate["market_id"], selection.market_id.value)
        self.assertEqual(candidate["outcome_id"], selection.outcome_id.value)
        self.assertEqual(candidate["line"], selection.line)
        self.assertIsNotNone(candidate["edge_pp"])
        self.assertIsNotNone(candidate["kelly_stake_pct"])

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

        result = self._analyst().compile_master_fixture_prediction(context)

        self.assertEqual(
            result["decision_status"],
            DecisionStatus.ANALYTICAL_CANDIDATE.value,
        )
        self.assertIsNone(result["viable_markets"][0]["bookmaker_odds"])
        self.assertIsNone(result["viable_markets"][0]["edge_pp"])

    def test_wrong_line_cannot_price_selected_market(self):
        selection = make_selection(
            MarketId.TOTAL_GOALS,
            OutcomeId.UNDER,
            line=3.5,
        )
        quotes = parse_bookmaker_quotes(self._quotes_for_selection(
            selection,
            line=selection.line + 1.0,
        ))
        pricing, reason = price_selection(selection, 0.70, quotes)

        self.assertIsNone(pricing)
        self.assertIn("exact market, outcome, and line", reason)

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
                },
                {},
            ),
            [],
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


if __name__ == "__main__":
    unittest.main()
