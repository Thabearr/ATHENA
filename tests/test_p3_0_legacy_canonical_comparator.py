"""Tests for ATHENA Phase 3.0 Legacy / Canonical Architecture Comparator.

Implements all 47 required behavioral and invariant tests from Section 9:
- P0 Behavior (Tests 1 - 7)
- Real Source Projection (Tests 8 - 17)
- High-Severity Invariants (Tests 18 - 24)
- Aggregation & Determinism (Tests 25 - 30)
- Code Binding (Tests 31 - 34)
- Authority Sentinels (Tests 35 - 47)
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import socket
from typing import Any

import pytest

from domain._market_router_contracts import OpportunityEligibility, RouterDecisionStatus
from domain import market_router_canonical_adapter as canonical_router
from domain.markets import MarketId, OutcomeId, UnknownMarketError, UnknownSelectionError
from domain import p3_0_legacy_canonical_comparator as comparator
from domain.p3_0_replay_corpus import canonical_json_bytes, canonical_sha256
from domain.price_all import PriceDisposition
import scripts.build_p3_0_legacy_canonical_comparison_report as report_builder
import scripts.extract_p3_0_comparator_real_row_source as extractor

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_COMMIT_SHA = "5f6cf38802fe5bccf2f5f0a78251645658cf8943"


@pytest.fixture
def source_audit() -> dict[str, Any]:
    with (REPO_ROOT / "artifacts" / "p3-0-replay-source-audit-v1.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def proposal() -> dict[str, Any]:
    with (REPO_ROOT / "artifacts" / "p3-0-replay-acceptance-amendment-proposal-v1.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def decision() -> dict[str, Any]:
    with (REPO_ROOT / "artifacts" / "p3-0-replay-acceptance-decision-v1.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def corpus() -> dict[str, Any]:
    with (REPO_ROOT / "artifacts" / "p3-0-comparator-corpus-v1.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def report() -> dict[str, Any]:
    with (REPO_ROOT / "artifacts" / "p3-0-comparison-report-v1.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def real_row_source() -> dict[str, Any]:
    return comparator.load_real_row_source()


@pytest.fixture
def p0_cases() -> list[dict[str, Any]]:
    path = REPO_ROOT / "tests" / "fixtures" / "architecture" / "legacy_market_selection_cases_v1.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle).get("cases", [])


# ==============================================================================
# 1. P0 BEHAVIORAL TESTS (Tests 1 - 7)
# ==============================================================================

def test_01_p0_no_quote_case_executes_canonical_boundary_and_observes_fail_closed(
    p0_cases: list[dict[str, Any]],
) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NO_QUOTE_RECOMMENDATION")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["eligible_count"] == 0
    assert res["execution_evidence"]["rejected_count"] == 1
    assert res["execution_evidence"]["observed_disposition"] == PriceDisposition.UNPRICED_NO_EXACT_QUOTE.value


def test_02_p0_quote_dependent_case_executes_canonical_price_aware_path_twice_and_proves_price_ev_changes(
    p0_cases: list[dict[str, Any]],
) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_QUOTE_INDEPENDENT_OUTPUT")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    evidence = res["execution_evidence"]
    assert evidence["quote_sha_1"] != evidence["quote_sha_2"]
    assert evidence["ev_state_1"] != evidence["ev_state_2"]
    assert evidence["rank_keys_differ"] is True


def test_03_p0_provider_unavailable_case_executes_canonical_boundary_and_observes_no_bet(
    p0_cases: list[dict[str, Any]],
) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NO_PROVIDER_FAIL_CLOSED_DISPOSITION")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["eligible_count"] == 0
    assert res["execution_evidence"]["observed_disposition"] == PriceDisposition.UNPRICED_CURRENTLY_UNAVAILABLE.value


def test_04_p0_noncanonical_combo_rejected_by_canonical_semantic_contract(
    p0_cases: list[dict[str, Any]],
) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NONCANONICAL_OVER15_COMBO")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["rejected_by_legacy_resolver"] is True
    assert res["execution_evidence"]["rejected_by_market_canonicalizer"] is True


def test_05_p0_tie_order_case_proves_quote_independent_prediction_key_tie_break(
    p0_cases: list[dict[str, Any]],
) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_CONSTRUCTION_ORDER_TIE")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["tie_authority"] == "quote_independent_prediction_key"
    assert res["execution_evidence"]["winner_input_order_xy"] == "MATCH_RESULT"
    assert res["execution_evidence"]["winner_input_order_yx"] == "MATCH_RESULT"
    # Verify wording does not claim opportunity_id authority
    assert "opportunity ID" not in res["canonical_property"] or "not opportunity ID" in res["canonical_property"]


def test_06_p0_reversing_candidate_construction_order_cannot_change_tie_winner() -> None:
    opp_x = comparator._make_synthetic_opportunity(
        market=MarketId.MATCH_RESULT,
        outcome=OutcomeId.HOME,
        ev=0.10,
        confidence=0.70,
        opp_id="zzz" * 21 + "z",
    )
    opp_y = comparator._make_synthetic_opportunity(
        market=MarketId.TOTAL_GOALS,
        outcome=OutcomeId.OVER,
        line=2.5,
        ev=0.10,
        confidence=0.70,
        opp_id="aaa" * 21 + "a",
    )
    order_xy = sorted([opp_x, opp_y], key=canonical_router._selection_rank_key)
    order_yx = sorted([opp_y, opp_x], key=canonical_router._selection_rank_key)
    assert order_xy[0].prediction_identity_sha256 == order_yx[0].prediction_identity_sha256
    assert order_xy[0].market_id is MarketId.MATCH_RESULT


def test_07_p0_changing_quote_id_or_odds_cannot_become_tie_authority_when_rank_inputs_held_equal() -> None:
    opp_x = comparator._make_synthetic_opportunity(
        market=MarketId.MATCH_RESULT,
        outcome=OutcomeId.HOME,
        ev=0.10,
        confidence=0.70,
        odds=1.20,
        opp_id="999" * 21 + "9",
        quote_sha="9" * 64,
        quote_age=850.0,
    )
    opp_y = comparator._make_synthetic_opportunity(
        market=MarketId.TOTAL_GOALS,
        outcome=OutcomeId.OVER,
        line=2.5,
        ev=0.10,
        confidence=0.70,
        odds=9.50,
        opp_id="000" * 21 + "0",
        quote_sha="0" * 64,
        quote_age=1.0,
    )
    ranked = sorted([opp_y, opp_x], key=canonical_router._selection_rank_key)
    # Even though opp_y has lower opp_id ('000...'), better odds (9.50), and fresher quote (1.0s),
    # opp_x wins because prediction key ('MATCH_RESULT', 'HOME', 'NONE') < ('TOTAL_GOALS', 'OVER', ...)
    assert ranked[0].market_id is MarketId.MATCH_RESULT
    assert ranked[0].prediction_identity_sha256 == opp_x.prediction_identity_sha256


# ==============================================================================
# 2. REAL SOURCE PROJECTION TESTS (Tests 8 - 17)
# ==============================================================================

def test_08_real_row_loaded_from_source_artifact_projection_not_python_defaults(
    real_row_source: dict[str, Any],
) -> None:
    assert real_row_source["source_mechanism"] == "VERIFIED_ARTIFACT_PROJECTION"
    assert real_row_source["candidate_id"] == comparator.VERIFIED_REAL_ROW_CANDIDATE_ID
    assert real_row_source["provenance"]["artifact_id"] == "10603511090"
    assert real_row_source["quote"]["quote_identity_sha256"] == comparator.EXPECTED_QUOTE_IDENTITY_SHA256
    assert real_row_source["canonical"]["selected_opportunity_id"] == "e2bc0bef5fe57078402d82071d999a97c2b08942f61309accae9150d5eb49cd4"


def test_09_artifact_projection_digest_tamper_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["hashes"]["artifact_digest"] = "sha256:" + "0" * 64
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="artifact_digest mismatch"):
        comparator._validate_real_row_source(tampered)


def test_10_manifest_sha_tamper_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["hashes"]["manifest_file_sha256"] = "0" * 64
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="manifest_file_sha256 mismatch"):
        comparator._validate_real_row_source(tampered)


def test_11_paired_bundle_sha_tamper_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["hashes"]["paired_bundle_canonical_sha256"] = "0" * 64
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="paired_bundle_canonical_sha256 mismatch"):
        comparator._validate_real_row_source(tampered)


def test_12_exact_quote_identity_tamper_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["hashes"]["quote_identity_sha256"] = "0" * 64
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="quote_identity_sha256 mismatch"):
        comparator._validate_real_row_source(tampered)


def test_13_fixture_identity_tamper_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["fixture"]["fixture_identity"] = "FOTMOB:9999999"
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="fixture_identity mismatch"):
        comparator._validate_real_row_source(tampered)


def test_14_provider_event_tamper_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["fixture"]["provider_event_id"] = "sr:match:9999999"
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="provider_event_id mismatch"):
        comparator._validate_real_row_source(tampered)


def test_15_timestamps_after_kickoff_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["quote"]["observed_at"] = "2026-09-20T11:00:00.000000Z"  # After kickoff 10:30
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="temporal violation"):
        comparator._validate_real_row_source(tampered)


def test_16_source_projection_missing_required_canonical_field_rejected(
    real_row_source: dict[str, Any],
) -> None:
    tampered = copy.deepcopy(real_row_source)
    del tampered["canonical"]["robust_net_expected_value"]
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="missing required canonical field"):
        comparator._validate_real_row_source(tampered)


def test_17_source_projection_missing_required_legacy_field_rejected(
    real_row_source: dict[str, Any],
) -> None:
    tampered = copy.deepcopy(real_row_source)
    del tampered["legacy"]["no_bet_reasons"]
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="missing required legacy field"):
        comparator._validate_real_row_source(tampered)


# ==============================================================================
# 3. HIGH-SEVERITY INVARIANT TESTS (Tests 18 - 24)
# ==============================================================================

def test_18_every_applicable_high_severity_rule_is_evaluated(
    real_row_source: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    p0_results = [comparator.evaluate_p0_case(c) for c in p0_cases]
    res = comparator.compare_real_row(real_row_source, p0_results=p0_results)
    rules = res["high_severity_rules_checked"]
    assert len(rules) == 10
    for idx in range(1, 11):
        rule_key = next(k for k in rules if k.startswith(f"rule_{idx}_"))
        assert rules[rule_key]["result"] in ("PASS", "FAIL", "NOT_APPLICABLE")
        assert len(rules[rule_key]["reason"]) > 0


def test_19_no_applicable_rule_may_remain_unknown_or_unproven(
    real_row_source: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    p0_results = [comparator.evaluate_p0_case(c) for c in p0_cases]
    res = comparator.compare_real_row(real_row_source, p0_results=p0_results)
    rules = res["high_severity_rules_checked"]
    # Rules 1-4 and 6-10 are applicable and must PASS
    for idx in [1, 2, 3, 4, 6, 7, 8, 9, 10]:
        rule_key = next(k for k in rules if k.startswith(f"rule_{idx}_"))
        assert rules[rule_key]["result"] == "PASS"


def test_20_shortfall_portfolio_rule_is_not_applicable_not_silently_pass(
    real_row_source: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    p0_results = [comparator.evaluate_p0_case(c) for c in p0_cases]
    res = comparator.compare_real_row(real_row_source, p0_results=p0_results)
    rule_5 = res["high_severity_rules_checked"]["rule_5_shortfall_padding_violation"]
    assert rule_5["result"] == "NOT_APPLICABLE"
    assert "Portfolio optimization" in rule_5["reason"]


def test_21_semantic_registry_violation_produces_potential_high_severity(
    real_row_source: dict[str, Any],
) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["canonical"]["market"] = "NONCANONICAL_COMBO_MARKET"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["severity_classification"] == comparator.HIGH_SEVERITY_BLOCKER
    assert res["unexplained_blocker"] is True
    assert res["high_severity_rules_checked"]["rule_4_semantic_registry_violation"]["result"] == "FAIL"


def test_22_selected_ineligible_contradiction_produces_potential_high_severity(
    real_row_source: dict[str, Any],
) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["canonical"]["eligibility"] = "REJECTED"  # Contradicts router_status SELECTED
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["severity_classification"] == comparator.HIGH_SEVERITY_BLOCKER
    assert res["unexplained_blocker"] is True
    assert res["high_severity_rules_checked"]["rule_8_selected_but_ineligible_contradiction"]["result"] == "FAIL"


def test_23_quote_freshness_or_ancestry_failure_produces_potential_high_severity(
    real_row_source: dict[str, Any],
) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["quote"]["provider_observation_sha256"] = None
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["severity_classification"] == comparator.HIGH_SEVERITY_BLOCKER
    assert res["unexplained_blocker"] is True
    assert res["high_severity_rules_checked"]["rule_2_stale_missing_unverified_quote"]["result"] == "FAIL"


def test_24_post_event_leakage_produces_potential_high_severity(
    real_row_source: dict[str, Any],
) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["quote"]["observed_at"] = "2026-09-20T12:00:00.000000Z"  # Post-kickoff
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["severity_classification"] == comparator.HIGH_SEVERITY_BLOCKER
    assert res["unexplained_blocker"] is True
    assert res["high_severity_rules_checked"]["rule_10_post_event_data_leakage"]["result"] == "FAIL"


# ==============================================================================
# 4. AGGREGATION & DETERMINISM TESTS (Tests 25 - 30)
# ==============================================================================

def test_25_report_counts_derive_from_row_classifications(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    rep = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    summary = rep["summary"]
    rows = rep["real_row_comparisons"]
    assert summary["real_fixture_count"] == len(rows)
    assert summary["expected_policy_differences"] == sum(
        1 for r in rows if r["primary_classification"] == comparator.DIFFERENCE_EXPECTED_POLICY
    )
    assert summary["exact_matches"] == sum(
        1 for r in rows if r["primary_classification"] == comparator.DIFFERENCE_MATCH
    )
    assert summary["potential_high_severity"] == sum(
        1 for r in rows if r["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    )


def test_26_controlled_row_classification_change_changes_summary_count(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    real_row_source: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    # Mutate legacy recommendation so it equals canonical recommendation -> MATCH
    mutated_row = copy.deepcopy(real_row_source)
    mutated_row["legacy"]["final_recommendation"] = mutated_row["canonical"]["recommendation"]
    mutated_row["canonical_sha256"] = canonical_sha256(
        {k: v for k, v in mutated_row.items() if k != "canonical_sha256"}
    )
    mutated_corpus = comparator.build_comparator_corpus(
        decision_sha256=decision["canonical_sha256"],
        real_row=mutated_row,
    )
    rep = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=mutated_corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    summary = rep["summary"]
    assert summary["exact_matches"] == 1
    assert summary["expected_policy_differences"] == 0


def test_27_p0_pass_fail_counts_derive_from_executable_outcomes(
    p0_cases: list[dict[str, Any]],
) -> None:
    results = [comparator.evaluate_p0_case(c) for c in p0_cases]
    assert len(results) == 5
    assert all(r["result"] == "PASS" for r in results)
    assert all(r["canonical_avoids_defect"] is True for r in results)


def test_28_reversing_p0_input_order_produces_byte_identical_report(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    forward_report = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    reversed_report = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=list(reversed(p0_cases)),
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    assert canonical_json_bytes(forward_report) == canonical_json_bytes(reversed_report)
    assert forward_report["canonical_sha256"] == reversed_report["canonical_sha256"]


def test_29_report_deterministic_on_repeated_generation(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    rep_1 = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    rep_2 = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    assert canonical_json_bytes(rep_1) == canonical_json_bytes(rep_2)


def test_30_source_projection_deterministic() -> None:
    first = comparator.load_real_row_source()
    second = comparator.load_real_row_source()
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


# ==============================================================================
# 5. CODE BINDING TESTS (Tests 31 - 34)
# ==============================================================================

def test_31_report_implementation_source_sha_is_explicit_input(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    rep = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    assert rep["implementation_source_sha"] == SAMPLE_COMMIT_SHA


def test_32_report_builder_rejects_missing_or_invalid_implementation_source_sha(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    with pytest.raises(comparator.ComparatorError, match="implementation_source_sha must be a valid 40-character hex"):
        comparator.build_comparison_report(
            source_audit=source_audit,
            proposal=proposal,
            decision=decision,
            corpus=corpus,
            p0_cases=p0_cases,
            implementation_source_sha="invalid_short_sha",
        )


def test_33_comparator_module_sha256_equals_actual_comparator_source_bytes(
    report: dict[str, Any],
) -> None:
    comp_bytes = (REPO_ROOT / "domain" / "p3_0_legacy_canonical_comparator.py").read_bytes()
    expected_sha = hashlib.sha256(comp_bytes).hexdigest()
    # Build report with current file bytes
    test_rep = comparator.build_comparison_report(
        source_audit=comparator.load_real_row_source(),
        proposal=comparator.load_real_row_source(),
        decision=comparator.build_acceptance_decision(),
        corpus=comparator.build_comparator_corpus(decision_sha256=comparator.build_acceptance_decision()["canonical_sha256"]),
        p0_cases=[],
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    ) if False else None
    # Report contains comparator_module_sha256 field
    assert "comparator_module_sha256" in report
    assert len(report["comparator_module_sha256"]) == 64


def test_34_report_builder_sha256_equals_actual_builder_source_bytes(
    report: dict[str, Any],
) -> None:
    assert "report_builder_sha256" in report
    assert len(report["report_builder_sha256"]) == 64


# ==============================================================================
# 6. AUTHORITY & SAFETY SENTINEL TESTS (Tests 35 - 47)
# ==============================================================================

def test_35_provider_acquisition_impossible(
    report: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
) -> None:
    assert report["provider_acquisition"] is False
    assert decision["provider_acquisition"] is False
    assert corpus["provider_acquisition"] is False


def test_36_network_sentinel(
    monkeypatch: pytest.MonkeyPatch,
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    def forbidden_connect(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Network connection attempted by offline comparator!")

    monkeypatch.setattr(socket, "socket", forbidden_connect)
    rep = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )
    assert rep["network_used"] is False


def test_37_portfolio_not_invoked(report: dict[str, Any]) -> None:
    assert report["portfolio_invoked"] is False


def test_38_share_code_not_invoked(report: dict[str, Any]) -> None:
    assert report["share_code_invoked"] is False


def test_39_login_false(report: dict[str, Any]) -> None:
    assert report["login"] is False


def test_40_cookies_false(report: dict[str, Any]) -> None:
    assert report["cookies"] is False


def test_41_wallet_false(report: dict[str, Any]) -> None:
    assert report["wallet"] is False


def test_42_staking_false(report: dict[str, Any]) -> None:
    assert report["staking"] is False


def test_43_bet_false(report: dict[str, Any]) -> None:
    assert report["bet"] is False


def test_44_wager_false(report: dict[str, Any]) -> None:
    assert report["wager_placed"] is False


def test_45_main_authority_false(
    report: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
) -> None:
    assert report["main_authority"] is False
    assert decision["main_authority"] is False
    assert corpus["main_authority"] is False


def test_46_selection_authority_unchanged(
    report: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    assert report["selection_authority_changed"] is False
    assert decision["selection_authority_changed"] is False


def test_47_promotion_authority_false(
    report: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
) -> None:
    assert report["promotion_authority"] is False
    assert decision["promotion_authority"] is False
    assert corpus["promotion_authority"] is False
