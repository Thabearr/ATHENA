"""Pre-register FotMob-to-PR80 source-local time semantic equivalence.

This protocol is deliberately result-free. It freezes the exact evidence and
operation-level requirements that a later qualification must satisfy before the
PR #119 historical rows may be used as PR #80 source-local history. It does not
authorize PR #80 input, model training, probability inference, pricing,
selection, production, or betting.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import domain.fotmob_historical_source_history_completeness_materialization_qualification as pr119
import domain.historical_model_feature_replay_candidate as pr69
import domain.prospective_successor_feature_construction_candidate as pr80
import domain.successor_live_input_semantic_qualification_protocol as pr78


SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL_V1"
PROTOCOL_SCOPE = (
    "PRE_REGISTERED_FROZEN_FOTMOB_HISTORY_TO_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_ONLY"
)
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_SOURCE_LOCAL_TIME_EQUIVALENCE_UNQUALIFIED"
REPOSITORY_MAIN_SHA = "37c5f031a71222b13cbea19eaab0fbd92ba74aa0"
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_QUALIFICATION"
)

PR119_RECEIPT_SHA256 = "da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0"
PR119_RECEIPT_SIZE = 6_810
PR119_QUALIFICATION_BLOB_SHA = "f0d17dbcd70fc8b5432b50061525224642541c05"
PR80_CONSTRUCTOR_BLOB_SHA = "9135f056d036fd0207a3daead2599ac2520274be"
PR69_REPLAY_BLOB_SHA = "b67a7e52954f47cc90c578ad193545c541984964"
PR78_SEMANTIC_PROTOCOL_BLOB_SHA = "cbd409fe42ffa8a3571f604e0817c06671db2a25"

SOURCE_NAMESPACE = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
FROZEN_HISTORY_ROW_COUNT = 21_326
HISTORICAL_REQUEST_DATE_END = "2026-08-14"
MODEL_LEAGUE_CODES = (
    "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
)

QUALIFICATION_REQUIREMENTS = (
    "RESOLVE_PR69_SOURCE_LOCAL_TIME_BASIS_TO_A_DETERMINISTIC_REVIEWED_RULE_OR_PROVE_SOURCE_INDEPENDENT_INVARIANCE",
    "PROVE_FOTMOB_EUROPE_OSLO_NAIVE_REPRESENTATION_IS_ADMISSIBLE_UNDER_THE_REVIEWED_REFERENCE_RULE",
    "PROVE_STRICT_PRIOR_MEMBERSHIP_EQUIVALENCE_FOR_EVERY_FROZEN_HISTORY_ROW_AND_REVIEWED_TARGET_BOUNDARY",
    "PROVE_FORM_ORDERING_EQUIVALENCE_INCLUDING_FIXTURE_IDENTIFIER_TIEBREAK_BEHAVIOR",
    "PROVE_ELO_ORDERING_EQUIVALENCE_INCLUDING_FIXTURE_IDENTIFIER_TIEBREAK_BEHAVIOR",
    "PROVE_MOST_RECENT_PRIOR_FIXTURE_EQUIVALENCE_PER_SOURCE_SCOPED_TEAM",
    "PROVE_DATETIME_DELTA_DAYS_INTEGER_COMPONENT_EQUIVALENCE_FOR_HOME_AND_AWAY_REST",
    "PROVE_HOME_MINUS_AWAY_REST_DAY_DIFFERENCE_EQUIVALENCE_AND_FATIGUE_BUCKET_EQUIVALENCE",
    "ZERO_UNRESOLVED_TEMPORAL_AMBIGUITY_OR_UNREVIEWED_TIMEZONE_INFERENCE",
    "PRESERVE_EXACT_PR69_PR78_PR80_PR119_ANCESTRY_WITHOUT_RESULT_DRIVEN_MUTATION",
)

ADMISSIBLE_EVIDENCE = (
    "EXACT_FROZEN_REPOSITORY_ANCESTRY_AND_RAW_SOURCE_BYTES",
    "PRESERVED_HASHED_PRIMARY_FOOTBALL_DATA_UK_DOCUMENTATION_OR_SOURCE_SEMANTICS",
    "PRESERVED_HASHED_PRIMARY_FOTMOB_DOCUMENTATION_OR_RESPONSE_SEMANTICS",
    "FORMAL_SOURCE_INDEPENDENT_INVARIANCE_PROOF_WITH_ALL_ASSUMPTIONS_PROVEN_FOR_FROZEN_SCOPE",
)

FORBIDDEN_SHORTCUTS = (
    "DO_NOT_ASSUME_EUROPE_OSLO_EQUALS_PR69_SOURCE_LOCAL_TIME",
    "DO_NOT_INFER_TIMEZONE_FROM_COUNTRY_LEAGUE_OR_VENUE_WITHOUT_REVIEWED_EVIDENCE",
    "ZERO_GLOBAL_ORDERING_DISAGREEMENT_DOES_NOT_PROVE_DATETIME_DELTA_DAYS_EQUIVALENCE",
    "EQUAL_NUMERIC_FEATURE_VALUES_ALONE_DO_NOT_PROVE_SEMANTIC_EQUIVALENCE",
    "DO_NOT_USE_CROSS_SOURCE_FIXTURE_OR_TEAM_IDENTITY_INFERENCE_TO_HIDE_TIME_BASIS_UNCERTAINTY",
    "DO_NOT_MUTATE_PR69_PR78_PR80_OR_PR119_SEMANTICS_AFTER_OBSERVING_EXECUTION_RESULTS",
)

QUALIFICATION_STATUS_VOCABULARY = (
    "QUALIFIED_EXACT_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE",
    "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED",
    "BLOCKED_FOTMOB_TIME_BASIS_EVIDENCE_INSUFFICIENT",
    "BLOCKED_TIME_DEPENDENT_OPERATION_MISMATCH",
    "BLOCKED_TEMPORAL_AMBIGUITY",
    "BLOCKED_ANCESTRY_OR_EVIDENCE_GAP",
)

SAFETY_KEYS = frozenset({
    "source_local_time_semantic_equivalence_qualified",
    "pr80_constructor_input_authorized",
    "successor_live_inputs_qualified",
    "successor_candidate_approved",
    "model_training_authorized",
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
})

PROTOCOL_SHA256 = "a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918"
PROTOCOL_SIZE = 5_242


class FotMobPR80SourceLocalTimeSemanticEquivalenceProtocolError(ValueError):
    """Raised when the frozen pre-registration contract no longer revalidates."""


def _error(message: str) -> FotMobPR80SourceLocalTimeSemanticEquivalenceProtocolError:
    return FotMobPR80SourceLocalTimeSemanticEquivalenceProtocolError(message)


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
        raise _error("source-local semantic protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(SAFETY_KEYS)})


def _verify_upstream() -> None:
    receipt = pr119.load_fotmob_historical_source_history_completeness_materialization_qualification_receipt()
    raw = pr119.canonical_fotmob_historical_source_history_completeness_materialization_qualification_receipt_bytes()
    if (
        pr119.RECEIPT_SHA256 != PR119_RECEIPT_SHA256
        or pr119.RECEIPT_SIZE != PR119_RECEIPT_SIZE
        or hashlib.sha256(raw).hexdigest() != PR119_RECEIPT_SHA256
        or len(raw) != PR119_RECEIPT_SIZE
    ):
        raise _error("PR119 receipt identity changed")
    if _git_blob_sha(Path(pr119.__file__)) != PR119_QUALIFICATION_BLOB_SHA:
        raise _error("PR119 qualification implementation blob changed")
    if pr119.NEXT_REQUIRED_BOUNDARY != (
        "PRE_REGISTER_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL"
    ):
        raise _error("PR119 next boundary changed")
    if receipt["materialization"]["history_row_count"] != FROZEN_HISTORY_ROW_COUNT:
        raise _error("PR119 frozen history row count changed")
    if receipt["source_evidence"]["historical_request_date_end"] != HISTORICAL_REQUEST_DATE_END:
        raise _error("PR119 historical ceiling changed")
    if receipt["source_evidence"]["pr80_source_local_semantic_equivalence"] != "UNPROVEN":
        raise _error("PR119 source-local semantic boundary changed")
    if receipt["materialization"]["pr80_constructor_input_authorized"] is not False:
        raise _error("PR119 unexpectedly authorized PR80 input")

    if pr69.SOURCE != "football_data_uk_csv":
        raise _error("PR69 source identity changed")
    if pr69.SOURCE_LOCAL_TIMEZONE_UNRESOLVED != "SOURCE_LOCAL_TIMEZONE_UNRESOLVED":
        raise _error("PR69 source-local timezone is no longer the frozen unresolved state")
    if _git_blob_sha(Path(pr69.__file__)) != PR69_REPLAY_BLOB_SHA:
        raise _error("PR69 replay implementation blob changed")

    if pr80.SOURCE_LOCAL_TIME_BASIS != "SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY":
        raise _error("PR80 source-local time basis changed")
    if _git_blob_sha(Path(pr80.__file__)) != PR80_CONSTRUCTOR_BLOB_SHA:
        raise _error("PR80 constructor implementation blob changed")

    semantic = pr78.build_successor_live_input_semantic_qualification_protocol()
    if _git_blob_sha(Path(pr78.__file__)) != PR78_SEMANTIC_PROTOCOL_BLOB_SHA:
        raise _error("PR78 semantic protocol implementation blob changed")
    if semantic.form_semantics.chronology != "STRICTLY_PRIOR_FIXTURES_ORDERED_KICKOFF_DESCENDING":
        raise _error("PR78 form chronology changed")
    if semantic.elo_semantics.chronology != (
        "SOURCE_LOCAL_KICKOFF_ASC_THEN_FIXTURE_IDENTIFIER_ASC_PREMATCH_STATE_ONLY"
    ):
        raise _error("PR78 Elo chronology changed")
    if semantic.fatigue_semantics.chronology != "MOST_RECENT_STRICTLY_PRIOR_FIXTURE_PER_TEAM":
        raise _error("PR78 fatigue chronology changed")
    if semantic.fatigue_semantics.rest_day_measure != "DATETIME_DELTA_DAYS_INTEGER_COMPONENT":
        raise _error("PR78 fatigue rest-day measure changed")
    if semantic.fatigue_semantics.orientation != "HOME_REST_DAYS_MINUS_AWAY_REST_DAYS":
        raise _error("PR78 fatigue orientation changed")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "ancestry": {
            "pr119_receipt_sha256": PR119_RECEIPT_SHA256,
            "pr119_receipt_size_bytes": PR119_RECEIPT_SIZE,
            "pr119_qualification_blob_sha": PR119_QUALIFICATION_BLOB_SHA,
            "pr80_constructor_blob_sha": PR80_CONSTRUCTOR_BLOB_SHA,
            "pr69_replay_blob_sha": PR69_REPLAY_BLOB_SHA,
            "pr78_semantic_protocol_blob_sha": PR78_SEMANTIC_PROTOCOL_BLOB_SHA,
        },
        "frozen_scope": {
            "source_namespace": SOURCE_NAMESPACE,
            "history_row_count": FROZEN_HISTORY_ROW_COUNT,
            "historical_request_date_end": HISTORICAL_REQUEST_DATE_END,
            "model_league_codes": list(MODEL_LEAGUE_CODES),
            "full_athena_competition_universe_claimed": False,
            "dates_after_historical_ceiling_authorized": False,
            "target_specific_pr80_construction_authorized": False,
            "global_fotmob_historical_coverage_promoted": False,
        },
        "reference_semantics": {
            "pr69_source": "football_data_uk_csv",
            "pr69_source_local_timezone": "SOURCE_LOCAL_TIMEZONE_UNRESOLVED",
            "pr69_date_formats": ["%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"],
            "pr69_time_formats": ["%H:%M", "%H:%M:%S", "%H.%M"],
            "pr69_local_kickoff_type": "NAIVE_DATETIME_COMBINED_FROM_SOURCE_DATE_AND_SOURCE_TIME",
            "pr80_source_local_time_basis": "SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY",
            "pr80_form_chronology": "STRICTLY_PRIOR_FIXTURES_ORDERED_KICKOFF_DESCENDING",
            "pr80_elo_chronology": "SOURCE_LOCAL_KICKOFF_ASC_THEN_FIXTURE_IDENTIFIER_ASC_PREMATCH_STATE_ONLY",
            "pr80_fatigue_chronology": "MOST_RECENT_STRICTLY_PRIOR_FIXTURE_PER_TEAM",
            "pr80_fatigue_rest_day_measure": "DATETIME_DELTA_DAYS_INTEGER_COMPONENT",
            "pr80_fatigue_orientation": "HOME_REST_DAYS_MINUS_AWAY_REST_DAYS",
        },
        "candidate_semantics": {
            "canonical_kickoff_field": "status.utcTime",
            "source_display_time_basis": "Europe/Oslo",
            "source_local_kickoff_derivation": "CANONICAL_KICKOFF_UTC_TO_EUROPE_OSLO_THEN_NAIVE_DISPLAY_TIME_CANDIDATE",
            "pr119_source_local_utc_global_order_disagreement_count": 0,
            "pr119_same_team_same_source_local_kickoff_conflict_count": 0,
            "pr119_same_team_same_utc_kickoff_conflict_count": 0,
            "pr119_source_local_semantic_equivalence": "UNPROVEN",
            "pr119_pr80_constructor_input_authorized": False,
        },
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "admissible_evidence": list(ADMISSIBLE_EVIDENCE),
        "forbidden_shortcuts": list(FORBIDDEN_SHORTCUTS),
        "qualification_status_vocabulary": list(QUALIFICATION_STATUS_VOCABULARY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    ancestry: Mapping[str, Any]
    frozen_scope: Mapping[str, Any]
    reference_semantics: Mapping[str, Any]
    candidate_semantics: Mapping[str, Any]
    qualification_requirements: tuple[str, ...]
    admissible_evidence: tuple[str, ...]
    forbidden_shortcuts: tuple[str, ...]
    qualification_status_vocabulary: tuple[str, ...]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _payload():
            raise _error("protocol differs from the exact frozen pre-registration contract")
        object.__setattr__(self, "ancestry", types.MappingProxyType(dict(self.ancestry)))
        object.__setattr__(self, "frozen_scope", types.MappingProxyType(dict(self.frozen_scope)))
        object.__setattr__(
            self, "reference_semantics", types.MappingProxyType(dict(self.reference_semantics))
        )
        object.__setattr__(
            self, "candidate_semantics", types.MappingProxyType(dict(self.candidate_semantics))
        )
        object.__setattr__(self, "safety", _safety())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_scope": self.protocol_scope,
            "protocol_state": self.protocol_state,
            "repository_main_sha": self.repository_main_sha,
            "ancestry": dict(self.ancestry),
            "frozen_scope": dict(self.frozen_scope),
            "reference_semantics": dict(self.reference_semantics),
            "candidate_semantics": dict(self.candidate_semantics),
            "qualification_requirements": list(self.qualification_requirements),
            "admissible_evidence": list(self.admissible_evidence),
            "forbidden_shortcuts": list(self.forbidden_shortcuts),
            "qualification_status_vocabulary": list(self.qualification_status_vocabulary),
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_fotmob_pr80_source_local_time_semantic_equivalence_protocol(
) -> FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol:
    """Build and revalidate the exact result-free pre-registration."""
    _verify_upstream()
    value = FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol(
        schema_version=SCHEMA_VERSION,
        protocol_id=PROTOCOL_ID,
        protocol_scope=PROTOCOL_SCOPE,
        protocol_state=PROTOCOL_STATE,
        repository_main_sha=REPOSITORY_MAIN_SHA,
        ancestry=_payload()["ancestry"],
        frozen_scope=_payload()["frozen_scope"],
        reference_semantics=_payload()["reference_semantics"],
        candidate_semantics=_payload()["candidate_semantics"],
        qualification_requirements=QUALIFICATION_REQUIREMENTS,
        admissible_evidence=ADMISSIBLE_EVIDENCE,
        forbidden_shortcuts=FORBIDDEN_SHORTCUTS,
        qualification_status_vocabulary=QUALIFICATION_STATUS_VOCABULARY,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_safety(),
    )
    exact = canonical_fotmob_pr80_source_local_time_semantic_equivalence_protocol_bytes(value)
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("canonical protocol identity changed")
    return value


def canonical_fotmob_pr80_source_local_time_semantic_equivalence_protocol_bytes(
    value: Any,
) -> bytes:
    if type(value) is not FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol:
        raise _error("value must be exact FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("protocol failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_fotmob_pr80_source_local_time_semantic_equivalence_protocol(value: Any) -> str:
    return hashlib.sha256(
        canonical_fotmob_pr80_source_local_time_semantic_equivalence_protocol_bytes(value)
    ).hexdigest()


__all__ = [
    "ADMISSIBLE_EVIDENCE",
    "FORBIDDEN_SHORTCUTS",
    "FROZEN_HISTORY_ROW_COUNT",
    "HISTORICAL_REQUEST_DATE_END",
    "MODEL_LEAGUE_CODES",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "QUALIFICATION_REQUIREMENTS",
    "QUALIFICATION_STATUS_VOCABULARY",
    "REPOSITORY_MAIN_SHA",
    "SAFETY_KEYS",
    "SOURCE_NAMESPACE",
    "FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol",
    "FotMobPR80SourceLocalTimeSemanticEquivalenceProtocolError",
    "build_fotmob_pr80_source_local_time_semantic_equivalence_protocol",
    "canonical_fotmob_pr80_source_local_time_semantic_equivalence_protocol_bytes",
    "sha256_fotmob_pr80_source_local_time_semantic_equivalence_protocol",
]
