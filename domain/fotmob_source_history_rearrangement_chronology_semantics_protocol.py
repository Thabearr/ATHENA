"""Pre-register reviewed FotMob source-history rearrangement chronology semantics.

PR #111 freezes only the source-scoped chronology contract for the 250 preserved
FotMob fixture IDs whose source-reported kickoff changed across request dates. It
does not execute chronology qualification, materialize history, or authorize
model, pricing, selection, production, or BET use.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_source_history_special_result_semantics_qualification as pr110

SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_SEMANTICS_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_SOURCE_SCOPED_REARRANGED_FIXTURE_CHRONOLOGY_DISPOSITION_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_REARRANGEMENT_CHRONOLOGY_UNQUALIFIED"
REPOSITORY_MAIN_SHA = "8bc0a8afc20b71958dee9d14ab1d783eff646447"
PR110_RECEIPT_SHA256 = "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
PR110_RECEIPT_SIZE = 8_558
PR110_QUALIFICATION_DOMAIN_BLOB_SHA = "ed3f2053ab9732e1e34e2e54f6f1e3531d01a4ca"
HISTORY_PROJECTION_SHA256 = "459c94fd53430663562d9ce614ca2b52b518b6a8f06f6661b27b555c567c281d"
HISTORY_PROJECTION_SIZE = 380_539

TRANSITION_SPECS = (
    (
        "POSTPONED_TO_ORDINARY_FT",
        ("POSTPONED", "ORDINARY_FT"),
        234,
        "SOURCE_SCHEDULE_REVISION_THEN_LATER_ORDINARY_FT_WITHOUT_INFERRING_REASON_FOR_RESCHEDULING",
        "LATER_ORDINARY_FT_MAY_REACH_SEPARATE_HISTORY_MATERIALIZATION_REVIEW_ONLY_AFTER_CHRONOLOGY_QUALIFICATION",
    ),
    (
        "ABANDONED_TO_ORDINARY_FT",
        ("ABANDONED", "ORDINARY_FT"),
        7,
        "SOURCE_LATER_REPORTS_ORDINARY_FT_AFTER_ABANDONED_STATE_WITHOUT_INFERRING_RESUMED_REPLAYED_RESTARTED_OR_CONTINUED_PLAY",
        "LATER_ORDINARY_FT_MAY_REACH_SEPARATE_HISTORY_MATERIALIZATION_REVIEW_ONLY_AFTER_CHRONOLOGY_QUALIFICATION",
    ),
    (
        "CANCELLED_TO_AWARDED_WIN",
        ("CANCELLED", "AWARDED_WIN"),
        5,
        "SOURCE_LATER_REPORTS_ADMINISTRATIVE_AWARDED_RESULT_AFTER_CANCELLED_STATE_WITHOUT_INFERRING_CAUSE",
        "EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY_PRESERVE_BOTH_SOURCE_STATES",
    ),
    (
        "POSTPONED_TO_POSTPONED_TO_ORDINARY_FT",
        ("POSTPONED", "POSTPONED", "ORDINARY_FT"),
        2,
        "MULTIPLE_SOURCE_SCHEDULE_REVISIONS_THEN_LATER_ORDINARY_FT",
        "LATER_ORDINARY_FT_MAY_REACH_SEPARATE_HISTORY_MATERIALIZATION_REVIEW_ONLY_AFTER_CHRONOLOGY_QUALIFICATION",
    ),
    (
        "POSTPONED_TO_AWARDED_WIN",
        ("POSTPONED", "AWARDED_WIN"),
        1,
        "SOURCE_LATER_REPORTS_ADMINISTRATIVE_AWARDED_RESULT_AFTER_POSTPONED_STATE_WITHOUT_INFERRING_CAUSE",
        "EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY_PRESERVE_BOTH_SOURCE_STATES",
    ),
    (
        "AWARDED_WIN_TO_AWARDED_WIN",
        ("AWARDED_WIN", "AWARDED_WIN"),
        1,
        "REPEATED_ADMINISTRATIVE_AWARDED_STATE_ACROSS_CHANGED_KICKOFF_METADATA_PRESERVE_BOTH_OCCURRENCES",
        "EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY_NO_LAST_OBSERVATION_COERCION",
    ),
)

IDENTITY_SEMANTICS = (
    "FOTMOB_FIXTURE_ID_IS_ONLY_A_SOURCE_SCOPED_LINEAGE_ANCHOR_AND_NEVER_A_CROSS_SOURCE_IDENTITY",
    "CHANGED_KICKOFF_ALONE_DOES_NOT_CREATE_A_NEW_SOURCE_FIXTURE_IDENTITY_WHEN_ALL_FROZEN_STATIC_IDENTITY_FIELDS_REMAIN_EXACT",
    "STATIC_IDENTITY_REQUIRES_EXACT_PRIMARY_ID_WRAPPER_LEAGUE_ID_HOME_TEAM_ID_AND_AWAY_TEAM_ID_ACROSS_ALL_OCCURRENCES",
    "SAME_DATE_A_B_CAPTURES_MUST_MATCH_EXACTLY_ON_IDENTITY_KICKOFF_STATE_REASON_AND_RELEVANT_SCORE_FIELDS",
    "REQUEST_DATE_MUST_EQUAL_THE_UTC_CALENDAR_DATE_OF_THE_SOURCE_REPORTED_KICKOFF_FOR_EACH_REVIEWED_OCCURRENCE",
    "EVERY_SUCCESSIVE_REVIEWED_KICKOFF_MUST_BE_STRICTLY_LATER_THAN_THE_PREVIOUS_SOURCE_REPORTED_KICKOFF",
    "KICKOFF_REVISION_SEMANTICS_ARE_LIMITED_TO_THE_FROZEN_REARRANGED_CORPUS_AND_DO_NOT_GLOBALLY_REDEFINE_FIXTURE_IDENTITY",
)

CHRONOLOGY_SEMANTICS = (
    "PRESERVE_EVERY_RAW_CAPTURE_AND_EVERY_FIXTURE_DATE_OCCURRENCE_NO_DESTRUCTIVE_COLLAPSE",
    "PAIR_SAME_DATE_A_B_CAPTURES_ONLY_AS_A_REPRODUCIBLE_EVIDENCE_VIEW_WHILE_RETAINING_BOTH_RAW_LINEAGES",
    "ORDER_CROSS_DATE_OCCURRENCES_BY_REQUEST_DATE_AND_REQUIRE_STRICT_FORWARD_KICKOFF_REVISION",
    "ACCEPT_ONLY_THE_SIX_PRE_REGISTERED_TRANSITION_PATTERNS_AND_FAIL_CLOSED_ON_ANY_OTHER_PATTERN_OR_VARIANT",
    "A_LATER_ORDINARY_FT_STATE_DOES_NOT_PROVE_WHETHER_AN_EARLIER_ABANDONED_MATCH_WAS_RESUMED_REPLAYED_RESTARTED_OR_REPLACED",
    "EARLIER_POSTPONED_CANCELLED_OR_ABANDONED_SCORE_SCALARS_MUST_NEVER_OVERRIDE_A_LATER_REVIEWED_TERMINAL_DISPOSITION",
    "AWARDED_WIN_REMAINS_ADMINISTRATIVE_SOURCE_RESULT_EVIDENCE_AND_NEVER_OBSERVED_FOOTBALL_PERFORMANCE",
    "DERIVED_TERMINAL_DISPOSITION_MAY_REFERENCE_A_LATER_SOURCE_STATE_BUT_MUST_NOT_DELETE_HIDE_OR_REWRITE_EARLIER_SOURCE_STATES",
    "CHRONOLOGY_QUALIFICATION_ALONE_MUST_NOT_AUTHORIZE_HISTORY_ROWS_MODEL_TRAINING_PROBABILITIES_PRICING_SELECTION_PRODUCTION_OR_BET",
)

QUALIFICATION_REQUIREMENTS = (
    "USE_ONLY_THE_EXACT_PRESERVED_PR105_CAMPAIGN_ARTIFACT_WITHOUT_NETWORK_REACQUISITION",
    "REVALIDATE_THE_EXACT_PR110_SPECIAL_RESULT_SEMANTICS_QUALIFICATION_RECEIPT_FIRST",
    "ACCOUNT_FOR_ALL_250_REARRANGED_FIXTURE_IDS_AND_ALL_502_FIXTURE_DATE_OCCURRENCES",
    "REQUIRE_EXACT_TWO_CAPTURE_SAME_DATE_PAIRS_WITH_ZERO_RELEVANT_FIELD_DRIFT",
    "REQUIRE_ZERO_CROSS_DATE_STATIC_IDENTITY_DRIFT_AND_ZERO_REQUEST_DATE_KICKOFF_UTC_DATE_MISMATCH",
    "REQUIRE_EVERY_CROSS_DATE_KICKOFF_REVISION_EDGE_TO_MOVE_STRICTLY_FORWARD",
    "REQUIRE_EXACT_TRANSITION_PATTERN_COUNTS_234_7_5_2_1_1",
    "REQUIRE_EXACT_TERMINAL_CLASS_COUNTS_243_ORDINARY_FT_AND_7_AWARDED_WIN",
    "PRESERVE_FIXTURE_3932603_AS_TWO_AWARDED_SOURCE_OCCURRENCES_WITHOUT_LAST_OBSERVATION_COERCION",
    "PRODUCE_A_DETERMINISTIC_CANONICAL_RECEIPT_WITH_EXACT_FIXTURE_MEMBERSHIP_COUNTS_PATTERN_COUNTS_AND_CONFLICT_COUNTS",
    "MUTATE_NO_SOURCE_CAPABILITY_COMPETITION_MODEL_PRICING_SELECTION_OR_BETTING_REGISTRY",
)

NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_QUALIFICATION"

_SAFETY_KEYS = frozenset(
    {
        "rearrangement_chronology_resolved",
        "ordinary_ft_history_rows_authorized",
        "special_result_history_rows_authorized",
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "initialization_boundary_proven",
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
        "model_training_authorized",
        "bet_authorized",
        "competition_registry_mutation_authorized",
        "source_capability_registry_mutation_authorized",
    }
)

PROTOCOL_SHA256 = "3f7caa751d0fe8114e50d8fee4bb2afa58023b4bee63429e4c6c51b9d2f92ce3"
PROTOCOL_SIZE = 7_642


class FotMobSourceHistoryRearrangementChronologySemanticsProtocolError(ValueError):
    """Raised when the frozen PR #111 protocol cannot be reproduced."""


def _error(message: str) -> FotMobSourceHistoryRearrangementChronologySemanticsProtocolError:
    return FotMobSourceHistoryRearrangementChronologySemanticsProtocolError(message)


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
        raise _error("rearrangement chronology protocol serialization failed") from exc
    return (text + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _transition_payloads() -> list[dict[str, Any]]:
    return [
        {
            "pattern_id": row[0],
            "pattern": list(row[1]),
            "fixture_id_count": row[2],
            "chronology_semantics": row[3],
            "terminal_disposition": row[4],
        }
        for row in TRANSITION_SPECS
    ]


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "upstream": {
            "pr110_qualification_receipt_sha256": PR110_RECEIPT_SHA256,
            "pr110_qualification_receipt_size_bytes": PR110_RECEIPT_SIZE,
            "pr110_qualification_domain_blob_sha": PR110_QUALIFICATION_DOMAIN_BLOB_SHA,
            "special_result_semantics_qualified_required": True,
            "historical_coverage_proven_required": False,
            "chronology_resolved_required": False,
            "special_fixture_history_projection_sha256": HISTORY_PROJECTION_SHA256,
            "special_fixture_history_projection_size_bytes": HISTORY_PROJECTION_SIZE,
        },
        "evidence_expectations": {
            "rearranged_fixture_id_count": 250,
            "rearranged_fixture_date_occurrence_count": 502,
            "raw_pair_capture_observation_count": 1004,
            "transition_edge_count": 252,
            "terminal_ordinary_ft_fixture_count": 243,
            "terminal_awarded_win_fixture_count": 7,
            "state_occurrence_counts": {
                "POSTPONED": 239,
                "ABANDONED": 7,
                "CANCELLED": 5,
                "ORDINARY_FT": 243,
                "AWARDED_WIN": 8,
            },
            "duplicate_terminal_awarded_fixture": {
                "fixture_id": 3932603,
                "request_dates": ["20230220", "20230305"],
            },
            "same_date_pair_capture_count_required": 2,
            "same_date_pair_conflict_count_required": 0,
            "cross_date_static_identity_drift_count_required": 0,
            "request_date_kickoff_utc_date_mismatch_count_required": 0,
            "kickoff_revision_direction": "STRICTLY_FORWARD_FOR_EVERY_REVIEWED_CROSS_DATE_EDGE",
        },
        "transition_specs": _transition_payloads(),
        "identity_semantics": list(IDENTITY_SEMANTICS),
        "chronology_semantics": list(CHRONOLOGY_SEMANTICS),
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "chronology_semantics_execution_performed": False,
        "rearrangement_chronology_qualified": False,
        "source_history_mutation_performed": False,
        "historical_coverage_proven": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _verify_upstream() -> None:
    receipt = pr110.load_fotmob_source_history_special_result_semantics_qualification_receipt()
    raw = pr110.canonical_fotmob_source_history_special_result_semantics_qualification_receipt_bytes()
    if len(raw) != PR110_RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != PR110_RECEIPT_SHA256:
        raise _error("PR110 qualification receipt identity changed")
    if receipt.get("special_result_semantics_qualified") is not True:
        raise _error("PR110 special-result semantics are no longer qualified")
    if receipt.get("historical_coverage_proven") is not False:
        raise _error("PR110 historical coverage premise changed")
    if receipt.get("next_required_boundary") != (
        "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_SEMANTICS_PROTOCOL"
    ):
        raise _error("PR110 next boundary changed")

    source = receipt.get("source_evidence")
    chronology = receipt.get("chronology_handoff")
    if not isinstance(source, dict) or not isinstance(chronology, dict):
        raise _error("PR110 chronology evidence is missing")
    if (
        source.get("special_fixture_history_projection_sha256"),
        source.get("special_fixture_history_projection_size_bytes"),
    ) != (HISTORY_PROJECTION_SHA256, HISTORY_PROJECTION_SIZE):
        raise _error("PR110 special-fixture history projection changed")
    if chronology.get("rearranged_fixture_id_count") != 250:
        raise _error("PR110 rearranged fixture count changed")
    if chronology.get("chronology_resolved") is not False:
        raise _error("PR110 chronology must remain unresolved before this protocol executes")
    if chronology.get("collapsed_to_final_observation") is not False:
        raise _error("PR110 chronology evidence was destructively collapsed")

    expected_transitions = [
        {"fixture_id_count": row[2], "pattern": list(row[1])}
        for row in TRANSITION_SPECS
    ]
    if chronology.get("transition_summary") != expected_transitions:
        raise _error("PR110 transition summary changed")
    if chronology.get("duplicate_terminal_awarded_fixture") != {
        "fixture_id": 3932603,
        "request_dates": ["20230220", "20230305"],
    }:
        raise _error("PR110 duplicate awarded chronology evidence changed")


@dataclasses.dataclass(frozen=True)
class FotMobSourceHistoryRearrangementChronologySemanticsProtocol:
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if dict(self.payload) != _payload():
            raise _error("rearrangement chronology protocol differs from frozen contract")
        safety = self.payload.get("safety")
        if (
            not isinstance(safety, Mapping)
            or set(safety) != _SAFETY_KEYS
            or any(value is not False for value in safety.values())
        ):
            raise _error("all rearrangement chronology safety values must remain exact False")
        for key in (
            "chronology_semantics_execution_performed",
            "rearrangement_chronology_qualified",
            "source_history_mutation_performed",
            "historical_coverage_proven",
        ):
            if self.payload.get(key) is not False:
                raise _error(f"{key} must remain exact False")
        object.__setattr__(self, "payload", types.MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def build_fotmob_source_history_rearrangement_chronology_semantics_protocol(
) -> FotMobSourceHistoryRearrangementChronologySemanticsProtocol:
    _verify_upstream()
    value = FotMobSourceHistoryRearrangementChronologySemanticsProtocol(_payload())
    raw = canonical_fotmob_source_history_rearrangement_chronology_semantics_protocol_bytes(value)
    if len(raw) != PROTOCOL_SIZE or hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise _error("rearrangement chronology protocol canonical identity changed")
    return value


def canonical_fotmob_source_history_rearrangement_chronology_semantics_protocol_bytes(
    value: FotMobSourceHistoryRearrangementChronologySemanticsProtocol,
) -> bytes:
    if type(value) is not FotMobSourceHistoryRearrangementChronologySemanticsProtocol:
        raise _error("rearrangement chronology protocol must be the exact reviewed type")
    return _canonical(value.to_dict())
