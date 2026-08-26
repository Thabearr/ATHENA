"""Strict Fixture State v2 qualification for ATHENA Market Router v1."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from domain._market_router_contracts import (
    CONTEXT_RISK_METHOD,
    MINIMUM_REVIEWED_CONTEXT_COMPLETENESS,
    MarketRouterError,
)
from domain.fixture_state_v2 import (
    FIXTURE_STATE_FIELD_REGISTRY,
    FIXTURE_STATE_FIELD_REGISTRY_SHA256,
    FixtureStateFieldId,
    FixtureStateImplementationState,
    FixtureStateStatus,
    FixtureStateV2Snapshot,
)

REVIEWED_ROUTER_CONTEXT_FIELD_IDS = tuple(sorted(
    (
        definition.field_id
        for definition in FIXTURE_STATE_FIELD_REGISTRY
        if definition.source_plan.currently_reviewed_path_exists
        and definition.source_plan.implementation_state
        is FixtureStateImplementationState.CURRENTLY_MAPPABLE
    ),
    key=lambda item: item.value,
))

EXCLUDED_FUTURE_CONTEXT_FIELD_IDS = tuple(sorted(
    (item for item in FixtureStateFieldId if item not in REVIEWED_ROUTER_CONTEXT_FIELD_IDS),
    key=lambda item: item.value,
))


@dataclass(frozen=True)
class RouterContextQualification:
    fixture_state_sha256: str
    fixture_identifier: str
    required_field_ids: tuple[FixtureStateFieldId, ...]
    available_field_ids: tuple[FixtureStateFieldId, ...]
    missing_field_ids: tuple[FixtureStateFieldId, ...]
    blocked_field_ids: tuple[FixtureStateFieldId, ...]
    excluded_future_field_ids: tuple[FixtureStateFieldId, ...]
    completeness: float
    passed: bool
    context_risk_method: str
    context_risk_buffer: None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_state_sha256": self.fixture_state_sha256,
            "fixture_identifier": self.fixture_identifier,
            "required_field_ids": [item.value for item in self.required_field_ids],
            "available_field_ids": [item.value for item in self.available_field_ids],
            "missing_field_ids": [item.value for item in self.missing_field_ids],
            "blocked_field_ids": [item.value for item in self.blocked_field_ids],
            "excluded_future_field_ids": [item.value for item in self.excluded_future_field_ids],
            "completeness": self.completeness,
            "passed": self.passed,
            "context_risk_method": self.context_risk_method,
            "context_risk_buffer": self.context_risk_buffer,
        }


def qualify_router_context(snapshot: FixtureStateV2Snapshot) -> RouterContextQualification:
    if type(snapshot) is not FixtureStateV2Snapshot:
        raise MarketRouterError("fixture_state must be exact FixtureStateV2Snapshot")
    if snapshot.field_registry_sha256 != FIXTURE_STATE_FIELD_REGISTRY_SHA256:
        raise MarketRouterError("Fixture State field registry identity mismatch")
    index = snapshot.field_index
    required = REVIEWED_ROUTER_CONTEXT_FIELD_IDS
    available = tuple(item for item in required if index[item].status is FixtureStateStatus.AVAILABLE)
    missing = tuple(item for item in required if index[item].status is FixtureStateStatus.MISSING)
    blocked = tuple(item for item in required if index[item].status is FixtureStateStatus.BLOCKED)
    if len(available) + len(missing) + len(blocked) != len(required):
        raise MarketRouterError("reviewed context field status is not exhaustive")
    completeness = len(available) / len(required) if required else 0.0
    passed = (
        not blocked
        and completeness >= MINIMUM_REVIEWED_CONTEXT_COMPLETENESS
        and not missing
    )
    return RouterContextQualification(
        fixture_state_sha256=snapshot.canonical_sha256,
        fixture_identifier=snapshot.fixture_identifier,
        required_field_ids=required,
        available_field_ids=available,
        missing_field_ids=missing,
        blocked_field_ids=blocked,
        excluded_future_field_ids=EXCLUDED_FUTURE_CONTEXT_FIELD_IDS,
        completeness=completeness,
        passed=passed,
        context_risk_method=CONTEXT_RISK_METHOD,
        context_risk_buffer=None,
    )


def router_context_contract_summary() -> Mapping[str, Any]:
    return MappingProxyType({
        "required_field_ids": tuple(item.value for item in REVIEWED_ROUTER_CONTEXT_FIELD_IDS),
        "excluded_future_field_ids": tuple(item.value for item in EXCLUDED_FUTURE_CONTEXT_FIELD_IDS),
        "minimum_completeness": MINIMUM_REVIEWED_CONTEXT_COMPLETENESS,
        "context_risk_method": CONTEXT_RISK_METHOD,
        "context_risk_buffer": None,
    })


__all__ = [name for name in globals() if not name.startswith("_")]
