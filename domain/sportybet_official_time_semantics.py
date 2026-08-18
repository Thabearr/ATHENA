"""Offline qualification of SportyBet's official website time semantics.

This boundary accepts only a human-exported copy of the exact reviewed SportyBet
Nigeria Terms & Conditions page. It performs no network I/O. A successful result
proves only the provider's global website rule that times relate to GMT unless
stated otherwise. Event-local override checks and event-year proof remain separate
boundaries, and every downstream betting authority remains false.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import re
import types
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from domain.sportybet_lite_source_capture import (
    MAX_MANIFEST_BYTES,
    MAX_RESPONSE_BYTES,
    SportyBetLiteCaptureError,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
    strict_json_loads,
)
from domain.sportybet_machine_event_header_candidate import visible_text_tokens
from domain.sportybet_user_controlled_evidence import (
    SportyBetUserEvidenceError,
    read_user_html,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-official-time-semantics-v1"
PROVIDER = "SportyBet"
SOURCE_ROLE = "OFFICIAL_PROVIDER_TERMS"
SOURCE_URL = "https://www.sportybet.com/ng/help?nav=terms-and-conditions"
SOURCE_HOST = "www.sportybet.com"
SOURCE_PATH = "/ng/help"
SOURCE_QUERY = "nav=terms-and-conditions"
ACQUISITION_MODE = "USER_CONTROLLED_BROWSER_EXPORT"
ATTESTATION = "I_MANUALLY_OBSERVED_AND_EXPORTED_THIS_OFFICIAL_PROVIDER_PAGE"
OBSERVATION_AUTHORITY = "USER_ATTESTED_NOT_PROVIDER_TIMESTAMP"
EXPECTED_STATEMENT = (
    "All times stated on the Website and/or referred to by SportyBet staff "
    "relate to GMT unless stated otherwise."
)
EXPECTED_STATEMENT_SHA256 = (
    "2fed00c2e1d3e7f2b0b6cff1e4f68ee17874529af54958a14aed68e7ca0b7de4"
)
SEMANTIC_STATUS = "QUALIFIED_GLOBAL_WEBSITE_TIME_BASIS"
TIME_ZONE_LABEL = "GMT"
UTC_OFFSET_SECONDS = 0
EVENT_APPLICATION_STATUS = "REQUIRES_EVENT_LOCAL_OVERRIDE_CHECK"
RAW_FILENAME = "page.html"
QUALIFICATION_FILENAME = "qualification.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-official-time-semantics"
)
MAX_QUALIFICATION_BYTES = MAX_MANIFEST_BYTES

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_STATEMENT_RE = re.compile(
    r"All times stated on the Website and/or referred to by SportyBet staff "
    r"relate to (?P<zone>[A-Z]{2,5}) unless stated otherwise\.",
    flags=re.ASCII,
)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "bookmaker_equivalence_authorized",
        "booking_code_authorized",
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
_EXPECTED_DIRECTORY_FILES = tuple(sorted((RAW_FILENAME, QUALIFICATION_FILENAME)))


class SportyBetOfficialTimeSemanticsError(ValueError):
    """Raised when the official time-semantics evidence boundary fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetOfficialTimeSemanticsError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetOfficialTimeSemanticsError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise SportyBetOfficialTimeSemanticsError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise SportyBetOfficialTimeSemanticsError(
                f"{label} must be timezone-aware"
            )
        return value.astimezone(dt.timezone.utc)
    except SportyBetOfficialTimeSemanticsError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise SportyBetOfficialTimeSemanticsError(f"{label} is invalid") from exc


def validate_source_url(value: Any) -> str:
    if type(value) is not str or value != SOURCE_URL:
        raise SportyBetOfficialTimeSemanticsError(
            "source_url must be the exact reviewed SportyBet Nigeria Terms & Conditions URL"
        )
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise SportyBetOfficialTimeSemanticsError("source_url is invalid") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != SOURCE_HOST
        or parsed.path != SOURCE_PATH
        or parsed.query != SOURCE_QUERY
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SportyBetOfficialTimeSemanticsError("source_url identity mismatch")
    try:
        if parsed.port is not None:
            raise SportyBetOfficialTimeSemanticsError(
                "source_url must not contain an explicit port"
            )
    except ValueError as exc:
        raise SportyBetOfficialTimeSemanticsError("source_url port is invalid") from exc
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise SportyBetOfficialTimeSemanticsError("source_url query is invalid") from exc
    if pairs != [("nav", "terms-and-conditions")]:
        raise SportyBetOfficialTimeSemanticsError("source_url query identity mismatch")
    return value


def _bounded_utf8_html(raw_html: Any) -> bytes:
    if type(raw_html) is not bytes or not 0 < len(raw_html) <= MAX_RESPONSE_BYTES:
        raise SportyBetOfficialTimeSemanticsError(
            "raw_html must be bounded non-empty exact bytes"
        )
    try:
        raw_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SportyBetOfficialTimeSemanticsError(
            "raw_html must be valid UTF-8"
        ) from exc
    return raw_html


def extract_global_time_semantics(raw_html: Any) -> tuple[str, int]:
    """Qualify and return the exact global website zone plus occurrence count."""
    raw = _bounded_utf8_html(raw_html)
    try:
        visible = " ".join(visible_text_tokens(raw))
    except Exception as exc:
        raise SportyBetOfficialTimeSemanticsError(
            "official page visible-text extraction failed"
        ) from exc
    matches = list(_STATEMENT_RE.finditer(visible))
    if not matches:
        raise SportyBetOfficialTimeSemanticsError(
            "official GMT-unless-stated-otherwise semantics statement not found"
        )
    if {match.group("zone") for match in matches} != {TIME_ZONE_LABEL}:
        raise SportyBetOfficialTimeSemanticsError(
            "official time semantics are conflicting or not exact GMT"
        )
    if {match.group(0) for match in matches} != {EXPECTED_STATEMENT}:
        raise SportyBetOfficialTimeSemanticsError(
            "official time semantics statement text mismatch"
        )
    if sha256_bytes(EXPECTED_STATEMENT.encode("utf-8")) != EXPECTED_STATEMENT_SHA256:
        raise SportyBetOfficialTimeSemanticsError(
            "frozen semantics statement SHA-256 mismatch"
        )
    return TIME_ZONE_LABEL, len(matches)


@dataclasses.dataclass(frozen=True)
class SportyBetOfficialTimeSemanticsQualification:
    schema_version: int
    dataset_name: str
    provider: str
    source_role: str
    source_url: str
    acquisition_mode: str
    observed_at_user_attested: dt.datetime
    imported_at_utc: dt.datetime
    observation_authority: str
    attestation: str
    athena_network_acquisition_performed: bool
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    semantics_statement: str
    semantics_statement_sha256: str
    semantics_statement_occurrence_count: int
    semantic_status: str
    time_zone_label: str
    utc_offset_seconds: int
    unless_stated_otherwise: bool
    event_local_override_check_required: bool
    event_application_status: str
    event_year_proven: bool
    provider_quote_at: None
    provider_snapshot_id: None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetOfficialTimeSemanticsError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetOfficialTimeSemanticsError("dataset/provider mismatch")
        if self.source_role != SOURCE_ROLE:
            raise SportyBetOfficialTimeSemanticsError("source_role mismatch")
        validate_source_url(self.source_url)
        if self.acquisition_mode != ACQUISITION_MODE:
            raise SportyBetOfficialTimeSemanticsError("acquisition_mode mismatch")
        observed = _utc(self.observed_at_user_attested, "observed_at_user_attested")
        imported = _utc(self.imported_at_utc, "imported_at_utc")
        if imported < observed:
            raise SportyBetOfficialTimeSemanticsError(
                "imported_at_utc must not precede the user-attested observation"
            )
        if self.observation_authority != OBSERVATION_AUTHORITY:
            raise SportyBetOfficialTimeSemanticsError("observation_authority mismatch")
        if self.attestation != ATTESTATION:
            raise SportyBetOfficialTimeSemanticsError("manual observation attestation mismatch")
        if self.athena_network_acquisition_performed is not False:
            raise SportyBetOfficialTimeSemanticsError(
                "ATHENA network acquisition must remain false"
            )
        if self.raw_file_name != RAW_FILENAME:
            raise SportyBetOfficialTimeSemanticsError("raw_file_name mismatch")
        if type(self.raw_sha256) is not str or _SHA256_RE.fullmatch(self.raw_sha256) is None:
            raise SportyBetOfficialTimeSemanticsError("raw_sha256 is invalid")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise SportyBetOfficialTimeSemanticsError("raw_size is invalid")
        if self.semantics_statement != EXPECTED_STATEMENT:
            raise SportyBetOfficialTimeSemanticsError("semantics_statement mismatch")
        if self.semantics_statement_sha256 != EXPECTED_STATEMENT_SHA256:
            raise SportyBetOfficialTimeSemanticsError("semantics_statement_sha256 mismatch")
        if (
            type(self.semantics_statement_occurrence_count) is not int
            or self.semantics_statement_occurrence_count < 1
        ):
            raise SportyBetOfficialTimeSemanticsError(
                "semantics_statement_occurrence_count must be a positive exact integer"
            )
        if self.semantic_status != SEMANTIC_STATUS:
            raise SportyBetOfficialTimeSemanticsError("semantic_status mismatch")
        if self.time_zone_label != TIME_ZONE_LABEL:
            raise SportyBetOfficialTimeSemanticsError("time_zone_label mismatch")
        if type(self.utc_offset_seconds) is not int or self.utc_offset_seconds != UTC_OFFSET_SECONDS:
            raise SportyBetOfficialTimeSemanticsError("utc_offset_seconds mismatch")
        if self.unless_stated_otherwise is not True:
            raise SportyBetOfficialTimeSemanticsError(
                "unless_stated_otherwise must be exact True"
            )
        if self.event_local_override_check_required is not True:
            raise SportyBetOfficialTimeSemanticsError(
                "event_local_override_check_required must be exact True"
            )
        if self.event_application_status != EVENT_APPLICATION_STATUS:
            raise SportyBetOfficialTimeSemanticsError("event_application_status mismatch")
        if self.event_year_proven is not False:
            raise SportyBetOfficialTimeSemanticsError("event_year_proven must remain false")
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise SportyBetOfficialTimeSemanticsError(
                "provider quote/snapshot identity is unrelated and must remain null"
            )
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "observed_at_user_attested", observed)
        object.__setattr__(self, "imported_at_utc", imported)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "source_role": self.source_role,
            "source_url": self.source_url,
            "acquisition_mode": self.acquisition_mode,
            "observed_at_user_attested": serialize_utc(self.observed_at_user_attested),
            "imported_at_utc": serialize_utc(self.imported_at_utc),
            "observation_authority": self.observation_authority,
            "attestation": self.attestation,
            "athena_network_acquisition_performed": False,
            "raw_file_name": self.raw_file_name,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "semantics_statement": self.semantics_statement,
            "semantics_statement_sha256": self.semantics_statement_sha256,
            "semantics_statement_occurrence_count": self.semantics_statement_occurrence_count,
            "semantic_status": self.semantic_status,
            "time_zone_label": self.time_zone_label,
            "utc_offset_seconds": self.utc_offset_seconds,
            "unless_stated_otherwise": True,
            "event_local_override_check_required": True,
            "event_application_status": self.event_application_status,
            "event_year_proven": False,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "safety": dict(self.safety),
        }


def build_qualification(
    raw_html: Any,
    *,
    source_url: str,
    observed_at_user_attested: dt.datetime,
    imported_at_utc: dt.datetime,
    attestation: str,
) -> SportyBetOfficialTimeSemanticsQualification:
    raw = _bounded_utf8_html(raw_html)
    validate_source_url(source_url)
    zone, occurrences = extract_global_time_semantics(raw)
    if zone != TIME_ZONE_LABEL:
        raise SportyBetOfficialTimeSemanticsError("qualified time zone mismatch")
    return SportyBetOfficialTimeSemanticsQualification(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        source_role=SOURCE_ROLE,
        source_url=source_url,
        acquisition_mode=ACQUISITION_MODE,
        observed_at_user_attested=observed_at_user_attested,
        imported_at_utc=imported_at_utc,
        observation_authority=OBSERVATION_AUTHORITY,
        attestation=attestation,
        athena_network_acquisition_performed=False,
        raw_file_name=RAW_FILENAME,
        raw_sha256=sha256_bytes(raw),
        raw_size=len(raw),
        semantics_statement=EXPECTED_STATEMENT,
        semantics_statement_sha256=EXPECTED_STATEMENT_SHA256,
        semantics_statement_occurrence_count=occurrences,
        semantic_status=SEMANTIC_STATUS,
        time_zone_label=TIME_ZONE_LABEL,
        utc_offset_seconds=UTC_OFFSET_SECONDS,
        unless_stated_otherwise=True,
        event_local_override_check_required=True,
        event_application_status=EVENT_APPLICATION_STATUS,
        event_year_proven=False,
        provider_quote_at=None,
        provider_snapshot_id=None,
        safety=_default_safety(),
    )


def canonical_qualification_bytes(value: Any) -> bytes:
    if not isinstance(value, SportyBetOfficialTimeSemanticsQualification):
        raise SportyBetOfficialTimeSemanticsError("qualification type mismatch")
    try:
        return (
            json.dumps(
                value.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetOfficialTimeSemanticsError(
            "qualification serialization failed"
        ) from exc


def qualification_sha256(value: Any) -> str:
    return sha256_bytes(canonical_qualification_bytes(value))


def evidence_identifier(value: Any) -> str:
    if not isinstance(value, SportyBetOfficialTimeSemanticsQualification):
        raise SportyBetOfficialTimeSemanticsError("qualification type mismatch")
    identity = {
        "source_url": value.source_url,
        "observed_at_user_attested": serialize_utc(value.observed_at_user_attested),
        "raw_sha256": value.raw_sha256,
        "semantics_statement_sha256": value.semantics_statement_sha256,
    }
    raw = json.dumps(
        identity,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)[:24]


def _qualification_from_mapping(value: Any) -> SportyBetOfficialTimeSemanticsQualification:
    expected = {
        field.name for field in dataclasses.fields(SportyBetOfficialTimeSemanticsQualification)
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SportyBetOfficialTimeSemanticsError("qualification keys mismatch")
    try:
        return SportyBetOfficialTimeSemanticsQualification(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            provider=value["provider"],
            source_role=value["source_role"],
            source_url=value["source_url"],
            acquisition_mode=value["acquisition_mode"],
            observed_at_user_attested=parse_utc_timestamp(
                value["observed_at_user_attested"], "observed_at_user_attested"
            ),
            imported_at_utc=parse_utc_timestamp(value["imported_at_utc"], "imported_at_utc"),
            observation_authority=value["observation_authority"],
            attestation=value["attestation"],
            athena_network_acquisition_performed=value[
                "athena_network_acquisition_performed"
            ],
            raw_file_name=value["raw_file_name"],
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            semantics_statement=value["semantics_statement"],
            semantics_statement_sha256=value["semantics_statement_sha256"],
            semantics_statement_occurrence_count=value[
                "semantics_statement_occurrence_count"
            ],
            semantic_status=value["semantic_status"],
            time_zone_label=value["time_zone_label"],
            utc_offset_seconds=value["utc_offset_seconds"],
            unless_stated_otherwise=value["unless_stated_otherwise"],
            event_local_override_check_required=value[
                "event_local_override_check_required"
            ],
            event_application_status=value["event_application_status"],
            event_year_proven=value["event_year_proven"],
            provider_quote_at=value["provider_quote_at"],
            provider_snapshot_id=value["provider_snapshot_id"],
            safety=value["safety"],
        )
    except SportyBetOfficialTimeSemanticsError:
        raise
    except (KeyError, TypeError, ValueError, SportyBetLiteCaptureError) as exc:
        raise SportyBetOfficialTimeSemanticsError("qualification is invalid") from exc


def _validate_root(output_root: Any, *, repository_root: Path) -> Path:
    repository = Path(repository_root).resolve(strict=True)
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        supplied = Path(output_root)
    except (TypeError, ValueError) as exc:
        raise SportyBetOfficialTimeSemanticsError("output root is invalid") from exc
    if ".." in supplied.parts:
        raise SportyBetOfficialTimeSemanticsError("output root must not contain traversal")
    supplied_abs = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(supplied_abs, "output root")
    except SportyBetLiteCaptureError as exc:
        raise SportyBetOfficialTimeSemanticsError(str(exc)) from exc
    if supplied_abs.resolve(strict=False) != expected.resolve(strict=False):
        raise SportyBetOfficialTimeSemanticsError(
            "output root must be the reviewed official-time-semantics evidence root"
        )
    return expected


def verify_evidence_directory(
    evidence_directory: Any,
    *,
    allowed_root: Path,
) -> SportyBetOfficialTimeSemanticsQualification:
    directory = Path(evidence_directory)
    root = Path(allowed_root)
    if ".." in directory.parts or ".." in root.parts:
        raise SportyBetOfficialTimeSemanticsError("evidence paths must not contain traversal")
    try:
        _reject_symlink_components(directory, "evidence directory")
        _reject_symlink_components(root, "allowed root")
        resolved_root = root.resolve(strict=True)
        resolved_dir = directory.resolve(strict=True)
        resolved_dir.relative_to(resolved_root)
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetOfficialTimeSemanticsError(
            "evidence directory escapes or cannot resolve under allowed root"
        ) from exc
    if directory.is_symlink() or not directory.is_dir():
        raise SportyBetOfficialTimeSemanticsError(
            "evidence directory must be a non-symlink directory"
        )
    try:
        names = tuple(sorted(item.name for item in directory.iterdir()))
    except OSError as exc:
        raise SportyBetOfficialTimeSemanticsError(
            "evidence directory cannot be enumerated"
        ) from exc
    if names != _EXPECTED_DIRECTORY_FILES:
        raise SportyBetOfficialTimeSemanticsError("evidence directory contents mismatch")
    try:
        raw = _read_regular(
            directory / RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="official time-semantics raw HTML",
        )
        qualification_raw = _read_regular(
            directory / QUALIFICATION_FILENAME,
            maximum=MAX_QUALIFICATION_BYTES,
            label="official time-semantics qualification",
        )
        mapping = strict_json_loads(qualification_raw)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetOfficialTimeSemanticsError(str(exc)) from exc
    qualification = _qualification_from_mapping(mapping)
    if qualification_raw != canonical_qualification_bytes(qualification):
        raise SportyBetOfficialTimeSemanticsError("qualification bytes are not canonical")
    if sha256_bytes(raw) != qualification.raw_sha256 or len(raw) != qualification.raw_size:
        raise SportyBetOfficialTimeSemanticsError("raw HTML identity mismatch")
    zone, occurrences = extract_global_time_semantics(raw)
    if (
        zone != qualification.time_zone_label
        or occurrences != qualification.semantics_statement_occurrence_count
    ):
        raise SportyBetOfficialTimeSemanticsError(
            "stored qualification does not replay from raw HTML"
        )
    if directory.name != evidence_identifier(qualification):
        raise SportyBetOfficialTimeSemanticsError("evidence directory identity mismatch")
    return qualification


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportyBetOfficialTimeSemanticsError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetOfficialTimeSemanticsError(
            f"could not durably write {path.name}"
        ) from exc


def _cleanup_partial_directory(directory: Path, root: Path) -> None:
    """Best-effort is forbidden: either the partial directory is removed or cleanup fails."""
    try:
        if not directory.exists():
            return
        if directory.is_symlink() or not directory.is_dir():
            raise SportyBetOfficialTimeSemanticsError(
                "partial evidence path changed type during cleanup"
            )
        entries = list(directory.iterdir())
        if any(entry.name not in _EXPECTED_DIRECTORY_FILES for entry in entries):
            raise SportyBetOfficialTimeSemanticsError(
                "partial evidence directory contains an unexpected entry"
            )
        for entry in entries:
            if entry.is_symlink() or not entry.is_file():
                raise SportyBetOfficialTimeSemanticsError(
                    "partial evidence directory contains a non-regular entry"
                )
            entry.unlink()
        _sync_directory(directory)
        directory.rmdir()
        _sync_directory(root)
    except SportyBetOfficialTimeSemanticsError:
        raise
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetOfficialTimeSemanticsError(
            "could not clean partial official time-semantics evidence"
        ) from exc


def store_official_time_semantics_evidence(
    raw_html: Any,
    *,
    source_url: str,
    observed_at_user_attested: dt.datetime,
    imported_at_utc: dt.datetime,
    attestation: str,
    repository_root: Path,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> tuple[Path, SportyBetOfficialTimeSemanticsQualification]:
    raw = _bounded_utf8_html(raw_html)
    repository = Path(repository_root).resolve(strict=True)
    root = _validate_root(output_root, repository_root=repository)
    try:
        _ensure_directory_tree_durable(root, boundary=repository)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetOfficialTimeSemanticsError(str(exc)) from exc
    qualification = build_qualification(
        raw,
        source_url=source_url,
        observed_at_user_attested=observed_at_user_attested,
        imported_at_utc=imported_at_utc,
        attestation=attestation,
    )
    directory = root / evidence_identifier(qualification)
    if directory.exists():
        existing = verify_evidence_directory(directory, allowed_root=root)
        try:
            existing_raw = _read_regular(
                directory / RAW_FILENAME,
                maximum=MAX_RESPONSE_BYTES,
                label="official time-semantics raw HTML",
            )
        except SportyBetLiteCaptureError as exc:
            raise SportyBetOfficialTimeSemanticsError(str(exc)) from exc
        if existing.to_dict() != qualification.to_dict() or existing_raw != raw:
            raise SportyBetOfficialTimeSemanticsError(
                "official time-semantics evidence identifier collision"
            )
        return directory, existing

    created = False
    try:
        directory.mkdir(exist_ok=False)
        created = True
        _sync_directory(root)
        _sync_directory(directory)
        _write_exclusive(directory / RAW_FILENAME, raw)
        _write_exclusive(
            directory / QUALIFICATION_FILENAME,
            canonical_qualification_bytes(qualification),
        )
        verified = verify_evidence_directory(directory, allowed_root=root)
        _sync_directory(directory)
        _sync_directory(root)
        return directory, verified
    except (OSError, SportyBetLiteCaptureError, SportyBetOfficialTimeSemanticsError) as exc:
        if created:
            try:
                _cleanup_partial_directory(directory, root)
            except SportyBetOfficialTimeSemanticsError as cleanup_exc:
                raise SportyBetOfficialTimeSemanticsError(
                    "official time-semantics evidence write failed and cleanup also failed"
                ) from cleanup_exc
        if isinstance(exc, SportyBetOfficialTimeSemanticsError):
            raise
        raise SportyBetOfficialTimeSemanticsError(
            "could not durably store official time-semantics evidence"
        ) from exc


def parse_observed_at(value: Any) -> dt.datetime:
    try:
        return parse_utc_timestamp(value, "observed_at_user_attested")
    except SportyBetLiteCaptureError as exc:
        raise SportyBetOfficialTimeSemanticsError(str(exc)) from exc


def read_official_time_semantics_html(path: Any) -> bytes:
    try:
        return read_user_html(path)
    except SportyBetUserEvidenceError as exc:
        raise SportyBetOfficialTimeSemanticsError(str(exc)) from exc
