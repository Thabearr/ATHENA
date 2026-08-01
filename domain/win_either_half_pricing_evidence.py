"""Deterministic Stage 5A pricing-evidence contracts for Win Either Half.

This module validates historical or replayed genuine bookmaker quotes. It does
not calculate edge, expected value, Kelly stakes, or betting decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId
from domain.pricing import (
    DEFAULT_MAX_QUOTE_AGE_SECONDS as PRODUCTION_DEFAULT_MAX_QUOTE_AGE_SECONDS,
)


SCHEMA_VERSION = 1
CANONICAL_DECIMAL_PLACES = 12
CANONICAL_QUANTUM = Decimal("0.000000000001")
CANONICAL_TOLERANCE = Decimal("0.000000000001")
DEFAULT_MAX_QUOTE_AGE_SECONDS = PRODUCTION_DEFAULT_MAX_QUOTE_AGE_SECONDS
DEVIG_METHOD = "multiplicative_normalization"

PERMITTED_MARKETS = (
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
)
PERMITTED_OUTCOMES = (OutcomeId.YES, OutcomeId.NO)
MARKET_TARGETS = {
    MarketId.HOME_WIN_EITHER_HALF: "home_win_either_half_yes",
    MarketId.AWAY_WIN_EITHER_HALF: "away_win_either_half_yes",
}
EVALUATION_ROLE_SPLITS = {
    "CALIBRATION_FIT_OOF": "TRAIN",
    "VALIDATION_SELECTION": "VALIDATION",
    "FINAL_TEST": "TEST",
}
BOOKMAKER_FAIR_PROBABILITY_BANDS = (
    ("[0.0,0.2)", Decimal("0.0"), Decimal("0.2"), False),
    ("[0.2,0.4)", Decimal("0.2"), Decimal("0.4"), False),
    ("[0.4,0.6)", Decimal("0.4"), Decimal("0.6"), False),
    ("[0.6,0.8)", Decimal("0.6"), Decimal("0.8"), False),
    ("[0.8,1.0]", Decimal("0.8"), Decimal("1.0"), True),
)
RESEARCH_QUOTE_FIELDS = (
    "schema_version",
    "fixture_identifier",
    "market_id",
    "outcome_id",
    "line",
    "source",
    "quote_snapshot_id",
    "observed_at",
    "fixture_kickoff",
    "decimal_odds",
    "is_genuine",
    "provider_event_identifier",
    "provider_market_identifier",
    "provider_selection_identifier",
)


class PricingEvidenceError(ValueError):
    """A bounded Stage 5A validation or configuration error."""


class EvidenceStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceReason(str, Enum):
    UNKNOWN_FIXTURE = "UNKNOWN_FIXTURE"
    UNKNOWN_MARKET = "UNKNOWN_MARKET"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    INVALID_LINE = "INVALID_LINE"
    INVALID_ODDS = "INVALID_ODDS"
    NOT_GENUINE = "NOT_GENUINE"
    MISSING_SOURCE = "MISSING_SOURCE"
    MISSING_SNAPSHOT_ID = "MISSING_SNAPSHOT_ID"
    MISSING_PROVIDER_IDENTIFIER = "MISSING_PROVIDER_IDENTIFIER"
    MISSING_DECISION_AT = "MISSING_DECISION_AT"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    FIXTURE_KICKOFF_MISMATCH = "FIXTURE_KICKOFF_MISMATCH"
    OBSERVED_AFTER_DECISION = "OBSERVED_AFTER_DECISION"
    OBSERVED_AFTER_KICKOFF = "OBSERVED_AFTER_KICKOFF"
    DECISION_AT_OR_AFTER_KICKOFF = "DECISION_AT_OR_AFTER_KICKOFF"
    STALE_AT_DECISION = "STALE_AT_DECISION"
    INCOMPLETE_MARKET = "INCOMPLETE_MARKET"
    DUPLICATE_OUTCOME = "DUPLICATE_OUTCOME"
    MIXED_FIXTURE = "MIXED_FIXTURE"
    MIXED_MARKET = "MIXED_MARKET"
    MIXED_SOURCE = "MIXED_SOURCE"
    MIXED_SNAPSHOT = "MIXED_SNAPSHOT"
    MIXED_OBSERVED_AT = "MIXED_OBSERVED_AT"
    PROVIDER_MAPPING_MISMATCH = "PROVIDER_MAPPING_MISMATCH"
    NON_FINITE_RESULT = "NON_FINITE_RESULT"
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"


def _normalized_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _reason_tuple(reasons: Sequence[EvidenceReason]) -> tuple[EvidenceReason, ...]:
    return tuple(sorted(set(reasons), key=lambda reason: reason.value))


def _parse_timestamp(value: Any) -> tuple[Optional[datetime], Optional[EvidenceReason]]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None, EvidenceReason.INVALID_TIMESTAMP
    else:
        return None, EvidenceReason.INVALID_TIMESTAMP
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, EvidenceReason.NAIVE_TIMESTAMP
    return parsed.astimezone(timezone.utc), None


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _decimal_odds(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed <= Decimal("1"):
        return None
    return parsed


def canonical_decimal(value: Decimal | float | int) -> float:
    """Return a finite value canonically rounded to twelve decimal places."""
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise PricingEvidenceError("A numerical result is not finite") from error
    if not parsed.is_finite():
        raise PricingEvidenceError("A numerical result is not finite")
    return float(parsed.quantize(CANONICAL_QUANTUM, rounding=ROUND_HALF_EVEN))


def canonical_decimal_text(value: Decimal | float | int) -> str:
    return format(canonical_decimal(value), f".{CANONICAL_DECIMAL_PLACES}f")


@dataclass(frozen=True)
class KnownFixture:
    fixture_identifier: str
    market_id: MarketId
    kickoff: datetime
    evaluation_role: str

    def __post_init__(self) -> None:
        if not _normalized_text(self.fixture_identifier):
            raise PricingEvidenceError("Known fixture identity is required")
        if self.market_id not in PERMITTED_MARKETS:
            raise PricingEvidenceError("Known fixture market is unsupported")
        if self.kickoff.tzinfo is None or self.kickoff.utcoffset() is None:
            raise PricingEvidenceError("Known fixture kickoff must be timezone-aware")
        if self.evaluation_role not in EVALUATION_ROLE_SPLITS:
            raise PricingEvidenceError("Known fixture evaluation role is unsupported")


@dataclass(frozen=True)
class ProviderSelectionMapping:
    source: str
    provider_event_identifier: str
    provider_market_identifier: str
    provider_selection_identifier: str
    fixture_identifier: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: None = None

    @property
    def lookup_key(self) -> tuple[str, str, str, str]:
        return (
            self.source,
            self.provider_event_identifier,
            self.provider_market_identifier,
            self.provider_selection_identifier,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProviderSelectionMapping":
        required = (
            "source",
            "provider_event_identifier",
            "provider_market_identifier",
            "provider_selection_identifier",
            "fixture_identifier",
        )
        text = {name: _normalized_text(value.get(name)) for name in required}
        if any(text[name] is None for name in required):
            raise PricingEvidenceError("Provider mapping identifiers are required")
        try:
            market_id = MarketId(value.get("market_id"))
            outcome_id = OutcomeId(value.get("outcome_id"))
        except (TypeError, ValueError) as error:
            raise PricingEvidenceError("Provider mapping must use canonical IDs") from error
        if market_id not in PERMITTED_MARKETS or outcome_id not in PERMITTED_OUTCOMES:
            raise PricingEvidenceError("Provider mapping selection is unsupported")
        if value.get("line") is not None:
            raise PricingEvidenceError("Win Either Half provider mappings require null line")
        return cls(
            source=text["source"],
            provider_event_identifier=text["provider_event_identifier"],
            provider_market_identifier=text["provider_market_identifier"],
            provider_selection_identifier=text["provider_selection_identifier"],
            fixture_identifier=text["fixture_identifier"],
            market_id=market_id,
            outcome_id=outcome_id,
        )


def build_provider_mapping_registry(
    mappings: Sequence[ProviderSelectionMapping],
) -> dict[tuple[str, str, str, str], ProviderSelectionMapping]:
    registry = {}
    for mapping in mappings:
        if mapping.lookup_key in registry:
            raise PricingEvidenceError("Duplicate provider mapping is not allowed")
        registry[mapping.lookup_key] = mapping
    return registry


@dataclass(frozen=True)
class ResearchQuoteRecord:
    schema_version: int
    fixture_identifier: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: None
    source: str
    quote_snapshot_id: str
    observed_at: datetime
    fixture_kickoff: datetime
    decision_at: datetime
    decimal_odds: Decimal
    is_genuine: bool
    provider_event_identifier: str
    provider_market_identifier: str
    provider_selection_identifier: str
    evaluation_role: str

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "fixture_identifier": self.fixture_identifier,
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": None,
            "source": self.source,
            "quote_snapshot_id": self.quote_snapshot_id,
            "observed_at": _timestamp_text(self.observed_at),
            "fixture_kickoff": _timestamp_text(self.fixture_kickoff),
            "decision_at": _timestamp_text(self.decision_at),
            "decimal_odds": canonical_decimal(self.decimal_odds),
            "is_genuine": self.is_genuine,
            "provider_event_identifier": self.provider_event_identifier,
            "provider_market_identifier": self.provider_market_identifier,
            "provider_selection_identifier": self.provider_selection_identifier,
            "evaluation_role": self.evaluation_role,
        }


@dataclass(frozen=True)
class QuoteValidationResult:
    status: EvidenceStatus
    reasons: tuple[EvidenceReason, ...]
    record: Optional[ResearchQuoteRecord]
    source_row_number: Optional[int] = None
    audit_fields: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.status is EvidenceStatus.ACCEPTED and (
            self.record is None or self.reasons
        ):
            raise PricingEvidenceError("Accepted quote result is inconsistent")
        if self.status is not EvidenceStatus.ACCEPTED and not self.reasons:
            raise PricingEvidenceError("Rejected quote result requires reasons")

    def audit_dict(self) -> dict:
        return dict(self.audit_fields)


def _bounded_audit_fields(value: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    fields = {}
    for name in RESEARCH_QUOTE_FIELDS:
        raw = value.get(name)
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            rendered = raw
        else:
            rendered = str(raw)
        if isinstance(rendered, str):
            rendered = rendered[:160]
        fields[name] = rendered
    return tuple(sorted(fields.items()))


def validate_research_quote(
    value: Mapping[str, Any],
    *,
    fixture_catalog: Mapping[tuple[str, MarketId], KnownFixture],
    provider_mappings: Mapping[
        tuple[str, str, str, str], ProviderSelectionMapping
    ],
    decision_at: Any,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    source_row_number: Optional[int] = None,
) -> QuoteValidationResult:
    """Validate one quote without fuzzy identifiers or silent defaults."""
    if (
        isinstance(max_quote_age_seconds, bool)
        or not isinstance(max_quote_age_seconds, int)
        or max_quote_age_seconds <= 0
    ):
        raise PricingEvidenceError("Maximum quote age must be a positive integer")
    reasons: list[EvidenceReason] = []
    audit_fields = _bounded_audit_fields(value)
    if value.get("schema_version") != SCHEMA_VERSION:
        reasons.append(EvidenceReason.UNSUPPORTED_SCHEMA_VERSION)

    fixture_identifier = _normalized_text(value.get("fixture_identifier"))
    try:
        market_id = MarketId(value.get("market_id"))
        if market_id not in PERMITTED_MARKETS:
            raise ValueError
    except (TypeError, ValueError):
        market_id = None
        reasons.append(EvidenceReason.UNKNOWN_MARKET)
    try:
        outcome_id = OutcomeId(value.get("outcome_id"))
        if outcome_id not in PERMITTED_OUTCOMES:
            raise ValueError
    except (TypeError, ValueError):
        outcome_id = None
        reasons.append(EvidenceReason.UNKNOWN_OUTCOME)
    if value.get("line") is not None:
        reasons.append(EvidenceReason.INVALID_LINE)

    fixture = (
        fixture_catalog.get((fixture_identifier, market_id))
        if fixture_identifier and market_id
        else None
    )
    if fixture is None:
        reasons.append(EvidenceReason.UNKNOWN_FIXTURE)

    source = _normalized_text(value.get("source"))
    if source is None:
        reasons.append(EvidenceReason.MISSING_SOURCE)
    snapshot_id = _normalized_text(value.get("quote_snapshot_id"))
    if snapshot_id is None:
        reasons.append(EvidenceReason.MISSING_SNAPSHOT_ID)
    provider_names = (
        "provider_event_identifier",
        "provider_market_identifier",
        "provider_selection_identifier",
    )
    provider_values = {
        name: _normalized_text(value.get(name)) for name in provider_names
    }
    if any(provider_values[name] is None for name in provider_names):
        reasons.append(EvidenceReason.MISSING_PROVIDER_IDENTIFIER)

    odds = _decimal_odds(value.get("decimal_odds"))
    if odds is None:
        reasons.append(EvidenceReason.INVALID_ODDS)
    if value.get("is_genuine") is not True:
        reasons.append(EvidenceReason.NOT_GENUINE)

    observed_at, observed_error = _parse_timestamp(value.get("observed_at"))
    kickoff, kickoff_error = _parse_timestamp(value.get("fixture_kickoff"))
    parsed_decision, decision_error = _parse_timestamp(decision_at)
    for error in (observed_error, kickoff_error, decision_error):
        if error is not None:
            reasons.append(error)
    if decision_at is None:
        reasons.append(EvidenceReason.MISSING_DECISION_AT)

    if fixture is not None and kickoff is not None:
        frozen_kickoff = fixture.kickoff.astimezone(timezone.utc)
        if kickoff != frozen_kickoff:
            reasons.append(EvidenceReason.FIXTURE_KICKOFF_MISMATCH)

    if source is not None and all(provider_values.values()):
        mapping_key = (
            source,
            provider_values["provider_event_identifier"],
            provider_values["provider_market_identifier"],
            provider_values["provider_selection_identifier"],
        )
        mapping = provider_mappings.get(mapping_key)
        if (
            mapping is None
            or mapping.fixture_identifier != fixture_identifier
            or mapping.market_id != market_id
            or mapping.outcome_id != outcome_id
            or mapping.line is not None
        ):
            reasons.append(EvidenceReason.PROVIDER_MAPPING_MISMATCH)

    if observed_at is not None and parsed_decision is not None:
        if observed_at > parsed_decision:
            reasons.append(EvidenceReason.OBSERVED_AFTER_DECISION)
        else:
            age = parsed_decision - observed_at
            if age > timedelta(seconds=max_quote_age_seconds):
                reasons.append(EvidenceReason.STALE_AT_DECISION)
    if observed_at is not None and kickoff is not None and observed_at >= kickoff:
        reasons.append(EvidenceReason.OBSERVED_AFTER_KICKOFF)
    if parsed_decision is not None and kickoff is not None and parsed_decision >= kickoff:
        reasons.append(EvidenceReason.DECISION_AT_OR_AFTER_KICKOFF)

    normalized_reasons = _reason_tuple(reasons)
    if normalized_reasons:
        return QuoteValidationResult(
            status=EvidenceStatus.REJECTED,
            reasons=normalized_reasons,
            record=None,
            source_row_number=source_row_number,
            audit_fields=audit_fields,
        )
    assert fixture is not None
    assert market_id is not None and outcome_id is not None
    assert source is not None and snapshot_id is not None
    assert observed_at is not None and kickoff is not None and parsed_decision is not None
    assert odds is not None
    return QuoteValidationResult(
        status=EvidenceStatus.ACCEPTED,
        reasons=(),
        source_row_number=source_row_number,
        audit_fields=audit_fields,
        record=ResearchQuoteRecord(
            schema_version=SCHEMA_VERSION,
            fixture_identifier=fixture_identifier,
            market_id=market_id,
            outcome_id=outcome_id,
            line=None,
            source=source,
            quote_snapshot_id=snapshot_id,
            observed_at=observed_at,
            fixture_kickoff=kickoff,
            decision_at=parsed_decision,
            decimal_odds=odds,
            is_genuine=True,
            provider_event_identifier=provider_values["provider_event_identifier"],
            provider_market_identifier=provider_values["provider_market_identifier"],
            provider_selection_identifier=provider_values[
                "provider_selection_identifier"
            ],
            evaluation_role=fixture.evaluation_role,
        ),
    )


@dataclass(frozen=True)
class PricedSnapshot:
    fixture_identifier: str
    market_id: MarketId
    source: str
    quote_snapshot_id: str
    observed_at: datetime
    fixture_kickoff: datetime
    decision_at: datetime
    evaluation_role: str
    yes_odds: Decimal
    no_odds: Decimal
    yes_raw_implied_probability: float
    no_raw_implied_probability: float
    overround: float
    yes_fair_probability: float
    no_fair_probability: float
    devig_method: str = DEVIG_METHOD

    def to_dict(self) -> dict:
        return {
            "fixture_identifier": self.fixture_identifier,
            "market_id": self.market_id.value,
            "line": None,
            "source": self.source,
            "quote_snapshot_id": self.quote_snapshot_id,
            "observed_at": _timestamp_text(self.observed_at),
            "fixture_kickoff": _timestamp_text(self.fixture_kickoff),
            "decision_at": _timestamp_text(self.decision_at),
            "evaluation_role": self.evaluation_role,
            "yes_odds": canonical_decimal(self.yes_odds),
            "no_odds": canonical_decimal(self.no_odds),
            "yes_raw_implied_probability": self.yes_raw_implied_probability,
            "no_raw_implied_probability": self.no_raw_implied_probability,
            "overround": self.overround,
            "yes_fair_probability": self.yes_fair_probability,
            "no_fair_probability": self.no_fair_probability,
            "devig_method": self.devig_method,
            "yes_fair_probability_band": bookmaker_fair_probability_band(
                self.yes_fair_probability
            ),
            "no_fair_probability_band": bookmaker_fair_probability_band(
                self.no_fair_probability
            ),
        }


@dataclass(frozen=True)
class SnapshotValidationResult:
    status: EvidenceStatus
    reasons: tuple[EvidenceReason, ...]
    records: tuple[ResearchQuoteRecord, ...]
    snapshot: Optional[PricedSnapshot]
    selected: bool = False


def validate_complete_snapshot(
    records: Sequence[ResearchQuoteRecord],
) -> SnapshotValidationResult:
    """Require an exact same-source, same-snapshot YES/NO market."""
    records = tuple(records)
    if not records:
        return SnapshotValidationResult(
            EvidenceStatus.UNAVAILABLE,
            (EvidenceReason.INCOMPLETE_MARKET,),
            (),
            None,
        )
    reasons: list[EvidenceReason] = []
    if len({record.fixture_identifier for record in records}) != 1:
        reasons.append(EvidenceReason.MIXED_FIXTURE)
    if len({record.market_id for record in records}) != 1:
        reasons.append(EvidenceReason.MIXED_MARKET)
    if len({record.source for record in records}) != 1:
        reasons.append(EvidenceReason.MIXED_SOURCE)
    if len({record.quote_snapshot_id for record in records}) != 1:
        reasons.append(EvidenceReason.MIXED_SNAPSHOT)
    if len({record.observed_at for record in records}) != 1:
        reasons.append(EvidenceReason.MIXED_OBSERVED_AT)
    if len({record.decision_at for record in records}) != 1:
        reasons.append(EvidenceReason.MIXED_OBSERVED_AT)
    if any(record.line is not None for record in records):
        reasons.append(EvidenceReason.INVALID_LINE)
    if any(record.is_genuine is not True for record in records):
        reasons.append(EvidenceReason.NOT_GENUINE)
    if (
        len({record.provider_event_identifier for record in records}) != 1
        or len({record.provider_market_identifier for record in records}) != 1
        or len({record.fixture_kickoff for record in records}) != 1
        or len({record.evaluation_role for record in records}) != 1
    ):
        reasons.append(EvidenceReason.PROVIDER_MAPPING_MISMATCH)
    outcomes: dict[OutcomeId, list[ResearchQuoteRecord]] = {}
    for record in records:
        outcomes.setdefault(record.outcome_id, []).append(record)
    if any(len(values) > 1 for values in outcomes.values()):
        reasons.append(EvidenceReason.DUPLICATE_OUTCOME)
    normalized_reasons = _reason_tuple(reasons)
    if normalized_reasons:
        return SnapshotValidationResult(
            EvidenceStatus.REJECTED, normalized_reasons, records, None
        )
    if set(outcomes) != set(PERMITTED_OUTCOMES):
        return SnapshotValidationResult(
            EvidenceStatus.UNAVAILABLE,
            (EvidenceReason.INCOMPLETE_MARKET,),
            records,
            None,
        )

    yes = outcomes[OutcomeId.YES][0]
    no = outcomes[OutcomeId.NO][0]
    try:
        yes_raw = Decimal(1) / yes.decimal_odds
        no_raw = Decimal(1) / no.decimal_odds
        overround = yes_raw + no_raw
        if not overround.is_finite() or overround <= 0:
            raise ArithmeticError
        yes_fair = yes_raw / overround
        no_fair = no_raw / overround
        values = (yes_raw, no_raw, overround, yes_fair, no_fair)
        if any(not value.is_finite() for value in values):
            raise ArithmeticError
        if not (Decimal(0) <= yes_fair <= Decimal(1)) or not (
            Decimal(0) <= no_fair <= Decimal(1)
        ):
            raise ArithmeticError
        canonical_yes_fair = Decimal(canonical_decimal_text(yes_fair))
        canonical_no_fair = Decimal(canonical_decimal_text(no_fair))
        if abs(canonical_yes_fair + canonical_no_fair - Decimal(1)) > (
            CANONICAL_TOLERANCE
        ):
            raise ArithmeticError
    except (ArithmeticError, InvalidOperation, ZeroDivisionError):
        return SnapshotValidationResult(
            EvidenceStatus.REJECTED,
            (EvidenceReason.NON_FINITE_RESULT,),
            records,
            None,
        )
    snapshot = PricedSnapshot(
        fixture_identifier=yes.fixture_identifier,
        market_id=yes.market_id,
        source=yes.source,
        quote_snapshot_id=yes.quote_snapshot_id,
        observed_at=yes.observed_at,
        fixture_kickoff=yes.fixture_kickoff,
        decision_at=yes.decision_at,
        evaluation_role=yes.evaluation_role,
        yes_odds=yes.decimal_odds,
        no_odds=no.decimal_odds,
        yes_raw_implied_probability=canonical_decimal(yes_raw),
        no_raw_implied_probability=canonical_decimal(no_raw),
        overround=canonical_decimal(overround),
        yes_fair_probability=canonical_decimal(yes_fair),
        no_fair_probability=canonical_decimal(no_fair),
    )
    return SnapshotValidationResult(EvidenceStatus.ACCEPTED, (), records, snapshot)


def select_latest_eligible_snapshots(
    results: Sequence[SnapshotValidationResult],
) -> tuple[SnapshotValidationResult, ...]:
    """Select latest observed snapshot per fixture, market, and bookmaker.

    If timestamps tie, the lexically greatest quote_snapshot_id wins.
    """
    winners: dict[tuple[str, MarketId, str], SnapshotValidationResult] = {}
    for result in results:
        if result.status is not EvidenceStatus.ACCEPTED or result.snapshot is None:
            continue
        snapshot = result.snapshot
        key = (snapshot.fixture_identifier, snapshot.market_id, snapshot.source)
        current = winners.get(key)
        candidate_order = (snapshot.observed_at, snapshot.quote_snapshot_id)
        current_order = (
            (current.snapshot.observed_at, current.snapshot.quote_snapshot_id)
            if current is not None and current.snapshot is not None
            else None
        )
        if current_order is None or candidate_order > current_order:
            winners[key] = result
    selected_ids = {id(result) for result in winners.values()}
    return tuple(
        SnapshotValidationResult(
            result.status,
            result.reasons,
            result.records,
            result.snapshot,
            selected=id(result) in selected_ids,
        )
        for result in results
    )


def bookmaker_fair_probability_band(probability: Any) -> str:
    if isinstance(probability, bool):
        raise PricingEvidenceError("Bookmaker fair probability must be finite")
    try:
        value = Decimal(str(probability))
    except (InvalidOperation, ValueError) as error:
        raise PricingEvidenceError("Bookmaker fair probability must be finite") from error
    if not value.is_finite() or not Decimal(0) <= value <= Decimal(1):
        raise PricingEvidenceError("Bookmaker fair probability must be in [0, 1]")
    for name, lower, upper, inclusive_upper in BOOKMAKER_FAIR_PROBABILITY_BANDS:
        if value >= lower and (value <= upper if inclusive_upper else value < upper):
            return name
    raise PricingEvidenceError("Bookmaker fair probability band is unavailable")


__all__ = [
    "BOOKMAKER_FAIR_PROBABILITY_BANDS",
    "CANONICAL_DECIMAL_PLACES",
    "CANONICAL_TOLERANCE",
    "DEFAULT_MAX_QUOTE_AGE_SECONDS",
    "DEVIG_METHOD",
    "EVALUATION_ROLE_SPLITS",
    "EvidenceReason",
    "EvidenceStatus",
    "KnownFixture",
    "MARKET_TARGETS",
    "PERMITTED_MARKETS",
    "PERMITTED_OUTCOMES",
    "PricedSnapshot",
    "PricingEvidenceError",
    "ProviderSelectionMapping",
    "QuoteValidationResult",
    "RESEARCH_QUOTE_FIELDS",
    "ResearchQuoteRecord",
    "SCHEMA_VERSION",
    "SnapshotValidationResult",
    "bookmaker_fair_probability_band",
    "build_provider_mapping_registry",
    "canonical_decimal",
    "canonical_decimal_text",
    "select_latest_eligible_snapshots",
    "validate_complete_snapshot",
    "validate_research_quote",
]
