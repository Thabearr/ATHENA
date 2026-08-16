"""Pre-register historical FotMob source-history completeness and materialization.

PR #118 reconciles the frozen PR #81/PR #99 completeness contracts with the
PR #117 campaign-specific historical adapter qualification.  It freezes the
next execution boundary only.  It does not prove completeness, materialize
history rows, mutate source capabilities, authorize PR #80 input, or create
model, probability, pricing, selection, production, or BET authority.
"""
from __future__ import annotations

import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_historical_source_history_adapter_qualification as pr117
import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_protocol as pr99
import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.fotmob_source_history_special_result_semantics_qualification as pr110
import domain.prospective_successor_feature_construction_candidate as pr80
import domain.prospective_successor_source_history_completeness_protocol as pr81
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_PROTOCOL_V1"
PROTOCOL_SCOPE = (
    "PRE_REGISTERED_FROZEN_CAMPAIGN_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_ONLY"
)
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN"
REPOSITORY_MAIN_SHA = "7e0e43852ff6527021de6ece52394b44bf222234"

PR81_PROTOCOL_SHA256 = "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
PR81_PROTOCOL_SIZE = 4_223
PR99_PROTOCOL_SHA256 = "edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87"
PR99_PROTOCOL_SIZE = 5_741
PR110_RECEIPT_SHA256 = "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
PR112_RECEIPT_SHA256 = "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
PR114_RECEIPT_SHA256 = "fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110"
PR117_RECEIPT_SHA256 = "a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020"
PR117_RECEIPT_SIZE = 5_081
PR117_ORDINARY_FT_PROJECTION_SHA256 = (
    "eddb7f5b58eb3cb92087dc7bf57a45a270aebabce38641cd3b4ffc2277d67ed3"
)
PR117_ORDINARY_FT_PROJECTION_SIZE = 22_080_831
PR80_CONSTRUCTION_SPEC_SHA256 = (
    "75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7"
)
PR80_CONSTRUCTION_SPEC_SIZE = 2_330

SOURCE_NAMESPACE = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
ARTIFACT_ID = 9_249_856_559
ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61_886_753
RESEARCH_CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
RESEARCH_CACHE_SIZE = 61_881_610
HISTORICAL_REQUEST_DATE_START = "2020-08-01"
HISTORICAL_REQUEST_DATE_END = "2026-08-14"
REQUEST_TIMEZONE = "UTC"
REQUEST_CCODE3 = "NGA"
SOURCE_LOCAL_TIME_BASIS = "Europe/Oslo"

FROZEN_FAMILY_REFERENCE_FLOORS = types.MappingProxyType({
    "B1": "2020-08-08", "D1": "2020-09-18", "E0": "2020-09-12",
    "F1": "2020-08-21", "G1": "2020-09-11", "I1": "2020-09-19",
    "N1": "2020-09-12", "P1": "2020-09-18", "SC0": "2020-08-01",
    "SP1": "2020-09-12", "T1": "2020-09-11",
})
ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE = types.MappingProxyType({
    "B1": 1933, "D1": 1835, "E0": 2280, "F1": 2056, "G1": 1431,
    "I1": 2280, "N1": 1865, "P1": 1846, "SC0": 1380, "SP1": 2280,
    "T1": 2140,
})
SPECIAL_STATE_OCCURRENCE_COUNTS = types.MappingProxyType({
    "ABANDONED": 20, "AFTER_EXTRA_TIME": 3, "AFTER_PENALTIES": 3,
    "AWARDED_WIN": 26, "CANCELLED": 11, "POSTPONED": 241,
})

CONTRACT_RECONCILIATION_RULES = (
    "PR81_SOURCE_HISTORY_COMPLETENESS_REQUIREMENTS_REMAIN_AUTHORITATIVE_AND_ARE_NOT_REWRITTEN",
    "PR99_PROSPECTIVE_DERIVED_SCORE_SOURCE_COMPLETENESS_PROTOCOL_REMAINS_UNCHANGED_FOR_PROSPECTIVE_USE",
    "FOR_THE_EXACT_FROZEN_PR105_CAMPAIGN_ONLY_THE_PR117_QUALIFIED_HISTORICAL_ADAPTER_IS_THE_REVIEWED_RESULT_ADAPTER_FOR_HISTORICAL_COMPLETENESS_AND_MATERIALIZATION",
    "THE_HISTORICAL_ADAPTER_BRIDGE_DOES_NOT_MUTATE_THE_PROSPECTIVE_ADAPTER_OR_DERIVED_SOURCE_CAPABILITY",
    "THE_ELEVEN_FROZEN_MODEL_FAMILIES_ARE_ONLY_THE_CURRENT_HISTORICAL_MODEL_UNIVERSE_NOT_ATHENAS_COMPLETE_COMPETITION_UNIVERSE",
)
COMPLETENESS_RULES = (
    "USE_ONLY_THE_EXACT_PR117_QUALIFIED_FROZEN_CAMPAIGN_AND_RECONSTRUCT_ITS_ORDINARY_FT_PROJECTION_WITHOUT_NETWORK_REACQUISITION",
    "REQUIRE_ALL_2205_REQUEST_DATES_FROM_2020_08_01_THROUGH_2026_08_14_WITH_EXACTLY_TWO_CANONICAL_CAPTURE_MANIFESTS_PER_DATE_TIMEZONE_UTC_AND_CCODE3_NGA",
    "REQUIRE_THE_EXACT_PR114_PER_FAMILY_ELO_INITIALIZATION_FLOORS_AND_PRESERVE_ALL_PRE_FLOOR_OBSERVATIONS_AS_EVIDENCE_ONLY",
    "REQUIRE_ALL_21640_TARGET_FAMILY_FIXTURE_DATE_OCCURRENCES_TO_CLOSE_EXACTLY_AS_21336_PR117_QUALIFIED_ORDINARY_FT_PLUS_304_PR110_REVIEWED_SPECIAL_STATE_OCCURRENCES",
    "EVERY_ORDINARY_FT_MATERIALIZATION_CANDIDATE_MUST_HAVE_FINAL_RESULT_EVIDENCE_OBSERVED_STRICTLY_AFTER_KICKOFF",
    "EVERY_IN_SCOPE_SPECIAL_STATE_MUST_RETAIN_PR110_SEMANTICS_AND_PR112_CHRONOLOGY_DISPOSITION_AND_MUST_NOT_BE_SILENTLY_DROPPED",
    "REQUIRE_ZERO_DUPLICATE_ORDINARY_FIXTURE_IDENTITIES_ZERO_SAME_TEAM_SAME_KICKOFF_AMBIGUITY_AND_ZERO_UNRESOLVED_SOURCE_SCOPED_TEAM_IDENTITY_CONFLICT",
    "REQUIRE_SOURCE_LOCAL_AND_UTC_ORDERING_TO_AGREE_FOR_THE_MATERIALIZABLE_HISTORY_CORPUS",
    "REQUIRE_EVERY_MATERIALIZABLE_ROW_REQUEST_DATE_TO_EQUAL_THE_UTC_CALENDAR_DATE_OF_ITS_CANONICAL_KICKOFF",
    "PROVE_DAILY_CAPTURE_COVERAGE_THROUGH_THE_REQUIRED_TARGET_DATE_BEFORE_ANY_TARGET_SPECIFIC_HISTORY_CAN_BE_CALLED_COMPLETE",
    "A_TARGET_REQUIRING_ANY_REQUEST_DATE_AFTER_2026_08_14_IS_OUTSIDE_THIS_FROZEN_COMPLETENESS_ENVELOPE_UNTIL_A_SEPARATELY_REVIEWED_CONTIGUOUS_EXTENSION_EXISTS",
)
MATERIALIZATION_RULES = (
    "ONLY_THE_21326_PR117_ORDINARY_FT_OCCURRENCES_ON_OR_AFTER_THEIR_PR114_FAMILY_FLOOR_MAY_BECOME_HISTORICAL_MATERIALIZATION_ROWS_AFTER_POSITIVE_COMPLETENESS_EXECUTION",
    "THE_10_PRE_FLOOR_ORDINARY_FT_OCCURRENCES_REMAIN_EVIDENCE_ONLY_AND_MUST_NEVER_SEED_ELO_FORM_FATIGUE_OR_PR80_HISTORY",
    "THE_304_REVIEWED_SPECIAL_STATE_OCCURRENCES_REMAIN_EVIDENCE_AND_DISPOSITION_ONLY_AND_MUST_NEVER_BE_MATERIALIZED_AS_ORDINARY_REGULATION_TIME_RESULTS",
    "SOURCE_NAMESPACE_IS_EXACTLY_FOTMOB_DATA_MATCHES_REVIEWED_ORDINARY_FT_FINISHED_SCORE_AND_FIXTURE_AND_TEAM_IDENTIFIERS_ARE_EXACT_DECIMAL_STRINGS_OF_POSITIVE_FOTMOB_SOURCE_IDS",
    "SOURCE_LOCAL_KICKOFF_IS_DERIVED_FROM_CANONICAL_KICKOFF_UTC_USING_EUROPE_OSLO_AND_THEN_MADE_NAIVE_ONLY_FOR_PR80_SOURCE_LOCAL_PARITY",
    "HOME_AND_AWAY_GOALS_ARE_EXACT_PR117_NONNEGATIVE_INTEGER_SCORES_WITH_NO_SCORE_NORMALIZATION",
    "OBSERVED_AT_IS_THE_EARLIEST_OF_THE_TWO_PR117_QUALIFIED_MANIFEST_OBSERVATION_TIMES_AND_MUST_BE_STRICTLY_AFTER_KICKOFF_UTC",
    "EVIDENCE_SHA256_IS_SHA256_OF_THE_EXACT_CANONICAL_PR117_ORDINARY_FT_PROJECTION_RECORD_BINDING_BOTH_MANIFEST_LINEAGES",
    "EVIDENCE_REFERENCE_IS_A_DETERMINISTIC_FROZEN_CAMPAIGN_REFERENCE_BINDING_REQUEST_DATE_AND_SOURCE_FIXTURE_ID",
    "EVERY_MATERIALIZED_ROW_MUST_VALIDATE_AS_PR80_PROSPECTIVE_MATCH_EVIDENCE_WITHOUT_RELAXING_PR80_INVARIANTS",
    "MATERIALIZATION_OUTPUT_MUST_BE_A_DETERMINISTIC_CANONICAL_PROJECTION_WITH_COUNT_SIZE_AND_SHA256_FROZEN_IN_THE_EXECUTION_RECEIPT",
    "MATERIALIZATION_DOES_NOT_BY_ITSELF_AUTHORIZE_PR80_CONSTRUCTOR_INPUT_A_TARGET_SPECIFIC_LATER_BOUNDARY_MUST_ENFORCE_STRICTLY_PRIOR_LOCAL_AND_UTC_ORDER_AND_OBSERVED_AT_BY_AS_OF",
)
FUTURE_EXTENSION_RULES = (
    "THE_FROZEN_HISTORICAL_ADAPTER_IS_NOT_AUTHORIZED_TO_ACQUIRE_OR_QUALIFY_DATES_AFTER_2026_08_14",
    "A_PROSPECTIVE_EXTENSION_AFTER_2026_08_14_MUST_USE_SEPARATELY_REVIEWED_PROSPECTIVE_ACQUISITION_AND_ADAPTER_SEMANTICS",
    "A_PROSPECTIVE_EXTENSION_MUST_BE_CALENDAR_DATE_CONTIGUOUS_WITH_THE_2026_08_14_HISTORICAL_CEILING_WITH_NO_FAILED_MISSING_OR_UNREVIEWED_DATES",
    "NO_TARGET_AFTER_THE_HISTORICAL_CEILING_MAY_CLAIM_COMPLETE_SOURCE_HISTORY_UNTIL_THE_EXTENSION_IS_QUALIFIED_THROUGH_ITS_REQUIRED_TARGET_DATE",
    "ANY_SEMANTIC_DIFFERENCE_BETWEEN_HISTORICAL_AND_PROSPECTIVE_ROW_LINEAGE_REQUIRES_A_SEPARATE_BRIDGE_REVIEW_NOT_AN_IMPLICIT_MERGE",
)
QUALIFICATION_STATUS_VOCABULARY = (
    "QUALIFIED_COMPLETE_FROZEN_HISTORICAL_HISTORY_THROUGH_2026_08_14",
    "BLOCKED_PR117_HISTORICAL_ADAPTER_QUALIFICATION_DRIFT",
    "BLOCKED_PR81_OR_PR99_COMPLETENESS_CONTRACT_DRIFT",
    "BLOCKED_INITIALIZATION_BOUNDARY_DRIFT",
    "BLOCKED_REQUIRED_DATE_GAP",
    "BLOCKED_RESULT_EVIDENCE_GAP",
    "BLOCKED_SPECIAL_RESULT_OR_CHRONOLOGY_DISPOSITION_DRIFT",
    "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT",
    "BLOCKED_SOURCE_LOCAL_TIME_BASIS_CONFLICT",
    "BLOCKED_OBSERVATION_TIME_NOT_AFTER_KICKOFF",
    "BLOCKED_MATERIALIZATION_ROW_INVARIANT",
    "BLOCKED_MATERIALIZATION_PROJECTION_NONDETERMINISTIC",
)
POSITIVE_EXECUTION_MAY_AUTHORIZE = (
    "SCOPED_FROZEN_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_PROVEN",
    "EXACT_21326_ORDINARY_FT_HISTORY_ROWS_MATERIALIZATION_AUTHORIZED",
    "PR117_HISTORICAL_ADAPTER_APPROVED_FOR_THE_FROZEN_CAMPAIGN_SCOPE_ONLY",
)
POSITIVE_EXECUTION_MUST_REMAIN_FALSE = (
    "GLOBAL_SOURCE_CAPABILITY_HISTORICAL_COVERAGE_CONFIRMED",
    "SOURCE_CAPABILITY_REGISTRY_MUTATION",
    "COMPETITION_REGISTRY_MUTATION",
    "PR80_CONSTRUCTOR_INPUT_AUTHORIZED",
    "SUCCESSOR_LIVE_INPUTS_QUALIFIED",
    "SUCCESSOR_CANDIDATE_APPROVED",
    "MODEL_TRAINING_AUTHORIZED",
    "EXPECTED_GOALS_PRODUCTION_AUTHORIZED",
    "PROBABILITY_INFERENCE_AUTHORIZED",
    "PRICING_AUTHORIZED",
    "MARKET_ACTIVATION_AUTHORIZED",
    "SELECTION_AUTHORIZED",
    "PRODUCTION_APPROVAL_AUTHORIZED",
    "BET_AUTHORIZED",
)

CURRENT_PRE_EXECUTION_DISPOSITION = "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_QUALIFICATION"
)

_SAFETY_KEYS = frozenset({
    "bet_authorized", "calibration_for_production_authorized",
    "competition_registry_mutation_authorized", "expected_goals_production_authorized",
    "expected_goals_transform_approved", "global_historical_coverage_capability_mutation_authorized",
    "history_rows_materialization_authorized", "market_activation_authorized",
    "model_training_authorized", "ordinary_ft_history_rows_authorized",
    "pr80_constructor_input_authorized", "pricing_authorized",
    "probability_adjustment_authorized", "probability_inference_authorized",
    "production_approval_authorized", "score_matrix_authorized", "selection_authorized",
    "source_capability_registry_mutation_authorized", "source_history_adapter_approved",
    "source_history_completeness_proven", "successor_candidate_approved",
    "successor_live_inputs_qualified",
})
PROTOCOL_SHA256 = "c4d9d019fa433677d82354570df1fe1c0e634c14b91c1f9ba0c3b47f91258209"
PROTOCOL_SIZE = 9_708


class FotMobHistoricalSourceHistoryCompletenessMaterializationProtocolError(ValueError):
    """Raised when the exact PR #118 protocol or frozen ancestry drifts."""


def _error(message: str) -> FotMobHistoricalSourceHistoryCompletenessMaterializationProtocolError:
    return FotMobHistoricalSourceHistoryCompletenessMaterializationProtocolError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(
            _plain(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("PR118 protocol serialization failed") from exc
    return (text + "\n").encode("utf-8")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return types.MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "upstream": {
            "pr81_protocol_sha256": PR81_PROTOCOL_SHA256,
            "pr81_protocol_size_bytes": PR81_PROTOCOL_SIZE,
            "pr99_protocol_sha256": PR99_PROTOCOL_SHA256,
            "pr99_protocol_size_bytes": PR99_PROTOCOL_SIZE,
            "pr110_special_result_receipt_sha256": PR110_RECEIPT_SHA256,
            "pr112_rearrangement_chronology_receipt_sha256": PR112_RECEIPT_SHA256,
            "pr114_elo_initialization_receipt_sha256": PR114_RECEIPT_SHA256,
            "pr117_historical_adapter_receipt_sha256": PR117_RECEIPT_SHA256,
            "pr117_historical_adapter_receipt_size_bytes": PR117_RECEIPT_SIZE,
            "pr117_ordinary_ft_projection_sha256": PR117_ORDINARY_FT_PROJECTION_SHA256,
            "pr117_ordinary_ft_projection_size_bytes": PR117_ORDINARY_FT_PROJECTION_SIZE,
            "pr80_construction_spec_sha256": PR80_CONSTRUCTION_SPEC_SHA256,
            "pr80_construction_spec_size_bytes": PR80_CONSTRUCTION_SPEC_SIZE,
        },
        "source_scope": {
            "source_namespace": SOURCE_NAMESPACE,
            "artifact_id": ARTIFACT_ID,
            "artifact_sha256": ARTIFACT_SHA256,
            "artifact_size_bytes": ARTIFACT_SIZE,
            "research_cache_sha256": RESEARCH_CACHE_SHA256,
            "research_cache_size_bytes": RESEARCH_CACHE_SIZE,
            "request_timezone": REQUEST_TIMEZONE,
            "ccode3": REQUEST_CCODE3,
            "historical_request_date_start": HISTORICAL_REQUEST_DATE_START,
            "historical_request_date_end": HISTORICAL_REQUEST_DATE_END,
            "source_local_time_basis": SOURCE_LOCAL_TIME_BASIS,
            "global_source_capability_historical_coverage_must_remain": "UNKNOWN",
        },
        "frozen_family_reference_floors": dict(FROZEN_FAMILY_REFERENCE_FLOORS),
        "evidence_expectations": {
            "request_date_count": 2205,
            "capture_manifest_count": 4410,
            "target_family_fixture_date_pair_count": 21640,
            "ordinary_ft_occurrence_count": 21336,
            "reviewed_special_state_occurrence_count": 304,
            "preboundary_ordinary_ft_occurrence_count": 10,
            "on_or_after_floor_materialization_candidate_count": 21326,
            "ordinary_ft_unique_source_fixture_id_count": 21336,
            "ordinary_ft_duplicate_source_fixture_id_count": 0,
            "on_or_after_floor_by_model_league": dict(ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE),
            "special_state_occurrence_counts": dict(SPECIAL_STATE_OCCURRENCE_COUNTS),
        },
        "contract_reconciliation_rules": list(CONTRACT_RECONCILIATION_RULES),
        "completeness_rules": list(COMPLETENESS_RULES),
        "materialization_rules": list(MATERIALIZATION_RULES),
        "future_extension_rules": list(FUTURE_EXTENSION_RULES),
        "qualification_status_vocabulary": list(QUALIFICATION_STATUS_VOCABULARY),
        "current_pre_execution_disposition": CURRENT_PRE_EXECUTION_DISPOSITION,
        "positive_execution_may_authorize": list(POSITIVE_EXECUTION_MAY_AUTHORIZE),
        "positive_execution_must_remain_false": list(POSITIVE_EXECUTION_MUST_REMAIN_FALSE),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _verify_upstream() -> None:
    pr81_value = pr81.build_prospective_successor_source_history_completeness_protocol()
    pr81_raw = pr81.canonical_prospective_successor_source_history_completeness_protocol_bytes(pr81_value)
    if (hashlib.sha256(pr81_raw).hexdigest(), len(pr81_raw)) != (PR81_PROTOCOL_SHA256, PR81_PROTOCOL_SIZE):
        raise _error("PR81 completeness protocol identity changed")

    pr99_value = pr99.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()
    pr99_raw = pr99.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(pr99_value)
    if (hashlib.sha256(pr99_raw).hexdigest(), len(pr99_raw)) != (PR99_PROTOCOL_SHA256, PR99_PROTOCOL_SIZE):
        raise _error("PR99 completeness protocol identity changed")

    pr117_receipt = pr117.load_fotmob_historical_source_history_adapter_qualification_receipt()
    pr117_raw = pr117.canonical_fotmob_historical_source_history_adapter_qualification_receipt_bytes()
    if (hashlib.sha256(pr117_raw).hexdigest(), len(pr117_raw)) != (PR117_RECEIPT_SHA256, PR117_RECEIPT_SIZE):
        raise _error("PR117 historical adapter receipt identity changed")
    if pr117_receipt.get("historical_source_history_adapter_qualified") is not True:
        raise _error("PR117 historical adapter qualification changed")
    if pr117_receipt.get("remaining_blockers") != ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]:
        raise _error("PR117 remaining blocker ancestry changed")
    if pr117_receipt.get("history_rows_materialized") != 0:
        raise _error("PR117 unexpectedly materialized history rows")

    r110 = pr110.load_fotmob_source_history_special_result_semantics_qualification_receipt()
    if pr110.RECEIPT_SHA256 != PR110_RECEIPT_SHA256 or r110.get("special_result_semantics_qualified") is not True:
        raise _error("PR110 special-result qualification changed")
    r112 = pr112.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    if pr112.RECEIPT_SHA256 != PR112_RECEIPT_SHA256 or r112.get("rearrangement_chronology_qualified") is not True:
        raise _error("PR112 rearrangement chronology qualification changed")
    r114 = pr114.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    if pr114.RECEIPT_SHA256 != PR114_RECEIPT_SHA256 or r114.get("initialization_boundary_qualified") is not True:
        raise _error("PR114 Elo initialization qualification changed")

    spec = pr80.build_prospective_successor_feature_construction_specification()
    spec_raw = pr80.canonical_prospective_successor_feature_construction_specification_bytes(spec)
    if (hashlib.sha256(spec_raw).hexdigest(), len(spec_raw)) != (PR80_CONSTRUCTION_SPEC_SHA256, PR80_CONSTRUCTION_SPEC_SIZE):
        raise _error("PR80 construction specification changed")

    if dict(pr114.EXPECTED_FLOORS) != dict(FROZEN_FAMILY_REFERENCE_FLOORS):
        raise _error("PR114 family reference floors changed")
    if dict(pr117.EXPECTED_BY_LEAGUE) != dict(ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE):
        raise _error("PR117 per-family candidate counts changed")
    if dict(pr117.EXPECTED_SPECIAL_COUNTS) != dict(SPECIAL_STATE_OCCURRENCE_COUNTS):
        raise _error("PR117 special-state accounting changed")
    if pr117.ORDINARY_FT_PROJECTION_SHA256 != PR117_ORDINARY_FT_PROJECTION_SHA256:
        raise _error("PR117 ordinary-FT projection identity changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(SOURCE_NAMESPACE)
    if capability is None:
        raise _error("reviewed derived FotMob source capability is missing")
    if capability.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed derived full-time score capability changed")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed derived fixture identity capability changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("global FotMob historical coverage must remain UNKNOWN at PR118")


def build_fotmob_historical_source_history_completeness_materialization_protocol() -> Mapping[str, Any]:
    """Return the immutable PR #118 protocol after revalidating frozen premises."""
    _verify_upstream()
    expected = _payload()
    exact = _canonical(expected)
    if (hashlib.sha256(exact).hexdigest(), len(exact)) != (PROTOCOL_SHA256, PROTOCOL_SIZE):
        raise _error("PR118 canonical protocol identity changed")
    return _freeze(expected)


def canonical_fotmob_historical_source_history_completeness_materialization_protocol_bytes(
    value: Mapping[str, Any],
) -> bytes:
    if not isinstance(value, Mapping) or _plain(value) != _plain(_payload()):
        raise _error("value differs from exact PR118 protocol")
    exact = _canonical(value)
    if (hashlib.sha256(exact).hexdigest(), len(exact)) != (PROTOCOL_SHA256, PROTOCOL_SIZE):
        raise _error("PR118 canonical protocol identity changed")
    return exact


def sha256_fotmob_historical_source_history_completeness_materialization_protocol(
    value: Mapping[str, Any],
) -> str:
    return hashlib.sha256(
        canonical_fotmob_historical_source_history_completeness_materialization_protocol_bytes(value)
    ).hexdigest()


__all__ = [
    "COMPLETENESS_RULES", "CONTRACT_RECONCILIATION_RULES", "CURRENT_PRE_EXECUTION_DISPOSITION",
    "FROZEN_FAMILY_REFERENCE_FLOORS", "FUTURE_EXTENSION_RULES", "HISTORICAL_REQUEST_DATE_END",
    "HISTORICAL_REQUEST_DATE_START", "MATERIALIZATION_RULES", "NEXT_REQUIRED_BOUNDARY",
    "ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE", "POSITIVE_EXECUTION_MAY_AUTHORIZE",
    "POSITIVE_EXECUTION_MUST_REMAIN_FALSE", "PROTOCOL_ID", "PROTOCOL_SCOPE", "PROTOCOL_SHA256",
    "PROTOCOL_SIZE", "PROTOCOL_STATE", "QUALIFICATION_STATUS_VOCABULARY", "SOURCE_LOCAL_TIME_BASIS",
    "SOURCE_NAMESPACE", "SPECIAL_STATE_OCCURRENCE_COUNTS",
    "FotMobHistoricalSourceHistoryCompletenessMaterializationProtocolError",
    "build_fotmob_historical_source_history_completeness_materialization_protocol",
    "canonical_fotmob_historical_source_history_completeness_materialization_protocol_bytes",
    "sha256_fotmob_historical_source_history_completeness_materialization_protocol",
]
