"""Domain logic for Stage 5B2 prospective Win Either Half pricing observation replay.

Stage 5B2 is provider-agnostic, offline research tooling to measure whether exact
Home Team to Win Either Half and Away Team to Win Either Half YES/NO bookmaker
snapshots would have been available and fresh at predeclared times before kickoff.

Safety & Governance Rules:
- Both Win Either Half markets remain DISABLED.
- Missing evidence is UNKNOWN, not UNAVAILABLE.
- UNAVAILABLE requires explicit provider unavailability evidence.
- No model probabilities, fair odds, edge, EV, Kelly, stakes, profits, betslips,
  booking codes, or bets are computed or emitted.
- All candidate offsets remain UNSELECTED.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from math import isfinite
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId

PERMITTED_MARKETS = (
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
)
PROSPECTIVE_REPLAY_ELIGIBLE_STATUSES = (
    "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
    "QUALIFIED_FOR_LIVE_PRICING",
    "QUALIFIED_PROSPECTIVE_REPLAY_ELIGIBLE",
)


SCHEMA_VERSION = 1
FROZEN_CANDIDATE_OFFSETS_SECONDS: tuple[int, ...] = (
    86400,
    21600,
    10800,
    3600,
    1800,
    900,
)
ATTEMPT_WINDOW_SECONDS = 300
MAXIMUM_QUOTE_AGE_SECONDS = 900
EXPECTED_ATTEMPTS_PER_FIXTURE = 12


class AttemptResult(str, Enum):
    QUOTES_CAPTURED = "QUOTES_CAPTURED"
    MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
    FIXTURE_UNAVAILABLE = "FIXTURE_UNAVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    CAPTURE_ERROR = "CAPTURE_ERROR"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


class AvailabilityReason(str, Enum):
    COMPLETE_ELIGIBLE_SNAPSHOT = "COMPLETE_ELIGIBLE_SNAPSHOT"
    EXPLICIT_MARKET_UNAVAILABLE = "EXPLICIT_MARKET_UNAVAILABLE"
    EXPLICIT_FIXTURE_UNAVAILABLE = "EXPLICIT_FIXTURE_UNAVAILABLE"
    EXPLICIT_SOURCE_UNAVAILABLE = "EXPLICIT_SOURCE_UNAVAILABLE"
    NO_ATTEMPT_RECORD = "NO_ATTEMPT_RECORD"
    CAPTURE_ERROR = "CAPTURE_ERROR"
    DUPLICATE_ATTEMPT_KEY = "DUPLICATE_ATTEMPT_KEY"
    INVALID_ATTEMPT_RECORD = "INVALID_ATTEMPT_RECORD"
    UNAVAILABLE_ATTEMPT_HAS_QUOTES = "UNAVAILABLE_ATTEMPT_HAS_QUOTES"
    CAPTURED_WITHOUT_QUOTES = "CAPTURED_WITHOUT_QUOTES"
    CONTRADICTORY_QUOTE_EVIDENCE = "CONTRADICTORY_QUOTE_EVIDENCE"
    NO_COMPLETE_ELIGIBLE_SNAPSHOT = "NO_COMPLETE_ELIGIBLE_SNAPSHOT"


class QuoteRejectionReason(str, Enum):
    SCHEMA_VERSION_INVALID = "SCHEMA_VERSION_INVALID"
    MISSING_FIELD = "MISSING_FIELD"
    UNEXPECTED_FIELD = "UNEXPECTED_FIELD"
    INVALID_LINE = "INVALID_LINE"
    INVALID_CANONICAL_MARKET = "INVALID_CANONICAL_MARKET"
    INVALID_CANONICAL_OUTCOME = "INVALID_CANONICAL_OUTCOME"
    DECIMAL_ODDS_INVALID = "DECIMAL_ODDS_INVALID"
    NON_GENUINE_SOURCE = "NON_GENUINE_SOURCE"
    TIMEZONE_MISSING = "TIMEZONE_MISSING"
    OBSERVED_AFTER_KICKOFF = "OBSERVED_AFTER_KICKOFF"
    KICKOFF_MISMATCH = "KICKOFF_MISMATCH"
    UNKNOWN_FIXTURE = "UNKNOWN_FIXTURE"
    MAPPING_MISMATCH = "MAPPING_MISMATCH"
    MISSING_PROVIDER_IDENTIFIER = "MISSING_PROVIDER_IDENTIFIER"
    MISSING_BOOKMAKER_IDENTIFIER = "MISSING_BOOKMAKER_IDENTIFIER"
    MIXED_PROVIDER = "MIXED_PROVIDER"
    MIXED_BOOKMAKER = "MIXED_BOOKMAKER"
    MIXED_PROVIDER_EVENT = "MIXED_PROVIDER_EVENT"
    MIXED_PROVIDER_MARKET = "MIXED_PROVIDER_MARKET"
    MIXED_SNAPSHOT = "MIXED_SNAPSHOT"
    MIXED_OBSERVED_AT = "MIXED_OBSERVED_AT"


class AttemptRejectionReason(str, Enum):
    SCHEMA_VERSION_INVALID = "SCHEMA_VERSION_INVALID"
    MISSING_FIELD = "MISSING_FIELD"
    UNEXPECTED_FIELD = "UNEXPECTED_FIELD"
    INVALID_LINE = "INVALID_LINE"
    INVALID_CANONICAL_MARKET = "INVALID_CANONICAL_MARKET"
    UNKNOWN_FIXTURE = "UNKNOWN_FIXTURE"
    INVALID_OFFSET = "INVALID_OFFSET"
    SCHEDULED_AT_MISMATCH = "SCHEDULED_AT_MISMATCH"
    ATTEMPT_WINDOW_VIOLATION = "ATTEMPT_WINDOW_VIOLATION"
    ATTEMPTED_AT_OR_AFTER_KICKOFF = "ATTEMPTED_AT_OR_AFTER_KICKOFF"
    TIMEZONE_MISSING = "TIMEZONE_MISSING"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
    BOOKMAKER_MISMATCH = "BOOKMAKER_MISMATCH"
    EVENT_MISMATCH = "EVENT_MISMATCH"
    MARKET_MISMATCH = "MARKET_MISMATCH"
    CAPTURE_METHOD_INVALID = "CAPTURE_METHOD_INVALID"
    SNAPSHOT_ID_REQUIRED = "SNAPSHOT_ID_REQUIRED"
    SNAPSHOT_ID_FORBIDDEN = "SNAPSHOT_ID_FORBIDDEN"
    RESULT_INVALID = "RESULT_INVALID"


FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "expected_value",
    "kelly",
    "bet_decision",
    "bet_label",
    "fair_probability",
    "fair_odds",
    "model_probability",
    "edge",
    "profit",
    "stake",
    "booking_code",
    "betslip",
    "acca_decision",
    "actual_score",
    "home_score",
    "away_score",
)


def assert_no_forbidden_fields(data: Any, path: str = "") -> None:
    """Recursively ensure no forbidden outcome, model, value, or bet concepts exist."""
    if isinstance(data, dict):
        for key, val in data.items():
            current_path = f"{path}.{key}" if path else str(key)
            lower_key = str(key).lower()
            if not lower_key.endswith("_forbidden_from_offset_evaluation"):
                for kw in FORBIDDEN_KEYWORDS:
                    if kw in lower_key:
                        raise ValueError(f"Forbidden field '{key}' at '{current_path}'")
            assert_no_forbidden_fields(val, current_path)
    elif isinstance(data, (list, tuple, set)):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"
            assert_no_forbidden_fields(item, current_path)


def canonical_record_bytes(value: Mapping[str, Any]) -> bytes:
    """Return deterministic UTF-8 bytes for a JSON object."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_record_sha256(value: Mapping[str, Any]) -> str:
    """Return canonical SHA-256 hex digest of a JSON object."""
    return hashlib.sha256(canonical_record_bytes(value)).hexdigest()


def parse_iso_datetime(value: Any) -> datetime:
    """Parse an ISO 8601 string into a timezone-aware UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Datetime must be a non-empty ISO string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("Datetime must have explicit timezone offset")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProspectiveFixture:
    fixture_identifier: str
    season: str
    competition_code: str
    kickoff: datetime
    home_team_identifier: str
    away_team_identifier: str
    provider_event_identifier: str
    expected_sources: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.fixture_identifier.strip():
            raise ValueError("fixture_identifier cannot be empty")
        if not self.season.strip():
            raise ValueError("season cannot be empty")
        if not self.competition_code.strip():
            raise ValueError("competition_code cannot be empty")
        if self.kickoff.tzinfo is None:
            raise ValueError("kickoff must be timezone-aware")
        if not self.home_team_identifier.strip():
            raise ValueError("home_team_identifier cannot be empty")
        if not self.away_team_identifier.strip():
            raise ValueError("away_team_identifier cannot be empty")
        if not self.provider_event_identifier.strip():
            raise ValueError("provider_event_identifier cannot be empty")
        if len(self.expected_sources) != 1 or not self.expected_sources[0].strip():
            raise ValueError("Stage 5B2 requires exactly one expected source in fixture catalog")


@dataclass(frozen=True)
class ProviderSelectionMapping:
    provider_identifier: str
    source: str
    bookmaker_identifier: str
    provider_event_identifier: str
    provider_market_identifier: str
    provider_selection_identifier: str
    fixture_identifier: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: None = None

    def __post_init__(self) -> None:
        if not self.provider_identifier.strip():
            raise ValueError("provider_identifier cannot be empty")
        if not self.source.strip():
            raise ValueError("source cannot be empty")
        if not self.bookmaker_identifier.strip():
            raise ValueError("bookmaker_identifier cannot be empty")
        if not self.provider_event_identifier.strip():
            raise ValueError("provider_event_identifier cannot be empty")
        if not self.provider_market_identifier.strip():
            raise ValueError("provider_market_identifier cannot be empty")
        if not self.provider_selection_identifier.strip():
            raise ValueError("provider_selection_identifier cannot be empty")
        if not self.fixture_identifier.strip():
            raise ValueError("fixture_identifier cannot be empty")
        if self.market_id not in PERMITTED_MARKETS:
            raise ValueError(f"Unsupported market_id: {self.market_id}")
        if self.outcome_id not in (OutcomeId.YES, OutcomeId.NO):
            raise ValueError(f"Unsupported outcome_id: {self.outcome_id}")
        if self.line is not None:
            raise ValueError("line must be None for Win Either Half markets")


@dataclass(frozen=True)
class ObservationAttempt:
    input_record_sha256: str
    attempt_id: str
    fixture_identifier: str
    market_id: MarketId
    source: str
    provider_identifier: str
    bookmaker_identifier: str
    provider_event_identifier: str
    provider_market_identifier: str
    offset_seconds_before_kickoff: int
    scheduled_at: datetime
    attempted_at: datetime
    result: AttemptResult
    capture_method: str
    quote_snapshot_id: Optional[str]
    line: None = None

    @property
    def expected_key(self) -> tuple[str, MarketId, int]:
        return (
            self.fixture_identifier,
            self.market_id,
            self.offset_seconds_before_kickoff,
        )


@dataclass(frozen=True)
class AttemptParseResult:
    input_record_sha256: str
    record: Optional[ObservationAttempt]
    reasons: tuple[str, ...]
    candidate_key: Optional[tuple[str, MarketId, int]]
    raw_payload: Mapping[str, Any]
    occurrence_index: int = 1


@dataclass(frozen=True)
class ProspectiveQuote:
    input_record_sha256: str
    provider_identifier: str
    source: str
    bookmaker_identifier: str
    fixture_identifier: str
    market_id: MarketId
    outcome_id: OutcomeId
    quote_snapshot_id: str
    observed_at: datetime
    fixture_kickoff: datetime
    decimal_odds: Decimal
    provider_event_identifier: str
    provider_market_identifier: str
    provider_selection_identifier: str


@dataclass(frozen=True)
class QuoteParseResult:
    input_record_sha256: str
    record: Optional[ProspectiveQuote]
    reasons: tuple[str, ...]
    candidate_key: Optional[tuple[str, MarketId, OutcomeId]]
    raw_payload: Mapping[str, Any]
    occurrence_index: int = 1


@dataclass(frozen=True)
class ValidatedSnapshot:
    fixture_identifier: str
    market_id: MarketId
    offset_seconds_before_kickoff: int
    source: str
    provider_identifier: str
    bookmaker_identifier: str
    provider_event_identifier: str
    provider_market_identifier: str
    quote_snapshot_id: str
    observed_at: datetime
    quote_age_seconds: int
    yes_quote_record_sha256: str
    no_quote_record_sha256: str


@dataclass(frozen=True)
class SnapshotBuildResult:
    snapshot: Optional[ValidatedSnapshot]
    has_contradiction: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProspectiveReplayRow:
    fixture_identifier: str
    market_id: MarketId
    offset_seconds_before_kickoff: int
    scheduled_at: datetime
    attempt_status: str
    attempt_result: Optional[str]
    raw_quote_row_count: int
    accepted_quote_row_count: int
    rejected_quote_row_count: int
    validated_snapshot_count: int
    availability_status: AvailabilityStatus
    availability_reason: AvailabilityReason
    validated_snapshot_id: Optional[str] = None
    validated_observed_at: Optional[datetime] = None
    validated_quote_age_seconds: Optional[int] = None


@dataclass(frozen=True)
class AttemptIndex:
    valid_by_key: Mapping[tuple[str, MarketId, int], tuple[ObservationAttempt, ...]]
    invalid_by_key: Mapping[tuple[str, MarketId, int], tuple[AttemptParseResult, ...]]
    unassociated_invalid: tuple[AttemptParseResult, ...]


def load_source_qualification(payload: Mapping[str, Any]) -> str:
    """Validate Stage 5B1 source qualification payload and return provider_identifier."""
    assert_no_forbidden_fields(payload)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Expected schema_version {SCHEMA_VERSION}")
    status = payload.get("prospective_replay_status")
    if status not in PROSPECTIVE_REPLAY_ELIGIBLE_STATUSES:
        raise ValueError(f"Source qualification status not eligible: {status}")
    provider_id = payload.get("provider_identifier")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("source qualification missing valid provider_identifier")
    return provider_id.strip()


def load_prospective_fixtures(payload: Mapping[str, Any]) -> dict[str, ProspectiveFixture]:
    """Parse and validate prospective fixture catalog."""
    assert_no_forbidden_fields(payload)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Expected schema_version {SCHEMA_VERSION}")
    raw_fixtures = payload.get("fixtures")
    if not isinstance(raw_fixtures, list) or not raw_fixtures:
        raise ValueError("fixtures must be a non-empty list")

    fixtures: dict[str, ProspectiveFixture] = {}
    for item in raw_fixtures:
        assert_no_forbidden_fields(item)
        f_id = item.get("fixture_identifier")
        if not isinstance(f_id, str) or not f_id.strip():
            raise ValueError("fixture missing valid fixture_identifier")
        if f_id in fixtures:
            raise ValueError(f"Duplicate fixture_identifier: {f_id}")

        kickoff = parse_iso_datetime(item.get("fixture_kickoff"))
        expected_sources = tuple(item.get("expected_sources", []))

        fixture = ProspectiveFixture(
            fixture_identifier=f_id.strip(),
            season=str(item.get("season", "")).strip(),
            competition_code=str(item.get("competition_code", "")).strip(),
            kickoff=kickoff,
            home_team_identifier=str(item.get("home_team_identifier", "")).strip(),
            away_team_identifier=str(item.get("away_team_identifier", "")).strip(),
            provider_event_identifier=str(item.get("provider_event_identifier", "")).strip(),
            expected_sources=expected_sources,
        )
        fixtures[fixture.fixture_identifier] = fixture
    return fixtures


def load_provider_mappings(
    payload: Mapping[str, Any],
    fixtures: Mapping[str, ProspectiveFixture],
    qualified_provider_identifier: str,
) -> dict[tuple[str, MarketId, OutcomeId], ProviderSelectionMapping]:
    """Parse and validate provider selection mappings with exact 4-way completeness."""
    assert_no_forbidden_fields(payload)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Expected schema_version {SCHEMA_VERSION}")
    raw_mappings = payload.get("mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        raise ValueError("mappings must be a non-empty list")

    mappings: dict[tuple[str, MarketId, OutcomeId], ProviderSelectionMapping] = {}
    for item in raw_mappings:
        assert_no_forbidden_fields(item)
        provider_id = str(item.get("provider_identifier", "")).strip()
        if provider_id != qualified_provider_identifier:
            raise ValueError(
                f"Mapping provider '{provider_id}' does not match qualified '{qualified_provider_identifier}'"
            )

        f_id = str(item.get("fixture_identifier", "")).strip()
        if f_id not in fixtures:
            raise ValueError(f"Mapping references unknown fixture: {f_id}")

        market_str = str(item.get("market_id", "")).strip()
        outcome_str = str(item.get("outcome_id", "")).strip()
        try:
            m_id = MarketId(market_str)
            o_id = OutcomeId(outcome_str)
        except ValueError as err:
            raise ValueError(f"Invalid market or outcome in mapping: {err}") from err

        if m_id not in PERMITTED_MARKETS:
            raise ValueError(f"Unsupported market in mapping: {m_id}")
        if o_id not in (OutcomeId.YES, OutcomeId.NO):
            raise ValueError(f"Unsupported outcome in mapping: {o_id}")

        key = (f_id, m_id, o_id)
        if key in mappings:
            raise ValueError(f"Duplicate mapping entry for key: {key}")

        line_val = item.get("line")
        if line_val is not None:
            raise ValueError("line must be None in mapping for Win Either Half")

        mapping = ProviderSelectionMapping(
            provider_identifier=provider_id,
            source=str(item.get("source", "")).strip(),
            bookmaker_identifier=str(item.get("bookmaker_identifier", "")).strip(),
            provider_event_identifier=str(item.get("provider_event_identifier", "")).strip(),
            provider_market_identifier=str(item.get("provider_market_identifier", "")).strip(),
            provider_selection_identifier=str(item.get("provider_selection_identifier", "")).strip(),
            fixture_identifier=f_id,
            market_id=m_id,
            outcome_id=o_id,
            line=None,
        )
        # Validate event matches fixture
        if mapping.provider_event_identifier != fixtures[f_id].provider_event_identifier:
            raise ValueError(f"Mapping event ID mismatch for fixture {f_id}")
        if mapping.source != fixtures[f_id].expected_sources[0]:
            raise ValueError(f"Mapping source mismatch for fixture {f_id}")

        mappings[key] = mapping

    # Verify complete 4-way coverage for every fixture
    for f_id in fixtures:
        for m_id in PERMITTED_MARKETS:
            for o_id in (OutcomeId.YES, OutcomeId.NO):
                k = (f_id, m_id, o_id)
                if k not in mappings:
                    raise ValueError(f"Missing required mapping for {k}")

            # Verify YES and NO share same market identity
            yes_m = mappings[(f_id, m_id, OutcomeId.YES)]
            no_m = mappings[(f_id, m_id, OutcomeId.NO)]
            if (
                yes_m.provider_identifier != no_m.provider_identifier
                or yes_m.source != no_m.source
                or yes_m.bookmaker_identifier != no_m.bookmaker_identifier
                or yes_m.provider_event_identifier != no_m.provider_event_identifier
                or yes_m.provider_market_identifier != no_m.provider_market_identifier
            ):
                raise ValueError(f"YES and NO mappings disagree for fixture {f_id}, market {m_id}")

    return mappings


def market_mapping_identity(
    canonical: Mapping[tuple[str, MarketId, OutcomeId], ProviderSelectionMapping]
) -> dict[tuple[str, MarketId], ProviderSelectionMapping]:
    """Return one verified market-level identity after YES/NO equality checks."""
    result: dict[tuple[str, MarketId], ProviderSelectionMapping] = {}
    for (f_id, m_id, o_id), mapping in canonical.items():
        if o_id is OutcomeId.YES:
            result[(f_id, m_id)] = mapping
    return result


def expected_attempt_keys(
    fixtures: Mapping[str, ProspectiveFixture],
) -> tuple[tuple[str, MarketId, int], ...]:
    """Return the exact ordered expected attempt keys across all fixtures."""
    return tuple(
        (fixture_identifier, market_id, offset)
        for fixture_identifier in sorted(fixtures)
        for market_id in sorted(PERMITTED_MARKETS, key=lambda item: item.value)
        for offset in FROZEN_CANDIDATE_OFFSETS_SECONDS
    )


def parse_attempt(
    value: Mapping[str, Any],
    *,
    fixtures: Mapping[str, ProspectiveFixture],
    mapping_by_market: Mapping[tuple[str, MarketId], ProviderSelectionMapping],
    qualified_provider_identifier: str,
    expected_source: str,
) -> AttemptParseResult:
    """Parse and validate one observation attempt record."""
    sha = canonical_record_sha256(value)
    reasons: list[str] = []

    # Check for forbidden fields
    try:
        assert_no_forbidden_fields(value)
    except ValueError:
        reasons.append(AttemptRejectionReason.UNEXPECTED_FIELD.value)

    if value.get("schema_version") != SCHEMA_VERSION:
        reasons.append(AttemptRejectionReason.SCHEMA_VERSION_INVALID.value)

    f_id = value.get("fixture_identifier")
    m_id_val = value.get("market_id")
    offset_val = value.get("offset_seconds_before_kickoff")

    candidate_market: Optional[MarketId] = None
    if isinstance(m_id_val, str):
        try:
            candidate_market = MarketId(m_id_val)
            if candidate_market not in PERMITTED_MARKETS:
                candidate_market = None
                reasons.append(AttemptRejectionReason.INVALID_CANONICAL_MARKET.value)
        except ValueError:
            reasons.append(AttemptRejectionReason.INVALID_CANONICAL_MARKET.value)
    else:
        reasons.append(AttemptRejectionReason.INVALID_CANONICAL_MARKET.value)

    candidate_offset: Optional[int] = None
    if isinstance(offset_val, int) and not isinstance(offset_val, bool):
        if offset_val in FROZEN_CANDIDATE_OFFSETS_SECONDS:
            candidate_offset = offset_val
        else:
            reasons.append(AttemptRejectionReason.INVALID_OFFSET.value)
    else:
        reasons.append(AttemptRejectionReason.INVALID_OFFSET.value)

    candidate_key: Optional[tuple[str, MarketId, int]] = None
    if isinstance(f_id, str) and f_id in fixtures and candidate_market and candidate_offset is not None:
        candidate_key = (f_id, candidate_market, candidate_offset)

    if not isinstance(f_id, str) or f_id not in fixtures:
        reasons.append(AttemptRejectionReason.UNKNOWN_FIXTURE.value)

    if value.get("line") is not None:
        reasons.append(AttemptRejectionReason.INVALID_LINE.value)

    attempt_id = value.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        reasons.append(AttemptRejectionReason.MISSING_FIELD.value)

    # Dates validation
    scheduled_at: Optional[datetime] = None
    attempted_at: Optional[datetime] = None
    try:
        scheduled_at = parse_iso_datetime(value.get("scheduled_at"))
    except Exception:
        reasons.append(AttemptRejectionReason.TIMEZONE_MISSING.value)

    try:
        attempted_at = parse_iso_datetime(value.get("attempted_at"))
    except Exception:
        reasons.append(AttemptRejectionReason.TIMEZONE_MISSING.value)

    if isinstance(f_id, str) and f_id in fixtures and candidate_offset is not None and scheduled_at is not None:
        expected_scheduled = fixtures[f_id].kickoff - timedelta(seconds=candidate_offset)
        if scheduled_at != expected_scheduled:
            reasons.append(AttemptRejectionReason.SCHEDULED_AT_MISMATCH.value)

    if scheduled_at is not None and attempted_at is not None:
        delta_sec = (attempted_at - scheduled_at).total_seconds()
        if abs(delta_sec) > ATTEMPT_WINDOW_SECONDS:
            reasons.append(AttemptRejectionReason.ATTEMPT_WINDOW_VIOLATION.value)

    if isinstance(f_id, str) and f_id in fixtures and attempted_at is not None:
        if attempted_at >= fixtures[f_id].kickoff:
            reasons.append(AttemptRejectionReason.ATTEMPTED_AT_OR_AFTER_KICKOFF.value)

    src = value.get("source")
    if src != expected_source:
        reasons.append(AttemptRejectionReason.SOURCE_MISMATCH.value)

    prov_id = value.get("provider_identifier")
    if prov_id != qualified_provider_identifier:
        reasons.append(AttemptRejectionReason.PROVIDER_MISMATCH.value)

    # Check mapping alignment
    if candidate_key and (f_id, candidate_market) in mapping_by_market:
        exp_map = mapping_by_market[(f_id, candidate_market)]
        if value.get("bookmaker_identifier") != exp_map.bookmaker_identifier:
            reasons.append(AttemptRejectionReason.BOOKMAKER_MISMATCH.value)
        if value.get("provider_event_identifier") != exp_map.provider_event_identifier:
            reasons.append(AttemptRejectionReason.EVENT_MISMATCH.value)
        if value.get("provider_market_identifier") != exp_map.provider_market_identifier:
            reasons.append(AttemptRejectionReason.MARKET_MISMATCH.value)

    capture_method = value.get("capture_method")
    if not isinstance(capture_method, str) or not capture_method.strip():
        reasons.append(AttemptRejectionReason.CAPTURE_METHOD_INVALID.value)

    raw_result = value.get("result")
    attempt_result: Optional[AttemptResult] = None
    try:
        attempt_result = AttemptResult(str(raw_result))
    except ValueError:
        reasons.append(AttemptRejectionReason.RESULT_INVALID.value)

    snap_id = value.get("quote_snapshot_id")
    if attempt_result is AttemptResult.QUOTES_CAPTURED:
        if not isinstance(snap_id, str) or not snap_id.strip():
            reasons.append(AttemptRejectionReason.SNAPSHOT_ID_REQUIRED.value)
    else:
        if snap_id is not None:
            reasons.append(AttemptRejectionReason.SNAPSHOT_ID_FORBIDDEN.value)

    if reasons:
        return AttemptParseResult(
            input_record_sha256=sha,
            record=None,
            reasons=tuple(sorted(set(reasons))),
            candidate_key=candidate_key,
            raw_payload=value,
        )

    assert candidate_market is not None
    assert candidate_offset is not None
    assert scheduled_at is not None
    assert attempted_at is not None
    assert attempt_result is not None
    assert isinstance(f_id, str)
    assert isinstance(attempt_id, str)
    assert isinstance(src, str)
    assert isinstance(prov_id, str)
    assert isinstance(capture_method, str)

    record = ObservationAttempt(
        input_record_sha256=sha,
        attempt_id=attempt_id.strip(),
        fixture_identifier=f_id.strip(),
        market_id=candidate_market,
        source=src.strip(),
        provider_identifier=prov_id.strip(),
        bookmaker_identifier=str(value.get("bookmaker_identifier", "")).strip(),
        provider_event_identifier=str(value.get("provider_event_identifier", "")).strip(),
        provider_market_identifier=str(value.get("provider_market_identifier", "")).strip(),
        offset_seconds_before_kickoff=candidate_offset,
        scheduled_at=scheduled_at,
        attempted_at=attempted_at,
        result=attempt_result,
        capture_method=capture_method.strip(),
        quote_snapshot_id=snap_id.strip() if snap_id else None,
        line=None,
    )
    return AttemptParseResult(
        input_record_sha256=sha,
        record=record,
        reasons=(),
        candidate_key=candidate_key,
        raw_payload=value,
    )


def index_attempt_results(
    results: Sequence[AttemptParseResult],
) -> AttemptIndex:
    """Index attempt parse results deterministically without overwriting duplicates."""
    valid_map: dict[tuple[str, MarketId, int], list[ObservationAttempt]] = {}
    invalid_map: dict[tuple[str, MarketId, int], list[AttemptParseResult]] = {}
    unassociated: list[AttemptParseResult] = []

    for r in results:
        if r.record is not None:
            valid_map.setdefault(r.record.expected_key, []).append(r.record)
        else:
            if r.candidate_key is not None:
                invalid_map.setdefault(r.candidate_key, []).append(r)
            else:
                unassociated.append(r)

    return AttemptIndex(
        valid_by_key={k: tuple(v) for k, v in valid_map.items()},
        invalid_by_key={k: tuple(v) for k, v in invalid_map.items()},
        unassociated_invalid=tuple(unassociated),
    )


def parse_quote(
    value: Mapping[str, Any],
    *,
    fixtures: Mapping[str, ProspectiveFixture],
    mappings: Mapping[tuple[str, MarketId, OutcomeId], ProviderSelectionMapping],
    qualified_provider_identifier: str,
    expected_source: str,
) -> QuoteParseResult:
    """Parse and validate one prospective quote record."""
    sha = canonical_record_sha256(value)
    reasons: list[str] = []

    try:
        assert_no_forbidden_fields(value)
    except ValueError:
        reasons.append(QuoteRejectionReason.UNEXPECTED_FIELD.value)

    if value.get("schema_version") != SCHEMA_VERSION:
        reasons.append(QuoteRejectionReason.SCHEMA_VERSION_INVALID.value)

    if value.get("line") is not None:
        reasons.append(QuoteRejectionReason.INVALID_LINE.value)

    f_id = value.get("fixture_identifier")
    m_id_val = value.get("market_id")
    o_id_val = value.get("outcome_id")

    candidate_market: Optional[MarketId] = None
    if isinstance(m_id_val, str):
        try:
            candidate_market = MarketId(m_id_val)
            if candidate_market not in PERMITTED_MARKETS:
                candidate_market = None
                reasons.append(QuoteRejectionReason.INVALID_CANONICAL_MARKET.value)
        except ValueError:
            reasons.append(QuoteRejectionReason.INVALID_CANONICAL_MARKET.value)
    else:
        reasons.append(QuoteRejectionReason.INVALID_CANONICAL_MARKET.value)

    candidate_outcome: Optional[OutcomeId] = None
    if isinstance(o_id_val, str):
        try:
            candidate_outcome = OutcomeId(o_id_val)
            if candidate_outcome not in (OutcomeId.YES, OutcomeId.NO):
                candidate_outcome = None
                reasons.append(QuoteRejectionReason.INVALID_CANONICAL_OUTCOME.value)
        except ValueError:
            reasons.append(QuoteRejectionReason.INVALID_CANONICAL_OUTCOME.value)
    else:
        reasons.append(QuoteRejectionReason.INVALID_CANONICAL_OUTCOME.value)

    candidate_key: Optional[tuple[str, MarketId, OutcomeId]] = None
    if isinstance(f_id, str) and candidate_market and candidate_outcome:
        candidate_key = (f_id, candidate_market, candidate_outcome)

    if not isinstance(f_id, str) or f_id not in fixtures:
        reasons.append(QuoteRejectionReason.UNKNOWN_FIXTURE.value)

    # Provider & Source validation
    prov_id = value.get("provider_identifier")
    if not isinstance(prov_id, str) or not prov_id.strip():
        reasons.append(QuoteRejectionReason.MISSING_PROVIDER_IDENTIFIER.value)
    elif prov_id != qualified_provider_identifier:
        reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)

    bookmaker_id = value.get("bookmaker_identifier")
    if not isinstance(bookmaker_id, str) or not bookmaker_id.strip():
        reasons.append(QuoteRejectionReason.MISSING_BOOKMAKER_IDENTIFIER.value)

    src = value.get("source")
    if src != expected_source:
        reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)

    if value.get("is_genuine") is not True:
        reasons.append(QuoteRejectionReason.NON_GENUINE_SOURCE.value)

    snap_id = value.get("quote_snapshot_id")
    if not isinstance(snap_id, str) or not snap_id.strip():
        reasons.append(QuoteRejectionReason.MISSING_FIELD.value)

    # Datetime validation
    observed_at: Optional[datetime] = None
    kickoff: Optional[datetime] = None
    try:
        observed_at = parse_iso_datetime(value.get("observed_at"))
    except Exception:
        reasons.append(QuoteRejectionReason.TIMEZONE_MISSING.value)

    try:
        kickoff = parse_iso_datetime(value.get("fixture_kickoff"))
    except Exception:
        reasons.append(QuoteRejectionReason.TIMEZONE_MISSING.value)

    if isinstance(f_id, str) and f_id in fixtures and kickoff is not None:
        if kickoff != fixtures[f_id].kickoff:
            reasons.append(QuoteRejectionReason.KICKOFF_MISMATCH.value)

    if observed_at is not None and kickoff is not None:
        if observed_at >= kickoff:
            reasons.append(QuoteRejectionReason.OBSERVED_AFTER_KICKOFF.value)

    # Decimal odds validation
    odds_raw = value.get("decimal_odds")
    parsed_odds: Optional[Decimal] = None
    try:
        if odds_raw is None:
            raise ValueError("missing decimal_odds")
        parsed_odds = Decimal(str(odds_raw))
        if not isfinite(parsed_odds) or parsed_odds <= 1:
            reasons.append(QuoteRejectionReason.DECIMAL_ODDS_INVALID.value)
    except (InvalidOperation, ValueError, TypeError):
        reasons.append(QuoteRejectionReason.DECIMAL_ODDS_INVALID.value)

    # Mapping matching
    if candidate_key and candidate_key in mappings:
        mapping = mappings[candidate_key]
        if bookmaker_id != mapping.bookmaker_identifier:
            reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)
        if value.get("provider_event_identifier") != mapping.provider_event_identifier:
            reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)
        if value.get("provider_market_identifier") != mapping.provider_market_identifier:
            reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)
        if value.get("provider_selection_identifier") != mapping.provider_selection_identifier:
            reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)
    else:
        if candidate_key is not None:
            reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)

    if reasons:
        return QuoteParseResult(
            input_record_sha256=sha,
            record=None,
            reasons=tuple(sorted(set(reasons))),
            candidate_key=candidate_key,
            raw_payload=value,
        )

    assert candidate_market is not None
    assert candidate_outcome is not None
    assert observed_at is not None
    assert kickoff is not None
    assert parsed_odds is not None
    assert isinstance(f_id, str)
    assert isinstance(prov_id, str)
    assert isinstance(bookmaker_id, str)
    assert isinstance(src, str)
    assert isinstance(snap_id, str)

    quote = ProspectiveQuote(
        input_record_sha256=sha,
        provider_identifier=prov_id.strip(),
        source=src.strip(),
        bookmaker_identifier=bookmaker_id.strip(),
        fixture_identifier=f_id.strip(),
        market_id=candidate_market,
        outcome_id=candidate_outcome,
        quote_snapshot_id=snap_id.strip(),
        observed_at=observed_at,
        fixture_kickoff=kickoff,
        decimal_odds=parsed_odds,
        provider_event_identifier=str(value.get("provider_event_identifier", "")).strip(),
        provider_market_identifier=str(value.get("provider_market_identifier", "")).strip(),
        provider_selection_identifier=str(value.get("provider_selection_identifier", "")).strip(),
    )
    return QuoteParseResult(
        input_record_sha256=sha,
        record=quote,
        reasons=(),
        candidate_key=candidate_key,
        raw_payload=value,
    )


def build_validated_snapshot(
    *,
    key: tuple[str, MarketId, int],
    attempt: ObservationAttempt,
    fixture: ProspectiveFixture,
    quotes_for_key: Sequence[QuoteParseResult],
    mapping: ProviderSelectionMapping,
) -> SnapshotBuildResult:
    """Build a complete validated snapshot for a QUOTES_CAPTURED attempt."""
    f_id, m_id, offset = key
    scheduled_at = fixture.kickoff - timedelta(seconds=offset)
    attempted_at = attempt.attempted_at

    # Only consider quotes matching attempt quote_snapshot_id
    matching_parsed = [
        q for q in quotes_for_key
        if q.raw_payload.get("quote_snapshot_id") == attempt.quote_snapshot_id
    ]

    if not matching_parsed:
        return SnapshotBuildResult(
            snapshot=None,
            has_contradiction=False,
            rejection_reasons=("NO_MATCHING_SNAPSHOT_QUOTES",),
        )

    # If any matching quote failed parsing structurally, it's contradictory
    for q in matching_parsed:
        if q.record is None:
            return SnapshotBuildResult(
                snapshot=None,
                has_contradiction=True,
                rejection_reasons=q.reasons,
            )

    valid_quotes = [q.record for q in matching_parsed if q.record is not None]

    # Check for mixed provider, bookmaker, event, market, source, observed_at
    prov_ids = {q.provider_identifier for q in valid_quotes}
    bm_ids = {q.bookmaker_identifier for q in valid_quotes}
    ev_ids = {q.provider_event_identifier for q in valid_quotes}
    mk_ids = {q.provider_market_identifier for q in valid_quotes}
    sources = {q.source for q in valid_quotes}
    obs_times = {q.observed_at for q in valid_quotes}

    reasons: list[str] = []
    if len(prov_ids) > 1 or (prov_ids and prov_ids != {attempt.provider_identifier}):
        reasons.append(QuoteRejectionReason.MIXED_PROVIDER.value)
    if len(bm_ids) > 1 or (bm_ids and bm_ids != {attempt.bookmaker_identifier}):
        reasons.append(QuoteRejectionReason.MIXED_BOOKMAKER.value)
    if len(ev_ids) > 1 or (ev_ids and ev_ids != {attempt.provider_event_identifier}):
        reasons.append(QuoteRejectionReason.MIXED_PROVIDER_EVENT.value)
    if len(mk_ids) > 1 or (mk_ids and mk_ids != {attempt.provider_market_identifier}):
        reasons.append(QuoteRejectionReason.MIXED_PROVIDER_MARKET.value)
    if len(sources) > 1 or (sources and sources != {attempt.source}):
        reasons.append(QuoteRejectionReason.MAPPING_MISMATCH.value)
    if len(obs_times) > 1:
        reasons.append(QuoteRejectionReason.MIXED_OBSERVED_AT.value)

    yes_quotes = [q for q in valid_quotes if q.outcome_id is OutcomeId.YES]
    no_quotes = [q for q in valid_quotes if q.outcome_id is OutcomeId.NO]

    if len(yes_quotes) > 1 or len(no_quotes) > 1:
        reasons.append("DUPLICATE_OUTCOME_IN_SNAPSHOT")

    if reasons:
        return SnapshotBuildResult(
            snapshot=None,
            has_contradiction=True,
            rejection_reasons=tuple(reasons),
        )

    if len(yes_quotes) != 1 or len(no_quotes) != 1:
        return SnapshotBuildResult(
            snapshot=None,
            has_contradiction=False,
            rejection_reasons=("INCOMPLETE_YES_NO_PAIR",),
        )

    yes_q = yes_quotes[0]
    no_q = no_quotes[0]
    obs_at = yes_q.observed_at

    # Eligibility at decision time
    if obs_at > scheduled_at or obs_at > attempted_at:
        return SnapshotBuildResult(
            snapshot=None,
            has_contradiction=False,
            rejection_reasons=("OBSERVED_AFTER_DECISION",),
        )

    age_sec = int((scheduled_at - obs_at).total_seconds())
    if age_sec < 0 or age_sec > MAXIMUM_QUOTE_AGE_SECONDS:
        return SnapshotBuildResult(
            snapshot=None,
            has_contradiction=False,
            rejection_reasons=("QUOTE_AGE_EXCEEDED",),
        )

    snapshot = ValidatedSnapshot(
        fixture_identifier=f_id,
        market_id=m_id,
        offset_seconds_before_kickoff=offset,
        source=yes_q.source,
        provider_identifier=yes_q.provider_identifier,
        bookmaker_identifier=yes_q.bookmaker_identifier,
        provider_event_identifier=yes_q.provider_event_identifier,
        provider_market_identifier=yes_q.provider_market_identifier,
        quote_snapshot_id=attempt.quote_snapshot_id or "",
        observed_at=obs_at,
        quote_age_seconds=age_sec,
        yes_quote_record_sha256=yes_q.input_record_sha256,
        no_quote_record_sha256=no_q.input_record_sha256,
    )
    return SnapshotBuildResult(
        snapshot=snapshot,
        has_contradiction=False,
        rejection_reasons=(),
    )


def evaluate_expected_key(
    *,
    key: tuple[str, MarketId, int],
    fixture: ProspectiveFixture,
    attempt_index: AttemptIndex,
    raw_quotes_for_key: Sequence[Mapping[str, Any]],
    parsed_quotes_for_key: Sequence[QuoteParseResult],
    mapping: ProviderSelectionMapping,
) -> tuple[ProspectiveReplayRow, Optional[ValidatedSnapshot]]:
    """Evaluate one expected (fixture, market, offset) key strictly following the precedence contract."""
    f_id, m_id, offset = key
    scheduled_at = fixture.kickoff - timedelta(seconds=offset)

    valid_attempts = attempt_index.valid_by_key.get(key, ())
    invalid_attempts = attempt_index.invalid_by_key.get(key, ())

    raw_quote_cnt = len(raw_quotes_for_key)
    accepted_quote_cnt = sum(1 for q in parsed_quotes_for_key if q.record is not None)
    rejected_quote_cnt = sum(1 for q in parsed_quotes_for_key if q.record is None)

    # 1. Invalid attempt evidence dominates UNKNOWN
    if invalid_attempts:
        row = ProspectiveReplayRow(
            fixture_identifier=f_id,
            market_id=m_id,
            offset_seconds_before_kickoff=offset,
            scheduled_at=scheduled_at,
            attempt_status="INVALID",
            attempt_result=None,
            raw_quote_row_count=raw_quote_cnt,
            accepted_quote_row_count=accepted_quote_cnt,
            rejected_quote_row_count=rejected_quote_cnt,
            validated_snapshot_count=0,
            availability_status=AvailabilityStatus.INVALID,
            availability_reason=AvailabilityReason.INVALID_ATTEMPT_RECORD,
        )
        return row, None

    if len(valid_attempts) > 1:
        row = ProspectiveReplayRow(
            fixture_identifier=f_id,
            market_id=m_id,
            offset_seconds_before_kickoff=offset,
            scheduled_at=scheduled_at,
            attempt_status="INVALID",
            attempt_result=None,
            raw_quote_row_count=raw_quote_cnt,
            accepted_quote_row_count=accepted_quote_cnt,
            rejected_quote_row_count=rejected_quote_cnt,
            validated_snapshot_count=0,
            availability_status=AvailabilityStatus.INVALID,
            availability_reason=AvailabilityReason.DUPLICATE_ATTEMPT_KEY,
        )
        return row, None

    # 2. No attempt record is UNKNOWN
    if not valid_attempts:
        row = ProspectiveReplayRow(
            fixture_identifier=f_id,
            market_id=m_id,
            offset_seconds_before_kickoff=offset,
            scheduled_at=scheduled_at,
            attempt_status="MISSING",
            attempt_result=None,
            raw_quote_row_count=raw_quote_cnt,
            accepted_quote_row_count=accepted_quote_cnt,
            rejected_quote_row_count=rejected_quote_cnt,
            validated_snapshot_count=0,
            availability_status=AvailabilityStatus.UNKNOWN,
            availability_reason=AvailabilityReason.NO_ATTEMPT_RECORD,
        )
        return row, None

    attempt = valid_attempts[0]

    # 3. CAPTURE_ERROR remains UNKNOWN
    if attempt.result is AttemptResult.CAPTURE_ERROR:
        if raw_quote_cnt > 0:
            row = ProspectiveReplayRow(
                fixture_identifier=f_id,
                market_id=m_id,
                offset_seconds_before_kickoff=offset,
                scheduled_at=scheduled_at,
                attempt_status="PRESENT",
                attempt_result=attempt.result.value,
                raw_quote_row_count=raw_quote_cnt,
                accepted_quote_row_count=accepted_quote_cnt,
                rejected_quote_row_count=rejected_quote_cnt,
                validated_snapshot_count=0,
                availability_status=AvailabilityStatus.INVALID,
                availability_reason=AvailabilityReason.CONTRADICTORY_QUOTE_EVIDENCE,
            )
            return row, None

        row = ProspectiveReplayRow(
            fixture_identifier=f_id,
            market_id=m_id,
            offset_seconds_before_kickoff=offset,
            scheduled_at=scheduled_at,
            attempt_status="PRESENT",
            attempt_result=attempt.result.value,
            raw_quote_row_count=0,
            accepted_quote_row_count=0,
            rejected_quote_row_count=0,
            validated_snapshot_count=0,
            availability_status=AvailabilityStatus.UNKNOWN,
            availability_reason=AvailabilityReason.CAPTURE_ERROR,
        )
        return row, None

    # 4. Explicit unavailability results produce UNAVAILABLE
    if attempt.result in (
        AttemptResult.MARKET_UNAVAILABLE,
        AttemptResult.FIXTURE_UNAVAILABLE,
        AttemptResult.SOURCE_UNAVAILABLE,
    ):
        if raw_quote_cnt > 0:
            row = ProspectiveReplayRow(
                fixture_identifier=f_id,
                market_id=m_id,
                offset_seconds_before_kickoff=offset,
                scheduled_at=scheduled_at,
                attempt_status="PRESENT",
                attempt_result=attempt.result.value,
                raw_quote_row_count=raw_quote_cnt,
                accepted_quote_row_count=accepted_quote_cnt,
                rejected_quote_row_count=rejected_quote_cnt,
                validated_snapshot_count=0,
                availability_status=AvailabilityStatus.INVALID,
                availability_reason=AvailabilityReason.UNAVAILABLE_ATTEMPT_HAS_QUOTES,
            )
            return row, None

        reason_map = {
            AttemptResult.MARKET_UNAVAILABLE: AvailabilityReason.EXPLICIT_MARKET_UNAVAILABLE,
            AttemptResult.FIXTURE_UNAVAILABLE: AvailabilityReason.EXPLICIT_FIXTURE_UNAVAILABLE,
            AttemptResult.SOURCE_UNAVAILABLE: AvailabilityReason.EXPLICIT_SOURCE_UNAVAILABLE,
        }
        row = ProspectiveReplayRow(
            fixture_identifier=f_id,
            market_id=m_id,
            offset_seconds_before_kickoff=offset,
            scheduled_at=scheduled_at,
            attempt_status="PRESENT",
            attempt_result=attempt.result.value,
            raw_quote_row_count=0,
            accepted_quote_row_count=0,
            rejected_quote_row_count=0,
            validated_snapshot_count=0,
            availability_status=AvailabilityStatus.UNAVAILABLE,
            availability_reason=reason_map[attempt.result],
        )
        return row, None

    # 5. QUOTES_CAPTURED
    if attempt.result is AttemptResult.QUOTES_CAPTURED:
        if raw_quote_cnt == 0:
            row = ProspectiveReplayRow(
                fixture_identifier=f_id,
                market_id=m_id,
                offset_seconds_before_kickoff=offset,
                scheduled_at=scheduled_at,
                attempt_status="PRESENT",
                attempt_result=attempt.result.value,
                raw_quote_row_count=0,
                accepted_quote_row_count=0,
                rejected_quote_row_count=0,
                validated_snapshot_count=0,
                availability_status=AvailabilityStatus.INVALID,
                availability_reason=AvailabilityReason.CAPTURED_WITHOUT_QUOTES,
            )
            return row, None

        snap_res = build_validated_snapshot(
            key=key,
            attempt=attempt,
            fixture=fixture,
            quotes_for_key=parsed_quotes_for_key,
            mapping=mapping,
        )

        if snap_res.has_contradiction:
            row = ProspectiveReplayRow(
                fixture_identifier=f_id,
                market_id=m_id,
                offset_seconds_before_kickoff=offset,
                scheduled_at=scheduled_at,
                attempt_status="PRESENT",
                attempt_result=attempt.result.value,
                raw_quote_row_count=raw_quote_cnt,
                accepted_quote_row_count=accepted_quote_cnt,
                rejected_quote_row_count=rejected_quote_cnt,
                validated_snapshot_count=0,
                availability_status=AvailabilityStatus.INVALID,
                availability_reason=AvailabilityReason.CONTRADICTORY_QUOTE_EVIDENCE,
            )
            return row, None

        if snap_res.snapshot is None:
            row = ProspectiveReplayRow(
                fixture_identifier=f_id,
                market_id=m_id,
                offset_seconds_before_kickoff=offset,
                scheduled_at=scheduled_at,
                attempt_status="PRESENT",
                attempt_result=attempt.result.value,
                raw_quote_row_count=raw_quote_cnt,
                accepted_quote_row_count=accepted_quote_cnt,
                rejected_quote_row_count=rejected_quote_cnt,
                validated_snapshot_count=0,
                availability_status=AvailabilityStatus.INVALID,
                availability_reason=AvailabilityReason.NO_COMPLETE_ELIGIBLE_SNAPSHOT,
            )
            return row, None

        # Fully available with valid complete snapshot
        snap = snap_res.snapshot
        row = ProspectiveReplayRow(
            fixture_identifier=f_id,
            market_id=m_id,
            offset_seconds_before_kickoff=offset,
            scheduled_at=scheduled_at,
            attempt_status="PRESENT",
            attempt_result=attempt.result.value,
            raw_quote_row_count=raw_quote_cnt,
            accepted_quote_row_count=accepted_quote_cnt,
            rejected_quote_row_count=rejected_quote_cnt,
            validated_snapshot_count=1,
            availability_status=AvailabilityStatus.AVAILABLE,
            availability_reason=AvailabilityReason.COMPLETE_ELIGIBLE_SNAPSHOT,
            validated_snapshot_id=snap.quote_snapshot_id,
            validated_observed_at=snap.observed_at,
            validated_quote_age_seconds=snap.quote_age_seconds,
        )
        return row, snap

    # Fallback to INVALID
    row = ProspectiveReplayRow(
        fixture_identifier=f_id,
        market_id=m_id,
        offset_seconds_before_kickoff=offset,
        scheduled_at=scheduled_at,
        attempt_status="INVALID",
        attempt_result=str(attempt.result),
        raw_quote_row_count=raw_quote_cnt,
        accepted_quote_row_count=accepted_quote_cnt,
        rejected_quote_row_count=rejected_quote_cnt,
        validated_snapshot_count=0,
        availability_status=AvailabilityStatus.INVALID,
        availability_reason=AvailabilityReason.INVALID_ATTEMPT_RECORD,
    )
    return row, None


def aggregate_replay(
    rows: Sequence[ProspectiveReplayRow],
    fixtures: Mapping[str, ProspectiveFixture],
) -> dict[str, Any]:
    """Aggregate replay results deterministically."""
    total_rows = len(rows)
    status_counts = {s.value: 0 for s in AvailabilityStatus}
    reason_counts: dict[str, int] = {}

    by_offset: dict[int, dict[str, Any]] = {
        off: {
            "total_rows": 0,
            "status_counts": {s.value: 0 for s in AvailabilityStatus},
            "status_percentages": {},
            "reason_counts": {},
            "same_source_both_markets_available_fixtures": 0,
        }
        for off in FROZEN_CANDIDATE_OFFSETS_SECONDS
    }

    by_offset_market: dict[str, dict[str, Any]] = {}

    # Track available markets per fixture per offset
    avail_by_fixture_offset: dict[tuple[str, int], set[MarketId]] = {}

    for row in rows:
        status_counts[row.availability_status.value] += 1
        reason_counts[row.availability_reason.value] = (
            reason_counts.get(row.availability_reason.value, 0) + 1
        )

        off_data = by_offset[row.offset_seconds_before_kickoff]
        off_data["total_rows"] += 1
        off_data["status_counts"][row.availability_status.value] += 1
        off_data["reason_counts"][row.availability_reason.value] = (
            off_data["reason_counts"].get(row.availability_reason.value, 0) + 1
        )

        om_key = f"{row.offset_seconds_before_kickoff}_{row.market_id.value}"
        if om_key not in by_offset_market:
            by_offset_market[om_key] = {
                "offset_seconds_before_kickoff": row.offset_seconds_before_kickoff,
                "market_id": row.market_id.value,
                "total_rows": 0,
                "status_counts": {s.value: 0 for s in AvailabilityStatus},
                "status_percentages": {},
                "reason_counts": {},
            }
        om_data = by_offset_market[om_key]
        om_data["total_rows"] += 1
        om_data["status_counts"][row.availability_status.value] += 1
        om_data["reason_counts"][row.availability_reason.value] = (
            om_data["reason_counts"].get(row.availability_reason.value, 0) + 1
        )

        if row.availability_status is AvailabilityStatus.AVAILABLE:
            avail_by_fixture_offset.setdefault(
                (row.fixture_identifier, row.offset_seconds_before_kickoff), set()
            ).add(row.market_id)

    # Compute percentages
    status_percentages = {
        s: round(cnt / total_rows, 4) if total_rows > 0 else 0.0
        for s, cnt in status_counts.items()
    }

    for off, data in by_offset.items():
        sub_tot = data["total_rows"]
        data["status_percentages"] = {
            s: round(cnt / sub_tot, 4) if sub_tot > 0 else 0.0
            for s, cnt in data["status_counts"].items()
        }
        # Count fixtures where both Home and Away are AVAILABLE
        both_cnt = sum(
            1
            for f_id in fixtures
            if len(avail_by_fixture_offset.get((f_id, off), set())) == 2
        )
        data["same_source_both_markets_available_fixtures"] = both_cnt

    for om_data in by_offset_market.values():
        sub_tot = om_data["total_rows"]
        om_data["status_percentages"] = {
            s: round(cnt / sub_tot, 4) if sub_tot > 0 else 0.0
            for s, cnt in om_data["status_counts"].items()
        }

    total_fixtures = len(fixtures)
    support_status = "SUPPORTED" if total_fixtures >= 100 else "UNSUPPORTED"

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": "win-either-half-prospective-replay-summary-v1",
        "total_fixtures": total_fixtures,
        "total_expected_rows": total_rows,
        "expected_rows_per_fixture": EXPECTED_ATTEMPTS_PER_FIXTURE,
        "support_status": support_status,
        "status_counts": status_counts,
        "status_percentages": status_percentages,
        "reason_counts": reason_counts,
        "by_offset": {str(k): v for k, v in by_offset.items()},
        "by_offset_and_market": by_offset_market,
        "holdout_governance": {
            "final_test_season": "2025-26",
            "final_test_status": "ALREADY_CONSUMED_AUDIT_HOLDOUT",
            "match_outcomes_forbidden_from_offset_evaluation": True,
            "model_performance_forbidden_from_offset_evaluation": True,
            "pricing_profitability_forbidden_from_offset_evaluation": True,
            "prospective_validation_required": True,
            "production_approval_authorized": False,
        },
        "selected_offset_seconds": None,
        "selection_status": "UNSELECTED",
        "selection_authorized": False,
        "production_approval_authorized": False,
        "market_statuses": {
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        },
        "no_production_approval": "Stage 5B2 is observation evidence only.",
    }
