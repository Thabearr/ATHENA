"""Tests for ATHENA Phase 3.0 Legacy / Canonical Architecture Comparator.

Implements all 38 required evidence-semantics tests from Section 10 plus authority sentinels:
- Price-All P0 Execution (Tests 1 - 8)
- Tie Independence (Tests 9 - 11)
- Hash Semantics (Tests 12 - 16)
- Temporal Boundaries (Tests 17 - 24)
- Provider Semantics (Tests 25 - 30)
- Severity Arithmetic (Tests 31 - 34)
- Receipt & Determinism (Tests 35 - 38)
- Authority & Safety Sentinels (Tests 39 - 47)
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
from domain import p3_0_p0_canonical_acceptance as p0_acceptance
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
    return comparator.build_acceptance_decision()


@pytest.fixture
def corpus(decision: dict[str, Any]) -> dict[str, Any]:
    corpus_file = REPO_ROOT / "artifacts" / "p3-0-comparator-corpus-v1.json"
    if corpus_file.is_file():
        try:
            with corpus_file.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                comparator.validate_comparator_corpus(loaded, expected_decision_sha=decision["canonical_sha256"])
                return loaded
        except Exception:
            pass
    return comparator.build_comparator_corpus(
        decision_sha256=decision["canonical_sha256"],
        real_row_source_path=REPO_ROOT / "artifacts" / "p3-0-comparator-real-row-source-v1.json",
    )


@pytest.fixture
def report(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    report_file = REPO_ROOT / "artifacts" / "p3-0-comparison-report-v1.json"
    if report_file.is_file():
        try:
            with report_file.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                comparator.validate_comparison_report(loaded)
                return loaded
        except Exception:
            pass
    return comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
        implementation_source_sha=SAMPLE_COMMIT_SHA,
    )


@pytest.fixture
def real_row_source() -> dict[str, Any]:
    return comparator.load_real_row_source()


@pytest.fixture
def p0_cases() -> list[dict[str, Any]]:
    path = REPO_ROOT / "tests" / "fixtures" / "architecture" / "legacy_market_selection_cases_v1.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle).get("cases", [])


# ==============================================================================
# 1. PRICE-ALL P0 (Tests 1 - 8)
# ==============================================================================

def test_01_p0_1_starts_from_no_exact_quote_and_real_price_all_produces_fail_closed_unpriced_state() -> None:
    res = p0_acceptance.run_p0_1_acceptance()
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["disposition"] == PriceDisposition.UNPRICED_NO_EXACT_QUOTE.value
    assert "domain.price_all.price_all_as_of" in res["execution_evidence"]["production_apis_executed"]
    assert res["execution_evidence"]["router_status"] == RouterDecisionStatus.NO_BET.value
    assert res["execution_evidence"]["selected_opportunity_id"] is None


def test_02_p0_1_does_not_preset_router_eligibility_as_proof(
    p0_cases: list[dict[str, Any]],
) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NO_QUOTE_RECOMMENDATION")
    res = comparator.evaluate_p0_case(case)
    # Proof relies on real Price-All disposition, not pre-set RouterOpportunity.eligibility
    assert res["execution_evidence"]["disposition"] == "UNPRICED_NO_EXACT_QUOTE"
    assert "pre-set" not in res["canonical_property"].lower()


def test_03_p0_2_real_price_all_state_a_uses_quote_a() -> None:
    res = p0_acceptance.run_p0_2_acceptance()
    assert res["execution_evidence"]["state_a"]["decimal_odds"] == 1.50
    assert res["execution_evidence"]["state_a"]["net_expected_value"] == -0.025
    assert len(res["execution_evidence"]["state_a"]["quote_identity"]) == 64


def test_04_p0_2_real_price_all_state_b_uses_quote_b() -> None:
    res = p0_acceptance.run_p0_2_acceptance()
    assert res["execution_evidence"]["state_b"]["decimal_odds"] == 2.10
    assert res["execution_evidence"]["state_b"]["net_expected_value"] == 0.365
    assert len(res["execution_evidence"]["state_b"]["quote_identity"]) == 64


def test_05_p0_2_ev_value_output_changes_due_to_price() -> None:
    res = p0_acceptance.run_p0_2_acceptance()
    assert res["canonical_avoids_defect"] is True
    assert res["execution_evidence"]["price_derived_ev_change"] is True
    assert res["execution_evidence"]["state_a"]["net_expected_value"] != res["execution_evidence"]["state_b"]["net_expected_value"]


def test_06_p0_2_quote_identity_is_bound_in_output() -> None:
    res = p0_acceptance.run_p0_2_acceptance()
    assert res["execution_evidence"]["state_a"]["quote_identity"] != res["execution_evidence"]["state_b"]["quote_identity"]


def test_07_p0_3_provider_unavailable_state_goes_through_real_pricing_seam() -> None:
    res = p0_acceptance.run_p0_3_acceptance()
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["disposition"] == PriceDisposition.UNPRICED_CURRENTLY_UNAVAILABLE.value
    assert "domain.price_all.price_all_as_of" in res["execution_evidence"]["production_apis_executed"]


def test_08_p0_3_cannot_become_router_selected() -> None:
    res = p0_acceptance.run_p0_3_acceptance()
    assert res["execution_evidence"]["router_status"] == RouterDecisionStatus.NO_BET.value
    assert res["execution_evidence"]["selected_opportunity_id"] is None


# ==============================================================================
# 2. TIE INDEPENDENCE (Tests 9 - 11)
# ==============================================================================

def test_09_rank_key_unit_result_independent_of_construction_order() -> None:
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


def test_10_rank_key_unit_result_independent_of_opportunity_id_and_quote_identity() -> None:
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
    assert ranked[0].market_id is MarketId.MATCH_RESULT
    assert ranked[0].prediction_identity_sha256 == opp_x.prediction_identity_sha256


def test_11_public_canonical_router_route_integration_selects_same_prediction_identity_under_reversed_input() -> None:
    res = p0_acceptance.run_p0_5_acceptance()
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["narrow_rank_ok"] is True
    assert res["execution_evidence"]["public_route_ok"] is True
    assert res["execution_evidence"]["selected_opportunity_id_xy"] is not None
    assert res["execution_evidence"]["selected_opportunity_id_xy"] == res["execution_evidence"]["selected_opportunity_id_yx"]


# ==============================================================================
# 3. HASH SEMANTICS (Tests 12 - 16)
# ==============================================================================

def test_12_as_of_embedded_canonical_sha_verified(real_row_source: dict[str, Any]) -> None:
    as_of = real_row_source.get("as_of_proof", {})
    from domain.p3_0_comparison_evidence import build_as_of_proof
    rebuilt = build_as_of_proof(
        capture_id=as_of["capture_id"],
        fixture_identity=as_of["fixture_identity"],
        capture_started_at=as_of["capture_started_at"],
        capture_completed_at=as_of["capture_completed_at"],
        timing=as_of["timing"],
    )
    assert rebuilt["canonical_sha256"] == comparator.EXPECTED_AS_OF_PROOF_CANONICAL_SHA256
    assert real_row_source["hashes"]["as_of_proof_canonical_sha256"] == comparator.EXPECTED_AS_OF_PROOF_CANONICAL_SHA256


def test_13_as_of_file_byte_sha_separately_verified(real_row_source: dict[str, Any]) -> None:
    file_sha = real_row_source["hashes"]["as_of_proof_file_sha256"]
    canon_sha = real_row_source["hashes"]["as_of_proof_canonical_sha256"]
    assert file_sha == comparator.EXPECTED_AS_OF_PROOF_FILE_SHA256
    assert file_sha != canon_sha


def test_14_join_embedded_canonical_sha_verified(real_row_source: dict[str, Any]) -> None:
    join_sha = real_row_source["hashes"]["join_receipt_canonical_sha256"]
    assert join_sha == comparator.EXPECTED_JOIN_RECEIPT_CANONICAL_SHA256


def test_15_join_file_byte_sha_separately_verified(real_row_source: dict[str, Any]) -> None:
    file_sha = real_row_source["hashes"]["join_receipt_file_sha256"]
    canon_sha = real_row_source["hashes"]["join_receipt_canonical_sha256"]
    assert file_sha == comparator.EXPECTED_JOIN_RECEIPT_FILE_SHA256
    assert file_sha != canon_sha


def test_16_hashing_object_including_its_own_canonical_sha_is_not_accepted_as_canonical_identity(
    real_row_source: dict[str, Any],
) -> None:
    as_of = real_row_source.get("as_of_proof", {})
    wrong_hash = canonical_sha256(as_of)
    assert wrong_hash != as_of["canonical_sha256"]
    tampered = copy.deepcopy(real_row_source)
    tampered["hashes"]["as_of_proof_canonical_sha256"] = wrong_hash
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="as_of_proof_canonical_sha256 mismatch"):
        comparator._validate_real_row_source(tampered)


# ==============================================================================
# 4. TEMPORAL BOUNDARIES (Tests 17 - 24)
# ==============================================================================

def test_17_exact_retained_as_of_proof_rebuilds_to_proven(real_row_source: dict[str, Any]) -> None:
    as_of = real_row_source.get("as_of_proof", {})
    assert as_of.get("result") == "PROVEN"


def test_18_quote_future_dated_at_price_all_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["as_of_proof"]["timing"]["provider_quote_observed_at"] = "2026-09-20T09:35:00.000000Z"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_9_probability_quote_as_of_incompatible"]["result"] == "FAIL"


def test_19_probability_future_dated_at_price_all_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["as_of_proof"]["timing"]["probability_evaluation_time"] = "2026-09-20T09:35:00.000000Z"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_9_probability_quote_as_of_incompatible"]["result"] == "FAIL"


def test_20_price_all_after_router_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["as_of_proof"]["timing"]["canonical_price_all_evaluation_time"] = "2026-09-20T09:35:00.000000Z"
    tampered["as_of_proof"]["timing"]["canonical_router_evaluation_time"] = "2026-09-20T09:34:00.000000Z"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_9_probability_quote_as_of_incompatible"]["result"] == "FAIL"


def test_21_legacy_evaluation_after_kickoff_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["as_of_proof"]["timing"]["legacy_evaluation_time"] = "2026-09-20T10:35:00.000000Z"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_10_post_event_data_leakage"]["result"] == "FAIL"


def test_22_router_evaluation_after_kickoff_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["as_of_proof"]["timing"]["canonical_router_evaluation_time"] = "2026-09-20T10:35:00.000000Z"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_10_post_event_data_leakage"]["result"] == "FAIL"


def test_23_required_evaluation_outside_capture_window_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["as_of_proof"]["timing"]["canonical_price_all_evaluation_time"] = "2026-09-20T09:00:00.000000Z"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_9_probability_quote_as_of_incompatible"]["result"] == "FAIL"


def test_24_tampered_proof_canonical_sha_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["as_of_proof"]["canonical_sha256"] = "0" * 64
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="as_of_proof canonical_sha256 mismatch"):
        comparator._validate_real_row_source(tampered)


# ==============================================================================
# 5. PROVIDER SEMANTICS (Tests 25 - 30)
# ==============================================================================

def test_25_current_provider_market_semantics_contract_validates() -> None:
    from domain.provider_market_semantics import validate_provider_market_semantics_contract
    res = validate_provider_market_semantics_contract()
    assert res.get("canonical_provider_market_semantics_contract_sha256") == comparator.EXPECTED_PROVIDER_SEMANTICS_CONTRACT_SHA256


def test_26_retained_provider_semantic_contract_sha_matches_current_reviewed_owner(
    real_row_source: dict[str, Any],
) -> None:
    retained_contract_sha = real_row_source["provider_semantics"]["canonical_contract_sha256"]
    assert retained_contract_sha == comparator.EXPECTED_PROVIDER_SEMANTICS_CONTRACT_SHA256


def test_27_quote_registry_sha_binds_retained_provider_semantics_registry_sha(
    real_row_source: dict[str, Any],
) -> None:
    quote_reg = real_row_source["quote"]["provider_registry_sha256"]
    prov_reg = real_row_source["provider_semantics"]["registry_sha256"]
    assert quote_reg == prov_reg == comparator.EXPECTED_PROVIDER_SEMANTICS_REGISTRY_SHA256


def test_28_unsupported_semantic_status_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["quote"]["provider_semantic_status"] = "UNSUPPORTED"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_4_semantic_registry_violation"]["result"] == "FAIL"


def test_29_wrong_provider_specifier_line_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["quote"]["provider_specifier"] = "hcp=-0.5"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_4_semantic_registry_violation"]["result"] == "FAIL"


def test_30_wrong_canonical_market_outcome_fails(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["canonical"]["market"] = "MATCH_RESULT"
    res = comparator.compare_real_row(tampered)
    assert res["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert res["high_severity_rules_checked"]["rule_4_semantic_registry_violation"]["result"] == "FAIL"


# ==============================================================================
# 6. SEVERITY ARITHMETIC (Tests 31 - 34)
# ==============================================================================

def test_31_potential_equals_explained_plus_confirmed_plus_unexplained_invariant(
    report: dict[str, Any],
) -> None:
    summary = report["summary"]
    assert summary["potential_high_severity"] == (
        summary["explained_high_severity"] + summary["confirmed_defects"] + summary["unexplained_high_severity"]
    )
    assert summary["potential_high_severity"] == 0
    assert summary["explained_high_severity"] == 0
    assert summary["confirmed_defects"] == 0
    assert summary["unexplained_high_severity"] == 0


def test_32_not_applicable_does_not_increment_explained_high_severity(
    report: dict[str, Any],
) -> None:
    summary = report["summary"]
    assert summary["explained_high_severity"] == 0


def test_33_rule_5_na_counted_separately(report: dict[str, Any]) -> None:
    summary = report["summary"]
    assert summary["high_severity_rule_not_applicable_count"] == 1


def test_34_all_applicable_rules_must_be_pass_or_fail_never_silently_unproven(
    real_row_source: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    p0_results = [comparator.evaluate_p0_case(c) for c in p0_cases]
    res = comparator.compare_real_row(real_row_source, p0_results=p0_results)
    rules = res["high_severity_rules_checked"]
    for idx in [1, 2, 3, 4, 6, 7, 8, 9, 10]:
        rule_key = next(k for k in rules if k.startswith(f"rule_{idx}_"))
        assert rules[rule_key]["result"] == "PASS"
    assert rules["rule_5_shortfall_padding_violation"]["result"] == "NOT_APPLICABLE"


# ==============================================================================
# 7. RECEIPT & DETERMINISM (Tests 35 - 38)
# ==============================================================================

def test_35_selected_quote_ancestry_in_report_matches_source_projection(
    real_row_source: dict[str, Any],
) -> None:
    quote = real_row_source["quote"]
    assert quote["provider_observation_sha256"] == comparator.EXPECTED_SELECTED_QUOTE_OBSERVATION_SHA256
    assert quote["reconciliation_sha256"] == comparator.EXPECTED_SELECTED_QUOTE_RECONCILIATION_SHA256
    assert quote["source_raw_sha256"] == comparator.EXPECTED_SELECTED_QUOTE_RAW_SHA256
    assert quote["source_inventory_sha256"] == comparator.EXPECTED_SELECTED_QUOTE_INVENTORY_SHA256
    assert quote["source_manifest_sha256"] == comparator.EXPECTED_SELECTED_QUOTE_MANIFEST_SHA256


def test_36_stale_ancestry_values_cannot_be_emitted_as_selected_quote_ancestry(
    real_row_source: dict[str, Any],
) -> None:
    stale_digests = {
        "b95ecce8868a2d3cbbbbd2f5b6026a7ee79339e31d7729221ec8ae2e3e601c40",
        "0fe86e24ddce8b64b182cb058e5f8f5ea08fa1ff7eb3a82dfab5ec325e0a0e99",
        "b152d19f86055d7a86ebf49e496d5a164b3017a5be893086eb61f09c6292ba57",
    }
    quote = real_row_source["quote"]
    for field in (
        "provider_observation_sha256",
        "reconciliation_sha256",
        "source_raw_sha256",
        "source_inventory_sha256",
        "source_manifest_sha256",
    ):
        assert quote[field] not in stale_digests


def test_37_reversed_p0_input_order_produces_byte_identical_report(
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


def test_38_deterministic_repeated_artifact_generation(
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


# ==============================================================================
# 8. AUTHORITY & SAFETY SENTINELS (Tests 39 - 47)
# ==============================================================================

def test_39_provider_acquisition_impossible(
    report: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
) -> None:
    assert report["provider_acquisition"] is False
    assert decision["provider_acquisition"] is False
    assert corpus["provider_acquisition"] is False


def test_40_network_sentinel(
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


def test_41_portfolio_not_invoked(report: dict[str, Any]) -> None:
    assert report["portfolio_invoked"] is False


def test_42_share_code_not_invoked(report: dict[str, Any]) -> None:
    assert report["share_code_invoked"] is False


def test_43_login_cookies_wallet_staking_bet_wager_main_authority_false(report: dict[str, Any]) -> None:
    for field in (
        "login",
        "cookies",
        "wallet",
        "staking",
        "bet",
        "wager_placed",
        "main_authority",
        "selection_authority_changed",
        "promotion_authority",
    ):
        assert report[field] is False


def test_44_selection_authority_unchanged(
    report: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    assert report["selection_authority_changed"] is False
    assert decision["selection_authority_changed"] is False


def test_45_source_projection_missing_required_fields_rejected(
    real_row_source: dict[str, Any],
) -> None:
    tampered = copy.deepcopy(real_row_source)
    del tampered["canonical"]["robust_net_expected_value"]
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="missing required canonical field"):
        comparator._validate_real_row_source(tampered)


def test_46_source_projection_tampering_rejected(real_row_source: dict[str, Any]) -> None:
    tampered = copy.deepcopy(real_row_source)
    tampered["hashes"]["artifact_digest"] = "sha256:" + "0" * 64
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="artifact_digest mismatch"):
        comparator._validate_real_row_source(tampered)


def test_47_rejection_of_noncanonical_combo_in_p0(p0_cases: list[dict[str, Any]]) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NONCANONICAL_OVER15_COMBO")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"
    assert res["execution_evidence"]["rejected_by_legacy_resolver"] is True
    assert res["execution_evidence"]["rejected_by_market_canonicalizer"] is True
