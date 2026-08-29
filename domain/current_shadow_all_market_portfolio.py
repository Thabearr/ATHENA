"""Research-only all-market Shadow Portfolio (PR E).

Consumes only source-replay-verifiable PR-D Price-all + Router outputs from the
current reconciliation lane.  The optimizer never reroutes a fixture, never
promotes a Router counterfactual, never pads a target, and never invents a
statistical dependence model.  Frozen Portfolio-v2 caps, survival and fragility
semantics remain the policy authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional, Sequence

from domain import current_shadow_all_market_price_all as price_all
from domain import current_shadow_all_market_router as router
from domain import sportybet_current_event_discovery_reconciliation as reconciliation
from domain._accumulator_optimizer_contracts import (
    EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION,
    JOINT_DEPENDENCE_STATUS,
    MAXIMUM_COMPETITION_SHARE,
    MAXIMUM_FRAGILE_SHARE,
    MAXIMUM_MARKET_FAMILY_SHARE,
    MAXIMUM_TARGET_SIZE,
    MAXIMUM_TEAM_APPEARANCES,
    MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2,
    MINIMUM_FRAGILE_CAP,
    MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE,
    MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE,
    AccumulatorOptimizationStatus,
    FragilityStatus,
    validate_accumulator_optimizer_contract,
)
from domain._current_shadow_price_core import (
    MAX_QUOTE_AGE_SECONDS,
    MINIMUM_LEAD_SECONDS,
    ShadowOpportunityEligibility,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowRouterDecisionStatus,
)
from domain._current_shadow_price_records import (
    ShadowExactQuote,
    ShadowMarketRouterDecision,
    ShadowPriceAllBundle,
    ShadowPriceResult,
    ShadowRoutedOpportunity,
)
from domain._current_shadow_quote_binding import (
    CURRENT_RECONCILIATION_DIRECT,
    build_current_shadow_exact_quotes,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-all-market-portfolio-v1"
STATUS = "RESEARCH_ONLY_CURRENT_SHADOW_ALL_MARKET_PORTFOLIO"
ROUTER_REPLAY_POLICY_ID = "REBUILD_EXACT_PRD_ROUTER_FROM_SOURCE_REPLAYED_PRICE_ALL_V1"
FIXTURE_EXPOSURE_POLICY_ID = "PRD_RETAINED_PR251_CURRENT_RECONCILIATION_EXPOSURE_IDENTITY_V1"
PORTFOLIO_FRESHNESS_POLICY_ID = "RECHECK_PRD_QUOTE_AGE_AND_KICKOFF_LEAD_AT_PORTFOLIO_TIME_V1"
JOINT_SELECTION_POLICY_ID = "DETERMINISTIC_MARGINAL_DIVERSIFICATION_WITH_HARD_CAPS_V1"
CORRELATION_POLICY_ID = "EXPOSURE_FLAGS_AND_CAPS_NO_FABRICATED_STATISTICAL_RHO_V1"
SURVIVAL_POLICY_ID = "WORST_MODEL_NON_NEGATIVE_SETTLEMENT_FLOOR_INDEPENDENCE_BASELINE_V1"
RESERVE_POLICY_ID = "PRESERVE_ROUTER_QUALIFIED_UNSELECTED_LEGS_WITH_REASONS_V1"
SHORTFALL_POLICY_ID = "REQUESTED_SIZE_IS_TARGET_NOT_REQUIREMENT_NEVER_PAD_V1"
FRAGILITY_POLICY_ID = "THIN_VALUE_OR_THIN_SURVIVAL_OPERATIONAL_FLAG_V1"
NEXT_BOUNDARY = "CURRENT_SHADOW_ALL_MARKET_RUNNER_AND_ANONYMOUS_CREATE_RELOAD_VERIFICATION"

AUTHORITY = MappingProxyType({
    "research_shadow_router_consumption": True,
    "research_shadow_portfolio": True,
    "research_shadow_shortfall": True,
    "research_shadow_reserve_recording": True,
    "research_shadow_current_runner": False,
    "research_anonymous_share_code_generation": False,
    "provider_create_reload_verification": False,
    "production_model": False,
    "production_probability": False,
    "phase6": False,
    "production_price_all": False,
    "production_market_router": False,
    "production_portfolio": False,
    "production_selection": False,
    "production_sportybet_execution": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})

_DNB_STATES = frozenset({"WIN", "PUSH", "LOSS"})
_AH_STATES = frozenset({"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"})


class CurrentShadowPortfolioError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowPortfolioError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentShadowPortfolioError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowPortfolioError(f"{label} is invalid") from exc


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurrentShadowPortfolioError(f"{label} must be finite probability")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise CurrentShadowPortfolioError(f"{label} must be in [0,1]")
    return result


def _validate_frozen_policy() -> str:
    identity = validate_accumulator_optimizer_contract()
    expected = EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION[1]
    if identity["accumulator_optimizer_contract_sha256"] != expected:
        raise CurrentShadowPortfolioError("frozen Portfolio-v2 contract identity drifted")
    if (
        MAXIMUM_TARGET_SIZE != 50
        or MAXIMUM_TEAM_APPEARANCES != 1
        or MAXIMUM_COMPETITION_SHARE != 0.40
        or MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2 != 2
        or MAXIMUM_MARKET_FAMILY_SHARE != 0.50
        or MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2 != 2
        or MAXIMUM_FRAGILE_SHARE != 0.30
        or MINIMUM_FRAGILE_CAP != 1
        or MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE != 0.02
        or MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE != 0.60
        or JOINT_DEPENDENCE_STATUS != "NO_VALIDATED_JOINT_CORRELATION_MODEL_V1"
    ):
        raise CurrentShadowPortfolioError("frozen Portfolio-v2 policy values drifted")
    return expected


@dataclass(frozen=True, init=False)
class ShadowPortfolioRouterInput:
    price_all_bundle: ShadowPriceAllBundle
    router_decision: ShadowMarketRouterDecision
    price_all_bundle_sha256: str
    router_decision_sha256: str
    fixture_identity: str
    provider_event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime
    source_observed_at: datetime
    fixture_reconciliation_sha256: str
    source_raw_sha256: str
    source_manifest_sha256: str
    source_inventory_sha256: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentShadowPortfolioError(
            "ShadowPortfolioRouterInput is builder-only; use build_shadow_portfolio_router_input()"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "price_all_bundle_sha256": self.price_all_bundle_sha256,
            "router_decision_sha256": self.router_decision_sha256,
            "fixture_identity": self.fixture_identity,
            "provider_event_id": self.provider_event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": _iso(self.kickoff_utc),
            "source_observed_at": _iso(self.source_observed_at),
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
        }


def build_shadow_portfolio_router_input(
    *,
    price_all_bundle: ShadowPriceAllBundle,
    router_decision: ShadowMarketRouterDecision,
) -> ShadowPortfolioRouterInput:
    if type(price_all_bundle) is not ShadowPriceAllBundle:
        raise CurrentShadowPortfolioError("price_all_bundle must be exact ShadowPriceAllBundle")
    if type(router_decision) is not ShadowMarketRouterDecision:
        raise CurrentShadowPortfolioError("router_decision must be exact ShadowMarketRouterDecision")
    try:
        checked_bundle = price_all.verify_shadow_price_all_bundle(price_all_bundle)
        rebuilt_decision = router.route_shadow_price_results(checked_bundle)
    except ShadowPriceError as exc:
        raise CurrentShadowPortfolioError("PR-D exact source/Router reconstruction failed") from exc
    if _canonical(rebuilt_decision.to_dict()) != _canonical(router_decision.to_dict()):
        raise CurrentShadowPortfolioError("Router decision differs from exact PR-D reconstruction")
    if rebuilt_decision.price_all_bundle_sha256 != checked_bundle.canonical_sha256:
        raise CurrentShadowPortfolioError("Router/Price-all SHA identity mismatch")

    context = checked_bundle._context
    if context.source_context_mode != CURRENT_RECONCILIATION_DIRECT:
        raise CurrentShadowPortfolioError(
            "PR-E current Portfolio requires direct current-reconciliation PR-D context"
        )
    if context._current_reconciliation_bundle is None:
        raise CurrentShadowPortfolioError("PR-D context omitted retained current reconciliation")
    try:
        reconciled = reconciliation.verify_current_event_discovery_reconciliation_bundle(
            context._current_reconciliation_bundle
        )
    except reconciliation.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowPortfolioError("current reconciliation source replay failed") from exc
    if reconciled.canonical_sha256 != context.fixture_reconciliation_sha256:
        raise CurrentShadowPortfolioError("retained reconciliation SHA differs from PR-D context")
    rows = [
        row for row in reconciled.rows
        if row.event_id == context.provider_event_id
    ]
    if len(rows) != 1 or rows[0].fixture_reconciliation_authorized is not True:
        raise CurrentShadowPortfolioError("Portfolio fixture/event exposure is not uniquely source-authorized")
    row = rows[0]
    if row.matched_fotmob_fixture_id is None:
        raise CurrentShadowPortfolioError("Portfolio exposure omitted matched FotMob fixture identity")
    source_fixture_identity = f"FOTMOB:{row.matched_fotmob_fixture_id}"
    if source_fixture_identity != context.fixture_identity:
        raise CurrentShadowPortfolioError(
            "Portfolio fixture identity differs from source-reconciled FotMob identity"
        )
    if row.competition_name is None:
        raise CurrentShadowPortfolioError("Portfolio exposure requires source-proven competition")
    inventory = context.provider_inventory
    if (
        row.home_team_name != inventory.home_team_name
        or row.away_team_name != inventory.away_team_name
        or row.kickoff_utc != inventory.kickoff_utc
        or row.direct_event_observed_at != inventory.observed_at
        or row.direct_event_raw_sha256 != inventory.source_raw_sha256
        or row.direct_event_manifest_sha256 != inventory.source_manifest_sha256
        or row.direct_event_inventory_sha256 != inventory.canonical_sha256
    ):
        raise CurrentShadowPortfolioError("Portfolio exposure differs from retained exact provider evidence")

    value = object.__new__(ShadowPortfolioRouterInput)
    for name, item in {
        "price_all_bundle": checked_bundle,
        "router_decision": rebuilt_decision,
        "price_all_bundle_sha256": checked_bundle.canonical_sha256,
        "router_decision_sha256": rebuilt_decision.decision_sha256,
        "fixture_identity": context.fixture_identity,
        "provider_event_id": context.provider_event_id,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "competition": row.competition_name,
        "kickoff_utc": row.kickoff_utc,
        "source_observed_at": inventory.observed_at,
        "fixture_reconciliation_sha256": reconciled.canonical_sha256,
        "source_raw_sha256": inventory.source_raw_sha256,
        "source_manifest_sha256": inventory.source_manifest_sha256,
        "source_inventory_sha256": inventory.canonical_sha256,
    }.items():
        object.__setattr__(value, name, item)
    return value


def verify_shadow_portfolio_router_input(value: Any) -> ShadowPortfolioRouterInput:
    if type(value) is not ShadowPortfolioRouterInput:
        raise CurrentShadowPortfolioError("value must be exact ShadowPortfolioRouterInput")
    rebuilt = build_shadow_portfolio_router_input(
        price_all_bundle=value.price_all_bundle,
        router_decision=value.router_decision,
    )
    if _canonical(rebuilt.to_dict()) != _canonical(value.to_dict()):
        raise CurrentShadowPortfolioError("Portfolio Router input differs on source replay")
    return rebuilt


@dataclass(frozen=True)
class ShadowPortfolioLeg:
    leg_id: str
    price_all_bundle_sha256: str
    router_decision_sha256: str
    selected_opportunity_id: str
    fixture_identity: str
    provider_event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime
    market_id: MarketId
    outcome_id: OutcomeId
    line: Optional[float]
    market_family: MarketFamily
    quote_identity_sha256: str
    provider_market_id: str
    provider_market_name: str
    provider_specifier: Optional[str]
    provider_outcome_id: str
    provider_outcome_name: str
    decimal_odds: float
    source_raw_sha256: str
    source_manifest_sha256: str
    source_inventory_sha256: str
    provider_registry_sha256: str
    provider_observation_sha256: str
    fixture_reconciliation_sha256: str
    robust_net_expected_value: float
    robust_edge: Optional[float]
    event_probability_floor: Optional[float]
    survival_probability_floor: float
    router_quote_age_seconds: float
    portfolio_quote_age_seconds: float
    portfolio_kickoff_lead_seconds: float
    fragility_status: FragilityStatus

    @property
    def fragile(self) -> bool:
        return self.fragility_status is not FragilityStatus.NON_FRAGILE

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg_id": self.leg_id,
            "price_all_bundle_sha256": self.price_all_bundle_sha256,
            "router_decision_sha256": self.router_decision_sha256,
            "selected_opportunity_id": self.selected_opportunity_id,
            "fixture_identity": self.fixture_identity,
            "provider_event_id": self.provider_event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": _iso(self.kickoff_utc),
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "market_family": self.market_family.value,
            "quote_identity_sha256": self.quote_identity_sha256,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "decimal_odds": self.decimal_odds,
            "source_raw_sha256": self.source_raw_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "provider_registry_sha256": self.provider_registry_sha256,
            "provider_observation_sha256": self.provider_observation_sha256,
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "robust_net_expected_value": self.robust_net_expected_value,
            "robust_edge": self.robust_edge,
            "event_probability_floor": self.event_probability_floor,
            "survival_probability_floor": self.survival_probability_floor,
            "router_quote_age_seconds": self.router_quote_age_seconds,
            "portfolio_quote_age_seconds": self.portfolio_quote_age_seconds,
            "portfolio_kickoff_lead_seconds": self.portfolio_kickoff_lead_seconds,
            "fragility_status": self.fragility_status.value,
            "fragile": self.fragile,
        }


@dataclass(frozen=True)
class ShadowPortfolioReserveLeg:
    leg: ShadowPortfolioLeg
    reserve_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"leg": self.leg.to_dict(), "reserve_reasons": list(self.reserve_reasons)}


@dataclass(frozen=True)
class ShadowPortfolioRouteAudit:
    fixture_identity: str
    provider_event_id: str
    router_decision_sha256: str
    router_status: str
    selected_opportunity_id: Optional[str]
    portfolio_source_age_seconds: float
    portfolio_kickoff_lead_seconds: float
    portfolio_admitted: bool
    admission_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identity": self.fixture_identity,
            "provider_event_id": self.provider_event_id,
            "router_decision_sha256": self.router_decision_sha256,
            "router_status": self.router_status,
            "selected_opportunity_id": self.selected_opportunity_id,
            "portfolio_source_age_seconds": self.portfolio_source_age_seconds,
            "portfolio_kickoff_lead_seconds": self.portfolio_kickoff_lead_seconds,
            "portfolio_admitted": self.portfolio_admitted,
            "admission_reasons": list(self.admission_reasons),
        }


@dataclass(frozen=True, init=False)
class ShadowPortfolioOptimization:
    evaluation_time: datetime
    requested_target_size: int
    selected_legs: tuple[ShadowPortfolioLeg, ...]
    reserve_legs: tuple[ShadowPortfolioReserveLeg, ...]
    route_audits: tuple[ShadowPortfolioRouteAudit, ...]
    optimization_status: AccumulatorOptimizationStatus
    shortfall: int
    expected_slip_survival: Optional[float]
    combined_decimal_odds_product: Optional[float]
    exposure_summary: Mapping[str, Any]
    authority: Mapping[str, bool]
    frozen_portfolio_v2_contract_sha256: str
    _router_inputs: tuple[ShadowPortfolioRouterInput, ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentShadowPortfolioError("ShadowPortfolioOptimization is builder-only")

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "evaluation_time": _iso(self.evaluation_time),
            "requested_target_size": self.requested_target_size,
            "selected_leg_count": len(self.selected_legs),
            "selected_legs": [item.to_dict() for item in self.selected_legs],
            "reserve_legs": [item.to_dict() for item in self.reserve_legs],
            "route_audits": [item.to_dict() for item in self.route_audits],
            "optimization_status": self.optimization_status.value,
            "shortfall": self.shortfall,
            "fulfilled": self.fulfilled,
            "expected_slip_survival": self.expected_slip_survival,
            "expected_slip_survival_method": (
                "CONSERVATIVE_WORST_MODEL_NON_NEGATIVE_SETTLEMENT_INDEPENDENCE_BASELINE;"
                "NOT_A_CORRELATION_ADJUSTED_JOINT_PROBABILITY"
            ),
            "combined_decimal_odds_product": self.combined_decimal_odds_product,
            "exposure_summary": dict(self.exposure_summary),
            "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
            "statistical_correlation_coefficients": None,
            "router_replay_policy_id": ROUTER_REPLAY_POLICY_ID,
            "fixture_exposure_policy_id": FIXTURE_EXPOSURE_POLICY_ID,
            "portfolio_freshness_policy_id": PORTFOLIO_FRESHNESS_POLICY_ID,
            "joint_selection_policy_id": JOINT_SELECTION_POLICY_ID,
            "correlation_policy_id": CORRELATION_POLICY_ID,
            "survival_policy_id": SURVIVAL_POLICY_ID,
            "reserve_policy_id": RESERVE_POLICY_ID,
            "shortfall_policy_id": SHORTFALL_POLICY_ID,
            "fragility_policy_id": FRAGILITY_POLICY_ID,
            "frozen_portfolio_v2_contract_sha256": self.frozen_portfolio_v2_contract_sha256,
            "authority": dict(self.authority),
            "next_boundary": NEXT_BOUNDARY,
            "wager_placed": False,
        }


def _selected_opportunity(
    value: ShadowPortfolioRouterInput,
) -> tuple[ShadowRoutedOpportunity, ShadowPriceResult, ShadowExactQuote]:
    decision = value.router_decision
    if decision.status is not ShadowRouterDecisionStatus.SELECTED or decision.selected_opportunity_id is None:
        raise CurrentShadowPortfolioError("only Router SELECTED decisions can become Portfolio legs")
    rows = [row for row in decision.opportunities if row.opportunity_id == decision.selected_opportunity_id]
    if len(rows) != 1:
        raise CurrentShadowPortfolioError("selected Router opportunity identity is not unique")
    opportunity = rows[0]
    if opportunity.eligibility is not ShadowOpportunityEligibility.ELIGIBLE:
        raise CurrentShadowPortfolioError("Router selected opportunity is not eligible")
    result = opportunity.price_result
    if result.disposition is not ShadowPriceDisposition.PRICED or result.quote_identity_sha256 is None:
        raise CurrentShadowPortfolioError("Router selected opportunity lacks exact priced quote")
    quotes = build_current_shadow_exact_quotes(value.price_all_bundle._context)
    matched = [quote for quote in quotes if quote.identity_sha256 == result.quote_identity_sha256]
    if len(matched) != 1:
        raise CurrentShadowPortfolioError("selected price result does not bind one exact current quote")
    quote = matched[0]
    if (
        quote.fixture_identity != value.fixture_identity
        or quote.provider_event_id != value.provider_event_id
        or quote.market_id is not result.market_id
        or quote.outcome_id is not result.outcome_id
        or quote.line != result.line
        or quote.source_raw_sha256 != result.source_raw_sha256
        or quote.source_manifest_sha256 != result.source_manifest_sha256
        or quote.source_inventory_sha256 != result.source_inventory_sha256
        or quote.provider_registry_sha256 != result.provider_registry_sha256
        or quote.provider_observation_sha256 != result.provider_observation_sha256
    ):
        raise CurrentShadowPortfolioError("selected quote identity differs from retained PR-D result")
    return opportunity, result, quote


def _survival(opportunity: ShadowRoutedOpportunity, result: ShadowPriceResult) -> float:
    if result.market_id not in {MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP}:
        if opportunity.event_probability_floor is None:
            raise CurrentShadowPortfolioError("selected scalar opportunity lacks event probability floor")
        return _probability(opportunity.event_probability_floor, "event_probability_floor")
    probabilities = dict(result.settlement_state_probabilities)
    keys = frozenset(probabilities)
    if result.market_id is MarketId.DRAW_NO_BET:
        if keys != _DNB_STATES:
            raise CurrentShadowPortfolioError("DNB settlement components drifted")
        survival = probabilities["WIN"] + probabilities["PUSH"]
    else:
        if keys != _AH_STATES:
            raise CurrentShadowPortfolioError("Asian Handicap settlement components drifted")
        survival = probabilities["WIN"] + probabilities["HALF_WIN"] + probabilities["PUSH"]
    return _probability(survival, "settlement survival probability")


def _fragility(robust_ev: float, survival: float) -> FragilityStatus:
    thin_value = robust_ev < MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE
    thin_survival = survival < MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE
    if thin_value and thin_survival:
        return FragilityStatus.FRAGILE_THIN_VALUE_AND_SURVIVAL
    if thin_value:
        return FragilityStatus.FRAGILE_THIN_VALUE
    if thin_survival:
        return FragilityStatus.FRAGILE_THIN_SURVIVAL
    return FragilityStatus.NON_FRAGILE


def _build_leg(value: ShadowPortfolioRouterInput, *, now: datetime) -> ShadowPortfolioLeg:
    opportunity, result, quote = _selected_opportunity(value)
    robust_ev = opportunity.robust_net_expected_value
    if robust_ev is None or not math.isfinite(robust_ev) or robust_ev <= 0.0:
        raise CurrentShadowPortfolioError("selected Router opportunity lacks positive robust EV")
    router_age = (value.price_all_bundle.evaluation_time - quote.observed_at).total_seconds()
    portfolio_age = (now - quote.observed_at).total_seconds()
    lead = (value.kickoff_utc - now).total_seconds()
    if not all(math.isfinite(item) for item in (router_age, portfolio_age, lead)):
        raise CurrentShadowPortfolioError("Portfolio freshness values are non-finite")
    if router_age < 0 or portfolio_age < 0:
        raise CurrentShadowPortfolioError("selected current quote is future-dated")
    if portfolio_age + 1e-9 < router_age:
        raise CurrentShadowPortfolioError("Portfolio quote age cannot be younger than Price-all quote age")
    survival = _survival(opportunity, result)
    family = MARKET_REGISTRY[result.market_id].family
    leg_id = _sha({
        "router_decision_sha256": value.router_decision_sha256,
        "selected_opportunity_id": opportunity.opportunity_id,
        "quote_identity_sha256": quote.identity_sha256,
        "fixture_reconciliation_sha256": value.fixture_reconciliation_sha256,
    })
    return ShadowPortfolioLeg(
        leg_id=leg_id,
        price_all_bundle_sha256=value.price_all_bundle_sha256,
        router_decision_sha256=value.router_decision_sha256,
        selected_opportunity_id=opportunity.opportunity_id,
        fixture_identity=value.fixture_identity,
        provider_event_id=value.provider_event_id,
        home_team=value.home_team,
        away_team=value.away_team,
        competition=value.competition,
        kickoff_utc=value.kickoff_utc,
        market_id=result.market_id,
        outcome_id=result.outcome_id,
        line=result.line,
        market_family=family,
        quote_identity_sha256=quote.identity_sha256,
        provider_market_id=quote.provider_market_id,
        provider_market_name=quote.provider_market_name,
        provider_specifier=quote.provider_specifier,
        provider_outcome_id=quote.provider_outcome_id,
        provider_outcome_name=quote.provider_outcome_name,
        decimal_odds=quote.decimal_odds,
        source_raw_sha256=quote.source_raw_sha256,
        source_manifest_sha256=quote.source_manifest_sha256,
        source_inventory_sha256=quote.source_inventory_sha256,
        provider_registry_sha256=quote.provider_registry_sha256,
        provider_observation_sha256=quote.provider_observation_sha256,
        fixture_reconciliation_sha256=quote.fixture_reconciliation_sha256,
        robust_net_expected_value=float(robust_ev),
        robust_edge=opportunity.robust_edge,
        event_probability_floor=opportunity.event_probability_floor,
        survival_probability_floor=survival,
        router_quote_age_seconds=float(router_age),
        portfolio_quote_age_seconds=float(portfolio_age),
        portfolio_kickoff_lead_seconds=float(lead),
        fragility_status=_fragility(float(robust_ev), survival),
    )


def _target_cap(target: int, share: float, minimum_when_multi: int) -> int:
    if target == 1:
        return 1
    return min(target, max(minimum_when_multi, int(math.ceil(target * share))))


def _caps(target: int) -> dict[str, int]:
    return {
        "team": MAXIMUM_TEAM_APPEARANCES,
        "competition": _target_cap(target, MAXIMUM_COMPETITION_SHARE, MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2),
        "market_family": _target_cap(target, MAXIMUM_MARKET_FAMILY_SHARE, MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2),
        "fragile": min(target, max(MINIMUM_FRAGILE_CAP, int(math.ceil(target * MAXIMUM_FRAGILE_SHARE)))),
    }


def _counts(selected: Sequence[ShadowPortfolioLeg]) -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
    team: dict[str, int] = {}
    competition: dict[str, int] = {}
    family: dict[str, int] = {}
    fragile = 0
    for leg in selected:
        for team_name in (leg.home_team, leg.away_team):
            team[team_name] = team.get(team_name, 0) + 1
        competition[leg.competition] = competition.get(leg.competition, 0) + 1
        family[leg.market_family.value] = family.get(leg.market_family.value, 0) + 1
        fragile += int(leg.fragile)
    return team, competition, family, fragile


def _constraint_reasons(candidate: ShadowPortfolioLeg, selected: Sequence[ShadowPortfolioLeg], caps: Mapping[str, int]) -> tuple[str, ...]:
    team, competition, family, fragile = _counts(selected)
    reasons: list[str] = []
    for name in (candidate.home_team, candidate.away_team):
        if team.get(name, 0) >= caps["team"]:
            reasons.append(f"TEAM_CAP:{name}")
    if competition.get(candidate.competition, 0) >= caps["competition"]:
        reasons.append(f"COMPETITION_CAP:{candidate.competition}")
    if family.get(candidate.market_family.value, 0) >= caps["market_family"]:
        reasons.append(f"MARKET_FAMILY_CAP:{candidate.market_family.value}")
    if candidate.fragile and fragile >= caps["fragile"]:
        reasons.append("FRAGILITY_CAP")
    return tuple(sorted(set(reasons)))


def _marginal_key(candidate: ShadowPortfolioLeg, selected: Sequence[ShadowPortfolioLeg], caps: Mapping[str, int]) -> tuple[Any, ...]:
    _team, competition, family, fragile = _counts(selected)
    penalty = (
        competition.get(candidate.competition, 0) / caps["competition"]
        + family.get(candidate.market_family.value, 0) / caps["market_family"]
        + ((fragile / caps["fragile"]) if candidate.fragile else 0.0)
    )
    edge_present = candidate.robust_edge is not None
    return (
        penalty,
        -candidate.survival_probability_floor,
        -candidate.robust_net_expected_value,
        0 if edge_present else 1,
        -(candidate.robust_edge if candidate.robust_edge is not None else 0.0),
        candidate.portfolio_quote_age_seconds,
        candidate.leg_id,
    )


def _reserve_key(candidate: ShadowPortfolioLeg) -> tuple[Any, ...]:
    edge_present = candidate.robust_edge is not None
    return (
        -candidate.survival_probability_floor,
        -candidate.robust_net_expected_value,
        0 if edge_present else 1,
        -(candidate.robust_edge if candidate.robust_edge is not None else 0.0),
        candidate.portfolio_quote_age_seconds,
        candidate.leg_id,
    )


def _exposure_summary(selected: Sequence[ShadowPortfolioLeg], caps: Mapping[str, int]) -> Mapping[str, Any]:
    team, competition, family, fragile = _counts(selected)
    return MappingProxyType({
        "caps": dict(caps),
        "team_counts": dict(sorted(team.items())),
        "competition_counts": dict(sorted(competition.items())),
        "market_family_counts": dict(sorted(family.items())),
        "fragile_count": fragile,
        "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
        "statistical_correlation_coefficients": None,
    })


def _survival_product(selected: Sequence[ShadowPortfolioLeg]) -> Optional[float]:
    if not selected:
        return None
    result = math.prod(leg.survival_probability_floor for leg in selected)
    if not math.isfinite(result):
        raise CurrentShadowPortfolioError("independence survival baseline is non-finite")
    return result


def _odds_product(selected: Sequence[ShadowPortfolioLeg]) -> Optional[float]:
    if not selected:
        return None
    value = Decimal("1")
    for leg in selected:
        value *= Decimal(str(leg.decimal_odds))
    result = float(value)
    return result if math.isfinite(result) else None


def optimize_shadow_portfolio(
    router_inputs: Iterable[ShadowPortfolioRouterInput],
    *,
    target_size: int,
    evaluation_time: datetime,
) -> ShadowPortfolioOptimization:
    frozen_contract = _validate_frozen_policy()
    now = _utc(evaluation_time, "evaluation_time")
    if isinstance(target_size, bool) or not isinstance(target_size, int):
        raise TypeError("target_size must be an integer")
    if not 1 <= target_size <= MAXIMUM_TARGET_SIZE:
        raise ValueError(f"target_size must be between 1 and {MAXIMUM_TARGET_SIZE}")
    supplied = tuple(router_inputs)
    if any(type(item) is not ShadowPortfolioRouterInput for item in supplied):
        raise CurrentShadowPortfolioError("router_inputs must contain exact ShadowPortfolioRouterInput values")
    verified = tuple(verify_shadow_portfolio_router_input(item) for item in supplied)
    fixture_ids = [item.fixture_identity for item in verified]
    event_ids = [item.provider_event_id for item in verified]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise CurrentShadowPortfolioError("duplicate fixture inputs are not allowed")
    if len(event_ids) != len(set(event_ids)):
        raise CurrentShadowPortfolioError("duplicate provider event inputs are not allowed")

    admitted: list[ShadowPortfolioLeg] = []
    blocked: list[ShadowPortfolioReserveLeg] = []
    audits: list[ShadowPortfolioRouteAudit] = []
    for source in sorted(verified, key=lambda item: item.fixture_identity):
        if source.price_all_bundle.evaluation_time > now:
            raise CurrentShadowPortfolioError("portfolio evaluation_time predates Price-all evaluation")
        source_age = (now - source.source_observed_at).total_seconds()
        kickoff_lead = (source.kickoff_utc - now).total_seconds()
        if not math.isfinite(source_age) or source_age < 0:
            raise CurrentShadowPortfolioError("current source observation is future-dated at Portfolio time")
        if not math.isfinite(kickoff_lead):
            raise CurrentShadowPortfolioError("Portfolio kickoff lead is non-finite")
        reasons: list[str] = []
        leg: Optional[ShadowPortfolioLeg] = None
        if source.router_decision.status is ShadowRouterDecisionStatus.SELECTED:
            leg = _build_leg(source, now=now)
            if leg.portfolio_quote_age_seconds > MAX_QUOTE_AGE_SECONDS:
                reasons.append("PORTFOLIO_TIME_STALE")
            if leg.portfolio_kickoff_lead_seconds <= MINIMUM_LEAD_SECONDS:
                reasons.append("TOO_CLOSE_TO_KICKOFF")
            if reasons:
                blocked.append(ShadowPortfolioReserveLeg(leg, tuple(sorted(set(reasons)))))
                leg = None
            else:
                admitted.append(leg)
        else:
            reasons.append("ROUTER_NO_BET")
        audits.append(ShadowPortfolioRouteAudit(
            fixture_identity=source.fixture_identity,
            provider_event_id=source.provider_event_id,
            router_decision_sha256=source.router_decision_sha256,
            router_status=source.router_decision.status.value,
            selected_opportunity_id=source.router_decision.selected_opportunity_id,
            portfolio_source_age_seconds=float(source_age),
            portfolio_kickoff_lead_seconds=float(kickoff_lead),
            portfolio_admitted=leg is not None,
            admission_reasons=tuple(sorted(set(reasons))),
        ))

    caps = _caps(target_size)
    remaining = sorted(admitted, key=lambda item: item.leg_id)
    selected: list[ShadowPortfolioLeg] = []
    while remaining and len(selected) < target_size:
        admissible = [leg for leg in remaining if not _constraint_reasons(leg, selected, caps)]
        if not admissible:
            break
        chosen = min(admissible, key=lambda leg: _marginal_key(leg, selected, caps))
        selected.append(chosen)
        remaining = [leg for leg in remaining if leg.leg_id != chosen.leg_id]

    selected = sorted(selected, key=lambda item: item.leg_id)
    selected_ids = {item.leg_id for item in selected}
    reserves: list[ShadowPortfolioReserveLeg] = list(blocked)
    for leg in sorted((item for item in admitted if item.leg_id not in selected_ids), key=_reserve_key):
        reasons = list(_constraint_reasons(leg, selected, caps))
        if len(selected) >= target_size:
            reasons.append("TARGET_ALREADY_FILLED")
        if not reasons:
            reasons.append("LOWER_MARGINAL_PORTFOLIO_PRIORITY")
        reserves.append(ShadowPortfolioReserveLeg(leg, tuple(sorted(set(reasons)))))
    reserves.sort(key=lambda item: (_reserve_key(item.leg), item.reserve_reasons))

    shortfall = max(0, target_size - len(selected))
    optimization_status = (
        AccumulatorOptimizationStatus.QUALIFIED_SET
        if selected
        else AccumulatorOptimizationStatus.NO_QUALIFIED_LEGS
    )
    value = object.__new__(ShadowPortfolioOptimization)
    for name, item in {
        "evaluation_time": now,
        "requested_target_size": target_size,
        "selected_legs": tuple(selected),
        "reserve_legs": tuple(reserves),
        "route_audits": tuple(sorted(audits, key=lambda row: row.fixture_identity)),
        "optimization_status": optimization_status,
        "shortfall": shortfall,
        "expected_slip_survival": _survival_product(selected),
        "combined_decimal_odds_product": _odds_product(selected),
        "exposure_summary": _exposure_summary(selected, caps),
        "authority": MappingProxyType(dict(AUTHORITY)),
        "frozen_portfolio_v2_contract_sha256": frozen_contract,
        "_router_inputs": verified,
    }.items():
        object.__setattr__(value, name, item)
    return value


def verify_shadow_portfolio_optimization(value: Any) -> ShadowPortfolioOptimization:
    if type(value) is not ShadowPortfolioOptimization:
        raise CurrentShadowPortfolioError("value must be exact ShadowPortfolioOptimization")
    rebuilt = optimize_shadow_portfolio(
        value._router_inputs,
        target_size=value.requested_target_size,
        evaluation_time=value.evaluation_time,
    )
    if _canonical(rebuilt.to_dict()) != _canonical(value.to_dict()):
        raise CurrentShadowPortfolioError("Shadow Portfolio differs on exact source reconstruction")
    return rebuilt


__all__ = [
    "AUTHORITY",
    "CurrentShadowPortfolioError",
    "DATASET_NAME",
    "ShadowPortfolioLeg",
    "ShadowPortfolioOptimization",
    "ShadowPortfolioReserveLeg",
    "ShadowPortfolioRouterInput",
    "STATUS",
    "build_shadow_portfolio_router_input",
    "optimize_shadow_portfolio",
    "verify_shadow_portfolio_optimization",
    "verify_shadow_portfolio_router_input",
]
