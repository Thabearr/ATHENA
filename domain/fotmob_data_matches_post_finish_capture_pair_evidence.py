"""Freeze the acquired FotMob PR83 post-finish capture-pair evidence.

PR85 preserves two exact transparent PR38 captures collected 310+ seconds apart.
It does not qualify final-result semantics because the current terminal snapshots
do not revalidate under the frozen PR39 schema.  The receipt therefore records
the evidence and the exact fail-closed boundary without granting downstream
authority.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from domain.fotmob_data_matches_final_result_semantics_protocol import (
    PROTOCOL_SHA256 as PR83_CANONICAL_SHA256,
    PROTOCOL_SIZE as PR83_CANONICAL_SIZE,
    build_fotmob_data_matches_final_result_semantics_protocol,
    canonical_fotmob_data_matches_final_result_semantics_protocol_bytes,
)
from domain.fotmob_data_matches_final_result_semantics_validation import (
    VALIDATION_SHA256 as PR84_CANONICAL_SHA256,
    VALIDATION_SIZE as PR84_CANONICAL_SIZE,
    build_fotmob_data_matches_final_result_semantics_validation,
    canonical_fotmob_data_matches_final_result_semantics_validation_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-post-finish-capture-pair-evidence-v1"
EVIDENCE_SCOPE = "ACQUIRE_AND_PRESERVE_PR83_POST_FINISH_CAPTURE_PAIR_EVIDENCE_ONLY"
EVIDENCE_STATE = "ACQUIRED_DISTINCT_CAPTURE_PAIR_BLOCKED_BY_PR39_TERMINAL_SCHEMA_DRIFT"

REPOSITORY_MAIN_SHA = "3ec2b2f415d483da6412fedb857c23642ee3b08b"
PR83_PROTOCOL_BLOB_SHA = "25f8045524badcb90239df59ac9c47f36fcffe34"
PR83_PROTOCOL_SHA256 = "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
PR83_PROTOCOL_SIZE = 3995
PR84_VALIDATION_BLOB_SHA = "93a74ff60b3af7549f06d8b37b3323a07f7404c4"
PR84_VALIDATION_SHA256 = "b8ac94402677c8d539ac365e348fd8415d3963b6511a0db5d0564f38737f1b9a"
PR84_VALIDATION_SIZE = 2490

ACQUISITION_RUN_ID = 31822859656
ACQUISITION_JOB_ID = 94840009083
ARTIFACT_ID = 9227788141
ARTIFACT_ZIP_SHA256 = "9dac79f90dad5c447eccf8fd6874f464f7e69437c979d82baaed633334cf3996"

REQUEST_DATE = "20260814"
TIMEZONE = "UTC"
CCODE3 = "NGA"

FIRST_CAPTURE_ID = "a18e843fabe5aca74846b160"
FIRST_OBSERVED_AT = "2026-08-14T17:12:02.437509Z"
FIRST_RAW_SHA256 = "fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
FIRST_RAW_SIZE = 114920
FIRST_MANIFEST_SHA256 = "27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"

SECOND_CAPTURE_ID = "e28d9ce746c1ef9102995517"
SECOND_OBSERVED_AT = "2026-08-14T17:17:13.043248Z"
SECOND_RAW_SHA256 = "175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
SECOND_RAW_SIZE = 114964
SECOND_MANIFEST_SHA256 = "d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"

OBSERVATION_SEPARATION_SECONDS = 310.605739
FIRST_MATCH_COUNT = 183
SECOND_MATCH_COUNT = 183
STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT = 29
ORDINARY_FT_REASON_PAIR_COUNT = 28
PENALTY_REASON_PAIR_COUNT = 1

SELECTED_FIXTURE_ID = 5186581
SELECTED_LEAGUE_ID = 920266
SELECTED_LEAGUE_NAME = "Super League"
SELECTED_HOME_TEAM_ID = 8623
SELECTED_HOME_TEAM_NAME = "Shandong Taishan"
SELECTED_AWAY_TEAM_ID = 4183
SELECTED_AWAY_TEAM_NAME = "Qingdao Hainiu"
SELECTED_KICKOFF_UTC = "2026-08-14T11:35:00.000Z"
SELECTED_HOME_SCORE = 3
SELECTED_AWAY_SCORE = 1
SELECTED_STATUS_ID_FIRST = 6
SELECTED_STATUS_ID_SECOND = 6
SELECTED_REASON_SHORT = "FT"
SELECTED_REASON_SHORT_KEY = "fulltime_short"
SELECTED_REASON_LONG = "Full-Time"
SELECTED_REASON_LONG_KEY = "finished"
SELECTED_FIXTURE_PROJECTION_SHA256 = (
    "46cab2b5138a620995fd093946f556dc3c5233a50c212c46253c5f8dd9184d1b"
)
SELECTED_FIXTURE_PROJECTION_SIZE = 788

PR39_EXTRA_TEAM_KEYS = ("penScore", "redCards")
PR39_EXTRA_STATUS_KEYS = (
    "awarded",
    "liveTime",
    "numberOfAwayRedCards",
    "numberOfHomeRedCards",
    "ongoing",
    "scoreStr",
)
PR39_EXTRA_HALFS_KEYS = ("secondHalfStarted",)
PRIMARY_BLOCKER = "PR39_STRICT_SCHEMA_REVALIDATION_FAILED_TERMINAL_SNAPSHOT_EXTRA_KEYS"
SECONDARY_BLOCKER = "PR83_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION"
)
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
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
)

EVIDENCE_SHA256 = "a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02"
EVIDENCE_SIZE = 3921


class FotMobDataMatchesPostFinishCapturePairEvidenceError(ValueError):
    """Raised if the frozen PR85 evidence receipt or ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesPostFinishCapturePairEvidenceError:
    return FotMobDataMatchesPostFinishCapturePairEvidenceError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("post-finish capture-pair evidence serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("post-finish capture-pair safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR85 safety values must be exact False")
    return _safety()


def _verify_upstream() -> None:
    if (
        PR83_CANONICAL_SHA256 != PR83_PROTOCOL_SHA256
        or PR83_CANONICAL_SIZE != PR83_PROTOCOL_SIZE
    ):
        raise _error("PR83 canonical protocol constants changed")
    protocol = build_fotmob_data_matches_final_result_semantics_protocol()
    protocol_bytes = canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(
        protocol
    )
    if (
        hashlib.sha256(protocol_bytes).hexdigest() != PR83_PROTOCOL_SHA256
        or len(protocol_bytes) != PR83_PROTOCOL_SIZE
    ):
        raise _error("PR83 canonical protocol identity changed")

    if (
        PR84_CANONICAL_SHA256 != PR84_VALIDATION_SHA256
        or PR84_CANONICAL_SIZE != PR84_VALIDATION_SIZE
    ):
        raise _error("PR84 canonical validation constants changed")
    validation = build_fotmob_data_matches_final_result_semantics_validation()
    validation_bytes = canonical_fotmob_data_matches_final_result_semantics_validation_bytes(
        validation
    )
    if (
        hashlib.sha256(validation_bytes).hexdigest() != PR84_VALIDATION_SHA256
        or len(validation_bytes) != PR84_VALIDATION_SIZE
    ):
        raise _error("PR84 canonical validation identity changed")
    if validation.next_required_boundary != (
        "ACQUIRE_AND_PRESERVE_TWO_REVIEWED_POST_FINISH_DATA_MATCHES_CAPTURES_FOR_ONE_FINISHED_FIXTURE"
    ):
        raise _error("PR84 next boundary changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob data-matches capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity is no longer confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("PR85 full-time-score premise changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("PR85 historical-coverage premise changed")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "evidence_scope": EVIDENCE_SCOPE,
        "evidence_state": EVIDENCE_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr83_protocol_blob_sha": PR83_PROTOCOL_BLOB_SHA,
        "pr83_protocol_sha256": PR83_PROTOCOL_SHA256,
        "pr83_protocol_size": PR83_PROTOCOL_SIZE,
        "pr84_validation_blob_sha": PR84_VALIDATION_BLOB_SHA,
        "pr84_validation_sha256": PR84_VALIDATION_SHA256,
        "pr84_validation_size": PR84_VALIDATION_SIZE,
        "acquisition_run_id": ACQUISITION_RUN_ID,
        "acquisition_job_id": ACQUISITION_JOB_ID,
        "artifact_id": ARTIFACT_ID,
        "artifact_zip_sha256": ARTIFACT_ZIP_SHA256,
        "request_date": REQUEST_DATE,
        "timezone": TIMEZONE,
        "ccode3": CCODE3,
        "first_capture_id": FIRST_CAPTURE_ID,
        "first_observed_at": FIRST_OBSERVED_AT,
        "first_raw_sha256": FIRST_RAW_SHA256,
        "first_raw_size": FIRST_RAW_SIZE,
        "first_manifest_sha256": FIRST_MANIFEST_SHA256,
        "second_capture_id": SECOND_CAPTURE_ID,
        "second_observed_at": SECOND_OBSERVED_AT,
        "second_raw_sha256": SECOND_RAW_SHA256,
        "second_raw_size": SECOND_RAW_SIZE,
        "second_manifest_sha256": SECOND_MANIFEST_SHA256,
        "observation_separation_seconds": OBSERVATION_SEPARATION_SECONDS,
        "raw_lineage_distinct": True,
        "manifest_lineage_distinct": True,
        "first_match_count": FIRST_MATCH_COUNT,
        "second_match_count": SECOND_MATCH_COUNT,
        "stable_finished_identity_score_pair_count": (
            STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT
        ),
        "ordinary_ft_reason_pair_count": ORDINARY_FT_REASON_PAIR_COUNT,
        "penalty_reason_pair_count": PENALTY_REASON_PAIR_COUNT,
        "selected_fixture_id": SELECTED_FIXTURE_ID,
        "selected_league_id": SELECTED_LEAGUE_ID,
        "selected_league_name": SELECTED_LEAGUE_NAME,
        "selected_home_team_id": SELECTED_HOME_TEAM_ID,
        "selected_home_team_name": SELECTED_HOME_TEAM_NAME,
        "selected_away_team_id": SELECTED_AWAY_TEAM_ID,
        "selected_away_team_name": SELECTED_AWAY_TEAM_NAME,
        "selected_kickoff_utc": SELECTED_KICKOFF_UTC,
        "selected_home_score": SELECTED_HOME_SCORE,
        "selected_away_score": SELECTED_AWAY_SCORE,
        "selected_status_id_first": SELECTED_STATUS_ID_FIRST,
        "selected_status_id_second": SELECTED_STATUS_ID_SECOND,
        "selected_reason_short": SELECTED_REASON_SHORT,
        "selected_reason_short_key": SELECTED_REASON_SHORT_KEY,
        "selected_reason_long": SELECTED_REASON_LONG,
        "selected_reason_long_key": SELECTED_REASON_LONG_KEY,
        "selected_fixture_projection_sha256": SELECTED_FIXTURE_PROJECTION_SHA256,
        "selected_fixture_projection_size": SELECTED_FIXTURE_PROJECTION_SIZE,
        "pr39_schema_revalidation_passed": False,
        "pr39_extra_team_keys": list(PR39_EXTRA_TEAM_KEYS),
        "pr39_extra_status_keys": list(PR39_EXTRA_STATUS_KEYS),
        "pr39_extra_halfs_keys": list(PR39_EXTRA_HALFS_KEYS),
        "primary_blocker": PRIMARY_BLOCKER,
        "secondary_blocker": SECONDARY_BLOCKER,
        "pr83_eligibility": False,
        "final_result_semantics_qualified": False,
        "source_capability_full_time_score_must_remain": (
            CapabilityAvailability.NOT_CAPTURED.value
        ),
        "historical_coverage_must_remain": CapabilityAvailability.UNKNOWN.value,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesPostFinishCapturePairEvidence:
    schema_version: int
    dataset_name: str
    evidence_scope: str
    evidence_state: str
    repository_main_sha: str
    pr83_protocol_blob_sha: str
    pr83_protocol_sha256: str
    pr83_protocol_size: int
    pr84_validation_blob_sha: str
    pr84_validation_sha256: str
    pr84_validation_size: int
    acquisition_run_id: int
    acquisition_job_id: int
    artifact_id: int
    artifact_zip_sha256: str
    request_date: str
    timezone: str
    ccode3: str
    first_capture_id: str
    first_observed_at: str
    first_raw_sha256: str
    first_raw_size: int
    first_manifest_sha256: str
    second_capture_id: str
    second_observed_at: str
    second_raw_sha256: str
    second_raw_size: int
    second_manifest_sha256: str
    observation_separation_seconds: float
    raw_lineage_distinct: bool
    manifest_lineage_distinct: bool
    first_match_count: int
    second_match_count: int
    stable_finished_identity_score_pair_count: int
    ordinary_ft_reason_pair_count: int
    penalty_reason_pair_count: int
    selected_fixture_id: int
    selected_league_id: int
    selected_league_name: str
    selected_home_team_id: int
    selected_home_team_name: str
    selected_away_team_id: int
    selected_away_team_name: str
    selected_kickoff_utc: str
    selected_home_score: int
    selected_away_score: int
    selected_status_id_first: int
    selected_status_id_second: int
    selected_reason_short: str
    selected_reason_short_key: str
    selected_reason_long: str
    selected_reason_long_key: str
    selected_fixture_projection_sha256: str
    selected_fixture_projection_size: int
    pr39_schema_revalidation_passed: bool
    pr39_extra_team_keys: tuple[str, ...]
    pr39_extra_status_keys: tuple[str, ...]
    pr39_extra_halfs_keys: tuple[str, ...]
    primary_blocker: str
    secondary_blocker: str
    pr83_eligibility: bool
    final_result_semantics_qualified: bool
    source_capability_full_time_score_must_remain: str
    historical_coverage_must_remain: str
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _payload():
            raise _error("post-finish capture-pair evidence differs from frozen PR85 receipt")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        result = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name != "safety"
        }
        result["pr39_extra_team_keys"] = list(self.pr39_extra_team_keys)
        result["pr39_extra_status_keys"] = list(self.pr39_extra_status_keys)
        result["pr39_extra_halfs_keys"] = list(self.pr39_extra_halfs_keys)
        result["safety"] = dict(self.safety)
        return result


def build_fotmob_data_matches_post_finish_capture_pair_evidence(
) -> FotMobDataMatchesPostFinishCapturePairEvidence:
    _verify_upstream()
    payload = _payload()
    value = FotMobDataMatchesPostFinishCapturePairEvidence(
        **{
            **payload,
            "pr39_extra_team_keys": tuple(payload["pr39_extra_team_keys"]),
            "pr39_extra_status_keys": tuple(payload["pr39_extra_status_keys"]),
            "pr39_extra_halfs_keys": tuple(payload["pr39_extra_halfs_keys"]),
            "safety": _safety(),
        }
    )
    exact = canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(value)
    if hashlib.sha256(exact).hexdigest() != EVIDENCE_SHA256 or len(exact) != EVIDENCE_SIZE:
        raise _error("PR85 post-finish capture-pair canonical identity changed")
    return value


def canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(
    value: FotMobDataMatchesPostFinishCapturePairEvidence,
) -> bytes:
    if not isinstance(value, FotMobDataMatchesPostFinishCapturePairEvidence):
        raise _error("post-finish capture-pair evidence value has wrong type")
    return _canonical(value.to_dict())


def revalidate_fotmob_data_matches_post_finish_capture_pair_evidence(
    value: FotMobDataMatchesPostFinishCapturePairEvidence,
) -> FotMobDataMatchesPostFinishCapturePairEvidence:
    if not isinstance(value, FotMobDataMatchesPostFinishCapturePairEvidence):
        raise _error("post-finish capture-pair evidence value has wrong type")
    expected = build_fotmob_data_matches_post_finish_capture_pair_evidence()
    if canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(value) != (
        canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(expected)
    ):
        raise _error("post-finish capture-pair evidence receipt changed")
    return expected


__all__ = [
    "DATASET_NAME",
    "EVIDENCE_SHA256",
    "EVIDENCE_SIZE",
    "EVIDENCE_STATE",
    "NEXT_REQUIRED_BOUNDARY",
    "FotMobDataMatchesPostFinishCapturePairEvidence",
    "FotMobDataMatchesPostFinishCapturePairEvidenceError",
    "build_fotmob_data_matches_post_finish_capture_pair_evidence",
    "canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes",
    "revalidate_fotmob_data_matches_post_finish_capture_pair_evidence",
]
