"""Pre-register FotMob source-history special-result semantics after PR #108."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_primary_id_competition_mapping_qualification as pr108

SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_SPECIAL_FINISHED_AND_UNRESOLVED_SOURCE_STATE_DISPOSITION_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_NO_SPECIAL_RESULT_SEMANTICS_QUALIFIED"
REPOSITORY_MAIN_SHA = "fa3aa9de0a679e6efebc1a53a245bd8b418f3839"
PR108_RECEIPT_SHA256 = "fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9"
PR108_RECEIPT_SIZE = 13_681
PR105_RECEIPT_SHA256 = "a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363"
PR105_RECEIPT_SIZE = 11_995
SPECIAL_PROJECTION_SHA256 = "d5f70aad76424a01249365da09d450b4fb7f27f3d03ab546e8b9783784f5a96b"
SPECIAL_PROJECTION_SIZE = 13_531
UNRESOLVED_PROJECTION_SHA256 = "153cca2a970bce982eecab45c2df5fbaf1df099d081c45f7c3195bb1580b8593"
UNRESOLVED_PROJECTION_SIZE = 8_154
ORDINARY_HISTORY_DISPOSITION = "EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY"
PRESERVATION_DISPOSITION = "PRESERVE_AS_SOURCE_EVIDENCE_NO_SILENT_DROP_OR_COERCION"

STATE_SPECS = (
    ("AWARDED_WIN", "AW", "", "Awarded win", "awarded_win", True, True, False, "EXACT_TRUE",
     "SOURCE_REPORTED_ADMINISTRATIVE_SCORE_NOT_OBSERVED_FOOTBALL_PERFORMANCE"),
    ("AFTER_EXTRA_TIME", "AET", "afterextratime_short", "After extra time", "afterextra", True, True, False, "EXACT_FALSE",
     "SOURCE_FINISHED_SCORE_INCLUDES_EXTRA_TIME_AND_IS_NOT_REGULATION_TIME_SCORE"),
    ("AFTER_PENALTIES", "Pen", "penalties_short", "After penalties", "afterpenalties", True, True, False, "EXACT_FALSE",
     "BASE_SCORE_AND_TEAM_PEN_SCORE_FIELDS_REMAIN_SEPARATE_AND_ARE_NOT_REGULATION_TIME_SCORE"),
    ("ABANDONED", "Ab", "aborted_short", "Abandoned", "aborted", True, True, True, "ABSENT_OR_FALSE",
     "SCORE_AT_ABANDONMENT_IS_PARTIAL_SOURCE_STATE_NOT_FINAL_REGULATION_RESULT"),
    ("CANCELLED", "Can", "cancelled_short", "Cancelled", "cancelled", False, False, True, "ABSENT_OR_FALSE",
     "ANY_SCORE_SCALARS_ARE_NONRESULT_METADATA_NOT_PLAYED_SCORE"),
    ("POSTPONED", "PP", "postponed_short", "Postponed", "postponed", False, False, True, "ABSENT_OR_FALSE",
     "ANY_SCORE_SCALARS_ARE_NONRESULT_METADATA_NOT_PLAYED_SCORE"),
)

SEMANTIC_RULES = (
    "CLASSIFY_ONLY_WITH_EXACT_REASON_TUPLE_AND_FINISHED_STARTED_CANCELLED_AWARDED_POLICY",
    "STATUS_ID_IS_SUPPORTING_EVIDENCE_ONLY_NEVER_THE_SOLE_SEMANTIC_CLASSIFIER",
    "NUMERIC_SCORE_COINCIDENCE_NEVER_OVERRIDES_STATUS_REASON_SEMANTICS",
    "AWARDED_RESULTS_MUST_NOT_TRAIN_OBSERVED_FOOTBALL_GOAL_MODELS",
    "AFTER_EXTRA_TIME_SCORES_MUST_NOT_BE_REINTERPRETED_AS_NINETY_MINUTE_SCORES",
    "AFTER_PENALTIES_BASE_SCORE_AND_TEAM_PEN_SCORE_FIELDS_MUST_REMAIN_SEPARATE",
    "ABANDONED_CANCELLED_AND_POSTPONED_STATES_MUST_NOT_BE_PROMOTED_TO_PLAYED_FINAL_RESULTS",
    "ALL_REVIEWED_SPECIAL_STATES_ARE_EXCLUDED_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY_BUT_PRESERVED_AS_SOURCE_EVIDENCE",
    "SOURCE_HISTORY_SEMANTICS_DO_NOT_DEFINE_BOOKMAKER_SETTLEMENT_RULES",
)

CHRONOLOGY_HANDOFF_RULES = (
    "SAME_DATE_A_B_CAPTURE_LINEAGES_MUST_AGREE_ON_IDENTITY_KICKOFF_STATE_REASON_AND_RELEVANT_SCORE_FIELDS",
    "CROSS_DATE_KICKOFF_OR_STATE_CHANGES_MUST_BE_PRESERVED_AS_TRANSITIONS_NOT_COLLAPSED_TO_A_CONVENIENT_FINAL_OBSERVATION",
    "POSTPONED_OR_CANCELLED_TO_ORDINARY_FT_AND_CANCELLED_TO_AWARDED_TRANSITIONS_REMAIN_BLOCKED_FOR_SEPARATE_CHRONOLOGY_REVIEW",
    "FIXTURE_3932603_ON_REQUEST_DATES_20230220_AND_20230305_REMAINS_TWO_SOURCE_OCCURRENCES_UNTIL_CHRONOLOGY_DISPOSITION",
)

QUALIFICATION_REQUIREMENTS = (
    "USE_ONLY_EXACT_PRESERVED_PR105_CAMPAIGN_ARTIFACT_WITHOUT_NETWORK_REACQUISITION",
    "REVALIDATE_PR108_COMPETITION_MAPPING_QUALIFICATION_FIRST",
    "ACCOUNT_FOR_EVERY_FIXTURE_IN_THE_PR105_SPECIAL_AND_UNRESOLVED_PROJECTIONS",
    "PRESERVE_REQUEST_DATE_CAPTURE_ID_FIXTURE_TEAM_KICKOFF_STATUS_REASON_SCORE_PEN_SCORE_ELIMINATED_TEAM_STATUS_ID_AND_TOURNAMENT_CONTEXT_WHEN_PRESENT",
    "FAIL_CLOSED_ON_UNKNOWN_REASON_OR_BOOLEAN_VARIANT",
    "REQUIRE_AFTER_PENALTIES_TEAM_PEN_SCORE_FIELDS_TO_REMAIN_SEPARATE_FROM_BASE_SCORE_AND_PRESERVE_ELIMINATED_TEAM_ID",
    "PRODUCE_DETERMINISTIC_CANONICAL_RECEIPT_WITH_COUNTS_IDS_CONFLICTS_AND_CROSS_DATE_TRANSITIONS",
    "MUTATE_NO_SOURCE_CAPABILITY_COMPETITION_MODEL_PRICING_SELECTION_OR_BETTING_REGISTRY",
)

NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_QUALIFICATION"
_SAFETY_KEYS = frozenset({
    "special_result_semantics_qualified", "special_result_history_rows_authorized",
    "ordinary_ft_history_extension_authorized", "rearrangement_chronology_resolved",
    "source_history_adapter_approved", "source_history_completeness_proven",
    "pr80_constructor_input_authorized", "successor_live_inputs_qualified",
    "successor_candidate_approved", "expected_goals_transform_approved",
    "expected_goals_production_authorized", "score_matrix_authorized",
    "probability_inference_authorized", "probability_adjustment_authorized",
    "calibration_for_production_authorized", "pricing_authorized",
    "market_activation_authorized", "selection_authorized",
    "production_approval_authorized", "bet_authorized", "model_training_authorized",
})
PROTOCOL_SHA256 = "5fc2d1c089ecea5fd3ab4b9920f578ac25b555c0d89bebad4eedbfcd80c3cf87"
PROTOCOL_SIZE = 7040

class FotMobSourceHistorySpecialResultSemanticsProtocolError(ValueError):
    pass

def _error(message: str) -> FotMobSourceHistorySpecialResultSemanticsProtocolError:
    return FotMobSourceHistorySpecialResultSemanticsProtocolError(message)

def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("special-result protocol serialization failed") from exc
    return (text + "\n").encode("utf-8")

def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})

def _state_payloads() -> list[dict[str, Any]]:
    return [
        {
            "state_id": row[0], "reason_short": row[1], "reason_short_key": row[2],
            "reason_long": row[3], "reason_long_key": row[4], "finished": row[5],
            "started": row[6], "cancelled": row[7], "awarded_requirement": row[8],
            "score_semantics": row[9], "history_disposition": ORDINARY_HISTORY_DISPOSITION,
            "preservation_disposition": PRESERVATION_DISPOSITION,
        }
        for row in STATE_SPECS
    ]

def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE, "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr108_receipt_sha256": PR108_RECEIPT_SHA256, "pr108_receipt_size": PR108_RECEIPT_SIZE,
        "pr105_receipt_sha256": PR105_RECEIPT_SHA256, "pr105_receipt_size": PR105_RECEIPT_SIZE,
        "evidence_scope": {
            "special_projection_sha256": SPECIAL_PROJECTION_SHA256,
            "special_projection_size": SPECIAL_PROJECTION_SIZE,
            "unresolved_projection_sha256": UNRESOLVED_PROJECTION_SHA256,
            "unresolved_projection_size": UNRESOLVED_PROJECTION_SIZE,
            "awarded_unique": 25, "awarded_observations": 26, "aet_unique": 3,
            "penalty_unique": 3, "abandoned_unique": 13, "cancelled_unique": 6,
            "postponed_unique": 2,
            "duplicate_terminal_awarded_fixture": {"fixture_id": 3932603, "request_dates": ["20230220", "20230305"]},
        },
        "state_specs": _state_payloads(), "semantic_rules": list(SEMANTIC_RULES),
        "chronology_handoff_rules": list(CHRONOLOGY_HANDOFF_RULES),
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "special_result_semantics_execution_performed": False,
        "source_history_mutation_performed": False, "historical_coverage_proven": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY, "safety": dict(_safety()),
    }

def _verify_upstream() -> None:
    receipt = pr108.load_fotmob_primary_id_competition_mapping_qualification_receipt()
    raw108 = pr108.canonical_fotmob_primary_id_competition_mapping_qualification_receipt_bytes()
    if len(raw108) != PR108_RECEIPT_SIZE or hashlib.sha256(raw108).hexdigest() != PR108_RECEIPT_SHA256:
        raise _error("PR108 qualification receipt identity changed")
    if receipt.get("mapping_qualification_proven") is not True or receipt.get("historical_coverage_proven") is not False:
        raise _error("PR108 mapping/history premise changed")
    if receipt.get("next_required_boundary") != "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_PROTOCOL":
        raise _error("PR108 next boundary changed")

    raw105 = pr108.PR105_RECEIPT_PATH.read_bytes()
    if len(raw105) != PR105_RECEIPT_SIZE or hashlib.sha256(raw105).hexdigest() != PR105_RECEIPT_SHA256:
        raise _error("PR105 completeness receipt identity changed")
    try:
        old = json.loads(raw105)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR105 completeness receipt is invalid JSON") from exc
    if raw105 != _canonical(old):
        raise _error("PR105 completeness receipt is not canonical")
    special, unresolved = old.get("special_result_blockers"), old.get("unresolved_source_states")
    if not isinstance(special, dict) or not isinstance(unresolved, dict):
        raise _error("PR105 special evidence missing")
    if (special.get("full_projection_sha256"), special.get("full_projection_size_bytes")) != (SPECIAL_PROJECTION_SHA256, SPECIAL_PROJECTION_SIZE):
        raise _error("PR105 special-result projection changed")
    if (unresolved.get("full_projection_sha256"), unresolved.get("full_projection_size_bytes")) != (UNRESOLVED_PROJECTION_SHA256, UNRESOLVED_PROJECTION_SIZE):
        raise _error("PR105 unresolved-state projection changed")
    counts = (special.get("awarded_win_unique_fixture_ids"), special.get("awarded_win_observation_count"),
              special.get("after_extra_time_unique_fixture_ids"), special.get("after_penalties_unique_fixture_ids"),
              unresolved.get("abandoned_unique_fixture_ids"), unresolved.get("cancelled_unique_fixture_ids"),
              unresolved.get("postponed_unique_fixture_ids"))
    if counts != (25, 26, 3, 3, 13, 6, 2):
        raise _error("PR105 special-result counts changed")
    if special.get("duplicate_terminal_awarded_fixture") != {"fixture_id": 3932603, "request_dates": ["20230220", "20230305"]}:
        raise _error("PR105 duplicate awarded evidence changed")

@dataclasses.dataclass(frozen=True)
class FotMobSourceHistorySpecialResultSemanticsProtocol:
    payload: Mapping[str, Any]
    def __post_init__(self) -> None:
        if dict(self.payload) != _payload():
            raise _error("special-result protocol differs from frozen contract")
        safety = self.payload.get("safety")
        if not isinstance(safety, Mapping) or set(safety) != _SAFETY_KEYS or any(value is not False for value in safety.values()):
            raise _error("all special-result safety values must remain exact False")
        for key in ("special_result_semantics_execution_performed", "source_history_mutation_performed", "historical_coverage_proven"):
            if self.payload.get(key) is not False:
                raise _error(f"{key} must remain exact False")
        object.__setattr__(self, "payload", types.MappingProxyType(dict(self.payload)))
    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)

def build_fotmob_source_history_special_result_semantics_protocol() -> FotMobSourceHistorySpecialResultSemanticsProtocol:
    _verify_upstream()
    value = FotMobSourceHistorySpecialResultSemanticsProtocol(_payload())
    raw = canonical_fotmob_source_history_special_result_semantics_protocol_bytes(value)
    if len(raw) != PROTOCOL_SIZE or hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise _error("special-result protocol canonical identity changed")
    return value

def canonical_fotmob_source_history_special_result_semantics_protocol_bytes(value: FotMobSourceHistorySpecialResultSemanticsProtocol) -> bytes:
    if type(value) is not FotMobSourceHistorySpecialResultSemanticsProtocol:
        raise _error("special-result protocol must be the exact reviewed type")
    return _canonical(value.to_dict())
