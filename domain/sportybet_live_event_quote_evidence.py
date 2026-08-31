"""Reviewed direct SportyBet current event/odds evidence boundary.

ATHENA already has a reviewed public anonymous SportyBet event read in the
semantic booking-code gate::

    GET /api/ng/factsCenter/event?productId=3&eventId=<sr:match:...>

This module makes that read a durable, replayable source boundary for current
provider-native market/outcome/odds evidence.  It is deliberately separate
from the blocked SportyBet Lite HTML network-acquisition boundary and from the
manual browser-export evidence lane.

The capture observation is ATHENA's response-completion time.  It is *not* a
provider-native quote timestamp or snapshot identifier.  Mapping into ATHENA
canonical markets still requires an exact previously reviewed SportyBet
canonical mapping; this source does not infer settlement equivalence.

No object issued here grants Price-all, Router, Optimizer, final-selection,
accumulator, staking, wallet, login, SportyBet execution, or BET authority.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
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
from domain.sportybet_reviewed_canonical_market_mapping import (
    MappedSportyBetCanonicalSelection,
    SportyBetReviewedCanonicalMarketMapping,
    canonical_mapping_sha256,
)
from scripts import sportybet_direct_share_bridge as direct_bridge


SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-sportybet-live-event-quote-evidence-v1"
INVENTORY_DATASET_NAME = "athena-sportybet-live-event-quote-inventory-v1"
MAPPED_QUOTE_DATASET_NAME = "athena-sportybet-live-mapped-quote-bundle-v1"
PROVIDER = "SportyBet"
PROVIDER_REGION = "Nigeria"
SOURCE_METHOD = "PUBLIC_ANONYMOUS_FACTS_CENTER_EVENT_GET"
REVIEW_BASIS = "SPORTYBET_DIRECT_BOOKING_BRIDGE_PUBLIC_EVENT_READ_V1"
ORIGIN = direct_bridge.SPORTYBET_ORIGIN
OPER_ID = direct_bridge.SPORTYBET_OPER_ID
EVENT_PATH = "/api/ng/factsCenter/event"
PRODUCT_ID = 3
REQUEST_HEADERS = (
    ("Accept", "application/json"),
    ("Accept-Language", "en-NG,en;q=0.9"),
    ("OperId", OPER_ID),
    ("User-Agent", "ATHENA/1.0 sportybet-live-event-quote-evidence"),
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
RAW_FILENAME = "event.raw.json"
MANIFEST_FILENAME = "manifest.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-live-event-quote-evidence"
)
MAX_OBSERVATION_AGE_SECONDS = 900
MINIMUM_LEAD_SECONDS = 120
OBSERVATION_AUTHORITY = (
    "ATHENA_DIRECT_PROVIDER_RESPONSE_COMPLETION_NOT_PROVIDER_QUOTE_TIMESTAMP"
)
REPLAY_PROOF_MODE = "REPLAY_AS_OF"
LIVE_PROOF_MODE = "LIVE_CURRENT"
REPLAY_STATUS = "DIRECT_PROVIDER_ODDS_EVIDENCE_AS_OF_REPLAY_VERIFIED"
LIVE_STATUS = "CURRENT_DIRECT_PROVIDER_ODDS_EVIDENCE_VERIFIED"
NEXT_BOUNDARY = "PRICE_ALL_DIRECT_PROVIDER_QUOTE_SOURCE_ADAPTER_REQUIRED"
EXPECTED_CONTRACT_SHA256 = (
    "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,160}$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_CAPTURE_AUTHORITY = types.MappingProxyType(
    {
        "direct_provider_event_read_evidence": True,
        "provider_native_odds_observed": True,
        "provider_quote_timestamp": False,
        "provider_snapshot_identity": False,
        "price_all": False,
        "market_router": False,
        "accumulator_optimizer": False,
        "selection": False,
        "accumulator": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


class SportyBetLiveEventQuoteEvidenceError(ValueError):
    """Raised when direct current SportyBet evidence fails closed."""


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SportyBetLiveEventQuoteEvidenceError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError(f"{label} is invalid") from exc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise SportyBetLiveEventQuoteEvidenceError(f"{label} must be an exact SHA-256")
    return value


def _event_id(value: Any) -> str:
    if type(value) is not str or _EVENT_RE.fullmatch(value) is None:
        raise SportyBetLiveEventQuoteEvidenceError(
            "event_id must use exact sr:match:<positive integer> form"
        )
    return value


def _native_id(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SportyBetLiveEventQuoteEvidenceError(f"{label} is missing or invalid")
    text = str(value)
    if _SAFE_ID_RE.fullmatch(text) is None:
        raise SportyBetLiveEventQuoteEvidenceError(f"{label} is invalid")
    return text


def request_target(event_id: Any) -> str:
    event = _event_id(event_id)
    return f"{EVENT_PATH}?{urlencode((('productId', PRODUCT_ID), ('eventId', event)))}"


def request_url(event_id: Any) -> str:
    return ORIGIN + request_target(event_id)


def _canonical_json_bytes(value: Any, *, newline: bool = True) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError("canonical JSON serialization failed") from exc
    return encoded + (b"\n" if newline else b"")


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str:
            raise SportyBetLiveEventQuoteEvidenceError("JSON object key must be a string")
        if key in result:
            raise SportyBetLiveEventQuoteEvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SportyBetLiveEventQuoteEvidenceError(f"invalid JSON constant: {value}")


def strict_json_loads(raw: Any) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise SportyBetLiveEventQuoteEvidenceError(
            "raw provider response must be bounded non-empty exact bytes"
        )
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except SportyBetLiveEventQuoteEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            "provider response is not strict UTF-8 JSON"
        ) from exc


def _exact_text(value: Any, label: str, *, maximum: int = 300) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise SportyBetLiveEventQuoteEvidenceError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def _walk_dicts(root: Any) -> Iterable[dict[str, Any]]:
    stack = [root]
    visited = 0
    while stack:
        value = stack.pop()
        visited += 1
        if visited > 250_000:
            raise SportyBetLiveEventQuoteEvidenceError(
                "provider response object graph is excessive"
            )
        if type(value) is dict:
            yield value
            stack.extend(reversed(tuple(value.values())))
        elif type(value) is list:
            stack.extend(reversed(value))


def _event_object(payload: Any, event_id: str) -> dict[str, Any]:
    if type(payload) is not dict:
        raise SportyBetLiveEventQuoteEvidenceError("provider response must be an object")
    if payload.get("bizCode") != 10000:
        raise SportyBetLiveEventQuoteEvidenceError(
            f"SportyBet bizCode was not SUCCESS: {payload.get('bizCode')!r}"
        )
    matches = [
        item
        for item in _walk_dicts(payload)
        if item.get("eventId") == event_id and type(item.get("markets")) is list
    ]
    if len(matches) != 1:
        raise SportyBetLiveEventQuoteEvidenceError(
            f"expected exactly one current event object with markets for {event_id}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _market_name(value: Mapping[str, Any]) -> str:
    return _exact_text(
        value.get("desc") or value.get("description") or value.get("name"),
        "provider market name",
    )


def _outcome_name(value: Mapping[str, Any]) -> str:
    return _exact_text(
        value.get("desc") or value.get("description") or value.get("name"),
        "provider outcome name",
    )


def _specifier(value: Any) -> str | None:
    if value is None:
        return None
    return _exact_text(value, "provider specifier", maximum=160)


def _odds(value: Any) -> tuple[str, float]:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise SportyBetLiveEventQuoteEvidenceError("provider outcome odds are missing")
    raw = str(value)
    try:
        decimal = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError("provider outcome odds are invalid") from exc
    if not decimal.is_finite() or decimal <= Decimal("1"):
        raise SportyBetLiveEventQuoteEvidenceError(
            "provider outcome odds must be finite and greater than 1"
        )
    number = float(decimal)
    if not math.isfinite(number):
        raise SportyBetLiveEventQuoteEvidenceError("provider outcome odds overflow")
    return raw, number


def _outcome_bookability(outcome: Mapping[str, Any]) -> tuple[bool, str]:
    values = [outcome[key] for key in ("isActive", "is_active") if key in outcome]
    if not values:
        # This is the exact default already reviewed by the semantic SportyBet
        # gate: absence of an active flag is not treated as inactive.
        return True, "REVIEWED_SEMANTIC_GATE_DEFAULT_ACTIVE_ABSENT_FLAG"
    normalized: list[bool] = []
    for value in values:
        if value in (1, True, "1"):
            normalized.append(True)
        elif value in (0, False, "0"):
            normalized.append(False)
        else:
            raise SportyBetLiveEventQuoteEvidenceError(
                "provider outcome active-state field is invalid"
            )
    if len(set(normalized)) != 1:
        raise SportyBetLiveEventQuoteEvidenceError(
            "provider outcome active-state fields conflict"
        )
    return normalized[0], "EXPLICIT_ACTIVE_FLAG"


def _kickoff(event: Mapping[str, Any]) -> datetime:
    value = event.get("estimateStartTime")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SportyBetLiveEventQuoteEvidenceError(
            "current event omitted numeric estimateStartTime"
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise SportyBetLiveEventQuoteEvidenceError("estimateStartTime is invalid")
    try:
        return datetime.fromtimestamp(number / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            "estimateStartTime is out of range"
        ) from exc


def _event_is_prematch_bookable(event: Mapping[str, Any]) -> bool:
    if event.get("bookingStatus") == "Unavailable":
        return False
    status = event.get("status")
    if status not in (None, 0, "0"):
        return False
    match_status = str(event.get("matchStatus") or "").strip().casefold()
    return not match_status or "not start" in match_status or match_status == "ns"


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "inventory_dataset_name": INVENTORY_DATASET_NAME,
        "mapped_quote_dataset_name": MAPPED_QUOTE_DATASET_NAME,
        "source_method": SOURCE_METHOD,
        "review_basis": REVIEW_BASIS,
        "origin": ORIGIN,
        "oper_id": OPER_ID,
        "event_path": EVENT_PATH,
        "product_id": PRODUCT_ID,
        "request_headers": [list(item) for item in REQUEST_HEADERS],
        "max_response_bytes": MAX_RESPONSE_BYTES,
        "max_observation_age_seconds": MAX_OBSERVATION_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "observation_authority": OBSERVATION_AUTHORITY,
        "replay_status": REPLAY_STATUS,
        "live_status": LIVE_STATUS,
        "next_boundary": NEXT_BOUNDARY,
    }


def calculate_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {"version": CONTRACT_VERSION, "semantics": _contract_payload()},
            newline=False,
        )
    ).hexdigest()


def validate_direct_event_source_contract() -> Mapping[str, Any]:
    """Pin this boundary to the already-reviewed direct/semantic endpoint."""
    from scripts import sportybet_semantic_share_bridge as semantic_bridge

    if ORIGIN != direct_bridge.SPORTYBET_ORIGIN or OPER_ID != direct_bridge.SPORTYBET_OPER_ID:
        raise SportyBetLiveEventQuoteEvidenceError(
            "direct SportyBet bridge identity drifted"
        )
    if (
        semantic_bridge.SPORTYBET_ORIGIN != ORIGIN
        or semantic_bridge.SPORTYBET_OPER_ID != OPER_ID
        or semantic_bridge.EVENT_PATH != EVENT_PATH
    ):
        raise SportyBetLiveEventQuoteEvidenceError(
            "semantic SportyBet event-read identity drifted"
        )
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise SportyBetLiveEventQuoteEvidenceError(
            "SportyBet direct-event quote evidence contract drifted"
        )
    return types.MappingProxyType(
        {
            "contract_sha256": actual,
            "origin": ORIGIN,
            "oper_id": OPER_ID,
            "event_path": EVENT_PATH,
            "product_id": PRODUCT_ID,
        }
    )


@dataclass(frozen=True)
class SportyBetLiveEventCaptureManifest:
    schema_version: int
    dataset_name: str
    provider: str
    provider_region: str
    source_method: str
    review_basis: str
    origin: str
    request_target: str
    request_headers: tuple[tuple[str, str], ...]
    event_id: str
    http_status: int
    biz_code: int
    observed_at: datetime
    observation_authority: str
    provider_quote_at: None
    provider_snapshot_id: None
    network_acquisition_performed: bool
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        validate_direct_event_source_contract()
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetLiveEventQuoteEvidenceError("schema_version mismatch")
        if (
            self.dataset_name != DATASET_NAME
            or self.provider != PROVIDER
            or self.provider_region != PROVIDER_REGION
        ):
            raise SportyBetLiveEventQuoteEvidenceError("dataset/provider identity mismatch")
        if self.source_method != SOURCE_METHOD or self.review_basis != REVIEW_BASIS:
            raise SportyBetLiveEventQuoteEvidenceError("source method/review basis mismatch")
        if self.origin != ORIGIN or self.request_target != request_target(self.event_id):
            raise SportyBetLiveEventQuoteEvidenceError("request identity mismatch")
        if type(self.request_headers) is not tuple or self.request_headers != REQUEST_HEADERS:
            raise SportyBetLiveEventQuoteEvidenceError("request headers mismatch")
        if (
            type(self.http_status) is not int
            or self.http_status != 200
            or type(self.biz_code) is not int
            or self.biz_code != 10000
        ):
            raise SportyBetLiveEventQuoteEvidenceError(
                "provider HTTP/bizCode success is required"
            )
        observed = _utc(self.observed_at, "observed_at")
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetLiveEventQuoteEvidenceError("observation authority mismatch")
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise SportyBetLiveEventQuoteEvidenceError(
                "provider quote/snapshot identity remains unproven"
            )
        if self.network_acquisition_performed is not True:
            raise SportyBetLiveEventQuoteEvidenceError(
                "network acquisition provenance must be exact True"
            )
        if self.raw_file_name != RAW_FILENAME:
            raise SportyBetLiveEventQuoteEvidenceError("raw file name mismatch")
        _sha(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise SportyBetLiveEventQuoteEvidenceError("raw_size is invalid")
        if dict(self.authority) != dict(_CAPTURE_AUTHORITY):
            raise SportyBetLiveEventQuoteEvidenceError("capture authority flags mismatch")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "authority", types.MappingProxyType(dict(_CAPTURE_AUTHORITY)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "provider_region": self.provider_region,
            "source_method": self.source_method,
            "review_basis": self.review_basis,
            "origin": self.origin,
            "request_target": self.request_target,
            "request_headers": [list(item) for item in self.request_headers],
            "event_id": self.event_id,
            "http_status": self.http_status,
            "biz_code": self.biz_code,
            "observed_at": serialize_utc(self.observed_at),
            "observation_authority": self.observation_authority,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "network_acquisition_performed": True,
            "raw_file_name": self.raw_file_name,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "authority": dict(self.authority),
        }


def canonical_manifest_bytes(manifest: Any) -> bytes:
    if type(manifest) is not SportyBetLiveEventCaptureManifest:
        raise SportyBetLiveEventQuoteEvidenceError("manifest type mismatch")
    return _canonical_json_bytes(manifest.to_dict())


def manifest_sha256(manifest: Any) -> str:
    return sha256_bytes(canonical_manifest_bytes(manifest))


def capture_identifier(manifest: Any) -> str:
    if type(manifest) is not SportyBetLiveEventCaptureManifest:
        raise SportyBetLiveEventQuoteEvidenceError("manifest type mismatch")
    identity = {
        "event_id": manifest.event_id,
        "request_target": manifest.request_target,
        "observed_at": serialize_utc(manifest.observed_at),
        "raw_sha256": manifest.raw_sha256,
    }
    return hashlib.sha256(
        _canonical_json_bytes(identity, newline=False)
    ).hexdigest()[:24]


def _manifest_from_mapping(value: Any) -> SportyBetLiveEventCaptureManifest:
    expected = {field.name for field in fields(SportyBetLiveEventCaptureManifest)}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SportyBetLiveEventQuoteEvidenceError("manifest keys mismatch")
    headers = value.get("request_headers")
    if type(headers) is not list or any(
        type(item) is not list or len(item) != 2 for item in headers
    ):
        raise SportyBetLiveEventQuoteEvidenceError("manifest request_headers are invalid")
    try:
        return SportyBetLiveEventCaptureManifest(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            provider=value["provider"],
            provider_region=value["provider_region"],
            source_method=value["source_method"],
            review_basis=value["review_basis"],
            origin=value["origin"],
            request_target=value["request_target"],
            request_headers=tuple(tuple(item) for item in headers),
            event_id=value["event_id"],
            http_status=value["http_status"],
            biz_code=value["biz_code"],
            observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
            observation_authority=value["observation_authority"],
            provider_quote_at=value["provider_quote_at"],
            provider_snapshot_id=value["provider_snapshot_id"],
            network_acquisition_performed=value["network_acquisition_performed"],
            raw_file_name=value["raw_file_name"],
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            authority=value["authority"],
        )
    except SportyBetLiveEventQuoteEvidenceError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError("manifest is invalid") from exc


def _evidence_root(repository_root: Path, *, create: bool) -> Path:
    try:
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            "repository_root must resolve to an existing directory"
        ) from exc
    if repository.is_symlink() or not repository.is_dir():
        raise SportyBetLiveEventQuoteEvidenceError(
            "repository_root must be a regular directory"
        )
    root = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        _reject_symlink_components(root, "live event quote evidence root")
        if create:
            _ensure_directory_tree_durable(root, boundary=repository)
        else:
            resolved = root.resolve(strict=True)
            resolved.relative_to(repository)
            if resolved.is_symlink() or not resolved.is_dir():
                raise SportyBetLiveEventQuoteEvidenceError(
                    "evidence root must be a non-symlink directory"
                )
    except SportyBetLiveEventQuoteEvidenceError:
        raise
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            "SportyBet live event evidence root is invalid"
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
        raise SportyBetLiveEventQuoteEvidenceError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except OSError as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            f"could not durably write {path.name}"
        ) from exc


def _build_manifest(
    *, event_id: str, raw: bytes, status: int, observed_at: datetime
) -> SportyBetLiveEventCaptureManifest:
    payload = strict_json_loads(raw)
    _event_object(payload, event_id)
    return SportyBetLiveEventCaptureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        provider_region=PROVIDER_REGION,
        source_method=SOURCE_METHOD,
        review_basis=REVIEW_BASIS,
        origin=ORIGIN,
        request_target=request_target(event_id),
        request_headers=REQUEST_HEADERS,
        event_id=event_id,
        http_status=status,
        biz_code=payload.get("bizCode"),
        observed_at=observed_at,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        network_acquisition_performed=True,
        raw_file_name=RAW_FILENAME,
        raw_sha256=sha256_bytes(raw),
        raw_size=len(raw),
        authority=_CAPTURE_AUTHORITY,
    )


def _network_fetch(event_id: str) -> tuple[bytes, int, datetime]:
    request = Request(
        request_url(event_id), method="GET", headers=dict(REQUEST_HEADERS)
    )
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
    except URLError as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            f"SportyBet event request failed: {exc.reason}"
        ) from exc
    observed_at = _now_utc()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SportyBetLiveEventQuoteEvidenceError(
            "SportyBet event response exceeds byte bound"
        )
    if status != 200:
        raise SportyBetLiveEventQuoteEvidenceError(
            f"SportyBet event returned HTTP {status}"
        )
    return raw, status, observed_at


def capture_live_event_quote_evidence(
    *, event_id: str, repository_root: Path, execute_live_network: bool
) -> tuple[Path, SportyBetLiveEventCaptureManifest]:
    """Execute exactly one reviewed public event GET and preserve its raw bytes."""
    validate_direct_event_source_contract()
    event = _event_id(event_id)
    if execute_live_network is not True:
        raise SportyBetLiveEventQuoteEvidenceError(
            "live SportyBet event acquisition requires exact execute_live_network=True"
        )
    raw, status, observed_at = _network_fetch(event)
    manifest = _build_manifest(
        event_id=event, raw=raw, status=status, observed_at=observed_at
    )
    root = _evidence_root(Path(repository_root), create=True)
    directory = root / capture_identifier(manifest)
    if directory.exists():
        existing = verify_live_event_quote_evidence(
            directory, repository_root=Path(repository_root)
        )
        existing_raw = _read_regular(
            directory / RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="SportyBet live event raw response",
        )
        if existing.to_dict() != manifest.to_dict() or existing_raw != raw:
            raise SportyBetLiveEventQuoteEvidenceError("capture identity collision")
        return directory, existing
    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(directory)
    except OSError as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            "could not create capture directory"
        ) from exc
    _write_exclusive(directory / RAW_FILENAME, raw)
    _write_exclusive(directory / MANIFEST_FILENAME, canonical_manifest_bytes(manifest))
    verified = verify_live_event_quote_evidence(
        directory, repository_root=Path(repository_root)
    )
    _sync_directory(directory)
    _sync_directory(root)
    return directory, verified


def verify_live_event_quote_evidence(
    evidence_directory: Path, *, repository_root: Path
) -> SportyBetLiveEventCaptureManifest:
    """Verify one preserved capture without creating missing filesystem state."""
    validate_direct_event_source_contract()
    root = _evidence_root(Path(repository_root), create=False)
    evidence = Path(evidence_directory)
    if ".." in evidence.parts:
        raise SportyBetLiveEventQuoteEvidenceError(
            "evidence path must not contain traversal"
        )
    try:
        _reject_symlink_components(evidence, "evidence directory")
        resolved = evidence.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetLiveEventQuoteEvidenceError(
            "evidence directory escapes the reviewed root"
        ) from exc
    if evidence.is_symlink() or not evidence.is_dir():
        raise SportyBetLiveEventQuoteEvidenceError(
            "evidence directory must be a regular directory"
        )
    if sorted(item.name for item in evidence.iterdir()) != sorted(
        (MANIFEST_FILENAME, RAW_FILENAME)
    ):
        raise SportyBetLiveEventQuoteEvidenceError(
            "evidence directory contents mismatch"
        )
    raw = _read_regular(
        evidence / RAW_FILENAME,
        maximum=MAX_RESPONSE_BYTES,
        label="SportyBet live event raw response",
    )
    manifest_raw = _read_regular(
        evidence / MANIFEST_FILENAME,
        maximum=MAX_MANIFEST_BYTES,
        label="SportyBet live event manifest",
    )
    try:
        manifest = _manifest_from_mapping(strict_json_loads(manifest_raw))
    except SportyBetLiveEventQuoteEvidenceError:
        raise
    if manifest_raw != canonical_manifest_bytes(manifest):
        raise SportyBetLiveEventQuoteEvidenceError("manifest bytes are not canonical")
    if manifest.raw_sha256 != sha256_bytes(raw) or manifest.raw_size != len(raw):
        raise SportyBetLiveEventQuoteEvidenceError("raw response identity mismatch")
    if evidence.name != capture_identifier(manifest):
        raise SportyBetLiveEventQuoteEvidenceError(
            "capture directory identity mismatch"
        )
    _event_object(strict_json_loads(raw), manifest.event_id)
    return manifest


@dataclass(frozen=True)
class SportyBetLiveEventSelection:
    event_id: str
    market_id: str
    market_name: str
    specifier: str | None
    outcome_id: str
    outcome_name: str
    bookable: bool
    bookability_basis: str
    odds_raw: str
    odds_decimal: float

    def __post_init__(self) -> None:
        _event_id(self.event_id)
        _native_id(self.market_id, "market_id")
        _native_id(self.outcome_id, "outcome_id")
        _exact_text(self.market_name, "market_name")
        _exact_text(self.outcome_name, "outcome_name")
        if self.specifier is not None:
            _specifier(self.specifier)
        if type(self.bookable) is not bool or self.bookability_basis not in {
            "EXPLICIT_ACTIVE_FLAG",
            "REVIEWED_SEMANTIC_GATE_DEFAULT_ACTIVE_ABSENT_FLAG",
        }:
            raise SportyBetLiveEventQuoteEvidenceError(
                "selection bookability evidence is invalid"
            )
        raw, decimal = _odds(self.odds_raw)
        if raw != self.odds_raw or decimal != self.odds_decimal:
            raise SportyBetLiveEventQuoteEvidenceError("selection odds identity mismatch")

    @property
    def selection_identity(self) -> tuple[str, str, str | None, str]:
        return (self.event_id, self.market_id, self.specifier, self.outcome_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "market_id": self.market_id,
            "market_name": self.market_name,
            "specifier": self.specifier,
            "outcome_id": self.outcome_id,
            "outcome_name": self.outcome_name,
            "bookable": self.bookable,
            "bookability_basis": self.bookability_basis,
            "odds_raw": self.odds_raw,
            "odds_decimal": self.odds_decimal,
        }


@dataclass(frozen=True)
class SportyBetLiveEventQuoteInventory:
    dataset_name: str
    event_id: str
    home_team_name: str
    away_team_name: str
    kickoff_utc: datetime
    booking_status: str | None
    event_status: Any
    match_status: str | None
    prematch_bookable_observed: bool
    observed_at: datetime
    observation_authority: str
    provider_quote_at: None
    provider_snapshot_id: None
    source_manifest_sha256: str
    source_raw_sha256: str
    selections: tuple[SportyBetLiveEventSelection, ...]

    def __post_init__(self) -> None:
        if self.dataset_name != INVENTORY_DATASET_NAME:
            raise SportyBetLiveEventQuoteEvidenceError("inventory dataset mismatch")
        _event_id(self.event_id)
        _exact_text(self.home_team_name, "home_team_name")
        _exact_text(self.away_team_name, "away_team_name")
        kickoff = _utc(self.kickoff_utc, "kickoff_utc")
        observed = _utc(self.observed_at, "observed_at")
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetLiveEventQuoteEvidenceError(
                "inventory observation authority mismatch"
            )
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise SportyBetLiveEventQuoteEvidenceError(
                "inventory cannot invent provider quote/snapshot identity"
            )
        _sha(self.source_manifest_sha256, "source_manifest_sha256")
        _sha(self.source_raw_sha256, "source_raw_sha256")
        if type(self.selections) is not tuple or not self.selections:
            raise SportyBetLiveEventQuoteEvidenceError(
                "inventory must contain priced provider selections"
            )
        identities = [item.selection_identity for item in self.selections]
        if len(identities) != len(set(identities)):
            raise SportyBetLiveEventQuoteEvidenceError(
                "duplicate provider selection identity"
            )
        object.__setattr__(self, "kickoff_utc", kickoff)
        object.__setattr__(self, "observed_at", observed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "event_id": self.event_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "booking_status": self.booking_status,
            "event_status": self.event_status,
            "match_status": self.match_status,
            "prematch_bookable_observed": self.prematch_bookable_observed,
            "observed_at": serialize_utc(self.observed_at),
            "observation_authority": self.observation_authority,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "selections": [item.to_dict() for item in self.selections],
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json_bytes(self.to_dict(), newline=False)
        ).hexdigest()


def build_live_event_quote_inventory(
    evidence_directory: Path, *, repository_root: Path
) -> SportyBetLiveEventQuoteInventory:
    manifest = verify_live_event_quote_evidence(
        evidence_directory, repository_root=repository_root
    )
    raw = _read_regular(
        Path(evidence_directory) / RAW_FILENAME,
        maximum=MAX_RESPONSE_BYTES,
        label="SportyBet live event raw response",
    )
    event = _event_object(strict_json_loads(raw), manifest.event_id)
    selections: list[SportyBetLiveEventSelection] = []
    for market in event.get("markets"):
        if type(market) is not dict:
            continue
        market_native = market.get("id", market.get("marketId"))
        if market_native is None:
            continue
        market_id = _native_id(market_native, "provider market ID")
        market_name = _market_name(market)
        specifier = _specifier(market.get("specifier"))
        outcomes = market.get("outcomes")
        if type(outcomes) is not list:
            continue
        for outcome in outcomes:
            if type(outcome) is not dict:
                continue
            outcome_native = outcome.get("id", outcome.get("outcomeId"))
            if outcome_native is None:
                continue
            bookable, bookability_basis = _outcome_bookability(outcome)
            try:
                odds_raw, decimal_odds = _odds(outcome.get("odds"))
            except SportyBetLiveEventQuoteEvidenceError:
                if bookable:
                    raise
                continue
            selections.append(
                SportyBetLiveEventSelection(
                    event_id=manifest.event_id,
                    market_id=market_id,
                    market_name=market_name,
                    specifier=specifier,
                    outcome_id=_native_id(outcome_native, "provider outcome ID"),
                    outcome_name=_outcome_name(outcome),
                    bookable=bookable,
                    bookability_basis=bookability_basis,
                    odds_raw=odds_raw,
                    odds_decimal=decimal_odds,
                )
            )
    if not selections:
        raise SportyBetLiveEventQuoteEvidenceError(
            "current event contains no priced selections"
        )
    ordered = tuple(
        sorted(
            selections,
            key=lambda item: (
                item.market_id,
                "" if item.specifier is None else item.specifier,
                item.outcome_id,
            ),
        )
    )
    return SportyBetLiveEventQuoteInventory(
        dataset_name=INVENTORY_DATASET_NAME,
        event_id=manifest.event_id,
        home_team_name=_exact_text(event.get("homeTeamName"), "provider home team"),
        away_team_name=_exact_text(event.get("awayTeamName"), "provider away team"),
        kickoff_utc=_kickoff(event),
        booking_status=(
            None if event.get("bookingStatus") is None else str(event.get("bookingStatus"))
        ),
        event_status=event.get("status"),
        match_status=(
            None if event.get("matchStatus") is None else str(event.get("matchStatus"))
        ),
        prematch_bookable_observed=_event_is_prematch_bookable(event),
        observed_at=manifest.observed_at,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256=manifest_sha256(manifest),
        source_raw_sha256=manifest.raw_sha256,
        selections=ordered,
    )


@dataclass(frozen=True)
class SportyBetLiveMappingAudit:
    provider_market_id: str
    provider_specifier: str | None
    provider_outcome_id: str
    provider_market_name: str
    provider_outcome_name: str
    canonical_market_id: str
    canonical_outcome_id: str
    canonical_line: float | None
    disposition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_market_id": self.provider_market_id,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_market_name": self.provider_market_name,
            "provider_outcome_name": self.provider_outcome_name,
            "canonical_market_id": self.canonical_market_id,
            "canonical_outcome_id": self.canonical_outcome_id,
            "canonical_line": self.canonical_line,
            "disposition": self.disposition,
        }


@dataclass(frozen=True, init=False)
class SportyBetLiveMappedQuote:
    fixture_id: str
    event_id: str
    canonical_market_id: str
    canonical_outcome_id: str
    canonical_line: float | None
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str | None
    provider_outcome_id: str
    provider_outcome_name: str
    odds_raw: str
    decimal_odds: float
    observed_at: datetime
    observation_authority: str
    provider_quote_at: None
    provider_snapshot_id: None
    live_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    reviewed_mapping_sha256: str
    settlement_equivalence_authority: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetLiveEventQuoteEvidenceError(
            "live mapped quotes are issued only by reviewed source replay"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "canonical_market_id": self.canonical_market_id,
            "canonical_outcome_id": self.canonical_outcome_id,
            "canonical_line": self.canonical_line,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "odds_raw": self.odds_raw,
            "decimal_odds": self.decimal_odds,
            "observed_at": serialize_utc(self.observed_at),
            "observation_authority": self.observation_authority,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "live_inventory_sha256": self.live_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "reviewed_mapping_sha256": self.reviewed_mapping_sha256,
            "settlement_equivalence_authority": self.settlement_equivalence_authority,
        }


@dataclass(frozen=True, init=False)
class SportyBetLiveMappedQuoteBundle:
    dataset_name: str
    status: str
    proof_mode: str
    event_id: str
    fixture_id: str
    evaluation_time: datetime
    observed_at: datetime
    kickoff_utc: datetime
    observation_age_seconds: float
    minimum_lead_seconds: int
    max_observation_age_seconds: int
    live_inventory_sha256: str
    reviewed_mapping_sha256: str
    quotes: tuple[SportyBetLiveMappedQuote, ...]
    mapping_audits: tuple[SportyBetLiveMappingAudit, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    _mapping: SportyBetReviewedCanonicalMarketMapping
    _inventory: SportyBetLiveEventQuoteInventory
    _evidence_directory: Path
    _repository_root: Path

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetLiveEventQuoteEvidenceError(
            "mapped quote bundles are issued only by reviewed direct-provider replay"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "event_id": self.event_id,
            "fixture_id": self.fixture_id,
            "evaluation_time": serialize_utc(self.evaluation_time),
            "observed_at": serialize_utc(self.observed_at),
            "kickoff_utc": serialize_utc(self.kickoff_utc),
            "observation_age_seconds": self.observation_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "max_observation_age_seconds": self.max_observation_age_seconds,
            "live_inventory_sha256": self.live_inventory_sha256,
            "reviewed_mapping_sha256": self.reviewed_mapping_sha256,
            "quote_count": len(self.quotes),
            "quotes": [item.to_dict() for item in self.quotes],
            "mapping_audits": [item.to_dict() for item in self.mapping_audits],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json_bytes(self.to_dict(), newline=False)
        ).hexdigest()


def _bundle_authority(proof_mode: str) -> Mapping[str, bool]:
    live = proof_mode == LIVE_PROOF_MODE
    return types.MappingProxyType(
        {
            "direct_provider_event_read_evidence": True,
            "provider_native_odds_observed": True,
            "as_of_observation_freshness_proven": True,
            "current_observation_freshness_proven": live,
            "reviewed_mapping_rebind": True,
            "provider_quote_timestamp": False,
            "provider_snapshot_identity": False,
            "price_all": False,
            "market_router": False,
            "accumulator_optimizer": False,
            "selection": False,
            "accumulator": False,
            "sportybet_execution": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "staking": False,
            "bet": False,
            "wager_placed": False,
        }
    )


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _quote_from_current(
    *,
    mapping: SportyBetReviewedCanonicalMarketMapping,
    mapped: MappedSportyBetCanonicalSelection,
    selected: SportyBetLiveEventSelection,
    inventory: SportyBetLiveEventQuoteInventory,
) -> SportyBetLiveMappedQuote:
    value = object.__new__(SportyBetLiveMappedQuote)
    return _set_frozen(
        value,
        {
            "fixture_id": mapping.matched_fotmob_fixture_id,
            "event_id": inventory.event_id,
            "canonical_market_id": mapped.canonical_market_id.value,
            "canonical_outcome_id": mapped.canonical_outcome_id.value,
            "canonical_line": mapped.canonical_line,
            "provider_market_id": selected.market_id,
            "provider_market_name": selected.market_name,
            "provider_specifier": selected.specifier,
            "provider_outcome_id": selected.outcome_id,
            "provider_outcome_name": selected.outcome_name,
            "odds_raw": selected.odds_raw,
            "decimal_odds": selected.odds_decimal,
            "observed_at": inventory.observed_at,
            "observation_authority": OBSERVATION_AUTHORITY,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "live_inventory_sha256": inventory.canonical_sha256,
            "source_manifest_sha256": inventory.source_manifest_sha256,
            "source_raw_sha256": inventory.source_raw_sha256,
            "reviewed_mapping_sha256": canonical_mapping_sha256(mapping),
            "settlement_equivalence_authority": (
                mapped.settlement_equivalence_authority.value
            ),
        },
    )


def _mapping_rows(
    mapping: SportyBetReviewedCanonicalMarketMapping,
    inventory: SportyBetLiveEventQuoteInventory,
) -> tuple[tuple[SportyBetLiveMappedQuote, ...], tuple[SportyBetLiveMappingAudit, ...]]:
    quotes: list[SportyBetLiveMappedQuote] = []
    audits: list[SportyBetLiveMappingAudit] = []
    by_native = {
        item.selection_identity: item for item in inventory.selections
    }
    for mapped in mapping.mapped_selections:
        if not mapped.canonical_market_mapping_authorized:
            raise SportyBetLiveEventQuoteEvidenceError(
                "reviewed mapping row lacks canonical mapping authority"
            )
        native_identity = (
            mapped.event_id,
            mapped.provider_market_id,
            mapped.provider_specifier,
            mapped.provider_outcome_id,
        )
        selected = by_native.get(native_identity)
        disposition: str
        if not mapped.bookmaker_equivalence_authorized:
            disposition = "SETTLEMENT_EQUIVALENCE_UNPROVEN"
        elif selected is None:
            disposition = "ABSENT_FROM_CURRENT_EVENT"
        else:
            if (
                selected.market_name != mapped.provider_market_name
                or selected.outcome_name != mapped.provider_selection_label
            ):
                raise SportyBetLiveEventQuoteEvidenceError(
                    "current provider-native identity changed human-readable semantics"
                )
            if not selected.bookable:
                disposition = "CURRENTLY_UNAVAILABLE"
            else:
                disposition = "QUOTED"
                quotes.append(
                    _quote_from_current(
                        mapping=mapping,
                        mapped=mapped,
                        selected=selected,
                        inventory=inventory,
                    )
                )
        audits.append(
            SportyBetLiveMappingAudit(
                provider_market_id=mapped.provider_market_id,
                provider_specifier=mapped.provider_specifier,
                provider_outcome_id=mapped.provider_outcome_id,
                provider_market_name=mapped.provider_market_name,
                provider_outcome_name=mapped.provider_selection_label,
                canonical_market_id=mapped.canonical_market_id.value,
                canonical_outcome_id=mapped.canonical_outcome_id.value,
                canonical_line=mapped.canonical_line,
                disposition=disposition,
            )
        )
    quotes_sorted = tuple(
        sorted(
            quotes,
            key=lambda item: (
                item.canonical_market_id,
                "" if item.canonical_line is None else str(item.canonical_line),
                item.canonical_outcome_id,
            ),
        )
    )
    audits_sorted = tuple(
        sorted(
            audits,
            key=lambda item: (
                item.canonical_market_id,
                "" if item.canonical_line is None else str(item.canonical_line),
                item.canonical_outcome_id,
            ),
        )
    )
    return quotes_sorted, audits_sorted


def _build_bundle(
    *,
    mapping: SportyBetReviewedCanonicalMarketMapping,
    inventory: SportyBetLiveEventQuoteInventory,
    evidence_directory: Path,
    repository_root: Path,
    evaluation_time: datetime,
    proof_mode: str,
) -> SportyBetLiveMappedQuoteBundle:
    validate_direct_event_source_contract()
    if type(mapping) is not SportyBetReviewedCanonicalMarketMapping:
        raise SportyBetLiveEventQuoteEvidenceError(
            "mapping must be exact reviewed SportyBet mapping"
        )
    if proof_mode not in {REPLAY_PROOF_MODE, LIVE_PROOF_MODE}:
        raise SportyBetLiveEventQuoteEvidenceError("proof_mode is invalid")
    now = _utc(evaluation_time, "evaluation_time")
    if inventory.event_id != mapping.sportybet_event_id:
        raise SportyBetLiveEventQuoteEvidenceError(
            "mapping/current live event identity mismatch"
        )
    if not inventory.prematch_bookable_observed:
        raise SportyBetLiveEventQuoteEvidenceError(
            "current SportyBet event is not pre-match/bookable"
        )
    age = (now - inventory.observed_at).total_seconds()
    if not math.isfinite(age) or age < 0:
        raise SportyBetLiveEventQuoteEvidenceError(
            "direct-provider observation is future-dated"
        )
    if age > MAX_OBSERVATION_AGE_SECONDS:
        raise SportyBetLiveEventQuoteEvidenceError(
            "direct-provider odds observation is stale"
        )
    if now + timedelta(seconds=MINIMUM_LEAD_SECONDS) >= inventory.kickoff_utc:
        raise SportyBetLiveEventQuoteEvidenceError(
            "current SportyBet event is too close to kickoff"
        )
    quotes, audits = _mapping_rows(mapping, inventory)
    value = object.__new__(SportyBetLiveMappedQuoteBundle)
    return _set_frozen(
        value,
        {
            "dataset_name": MAPPED_QUOTE_DATASET_NAME,
            "status": LIVE_STATUS if proof_mode == LIVE_PROOF_MODE else REPLAY_STATUS,
            "proof_mode": proof_mode,
            "event_id": inventory.event_id,
            "fixture_id": mapping.matched_fotmob_fixture_id,
            "evaluation_time": now,
            "observed_at": inventory.observed_at,
            "kickoff_utc": inventory.kickoff_utc,
            "observation_age_seconds": age,
            "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
            "max_observation_age_seconds": MAX_OBSERVATION_AGE_SECONDS,
            "live_inventory_sha256": inventory.canonical_sha256,
            "reviewed_mapping_sha256": canonical_mapping_sha256(mapping),
            "quotes": quotes,
            "mapping_audits": audits,
            "authority": _bundle_authority(proof_mode),
            "next_boundary": NEXT_BOUNDARY,
            "_mapping": mapping,
            "_inventory": inventory,
            "_evidence_directory": Path(evidence_directory),
            "_repository_root": Path(repository_root),
        },
    )


def issue_mapped_quote_bundle_as_of(
    *,
    mapping: SportyBetReviewedCanonicalMarketMapping,
    evidence_directory: Path,
    repository_root: Path,
    evaluation_time: datetime,
) -> SportyBetLiveMappedQuoteBundle:
    """Deterministic replay.  This function never claims wall-clock currentness."""
    inventory = build_live_event_quote_inventory(
        evidence_directory, repository_root=repository_root
    )
    return _build_bundle(
        mapping=mapping,
        inventory=inventory,
        evidence_directory=evidence_directory,
        repository_root=repository_root,
        evaluation_time=evaluation_time,
        proof_mode=REPLAY_PROOF_MODE,
    )


def capture_and_issue_current_mapped_quote_bundle(
    *,
    mapping: SportyBetReviewedCanonicalMarketMapping,
    repository_root: Path,
    execute_live_network: bool,
) -> SportyBetLiveMappedQuoteBundle:
    """Only public issuer permitted to claim current direct-provider odds evidence."""
    if type(mapping) is not SportyBetReviewedCanonicalMarketMapping:
        raise SportyBetLiveEventQuoteEvidenceError(
            "mapping must be exact reviewed SportyBet mapping"
        )
    evidence_directory, _manifest = capture_live_event_quote_evidence(
        event_id=mapping.sportybet_event_id,
        repository_root=repository_root,
        execute_live_network=execute_live_network,
    )
    inventory = build_live_event_quote_inventory(
        evidence_directory, repository_root=repository_root
    )
    return _build_bundle(
        mapping=mapping,
        inventory=inventory,
        evidence_directory=evidence_directory,
        repository_root=repository_root,
        evaluation_time=_now_utc(),
        proof_mode=LIVE_PROOF_MODE,
    )


def verify_mapped_quote_bundle(
    bundle: SportyBetLiveMappedQuoteBundle,
) -> SportyBetLiveMappedQuoteBundle:
    """Rebuild an issued bundle from its exact retained source ancestry."""
    if type(bundle) is not SportyBetLiveMappedQuoteBundle:
        raise SportyBetLiveEventQuoteEvidenceError(
            "bundle must be exact SportyBetLiveMappedQuoteBundle"
        )
    inventory = build_live_event_quote_inventory(
        bundle._evidence_directory,
        repository_root=bundle._repository_root,
    )
    if inventory.to_dict() != bundle._inventory.to_dict():
        raise SportyBetLiveEventQuoteEvidenceError(
            "retained live inventory differs from exact evidence replay"
        )
    rebuilt = _build_bundle(
        mapping=bundle._mapping,
        inventory=inventory,
        evidence_directory=bundle._evidence_directory,
        repository_root=bundle._repository_root,
        evaluation_time=bundle.evaluation_time,
        proof_mode=bundle.proof_mode,
    )
    if rebuilt.to_dict() != bundle.to_dict():
        raise SportyBetLiveEventQuoteEvidenceError(
            "mapped quote bundle differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
