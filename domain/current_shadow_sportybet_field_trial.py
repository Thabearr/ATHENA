"""Research-only current ATHENA -> SportyBet field-trial policy.

This boundary is intentionally separate from the production Phase 6 -> Price-all
v3 -> Router v3 -> Portfolio v3 chain.  It consumes only a reviewed PR149 sealed
shadow prediction plus one exact current SportyBet event-detail inventory and
produces a *research field-trial* opportunity/portfolio record.

It does not mint ``CalibratedValueCandidate`` values, does not set production
model/probability/Phase6 authority, and does not place a wager.  The initial
market surface is deliberately narrow: exact SportyBet ``Total Goals`` half-goal
lines only.  This avoids inventing path/half-time/early-payout semantics while
still allowing a real current-provider field trial.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain import score_matrix
from domain import sportybet_live_event_quote_evidence as live
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain._accumulator_optimizer_contracts import (
    EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION,
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
    validate_accumulator_optimizer_contract,
)
from domain._market_router_contracts import (
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
)
from domain.markets import MarketFamily, MarketId, OutcomeId

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-sportybet-field-trial-v1"
STATUS = "RESEARCH_ONLY_CURRENT_SHADOW_FIELD_TRIAL"
PROVIDER = "SportyBet"
MAX_SOURCE_AGE_SECONDS = 900
MINIMUM_LEAD_SECONDS = 120
MARKET_POLICY_ID = "EXACT_TOTAL_GOALS_HALF_LINES_ONLY_V1"
VALUE_POLICY_ID = "PR149_CALIBRATED_XG_POISSON_PLUS_CURRENT_PROVIDER_DECIMAL_ODDS_RESEARCH_V1"
ROUTER_POLICY_ID = "FROZEN_ROUTER_V2_THRESHOLDS_SINGLE_SHADOW_MODEL_RESEARCH_V1"
PORTFOLIO_POLICY_ID = "FROZEN_PORTFOLIO_V2_CAPS_AND_MARGINAL_ORDER_RESEARCH_V1"
SHORTFALL_POLICY_ID = "TARGET_IS_NOT_PADDED_RESEARCH_CODE_MAY_PRESERVE_SHORTFALL_V1"
NEXT_BOUNDARY = "USER_CONTROLLED_ANONYMOUS_RESEARCH_SHARE_CODE_TRANSPORT_OPTIONAL"

AUTHORITY = types.MappingProxyType(
    {
        "reviewed_current_fixture_identity": True,
        "reviewed_shadow_expected_goals": True,
        "research_score_matrix": True,
        "research_market_probability": True,
        "research_current_provider_value": True,
        "research_field_trial_routing": True,
        "research_field_trial_portfolio": True,
        "production_model": False,
        "production_probability": False,
        "phase6": False,
        "production_price_all": False,
        "production_market_router": False,
        "production_portfolio": False,
        "production_selection": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)

_TOTAL_SPECIFIER_RE = re.compile(r"^total=(-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class CurrentShadowSportyBetFieldTrialError(ValueError):
    """Raised when the research field-trial cannot preserve exact source semantics."""


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentShadowSportyBetFieldTrialError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowSportyBetFieldTrialError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurrentShadowSportyBetFieldTrialError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise CurrentShadowSportyBetFieldTrialError(f"{label} must be finite numeric")
    return result


def _probability(value: Any, label: str) -> float:
    result = _finite(value, label)
    if not 0.0 <= result <= 1.0:
        raise CurrentShadowSportyBetFieldTrialError(f"{label} must be within [0,1]")
    return result


def _source_id(value: str) -> int:
    if type(value) is not str or not value.startswith("FOTMOB:"):
        raise CurrentShadowSportyBetFieldTrialError("fixture_identifier must be exact FOTMOB:<id>")
    raw = value.removeprefix("FOTMOB:")
    if not raw.isdigit() or int(raw) <= 0:
        raise CurrentShadowSportyBetFieldTrialError("fixture_identifier has invalid FotMob ID")
    return int(raw)


def _half_line(value: float) -> bool:
    doubled = value * 2.0
    return math.isfinite(doubled) and abs(doubled - round(doubled)) <= 1e-12 and int(round(doubled)) % 2 == 1


def _target_cap(target: int, share: float, minimum_when_multi: int) -> int:
    if target == 1:
        return 1
    return min(target, max(minimum_when_multi, int(math.ceil(target * share))))


def _caps(target: int) -> Mapping[str, int]:
    return types.MappingProxyType(
        {
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
                max(MINIMUM_FRAGILE_CAP, int(math.ceil(target * MAXIMUM_FRAGILE_SHARE))),
            ),
        }
    )


def _validate_policy_dependencies() -> Mapping[str, str]:
    try:
        optimizer = validate_accumulator_optimizer_contract()
        live_contract = live.validate_direct_event_source_contract()
    except Exception as exc:
        raise CurrentShadowSportyBetFieldTrialError("reviewed research dependencies drifted") from exc
    expected_optimizer = EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION[1]
    if optimizer["accumulator_optimizer_contract_sha256"] != expected_optimizer:
        raise CurrentShadowSportyBetFieldTrialError("frozen Portfolio-v2 policy identity drifted")
    if live_contract["contract_sha256"] != live.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetFieldTrialError("current SportyBet event source identity drifted")
    if (
        MINIMUM_EVENT_PROBABILITY != 0.55
        or MINIMUM_NET_EXPECTED_VALUE != 0.0
        or MINIMUM_ROBUST_NET_EXPECTED_VALUE != 0.0
        or MINIMUM_ROBUST_EDGE != 0.0
    ):
        raise CurrentShadowSportyBetFieldTrialError("frozen Router threshold identity drifted")
    return types.MappingProxyType(
        {
            "accumulator_optimizer_v2_contract_sha256": expected_optimizer,
            "live_event_source_contract_sha256": live.EXPECTED_CONTRACT_SHA256,
        }
    )


@dataclasses.dataclass(frozen=True)
class ResearchFixtureIdentity:
    fixture_identifier: str
    event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime

    def __post_init__(self) -> None:
        _source_id(self.fixture_identifier)
        for value, label in (
            (self.event_id, "event_id"),
            (self.home_team, "home_team"),
            (self.away_team, "away_team"),
            (self.competition, "competition"),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise CurrentShadowSportyBetFieldTrialError(f"{label} must be exact non-empty text")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
        }


@dataclasses.dataclass(frozen=True)
class ResearchTotalGoalsOpportunity:
    opportunity_id: str
    fixture: ResearchFixtureIdentity
    sealed_prediction_sha256: str
    home_expected_goals: float
    away_expected_goals: float
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str
    provider_outcome_id: str
    provider_outcome_name: str
    outcome_id: OutcomeId
    line: float
    decimal_odds: float
    quote_observed_at: datetime
    quote_age_seconds: float
    kickoff_lead_seconds: float
    event_probability: float
    fair_probability: float
    robust_edge: float
    net_expected_value: float
    survival_probability: float
    eligible: bool
    rejection_reasons: tuple[str, ...]
    fragile: bool
    current_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "fixture": self.fixture.to_dict(),
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "home_expected_goals": self.home_expected_goals,
            "away_expected_goals": self.away_expected_goals,
            "market_id": MarketId.TOTAL_GOALS.value,
            "market_family": MarketFamily.TOTAL_GOALS.value,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "decimal_odds": self.decimal_odds,
            "quote_observed_at": self.quote_observed_at.isoformat().replace("+00:00", "Z"),
            "quote_age_seconds": self.quote_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "event_probability": self.event_probability,
            "fair_probability": self.fair_probability,
            "robust_edge": self.robust_edge,
            "net_expected_value": self.net_expected_value,
            "survival_probability": self.survival_probability,
            "eligible": self.eligible,
            "rejection_reasons": list(self.rejection_reasons),
            "fragile": self.fragile,
            "current_inventory_sha256": self.current_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
        }

    def direct_selection(self) -> dict[str, str]:
        return {
            "eventId": self.fixture.event_id,
            "marketId": self.provider_market_id,
            "outcomeId": self.provider_outcome_id,
            "specifier": self.provider_specifier,
        }


@dataclasses.dataclass(frozen=True)
class ResearchFixtureDecision:
    fixture: ResearchFixtureIdentity
    status: str
    selected_opportunity_id: str | None
    opportunities: tuple[ResearchTotalGoalsOpportunity, ...]
    decision_reasons: tuple[str, ...]

    @property
    def selected(self) -> ResearchTotalGoalsOpportunity | None:
        if self.selected_opportunity_id is None:
            return None
        rows = [item for item in self.opportunities if item.opportunity_id == self.selected_opportunity_id]
        if len(rows) != 1:
            raise CurrentShadowSportyBetFieldTrialError("selected research opportunity identity is inconsistent")
        return rows[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture.to_dict(),
            "status": self.status,
            "selected_opportunity_id": self.selected_opportunity_id,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "decision_reasons": list(self.decision_reasons),
        }


@dataclasses.dataclass(frozen=True)
class ResearchShadowPortfolio:
    requested_target_size: int
    evaluation_time: datetime
    selected_legs: tuple[ResearchTotalGoalsOpportunity, ...]
    reserve_legs: tuple[ResearchTotalGoalsOpportunity, ...]
    shortfall: int
    expected_slip_survival: float | None
    combined_decimal_odds_product: float | None
    caps: Mapping[str, int]
    authority: Mapping[str, bool]
    policy_identities: Mapping[str, str]

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0

    @property
    def field_trial_status(self) -> str:
        if not self.selected_legs:
            return "RESEARCH_NO_QUALIFIED_LEGS"
        return "RESEARCH_TARGET_QUALIFIED" if self.fulfilled else "RESEARCH_QUALIFIED_WITH_SHORTFALL"

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def direct_selections(self) -> tuple[dict[str, str], ...]:
        return tuple(item.direct_selection() for item in self.selected_legs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "provider": PROVIDER,
            "field_trial_status": self.field_trial_status,
            "requested_target_size": self.requested_target_size,
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "selected_legs": [item.to_dict() for item in self.selected_legs],
            "reserve_legs": [item.to_dict() for item in self.reserve_legs],
            "selected_leg_count": len(self.selected_legs),
            "shortfall": self.shortfall,
            "fulfilled": self.fulfilled,
            "expected_slip_survival": self.expected_slip_survival,
            "expected_slip_survival_method": "SINGLE_RESEARCH_SHADOW_MODEL_INDEPENDENCE_BASELINE_NOT_CORRELATION_ADJUSTED",
            "combined_decimal_odds_product": self.combined_decimal_odds_product,
            "caps": dict(self.caps),
            "market_policy_id": MARKET_POLICY_ID,
            "value_policy_id": VALUE_POLICY_ID,
            "router_policy_id": ROUTER_POLICY_ID,
            "portfolio_policy_id": PORTFOLIO_POLICY_ID,
            "shortfall_policy_id": SHORTFALL_POLICY_ID,
            "policy_identities": dict(self.policy_identities),
            "authority": dict(self.authority),
            "next_boundary": NEXT_BOUNDARY,
            "wager_placed": False,
        }


def build_total_goals_research_decision(
    *,
    fixture: ResearchFixtureIdentity,
    sealed_prediction: fresh.SealedFreshPrediction,
    sealed_prediction_sha256: str,
    inventory: live.SportyBetLiveEventQuoteInventory,
    evaluation_time: datetime,
) -> ResearchFixtureDecision:
    """Price exact current half-goal Total Goals rows from one sealed shadow case."""
    _validate_policy_dependencies()
    if type(sealed_prediction) is not fresh.SealedFreshPrediction:
        raise CurrentShadowSportyBetFieldTrialError("sealed_prediction must be exact PR149 object")
    prediction = dataclasses.replace(sealed_prediction)
    expected_sha = fresh.sha256_sealed_fresh_prediction(prediction)
    if sealed_prediction_sha256 != expected_sha or _SHA_RE.fullmatch(sealed_prediction_sha256) is None:
        raise CurrentShadowSportyBetFieldTrialError("sealed prediction identity mismatch")
    source_id = _source_id(fixture.fixture_identifier)
    if prediction.fixture.fixture_id != source_id or prediction.fixture.kickoff_utc != fixture.kickoff_utc:
        raise CurrentShadowSportyBetFieldTrialError("sealed shadow fixture identity differs from field-trial fixture")
    if type(inventory) is not live.SportyBetLiveEventQuoteInventory:
        raise CurrentShadowSportyBetFieldTrialError("inventory must be exact current SportyBet event inventory")
    if (
        inventory.event_id != fixture.event_id
        or inventory.home_team_name != fixture.home_team
        or inventory.away_team_name != fixture.away_team
        or inventory.kickoff_utc != fixture.kickoff_utc
    ):
        raise CurrentShadowSportyBetFieldTrialError("current provider event identity differs from exact fixture")
    if inventory.prematch_bookable_observed is not True:
        return ResearchFixtureDecision(fixture, "NO_BET", None, (), ("CURRENT_EVENT_NOT_PREMATCH_BOOKABLE",))

    now = _utc(evaluation_time, "evaluation_time")
    observed = _utc(inventory.observed_at, "inventory observed_at")
    age = (now - observed).total_seconds()
    lead = (fixture.kickoff_utc - now).total_seconds()
    if not math.isfinite(age) or age < 0:
        raise CurrentShadowSportyBetFieldTrialError("current provider observation is future-dated")
    freshness_reasons: list[str] = []
    if age > MAX_SOURCE_AGE_SECONDS:
        freshness_reasons.append("CURRENT_PROVIDER_QUOTE_STALE")
    if not math.isfinite(lead) or lead <= MINIMUM_LEAD_SECONDS:
        freshness_reasons.append("FIXTURE_TOO_CLOSE_TO_KICKOFF")
    if freshness_reasons:
        return ResearchFixtureDecision(
            fixture,
            "NO_BET",
            None,
            (),
            tuple(sorted(set(freshness_reasons))),
        )

    rates = dict(prediction.rates)
    if set(rates) != {
        "native_home",
        "native_away",
        "elo_only_home",
        "elo_only_away",
        "calibrated_home",
        "calibrated_away",
    }:
        raise CurrentShadowSportyBetFieldTrialError("PR149 rate vocabulary drifted")
    home_xg = _finite(rates["calibrated_home"], "calibrated_home")
    away_xg = _finite(rates["calibrated_away"], "calibrated_away")
    if home_xg < 0 or away_xg < 0:
        raise CurrentShadowSportyBetFieldTrialError("calibrated rates must be non-negative")
    matrix = score_matrix.build_score_matrix(home_xg, away_xg)

    grouped: dict[tuple[str, str], dict[str, live.SportyBetLiveEventSelection]] = {}
    for selection in inventory.selections:
        if selection.market_name != "Total Goals" or selection.specifier is None or not selection.bookable:
            continue
        match = _TOTAL_SPECIFIER_RE.fullmatch(selection.specifier)
        if match is None:
            continue
        try:
            line = float(match.group(1))
        except ValueError:
            continue
        if line < 0 or not _half_line(line):
            continue
        if selection.outcome_id not in {"O", "U"}:
            continue
        expected_name = ("Over " if selection.outcome_id == "O" else "Under ") + format(line, "g")
        if selection.outcome_name != expected_name:
            continue
        grouped.setdefault((selection.market_id, selection.specifier), {})[selection.outcome_id] = selection

    opportunities: list[ResearchTotalGoalsOpportunity] = []
    for (market_id, specifier), sides in sorted(grouped.items()):
        if set(sides) != {"O", "U"}:
            continue
        over = sides["O"]
        under = sides["U"]
        if over.market_name != under.market_name or over.specifier != under.specifier:
            continue
        match = _TOTAL_SPECIFIER_RE.fullmatch(specifier)
        if match is None:
            continue
        line = float(match.group(1))
        implied_over = 1.0 / _finite(over.odds_decimal, "over odds")
        implied_under = 1.0 / _finite(under.odds_decimal, "under odds")
        implied_sum = implied_over + implied_under
        if not math.isfinite(implied_sum) or implied_sum <= 0:
            continue
        fair = {"O": implied_over / implied_sum, "U": implied_under / implied_sum}
        event = {"O": matrix.over(line), "U": matrix.under(line)}
        for key, outcome_id in (("O", OutcomeId.OVER), ("U", OutcomeId.UNDER)):
            selected = sides[key]
            p = _probability(event[key], "event probability")
            fair_p = _probability(fair[key], "fair probability")
            odds = _finite(selected.odds_decimal, "decimal odds")
            if odds <= 1.0:
                continue
            net_ev = p * odds - 1.0
            edge = p - fair_p
            reasons: list[str] = []
            if p < MINIMUM_EVENT_PROBABILITY:
                reasons.append("EVENT_PROBABILITY_BELOW_FROZEN_ROUTER_THRESHOLD")
            if net_ev <= MINIMUM_NET_EXPECTED_VALUE or net_ev <= MINIMUM_ROBUST_NET_EXPECTED_VALUE:
                reasons.append("NET_EXPECTED_VALUE_NOT_STRICTLY_POSITIVE")
            if edge <= MINIMUM_ROBUST_EDGE:
                reasons.append("ROBUST_EDGE_NOT_STRICTLY_POSITIVE")
            fragile = (
                net_ev < MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE
                or p < MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE
            )
            payload = {
                "fixture_identifier": fixture.fixture_identifier,
                "event_id": fixture.event_id,
                "sealed_prediction_sha256": sealed_prediction_sha256,
                "inventory_sha256": inventory.canonical_sha256,
                "provider_market_id": market_id,
                "provider_specifier": specifier,
                "provider_outcome_id": selected.outcome_id,
                "odds": odds,
                "event_probability": p,
            }
            opportunities.append(
                ResearchTotalGoalsOpportunity(
                    opportunity_id=_sha(payload),
                    fixture=fixture,
                    sealed_prediction_sha256=sealed_prediction_sha256,
                    home_expected_goals=home_xg,
                    away_expected_goals=away_xg,
                    provider_market_id=selected.market_id,
                    provider_market_name=selected.market_name,
                    provider_specifier=selected.specifier or "",
                    provider_outcome_id=selected.outcome_id,
                    provider_outcome_name=selected.outcome_name,
                    outcome_id=outcome_id,
                    line=line,
                    decimal_odds=odds,
                    quote_observed_at=observed,
                    quote_age_seconds=age,
                    kickoff_lead_seconds=lead,
                    event_probability=p,
                    fair_probability=fair_p,
                    robust_edge=edge,
                    net_expected_value=net_ev,
                    survival_probability=p,
                    eligible=not reasons,
                    rejection_reasons=tuple(sorted(set(reasons))),
                    fragile=fragile,
                    current_inventory_sha256=inventory.canonical_sha256,
                    source_manifest_sha256=inventory.source_manifest_sha256,
                    source_raw_sha256=inventory.source_raw_sha256,
                )
            )

    eligible = [item for item in opportunities if item.eligible]
    if not eligible:
        return ResearchFixtureDecision(
            fixture=fixture,
            status="NO_BET",
            selected_opportunity_id=None,
            opportunities=tuple(sorted(opportunities, key=lambda item: item.opportunity_id)),
            decision_reasons=("NO_ELIGIBLE_RESEARCH_TOTAL_GOALS_VALUE",),
        )
    chosen = min(
        eligible,
        key=lambda item: (
            -item.net_expected_value,
            -item.robust_edge,
            -item.event_probability,
            item.quote_age_seconds,
            item.opportunity_id,
        ),
    )
    return ResearchFixtureDecision(
        fixture=fixture,
        status="SELECTED",
        selected_opportunity_id=chosen.opportunity_id,
        opportunities=tuple(sorted(opportunities, key=lambda item: item.opportunity_id)),
        decision_reasons=("RESEARCH_SHADOW_TOTAL_GOALS_ROBUST_VALUE_SELECTED",),
    )


def _counts(selected: Sequence[ResearchTotalGoalsOpportunity]) -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
    teams: dict[str, int] = {}
    competitions: dict[str, int] = {}
    families: dict[str, int] = {}
    fragile = 0
    for item in selected:
        for name in (item.fixture.home_team, item.fixture.away_team):
            teams[name] = teams.get(name, 0) + 1
        competitions[item.fixture.competition] = competitions.get(item.fixture.competition, 0) + 1
        families[MarketFamily.TOTAL_GOALS.value] = families.get(MarketFamily.TOTAL_GOALS.value, 0) + 1
        fragile += int(item.fragile)
    return teams, competitions, families, fragile


def _constraint_reasons(
    candidate: ResearchTotalGoalsOpportunity,
    selected: Sequence[ResearchTotalGoalsOpportunity],
    caps: Mapping[str, int],
) -> tuple[str, ...]:
    teams, competitions, families, fragile = _counts(selected)
    reasons: list[str] = []
    for name in (candidate.fixture.home_team, candidate.fixture.away_team):
        if teams.get(name, 0) >= caps["team"]:
            reasons.append(f"TEAM_EXPOSURE_CAP:{name}")
    if competitions.get(candidate.fixture.competition, 0) >= caps["competition"]:
        reasons.append(f"COMPETITION_CONCENTRATION_CAP:{candidate.fixture.competition}")
    if families.get(MarketFamily.TOTAL_GOALS.value, 0) >= caps["market_family"]:
        reasons.append(f"MARKET_FAMILY_CONCENTRATION_CAP:{MarketFamily.TOTAL_GOALS.value}")
    if candidate.fragile and fragile >= caps["fragile"]:
        reasons.append("FRAGILITY_CAP")
    return tuple(sorted(set(reasons)))


def _marginal_key(
    candidate: ResearchTotalGoalsOpportunity,
    selected: Sequence[ResearchTotalGoalsOpportunity],
    caps: Mapping[str, int],
) -> tuple[Any, ...]:
    _teams, competitions, families, fragile = _counts(selected)
    exposure_penalty = (
        competitions.get(candidate.fixture.competition, 0) / caps["competition"]
        + families.get(MarketFamily.TOTAL_GOALS.value, 0) / caps["market_family"]
        + ((fragile / caps["fragile"]) if candidate.fragile else 0.0)
    )
    return (
        exposure_penalty,
        -candidate.survival_probability,
        -candidate.net_expected_value,
        -candidate.robust_edge,
        candidate.quote_age_seconds,
        candidate.opportunity_id,
    )


def optimize_research_shadow_portfolio(
    decisions: Sequence[ResearchFixtureDecision],
    *,
    target_size: int,
    evaluation_time: datetime,
) -> ResearchShadowPortfolio:
    identities = _validate_policy_dependencies()
    now = _utc(evaluation_time, "evaluation_time")
    if isinstance(target_size, bool) or not isinstance(target_size, int) or not 1 <= target_size <= MAXIMUM_TARGET_SIZE:
        raise CurrentShadowSportyBetFieldTrialError(
            f"target_size must be an integer from 1 through {MAXIMUM_TARGET_SIZE}"
        )
    if isinstance(decisions, (str, bytes)) or not isinstance(decisions, Sequence):
        raise CurrentShadowSportyBetFieldTrialError("decisions must be a sequence")
    rows = tuple(decisions)
    if any(type(item) is not ResearchFixtureDecision for item in rows):
        raise CurrentShadowSportyBetFieldTrialError("decisions contain invalid item")
    fixture_ids = [item.fixture.fixture_identifier for item in rows]
    event_ids = [item.fixture.event_id for item in rows]
    if len(fixture_ids) != len(set(fixture_ids)) or len(event_ids) != len(set(event_ids)):
        raise CurrentShadowSportyBetFieldTrialError("duplicate fixture/event decisions are forbidden")

    admitted = [item.selected for item in rows if item.selected is not None]
    admitted = [item for item in admitted if item is not None]
    caps = _caps(target_size)
    remaining = sorted(admitted, key=lambda item: item.opportunity_id)
    selected: list[ResearchTotalGoalsOpportunity] = []
    while remaining and len(selected) < target_size:
        admissible = [item for item in remaining if not _constraint_reasons(item, selected, caps)]
        if not admissible:
            break
        chosen = min(admissible, key=lambda item: _marginal_key(item, selected, caps))
        selected.append(chosen)
        remaining = [item for item in remaining if item.opportunity_id != chosen.opportunity_id]

    selected = sorted(selected, key=lambda item: item.opportunity_id)
    selected_ids = {item.opportunity_id for item in selected}
    reserves = tuple(
        sorted(
            (item for item in admitted if item.opportunity_id not in selected_ids),
            key=lambda item: (
                -item.survival_probability,
                -item.net_expected_value,
                -item.robust_edge,
                item.quote_age_seconds,
                item.opportunity_id,
            ),
        )
    )
    survival = None if not selected else math.prod(item.survival_probability for item in selected)
    if survival is not None and not math.isfinite(survival):
        raise CurrentShadowSportyBetFieldTrialError("research survival product is non-finite")
    odds_product: float | None = None
    if selected:
        odds_value = Decimal("1")
        for item in selected:
            odds_value *= Decimal(str(item.decimal_odds))
        parsed = float(odds_value)
        odds_product = parsed if math.isfinite(parsed) else None
    return ResearchShadowPortfolio(
        requested_target_size=target_size,
        evaluation_time=now,
        selected_legs=tuple(selected),
        reserve_legs=reserves,
        shortfall=max(0, target_size - len(selected)),
        expected_slip_survival=survival,
        combined_decimal_odds_product=odds_product,
        caps=caps,
        authority=types.MappingProxyType(dict(AUTHORITY)),
        policy_identities=identities,
    )


__all__ = [name for name in globals() if not name.startswith("_")]
