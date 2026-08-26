"""ATHENA Phase 9 correlation-aware Accumulator Optimizer v2.

The authoritative boundary replays Phase 8 for every supplied fixture from the
exact builder-issued Phase 6/7 inputs before any portfolio leg can exist.  It
then selects a diversified qualified set, may return a requested-size shortfall,
and preserves reserves.  It does not construct a bookmaker slip or authorize a
bet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain._accumulator_optimizer_contracts import (
    AUTHORITY_FLAGS,
    CORRELATION_POLICY_ID,
    FRAGILITY_POLICY_ID,
    JOINT_DEPENDENCE_STATUS,
    JOINT_SELECTION_POLICY_ID,
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
    RESERVE_POLICY_ID,
    SHORTFALL_POLICY_ID,
    SURVIVAL_POLICY_ID,
    AccumulatorOptimizationStatus,
    AccumulatorOptimizerError,
    FragilityStatus,
    validate_accumulator_optimizer_contract,
)
from domain._market_router_contracts import RouterDecisionStatus
from domain._price_all_contracts import (
    CalibratedValueCandidate,
    PriceDisposition,
    SportyBetExactQuote,
)
from domain.fixture_state_v2 import FixtureStateV2Snapshot
from domain.market_router import MarketRouterDecision, RoutedOpportunity, route_market_candidates
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId

_FULL_SETTLEMENT_MARKETS = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})
_DNB_COMPONENTS = frozenset({"WIN", "PUSH", "LOSS"})
_AH_COMPONENTS = frozenset({"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"})


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise AccumulatorOptimizerError("evaluation_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite_probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AccumulatorOptimizerError(f"{label} must be a finite probability")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise AccumulatorOptimizerError(f"{label} must be within [0,1]")
    return result


@dataclass(frozen=True)
class AccumulatorFixtureInput:
    """Exact upstream objects required to replay one fixture through Phase 8."""

    candidates: tuple[CalibratedValueCandidate, ...]
    quotes: tuple[SportyBetExactQuote, ...]
    fixture_state: FixtureStateV2Snapshot
    reconciliation: reconciliation.SportyBetFotMobFullUtcReconciliation

    def __post_init__(self) -> None:
        if type(self.candidates) is not tuple or any(
            type(item) is not CalibratedValueCandidate for item in self.candidates
        ):
            raise AccumulatorOptimizerError("candidates must be an exact tuple of Phase 6 candidates")
        if type(self.quotes) is not tuple or any(
            type(item) is not SportyBetExactQuote for item in self.quotes
        ):
            raise AccumulatorOptimizerError("quotes must be an exact tuple of source-issued quotes")
        if type(self.fixture_state) is not FixtureStateV2Snapshot:
            raise AccumulatorOptimizerError("fixture_state must be exact FixtureStateV2Snapshot")
        if type(self.reconciliation) is not reconciliation.SportyBetFotMobFullUtcReconciliation:
            raise AccumulatorOptimizerError(
                "reconciliation must be exact SportyBetFotMobFullUtcReconciliation"
            )


@dataclass(frozen=True)
class PortfolioLeg:
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
    reconciliation_sha256: str
    decimal_odds: float
    quote_age_seconds: float
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
            "reconciliation_sha256": self.reconciliation_sha256,
            "decimal_odds": self.decimal_odds,
            "quote_age_seconds": self.quote_age_seconds,
            "robust_net_expected_value": self.robust_net_expected_value,
            "robust_edge": self.robust_edge,
            "calibrated_event_probability_floor": self.calibrated_event_probability_floor,
            "survival_probability_floor": self.survival_probability_floor,
            "model_count": self.model_count,
            "fragility_status": self.fragility_status.value,
            "fragile": self.fragile,
        }


@dataclass(frozen=True)
class FixtureRouteAudit:
    fixture_id: str
    sportybet_event_id: str | None
    router_decision_sha256: str
    router_decision_status: str
    router_decision_reasons: tuple[str, ...]
    selected_opportunity_id: str | None
    portfolio_admitted: bool
    portfolio_admission_reasons: tuple[str, ...]
    router_decision: MarketRouterDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
            "router_decision_sha256": self.router_decision_sha256,
            "router_decision_status": self.router_decision_status,
            "router_decision_reasons": list(self.router_decision_reasons),
            "selected_opportunity_id": self.selected_opportunity_id,
            "portfolio_admitted": self.portfolio_admitted,
            "portfolio_admission_reasons": list(self.portfolio_admission_reasons),
            "router_decision": self.router_decision.to_dict(),
        }


@dataclass(frozen=True)
class ReserveLeg:
    leg: PortfolioLeg
    reserve_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg": self.leg.to_dict(),
            "reserve_reasons": list(self.reserve_reasons),
        }


@dataclass(frozen=True)
class AccumulatorOptimization:
    accumulator_optimizer_contract_sha256: str
    market_router_contract_sha256: str
    evaluation_time: datetime
    requested_target_size: int
    selected_legs: tuple[PortfolioLeg, ...]
    reserve_legs: tuple[ReserveLeg, ...]
    route_audits: tuple[FixtureRouteAudit, ...]
    status: AccumulatorOptimizationStatus
    shortfall: int
    expected_slip_survival: float | None
    expected_slip_survival_method: str
    correlation_adjusted_expected_slip_survival: None
    combined_decimal_odds_product: float | None
    exposure_summary: Mapping[str, Any]
    flagged_exposure_pairs: tuple[Mapping[str, Any], ...]

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0

    @property
    def canonical_sha256(self) -> str:
        return _sha(self._identity_dict())

    @property
    def optimization_id(self) -> str:
        return self.canonical_sha256

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "accumulator_optimizer_contract_sha256": self.accumulator_optimizer_contract_sha256,
            "market_router_contract_sha256": self.market_router_contract_sha256,
            "evaluation_time": _iso(self.evaluation_time),
            "requested_target_size": self.requested_target_size,
            "selected_legs": [item.to_dict() for item in self.selected_legs],
            "reserve_legs": [item.to_dict() for item in self.reserve_legs],
            "route_audits": [item.to_dict() for item in self.route_audits],
            "status": self.status.value,
            "shortfall": self.shortfall,
            "fulfilled": self.fulfilled,
            "expected_slip_survival": self.expected_slip_survival,
            "expected_slip_survival_method": self.expected_slip_survival_method,
            "correlation_adjusted_expected_slip_survival": None,
            "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
            "combined_decimal_odds_product": self.combined_decimal_odds_product,
            "exposure_summary": dict(self.exposure_summary),
            "flagged_exposure_pairs": [dict(item) for item in self.flagged_exposure_pairs],
            "joint_selection_policy_id": JOINT_SELECTION_POLICY_ID,
            "correlation_policy_id": CORRELATION_POLICY_ID,
            "survival_policy_id": SURVIVAL_POLICY_ID,
            "fragility_policy_id": FRAGILITY_POLICY_ID,
            "reserve_policy_id": RESERVE_POLICY_ID,
            "shortfall_policy_id": SHORTFALL_POLICY_ID,
            "authority_flags": dict(AUTHORITY_FLAGS),
        }

    def to_dict(self) -> dict[str, Any]:
        result = self._identity_dict()
        result["optimization_id"] = self.optimization_id
        result["canonical_sha256"] = self.canonical_sha256
        return result


def _quote_sha(quote: SportyBetExactQuote) -> str:
    return _sha(quote.to_dict())


def _sorted_candidates(values: Sequence[CalibratedValueCandidate]) -> tuple[CalibratedValueCandidate, ...]:
    return tuple(sorted(values, key=lambda item: item.candidate_id))


def _sorted_quotes(values: Sequence[SportyBetExactQuote]) -> tuple[SportyBetExactQuote, ...]:
    return tuple(sorted(values, key=lambda item: _quote_sha(item)))


def _selected_results(
    decision: MarketRouterDecision,
    opportunity: RoutedOpportunity,
):
    candidate_ids = {item.candidate_id for item in opportunity.variants}
    results = tuple(
        item for item in decision.price_all_results
        if item.candidate.candidate_id in candidate_ids
    )
    if len(results) != len(candidate_ids):
        raise AccumulatorOptimizerError(
            "selected Router opportunity does not retain every contributing Phase 7 result"
        )
    if any(item.disposition is not PriceDisposition.PRICED or item.quote is None for item in results):
        raise AccumulatorOptimizerError("selected Router opportunity contains an unpriced variant")
    return tuple(sorted(results, key=lambda item: item.candidate.candidate_id))


def _survival_floor(
    opportunity: RoutedOpportunity,
    results,
) -> float:
    if opportunity.market_id not in _FULL_SETTLEMENT_MARKETS:
        if opportunity.calibrated_event_probability_floor is None:
            raise AccumulatorOptimizerError(
                "ordinary selected opportunity lacks calibrated event probability floor"
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
                raise AccumulatorOptimizerError("DNB settlement components drifted")
            survival = probabilities["WIN"] + probabilities["PUSH"]
        else:
            if components != _AH_COMPONENTS:
                raise AccumulatorOptimizerError("Asian Handicap settlement components drifted")
            survival = (
                probabilities["WIN"]
                + probabilities["HALF_WIN"]
                + probabilities["PUSH"]
            )
        values.append(_finite_probability(survival, "settlement survival probability"))
    if not values:
        raise AccumulatorOptimizerError("full-settlement opportunity has no model variants")
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


def _reconciliation_sha(value: reconciliation.SportyBetFotMobFullUtcReconciliation) -> str:
    return hashlib.sha256(reconciliation.canonical_reconciliation_bytes(value)).hexdigest()


def _build_portfolio_leg(
    decision: MarketRouterDecision,
    source_reconciliation: reconciliation.SportyBetFotMobFullUtcReconciliation,
) -> PortfolioLeg:
    opportunity = decision.selected_opportunity
    if decision.decision_status is not RouterDecisionStatus.SELECTED or opportunity is None:
        raise AccumulatorOptimizerError("only a Router SELECTED decision can become a portfolio leg")
    results = _selected_results(decision, opportunity)
    quotes = tuple(item.quote for item in results if item.quote is not None)
    quote_hashes = {_quote_sha(item) for item in quotes}
    if len(quote_hashes) != 1:
        raise AccumulatorOptimizerError("selected opportunity variants do not share one exact quote")
    quote = quotes[0]
    recon_sha = _reconciliation_sha(source_reconciliation)
    quote_reconciliation_shas = {item.fixture_reconciliation_sha256 for item in quotes}
    if quote_reconciliation_shas != {recon_sha}:
        raise AccumulatorOptimizerError(
            "source exposure reconciliation is not the exact reconciliation bound into the selected quote"
        )
    if (
        source_reconciliation.disposition
        is not reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        or source_reconciliation.fixture_reconciliation_authorized is not True
        or source_reconciliation.matched_fixture is None
    ):
        raise AccumulatorOptimizerError("portfolio exposure requires authorized unique full-UTC reconciliation")
    matched = source_reconciliation.matched_fixture
    if (
        decision.fixture_id != matched.source_fixture_identifier
        or decision.sportybet_event_id != source_reconciliation.sportybet_event_id
        or quote.fixture_id != decision.fixture_id
        or quote.event_id != decision.sportybet_event_id
    ):
        raise AccumulatorOptimizerError("Router/quote/reconciliation fixture identity mismatch")
    if source_reconciliation.sportybet_kickoff_utc != decision.evaluation_time and False:
        # Deliberately unreachable: evaluation time is not kickoff.  The exact kickoff
        # is validated against Fixture State before this builder is called.
        raise AssertionError
    robust_ev = opportunity.robust_net_expected_value
    if robust_ev is None or not math.isfinite(robust_ev) or robust_ev <= 0.0:
        raise AccumulatorOptimizerError("selected Router opportunity lacks positive robust EV")
    survival = _survival_floor(opportunity, results)
    family = MARKET_REGISTRY[opportunity.market_id].family
    quote_age = opportunity.quote_age_seconds
    if quote_age is None or not math.isfinite(quote_age) or quote_age < 0.0:
        raise AccumulatorOptimizerError("selected Router opportunity lacks valid quote age")
    odds = opportunity.decimal_odds
    if odds is None or not math.isfinite(odds) or odds <= 1.0:
        raise AccumulatorOptimizerError("selected Router opportunity lacks valid decimal odds")
    payload = {
        "router_decision_sha256": decision.canonical_sha256,
        "selected_opportunity_id": opportunity.opportunity_id,
        "reconciliation_sha256": recon_sha,
        "quote_identity_sha256": next(iter(quote_hashes)),
    }
    return PortfolioLeg(
        leg_id=_sha(payload),
        router_decision_sha256=decision.canonical_sha256,
        selected_opportunity_id=opportunity.opportunity_id,
        fixture_id=decision.fixture_id,
        sportybet_event_id=decision.sportybet_event_id or "",
        home_team=matched.home_team,
        away_team=matched.away_team,
        competition=matched.competition,
        kickoff_utc=source_reconciliation.sportybet_kickoff_utc,
        market_id=opportunity.market_id,
        outcome_id=opportunity.outcome_id,
        line=opportunity.line,
        market_family=family,
        quote_identity_sha256=next(iter(quote_hashes)),
        reconciliation_sha256=recon_sha,
        decimal_odds=float(odds),
        quote_age_seconds=float(quote_age),
        robust_net_expected_value=float(robust_ev),
        robust_edge=opportunity.robust_edge,
        calibrated_event_probability_floor=opportunity.calibrated_event_probability_floor,
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
            target, MAXIMUM_COMPETITION_SHARE, MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2
        ),
        "market_family": _target_cap(
            target, MAXIMUM_MARKET_FAMILY_SHARE, MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2
        ),
        "fragile": min(target, max(MINIMUM_FRAGILE_CAP, int(math.ceil(target * MAXIMUM_FRAGILE_SHARE)))),
    }


def _counts(selected: Sequence[PortfolioLeg]):
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
    candidate: PortfolioLeg,
    selected: Sequence[PortfolioLeg],
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
        reasons.append(f"MARKET_FAMILY_CONCENTRATION_CAP:{candidate.market_family.value}")
    if candidate.fragile and fragile >= caps["fragile"]:
        reasons.append("FRAGILITY_CAP")
    return tuple(sorted(set(reasons)))


def _marginal_key(
    candidate: PortfolioLeg,
    selected: Sequence[PortfolioLeg],
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
        candidate.quote_age_seconds,
        candidate.leg_id,
    )


def _reserve_key(candidate: PortfolioLeg) -> tuple[Any, ...]:
    edge_present = candidate.robust_edge is not None
    return (
        -candidate.survival_probability_floor,
        -candidate.robust_net_expected_value,
        0 if edge_present else 1,
        -(candidate.robust_edge if candidate.robust_edge is not None else 0.0),
        candidate.quote_age_seconds,
        candidate.leg_id,
    )


def _exposure_summary(selected: Sequence[PortfolioLeg], caps: Mapping[str, int]) -> Mapping[str, Any]:
    team, competition, family, fragile = _counts(selected)
    return {
        "caps": dict(caps),
        "team_counts": dict(sorted(team.items())),
        "competition_counts": dict(sorted(competition.items())),
        "market_family_counts": dict(sorted(family.items())),
        "fragile_count": fragile,
        "statistical_correlation_coefficients": None,
        "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
    }


def _flagged_pairs(selected: Sequence[PortfolioLeg]) -> tuple[Mapping[str, Any], ...]:
    flags: list[Mapping[str, Any]] = []
    ordered = sorted(selected, key=lambda item: item.leg_id)
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1:]:
            shared_teams = tuple(sorted({left.home_team, left.away_team} & {right.home_team, right.away_team}))
            same_competition = left.competition == right.competition
            same_family = left.market_family is right.market_family
            if shared_teams or same_competition or same_family:
                flags.append({
                    "left_leg_id": left.leg_id,
                    "right_leg_id": right.leg_id,
                    "shared_teams": list(shared_teams),
                    "same_competition": same_competition,
                    "same_market_family": same_family,
                    "statistical_correlation": None,
                })
    return tuple(flags)


def _survival_product(selected: Sequence[PortfolioLeg]) -> float | None:
    if not selected:
        return None
    result = math.prod(item.survival_probability_floor for item in selected)
    if not math.isfinite(result):
        raise AccumulatorOptimizerError("independence survival baseline is non-finite")
    return result


def _odds_product(selected: Sequence[PortfolioLeg]) -> float | None:
    if not selected:
        return None
    value = Decimal("1")
    for item in selected:
        value *= Decimal(str(item.decimal_odds))
    result = float(value)
    return result if math.isfinite(result) else None


def optimize_accumulator(
    fixture_inputs: Iterable[AccumulatorFixtureInput],
    *,
    target_size: int,
    evaluation_time: datetime,
) -> AccumulatorOptimization:
    """Replay every fixture through Phase 8, then build a disciplined portfolio.

    Requested size is a target only.  No Router NO_BET is overridden and no
    qualified reserve is promoted through a violated portfolio cap merely to
    fill the requested count.
    """
    identities = validate_accumulator_optimizer_contract()
    now = _utc(evaluation_time)
    if isinstance(target_size, bool) or not isinstance(target_size, int):
        raise TypeError("target_size must be an integer")
    if target_size < 1 or target_size > MAXIMUM_TARGET_SIZE:
        raise ValueError(f"target_size must be between 1 and {MAXIMUM_TARGET_SIZE}")
    values = tuple(fixture_inputs)
    if any(type(item) is not AccumulatorFixtureInput for item in values):
        raise AccumulatorOptimizerError("fixture_inputs must contain exact AccumulatorFixtureInput values")

    fixture_ids = [item.fixture_state.fixture_identifier for item in values]
    event_ids = [item.reconciliation.sportybet_event_id for item in values]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise AccumulatorOptimizerError("duplicate fixture inputs are not allowed")
    if len(event_ids) != len(set(event_ids)):
        raise AccumulatorOptimizerError("duplicate SportyBet event inputs are not allowed")

    admitted_legs: list[PortfolioLeg] = []
    audits: list[FixtureRouteAudit] = []
    for item in sorted(values, key=lambda value: value.fixture_state.fixture_identifier):
        decision = route_market_candidates(
            _sorted_candidates(item.candidates),
            _sorted_quotes(item.quotes),
            fixture_state=item.fixture_state,
            evaluation_time=now,
        )
        admission_reasons: list[str] = []
        leg: PortfolioLeg | None = None
        if decision.decision_status is RouterDecisionStatus.SELECTED:
            try:
                if item.reconciliation.sportybet_kickoff_utc != item.fixture_state.kickoff:
                    raise AccumulatorOptimizerError(
                        "Fixture State kickoff does not match source-bound full-UTC reconciliation"
                    )
                leg = _build_portfolio_leg(decision, item.reconciliation)
            except AccumulatorOptimizerError as exc:
                admission_reasons.append(str(exc))
        else:
            admission_reasons.extend(decision.decision_reasons)
        if leg is not None:
            admitted_legs.append(leg)
        audits.append(FixtureRouteAudit(
            fixture_id=decision.fixture_id,
            sportybet_event_id=decision.sportybet_event_id,
            router_decision_sha256=decision.canonical_sha256,
            router_decision_status=decision.decision_status.value,
            router_decision_reasons=decision.decision_reasons,
            selected_opportunity_id=decision.selected_opportunity_id,
            portfolio_admitted=leg is not None,
            portfolio_admission_reasons=tuple(sorted(set(admission_reasons))),
            router_decision=decision,
        ))

    caps = _caps(target_size)
    remaining = sorted(admitted_legs, key=lambda item: item.leg_id)
    selected: list[PortfolioLeg] = []
    while remaining and len(selected) < target_size:
        admissible = [
            item for item in remaining
            if not _constraint_reasons(item, selected, caps)
        ]
        if not admissible:
            break
        chosen = min(admissible, key=lambda item: _marginal_key(item, selected, caps))
        selected.append(chosen)
        remaining = [item for item in remaining if item.leg_id != chosen.leg_id]

    selected = sorted(selected, key=lambda item: item.leg_id)
    selected_ids = {item.leg_id for item in selected}
    reserve_rows: list[ReserveLeg] = []
    for item in sorted(
        (candidate for candidate in admitted_legs if candidate.leg_id not in selected_ids),
        key=_reserve_key,
    ):
        reasons = list(_constraint_reasons(item, selected, caps))
        if len(selected) >= target_size:
            reasons.append("TARGET_FILLED")
        if not reasons:
            reasons.append("LOWER_MARGINAL_PORTFOLIO_PRIORITY")
        reserve_rows.append(ReserveLeg(item, tuple(sorted(set(reasons)))))

    shortfall = max(0, target_size - len(selected))
    status = (
        AccumulatorOptimizationStatus.QUALIFIED_SET
        if selected
        else AccumulatorOptimizationStatus.NO_QUALIFIED_LEGS
    )
    return AccumulatorOptimization(
        accumulator_optimizer_contract_sha256=identities[
            "accumulator_optimizer_contract_sha256"
        ],
        market_router_contract_sha256=identities["market_router_contract_sha256"],
        evaluation_time=now,
        requested_target_size=target_size,
        selected_legs=tuple(selected),
        reserve_legs=tuple(reserve_rows),
        route_audits=tuple(sorted(audits, key=lambda item: item.fixture_id)),
        status=status,
        shortfall=shortfall,
        expected_slip_survival=_survival_product(selected),
        expected_slip_survival_method=(
            "CONSERVATIVE_WORST_MODEL_NON_NEGATIVE_SETTLEMENT_INDEPENDENCE_BASELINE;"
            "NOT_A_CORRELATION_ADJUSTED_JOINT_PROBABILITY"
        ),
        correlation_adjusted_expected_slip_survival=None,
        combined_decimal_odds_product=_odds_product(selected),
        exposure_summary=_exposure_summary(selected, caps),
        flagged_exposure_pairs=_flagged_pairs(selected),
    )


__all__ = [name for name in globals() if not name.startswith("_")]
