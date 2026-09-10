from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.architecture_runtime_reachability import (
    POLICY_ID,
    RuntimeTrace,
    canonical_json_bytes,
    scoped_callable_checkpoint,
    validate_trace_document,
)
from scripts import audit_runtime_reachability as audit


EXPECTED_ROOTS = {
    "build_acca",
    "scripts.execute_current_shadow_request",
    "scripts.restore_current_shadow_history_prime_artifact",
    "scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
    "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
    "scripts.send_current_shadow_email",
}


def _trace():
    return RuntimeTrace(
        source_commit=audit.BASELINE_MAIN,
        supported_root="build_acca",
        root_authority_profile="MAIN_ONLY",
        synthetic_case_id="TRACE_UNIT_TEST",
    )


def test_import_or_object_construction_does_not_record_execution() -> None:
    trace = _trace()
    import engine.market_selector  # noqa: F401

    assert trace.records == ()


def test_scoped_checkpoint_restores_callable_after_success() -> None:
    class Target:
        def run(self, value):
            return value + 1

    target = Target()
    original = target.run
    trace = _trace()
    with scoped_callable_checkpoint(
        target,
        "run",
        trace=trace,
        module="tests.synthetic",
        qualname="Target.run",
        checkpoint_kind="SUPPORTING_LOGIC",
        authority_category="NONE",
    ):
        assert target.run(3) == 4
        assert target.run is not original

    assert target.run(4) == 5
    assert target.run.__func__ is original.__func__
    assert trace.records[0]["outcome"] == "RETURNED"


def test_scoped_checkpoint_restores_callable_and_reraises_after_exception() -> None:
    class Boom:
        def run(self):
            raise KeyError("exact failure")

    target = Boom()
    original = target.run
    trace = _trace()
    with pytest.raises(KeyError, match="exact failure"):
        with scoped_callable_checkpoint(
            target,
            "run",
            trace=trace,
            module="tests.synthetic",
            qualname="Boom.run",
            checkpoint_kind="SUPPORTING_LOGIC",
            authority_category="NONE",
        ):
            target.run()

    assert target.run.__func__ is original.__func__
    assert trace.records[0]["outcome"] == "RAISED"
    assert trace.records[0]["notes"] == ["exception_type=KeyError"]


def test_supporting_checkpoint_does_not_become_decision_authority() -> None:
    trace = _trace()
    token = trace.begin(
        module="tests.synthetic",
        qualname="helper",
        checkpoint_kind="SUPPORTING_LOGIC",
        authority_category="NONE",
    )
    trace.finish(token)
    document = trace.to_dict(disposition="EXECUTED_SUPPORTING_LOGIC")
    assert document["checkpoints"][0]["checkpoint_kind"] == "SUPPORTING_LOGIC"
    assert document["checkpoints"][0]["authority_category"] == "NONE"


def test_trace_document_is_byte_deterministic() -> None:
    first = _trace()
    token = first.begin(
        module="tests.synthetic",
        qualname="decision",
        checkpoint_kind="DECISION_AUTHORITY",
        authority_category="MARKET_ROUTING",
    )
    first.finish(token)
    first_doc = first.to_dict(disposition="EXECUTED_DECISION_AUTHORITY")

    second = _trace()
    token = second.begin(
        module="tests.synthetic",
        qualname="decision",
        checkpoint_kind="DECISION_AUTHORITY",
        authority_category="MARKET_ROUTING",
    )
    second.finish(token)
    second_doc = second.to_dict(disposition="EXECUTED_DECISION_AUTHORITY")

    assert canonical_json_bytes(first_doc) == canonical_json_bytes(second_doc)
    validate_trace_document(first_doc)


def test_full_runtime_evidence_covers_exact_p02_supported_roots() -> None:
    payload = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    assert payload["policy_id"] == POLICY_ID
    assert set(payload["p0_2_supported_roots"]) == EXPECTED_ROOTS
    assert {
        item["supported_root"] for item in payload["supported_root_traces"]
    } == EXPECTED_ROOTS


def test_build_acca_runtime_trace_does_not_execute_predictionservice_or_marketselector() -> None:
    payload = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    observation = payload["supported_root_observations"]["build_acca"]
    assert observation["prediction_service_executed"] is False
    assert observation["market_selector_executed"] is False
    assert observation["decision_authority_modules"] == [
        "intelligence.acca_filter",
        "intelligence.accumulator",
    ]

    trace = next(
        item for item in payload["supported_root_traces"]
        if item["supported_root"] == "build_acca"
    )
    executed = {(row["module"], row["qualname"]) for row in trace["checkpoints"]}
    assert ("services.prediction_service", "PredictionService.predict") not in executed
    assert ("engine.market_selector", "MarketSelector.select") not in executed


def test_prediction_service_supplemental_trace_reaches_legacy_market_selector() -> None:
    payload = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    trace = payload["supplemental_legacy_prediction_service_trace"]
    ordered = [
        (row["module"], row["qualname"], row["checkpoint_kind"])
        for row in trace["checkpoints"]
    ]
    assert ordered == [
        ("services.prediction_service", "PredictionService.predict", "ORCHESTRATION"),
        ("engine.probability_engine", "ProbabilityEngine.calculate", "SUPPORTING_LOGIC"),
        ("engine.risk_engine", "RiskEngine.evaluate", "SUPPORTING_LOGIC"),
        ("engine.reliability_engine", "ReliabilityEngine.evaluate", "SUPPORTING_LOGIC"),
        ("engine.market_selector", "MarketSelector.select", "DECISION_AUTHORITY"),
    ]


def test_current_shadow_trace_executes_actual_transitional_decision_owners() -> None:
    payload = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    trace = next(
        item for item in payload["supported_root_traces"]
        if item["supported_root"] == "scripts.execute_current_shadow_request"
    )
    owners = [
        (row["module"], row["qualname"], row["authority_category"])
        for row in trace["checkpoints"]
        if row["checkpoint_kind"] == "DECISION_AUTHORITY"
    ]
    assert owners == [
        (
            "domain.current_shadow_all_market_price_all",
            "price_all_shadow_fixture",
            "PRICE_ALL",
        ),
        (
            "domain.current_shadow_all_market_router",
            "route_shadow_price_results",
            "MARKET_ROUTING",
        ),
        (
            "domain.current_shadow_all_market_portfolio",
            "optimize_shadow_portfolio",
            "PORTFOLIO_CONSTRUCTION",
        ),
    ]
    observation = payload["supported_root_observations"][
        "scripts.execute_current_shadow_request"
    ]
    assert observation["portfolio_selected_count"] == 1
    assert observation["forbidden_external_boundary_call_count"] == 0
    assert observation["real_share_code_function_executed"] is False


def test_delivery_and_maintenance_roots_do_not_gain_market_decision_authority() -> None:
    payload = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    by_root = {
        item["supported_root"]: item for item in payload["supported_root_traces"]
    }
    assert by_root["scripts.send_current_shadow_email"]["runtime_disposition"] == (
        "EXECUTED_DELIVERY_ONLY"
    )
    for root in (
        "scripts.restore_current_shadow_history_prime_artifact",
        "scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
        "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
    ):
        assert by_root[root]["runtime_disposition"] == "NO_DECISION_AUTHORITY_REACHED"
        assert all(
            row["checkpoint_kind"] != "DECISION_AUTHORITY"
            for row in by_root[root]["checkpoints"]
        )


def test_legacy_problem_case_registry_has_five_reproduced_cases() -> None:
    payload = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    cases = payload["legacy_market_selection_problem_cases"]
    assert len(cases) == 5
    assert [case["case_id"] for case in cases] == [
        "LEGACY_SELECTOR_NO_QUOTE_RECOMMENDATION",
        "LEGACY_SELECTOR_QUOTE_INDEPENDENT_OUTPUT",
        "LEGACY_SELECTOR_NO_PROVIDER_FAIL_CLOSED_DISPOSITION",
        "LEGACY_SELECTOR_NONCANONICAL_OVER15_COMBO",
        "LEGACY_SELECTOR_CONSTRUCTION_ORDER_TIE",
    ]
    assert cases[0]["current_recommended_market"] == "Both Teams To Score"
    assert cases[2]["current_recommended_market"] == "Under 2.5"
    assert cases[3]["current_recommended_market"] == "Home or Over 1.5"
    assert cases[4]["current_ranked_markets"][:2] == [
        ["Home or Draw", 80.0],
        ["Home or Away", 80.0],
    ]


def test_runtime_evidence_is_deterministic_across_repeated_synthetic_execution() -> None:
    first = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    second = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_runtime_evidence_grants_no_cleanup_production_or_wager_authority() -> None:
    payload = audit.build_runtime_evidence(audit.BASELINE_MAIN)
    assert payload["cleanup"] == {
        "disposition_changes_authorized": False,
        "delete_authority_granted": False,
        "all_reviewed_cleanup_dispositions_required": "UNCLASSIFIED",
    }
    assert all(value is False for value in payload["safety"].values())
    for trace in payload["supported_root_traces"] + [
        payload["supplemental_legacy_prediction_service_trace"]
    ]:
        authority = trace["authority"]
        assert authority["cleanup_authority"] == "NONE"
        assert all(
            value is False
            for key, value in authority.items()
            if key != "cleanup_authority"
        )


@pytest.mark.xfail(
    strict=True,
    reason="P0.5 evidence: legacy selector currently recommends without reviewed quote authority",
)
def test_future_legacy_selector_requires_quote_before_recommendation() -> None:
    case = audit._legacy_cases()[0]
    assert case["current_recommended_market"] == "No Recommendation"


@pytest.mark.xfail(
    strict=True,
    reason="P0.5 evidence: legacy selector currently ignores attached quote-like/provider-like fields",
)
def test_future_legacy_selector_output_is_not_quote_independent() -> None:
    cases = audit._legacy_cases()
    assert cases[0]["current_recommended_market"] != cases[1]["current_recommended_market"]


@pytest.mark.xfail(
    strict=True,
    reason="P0.5 evidence: provider absence has no explicit unpriced selector disposition",
)
def test_future_legacy_selector_fails_closed_without_provider_availability() -> None:
    case = audit._legacy_cases()[2]
    assert case["current_recommended_market"] == "No Recommendation"


@pytest.mark.xfail(
    strict=True,
    reason="P0.5 evidence: ad-hoc Home or Over 1.5 can currently become the legacy recommendation",
)
def test_future_legacy_selector_emits_only_reviewed_canonical_market_identity() -> None:
    case = audit._legacy_cases()[3]
    assert case["current_recommended_market"] != "Home or Over 1.5"


@pytest.mark.xfail(
    strict=True,
    reason="P0.5 evidence: equal legacy scores are currently resolved by append/stable-sort order",
)
def test_future_legacy_selector_does_not_leave_equal_top_scores_to_construction_order() -> None:
    case = audit._legacy_cases()[4]
    top_two = case["current_ranked_markets"][:2]
    assert top_two[0][1] != top_two[1][1]
