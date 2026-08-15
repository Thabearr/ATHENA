from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path
from typing import Any

import pytest

import domain.fotmob_data_matches_final_result_semantics_protocol as pr83
import domain.fotmob_data_matches_final_result_semantics_validation_with_reason_gate as pr92
import domain.fotmob_data_matches_status_reason_semantics_validation as pr91
from domain.fotmob_data_matches_full_time_score_capability_promotion_protocol import (
    CURRENT_REUSABLE_ADAPTER_STATE,
    EXCLUDED_PENALTY_COUNT,
    EXCLUDED_PENALTY_FIXTURE_ID,
    HISTORICAL_COVERAGE_RULE,
    NEXT_REQUIRED_BOUNDARY,
    PARENT_NON_MUTATION_RULE,
    PARENT_REQUIRED_CAPABILITIES,
    PARENT_SOURCE_KEY,
    PENALTY_EXCLUSION_RULE,
    PROMOTION_MODE,
    PROMOTION_SCOPE_RULE,
    PROPOSED_CAPABILITIES,
    PROPOSED_EVIDENCE,
    PROPOSED_NOTES,
    PROPOSED_SOURCE_KEY,
    PROTOCOL_ID,
    PROTOCOL_SCOPE,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    PROTOCOL_STATE,
    QUALIFICATION_REQUIREMENTS,
    QUALIFIED_ORDINARY_FT_COUNT,
    REPOSITORY_MAIN_SHA,
    REUSABLE_ADAPTER_MODULE_PATH,
    REUSABLE_ADAPTER_RULE,
    SEMANTIC_EXCLUSION_RULE,
    STATUS_VOCABULARY,
    FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocolError,
    build_fotmob_data_matches_full_time_score_capability_promotion_protocol,
    canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes,
    revalidate_fotmob_data_matches_full_time_score_capability_promotion_protocol,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
PR92_BLOB = "0acd3cc554b927f0038bbaba122a54974e1c0829"
PR91_BLOB = "a663a2c2879cb70dbd1f31f0f8bbe4ff8f1034d6"
PR83_BLOB = "25f8045524badcb90239df59ac9c47f36fcffe34"
SOURCE_CAPABILITIES_BLOB = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
REVIEWED_CAPABILITY_TEST_BLOB = "8cf8837686aa8ebed0788676416b70ff3deffd4a"
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "source_capability_promotion_execution_authorized",
    "source_capability_registry_update_authorized",
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
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _capability_dict(capability: Any) -> dict[str, str]:
    return {
        "full_time_score": capability.full_time_score.value,
        "half_time_score": capability.half_time_score.value,
        "event_timestamps": capability.event_timestamps.value,
        "reliable_fixture_identity": capability.reliable_fixture_identity.value,
        "historical_coverage": capability.historical_coverage.value,
        "freshness_metadata": capability.freshness_metadata.value,
    }


def test_exact_merged_ancestry_blobs_are_frozen() -> None:
    assert REPOSITORY_MAIN_SHA == "5e63aaa8d2c036b2af95d0f3a48bd78adb5cc02e"
    assert (
        _git_blob_sha(
            ROOT
            / "domain"
            / "fotmob_data_matches_final_result_semantics_validation_with_reason_gate.py"
        )
        == PR92_BLOB
    )
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_status_reason_semantics_validation.py")
        == PR91_BLOB
    )
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_final_result_semantics_protocol.py")
        == PR83_BLOB
    )
    assert _git_blob_sha(ROOT / "domain" / "source_capabilities.py") == SOURCE_CAPABILITIES_BLOB
    assert (
        _git_blob_sha(ROOT / "tests" / "test_fotmob_reviewed_catalog_source_capability.py")
        == REVIEWED_CAPABILITY_TEST_BLOB
    )


def test_pr92_and_pr91_evidence_counts_are_exact() -> None:
    assert (pr92.RECEIPT_SHA256, pr92.RECEIPT_SIZE) == (
        "b821d5211de1e2a058b85ac1ca2ac50bdd0d3b577b54aa40c86ed6773bcb0c86",
        3561,
    )
    assert pr92.QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_COUNT == QUALIFIED_ORDINARY_FT_COUNT == 28
    assert pr92.NONQUALIFIED_EXECUTION_INPUT_COUNT == 0
    assert pr92.PR91_PENALTY_BLOCKED_COUNT == EXCLUDED_PENALTY_COUNT == 1
    assert pr92.PENALTY_FIXTURE_ID == EXCLUDED_PENALTY_FIXTURE_ID == 5844873
    assert pr91.ORDINARY_FT_REASON_QUALIFIED_COUNT == 28
    assert pr91.PENALTY_REASON_BLOCKED_COUNT == 1
    assert pr91.PENALTY_FIXTURE_ID == 5844873
    assert pr92.QUALIFIED_STATUS == (
        pr83.FinalResultSemanticsStatus.QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS.value
    )


def test_parent_capability_stays_identity_only_and_proposed_key_is_absent() -> None:
    parent = SOURCE_CAPABILITY_REGISTRY[PARENT_SOURCE_KEY]
    assert _capability_dict(parent) == dict(PARENT_REQUIRED_CAPABILITIES)
    assert parent.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert parent.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert parent.historical_coverage is CapabilityAvailability.UNKNOWN
    assert PROPOSED_SOURCE_KEY not in SOURCE_CAPABILITY_REGISTRY


def test_reusable_prospective_adapter_is_required_and_currently_absent() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert value.reusable_adapter_module_path == REUSABLE_ADAPTER_MODULE_PATH == (
        "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py"
    )
    assert value.current_reusable_adapter_state == CURRENT_REUSABLE_ADAPTER_STATE == (
        "ABSENT_NOT_IMPLEMENTED_AT_PR93_PRE_REGISTRATION"
    )
    assert not (ROOT / REUSABLE_ADAPTER_MODULE_PATH).exists()
    assert value.reusable_adapter_rule == REUSABLE_ADAPTER_RULE
    assert "REUSABLE_REVIEWED_PROSPECTIVE" in REUSABLE_ADAPTER_RULE
    assert "NOT_ONE_OFF_EVIDENCE_RECEIPT" in REUSABLE_ADAPTER_RULE
    assert (
        "REQUIRE_REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_ADAPTER_BEFORE_REGISTRY_PROMOTION"
        in QUALIFICATION_REQUIREMENTS
    )


def test_protocol_registers_a_new_scoped_key_not_a_parent_mutation() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert value.parent_source_key == PARENT_SOURCE_KEY == "fotmob_data_matches_reviewed_catalog"
    assert value.proposed_source_key == PROPOSED_SOURCE_KEY == (
        "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
    )
    assert value.parent_source_key != value.proposed_source_key
    assert value.promotion_mode == PROMOTION_MODE == (
        "REGISTER_NEW_DERIVED_ADAPTER_SCOPED_SOURCE_KEY_DO_NOT_MUTATE_PARENT"
    )
    assert value.parent_non_mutation_rule == PARENT_NON_MUTATION_RULE


def test_proposed_capability_is_exact_and_does_not_claim_coverage_or_freshness() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert dict(value.proposed_capabilities) == dict(PROPOSED_CAPABILITIES) == {
        "full_time_score": "CONFIRMED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
    assert value.historical_coverage_rule == HISTORICAL_COVERAGE_RULE == (
        "HISTORICAL_COVERAGE_REMAINS_UNKNOWN"
    )


def test_scope_and_penalty_exclusions_are_frozen() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert value.promotion_scope_rule == PROMOTION_SCOPE_RULE
    assert "PR92_QUALIFIED_SOURCE_REPORTED_FINISHED_SCORE" in PROMOTION_SCOPE_RULE
    assert value.penalty_exclusion_rule == PENALTY_EXCLUSION_RULE
    assert value.semantic_exclusion_rule == SEMANTIC_EXCLUSION_RULE
    assert "PENALTY_OR_OTHER_UNREVIEWED_REASON_FIXTURES_MUST_NOT_ENTER" in PENALTY_EXCLUSION_RULE
    for phrase in (
        "reusable reviewed prospective adapter",
        "regulation-time",
        "extra-time",
        "penalty-score",
        "bookmaker-settlement",
        "historical-coverage",
        "source-freshness",
        "model-readiness",
        "pricing",
        "selection",
        "betting authority",
    ):
        assert phrase in PROPOSED_NOTES


def test_proposed_evidence_is_repository_reviewed_only() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert value.proposed_evidence == PROPOSED_EVIDENCE
    for item in PROPOSED_EVIDENCE:
        path = item.split(":", 1)[0]
        assert (ROOT / path).is_file()


def test_exact_protocol_identity_and_state() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    exact = canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(value)
    assert PROTOCOL_ID == "FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL_V1"
    assert PROTOCOL_SCOPE == "PRE_REGISTERED_REVIEWED_SCOPED_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ONLY"
    assert PROTOCOL_STATE == "PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_CAPABILITY_CHANGE"
    assert hashlib.sha256(exact).hexdigest() == PROTOCOL_SHA256 == (
        "1a291349ecee28b0d4e5216daf495ebff61e1247724df17502c99641d3f55b38"
    )
    assert len(exact) == PROTOCOL_SIZE == 6163
    assert revalidate_fotmob_data_matches_full_time_score_capability_promotion_protocol(value) == value


def test_status_vocabulary_and_next_boundary_are_exact() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert value.status_vocabulary == STATUS_VOCABULARY == (
        "QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION",
        "BLOCKED_PR92_EVIDENCE_ANCESTRY_DRIFT",
        "BLOCKED_PARENT_SOURCE_CAPABILITY_DRIFT",
        "BLOCKED_PROPOSED_SOURCE_KEY_ALREADY_EXISTS",
        "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED",
        "BLOCKED_PROPOSED_CAPABILITY_SCOPE_OVERCLAIM",
        "BLOCKED_PENALTY_OR_UNREVIEWED_REASON_INCLUDED",
    )
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT"
    )
    assert value.qualification_requirements == QUALIFICATION_REQUIREMENTS


def test_every_authority_remains_exact_false() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert set(value.safety) == SAFETY_KEYS
    assert all(type(flag) is bool and flag is False for flag in value.safety.values())


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("schema_version", True),
        ("qualified_ordinary_ft_count", 29),
        ("excluded_penalty_count", 2),
        ("excluded_penalty_fixture_id", 1),
        ("proposed_source_key", PARENT_SOURCE_KEY),
        ("promotion_mode", "MUTATE_PARENT"),
        ("current_reusable_adapter_state", "IMPLEMENTED"),
        ("reusable_adapter_rule", "ONE_OFF_RECEIPT_IS_ENOUGH"),
        ("next_required_boundary", "SKIP_EXECUTION"),
    ),
)
def test_protocol_mutation_fails_closed(field: str, bad: Any) -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    with pytest.raises(FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocolError):
        dataclasses.replace(value, **{field: bad})


def test_capability_and_safety_mappings_are_detached_and_immutable() -> None:
    value = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    with pytest.raises(TypeError):
        value.proposed_capabilities["full_time_score"] = "UNKNOWN"  # type: ignore[index]
    with pytest.raises(TypeError):
        value.parent_required_capabilities["full_time_score"] = "CONFIRMED"  # type: ignore[index]
    with pytest.raises(TypeError):
        value.safety["bet_authorized"] = True  # type: ignore[index]

    bad = dict(value.proposed_capabilities)
    bad["historical_coverage"] = "CONFIRMED"
    with pytest.raises(FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocolError):
        dataclasses.replace(value, proposed_capabilities=bad)


def test_protocol_imports_no_network_or_downstream_runtime_modules() -> None:
    path = ROOT / "domain" / "fotmob_data_matches_full_time_score_capability_promotion_protocol.py"
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
