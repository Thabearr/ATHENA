"""Types for all-market Shadow probability settlement (PR C)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from types import MappingProxyType
from typing import Any, Mapping, Optional

from domain.markets import MarketFamily, MarketId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    PricingAuthority,
    SelectionAuthority,
    SettlementCapability,
)
from domain.score_matrix_market_probabilities import (
    AnalyticalEventProbability,
    AnalyticalSettlementDistribution,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-all-market-shadow-probability-settlement-v1"
DEFAULT_TOTAL_GOALS_LINE = 2.5
DEFAULT_AH_HOME_LINES: tuple[float, ...] = (-0.5, 0.0, 0.5, -0.25, 0.25, -0.75, 0.75)
SETTLEMENT_SUM_TOLERANCE = 1e-12

_AUTHORITY_KEYS = (
    "production_model",
    "production_probability",
    "score_matrix_production",
    "phase6",
    "production_price_all",
    "production_market_router",
    "production_portfolio",
    "production_selection",
    "sportybet_execution",
    "staking",
    "bet",
    "wager_placed",
)


class ShadowDisposition(str, Enum):
    ANALYTICAL_READY = "ANALYTICAL_READY"
    ANALYTICAL_READY_PROVIDER_BLOCKED = "ANALYTICAL_READY_PROVIDER_BLOCKED"
    MISSING_REQUIRED_INPUT = "MISSING_REQUIRED_INPUT"
    UNSUPPORTED_EXACT_LINE = "UNSUPPORTED_EXACT_LINE"
    NO_REVIEWED_XG = "NO_REVIEWED_XG"
    SPECIALIST_FEATURES_MISSING = "SPECIALIST_FEATURES_MISSING"
    PROVIDER_UNPROVEN = "PROVIDER_UNPROVEN"
    OUTSIDE_REVIEWED_XG_WINDOW = "OUTSIDE_REVIEWED_XG_WINDOW"


class AllMarketShadowError(ValueError):
    """Raised when the Shadow surface cannot be constructed defensibly."""


def _authority_map() -> Mapping[str, bool]:
    return MappingProxyType({key: False for key in _AUTHORITY_KEYS})


def _finite_non_negative(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise AllMarketShadowError(f"{label} must be a finite non-negative number")
    return float(value)


def _probability(value: Any, label: str = "probability") -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise AllMarketShadowError(f"{label} must be a finite probability in [0, 1]")
    return float(value)


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    import json
    try:
        return (
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AllMarketShadowError("canonical serialization failed") from exc


@dataclass(frozen=True)
class ResearchXGRates:
    """Reviewed research/shadow expected-goals pair (not production authority)."""

    calibrated_home: float
    calibrated_away: float
    sealed_prediction_sha256: Optional[str] = None
    feature_projection_identity: Optional[str] = None
    history_prefix_identity: Optional[str] = None
    source_fixture_identity: Optional[str] = None
    completeness_status: str = "SEALED_RESEARCH_RATES"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "calibrated_home", _finite_non_negative(self.calibrated_home, "calibrated_home")
        )
        object.__setattr__(
            self, "calibrated_away", _finite_non_negative(self.calibrated_away, "calibrated_away")
        )
        for field in (
            "sealed_prediction_sha256",
            "feature_projection_identity",
            "history_prefix_identity",
            "source_fixture_identity",
        ):
            value = getattr(self, field)
            if value is not None and (type(value) is not str or not value.strip()):
                raise AllMarketShadowError(f"{field} must be non-empty string or None")
        if type(self.completeness_status) is not str or not self.completeness_status.strip():
            raise AllMarketShadowError("completeness_status must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "calibrated_home": self.calibrated_home,
            "calibrated_away": self.calibrated_away,
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "feature_projection_identity": self.feature_projection_identity,
            "history_prefix_identity": self.history_prefix_identity,
            "source_fixture_identity": self.source_fixture_identity,
            "completeness_status": self.completeness_status,
            "production_authority": False,
        }


@dataclass(frozen=True)
class ShadowMarketAssessment:
    market_id: MarketId
    market_family: MarketFamily
    disposition: ShadowDisposition
    probability_method: Optional[str]
    probability_input_namespace: Optional[str]
    analytical_capability: AnalyticalProbabilityCapability
    settlement_capability: SettlementCapability
    event_probabilities: tuple[AnalyticalEventProbability, ...]
    settlement_distributions: tuple[AnalyticalSettlementDistribution, ...]
    required_inputs: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    blocker_reason: Optional[str]
    provider_semantic_status: Optional[str]
    pricing_authority: PricingAuthority
    selection_authority: SelectionAuthority
    score_matrix_audit: Optional[Mapping[str, Any]] = None
    specialist_evidence: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        if type(self.market_id) is not MarketId:
            raise AllMarketShadowError("market_id must be exact MarketId")
        if type(self.disposition) is not ShadowDisposition:
            raise AllMarketShadowError("disposition must be exact ShadowDisposition")
        if self.pricing_authority is not PricingAuthority.NOT_AUTHORIZED:
            raise AllMarketShadowError("pricing_authority must remain NOT_AUTHORIZED")
        if self.selection_authority is not SelectionAuthority.NOT_AUTHORIZED:
            raise AllMarketShadowError("selection_authority must remain NOT_AUTHORIZED")
        if type(self.event_probabilities) is not tuple or any(
            type(item) is not AnalyticalEventProbability for item in self.event_probabilities
        ):
            raise AllMarketShadowError("event_probabilities must be exact tuple")
        if type(self.settlement_distributions) is not tuple or any(
            type(item) is not AnalyticalSettlementDistribution
            for item in self.settlement_distributions
        ):
            raise AllMarketShadowError("settlement_distributions must be exact tuple")
        for item in self.event_probabilities:
            _probability(item.probability, f"{self.market_id.value} event probability")
        for item in self.settlement_distributions:
            total = item.settlement.total_probability
            if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=SETTLEMENT_SUM_TOLERANCE):
                raise AllMarketShadowError(
                    f"{self.market_id.value} settlement mass does not sum to 1"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "market_family": self.market_family.value,
            "disposition": self.disposition.value,
            "probability_method": self.probability_method,
            "probability_input_namespace": self.probability_input_namespace,
            "analytical_capability": self.analytical_capability.value,
            "settlement_capability": self.settlement_capability.value,
            "event_probabilities": [item.to_dict() for item in self.event_probabilities],
            "settlement_distributions": [
                item.to_dict() for item in self.settlement_distributions
            ],
            "required_inputs": list(self.required_inputs),
            "missing_inputs": list(self.missing_inputs),
            "blocker_reason": self.blocker_reason,
            "provider_semantic_status": self.provider_semantic_status,
            "pricing_authority": self.pricing_authority.value,
            "selection_authority": self.selection_authority.value,
            "score_matrix_audit": (
                dict(self.score_matrix_audit) if self.score_matrix_audit is not None else None
            ),
            "specialist_evidence": (
                dict(self.specialist_evidence) if self.specialist_evidence is not None else None
            ),
        }


# Research lane markers (PR D binds Price-all to CURRENT_SOURCE_BOUND only)
SOURCE_LANE_MATHEMATICAL_TEST = "MATHEMATICAL_TEST"
SOURCE_LANE_CURRENT_SOURCE_BOUND = "CURRENT_SOURCE_BOUND"


@dataclass(frozen=True)
class CurrentAllMarketShadowFixtureScan:
    fixture_identity: str
    kickoff_utc_iso: Optional[str]
    research_xg: Optional[ResearchXGRates]
    score_matrix_audit: Optional[Mapping[str, Any]]
    market_assessments: tuple[ShadowMarketAssessment, ...]
    authority: Mapping[str, bool]
    source_lane: str = SOURCE_LANE_MATHEMATICAL_TEST

    def __post_init__(self) -> None:
        if type(self.fixture_identity) is not str or not self.fixture_identity.strip():
            raise AllMarketShadowError("fixture_identity must be non-empty")
        if type(self.market_assessments) is not tuple:
            raise AllMarketShadowError("market_assessments must be a tuple")
        if len(self.market_assessments) != len(MarketId):
            raise AllMarketShadowError(
                f"expected exactly {len(MarketId)} market rows, got {len(self.market_assessments)}"
            )
        seen: set[MarketId] = set()
        for assessment in self.market_assessments:
            if type(assessment) is not ShadowMarketAssessment:
                raise AllMarketShadowError("assessment type mismatch")
            if assessment.market_id in seen:
                raise AllMarketShadowError(f"duplicate market {assessment.market_id.value}")
            seen.add(assessment.market_id)
        if seen != set(MarketId):
            missing = set(MarketId) - seen
            raise AllMarketShadowError(f"missing markets: {sorted(m.value for m in missing)}")
        if not isinstance(self.authority, Mapping) or set(self.authority) != set(_AUTHORITY_KEYS):
            raise AllMarketShadowError("authority keys mismatch")
        if any(self.authority[key] is not False for key in _AUTHORITY_KEYS):
            raise AllMarketShadowError("all authority flags must be false")
        object.__setattr__(self, "authority", _authority_map())

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identity": self.fixture_identity,
            "kickoff_utc_iso": self.kickoff_utc_iso,
            "research_xg": None if self.research_xg is None else self.research_xg.to_dict(),
            "score_matrix_audit": (
                dict(self.score_matrix_audit) if self.score_matrix_audit is not None else None
            ),
            "market_assessments": [item.to_dict() for item in self.market_assessments],
            "authority": dict(self.authority),
            "source_lane": self.source_lane,
        }


@dataclass(frozen=True)
class CurrentAllMarketShadowScan:
    schema_version: int
    dataset_name: str
    fixtures: tuple[CurrentAllMarketShadowFixtureScan, ...]
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise AllMarketShadowError("scan schema identity mismatch")
        if type(self.fixtures) is not tuple or not self.fixtures:
            raise AllMarketShadowError("fixtures must be a non-empty tuple")
        identities = [f.fixture_identity for f in self.fixtures]
        if len(set(identities)) != len(identities):
            raise AllMarketShadowError("duplicate fixture identities rejected")
        if not isinstance(self.authority, Mapping) or set(self.authority) != set(_AUTHORITY_KEYS):
            raise AllMarketShadowError("authority keys mismatch")
        if any(self.authority[key] is not False for key in _AUTHORITY_KEYS):
            raise AllMarketShadowError("all authority flags must be false")
        object.__setattr__(self, "authority", _authority_map())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "fixtures": [item.to_dict() for item in self.fixtures],
            "authority": dict(self.authority),
            "wager_placed": False,
        }
