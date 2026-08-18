"""Promote a SportyBet event's missing year/full UTC from confirmed Sportradar metadata.

This boundary combines three exact, independently revalidated sources:
- PR #158 SportyBet event-local GMT qualification;
- PR #160 SportyBet -> Sportradar event-ID bridge;
- PR #161 user-controlled official Sportradar event metadata.

Promotion is allowed only when the official Sportradar start time and date are both
explicitly confirmed, the event has not been replaced, and the normalized UTC
day/month/weekday/hour/minute exactly equal SportyBet's visible GMT partial
calendar. The provider timestamp is preserved exactly; seconds/microseconds are
never rounded or invented.

No FotMob fixture is consulted. Current-calendar inference is forbidden. This
boundary does not authorize FotMob reconciliation, pricing, value, selection,
slip/ACCA construction, booking-code generation, execution, or BET.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain import sportradar_user_controlled_event_metadata as metadata
from domain import sportybet_event_local_time_basis as local_time
from domain import sportybet_machine_event_header_candidate as header
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_event_identity_verification as bridge_verify
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.sportybet_lite_source_capture import SportyBetLiteRequestKind, serialize_utc, sha256_bytes

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-sportradar-kickoff-identity-promotion-v1"
PROVIDER = "SportyBet"
STATUS = "PROMOTED_CONFIRMED_SPORTRADAR_KICKOFF_YEAR_AND_UTC"
PROMOTION_AUTHORITY = "EXACT_REDERIVED_PR158_PR160_PR161_CONFIRMED_SPORTRADAR_TIMESTAMP"
CONFIRMATION_STATUS = "START_TIME_AND_DATE_CONFIRMED_TRUE"
CALENDAR_MATCH_STATUS = "EXACT_GMT_DAY_MONTH_WEEKDAY_HOUR_MINUTE"
REPLACEMENT_STATUS = "SOURCE_EVENT_NOT_REPLACED"
TIME_ZONE_LABEL = "GMT"
UTC_OFFSET_SECONDS = 0
MAX_CANONICAL_BYTES = 256 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_LEGACY_EVENT_ID_RE = re.compile(r"^sr:match:[1-9][0-9]*$", flags=re.ASCII)
_CURRENT_EVENT_ID_RE = re.compile(r"^sr:sport_event:[1-9][0-9]*$", flags=re.ASCII)
_COMPETITION_ID_RE = re.compile(r"^sr:competition:[1-9][0-9]*$", flags=re.ASCII)
_COMPETITOR_ID_RE = re.compile(r"^sr:competitor:[1-9][0-9]*$", flags=re.ASCII)
_SAFETY_KEYS = frozenset({
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
})


class SportyBetSportradarKickoffIdentityPromotionError(ValueError):
    """Raised when the kickoff year/full-UTC promotion fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetSportradarKickoffIdentityPromotionError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _evidence_id(value: Any, label: str) -> str:
    if type(value) is not str or _EVIDENCE_ID_RE.fullmatch(value) is None:
        raise SportyBetSportradarKickoffIdentityPromotionError(f"{label} is invalid")
    return value


def _provider_id(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise SportyBetSportradarKickoffIdentityPromotionError(f"{label} is invalid")
    return value


def _exact_text(value: Any, label: str, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise SportyBetSportradarKickoffIdentityPromotionError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def _parse_exact_provider_timestamp(value: Any) -> tuple[str, dt.datetime, str]:
    exact = _exact_text(value, "sportradar_start_time", maximum=80)
    candidate = exact[:-1] + "+00:00" if exact.endswith("Z") else exact
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "sportradar_start_time must be timezone-aware ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "sportradar_start_time must contain an explicit UTC offset"
        )
    normalized = parsed.astimezone(dt.timezone.utc)
    normalized_text = normalized.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    return exact, normalized, normalized_text


def _revalidate_time_basis(
    value: Any,
    *,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
) -> local_time.SportyBetEventLocalTimeBasis:
    if not isinstance(value, local_time.SportyBetEventLocalTimeBasis):
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "event-local time-basis type mismatch"
        )
    try:
        rebuilt = local_time.build_event_local_time_basis(
            event_manifest=event_manifest,
            event_inventory=event_inventory,
            event_raw_html=event_raw_html,
            terms_qualification=terms_qualification,
            terms_raw_html=terms_raw_html,
        )
        supplied_bytes = local_time.canonical_time_basis_bytes(value)
        rebuilt_bytes = local_time.canonical_time_basis_bytes(rebuilt)
    except local_time.SportyBetEventLocalTimeBasisError as exc:
        raise SportyBetSportradarKickoffIdentityPromotionError(str(exc)) from exc
    if supplied_bytes != rebuilt_bytes:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "event-local time basis is not the exact deterministic derivative of preserved sources"
        )
    if (
        rebuilt.specific_event_time_basis_qualified is not True
        or rebuilt.kickoff_timezone != TIME_ZONE_LABEL
        or rebuilt.utc_offset_seconds != UTC_OFFSET_SECONDS
        or rebuilt.kickoff_year is not None
        or rebuilt.kickoff_utc is not None
    ):
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "event-local time basis is not the reviewed GMT/year-unknown boundary"
        )
    return rebuilt


def _revalidate_bridge(
    value: Any,
    *,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
) -> bridge.SportyBetSportradarEventIdentityBridge:
    try:
        return bridge_verify.revalidate_sportradar_event_identity_bridge(
            value,
            manifest=event_manifest,
            inventory=event_inventory,
            raw_html=event_raw_html,
        )
    except bridge.SportyBetSportradarEventIdentityError as exc:
        raise SportyBetSportradarKickoffIdentityPromotionError(str(exc)) from exc


def _revalidate_metadata(
    value: Any,
    raw_response: bytes,
    *,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
) -> metadata.SportradarUserControlledEventMetadataEvidence:
    try:
        return metadata.revalidate_event_metadata_evidence(
            value,
            raw_response,
            event_bridge=event_bridge,
            sportybet_manifest=event_manifest,
            sportybet_inventory=event_inventory,
            sportybet_raw_html=event_raw_html,
        )
    except metadata.SportradarUserControlledEventMetadataError as exc:
        raise SportyBetSportradarKickoffIdentityPromotionError(str(exc)) from exc


def _calendar_tuple(
    value: local_time.SportyBetEventLocalTimeBasis,
) -> tuple[int, int, str, int, int]:
    return (
        value.kickoff_day,
        value.kickoff_month,
        value.kickoff_weekday,
        value.kickoff_hour,
        value.kickoff_minute,
    )


def _utc_calendar_tuple(value: dt.datetime) -> tuple[int, int, str, int, int]:
    return (
        value.day,
        value.month,
        value.strftime("%A"),
        value.hour,
        value.minute,
    )


@dataclasses.dataclass(frozen=True)
class SportyBetSportradarKickoffIdentityPromotion:
    schema_version: int
    dataset_name: str
    provider: str
    status: str
    promotion_authority: str
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
    sportradar_start_time: str
    sportradar_start_time_utc_normalized: str
    sportradar_start_time_confirmed: bool
    sportradar_date_confirmed: bool
    sportradar_replaced_by: None
    sportradar_competition_id: str
    sportradar_competition_name: str
    sportradar_home_competitor_id: str
    sportradar_home_competitor_name: str
    sportradar_away_competitor_id: str
    sportradar_away_competitor_name: str
    confirmation_status: str
    replacement_status: str
    partial_calendar_match_status: str
    sportybet_kickoff_year: int
    sportybet_kickoff_timezone: str
    sportybet_utc_offset_seconds: int
    sportybet_kickoff_utc: dt.datetime
    provider_timestamp_subminute_precision_preserved: bool
    sportybet_year_promoted: bool
    sportybet_kickoff_utc_promoted: bool
    provider_event_kickoff_identity_promoted: bool
    fixture_identity_promoted: bool
    fotmob_fixture_reconciliation_authorized: bool
    provider_quote_at: None
    provider_snapshot_id: None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetSportradarKickoffIdentityPromotionError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetSportradarKickoffIdentityPromotionError("dataset/provider mismatch")
        if self.status != STATUS or self.promotion_authority != PROMOTION_AUTHORITY:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "status/promotion authority mismatch"
            )
        _hash(self.source_time_basis_sha256, "source_time_basis_sha256")
        _hash(self.source_bridge_sha256, "source_bridge_sha256")
        _evidence_id(self.source_metadata_evidence_id, "source_metadata_evidence_id")
        _hash(self.source_metadata_evidence_sha256, "source_metadata_evidence_sha256")
        _evidence_id(self.source_event_evidence_id, "source_event_evidence_id")
        _hash(self.source_event_manifest_sha256, "source_event_manifest_sha256")
        _hash(self.source_native_inventory_sha256, "source_native_inventory_sha256")
        _hash(self.source_event_raw_sha256, "source_event_raw_sha256")
        _provider_id(self.sportybet_event_id, "sportybet_event_id", _LEGACY_EVENT_ID_RE)
        _provider_id(self.sportradar_event_id, "sportradar_event_id", _CURRENT_EVENT_ID_RE)
        try:
            kind, source_event_id, source_sport_id, _market_group, _target = manual.validate_source_url(
                self.event_source_url
            )
        except manual.SportyBetUserEvidenceError as exc:
            raise SportyBetSportradarKickoffIdentityPromotionError(str(exc)) from exc
        if (
            kind is not SportyBetLiteRequestKind.EVENT_DETAIL
            or source_event_id != self.sportybet_event_id
            or source_sport_id != self.sportybet_sport_id
        ):
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "event source URL does not match promoted provider event/sport identity"
            )
        if self.sportybet_sport_id != bridge.SOCCER_SPORT_ID:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "sportybet_sport_id must be exact soccer sr:sport:1"
            )
        if self.sportybet_event_id.removeprefix("sr:match:") != self.sportradar_event_id.removeprefix(
            "sr:sport_event:"
        ):
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "legacy/current event IDs do not preserve the same numeric payload"
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
            raise SportyBetSportradarKickoffIdentityPromotionError(str(exc)) from exc
        exact_start, kickoff_utc, normalized_text = _parse_exact_provider_timestamp(
            self.sportradar_start_time
        )
        if self.sportradar_start_time_utc_normalized != normalized_text:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "normalized Sportradar start time does not match exact provider timestamp"
            )
        if self.sportradar_start_time_confirmed is not True:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "sportradar_start_time_confirmed must be exact True"
            )
        if self.sportradar_date_confirmed is not True:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "sportradar_date_confirmed must be exact True"
            )
        if self.sportradar_replaced_by is not None:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "replaced events cannot promote SportyBet kickoff identity"
            )
        _provider_id(
            self.sportradar_competition_id,
            "sportradar_competition_id",
            _COMPETITION_ID_RE,
        )
        _provider_id(
            self.sportradar_home_competitor_id,
            "sportradar_home_competitor_id",
            _COMPETITOR_ID_RE,
        )
        _provider_id(
            self.sportradar_away_competitor_id,
            "sportradar_away_competitor_id",
            _COMPETITOR_ID_RE,
        )
        if self.sportradar_home_competitor_id == self.sportradar_away_competitor_id:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "Sportradar home/away competitor IDs must be distinct"
            )
        for label, value in (
            ("sportradar_competition_name", self.sportradar_competition_name),
            ("sportradar_home_competitor_name", self.sportradar_home_competitor_name),
            ("sportradar_away_competitor_name", self.sportradar_away_competitor_name),
        ):
            _exact_text(value, label)
        if self.confirmation_status != CONFIRMATION_STATUS:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "confirmation_status mismatch"
            )
        if self.replacement_status != REPLACEMENT_STATUS:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "replacement_status mismatch"
            )
        if self.partial_calendar_match_status != CALENDAR_MATCH_STATUS:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "partial_calendar_match_status mismatch"
            )
        display_calendar = (
            checked_header.kickoff_day,
            checked_header.kickoff_month,
            checked_header.kickoff_weekday,
            checked_header.kickoff_hour,
            checked_header.kickoff_minute,
        )
        if display_calendar != _utc_calendar_tuple(kickoff_utc):
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "confirmed Sportradar UTC timestamp does not exactly match SportyBet GMT partial calendar"
            )
        if (
            type(self.sportybet_kickoff_year) is not int
            or isinstance(self.sportybet_kickoff_year, bool)
            or self.sportybet_kickoff_year != kickoff_utc.year
        ):
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "sportybet_kickoff_year must equal the confirmed provider UTC year"
            )
        if self.sportybet_kickoff_timezone != TIME_ZONE_LABEL:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "sportybet_kickoff_timezone mismatch"
            )
        if (
            type(self.sportybet_utc_offset_seconds) is not int
            or isinstance(self.sportybet_utc_offset_seconds, bool)
            or self.sportybet_utc_offset_seconds != UTC_OFFSET_SECONDS
        ):
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "sportybet_utc_offset_seconds mismatch"
            )
        supplied_kickoff = self.sportybet_kickoff_utc
        if (
            not isinstance(supplied_kickoff, dt.datetime)
            or supplied_kickoff.tzinfo is None
            or supplied_kickoff.utcoffset() is None
            or supplied_kickoff.astimezone(dt.timezone.utc) != kickoff_utc
        ):
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "sportybet_kickoff_utc must equal the exact confirmed provider instant"
            )
        if self.provider_timestamp_subminute_precision_preserved is not True:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "provider timestamp subminute precision must be preserved"
            )
        for field_name in (
            "sportybet_year_promoted",
            "sportybet_kickoff_utc_promoted",
            "provider_event_kickoff_identity_promoted",
        ):
            if getattr(self, field_name) is not True:
                raise SportyBetSportradarKickoffIdentityPromotionError(
                    f"{field_name} must be exact True"
                )
        if self.fixture_identity_promoted is not False:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "fixture_identity_promoted must remain exact False"
            )
        if self.fotmob_fixture_reconciliation_authorized is not False:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "FotMob fixture reconciliation must remain exact False"
            )
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise SportyBetSportradarKickoffIdentityPromotionError(
                "provider quote/snapshot identity remains unproven"
            )
        object.__setattr__(self, "competition_display", checked_header.competition_display)
        object.__setattr__(self, "home_display", checked_header.home_display)
        object.__setattr__(self, "away_display", checked_header.away_display)
        object.__setattr__(self, "sportradar_start_time", exact_start)
        object.__setattr__(self, "sportybet_kickoff_utc", kickoff_utc)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        result = {field.name: getattr(self, field.name) for field in dataclasses.fields(self)}
        result["sportybet_kickoff_utc"] = serialize_utc(self.sportybet_kickoff_utc)
        result["safety"] = dict(self.safety)
        return result


def build_kickoff_identity_promotion(
    *,
    event_time_basis: local_time.SportyBetEventLocalTimeBasis,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportradar_evidence: metadata.SportradarUserControlledEventMetadataEvidence,
    sportradar_raw_response: bytes,
) -> SportyBetSportradarKickoffIdentityPromotion:
    rebuilt_time_basis = _revalidate_time_basis(
        event_time_basis,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
        terms_qualification=terms_qualification,
        terms_raw_html=terms_raw_html,
    )
    rebuilt_bridge = _revalidate_bridge(
        event_bridge,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
    )
    if (
        rebuilt_time_basis.event_id != rebuilt_bridge.sportybet_event_id
        or rebuilt_time_basis.sport_id != rebuilt_bridge.sportybet_sport_id
        or rebuilt_time_basis.event_candidate_sha256 != rebuilt_bridge.source_event_candidate_sha256
        or rebuilt_time_basis.event_source_evidence_id != rebuilt_bridge.source_evidence_id
        or rebuilt_time_basis.event_source_manifest_sha256 != rebuilt_bridge.source_evidence_manifest_sha256
        or rebuilt_time_basis.event_source_native_inventory_sha256 != rebuilt_bridge.source_native_inventory_sha256
        or rebuilt_time_basis.event_source_raw_sha256 != rebuilt_bridge.source_raw_sha256
    ):
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "PR #158 and PR #160 do not bind the exact same SportyBet event evidence"
        )
    rebuilt_metadata = _revalidate_metadata(
        sportradar_evidence,
        sportradar_raw_response,
        event_bridge=rebuilt_bridge,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
    )
    bridge_sha = bridge.bridge_sha256(rebuilt_bridge)
    if (
        rebuilt_metadata.source_bridge_sha256 != bridge_sha
        or rebuilt_metadata.source_sportybet_event_id != rebuilt_bridge.sportybet_event_id
        or rebuilt_metadata.source_sportradar_event_id != rebuilt_bridge.sportradar_current_sport_event_id
        or rebuilt_metadata.response_event_id != rebuilt_bridge.sportradar_current_sport_event_id
    ):
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "PR #161 metadata does not bind the exact revalidated PR #160 event identity"
        )
    if rebuilt_metadata.start_time_confirmed is not True:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "official Sportradar start_time_confirmed must be exact True before promotion"
        )
    if rebuilt_metadata.date_confirmed is not True:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "official Sportradar date_confirmed must be exact True before promotion"
        )
    if rebuilt_metadata.replaced_by is not None:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "official Sportradar event has replaced_by; separate identity review required"
        )
    exact_start, kickoff_utc, normalized_text = _parse_exact_provider_timestamp(
        rebuilt_metadata.start_time
    )
    if normalized_text != rebuilt_metadata.start_time_utc_normalized:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "PR #161 normalized start time does not equal exact provider timestamp"
        )
    if _calendar_tuple(rebuilt_time_basis) != _utc_calendar_tuple(kickoff_utc):
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "confirmed Sportradar UTC timestamp does not exactly match SportyBet GMT partial calendar"
        )
    return SportyBetSportradarKickoffIdentityPromotion(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        status=STATUS,
        promotion_authority=PROMOTION_AUTHORITY,
        source_time_basis_sha256=local_time.time_basis_sha256(rebuilt_time_basis),
        source_bridge_sha256=bridge_sha,
        source_metadata_evidence_id=metadata.evidence_identifier(rebuilt_metadata),
        source_metadata_evidence_sha256=metadata.evidence_sha256(rebuilt_metadata),
        source_event_evidence_id=rebuilt_time_basis.event_source_evidence_id,
        source_event_manifest_sha256=rebuilt_time_basis.event_source_manifest_sha256,
        source_native_inventory_sha256=rebuilt_time_basis.event_source_native_inventory_sha256,
        source_event_raw_sha256=rebuilt_time_basis.event_source_raw_sha256,
        event_source_url=rebuilt_time_basis.event_source_url,
        sportybet_event_id=rebuilt_bridge.sportybet_event_id,
        sportybet_sport_id=rebuilt_bridge.sportybet_sport_id,
        sportradar_event_id=rebuilt_bridge.sportradar_current_sport_event_id,
        competition_display=rebuilt_time_basis.competition_display,
        home_display=rebuilt_time_basis.home_display,
        away_display=rebuilt_time_basis.away_display,
        kickoff_display=rebuilt_time_basis.kickoff_display,
        kickoff_day=rebuilt_time_basis.kickoff_day,
        kickoff_month=rebuilt_time_basis.kickoff_month,
        kickoff_weekday=rebuilt_time_basis.kickoff_weekday,
        kickoff_hour=rebuilt_time_basis.kickoff_hour,
        kickoff_minute=rebuilt_time_basis.kickoff_minute,
        sportradar_start_time=exact_start,
        sportradar_start_time_utc_normalized=normalized_text,
        sportradar_start_time_confirmed=True,
        sportradar_date_confirmed=True,
        sportradar_replaced_by=None,
        sportradar_competition_id=rebuilt_metadata.competition_id,
        sportradar_competition_name=rebuilt_metadata.competition_name,
        sportradar_home_competitor_id=rebuilt_metadata.home_competitor_id,
        sportradar_home_competitor_name=rebuilt_metadata.home_competitor_name,
        sportradar_away_competitor_id=rebuilt_metadata.away_competitor_id,
        sportradar_away_competitor_name=rebuilt_metadata.away_competitor_name,
        confirmation_status=CONFIRMATION_STATUS,
        replacement_status=REPLACEMENT_STATUS,
        partial_calendar_match_status=CALENDAR_MATCH_STATUS,
        sportybet_kickoff_year=kickoff_utc.year,
        sportybet_kickoff_timezone=TIME_ZONE_LABEL,
        sportybet_utc_offset_seconds=UTC_OFFSET_SECONDS,
        sportybet_kickoff_utc=kickoff_utc,
        provider_timestamp_subminute_precision_preserved=True,
        sportybet_year_promoted=True,
        sportybet_kickoff_utc_promoted=True,
        provider_event_kickoff_identity_promoted=True,
        fixture_identity_promoted=False,
        fotmob_fixture_reconciliation_authorized=False,
        provider_quote_at=None,
        provider_snapshot_id=None,
        safety=_default_safety(),
    )


def canonical_promotion_bytes(value: Any) -> bytes:
    if not isinstance(value, SportyBetSportradarKickoffIdentityPromotion):
        raise SportyBetSportradarKickoffIdentityPromotionError("promotion type mismatch")
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
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "promotion canonical serialization failed"
        ) from exc
    if len(payload) > MAX_CANONICAL_BYTES:
        raise SportyBetSportradarKickoffIdentityPromotionError(
            "promotion artifact exceeds reviewed size limit"
        )
    return payload


def promotion_sha256(value: Any) -> str:
    return sha256_bytes(canonical_promotion_bytes(value))


__all__ = [
    "CALENDAR_MATCH_STATUS",
    "CONFIRMATION_STATUS",
    "DATASET_NAME",
    "PROMOTION_AUTHORITY",
    "REPLACEMENT_STATUS",
    "STATUS",
    "SportyBetSportradarKickoffIdentityPromotion",
    "SportyBetSportradarKickoffIdentityPromotionError",
    "build_kickoff_identity_promotion",
    "canonical_promotion_bytes",
    "promotion_sha256",
]
