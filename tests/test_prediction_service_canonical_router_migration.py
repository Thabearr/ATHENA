from __future__ import annotations

import ast
import io
from datetime import timedelta
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from domain import market_router_canonical_adapter as canonical_router
from domain import markets
from domain import price_all
from domain._market_router_contracts import RouterDecisionStatus
from engine.market_selector import MarketSelector
from engine.report_generator import ReportGenerator
from models.prediction import Prediction
from services import main_canonical_prediction_adapter as presentation
from services.prediction_service import PredictionService
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_market_router_v3_current_provider import (
    _fixture_state,
    _priced_match_result,
)


def _prediction() -> Prediction:
    return Prediction(
        fixture_id=6001,
        league="Synthetic League",
        home_team="Home FC",
        away_team="Away FC",
        home_strength=70.0,
        away_strength=30.0,
        home_xg=1.5,
        away_xg=0.7,
        expected_goals=2.2,
        reasons=["analysis remains descriptive"],
    )


def _decision(monkeypatch, probability: float):
    evaluation = price_all.PriceAllEvaluation._from_v3(
        _priced_match_result(monkeypatch, probability=probability)
    )
    return canonical_router.route(
        evaluation,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )


def _service(monkeypatch) -> PredictionService:
    service = object.__new__(PredictionService)

    class _Analyzer:
        def analyze(self, _fixture):
            return _prediction()

    from engine.probability_engine import ProbabilityEngine
    from engine.reliability_engine import ReliabilityEngine
    from engine.risk_engine import RiskEngine

    service.analyzer = _Analyzer()
    service.probability = ProbabilityEngine()
    service.risk = RiskEngine()
    service.reliability = ReliabilityEngine()
    return service


def test_main_core_and_router_owner_are_exact_and_side_effect_free():
    presentation.clear_main_canonical_core_cache()
    bindings = presentation.resolve_main_canonical_core()
    record = bindings.record_for("market_router")
    assert bindings.authority_profile == "MAIN"
    assert bindings.registry_canonical_sha256 == (
        "d52fbb292ddaea9ba2e94fda036f715db5ced7248187814fd29ac7859de26104"
    )
    assert record.component_id == presentation.EXPECTED_ROUTER_COMPONENT_ID
    assert record.contract_sha256 == presentation.EXPECTED_ROUTER_CONTRACT_SHA256
    assert record.artifact_git_blob_sha == presentation.EXPECTED_ROUTER_ARTIFACT_GIT_BLOB_SHA
    assert record.main_authority is True
    assert record.allowed_profiles == ("MAIN", "SHADOW")
    assert presentation.MAIN_AUTHORITY_MANIFEST.to_dict()["capabilities"] == {
        "provider_acquisition": False,
        "share_code_generation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager": False,
    }
    assert all(value is False for key, value in presentation.AUTHORITY.items() if key not in {
        "authority_profile", "canonical_core_resolution", "canonical_router_verification",
        "presentation_projection_only",
    })


def test_selected_projection_is_exact_one_way_canonical_projection(monkeypatch):
    selected = _decision(monkeypatch, 0.60)
    opportunity = selected.selected_opportunity
    assert selected.decision_status is RouterDecisionStatus.SELECTED
    assert opportunity is not None
    prediction = presentation.project_canonical_router_decision(_prediction(), selected)
    expected = markets.make_selection(
        opportunity.market_id, opportunity.outcome_id, line=opportunity.line
    )
    assert type(prediction) is Prediction
    assert prediction.recommended_market == expected.display_label
    assert prediction.market_confidence == round(opportunity.prediction_confidence * 100.0, 1)
    assert prediction.ranked_markets == [
        (expected.display_label, round(opportunity.prediction_confidence * 100.0, 1))
    ]
    assert prediction.home_xg == 1.5
    assert prediction.away_xg == 0.7
    assert prediction.expected_goals == 2.2
    assert prediction.reasons == ["analysis remains descriptive"]


def test_no_bet_projection_is_fail_closed(monkeypatch):
    no_bet = _decision(monkeypatch, 0.45)
    assert no_bet.decision_status is RouterDecisionStatus.NO_BET
    prediction = presentation.project_canonical_router_decision(_prediction(), no_bet)
    assert prediction.recommended_market == "No Recommendation"
    assert prediction.market_confidence == 0.0
    assert prediction.ranked_markets == []
    assert set(no_bet.decision_reasons).issubset(prediction.reasons)


def test_missing_router_decision_is_fail_closed_and_ignores_legacy_fields():
    prediction = _prediction()
    prediction.recommended_market = "Home Win"
    prediction.market_confidence = 99.0
    prediction.ranked_markets = [("Home Win", 99.0)]
    prediction.market_scores["Home Win"] = 999.0
    result = presentation.project_canonical_router_decision(prediction)
    assert result.recommended_market == "No Recommendation"
    assert result.market_confidence == 0.0
    assert result.ranked_markets == []
    assert presentation.NO_ROUTER_REASON in result.reasons


def test_wrong_type_and_unverifiable_router_decision_fail_closed_as_typed_errors(monkeypatch):
    with pytest.raises(presentation.MainCanonicalPredictionAdapterError):
        presentation.project_canonical_router_decision(_prediction(), {"status": "SELECTED"})

    selected = _decision(monkeypatch, 0.60)
    monkeypatch.setattr(
        canonical_router,
        "verify_router_decision",
        lambda _value: (_ for _ in ()).throw(ValueError("reconstruction mismatch")),
    )
    with pytest.raises(presentation.MainCanonicalPredictionAdapterError):
        presentation.project_canonical_router_decision(_prediction(), selected)


def test_prediction_service_has_no_legacy_selector_and_runs_it_zero_times(monkeypatch):
    source = Path("services/prediction_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "engine.market_selector" not in source
    assert "MarketSelector" not in source
    assert not any(isinstance(node, ast.Attribute) and node.attr == "select" for node in ast.walk(tree))

    calls = 0

    def explode(_self, _prediction):
        nonlocal calls
        calls += 1
        raise AssertionError("MarketSelector.select executed in migrated PredictionService")

    monkeypatch.setattr(MarketSelector, "select", explode)
    service = _service(monkeypatch)
    result = service.predict({"fixture": {"id": 1}})
    assert calls == 0
    assert result.recommended_market == "No Recommendation"
    assert result.market_confidence == 0.0
    assert result.ranked_markets == []


def test_prediction_service_selected_decision_projects_without_selector(monkeypatch):
    selected = _decision(monkeypatch, 0.60)
    calls = 0

    def explode(_self, _prediction):
        nonlocal calls
        calls += 1
        raise AssertionError("MarketSelector.select executed in migrated PredictionService")

    monkeypatch.setattr(MarketSelector, "select", explode)
    result = _service(monkeypatch).predict({}, router_decision=selected)
    expected = markets.make_selection(
        selected.selected_opportunity.market_id,
        selected.selected_opportunity.outcome_id,
        line=selected.selected_opportunity.line,
    )
    assert calls == 0
    assert result.recommended_market == expected.display_label


def test_adapter_is_one_way_and_has_no_analysis_selector_or_provider_imports():
    source = Path("services/main_canonical_prediction_adapter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "engine.market_selector" not in source
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert not any(
        module
        and (
            module.startswith("engine")
            or module.startswith("provider")
            or module.startswith("providers")
            or module.startswith("domain.price_all")
        )
        for module in imported_modules
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"route", "price_all_as_of", "price_all_current"}
        for node in ast.walk(tree)
    )


def test_projection_is_deterministic_and_never_uses_quote_or_legacy_scores(monkeypatch):
    selected = _decision(monkeypatch, 0.60)
    first = _prediction()
    second = _prediction()
    first.market_scores["Home Win"] = -999999.0
    second.market_scores["Home Win"] = 999999.0
    result_one = presentation.project_canonical_router_decision(first, selected)
    result_two = presentation.project_canonical_router_decision(second, selected)
    assert result_one.recommended_market == result_two.recommended_market
    assert result_one.market_confidence == result_two.market_confidence
    assert result_one.ranked_markets == result_two.ranked_markets


def _attach_fake_quote_attributes(prediction: Prediction) -> Prediction:
    prediction.odds = 99.0
    prediction.decimal_odds = 99.0
    prediction.provider_event_id = "fake-event"
    prediction.provider_market_id = "fake-market"
    prediction.quote_identity_sha256 = "f" * 64
    prediction.provider_quote = {"odds": 99.0}
    prediction.recommended_market = "Home Win"
    prediction.market_confidence = 99.0
    prediction.ranked_markets = [("Home Win", 99.0)]
    return prediction


def test_fake_quote_provider_attributes_have_no_authority_without_router_decision():
    result = presentation.project_canonical_router_decision(
        _attach_fake_quote_attributes(_prediction())
    )
    assert result.recommended_market == "No Recommendation"
    assert result.market_confidence == 0.0
    assert result.ranked_markets == []
    assert presentation.NO_ROUTER_REASON in result.reasons


def test_fake_quote_provider_attributes_cannot_change_selected_projection(monkeypatch):
    selected = _decision(monkeypatch, 0.60)
    clean = presentation.project_canonical_router_decision(_prediction(), selected)
    polluted = presentation.project_canonical_router_decision(
        _attach_fake_quote_attributes(_prediction()), selected
    )
    assert polluted.recommended_market == clean.recommended_market
    assert polluted.market_confidence == clean.market_confidence
    assert polluted.ranked_markets == clean.ranked_markets


def test_report_generator_preserves_legacy_output_shape_for_no_decision_and_selected(
    monkeypatch,
):
    no_decision = _service(monkeypatch).predict({})
    no_decision_output = io.StringIO()
    with redirect_stdout(no_decision_output):
        ReportGenerator().generate(no_decision)
    rendered_no_decision = no_decision_output.getvalue()
    for field in (
        "Home FC vs Away FC",
        "League: Synthetic League",
        "Home Win Probability",
        "Draw Probability",
        "Away Win Probability",
        "Confidence",
        "Risk Score",
        "Recommended Market",
        "No Recommendation",
    ):
        assert field in rendered_no_decision

    selected = _decision(monkeypatch, 0.60)
    selected_prediction = _service(monkeypatch).predict({}, router_decision=selected)
    selected_output = io.StringIO()
    with redirect_stdout(selected_output):
        ReportGenerator().generate(selected_prediction)
    assert "Recommended Market : Home Win" in selected_output.getvalue()
