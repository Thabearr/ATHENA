"""Portfolio Optimizer v3 over exact current-provider Router v3 decisions."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import types
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from domain import market_router_v3_current_provider as router_v3
from domain import portfolio_optimizer_v2_direct_provider as frozen_v2
from domain import sportybet_current_event_discovery_reconciliation as current_recon
from domain._accumulator_optimizer_contracts import (
    JOINT_DEPENDENCE_STATUS,
    RESERVE_POLICY_ID,
    SHORTFALL_POLICY_ID,
)
from domain._market_router_contracts import OpportunityEligibility, RouterDecisionStatus
from domain._portfolio_optimizer_v2_direct_provider_contracts import (
    EXPECTED_CONTRACT_SHA256 as PORTFOLIO_V2_CONTRACT_SHA256,
    FragilityStatus,
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
    PortfolioOptimizationStatus,
    validate_portfolio_optimizer_v2_contract,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-portfolio-optimizer-v3-current-provider-v1"
STATUS_AS_OF = "PORTFOLIO_OPTIMIZER_V3_CURRENT_PROVIDER_AS_OF_VERIFIED"
STATUS_LIVE = "PORTFOLIO_OPTIMIZER_V3_CURRENT_PROVIDER_LIVE_VERIFIED"
MARKET_ROUTER_V3_CONTRACT_SHA256 = router_v3.EXPECTED_CONTRACT_SHA256
CURRENT_RECONCILIATION_CONTRACT_SHA256 = current_recon.EXPECTED_CONTRACT_SHA256
SOURCE_REPLAY_POLICY_ID = "REPLAY_ROUTER_V3_AND_RETAINED_PR251_CURRENT_RECONCILIATION_V1"
EXPOSURE_POLICY_ID = "EXACT_PR251_HOME_AWAY_COMPETITION_CURRENT_EXPOSURE_V1"
OPTIMIZATION_POLICY_ID = "PRESERVE_FROZEN_PORTFOLIO_V2_CAPS_MARGINAL_ORDER_AND_SHORTFALL_V1"
NEXT_BOUNDARY = "CURRENT_SELECTED_LEG_SOURCE_REPLAY_AND_SPORTYBET_EXECUTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "4dc8be4e0a9f607b6c0804048bb326c0aa342d37fe540abbcd3e1b3a5f6a6dad"

AUTHORITY = types.MappingProxyType(
    {
        "current_provider_router_consumption": True,
        "router_decision_reconstruction": True,
        "current_reconciliation_source_replay": True,
        "portfolio_time_freshness_recheck": True,
        "portfolio_optimization": True,
        "qualified_leg_set": True,
        "reserve_leg_recording": True,
        "final_cross_fixture_selection": True,
        "football_probability_generation": False,
        "calibration": False,
        "value_record_computation": False,
        "market_routing": False,
        "statistical_joint_dependence_model": False,
        "accumulator_slip_construction": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)

_FULL_SETTLEMENT = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})
_DNB_COMPONENTS = frozen_v2._DNB_COMPONENTS
_AH_COMPONENTS = frozen_v2._AH_COMPONENTS


class PortfolioOptimizerV3CurrentProviderError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise PortfolioOptimizerV3CurrentProviderError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PortfolioOptimizerV3CurrentProviderError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _finite_probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortfolioOptimizerV3CurrentProviderError(
            f"{label} must be a finite probability"
        )
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise PortfolioOptimizerV3CurrentProviderError(
            f"{label} must be within [0,1]"
        )
    return result


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "dataset_name": DATASET_NAME,
        "market_router_v3_contract_sha256": MARKET_ROUTER_V3_CONTRACT_SHA256,
        "portfolio_v2_policy_contract_sha256": PORTFOLIO_V2_CONTRACT_SHA256,
        "current_reconciliation_contract_sha256": CURRENT_RECONCILIATION_CONTRACT_SHA256,
        "source_replay_policy_id": SOURCE_REPLAY_POLICY_ID,
        "exposure_policy_id": EXPOSURE_POLICY_ID,
        "optimization_policy_id": OPTIMIZATION_POLICY_ID,
        "maximum_target_size": MAXIMUM_TARGET_SIZE,
        "caps": {
            "team": MAXIMUM_TEAM_APPEARANCES,
            "competition_share": MAXIMUM_COMPETITION_SHARE,
            "market_family_share": MAXIMUM_MARKET_FAMILY_SHARE,
            "fragile_share": MAXIMUM_FRAGILE_SHARE,
        },
        "reserve_policy_id": RESERVE_POLICY_ID,
        "shortfall_policy_id": SHORTFALL_POLICY_ID,
        "authority": dict(AUTHORITY),
        "next_boundary": NEXT_BOUNDARY,
    }


def calculate_portfolio_optimizer_v3_contract_sha256() -> str:
    return _sha(_contract_payload())


def validate_portfolio_optimizer_v3_contract() -> Mapping[str, str]:
    try:
        router = router_v3.validate_market_router_v3_contract()
        portfolio = validate_portfolio_optimizer_v2_contract()
        reconciliation = current_recon.validate_current_event_discovery_contract()
    except Exception as exc:
        raise PortfolioOptimizerV3CurrentProviderError("Portfolio v3 dependency validation failed") from exc
    if router["market_router_v3_contract_sha256"] != MARKET_ROUTER_V3_CONTRACT_SHA256:
        raise PortfolioOptimizerV3CurrentProviderError("Router v3 identity drifted")
    if portfolio["portfolio_optimizer_v2_contract_sha256"] != PORTFOLIO_V2_CONTRACT_SHA256:
        raise PortfolioOptimizerV3CurrentProviderError("Portfolio v2 policy identity drifted")
    if reconciliation["current_event_discovery_contract_sha256"] != CURRENT_RECONCILIATION_CONTRACT_SHA256:
        raise PortfolioOptimizerV3CurrentProviderError("current reconciliation identity drifted")
    actual = calculate_portfolio_optimizer_v3_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise PortfolioOptimizerV3CurrentProviderError("Portfolio v3 contract drifted")
    return types.MappingProxyType({
        "portfolio_optimizer_v3_contract_sha256": actual,
        "market_router_v3_contract_sha256": MARKET_ROUTER_V3_CONTRACT_SHA256,
        "portfolio_v2_policy_contract_sha256": PORTFOLIO_V2_CONTRACT_SHA256,
        "current_reconciliation_contract_sha256": CURRENT_RECONCILIATION_CONTRACT_SHA256,
    })


@dataclasses.dataclass(frozen=True, init=False)
class CurrentProviderPortfolioRouterInput:
    router_decision: router_v3.MarketRouterV3CurrentProviderDecision
    router_decision_sha256: str
    current_reconciliation_sha256: str
    fixture_id: str
    event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime
    _current_reconciliation: current_recon.SportyBetCurrentEventDiscoveryReconciliationBundle

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PortfolioOptimizerV3CurrentProviderError("Portfolio Router inputs are builder-only")

    @classmethod
    def from_router_decision(cls, router_decision: router_v3.MarketRouterV3CurrentProviderDecision) -> "CurrentProviderPortfolioRouterInput":
        if type(router_decision) is not router_v3.MarketRouterV3CurrentProviderDecision:
            raise PortfolioOptimizerV3CurrentProviderError("exact Router v3 decision is required")
        try:
            decision = router_v3.verify_market_router_v3_current_provider_decision(router_decision)
            retained = decision.price_all_evaluation._source_bundle._source_mapping._current_bundle
            current_bundle = current_recon.verify_current_event_discovery_reconciliation_bundle(retained)
        except Exception as exc:
            raise PortfolioOptimizerV3CurrentProviderError("retained Router/current reconciliation replay failed") from exc
        rows = tuple(row for row in current_bundle.rows if row.event_id == decision.event_id)
        if len(rows) != 1:
            raise PortfolioOptimizerV3CurrentProviderError("exactly one retained current reconciliation row is required")
        row = rows[0]
        if (
            row.disposition is not current_recon.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
            or row.fixture_reconciliation_authorized is not True
            or row.matched_fotmob_fixture_id != decision.fixture_id
            or row.competition_name is None
            or row.kickoff_utc != decision.kickoff_utc
        ):
            raise PortfolioOptimizerV3CurrentProviderError("retained current reconciliation row is not exact and authorized")
        source = decision.price_all_evaluation
        if (
            row.direct_event_inventory_sha256 != source.current_inventory_sha256
            or row.direct_event_manifest_sha256 != source.current_manifest_sha256
            or row.direct_event_raw_sha256 != source.current_raw_sha256
            or source.source_current_reconciliation_sha256 != current_bundle.canonical_sha256
        ):
            raise PortfolioOptimizerV3CurrentProviderError("PR251 row ancestry differs from selected current quote ancestry")
        value = object.__new__(cls)
        for name, field in {
            "router_decision": decision,
            "router_decision_sha256": decision.canonical_sha256,
            "current_reconciliation_sha256": current_bundle.canonical_sha256,
            "fixture_id": decision.fixture_id,
            "event_id": decision.event_id,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "competition": row.competition_name,
            "kickoff_utc": row.kickoff_utc,
            "_current_reconciliation": retained,
        }.items():
            object.__setattr__(value, name, field)
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "router_decision_sha256": self.router_decision_sha256,
            "current_reconciliation_sha256": self.current_reconciliation_sha256,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
        }


def verify_current_provider_portfolio_router_input(value: Any) -> CurrentProviderPortfolioRouterInput:
    if type(value) is not CurrentProviderPortfolioRouterInput:
        raise PortfolioOptimizerV3CurrentProviderError("exact Portfolio Router input is required")
    rebuilt = CurrentProviderPortfolioRouterInput.from_router_decision(value.router_decision)
    if rebuilt.to_dict() != value.to_dict():
        raise PortfolioOptimizerV3CurrentProviderError("Portfolio Router input differs from source replay")
    return rebuilt


@dataclasses.dataclass(frozen=True)
class CurrentProviderPortfolioLeg:
    leg_id: str
    router_decision_sha256: str
    selected_opportunity_id: str
    fixture_id: str
    event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime
    market_id: MarketId
    outcome_id: OutcomeId
    line: float | None
    market_family: MarketFamily
    provider_market_id: str
    provider_outcome_id: str
    provider_specifier: str | None
    provider_market_name: str
    provider_outcome_name: str
    decimal_odds: float
    quote_sha256: str
    current_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    current_mapping_rebind_sha256: str
    current_mapping_contract_sha256: str
    current_reconciliation_sha256: str
    source_legacy_mapping_sha256: str
    router_quote_age_seconds: float
    portfolio_quote_age_seconds: float
    portfolio_kickoff_lead_seconds: float
    robust_net_expected_value: float
    robust_edge: float | None
    event_probability_floor: float | None
    survival_probability_floor: float
    model_count: int
    fragility_status: FragilityStatus

    @property
    def fragile(self) -> bool:
        return self.fragility_status is not FragilityStatus.NON_FRAGILE

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value.update({
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "market_family": self.market_family.value,
            "fragility_status": self.fragility_status.value,
            "fragile": self.fragile,
        })
        return value


@dataclasses.dataclass(frozen=True)
class CurrentProviderReserveLeg:
    leg: CurrentProviderPortfolioLeg
    reserve_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"leg": self.leg.to_dict(), "reserve_reasons": list(self.reserve_reasons)}


@dataclasses.dataclass(frozen=True)
class CurrentProviderPortfolioRouteAudit:
    fixture_id: str
    event_id: str
    router_decision_sha256: str
    router_decision_status: str
    admitted: bool
    admission_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "router_decision_sha256": self.router_decision_sha256,
            "router_decision_status": self.router_decision_status,
            "admitted": self.admitted,
            "admission_reasons": list(self.admission_reasons),
        }


@dataclasses.dataclass(frozen=True, init=False)
class CurrentProviderPortfolioOptimization:
    dataset_name: str
    status: str
    proof_mode: str
    portfolio_optimizer_v3_contract_sha256: str
    market_router_v3_contract_sha256: str
    portfolio_v2_policy_contract_sha256: str
    evaluation_time: datetime
    requested_target_size: int
    selected_legs: tuple[CurrentProviderPortfolioLeg, ...]
    reserve_legs: tuple[CurrentProviderReserveLeg, ...]
    route_audits: tuple[CurrentProviderPortfolioRouteAudit, ...]
    optimization_status: PortfolioOptimizationStatus
    shortfall: int
    expected_slip_survival: float | None
    combined_decimal_odds_product: float | None
    exposure_summary: Mapping[str, Any]
    authority: Mapping[str, bool]
    next_boundary: str
    _router_inputs: tuple[CurrentProviderPortfolioRouterInput, ...]
    _require_live_current: bool

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PortfolioOptimizerV3CurrentProviderError("Portfolio v3 optimizations are builder-only")

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    @property
    def optimization_id(self) -> str:
        return self.canonical_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "portfolio_optimizer_v3_contract_sha256": self.portfolio_optimizer_v3_contract_sha256,
            "market_router_v3_contract_sha256": self.market_router_v3_contract_sha256,
            "portfolio_v2_policy_contract_sha256": self.portfolio_v2_policy_contract_sha256,
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "requested_target_size": self.requested_target_size,
            "selected_legs": [item.to_dict() for item in self.selected_legs],
            "reserve_legs": [item.to_dict() for item in self.reserve_legs],
            "route_audits": [item.to_dict() for item in self.route_audits],
            "optimization_status": self.optimization_status.value,
            "shortfall": self.shortfall,
            "fulfilled": self.fulfilled,
            "expected_slip_survival": self.expected_slip_survival,
            "combined_decimal_odds_product": self.combined_decimal_odds_product,
            "exposure_summary": dict(self.exposure_summary),
            "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
            "reserve_policy_id": RESERVE_POLICY_ID,
            "shortfall_policy_id": SHORTFALL_POLICY_ID,
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _selected_results(decision: router_v3.MarketRouterV3CurrentProviderDecision) -> tuple[Any, ...]:
    opportunity = decision.selected_opportunity
    if opportunity is None:
        raise PortfolioOptimizerV3CurrentProviderError("Router selected opportunity is absent")
    expected = {item.candidate_id: item for item in opportunity.variants}
    results = tuple(x for x in decision.price_all_evaluation.results if x.candidate.candidate_id in expected)
    if len(results) != len(expected):
        raise PortfolioOptimizerV3CurrentProviderError("Router variants differ from Price-all results")
    for result in results:
        variant = expected[result.candidate.candidate_id]
        if result.canonical_sha256 != variant.price_all_result_sha256 or result.quote is None:
            raise PortfolioOptimizerV3CurrentProviderError("Router variant/quote ancestry mismatch")
    return results


def _survival(opportunity: router_v3.CurrentProviderRoutedOpportunity, results: Sequence[Any]) -> float:
    if opportunity.market_id not in _FULL_SETTLEMENT:
        if opportunity.event_probability_floor is None:
            raise PortfolioOptimizerV3CurrentProviderError("ordinary leg lacks event probability floor")
        return _finite_probability(
            opportunity.event_probability_floor,
            "ordinary leg event probability floor",
        )
    values: list[float] = []
    for result in results:
        probabilities = result.candidate.probability_map
        components = frozenset(probabilities)
        if opportunity.market_id is MarketId.DRAW_NO_BET:
            if components != _DNB_COMPONENTS:
                raise PortfolioOptimizerV3CurrentProviderError(
                    "DNB settlement components drifted"
                )
            survival = probabilities["WIN"] + probabilities["PUSH"]
        else:
            if components != _AH_COMPONENTS:
                raise PortfolioOptimizerV3CurrentProviderError(
                    "Asian Handicap settlement components drifted"
                )
            survival = (
                probabilities["WIN"]
                + probabilities["HALF_WIN"]
                + probabilities["PUSH"]
            )
        values.append(
            _finite_probability(
                survival,
                "selected settlement survival probability",
            )
        )
    if not values:
        raise PortfolioOptimizerV3CurrentProviderError(
            "selected full-settlement opportunity has no model variants"
        )
    return min(values)


def _fragility(robust_ev: float, survival: float) -> FragilityStatus:
    return frozen_v2._fragility(robust_ev, survival)


def _build_leg(source: CurrentProviderPortfolioRouterInput, now: datetime) -> CurrentProviderPortfolioLeg:
    decision = source.router_decision
    opportunity = decision.selected_opportunity
    if decision.decision_status is not RouterDecisionStatus.SELECTED or opportunity is None:
        raise PortfolioOptimizerV3CurrentProviderError("only Router SELECTED can become a leg")
    if opportunity.eligibility is not OpportunityEligibility.ELIGIBLE:
        raise PortfolioOptimizerV3CurrentProviderError("selected Router opportunity is not eligible")
    age = (now - decision.source_observed_at).total_seconds()
    lead = (decision.kickoff_utc - now).total_seconds()
    if not math.isfinite(age) or age < 0:
        raise PortfolioOptimizerV3CurrentProviderError(
            "selected current-provider source is future-dated at portfolio time"
        )
    if not math.isfinite(lead):
        raise PortfolioOptimizerV3CurrentProviderError(
            "selected current-provider kickoff lead is invalid"
        )
    if age > decision.price_all_evaluation.max_quote_age_seconds or lead <= decision.price_all_evaluation.minimum_lead_seconds:
        raise PortfolioOptimizerV3CurrentProviderError("selected leg is stale or too close to kickoff")
    results = _selected_results(decision)
    quote_shas = {_sha(result.quote.to_dict()) for result in results}
    if quote_shas != {opportunity.quote_sha256}:
        raise PortfolioOptimizerV3CurrentProviderError("selected variants do not share Router quote")
    quote = results[0].quote
    required = (
        opportunity.provider_market_id, opportunity.provider_outcome_id,
        opportunity.provider_market_name, opportunity.provider_outcome_name,
        opportunity.decimal_odds, opportunity.robust_net_expected_value,
    )
    if any(value is None for value in required):
        raise PortfolioOptimizerV3CurrentProviderError("selected opportunity omitted exact execution ancestry")
    if (
        quote.provider_market_id != opportunity.provider_market_id
        or quote.provider_outcome_id != opportunity.provider_outcome_id
        or quote.provider_specifier != opportunity.provider_specifier
        or quote.source_raw_sha256 != opportunity.source_raw_sha256
        or opportunity.source_current_reconciliation_sha256 != source.current_reconciliation_sha256
    ):
        raise PortfolioOptimizerV3CurrentProviderError("selected Router/provider/current reconciliation ancestry differs")
    robust_ev = float(opportunity.robust_net_expected_value)
    if not math.isfinite(robust_ev) or robust_ev <= 0.0:
        raise PortfolioOptimizerV3CurrentProviderError(
            "selected Router opportunity lacks positive robust EV"
        )
    odds = float(opportunity.decimal_odds)
    if not math.isfinite(odds) or odds <= 1.0:
        raise PortfolioOptimizerV3CurrentProviderError(
            "selected Router opportunity lacks valid decimal odds"
        )
    router_age = opportunity.router_quote_age_seconds
    if router_age is None or not math.isfinite(router_age) or router_age < 0:
        raise PortfolioOptimizerV3CurrentProviderError(
            "selected Router opportunity lacks valid Router quote age"
        )
    if age + 1e-9 < router_age:
        raise PortfolioOptimizerV3CurrentProviderError(
            "portfolio quote age cannot be younger than Router quote age"
        )
    survival = _survival(opportunity, results)
    payload = {
        "router_decision_sha256": decision.canonical_sha256,
        "opportunity_id": opportunity.opportunity_id,
        "quote_sha256": opportunity.quote_sha256,
        "current_reconciliation_sha256": source.current_reconciliation_sha256,
    }
    return CurrentProviderPortfolioLeg(
        leg_id=_sha(payload), router_decision_sha256=decision.canonical_sha256,
        selected_opportunity_id=opportunity.opportunity_id,
        fixture_id=source.fixture_id, event_id=source.event_id,
        home_team=source.home_team, away_team=source.away_team,
        competition=source.competition, kickoff_utc=source.kickoff_utc,
        market_id=opportunity.market_id, outcome_id=opportunity.outcome_id,
        line=opportunity.line, market_family=MARKET_REGISTRY[opportunity.market_id].family,
        provider_market_id=str(opportunity.provider_market_id),
        provider_outcome_id=str(opportunity.provider_outcome_id),
        provider_specifier=opportunity.provider_specifier,
        provider_market_name=str(opportunity.provider_market_name),
        provider_outcome_name=str(opportunity.provider_outcome_name),
        decimal_odds=odds,
        quote_sha256=str(opportunity.quote_sha256),
        current_inventory_sha256=opportunity.current_inventory_sha256,
        source_manifest_sha256=opportunity.source_manifest_sha256,
        source_raw_sha256=opportunity.source_raw_sha256,
        current_mapping_rebind_sha256=opportunity.current_mapping_rebind_sha256,
        current_mapping_contract_sha256=opportunity.current_mapping_contract_sha256,
        current_reconciliation_sha256=source.current_reconciliation_sha256,
        source_legacy_mapping_sha256=opportunity.source_legacy_mapping_sha256,
        router_quote_age_seconds=float(router_age),
        portfolio_quote_age_seconds=age,
        portfolio_kickoff_lead_seconds=lead,
        robust_net_expected_value=robust_ev,
        robust_edge=opportunity.robust_edge,
        event_probability_floor=opportunity.event_probability_floor,
        survival_probability_floor=survival,
        model_count=len(opportunity.variants),
        fragility_status=_fragility(robust_ev, survival),
    )


def _caps(target: int) -> dict[str, int]:
    def cap(share: float, minimum: int) -> int:
        return 1 if target == 1 else min(target, max(minimum, math.ceil(target * share)))
    return {
        "team": MAXIMUM_TEAM_APPEARANCES,
        "competition": cap(MAXIMUM_COMPETITION_SHARE, MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2),
        "market_family": cap(MAXIMUM_MARKET_FAMILY_SHARE, MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2),
        "fragile": min(target, max(MINIMUM_FRAGILE_CAP, math.ceil(target * MAXIMUM_FRAGILE_SHARE))),
    }


def _counts(selected: Sequence[CurrentProviderPortfolioLeg]) -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
    teams: dict[str, int] = {}; competitions: dict[str, int] = {}; families: dict[str, int] = {}; fragile = 0
    for leg in selected:
        for team in (leg.home_team, leg.away_team): teams[team] = teams.get(team, 0) + 1
        competitions[leg.competition] = competitions.get(leg.competition, 0) + 1
        families[leg.market_family.value] = families.get(leg.market_family.value, 0) + 1
        fragile += int(leg.fragile)
    return teams, competitions, families, fragile


def _constraints(candidate: CurrentProviderPortfolioLeg, selected: Sequence[CurrentProviderPortfolioLeg], caps: Mapping[str, int]) -> tuple[str, ...]:
    teams, competitions, families, fragile = _counts(selected); reasons = []
    for team in (candidate.home_team, candidate.away_team):
        if teams.get(team, 0) >= caps["team"]: reasons.append(f"TEAM_EXPOSURE_CAP:{team}")
    if competitions.get(candidate.competition, 0) >= caps["competition"]: reasons.append(f"COMPETITION_CONCENTRATION_CAP:{candidate.competition}")
    if families.get(candidate.market_family.value, 0) >= caps["market_family"]: reasons.append(f"MARKET_FAMILY_CONCENTRATION_CAP:{candidate.market_family.value}")
    if candidate.fragile and fragile >= caps["fragile"]: reasons.append("FRAGILITY_CAP")
    return tuple(sorted(set(reasons)))


def _marginal(candidate: CurrentProviderPortfolioLeg, selected: Sequence[CurrentProviderPortfolioLeg], caps: Mapping[str, int]) -> tuple[Any, ...]:
    _, competitions, families, fragile = _counts(selected)
    penalty = competitions.get(candidate.competition, 0) / caps["competition"] + families.get(candidate.market_family.value, 0) / caps["market_family"] + (fragile / caps["fragile"] if candidate.fragile else 0)
    return (penalty, -candidate.survival_probability_floor, -candidate.robust_net_expected_value, 0 if candidate.robust_edge is not None else 1, -(candidate.robust_edge or 0), candidate.portfolio_quote_age_seconds, candidate.leg_id)


def _reserve_key(candidate: CurrentProviderPortfolioLeg) -> tuple[Any, ...]:
    edge_present = candidate.robust_edge is not None
    return (
        -candidate.survival_probability_floor,
        -candidate.robust_net_expected_value,
        0 if edge_present else 1,
        -(candidate.robust_edge if candidate.robust_edge is not None else 0.0),
        candidate.portfolio_quote_age_seconds,
        candidate.leg_id,
    )


def _survival_product(selected: Sequence[CurrentProviderPortfolioLeg]) -> float | None:
    if not selected:
        return None
    value = math.prod(item.survival_probability_floor for item in selected)
    if not math.isfinite(value):
        raise PortfolioOptimizerV3CurrentProviderError(
            "independence survival baseline is non-finite"
        )
    return value


def _odds_product(selected: Sequence[CurrentProviderPortfolioLeg]) -> float | None:
    if not selected:
        return None
    value = Decimal("1")
    for item in selected:
        value *= Decimal(str(item.decimal_odds))
    result = float(value)
    return result if math.isfinite(result) else None


def _build(router_inputs: Iterable[CurrentProviderPortfolioRouterInput], *, target_size: int, evaluation_time: datetime, require_live_current: bool) -> CurrentProviderPortfolioOptimization:
    identities = validate_portfolio_optimizer_v3_contract(); now = _utc(evaluation_time, "evaluation_time")
    if type(target_size) is not int or not 1 <= target_size <= MAXIMUM_TARGET_SIZE:
        raise PortfolioOptimizerV3CurrentProviderError(f"target_size must be 1..{MAXIMUM_TARGET_SIZE}")
    inputs = tuple(router_inputs)
    verified = tuple(verify_current_provider_portfolio_router_input(item) for item in inputs)
    if len({item.fixture_id for item in verified}) != len(verified) or len({item.event_id for item in verified}) != len(verified):
        raise PortfolioOptimizerV3CurrentProviderError("duplicate fixture or provider event input")
    if any(item.router_decision.evaluation_time > now for item in verified):
        raise PortfolioOptimizerV3CurrentProviderError(
            "portfolio evaluation_time predates a Router v3 decision"
        )
    if require_live_current and any(
        item.router_decision.proof_mode != router_v3.price_v3.LIVE_CURRENT
        or item.router_decision.status != router_v3.STATUS_LIVE
        for item in verified
    ):
        raise PortfolioOptimizerV3CurrentProviderError("live Portfolio v3 requires live current Router ancestry")
    candidates: list[CurrentProviderPortfolioLeg] = []
    audits: list[CurrentProviderPortfolioRouteAudit] = []
    for item in sorted(verified, key=lambda value: value.fixture_id):
        if item.router_decision.decision_status is RouterDecisionStatus.SELECTED:
            try:
                candidates.append(_build_leg(item, now))
                admitted, reasons = True, ()
            except PortfolioOptimizerV3CurrentProviderError as exc:
                admitted, reasons = False, (str(exc),)
        else:
            admitted, reasons = False, tuple(item.router_decision.decision_reasons)
        audits.append(CurrentProviderPortfolioRouteAudit(
            fixture_id=item.fixture_id,
            event_id=item.event_id,
            router_decision_sha256=item.router_decision_sha256,
            router_decision_status=item.router_decision.decision_status.value,
            admitted=admitted,
            admission_reasons=tuple(sorted(set(reasons))),
        ))
    caps = _caps(target_size); selected: list[CurrentProviderPortfolioLeg] = []; remaining = sorted(candidates, key=lambda item: item.leg_id)
    while remaining and len(selected) < target_size:
        eligible = [item for item in remaining if not _constraints(item, selected, caps)]
        if not eligible: break
        chosen = min(eligible, key=lambda item: _marginal(item, selected, caps)); selected.append(chosen); remaining.remove(chosen)
    selected = sorted(selected, key=lambda item: item.leg_id); selected_ids = {x.leg_id for x in selected}
    reserve_rows: list[CurrentProviderReserveLeg] = []
    for item in sorted(
        (candidate for candidate in candidates if candidate.leg_id not in selected_ids),
        key=_reserve_key,
    ):
        reasons = list(_constraints(item, selected, caps))
        if len(selected) >= target_size:
            reasons.append("TARGET_FILLED")
        if not reasons:
            reasons.append("LOWER_MARGINAL_PORTFOLIO_PRIORITY")
        reserve_rows.append(
            CurrentProviderReserveLeg(
                item,
                tuple(sorted(set(reasons))),
            )
        )
    reserves = tuple(reserve_rows)
    shortfall = max(0, target_size - len(selected))
    status = PortfolioOptimizationStatus.QUALIFIED_SET if selected else PortfolioOptimizationStatus.NO_QUALIFIED_LEGS
    survival = _survival_product(selected)
    odds = _odds_product(selected)
    teams, competitions, families, fragile = _counts(selected)
    exposure = types.MappingProxyType({"caps": dict(caps), "team_counts": dict(sorted(teams.items())), "competition_counts": dict(sorted(competitions.items())), "market_family_counts": dict(sorted(families.items())), "fragile_count": fragile, "statistical_correlation_coefficients": None, "joint_dependence_status": JOINT_DEPENDENCE_STATUS})
    value = object.__new__(CurrentProviderPortfolioOptimization)
    for name, field in {
        "dataset_name": DATASET_NAME,
        "status": STATUS_LIVE if require_live_current else STATUS_AS_OF,
        "proof_mode": router_v3.price_v3.LIVE_CURRENT if require_live_current else router_v3.price_v3.AS_OF_REPLAY,
        "portfolio_optimizer_v3_contract_sha256": identities["portfolio_optimizer_v3_contract_sha256"],
        "market_router_v3_contract_sha256": MARKET_ROUTER_V3_CONTRACT_SHA256,
        "portfolio_v2_policy_contract_sha256": PORTFOLIO_V2_CONTRACT_SHA256,
        "evaluation_time": now,
        "requested_target_size": target_size,
        "selected_legs": tuple(selected), "reserve_legs": reserves,
        "route_audits": tuple(sorted(audits, key=lambda item: item.fixture_id)),
        "optimization_status": status, "shortfall": shortfall,
        "expected_slip_survival": survival, "combined_decimal_odds_product": odds,
        "exposure_summary": exposure, "authority": types.MappingProxyType(dict(AUTHORITY)),
        "next_boundary": NEXT_BOUNDARY, "_router_inputs": verified,
        "_require_live_current": require_live_current,
    }.items(): object.__setattr__(value, name, field)
    return value


def optimize_current_provider_portfolio_as_of(router_inputs: Iterable[CurrentProviderPortfolioRouterInput], *, target_size: int, evaluation_time: datetime) -> CurrentProviderPortfolioOptimization:
    return _build(router_inputs, target_size=target_size, evaluation_time=evaluation_time, require_live_current=False)


def optimize_current_provider_portfolio(router_inputs: Iterable[CurrentProviderPortfolioRouterInput], *, target_size: int) -> CurrentProviderPortfolioOptimization:
    return _build(router_inputs, target_size=target_size, evaluation_time=_now_utc(), require_live_current=True)


def verify_current_provider_portfolio_optimization(value: Any) -> CurrentProviderPortfolioOptimization:
    if type(value) is not CurrentProviderPortfolioOptimization:
        raise PortfolioOptimizerV3CurrentProviderError("exact Portfolio v3 optimization is required")
    rebuilt = _build(value._router_inputs, target_size=value.requested_target_size, evaluation_time=value.evaluation_time, require_live_current=value._require_live_current)
    if rebuilt.to_dict() != value.to_dict():
        raise PortfolioOptimizerV3CurrentProviderError("Portfolio v3 differs from source reconstruction")
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
