"""Execute the reviewed PR95 ordinary-FT finished-score adapter on exact PR85 evidence.

This boundary validates the reusable adapter against the preserved two-capture
post-finish evidence pair and freezes the exact deterministic result. It does not
register a source capability, mutate the parent reviewed catalog, prove historical
coverage, or authorize model, pricing, selection, production, or betting use.
"""
from __future__ import annotations

import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as pr95
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureManifest,
    serialize_utc,
    sha256_bytes,
    sha256_data_matches_capture_manifest,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-ordinary-ft-finished-score-adapter-validation-v1"
EXECUTION_SCOPE = "EXECUTE_PR95_REUSABLE_ADAPTER_AGAINST_EXACT_PRESERVED_PR85_PAIR_ONLY"
EXECUTION_STATE = "EXECUTED_EXACT_PR85_PAIR_28_ORDINARY_FT_SCORES_QUALIFIED_PENALTY_BLOCKED"
REPOSITORY_MAIN_SHA = "d836e6bafb71bdefbc47ae00895229eaa0a136a5"
PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"
PROPOSED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"

PR95_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
PR95_DATASET_NAME = "athena-fotmob-data-matches-ordinary-ft-finished-score-adapter-v1"
PR95_ADAPTER_SCOPE = "REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_PAIR_GATE_ONLY"
PR95_ADAPTER_STATE = "IMPLEMENTED_REUSABLE_PROSPECTIVE_GATE_NO_CAPABILITY_REGISTRATION"
PR85_EVIDENCE_BLOB_SHA = "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"

REQUEST_DATE, TIMEZONE, CCODE3 = "20260814", "UTC", "NGA"
FIRST_CAPTURE_ID = "a18e843fabe5aca74846b160"
FIRST_RAW_SHA256 = "fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
FIRST_MANIFEST_SHA256 = "27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"
FIRST_RAW_SIZE = 114920
FIRST_OBSERVED_AT = "2026-08-14T17:12:02.437509Z"
SECOND_CAPTURE_ID = "e28d9ce746c1ef9102995517"
SECOND_RAW_SHA256 = "175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
SECOND_MANIFEST_SHA256 = "d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"
SECOND_RAW_SIZE = 114964
SECOND_OBSERVED_AT = "2026-08-14T17:17:13.043248Z"
OBSERVATION_SEPARATION_MICROSECONDS = 310_605_739

ADAPTER_RESULT_SHA256 = "7e3fcb2c8a4fa8f883ec7dcac2fd15ea8d2f1aa359c5c5f42ab7eaf604bdce27"
ADAPTER_RESULT_SIZE = 22570
QUALIFIED_SCORES_PROJECTION_SHA256 = "ffdb20556808a1a6459d959b050e3aa5780f3c017d6971adf0c17a3c91ce03ab"
TERMINAL_CANDIDATE_UNION_COUNT = 29
QUALIFIED_COUNT = 28
PENALTY_FIXTURE_ID = 5844873
ORDINARY_ANCHOR_FIXTURE_ID = 5186581
ORDINARY_ANCHOR_HOME_SCORE = 3
ORDINARY_ANCHOR_AWAY_SCORE = 1
PENALTY_BLOCK_STATUS = (
    pr95.AdapterFixtureStatus.BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS.value
)
BLOCKED_FIXTURE_IDS_BY_STATUS = types.MappingProxyType({PENALTY_BLOCK_STATUS: (PENALTY_FIXTURE_ID,)})

NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT_WITH_VALIDATED_ADAPTER"
)
RECEIPT_SHA256 = "09dd9fdff1eddb7b421e968c8de93262b09ce526adeb3d3b95050ddf1f2d4562"
RECEIPT_SIZE = 3610

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_capability_registration_authorized",
        "source_capability_registry_update_performed",
        "parent_source_capability_mutation_authorized",
        "global_fotmob_full_time_score_capability_authorized",
        "historical_coverage_qualified",
        "status_reason_semantics_globally_qualified",
        "regulation_time_score_semantics_qualified",
        "extra_time_score_semantics_qualified",
        "penalty_score_semantics_qualified",
        "bookmaker_settlement_semantics_qualified",
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


class FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError(ValueError):
    """Raised when the exact PR96 execution or receipt drifts."""


def _error(message: str) -> FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError:
    return FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                _plain(value),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("PR96 receipt serialization failed") from exc


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _expected() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "execution_scope": EXECUTION_SCOPE,
        "execution_state": EXECUTION_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "parent_source_key": PARENT_SOURCE_KEY,
        "proposed_source_key": PROPOSED_SOURCE_KEY,
        "pr95_adapter_blob_sha": PR95_ADAPTER_BLOB_SHA,
        "pr85_evidence_blob_sha": PR85_EVIDENCE_BLOB_SHA,
        "source_capabilities_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "request_date": REQUEST_DATE,
        "timezone": TIMEZONE,
        "ccode3": CCODE3,
        "first_capture_id": FIRST_CAPTURE_ID,
        "first_raw_sha256": FIRST_RAW_SHA256,
        "first_manifest_sha256": FIRST_MANIFEST_SHA256,
        "first_raw_size": FIRST_RAW_SIZE,
        "first_observed_at": FIRST_OBSERVED_AT,
        "second_capture_id": SECOND_CAPTURE_ID,
        "second_raw_sha256": SECOND_RAW_SHA256,
        "second_manifest_sha256": SECOND_MANIFEST_SHA256,
        "second_raw_size": SECOND_RAW_SIZE,
        "second_observed_at": SECOND_OBSERVED_AT,
        "observation_separation_microseconds": OBSERVATION_SEPARATION_MICROSECONDS,
        "adapter_result_sha256": ADAPTER_RESULT_SHA256,
        "adapter_result_size": ADAPTER_RESULT_SIZE,
        "qualified_scores_projection_sha256": QUALIFIED_SCORES_PROJECTION_SHA256,
        "pair_status": pr95.AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES.value,
        "terminal_candidate_union_count": TERMINAL_CANDIDATE_UNION_COUNT,
        "qualified_count": QUALIFIED_COUNT,
        "blocked_fixture_ids_by_status": dict(BLOCKED_FIXTURE_IDS_BY_STATUS),
        "penalty_fixture_id": PENALTY_FIXTURE_ID,
        "ordinary_anchor_fixture_id": ORDINARY_ANCHOR_FIXTURE_ID,
        "ordinary_anchor_score": (ORDINARY_ANCHOR_HOME_SCORE, ORDINARY_ANCHOR_AWAY_SCORE),
        "adapter_validation_qualified": True,
        "source_capability_registration_performed": False,
        "parent_source_full_time_score": "NOT_CAPTURED",
        "parent_source_historical_coverage": "UNKNOWN",
        "proposed_source_key_registered": False,
        "semantic_scope_rule": pr95.SEMANTIC_SCOPE_RULE,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    out = dict(value)
    out["blocked_fixture_ids_by_status"] = types.MappingProxyType(
        {key: tuple(items) for key, items in value["blocked_fixture_ids_by_status"].items()}
    )
    out["ordinary_anchor_score"] = tuple(value["ordinary_anchor_score"])
    out["safety"] = types.MappingProxyType(dict(value["safety"]))
    return types.MappingProxyType(out)


def _verify_registry() -> None:
    parent = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    if parent is None:
        raise _error("parent reviewed FotMob catalog capability is missing")
    if parent.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("parent reliable fixture identity premise changed")
    if parent.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("parent full_time_score must remain NOT_CAPTURED")
    if parent.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("parent historical coverage must remain UNKNOWN")
    if PROPOSED_SOURCE_KEY in SOURCE_CAPABILITY_REGISTRY:
        raise _error("derived adapter-scoped source key already exists before reviewed registration")


def _verify_adapter_ancestry() -> None:
    if (
        pr95.DATASET_NAME,
        pr95.ADAPTER_SCOPE,
        pr95.ADAPTER_STATE,
        pr95.NEXT_REQUIRED_BOUNDARY,
    ) != (
        PR95_DATASET_NAME,
        PR95_ADAPTER_SCOPE,
        PR95_ADAPTER_STATE,
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER_VALIDATION",
    ):
        raise _error("PR95 adapter identity changed")
    if pr95.PARENT_SOURCE_KEY != PARENT_SOURCE_KEY or pr95.FUTURE_DERIVED_SOURCE_KEY != PROPOSED_SOURCE_KEY:
        raise _error("PR95 source-key scope changed")


def _verify_manifest(
    raw: bytes,
    manifest: FotMobDataMatchesCaptureManifest,
    *,
    raw_sha256: str,
    manifest_sha256: str,
    raw_size: int,
    observed_at: str,
) -> None:
    if type(raw) is not bytes or not isinstance(manifest, FotMobDataMatchesCaptureManifest):
        raise _error("exact PR85 capture input types changed")
    if (manifest.request_date, manifest.timezone, manifest.ccode3) != (REQUEST_DATE, TIMEZONE, CCODE3):
        raise _error("exact PR85 request identity changed")
    if sha256_bytes(raw) != raw_sha256 or manifest.raw_sha256 != raw_sha256:
        raise _error("exact PR85 raw lineage changed")
    if len(raw) != raw_size or manifest.raw_size != raw_size:
        raise _error("exact PR85 raw size changed")
    if sha256_data_matches_capture_manifest(manifest) != manifest_sha256:
        raise _error("exact PR85 manifest lineage changed")
    if serialize_utc(manifest.observed_at) != observed_at:
        raise _error("exact PR85 observation time changed")


def _qualified_projection_bytes(result: pr95.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult) -> bytes:
    return _canonical([item.to_dict() for item in result.qualified_scores])


def execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation(
    first_raw_json: bytes,
    first_manifest: FotMobDataMatchesCaptureManifest,
    second_raw_json: bytes,
    second_manifest: FotMobDataMatchesCaptureManifest,
) -> Mapping[str, Any]:
    """Execute PR95 on the exact preserved PR85 pair and return the frozen PR96 receipt."""

    _verify_adapter_ancestry()
    _verify_registry()
    _verify_manifest(
        first_raw_json,
        first_manifest,
        raw_sha256=FIRST_RAW_SHA256,
        manifest_sha256=FIRST_MANIFEST_SHA256,
        raw_size=FIRST_RAW_SIZE,
        observed_at=FIRST_OBSERVED_AT,
    )
    _verify_manifest(
        second_raw_json,
        second_manifest,
        raw_sha256=SECOND_RAW_SHA256,
        manifest_sha256=SECOND_MANIFEST_SHA256,
        raw_size=SECOND_RAW_SIZE,
        observed_at=SECOND_OBSERVED_AT,
    )
    delta = second_manifest.observed_at - first_manifest.observed_at
    microseconds = delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
    if microseconds != OBSERVATION_SEPARATION_MICROSECONDS:
        raise _error("exact PR85 observation separation changed")

    try:
        result = pr95.adapt_fotmob_data_matches_ordinary_ft_finished_scores(
            first_raw_json,
            first_manifest,
            second_raw_json,
            second_manifest,
        )
    except Exception as exc:
        raise _error("PR95 reusable adapter rejected the exact preserved evidence") from exc

    if result.pair_status is not pr95.AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES:
        raise _error("PR95 exact pair no longer qualifies")
    if result.terminal_candidate_union_count != TERMINAL_CANDIDATE_UNION_COUNT:
        raise _error("PR95 terminal candidate union count changed")
    if result.qualified_count != QUALIFIED_COUNT or len(result.qualified_scores) != QUALIFIED_COUNT:
        raise _error("PR95 exact qualified count changed")
    if dict(result.blocked_fixture_ids_by_status) != dict(BLOCKED_FIXTURE_IDS_BY_STATUS):
        raise _error("PR95 exact blocked-fixture disposition changed")
    if PENALTY_FIXTURE_ID in {item.fixture_id for item in result.qualified_scores}:
        raise _error("reviewed penalty fixture escaped into ordinary-FT output")
    anchor = next((item for item in result.qualified_scores if item.fixture_id == ORDINARY_ANCHOR_FIXTURE_ID), None)
    if anchor is None or (anchor.home_score, anchor.away_score) != (
        ORDINARY_ANCHOR_HOME_SCORE,
        ORDINARY_ANCHOR_AWAY_SCORE,
    ):
        raise _error("ordinary-FT audit anchor changed")
    if result.source_capability_registration_performed is not False:
        raise _error("PR95 adapter unexpectedly performed capability registration")
    if any(flag is not False for flag in result.safety.values()):
        raise _error("PR95 adapter safety boundary changed")

    adapter_bytes = pr95.canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_result_bytes(result)
    if hashlib.sha256(adapter_bytes).hexdigest() != ADAPTER_RESULT_SHA256 or len(adapter_bytes) != ADAPTER_RESULT_SIZE:
        raise _error("PR95 canonical adapter result changed")
    qualified_bytes = _qualified_projection_bytes(result)
    if hashlib.sha256(qualified_bytes).hexdigest() != QUALIFIED_SCORES_PROJECTION_SHA256:
        raise _error("PR95 qualified-score projection changed")

    expected = _expected()
    exact = _canonical(expected)
    if hashlib.sha256(exact).hexdigest() != RECEIPT_SHA256 or len(exact) != RECEIPT_SIZE:
        raise _error("PR96 canonical receipt identity changed")
    return _freeze(expected)


def canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes(
    value: Mapping[str, Any],
) -> bytes:
    if not isinstance(value, Mapping) or _plain(value) != _plain(_expected()):
        raise _error("receipt differs from the exact PR96 outcome")
    exact = _canonical(value)
    if hashlib.sha256(exact).hexdigest() != RECEIPT_SHA256 or len(exact) != RECEIPT_SIZE:
        raise _error("PR96 canonical receipt identity changed")
    return exact


def sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt(
    value: Mapping[str, Any],
) -> str:
    return hashlib.sha256(
        canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes(value)
    ).hexdigest()


__all__ = [
    "ADAPTER_RESULT_SHA256",
    "ADAPTER_RESULT_SIZE",
    "BLOCKED_FIXTURE_IDS_BY_STATUS",
    "DATASET_NAME",
    "EXECUTION_SCOPE",
    "EXECUTION_STATE",
    "NEXT_REQUIRED_BOUNDARY",
    "PENALTY_FIXTURE_ID",
    "PR95_ADAPTER_BLOB_SHA",
    "QUALIFIED_COUNT",
    "QUALIFIED_SCORES_PROJECTION_SHA256",
    "RECEIPT_SHA256",
    "RECEIPT_SIZE",
    "REPOSITORY_MAIN_SHA",
    "TERMINAL_CANDIDATE_UNION_COUNT",
    "FotMobDataMatchesOrdinaryFtFinishedScoreAdapterValidationError",
    "canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes",
    "execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation",
    "sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt",
]
