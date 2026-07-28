import unittest
from types import SimpleNamespace
from unittest.mock import patch

from domain.markets import DecisionStatus, MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from intelligence.match_analyst import (
    MatchAnalyst,
    build_viable_market_candidates,
)
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
