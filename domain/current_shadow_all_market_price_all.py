"""Research-only Shadow Price-all for all 15 canonical markets (PR D).

Consumes PR-C analytical assessments + source-bound ShadowExactQuote rows.
Quotes must be issued by build_shadow_exact_quote (inventory join).
Does not mint Phase-6 CalibratedValueCandidate. Does not route or bet.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from domain.markets import MARKET_REGISTRY, MarketId
from domain._all_market_shadow_types import (
    CurrentAllMarketShadowFixtureScan,
    ShadowDisposition,
)
from domain._current_shadow_price_types import (
    SOURCE_BOUND_ISSUANCE_TOKEN,
    ShadowExactQuote,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowPriceResult,
    _sha256,
)
from domain._current_shadow_quote_binding import (
    build_shadow_exact_quote,
    build_shadow_exact_quotes_from_observations,
)
from domain._current_shadow_price_helpers import _empty, _price_one


def _scan_sha(scan: CurrentAllMarketShadowFixtureScan) -> str:
    return _sha256(scan.to_dict())


def price_all_shadow_fixture(
    scan: CurrentAllMarketShadowFixtureScan,
    quotes: Sequence[ShadowExactQuote],
    *,
    evaluation_time: datetime,
) -> tuple[ShadowPriceResult, ...]:
    """Price every PR-C market/outcome/line against source-bound exact quotes.

    Retains negative EV, blocked, and unpriced rows. No prefilter before Router.
    Fixture identity always comes from the PR-C scan (never 'UNKNOWN').
    """

    if type(scan) is not CurrentAllMarketShadowFixtureScan:
        raise ShadowPriceError("scan must be exact CurrentAllMarketShadowFixtureScan")
    if not isinstance(quotes, Sequence) or isinstance(quotes, (str, bytes)):
        raise ShadowPriceError("quotes must be a sequence of ShadowExactQuote")
    fixture_identity = scan.fixture_identity
    for quote in quotes:
        if type(quote) is not ShadowExactQuote:
            raise ShadowPriceError("quotes must be exact ShadowExactQuote instances")
        if quote.source_bound_issuance != SOURCE_BOUND_ISSUANCE_TOKEN:
            raise ShadowPriceError("quote is not source-bound issued")
        if quote.fixture_identity != fixture_identity:
            raise ShadowPriceError("quote fixture_identity does not match scan")

    prc_sha = _scan_sha(scan)
    sealed = None if scan.research_xg is None else scan.research_xg.sealed_prediction_sha256
    history = None if scan.research_xg is None else scan.research_xg.history_prefix_identity

    results: list[ShadowPriceResult] = []
    seen_markets: set[MarketId] = set()

    for assessment in scan.market_assessments:
        seen_markets.add(assessment.market_id)
        if assessment.disposition not in {
            ShadowDisposition.ANALYTICAL_READY,
            ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED,
        }:
            results.append(
                _empty(
                    fixture_identity=fixture_identity,
                    market_id=assessment.market_id,
                    outcome_id=MARKET_REGISTRY[assessment.market_id].supported_outcomes[0],
                    line=None,
                    disposition=ShadowPriceDisposition.AUDIT_ONLY_UPSTREAM_BLOCKED,
                    reason=assessment.blocker_reason or assessment.disposition.value,
                    provider_semantic_status=assessment.provider_semantic_status,
                    probability_method=assessment.probability_method,
                    probability_input_namespace=assessment.probability_input_namespace,
                    prc_scan_sha256=prc_sha,
                    sealed_prediction_sha256=sealed,
                    history_prefix_identity=history,
                    score_matrix_audit=assessment.score_matrix_audit,
                )
            )
            continue

        if assessment.settlement_distributions:
            for item in assessment.settlement_distributions:
                line = getattr(item.settlement, "line", None)
                p_win = float(item.settlement.full_win) + 0.5 * float(item.settlement.half_win)
                results.append(
                    _price_one(
                        assessment,
                        item.outcome_id,
                        line,
                        quotes,
                        evaluation_time,
                        p_win,
                        fixture_identity=fixture_identity,
                        prc_scan_sha256=prc_sha,
                        sealed_prediction_sha256=sealed,
                        history_prefix_identity=history,
                    )
                )
            continue

        for event in assessment.event_probabilities:
            results.append(
                _price_one(
                    assessment,
                    event.outcome_id,
                    event.line,
                    quotes,
                    evaluation_time,
                    float(event.probability),
                    fixture_identity=fixture_identity,
                    prc_scan_sha256=prc_sha,
                    sealed_prediction_sha256=sealed,
                    history_prefix_identity=history,
                )
            )

    if set(seen_markets) != set(MarketId):
        missing = sorted(set(MarketId) - seen_markets, key=lambda m: m.value)
        raise ShadowPriceError(f"PR-C scan missing markets: {missing}")

    results.sort(
        key=lambda r: (
            r.market_id.value,
            r.outcome_id.value,
            -1.0 if r.line is None else float(r.line),
            r.disposition.value,
        )
    )
    return tuple(results)


__all__ = [
    "build_shadow_exact_quote",
    "build_shadow_exact_quotes_from_observations",
    "price_all_shadow_fixture",
]
