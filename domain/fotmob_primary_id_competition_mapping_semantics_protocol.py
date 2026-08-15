"""Pre-register generic FotMob ``primaryId`` competition-family mapping semantics.

This boundary freezes source-scoped competition identity semantics before any
post-campaign qualification is allowed.  The eleven domestic leagues discovered
by the PR #105 campaign are the initial proof set only; they are deliberately not
encoded as ATHENA's final competition universe.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import domain.fotmob_ordinary_ft_source_history_acquisition_protocol as pr101


SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_PROTOCOL_V1"
PROTOCOL_SCOPE = (
    "PRE_REGISTERED_GENERIC_FOTMOB_COMPETITION_IDENTITY_SEMANTICS_ONLY_NO_QUALIFICATION"
)
PROTOCOL_STATE = "PRE_REGISTERED_NOT_QUALIFIED_NO_MAPPING_PROMOTION"
REPOSITORY_MAIN_SHA = "6090bb46ef1a5662ddcec2761e3524647d83ba2e"

PR105_RECEIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "research-manifests"
    / "fotmob-ordinary-ft-source-history-campaign-completeness-receipt-v1.json"
)
PR105_RECEIPT_BLOB_SHA = "6e60a5da12e5a5ac35ce31ca0a133df7959ca1f7"
PR105_RECEIPT_SHA256 = (
    "a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363"
)
PR105_RECEIPT_SIZE = 11_995

PR101_PROTOCOL_BLOB_SHA = "39541b351d2990f7ebb9572a8c9c674c85864284"
PR101_PROTOCOL_SHA256 = (
    "cfd8542df66c9e8fbe748f0559d67c336d41e441f3b4de8d6601ac1087cad3a6"
)
PR101_PROTOCOL_SIZE = 8_511

SOURCE = "fotmob"
SOURCE_FIELD = "primaryId"
INITIAL_PROOF_SET_ROLE = "ELEVEN_DOMESTIC_LEAGUES_INITIAL_QUALIFICATION_PROOF_SET_ONLY"
INITIAL_QUALIFICATION_STATE = "PRE_REGISTERED_INITIAL_PROOF_SET_NOT_YET_QUALIFIED"

SUPPORTED_COMPETITION_CLASSES = (
    "DOMESTIC_LEAGUE",
    "DOMESTIC_CUP",
    "DOMESTIC_LEAGUE_CUP",
    "CONTINENTAL_CLUB",
    "INTERNATIONAL_TOURNAMENT",
    "INTERNATIONAL_QUALIFIER",
    "INTERNATIONAL_FRIENDLY",
    "OTHER_REVIEW_REQUIRED",
)

IDENTITY_RULES = (
    "FOTMOB_PRIMARY_ID_IS_SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY_ONLY_AND_MUST_NOT_BE_PROMOTED_TO_GLOBAL_CROSS_PROVIDER_IDENTITY",
    "WRAPPER_LEAGUE_ID_IS_SEASON_PHASE_OR_PRESENTATION_IDENTITY_AND_MAY_VARY_WITHIN_ONE_PRIMARY_ID_FAMILY_ONLY_AFTER_SEPARATE_QUALIFICATION",
    "DISPLAY_NAME_IS_METADATA_ONLY_AND_MUST_NEVER_BE_THE_SOLE_IDENTITY_KEY",
    "MISSING_OR_MALFORMED_PRIMARY_ID_BLOCKS_MAPPING_QUALIFICATION_AND_MUST_NOT_FALL_BACK_TO_NAME_OR_WRAPPER_ID",
    "A_PRIMARY_ID_MUST_NOT_MAP_TO_MULTIPLE_INCOMPATIBLE_ATHENA_COMPETITION_FAMILIES",
    "DOMESTIC_COMPETITION_MAPPING_REQUIRES_COUNTRY_LINEAGE_TO_MATCH_THE_PRE_REGISTERED_EXPECTATION",
    "CONTINENTAL_OR_INTERNATIONAL_COMPETITIONS_MAY_NOT_INHERIT_A_DOMESTIC_COUNTRY_RULE_AND_REQUIRE_SEPARATELY_REVIEWED_ORGANIZER_REGION_AND_COMPETITION_CLASS_EVIDENCE",
    "WRAPPER_ID_OR_NAME_DRIFT_MAY_BE_ACCEPTED_ONLY_WHEN_PRIMARY_ID_LINEAGE_IS_STABLE_AND_NO_COLLISION_OR_SEMANTIC_CONFLICT_IS_OBSERVED",
    "ANY_PRIMARY_ID_COLLISION_COUNTRY_CONFLICT_OR_COMPETITION_CLASS_CONFLICT_FAILS_CLOSED",
    "PRIMARY_ID_MAPPING_QUALIFICATION_ESTABLISHES_SOURCE_COMPETITION_IDENTITY_ONLY_NOT_MODEL_CALIBRATION_OR_BETTING_ELIGIBILITY",
)

COMPETITION_UNIVERSE_RULES = (
    "THE_ELEVEN_DOMESTIC_LEAGUES_ARE_THE_INITIAL_HISTORICAL_QUALIFICATION_PROOF_SET_ONLY_NOT_THE_FINAL_ATHENA_COMPETITION_UNIVERSE",
    "THE_COMPETITION_IDENTITY_CONTRACT_MUST_SUPPORT_FUTURE_DOMESTIC_LEAGUES_DOMESTIC_CUPS_LEAGUE_CUPS_CONTINENTAL_CLUB_COMPETITIONS_AND_INTERNATIONAL_COMPETITIONS_WITHOUT_REDEFINING_PRIMARY_ID_SEMANTICS",
    "NEW_FOTMOB_COMPETITIONS_MAY_ENTER_DISCOVERY_AS_UNQUALIFIED_CANDIDATES_WITHOUT_BEING_DROPPED_OR_FORCED_INTO_AN_EXISTING_MODEL_LEAGUE_CODE",
    "EVERY_NEW_COMPETITION_FAMILY_REQUIRES_EXPLICIT_REVIEWED_MAPPING_QUALIFICATION_BEFORE_HISTORICAL_REPLAY_MODEL_TRAINING_OR_CALIBRATION_USE",
    "CHAMPIONS_LEAGUE_EUROPA_LEAGUE_CONFERENCE_LEAGUE_DOMESTIC_CUPS_AND_INTERNATIONAL_MATCHES_ARE_NOT_EXCLUDED_BY_THIS_PROTOCOL_BUT_ARE_NOT_QUALIFIED_BY_THE_INITIAL_ELEVEN_LEAGUE_PROOF_SET",
    "COMPETITION_STAGE_PHASE_LEG_TIE_NEUTRAL_VENUE_AND_TOURNAMENT_CONTEXT_REMAIN_SEPARATE_DOWNSTREAM_CONTEXT_FIELDS_AND_ARE_NOT_INFERRED_FROM_PRIMARY_ID_ALONE",
    "UNKNOWN_OR_UNQUALIFIED_COMPETITIONS_REMAIN_VISIBLE_AS_SOURCE_EVIDENCE_AND_FAIL_CLOSED_FOR_ANY_DOWNSTREAM_USE_REQUIRING_QUALIFIED_COMPETITION_IDENTITY",
)

QUALIFICATION_RULES = (
    "QUALIFICATION_MUST_EXECUTE_AGAINST_THE_PRESERVED_PR105_CAMPAIGN_EVIDENCE_WITHOUT_NETWORK_REACQUISITION_OR_POST_HOC_RULE_CHANGES",
    "THE_INITIAL_ELEVEN_CANDIDATES_MUST_MATCH_EXACT_PRIMARY_ID_AND_EXPECTED_COUNTRY_LINEAGE",
    "ALL_OBSERVED_WRAPPER_LEAGUE_IDS_AND_NAME_VARIANTS_FOR_A_CANDIDATE_MUST_BE_ACCOUNTED_FOR_BEFORE_THAT_CANDIDATE_CAN_PASS",
    "NO_CANDIDATE_PASSES_IF_THE_SAME_PRIMARY_ID_IS_OBSERVED_WITH_CONTRADICTORY_COUNTRY_LINEAGE_OR_INCOMPATIBLE_COMPETITION_FAMILY_EVIDENCE",
    "QUALIFICATION_RESULT_MUST_BE_REPRODUCIBLE_CANONICALLY_HASHED_AND_PRESERVE_CONFLICTS_INSTEAD_OF_SELECTING_A_CONVENIENT_VALUE",
    "PARTIAL_SUCCESS_DOES_NOT_PROMOTE_HISTORICAL_COVERAGE_FOR_FAILED_OR_UNQUALIFIED_COMPETITION_FAMILIES",
    "THIS_PROTOCOL_DOES_NOT_DISPOSITION_AWARDED_EXTRA_TIME_PENALTY_REARRANGED_OR_INITIALIZATION_BOUNDARY_BLOCKERS",
)

NEXT_REQUIRED_BOUNDARY = (
    "QUALIFY_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_AGAINST_PRESERVED_CAMPAIGN_EVIDENCE"
)

_SAFETY_KEYS = frozenset(
    {
        "primary_id_mapping_qualified",
        "competition_registry_mutation_authorized",
        "expanded_competition_universe_authorized",
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
        "model_training_authorized",
    }
)

PROTOCOL_SHA256 = "6d3e6083325853b481fe2a5ad928d67c5fe7cb46d25f5c33024146855c6e725e"
PROTOCOL_SIZE = 7_370


class FotMobPrimaryIdCompetitionMappingSemanticsProtocolError(ValueError):
    """Raised when the frozen competition-mapping protocol cannot be reproduced."""


def _error(message: str) -> FotMobPrimaryIdCompetitionMappingSemanticsProtocolError:
    return FotMobPrimaryIdCompetitionMappingSemanticsProtocolError(message)


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
        raise _error("competition-mapping protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("competition-mapping safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all competition-mapping safety values must remain exact False")
    return _safety()


@dataclasses.dataclass(frozen=True)
class InitialCompetitionMappingCandidate:
    model_league_code: str
    fotmob_primary_id: int
    expected_country_code: str
    competition_class: str
    qualification_state: str

    def __post_init__(self) -> None:
        if (
            type(self.model_league_code) is not str
            or not self.model_league_code
            or self.model_league_code != self.model_league_code.strip()
        ):
            raise _error("model_league_code must be exact non-empty text")
        if type(self.fotmob_primary_id) is not int or self.fotmob_primary_id <= 0:
            raise _error("fotmob_primary_id must be an exact positive integer")
        if (
            type(self.expected_country_code) is not str
            or len(self.expected_country_code) != 3
            or self.expected_country_code != self.expected_country_code.upper()
            or not self.expected_country_code.isalpha()
        ):
            raise _error("expected_country_code must be exact uppercase alpha-3 text")
        if self.competition_class not in SUPPORTED_COMPETITION_CLASSES:
            raise _error("competition_class is not a reviewed protocol class")
        if self.qualification_state != INITIAL_QUALIFICATION_STATE:
            raise _error("initial mapping candidate must remain unqualified")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _initial_mapping_candidates() -> tuple[InitialCompetitionMappingCandidate, ...]:
    return (
        InitialCompetitionMappingCandidate("B1", 40, "BEL", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("D1", 54, "GER", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("E0", 47, "ENG", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("F1", 53, "FRA", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("G1", 135, "GRE", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("I1", 55, "ITA", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("N1", 57, "NED", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("P1", 61, "POR", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("SC0", 64, "SCO", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("SP1", 87, "ESP", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
        InitialCompetitionMappingCandidate("T1", 71, "TUR", "DOMESTIC_LEAGUE", INITIAL_QUALIFICATION_STATE),
    )


def _protocol_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr105_receipt_blob_sha": PR105_RECEIPT_BLOB_SHA,
        "pr105_receipt_sha256": PR105_RECEIPT_SHA256,
        "pr105_receipt_size": PR105_RECEIPT_SIZE,
        "pr101_protocol_blob_sha": PR101_PROTOCOL_BLOB_SHA,
        "pr101_protocol_sha256": PR101_PROTOCOL_SHA256,
        "pr101_protocol_size": PR101_PROTOCOL_SIZE,
        "source": SOURCE,
        "source_field": SOURCE_FIELD,
        "initial_proof_set_role": INITIAL_PROOF_SET_ROLE,
        "supported_competition_classes": list(SUPPORTED_COMPETITION_CLASSES),
        "initial_mapping_candidates": [
            candidate.to_dict() for candidate in _initial_mapping_candidates()
        ],
        "identity_rules": list(IDENTITY_RULES),
        "competition_universe_rules": list(COMPETITION_UNIVERSE_RULES),
        "qualification_rules": list(QUALIFICATION_RULES),
        "mapping_qualification_performed": False,
        "competition_registry_mutation_performed": False,
        "historical_coverage_proven": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _verify_upstream() -> None:
    protocol = pr101.build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    exact_protocol = (
        pr101.canonical_fotmob_ordinary_ft_source_history_acquisition_protocol_bytes(
            protocol
        )
    )
    if (
        hashlib.sha256(exact_protocol).hexdigest() != PR101_PROTOCOL_SHA256
        or len(exact_protocol) != PR101_PROTOCOL_SIZE
    ):
        raise _error("PR101 acquisition protocol canonical identity changed")

    raw = PR105_RECEIPT_PATH.read_bytes()
    if len(raw) != PR105_RECEIPT_SIZE:
        raise _error("PR105 completeness receipt size changed")
    if hashlib.sha256(raw).hexdigest() != PR105_RECEIPT_SHA256:
        raise _error("PR105 completeness receipt SHA-256 changed")
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR105 completeness receipt is not valid canonical JSON") from exc
    if raw != _canonical(receipt):
        raise _error("PR105 completeness receipt is not canonical")

    if receipt.get("primary_status") != "BLOCKED_LEAGUE_MAPPING_UNPROVEN":
        raise _error("PR105 primary mapping blocker changed")
    if receipt.get("historical_coverage_proven") is not False:
        raise _error("PR105 historical coverage must remain unproven")
    if receipt.get("history_adapter_materialized") is not False:
        raise _error("PR105 must not materialize a history adapter")
    if receipt.get("next_required_boundary") != (
        "PRE_REGISTER_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_PROTOCOL"
    ):
        raise _error("PR105 next reviewed boundary changed")

    mapping = receipt.get("league_mapping_evidence")
    if not isinstance(mapping, dict) or mapping.get("mapping_proven") is not False:
        raise _error("PR105 mapping evidence must remain discovery-only")
    records = mapping.get("records")
    if not isinstance(records, list):
        raise _error("PR105 mapping evidence records missing")

    observed = {
        (
            item.get("model_league_code"),
            item.get("fotmob_primary_id"),
            item.get("expected_country_code"),
        )
        for item in records
        if isinstance(item, dict)
    }
    expected = {
        (
            candidate.model_league_code,
            candidate.fotmob_primary_id,
            candidate.expected_country_code,
        )
        for candidate in _initial_mapping_candidates()
    }
    if observed != expected or len(records) != len(expected):
        raise _error("PR105 eleven-candidate primaryId evidence changed")

    safety = receipt.get("safety")
    if (
        not isinstance(safety, dict)
        or not safety
        or any(type(value) is not bool or value is not False for value in safety.values())
    ):
        raise _error("PR105 downstream safety boundary changed")


@dataclasses.dataclass(frozen=True)
class FotMobPrimaryIdCompetitionMappingSemanticsProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    pr105_receipt_blob_sha: str
    pr105_receipt_sha256: str
    pr105_receipt_size: int
    pr101_protocol_blob_sha: str
    pr101_protocol_sha256: str
    pr101_protocol_size: int
    source: str
    source_field: str
    initial_proof_set_role: str
    supported_competition_classes: tuple[str, ...]
    initial_mapping_candidates: tuple[InitialCompetitionMappingCandidate, ...]
    identity_rules: tuple[str, ...]
    competition_universe_rules: tuple[str, ...]
    qualification_rules: tuple[str, ...]
    mapping_qualification_performed: bool
    competition_registry_mutation_performed: bool
    historical_coverage_proven: bool
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _protocol_payload():
            raise _error("competition-mapping protocol differs from frozen contract")
        if self.mapping_qualification_performed is not False:
            raise _error("mapping_qualification_performed must remain exact False")
        if self.competition_registry_mutation_performed is not False:
            raise _error("competition_registry_mutation_performed must remain exact False")
        if self.historical_coverage_proven is not False:
            raise _error("historical_coverage_proven must remain exact False")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_scope": self.protocol_scope,
            "protocol_state": self.protocol_state,
            "repository_main_sha": self.repository_main_sha,
            "pr105_receipt_blob_sha": self.pr105_receipt_blob_sha,
            "pr105_receipt_sha256": self.pr105_receipt_sha256,
            "pr105_receipt_size": self.pr105_receipt_size,
            "pr101_protocol_blob_sha": self.pr101_protocol_blob_sha,
            "pr101_protocol_sha256": self.pr101_protocol_sha256,
            "pr101_protocol_size": self.pr101_protocol_size,
            "source": self.source,
            "source_field": self.source_field,
            "initial_proof_set_role": self.initial_proof_set_role,
            "supported_competition_classes": list(self.supported_competition_classes),
            "initial_mapping_candidates": [
                candidate.to_dict() for candidate in self.initial_mapping_candidates
            ],
            "identity_rules": list(self.identity_rules),
            "competition_universe_rules": list(self.competition_universe_rules),
            "qualification_rules": list(self.qualification_rules),
            "mapping_qualification_performed": self.mapping_qualification_performed,
            "competition_registry_mutation_performed": self.competition_registry_mutation_performed,
            "historical_coverage_proven": self.historical_coverage_proven,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_fotmob_primary_id_competition_mapping_semantics_protocol(
) -> FotMobPrimaryIdCompetitionMappingSemanticsProtocol:
    _verify_upstream()
    payload = _protocol_payload()
    return FotMobPrimaryIdCompetitionMappingSemanticsProtocol(
        schema_version=payload["schema_version"],
        protocol_id=payload["protocol_id"],
        protocol_scope=payload["protocol_scope"],
        protocol_state=payload["protocol_state"],
        repository_main_sha=payload["repository_main_sha"],
        pr105_receipt_blob_sha=payload["pr105_receipt_blob_sha"],
        pr105_receipt_sha256=payload["pr105_receipt_sha256"],
        pr105_receipt_size=payload["pr105_receipt_size"],
        pr101_protocol_blob_sha=payload["pr101_protocol_blob_sha"],
        pr101_protocol_sha256=payload["pr101_protocol_sha256"],
        pr101_protocol_size=payload["pr101_protocol_size"],
        source=payload["source"],
        source_field=payload["source_field"],
        initial_proof_set_role=payload["initial_proof_set_role"],
        supported_competition_classes=tuple(payload["supported_competition_classes"]),
        initial_mapping_candidates=tuple(
            InitialCompetitionMappingCandidate(**candidate)
            for candidate in payload["initial_mapping_candidates"]
        ),
        identity_rules=tuple(payload["identity_rules"]),
        competition_universe_rules=tuple(payload["competition_universe_rules"]),
        qualification_rules=tuple(payload["qualification_rules"]),
        mapping_qualification_performed=payload["mapping_qualification_performed"],
        competition_registry_mutation_performed=payload[
            "competition_registry_mutation_performed"
        ],
        historical_coverage_proven=payload["historical_coverage_proven"],
        next_required_boundary=payload["next_required_boundary"],
        safety=types.MappingProxyType(dict(payload["safety"])),
    )


def canonical_fotmob_primary_id_competition_mapping_semantics_protocol_bytes(
    value: FotMobPrimaryIdCompetitionMappingSemanticsProtocol,
) -> bytes:
    if type(value) is not FotMobPrimaryIdCompetitionMappingSemanticsProtocol:
        raise _error("competition-mapping protocol must be the exact reviewed type")
    return _canonical(value.to_dict())
