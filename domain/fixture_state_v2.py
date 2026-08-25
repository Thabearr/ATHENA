"""Canonical, immutable pre-match Fixture State v2 contract.

This additive boundary consumes one already-built FixtureIntelligenceSnapshot.
It performs no acquisition, feature engineering, inference, pricing, or model
selection.  The existing fixture_model_features v1 contract remains unchanged.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping
from typing import Any, Tuple

from domain.fixture_intelligence import (
    DATASET_NAME as FIXTURE_INTELLIGENCE_DATASET_NAME,
    SCHEMA_VERSION as FIXTURE_INTELLIGENCE_SCHEMA_VERSION,
    FixtureIntelligenceFact,
    FixtureIntelligenceSnapshot,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    canonical_snapshot_bytes,
    sha256_bytes,
)


DATASET_NAME = "athena-fixture-state-v2"
SCHEMA_VERSION = 2
SOURCE_COVERAGE_SCHEMA_VERSION = 1
FIXTURE_STATE_FIELD_REGISTRY_VERSION = 1


class FixtureStateV2Error(ValueError):
    """Raised when Fixture State v2 input fails closed."""


class FixtureStateFieldFamily(str, enum.Enum):
    LEGACY_STRENGTH = "LEGACY_STRENGTH"
    TEAM_STRENGTH_PERFORMANCE = "TEAM_STRENGTH_PERFORMANCE"
    TACTICAL_REGIME = "TACTICAL_REGIME"
    AVAILABILITY_LINEUP = "AVAILABILITY_LINEUP"
    CONTEXT = "CONTEXT"


class FixtureStateValueType(str, enum.Enum):
    FINITE_NUMBER = "FINITE_NUMBER"
    CATEGORICAL_STRING = "CATEGORICAL_STRING"
    BOOLEAN = "BOOLEAN"
    STRUCTURED_RECORD = "STRUCTURED_RECORD"


class FixtureStateDerivation(str, enum.Enum):
    RAW_EVIDENCE_DERIVED = "RAW_EVIDENCE_DERIVED"
    FUTURE_DERIVED_SLOT = "FUTURE_DERIVED_SLOT"
    FUTURE_SOURCE_REQUIRED_SLOT = "FUTURE_SOURCE_REQUIRED_SLOT"
    PENDING_REVIEWED_ADAPTER_SLOT = "PENDING_REVIEWED_ADAPTER_SLOT"


class FixtureStateAvailabilityExpectation(str, enum.Enum):
    CURRENTLY_MAPPED_WHEN_QUALIFYING_EVIDENCE_EXISTS = (
        "CURRENTLY_MAPPED_WHEN_QUALIFYING_EVIDENCE_EXISTS"
    )
    SCHEMA_SLOT_ONLY_PENDING_FUTURE_REVIEWED_DERIVATION = (
        "SCHEMA_SLOT_ONLY_PENDING_FUTURE_REVIEWED_DERIVATION"
    )
    SCHEMA_SLOT_ONLY_PENDING_FUTURE_REVIEWED_SOURCE = (
        "SCHEMA_SLOT_ONLY_PENDING_FUTURE_REVIEWED_SOURCE"
    )
    SCHEMA_SLOT_ONLY_PENDING_REVIEWED_ADAPTER = (
        "SCHEMA_SLOT_ONLY_PENDING_REVIEWED_ADAPTER"
    )


class FixtureStateSourceClass(str, enum.Enum):
    FOTMOB_PRIMARY = "FOTMOB_PRIMARY"
    ATHENA_DERIVED = "ATHENA_DERIVED"
    OFFICIAL_CORROBORATION = "OFFICIAL_CORROBORATION"
    SPECIALIST_EXTERNAL = "SPECIALIST_EXTERNAL"
    VERIFIED_EXTERNAL = "VERIFIED_EXTERNAL"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"
    FUTURE_SOURCE_REQUIRED = "FUTURE_SOURCE_REQUIRED"


class FixtureStateObservationMode(str, enum.Enum):
    DIRECTLY_OBSERVED = "DIRECTLY_OBSERVED"
    ATHENA_DERIVED = "ATHENA_DERIVED"


class FixtureStateImplementationState(str, enum.Enum):
    CURRENTLY_MAPPABLE = "CURRENTLY_MAPPABLE"
    PARTIALLY_PROVEN_PENDING_V2_ADAPTER = (
        "PARTIALLY_PROVEN_PENDING_V2_ADAPTER"
    )
    FUTURE_DERIVED = "FUTURE_DERIVED"
    FUTURE_SOURCE_REQUIRED = "FUTURE_SOURCE_REQUIRED"


class FixtureStateOfficialCorroboration(str, enum.Enum):
    NOT_REQUIRED_BY_CURRENT_CONTRACT = "NOT_REQUIRED_BY_CURRENT_CONTRACT"
    MAY_BE_REQUIRED_BY_FUTURE_POLICY = "MAY_BE_REQUIRED_BY_FUTURE_POLICY"


class FixtureStateFieldId(str, enum.Enum):
    HOME_FORM = "home_form"
    AWAY_FORM = "away_form"
    HOME_ELO = "home_elo"
    AWAY_ELO = "away_elo"
    FATIGUE = "fatigue"
    LIVE_DATA_FRESHNESS = "live_data_freshness"

    HOME_ATTACK_STRENGTH = "home_attack_strength"
    AWAY_ATTACK_STRENGTH = "away_attack_strength"
    HOME_DEFENSIVE_STRENGTH = "home_defensive_strength"
    AWAY_DEFENSIVE_STRENGTH = "away_defensive_strength"
    HOME_OPPONENT_ADJUSTED_ATTACK_STRENGTH = (
        "home_opponent_adjusted_attack_strength"
    )
    AWAY_OPPONENT_ADJUSTED_ATTACK_STRENGTH = (
        "away_opponent_adjusted_attack_strength"
    )
    HOME_OPPONENT_ADJUSTED_DEFENSIVE_STRENGTH = (
        "home_opponent_adjusted_defensive_strength"
    )
    AWAY_OPPONENT_ADJUSTED_DEFENSIVE_STRENGTH = (
        "away_opponent_adjusted_defensive_strength"
    )
    HOME_VENUE_ATTACK_STRENGTH = "home_venue_attack_strength"
    HOME_VENUE_DEFENSIVE_STRENGTH = "home_venue_defensive_strength"
    AWAY_VENUE_ATTACK_STRENGTH = "away_venue_attack_strength"
    AWAY_VENUE_DEFENSIVE_STRENGTH = "away_venue_defensive_strength"

    HOME_TACTICAL_IDENTITY = "home_tactical_identity"
    AWAY_TACTICAL_IDENTITY = "away_tactical_identity"
    HOME_MANAGER_REGIME_IDENTITY = "home_manager_regime_identity"
    AWAY_MANAGER_REGIME_IDENTITY = "away_manager_regime_identity"

    HOME_AVAILABILITY_STATE = "home_availability_state"
    AWAY_AVAILABILITY_STATE = "away_availability_state"
    HOME_LINEUP_STATE = "home_lineup_state"
    AWAY_LINEUP_STATE = "away_lineup_state"
    HOME_LINEUP_CONFIRMED = "home_lineup_confirmed"
    AWAY_LINEUP_CONFIRMED = "away_lineup_confirmed"
    HOME_LINEUP_FRESHNESS = "home_lineup_freshness"
    AWAY_LINEUP_FRESHNESS = "away_lineup_freshness"

    VENUE = "venue"
    HOME_TRAVEL_CONTEXT = "home_travel_context"
    AWAY_TRAVEL_CONTEXT = "away_travel_context"
    WEATHER = "weather"
    REFEREE = "referee"
    COMPETITION_STAGE = "competition_stage"
    MOTIVATION_MATCH_CONTEXT = "motivation_match_context"


class FixtureStateStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


class FixtureStateBlocker(str, enum.Enum):
    CONFLICTED_EVIDENCE = "CONFLICTED_EVIDENCE"
    STALE_EVIDENCE_PRESENT = "STALE_EVIDENCE_PRESENT"
    UNVERIFIED_EVIDENCE_PRESENT = "UNVERIFIED_EVIDENCE_PRESENT"
    NO_SUPPORTED_EVIDENCE = "NO_SUPPORTED_EVIDENCE"
    INVALID_SUPPORTED_VALUE = "INVALID_SUPPORTED_VALUE"
    UNSUPPORTED_OR_AMBIGUOUS_SEMANTICS = (
        "UNSUPPORTED_OR_AMBIGUOUS_SEMANTICS"
    )


@dataclasses.dataclass(frozen=True)
class FixtureStateSourcePlan:
    preferred_source_class: FixtureStateSourceClass
    preferred_upstream_contract: str | None
    official_corroboration: FixtureStateOfficialCorroboration
    observation_mode: FixtureStateObservationMode
    currently_reviewed_path_exists: bool
    implementation_state: FixtureStateImplementationState
    future_work_required: str

    def __post_init__(self) -> None:
        if type(self.preferred_source_class) is not FixtureStateSourceClass:
            raise FixtureStateV2Error("preferred source class must be typed")
        if self.preferred_upstream_contract is not None:
            _exact_source_plan_text(
                self.preferred_upstream_contract, "preferred upstream contract"
            )
        if type(self.official_corroboration) is not FixtureStateOfficialCorroboration:
            raise FixtureStateV2Error("official corroboration policy must be typed")
        if type(self.observation_mode) is not FixtureStateObservationMode:
            raise FixtureStateV2Error("observation mode must be typed")
        if type(self.currently_reviewed_path_exists) is not bool:
            raise FixtureStateV2Error("reviewed path flag must be an exact boolean")
        if type(self.implementation_state) is not FixtureStateImplementationState:
            raise FixtureStateV2Error("implementation state must be typed")
        _exact_source_plan_text(self.future_work_required, "future work")

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_source_class": self.preferred_source_class.value,
            "preferred_upstream_contract": self.preferred_upstream_contract,
            "official_corroboration": self.official_corroboration.value,
            "observation_mode": self.observation_mode.value,
            "currently_reviewed_path_exists": self.currently_reviewed_path_exists,
            "implementation_state": self.implementation_state.value,
            "future_work_required": self.future_work_required,
        }


def _exact_source_plan_text(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 512
    ):
        raise FixtureStateV2Error(f"{label} must be exact non-empty text")
    return value


@dataclasses.dataclass(frozen=True)
class FixtureStateFieldDefinition:
    field_id: FixtureStateFieldId
    family: FixtureStateFieldFamily
    value_type: FixtureStateValueType
    source_category: IntelligenceCategory | None
    source_field: str | None
    derivation: FixtureStateDerivation
    availability_expectation: FixtureStateAvailabilityExpectation
    source_plan: FixtureStateSourcePlan

    def __post_init__(self) -> None:
        if type(self.field_id) is not FixtureStateFieldId:
            raise FixtureStateV2Error("field definition field_id must be typed")
        if type(self.family) is not FixtureStateFieldFamily:
            raise FixtureStateV2Error("field definition family must be typed")
        if type(self.value_type) is not FixtureStateValueType:
            raise FixtureStateV2Error("field definition value_type must be typed")
        if type(self.derivation) is not FixtureStateDerivation:
            raise FixtureStateV2Error("field definition derivation must be typed")
        if type(self.availability_expectation) is not FixtureStateAvailabilityExpectation:
            raise FixtureStateV2Error(
                "field definition availability_expectation must be typed"
            )
        if type(self.source_plan) is not FixtureStateSourcePlan:
            raise FixtureStateV2Error("field definition source_plan must be typed")
        mapped = self.source_category is not None or self.source_field is not None
        if mapped:
            if type(self.source_category) is not IntelligenceCategory:
                raise FixtureStateV2Error("mapped field requires a source category")
            if (
                type(self.source_field) is not str
                or not self.source_field
                or self.source_field != self.source_field.strip()
            ):
                raise FixtureStateV2Error("mapped field requires an exact source field")
            if self.derivation is not FixtureStateDerivation.RAW_EVIDENCE_DERIVED:
                raise FixtureStateV2Error("mapped field must be raw evidence-derived")
            if (
                self.source_plan.implementation_state
                is not FixtureStateImplementationState.CURRENTLY_MAPPABLE
            ):
                raise FixtureStateV2Error(
                    "mapped field must have CURRENTLY_MAPPABLE source coverage"
                )
        elif self.derivation not in {
            FixtureStateDerivation.FUTURE_DERIVED_SLOT,
            FixtureStateDerivation.FUTURE_SOURCE_REQUIRED_SLOT,
            FixtureStateDerivation.PENDING_REVIEWED_ADAPTER_SLOT,
        }:
            raise FixtureStateV2Error("unmapped field must be an explicit future slot")

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id.value,
            "family": self.family.value,
            "value_type": self.value_type.value,
            "source_category": (
                None if self.source_category is None else self.source_category.value
            ),
            "source_field": self.source_field,
            "derivation": self.derivation.value,
            "availability_expectation": self.availability_expectation.value,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_identity_dict(),
            "source_plan": self.source_plan.to_dict(),
        }


def _mapped(
    field_id: FixtureStateFieldId,
    family: FixtureStateFieldFamily,
    value_type: FixtureStateValueType,
    category: IntelligenceCategory,
    source_field: str,
) -> FixtureStateFieldDefinition:
    return FixtureStateFieldDefinition(
        field_id=field_id,
        family=family,
        value_type=value_type,
        source_category=category,
        source_field=source_field,
        derivation=FixtureStateDerivation.RAW_EVIDENCE_DERIVED,
        availability_expectation=(
            FixtureStateAvailabilityExpectation.CURRENTLY_MAPPED_WHEN_QUALIFYING_EVIDENCE_EXISTS
        ),
        source_plan=_source_plan(field_id),
    )


def _future(
    field_id: FixtureStateFieldId,
    family: FixtureStateFieldFamily,
    value_type: FixtureStateValueType,
) -> FixtureStateFieldDefinition:
    source_plan = _source_plan(field_id)
    source_required = (
        source_plan.implementation_state
        is FixtureStateImplementationState.FUTURE_SOURCE_REQUIRED
    )
    pending_adapter = (
        source_plan.implementation_state
        is FixtureStateImplementationState.PARTIALLY_PROVEN_PENDING_V2_ADAPTER
    )
    return FixtureStateFieldDefinition(
        field_id=field_id,
        family=family,
        value_type=value_type,
        source_category=None,
        source_field=None,
        derivation=(
            FixtureStateDerivation.PENDING_REVIEWED_ADAPTER_SLOT
            if pending_adapter
            else (
                FixtureStateDerivation.FUTURE_SOURCE_REQUIRED_SLOT
                if source_required
                else FixtureStateDerivation.FUTURE_DERIVED_SLOT
            )
        ),
        availability_expectation=(
            FixtureStateAvailabilityExpectation.SCHEMA_SLOT_ONLY_PENDING_REVIEWED_ADAPTER
            if pending_adapter
            else (
                FixtureStateAvailabilityExpectation.SCHEMA_SLOT_ONLY_PENDING_FUTURE_REVIEWED_SOURCE
                if source_required
                else FixtureStateAvailabilityExpectation.SCHEMA_SLOT_ONLY_PENDING_FUTURE_REVIEWED_DERIVATION
            )
        ),
        source_plan=source_plan,
    )


def _source_plan(field_id: FixtureStateFieldId) -> FixtureStateSourcePlan:
    no_official = FixtureStateOfficialCorroboration.NOT_REQUIRED_BY_CURRENT_CONTRACT
    may_official = FixtureStateOfficialCorroboration.MAY_BE_REQUIRED_BY_FUTURE_POLICY

    if field_id in {FixtureStateFieldId.HOME_FORM, FixtureStateFieldId.AWAY_FORM}:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.FOTMOB_PRIMARY,
            preferred_upstream_contract=(
                "FixtureIntelligenceSnapshot FORM fact and reviewed "
                "fixture_model_features v1 binding"
            ),
            official_corroboration=no_official,
            observation_mode=FixtureStateObservationMode.DIRECTLY_OBSERVED,
            currently_reviewed_path_exists=True,
            implementation_state=FixtureStateImplementationState.CURRENTLY_MAPPABLE,
            future_work_required="Preserve prospective source qualification and as-of coverage.",
        )
    if field_id in {
        FixtureStateFieldId.HOME_ELO,
        FixtureStateFieldId.AWAY_ELO,
        FixtureStateFieldId.FATIGUE,
        FixtureStateFieldId.LIVE_DATA_FRESHNESS,
    }:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.ATHENA_DERIVED,
            preferred_upstream_contract=(
                "FixtureIntelligenceSnapshot exact fact and reviewed "
                "fixture_model_features v1 binding"
            ),
            official_corroboration=no_official,
            observation_mode=FixtureStateObservationMode.ATHENA_DERIVED,
            currently_reviewed_path_exists=True,
            implementation_state=FixtureStateImplementationState.CURRENTLY_MAPPABLE,
            future_work_required="Retain the reviewed v1 semantics in prospective as-of builders.",
        )
    if field_id in {
        FixtureStateFieldId.HOME_ATTACK_STRENGTH,
        FixtureStateFieldId.AWAY_ATTACK_STRENGTH,
        FixtureStateFieldId.HOME_DEFENSIVE_STRENGTH,
        FixtureStateFieldId.AWAY_DEFENSIVE_STRENGTH,
        FixtureStateFieldId.HOME_OPPONENT_ADJUSTED_ATTACK_STRENGTH,
        FixtureStateFieldId.AWAY_OPPONENT_ADJUSTED_ATTACK_STRENGTH,
        FixtureStateFieldId.HOME_OPPONENT_ADJUSTED_DEFENSIVE_STRENGTH,
        FixtureStateFieldId.AWAY_OPPONENT_ADJUSTED_DEFENSIVE_STRENGTH,
        FixtureStateFieldId.HOME_VENUE_ATTACK_STRENGTH,
        FixtureStateFieldId.HOME_VENUE_DEFENSIVE_STRENGTH,
        FixtureStateFieldId.AWAY_VENUE_ATTACK_STRENGTH,
        FixtureStateFieldId.AWAY_VENUE_DEFENSIVE_STRENGTH,
    }:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.ATHENA_DERIVED,
            preferred_upstream_contract=(
                "Future qualified ATHENA performance aggregate projected through "
                "FixtureIntelligenceSnapshot"
            ),
            official_corroboration=no_official,
            observation_mode=FixtureStateObservationMode.ATHENA_DERIVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_DERIVED,
            future_work_required="Define and validate the historical as-of strength derivation.",
        )
    if field_id in {
        FixtureStateFieldId.HOME_TACTICAL_IDENTITY,
        FixtureStateFieldId.AWAY_TACTICAL_IDENTITY,
    }:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.ATHENA_DERIVED,
            preferred_upstream_contract=None,
            official_corroboration=no_official,
            observation_mode=FixtureStateObservationMode.ATHENA_DERIVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_DERIVED,
            future_work_required="Phase 3 Tactical Identity Engine; no editorial or team-name rules.",
        )
    if field_id in {
        FixtureStateFieldId.HOME_MANAGER_REGIME_IDENTITY,
        FixtureStateFieldId.AWAY_MANAGER_REGIME_IDENTITY,
    }:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.ATHENA_DERIVED,
            preferred_upstream_contract=None,
            official_corroboration=may_official,
            observation_mode=FixtureStateObservationMode.ATHENA_DERIVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_DERIVED,
            future_work_required=(
                "Qualify FotMob or official manager evidence, then define regime segmentation."
            ),
        )
    if field_id in {
        FixtureStateFieldId.HOME_AVAILABILITY_STATE,
        FixtureStateFieldId.AWAY_AVAILABILITY_STATE,
        FixtureStateFieldId.HOME_LINEUP_STATE,
        FixtureStateFieldId.AWAY_LINEUP_STATE,
        FixtureStateFieldId.HOME_LINEUP_CONFIRMED,
        FixtureStateFieldId.AWAY_LINEUP_CONFIRMED,
        FixtureStateFieldId.HOME_LINEUP_FRESHNESS,
        FixtureStateFieldId.AWAY_LINEUP_FRESHNESS,
    }:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.FOTMOB_PRIMARY,
            preferred_upstream_contract=(
                "Exact reviewed FotMob ancestry: PR197 preserves LINEUP/"
                "source_lineup_type=predicted; separate handoff preserves exact "
                "unavailable-player counts but no generic v2 mapping"
            ),
            official_corroboration=may_official,
            observation_mode=FixtureStateObservationMode.DIRECTLY_OBSERVED,
            currently_reviewed_path_exists=False,
            implementation_state=(
                FixtureStateImplementationState.PARTIALLY_PROVEN_PENDING_V2_ADAPTER
            ),
            future_work_required=(
                "Add a reviewed FixtureIntelligence-to-v2 adapter, prospective "
                "freshness, broader fixture coverage, and confirmation policy."
            ),
        )
    if field_id is FixtureStateFieldId.VENUE:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.FOTMOB_PRIMARY,
            preferred_upstream_contract=None,
            official_corroboration=no_official,
            observation_mode=FixtureStateObservationMode.DIRECTLY_OBSERVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_SOURCE_REQUIRED,
            future_work_required="Qualify a prospective FotMob venue mapping.",
        )
    if field_id in {
        FixtureStateFieldId.HOME_TRAVEL_CONTEXT,
        FixtureStateFieldId.AWAY_TRAVEL_CONTEXT,
    }:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.ATHENA_DERIVED,
            preferred_upstream_contract=None,
            official_corroboration=no_official,
            observation_mode=FixtureStateObservationMode.ATHENA_DERIVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_DERIVED,
            future_work_required="Derive travel burden from verified fixture and venue geography.",
        )
    if field_id is FixtureStateFieldId.WEATHER:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.SPECIALIST_EXTERNAL,
            preferred_upstream_contract=None,
            official_corroboration=no_official,
            observation_mode=FixtureStateObservationMode.DIRECTLY_OBSERVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_SOURCE_REQUIRED,
            future_work_required="Qualify a meteorological provider and freshness policy.",
        )
    if field_id is FixtureStateFieldId.REFEREE:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.FOTMOB_PRIMARY,
            preferred_upstream_contract=None,
            official_corroboration=may_official,
            observation_mode=FixtureStateObservationMode.DIRECTLY_OBSERVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_SOURCE_REQUIRED,
            future_work_required="Review FotMob coverage or qualify an official competition source.",
        )
    if field_id is FixtureStateFieldId.COMPETITION_STAGE:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.FOTMOB_PRIMARY,
            preferred_upstream_contract=None,
            official_corroboration=may_official,
            observation_mode=FixtureStateObservationMode.DIRECTLY_OBSERVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_SOURCE_REQUIRED,
            future_work_required="Review FotMob stage semantics or qualify official competition data.",
        )
    if field_id is FixtureStateFieldId.MOTIVATION_MATCH_CONTEXT:
        return FixtureStateSourcePlan(
            preferred_source_class=FixtureStateSourceClass.ATHENA_DERIVED,
            preferred_upstream_contract=None,
            official_corroboration=may_official,
            observation_mode=FixtureStateObservationMode.ATHENA_DERIVED,
            currently_reviewed_path_exists=False,
            implementation_state=FixtureStateImplementationState.FUTURE_DERIVED,
            future_work_required=(
                "Derive only from objective competition state and explicit qualified evidence."
            ),
        )
    raise FixtureStateV2Error(f"missing source plan for {field_id.value}")


_L = FixtureStateFieldFamily.LEGACY_STRENGTH
_P = FixtureStateFieldFamily.TEAM_STRENGTH_PERFORMANCE
_T = FixtureStateFieldFamily.TACTICAL_REGIME
_A = FixtureStateFieldFamily.AVAILABILITY_LINEUP
_C = FixtureStateFieldFamily.CONTEXT
_N = FixtureStateValueType.FINITE_NUMBER
_S = FixtureStateValueType.CATEGORICAL_STRING
_B = FixtureStateValueType.BOOLEAN
_R = FixtureStateValueType.STRUCTURED_RECORD


FIXTURE_STATE_FIELD_REGISTRY: Tuple[FixtureStateFieldDefinition, ...] = tuple(
    sorted(
        (
            _mapped(FixtureStateFieldId.HOME_FORM, _L, _N, IntelligenceCategory.FORM, "home_form"),
            _mapped(FixtureStateFieldId.AWAY_FORM, _L, _N, IntelligenceCategory.FORM, "away_form"),
            _mapped(FixtureStateFieldId.HOME_ELO, _L, _N, IntelligenceCategory.PERFORMANCE, "home_elo"),
            _mapped(FixtureStateFieldId.AWAY_ELO, _L, _N, IntelligenceCategory.PERFORMANCE, "away_elo"),
            _mapped(FixtureStateFieldId.FATIGUE, _L, _N, IntelligenceCategory.SCHEDULE_LOAD, "fatigue"),
            _mapped(FixtureStateFieldId.LIVE_DATA_FRESHNESS, _L, _N, IntelligenceCategory.FIXTURE_CONTEXT, "live_data_freshness"),
            _future(FixtureStateFieldId.HOME_ATTACK_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.AWAY_ATTACK_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.HOME_DEFENSIVE_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.AWAY_DEFENSIVE_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.HOME_OPPONENT_ADJUSTED_ATTACK_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.AWAY_OPPONENT_ADJUSTED_ATTACK_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.HOME_OPPONENT_ADJUSTED_DEFENSIVE_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.AWAY_OPPONENT_ADJUSTED_DEFENSIVE_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.HOME_VENUE_ATTACK_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.HOME_VENUE_DEFENSIVE_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.AWAY_VENUE_ATTACK_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.AWAY_VENUE_DEFENSIVE_STRENGTH, _P, _N),
            _future(FixtureStateFieldId.HOME_TACTICAL_IDENTITY, _T, _S),
            _future(FixtureStateFieldId.AWAY_TACTICAL_IDENTITY, _T, _S),
            _future(FixtureStateFieldId.HOME_MANAGER_REGIME_IDENTITY, _T, _S),
            _future(FixtureStateFieldId.AWAY_MANAGER_REGIME_IDENTITY, _T, _S),
            _future(FixtureStateFieldId.HOME_AVAILABILITY_STATE, _A, _R),
            _future(FixtureStateFieldId.AWAY_AVAILABILITY_STATE, _A, _R),
            _future(FixtureStateFieldId.HOME_LINEUP_STATE, _A, _S),
            _future(FixtureStateFieldId.AWAY_LINEUP_STATE, _A, _S),
            _future(FixtureStateFieldId.HOME_LINEUP_CONFIRMED, _A, _B),
            _future(FixtureStateFieldId.AWAY_LINEUP_CONFIRMED, _A, _B),
            _future(FixtureStateFieldId.HOME_LINEUP_FRESHNESS, _A, _N),
            _future(FixtureStateFieldId.AWAY_LINEUP_FRESHNESS, _A, _N),
            _future(FixtureStateFieldId.VENUE, _C, _S),
            _future(FixtureStateFieldId.HOME_TRAVEL_CONTEXT, _C, _R),
            _future(FixtureStateFieldId.AWAY_TRAVEL_CONTEXT, _C, _R),
            _future(FixtureStateFieldId.WEATHER, _C, _R),
            _future(FixtureStateFieldId.REFEREE, _C, _S),
            _future(FixtureStateFieldId.COMPETITION_STAGE, _C, _S),
            _future(FixtureStateFieldId.MOTIVATION_MATCH_CONTEXT, _C, _R),
        ),
        key=lambda item: item.field_id.value,
    )
)

_DEFINITION_BY_ID = types.MappingProxyType(
    {definition.field_id: definition for definition in FIXTURE_STATE_FIELD_REGISTRY}
)
if (
    len(FIXTURE_STATE_FIELD_REGISTRY) != len(FixtureStateFieldId)
    or len(_DEFINITION_BY_ID) != len(FixtureStateFieldId)
):
    raise RuntimeError("Fixture State v2 registry must define every field exactly once")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureStateV2Error("Fixture State v2 canonical serialization failed") from exc


def _field_registry_identity_dict(
    registry: tuple[FixtureStateFieldDefinition, ...],
    version: int,
) -> dict[str, Any]:
    if type(registry) is not tuple or any(
        type(item) is not FixtureStateFieldDefinition for item in registry
    ):
        raise FixtureStateV2Error("field registry must be an exact definition tuple")
    if type(version) is not int or version <= 0:
        raise FixtureStateV2Error("field registry version must be a positive int")
    ids = tuple(item.field_id for item in registry)
    if ids != tuple(sorted(FixtureStateFieldId, key=lambda item: item.value)):
        raise FixtureStateV2Error(
            "field registry identity requires one sorted definition per field"
        )
    return {
        "field_registry_version": version,
        "fields": [item.to_identity_dict() for item in registry],
    }


def _field_registry_sha256(
    registry: tuple[FixtureStateFieldDefinition, ...],
    version: int,
) -> str:
    return hashlib.sha256(
        _canonical_bytes(_field_registry_identity_dict(registry, version))
    ).hexdigest()


EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION: Mapping[int, str] = (
    types.MappingProxyType(
        {
            1: "330e81a3fd8dc88c8fee98544d7f63e9d429c43c5d32ca761da5227e34de588a",
        }
    )
)


def _validated_field_registry_sha256(
    registry: tuple[FixtureStateFieldDefinition, ...],
    version: int,
    expected_sha256_by_version: Mapping[int, str],
) -> str:
    computed_sha256 = _field_registry_sha256(registry, version)
    expected_sha256 = expected_sha256_by_version.get(version)
    if expected_sha256 is None:
        raise FixtureStateV2Error(
            "field registry version has no independently pinned reviewed SHA-256"
        )
    if (
        type(expected_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256, flags=re.ASCII) is None
    ):
        raise FixtureStateV2Error(
            "pinned field registry SHA-256 must be exact lowercase SHA-256"
        )
    if computed_sha256 != expected_sha256:
        raise FixtureStateV2Error(
            "live stable field registry differs from its independently pinned "
            "reviewed SHA-256"
        )
    return computed_sha256


FIXTURE_STATE_FIELD_REGISTRY_SHA256 = _validated_field_registry_sha256(
    FIXTURE_STATE_FIELD_REGISTRY,
    FIXTURE_STATE_FIELD_REGISTRY_VERSION,
    EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_STRUCTURED_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "provider_acquisition_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "model_promotion_authorized",
        "calibration_authorized",
        "bookmaker_pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "accumulator_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FixtureStateV2Error(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise FixtureStateV2Error(f"{label} must be timezone-aware")
    try:
        return value.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureStateV2Error(f"{label} is invalid") from exc


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _finite_number(value: Any) -> float:
    if type(value) not in (int, float):
        raise FixtureStateV2Error("value must be a finite numeric scalar")
    result = float(value)
    if not math.isfinite(result):
        raise FixtureStateV2Error("value must not be NaN or Infinity")
    return result


def _exact_string(value: Any) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 512
    ):
        raise FixtureStateV2Error("value must be a non-empty exact string")
    return value


def _structured_scalar(value: Any) -> bool | float | str:
    if type(value) is bool:
        return value
    if type(value) in (int, float):
        return _finite_number(value)
    if type(value) is str:
        return _exact_string(value)
    raise FixtureStateV2Error(
        "structured record values must be finite numbers, exact strings, or booleans"
    )


def _structured_record(value: Any) -> tuple[tuple[str, bool | float | str], ...]:
    if isinstance(value, Mapping):
        raw_items = tuple(value.items())
    elif type(value) is tuple:
        raw_items = value
        if raw_items != tuple(sorted(raw_items, key=lambda item: item[0])):
            raise FixtureStateV2Error("structured record tuple must be key-sorted")
    else:
        raise FixtureStateV2Error("structured record must be a mapping or exact tuple")
    if not raw_items:
        raise FixtureStateV2Error("structured record must not be empty")
    normalized: list[tuple[str, bool | float | str]] = []
    for item in raw_items:
        if type(item) not in (tuple, list) or len(item) != 2:
            raise FixtureStateV2Error("structured record entries must be key/value pairs")
        key, child = item
        if type(key) is not str or _STRUCTURED_KEY_RE.fullmatch(key) is None:
            raise FixtureStateV2Error("structured record key is not canonical")
        normalized.append((key, _structured_scalar(child)))
    keys = [item[0] for item in normalized]
    if len(keys) != len(set(keys)):
        raise FixtureStateV2Error("structured record contains duplicate keys")
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _normalize_value(value: Any, value_type: FixtureStateValueType) -> Any:
    if value_type is FixtureStateValueType.FINITE_NUMBER:
        return _finite_number(value)
    if value_type is FixtureStateValueType.CATEGORICAL_STRING:
        return _exact_string(value)
    if value_type is FixtureStateValueType.BOOLEAN:
        if type(value) is not bool:
            raise FixtureStateV2Error("value must be an exact boolean")
        return value
    if value_type is FixtureStateValueType.STRUCTURED_RECORD:
        return _structured_record(value)
    raise FixtureStateV2Error("unsupported Fixture State value type")


def _thaw_normalized_value(value: Any) -> Any:
    """Serialize an already-normalized immutable value without registry lookup."""
    if value is None:
        return None
    if type(value) is tuple:
        return {key: child for key, child in value}
    return value


def _canonical_raw_value(value: Any) -> str:
    def thaw(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: thaw(child) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            return [thaw(child) for child in item]
        return item

    try:
        return json.dumps(
            thaw(value),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureStateV2Error("evidence value is not canonical JSON") from exc


@dataclasses.dataclass(frozen=True)
class FixtureStateEvidenceIdentity:
    category: IntelligenceCategory
    field: str
    fact_status: IntelligenceFactStatus
    source_role: SourceRole
    observed_at: datetime.datetime
    evidence_sha256: str
    source_provider: str
    source_reference: str

    def __post_init__(self) -> None:
        if type(self.category) is not IntelligenceCategory:
            raise FixtureStateV2Error("evidence category must be typed")
        if type(self.fact_status) is not IntelligenceFactStatus:
            raise FixtureStateV2Error("evidence fact_status must be typed")
        if type(self.source_role) is not SourceRole:
            raise FixtureStateV2Error("evidence source_role must be typed")
        _exact_string(self.field)
        observed = _utc(self.observed_at, "evidence observed_at")
        if type(self.evidence_sha256) is not str or _SHA256_RE.fullmatch(self.evidence_sha256) is None:
            raise FixtureStateV2Error("evidence_sha256 must be exact lowercase SHA-256")
        _exact_string(self.source_provider)
        _exact_string(self.source_reference)
        object.__setattr__(self, "observed_at", observed)

    @property
    def sort_key(self) -> tuple[str, str, str, str, str, str, str, str]:
        return (
            self.category.value,
            self.field,
            self.fact_status.value,
            self.source_role.value,
            _iso(self.observed_at),
            self.evidence_sha256,
            self.source_provider,
            self.source_reference,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "field": self.field,
            "fact_status": self.fact_status.value,
            "source_role": self.source_role.value,
            "observed_at": _iso(self.observed_at),
            "evidence_sha256": self.evidence_sha256,
            "source_provider": self.source_provider,
            "source_reference": self.source_reference,
        }


def _evidence_identity(fact: FixtureIntelligenceFact) -> FixtureStateEvidenceIdentity:
    return FixtureStateEvidenceIdentity(
        category=fact.category,
        field=fact.field,
        fact_status=fact.status,
        source_role=fact.source_role,
        observed_at=fact.observed_at,
        evidence_sha256=fact.evidence_sha256,
        source_provider=fact.source_provider,
        source_reference=fact.source_reference,
    )


@dataclasses.dataclass(frozen=True)
class FixtureStateFieldResolution:
    field_id: FixtureStateFieldId
    status: FixtureStateStatus
    value: Any
    blockers: Tuple[FixtureStateBlocker, ...]
    evidence: Tuple[FixtureStateEvidenceIdentity, ...]

    def __post_init__(self) -> None:
        if type(self.field_id) is not FixtureStateFieldId:
            raise FixtureStateV2Error("resolution field_id must be typed")
        if type(self.status) is not FixtureStateStatus:
            raise FixtureStateV2Error("resolution status must be typed")
        if type(self.blockers) is not tuple or any(
            type(item) is not FixtureStateBlocker for item in self.blockers
        ):
            raise FixtureStateV2Error("resolution blockers must be a typed tuple")
        if self.blockers != tuple(sorted(set(self.blockers), key=lambda item: item.value)):
            raise FixtureStateV2Error("resolution blockers must be unique and sorted")
        if type(self.evidence) is not tuple or any(
            type(item) is not FixtureStateEvidenceIdentity for item in self.evidence
        ):
            raise FixtureStateV2Error("resolution evidence must be a typed tuple")
        if self.evidence != tuple(sorted(set(self.evidence), key=lambda item: item.sort_key)):
            raise FixtureStateV2Error("resolution evidence must be unique and sorted")
        definition = _DEFINITION_BY_ID[self.field_id]
        if definition.source_category is not None and any(
            item.category is not definition.source_category
            or item.field != definition.source_field
            for item in self.evidence
        ):
            raise FixtureStateV2Error(
                "resolution evidence does not match registered source binding"
            )
        if self.status is FixtureStateStatus.AVAILABLE:
            normalized = _normalize_value(self.value, definition.value_type)
            if definition.source_category is None:
                raise FixtureStateV2Error(
                    "field has no currently approved AVAILABLE activation path"
                )
            if self.blockers:
                raise FixtureStateV2Error("AVAILABLE resolution cannot contain blockers")
            if not self.evidence or not any(
                item.fact_status is IntelligenceFactStatus.SUPPORTED
                for item in self.evidence
            ):
                raise FixtureStateV2Error(
                    "AVAILABLE resolution requires supported evidence identity"
                )
            object.__setattr__(self, "value", normalized)
        elif self.status is FixtureStateStatus.MISSING:
            if self.value is not None or self.blockers or self.evidence:
                raise FixtureStateV2Error(
                    "MISSING resolution must have null value and no blockers/evidence"
                )
        else:
            if self.value is not None:
                raise FixtureStateV2Error("BLOCKED resolution value must be null")
            if not self.blockers or not self.evidence:
                raise FixtureStateV2Error(
                    "BLOCKED resolution must retain blockers and evidence identities"
                )

    @property
    def evidence_sha256s(self) -> tuple[str, ...]:
        return tuple(sorted({item.evidence_sha256 for item in self.evidence}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id.value,
            "status": self.status.value,
            "value": _thaw_normalized_value(self.value),
            "blockers": [item.value for item in self.blockers],
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclasses.dataclass(frozen=True)
class FixtureStateCoverage:
    total_registered_fields: int
    available_count: int
    missing_count: int
    blocked_count: int
    available_ids: Tuple[FixtureStateFieldId, ...]
    missing_ids: Tuple[FixtureStateFieldId, ...]
    blocked_ids: Tuple[FixtureStateFieldId, ...]

    def __post_init__(self) -> None:
        for name in (
            "total_registered_fields",
            "available_count",
            "missing_count",
            "blocked_count",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise FixtureStateV2Error(f"coverage {name} must be non-negative int")
        for name in ("available_ids", "missing_ids", "blocked_ids"):
            value = getattr(self, name)
            if type(value) is not tuple or any(type(item) is not FixtureStateFieldId for item in value):
                raise FixtureStateV2Error(f"coverage {name} must be a typed tuple")
            if value != tuple(sorted(set(value), key=lambda item: item.value)):
                raise FixtureStateV2Error(f"coverage {name} must be unique and sorted")
        combined = self.available_ids + self.missing_ids + self.blocked_ids
        if len(set(combined)) != len(combined) or set(combined) != set(FixtureStateFieldId):
            raise FixtureStateV2Error("coverage IDs must partition the field registry")
        if (
            self.total_registered_fields != len(FixtureStateFieldId)
            or self.available_count != len(self.available_ids)
            or self.missing_count != len(self.missing_ids)
            or self.blocked_count != len(self.blocked_ids)
        ):
            raise FixtureStateV2Error("coverage counts do not match coverage IDs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_registered_fields": self.total_registered_fields,
            "available_count": self.available_count,
            "missing_count": self.missing_count,
            "blocked_count": self.blocked_count,
            "available_ids": [item.value for item in self.available_ids],
            "missing_ids": [item.value for item in self.missing_ids],
            "blocked_ids": [item.value for item in self.blocked_ids],
        }


def _coverage(resolutions: Tuple[FixtureStateFieldResolution, ...]) -> FixtureStateCoverage:
    by_status = {
        status: tuple(
            item.field_id for item in resolutions if item.status is status
        )
        for status in FixtureStateStatus
    }
    return FixtureStateCoverage(
        total_registered_fields=len(FixtureStateFieldId),
        available_count=len(by_status[FixtureStateStatus.AVAILABLE]),
        missing_count=len(by_status[FixtureStateStatus.MISSING]),
        blocked_count=len(by_status[FixtureStateStatus.BLOCKED]),
        available_ids=by_status[FixtureStateStatus.AVAILABLE],
        missing_ids=by_status[FixtureStateStatus.MISSING],
        blocked_ids=by_status[FixtureStateStatus.BLOCKED],
    )


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


@dataclasses.dataclass(frozen=True, init=False)
class FixtureStateV2Snapshot:
    schema_version: int
    dataset_name: str
    field_registry_version: int
    field_registry_sha256: str
    fixture_identifier: str
    kickoff: datetime.datetime
    as_of: datetime.datetime
    source_snapshot_dataset_name: str
    source_snapshot_schema_version: int
    source_snapshot_sha256: str
    fields: Tuple[FixtureStateFieldResolution, ...]
    safety: Mapping[str, bool]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise FixtureStateV2Error(
            "FixtureStateV2Snapshot is builder-only; replay an exact "
            "FixtureIntelligenceSnapshot"
        )

    @classmethod
    def _from_intelligence_snapshot(
        cls,
        intelligence_snapshot: FixtureIntelligenceSnapshot,
    ) -> FixtureStateV2Snapshot:
        if type(intelligence_snapshot) is not FixtureIntelligenceSnapshot:
            raise FixtureStateV2Error(
                "intelligence_snapshot must be exact FixtureIntelligenceSnapshot"
            )
        if intelligence_snapshot.as_of >= intelligence_snapshot.kickoff:
            raise FixtureStateV2Error("as_of must be strictly before kickoff")
        if any(
            fact.observed_at > intelligence_snapshot.as_of
            for fact in intelligence_snapshot.facts
        ):
            raise FixtureStateV2Error("evidence observed after as_of cannot enter state")

        registry_sha256 = _validated_field_registry_sha256(
            FIXTURE_STATE_FIELD_REGISTRY,
            FIXTURE_STATE_FIELD_REGISTRY_VERSION,
            EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION,
        )
        fields = tuple(
            _resolution_for(intelligence_snapshot, definition)
            for definition in FIXTURE_STATE_FIELD_REGISTRY
        )
        source_sha256 = sha256_bytes(canonical_snapshot_bytes(intelligence_snapshot))

        instance = object.__new__(cls)
        values = {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "field_registry_version": FIXTURE_STATE_FIELD_REGISTRY_VERSION,
            "field_registry_sha256": registry_sha256,
            "fixture_identifier": intelligence_snapshot.fixture_identifier,
            "kickoff": intelligence_snapshot.kickoff,
            "as_of": intelligence_snapshot.as_of,
            "source_snapshot_dataset_name": intelligence_snapshot.dataset_name,
            "source_snapshot_schema_version": intelligence_snapshot.schema_version,
            "source_snapshot_sha256": source_sha256,
            "fields": fields,
            "safety": _default_safety(),
        }
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FixtureStateV2Error(f"schema_version must be exact int {SCHEMA_VERSION}")
        if self.dataset_name != DATASET_NAME:
            raise FixtureStateV2Error(f"dataset_name must be {DATASET_NAME}")
        if type(self.field_registry_version) is not int or self.field_registry_version <= 0:
            raise FixtureStateV2Error("field_registry_version must be a positive int")
        if (
            type(self.field_registry_sha256) is not str
            or _SHA256_RE.fullmatch(self.field_registry_sha256) is None
        ):
            raise FixtureStateV2Error("field_registry_sha256 must be exact SHA-256")
        _exact_string(self.fixture_identifier)
        kickoff = _utc(self.kickoff, "kickoff")
        as_of = _utc(self.as_of, "as_of")
        if as_of >= kickoff:
            raise FixtureStateV2Error("as_of must be strictly before kickoff")
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "as_of", as_of)
        if self.source_snapshot_dataset_name != FIXTURE_INTELLIGENCE_DATASET_NAME:
            raise FixtureStateV2Error("source snapshot dataset must be fixture intelligence v1")
        if (
            type(self.source_snapshot_schema_version) is not int
            or self.source_snapshot_schema_version != FIXTURE_INTELLIGENCE_SCHEMA_VERSION
        ):
            raise FixtureStateV2Error("source snapshot schema version mismatch")
        if type(self.source_snapshot_sha256) is not str or _SHA256_RE.fullmatch(self.source_snapshot_sha256) is None:
            raise FixtureStateV2Error("source snapshot SHA-256 is invalid")
        if type(self.fields) is not tuple or any(
            type(item) is not FixtureStateFieldResolution for item in self.fields
        ):
            raise FixtureStateV2Error("fields must be a typed tuple")
        ids = tuple(item.field_id for item in self.fields)
        if ids != tuple(sorted(FixtureStateFieldId, key=lambda item: item.value)):
            raise FixtureStateV2Error(
                "fields must contain exactly one sorted resolution per registered field"
            )
        for resolution in self.fields:
            if any(item.observed_at > as_of for item in resolution.evidence):
                raise FixtureStateV2Error("evidence observed after as_of cannot enter state")
        if not isinstance(self.safety, Mapping) or set(self.safety) != _SAFETY_KEYS:
            raise FixtureStateV2Error("safety keys mismatch")
        detached: dict[str, bool] = {}
        for key in sorted(_SAFETY_KEYS):
            if type(self.safety[key]) is not bool or self.safety[key] is not False:
                raise FixtureStateV2Error(f"safety[{key!r}] must be exact false")
            detached[key] = False
        object.__setattr__(self, "safety", types.MappingProxyType(detached))

    @property
    def coverage(self) -> FixtureStateCoverage:
        return _coverage(self.fields)

    @property
    def field_index(self) -> Mapping[FixtureStateFieldId, FixtureStateFieldResolution]:
        return types.MappingProxyType({item.field_id: item for item in self.fields})

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "field_registry_version": self.field_registry_version,
            "field_registry_sha256": self.field_registry_sha256,
            "fixture_identifier": self.fixture_identifier,
            "kickoff": _iso(self.kickoff),
            "as_of": _iso(self.as_of),
            "source_snapshot_dataset_name": self.source_snapshot_dataset_name,
            "source_snapshot_schema_version": self.source_snapshot_schema_version,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "fields": [item.to_dict() for item in self.fields],
            "coverage": self.coverage.to_dict(),
            "safety": dict(self.safety),
        }

    def _source_coverage_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SOURCE_COVERAGE_SCHEMA_VERSION,
            "fields": [
                {
                    "field_id": item.field_id.value,
                    **item.source_plan.to_dict(),
                }
                for item in FIXTURE_STATE_FIELD_REGISTRY
            ],
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            **self._identity_dict(),
            "source_coverage": self._source_coverage_dict(),
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self._identity_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["canonical_sha256"] = self.canonical_sha256
        return result


def _resolution_for(
    snapshot: FixtureIntelligenceSnapshot,
    definition: FixtureStateFieldDefinition,
) -> FixtureStateFieldResolution:
    if definition.source_category is None:
        return FixtureStateFieldResolution(
            definition.field_id,
            FixtureStateStatus.MISSING,
            None,
            (),
            (),
        )
    matching = tuple(
        fact
        for fact in snapshot.facts
        if fact.category is definition.source_category
        and fact.field == definition.source_field
    )
    if not matching:
        return FixtureStateFieldResolution(
            definition.field_id,
            FixtureStateStatus.MISSING,
            None,
            (),
            (),
        )
    evidence = tuple(
        sorted({_evidence_identity(fact) for fact in matching}, key=lambda item: item.sort_key)
    )
    field_key = (definition.source_category.value, definition.source_field)
    conflicted = field_key in snapshot.conflicted_fields or any(
        fact.status is IntelligenceFactStatus.CONFLICTED for fact in matching
    )
    supported = tuple(
        fact for fact in matching if fact.status is IntelligenceFactStatus.SUPPORTED
    )
    if supported and not conflicted:
        try:
            canonical_values = {_canonical_raw_value(fact.value) for fact in supported}
        except FixtureStateV2Error:
            canonical_values = set()
        if len(canonical_values) > 1:
            conflicted = True
    if conflicted:
        return FixtureStateFieldResolution(
            definition.field_id,
            FixtureStateStatus.BLOCKED,
            None,
            (FixtureStateBlocker.CONFLICTED_EVIDENCE,),
            evidence,
        )
    if supported:
        try:
            value = _normalize_value(supported[0].value, definition.value_type)
        except FixtureStateV2Error:
            return FixtureStateFieldResolution(
                definition.field_id,
                FixtureStateStatus.BLOCKED,
                None,
                (FixtureStateBlocker.INVALID_SUPPORTED_VALUE,),
                evidence,
            )
        return FixtureStateFieldResolution(
            definition.field_id,
            FixtureStateStatus.AVAILABLE,
            value,
            (),
            evidence,
        )
    blockers = {FixtureStateBlocker.NO_SUPPORTED_EVIDENCE}
    if any(fact.status is IntelligenceFactStatus.STALE for fact in matching):
        blockers.add(FixtureStateBlocker.STALE_EVIDENCE_PRESENT)
    if any(fact.status is IntelligenceFactStatus.UNVERIFIED for fact in matching):
        blockers.add(FixtureStateBlocker.UNVERIFIED_EVIDENCE_PRESENT)
    return FixtureStateFieldResolution(
        definition.field_id,
        FixtureStateStatus.BLOCKED,
        None,
        tuple(sorted(blockers, key=lambda item: item.value)),
        evidence,
    )


def build_fixture_state_v2_snapshot(
    intelligence_snapshot: FixtureIntelligenceSnapshot,
) -> FixtureStateV2Snapshot:
    """Resolve the complete v2 registry from one preserved pre-match snapshot."""
    return FixtureStateV2Snapshot._from_intelligence_snapshot(intelligence_snapshot)


@dataclasses.dataclass(frozen=True)
class RequiredFixtureStateEvaluation:
    required_field_ids: Tuple[FixtureStateFieldId, ...]
    usable: bool
    available_field_ids: Tuple[FixtureStateFieldId, ...]
    missing_field_ids: Tuple[FixtureStateFieldId, ...]
    blocked_field_ids: Tuple[FixtureStateFieldId, ...]

    def __post_init__(self) -> None:
        for name in (
            "required_field_ids",
            "available_field_ids",
            "missing_field_ids",
            "blocked_field_ids",
        ):
            value = getattr(self, name)
            if type(value) is not tuple or any(type(item) is not FixtureStateFieldId for item in value):
                raise FixtureStateV2Error(f"{name} must be a typed tuple")
            if value != tuple(sorted(set(value), key=lambda item: item.value)):
                raise FixtureStateV2Error(f"{name} must be unique and sorted")
        if not self.required_field_ids:
            raise FixtureStateV2Error("required_field_ids must not be empty")
        partition = (
            self.available_field_ids
            + self.missing_field_ids
            + self.blocked_field_ids
        )
        if set(partition) != set(self.required_field_ids) or len(partition) != len(set(partition)):
            raise FixtureStateV2Error("requirement result must partition required fields")
        expected_usable = not self.missing_field_ids and not self.blocked_field_ids
        if type(self.usable) is not bool or self.usable is not expected_usable:
            raise FixtureStateV2Error("usable must reflect exact required field statuses")

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_field_ids": [item.value for item in self.required_field_ids],
            "usable": self.usable,
            "available_field_ids": [item.value for item in self.available_field_ids],
            "missing_field_ids": [item.value for item in self.missing_field_ids],
            "blocked_field_ids": [item.value for item in self.blocked_field_ids],
        }


def evaluate_required_fields(
    snapshot: FixtureStateV2Snapshot,
    required_field_ids: tuple[FixtureStateFieldId, ...],
) -> RequiredFixtureStateEvaluation:
    if type(snapshot) is not FixtureStateV2Snapshot:
        raise FixtureStateV2Error("snapshot must be exact FixtureStateV2Snapshot")
    if type(required_field_ids) is not tuple or any(
        type(item) is not FixtureStateFieldId for item in required_field_ids
    ):
        raise FixtureStateV2Error("required_field_ids must be an exact typed tuple")
    if len(required_field_ids) != len(set(required_field_ids)):
        raise FixtureStateV2Error("required_field_ids must not contain duplicates")
    required = tuple(sorted(required_field_ids, key=lambda item: item.value))
    index = snapshot.field_index
    available = tuple(
        item for item in required if index[item].status is FixtureStateStatus.AVAILABLE
    )
    missing = tuple(
        item for item in required if index[item].status is FixtureStateStatus.MISSING
    )
    blocked = tuple(
        item for item in required if index[item].status is FixtureStateStatus.BLOCKED
    )
    return RequiredFixtureStateEvaluation(
        required_field_ids=required,
        usable=not missing and not blocked,
        available_field_ids=available,
        missing_field_ids=missing,
        blocked_field_ids=blocked,
    )


def canonical_fixture_state_v2_bytes(snapshot: FixtureStateV2Snapshot) -> bytes:
    if type(snapshot) is not FixtureStateV2Snapshot:
        raise FixtureStateV2Error("snapshot must be exact FixtureStateV2Snapshot")
    return _canonical_bytes(snapshot._identity_dict())


def sha256_fixture_state_v2(snapshot: FixtureStateV2Snapshot) -> str:
    if type(snapshot) is not FixtureStateV2Snapshot:
        raise FixtureStateV2Error("snapshot must be exact FixtureStateV2Snapshot")
    return snapshot.canonical_sha256


__all__ = [
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "SOURCE_COVERAGE_SCHEMA_VERSION",
    "FIXTURE_STATE_FIELD_REGISTRY_VERSION",
    "FIXTURE_STATE_FIELD_REGISTRY_SHA256",
    "EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION",
    "FIXTURE_STATE_FIELD_REGISTRY",
    "FixtureStateAvailabilityExpectation",
    "FixtureStateBlocker",
    "FixtureStateCoverage",
    "FixtureStateDerivation",
    "FixtureStateEvidenceIdentity",
    "FixtureStateFieldDefinition",
    "FixtureStateFieldFamily",
    "FixtureStateFieldId",
    "FixtureStateFieldResolution",
    "FixtureStateImplementationState",
    "FixtureStateObservationMode",
    "FixtureStateOfficialCorroboration",
    "FixtureStateSourceClass",
    "FixtureStateSourcePlan",
    "FixtureStateStatus",
    "FixtureStateV2Error",
    "FixtureStateV2Snapshot",
    "FixtureStateValueType",
    "RequiredFixtureStateEvaluation",
    "build_fixture_state_v2_snapshot",
    "canonical_fixture_state_v2_bytes",
    "evaluate_required_fields",
    "sha256_fixture_state_v2",
]
