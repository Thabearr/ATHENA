"""ATHENA Phase 7 price-all, settlement-aware value evaluation.

This module consumes upstream-authorized calibrated candidates and exact,
source-qualified SportyBet quotes.  It deliberately does not rank, route,
select, export, or authorize a bet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from domain._price_all_contracts import (
    AUTHORITY_FLAGS,
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    CalibratedValueCandidate,
    DevigStatus,
    PriceAllError,
    PriceDisposition,
    SettlementState,
    SportyBetExactQuote,
    validate_price_all_contract,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.sportybet_reviewed_canonical_market_mapping import (
    SettlementEquivalenceAuthority,
)

_EARLY_OR_WEH = frozenset({
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
    MarketId.MATCH_RESULT_1UP,
    MarketId.MATCH_RESULT_2UP,
})
_ORDINARY_PARTITIONS: Mapping[MarketId, tuple[OutcomeId, ...]] = MappingProxyType({
    MarketId.MATCH_RESULT: (OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
    MarketId.BTTS: (OutcomeId.YES, OutcomeId.NO),
    MarketId.TOTAL_GOALS: (OutcomeId.OVER, OutcomeId.UNDER),
    MarketId.DRAW_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
    MarketId.HOME_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
    MarketId.AWAY_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
    MarketId.HOME_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
    MarketId.AWAY_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
})
def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PriceAllError("evaluation_time must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class PriceAllValueResult:
    candidate: CalibratedValueCandidate
    disposition: PriceDisposition
    reason: str
    quote: SportyBetExactQuote | None
    evaluation_time: datetime
    quote_age_seconds: float | None
    raw_implied_probability: float | None
    devig_status: DevigStatus | None
    devig_method: str | None
    overround: float | None
    fair_probability: float | None
    settlement_returns: tuple[tuple[str, float], ...]
    expected_return_multiplier: float | None
    net_expected_value: float | None
    ev_percentage: float | None
    contract_sha256: str

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "disposition": self.disposition.value,
            "reason": self.reason,
            "quote": None if self.quote is None else self.quote.to_dict(),
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "quote_age_seconds": self.quote_age_seconds,
            "raw_implied_probability": self.raw_implied_probability,
            "devig_status": None if self.devig_status is None else self.devig_status.value,
            "devig_method": self.devig_method,
            "overround": self.overround,
            "fair_probability": self.fair_probability,
            "settlement_returns": [
                {"state": state, "unit_stake_profit": profit}
                for state, profit in self.settlement_returns
            ],
            "expected_return_multiplier": self.expected_return_multiplier,
            "net_expected_value": self.net_expected_value,
            "ev_percentage": self.ev_percentage,
            "price_all_contract_sha256": self.contract_sha256,
            "authority_flags": dict(AUTHORITY_FLAGS),
        }


def _empty_result(candidate: CalibratedValueCandidate, disposition: PriceDisposition,
                  reason: str, now: datetime, contract_sha: str,
                  quote: SportyBetExactQuote | None = None,
                  age: float | None = None) -> PriceAllValueResult:
    return PriceAllValueResult(candidate, disposition, reason, quote, now, age, None,
                               None, None, None, None, (), None, None, None, contract_sha)


def _required_states(candidate: CalibratedValueCandidate) -> tuple[SettlementState, ...]:
    family = MARKET_REGISTRY[candidate.market_id].family
    if family is MarketFamily.DRAW_NO_BET:
        return (SettlementState.WIN, SettlementState.PUSH, SettlementState.LOSS)
    if family is MarketFamily.ASIAN_HANDICAP:
        return tuple(SettlementState)
    if family is MarketFamily.TOTAL_GOALS:
        quarter_units = Decimal(str(candidate.line)) * 4
        if quarter_units != quarter_units.to_integral_value():
            raise PriceAllError("total-goals line lacks reviewed quarter-goal settlement semantics")
        modulo = int(quarter_units) % 4
        if modulo == 0:
            return (SettlementState.WIN, SettlementState.PUSH, SettlementState.LOSS)
        if modulo == 2:
            return (SettlementState.WIN, SettlementState.LOSS)
        return tuple(SettlementState)
    return (SettlementState.WIN, SettlementState.LOSS)


def _settlement_ev(candidate: CalibratedValueCandidate, odds: float) -> tuple[tuple[tuple[str, float], ...], float]:
    required = _required_states(candidate)
    supplied = candidate.probability_map
    required_names = {state.value for state in required}
    if set(supplied) == required_names:
        settlement_probabilities = supplied
    else:
        partition = _ORDINARY_PARTITIONS.get(candidate.market_id)
        unit = dict(candidate.calibration_unit)
        if (
            required == (SettlementState.WIN, SettlementState.LOSS)
            and set(supplied) == {"YES", "NO"}
            and unit.get("selection_outcome") == candidate.outcome_id.value
        ):
            settlement_probabilities = MappingProxyType({
                SettlementState.WIN.value: supplied["YES"],
                SettlementState.LOSS.value: supplied["NO"],
            })
        elif required == (SettlementState.WIN, SettlementState.LOSS) and partition is not None \
                and set(supplied) == {outcome.value for outcome in partition}:
            win = supplied[candidate.outcome_id.value]
            settlement_probabilities = MappingProxyType({
                SettlementState.WIN.value: win,
                SettlementState.LOSS.value: math.fsum(
                    probability for name, probability in supplied.items()
                    if name != candidate.outcome_id.value),
            })
        else:
            raise PriceAllError("calibrated settlement distribution is incomplete")
    returns = {
        SettlementState.WIN: odds - 1.0,
        SettlementState.HALF_WIN: (odds - 1.0) / 2.0,
        SettlementState.PUSH: 0.0,
        SettlementState.HALF_LOSS: -0.5,
        SettlementState.LOSS: -1.0,
    }
    serialized = tuple((state.value, returns[state]) for state in required)
    ev = math.fsum(settlement_probabilities[state.value] * returns[state] for state in required)
    return serialized, ev


def _partition_quotes(candidate: CalibratedValueCandidate, quote: SportyBetExactQuote,
                      quotes: Sequence[SportyBetExactQuote]) -> tuple[DevigStatus, float | None, float | None]:
    family = MARKET_REGISTRY[candidate.market_id].family
    if family in {MarketFamily.DOUBLE_CHANCE, MarketFamily.EARLY_PAYOUT}:
        return DevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS, None, None
    if family in {MarketFamily.DRAW_NO_BET, MarketFamily.ASIAN_HANDICAP}:
        return DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT, None, None
    if family is MarketFamily.TOTAL_GOALS:
        quarter_units = Decimal(str(candidate.line)) * 4
        if quarter_units != quarter_units.to_integral_value() or int(quarter_units) % 4 != 2:
            return DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT, None, None
    expected = _ORDINARY_PARTITIONS.get(candidate.market_id)
    if expected is None:
        return DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION, None, None
    market_related = [item for item in quotes if (
        item.fixture_id == quote.fixture_id
        and item.event_id == quote.event_id
        and item.source == quote.source
        and item.canonical_market_id is quote.canonical_market_id
        and item.canonical_line == quote.canonical_line
        and item.provider_market_id == quote.provider_market_id
        and item.provider_specifier == quote.provider_specifier
        and item.fixture_reconciliation_sha256 == quote.fixture_reconciliation_sha256
    )]
    same = [item for item in market_related if (
        item.evidence_snapshot_sha256 == quote.evidence_snapshot_sha256
        and item.source_evidence_manifest_sha256 == quote.source_evidence_manifest_sha256
        and item.source_raw_sha256 == quote.source_raw_sha256
        and item.mapping_evidence_sha256 == quote.mapping_evidence_sha256
        and item.source_native_inventory_sha256 == quote.source_native_inventory_sha256
    )]
    by_outcome: dict[OutcomeId, SportyBetExactQuote] = {}
    duplicate = False
    for item in same:
        if item.canonical_outcome_id in by_outcome:
            duplicate = True
        by_outcome[item.canonical_outcome_id] = item
    if duplicate or set(by_outcome) != set(expected):
        if set(item.canonical_outcome_id for item in market_related) >= set(expected):
            return DevigStatus.UNAVAILABLE_CROSS_SNAPSHOT_PARTITION, None, None
        return DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION, None, None
    overround = math.fsum(1.0 / by_outcome[outcome].decimal_odds for outcome in expected)
    return DevigStatus.AVAILABLE_COMPLETE_PARTITION, overround, (1.0 / quote.decimal_odds) / overround


def price_all_candidates(
    candidates: Iterable[CalibratedValueCandidate],
    quotes: Iterable[SportyBetExactQuote],
    *,
    evaluation_time: datetime,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
) -> tuple[PriceAllValueResult, ...]:
    """Evaluate every candidate; no candidate is dropped, ranked, or selected."""
    identities = validate_price_all_contract()
    contract_sha = identities["price_all_contract_sha256"]
    now = _utc(evaluation_time)
    if type(max_quote_age_seconds) is not int or max_quote_age_seconds < 0:
        raise PriceAllError("max_quote_age_seconds must be a non-negative integer")
    candidate_values = tuple(candidates)
    quote_values = tuple(quotes)
    if any(type(item) is not CalibratedValueCandidate for item in candidate_values):
        raise PriceAllError("candidates must be exact calibrated value candidates")
    if any(type(item) is not SportyBetExactQuote for item in quote_values):
        raise PriceAllError("quotes must be exact SportyBet quotes")
    if len({item.candidate_id for item in candidate_values}) != len(candidate_values):
        raise PriceAllError("candidate_id must be unique")
    duplicate_quote_ids = {item.quote_identity for item in quote_values if sum(
        other.quote_identity == item.quote_identity for other in quote_values) > 1}
    results: list[PriceAllValueResult] = []
    for candidate in sorted(candidate_values, key=lambda item: item.candidate_id):
        if candidate.market_id in _EARLY_OR_WEH:
            results.append(_empty_result(candidate,
                PriceDisposition.BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE,
                "upstream calibrated probability authority is unavailable", now, contract_sha))
            continue
        exact = [item for item in quote_values if (
            item.fixture_id == candidate.fixture_id
            and item.event_id == candidate.sportybet_event_id
            and item.canonical_market_id is candidate.market_id
            and item.canonical_outcome_id is candidate.outcome_id
            and item.canonical_line == candidate.line
        )]
        if not exact:
            results.append(_empty_result(candidate, PriceDisposition.UNPRICED_NO_EXACT_QUOTE,
                "no exact fixture/event/market/outcome/line quote", now, contract_sha))
            continue
        if len(exact) != 1 or exact[0].quote_identity in duplicate_quote_ids:
            results.append(_empty_result(candidate, PriceDisposition.UNPRICED_AMBIGUOUS_QUOTE,
                "duplicate exact provider quote", now, contract_sha))
            continue
        quote = exact[0]
        age = (now - quote.observed_at.astimezone(timezone.utc)).total_seconds()
        if age < 0:
            results.append(_empty_result(candidate, PriceDisposition.UNPRICED_FUTURE_QUOTE,
                "quote is future-dated", now, contract_sha, quote, age))
            continue
        if age > max_quote_age_seconds:
            results.append(_empty_result(candidate, PriceDisposition.UNPRICED_STALE_QUOTE,
                "quote exceeds freshness policy", now, contract_sha, quote, age))
            continue
        if quote.settlement_equivalence_authority is SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN:
            results.append(_empty_result(candidate,
                PriceDisposition.UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN,
                "reviewed settlement equivalence is absent", now, contract_sha, quote, age))
            continue
        try:
            returns, ev = _settlement_ev(candidate, quote.decimal_odds)
        except PriceAllError:
            results.append(_empty_result(candidate,
                PriceDisposition.BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE,
                "full settlement probability representation is required", now, contract_sha, quote, age))
            continue
        devig, overround, fair = _partition_quotes(candidate, quote, quote_values)
        results.append(PriceAllValueResult(
            candidate=candidate,
            disposition=PriceDisposition.PRICED,
            reason="exact verified quote priced without routing or selection",
            quote=quote,
            evaluation_time=now,
            quote_age_seconds=age,
            raw_implied_probability=1.0 / quote.decimal_odds,
            devig_status=devig,
            devig_method=("PROPORTIONAL_MULTIPLICATIVE" if fair is not None else None),
            overround=overround,
            fair_probability=fair,
            settlement_returns=returns,
            expected_return_multiplier=1.0 + ev,
            net_expected_value=ev,
            ev_percentage=ev * 100.0,
            contract_sha256=contract_sha,
        ))
    return tuple(results)


__all__ = [name for name in globals() if not name.startswith("_")]
