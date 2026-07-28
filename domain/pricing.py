"""Validation and pricing for genuine, exact-selection bookmaker quotes."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional, Sequence, Tuple

from domain.markets import (
    MARKET_REGISTRY,
    CanonicalSelection,
    MarketRegistryError,
    MarketId,
    OutcomeId,
    validate_selection,
)


@dataclass(frozen=True)
class BookmakerQuote:
    market_id: MarketId
    outcome_id: OutcomeId
    line: Optional[float]
    bookmaker_odds: float
    source: str
    is_genuine: bool
    is_current: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BookmakerQuote":
        market_id, outcome_id, line = validate_selection(
            value.get("market_id"),
            value.get("outcome_id"),
            value.get("line"),
        )
        odds = value.get("bookmaker_odds", value.get("odds"))
        if (
            not isinstance(odds, (int, float))
            or isinstance(odds, bool)
            or not math.isfinite(float(odds))
            or float(odds) <= 1.0
        ):
            raise ValueError("Bookmaker odds must be finite decimal odds above 1.0")
        source = value.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("A bookmaker quote requires an explicit source")
        return cls(
            market_id=market_id,
            outcome_id=outcome_id,
            line=line,
            bookmaker_odds=float(odds),
            source=source.strip(),
            is_genuine=value.get("is_genuine") is True,
            is_current=value.get("is_current") is True,
        )

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "bookmaker_odds": self.bookmaker_odds,
            "source": self.source,
            "is_genuine": self.is_genuine,
            "is_current": self.is_current,
        }


@dataclass(frozen=True)
class SelectionPricing:
    bookmaker_quote: BookmakerQuote
    bookmaker_probability: float
    edge_pp: float
    kelly_stake_pct: float
    method: str = "multiplicative_devig"


def parse_bookmaker_quotes(raw: Any) -> Tuple[BookmakerQuote, ...]:
    """Accept only explicit quote records; legacy scalar/verdict maps are unpriced."""
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    quotes = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        try:
            quote = BookmakerQuote.from_mapping(item)
        except (MarketRegistryError, TypeError, ValueError):
            continue
        if quote.is_genuine and quote.is_current:
            quotes.append(quote)
    return tuple(quotes)


def quote_matches_selection(
    quote: BookmakerQuote,
    selection: CanonicalSelection,
) -> bool:
    return (
        quote.market_id == selection.market_id
        and quote.outcome_id == selection.outcome_id
        and quote.line == selection.line
    )


def price_selection(
    selection: CanonicalSelection,
    model_probability: float,
    quotes: Sequence[BookmakerQuote],
    *,
    kelly_fraction_used: float = 1 / 8,
) -> tuple[Optional[SelectionPricing], str]:
    """Price a selection only from a complete, current market outcome set."""
    market_quotes = [
        quote
        for quote in quotes
        if quote.market_id == selection.market_id
        and quote.line == selection.line
    ]
    exact = next(
        (
            quote
            for quote in market_quotes
            if quote_matches_selection(quote, selection)
        ),
        None,
    )
    if exact is None:
        return None, "Pricing validation is pending: no genuine current bookmaker odds match the exact market, outcome, and line."

    supported_outcomes = MARKET_REGISTRY[
        selection.market_id
    ].supported_outcomes
    required_outcomes = set(supported_outcomes)
    quote_by_outcome = {quote.outcome_id: quote for quote in market_quotes}
    if not required_outcomes.issubset(quote_by_outcome):
        return None, "Pricing validation is pending: the bookmaker market is incomplete, so implied probabilities cannot be de-vigged."

    ordered = [quote_by_outcome[outcome] for outcome in supported_outcomes]
    raw_probabilities = [1.0 / quote.bookmaker_odds for quote in ordered]
    overround = sum(raw_probabilities)
    if overround <= 0:
        return None, "Pricing validation failed: bookmaker implied probability could not be calculated."
    fair_by_outcome = {
        quote.outcome_id: raw / overround
        for quote, raw in zip(ordered, raw_probabilities)
    }
    bookmaker_probability = fair_by_outcome[selection.outcome_id]
    edge_pp = (float(model_probability) - bookmaker_probability) * 100
    b = exact.bookmaker_odds - 1.0
    full_kelly = (
        (float(model_probability) * exact.bookmaker_odds - 1.0) / b
    )
    kelly = max(0.0, full_kelly) * kelly_fraction_used * 100
    return (
        SelectionPricing(
            bookmaker_quote=exact,
            bookmaker_probability=bookmaker_probability,
            edge_pp=edge_pp,
            kelly_stake_pct=kelly,
        ),
        "",
    )


__all__ = [
    "BookmakerQuote",
    "SelectionPricing",
    "parse_bookmaker_quotes",
    "price_selection",
    "quote_matches_selection",
]
