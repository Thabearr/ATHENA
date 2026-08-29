"""Shadow Price-all record dataclasses (PR D)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId
from domain._current_shadow_price_core import (
    DATASET_NAME,
    SCHEMA_VERSION,
    SOURCE_BOUND_ISSUANCE_TOKEN,
    ShadowDevigStatus,
    ShadowModelAgreementStatus,
    ShadowOpportunityEligibility,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowRouterDecisionStatus,
    _EVENT_RE,
    _finite,
    _odds,
    _probability,
    _require_sha,
    _sha256,
)


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
    source_bound_issuance: str
    odds_raw: Optional[str] = None
    observation_identity_sha256: Optional[str] = None
    registry_coverage_identity: Optional[str] = None
    bookable: bool = True

    def __post_init__(self) -> None:
        if type(self.fixture_identity) is not str or not self.fixture_identity.strip():
            raise ShadowPriceError("fixture_identity must be non-empty")
        if self.source_bound_issuance != SOURCE_BOUND_ISSUANCE_TOKEN:
            raise ShadowPriceError(
                "ShadowExactQuote must be issued by source-bound builder "
                "(inventory+PR-B observation join); direct caller construction is forbidden"
            )
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
            "source_bound_issuance": self.source_bound_issuance,
            "odds_raw": self.odds_raw,
            "observation_identity_sha256": self.observation_identity_sha256,
            "registry_coverage_identity": self.registry_coverage_identity,
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
    probability_input_namespace: Optional[str] = None
    prc_scan_sha256: Optional[str] = None
    sealed_prediction_sha256: Optional[str] = None
    history_prefix_identity: Optional[str] = None
    source_raw_sha256: Optional[str] = None
    source_manifest_sha256: Optional[str] = None
    source_inventory_sha256: Optional[str] = None
    observation_identity_sha256: Optional[str] = None
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
            "probability_input_namespace": self.probability_input_namespace,
            "prc_scan_sha256": self.prc_scan_sha256,
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "history_prefix_identity": self.history_prefix_identity,
            "source_raw_sha256": self.source_raw_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "observation_identity_sha256": self.observation_identity_sha256,
            "score_matrix_audit": (
                dict(self.score_matrix_audit) if self.score_matrix_audit is not None else None
            ),
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
