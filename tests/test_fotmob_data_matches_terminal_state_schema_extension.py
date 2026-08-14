from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

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
    FIRST_RAW_SHA256,
    SECOND_CAPTURE_ID,
    SECOND_MANIFEST_SHA256,
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
SYNTHETIC_DATE = "20260815"
SYNTHETIC_KICKOFF = "2026-08-15T12:00:00.000Z"
SYNTHETIC_KICKOFF_MS = 1786795200000
SYNTHETIC_OBSERVED = datetime.datetime(
    2026, 8, 15, 13, 0, 0, tzinfo=datetime.timezone.utc
)


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


def _manifest_for_raw(
    raw: bytes,
    *,
    observed_at: datetime.datetime = SYNTHETIC_OBSERVED,
    network: bool = False,
):
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=observed_at,
        network_acquisition_performed=network,
    )
    return build_data_matches_capture_manifest(
        response,
        request_date=SYNTHETIC_DATE,
        timezone="UTC",
        ccode3="NGA",
    )


def _raw_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _synthetic_payload() -> dict[str, Any]:
    return {
        "date": SYNTHETIC_DATE,
        "leagues": [
            {
                "ccode": "ENG",
                "id": 42,
                "internalRank": 1,
                "matches": [
                    {
                        "away": {
                            "id": 12,
                            "longName": "Away",
                            "name": "Away",
                            "penScore": 0,
                            "redCards": 0,
                            "score": 1,
                        },
                        "eliminatedTeamId": None,
                        "home": {
                            "id": 11,
                            "longName": "Home",
                            "name": "Home",
                            "penScore": 0,
                            "redCards": 1,
                            "score": 2,
                        },
                        "id": 1001,
                        "leagueId": 42,
                        "status": {
                            "awarded": False,
                            "cancelled": False,
                            "finished": True,
                            "halfs": {
                                "firstHalfStarted": "2026-08-15T12:00:00Z",
                                "secondHalfStarted": "2026-08-15T13:00:00Z",
                            },
                            "liveTime": {
                                "addedTime": 0,
                                "basePeriod": 90,
                                "long": "",
                                "longKey": "",
                                "maxTime": 90,
                                "short": "",
                                "shortKey": "",
                            },
                            "numberOfAwayRedCards": 0,
                            "numberOfHomeRedCards": 1,
                            "ongoing": False,
                            "periodLength": 45,
                            "reason": {
                                "long": "Full-Time",
                                "longKey": "finished",
                                "short": "FT",
                                "shortKey": "fulltime_short",
                            },
                            "scoreStr": "2 - 1",
                            "started": True,
                            "utcTime": SYNTHETIC_KICKOFF,
                        },
                        "statusId": 6,
                        "time": "15.08.2026 12:00",
                        "timeTS": SYNTHETIC_KICKOFF_MS,
                        "tournamentStage": "",
                    }
                ],
                "name": "Example competition",
                "primaryId": 42,
                "simpleLeague": False,
            }
        ],
    }


def _synthetic_raw_and_manifest():
    raw = _raw_bytes(_synthetic_payload())
    return raw, _manifest_for_raw(raw)


def _first_match(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["leagues"][0]["matches"][0]


def _non_null_eliminated_team_id_count(raw: bytes) -> int:
    payload = json.loads(raw)
    return sum(
        1
        for league in payload["leagues"]
        for match in league["matches"]
        if match["eliminatedTeamId"] is not None
    )


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
    ("capture_id", "expected_raw_sha", "expected_manifest_sha"),
    (
        (FIRST_CAPTURE_ID, FIRST_RAW_SHA256, FIRST_MANIFEST_SHA256),
        (SECOND_CAPTURE_ID, SECOND_RAW_SHA256, SECOND_MANIFEST_SHA256),
    ),
)
def test_pr85_terminal_captures_fail_closed_on_non_null_eliminated_team_id(
    capture_id: str,
    expected_raw_sha: str,
    expected_manifest_sha: str,
) -> None:
    raw, manifest = _load_capture(capture_id)
    assert manifest.raw_sha256 == expected_raw_sha
    from domain.fotmob_data_matches_capture import sha256_data_matches_capture_manifest

    assert sha256_data_matches_capture_manifest(manifest) == expected_manifest_sha
    assert _non_null_eliminated_team_id_count(raw) > 0

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT
    )
    assert "non-null eliminatedTeamId" in str(exc_info.value)


def test_synthetic_pr39_compatible_terminal_payload_qualifies_extension_only() -> None:
    raw, manifest = _synthetic_raw_and_manifest()
    result = assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)

    assert (
        result.status
        is TerminalStateSchemaExtensionStatus.QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION
    )
    assert result.match_count == 1
    assert dict(result.team_extension_occurrences) == {"penScore": 2, "redCards": 2}
    assert dict(result.status_extension_occurrences) == {
        "awarded": 1,
        "liveTime": 1,
        "numberOfAwayRedCards": 1,
        "numberOfHomeRedCards": 1,
        "ongoing": 1,
        "scoreStr": 1,
    }
    assert dict(result.halfs_extension_occurrences) == {"secondHalfStarted": 1}
    assert result.live_time_occurrence_count == 1
    assert result.reason_semantics_qualified is False
    assert result.final_result_semantics_qualified is False
    assert result.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert set(result.safety.values()) == {False}


@pytest.mark.parametrize("capture_id", (FIRST_CAPTURE_ID, SECOND_CAPTURE_ID))
def test_frozen_pr39_still_rejects_terminal_snapshot_without_extension(
    capture_id: str,
) -> None:
    raw, manifest = _load_capture(capture_id)
    with pytest.raises(pr39_schema.FotMobDataMatchesSchemaError):
        pr39_schema.assess_fotmob_data_matches_schema(raw, manifest)


def test_unregistered_extra_key_fails_closed() -> None:
    payload = _synthetic_payload()
    _first_match(payload)["home"]["invented"] = 1
    raw = _raw_bytes(payload)
    manifest = _manifest_for_raw(raw)

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET
    )


@pytest.mark.parametrize("bad_value", (None, True, -1, 1.5, "1"))
def test_extension_integer_type_and_nullability_fail_closed(bad_value: Any) -> None:
    payload = _synthetic_payload()
    _first_match(payload)["home"]["penScore"] = bad_value
    raw = _raw_bytes(payload)
    manifest = _manifest_for_raw(raw)

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH
    )


@pytest.mark.parametrize("bad_value", (None, 0, 1, "false"))
def test_extension_bool_type_and_nullability_fail_closed(bad_value: Any) -> None:
    payload = _synthetic_payload()
    _first_match(payload)["status"]["awarded"] = bad_value
    raw = _raw_bytes(payload)
    manifest = _manifest_for_raw(raw)

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH
    )


def test_live_time_shape_fails_closed_for_missing_or_extra_keys() -> None:
    payload = _synthetic_payload()
    del _first_match(payload)["status"]["liveTime"]["shortKey"]
    raw = _raw_bytes(payload)
    manifest = _manifest_for_raw(raw)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_LIVE_TIME_SHAPE_MISMATCH
    )

    payload = _synthetic_payload()
    _first_match(payload)["status"]["liveTime"]["invented"] = 0
    raw = _raw_bytes(payload)
    manifest = _manifest_for_raw(raw)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_LIVE_TIME_SHAPE_MISMATCH
    )


def test_pr39_base_invariant_failure_is_not_hidden_by_extension() -> None:
    payload = _synthetic_payload()
    _first_match(payload)["timeTS"] += 1
    raw = _raw_bytes(payload)
    manifest = _manifest_for_raw(raw)

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT
    )


def test_structural_success_cannot_promote_reason_or_final_result_semantics() -> None:
    raw, manifest = _synthetic_raw_and_manifest()
    result = assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)

    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError):
        dataclasses.replace(result, reason_semantics_qualified=True)
    with pytest.raises(FotMobDataMatchesTerminalStateSchemaExtensionError):
        dataclasses.replace(result, final_result_semantics_qualified=True)

    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN


def test_next_boundary_and_status_vocabulary_are_exact() -> None:
    assert NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION"
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
