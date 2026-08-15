"""Pre-register source-history completeness for the reviewed FotMob ordinary-FT score source.

PR #99 binds the frozen PR #81 source-history completeness contract to the
separate derived FotMob ordinary-FT finished-score capability registered by
PR #98.  The derived source now has reviewed source-reported finished-score
semantics, but historical coverage remains UNKNOWN.  This protocol therefore
freezes the next evidence boundary without authorizing source history,
successor features, modelling, probability inference, pricing, selection,
production, or betting.
"""
from __future__ import annotations

import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter as pr97
import domain.fotmob_data_matches_full_time_score_capability_promotion_protocol as pr93
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter_validation as pr96
import domain.prospective_successor_source_history_completeness_protocol as pr81
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_ORDINARY_FT_FINISHED_SCORE_SOURCE_HISTORY_COMPLETENESS_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_REVIEWED_DERIVED_ORDINARY_FT_SCORE_SOURCE_HISTORY_COMPLETENESS_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN"
REPOSITORY_MAIN_SHA = "db8bc1eb1b4a5b35751d70a14e0fe07157fe149f"

PR81_PROTOCOL_SHA256 = "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
PR81_PROTOCOL_SIZE = 4223
PR93_PROTOCOL_SHA256 = "8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009"
PR93_PROTOCOL_SIZE = 6458
PR96_RECEIPT_SHA256 = "09dd9fdff1eddb7b421e968c8de93262b09ce526adeb3d3b95050ddf1f2d4562"
PR96_RECEIPT_SIZE = 3610
PR97_ASSESSMENT_SHA256 = "edec152475a4c964084cdee1ba7c6a7385457297b63acf4a81e683dc74e99e03"
PR97_ASSESSMENT_SIZE = 5369
PR98_SOURCE_CAPABILITIES_BLOB_SHA = "37b919eb5efa0c931e1bf10d3f845865567ef0c4"

DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

_DERIVED_SOURCE_FACTS = types.MappingProxyType(
    {
        "full_time_score": "CONFIRMED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
)
_PARENT_SOURCE_FACTS = types.MappingProxyType(
    {
        "full_time_score": "NOT_CAPTURED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
)

SCORE_SEMANTIC_SCOPE_RULE = (
    "CONFIRMED_FULL_TIME_SCORE_MEANS_ONLY_PR92_QUALIFIED_SOURCE_REPORTED_FINISHED_SCORE_FOR_EXACT_ORDINARY_FT_GATE"
)
PENALTY_EXCLUSION_RULE = (
    "PENALTY_OR_OTHER_UNREVIEWED_REASON_FIXTURES_MUST_NOT_ENTER_DERIVED_CAPABILITY"
)
SEMANTIC_EXCLUSION_RULE = (
    "DO_NOT_INFER_REGULATION_TIME_EXTRA_TIME_PENALTY_SCORE_BOOKMAKER_SETTLEMENT_OR_GLOBAL_STATUS_REASON_SEMANTICS"
)
HISTORICAL_COVERAGE_RULE = "HISTORICAL_COVERAGE_REMAINS_UNKNOWN"

DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS = (
    "EVERY_ADMITTED_RESULT_MUST_PASS_THE_REUSABLE_REVIEWED_ORDINARY_FT_FINISHED_SCORE_ADAPTER",
    "ANY_IN_SCOPE_FINISHED_FIXTURE_OUTSIDE_THE_ORDINARY_FT_GATE_BLOCKS_COMPLETENESS_UNLESS_SEPARATELY_REVIEWED",
    "DERIVED_SCORE_CAPABILITY_DOES_NOT_PROVE_HISTORICAL_COVERAGE_OR_DAILY_CAPTURE_COMPLETENESS",
    "DO_NOT_SUBSTITUTE_LEGACY_FOTMOB_HISTORICAL_OR_ANY_OTHER_SOURCE_FOR_THE_REGISTERED_DERIVED_SOURCE",
)

QUALIFICATION_STATUS_VOCABULARY = (
    "QUALIFIED_COMPLETE_REVIEWED_ORDINARY_FT_HISTORY",
    "BLOCKED_DERIVED_SOURCE_CAPABILITY_DRIFT",
    "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
    "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
    "BLOCKED_LEAGUE_MAPPING_UNPROVEN",
    "BLOCKED_REQUIRED_DATE_GAP",
    "BLOCKED_RESULT_EVIDENCE_GAP",
    "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW",
    "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT",
)
CURRENT_PRE_EXECUTION_DISPOSITION = "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_ORDINARY_FT_FINISHED_SCORE_SOURCE_HISTORY_COMPLETENESS_ASSESSMENT"
)

_SAFETY_KEYS = frozenset(
    {
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

PROTOCOL_SHA256 = "ac922634b999a4e8bdb186df3ac2fc1291c130aca405956ea611c5cc582d9e15"
PROTOCOL_SIZE = 5048


class FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessProtocolError(ValueError):
    """Raised when the PR99 protocol or reviewed ancestry drifts."""


def _error(message: str) -> FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessProtocolError:
    return FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessProtocolError(message)


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
        raise _error("PR99 source-history completeness protocol serialization failed") from exc


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


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr81_protocol_sha256": PR81_PROTOCOL_SHA256,
        "pr81_protocol_size": PR81_PROTOCOL_SIZE,
        "pr93_protocol_sha256": PR93_PROTOCOL_SHA256,
        "pr93_protocol_size": PR93_PROTOCOL_SIZE,
        "pr96_receipt_sha256": PR96_RECEIPT_SHA256,
        "pr96_receipt_size": PR96_RECEIPT_SIZE,
        "pr97_assessment_sha256": PR97_ASSESSMENT_SHA256,
        "pr97_assessment_size": PR97_ASSESSMENT_SIZE,
        "pr98_source_capabilities_blob_sha": PR98_SOURCE_CAPABILITIES_BLOB_SHA,
        "derived_source_key": DERIVED_SOURCE_KEY,
        "parent_source_key": PARENT_SOURCE_KEY,
        "derived_source_facts": dict(_DERIVED_SOURCE_FACTS),
        "parent_source_facts": dict(_PARENT_SOURCE_FACTS),
        "score_semantic_scope_rule": SCORE_SEMANTIC_SCOPE_RULE,
        "penalty_exclusion_rule": PENALTY_EXCLUSION_RULE,
        "semantic_exclusion_rule": SEMANTIC_EXCLUSION_RULE,
        "historical_coverage_rule": HISTORICAL_COVERAGE_RULE,
        "frozen_model_league_codes": list(pr81.FROZEN_MODEL_LEAGUE_CODES),
        "elo_initialization_semantics": pr81.ELO_INITIALIZATION_SEMANTICS,
        "pr81_history_adapter_requirements": list(pr81.HISTORY_ADAPTER_REQUIREMENTS),
        "pr81_completeness_requirements": list(pr81.COMPLETENESS_REQUIREMENTS),
        "derived_source_additional_requirements": list(DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS),
        "qualification_status_vocabulary": list(QUALIFICATION_STATUS_VOCABULARY),
        "current_pre_execution_disposition": CURRENT_PRE_EXECUTION_DISPOSITION,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return types.MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _verify_upstream() -> None:
    if (pr81.PROTOCOL_SHA256, pr81.PROTOCOL_SIZE) != (PR81_PROTOCOL_SHA256, PR81_PROTOCOL_SIZE):
        raise _error("PR81 source-history completeness protocol identity changed")
    pr81_value = pr81.build_prospective_successor_source_history_completeness_protocol()
    pr81_exact = pr81.canonical_prospective_successor_source_history_completeness_protocol_bytes(pr81_value)
    if hashlib.sha256(pr81_exact).hexdigest() != PR81_PROTOCOL_SHA256 or len(pr81_exact) != PR81_PROTOCOL_SIZE:
        raise _error("PR81 canonical source-history completeness protocol changed")

    if (pr93.PROTOCOL_SHA256, pr93.PROTOCOL_SIZE) != (PR93_PROTOCOL_SHA256, PR93_PROTOCOL_SIZE):
        raise _error("PR93 score-capability promotion protocol identity changed")
    pr93_value = pr93.build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    pr93_exact = pr93.canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(pr93_value)
    if hashlib.sha256(pr93_exact).hexdigest() != PR93_PROTOCOL_SHA256 or len(pr93_exact) != PR93_PROTOCOL_SIZE:
        raise _error("PR93 canonical score-capability promotion protocol changed")

    if (pr96.RECEIPT_SHA256, pr96.RECEIPT_SIZE) != (PR96_RECEIPT_SHA256, PR96_RECEIPT_SIZE):
        raise _error("PR96 reusable-adapter validation receipt identity changed")
    if (pr96.TERMINAL_CANDIDATE_UNION_COUNT, pr96.QUALIFIED_COUNT, pr96.PENALTY_FIXTURE_ID) != (29, 28, 5844873):
        raise _error("PR96 ordinary-FT validation evidence changed")

    if (pr97.ASSESSMENT_SHA256, pr97.ASSESSMENT_SIZE) != (PR97_ASSESSMENT_SHA256, PR97_ASSESSMENT_SIZE):
        raise _error("PR97 capability assessment identity changed")
    pr97_value = pr97.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    pr97_exact = pr97.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(pr97_value)
    if hashlib.sha256(pr97_exact).hexdigest() != PR97_ASSESSMENT_SHA256 or len(pr97_exact) != PR97_ASSESSMENT_SIZE:
        raise _error("PR97 canonical capability assessment changed")
    if pr97.PRIMARY_STATUS != "QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION":
        raise _error("PR97 no longer qualifies the derived score capability")

    if pr93.PROPOSED_SOURCE_KEY != DERIVED_SOURCE_KEY or pr93.PARENT_SOURCE_KEY != PARENT_SOURCE_KEY:
        raise _error("PR93 source-key scope changed")
    if pr93.PROMOTION_SCOPE_RULE != SCORE_SEMANTIC_SCOPE_RULE:
        raise _error("PR93 score semantic scope changed")
    if pr93.PENALTY_EXCLUSION_RULE != PENALTY_EXCLUSION_RULE:
        raise _error("PR93 penalty exclusion rule changed")
    if pr93.SEMANTIC_EXCLUSION_RULE != SEMANTIC_EXCLUSION_RULE:
        raise _error("PR93 semantic exclusion rule changed")
    if pr93.HISTORICAL_COVERAGE_RULE != HISTORICAL_COVERAGE_RULE:
        raise _error("PR93 historical coverage rule changed")

    parent = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    derived = SOURCE_CAPABILITY_REGISTRY.get(DERIVED_SOURCE_KEY)
    if parent is None or derived is None:
        raise _error("required reviewed FotMob source capability is missing")
    if _capability_dict(parent) != dict(_PARENT_SOURCE_FACTS):
        raise _error("parent reviewed catalog capability drifted")
    if _capability_dict(derived) != dict(_DERIVED_SOURCE_FACTS):
        raise _error("derived ordinary-FT score capability drifted")
    if tuple(derived.evidence) != tuple(pr93.PROPOSED_EVIDENCE) or derived.notes != pr93.PROPOSED_NOTES:
        raise _error("derived score capability evidence or notes drifted from PR93")
    if derived.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("derived full_time_score must remain CONFIRMED")
    if derived.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("derived reliable fixture identity must remain CONFIRMED")
    if derived.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("derived historical coverage must remain UNKNOWN at pre-registration")
    if parent.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("parent full_time_score must remain NOT_CAPTURED")
    if DERIVED_SOURCE_KEY == "fotmob_historical":
        raise _error("legacy FotMob historical source cannot substitute for the reviewed derived source")


def build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol() -> Mapping[str, Any]:
    """Return the immutable PR99 protocol after revalidating all frozen premises."""

    _verify_upstream()
    expected = _payload()
    exact = _canonical(expected)
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR99 canonical source-history completeness protocol identity changed")
    return _freeze(expected)


def canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(
    value: Mapping[str, Any],
) -> bytes:
    if not isinstance(value, Mapping) or _plain(value) != _plain(_payload()):
        raise _error("source-history completeness protocol differs from the exact PR99 contract")
    exact = _canonical(value)
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR99 canonical source-history completeness protocol identity changed")
    return exact


def sha256_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol(
    value: Mapping[str, Any],
) -> str:
    return hashlib.sha256(
        canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(value)
    ).hexdigest()


__all__ = [
    "CURRENT_PRE_EXECUTION_DISPOSITION",
    "DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS",
    "DERIVED_SOURCE_KEY",
    "HISTORICAL_COVERAGE_RULE",
    "NEXT_REQUIRED_BOUNDARY",
    "PARENT_SOURCE_KEY",
    "PENALTY_EXCLUSION_RULE",
    "PR98_SOURCE_CAPABILITIES_BLOB_SHA",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "QUALIFICATION_STATUS_VOCABULARY",
    "REPOSITORY_MAIN_SHA",
    "SCORE_SEMANTIC_SCOPE_RULE",
    "SEMANTIC_EXCLUSION_RULE",
    "FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessProtocolError",
    "build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol",
    "canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes",
    "sha256_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol",
]
