"""Execute the frozen PR #93 full-time-score capability promotion assessment.

This boundary is evidence-only and deliberately fails closed.  PR #93 requires a
reusable reviewed prospective ordinary-FT finished-score adapter before ATHENA may
qualify even a derived adapter-scoped ``full_time_score`` capability.  The exact
assessed repository tree contains no such adapter, so no source capability is
qualified or registered and no downstream authority changes.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_full_time_score_capability_promotion_protocol as pr93
from domain.source_capabilities import SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-full-time-score-capability-promotion-assessment-v1"
ASSESSMENT_SCOPE = "EXECUTE_PR93_SCOPED_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT_ONLY"
ASSESSMENT_STATE = "EXECUTED_FAIL_CLOSED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED"
REPOSITORY_MAIN_SHA = "30269b776b6ff66668b9149863ee6d4bdf8e8025"
ASSESSED_REPOSITORY_TREE_SHA = "20347b1521283ea0988b263978027143bb31e255"

PR93_PROTOCOL_BLOB_SHA = "c9b5d47674283e2a8f2d54a68966b97fbd418047"
PR93_PROTOCOL_SHA256 = "8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009"
PR93_PROTOCOL_SIZE = 6458

PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"
PROPOSED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
REUSABLE_ADAPTER_MODULE_PATH = "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py"
REUSABLE_ADAPTER_STATE_AT_ASSESSMENT = "ABSENT_NOT_IMPLEMENTED_AT_PR93_PRE_REGISTRATION"
ADAPTER_PATH_PRESENT_IN_EXACT_ASSESSED_TREE = False
ADAPTER_ABSENCE_EVIDENCE = (
    "EXACT_ASSESSED_MAIN_TREE_ENUMERATION_PLUS_PR93_FROZEN_PRE_REGISTRATION_ABSENCE_STATE"
)

QUALIFIED_ORDINARY_FT_COUNT = 28
EXCLUDED_PENALTY_COUNT = 1
EXCLUDED_PENALTY_FIXTURE_ID = 5844873
PRIMARY_STATUS = "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED"
SMALLEST_MISSING_REVIEWED_BOUNDARY = (
    "BUILD_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER"
)

_PARENT_CAPABILITIES_AT_ASSESSMENT = types.MappingProxyType(
    {
        "full_time_score": "NOT_CAPTURED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
)
_PROPOSED_CAPABILITIES_IF_FUTURE_REGISTRATION_QUALIFIES = types.MappingProxyType(
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
        "source_capability_promotion_assessment_qualified",
        "reusable_score_adapter_implemented",
        "reusable_score_adapter_qualified",
        "source_capability_registration_qualified",
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

ASSESSMENT_SHA256 = "adfe1a6e0103a65c30ed19026940bfb5474c63dc44328b7c632ea8dbe15d2eb5"
ASSESSMENT_SIZE = 4568


class FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError(ValueError):
    """Raised when the frozen PR #94 assessment or its ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError:
    return FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError(message)


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
        raise _error("full-time-score capability promotion assessment serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("PR94 safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR94 safety values must remain exact False")
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


@dataclasses.dataclass(frozen=True)
class CapabilityPromotionGateResult:
    gate_id: str
    outcome: str
    status: str | None
    reason: str

    def __post_init__(self) -> None:
        if type(self.gate_id) is not str or not self.gate_id:
            raise _error("gate_id must be exact non-empty text")
        if self.outcome not in {"PASS", "BLOCKED", "NOT_REACHED"}:
            raise _error("gate outcome is outside the frozen PR94 vocabulary")
        if self.outcome == "BLOCKED":
            if type(self.status) is not str or self.status not in pr93.STATUS_VOCABULARY:
                raise _error("blocked gate must carry an exact PR93 status")
        elif self.status is not None:
            raise _error("PASS/NOT_REACHED gates must not claim a blocker status")
        if type(self.reason) is not str or not self.reason:
            raise _error("gate reason must be exact non-empty text")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "outcome": self.outcome,
            "status": self.status,
            "reason": self.reason,
        }


def _gate_results() -> tuple[CapabilityPromotionGateResult, ...]:
    return (
        CapabilityPromotionGateResult(
            gate_id="PR93_PROTOCOL_ANCESTRY",
            outcome="PASS",
            status=None,
            reason="EXACT_PR93_PROTOCOL_CANONICAL_IDENTITY_REVALIDATED",
        ),
        CapabilityPromotionGateResult(
            gate_id="PARENT_SOURCE_CAPABILITY",
            outcome="PASS",
            status=None,
            reason="PARENT_REVIEWED_CATALOG_REMAINS_IDENTITY_ONLY_WITH_FULL_TIME_SCORE_NOT_CAPTURED",
        ),
        CapabilityPromotionGateResult(
            gate_id="PROPOSED_SOURCE_KEY_ABSENCE",
            outcome="PASS",
            status=None,
            reason="DERIVED_SOURCE_KEY_IS_NOT_PRESENT_IN_CURRENT_SOURCE_CAPABILITY_REGISTRY",
        ),
        CapabilityPromotionGateResult(
            gate_id="PR92_ORDINARY_FT_EVIDENCE_SCOPE",
            outcome="PASS",
            status=None,
            reason="EXACT_PR92_EVIDENCE_REMAINS_28_ORDINARY_FT_QUALIFIED_AND_ONE_PENALTY_EXCLUDED",
        ),
        CapabilityPromotionGateResult(
            gate_id="REUSABLE_PROSPECTIVE_SCORE_ADAPTER",
            outcome="BLOCKED",
            status=PRIMARY_STATUS,
            reason="PR93_FROZE_REUSABLE_ADAPTER_AS_REQUIRED_AND_ABSENT_AT_PRE_REGISTRATION_NO_PROSPECTIVE_ADAPTER_AUTHORITY_NOW_EXISTS",
        ),
        CapabilityPromotionGateResult(
            gate_id="DERIVED_CAPABILITY_REGISTRATION",
            outcome="NOT_REACHED",
            status=None,
            reason="REGISTRATION_CANNOT_BE_QUALIFIED_OR_EXECUTED_BEFORE_REUSABLE_ADAPTER_BOUNDARY",
        ),
    )


def _verify_upstream() -> None:
    if (pr93.PROTOCOL_SHA256, pr93.PROTOCOL_SIZE) != (
        PR93_PROTOCOL_SHA256,
        PR93_PROTOCOL_SIZE,
    ):
        raise _error("PR93 canonical protocol constants changed")
    protocol = pr93.build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    exact = pr93.canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(
        protocol
    )
    if (
        hashlib.sha256(exact).hexdigest() != PR93_PROTOCOL_SHA256
        or len(exact) != PR93_PROTOCOL_SIZE
    ):
        raise _error("PR93 protocol canonical identity changed")
    if protocol.next_required_boundary != (
        "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT"
    ):
        raise _error("PR93 next boundary changed")
    if protocol.reusable_adapter_module_path != REUSABLE_ADAPTER_MODULE_PATH:
        raise _error("PR93 reusable adapter path changed")
    if protocol.current_reusable_adapter_state != REUSABLE_ADAPTER_STATE_AT_ASSESSMENT:
        raise _error("PR93 reusable adapter state changed")
    if (
        protocol.qualified_ordinary_ft_count,
        protocol.excluded_penalty_count,
        protocol.excluded_penalty_fixture_id,
    ) != (
        QUALIFIED_ORDINARY_FT_COUNT,
        EXCLUDED_PENALTY_COUNT,
        EXCLUDED_PENALTY_FIXTURE_ID,
    ):
        raise _error("PR93 reviewed evidence counts changed")
    if dict(protocol.parent_required_capabilities) != dict(_PARENT_CAPABILITIES_AT_ASSESSMENT):
        raise _error("PR93 parent capability contract changed")
    if dict(protocol.proposed_capabilities) != dict(
        _PROPOSED_CAPABILITIES_IF_FUTURE_REGISTRATION_QUALIFIES
    ):
        raise _error("PR93 proposed capability contract changed")
    if PRIMARY_STATUS not in protocol.status_vocabulary:
        raise _error("PR93 missing reusable-adapter blocker status")

    parent = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    if parent is None:
        raise _error("parent reviewed catalog capability is missing")
    if _capability_dict(parent) != dict(_PARENT_CAPABILITIES_AT_ASSESSMENT):
        raise _error("parent reviewed catalog capability drifted")
    if PROPOSED_SOURCE_KEY in SOURCE_CAPABILITY_REGISTRY:
        raise _error("proposed derived source key already exists")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "assessment_scope": ASSESSMENT_SCOPE,
        "assessment_state": ASSESSMENT_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr93_protocol_blob_sha": PR93_PROTOCOL_BLOB_SHA,
        "pr93_protocol_sha256": PR93_PROTOCOL_SHA256,
        "pr93_protocol_size": PR93_PROTOCOL_SIZE,
        "parent_source_key": PARENT_SOURCE_KEY,
        "proposed_source_key": PROPOSED_SOURCE_KEY,
        "reusable_adapter_module_path": REUSABLE_ADAPTER_MODULE_PATH,
        "reusable_adapter_state_at_assessment": REUSABLE_ADAPTER_STATE_AT_ASSESSMENT,
        "qualified_ordinary_ft_count": QUALIFIED_ORDINARY_FT_COUNT,
        "excluded_penalty_count": EXCLUDED_PENALTY_COUNT,
        "excluded_penalty_fixture_id": EXCLUDED_PENALTY_FIXTURE_ID,
        "parent_capabilities_at_assessment": dict(_PARENT_CAPABILITIES_AT_ASSESSMENT),
        "proposed_capabilities_if_future_registration_qualifies": dict(
            _PROPOSED_CAPABILITIES_IF_FUTURE_REGISTRATION_QUALIFIES
        ),
        "assessment_executed": True,
        "reusable_adapter_implemented": False,
        "proposed_source_key_present": False,
        "parent_source_capability_matches_protocol": True,
        "pr92_evidence_scope_matches_protocol": True,
        "registration_qualified": False,
        "registry_update_performed": False,
        "primary_status": PRIMARY_STATUS,
        "gate_results": [item.to_dict() for item in _gate_results()],
        "smallest_missing_reviewed_boundary": SMALLEST_MISSING_REVIEWED_BOUNDARY,
        "safety": dict(_safety()),
        "assessed_repository_tree_sha": ASSESSED_REPOSITORY_TREE_SHA,
        "adapter_path_present_in_exact_assessed_tree": ADAPTER_PATH_PRESENT_IN_EXACT_ASSESSED_TREE,
        "adapter_absence_evidence": ADAPTER_ABSENCE_EVIDENCE,
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment:
    schema_version: int
    dataset_name: str
    assessment_scope: str
    assessment_state: str
    repository_main_sha: str
    pr93_protocol_blob_sha: str
    pr93_protocol_sha256: str
    pr93_protocol_size: int
    parent_source_key: str
    proposed_source_key: str
    reusable_adapter_module_path: str
    reusable_adapter_state_at_assessment: str
    qualified_ordinary_ft_count: int
    excluded_penalty_count: int
    excluded_penalty_fixture_id: int
    parent_capabilities_at_assessment: Mapping[str, str]
    proposed_capabilities_if_future_registration_qualifies: Mapping[str, str]
    assessment_executed: bool
    reusable_adapter_implemented: bool
    proposed_source_key_present: bool
    parent_source_capability_matches_protocol: bool
    pr92_evidence_scope_matches_protocol: bool
    registration_qualified: bool
    registry_update_performed: bool
    primary_status: str
    gate_results: tuple[CapabilityPromotionGateResult, ...]
    smallest_missing_reviewed_boundary: str
    safety: Mapping[str, bool]
    assessed_repository_tree_sha: str
    adapter_path_present_in_exact_assessed_tree: bool
    adapter_absence_evidence: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise _error("schema_version must remain exact integer 1")
        for label, value in (
            ("assessment_executed", self.assessment_executed),
            ("reusable_adapter_implemented", self.reusable_adapter_implemented),
            ("proposed_source_key_present", self.proposed_source_key_present),
            ("parent_source_capability_matches_protocol", self.parent_source_capability_matches_protocol),
            ("pr92_evidence_scope_matches_protocol", self.pr92_evidence_scope_matches_protocol),
            ("registration_qualified", self.registration_qualified),
            ("registry_update_performed", self.registry_update_performed),
            ("adapter_path_present_in_exact_assessed_tree", self.adapter_path_present_in_exact_assessed_tree),
        ):
            if type(value) is not bool:
                raise _error(f"{label} must be an exact bool")
        if self.assessment_executed is not True:
            raise _error("assessment_executed must remain exact True")
        if self.reusable_adapter_implemented is not False:
            raise _error("reusable_adapter_implemented must remain exact False")
        if self.proposed_source_key_present is not False:
            raise _error("proposed_source_key_present must remain exact False")
        if self.parent_source_capability_matches_protocol is not True:
            raise _error("parent source capability must match the frozen PR93 contract")
        if self.pr92_evidence_scope_matches_protocol is not True:
            raise _error("PR92 evidence scope must match the frozen PR93 contract")
        if self.registration_qualified is not False or self.registry_update_performed is not False:
            raise _error("PR94 must not qualify or execute registry registration")
        if self.adapter_path_present_in_exact_assessed_tree is not False:
            raise _error("exact assessed tree must record the reusable adapter as absent")
        if self.primary_status != PRIMARY_STATUS or self.primary_status not in pr93.STATUS_VOCABULARY:
            raise _error("primary status escaped frozen PR93 vocabulary")
        if type(self.gate_results) is not tuple or any(
            type(item) is not CapabilityPromotionGateResult for item in self.gate_results
        ):
            raise _error("gate_results must be an exact immutable PR94 gate tuple")
        if self.to_dict() != _payload():
            raise _error("full-time-score capability promotion assessment differs from frozen PR94 result")
        object.__setattr__(
            self,
            "parent_capabilities_at_assessment",
            types.MappingProxyType(dict(_PARENT_CAPABILITIES_AT_ASSESSMENT)),
        )
        object.__setattr__(
            self,
            "proposed_capabilities_if_future_registration_qualifies",
            types.MappingProxyType(dict(_PROPOSED_CAPABILITIES_IF_FUTURE_REGISTRATION_QUALIFIES)),
        )
        object.__setattr__(
            self,
            "gate_results",
            tuple(dataclasses.replace(item) for item in self.gate_results),
        )
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "assessment_scope": self.assessment_scope,
            "assessment_state": self.assessment_state,
            "repository_main_sha": self.repository_main_sha,
            "pr93_protocol_blob_sha": self.pr93_protocol_blob_sha,
            "pr93_protocol_sha256": self.pr93_protocol_sha256,
            "pr93_protocol_size": self.pr93_protocol_size,
            "parent_source_key": self.parent_source_key,
            "proposed_source_key": self.proposed_source_key,
            "reusable_adapter_module_path": self.reusable_adapter_module_path,
            "reusable_adapter_state_at_assessment": self.reusable_adapter_state_at_assessment,
            "qualified_ordinary_ft_count": self.qualified_ordinary_ft_count,
            "excluded_penalty_count": self.excluded_penalty_count,
            "excluded_penalty_fixture_id": self.excluded_penalty_fixture_id,
            "parent_capabilities_at_assessment": dict(self.parent_capabilities_at_assessment),
            "proposed_capabilities_if_future_registration_qualifies": dict(
                self.proposed_capabilities_if_future_registration_qualifies
            ),
            "assessment_executed": self.assessment_executed,
            "reusable_adapter_implemented": self.reusable_adapter_implemented,
            "proposed_source_key_present": self.proposed_source_key_present,
            "parent_source_capability_matches_protocol": self.parent_source_capability_matches_protocol,
            "pr92_evidence_scope_matches_protocol": self.pr92_evidence_scope_matches_protocol,
            "registration_qualified": self.registration_qualified,
            "registry_update_performed": self.registry_update_performed,
            "primary_status": self.primary_status,
            "gate_results": [item.to_dict() for item in self.gate_results],
            "smallest_missing_reviewed_boundary": self.smallest_missing_reviewed_boundary,
            "safety": dict(self.safety),
            "assessed_repository_tree_sha": self.assessed_repository_tree_sha,
            "adapter_path_present_in_exact_assessed_tree": self.adapter_path_present_in_exact_assessed_tree,
            "adapter_absence_evidence": self.adapter_absence_evidence,
        }


def build_fotmob_data_matches_full_time_score_capability_promotion_assessment(
) -> FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment:
    _verify_upstream()
    payload = _payload()
    value = FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment(
        **{
            **payload,
            "parent_capabilities_at_assessment": types.MappingProxyType(
                dict(payload["parent_capabilities_at_assessment"])
            ),
            "proposed_capabilities_if_future_registration_qualifies": types.MappingProxyType(
                dict(payload["proposed_capabilities_if_future_registration_qualifies"])
            ),
            "gate_results": _gate_results(),
            "safety": _safety(),
        }
    )
    exact = canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(
        value
    )
    if hashlib.sha256(exact).hexdigest() != ASSESSMENT_SHA256 or len(exact) != ASSESSMENT_SIZE:
        raise _error("PR94 capability-promotion assessment canonical identity changed")
    return value


def canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(
    value: FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment,
) -> bytes:
    if not isinstance(value, FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment):
        raise _error("capability-promotion assessment value has wrong type")
    return _canonical(value.to_dict())


def revalidate_fotmob_data_matches_full_time_score_capability_promotion_assessment(
    value: FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment,
) -> FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment:
    if not isinstance(value, FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment):
        raise _error("capability-promotion assessment value has wrong type")
    expected = build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    if canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(value) != (
        canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(expected)
    ):
        raise _error("capability-promotion assessment changed")
    return expected


__all__ = [
    "ADAPTER_ABSENCE_EVIDENCE",
    "ADAPTER_PATH_PRESENT_IN_EXACT_ASSESSED_TREE",
    "ASSESSED_REPOSITORY_TREE_SHA",
    "ASSESSMENT_SCOPE",
    "ASSESSMENT_SHA256",
    "ASSESSMENT_SIZE",
    "ASSESSMENT_STATE",
    "DATASET_NAME",
    "EXCLUDED_PENALTY_COUNT",
    "EXCLUDED_PENALTY_FIXTURE_ID",
    "PARENT_SOURCE_KEY",
    "PRIMARY_STATUS",
    "PROPOSED_SOURCE_KEY",
    "QUALIFIED_ORDINARY_FT_COUNT",
    "REPOSITORY_MAIN_SHA",
    "REUSABLE_ADAPTER_MODULE_PATH",
    "REUSABLE_ADAPTER_STATE_AT_ASSESSMENT",
    "SMALLEST_MISSING_REVIEWED_BOUNDARY",
    "CapabilityPromotionGateResult",
    "FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessment",
    "FotMobDataMatchesFullTimeScoreCapabilityPromotionAssessmentError",
    "build_fotmob_data_matches_full_time_score_capability_promotion_assessment",
    "canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes",
    "revalidate_fotmob_data_matches_full_time_score_capability_promotion_assessment",
]
