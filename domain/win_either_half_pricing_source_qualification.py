"""Deterministic Stage 5B1 pricing-source qualification contracts.

The module qualifies evidence capabilities, never odds, bets, or providers by
reputation. Every source role uses mandatory gates and fails closed when any
required fact is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId


SCHEMA_VERSION = 1
KICKOFF_TOLERANCE_SECONDS = 300
PERMITTED_MARKETS = (
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
)
PERMITTED_OUTCOMES = (OutcomeId.YES, OutcomeId.NO)


class SourceQualificationError(ValueError):
    """A bounded source-qualification input or invariant failure."""


class SourceRole(str, Enum):
    HISTORICAL_RESEARCH_SOURCE = "HISTORICAL_RESEARCH_SOURCE"
    LIVE_PRICING_SOURCE = "LIVE_PRICING_SOURCE"
    EXECUTION_BOOKMAKER = "EXECUTION_BOOKMAKER"


class QualificationStatus(str, Enum):
    QUALIFIED_FOR_HISTORICAL_RESEARCH = "QUALIFIED_FOR_HISTORICAL_RESEARCH"
    QUALIFIED_FOR_LIVE_PRICING = "QUALIFIED_FOR_LIVE_PRICING"
    QUALIFIED_AS_EXECUTION_BOOKMAKER = "QUALIFIED_AS_EXECUTION_BOOKMAKER"
    QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY = "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY"
    PARTIALLY_QUALIFIED = "PARTIALLY_QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    UNKNOWN = "UNKNOWN"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FixtureMappingStatus(str, Enum):
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"


class GateId(str, Enum):
    EXACT_MARKET_SEMANTICS = "exact_market_semantics"
    EXACT_YES_NO_STRUCTURE = "exact_yes_no_structure"
    RAW_DECIMAL_ODDS = "raw_decimal_odds"
    BOOKMAKER_PROVENANCE = "bookmaker_provenance"
    QUOTE_OBSERVED_AT = "quote_observed_at"
    SAME_BOOKMAKER_SNAPSHOT = "same_bookmaker_snapshot"
    FIXTURE_MAPPING = "fixture_mapping"
    REPRODUCIBLE_EXPORT = "reproducible_export"
    HISTORICAL_RETENTION = "historical_retention"
    FROZEN_PERIOD_COVERAGE = "frozen_period_coverage"
    RESEARCH_RETENTION_PERMISSION = "research_retention_permission"
    CURRENT_MARKET_AVAILABILITY = "current_market_availability"
    FRESHNESS_ENFORCEABLE = "freshness_enforceable"
    REPRODUCIBLE_PROVIDER_MAPPING = "reproducible_provider_mapping"
    PERMITTED_AUTOMATION = "permitted_automation"
    EXACT_EXECUTION_SELECTION = "exact_execution_selection"
    DETERMINISTIC_BETSLIP = "deterministic_betslip"
    VALIDATED_QUOTE_PRICE_MATCH = "validated_quote_price_match"
    CHANGED_ODDS_DETECTION = "changed_odds_detection"
    SUSPENDED_SELECTION_DETECTION = "suspended_selection_detection"
    MISSING_MARKET_DETECTION = "missing_market_detection"
    EXPLICIT_USER_CONFIRMATION = "explicit_user_confirmation"
    BOOKING_CODE_SUPPORT = "booking_code_support"


HISTORICAL_REQUIRED_GATES = (
    GateId.EXACT_MARKET_SEMANTICS,
    GateId.EXACT_YES_NO_STRUCTURE,
    GateId.RAW_DECIMAL_ODDS,
    GateId.BOOKMAKER_PROVENANCE,
    GateId.QUOTE_OBSERVED_AT,
    GateId.SAME_BOOKMAKER_SNAPSHOT,
    GateId.FIXTURE_MAPPING,
    GateId.REPRODUCIBLE_EXPORT,
    GateId.HISTORICAL_RETENTION,
    GateId.FROZEN_PERIOD_COVERAGE,
    GateId.RESEARCH_RETENTION_PERMISSION,
)
LIVE_REQUIRED_GATES = (
    GateId.EXACT_MARKET_SEMANTICS,
    GateId.EXACT_YES_NO_STRUCTURE,
    GateId.RAW_DECIMAL_ODDS,
    GateId.BOOKMAKER_PROVENANCE,
    GateId.QUOTE_OBSERVED_AT,
    GateId.SAME_BOOKMAKER_SNAPSHOT,
    GateId.FIXTURE_MAPPING,
    GateId.CURRENT_MARKET_AVAILABILITY,
    GateId.FRESHNESS_ENFORCEABLE,
    GateId.REPRODUCIBLE_PROVIDER_MAPPING,
)
EXECUTION_REQUIRED_GATES = (
    GateId.EXACT_MARKET_SEMANTICS,
    GateId.EXACT_YES_NO_STRUCTURE,
    GateId.FIXTURE_MAPPING,
    GateId.PERMITTED_AUTOMATION,
    GateId.EXACT_EXECUTION_SELECTION,
    GateId.DETERMINISTIC_BETSLIP,
    GateId.VALIDATED_QUOTE_PRICE_MATCH,
    GateId.CHANGED_ODDS_DETECTION,
    GateId.SUSPENDED_SELECTION_DETECTION,
    GateId.MISSING_MARKET_DETECTION,
    GateId.EXPLICIT_USER_CONFIRMATION,
    GateId.BOOKING_CODE_SUPPORT,
)
PROSPECTIVE_REQUIRED_GATES = (
    *LIVE_REQUIRED_GATES,
    GateId.REPRODUCIBLE_EXPORT,
    GateId.RESEARCH_RETENTION_PERMISSION,
)

ROLE_REQUIRED_GATES = {
    SourceRole.HISTORICAL_RESEARCH_SOURCE: HISTORICAL_REQUIRED_GATES,
    SourceRole.LIVE_PRICING_SOURCE: LIVE_REQUIRED_GATES,
    SourceRole.EXECUTION_BOOKMAKER: EXECUTION_REQUIRED_GATES,
}
ROLE_QUALIFIED_STATUS = {
    SourceRole.HISTORICAL_RESEARCH_SOURCE:
        QualificationStatus.QUALIFIED_FOR_HISTORICAL_RESEARCH,
    SourceRole.LIVE_PRICING_SOURCE:
        QualificationStatus.QUALIFIED_FOR_LIVE_PRICING,
    SourceRole.EXECUTION_BOOKMAKER:
        QualificationStatus.QUALIFIED_AS_EXECUTION_BOOKMAKER,
}


HOME_YES_SETTLEMENT = "home team wins at least one regulation half"
HOME_NO_SETTLEMENT = "home team does not win either regulation half"
AWAY_YES_SETTLEMENT = "away team wins at least one regulation half"
AWAY_NO_SETTLEMENT = "away team does not win either regulation half"
MARKET_SEMANTICS = {
    MarketId.HOME_WIN_EITHER_HALF: {
        "market_description": "Home Team to Win Either Half",
        "subject": "HOME_TEAM",
        "yes_settlement": HOME_YES_SETTLEMENT,
        "no_settlement": HOME_NO_SETTLEMENT,
    },
    MarketId.AWAY_WIN_EITHER_HALF: {
        "market_description": "Away Team to Win Either Half",
        "subject": "AWAY_TEAM",
        "yes_settlement": AWAY_YES_SETTLEMENT,
        "no_settlement": AWAY_NO_SETTLEMENT,
    },
}


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _aware_utc(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise SourceQualificationError(f"{field} must be ISO-8601") from error
    else:
        raise SourceQualificationError(f"{field} is required")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceQualificationError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class GateEvidence:
    status: GateStatus
    reason: str
    evidence_reference: Optional[str]
    checked_at: datetime

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GateEvidence":
        if not isinstance(value, Mapping):
            raise SourceQualificationError("Gate evidence must be an object")
        try:
            status = GateStatus(value.get("status"))
        except (TypeError, ValueError) as error:
            raise SourceQualificationError("Gate status is invalid") from error
        reason = _text(value.get("reason"))
        if reason is None:
            raise SourceQualificationError("Gate reason is required")
        reference = _text(value.get("evidence_reference"))
        if status is GateStatus.PASS and reference is None:
            raise SourceQualificationError("Passing gates require evidence_reference")
        return cls(
            status=status,
            reason=reason[:500],
            evidence_reference=reference,
            checked_at=_aware_utc(value.get("checked_at"), "gate checked_at"),
        )

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "evidence_reference": self.evidence_reference,
            "checked_at": _timestamp(self.checked_at),
        }


def validate_market_semantics(value: Mapping[str, Any]) -> GateEvidence:
    """Require exact canonical settlement proof; aliases and approximations fail."""
    checked_at = _aware_utc(value.get("checked_at"), "market semantics checked_at")
    try:
        market = MarketId(value.get("market_id"))
    except (TypeError, ValueError):
        return GateEvidence(GateStatus.FAIL, "UNKNOWN_MARKET", None, checked_at)
    expected = MARKET_SEMANTICS.get(market)
    if expected is None:
        return GateEvidence(GateStatus.FAIL, "UNSUPPORTED_MARKET", None, checked_at)
    if value.get("line") is not None:
        return GateEvidence(GateStatus.FAIL, "LINE_MUST_BE_NULL", None, checked_at)
    reference = _text(value.get("evidence_reference"))
    if reference is None:
        return GateEvidence(GateStatus.UNKNOWN, "MISSING_EVIDENCE", None, checked_at)
    supplied = {
        key: _text(value.get(key))
        for key in (
            "market_description",
            "subject",
            "yes_settlement",
            "no_settlement",
        )
    }
    if any(value is None for value in supplied.values()):
        return GateEvidence(
            GateStatus.UNKNOWN,
            "MISSING_MARKET_DESCRIPTION",
            reference,
            checked_at,
        )
    if supplied != expected:
        return GateEvidence(
            GateStatus.FAIL,
            "MARKET_SEMANTICS_MISMATCH",
            reference,
            checked_at,
        )
    outcomes = value.get("outcome_identifiers")
    if outcomes != [OutcomeId.YES.value, OutcomeId.NO.value]:
        return GateEvidence(
            GateStatus.FAIL, "YES_NO_IDENTIFIERS_MISMATCH", reference, checked_at
        )
    return GateEvidence(
        GateStatus.PASS, "EXACT_CANONICAL_SEMANTICS", reference, checked_at
    )


def qualify_mandatory_gates(
    role: SourceRole,
    gates: Mapping[GateId, GateEvidence],
) -> QualificationStatus:
    required = ROLE_REQUIRED_GATES[role]
    statuses = [gates.get(gate) for gate in required]
    if any(value is not None and value.status is GateStatus.FAIL for value in statuses):
        return QualificationStatus.DISQUALIFIED
    present = [value for value in statuses if value is not None]
    if len(present) == len(required) and all(
        value.status in {GateStatus.PASS, GateStatus.NOT_APPLICABLE}
        for value in present
    ):
        return ROLE_QUALIFIED_STATUS[role]
    if any(value.status is GateStatus.PASS for value in present):
        return QualificationStatus.PARTIALLY_QUALIFIED
    return QualificationStatus.UNKNOWN


def qualify_prospective_replay(
    gates: Mapping[GateId, GateEvidence],
) -> QualificationStatus:
    statuses = [gates.get(gate) for gate in PROSPECTIVE_REQUIRED_GATES]
    if any(value is not None and value.status is GateStatus.FAIL for value in statuses):
        return QualificationStatus.DISQUALIFIED
    if len([value for value in statuses if value is not None]) == len(statuses) and all(
        value is not None
        and value.status in {GateStatus.PASS, GateStatus.NOT_APPLICABLE}
        for value in statuses
    ):
        if qualify_mandatory_gates(
            SourceRole.HISTORICAL_RESEARCH_SOURCE, gates
        ) is QualificationStatus.QUALIFIED_FOR_HISTORICAL_RESEARCH:
            return QualificationStatus.QUALIFIED_FOR_HISTORICAL_RESEARCH
        return QualificationStatus.QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY
    if any(value is not None and value.status is GateStatus.PASS for value in statuses):
        return QualificationStatus.PARTIALLY_QUALIFIED
    return QualificationStatus.UNKNOWN


@dataclass(frozen=True)
class FixtureReference:
    provider_event_identifier: Optional[str]
    competition_identifier: Optional[str]
    season_identifier: Optional[str]
    kickoff: Optional[datetime]
    home_participant_identifier: Optional[str]
    home_participant_name: Optional[str]
    away_participant_identifier: Optional[str]
    away_participant_name: Optional[str]
    neutral_venue: Optional[bool]
    fixture_status: Optional[str]


def evaluate_fixture_mapping(
    provider: FixtureReference,
    canonical: FixtureReference,
    *,
    fuzzy_only: bool = False,
    kickoff_tolerance_seconds: int = KICKOFF_TOLERANCE_SECONDS,
) -> FixtureMappingStatus:
    """Map only explicit identifiers and bounded kickoff agreement."""
    required = (
        provider.provider_event_identifier,
        provider.kickoff,
        provider.home_participant_identifier,
        provider.away_participant_identifier,
        canonical.kickoff,
        canonical.home_participant_identifier,
        canonical.away_participant_identifier,
    )
    if any(value is None for value in required):
        return FixtureMappingStatus.UNAVAILABLE
    if fuzzy_only:
        return FixtureMappingStatus.AMBIGUOUS
    if (
        provider.home_participant_identifier
        == canonical.away_participant_identifier
        and provider.away_participant_identifier
        == canonical.home_participant_identifier
    ):
        return FixtureMappingStatus.CONFLICT
    if (
        provider.home_participant_identifier
        != canonical.home_participant_identifier
        or provider.away_participant_identifier
        != canonical.away_participant_identifier
    ):
        return FixtureMappingStatus.AMBIGUOUS
    provider_kickoff = _aware_utc(provider.kickoff, "provider kickoff")
    canonical_kickoff = _aware_utc(canonical.kickoff, "canonical kickoff")
    if abs((provider_kickoff - canonical_kickoff).total_seconds()) > (
        kickoff_tolerance_seconds
    ):
        return FixtureMappingStatus.CONFLICT
    comparable_fields = (
        (provider.competition_identifier, canonical.competition_identifier),
        (provider.season_identifier, canonical.season_identifier),
        (provider.neutral_venue, canonical.neutral_venue),
        (provider.fixture_status, canonical.fixture_status),
    )
    if any(
        provider_value is not None
        and canonical_value is not None
        and provider_value != canonical_value
        for provider_value, canonical_value in comparable_fields
    ):
        return FixtureMappingStatus.CONFLICT
    return FixtureMappingStatus.EXACT


@dataclass(frozen=True)
class SnapshotIdentityResult:
    status: GateStatus
    reason: str
    snapshot_identifier: Optional[str]
    derived: bool


def validate_snapshot_identity(
    *,
    provider_identifier: Any,
    fixture_identifier: Any,
    market_id: Any,
    bookmaker_identifier: Any,
    yes_observed_at: Any,
    no_observed_at: Any,
    native_snapshot_id: Any = None,
) -> SnapshotIdentityResult:
    try:
        market = MarketId(market_id)
    except (TypeError, ValueError):
        return SnapshotIdentityResult(GateStatus.FAIL, "UNKNOWN_MARKET", None, False)
    if market not in PERMITTED_MARKETS:
        return SnapshotIdentityResult(GateStatus.FAIL, "UNKNOWN_MARKET", None, False)
    required = tuple(
        _text(value)
        for value in (provider_identifier, fixture_identifier, bookmaker_identifier)
    )
    if any(value is None for value in required):
        return SnapshotIdentityResult(
            GateStatus.UNKNOWN, "MISSING_SNAPSHOT_COMPONENT", None, False
        )
    try:
        yes_time = _aware_utc(yes_observed_at, "YES observed_at")
        no_time = _aware_utc(no_observed_at, "NO observed_at")
    except SourceQualificationError as error:
        return SnapshotIdentityResult(GateStatus.FAIL, str(error), None, False)
    if yes_time != no_time:
        return SnapshotIdentityResult(
            GateStatus.FAIL, "MIXED_OBSERVED_AT", None, False
        )
    native = _text(native_snapshot_id)
    if native is not None:
        return SnapshotIdentityResult(GateStatus.PASS, "NATIVE_SNAPSHOT_ID", native, False)
    material = "|".join(
        (
            required[0],
            required[1],
            market.value,
            required[2],
            _timestamp(yes_time),
        )
    )
    derived = "derived-sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
    return SnapshotIdentityResult(GateStatus.PASS, "DERIVED_COMMON_TIMESTAMP", derived, True)


@dataclass(frozen=True)
class DecisionProtocol:
    decision_protocol_id: str
    seconds_before_kickoff: Optional[int]
    maximum_quote_age_seconds: int
    snapshot_selection_rule: str
    timezone: str
    postponed_fixture_handling: str
    rescheduled_fixture_handling: str
    kickoff_correction_handling: str
    abandoned_cancelled_handling: str
    frozen_timestamp: Optional[str]
    frozen_revision: Optional[str]

    def to_dict(self) -> dict:
        return {
            "decision_protocol_id": self.decision_protocol_id,
            "seconds_before_kickoff": self.seconds_before_kickoff,
            "maximum_quote_age_seconds": self.maximum_quote_age_seconds,
            "snapshot_selection_rule": self.snapshot_selection_rule,
            "timezone": self.timezone,
            "postponed_fixture_handling": self.postponed_fixture_handling,
            "rescheduled_fixture_handling": self.rescheduled_fixture_handling,
            "kickoff_correction_handling": self.kickoff_correction_handling,
            "abandoned_cancelled_handling": self.abandoned_cancelled_handling,
            "frozen_timestamp": self.frozen_timestamp,
            "frozen_revision": self.frozen_revision,
        }


DEFAULT_DECISION_PROTOCOL = DecisionProtocol(
    decision_protocol_id="win-either-half-pricing-decision-protocol-v1-unselected",
    seconds_before_kickoff=None,
    maximum_quote_age_seconds=900,
    snapshot_selection_rule="LATEST_COMPLETE_SAME_BOOKMAKER_SNAPSHOT_NOT_AFTER_DECISION",
    timezone="UTC",
    postponed_fixture_handling="UNAVAILABLE_PENDING_EXPLICIT_RESCHEDULE_REVIEW",
    rescheduled_fixture_handling="REQUIRE_NEW_FROZEN_KICKOFF_AND_DECISION_TIMESTAMP",
    kickoff_correction_handling="FAIL_CLOSED_AND_REBUILD_PROTOCOL_INPUT",
    abandoned_cancelled_handling="UNAVAILABLE",
    frozen_timestamp=None,
    frozen_revision=None,
)


def canonical_market_registry_snapshot() -> dict:
    return {
        market.value: {
            "display_name": MARKET_REGISTRY[market].display_name,
            "family": MARKET_REGISTRY[market].family.value,
        }
        for market in sorted(MarketId, key=lambda item: item.value)
    }


__all__ = [
    "DEFAULT_DECISION_PROTOCOL",
    "EXECUTION_REQUIRED_GATES",
    "FixtureMappingStatus",
    "FixtureReference",
    "GateEvidence",
    "GateId",
    "GateStatus",
    "HISTORICAL_REQUIRED_GATES",
    "KICKOFF_TOLERANCE_SECONDS",
    "LIVE_REQUIRED_GATES",
    "MARKET_SEMANTICS",
    "PERMITTED_MARKETS",
    "PERMITTED_OUTCOMES",
    "PROSPECTIVE_REQUIRED_GATES",
    "QualificationStatus",
    "ROLE_REQUIRED_GATES",
    "SCHEMA_VERSION",
    "SnapshotIdentityResult",
    "SourceQualificationError",
    "SourceRole",
    "canonical_market_registry_snapshot",
    "evaluate_fixture_mapping",
    "qualify_mandatory_gates",
    "qualify_prospective_replay",
    "validate_market_semantics",
    "validate_snapshot_identity",
]
