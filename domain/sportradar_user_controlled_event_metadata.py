"""Offline official Sportradar event-metadata evidence bound to SportyBet.

This boundary never performs Sportradar or SportyBet network I/O. A human may
export an official Sportradar Soccer v4 Sport Event Summary JSON response. ATHENA
revalidates the exact PR #160 SportyBet -> Sportradar event-ID bridge, validates
the official endpoint identity, preserves and hashes the response bytes, and
extracts only documented event metadata.

The evidence does not itself promote the missing SportyBet year or kickoff UTC,
prove SportyBet <-> FotMob fixture equivalence, authorize pricing, selection,
booking-code construction, execution, or BET.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import re
import types
from typing import Any, Mapping
from urllib.parse import urlsplit

from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_event_identity_verification as bridge_verify
from domain import sportybet_user_controlled_evidence as sporty_manual
from domain import sportybet_user_controlled_native_inventory as sporty_native
from domain.sportybet_lite_source_capture import (
    MAX_MANIFEST_BYTES,
    MAX_RESPONSE_BYTES,
    SportyBetLiteCaptureError,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportradar-user-controlled-event-metadata-evidence-v1"
PROVIDER = "Sportradar"
SOURCE_ROLE = "OFFICIAL_SPORTRADAR_SOCCER_V4_SPORT_EVENT_SUMMARY"
SOURCE_HOST = "api.sportradar.com"
API_VERSION = "v4"
LANGUAGE_CODE = "en"
FORMAT = "json"
ALLOWED_ACCESS_LEVELS = frozenset({"trial", "production"})
ACQUISITION_MODE = "USER_CONTROLLED_OFFICIAL_API_RESPONSE_EXPORT"
ATTESTATION = "I_MANUALLY_OBTAINED_AND_EXPORTED_THIS_OFFICIAL_SPORTRADAR_RESPONSE"
OBSERVATION_AUTHORITY = "USER_ATTESTED_NOT_PROVIDER_TIMESTAMP"
STATUS = "USER_CONTROLLED_OFFICIAL_SPORTRADAR_EVENT_METADATA_EVIDENCE"
RAW_FILENAME = "response.json"
MANIFEST_FILENAME = "manifest.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportradar-user-controlled-event-metadata"
)
MAX_METADATA_MANIFEST_BYTES = MAX_MANIFEST_BYTES

_SPORT_EVENT_ID_RE = re.compile(r"^sr:sport_event:[1-9][0-9]*$", flags=re.ASCII)
_SPORT_ID_RE = re.compile(r"^sr:sport:[1-9][0-9]*$", flags=re.ASCII)
_COMPETITION_ID_RE = re.compile(r"^sr:competition:[1-9][0-9]*$", flags=re.ASCII)
_COMPETITOR_ID_RE = re.compile(r"^sr:competitor:[1-9][0-9]*$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "booking_code_authorized",
        "bookmaker_equivalence_authorized",
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
_EXPECTED_DIRECTORY_FILES = tuple(sorted((MANIFEST_FILENAME, RAW_FILENAME)))


class SportradarUserControlledEventMetadataError(ValueError):
    """Raised when official Sportradar metadata evidence fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportradarUserControlledEventMetadataError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportradarUserControlledEventMetadataError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise SportradarUserControlledEventMetadataError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise SportradarUserControlledEventMetadataError(
                f"{label} must be timezone-aware"
            )
        return value.astimezone(dt.timezone.utc)
    except SportradarUserControlledEventMetadataError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise SportradarUserControlledEventMetadataError(f"{label} is invalid") from exc


def _text(value: Any, label: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SportradarUserControlledEventMetadataError(
            f"{label} must be a non-empty exact trimmed string"
        )
    if len(value) > maximum:
        raise SportradarUserControlledEventMetadataError(
            f"{label} exceeds {maximum} characters"
        )
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise SportradarUserControlledEventMetadataError(
            f"{label} contains a control character"
        )
    return value


def _provider_id(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    text = _text(value, label, maximum=180)
    if pattern.fullmatch(text) is None:
        raise SportradarUserControlledEventMetadataError(f"{label} is invalid")
    return text


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportradarUserControlledEventMetadataError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _optional_bool(value: Any, label: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise SportradarUserControlledEventMetadataError(
            f"{label} must be exact bool or null"
        )
    return value


def _parse_provider_timestamp(value: Any, label: str) -> tuple[str, str]:
    exact = _text(value, label, maximum=80)
    candidate = exact[:-1] + "+00:00" if exact.endswith("Z") else exact
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportradarUserControlledEventMetadataError(
            f"{label} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SportradarUserControlledEventMetadataError(
            f"{label} must include an explicit UTC offset"
        )
    normalized = parsed.astimezone(dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    return exact, normalized


def validate_source_url(value: Any) -> tuple[str, str]:
    """Return exact access level and event ID for the reviewed official endpoint."""

    text = _text(value, "source_url", maximum=512)
    try:
        parsed = urlsplit(text)
    except ValueError as exc:
        raise SportradarUserControlledEventMetadataError("source_url is invalid") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != SOURCE_HOST
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or "%" in parsed.path
    ):
        raise SportradarUserControlledEventMetadataError(
            "source_url must be the exact reviewed official Sportradar Soccer v4 endpoint"
        )
    try:
        if parsed.port is not None:
            raise SportradarUserControlledEventMetadataError(
                "source_url must not contain an explicit port"
            )
    except ValueError as exc:
        raise SportradarUserControlledEventMetadataError(
            "source_url port is invalid"
        ) from exc
    parts = parsed.path.split("/")
    if len(parts) != 8 or parts[0] != "" or parts[1] != "soccer":
        raise SportradarUserControlledEventMetadataError("source_url path mismatch")
    access_level, version, language, resource, event_id, summary = parts[2:]
    if access_level not in ALLOWED_ACCESS_LEVELS:
        raise SportradarUserControlledEventMetadataError("source_url access level mismatch")
    if (
        version != API_VERSION
        or language != LANGUAGE_CODE
        or resource != "sport_events"
        or summary != "summary.json"
    ):
        raise SportradarUserControlledEventMetadataError("source_url endpoint mismatch")
    _provider_id(event_id, "source_url sport_event_id", _SPORT_EVENT_ID_RE)
    canonical = (
        f"https://{SOURCE_HOST}/soccer/{access_level}/{API_VERSION}/{LANGUAGE_CODE}/"
        f"sport_events/{event_id}/summary.json"
    )
    if text != canonical:
        raise SportradarUserControlledEventMetadataError("source_url is not canonical")
    return access_level, event_id


def _reject_json_constant(value: str) -> None:
    raise SportradarUserControlledEventMetadataError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SportradarUserControlledEventMetadataError(
                f"duplicate JSON object key: {key}"
            )
        result[key] = value
    return result


def strict_response_json(raw_response: Any) -> Mapping[str, Any]:
    if type(raw_response) is not bytes or not 0 < len(raw_response) <= MAX_RESPONSE_BYTES:
        raise SportradarUserControlledEventMetadataError(
            "raw_response must be bounded non-empty exact bytes"
        )
    try:
        text = raw_response.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SportradarUserControlledEventMetadataError(
            "raw_response must be valid UTF-8"
        ) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except SportradarUserControlledEventMetadataError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise SportradarUserControlledEventMetadataError(
            "raw_response must be strict JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise SportradarUserControlledEventMetadataError(
            "Sportradar response root must be an object"
        )
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SportradarUserControlledEventMetadataError(f"{label} must be an object")
    return value


def _extract_event_metadata(
    payload: Mapping[str, Any], *, expected_event_id: str
) -> dict[str, Any]:
    event = _mapping(payload.get("sport_event"), "sport_event")
    event_id = _provider_id(event.get("id"), "sport_event.id", _SPORT_EVENT_ID_RE)
    if event_id != expected_event_id:
        raise SportradarUserControlledEventMetadataError(
            "Sportradar response sport_event.id does not match verified resolver key"
        )

    start_time, start_time_utc = _parse_provider_timestamp(
        event.get("start_time"), "sport_event.start_time"
    )
    start_time_confirmed = _optional_bool(
        event.get("start_time_confirmed"), "sport_event.start_time_confirmed"
    )
    date_confirmed = _optional_bool(event.get("date_confirmed"), "sport_event.date_confirmed")
    replaced_by = event.get("replaced_by")
    if replaced_by is not None:
        replaced_by = _provider_id(replaced_by, "sport_event.replaced_by", _SPORT_EVENT_ID_RE)

    context = _mapping(event.get("sport_event_context"), "sport_event.sport_event_context")
    sport = _mapping(context.get("sport"), "sport_event_context.sport")
    sport_id = _provider_id(sport.get("id"), "sport.id", _SPORT_ID_RE)
    if sport_id != bridge.SOCCER_SPORT_ID:
        raise SportradarUserControlledEventMetadataError(
            "official metadata must identify exact soccer sport id sr:sport:1"
        )

    competition = _mapping(context.get("competition"), "sport_event_context.competition")
    competition_id = _provider_id(
        competition.get("id"), "competition.id", _COMPETITION_ID_RE
    )
    competition_name = _text(competition.get("name"), "competition.name")

    competitors = event.get("competitors")
    if not isinstance(competitors, list) or len(competitors) != 2:
        raise SportradarUserControlledEventMetadataError(
            "sport_event.competitors must contain exactly two competitors"
        )
    by_qualifier: dict[str, tuple[str, str]] = {}
    for index, raw_competitor in enumerate(competitors):
        competitor = _mapping(raw_competitor, f"competitors[{index}]")
        qualifier = _text(competitor.get("qualifier"), f"competitors[{index}].qualifier")
        if qualifier not in {"home", "away"} or qualifier in by_qualifier:
            raise SportradarUserControlledEventMetadataError(
                "competitor qualifiers must be exactly one home and one away"
            )
        competitor_id = _provider_id(
            competitor.get("id"), f"competitors[{index}].id", _COMPETITOR_ID_RE
        )
        competitor_name = _text(
            competitor.get("name"), f"competitors[{index}].name"
        )
        by_qualifier[qualifier] = (competitor_id, competitor_name)
    if set(by_qualifier) != {"home", "away"}:
        raise SportradarUserControlledEventMetadataError(
            "competitor qualifiers must be exactly home and away"
        )

    generated_at = payload.get("generated_at")
    generated_at_utc: str | None = None
    if generated_at is not None:
        generated_at, generated_at_utc = _parse_provider_timestamp(
            generated_at, "generated_at"
        )

    return {
        "response_event_id": event_id,
        "sport_id": sport_id,
        "start_time": start_time,
        "start_time_utc_normalized": start_time_utc,
        "start_time_confirmed": start_time_confirmed,
        "date_confirmed": date_confirmed,
        "replaced_by": replaced_by,
        "competition_id": competition_id,
        "competition_name": competition_name,
        "home_competitor_id": by_qualifier["home"][0],
        "home_competitor_name": by_qualifier["home"][1],
        "away_competitor_id": by_qualifier["away"][0],
        "away_competitor_name": by_qualifier["away"][1],
        "provider_generated_at": generated_at,
        "provider_generated_at_utc_normalized": generated_at_utc,
    }


@dataclasses.dataclass(frozen=True)
class SportradarUserControlledEventMetadataEvidence:
    schema_version: int
    dataset_name: str
    provider: str
    source_role: str
    status: str
    acquisition_mode: str
    source_url: str
    access_level: str
    language_code: str
    response_format: str
    observed_at_user_attested: dt.datetime
    imported_at_utc: dt.datetime
    observation_authority: str
    attestation: str
    athena_network_acquisition_performed: bool
    api_key_persisted: bool
    request_headers_persisted: bool
    source_bridge_sha256: str
    source_sportybet_event_id: str
    source_sportradar_event_id: str
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    response_event_id: str
    sport_id: str
    start_time: str
    start_time_utc_normalized: str
    start_time_confirmed: bool | None
    date_confirmed: bool | None
    replaced_by: str | None
    competition_id: str
    competition_name: str
    home_competitor_id: str
    home_competitor_name: str
    away_competitor_id: str
    away_competitor_name: str
    provider_generated_at: str | None
    provider_generated_at_utc_normalized: str | None
    exact_bridge_identity_matched: bool
    official_response_event_identity_matched: bool
    event_metadata_resolution_authorized: bool
    sportybet_year_promoted: bool
    sportybet_kickoff_utc_promoted: bool
    fixture_identity_promoted: bool
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportradarUserControlledEventMetadataError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportradarUserControlledEventMetadataError("dataset/provider mismatch")
        if self.source_role != SOURCE_ROLE or self.status != STATUS:
            raise SportradarUserControlledEventMetadataError("source role/status mismatch")
        if self.acquisition_mode != ACQUISITION_MODE:
            raise SportradarUserControlledEventMetadataError("acquisition_mode mismatch")
        access_level, source_event_id = validate_source_url(self.source_url)
        if self.access_level != access_level:
            raise SportradarUserControlledEventMetadataError("access_level mismatch")
        if self.language_code != LANGUAGE_CODE or self.response_format != FORMAT:
            raise SportradarUserControlledEventMetadataError("language/format mismatch")
        observed = _utc(self.observed_at_user_attested, "observed_at_user_attested")
        imported = _utc(self.imported_at_utc, "imported_at_utc")
        if imported < observed:
            raise SportradarUserControlledEventMetadataError(
                "imported_at_utc must not precede user-attested observation"
            )
        if self.observation_authority != OBSERVATION_AUTHORITY or self.attestation != ATTESTATION:
            raise SportradarUserControlledEventMetadataError("observation authority/attestation mismatch")
        if self.athena_network_acquisition_performed is not False:
            raise SportradarUserControlledEventMetadataError("ATHENA network acquisition must remain false")
        if self.api_key_persisted is not False or self.request_headers_persisted is not False:
            raise SportradarUserControlledEventMetadataError(
                "API keys and request headers must never be persisted"
            )
        _hash(self.source_bridge_sha256, "source_bridge_sha256")
        _provider_id(self.source_sportybet_event_id, "source_sportybet_event_id", re.compile(r"^sr:match:[1-9][0-9]*$", flags=re.ASCII))
        current_id = _provider_id(
            self.source_sportradar_event_id,
            "source_sportradar_event_id",
            _SPORT_EVENT_ID_RE,
        )
        if source_event_id != current_id:
            raise SportradarUserControlledEventMetadataError(
                "source URL event ID does not match source_sportradar_event_id"
            )
        if self.raw_file_name != RAW_FILENAME:
            raise SportradarUserControlledEventMetadataError("raw_file_name mismatch")
        _hash(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise SportradarUserControlledEventMetadataError("raw_size is invalid")
        if self.response_event_id != current_id:
            raise SportradarUserControlledEventMetadataError("response event identity mismatch")
        if self.sport_id != bridge.SOCCER_SPORT_ID:
            raise SportradarUserControlledEventMetadataError("sport_id mismatch")
        _parse_provider_timestamp(self.start_time, "start_time")
        _parse_provider_timestamp(self.start_time_utc_normalized, "start_time_utc_normalized")
        _optional_bool(self.start_time_confirmed, "start_time_confirmed")
        _optional_bool(self.date_confirmed, "date_confirmed")
        if self.replaced_by is not None:
            _provider_id(self.replaced_by, "replaced_by", _SPORT_EVENT_ID_RE)
        _provider_id(self.competition_id, "competition_id", _COMPETITION_ID_RE)
        _text(self.competition_name, "competition_name")
        _provider_id(self.home_competitor_id, "home_competitor_id", _COMPETITOR_ID_RE)
        _provider_id(self.away_competitor_id, "away_competitor_id", _COMPETITOR_ID_RE)
        _text(self.home_competitor_name, "home_competitor_name")
        _text(self.away_competitor_name, "away_competitor_name")
        if (self.provider_generated_at is None) != (
            self.provider_generated_at_utc_normalized is None
        ):
            raise SportradarUserControlledEventMetadataError(
                "provider generated timestamp fields must be both null or both populated"
            )
        if self.provider_generated_at is not None:
            _parse_provider_timestamp(self.provider_generated_at, "provider_generated_at")
            _parse_provider_timestamp(
                self.provider_generated_at_utc_normalized,
                "provider_generated_at_utc_normalized",
            )
        for field_name in (
            "exact_bridge_identity_matched",
            "official_response_event_identity_matched",
        ):
            if getattr(self, field_name) is not True:
                raise SportradarUserControlledEventMetadataError(
                    f"{field_name} must be exact True"
                )
        for field_name in (
            "event_metadata_resolution_authorized",
            "sportybet_year_promoted",
            "sportybet_kickoff_utc_promoted",
            "fixture_identity_promoted",
        ):
            if getattr(self, field_name) is not False:
                raise SportradarUserControlledEventMetadataError(
                    f"{field_name} must remain exact False"
                )
        object.__setattr__(self, "observed_at_user_attested", observed)
        object.__setattr__(self, "imported_at_utc", imported)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["observed_at_user_attested"] = serialize_utc(self.observed_at_user_attested)
        result["imported_at_utc"] = serialize_utc(self.imported_at_utc)
        result["safety"] = dict(self.safety)
        return result


def build_event_metadata_evidence(
    raw_response: bytes,
    *,
    source_url: str,
    observed_at_user_attested: dt.datetime,
    imported_at_utc: dt.datetime,
    attestation: str,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportybet_manifest: sporty_manual.SportyBetUserControlledEvidenceManifest,
    sportybet_inventory: sporty_native.SportyBetUserControlledNativeInventory,
    sportybet_raw_html: bytes,
) -> SportradarUserControlledEventMetadataEvidence:
    """Build evidence only after exact PR #160 bridge revalidation succeeds."""

    try:
        rebuilt_bridge = bridge_verify.revalidate_sportradar_event_identity_bridge(
            event_bridge,
            manifest=sportybet_manifest,
            inventory=sportybet_inventory,
            raw_html=sportybet_raw_html,
        )
    except bridge.SportyBetSportradarEventIdentityError as exc:
        raise SportradarUserControlledEventMetadataError(str(exc)) from exc
    access_level, requested_event_id = validate_source_url(source_url)
    if requested_event_id != rebuilt_bridge.sportradar_current_sport_event_id:
        raise SportradarUserControlledEventMetadataError(
            "official Sportradar request is not keyed to the exact verified bridge ID"
        )
    payload = strict_response_json(raw_response)
    extracted = _extract_event_metadata(
        payload,
        expected_event_id=rebuilt_bridge.sportradar_current_sport_event_id,
    )
    return SportradarUserControlledEventMetadataEvidence(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        source_role=SOURCE_ROLE,
        status=STATUS,
        acquisition_mode=ACQUISITION_MODE,
        source_url=source_url,
        access_level=access_level,
        language_code=LANGUAGE_CODE,
        response_format=FORMAT,
        observed_at_user_attested=observed_at_user_attested,
        imported_at_utc=imported_at_utc,
        observation_authority=OBSERVATION_AUTHORITY,
        attestation=attestation,
        athena_network_acquisition_performed=False,
        api_key_persisted=False,
        request_headers_persisted=False,
        source_bridge_sha256=bridge.bridge_sha256(rebuilt_bridge),
        source_sportybet_event_id=rebuilt_bridge.sportybet_event_id,
        source_sportradar_event_id=rebuilt_bridge.sportradar_current_sport_event_id,
        raw_file_name=RAW_FILENAME,
        raw_sha256=sha256_bytes(raw_response),
        raw_size=len(raw_response),
        exact_bridge_identity_matched=True,
        official_response_event_identity_matched=True,
        event_metadata_resolution_authorized=False,
        sportybet_year_promoted=False,
        sportybet_kickoff_utc_promoted=False,
        fixture_identity_promoted=False,
        safety=_default_safety(),
        **extracted,
    )


def canonical_manifest_bytes(value: Any) -> bytes:
    if not isinstance(value, SportradarUserControlledEventMetadataEvidence):
        raise SportradarUserControlledEventMetadataError("evidence type mismatch")
    try:
        return (
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
        raise SportradarUserControlledEventMetadataError(
            "evidence canonical serialization failed"
        ) from exc


def evidence_sha256(value: Any) -> str:
    return sha256_bytes(canonical_manifest_bytes(value))


def evidence_identifier(value: Any) -> str:
    if not isinstance(value, SportradarUserControlledEventMetadataEvidence):
        raise SportradarUserControlledEventMetadataError("evidence type mismatch")
    identity = {
        "source_bridge_sha256": value.source_bridge_sha256,
        "source_url": value.source_url,
        "observed_at_user_attested": serialize_utc(value.observed_at_user_attested),
        "raw_sha256": value.raw_sha256,
    }
    raw = json.dumps(
        identity,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)[:24]


def revalidate_event_metadata_evidence(
    value: Any,
    raw_response: bytes,
    *,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportybet_manifest: sporty_manual.SportyBetUserControlledEvidenceManifest,
    sportybet_inventory: sporty_native.SportyBetUserControlledNativeInventory,
    sportybet_raw_html: bytes,
) -> SportradarUserControlledEventMetadataEvidence:
    """Rebuild evidence from exact source bytes and require canonical equality."""

    if not isinstance(value, SportradarUserControlledEventMetadataEvidence):
        raise SportradarUserControlledEventMetadataError("evidence type mismatch")
    rebuilt = build_event_metadata_evidence(
        raw_response,
        source_url=value.source_url,
        observed_at_user_attested=value.observed_at_user_attested,
        imported_at_utc=value.imported_at_utc,
        attestation=value.attestation,
        event_bridge=event_bridge,
        sportybet_manifest=sportybet_manifest,
        sportybet_inventory=sportybet_inventory,
        sportybet_raw_html=sportybet_raw_html,
    )
    if canonical_manifest_bytes(value) != canonical_manifest_bytes(rebuilt):
        raise SportradarUserControlledEventMetadataError(
            "metadata evidence is not the exact deterministic derivative of preserved sources"
        )
    return rebuilt


def _manifest_from_mapping(value: Any) -> SportradarUserControlledEventMetadataEvidence:
    expected = {field.name for field in dataclasses.fields(SportradarUserControlledEventMetadataEvidence)}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SportradarUserControlledEventMetadataError("manifest keys mismatch")
    converted = dict(value)
    try:
        converted["observed_at_user_attested"] = parse_utc_timestamp(
            converted["observed_at_user_attested"], "observed_at_user_attested"
        )
        converted["imported_at_utc"] = parse_utc_timestamp(
            converted["imported_at_utc"], "imported_at_utc"
        )
    except SportyBetLiteCaptureError as exc:
        raise SportradarUserControlledEventMetadataError(str(exc)) from exc
    try:
        return SportradarUserControlledEventMetadataEvidence(**converted)
    except SportradarUserControlledEventMetadataError:
        raise
    except (TypeError, ValueError) as exc:
        raise SportradarUserControlledEventMetadataError("manifest is invalid") from exc


def _validate_root(output_root: Any, *, repository_root: Path) -> Path:
    repository = Path(repository_root).resolve(strict=True)
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        supplied = Path(output_root)
    except (TypeError, ValueError) as exc:
        raise SportradarUserControlledEventMetadataError("output root is invalid") from exc
    if ".." in supplied.parts:
        raise SportradarUserControlledEventMetadataError("output root must not contain traversal")
    supplied_abs = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(supplied_abs, "output root")
    except SportyBetLiteCaptureError as exc:
        raise SportradarUserControlledEventMetadataError(str(exc)) from exc
    if supplied_abs.resolve(strict=False) != expected.resolve(strict=False):
        raise SportradarUserControlledEventMetadataError(
            "output root must be the reviewed Sportradar metadata evidence root"
        )
    return expected


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportradarUserControlledEventMetadataError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportradarUserControlledEventMetadataError(
            f"could not durably write {path.name}"
        ) from exc


def verify_evidence_directory(
    evidence_directory: Any, *, allowed_root: Path
) -> SportradarUserControlledEventMetadataEvidence:
    directory = Path(evidence_directory)
    root = Path(allowed_root)
    if ".." in directory.parts or ".." in root.parts:
        raise SportradarUserControlledEventMetadataError(
            "evidence paths must not contain traversal"
        )
    try:
        _reject_symlink_components(directory, "evidence directory")
        _reject_symlink_components(root, "allowed root")
        resolved_root = root.resolve(strict=True)
        resolved_dir = directory.resolve(strict=True)
        resolved_dir.relative_to(resolved_root)
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportradarUserControlledEventMetadataError(
            "evidence directory escapes or cannot resolve under allowed root"
        ) from exc
    if directory.is_symlink() or not directory.is_dir():
        raise SportradarUserControlledEventMetadataError(
            "evidence directory must be a non-symlink directory"
        )
    if tuple(sorted(item.name for item in directory.iterdir())) != _EXPECTED_DIRECTORY_FILES:
        raise SportradarUserControlledEventMetadataError("evidence directory contents mismatch")
    try:
        raw = _read_regular(
            directory / RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="Sportradar raw response",
        )
        manifest_raw = _read_regular(
            directory / MANIFEST_FILENAME,
            maximum=MAX_METADATA_MANIFEST_BYTES,
            label="Sportradar metadata manifest",
        )
    except SportyBetLiteCaptureError as exc:
        raise SportradarUserControlledEventMetadataError(str(exc)) from exc
    try:
        mapping = json.loads(
            manifest_raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except SportradarUserControlledEventMetadataError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SportradarUserControlledEventMetadataError("manifest JSON is invalid") from exc
    manifest = _manifest_from_mapping(mapping)
    if manifest_raw != canonical_manifest_bytes(manifest):
        raise SportradarUserControlledEventMetadataError("manifest bytes are not canonical")
    if sha256_bytes(raw) != manifest.raw_sha256 or len(raw) != manifest.raw_size:
        raise SportradarUserControlledEventMetadataError("raw response identity mismatch")
    if directory.name != evidence_identifier(manifest):
        raise SportradarUserControlledEventMetadataError("evidence directory identity mismatch")
    return manifest


def store_event_metadata_evidence(
    raw_response: bytes,
    *,
    source_url: str,
    observed_at_user_attested: dt.datetime,
    imported_at_utc: dt.datetime,
    attestation: str,
    event_bridge: bridge.SportyBetSportradarEventIdentityBridge,
    sportybet_manifest: sporty_manual.SportyBetUserControlledEvidenceManifest,
    sportybet_inventory: sporty_native.SportyBetUserControlledNativeInventory,
    sportybet_raw_html: bytes,
    repository_root: Path,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> tuple[Path, SportradarUserControlledEventMetadataEvidence]:
    repository = Path(repository_root).resolve(strict=True)
    root = _validate_root(output_root, repository_root=repository)
    try:
        _ensure_directory_tree_durable(root, boundary=repository)
    except SportyBetLiteCaptureError as exc:
        raise SportradarUserControlledEventMetadataError(str(exc)) from exc
    evidence = build_event_metadata_evidence(
        raw_response,
        source_url=source_url,
        observed_at_user_attested=observed_at_user_attested,
        imported_at_utc=imported_at_utc,
        attestation=attestation,
        event_bridge=event_bridge,
        sportybet_manifest=sportybet_manifest,
        sportybet_inventory=sportybet_inventory,
        sportybet_raw_html=sportybet_raw_html,
    )
    directory = root / evidence_identifier(evidence)
    if directory.exists():
        existing = verify_evidence_directory(directory, allowed_root=root)
        try:
            existing_raw = _read_regular(
                directory / RAW_FILENAME,
                maximum=MAX_RESPONSE_BYTES,
                label="Sportradar raw response",
            )
        except SportyBetLiteCaptureError as exc:
            raise SportradarUserControlledEventMetadataError(str(exc)) from exc
        if canonical_manifest_bytes(existing) != canonical_manifest_bytes(evidence) or existing_raw != raw_response:
            raise SportradarUserControlledEventMetadataError("evidence identifier collision")
        return directory, existing
    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(directory)
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportradarUserControlledEventMetadataError(
            "could not create evidence directory"
        ) from exc
    _write_exclusive(directory / RAW_FILENAME, raw_response)
    _write_exclusive(directory / MANIFEST_FILENAME, canonical_manifest_bytes(evidence))
    verified = verify_evidence_directory(directory, allowed_root=root)
    try:
        _sync_directory(directory)
        _sync_directory(root)
    except SportyBetLiteCaptureError as exc:
        raise SportradarUserControlledEventMetadataError(str(exc)) from exc
    return directory, verified


__all__ = [
    "ACQUISITION_MODE",
    "ALLOWED_OUTPUT_RELATIVE",
    "ATTESTATION",
    "DATASET_NAME",
    "SOURCE_ROLE",
    "STATUS",
    "SportradarUserControlledEventMetadataError",
    "SportradarUserControlledEventMetadataEvidence",
    "build_event_metadata_evidence",
    "canonical_manifest_bytes",
    "evidence_identifier",
    "evidence_sha256",
    "revalidate_event_metadata_evidence",
    "store_event_metadata_evidence",
    "strict_response_json",
    "validate_source_url",
    "verify_evidence_directory",
]
