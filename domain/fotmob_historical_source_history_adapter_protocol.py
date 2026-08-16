"""Pre-register the reviewed FotMob historical source-history adapter.

PR #116 freezes a historical-only ordinary-FT adapter contract for the exact
preserved FotMob campaign after PR #115 proved that the prospective adapter is
not admissible for that corpus.  This module does not execute the adapter,
materialize source history, mutate source capabilities, or authorize downstream
model, pricing, selection, production, or BET use.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as prospective_adapter
import domain.fotmob_data_matches_status_reason_semantics_protocol as pr90
import domain.fotmob_source_history_adapter_completeness_assessment as pr115
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_FROZEN_CAMPAIGN_HISTORICAL_ORDINARY_FT_SOURCE_HISTORY_ADAPTER_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_SOURCE_HISTORY_ADAPTER_UNQUALIFIED"
REPOSITORY_MAIN_SHA = "3b49eccc9476754972c18b9abcfe013f783a6205"

PR115_RECEIPT_SHA256 = "247dd06389f17cc2d27af568b92f19de1da49b3d3fce1c73ad901d904a2366b2"
PR115_RECEIPT_SIZE = 6634
PR115_ASSESSMENT_DOMAIN_BLOB_SHA = "15a120272c08a495c4a12d7321f8b4ff7ec6b2ec"
PROSPECTIVE_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
PR90_PROTOCOL_BLOB_SHA = "f9546ff05cddfe366d278d4dbdf1020bb7666951"
PR90_PROTOCOL_SHA256 = "08bbc2d1e53cfb1268ba71745ae80d9bc32f4bfad0f02d52225df936c7634f23"
PR90_PROTOCOL_SIZE = 5602

ARTIFACT_ID = 9_249_856_559
ARTIFACT_NAME = "fotmob-ordinary-ft-source-history-campaign-31887523012"
ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61886753
RESEARCH_CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
RESEARCH_CACHE_SIZE = 61881610
DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"

TARGET_COMPETITION_FAMILIES = (
    ("B1", 40), ("D1", 54), ("E0", 47), ("F1", 53), ("G1", 135),
    ("I1", 55), ("N1", 57), ("P1", 61), ("SC0", 64), ("SP1", 87), ("T1", 71),
)
ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE = types.MappingProxyType({'B1': 1933, 'D1': 1835, 'E0': 2280, 'F1': 2056, 'G1': 1431, 'I1': 2280, 'N1': 1865, 'P1': 1846, 'SC0': 1380, 'SP1': 2280, 'T1': 2140})
ORDINARY_FT_REASON_TUPLE = types.MappingProxyType({"short": "FT", "shortKey": "fulltime_short", "long": "Full-Time", "longKey": "finished"})

PAIR_LINEAGE_RULES = ('HISTORICAL_PAIR_REQUIRES_EXACTLY_TWO_DISTINCT_CANONICAL_MANIFEST_LINEAGES_FOR_ONE_REQUEST_DATE_TIMEZONE_CCODE3', 'EACH_RAW_RESPONSE_MUST_INDEPENDENTLY_MATCH_ITS_OWN_MANIFEST_SHA256_SIZE_AND_NETWORK_ACQUISITION_TRUE', 'OBSERVATION_TIMES_MUST_BE_STRICTLY_ORDERED_AND_SEPARATED_BY_AT_LEAST_300_SECONDS', 'IDENTICAL_RAW_SHA256_IS_ADMISSIBLE_ONLY_FOR_THIS_FROZEN_HISTORICAL_ADAPTER_WHEN_MANIFEST_LINEAGES_ARE_DISTINCT_AND_ALL_TARGET_RELEVANT_FIELDS_ARE_EXACTLY_STABLE', 'IDENTICAL_RAW_SHA256_MEANS_BYTE_IDENTICAL_CONTENT_RETRIEVED_TWICE_NOT_TWO_DISTINCT_CONTENT_LINEAGES', 'DISTINCT_RAW_SHA256_DOES_NOT_BYPASS_TARGET_RELEVANT_FIELD_STABILITY_OR_HISTORICAL_STRUCTURAL_REVALIDATION', 'NEVER_SYNTHESIZE_REWRITE_SALT_OR_MUTATE_RAW_BYTES_OR_MANIFESTS_TO_CREATE_DISTINCT_LINEAGE', 'THE_PROSPECTIVE_ORDINARY_FT_ADAPTER_DISTINCT_RAW_LINEAGE_RULE_REMAINS_UNCHANGED')
HISTORICAL_STRUCTURAL_RULES = ('HISTORICAL_ADAPTER_IS_LIMITED_TO_THE_EXACT_HASHED_PR105_CAMPAIGN_AND_MAKES_NO_GLOBAL_FOTMOB_SCHEMA_CLAIM', 'ONLY_REQUIRED_HISTORY_FIELDS_ARE_INTERPRETED_ALL_OTHER_FROZEN_PAYLOAD_METADATA_REMAINS_OPAQUE_AND_PRESERVED_IN_RAW_EVIDENCE', 'TARGET_ORDINARY_FT_STATUS_HALFS_MUST_BE_AN_EXACT_MAPPING_WITH_FIRST_HALF_STARTED_AND_SECOND_HALF_STARTED_ONLY', 'FIRST_HALF_STARTED_AND_SECOND_HALF_STARTED_MUST_BE_EXACT_STRINGS_PARSEABLE_AS_DD_MM_YYYY_HH_MM_SS_WITHOUT_TIMEZONE_OR_FOOTBALL_SEMANTIC_INFERENCE', 'FIRST_HALF_STARTED_IS_HISTORICAL_OPAQUE_METADATA_AND_IS_NOT_KICKOFF_HALFTIME_DURATION_RESUMPTION_OR_SETTLEMENT_EVIDENCE', 'STATUS_UTC_TIME_IS_THE_ONLY_CANONICAL_KICKOFF_FIELD_AND_MUST_PARSE_AS_UTC', 'MATCH_TIME_MUST_CORROBORATE_STATUS_UTC_TIME_VIA_EUROPE_OSLO_AT_MINUTE_PRECISION_FOR_THIS_FROZEN_CORPUS_ONLY', 'NO_OPAQUE_OR_IGNORED_FIELD_MAY_OVERRIDE_IDENTITY_SCORE_REASON_AWARDED_PENALTY_OR_CHRONOLOGY_GATES', 'THE_FROZEN_PR89_AND_PROSPECTIVE_ADAPTER_IMPLEMENTATIONS_ARE_NOT_MUTATED_OR_REDEFINED_BY_THIS_HISTORICAL_CONTRACT')
ORDINARY_FT_SEMANTICS = ('LIMIT_TO_THE_ELEVEN_PR108_QUALIFIED_SOURCE_SCOPED_PRIMARY_ID_COMPETITION_FAMILIES', 'FOTMOB_FIXTURE_ID_REMAINS_A_SOURCE_SCOPED_IDENTITY_ONLY_AND_NEVER_CROSS_SOURCE_IDENTITY', 'REQUIRE_EXACT_WRAPPER_LEAGUE_ID_HOME_TEAM_ID_AWAY_TEAM_ID_AND_KICKOFF_UTC_STABILITY_ACROSS_THE_PAIR', 'REQUIRE_FINISHED_TRUE_STARTED_TRUE_CANCELLED_FALSE', 'REQUIRE_STATUS_AWARDED_ABSENT_OR_EXACT_FALSE', 'REQUIRE_EXACT_PR90_ORDINARY_FT_FOUR_FIELD_REASON_TUPLE_WITHOUT_NORMALIZATION_ALIASING_OR_PARTIAL_MATCH', 'REQUIRE_HOME_AND_AWAY_SCORE_TO_BE_EXACT_NONNEGATIVE_INTEGERS_AND_STABLE_ACROSS_THE_PAIR', 'REQUIRE_TEAM_PEN_SCORE_ABSENT_ON_BOTH_ENDPOINTS', 'STATUS_ID_SCORE_STR_PERIOD_LENGTH_HALFS_TIMESTAMPS_TEAM_NAMES_RED_CARDS_AND_OTHER_OPAQUE_FIELDS_CANNOT_CREATE_RESULT_SEMANTICS', 'AWARDED_AFTER_EXTRA_TIME_AFTER_PENALTIES_ABANDONED_CANCELLED_POSTPONED_OR_ANY_UNREVIEWED_STATE_IS_NEVER_ADMITTED_AS_ORDINARY_FT_HISTORY', 'PR110_SPECIAL_RESULT_AND_PR112_REARRANGEMENT_DISPOSITIONS_REMAIN_AUTHORITATIVE')
QUALIFICATION_OUTPUT_RULES = ('QUALIFICATION_OUTPUT_MAY_CREATE_ONLY_A_DETERMINISTIC_DERIVED_EVIDENCE_PROJECTION_NOT_SOURCE_HISTORY_ROWS', 'ONE_ORDINARY_FT_PROJECTION_RECORD_PER_SOURCE_FIXTURE_ID_AND_FIXTURE_DATE_OCCURRENCE_WITH_NO_DESTRUCTIVE_RAW_EVIDENCE_COLLAPSE', 'PROJECTION_RECORD_MUST_BIND_REQUEST_DATE_FIXTURE_ID_MODEL_LEAGUE_CODE_PRIMARY_ID_WRAPPER_LEAGUE_ID_KICKOFF_UTC_HOME_TEAM_ID_AWAY_TEAM_ID_HOME_SCORE_AWAY_SCORE_REASON_AND_BOTH_MANIFEST_LINEAGES', 'PROJECTION_RECORD_MUST_RECORD_WHETHER_THE_OCCURRENCE_IS_BEFORE_OR_ON_AFTER_THE_PR114_ELO_INITIALIZATION_FLOOR', 'THE_TEN_PREBOUNDARY_ORDINARY_FT_OCCURRENCES_REMAIN_EVIDENCE_ONLY_AND_CANNOT_SEED_ELO_OR_MODEL_HISTORY', 'THE_21326_ON_OR_AFTER_FLOOR_OCCURRENCES_REMAIN_ONLY_FUTURE_HISTORY_MATERIALIZATION_CANDIDATES_UNTIL_COMPLETENESS_IS_RERUN', 'NO_PROJECTION_RECORD_MAY_BE_PASSED_TO_PR80_DURING_THIS_QUALIFICATION_BOUNDARY')
QUALIFICATION_REQUIREMENTS = ('USE_ONLY_ARTIFACT_9249856559_WITH_EXACT_OUTER_AND_RESEARCH_CACHE_HASHES_WITHOUT_NETWORK_REACQUISITION', 'REVALIDATE_THE_EXACT_PR115_FAIL_CLOSED_RECEIPT_AND_ITS_BLOCKED_RESULT_EVIDENCE_GAP_BEFORE_EXECUTION', 'DO_NOT_CALL_OR_MODIFY_THE_PROSPECTIVE_ADAPTER_AS_THE_HISTORICAL_PAIR_GATE', 'REQUIRE_2205_REQUEST_DATES_4410_MANIFESTS_2205_DISTINCT_MANIFEST_PAIRS_AND_THE_FROZEN_OBSERVATION_SEPARATION_RULE', 'REQUIRE_2204_IDENTICAL_RAW_PAIRS_ONE_DISTINCT_RAW_PAIR_AND_ZERO_TARGET_FAMILY_PAIRS_ON_THE_DISTINCT_RAW_DATE', 'ACCOUNT_FOR_ALL_21640_TARGET_FAMILY_FIXTURE_DATE_PAIRS_AS_21336_ORDINARY_FT_PLUS_304_REVIEWED_SPECIAL_STATES', 'REQUIRE_21336_UNIQUE_ORDINARY_FT_SOURCE_FIXTURE_IDS_WITH_ZERO_DUPLICATE_ORDINARY_FIXTURE_ID', 'REQUIRE_ALL_21336_TARGET_ORDINARY_FT_ROWS_TO_HAVE_EXACT_HISTORICAL_HALFS_KEYSET_AND_PARSEABLE_STRING_DOMAINS', 'REQUIRE_EXACT_PR114_SPLIT_OF_10_PREBOUNDARY_AND_21326_ON_OR_AFTER_FLOOR_ORDINARY_FT_OCCURRENCES', 'REQUIRE_ZERO_A_B_RELEVANT_FIELD_CONFLICTS_AND_ZERO_EUROPE_OSLO_DISPLAY_TIME_MISMATCHES', 'FAIL_CLOSED_ON_ANY_IDENTITY_SCORE_REASON_STATE_PENALTY_HALFS_TIME_BASIS_OR_PROVENANCE_DRIFT', 'PRODUCE_DETERMINISTIC_CANONICAL_ADAPTER_QUALIFICATION_RECEIPT_AND_PROJECTION_HASHES', 'MUTATE_NO_SOURCE_CAPABILITY_COMPETITION_HISTORY_MODEL_PRICING_SELECTION_OR_BETTING_REGISTRY')

NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_QUALIFICATION"

_SAFETY_KEYS = frozenset(['bet_authorized', 'calibration_for_production_authorized', 'competition_registry_mutation_authorized', 'expected_goals_production_authorized', 'expected_goals_transform_approved', 'historical_coverage_proven', 'historical_source_history_adapter_qualified', 'history_rows_materialization_authorized', 'market_activation_authorized', 'model_training_authorized', 'network_acquisition_authorized', 'ordinary_ft_history_rows_authorized', 'pr80_constructor_input_authorized', 'pr89_mutation_authorized', 'pricing_authorized', 'probability_adjustment_authorized', 'probability_inference_authorized', 'production_approval_authorized', 'prospective_adapter_mutation_authorized', 'score_matrix_authorized', 'selection_authorized', 'source_capability_registry_mutation_authorized', 'source_history_adapter_approved', 'source_history_completeness_proven', 'successor_candidate_approved', 'successor_live_inputs_qualified'])
PROTOCOL_SHA256 = "f987bc68eaf9f4c7b57a66788f3dcac5d704be6dad36ecae92bf5dd7e315ea9a"
PROTOCOL_SIZE = 9898


class FotMobHistoricalSourceHistoryAdapterProtocolError(ValueError):
    """Raised when the frozen PR #116 protocol cannot be reproduced."""


def _error(message: str) -> FotMobHistoricalSourceHistoryAdapterProtocolError:
    return FotMobHistoricalSourceHistoryAdapterProtocolError(message)


def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("historical source-history adapter protocol serialization failed") from exc
    return (text + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _target_competition_payload() -> list[dict[str, int | str]]:
    return [
        {"model_league_code": model_code, "primary_id": primary_id}
        for model_code, primary_id in TARGET_COMPETITION_FAMILIES
    ]


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "upstream": {
            "pr115_assessment_receipt_sha256": PR115_RECEIPT_SHA256,
            "pr115_assessment_receipt_size_bytes": PR115_RECEIPT_SIZE,
            "pr115_assessment_domain_blob_sha": PR115_ASSESSMENT_DOMAIN_BLOB_SHA,
            "pr115_primary_status_required": "BLOCKED_RESULT_EVIDENCE_GAP",
            "pr115_history_rows_materialized_required": 0,
            "prospective_adapter_blob_sha": PROSPECTIVE_ADAPTER_BLOB_SHA,
            "pr89_structural_implementation_blob_sha": PR89_IMPLEMENTATION_BLOB_SHA,
            "pr90_reason_protocol_blob_sha": PR90_PROTOCOL_BLOB_SHA,
            "pr90_reason_protocol_sha256": PR90_PROTOCOL_SHA256,
            "pr90_reason_protocol_size_bytes": PR90_PROTOCOL_SIZE,
            "historical_coverage_proven_required": False,
        },
        "source_evidence": {
            "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME,
            "artifact_sha256": ARTIFACT_SHA256,
            "artifact_size_bytes": ARTIFACT_SIZE,
            "research_cache_sha256": RESEARCH_CACHE_SHA256,
            "research_cache_size_bytes": RESEARCH_CACHE_SIZE,
            "request_timezone": "UTC",
            "ccode3": "NGA",
            "start_date": "2020-08-01",
            "end_date": "2026-08-14",
        },
        "target_competition_families": _target_competition_payload(),
        "ordinary_ft_reason_tuple": dict(ORDINARY_FT_REASON_TUPLE),
        "evidence_expectations": {
            "request_date_count": 2205,
            "capture_manifest_count": 4410,
            "capture_pair_count": 2205,
            "distinct_manifest_pair_count": 2205,
            "identical_raw_sha256_pair_count": 2204,
            "distinct_raw_sha256_pair_count": 1,
            "distinct_raw_sha256_pair_dates": ["20250712"],
            "target_family_fixture_date_pair_count": 21640,
            "target_family_pairs_on_distinct_raw_dates": 0,
            "ordinary_ft_fixture_date_occurrence_count": 21336,
            "ordinary_ft_unique_source_fixture_id_count": 21336,
            "ordinary_ft_duplicate_source_fixture_id_count": 0,
            "preboundary_ordinary_ft_occurrence_count": 10,
            "on_or_after_floor_ordinary_ft_occurrence_count": 21326,
            "on_or_after_floor_ordinary_ft_by_model_league": dict(ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE),
            "reviewed_special_state_occurrence_count": 304,
            "same_date_target_relevant_field_conflict_count": 0,
            "source_display_time_basis": "Europe/Oslo",
            "source_display_time_basis_mismatch_count": 0,
            "historical_halfs_exact_keys": ["firstHalfStarted", "secondHalfStarted"],
            "historical_halfs_candidate_count": 21336,
            "historical_halfs_type": "EXACT_STRING_FOR_BOTH_KEYS",
            "historical_halfs_format": "%d.%m.%Y %H:%M:%S",
            "minimum_pair_separation_seconds": 300,
        },
        "pair_lineage_rules": list(PAIR_LINEAGE_RULES),
        "historical_structural_rules": list(HISTORICAL_STRUCTURAL_RULES),
        "ordinary_ft_semantics": list(ORDINARY_FT_SEMANTICS),
        "qualification_output_rules": list(QUALIFICATION_OUTPUT_RULES),
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "historical_adapter_execution_performed": False,
        "historical_source_history_adapter_qualified": False,
        "source_history_completeness_proven": False,
        "historical_coverage_proven": False,
        "history_rows_materialized": 0,
        "source_history_mutation_performed": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _verify_upstream() -> None:
    receipt = pr115.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    raw = pr115.canonical_fotmob_source_history_adapter_completeness_assessment_receipt_bytes()
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (PR115_RECEIPT_SHA256, PR115_RECEIPT_SIZE):
        raise _error("PR115 assessment receipt identity changed")
    if _git_blob_sha(Path(pr115.__file__)) != PR115_ASSESSMENT_DOMAIN_BLOB_SHA:
        raise _error("PR115 assessment implementation blob changed")
    if receipt.get("primary_status") != "BLOCKED_RESULT_EVIDENCE_GAP":
        raise _error("PR115 primary blocker changed")
    if receipt.get("history_rows_materialized") != 0:
        raise _error("PR115 unexpectedly materialized history rows")
    if receipt.get("source_history_adapter_approved") is not False:
        raise _error("PR115 source-history adapter premise changed")
    if receipt.get("source_history_completeness_proven") is not False:
        raise _error("PR115 completeness premise changed")
    if receipt.get("historical_coverage_proven") is not False:
        raise _error("PR115 historical-coverage premise changed")
    if receipt.get("next_required_boundary") != (
        "PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_PROTOCOL"
    ):
        raise _error("PR115 next boundary changed")

    checks = receipt.get("campaign_checks")
    adapter = receipt.get("adapter_compatibility")
    if not isinstance(checks, dict) or not isinstance(adapter, dict):
        raise _error("PR115 campaign or adapter evidence is missing")
    if (
        checks.get("request_date_count"),
        checks.get("capture_manifest_count"),
        checks.get("distinct_manifest_pair_count"),
        checks.get("target_family_fixture_date_pair_count"),
        checks.get("reviewed_ordinary_ft_candidate_count_on_or_after_floor"),
        checks.get("special_state_occurrence_count_on_or_after_floor"),
        checks.get("same_date_target_relevant_field_conflict_count"),
        checks.get("source_display_time_basis_mismatch_count"),
    ) != (2205, 4410, 2205, 21640, 21326, 304, 0, 0):
        raise _error("PR115 campaign evidence changed")
    if checks.get("ordinary_ft_candidates_by_model_league") != dict(ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE):
        raise _error("PR115 per-league ordinary-FT accounting changed")
    if (
        adapter.get("capture_pair_count"),
        adapter.get("identical_raw_sha256_pair_count"),
        adapter.get("distinct_raw_sha256_pair_count"),
        adapter.get("distinct_raw_sha256_pair_dates"),
        adapter.get("target_family_fixture_date_pairs_on_distinct_raw_dates"),
        adapter.get("ordinary_ft_candidates_blocked_by_identical_raw_lineage_requirement"),
    ) != (2205, 2204, 1, ["20250712"], 0, 21326):
        raise _error("PR115 adapter-compatibility evidence changed")
    if adapter.get("reviewed_adapter_blob_sha") != PROSPECTIVE_ADAPTER_BLOB_SHA:
        raise _error("PR115 prospective adapter blob evidence changed")

    if _git_blob_sha(Path(prospective_adapter.__file__)) != PROSPECTIVE_ADAPTER_BLOB_SHA:
        raise _error("prospective ordinary-FT adapter blob changed")
    if _git_blob_sha(Path(pr89.__file__)) != PR89_IMPLEMENTATION_BLOB_SHA:
        raise _error("PR89 structural implementation blob changed")
    if _git_blob_sha(Path(pr90.__file__)) != PR90_PROTOCOL_BLOB_SHA:
        raise _error("PR90 reason protocol blob changed")
    protocol90 = pr90.build_fotmob_data_matches_status_reason_semantics_protocol()
    raw90 = pr90.canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes(protocol90)
    if (hashlib.sha256(raw90).hexdigest(), len(raw90)) != (PR90_PROTOCOL_SHA256, PR90_PROTOCOL_SIZE):
        raise _error("PR90 reason protocol identity changed")
    if dict(pr90.ORDINARY_FT_REASON_TUPLE) != dict(ORDINARY_FT_REASON_TUPLE):
        raise _error("PR90 ordinary-FT reason tuple changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(DERIVED_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed derived FotMob score source is missing")
    if capability.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("derived full-time score capability changed")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("derived fixture identity capability changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("historical coverage must remain UNKNOWN before this protocol executes")


@dataclasses.dataclass(frozen=True)
class FotMobHistoricalSourceHistoryAdapterProtocol:
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if dict(self.payload) != _payload():
            raise _error("historical source-history adapter protocol differs from frozen contract")
        safety = self.payload.get("safety")
        if (
            not isinstance(safety, Mapping)
            or set(safety) != _SAFETY_KEYS
            or any(type(value) is not bool or value is not False for value in safety.values())
        ):
            raise _error("all historical adapter safety values must remain exact False")
        for key in (
            "historical_adapter_execution_performed",
            "historical_source_history_adapter_qualified",
            "source_history_completeness_proven",
            "historical_coverage_proven",
            "source_history_mutation_performed",
        ):
            if self.payload.get(key) is not False:
                raise _error(f"{key} must remain exact False")
        if self.payload.get("history_rows_materialized") != 0:
            raise _error("pre-registration must materialize zero history rows")
        object.__setattr__(self, "payload", types.MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def build_fotmob_historical_source_history_adapter_protocol() -> FotMobHistoricalSourceHistoryAdapterProtocol:
    """Build the exact pre-registered historical source-history adapter contract."""
    _verify_upstream()
    return FotMobHistoricalSourceHistoryAdapterProtocol(_payload())


def canonical_fotmob_historical_source_history_adapter_protocol_bytes(
    value: FotMobHistoricalSourceHistoryAdapterProtocol,
) -> bytes:
    if not isinstance(value, FotMobHistoricalSourceHistoryAdapterProtocol):
        raise TypeError("value must be FotMobHistoricalSourceHistoryAdapterProtocol")
    raw = _canonical(value.to_dict())
    if len(raw) != PROTOCOL_SIZE or hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise _error("historical source-history adapter canonical identity changed")
    return raw


__all__ = [
    "ARTIFACT_ID",
    "ARTIFACT_NAME",
    "ARTIFACT_SHA256",
    "ARTIFACT_SIZE",
    "HISTORICAL_STRUCTURAL_RULES",
    "NEXT_REQUIRED_BOUNDARY",
    "ORDINARY_FT_REASON_TUPLE",
    "ORDINARY_FT_SEMANTICS",
    "ON_OR_AFTER_FLOOR_BY_MODEL_LEAGUE",
    "PAIR_LINEAGE_RULES",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "QUALIFICATION_OUTPUT_RULES",
    "QUALIFICATION_REQUIREMENTS",
    "REPOSITORY_MAIN_SHA",
    "TARGET_COMPETITION_FAMILIES",
    "FotMobHistoricalSourceHistoryAdapterProtocol",
    "FotMobHistoricalSourceHistoryAdapterProtocolError",
    "build_fotmob_historical_source_history_adapter_protocol",
    "canonical_fotmob_historical_source_history_adapter_protocol_bytes",
]
