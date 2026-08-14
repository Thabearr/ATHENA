from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_data_matches_post_finish_capture_pair_evidence as pr85
import domain.fotmob_data_matches_schema as pr39_schema
import domain.fotmob_data_matches_terminal_state_schema_extension_protocol as protocol_module
from domain.fotmob_data_matches_terminal_state_schema_extension_protocol import (
    EXTENSION_HALFS_OPTIONAL_KEYS,
    EXTENSION_STATUS_OPTIONAL_KEYS,
    EXTENSION_TEAM_OPTIONAL_KEYS,
    LIVE_TIME_REQUIRED_KEYS,
    NEXT_REQUIRED_BOUNDARY,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    PROTOCOL_STATE,
    STATUS_VOCABULARY,
    TYPE_RULES,
    FotMobDataMatchesTerminalStateSchemaExtensionProtocolError,
    build_fotmob_data_matches_terminal_state_schema_extension_protocol,
    canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes,
    revalidate_fotmob_data_matches_terminal_state_schema_extension_protocol,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def test_exact_canonical_pr86_protocol() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()
    exact = canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(
        value
    )

    assert PROTOCOL_STATE == (
        "PRE_REGISTERED_NOT_IMPLEMENTED_NO_TERMINAL_STATE_SCHEMA_EXTENSION_QUALIFIED"
    )
    assert len(exact) == PROTOCOL_SIZE == 5639
    assert hashlib.sha256(exact).hexdigest() == PROTOCOL_SHA256
    assert PROTOCOL_SHA256 == (
        "6e2e0936023531ad9c0a87cde68eb0cf4c8753b27aaa8c001bcbd3fcb5daa225"
    )
    assert set(value.safety.values()) == {False}


def test_exact_pr85_and_pr39_file_ancestry_is_frozen() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()

    assert _git_blob_sha(
        ROOT / "domain" / "fotmob_data_matches_post_finish_capture_pair_evidence.py"
    ) == value.pr85_evidence_blob_sha == "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
    assert _git_blob_sha(
        ROOT / "domain" / "fotmob_data_matches_schema.py"
    ) == value.pr39_schema_blob_sha == "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"

    evidence = pr85.build_fotmob_data_matches_post_finish_capture_pair_evidence()
    evidence_bytes = pr85.canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(
        evidence
    )
    assert len(evidence_bytes) == value.pr85_evidence_size == 3921
    assert hashlib.sha256(evidence_bytes).hexdigest() == value.pr85_evidence_sha256
    assert value.repository_main_sha == "4dc04a8856a01d5756bf992887df2553928c48a4"


def test_pr39_base_contract_remains_frozen_and_extension_is_additive() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()

    assert tuple(sorted(pr39_schema.TEAM_KEYS)) == value.base_team_keys
    assert tuple(sorted(pr39_schema.STATUS_REQUIRED_KEYS)) == value.base_status_required_keys
    assert tuple(sorted(pr39_schema.STATUS_OPTIONAL_KEYS)) == value.base_status_optional_keys
    assert tuple(sorted(pr39_schema.HALFS_KEYS)) == value.base_halfs_keys

    assert set(value.extension_team_optional_keys).isdisjoint(value.base_team_keys)
    assert set(value.extension_status_optional_keys).isdisjoint(
        set(value.base_status_required_keys) | set(value.base_status_optional_keys)
    )
    assert set(value.extension_halfs_optional_keys).isdisjoint(value.base_halfs_keys)
    assert value.pr39_immutability_rule == (
        "PR39_V1_REMAINS_FROZEN_THE_EXTENSION_MUST_BE_A_SEPARATE_ADDITIVE_REVIEWED_LAYER"
    )


def test_extension_key_sets_exactly_match_pr85_observed_terminal_drift() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()

    assert EXTENSION_TEAM_OPTIONAL_KEYS == ("penScore", "redCards")
    assert EXTENSION_STATUS_OPTIONAL_KEYS == (
        "awarded",
        "liveTime",
        "numberOfAwayRedCards",
        "numberOfHomeRedCards",
        "ongoing",
        "scoreStr",
    )
    assert EXTENSION_HALFS_OPTIONAL_KEYS == ("secondHalfStarted",)
    assert LIVE_TIME_REQUIRED_KEYS == (
        "addedTime",
        "basePeriod",
        "long",
        "longKey",
        "maxTime",
        "short",
        "shortKey",
    )

    assert tuple(pr85.PR39_EXTRA_TEAM_KEYS) == value.extension_team_optional_keys
    assert tuple(pr85.PR39_EXTRA_STATUS_KEYS) == value.extension_status_optional_keys
    assert tuple(pr85.PR39_EXTRA_HALFS_KEYS) == value.extension_halfs_optional_keys
    assert pr85.PRIMARY_BLOCKER == (
        "PR39_STRICT_SCHEMA_REVALIDATION_FAILED_TERMINAL_SNAPSHOT_EXTRA_KEYS"
    )


def test_type_and_nullability_domains_are_frozen_without_semantic_inference() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()

    assert TYPE_RULES == value.type_rules
    assert len(TYPE_RULES) == 16
    assert "team.penScore=OPTIONAL_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN" in TYPE_RULES
    assert "status.awarded=OPTIONAL_EXACT_BOOL_NULL_FORBIDDEN" in TYPE_RULES
    assert (
        "status.liveTime=OPTIONAL_EXACT_OBJECT_NULL_FORBIDDEN_EXACT_REGISTERED_KEYS"
        in TYPE_RULES
    )
    assert (
        "status.liveTime.shortKey=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED"
        in TYPE_RULES
    )
    assert (
        "status.halfs.secondHalfStarted=OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED"
        in TYPE_RULES
    )

    assert value.optionality_rule == (
        "ALL_EXTENSION_KEYS_ARE_OPTIONAL_AND_MUST_NOT_BECOME_PR39_BASE_REQUIRED_KEYS"
    )
    assert value.unknown_key_rule == (
        "ANY_KEY_OUTSIDE_PR39_BASE_PLUS_PRE_REGISTERED_EXTENSION_SETS_FAILS_CLOSED"
    )
    assert "NO_PARSING_OR_MEANING_INFERENCE" in value.string_semantics_rule
    assert "NO_FOOTBALL_MEANING_INFERENCE" in value.integer_semantics_rule
    assert "NO_FOOTBALL_MEANING_INFERENCE" in value.boolean_semantics_rule


def test_protocol_preserves_independent_status_reason_gate_and_no_semantics() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()

    assert pr85.SECONDARY_BLOCKER == "PR83_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW"
    assert value.reason_gate_rule == (
        "PR83_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW_REMAINS_UNCHANGED_AND_INDEPENDENT"
    )
    assert value.semantic_exclusion_rule == (
        "NO_FINAL_RESULT_REGULATION_TIME_EXTRA_TIME_PENALTIES_RED_CARD_AWARD_LIVE_TIME_OR_SETTLEMENT_SEMANTICS_ARE_QUALIFIED_BY_THIS_PROTOCOL"
    )
    assert value.safety["final_result_semantics_qualified"] is False
    assert value.safety["terminal_schema_extension_qualified"] is False
    assert value.safety["pr39_schema_mutation_authorized"] is False


def test_status_vocabulary_and_next_boundary_are_exact() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()

    assert STATUS_VOCABULARY == (
        "QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION",
        "BLOCKED_BASE_PR39_CONTRACT_DRIFT",
        "BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT",
        "BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET",
        "BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH",
        "BLOCKED_LIVE_TIME_SHAPE_MISMATCH",
    )
    assert value.status_vocabulary == STATUS_VOCABULARY
    assert NEXT_REQUIRED_BOUNDARY == (
        "IMPLEMENT_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION"
    )
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY


def test_source_capabilities_and_all_downstream_authority_remain_false() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]

    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    assert all(flag is False for flag in value.safety.values())


def test_mutation_and_positive_authority_fail_closed() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionProtocolError):
        dataclasses.replace(
            value,
            extension_team_optional_keys=("penScore", "redCards", "invented"),
        )
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionProtocolError):
        dataclasses.replace(value, protocol_state="changed")
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionProtocolError):
        dataclasses.replace(
            value,
            next_required_boundary="EXECUTE_FINAL_RESULT_SEMANTICS",
        )

    safety = dict(value.safety)
    safety["terminal_schema_extension_qualified"] = True
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionProtocolError):
        dataclasses.replace(value, safety=safety)


def test_revalidator_rejects_changed_protocol() -> None:
    value = build_fotmob_data_matches_terminal_state_schema_extension_protocol()
    assert (
        revalidate_fotmob_data_matches_terminal_state_schema_extension_protocol(value)
        == value
    )
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionProtocolError):
        dataclasses.replace(value, unknown_key_rule="changed")


def test_protocol_module_cannot_acquire_network_or_run_downstream() -> None:
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
