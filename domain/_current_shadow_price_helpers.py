"""Internal Price-all helpers (PR D)."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId
from domain._all_market_shadow_types import ShadowDisposition, ShadowMarketAssessment
from domain._current_shadow_price_types import (
    MAX_QUOTE_AGE_SECONDS,
    ORDINARY_PARTITIONS,
    OVERLAPPING_MARKETS,
    PUSH_SPLIT_MARKETS,
    ShadowDevigStatus,
    ShadowExactQuote,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowPriceResult,
    settlement_unit_return,
)


def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ShadowPriceError("evaluation_time must be timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _provider_blocked(status: Optional[str]) -> bool:
    if status is None:
        return False
    if status in {"SUPPORTED", "SUPPORTED_WITH_EXACT_LINE_POLICY"}:
        return False
    return True


def _empty(
    *,
    fixture_identity: str,
    market_id: MarketId,
    outcome_id: OutcomeId,
    line: Optional[float],
    disposition: ShadowPriceDisposition,
    reason: str,
    model_probability: Optional[float] = None,
    provider_semantic_status: Optional[str] = None,
    probability_method: Optional[str] = None,
    probability_input_namespace: Optional[str] = None,
    prc_scan_sha256: Optional[str] = None,
    sealed_prediction_sha256: Optional[str] = None,
    history_prefix_identity: Optional[str] = None,
    score_matrix_audit: Optional[Mapping[str, object]] = None,
) -> ShadowPriceResult:
    return ShadowPriceResult(
        fixture_identity=fixture_identity,
        market_id=market_id,
        outcome_id=outcome_id,
        line=line,
        disposition=disposition,
        model_probability=model_probability,
        decimal_odds=None,
        implied_probability=None,
        fair_probability=None,
        overround=None,
        devig_status=None,
        net_expected_value=None,
        expected_return_multiplier=None,
        settlement_state_probabilities=(),
        settlement_unit_returns=(),
        quote_identity_sha256=None,
        provider_event_id=None,
        provider_semantic_status=provider_semantic_status,
        rejection_reason=reason,
        probability_method=probability_method,
        probability_input_namespace=probability_input_namespace,
        prc_scan_sha256=prc_scan_sha256,
        sealed_prediction_sha256=sealed_prediction_sha256,
        history_prefix_identity=history_prefix_identity,
        score_matrix_audit=score_matrix_audit,
    )


def _match_quotes(
    quotes: Sequence[ShadowExactQuote],
    *,
    fixture_identity: str,
    market_id: MarketId,
    outcome_id: OutcomeId,
    line: Optional[float],
) -> tuple[Optional[ShadowExactQuote], Optional[ShadowPriceDisposition], Optional[str]]:
    matches = []
    for quote in quotes:
        if quote.fixture_identity != fixture_identity:
            continue
        if quote.market_id is not market_id:
            continue
        if quote.outcome_id is not outcome_id:
            continue
        if line is None and quote.line is None:
            matches.append(quote)
        elif (
            line is not None
            and quote.line is not None
            and math.isclose(float(line), float(quote.line), rel_tol=0.0, abs_tol=1e-12)
        ):
            matches.append(quote)
    if not matches:
        return None, ShadowPriceDisposition.UNPRICED_NO_EXACT_QUOTE, "no exact matching quote"
    if len(matches) > 1:
        return None, ShadowPriceDisposition.UNPRICED_AMBIGUOUS_QUOTE, "duplicate exact quotes"
    return matches[0], None, None


def _partition_peers(
    quotes: Sequence[ShadowExactQuote],
    selected: ShadowExactQuote,
    outcomes: tuple[OutcomeId, ...],
) -> tuple[ShadowDevigStatus, Optional[float], Optional[float]]:
    peers: dict[OutcomeId, ShadowExactQuote] = {}
    for quote in quotes:
        if quote.fixture_identity != selected.fixture_identity:
            continue
        if quote.market_id is not selected.market_id:
            continue
        if quote.provider_event_id != selected.provider_event_id:
            continue
        if quote.provider_market_id != selected.provider_market_id:
            continue
        if quote.provider_specifier != selected.provider_specifier:
            continue
        if quote.line != selected.line and not (
            quote.line is not None
            and selected.line is not None
            and math.isclose(quote.line, selected.line, abs_tol=1e-12)
        ):
            continue
        if quote.source_inventory_sha256 != selected.source_inventory_sha256:
            return ShadowDevigStatus.CROSS_SNAPSHOT, None, None
        if quote.source_raw_sha256 != selected.source_raw_sha256:
            return ShadowDevigStatus.CROSS_SNAPSHOT, None, None
        if quote.source_manifest_sha256 != selected.source_manifest_sha256:
            return ShadowDevigStatus.CROSS_SNAPSHOT, None, None
        if quote.outcome_id in peers:
            return ShadowDevigStatus.INCOMPLETE_PARTITION, None, None
        peers[quote.outcome_id] = quote
    if set(peers) != set(outcomes):
        return ShadowDevigStatus.INCOMPLETE_PARTITION, None, None
    implied = {outcome: 1.0 / peers[outcome].decimal_odds for outcome in outcomes}
    overround = math.fsum(implied.values())
    if overround <= 0.0 or not math.isfinite(overround):
        return ShadowDevigStatus.INCOMPLETE_PARTITION, None, None
    fair = implied[selected.outcome_id] / overround
    return ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION, fair, overround


def _settlement_ev_from_assessment(
    assessment: ShadowMarketAssessment,
    outcome_id: OutcomeId,
    decimal_odds: float,
    line: Optional[float],
) -> tuple[tuple[tuple[str, float], ...], tuple[tuple[str, float], ...], float]:
    if assessment.market_id in PUSH_SPLIT_MARKETS:
        distributions = assessment.settlement_distributions
        matched = [
            item
            for item in distributions
            if item.outcome_id is outcome_id
            and (
                line is None
                or getattr(item.settlement, "line", None) is None
                or math.isclose(float(item.settlement.line), float(line), abs_tol=1e-12)
            )
        ]
        if len(matched) != 1:
            raise ShadowPriceError("settlement distribution missing for outcome/line")
        settlement = matched[0].settlement
        states: list[tuple[str, float]] = []
        mapping = (
            ("WIN", float(settlement.full_win)),
            ("HALF_WIN", float(settlement.half_win)),
            ("PUSH", float(settlement.push)),
            ("HALF_LOSS", float(settlement.half_loss)),
            ("LOSS", float(settlement.full_loss)),
        )
        for name, prob in mapping:
            if assessment.market_id is MarketId.DRAW_NO_BET and name in {"HALF_WIN", "HALF_LOSS"}:
                continue
            states.append((name, prob))
        total = math.fsum(p for _, p in states)
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ShadowPriceError("settlement mass does not sum to 1")
        returns = tuple((name, settlement_unit_return(name, decimal_odds)) for name, _ in states)
        ev = math.fsum(p * settlement_unit_return(name, decimal_odds) for name, p in states)
        return tuple(states), returns, ev

    events = [
        e
        for e in assessment.event_probabilities
        if e.outcome_id is outcome_id
        and (
            line is None
            or e.line is None
            or math.isclose(float(e.line), float(line), abs_tol=1e-12)
        )
    ]
    if len(events) != 1:
        raise ShadowPriceError("event probability missing for outcome/line")
    p_win = float(events[0].probability)
    states = (("WIN", p_win), ("LOSS", 1.0 - p_win))
    returns = (
        ("WIN", settlement_unit_return("WIN", decimal_odds)),
        ("LOSS", settlement_unit_return("LOSS", decimal_odds)),
    )
    ev = p_win * (decimal_odds - 1.0) + (1.0 - p_win) * (-1.0)
    return states, returns, ev


def _price_one(
    assessment: ShadowMarketAssessment,
    outcome_id: OutcomeId,
    line: Optional[float],
    quotes: Sequence[ShadowExactQuote],
    evaluation_time: datetime,
    model_probability: float,
    *,
    fixture_identity: str,
    prc_scan_sha256: str,
    sealed_prediction_sha256: Optional[str],
    history_prefix_identity: Optional[str],
) -> ShadowPriceResult:
    provider_status = assessment.provider_semantic_status
    ancestry = dict(
        probability_method=assessment.probability_method,
        probability_input_namespace=assessment.probability_input_namespace,
        prc_scan_sha256=prc_scan_sha256,
        sealed_prediction_sha256=sealed_prediction_sha256,
        history_prefix_identity=history_prefix_identity,
        score_matrix_audit=assessment.score_matrix_audit,
    )

    if assessment.disposition not in {
        ShadowDisposition.ANALYTICAL_READY,
        ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED,
    }:
        return _empty(
            fixture_identity=fixture_identity,
            market_id=assessment.market_id,
            outcome_id=outcome_id,
            line=line,
            disposition=ShadowPriceDisposition.UNPRICED_UPSTREAM_BLOCKED,
            reason=assessment.blocker_reason or assessment.disposition.value,
            model_probability=model_probability,
            provider_semantic_status=provider_status,
            **ancestry,
        )

    if _provider_blocked(provider_status) or assessment.disposition is ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED:
        return _empty(
            fixture_identity=fixture_identity,
            market_id=assessment.market_id,
            outcome_id=outcome_id,
            line=line,
            disposition=ShadowPriceDisposition.UNPRICED_PROVIDER_BLOCKED,
            reason=f"provider semantic status={provider_status}",
            model_probability=model_probability,
            provider_semantic_status=provider_status,
            **ancestry,
        )

    quote, bad_disp, bad_reason = _match_quotes(
        quotes,
        fixture_identity=fixture_identity,
        market_id=assessment.market_id,
        outcome_id=outcome_id,
        line=line,
    )
    if quote is None:
        return _empty(
            fixture_identity=fixture_identity,
            market_id=assessment.market_id,
            outcome_id=outcome_id,
            line=line,
            disposition=bad_disp or ShadowPriceDisposition.UNPRICED_NO_EXACT_QUOTE,
            reason=bad_reason or "no exact quote",
            model_probability=model_probability,
            provider_semantic_status=provider_status,
            **ancestry,
        )

    age = (_utc(evaluation_time) - quote.observed_at.astimezone(timezone.utc)).total_seconds()
    if age < 0:
        return _empty(
            fixture_identity=fixture_identity,
            market_id=assessment.market_id,
            outcome_id=outcome_id,
            line=line,
            disposition=ShadowPriceDisposition.UNPRICED_FUTURE_QUOTE,
            reason="quote observed_at is in the future",
            model_probability=model_probability,
            provider_semantic_status=provider_status,
            **ancestry,
        )
    if age > MAX_QUOTE_AGE_SECONDS:
        return _empty(
            fixture_identity=fixture_identity,
            market_id=assessment.market_id,
            outcome_id=outcome_id,
            line=line,
            disposition=ShadowPriceDisposition.UNPRICED_STALE_QUOTE,
            reason=f"quote age {age:.0f}s exceeds {MAX_QUOTE_AGE_SECONDS}s",
            model_probability=model_probability,
            provider_semantic_status=provider_status,
            **ancestry,
        )

    try:
        states, returns, ev = _settlement_ev_from_assessment(
            assessment, outcome_id, quote.decimal_odds, line
        )
    except ShadowPriceError as exc:
        return _empty(
            fixture_identity=fixture_identity,
            market_id=assessment.market_id,
            outcome_id=outcome_id,
            line=line,
            disposition=ShadowPriceDisposition.UNPRICED_SETTLEMENT_INCOMPLETE,
            reason=str(exc),
            model_probability=model_probability,
            provider_semantic_status=provider_status,
            **ancestry,
        )

    if assessment.market_id in OVERLAPPING_MARKETS:
        devig_status = ShadowDevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS
        fair = None
        overround = None
    elif assessment.market_id in PUSH_SPLIT_MARKETS:
        devig_status = ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
        fair = None
        overround = None
    elif assessment.market_id in ORDINARY_PARTITIONS:
        devig_status, fair, overround = _partition_peers(
            quotes, quote, ORDINARY_PARTITIONS[assessment.market_id]
        )
    else:
        devig_status = ShadowDevigStatus.NOT_APPLICABLE
        fair = None
        overround = None

    implied = 1.0 / quote.decimal_odds
    return ShadowPriceResult(
        fixture_identity=fixture_identity,
        market_id=assessment.market_id,
        outcome_id=outcome_id,
        line=line,
        disposition=ShadowPriceDisposition.PRICED,
        model_probability=model_probability,
        decimal_odds=quote.decimal_odds,
        implied_probability=implied,
        fair_probability=fair,
        overround=overround,
        devig_status=devig_status,
        net_expected_value=ev,
        expected_return_multiplier=1.0 + ev,
        settlement_state_probabilities=states,
        settlement_unit_returns=returns,
        quote_identity_sha256=quote.identity_sha256(),
        provider_event_id=quote.provider_event_id,
        provider_semantic_status=provider_status,
        rejection_reason=None,
        probability_method=assessment.probability_method,
        probability_input_namespace=assessment.probability_input_namespace,
        prc_scan_sha256=prc_scan_sha256,
        sealed_prediction_sha256=sealed_prediction_sha256,
        history_prefix_identity=history_prefix_identity,
        source_raw_sha256=quote.source_raw_sha256,
        source_manifest_sha256=quote.source_manifest_sha256,
        source_inventory_sha256=quote.source_inventory_sha256,
        observation_identity_sha256=quote.observation_identity_sha256,
        score_matrix_audit=assessment.score_matrix_audit,
    )
