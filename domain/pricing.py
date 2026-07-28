"""Validation and pricing for genuine, exact-selection bookmaker quotes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from domain.markets import (
    MARKET_REGISTRY,
    CanonicalSelection,
    MarketRegistryError,
    MarketId,
    OutcomeId,
    validate_selection,
)

DEFAULT_MAX_QUOTE_AGE_SECONDS = 15 * 60


def parse_observed_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A bookmaker quote requires observed_at")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        observed_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    return observed_at.astimezone(timezone.utc)


@dataclass(frozen=True)
class BookmakerQuote:
    market_id: MarketId
    outcome_id: OutcomeId
    line: Optional[float]
    bookmaker_odds: float
    source: str
    quote_snapshot_id: str
    observed_at: datetime
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
        snapshot_id = value.get("quote_snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError(
                "A bookmaker quote requires quote_snapshot_id"
            )
        return cls(
            market_id=market_id,
            outcome_id=outcome_id,
            line=line,
            bookmaker_odds=float(odds),
            source=source.strip(),
            quote_snapshot_id=snapshot_id.strip(),
            observed_at=parse_observed_at(value.get("observed_at")),
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
            "quote_snapshot_id": self.quote_snapshot_id,
            "observed_at": self.observed_at.isoformat(),
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


def parse_bookmaker_quotes(
    raw: Any,
    *,
    current_time: Optional[datetime] = None,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
) -> Tuple[BookmakerQuote, ...]:
    """Accept only explicit quote records; legacy scalar/verdict maps are unpriced."""
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    if max_quote_age_seconds <= 0:
        raise ValueError("max_quote_age_seconds must be positive")
    now = current_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("current_time must include a timezone")
    now = now.astimezone(timezone.utc)
    max_age = timedelta(seconds=max_quote_age_seconds)
    quotes = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        try:
            quote = BookmakerQuote.from_mapping(item)
        except (MarketRegistryError, TypeError, ValueError):
            continue
        age = now - quote.observed_at
        if (
            quote.is_genuine
            and quote.is_current
            and timedelta(0) <= age <= max_age
        ):
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
    if not any(
        quote_matches_selection(quote, selection)
        for quote in market_quotes
    ):
        return None, "Pricing validation is pending: no genuine current bookmaker odds match the exact market, outcome, and line."

    supported_outcomes = MARKET_REGISTRY[
        selection.market_id
    ].supported_outcomes
    required_outcomes = set(supported_outcomes)
    grouped: Dict[
        tuple[str, MarketId, Optional[float], str],
        list[BookmakerQuote],
    ] = {}
    for quote in market_quotes:
        group_key = (
            quote.source,
            quote.market_id,
            quote.line,
            quote.quote_snapshot_id,
        )
        grouped.setdefault(group_key, []).append(quote)

    complete_groups = []
    for group_key, group_quotes in grouped.items():
        quotes_by_outcome: Dict[OutcomeId, list[BookmakerQuote]] = {}
        for quote in group_quotes:
            quotes_by_outcome.setdefault(quote.outcome_id, []).append(quote)
        if (
            set(quotes_by_outcome) == required_outcomes
            and all(
                len(outcome_quotes) == 1
                for outcome_quotes in quotes_by_outcome.values()
            )
        ):
            complete_groups.append((group_key, quotes_by_outcome))

    if not complete_groups:
        return None, "Pricing validation is pending: the bookmaker market is incomplete, so implied probabilities cannot be de-vigged."

    complete_groups.sort(
        key=lambda item: (
            max(
                quote.observed_at
                for quotes_for_outcome in item[1].values()
                for quote in quotes_for_outcome
            ),
            item[0][0],
            item[0][3],
        ),
        reverse=True,
    )
    _, grouped_quotes = complete_groups[0]
    quote_by_outcome = {
        outcome: outcome_quotes[0]
        for outcome, outcome_quotes in grouped_quotes.items()
    }
    exact = quote_by_outcome[selection.outcome_id]
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
    "DEFAULT_MAX_QUOTE_AGE_SECONDS",
    "BookmakerQuote",
    "SelectionPricing",
    "parse_bookmaker_quotes",
    "parse_observed_at",
    "price_selection",
    "quote_matches_selection",
]
