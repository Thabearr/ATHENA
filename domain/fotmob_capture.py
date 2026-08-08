"""Strict contracts for preserved FotMob matches-by-date capture evidence."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import pathlib
import re
import types
from typing import Any, Mapping, Sequence, Tuple


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-matches-capture-v1"
SOURCE_PROVIDER = "FOTMOB_UNOFFICIAL_PUBLIC_WEB"
ALLOWED_HOST = "www.fotmob.com"
ALLOWED_PATH = "/api/matches"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
RESPONSE_FILENAME = "response.json"
CANDIDATE_FILENAME = "fixture-candidates.jsonl"
MANIFEST_FILENAME = "manifest.json"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DATE_RE = re.compile(r"^[0-9]{8}$", flags=re.ASCII)
_SOURCE_REFERENCE_RE = re.compile(
    r"^https://www\.fotmob\.com/api/matches\?date=([0-9]{8})$",
    flags=re.ASCII,
)


class FotMobCaptureError(ValueError):
    """Raised when capture data or a capture contract fails closed."""


class FotMobResource(str, enum.Enum):
    MATCHES_BY_DATE = "MATCHES_BY_DATE"


class FotMobReviewStatus(str, enum.Enum):
    UNREVIEWED = "UNREVIEWED"


class FotMobFixtureRejectionReason(str, enum.Enum):
    INVALID_LEAGUE = "INVALID_LEAGUE"
    INVALID_MATCH_CONTAINER = "INVALID_MATCH_CONTAINER"
    INVALID_MATCH_ID = "INVALID_MATCH_ID"
    INVALID_HOME_TEAM = "INVALID_HOME_TEAM"
    INVALID_AWAY_TEAM = "INVALID_AWAY_TEAM"
    INVALID_COMPETITION = "INVALID_COMPETITION"
    INVALID_KICKOFF = "INVALID_KICKOFF"


_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_performed",
        "scraping_performed",
        "browser_automation_performed",
        "credential_use_performed",
        "pricing_acquisition_performed",
        "probability_inference_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


def sha256_bytes(content: bytes) -> str:
    if not isinstance(content, bytes):
        raise FotMobCaptureError("SHA-256 input must be exact bytes")
    return hashlib.sha256(content).hexdigest()


def validate_request_date(value: Any) -> str:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise FotMobCaptureError("request date must be exactly YYYYMMDD ASCII digits")
    try:
        parsed = datetime.datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobCaptureError("request date is not a valid Gregorian date") from exc
    if parsed.strftime("%Y%m%d") != value:
        raise FotMobCaptureError("request date is not canonical YYYYMMDD")
    return value


def build_source_reference(request_date: Any) -> str:
    date = validate_request_date(request_date)
    return f"https://{ALLOWED_HOST}{ALLOWED_PATH}?date={date}"


def request_target(request_date: Any) -> str:
    date = validate_request_date(request_date)
    return f"{ALLOWED_PATH}?date={date}"


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobCaptureError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobCaptureError(f"{label} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobCaptureError(f"{label} is invalid") from exc


def parse_utc_timestamp(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FotMobCaptureError(f"{label} must be a timezone-aware ISO-8601 string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobCaptureError(f"{label} is not valid ISO-8601") from exc
    return _utc(parsed, label)


def serialize_utc(value: datetime.datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def validate_json_content_type(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FotMobCaptureError("Content-Type must identify JSON")
    media_type = value.split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise FotMobCaptureError("Content-Type must be application/json")
    return value


def _strict_string(value: Any, label: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise FotMobCaptureError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise FotMobCaptureError(f"{label} must not contain surrounding whitespace")
    if len(value) > maximum:
        raise FotMobCaptureError(f"{label} must be at most {maximum} characters")
    return value


def _strict_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise FotMobCaptureError(f"{label} must be an exact non-negative integer")
    return value


def _strict_positive_match_id(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise FotMobCaptureError("match id must be an exact positive integer")
    return value


def validate_logical_evidence_path(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FotMobCaptureError("evidence_file_path must be a non-empty relative path")
    posix = pathlib.PurePosixPath(value)
    windows = pathlib.PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        raise FotMobCaptureError("evidence_file_path must be relative")
    if value.startswith(("//", "\\\\")):
        raise FotMobCaptureError("evidence_file_path must not be a UNC path")
    if ".." in posix.parts or ".." in windows.parts:
        raise FotMobCaptureError("evidence_file_path must not contain traversal")
    return value


def _strict_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FotMobCaptureError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _source_reference_date(value: Any) -> str:
    if not isinstance(value, str):
        raise FotMobCaptureError("source_reference must be canonical")
    match = _SOURCE_REFERENCE_RE.fullmatch(value)
    if match is None:
        raise FotMobCaptureError("source_reference must be canonical matches-by-date URL")
    date = validate_request_date(match.group(1))
    if value != build_source_reference(date):
        raise FotMobCaptureError("source_reference must be canonical")
    return date


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCandidate:
    fixture_identifier: str
    source_fixture_identifier: str
    home_team: str
    away_team: str
    competition: str
    kickoff: datetime.datetime
    source_reference: str
    observed_at: datetime.datetime
    evidence_file_path: str
    evidence_sha256: str
    review_status: FotMobReviewStatus

    def __post_init__(self) -> None:
        try:
            source_id = _strict_string(
                self.source_fixture_identifier, "source_fixture_identifier"
            )
            if (
                not source_id.isascii()
                or not source_id.isdigit()
                or int(source_id) <= 0
                or str(int(source_id)) != source_id
            ):
                raise FotMobCaptureError(
                    "source_fixture_identifier must be a positive decimal integer string"
                )
            if self.fixture_identifier != f"FOTMOB:{source_id}":
                raise FotMobCaptureError(
                    "fixture_identifier must be FOTMOB:<source_fixture_identifier>"
                )
            _strict_string(self.home_team, "home_team")
            _strict_string(self.away_team, "away_team")
            _strict_string(self.competition, "competition")
            if self.home_team == self.away_team:
                raise FotMobCaptureError("home_team and away_team must differ")
            object.__setattr__(self, "kickoff", _utc(self.kickoff, "kickoff"))
            object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
            _source_reference_date(self.source_reference)
            validate_logical_evidence_path(self.evidence_file_path)
            _strict_sha(self.evidence_sha256, "evidence_sha256")
            if self.review_status is not FotMobReviewStatus.UNREVIEWED:
                raise FotMobCaptureError("review_status must be UNREVIEWED")
        except FotMobCaptureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobCaptureError(f"invalid fixture candidate: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "source_fixture_identifier": self.source_fixture_identifier,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff": serialize_utc(self.kickoff),
            "source_reference": self.source_reference,
            "observed_at": serialize_utc(self.observed_at),
            "evidence_file_path": self.evidence_file_path,
            "evidence_sha256": self.evidence_sha256,
            "review_status": self.review_status.value,
        }


@dataclasses.dataclass(frozen=True)
class FotMobFixtureRejection:
    league_index: int
    match_index: int
    reason: FotMobFixtureRejectionReason

    def __post_init__(self) -> None:
        _strict_nonnegative_int(self.league_index, "league_index")
        _strict_nonnegative_int(self.match_index, "match_index")
        if not isinstance(self.reason, FotMobFixtureRejectionReason):
            raise FotMobCaptureError("reason must be FotMobFixtureRejectionReason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "league_index": self.league_index,
            "match_index": self.match_index,
            "reason": self.reason.value,
        }


def _candidate_sort_key(candidate: FotMobFixtureCandidate) -> tuple[Any, ...]:
    return (candidate.kickoff, candidate.fixture_identifier)


def _rejection_sort_key(rejection: FotMobFixtureRejection) -> tuple[Any, ...]:
    return (rejection.league_index, rejection.match_index, rejection.reason.value)


def _default_safety(network_acquisition_performed: bool) -> dict[str, bool]:
    if type(network_acquisition_performed) is not bool:
        raise FotMobCaptureError("network_acquisition_performed must be exact bool")
    return {
        key: (network_acquisition_performed if key == "network_acquisition_performed" else False)
        for key in sorted(_SAFETY_KEYS)
    }


@dataclasses.dataclass(frozen=True)
class FotMobMatchesCaptureManifest:
    schema_version: int
    dataset_name: str
    source_provider: str
    resource: FotMobResource
    request_date: str
    source_reference: str
    observed_at: datetime.datetime
    http_status: int
    content_type: str
    payload_byte_size: int
    payload_sha256: str
    evidence_file_path: str
    candidate_fixture_count: int
    rejected_fixture_count: int
    candidates: Tuple[FotMobFixtureCandidate, ...]
    rejections: Tuple[FotMobFixtureRejection, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        try:
            if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
                raise FotMobCaptureError("schema_version must be exact integer 1")
            if self.dataset_name != DATASET_NAME:
                raise FotMobCaptureError(f"dataset_name must be {DATASET_NAME}")
            if self.source_provider != SOURCE_PROVIDER:
                raise FotMobCaptureError(f"source_provider must be {SOURCE_PROVIDER}")
            if self.resource is not FotMobResource.MATCHES_BY_DATE:
                raise FotMobCaptureError("resource must be MATCHES_BY_DATE")
            date = validate_request_date(self.request_date)
            if self.source_reference != build_source_reference(date):
                raise FotMobCaptureError("source_reference does not match request_date")
            observed_at = _utc(self.observed_at, "observed_at")
            object.__setattr__(self, "observed_at", observed_at)
            if type(self.http_status) is not int or self.http_status != 200:
                raise FotMobCaptureError("http_status must be exact integer 200")
            validate_json_content_type(self.content_type)
            size = _strict_nonnegative_int(self.payload_byte_size, "payload_byte_size")
            if size > MAX_RESPONSE_BYTES:
                raise FotMobCaptureError("payload_byte_size exceeds maximum")
            _strict_sha(self.payload_sha256, "payload_sha256")
            validate_logical_evidence_path(self.evidence_file_path)
            candidate_count = _strict_nonnegative_int(
                self.candidate_fixture_count, "candidate_fixture_count"
            )
            rejected_count = _strict_nonnegative_int(
                self.rejected_fixture_count, "rejected_fixture_count"
            )
            if not isinstance(self.candidates, tuple):
                raise FotMobCaptureError("candidates must be a tuple")
            if any(not isinstance(item, FotMobFixtureCandidate) for item in self.candidates):
                raise FotMobCaptureError("candidates must contain fixture candidates")
            if not isinstance(self.rejections, tuple):
                raise FotMobCaptureError("rejections must be a tuple")
            if any(not isinstance(item, FotMobFixtureRejection) for item in self.rejections):
                raise FotMobCaptureError("rejections must contain fixture rejections")
            if candidate_count != len(self.candidates):
                raise FotMobCaptureError("candidate_fixture_count must match candidates")
            if rejected_count != len(self.rejections):
                raise FotMobCaptureError("rejected_fixture_count must match rejections")
            if self.candidates != tuple(sorted(self.candidates, key=_candidate_sort_key)):
                raise FotMobCaptureError("candidates must be deterministically sorted")
            if self.rejections != tuple(sorted(self.rejections, key=_rejection_sort_key)):
                raise FotMobCaptureError("rejections must be deterministically sorted")
            if len({item.fixture_identifier for item in self.candidates}) != len(self.candidates):
                raise FotMobCaptureError("candidate fixture identifiers must be unique")
            for candidate in self.candidates:
                if candidate.source_reference != self.source_reference:
                    raise FotMobCaptureError("candidate source_reference mismatch")
                if candidate.observed_at != observed_at:
                    raise FotMobCaptureError("candidate observed_at mismatch")
                if candidate.evidence_file_path != self.evidence_file_path:
                    raise FotMobCaptureError("candidate evidence_file_path mismatch")
                if candidate.evidence_sha256 != self.payload_sha256:
                    raise FotMobCaptureError("candidate evidence_sha256 mismatch")

            if not isinstance(self.safety, Mapping):
                raise FotMobCaptureError("safety must be a mapping")
            if set(self.safety.keys()) != _SAFETY_KEYS:
                raise FotMobCaptureError("safety keys mismatch")
            detached: dict[str, bool] = {}
            for key, value in self.safety.items():
                if type(value) is not bool:
                    raise FotMobCaptureError(f"safety[{key!r}] must be exact bool")
                if key != "network_acquisition_performed" and value is not False:
                    raise FotMobCaptureError(f"safety[{key!r}] must be False")
                detached[key] = value
            object.__setattr__(self, "safety", types.MappingProxyType(dict(detached)))
        except FotMobCaptureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobCaptureError(f"invalid capture manifest: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "source_provider": self.source_provider,
            "resource": self.resource.value,
            "request_date": self.request_date,
            "source_reference": self.source_reference,
            "observed_at": serialize_utc(self.observed_at),
            "http_status": self.http_status,
            "content_type": self.content_type,
            "payload_byte_size": self.payload_byte_size,
            "payload_sha256": self.payload_sha256,
            "evidence_file_path": self.evidence_file_path,
            "candidate_fixture_count": self.candidate_fixture_count,
            "rejected_fixture_count": self.rejected_fixture_count,
            "candidates": [item.to_dict() for item in self.candidates],
            "rejections": [item.to_dict() for item in self.rejections],
            "safety": dict(self.safety),
        }


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FotMobCaptureError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise FotMobCaptureError(f"invalid JSON constant: {value}")


def strict_json_loads(raw_payload: bytes, *, label: str = "payload") -> Any:
    if not isinstance(raw_payload, bytes):
        raise FotMobCaptureError(f"{label} must be exact bytes")
    try:
        text = raw_payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FotMobCaptureError(f"{label} must be valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except FotMobCaptureError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobCaptureError(f"{label} is not strict JSON") from exc


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def parse_fotmob_matches_payload(
    raw_payload: bytes,
    *,
    request_date: str,
    observed_at: datetime.datetime,
    evidence_file_path: str = RESPONSE_FILENAME,
) -> tuple[Tuple[FotMobFixtureCandidate, ...], Tuple[FotMobFixtureRejection, ...]]:
    """Extract deterministic UNREVIEWED candidates from preserved raw bytes."""

    if not isinstance(raw_payload, bytes):
        raise FotMobCaptureError("raw_payload must be exact bytes")
    if len(raw_payload) > MAX_RESPONSE_BYTES:
        raise FotMobCaptureError("raw payload exceeds maximum response size")
    date = validate_request_date(request_date)
    observed = _utc(observed_at, "observed_at")
    evidence_path = validate_logical_evidence_path(evidence_file_path)
    payload_sha = sha256_bytes(raw_payload)
    source_reference = build_source_reference(date)
    payload = strict_json_loads(raw_payload)
    if not isinstance(payload, Mapping):
        raise FotMobCaptureError("top-level payload must be a JSON object")
    if "leagues" not in payload:
        raise FotMobCaptureError("top-level payload must contain leagues")
    leagues = payload["leagues"]
    if not isinstance(leagues, list):
        raise FotMobCaptureError("leagues must be a list")

    candidates: list[FotMobFixtureCandidate] = []
    rejections: list[FotMobFixtureRejection] = []
    seen_fixture_ids: set[str] = set()

    for league_index, raw_league in enumerate(leagues):
        league = _mapping(raw_league)
        if league is None:
            rejections.append(
                FotMobFixtureRejection(
                    league_index, 0, FotMobFixtureRejectionReason.INVALID_LEAGUE
                )
            )
            continue
        try:
            competition = _strict_string(league.get("name"), "league name")
        except FotMobCaptureError:
            rejections.append(
                FotMobFixtureRejection(
                    league_index, 0, FotMobFixtureRejectionReason.INVALID_COMPETITION
                )
            )
            continue
        matches = league.get("matches")
        if not isinstance(matches, list):
            rejections.append(
                FotMobFixtureRejection(
                    league_index,
                    0,
                    FotMobFixtureRejectionReason.INVALID_MATCH_CONTAINER,
                )
            )
            continue

        for match_index, raw_match in enumerate(matches):
            match = _mapping(raw_match)
            if match is None:
                rejections.append(
                    FotMobFixtureRejection(
                        league_index,
                        match_index,
                        FotMobFixtureRejectionReason.INVALID_MATCH_CONTAINER,
                    )
                )
                continue
            try:
                match_id = _strict_positive_match_id(match.get("id"))
            except FotMobCaptureError:
                rejections.append(
                    FotMobFixtureRejection(
                        league_index,
                        match_index,
                        FotMobFixtureRejectionReason.INVALID_MATCH_ID,
                    )
                )
                continue
            home = _mapping(match.get("home"))
            try:
                home_team = _strict_string(
                    home.get("name") if home is not None else None,
                    "home team",
                )
            except FotMobCaptureError:
                rejections.append(
                    FotMobFixtureRejection(
                        league_index,
                        match_index,
                        FotMobFixtureRejectionReason.INVALID_HOME_TEAM,
                    )
                )
                continue
            away = _mapping(match.get("away"))
            try:
                away_team = _strict_string(
                    away.get("name") if away is not None else None,
                    "away team",
                )
            except FotMobCaptureError:
                rejections.append(
                    FotMobFixtureRejection(
                        league_index,
                        match_index,
                        FotMobFixtureRejectionReason.INVALID_AWAY_TEAM,
                    )
                )
                continue
            status = _mapping(match.get("status"))
            try:
                kickoff = parse_utc_timestamp(
                    status.get("utcTime") if status is not None else None,
                    "kickoff",
                )
            except FotMobCaptureError:
                rejections.append(
                    FotMobFixtureRejection(
                        league_index,
                        match_index,
                        FotMobFixtureRejectionReason.INVALID_KICKOFF,
                    )
                )
                continue
            source_id = str(match_id)
            fixture_id = f"FOTMOB:{source_id}"
            if fixture_id in seen_fixture_ids:
                rejections.append(
                    FotMobFixtureRejection(
                        league_index,
                        match_index,
                        FotMobFixtureRejectionReason.INVALID_MATCH_ID,
                    )
                )
                continue
            seen_fixture_ids.add(fixture_id)
            candidates.append(
                FotMobFixtureCandidate(
                    fixture_identifier=fixture_id,
                    source_fixture_identifier=source_id,
                    home_team=home_team,
                    away_team=away_team,
                    competition=competition,
                    kickoff=kickoff,
                    source_reference=source_reference,
                    observed_at=observed,
                    evidence_file_path=evidence_path,
                    evidence_sha256=payload_sha,
                    review_status=FotMobReviewStatus.UNREVIEWED,
                )
            )
    return (
        tuple(sorted(candidates, key=_candidate_sort_key)),
        tuple(sorted(rejections, key=_rejection_sort_key)),
    )


def build_capture_manifest(
    raw_payload: bytes,
    *,
    request_date: str,
    observed_at: datetime.datetime,
    http_status: int = 200,
    content_type: str = "application/json",
    evidence_file_path: str = RESPONSE_FILENAME,
    network_acquisition_performed: bool,
) -> FotMobMatchesCaptureManifest:
    if not isinstance(raw_payload, bytes):
        raise FotMobCaptureError("raw_payload must be exact bytes")
    if len(raw_payload) > MAX_RESPONSE_BYTES:
        raise FotMobCaptureError("raw payload exceeds maximum response size")
    candidates, rejections = parse_fotmob_matches_payload(
        raw_payload,
        request_date=request_date,
        observed_at=observed_at,
        evidence_file_path=evidence_file_path,
    )
    return FotMobMatchesCaptureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        source_provider=SOURCE_PROVIDER,
        resource=FotMobResource.MATCHES_BY_DATE,
        request_date=validate_request_date(request_date),
        source_reference=build_source_reference(request_date),
        observed_at=_utc(observed_at, "observed_at"),
        http_status=http_status,
        content_type=validate_json_content_type(content_type),
        payload_byte_size=len(raw_payload),
        payload_sha256=sha256_bytes(raw_payload),
        evidence_file_path=validate_logical_evidence_path(evidence_file_path),
        candidate_fixture_count=len(candidates),
        rejected_fixture_count=len(rejections),
        candidates=candidates,
        rejections=rejections,
        safety=_default_safety(network_acquisition_performed),
    )


def canonical_candidate_jsonl_bytes(
    candidates: Sequence[FotMobFixtureCandidate],
) -> bytes:
    if not isinstance(candidates, (tuple, list)):
        raise FotMobCaptureError("candidates must be a list or tuple")
    if any(not isinstance(item, FotMobFixtureCandidate) for item in candidates):
        raise FotMobCaptureError("candidates must contain fixture candidates")
    ordered = tuple(sorted(candidates, key=_candidate_sort_key))
    try:
        return b"".join(
            (
                json.dumps(
                    item.to_dict(),
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            for item in ordered
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobCaptureError("candidate JSON Lines serialization failed") from exc


def canonical_manifest_bytes(manifest: FotMobMatchesCaptureManifest) -> bytes:
    if not isinstance(manifest, FotMobMatchesCaptureManifest):
        raise FotMobCaptureError("manifest must be FotMobMatchesCaptureManifest")
    try:
        return (
            json.dumps(
                manifest.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobCaptureError("manifest serialization failed") from exc


_CANDIDATE_KEYS = frozenset(field.name for field in dataclasses.fields(FotMobFixtureCandidate))
_REJECTION_KEYS = frozenset(field.name for field in dataclasses.fields(FotMobFixtureRejection))
_MANIFEST_KEYS = frozenset(field.name for field in dataclasses.fields(FotMobMatchesCaptureManifest))


def _candidate_from_mapping(value: Any) -> FotMobFixtureCandidate:
    if not isinstance(value, Mapping) or set(value) != _CANDIDATE_KEYS:
        raise FotMobCaptureError("manifest candidate keys mismatch")
    try:
        return FotMobFixtureCandidate(
            fixture_identifier=value["fixture_identifier"],
            source_fixture_identifier=value["source_fixture_identifier"],
            home_team=value["home_team"],
            away_team=value["away_team"],
            competition=value["competition"],
            kickoff=parse_utc_timestamp(value["kickoff"], "candidate kickoff"),
            source_reference=value["source_reference"],
            observed_at=parse_utc_timestamp(value["observed_at"], "candidate observed_at"),
            evidence_file_path=value["evidence_file_path"],
            evidence_sha256=value["evidence_sha256"],
            review_status=FotMobReviewStatus(value["review_status"]),
        )
    except FotMobCaptureError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise FotMobCaptureError("invalid manifest candidate") from exc


def _rejection_from_mapping(value: Any) -> FotMobFixtureRejection:
    if not isinstance(value, Mapping) or set(value) != _REJECTION_KEYS:
        raise FotMobCaptureError("manifest rejection keys mismatch")
    try:
        return FotMobFixtureRejection(
            league_index=value["league_index"],
            match_index=value["match_index"],
            reason=FotMobFixtureRejectionReason(value["reason"]),
        )
    except FotMobCaptureError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise FotMobCaptureError("invalid manifest rejection") from exc


def manifest_from_mapping(value: Any) -> FotMobMatchesCaptureManifest:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_KEYS:
        raise FotMobCaptureError("manifest keys mismatch")
    candidates = value.get("candidates")
    rejections = value.get("rejections")
    if not isinstance(candidates, list) or not isinstance(rejections, list):
        raise FotMobCaptureError("manifest candidates and rejections must be lists")
    try:
        return FotMobMatchesCaptureManifest(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            source_provider=value["source_provider"],
            resource=FotMobResource(value["resource"]),
            request_date=value["request_date"],
            source_reference=value["source_reference"],
            observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
            http_status=value["http_status"],
            content_type=value["content_type"],
            payload_byte_size=value["payload_byte_size"],
            payload_sha256=value["payload_sha256"],
            evidence_file_path=value["evidence_file_path"],
            candidate_fixture_count=value["candidate_fixture_count"],
            rejected_fixture_count=value["rejected_fixture_count"],
            candidates=tuple(_candidate_from_mapping(item) for item in candidates),
            rejections=tuple(_rejection_from_mapping(item) for item in rejections),
            safety=value["safety"],
        )
    except FotMobCaptureError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise FotMobCaptureError("invalid manifest") from exc


def _regular_non_symlink(path: pathlib.Path, label: str) -> pathlib.Path:
    if path.is_symlink() or not path.is_file():
        raise FotMobCaptureError(f"{label} must be a regular non-symlink file")
    return path


def verify_capture_directory(
    capture_directory: pathlib.Path,
    *,
    require_network_acquisition_performed: bool | None = None,
) -> FotMobMatchesCaptureManifest:
    """Verify an existing capture entirely offline."""

    try:
        capture_directory = pathlib.Path(capture_directory)
    except (TypeError, ValueError) as exc:
        raise FotMobCaptureError("capture directory path is invalid") from exc
    if capture_directory.is_symlink() or not capture_directory.is_dir():
        raise FotMobCaptureError("capture directory must be a non-symlink directory")
    entries = {entry.name for entry in capture_directory.iterdir()}
    required = {RESPONSE_FILENAME, CANDIDATE_FILENAME, MANIFEST_FILENAME}
    if entries != required:
        raise FotMobCaptureError("capture directory must contain exactly the required files")
    raw_path = _regular_non_symlink(capture_directory / RESPONSE_FILENAME, "raw evidence")
    candidate_path = _regular_non_symlink(
        capture_directory / CANDIDATE_FILENAME, "candidate JSON Lines"
    )
    manifest_path = _regular_non_symlink(
        capture_directory / MANIFEST_FILENAME, "manifest"
    )
    try:
        raw_payload = raw_path.read_bytes()
        candidate_bytes = candidate_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise FotMobCaptureError("capture files could not be read") from exc
    payload = strict_json_loads(manifest_bytes, label="manifest")
    manifest = manifest_from_mapping(payload)
    if manifest.request_date != capture_directory.parent.name:
        raise FotMobCaptureError("capture directory date does not match manifest")
    if require_network_acquisition_performed is not None:
        if type(require_network_acquisition_performed) is not bool:
            raise FotMobCaptureError("network verification requirement must be exact bool")
        if (
            manifest.safety["network_acquisition_performed"]
            is not require_network_acquisition_performed
        ):
            raise FotMobCaptureError("network acquisition provenance state mismatch")
    if manifest.evidence_file_path != RESPONSE_FILENAME:
        raise FotMobCaptureError("manifest evidence path must be response.json")
    if len(raw_payload) != manifest.payload_byte_size:
        raise FotMobCaptureError("raw evidence byte size mismatch")
    if sha256_bytes(raw_payload) != manifest.payload_sha256:
        raise FotMobCaptureError("raw evidence SHA-256 mismatch")
    expected = build_capture_manifest(
        raw_payload,
        request_date=manifest.request_date,
        observed_at=manifest.observed_at,
        http_status=manifest.http_status,
        content_type=manifest.content_type,
        evidence_file_path=manifest.evidence_file_path,
        network_acquisition_performed=manifest.safety[
            "network_acquisition_performed"
        ],
    )
    if expected != manifest:
        raise FotMobCaptureError("manifest does not match derived capture evidence")
    if canonical_candidate_jsonl_bytes(expected.candidates) != candidate_bytes:
        raise FotMobCaptureError("candidate JSON Lines do not match raw evidence")
    if canonical_manifest_bytes(expected) != manifest_bytes:
        raise FotMobCaptureError("manifest bytes are not canonical or have drifted")
    return manifest


__all__ = [
    "ALLOWED_HOST",
    "ALLOWED_PATH",
    "CANDIDATE_FILENAME",
    "DATASET_NAME",
    "FotMobCaptureError",
    "FotMobFixtureCandidate",
    "FotMobFixtureRejection",
    "FotMobFixtureRejectionReason",
    "FotMobMatchesCaptureManifest",
    "FotMobResource",
    "FotMobReviewStatus",
    "MANIFEST_FILENAME",
    "MAX_RESPONSE_BYTES",
    "RESPONSE_FILENAME",
    "SCHEMA_VERSION",
    "SOURCE_PROVIDER",
    "build_capture_manifest",
    "build_source_reference",
    "canonical_candidate_jsonl_bytes",
    "canonical_manifest_bytes",
    "manifest_from_mapping",
    "parse_fotmob_matches_payload",
    "parse_utc_timestamp",
    "request_target",
    "serialize_utc",
    "sha256_bytes",
    "strict_json_loads",
    "validate_json_content_type",
    "validate_logical_evidence_path",
    "validate_request_date",
    "verify_capture_directory",
]
