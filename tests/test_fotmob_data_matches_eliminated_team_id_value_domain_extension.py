from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import domain.fotmob_data_matches_terminal_state_schema_extension as pr87
from domain.fotmob_data_matches_capture import (
    MAX_RESPONSE_BYTES,
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
    sha256_data_matches_capture_manifest,
    verify_data_matches_capture_directory,
)
from domain.fotmob_data_matches_eliminated_team_id_value_domain_extension import (
    NEXT_REQUIRED_BOUNDARY,
    PR39_SCHEMA_BLOB_SHA,
    PR85_EVIDENCE_BLOB_SHA,
    PR87_IMPLEMENTATION_BLOB_SHA,
    PR88_PROTOCOL_BLOB_SHA,
    PR88_PROTOCOL_SHA256,
    PR88_PROTOCOL_SIZE,
    REPOSITORY_MAIN_SHA,
    EliminatedTeamIdValueDomainStatus,
    FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError,
    assess_fotmob_data_matches_eliminated_team_id_value_domain,
    canonical_fotmob_data_matches_eliminated_team_id_value_domain_assessment_bytes,
    sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment,
)
from domain.fotmob_data_matches_eliminated_team_id_value_domain_protocol import (
    FIRST_CAPTURE_ID,
    FIRST_MANIFEST_SHA256,
    FIRST_RAW_SHA256,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    SECOND_CAPTURE_ID,
    SECOND_MANIFEST_SHA256,
    SECOND_RAW_SHA256,
    build_fotmob_data_matches_eliminated_team_id_value_domain_protocol,
    canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes,
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

SAFETY_KEYS = {
    "network_acquisition_authorized",
    "eliminated_team_id_value_domain_implementation_authorized",
    "eliminated_team_id_value_domain_qualified",
    "eliminated_team_id_semantics_qualified",
    "pr39_schema_mutation_authorized",
    "pr87_implementation_mutation_authorized",
    "status_reason_semantics_qualified",
    "final_result_semantics_qualified",
    "source_capability_update_authorized",
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


def _load_capture(capture_id: str):
    capture_dir = DATE_ROOT / capture_id
    manifest = verify_data_matches_capture_directory(
        capture_dir,
        allowed_root=EVIDENCE_ROOT,
        require_network_acquisition_performed=True,
    )
    return (capture_dir / "response.json").read_bytes(), manifest


def _raw_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest_for_raw(raw: bytes):
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=SYNTHETIC_OBSERVED,
        network_acquisition_performed=False,
    )
    return build_data_matches_capture_manifest(
        response,
        request_date=SYNTHETIC_DATE,
        timezone="UTC",
        ccode3="NGA",
    )


def _synthetic_payload(eliminated_team_id: Any = None) -> dict[str, Any]:
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
                        "eliminatedTeamId": eliminated_team_id,
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


def _assess_synthetic(eliminated_team_id: Any = None):
    raw = _raw_bytes(_synthetic_payload(eliminated_team_id))
    return assess_fotmob_data_matches_eliminated_team_id_value_domain(
        raw, _manifest_for_raw(raw)
    )


def test_exact_merged_main_and_frozen_blob_ancestry() -> None:
    assert REPOSITORY_MAIN_SHA == "df6b782e0e1b36c46089333a893a12f44e40fa07"
    assert _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_schema.py") == PR39_SCHEMA_BLOB_SHA
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_post_finish_capture_pair_evidence.py")
        == PR85_EVIDENCE_BLOB_SHA
    )
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_terminal_state_schema_extension.py")
        == PR87_IMPLEMENTATION_BLOB_SHA
    )
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_eliminated_team_id_value_domain_protocol.py")
        == PR88_PROTOCOL_BLOB_SHA
    )


def test_exact_pr88_protocol_revalidates() -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    exact = canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes(value)
    assert PR88_PROTOCOL_SHA256 == PROTOCOL_SHA256
    assert PR88_PROTOCOL_SIZE == PROTOCOL_SIZE == 4276
    assert hashlib.sha256(exact).hexdigest() == PR88_PROTOCOL_SHA256
    assert len(exact) == PR88_PROTOCOL_SIZE


@pytest.mark.parametrize(
    ("capture_id", "raw_sha", "manifest_sha"),
    (
        (FIRST_CAPTURE_ID, FIRST_RAW_SHA256, FIRST_MANIFEST_SHA256),
        (SECOND_CAPTURE_ID, SECOND_RAW_SHA256, SECOND_MANIFEST_SHA256),
    ),
)
def test_exact_pr85_captures_now_qualify_complete_structural_chain(
    capture_id: str,
    raw_sha: str,
    manifest_sha: str,
) -> None:
    raw, manifest = _load_capture(capture_id)
    assert manifest.raw_sha256 == raw_sha
    assert sha256_data_matches_capture_manifest(manifest) == manifest_sha

    result = assess_fotmob_data_matches_eliminated_team_id_value_domain(raw, manifest)
    assert (
        result.status
        is EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    )
    assert result.source_raw_sha256 == raw_sha
    assert result.source_capture_manifest_sha256 == manifest_sha
    assert result.eliminated_team_id_occurrence_count == 183
    assert result.eliminated_team_id_non_null_count == 1
    assert result.eliminated_team_id_null_count == 182
    assert result.pr87_match_count == 183
    assert result.pr87_assessment_size > 0
    assert result.status_reason_semantics_qualified is False
    assert result.final_result_semantics_qualified is False
    assert result.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert set(result.safety) == SAFETY_KEYS
    assert all(type(flag) is bool and flag is False for flag in result.safety.values())


@pytest.mark.parametrize("capture_id", (FIRST_CAPTURE_ID, SECOND_CAPTURE_ID))
def test_frozen_pr87_itself_remains_unchanged_and_still_rejects_real_capture(
    capture_id: str,
) -> None:
    raw, manifest = _load_capture(capture_id)
    with pytest.raises(pr87.FotMobDataMatchesTerminalStateSchemaExtensionError) as exc_info:
        pr87.assess_fotmob_data_matches_terminal_state_schema_extension(raw, manifest)
    assert (
        exc_info.value.status
        is pr87.TerminalStateSchemaExtensionStatus.BLOCKED_BASE_PR39_CONTRACT_DRIFT
    )
    assert "non-null eliminatedTeamId" in str(exc_info.value)


def test_null_and_positive_integer_domains_qualify_structurally() -> None:
    null_result = _assess_synthetic(None)
    assert null_result.eliminated_team_id_non_null_count == 0
    assert null_result.eliminated_team_id_null_count == 1

    positive_result = _assess_synthetic(11)
    assert positive_result.eliminated_team_id_non_null_count == 1
    assert positive_result.eliminated_team_id_null_count == 0


def test_positive_integer_need_not_equal_endpoint_team_ids() -> None:
    result = _assess_synthetic(999999)
    assert (
        result.status
        is EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    )
    assert result.eliminated_team_id_non_null_count == 1


@pytest.mark.parametrize("bad_value", (True, False, 1.0, "11", [], {}))
def test_non_integer_non_null_values_fail_closed(bad_value: Any) -> None:
    raw = _raw_bytes(_synthetic_payload(bad_value))
    with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError) as exc_info:
        assess_fotmob_data_matches_eliminated_team_id_value_domain(raw, _manifest_for_raw(raw))
    assert (
        exc_info.value.status
        is EliminatedTeamIdValueDomainStatus.BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH
    )


@pytest.mark.parametrize("bad_value", (0, -1, -999))
def test_nonpositive_integer_values_fail_closed(bad_value: int) -> None:
    raw = _raw_bytes(_synthetic_payload(bad_value))
    with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError) as exc_info:
        assess_fotmob_data_matches_eliminated_team_id_value_domain(raw, _manifest_for_raw(raw))
    assert (
        exc_info.value.status
        is EliminatedTeamIdValueDomainStatus.BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER
    )


def test_value_domain_projection_does_not_hide_other_pr87_structural_failure() -> None:
    payload = _synthetic_payload(11)
    payload["leagues"][0]["matches"][0]["home"]["invented"] = 1
    raw = _raw_bytes(payload)
    with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError) as exc_info:
        assess_fotmob_data_matches_eliminated_team_id_value_domain(raw, _manifest_for_raw(raw))
    assert (
        exc_info.value.status
        is EliminatedTeamIdValueDomainStatus.BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT
    )
    assert "BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET" in str(exc_info.value)


def test_source_raw_manifest_lineage_mismatch_fails_closed() -> None:
    raw = _raw_bytes(_synthetic_payload(11))
    manifest = _manifest_for_raw(raw)
    changed_raw = raw + b" "
    with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError) as exc_info:
        assess_fotmob_data_matches_eliminated_team_id_value_domain(changed_raw, manifest)
    assert (
        exc_info.value.status
        is EliminatedTeamIdValueDomainStatus.BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT
    )


def test_assessment_is_deterministic_immutable_and_fail_closed() -> None:
    first = _assess_synthetic(11)
    second = _assess_synthetic(11)
    first_bytes = canonical_fotmob_data_matches_eliminated_team_id_value_domain_assessment_bytes(first)
    second_bytes = canonical_fotmob_data_matches_eliminated_team_id_value_domain_assessment_bytes(second)
    assert first_bytes == second_bytes
    assert (
        sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(first)
        == hashlib.sha256(first_bytes).hexdigest()
    )

    for changes in (
        {"status_reason_semantics_qualified": True},
        {"final_result_semantics_qualified": True},
        {"eliminated_team_id_non_null_count": 2},
        {"request_date": "2026-08-15"},
        {"timezone": ""},
        {"ccode3": "ng"},
        {"source_raw_size": MAX_RESPONSE_BYTES + 1},
    ):
        with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError):
            dataclasses.replace(first, **changes)

    safety = dict(first.safety)
    safety["bet_authorized"] = True
    with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError):
        dataclasses.replace(first, safety=safety)
    with pytest.raises(TypeError):
        first.safety["bet_authorized"] = True  # type: ignore[index]


def test_source_capability_and_all_downstream_authority_remain_unchanged() -> None:
    result = _assess_synthetic(11)
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    assert all(flag is False for flag in result.safety.values())


def test_next_boundary_is_status_reason_semantics_preregistration_only() -> None:
    result = _assess_synthetic(11)
    assert (
        NEXT_REQUIRED_BOUNDARY
        == "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL"
    )
    assert result.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert result.status_reason_semantics_qualified is False
    assert result.final_result_semantics_qualified is False


def test_implementation_has_no_network_or_downstream_runtime_imports() -> None:
    path = ROOT / "domain" / "fotmob_data_matches_eliminated_team_id_value_domain_extension.py"
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
