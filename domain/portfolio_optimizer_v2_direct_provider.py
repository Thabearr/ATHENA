"""ATHENA Portfolio Optimizer v2 for verified direct-provider Router decisions.

This boundary consumes only exact builder-issued Market Router v2 decisions, replays
and verifies the source-bound full-UTC reconciliation used for exposure identity,
rechecks direct-provider freshness again at portfolio time, and builds a
conservative diversified qualified leg set. Requested size is a target, never a
requirement.

It does not generate football probabilities, recalibrate models, recompute value,
reroute markets, fabricate statistical correlation, construct a SportyBet slip,
stake, execute, or place a wager.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import types
from typing import Any, Iterable, Mapping, Sequence

from domain import market_router_v2_direct_provider as router_v2
from domain import price_all_v2_direct_provider as price_v2
from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as reconciliation_receipt
from domain._market_router_contracts import OpportunityEligibility, RouterDecisionStatus
from domain._portfolio_optimizer_v2_direct_provider_contracts import (
    AUTHORITY,
    CORRELATION_POLICY_ID,
    DATASET_NAME,
    FIXTURE_EXPOSURE_IDENTITY_POLICY_ID,
    FRAGILITY_POLICY_ID,
    FragilityStatus,
    JOINT_DEPENDENCE_STATUS,
    JOINT_SELECTION_POLICY_ID,
    LEGACY_ACCUMULATOR_OPTIMIZER_V2_CONTRACT_SHA256,
    MARKET_ROUTER_V2_CONTRACT_SHA256,
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
    NEXT_BOUNDARY,
    PORTFOLIO_TIME_FRESHNESS_POLICY_ID,
    PortfolioOptimizationStatus,
    PortfolioOptimizerV2DirectProviderError,
    RESERVE_POLICY_ID,
    ROUTER_DECISION_RECONSTRUCTION_POLICY_ID,
    SHORTFALL_POLICY_ID,
    STATUS,
    SURVIVAL_POLICY_ID,
    validate_portfolio_optimizer_v2_contract,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.sportybet_reviewed_canonical_market_mapping import (
    SportyBetReviewedCanonicalMarketMapping,
)

_FULL_SETTLEMENT_MARKETS = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})
_DNB_COMPONENTS = frozenset({"WIN", "PUSH", "LOSS"})
_AH_COMPONENTS = frozenset({"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"})


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PortfolioOptimizerV2DirectProviderError(
            "canonical JSON serialization failed"
        ) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PortfolioOptimizerV2DirectProviderError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PortfolioOptimizerV2DirectProviderError(f"{label} is invalid") from exc


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite_probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortfolioOptimizerV2DirectProviderError(
            f"{label} must be a finite probability"
        )
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise PortfolioOptimizerV2DirectProviderError(
            f"{label} must be within [0,1]"
        )
    return result


def _source_mapping(
    decision: router_v2.MarketRouterV2DirectProviderDecision,
) -> SportyBetReviewedCanonicalMarketMapping:
    try:
        mapping = (
            decision.price_all_evaluation
            ._quote_source
            ._source_bundle
            ._mapping
        )
    except AttributeError as exc:
        raise PortfolioOptimizerV2DirectProviderError(
            "Router v2 decision omitted retained reviewed mapping ancestry"
        ) from exc
    if type(mapping) is not SportyBetReviewedCanonicalMarketMapping:
        raise PortfolioOptimizerV2DirectProviderError(
            "Router v2 retained mapping ancestry has an unexpected type"
        )
    return mapping


@dataclass(frozen=True, init=False)
class DirectProviderPortfolioRouterInput:
    """Builder-only source-bound Router v2 input for one portfolio fixture."""

    router_decision: router_v2.MarketRouterV2DirectProviderDecision
    reconciliation: reconciliation.SportyBetFotMobFullUtcReconciliation
    router_decision_sha256: str
    reconciliation_sha256: str
    reconciliation_identifier: str
    fixture_id: str
    sportybet_event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime
    _receipt_directory: Any
    _source_bundle: reconciliation_receipt.FullUtcReconciliationSourceBundle
    _repository_root: Path

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PortfolioOptimizerV2DirectProviderError(
            "DirectProviderPortfolioRouterInput is builder-only; use "
            "from_source_replayed_receipt()"
        )

    @classmethod
    def from_source_replayed_receipt(
        cls,
        *,
        router_decision: router_v2.MarketRouterV2DirectProviderDecision,
        receipt_directory: Any,
        source_bundle: reconciliation_receipt.FullUtcReconciliationSourceBundle,
        repository_root: Path,
    ) -> "DirectProviderPortfolioRouterInput":
        if type(router_decision) is not router_v2.MarketRouterV2DirectProviderDecision:
            raise PortfolioOptimizerV2DirectProviderError(
                "router_decision must be exact MarketRouterV2DirectProviderDecision"
            )
        if type(source_bundle) is not reconciliation_receipt.FullUtcReconciliationSourceBundle:
            raise PortfolioOptimizerV2DirectProviderError(
                "source_bundle must be exact FullUtcReconciliationSourceBundle"
            )
        if not isinstance(repository_root, Path):
            raise PortfolioOptimizerV2DirectProviderError(
                "repository_root must be a Path"
            )
        try:
            verified_decision = (
                router_v2.verify_market_router_v2_direct_provider_decision(
                    router_decision
                )
            )
        except router_v2.MarketRouterV2DirectProviderError as exc:
            raise PortfolioOptimizerV2DirectProviderError(
                "Router v2 decision reconstruction failed"
            ) from exc

        if (
            verified_decision.dataset_name
            != router_v2.DATASET_NAME
            or verified_decision.status != router_v2.STATUS
            or verified_decision.next_boundary != router_v2.NEXT_BOUNDARY
            or verified_decision.market_router_v2_contract_sha256
            != MARKET_ROUTER_V2_CONTRACT_SHA256
        ):
            raise PortfolioOptimizerV2DirectProviderError(
                "Router v2 decision state is not approved for portfolio consumption"
            )
        if (
            verified_decision.authority.get(
                "verified_direct_provider_value_consumption"
            )
            is not True
            or verified_decision.authority.get("market_routing") is not True
            or verified_decision.authority.get("fixture_market_selection") is not True
            or verified_decision.authority.get("portfolio_optimization") is not False
            or verified_decision.authority.get("bet") is not False
        ):
            raise PortfolioOptimizerV2DirectProviderError(
                "Router v2 authority flags mismatch"
            )

        try:
            rebuilt = reconciliation_receipt.verify_reconciliation_receipt_directory(
                receipt_directory,
                source_bundle=source_bundle,
                repository_root=repository_root,
            )
        except reconciliation_receipt.SportyBetFotMobFullUtcReconciliationReceiptError as exc:
            raise PortfolioOptimizerV2DirectProviderError(
                "source-replayed full-UTC reconciliation receipt verification failed"
            ) from exc
        if (
            rebuilt.disposition
            is not reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
            or rebuilt.fixture_reconciliation_authorized is not True
            or rebuilt.matched_fixture is None
        ):
            raise PortfolioOptimizerV2DirectProviderError(
                "portfolio exposure requires a source-replayed unique exact full-UTC reconciliation"
            )
        try:
            payload = reconciliation.canonical_reconciliation_bytes(rebuilt)
            reconciliation_sha = reconciliation_receipt.receipt_sha256_from_bytes(
                payload
            )
            reconciliation_identifier = (
                reconciliation_receipt.receipt_identifier_from_bytes(payload)
            )
        except Exception as exc:
            raise PortfolioOptimizerV2DirectProviderError(
                "source-replayed reconciliation identity could not be calculated"
            ) from exc

        mapping = _source_mapping(verified_decision)
        if mapping.source_reconciliation_receipt_sha256 != reconciliation_sha:
            raise PortfolioOptimizerV2DirectProviderError(
                "source-replayed reconciliation SHA does not match Router direct-provider ancestry"
            )
        matched = rebuilt.matched_fixture
        if (
            verified_decision.fixture_id != matched.source_fixture_identifier
            or verified_decision.sportybet_event_id != rebuilt.sportybet_event_id
            or mapping.matched_fotmob_fixture_id != verified_decision.fixture_id
            or mapping.sportybet_event_id != verified_decision.sportybet_event_id
        ):
            raise PortfolioOptimizerV2DirectProviderError(
                "Router/mapping/reconciliation fixture or event identity mismatch"
            )
        kickoff = _utc(rebuilt.sportybet_kickoff_utc, "reconciliation kickoff")
        if (
            kickoff != _utc(verified_decision.kickoff_utc, "Router kickoff")
            or kickoff
            != _utc(
                verified_decision.price_all_evaluation.kickoff_utc,
                "Price-all kickoff",
            )
        ):
            raise PortfolioOptimizerV2DirectProviderError(
                "Router/Price-all/reconciliation kickoff identity mismatch"
            )
        if (
            verified_decision.source_quote_source_sha256
            != verified_decision.price_all_evaluation.source_quote_source_sha256
            or verified_decision.source_bundle_sha256
            != verified_decision.price_all_evaluation.source_bundle_sha256
        ):
            raise PortfolioOptimizerV2DirectProviderError(
                "Router source identity differs from retained Price-all evaluation"
            )

        instance = object.__new__(cls)
        values = {
            "router_decision": verified_decision,
            "reconciliation": rebuilt,
            "router_decision_sha256": verified_decision.canonical_sha256,
            "reconciliation_sha256": reconciliation_sha,
            "reconciliation_identifier": reconciliation_identifier,
            "fixture_id": verified_decision.fixture_id,
            "sportybet_event_id": verified_decision.sportybet_event_id,
            "home_team": matched.home_team,
            "away_team": matched.away_team,
            "competition": matched.competition,
            "kickoff_utc": kickoff,
            "_receipt_directory": receipt_directory,
            "_source_bundle": source_bundle,
            "_repository_root": repository_root,
        }
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        return instance

    def to_dict(self) -> dict[str, Any]:
        return {
            "router_decision_sha256": self.router_decision_sha256,
            "reconciliation_sha256": self.reconciliation_sha256,
            "reconciliation_identifier": self.reconciliation_identifier,
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": _iso(self.kickoff_utc),
        }


def verify_direct_provider_portfolio_router_input(
    value: DirectProviderPortfolioRouterInput,
) -> DirectProviderPortfolioRouterInput:
    if type(value) is not DirectProviderPortfolioRouterInput:
        raise PortfolioOptimizerV2DirectProviderError(
            "value must be exact DirectProviderPortfolioRouterInput"
        )
    rebuilt = DirectProviderPortfolioRouterInput.from_source_replayed_receipt(
        router_decision=value.router_decision,
        receipt_directory=value._receipt_directory,
        source_bundle=value._source_bundle,
        repository_root=value._repository_root,
    )
    if (
        rebuilt.to_dict() != value.to_dict()
        or rebuilt.router_decision.to_dict() != value.router_decision.to_dict()
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "portfolio Router input differs from exact source reconstruction"
        )
    return rebuilt


@dataclass(frozen=True)
class DirectProviderPortfolioLeg:
    leg_id: str
    router_decision_sha256: str
    selected_opportunity_id: str
    fixture_id: str
    sportybet_event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime
    market_id: MarketId
    outcome_id: OutcomeId
    line: float | None
    market_family: MarketFamily
    quote_identity_sha256: str
    provider_market_id: str
    provider_outcome_id: str
    provider_specifier: str | None
    source_quote_source_sha256: str
    source_bundle_sha256: str
    source_raw_sha256: str
    reviewed_mapping_sha256: str
    fixture_reconciliation_sha256: str
    decimal_odds: float
    router_quote_age_seconds: float
    portfolio_quote_age_seconds: float
    portfolio_kickoff_lead_seconds: float
    robust_net_expected_value: float
    robust_edge: float | None
    calibrated_event_probability_floor: float | None
    survival_probability_floor: float
    model_count: int
    fragility_status: FragilityStatus

    @property
    def fragile(self) -> bool:
        return self.fragility_status is not FragilityStatus.NON_FRAGILE

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg_id": self.leg_id,
            "router_decision_sha256": self.router_decision_sha256,
            "selected_opportunity_id": self.selected_opportunity_id,
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
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
            "provider_outcome_id": self.provider_outcome_id,
            "provider_specifier": self.provider_specifier,
            "source_quote_source_sha256": self.source_quote_source_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "reviewed_mapping_sha256": self.reviewed_mapping_sha256,
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "decimal_odds": self.decimal_odds,
            "router_quote_age_seconds": self.router_quote_age_seconds,
            "portfolio_quote_age_seconds": self.portfolio_quote_age_seconds,
            "portfolio_kickoff_lead_seconds": self.portfolio_kickoff_lead_seconds,
            "robust_net_expected_value": self.robust_net_expected_value,
            "robust_edge": self.robust_edge,
            "calibrated_event_probability_floor": (
                self.calibrated_event_probability_floor
            ),
            "survival_probability_floor": self.survival_probability_floor,
            "model_count": self.model_count,
            "fragility_status": self.fragility_status.value,
            "fragile": self.fragile,
        }


@dataclass(frozen=True)
class DirectProviderPortfolioRouteAudit:
    fixture_id: str
    sportybet_event_id: str
    router_decision_sha256: str
    router_decision_status: str
    router_decision_reasons: tuple[str, ...]
    selected_opportunity_id: str | None
    portfolio_source_age_seconds: float
    portfolio_kickoff_lead_seconds: float
    portfolio_admitted: bool
    portfolio_admission_reasons: tuple[str, ...]
    router_decision: router_v2.MarketRouterV2DirectProviderDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
            "router_decision_sha256": self.router_decision_sha256,
            "router_decision_status": self.router_decision_status,
            "router_decision_reasons": list(self.router_decision_reasons),
            "selected_opportunity_id": self.selected_opportunity_id,
            "portfolio_source_age_seconds": self.portfolio_source_age_seconds,
            "portfolio_kickoff_lead_seconds": self.portfolio_kickoff_lead_seconds,
            "portfolio_admitted": self.portfolio_admitted,
            "portfolio_admission_reasons": list(self.portfolio_admission_reasons),
            "router_decision": self.router_decision.to_dict(),
        }


@dataclass(frozen=True)
class DirectProviderReserveLeg:
    leg: DirectProviderPortfolioLeg
    reserve_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg": self.leg.to_dict(),
            "reserve_reasons": list(self.reserve_reasons),
        }


@dataclass(frozen=True, init=False)
class DirectProviderPortfolioOptimization:
    dataset_name: str
    status: str
    portfolio_optimizer_v2_contract_sha256: str
    market_router_v2_contract_sha256: str
    legacy_accumulator_optimizer_v2_contract_sha256: str
    evaluation_time: datetime
    requested_target_size: int
    selected_legs: tuple[DirectProviderPortfolioLeg, ...]
    reserve_legs: tuple[DirectProviderReserveLeg, ...]
    route_audits: tuple[DirectProviderPortfolioRouteAudit, ...]
    optimization_status: PortfolioOptimizationStatus
    shortfall: int
    expected_slip_survival: float | None
    expected_slip_survival_method: str
    correlation_adjusted_expected_slip_survival: None
    combined_decimal_odds_product: float | None
    exposure_summary: Mapping[str, Any]
    flagged_exposure_pairs: tuple[Mapping[str, Any], ...]
    authority: Mapping[str, bool]
    next_boundary: str
    _router_inputs: tuple[DirectProviderPortfolioRouterInput, ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PortfolioOptimizerV2DirectProviderError(
            "portfolio optimizations are issued only by verified direct-provider optimization"
        )

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    @property
    def optimization_id(self) -> str:
        return self.canonical_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "portfolio_optimizer_v2_contract_sha256": (
                self.portfolio_optimizer_v2_contract_sha256
            ),
            "market_router_v2_contract_sha256": self.market_router_v2_contract_sha256,
            "legacy_accumulator_optimizer_v2_contract_sha256": (
                self.legacy_accumulator_optimizer_v2_contract_sha256
            ),
            "evaluation_time": _iso(self.evaluation_time),
            "requested_target_size": self.requested_target_size,
            "selected_legs": [item.to_dict() for item in self.selected_legs],
            "reserve_legs": [item.to_dict() for item in self.reserve_legs],
            "route_audits": [item.to_dict() for item in self.route_audits],
            "optimization_status": self.optimization_status.value,
            "shortfall": self.shortfall,
            "fulfilled": self.fulfilled,
            "expected_slip_survival": self.expected_slip_survival,
            "expected_slip_survival_method": self.expected_slip_survival_method,
            "correlation_adjusted_expected_slip_survival": None,
            "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
            "combined_decimal_odds_product": self.combined_decimal_odds_product,
            "exposure_summary": dict(self.exposure_summary),
            "flagged_exposure_pairs": [
                dict(item) for item in self.flagged_exposure_pairs
            ],
            "router_decision_reconstruction_policy_id": (
                ROUTER_DECISION_RECONSTRUCTION_POLICY_ID
            ),
            "fixture_exposure_identity_policy_id": (
                FIXTURE_EXPOSURE_IDENTITY_POLICY_ID
            ),
            "portfolio_time_freshness_policy_id": (
                PORTFOLIO_TIME_FRESHNESS_POLICY_ID
            ),
            "joint_selection_policy_id": JOINT_SELECTION_POLICY_ID,
            "correlation_policy_id": CORRELATION_POLICY_ID,
            "survival_policy_id": SURVIVAL_POLICY_ID,
            "fragility_policy_id": FRAGILITY_POLICY_ID,
            "reserve_policy_id": RESERVE_POLICY_ID,
            "shortfall_policy_id": SHORTFALL_POLICY_ID,
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _selected_results(
    decision: router_v2.MarketRouterV2DirectProviderDecision,
    opportunity: router_v2.DirectProviderRoutedOpportunity,
) -> tuple[price_v2.PriceAllV2DirectProviderResult, ...]:
    variant_by_candidate = {item.candidate_id: item for item in opportunity.variants}
    results = tuple(
        item
        for item in decision.price_all_evaluation.results
        if item.candidate.candidate_id in variant_by_candidate
    )
    if len(results) != len(variant_by_candidate):
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router opportunity does not retain every contributing Price-all v2 result"
        )
    ordered = tuple(sorted(results, key=lambda item: item.candidate.candidate_id))
    for item in ordered:
        variant = variant_by_candidate[item.candidate.candidate_id]
        if item.canonical_sha256 != variant.price_all_v2_result_sha256:
            raise PortfolioOptimizerV2DirectProviderError(
                "selected Router variant differs from retained Price-all v2 result identity"
            )
        if (
            item.disposition is not price_v2.DirectProviderPriceDisposition.PRICED
            or item.quote is None
        ):
            raise PortfolioOptimizerV2DirectProviderError(
                "selected Router opportunity contains an unpriced Price-all v2 variant"
            )
    return ordered


def _survival_floor(
    opportunity: router_v2.DirectProviderRoutedOpportunity,
    results: Sequence[price_v2.PriceAllV2DirectProviderResult],
) -> float:
    if opportunity.market_id not in _FULL_SETTLEMENT_MARKETS:
        if opportunity.calibrated_event_probability_floor is None:
            raise PortfolioOptimizerV2DirectProviderError(
                "selected ordinary opportunity lacks calibrated event-probability floor"
            )
        return _finite_probability(
            opportunity.calibrated_event_probability_floor,
            "selected opportunity event-probability floor",
        )

    values: list[float] = []
    for item in results:
        probabilities = dict(item.candidate.settlement_probabilities)
        components = frozenset(probabilities)
        if opportunity.market_id is MarketId.DRAW_NO_BET:
            if components != _DNB_COMPONENTS:
                raise PortfolioOptimizerV2DirectProviderError(
                    "DNB settlement components drifted"
                )
            survival = probabilities["WIN"] + probabilities["PUSH"]
        else:
            if components != _AH_COMPONENTS:
                raise PortfolioOptimizerV2DirectProviderError(
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
        raise PortfolioOptimizerV2DirectProviderError(
            "selected full-settlement opportunity has no model variants"
        )
    return min(values)


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


def _portfolio_freshness(
    decision: router_v2.MarketRouterV2DirectProviderDecision,
    now: datetime,
) -> tuple[float, float, tuple[str, ...]]:
    source_observed = _utc(decision.source_observed_at, "Router source_observed_at")
    kickoff = _utc(decision.kickoff_utc, "Router kickoff")
    source_age = (now - source_observed).total_seconds()
    kickoff_lead = (kickoff - now).total_seconds()
    if not math.isfinite(source_age) or source_age < 0:
        raise PortfolioOptimizerV2DirectProviderError(
            "direct-provider source observation is future-dated at portfolio time"
        )
    if not math.isfinite(kickoff_lead):
        raise PortfolioOptimizerV2DirectProviderError(
            "portfolio kickoff lead is invalid"
        )
    reasons: list[str] = []
    if source_age > decision.max_quote_age_seconds:
        reasons.append(
            "direct-provider source exceeds the effective Router/Price-all maximum quote age at portfolio time"
        )
    if kickoff_lead <= decision.minimum_lead_seconds:
        reasons.append(
            "direct-provider source is too close to kickoff at portfolio time"
        )
    return source_age, kickoff_lead, tuple(sorted(set(reasons)))


def _build_portfolio_leg(
    source: DirectProviderPortfolioRouterInput,
    *,
    now: datetime,
    portfolio_quote_age_seconds: float,
    portfolio_kickoff_lead_seconds: float,
) -> DirectProviderPortfolioLeg:
    decision = source.router_decision
    opportunity = decision.selected_opportunity
    if (
        decision.decision_status is not RouterDecisionStatus.SELECTED
        or opportunity is None
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "only a Router v2 SELECTED decision can become a portfolio leg"
        )
    if (
        opportunity.eligibility is not OpportunityEligibility.ELIGIBLE
        or opportunity.route_source_freshness_passed is not True
        or decision.route_source_freshness_passed is not True
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router v2 opportunity is not eligible and source-fresh"
        )
    results = _selected_results(decision, opportunity)
    quote_hashes = {_sha(item.quote.to_dict()) for item in results if item.quote is not None}
    if len(quote_hashes) != 1:
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router opportunity variants do not share one exact direct-provider quote"
        )
    quote_identity = next(iter(quote_hashes))
    if opportunity.quote_identity_sha256 != quote_identity:
        raise PortfolioOptimizerV2DirectProviderError(
            "Router opportunity quote identity differs from retained Price-all v2 quote"
        )
    quotes = tuple(item.quote for item in results if item.quote is not None)
    quote = quotes[0]
    if any(
        item.fixture_reconciliation_sha256 != source.reconciliation_sha256
        for item in quotes
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "selected direct-provider quote ancestry does not bind source-replayed reconciliation"
        )
    if (
        opportunity.fixture_reconciliation_sha256 != source.reconciliation_sha256
        or opportunity.source_quote_source_sha256
        != decision.source_quote_source_sha256
        or opportunity.source_bundle_sha256 != decision.source_bundle_sha256
        or opportunity.source_raw_sha256 is None
        or opportunity.reviewed_mapping_sha256 is None
        or opportunity.provider_market_id is None
        or opportunity.provider_outcome_id is None
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router opportunity omitted exact direct-provider provenance"
        )
    if (
        quote.provider_market_id != opportunity.provider_market_id
        or quote.provider_outcome_id != opportunity.provider_outcome_id
        or quote.provider_specifier != opportunity.provider_specifier
        or quote.source_raw_sha256 != opportunity.source_raw_sha256
        or quote.reviewed_mapping_sha256 != opportunity.reviewed_mapping_sha256
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router provider identity differs from retained direct-provider quote"
        )

    robust_ev = opportunity.robust_net_expected_value
    if robust_ev is None or not math.isfinite(robust_ev) or robust_ev <= 0.0:
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router opportunity lacks positive robust EV"
        )
    odds = opportunity.decimal_odds
    if odds is None or not math.isfinite(odds) or odds <= 1.0:
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router opportunity lacks valid decimal odds"
        )
    router_age = opportunity.router_quote_age_seconds
    if router_age is None or not math.isfinite(router_age) or router_age < 0:
        raise PortfolioOptimizerV2DirectProviderError(
            "selected Router opportunity lacks valid Router quote age"
        )
    if portfolio_quote_age_seconds + 1e-9 < router_age:
        raise PortfolioOptimizerV2DirectProviderError(
            "portfolio quote age cannot be younger than reviewed Router quote age"
        )
    survival = _survival_floor(opportunity, results)
    family = MARKET_REGISTRY[opportunity.market_id].family

    leg_payload = {
        "router_decision_sha256": decision.canonical_sha256,
        "selected_opportunity_id": opportunity.opportunity_id,
        "quote_identity_sha256": quote_identity,
        "source_quote_source_sha256": opportunity.source_quote_source_sha256,
        "source_bundle_sha256": opportunity.source_bundle_sha256,
        "fixture_reconciliation_sha256": source.reconciliation_sha256,
    }
    return DirectProviderPortfolioLeg(
        leg_id=_sha(leg_payload),
        router_decision_sha256=decision.canonical_sha256,
        selected_opportunity_id=opportunity.opportunity_id,
        fixture_id=decision.fixture_id,
        sportybet_event_id=decision.sportybet_event_id,
        home_team=source.home_team,
        away_team=source.away_team,
        competition=source.competition,
        kickoff_utc=source.kickoff_utc,
        market_id=opportunity.market_id,
        outcome_id=opportunity.outcome_id,
        line=opportunity.line,
        market_family=family,
        quote_identity_sha256=quote_identity,
        provider_market_id=opportunity.provider_market_id,
        provider_outcome_id=opportunity.provider_outcome_id,
        provider_specifier=opportunity.provider_specifier,
        source_quote_source_sha256=opportunity.source_quote_source_sha256,
        source_bundle_sha256=opportunity.source_bundle_sha256,
        source_raw_sha256=opportunity.source_raw_sha256,
        reviewed_mapping_sha256=opportunity.reviewed_mapping_sha256,
        fixture_reconciliation_sha256=source.reconciliation_sha256,
        decimal_odds=float(odds),
        router_quote_age_seconds=float(router_age),
        portfolio_quote_age_seconds=float(portfolio_quote_age_seconds),
        portfolio_kickoff_lead_seconds=float(portfolio_kickoff_lead_seconds),
        robust_net_expected_value=float(robust_ev),
        robust_edge=opportunity.robust_edge,
        calibrated_event_probability_floor=(
            opportunity.calibrated_event_probability_floor
        ),
        survival_probability_floor=survival,
        model_count=len(opportunity.variants),
        fragility_status=_fragility(float(robust_ev), survival),
    )


def _target_cap(target: int, share: float, minimum_when_multi: int) -> int:
    if target == 1:
        return 1
    return min(target, max(minimum_when_multi, int(math.ceil(target * share))))


def _caps(target: int) -> dict[str, int]:
    return {
        "team": MAXIMUM_TEAM_APPEARANCES,
        "competition": _target_cap(
            target,
            MAXIMUM_COMPETITION_SHARE,
            MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2,
        ),
        "market_family": _target_cap(
            target,
            MAXIMUM_MARKET_FAMILY_SHARE,
            MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2,
        ),
        "fragile": min(
            target,
            max(
                MINIMUM_FRAGILE_CAP,
                int(math.ceil(target * MAXIMUM_FRAGILE_SHARE)),
            ),
        ),
    }


def _counts(
    selected: Sequence[DirectProviderPortfolioLeg],
) -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
    team: dict[str, int] = {}
    competition: dict[str, int] = {}
    family: dict[str, int] = {}
    fragile = 0
    for item in selected:
        for name in (item.home_team, item.away_team):
            team[name] = team.get(name, 0) + 1
        competition[item.competition] = competition.get(item.competition, 0) + 1
        family[item.market_family.value] = family.get(item.market_family.value, 0) + 1
        fragile += int(item.fragile)
    return team, competition, family, fragile


def _constraint_reasons(
    candidate: DirectProviderPortfolioLeg,
    selected: Sequence[DirectProviderPortfolioLeg],
    caps: Mapping[str, int],
) -> tuple[str, ...]:
    team, competition, family, fragile = _counts(selected)
    reasons: list[str] = []
    for name in (candidate.home_team, candidate.away_team):
        if team.get(name, 0) >= caps["team"]:
            reasons.append(f"TEAM_EXPOSURE_CAP:{name}")
    if competition.get(candidate.competition, 0) >= caps["competition"]:
        reasons.append(f"COMPETITION_CONCENTRATION_CAP:{candidate.competition}")
    if family.get(candidate.market_family.value, 0) >= caps["market_family"]:
        reasons.append(
            f"MARKET_FAMILY_CONCENTRATION_CAP:{candidate.market_family.value}"
        )
    if candidate.fragile and fragile >= caps["fragile"]:
        reasons.append("FRAGILITY_CAP")
    return tuple(sorted(set(reasons)))


def _marginal_key(
    candidate: DirectProviderPortfolioLeg,
    selected: Sequence[DirectProviderPortfolioLeg],
    caps: Mapping[str, int],
) -> tuple[Any, ...]:
    _team, competition, family, fragile = _counts(selected)
    exposure_penalty = (
        competition.get(candidate.competition, 0) / caps["competition"]
        + family.get(candidate.market_family.value, 0) / caps["market_family"]
        + ((fragile / caps["fragile"]) if candidate.fragile else 0.0)
    )
    edge_present = candidate.robust_edge is not None
    return (
        exposure_penalty,
        -candidate.survival_probability_floor,
        -candidate.robust_net_expected_value,
        0 if edge_present else 1,
        -(candidate.robust_edge if candidate.robust_edge is not None else 0.0),
        candidate.portfolio_quote_age_seconds,
        candidate.leg_id,
    )


def _reserve_key(candidate: DirectProviderPortfolioLeg) -> tuple[Any, ...]:
    edge_present = candidate.robust_edge is not None
    return (
        -candidate.survival_probability_floor,
        -candidate.robust_net_expected_value,
        0 if edge_present else 1,
        -(candidate.robust_edge if candidate.robust_edge is not None else 0.0),
        candidate.portfolio_quote_age_seconds,
        candidate.leg_id,
    )


def _exposure_summary(
    selected: Sequence[DirectProviderPortfolioLeg],
    caps: Mapping[str, int],
) -> Mapping[str, Any]:
    team, competition, family, fragile = _counts(selected)
    return types.MappingProxyType(
        {
            "caps": dict(caps),
            "team_counts": dict(sorted(team.items())),
            "competition_counts": dict(sorted(competition.items())),
            "market_family_counts": dict(sorted(family.items())),
            "fragile_count": fragile,
            "statistical_correlation_coefficients": None,
            "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
        }
    )


def _flagged_pairs(
    selected: Sequence[DirectProviderPortfolioLeg],
) -> tuple[Mapping[str, Any], ...]:
    flags: list[Mapping[str, Any]] = []
    ordered = sorted(selected, key=lambda item: item.leg_id)
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            shared_teams = tuple(
                sorted(
                    {left.home_team, left.away_team}
                    & {right.home_team, right.away_team}
                )
            )
            same_competition = left.competition == right.competition
            same_family = left.market_family is right.market_family
            if shared_teams or same_competition or same_family:
                flags.append(
                    types.MappingProxyType(
                        {
                            "left_leg_id": left.leg_id,
                            "right_leg_id": right.leg_id,
                            "shared_teams": list(shared_teams),
                            "same_competition": same_competition,
                            "same_market_family": same_family,
                            "statistical_correlation": None,
                        }
                    )
                )
    return tuple(flags)


def _survival_product(
    selected: Sequence[DirectProviderPortfolioLeg],
) -> float | None:
    if not selected:
        return None
    result = math.prod(item.survival_probability_floor for item in selected)
    if not math.isfinite(result):
        raise PortfolioOptimizerV2DirectProviderError(
            "independence survival baseline is non-finite"
        )
    return result


def _odds_product(
    selected: Sequence[DirectProviderPortfolioLeg],
) -> float | None:
    if not selected:
        return None
    value = Decimal("1")
    for item in selected:
        value *= Decimal(str(item.decimal_odds))
    result = float(value)
    return result if math.isfinite(result) else None


def optimize_direct_provider_portfolio(
    router_inputs: Iterable[DirectProviderPortfolioRouterInput],
    *,
    target_size: int,
    evaluation_time: datetime,
) -> DirectProviderPortfolioOptimization:
    """Build a disciplined portfolio from verified Router v2 decisions.

    Router NO_BET decisions are never overridden. A Router SELECTED decision can
    only be removed by stricter downstream checks such as portfolio-time source
    freshness or hard exposure caps. Requested size is a target only.
    """
    identities = validate_portfolio_optimizer_v2_contract()
    now = _utc(evaluation_time, "evaluation_time")
    if isinstance(target_size, bool) or not isinstance(target_size, int):
        raise TypeError("target_size must be an integer")
    if target_size < 1 or target_size > MAXIMUM_TARGET_SIZE:
        raise ValueError(
            f"target_size must be between 1 and {MAXIMUM_TARGET_SIZE}"
        )

    values = tuple(router_inputs)
    if any(type(item) is not DirectProviderPortfolioRouterInput for item in values):
        raise PortfolioOptimizerV2DirectProviderError(
            "router_inputs must contain exact DirectProviderPortfolioRouterInput values"
        )
    verified_inputs = tuple(
        verify_direct_provider_portfolio_router_input(item) for item in values
    )
    fixture_ids = [item.fixture_id for item in verified_inputs]
    event_ids = [item.sportybet_event_id for item in verified_inputs]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise PortfolioOptimizerV2DirectProviderError(
            "duplicate fixture inputs are not allowed"
        )
    if len(event_ids) != len(set(event_ids)):
        raise PortfolioOptimizerV2DirectProviderError(
            "duplicate SportyBet event inputs are not allowed"
        )

    admitted_legs: list[DirectProviderPortfolioLeg] = []
    audits: list[DirectProviderPortfolioRouteAudit] = []
    for item in sorted(verified_inputs, key=lambda value: value.fixture_id):
        decision = item.router_decision
        if decision.evaluation_time > now:
            raise PortfolioOptimizerV2DirectProviderError(
                "portfolio evaluation_time predates a Router v2 decision"
            )
        source_age, kickoff_lead, freshness_reasons = _portfolio_freshness(
            decision, now
        )
        admission_reasons: list[str] = []
        leg: DirectProviderPortfolioLeg | None = None
        if decision.decision_status is RouterDecisionStatus.SELECTED:
            if freshness_reasons:
                admission_reasons.extend(freshness_reasons)
            else:
                try:
                    leg = _build_portfolio_leg(
                        item,
                        now=now,
                        portfolio_quote_age_seconds=source_age,
                        portfolio_kickoff_lead_seconds=kickoff_lead,
                    )
                except PortfolioOptimizerV2DirectProviderError as exc:
                    admission_reasons.append(str(exc))
        else:
            admission_reasons.extend(decision.decision_reasons)

        if leg is not None:
            admitted_legs.append(leg)
        audits.append(
            DirectProviderPortfolioRouteAudit(
                fixture_id=decision.fixture_id,
                sportybet_event_id=decision.sportybet_event_id,
                router_decision_sha256=decision.canonical_sha256,
                router_decision_status=decision.decision_status.value,
                router_decision_reasons=decision.decision_reasons,
                selected_opportunity_id=decision.selected_opportunity_id,
                portfolio_source_age_seconds=source_age,
                portfolio_kickoff_lead_seconds=kickoff_lead,
                portfolio_admitted=leg is not None,
                portfolio_admission_reasons=tuple(
                    sorted(set(admission_reasons))
                ),
                router_decision=decision,
            )
        )

    caps = _caps(target_size)
    remaining = sorted(admitted_legs, key=lambda item: item.leg_id)
    selected: list[DirectProviderPortfolioLeg] = []
    while remaining and len(selected) < target_size:
        admissible = [
            item
            for item in remaining
            if not _constraint_reasons(item, selected, caps)
        ]
        if not admissible:
            break
        chosen = min(
            admissible,
            key=lambda item: _marginal_key(item, selected, caps),
        )
        selected.append(chosen)
        remaining = [item for item in remaining if item.leg_id != chosen.leg_id]

    selected = sorted(selected, key=lambda item: item.leg_id)
    selected_ids = {item.leg_id for item in selected}
    reserve_rows: list[DirectProviderReserveLeg] = []
    for item in sorted(
        (
            candidate
            for candidate in admitted_legs
            if candidate.leg_id not in selected_ids
        ),
        key=_reserve_key,
    ):
        reasons = list(_constraint_reasons(item, selected, caps))
        if len(selected) >= target_size:
            reasons.append("TARGET_FILLED")
        if not reasons:
            reasons.append("LOWER_MARGINAL_PORTFOLIO_PRIORITY")
        reserve_rows.append(
            DirectProviderReserveLeg(
                item,
                tuple(sorted(set(reasons))),
            )
        )

    shortfall = max(0, target_size - len(selected))
    optimization_status = (
        PortfolioOptimizationStatus.QUALIFIED_SET
        if selected
        else PortfolioOptimizationStatus.NO_QUALIFIED_LEGS
    )
    value = object.__new__(DirectProviderPortfolioOptimization)
    return _set_frozen(
        value,
        {
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "portfolio_optimizer_v2_contract_sha256": identities[
                "portfolio_optimizer_v2_contract_sha256"
            ],
            "market_router_v2_contract_sha256": identities[
                "market_router_v2_contract_sha256"
            ],
            "legacy_accumulator_optimizer_v2_contract_sha256": identities[
                "legacy_accumulator_optimizer_v2_contract_sha256"
            ],
            "evaluation_time": now,
            "requested_target_size": target_size,
            "selected_legs": tuple(selected),
            "reserve_legs": tuple(reserve_rows),
            "route_audits": tuple(
                sorted(audits, key=lambda item: item.fixture_id)
            ),
            "optimization_status": optimization_status,
            "shortfall": shortfall,
            "expected_slip_survival": _survival_product(selected),
            "expected_slip_survival_method": (
                "CONSERVATIVE_WORST_MODEL_NON_NEGATIVE_SETTLEMENT_INDEPENDENCE_"
                "BASELINE;NOT_A_CORRELATION_ADJUSTED_JOINT_PROBABILITY"
            ),
            "correlation_adjusted_expected_slip_survival": None,
            "combined_decimal_odds_product": _odds_product(selected),
            "exposure_summary": _exposure_summary(selected, caps),
            "flagged_exposure_pairs": _flagged_pairs(selected),
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_router_inputs": verified_inputs,
        },
    )


def verify_direct_provider_portfolio_optimization(
    value: DirectProviderPortfolioOptimization,
) -> DirectProviderPortfolioOptimization:
    """Rebuild an optimization from its exact retained Router/source inputs."""
    if type(value) is not DirectProviderPortfolioOptimization:
        raise PortfolioOptimizerV2DirectProviderError(
            "value must be exact DirectProviderPortfolioOptimization"
        )
    rebuilt = optimize_direct_provider_portfolio(
        value._router_inputs,
        target_size=value.requested_target_size,
        evaluation_time=value.evaluation_time,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise PortfolioOptimizerV2DirectProviderError(
            "portfolio optimization differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
