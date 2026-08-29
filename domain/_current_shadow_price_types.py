"""Research-only Shadow Price-all / Router types (PR D).

Separate from Phase-7 CalibratedValueCandidate. No production authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-all-market-price-all-router-v1"
DEVIG_POLICY_ID = "PROPORTIONAL_ONLY_MUTUALLY_EXCLUSIVE_EXHAUSTIVE_PARTITIONS_V1"
SETTLEMENT_RETURN_POLICY_ID = "UNIT_STAKE_FULL_PUSH_SPLIT_SETTLEMENT_RETURNS_V1"
ROUTER_POLICY_ID = "SHADOW_CONSERVATIVE_FROZEN_THRESHOLDS_V1"
QUOTE_POLICY_ID = "EXACT_SOURCE_BOUND_SPORTYBET_SELECTION_IDENTITY_V1"
MAX_QUOTE_AGE_SECONDS = 900

MINIMUM_EVENT_PROBABILITY = 0.55
MINIMUM_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_EDGE = 0.0

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)

AUTHORITY_FLAGS = MappingProxyType(
    {
        "research_current_quote_consumption": True,
        "research_shadow_price_all": True,
        "research_shadow_market_routing": True,
        "research_counterfactual_recording": True,
        "production_model": False,
        "production_probability": False,
        "phase6": False,
        "production_price_all": False,
        "production_market_router": False,
        "production_portfolio": False,
        "production_selection": False,
        "accumulator": False,
        "slip_construction": False,
        "share_code_generation": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)

ORDINARY_PARTITIONS: Mapping[MarketId, tuple[OutcomeId, ...]] = MappingProxyType(
    {
        MarketId.MATCH_RESULT: (OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
        MarketId.BTTS: (OutcomeId.YES, OutcomeId.NO),
        MarketId.TOTAL_GOALS: (OutcomeId.OVER, OutcomeId.UNDER),
        MarketId.DRAW_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
        MarketId.HOME_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
        MarketId.AWAY_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
        MarketId.HOME_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
        MarketId.AWAY_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
        MarketId.HOME_WIN_EITHER_HALF: (OutcomeId.YES, OutcomeId.NO),
        MarketId.AWAY_WIN_EITHER_HALF: (OutcomeId.YES, OutcomeId.NO),
    }
)

OVERLAPPING_MARKETS = frozenset(
    {MarketId.DOUBLE_CHANCE, MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}
)
PUSH_SPLIT_MARKETS = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})


class ShadowPriceError(ValueError):
    """Raised when Shadow Price-all / Router input fails closed."""


class ShadowPriceDisposition(str, Enum):
    PRICED = "PRICED"
    UNPRICED_NO_EXACT_QUOTE = "UNPRICED_NO_EXACT_QUOTE"
    UNPRICED_AMBIGUOUS_QUOTE = "UNPRICED_AMBIGUOUS_QUOTE"
    UNPRICED_STALE_QUOTE = "UNPRICED_STALE_QUOTE"
    UNPRICED_FUTURE_QUOTE = "UNPRICED_FUTURE_QUOTE"
    UNPRICED_PROVIDER_BLOCKED = "UNPRICED_PROVIDER_BLOCKED"
    UNPRICED_UPSTREAM_BLOCKED = "UNPRICED_UPSTREAM_BLOCKED"
    UNPRICED_INVALID_ODDS = "UNPRICED_INVALID_ODDS"
    UNPRICED_SETTLEMENT_INCOMPLETE = "UNPRICED_SETTLEMENT_INCOMPLETE"
    UNPRICED_SOURCE_MISMATCH = "UNPRICED_SOURCE_MISMATCH"
    AUDIT_ONLY_UPSTREAM_BLOCKED = "AUDIT_ONLY_UPSTREAM_BLOCKED"


class ShadowDevigStatus(str, Enum):
    PROPORTIONAL_COMPLETE_PARTITION = "PROPORTIONAL_COMPLETE_PARTITION"
    NOT_IDENTIFIABLE_OVERLAPPING_EVENTS = "NOT_IDENTIFIABLE_OVERLAPPING_EVENTS"
    NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT = "NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT"
    INCOMPLETE_PARTITION = "INCOMPLETE_PARTITION"
    CROSS_SNAPSHOT = "CROSS_SNAPSHOT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ShadowRouterDecisionStatus(str, Enum):
    SELECTED = "SELECTED"
    NO_BET = "NO_BET"


class ShadowOpportunityEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"


class ShadowModelAgreementStatus(str, Enum):
    SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE = "SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha(value: Optional[str], label: str) -> Optional[str]:
    if value is None:
        return None
    if type(value) is not str or not _SHA_RE.fullmatch(value):
        raise ShadowPriceError(f"{label} must be exact 64-char lowercase hex SHA-256")
    return value


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ShadowPriceError(f"{label} must be finite numeric")
    return float(value)


def _probability(value: float, label: str) -> float:
    p = _finite(value, label)
    if p < 0.0 or p > 1.0:
        raise ShadowPriceError(f"{label} must be in [0, 1]")
    return p


def _odds(value: float, label: str = "decimal_odds") -> float:
    o = _finite(value, label)
    if o <= 1.0:
        raise ShadowPriceError(f"{label} must be > 1")
    return o


@dataclass(frozen=True)
class ShadowExactQuote:
    fixture_identity: str
    provider_event_id: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: Optional[float]
    provider_market_id: str
    provider_market_name: str
    provider_specifier: Optional[str]
    provider_outcome_id: str
    provider_outcome_name: str
    decimal_odds: float
    observed_at: datetime
    source_raw_sha256: str
    source_manifest_sha256: str
    source_inventory_sha256: str
    provider_semantic_status: str
    bookable: bool = True

    def __post_init__(self) -> None:
        if type(self.fixture_identity) is not str or not self.fixture_identity.strip():
            raise ShadowPriceError("fixture_identity must be non-empty")
        if type(self.provider_event_id) is not str or not _EVENT_RE.fullmatch(self.provider_event_id):
            raise ShadowPriceError("provider_event_id must be exact sr:match:N")
        if type(self.market_id) is not MarketId:
            raise ShadowPriceError("market_id must be exact MarketId")
        if type(self.outcome_id) is not OutcomeId:
            raise ShadowPriceError("outcome_id must be exact OutcomeId")
        object.__setattr__(self, "decimal_odds", _odds(self.decimal_odds))
        if type(self.observed_at) is not datetime or self.observed_at.tzinfo is None:
            raise ShadowPriceError("observed_at must be timezone-aware datetime")
        for label, value in (
            ("source_raw_sha256", self.source_raw_sha256),
            ("source_manifest_sha256", self.source_manifest_sha256),
            ("source_inventory_sha256", self.source_inventory_sha256),
        ):
            _require_sha(value, label)
        if self.line is not None:
            object.__setattr__(self, "line", _finite(self.line, "line"))
        if self.bookable is not True:
            raise ShadowPriceError("quote must be bookable")

    @property
    def selection_identity(self) -> tuple[str, str, Optional[str], str]:
        return (
            self.provider_event_id,
            self.provider_market_id,
            self.provider_specifier,
            self.provider_outcome_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identity": self.fixture_identity,
            "provider_event_id": self.provider_event_id,
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "decimal_odds": self.decimal_odds,
            "observed_at": self.observed_at.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
            "source_raw_sha256": self.source_raw_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "provider_semantic_status": self.provider_semantic_status,
            "bookable": self.bookable,
        }

    def identity_sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True)
class ShadowPriceResult:
    fixture_identity: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: Optional[float]
    disposition: ShadowPriceDisposition
    model_probability: Optional[float]
    decimal_odds: Optional[float]
    implied_probability: Optional[float]
    fair_probability: Optional[float]
    overround: Optional[float]
    devig_status: Optional[ShadowDevigStatus]
    net_expected_value: Optional[float]
    expected_return_multiplier: Optional[float]
    settlement_state_probabilities: tuple[tuple[str, float], ...]
    settlement_unit_returns: tuple[tuple[str, float], ...]
    quote_identity_sha256: Optional[str]
    provider_event_id: Optional[str]
    provider_semantic_status: Optional[str]
    rejection_reason: Optional[str]
    probability_method: Optional[str]
    score_matrix_audit: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        if type(self.disposition) is not ShadowPriceDisposition:
            raise ShadowPriceError("disposition must be exact ShadowPriceDisposition")
        if self.model_probability is not None:
            object.__setattr__(
                self, "model_probability", _probability(self.model_probability, "model_probability")
            )
        if self.decimal_odds is not None:
            object.__setattr__(self, "decimal_odds", _finite(self.decimal_odds, "decimal_odds"))
        if self.net_expected_value is not None:
            object.__setattr__(
                self, "net_expected_value", _finite(self.net_expected_value, "net_expected_value")
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identity": self.fixture_identity,
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "disposition": self.disposition.value,
            "model_probability": self.model_probability,
            "decimal_odds": self.decimal_odds,
            "implied_probability": self.implied_probability,
            "fair_probability": self.fair_probability,
            "overround": self.overround,
            "devig_status": None if self.devig_status is None else self.devig_status.value,
            "net_expected_value": self.net_expected_value,
            "expected_return_multiplier": self.expected_return_multiplier,
            "settlement_state_probabilities": [
                {"state": s, "probability": p} for s, p in self.settlement_state_probabilities
            ],
            "settlement_unit_returns": [
                {"state": s, "unit_return": r} for s, r in self.settlement_unit_returns
            ],
            "quote_identity_sha256": self.quote_identity_sha256,
            "provider_event_id": self.provider_event_id,
            "provider_semantic_status": self.provider_semantic_status,
            "rejection_reason": self.rejection_reason,
            "probability_method": self.probability_method,
        }

    def opportunity_id(self) -> str:
        return _sha256(
            {
                "fixture": self.fixture_identity,
                "market": self.market_id.value,
                "outcome": self.outcome_id.value,
                "line": self.line,
                "quote": self.quote_identity_sha256,
            }
        )


@dataclass(frozen=True)
class ShadowRoutedOpportunity:
    opportunity_id: str
    price_result: ShadowPriceResult
    eligibility: ShadowOpportunityEligibility
    robust_net_expected_value: Optional[float]
    robust_edge: Optional[float]
    event_probability_floor: Optional[float]
    model_agreement: ShadowModelAgreementStatus
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "price_result": self.price_result.to_dict(),
            "eligibility": self.eligibility.value,
            "robust_net_expected_value": self.robust_net_expected_value,
            "robust_edge": self.robust_edge,
            "event_probability_floor": self.event_probability_floor,
            "model_agreement": self.model_agreement.value,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class ShadowMarketRouterDecision:
    fixture_identity: str
    status: ShadowRouterDecisionStatus
    selected_opportunity_id: Optional[str]
    runner_up_opportunity_id: Optional[str]
    strongest_rejected_opportunity_id: Optional[str]
    opportunities: tuple[ShadowRoutedOpportunity, ...]
    price_results: tuple[ShadowPriceResult, ...]
    router_policy_id: str
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.status) is not ShadowRouterDecisionStatus:
            raise ShadowPriceError("status must be exact ShadowRouterDecisionStatus")
        if any(
            self.authority.get(k)
            for k in (
                "production_price_all",
                "production_market_router",
                "production_selection",
                "bet",
                "wager_placed",
                "staking",
                "sportybet_execution",
            )
        ):
            raise ShadowPriceError("production/execution authority must remain false")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "fixture_identity": self.fixture_identity,
            "status": self.status.value,
            "selected_opportunity_id": self.selected_opportunity_id,
            "runner_up_opportunity_id": self.runner_up_opportunity_id,
            "strongest_rejected_opportunity_id": self.strongest_rejected_opportunity_id,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "price_results": [item.to_dict() for item in self.price_results],
            "router_policy_id": self.router_policy_id,
            "authority": dict(self.authority),
            "wager_placed": False,
        }

    def decision_sha256(self) -> str:
        return _sha256(self.to_dict())


def settlement_unit_return(state: str, decimal_odds: float) -> float:
    if state == "WIN":
        return decimal_odds - 1.0
    if state == "HALF_WIN":
        return (decimal_odds - 1.0) / 2.0
    if state == "PUSH":
        return 0.0
    if state == "HALF_LOSS":
        return -0.5
    if state == "LOSS":
        return -1.0
    raise ShadowPriceError(f"unknown settlement state {state}")


__all__ = [
    "AUTHORITY_FLAGS",
    "DATASET_NAME",
    "DEVIG_POLICY_ID",
    "MAX_QUOTE_AGE_SECONDS",
    "MINIMUM_EVENT_PROBABILITY",
    "MINIMUM_NET_EXPECTED_VALUE",
    "MINIMUM_ROBUST_EDGE",
    "MINIMUM_ROBUST_NET_EXPECTED_VALUE",
    "ORDINARY_PARTITIONS",
    "OVERLAPPING_MARKETS",
    "PUSH_SPLIT_MARKETS",
    "QUOTE_POLICY_ID",
    "ROUTER_POLICY_ID",
    "SCHEMA_VERSION",
    "SETTLEMENT_RETURN_POLICY_ID",
    "ShadowDevigStatus",
    "ShadowExactQuote",
    "ShadowMarketRouterDecision",
    "ShadowModelAgreementStatus",
    "ShadowOpportunityEligibility",
    "ShadowPriceDisposition",
    "ShadowPriceError",
    "ShadowPriceResult",
    "ShadowRoutedOpportunity",
    "ShadowRouterDecisionStatus",
    "settlement_unit_return",
    "_canonical_bytes",
    "_sha256",
]
