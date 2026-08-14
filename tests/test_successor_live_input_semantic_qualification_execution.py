from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from domain.successor_live_input_semantic_qualification_execution import (
    ASSESSMENT_SCOPE,
    ASSESSMENT_STATE,
    DATASET_NAME,
    NEXT_REQUIRED_BOUNDARY,
    PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA,
    PR55_UNVERIFIED_CANDIDATES_BLOB_SHA,
    PR57_UNVERIFIED_FACTS_BLOB_SHA,
    PR58_FIELD_EVIDENCE_QUALIFICATION_BLOB_SHA,
    PR62_FACT_STATUS_MATERIALIZER_BLOB_SHA,
    PR65_FIXTURE_INTELLIGENCE_SNAPSHOT_BLOB_SHA,
    PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA,
    PR78_MAIN_SHA,
    PR78_PROTOCOL_BLOB_SHA,
    PR78_PROTOCOL_SHA256,
    PR78_PROTOCOL_SIZE,
    SuccessorLiveInputSemanticQualificationExecutionError,
    build_successor_live_input_semantic_qualification_execution,
    canonical_successor_live_input_semantic_qualification_execution_bytes,
    revalidate_successor_live_input_semantic_qualification_execution,
    sha256_successor_live_input_semantic_qualification_execution,
)
from domain.successor_live_input_semantic_qualification_protocol import (
    LIVE_DATA_FRESHNESS_ROLE,
    SemanticQualificationStatus,
    build_successor_live_input_semantic_qualification_protocol,
    canonical_successor_live_input_semantic_qualification_protocol_bytes,
)


MODULE_PATH = Path("domain/successor_live_input_semantic_qualification_execution.py")
PROTOCOL_PATH = Path("domain/successor_live_input_semantic_qualification_protocol.py")
PR55_PATH = Path("domain/fotmob_reviewed_match_details_unverified_candidates.py")
PR57_PATH = Path("domain/fotmob_reviewed_match_details_unverified_facts.py")
PR58_PATH = Path("domain/fotmob_reviewed_match_details_field_evidence_qualification.py")
PR62_PATH = Path("domain/fotmob_reviewed_match_details_fact_status_materializer.py")
PR65_PATH = Path("domain/fotmob_reviewed_match_details_fixture_intelligence_snapshot.py")
PR66_PATH = Path("domain/fotmob_reviewed_match_details_model_feature_handoff.py")
PR31_PATH = Path("domain/fixture_model_features.py")

EXPECTED_ASSESSMENT_SHA256 = "aea27d67b93bf777a01c4956757ba7b31c521e9eea71006d20ca5bd4acf791f4"
EXPECTED_ASSESSMENT_SIZE = 6204


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def _assessment():
    return build_successor_live_input_semantic_qualification_execution()


def test_exact_pr78_and_reviewed_live_chain_blob_ancestry_is_checked_out() -> None:
    assessment = _assessment()
    assert assessment.repository_main_sha == PR78_MAIN_SHA
    assert _git_blob_sha(PROTOCOL_PATH) == PR78_PROTOCOL_BLOB_SHA
    assert _git_blob_sha(PR55_PATH) == PR55_UNVERIFIED_CANDIDATES_BLOB_SHA
    assert _git_blob_sha(PR57_PATH) == PR57_UNVERIFIED_FACTS_BLOB_SHA
    assert _git_blob_sha(PR58_PATH) == PR58_FIELD_EVIDENCE_QUALIFICATION_BLOB_SHA
    assert _git_blob_sha(PR62_PATH) == PR62_FACT_STATUS_MATERIALIZER_BLOB_SHA
    assert _git_blob_sha(PR65_PATH) == PR65_FIXTURE_INTELLIGENCE_SNAPSHOT_BLOB_SHA
    assert _git_blob_sha(PR66_PATH) == PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA
    assert _git_blob_sha(PR31_PATH) == PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA


def test_exact_pr78_protocol_identity_is_revalidated_before_execution() -> None:
    protocol = build_successor_live_input_semantic_qualification_protocol()
    raw = canonical_successor_live_input_semantic_qualification_protocol_bytes(protocol)
    assert len(raw) == PR78_PROTOCOL_SIZE
    assert hashlib.sha256(raw).hexdigest() == PR78_PROTOCOL_SHA256


def test_reviewed_live_chain_is_raw_scalar_then_status_and_mechanical_handoff() -> None:
    pr55 = PR55_PATH.read_text(encoding="utf-8")
    pr57 = PR57_PATH.read_text(encoding="utf-8")
    pr58 = PR58_PATH.read_text(encoding="utf-8")
    pr62 = PR62_PATH.read_text(encoding="utf-8")
    pr65 = PR65_PATH.read_text(encoding="utf-8")
    pr66 = PR66_PATH.read_text(encoding="utf-8")
    pr31 = PR31_PATH.read_text(encoding="utf-8")

    assert "Extract exact reviewed FotMob match-details scalars as UNVERIFIED candidates." in pr55
    assert "_extract_object_path" in pr55 and "_canonical_scalar" in pr55
    assert "value=_scalar(candidate.value)" in pr57
    assert 'QUALIFICATION_SCOPE = "EXACT_OBSERVATION_ONLY"' in pr58
    assert "only changed payload field is ``status``" in pr62
    assert "build_snapshot(" in pr65
    assert "build_model_feature_snapshot(" in pr66
    assert "It performs no feature engineering" in pr66
    assert "value = _finite_float(supported[0].value)" in pr31


def test_pr66_pr31_reviewed_path_does_not_import_legacy_feature_engines() -> None:
    roots: set[str] = set()
    for path in (PR66_PATH, PR31_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module)
    assert "services.team_form_service" not in roots
    assert "intelligence.form" not in roots
    assert "intelligence.elo_engine" not in roots
    assert "intelligence.fatigue" not in roots


def test_execution_is_fail_closed_for_all_five_successor_inputs() -> None:
    assessment = _assessment()
    assert assessment.schema_version == 1
    assert assessment.dataset_name == DATASET_NAME
    assert assessment.assessment_scope == ASSESSMENT_SCOPE
    assert assessment.assessment_state == ASSESSMENT_STATE
    assert assessment.semantic_qualification_executed is True
    assert assessment.all_five_exact_semantic_equivalence is False
    assert tuple(item.feature_id for item in assessment.features) == (
        "home_elo",
        "away_elo",
        "home_form",
        "away_form",
        "fatigue",
    )
    assert all(
        item.status is SemanticQualificationStatus.UNQUALIFIED_INSUFFICIENT_PROVENANCE
        for item in assessment.features
    )
    assert all(
        item.derivation_provenance_compatibility == "NOT_PROVEN_BY_REVIEWED_LIVE_CHAIN"
        for item in assessment.features
    )


def test_no_definition_mismatch_is_invented_when_provenance_is_missing() -> None:
    assessment = _assessment()
    assert all(
        item.status is not SemanticQualificationStatus.UNQUALIFIED_DEFINITION_MISMATCH
        for item in assessment.features
    )
    assert all(
        item.value_level_compatibility == "NOT_SUFFICIENT_TO_ESTABLISH_SEMANTIC_EQUIVALENCE"
        for item in assessment.features
    )


def test_live_data_freshness_remains_outside_successor_predictor_qualification() -> None:
    assessment = _assessment()
    assert assessment.live_data_freshness_role == LIVE_DATA_FRESHNESS_ROLE
    assert all(item.feature_id != "live_data_freshness" for item in assessment.features)


def test_next_boundary_is_exact_reviewed_prospective_feature_construction() -> None:
    assessment = _assessment()
    assert assessment.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert NEXT_REQUIRED_BOUNDARY == "BUILD_REVIEWED_EXACT_PROSPECTIVE_SUCCESSOR_FEATURE_CONSTRUCTION"


def test_canonical_assessment_hash_and_size_are_frozen() -> None:
    assessment = _assessment()
    raw = canonical_successor_live_input_semantic_qualification_execution_bytes(assessment)
    assert len(raw) == EXPECTED_ASSESSMENT_SIZE
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_ASSESSMENT_SHA256
    assert sha256_successor_live_input_semantic_qualification_execution(assessment) == EXPECTED_ASSESSMENT_SHA256
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert raw == (
        json.dumps(
            assessment.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def test_revalidator_accepts_only_exact_assessment_and_bytes() -> None:
    assessment = _assessment()
    raw = canonical_successor_live_input_semantic_qualification_execution_bytes(assessment)
    assert revalidate_successor_live_input_semantic_qualification_execution(
        assessment=assessment,
        assessment_bytes=raw,
    ) == assessment

    mutated = bytearray(raw)
    mutated[-2] = ord(" ") if mutated[-2] != ord(" ") else ord("\t")
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        revalidate_successor_live_input_semantic_qualification_execution(
            assessment=assessment,
            assessment_bytes=bytes(mutated),
        )
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        revalidate_successor_live_input_semantic_qualification_execution(
            assessment=assessment,
            assessment_bytes=bytearray(raw),  # type: ignore[arg-type]
        )


def test_positive_qualification_or_all_five_promotion_fails_closed() -> None:
    assessment = _assessment()
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        dataclasses.replace(
            assessment.features[0],
            status=SemanticQualificationStatus.QUALIFIED_EXACT_SEMANTIC_EQUIVALENCE,
        )
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        dataclasses.replace(assessment, all_five_exact_semantic_equivalence=True)


def test_chain_ancestry_or_result_mutation_fails_closed() -> None:
    assessment = _assessment()
    bad_blobs = dict(assessment.source_blob_shas)
    bad_blobs["pr66_model_feature_handoff"] = "f" * 40
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        dataclasses.replace(assessment, source_blob_shas=bad_blobs)
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        dataclasses.replace(assessment, repository_main_sha="f" * 40)
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        dataclasses.replace(assessment, assessment_state="QUALIFIED")


def test_all_downstream_authority_remains_false() -> None:
    assessment = _assessment()
    assert assessment.safety
    assert all(type(value) is bool and value is False for value in assessment.safety.values())
    promoted = dict(assessment.safety)
    promoted["expected_goals_production_authorized"] = True
    with pytest.raises(SuccessorLiveInputSemanticQualificationExecutionError):
        dataclasses.replace(assessment, safety=promoted)


def test_execution_module_is_inert_and_has_no_runtime_or_network_dependencies() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports <= {
        "__future__",
        "dataclasses",
        "hashlib",
        "json",
        "types",
        "collections.abc",
        "typing",
        "domain.successor_live_input_semantic_qualification_protocol",
    }
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "requests",
        "httpx",
        "selenium",
        "playwright",
        "score_matrix",
        "match_analyst",
        "pricing",
        "bookmaker",
        "selection_engine",
    ):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source
