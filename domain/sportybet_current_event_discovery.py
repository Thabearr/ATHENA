"""Current SportyBet football-event discovery and exact FotMob reconciliation.

This additive boundary discovers the current configurable SportyBet Nigeria football
prematch event feed through one anonymous read-only FactsCenter request, preserves the
exact response bytes, and reconciles provider events to already-reviewed FotMob fixture
catalog inputs using exact home/away/competition/full-UTC identity only.

It does not infer aliases, reverse teams, round kickoff times, map bookmaker markets,
price selections, route markets, optimize a portfolio, construct a slip, stake, or bet.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
import enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import types
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from domain import fotmob_fixture_catalog_handoff as fotmob_handoff
from domain import sportybet_live_event_quote_evidence as live_event
from domain._sportybet_current_event_discovery_contracts import (
    AUTHORITY,
    CAPTURE_DATASET_NAME,
    DATASET_NAME,
    FOOTBALL_SPORT_ID,
    INVENTORY_DATASET_NAME,
    LIVE_STATUS,
    MATCHING_BASIS,
    MAX_OBSERVATION_AGE_SECONDS,
    MINIMUM_LEAD_SECONDS,
    NEXT_BOUNDARY,
    OBSERVATION_AUTHORITY,
    REPLAY_STATUS,
    SCHEMA_VERSION,
    SOURCE_METHOD,
    UPCOMING_PATH,
    validate_current_event_discovery_contract,
)
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
)

PROVIDER = "SportyBet"
PROVIDER_REGION = "Nigeria"
ORIGIN = live_event.ORIGIN
OPER_ID = live_event.OPER_ID
REQUEST_HEADERS = (
    ("Accept", "application/json"),
    ("Accept-Language", "en-NG,en;q=0.9"),
    ("OperId", OPER_ID),
    ("User-Agent", "ATHENA/1.0 sportybet-current-event-discovery"),
)
MAX_RESPONSE_BYTES = live_event.MAX_RESPONSE_BYTES
MAX_MANIFEST_BYTES = 256 * 1024
RAW_FILENAME = "upcoming.raw.json"
MANIFEST_FILENAME = "manifest.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-current-upcoming-event-discovery"
)
REPLAY_PROOF_MODE = "REPLAY_AS_OF"
LIVE_PROOF_MODE = "LIVE_CURRENT"

_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SAFE_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,200}$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_CAPTURE_AUTHORITY = types.MappingProxyType(
    {
        "direct_provider_network_acquisition": True,
        "current_event_discovery": True,
        "fixture_reconciliation": False,
        "canonical_market_mapping": False,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


class SportyBetCurrentEventDiscoveryError(ValueError):
    """Raised when current event discovery/reconciliation fails closed."""


class CurrentEventReconciliationDisposition(str, enum.Enum):
    UNIQUE_EXACT_MATCH_RECONCILED = "UNIQUE_EXACT_MATCH_RECONCILED"
    NO_EXACT_MATCH = "NO_EXACT_MATCH"
    AMBIGUOUS_FOTMOB_MATCH = "AMBIGUOUS_FOTMOB_MATCH"
    AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE = "AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE"
    COMPETITION_IDENTITY_UNAVAILABLE = "COMPETITION_IDENTITY_UNAVAILABLE"
    PROVIDER_EVENT_NOT_PREMATCH_BOOKABLE = "PROVIDER_EVENT_NOT_PREMATCH_BOOKABLE"
    PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF = "PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF"


def _canonical_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "canonical JSON serialization failed"
        ) from exc
    return encoded + (b"\n" if newline else b"")


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SportyBetCurrentEventDiscoveryError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetCurrentEventDiscoveryError(f"{label} is invalid") from exc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise SportyBetCurrentEventDiscoveryError(
            f"{label} must be an exact lowercase SHA-256"
        )
    return value


def _exact_text(value: Any, label: str, *, maximum: int = 400) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise SportyBetCurrentEventDiscoveryError(
            f"{label} must be exact non-empty trimmed text"
        )
    return value


def _provider_id(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SportyBetCurrentEventDiscoveryError(f"{label} is missing or invalid")
    text = str(value)
    if _SAFE_PROVIDER_ID_RE.fullmatch(text) is None:
        raise SportyBetCurrentEventDiscoveryError(f"{label} is invalid")
    return text


def _event_id(value: Any) -> str:
    if type(value) is not str or _EVENT_RE.fullmatch(value) is None:
        raise SportyBetCurrentEventDiscoveryError(
            "SportyBet event_id must use exact sr:match:<positive integer> form"
        )
    return value


def request_target() -> str:
    return f"{UPCOMING_PATH}?{urlencode((('sportId', FOOTBALL_SPORT_ID),))}"


def request_url() -> str:
    return ORIGIN + request_target()


def _strict_json(raw: Any) -> Any:
    try:
        return live_event.strict_json_loads(raw)
    except live_event.SportyBetLiveEventQuoteEvidenceError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "SportyBet current-event response is not strict UTF-8 JSON"
        ) from exc


def _root_payload(raw: bytes) -> dict[str, Any]:
    payload = _strict_json(raw)
    if type(payload) is not dict:
        raise SportyBetCurrentEventDiscoveryError("provider response must be an object")
    if payload.get("bizCode") != 10000:
        raise SportyBetCurrentEventDiscoveryError(
            f"SportyBet bizCode was not SUCCESS: {payload.get('bizCode')!r}"
        )
    return payload


def _kickoff(value: Any) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SportyBetCurrentEventDiscoveryError(
            "provider event omitted numeric estimateStartTime"
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise SportyBetCurrentEventDiscoveryError("estimateStartTime is invalid")
    try:
        return datetime.fromtimestamp(number / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "estimateStartTime is out of range"
        ) from exc


def _prematch_bookable(event: Mapping[str, Any]) -> bool:
    booking_status = event.get("bookingStatus")
    if isinstance(booking_status, str) and booking_status.casefold() in {
        "unavailable",
        "closed",
        "suspended",
    }:
        return False
    status = event.get("status")
    if status not in (None, 0, "0"):
        return False
    match_status = str(event.get("matchStatus") or "").strip().casefold()
    if match_status and not (
        "not start" in match_status
        or match_status in {"ns", "not_started", "notstarted"}
    ):
        return False
    return True


def _label_from_mapping(value: Mapping[str, Any]) -> str | None:
    for key in (
        "tournamentName",
        "competitionName",
        "tournament_name",
        "competition_name",
        "name",
        "desc",
        "description",
    ):
        child = value.get(key)
        if type(child) is str and child and child == child.strip():
            try:
                return _exact_text(child, "provider competition label")
            except SportyBetCurrentEventDiscoveryError:
                continue
    return None


def _context_from_container(
    value: Mapping[str, Any],
    inherited: tuple[str | None, str | None, str | None],
) -> tuple[str | None, str | None, str | None]:
    label, category_id, tournament_id = inherited
    direct_tournament = value.get("tournament")
    if type(direct_tournament) is dict:
        candidate_label = _label_from_mapping(direct_tournament)
        if candidate_label is not None:
            label = candidate_label
        candidate_id = direct_tournament.get("id", direct_tournament.get("tournamentId"))
        if candidate_id is not None:
            tournament_id = _provider_id(candidate_id, "provider tournament_id")
    direct_category = value.get("category")
    if type(direct_category) is dict:
        candidate_id = direct_category.get("id", direct_category.get("categoryId"))
        if candidate_id is not None:
            category_id = _provider_id(candidate_id, "provider category_id")

    explicit_tournament_id = value.get("tournamentId")
    object_id = value.get("id")
    looks_tournament = (
        explicit_tournament_id is not None
        or type(value.get("events")) is list
        or (
            isinstance(object_id, str)
            and ("tournament" in object_id.casefold() or "league" in object_id.casefold())
        )
    )
    if explicit_tournament_id is not None:
        tournament_id = _provider_id(explicit_tournament_id, "provider tournament_id")
    elif looks_tournament and object_id is not None:
        tournament_id = _provider_id(object_id, "provider tournament_id")
    explicit_category_id = value.get("categoryId")
    if explicit_category_id is not None:
        category_id = _provider_id(explicit_category_id, "provider category_id")
    if looks_tournament:
        candidate_label = _label_from_mapping(value)
        if candidate_label is not None:
            label = candidate_label
    return label, category_id, tournament_id


def _event_competition(
    event: Mapping[str, Any],
    inherited: tuple[str | None, str | None, str | None],
) -> tuple[str | None, str | None, str | None]:
    label, category_id, tournament_id = inherited
    for key in ("tournamentName", "competitionName", "tournament_name", "competition_name"):
        candidate = event.get(key)
        if type(candidate) is str and candidate and candidate == candidate.strip():
            label = _exact_text(candidate, "provider competition label")
            break
    if event.get("categoryId") is not None:
        category_id = _provider_id(event.get("categoryId"), "provider category_id")
    if event.get("tournamentId") is not None:
        tournament_id = _provider_id(event.get("tournamentId"), "provider tournament_id")
    direct_tournament = event.get("tournament")
    if type(direct_tournament) is dict:
        if direct_tournament.get("id") is not None:
            tournament_id = _provider_id(
                direct_tournament.get("id"), "provider tournament_id"
            )
        candidate = _label_from_mapping(direct_tournament)
        if candidate is not None:
            label = candidate
    direct_category = event.get("category")
    if type(direct_category) is dict and direct_category.get("id") is not None:
        category_id = _provider_id(direct_category.get("id"), "provider category_id")
    sport = event.get("sport")
    if type(sport) is dict:
        category = sport.get("category")
        if type(category) is dict:
            if category.get("id") is not None:
                category_id = _provider_id(category.get("id"), "provider category_id")
            tournament = category.get("tournament")
            if type(tournament) is dict:
                if tournament.get("id") is not None:
                    tournament_id = _provider_id(
                        tournament.get("id"), "provider tournament_id"
                    )
                candidate = _label_from_mapping(tournament)
                if candidate is not None:
                    label = candidate
        tournament = sport.get("tournament")
        if type(tournament) is dict:
            if tournament.get("id") is not None:
                tournament_id = _provider_id(
                    tournament.get("id"), "provider tournament_id"
                )
            candidate = _label_from_mapping(tournament)
            if candidate is not None:
                label = candidate
    return label, category_id, tournament_id


@dataclass(frozen=True)
class SportyBetCurrentEvent:
    event_id: str
    sport_id: str
    home_team_name: str
    away_team_name: str
    competition_name: str | None
    category_id: str | None
    tournament_id: str | None
    kickoff_utc: datetime
    booking_status: str | None
    event_status: Any
    match_status: str | None
    prematch_bookable_observed: bool

    def __post_init__(self) -> None:
        _event_id(self.event_id)
        if self.sport_id != FOOTBALL_SPORT_ID:
            raise SportyBetCurrentEventDiscoveryError("event sport_id is not football")
        _exact_text(self.home_team_name, "home_team_name")
        _exact_text(self.away_team_name, "away_team_name")
        if self.home_team_name == self.away_team_name:
            raise SportyBetCurrentEventDiscoveryError("home and away team names must differ")
        if self.competition_name is not None:
            _exact_text(self.competition_name, "competition_name")
        if self.category_id is not None:
            _provider_id(self.category_id, "category_id")
        if self.tournament_id is not None:
            _provider_id(self.tournament_id, "tournament_id")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        if type(self.prematch_bookable_observed) is not bool:
            raise SportyBetCurrentEventDiscoveryError(
                "prematch_bookable_observed must be exact bool"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sport_id": self.sport_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "competition_name": self.competition_name,
            "category_id": self.category_id,
            "tournament_id": self.tournament_id,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "booking_status": self.booking_status,
            "event_status": self.event_status,
            "match_status": self.match_status,
            "prematch_bookable_observed": self.prematch_bookable_observed,
        }


def _event_from_mapping(
    value: Mapping[str, Any],
    context: tuple[str | None, str | None, str | None],
) -> SportyBetCurrentEvent:
    event_id = _event_id(value.get("eventId"))
    sport_id = value.get("sportId")
    if sport_id is None:
        sport = value.get("sport")
        if type(sport) is dict:
            sport_id = sport.get("id")
    if sport_id is None:
        # The request itself is scoped to exact football sportId. Preserve that
        # request-scoped identity rather than inventing a provider field.
        sport_id = FOOTBALL_SPORT_ID
    sport_id = _provider_id(sport_id, "provider sport_id")
    if sport_id != FOOTBALL_SPORT_ID:
        raise SportyBetCurrentEventDiscoveryError(
            f"discovered event {event_id} escaped football request scope"
        )
    competition, category_id, tournament_id = _event_competition(value, context)
    return SportyBetCurrentEvent(
        event_id=event_id,
        sport_id=sport_id,
        home_team_name=_exact_text(value.get("homeTeamName"), "provider home team"),
        away_team_name=_exact_text(value.get("awayTeamName"), "provider away team"),
        competition_name=competition,
        category_id=category_id,
        tournament_id=tournament_id,
        kickoff_utc=_kickoff(value.get("estimateStartTime")),
        booking_status=(
            None if value.get("bookingStatus") is None else str(value.get("bookingStatus"))
        ),
        event_status=value.get("status"),
        match_status=(
            None if value.get("matchStatus") is None else str(value.get("matchStatus"))
        ),
        prematch_bookable_observed=_prematch_bookable(value),
    )


def _extract_events(payload: Mapping[str, Any]) -> tuple[SportyBetCurrentEvent, ...]:
    discovered: list[SportyBetCurrentEvent] = []
    visited = 0

    def walk(
        value: Any,
        context: tuple[str | None, str | None, str | None],
    ) -> None:
        nonlocal visited
        visited += 1
        if visited > 300_000:
            raise SportyBetCurrentEventDiscoveryError(
                "provider response object graph is excessive"
            )
        if type(value) is list:
            for child in value:
                walk(child, context)
            return
        if type(value) is not dict:
            return
        if "eventId" in value and (
            "homeTeamName" in value
            or "awayTeamName" in value
            or "estimateStartTime" in value
        ):
            # Do not treat event-level generic ``name``/``desc`` fields as a
            # tournament container label. Event-specific competition extraction
            # only accepts explicit tournament/competition fields or nested
            # provider tournament objects.
            discovered.append(_event_from_mapping(value, context))
            # Event descendants (markets/outcomes) cannot be discovery events.
            return
        next_context = _context_from_container(value, context)
        for child in value.values():
            walk(child, next_context)

    data = payload.get("data")
    if data is None:
        # A successful empty result may encode no data. Treat this as an empty
        # current configurable inventory, not as an invented event universe.
        return ()
    walk(data, (None, None, None))
    by_id: dict[str, SportyBetCurrentEvent] = {}
    for event in discovered:
        existing = by_id.get(event.event_id)
        if existing is None:
            by_id[event.event_id] = event
        elif existing.to_dict() != event.to_dict():
            raise SportyBetCurrentEventDiscoveryError(
                f"conflicting duplicate provider event identity: {event.event_id}"
            )
    return tuple(sorted(by_id.values(), key=lambda item: (item.kickoff_utc, item.event_id)))


@dataclass(frozen=True)
class SportyBetCurrentEventCaptureManifest:
    schema_version: int
    dataset_name: str
    provider: str
    provider_region: str
    source_method: str
    origin: str
    request_target: str
    request_headers: tuple[tuple[str, str], ...]
    sport_id: str
    http_status: int
    biz_code: int
    observed_at: datetime
    observation_authority: str
    provider_event_timestamp: None
    provider_snapshot_id: None
    network_acquisition_performed: bool
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        validate_current_event_discovery_contract()
        if self.schema_version != SCHEMA_VERSION or type(self.schema_version) is not int:
            raise SportyBetCurrentEventDiscoveryError("manifest schema_version mismatch")
        if (
            self.dataset_name != CAPTURE_DATASET_NAME
            or self.provider != PROVIDER
            or self.provider_region != PROVIDER_REGION
            or self.source_method != SOURCE_METHOD
        ):
            raise SportyBetCurrentEventDiscoveryError("manifest source identity mismatch")
        if self.origin != ORIGIN or self.request_target != request_target():
            raise SportyBetCurrentEventDiscoveryError("manifest request target mismatch")
        if type(self.request_headers) is not tuple or self.request_headers != REQUEST_HEADERS:
            raise SportyBetCurrentEventDiscoveryError("manifest request headers mismatch")
        if self.sport_id != FOOTBALL_SPORT_ID:
            raise SportyBetCurrentEventDiscoveryError("manifest sport identity mismatch")
        if self.http_status != 200 or type(self.http_status) is not int:
            raise SportyBetCurrentEventDiscoveryError("HTTP 200 is required")
        if self.biz_code != 10000 or type(self.biz_code) is not int:
            raise SportyBetCurrentEventDiscoveryError("SportyBet SUCCESS bizCode is required")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetCurrentEventDiscoveryError("observation authority mismatch")
        if self.provider_event_timestamp is not None or self.provider_snapshot_id is not None:
            raise SportyBetCurrentEventDiscoveryError(
                "provider event timestamp/snapshot identity remains unproven"
            )
        if self.network_acquisition_performed is not True:
            raise SportyBetCurrentEventDiscoveryError(
                "network acquisition provenance must be exact True"
            )
        if self.raw_file_name != RAW_FILENAME:
            raise SportyBetCurrentEventDiscoveryError("raw file name mismatch")
        _sha(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise SportyBetCurrentEventDiscoveryError("raw_size is invalid")
        if dict(self.authority) != dict(_CAPTURE_AUTHORITY):
            raise SportyBetCurrentEventDiscoveryError("capture authority flags mismatch")
        object.__setattr__(
            self, "authority", types.MappingProxyType(dict(_CAPTURE_AUTHORITY))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "provider_region": self.provider_region,
            "source_method": self.source_method,
            "origin": self.origin,
            "request_target": self.request_target,
            "request_headers": [list(item) for item in self.request_headers],
            "sport_id": self.sport_id,
            "http_status": self.http_status,
            "biz_code": self.biz_code,
            "observed_at": serialize_utc(self.observed_at),
            "observation_authority": self.observation_authority,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
            "network_acquisition_performed": True,
            "raw_file_name": self.raw_file_name,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "authority": dict(self.authority),
        }


def canonical_manifest_bytes(manifest: Any) -> bytes:
    if type(manifest) is not SportyBetCurrentEventCaptureManifest:
        raise SportyBetCurrentEventDiscoveryError("manifest type mismatch")
    return _canonical_bytes(manifest.to_dict(), newline=True)


def manifest_sha256(manifest: Any) -> str:
    return sha256_bytes(canonical_manifest_bytes(manifest))


def capture_identifier(manifest: Any) -> str:
    if type(manifest) is not SportyBetCurrentEventCaptureManifest:
        raise SportyBetCurrentEventDiscoveryError("manifest type mismatch")
    identity = {
        "request_target": manifest.request_target,
        "observed_at": serialize_utc(manifest.observed_at),
        "raw_sha256": manifest.raw_sha256,
    }
    return hashlib.sha256(_canonical_bytes(identity)).hexdigest()[:24]


def _manifest_from_mapping(value: Any) -> SportyBetCurrentEventCaptureManifest:
    expected = {item.name for item in fields(SportyBetCurrentEventCaptureManifest)}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SportyBetCurrentEventDiscoveryError("manifest keys mismatch")
    headers = value.get("request_headers")
    if type(headers) is not list or any(
        type(item) is not list or len(item) != 2 for item in headers
    ):
        raise SportyBetCurrentEventDiscoveryError("manifest request_headers invalid")
    try:
        return SportyBetCurrentEventCaptureManifest(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            provider=value["provider"],
            provider_region=value["provider_region"],
            source_method=value["source_method"],
            origin=value["origin"],
            request_target=value["request_target"],
            request_headers=tuple(tuple(item) for item in headers),
            sport_id=value["sport_id"],
            http_status=value["http_status"],
            biz_code=value["biz_code"],
            observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
            observation_authority=value["observation_authority"],
            provider_event_timestamp=value["provider_event_timestamp"],
            provider_snapshot_id=value["provider_snapshot_id"],
            network_acquisition_performed=value["network_acquisition_performed"],
            raw_file_name=value["raw_file_name"],
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            authority=value["authority"],
        )
    except SportyBetCurrentEventDiscoveryError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SportyBetCurrentEventDiscoveryError("manifest is invalid") from exc


def _evidence_root(repository_root: Path, *, create: bool) -> Path:
    try:
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "repository_root must resolve to an existing directory"
        ) from exc
    if repository.is_symlink() or not repository.is_dir():
        raise SportyBetCurrentEventDiscoveryError(
            "repository_root must be a regular directory"
        )
    root = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        _reject_symlink_components(root, "current-event discovery evidence root")
        if create:
            _ensure_directory_tree_durable(root, boundary=repository)
        else:
            resolved = root.resolve(strict=True)
            resolved.relative_to(repository)
            if resolved.is_symlink() or not resolved.is_dir():
                raise SportyBetCurrentEventDiscoveryError(
                    "evidence root must be a non-symlink directory"
                )
    except SportyBetCurrentEventDiscoveryError:
        raise
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "current-event evidence root is invalid"
        ) from exc
    return root


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except OSError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            f"could not durably write {path.name}"
        ) from exc


def _network_fetch() -> tuple[bytes, int, datetime]:
    request = Request(
        request_url(),
        method="GET",
        headers=dict(REQUEST_HEADERS),
    )
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
            observed_at = _now_utc()
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
        observed_at = _now_utc()
    except URLError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            f"SportyBet current-event request failed: {exc.reason}"
        ) from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SportyBetCurrentEventDiscoveryError(
            "SportyBet current-event response exceeds byte bound"
        )
    if status != 200:
        raise SportyBetCurrentEventDiscoveryError(
            f"SportyBet current-event endpoint returned HTTP {status}"
        )
    _root_payload(raw)
    return raw, status, observed_at


def _build_manifest(
    *, raw: bytes, status: int, observed_at: datetime
) -> SportyBetCurrentEventCaptureManifest:
    payload = _root_payload(raw)
    return SportyBetCurrentEventCaptureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=CAPTURE_DATASET_NAME,
        provider=PROVIDER,
        provider_region=PROVIDER_REGION,
        source_method=SOURCE_METHOD,
        origin=ORIGIN,
        request_target=request_target(),
        request_headers=REQUEST_HEADERS,
        sport_id=FOOTBALL_SPORT_ID,
        http_status=status,
        biz_code=payload.get("bizCode"),
        observed_at=observed_at,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_event_timestamp=None,
        provider_snapshot_id=None,
        network_acquisition_performed=True,
        raw_file_name=RAW_FILENAME,
        raw_sha256=sha256_bytes(raw),
        raw_size=len(raw),
        authority=_CAPTURE_AUTHORITY,
    )


def capture_current_event_evidence(
    *, repository_root: Path, execute_live_network: bool
) -> tuple[Path, SportyBetCurrentEventCaptureManifest]:
    """Capture exactly one current anonymous configurable football event response."""
    validate_current_event_discovery_contract()
    if execute_live_network is not True:
        raise SportyBetCurrentEventDiscoveryError(
            "live current-event discovery requires exact execute_live_network=True"
        )
    raw, status, observed_at = _network_fetch()
    manifest = _build_manifest(raw=raw, status=status, observed_at=observed_at)
    root = _evidence_root(Path(repository_root), create=True)
    directory = root / capture_identifier(manifest)
    if directory.exists():
        existing = verify_current_event_evidence(
            directory, repository_root=Path(repository_root)
        )
        existing_raw = _read_regular(
            directory / RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="SportyBet current-event raw response",
        )
        if existing.to_dict() != manifest.to_dict() or existing_raw != raw:
            raise SportyBetCurrentEventDiscoveryError("capture identity collision")
        return directory, existing
    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(directory)
    except OSError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "could not create capture directory"
        ) from exc
    _write_exclusive(directory / RAW_FILENAME, raw)
    _write_exclusive(directory / MANIFEST_FILENAME, canonical_manifest_bytes(manifest))
    verified = verify_current_event_evidence(
        directory, repository_root=Path(repository_root)
    )
    _sync_directory(directory)
    _sync_directory(root)
    return directory, verified


def verify_current_event_evidence(
    evidence_directory: Path, *, repository_root: Path
) -> SportyBetCurrentEventCaptureManifest:
    validate_current_event_discovery_contract()
    root = _evidence_root(Path(repository_root), create=False)
    evidence = Path(evidence_directory)
    if ".." in evidence.parts:
        raise SportyBetCurrentEventDiscoveryError(
            "evidence path must not contain traversal"
        )
    try:
        _reject_symlink_components(evidence, "evidence directory")
        resolved = evidence.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "evidence directory escapes reviewed root"
        ) from exc
    if evidence.is_symlink() or not evidence.is_dir():
        raise SportyBetCurrentEventDiscoveryError(
            "evidence directory must be a regular directory"
        )
    if sorted(item.name for item in evidence.iterdir()) != sorted(
        (MANIFEST_FILENAME, RAW_FILENAME)
    ):
        raise SportyBetCurrentEventDiscoveryError(
            "evidence directory contents mismatch"
        )
    raw = _read_regular(
        evidence / RAW_FILENAME,
        maximum=MAX_RESPONSE_BYTES,
        label="SportyBet current-event raw response",
    )
    manifest_raw = _read_regular(
        evidence / MANIFEST_FILENAME,
        maximum=MAX_MANIFEST_BYTES,
        label="SportyBet current-event manifest",
    )
    manifest = _manifest_from_mapping(_strict_json(manifest_raw))
    if manifest_raw != canonical_manifest_bytes(manifest):
        raise SportyBetCurrentEventDiscoveryError("manifest bytes are not canonical")
    if manifest.raw_sha256 != sha256_bytes(raw) or manifest.raw_size != len(raw):
        raise SportyBetCurrentEventDiscoveryError("raw response identity mismatch")
    if evidence.name != capture_identifier(manifest):
        raise SportyBetCurrentEventDiscoveryError(
            "capture directory identity mismatch"
        )
    _root_payload(raw)
    return manifest


@dataclass(frozen=True)
class SportyBetCurrentEventInventory:
    dataset_name: str
    sport_id: str
    observed_at: datetime
    observation_authority: str
    provider_event_timestamp: None
    provider_snapshot_id: None
    source_manifest_sha256: str
    source_raw_sha256: str
    events: tuple[SportyBetCurrentEvent, ...]

    def __post_init__(self) -> None:
        if self.dataset_name != INVENTORY_DATASET_NAME:
            raise SportyBetCurrentEventDiscoveryError("inventory dataset mismatch")
        if self.sport_id != FOOTBALL_SPORT_ID:
            raise SportyBetCurrentEventDiscoveryError("inventory sport identity mismatch")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetCurrentEventDiscoveryError("inventory observation authority mismatch")
        if self.provider_event_timestamp is not None or self.provider_snapshot_id is not None:
            raise SportyBetCurrentEventDiscoveryError(
                "inventory cannot invent provider event timestamp/snapshot identity"
            )
        _sha(self.source_manifest_sha256, "source_manifest_sha256")
        _sha(self.source_raw_sha256, "source_raw_sha256")
        if type(self.events) is not tuple or any(
            type(item) is not SportyBetCurrentEvent for item in self.events
        ):
            raise SportyBetCurrentEventDiscoveryError("inventory events must be typed tuple")
        if self.events != tuple(
            sorted(self.events, key=lambda item: (item.kickoff_utc, item.event_id))
        ):
            raise SportyBetCurrentEventDiscoveryError("inventory events must be canonical sorted")
        ids = [item.event_id for item in self.events]
        if len(ids) != len(set(ids)):
            raise SportyBetCurrentEventDiscoveryError("inventory event IDs are not unique")

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "sport_id": self.sport_id,
            "observed_at": serialize_utc(self.observed_at),
            "observation_authority": self.observation_authority,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "event_count": len(self.events),
            "events": [item.to_dict() for item in self.events],
        }


def build_current_event_inventory(
    evidence_directory: Path, *, repository_root: Path
) -> SportyBetCurrentEventInventory:
    manifest = verify_current_event_evidence(
        evidence_directory, repository_root=repository_root
    )
    raw = _read_regular(
        Path(evidence_directory) / RAW_FILENAME,
        maximum=MAX_RESPONSE_BYTES,
        label="SportyBet current-event raw response",
    )
    payload = _root_payload(raw)
    return SportyBetCurrentEventInventory(
        dataset_name=INVENTORY_DATASET_NAME,
        sport_id=FOOTBALL_SPORT_ID,
        observed_at=manifest.observed_at,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_event_timestamp=None,
        provider_snapshot_id=None,
        source_manifest_sha256=manifest_sha256(manifest),
        source_raw_sha256=manifest.raw_sha256,
        events=_extract_events(payload),
    )


def _verify_fotmob_handoff(
    value: Any,
) -> fotmob_handoff.FotMobFixtureCatalogHandoff:
    if type(value) is not fotmob_handoff.FotMobFixtureCatalogHandoff:
        raise SportyBetCurrentEventDiscoveryError(
            "fotmob_catalog_handoff must be exact FotMobFixtureCatalogHandoff"
        )
    try:
        rebuilt = fotmob_handoff.build_fotmob_fixture_catalog_handoff(
            value.candidate_bundle,
            value.review_bundle,
        )
    except fotmob_handoff.FotMobFixtureCatalogHandoffError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob reviewed catalog handoff reconstruction failed"
        ) from exc
    if rebuilt.to_dict() != value.to_dict():
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob reviewed catalog handoff differs from exact reconstruction"
        )
    return rebuilt


@dataclass(frozen=True)
class SportyBetCurrentEventFixtureReconciliationRow:
    event_id: str
    home_team_name: str
    away_team_name: str
    competition_name: str | None
    kickoff_utc: datetime
    prematch_bookable_observed: bool
    kickoff_lead_seconds: float
    disposition: CurrentEventReconciliationDisposition
    exact_fotmob_match_count: int
    matched_fotmob_fixture_id: str | None
    matched_fotmob_candidate_sha256: str | None
    matched_fotmob_capture_manifest_sha256: str | None
    fixture_reconciliation_authorized: bool

    def __post_init__(self) -> None:
        _event_id(self.event_id)
        _exact_text(self.home_team_name, "home_team_name")
        _exact_text(self.away_team_name, "away_team_name")
        if self.competition_name is not None:
            _exact_text(self.competition_name, "competition_name")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        if type(self.prematch_bookable_observed) is not bool:
            raise SportyBetCurrentEventDiscoveryError("bookability flag must be bool")
        if not math.isfinite(self.kickoff_lead_seconds):
            raise SportyBetCurrentEventDiscoveryError("kickoff lead must be finite")
        if type(self.disposition) is not CurrentEventReconciliationDisposition:
            raise SportyBetCurrentEventDiscoveryError("reconciliation disposition must be typed")
        if type(self.exact_fotmob_match_count) is not int or self.exact_fotmob_match_count < 0:
            raise SportyBetCurrentEventDiscoveryError("exact match count must be non-negative int")
        for value, label in (
            (self.matched_fotmob_candidate_sha256, "matched_fotmob_candidate_sha256"),
            (
                self.matched_fotmob_capture_manifest_sha256,
                "matched_fotmob_capture_manifest_sha256",
            ),
        ):
            if value is not None:
                _sha(value, label)
        expected_authorized = (
            self.disposition
            is CurrentEventReconciliationDisposition.UNIQUE_EXACT_MATCH_RECONCILED
        )
        if self.fixture_reconciliation_authorized is not expected_authorized:
            raise SportyBetCurrentEventDiscoveryError(
                "fixture reconciliation authority mismatches disposition"
            )
        if expected_authorized:
            if (
                self.exact_fotmob_match_count != 1
                or self.matched_fotmob_fixture_id is None
                or self.matched_fotmob_candidate_sha256 is None
                or self.matched_fotmob_capture_manifest_sha256 is None
            ):
                raise SportyBetCurrentEventDiscoveryError(
                    "authorized row omitted exact FotMob identity"
                )
        elif self.disposition is not CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE:
            if self.matched_fotmob_fixture_id is not None:
                raise SportyBetCurrentEventDiscoveryError(
                    "unauthorized row must not retain a chosen FotMob fixture"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "competition_name": self.competition_name,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "prematch_bookable_observed": self.prematch_bookable_observed,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "disposition": self.disposition.value,
            "exact_fotmob_match_count": self.exact_fotmob_match_count,
            "matched_fotmob_fixture_id": self.matched_fotmob_fixture_id,
            "matched_fotmob_candidate_sha256": self.matched_fotmob_candidate_sha256,
            "matched_fotmob_capture_manifest_sha256": (
                self.matched_fotmob_capture_manifest_sha256
            ),
            "fixture_reconciliation_authorized": self.fixture_reconciliation_authorized,
        }


def _initial_reconciliation_rows(
    inventory: SportyBetCurrentEventInventory,
    handoff: fotmob_handoff.FotMobFixtureCatalogHandoff,
    *,
    evaluation_time: datetime,
) -> list[SportyBetCurrentEventFixtureReconciliationRow]:
    records = tuple(handoff.catalog_inputs)
    rows: list[SportyBetCurrentEventFixtureReconciliationRow] = []
    for event in inventory.events:
        lead = (event.kickoff_utc - evaluation_time).total_seconds()
        if event.competition_name is None:
            disposition = CurrentEventReconciliationDisposition.COMPETITION_IDENTITY_UNAVAILABLE
            matches = ()
        elif not event.prematch_bookable_observed:
            disposition = (
                CurrentEventReconciliationDisposition.PROVIDER_EVENT_NOT_PREMATCH_BOOKABLE
            )
            matches = ()
        elif lead <= MINIMUM_LEAD_SECONDS:
            disposition = (
                CurrentEventReconciliationDisposition.PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF
            )
            matches = ()
        else:
            matches = tuple(
                item
                for item in records
                if (
                    item.home_team == event.home_team_name
                    and item.away_team == event.away_team_name
                    and item.competition == event.competition_name
                    and item.kickoff == event.kickoff_utc
                )
            )
            if len(matches) == 1:
                disposition = CurrentEventReconciliationDisposition.UNIQUE_EXACT_MATCH_RECONCILED
            elif not matches:
                disposition = CurrentEventReconciliationDisposition.NO_EXACT_MATCH
            else:
                disposition = CurrentEventReconciliationDisposition.AMBIGUOUS_FOTMOB_MATCH
        matched = matches[0] if len(matches) == 1 else None
        rows.append(
            SportyBetCurrentEventFixtureReconciliationRow(
                event_id=event.event_id,
                home_team_name=event.home_team_name,
                away_team_name=event.away_team_name,
                competition_name=event.competition_name,
                kickoff_utc=event.kickoff_utc,
                prematch_bookable_observed=event.prematch_bookable_observed,
                kickoff_lead_seconds=float(lead),
                disposition=disposition,
                exact_fotmob_match_count=len(matches),
                matched_fotmob_fixture_id=(
                    None if matched is None else matched.source_fixture_identifier
                ),
                matched_fotmob_candidate_sha256=(
                    None if matched is None else matched.candidate_sha256
                ),
                matched_fotmob_capture_manifest_sha256=(
                    None if matched is None else matched.source_capture_manifest_sha256
                ),
                fixture_reconciliation_authorized=(
                    disposition
                    is CurrentEventReconciliationDisposition.UNIQUE_EXACT_MATCH_RECONCILED
                ),
            )
        )
    return rows


def _invalidate_duplicate_provider_targets(
    rows: list[SportyBetCurrentEventFixtureReconciliationRow],
) -> tuple[SportyBetCurrentEventFixtureReconciliationRow, ...]:
    by_fixture: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if (
            row.disposition
            is CurrentEventReconciliationDisposition.UNIQUE_EXACT_MATCH_RECONCILED
            and row.matched_fotmob_fixture_id is not None
        ):
            by_fixture.setdefault(row.matched_fotmob_fixture_id, []).append(index)
    for indexes in by_fixture.values():
        if len(indexes) <= 1:
            continue
        for index in indexes:
            old = rows[index]
            rows[index] = SportyBetCurrentEventFixtureReconciliationRow(
                event_id=old.event_id,
                home_team_name=old.home_team_name,
                away_team_name=old.away_team_name,
                competition_name=old.competition_name,
                kickoff_utc=old.kickoff_utc,
                prematch_bookable_observed=old.prematch_bookable_observed,
                kickoff_lead_seconds=old.kickoff_lead_seconds,
                disposition=(
                    CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE
                ),
                exact_fotmob_match_count=old.exact_fotmob_match_count,
                matched_fotmob_fixture_id=old.matched_fotmob_fixture_id,
                matched_fotmob_candidate_sha256=old.matched_fotmob_candidate_sha256,
                matched_fotmob_capture_manifest_sha256=(
                    old.matched_fotmob_capture_manifest_sha256
                ),
                fixture_reconciliation_authorized=False,
            )
    return tuple(sorted(rows, key=lambda item: (item.kickoff_utc, item.event_id)))


@dataclass(frozen=True, init=False)
class SportyBetCurrentEventFixtureReconciliation:
    schema_version: int
    dataset_name: str
    status: str
    proof_mode: str
    evaluation_time: datetime
    observed_at: datetime
    observation_age_seconds: float
    maximum_observation_age_seconds: int
    minimum_lead_seconds: int
    sport_id: str
    matching_basis: str
    source_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    fotmob_handoff_sha256: str
    current_event_discovery_contract_sha256: str
    rows: tuple[SportyBetCurrentEventFixtureReconciliationRow, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    _evidence_directory: Path
    _repository_root: Path
    _fotmob_handoff: fotmob_handoff.FotMobFixtureCatalogHandoff

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetCurrentEventDiscoveryError(
            "current-event reconciliations are builder-only"
        )

    @property
    def matched_rows(self) -> tuple[SportyBetCurrentEventFixtureReconciliationRow, ...]:
        return tuple(item for item in self.rows if item.fixture_reconciliation_authorized)

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        counts = {
            disposition.value: sum(item.disposition is disposition for item in self.rows)
            for disposition in CurrentEventReconciliationDisposition
        }
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "evaluation_time": serialize_utc(self.evaluation_time),
            "observed_at": serialize_utc(self.observed_at),
            "observation_age_seconds": self.observation_age_seconds,
            "maximum_observation_age_seconds": self.maximum_observation_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "sport_id": self.sport_id,
            "matching_basis": self.matching_basis,
            "source_inventory_sha256": self.source_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "fotmob_handoff_sha256": self.fotmob_handoff_sha256,
            "current_event_discovery_contract_sha256": (
                self.current_event_discovery_contract_sha256
            ),
            "event_count": len(self.rows),
            "matched_count": len(self.matched_rows),
            "disposition_counts": counts,
            "rows": [item.to_dict() for item in self.rows],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _build_reconciliation(
    *,
    evidence_directory: Path,
    repository_root: Path,
    fotmob_catalog_handoff: fotmob_handoff.FotMobFixtureCatalogHandoff,
    evaluation_time: datetime,
    proof_mode: str,
) -> SportyBetCurrentEventFixtureReconciliation:
    identities = validate_current_event_discovery_contract()
    if proof_mode not in {REPLAY_PROOF_MODE, LIVE_PROOF_MODE}:
        raise SportyBetCurrentEventDiscoveryError("proof_mode is invalid")
    now = _utc(evaluation_time, "evaluation_time")
    handoff = _verify_fotmob_handoff(fotmob_catalog_handoff)
    inventory = build_current_event_inventory(
        evidence_directory, repository_root=repository_root
    )
    age = (now - inventory.observed_at).total_seconds()
    if not math.isfinite(age) or age < 0:
        raise SportyBetCurrentEventDiscoveryError(
            "evaluation_time predates direct-provider response completion"
        )
    if age > MAX_OBSERVATION_AGE_SECONDS:
        raise SportyBetCurrentEventDiscoveryError(
            "current-event evidence exceeds maximum observation age"
        )
    rows = _invalidate_duplicate_provider_targets(
        _initial_reconciliation_rows(inventory, handoff, evaluation_time=now)
    )
    value = object.__new__(SportyBetCurrentEventFixtureReconciliation)
    return _set_frozen(
        value,
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": LIVE_STATUS if proof_mode == LIVE_PROOF_MODE else REPLAY_STATUS,
            "proof_mode": proof_mode,
            "evaluation_time": now,
            "observed_at": inventory.observed_at,
            "observation_age_seconds": float(age),
            "maximum_observation_age_seconds": MAX_OBSERVATION_AGE_SECONDS,
            "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
            "sport_id": FOOTBALL_SPORT_ID,
            "matching_basis": MATCHING_BASIS,
            "source_inventory_sha256": inventory.canonical_sha256,
            "source_manifest_sha256": inventory.source_manifest_sha256,
            "source_raw_sha256": inventory.source_raw_sha256,
            "fotmob_handoff_sha256": (
                fotmob_handoff.sha256_fotmob_fixture_catalog_handoff(handoff)
            ),
            "current_event_discovery_contract_sha256": identities[
                "current_event_discovery_contract_sha256"
            ],
            "rows": rows,
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_evidence_directory": Path(evidence_directory),
            "_repository_root": Path(repository_root),
            "_fotmob_handoff": handoff,
        },
    )


def replay_current_event_fixture_reconciliation(
    *,
    evidence_directory: Path,
    repository_root: Path,
    fotmob_catalog_handoff: fotmob_handoff.FotMobFixtureCatalogHandoff,
    evaluation_time: datetime,
) -> SportyBetCurrentEventFixtureReconciliation:
    """Reconcile one preserved provider response at an explicit as-of time."""
    return _build_reconciliation(
        evidence_directory=evidence_directory,
        repository_root=repository_root,
        fotmob_catalog_handoff=fotmob_catalog_handoff,
        evaluation_time=evaluation_time,
        proof_mode=REPLAY_PROOF_MODE,
    )


def capture_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_catalog_handoff: fotmob_handoff.FotMobFixtureCatalogHandoff,
    execute_live_network: bool,
) -> SportyBetCurrentEventFixtureReconciliation:
    """Capture live current events and reconcile them without caller-controlled time."""
    directory, _manifest = capture_current_event_evidence(
        repository_root=repository_root,
        execute_live_network=execute_live_network,
    )
    return _build_reconciliation(
        evidence_directory=directory,
        repository_root=repository_root,
        fotmob_catalog_handoff=fotmob_catalog_handoff,
        evaluation_time=_now_utc(),
        proof_mode=LIVE_PROOF_MODE,
    )


def verify_current_event_fixture_reconciliation(
    value: SportyBetCurrentEventFixtureReconciliation,
) -> SportyBetCurrentEventFixtureReconciliation:
    """Rebuild one reconciliation from retained exact provider/FotMob inputs."""
    if type(value) is not SportyBetCurrentEventFixtureReconciliation:
        raise SportyBetCurrentEventDiscoveryError(
            "value must be exact SportyBetCurrentEventFixtureReconciliation"
        )
    rebuilt = _build_reconciliation(
        evidence_directory=value._evidence_directory,
        repository_root=value._repository_root,
        fotmob_catalog_handoff=value._fotmob_handoff,
        evaluation_time=value.evaluation_time,
        proof_mode=value.proof_mode,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise SportyBetCurrentEventDiscoveryError(
            "current-event reconciliation differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
