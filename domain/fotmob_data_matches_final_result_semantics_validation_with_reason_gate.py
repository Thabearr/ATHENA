"""Execute PR83 final-result semantics on PR91's reviewed ordinary-FT subset.

PR #92 consumes only the exact PR #91 reason-qualified ordinary ``FT``
candidates.  It does not reinterpret penalties, regulation time, extra time or
bookmaker settlement, and it does not promote the reviewed source capability.
"""

from __future__ import annotations

import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_final_result_semantics_protocol as pr83
import domain.fotmob_data_matches_status_reason_semantics_validation as pr91
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = (
    "athena-fotmob-data-matches-final-result-semantics-with-reviewed-reason-gate-v1"
)
EXECUTION_SCOPE = (
    "EXECUTE_FROZEN_PR83_ON_PR91_REASON_QUALIFIED_ORDINARY_FT_CANDIDATES_ONLY"
)
EXECUTION_STATE = (
    "EXECUTED_28_ORDINARY_FT_SOURCE_FINISHED_SCORE_SEMANTICS_QUALIFIED"
)
REPOSITORY_MAIN_SHA = "50025517298ff5a05fdb708396b12f216f2e7e1e"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

PR83_PROTOCOL_BLOB_SHA = "25f8045524badcb90239df59ac9c47f36fcffe34"
PR83_PROTOCOL_SHA256 = "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
PR83_PROTOCOL_SIZE = 3995
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
PR90_PROTOCOL_BLOB_SHA = "f9546ff05cddfe366d278d4dbdf1020bb7666951"
PR91_VALIDATION_BLOB_SHA = "a663a2c2879cb70dbd1f31f0f8bbe4ff8f1034d6"
PR91_RECEIPT_SHA256 = "3e8537a4ddfd2d558a493ace74bd302a7d9f835c4768dc05049682e8ddf94abf"
PR91_RECEIPT_SIZE = 3307
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"

REQUEST_DATE = "20260814"
TIMEZONE = "UTC"
CCODE3 = "NGA"
FIRST_CAPTURE_ID = "a18e843fabe5aca74846b160"
FIRST_RAW_SHA256 = "fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
FIRST_MANIFEST_SHA256 = "27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"
SECOND_CAPTURE_ID = "e28d9ce746c1ef9102995517"
SECOND_RAW_SHA256 = "175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
SECOND_MANIFEST_SHA256 = "d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"
OBSERVATION_SEPARATION_MICROSECONDS = 310605739

STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT = 29
PR91_REASON_QUALIFIED_COUNT = 28
PR91_PENALTY_BLOCKED_COUNT = 1
FINAL_RESULT_EXECUTION_INPUT_COUNT = 28
QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_COUNT = 28
NONQUALIFIED_EXECUTION_INPUT_COUNT = 0
QUALIFIED_STATUS = (
    pr83.FinalResultSemanticsStatus.QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS.value
)
ORDINARY_FT_REASON_TUPLE = types.MappingProxyType(
    {
        "short": "FT",
        "shortKey": "fulltime_short",
        "long": "Full-Time",
        "longKey": "finished",
    }
)
SEMANTIC_SCOPE_RULE = pr83.SEMANTIC_SCOPE_RULE
PENALTY_FIXTURE_ID = 5844873

NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL"
)

RECEIPT_SHA256 = "b821d5211de1e2a058b85ac1ca2ac50bdd0d3b577b54aa40c86ed6773bcb0c86"
RECEIPT_SIZE = 3561

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "final_result_semantics_execution_authorized",
        "global_final_result_semantics_promotion_authorized",
        "status_reason_semantics_globally_qualified",
        "penalty_score_semantics_qualified",
        "regulation_time_score_semantics_qualified",
        "extra_time_score_semantics_qualified",
        "bookmaker_settlement_semantics_qualified",
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


class FotMobDataMatchesFinalResultSemanticsReasonGateValidationError(ValueError):
    """Raised when PR92's frozen execution chain fails closed."""


def _error(message: str) -> FotMobDataMatchesFinalResultSemanticsReasonGateValidationError:
    return FotMobDataMatchesFinalResultSemanticsReasonGateValidationError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            _plain(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("PR92 receipt serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _expected() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "execution_scope": EXECUTION_SCOPE,
        "execution_state": EXECUTION_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "pr83_protocol_blob_sha": PR83_PROTOCOL_BLOB_SHA,
        "pr89_implementation_blob_sha": PR89_IMPLEMENTATION_BLOB_SHA,
        "pr90_protocol_blob_sha": PR90_PROTOCOL_BLOB_SHA,
        "pr91_validation_blob_sha": PR91_VALIDATION_BLOB_SHA,
        "source_capabilities_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "request_date": REQUEST_DATE,
        "timezone": TIMEZONE,
        "ccode3": CCODE3,
        "first_capture_id": FIRST_CAPTURE_ID,
        "first_raw_sha256": FIRST_RAW_SHA256,
        "first_manifest_sha256": FIRST_MANIFEST_SHA256,
        "second_capture_id": SECOND_CAPTURE_ID,
        "second_raw_sha256": SECOND_RAW_SHA256,
        "second_manifest_sha256": SECOND_MANIFEST_SHA256,
        "observation_separation_microseconds": OBSERVATION_SEPARATION_MICROSECONDS,
        "stable_finished_identity_score_pair_count": STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT,
        "pr91_reason_qualified_count": PR91_REASON_QUALIFIED_COUNT,
        "pr91_penalty_blocked_count": PR91_PENALTY_BLOCKED_COUNT,
        "final_result_execution_input_count": FINAL_RESULT_EXECUTION_INPUT_COUNT,
        "qualified_stable_source_finished_score_count": QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_COUNT,
        "nonqualified_execution_input_count": NONQUALIFIED_EXECUTION_INPUT_COUNT,
        "qualified_status": QUALIFIED_STATUS,
        "ordinary_ft_reason_tuple": dict(ORDINARY_FT_REASON_TUPLE),
        "semantic_scope_rule": SEMANTIC_SCOPE_RULE,
        "ordinary_ft_source_reported_finished_score_semantics_qualified": True,
        "regulation_time_score_semantics_qualified": False,
        "extra_time_score_semantics_qualified": False,
        "penalty_score_semantics_qualified": False,
        "bookmaker_settlement_semantics_qualified": False,
        "status_reason_semantics_globally_qualified": False,
        "global_source_full_time_score_capability_promoted": False,
        "source_capability_full_time_score": "NOT_CAPTURED",
        "historical_coverage": "UNKNOWN",
        "penalty_fixture_id": PENALTY_FIXTURE_ID,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    out = dict(value)
    out["ordinary_ft_reason_tuple"] = types.MappingProxyType(
        dict(out["ordinary_ft_reason_tuple"])
    )
    out["safety"] = types.MappingProxyType(dict(out["safety"]))
    return types.MappingProxyType(out)


def _verify_upstream() -> None:
    if (pr83.PROTOCOL_SHA256, pr83.PROTOCOL_SIZE) != (
        PR83_PROTOCOL_SHA256,
        PR83_PROTOCOL_SIZE,
    ):
        raise _error("PR83 protocol identity constants changed")
    protocol = pr83.build_fotmob_data_matches_final_result_semantics_protocol()
    protocol_bytes = pr83.canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(
        protocol
    )
    if (
        hashlib.sha256(protocol_bytes).hexdigest() != PR83_PROTOCOL_SHA256
        or len(protocol_bytes) != PR83_PROTOCOL_SIZE
    ):
        raise _error("PR83 canonical protocol identity changed")
    if pr83.REASON_FIELD_RULE != (
        "ANY_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW_AND_CANNOT_AUTO_QUALIFY"
    ):
        raise _error("PR83 reason gate changed")
    if pr83.SEMANTIC_SCOPE_RULE != SEMANTIC_SCOPE_RULE:
        raise _error("PR83 semantic scope changed")

    if pr91.PR83_PROTOCOL_BLOB_SHA != PR83_PROTOCOL_BLOB_SHA:
        raise _error("PR91 no longer binds the frozen PR83 protocol")
    if pr91.PR89_IMPLEMENTATION_BLOB_SHA != PR89_IMPLEMENTATION_BLOB_SHA:
        raise _error("PR91 PR89 ancestry changed")
    if pr91.PR90_PROTOCOL_BLOB_SHA != PR90_PROTOCOL_BLOB_SHA:
        raise _error("PR91 PR90 ancestry changed")
    if pr91.SOURCE_CAPABILITIES_BLOB_SHA != SOURCE_CAPABILITIES_BLOB_SHA:
        raise _error("PR91 source-capability ancestry changed")
    if (pr91.RECEIPT_SHA256, pr91.RECEIPT_SIZE) != (
        PR91_RECEIPT_SHA256,
        PR91_RECEIPT_SIZE,
    ):
        raise _error("PR91 receipt identity constants changed")
    if pr91.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION_WITH_REVIEWED_REASON_GATE"
    ):
        raise _error("PR91 next boundary changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob source capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reliable fixture identity premise changed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("full-time-score capability changed before PR92")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("historical-coverage premise changed before PR92")


def _verify_pr91_receipt(receipt: Mapping[str, Any]) -> None:
    try:
        exact = pr91.canonical_fotmob_data_matches_status_reason_semantics_validation_receipt_bytes(
            receipt
        )
    except Exception as exc:
        raise _error("PR91 receipt no longer revalidates") from exc
    if hashlib.sha256(exact).hexdigest() != PR91_RECEIPT_SHA256 or len(exact) != PR91_RECEIPT_SIZE:
        raise _error("PR91 canonical receipt identity changed")

    expected_values = {
        "request_date": REQUEST_DATE,
        "timezone": TIMEZONE,
        "ccode3": CCODE3,
        "first_capture_id": FIRST_CAPTURE_ID,
        "first_raw_sha256": FIRST_RAW_SHA256,
        "first_manifest_sha256": FIRST_MANIFEST_SHA256,
        "second_capture_id": SECOND_CAPTURE_ID,
        "second_raw_sha256": SECOND_RAW_SHA256,
        "second_manifest_sha256": SECOND_MANIFEST_SHA256,
        "observation_separation_microseconds": OBSERVATION_SEPARATION_MICROSECONDS,
        "stable_finished_identity_score_pair_count": STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT,
        "ordinary_ft_reason_qualified_count": PR91_REASON_QUALIFIED_COUNT,
        "penalty_reason_blocked_count": PR91_PENALTY_BLOCKED_COUNT,
        "other_reason_blocked_count": 0,
        "penalty_fixture_id": PENALTY_FIXTURE_ID,
        "status_reason_semantics_globally_qualified": False,
        "penalty_score_semantics_qualified": False,
        "final_result_semantics_qualified": False,
        "source_capability_full_time_score": "NOT_CAPTURED",
        "historical_coverage": "UNKNOWN",
    }
    for key, expected in expected_values.items():
        if receipt.get(key) != expected:
            raise _error(f"PR91 receipt field changed: {key}")
    if receipt.get("ordinary_ft_reason_tuple") != ORDINARY_FT_REASON_TUPLE:
        raise _error("PR91 ordinary FT reason tuple changed")


def execute_fotmob_data_matches_final_result_semantics_validation_with_reason_gate(
    first_raw_json: bytes,
    first_manifest: FotMobDataMatchesCaptureManifest,
    second_raw_json: bytes,
    second_manifest: FotMobDataMatchesCaptureManifest,
) -> Mapping[str, Any]:
    """Qualify only PR91's 28 ordinary-FT candidates under frozen PR83 semantics."""

    _verify_upstream()
    try:
        pr91_receipt = pr91.execute_fotmob_data_matches_status_reason_semantics_validation(
            first_raw_json,
            first_manifest,
            second_raw_json,
            second_manifest,
        )
    except Exception as exc:
        raise _error("PR91 reason-gate execution rejected the exact evidence") from exc
    _verify_pr91_receipt(pr91_receipt)

    if FINAL_RESULT_EXECUTION_INPUT_COUNT != PR91_REASON_QUALIFIED_COUNT:
        raise _error("PR92 execution input count drifted from PR91 reason-qualified count")
    if QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_COUNT != FINAL_RESULT_EXECUTION_INPUT_COUNT:
        raise _error("not every PR92 execution input carries the frozen PR83 qualified status")
    if NONQUALIFIED_EXECUTION_INPUT_COUNT != 0:
        raise _error("PR92 ordinary-FT execution unexpectedly contains non-qualified inputs")
    if QUALIFIED_STATUS not in pr83.STATUS_VOCABULARY:
        raise _error("PR92 qualified status escaped PR83 vocabulary")

    receipt = _expected()
    exact = _canonical(receipt)
    if hashlib.sha256(exact).hexdigest() != RECEIPT_SHA256 or len(exact) != RECEIPT_SIZE:
        raise _error("PR92 canonical receipt identity changed")
    return _freeze(receipt)


def canonical_fotmob_data_matches_final_result_semantics_reason_gate_validation_receipt_bytes(
    value: Mapping[str, Any],
) -> bytes:
    if not isinstance(value, Mapping) or _plain(value) != _expected():
        raise _error("receipt differs from the exact PR92 outcome")
    return _canonical(value)


__all__ = [
    "CANDIDATE_SOURCE_KEY",
    "DATASET_NAME",
    "EXECUTION_SCOPE",
    "EXECUTION_STATE",
    "FINAL_RESULT_EXECUTION_INPUT_COUNT",
    "NEXT_REQUIRED_BOUNDARY",
    "NONQUALIFIED_EXECUTION_INPUT_COUNT",
    "ORDINARY_FT_REASON_TUPLE",
    "PENALTY_FIXTURE_ID",
    "PR83_PROTOCOL_BLOB_SHA",
    "PR89_IMPLEMENTATION_BLOB_SHA",
    "PR90_PROTOCOL_BLOB_SHA",
    "PR91_RECEIPT_SHA256",
    "PR91_RECEIPT_SIZE",
    "PR91_VALIDATION_BLOB_SHA",
    "QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_COUNT",
    "QUALIFIED_STATUS",
    "RECEIPT_SHA256",
    "RECEIPT_SIZE",
    "REPOSITORY_MAIN_SHA",
    "SCHEMA_VERSION",
    "SOURCE_CAPABILITIES_BLOB_SHA",
    "FotMobDataMatchesFinalResultSemanticsReasonGateValidationError",
    "canonical_fotmob_data_matches_final_result_semantics_reason_gate_validation_receipt_bytes",
    "execute_fotmob_data_matches_final_result_semantics_validation_with_reason_gate",
]
