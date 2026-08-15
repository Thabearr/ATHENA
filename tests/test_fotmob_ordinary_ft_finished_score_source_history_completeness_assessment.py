from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_assessment as assessment_module
import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_protocol as pr99
from domain.fotmob_ordinary_ft_finished_score_source_history_completeness_assessment import (
    ASSESSMENT_SHA256,
    ASSESSMENT_SIZE,
    ASSESSMENT_STATE,
    SMALLEST_MISSING_REVIEWED_BOUNDARY,
    STATUS_VOCABULARY,
    FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError,
    FotMobOrdinaryFtSourceHistoryQualificationStatus,
    build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment,
    canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment_bytes,
)


ROOT = Path(__file__).resolve().parents[1]


def _git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def test_assessment_is_exact_canonical_fail_closed_evidence() -> None:
    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()
    exact = (
        canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment_bytes(
            value
        )
    )

    assert value.assessment_state == ASSESSMENT_STATE
    assert value.assessment_executed is True
    assert value.network_acquisition_performed is False
    assert value.history_adapter_materialized is False
    assert value.history_rows_materialized == 0
    assert value.derived_score_capability_revalidated is True
    assert len(exact) == ASSESSMENT_SIZE == 4720
    assert hashlib.sha256(exact).hexdigest() == ASSESSMENT_SHA256
    assert ASSESSMENT_SHA256 == (
        "069a66ac3c10d6d1f7da24cd0219fc178328b3327cd1446efaaff3dfec9cffb3"
    )
    assert set(value.safety.values()) == {False}


def test_assessment_binds_exact_pr99_registry_and_adapter_ancestry() -> None:
    expected_blobs = {
        ROOT
        / "domain"
        / "fotmob_ordinary_ft_finished_score_source_history_completeness_protocol.py": (
            "3dd38f5f61c20c10900fa0bee9a30a69a58a3006"
        ),
        ROOT / "domain" / "source_capabilities.py": (
            "37b919eb5efa0c931e1bf10d3f845865567ef0c4"
        ),
        ROOT
        / "domain"
        / "fotmob_data_matches_ordinary_ft_finished_score_adapter.py": (
            "868563206e09010fce74b4ba7954028930baad54"
        ),
    }
    assert {path: _git_blob_oid(path) for path in expected_blobs} == expected_blobs

    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()
    assert value.repository_main_sha == "43fb4aa09df0255bd76ddde0b02786a73f758771"
    assert value.pr99_protocol_blob_sha == expected_blobs[
        ROOT
        / "domain"
        / "fotmob_ordinary_ft_finished_score_source_history_completeness_protocol.py"
    ]
    assert value.pr99_protocol_sha256 == (
        "edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87"
    )
    assert value.pr99_protocol_size == 5741
    assert value.pr98_source_capabilities_blob_sha == expected_blobs[
        ROOT / "domain" / "source_capabilities.py"
    ]
    assert value.reviewed_ordinary_ft_adapter_blob_sha == expected_blobs[
        ROOT / "domain" / "fotmob_data_matches_ordinary_ft_finished_score_adapter.py"
    ]


def test_registered_derived_score_capability_passes_but_history_does_not() -> None:
    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()
    gates = {gate.gate_id: gate for gate in value.gate_results}

    assert value.current_reviewed_source_facts == {
        "derived_full_time_score": "CONFIRMED",
        "derived_reliable_fixture_identity": "CONFIRMED",
        "derived_historical_coverage": "UNKNOWN",
        "parent_full_time_score": "NOT_CAPTURED",
        "parent_historical_coverage": "UNKNOWN",
        "validated_terminal_candidate_count": 29,
        "validated_ordinary_ft_qualified_count": 28,
        "validated_penalty_fixture_excluded": 5844873,
    }
    assert gates["DERIVED_SCORE_CAPABILITY"].outcome == "PASSED"
    assert gates["DERIVED_SCORE_CAPABILITY"].status is None

    assert value.primary_status is (
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN
    )
    assert value.blocking_statuses == (
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN,
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN,
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_LEAGUE_MAPPING_UNPROVEN,
    )
    assert (
        FotMobOrdinaryFtSourceHistoryQualificationStatus.QUALIFIED_COMPLETE_REVIEWED_ORDINARY_FT_HISTORY
        not in value.blocking_statuses
    )


def test_protocol_status_vocabulary_and_frozen_rules_are_preserved() -> None:
    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()

    assert STATUS_VOCABULARY == tuple(pr99.QUALIFICATION_STATUS_VOCABULARY)
    assert value.frozen_model_league_codes == (
        "B1",
        "D1",
        "E0",
        "F1",
        "G1",
        "I1",
        "N1",
        "P1",
        "SC0",
        "SP1",
        "T1",
    )
    assert value.initialization_boundary_rule == (
        "MUST_BE_PROVEN_EQUIVALENT_TO_FROZEN_PR69_REPLAY_START_NOT_CHOSEN_AD_HOC"
    )
    assert value.derived_source_additional_requirements == tuple(
        pr99.DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS
    )


def test_corpus_specific_gates_are_not_falsely_claimed_as_observed_failures() -> None:
    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()
    gates = {gate.gate_id: gate for gate in value.gate_results}

    assert tuple(gate.gate_id for gate in value.gate_results) == (
        "DERIVED_SCORE_CAPABILITY",
        "HISTORICAL_COVERAGE",
        "ELO_INITIALIZATION_BOUNDARY",
        "ELEVEN_LEAGUE_MAPPING",
        "DAILY_DATE_COVERAGE",
        "FINISHED_RESULT_EVIDENCE_COVERAGE",
        "NON_ORDINARY_FT_RESULT_STATES",
        "IDENTITY_AND_CHRONOLOGY_CONFLICTS",
    )
    assert gates["HISTORICAL_COVERAGE"].outcome == "BLOCKED"
    assert gates["ELO_INITIALIZATION_BOUNDARY"].outcome == "UNPROVEN"
    assert gates["ELEVEN_LEAGUE_MAPPING"].outcome == "UNPROVEN"

    for gate_id in (
        "DAILY_DATE_COVERAGE",
        "FINISHED_RESULT_EVIDENCE_COVERAGE",
        "NON_ORDINARY_FT_RESULT_STATES",
        "IDENTITY_AND_CHRONOLOGY_CONFLICTS",
    ):
        assert gates[gate_id].outcome == "NOT_REACHED"
        assert gates[gate_id].status is None

    assert value.non_reached_statuses == (
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_REQUIRED_DATE_GAP,
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_RESULT_EVIDENCE_GAP,
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW,
        FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT,
    )


def test_smallest_missing_boundary_pre_registers_history_acquisition_before_network_use() -> None:
    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()
    assert value.smallest_missing_reviewed_boundary == SMALLEST_MISSING_REVIEWED_BOUNDARY
    assert SMALLEST_MISSING_REVIEWED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_PROTOCOL"
    )


def test_assessment_rejects_qualification_materialization_and_safety_mutations() -> None:
    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()

    with pytest.raises(
        FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError,
        match="differs from frozen result",
    ):
        dataclasses.replace(
            value,
            primary_status=(
                FotMobOrdinaryFtSourceHistoryQualificationStatus.QUALIFIED_COMPLETE_REVIEWED_ORDINARY_FT_HISTORY
            ),
        )

    with pytest.raises(
        FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError,
        match="network_acquisition_performed must remain exact False",
    ):
        dataclasses.replace(value, network_acquisition_performed=True)

    with pytest.raises(
        FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError,
        match="history_adapter_materialized must remain exact False",
    ):
        dataclasses.replace(value, history_adapter_materialized=True)

    safety = dict(value.safety)
    safety["source_history_completeness_proven"] = True
    with pytest.raises(
        FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError,
        match="differs from frozen result",
    ):
        dataclasses.replace(value, safety=safety)


def test_assessment_rejects_malformed_status_types_fail_closed() -> None:
    value = build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()
    with pytest.raises(
        FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError,
        match="primary_status must be an exact PR100 qualification status",
    ):
        dataclasses.replace(value, primary_status="BLOCKED_HISTORICAL_COVERAGE_UNPROVEN")


def test_assessment_rejects_mutated_pr99_identity(monkeypatch) -> None:
    monkeypatch.setattr(assessment_module, "PR99_PROTOCOL_SHA256", "0" * 64)
    with pytest.raises(
        FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError,
        match="PR99 source-history protocol constants changed",
    ):
        build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()


def test_assessment_is_domain_only_and_cannot_acquire_or_infer_downstream() -> None:
    source = Path(assessment_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
            imported_modules.add(node.module)

    assert imported_roots.isdisjoint(
        {
            "requests",
            "httpx",
            "aiohttp",
            "playwright",
            "workers",
            "providers",
            "api",
            "services",
            "engine",
            "models",
            "database",
            "repositories",
        }
    )
    assert all(
        token not in module_name
        for module_name in imported_modules
        for token in (
            "score_matrix",
            "probability",
            "pricing",
            "selection",
            "betting",
            "sportybet",
        )
    )
