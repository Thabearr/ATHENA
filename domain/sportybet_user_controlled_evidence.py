"""User-controlled SportyBet Lite evidence ingestion.

This boundary never performs network I/O.  It records HTML that a human user
explicitly observed and exported from the reviewed SportyBet Lite surface.  A
user-attested observation time is evidence about when the user observed the
page; it is never promoted to a provider quote timestamp or snapshot identity.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import types
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from domain.sportybet_lite_source_capture import (
    ALLOWED_HOST,
    ALLOWED_OUTPUT_RELATIVE as LIVE_CAPTURE_OUTPUT_RELATIVE,
    DEFAULT_MARKET_GROUP,
    EVENT_DETAIL_PATH,
    INDEX_PATH,
    MAX_MANIFEST_BYTES,
    MAX_RESPONSE_BYTES,
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
    parse_utc_timestamp,
    request_target,
    serialize_utc,
    sha256_bytes,
    strict_json_loads,
    validate_event_id,
    validate_sport_id,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-user-controlled-evidence-v1"
PROVIDER = "SportyBet"
ACQUISITION_MODE = "USER_CONTROLLED_BROWSER_EXPORT"
ATTESTATION = "I_MANUALLY_OBSERVED_AND_EXPORTED_THIS_PAGE"
OBSERVATION_AUTHORITY = "USER_ATTESTED_NOT_PROVIDER_TIMESTAMP"
RAW_FILENAME = "page.html"
MANIFEST_FILENAME = "manifest.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-user-controlled-evidence"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "bookmaker_equivalence_authorized",
        "canonical_market_mapping_authorized",
        "fixture_reconciliation_authorized",
        "fresh_price_authorized",
        "model_integration_authorized",
        "network_acquisition_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "sportybet_execution_authorized",
    }
)


class SportyBetUserEvidenceError(ValueError):
    """Raised when user-controlled SportyBet evidence fails closed."""


def _error_from_capture(exc: Exception) -> SportyBetUserEvidenceError:
    return SportyBetUserEvidenceError(str(exc))


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise SportyBetUserEvidenceError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise SportyBetUserEvidenceError(f"{label} must be timezone-aware")
        return value.astimezone(dt.timezone.utc)
    except SportyBetUserEvidenceError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise SportyBetUserEvidenceError(f"{label} is invalid") from exc


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetUserEvidenceError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetUserEvidenceError(f"safety[{key!r}] must be exact bool False")
        detached[key] = False
    return types.MappingProxyType(detached)


def _safe_query(url: str) -> tuple[SportyBetLiteRequestKind, str | None, str | None, str | None, str]:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise SportyBetUserEvidenceError("source_url is invalid") from exc
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise SportyBetUserEvidenceError("source_url must use the exact reviewed HTTPS SportyBet host")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise SportyBetUserEvidenceError("source_url must not contain user information or a fragment")
    try:
        if parsed.port is not None:
            raise SportyBetUserEvidenceError("source_url must not contain an explicit port")
    except ValueError as exc:
        raise SportyBetUserEvidenceError("source_url port is invalid") from exc
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=False, encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError) as exc:
        raise SportyBetUserEvidenceError("source_url query is invalid") from exc
    query: dict[str, str] = {}
    for key, value in pairs:
        if key in query:
            raise SportyBetUserEvidenceError(f"duplicate source_url query key: {key}")
        query[key] = value
    if parsed.path == INDEX_PATH:
        if query:
            raise SportyBetUserEvidenceError("SportyBet Lite index URL must not carry query parameters")
        kind = SportyBetLiteRequestKind.INDEX
        target = request_target(kind)
        return kind, None, None, None, target
    if parsed.path != EVENT_DETAIL_PATH:
        raise SportyBetUserEvidenceError("source_url path is outside the reviewed SportyBet Lite surface")
    if set(query) != {"eventId", "marketGroupsName", "sportId"}:
        raise SportyBetUserEvidenceError("event detail source_url query keys mismatch")
    try:
        event_id = validate_event_id(query["eventId"])
        sport_id = validate_sport_id(query["sportId"])
    except SportyBetLiteCaptureError as exc:
        raise _error_from_capture(exc) from exc
    if query["marketGroupsName"] != DEFAULT_MARKET_GROUP:
        raise SportyBetUserEvidenceError("marketGroupsName must be exact reviewed Main value")
    kind = SportyBetLiteRequestKind.EVENT_DETAIL
    target = request_target(
        kind,
        event_id=event_id,
        sport_id=sport_id,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    if parsed.query != target.split("?", 1)[1]:
        raise SportyBetUserEvidenceError("source_url query order/encoding must match the reviewed request identity")
    return kind, event_id, sport_id, DEFAULT_MARKET_GROUP, target


def validate_source_url(value: Any) -> tuple[SportyBetLiteRequestKind, str | None, str | None, str | None, str]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SportyBetUserEvidenceError("source_url must be a non-empty exact string")
    return _safe_query(value)


def read_user_html(path: Any) -> bytes:
    try:
        source = Path(path)
    except (TypeError, ValueError) as exc:
        raise SportyBetUserEvidenceError("html file path is invalid") from exc
    if source.is_symlink():
        raise SportyBetUserEvidenceError("html file must not be a symlink")
    try:
        meta = source.stat()
    except OSError as exc:
        raise SportyBetUserEvidenceError("html file cannot be inspected") from exc
    if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= MAX_RESPONSE_BYTES:
        raise SportyBetUserEvidenceError("html file must be a bounded non-empty regular file")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise SportyBetUserEvidenceError("html file cannot be read") from exc
    if len(raw) != meta.st_size or not raw:
        raise SportyBetUserEvidenceError("html file changed while being read")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SportyBetUserEvidenceError("html file must be valid UTF-8") from exc
    return raw


@dataclasses.dataclass(frozen=True)
class SportyBetUserControlledEvidenceManifest:
    schema_version: int
    dataset_name: str
    provider: str
    acquisition_mode: str
    source_url: str
    request_kind: SportyBetLiteRequestKind
    request_target: str
    event_id: str | None
    sport_id: str | None
    market_groups_name: str | None
    observed_at_user_attested: dt.datetime
    imported_at_utc: dt.datetime
    observation_authority: str
    attestation: str
    athena_network_acquisition_performed: bool
    provider_quote_at: None
    provider_snapshot_id: None
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetUserEvidenceError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetUserEvidenceError("dataset/provider mismatch")
        if self.acquisition_mode != ACQUISITION_MODE:
            raise SportyBetUserEvidenceError("acquisition_mode mismatch")
        kind, event_id, sport_id, market_group, target = validate_source_url(self.source_url)
        if self.request_kind is not kind or self.request_target != target:
            raise SportyBetUserEvidenceError("source request identity mismatch")
        if (self.event_id, self.sport_id, self.market_groups_name) != (event_id, sport_id, market_group):
            raise SportyBetUserEvidenceError("provider request fields mismatch")
        observed = _utc(self.observed_at_user_attested, "observed_at_user_attested")
        imported = _utc(self.imported_at_utc, "imported_at_utc")
        if imported < observed:
            raise SportyBetUserEvidenceError("imported_at_utc must not precede the user-attested observation")
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetUserEvidenceError("observation_authority mismatch")
        if self.attestation != ATTESTATION:
            raise SportyBetUserEvidenceError("manual observation attestation mismatch")
        if self.athena_network_acquisition_performed is not False:
            raise SportyBetUserEvidenceError("ATHENA network acquisition must remain false")
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise SportyBetUserEvidenceError("provider quote/snapshot identity is unproven and must remain null")
        if self.raw_file_name != RAW_FILENAME:
            raise SportyBetUserEvidenceError("raw_file_name mismatch")
        if not isinstance(self.raw_sha256, str) or _SHA256_RE.fullmatch(self.raw_sha256) is None:
            raise SportyBetUserEvidenceError("raw_sha256 is invalid")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise SportyBetUserEvidenceError("raw_size is invalid")
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "observed_at_user_attested", observed)
        object.__setattr__(self, "imported_at_utc", imported)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "acquisition_mode": self.acquisition_mode,
            "source_url": self.source_url,
            "request_kind": self.request_kind.value,
            "request_target": self.request_target,
            "event_id": self.event_id,
            "sport_id": self.sport_id,
            "market_groups_name": self.market_groups_name,
            "observed_at_user_attested": serialize_utc(self.observed_at_user_attested),
            "imported_at_utc": serialize_utc(self.imported_at_utc),
            "observation_authority": self.observation_authority,
            "attestation": self.attestation,
            "athena_network_acquisition_performed": False,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "raw_file_name": self.raw_file_name,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "safety": dict(self.safety),
        }


def build_manifest(raw_html: Any, *, source_url: str, observed_at_user_attested: dt.datetime, imported_at_utc: dt.datetime, attestation: str) -> SportyBetUserControlledEvidenceManifest:
    if type(raw_html) is not bytes or not raw_html or len(raw_html) > MAX_RESPONSE_BYTES:
        raise SportyBetUserEvidenceError("raw_html must be bounded non-empty exact bytes")
    try:
        raw_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SportyBetUserEvidenceError("raw_html must be valid UTF-8") from exc
    kind, event_id, sport_id, market_group, target = validate_source_url(source_url)
    return SportyBetUserControlledEvidenceManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        acquisition_mode=ACQUISITION_MODE,
        source_url=source_url,
        request_kind=kind,
        request_target=target,
        event_id=event_id,
        sport_id=sport_id,
        market_groups_name=market_group,
        observed_at_user_attested=observed_at_user_attested,
        imported_at_utc=imported_at_utc,
        observation_authority=OBSERVATION_AUTHORITY,
        attestation=attestation,
        athena_network_acquisition_performed=False,
        provider_quote_at=None,
        provider_snapshot_id=None,
        raw_file_name=RAW_FILENAME,
        raw_sha256=sha256_bytes(raw_html),
        raw_size=len(raw_html),
        safety=_default_safety(),
    )


def canonical_manifest_bytes(manifest: Any) -> bytes:
    if not isinstance(manifest, SportyBetUserControlledEvidenceManifest):
        raise SportyBetUserEvidenceError("manifest type mismatch")
    try:
        return (json.dumps(manifest.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetUserEvidenceError("manifest serialization failed") from exc


def manifest_sha256(manifest: Any) -> str:
    return sha256_bytes(canonical_manifest_bytes(manifest))


def evidence_identifier(manifest: Any) -> str:
    if not isinstance(manifest, SportyBetUserControlledEvidenceManifest):
        raise SportyBetUserEvidenceError("manifest type mismatch")
    identity = {
        "source_url": manifest.source_url,
        "observed_at_user_attested": serialize_utc(manifest.observed_at_user_attested),
        "raw_sha256": manifest.raw_sha256,
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(raw)[:24]


def _manifest_from_mapping(value: Any) -> SportyBetUserControlledEvidenceManifest:
    expected = {field.name for field in dataclasses.fields(SportyBetUserControlledEvidenceManifest)}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SportyBetUserEvidenceError("manifest keys mismatch")
    try:
        return SportyBetUserControlledEvidenceManifest(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            provider=value["provider"],
            acquisition_mode=value["acquisition_mode"],
            source_url=value["source_url"],
            request_kind=SportyBetLiteRequestKind(value["request_kind"]),
            request_target=value["request_target"],
            event_id=value["event_id"],
            sport_id=value["sport_id"],
            market_groups_name=value["market_groups_name"],
            observed_at_user_attested=parse_utc_timestamp(value["observed_at_user_attested"], "observed_at_user_attested"),
            imported_at_utc=parse_utc_timestamp(value["imported_at_utc"], "imported_at_utc"),
            observation_authority=value["observation_authority"],
            attestation=value["attestation"],
            athena_network_acquisition_performed=value["athena_network_acquisition_performed"],
            provider_quote_at=value["provider_quote_at"],
            provider_snapshot_id=value["provider_snapshot_id"],
            raw_file_name=value["raw_file_name"],
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            safety=value["safety"],
        )
    except SportyBetUserEvidenceError:
        raise
    except (KeyError, TypeError, ValueError, SportyBetLiteCaptureError) as exc:
        raise SportyBetUserEvidenceError("manifest is invalid") from exc


def _validate_root(output_root: Any, *, repository_root: Path) -> Path:
    repository = Path(repository_root).resolve(strict=True)
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        supplied = Path(output_root)
    except (TypeError, ValueError) as exc:
        raise SportyBetUserEvidenceError("output root is invalid") from exc
    if ".." in supplied.parts:
        raise SportyBetUserEvidenceError("output root must not contain traversal")
    supplied_abs = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(supplied_abs, "output root")
    except SportyBetLiteCaptureError as exc:
        raise _error_from_capture(exc) from exc
    if supplied_abs.resolve(strict=False) != expected.resolve(strict=False):
        raise SportyBetUserEvidenceError("output root must be the reviewed user-controlled evidence root")
    if expected == repository / LIVE_CAPTURE_OUTPUT_RELATIVE:
        raise SportyBetUserEvidenceError("manual evidence must never share the live-capture root")
    return expected


def verify_evidence_directory(evidence_directory: Any, *, allowed_root: Path) -> SportyBetUserControlledEvidenceManifest:
    directory = Path(evidence_directory)
    root = Path(allowed_root)
    if ".." in directory.parts or ".." in root.parts:
        raise SportyBetUserEvidenceError("evidence paths must not contain traversal")
    try:
        _reject_symlink_components(directory, "evidence directory")
        _reject_symlink_components(root, "allowed root")
        resolved_root = root.resolve(strict=True)
        resolved_dir = directory.resolve(strict=True)
        resolved_dir.relative_to(resolved_root)
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetUserEvidenceError("evidence directory escapes or cannot resolve under allowed root") from exc
    if directory.is_symlink() or not directory.is_dir():
        raise SportyBetUserEvidenceError("evidence directory must be a non-symlink directory")
    if sorted(item.name for item in directory.iterdir()) != [MANIFEST_FILENAME, RAW_FILENAME]:
        raise SportyBetUserEvidenceError("evidence directory contents mismatch")
    try:
        raw = _read_regular(directory / RAW_FILENAME, maximum=MAX_RESPONSE_BYTES, label="manual raw HTML")
        manifest_raw = _read_regular(directory / MANIFEST_FILENAME, maximum=MAX_MANIFEST_BYTES, label="manual manifest")
        mapping = strict_json_loads(manifest_raw)
    except SportyBetLiteCaptureError as exc:
        raise _error_from_capture(exc) from exc
    manifest = _manifest_from_mapping(mapping)
    if manifest_raw != canonical_manifest_bytes(manifest):
        raise SportyBetUserEvidenceError("manifest bytes are not canonical")
    if sha256_bytes(raw) != manifest.raw_sha256 or len(raw) != manifest.raw_size:
        raise SportyBetUserEvidenceError("raw HTML identity mismatch")
    if directory.name != evidence_identifier(manifest):
        raise SportyBetUserEvidenceError("evidence directory identity mismatch")
    return manifest


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportyBetUserEvidenceError(f"refusing to overwrite {path.name}") from exc
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetUserEvidenceError(f"could not durably write {path.name}") from exc


def store_user_controlled_evidence(raw_html: bytes, *, source_url: str, observed_at_user_attested: dt.datetime, imported_at_utc: dt.datetime, attestation: str, repository_root: Path, output_root: Path = ALLOWED_OUTPUT_RELATIVE) -> tuple[Path, SportyBetUserControlledEvidenceManifest]:
    repository = Path(repository_root).resolve(strict=True)
    root = _validate_root(output_root, repository_root=repository)
    try:
        _ensure_directory_tree_durable(root, boundary=repository)
    except SportyBetLiteCaptureError as exc:
        raise _error_from_capture(exc) from exc
    manifest = build_manifest(
        raw_html,
        source_url=source_url,
        observed_at_user_attested=observed_at_user_attested,
        imported_at_utc=imported_at_utc,
        attestation=attestation,
    )
    directory = root / evidence_identifier(manifest)
    if directory.exists():
        existing = verify_evidence_directory(directory, allowed_root=root)
        try:
            existing_raw = _read_regular(directory / RAW_FILENAME, maximum=MAX_RESPONSE_BYTES, label="manual raw HTML")
        except SportyBetLiteCaptureError as exc:
            raise _error_from_capture(exc) from exc
        if existing.to_dict() != manifest.to_dict() or existing_raw != raw_html:
            raise SportyBetUserEvidenceError("evidence identifier collision")
        return directory, existing
    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(directory)
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetUserEvidenceError("could not create evidence directory") from exc
    _write_exclusive(directory / RAW_FILENAME, raw_html)
    _write_exclusive(directory / MANIFEST_FILENAME, canonical_manifest_bytes(manifest))
    verified = verify_evidence_directory(directory, allowed_root=root)
    try:
        _sync_directory(directory)
        _sync_directory(root)
    except SportyBetLiteCaptureError as exc:
        raise _error_from_capture(exc) from exc
    return directory, verified
