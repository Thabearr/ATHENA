"""PR-F provider-catalog fanout discovery with exact current FotMob reconciliation.

This research-only boundary expands current anonymous SportyBet discovery using the
provider's own public football catalogue.  Active category/tournament identities
come only from the exact current ``sportList`` response; those identities are then
used to query the already proven anonymous upcoming-events endpoint.  No caller,
fixture source, alias table, or heuristic may supply provider category/tournament
IDs.  Exact home/away/competition/full-UTC matching and PR246 direct-event
confirmation remain unchanged.

The fanout evidence is fully replayable: the catalogue response and every bounded
tournament response are retained byte-for-byte with request targets, response
completion timestamps, hashes, and event ancestry.  This boundary grants only
fixture-reconciliation authority and never login, wallet, stake, BET, or wager
authority.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import types
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from domain import current_shadow_sportybet_upcoming_reconciliation as upcoming
from domain import sportybet_current_event_discovery_reconciliation as reviewed
from domain import sportybet_live_event_quote_evidence as live
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest
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
DATASET_NAME = "athena-current-shadow-sportybet-catalog-fanout-reconciliation-v1"
DISCOVERY_DATASET_NAME = "athena-current-shadow-sportybet-catalog-fanout-discovery-v1"
STATUS = "RESEARCH_SHADOW_PROVIDER_CATALOG_FANOUT_EXACT_RECONCILIATION_VERIFIED"
PROVIDER = "SportyBet"
PROVIDER_REGION = "Nigeria"
ORIGIN = live.ORIGIN
OPER_ID = live.OPER_ID
FOOTBALL_SPORT_ID = reviewed.FOOTBALL_SPORT_ID
CATALOG_PATH = "/api/ng/factsCenter/sportList"
UPCOMING_PATH = upcoming.UPCOMING_PATH
CATALOG_SOURCE_METHOD = "PUBLIC_ANONYMOUS_FACTS_CENTER_SPORT_LIST_GET"
FANOUT_SOURCE_METHOD = "PROVIDER_CATALOG_SUPPLIED_CATEGORY_TOURNAMENT_UPCOMING_GET"
MAX_RESPONSE_BYTES = upcoming.MAX_RESPONSE_BYTES
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_SOURCE_AGE_SECONDS = reviewed.MAX_SOURCE_AGE_SECONDS
MINIMUM_LEAD_SECONDS = reviewed.MINIMUM_LEAD_SECONDS
REQUEST_NONCE_MAX_SKEW_MS = upcoming.REQUEST_NONCE_MAX_SKEW_MS
REQUEST_HEADERS = reviewed.REQUEST_HEADERS
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/current-shadow-sportybet-catalog-fanout"
)
CATALOG_RAW_FILENAME = "catalog.raw.json"
MANIFEST_FILENAME = "manifest.json"
TOURNAMENT_DIRNAME = "tournaments"
MATCHING_BASIS = reviewed.MATCHING_BASIS
DETAIL_CONFIRMATION_POLICY = reviewed.DETAIL_CONFIRMATION_POLICY
CATALOG_IDENTITY_POLICY = (
    "EXACT_CURRENT_PROVIDER_SPORTLIST_FOOTBALL_CATEGORY_TOURNAMENT_IDENTITIES_ONLY"
)
FANOUT_POLICY = (
    "ACTIVE_EVENTSIZE_POSITIVE_PROVIDER_CATALOG_PAIRS_ONLY_NO_CALLER_IDS_NO_GUESSING"
)
OBSERVATION_AUTHORITY = (
    "ATHENA_PROVIDER_RESPONSE_COMPLETION_NOT_PROVIDER_EVENT_TIMESTAMP"
)
NEXT_BOUNDARY = "CURRENT_SHADOW_PRICE_ALL_EXACT_PROVIDER_EVENT_EVIDENCE_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "421613388a13ca6000e83e988fd34cb6ea93dca15ca4b0bab3b04c72a7e4d438"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_CATEGORY_RE = re.compile(r"^sr:category:.+$", re.ASCII)
_TOURNAMENT_RE = re.compile(r"^sr:(?:tournament|simple_tournament):.+$", re.ASCII)

AUTHORITY = types.MappingProxyType(
    {
        "provider_catalog_discovery": True,
        "provider_catalog_fanout": True,
        "current_event_detail_confirmation": True,
        "fixture_reconciliation": True,
        "canonical_market_mapping": False,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "final_selection": False,
        "accumulator_slip_construction": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)

CurrentEventReconciliationDisposition = reviewed.CurrentEventReconciliationDisposition
CurrentEventReconciliationRow = reviewed.CurrentEventReconciliationRow


class CurrentShadowSportyBetCatalogFanoutReconciliationError(ValueError):
    """Raised when provider-catalog fanout evidence cannot be proven exactly."""


SportyBetCurrentEventDiscoveryError = CurrentShadowSportyBetCatalogFanoutReconciliationError


def _canonical(value: Any, *, newline: bool = False) -> bytes:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "canonical JSON serialization failed"
        ) from exc
    return raw + (b"\n" if newline else b"")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            f"{label} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            f"{label} must be exact non-empty trimmed text"
        )
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            f"{label} must be exact SHA-256"
        )
    return value


def catalog_request_target() -> str:
    return CATALOG_PATH + "?" + urlencode((("sportId", FOOTBALL_SPORT_ID),))


def tournament_request_target(
    *, category_id: str, tournament_id: str, request_nonce_ms: int
) -> str:
    if type(category_id) is not str or _CATEGORY_RE.fullmatch(category_id) is None:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("category_id invalid")
    if type(tournament_id) is not str or _TOURNAMENT_RE.fullmatch(tournament_id) is None:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("tournament_id invalid")
    if isinstance(request_nonce_ms, bool) or not isinstance(request_nonce_ms, int) or request_nonce_ms <= 0:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("request nonce invalid")
    return UPCOMING_PATH + "?" + urlencode(
        (
            ("sportId", FOOTBALL_SPORT_ID),
            ("categoryId", category_id),
            ("tournamentId", tournament_id),
            ("_t", request_nonce_ms),
        )
    )


def _validate_tournament_target(
    value: Any,
    *,
    category_id: str,
    tournament_id: str,
    observed_at: datetime,
) -> int:
    if type(value) is not str or not value.startswith("/"):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout request target invalid")
    parsed = urlsplit(value)
    if parsed.path != UPCOMING_PATH or parsed.fragment:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout request path drifted")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout request query invalid") from exc
    if set(query) != {"sportId", "categoryId", "tournamentId", "_t"}:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout request query keys drifted")
    if query["sportId"] != [FOOTBALL_SPORT_ID]:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout sport identity drifted")
    if query["categoryId"] != [category_id] or query["tournamentId"] != [tournament_id]:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout provider identity drifted")
    nonce_rows = query["_t"]
    if len(nonce_rows) != 1 or not nonce_rows[0].isdigit():
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout cache nonce invalid")
    nonce = int(nonce_rows[0])
    if nonce <= 0 or str(nonce) != nonce_rows[0]:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout cache nonce not canonical")
    observed_ms = int(_utc(observed_at, "observed_at").timestamp() * 1000)
    skew = observed_ms - nonce
    if skew < 0 or skew > REQUEST_NONCE_MAX_SKEW_MS:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "fanout cache nonce outside reviewed response-completion skew"
        )
    return nonce


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "provider": PROVIDER,
        "provider_region": PROVIDER_REGION,
        "origin": ORIGIN,
        "oper_id": OPER_ID,
        "football_sport_id": FOOTBALL_SPORT_ID,
        "catalog_path": CATALOG_PATH,
        "upcoming_path": UPCOMING_PATH,
        "catalog_source_method": CATALOG_SOURCE_METHOD,
        "fanout_source_method": FANOUT_SOURCE_METHOD,
        "catalog_identity_policy": CATALOG_IDENTITY_POLICY,
        "fanout_policy": FANOUT_POLICY,
        "matching_basis": MATCHING_BASIS,
        "detail_confirmation_policy": DETAIL_CONFIRMATION_POLICY,
        "max_response_bytes": MAX_RESPONSE_BYTES,
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "request_nonce_max_skew_ms": REQUEST_NONCE_MAX_SKEW_MS,
        "reviewed_reconciliation_contract_sha256": reviewed.EXPECTED_CONTRACT_SHA256,
        "upcoming_reconciliation_contract_sha256": upcoming.EXPECTED_CONTRACT_SHA256,
        "live_event_source_contract_sha256": live.EXPECTED_CONTRACT_SHA256,
        "authority": dict(AUTHORITY),
        "next_boundary": NEXT_BOUNDARY,
    }


def calculate_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical({"version": CONTRACT_VERSION, "semantics": _contract_payload()})
    ).hexdigest()


def validate_contract() -> Mapping[str, str]:
    try:
        reviewed_identity = reviewed.validate_current_event_discovery_contract()
        upcoming_identity = upcoming.validate_contract()
        live_identity = live.validate_direct_event_source_contract()
    except Exception as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "reviewed SportyBet dependencies drifted"
        ) from exc
    if reviewed_identity["current_event_discovery_contract_sha256"] != reviewed.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("reviewed reconciliation contract drifted")
    if upcoming_identity["contract_sha256"] != upcoming.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("upcoming reconciliation contract drifted")
    if live_identity["contract_sha256"] != live.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("live event source contract drifted")
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout contract drifted")
    return types.MappingProxyType({"contract_sha256": actual})


@dataclasses.dataclass(frozen=True)
class ProviderCatalogTournament:
    category_id: str
    category_name: str
    tournament_id: str
    tournament_name: str
    event_size: int

    def __post_init__(self) -> None:
        if _CATEGORY_RE.fullmatch(_text(self.category_id, "category_id")) is None:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("category_id invalid")
        _text(self.category_name, "category_name")
        if _TOURNAMENT_RE.fullmatch(_text(self.tournament_id, "tournament_id")) is None:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("tournament_id invalid")
        _text(self.tournament_name, "tournament_name")
        if isinstance(self.event_size, bool) or not isinstance(self.event_size, int) or self.event_size <= 0:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("active tournament event_size invalid")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ProviderTournamentObservation:
    category_id: str
    tournament_id: str
    request_target: str
    request_nonce_ms: int
    observed_at: datetime
    raw_sha256: str
    raw_size: int
    event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        nonce = _validate_tournament_target(
            self.request_target,
            category_id=self.category_id,
            tournament_id=self.tournament_id,
            observed_at=self.observed_at,
        )
        if self.request_nonce_ms != nonce:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("observation nonce mismatch")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        _sha(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("observation raw_size invalid")
        if type(self.event_ids) is not tuple or self.event_ids != tuple(sorted(self.event_ids)):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("observation event IDs must be sorted")
        if len(self.event_ids) != len(set(self.event_ids)):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("observation event IDs duplicate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_id": self.category_id,
            "tournament_id": self.tournament_id,
            "request_target": self.request_target,
            "request_nonce_ms": self.request_nonce_ms,
            "observed_at": serialize_utc(self.observed_at),
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "event_ids": list(self.event_ids),
        }


@dataclasses.dataclass(frozen=True)
class CurrentShadowSportyBetCatalogFanoutSnapshot:
    schema_version: int
    dataset_name: str
    provider: str
    provider_region: str
    catalog_source_method: str
    fanout_source_method: str
    football_sport_id: str
    catalog_request_target: str
    catalog_observed_at: datetime
    catalog_raw_sha256: str
    catalog_raw_size: int
    tournaments: tuple[ProviderCatalogTournament, ...]
    observations: tuple[ProviderTournamentObservation, ...]
    events: tuple[reviewed.SportyBetDiscoveredEvent, ...]
    observation_authority: str
    provider_event_timestamp: None
    provider_snapshot_id: None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or type(self.schema_version) is not int:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot schema mismatch")
        if self.dataset_name != DISCOVERY_DATASET_NAME:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot dataset mismatch")
        if (self.provider, self.provider_region) != (PROVIDER, PROVIDER_REGION):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot provider mismatch")
        if self.catalog_source_method != CATALOG_SOURCE_METHOD or self.fanout_source_method != FANOUT_SOURCE_METHOD:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot source method mismatch")
        if self.football_sport_id != FOOTBALL_SPORT_ID:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot sport mismatch")
        if self.catalog_request_target != catalog_request_target():
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog request target mismatch")
        object.__setattr__(self, "catalog_observed_at", _utc(self.catalog_observed_at, "catalog_observed_at"))
        _sha(self.catalog_raw_sha256, "catalog_raw_sha256")
        if type(self.catalog_raw_size) is not int or not 0 < self.catalog_raw_size <= MAX_RESPONSE_BYTES:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog raw_size invalid")
        if type(self.tournaments) is not tuple or any(type(x) is not ProviderCatalogTournament for x in self.tournaments):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot tournaments invalid")
        pairs = tuple((x.category_id, x.tournament_id) for x in self.tournaments)
        if pairs != tuple(sorted(pairs)) or len(pairs) != len(set(pairs)):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot tournament pairs invalid")
        if type(self.observations) is not tuple or any(type(x) is not ProviderTournamentObservation for x in self.observations):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot observations invalid")
        observation_pairs = tuple((x.category_id, x.tournament_id) for x in self.observations)
        if observation_pairs != pairs:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot did not observe every active catalog tournament exactly once")
        if type(self.events) is not tuple or any(type(x) is not reviewed.SportyBetDiscoveredEvent for x in self.events):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot events invalid")
        ids = tuple(x.event_id for x in self.events)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot events must be sorted and unique")
        raw_observations = {(x.raw_sha256, x.observed_at) for x in self.observations}
        if any((x.source_raw_sha256, x.source_observed_at) not in raw_observations for x in self.events):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("event ancestry escaped fanout observations")
        manifest_event_ids = sorted(event_id for obs in self.observations for event_id in obs.event_ids)
        if manifest_event_ids != sorted(ids):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("observation/event identity coverage mismatch")
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot observation authority mismatch")
        if self.provider_event_timestamp is not None or self.provider_snapshot_id is not None:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("snapshot cannot invent provider timestamp/snapshot ID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "provider_region": self.provider_region,
            "catalog_source_method": self.catalog_source_method,
            "fanout_source_method": self.fanout_source_method,
            "football_sport_id": self.football_sport_id,
            "catalog_request_target": self.catalog_request_target,
            "catalog_observed_at": serialize_utc(self.catalog_observed_at),
            "catalog_raw_sha256": self.catalog_raw_sha256,
            "catalog_raw_size": self.catalog_raw_size,
            "active_tournament_count": len(self.tournaments),
            "tournaments": [x.to_dict() for x in self.tournaments],
            "observation_count": len(self.observations),
            "observations": [x.to_dict() for x in self.observations],
            "event_count": len(self.events),
            "events": [x.to_dict() for x in self.events],
            "observation_authority": self.observation_authority,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


def _network_get(target: str) -> tuple[bytes, datetime]:
    request = Request(ORIGIN + target, method="GET", headers=dict(REQUEST_HEADERS))
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
    except URLError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            f"SportyBet provider request failed: {exc.reason}"
        ) from exc
    observed_at = _now_utc()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("SportyBet response exceeds byte bound")
    if status != 200 or not raw:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
            f"SportyBet provider response returned HTTP {status}"
        )
    return raw, observed_at


def _parse_catalog(raw: bytes) -> tuple[ProviderCatalogTournament, ...]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog response must be bounded non-empty bytes")
    try:
        payload = live.strict_json_loads(raw)
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    if type(payload) is not dict or payload.get("bizCode") != 10000:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog provider response must be successful")
    data = payload.get("data")
    if type(data) is not list:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog data must be a list")
    football = [row for row in data if type(row) is dict and row.get("id") == FOOTBALL_SPORT_ID]
    if len(football) != 1:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog must contain exactly one football row")
    categories = football[0].get("categories")
    if type(categories) is not list:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("football catalog categories must be a list")
    active: list[ProviderCatalogTournament] = []
    seen_pairs: set[tuple[str, str]] = set()
    for category in categories:
        if type(category) is not dict:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog category row must be object")
        category_id = _text(category.get("id"), "catalog category id")
        category_name = _text(category.get("name"), "catalog category name")
        if _CATEGORY_RE.fullmatch(category_id) is None:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog category ID invalid")
        tournaments = category.get("tournaments")
        if type(tournaments) is not list:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog tournaments must be a list")
        for tournament in tournaments:
            if type(tournament) is not dict:
                raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog tournament row must be object")
            tournament_id = _text(tournament.get("id"), "catalog tournament id")
            tournament_name = _text(tournament.get("name"), "catalog tournament name")
            if _TOURNAMENT_RE.fullmatch(tournament_id) is None:
                raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog tournament ID invalid")
            event_size = tournament.get("eventSize")
            if isinstance(event_size, bool) or not isinstance(event_size, int) or event_size < 0:
                raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog eventSize invalid")
            pair = (category_id, tournament_id)
            if pair in seen_pairs:
                raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog category/tournament pair duplicated")
            seen_pairs.add(pair)
            if event_size == 0:
                continue
            active.append(ProviderCatalogTournament(
                category_id=category_id,
                category_name=category_name,
                tournament_id=tournament_id,
                tournament_name=tournament_name,
                event_size=event_size,
            ))
    return tuple(sorted(active, key=lambda x: (x.category_id, x.tournament_id)))


def _parse_tournament_response(
    raw: bytes,
    *,
    category_id: str,
    tournament_id: str,
    request_nonce_ms: int,
    observed_at: datetime,
) -> tuple[ProviderTournamentObservation, tuple[reviewed.SportyBetDiscoveredEvent, ...]]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout response must be bounded non-empty bytes")
    try:
        payload = live.strict_json_loads(raw)
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    if type(payload) is not dict or payload.get("bizCode") != 10000:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout provider response must be successful")
    data = payload.get("data")
    if type(data) is not list:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout data must be a list")
    raw_hash = sha256_bytes(raw)
    observed = _utc(observed_at, "observed_at")
    events: list[reviewed.SportyBetDiscoveredEvent] = []
    for row in data:
        if type(row) is not dict:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout event row must be object")
        try:
            event = reviewed._event_from_mapping(
                row,
                inherited_competition=None,
                page_num=1,
                raw_sha256=raw_hash,
                observed_at=observed,
            )
        except reviewed.SportyBetCurrentEventDiscoveryError as exc:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
        events.append(event)
    ids = [x.event_id for x in events]
    if len(ids) != len(set(ids)):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout response contains duplicate event IDs")
    target = tournament_request_target(
        category_id=category_id,
        tournament_id=tournament_id,
        request_nonce_ms=request_nonce_ms,
    )
    observation = ProviderTournamentObservation(
        category_id=category_id,
        tournament_id=tournament_id,
        request_target=target,
        request_nonce_ms=request_nonce_ms,
        observed_at=observed,
        raw_sha256=raw_hash,
        raw_size=len(raw),
        event_ids=tuple(sorted(ids)),
    )
    return observation, tuple(sorted(events, key=lambda x: x.event_id))


def _evidence_root(repository_root: Path, *, create: bool) -> Path:
    try:
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("repository_root must resolve to an existing directory") from exc
    if repository.is_symlink() or not repository.is_dir():
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("repository_root must be a regular directory")
    root = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        _reject_symlink_components(root, "catalog fanout evidence root")
        if create:
            _ensure_directory_tree_durable(root, boundary=repository)
        else:
            resolved = root.resolve(strict=True)
            resolved.relative_to(repository)
            if resolved.is_symlink() or not resolved.is_dir():
                raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout evidence root invalid")
    except CurrentShadowSportyBetCatalogFanoutReconciliationError:
        raise
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout evidence root invalid") from exc
    return root


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(f"refusing to overwrite {path.name}") from exc
    except OSError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(f"could not durably write {path.name}") from exc


def _raw_filename(observation: ProviderTournamentObservation) -> str:
    pair_hash = hashlib.sha256(
        _canonical({"category_id": observation.category_id, "tournament_id": observation.tournament_id})
    ).hexdigest()
    return f"pair-{pair_hash[:24]}-{observation.raw_sha256[:16]}.json"


def _snapshot_from_parts(
    *,
    catalog_raw: bytes,
    catalog_observed_at: datetime,
    tournaments: tuple[ProviderCatalogTournament, ...],
    observations: tuple[ProviderTournamentObservation, ...],
    events: Sequence[reviewed.SportyBetDiscoveredEvent],
) -> CurrentShadowSportyBetCatalogFanoutSnapshot:
    try:
        deduped = reviewed._dedupe_events(tuple(events))
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    return CurrentShadowSportyBetCatalogFanoutSnapshot(
        schema_version=SCHEMA_VERSION,
        dataset_name=DISCOVERY_DATASET_NAME,
        provider=PROVIDER,
        provider_region=PROVIDER_REGION,
        catalog_source_method=CATALOG_SOURCE_METHOD,
        fanout_source_method=FANOUT_SOURCE_METHOD,
        football_sport_id=FOOTBALL_SPORT_ID,
        catalog_request_target=catalog_request_target(),
        catalog_observed_at=_utc(catalog_observed_at, "catalog_observed_at"),
        catalog_raw_sha256=sha256_bytes(catalog_raw),
        catalog_raw_size=len(catalog_raw),
        tournaments=tournaments,
        observations=observations,
        events=deduped,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_event_timestamp=None,
        provider_snapshot_id=None,
    )


def capture_current_catalog_fanout_discovery(
    *, repository_root: Path, execute_live_network: bool
) -> tuple[Path, CurrentShadowSportyBetCatalogFanoutSnapshot]:
    validate_contract()
    if execute_live_network is not True:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("live catalog fanout requires execute_live_network=True")
    repository = Path(repository_root).resolve(strict=True)
    catalog_raw, catalog_observed = _network_get(catalog_request_target())
    tournaments = _parse_catalog(catalog_raw)
    if not tournaments:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("provider football catalog has no active tournaments")
    observations: list[ProviderTournamentObservation] = []
    events: list[reviewed.SportyBetDiscoveredEvent] = []
    raw_by_pair: dict[tuple[str, str], bytes] = {}
    for tournament in tournaments:
        nonce = int(time.time() * 1000)
        target = tournament_request_target(
            category_id=tournament.category_id,
            tournament_id=tournament.tournament_id,
            request_nonce_ms=nonce,
        )
        raw, observed = _network_get(target)
        observation, parsed = _parse_tournament_response(
            raw,
            category_id=tournament.category_id,
            tournament_id=tournament.tournament_id,
            request_nonce_ms=nonce,
            observed_at=observed,
        )
        observations.append(observation)
        events.extend(parsed)
        raw_by_pair[(tournament.category_id, tournament.tournament_id)] = raw
    ordered_observations = tuple(sorted(observations, key=lambda x: (x.category_id, x.tournament_id)))
    snapshot = _snapshot_from_parts(
        catalog_raw=catalog_raw,
        catalog_observed_at=catalog_observed,
        tournaments=tournaments,
        observations=ordered_observations,
        events=events,
    )
    root = _evidence_root(repository, create=True)
    directory = root / snapshot.canonical_sha256[:24]
    manifest_bytes = _canonical(snapshot.to_dict(), newline=True)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout manifest exceeds byte bound")
    if directory.exists():
        existing = verify_current_catalog_fanout_discovery(directory, repository_root=repository)
        if existing.to_dict() != snapshot.to_dict():
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout capture identity collision")
        return directory, existing
    directory.mkdir(exist_ok=False)
    tournament_dir = directory / TOURNAMENT_DIRNAME
    tournament_dir.mkdir(exist_ok=False)
    _sync_directory(root)
    _sync_directory(directory)
    _sync_directory(tournament_dir)
    _write_exclusive(directory / CATALOG_RAW_FILENAME, catalog_raw)
    for observation in ordered_observations:
        raw = raw_by_pair[(observation.category_id, observation.tournament_id)]
        _write_exclusive(tournament_dir / _raw_filename(observation), raw)
    _write_exclusive(directory / MANIFEST_FILENAME, manifest_bytes)
    verified = verify_current_catalog_fanout_discovery(directory, repository_root=repository)
    _sync_directory(tournament_dir)
    _sync_directory(directory)
    _sync_directory(root)
    return directory, verified


def _event_from_mapping(value: Any) -> reviewed.SportyBetDiscoveredEvent:
    if type(value) is not dict:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("manifest event row invalid")
    try:
        return reviewed.SportyBetDiscoveredEvent(
            event_id=value["event_id"],
            home_team_name=value["home_team_name"],
            away_team_name=value["away_team_name"],
            competition_name=value["competition_name"],
            competition_basis=value["competition_basis"],
            kickoff_utc=parse_utc_timestamp(value["kickoff_utc"], "event kickoff_utc"),
            booking_status=value["booking_status"],
            event_status=value["event_status"],
            match_status=value["match_status"],
            prematch_bookable_observed=value["prematch_bookable_observed"],
            source_page_num=value["source_page_num"],
            source_raw_sha256=value["source_raw_sha256"],
            source_observed_at=parse_utc_timestamp(value["source_observed_at"], "event source_observed_at"),
        )
    except (KeyError, TypeError, ValueError, SportyBetLiteCaptureError, reviewed.SportyBetCurrentEventDiscoveryError) as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("manifest event row invalid") from exc


def _snapshot_from_manifest(value: Any) -> CurrentShadowSportyBetCatalogFanoutSnapshot:
    expected = {
        "schema_version", "dataset_name", "provider", "provider_region",
        "catalog_source_method", "fanout_source_method", "football_sport_id",
        "catalog_request_target", "catalog_observed_at", "catalog_raw_sha256",
        "catalog_raw_size", "active_tournament_count", "tournaments",
        "observation_count", "observations", "event_count", "events",
        "observation_authority", "provider_event_timestamp", "provider_snapshot_id",
    }
    if type(value) is not dict or set(value) != expected:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout manifest keys mismatch")
    try:
        tournaments = tuple(ProviderCatalogTournament(**row) for row in value["tournaments"])
        observations = tuple(
            ProviderTournamentObservation(
                category_id=row["category_id"],
                tournament_id=row["tournament_id"],
                request_target=row["request_target"],
                request_nonce_ms=row["request_nonce_ms"],
                observed_at=parse_utc_timestamp(row["observed_at"], "observation observed_at"),
                raw_sha256=row["raw_sha256"],
                raw_size=row["raw_size"],
                event_ids=tuple(row["event_ids"]),
            )
            for row in value["observations"]
        )
        events = tuple(_event_from_mapping(row) for row in value["events"])
        if value["active_tournament_count"] != len(tournaments) or value["observation_count"] != len(observations) or value["event_count"] != len(events):
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout manifest counts mismatch")
        return CurrentShadowSportyBetCatalogFanoutSnapshot(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            provider=value["provider"],
            provider_region=value["provider_region"],
            catalog_source_method=value["catalog_source_method"],
            fanout_source_method=value["fanout_source_method"],
            football_sport_id=value["football_sport_id"],
            catalog_request_target=value["catalog_request_target"],
            catalog_observed_at=parse_utc_timestamp(value["catalog_observed_at"], "catalog_observed_at"),
            catalog_raw_sha256=value["catalog_raw_sha256"],
            catalog_raw_size=value["catalog_raw_size"],
            tournaments=tournaments,
            observations=observations,
            events=events,
            observation_authority=value["observation_authority"],
            provider_event_timestamp=value["provider_event_timestamp"],
            provider_snapshot_id=value["provider_snapshot_id"],
        )
    except CurrentShadowSportyBetCatalogFanoutReconciliationError:
        raise
    except (KeyError, TypeError, ValueError, SportyBetLiteCaptureError) as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout manifest invalid") from exc


def verify_current_catalog_fanout_discovery(
    evidence_directory: Path, *, repository_root: Path
) -> CurrentShadowSportyBetCatalogFanoutSnapshot:
    validate_contract()
    root = _evidence_root(Path(repository_root), create=False)
    evidence = Path(evidence_directory)
    if ".." in evidence.parts:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout evidence path traversal rejected")
    try:
        _reject_symlink_components(evidence, "catalog fanout evidence directory")
        resolved = evidence.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout evidence directory escapes reviewed root") from exc
    if evidence.is_symlink() or not evidence.is_dir():
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout evidence must be regular directory")
    try:
        manifest_raw = _read_regular(evidence / MANIFEST_FILENAME, maximum=MAX_MANIFEST_BYTES, label="catalog fanout manifest")
        manifest_value = live.strict_json_loads(manifest_raw)
    except (SportyBetLiteCaptureError, live.SportyBetLiveEventQuoteEvidenceError) as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout manifest unreadable") from exc
    snapshot = _snapshot_from_manifest(manifest_value)
    expected_top = {CATALOG_RAW_FILENAME, MANIFEST_FILENAME, TOURNAMENT_DIRNAME}
    if {x.name for x in evidence.iterdir()} != expected_top:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout evidence directory contents mismatch")
    tournament_dir = evidence / TOURNAMENT_DIRNAME
    if tournament_dir.is_symlink() or not tournament_dir.is_dir():
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout tournament evidence directory invalid")
    catalog_raw = _read_regular(evidence / CATALOG_RAW_FILENAME, maximum=MAX_RESPONSE_BYTES, label="catalog raw")
    if sha256_bytes(catalog_raw) != snapshot.catalog_raw_sha256 or len(catalog_raw) != snapshot.catalog_raw_size:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog raw identity mismatch")
    tournaments = _parse_catalog(catalog_raw)
    if tournaments != snapshot.tournaments:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog active tournament replay differs")
    rebuilt_observations: list[ProviderTournamentObservation] = []
    rebuilt_events: list[reviewed.SportyBetDiscoveredEvent] = []
    expected_files: set[str] = set()
    for observation in snapshot.observations:
        filename = _raw_filename(observation)
        expected_files.add(filename)
        raw = _read_regular(tournament_dir / filename, maximum=MAX_RESPONSE_BYTES, label="fanout tournament raw")
        if sha256_bytes(raw) != observation.raw_sha256 or len(raw) != observation.raw_size:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout tournament raw identity mismatch")
        rebuilt_observation, events = _parse_tournament_response(
            raw,
            category_id=observation.category_id,
            tournament_id=observation.tournament_id,
            request_nonce_ms=observation.request_nonce_ms,
            observed_at=observation.observed_at,
        )
        if rebuilt_observation.to_dict() != observation.to_dict():
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout observation differs from exact raw replay")
        rebuilt_observations.append(rebuilt_observation)
        rebuilt_events.extend(events)
    if {x.name for x in tournament_dir.iterdir()} != expected_files:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout tournament evidence file set mismatch")
    rebuilt = _snapshot_from_parts(
        catalog_raw=catalog_raw,
        catalog_observed_at=snapshot.catalog_observed_at,
        tournaments=tournaments,
        observations=tuple(rebuilt_observations),
        events=rebuilt_events,
    )
    if rebuilt.to_dict() != snapshot.to_dict():
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout snapshot differs from retained-source replay")
    if evidence.name != snapshot.canonical_sha256[:24]:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("fanout evidence directory identity mismatch")
    return snapshot


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for key, value in values.items():
        object.__setattr__(obj, key, value)
    return obj


@dataclasses.dataclass(frozen=True, init=False)
class CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    schema_version: int
    dataset_name: str
    status: str
    evaluation_time: datetime
    max_source_age_seconds: int
    minimum_lead_seconds: int
    fanout_snapshot_sha256: str
    source_fotmob_admission_sha256: str
    source_fotmob_candidate_bundle_sha256: str
    source_fotmob_review_bundle_sha256: str
    source_fotmob_handoff_sha256: str
    source_fotmob_catalog_sha256: str
    source_fotmob_manifest_sha256: str
    fotmob_capture_identities: tuple[Mapping[str, Any], ...]
    rows: tuple[reviewed.CurrentEventReconciliationRow, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    contract_sha256: str
    _repository_root: Path
    _fanout_directory: Path
    _detail_directories: tuple[tuple[str, Path], ...]
    _fotmob_admission: Any
    _fotmob_captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout bundles are builder-only")

    @property
    def matched_rows(self) -> tuple[reviewed.CurrentEventReconciliationRow, ...]:
        return tuple(x for x in self.rows if x.fixture_reconciliation_authorized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "evaluation_time": serialize_utc(self.evaluation_time),
            "max_source_age_seconds": self.max_source_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "fanout_snapshot_sha256": self.fanout_snapshot_sha256,
            "source_fotmob_admission_sha256": self.source_fotmob_admission_sha256,
            "source_fotmob_candidate_bundle_sha256": self.source_fotmob_candidate_bundle_sha256,
            "source_fotmob_review_bundle_sha256": self.source_fotmob_review_bundle_sha256,
            "source_fotmob_handoff_sha256": self.source_fotmob_handoff_sha256,
            "source_fotmob_catalog_sha256": self.source_fotmob_catalog_sha256,
            "source_fotmob_manifest_sha256": self.source_fotmob_manifest_sha256,
            "fotmob_capture_identities": [dict(x) for x in self.fotmob_capture_identities],
            "event_count": len(self.rows),
            "matched_count": len(self.matched_rows),
            "rows": [x.to_dict() for x in self.rows],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "contract_sha256": self.contract_sha256,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
            "wager_placed": False,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


SportyBetCurrentEventDiscoveryReconciliationBundle = CurrentShadowSportyBetCatalogFanoutReconciliationBundle


def _build_bundle(
    *,
    repository_root: Path,
    fanout_directory: Path,
    fanout: CurrentShadowSportyBetCatalogFanoutSnapshot,
    admission: Any,
    captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
    detail_directories: Mapping[str, Path],
    evaluation_time: datetime,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    evaluation = _utc(evaluation_time, "evaluation_time")
    reviewed_rows = reviewed._reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in fanout.events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = reviewed._match_event(event, reviewed_rows)
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
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("direct event-detail evidence set mismatch")
    rows: list[reviewed.CurrentEventReconciliationRow] = []
    for event in fanout.events:
        state, matches = provisional[event.event_id]
        discovery_age = (evaluation - event.source_observed_at).total_seconds()
        kickoff_lead = (event.kickoff_utc - evaluation).total_seconds()
        if discovery_age < 0:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError("evaluation_time predates fanout response completion")
        disposition: reviewed.CurrentEventReconciliationDisposition
        matched_id: str | None = None
        direct_observed: datetime | None = None
        direct_age: float | None = None
        direct_manifest_sha: str | None = None
        direct_inventory_sha: str | None = None
        direct_raw_sha: str | None = None
        if discovery_age > MAX_SOURCE_AGE_SECONDS:
            disposition = reviewed.CurrentEventReconciliationDisposition.DISCOVERY_EVIDENCE_STALE
        elif kickoff_lead <= MINIMUM_LEAD_SECONDS:
            disposition = reviewed.CurrentEventReconciliationDisposition.PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF
        elif state == "NONBOOKABLE":
            disposition = reviewed.CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE
        elif state == "NO_COMPETITION":
            disposition = reviewed.CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN
        elif state == "NO_MATCH":
            disposition = reviewed.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
        elif state == "AMBIGUOUS_FOTMOB":
            disposition = reviewed.CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH
        elif target_counts[matches[0].source_fixture_identifier] > 1:
            disposition = reviewed.CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE
        else:
            matched = matches[0]
            matched_id = matched.source_fixture_identifier
            inventory = reviewed._detail_inventory_from_directory(detail_directories[event.event_id], repository_root=repository_root)
            direct_observed = inventory.observed_at
            direct_age = (evaluation - inventory.observed_at).total_seconds()
            if direct_age < 0:
                raise CurrentShadowSportyBetCatalogFanoutReconciliationError("evaluation_time predates direct event-detail response")
            direct_manifest_sha = inventory.source_manifest_sha256
            direct_inventory_sha = inventory.canonical_sha256
            direct_raw_sha = inventory.source_raw_sha256
            if (
                inventory.event_id != event.event_id
                or inventory.home_team_name != event.home_team_name
                or inventory.away_team_name != event.away_team_name
                or inventory.kickoff_utc != event.kickoff_utc
            ):
                disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH
            elif not inventory.prematch_bookable_observed:
                disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE
            elif direct_age > MAX_SOURCE_AGE_SECONDS:
                disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_STALE
            else:
                disposition = reviewed.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
        rows.append(reviewed.CurrentEventReconciliationRow(
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
                disposition is reviewed.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
            ),
        ))
    ordered = tuple(sorted(rows, key=lambda x: x.event_id))
    admission_payload = admission.to_dict()
    value = object.__new__(CurrentShadowSportyBetCatalogFanoutReconciliationBundle)
    return _set_frozen(value, {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "evaluation_time": evaluation,
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "fanout_snapshot_sha256": fanout.canonical_sha256,
        "source_fotmob_admission_sha256": reviewed.fotmob_admission.sha256_reviewed_fixture_catalog_admission(admission),
        "source_fotmob_candidate_bundle_sha256": admission_payload["candidate_bundle_sha256"],
        "source_fotmob_review_bundle_sha256": admission_payload["review_bundle_sha256"],
        "source_fotmob_handoff_sha256": admission_payload["handoff_sha256"],
        "source_fotmob_catalog_sha256": admission_payload["catalog_sha256"],
        "source_fotmob_manifest_sha256": admission_payload["manifest_sha256"],
        "fotmob_capture_identities": reviewed._capture_identity_rows(captures),
        "rows": ordered,
        "authority": reviewed._output_authority(ordered),
        "next_boundary": NEXT_BOUNDARY,
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "_repository_root": Path(repository_root),
        "_fanout_directory": Path(fanout_directory),
        "_detail_directories": tuple(sorted(((event_id, Path(path)) for event_id, path in detail_directories.items()), key=lambda x: x[0])),
        "_fotmob_admission": admission,
        "_fotmob_captures": captures,
    })


def reconcile_current_events_from_catalog_fanout(
    *,
    repository_root: Path,
    fanout_evidence_directory: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[tuple[bytes, FotMobDataMatchesCaptureManifest]],
    execute_live_network: bool,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    validate_contract()
    if execute_live_network is not True:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("direct confirmation requires execute_live_network=True")
    repository = Path(repository_root).resolve(strict=True)
    try:
        captures = reviewed._materialize_fotmob_captures(fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(fotmob_admission_value, captures)
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    fanout = verify_current_catalog_fanout_discovery(fanout_evidence_directory, repository_root=repository)
    reviewed_rows = reviewed._reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in fanout.events:
        if not event.prematch_bookable_observed:
            provisional[event.event_id] = ("NONBOOKABLE", ())
        elif event.competition_name is None:
            provisional[event.event_id] = ("NO_COMPETITION", ())
        else:
            matches = reviewed._match_event(event, reviewed_rows)
            if not matches:
                provisional[event.event_id] = ("NO_MATCH", ())
            elif len(matches) > 1:
                provisional[event.event_id] = ("AMBIGUOUS_FOTMOB", matches)
            else:
                provisional[event.event_id] = ("UNIQUE", matches)
    counts = Counter(matches[0].source_fixture_identifier for state, matches in provisional.values() if state == "UNIQUE")
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
            live.build_live_event_quote_inventory(directory, repository_root=repository)
        except live.SportyBetLiveEventQuoteEvidenceError as exc:
            raise CurrentShadowSportyBetCatalogFanoutReconciliationError(
                f"PR246 direct event-detail acquisition failed closed for {event_id}: {exc}"
            ) from exc
        detail_dirs[event_id] = directory
    return _build_bundle(
        repository_root=repository,
        fanout_directory=Path(fanout_evidence_directory),
        fanout=fanout,
        admission=admission,
        captures=captures,
        detail_directories=detail_dirs,
        evaluation_time=_now_utc(),
    )


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[tuple[bytes, FotMobDataMatchesCaptureManifest]],
    execute_live_network: bool,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    directory, _snapshot = capture_current_catalog_fanout_discovery(
        repository_root=repository_root,
        execute_live_network=execute_live_network,
    )
    return reconcile_current_events_from_catalog_fanout(
        repository_root=repository_root,
        fanout_evidence_directory=directory,
        fotmob_admission_value=fotmob_admission_value,
        fotmob_captures=fotmob_captures,
        execute_live_network=execute_live_network,
    )


def verify_current_event_discovery_reconciliation_bundle(
    value: Any,
) -> CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
    if type(value) is not CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("value must be exact catalog fanout reconciliation bundle")
    validate_contract()
    try:
        captures = reviewed._materialize_fotmob_captures(value._fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(value._fotmob_admission, captures)
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError(str(exc)) from exc
    fanout = verify_current_catalog_fanout_discovery(value._fanout_directory, repository_root=value._repository_root)
    rebuilt = _build_bundle(
        repository_root=value._repository_root,
        fanout_directory=value._fanout_directory,
        fanout=fanout,
        admission=admission,
        captures=captures,
        detail_directories=dict(value._detail_directories),
        evaluation_time=value.evaluation_time,
    )
    if _canonical(value.to_dict()) != _canonical(rebuilt.to_dict()):
        raise CurrentShadowSportyBetCatalogFanoutReconciliationError("catalog fanout reconciliation differs from retained-source replay")
    return rebuilt


__all__ = [
    "AUTHORITY",
    "CATALOG_IDENTITY_POLICY",
    "CATALOG_PATH",
    "CurrentEventReconciliationDisposition",
    "CurrentEventReconciliationRow",
    "CurrentShadowSportyBetCatalogFanoutReconciliationBundle",
    "CurrentShadowSportyBetCatalogFanoutReconciliationError",
    "CurrentShadowSportyBetCatalogFanoutSnapshot",
    "EXPECTED_CONTRACT_SHA256",
    "FANOUT_POLICY",
    "ProviderCatalogTournament",
    "ProviderTournamentObservation",
    "SportyBetCurrentEventDiscoveryError",
    "SportyBetCurrentEventDiscoveryReconciliationBundle",
    "calculate_contract_sha256",
    "capture_current_catalog_fanout_discovery",
    "catalog_request_target",
    "discover_and_reconcile_current_events",
    "reconcile_current_events_from_catalog_fanout",
    "tournament_request_target",
    "validate_contract",
    "verify_current_catalog_fanout_discovery",
    "verify_current_event_discovery_reconciliation_bundle",
]
