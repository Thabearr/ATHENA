"""Pre-register a reviewed scoped FotMob full-time-score capability promotion.

PR #93 freezes a future decision boundary only.  The existing reviewed catalog
capability stays identity-only.  A future CONFIRMED score capability must live
under a derived adapter-scoped source key, must exclude penalty/unreviewed-reason
fixtures, and must be backed by a reusable prospective adapter rather than a
one-off evidence receipt.  No registry or downstream authority changes here.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_final_result_semantics_protocol as pr83
import domain.fotmob_data_matches_final_result_semantics_validation_with_reason_gate as pr92
import domain.fotmob_data_matches_status_reason_semantics_validation as pr91
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_REVIEWED_SCOPED_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_CAPABILITY_CHANGE"
REPOSITORY_MAIN_SHA = "5e63aaa8d2c036b2af95d0f3a48bd78adb5cc02e"

PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"
PROPOSED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"

PR92_VALIDATION_BLOB_SHA = "0acd3cc554b927f0038bbaba122a54974e1c0829"
PR92_RECEIPT_SHA256 = "b821d5211de1e2a058b85ac1ca2ac50bdd0d3b577b54aa40c86ed6773bcb0c86"
PR92_RECEIPT_SIZE = 3561
PR91_VALIDATION_BLOB_SHA = "a663a2c2879cb70dbd1f31f0f8bbe4ff8f1034d6"
PR83_PROTOCOL_BLOB_SHA = "25f8045524badcb90239df59ac9c47f36fcffe34"
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
REVIEWED_CATALOG_CAPABILITY_TEST_BLOB_SHA = "8cf8837686aa8ebed0788676416b70ff3deffd4a"

QUALIFIED_ORDINARY_FT_COUNT = 28
EXCLUDED_PENALTY_COUNT = 1
EXCLUDED_PENALTY_FIXTURE_ID = 5844873

PROMOTION_MODE = "REGISTER_NEW_DERIVED_ADAPTER_SCOPED_SOURCE_KEY_DO_NOT_MUTATE_PARENT"
REUSABLE_ADAPTER_MODULE_PATH = "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py"
CURRENT_REUSABLE_ADAPTER_STATE = "ABSENT_NOT_IMPLEMENTED_AT_PR93_PRE_REGISTRATION"
REUSABLE_ADAPTER_RULE = (
    "SOURCE_CAPABILITY_PROMOTION_REQUIRES_REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_ADAPTER_NOT_ONE_OFF_EVIDENCE_RECEIPT"
)
FUTURE_REQUIRED_ADAPTER_EVIDENCE = (
    "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py: reusable reviewed prospective ordinary-FT finished-score gate"
)

PARENT_REQUIRED_CAPABILITIES = types.MappingProxyType(
    {
        "full_time_score": "NOT_CAPTURED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
)
PROPOSED_CAPABILITIES = types.MappingProxyType(
    {
        "full_time_score": "CONFIRMED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
)
PROMOTION_SCOPE_RULE = (
    "CONFIRMED_FULL_TIME_SCORE_MEANS_ONLY_PR92_QUALIFIED_SOURCE_REPORTED_FINISHED_SCORE_FOR_EXACT_ORDINARY_FT_GATE"
)
PARENT_NON_MUTATION_RULE = (
    "PARENT_FOTMOB_DATA_MATCHES_REVIEWED_CATALOG_REMAINS_IDENTITY_ONLY_AND_UNCHANGED"
)
PENALTY_EXCLUSION_RULE = (
    "PENALTY_OR_OTHER_UNREVIEWED_REASON_FIXTURES_MUST_NOT_ENTER_DERIVED_CAPABILITY"
)
SEMANTIC_EXCLUSION_RULE = (
    "DO_NOT_INFER_REGULATION_TIME_EXTRA_TIME_PENALTY_SCORE_BOOKMAKER_SETTLEMENT_OR_GLOBAL_STATUS_REASON_SEMANTICS"
)
HISTORICAL_COVERAGE_RULE = "HISTORICAL_COVERAGE_REMAINS_UNKNOWN"

PROPOSED_EVIDENCE = (
    "domain/fotmob_data_matches_final_result_semantics_validation_with_reason_gate.py: exact PR92 28 ordinary-FT source-reported finished-score semantics",
    "domain/fotmob_data_matches_status_reason_semantics_validation.py: exact reviewed ordinary-FT reason gate and penalty exclusion",
    "domain/fotmob_data_matches_eliminated_team_id_value_domain_extension.py: reviewed structural chain over preserved PR85 captures",
    "domain/fotmob_data_matches_capture.py: provenance-bound reviewed capture manifests",
    FUTURE_REQUIRED_ADAPTER_EVIDENCE,
)
PROPOSED_NOTES = (
    "Derived reviewed adapter capability only. CONFIRMED full_time_score means "
    "source-reported finished score for fixtures that pass the exact PR92 "
    "ordinary-FT gate through a reusable reviewed prospective adapter. It does "
    "not apply to penalty or other unreviewed-reason fixtures and does not "
    "establish regulation-time, extra-time, penalty-score, bookmaker-settlement, "
    "historical-coverage, source-freshness, model-readiness, pricing, selection, "
    "or betting authority. Parent fotmob_data_matches_reviewed_catalog remains "
    "unchanged."
)

QUALIFICATION_REQUIREMENTS = (
    "VERIFY_EXACT_PR92_VALIDATION_BLOB_AND_CANONICAL_RECEIPT_IDENTITY",
    "VERIFY_EXACT_PR91_REASON_GATE_AND_PR83_SEMANTIC_SCOPE_ANCESTRY",
    "REQUIRE_PARENT_REVIEWED_CATALOG_CAPABILITY_TO_REMAIN_IDENTITY_ONLY_WITH_FULL_TIME_SCORE_NOT_CAPTURED",
    "REQUIRE_PROPOSED_DERIVED_SOURCE_KEY_TO_BE_ABSENT_BEFORE_REGISTRATION",
    "REQUIRE_REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_ADAPTER_BEFORE_REGISTRY_PROMOTION",
    "QUALIFY_ONLY_THE_EXACT_PR92_ORDINARY_FT_GATE_NOT_ALL_DATA_MATCHES_FIXTURES",
    "EXCLUDE_THE_PR91_PENALTY_FIXTURE_AND_ANY_OTHER_UNREVIEWED_REASON_FROM_THE_DERIVED_CAPABILITY",
    "REGISTER_A_NEW_DERIVED_ADAPTER_SCOPED_SOURCE_KEY_INSTEAD_OF_MUTATING_THE_PARENT_SOURCE_KEY",
    "KEEP_HISTORICAL_COVERAGE_UNKNOWN_AND_FRESHNESS_METADATA_NOT_CAPTURED",
    "DO_NOT_PROMOTE_REGULATION_TIME_EXTRA_TIME_PENALTY_SCORE_SETTLEMENT_OR_GLOBAL_REASON_SEMANTICS",
    "DO_NOT_AUTHORIZE_SOURCE_HISTORY_MODEL_PROBABILITY_PRICING_SELECTION_PRODUCTION_OR_BETTING",
)

STATUS_VOCABULARY = (
    "QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION",
    "BLOCKED_PR92_EVIDENCE_ANCESTRY_DRIFT",
    "BLOCKED_PARENT_SOURCE_CAPABILITY_DRIFT",
    "BLOCKED_PROPOSED_SOURCE_KEY_ALREADY_EXISTS",
    "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED",
    "BLOCKED_PROPOSED_CAPABILITY_SCOPE_OVERCLAIM",
    "BLOCKED_PENALTY_OR_UNREVIEWED_REASON_INCLUDED",
)
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT"
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_capability_promotion_execution_authorized",
        "source_capability_registry_update_authorized",
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

PROTOCOL_SHA256 = "8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009"
PROTOCOL_SIZE = 6458


class FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocolError(ValueError):
    """Raised when the frozen PR #93 protocol or its reviewed ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocolError:
    return FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocolError(message)


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
        raise _error("full-time-score capability promotion protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("PR93 safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR93 safety values must remain exact False")
    return _safety()


def _capability_dict(capability: Any) -> dict[str, str]:
    return {
        "full_time_score": capability.full_time_score.value,
        "half_time_score": capability.half_time_score.value,
        "event_timestamps": capability.event_timestamps.value,
        "reliable_fixture_identity": capability.reliable_fixture_identity.value,
        "historical_coverage": capability.historical_coverage.value,
        "freshness_metadata": capability.freshness_metadata.value,
    }


def _verify_upstream() -> None:
    if (pr92.RECEIPT_SHA256, pr92.RECEIPT_SIZE) != (
        PR92_RECEIPT_SHA256,
        PR92_RECEIPT_SIZE,
    ):
        raise _error("PR92 receipt identity constants changed")
    if pr92.NEXT_REQUIRED_BOUNDARY != (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_PROTOCOL"
    ):
        raise _error("PR92 next boundary changed")
    if (
        pr92.QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_COUNT,
        pr92.PR91_PENALTY_BLOCKED_COUNT,
        pr92.PENALTY_FIXTURE_ID,
    ) != (QUALIFIED_ORDINARY_FT_COUNT, EXCLUDED_PENALTY_COUNT, EXCLUDED_PENALTY_FIXTURE_ID):
        raise _error("PR92 qualified/excluded evidence counts changed")
    if pr92.QUALIFIED_STATUS != (
        pr83.FinalResultSemanticsStatus.QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS.value
    ):
        raise _error("PR92 qualified status escaped frozen PR83 semantics")
    if pr92.SEMANTIC_SCOPE_RULE != pr83.SEMANTIC_SCOPE_RULE:
        raise _error("PR92/PR83 semantic scope ancestry changed")

    if (
        pr91.ORDINARY_FT_REASON_QUALIFIED_COUNT,
        pr91.PENALTY_REASON_BLOCKED_COUNT,
        pr91.PENALTY_FIXTURE_ID,
    ) != (QUALIFIED_ORDINARY_FT_COUNT, EXCLUDED_PENALTY_COUNT, EXCLUDED_PENALTY_FIXTURE_ID):
        raise _error("PR91 reason-gate evidence counts changed")
    if pr91.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION_WITH_REVIEWED_REASON_GATE"
    ):
        raise _error("PR91 next boundary changed")

    parent = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    if parent is None:
        raise _error("parent reviewed FotMob catalog capability is missing")
    if _capability_dict(parent) != dict(PARENT_REQUIRED_CAPABILITIES):
        raise _error("parent reviewed catalog capability drifted from the frozen identity-only state")
    if parent.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("parent reliable fixture identity is no longer confirmed")
    if parent.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("parent full-time-score capability changed before PR93 execution")
    # Proposed-key absence is a PR93 pre-registration fact. A later reviewed
    # registration of the derived key must not invalidate this historical protocol.


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "parent_source_key": PARENT_SOURCE_KEY,
        "proposed_source_key": PROPOSED_SOURCE_KEY,
        "pr92_validation_blob_sha": PR92_VALIDATION_BLOB_SHA,
        "pr92_receipt_sha256": PR92_RECEIPT_SHA256,
        "pr92_receipt_size": PR92_RECEIPT_SIZE,
        "pr91_validation_blob_sha": PR91_VALIDATION_BLOB_SHA,
        "pr83_protocol_blob_sha": PR83_PROTOCOL_BLOB_SHA,
        "source_capabilities_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "reviewed_catalog_capability_test_blob_sha": REVIEWED_CATALOG_CAPABILITY_TEST_BLOB_SHA,
        "qualified_ordinary_ft_count": QUALIFIED_ORDINARY_FT_COUNT,
        "excluded_penalty_count": EXCLUDED_PENALTY_COUNT,
        "excluded_penalty_fixture_id": EXCLUDED_PENALTY_FIXTURE_ID,
        "promotion_mode": PROMOTION_MODE,
        "reusable_adapter_module_path": REUSABLE_ADAPTER_MODULE_PATH,
        "current_reusable_adapter_state": CURRENT_REUSABLE_ADAPTER_STATE,
        "reusable_adapter_rule": REUSABLE_ADAPTER_RULE,
        "future_required_adapter_evidence": FUTURE_REQUIRED_ADAPTER_EVIDENCE,
        "parent_required_capabilities": dict(PARENT_REQUIRED_CAPABILITIES),
        "proposed_capabilities": dict(PROPOSED_CAPABILITIES),
        "promotion_scope_rule": PROMOTION_SCOPE_RULE,
        "parent_non_mutation_rule": PARENT_NON_MUTATION_RULE,
        "penalty_exclusion_rule": PENALTY_EXCLUSION_RULE,
        "semantic_exclusion_rule": SEMANTIC_EXCLUSION_RULE,
        "historical_coverage_rule": HISTORICAL_COVERAGE_RULE,
        "proposed_evidence": list(PROPOSED_EVIDENCE),
        "proposed_notes": PROPOSED_NOTES,
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "status_vocabulary": list(STATUS_VOCABULARY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    parent_source_key: str
    proposed_source_key: str
    pr92_validation_blob_sha: str
    pr92_receipt_sha256: str
    pr92_receipt_size: int
    pr91_validation_blob_sha: str
    pr83_protocol_blob_sha: str
    source_capabilities_blob_sha: str
    reviewed_catalog_capability_test_blob_sha: str
    qualified_ordinary_ft_count: int
    excluded_penalty_count: int
    excluded_penalty_fixture_id: int
    promotion_mode: str
    reusable_adapter_module_path: str
    current_reusable_adapter_state: str
    reusable_adapter_rule: str
    future_required_adapter_evidence: str
    parent_required_capabilities: Mapping[str, str]
    proposed_capabilities: Mapping[str, str]
    promotion_scope_rule: str
    parent_non_mutation_rule: str
    penalty_exclusion_rule: str
    semantic_exclusion_rule: str
    historical_coverage_rule: str
    proposed_evidence: tuple[str, ...]
    proposed_notes: str
    qualification_requirements: tuple[str, ...]
    status_vocabulary: tuple[str, ...]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise _error("schema_version must be exact integer 1")
        if type(self.pr92_receipt_size) is not int or self.pr92_receipt_size != PR92_RECEIPT_SIZE:
            raise _error("PR92 receipt size changed")
        for label, value in (
            ("qualified_ordinary_ft_count", self.qualified_ordinary_ft_count),
            ("excluded_penalty_count", self.excluded_penalty_count),
            ("excluded_penalty_fixture_id", self.excluded_penalty_fixture_id),
        ):
            if type(value) is not int or value < 1:
                raise _error(f"{label} must be an exact positive integer")
        if self.parent_source_key == self.proposed_source_key:
            raise _error("derived capability key must not equal the parent key")
        if self.future_required_adapter_evidence not in self.proposed_evidence:
            raise _error("future reusable adapter evidence must be part of proposed registry evidence")
        if self.to_dict() != _payload():
            raise _error("full-time-score capability promotion protocol differs from frozen PR93 payload")
        object.__setattr__(
            self,
            "parent_required_capabilities",
            types.MappingProxyType(dict(self.parent_required_capabilities)),
        )
        object.__setattr__(
            self,
            "proposed_capabilities",
            types.MappingProxyType(dict(self.proposed_capabilities)),
        )
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_scope": self.protocol_scope,
            "protocol_state": self.protocol_state,
            "repository_main_sha": self.repository_main_sha,
            "parent_source_key": self.parent_source_key,
            "proposed_source_key": self.proposed_source_key,
            "pr92_validation_blob_sha": self.pr92_validation_blob_sha,
            "pr92_receipt_sha256": self.pr92_receipt_sha256,
            "pr92_receipt_size": self.pr92_receipt_size,
            "pr91_validation_blob_sha": self.pr91_validation_blob_sha,
            "pr83_protocol_blob_sha": self.pr83_protocol_blob_sha,
            "source_capabilities_blob_sha": self.source_capabilities_blob_sha,
            "reviewed_catalog_capability_test_blob_sha": self.reviewed_catalog_capability_test_blob_sha,
            "qualified_ordinary_ft_count": self.qualified_ordinary_ft_count,
            "excluded_penalty_count": self.excluded_penalty_count,
            "excluded_penalty_fixture_id": self.excluded_penalty_fixture_id,
            "promotion_mode": self.promotion_mode,
            "reusable_adapter_module_path": self.reusable_adapter_module_path,
            "current_reusable_adapter_state": self.current_reusable_adapter_state,
            "reusable_adapter_rule": self.reusable_adapter_rule,
            "future_required_adapter_evidence": self.future_required_adapter_evidence,
            "parent_required_capabilities": dict(self.parent_required_capabilities),
            "proposed_capabilities": dict(self.proposed_capabilities),
            "promotion_scope_rule": self.promotion_scope_rule,
            "parent_non_mutation_rule": self.parent_non_mutation_rule,
            "penalty_exclusion_rule": self.penalty_exclusion_rule,
            "semantic_exclusion_rule": self.semantic_exclusion_rule,
            "historical_coverage_rule": self.historical_coverage_rule,
            "proposed_evidence": list(self.proposed_evidence),
            "proposed_notes": self.proposed_notes,
            "qualification_requirements": list(self.qualification_requirements),
            "status_vocabulary": list(self.status_vocabulary),
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_fotmob_data_matches_full_time_score_capability_promotion_protocol(
) -> FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol:
    _verify_upstream()
    payload = _payload()
    value = FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol(
        **{
            **payload,
            "proposed_evidence": tuple(payload["proposed_evidence"]),
            "qualification_requirements": tuple(payload["qualification_requirements"]),
            "status_vocabulary": tuple(payload["status_vocabulary"]),
            "safety": _safety(),
        }
    )
    exact = canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(value)
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR93 capability-promotion canonical identity changed")
    return value


def canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(
    value: FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol,
) -> bytes:
    if not isinstance(value, FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol):
        raise _error("capability-promotion protocol value has wrong type")
    return _canonical(value.to_dict())


def revalidate_fotmob_data_matches_full_time_score_capability_promotion_protocol(
    value: FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol,
) -> FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol:
    if not isinstance(value, FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol):
        raise _error("capability-promotion protocol value has wrong type")
    expected = build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    if canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(value) != (
        canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(expected)
    ):
        raise _error("capability-promotion protocol changed")
    return expected


__all__ = [
    "CURRENT_REUSABLE_ADAPTER_STATE",
    "EXCLUDED_PENALTY_COUNT",
    "EXCLUDED_PENALTY_FIXTURE_ID",
    "FUTURE_REQUIRED_ADAPTER_EVIDENCE",
    "HISTORICAL_COVERAGE_RULE",
    "NEXT_REQUIRED_BOUNDARY",
    "PARENT_NON_MUTATION_RULE",
    "PARENT_REQUIRED_CAPABILITIES",
    "PARENT_SOURCE_KEY",
    "PENALTY_EXCLUSION_RULE",
    "PROMOTION_MODE",
    "PROMOTION_SCOPE_RULE",
    "PROPOSED_CAPABILITIES",
    "PROPOSED_EVIDENCE",
    "PROPOSED_NOTES",
    "PROPOSED_SOURCE_KEY",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "QUALIFICATION_REQUIREMENTS",
    "QUALIFIED_ORDINARY_FT_COUNT",
    "REPOSITORY_MAIN_SHA",
    "REUSABLE_ADAPTER_MODULE_PATH",
    "REUSABLE_ADAPTER_RULE",
    "SEMANTIC_EXCLUSION_RULE",
    "STATUS_VOCABULARY",
    "FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocol",
    "FotMobDataMatchesFullTimeScoreCapabilityPromotionProtocolError",
    "build_fotmob_data_matches_full_time_score_capability_promotion_protocol",
    "canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes",
    "revalidate_fotmob_data_matches_full_time_score_capability_promotion_protocol",
]
