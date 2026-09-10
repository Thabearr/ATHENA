"""Canonical ATHENA Portfolio interface (P1.5).

P1.5 promotes the reviewed cross-fixture Portfolio-v3 selection/shortfall policy
behind the unversioned ``domain.portfolio_optimizer`` boundary. Inputs are
verified P1.4 canonical Router decisions and the public target parameter is
``target_legs``. Exposure caps, marginal ordering, reserve reasons, fragility
classification, settlement-survival handling and shortfall behavior remain
delegated to the reviewed Portfolio-v3 policy helpers; this module does not copy
or change those formulas.

The output is a canonical ``SelectedPortfolio`` for the later delivery boundary.
This module does not generate football probabilities, price markets, reroute a
fixture, optimize to target total odds, calculate Kelly stakes, create a share
code, authenticate, access a wallet, stake, or place a wager.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import types
from typing import Any

from domain import market_router_canonical_adapter as _router
from domain import portfolio_optimizer_v3_current_provider as _v3
from domain import run_contracts as _runs
from domain._market_router_contracts import OpportunityEligibility, RouterDecisionStatus
from domain._portfolio_optimizer_v2_direct_provider_contracts import (
    FragilityStatus,
    PortfolioOptimizationStatus,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CANONICAL_PORTFOLIO_V1"
IMPLEMENTATION_ID = "domain.portfolio_optimizer"
OUTPUT_CONTRACT = "SelectedPortfolio"
CANONICAL_ROUTER_IMPLEMENTATION_ID = _router.IMPLEMENTATION_ID
CANONICAL_ROUTER_CONTRACT_SHA256 = _router.EXPECTED_CONTRACT_SHA256
SOURCE_PORTFOLIO_V3_CONTRACT_SHA256 = _v3.EXPECTED_CONTRACT_SHA256
SOURCE_OPTIMIZATION_POLICY_ID = _v3.OPTIMIZATION_POLICY_ID
FROZEN_PORTFOLIO_V2_CONTRACT_SHA256 = _v3.PORTFOLIO_V2_CONTRACT_SHA256
MIN_TARGET_LEGS = _runs.MIN_TARGET_LEGS
MAX_TARGET_LEGS = _runs.MAX_TARGET_LEGS
RESERVE_POLICY_ID = _v3.RESERVE_POLICY_ID
SHORTFALL_POLICY_ID = _v3.SHORTFALL_POLICY_ID
JOINT_DEPENDENCE_STATUS = _v3.JOINT_DEPENDENCE_STATUS
AS_OF_REPLAY = _v3.router_v3.price_v3.AS_OF_REPLAY
LIVE_CURRENT = _v3.router_v3.price_v3.LIVE_CURRENT
STATUS_AS_OF = "CANONICAL_SELECTED_PORTFOLIO_AS_OF_VERIFIED"
STATUS_LIVE = "CANONICAL_SELECTED_PORTFOLIO_LIVE_VERIFIED"
NEXT_BOUNDARY = "CANONICAL_SPORTYBET_SHARE_CODE_SERVICE_REQUIRES_SELECTED_PORTFOLIO"

AUTHORITY = types.MappingProxyType(
    {
        "canonical_router_consumption": True,
        "source_portfolio_v3_policy_reuse": True,
        "portfolio_optimization": True,
        "qualified_leg_set": True,
        "reserve_leg_recording": True,
        "final_cross_fixture_selection": True,
        "truthful_shortfall": True,
        "football_probability_generation": False,
        "calibration": False,
        "price_all_value_computation": False,
        "market_routing": False,
        "target_total_odds_optimization": False,
        "kelly_optimization": False,
        "statistical_joint_dependence_model": False,
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


class CanonicalPortfolioError(ValueError):
    """Canonical Portfolio rejected input or source-policy reconstruction."""


def _canonical_bytes(value: Any) -> bytes:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalPortfolioError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalPortfolioError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalPortfolioError(f"{label} is invalid") from exc


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "implementation_id": IMPLEMENTATION_ID,
        "output_contract": OUTPUT_CONTRACT,
        "canonical_router_implementation_id": CANONICAL_ROUTER_IMPLEMENTATION_ID,
        "canonical_router_contract_sha256": CANONICAL_ROUTER_CONTRACT_SHA256,
        "source_portfolio_v3_contract_sha256": SOURCE_PORTFOLIO_V3_CONTRACT_SHA256,
        "source_optimization_policy_id": SOURCE_OPTIMIZATION_POLICY_ID,
        "target_field": "target_legs",
        "target_legs": {
            "minimum": MIN_TARGET_LEGS,
            "maximum": MAX_TARGET_LEGS,
        },
        "caps": {
            "maximum_team_appearances": _v3.MAXIMUM_TEAM_APPEARANCES,
            "maximum_competition_share": _v3.MAXIMUM_COMPETITION_SHARE,
            "minimum_competition_cap_when_target_ge_2": _v3.MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2,
            "maximum_market_family_share": _v3.MAXIMUM_MARKET_FAMILY_SHARE,
            "minimum_market_family_cap_when_target_ge_2": _v3.MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2,
            "maximum_fragile_share": _v3.MAXIMUM_FRAGILE_SHARE,
            "minimum_fragile_cap": _v3.MINIMUM_FRAGILE_CAP,
        },
        "reserve_policy_id": RESERVE_POLICY_ID,
        "shortfall_policy_id": SHORTFALL_POLICY_ID,
        "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
        "target_total_odds_objective": False,
        "kelly_objective": False,
        "authority": dict(AUTHORITY),
    }


def calculate_portfolio_contract_sha256() -> str:
    return _sha(_contract_payload())


EXPECTED_CONTRACT_SHA256 = "916247c4a891e3c0a2b8205b9d33000987471a54107f2b3d508c8e5ab1e9a99c"


def validate_portfolio_contract() -> Mapping[str, Any]:
    try:
        router = _router.validate_canonical_market_router_contract()
        source = _v3.validate_portfolio_optimizer_v3_contract()
    except Exception as exc:
        raise CanonicalPortfolioError("canonical Portfolio dependency validation failed") from exc
    if (
        router["canonical_market_router_contract_sha256"]
        != CANONICAL_ROUTER_CONTRACT_SHA256
    ):
        raise CanonicalPortfolioError("canonical Router contract identity drifted")
    if (
        source["portfolio_optimizer_v3_contract_sha256"]
        != SOURCE_PORTFOLIO_V3_CONTRACT_SHA256
    ):
        raise CanonicalPortfolioError("source Portfolio-v3 contract identity drifted")
    if source["portfolio_v2_policy_contract_sha256"] != FROZEN_PORTFOLIO_V2_CONTRACT_SHA256:
        raise CanonicalPortfolioError("frozen Portfolio-v2 policy identity drifted")
    if MIN_TARGET_LEGS != 1 or MAX_TARGET_LEGS != 50:
        raise CanonicalPortfolioError("canonical RunRequest target_legs bounds drifted")
    actual = calculate_portfolio_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CanonicalPortfolioError("canonical Portfolio contract drifted")
    return types.MappingProxyType(
        {
            "canonical_portfolio_contract_sha256": actual,
            "canonical_router_contract_sha256": CANONICAL_ROUTER_CONTRACT_SHA256,
            "source_portfolio_v3_contract_sha256": SOURCE_PORTFOLIO_V3_CONTRACT_SHA256,
            "frozen_portfolio_v2_contract_sha256": FROZEN_PORTFOLIO_V2_CONTRACT_SHA256,
        }
    )


@dataclasses.dataclass(frozen=True, init=False)
class PortfolioRouterInput:
    """Verified exposure/source binding for one canonical Router decision."""

    router_decision: _router.RouterDecision
    canonical_router_decision_sha256: str
    source_router_v3_decision_sha256: str
    source_portfolio_router_input_sha256: str
    fixture_id: str
    event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime
    current_reconciliation_sha256: str
    _source_portfolio_input: _v3.CurrentProviderPortfolioRouterInput

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CanonicalPortfolioError(
            "PortfolioRouterInput is builder-only; use from_router_decision()"
        )

    @classmethod
    def from_router_decision(
        cls, router_decision: _router.RouterDecision
    ) -> "PortfolioRouterInput":
        if type(router_decision) is not _router.RouterDecision:
            raise CanonicalPortfolioError("exact canonical RouterDecision is required")
        try:
            decision = _router.verify_router_decision(router_decision)
            source_decision = decision._source_decision
            source_input = _v3.CurrentProviderPortfolioRouterInput.from_router_decision(
                source_decision
            )
        except Exception as exc:
            raise CanonicalPortfolioError(
                "canonical Router/current reconciliation source replay failed"
            ) from exc
        if decision.fixture_id != source_input.fixture_id or decision.event_id != source_input.event_id:
            raise CanonicalPortfolioError(
                "canonical Router identity differs from source Portfolio exposure"
            )
        if (
            decision.source_router_v3_decision_sha256
            != source_input.router_decision_sha256
        ):
            raise CanonicalPortfolioError(
                "canonical Router source-v3 identity differs from Portfolio exposure"
            )
        value = object.__new__(cls)
        for name, field in {
            "router_decision": decision,
            "canonical_router_decision_sha256": decision.canonical_sha256,
            "source_router_v3_decision_sha256": source_input.router_decision_sha256,
            "source_portfolio_router_input_sha256": _sha(source_input.to_dict()),
            "fixture_id": source_input.fixture_id,
            "event_id": source_input.event_id,
            "home_team": source_input.home_team,
            "away_team": source_input.away_team,
            "competition": source_input.competition,
            "kickoff_utc": source_input.kickoff_utc,
            "current_reconciliation_sha256": source_input.current_reconciliation_sha256,
            "_source_portfolio_input": source_input,
        }.items():
            object.__setattr__(value, name, field)
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_router_decision_sha256": self.canonical_router_decision_sha256,
            "source_router_v3_decision_sha256": self.source_router_v3_decision_sha256,
            "source_portfolio_router_input_sha256": self.source_portfolio_router_input_sha256,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": _iso(self.kickoff_utc),
            "current_reconciliation_sha256": self.current_reconciliation_sha256,
        }


def verify_portfolio_router_input(value: Any) -> PortfolioRouterInput:
    if type(value) is not PortfolioRouterInput:
        raise CanonicalPortfolioError("exact PortfolioRouterInput is required")
    rebuilt = PortfolioRouterInput.from_router_decision(value.router_decision)
    if rebuilt.to_dict() != value.to_dict():
        raise CanonicalPortfolioError(
            "PortfolioRouterInput differs from exact source reconstruction"
        )
    return rebuilt


@dataclasses.dataclass(frozen=True)
class PortfolioLeg:
    leg_id: str
    canonical_router_decision_sha256: str
    source_router_v3_decision_sha256: str
    selected_opportunity_id: str
    prediction_identity_sha256: str
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
    prediction_confidence: float
    prediction_confidence_method: str
    model_count: int
    fragility_status: FragilityStatus

    @property
    def fragile(self) -> bool:
        return self.fragility_status is not FragilityStatus.NON_FRAGILE

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg_id": self.leg_id,
            "canonical_router_decision_sha256": self.canonical_router_decision_sha256,
            "source_router_v3_decision_sha256": self.source_router_v3_decision_sha256,
            "selected_opportunity_id": self.selected_opportunity_id,
            "prediction_identity_sha256": self.prediction_identity_sha256,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": _iso(self.kickoff_utc),
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "market_family": self.market_family.value,
            "provider_market_id": self.provider_market_id,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_specifier": self.provider_specifier,
            "provider_market_name": self.provider_market_name,
            "provider_outcome_name": self.provider_outcome_name,
            "decimal_odds": self.decimal_odds,
            "quote_sha256": self.quote_sha256,
            "current_inventory_sha256": self.current_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": self.current_mapping_contract_sha256,
            "current_reconciliation_sha256": self.current_reconciliation_sha256,
            "source_legacy_mapping_sha256": self.source_legacy_mapping_sha256,
            "router_quote_age_seconds": self.router_quote_age_seconds,
            "portfolio_quote_age_seconds": self.portfolio_quote_age_seconds,
            "portfolio_kickoff_lead_seconds": self.portfolio_kickoff_lead_seconds,
            "robust_net_expected_value": self.robust_net_expected_value,
            "robust_edge": self.robust_edge,
            "event_probability_floor": self.event_probability_floor,
            "survival_probability_floor": self.survival_probability_floor,
            "prediction_confidence": self.prediction_confidence,
            "prediction_confidence_method": self.prediction_confidence_method,
            "model_count": self.model_count,
            "fragility_status": self.fragility_status.value,
            "fragile": self.fragile,
        }


@dataclasses.dataclass(frozen=True)
class ReserveLeg:
    leg: PortfolioLeg
    reserve_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg": self.leg.to_dict(),
            "reserve_reasons": list(self.reserve_reasons),
        }


@dataclasses.dataclass(frozen=True)
class PortfolioRouteAudit:
    fixture_id: str
    event_id: str
    canonical_router_decision_sha256: str
    source_router_v3_decision_sha256: str
    router_decision_status: str
    selected_opportunity_id: str | None
    admitted: bool
    admission_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "canonical_router_decision_sha256": self.canonical_router_decision_sha256,
            "source_router_v3_decision_sha256": self.source_router_v3_decision_sha256,
            "router_decision_status": self.router_decision_status,
            "selected_opportunity_id": self.selected_opportunity_id,
            "admitted": self.admitted,
            "admission_reasons": list(self.admission_reasons),
        }


@dataclasses.dataclass(frozen=True, init=False)
class SelectedPortfolio:
    schema_version: int
    policy_id: str
    status: str
    proof_mode: str
    canonical_portfolio_contract_sha256: str
    canonical_router_contract_sha256: str
    source_portfolio_v3_contract_sha256: str
    evaluation_time: datetime
    target_legs: int
    selected_legs: tuple[PortfolioLeg, ...]
    reserve_legs: tuple[ReserveLeg, ...]
    route_audits: tuple[PortfolioRouteAudit, ...]
    optimization_status: PortfolioOptimizationStatus
    shortfall: int
    expected_slip_survival: float | None
    combined_decimal_odds_product: float | None
    exposure_summary: Mapping[str, Any]
    binding_caps: tuple[str, ...]
    reserve_policy_id: str
    shortfall_policy_id: str
    joint_dependence_status: str
    target_total_odds_objective: bool
    kelly_objective: bool
    authority: Mapping[str, bool]
    next_boundary: str
    _router_inputs: tuple[PortfolioRouterInput, ...]
    _require_live_current: bool

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CanonicalPortfolioError(
            "SelectedPortfolio is builder-only; use optimize_portfolio*()"
        )

    @property
    def selected_count(self) -> int:
        return len(self.selected_legs)

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0

    @property
    def canonical_sha256(self) -> str:
        return _sha(self._identity_dict())

    @property
    def selected_portfolio_id(self) -> str:
        return self.canonical_sha256

    @property
    def optimization_id(self) -> str:
        return self.canonical_sha256

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "canonical_portfolio_contract_sha256": self.canonical_portfolio_contract_sha256,
            "canonical_router_contract_sha256": self.canonical_router_contract_sha256,
            "source_portfolio_v3_contract_sha256": self.source_portfolio_v3_contract_sha256,
            "evaluation_time": _iso(self.evaluation_time),
            "target_legs": self.target_legs,
            "selected_count": self.selected_count,
            "selected_legs": [item.to_dict() for item in self.selected_legs],
            "reserve_legs": [item.to_dict() for item in self.reserve_legs],
            "route_audits": [item.to_dict() for item in self.route_audits],
            "optimization_status": self.optimization_status.value,
            "shortfall": self.shortfall,
            "fulfilled": self.fulfilled,
            "expected_slip_survival": self.expected_slip_survival,
            "combined_decimal_odds_product": self.combined_decimal_odds_product,
            "combined_decimal_odds_product_is_diagnostic_only": True,
            "exposure_summary": dict(self.exposure_summary),
            "binding_caps": list(self.binding_caps),
            "reserve_policy_id": self.reserve_policy_id,
            "shortfall_policy_id": self.shortfall_policy_id,
            "joint_dependence_status": self.joint_dependence_status,
            "target_total_odds_objective": self.target_total_odds_objective,
            "kelly_objective": self.kelly_objective,
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._identity_dict()
        payload["selected_portfolio_id"] = self.selected_portfolio_id
        payload["canonical_sha256"] = self.canonical_sha256
        return payload


def _source_opportunity(
    source_decision: Any,
    canonical_opportunity: _router.RouterOpportunity,
) -> Any:
    rows = tuple(
        item
        for item in source_decision.opportunities
        if item.opportunity_id == canonical_opportunity.opportunity_id
    )
    if len(rows) != 1:
        raise CanonicalPortfolioError(
            "canonical selected opportunity is absent or ambiguous in source Router v3"
        )
    source = rows[0]
    if (
        source.fixture_id != canonical_opportunity.fixture_id
        or source.event_id != canonical_opportunity.event_id
        or source.market_id is not canonical_opportunity.market_id
        or source.outcome_id is not canonical_opportunity.outcome_id
        or source.line != canonical_opportunity.line
        or source.provider_market_id != canonical_opportunity.provider_market_id
        or source.provider_outcome_id != canonical_opportunity.provider_outcome_id
        or source.provider_specifier != canonical_opportunity.provider_specifier
        or source.decimal_odds != canonical_opportunity.decimal_odds
        or source.quote_sha256 != canonical_opportunity.quote_sha256
        or source.robust_net_expected_value
        != canonical_opportunity.robust_net_expected_value
        or source.robust_edge != canonical_opportunity.robust_edge
        or source.event_probability_floor
        != canonical_opportunity.event_probability_floor
        or source.eligibility is not canonical_opportunity.source_v3_eligibility
    ):
        raise CanonicalPortfolioError(
            "canonical selected opportunity differs from source Router-v3 projection"
        )
    source_variants = {
        item.candidate_id: item.price_all_result_sha256 for item in source.variants
    }
    canonical_variants = {
        item.candidate_id: item.price_all_result_sha256
        for item in canonical_opportunity.variants
    }
    if source_variants != canonical_variants:
        raise CanonicalPortfolioError(
            "canonical selected variants differ from source Router-v3 projection"
        )
    return source


def _selected_results(source_decision: Any, source_opportunity: Any) -> tuple[Any, ...]:
    expected = {
        item.candidate_id: item.price_all_result_sha256
        for item in source_opportunity.variants
    }
    results = tuple(
        item
        for item in source_decision.price_all_evaluation.results
        if item.candidate.candidate_id in expected
    )
    if len(results) != len(expected):
        raise CanonicalPortfolioError(
            "selected source Router variants differ from Price-all results"
        )
    for result in results:
        if result.canonical_sha256 != expected[result.candidate.candidate_id]:
            raise CanonicalPortfolioError(
                "selected source Router variant/Price-all identity mismatch"
            )
        if result.quote is None:
            raise CanonicalPortfolioError(
                "selected source Router variant lacks exact provider quote"
            )
    return results


def _build_leg(source: PortfolioRouterInput, now: datetime) -> PortfolioLeg:
    decision = source.router_decision
    opportunity = decision.selected_opportunity
    if (
        decision.decision_status is not RouterDecisionStatus.SELECTED
        or opportunity is None
    ):
        raise CanonicalPortfolioError(
            "only canonical Router SELECTED decisions can become Portfolio legs"
        )
    if opportunity.eligibility is not OpportunityEligibility.ELIGIBLE:
        raise CanonicalPortfolioError(
            "canonical selected Router opportunity is not eligible"
        )
    if opportunity.prediction_confidence is None or not math.isfinite(
        opportunity.prediction_confidence
    ):
        raise CanonicalPortfolioError(
            "canonical selected Router opportunity lacks comparable confidence"
        )
    if type(opportunity.prediction_confidence_method) is not str or not opportunity.prediction_confidence_method:
        raise CanonicalPortfolioError(
            "canonical selected Router opportunity lacks confidence semantics"
        )
    source_decision = source._source_portfolio_input.router_decision
    source_opportunity = _source_opportunity(source_decision, opportunity)

    age = (now - source_decision.source_observed_at).total_seconds()
    lead = (source.kickoff_utc - now).total_seconds()
    if not math.isfinite(age) or age < 0:
        raise CanonicalPortfolioError(
            "selected current-provider source is future-dated at Portfolio time"
        )
    if not math.isfinite(lead):
        raise CanonicalPortfolioError(
            "selected current-provider kickoff lead is invalid"
        )
    if (
        age > source_decision.price_all_evaluation.max_quote_age_seconds
        or lead <= source_decision.price_all_evaluation.minimum_lead_seconds
    ):
        raise CanonicalPortfolioError("selected leg is stale or too close to kickoff")

    results = _selected_results(source_decision, source_opportunity)
    quote_shas = {_v3._sha(result.quote.to_dict()) for result in results}
    if quote_shas != {opportunity.quote_sha256}:
        raise CanonicalPortfolioError(
            "selected variants do not share canonical Router quote"
        )
    quote = results[0].quote
    required = (
        opportunity.provider_market_id,
        opportunity.provider_outcome_id,
        opportunity.provider_market_name,
        opportunity.provider_outcome_name,
        opportunity.decimal_odds,
        opportunity.robust_net_expected_value,
        opportunity.quote_sha256,
    )
    if any(value is None for value in required):
        raise CanonicalPortfolioError(
            "selected opportunity omitted exact provider/value ancestry"
        )
    if (
        quote.provider_market_id != opportunity.provider_market_id
        or quote.provider_outcome_id != opportunity.provider_outcome_id
        or quote.provider_specifier != opportunity.provider_specifier
        or quote.source_raw_sha256 != opportunity.source_raw_sha256
        or opportunity.source_current_reconciliation_sha256
        != source.current_reconciliation_sha256
    ):
        raise CanonicalPortfolioError(
            "canonical Router/provider/current reconciliation ancestry differs"
        )

    robust_ev = float(opportunity.robust_net_expected_value)
    if not math.isfinite(robust_ev) or robust_ev <= 0.0:
        raise CanonicalPortfolioError(
            "selected Router opportunity lacks positive robust EV"
        )
    odds = float(opportunity.decimal_odds)
    if not math.isfinite(odds) or odds <= 1.0:
        raise CanonicalPortfolioError(
            "selected Router opportunity lacks valid decimal odds"
        )
    router_age = opportunity.router_quote_age_seconds
    if router_age is None or not math.isfinite(router_age) or router_age < 0:
        raise CanonicalPortfolioError(
            "selected Router opportunity lacks valid Router quote age"
        )
    if age + 1e-9 < router_age:
        raise CanonicalPortfolioError(
            "Portfolio quote age cannot be younger than Router quote age"
        )

    try:
        survival = _v3._survival(source_opportunity, results)
        fragility = _v3._fragility(robust_ev, survival)
    except Exception as exc:
        raise CanonicalPortfolioError(
            "source Portfolio-v3 settlement/fragility policy failed"
        ) from exc

    leg_id = _sha(
        {
            "router_decision_sha256": source.source_router_v3_decision_sha256,
            "opportunity_id": opportunity.opportunity_id,
            "quote_sha256": opportunity.quote_sha256,
            "current_reconciliation_sha256": source.current_reconciliation_sha256,
        }
    )
    return PortfolioLeg(
        leg_id=leg_id,
        canonical_router_decision_sha256=source.canonical_router_decision_sha256,
        source_router_v3_decision_sha256=source.source_router_v3_decision_sha256,
        selected_opportunity_id=opportunity.opportunity_id,
        prediction_identity_sha256=opportunity.prediction_identity_sha256,
        fixture_id=source.fixture_id,
        event_id=source.event_id,
        home_team=source.home_team,
        away_team=source.away_team,
        competition=source.competition,
        kickoff_utc=source.kickoff_utc,
        market_id=opportunity.market_id,
        outcome_id=opportunity.outcome_id,
        line=opportunity.line,
        market_family=MARKET_REGISTRY[opportunity.market_id].family,
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
        portfolio_quote_age_seconds=float(age),
        portfolio_kickoff_lead_seconds=float(lead),
        robust_net_expected_value=robust_ev,
        robust_edge=opportunity.robust_edge,
        event_probability_floor=opportunity.event_probability_floor,
        survival_probability_floor=survival,
        prediction_confidence=float(opportunity.prediction_confidence),
        prediction_confidence_method=opportunity.prediction_confidence_method,
        model_count=len(opportunity.variants),
        fragility_status=fragility,
    )


def _select_candidates(
    candidates: Sequence[PortfolioLeg], *, target_legs: int
) -> tuple[
    tuple[PortfolioLeg, ...],
    tuple[ReserveLeg, ...],
    Mapping[str, int],
]:
    """Apply the reviewed Portfolio-v3 cap/marginal/reserve policy unchanged."""
    caps = _v3._caps(target_legs)
    selected: list[PortfolioLeg] = []
    remaining = sorted(candidates, key=lambda item: item.leg_id)
    while remaining and len(selected) < target_legs:
        eligible = [
            item
            for item in remaining
            if not _v3._constraints(item, selected, caps)
        ]
        if not eligible:
            break
        chosen = min(
            eligible,
            key=lambda item: _v3._marginal(item, selected, caps),
        )
        selected.append(chosen)
        remaining.remove(chosen)

    selected = sorted(selected, key=lambda item: item.leg_id)
    selected_ids = {item.leg_id for item in selected}
    reserve_rows: list[ReserveLeg] = []
    for item in sorted(
        (
            candidate
            for candidate in candidates
            if candidate.leg_id not in selected_ids
        ),
        key=_v3._reserve_key,
    ):
        reasons = list(_v3._constraints(item, selected, caps))
        if len(selected) >= target_legs:
            reasons.append("TARGET_FILLED")
        if not reasons:
            reasons.append("LOWER_MARGINAL_PORTFOLIO_PRIORITY")
        reserve_rows.append(
            ReserveLeg(
                leg=item,
                reserve_reasons=tuple(sorted(set(reasons))),
            )
        )
    return tuple(selected), tuple(reserve_rows), types.MappingProxyType(dict(caps))


def _binding_caps(reserves: Sequence[ReserveLeg]) -> tuple[str, ...]:
    prefixes = (
        "TEAM_EXPOSURE_CAP:",
        "COMPETITION_CONCENTRATION_CAP:",
        "MARKET_FAMILY_CONCENTRATION_CAP:",
    )
    values = {
        reason
        for reserve in reserves
        for reason in reserve.reserve_reasons
        if reason == "FRAGILITY_CAP" or reason.startswith(prefixes)
    }
    return tuple(sorted(values))


def _exposure_summary(
    selected: Sequence[PortfolioLeg], caps: Mapping[str, int]
) -> Mapping[str, Any]:
    teams, competitions, families, fragile = _v3._counts(selected)
    return types.MappingProxyType(
        {
            "caps": dict(caps),
            "team_counts": dict(sorted(teams.items())),
            "competition_counts": dict(sorted(competitions.items())),
            "market_family_counts": dict(sorted(families.items())),
            "fragile_count": fragile,
            "statistical_correlation_coefficients": None,
            "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
        }
    )


def _build(
    router_inputs: Iterable[PortfolioRouterInput],
    *,
    target_legs: int,
    evaluation_time: datetime,
    require_live_current: bool,
) -> SelectedPortfolio:
    identities = validate_portfolio_contract()
    now = _utc(evaluation_time, "evaluation_time")
    if type(target_legs) is not int or not MIN_TARGET_LEGS <= target_legs <= MAX_TARGET_LEGS:
        raise CanonicalPortfolioError(
            f"target_legs must be exact integer {MIN_TARGET_LEGS}..{MAX_TARGET_LEGS}"
        )
    supplied = tuple(router_inputs)
    if any(type(item) is not PortfolioRouterInput for item in supplied):
        raise CanonicalPortfolioError(
            "router_inputs must contain exact PortfolioRouterInput values"
        )
    verified = tuple(verify_portfolio_router_input(item) for item in supplied)
    if len({item.fixture_id for item in verified}) != len(verified):
        raise CanonicalPortfolioError("duplicate fixture input")
    if len({item.event_id for item in verified}) != len(verified):
        raise CanonicalPortfolioError("duplicate provider event input")
    if any(item.router_decision.evaluation_time > now for item in verified):
        raise CanonicalPortfolioError(
            "Portfolio evaluation_time predates a canonical Router decision"
        )
    if require_live_current and any(
        item.router_decision._require_live_current is not True
        or item.router_decision.proof_mode != LIVE_CURRENT
        or item._source_portfolio_input.router_decision.status != _v3.router_v3.STATUS_LIVE
        for item in verified
    ):
        raise CanonicalPortfolioError(
            "live canonical Portfolio requires LIVE_CURRENT canonical/source Router ancestry"
        )

    candidates: list[PortfolioLeg] = []
    audits: list[PortfolioRouteAudit] = []
    for item in sorted(verified, key=lambda value: value.fixture_id):
        decision = item.router_decision
        if decision.decision_status is RouterDecisionStatus.SELECTED:
            try:
                candidates.append(_build_leg(item, now))
                admitted, reasons = True, ()
            except CanonicalPortfolioError as exc:
                admitted, reasons = False, (str(exc),)
        else:
            admitted = False
            reasons = tuple(decision.decision_reasons)
        audits.append(
            PortfolioRouteAudit(
                fixture_id=item.fixture_id,
                event_id=item.event_id,
                canonical_router_decision_sha256=item.canonical_router_decision_sha256,
                source_router_v3_decision_sha256=item.source_router_v3_decision_sha256,
                router_decision_status=decision.decision_status.value,
                selected_opportunity_id=decision.selected_opportunity_id,
                admitted=admitted,
                admission_reasons=tuple(sorted(set(reasons))),
            )
        )

    selected, reserves, caps = _select_candidates(
        candidates, target_legs=target_legs
    )
    shortfall = max(0, target_legs - len(selected))
    optimization_status = (
        PortfolioOptimizationStatus.QUALIFIED_SET
        if selected
        else PortfolioOptimizationStatus.NO_QUALIFIED_LEGS
    )
    try:
        survival = _v3._survival_product(selected)
        odds = _v3._odds_product(selected)
    except Exception as exc:
        raise CanonicalPortfolioError(
            "source Portfolio-v3 aggregate diagnostics failed"
        ) from exc

    value = object.__new__(SelectedPortfolio)
    for name, field in {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "status": STATUS_LIVE if require_live_current else STATUS_AS_OF,
        "proof_mode": LIVE_CURRENT if require_live_current else AS_OF_REPLAY,
        "canonical_portfolio_contract_sha256": identities[
            "canonical_portfolio_contract_sha256"
        ],
        "canonical_router_contract_sha256": CANONICAL_ROUTER_CONTRACT_SHA256,
        "source_portfolio_v3_contract_sha256": SOURCE_PORTFOLIO_V3_CONTRACT_SHA256,
        "evaluation_time": now,
        "target_legs": target_legs,
        "selected_legs": selected,
        "reserve_legs": reserves,
        "route_audits": tuple(sorted(audits, key=lambda item: item.fixture_id)),
        "optimization_status": optimization_status,
        "shortfall": shortfall,
        "expected_slip_survival": survival,
        "combined_decimal_odds_product": odds,
        "exposure_summary": _exposure_summary(selected, caps),
        "binding_caps": _binding_caps(reserves),
        "reserve_policy_id": RESERVE_POLICY_ID,
        "shortfall_policy_id": SHORTFALL_POLICY_ID,
        "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
        "target_total_odds_objective": False,
        "kelly_objective": False,
        "authority": types.MappingProxyType(dict(AUTHORITY)),
        "next_boundary": NEXT_BOUNDARY,
        "_router_inputs": verified,
        "_require_live_current": require_live_current,
    }.items():
        object.__setattr__(value, name, field)
    return value


def optimize_portfolio_as_of(
    router_decisions: Iterable[_router.RouterDecision],
    *,
    target_legs: int,
    evaluation_time: datetime,
) -> SelectedPortfolio:
    """Build a canonical replay portfolio from P1.4 Router decisions."""
    inputs = tuple(
        PortfolioRouterInput.from_router_decision(item)
        for item in router_decisions
    )
    return _build(
        inputs,
        target_legs=target_legs,
        evaluation_time=evaluation_time,
        require_live_current=False,
    )


def optimize_portfolio(
    router_decisions: Iterable[_router.RouterDecision],
    *,
    target_legs: int,
) -> SelectedPortfolio:
    """Build a canonical LIVE_CURRENT portfolio from P1.4 Router decisions."""
    inputs = tuple(
        PortfolioRouterInput.from_router_decision(item)
        for item in router_decisions
    )
    return _build(
        inputs,
        target_legs=target_legs,
        evaluation_time=datetime.now(timezone.utc),
        require_live_current=True,
    )


def verify_selected_portfolio(value: Any) -> SelectedPortfolio:
    """Rebuild from retained canonical Router evidence and reject drift."""
    if type(value) is not SelectedPortfolio:
        raise CanonicalPortfolioError("exact SelectedPortfolio is required")
    rebuilt = _build(
        value._router_inputs,
        target_legs=value.target_legs,
        evaluation_time=value.evaluation_time,
        require_live_current=value._require_live_current,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise CanonicalPortfolioError(
            "SelectedPortfolio differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [
    "AS_OF_REPLAY",
    "AUTHORITY",
    "CANONICAL_ROUTER_CONTRACT_SHA256",
    "CanonicalPortfolioError",
    "EXPECTED_CONTRACT_SHA256",
    "IMPLEMENTATION_ID",
    "JOINT_DEPENDENCE_STATUS",
    "LIVE_CURRENT",
    "MAX_TARGET_LEGS",
    "MIN_TARGET_LEGS",
    "NEXT_BOUNDARY",
    "OUTPUT_CONTRACT",
    "POLICY_ID",
    "PortfolioLeg",
    "PortfolioRouteAudit",
    "PortfolioRouterInput",
    "RESERVE_POLICY_ID",
    "ReserveLeg",
    "SCHEMA_VERSION",
    "SHORTFALL_POLICY_ID",
    "SOURCE_PORTFOLIO_V3_CONTRACT_SHA256",
    "SelectedPortfolio",
    "calculate_portfolio_contract_sha256",
    "optimize_portfolio",
    "optimize_portfolio_as_of",
    "validate_portfolio_contract",
    "verify_portfolio_router_input",
    "verify_selected_portfolio",
]
