from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

import domain.prospective_successor_source_history_completeness_assessment as assessment_module
from domain.prospective_successor_source_history_completeness_assessment import (
    ASSESSMENT_SHA256,
    ASSESSMENT_SIZE,
    ASSESSMENT_STATE,
    ProspectiveSuccessorSourceHistoryCompletenessAssessmentError,
    SMALLEST_MISSING_REVIEWED_BOUNDARY,
    build_prospective_successor_source_history_completeness_assessment,
    canonical_prospective_successor_source_history_completeness_assessment_bytes,
)
from domain.prospective_successor_source_history_completeness_protocol import (
    SourceHistoryQualificationStatus,
)


ROOT = Path(__file__).resolve().parents[1]


def _git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def test_assessment_is_exact_canonical_fail_closed_evidence() -> None:
    value = build_prospective_successor_source_history_completeness_assessment()
    exact = canonical_prospective_successor_source_history_completeness_assessment_bytes(
        value
    )

    assert value.assessment_state == ASSESSMENT_STATE
    assert value.assessment_executed is True
    assert value.history_adapter_materialized is False
    assert value.history_rows_materialized == 0
    assert len(exact) == ASSESSMENT_SIZE == 3763
    assert hashlib.sha256(exact).hexdigest() == ASSESSMENT_SHA256
    assert ASSESSMENT_SHA256 == (
        "de8f7398c588a210a9073e23ff67c81b9d8c38b6afc5d5b3c5e72b0c71f0a231"
    )
    assert set(value.safety.values()) == {False}


def test_assessment_binds_exact_pr81_and_reviewed_source_blobs() -> None:
    expected = {
        ROOT / "domain" / "prospective_successor_source_history_completeness_protocol.py": "6d9fc8a32d99cd4013836b2378f85b7dfe971d84",
        ROOT / "domain" / "source_capabilities.py": "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96",
        ROOT / "domain" / "fotmob_data_matches_capture.py": "ca2149395de868104666620173b55a880b10c729",
        ROOT / "domain" / "fotmob_data_matches_schema.py": "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f",
        ROOT / "domain" / "fotmob_reviewed_match_details_capture.py": "22e9b8c111abc38dae043b3274a4b8b2c7b90047",
    }
    assert {_git_blob_oid(path) for path in expected} == set(expected.values())

    value = build_prospective_successor_source_history_completeness_assessment()
    assert value.repository_main_sha == "aeac6c3b54c5c39c73f6aadf27a3cd012475a4ed"
    assert value.pr81_protocol_blob_sha == expected[
        ROOT / "domain" / "prospective_successor_source_history_completeness_protocol.py"
    ]
    assert value.pr81_protocol_sha256 == (
        "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
    )
    assert value.pr81_protocol_size == 4223
    assert value.source_blob_shas == {
        "fotmob_data_matches_capture": expected[
            ROOT / "domain" / "fotmob_data_matches_capture.py"
        ],
        "fotmob_data_matches_schema": expected[
            ROOT / "domain" / "fotmob_data_matches_schema.py"
        ],
        "fotmob_reviewed_match_details_capture": expected[
            ROOT / "domain" / "fotmob_reviewed_match_details_capture.py"
        ],
        "source_capabilities": expected[ROOT / "domain" / "source_capabilities.py"],
    }


def test_current_reviewed_source_fails_before_history_materialization() -> None:
    value = build_prospective_successor_source_history_completeness_assessment()

    assert value.current_reviewed_source_facts == {
        "reliable_fixture_identity": "CONFIRMED",
        "full_time_score": "NOT_CAPTURED",
        "historical_coverage": "UNKNOWN",
        "data_matches_raw_full_time_score_candidate": "AMBIGUOUS",
        "reviewed_match_details_capture_temporal_role": "STRICTLY_PRE_KICKOFF_ONLY",
    }
    assert value.primary_status is (
        SourceHistoryQualificationStatus.BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS
    )
    assert value.blocking_statuses == (
        SourceHistoryQualificationStatus.BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS,
        SourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN,
        SourceHistoryQualificationStatus.BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN,
        SourceHistoryQualificationStatus.BLOCKED_LEAGUE_MAPPING_UNPROVEN,
    )
    assert SourceHistoryQualificationStatus.QUALIFIED_COMPLETE_REVIEWED_HISTORY not in (
        value.blocking_statuses
    )


def test_later_corpus_specific_gates_are_not_falsely_claimed_as_observed_failures() -> None:
    value = build_prospective_successor_source_history_completeness_assessment()
    gates = {gate.gate_id: gate for gate in value.gate_results}

    assert tuple(gate.gate_id for gate in value.gate_results) == (
        "FINAL_RESULT_SEMANTICS",
        "HISTORICAL_COVERAGE",
        "ELO_INITIALIZATION_BOUNDARY",
        "ELEVEN_LEAGUE_MAPPING",
        "DAILY_DATE_COVERAGE",
        "FINISHED_RESULT_EVIDENCE_COVERAGE",
        "IDENTITY_AND_CHRONOLOGY_CONFLICTS",
    )
    assert gates["FINAL_RESULT_SEMANTICS"].outcome == "BLOCKED"
    assert gates["HISTORICAL_COVERAGE"].outcome == "UNPROVEN"
    assert gates["ELO_INITIALIZATION_BOUNDARY"].outcome == "UNPROVEN"
    assert gates["ELEVEN_LEAGUE_MAPPING"].outcome == "UNPROVEN"
    for gate_id in (
        "DAILY_DATE_COVERAGE",
        "FINISHED_RESULT_EVIDENCE_COVERAGE",
        "IDENTITY_AND_CHRONOLOGY_CONFLICTS",
    ):
        assert gates[gate_id].outcome == "NOT_REACHED"
        assert gates[gate_id].status is None

    assert value.non_reached_statuses == (
        SourceHistoryQualificationStatus.BLOCKED_REQUIRED_DATE_GAP,
        SourceHistoryQualificationStatus.BLOCKED_RESULT_EVIDENCE_GAP,
        SourceHistoryQualificationStatus.BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT,
    )


def test_smallest_missing_boundary_is_post_match_final_result_evidence() -> None:
    value = build_prospective_successor_source_history_completeness_assessment()
    assert value.smallest_missing_reviewed_boundary == SMALLEST_MISSING_REVIEWED_BOUNDARY
    assert SMALLEST_MISSING_REVIEWED_BOUNDARY == (
        "BUILD_REVIEWED_FOTMOB_POST_MATCH_FINAL_RESULT_EVIDENCE_BOUNDARY"
    )


def test_assessment_rejects_status_materialization_and_safety_mutations() -> None:
    value = build_prospective_successor_source_history_completeness_assessment()

    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessAssessmentError,
        match="differs from frozen PR82 result",
    ):
        dataclasses.replace(
            value,
            primary_status=SourceHistoryQualificationStatus.QUALIFIED_COMPLETE_REVIEWED_HISTORY,
        )

    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessAssessmentError,
        match="differs from frozen PR82 result",
    ):
        dataclasses.replace(value, history_adapter_materialized=True)

    safety = dict(value.safety)
    safety["pr80_constructor_input_authorized"] = True
    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessAssessmentError,
        match="differs from frozen PR82 result",
    ):
        dataclasses.replace(value, safety=safety)


def test_assessment_rejects_mutated_pr81_identity(monkeypatch) -> None:
    monkeypatch.setattr(assessment_module, "PR81_CANONICAL_SHA256", "0" * 64)
    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessAssessmentError,
        match="PR81 canonical protocol constants changed",
    ):
        build_prospective_successor_source_history_completeness_assessment()


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
