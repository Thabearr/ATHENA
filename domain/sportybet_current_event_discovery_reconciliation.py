"""Current SportyBet football-event discovery with source-replayed FotMob reconciliation.

This boundary discovers current SportyBet football event IDs from one anonymous
read-only FactsCenter endpoint, preserves every response page, and reconciles
only exact case-sensitive home/away/competition/full-UTC identities against a
reviewed FotMob catalog that is re-derived from the exact raw FotMob captures
and explicit review decisions.

A unique match is additionally confirmed through the reviewed PR #246 direct
SportyBet event-detail source. Currentness is checked at issuance time for both
the discovery observation and direct event-detail observation. The boundary
issues fixture-reconciliation authority only. It does not map canonical markets,
compute value, route, optimize, construct a slip, stake, execute, or place a bet.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import types
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from domain import _portfolio_optimizer_v2_direct_provider_contracts as portfolio_v2_contracts
from domain import current_fotmob_fixture_candidate_adapter as current_fotmob_candidates
from domain import fotmob_fixture_candidate_review as fotmob_review
from domain import fotmob_fixture_candidates as fotmob_candidates
from domain import fotmob_fixture_catalog_handoff as fotmob_handoff
from domain import reviewed_fixture_catalog_admission as fotmob_admission
from domain import sportybet_live_event_quote_evidence as live
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as FOTMOB_CAPTURE_DATASET_NAME,
    SCHEMA_VERSION as FOTMOB_CAPTURE_SCHEMA_VERSION,
    FotMobDataMatchesCaptureManifest,
    sha256_bytes as fotmob_sha256_bytes,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput
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
PAGINATION_TERMINATION_POLICY = (
    "EMPTY_PAGE_OR_SHORT_PAGE_BELOW_REQUESTED_PAGE_SIZE_V2"
)
PAGINATION_TERMINATION_EMPTY_PAGE = "EMPTY_PAGE"
PAGINATION_TERMINATION_SHORT_PAGE = "SHORT_PAGE_BELOW_REQUESTED_PAGE_SIZE"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SOURCE_AGE_SECONDS = 900
MINIMUM_LEAD_SECONDS = 120
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
PAGE_FILENAME_TEMPLATE = "page-{page_num:03d}.json"
OBSERVATION_AUTHORITY = (
    "ATHENA_DIRECT_PROVIDER_DISCOVERY_RESPONSE_COMPLETION_NOT_PROVIDER_EVENT_TIMESTAMP"
)
MATCHING_BASIS = (
    "EXACT_CASE_SENSITIVE_HOME_AWAY_COMPETITION_FULL_UTC_"
    "NO_ALIAS_NO_FUZZY_NO_REVERSAL_NO_ROUNDING_NO_TOLERANCE"
)
DETAIL_CONFIRMATION_POLICY = (
    "EXACT_PR246_EVENT_GET_REPLAY_REQUIRED_BEFORE_FIXTURE_RECONCILIATION_AUTHORITY"
)
FOTMOB_SOURCE_REPLAY_POLICY = (
    "RAW_FOTMOB_CAPTURE_PLUS_EXPLICIT_REVIEW_PLUS_ADMITTED_CATALOG_REDERIVATION_REQUIRED"
)
PORTFOLIO_OPTIMIZER_V2_CONTRACT_SHA256 = (
    "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd"
)
LIVE_EVENT_SOURCE_CONTRACT_SHA256 = (
    "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
)
NEXT_BOUNDARY = "CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED"
EXPECTED_CONTRACT_SHA256 = (
    "64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee"
)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

CONTRACT_AUTHORITY = types.MappingProxyType(
    {
        "current_event_discovery_issuer": True,
        "current_event_detail_confirmation_issuer": True,
        "fixture_reconciliation_issuer": True,
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
    """Raised when current SportyBet event discovery/reconciliation fails closed."""


class CurrentEventReconciliationDisposition(str, enum.Enum):
    UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED = (
        "UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED"
    )
    DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE = "DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE"
    PROVIDER_COMPETITION_UNPROVEN = "PROVIDER_COMPETITION_UNPROVEN"
    DISCOVERY_EVIDENCE_STALE = "DISCOVERY_EVIDENCE_STALE"
    PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF = "PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF"
    NO_EXACT_REVIEWED_FOTMOB_MATCH = "NO_EXACT_REVIEWED_FOTMOB_MATCH"
    AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH = "AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH"
    AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE = "AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE"
    DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH = "DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH"
    DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE = (
        "DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE"
    )
    DIRECT_EVENT_DETAIL_STALE = "DIRECT_EVENT_DETAIL_STALE"


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
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
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
    return _text(str(value), label, maximum=maximum)


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
        raise SportyBetCurrentEventDiscoveryError(
            "page_num is outside reviewed pagination bounds"
        )
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
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "matching_basis": MATCHING_BASIS,
        "detail_confirmation_policy": DETAIL_CONFIRMATION_POLICY,
        "fotmob_source_replay_policy": FOTMOB_SOURCE_REPLAY_POLICY,
        "portfolio_optimizer_v2_contract_sha256": (
            PORTFOLIO_OPTIMIZER_V2_CONTRACT_SHA256
        ),
        "live_event_source_contract_sha256": LIVE_EVENT_SOURCE_CONTRACT_SHA256,
        "fotmob_admission_dataset_name": fotmob_admission.DATASET_NAME,
        "fotmob_admission_schema_version": fotmob_admission.SCHEMA_VERSION,
        "fotmob_capture_dataset_name": FOTMOB_CAPTURE_DATASET_NAME,
        "fotmob_capture_schema_version": FOTMOB_CAPTURE_SCHEMA_VERSION,
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(CONTRACT_AUTHORITY),
    }


def calculate_current_event_discovery_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {"version": CONTRACT_VERSION, "semantics": _contract_payload()},
            newline=False,
        )
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
    if (fotmob_admission.DATASET_NAME, fotmob_admission.SCHEMA_VERSION) != (
        "athena-reviewed-fixture-catalog-admission-v1",
        1,
    ):
        raise SportyBetCurrentEventDiscoveryError(
            "reviewed FotMob admission identity drifted"
        )
    if (FOTMOB_CAPTURE_DATASET_NAME, FOTMOB_CAPTURE_SCHEMA_VERSION) != (
        "athena-fotmob-data-matches-capture-v1",
        1,
    ):
        raise SportyBetCurrentEventDiscoveryError("FotMob raw capture identity drifted")
    if (
        live.MAX_OBSERVATION_AGE_SECONDS != MAX_SOURCE_AGE_SECONDS
        or live.MINIMUM_LEAD_SECONDS != MINIMUM_LEAD_SECONDS
    ):
        raise SportyBetCurrentEventDiscoveryError(
            "PR246 freshness/kickoff policy drifted"
        )
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
        raise SportyBetCurrentEventDiscoveryError(
            "discovered estimateStartTime is invalid"
        )
    try:
        return datetime.fromtimestamp(number / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "discovered estimateStartTime is out of range"
        ) from exc


def _event_is_prematch_bookable(event: Mapping[str, Any]) -> bool:
    if str(event.get("bookingStatus") or "").strip().casefold() == "unavailable":
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
        return _text(str(tournament.get("name")), "provider nested tournament name")
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
            values.append((_text(str(event.get(key)), f"provider {key}"), basis))
    nested = _nested_competition(event)
    if nested is not None:
        values.append((nested, "EVENT_NESTED_TOURNAMENT_NAME"))
    unique = {name for name, _basis in values}
    if not unique:
        return None, "PROVIDER_COMPETITION_UNAVAILABLE"
    if len(unique) != 1:
        return None, "PROVIDER_COMPETITION_CONFLICTED"
    name = next(iter(unique))
    bases = "+".join(sorted({basis for _name, basis in values}))
    return name, bases


@dataclasses.dataclass(frozen=True)
class SportyBetDiscoveryPage:
    page_num: int
    request_target: str
    observed_at: datetime
    raw_sha256: str
    raw_size: int
    event_count: int

    def __post_init__(self) -> None:
        if type(self.page_num) is not int or not 1 <= self.page_num <= MAX_PAGES:
            raise SportyBetCurrentEventDiscoveryError("discovery page_num is invalid")
        if self.request_target != request_target(self.page_num):
            raise SportyBetCurrentEventDiscoveryError("discovery request_target mismatch")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "page observed_at"))
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
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "event_count": self.event_count,
        }


@dataclasses.dataclass(frozen=True)
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
            raise SportyBetCurrentEventDiscoveryError(
                "discovered home/away teams must differ"
            )
        if self.competition_name is not None:
            _text(self.competition_name, "competition_name")
        _text(self.competition_basis, "competition_basis")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        if self.booking_status is not None:
            _text(self.booking_status, "booking_status")
        if self.match_status is not None:
            _text(self.match_status, "match_status")
        if type(self.prematch_bookable_observed) is not bool:
            raise SportyBetCurrentEventDiscoveryError(
                "prematch_bookable_observed must be bool"
            )
        if type(self.source_page_num) is not int or not 1 <= self.source_page_num <= MAX_PAGES:
            raise SportyBetCurrentEventDiscoveryError("source_page_num is invalid")
        _sha(self.source_raw_sha256, "source_raw_sha256")
        object.__setattr__(
            self,
            "source_observed_at",
            _utc(self.source_observed_at, "source_observed_at"),
        )

    @property
    def identity_payload(self) -> dict[str, Any]:
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
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity_payload,
            "source_page_num": self.source_page_num,
            "source_raw_sha256": self.source_raw_sha256,
            "source_observed_at": serialize_utc(self.source_observed_at),
        }


@dataclasses.dataclass(frozen=True)
class SportyBetCurrentEventDiscoveryManifest:
    schema_version: int
    dataset_name: str
    provider: str
    provider_region: str
    source_method: str
    football_sport_id: str
    pages: tuple[SportyBetDiscoveryPage, ...]
    events: tuple[SportyBetDiscoveredEvent, ...]
    first_observed_at: datetime
    last_observed_at: datetime
    observation_authority: str
    provider_event_timestamp: None
    provider_snapshot_id: None
    terminal_empty_page_observed: bool
    pagination_termination_basis: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or type(self.schema_version) is not int:
            raise SportyBetCurrentEventDiscoveryError("discovery schema_version mismatch")
        if self.dataset_name != DISCOVERY_DATASET_NAME:
            raise SportyBetCurrentEventDiscoveryError("discovery dataset_name mismatch")
        if self.provider != PROVIDER or self.provider_region != PROVIDER_REGION:
            raise SportyBetCurrentEventDiscoveryError("discovery provider identity mismatch")
        if self.source_method != DISCOVERY_SOURCE_METHOD:
            raise SportyBetCurrentEventDiscoveryError("discovery source_method mismatch")
        if self.football_sport_id != FOOTBALL_SPORT_ID:
            raise SportyBetCurrentEventDiscoveryError("discovery sport identity mismatch")
        if type(self.pages) is not tuple or not self.pages:
            raise SportyBetCurrentEventDiscoveryError("discovery pages must be non-empty tuple")
        if any(type(item) is not SportyBetDiscoveryPage for item in self.pages):
            raise SportyBetCurrentEventDiscoveryError("discovery pages contain invalid item")
        if tuple(item.page_num for item in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise SportyBetCurrentEventDiscoveryError("discovery pages must be contiguous from page 1")
        if type(self.events) is not tuple or any(
            type(item) is not SportyBetDiscoveredEvent for item in self.events
        ):
            raise SportyBetCurrentEventDiscoveryError("discovery events must be immutable tuple")
        ids = tuple(item.event_id for item in self.events)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise SportyBetCurrentEventDiscoveryError(
                "discovery events must be sorted and unique by event_id"
            )
        first = _utc(self.first_observed_at, "first_observed_at")
        last = _utc(self.last_observed_at, "last_observed_at")
        if first != min(item.observed_at for item in self.pages) or last != max(
            item.observed_at for item in self.pages
        ):
            raise SportyBetCurrentEventDiscoveryError(
                "discovery observation envelope does not match page observations"
            )
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetCurrentEventDiscoveryError("discovery observation authority mismatch")
        if self.provider_event_timestamp is not None or self.provider_snapshot_id is not None:
            raise SportyBetCurrentEventDiscoveryError(
                "discovery cannot invent provider event timestamp/snapshot identity"
            )
        last_event_count = self.pages[-1].event_count
        if self.pagination_termination_basis == PAGINATION_TERMINATION_EMPTY_PAGE:
            if self.terminal_empty_page_observed is not True or last_event_count != 0:
                raise SportyBetCurrentEventDiscoveryError(
                    "empty-page termination basis does not match the final page"
                )
        elif self.pagination_termination_basis == PAGINATION_TERMINATION_SHORT_PAGE:
            if (
                self.terminal_empty_page_observed is not False
                or not 0 < last_event_count < PAGE_SIZE
            ):
                raise SportyBetCurrentEventDiscoveryError(
                    "short-page termination basis does not match the final page"
                )
        else:
            raise SportyBetCurrentEventDiscoveryError(
                "discovery pagination termination basis is not reviewed"
            )
        object.__setattr__(self, "first_observed_at", first)
        object.__setattr__(self, "last_observed_at", last)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "provider_region": self.provider_region,
            "source_method": self.source_method,
            "football_sport_id": self.football_sport_id,
            "pages": [item.to_dict() for item in self.pages],
            "events": [item.to_dict() for item in self.events],
            "first_observed_at": serialize_utc(self.first_observed_at),
            "last_observed_at": serialize_utc(self.last_observed_at),
            "observation_authority": self.observation_authority,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
            "terminal_empty_page_observed": self.terminal_empty_page_observed,
            "pagination_termination_basis": self.pagination_termination_basis,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()


def _extract_page_events(payload: Any, *, page: SportyBetDiscoveryPage | None = None) -> list[tuple[dict[str, Any], str | None]]:
    if type(payload) is not dict or payload.get("bizCode") != 10000:
        raise SportyBetCurrentEventDiscoveryError(
            "SportyBet discovery response must be a successful object"
        )
    data = payload.get("data")
    collected: list[tuple[dict[str, Any], str | None]] = []
    visited = 0

    def walk(value: Any, inherited: str | None, depth: int) -> None:
        nonlocal visited
        visited += 1
        if visited > 20_000 or depth > 5:
            raise SportyBetCurrentEventDiscoveryError(
                "SportyBet discovery response nesting is excessive"
            )
        if type(value) is list:
            for item in value:
                walk(item, inherited, depth + 1)
            return
        if type(value) is not dict:
            return
        if value.get("eventId") is not None:
            collected.append((value, inherited))
            return
        envelope_name = inherited
        for key in ("name", "tournamentName", "competitionName", "leagueName"):
            if value.get(key) is not None:
                candidate = _text(str(value.get(key)), f"provider envelope {key}")
                if envelope_name is not None and envelope_name != candidate:
                    envelope_name = None
                else:
                    envelope_name = candidate
                break
        child_keys = [key for key in ("events", "tournaments", "groups", "items") if key in value]
        if not child_keys:
            return
        for key in child_keys:
            child = value.get(key)
            if type(child) is not list:
                raise SportyBetCurrentEventDiscoveryError(
                    f"provider discovery {key} must be a list"
                )
            walk(child, envelope_name, depth + 1)

    if type(data) not in (list, dict):
        raise SportyBetCurrentEventDiscoveryError("provider discovery data shape is invalid")
    walk(data, None, 0)
    return collected


def _event_from_mapping(
    value: Mapping[str, Any],
    *,
    inherited_competition: str | None,
    page_num: int,
    raw_sha256: str,
    observed_at: datetime,
) -> SportyBetDiscoveredEvent:
    if value.get("sportId") not in (None, FOOTBALL_SPORT_ID):
        raise SportyBetCurrentEventDiscoveryError(
            "football-scoped discovery returned a non-football event"
        )
    competition_name, basis = _competition(value, inherited_competition)
    return SportyBetDiscoveredEvent(
        event_id=_event_id(value.get("eventId")),
        home_team_name=_text(str(value.get("homeTeamName")), "provider home team"),
        away_team_name=_text(str(value.get("awayTeamName")), "provider away team"),
        competition_name=competition_name,
        competition_basis=basis,
        kickoff_utc=_kickoff(value.get("estimateStartTime")),
        booking_status=_optional_text(value.get("bookingStatus"), "booking_status"),
        event_status=value.get("status"),
        match_status=_optional_text(value.get("matchStatus"), "match_status"),
        prematch_bookable_observed=_event_is_prematch_bookable(value),
        source_page_num=page_num,
        source_raw_sha256=raw_sha256,
        source_observed_at=observed_at,
    )


def _parse_page(raw: bytes, *, page_num: int, observed_at: datetime) -> tuple[SportyBetDiscoveryPage, tuple[SportyBetDiscoveredEvent, ...]]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise SportyBetCurrentEventDiscoveryError(
            "discovery page must be bounded non-empty exact bytes"
        )
    try:
        payload = live.strict_json_loads(raw)
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise SportyBetCurrentEventDiscoveryError(str(exc)) from exc
    raw_hash = sha256_bytes(raw)
    extracted = _extract_page_events(payload)
    events = tuple(
        _event_from_mapping(
            event,
            inherited_competition=inherited,
            page_num=page_num,
            raw_sha256=raw_hash,
            observed_at=observed_at,
        )
        for event, inherited in extracted
    )
    page = SportyBetDiscoveryPage(
        page_num=page_num,
        request_target=request_target(page_num),
        observed_at=observed_at,
        raw_sha256=raw_hash,
        raw_size=len(raw),
        event_count=len(events),
    )
    return page, events


def _dedupe_events(events: Sequence[SportyBetDiscoveredEvent]) -> tuple[SportyBetDiscoveredEvent, ...]:
    by_id: dict[str, SportyBetDiscoveredEvent] = {}
    for event in events:
        existing = by_id.get(event.event_id)
        if existing is None:
            by_id[event.event_id] = event
            continue
        if existing.identity_payload != event.identity_payload:
            raise SportyBetCurrentEventDiscoveryError(
                f"conflicting duplicate provider event identity: {event.event_id}"
            )
        # Keep the newest exact duplicate so freshness is not understated.
        if event.source_observed_at > existing.source_observed_at:
            by_id[event.event_id] = event
    return tuple(by_id[key] for key in sorted(by_id))


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
    observed_at = _now_utc()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SportyBetCurrentEventDiscoveryError(
            "SportyBet discovery response exceeds byte bound"
        )
    if status != 200:
        raise SportyBetCurrentEventDiscoveryError(
            f"SportyBet discovery returned HTTP {status}"
        )
    return raw, status, observed_at


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
        _reject_symlink_components(root, "current event discovery evidence root")
        if create:
            _ensure_directory_tree_durable(root, boundary=repository)
        else:
            resolved = root.resolve(strict=True)
            resolved.relative_to(repository)
            if resolved.is_symlink() or not resolved.is_dir():
                raise SportyBetCurrentEventDiscoveryError(
                    "discovery evidence root must be a non-symlink directory"
                )
    except SportyBetCurrentEventDiscoveryError:
        raise
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "current event discovery evidence root is invalid"
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


def _manifest_from_mapping(value: Any) -> SportyBetCurrentEventDiscoveryManifest:
    expected = {
        "schema_version",
        "dataset_name",
        "provider",
        "provider_region",
        "source_method",
        "football_sport_id",
        "pages",
        "events",
        "first_observed_at",
        "last_observed_at",
        "observation_authority",
        "provider_event_timestamp",
        "provider_snapshot_id",
        "terminal_empty_page_observed",
        "pagination_termination_basis",
    }
    if type(value) is not dict or set(value) != expected:
        raise SportyBetCurrentEventDiscoveryError("discovery manifest keys mismatch")
    pages_raw = value["pages"]
    events_raw = value["events"]
    if type(pages_raw) is not list or type(events_raw) is not list:
        raise SportyBetCurrentEventDiscoveryError("discovery manifest arrays are invalid")
    try:
        pages = tuple(
            SportyBetDiscoveryPage(
                page_num=item["page_num"],
                request_target=item["request_target"],
                observed_at=parse_utc_timestamp(item["observed_at"], "page observed_at"),
                raw_sha256=item["raw_sha256"],
                raw_size=item["raw_size"],
                event_count=item["event_count"],
            )
            for item in pages_raw
        )
        events = tuple(
            SportyBetDiscoveredEvent(
                event_id=item["event_id"],
                home_team_name=item["home_team_name"],
                away_team_name=item["away_team_name"],
                competition_name=item["competition_name"],
                competition_basis=item["competition_basis"],
                kickoff_utc=parse_utc_timestamp(item["kickoff_utc"], "event kickoff_utc"),
                booking_status=item["booking_status"],
                event_status=item["event_status"],
                match_status=item["match_status"],
                prematch_bookable_observed=item["prematch_bookable_observed"],
                source_page_num=item["source_page_num"],
                source_raw_sha256=item["source_raw_sha256"],
                source_observed_at=parse_utc_timestamp(
                    item["source_observed_at"], "event source_observed_at"
                ),
            )
            for item in events_raw
        )
        return SportyBetCurrentEventDiscoveryManifest(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            provider=value["provider"],
            provider_region=value["provider_region"],
            source_method=value["source_method"],
            football_sport_id=value["football_sport_id"],
            pages=pages,
            events=events,
            first_observed_at=parse_utc_timestamp(
                value["first_observed_at"], "first_observed_at"
            ),
            last_observed_at=parse_utc_timestamp(
                value["last_observed_at"], "last_observed_at"
            ),
            observation_authority=value["observation_authority"],
            provider_event_timestamp=value["provider_event_timestamp"],
            provider_snapshot_id=value["provider_snapshot_id"],
            terminal_empty_page_observed=value["terminal_empty_page_observed"],
            pagination_termination_basis=value["pagination_termination_basis"],
        )
    except (KeyError, TypeError, ValueError, SportyBetLiteCaptureError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "discovery manifest is invalid"
        ) from exc


def capture_current_event_discovery(
    *, repository_root: Path, execute_live_network: bool
) -> tuple[Path, SportyBetCurrentEventDiscoveryManifest]:
    validate_current_event_discovery_contract()
    if execute_live_network is not True:
        raise SportyBetCurrentEventDiscoveryError(
            "live current-event discovery requires exact execute_live_network=True"
        )
    page_rows: list[SportyBetDiscoveryPage] = []
    all_events: list[SportyBetDiscoveredEvent] = []
    raw_pages: list[bytes] = []
    termination_basis: str | None = None
    for page_num in range(1, MAX_PAGES + 1):
        raw, status, observed_at = _network_fetch_page(page_num)
        if status != 200:
            raise SportyBetCurrentEventDiscoveryError(
                f"SportyBet discovery returned HTTP {status}"
            )
        page, events = _parse_page(raw, page_num=page_num, observed_at=observed_at)
        page_rows.append(page)
        all_events.extend(events)
        raw_pages.append(raw)
        if not events:
            termination_basis = PAGINATION_TERMINATION_EMPTY_PAGE
            break
        if len(events) < PAGE_SIZE:
            termination_basis = PAGINATION_TERMINATION_SHORT_PAGE
            break
    if termination_basis is None:
        raise SportyBetCurrentEventDiscoveryError(
            "discovery pagination reached reviewed maximum without an empty or short terminal page"
        )
    manifest = SportyBetCurrentEventDiscoveryManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DISCOVERY_DATASET_NAME,
        provider=PROVIDER,
        provider_region=PROVIDER_REGION,
        source_method=DISCOVERY_SOURCE_METHOD,
        football_sport_id=FOOTBALL_SPORT_ID,
        pages=tuple(page_rows),
        events=_dedupe_events(all_events),
        first_observed_at=min(item.observed_at for item in page_rows),
        last_observed_at=max(item.observed_at for item in page_rows),
        observation_authority=OBSERVATION_AUTHORITY,
        provider_event_timestamp=None,
        provider_snapshot_id=None,
        terminal_empty_page_observed=(
            termination_basis == PAGINATION_TERMINATION_EMPTY_PAGE
        ),
        pagination_termination_basis=termination_basis,
    )
    root = _evidence_root(Path(repository_root), create=True)
    directory = root / manifest.canonical_sha256[:24]
    manifest_bytes = _canonical_bytes(manifest.to_dict(), newline=True)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise SportyBetCurrentEventDiscoveryError("discovery manifest exceeds byte bound")
    if directory.exists():
        existing = verify_current_event_discovery(
            directory, repository_root=Path(repository_root)
        )
        if existing.to_dict() != manifest.to_dict():
            raise SportyBetCurrentEventDiscoveryError("discovery capture identity collision")
        return directory, existing
    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(directory)
        for page, raw in zip(page_rows, raw_pages, strict=True):
            _write_exclusive(
                directory / PAGE_FILENAME_TEMPLATE.format(page_num=page.page_num),
                raw,
            )
        _write_exclusive(directory / MANIFEST_FILENAME, manifest_bytes)
        verified = verify_current_event_discovery(
            directory, repository_root=Path(repository_root)
        )
        _sync_directory(directory)
        _sync_directory(root)
        return directory, verified
    except Exception:
        raise


def verify_current_event_discovery(
    evidence_directory: Path, *, repository_root: Path
) -> SportyBetCurrentEventDiscoveryManifest:
    validate_current_event_discovery_contract()
    root = _evidence_root(Path(repository_root), create=False)
    evidence = Path(evidence_directory)
    if ".." in evidence.parts:
        raise SportyBetCurrentEventDiscoveryError(
            "discovery evidence path must not contain traversal"
        )
    try:
        _reject_symlink_components(evidence, "discovery evidence directory")
        resolved = evidence.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "discovery evidence directory escapes reviewed root"
        ) from exc
    if evidence.is_symlink() or not evidence.is_dir():
        raise SportyBetCurrentEventDiscoveryError(
            "discovery evidence must be a regular directory"
        )
    try:
        manifest_raw = _read_regular(
            evidence / MANIFEST_FILENAME,
            maximum=MAX_MANIFEST_BYTES,
            label="current event discovery manifest",
        )
    except SportyBetLiteCaptureError as exc:
        raise SportyBetCurrentEventDiscoveryError(str(exc)) from exc
    try:
        manifest = _manifest_from_mapping(live.strict_json_loads(manifest_raw))
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise SportyBetCurrentEventDiscoveryError(str(exc)) from exc
    if manifest_raw != _canonical_bytes(manifest.to_dict(), newline=True):
        raise SportyBetCurrentEventDiscoveryError("discovery manifest bytes are not canonical")
    expected_names = {MANIFEST_FILENAME} | {
        PAGE_FILENAME_TEMPLATE.format(page_num=item.page_num) for item in manifest.pages
    }
    if {item.name for item in evidence.iterdir()} != expected_names:
        raise SportyBetCurrentEventDiscoveryError("discovery directory contents mismatch")
    rebuilt_events: list[SportyBetDiscoveredEvent] = []
    for page in manifest.pages:
        path = evidence / PAGE_FILENAME_TEMPLATE.format(page_num=page.page_num)
        try:
            raw = _read_regular(
                path,
                maximum=MAX_RESPONSE_BYTES,
                label=f"current event discovery page {page.page_num}",
            )
        except SportyBetLiteCaptureError as exc:
            raise SportyBetCurrentEventDiscoveryError(str(exc)) from exc
        if sha256_bytes(raw) != page.raw_sha256 or len(raw) != page.raw_size:
            raise SportyBetCurrentEventDiscoveryError("discovery raw page identity mismatch")
        rebuilt_page, events = _parse_page(
            raw,
            page_num=page.page_num,
            observed_at=page.observed_at,
        )
        if rebuilt_page != page:
            raise SportyBetCurrentEventDiscoveryError(
                "discovery page metadata differs from exact raw replay"
            )
        rebuilt_events.extend(events)
    if _dedupe_events(rebuilt_events) != manifest.events:
        raise SportyBetCurrentEventDiscoveryError(
            "discovery events differ from exact raw page replay"
        )
    if evidence.name != manifest.canonical_sha256[:24]:
        raise SportyBetCurrentEventDiscoveryError("discovery directory identity mismatch")
    return manifest


def _materialize_fotmob_captures(
    captures: Any,
) -> tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...]:
    if not isinstance(captures, Sequence) or isinstance(captures, (str, bytes)) or not captures:
        raise SportyBetCurrentEventDiscoveryError(
            "fotmob_captures must be a non-empty sequence of exact (bytes, manifest) tuples"
        )
    rows: list[tuple[bytes, FotMobDataMatchesCaptureManifest]] = []
    for entry in captures:
        if type(entry) is not tuple or len(entry) != 2:
            raise SportyBetCurrentEventDiscoveryError(
                "each FotMob capture must be an exact (bytes, manifest) tuple"
            )
        raw, manifest = entry
        if type(raw) is not bytes or type(manifest) is not FotMobDataMatchesCaptureManifest:
            raise SportyBetCurrentEventDiscoveryError(
                "FotMob capture entries require exact raw bytes and capture manifests"
            )
        if manifest.raw_sha256 != fotmob_sha256_bytes(raw) or manifest.raw_size != len(raw):
            raise SportyBetCurrentEventDiscoveryError(
                "FotMob raw capture does not match its exact manifest identity"
            )
        rows.append((raw, manifest))
    return tuple(rows)


def _build_replayed_fotmob_candidates(
    capture_rows: Any,
) -> fotmob_candidates.FotMobFixtureCandidateBundle:
    """Replay current single-capture candidates through the reviewed adapter.

    Current live issuance uses one exact FotMob capture.  Rebuild that capture
    through the same current-only PR39-or-reviewed-additive adapter used by the
    issuer, so deterministic admission replay preserves reviewed additive schema
    handling and request-date projection.  Multi-capture replay remains on the
    frozen PR39 builder.
    """
    if len(capture_rows) == 1:
        raw, manifest = capture_rows[0]
        return current_fotmob_candidates.build_current_fotmob_fixture_candidate_bundle(
            raw, manifest
        )
    return fotmob_candidates.build_fotmob_fixture_candidate_bundle(capture_rows)


def _rederive_exact_fotmob_admission(
    supplied: Any,
    captures: Any,
) -> fotmob_admission.ReviewedFixtureCatalogAdmission:
    if type(supplied) is not fotmob_admission.ReviewedFixtureCatalogAdmission:
        raise SportyBetCurrentEventDiscoveryError(
            "fotmob_admission_value must be exact ReviewedFixtureCatalogAdmission"
        )
    capture_rows = _materialize_fotmob_captures(captures)
    try:
        checked = dataclasses.replace(supplied)
        rebuilt_candidate = _build_replayed_fotmob_candidates(capture_rows)
        rebuilt_review = fotmob_review.build_fotmob_fixture_candidate_review_bundle(
            rebuilt_candidate,
            checked.handoff.review_bundle.decisions,
        )
        rebuilt_handoff = fotmob_handoff.build_fotmob_fixture_catalog_handoff(
            rebuilt_candidate,
            rebuilt_review,
        )
        supplied_handoff_bytes = fotmob_handoff.canonical_fotmob_fixture_catalog_handoff_bytes(
            checked.handoff
        )
        rebuilt_handoff_bytes = fotmob_handoff.canonical_fotmob_fixture_catalog_handoff_bytes(
            rebuilt_handoff
        )
    except (
        fotmob_admission.ReviewedFixtureCatalogAdmissionError,
        current_fotmob_candidates.CurrentFotMobFixtureCandidateAdapterError,
        fotmob_candidates.FotMobFixtureCandidateError,
        fotmob_review.FotMobFixtureCandidateReviewError,
        fotmob_handoff.FotMobFixtureCatalogHandoffError,
    ) as exc:
        raise SportyBetCurrentEventDiscoveryError(
            f"FotMob reviewed-catalog source replay failed closed: {exc}"
        ) from exc
    if supplied_handoff_bytes != rebuilt_handoff_bytes:
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob admission handoff is not the exact deterministic derivative of supplied raw captures and review decisions"
        )
    if (
        checked.decision.disposition
        is not fotmob_admission.ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ):
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob reviewed catalog must have exact ADMITTED disposition"
        )
    if checked.decision.source_capability != fotmob_admission.REVIEWED_SOURCE_CAPABILITY:
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob admission source capability mismatch"
        )
    if not checked.admitted_fixtures:
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob ADMITTED catalog exposes no fixture identities"
        )
    if any(type(value) is not bool or value is not False for value in checked.safety.values()):
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob admission safety must remain fail-closed"
        )
    return checked


def _reviewed_rows(
    admission: fotmob_admission.ReviewedFixtureCatalogAdmission,
) -> tuple[FotMobReviewedFixtureCatalogInput, ...]:
    rows = admission.handoff.catalog_inputs
    if type(rows) is not tuple or not rows or any(
        type(item) is not FotMobReviewedFixtureCatalogInput for item in rows
    ):
        raise SportyBetCurrentEventDiscoveryError(
            "source-replayed FotMob admission exposes invalid reviewed inputs"
        )
    ids = [item.source_fixture_identifier for item in rows]
    if len(ids) != len(set(ids)):
        raise SportyBetCurrentEventDiscoveryError(
            "source-replayed FotMob admission contains duplicate source fixture IDs"
        )
    try:
        return tuple(sorted(rows, key=lambda item: int(item.source_fixture_identifier)))
    except ValueError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            "FotMob source fixture identifier is not canonical decimal"
        ) from exc


def _capture_identity_rows(
    captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
) -> tuple[Mapping[str, Any], ...]:
    rows = []
    for raw, manifest in captures:
        rows.append(
            {
                "request_date": manifest.request_date,
                "raw_sha256": fotmob_sha256_bytes(raw),
                "raw_size": len(raw),
                "manifest_sha256": sha256_data_matches_capture_manifest(manifest),
                "observed_at": serialize_utc(manifest.observed_at),
            }
        )
    ordered = tuple(sorted(rows, key=lambda item: (item["request_date"], item["manifest_sha256"])))
    return tuple(types.MappingProxyType(dict(item)) for item in ordered)


@dataclasses.dataclass(frozen=True)
class CurrentEventReconciliationRow:
    event_id: str
    home_team_name: str
    away_team_name: str
    competition_name: str | None
    kickoff_utc: datetime
    discovery_observed_at: datetime
    discovery_age_seconds: float
    kickoff_lead_seconds: float
    disposition: CurrentEventReconciliationDisposition
    exact_fotmob_match_count: int
    matched_fotmob_fixture_id: str | None
    direct_event_observed_at: datetime | None
    direct_event_age_seconds: float | None
    direct_event_manifest_sha256: str | None
    direct_event_inventory_sha256: str | None
    direct_event_raw_sha256: str | None
    fixture_reconciliation_authorized: bool

    def __post_init__(self) -> None:
        _event_id(self.event_id)
        _text(self.home_team_name, "row home_team_name")
        _text(self.away_team_name, "row away_team_name")
        if self.competition_name is not None:
            _text(self.competition_name, "row competition_name")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "row kickoff_utc"))
        object.__setattr__(
            self,
            "discovery_observed_at",
            _utc(self.discovery_observed_at, "row discovery_observed_at"),
        )
        for value, label in (
            (self.discovery_age_seconds, "discovery_age_seconds"),
            (self.kickoff_lead_seconds, "kickoff_lead_seconds"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise SportyBetCurrentEventDiscoveryError(f"{label} must be finite")
        if type(self.disposition) is not CurrentEventReconciliationDisposition:
            raise SportyBetCurrentEventDiscoveryError("row disposition is invalid")
        if type(self.exact_fotmob_match_count) is not int or self.exact_fotmob_match_count < 0:
            raise SportyBetCurrentEventDiscoveryError("exact_fotmob_match_count is invalid")
        if self.matched_fotmob_fixture_id is not None:
            _text(self.matched_fotmob_fixture_id, "matched_fotmob_fixture_id", maximum=64)
        if self.direct_event_observed_at is not None:
            object.__setattr__(
                self,
                "direct_event_observed_at",
                _utc(self.direct_event_observed_at, "direct_event_observed_at"),
            )
        if self.direct_event_age_seconds is not None and (
            isinstance(self.direct_event_age_seconds, bool)
            or not isinstance(self.direct_event_age_seconds, (int, float))
            or not math.isfinite(float(self.direct_event_age_seconds))
        ):
            raise SportyBetCurrentEventDiscoveryError(
                "direct_event_age_seconds must be finite or None"
            )
        for value, label in (
            (self.direct_event_manifest_sha256, "direct_event_manifest_sha256"),
            (self.direct_event_inventory_sha256, "direct_event_inventory_sha256"),
            (self.direct_event_raw_sha256, "direct_event_raw_sha256"),
        ):
            if value is not None:
                _sha(value, label)
        if type(self.fixture_reconciliation_authorized) is not bool:
            raise SportyBetCurrentEventDiscoveryError(
                "fixture_reconciliation_authorized must be bool"
            )
        if self.fixture_reconciliation_authorized != (
            self.disposition
            is CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
        ):
            raise SportyBetCurrentEventDiscoveryError(
                "row authorization must correspond exactly to unique current reconciliation"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "competition_name": self.competition_name,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "discovery_observed_at": serialize_utc(self.discovery_observed_at),
            "discovery_age_seconds": self.discovery_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "disposition": self.disposition.value,
            "exact_fotmob_match_count": self.exact_fotmob_match_count,
            "matched_fotmob_fixture_id": self.matched_fotmob_fixture_id,
            "direct_event_observed_at": (
                None
                if self.direct_event_observed_at is None
                else serialize_utc(self.direct_event_observed_at)
            ),
            "direct_event_age_seconds": self.direct_event_age_seconds,
            "direct_event_manifest_sha256": self.direct_event_manifest_sha256,
            "direct_event_inventory_sha256": self.direct_event_inventory_sha256,
            "direct_event_raw_sha256": self.direct_event_raw_sha256,
            "fixture_reconciliation_authorized": self.fixture_reconciliation_authorized,
        }


def _output_authority(rows: Sequence[CurrentEventReconciliationRow]) -> Mapping[str, bool]:
    any_authorized = any(item.fixture_reconciliation_authorized for item in rows)
    any_detail = any(item.direct_event_manifest_sha256 is not None for item in rows)
    return types.MappingProxyType(
        {
            "current_event_discovery": True,
            "current_event_detail_confirmation": any_detail,
            "fixture_reconciliation": any_authorized,
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


@dataclasses.dataclass(frozen=True, init=False)
class SportyBetCurrentEventDiscoveryReconciliationBundle:
    schema_version: int
    dataset_name: str
    status: str
    evaluation_time: datetime
    max_source_age_seconds: int
    minimum_lead_seconds: int
    discovery_manifest_sha256: str
    source_fotmob_admission_sha256: str
    source_fotmob_candidate_bundle_sha256: str
    source_fotmob_review_bundle_sha256: str
    source_fotmob_handoff_sha256: str
    source_fotmob_catalog_sha256: str
    source_fotmob_manifest_sha256: str
    fotmob_capture_identities: tuple[Mapping[str, Any], ...]
    rows: tuple[CurrentEventReconciliationRow, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    contract_sha256: str
    _repository_root: Path
    _discovery_directory: Path
    _detail_directories: tuple[tuple[str, Path], ...]
    _fotmob_admission: fotmob_admission.ReviewedFixtureCatalogAdmission
    _fotmob_captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetCurrentEventDiscoveryError(
            "current-event reconciliation bundles are builder-only"
        )

    @property
    def matched_rows(self) -> tuple[CurrentEventReconciliationRow, ...]:
        return tuple(item for item in self.rows if item.fixture_reconciliation_authorized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "evaluation_time": serialize_utc(self.evaluation_time),
            "max_source_age_seconds": self.max_source_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "discovery_manifest_sha256": self.discovery_manifest_sha256,
            "source_fotmob_admission_sha256": self.source_fotmob_admission_sha256,
            "source_fotmob_candidate_bundle_sha256": self.source_fotmob_candidate_bundle_sha256,
            "source_fotmob_review_bundle_sha256": self.source_fotmob_review_bundle_sha256,
            "source_fotmob_handoff_sha256": self.source_fotmob_handoff_sha256,
            "source_fotmob_catalog_sha256": self.source_fotmob_catalog_sha256,
            "source_fotmob_manifest_sha256": self.source_fotmob_manifest_sha256,
            "fotmob_capture_identities": [dict(item) for item in self.fotmob_capture_identities],
            "event_count": len(self.rows),
            "matched_count": len(self.matched_rows),
            "rows": [item.to_dict() for item in self.rows],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "contract_sha256": self.contract_sha256,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
            "wager_placed": False,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _match_event(
    event: SportyBetDiscoveredEvent,
    reviewed: Sequence[FotMobReviewedFixtureCatalogInput],
) -> tuple[FotMobReviewedFixtureCatalogInput, ...]:
    if event.competition_name is None:
        return ()
    return tuple(
        item
        for item in reviewed
        if item.home_team == event.home_team_name
        and item.away_team == event.away_team_name
        and item.competition == event.competition_name
        and item.kickoff.astimezone(timezone.utc) == event.kickoff_utc
    )


def _detail_inventory_from_directory(
    directory: Path,
    *,
    repository_root: Path,
) -> live.SportyBetLiveEventQuoteInventory:
    try:
        return live.build_live_event_quote_inventory(
            directory,
            repository_root=repository_root,
        )
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise SportyBetCurrentEventDiscoveryError(
            f"PR246 direct event-detail replay failed closed: {exc}"
        ) from exc


def _build_bundle(
    *,
    repository_root: Path,
    discovery_directory: Path,
    discovery: SportyBetCurrentEventDiscoveryManifest,
    admission: fotmob_admission.ReviewedFixtureCatalogAdmission,
    captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
    detail_directories: Mapping[str, Path],
    evaluation_time: datetime,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    evaluation = _utc(evaluation_time, "evaluation_time")
    reviewed = _reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[FotMobReviewedFixtureCatalogInput, ...]]] = {}
    for event in discovery.events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = _match_event(event, reviewed)
            if not matches:
                provisional[event.event_id] = ("NO_MATCH", ())
            elif len(matches) > 1:
                provisional[event.event_id] = ("AMBIGUOUS_FOTMOB", matches)
            else:
                provisional[event.event_id] = ("UNIQUE", matches)
    target_counts = Counter(
        matches[0].source_fixture_identifier
        for state, matches in provisional.values()
        if state == "UNIQUE"
    )
    expected_detail_ids = {
        event_id
        for event_id, (state, matches) in provisional.items()
        if state == "UNIQUE" and target_counts[matches[0].source_fixture_identifier] == 1
    }
    if set(detail_directories) != expected_detail_ids:
        raise SportyBetCurrentEventDiscoveryError(
            "direct event-detail evidence set does not match exact unique reconciliation candidates"
        )

    rows: list[CurrentEventReconciliationRow] = []
    for event in discovery.events:
        state, matches = provisional[event.event_id]
        discovery_age = (evaluation - event.source_observed_at).total_seconds()
        kickoff_lead = (event.kickoff_utc - evaluation).total_seconds()
        if discovery_age < 0:
            raise SportyBetCurrentEventDiscoveryError(
                "evaluation_time predates a discovery response completion"
            )
        disposition: CurrentEventReconciliationDisposition
        matched_id: str | None = None
        direct_observed: datetime | None = None
        direct_age: float | None = None
        direct_manifest_sha: str | None = None
        direct_inventory_sha: str | None = None
        direct_raw_sha: str | None = None

        if discovery_age > MAX_SOURCE_AGE_SECONDS:
            disposition = CurrentEventReconciliationDisposition.DISCOVERY_EVIDENCE_STALE
        elif kickoff_lead <= MINIMUM_LEAD_SECONDS:
            disposition = CurrentEventReconciliationDisposition.PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF
        elif state == "NONBOOKABLE":
            disposition = CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE
        elif state == "NO_COMPETITION":
            disposition = CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN
        elif state == "NO_MATCH":
            disposition = CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
        elif state == "AMBIGUOUS_FOTMOB":
            disposition = CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH
        elif target_counts[matches[0].source_fixture_identifier] > 1:
            disposition = CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE
        else:
            matched = matches[0]
            matched_id = matched.source_fixture_identifier
            inventory = _detail_inventory_from_directory(
                detail_directories[event.event_id],
                repository_root=repository_root,
            )
            direct_observed = inventory.observed_at
            direct_age = (evaluation - inventory.observed_at).total_seconds()
            if direct_age < 0:
                raise SportyBetCurrentEventDiscoveryError(
                    "evaluation_time predates a direct event-detail response completion"
                )
            direct_manifest_sha = inventory.source_manifest_sha256
            direct_inventory_sha = inventory.canonical_sha256
            direct_raw_sha = inventory.source_raw_sha256
            if (
                inventory.event_id != event.event_id
                or inventory.home_team_name != event.home_team_name
                or inventory.away_team_name != event.away_team_name
                or inventory.kickoff_utc != event.kickoff_utc
            ):
                disposition = CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH
            elif not inventory.prematch_bookable_observed:
                disposition = CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE
            elif direct_age > MAX_SOURCE_AGE_SECONDS:
                disposition = CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_STALE
            else:
                disposition = CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED

        rows.append(
            CurrentEventReconciliationRow(
                event_id=event.event_id,
                home_team_name=event.home_team_name,
                away_team_name=event.away_team_name,
                competition_name=event.competition_name,
                kickoff_utc=event.kickoff_utc,
                discovery_observed_at=event.source_observed_at,
                discovery_age_seconds=discovery_age,
                kickoff_lead_seconds=kickoff_lead,
                disposition=disposition,
                exact_fotmob_match_count=len(matches),
                matched_fotmob_fixture_id=matched_id,
                direct_event_observed_at=direct_observed,
                direct_event_age_seconds=direct_age,
                direct_event_manifest_sha256=direct_manifest_sha,
                direct_event_inventory_sha256=direct_inventory_sha,
                direct_event_raw_sha256=direct_raw_sha,
                fixture_reconciliation_authorized=(
                    disposition
                    is CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
                ),
            )
        )

    ordered = tuple(sorted(rows, key=lambda item: item.event_id))
    admission_payload = admission.to_dict()
    detail_tuple = tuple(
        sorted(
            ((event_id, Path(path)) for event_id, path in detail_directories.items()),
            key=lambda item: item[0],
        )
    )
    value = object.__new__(SportyBetCurrentEventDiscoveryReconciliationBundle)
    return _set_frozen(
        value,
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "evaluation_time": evaluation,
            "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
            "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
            "discovery_manifest_sha256": discovery.canonical_sha256,
            "source_fotmob_admission_sha256": (
                fotmob_admission.sha256_reviewed_fixture_catalog_admission(admission)
            ),
            "source_fotmob_candidate_bundle_sha256": admission_payload[
                "candidate_bundle_sha256"
            ],
            "source_fotmob_review_bundle_sha256": admission_payload[
                "review_bundle_sha256"
            ],
            "source_fotmob_handoff_sha256": admission_payload["handoff_sha256"],
            "source_fotmob_catalog_sha256": admission_payload["catalog_sha256"],
            "source_fotmob_manifest_sha256": admission_payload["manifest_sha256"],
            "fotmob_capture_identities": _capture_identity_rows(captures),
            "rows": ordered,
            "authority": _output_authority(ordered),
            "next_boundary": NEXT_BOUNDARY,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "_repository_root": Path(repository_root),
            "_discovery_directory": Path(discovery_directory),
            "_detail_directories": detail_tuple,
            "_fotmob_admission": admission,
            "_fotmob_captures": captures,
        },
    )


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_admission_value: fotmob_admission.ReviewedFixtureCatalogAdmission,
    fotmob_captures: Sequence[tuple[bytes, FotMobDataMatchesCaptureManifest]],
    execute_live_network: bool,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    """Capture current SportyBet events and issue exact source-replayed fixture mappings."""
    validate_current_event_discovery_contract()
    if execute_live_network is not True:
        raise SportyBetCurrentEventDiscoveryError(
            "live current-event reconciliation requires exact execute_live_network=True"
        )
    repository = Path(repository_root).resolve(strict=True)
    captures = _materialize_fotmob_captures(fotmob_captures)
    admission = _rederive_exact_fotmob_admission(fotmob_admission_value, captures)
    discovery_directory, discovery = capture_current_event_discovery(
        repository_root=repository,
        execute_live_network=True,
    )
    reviewed = _reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[FotMobReviewedFixtureCatalogInput, ...]]] = {}
    for event in discovery.events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = _match_event(event, reviewed)
            if not matches:
                provisional[event.event_id] = ("NO_MATCH", ())
            elif len(matches) > 1:
                provisional[event.event_id] = ("AMBIGUOUS_FOTMOB", matches)
            else:
                provisional[event.event_id] = ("UNIQUE", matches)
    counts = Counter(
        matches[0].source_fixture_identifier
        for state, matches in provisional.values()
        if state == "UNIQUE"
    )
    detail_dirs: dict[str, Path] = {}
    for event_id, (state, matches) in sorted(provisional.items()):
        if state != "UNIQUE" or counts[matches[0].source_fixture_identifier] != 1:
            continue
        try:
            directory, _manifest = live.capture_live_event_quote_evidence(
                event_id=event_id,
                repository_root=repository,
                execute_live_network=True,
            )
            # Build immediately so malformed/non-priced direct detail fails before issuance.
            live.build_live_event_quote_inventory(
                directory,
                repository_root=repository,
            )
        except live.SportyBetLiveEventQuoteEvidenceError as exc:
            raise SportyBetCurrentEventDiscoveryError(
                f"PR246 direct event-detail acquisition failed closed for {event_id}: {exc}"
            ) from exc
        detail_dirs[event_id] = directory
    evaluation_time = _now_utc()
    return _build_bundle(
        repository_root=repository,
        discovery_directory=discovery_directory,
        discovery=discovery,
        admission=admission,
        captures=captures,
        detail_directories=detail_dirs,
        evaluation_time=evaluation_time,
    )


def verify_current_event_discovery_reconciliation_bundle(
    value: Any,
) -> SportyBetCurrentEventDiscoveryReconciliationBundle:
    """Replay every retained source and require exact deterministic bundle equality."""
    if type(value) is not SportyBetCurrentEventDiscoveryReconciliationBundle:
        raise SportyBetCurrentEventDiscoveryError(
            "value must be exact SportyBetCurrentEventDiscoveryReconciliationBundle"
        )
    validate_current_event_discovery_contract()
    captures = _materialize_fotmob_captures(value._fotmob_captures)
    admission = _rederive_exact_fotmob_admission(value._fotmob_admission, captures)
    discovery = verify_current_event_discovery(
        value._discovery_directory,
        repository_root=value._repository_root,
    )
    detail_dirs = dict(value._detail_directories)
    rebuilt = _build_bundle(
        repository_root=value._repository_root,
        discovery_directory=value._discovery_directory,
        discovery=discovery,
        admission=admission,
        captures=captures,
        detail_directories=detail_dirs,
        evaluation_time=value.evaluation_time,
    )
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()):
        raise SportyBetCurrentEventDiscoveryError(
            "current event reconciliation differs from exact retained-source replay"
        )
    return rebuilt


__all__ = [
    "ALLOWED_OUTPUT_RELATIVE",
    "CONTRACT_VERSION",
    "CurrentEventReconciliationDisposition",
    "CurrentEventReconciliationRow",
    "DATASET_NAME",
    "DISCOVERY_DATASET_NAME",
    "DISCOVERY_PATH",
    "EXPECTED_CONTRACT_SHA256",
    "FOTMOB_SOURCE_REPLAY_POLICY",
    "MAX_PAGES",
    "MAX_SOURCE_AGE_SECONDS",
    "MINIMUM_LEAD_SECONDS",
    "NEXT_BOUNDARY",
    "PAGE_SIZE",
    "PAGINATION_TERMINATION_EMPTY_PAGE",
    "PAGINATION_TERMINATION_POLICY",
    "PAGINATION_TERMINATION_SHORT_PAGE",
    "SCHEMA_VERSION",
    "STATUS",
    "SportyBetCurrentEventDiscoveryError",
    "SportyBetCurrentEventDiscoveryManifest",
    "SportyBetCurrentEventDiscoveryReconciliationBundle",
    "SportyBetDiscoveredEvent",
    "SportyBetDiscoveryPage",
    "calculate_current_event_discovery_contract_sha256",
    "capture_current_event_discovery",
    "discover_and_reconcile_current_events",
    "request_target",
    "request_url",
    "validate_current_event_discovery_contract",
    "verify_current_event_discovery",
    "verify_current_event_discovery_reconciliation_bundle",
]
