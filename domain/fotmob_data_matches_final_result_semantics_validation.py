"""Execute PR83 against ATHENA's currently reviewed FotMob evidence inventory.

This boundary is deliberately evidence-limited.  It does not acquire new network
material.  It records that the committed/reviewed data-matches evidence known
by the PR39 lineage cannot establish a PR83-eligible two-capture post-finish
pair, so final-result semantics remain unqualified.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from domain.fotmob_data_matches_final_result_semantics_protocol import (
    FinalResultSemanticsStatus,
    NEXT_REQUIRED_BOUNDARY as PR83_NEXT_REQUIRED_BOUNDARY,
    PROTOCOL_SHA256 as PR83_CANONICAL_SHA256,
    PROTOCOL_SIZE as PR83_CANONICAL_SIZE,
    PROTOCOL_STATE as PR83_PROTOCOL_STATE,
    STATUS_VOCABULARY as PR83_STATUS_VOCABULARY,
    build_fotmob_data_matches_final_result_semantics_protocol,
    canonical_fotmob_data_matches_final_result_semantics_protocol_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-final-result-semantics-validation-v1"
VALIDATION_SCOPE = "EXECUTE_PR83_AGAINST_CURRENT_REVIEWED_EVIDENCE_INVENTORY_ONLY"
VALIDATION_STATE = "EXECUTED_FAIL_CLOSED_INSUFFICIENT_POST_FINISH_OBSERVATIONS"

PR83_MAIN_SHA = "5cba22dfa480f66cf7fde22e31c730fb0848bcce"
PR83_PROTOCOL_BLOB_SHA = "25f8045524badcb90239df59ac9c47f36fcffe34"
PR83_PROTOCOL_SHA256 = "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
PR83_PROTOCOL_SIZE = 3995
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

# PR39's reviewed schema documentation records exactly one reviewed PR38 capture.
# Its raw body remains deliberately ignored research state rather than committed
# fixture-level evidence.  PR39 emitted metadata only and did not establish a
# PR83-eligible finished observation.  The exact number of post-finish captures
# cannot be reconstructed from committed metadata, so it remains UNKNOWN rather
# than being guessed as zero or one.
REVIEWED_INVENTORY_BASIS = (
    "PR39_DOCUMENTED_SINGLE_REVIEWED_DATA_MATCHES_CAPTURE_METADATA_ONLY"
)
REVIEWED_CAPTURE_COUNT = 1
REVIEWED_POST_FINISH_CAPTURE_COUNT = "UNKNOWN_FROM_COMMITTED_METADATA_ONLY"
REVIEWED_PR83_ELIGIBLE_CAPTURE_PAIR_COUNT = 0
REQUIRED_DISTINCT_POST_FINISH_CAPTURES_PER_PAIR = 2
REVIEWED_CAPTURE_REQUEST_DATE = "20260815"
REVIEWED_CAPTURE_RAW_SHA256 = (
    "6eabfb341d29f3b5db0833972a9aaf7dbd97df150ccecde09f6f67396bc73b27"
)
REVIEWED_CAPTURE_RAW_SIZE = 314098
REVIEWED_CAPTURE_MANIFEST_SHA256 = (
    "3fe1d24a0738114c46114a815eca44c4221b53fe8da2476d5a487153ce72d145"
)
REVIEWED_CAPTURE_FIXTURE_VALUES_AVAILABLE = False
REVIEWED_CAPTURE_STARTED_FINISHED_SEMANTICS_AVAILABLE = False

VALIDATION_STATUS = FinalResultSemanticsStatus.BLOCKED_INSUFFICIENT_POST_FINISH_OBSERVATIONS
STATUS_REASON = (
    "CURRENT_REVIEWED_INVENTORY_HAS_NO_PR83_ELIGIBLE_POST_FINISH_CAPTURE_PAIR_AND_NO_COMMITTED_FIXTURE_LEVEL_VALUES_TO_RECONSTRUCT_ONE"
)
NEXT_REQUIRED_BOUNDARY = (
    "ACQUIRE_AND_PRESERVE_TWO_REVIEWED_POST_FINISH_DATA_MATCHES_CAPTURES_FOR_ONE_FINISHED_FIXTURE"
)

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

VALIDATION_SHA256 = "b8ac94402677c8d539ac365e348fd8415d3963b6511a0db5d0564f38737f1b9a"
VALIDATION_SIZE = 2490


class FotMobDataMatchesFinalResultSemanticsValidationError(ValueError):
    """Raised if the frozen PR84 receipt or its reviewed ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesFinalResultSemanticsValidationError:
    return FotMobDataMatchesFinalResultSemanticsValidationError(message)


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
        raise _error("final-result semantics validation serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("final-result semantics validation safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR84 safety values must be exact False")
    return _safety()


def _verify_upstream() -> None:
    if (
        PR83_CANONICAL_SHA256 != PR83_PROTOCOL_SHA256
        or PR83_CANONICAL_SIZE != PR83_PROTOCOL_SIZE
    ):
        raise _error("PR83 canonical protocol constants changed")
    protocol = build_fotmob_data_matches_final_result_semantics_protocol()
    exact = canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(protocol)
    if (
        hashlib.sha256(exact).hexdigest() != PR83_PROTOCOL_SHA256
        or len(exact) != PR83_PROTOCOL_SIZE
    ):
        raise _error("PR83 canonical protocol identity changed")
    if PR83_PROTOCOL_STATE != "PRE_REGISTERED_NOT_EXECUTED_NO_FINAL_RESULT_SEMANTICS_QUALIFIED":
        raise _error("PR83 protocol state changed")
    if PR83_NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION"
    ):
        raise _error("PR83 next boundary changed")
    if VALIDATION_STATUS.value not in PR83_STATUS_VOCABULARY:
        raise _error("PR84 status is outside the frozen PR83 vocabulary")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob data-matches capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity is no longer confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("PR84 full-time-score premise changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("PR84 historical-coverage premise changed")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "validation_scope": VALIDATION_SCOPE,
        "validation_state": VALIDATION_STATE,
        "repository_main_sha": PR83_MAIN_SHA,
        "pr83_protocol_blob_sha": PR83_PROTOCOL_BLOB_SHA,
        "pr83_protocol_sha256": PR83_PROTOCOL_SHA256,
        "pr83_protocol_size": PR83_PROTOCOL_SIZE,
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "reviewed_inventory_basis": REVIEWED_INVENTORY_BASIS,
        "reviewed_capture_count": REVIEWED_CAPTURE_COUNT,
        "reviewed_post_finish_capture_count": REVIEWED_POST_FINISH_CAPTURE_COUNT,
        "reviewed_pr83_eligible_capture_pair_count": (
            REVIEWED_PR83_ELIGIBLE_CAPTURE_PAIR_COUNT
        ),
        "required_distinct_post_finish_captures_per_pair": (
            REQUIRED_DISTINCT_POST_FINISH_CAPTURES_PER_PAIR
        ),
        "reviewed_capture_request_date": REVIEWED_CAPTURE_REQUEST_DATE,
        "reviewed_capture_raw_sha256": REVIEWED_CAPTURE_RAW_SHA256,
        "reviewed_capture_raw_size": REVIEWED_CAPTURE_RAW_SIZE,
        "reviewed_capture_manifest_sha256": REVIEWED_CAPTURE_MANIFEST_SHA256,
        "reviewed_capture_fixture_values_available_in_committed_reviewed_evidence": (
            REVIEWED_CAPTURE_FIXTURE_VALUES_AVAILABLE
        ),
        "reviewed_capture_started_finished_semantics_available": (
            REVIEWED_CAPTURE_STARTED_FINISHED_SEMANTICS_AVAILABLE
        ),
        "status": VALIDATION_STATUS.value,
        "status_reason": STATUS_REASON,
        "final_result_semantics_qualified": False,
        "source_capability_must_remain": CapabilityAvailability.NOT_CAPTURED.value,
        "historical_coverage_must_remain": CapabilityAvailability.UNKNOWN.value,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesFinalResultSemanticsValidation:
    schema_version: int
    dataset_name: str
    validation_scope: str
    validation_state: str
    repository_main_sha: str
    pr83_protocol_blob_sha: str
    pr83_protocol_sha256: str
    pr83_protocol_size: int
    candidate_source_key: str
    reviewed_inventory_basis: str
    reviewed_capture_count: int
    reviewed_post_finish_capture_count: str
    reviewed_pr83_eligible_capture_pair_count: int
    required_distinct_post_finish_captures_per_pair: int
    reviewed_capture_request_date: str
    reviewed_capture_raw_sha256: str
    reviewed_capture_raw_size: int
    reviewed_capture_manifest_sha256: str
    reviewed_capture_fixture_values_available_in_committed_reviewed_evidence: bool
    reviewed_capture_started_finished_semantics_available: bool
    status: str
    status_reason: str
    final_result_semantics_qualified: bool
    source_capability_must_remain: str
    historical_coverage_must_remain: str
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _payload():
            raise _error("final-result semantics validation differs from frozen PR84 receipt")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "validation_scope": self.validation_scope,
            "validation_state": self.validation_state,
            "repository_main_sha": self.repository_main_sha,
            "pr83_protocol_blob_sha": self.pr83_protocol_blob_sha,
            "pr83_protocol_sha256": self.pr83_protocol_sha256,
            "pr83_protocol_size": self.pr83_protocol_size,
            "candidate_source_key": self.candidate_source_key,
            "reviewed_inventory_basis": self.reviewed_inventory_basis,
            "reviewed_capture_count": self.reviewed_capture_count,
            "reviewed_post_finish_capture_count": self.reviewed_post_finish_capture_count,
            "reviewed_pr83_eligible_capture_pair_count": (
                self.reviewed_pr83_eligible_capture_pair_count
            ),
            "required_distinct_post_finish_captures_per_pair": (
                self.required_distinct_post_finish_captures_per_pair
            ),
            "reviewed_capture_request_date": self.reviewed_capture_request_date,
            "reviewed_capture_raw_sha256": self.reviewed_capture_raw_sha256,
            "reviewed_capture_raw_size": self.reviewed_capture_raw_size,
            "reviewed_capture_manifest_sha256": self.reviewed_capture_manifest_sha256,
            "reviewed_capture_fixture_values_available_in_committed_reviewed_evidence": (
                self.reviewed_capture_fixture_values_available_in_committed_reviewed_evidence
            ),
            "reviewed_capture_started_finished_semantics_available": (
                self.reviewed_capture_started_finished_semantics_available
            ),
            "status": self.status,
            "status_reason": self.status_reason,
            "final_result_semantics_qualified": self.final_result_semantics_qualified,
            "source_capability_must_remain": self.source_capability_must_remain,
            "historical_coverage_must_remain": self.historical_coverage_must_remain,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_fotmob_data_matches_final_result_semantics_validation(
) -> FotMobDataMatchesFinalResultSemanticsValidation:
    _verify_upstream()
    payload = _payload()
    value = FotMobDataMatchesFinalResultSemanticsValidation(
        schema_version=payload["schema_version"],
        dataset_name=payload["dataset_name"],
        validation_scope=payload["validation_scope"],
        validation_state=payload["validation_state"],
        repository_main_sha=payload["repository_main_sha"],
        pr83_protocol_blob_sha=payload["pr83_protocol_blob_sha"],
        pr83_protocol_sha256=payload["pr83_protocol_sha256"],
        pr83_protocol_size=payload["pr83_protocol_size"],
        candidate_source_key=payload["candidate_source_key"],
        reviewed_inventory_basis=payload["reviewed_inventory_basis"],
        reviewed_capture_count=payload["reviewed_capture_count"],
        reviewed_post_finish_capture_count=payload["reviewed_post_finish_capture_count"],
        reviewed_pr83_eligible_capture_pair_count=payload[
            "reviewed_pr83_eligible_capture_pair_count"
        ],
        required_distinct_post_finish_captures_per_pair=payload[
            "required_distinct_post_finish_captures_per_pair"
        ],
        reviewed_capture_request_date=payload["reviewed_capture_request_date"],
        reviewed_capture_raw_sha256=payload["reviewed_capture_raw_sha256"],
        reviewed_capture_raw_size=payload["reviewed_capture_raw_size"],
        reviewed_capture_manifest_sha256=payload["reviewed_capture_manifest_sha256"],
        reviewed_capture_fixture_values_available_in_committed_reviewed_evidence=payload[
            "reviewed_capture_fixture_values_available_in_committed_reviewed_evidence"
        ],
        reviewed_capture_started_finished_semantics_available=payload[
            "reviewed_capture_started_finished_semantics_available"
        ],
        status=payload["status"],
        status_reason=payload["status_reason"],
        final_result_semantics_qualified=payload["final_result_semantics_qualified"],
        source_capability_must_remain=payload["source_capability_must_remain"],
        historical_coverage_must_remain=payload["historical_coverage_must_remain"],
        next_required_boundary=payload["next_required_boundary"],
        safety=_safety(),
    )
    exact = canonical_fotmob_data_matches_final_result_semantics_validation_bytes(value)
    if hashlib.sha256(exact).hexdigest() != VALIDATION_SHA256 or len(exact) != VALIDATION_SIZE:
        raise _error("PR84 final-result semantics validation canonical identity changed")
    return value


def canonical_fotmob_data_matches_final_result_semantics_validation_bytes(
    value: FotMobDataMatchesFinalResultSemanticsValidation,
) -> bytes:
    if not isinstance(value, FotMobDataMatchesFinalResultSemanticsValidation):
        raise _error("final-result semantics validation value has wrong type")
    return _canonical(value.to_dict())


def revalidate_fotmob_data_matches_final_result_semantics_validation(
    value: FotMobDataMatchesFinalResultSemanticsValidation,
) -> FotMobDataMatchesFinalResultSemanticsValidation:
    if not isinstance(value, FotMobDataMatchesFinalResultSemanticsValidation):
        raise _error("final-result semantics validation value has wrong type")
    expected = build_fotmob_data_matches_final_result_semantics_validation()
    if canonical_fotmob_data_matches_final_result_semantics_validation_bytes(value) != (
        canonical_fotmob_data_matches_final_result_semantics_validation_bytes(expected)
    ):
        raise _error("final-result semantics validation receipt changed")
    return expected
