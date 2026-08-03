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

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, Context, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId
from domain.model_status import MODEL_STATUS_REGISTRY
from domain.win_either_half_pricing_source_qualification import (
    QualificationStatus,
    canonical_market_registry_snapshot,
)

SCHEMA_VERSION = 1
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-protocols"
    / "win-either-half-prospective-replay-v1.json"
)

PERMITTED_MARKETS = (
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
)
PROSPECTIVE_REPLAY_ELIGIBLE_STATUSES = frozenset({
    QualificationStatus.QUALIFIED_FOR_HISTORICAL_RESEARCH.value,
    QualificationStatus.QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY.value,
})

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

ATTEMPT_REQUIRED_FIELDS = frozenset({
    "schema_version",
    "attempt_id",
    "fixture_identifier",
    "market_id",
    "line",
    "provider_identifier",
    "source",
    "bookmaker_identifier",
    "provider_event_identifier",
    "provider_market_identifier",
    "offset_seconds_before_kickoff",
    "scheduled_at",
    "attempted_at",
    "result",
    "capture_method",
    "quote_snapshot_id",
})

QUOTE_REQUIRED_FIELDS = frozenset({
    "schema_version",
    "attempt_id",
    "fixture_identifier",
    "market_id",
    "outcome_id",
    "line",
    "provider_identifier",
    "source",
    "bookmaker_identifier",
    "provider_event_identifier",
    "provider_market_identifier",
    "provider_selection_identifier",
    "quote_snapshot_id",
    "observed_at",
    "fixture_kickoff",
    "decimal_odds",
    "is_genuine",
})

FORBIDDEN_INPUT_KEYS = frozenset({
    "home_goals",
    "away_goals",
    "full_time_home_goals",
    "full_time_away_goals",
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
    "stake",
    "profit",
    "profitability",
    "bet",
    "bet_decision",
    "decision_label",
    "acca_selection",
    "settled_outcome",
})

DECIMAL_CONTEXT = Context(
    prec=50,
    rounding=ROUND_HALF_EVEN,
    Emin=-999,
    Emax=999,
)


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
    AVAILABLE_QUALIFIED_SNAPSHOT = "AVAILABLE_QUALIFIED_SNAPSHOT"
    EXPLICIT_MARKET_UNAVAILABLE = "EXPLICIT_MARKET_UNAVAILABLE"
    EXPLICIT_FIXTURE_UNAVAILABLE = "EXPLICIT_FIXTURE_UNAVAILABLE"
    EXPLICIT_SOURCE_UNAVAILABLE = "EXPLICIT_SOURCE_UNAVAILABLE"
    NO_ATTEMPT_RECORD = "NO_ATTEMPT_RECORD"
    CAPTURE_ERROR = "CAPTURE_ERROR"
    INVALID_CAPTURE_ERROR_WITH_QUOTES = "INVALID_CAPTURE_ERROR_WITH_QUOTES"
    INVALID_UNAVAILABLE_ATTEMPT_WITH_QUOTES = "INVALID_UNAVAILABLE_ATTEMPT_WITH_QUOTES"
    INVALID_CAPTURED_ATTEMPT_WITH_REJECTED_QUOTES = "INVALID_CAPTURED_ATTEMPT_WITH_REJECTED_QUOTES"
    NO_VALID_QUOTES_FOR_CAPTURED_ATTEMPT = "NO_VALID_QUOTES_FOR_CAPTURED_ATTEMPT"
    INCOMPLETE_MARKET_SNAPSHOT = "INCOMPLETE_MARKET_SNAPSHOT"
    STALE_QUOTE = "STALE_QUOTE"
    INVALID_ATTEMPT_RECORD = "INVALID_ATTEMPT_RECORD"


@dataclass(frozen=True)
class FixtureMetadata:
    fixture_identifier: str
    kickoff: datetime


@dataclass(frozen=True)
class OutcomeMapping:
    outcome_id: OutcomeId
    provider_selection_identifier: str


@dataclass(frozen=True)
class MarketMapping:
    market_id: MarketId
    provider_market_identifier: str
    outcomes: dict[OutcomeId, OutcomeMapping]


@dataclass(frozen=True)
class ProviderMapping:
    provider_identifier: str
    source: str
    bookmaker_identifier: str
    provider_event_identifier: str
    markets: dict[MarketId, MarketMapping]


@dataclass(frozen=True)
class ObservationAttempt:
    input_record_sha256: str
    attempt_id: str
    fixture_identifier: str
    market_id: MarketId
    source: str
    provider_identifier: str
    bookmaker_identifier: str
    provider_event_identifier: Optional[str]
    provider_market_identifier: Optional[str]
    offset_seconds_before_kickoff: int
    scheduled_at: datetime
    attempted_at: datetime
    result: AttemptResult
    capture_method: str
    quote_snapshot_id: Optional[str]


@dataclass(frozen=True)
class ProspectiveQuote:
    input_record_sha256: str
    attempt_id: str
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
class ValidatedSnapshot:
    snapshot_sha256: str
    attempt_id: str
    fixture_identifier: str
    market_id: MarketId
    source: str
    provider_identifier: str
    bookmaker_identifier: str
    offset_seconds_before_kickoff: int
    scheduled_at: datetime
    attempted_at: datetime
    quote_snapshot_id: str
    observed_at: datetime
    yes_quote_record_sha256: str
    no_quote_record_sha256: str
    quote_age_seconds_at_attempt: int


@dataclass(frozen=True)
class EvaluationRecord:
    evaluation_record_sha256: str
    fixture_identifier: str
    market_id: MarketId
    offset_seconds_before_kickoff: int
    scheduled_at: datetime
    availability_status: AvailabilityStatus
    availability_reason: str
    attempt_id: Optional[str]
    attempt_result: Optional[str]
    attempted_at: Optional[datetime]
    attempt_window_seconds_used: Optional[int]
    quote_snapshot_id: Optional[str]
    observed_at: Optional[datetime]
    quote_age_seconds_at_attempt: Optional[int]
    has_valid_snapshot: bool


@dataclass(frozen=True)
class AttemptParseResult:
    raw_record: Mapping[str, Any]
    input_record_sha256: str
    is_valid: bool
    attempt: Optional[ObservationAttempt]
    rejection_reasons: tuple[str, ...]
    expected_key: Optional[tuple[str, MarketId, int]]


@dataclass(frozen=True)
class QuoteParseResult:
    raw_record: Mapping[str, Any]
    input_record_sha256: str
    is_valid: bool
    quote: Optional[ProspectiveQuote]
    rejection_reasons: tuple[str, ...]


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    ).encode("utf-8")


def canonical_record_sha256(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(record)).hexdigest()


def _require_schema_version(payload: Mapping[str, Any], label: str) -> None:
    value = payload.get("schema_version")
    if type(value) is not int or value != SCHEMA_VERSION:
        raise ValueError(f"{label} schema_version must be integer 1")


def _validate_exact_fields(
    value: Mapping[str, Any],
    required: frozenset[str],
    label: str,
) -> tuple[str, ...]:
    supplied = frozenset(str(key) for key in value)
    reasons = []
    if required - supplied:
        reasons.append(f"{label}_MISSING_FIELD")
    if supplied - required:
        reasons.append(f"{label}_UNEXPECTED_FIELD")
    return tuple(reasons)


def assert_no_forbidden_fields(data: Any, path: str = "") -> None:
    """Recursively ensure no forbidden outcome, model, value, or bet concepts exist."""
    if isinstance(data, Mapping):
        for key, val in data.items():
            current_path = f"{path}.{key}" if path else str(key)
            lower_key = str(key).strip().lower()
            if not lower_key.endswith("_forbidden_from_offset_evaluation"):
                if lower_key in FORBIDDEN_INPUT_KEYS:
                    raise ValueError(f"Forbidden field '{key}' at '{current_path}'")
            assert_no_forbidden_fields(val, current_path)
    elif isinstance(data, (list, tuple, set)):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"
            assert_no_forbidden_fields(item, current_path)


def load_source_qualification(payload: Mapping[str, Any]) -> str:
    """Validate Stage 5B1 report and extract provider_identifier."""
    assert_no_forbidden_fields(payload)
    _require_schema_version(payload, "source qualification")

    if payload.get("dataset_name") != "win-either-half-pricing-source-qualification-v1":
        raise ValueError("Unexpected Stage 5B1 dataset_name")

    qualification = payload.get("qualification")
    if not isinstance(qualification, Mapping):
        raise ValueError("Stage 5B1 qualification must be an object")

    status = qualification.get("prospective_replay_status")
    if status not in PROSPECTIVE_REPLAY_ELIGIBLE_STATUSES:
        raise ValueError(f"Source qualification status not eligible: {status}")

    provider_id = payload.get("provider_identifier")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("Missing Stage 5B1 provider_identifier")

    holdout = payload.get("holdout_governance")
    if not isinstance(holdout, Mapping):
        raise ValueError("Missing Stage 5B1 holdout_governance")
    if holdout.get("prospective_validation_required") is not True:
        raise ValueError("Prospective validation must remain required")
    if holdout.get("production_approval_authorized") is not False:
        raise ValueError("Stage 5B1 must not authorize production")

    statuses = payload.get("market_statuses")
    if not isinstance(statuses, Mapping):
        raise ValueError("Missing Stage 5B1 market_statuses")
    for market in PERMITTED_MARKETS:
        if statuses.get(market.value) != "DISABLED":
            raise ValueError(f"{market.value} must remain DISABLED")

    if not isinstance(payload.get("no_production_approval"), str):
        raise ValueError("Missing Stage 5B1 no-production statement")

    return provider_id.strip()


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_decimal_odds(value: Any) -> Optional[Decimal]:
    if value is None or type(value) is bool or isinstance(value, (list, dict, tuple, set)):
        return None
    try:
        with localcontext(DECIMAL_CONTEXT):
            d = Decimal(str(value))
            if not d.is_finite():
                return None
            if d <= Decimal("1.0"):
                return None
            return d
    except (InvalidOperation, TypeError, ValueError):
        return None


def load_fixtures_dataset(payload: Mapping[str, Any]) -> dict[str, FixtureMetadata]:
    """Parse and validate fixtures dataset."""
    assert_no_forbidden_fields(payload)
    _require_schema_version(payload, "fixtures")

    fixtures_list = payload.get("fixtures")
    if not isinstance(fixtures_list, list):
        raise ValueError("Fixtures payload missing 'fixtures' list")

    fixtures: dict[str, FixtureMetadata] = {}
    for item in fixtures_list:
        if not isinstance(item, Mapping):
            raise ValueError("Fixture record must be an object")
        assert_no_forbidden_fields(item)
        fid = item.get("fixture_identifier")
        if not isinstance(fid, str) or not fid.strip():
            raise ValueError("Fixture missing fixture_identifier")
        if fid in fixtures:
            raise ValueError(f"Duplicate fixture_identifier: {fid}")
        kickoff_raw = item.get("kickoff")
        kickoff = parse_iso_datetime(kickoff_raw)
        if kickoff is None:
            raise ValueError(f"Invalid kickoff timestamp for fixture {fid}")
        fixtures[fid] = FixtureMetadata(fixture_identifier=fid, kickoff=kickoff)

    return fixtures


def validate_attempt_mapping_semantics(
    *,
    fixture_identifier: str,
    market: MarketId,
    result: AttemptResult,
    provider_identifier: Any,
    source: Any,
    bookmaker_identifier: Any,
    provider_event_identifier: Any,
    provider_market_identifier: Any,
    mappings: Mapping[str, ProviderMapping],
) -> tuple[str, ...]:
    """Validate identifiers without treating mapping presence as availability."""
    reasons: set[str] = set()
    mapping = mappings.get(fixture_identifier)

    def common_mapping_mismatch() -> bool:
        return bool(
            mapping is not None
            and (
                provider_identifier != mapping.provider_identifier
                or source != mapping.source
                or bookmaker_identifier != mapping.bookmaker_identifier
            )
        )

    if common_mapping_mismatch():
        reasons.add("MAPPING_MISMATCH")

    event_present = (
        isinstance(provider_event_identifier, str)
        and bool(provider_event_identifier.strip())
    )
    market_present = (
        isinstance(provider_market_identifier, str)
        and bool(provider_market_identifier.strip())
    )

    if provider_event_identifier is not None and not event_present:
        reasons.add("INVALID_PROVIDER_EVENT_IDENTIFIER")
    if provider_market_identifier is not None and not market_present:
        reasons.add("INVALID_PROVIDER_MARKET_IDENTIFIER")

    if result == AttemptResult.QUOTES_CAPTURED:
        if mapping is None:
            reasons.add("MISSING_CAPTURE_MAPPING")
        if not event_present:
            reasons.add("PROVIDER_EVENT_ID_REQUIRED")
        if not market_present:
            reasons.add("PROVIDER_MARKET_ID_REQUIRED")

        if mapping is not None:
            if provider_event_identifier != mapping.provider_event_identifier:
                reasons.add("MAPPING_MISMATCH")
            market_mapping = mapping.markets.get(market)
            if market_mapping is None:
                reasons.add("MISSING_CAPTURE_MAPPING")
            elif (
                provider_market_identifier
                != market_mapping.provider_market_identifier
            ):
                reasons.add("MAPPING_MISMATCH")

    elif result == AttemptResult.MARKET_UNAVAILABLE:
        # The fixture/event must have been resolved at this attempt.
        # A market mapping may exist from another offset; that does not prove
        # the market was available at this timestamp.
        if mapping is None:
            reasons.add("MISSING_EVENT_MAPPING_FOR_MARKET_UNAVAILABLE")
        if not event_present:
            reasons.add("PROVIDER_EVENT_ID_REQUIRED")
        if market_present or provider_market_identifier is not None:
            reasons.add("PROVIDER_MARKET_ID_MUST_BE_NULL")
        if (
            mapping is not None
            and provider_event_identifier != mapping.provider_event_identifier
        ):
            reasons.add("MAPPING_MISMATCH")

    elif result == AttemptResult.FIXTURE_UNAVAILABLE:
        # A mapping may have been learned at a later offset. Its presence is
        # not evidence that the fixture was listed at this attempt.
        if provider_event_identifier is not None:
            reasons.add("PROVIDER_EVENT_ID_MUST_BE_NULL")
        if provider_market_identifier is not None:
            reasons.add("PROVIDER_MARKET_ID_MUST_BE_NULL")

    elif result == AttemptResult.SOURCE_UNAVAILABLE:
        if provider_event_identifier is not None:
            reasons.add("PROVIDER_EVENT_ID_MUST_BE_NULL")
        if provider_market_identifier is not None:
            reasons.add("PROVIDER_MARKET_ID_MUST_BE_NULL")

    elif result == AttemptResult.CAPTURE_ERROR:
        # Valid progress states are:
        #   1. no identifiers resolved;
        #   2. exact event resolved, market unresolved;
        #   3. exact event and exact market resolved.
        if market_present and not event_present:
            reasons.add("PARTIAL_CAPTURE_ERROR_IDENTIFIERS")
        elif event_present:
            if mapping is None:
                reasons.add("MISSING_EVENT_MAPPING_FOR_CAPTURE_ERROR")
            else:
                if (
                    provider_event_identifier
                    != mapping.provider_event_identifier
                ):
                    reasons.add("MAPPING_MISMATCH")
                if market_present:
                    market_mapping = mapping.markets.get(market)
                    if market_mapping is None:
                        reasons.add("MISSING_CAPTURE_MAPPING")
                    elif (
                        provider_market_identifier
                        != market_mapping.provider_market_identifier
                    ):
                        reasons.add("MAPPING_MISMATCH")

    return tuple(sorted(reasons))


def load_provider_mappings_dataset(
    payload: Mapping[str, Any],
    expected_provider: str,
    fixtures: Mapping[str, FixtureMetadata],
) -> dict[str, ProviderMapping]:
    """Parse and validate provider fixture/market/selection mappings."""
    assert_no_forbidden_fields(payload)
    _require_schema_version(payload, "provider mappings")

    mappings_list = payload.get("mappings")
    if not isinstance(mappings_list, list):
        raise ValueError("Provider mappings payload missing 'mappings' list")

    allowed_fixture_ids = set(fixtures)
    mappings: dict[str, ProviderMapping] = {}
    for item in mappings_list:
        if not isinstance(item, Mapping):
            raise ValueError("Mapping record must be an object")
        assert_no_forbidden_fields(item)
        fid = item.get("fixture_identifier")
        if not isinstance(fid, str) or not fid.strip():
            raise ValueError("Mapping missing fixture_identifier")
        if fid in mappings:
            raise ValueError(f"Duplicate mapping for fixture {fid}")

        provider = item.get("provider_identifier")
        if provider != expected_provider:
            raise ValueError(f"Provider mismatch in mapping: {provider} != {expected_provider}")

        source = item.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Mapping missing source")

        bookmaker = item.get("bookmaker_identifier")
        if not isinstance(bookmaker, str) or not bookmaker.strip():
            raise ValueError("Mapping missing bookmaker_identifier")

        event_id = item.get("provider_event_identifier")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Mapping missing provider_event_identifier")

        markets_raw = item.get("markets")
        if not isinstance(markets_raw, Mapping):
            raise ValueError("Mapping missing markets object")

        allowed_market_keys = {market.value for market in PERMITTED_MARKETS}
        supplied_market_keys = set(markets_raw)
        unexpected_market_keys = sorted(supplied_market_keys - allowed_market_keys)
        if unexpected_market_keys:
            raise ValueError(
                f"Provider mapping contains unsupported market keys for {fid}: {unexpected_market_keys}"
            )

        market_map: dict[MarketId, MarketMapping] = {}
        for market in PERMITTED_MARKETS:
            mkt_payload = markets_raw.get(market.value)
            if not isinstance(mkt_payload, Mapping):
                continue
            assert_no_forbidden_fields(mkt_payload)
            mkt_id_str = mkt_payload.get("provider_market_identifier")
            if not isinstance(mkt_id_str, str) or not mkt_id_str.strip():
                raise ValueError(f"Mapping missing provider_market_identifier for {market.value}")

            outcomes_raw = mkt_payload.get("outcomes")
            if not isinstance(outcomes_raw, Mapping):
                raise ValueError(f"Mapping missing outcomes for {market.value}")

            outcome_keys = set(outcomes_raw)
            if outcome_keys != {OutcomeId.YES.value, OutcomeId.NO.value}:
                raise ValueError(
                    f"Provider mapping outcomes must be exactly YES and NO for {fid} / {market.value}"
                )

            yes_identifier = outcomes_raw[OutcomeId.YES.value]
            no_identifier = outcomes_raw[OutcomeId.NO.value]
            if not isinstance(yes_identifier, str) or not yes_identifier.strip():
                raise ValueError(f"Mapping missing YES selection for {fid} / {market.value}")
            if not isinstance(no_identifier, str) or not no_identifier.strip():
                raise ValueError(f"Mapping missing NO selection for {fid} / {market.value}")
            if yes_identifier == no_identifier:
                raise ValueError(
                    f"YES and NO provider selection identifiers must differ for {fid} / {market.value}"
                )

            outcome_map: dict[OutcomeId, OutcomeMapping] = {
                OutcomeId.YES: OutcomeMapping(
                    outcome_id=OutcomeId.YES,
                    provider_selection_identifier=yes_identifier,
                ),
                OutcomeId.NO: OutcomeMapping(
                    outcome_id=OutcomeId.NO,
                    provider_selection_identifier=no_identifier,
                ),
            }

            market_map[market] = MarketMapping(
                market_id=market,
                provider_market_identifier=mkt_id_str,
                outcomes=outcome_map,
            )

        mappings[fid] = ProviderMapping(
            provider_identifier=provider,
            source=source,
            bookmaker_identifier=bookmaker,
            provider_event_identifier=event_id,
            markets=market_map,
        )

    extra_fixture_ids = sorted(set(mappings) - allowed_fixture_ids)
    if extra_fixture_ids:
        raise ValueError(
            f"Provider mappings contain unknown fixtures: {extra_fixture_ids}"
        )

    return mappings


def candidate_expected_key(
    record: Mapping[str, Any],
    fixtures: Mapping[str, FixtureMetadata],
) -> Optional[tuple[str, MarketId, int]]:
    """Compute expected key whenever fixture, market and offset are parseable."""
    fid = record.get("fixture_identifier")
    if not isinstance(fid, str) or fid not in fixtures:
        return None
    mkt_raw = record.get("market_id")
    try:
        market = MarketId(mkt_raw) if isinstance(mkt_raw, str) else None
    except ValueError:
        market = None
    if market not in PERMITTED_MARKETS:
        return None
    offset = record.get("offset_seconds_before_kickoff")
    if type(offset) is not int or offset not in FROZEN_CANDIDATE_OFFSETS_SECONDS:
        return None
    return (fid, market, offset)


def parse_observation_attempts(
    raw_records: Sequence[Mapping[str, Any]],
    fixtures: Mapping[str, FixtureMetadata],
    mappings: Mapping[str, ProviderMapping],
    expected_provider: str,
) -> tuple[
    list[AttemptParseResult],
    dict[str, ObservationAttempt],
    dict[tuple[str, MarketId, int], ObservationAttempt],
    dict[tuple[str, MarketId, int], tuple[AttemptParseResult, ...]],
]:
    """Parse raw observation attempts, validate strict fields, and enforce unique attempt IDs and expected keys."""
    results: list[AttemptParseResult] = []
    seen_attempt_ids: dict[str, int] = {}
    expected_key_counts: Counter[tuple[str, MarketId, int]] = Counter()

    for record in raw_records:
        aid = record.get("attempt_id")
        if isinstance(aid, str) and aid.strip():
            seen_attempt_ids[aid] = seen_attempt_ids.get(aid, 0) + 1
        key = candidate_expected_key(record, fixtures)
        if key is not None:
            expected_key_counts[key] += 1

    valid_attempts_by_id: dict[str, ObservationAttempt] = {}
    valid_attempts_by_key: dict[tuple[str, MarketId, int], ObservationAttempt] = {}
    invalid_attempts_by_key_map: dict[tuple[str, MarketId, int], list[AttemptParseResult]] = {}

    for record in raw_records:
        rec_sha = canonical_record_sha256(record)
        reasons: list[str] = []

        # Check forbidden fields
        try:
            assert_no_forbidden_fields(record)
        except ValueError:
            reasons.append("FORBIDDEN_FIELDS_PRESENT")

        # Validate exact fields
        field_reasons = _validate_exact_fields(record, ATTEMPT_REQUIRED_FIELDS, "ATTEMPT")
        reasons.extend(field_reasons)

        schema_ver = record.get("schema_version")
        if type(schema_ver) is not int or schema_ver != SCHEMA_VERSION:
            reasons.append("INVALID_SCHEMA_VERSION")

        aid = record.get("attempt_id")
        if not isinstance(aid, str) or not aid.strip():
            reasons.append("INVALID_ATTEMPT_ID")
        elif seen_attempt_ids.get(aid, 0) > 1:
            reasons.append("DUPLICATE_ATTEMPT_ID")

        fid = record.get("fixture_identifier")
        if not isinstance(fid, str) or fid not in fixtures:
            reasons.append("UNKNOWN_FIXTURE")

        mkt_raw = record.get("market_id")
        try:
            market = MarketId(mkt_raw) if isinstance(mkt_raw, str) else None
        except ValueError:
            market = None
        if market not in PERMITTED_MARKETS:
            reasons.append("UNKNOWN_MARKET")

        line = record.get("line")
        if line is not None:
            reasons.append("UNEXPECTED_LINE")

        prov = record.get("provider_identifier")
        if prov != expected_provider:
            reasons.append("UNQUALIFIED_SOURCE")

        src = record.get("source")
        if not isinstance(src, str) or not src.strip():
            reasons.append("INVALID_SOURCE")

        bookmaker = record.get("bookmaker_identifier")
        if not isinstance(bookmaker, str) or not bookmaker.strip():
            reasons.append("INVALID_BOOKMAKER")

        prov_event = record.get("provider_event_identifier")
        prov_mkt = record.get("provider_market_identifier")

        offset = record.get("offset_seconds_before_kickoff")
        if type(offset) is not int or offset not in FROZEN_CANDIDATE_OFFSETS_SECONDS:
            reasons.append("INVALID_OFFSET_SECONDS")

        res_raw = record.get("result")
        try:
            result_enum = AttemptResult(res_raw) if isinstance(res_raw, str) else None
        except ValueError:
            result_enum = None
        if result_enum is None:
            reasons.append("UNKNOWN_RESULT")

        method = record.get("capture_method")
        if not isinstance(method, str) or not method.strip():
            reasons.append("INVALID_CAPTURE_METHOD")

        snap_id = record.get("quote_snapshot_id")
        if result_enum == AttemptResult.QUOTES_CAPTURED:
            if not isinstance(snap_id, str) or not snap_id.strip():
                reasons.append("MISSING_SNAPSHOT_ID_FOR_CAPTURED")
        else:
            if snap_id is not None:
                reasons.append("SNAPSHOT_ID_PRESENT_WHEN_NOT_CAPTURED")

        sched_raw = record.get("scheduled_at")
        sched_dt = parse_iso_datetime(sched_raw)
        if sched_dt is None:
            reasons.append("INVALID_SCHEDULED_AT")

        att_raw = record.get("attempted_at")
        att_dt = parse_iso_datetime(att_raw)
        if att_dt is None:
            reasons.append("INVALID_ATTEMPTED_AT")

        # Time coherence checks with fixture
        if fid in fixtures and offset in FROZEN_CANDIDATE_OFFSETS_SECONDS and sched_dt is not None:
            fixture = fixtures[fid]
            expected_sched = fixture.kickoff - timedelta(seconds=offset)
            if sched_dt != expected_sched:
                reasons.append("SCHEDULED_AT_MISMATCH")

            if att_dt is not None:
                if att_dt >= fixture.kickoff:
                    reasons.append("ATTEMPT_AFTER_KICKOFF")
                delta_sec = abs((att_dt - sched_dt).total_seconds())
                if delta_sec > ATTEMPT_WINDOW_SECONDS:
                    reasons.append("ATTEMPT_WINDOW_EXCEEDED")

        # Provider mapping checks according to result semantics
        if fid in fixtures and market in PERMITTED_MARKETS and result_enum is not None:
            mapping_reasons = validate_attempt_mapping_semantics(
                fixture_identifier=fid,
                market=market,
                result=result_enum,
                provider_identifier=prov,
                source=src,
                bookmaker_identifier=bookmaker,
                provider_event_identifier=prov_event,
                provider_market_identifier=prov_mkt,
                mappings=mappings,
            )
            reasons.extend(mapping_reasons)

        # Expected key duplicate check
        expected_key = candidate_expected_key(record, fixtures)
        if expected_key is not None and expected_key_counts[expected_key] > 1:
            reasons.append("DUPLICATE_EXPECTED_KEY")

        normalized_reasons = tuple(sorted(set(reasons)))
        is_valid = len(normalized_reasons) == 0
        attempt_obj = None
        if (
            is_valid
            and expected_key is not None
            and aid is not None
            and market is not None
            and result_enum is not None
            and sched_dt is not None
            and att_dt is not None
        ):
            attempt_obj = ObservationAttempt(
                input_record_sha256=rec_sha,
                attempt_id=aid,
                fixture_identifier=fid,
                market_id=market,
                source=src,
                provider_identifier=prov,
                bookmaker_identifier=bookmaker,
                provider_event_identifier=prov_event,
                provider_market_identifier=prov_mkt,
                offset_seconds_before_kickoff=offset,
                scheduled_at=sched_dt,
                attempted_at=att_dt,
                result=result_enum,
                capture_method=method,
                quote_snapshot_id=snap_id,
            )
            valid_attempts_by_id[aid] = attempt_obj
            valid_attempts_by_key[expected_key] = attempt_obj

        parse_result = AttemptParseResult(
            raw_record=record,
            input_record_sha256=rec_sha,
            is_valid=is_valid,
            attempt=attempt_obj,
            rejection_reasons=normalized_reasons,
            expected_key=expected_key,
        )
        if not is_valid and expected_key is not None:
            invalid_attempts_by_key_map.setdefault(expected_key, []).append(parse_result)

        results.append(parse_result)

    invalid_attempts_by_key = {
        k: tuple(v) for k, v in invalid_attempts_by_key_map.items()
    }
    return results, valid_attempts_by_id, valid_attempts_by_key, invalid_attempts_by_key


def parse_prospective_quotes(
    raw_records: Sequence[Mapping[str, Any]],
    fixtures: Mapping[str, FixtureMetadata],
    mappings: Mapping[str, ProviderMapping],
    valid_attempts_by_id: Mapping[str, ObservationAttempt],
    expected_provider: str,
) -> list[QuoteParseResult]:
    """Parse quotes and validate against linked observation attempt, provider mappings, and freshness."""
    results: list[QuoteParseResult] = []

    for record in raw_records:
        rec_sha = canonical_record_sha256(record)
        reasons: list[str] = []

        # Check forbidden fields
        try:
            assert_no_forbidden_fields(record)
        except ValueError:
            reasons.append("FORBIDDEN_FIELDS_PRESENT")

        # Validate exact fields
        field_reasons = _validate_exact_fields(record, QUOTE_REQUIRED_FIELDS, "QUOTE")
        reasons.extend(field_reasons)

        schema_ver = record.get("schema_version")
        if type(schema_ver) is not int or schema_ver != SCHEMA_VERSION:
            reasons.append("INVALID_SCHEMA_VERSION")

        aid = record.get("attempt_id")
        if not isinstance(aid, str) or not aid.strip():
            reasons.append("INVALID_ATTEMPT_ID")

        fid = record.get("fixture_identifier")
        if not isinstance(fid, str) or fid not in fixtures:
            reasons.append("UNKNOWN_FIXTURE")

        mkt_raw = record.get("market_id")
        try:
            market = MarketId(mkt_raw) if isinstance(mkt_raw, str) else None
        except ValueError:
            market = None
        if market not in PERMITTED_MARKETS:
            reasons.append("INVALID_CANONICAL_MARKET")

        out_raw = record.get("outcome_id")
        try:
            outcome = OutcomeId(out_raw) if isinstance(out_raw, str) else None
        except ValueError:
            outcome = None
        if outcome not in (OutcomeId.YES, OutcomeId.NO):
            reasons.append("INVALID_CANONICAL_OUTCOME")

        line = record.get("line")
        if line is not None:
            reasons.append("INVALID_LINE")

        prov = record.get("provider_identifier")
        if prov != expected_provider:
            reasons.append("UNQUALIFIED_SOURCE")

        src = record.get("source")
        bookmaker = record.get("bookmaker_identifier")
        prov_event = record.get("provider_event_identifier")
        prov_mkt = record.get("provider_market_identifier")
        prov_sel = record.get("provider_selection_identifier")
        snap_id = record.get("quote_snapshot_id")

        obs_raw = record.get("observed_at")
        obs_dt = parse_iso_datetime(obs_raw)
        if obs_dt is None:
            reasons.append("TIMEZONE_MISSING")

        koff_raw = record.get("fixture_kickoff")
        koff_dt = parse_iso_datetime(koff_raw)
        if koff_dt is None:
            reasons.append("INVALID_FIXTURE_KICKOFF")
        elif fid in fixtures and koff_dt != fixtures[fid].kickoff:
            reasons.append("KICKOFF_MISMATCH")

        odds = parse_decimal_odds(record.get("decimal_odds"))
        if odds is None:
            reasons.append("DECIMAL_ODDS_INVALID")

        is_genuine = record.get("is_genuine")
        if is_genuine is not True:
            reasons.append("NON_GENUINE_SOURCE")

        # Validate against linked attempt
        if isinstance(aid, str) and aid.strip():
            if aid not in valid_attempts_by_id:
                reasons.append("UNKNOWN_ATTEMPT_ID")
            else:
                att = valid_attempts_by_id[aid]
                if att.result != AttemptResult.QUOTES_CAPTURED:
                    reasons.append("ATTEMPT_NOT_QUOTES_CAPTURED")
                if fid != att.fixture_identifier:
                    reasons.append("ATTEMPT_FIXTURE_MISMATCH")
                if market != att.market_id:
                    reasons.append("ATTEMPT_MARKET_MISMATCH")
                if prov != att.provider_identifier:
                    reasons.append("ATTEMPT_PROVIDER_MISMATCH")
                if src != att.source:
                    reasons.append("ATTEMPT_SOURCE_MISMATCH")
                if bookmaker != att.bookmaker_identifier:
                    reasons.append("ATTEMPT_BOOKMAKER_MISMATCH")
                if prov_event != att.provider_event_identifier:
                    reasons.append("ATTEMPT_PROVIDER_EVENT_MISMATCH")
                if prov_mkt != att.provider_market_identifier:
                    reasons.append("ATTEMPT_PROVIDER_MARKET_MISMATCH")
                if snap_id != att.quote_snapshot_id:
                    reasons.append("ATTEMPT_SNAPSHOT_MISMATCH")

                if obs_dt is not None and fid in fixtures:
                    fixture = fixtures[fid]
                    if obs_dt >= fixture.kickoff:
                        reasons.append("QUOTE_OBSERVED_AT_OR_AFTER_KICKOFF")
                    quote_age = att.attempted_at - obs_dt
                    if quote_age < timedelta(0):
                        reasons.append("QUOTE_OBSERVED_AFTER_ATTEMPT")
                    elif quote_age > timedelta(seconds=MAXIMUM_QUOTE_AGE_SECONDS):
                        reasons.append("STALE_QUOTE")

        # Validate against provider mappings
        if fid in mappings and market in PERMITTED_MARKETS and outcome in (OutcomeId.YES, OutcomeId.NO):
            mapping = mappings[fid]
            if prov != mapping.provider_identifier or src != mapping.source or bookmaker != mapping.bookmaker_identifier:
                reasons.append("MAPPING_MISMATCH")
            mkt_map = mapping.markets.get(market)
            if mkt_map is None or prov_mkt != mkt_map.provider_market_identifier:
                reasons.append("MAPPING_MARKET_MISMATCH")
            elif outcome not in mkt_map.outcomes or prov_sel != mkt_map.outcomes[outcome].provider_selection_identifier:
                reasons.append("MAPPING_SELECTION_MISMATCH")

        normalized_reasons = tuple(sorted(set(reasons)))
        is_valid = len(normalized_reasons) == 0
        quote_obj = None
        if (
            is_valid
            and aid is not None
            and market is not None
            and outcome is not None
            and obs_dt is not None
            and koff_dt is not None
            and odds is not None
        ):
            quote_obj = ProspectiveQuote(
                input_record_sha256=rec_sha,
                attempt_id=aid,
                provider_identifier=prov,
                source=src,
                bookmaker_identifier=bookmaker,
                fixture_identifier=fid,
                market_id=market,
                outcome_id=outcome,
                quote_snapshot_id=snap_id,
                observed_at=obs_dt,
                fixture_kickoff=koff_dt,
                decimal_odds=odds,
                provider_event_identifier=prov_event,
                provider_market_identifier=prov_mkt,
                provider_selection_identifier=prov_sel,
            )

        results.append(
            QuoteParseResult(
                raw_record=record,
                input_record_sha256=rec_sha,
                is_valid=is_valid,
                quote=quote_obj,
                rejection_reasons=normalized_reasons,
            )
        )

    return results


def evaluate_prospective_replay(
    fixtures: Mapping[str, FixtureMetadata],
    valid_attempts_by_key: Mapping[tuple[str, MarketId, int], ObservationAttempt],
    invalid_attempts_by_key: Mapping[tuple[str, MarketId, int], Sequence[AttemptParseResult]],
    quote_results_by_attempt_id: Mapping[str, Sequence[QuoteParseResult]],
) -> tuple[list[ValidatedSnapshot], list[EvaluationRecord]]:
    """Evaluate 12 expected keys per fixture according to strict precedence rules."""
    snapshots: list[ValidatedSnapshot] = []
    evaluations: list[EvaluationRecord] = []

    # Sort fixtures canonically by kickoff, then fixture_identifier
    sorted_fixtures = sorted(
        fixtures.values(),
        key=lambda f: (f.kickoff, f.fixture_identifier),
    )

    for fixture in sorted_fixtures:
        for market in sorted(PERMITTED_MARKETS, key=lambda m: m.value):
            for offset in sorted(FROZEN_CANDIDATE_OFFSETS_SECONDS, reverse=True):
                key = (fixture.fixture_identifier, market, offset)
                scheduled_at = fixture.kickoff - timedelta(seconds=offset)

                invalid_rows = invalid_attempts_by_key.get(key, ())
                if invalid_rows:
                    eval_sha = hashlib.sha256(
                        f"{fixture.fixture_identifier}|{market.value}|{offset}|{AvailabilityStatus.INVALID.value}|{AvailabilityReason.INVALID_ATTEMPT_RECORD.value}".encode("utf-8")
                    ).hexdigest()
                    evaluations.append(
                        EvaluationRecord(
                            evaluation_record_sha256=eval_sha,
                            fixture_identifier=fixture.fixture_identifier,
                            market_id=market,
                            offset_seconds_before_kickoff=offset,
                            scheduled_at=scheduled_at,
                            availability_status=AvailabilityStatus.INVALID,
                            availability_reason=AvailabilityReason.INVALID_ATTEMPT_RECORD.value,
                            attempt_id=None,
                            attempt_result=None,
                            attempted_at=None,
                            attempt_window_seconds_used=None,
                            quote_snapshot_id=None,
                            observed_at=None,
                            quote_age_seconds_at_attempt=None,
                            has_valid_snapshot=False,
                        )
                    )
                    continue

                if key not in valid_attempts_by_key:
                    # Missing attempt
                    eval_sha = hashlib.sha256(
                        f"{fixture.fixture_identifier}|{market.value}|{offset}|{AvailabilityStatus.UNKNOWN.value}|{AvailabilityReason.NO_ATTEMPT_RECORD.value}".encode("utf-8")
                    ).hexdigest()
                    evaluations.append(
                        EvaluationRecord(
                            evaluation_record_sha256=eval_sha,
                            fixture_identifier=fixture.fixture_identifier,
                            market_id=market,
                            offset_seconds_before_kickoff=offset,
                            scheduled_at=scheduled_at,
                            availability_status=AvailabilityStatus.UNKNOWN,
                            availability_reason=AvailabilityReason.NO_ATTEMPT_RECORD.value,
                            attempt_id=None,
                            attempt_result=None,
                            attempted_at=None,
                            attempt_window_seconds_used=None,
                            quote_snapshot_id=None,
                            observed_at=None,
                            quote_age_seconds_at_attempt=None,
                            has_valid_snapshot=False,
                        )
                    )
                    continue

                attempt = valid_attempts_by_key[key]
                linked_results = list(quote_results_by_attempt_id.get(attempt.attempt_id, []))
                linked_valid_quotes = [
                    result.quote
                    for result in linked_results
                    if result.is_valid and result.quote is not None
                ]
                linked_invalid_results = [
                    result for result in linked_results if not result.is_valid
                ]
                window_used = int(abs((attempt.attempted_at - scheduled_at).total_seconds()))

                if attempt.result == AttemptResult.CAPTURE_ERROR:
                    if linked_results:
                        status = AvailabilityStatus.INVALID
                        reason = AvailabilityReason.INVALID_CAPTURE_ERROR_WITH_QUOTES.value
                    else:
                        status = AvailabilityStatus.UNKNOWN
                        reason = AvailabilityReason.CAPTURE_ERROR.value
                    eval_sha = hashlib.sha256(
                        f"{fixture.fixture_identifier}|{market.value}|{offset}|{status.value}|{reason}".encode("utf-8")
                    ).hexdigest()
                    evaluations.append(
                        EvaluationRecord(
                            evaluation_record_sha256=eval_sha,
                            fixture_identifier=fixture.fixture_identifier,
                            market_id=market,
                            offset_seconds_before_kickoff=offset,
                            scheduled_at=scheduled_at,
                            availability_status=status,
                            availability_reason=reason,
                            attempt_id=attempt.attempt_id,
                            attempt_result=attempt.result.value,
                            attempted_at=attempt.attempted_at,
                            attempt_window_seconds_used=window_used,
                            quote_snapshot_id=None,
                            observed_at=None,
                            quote_age_seconds_at_attempt=None,
                            has_valid_snapshot=False,
                        )
                    )
                    continue

                if attempt.result in (
                    AttemptResult.MARKET_UNAVAILABLE,
                    AttemptResult.FIXTURE_UNAVAILABLE,
                    AttemptResult.SOURCE_UNAVAILABLE,
                ):
                    if linked_results:
                        status = AvailabilityStatus.INVALID
                        reason = AvailabilityReason.INVALID_UNAVAILABLE_ATTEMPT_WITH_QUOTES.value
                    else:
                        status = AvailabilityStatus.UNAVAILABLE
                        if attempt.result == AttemptResult.MARKET_UNAVAILABLE:
                            reason = AvailabilityReason.EXPLICIT_MARKET_UNAVAILABLE.value
                        elif attempt.result == AttemptResult.FIXTURE_UNAVAILABLE:
                            reason = AvailabilityReason.EXPLICIT_FIXTURE_UNAVAILABLE.value
                        else:
                            reason = AvailabilityReason.EXPLICIT_SOURCE_UNAVAILABLE.value
                    eval_sha = hashlib.sha256(
                        f"{fixture.fixture_identifier}|{market.value}|{offset}|{status.value}|{reason}".encode("utf-8")
                    ).hexdigest()
                    evaluations.append(
                        EvaluationRecord(
                            evaluation_record_sha256=eval_sha,
                            fixture_identifier=fixture.fixture_identifier,
                            market_id=market,
                            offset_seconds_before_kickoff=offset,
                            scheduled_at=scheduled_at,
                            availability_status=status,
                            availability_reason=reason,
                            attempt_id=attempt.attempt_id,
                            attempt_result=attempt.result.value,
                            attempted_at=attempt.attempted_at,
                            attempt_window_seconds_used=window_used,
                            quote_snapshot_id=None,
                            observed_at=None,
                            quote_age_seconds_at_attempt=None,
                            has_valid_snapshot=False,
                        )
                    )
                    continue

                if attempt.result == AttemptResult.QUOTES_CAPTURED:
                    if linked_invalid_results:
                        status = AvailabilityStatus.INVALID
                        reason = AvailabilityReason.INVALID_CAPTURED_ATTEMPT_WITH_REJECTED_QUOTES.value
                        eval_sha = hashlib.sha256(
                            f"{fixture.fixture_identifier}|{market.value}|{offset}|{status.value}|{reason}".encode("utf-8")
                        ).hexdigest()
                        evaluations.append(
                            EvaluationRecord(
                                evaluation_record_sha256=eval_sha,
                                fixture_identifier=fixture.fixture_identifier,
                                market_id=market,
                                offset_seconds_before_kickoff=offset,
                                scheduled_at=scheduled_at,
                                availability_status=status,
                                availability_reason=reason,
                                attempt_id=attempt.attempt_id,
                                attempt_result=attempt.result.value,
                                attempted_at=attempt.attempted_at,
                                attempt_window_seconds_used=window_used,
                                quote_snapshot_id=attempt.quote_snapshot_id,
                                observed_at=None,
                                quote_age_seconds_at_attempt=None,
                                has_valid_snapshot=False,
                            )
                        )
                        continue

                    yes_quotes = [q for q in linked_valid_quotes if q.outcome_id == OutcomeId.YES]
                    no_quotes = [q for q in linked_valid_quotes if q.outcome_id == OutcomeId.NO]

                    if not linked_valid_quotes:
                        status = AvailabilityStatus.INVALID
                        reason = AvailabilityReason.NO_VALID_QUOTES_FOR_CAPTURED_ATTEMPT.value
                        eval_sha = hashlib.sha256(
                            f"{fixture.fixture_identifier}|{market.value}|{offset}|{status.value}|{reason}".encode("utf-8")
                        ).hexdigest()
                        evaluations.append(
                            EvaluationRecord(
                                evaluation_record_sha256=eval_sha,
                                fixture_identifier=fixture.fixture_identifier,
                                market_id=market,
                                offset_seconds_before_kickoff=offset,
                                scheduled_at=scheduled_at,
                                availability_status=status,
                                availability_reason=reason,
                                attempt_id=attempt.attempt_id,
                                attempt_result=attempt.result.value,
                                attempted_at=attempt.attempted_at,
                                attempt_window_seconds_used=window_used,
                                quote_snapshot_id=attempt.quote_snapshot_id,
                                observed_at=None,
                                quote_age_seconds_at_attempt=None,
                                has_valid_snapshot=False,
                            )
                        )
                    elif len(yes_quotes) == 1 and len(no_quotes) == 1:
                        yq = yes_quotes[0]
                        nq = no_quotes[0]
                        if yq.quote_snapshot_id == nq.quote_snapshot_id and yq.observed_at == nq.observed_at:
                            age_sec = int((attempt.attempted_at - yq.observed_at).total_seconds())
                            snap_sha = hashlib.sha256(
                                f"{attempt.attempt_id}|{yq.input_record_sha256}|{nq.input_record_sha256}".encode("utf-8")
                            ).hexdigest()
                            snap = ValidatedSnapshot(
                                snapshot_sha256=snap_sha,
                                attempt_id=attempt.attempt_id,
                                fixture_identifier=fixture.fixture_identifier,
                                market_id=market,
                                source=attempt.source,
                                provider_identifier=attempt.provider_identifier,
                                bookmaker_identifier=attempt.bookmaker_identifier,
                                offset_seconds_before_kickoff=offset,
                                scheduled_at=scheduled_at,
                                attempted_at=attempt.attempted_at,
                                quote_snapshot_id=yq.quote_snapshot_id,
                                observed_at=yq.observed_at,
                                yes_quote_record_sha256=yq.input_record_sha256,
                                no_quote_record_sha256=nq.input_record_sha256,
                                quote_age_seconds_at_attempt=age_sec,
                            )
                            snapshots.append(snap)

                            status = AvailabilityStatus.AVAILABLE
                            reason = AvailabilityReason.AVAILABLE_QUALIFIED_SNAPSHOT.value
                            eval_sha = hashlib.sha256(
                                f"{fixture.fixture_identifier}|{market.value}|{offset}|{status.value}|{reason}".encode("utf-8")
                            ).hexdigest()
                            evaluations.append(
                                EvaluationRecord(
                                    evaluation_record_sha256=eval_sha,
                                    fixture_identifier=fixture.fixture_identifier,
                                    market_id=market,
                                    offset_seconds_before_kickoff=offset,
                                    scheduled_at=scheduled_at,
                                    availability_status=status,
                                    availability_reason=reason,
                                    attempt_id=attempt.attempt_id,
                                    attempt_result=attempt.result.value,
                                    attempted_at=attempt.attempted_at,
                                    attempt_window_seconds_used=window_used,
                                    quote_snapshot_id=yq.quote_snapshot_id,
                                    observed_at=yq.observed_at,
                                    quote_age_seconds_at_attempt=age_sec,
                                    has_valid_snapshot=True,
                                )
                            )
                        else:
                            status = AvailabilityStatus.INVALID
                            reason = AvailabilityReason.INCOMPLETE_MARKET_SNAPSHOT.value
                            eval_sha = hashlib.sha256(
                                f"{fixture.fixture_identifier}|{market.value}|{offset}|{status.value}|{reason}".encode("utf-8")
                            ).hexdigest()
                            evaluations.append(
                                EvaluationRecord(
                                    evaluation_record_sha256=eval_sha,
                                    fixture_identifier=fixture.fixture_identifier,
                                    market_id=market,
                                    offset_seconds_before_kickoff=offset,
                                    scheduled_at=scheduled_at,
                                    availability_status=status,
                                    availability_reason=reason,
                                    attempt_id=attempt.attempt_id,
                                    attempt_result=attempt.result.value,
                                    attempted_at=attempt.attempted_at,
                                    attempt_window_seconds_used=window_used,
                                    quote_snapshot_id=attempt.quote_snapshot_id,
                                    observed_at=None,
                                    quote_age_seconds_at_attempt=None,
                                    has_valid_snapshot=False,
                                )
                            )
                    else:
                        status = AvailabilityStatus.INVALID
                        reason = AvailabilityReason.INCOMPLETE_MARKET_SNAPSHOT.value
                        eval_sha = hashlib.sha256(
                            f"{fixture.fixture_identifier}|{market.value}|{offset}|{status.value}|{reason}".encode("utf-8")
                        ).hexdigest()
                        evaluations.append(
                            EvaluationRecord(
                                evaluation_record_sha256=eval_sha,
                                fixture_identifier=fixture.fixture_identifier,
                                market_id=market,
                                offset_seconds_before_kickoff=offset,
                                scheduled_at=scheduled_at,
                                availability_status=status,
                                availability_reason=reason,
                                attempt_id=attempt.attempt_id,
                                attempt_result=attempt.result.value,
                                attempted_at=attempt.attempted_at,
                                attempt_window_seconds_used=window_used,
                                quote_snapshot_id=attempt.quote_snapshot_id,
                                observed_at=None,
                                quote_age_seconds_at_attempt=None,
                                has_valid_snapshot=False,
                            )
                        )

    return snapshots, evaluations


def build_expected_protocol_contract() -> dict[str, Any]:
    """Construct complete expected Stage 5B2 research protocol JSON dictionary."""
    return {
        "schema_version": 1,
        "dataset_name": "win-either-half-prospective-replay-protocol-v1",
        "candidate_offsets_seconds": [
            86400,
            21600,
            10800,
            3600,
            1800,
            900,
        ],
        "attempt_contract": {
            "expected_attempts_per_fixture": 12,
            "attempt_window_seconds": 300,
            "scheduled_at_must_equal_kickoff_minus_offset": True,
            "attempted_at_must_be_before_kickoff": True,
            "attempt_results": [
                "QUOTES_CAPTURED",
                "MARKET_UNAVAILABLE",
                "FIXTURE_UNAVAILABLE",
                "SOURCE_UNAVAILABLE",
                "CAPTURE_ERROR",
            ],
            "identifier_semantics": {
                "QUOTES_CAPTURED": {
                    "provider_event_identifier": "REQUIRED_EXACT_MAPPING",
                    "provider_market_identifier": "REQUIRED_EXACT_MAPPING",
                },
                "MARKET_UNAVAILABLE": {
                    "provider_event_identifier": "REQUIRED_EXACT_FIXTURE_MAPPING",
                    "provider_market_identifier": "MUST_BE_NULL",
                    "target_market_mapping": "MAY_EXIST_FROM_ANOTHER_OFFSET",
                },
                "FIXTURE_UNAVAILABLE": {
                    "provider_event_identifier": "MUST_BE_NULL",
                    "provider_market_identifier": "MUST_BE_NULL",
                    "fixture_mapping": "MAY_EXIST_FROM_ANOTHER_OFFSET",
                },
                "SOURCE_UNAVAILABLE": {
                    "provider_event_identifier": "MUST_BE_NULL",
                    "provider_market_identifier": "MUST_BE_NULL",
                    "fixture_mapping": "MAY_EXIST_FROM_ANOTHER_OFFSET",
                },
                "CAPTURE_ERROR": {
                    "identifier_progression": [
                        "BOTH_NULL",
                        "EVENT_EXACT_MARKET_NULL",
                        "EVENT_EXACT_MARKET_EXACT",
                    ],
                    "market_identifier_requires_event_identifier": True,
                    "non_null_identifiers_must_match_mapping": True,
                },
            },
        },
        "provider_mapping_contract": {
            "fixture_coverage": "PARTIAL",
            "unknown_fixture_mappings_forbidden": True,
            "permitted_market_keys_only": True,
            "supplied_market_requires_exact_yes_no": True,
            "yes_no_selection_identifiers_must_differ": True,
            "captured_attempt_requires_exact_mapping": True,
            "mapping_presence_is_not_temporal_availability_evidence": True,
        },
        "market_scope": {
            "AWAY_WIN_EITHER_HALF": {
                "line": None,
                "outcomes": [
                    "YES",
                    "NO",
                ],
            },
            "HOME_WIN_EITHER_HALF": {
                "line": None,
                "outcomes": [
                    "YES",
                    "NO",
                ],
            },
        },
        "quote_contract": {
            "maximum_quote_age_seconds": 900,
            "requires_same_source": True,
            "requires_same_provider": True,
            "requires_same_bookmaker": True,
            "requires_same_provider_event": True,
            "requires_same_provider_market": True,
            "requires_same_snapshot": True,
            "requires_same_observed_at": True,
            "odds_values_emitted": False,
            "attempt_id_required": True,
            "quotes_must_link_to_exact_attempt": True,
        },
        "input_contract": {
            "attempt_required_fields": sorted(list(ATTEMPT_REQUIRED_FIELDS)),
            "quote_required_fields": sorted(list(QUOTE_REQUIRED_FIELDS)),
            "forbidden_fields": sorted(list(FORBIDDEN_INPUT_KEYS)),
        },
        "availability_contract": {
            "statuses": [
                "AVAILABLE",
                "UNAVAILABLE",
                "UNKNOWN",
                "INVALID",
            ],
            "unavailable_requires_explicit_provider_evidence": True,
            "missing_attempt_status": "UNKNOWN",
            "capture_error_status": "UNKNOWN",
            "contradiction_status": "INVALID",
            "invalid_precedes_unknown": True,
        },
        "holdout_governance": {
            "final_test_season": "2025-26",
            "final_test_status": "ALREADY_CONSUMED_AUDIT_HOLDOUT",
            "match_outcomes_forbidden_from_offset_evaluation": True,
            "model_performance_forbidden_from_offset_evaluation": True,
            "pricing_profitability_forbidden_from_offset_evaluation": True,
            "prospective_validation_required": True,
            "production_approval_authorized": False,
        },
        "output_contract": {
            "row_grain": "ONE_ROW_PER_FIXTURE_MARKET_OFFSET",
            "selected_offset_seconds": None,
            "selection_authorized": False,
            "selection_status": "UNSELECTED",
            "all_outputs_ignored": True,
            "manifest_required": True,
            "transactional_write_required": True,
        },
        "minimum_fixtures_for_interpretation": 100,
        "source_qualification_required_statuses": [
            "QUALIFIED_FOR_HISTORICAL_RESEARCH",
            "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
        ],
        "no_production_approval": True,
    }


def validate_protocol_contract(
    protocol: Mapping[str, Any],
    protocol_raw: bytes,
    *,
    committed_path: Path = DEFAULT_PROTOCOL_PATH,
) -> None:
    """Validate supplied research protocol matches committed file and Python specification."""
    if not committed_path.is_file():
        raise ValueError(f"Committed protocol file missing: {committed_path}")

    committed_raw = committed_path.read_bytes()
    try:
        committed = json.loads(committed_raw.decode("utf-8"))
    except Exception as error:
        raise ValueError("Committed Stage 5B2 protocol is invalid") from error

    if protocol_raw != committed_raw:
        raise ValueError("Supplied Stage 5B2 protocol bytes differ from committed protocol")
    if protocol != committed:
        raise ValueError("Supplied Stage 5B2 protocol differs from committed protocol")

    expected = build_expected_protocol_contract()
    if protocol != expected:
        raise ValueError("Committed Stage 5B2 protocol drifted from Python contract")
