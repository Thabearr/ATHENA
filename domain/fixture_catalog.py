"""Offline fixture-catalog compiler with strict provenance validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
SOURCE_NAME = "FOTMOB"
MANIFEST_DATASET_NAME = "athena-fixture-catalog-manifest-v1"
STRICT_CATALOG_TOP_LEVEL_KEYS = frozenset({"schema_version", "fixtures"})
STRICT_CATALOG_FIXTURE_KEYS = frozenset({"fixture_identifier", "kickoff"})
INPUT_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "source",
        "source_fixture_identifier",
        "home_team",
        "away_team",
        "competition",
        "kickoff",
        "source_reference",
        "reviewed_at",
        "evidence_file_path",
        "evidence_sha256",
    }
)
SAFETY_FLAGS = {
    "network_requests": False,
    "scraping": False,
    "browser_automation": False,
    "credential_use": False,
    "odds_collection": False,
    "bookmaker_qualification": False,
    "market_activation": False,
    "bet_decision": False,
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FixtureCatalogError(ValueError):
    """Raised when catalog input, evidence, or outputs fail closed."""


@dataclass(frozen=True)
class FixtureProvenanceRecord:
    fixture_identifier: str
    source_fixture_identifier: str
    home_team: str
    away_team: str
    competition: str
    kickoff: datetime
    source_reference: str
    reviewed_at: datetime
    evidence_file_path: str
    evidence_sha256: str

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "kickoff": serialize_utc(self.kickoff),
        }

    def provenance_entry(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "source_fixture_identifier": self.source_fixture_identifier,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff": serialize_utc(self.kickoff),
            "source_reference": self.source_reference,
            "reviewed_at": serialize_utc(self.reviewed_at),
            "evidence_file_path": self.evidence_file_path,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class FixtureCatalogResult:
    catalog: dict[str, Any]
    manifest: dict[str, Any]
    catalog_bytes: bytes
    manifest_bytes: bytes
    normalized_input_bytes: bytes
    normalized_input_sha256: str
    records: tuple[FixtureProvenanceRecord, ...]
    as_of: datetime
    minimum_lead_seconds: int
    generator_commit: str
    tracked_worktree_clean: bool


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixtureCatalogError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FixtureCatalogError(f"Invalid JSON constant: {value}")


def _loads_strict_json(text: str, label: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FixtureCatalogError:
        raise
    except json.JSONDecodeError as error:
        raise FixtureCatalogError(f"{label} is not valid JSON: {error}") from error


def _require_strict_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise FixtureCatalogError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise FixtureCatalogError(f"{label} must not contain surrounding whitespace")
    return value


def _require_strict_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise FixtureCatalogError(f"{label} must be an integer")
    return value


def parse_utc_timestamp(value: Any, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, bool) or value is None:
        raise FixtureCatalogError(f"{label} must be a timezone-aware ISO-8601 timestamp")
    elif not isinstance(value, str) or not value or value != value.strip():
        raise FixtureCatalogError(f"{label} must be a timezone-aware ISO-8601 timestamp")
    else:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise FixtureCatalogError(f"{label} is not valid ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixtureCatalogError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def serialize_utc(value: datetime) -> str:
    parsed = parse_utc_timestamp(value, "timestamp")
    text = parsed.isoformat(timespec="microseconds")
    return text.replace("+00:00", "Z")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _ensure_regular_non_symlink_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise FixtureCatalogError(f"{label} must be a regular non-symlink file")
    return path


def _ensure_existing_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise FixtureCatalogError(f"{label} must be an existing directory")
    return path


def _ensure_no_symlink_components(path: Path, label: str) -> Path:
    absolute = path if path.is_absolute() else Path.cwd() / path
    anchor = Path(absolute.anchor) if absolute.anchor else Path.cwd().anchor
    current = Path(anchor) if anchor else Path(".")
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise FixtureCatalogError(f"{label} contains a forbidden symlink component")
    return absolute


def _resolve_relative_file(root: Path, relative_path: str, label: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise FixtureCatalogError(f"{label} must be a non-empty relative path")
    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.anchor:
        raise FixtureCatalogError(f"{label} must be relative")
    if any(part == ".." for part in candidate.parts):
        raise FixtureCatalogError(f"{label} must not contain path traversal")
    root_resolved = _ensure_no_symlink_components(root, "Evidence root")
    _ensure_existing_directory(root_resolved, "Evidence root")
    current = root_resolved
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise FixtureCatalogError(f"{label} must not contain symlink components")
        if not current.exists():
            raise FixtureCatalogError(f"{label} does not exist")
    if current.is_symlink() or not current.is_file():
        raise FixtureCatalogError(f"{label} must be a regular file")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as error:
        raise FixtureCatalogError(
            f"{label} must resolve beneath the evidence root"
        ) from error
    return resolved


def _validate_evidence_file(root: Path, relative_path: str, expected_sha256: str) -> str:
    if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
        raise FixtureCatalogError("evidence_sha256 must be exactly 64 lowercase hex characters")
    resolved = _resolve_relative_file(root, relative_path, "evidence_file_path")
    actual = stream_sha256(resolved)
    if actual != expected_sha256:
        raise FixtureCatalogError("evidence_sha256 does not match the evidence file")
    return actual


def _normalize_record_payload(payload: Mapping[str, Any], evidence_root: Path) -> FixtureProvenanceRecord:
    if set(payload) != INPUT_RECORD_KEYS:
        unexpected = sorted(set(payload) - INPUT_RECORD_KEYS)
        missing = sorted(INPUT_RECORD_KEYS - set(payload))
        details: list[str] = []
        if missing:
            details.append(f"missing keys: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected keys: {', '.join(unexpected)}")
        raise FixtureCatalogError("; ".join(details) or "Invalid input record keys")

    schema_version = _require_strict_int(payload["schema_version"], "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise FixtureCatalogError("schema_version must be exactly 1")
    source = _require_strict_string(payload["source"], "source")
    if source != SOURCE_NAME:
        raise FixtureCatalogError("source must be exactly FOTMOB")

    source_fixture_identifier = _require_strict_string(
        payload["source_fixture_identifier"], "source_fixture_identifier"
    )
    home_team = _require_strict_string(payload["home_team"], "home_team")
    away_team = _require_strict_string(payload["away_team"], "away_team")
    if home_team == away_team:
        raise FixtureCatalogError("home_team and away_team must differ")
    competition = _require_strict_string(payload["competition"], "competition")
    kickoff = parse_utc_timestamp(payload["kickoff"], "kickoff")
    source_reference = _require_strict_string(payload["source_reference"], "source_reference")
    reviewed_at = parse_utc_timestamp(payload["reviewed_at"], "reviewed_at")
    return FixtureProvenanceRecord(
        fixture_identifier=f"FOTMOB:{source_fixture_identifier}",
        source_fixture_identifier=source_fixture_identifier,
        home_team=home_team,
        away_team=away_team,
        competition=competition,
        kickoff=kickoff,
        source_reference=source_reference,
        reviewed_at=reviewed_at,
        evidence_file_path=_require_strict_string(
            payload["evidence_file_path"], "evidence_file_path"
        ),
        evidence_sha256=payload["evidence_sha256"],
    )


def load_fixture_provenance_records(
    input_path: Path,
    *,
    evidence_root: Path,
    as_of: datetime,
    minimum_lead_seconds: int,
) -> tuple[FixtureProvenanceRecord, ...]:
    try:
        raw = input_path.read_bytes()
    except OSError as error:
        raise FixtureCatalogError(f"Could not read input file: {input_path}") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FixtureCatalogError("Input must be valid UTF-8") from error
    if not text:
        raise FixtureCatalogError("Input must contain at least one record")
    if minimum_lead_seconds < 0:
        raise FixtureCatalogError("minimum_lead_seconds must be non-negative")
    normalized_as_of = parse_utc_timestamp(as_of, "as_of")
    records: list[FixtureProvenanceRecord] = []
    seen_source_ids: set[str] = set()
    seen_fixture_ids: set[str] = set()
    seen_exact_rows: set[tuple[Any, ...]] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "":
            raise FixtureCatalogError(f"Blank line is forbidden at line {line_number}")
        payload = _loads_strict_json(line, f"line {line_number}")
        if not isinstance(payload, Mapping):
            raise FixtureCatalogError(f"Line {line_number} must be a JSON object")
        record = _normalize_record_payload(payload, evidence_root)
        if record.source_fixture_identifier in seen_source_ids:
            raise FixtureCatalogError(
                f"Duplicate source_fixture_identifier: {record.source_fixture_identifier}"
            )
        if record.fixture_identifier in seen_fixture_ids:
            raise FixtureCatalogError(f"Duplicate fixture_identifier: {record.fixture_identifier}")
        exact_row = (
            record.source_fixture_identifier,
            record.home_team,
            record.away_team,
            record.competition,
            serialize_utc(record.kickoff),
            record.source_reference,
            serialize_utc(record.reviewed_at),
            record.evidence_file_path,
            record.evidence_sha256,
        )
        if exact_row in seen_exact_rows:
            raise FixtureCatalogError("Duplicate exact fixture row")
        if record.reviewed_at > normalized_as_of:
            raise FixtureCatalogError("reviewed_at must not be after as_of")
        if record.kickoff < normalized_as_of + timedelta(seconds=minimum_lead_seconds):
            raise FixtureCatalogError("kickoff does not satisfy the minimum lead time")
        _validate_evidence_file(
            evidence_root,
            record.evidence_file_path,
            record.evidence_sha256,
        )
        seen_source_ids.add(record.source_fixture_identifier)
        seen_fixture_ids.add(record.fixture_identifier)
        seen_exact_rows.add(exact_row)
        records.append(record)
    if not records:
        raise FixtureCatalogError("Input must contain at least one fixture record")
    return tuple(records)


def build_strict_catalog(records: Sequence[FixtureProvenanceRecord]) -> dict[str, Any]:
    if not records:
        raise FixtureCatalogError("Input must contain at least one fixture record")
    seen: set[str] = set()
    for record in records:
        if record.fixture_identifier in seen:
            raise FixtureCatalogError(
                f"Duplicate fixture_identifier: {record.fixture_identifier}"
            )
        seen.add(record.fixture_identifier)
    ordered = tuple(sorted(records, key=lambda item: (item.kickoff, item.fixture_identifier)))
    return {
        "schema_version": SCHEMA_VERSION,
        "fixtures": [record.catalog_entry() for record in ordered],
    }


def build_manifest(
    *,
    records: Sequence[FixtureProvenanceRecord],
    catalog_bytes: bytes,
    normalized_input_bytes: bytes,
    as_of: datetime,
    minimum_lead_seconds: int,
    generator_commit: str,
    tracked_worktree_clean: bool,
) -> dict[str, Any]:
    ordered = tuple(sorted(records, key=lambda item: (item.kickoff, item.fixture_identifier)))
    kickoff_values = [record.kickoff for record in ordered]
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": MANIFEST_DATASET_NAME,
        "generator": "scripts.manage_fixture_catalog",
        "generator_commit": generator_commit,
        "tracked_worktree_clean": tracked_worktree_clean,
        "source": SOURCE_NAME,
        "as_of": serialize_utc(as_of),
        "minimum_lead_seconds": minimum_lead_seconds,
        "fixture_count": len(ordered),
        "earliest_kickoff": serialize_utc(min(kickoff_values)),
        "latest_kickoff": serialize_utc(max(kickoff_values)),
        "catalog_byte_size": len(catalog_bytes),
        "catalog_sha256": sha256_bytes(catalog_bytes),
        "normalized_input_byte_size": len(normalized_input_bytes),
        "normalized_input_sha256": sha256_bytes(normalized_input_bytes),
        "deterministic_ordering_rules": [
            "normalized input stream serializes sorted provenance records as canonical JSON Lines",
            "fixtures sort by kickoff then fixture_identifier",
            "provenance records use the same ordering as the strict catalog",
            "JSON serializes with sorted keys, indent 2, UTF-8, and a final newline",
        ],
        "provenance_records": [record.provenance_entry() for record in ordered],
        "safety": dict(SAFETY_FLAGS),
    }


def compile_fixture_catalog(
    *,
    input_path: Path,
    evidence_root: Path,
    as_of: datetime,
    minimum_lead_seconds: int = 0,
    code_state: Mapping[str, Any] | None = None,
) -> FixtureCatalogResult:
    if code_state is None:
        from scripts.freeze_evidence_baseline import get_code_state

        code_state = get_code_state(Path(__file__).resolve().parents[1])
    generator_commit = _require_full_git_sha(
        code_state.get("evidence_git_head_sha"),
        "evidence_git_head_sha",
    )
    tracked_worktree_clean = bool(code_state.get("tracked_worktree_clean"))
    if not tracked_worktree_clean:
        raise FixtureCatalogError("Tracked worktree must be clean")
    records = load_fixture_provenance_records(
        input_path,
        evidence_root=evidence_root,
        as_of=as_of,
        minimum_lead_seconds=minimum_lead_seconds,
    )
    ordered_records = tuple(
        sorted(records, key=lambda item: (item.kickoff, item.fixture_identifier))
    )
    normalized_input_bytes = b"".join(
        canonical_json_bytes(record.provenance_entry()) for record in ordered_records
    )
    catalog = build_strict_catalog(ordered_records)
    catalog_bytes = canonical_json_bytes(catalog)
    manifest = build_manifest(
        records=ordered_records,
        catalog_bytes=catalog_bytes,
        normalized_input_bytes=normalized_input_bytes,
        as_of=as_of,
        minimum_lead_seconds=minimum_lead_seconds,
        generator_commit=generator_commit,
        tracked_worktree_clean=tracked_worktree_clean,
    )
    manifest_bytes = canonical_json_bytes(manifest)
    return FixtureCatalogResult(
        catalog=catalog,
        manifest=manifest,
        catalog_bytes=catalog_bytes,
        manifest_bytes=manifest_bytes,
        normalized_input_bytes=normalized_input_bytes,
        normalized_input_sha256=sha256_bytes(normalized_input_bytes),
        records=ordered_records,
        as_of=parse_utc_timestamp(as_of, "as_of"),
        minimum_lead_seconds=minimum_lead_seconds,
        generator_commit=generator_commit,
        tracked_worktree_clean=tracked_worktree_clean,
    )


def _require_full_git_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise FixtureCatalogError(f"{label} must be a full 40-character Git SHA")
    return value.lower()


def strict_catalog_keys() -> frozenset[str]:
    return STRICT_CATALOG_TOP_LEVEL_KEYS


def strict_fixture_keys() -> frozenset[str]:
    return STRICT_CATALOG_FIXTURE_KEYS


__all__ = [
    "FixtureCatalogError",
    "FixtureCatalogResult",
    "FixtureProvenanceRecord",
    "INPUT_RECORD_KEYS",
    "MANIFEST_DATASET_NAME",
    "SCHEMA_VERSION",
    "SAFETY_FLAGS",
    "SOURCE_NAME",
    "STRICT_CATALOG_FIXTURE_KEYS",
    "STRICT_CATALOG_TOP_LEVEL_KEYS",
    "build_manifest",
    "build_strict_catalog",
    "canonical_json_bytes",
    "compile_fixture_catalog",
    "load_fixture_provenance_records",
    "parse_utc_timestamp",
    "serialize_utc",
    "sha256_bytes",
    "stream_sha256",
    "strict_catalog_keys",
    "strict_fixture_keys",
]
