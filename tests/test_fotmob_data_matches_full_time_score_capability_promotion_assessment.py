from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path
from typing import Any

import pytest

import domain.fotmob_data_matches_full_time_score_capability_promotion_protocol as pr93
from domain.fotmob_data_matches_full_time_score_capability_promotion_assessment import (
    ADAPTER_ABSENCE_EVIDENCE,
    ADAPTER_PATH_PRESENT_IN_EXACT_ASSESSED_TREE,
    ASSESSED_REPOSITORY_TREE_SHA,
    ASSESSMENT_SCOPE,
    ASSESSMENT_SHA256,
    ASSESSMENT_SIZE,
    ASSESSMENT_STATE,
    DATASET_NAME,
    EXCLUDED_PENALTY_COUNT,
    EXCLUDED_PENALTY_FIXTURE_ID,
    PARENT_SOURCE_KEY,
    PRIMARY_STATUS,
    PROPOSED_SOURCE_KEY,
    QUALIFIED_ORDINARY_FT_COUNT,
    REPOSITORY_MAIN_SHA,
    REUSABLE_ADAPTER_MODULE_PATH,
    REUSABLE_ADAPTER_STATE_AT_ASSESSMENT,
    SMALLEST_MISSING_REVIEWED_BOUNDARY,
    CapabilityPromotionGateResult,
    FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError,
    build_fotmob_data_matches_full_time_score_capability_promotion_assessment,
    canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes,
    revalidate_fotmob_data_matches_full_time_score_capability_promotion_assessment,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
PR93_PROTOCOL_BLOB_SHA = "c9b5d47674283e2a8f2d54a68966b97fbd418047"
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "source_capability_promotion_assessment_qualified",
    "reusable_score_adapter_implemented",
    "reusable_score_adapter_qualified",
    "source_capability_registration_qualified",
    "source_capability_registry_update_authorized",
    "source_capability_registry_update_performed",
    "parent_source_capability_mutation_authorized",
    "global_fotmob_full_time_score_capability_authorized",
    "penalty_score_semantics_qualified",
    "regulation_time_score_semantics_qualified",
    "extra_time_score_semantics_qualified",
    "bookmaker_settlement_semantics_qualified",
    "status_reason_semantics_globally_qualified",
    "historical_coverage_qualified",
    "source_history_adapter_approved",
    "source_history_completeness_proven",
    "pr80_constructor_input_authorized",
    "successor_live_inputs_qualified",
    "successor_candidate_approved",
    "expected_goals_transform_approved",
    "expected_goals_production_authorized",
    "score_matrix_authorized",
    "probability_inference_authorized",
    "probability_adjustment_authorized",
    "calibration_for_production_authorized",
    "pricing_authorized",
    "market_activation_authorized",
    "selection_authorized",
    "production_approval_authorized",
    "bet_authorized",
}


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def test_exact_assessment_identity_and_base_tree_are_frozen() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    exact = canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(value)

    assert DATASET_NAME == (
        "athena-fotmob-data-matches-full-time-score-capability-promotion-assessment-v1"
    )
    assert ASSESSMENT_SCOPE == (
        "EXECUTE_PR93_SCOPED_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT_ONLY"
    )
    assert ASSESSMENT_STATE == (
        "EXECUTED_FAIL_CLOSED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED"
    )
    assert REPOSITORY_MAIN_SHA == "30269b776b6ff66668b9149863ee6d4bdf8e8025"
    assert ASSESSED_REPOSITORY_TREE_SHA == "20347b1521283ea0988b263978027143bb31e255"
    assert hashlib.sha256(exact).hexdigest() == ASSESSMENT_SHA256
    assert len(exact) == ASSESSMENT_SIZE == 4568
    assert revalidate_fotmob_data_matches_full_time_score_capability_promotion_assessment(value) == value


def test_exact_pr93_and_source_capability_blob_ancestry_is_unchanged() -> None:
    assert (
        _git_blob_sha(
            ROOT / "domain" / "fotmob_data_matches_full_time_score_capability_promotion_protocol.py"
        )
        == PR93_PROTOCOL_BLOB_SHA
    )
    assert _git_blob_sha(ROOT / "domain" / "source_capabilities.py") == SOURCE_CAPABILITIES_BLOB_SHA
    assert pr93.PROTOCOL_SHA256 == (
        "8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009"
    )
    assert pr93.PROTOCOL_SIZE == 6458


def test_assessment_fails_closed_on_exact_missing_reusable_adapter_boundary() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()

    assert value.assessment_executed is True
    assert value.reusable_adapter_implemented is False
    assert value.adapter_path_present_in_exact_assessed_tree is False
    assert ADAPTER_PATH_PRESENT_IN_EXACT_ASSESSED_TREE is False
    assert value.reusable_adapter_module_path == REUSABLE_ADAPTER_MODULE_PATH == (
        "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py"
    )
    assert value.reusable_adapter_state_at_assessment == REUSABLE_ADAPTER_STATE_AT_ASSESSMENT == (
        "ABSENT_NOT_IMPLEMENTED_AT_PR93_PRE_REGISTRATION"
    )
    assert value.adapter_absence_evidence == ADAPTER_ABSENCE_EVIDENCE == (
        "EXACT_ASSESSED_MAIN_TREE_ENUMERATION_PLUS_PR93_FROZEN_PRE_REGISTRATION_ABSENCE_STATE"
    )
    assert value.primary_status == PRIMARY_STATUS == (
        "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED"
    )
    assert value.registration_qualified is False
    assert value.registry_update_performed is False


def test_prior_evidence_and_parent_registry_gates_pass_without_promotion() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()

    assert value.qualified_ordinary_ft_count == QUALIFIED_ORDINARY_FT_COUNT == 28
    assert value.excluded_penalty_count == EXCLUDED_PENALTY_COUNT == 1
    assert value.excluded_penalty_fixture_id == EXCLUDED_PENALTY_FIXTURE_ID == 5844873
    assert value.pr92_evidence_scope_matches_protocol is True
    assert value.parent_source_capability_matches_protocol is True
    assert value.proposed_source_key_present is False

    parent = SOURCE_CAPABILITY_REGISTRY[PARENT_SOURCE_KEY]
    assert parent.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert parent.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert parent.historical_coverage is CapabilityAvailability.UNKNOWN
    assert PROPOSED_SOURCE_KEY not in SOURCE_CAPABILITY_REGISTRY


def test_gate_sequence_is_exact_and_registration_is_not_reached() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    assert tuple((item.gate_id, item.outcome, item.status) for item in value.gate_results) == (
        ("PR93_PROTOCOL_ANCESTRY", "PASS", None),
        ("PARENT_SOURCE_CAPABILITY", "PASS", None),
        ("PROPOSED_SOURCE_KEY_ABSENCE", "PASS", None),
        ("PR92_ORDINARY_FT_EVIDENCE_SCOPE", "PASS", None),
        (
            "REUSABLE_PROSPECTIVE_SCORE_ADAPTER",
            "BLOCKED",
            "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED",
        ),
        ("DERIVED_CAPABILITY_REGISTRATION", "NOT_REACHED", None),
    )
    assert value.smallest_missing_reviewed_boundary == SMALLEST_MISSING_REVIEWED_BOUNDARY == (
        "BUILD_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER"
    )


def test_proposed_future_capability_remains_narrow_and_unregistered() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    assert dict(value.parent_capabilities_at_assessment) == dict(pr93.PARENT_REQUIRED_CAPABILITIES)
    assert dict(value.proposed_capabilities_if_future_registration_qualifies) == dict(
        pr93.PROPOSED_CAPABILITIES
    )
    assert value.proposed_capabilities_if_future_registration_qualifies["full_time_score"] == "CONFIRMED"
    assert value.proposed_capabilities_if_future_registration_qualifies["historical_coverage"] == "UNKNOWN"
    assert value.proposed_capabilities_if_future_registration_qualifies["freshness_metadata"] == "NOT_CAPTURED"
    assert value.proposed_source_key not in SOURCE_CAPABILITY_REGISTRY


def test_all_authority_stays_exact_false_and_receipt_is_immutable() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    assert set(value.safety) == SAFETY_KEYS
    assert all(type(flag) is bool and flag is False for flag in value.safety.values())

    with pytest.raises(TypeError):
        value.safety["bet_authorized"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        value.parent_capabilities_at_assessment["full_time_score"] = "CONFIRMED"  # type: ignore[index]
    with pytest.raises(TypeError):
        value.proposed_capabilities_if_future_registration_qualifies["historical_coverage"] = "CONFIRMED"  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("assessment_executed", False),
        ("reusable_adapter_implemented", True),
        ("proposed_source_key_present", True),
        ("parent_source_capability_matches_protocol", False),
        ("pr92_evidence_scope_matches_protocol", False),
        ("registration_qualified", True),
        ("registry_update_performed", True),
        ("adapter_path_present_in_exact_assessed_tree", True),
        ("primary_status", "QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION"),
    ),
)
def test_authority_or_result_mutation_fails_closed(field: str, bad: Any) -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    with pytest.raises(FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError):
        dataclasses.replace(value, **{field: bad})


def test_gate_result_rejects_non_pr93_blocker_or_status_on_pass() -> None:
    with pytest.raises(FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError):
        CapabilityPromotionGateResult(
            gate_id="X",
            outcome="BLOCKED",
            status="MADE_UP_STATUS",
            reason="X",
        )
    with pytest.raises(FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError):
        CapabilityPromotionGateResult(
            gate_id="X",
            outcome="PASS",
            status=PRIMARY_STATUS,
            reason="X",
        )


def test_assessment_module_has_no_network_or_downstream_runtime_imports() -> None:
    path = ROOT / "domain" / "fotmob_data_matches_full_time_score_capability_promotion_assessment.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(
        {"requests", "httpx", "aiohttp", "providers", "engine", "models", "services", "workers"}
    )
