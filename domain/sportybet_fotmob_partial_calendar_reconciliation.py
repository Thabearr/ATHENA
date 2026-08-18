"""Fail-closed SportyBet -> FotMob partial-calendar reconciliation candidate.

This boundary consumes the exact PR #158 event-local GMT qualification and
already-reviewed FotMob fixture catalog inputs. The PR #158 artifact is not
trusted by shape or hash alone: it is deterministically re-derived from its exact
upstream SportyBet event and Terms evidence and must be canonical-byte identical.

Matching is exact and case-sensitive on home, away, competition, day, month,
weekday, hour and minute. FotMob kickoff seconds and microseconds must be zero.
The SportyBet year remains unknown and is deliberately ignored for candidate
matching, so even one unique FotMob row does not prove the SportyBet year or
fixture identity. No fuzzy aliases, participant reversal, kickoff tolerance,
pricing, selection, booking-code, execution or BET authority is created.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import re
import types
from collections.abc import Iterable, Mapping
from typing import Any

from domain import sportybet_event_local_time_basis as local_time
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    parse_utc_timestamp,
    serialize_utc,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-fotmob-partial-calendar-reconciliation-v1"
PROVIDER = "SportyBet"
STATUS = "PARTIAL_CALENDAR_RECONCILIATION_CANDIDATE_YEAR_UNPROVEN"
MATCHING_BASIS = (
    "EXACT_HOME_AWAY_COMPETITION_DAY_MONTH_WEEKDAY_HOUR_MINUTE_GMT_"
    "FOTMOB_ZERO_SECONDS_YEAR_IGNORED_NO_FUZZY_NO_REVERSAL_NO_TOLERANCE"
)
TIME_ZONE_LABEL = "GMT"
UTC_OFFSET_SECONDS = 0
MAX_CANONICAL_BYTES = 512 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "bookmaker_equivalence_authorized",
        "booking_code_authorized",
        "canonical_market_mapping_authorized",
        "fixture_reconciliation_authorized",
        "fresh_price_authorized",
        "model_integration_authorized",
        "network_acquisition_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "sportybet_execution_authorized",
    }
)


class SportyBetFotMobPartialCalendarError(ValueError):
    """Raised when the partial-calendar reconciliation boundary fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetFotMobPartialCalendarError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetFotMobPartialCalendarError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetFotMobPartialCalendarError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _evidence_id(value: Any, label: str) -> str:
    if type(value) is not str or _EVIDENCE_ID_RE.fullmatch(value) is None:
        raise SportyBetFotMobPartialCalendarError(f"{label} is invalid")
    return value


def _text(value: Any, label: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SportyBetFotMobPartialCalendarError(
            f"{label} must be a non-empty exact trimmed string"
        )
    if len(value) > maximum:
        raise SportyBetFotMobPartialCalendarError(
            f"{label} exceeds {maximum} characters"
        )
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise SportyBetFotMobPartialCalendarError(
            f"{label} contains a control character"
        )
    return value


def _canonical_utc(value: Any, label: str) -> str:
    if type(value) is not str:
        raise SportyBetFotMobPartialCalendarError(f"{label} must be a string")
    try:
        parsed = parse_utc_timestamp(value, label)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetFotMobPartialCalendarError(str(exc)) from exc
    if serialize_utc(parsed) != value:
        raise SportyBetFotMobPartialCalendarError(
            f"{label} must use canonical UTC serialization"
        )
    return value


def _canonical_mapping_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetFotMobPartialCalendarError(
            "canonical serialization failed"
        ) from exc


def _reviewed_fotmob_rows(
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> tuple[FotMobReviewedFixtureCatalogInput, ...]:
    try:
        rows = tuple(fixtures)
    except TypeError as exc:
        raise SportyBetFotMobPartialCalendarError(
            "fixtures must be an iterable of reviewed FotMob inputs"
        ) from exc
    if not rows:
        raise SportyBetFotMobPartialCalendarError(
            "at least one reviewed FotMob fixture is required"
        )
    if any(type(item) is not FotMobReviewedFixtureCatalogInput for item in rows):
        raise SportyBetFotMobPartialCalendarError(
            "fixture population contains a non-reviewed FotMob catalog input"
        )
    source_ids = [item.source_fixture_identifier for item in rows]
    if len(source_ids) != len(set(source_ids)):
        raise SportyBetFotMobPartialCalendarError(
            "duplicate FotMob source_fixture_identifier in reconciliation population"
        )
    try:
        return tuple(sorted(rows, key=lambda item: int(item.source_fixture_identifier)))
    except ValueError as exc:  # defensive; reviewed input already enforces this
        raise SportyBetFotMobPartialCalendarError(
            "FotMob source fixture identifier is not canonical decimal"
        ) from exc


def canonical_fotmob_population_bytes(
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> bytes:
    rows = _reviewed_fotmob_rows(fixtures)
    return b"".join(_canonical_mapping_bytes(item.to_dict()) for item in rows)


def fotmob_population_sha256(
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> str:
    return hashlib.sha256(canonical_fotmob_population_bytes(fixtures)).hexdigest()


def _rederive_exact_time_basis(
    *,
    supplied: Any,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
) -> local_time.SportyBetEventLocalTimeBasis:
    if not isinstance(supplied, local_time.SportyBetEventLocalTimeBasis):
        raise SportyBetFotMobPartialCalendarError(
            "time_basis must be a PR #158 SportyBetEventLocalTimeBasis"
        )
    try:
        rebuilt = local_time.build_event_local_time_basis(
            event_manifest=event_manifest,
            event_inventory=event_inventory,
            event_raw_html=event_raw_html,
            terms_qualification=terms_qualification,
            terms_raw_html=terms_raw_html,
        )
        supplied_bytes = local_time.canonical_time_basis_bytes(supplied)
        rebuilt_bytes = local_time.canonical_time_basis_bytes(rebuilt)
    except local_time.SportyBetEventLocalTimeBasisError as exc:
        raise SportyBetFotMobPartialCalendarError(str(exc)) from exc
    if supplied_bytes != rebuilt_bytes:
        raise SportyBetFotMobPartialCalendarError(
            "PR #158 time-basis artifact is not the exact deterministic derivative of upstream evidence"
        )
    if (
        rebuilt.specific_event_time_basis_qualified is not True
        or rebuilt.kickoff_timezone != TIME_ZONE_LABEL
        or rebuilt.utc_offset_seconds != UTC_OFFSET_SECONDS
        or rebuilt.kickoff_year is not None
        or rebuilt.kickoff_utc is not None
    ):
        raise SportyBetFotMobPartialCalendarError(
            "PR #158 time basis does not carry the reviewed GMT/year-unknown state"
        )
    return rebuilt


def _kickoff_partial_key(value: dt.datetime) -> tuple[int, int, str, int, int] | None:
    kickoff = value.astimezone(dt.timezone.utc)
    # A displayed SportyBet HH:MM is not evidence for rounding a FotMob timestamp.
    # Require the trusted FotMob instant itself to lie exactly on the minute boundary.
    if kickoff.second != 0 or kickoff.microsecond != 0:
        return None
    return (
        kickoff.day,
        kickoff.month,
        _WEEKDAYS[kickoff.weekday()],
        kickoff.hour,
        kickoff.minute,
    )


def _sportybet_partial_key(
    value: local_time.SportyBetEventLocalTimeBasis,
) -> tuple[int, int, str, int, int]:
    return (
        value.kickoff_day,
        value.kickoff_month,
        value.kickoff_weekday,
        value.kickoff_hour,
        value.kickoff_minute,
    )


@dataclasses.dataclass(frozen=True)
class MatchedFotMobPartialCalendarFixture:
    source_fixture_identifier: str
    source_capture_manifest_sha256: str
    candidate_sha256: str
    evidence_sha256: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: str
    fotmob_year: int

    def __post_init__(self) -> None:
        _text(self.source_fixture_identifier, "source_fixture_identifier", maximum=64)
        try:
            parsed_id = int(self.source_fixture_identifier)
        except ValueError as exc:
            raise SportyBetFotMobPartialCalendarError(
                "source_fixture_identifier must be canonical decimal"
            ) from exc
        if str(parsed_id) != self.source_fixture_identifier:
            raise SportyBetFotMobPartialCalendarError(
                "source_fixture_identifier must be canonical decimal"
            )
        _hash(self.source_capture_manifest_sha256, "source_capture_manifest_sha256")
        _hash(self.candidate_sha256, "candidate_sha256")
        _hash(self.evidence_sha256, "evidence_sha256")
        home = _text(self.home_team, "home_team")
        away = _text(self.away_team, "away_team")
        _text(self.competition, "competition")
        if home == away:
            raise SportyBetFotMobPartialCalendarError(
                "matched FotMob home and away teams must differ"
            )
        kickoff_text = _canonical_utc(self.kickoff_utc, "kickoff_utc")
        try:
            kickoff = parse_utc_timestamp(kickoff_text, "kickoff_utc")
        except SportyBetLiteCaptureError as exc:  # pragma: no cover
            raise SportyBetFotMobPartialCalendarError(str(exc)) from exc
        if kickoff.second != 0 or kickoff.microsecond != 0:
            raise SportyBetFotMobPartialCalendarError(
                "matched FotMob kickoff must be exactly minute-aligned"
            )
        if type(self.fotmob_year) is not int or isinstance(self.fotmob_year, bool):
            raise SportyBetFotMobPartialCalendarError("fotmob_year must be an exact integer")
        if self.fotmob_year != kickoff.year:
            raise SportyBetFotMobPartialCalendarError(
                "fotmob_year does not match matched FotMob kickoff"
            )

    @classmethod
    def from_reviewed(
        cls,
        value: FotMobReviewedFixtureCatalogInput,
    ) -> "MatchedFotMobPartialCalendarFixture":
        kickoff = value.kickoff.astimezone(dt.timezone.utc)
        return cls(
            source_fixture_identifier=value.source_fixture_identifier,
            source_capture_manifest_sha256=value.source_capture_manifest_sha256,
            candidate_sha256=value.candidate_sha256,
            evidence_sha256=value.evidence_sha256,
            home_team=value.home_team,
            away_team=value.away_team,
            competition=value.competition,
            kickoff_utc=serialize_utc(kickoff),
            fotmob_year=kickoff.year,
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class PartialCalendarDisposition(str, enum.Enum):
    UNIQUE_EXACT_PARTIAL_CALENDAR_MATCH_CANDIDATE_YEAR_UNPROVEN = (
        "UNIQUE_EXACT_PARTIAL_CALENDAR_MATCH_CANDIDATE_YEAR_UNPROVEN"
    )
    NO_EXACT_PARTIAL_CALENDAR_MATCH = "NO_EXACT_PARTIAL_CALENDAR_MATCH"
    AMBIGUOUS_EXACT_PARTIAL_CALENDAR_MATCH = "AMBIGUOUS_EXACT_PARTIAL_CALENDAR_MATCH"


@dataclasses.dataclass(frozen=True)
class SportyBetFotMobPartialCalendarCandidate:
    schema_version: int
    dataset_name: str
    provider: str
    status: str
    source_time_basis_sha256: str
    event_source_evidence_id: str
    event_source_manifest_sha256: str
    event_source_native_inventory_sha256: str
    event_source_raw_sha256: str
    event_candidate_sha256: str
    terms_evidence_id: str
    terms_qualification_sha256: str
    terms_raw_sha256: str
    fotmob_population_sha256: str
    sportybet_event_id: str
    sportybet_sport_id: str
    matching_basis: str
    competition_display: str
    home_display: str
    away_display: str
    kickoff_display: str
    kickoff_day: int
    kickoff_month: int
    kickoff_weekday: str
    kickoff_hour: int
    kickoff_minute: int
    kickoff_timezone: str
    utc_offset_seconds: int
    sportybet_kickoff_year: None
    sportybet_kickoff_utc: None
    sportybet_year_proven: bool
    disposition: PartialCalendarDisposition
    exact_match_count: int
    matched_fixture: MatchedFotMobPartialCalendarFixture | None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetFotMobPartialCalendarError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetFotMobPartialCalendarError("dataset/provider mismatch")
        if self.status != STATUS:
            raise SportyBetFotMobPartialCalendarError("status mismatch")
        _hash(self.source_time_basis_sha256, "source_time_basis_sha256")
        _evidence_id(self.event_source_evidence_id, "event_source_evidence_id")
        _hash(self.event_source_manifest_sha256, "event_source_manifest_sha256")
        _hash(
            self.event_source_native_inventory_sha256,
            "event_source_native_inventory_sha256",
        )
        _hash(self.event_source_raw_sha256, "event_source_raw_sha256")
        _hash(self.event_candidate_sha256, "event_candidate_sha256")
        _evidence_id(self.terms_evidence_id, "terms_evidence_id")
        _hash(self.terms_qualification_sha256, "terms_qualification_sha256")
        _hash(self.terms_raw_sha256, "terms_raw_sha256")
        _hash(self.fotmob_population_sha256, "fotmob_population_sha256")
        _text(self.sportybet_event_id, "sportybet_event_id", maximum=160)
        _text(self.sportybet_sport_id, "sportybet_sport_id", maximum=160)
        competition = _text(self.competition_display, "competition_display")
        home = _text(self.home_display, "home_display")
        away = _text(self.away_display, "away_display")
        _text(self.kickoff_display, "kickoff_display", maximum=64)
        if home == away:
            raise SportyBetFotMobPartialCalendarError(
                "SportyBet home and away display names must differ"
            )
        if self.matching_basis != MATCHING_BASIS:
            raise SportyBetFotMobPartialCalendarError("matching_basis mismatch")
        if self.kickoff_timezone != TIME_ZONE_LABEL:
            raise SportyBetFotMobPartialCalendarError("kickoff_timezone mismatch")
        if (
            type(self.utc_offset_seconds) is not int
            or isinstance(self.utc_offset_seconds, bool)
            or self.utc_offset_seconds != UTC_OFFSET_SECONDS
        ):
            raise SportyBetFotMobPartialCalendarError("utc_offset_seconds mismatch")
        if self.sportybet_kickoff_year is not None or self.sportybet_kickoff_utc is not None:
            raise SportyBetFotMobPartialCalendarError(
                "SportyBet year and UTC instant remain unproven and must be null"
            )
        if self.sportybet_year_proven is not False:
            raise SportyBetFotMobPartialCalendarError(
                "sportybet_year_proven must remain exact False"
            )
        if (
            type(self.kickoff_day) is not int
            or type(self.kickoff_month) is not int
            or type(self.kickoff_hour) is not int
            or type(self.kickoff_minute) is not int
            or type(self.kickoff_weekday) is not str
        ):
            raise SportyBetFotMobPartialCalendarError(
                "SportyBet partial-calendar components have invalid types"
            )
        if self.kickoff_weekday not in _WEEKDAYS:
            raise SportyBetFotMobPartialCalendarError("kickoff_weekday is invalid")
        if type(self.disposition) is not PartialCalendarDisposition:
            raise SportyBetFotMobPartialCalendarError("disposition is invalid")
        if (
            type(self.exact_match_count) is not int
            or isinstance(self.exact_match_count, bool)
            or self.exact_match_count < 0
        ):
            raise SportyBetFotMobPartialCalendarError("exact_match_count is invalid")
        if (
            self.disposition
            is PartialCalendarDisposition.UNIQUE_EXACT_PARTIAL_CALENDAR_MATCH_CANDIDATE_YEAR_UNPROVEN
        ):
            if self.exact_match_count != 1 or not isinstance(
                self.matched_fixture,
                MatchedFotMobPartialCalendarFixture,
            ):
                raise SportyBetFotMobPartialCalendarError(
                    "unique candidate requires exactly one matched FotMob fixture"
                )
            matched = self.matched_fixture
            if (
                matched.home_team != home
                or matched.away_team != away
                or matched.competition != competition
            ):
                raise SportyBetFotMobPartialCalendarError(
                    "matched FotMob fixture text does not equal SportyBet display identity"
                )
            try:
                kickoff = parse_utc_timestamp(matched.kickoff_utc, "matched_fixture.kickoff_utc")
            except SportyBetLiteCaptureError as exc:
                raise SportyBetFotMobPartialCalendarError(str(exc)) from exc
            expected_key = (
                self.kickoff_day,
                self.kickoff_month,
                self.kickoff_weekday,
                self.kickoff_hour,
                self.kickoff_minute,
            )
            if _kickoff_partial_key(kickoff) != expected_key:
                raise SportyBetFotMobPartialCalendarError(
                    "matched FotMob fixture does not equal SportyBet partial calendar identity"
                )
        elif self.disposition is PartialCalendarDisposition.NO_EXACT_PARTIAL_CALENDAR_MATCH:
            if self.exact_match_count != 0 or self.matched_fixture is not None:
                raise SportyBetFotMobPartialCalendarError(
                    "no-match disposition cannot contain a matched fixture"
                )
        else:
            if self.exact_match_count < 2 or self.matched_fixture is not None:
                raise SportyBetFotMobPartialCalendarError(
                    "ambiguous disposition requires multiple matches and no chosen fixture"
                )
        object.__setattr__(self, "competition_display", competition)
        object.__setattr__(self, "home_display", home)
        object.__setattr__(self, "away_display", away)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "status": self.status,
            "source_time_basis_sha256": self.source_time_basis_sha256,
            "event_source_evidence_id": self.event_source_evidence_id,
            "event_source_manifest_sha256": self.event_source_manifest_sha256,
            "event_source_native_inventory_sha256": self.event_source_native_inventory_sha256,
            "event_source_raw_sha256": self.event_source_raw_sha256,
            "event_candidate_sha256": self.event_candidate_sha256,
            "terms_evidence_id": self.terms_evidence_id,
            "terms_qualification_sha256": self.terms_qualification_sha256,
            "terms_raw_sha256": self.terms_raw_sha256,
            "fotmob_population_sha256": self.fotmob_population_sha256,
            "sportybet_event_id": self.sportybet_event_id,
            "sportybet_sport_id": self.sportybet_sport_id,
            "matching_basis": self.matching_basis,
            "competition_display": self.competition_display,
            "home_display": self.home_display,
            "away_display": self.away_display,
            "kickoff_display": self.kickoff_display,
            "kickoff_day": self.kickoff_day,
            "kickoff_month": self.kickoff_month,
            "kickoff_weekday": self.kickoff_weekday,
            "kickoff_hour": self.kickoff_hour,
            "kickoff_minute": self.kickoff_minute,
            "kickoff_timezone": TIME_ZONE_LABEL,
            "utc_offset_seconds": UTC_OFFSET_SECONDS,
            "sportybet_kickoff_year": None,
            "sportybet_kickoff_utc": None,
            "sportybet_year_proven": False,
            "disposition": self.disposition.value,
            "exact_match_count": self.exact_match_count,
            "matched_fixture": (
                None if self.matched_fixture is None else self.matched_fixture.to_dict()
            ),
            "safety": dict(self.safety),
        }


def build_partial_calendar_reconciliation_candidate(
    *,
    time_basis: local_time.SportyBetEventLocalTimeBasis,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> SportyBetFotMobPartialCalendarCandidate:
    rebuilt = _rederive_exact_time_basis(
        supplied=time_basis,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
        terms_qualification=terms_qualification,
        terms_raw_html=terms_raw_html,
    )
    rows = _reviewed_fotmob_rows(fixtures)
    source_key = _sportybet_partial_key(rebuilt)
    matches = tuple(
        item
        for item in rows
        if item.home_team == rebuilt.home_display
        and item.away_team == rebuilt.away_display
        and item.competition == rebuilt.competition_display
        and _kickoff_partial_key(item.kickoff) == source_key
    )
    if len(matches) == 1:
        disposition = (
            PartialCalendarDisposition.UNIQUE_EXACT_PARTIAL_CALENDAR_MATCH_CANDIDATE_YEAR_UNPROVEN
        )
        matched = MatchedFotMobPartialCalendarFixture.from_reviewed(matches[0])
    elif not matches:
        disposition = PartialCalendarDisposition.NO_EXACT_PARTIAL_CALENDAR_MATCH
        matched = None
    else:
        disposition = PartialCalendarDisposition.AMBIGUOUS_EXACT_PARTIAL_CALENDAR_MATCH
        matched = None
    return SportyBetFotMobPartialCalendarCandidate(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        status=STATUS,
        source_time_basis_sha256=local_time.time_basis_sha256(rebuilt),
        event_source_evidence_id=rebuilt.event_source_evidence_id,
        event_source_manifest_sha256=rebuilt.event_source_manifest_sha256,
        event_source_native_inventory_sha256=rebuilt.event_source_native_inventory_sha256,
        event_source_raw_sha256=rebuilt.event_source_raw_sha256,
        event_candidate_sha256=rebuilt.event_candidate_sha256,
        terms_evidence_id=rebuilt.terms_evidence_id,
        terms_qualification_sha256=rebuilt.terms_qualification_sha256,
        terms_raw_sha256=rebuilt.terms_raw_sha256,
        fotmob_population_sha256=fotmob_population_sha256(rows),
        sportybet_event_id=rebuilt.event_id,
        sportybet_sport_id=rebuilt.sport_id,
        matching_basis=MATCHING_BASIS,
        competition_display=rebuilt.competition_display,
        home_display=rebuilt.home_display,
        away_display=rebuilt.away_display,
        kickoff_display=rebuilt.kickoff_display,
        kickoff_day=rebuilt.kickoff_day,
        kickoff_month=rebuilt.kickoff_month,
        kickoff_weekday=rebuilt.kickoff_weekday,
        kickoff_hour=rebuilt.kickoff_hour,
        kickoff_minute=rebuilt.kickoff_minute,
        kickoff_timezone=TIME_ZONE_LABEL,
        utc_offset_seconds=UTC_OFFSET_SECONDS,
        sportybet_kickoff_year=None,
        sportybet_kickoff_utc=None,
        sportybet_year_proven=False,
        disposition=disposition,
        exact_match_count=len(matches),
        matched_fixture=matched,
        safety=_default_safety(),
    )


def canonical_candidate_bytes(value: Any) -> bytes:
    if not isinstance(value, SportyBetFotMobPartialCalendarCandidate):
        raise SportyBetFotMobPartialCalendarError("candidate type mismatch")
    payload = _canonical_mapping_bytes(value.to_dict())
    if len(payload) > MAX_CANONICAL_BYTES:
        raise SportyBetFotMobPartialCalendarError(
            "candidate exceeds reviewed size limit"
        )
    return payload


def candidate_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_candidate_bytes(value)).hexdigest()


__all__ = [
    "DATASET_NAME",
    "MATCHING_BASIS",
    "PartialCalendarDisposition",
    "MatchedFotMobPartialCalendarFixture",
    "SportyBetFotMobPartialCalendarCandidate",
    "SportyBetFotMobPartialCalendarError",
    "build_partial_calendar_reconciliation_candidate",
    "canonical_candidate_bytes",
    "canonical_fotmob_population_bytes",
    "candidate_sha256",
    "fotmob_population_sha256",
]
