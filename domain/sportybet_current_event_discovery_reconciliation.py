"""Current SportyBet football event discovery and exact FotMob reconciliation.

This boundary discovers provider event IDs from SportyBet's anonymous public
football event list, preserves the exact response pages, matches only exact
case-sensitive home/away/competition/full-UTC identities against reviewed
FotMob catalog inputs, and confirms every authorized match through the already
reviewed direct event-detail source before issuing fixture-reconciliation
authority.

It does not map canonical markets, compute prices/value, route, optimize, build
a slip, stake, execute, or place a wager.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import types
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from domain import fotmob_fixture_catalog_handoff as fotmob_handoff
from domain import sportybet_live_event_quote_evidence as live
from domain import _portfolio_optimizer_v2_direct_provider_contracts as portfolio_v2_contracts
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
    serialize_utc,
    sha256_bytes,
)

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-sportybet-current-event-discovery-reconciliation-v1"
DISCOVERY_DATASET_NAME = "athena-sportybet-current-event-discovery-v1"
STATUS = "CURRENT_DIRECT_PROVIDER_EVENT_DISCOVERY_RECONCILIATION_VERIFIED"
PROVIDER = "SportyBet"
PROVIDER_REGION = "Nigeria"
DISCOVERY_SOURCE_METHOD = "PUBLIC_ANONYMOUS_FACTS_CENTER_LIVE_OR_PREMATCH_EVENTS_GET"
ORIGIN = live.ORIGIN
OPER_ID = live.OPER_ID
DISCOVERY_PATH = "/api/ng/factsCenter/liveOrPrematchEvents"
FOOTBALL_SPORT_ID = "sr:sport:1"
PAGE_SIZE = 100
MAX_PAGES = 20
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
REQUEST_HEADERS = (
    ("Accept", "application/json"),
    ("Accept-Language", "en-NG,en;q=0.9"),
    ("OperId", OPER_ID),
    ("User-Agent", "ATHENA/1.0 sportybet-current-event-discovery"),
)
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-current-event-discovery"
)
MANIFEST_FILENAME = "manifest.json"
OBSERVATION_AUTHORITY = (
    "ATHENA_DIRECT_PROVIDER_DISCOVERY_RESPONSE_COMPLETION_NOT_PROVIDER_EVENT_TIMESTAMP"
)
MATCHING_BASIS = (
    "EXACT_CASE_SENSITIVE_HOME_AWAY_COMPETITION_FULL_UTC_NO_ALIAS_NO_FUZZY_NO_TOLERANCE"
)
DETAIL_CONFIRMATION_POLICY = (
    "EXACT_PR246_EVENT_GET_REPLAY_REQUIRED_BEFORE_FIXTURE_RECONCILIATION_AUTHORITY"
)
PORTFOLIO_OPTIMIZER_V2_CONTRACT_SHA256 = (
    "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd"
)
LIVE_EVENT_SOURCE_CONTRACT_SHA256 = (
    "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
)
NEXT_BOUNDARY = "CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED"
EXPECTED_CONTRACT_SHA256 = (
    "ce69058ea61eecb9b5849567746bc0358ee29f2a4798b61190673d436d25b7ae"
)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

AUTHORITY = types.MappingProxyType(
    {
        "current_event_discovery": True,
        "current_event_detail_confirmation": True,
        "fixture_reconciliation": True,
        "canonical_market_mapping": False,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "final_selection": False,
        "accumulator_slip_construction": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)


class SportyBetCurrentEventDiscoveryError(ValueError):
    """Raised when current provider event discovery/reconciliation fails closed."""


class CurrentEventReconciliationDisposition(str, enum.Enum):
    UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED = (
        "UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED"
    )
    DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE = "DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE"
    PROVIDER_COMPETITION_UNPROVEN = "PROVIDER_COMPETITION_UNPROVEN"
    NO_EXACT_REVIEWED_FOTMOB_MATCH = "NO_EXACT_REVIEWED_FOTMOB_MATCH"
    AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH = "AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH"
    DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED = "DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED"


def _canonical_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        raw = json.dumps(
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
    return raw + (b"\n" if newline else b"")


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise SportyBetCurrentEventDiscoveryError(f"{label} must be an exact SHA-256")
    return value


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SportyBetCurrentEventDiscoveryError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetCurrentEventDiscoveryError(f"{label} is invalid") from exc


def _text(value: Any, label: str, *, maximum: int = 300) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise SportyBetCurrentEventDiscoveryError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def _optional_text(value: Any, label: str, *, maximum: int = 300) -> str | None:
    if value is None:
        return None
    return _text(value, label, maximum=maximum)


def _event_id(value: Any) -> str:
    if type(value) is not str or _EVENT_RE.fullmatch(value) is None:
        raise SportyBetCurrentEventDiscoveryError(
            "event_id must use exact sr:match:<positive integer> form"
        )
    return value


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def request_target(page_num: Any) -> str:
    if isinstance(page_num, bool) or not isinstance(page_num, int) or not 1 <= page_num <= MAX_PAGES:
        raise SportyBetCurrentEventDiscoveryError("page_num is outside reviewed pagination bounds")
    query = urlencode(
        (
            ("sportId", FOOTBALL_SPORT_ID),
            ("pageSize", PAGE_SIZE),
            ("pageNum", page_num),
        )
    )
    return f"{DISCOVERY_PATH}?{query}"


def request_url(page_num: Any) -> str:
    return ORIGIN + request_target(page_num)


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "discovery_source_method": DISCOVERY_SOURCE_METHOD,
        "origin": ORIGIN,
        "oper_id": OPER_ID,
        "discovery_path": DISCOVERY_PATH,
        "football_sport_id": FOOTBALL_SPORT_ID,
        "request_headers": [list(item) for item in REQUEST_HEADERS],
        "page_size": PAGE_SIZE,
        "max_pages": MAX_PAGES,
        "max_response_bytes": MAX_RESPONSE_BYTES,
        "matching_basis": MATCHING_BASIS,
        "detail_confirmation_policy": DETAIL_CONFIRMATION_POLICY,
        "portfolio_optimizer_v2_contract_sha256": (
            PORTFOLIO_OPTIMIZER_V2_CONTRACT_SHA256
        ),
        "live_event_source_contract_sha256": LIVE_EVENT_SOURCE_CONTRACT_SHA256,
        "fotmob_handoff_dataset_name": fotmob_handoff.DATASET_NAME,
        "fotmob_handoff_schema_version": fotmob_handoff.SCHEMA_VERSION,
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(AUTHORITY),
    }


def calculate_current_event_discovery_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes({"version": CONTRACT_VERSION, "semantics": _contract_payload()})
    ).hexdigest()


def validate_current_event_discovery_contract() -> Mapping[str, str]:
    try:
        live_identity = live.validate_direct_event_source_contract()
        portfolio_identity = portfolio_v2_contracts.validate_portfolio_optimizer_v2_contract()
    except Exception as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "current event discovery dependency validation failed"
        ) from exc
    if live_identity["contract_sha256"] != LIVE_EVENT_SOURCE_CONTRACT_SHA256:
        raise SportyBetCurrentEventDiscoveryError("PR246 live event source identity drifted")
    if (
        portfolio_identity["portfolio_optimizer_v2_contract_sha256"]
        != PORTFOLIO_OPTIMIZER_V2_CONTRACT_SHA256
    ):
        raise SportyBetCurrentEventDiscoveryError("PR250 portfolio identity drifted")
    if (fotmob_handoff.DATASET_NAME, fotmob_handoff.SCHEMA_VERSION) != (
        "athena-fotmob-fixture-catalog-handoff-v1",
        1,
    ):
        raise SportyBetCurrentEventDiscoveryError("FotMob reviewed handoff identity drifted")
    actual = calculate_current_event_discovery_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise SportyBetCurrentEventDiscoveryError(
            "current event discovery/reconciliation contract drifted"
        )
    return types.MappingProxyType(
        {
            "current_event_discovery_contract_sha256": actual,
            "live_event_source_contract_sha256": live_identity["contract_sha256"],
            "portfolio_optimizer_v2_contract_sha256": (
                portfolio_identity["portfolio_optimizer_v2_contract_sha256"]
            ),
        }
    )


def _kickoff(value: Any) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SportyBetCurrentEventDiscoveryError(
            "discovered event omitted numeric estimateStartTime"
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise SportyBetCurrentEventDiscoveryError("discovered estimateStartTime is invalid")
    try:
        return datetime.fromtimestamp(number / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "discovered estimateStartTime is out of range"
        ) from exc


def _event_is_prematch_bookable(event: Mapping[str, Any]) -> bool:
    if event.get("bookingStatus") == "Unavailable":
        return False
    status = event.get("status")
    if status not in (None, 0, "0"):
        return False
    if event.get("setScore") not in (None, "") or event.get("playedSeconds") not in (None, ""):
        return False
    match_status = str(event.get("matchStatus") or "").strip().casefold()
    return not match_status or "not start" in match_status or match_status == "ns"


def _nested_competition(event: Mapping[str, Any]) -> str | None:
    sport = event.get("sport")
    if type(sport) is not dict:
        return None
    category = sport.get("category")
    if type(category) is not dict:
        return None
    tournament = category.get("tournament")
    if type(tournament) is dict and tournament.get("name") is not None:
        return _text(tournament.get("name"), "provider tournament name")
    return None


def _competition(event: Mapping[str, Any], inherited: str | None) -> tuple[str | None, str]:
    values: list[tuple[str, str]] = []
    if inherited is not None:
        values.append((_text(inherited, "provider tournament envelope name"), "TOURNAMENT_ENVELOPE_NAME"))
    for key, basis in (
        ("tournamentName", "EVENT_TOURNAMENT_NAME"),
        ("leagueName", "EVENT_LEAGUE_NAME"),
        ("competitionName", "EVENT_COMPETITION_NAME"),
    ):
        if event.get(key) is not None:
            values.append((_text(event.get(key), f"provider {key}"), basis))
    nested = _nested_competition(event)
    if nested is not None:
        values.append((nested, "EVENT_NESTED_TOURNAMENT_NAME"))
    unique = {name for name, _ in values}
    if not unique:
        return None, "PROVIDER_COMPETITION_UNAVAILABLE"
    if len(unique) != 1:
        return None, "PROVIDER_COMPETITION_CONFLICTED"
    name = next(iter(unique))
    bases = "+".join(sorted({basis for _, basis in values}))
    return name, bases


@dataclass(frozen=True)
class SportyBetDiscoveredEvent:
    event_id: str
    home_team_name: str
    away_team_name: str
    competition_name: str | None
    competition_basis: str
    kickoff_utc: datetime
    booking_status: str | None
    event_status: Any
    match_status: str | None
    prematch_bookable_observed: bool
    source_page_num: int
    source_raw_sha256: str
    source_observed_at: datetime

    def __post_init__(self) -> None:
        _event_id(self.event_id)
        _text(self.home_team_name, "home_team_name")
        _text(self.away_team_name, "away_team_name")
        if self.home_team_name == self.away_team_name:
            raise SportyBetCurrentEventDiscoveryError("discovered home/away teams must differ")
        if self.competition_name is not None:
            _text(self.competition_name, "competition_name")
        _text(self.competition_basis, "competition_basis")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        if type(self.prematch_bookable_observed) is not bool:
            raise SportyBetCurrentEventDiscoveryError("prematch_bookable_observed must be bool")
        if type(self.source_page_num) is not int or not 1 <= self.source_page_num <= MAX_PAGES:
            raise SportyBetCurrentEventDiscoveryError("source_page_num is invalid")
        _sha(self.source_raw_sha256, "source_raw_sha256")
        object.__setattr__(
            self, "source_observed_at", _utc(self.source_observed_at, "source_observed_at")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "competition_name": self.competition_name,
            "competition_basis": self.competition_basis,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "booking_status": self.booking_status,
            "event_status": self.event_status,
            "match_status": self.match_status,
            "prematch_bookable_observed": self.prematch_bookable_observed,
            "source_page_num": self.source_page_num,
            "source_raw_sha256": self.source_raw_sha256,
            "source_observed_at": serialize_utc(self.source_observed_at),
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()


def _candidate_from_event(
    event: Mapping[str, Any], *, inherited_competition: str | None, page_num: int,
    raw_sha256: str, observed_at: datetime,
) -> SportyBetDiscoveredEvent:
    competition_name, competition_basis = _competition(event, inherited_competition)
    return SportyBetDiscoveredEvent(
        event_id=_event_id(event.get("eventId")),
        home_team_name=_text(event.get("homeTeamName"), "provider home team"),
        away_team_name=_text(event.get("awayTeamName"), "provider away team"),
        competition_name=competition_name,
        competition_basis=competition_basis,
        kickoff_utc=_kickoff(event.get("estimateStartTime")),
        booking_status=_optional_text(event.get("bookingStatus"), "bookingStatus"),
        event_status=event.get("status"),
        match_status=(None if event.get("matchStatus") is None else str(event.get("matchStatus"))),
        prematch_bookable_observed=_event_is_prematch_bookable(event),
        source_page_num=page_num,
        source_raw_sha256=raw_sha256,
        source_observed_at=observed_at,
    )


def _extract_events(raw: bytes, *, page_num: int, observed_at: datetime) -> tuple[SportyBetDiscoveredEvent, ...]:
    payload = live.strict_json_loads(raw)
    if type(payload) is not dict or payload.get("bizCode") != 10000:
        raise SportyBetCurrentEventDiscoveryError("SportyBet discovery response was not SUCCESS")
    data = payload.get("data")
    if type(data) not in (list, dict):
        raise SportyBetCurrentEventDiscoveryError("SportyBet discovery data must be list or object")
    raw_sha = sha256_bytes(raw)
    rows: list[SportyBetDiscoveredEvent] = []

    def visit(value: Any, inherited: str | None) -> None:
        if type(value) is list:
            for item in value:
                visit(item, inherited)
            return
        if type(value) is not dict:
            return
        event_like = all(key in value for key in ("eventId", "homeTeamName", "awayTeamName"))
        if event_like:
            rows.append(
                _candidate_from_event(
                    value,
                    inherited_competition=inherited,
                    page_num=page_num,
                    raw_sha256=raw_sha,
                    observed_at=observed_at,
                )
            )
            return
        child_inherited = inherited
        if type(value.get("events")) is list and value.get("name") is not None:
            child_inherited = _text(value.get("name"), "provider tournament envelope name")
        for child in value.values():
            if type(child) in (list, dict):
                visit(child, child_inherited)

    visit(data, None)
    identities = [item.event_id for item in rows]
    if len(identities) != len(set(identities)):
        raise SportyBetCurrentEventDiscoveryError(
            "one discovery page contains duplicate provider event IDs"
        )
    return tuple(sorted(rows, key=lambda item: int(item.event_id.rsplit(":", 1)[1])))


@dataclass(frozen=True)
class SportyBetDiscoveryPageEvidence:
    page_num: int
    request_target: str
    observed_at: datetime
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    event_count: int

    def __post_init__(self) -> None:
        if type(self.page_num) is not int or not 1 <= self.page_num <= MAX_PAGES:
            raise SportyBetCurrentEventDiscoveryError("page evidence number is invalid")
        if self.request_target != request_target(self.page_num):
            raise SportyBetCurrentEventDiscoveryError("page request identity mismatch")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "page observed_at"))
        if self.raw_file_name != f"page-{self.page_num:04d}.raw.json":
            raise SportyBetCurrentEventDiscoveryError("page raw filename mismatch")
        _sha(self.raw_sha256, "page raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise SportyBetCurrentEventDiscoveryError("page raw_size is invalid")
        if type(self.event_count) is not int or self.event_count < 0:
            raise SportyBetCurrentEventDiscoveryError("page event_count is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_num": self.page_num,
            "request_target": self.request_target,
            "observed_at": serialize_utc(self.observed_at),
            "raw_file_name": self.raw_file_name,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "event_count": self.event_count,
        }


_DISCOVERY_AUTHORITY = types.MappingProxyType(
    {
        "current_event_discovery": True,
        "fixture_reconciliation": False,
        "canonical_market_mapping": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "bet": False,
    }
)


@dataclass(frozen=True)
class SportyBetCurrentEventDiscoveryManifest:
    schema_version: int
    dataset_name: str
    provider: str
    provider_region: str
    source_method: str
    origin: str
    sport_id: str
    page_size: int
    pages: tuple[SportyBetDiscoveryPageEvidence, ...]
    events: tuple[SportyBetDiscoveredEvent, ...]
    observed_at: datetime
    observation_authority: str
    network_acquisition_performed: bool
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        validate_current_event_discovery_contract()
        if (
            self.schema_version,
            self.dataset_name,
            self.provider,
            self.provider_region,
            self.source_method,
            self.origin,
            self.sport_id,
            self.page_size,
        ) != (
            SCHEMA_VERSION,
            DISCOVERY_DATASET_NAME,
            PROVIDER,
            PROVIDER_REGION,
            DISCOVERY_SOURCE_METHOD,
            ORIGIN,
            FOOTBALL_SPORT_ID,
            PAGE_SIZE,
        ):
            raise SportyBetCurrentEventDiscoveryError("discovery manifest metadata mismatch")
        if type(self.pages) is not tuple or not self.pages:
            raise SportyBetCurrentEventDiscoveryError("discovery must preserve at least one response page")
        if tuple(item.page_num for item in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise SportyBetCurrentEventDiscoveryError("discovery pages must be contiguous from page 1")
        if type(self.events) is not tuple:
            raise SportyBetCurrentEventDiscoveryError("discovered events must be an immutable tuple")
        event_ids = [item.event_id for item in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise SportyBetCurrentEventDiscoveryError("discovery manifest event IDs are not unique")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "discovery observed_at"))
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetCurrentEventDiscoveryError("discovery observation authority mismatch")
        if self.network_acquisition_performed is not True:
            raise SportyBetCurrentEventDiscoveryError("network acquisition provenance must be exact True")
        if dict(self.authority) != dict(_DISCOVERY_AUTHORITY):
            raise SportyBetCurrentEventDiscoveryError("discovery authority mismatch")
        object.__setattr__(self, "authority", types.MappingProxyType(dict(_DISCOVERY_AUTHORITY)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "provider_region": self.provider_region,
            "source_method": self.source_method,
            "origin": self.origin,
            "sport_id": self.sport_id,
            "page_size": self.page_size,
            "page_count": len(self.pages),
            "pages": [item.to_dict() for item in self.pages],
            "event_count": len(self.events),
            "events": [item.to_dict() for item in self.events],
            "observed_at": serialize_utc(self.observed_at),
            "observation_authority": self.observation_authority,
            "network_acquisition_performed": True,
            "authority": dict(self.authority),
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()


def _network_fetch_page(page_num: int) -> tuple[bytes, int, datetime]:
    request = Request(request_url(page_num), method="GET", headers=dict(REQUEST_HEADERS))
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
    except URLError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            f"SportyBet discovery request failed: {exc.reason}"
        ) from exc
    observed = _now_utc()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SportyBetCurrentEventDiscoveryError("SportyBet discovery response exceeds byte bound")
    if status != 200:
        raise SportyBetCurrentEventDiscoveryError(f"SportyBet discovery returned HTTP {status}")
    return raw, status, observed


def _evidence_root(repository_root: Path, *, create: bool) -> Path:
    try:
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "repository_root must resolve to an existing directory"
        ) from exc
    if repository.is_symlink() or not repository.is_dir():
        raise SportyBetCurrentEventDiscoveryError("repository_root must be a regular directory")
    root = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        _reject_symlink_components(root, "current event discovery root")
        if create:
            _ensure_directory_tree_durable(root, boundary=repository)
        else:
            resolved = root.resolve(strict=True)
            resolved.relative_to(repository)
            if resolved.is_symlink() or not resolved.is_dir():
                raise SportyBetCurrentEventDiscoveryError("discovery root must be a directory")
    except SportyBetCurrentEventDiscoveryError:
        raise
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError("discovery evidence root is invalid") from exc
    return root


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportyBetCurrentEventDiscoveryError(f"refusing to overwrite {path.name}") from exc
    except OSError as exc:
        raise SportyBetCurrentEventDiscoveryError(f"could not durably write {path.name}") from exc


def _manifest_bytes(manifest: SportyBetCurrentEventDiscoveryManifest) -> bytes:
    return _canonical_bytes(manifest.to_dict(), newline=True)


def _capture_identifier(manifest: SportyBetCurrentEventDiscoveryManifest) -> str:
    return manifest.canonical_sha256[:24]


def capture_current_event_discovery(
    *, repository_root: Path, execute_live_network: bool
) -> tuple[Path, SportyBetCurrentEventDiscoveryManifest]:
    """Capture current football event-list pages until pagination produces no new IDs."""
    validate_current_event_discovery_contract()
    if execute_live_network is not True:
        raise SportyBetCurrentEventDiscoveryError(
            "current SportyBet discovery requires exact execute_live_network=True"
        )
    page_payloads: list[tuple[SportyBetDiscoveryPageEvidence, bytes]] = []
    event_by_id: dict[str, SportyBetDiscoveredEvent] = {}
    exhausted = False
    for page_num in range(1, MAX_PAGES + 1):
        raw, status, observed = _network_fetch_page(page_num)
        if status != 200:
            raise SportyBetCurrentEventDiscoveryError("discovery HTTP status must be 200")
        page_events = _extract_events(raw, page_num=page_num, observed_at=observed)
        page = SportyBetDiscoveryPageEvidence(
            page_num=page_num,
            request_target=request_target(page_num),
            observed_at=observed,
            raw_file_name=f"page-{page_num:04d}.raw.json",
            raw_sha256=sha256_bytes(raw),
            raw_size=len(raw),
            event_count=len(page_events),
        )
        page_payloads.append((page, raw))
        new_count = 0
        for event in page_events:
            existing = event_by_id.get(event.event_id)
            if existing is None:
                event_by_id[event.event_id] = event
                new_count += 1
            else:
                comparable_existing = dict(existing.to_dict())
                comparable_new = dict(event.to_dict())
                for row in (comparable_existing, comparable_new):
                    row.pop("source_page_num", None)
                    row.pop("source_raw_sha256", None)
                    row.pop("source_observed_at", None)
                if comparable_existing != comparable_new:
                    raise SportyBetCurrentEventDiscoveryError(
                        f"provider event identity drifted across discovery pages: {event.event_id}"
                    )
        if not page_events or new_count == 0:
            exhausted = True
            break
    if not exhausted:
        raise SportyBetCurrentEventDiscoveryError(
            "discovery pagination bound exhausted while new event IDs were still arriving"
        )
    pages = tuple(item for item, _ in page_payloads)
    events = tuple(
        sorted(event_by_id.values(), key=lambda item: int(item.event_id.rsplit(":", 1)[1]))
    )
    manifest = SportyBetCurrentEventDiscoveryManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DISCOVERY_DATASET_NAME,
        provider=PROVIDER,
        provider_region=PROVIDER_REGION,
        source_method=DISCOVERY_SOURCE_METHOD,
        origin=ORIGIN,
        sport_id=FOOTBALL_SPORT_ID,
        page_size=PAGE_SIZE,
        pages=pages,
        events=events,
        observed_at=max(item.observed_at for item in pages),
        observation_authority=OBSERVATION_AUTHORITY,
        network_acquisition_performed=True,
        authority=_DISCOVERY_AUTHORITY,
    )
    root = _evidence_root(Path(repository_root), create=True)
    directory = root / _capture_identifier(manifest)
    if directory.exists():
        existing = verify_current_event_discovery(directory, repository_root=repository_root)
        if existing.to_dict() != manifest.to_dict():
            raise SportyBetCurrentEventDiscoveryError("discovery capture identity collision")
        return directory, existing
    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(directory)
    except OSError as exc:
        raise SportyBetCurrentEventDiscoveryError("could not create discovery directory") from exc
    for page, raw in page_payloads:
        _write_exclusive(directory / page.raw_file_name, raw)
    _write_exclusive(directory / MANIFEST_FILENAME, _manifest_bytes(manifest))
    verified = verify_current_event_discovery(directory, repository_root=repository_root)
    _sync_directory(directory)
    _sync_directory(root)
    return directory, verified


def _event_from_mapping(value: Mapping[str, Any]) -> SportyBetDiscoveredEvent:
    try:
        from domain.sportybet_lite_source_capture import parse_utc_timestamp
        return SportyBetDiscoveredEvent(
            event_id=value["event_id"],
            home_team_name=value["home_team_name"],
            away_team_name=value["away_team_name"],
            competition_name=value["competition_name"],
            competition_basis=value["competition_basis"],
            kickoff_utc=parse_utc_timestamp(value["kickoff_utc"], "kickoff_utc"),
            booking_status=value["booking_status"],
            event_status=value["event_status"],
            match_status=value["match_status"],
            prematch_bookable_observed=value["prematch_bookable_observed"],
            source_page_num=value["source_page_num"],
            source_raw_sha256=value["source_raw_sha256"],
            source_observed_at=parse_utc_timestamp(value["source_observed_at"], "source_observed_at"),
        )
    except Exception as exc:
        if isinstance(exc, SportyBetCurrentEventDiscoveryError):
            raise
        raise SportyBetCurrentEventDiscoveryError("discovered event manifest row is invalid") from exc


def _page_from_mapping(value: Mapping[str, Any]) -> SportyBetDiscoveryPageEvidence:
    try:
        from domain.sportybet_lite_source_capture import parse_utc_timestamp
        return SportyBetDiscoveryPageEvidence(
            page_num=value["page_num"],
            request_target=value["request_target"],
            observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
            raw_file_name=value["raw_file_name"],
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            event_count=value["event_count"],
        )
    except Exception as exc:
        if isinstance(exc, SportyBetCurrentEventDiscoveryError):
            raise
        raise SportyBetCurrentEventDiscoveryError("discovery page manifest row is invalid") from exc


def _manifest_from_mapping(value: Any) -> SportyBetCurrentEventDiscoveryManifest:
    expected = {
        "schema_version", "dataset_name", "provider", "provider_region", "source_method",
        "origin", "sport_id", "page_size", "page_count", "pages", "event_count", "events",
        "observed_at", "observation_authority", "network_acquisition_performed", "authority",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SportyBetCurrentEventDiscoveryError("discovery manifest keys mismatch")
    if type(value["pages"]) is not list or type(value["events"]) is not list:
        raise SportyBetCurrentEventDiscoveryError("discovery manifest rows must be lists")
    from domain.sportybet_lite_source_capture import parse_utc_timestamp
    manifest = SportyBetCurrentEventDiscoveryManifest(
        schema_version=value["schema_version"],
        dataset_name=value["dataset_name"],
        provider=value["provider"],
        provider_region=value["provider_region"],
        source_method=value["source_method"],
        origin=value["origin"],
        sport_id=value["sport_id"],
        page_size=value["page_size"],
        pages=tuple(_page_from_mapping(item) for item in value["pages"]),
        events=tuple(_event_from_mapping(item) for item in value["events"]),
        observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
        observation_authority=value["observation_authority"],
        network_acquisition_performed=value["network_acquisition_performed"],
        authority=value["authority"],
    )
    if value["page_count"] != len(manifest.pages) or value["event_count"] != len(manifest.events):
        raise SportyBetCurrentEventDiscoveryError("discovery manifest counts mismatch")
    return manifest


def verify_current_event_discovery(
    evidence_directory: Path, *, repository_root: Path
) -> SportyBetCurrentEventDiscoveryManifest:
    validate_current_event_discovery_contract()
    root = _evidence_root(Path(repository_root), create=False)
    evidence = Path(evidence_directory)
    if ".." in evidence.parts:
        raise SportyBetCurrentEventDiscoveryError("discovery evidence path contains traversal")
    try:
        _reject_symlink_components(evidence, "discovery evidence directory")
        resolved = evidence.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError("discovery directory escapes reviewed root") from exc
    if evidence.is_symlink() or not evidence.is_dir():
        raise SportyBetCurrentEventDiscoveryError("discovery evidence must be a regular directory")
    manifest_raw = _read_regular(
        evidence / MANIFEST_FILENAME,
        maximum=MAX_MANIFEST_BYTES,
        label="SportyBet discovery manifest",
    )
    manifest = _manifest_from_mapping(live.strict_json_loads(manifest_raw))
    if manifest_raw != _manifest_bytes(manifest):
        raise SportyBetCurrentEventDiscoveryError("discovery manifest bytes are not canonical")
    expected_names = sorted([MANIFEST_FILENAME] + [item.raw_file_name for item in manifest.pages])
    if sorted(item.name for item in evidence.iterdir()) != expected_names:
        raise SportyBetCurrentEventDiscoveryError("discovery directory contents mismatch")
    rebuilt_by_id: dict[str, SportyBetDiscoveredEvent] = {}
    for page in manifest.pages:
        raw = _read_regular(
            evidence / page.raw_file_name,
            maximum=MAX_RESPONSE_BYTES,
            label="SportyBet discovery raw page",
        )
        if sha256_bytes(raw) != page.raw_sha256 or len(raw) != page.raw_size:
            raise SportyBetCurrentEventDiscoveryError("discovery raw page identity mismatch")
        rows = _extract_events(raw, page_num=page.page_num, observed_at=page.observed_at)
        if len(rows) != page.event_count:
            raise SportyBetCurrentEventDiscoveryError("discovery page event count mismatch")
        for row in rows:
            if row.event_id not in rebuilt_by_id:
                rebuilt_by_id[row.event_id] = row
    rebuilt = tuple(
        sorted(rebuilt_by_id.values(), key=lambda item: int(item.event_id.rsplit(":", 1)[1]))
    )
    if [item.to_dict() for item in rebuilt] != [item.to_dict() for item in manifest.events]:
        raise SportyBetCurrentEventDiscoveryError("discovered events do not replay from raw pages")
    if evidence.name != _capture_identifier(manifest):
        raise SportyBetCurrentEventDiscoveryError("discovery capture directory identity mismatch")
    return manifest


def _verified_handoff(value: Any) -> fotmob_handoff.FotMobFixtureCatalogHandoff:
    if type(value) is not fotmob_handoff.FotMobFixtureCatalogHandoff:
        raise SportyBetCurrentEventDiscoveryError(
            "fotmob_catalog_handoff must be exact FotMobFixtureCatalogHandoff"
        )
    try:
        rebuilt = fotmob_handoff.build_fotmob_fixture_catalog_handoff(
            value.candidate_bundle, value.review_bundle
        )
        expected = fotmob_handoff.canonical_fotmob_fixture_catalog_handoff_bytes(rebuilt)
        supplied = fotmob_handoff.canonical_fotmob_fixture_catalog_handoff_bytes(value)
    except Exception as exc:
        raise SportyBetCurrentEventDiscoveryError("FotMob handoff reconstruction failed") from exc
    if expected != supplied:
        raise SportyBetCurrentEventDiscoveryError("FotMob handoff differs from exact reconstruction")
    return rebuilt


@dataclass(frozen=True)
class SportyBetCurrentEventReconciliation:
    event_id: str
    disposition: CurrentEventReconciliationDisposition
    reason: str
    discovery_event_sha256: str
    matched_fotmob_fixture_id: str | None
    matched_home_team: str | None
    matched_away_team: str | None
    matched_competition: str | None
    matched_kickoff_utc: datetime | None
    direct_event_manifest_sha256: str | None
    direct_event_inventory_sha256: str | None
    direct_event_raw_sha256: str | None
    fixture_reconciliation_authorized: bool

    def __post_init__(self) -> None:
        _event_id(self.event_id)
        if type(self.disposition) is not CurrentEventReconciliationDisposition:
            raise SportyBetCurrentEventDiscoveryError("reconciliation disposition is invalid")
        _text(self.reason, "reconciliation reason", maximum=1000)
        _sha(self.discovery_event_sha256, "discovery_event_sha256")
        authorized = (
            self.disposition
            is CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
        )
        if self.fixture_reconciliation_authorized is not authorized:
            raise SportyBetCurrentEventDiscoveryError("reconciliation authority/disposition mismatch")
        if authorized:
            for label, value in (
                ("matched_fotmob_fixture_id", self.matched_fotmob_fixture_id),
                ("matched_home_team", self.matched_home_team),
                ("matched_away_team", self.matched_away_team),
                ("matched_competition", self.matched_competition),
            ):
                _text(value, label)
            if self.matched_kickoff_utc is None:
                raise SportyBetCurrentEventDiscoveryError("authorized reconciliation omitted kickoff")
            object.__setattr__(
                self, "matched_kickoff_utc", _utc(self.matched_kickoff_utc, "matched_kickoff_utc")
            )
            _sha(self.direct_event_manifest_sha256, "direct_event_manifest_sha256")
            _sha(self.direct_event_inventory_sha256, "direct_event_inventory_sha256")
            _sha(self.direct_event_raw_sha256, "direct_event_raw_sha256")
        else:
            if any(
                value is not None
                for value in (
                    self.matched_fotmob_fixture_id,
                    self.matched_home_team,
                    self.matched_away_team,
                    self.matched_competition,
                    self.matched_kickoff_utc,
                    self.direct_event_manifest_sha256,
                    self.direct_event_inventory_sha256,
                    self.direct_event_raw_sha256,
                )
            ):
                raise SportyBetCurrentEventDiscoveryError(
                    "unauthorized reconciliation must not retain promoted match/detail identity"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "disposition": self.disposition.value,
            "reason": self.reason,
            "discovery_event_sha256": self.discovery_event_sha256,
            "matched_fotmob_fixture_id": self.matched_fotmob_fixture_id,
            "matched_home_team": self.matched_home_team,
            "matched_away_team": self.matched_away_team,
            "matched_competition": self.matched_competition,
            "matched_kickoff_utc": (
                None if self.matched_kickoff_utc is None else serialize_utc(self.matched_kickoff_utc)
            ),
            "direct_event_manifest_sha256": self.direct_event_manifest_sha256,
            "direct_event_inventory_sha256": self.direct_event_inventory_sha256,
            "direct_event_raw_sha256": self.direct_event_raw_sha256,
            "fixture_reconciliation_authorized": self.fixture_reconciliation_authorized,
        }


def _unmatched(
    event: SportyBetDiscoveredEvent,
    disposition: CurrentEventReconciliationDisposition,
    reason: str,
) -> SportyBetCurrentEventReconciliation:
    return SportyBetCurrentEventReconciliation(
        event_id=event.event_id,
        disposition=disposition,
        reason=reason,
        discovery_event_sha256=event.canonical_sha256,
        matched_fotmob_fixture_id=None,
        matched_home_team=None,
        matched_away_team=None,
        matched_competition=None,
        matched_kickoff_utc=None,
        direct_event_manifest_sha256=None,
        direct_event_inventory_sha256=None,
        direct_event_raw_sha256=None,
        fixture_reconciliation_authorized=False,
    )


def _exact_matches(event: SportyBetDiscoveredEvent, handoff: fotmob_handoff.FotMobFixtureCatalogHandoff) -> tuple[Any, ...]:
    if event.competition_name is None:
        return ()
    return tuple(
        item
        for item in handoff.catalog_inputs
        if (
            item.home_team == event.home_team_name
            and item.away_team == event.away_team_name
            and item.competition == event.competition_name
            and _utc(item.kickoff, "FotMob kickoff") == event.kickoff_utc
        )
    )


def _reconcile_one(
    event: SportyBetDiscoveredEvent,
    *, handoff: fotmob_handoff.FotMobFixtureCatalogHandoff,
    repository_root: Path,
    execute_live_network: bool,
) -> tuple[SportyBetCurrentEventReconciliation, Path | None]:
    if not event.prematch_bookable_observed:
        return _unmatched(
            event,
            CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE,
            "discovered provider event is not currently observed as prematch/bookable",
        ), None
    if event.competition_name is None:
        return _unmatched(
            event,
            CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN,
            f"provider competition identity is not exact: {event.competition_basis}",
        ), None
    matches = _exact_matches(event, handoff)
    if not matches:
        return _unmatched(
            event,
            CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH,
            "no reviewed FotMob fixture exactly matches provider home/away/competition/full UTC",
        ), None
    if len(matches) != 1:
        return _unmatched(
            event,
            CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH,
            "multiple reviewed FotMob fixtures exactly match provider identity",
        ), None
    matched = matches[0]
    try:
        evidence_dir, detail_manifest = live.capture_live_event_quote_evidence(
            event_id=event.event_id,
            repository_root=repository_root,
            execute_live_network=execute_live_network,
        )
        inventory = live.build_live_event_quote_inventory(
            evidence_dir, repository_root=repository_root
        )
    except Exception:
        return _unmatched(
            event,
            CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED,
            "exact direct event-detail confirmation failed closed",
        ), None
    if (
        inventory.event_id != event.event_id
        or inventory.home_team_name != event.home_team_name
        or inventory.away_team_name != event.away_team_name
        or inventory.kickoff_utc != event.kickoff_utc
        or inventory.prematch_bookable_observed is not True
    ):
        return _unmatched(
            event,
            CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED,
            "direct event detail differs from discovery identity or is no longer prematch/bookable",
        ), None
    if inventory.observed_at >= inventory.kickoff_utc:
        return _unmatched(
            event,
            CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED,
            "direct event detail was observed at or after kickoff",
        ), None
    result = SportyBetCurrentEventReconciliation(
        event_id=event.event_id,
        disposition=(
            CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
        ),
        reason=(
            "unique exact reviewed FotMob identity confirmed by exact current direct-provider event detail"
        ),
        discovery_event_sha256=event.canonical_sha256,
        matched_fotmob_fixture_id=matched.source_fixture_identifier,
        matched_home_team=matched.home_team,
        matched_away_team=matched.away_team,
        matched_competition=matched.competition,
        matched_kickoff_utc=matched.kickoff,
        direct_event_manifest_sha256=live.manifest_sha256(detail_manifest),
        direct_event_inventory_sha256=inventory.canonical_sha256,
        direct_event_raw_sha256=detail_manifest.raw_sha256,
        fixture_reconciliation_authorized=True,
    )
    return result, evidence_dir


@dataclass(frozen=True, init=False)
class SportyBetCurrentEventDiscoveryReconciliationBundle:
    dataset_name: str
    status: str
    current_event_discovery_contract_sha256: str
    live_event_source_contract_sha256: str
    portfolio_optimizer_v2_contract_sha256: str
    discovery_manifest_sha256: str
    fotmob_handoff_sha256: str
    reconciliation_count: int
    authorized_reconciliation_count: int
    results: tuple[SportyBetCurrentEventReconciliation, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    _discovery_directory: Path
    _repository_root: Path
    _fotmob_handoff: fotmob_handoff.FotMobFixtureCatalogHandoff
    _event_evidence_directories: Mapping[str, Path]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetCurrentEventDiscoveryError(
            "reconciliation bundles are issued only by reviewed discovery/source replay"
        )

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "current_event_discovery_contract_sha256": self.current_event_discovery_contract_sha256,
            "live_event_source_contract_sha256": self.live_event_source_contract_sha256,
            "portfolio_optimizer_v2_contract_sha256": self.portfolio_optimizer_v2_contract_sha256,
            "discovery_manifest_sha256": self.discovery_manifest_sha256,
            "fotmob_handoff_sha256": self.fotmob_handoff_sha256,
            "reconciliation_count": self.reconciliation_count,
            "authorized_reconciliation_count": self.authorized_reconciliation_count,
            "results": [item.to_dict() for item in self.results],
            "matching_basis": MATCHING_BASIS,
            "detail_confirmation_policy": DETAIL_CONFIRMATION_POLICY,
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_catalog_handoff: fotmob_handoff.FotMobFixtureCatalogHandoff,
    execute_live_network: bool,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    """Discover current SportyBet football events and authorize only exact confirmed matches."""
    identities = validate_current_event_discovery_contract()
    verified_handoff = _verified_handoff(fotmob_catalog_handoff)
    discovery_directory, discovery = capture_current_event_discovery(
        repository_root=repository_root,
        execute_live_network=execute_live_network,
    )
    results: list[SportyBetCurrentEventReconciliation] = []
    detail_dirs: dict[str, Path] = {}
    for event in discovery.events:
        result, detail_dir = _reconcile_one(
            event,
            handoff=verified_handoff,
            repository_root=repository_root,
            execute_live_network=execute_live_network,
        )
        results.append(result)
        if detail_dir is not None:
            detail_dirs[event.event_id] = detail_dir
    ordered = tuple(sorted(results, key=lambda item: int(item.event_id.rsplit(":", 1)[1])))
    value = object.__new__(SportyBetCurrentEventDiscoveryReconciliationBundle)
    return _set_frozen(
        value,
        {
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "current_event_discovery_contract_sha256": identities[
                "current_event_discovery_contract_sha256"
            ],
            "live_event_source_contract_sha256": identities[
                "live_event_source_contract_sha256"
            ],
            "portfolio_optimizer_v2_contract_sha256": identities[
                "portfolio_optimizer_v2_contract_sha256"
            ],
            "discovery_manifest_sha256": discovery.canonical_sha256,
            "fotmob_handoff_sha256": fotmob_handoff.sha256_fotmob_fixture_catalog_handoff(
                verified_handoff
            ),
            "reconciliation_count": len(ordered),
            "authorized_reconciliation_count": sum(
                1 for item in ordered if item.fixture_reconciliation_authorized
            ),
            "results": ordered,
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_discovery_directory": discovery_directory,
            "_repository_root": Path(repository_root),
            "_fotmob_handoff": verified_handoff,
            "_event_evidence_directories": types.MappingProxyType(dict(detail_dirs)),
        },
    )


def verify_current_event_discovery_reconciliation_bundle(
    value: SportyBetCurrentEventDiscoveryReconciliationBundle,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    """Rebuild the bundle without network from exact retained discovery/detail evidence."""
    if type(value) is not SportyBetCurrentEventDiscoveryReconciliationBundle:
        raise SportyBetCurrentEventDiscoveryError(
            "value must be exact SportyBetCurrentEventDiscoveryReconciliationBundle"
        )
    identities = validate_current_event_discovery_contract()
    handoff = _verified_handoff(value._fotmob_handoff)
    discovery = verify_current_event_discovery(
        value._discovery_directory, repository_root=value._repository_root
    )
    rebuilt_results: list[SportyBetCurrentEventReconciliation] = []
    for event in discovery.events:
        if not event.prematch_bookable_observed:
            rebuilt_results.append(
                _unmatched(
                    event,
                    CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE,
                    "discovered provider event is not currently observed as prematch/bookable",
                )
            )
            continue
        if event.competition_name is None:
            rebuilt_results.append(
                _unmatched(
                    event,
                    CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN,
                    f"provider competition identity is not exact: {event.competition_basis}",
                )
            )
            continue
        matches = _exact_matches(event, handoff)
        if not matches:
            rebuilt_results.append(
                _unmatched(
                    event,
                    CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH,
                    "no reviewed FotMob fixture exactly matches provider home/away/competition/full UTC",
                )
            )
            continue
        if len(matches) != 1:
            rebuilt_results.append(
                _unmatched(
                    event,
                    CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH,
                    "multiple reviewed FotMob fixtures exactly match provider identity",
                )
            )
            continue
        evidence_dir = value._event_evidence_directories.get(event.event_id)
        if evidence_dir is None:
            rebuilt_results.append(
                _unmatched(
                    event,
                    CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED,
                    "exact direct event-detail confirmation failed closed",
                )
            )
            continue
        try:
            detail_manifest = live.verify_live_event_quote_evidence(
                evidence_dir, repository_root=value._repository_root
            )
            inventory = live.build_live_event_quote_inventory(
                evidence_dir, repository_root=value._repository_root
            )
        except Exception:
            rebuilt_results.append(
                _unmatched(
                    event,
                    CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED,
                    "exact direct event-detail confirmation failed closed",
                )
            )
            continue
        if (
            inventory.event_id != event.event_id
            or inventory.home_team_name != event.home_team_name
            or inventory.away_team_name != event.away_team_name
            or inventory.kickoff_utc != event.kickoff_utc
            or inventory.prematch_bookable_observed is not True
            or inventory.observed_at >= inventory.kickoff_utc
        ):
            rebuilt_results.append(
                _unmatched(
                    event,
                    CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED,
                    "direct event detail differs from discovery identity or is no longer prematch/bookable",
                )
            )
            continue
        matched = matches[0]
        rebuilt_results.append(
            SportyBetCurrentEventReconciliation(
                event_id=event.event_id,
                disposition=(
                    CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
                ),
                reason=(
                    "unique exact reviewed FotMob identity confirmed by exact current direct-provider event detail"
                ),
                discovery_event_sha256=event.canonical_sha256,
                matched_fotmob_fixture_id=matched.source_fixture_identifier,
                matched_home_team=matched.home_team,
                matched_away_team=matched.away_team,
                matched_competition=matched.competition,
                matched_kickoff_utc=matched.kickoff,
                direct_event_manifest_sha256=live.manifest_sha256(detail_manifest),
                direct_event_inventory_sha256=inventory.canonical_sha256,
                direct_event_raw_sha256=detail_manifest.raw_sha256,
                fixture_reconciliation_authorized=True,
            )
        )
    ordered = tuple(
        sorted(rebuilt_results, key=lambda item: int(item.event_id.rsplit(":", 1)[1]))
    )
    rebuilt = object.__new__(SportyBetCurrentEventDiscoveryReconciliationBundle)
    rebuilt = _set_frozen(
        rebuilt,
        {
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "current_event_discovery_contract_sha256": identities[
                "current_event_discovery_contract_sha256"
            ],
            "live_event_source_contract_sha256": identities[
                "live_event_source_contract_sha256"
            ],
            "portfolio_optimizer_v2_contract_sha256": identities[
                "portfolio_optimizer_v2_contract_sha256"
            ],
            "discovery_manifest_sha256": discovery.canonical_sha256,
            "fotmob_handoff_sha256": fotmob_handoff.sha256_fotmob_fixture_catalog_handoff(
                handoff
            ),
            "reconciliation_count": len(ordered),
            "authorized_reconciliation_count": sum(
                1 for item in ordered if item.fixture_reconciliation_authorized
            ),
            "results": ordered,
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_discovery_directory": value._discovery_directory,
            "_repository_root": value._repository_root,
            "_fotmob_handoff": handoff,
            "_event_evidence_directories": value._event_evidence_directories,
        },
    )
    if rebuilt.to_dict() != value.to_dict():
        raise SportyBetCurrentEventDiscoveryError(
            "current event discovery/reconciliation bundle differs from exact source replay"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
