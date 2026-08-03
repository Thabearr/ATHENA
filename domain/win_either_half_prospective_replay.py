"""Provider-agnostic Stage 5B2 prospective quote replay for Win Either Half.

This module measures whether exact genuine bookmaker YES/NO snapshots would
have been available and fresh at predeclared decision offsets. It does not use
match outcomes, model probabilities, edge, expected value, Kelly, stakes, or
betting decisions, and it does not select a final decision offset.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, DecimalException, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus


SCHEMA_VERSION = 1
DEFAULT_MAX_QUOTE_AGE_SECONDS = 900
MAXIMUM_CANDIDATE_OFFSET_SECONDS = 7 * 24 * 60 * 60
DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999, Emax=999)
PERMITTED_MARKETS = (
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
)
PERMITTED_OUTCOMES = (OutcomeId.YES, OutcomeId.NO)
QUALIFIED_PROSPECTIVE_STATUSES = frozenset(
    {
        "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
        "QUALIFIED_FOR_HISTORICAL_RESEARCH",
    }
)
FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "result",
        "score",
        "home_score",
        "away_score",
        "home_goals",
        "away_goals",
        "half_time_home_goals",
        "half_time_away_goals",
        "target",
        "target_value",
        "label",
        "model_probability",
        "calibrated_probability",
        "edge",
        "edge_pp",
        "expected_value",
        "kelly",
        "kelly_stake",
        "profit",
        "profitability",
        "stake",
        "bet",
        "bet_decision",
        "decision_label",
        "settled_outcome",
    }
)


class ProspectiveReplayError(ValueError):
    """A bounded prospective replay contract or validation failure."""


class ReplayStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ReplayReason(str, Enum):
    AVAILABLE = "AVAILABLE"
    NO_QUOTE_RECORDS = "NO_QUOTE_RECORDS"
    NO_STRUCTURALLY_VALID_QUOTES = "NO_STRUCTURALLY_VALID_QUOTES"
    NO_QUOTES_AT_OR_BEFORE_DECISION = "NO_QUOTES_AT_OR_BEFORE_DECISION"
    NO_FRESH_QUOTES_AT_DECISION = "NO_FRESH_QUOTES_AT_DECISION"
    NO_COMPLETE_SNAPSHOT = "NO_COMPLETE_SNAPSHOT"


class QuoteRejectionReason(str, Enum):
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
    UNKNOWN_FIXTURE = "UNKNOWN_FIXTURE"
    UNKNOWN_MARKET = "UNKNOWN_MARKET"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    INVALID_LINE = "INVALID_LINE"
    MISSING_SOURCE = "MISSING_SOURCE"
    MISSING_SNAPSHOT_ID = "MISSING_SNAPSHOT_ID"
    MISSING_PROVIDER_IDENTIFIER = "MISSING_PROVIDER_IDENTIFIER"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    FIXTURE_KICKOFF_MISMATCH = "FIXTURE_KICKOFF_MISMATCH"
    INVALID_ODDS = "INVALID_ODDS"
    NOT_GENUINE = "NOT_GENUINE"
    PROVIDER_MAPPING_MISMATCH = "PROVIDER_MAPPING_MISMATCH"
    OBSERVED_AT_OR_AFTER_KICKOFF = "OBSERVED_AT_OR_AFTER_KICKOFF"


class SupportStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    LOW_SUPPORT = "LOW_SUPPORT"
    SUPPORTED = "SUPPORTED"


@dataclass(frozen=True)
class ProspectiveFixture:
    fixture_identifier: str
    provider_event_identifier: str
    kickoff: datetime
    market_ids: tuple[MarketId, ...] = PERMITTED_MARKETS

    def __post_init__(self) -> None:
        if not _text(self.fixture_identifier):
            raise ProspectiveReplayError("Fixture identifier is required")
        if not _text(self.provider_event_identifier):
            raise ProspectiveReplayError("Provider event identifier is required")
        if self.kickoff.tzinfo is None or self.kickoff.utcoffset() is None:
            raise ProspectiveReplayError("Fixture kickoff must be timezone-aware")
        if tuple(sorted(self.market_ids, key=lambda item: item.value)) != tuple(
            sorted(PERMITTED_MARKETS, key=lambda item: item.value)
        ):
            raise ProspectiveReplayError(
                "Every prospective fixture must contain both exact Win Either Half markets"
            )


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

    @property
    def canonical_key(self) -> tuple[str, str, MarketId, OutcomeId]:
        return (self.source, self.fixture_identifier, self.market_id, self.outcome_id)


@dataclass(frozen=True)
class ProspectiveQuote:
    source_row_number: int
    fixture_identifier: str
    market_id: MarketId
    outcome_id: OutcomeId
    source: str
    quote_snapshot_id: str
    observed_at: datetime
    fixture_kickoff: datetime
    decimal_odds: Decimal
    provider_event_identifier: str
    provider_market_identifier: str
    provider_selection_identifier: str


@dataclass(frozen=True)
class QuoteParseResult:
    source_row_number: int
    record: Optional[ProspectiveQuote]
    reasons: tuple[QuoteRejectionReason, ...]
    audit_fields: tuple[tuple[str, Any], ...]

    @property
    def accepted(self) -> bool:
        return self.record is not None and not self.reasons

    def audit_dict(self) -> dict[str, Any]:
        return dict(self.audit_fields)


@dataclass(frozen=True)
class ProspectiveReplayRow:
    fixture_identifier: str
    market_id: MarketId
    source: str
    fixture_kickoff: datetime
    candidate_offset_seconds: int
    decision_at: datetime
    raw_quote_row_count: int
    structurally_valid_quote_row_count: int
    at_or_before_decision_quote_row_count: int
    fresh_quote_row_count: int
    complete_snapshot_count: int
    availability_status: ReplayStatus
    availability_reason: ReplayReason
    selected_snapshot_id: Optional[str]
    selected_observed_at: Optional[datetime]
    selected_quote_age_seconds: Optional[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "market_id": self.market_id.value,
            "source": self.source,
            "fixture_kickoff": _timestamp_text(self.fixture_kickoff),
            "candidate_offset_seconds": self.candidate_offset_seconds,
            "decision_at": _timestamp_text(self.decision_at),
            "raw_quote_row_count": self.raw_quote_row_count,
            "structurally_valid_quote_row_count": self.structurally_valid_quote_row_count,
            "at_or_before_decision_quote_row_count": self.at_or_before_decision_quote_row_count,
            "fresh_quote_row_count": self.fresh_quote_row_count,
            "complete_snapshot_count": self.complete_snapshot_count,
            "availability_status": self.availability_status.value,
            "availability_reason": self.availability_reason.value,
            "selected_snapshot_id": self.selected_snapshot_id,
            "selected_observed_at": (
                _timestamp_text(self.selected_observed_at)
                if self.selected_observed_at is not None
                else None
            ),
            "selected_quote_age_seconds": self.selected_quote_age_seconds,
        }


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _timestamp(value: Any, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ProspectiveReplayError(f"{label} must be ISO-8601") from error
    else:
        raise ProspectiveReplayError(f"{label} is required")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProspectiveReplayError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _timestamp_with_reason(
    value: Any,
) -> tuple[Optional[datetime], Optional[QuoteRejectionReason]]:
    try:
        return _timestamp(value, "timestamp"), None
    except ProspectiveReplayError as error:
        if "timezone-aware" in str(error):
            return None, QuoteRejectionReason.NAIVE_TIMESTAMP
        return None, QuoteRejectionReason.INVALID_TIMESTAMP


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _odds(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        with localcontext(DECIMAL_CONTEXT) as context:
            parsed = context.create_decimal(str(value))
    except (DecimalException, InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed <= Decimal("1"):
        return None
    return parsed


def _percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 6)


def _support_status(rows: int, minimum: int) -> SupportStatus:
    if rows == 0:
        return SupportStatus.UNAVAILABLE
    if rows < minimum:
        return SupportStatus.LOW_SUPPORT
    return SupportStatus.SUPPORTED


def reject_forbidden_fields(value: Any, *, location: str = "input") -> None:
    """Reject outcome, model-performance, value, and betting fields recursively."""
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).strip().lower()
            if key in FORBIDDEN_INPUT_KEYS:
                raise ProspectiveReplayError(
                    f"Forbidden field {raw_key!r} found in {location}"
                )
            reject_forbidden_fields(nested, location=f"{location}.{raw_key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reject_forbidden_fields(nested, location=f"{location}[{index}]")


def validate_candidate_offsets(values: Any) -> tuple[int, ...]:
    if not isinstance(values, list) or not values:
        raise ProspectiveReplayError("candidate_offsets_seconds must be a non-empty list")
    offsets: list[int] = []
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            or value > MAXIMUM_CANDIDATE_OFFSET_SECONDS
        ):
            raise ProspectiveReplayError(
                "Candidate offsets must be positive integer seconds not exceeding seven days"
            )
        offsets.append(value)
    if len(set(offsets)) != len(offsets):
        raise ProspectiveReplayError("Candidate offsets must be unique")
    return tuple(sorted(offsets, reverse=True))


def validate_source_qualification_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProspectiveReplayError("Source qualification report must be an object")
    reject_forbidden_fields(value, location="source_qualification_report")
    if value.get("schema_version") != 1 or value.get("dataset_name") != (
        "win-either-half-pricing-source-qualification-v1"
    ):
        raise ProspectiveReplayError("Unexpected source qualification report contract")
    provider_identifier = _text(value.get("provider_identifier"))
    if provider_identifier is None:
        raise ProspectiveReplayError("Qualified provider identifier is required")
    qualification = value.get("qualification")
    if not isinstance(qualification, Mapping):
        raise ProspectiveReplayError("Source qualification statuses are required")
    prospective_status = qualification.get("prospective_replay_status")
    if prospective_status not in QUALIFIED_PROSPECTIVE_STATUSES:
        raise ProspectiveReplayError(
            "Source is not qualified for prospective replay"
        )
    holdout = value.get("holdout_governance")
    if not isinstance(holdout, Mapping) or holdout.get(
        "prospective_validation_required"
    ) is not True:
        raise ProspectiveReplayError(
            "Source qualification report must preserve prospective holdout governance"
        )
    statuses = value.get("market_statuses")
    if not isinstance(statuses, Mapping) or any(
        statuses.get(market.value) != ModelStatus.DISABLED.value
        for market in PERMITTED_MARKETS
    ):
        raise ProspectiveReplayError(
            "Both Win Either Half markets must remain DISABLED"
        )
    if any(
        MODEL_STATUS_REGISTRY[market].status is not ModelStatus.DISABLED
        for market in PERMITTED_MARKETS
    ):
        raise ProspectiveReplayError("Repository market safety has drifted")
    return {
        "provider_identifier": provider_identifier,
        "prospective_replay_status": prospective_status,
    }


def load_fixture_catalog(value: Any, *, provider_identifier: str) -> tuple[
    dict[str, ProspectiveFixture], tuple[str, ...]
]:
    if not isinstance(value, Mapping):
        raise ProspectiveReplayError("Fixture catalog must be an object")
    reject_forbidden_fields(value, location="fixture_catalog")
    if value.get("schema_version") != 1 or value.get("dataset_name") != (
        "win-either-half-prospective-fixtures-v1"
    ):
        raise ProspectiveReplayError("Unexpected fixture catalog contract")
    if value.get("provider_identifier") != provider_identifier:
        raise ProspectiveReplayError(
            "Fixture catalog provider does not match qualification report"
        )
    raw_sources = value.get("expected_sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ProspectiveReplayError("Fixture catalog expected_sources is required")
    sources = tuple(sorted({_text(source) for source in raw_sources if _text(source)}))
    if len(sources) != len(raw_sources):
        raise ProspectiveReplayError("Expected sources must be unique non-empty strings")
    records = value.get("fixtures")
    if not isinstance(records, list) or not records:
        raise ProspectiveReplayError("Fixture catalog must contain fixtures")
    catalog: dict[str, ProspectiveFixture] = {}
    for row in records:
        if not isinstance(row, Mapping):
            raise ProspectiveReplayError("Fixture row must be an object")
        fixture_identifier = _text(row.get("fixture_identifier"))
        provider_event_identifier = _text(row.get("provider_event_identifier"))
        if fixture_identifier is None or provider_event_identifier is None:
            raise ProspectiveReplayError("Fixture identifiers are required")
        if fixture_identifier in catalog:
            raise ProspectiveReplayError("Fixture identifiers must be unique")
        raw_markets = row.get("market_ids")
        if not isinstance(raw_markets, list):
            raise ProspectiveReplayError("Fixture market_ids must be a list")
        try:
            market_ids = tuple(MarketId(item) for item in raw_markets)
        except (TypeError, ValueError) as error:
            raise ProspectiveReplayError("Fixture contains an unsupported market") from error
        fixture = ProspectiveFixture(
            fixture_identifier=fixture_identifier,
            provider_event_identifier=provider_event_identifier,
            kickoff=_timestamp(row.get("kickoff_utc"), "fixture kickoff_utc"),
            market_ids=market_ids,
        )
        catalog[fixture_identifier] = fixture
    return dict(sorted(catalog.items())), sources


def load_provider_mappings(
    records: Any,
    *,
    fixtures: Mapping[str, ProspectiveFixture],
    expected_sources: Sequence[str],
) -> tuple[
    dict[tuple[str, str, str, str], ProviderSelectionMapping],
    dict[tuple[str, str, MarketId, OutcomeId], ProviderSelectionMapping],
]:
    if not isinstance(records, list):
        raise ProspectiveReplayError("Provider mappings must be a list")
    reject_forbidden_fields(records, location="provider_mappings")
    lookup: dict[tuple[str, str, str, str], ProviderSelectionMapping] = {}
    canonical: dict[tuple[str, str, MarketId, OutcomeId], ProviderSelectionMapping] = {}
    for row in records:
        if not isinstance(row, Mapping):
            raise ProspectiveReplayError("Provider mapping row must be an object")
        required = (
            "source",
            "provider_event_identifier",
            "provider_market_identifier",
            "provider_selection_identifier",
            "fixture_identifier",
        )
        text = {field: _text(row.get(field)) for field in required}
        if any(text[field] is None for field in required):
            raise ProspectiveReplayError("Provider mapping identifiers are required")
        if text["source"] not in expected_sources:
            raise ProspectiveReplayError("Provider mapping source is not expected")
        fixture = fixtures.get(text["fixture_identifier"])
        if fixture is None:
            raise ProspectiveReplayError("Provider mapping fixture is unknown")
        if text["provider_event_identifier"] != fixture.provider_event_identifier:
            raise ProspectiveReplayError("Provider mapping event does not match fixture")
        try:
            market_id = MarketId(row.get("market_id"))
            outcome_id = OutcomeId(row.get("outcome_id"))
        except (TypeError, ValueError) as error:
            raise ProspectiveReplayError("Provider mapping canonical IDs are invalid") from error
        if market_id not in PERMITTED_MARKETS or outcome_id not in PERMITTED_OUTCOMES:
            raise ProspectiveReplayError("Provider mapping selection is unsupported")
        if row.get("line") is not None:
            raise ProspectiveReplayError("Win Either Half mappings require null line")
        mapping = ProviderSelectionMapping(
            source=text["source"],
            provider_event_identifier=text["provider_event_identifier"],
            provider_market_identifier=text["provider_market_identifier"],
            provider_selection_identifier=text["provider_selection_identifier"],
            fixture_identifier=text["fixture_identifier"],
            market_id=market_id,
            outcome_id=outcome_id,
        )
        if mapping.lookup_key in lookup or mapping.canonical_key in canonical:
            raise ProspectiveReplayError("Provider mappings must be unique")
        lookup[mapping.lookup_key] = mapping
        canonical[mapping.canonical_key] = mapping

    missing = []
    for fixture_identifier in fixtures:
        for source in expected_sources:
            for market in PERMITTED_MARKETS:
                for outcome in PERMITTED_OUTCOMES:
                    key = (source, fixture_identifier, market, outcome)
                    if key not in canonical:
                        missing.append(key)
    if missing:
        raise ProspectiveReplayError(
            "Provider mappings must cover every fixture, source, market, and YES/NO outcome"
        )
    return lookup, canonical


def _audit_fields(value: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    names = (
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
    result = {}
    for name in names:
        raw = value.get(name)
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            rendered = raw
        else:
            rendered = str(raw)
        if isinstance(rendered, str):
            rendered = rendered[:160]
        result[name] = rendered
    return tuple(sorted(result.items()))


def parse_quote(
    value: Mapping[str, Any],
    *,
    source_row_number: int,
    fixtures: Mapping[str, ProspectiveFixture],
    mapping_lookup: Mapping[
        tuple[str, str, str, str], ProviderSelectionMapping
    ],
) -> QuoteParseResult:
    reject_forbidden_fields(value, location=f"quotes[{source_row_number}]")
    reasons: list[QuoteRejectionReason] = []
    audit = _audit_fields(value)
    if value.get("schema_version") != SCHEMA_VERSION:
        reasons.append(QuoteRejectionReason.UNSUPPORTED_SCHEMA_VERSION)
    fixture_identifier = _text(value.get("fixture_identifier"))
    fixture = fixtures.get(fixture_identifier) if fixture_identifier else None
    if fixture is None:
        reasons.append(QuoteRejectionReason.UNKNOWN_FIXTURE)
    try:
        market_id = MarketId(value.get("market_id"))
        if market_id not in PERMITTED_MARKETS:
            raise ValueError
    except (TypeError, ValueError):
        market_id = None
        reasons.append(QuoteRejectionReason.UNKNOWN_MARKET)
    try:
        outcome_id = OutcomeId(value.get("outcome_id"))
        if outcome_id not in PERMITTED_OUTCOMES:
            raise ValueError
    except (TypeError, ValueError):
        outcome_id = None
        reasons.append(QuoteRejectionReason.UNKNOWN_OUTCOME)
    if value.get("line") is not None:
        reasons.append(QuoteRejectionReason.INVALID_LINE)
    source = _text(value.get("source"))
    if source is None:
        reasons.append(QuoteRejectionReason.MISSING_SOURCE)
    snapshot_id = _text(value.get("quote_snapshot_id"))
    if snapshot_id is None:
        reasons.append(QuoteRejectionReason.MISSING_SNAPSHOT_ID)
    provider_fields = (
        "provider_event_identifier",
        "provider_market_identifier",
        "provider_selection_identifier",
    )
    provider = {field: _text(value.get(field)) for field in provider_fields}
    if any(provider[field] is None for field in provider_fields):
        reasons.append(QuoteRejectionReason.MISSING_PROVIDER_IDENTIFIER)
    observed_at, observed_error = _timestamp_with_reason(value.get("observed_at"))
    kickoff, kickoff_error = _timestamp_with_reason(value.get("fixture_kickoff"))
    if observed_error is not None:
        reasons.append(observed_error)
    if kickoff_error is not None:
        reasons.append(kickoff_error)
    decimal_odds = _odds(value.get("decimal_odds"))
    if decimal_odds is None:
        reasons.append(QuoteRejectionReason.INVALID_ODDS)
    if value.get("is_genuine") is not True:
        reasons.append(QuoteRejectionReason.NOT_GENUINE)
    if fixture is not None and kickoff is not None and kickoff != fixture.kickoff:
        reasons.append(QuoteRejectionReason.FIXTURE_KICKOFF_MISMATCH)
    if observed_at is not None and kickoff is not None and observed_at >= kickoff:
        reasons.append(QuoteRejectionReason.OBSERVED_AT_OR_AFTER_KICKOFF)
    if source is not None and all(provider.values()):
        mapping = mapping_lookup.get(
            (
                source,
                provider["provider_event_identifier"],
                provider["provider_market_identifier"],
                provider["provider_selection_identifier"],
            )
        )
        if (
            mapping is None
            or mapping.fixture_identifier != fixture_identifier
            or mapping.market_id != market_id
            or mapping.outcome_id != outcome_id
        ):
            reasons.append(QuoteRejectionReason.PROVIDER_MAPPING_MISMATCH)
    normalized = tuple(sorted(set(reasons), key=lambda item: item.value))
    if normalized:
        return QuoteParseResult(source_row_number, None, normalized, audit)
    assert fixture_identifier is not None
    assert market_id is not None
    assert outcome_id is not None
    assert source is not None
    assert snapshot_id is not None
    assert observed_at is not None
    assert kickoff is not None
    assert decimal_odds is not None
    return QuoteParseResult(
        source_row_number,
        ProspectiveQuote(
            source_row_number=source_row_number,
            fixture_identifier=fixture_identifier,
            market_id=market_id,
            outcome_id=outcome_id,
            source=source,
            quote_snapshot_id=snapshot_id,
            observed_at=observed_at,
            fixture_kickoff=kickoff,
            decimal_odds=decimal_odds,
            provider_event_identifier=provider["provider_event_identifier"],
            provider_market_identifier=provider["provider_market_identifier"],
            provider_selection_identifier=provider["provider_selection_identifier"],
        ),
        (),
        audit,
    )


def parse_quotes(
    rows: Sequence[Mapping[str, Any]],
    *,
    fixtures: Mapping[str, ProspectiveFixture],
    mapping_lookup: Mapping[
        tuple[str, str, str, str], ProviderSelectionMapping
    ],
) -> tuple[QuoteParseResult, ...]:
    results = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ProspectiveReplayError("Every quote row must be an object")
        results.append(
            parse_quote(
                row,
                source_row_number=index,
                fixtures=fixtures,
                mapping_lookup=mapping_lookup,
            )
        )
    return tuple(results)


def _complete_snapshots(
    quotes: Sequence[ProspectiveQuote],
) -> tuple[tuple[str, datetime, tuple[ProspectiveQuote, ...]], ...]:
    groups: dict[tuple[str, datetime], list[ProspectiveQuote]] = defaultdict(list)
    for quote in quotes:
        groups[(quote.quote_snapshot_id, quote.observed_at)].append(quote)
    complete = []
    for (snapshot_id, observed_at), rows in groups.items():
        outcomes: dict[OutcomeId, list[ProspectiveQuote]] = defaultdict(list)
        for row in rows:
            outcomes[row.outcome_id].append(row)
        if set(outcomes) != set(PERMITTED_OUTCOMES):
            continue
        if any(len(outcomes[outcome]) != 1 for outcome in PERMITTED_OUTCOMES):
            continue
        if len({row.provider_event_identifier for row in rows}) != 1:
            continue
        if len({row.provider_market_identifier for row in rows}) != 1:
            continue
        complete.append((snapshot_id, observed_at, tuple(rows)))
    return tuple(sorted(complete, key=lambda item: (item[1], item[0])))


def evaluate_replay_row(
    *,
    fixture: ProspectiveFixture,
    market_id: MarketId,
    source: str,
    candidate_offset_seconds: int,
    raw_quote_count: int,
    valid_quotes: Sequence[ProspectiveQuote],
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
) -> ProspectiveReplayRow:
    if (
        isinstance(max_quote_age_seconds, bool)
        or not isinstance(max_quote_age_seconds, int)
        or max_quote_age_seconds <= 0
    ):
        raise ProspectiveReplayError("Maximum quote age must be a positive integer")
    if candidate_offset_seconds <= 0:
        raise ProspectiveReplayError("Candidate offset must be positive")
    decision_at = fixture.kickoff - timedelta(seconds=candidate_offset_seconds)
    matching = tuple(
        quote
        for quote in valid_quotes
        if quote.fixture_identifier == fixture.fixture_identifier
        and quote.market_id is market_id
        and quote.source == source
    )
    at_or_before = tuple(
        quote for quote in matching if quote.observed_at <= decision_at
    )
    fresh = tuple(
        quote
        for quote in at_or_before
        if decision_at - quote.observed_at
        <= timedelta(seconds=max_quote_age_seconds)
    )
    complete = _complete_snapshots(fresh)
    status = ReplayStatus.UNAVAILABLE
    selected_snapshot_id = None
    selected_observed_at = None
    selected_age = None
    if raw_quote_count == 0:
        reason = ReplayReason.NO_QUOTE_RECORDS
    elif not matching:
        reason = ReplayReason.NO_STRUCTURALLY_VALID_QUOTES
    elif not at_or_before:
        reason = ReplayReason.NO_QUOTES_AT_OR_BEFORE_DECISION
    elif not fresh:
        reason = ReplayReason.NO_FRESH_QUOTES_AT_DECISION
    elif not complete:
        reason = ReplayReason.NO_COMPLETE_SNAPSHOT
    else:
        winner = max(complete, key=lambda item: (item[1], item[0]))
        selected_snapshot_id = winner[0]
        selected_observed_at = winner[1]
        selected_age = int((decision_at - selected_observed_at).total_seconds())
        status = ReplayStatus.AVAILABLE
        reason = ReplayReason.AVAILABLE
    return ProspectiveReplayRow(
        fixture_identifier=fixture.fixture_identifier,
        market_id=market_id,
        source=source,
        fixture_kickoff=fixture.kickoff,
        candidate_offset_seconds=candidate_offset_seconds,
        decision_at=decision_at,
        raw_quote_row_count=raw_quote_count,
        structurally_valid_quote_row_count=len(matching),
        at_or_before_decision_quote_row_count=len(at_or_before),
        fresh_quote_row_count=len(fresh),
        complete_snapshot_count=len(complete),
        availability_status=status,
        availability_reason=reason,
        selected_snapshot_id=selected_snapshot_id,
        selected_observed_at=selected_observed_at,
        selected_quote_age_seconds=selected_age,
    )


def run_prospective_replay(
    *,
    fixtures: Mapping[str, ProspectiveFixture],
    expected_sources: Sequence[str],
    offsets: Sequence[int],
    raw_quote_rows: Sequence[Mapping[str, Any]],
    quote_results: Sequence[QuoteParseResult],
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
) -> tuple[ProspectiveReplayRow, ...]:
    raw_counts: Counter[tuple[str, MarketId, str]] = Counter()
    for row in raw_quote_rows:
        fixture_identifier = _text(row.get("fixture_identifier"))
        source = _text(row.get("source"))
        try:
            market = MarketId(row.get("market_id"))
        except (TypeError, ValueError):
            continue
        if (
            fixture_identifier in fixtures
            and market in PERMITTED_MARKETS
            and source in expected_sources
        ):
            raw_counts[(fixture_identifier, market, source)] += 1
    valid_quotes = tuple(
        result.record for result in quote_results if result.record is not None
    )
    output = []
    for fixture_identifier in sorted(fixtures):
        fixture = fixtures[fixture_identifier]
        for source in sorted(expected_sources):
            for market in sorted(PERMITTED_MARKETS, key=lambda item: item.value):
                for offset in sorted(offsets, reverse=True):
                    output.append(
                        evaluate_replay_row(
                            fixture=fixture,
                            market_id=market,
                            source=source,
                            candidate_offset_seconds=offset,
                            raw_quote_count=raw_counts[
                                (fixture_identifier, market, source)
                            ],
                            valid_quotes=valid_quotes,
                            max_quote_age_seconds=max_quote_age_seconds,
                        )
                    )
    return tuple(output)


def aggregate_replay(
    rows: Sequence[ProspectiveReplayRow],
    *,
    minimum_fixtures_for_interpretation: int,
) -> dict[str, Any]:
    if (
        isinstance(minimum_fixtures_for_interpretation, bool)
        or not isinstance(minimum_fixtures_for_interpretation, int)
        or minimum_fixtures_for_interpretation <= 0
    ):
        raise ProspectiveReplayError(
            "minimum_fixtures_for_interpretation must be a positive integer"
        )
    rows = tuple(rows)
    by_offset: dict[int, list[ProspectiveReplayRow]] = defaultdict(list)
    for row in rows:
        by_offset[row.candidate_offset_seconds].append(row)
    offset_rows = []
    market_rows = []
    for offset in sorted(by_offset, reverse=True):
        group = by_offset[offset]
        available = sum(
            row.availability_status is ReplayStatus.AVAILABLE for row in group
        )
        fixture_source_pairs = sorted(
            {(row.fixture_identifier, row.source) for row in group}
        )
        both_available = 0
        for pair in fixture_source_pairs:
            pair_rows = [
                row
                for row in group
                if (row.fixture_identifier, row.source) == pair
            ]
            if {
                row.market_id
                for row in pair_rows
                if row.availability_status is ReplayStatus.AVAILABLE
            } == set(PERMITTED_MARKETS):
                both_available += 1
        fixture_count = len({row.fixture_identifier for row in group})
        offset_rows.append(
            {
                "candidate_offset_seconds": offset,
                "fixture_count": fixture_count,
                "support_status": _support_status(
                    fixture_count, minimum_fixtures_for_interpretation
                ).value,
                "fixture_market_source_denominator": len(group),
                "available_fixture_market_source_rows": available,
                "availability_percentage": _percentage(available, len(group)),
                "fixture_source_denominator": len(fixture_source_pairs),
                "both_markets_available_same_source": both_available,
                "both_markets_availability_percentage": _percentage(
                    both_available, len(fixture_source_pairs)
                ),
                "reason_counts": dict(
                    sorted(Counter(row.availability_reason.value for row in group).items())
                ),
            }
        )
        keys = sorted({(row.source, row.market_id) for row in group}, key=lambda item: (item[0], item[1].value))
        for source, market in keys:
            subset = [
                row for row in group if row.source == source and row.market_id is market
            ]
            subset_available = sum(
                row.availability_status is ReplayStatus.AVAILABLE for row in subset
            )
            market_rows.append(
                {
                    "candidate_offset_seconds": offset,
                    "source": source,
                    "market_id": market.value,
                    "denominator": len(subset),
                    "available": subset_available,
                    "availability_percentage": _percentage(
                        subset_available, len(subset)
                    ),
                    "reason_counts": dict(
                        sorted(
                            Counter(
                                row.availability_reason.value for row in subset
                            ).items()
                        )
                    ),
                }
            )
    return {
        "selection_status": "UNSELECTED",
        "selection_reason": (
            "Stage 5B2 reports operational availability only; it does not select "
            "or freeze a decision offset."
        ),
        "rows": len(rows),
        "available_rows": sum(
            row.availability_status is ReplayStatus.AVAILABLE for row in rows
        ),
        "offsets": offset_rows,
        "by_offset_source_market": market_rows,
    }


__all__ = [
    "DEFAULT_MAX_QUOTE_AGE_SECONDS",
    "FORBIDDEN_INPUT_KEYS",
    "PERMITTED_MARKETS",
    "PERMITTED_OUTCOMES",
    "ProspectiveFixture",
    "ProspectiveQuote",
    "ProspectiveReplayError",
    "ProspectiveReplayRow",
    "ProviderSelectionMapping",
    "QUALIFIED_PROSPECTIVE_STATUSES",
    "QuoteParseResult",
    "QuoteRejectionReason",
    "ReplayReason",
    "ReplayStatus",
    "SCHEMA_VERSION",
    "SupportStatus",
    "aggregate_replay",
    "evaluate_replay_row",
    "load_fixture_catalog",
    "load_provider_mappings",
    "parse_quote",
    "parse_quotes",
    "reject_forbidden_fields",
    "run_prospective_replay",
    "validate_candidate_offsets",
    "validate_source_qualification_report",
]
