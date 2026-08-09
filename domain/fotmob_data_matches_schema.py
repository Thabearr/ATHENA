"""Strict offline assessment of reviewed FotMob data-matches JSON structure."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from typing import Any, Mapping, Tuple

from domain.fotmob_data_matches_capture import (
    DATASET_NAME as SOURCE_CAPTURE_DATASET_NAME,
    MAX_RESPONSE_BYTES,
    SCHEMA_VERSION as SOURCE_CAPTURE_SCHEMA_VERSION,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    serialize_utc,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_data_matches_probe import (
    FotMobDataMatchesProbeError,
    validate_ccode3,
    validate_request_date,
    validate_timezone,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-schema-assessment-v1"

TOP_LEVEL_KEYS = frozenset({"date", "leagues"})
LEAGUE_REQUIRED_KEYS = frozenset(
    {"ccode", "id", "internalRank", "matches", "name", "primaryId", "simpleLeague"}
)
LEAGUE_OPTIONAL_KEYS = frozenset(
    {"groupName", "isGroup", "localRank", "parentLeagueId", "parentLeagueName"}
)
LEAGUE_ALLOWED_KEYS = LEAGUE_REQUIRED_KEYS | LEAGUE_OPTIONAL_KEYS
MATCH_KEYS = frozenset(
    {
        "away",
        "eliminatedTeamId",
        "home",
        "id",
        "leagueId",
        "status",
        "statusId",
        "time",
        "timeTS",
        "tournamentStage",
    }
)
TEAM_KEYS = frozenset({"id", "longName", "name", "score"})
STATUS_REQUIRED_KEYS = frozenset(
    {"cancelled", "finished", "halfs", "periodLength", "started", "utcTime"}
)
STATUS_OPTIONAL_KEYS = frozenset({"aggregatedStr", "reason"})
STATUS_ALLOWED_KEYS = STATUS_REQUIRED_KEYS | STATUS_OPTIONAL_KEYS
HALFS_KEYS = frozenset({"firstHalfStarted"})
REASON_KEYS = frozenset({"long", "longKey", "short", "shortKey"})

_UTC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$",
    flags=re.ASCII,
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_json_capture_authorized",
        "schema_assessment_authorized",
        "fixture_extraction_authorized",
        "fixture_candidate_generation_authorized",
        "source_qualified",
        "fixture_promotion_authorized",
        "intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobDataMatchesSchemaError(ValueError):
    """Raised when reviewed data-matches schema evidence fails closed."""


class StructuralCapability(str, enum.Enum):
    PRESENT_IN_CAPTURE = "PRESENT_IN_CAPTURE"
    ABSENT_IN_CAPTURE = "ABSENT_IN_CAPTURE"
    AMBIGUOUS = "AMBIGUOUS"


def _exact_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise FotMobDataMatchesSchemaError(
            f"{label} must be an exact non-negative integer"
        )
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FotMobDataMatchesSchemaError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobDataMatchesSchemaError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobDataMatchesSchemaError(f"{label} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobDataMatchesSchemaError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesSchemaError(f"{label} is invalid") from exc


def _key_tuple(value: Any, label: str) -> Tuple[str, ...]:
    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise FotMobDataMatchesSchemaError(f"{label} must be an immutable string tuple")
    if value != tuple(sorted(set(value))):
        raise FotMobDataMatchesSchemaError(f"{label} must be sorted and unique")
    return value


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _request_values(
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> tuple[str, str, str]:
    try:
        return (
            validate_request_date(request_date),
            validate_timezone(timezone),
            validate_ccode3(ccode3),
        )
    except FotMobDataMatchesProbeError as exc:
        raise FotMobDataMatchesSchemaError(
            "request identity does not match the PR #38 contract"
        ) from exc


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobDataMatchesSchemaError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobDataMatchesSchemaError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(dict(detached))


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesSchemaAssessment:
    schema_version: int
    dataset_name: str
    source_capture_dataset_name: str
    source_capture_schema_version: int
    source_capture_manifest_sha256: str
    source_raw_sha256: str
    source_raw_size: int
    source_observed_at: datetime.datetime
    request_date: str
    timezone: str
    ccode3: str
    payload_date: str
    top_level_keys: Tuple[str, ...]
    league_count: int
    match_count: int
    duplicate_match_id_count: int
    league_link_mismatch_count: int
    kickoff_timestamp_mismatch_count: int
    kickoff_request_date_mismatch_count: int
    league_key_union: Tuple[str, ...]
    match_key_union: Tuple[str, ...]
    match_key_intersection: Tuple[str, ...]
    fixture_identity_candidate: StructuralCapability
    kickoff_candidate: StructuralCapability
    team_identity_candidate: StructuralCapability
    competition_identity_candidate: StructuralCapability
    status_candidate: StructuralCapability
    full_time_score_candidate: StructuralCapability
    half_time_score_candidate: StructuralCapability
    source_freshness_candidate: StructuralCapability
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        try:
            if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
                raise FotMobDataMatchesSchemaError(
                    "schema_version must be exact integer 1"
                )
            if self.dataset_name != DATASET_NAME:
                raise FotMobDataMatchesSchemaError(f"dataset_name must be {DATASET_NAME}")
            if self.source_capture_dataset_name != SOURCE_CAPTURE_DATASET_NAME:
                raise FotMobDataMatchesSchemaError("source capture dataset must be PR #38 v1")
            if (
                type(self.source_capture_schema_version) is not int
                or self.source_capture_schema_version != SOURCE_CAPTURE_SCHEMA_VERSION
            ):
                raise FotMobDataMatchesSchemaError(
                    "source_capture_schema_version must be exact integer 1"
                )
            manifest_sha = _sha256(
                self.source_capture_manifest_sha256,
                "source_capture_manifest_sha256",
            )
            raw_sha = _sha256(self.source_raw_sha256, "source_raw_sha256")
            if (
                type(self.source_raw_size) is not int
                or not 0 < self.source_raw_size <= MAX_RESPONSE_BYTES
            ):
                raise FotMobDataMatchesSchemaError(
                    "source_raw_size must be an exact positive integer within 8 MiB"
                )
            observed_at = _utc(self.source_observed_at, "source_observed_at")
            request_date, timezone, ccode3 = _request_values(
                self.request_date, self.timezone, self.ccode3
            )
            if type(self.payload_date) is not str or self.payload_date != request_date:
                raise FotMobDataMatchesSchemaError(
                    "payload_date must exactly equal request_date"
                )
            top_keys = _key_tuple(self.top_level_keys, "top_level_keys")
            if top_keys != tuple(sorted(TOP_LEVEL_KEYS)):
                raise FotMobDataMatchesSchemaError("top_level_keys mismatch")
            league_count = _exact_nonnegative_int(self.league_count, "league_count")
            match_count = _exact_nonnegative_int(self.match_count, "match_count")
            for label in (
                "duplicate_match_id_count",
                "league_link_mismatch_count",
                "kickoff_timestamp_mismatch_count",
                "kickoff_request_date_mismatch_count",
            ):
                if _exact_nonnegative_int(getattr(self, label), label) != 0:
                    raise FotMobDataMatchesSchemaError(f"{label} must be zero on success")
            league_union = _key_tuple(self.league_key_union, "league_key_union")
            match_union = _key_tuple(self.match_key_union, "match_key_union")
            match_intersection = _key_tuple(
                self.match_key_intersection, "match_key_intersection"
            )
            if league_count:
                if not LEAGUE_REQUIRED_KEYS.issubset(league_union) or not set(
                    league_union
                ).issubset(LEAGUE_ALLOWED_KEYS):
                    raise FotMobDataMatchesSchemaError("league_key_union mismatch")
            elif league_union:
                raise FotMobDataMatchesSchemaError(
                    "empty league list must have empty league key metadata"
                )
            if match_count and (
                set(match_union) != MATCH_KEYS or set(match_intersection) != MATCH_KEYS
            ):
                raise FotMobDataMatchesSchemaError("match key metadata mismatch")
            if not match_count and (match_union or match_intersection):
                raise FotMobDataMatchesSchemaError(
                    "empty capture must have empty match key metadata"
                )
            capability_fields = (
                "fixture_identity_candidate",
                "kickoff_candidate",
                "team_identity_candidate",
                "competition_identity_candidate",
                "status_candidate",
                "full_time_score_candidate",
                "half_time_score_candidate",
                "source_freshness_candidate",
            )
            if any(
                not isinstance(getattr(self, field), StructuralCapability)
                for field in capability_fields
            ):
                raise FotMobDataMatchesSchemaError(
                    "capability values must be StructuralCapability"
                )
            match_presence = (
                StructuralCapability.PRESENT_IN_CAPTURE
                if match_count
                else StructuralCapability.ABSENT_IN_CAPTURE
            )
            expected_capabilities = {
                "fixture_identity_candidate": match_presence,
                "kickoff_candidate": match_presence,
                "team_identity_candidate": match_presence,
                "competition_identity_candidate": (
                    StructuralCapability.PRESENT_IN_CAPTURE
                    if league_count and match_count
                    else StructuralCapability.ABSENT_IN_CAPTURE
                ),
                "status_candidate": match_presence,
                "full_time_score_candidate": (
                    StructuralCapability.AMBIGUOUS
                    if match_count
                    else StructuralCapability.ABSENT_IN_CAPTURE
                ),
                "half_time_score_candidate": StructuralCapability.ABSENT_IN_CAPTURE,
                "source_freshness_candidate": StructuralCapability.ABSENT_IN_CAPTURE,
            }
            if any(
                getattr(self, field) is not expected
                for field, expected in expected_capabilities.items()
            ):
                raise FotMobDataMatchesSchemaError(
                    "capability values do not match structural observations"
                )
            safety = _validate_safety(self.safety)
            object.__setattr__(self, "source_capture_manifest_sha256", manifest_sha)
            object.__setattr__(self, "source_raw_sha256", raw_sha)
            object.__setattr__(self, "source_observed_at", observed_at)
            object.__setattr__(self, "request_date", request_date)
            object.__setattr__(self, "timezone", timezone)
            object.__setattr__(self, "ccode3", ccode3)
            object.__setattr__(self, "top_level_keys", top_keys)
            object.__setattr__(self, "league_count", league_count)
            object.__setattr__(self, "match_count", match_count)
            object.__setattr__(self, "league_key_union", league_union)
            object.__setattr__(self, "match_key_union", match_union)
            object.__setattr__(self, "match_key_intersection", match_intersection)
            object.__setattr__(self, "safety", safety)
        except FotMobDataMatchesSchemaError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobDataMatchesSchemaError(
                f"invalid data-matches schema assessment: {type(exc).__name__}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "source_capture_dataset_name": self.source_capture_dataset_name,
            "source_capture_schema_version": self.source_capture_schema_version,
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_raw_size": self.source_raw_size,
            "source_observed_at": serialize_utc(self.source_observed_at),
            "request_date": self.request_date,
            "timezone": self.timezone,
            "ccode3": self.ccode3,
            "payload_date": self.payload_date,
            "top_level_keys": list(self.top_level_keys),
            "league_count": self.league_count,
            "match_count": self.match_count,
            "duplicate_match_id_count": self.duplicate_match_id_count,
            "league_link_mismatch_count": self.league_link_mismatch_count,
            "kickoff_timestamp_mismatch_count": self.kickoff_timestamp_mismatch_count,
            "kickoff_request_date_mismatch_count": self.kickoff_request_date_mismatch_count,
            "league_key_union": list(self.league_key_union),
            "match_key_union": list(self.match_key_union),
            "match_key_intersection": list(self.match_key_intersection),
            "fixture_identity_candidate": self.fixture_identity_candidate.value,
            "kickoff_candidate": self.kickoff_candidate.value,
            "team_identity_candidate": self.team_identity_candidate.value,
            "competition_identity_candidate": self.competition_identity_candidate.value,
            "status_candidate": self.status_candidate.value,
            "full_time_score_candidate": self.full_time_score_candidate.value,
            "half_time_score_candidate": self.half_time_score_candidate.value,
            "source_freshness_candidate": self.source_freshness_candidate.value,
            "safety": dict(self.safety),
        }


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FotMobDataMatchesSchemaError(f"duplicate response JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FotMobDataMatchesSchemaError(f"invalid response JSON constant: {value}")


def _strict_response_json(raw_json: bytes) -> dict[str, Any]:
    try:
        text = raw_json.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FotMobDataMatchesSchemaError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesSchemaError("response is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise FotMobDataMatchesSchemaError("response top level must be an object")
    return value


def _revalidate_source_manifest(value: Any) -> FotMobDataMatchesCaptureManifest:
    if not isinstance(value, FotMobDataMatchesCaptureManifest):
        raise FotMobDataMatchesSchemaError(
            "source_manifest must be FotMobDataMatchesCaptureManifest"
        )
    try:
        manifest = dataclasses.replace(value)
    except FotMobDataMatchesCaptureError as exc:
        raise FotMobDataMatchesSchemaError("source manifest is invalid") from exc
    if (
        manifest.dataset_name != SOURCE_CAPTURE_DATASET_NAME
        or manifest.schema_version != SOURCE_CAPTURE_SCHEMA_VERSION
    ):
        raise FotMobDataMatchesSchemaError("source manifest is not PR #38 v1")
    return manifest


def _require_keys(
    value: Any,
    *,
    required: frozenset[str],
    allowed: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise FotMobDataMatchesSchemaError(f"{label} must be an object")
    keys = set(value)
    if not required.issubset(keys):
        raise FotMobDataMatchesSchemaError(f"{label} is missing required keys")
    if not keys.issubset(allowed):
        raise FotMobDataMatchesSchemaError(f"{label} has unreviewed keys")
    return value


def _exact_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise FotMobDataMatchesSchemaError(f"{label} must be an exact integer")
    return value


def _exact_str(value: Any, label: str) -> str:
    if type(value) is not str:
        raise FotMobDataMatchesSchemaError(f"{label} must be an exact string")
    return value


def _exact_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise FotMobDataMatchesSchemaError(f"{label} must be an exact bool")
    return value


def _validate_team(value: Any, label: str) -> None:
    team = _require_keys(value, required=TEAM_KEYS, allowed=TEAM_KEYS, label=label)
    _exact_int(team["id"], f"{label}.id")
    _exact_int(team["score"], f"{label}.score")
    _exact_str(team["name"], f"{label}.name")
    _exact_str(team["longName"], f"{label}.longName")


def _validate_reason(value: Any, label: str) -> None:
    reason = _require_keys(value, required=REASON_KEYS, allowed=REASON_KEYS, label=label)
    for key in REASON_KEYS:
        _exact_str(reason[key], f"{label}.{key}")


def _parse_reviewed_utc(value: Any, label: str) -> datetime.datetime:
    text = _exact_str(value, label)
    if _UTC_TIMESTAMP_RE.fullmatch(text) is None:
        raise FotMobDataMatchesSchemaError(
            f"{label} must be an ISO-8601 UTC timestamp ending in Z"
        )
    try:
        parsed = datetime.datetime.fromisoformat(text[:-1] + "+00:00")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesSchemaError(f"{label} is not a valid timestamp") from exc
    if parsed.utcoffset() != datetime.timedelta(0):
        raise FotMobDataMatchesSchemaError(f"{label} must be explicit UTC")
    if parsed.microsecond % 1000:
        raise FotMobDataMatchesSchemaError(
            f"{label} must be compatible with epoch milliseconds"
        )
    return parsed.astimezone(datetime.timezone.utc)


def _epoch_milliseconds(value: datetime.datetime) -> int:
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    delta = value - epoch
    return (
        delta.days * 86_400_000
        + delta.seconds * 1_000
        + delta.microseconds // 1_000
    )


def _validate_status(value: Any, label: str) -> datetime.datetime:
    status = _require_keys(
        value,
        required=STATUS_REQUIRED_KEYS,
        allowed=STATUS_ALLOWED_KEYS,
        label=label,
    )
    kickoff = _parse_reviewed_utc(status["utcTime"], f"{label}.utcTime")
    _exact_int(status["periodLength"], f"{label}.periodLength")
    for key in ("started", "cancelled", "finished"):
        _exact_bool(status[key], f"{label}.{key}")
    halfs = _require_keys(
        status["halfs"], required=HALFS_KEYS, allowed=HALFS_KEYS, label=f"{label}.halfs"
    )
    _exact_str(halfs["firstHalfStarted"], f"{label}.halfs.firstHalfStarted")
    if "aggregatedStr" in status:
        _exact_str(status["aggregatedStr"], f"{label}.aggregatedStr")
    if "reason" in status:
        _validate_reason(status["reason"], f"{label}.reason")
    return kickoff


def _validate_league_fields(league: dict[str, Any], label: str) -> None:
    _exact_str(league["ccode"], f"{label}.ccode")
    _exact_int(league["id"], f"{label}.id")
    _exact_int(league["internalRank"], f"{label}.internalRank")
    _exact_str(league["name"], f"{label}.name")
    _exact_int(league["primaryId"], f"{label}.primaryId")
    _exact_bool(league["simpleLeague"], f"{label}.simpleLeague")
    optional_domains = {
        "groupName": _exact_str,
        "isGroup": _exact_bool,
        "localRank": _exact_int,
        "parentLeagueId": _exact_int,
        "parentLeagueName": _exact_str,
    }
    for key, validator in optional_domains.items():
        if key in league:
            validator(league[key], f"{label}.{key}")
    if type(league["matches"]) is not list:
        raise FotMobDataMatchesSchemaError(f"{label}.matches must be a list")


def assess_fotmob_data_matches_schema(
    raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
) -> FotMobDataMatchesSchemaAssessment:
    """Assess only the frozen PR #39 structural schema, with no fixture output."""

    if type(raw_json) is not bytes:
        raise FotMobDataMatchesSchemaError("raw_json must be exact bytes")
    if not raw_json:
        raise FotMobDataMatchesSchemaError("raw_json must not be empty")
    if len(raw_json) > MAX_RESPONSE_BYTES:
        raise FotMobDataMatchesSchemaError("raw_json exceeds the 8 MiB limit")
    manifest = _revalidate_source_manifest(source_manifest)
    if len(raw_json) != manifest.raw_size:
        raise FotMobDataMatchesSchemaError("raw_json size does not match source manifest")
    raw_sha = hashlib.sha256(raw_json).hexdigest()
    if raw_sha != manifest.raw_sha256:
        raise FotMobDataMatchesSchemaError("raw_json SHA-256 does not match source manifest")

    payload = _strict_response_json(raw_json)
    if set(payload) != TOP_LEVEL_KEYS:
        raise FotMobDataMatchesSchemaError("response top-level keys must be date and leagues")
    payload_date = _exact_str(payload["date"], "payload.date")
    if payload_date != manifest.request_date:
        raise FotMobDataMatchesSchemaError("payload date does not match source request date")
    leagues = payload["leagues"]
    if type(leagues) is not list:
        raise FotMobDataMatchesSchemaError("payload.leagues must be a list")

    match_ids: set[int] = set()
    league_union: set[str] = set()
    match_union: set[str] = set()
    match_intersection: set[str] | None = None
    match_count = 0
    for league_index, raw_league in enumerate(leagues):
        league_label = f"leagues[{league_index}]"
        league = _require_keys(
            raw_league,
            required=LEAGUE_REQUIRED_KEYS,
            allowed=LEAGUE_ALLOWED_KEYS,
            label=league_label,
        )
        _validate_league_fields(league, league_label)
        league_union.update(league)
        league_id = league["id"]
        for match_index, raw_match in enumerate(league["matches"]):
            match_label = f"{league_label}.matches[{match_index}]"
            match = _require_keys(
                raw_match, required=MATCH_KEYS, allowed=MATCH_KEYS, label=match_label
            )
            match_union.update(match)
            match_intersection = (
                set(match) if match_intersection is None else match_intersection & set(match)
            )
            match_id = _exact_int(match["id"], f"{match_label}.id")
            if match_id in match_ids:
                raise FotMobDataMatchesSchemaError("duplicate match id")
            match_ids.add(match_id)
            linked_league_id = _exact_int(match["leagueId"], f"{match_label}.leagueId")
            if linked_league_id != league_id:
                raise FotMobDataMatchesSchemaError("match leagueId does not match containing league")
            _exact_int(match["statusId"], f"{match_label}.statusId")
            _exact_str(match["time"], f"{match_label}.time")
            timestamp_ms = _exact_int(match["timeTS"], f"{match_label}.timeTS")
            _exact_str(match["tournamentStage"], f"{match_label}.tournamentStage")
            if match["eliminatedTeamId"] is not None:
                raise FotMobDataMatchesSchemaError(
                    f"{match_label}.eliminatedTeamId must be null in V1"
                )
            _validate_team(match["home"], f"{match_label}.home")
            _validate_team(match["away"], f"{match_label}.away")
            kickoff = _validate_status(match["status"], f"{match_label}.status")
            if _epoch_milliseconds(kickoff) != timestamp_ms:
                raise FotMobDataMatchesSchemaError("timeTS does not match status.utcTime")
            if kickoff.strftime("%Y%m%d") != manifest.request_date:
                raise FotMobDataMatchesSchemaError(
                    "kickoff UTC date does not match source request date"
                )
            match_count += 1

    matches_present = match_count > 0
    leagues_present = len(leagues) > 0
    present_or_absent = (
        StructuralCapability.PRESENT_IN_CAPTURE
        if matches_present
        else StructuralCapability.ABSENT_IN_CAPTURE
    )
    return FotMobDataMatchesSchemaAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        source_capture_dataset_name=manifest.dataset_name,
        source_capture_schema_version=manifest.schema_version,
        source_capture_manifest_sha256=sha256_data_matches_capture_manifest(manifest),
        source_raw_sha256=manifest.raw_sha256,
        source_raw_size=manifest.raw_size,
        source_observed_at=manifest.observed_at,
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        payload_date=payload_date,
        top_level_keys=tuple(sorted(payload)),
        league_count=len(leagues),
        match_count=match_count,
        duplicate_match_id_count=0,
        league_link_mismatch_count=0,
        kickoff_timestamp_mismatch_count=0,
        kickoff_request_date_mismatch_count=0,
        league_key_union=tuple(sorted(league_union)),
        match_key_union=tuple(sorted(match_union)),
        match_key_intersection=tuple(sorted(match_intersection or set())),
        fixture_identity_candidate=present_or_absent,
        kickoff_candidate=present_or_absent,
        team_identity_candidate=present_or_absent,
        competition_identity_candidate=(
            StructuralCapability.PRESENT_IN_CAPTURE
            if leagues_present and matches_present
            else StructuralCapability.ABSENT_IN_CAPTURE
        ),
        status_candidate=present_or_absent,
        full_time_score_candidate=(
            StructuralCapability.AMBIGUOUS
            if matches_present
            else StructuralCapability.ABSENT_IN_CAPTURE
        ),
        half_time_score_candidate=StructuralCapability.ABSENT_IN_CAPTURE,
        source_freshness_candidate=StructuralCapability.ABSENT_IN_CAPTURE,
        safety=_default_safety(),
    )


def data_matches_schema_assessment_to_dict(
    assessment: Any,
) -> dict[str, Any]:
    if not isinstance(assessment, FotMobDataMatchesSchemaAssessment):
        raise FotMobDataMatchesSchemaError(
            "assessment must be FotMobDataMatchesSchemaAssessment"
        )
    return assessment.to_dict()


def canonical_data_matches_schema_assessment_bytes(assessment: Any) -> bytes:
    if not isinstance(assessment, FotMobDataMatchesSchemaAssessment):
        raise FotMobDataMatchesSchemaError(
            "assessment must be FotMobDataMatchesSchemaAssessment"
        )
    try:
        return (
            json.dumps(
                assessment.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesSchemaError("assessment serialization failed") from exc


def sha256_data_matches_schema_assessment(assessment: Any) -> str:
    return hashlib.sha256(
        canonical_data_matches_schema_assessment_bytes(assessment)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "HALFS_KEYS",
    "LEAGUE_ALLOWED_KEYS",
    "LEAGUE_OPTIONAL_KEYS",
    "LEAGUE_REQUIRED_KEYS",
    "MATCH_KEYS",
    "REASON_KEYS",
    "SCHEMA_VERSION",
    "STATUS_ALLOWED_KEYS",
    "STATUS_OPTIONAL_KEYS",
    "STATUS_REQUIRED_KEYS",
    "StructuralCapability",
    "TEAM_KEYS",
    "TOP_LEVEL_KEYS",
    "FotMobDataMatchesSchemaAssessment",
    "FotMobDataMatchesSchemaError",
    "assess_fotmob_data_matches_schema",
    "canonical_data_matches_schema_assessment_bytes",
    "data_matches_schema_assessment_to_dict",
    "sha256_data_matches_schema_assessment",
]
