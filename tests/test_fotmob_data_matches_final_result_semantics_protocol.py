from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_data_matches_final_result_semantics_protocol as protocol_module
from domain.fotmob_data_matches_final_result_semantics_protocol import (
    CANDIDATE_FIELDS,
    FinalResultSemanticsStatus,
    FotMobDataMatchesFinalResultSemanticsProtocolError,
    MINIMUM_REPEAT_SEPARATION_SECONDS,
    NEXT_REQUIRED_BOUNDARY,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    PROTOCOL_STATE,
    QUALIFICATION_REQUIREMENTS,
    STATUS_VOCABULARY,
    build_fotmob_data_matches_final_result_semantics_protocol,
    canonical_fotmob_data_matches_final_result_semantics_protocol_bytes,
)
from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)


ROOT = Path(__file__).resolve().parents[1]


def _git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def test_protocol_is_exact_result_free_canonical_contract() -> None:
    value = build_fotmob_data_matches_final_result_semantics_protocol()
    exact = canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(value)

    assert value.protocol_state == PROTOCOL_STATE
    assert PROTOCOL_STATE == (
        "PRE_REGISTERED_NOT_EXECUTED_NO_FINAL_RESULT_SEMANTICS_QUALIFIED"
    )
    assert len(exact) == PROTOCOL_SIZE == 3995
    assert hashlib.sha256(exact).hexdigest() == PROTOCOL_SHA256
    assert PROTOCOL_SHA256 == (
        "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
    )
    assert set(value.safety.values()) == {False}


def test_protocol_binds_exact_pr82_and_reviewed_data_matches_blobs() -> None:
    expected = {
        ROOT
        / "domain"
        / "prospective_successor_source_history_completeness_assessment.py": (
            "6a46f36d7070e6e62a1587906c2e642fbcfea052"
        ),
        ROOT / "domain" / "fotmob_data_matches_capture.py": (
            "ca2149395de868104666620173b55a880b10c729"
        ),
        ROOT / "domain" / "fotmob_data_matches_schema.py": (
            "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
        ),
        ROOT / "domain" / "source_capabilities.py": (
            "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
        ),
    }

    assert {_git_blob_oid(path) for path in expected} == set(expected.values())
    value = build_fotmob_data_matches_final_result_semantics_protocol()
    assert value.repository_main_sha == "a82aa81412f45a04720687c930f36d16dbe39f67"
    assert value.pr82_assessment_blob_sha == expected[
        ROOT
        / "domain"
        / "prospective_successor_source_history_completeness_assessment.py"
    ]
    assert value.data_matches_capture_blob_sha == expected[
        ROOT / "domain" / "fotmob_data_matches_capture.py"
    ]
    assert value.data_matches_schema_blob_sha == expected[
        ROOT / "domain" / "fotmob_data_matches_schema.py"
    ]
    assert value.source_capabilities_blob_sha == expected[
        ROOT / "domain" / "source_capabilities.py"
    ]


def test_candidate_fields_are_exact_and_do_not_invent_scorestr() -> None:
    assert CANDIDATE_FIELDS == (
        "match.id",
        "match.leagueId",
        "match.home.id",
        "match.home.score",
        "match.away.id",
        "match.away.score",
        "match.status.utcTime",
        "match.status.started",
        "match.status.cancelled",
        "match.status.finished",
    )
    assert all("scoreStr" not in field for field in CANDIDATE_FIELDS)


def test_current_schema_really_has_score_and_terminal_status_but_keeps_ft_ambiguous() -> None:
    source = (ROOT / "domain" / "fotmob_data_matches_schema.py").read_text(
        encoding="utf-8"
    )
    assert 'TEAM_KEYS = frozenset({"id", "longName", "name", "score"})' in source
    assert '"cancelled", "finished", "halfs", "periodLength", "started", "utcTime"' in source
    assert '"full_time_score_candidate": (' in source
    assert "StructuralCapability.AMBIGUOUS" in source
    assert '_exact_int(team["score"]' in source
    assert '_exact_bool(status[key]' in source


def test_current_capability_must_remain_not_captured_before_execution() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN


def test_terminal_score_stability_rules_are_pre_registered() -> None:
    value = build_fotmob_data_matches_final_result_semantics_protocol()

    assert value.terminal_state_rule == (
        "STATUS_FINISHED_TRUE_AND_CANCELLED_FALSE_AND_STARTED_TRUE"
    )
    assert value.score_rule == (
        "HOME_AND_AWAY_SCORE_MUST_BE_EXACT_NONNEGATIVE_INTEGERS"
    )
    assert value.minimum_repeat_separation_seconds == MINIMUM_REPEAT_SEPARATION_SECONDS
    assert MINIMUM_REPEAT_SEPARATION_SECONDS == 300
    assert value.observation_rule == (
        "AT_LEAST_TWO_DISTINCT_POST_KICKOFF_FINISHED_CAPTURES_WITH_DISTINCT_CAPTURE_LINEAGE"
    )
    assert value.stability_rule == (
        "SOURCE_MATCH_TEAM_LEAGUE_KICKOFF_AND_SCORE_PAIR_MUST_BE_IDENTICAL_ACROSS_REQUIRED_FINISHED_CAPTURES"
    )
    assert (
        "REQUIRE_AT_LEAST_TWO_DISTINCT_CAPTURE_MANIFESTS_AND_RAW_SHA256_VALUES"
        in QUALIFICATION_REQUIREMENTS
    )
    assert (
        "REQUIRE_IDENTICAL_HOME_AWAY_SCORE_PAIR_ACROSS_REQUIRED_FINISHED_OBSERVATIONS"
        in QUALIFICATION_REQUIREMENTS
    )


def test_semantic_scope_does_not_overclaim_regulation_time_or_settlement() -> None:
    value = build_fotmob_data_matches_final_result_semantics_protocol()
    assert value.semantic_scope_rule == (
        "QUALIFICATION_MEANS_SOURCE_REPORTED_FINISHED_SCORE_ONLY_NOT_REGULATION_TIME_EXTRA_TIME_PENALTIES_OR_SETTLEMENT_SEMANTICS_BEYOND_THE_SOURCE_FIELDS"
    )
    assert value.status_id_rule == (
        "STATUS_ID_IS_RECORDED_AS_EVIDENCE_BUT_NEVER_USED_AS_THE_SOLE_FINALITY_SIGNAL"
    )
    assert value.reason_field_rule == (
        "ANY_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW_AND_CANNOT_AUTO_QUALIFY"
    )
    assert value.legacy_exclusion_rule == (
        "LEGACY_FOTMOB_BYPASS_AND_HISTORICAL_SCRAPER_OUTPUT_CANNOT_PROVE_THIS_REVIEWED_DATA_MATCHES_SEMANTIC_BOUNDARY"
    )


def test_status_vocabulary_is_exact_and_has_only_one_positive_status() -> None:
    assert STATUS_VOCABULARY == tuple(item.value for item in FinalResultSemanticsStatus)
    positives = [status for status in STATUS_VOCABULARY if status.startswith("QUALIFIED_")]
    assert positives == ["QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS"]
    assert set(STATUS_VOCABULARY) == {
        "QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS",
        "BLOCKED_NOT_FINISHED",
        "BLOCKED_CANCELLED_OR_CONFLICTING_STATUS",
        "BLOCKED_SCORE_INVALID",
        "BLOCKED_INSUFFICIENT_POST_FINISH_OBSERVATIONS",
        "BLOCKED_POST_FINISH_SCORE_INSTABILITY",
        "BLOCKED_FIXTURE_IDENTITY_DRIFT",
        "BLOCKED_CAPTURE_LINEAGE_OR_TIME",
        "BLOCKED_STATUS_REASON_REQUIRES_REVIEW",
    }


def test_next_boundary_is_execution_not_source_capability_promotion() -> None:
    value = build_fotmob_data_matches_final_result_semantics_protocol()
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION"
    )
    assert value.safety["final_result_semantics_execution_authorized"] is False
    assert value.safety["final_result_semantics_qualified"] is False
    assert value.safety["source_capability_update_authorized"] is False


def test_protocol_rejects_positive_or_weakened_mutations() -> None:
    value = build_fotmob_data_matches_final_result_semantics_protocol()

    safety = dict(value.safety)
    safety["final_result_semantics_qualified"] = True
    with pytest.raises(
        FotMobDataMatchesFinalResultSemanticsProtocolError,
        match="differs from frozen PR83 contract",
    ):
        dataclasses.replace(value, safety=safety)

    with pytest.raises(
        FotMobDataMatchesFinalResultSemanticsProtocolError,
        match="differs from frozen PR83 contract",
    ):
        dataclasses.replace(value, minimum_repeat_separation_seconds=0)

    with pytest.raises(
        FotMobDataMatchesFinalResultSemanticsProtocolError,
        match="differs from frozen PR83 contract",
    ):
        dataclasses.replace(
            value,
            candidate_fields=tuple(
                field for field in value.candidate_fields if field != "match.status.finished"
            ),
        )


def test_protocol_rejects_mutated_pr82_identity(monkeypatch) -> None:
    monkeypatch.setattr(protocol_module, "PR82_CANONICAL_SHA256", "0" * 64)
    with pytest.raises(
        FotMobDataMatchesFinalResultSemanticsProtocolError,
        match="PR82 canonical assessment constants changed",
    ):
        build_fotmob_data_matches_final_result_semantics_protocol()


def test_protocol_is_domain_only_and_cannot_acquire_or_run_downstream() -> None:
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
