"""Replayable, evidence-only contract for SportyBet's global pcUpcomingEvents source.

This module deliberately does not own Current Shadow or P3.0 runtime discovery.
It preserves exact native provider event ancestry so a later, separately reviewed
migration can decide whether to consume it.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import types
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from domain import sportybet_live_event_quote_evidence as live

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
DATASET_NAME = "athena-current-shadow-sportybet-pc-upcoming-global-football-v1"
PROVIDER = "SportyBet"
PROVIDER_REGION = "Nigeria"
SOURCE_METHOD = "PUBLIC_ANONYMOUS_FACTS_CENTER_PC_UPCOMING_EVENTS_GET"
SOURCE_PATH = "/api/ng/factsCenter/pcUpcomingEvents"
ORIGIN = live.ORIGIN
OPER_ID = live.OPER_ID
FOOTBALL_SPORT_ID = "sr:sport:1"
MARKET_ID = "1"
PAGE_SIZE = 100
MAX_PAGES = 20
TIMELINE_HOURS = 48
TODAY_GAMES = "false"
REQUEST_NONCE_MAX_SKEW_MS = 120_000
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 45
REQUEST_HEADERS = (
    ("Accept", "application/json"),
    ("Accept-Language", "en-NG,en;q=0.9"),
    ("OperId", OPER_ID),
    ("User-Agent", "ATHENA/1.0 sportybet-current-event-discovery"),
)
EVIDENCE_ROOT = Path(
    ".cache/athena-research/current-shadow-sportybet-pc-upcoming-discovery"
)
P4_4_BASE_MAIN = "6b39648cac4e9924c0809d60dddc9c5d5660ad77"
DIAGNOSTIC_ISSUE_COMMENT_ID = 5840014421
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_EVENT_ID_RE = re.compile(r"^sr:match:([1-9][0-9]*)$", re.ASCII)
_COMPETITOR_ID_RE = re.compile(r"^sr:competitor:([1-9][0-9]*)$", re.ASCII)
_CATEGORY_ID_RE = re.compile(r"^sr:category:([1-9][0-9]*)$", re.ASCII)
_TOURNAMENT_ID_RE = re.compile(r"^sr:tournament:([1-9][0-9]*)$", re.ASCII)

AUTHORITY = types.MappingProxyType({
    "provider_discovery_evidence": True,
    "provider_absence": False,
    "current_shadow_runtime_discovery": False,
    "p3_runtime_discovery": False,
    "fixture_reconciliation": False,
    "pricing": False,
    "selection": False,
    "model": False,
    "router": False,
    "portfolio": False,
    "share_code": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})


class PcUpcomingDiscoveryError(ValueError):
    """Raised when pcUpcomingEvents bytes do not satisfy the reviewed contract."""


def _canonical(value: Any, *, newline: bool = False) -> bytes:
    try:
        result = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PcUpcomingDiscoveryError("canonical JSON serialization failed") from exc
    return result + (b"\n" if newline else b"")


def _strict_json_loads(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PcUpcomingDiscoveryError("JSON contains a duplicate object key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise PcUpcomingDiscoveryError(f"JSON contains invalid numeric constant {value}")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except PcUpcomingDiscoveryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PcUpcomingDiscoveryError("response is not strict UTF-8 JSON") from exc


def _sha(raw: Any, label: str) -> str:
    if type(raw) is not str or _SHA_RE.fullmatch(raw) is None:
        raise PcUpcomingDiscoveryError(f"{label} must be lowercase SHA-256")
    return raw


def _nonempty_string(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise PcUpcomingDiscoveryError(f"{label} must be a non-empty string")
    return value


def _provider_id(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise PcUpcomingDiscoveryError(f"{label} is not an exact provider-native ID")
    return value


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PcUpcomingDiscoveryError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime_from_epoch_milliseconds(value: int) -> datetime:
    return datetime.fromtimestamp(value // 1000, timezone.utc).replace(microsecond=(value % 1000) * 1000)


def _parse_utc_text(value: Any, label: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise PcUpcomingDiscoveryError(f"{label} must be canonical UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PcUpcomingDiscoveryError(f"{label} is invalid") from exc
    return _utc(parsed, label)


def request_target(page_num: Any, request_nonce_ms: Any) -> str:
    if type(page_num) is not int or not 1 <= page_num <= MAX_PAGES:
        raise PcUpcomingDiscoveryError("page_num must be an integer from 1 through MAX_PAGES")
    if type(request_nonce_ms) is not int or request_nonce_ms <= 0:
        raise PcUpcomingDiscoveryError("request_nonce_ms must be a positive integer")
    query = urlencode(
        (
            ("sportId", FOOTBALL_SPORT_ID),
            ("marketId", MARKET_ID),
            ("pageSize", str(PAGE_SIZE)),
            ("pageNum", str(page_num)),
            ("todayGames", TODAY_GAMES),
            ("timeline", str(TIMELINE_HOURS)),
            ("_t", str(request_nonce_ms)),
        )
    )
    return f"{SOURCE_PATH}?{query}"


def request_url(page_num: Any, request_nonce_ms: Any) -> str:
    return ORIGIN + request_target(page_num, request_nonce_ms)


def _validate_target(value: Any, *, page_num: int, observed_at: datetime) -> int:
    if type(value) is not str:
        raise PcUpcomingDiscoveryError("request_target must be a string")
    parsed = urlsplit(value)
    if parsed.path != SOURCE_PATH or parsed.fragment or parsed.netloc or parsed.scheme:
        raise PcUpcomingDiscoveryError("request target path/authority is invalid")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise PcUpcomingDiscoveryError("request query is malformed") from exc
    expected_keys = {"sportId", "marketId", "pageSize", "pageNum", "todayGames", "timeline", "_t"}
    if set(query) != expected_keys or any(len(values) != 1 for values in query.values()):
        raise PcUpcomingDiscoveryError("request query keys/cardinality drifted")
    nonce_text = query["_t"][0]
    if not nonce_text.isascii() or not nonce_text.isdigit() or str(int(nonce_text)) != nonce_text:
        raise PcUpcomingDiscoveryError("request nonce is not canonical positive epoch milliseconds")
    nonce = int(nonce_text)
    if nonce <= 0:
        raise PcUpcomingDiscoveryError("request nonce must be positive")
    canonical_target = request_target(page_num, nonce)
    if value != canonical_target:
        raise PcUpcomingDiscoveryError("request target differs from fixed query policy")
    observed_ms = int(_utc(observed_at, "observed_at").timestamp() * 1000)
    skew = observed_ms - nonce
    if skew < 0 or skew > REQUEST_NONCE_MAX_SKEW_MS:
        raise PcUpcomingDiscoveryError("request nonce is outside response-completion skew")
    return nonce


def policy_payload() -> dict[str, Any]:
    """Return deterministic semantics; this contract grants no runtime authority."""
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "dataset_name": DATASET_NAME,
        "provider": PROVIDER,
        "provider_region": PROVIDER_REGION,
        "source_method": SOURCE_METHOD,
        "origin": ORIGIN,
        "oper_id": OPER_ID,
        "path": SOURCE_PATH,
        "fixed_query": {
            "sportId": FOOTBALL_SPORT_ID,
            "marketId": MARKET_ID,
            "pageSize": PAGE_SIZE,
            "pageNum": "dynamic-positive-integer-1-through-20",
            "todayGames": False,
            "timeline": TIMELINE_HOURS,
            "_t": "positive-epoch-milliseconds-response-completion-nonce",
        },
        "request_headers": [list(item) for item in REQUEST_HEADERS],
        "request_nonce_max_skew_ms": REQUEST_NONCE_MAX_SKEW_MS,
        "max_response_bytes_per_page": MAX_RESPONSE_BYTES,
        "page_size": PAGE_SIZE,
        "max_pages": MAX_PAGES,
        "coverage_horizon_hours": TIMELINE_HOURS,
        "identity": "EXACT_PROVIDER_NATIVE_IDS_AND_ENCLOSING_TOURNAMENT_ANCESTRY",
        "projection_rule": "OBSERVED_EVENT_FIELDS_AND_WRAPPER_ANCESTRY_ONLY_NO_QUERY_SCOPE_FIELDS_SYNTHESIZED_AS_EVENT_FIELDS",
        "duplicate_event_rule": "IDENTITY_EQUIVALENT_DUPLICATES_DEDUPED_CONFLICTS_REJECTED",
        "captured_event_count_semantics": "UNIQUE_IDENTITY_EQUIVALENT_DEDUPED_EVENT_IDS",
        "pagination_completion_rule": "CONTIGUOUS_REQUIRED_PAGES_AND_UNIQUE_EVENTS_EQUAL_PROVIDER_TOTAL_NUM",
        "observation_time_basis": "ATHENA_RESPONSE_COMPLETION_NOT_PROVIDER_EVENT_OR_QUOTE_TIME",
        "observation_time_serialization": "UTC_MICROSECOND_PRECISION",
        "missing_match_status_rule": "PRESERVE_MISSING_OR_NULL_AS_NULL_AND_DO_NOT_INFER_PREMATCH_BOOKABILITY",
        "authority": dict(AUTHORITY),
    }


def calculate_policy_sha256() -> str:
    return hashlib.sha256(_canonical(policy_payload())).hexdigest()


# Set to the canonical policy hash after the contract payload is finalized.
PINNED_POLICY_SHA256 = "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"


@dataclasses.dataclass(frozen=True)
class PcUpcomingDiscoveredEvent:
    event_id: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    category_id: str
    category_name: str
    tournament_id: str
    tournament_name: str
    source_sport_id: str | None
    kickoff_utc: datetime
    estimate_start_time_ms: int
    booking_status: str
    match_status: str | None
    event_status: int | str | None
    prematch_bookable_observed: bool
    source_page_num: int
    source_raw_sha256: str
    source_observed_at: datetime

    def __post_init__(self) -> None:
        _provider_id(self.event_id, _EVENT_ID_RE, "event_id")
        _provider_id(self.home_team_id, _COMPETITOR_ID_RE, "home_team_id")
        _provider_id(self.away_team_id, _COMPETITOR_ID_RE, "away_team_id")
        if self.home_team_id == self.away_team_id:
            raise PcUpcomingDiscoveryError("home and away competitor IDs must differ")
        for name in ("home_team_name", "away_team_name", "category_name", "tournament_name", "booking_status"):
            _nonempty_string(getattr(self, name), name)
        if self.home_team_name == self.away_team_name:
            raise PcUpcomingDiscoveryError("home and away team names must differ")
        if self.match_status is not None:
            _nonempty_string(self.match_status, "match_status")
        _provider_id(self.category_id, _CATEGORY_ID_RE, "category_id")
        _provider_id(self.tournament_id, _TOURNAMENT_ID_RE, "tournament_id")
        if self.source_sport_id is not None and self.source_sport_id != FOOTBALL_SPORT_ID:
            raise PcUpcomingDiscoveryError("source_sport_id conflicts with fixed football source")
        if type(self.estimate_start_time_ms) is not int or self.estimate_start_time_ms <= 0:
            raise PcUpcomingDiscoveryError("estimate_start_time_ms must be a positive integer")
        if type(self.kickoff_utc) is not datetime or _utc(self.kickoff_utc, "kickoff_utc") != _datetime_from_epoch_milliseconds(self.estimate_start_time_ms):
            raise PcUpcomingDiscoveryError("kickoff_utc must exactly represent estimateStartTime")
        if self.event_status is not None and type(self.event_status) not in (int, str):
            raise PcUpcomingDiscoveryError("event_status must be an integer, string, or None")
        if type(self.prematch_bookable_observed) is not bool:
            raise PcUpcomingDiscoveryError("prematch_bookable_observed must be bool")
        if type(self.source_page_num) is not int or not 1 <= self.source_page_num <= MAX_PAGES:
            raise PcUpcomingDiscoveryError("source_page_num is outside the reviewed page range")
        _sha(self.source_raw_sha256, "source_raw_sha256")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "kickoff_utc"))
        object.__setattr__(self, "source_observed_at", _utc(self.source_observed_at, "source_observed_at"))

    def identity_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team_id": self.home_team_id,
            "home_team_name": self.home_team_name,
            "away_team_id": self.away_team_id,
            "away_team_name": self.away_team_name,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "tournament_id": self.tournament_id,
            "tournament_name": self.tournament_name,
            "source_sport_id": self.source_sport_id,
            "estimate_start_time_ms": self.estimate_start_time_ms,
            "booking_status": self.booking_status,
            "match_status": self.match_status,
            "event_status": self.event_status,
            "prematch_bookable_observed": self.prematch_bookable_observed,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity_dict(),
            "kickoff_utc": _utc_text(self.kickoff_utc),
            "source_page_num": self.source_page_num,
            "source_raw_sha256": self.source_raw_sha256,
            "source_observed_at": _utc_text(self.source_observed_at),
        }


@dataclasses.dataclass(frozen=True)
class PcUpcomingPageEvidence:
    page_num: int
    request_target: str
    request_nonce_ms: int
    observed_at: datetime
    raw_sha256: str
    raw_size: int
    total_num: int
    tournament_count: int
    event_count: int
    events: tuple[PcUpcomingDiscoveredEvent, ...]
    raw_relative_path: str
    raw_bytes: bytes = dataclasses.field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.page_num) is not int or not 1 <= self.page_num <= MAX_PAGES:
            raise PcUpcomingDiscoveryError("page_num is outside the reviewed range")
        observed = _utc(self.observed_at, "observed_at")
        nonce = _validate_target(self.request_target, page_num=self.page_num, observed_at=observed)
        if type(self.request_nonce_ms) is not int or self.request_nonce_ms != nonce:
            raise PcUpcomingDiscoveryError("request nonce differs from exact request target")
        _sha(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise PcUpcomingDiscoveryError("raw_size is outside response bound")
        if type(self.raw_bytes) is not bytes or len(self.raw_bytes) != self.raw_size:
            raise PcUpcomingDiscoveryError("raw_bytes differ from page raw_size")
        if hashlib.sha256(self.raw_bytes).hexdigest() != self.raw_sha256:
            raise PcUpcomingDiscoveryError("raw_bytes SHA-256 differs")
        for field_name, field_value in (("total_num", self.total_num), ("tournament_count", self.tournament_count), ("event_count", self.event_count)):
            if type(field_value) is not int or field_value < 0:
                raise PcUpcomingDiscoveryError(f"{field_name} must be a non-negative integer")
        if type(self.events) is not tuple or self.tournament_count < 0 or self.event_count != len(self.events) or len(self.events) > PAGE_SIZE:
            raise PcUpcomingDiscoveryError("page counts differ from parsed rows")
        if type(self.events) is not tuple or any(type(event) is not PcUpcomingDiscoveredEvent for event in self.events):
            raise PcUpcomingDiscoveryError("page events must be exact immutable event values")
        expected_path = f"pages/page-{self.page_num:03d}.raw.json"
        if self.raw_relative_path != expected_path:
            raise PcUpcomingDiscoveryError("raw page path differs from the fixed evidence layout")
        if any(event.source_page_num != self.page_num or event.source_raw_sha256 != self.raw_sha256 or event.source_observed_at != observed for event in self.events):
            raise PcUpcomingDiscoveryError("event source ancestry differs from its exact page")
        object.__setattr__(self, "observed_at", observed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_num": self.page_num,
            "request_target": self.request_target,
            "request_nonce_ms": self.request_nonce_ms,
            "observed_at": _utc_text(self.observed_at),
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "total_num": self.total_num,
            "tournament_count": self.tournament_count,
            "event_count": self.event_count,
            "raw_relative_path": self.raw_relative_path,
        }


def _event_from_row(
    row: Any,
    *,
    category_id: str,
    category_name: str,
    tournament_id: str,
    tournament_name: str,
    page_num: int,
    raw_sha256: str,
    observed_at: datetime,
) -> PcUpcomingDiscoveredEvent:
    if type(row) is not dict:
        raise PcUpcomingDiscoveryError("event row must be an object")
    event_id = _provider_id(row.get("eventId"), _EVENT_ID_RE, "eventId")
    home_id = _provider_id(row.get("homeTeamId"), _COMPETITOR_ID_RE, "homeTeamId")
    away_id = _provider_id(row.get("awayTeamId"), _COMPETITOR_ID_RE, "awayTeamId")
    home_name = _nonempty_string(row.get("homeTeamName"), "homeTeamName")
    away_name = _nonempty_string(row.get("awayTeamName"), "awayTeamName")
    estimate_ms = row.get("estimateStartTime")
    if type(estimate_ms) is not int or estimate_ms <= 0:
        raise PcUpcomingDiscoveryError("estimateStartTime must be positive integer epoch milliseconds")
    kickoff = _datetime_from_epoch_milliseconds(estimate_ms)
    match_status_raw = row.get("matchStatus")
    match_status = None if match_status_raw is None else _nonempty_string(match_status_raw, "matchStatus")
    booking_status = _nonempty_string(row.get("bookingStatus"), "bookingStatus")
    event_status = row.get("status")
    if event_status is not None and type(event_status) not in (int, str):
        raise PcUpcomingDiscoveryError("status must be an integer, string, or absent")
    sport = row.get("sport")
    source_sport_id: str | None = None
    if sport is not None:
        if type(sport) is not dict:
            raise PcUpcomingDiscoveryError("nested sport ancestry must be an object")
        if "id" in sport:
            source_sport_id = _nonempty_string(sport["id"], "sport.id")
            if source_sport_id != FOOTBALL_SPORT_ID:
                raise PcUpcomingDiscoveryError("nested event sport conflicts with fixed football source")
        category = sport.get("category")
        if category is not None:
            if type(category) is not dict:
                raise PcUpcomingDiscoveryError("nested category ancestry must be an object")
            nested_tournament = category.get("tournament")
            if (category.get("id"), category.get("name")) != (category_id, category_name):
                raise PcUpcomingDiscoveryError("event category ancestry conflicts with wrapper")
            if nested_tournament is not None and (
                type(nested_tournament) is not dict
                or (nested_tournament.get("id"), nested_tournament.get("name")) != (tournament_id, tournament_name)
            ):
                raise PcUpcomingDiscoveryError("event tournament ancestry conflicts with wrapper")
    return PcUpcomingDiscoveredEvent(
        event_id=event_id,
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        category_id=category_id,
        category_name=category_name,
        tournament_id=tournament_id,
        tournament_name=tournament_name,
        source_sport_id=source_sport_id,
        kickoff_utc=kickoff,
        estimate_start_time_ms=estimate_ms,
        booking_status=booking_status,
        match_status=match_status,
        event_status=event_status,
        prematch_bookable_observed=(booking_status in {"Booked", "Buyable"} and event_status == 0 and match_status == "Not start"),
        source_page_num=page_num,
        source_raw_sha256=raw_sha256,
        source_observed_at=observed_at,
    )


def parse_page(
    raw: bytes,
    *,
    page_num: Any,
    request_nonce_ms: Any,
    observed_at: datetime,
) -> PcUpcomingPageEvidence:
    if type(page_num) is not int or not 1 <= page_num <= MAX_PAGES:
        raise PcUpcomingDiscoveryError("page_num must be an integer in the reviewed range")
    if type(request_nonce_ms) is not int or request_nonce_ms <= 0:
        raise PcUpcomingDiscoveryError("request_nonce_ms must be a positive integer")
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise PcUpcomingDiscoveryError("raw page bytes are empty or exceed the bound")
    observed = _utc(observed_at, "observed_at")
    target = request_target(page_num, request_nonce_ms)
    _validate_target(target, page_num=page_num, observed_at=observed)
    payload = _strict_json_loads(raw)
    if type(payload) is not dict or type(payload.get("bizCode")) is not int or payload["bizCode"] != 10000:
        raise PcUpcomingDiscoveryError("provider response bizCode must be exact integer 10000")
    data = payload.get("data")
    if type(data) is not dict:
        raise PcUpcomingDiscoveryError("provider data must be an object")
    total_num = data.get("totalNum")
    tournaments = data.get("tournaments")
    if type(total_num) is not int or total_num < 0:
        raise PcUpcomingDiscoveryError("data.totalNum must be a non-negative integer")
    if type(tournaments) is not list:
        raise PcUpcomingDiscoveryError("data.tournaments must be a list")
    raw_hash = hashlib.sha256(raw).hexdigest()
    events: list[PcUpcomingDiscoveredEvent] = []
    for tournament in tournaments:
        if type(tournament) is not dict:
            raise PcUpcomingDiscoveryError("tournament row must be an object")
        tournament_id = _provider_id(tournament.get("id"), _TOURNAMENT_ID_RE, "tournament.id")
        tournament_name = _nonempty_string(tournament.get("name"), "tournament.name")
        category_id = _provider_id(tournament.get("categoryId"), _CATEGORY_ID_RE, "tournament.categoryId")
        category_name = _nonempty_string(tournament.get("categoryName"), "tournament.categoryName")
        rows = tournament.get("events")
        if type(rows) is not list:
            raise PcUpcomingDiscoveryError("tournament.events must be a list")
        for row in rows:
            events.append(
                _event_from_row(
                    row,
                    category_id=category_id,
                    category_name=category_name,
                    tournament_id=tournament_id,
                    tournament_name=tournament_name,
                    page_num=page_num,
                    raw_sha256=raw_hash,
                    observed_at=observed,
                )
            )
    if len(events) > PAGE_SIZE:
        raise PcUpcomingDiscoveryError("page event rows exceed the fixed page size")
    within_page: dict[str, PcUpcomingDiscoveredEvent] = {}
    for event in events:
        prior = within_page.get(event.event_id)
        if prior is not None and prior.identity_dict() != event.identity_dict():
            raise PcUpcomingDiscoveryError("conflicting duplicate event identity within page")
        within_page[event.event_id] = event
    return PcUpcomingPageEvidence(
        page_num=page_num,
        request_target=target,
        request_nonce_ms=request_nonce_ms,
        observed_at=observed,
        raw_sha256=raw_hash,
        raw_size=len(raw),
        total_num=total_num,
        tournament_count=len(tournaments),
        event_count=len(events),
        events=tuple(events),
        raw_relative_path=f"pages/page-{page_num:03d}.raw.json",
        raw_bytes=raw,
    )


def _dedupe_pages(pages: tuple[PcUpcomingPageEvidence, ...]) -> tuple[PcUpcomingDiscoveredEvent, ...]:
    by_id: dict[str, PcUpcomingDiscoveredEvent] = {}
    for page in pages:
        for event in page.events:
            prior = by_id.get(event.event_id)
            if prior is None:
                by_id[event.event_id] = event
            elif prior.identity_dict() != event.identity_dict():
                raise PcUpcomingDiscoveryError("conflicting duplicate event ID across pages")
    return tuple(by_id[key] for key in sorted(by_id))


@dataclasses.dataclass(frozen=True)
class PcUpcomingDiscoveryManifest:
    schema_version: int
    dataset: str
    provider: str
    provider_region: str
    source_method: str
    policy_id: str
    policy_sha256: str
    pages: tuple[PcUpcomingPageEvidence, ...]
    events: tuple[PcUpcomingDiscoveredEvent, ...]
    first_observed_at: datetime
    last_observed_at: datetime
    provider_total_num: int
    captured_event_count: int
    captured_page_count: int
    pagination_complete: bool
    pagination_completion_basis: str
    coverage_horizon_hours: int
    market_filter: int
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or type(self.schema_version) is not int:
            raise PcUpcomingDiscoveryError("manifest schema version mismatch")
        if (self.dataset, self.provider, self.provider_region, self.source_method, self.policy_id) != (DATASET_NAME, PROVIDER, PROVIDER_REGION, SOURCE_METHOD, POLICY_ID):
            raise PcUpcomingDiscoveryError("manifest source identity mismatch")
        if self.policy_sha256 != calculate_policy_sha256():
            raise PcUpcomingDiscoveryError("manifest policy SHA differs")
        if type(self.pages) is not tuple or not self.pages or any(type(page) is not PcUpcomingPageEvidence for page in self.pages):
            raise PcUpcomingDiscoveryError("manifest pages must be a non-empty tuple")
        if len(self.pages) > MAX_PAGES:
            raise PcUpcomingDiscoveryError("manifest captured pages exceed MAX_PAGES")
        numbers = tuple(page.page_num for page in self.pages)
        if numbers != tuple(range(1, len(numbers) + 1)):
            raise PcUpcomingDiscoveryError("pages must be contiguous from page 1")
        totals = {page.total_num for page in self.pages}
        if len(totals) != 1:
            raise PcUpcomingDiscoveryError("provider totalNum drifted across pages")
        total_num = next(iter(totals))
        expected_pages = max(1, math.ceil(total_num / PAGE_SIZE))
        if len(self.pages) > expected_pages:
            raise PcUpcomingDiscoveryError("captured pages exceed provider-required page range")
        if expected_pages > MAX_PAGES and len(self.pages) >= expected_pages:
            raise PcUpcomingDiscoveryError("pagination beyond MAX_PAGES cannot be asserted complete")
        events = _dedupe_pages(self.pages)
        if self.events != events:
            raise PcUpcomingDiscoveryError("manifest events differ from replayed page rows")
        expected_complete = len(self.pages) == expected_pages and len(events) == total_num and expected_pages <= MAX_PAGES
        if type(self.pagination_complete) is not bool or self.pagination_complete != expected_complete:
            raise PcUpcomingDiscoveryError("pagination completeness claim is not supported")
        expected_basis = (
            "CONTIGUOUS_REQUIRED_PAGES_AND_UNIQUE_EVENT_COUNT_EQUAL_PROVIDER_TOTAL_NUM"
            if expected_complete
            else "INCOMPLETE_CAPTURE_DOES_NOT_PROVE_PROVIDER_ABSENCE"
        )
        if self.pagination_completion_basis != expected_basis:
            raise PcUpcomingDiscoveryError("pagination completion basis mismatch")
        if type(self.coverage_horizon_hours) is not int or type(self.market_filter) is not int or (self.coverage_horizon_hours, self.market_filter) != (TIMELINE_HOURS, int(MARKET_ID)):
            raise PcUpcomingDiscoveryError("manifest query scope mismatch")
        if dict(self.authority) != AUTHORITY or any(type(value) is not bool for value in self.authority.values()):
            raise PcUpcomingDiscoveryError("source contract authority must remain evidence-only")
        object.__setattr__(self, "authority", types.MappingProxyType(dict(self.authority)))
        first = min(page.observed_at for page in self.pages)
        last = max(page.observed_at for page in self.pages)
        if _utc(self.first_observed_at, "first_observed_at") != first or _utc(self.last_observed_at, "last_observed_at") != last:
            raise PcUpcomingDiscoveryError("manifest observation range differs from page completions")
        count_values = (self.provider_total_num, self.captured_event_count, self.captured_page_count)
        if any(type(value) is not int or value < 0 for value in count_values) or count_values != (total_num, len(events), len(self.pages)):
            raise PcUpcomingDiscoveryError("manifest counts differ from page evidence")

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.semantic_dict())).hexdigest()

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset": self.dataset,
            "provider": self.provider,
            "provider_region": self.provider_region,
            "source_method": self.source_method,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "pages": [page.to_dict() for page in self.pages],
            "events": [event.to_dict() for event in self.events],
            "first_observed_at": _utc_text(self.first_observed_at),
            "last_observed_at": _utc_text(self.last_observed_at),
            "provider_total_num": self.provider_total_num,
            "captured_event_count": self.captured_event_count,
            "captured_page_count": self.captured_page_count,
            "pagination_complete": self.pagination_complete,
            "pagination_completion_basis": self.pagination_completion_basis,
            "coverage_horizon_hours": self.coverage_horizon_hours,
            "market_filter": self.market_filter,
            "authority": dict(self.authority),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.semantic_dict(), "canonical_sha256": self.canonical_sha256}


def build_manifest(pages: tuple[PcUpcomingPageEvidence, ...] | list[PcUpcomingPageEvidence]) -> PcUpcomingDiscoveryManifest:
    page_tuple = tuple(pages)
    if not page_tuple:
        raise PcUpcomingDiscoveryError("at least one page is required")
    if len(page_tuple) > MAX_PAGES:
        raise PcUpcomingDiscoveryError("captured page count exceeds MAX_PAGES")
    events = _dedupe_pages(page_tuple)
    total = page_tuple[0].total_num
    expected_pages = max(1, math.ceil(total / PAGE_SIZE))
    complete = len(page_tuple) == expected_pages and len(events) == total and expected_pages <= MAX_PAGES
    return PcUpcomingDiscoveryManifest(
        schema_version=SCHEMA_VERSION,
        dataset=DATASET_NAME,
        provider=PROVIDER,
        provider_region=PROVIDER_REGION,
        source_method=SOURCE_METHOD,
        policy_id=POLICY_ID,
        policy_sha256=calculate_policy_sha256(),
        pages=page_tuple,
        events=events,
        first_observed_at=min(page.observed_at for page in page_tuple),
        last_observed_at=max(page.observed_at for page in page_tuple),
        provider_total_num=total,
        captured_event_count=len(events),
        captured_page_count=len(page_tuple),
        pagination_complete=complete,
        pagination_completion_basis=(
            "CONTIGUOUS_REQUIRED_PAGES_AND_UNIQUE_EVENT_COUNT_EQUAL_PROVIDER_TOTAL_NUM"
            if complete
            else "INCOMPLETE_CAPTURE_DOES_NOT_PROVE_PROVIDER_ABSENCE"
        ),
        coverage_horizon_hours=TIMELINE_HOURS,
        market_filter=int(MARKET_ID),
        authority=dict(AUTHORITY),
    )


def provider_identity_projection_bytes(value: PcUpcomingDiscoveryManifest | PcUpcomingPageEvidence) -> bytes:
    if type(value) is PcUpcomingPageEvidence:
        events = value.events
    elif type(value) is PcUpcomingDiscoveryManifest:
        events = value.events
    else:
        raise PcUpcomingDiscoveryError("projection requires exact page or manifest evidence")
    rows = []
    for event in events:
        sport_projection: dict[str, Any] = {}
        if event.source_sport_id is not None:
            sport_projection["id"] = event.source_sport_id
        sport_projection["category"] = {
            "id": event.category_id,
            "name": event.category_name,
            "tournament": {"id": event.tournament_id, "name": event.tournament_name},
        }
        rows.append(
            {
                "eventId": event.event_id,
                "estimateStartTime": event.estimate_start_time_ms,
                "homeTeamId": event.home_team_id,
                "homeTeamName": event.home_team_name,
                "awayTeamId": event.away_team_id,
                "awayTeamName": event.away_team_name,
                "sport": sport_projection,
                "source_ancestry": {
                    "source_raw_sha256": event.source_raw_sha256,
                    "source_page_num": event.source_page_num,
                    "source_observed_at": _utc_text(event.source_observed_at),
                },
            }
        )
    return _canonical(
        {
            "dataset": "ATHENA_PC_UPCOMING_PROVIDER_IDENTITY_PROJECTION_V1",
            "projection_policy_id": "EXACT_NATIVE_FIELDS_DERIVED_FROM_REPLAYED_PC_UPCOMING_RAW_BYTES",
            "is_provider_response": False,
            "source_policy_id": POLICY_ID,
            "source_policy_sha256": calculate_policy_sha256(),
            "events": rows,
        }
    )


def _read_regular(path: Path, *, max_bytes: int) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise PcUpcomingDiscoveryError("evidence path is not a regular file")
        raw = path.read_bytes()
    except OSError as exc:
        raise PcUpcomingDiscoveryError("could not read source evidence bytes") from exc
    if not raw or len(raw) > max_bytes:
        raise PcUpcomingDiscoveryError("source evidence byte bound failed")
    return raw


def verify_current_pc_upcoming_discovery(
    *, repository_root: str | Path, manifest: Mapping[str, Any] | None = None
) -> PcUpcomingDiscoveryManifest:
    root = Path(repository_root) / EVIDENCE_ROOT
    if manifest is None:
        manifest_raw = _read_regular(root / "manifest.json", max_bytes=MAX_MANIFEST_BYTES)
        loaded = _strict_json_loads(manifest_raw)
    else:
        loaded = dict(manifest)
    expected_keys = {
        "schema_version", "dataset", "provider", "provider_region", "source_method", "policy_id", "policy_sha256",
        "pages", "events", "first_observed_at", "last_observed_at", "provider_total_num", "captured_event_count",
        "captured_page_count", "pagination_complete", "pagination_completion_basis", "coverage_horizon_hours", "market_filter",
        "authority", "canonical_sha256",
    }
    if type(loaded) is not dict or set(loaded) != expected_keys or type(loaded.get("pages")) is not list:
        raise PcUpcomingDiscoveryError("manifest shape mismatch")
    page_rows = loaded["pages"]
    pages: list[PcUpcomingPageEvidence] = []
    page_keys = {"page_num", "request_target", "request_nonce_ms", "observed_at", "raw_sha256", "raw_size", "total_num", "tournament_count", "event_count", "raw_relative_path"}
    for row in page_rows:
        if type(row) is not dict or set(row) != page_keys:
            raise PcUpcomingDiscoveryError("manifest page shape mismatch")
        relative = row["raw_relative_path"]
        expected_relative = f"pages/page-{row['page_num']:03d}.raw.json" if type(row["page_num"]) is int else ""
        if relative != expected_relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise PcUpcomingDiscoveryError("manifest raw page path is unsafe or unexpected")
        raw = _read_regular(root / relative, max_bytes=MAX_RESPONSE_BYTES)
        if hashlib.sha256(raw).hexdigest() != row["raw_sha256"] or len(raw) != row["raw_size"]:
            raise PcUpcomingDiscoveryError("raw page bytes do not match manifest hash/size")
        page = parse_page(
            raw,
            page_num=row["page_num"],
            request_nonce_ms=row["request_nonce_ms"],
            observed_at=_parse_utc_text(row["observed_at"], "page observed_at"),
        )
        if page.to_dict() != row:
            raise PcUpcomingDiscoveryError("manifest page metadata differs from raw replay")
        pages.append(page)
    rebuilt = build_manifest(tuple(pages))
    if rebuilt.to_dict() != loaded:
        raise PcUpcomingDiscoveryError("manifest projection differs from exact raw replay")
    return rebuilt


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, response: Any, code: int, msg: str, headers: Any, new_url: str) -> None:
        return None


def _fetch_page(page_num: int, nonce: int) -> tuple[bytes, datetime]:
    request = Request(request_url(page_num, nonce), method="GET", headers=dict(REQUEST_HEADERS))
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # A single attempt only: no retry and no redirect is followed.
        raise PcUpcomingDiscoveryError(f"provider returned HTTP {int(exc.code)}") from exc
    except URLError as exc:
        raise PcUpcomingDiscoveryError("provider request failed; retries are disabled") from exc
    observed = datetime.now(timezone.utc)
    if status != 200:
        raise PcUpcomingDiscoveryError(f"provider returned HTTP {status}")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise PcUpcomingDiscoveryError("provider response exceeds the fixed byte bound")
    return raw, observed


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
    except OSError as exc:
        raise PcUpcomingDiscoveryError("could not persist non-overwriting source evidence") from exc


def capture_current_pc_upcoming_discovery(
    *, repository_root: str | Path, execute_live_network: bool
) -> PcUpcomingDiscoveryManifest:
    """Explicitly gated fixed-query capture; tests and audits must never call live."""
    if execute_live_network is not True:
        raise PcUpcomingDiscoveryError("network capture requires explicit execute_live_network=True")
    root = Path(repository_root) / EVIDENCE_ROOT
    if root.exists():
        raise PcUpcomingDiscoveryError("refusing to overwrite an existing evidence capture")
    root.mkdir(parents=True, exist_ok=False)
    pages: list[PcUpcomingPageEvidence] = []
    required_pages: int | None = None
    for page_num in range(1, MAX_PAGES + 1):
        if required_pages is not None and page_num > required_pages:
            break
        nonce = int(time.time() * 1000)
        raw, observed = _fetch_page(page_num, nonce)
        page = parse_page(raw, page_num=page_num, request_nonce_ms=nonce, observed_at=observed)
        _write_exclusive(root / page.raw_relative_path, raw)
        pages.append(page)
        if required_pages is None:
            required_pages = max(1, math.ceil(page.total_num / PAGE_SIZE))
        elif page.total_num != pages[0].total_num:
            raise PcUpcomingDiscoveryError("provider totalNum changed across pages; capture is incomplete")
    if required_pages is None:
        raise PcUpcomingDiscoveryError("no page was captured")
    manifest = build_manifest(tuple(pages))
    manifest_bytes = _canonical(manifest.to_dict(), newline=True)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise PcUpcomingDiscoveryError("manifest exceeds the fixed evidence byte bound")
    _write_exclusive(root / "manifest.json", manifest_bytes)
    return manifest
