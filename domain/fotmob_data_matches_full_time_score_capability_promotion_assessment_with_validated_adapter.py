"""Reassess the frozen PR93 FotMob score capability after PR95/PR96 validation.

This boundary is evidence-only.  It proves that the reusable reviewed ordinary-FT
finished-score adapter required by PR93 now exists and that PR96 validated it on
the exact preserved PR85 evidence pair.  It may therefore qualify the separate
derived adapter-scoped source key for a later registry-registration boundary.

It does not mutate the source-capability registry, mutate the parent reviewed
catalog, prove historical coverage, or authorize model, probability, pricing,
selection, production, or betting use.
"""
from __future__ import annotations

import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_full_time_score_capability_promotion_assessment as pr94
import domain.fotmob_data_matches_full_time_score_capability_promotion_protocol as pr93
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as pr95
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter_validation as pr96
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = (
    "athena-fotmob-data-matches-full-time-score-capability-promotion-assessment-with-validated-adapter-v1"
)
ASSESSMENT_SCOPE = (
    "EXECUTE_PR93_SCOPED_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT_WITH_EXACT_PR95_ADAPTER_AND_PR96_VALIDATION_ONLY"
)
ASSESSMENT_STATE = "EXECUTED_QUALIFIED_FOR_DERIVED_SOURCE_CAPABILITY_REGISTRATION_NOT_REGISTERED"
REPOSITORY_MAIN_SHA = "1831c9d6d631cf249c40e4352959be1905b1c01e"
ASSESSED_REPOSITORY_TREE_SHA = "ba682efd2e90660dd9e40371ad5b135c1212a2b3"

PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"
PROPOSED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
REUSABLE_ADAPTER_MODULE_PATH = "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py"

PR93_PROTOCOL_BLOB_SHA = "27df60b90aa29273aeef4b8e9a51992c5c57cf9b"
PR93_PROTOCOL_SHA256 = "8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009"
PR93_PROTOCOL_SIZE = 6458
PR94_ASSESSMENT_BLOB_SHA = "e81be529acc5471e875d4c619e9f77e885217716"
PR94_ASSESSMENT_SHA256 = "adfe1a6e0103a65c30ed19026940bfb5474c63dc44328b7c632ea8dbe15d2eb5"
PR94_ASSESSMENT_SIZE = 4568
PR95_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
PR95_ADAPTER_STATE = "IMPLEMENTED_REUSABLE_PROSPECTIVE_GATE_NO_CAPABILITY_REGISTRATION"
PR96_VALIDATION_BLOB_SHA = "d6ad05c778669b976c4a475080da845cc8bf47cb"
PR96_RECEIPT_SHA256 = "09dd9fdff1eddb7b421e968c8de93262b09ce526adeb3d3b95050ddf1f2d4562"
PR96_RECEIPT_SIZE = 3610
PR96_ADAPTER_RESULT_SHA256 = "7e3fcb2c8a4fa8f883ec7dcac2fd15ea8d2f1aa359c5c5f42ab7eaf604bdce27"
PR96_QUALIFIED_SCORES_PROJECTION_SHA256 = (
    "ffdb20556808a1a6459d959b050e3aa5780f3c017d6971adf0c17a3c91ce03ab"
)
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"

TERMINAL_CANDIDATE_UNION_COUNT = 29
QUALIFIED_ORDINARY_FT_COUNT = 28
EXCLUDED_PENALTY_COUNT = 1
EXCLUDED_PENALTY_FIXTURE_ID = 5844873
PRIMARY_STATUS = "QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION"
PROMOTION_MODE = "REGISTER_NEW_DERIVED_ADAPTER_SCOPED_SOURCE_KEY_DO_NOT_MUTATE_PARENT"
PROMOTION_SCOPE_RULE = (
    "CONFIRMED_FULL_TIME_SCORE_MEANS_ONLY_PR92_QUALIFIED_SOURCE_REPORTED_FINISHED_SCORE_FOR_EXACT_ORDINARY_FT_GATE"
)
NEXT_REQUIRED_BOUNDARY = (
    "REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_CAPABILITY"
)

_PARENT_CAPABILITIES = types.MappingProxyType(
    {
        "full_time_score": "NOT_CAPTURED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
)
_PROPOSED_CAPABILITIES = types.MappingProxyType(
    {
        "full_time_score": "CONFIRMED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_capability_registry_update_authorized",
        "source_capability_registry_update_performed",
        "parent_source_capability_mutation_authorized",
        "global_fotmob_full_time_score_capability_authorized",
        "penalty_score_semantics_qualified",
        "regulation_time_score_semantics_qualified",
        "extra_time_score_semantics_qualified",
        "bookmaker_settlement_semantics_qualified",
        "status_reason_semantics_globally_qualified",
        "historical_coverage_qualified",
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

ASSESSMENT_SHA256 = "edec152475a4c964084cdee1ba7c6a7385457297b63acf4a81e683dc74e99e03"
ASSESSMENT_SIZE = 5369


class FotMobDataMatchesFullTimeScoreCapabilityPromotionValidatedAdapterAssessmentError(ValueError):
    """Raised when the PR97 assessment or one of its frozen premises drifts."""


def _error(
    message: str,
) -> FotMobDataMatchesFullTimeScoreCapabilityPromotionValidatedAdapterAssessmentError:
    return FotMobDataMatchesFullTimeScoreCapabilityPromotionValidatedAdapterAssessmentError(message)


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
        raise _error("PR97 assessment serialization failed") from exc


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _capability_dict(capability: Any) -> dict[str, str]:
    return {
        "full_time_score": capability.full_time_score.value,
        "half_time_score": capability.half_time_score.value,
        "event_timestamps": capability.event_timestamps.value,
        "reliable_fixture_identity": capability.reliable_fixture_identity.value,
        "historical_coverage": capability.historical_coverage.value,
        "freshness_metadata": capability.freshness_metadata.value,
    }


def _gate_results() -> tuple[Mapping[str, str], ...]:
    return (
        types.MappingProxyType(
            {
                "gate_id": "PR93_PROTOCOL_ANCESTRY",
                "outcome": "PASS",
                "reason": "EXACT_PR93_CANONICAL_PROTOCOL_REVALIDATED",
            }
        ),
        types.MappingProxyType(
            {
                "gate_id": "PARENT_SOURCE_CAPABILITY",
                "outcome": "PASS",
                "reason": "PARENT_REVIEWED_CATALOG_REMAINS_IDENTITY_ONLY_AND_UNCHANGED",
            }
        ),
        types.MappingProxyType(
            {
                "gate_id": "PROPOSED_SOURCE_KEY_ABSENCE",
                "outcome": "PASS",
                "reason": "DERIVED_SOURCE_KEY_IS_ABSENT_BEFORE_REGISTRATION",
            }
        ),
        types.MappingProxyType(
            {
                "gate_id": "REUSABLE_PROSPECTIVE_SCORE_ADAPTER",
                "outcome": "PASS",
                "reason": "EXACT_PR95_REUSABLE_ADAPTER_EXISTS_AT_FROZEN_PATH_AND_SCOPE",
            }
        ),
        types.MappingProxyType(
            {
                "gate_id": "REUSABLE_ADAPTER_VALIDATION",
                "outcome": "PASS",
                "reason": "EXACT_PR96_VALIDATION_QUALIFIES_28_ORDINARY_FT_SCORES_AND_BLOCKS_PENALTY_FIXTURE_5844873",
            }
        ),
        types.MappingProxyType(
            {
                "gate_id": "CAPABILITY_SCOPE_AND_PENALTY_EXCLUSION",
                "outcome": "PASS",
                "reason": "PROPOSED_CAPABILITY_MATCHES_PR93_AND_EXCLUDES_PENALTY_UNREVIEWED_REASON_AND_SETTLEMENT_SEMANTICS",
            }
        ),
        types.MappingProxyType(
            {
                "gate_id": "DERIVED_CAPABILITY_REGISTRATION_QUALIFICATION",
                "outcome": "PASS",
                "reason": "ALL_FROZEN_PR93_ASSESSMENT_REQUIREMENTS_NOW_PASS_WITH_VALIDATED_REUSABLE_ADAPTER",
            }
        ),
        types.MappingProxyType(
            {
                "gate_id": "SOURCE_CAPABILITY_REGISTRY_UPDATE",
                "outcome": "NOT_PERFORMED",
                "reason": "REGISTRY_MUTATION_IS_RESERVED_FOR_THE_NEXT_SEPARATE_REVIEWED_BOUNDARY",
            }
        ),
    )


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "assessment_scope": ASSESSMENT_SCOPE,
        "assessment_state": ASSESSMENT_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "parent_source_key": PARENT_SOURCE_KEY,
        "proposed_source_key": PROPOSED_SOURCE_KEY,
        "pr93_protocol_blob_sha": PR93_PROTOCOL_BLOB_SHA,
        "pr93_protocol_sha256": PR93_PROTOCOL_SHA256,
        "pr93_protocol_size": PR93_PROTOCOL_SIZE,
        "pr94_assessment_blob_sha": PR94_ASSESSMENT_BLOB_SHA,
        "pr94_assessment_sha256": PR94_ASSESSMENT_SHA256,
        "pr94_assessment_size": PR94_ASSESSMENT_SIZE,
        "pr95_adapter_blob_sha": PR95_ADAPTER_BLOB_SHA,
        "pr95_adapter_state": PR95_ADAPTER_STATE,
        "pr96_validation_blob_sha": PR96_VALIDATION_BLOB_SHA,
        "pr96_receipt_sha256": PR96_RECEIPT_SHA256,
        "pr96_receipt_size": PR96_RECEIPT_SIZE,
        "pr96_adapter_result_sha256": PR96_ADAPTER_RESULT_SHA256,
        "pr96_qualified_scores_projection_sha256": PR96_QUALIFIED_SCORES_PROJECTION_SHA256,
        "source_capabilities_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "reusable_adapter_module_path": REUSABLE_ADAPTER_MODULE_PATH,
        "terminal_candidate_union_count": TERMINAL_CANDIDATE_UNION_COUNT,
        "qualified_ordinary_ft_count": QUALIFIED_ORDINARY_FT_COUNT,
        "excluded_penalty_count": EXCLUDED_PENALTY_COUNT,
        "excluded_penalty_fixture_id": EXCLUDED_PENALTY_FIXTURE_ID,
        "primary_status": PRIMARY_STATUS,
        "promotion_mode": PROMOTION_MODE,
        "promotion_scope_rule": PROMOTION_SCOPE_RULE,
        "parent_capabilities": dict(_PARENT_CAPABILITIES),
        "proposed_capabilities": dict(_PROPOSED_CAPABILITIES),
        "reusable_adapter_implemented": True,
        "reusable_adapter_validation_qualified": True,
        "proposed_source_key_present_before_registration": False,
        "parent_source_capability_matches_protocol": True,
        "scope_and_penalty_exclusion_match_protocol": True,
        "registration_qualified": True,
        "registry_update_performed": False,
        "gate_results": [dict(item) for item in _gate_results()],
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
        "assessed_repository_tree_sha": ASSESSED_REPOSITORY_TREE_SHA,
    }


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    out = dict(value)
    out["parent_capabilities"] = types.MappingProxyType(dict(value["parent_capabilities"]))
    out["proposed_capabilities"] = types.MappingProxyType(dict(value["proposed_capabilities"]))
    out["gate_results"] = tuple(types.MappingProxyType(dict(item)) for item in value["gate_results"])
    out["safety"] = types.MappingProxyType(dict(value["safety"]))
    return types.MappingProxyType(out)


def _verify_upstream() -> None:
    if (pr93.PROTOCOL_SHA256, pr93.PROTOCOL_SIZE) != (PR93_PROTOCOL_SHA256, PR93_PROTOCOL_SIZE):
        raise _error("PR93 protocol canonical constants changed")
    protocol = pr93.build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    protocol_bytes = pr93.canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(
        protocol
    )
    if hashlib.sha256(protocol_bytes).hexdigest() != PR93_PROTOCOL_SHA256 or len(protocol_bytes) != PR93_PROTOCOL_SIZE:
        raise _error("PR93 canonical protocol identity changed")
    if protocol.parent_source_key != PARENT_SOURCE_KEY or protocol.proposed_source_key != PROPOSED_SOURCE_KEY:
        raise _error("PR93 source-key scope changed")
    if protocol.reusable_adapter_module_path != REUSABLE_ADAPTER_MODULE_PATH:
        raise _error("PR93 reusable adapter path changed")
    if protocol.promotion_mode != PROMOTION_MODE or protocol.promotion_scope_rule != PROMOTION_SCOPE_RULE:
        raise _error("PR93 promotion scope changed")
    if dict(protocol.parent_required_capabilities) != dict(_PARENT_CAPABILITIES):
        raise _error("PR93 parent capability contract changed")
    if dict(protocol.proposed_capabilities) != dict(_PROPOSED_CAPABILITIES):
        raise _error("PR93 proposed capability contract changed")
    if PRIMARY_STATUS not in protocol.status_vocabulary:
        raise _error("PR93 qualification status vocabulary changed")

    if (pr94.ASSESSMENT_SHA256, pr94.ASSESSMENT_SIZE) != (
        PR94_ASSESSMENT_SHA256,
        PR94_ASSESSMENT_SIZE,
    ):
        raise _error("PR94 historical assessment identity changed")
    old_assessment = pr94.build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    old_bytes = pr94.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(
        old_assessment
    )
    if hashlib.sha256(old_bytes).hexdigest() != PR94_ASSESSMENT_SHA256 or len(old_bytes) != PR94_ASSESSMENT_SIZE:
        raise _error("PR94 historical assessment canonical identity changed")
    if old_assessment.primary_status != "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED":
        raise _error("PR94 historical blocker changed")
    if old_assessment.registration_qualified is not False or old_assessment.registry_update_performed is not False:
        raise _error("PR94 historical fail-closed disposition changed")

    if pr95.ADAPTER_STATE != PR95_ADAPTER_STATE:
        raise _error("PR95 reusable adapter state changed")
    if pr95.PARENT_SOURCE_KEY != PARENT_SOURCE_KEY or pr95.FUTURE_DERIVED_SOURCE_KEY != PROPOSED_SOURCE_KEY:
        raise _error("PR95 source-key scope changed")
    if pr95.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER_VALIDATION"
    ):
        raise _error("PR95 validation boundary changed")

    if (pr96.RECEIPT_SHA256, pr96.RECEIPT_SIZE) != (PR96_RECEIPT_SHA256, PR96_RECEIPT_SIZE):
        raise _error("PR96 validation receipt identity changed")
    if pr96.PR95_ADAPTER_BLOB_SHA != PR95_ADAPTER_BLOB_SHA:
        raise _error("PR96 no longer binds the exact PR95 adapter blob")
    if pr96.ADAPTER_RESULT_SHA256 != PR96_ADAPTER_RESULT_SHA256:
        raise _error("PR96 adapter-result identity changed")
    if pr96.QUALIFIED_SCORES_PROJECTION_SHA256 != PR96_QUALIFIED_SCORES_PROJECTION_SHA256:
        raise _error("PR96 qualified-score projection changed")
    if (
        pr96.TERMINAL_CANDIDATE_UNION_COUNT,
        pr96.QUALIFIED_COUNT,
        pr96.PENALTY_FIXTURE_ID,
    ) != (
        TERMINAL_CANDIDATE_UNION_COUNT,
        QUALIFIED_ORDINARY_FT_COUNT,
        EXCLUDED_PENALTY_FIXTURE_ID,
    ):
        raise _error("PR96 candidate/qualified/penalty evidence changed")
    if pr96.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT_WITH_VALIDATED_ADAPTER"
    ):
        raise _error("PR96 next boundary changed")

    parent = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    if parent is None:
        raise _error("parent reviewed FotMob catalog capability is missing")
    if _capability_dict(parent) != dict(_PARENT_CAPABILITIES):
        raise _error("parent reviewed catalog capability drifted")
    if parent.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("parent full_time_score must remain NOT_CAPTURED")
    if parent.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("parent reliable fixture identity must remain CONFIRMED")
    if parent.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("parent historical coverage must remain UNKNOWN")
    if PROPOSED_SOURCE_KEY in SOURCE_CAPABILITY_REGISTRY:
        raise _error("derived source key already exists before the separate registration boundary")


def build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter(
) -> Mapping[str, Any]:
    """Return the immutable PR97 assessment after revalidating every frozen premise."""

    _verify_upstream()
    expected = _payload()
    exact = _canonical(expected)
    if hashlib.sha256(exact).hexdigest() != ASSESSMENT_SHA256 or len(exact) != ASSESSMENT_SIZE:
        raise _error("PR97 canonical assessment identity changed")
    return _freeze(expected)


def canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(
    value: Mapping[str, Any],
) -> bytes:
    if not isinstance(value, Mapping) or _plain(value) != _plain(_payload()):
        raise _error("assessment differs from the exact PR97 qualified outcome")
    exact = _canonical(value)
    if hashlib.sha256(exact).hexdigest() != ASSESSMENT_SHA256 or len(exact) != ASSESSMENT_SIZE:
        raise _error("PR97 canonical assessment identity changed")
    return exact


def sha256_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter(
    value: Mapping[str, Any],
) -> str:
    return hashlib.sha256(
        canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(
            value
        )
    ).hexdigest()


__all__ = [
    "ASSESSED_REPOSITORY_TREE_SHA",
    "ASSESSMENT_SCOPE",
    "ASSESSMENT_SHA256",
    "ASSESSMENT_SIZE",
    "ASSESSMENT_STATE",
    "DATASET_NAME",
    "EXCLUDED_PENALTY_COUNT",
    "EXCLUDED_PENALTY_FIXTURE_ID",
    "NEXT_REQUIRED_BOUNDARY",
    "PARENT_SOURCE_KEY",
    "PRIMARY_STATUS",
    "PROPOSED_SOURCE_KEY",
    "QUALIFIED_ORDINARY_FT_COUNT",
    "REPOSITORY_MAIN_SHA",
    "TERMINAL_CANDIDATE_UNION_COUNT",
    "FotMobDataMatchesFullTimeScoreCapabilityPromotionValidatedAdapterAssessmentError",
    "build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter",
    "canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes",
    "sha256_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter",
]
