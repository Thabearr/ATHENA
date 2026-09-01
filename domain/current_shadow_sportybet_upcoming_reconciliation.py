"""PR-F research-only SportyBet upcoming-event reconciliation adapter.

This boundary mirrors the exact public anonymous upcoming-event acquisition path
that was already proven live by PR258, then preserves ATHENA's stricter current
fixture rule: only exact case-sensitive home/away/competition/full-UTC matches
against source-replayed reviewed FotMob fixtures may gain reconciliation
authority.  Every unique candidate is freshly confirmed through the reviewed
PR246 direct event-detail source before issuance.

The adapter exists only for the PR-F Shadow runner.  It does not alter the
shared PR251 discovery contract, PR252 mapping contract, production Phase 6,
provider execution authority, staking, or BET authority.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import math
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
from scripts import run_pr258_sportybet_live_transport_proof as pr258

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-current-shadow-sportybet-upcoming-reconciliation-v1"
DISCOVERY_DATASET_NAME = "athena-current-shadow-sportybet-upcoming-discovery-v1"
STATUS = "RESEARCH_SHADOW_PR258_UPCOMING_EXACT_RECONCILIATION_VERIFIED"
PROVIDER = "SportyBet"
PROVIDER_REGION = "Nigeria"
DISCOVERY_SOURCE_METHOD = "PUBLIC_ANONYMOUS_FACTS_CENTER_WAP_CONFIGURABLE_UPCOMING_EVENTS_GET"
ORIGIN = live.ORIGIN
OPER_ID = live.OPER_ID
UPCOMING_PATH = "/api/ng/factsCenter/wapConfigurableUpcomingEvents"
FOOTBALL_SPORT_ID = reviewed.FOOTBALL_SPORT_ID
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SOURCE_AGE_SECONDS = reviewed.MAX_SOURCE_AGE_SECONDS
MINIMUM_LEAD_SECONDS = reviewed.MINIMUM_LEAD_SECONDS
REQUEST_NONCE_MAX_SKEW_MS = 120_000
REQUEST_HEADERS = reviewed.REQUEST_HEADERS
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/current-shadow-sportybet-upcoming-discovery"
)
RAW_FILENAME = "upcoming.raw.json"
MANIFEST_FILENAME = "manifest.json"
OBSERVATION_AUTHORITY = (
    "ATHENA_PR258_UPCOMING_RESPONSE_COMPLETION_NOT_PROVIDER_EVENT_TIMESTAMP"
)
MATCHING_BASIS = reviewed.MATCHING_BASIS
DETAIL_CONFIRMATION_POLICY = reviewed.DETAIL_CONFIRMATION_POLICY
NEXT_BOUNDARY = "CURRENT_SHADOW_PRICE_ALL_EXACT_PROVIDER_EVENT_EVIDENCE_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "90c14bd68ed6e8205c16fedfa815d120c53f2af1a3a8f362eee2702a4223b9ff"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

AUTHORITY = types.MappingProxyType(
    {
        "pr258_upcoming_discovery": True,
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
        "wager_placed": False,
    }
)

CurrentEventReconciliationDisposition = reviewed.CurrentEventReconciliationDisposition
CurrentEventReconciliationRow = reviewed.CurrentEventReconciliationRow


class CurrentShadowSportyBetUpcomingReconciliationError(ValueError):
    """Raised when the PR-F upcoming discovery/reconciliation cannot prove its source."""


SportyBetCurrentEventDiscoveryError = CurrentShadowSportyBetUpcomingReconciliationError


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
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "canonical JSON serialization failed"
        ) from exc
    return raw + (b"\n" if newline else b"")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            f"{label} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            f"{label} must be exact SHA-256"
        )
    return value


def request_target(request_nonce_ms: Any) -> str:
    if isinstance(request_nonce_ms, bool) or not isinstance(request_nonce_ms, int) or request_nonce_ms <= 0:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "request_nonce_ms must be a positive integer"
        )
    query = urlencode((("sportId", FOOTBALL_SPORT_ID), ("_t", request_nonce_ms)))
    return f"{UPCOMING_PATH}?{query}"


def request_url(request_nonce_ms: Any) -> str:
    return ORIGIN + request_target(request_nonce_ms)


def _validate_request_target(value: Any, *, observed_at: datetime) -> int:
    if type(value) is not str or not value.startswith("/"):
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming request target is invalid"
        )
    parsed = urlsplit(value)
    if parsed.path != UPCOMING_PATH or parsed.fragment:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming request path drifted"
        )
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if set(query) != {"sportId", "_t"} or query["sportId"] != [FOOTBALL_SPORT_ID]:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming request query drifted"
        )
    nonce_rows = query["_t"]
    if len(nonce_rows) != 1 or not nonce_rows[0].isdigit():
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming request cache nonce is invalid"
        )
    nonce = int(nonce_rows[0])
    if nonce <= 0 or str(nonce) != nonce_rows[0]:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming request cache nonce is not canonical"
        )
    observed_ms = int(_utc(observed_at, "observed_at").timestamp() * 1000)
    skew = observed_ms - nonce
    if skew < 0 or skew > REQUEST_NONCE_MAX_SKEW_MS:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming request cache nonce is outside reviewed response-completion skew"
        )
    return nonce


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "discovery_source_method": DISCOVERY_SOURCE_METHOD,
        "origin": ORIGIN,
        "oper_id": OPER_ID,
        "upcoming_path": UPCOMING_PATH,
        "football_sport_id": FOOTBALL_SPORT_ID,
        "request_headers": [list(item) for item in REQUEST_HEADERS],
        "request_nonce_max_skew_ms": REQUEST_NONCE_MAX_SKEW_MS,
        "max_response_bytes": MAX_RESPONSE_BYTES,
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "matching_basis": MATCHING_BASIS,
        "detail_confirmation_policy": DETAIL_CONFIRMATION_POLICY,
        "reviewed_reconciliation_contract_sha256": reviewed.EXPECTED_CONTRACT_SHA256,
        "live_event_source_contract_sha256": live.EXPECTED_CONTRACT_SHA256,
        "pr258_upcoming_path": pr258.UPCOMING_PATH,
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(AUTHORITY),
    }


def calculate_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical({"version": CONTRACT_VERSION, "semantics": _contract_payload()})
    ).hexdigest()


def validate_contract() -> Mapping[str, str]:
    try:
        reviewed_identity = reviewed.validate_current_event_discovery_contract()
        live_identity = live.validate_direct_event_source_contract()
    except Exception as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "reviewed SportyBet dependencies drifted"
        ) from exc
    if pr258.UPCOMING_PATH != UPCOMING_PATH:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "PR258 proven upcoming-event endpoint drifted"
        )
    if pr258.MAX_RESPONSE_BYTES != MAX_RESPONSE_BYTES:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "PR258 upcoming-event byte bound drifted"
        )
    if reviewed_identity["current_event_discovery_contract_sha256"] != reviewed.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "reviewed exact reconciliation contract drifted"
        )
    if live_identity["contract_sha256"] != live.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "reviewed direct event-detail contract drifted"
        )
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "PR-F upcoming reconciliation contract drifted"
        )
    return types.MappingProxyType(
        {
            "contract_sha256": actual,
            "reviewed_reconciliation_contract_sha256": reviewed.EXPECTED_CONTRACT_SHA256,
            "live_event_source_contract_sha256": live.EXPECTED_CONTRACT_SHA256,
        }
    )


def _evidence_root(repository_root: Path, *, create: bool) -> Path:
    try:
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "repository_root must resolve to an existing directory"
        ) from exc
    if repository.is_symlink() or not repository.is_dir():
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "repository_root must be a regular directory"
        )
    root = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        _reject_symlink_components(root, "PR-F upcoming evidence root")
        if create:
            _ensure_directory_tree_durable(root, boundary=repository)
        else:
            resolved = root.resolve(strict=True)
            resolved.relative_to(repository)
            if resolved.is_symlink() or not resolved.is_dir():
                raise CurrentShadowSportyBetUpcomingReconciliationError(
                    "PR-F upcoming evidence root must be a non-symlink directory"
                )
    except CurrentShadowSportyBetUpcomingReconciliationError:
        raise
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "PR-F upcoming evidence root is invalid"
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
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except OSError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            f"could not durably write {path.name}"
        ) from exc


@dataclasses.dataclass(frozen=True)
class CurrentShadowUpcomingDiscoverySnapshot:
    schema_version: int
    dataset_name: str
    provider: str
    provider_region: str
    source_method: str
    football_sport_id: str
    request_target: str
    request_nonce_ms: int
    observed_at: datetime
    raw_sha256: str
    raw_size: int
    events: tuple[reviewed.SportyBetDiscoveredEvent, ...]
    observation_authority: str
    provider_event_timestamp: None
    provider_snapshot_id: None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or type(self.schema_version) is not int:
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot schema mismatch")
        if self.dataset_name != DISCOVERY_DATASET_NAME:
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot dataset mismatch")
        if (self.provider, self.provider_region) != (PROVIDER, PROVIDER_REGION):
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot provider mismatch")
        if self.source_method != DISCOVERY_SOURCE_METHOD:
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot source method mismatch")
        if self.football_sport_id != FOOTBALL_SPORT_ID:
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot sport mismatch")
        observed = _utc(self.observed_at, "observed_at")
        nonce = _validate_request_target(self.request_target, observed_at=observed)
        if self.request_nonce_ms != nonce:
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot request nonce mismatch")
        _sha(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot raw_size invalid")
        if type(self.events) is not tuple or any(
            type(item) is not reviewed.SportyBetDiscoveredEvent for item in self.events
        ):
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot events invalid")
        ids = tuple(item.event_id for item in self.events)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise CurrentShadowSportyBetUpcomingReconciliationError(
                "snapshot events must be sorted and unique"
            )
        if any(
            item.source_page_num != 1
            or item.source_raw_sha256 != self.raw_sha256
            or item.source_observed_at != observed
            for item in self.events
        ):
            raise CurrentShadowSportyBetUpcomingReconciliationError(
                "snapshot event ancestry differs from exact upcoming response"
            )
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise CurrentShadowSportyBetUpcomingReconciliationError("snapshot observation authority mismatch")
        if self.provider_event_timestamp is not None or self.provider_snapshot_id is not None:
            raise CurrentShadowSportyBetUpcomingReconciliationError(
                "snapshot cannot invent provider timestamp/snapshot identity"
            )
        object.__setattr__(self, "observed_at", observed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "provider_region": self.provider_region,
            "source_method": self.source_method,
            "football_sport_id": self.football_sport_id,
            "request_target": self.request_target,
            "request_nonce_ms": self.request_nonce_ms,
            "observed_at": serialize_utc(self.observed_at),
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "event_count": len(self.events),
            "events": [item.to_dict() for item in self.events],
            "observation_authority": self.observation_authority,
            "provider_event_timestamp": None,
            "provider_snapshot_id": None,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


def _event_from_upcoming_row(
    value: Any,
    *,
    raw_sha256: str,
    observed_at: datetime,
) -> reviewed.SportyBetDiscoveredEvent:
    if type(value) is not dict:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming provider data row must be an object"
        )
    sport = value.get("sport")
    if type(sport) is not dict or sport.get("id") != FOOTBALL_SPORT_ID:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming provider row is not exact football"
        )
    try:
        return reviewed._event_from_mapping(
            value,
            inherited_competition=None,
            page_num=1,
            raw_sha256=raw_sha256,
            observed_at=observed_at,
        )
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(str(exc)) from exc


def _parse_snapshot(
    raw: bytes,
    *,
    request_nonce_ms: int,
    observed_at: datetime,
) -> CurrentShadowUpcomingDiscoverySnapshot:
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming response must be bounded non-empty exact bytes"
        )
    try:
        payload = live.strict_json_loads(raw)
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(str(exc)) from exc
    if type(payload) is not dict or payload.get("bizCode") != 10000:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming provider response must be successful"
        )
    data = payload.get("data")
    if type(data) is not list:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming provider data must be a list"
        )
    observed = _utc(observed_at, "observed_at")
    raw_hash = sha256_bytes(raw)
    events = tuple(
        _event_from_upcoming_row(item, raw_sha256=raw_hash, observed_at=observed)
        for item in data
    )
    ids = [item.event_id for item in events]
    if len(ids) != len(set(ids)):
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming provider response contains duplicate event IDs"
        )
    ordered = tuple(sorted(events, key=lambda item: item.event_id))
    return CurrentShadowUpcomingDiscoverySnapshot(
        schema_version=SCHEMA_VERSION,
        dataset_name=DISCOVERY_DATASET_NAME,
        provider=PROVIDER,
        provider_region=PROVIDER_REGION,
        source_method=DISCOVERY_SOURCE_METHOD,
        football_sport_id=FOOTBALL_SPORT_ID,
        request_target=request_target(request_nonce_ms),
        request_nonce_ms=request_nonce_ms,
        observed_at=observed,
        raw_sha256=raw_hash,
        raw_size=len(raw),
        events=ordered,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_event_timestamp=None,
        provider_snapshot_id=None,
    )


def _network_fetch_snapshot() -> tuple[bytes, int, datetime, int]:
    nonce = int(time.time() * 1000)
    request = Request(request_url(nonce), method="GET", headers=dict(REQUEST_HEADERS))
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
    except URLError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            f"SportyBet upcoming request failed: {exc.reason}"
        ) from exc
    observed_at = _now_utc()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "SportyBet upcoming response exceeds byte bound"
        )
    if status != 200:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            f"SportyBet upcoming response returned HTTP {status}"
        )
    return raw, status, observed_at, nonce


def _snapshot_from_mapping(value: Any) -> CurrentShadowUpcomingDiscoverySnapshot:
    expected = {
        "schema_version", "dataset_name", "provider", "provider_region",
        "source_method", "football_sport_id", "request_target", "request_nonce_ms",
        "observed_at", "raw_sha256", "raw_size", "event_count", "events",
        "observation_authority", "provider_event_timestamp", "provider_snapshot_id",
    }
    if type(value) is not dict or set(value) != expected:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming manifest keys mismatch"
        )
    events_raw = value["events"]
    if type(events_raw) is not list or value["event_count"] != len(events_raw):
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming manifest event count mismatch"
        )
    try:
        events = tuple(
            reviewed.SportyBetDiscoveredEvent(
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
        return CurrentShadowUpcomingDiscoverySnapshot(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            provider=value["provider"],
            provider_region=value["provider_region"],
            source_method=value["source_method"],
            football_sport_id=value["football_sport_id"],
            request_target=value["request_target"],
            request_nonce_ms=value["request_nonce_ms"],
            observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            events=events,
            observation_authority=value["observation_authority"],
            provider_event_timestamp=value["provider_event_timestamp"],
            provider_snapshot_id=value["provider_snapshot_id"],
        )
    except (KeyError, TypeError, ValueError, SportyBetLiteCaptureError) as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming manifest is invalid"
        ) from exc


def capture_current_upcoming_discovery(
    *, repository_root: Path, execute_live_network: bool
) -> tuple[Path, CurrentShadowUpcomingDiscoverySnapshot]:
    validate_contract()
    if execute_live_network is not True:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "live upcoming discovery requires exact execute_live_network=True"
        )
    raw, status, observed_at, nonce = _network_fetch_snapshot()
    if status != 200:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            f"SportyBet upcoming response returned HTTP {status}"
        )
    snapshot = _parse_snapshot(raw, request_nonce_ms=nonce, observed_at=observed_at)
    root = _evidence_root(Path(repository_root), create=True)
    directory = root / snapshot.canonical_sha256[:24]
    manifest_bytes = _canonical(snapshot.to_dict(), newline=True)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming manifest exceeds byte bound"
        )
    if directory.exists():
        existing = verify_current_upcoming_discovery(
            directory, repository_root=Path(repository_root)
        )
        if existing.to_dict() != snapshot.to_dict():
            raise CurrentShadowSportyBetUpcomingReconciliationError(
                "upcoming capture identity collision"
            )
        return directory, existing
    directory.mkdir(exist_ok=False)
    _sync_directory(root)
    _sync_directory(directory)
    _write_exclusive(directory / RAW_FILENAME, raw)
    _write_exclusive(directory / MANIFEST_FILENAME, manifest_bytes)
    verified = verify_current_upcoming_discovery(
        directory, repository_root=Path(repository_root)
    )
    _sync_directory(directory)
    _sync_directory(root)
    return directory, verified


def verify_current_upcoming_discovery(
    evidence_directory: Path, *, repository_root: Path
) -> CurrentShadowUpcomingDiscoverySnapshot:
    validate_contract()
    root = _evidence_root(Path(repository_root), create=False)
    evidence = Path(evidence_directory)
    if ".." in evidence.parts:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming evidence path must not contain traversal"
        )
    try:
        _reject_symlink_components(evidence, "upcoming evidence directory")
        resolved = evidence.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming evidence directory escapes reviewed root"
        ) from exc
    if evidence.is_symlink() or not evidence.is_dir():
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming evidence must be a regular directory"
        )
    try:
        manifest_raw = _read_regular(
            evidence / MANIFEST_FILENAME,
            maximum=MAX_MANIFEST_BYTES,
            label="PR-F upcoming manifest",
        )
        raw = _read_regular(
            evidence / RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="PR-F upcoming raw response",
        )
    except SportyBetLiteCaptureError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(str(exc)) from exc
    try:
        mapping = live.strict_json_loads(manifest_raw)
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(str(exc)) from exc
    snapshot = _snapshot_from_mapping(mapping)
    if manifest_raw != _canonical(snapshot.to_dict(), newline=True):
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming manifest bytes are not canonical"
        )
    if {item.name for item in evidence.iterdir()} != {RAW_FILENAME, MANIFEST_FILENAME}:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming evidence directory contents mismatch"
        )
    if sha256_bytes(raw) != snapshot.raw_sha256 or len(raw) != snapshot.raw_size:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming raw response identity mismatch"
        )
    rebuilt = _parse_snapshot(
        raw,
        request_nonce_ms=snapshot.request_nonce_ms,
        observed_at=snapshot.observed_at,
    )
    if rebuilt.to_dict() != snapshot.to_dict():
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming snapshot differs from exact raw replay"
        )
    if evidence.name != snapshot.canonical_sha256[:24]:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "upcoming evidence directory identity mismatch"
        )
    return snapshot


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for key, value in values.items():
        object.__setattr__(obj, key, value)
    return obj


@dataclasses.dataclass(frozen=True, init=False)
class CurrentShadowSportyBetUpcomingReconciliationBundle:
    schema_version: int
    dataset_name: str
    status: str
    evaluation_time: datetime
    max_source_age_seconds: int
    minimum_lead_seconds: int
    discovery_snapshot_sha256: str
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
    _discovery_directory: Path
    _detail_directories: tuple[tuple[str, Path], ...]
    _fotmob_admission: Any
    _fotmob_captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "PR-F upcoming reconciliation bundles are builder-only"
        )

    @property
    def matched_rows(self) -> tuple[reviewed.CurrentEventReconciliationRow, ...]:
        return tuple(item for item in self.rows if item.fixture_reconciliation_authorized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "evaluation_time": serialize_utc(self.evaluation_time),
            "max_source_age_seconds": self.max_source_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "discovery_snapshot_sha256": self.discovery_snapshot_sha256,
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
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


SportyBetCurrentEventDiscoveryReconciliationBundle = (
    CurrentShadowSportyBetUpcomingReconciliationBundle
)


def _build_bundle(
    *,
    repository_root: Path,
    discovery_directory: Path,
    discovery: CurrentShadowUpcomingDiscoverySnapshot,
    admission: Any,
    captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
    detail_directories: Mapping[str, Path],
    evaluation_time: datetime,
) -> CurrentShadowSportyBetUpcomingReconciliationBundle:
    evaluation = _utc(evaluation_time, "evaluation_time")
    reviewed_rows = reviewed._reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in discovery.events:
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
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "direct event-detail evidence set does not match exact upcoming reconciliation candidates"
        )

    rows: list[reviewed.CurrentEventReconciliationRow] = []
    for event in discovery.events:
        state, matches = provisional[event.event_id]
        discovery_age = (evaluation - event.source_observed_at).total_seconds()
        kickoff_lead = (event.kickoff_utc - evaluation).total_seconds()
        if discovery_age < 0:
            raise CurrentShadowSportyBetUpcomingReconciliationError(
                "evaluation_time predates upcoming response completion"
            )
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
            inventory = reviewed._detail_inventory_from_directory(
                detail_directories[event.event_id], repository_root=repository_root
            )
            direct_observed = inventory.observed_at
            direct_age = (evaluation - inventory.observed_at).total_seconds()
            if direct_age < 0:
                raise CurrentShadowSportyBetUpcomingReconciliationError(
                    "evaluation_time predates direct event-detail response completion"
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
                disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH
            elif not inventory.prematch_bookable_observed:
                disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE
            elif direct_age > MAX_SOURCE_AGE_SECONDS:
                disposition = reviewed.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_STALE
            else:
                disposition = reviewed.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED

        rows.append(
            reviewed.CurrentEventReconciliationRow(
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
                    is reviewed.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
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
    value = object.__new__(CurrentShadowSportyBetUpcomingReconciliationBundle)
    return _set_frozen(
        value,
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "evaluation_time": evaluation,
            "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
            "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
            "discovery_snapshot_sha256": discovery.canonical_sha256,
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
            "_discovery_directory": Path(discovery_directory),
            "_detail_directories": detail_tuple,
            "_fotmob_admission": admission,
            "_fotmob_captures": captures,
        },
    )


def discover_and_reconcile_current_events(
    *,
    repository_root: Path,
    fotmob_admission_value: Any,
    fotmob_captures: Sequence[tuple[bytes, FotMobDataMatchesCaptureManifest]],
    execute_live_network: bool,
) -> CurrentShadowSportyBetUpcomingReconciliationBundle:
    validate_contract()
    if execute_live_network is not True:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "live upcoming reconciliation requires exact execute_live_network=True"
        )
    repository = Path(repository_root).resolve(strict=True)
    try:
        captures = reviewed._materialize_fotmob_captures(fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(
            fotmob_admission_value, captures
        )
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(str(exc)) from exc
    discovery_directory, discovery = capture_current_upcoming_discovery(
        repository_root=repository, execute_live_network=True
    )
    reviewed_rows = reviewed._reviewed_rows(admission)
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in discovery.events:
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
            live.build_live_event_quote_inventory(directory, repository_root=repository)
        except live.SportyBetLiveEventQuoteEvidenceError as exc:
            raise CurrentShadowSportyBetUpcomingReconciliationError(
                f"PR246 direct event-detail acquisition failed closed for {event_id}: {exc}"
            ) from exc
        detail_dirs[event_id] = directory
    return _build_bundle(
        repository_root=repository,
        discovery_directory=discovery_directory,
        discovery=discovery,
        admission=admission,
        captures=captures,
        detail_directories=detail_dirs,
        evaluation_time=_now_utc(),
    )


def verify_current_event_discovery_reconciliation_bundle(
    value: Any,
) -> CurrentShadowSportyBetUpcomingReconciliationBundle:
    if type(value) is not CurrentShadowSportyBetUpcomingReconciliationBundle:
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "value must be exact CurrentShadowSportyBetUpcomingReconciliationBundle"
        )
    validate_contract()
    try:
        captures = reviewed._materialize_fotmob_captures(value._fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(
            value._fotmob_admission, captures
        )
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentShadowSportyBetUpcomingReconciliationError(str(exc)) from exc
    discovery = verify_current_upcoming_discovery(
        value._discovery_directory, repository_root=value._repository_root
    )
    rebuilt = _build_bundle(
        repository_root=value._repository_root,
        discovery_directory=value._discovery_directory,
        discovery=discovery,
        admission=admission,
        captures=captures,
        detail_directories=dict(value._detail_directories),
        evaluation_time=value.evaluation_time,
    )
    if _canonical(value.to_dict()) != _canonical(rebuilt.to_dict()):
        raise CurrentShadowSportyBetUpcomingReconciliationError(
            "PR-F upcoming reconciliation differs from exact retained-source replay"
        )
    return rebuilt


__all__ = [
    "CurrentEventReconciliationDisposition",
    "CurrentEventReconciliationRow",
    "CurrentShadowSportyBetUpcomingReconciliationBundle",
    "CurrentShadowSportyBetUpcomingReconciliationError",
    "CurrentShadowUpcomingDiscoverySnapshot",
    "DATASET_NAME",
    "DISCOVERY_SOURCE_METHOD",
    "EXPECTED_CONTRACT_SHA256",
    "SportyBetCurrentEventDiscoveryError",
    "SportyBetCurrentEventDiscoveryReconciliationBundle",
    "STATUS",
    "UPCOMING_PATH",
    "calculate_contract_sha256",
    "capture_current_upcoming_discovery",
    "discover_and_reconcile_current_events",
    "request_target",
    "request_url",
    "validate_contract",
    "verify_current_event_discovery_reconciliation_bundle",
    "verify_current_upcoming_discovery",
]
