"""Tests for ATHENA Phase 3.0 Legacy / Canonical Architecture Comparator.

Covers all 44 required test cases under the owner-approved historical-source-gap exception:
- Acceptance Decision (Tests 1-8)
- Corpus (Tests 9-14)
- Comparator Mechanics & Taxonomy (Tests 15-26)
- P0 Synthetic Defect Classes (Tests 27-31)
- Side Effect / Authority Sentinels (Tests 32-44)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import socket
from typing import Any

import pytest

from domain import p3_0_legacy_canonical_comparator as comparator
from domain.p3_0_replay_corpus import canonical_json_bytes, canonical_sha256

REPO_ROOT = Path(__file__).resolve().parents[1]


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
def p0_cases() -> list[dict[str, Any]]:
    path = REPO_ROOT / "tests" / "fixtures" / "architecture" / "legacy_market_selection_cases_v1.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle).get("cases", [])


# ==============================================================================
# ACCEPTANCE DECISION (Tests 1 - 8)
# ==============================================================================

def test_01_decision_artifact_deterministic() -> None:
    first = comparator.build_acceptance_decision()
    second = comparator.build_acceptance_decision()
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["canonical_sha256"] == second["canonical_sha256"]
    comparator.validate_acceptance_decision(first)


def test_02_proposal_remains_preserved(proposal: dict[str, Any]) -> None:
    assert proposal["policy_id"] == "ATHENA_P3_0_REPLAY_ACCEPTANCE_AMENDMENT_PROPOSAL_V1"
    assert proposal["canonical_sha256"] == comparator.PROPOSAL_CANONICAL_SHA256
    unsigned = {k: v for k, v in proposal.items() if k != "canonical_sha256"}
    assert canonical_sha256(unsigned) == comparator.PROPOSAL_CANONICAL_SHA256


def test_03_r1_remains_false(decision: dict[str, Any]) -> None:
    assert decision["original_r1_satisfied"] is False


def test_04_r2_remains_false(decision: dict[str, Any]) -> None:
    assert decision["original_r2_satisfied"] is False


def test_05_exception_cannot_be_interpreted_as_r1_r2_success(decision: dict[str, Any]) -> None:
    tampered = copy.deepcopy(decision)
    tampered["original_r1_satisfied"] = True
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="original_r1_satisfied must remain False"):
        comparator.validate_acceptance_decision(tampered)

    tampered["original_r1_satisfied"] = False
    tampered["original_r2_satisfied"] = True
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="original_r2_satisfied must remain False"):
        comparator.validate_acceptance_decision(tampered)


def test_06_real_row_count_exactly_one(decision: dict[str, Any], corpus: dict[str, Any]) -> None:
    assert decision["real_replay_rows_admitted"] == 1
    assert corpus["real_replay_row_count"] == 1
    assert len(corpus["rows"]) == 1


def test_07_synthetic_cases_exactly_five(decision: dict[str, Any], p0_cases: list[dict[str, Any]]) -> None:
    assert decision["synthetic_p0_cases_admitted"] == 5
    assert len(p0_cases) == 5


def test_08_synthetic_cases_excluded_from_real_corpus_count(corpus: dict[str, Any], report: dict[str, Any]) -> None:
    assert corpus["real_replay_row_count"] == 1
    for row in corpus["rows"]:
        assert row.get("label") != comparator.SYNTHETIC_P0_LABEL
    assert report["real_replay_row_count"] == 1
    assert report["synthetic_p0_case_count"] == 5


# ==============================================================================
# CORPUS (Tests 9 - 14)
# ==============================================================================

def test_09_only_verified_complete_real_row_admitted(corpus: dict[str, Any]) -> None:
    assert len(corpus["rows"]) == 1
    row = corpus["rows"][0]
    assert row["candidate_id"] == comparator.VERIFIED_REAL_ROW_CANDIDATE_ID
    assert row["fixture_identity"] == comparator.VERIFIED_REAL_ROW_FIXTURE_ID
    assert row["provider_event_id"] == comparator.VERIFIED_REAL_ROW_PROVIDER_EVENT_ID
    assert row["competition"] == comparator.VERIFIED_REAL_ROW_COMPETITION
    assert row["kickoff_utc"] == comparator.VERIFIED_REAL_ROW_KICKOFF_UTC
    assert row["home_team"] == comparator.VERIFIED_REAL_ROW_HOME_TEAM
    assert row["away_team"] == comparator.VERIFIED_REAL_ROW_AWAY_TEAM


def test_10_source_absent_candidate_rejected(decision: dict[str, Any]) -> None:
    absent_row = {
        "candidate_id": "current-shadow:run-001:route-001",
        "fixture_identity": "FOTMOB:999999",
        "provider_event_id": "sr:match:999999",
        "competition": "Premier League",
        "kickoff_utc": "2026-09-20T12:00:00.000000Z",
        "home_team": "Team A",
        "away_team": "Team B",
        "market_families": ["MATCH_RESULT"],
    }
    with pytest.raises(comparator.ComparatorError, match="rejected candidate"):
        comparator.build_comparator_corpus(
            decision_sha256=decision["canonical_sha256"],
            real_row=absent_row,
        )


def test_11_corpus_deterministic(decision: dict[str, Any]) -> None:
    first = comparator.build_comparator_corpus(decision_sha256=decision["canonical_sha256"])
    second = comparator.build_comparator_corpus(decision_sha256=decision["canonical_sha256"])
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["canonical_sha256"] == second["canonical_sha256"]
    comparator.validate_comparator_corpus(first, expected_decision_sha=decision["canonical_sha256"])


def test_12_tampered_source_audit_rejected(corpus: dict[str, Any]) -> None:
    with pytest.raises(comparator.ComparatorError, match="source_audit_sha256 mismatch"):
        comparator.validate_comparator_corpus(
            corpus,
            expected_source_audit_sha="0" * 64,
        )


def test_13_tampered_acceptance_decision_rejected(corpus: dict[str, Any]) -> None:
    with pytest.raises(comparator.ComparatorError, match="owner_exception_decision_sha256 mismatch"):
        comparator.validate_comparator_corpus(
            corpus,
            expected_decision_sha="f" * 64,
        )


def test_14_duplicate_real_row_rejected(corpus: dict[str, Any]) -> None:
    tampered = copy.deepcopy(corpus)
    tampered["rows"].append(tampered["rows"][0])
    tampered["real_replay_row_count"] = 2
    tampered["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="corpus must contain exactly 1 real row"):
        comparator.validate_comparator_corpus(tampered)


# ==============================================================================
# COMPARATOR (Tests 15 - 26)
# ==============================================================================

def test_15_exact_real_fixture_bound_correctly(corpus: dict[str, Any]) -> None:
    row = corpus["rows"][0]
    comparison = comparator.compare_real_row(row)
    assert comparison["fixture_identity"] == "FOTMOB:5749683"
    assert comparison["provider_event_id"] == "sr:match:71945268"
    assert comparison["home_team"] == "Fiorentina"
    assert comparison["away_team"] == "Napoli"
    assert comparison["competition"] == "Serie A"
    assert comparison["kickoff_utc"] == "2026-09-20T10:30:00.000000Z"


def test_16_legacy_null_no_action_disposition_preserved(corpus: dict[str, Any]) -> None:
    row = corpus["rows"][0]
    comparison = comparator.compare_real_row(row)
    assert comparison["legacy"]["final_recommendation"] is None
    assert comparison["legacy"]["decision_status"] == "ANALYTICAL_CANDIDATE"
    assert len(comparison["legacy"]["no_bet_reasons"]) > 0


def test_17_canonical_selected_opportunity_preserved(corpus: dict[str, Any]) -> None:
    row = corpus["rows"][0]
    comparison = comparator.compare_real_row(row)
    assert comparison["canonical"]["router_status"] == "SELECTED"
    assert comparison["canonical"]["recommendation"] == "ASIAN_HANDICAP AWAY 0.0 @ 1.61 (Fiorentina vs Napoli)"
    assert comparison["canonical"]["decimal_odds"] == 1.61
    assert comparison["canonical"]["line"] == 0.0
    assert comparison["canonical"]["market"] == "ASIAN_HANDICAP"
    assert comparison["canonical"]["outcome"] == "AWAY"


def test_18_semantically_invalid_probability_comparison_returns_not_comparable(corpus: dict[str, Any]) -> None:
    row = corpus["rows"][0]
    comparison = comparator.compare_real_row(row)
    assert comparison["probability_comparison"]["status"] == "NOT_COMPARABLE"


def test_19_expected_policy_difference_classification(corpus: dict[str, Any]) -> None:
    row = corpus["rows"][0]
    comparison = comparator.compare_real_row(row)
    assert comparison["primary_classification"] == comparator.DIFFERENCE_EXPECTED_POLICY
    assert comparison["severity_classification"] == comparator.HIGH_SEVERITY_EXPLAINED
    assert comparison["unexplained_blocker"] is False


def test_20_ordinary_legacy_canonical_difference_not_high_severity(corpus: dict[str, Any]) -> None:
    row = corpus["rows"][0]
    comparison = comparator.compare_real_row(row)
    assert comparison["unexplained_blocker"] is False
    assert comparison["severity_classification"] != comparator.HIGH_SEVERITY_BLOCKER


def test_21_invalid_exact_quote_high_severity(corpus: dict[str, Any]) -> None:
    row = copy.deepcopy(corpus["rows"][0])
    row["hashes"]["quote_identity_binding"] = "UNVERIFIED_QUOTE_HASH"
    comparison = comparator.compare_real_row(row)
    assert comparison["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert comparison["severity_classification"] == comparator.HIGH_SEVERITY_BLOCKER
    assert comparison["unexplained_blocker"] is True


def test_22_fixture_mismatch_high_severity(corpus: dict[str, Any]) -> None:
    row = copy.deepcopy(corpus["rows"][0])
    row["fixture_identity"] = "FOTMOB:WRONG"
    comparison = comparator.compare_real_row(row)
    assert comparison["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert comparison["severity_classification"] == comparator.HIGH_SEVERITY_BLOCKER
    assert comparison["unexplained_blocker"] is True


def test_23_selected_but_ineligible_high_severity(corpus: dict[str, Any]) -> None:
    row = copy.deepcopy(corpus["rows"][0])
    row["canonical_ineligible_selected"] = True
    comparison = comparator.compare_real_row(row)
    assert comparison["primary_classification"] == comparator.DIFFERENCE_POTENTIAL_HIGH_SEVERITY
    assert comparison["severity_classification"] == comparator.HIGH_SEVERITY_BLOCKER
    assert comparison["unexplained_blocker"] is True


def test_24_report_deterministic(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    first = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
    )
    second = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
    )
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["canonical_sha256"] == second["canonical_sha256"]
    comparator.validate_comparison_report(first)


def test_25_report_order_independence(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    reversed_cases = list(reversed(p0_cases))
    first = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
    )
    second = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=reversed_cases,
    )
    # The summary and counts remain invariant
    assert first["summary"] == second["summary"]
    assert first["real_replay_row_count"] == second["real_replay_row_count"]
    assert first["synthetic_p0_case_count"] == second["synthetic_p0_case_count"]


def test_26_unexplained_high_severity_blocks_exit(
    source_audit: dict[str, Any],
    proposal: dict[str, Any],
    decision: dict[str, Any],
    corpus: dict[str, Any],
    p0_cases: list[dict[str, Any]],
) -> None:
    tampered_corpus = copy.deepcopy(corpus)
    tampered_corpus["rows"][0]["canonical_ineligible_selected"] = True
    tampered_corpus["canonical_sha256"] = canonical_sha256({k: v for k, v in tampered_corpus.items() if k != "canonical_sha256"})
    with pytest.raises(comparator.ComparatorError, match="unexplained high severity blocker"):
        comparator.build_comparison_report(
            source_audit=source_audit,
            proposal=proposal,
            decision=decision,
            corpus=tampered_corpus,
            p0_cases=p0_cases,
        )


# ==============================================================================
# P0 SYNTHETIC DEFECT CLASSES (Tests 27 - 31)
# ==============================================================================

def test_27_p0_no_quote_defect_avoided(p0_cases: list[dict[str, Any]]) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NO_QUOTE_RECOMMENDATION")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"


def test_28_p0_quote_independent_defect_avoided(p0_cases: list[dict[str, Any]]) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_QUOTE_INDEPENDENT_OUTPUT")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"


def test_29_p0_provider_unavailable_defect_avoided(p0_cases: list[dict[str, Any]]) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NO_PROVIDER_FAIL_CLOSED_DISPOSITION")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"


def test_30_p0_noncanonical_combo_defect_avoided(p0_cases: list[dict[str, Any]]) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_NONCANONICAL_OVER15_COMBO")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"


def test_31_p0_tie_order_defect_avoided(p0_cases: list[dict[str, Any]]) -> None:
    case = next(c for c in p0_cases if c["case_id"] == "LEGACY_SELECTOR_CONSTRUCTION_ORDER_TIE")
    res = comparator.evaluate_p0_case(case)
    assert res["canonical_avoids_defect"] is True
    assert res["result"] == "PASS"


# ==============================================================================
# SIDE EFFECT / AUTHORITY SENTINELS (Tests 32 - 44)
# ==============================================================================

def test_32_network_sentinel(
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
    report = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
    )
    assert report["network_used"] is False


def test_33_provider_acquisition_impossible(report: dict[str, Any], decision: dict[str, Any], corpus: dict[str, Any]) -> None:
    assert report["provider_acquisition"] is False
    assert decision["provider_acquisition"] is False
    assert corpus["provider_acquisition"] is False


def test_34_portfolio_not_invoked(report: dict[str, Any]) -> None:
    assert report["portfolio_invoked"] is False


def test_35_share_code_not_invoked(report: dict[str, Any]) -> None:
    assert report["share_code_invoked"] is False


def test_36_login_false(report: dict[str, Any]) -> None:
    assert report["login"] is False


def test_37_cookies_false(report: dict[str, Any]) -> None:
    assert report["cookies"] is False


def test_38_wallet_false(report: dict[str, Any]) -> None:
    assert report["wallet"] is False


def test_39_staking_false(report: dict[str, Any]) -> None:
    assert report["staking"] is False


def test_40_bet_false(report: dict[str, Any]) -> None:
    assert report["bet"] is False


def test_41_wager_placed_false(report: dict[str, Any]) -> None:
    assert report["wager_placed"] is False


def test_42_main_authority_false(report: dict[str, Any], decision: dict[str, Any], corpus: dict[str, Any]) -> None:
    assert report["main_authority"] is False
    assert decision["main_authority"] is False
    assert corpus["main_authority"] is False


def test_43_selection_authority_unchanged(report: dict[str, Any], decision: dict[str, Any]) -> None:
    assert report["selection_authority_changed"] is False
    assert decision["selection_authority_changed"] is False


def test_44_promotion_authority_false(report: dict[str, Any], decision: dict[str, Any], corpus: dict[str, Any]) -> None:
    assert report["promotion_authority"] is False
    assert decision["promotion_authority"] is False
    assert corpus["promotion_authority"] is False
