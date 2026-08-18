"""Strict SportyBet -> FotMob fixture reconciliation from provider-resolved full UTC.

This boundary consumes PR #162 only after that promotion is revalidated from every
preserved upstream SportyBet, Terms, bridge and Sportradar source. It then compares
against already-reviewed FotMob fixture inputs using exact, case-sensitive home,
away, competition and full UTC kickoff equality.

A unique exact match may authorize only fixture reconciliation. Zero or multiple
matches authorize nothing. No fuzzy aliases, participant reversal, kickoff
rounding/tolerance, market mapping, pricing, selection, booking-code, execution or
BET authority is created here.
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

from domain import sportradar_user_controlled_event_metadata as metadata
from domain import sportybet_event_local_time_basis as local_time
from domain import sportybet_machine_event_header_candidate as header
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_kickoff_identity_promotion as promotion
from domain import sportybet_sportradar_kickoff_identity_promotion_verification as promotion_verify
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    parse_utc_timestamp,
    serialize_utc,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-fotmob-full-utc-reconciliation-v1"
PROVIDER = "SportyBet"
STATUS = "FULL_UTC_FIXTURE_RECONCILIATION_RESULT"
MATCHING_BASIS = (
    "EXACT_HOME_AWAY_COMPETITION_FULL_UTC_NO_FUZZY_NO_ALIAS_"
    "NO_REVERSAL_NO_ROUNDING_NO_TOLERANCE"
)
TIME_ZONE_LABEL = "GMT"
UTC_OFFSET_SECONDS = 0
MAX_CANONICAL_BYTES = 512 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_LEGACY_EVENT_ID_RE = re.compile(r"^sr:match:[1-9][0-9]*$", flags=re.ASCII)
_SPORT_ID_RE = re.compile(r"^sr:sport:[1-9][0-9]*$", flags=re.ASCII)
_CURRENT_EVENT_ID_RE = re.compile(r"^sr:sport_event:[1-9][0-9]*$", flags=re.ASCII)
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
        "sportradar_metadata_resolution_authorized",
        "sportybet_execution_authorized",
    }
)


class SportyBetFotMobFullUtcReconciliationError(ValueError):
    """Raised when full-UTC fixture reconciliation fails closed."""


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetFotMobFullUtcReconciliationError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _evidence_id(value: Any, label: str) -> str:
    if type(value) is not str or _EVIDENCE_ID_RE.fullmatch(value) is None:
        raise SportyBetFotMobFullUtcReconciliationError(f"{label} is invalid")
    return value


def _text(value: Any, label: str, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise SportyBetFotMobFullUtcReconciliationError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def _provider_id(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise SportyBetFotMobFullUtcReconciliationError(f"{label} is invalid")
    return value


def _canonical_utc(value: Any, label: str) -> str:
    if type(value) is not str:
        raise SportyBetFotMobFullUtcReconciliationError(f"{label} must be a string")
    try:
        parsed = parse_utc_timestamp(value, label)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetFotMobFullUtcReconciliationError(str(exc)) from exc
    if serialize_utc(parsed) != value:
        raise SportyBetFotMobFullUtcReconciliationError(
            f"{label} must use canonical UTC serialization"
        )
    return value


def _default_safety(*, fixture_authorized: bool) -> dict[str, bool]:
    return {
        key: (fixture_authorized if key == "fixture_reconciliation_authorized" else False)
        for key in sorted(_SAFETY_KEYS)
    }


def _validate_safety(value: Any, *, fixture_authorized: bool) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetFotMobFullUtcReconciliationError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key in sorted(_SAFETY_KEYS):
        item = value[key]
        expected = fixture_authorized if key == "fixture_reconciliation_authorized" else False
        if type(item) is not bool or item is not expected:
            raise SportyBetFotMobFullUtcReconciliationError(
                f"safety[{key!r}] does not match reviewed authority policy"
            )
        detached[key] = expected
    return types.MappingProxyType(detached)


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
        raise SportyBetFotMobFullUtcReconciliationError(
            "canonical serialization failed"
        ) from exc


def _reviewed_fotmob_rows(
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> tuple[FotMobReviewedFixtureCatalogInput, ...]:
    try:
        rows = tuple(fixtures)
    except TypeError as exc:
        raise SportyBetFotMobFullUtcReconciliationError(
            "fixtures must be an iterable of reviewed FotMob inputs"
        ) from exc
    if not rows:
        raise SportyBetFotMobFullUtcReconciliationError(
            "at least one reviewed FotMob fixture is required"
        )
    if any(type(item) is not FotMobReviewedFixtureCatalogInput for item in rows):
        raise SportyBetFotMobFullUtcReconciliationError(
            "fixture population contains a non-reviewed FotMob catalog input"
        )
    source_ids = [item.source_fixture_identifier for item in rows]
    if len(source_ids) != len(set(source_ids)):
        raise SportyBetFotMobFullUtcReconciliationError(
            "duplicate FotMob source_fixture_identifier in reconciliation population"
        )
    try:
        return tuple(sorted(rows, key=lambda item: int(item.source_fixture_identifier)))
    except ValueError as exc:  # reviewed input already enforces canonical decimal IDs
        raise SportyBetFotMobFullUtcReconciliationError(
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


def _rederive_exact_promotion(
    *,
    supplied: Any,
    event_time_basis: local_time.SportyBetEventLocalTimeBasis,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportradar_evidence: metadata.SportradarUserControlledEventMetadataEvidence,
    sportradar_raw_response: bytes,
) -> promotion.SportyBetSportradarKickoffIdentityPromotion:
    try:
        rebuilt = promotion_verify.revalidate_kickoff_identity_promotion(
            supplied,
            event_time_basis=event_time_basis,
            event_manifest=event_manifest,
            event_inventory=event_inventory,
            event_raw_html=event_raw_html,
            terms_qualification=terms_qualification,
            terms_raw_html=terms_raw_html,
            event_bridge=event_bridge,
            sportradar_evidence=sportradar_evidence,
            sportradar_raw_response=sportradar_raw_response,
        )
    except promotion.SportyBetSportradarKickoffIdentityPromotionError as exc:
        raise SportyBetFotMobFullUtcReconciliationError(str(exc)) from exc
    if (
        rebuilt.sportybet_year_promoted is not True
        or rebuilt.sportybet_kickoff_utc_promoted is not True
        or rebuilt.provider_event_kickoff_identity_promoted is not True
        or rebuilt.fixture_identity_promoted is not False
        or rebuilt.fotmob_fixture_reconciliation_authorized is not False
        or rebuilt.provider_quote_at is not None
        or rebuilt.provider_snapshot_id is not None
    ):
        raise SportyBetFotMobFullUtcReconciliationError(
            "PR #162 does not carry the reviewed provider-kickoff-only promotion state"
        )
    return rebuilt


@dataclasses.dataclass(frozen=True)
class MatchedFotMobFullUtcFixture:
    source_fixture_identifier: str
    source_capture_manifest_sha256: str
    candidate_sha256: str
    evidence_sha256: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: str

    def __post_init__(self) -> None:
        _text(self.source_fixture_identifier, "source_fixture_identifier", maximum=64)
        try:
            parsed = int(self.source_fixture_identifier)
        except ValueError as exc:
            raise SportyBetFotMobFullUtcReconciliationError(
                "source_fixture_identifier must be canonical decimal"
            ) from exc
        if str(parsed) != self.source_fixture_identifier:
            raise SportyBetFotMobFullUtcReconciliationError(
                "source_fixture_identifier must be canonical decimal"
            )
        _hash(self.source_capture_manifest_sha256, "source_capture_manifest_sha256")
        _hash(self.candidate_sha256, "candidate_sha256")
        _hash(self.evidence_sha256, "evidence_sha256")
        home = _text(self.home_team, "home_team")
        away = _text(self.away_team, "away_team")
        _text(self.competition, "competition")
        if home == away:
            raise SportyBetFotMobFullUtcReconciliationError(
                "matched FotMob home and away teams must differ"
            )
        _canonical_utc(self.kickoff_utc, "kickoff_utc")

    @classmethod
    def from_reviewed(
        cls,
        value: FotMobReviewedFixtureCatalogInput,
    ) -> "MatchedFotMobFullUtcFixture":
        return cls(
            source_fixture_identifier=value.source_fixture_identifier,
            source_capture_manifest_sha256=value.source_capture_manifest_sha256,
            candidate_sha256=value.candidate_sha256,
            evidence_sha256=value.evidence_sha256,
            home_team=value.home_team,
            away_team=value.away_team,
            competition=value.competition,
            kickoff_utc=serialize_utc(value.kickoff.astimezone(dt.timezone.utc)),
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class FullUtcReconciliationDisposition(str, enum.Enum):
    UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED = "UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED"
    NO_EXACT_FULL_UTC_MATCH = "NO_EXACT_FULL_UTC_MATCH"
    AMBIGUOUS_EXACT_FULL_UTC_MATCH = "AMBIGUOUS_EXACT_FULL_UTC_MATCH"


@dataclasses.dataclass(frozen=True)
class SportyBetFotMobFullUtcReconciliation:
    schema_version: int
    dataset_name: str
    provider: str
    status: str
    matching_basis: str
    source_promotion_sha256: str
    source_time_basis_sha256: str
    source_bridge_sha256: str
    source_metadata_evidence_id: str
    source_metadata_evidence_sha256: str
    source_event_evidence_id: str
    source_event_manifest_sha256: str
    source_native_inventory_sha256: str
    source_event_raw_sha256: str
    event_source_url: str
    sportybet_event_id: str
    sportybet_sport_id: str
    sportradar_event_id: str
    competition_display: str
    home_display: str
    away_display: str
    kickoff_display: str
    kickoff_day: int
    kickoff_month: int
    kickoff_weekday: str
    kickoff_hour: int
    kickoff_minute: int
    sportybet_kickoff_year: int
    sportybet_kickoff_timezone: str
    sportybet_utc_offset_seconds: int
    sportybet_kickoff_utc: dt.datetime
    provider_timestamp_subminute_precision_preserved: bool
    fotmob_population_sha256: str
    disposition: FullUtcReconciliationDisposition
    exact_match_count: int
    matched_fixture: MatchedFotMobFullUtcFixture | None
    fixture_reconciliation_authorized: bool
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetFotMobFullUtcReconciliationError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetFotMobFullUtcReconciliationError("dataset/provider mismatch")
        if self.status != STATUS or self.matching_basis != MATCHING_BASIS:
            raise SportyBetFotMobFullUtcReconciliationError("status/matching_basis mismatch")
        _hash(self.source_promotion_sha256, "source_promotion_sha256")
        _hash(self.source_time_basis_sha256, "source_time_basis_sha256")
        _hash(self.source_bridge_sha256, "source_bridge_sha256")
        _evidence_id(self.source_metadata_evidence_id, "source_metadata_evidence_id")
        _hash(self.source_metadata_evidence_sha256, "source_metadata_evidence_sha256")
        _evidence_id(self.source_event_evidence_id, "source_event_evidence_id")
        _hash(self.source_event_manifest_sha256, "source_event_manifest_sha256")
        _hash(self.source_native_inventory_sha256, "source_native_inventory_sha256")
        _hash(self.source_event_raw_sha256, "source_event_raw_sha256")
        _hash(self.fotmob_population_sha256, "fotmob_population_sha256")
        _provider_id(self.sportybet_event_id, "sportybet_event_id", _LEGACY_EVENT_ID_RE)
        _provider_id(self.sportybet_sport_id, "sportybet_sport_id", _SPORT_ID_RE)
        _provider_id(self.sportradar_event_id, "sportradar_event_id", _CURRENT_EVENT_ID_RE)
        try:
            kind, event_id, sport_id, _, _ = manual.validate_source_url(self.event_source_url)
        except manual.SportyBetUserEvidenceError as exc:
            raise SportyBetFotMobFullUtcReconciliationError(str(exc)) from exc
        if (
            kind is not SportyBetLiteRequestKind.EVENT_DETAIL
            or event_id != self.sportybet_event_id
            or sport_id != self.sportybet_sport_id
        ):
            raise SportyBetFotMobFullUtcReconciliationError(
                "event source URL does not match SportyBet event/sport identity"
            )
        try:
            checked_header = header.ExtractedVisibleEventHeader(
                competition_display=self.competition_display,
                kickoff_display=self.kickoff_display,
                home_display=self.home_display,
                away_display=self.away_display,
                kickoff_day=self.kickoff_day,
                kickoff_month=self.kickoff_month,
                kickoff_weekday=self.kickoff_weekday,
                kickoff_hour=self.kickoff_hour,
                kickoff_minute=self.kickoff_minute,
            )
        except header.SportyBetMachineEventHeaderError as exc:
            raise SportyBetFotMobFullUtcReconciliationError(str(exc)) from exc
        if (
            type(self.sportybet_kickoff_year) is not int
            or isinstance(self.sportybet_kickoff_year, bool)
        ):
            raise SportyBetFotMobFullUtcReconciliationError(
                "sportybet_kickoff_year must be an exact integer"
            )
        if self.sportybet_kickoff_timezone != TIME_ZONE_LABEL:
            raise SportyBetFotMobFullUtcReconciliationError(
                "sportybet_kickoff_timezone mismatch"
            )
        if (
            type(self.sportybet_utc_offset_seconds) is not int
            or isinstance(self.sportybet_utc_offset_seconds, bool)
            or self.sportybet_utc_offset_seconds != UTC_OFFSET_SECONDS
        ):
            raise SportyBetFotMobFullUtcReconciliationError(
                "sportybet_utc_offset_seconds mismatch"
            )
        kickoff = self.sportybet_kickoff_utc
        if (
            not isinstance(kickoff, dt.datetime)
            or kickoff.tzinfo is None
            or kickoff.utcoffset() is None
        ):
            raise SportyBetFotMobFullUtcReconciliationError(
                "sportybet_kickoff_utc must be timezone-aware"
            )
        kickoff = kickoff.astimezone(dt.timezone.utc)
        if self.sportybet_kickoff_year != kickoff.year:
            raise SportyBetFotMobFullUtcReconciliationError(
                "sportybet_kickoff_year does not match full UTC kickoff"
            )
        display_calendar = (
            checked_header.kickoff_day,
            checked_header.kickoff_month,
            checked_header.kickoff_weekday,
            checked_header.kickoff_hour,
            checked_header.kickoff_minute,
        )
        kickoff_calendar = (
            kickoff.day,
            kickoff.month,
            kickoff.strftime("%A"),
            kickoff.hour,
            kickoff.minute,
        )
        if display_calendar != kickoff_calendar:
            raise SportyBetFotMobFullUtcReconciliationError(
                "full UTC kickoff does not match SportyBet GMT display calendar"
            )
        if self.provider_timestamp_subminute_precision_preserved is not True:
            raise SportyBetFotMobFullUtcReconciliationError(
                "provider timestamp subminute precision must remain preserved"
            )
        if type(self.disposition) is not FullUtcReconciliationDisposition:
            raise SportyBetFotMobFullUtcReconciliationError("disposition is invalid")
        if (
            type(self.exact_match_count) is not int
            or isinstance(self.exact_match_count, bool)
            or self.exact_match_count < 0
        ):
            raise SportyBetFotMobFullUtcReconciliationError("exact_match_count is invalid")
        if type(self.fixture_reconciliation_authorized) is not bool:
            raise SportyBetFotMobFullUtcReconciliationError(
                "fixture_reconciliation_authorized must be exact bool"
            )
        if (
            self.disposition
            is FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        ):
            if (
                self.exact_match_count != 1
                or not isinstance(self.matched_fixture, MatchedFotMobFullUtcFixture)
                or self.fixture_reconciliation_authorized is not True
            ):
                raise SportyBetFotMobFullUtcReconciliationError(
                    "unique exact match must contain one fixture and authorize reconciliation"
                )
            matched = self.matched_fixture
            if (
                matched.home_team != checked_header.home_display
                or matched.away_team != checked_header.away_display
                or matched.competition != checked_header.competition_display
                or _canonical_utc(matched.kickoff_utc, "matched_fixture.kickoff_utc")
                != serialize_utc(kickoff)
            ):
                raise SportyBetFotMobFullUtcReconciliationError(
                    "matched FotMob fixture does not exactly equal SportyBet full-UTC identity"
                )
        elif self.disposition is FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH:
            if (
                self.exact_match_count != 0
                or self.matched_fixture is not None
                or self.fixture_reconciliation_authorized is not False
            ):
                raise SportyBetFotMobFullUtcReconciliationError(
                    "no-match disposition cannot authorize or contain a fixture"
                )
        else:
            if (
                self.exact_match_count < 2
                or self.matched_fixture is not None
                or self.fixture_reconciliation_authorized is not False
            ):
                raise SportyBetFotMobFullUtcReconciliationError(
                    "ambiguous disposition requires multiple matches and no authority"
                )
        object.__setattr__(self, "competition_display", checked_header.competition_display)
        object.__setattr__(self, "home_display", checked_header.home_display)
        object.__setattr__(self, "away_display", checked_header.away_display)
        object.__setattr__(self, "sportybet_kickoff_utc", kickoff)
        object.__setattr__(
            self,
            "safety",
            _validate_safety(
                self.safety,
                fixture_authorized=self.fixture_reconciliation_authorized,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "status": self.status,
            "matching_basis": self.matching_basis,
            "source_promotion_sha256": self.source_promotion_sha256,
            "source_time_basis_sha256": self.source_time_basis_sha256,
            "source_bridge_sha256": self.source_bridge_sha256,
            "source_metadata_evidence_id": self.source_metadata_evidence_id,
            "source_metadata_evidence_sha256": self.source_metadata_evidence_sha256,
            "source_event_evidence_id": self.source_event_evidence_id,
            "source_event_manifest_sha256": self.source_event_manifest_sha256,
            "source_native_inventory_sha256": self.source_native_inventory_sha256,
            "source_event_raw_sha256": self.source_event_raw_sha256,
            "event_source_url": self.event_source_url,
            "sportybet_event_id": self.sportybet_event_id,
            "sportybet_sport_id": self.sportybet_sport_id,
            "sportradar_event_id": self.sportradar_event_id,
            "competition_display": self.competition_display,
            "home_display": self.home_display,
            "away_display": self.away_display,
            "kickoff_display": self.kickoff_display,
            "kickoff_day": self.kickoff_day,
            "kickoff_month": self.kickoff_month,
            "kickoff_weekday": self.kickoff_weekday,
            "kickoff_hour": self.kickoff_hour,
            "kickoff_minute": self.kickoff_minute,
            "sportybet_kickoff_year": self.sportybet_kickoff_year,
            "sportybet_kickoff_timezone": self.sportybet_kickoff_timezone,
            "sportybet_utc_offset_seconds": self.sportybet_utc_offset_seconds,
            "sportybet_kickoff_utc": serialize_utc(self.sportybet_kickoff_utc),
            "provider_timestamp_subminute_precision_preserved": (
                self.provider_timestamp_subminute_precision_preserved
            ),
            "fotmob_population_sha256": self.fotmob_population_sha256,
            "disposition": self.disposition.value,
            "exact_match_count": self.exact_match_count,
            "matched_fixture": (
                None if self.matched_fixture is None else self.matched_fixture.to_dict()
            ),
            "fixture_reconciliation_authorized": self.fixture_reconciliation_authorized,
            "safety": dict(self.safety),
        }


def build_full_utc_reconciliation(
    *,
    kickoff_promotion: promotion.SportyBetSportradarKickoffIdentityPromotion,
    event_time_basis: local_time.SportyBetEventLocalTimeBasis,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportradar_evidence: metadata.SportradarUserControlledEventMetadataEvidence,
    sportradar_raw_response: bytes,
    fixtures: Iterable[FotMobReviewedFixtureCatalogInput],
) -> SportyBetFotMobFullUtcReconciliation:
    rebuilt = _rederive_exact_promotion(
        supplied=kickoff_promotion,
        event_time_basis=event_time_basis,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
        terms_qualification=terms_qualification,
        terms_raw_html=terms_raw_html,
        event_bridge=event_bridge,
        sportradar_evidence=sportradar_evidence,
        sportradar_raw_response=sportradar_raw_response,
    )
    rows = _reviewed_fotmob_rows(fixtures)
    source_kickoff = rebuilt.sportybet_kickoff_utc.astimezone(dt.timezone.utc)
    matches = tuple(
        item
        for item in rows
        if item.home_team == rebuilt.home_display
        and item.away_team == rebuilt.away_display
        and item.competition == rebuilt.competition_display
        and item.kickoff.astimezone(dt.timezone.utc) == source_kickoff
    )
    if len(matches) == 1:
        disposition = FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        matched = MatchedFotMobFullUtcFixture.from_reviewed(matches[0])
        fixture_authorized = True
    elif not matches:
        disposition = FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH
        matched = None
        fixture_authorized = False
    else:
        disposition = FullUtcReconciliationDisposition.AMBIGUOUS_EXACT_FULL_UTC_MATCH
        matched = None
        fixture_authorized = False
    return SportyBetFotMobFullUtcReconciliation(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        status=STATUS,
        matching_basis=MATCHING_BASIS,
        source_promotion_sha256=promotion.promotion_sha256(rebuilt),
        source_time_basis_sha256=rebuilt.source_time_basis_sha256,
        source_bridge_sha256=rebuilt.source_bridge_sha256,
        source_metadata_evidence_id=rebuilt.source_metadata_evidence_id,
        source_metadata_evidence_sha256=rebuilt.source_metadata_evidence_sha256,
        source_event_evidence_id=rebuilt.source_event_evidence_id,
        source_event_manifest_sha256=rebuilt.source_event_manifest_sha256,
        source_native_inventory_sha256=rebuilt.source_native_inventory_sha256,
        source_event_raw_sha256=rebuilt.source_event_raw_sha256,
        event_source_url=rebuilt.event_source_url,
        sportybet_event_id=rebuilt.sportybet_event_id,
        sportybet_sport_id=rebuilt.sportybet_sport_id,
        sportradar_event_id=rebuilt.sportradar_event_id,
        competition_display=rebuilt.competition_display,
        home_display=rebuilt.home_display,
        away_display=rebuilt.away_display,
        kickoff_display=rebuilt.kickoff_display,
        kickoff_day=rebuilt.kickoff_day,
        kickoff_month=rebuilt.kickoff_month,
        kickoff_weekday=rebuilt.kickoff_weekday,
        kickoff_hour=rebuilt.kickoff_hour,
        kickoff_minute=rebuilt.kickoff_minute,
        sportybet_kickoff_year=rebuilt.sportybet_kickoff_year,
        sportybet_kickoff_timezone=rebuilt.sportybet_kickoff_timezone,
        sportybet_utc_offset_seconds=rebuilt.sportybet_utc_offset_seconds,
        sportybet_kickoff_utc=source_kickoff,
        provider_timestamp_subminute_precision_preserved=(
            rebuilt.provider_timestamp_subminute_precision_preserved
        ),
        fotmob_population_sha256=fotmob_population_sha256(rows),
        disposition=disposition,
        exact_match_count=len(matches),
        matched_fixture=matched,
        fixture_reconciliation_authorized=fixture_authorized,
        safety=_default_safety(fixture_authorized=fixture_authorized),
    )


def canonical_reconciliation_bytes(value: Any) -> bytes:
    if not isinstance(value, SportyBetFotMobFullUtcReconciliation):
        raise SportyBetFotMobFullUtcReconciliationError("reconciliation type mismatch")
    try:
        payload = (
            json.dumps(
                value.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetFotMobFullUtcReconciliationError(
            "reconciliation canonical serialization failed"
        ) from exc
    if len(payload) > MAX_CANONICAL_BYTES:
        raise SportyBetFotMobFullUtcReconciliationError(
            "reconciliation artifact exceeds reviewed size limit"
        )
    return payload


def reconciliation_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_reconciliation_bytes(value)).hexdigest()


__all__ = [
    "DATASET_NAME",
    "MATCHING_BASIS",
    "STATUS",
    "FullUtcReconciliationDisposition",
    "MatchedFotMobFullUtcFixture",
    "SportyBetFotMobFullUtcReconciliation",
    "SportyBetFotMobFullUtcReconciliationError",
    "build_full_utc_reconciliation",
    "canonical_fotmob_population_bytes",
    "canonical_reconciliation_bytes",
    "fotmob_population_sha256",
    "reconciliation_sha256",
]
