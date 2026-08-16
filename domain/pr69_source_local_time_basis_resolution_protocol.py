"""Pre-register resolution of the exact PR #69 source-local time basis.

This protocol is deliberately result-free. It freezes what evidence and proof
would be sufficient to resolve the football-data.co.uk source-local wall-clock
basis inherited by PR #69, after PR #121 correctly failed closed. It does not
infer a timezone, compare FotMob clocks, authorize PR #80 construction, or
create model, probability, pricing, selection, production, or betting authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import domain.fotmob_pr80_source_local_time_semantic_equivalence_qualification as pr121
import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.historical_model_feature_replay_candidate as pr69


SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_PROTOCOL_V1"
PROTOCOL_SCOPE = (
    "PRE_REGISTERED_EXACT_PR69_FOOTBALL_DATA_UK_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_ONLY"
)
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_PR69_SOURCE_LOCAL_TIME_BASIS_UNRESOLVED"
REPOSITORY_MAIN_SHA = "06ae83b0305f2080be5a875987f8a77e2a8b31dc"
NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_QUALIFICATION"

PR121_RECEIPT_SHA256 = "8d057e96504a83237b719b3a465e29b7df74e2b6c3630fc1d97e8a2a7bdfb5fb"
PR121_RECEIPT_SIZE = 3_599
PR121_QUALIFICATION_BLOB_SHA = "98c53095f56515975ae4b07194ffbe27749a7f53"
PR120_PROTOCOL_BLOB_SHA = "e07616e99c0beaf2a95bcaec96d02616b21c378f"
PR120_PROTOCOL_SHA256 = "a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918"
PR120_PROTOCOL_SIZE = 5_242
PR69_REPLAY_BLOB_SHA = "b67a7e52954f47cc90c578ad193545c541984964"
PR114_RECEIPT_SHA256 = "fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110"
PR114_RECEIPT_SIZE = 24_428
PR69_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
PR69_CANONICAL_REPLAY_SHA256 = "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
PR69_CANONICAL_REPLAY_SIZE = 39_952_730
PR69_SOURCE_FILE_COUNT = 66
PR69_SOURCE_TOTAL_BYTES = 10_006_877
PR69_SOURCE_FIXTURE_COUNT = 21_226

SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
MODEL_LEAGUE_CODES = (
    "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
)

DIRECT_REFERENCE_MODEL_SHAPES = (
    "UTC_WITH_EXPLICIT_PRIMARY_SOURCE_RULE",
    "FIXED_OFFSET_WITH_EXPLICIT_PRIMARY_SOURCE_RULE",
    "NAMED_IANA_ZONE_WITH_EXPLICIT_PRIMARY_SOURCE_RULE",
    "COMPETITION_OR_SOURCE_DEFINED_LOCAL_CIVIL_TIME_WITH_EXPLICIT_DETERMINISTIC_MAPPING_RULE",
)

QUALIFICATION_REQUIREMENTS = (
    "REVALIDATE_EXACT_PR121_BLOCKER_AND_PR69_PR114_SOURCE_CORPUS_ANCESTRY_BEFORE_EVIDENCE_INTERPRETATION",
    "INVENTORY_ALL_66_EXACT_PR69_SOURCE_FILES_AND_PRESERVE_THEIR_RAW_DATE_TIME_TEXT_WITHOUT_NORMALIZATION",
    "ACQUIRE_OR_REUSE_ONLY_PROVENANCED_PRIMARY_FOOTBALL_DATA_UK_TIME_SEMANTICS_OR_A_FORMAL_INVARIANCE_PROOF_BUNDLE",
    "CLASSIFY_PRIMARY_TIME_BASIS_EVIDENCE_BY_EFFECTIVE_SCOPE_PERIOD_AND_VERSION_BEFORE_APPLYING_IT_TO_SOURCE_ROWS",
    "REQUIRE_ANY_DIRECT_REFERENCE_RULE_TO_DETERMINISTICALLY_MAP_EVERY_RELEVANT_PR69_ROW_WITHOUT_COUNTRY_VENUE_OR_CROSS_SOURCE_GUESSING",
    "FAIL_CLOSED_ON_PRIMARY_EVIDENCE_CONFLICT_MISSING_EFFECTIVE_PERIOD_OR_UNMAPPED_SOURCE_ROWS",
    "IF_DIRECT_REFERENCE_SEMANTICS_CANNOT_BE_RECOVERED_REQUIRE_FORMAL_OPERATIONAL_INVARIANCE_ACROSS_EVERY_ADMISSIBLE_REFERENCE_TRANSFORMATION",
    "PROVE_ALL_INVARIANCE_ASSUMPTIONS_FROM_ADMISSIBLE_EVIDENCE_RATHER_THAN_FROM_EQUAL_OBSERVED_FEATURE_OUTPUTS",
    "DO_NOT_COMPARE_FOTMOB_EUROPE_OSLO_TO_PR69_AS_REFERENCE_EVIDENCE_BEFORE_THIS_BOUNDARY_IS_RESOLVED",
    "PRESERVE_PR69_NAIVE_SOURCE_LOCAL_DATETIME_SEMANTICS_AND_DO_NOT_REWRITE_HISTORICAL_BYTES_OR_FIXTURE_IDENTITIES",
)

ADMISSIBLE_EVIDENCE = (
    "EXACT_FROZEN_PR69_RAW_SOURCE_BYTES_AND_PR114_HASHED_REBUILD_EVIDENCE",
    "PRIMARY_FOOTBALL_DATA_UK_DOCUMENTATION_OR_DATA_DICTIONARY_WITH_EXACT_URL_CAPTURE_TIME_RAW_BYTES_HASH_AND_EFFECTIVE_SCOPE",
    "ARCHIVED_COPY_OF_PRIMARY_FOOTBALL_DATA_UK_CONTENT_ONLY_WHEN_ORIGIN_PROVENANCE_AND_CAPTURE_BYTES_ARE_PRESERVED",
    "PRIMARY_SOURCE_FILE_METADATA_OR_EMBEDDED_SEMANTICS_ONLY_WHEN_PRESENT_IN_THE_EXACT_PRESERVED_BYTES",
    "FORMAL_OPERATIONAL_INVARIANCE_PROOF_WITH_MACHINE_CHECKABLE_ASSUMPTIONS_AND_ALL_ASSUMPTIONS_PROVEN_FOR_THE_FROZEN_SCOPE",
)

FORBIDDEN_SHORTCUTS = (
    "DO_NOT_INFER_TIMEZONE_FROM_LEAGUE_COUNTRY_TEAM_VENUE_OR_COMMON_FOOTBALL_PRACTICE",
    "DO_NOT_TREAT_FOTMOB_EUROPE_OSLO_OR_ANY_OTHER_CROSS_SOURCE_CLOCK_AS_THE_PR69_REFERENCE",
    "DO_NOT_TREAT_EQUAL_KICKOFF_ORDER_EQUAL_FEATURE_VALUES_OR_ZERO_OBSERVED_DISAGREEMENTS_AS_REFERENCE_BASIS_EVIDENCE",
    "DO_NOT_USE_SEARCH_SNIPPETS_BLOGS_MIRRORS_FORUMS_OR_SECONDARY_INTERPRETATIONS_AS_AUTHORITY",
    "DO_NOT_BACKFILL_MISSING_TIMEZONE_SEMANTICS_FROM_CURRENT_PROVIDER_BEHAVIOR_UNLESS_PRIMARY_EVIDENCE_EXPLICITLY_COVERS_THE_HISTORICAL_SCOPE",
    "DO_NOT_SALT_REWRITE_REFORMAT_OR_MUTATE_SOURCE_BYTES_TO_CREATE_TIME_BASIS_EVIDENCE",
    "DO_NOT_RESOLVE_CONFLICTING_PRIMARY_EVIDENCE_BY_MAJORITY_VOTE_OR_RESULT_FIT",
    "DO_NOT_AUTHORIZE_PR80_MODEL_PROBABILITY_PRICING_SELECTION_PRODUCTION_OR_BET_FROM_THIS_PRE_REGISTRATION",
)

QUALIFICATION_STATUS_VOCABULARY = (
    "QUALIFIED_DIRECT_PRIMARY_SOURCE_TIME_BASIS",
    "QUALIFIED_FORMAL_OPERATIONAL_INVARIANCE_WITHOUT_NAMED_TIMEZONE",
    "BLOCKED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE",
    "BLOCKED_PRIMARY_EVIDENCE_CONFLICT",
    "BLOCKED_TIME_BASIS_SCOPE_OR_EFFECTIVE_PERIOD_AMBIGUOUS",
    "BLOCKED_UNMAPPED_PR69_SOURCE_ROWS",
    "BLOCKED_INVARIANCE_ASSUMPTIONS_UNPROVEN",
    "BLOCKED_ANCESTRY_OR_SOURCE_CORPUS_MISMATCH",
)

SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "calibration_for_production_authorized",
        "expected_goals_production_authorized",
        "expected_goals_transform_approved",
        "market_activation_authorized",
        "model_training_authorized",
        "pr69_source_local_time_basis_resolved",
        "pr80_constructor_input_authorized",
        "pricing_authorized",
        "probability_adjustment_authorized",
        "probability_inference_authorized",
        "production_approval_authorized",
        "score_matrix_authorized",
        "selection_authorized",
        "source_local_time_semantic_equivalence_qualified",
        "successor_candidate_approved",
        "successor_live_inputs_qualified",
    }
)

PROTOCOL_SHA256 = "d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a"
PROTOCOL_SIZE = 6_983


class PR69SourceLocalTimeBasisResolutionProtocolError(ValueError):
    """Raised when the exact pre-registration contract no longer revalidates."""


def _error(message: str) -> PR69SourceLocalTimeBasisResolutionProtocolError:
    return PR69SourceLocalTimeBasisResolutionProtocolError(message)


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
        raise _error("PR69 source-local time protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(SAFETY_KEYS)})


def _verify_upstream() -> None:
    r121 = pr121.load_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt()
    r121_raw = (
        pr121.canonical_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt_bytes()
    )
    if (
        pr121.RECEIPT_SHA256 != PR121_RECEIPT_SHA256
        or pr121.RECEIPT_SIZE != PR121_RECEIPT_SIZE
        or hashlib.sha256(r121_raw).hexdigest() != PR121_RECEIPT_SHA256
        or len(r121_raw) != PR121_RECEIPT_SIZE
    ):
        raise _error("PR121 receipt identity changed")
    if _git_blob_sha(Path(pr121.__file__)) != PR121_QUALIFICATION_BLOB_SHA:
        raise _error("PR121 qualification implementation blob changed")
    if r121.get("remaining_blockers") != ["BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"]:
        raise _error("PR121 blocker changed")
    if r121.get("next_required_boundary") != (
        "PRE_REGISTER_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_PROTOCOL"
    ):
        raise _error("PR121 next boundary changed")
    if r121.get("reference_gate", {}).get("reference_basis_resolved") is not False:
        raise _error("PR121 unexpectedly resolved the reference basis")
    if r121.get("reference_gate", {}).get("source_independent_invariance_proven") is not False:
        raise _error("PR121 unexpectedly proved source-independent invariance")
    if r121.get("protocol") != {
        "protocol_id": "REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL_V1",
        "blob_sha": PR120_PROTOCOL_BLOB_SHA,
        "canonical_sha256": PR120_PROTOCOL_SHA256,
        "canonical_size_bytes": PR120_PROTOCOL_SIZE,
    }:
        raise _error("PR120 ancestry changed inside PR121")

    if pr69.SOURCE != "football_data_uk_csv":
        raise _error("PR69 source identity changed")
    if pr69.SOURCE_LOCAL_TIMEZONE_UNRESOLVED != "SOURCE_LOCAL_TIMEZONE_UNRESOLVED":
        raise _error("PR69 source-local timezone state changed")
    if _git_blob_sha(Path(pr69.__file__)) != PR69_REPLAY_BLOB_SHA:
        raise _error("PR69 replay implementation blob changed")

    r114 = pr114.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    r114_raw = (
        pr114.canonical_fotmob_source_history_elo_initialization_boundary_qualification_receipt_bytes()
    )
    if (
        pr114.RECEIPT_SHA256 != PR114_RECEIPT_SHA256
        or pr114.RECEIPT_SIZE != PR114_RECEIPT_SIZE
        or hashlib.sha256(r114_raw).hexdigest() != PR114_RECEIPT_SHA256
        or len(r114_raw) != PR114_RECEIPT_SIZE
    ):
        raise _error("PR114 receipt identity changed")
    rebuild = r114.get("pr69_rebuild", {}).get("checks")
    if rebuild != {
        "canonical_replay_sha256": PR69_CANONICAL_REPLAY_SHA256,
        "canonical_replay_size_bytes": PR69_CANONICAL_REPLAY_SIZE,
        "fixture_count": PR69_SOURCE_FIXTURE_COUNT,
        "source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
        "source_file_count": PR69_SOURCE_FILE_COUNT,
        "source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
    }:
        raise _error("exact PR69 source corpus ancestry changed")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "ancestry": {
            "pr121_receipt_sha256": PR121_RECEIPT_SHA256,
            "pr121_receipt_size_bytes": PR121_RECEIPT_SIZE,
            "pr121_qualification_blob_sha": PR121_QUALIFICATION_BLOB_SHA,
            "pr120_protocol_blob_sha": PR120_PROTOCOL_BLOB_SHA,
            "pr120_protocol_sha256": PR120_PROTOCOL_SHA256,
            "pr120_protocol_size_bytes": PR120_PROTOCOL_SIZE,
            "pr69_replay_blob_sha": PR69_REPLAY_BLOB_SHA,
            "pr114_receipt_sha256": PR114_RECEIPT_SHA256,
            "pr114_receipt_size_bytes": PR114_RECEIPT_SIZE,
            "pr69_source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
            "pr69_canonical_replay_sha256": PR69_CANONICAL_REPLAY_SHA256,
            "pr69_canonical_replay_size_bytes": PR69_CANONICAL_REPLAY_SIZE,
        },
        "frozen_pr69_scope": {
            "source": "football_data_uk_csv",
            "source_local_timezone_state": "SOURCE_LOCAL_TIMEZONE_UNRESOLVED",
            "source_local_kickoff_type": "NAIVE_DATETIME_COMBINED_FROM_SOURCE_DATE_AND_SOURCE_TIME",
            "source_file_count": PR69_SOURCE_FILE_COUNT,
            "source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
            "source_fixture_count": PR69_SOURCE_FIXTURE_COUNT,
            "seasons": list(SEASONS),
            "model_league_codes": list(MODEL_LEAGUE_CODES),
            "full_athena_competition_universe_claimed": False,
        },
        "direct_resolution_contract": {
            "accepted_reference_model_shapes": list(DIRECT_REFERENCE_MODEL_SHAPES),
            "must_cover_every_relevant_pr69_row": True,
            "must_define_dst_or_offset_transition_semantics_when_applicable": True,
            "must_define_effective_period_and_version_scope": True,
            "must_be_executable_without_cross_source_identity_inference": True,
            "raw_source_time_text_remains_immutable": True,
            "named_timezone_required": False,
        },
        "invariance_route_contract": {
            "available_only_if_direct_primary_semantics_not_recovered": True,
            "must_enumerate_every_admissible_reference_transformation": True,
            "must_prove_strict_prior_membership_invariance": True,
            "must_prove_form_ordering_and_tiebreak_invariance": True,
            "must_prove_elo_ordering_and_tiebreak_invariance": True,
            "must_prove_most_recent_prior_fixture_invariance": True,
            "must_prove_integer_datetime_delta_days_invariance": True,
            "must_prove_home_minus_away_rest_difference_invariance": True,
            "must_prove_fatigue_bucket_invariance": True,
            "equal_numeric_outputs_without_proven_assumptions_are_insufficient": True,
        },
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "admissible_evidence": list(ADMISSIBLE_EVIDENCE),
        "forbidden_shortcuts": list(FORBIDDEN_SHORTCUTS),
        "qualification_status_vocabulary": list(QUALIFICATION_STATUS_VOCABULARY),
        "execution_output_contract": {
            "evidence_inventory_required": True,
            "primary_evidence_conflict_table_required": True,
            "row_coverage_accounting_required": True,
            "resolution_rule_or_invariance_proof_required_for_positive_status": True,
            "fotmob_equivalence_assessment_performed": False,
            "pr80_constructor_input_authorized": False,
            "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        },
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class PR69SourceLocalTimeBasisResolutionProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    ancestry: Mapping[str, Any]
    frozen_pr69_scope: Mapping[str, Any]
    direct_resolution_contract: Mapping[str, Any]
    invariance_route_contract: Mapping[str, Any]
    qualification_requirements: tuple[str, ...]
    admissible_evidence: tuple[str, ...]
    forbidden_shortcuts: tuple[str, ...]
    qualification_status_vocabulary: tuple[str, ...]
    execution_output_contract: Mapping[str, Any]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _payload():
            raise _error("protocol differs from the exact frozen pre-registration contract")
        for name in (
            "ancestry",
            "frozen_pr69_scope",
            "direct_resolution_contract",
            "invariance_route_contract",
            "execution_output_contract",
        ):
            object.__setattr__(self, name, types.MappingProxyType(dict(getattr(self, name))))
        object.__setattr__(self, "safety", _safety())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_scope": self.protocol_scope,
            "protocol_state": self.protocol_state,
            "repository_main_sha": self.repository_main_sha,
            "ancestry": dict(self.ancestry),
            "frozen_pr69_scope": dict(self.frozen_pr69_scope),
            "direct_resolution_contract": dict(self.direct_resolution_contract),
            "invariance_route_contract": dict(self.invariance_route_contract),
            "qualification_requirements": list(self.qualification_requirements),
            "admissible_evidence": list(self.admissible_evidence),
            "forbidden_shortcuts": list(self.forbidden_shortcuts),
            "qualification_status_vocabulary": list(self.qualification_status_vocabulary),
            "execution_output_contract": dict(self.execution_output_contract),
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_pr69_source_local_time_basis_resolution_protocol() -> PR69SourceLocalTimeBasisResolutionProtocol:
    """Build and fully revalidate the exact result-free pre-registration."""
    _verify_upstream()
    payload = _payload()
    value = PR69SourceLocalTimeBasisResolutionProtocol(
        schema_version=SCHEMA_VERSION,
        protocol_id=PROTOCOL_ID,
        protocol_scope=PROTOCOL_SCOPE,
        protocol_state=PROTOCOL_STATE,
        repository_main_sha=REPOSITORY_MAIN_SHA,
        ancestry=payload["ancestry"],
        frozen_pr69_scope=payload["frozen_pr69_scope"],
        direct_resolution_contract=payload["direct_resolution_contract"],
        invariance_route_contract=payload["invariance_route_contract"],
        qualification_requirements=QUALIFICATION_REQUIREMENTS,
        admissible_evidence=ADMISSIBLE_EVIDENCE,
        forbidden_shortcuts=FORBIDDEN_SHORTCUTS,
        qualification_status_vocabulary=QUALIFICATION_STATUS_VOCABULARY,
        execution_output_contract=payload["execution_output_contract"],
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_safety(),
    )
    raw = canonical_pr69_source_local_time_basis_resolution_protocol_bytes(value)
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256 or len(raw) != PROTOCOL_SIZE:
        raise _error("canonical protocol identity changed")
    return value


def canonical_pr69_source_local_time_basis_resolution_protocol_bytes(value: Any) -> bytes:
    if type(value) is not PR69SourceLocalTimeBasisResolutionProtocol:
        raise _error("value must be exact PR69SourceLocalTimeBasisResolutionProtocol")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("protocol failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_pr69_source_local_time_basis_resolution_protocol(value: Any) -> str:
    return hashlib.sha256(canonical_pr69_source_local_time_basis_resolution_protocol_bytes(value)).hexdigest()


__all__ = [
    "ADMISSIBLE_EVIDENCE",
    "DIRECT_REFERENCE_MODEL_SHAPES",
    "FORBIDDEN_SHORTCUTS",
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
    "SEASONS",
    "PR69SourceLocalTimeBasisResolutionProtocol",
    "PR69SourceLocalTimeBasisResolutionProtocolError",
    "build_pr69_source_local_time_basis_resolution_protocol",
    "canonical_pr69_source_local_time_basis_resolution_protocol_bytes",
    "sha256_pr69_source_local_time_basis_resolution_protocol",
]
