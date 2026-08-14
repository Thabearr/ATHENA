from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

import domain.prospective_successor_source_history_completeness_protocol as protocol_module
from domain.prospective_successor_source_history_completeness_protocol import (
    CANDIDATE_SOURCE_KEY,
    COMPLETENESS_REQUIREMENTS,
    FROZEN_MODEL_LEAGUE_CODES,
    HISTORY_ADAPTER_REQUIREMENTS,
    NEXT_REQUIRED_BOUNDARY,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    PROTOCOL_STATE,
    ProspectiveSuccessorSourceHistoryCompletenessProtocolError,
    SourceHistoryQualificationStatus,
    build_prospective_successor_source_history_completeness_protocol,
    canonical_prospective_successor_source_history_completeness_protocol_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]


def _git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    payload = f"blob {len(raw)}\0".encode("ascii") + raw
    return hashlib.sha1(payload).hexdigest()


def test_protocol_is_exact_canonical_preregistered_evidence() -> None:
    protocol = build_prospective_successor_source_history_completeness_protocol()
    exact = canonical_prospective_successor_source_history_completeness_protocol_bytes(
        protocol
    )

    assert len(exact) == PROTOCOL_SIZE == 4223
    assert hashlib.sha256(exact).hexdigest() == PROTOCOL_SHA256
    assert PROTOCOL_SHA256 == "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
    assert protocol.protocol_state == PROTOCOL_STATE
    assert protocol.protocol_state == "PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_HISTORY_QUALIFIED"
    assert protocol.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert set(protocol.safety.values()) == {False}


def test_protocol_binds_exact_pr80_and_reviewed_source_blob_ancestry() -> None:
    expected = {
        ROOT / "domain" / "prospective_successor_feature_construction_candidate.py": "9135f056d036fd0207a3daead2599ac2520274be",
        ROOT / "domain" / "source_capabilities.py": "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96",
        ROOT / "domain" / "fotmob_data_matches_capture.py": "ca2149395de868104666620173b55a880b10c729",
        ROOT / "domain" / "fotmob_data_matches_schema.py": "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f",
        ROOT / "domain" / "fotmob_reviewed_match_details_capture.py": "22e9b8c111abc38dae043b3274a4b8b2c7b90047",
    }
    assert {path.name: _git_blob_oid(path) for path in expected} == {
        path.name: oid for path, oid in expected.items()
    }

    protocol = build_prospective_successor_source_history_completeness_protocol()
    assert protocol.repository_main_sha == "271afbc2b22d39eb6e8cd13f49fd55c4f0c45ba2"
    assert protocol.pr80_constructor_blob_sha == expected[
        ROOT / "domain" / "prospective_successor_feature_construction_candidate.py"
    ]
    assert protocol.candidate_source_capability_anchor_blob_sha == expected[
        ROOT / "domain" / "source_capabilities.py"
    ]
    assert protocol.candidate_data_matches_capture_blob_sha == expected[
        ROOT / "domain" / "fotmob_data_matches_capture.py"
    ]
    assert protocol.candidate_data_matches_schema_blob_sha == expected[
        ROOT / "domain" / "fotmob_data_matches_schema.py"
    ]


def test_current_reviewed_fotmob_source_is_deliberately_not_score_or_history_qualified() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY[CANDIDATE_SOURCE_KEY]
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN

    protocol = build_prospective_successor_source_history_completeness_protocol()
    assert protocol.current_reviewed_source_facts == {
        "reliable_fixture_identity": "CONFIRMED",
        "full_time_score": "NOT_CAPTURED",
        "historical_coverage": "UNKNOWN",
        "data_matches_raw_full_time_score_candidate": "AMBIGUOUS",
        "reviewed_match_details_capture_temporal_role": "STRICTLY_PRE_KICKOFF_ONLY",
    }
    assert (
        SourceHistoryQualificationStatus.BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS.value
        in protocol.status_vocabulary
    )
    assert (
        SourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN.value
        in protocol.status_vocabulary
    )


def test_protocol_cannot_silently_substitute_legacy_fotmob_capability() -> None:
    reviewed = SOURCE_CAPABILITY_REGISTRY[CANDIDATE_SOURCE_KEY]
    legacy = SOURCE_CAPABILITY_REGISTRY["fotmob_historical"]
    assert reviewed.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert reviewed.historical_coverage is CapabilityAvailability.UNKNOWN
    assert legacy.full_time_score is CapabilityAvailability.CONFIRMED
    assert legacy.historical_coverage is CapabilityAvailability.CONFIRMED

    protocol = build_prospective_successor_source_history_completeness_protocol()
    assert protocol.candidate_source_key == CANDIDATE_SOURCE_KEY
    assert protocol.candidate_source_key != "fotmob_historical"


def test_frozen_model_universe_matches_the_real_successor_receipt() -> None:
    receipt_path = (
        ROOT
        / "artifacts"
        / "research-manifests"
        / "historical-expected-goals-successor-real-corpus-receipt-v1.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    fit = receipt["candidate"]["fit_evaluation"]
    assert {record["group_key"] for record in fit["league_breakdown"]} == set(
        FROZEN_MODEL_LEAGUE_CODES
    )
    assert len(FROZEN_MODEL_LEAGUE_CODES) == 11
    assert receipt["source_file_count"] == 66
    assert receipt["source_fixture_count"] == 21_226
    assert receipt["source_corpus_sha256"] == (
        "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
    )


def test_completeness_contract_forbids_target_team_only_elo_history() -> None:
    assert (
        "NO_SILENT_FILTERING_TO_ONLY_TARGET_TEAMS_BECAUSE_ELO_REPLAY_DEPENDS_ON_OPPONENT_STATE"
        in COMPLETENESS_REQUIREMENTS
    )
    assert (
        "PROVE_THE_EXACT_ELO_INITIALIZATION_BOUNDARY_AGAINST_FROZEN_PR69_SEMANTICS"
        in COMPLETENESS_REQUIREMENTS
    )
    assert (
        "COVER_EVERY_CALENDAR_DATE_FROM_INITIALIZATION_BOUNDARY_THROUGH_TARGET_SOURCE_LOCAL_DATE"
        in COMPLETENESS_REQUIREMENTS
    )
    assert (
        "EVERY_IN_SCOPE_FINISHED_FIXTURE_HAS_REVIEWED_FINAL_RESULT_EVIDENCE"
        in COMPLETENESS_REQUIREMENTS
    )


def test_adapter_contract_requires_observation_time_identity_and_final_score_semantics() -> None:
    assert (
        "ONE_FOTMOB_SOURCE_NAMESPACE_WITH_EXACT_SOURCE_FIXTURE_AND_TEAM_IDENTITIES"
        in HISTORY_ADAPTER_REQUIREMENTS
    )
    assert (
        "EXACT_KICKOFF_UTC_AND_EXPLICIT_SOURCE_LOCAL_TIME_BASIS"
        in HISTORY_ADAPTER_REQUIREMENTS
    )
    assert (
        "ONE_EXACT_REQUEST_TIMEZONE_AND_CCODE3_ACROSS_REQUIRED_DAILY_CAPTURES"
        in HISTORY_ADAPTER_REQUIREMENTS
    )
    assert (
        "EXPLICIT_NONNEGATIVE_FINAL_HOME_AND_AWAY_GOALS" in HISTORY_ADAPTER_REQUIREMENTS
    )
    assert (
        "FINAL_RESULT_OBSERVED_AFTER_SOURCE_FIXTURE_KICKOFF_AND_BY_TARGET_AS_OF"
        in HISTORY_ADAPTER_REQUIREMENTS
    )
    assert "NO_CROSS_SOURCE_IDENTITY_INFERENCE" in HISTORY_ADAPTER_REQUIREMENTS


def test_protocol_rejects_state_source_fact_and_safety_promotion() -> None:
    protocol = build_prospective_successor_source_history_completeness_protocol()

    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessProtocolError,
        match="differs from frozen PR81 contract",
    ):
        dataclasses.replace(protocol, protocol_state="EXECUTED")

    changed_facts = dict(protocol.current_reviewed_source_facts)
    changed_facts["full_time_score"] = "CONFIRMED"
    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessProtocolError,
        match="differs from frozen PR81 contract",
    ):
        dataclasses.replace(protocol, current_reviewed_source_facts=changed_facts)

    safety = dict(protocol.safety)
    safety["source_history_adapter_approved"] = True
    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessProtocolError,
        match="differs from frozen PR81 contract",
    ):
        dataclasses.replace(protocol, safety=safety)


def test_protocol_rejects_mutated_feature_constructor_identity(monkeypatch) -> None:
    monkeypatch.setattr(protocol_module, "CONSTRUCTION_SPEC_SHA256", "0" * 64)
    with pytest.raises(
        ProspectiveSuccessorSourceHistoryCompletenessProtocolError,
        match="PR80 constructor specification constants changed",
    ):
        build_prospective_successor_source_history_completeness_protocol()


def test_protocol_is_domain_only_and_imports_no_acquisition_or_downstream_layers() -> None:
    source = Path(protocol_module.__file__).read_text(encoding="utf-8")
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
