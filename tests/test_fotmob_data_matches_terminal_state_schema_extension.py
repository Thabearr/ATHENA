from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_data_matches_schema as pr39_schema
import domain.fotmob_data_matches_terminal_state_schema_extension as implementation
import domain.fotmob_data_matches_terminal_state_schema_extension_protocol as protocol
from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
    verify_data_matches_capture_directory,
)
from domain.fotmob_data_matches_post_finish_capture_pair_evidence import (
    FIRST_CAPTURE_ID,
    FIRST_MANIFEST_SHA256,
    FIRST_MATCH_COUNT,
    FIRST_RAW_SHA256,
    SECOND_CAPTURE_ID,
    SECOND_MANIFEST_SHA256,
    SECOND_MATCH_COUNT,
    SECOND_RAW_SHA256,
)
from domain.fotmob_data_matches_terminal_state_schema_extension import (
    NEXT_REQUIRED_BOUNDARY,
    PR39_SCHEMA_BLOB_SHA,
    PR86_PROTOCOL_BLOB_SHA,
    FotMobDataMatchesTerminalStateSchemaExtensionError,
    TerminalStateSchemaExtensionStatus,
    assess_fotmob_data_matches_terminal_state_schema_extension,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence" / "fotmob_data_matches" / "pr83_post_finish_pair"
DATE_ROOT = EVIDENCE_ROOT / "20260814"


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _load_capture(capture_id: str):
    capture_dir = DATE_ROOT / capture_id
    manifest = verify_data_matches_capture_directory(
        capture_dir,
        allowed_root=EVIDENCE_ROOT,
        require_network_acquisition_performed=True,
    )
    raw = (capture_dir / "response.json").read_bytes()
    return raw, manifest


def _mutated_manifest(raw: bytes, original_manifest):
    response = CapturedFotMobDataMatchesResponse(
        status=original_manifest.status,
        content_type=original_manifest.content_type,
        content_length=len(raw),
        body=raw,
        observed_at=original_manifest.observed_at,
        network_acquisition_performed=original_manifest.network_acquisition_performed,
    )
    return build_data_matches_capture_manifest(
        response,
        request_date=original_manifest.request_date,
        timezone=original_manifest.timezone,
        ccode3=original_manifest.ccode3,
    )


def _mutate_raw(raw: bytes, mutator):
    payload = json.loads(raw)
    mutator(payload)
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _first_match(payload):
    for league in payload["leagues"]:
        if league["matches"]:
            return league["matches"][0]
    raise AssertionError("expected at least one match")


def test_exact_pr86_and_pr39_ancestry_is_frozen() -> None:
    assert _git_blob_sha(
        ROOT / "domain" / "fotmob_data_matches_terminal_state_schema_extension_protocol.py"
    ) == PR86_PROTOCOL_BLOB_SHA == "71b2f1a8add05929835d469df94396375a115391"
    assert _git_blob_sha(
        ROOT / "domain" / "fotmob_data_matches_schema.py"
    ) == PR39_SCHEMA_BLOB_SHA == "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"

    value = protocol.build_fotmob_data_matches_terminal_state_schema_extension_protocol()
    exact = protocol.canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(
        value
    )
    assert hashlib.sha256(exact).hexdigest() == protocol.PROTOCOL_SHA256
    assert len(exact) == protocol.PROTOCOL_SIZE == 5639


@pytest.mark.parametrize(
    ("capture_id", "expected_raw_sha", "expected_manifest_sha", "expected_match_count"),
    (
        (FIRST_CAPTURE_ID, FIRST_RAW_SHA256, FIRST_MANIFEST_SHA256, FIRST_MATCH_COUNT),
        (SECOND_CAPTURE_ID, SECOND_RAW_SHA256, SECOND_MANIFEST_SHA256, SECOND_MATCH_COUNT),
    ),
)
def test_pr85_terminal_captures_qualify_structural_extension(
    capture_id: str,
    expected_raw_sha: str,
    expected_manifest_sha: str,
    expected_match_count: int,
) -> None:
    raw, manifest = _load_capture(capture_id)
    result = assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)

    assert (
        result.status
        is TerminalStateSchemaExtensionStatus.QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
    )
    assert result.source_raw_sha256 == expected_raw_sha
    assert result.source_capture_manifest_sha256 == expected_manifest_sha
    assert result.match_count == expected_match_count == 183
    assert sum(result.team_extension_occurrences.values()) > 0
    assert sum(result.status_extension_occurrences.values()) > 0
    assert sum(result.halfs_extension_occurrences.values()) > 0
    assert result.reason_semantics_qualified is False
    assert result.final_result_semantics_qualified is False
    assert result.next_required_boundary == (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS"
    )
    assert set(result.safety.values()) == {False}


@pytest.mark.parametrize("capture_id", (FIRST_CAPTURE_ID, SECOND_CAPTURE_ID))
def test_frozen_pr39_still_rejects_terminal_snapshot_without_extension(
    capture_id: str,
) -> None:
    raw, manifest = _load_capture(capture_id)
    with pytest.raises(pr39_schema.FotMobDataMatchesSchemaError):
        pr39_schema.assess_fotmob_data_matches_schema(raw, manifest)


def test_unregistered_extra_key_fails_closed() -> None:
    raw, manifest = _load_capture(FIRST_CAPTURE_ID)

    def mutate(payload):
        _first_match(payload)["home"]["invented"] = 1

    changed = _mutate_raw(raw, mutate)
    changed_manifest = _mutated_manifest(changed, manifest)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(changed, changed_manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET
    )


@pytest.mark.parametrize("bad_value", (None, True, -1, 1.5, "1"))
def test_extension_integer_type_and_nullability_fail_closed(bad_value) -> None:
    raw, manifest = _load_capture(FIRST_CAPTURE_ID)

    def mutate(payload):
        _first_match(payload)["home"]["penScore"] = bad_value

    changed = _mutate_raw(raw, mutate)
    changed_manifest = _mutated_manifest(changed, manifest)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(changed, changed_manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH
    )


@pytest.mark.parametrize("bad_value", (None, 0, 1, "false"))
def test_extension_bool_type_and_nullability_fail_closed(bad_value) -> None:
    raw, manifest = _load_capture(FIRST_CAPTURE_ID)

    def mutate(payload):
        _first_match(payload)["status"]["awarded"] = bad_value

    changed = _mutate_raw(raw, mutate)
    changed_manifest = _mutated_manifest(changed, manifest)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(changed, changed_manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH
    )


def test_live_time_shape_fails_closed_for_missing_or_extra_keys() -> None:
    raw, manifest = _load_capture(FIRST_CAPTURE_ID)

    def add_missing(payload):
        _first_match(payload)["status"]["liveTime"] = {
            "addedTime": 0,
            "basePeriod": 90,
            "long": "",
            "longKey": "",
            "maxTime": 90,
            "short": "",
        }

    changed = _mutate_raw(raw, add_missing)
    changed_manifest = _mutated_manifest(changed, manifest)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(changed, changed_manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_LIVE_TIME_SHAPE_MISMATCH
    )

    def add_extra(payload):
        _first_match(payload)["status"]["liveTime"] = {
            "addedTime": 0,
            "basePeriod": 90,
            "long": "",
            "longKey": "",
            "maxTime": 90,
            "short": "",
            "shortKey": "",
            "invented": 0,
        }

    changed = _mutate_raw(raw, add_extra)
    changed_manifest = _mutated_manifest(changed, manifest)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(changed, changed_manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_LIVE_TIME_SHAPE_MISMATCH
    )


def test_pr39_base_invariant_failure_is_not_hidden_by_extension() -> None:
    raw, manifest = _load_capture(FIRST_CAPTURE_ID)

    def mutate(payload):
        _first_match(payload)["timeTS"] += 1

    changed = _mutate_raw(raw, mutate)
    changed_manifest = _mutated_manifest(changed, manifest)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(changed, changed_manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT
    )


def test_structural_success_cannot_promote_reason_or_final_result_semantics() -> None:
    raw, manifest = _load_capture(FIRST_CAPTURE_ID)
    result = assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError):
        dataclasses.replace(result, reason_semantics_qualified=True)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError):
        dataclasses.replace(result, final_result_semantics_qualified=True)

    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN


def test_next_boundary_is_exact_and_status_vocabulary_is_frozen() -> None:
    assert NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS"
    )
    assert tuple(item.value for item in TerminalStateSchemaExtensionStatus) == (
        "QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION",
        "BLOCKED_BASE_PR39_CONTRACT_DRIFT",
        "BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT",
        "BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET",
        "BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH",
        "BLOCKED_LIVE_TIME_SHAPE_MISMATCH",
    )


def test_implementation_cannot_acquire_network_or_run_downstream() -> None:
    source = Path(implementation.__file__).read_text(encoding="utf-8")
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
