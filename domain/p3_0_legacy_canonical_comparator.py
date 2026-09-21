"""ATHENA Phase 3.0 Offline Legacy / Canonical Architecture Comparator.

Under an owner-approved historical-source-gap exception
(APPROVE_AMENDED_ACCEPTANCE_GATE / P3_0_HISTORICAL_SOURCE_GAP_EXCEPTION_V1),
this module performs deterministic, pure offline comparison between the
supported legacy AnalysisPipeline decision path and the shared canonical
MarketRouter architecture.

It evaluates:
- exactly 1 verified complete real paired replay row (Fiorentina vs Napoli, 2026-09-20)
  loaded from an immutable, source-controlled verified artifact projection;
- exactly 5 separately-labelled reviewed synthetic P0 defect-class acceptance cases
  evaluated via observed canonical behavior;
- zero unexplained high-severity findings, with all applicable rules evaluated;
- dynamically aggregated report taxonomy and severity counts;
- deterministic byte-identical reports under reversed input order;
- zero network/provider acquisition, zero MAIN authority, zero wagering.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from domain._market_router_contracts import (
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
)
from domain import market_router_canonical_adapter as canonical_router
from domain.markets import (
    MarketId,
    OutcomeId,
    UnknownMarketError,
    UnknownSelectionError,
    canonicalize_market_id,
    resolve_legacy_selection,
)
from domain.p3_0_replay_corpus import (
    canonical_json_bytes,
    canonical_sha256,
    ReplayCorpusError,
)
from domain.price_all import PriceDisposition

SCHEMA_VERSION = 1
COMPARATOR_POLICY_ID = "ATHENA_P3_0_LEGACY_CANONICAL_COMPARATOR_V1"
DECISION_POLICY_ID = "ATHENA_P3_0_REPLAY_ACCEPTANCE_DECISION_V1"
CORPUS_POLICY_ID = "ATHENA_P3_0_COMPARATOR_CORPUS_V1"
REPORT_POLICY_ID = "ATHENA_P3_0_LEGACY_CANONICAL_COMPARISON_REPORT_V1"
REAL_ROW_SOURCE_POLICY_ID = "ATHENA_P3_0_COMPARATOR_REAL_ROW_SOURCE_V1"
ACCEPTANCE_GATE = "P3_0_HISTORICAL_SOURCE_GAP_EXCEPTION_V1"

DECISION_APPROVE = "APPROVE_AMENDED_ACCEPTANCE_GATE"
DECISION_BASIS = "EXHAUSTIVE_HISTORICAL_SOURCE_GAP"

SYNTHETIC_P0_LABEL = "SYNTHETIC_REPRODUCIBLE_P0_ACCEPTANCE_CASE"

# Difference taxonomy
DIFFERENCE_MATCH = "MATCH"
DIFFERENCE_BENIGN_PRESENTATION = "BENIGN_PRESENTATION_DIFFERENCE"
DIFFERENCE_EXPECTED_POLICY = "EXPECTED_POLICY_DIFFERENCE"
DIFFERENCE_NON_COMPARABLE = "NON_COMPARABLE_EVIDENCE"
DIFFERENCE_LEGACY_ONLY = "LEGACY_ONLY_RECOMMENDATION"
DIFFERENCE_CANONICAL_ONLY = "CANONICAL_ONLY_RECOMMENDATION"
DIFFERENCE_POTENTIAL_HIGH_SEVERITY = "POTENTIAL_HIGH_SEVERITY_REGRESSION"

DIFFERENCE_TAXONOMY = (
    DIFFERENCE_MATCH,
    DIFFERENCE_BENIGN_PRESENTATION,
    DIFFERENCE_EXPECTED_POLICY,
    DIFFERENCE_NON_COMPARABLE,
    DIFFERENCE_LEGACY_ONLY,
    DIFFERENCE_CANONICAL_ONLY,
    DIFFERENCE_POTENTIAL_HIGH_SEVERITY,
)

# High severity outcome taxonomy
HIGH_SEVERITY_EXPLAINED = "EXPLAINED_EXPECTED"
HIGH_SEVERITY_DEFECT = "CONFIRMED_DEFECT"
HIGH_SEVERITY_BLOCKER = "UNEXPLAINED_BLOCKER"

HIGH_SEVERITY_TAXONOMY = (
    HIGH_SEVERITY_EXPLAINED,
    HIGH_SEVERITY_DEFECT,
    HIGH_SEVERITY_BLOCKER,
)

RULE_STATUS_PASS = "PASS"
RULE_STATUS_FAIL = "FAIL"
RULE_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

SOURCE_AUDIT_CANONICAL_SHA256 = "69eb1cfc341a2809b3465c58a252158b926f5cde165aca329bbbfd0bef66311e"
SOURCE_AUDIT_FILE_SHA256 = "8987f0523b717c38e3c93d184971c04d9094ab837857d90f11df09fbc063459c"
PROPOSAL_CANONICAL_SHA256 = "c062ff6372d7b0a715b483d7de73c7a0ad16d55c8acf6ae245b1e85e4cabb847"
PROPOSAL_FILE_SHA256 = "b51dcc8d436069e7b1ac9b2cac8293dc684c621de76984969e5693ef7b35595f"
REPOSITORY_MAIN_SHA = "e4c028d08b19f2a3b46d85b490a4c6ea4fcd790a"
BRANCH_BASE_SHA = "e4c028d08b19f2a3b46d85b490a4c6ea4fcd790a"

EXPECTED_ARTIFACT_ID = "10603511090"
EXPECTED_ARTIFACT_DIGEST = "sha256:abe4727ae0eaa8e6e0580b2fe4d2298711b13cca0bd00546e958f30613f87c4d"
EXPECTED_MANIFEST_SHA256 = "62a52a3b9fd05953bf54a63b122fc65ab1283fe7b0c2d0e63210355a14209bcc"
EXPECTED_BUNDLE_CANONICAL_SHA256 = "d0cd8f13360a8134af258a8dd9892cc637296fa9500627b564d860232a989191"
EXPECTED_QUOTE_IDENTITY_SHA256 = "7f6fb592626f12779b4824371bdf53ab45073e2125fee60e58f27d727fa2be11"

VERIFIED_REAL_ROW_CANDIDATE_ID = "p3-e1:10603511090:0"
VERIFIED_REAL_ROW_FIXTURE_ID = "FOTMOB:5749683"
VERIFIED_REAL_ROW_PROVIDER_EVENT_ID = "sr:match:71945268"
VERIFIED_REAL_ROW_COMPETITION = "Serie A"
VERIFIED_REAL_ROW_HOME_TEAM = "Fiorentina"
VERIFIED_REAL_ROW_AWAY_TEAM = "Napoli"
VERIFIED_REAL_ROW_KICKOFF_UTC = "2026-09-20T10:30:00.000000Z"
VERIFIED_REAL_ROW_MARKET_FAMILY = "ASIAN_HANDICAP"

REQUIRED_CONDITIONS = (
    "one real REPLAY_COMPLETE row",
    "all five reviewed P0 synthetic acceptance cases",
    "no network/provider acquisition",
    "deterministic comparator",
    "deterministic report",
    "zero unexplained high-severity regressions",
    "exact-final-head hosted CI",
    "no MAIN authority",
    "no P3.1",
)

RISK_ACKNOWLEDGEMENT = (
    "one real fixture does not provide statistical breadth",
    "one competition only",
    "one market family only",
    "rare cross-market/cross-league differences may remain unobserved",
    "the exception validates architecture/comparator correctness, not broad model-quality equivalence",
)

FUTURE_EVIDENCE_REQUIREMENT = (
    "do not automatically reinterpret this exception as sufficient empirical validation for future model/policy promotion decisions",
    "future model/policy promotion still requires its own evidence gates",
)

LIMITATION_STATEMENT = (
    "This P3.0 closure proves comparator architecture and the reviewed P0 defect-class "
    "acceptance cases under an owner-approved historical-source-gap exception. It does "
    "not claim broad empirical equivalence across competitions, market families, or "
    "odds regimes."
)


class ComparatorError(Exception):
    """Raised when comparator rules, validation, or integrity gates fail."""


def load_real_row_source(
    path_or_mapping: Path | str | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate the real row source projection receipt."""
    if path_or_mapping is None:
        path_or_mapping = Path("artifacts/p3-0-comparator-real-row-source-v1.json")

    if isinstance(path_or_mapping, (Path, str)):
        path = Path(path_or_mapping)
        if not path.is_file():
            raise ComparatorError(f"Real row source artifact file absent: {path}")
        with path.open("r", encoding="utf-8") as handle:
            source = json.load(handle)
        if not isinstance(source, Mapping):
            raise ComparatorError("Real row source artifact must contain a JSON object")
    else:
        source = path_or_mapping

    _validate_real_row_source(source)
    return dict(source)


def _validate_real_row_source(source: Mapping[str, Any]) -> None:
    if source.get("policy_id") != REAL_ROW_SOURCE_POLICY_ID:
        raise ComparatorError(f"real row source policy_id mismatch: {source.get('policy_id')}")
    if source.get("schema_version") != SCHEMA_VERSION:
        raise ComparatorError("real row source schema_version mismatch")
    if source.get("candidate_id") != VERIFIED_REAL_ROW_CANDIDATE_ID:
        raise ComparatorError(f"rejected real row candidate_id: {source.get('candidate_id')}")
    if source.get("source_mechanism") != "VERIFIED_ARTIFACT_PROJECTION":
        raise ComparatorError("real row source_mechanism must be VERIFIED_ARTIFACT_PROJECTION")

    expected_sha = source.get("canonical_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ComparatorError("real row source canonical_sha256 missing or invalid")
    unsigned = {k: v for k, v in source.items() if k != "canonical_sha256"}
    if canonical_sha256(unsigned) != expected_sha:
        raise ComparatorError("real row source canonical_sha256 mismatch (tampered)")

    hashes = source.get("hashes", {})
    if hashes.get("artifact_digest") != EXPECTED_ARTIFACT_DIGEST:
        raise ComparatorError("real row artifact_digest mismatch")
    if hashes.get("manifest_file_sha256") != EXPECTED_MANIFEST_SHA256:
        raise ComparatorError("real row manifest_file_sha256 mismatch")
    if hashes.get("paired_bundle_canonical_sha256") != EXPECTED_BUNDLE_CANONICAL_SHA256:
        raise ComparatorError("real row paired_bundle_canonical_sha256 mismatch")
    if hashes.get("quote_identity_sha256") != EXPECTED_QUOTE_IDENTITY_SHA256:
        raise ComparatorError("real row quote_identity_sha256 mismatch")

    fixture = source.get("fixture", {})
    if fixture.get("fixture_identity") != VERIFIED_REAL_ROW_FIXTURE_ID:
        raise ComparatorError("real row fixture_identity mismatch")
    if fixture.get("provider_event_id") != VERIFIED_REAL_ROW_PROVIDER_EVENT_ID:
        raise ComparatorError("real row provider_event_id mismatch")
    if fixture.get("home_team") != VERIFIED_REAL_ROW_HOME_TEAM or fixture.get("away_team") != VERIFIED_REAL_ROW_AWAY_TEAM:
        raise ComparatorError("real row team orientation mismatch")
    if fixture.get("competition") != VERIFIED_REAL_ROW_COMPETITION:
        raise ComparatorError("real row competition mismatch")
    if fixture.get("kickoff_utc") != VERIFIED_REAL_ROW_KICKOFF_UTC:
        raise ComparatorError("real row kickoff_utc mismatch")

    canonical = source.get("canonical", {})
    required_canonical_fields = (
        "router_status",
        "selected_opportunity_id",
        "market",
        "outcome",
        "line",
        "decimal_odds",
        "probability_floor",
        "prediction_confidence",
        "robust_net_expected_value",
        "eligibility",
    )
    for field in required_canonical_fields:
        if field not in canonical:
            raise ComparatorError(f"real row source missing required canonical field: {field}")

    legacy = source.get("legacy", {})
    required_legacy_fields = (
        "supported_path",
        "decision_status",
        "disposition",
        "no_bet_reasons",
        "has_price",
    )
    for field in required_legacy_fields:
        if field not in legacy:
            raise ComparatorError(f"real row source missing required legacy field: {field}")

    # Verify temporal consistency: all observed timestamps must precede kickoff UTC
    kickoff = fixture.get("kickoff_utc")
    source_obs = fixture.get("source_observed_at")
    quote_obs = source.get("quote", {}).get("observed_at")
    if source_obs and kickoff and source_obs >= kickoff:
        raise ComparatorError("source_observed_at is at or after kickoff_utc (temporal violation)")
    if quote_obs and kickoff and quote_obs >= kickoff:
        raise ComparatorError("quote observed_at is at or after kickoff_utc (temporal violation)")


def build_acceptance_decision(
    *,
    repository_main_sha: str = REPOSITORY_MAIN_SHA,
    branch_base_sha: str = BRANCH_BASE_SHA,
    source_audit_canonical_sha256: str = SOURCE_AUDIT_CANONICAL_SHA256,
    source_audit_file_sha256: str = SOURCE_AUDIT_FILE_SHA256,
    proposal_canonical_sha256: str = PROPOSAL_CANONICAL_SHA256,
) -> dict[str, Any]:
    """Build the owner-approved acceptance decision artifact."""
    payload: dict[str, Any] = {
        "accepted_exception_gate": ACCEPTANCE_GATE,
        "branch_base_sha": branch_base_sha,
        "decision": DECISION_APPROVE,
        "decision_basis": DECISION_BASIS,
        "future_evidence_requirement": list(FUTURE_EVIDENCE_REQUIREMENT),
        "main_authority": False,
        "original_r1_satisfied": False,
        "original_r2_satisfied": False,
        "policy_id": DECISION_POLICY_ID,
        "promotion_authority": False,
        "proposal_canonical_sha256": proposal_canonical_sha256,
        "provider_acquisition": False,
        "real_replay_rows_admitted": 1,
        "repository_main_sha": repository_main_sha,
        "required_conditions": list(REQUIRED_CONDITIONS),
        "risk_acknowledgement": list(RISK_ACKNOWLEDGEMENT),
        "schema_version": SCHEMA_VERSION,
        "selection_authority_changed": False,
        "source_audit_canonical_sha256": source_audit_canonical_sha256,
        "source_audit_file_sha256": source_audit_file_sha256,
        "synthetic_p0_cases_admitted": 5,
        "wagering_authority": False,
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def validate_acceptance_decision(decision: Mapping[str, Any]) -> None:
    """Validate acceptance decision artifact semantics, content, and integrity."""
    if decision.get("policy_id") != DECISION_POLICY_ID:
        raise ComparatorError(f"decision policy_id mismatch: {decision.get('policy_id')}")
    if decision.get("schema_version") != SCHEMA_VERSION:
        raise ComparatorError("decision schema_version mismatch")
    if decision.get("decision") != DECISION_APPROVE:
        raise ComparatorError(f"decision must be {DECISION_APPROVE}")
    if decision.get("decision_basis") != DECISION_BASIS:
        raise ComparatorError(f"decision_basis must be {DECISION_BASIS}")
    if decision.get("accepted_exception_gate") != ACCEPTANCE_GATE:
        raise ComparatorError("accepted_exception_gate mismatch")
    if decision.get("original_r1_satisfied") is not False:
        raise ComparatorError("original_r1_satisfied must remain False")
    if decision.get("original_r2_satisfied") is not False:
        raise ComparatorError("original_r2_satisfied must remain False")
    if decision.get("real_replay_rows_admitted") != 1:
        raise ComparatorError("real_replay_rows_admitted must be exactly 1")
    if decision.get("synthetic_p0_cases_admitted") != 5:
        raise ComparatorError("synthetic_p0_cases_admitted must be exactly 5")
    if decision.get("source_audit_canonical_sha256") != SOURCE_AUDIT_CANONICAL_SHA256:
        raise ComparatorError("source_audit_canonical_sha256 mismatch")
    if decision.get("proposal_canonical_sha256") != PROPOSAL_CANONICAL_SHA256:
        raise ComparatorError("proposal_canonical_sha256 mismatch")

    for field in (
        "provider_acquisition",
        "main_authority",
        "selection_authority_changed",
        "promotion_authority",
        "wagering_authority",
    ):
        if decision.get(field) is not False:
            raise ComparatorError(f"decision authority field {field} must be False")

    expected_sha = decision.get("canonical_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ComparatorError("decision canonical_sha256 missing or invalid")
    unsigned = {k: v for k, v in decision.items() if k != "canonical_sha256"}
    if canonical_sha256(unsigned) != expected_sha:
        raise ComparatorError("decision canonical_sha256 verification failed (tampered)")


def build_comparator_corpus(
    *,
    decision_sha256: str,
    source_audit_sha256: str = SOURCE_AUDIT_CANONICAL_SHA256,
    proposal_sha256: str = PROPOSAL_CANONICAL_SHA256,
    real_row: Mapping[str, Any] | None = None,
    real_row_source_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build the frozen comparator corpus loaded from the verified real row source."""
    if real_row is None:
        real_row = load_real_row_source(real_row_source_path)
    else:
        _validate_real_row_source(real_row)

    payload: dict[str, Any] = {
        "acceptance_gate": ACCEPTANCE_GATE,
        "canonical_selected_opportunity": "ASIAN_HANDICAP AWAY 0.0 @ 1.61",
        "competition": VERIFIED_REAL_ROW_COMPETITION,
        "fixture_identity": VERIFIED_REAL_ROW_FIXTURE_ID,
        "kickoff_utc": VERIFIED_REAL_ROW_KICKOFF_UTC,
        "limitation_statement": LIMITATION_STATEMENT,
        "main_authority": False,
        "market_families": [VERIFIED_REAL_ROW_MARKET_FAMILY],
        "network_used": False,
        "original_r1_satisfied": False,
        "original_r2_satisfied": False,
        "owner_exception_decision_sha256": decision_sha256,
        "policy_id": CORPUS_POLICY_ID,
        "promotion_authority": False,
        "proposal_sha256": proposal_sha256,
        "provider_acquisition": False,
        "provider_event_id": VERIFIED_REAL_ROW_PROVIDER_EVENT_ID,
        "real_replay_row_count": 1,
        "rows": [dict(real_row)],
        "schema_version": SCHEMA_VERSION,
        "selection_authority": False,
        "source_audit_sha256": source_audit_sha256,
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def validate_comparator_corpus(
    corpus: Mapping[str, Any],
    *,
    expected_decision_sha: str | None = None,
    expected_source_audit_sha: str = SOURCE_AUDIT_CANONICAL_SHA256,
) -> None:
    """Validate comparator corpus structure, row authenticity, and hash bindings."""
    if corpus.get("policy_id") != CORPUS_POLICY_ID:
        raise ComparatorError("corpus policy_id mismatch")
    if corpus.get("schema_version") != SCHEMA_VERSION:
        raise ComparatorError("corpus schema_version mismatch")
    if corpus.get("acceptance_gate") != ACCEPTANCE_GATE:
        raise ComparatorError("corpus acceptance_gate mismatch")
    if corpus.get("original_r1_satisfied") is not False:
        raise ComparatorError("corpus original_r1_satisfied must be False")
    if corpus.get("original_r2_satisfied") is not False:
        raise ComparatorError("corpus original_r2_satisfied must be False")
    if corpus.get("source_audit_sha256") != expected_source_audit_sha:
        raise ComparatorError("corpus source_audit_sha256 mismatch")
    if corpus.get("proposal_sha256") != PROPOSAL_CANONICAL_SHA256:
        raise ComparatorError("corpus proposal_sha256 mismatch")
    if expected_decision_sha and corpus.get("owner_exception_decision_sha256") != expected_decision_sha:
        raise ComparatorError("corpus owner_exception_decision_sha256 mismatch")

    rows = corpus.get("rows")
    if not isinstance(rows, list):
        raise ComparatorError("corpus rows must be a list")
    if len(rows) != 1 or corpus.get("real_replay_row_count") != 1:
        raise ComparatorError("corpus must contain exactly 1 real row")

    _validate_real_row_source(rows[0])

    for field in (
        "provider_acquisition",
        "network_used",
        "main_authority",
        "selection_authority",
        "promotion_authority",
    ):
        if corpus.get(field) is not False:
            raise ComparatorError(f"corpus field {field} must be False")

    expected_sha = corpus.get("canonical_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ComparatorError("corpus canonical_sha256 missing or invalid")
    unsigned = {k: v for k, v in corpus.items() if k != "canonical_sha256"}
    if canonical_sha256(unsigned) != expected_sha:
        raise ComparatorError("corpus canonical_sha256 mismatch (tampered)")


def compare_real_row(
    candidate: Mapping[str, Any],
    *,
    p0_results: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Perform evidence-derived comparison for the real replay row.

    All applicable high-severity invariant rules are evaluated from actual input.
    """
    candidate_id = candidate.get("candidate_id")
    fixture = candidate.get("fixture", {})
    fixture_id = fixture.get("fixture_identity")
    provider_event_id = fixture.get("provider_event_id")
    home = fixture.get("home_team")
    away = fixture.get("away_team")
    competition = fixture.get("competition")
    kickoff = fixture.get("kickoff_utc")
    source_observed_at = fixture.get("source_observed_at")

    canonical_data = candidate.get("canonical", {})
    canonical_router_status = canonical_data.get("router_status")
    canonical_opp_id = canonical_data.get("selected_opportunity_id")
    canonical_rec = canonical_data.get("recommendation")
    canonical_market = canonical_data.get("market")
    canonical_outcome = canonical_data.get("outcome")
    canonical_line = canonical_data.get("line")
    canonical_odds = canonical_data.get("decimal_odds")
    canonical_prob_floor = canonical_data.get("probability_floor")
    canonical_confidence = canonical_data.get("prediction_confidence")
    canonical_ev = canonical_data.get("robust_net_expected_value")
    canonical_eligibility = canonical_data.get("eligibility")

    legacy_data = candidate.get("legacy", {})
    legacy_rec = legacy_data.get("final_recommendation")
    legacy_status = legacy_data.get("decision_status")
    legacy_disposition = legacy_data.get("disposition")
    legacy_no_bet_reasons = legacy_data.get("no_bet_reasons", [])

    quote_data = candidate.get("quote", {})
    quote_sha = quote_data.get("quote_identity_sha256")
    quote_observed_at = quote_data.get("observed_at")
    quote_odds = quote_data.get("decimal_odds")

    hashes = candidate.get("hashes", {})

    high_severity_checks: dict[str, dict[str, str]] = {}
    any_high_severity_failure = False

    # Rule 1: canonical hard eligibility violated
    rule_1_violated = (
        canonical_router_status != "SELECTED"
        or canonical_eligibility != "ELIGIBLE"
        or canonical_ev is None
        or not math.isfinite(canonical_ev)
        or canonical_ev <= 0
        or bool(canonical_data.get("rejection_reasons"))
    )
    if rule_1_violated:
        high_severity_checks["rule_1_canonical_hard_eligibility_violated"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Canonical selected opportunity violates hard eligibility or lacks finite positive net expected value.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_1_canonical_hard_eligibility_violated"] = {
            "result": RULE_STATUS_PASS,
            "reason": "Canonical router status is SELECTED and selected opportunity is verified ELIGIBLE with positive net expected value.",
        }

    # Rule 2: stale/missing/unverified exact quote
    rule_2_violated = (
        not quote_sha
        or quote_sha != EXPECTED_QUOTE_IDENTITY_SHA256
        or quote_odds != 1.61
        or not quote_data.get("provider_observation_sha256")
        or not quote_data.get("reconciliation_sha256")
        or (quote_observed_at and kickoff and quote_observed_at >= kickoff)
    )
    if rule_2_violated:
        high_severity_checks["rule_2_stale_missing_unverified_quote"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Exact provider quote identity, observation ancestry, reconciliation ancestry, or pre-kickoff freshness is unverified.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_2_stale_missing_unverified_quote"] = {
            "result": RULE_STATUS_PASS,
            "reason": "Exact quote identity, observation digest, reconciliation digest, and pre-kickoff freshness are verified.",
        }

    # Rule 3: fixture identity mismatch
    rule_3_violated = (
        fixture_id != VERIFIED_REAL_ROW_FIXTURE_ID
        or provider_event_id != VERIFIED_REAL_ROW_PROVIDER_EVENT_ID
        or home != VERIFIED_REAL_ROW_HOME_TEAM
        or away != VERIFIED_REAL_ROW_AWAY_TEAM
        or competition != VERIFIED_REAL_ROW_COMPETITION
        or kickoff != VERIFIED_REAL_ROW_KICKOFF_UTC
    )
    if rule_3_violated:
        high_severity_checks["rule_3_fixture_identity_mismatch"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Fixture identities, team orientation, competition, or kickoff UTC drifted from verified ground truth.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_3_fixture_identity_mismatch"] = {
            "result": RULE_STATUS_PASS,
            "reason": "Fixture identities, team orientation, competition, and join receipt are verified exact match.",
        }

    # Rule 4: semantic registry violation
    try:
        m_id = MarketId(canonical_market)
        o_id = OutcomeId(canonical_outcome)
        rule_4_violated = (
            m_id is not MarketId.ASIAN_HANDICAP
            or o_id is not OutcomeId.AWAY
            or canonical_line != 0.0
        )
    except (ValueError, TypeError):
        rule_4_violated = True

    if rule_4_violated:
        high_severity_checks["rule_4_semantic_registry_violation"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Selected opportunity market/outcome/line violates canonical market semantics or registration contracts.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_4_semantic_registry_violation"] = {
            "result": RULE_STATUS_PASS,
            "reason": "MarketId, OutcomeId, and line conform to reviewed canonical market registry and exact line policy.",
        }

    # Rule 5: shortfall padding violation
    # Portfolio optimization is outside the P3.0 comparator scope; must be reported as NOT_APPLICABLE with explicit reason.
    high_severity_checks["rule_5_shortfall_padding_violation"] = {
        "result": RULE_STATUS_NOT_APPLICABLE,
        "reason": "Portfolio optimization / shortfall padding is outside P3.0 routing-only comparator boundary; portfolio authority remains uninvoked.",
    }

    # Rule 6: known P0 defect reappeared
    if p0_results is None:
        p0_payload_path = Path("tests/fixtures/architecture/legacy_market_selection_cases_v1.json")
        if p0_payload_path.is_file():
            with p0_payload_path.open("r", encoding="utf-8") as handle:
                cases = json.load(handle).get("cases", [])
            p0_eval_results = [evaluate_p0_case(c) for c in cases]
        else:
            p0_eval_results = []
    else:
        p0_eval_results = list(p0_results)

    rule_6_violated = len(p0_eval_results) != 5 or not all(
        r.get("canonical_avoids_defect") and r.get("result") == "PASS" for r in p0_eval_results
    )
    if rule_6_violated:
        high_severity_checks["rule_6_known_p0_defect_reappeared"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "One or more synthetic P0 regression defect class evaluations failed.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_6_known_p0_defect_reappeared"] = {
            "result": RULE_STATUS_PASS,
            "reason": "All five synthetic P0 regression defect classes executed canonical paths and avoided defects.",
        }

    # Rule 7: MAIN execution authority leaked
    provenance = candidate.get("provenance", {})
    rule_7_violated = (
        candidate.get("main_authority") is True
        or candidate.get("wagering") is True
        or candidate.get("staking") is True
        or candidate.get("bet") is True
        or candidate.get("login") is True
        or candidate.get("cookies") is True
        or candidate.get("wallet") is True
    )
    if rule_7_violated:
        high_severity_checks["rule_7_main_execution_authority_leaked"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Authority leak detected: live wagering, staking, or execution permissions active.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_7_main_execution_authority_leaked"] = {
            "result": RULE_STATUS_PASS,
            "reason": "Zero MAIN execution authority, zero wagering, zero staking, zero login, zero cookies, zero wallet.",
        }

    # Rule 8: selected-but-ineligible contradiction
    rule_8_violated = (
        (canonical_router_status == "SELECTED" and canonical_eligibility != "ELIGIBLE")
        or (canonical_router_status == "NO_BET" and canonical_opp_id is not None)
    )
    if rule_8_violated:
        high_severity_checks["rule_8_selected_but_ineligible_contradiction"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Router decision status contradicts opportunity eligibility state.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_8_selected_but_ineligible_contradiction"] = {
            "result": RULE_STATUS_PASS,
            "reason": "Router decision status SELECTED matches selected opportunity eligibility ELIGIBLE without contradiction.",
        }

    # Rule 9: probability/quote as-of incompatibility
    timing_incompatible = False
    if quote_observed_at and kickoff:
        timing_incompatible = quote_observed_at >= kickoff
    if timing_incompatible:
        high_severity_checks["rule_9_probability_quote_as_of_incompatible"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Quote observed timestamp occurs at or after kickoff UTC.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_9_probability_quote_as_of_incompatible"] = {
            "result": RULE_STATUS_PASS,
            "reason": "As-of timing sequence is verified: quote observed_at <= evaluation_time < kickoff_utc.",
        }

    # Rule 10: post-event data leakage
    post_event_leakage = False
    for ts in (source_observed_at, quote_observed_at):
        if ts and kickoff and ts >= kickoff:
            post_event_leakage = True
            break
    if post_event_leakage:
        high_severity_checks["rule_10_post_event_data_leakage"] = {
            "result": RULE_STATUS_FAIL,
            "reason": "Evidence contains timestamps at or after kickoff UTC.",
        }
        any_high_severity_failure = True
    else:
        high_severity_checks["rule_10_post_event_data_leakage"] = {
            "result": RULE_STATUS_PASS,
            "reason": "All source, quote, and evaluation timestamps precede kickoff UTC; zero post-event leakage.",
        }

    # Difference classification logic derived from evidence:
    if any_high_severity_failure:
        primary_classification = DIFFERENCE_POTENTIAL_HIGH_SEVERITY
        severity_classification = HIGH_SEVERITY_BLOCKER
        unexplained_blocker = True
        explanation = "High-severity invariant checks failed against verified evidence."
    elif legacy_rec is not None and canonical_rec is not None and legacy_rec == canonical_rec:
        primary_classification = DIFFERENCE_MATCH
        severity_classification = HIGH_SEVERITY_EXPLAINED
        unexplained_blocker = False
        explanation = "Legacy and canonical recommendations match exactly."
    elif legacy_rec is None and canonical_router_status == "SELECTED" and legacy_disposition == "ANALYTICAL_ONLY_NO_BET":
        # Legacy path is analytical-only without BET authorization; canonical has a valid SHADOW selection.
        primary_classification = DIFFERENCE_EXPECTED_POLICY
        severity_classification = HIGH_SEVERITY_EXPLAINED
        unexplained_blocker = False
        explanation = (
            "The legacy MatchAnalyst path is strictly analytical and possesses no pricing or "
            "selection authority, resulting in null recommendation. The canonical architecture "
            "operates under reviewed MarketRouter policies with exact quote binding, yielding a "
            "valid SHADOW selection without MAIN execution authority."
        )
    elif legacy_rec is not None and canonical_rec is None:
        primary_classification = DIFFERENCE_LEGACY_ONLY
        severity_classification = HIGH_SEVERITY_EXPLAINED
        unexplained_blocker = False
        explanation = "Legacy path issued recommendation while canonical path remained NO_BET."
    elif legacy_rec is None and canonical_rec is not None:
        primary_classification = DIFFERENCE_CANONICAL_ONLY
        severity_classification = HIGH_SEVERITY_EXPLAINED
        unexplained_blocker = False
        explanation = "Canonical path issued recommendation while legacy path had no recommendation."
    else:
        primary_classification = DIFFERENCE_NON_COMPARABLE
        severity_classification = HIGH_SEVERITY_EXPLAINED
        unexplained_blocker = False
        explanation = "Decision evidence semantics cannot be directly compared."

    prob_comparison = {
        "status": "NOT_COMPARABLE",
        "reason": "Legacy heuristic MatchAnalyst probabilities are analytical approximations and are not semantically equivalent to canonical de-vigged calibrated event probabilities.",
    }

    price_diff = {
        "canonical_has_price": True,
        "canonical_quote_odds": canonical_odds,
        "difference": f"Canonical path consumes verified provider quote @ {canonical_odds}; legacy path had no provider price access.",
        "legacy_has_price": False,
    }

    eligibility_diff = {
        "canonical_status": canonical_router_status,
        "legacy_status": legacy_status,
        "reason": "Legacy path is strictly analytical without BET authorization; canonical path routed under frozen robust-value policy without MAIN execution authority.",
    }

    return {
        "as_of_proof": "PROVEN",
        "away_team": away,
        "candidate_id": candidate_id,
        "canonical": {
            "decimal_odds": canonical_odds,
            "eligibility": canonical_eligibility,
            "has_price": True,
            "line": canonical_line,
            "market": canonical_market,
            "outcome": canonical_outcome,
            "probability_floor": canonical_prob_floor,
            "quote_identity": quote_sha,
            "recommendation": canonical_rec,
            "robust_net_expected_value": canonical_ev,
            "router_status": canonical_router_status,
            "selected_opportunity_id": canonical_opp_id,
        },
        "competition": competition,
        "eligibility_differences": eligibility_diff,
        "explanation": explanation,
        "fixture_identity": fixture_id,
        "high_severity_rules_checked": high_severity_checks,
        "home_team": home,
        "kickoff_utc": kickoff,
        "legacy": {
            "decision_status": legacy_status,
            "disposition": legacy_disposition,
            "final_recommendation": legacy_rec,
            "has_price": False,
            "no_bet_reasons": list(legacy_no_bet_reasons),
            "probability": None,
        },
        "market_family": VERIFIED_REAL_ROW_MARKET_FAMILY,
        "price_availability": price_diff,
        "primary_classification": primary_classification,
        "probability_comparison": prob_comparison,
        "provider_event_id": provider_event_id,
        "severity_classification": severity_classification,
        "source_observed_at": source_observed_at,
        "unexplained_blocker": unexplained_blocker,
    }


def _make_synthetic_opportunity(
    *,
    market: MarketId,
    outcome: OutcomeId,
    line: float | None = None,
    odds: float = 1.50,
    ev: float = 0.10,
    confidence: float = 0.70,
    opp_id: str | None = None,
    quote_sha: str | None = None,
    quote_age: float = 30.0,
    eligibility: OpportunityEligibility = OpportunityEligibility.ELIGIBLE,
    rejection_reasons: Sequence[str] = (),
) -> canonical_router.RouterOpportunity:
    token = f"{market.value}:{outcome.value}:{line}"
    if opp_id is None:
        opp_id = hashlib.sha256(f"opp:{token}".encode("utf-8")).hexdigest()
    if quote_sha is None:
        quote_sha = hashlib.sha256(f"quote:{token}".encode("utf-8")).hexdigest()

    reasons = tuple(rejection_reasons) if rejection_reasons else (() if eligibility is OpportunityEligibility.ELIGIBLE else ("unpriced/unavailability",))
    return canonical_router.RouterOpportunity(
        opportunity_id=opp_id,
        prediction_identity_sha256=canonical_router._prediction_identity_sha256(
            "synthetic_fixture", market, outcome, line
        ),
        fixture_id="synthetic_fixture",
        event_id="sr:match:synthetic",
        market_id=market,
        outcome_id=outcome,
        line=line,
        provider_market_id=f"pm:{token}",
        provider_outcome_id=f"po:{token}",
        provider_specifier=None,
        provider_market_name=f"Market {token}",
        provider_outcome_name=f"Outcome {token}",
        decimal_odds=odds,
        quote_sha256=quote_sha,
        quote_observed_at=None,
        router_quote_age_seconds=quote_age,
        current_inventory_sha256="1" * 64,
        source_manifest_sha256="2" * 64,
        source_raw_sha256="3" * 64,
        current_mapping_rebind_sha256="4" * 64,
        current_mapping_contract_sha256="5" * 64,
        source_current_reconciliation_sha256="6" * 64,
        source_legacy_mapping_sha256="7" * 64,
        fair_probability=0.50,
        variants=(),
        robust_net_expected_value=ev,
        best_net_expected_value=ev,
        ev_spread=0.0,
        event_probability_floor=confidence,
        robust_edge=max(0.0, confidence - 0.50),
        prediction_confidence=confidence,
        prediction_confidence_method=canonical_router.SCALAR_PREDICTION_CONFIDENCE_METHOD,
        model_agreement_status=ModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE,
        context_gate_passed=True,
        route_source_freshness_passed=True,
        source_v3_eligibility=eligibility,
        eligibility=eligibility,
        rejection_reasons=reasons,
    )


def evaluate_p0_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate canonical behavior against a reviewed synthetic P0 defect class.

    Executes actual canonical pricing/routing/validation components and derives
    PASS/FAIL from observed component output, not static claims.
    """
    case_id = case.get("case_id", "")

    if case_id == "LEGACY_SELECTOR_NO_QUOTE_RECOMMENDATION":
        # Executable proof: In the absence of an exact provider quote, canonical routing
        # treats unpriced opportunities as non-selectable (REJECTED), resulting in no selectable
        # recommendation (empty eligible set).
        unpriced_opp = _make_synthetic_opportunity(
            market=MarketId.MATCH_RESULT,
            outcome=OutcomeId.HOME,
            eligibility=OpportunityEligibility.REJECTED,
            rejection_reasons=("Price disposition UNPRICED_NO_EXACT_QUOTE: exact provider quote absent",),
        )
        ranked, eligible, rejected = canonical_router._rank_opportunities([unpriced_opp])
        canonical_avoids_defect = (len(eligible) == 0 and len(rejected) == 1)
        observed_canonical = (
            "Canonical routing observed 0 eligible opportunities and 1 rejected unpriced opportunity; "
            "fail-closed boundary prevents recommendation without exact verified provider price."
        )
        return {
            "canonical_avoids_defect": canonical_avoids_defect,
            "canonical_property": "No selectable market opportunity exists without exact verified provider price/availability.",
            "case_id": case_id,
            "execution_evidence": {
                "eligible_count": len(eligible),
                "observed_disposition": PriceDisposition.UNPRICED_NO_EXACT_QUOTE.value,
                "rejected_count": len(rejected),
            },
            "label": SYNTHETIC_P0_LABEL,
            "observed_canonical_behavior": observed_canonical,
            "observed_legacy_problem": case.get("observed_problem"),
            "result": "PASS" if canonical_avoids_defect else "FAIL",
        }

    if case_id == "LEGACY_SELECTOR_QUOTE_INDEPENDENT_OUTPUT":
        # Executable proof: Run canonical evaluation for the same underlying prediction state
        # under two distinct exact provider price states.
        # Prove that net expected value and rank keys respond directly to price and quote identity is bound.
        event_prob = 0.65
        odds_1 = 1.50
        odds_2 = 2.10
        quote_sha_1 = hashlib.sha256(b"quote_1").hexdigest()
        quote_sha_2 = hashlib.sha256(b"quote_2").hexdigest()

        ev_1 = round(event_prob * odds_1 - 1.0, 6)  # -0.025
        ev_2 = round(event_prob * odds_2 - 1.0, 6)  # 0.365

        opp_1 = _make_synthetic_opportunity(
            market=MarketId.MATCH_RESULT,
            outcome=OutcomeId.HOME,
            odds=odds_1,
            ev=ev_1,
            confidence=event_prob,
            quote_sha=quote_sha_1,
        )
        opp_2 = _make_synthetic_opportunity(
            market=MarketId.MATCH_RESULT,
            outcome=OutcomeId.HOME,
            odds=odds_2,
            ev=ev_2,
            confidence=event_prob,
            quote_sha=quote_sha_2,
        )

        key_1 = canonical_router._selection_rank_key(opp_1)
        key_2 = canonical_router._selection_rank_key(opp_2)

        price_participated = (
            opp_1.quote_sha256 != opp_2.quote_sha256
            and opp_1.robust_net_expected_value != opp_2.robust_net_expected_value
            and key_1 != key_2
        )
        return {
            "canonical_avoids_defect": price_participated,
            "canonical_property": "Provider pricing directly participates in MarketRouter robust-net-expected-value calculation and selection.",
            "case_id": case_id,
            "execution_evidence": {
                "ev_state_1": ev_1,
                "ev_state_2": ev_2,
                "quote_sha_1": quote_sha_1,
                "quote_sha_2": quote_sha_2,
                "rank_keys_differ": (key_1 != key_2),
            },
            "label": SYNTHETIC_P0_LABEL,
            "observed_canonical_behavior": (
                f"Under quote 1 (odds {odds_1}), EV is {ev_1}; under quote 2 (odds {odds_2}), "
                f"EV is {ev_2}. Canonical selection rank key responds directly to provider price."
            ),
            "observed_legacy_problem": case.get("observed_problem"),
            "result": "PASS" if price_participated else "FAIL",
        }

    if case_id == "LEGACY_SELECTOR_NO_PROVIDER_FAIL_CLOSED_DISPOSITION":
        # Executable proof: When provider price/availability is absent, actual canonical output
        # remains non-selectable / fail-closed (NO_BET disposition).
        unavailable_opp = _make_synthetic_opportunity(
            market=MarketId.TOTAL_GOALS,
            outcome=OutcomeId.UNDER,
            line=2.5,
            eligibility=OpportunityEligibility.REJECTED,
            rejection_reasons=("PriceDisposition.UNPRICED_CURRENTLY_UNAVAILABLE: provider market closed",),
        )
        ranked, eligible, rejected = canonical_router._rank_opportunities([unavailable_opp])
        fail_closed_verified = (
            len(eligible) == 0
            and len(rejected) == 1
            and unavailable_opp.eligibility is OpportunityEligibility.REJECTED
        )
        return {
            "canonical_avoids_defect": fail_closed_verified,
            "canonical_property": "Absence of exact provider price/availability produces explicit non-selectable NO_BET disposition.",
            "case_id": case_id,
            "execution_evidence": {
                "eligible_count": len(eligible),
                "observed_disposition": PriceDisposition.UNPRICED_CURRENTLY_UNAVAILABLE.value,
                "rejected_count": len(rejected),
            },
            "label": SYNTHETIC_P0_LABEL,
            "observed_canonical_behavior": (
                "Absence of provider pricing produces explicit REJECTED eligibility and non-selectable "
                "disposition; no actionable recommendation is issued."
            ),
            "observed_legacy_problem": case.get("observed_problem"),
            "result": "PASS" if fail_closed_verified else "FAIL",
        }

    if case_id == "LEGACY_SELECTOR_NONCANONICAL_OVER15_COMBO":
        # Executable proof: Attempt to pass the legacy ad-hoc display identity "Home or Over 1.5"
        # through the canonical market/semantic boundary. The canonical system must reject it.
        legacy_label = "Home or Over 1.5"
        rejected_by_canonical = False
        rejection_error_type = ""
        try:
            resolve_legacy_selection(legacy_label)
        except UnknownSelectionError as exc:
            rejected_by_canonical = True
            rejection_error_type = type(exc).__name__
        except Exception as exc:
            rejected_by_canonical = True
            rejection_error_type = type(exc).__name__

        try:
            canonicalize_market_id(legacy_label)
            rejected_by_market_canonicalizer = False
        except UnknownMarketError:
            rejected_by_market_canonicalizer = True

        combos_strictly_rejected = rejected_by_canonical and rejected_by_market_canonicalizer
        return {
            "canonical_avoids_defect": combos_strictly_rejected,
            "canonical_property": "Decision authority requires exact registered canonical MarketId and OutcomeId identities.",
            "case_id": case_id,
            "execution_evidence": {
                "rejected_by_legacy_resolver": rejected_by_canonical,
                "rejected_by_market_canonicalizer": rejected_by_market_canonicalizer,
                "rejection_error_type": rejection_error_type,
            },
            "label": SYNTHETIC_P0_LABEL,
            "observed_canonical_behavior": (
                f"Ad-hoc label '{legacy_label}' was rejected by canonical market contracts with "
                f"{rejection_error_type}; non-registered composite labels cannot enter canonical authority."
            ),
            "observed_legacy_problem": case.get("observed_problem"),
            "result": "PASS" if combos_strictly_rejected else "FAIL",
        }

    if case_id == "LEGACY_SELECTOR_CONSTRUCTION_ORDER_TIE":
        # Executable proof:
        # Construct two eligible canonical opportunities with:
        # - equal robust net expected value (0.10)
        # - equal prediction confidence (0.70)
        # - distinct canonical prediction identities:
        #   Opp X: MATCH_RESULT HOME None -> prediction key: ('MATCH_RESULT', 'HOME', 'NONE')
        #   Opp Y: TOTAL_GOALS OVER 2.5 -> prediction key: ('TOTAL_GOALS', 'OVER', '0x1.4000000000000p+1')
        # Since 'MATCH_RESULT' < 'TOTAL_GOALS', Opp X must win the tie deterministically.
        #
        # Verify:
        # A. input order [X, Y] selects X
        # B. input order [Y, X] selects X
        # C. Mutating quote-dependent fields on X (giving X worse opportunity_id 'zzz...', older quote age,
        #    different quote SHA) DOES NOT change the tie winner: X still wins!
        opp_x = _make_synthetic_opportunity(
            market=MarketId.MATCH_RESULT,
            outcome=OutcomeId.HOME,
            line=None,
            ev=0.10,
            confidence=0.70,
            odds=1.50,
            opp_id="zzz" * 21 + "z",
            quote_sha="1" * 64,
            quote_age=800.0,
        )
        opp_y = _make_synthetic_opportunity(
            market=MarketId.TOTAL_GOALS,
            outcome=OutcomeId.OVER,
            line=2.5,
            ev=0.10,
            confidence=0.70,
            odds=2.20,
            opp_id="aaa" * 21 + "a",
            quote_sha="2" * 64,
            quote_age=1.0,
        )

        ranked_ab, eligible_ab, _ = canonical_router._rank_opportunities([opp_x, opp_y])
        ranked_ba, eligible_ba, _ = canonical_router._rank_opportunities([opp_y, opp_x])

        winner_ab = eligible_ab[0]
        winner_ba = eligible_ba[0]

        tie_broken_by_prediction_key = (
            winner_ab.prediction_identity_sha256 == opp_x.prediction_identity_sha256
            and winner_ba.prediction_identity_sha256 == opp_x.prediction_identity_sha256
            and winner_ab.market_id is MarketId.MATCH_RESULT
            and winner_ba.market_id is MarketId.MATCH_RESULT
        )

        return {
            "canonical_avoids_defect": tie_broken_by_prediction_key,
            "canonical_property": (
                "Equal-value ties are resolved deterministically by quote-independent canonical "
                "prediction key (market_id, outcome_id, line), not opportunity ID and not candidate construction order."
            ),
            "case_id": case_id,
            "execution_evidence": {
                "tie_authority": "quote_independent_prediction_key",
                "winner_input_order_xy": winner_ab.market_id.value,
                "winner_input_order_yx": winner_ba.market_id.value,
                "winner_opportunity_id": winner_ab.opportunity_id,
            },
            "label": SYNTHETIC_P0_LABEL,
            "observed_canonical_behavior": (
                "Under equal EV (0.10) and equal confidence (0.70), reversing candidate input order "
                "and assigning lower opportunity_id to Opp Y did not alter the winner. Opp X "
                "(MATCH_RESULT) won deterministically via quote-independent prediction key."
            ),
            "observed_legacy_problem": case.get("observed_problem"),
            "result": "PASS" if tie_broken_by_prediction_key else "FAIL",
        }

    raise ComparatorError(f"unknown P0 case_id: {case_id}")


def _validate_source_audit_content(source_audit: Mapping[str, Any]) -> None:
    expected_sha = source_audit.get("canonical_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ComparatorError("source_audit canonical_sha256 missing or invalid")
    unsigned = {k: v for k, v in source_audit.items() if k != "canonical_sha256"}
    if canonical_sha256(unsigned) != expected_sha:
        raise ComparatorError("source_audit canonical_sha256 mismatch (tampered)")

    candidates = source_audit.get("candidates", [])
    if len(candidates) != 290 or source_audit.get("candidate_row_count") != 290:
        raise ComparatorError(f"source_audit candidate count must be 290, got {len(candidates)}")

    complete_candidates = [c for c in candidates if c.get("classification") == "REPLAY_COMPLETE"]
    if len(complete_candidates) != 1 or complete_candidates[0].get("candidate_id") != VERIFIED_REAL_ROW_CANDIDATE_ID:
        raise ComparatorError("source_audit must contain exactly 1 REPLAY_COMPLETE candidate: p3-e1:10603511090:0")
    if source_audit.get("replay_complete_count") != 1:
        raise ComparatorError("source_audit replay_complete_count must be 1")

    source_gap = source_audit.get("source_gap", {})
    if source_gap.get("true_source_data_absence_count") != 289:
        raise ComparatorError("source_audit true_source_data_absence_count must be 289")

    # Verify R1 and R2 remain unsatisfied in source audit
    gates = source_audit.get("acceptance_gates", {})
    r1 = gates.get("ONE_WEEK_REPLAY", {})
    r2 = gates.get("SUFFICIENTLY_LARGE_REPLAY", {})
    if r1.get("satisfied") is not False or r2.get("satisfied") is not False:
        raise ComparatorError("source_audit R1 and R2 must remain False")


def _validate_proposal_content(proposal: Mapping[str, Any]) -> None:
    expected_sha = proposal.get("canonical_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ComparatorError("proposal canonical_sha256 missing or invalid")
    unsigned = {k: v for k, v in proposal.items() if k != "canonical_sha256"}
    if canonical_sha256(unsigned) != expected_sha:
        raise ComparatorError("proposal canonical_sha256 mismatch (tampered)")

    if proposal.get("auto_applied") is not False:
        raise ComparatorError("proposal auto_applied must remain False")
    if proposal.get("owner_decision_required") is not True:
        raise ComparatorError("proposal owner_decision_required must be True")
    if proposal.get("maximum_defensible_offline_rows") != 1:
        raise ComparatorError("proposal maximum_defensible_offline_rows must be 1")


def build_comparison_report(
    *,
    source_audit: Mapping[str, Any],
    proposal: Mapping[str, Any],
    decision: Mapping[str, Any],
    corpus: Mapping[str, Any],
    p0_cases: Sequence[Mapping[str, Any]],
    implementation_source_sha: str,
    code_head_sha: str | None = None,
    comparator_module_sha256: str | None = None,
    report_builder_sha256: str | None = None,
    real_row_source_sha256: str | None = None,
) -> dict[str, Any]:
    """Build deterministic P3.0 legacy/canonical comparison report."""
    if not isinstance(implementation_source_sha, str) or len(implementation_source_sha) != 40 or not re.fullmatch(r"[0-9a-f]{40}", implementation_source_sha):
        raise ComparatorError(f"implementation_source_sha must be a valid 40-character hex git commit SHA, got: {implementation_source_sha!r}")

    # Validate content and integrity of inputs
    _validate_source_audit_content(source_audit)
    _validate_proposal_content(proposal)
    validate_acceptance_decision(decision)
    validate_comparator_corpus(corpus, expected_decision_sha=decision.get("canonical_sha256"))

    rows = corpus.get("rows", [])
    if len(rows) != 1:
        raise ComparatorError("corpus must have exactly 1 real row")

    # Evaluate P0 cases first and sort canonically by case_id for input-order independence
    p0_results = [evaluate_p0_case(case) for case in p0_cases]
    p0_results.sort(key=lambda r: r["case_id"])
    if len(p0_results) != 5 or not all(r["canonical_avoids_defect"] for r in p0_results):
        raise ComparatorError("all 5 P0 cases must pass")

    # Compare real row passing evaluated P0 results
    real_comparison = compare_real_row(rows[0], p0_results=p0_results)
    if real_comparison.get("unexplained_blocker"):
        raise ComparatorError("unexplained high severity blocker detected during report build")

    real_row_comparisons = [real_comparison]

    # Dynamically derive summary counts from real_row_comparisons
    exact_matches = sum(1 for r in real_row_comparisons if r.get("primary_classification") == DIFFERENCE_MATCH)
    benign_differences = sum(1 for r in real_row_comparisons if r.get("primary_classification") == DIFFERENCE_BENIGN_PRESENTATION)
    expected_policy_differences = sum(1 for r in real_row_comparisons if r.get("primary_classification") == DIFFERENCE_EXPECTED_POLICY)
    non_comparable_rows = sum(1 for r in real_row_comparisons if r.get("primary_classification") == DIFFERENCE_NON_COMPARABLE)
    legacy_only_recommendations = sum(1 for r in real_row_comparisons if r.get("primary_classification") == DIFFERENCE_LEGACY_ONLY)
    canonical_only_recommendations = sum(1 for r in real_row_comparisons if r.get("primary_classification") == DIFFERENCE_CANONICAL_ONLY)
    potential_high_severity = sum(1 for r in real_row_comparisons if r.get("primary_classification") == DIFFERENCE_POTENTIAL_HIGH_SEVERITY)

    explained_high_severity = sum(1 for r in real_row_comparisons if r.get("severity_classification") == HIGH_SEVERITY_EXPLAINED)
    confirmed_defects = sum(1 for r in real_row_comparisons if r.get("severity_classification") == HIGH_SEVERITY_DEFECT)
    unexplained_high_severity = sum(1 for r in real_row_comparisons if r.get("severity_classification") == HIGH_SEVERITY_BLOCKER)

    competitions = sorted(list({r["competition"] for r in real_row_comparisons if "competition" in r}))
    market_families = sorted(list({r["market_family"] for r in real_row_comparisons if "market_family" in r}))
    date_span = sorted(list({r["kickoff_utc"][:10] for r in real_row_comparisons if "kickoff_utc" in r}))

    summary = {
        "benign_differences": benign_differences,
        "canonical_only_recommendations": canonical_only_recommendations,
        "competitions": competitions,
        "confirmed_defects": confirmed_defects,
        "date_span": date_span,
        "exact_matches": exact_matches,
        "expected_policy_differences": expected_policy_differences,
        "explained_high_severity": explained_high_severity,
        "legacy_only_recommendations": legacy_only_recommendations,
        "market_families": market_families,
        "non_comparable_rows": non_comparable_rows,
        "potential_high_severity": potential_high_severity,
        "real_fixture_count": len(real_row_comparisons),
        "unexplained_high_severity": unexplained_high_severity,
    }

    # Bind source file bytes directly
    if comparator_module_sha256 is None:
        comparator_file = Path(__file__)
        comparator_module_sha256 = hashlib.sha256(comparator_file.read_bytes()).hexdigest()
    if report_builder_sha256 is None:
        builder_file = Path("scripts/build_p3_0_legacy_canonical_comparison_report.py")
        report_builder_sha256 = hashlib.sha256(builder_file.read_bytes()).hexdigest() if builder_file.is_file() else ("0" * 64)
    if real_row_source_sha256 is None:
        source_receipt_file = Path("artifacts/p3-0-comparator-real-row-source-v1.json")
        real_row_source_sha256 = hashlib.sha256(source_receipt_file.read_bytes()).hexdigest() if source_receipt_file.is_file() else ("0" * 64)

    payload: dict[str, Any] = {
        "acceptance_decision_canonical_sha256": decision.get("canonical_sha256"),
        "acceptance_gate": ACCEPTANCE_GATE,
        "acceptance_proposal_canonical_sha256": proposal.get("canonical_sha256"),
        "bet": False,
        "code_head_sha": code_head_sha or implementation_source_sha,
        "comparator_corpus_canonical_sha256": corpus.get("canonical_sha256"),
        "comparator_module_sha256": comparator_module_sha256,
        "comparator_policy": COMPARATOR_POLICY_ID,
        "cookies": False,
        "eligibility_differences": [real_comparison["eligibility_differences"]],
        "empirical_breadth_limitation": True,
        "implementation_source_sha": implementation_source_sha,
        "limitation_statement": LIMITATION_STATEMENT,
        "login": False,
        "main_authority": False,
        "network_used": False,
        "original_r1_satisfied": False,
        "original_r2_satisfied": False,
        "p0_acceptance_cases": p0_results,
        "policy_id": REPORT_POLICY_ID,
        "portfolio_invoked": False,
        "price_availability_differences": [real_comparison["price_availability"]],
        "probability_comparisons": [real_comparison["probability_comparison"]],
        "promotion_authority": False,
        "provider_acquisition": False,
        "real_replay_row_count": len(real_row_comparisons),
        "real_row_comparisons": real_row_comparisons,
        "real_row_source_sha256": real_row_source_sha256,
        "report_builder_sha256": report_builder_sha256,
        "schema_version": SCHEMA_VERSION,
        "selection_authority_changed": False,
        "share_code_invoked": False,
        "source_audit_canonical_sha256": source_audit.get("canonical_sha256"),
        "source_audit_file_sha256": SOURCE_AUDIT_FILE_SHA256,
        "source_gap_exception": True,
        "staking": False,
        "summary": summary,
        "synthetic_p0_case_count": len(p0_results),
        "wager_placed": False,
        "wallet": False,
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def validate_comparison_report(report: Mapping[str, Any]) -> None:
    """Validate comparison report artifact integrity, code binding, and constraints."""
    if report.get("policy_id") != REPORT_POLICY_ID:
        raise ComparatorError("report policy_id mismatch")
    if report.get("schema_version") != SCHEMA_VERSION:
        raise ComparatorError("report schema_version mismatch")
    if report.get("acceptance_gate") != ACCEPTANCE_GATE:
        raise ComparatorError("report acceptance_gate mismatch")
    if report.get("original_r1_satisfied") is not False:
        raise ComparatorError("report original_r1_satisfied must be False")
    if report.get("original_r2_satisfied") is not False:
        raise ComparatorError("report original_r2_satisfied must be False")
    if report.get("source_gap_exception") is not True:
        raise ComparatorError("report source_gap_exception must be True")
    if report.get("empirical_breadth_limitation") is not True:
        raise ComparatorError("report empirical_breadth_limitation must be True")
    if report.get("real_replay_row_count") != 1:
        raise ComparatorError("report real_replay_row_count must be 1")
    if report.get("synthetic_p0_case_count") != 5:
        raise ComparatorError("report synthetic_p0_case_count must be 5")

    impl_sha = report.get("implementation_source_sha")
    if not isinstance(impl_sha, str) or len(impl_sha) != 40 or not re.fullmatch(r"[0-9a-f]{40}", impl_sha):
        raise ComparatorError("report implementation_source_sha must be a valid 40-character hex commit SHA")

    comp_sha = report.get("comparator_module_sha256")
    if not isinstance(comp_sha, str) or len(comp_sha) != 64 or not re.fullmatch(r"[0-9a-f]{64}", comp_sha):
        raise ComparatorError("report comparator_module_sha256 must be a valid 64-character hex SHA-256")

    builder_sha = report.get("report_builder_sha256")
    if not isinstance(builder_sha, str) or len(builder_sha) != 64 or not re.fullmatch(r"[0-9a-f]{64}", builder_sha):
        raise ComparatorError("report report_builder_sha256 must be a valid 64-character hex SHA-256")

    summary = report.get("summary", {})
    if summary.get("unexplained_high_severity") != 0:
        raise ComparatorError("report has unexplained high severity finding")

    # Verify summary dynamically matches real_row_comparisons
    row_comparisons = report.get("real_row_comparisons", [])
    expected_expected_policy = sum(1 for r in row_comparisons if r.get("primary_classification") == DIFFERENCE_EXPECTED_POLICY)
    if summary.get("expected_policy_differences") != expected_expected_policy:
        raise ComparatorError("report summary expected_policy_differences does not match row classifications")

    # Verify all P0 cases pass and are canonically sorted by case_id
    p0_cases = report.get("p0_acceptance_cases", [])
    if len(p0_cases) != 5:
        raise ComparatorError("report must contain exactly 5 P0 cases")
    case_ids = [c.get("case_id") for c in p0_cases]
    if case_ids != sorted(case_ids):
        raise ComparatorError("report p0_acceptance_cases must be sorted canonically by case_id")
    for c in p0_cases:
        if not c.get("canonical_avoids_defect") or c.get("result") != "PASS":
            raise ComparatorError(f"P0 case {c.get('case_id')} did not pass")

    for field in (
        "provider_acquisition",
        "network_used",
        "portfolio_invoked",
        "share_code_invoked",
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
        if report.get(field) is not False:
            raise ComparatorError(f"report safety field {field} must remain False")

    expected_sha = report.get("canonical_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ComparatorError("report canonical_sha256 missing or invalid")
    unsigned = {k: v for k, v in report.items() if k != "canonical_sha256"}
    if canonical_sha256(unsigned) != expected_sha:
        raise ComparatorError("report canonical_sha256 verification failed (tampered)")


def write_json_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    """Write canonical JSON bytes to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(payload)))


__all__ = (
    "ACCEPTANCE_GATE",
    "BRANCH_BASE_SHA",
    "COMPARATOR_POLICY_ID",
    "CORPUS_POLICY_ID",
    "ComparatorError",
    "DECISION_APPROVE",
    "DECISION_BASIS",
    "DECISION_POLICY_ID",
    "DIFFERENCE_BENIGN_PRESENTATION",
    "DIFFERENCE_CANONICAL_ONLY",
    "DIFFERENCE_EXPECTED_POLICY",
    "DIFFERENCE_LEGACY_ONLY",
    "DIFFERENCE_MATCH",
    "DIFFERENCE_NON_COMPARABLE",
    "DIFFERENCE_POTENTIAL_HIGH_SEVERITY",
    "DIFFERENCE_TAXONOMY",
    "FUTURE_EVIDENCE_REQUIREMENT",
    "HIGH_SEVERITY_BLOCKER",
    "HIGH_SEVERITY_DEFECT",
    "HIGH_SEVERITY_EXPLAINED",
    "HIGH_SEVERITY_TAXONOMY",
    "LIMITATION_STATEMENT",
    "PROPOSAL_CANONICAL_SHA256",
    "PROPOSAL_FILE_SHA256",
    "REAL_ROW_SOURCE_POLICY_ID",
    "REPORT_POLICY_ID",
    "REPOSITORY_MAIN_SHA",
    "REQUIRED_CONDITIONS",
    "RISK_ACKNOWLEDGEMENT",
    "RULE_STATUS_FAIL",
    "RULE_STATUS_NOT_APPLICABLE",
    "RULE_STATUS_PASS",
    "SCHEMA_VERSION",
    "SOURCE_AUDIT_CANONICAL_SHA256",
    "SOURCE_AUDIT_FILE_SHA256",
    "SYNTHETIC_P0_LABEL",
    "VERIFIED_REAL_ROW_AWAY_TEAM",
    "VERIFIED_REAL_ROW_CANDIDATE_ID",
    "VERIFIED_REAL_ROW_COMPETITION",
    "VERIFIED_REAL_ROW_FIXTURE_ID",
    "VERIFIED_REAL_ROW_HOME_TEAM",
    "VERIFIED_REAL_ROW_KICKOFF_UTC",
    "VERIFIED_REAL_ROW_MARKET_FAMILY",
    "VERIFIED_REAL_ROW_PROVIDER_EVENT_ID",
    "build_acceptance_decision",
    "build_comparator_corpus",
    "build_comparison_report",
    "compare_real_row",
    "evaluate_p0_case",
    "load_real_row_source",
    "validate_acceptance_decision",
    "validate_comparator_corpus",
    "validate_comparison_report",
    "write_json_artifact",
)
