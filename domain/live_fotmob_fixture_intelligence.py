"""Legacy live FotMob runtime evidence preservation.

This module deliberately does **not** create canonical Fixture Intelligence.
The operational ``FotmobBypassClient`` uses browser impersonation and therefore
cannot be represented as ATHENA's reviewed transparent FotMob source without
lying about transport provenance.

The only authority granted here is immutable compatibility evidence retention:
exact response bytes, observation time, source URL and hashes are preserved so
later reviewed boundaries can inspect or compare the legacy runtime.  Canonical
Fixture Intelligence must continue through the existing reviewed FotMob source
chain (data-matches capture and reviewed match-details replay/admission).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import parse_qs, urlsplit


SCHEMA_VERSION = 2
DATASET_NAME = "athena-live-fotmob-runtime-evidence-v2"
EVIDENCE_ROOT = Path(".cache/athena-runtime/fotmob-live-evidence")
RAW_FILENAME = "response.json"
MANIFEST_FILENAME = "manifest.json"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
CANONICAL_ISSUER_STATUS = (
    "BLOCKED_REVIEWED_TRANSPARENT_FOTMOB_SOURCE_REPLAY_REQUIRED"
)
_SHA = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_FIXTURE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", re.ASCII)
_DATE = re.compile(r"^[0-9]{8}$", re.ASCII)


class LiveFotMobFixtureIntelligenceError(ValueError):
    """Raised when legacy runtime evidence or authority boundaries fail closed."""


def _utc(value: Any, label: str) -> dt.datetime:
    if (
        not isinstance(value, dt.datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise LiveFotMobFixtureIntelligenceError(
            f"{label} must be timezone-aware datetime"
        )
    return value.astimezone(dt.timezone.utc)


def _fixture(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or (match := _FIXTURE.fullmatch(value)) is None:
        raise LiveFotMobFixtureIntelligenceError(
            "fixture_identifier must be FOTMOB:<positive id>"
        )
    return value, match.group(1)


def _json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "manifest serialization failed"
        ) from exc


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "raw FotMob evidence is not UTF-8 JSON"
        ) from exc
    if type(value) is not dict:
        raise LiveFotMobFixtureIntelligenceError(
            "raw FotMob evidence root must be an object"
        )
    return value


def _source_identity(
    kind: str,
    source_reference: Any,
    fixture_identifier: str | None,
) -> tuple[str | None, str]:
    if not isinstance(source_reference, str) or source_reference != source_reference.strip():
        raise LiveFotMobFixtureIntelligenceError(
            "source_reference must be an exact FotMob URL"
        )
    parsed = urlsplit(source_reference)
    if parsed.scheme != "https" or parsed.netloc != "www.fotmob.com" or parsed.fragment:
        raise LiveFotMobFixtureIntelligenceError(
            "source_reference must be an exact https://www.fotmob.com endpoint"
        )
    try:
        query = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "source_reference query is invalid"
        ) from exc

    if kind == "FIXTURE_LIST":
        if fixture_identifier is not None:
            raise LiveFotMobFixtureIntelligenceError(
                "fixture-list evidence belongs to the HTTP response, not one fixture"
            )
        if parsed.path != "/api/data/matches" or set(query) != {"date"}:
            raise LiveFotMobFixtureIntelligenceError(
                "fixture-list source_reference must be exact /api/data/matches?date=YYYYMMDD"
            )
        dates = query["date"]
        if len(dates) != 1 or _DATE.fullmatch(dates[0]) is None:
            raise LiveFotMobFixtureIntelligenceError(
                "fixture-list source date must be canonical YYYYMMDD"
            )
        return None, dates[0]

    if kind == "MATCH_DETAILS":
        fixture, source_id = _fixture(fixture_identifier)
        if parsed.path != "/api/data/matchDetails" or set(query) != {"matchId"}:
            raise LiveFotMobFixtureIntelligenceError(
                "match-details source_reference must be exact /api/data/matchDetails?matchId=<id>"
            )
        match_ids = query["matchId"]
        if len(match_ids) != 1 or match_ids[0] != source_id:
            raise LiveFotMobFixtureIntelligenceError(
                "match-details source matchId must equal fixture_identifier"
            )
        return fixture, source_id

    raise LiveFotMobFixtureIntelligenceError(
        "unsupported live FotMob evidence kind"
    )


def _canonical_repository_root(repository_root: Path) -> Path:
    try:
        root = Path(repository_root)
    except (TypeError, ValueError) as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "repository_root is invalid"
        ) from exc
    if root.is_symlink() or not root.is_dir():
        raise LiveFotMobFixtureIntelligenceError(
            "repository_root must be an existing non-symlink directory"
        )
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "repository_root cannot be resolved"
        ) from exc


def _ensure_evidence_root(repository_root: Path) -> Path:
    root = _canonical_repository_root(repository_root)
    current = root
    for part in EVIDENCE_ROOT.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise LiveFotMobFixtureIntelligenceError(
                    "live evidence root contains a forbidden symlink/non-directory"
                )
            continue
        try:
            current.mkdir()
        except OSError as exc:
            raise LiveFotMobFixtureIntelligenceError(
                "live evidence root creation failed"
            ) from exc
    return current


def _validate_receipt_directory(value: Any) -> Path:
    if not isinstance(value, Path) or value.is_absolute():
        raise LiveFotMobFixtureIntelligenceError(
            "evidence_directory must be a relative Path"
        )
    if ".." in value.parts or "." in value.parts:
        raise LiveFotMobFixtureIntelligenceError(
            "evidence_directory must not contain traversal"
        )
    root_parts = EVIDENCE_ROOT.parts
    if (
        len(value.parts) != len(root_parts) + 1
        or value.parts[: len(root_parts)] != root_parts
        or not value.parts[-1]
    ):
        raise LiveFotMobFixtureIntelligenceError(
            "evidence_directory must be one capture beneath the fixed live evidence root"
        )
    return value


def _reject_symlink_components(repository_root: Path, relative: Path) -> Path:
    root = _canonical_repository_root(repository_root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise LiveFotMobFixtureIntelligenceError(
                "live evidence path contains a forbidden symlink"
            )
    try:
        resolved = current.resolve(strict=True)
        expected_root = (root / EVIDENCE_ROOT).resolve(strict=True)
        resolved.relative_to(expected_root)
    except (OSError, ValueError) as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence path escaped the fixed root"
        ) from exc
    return current


def _read_regular_file(path: Path, label: str) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise LiveFotMobFixtureIntelligenceError(
            f"{label} is unavailable"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise LiveFotMobFixtureIntelligenceError(
            f"{label} must be a regular non-symlink file"
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise LiveFotMobFixtureIntelligenceError(
            f"{label} is unavailable"
        ) from exc


def _sync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence directory durability failed"
        ) from exc


@dataclasses.dataclass(frozen=True)
class LiveFotMobEvidenceReceipt:
    """Immutable pointer to one legacy browser-impersonated HTTP response.

    This receipt is compatibility evidence only.  It is intentionally not an
    ATHENA reviewed source-capture object and grants no Fixture Intelligence
    authority.
    """

    kind: str
    fixture_identifier: str | None
    source_reference: str
    observed_at: dt.datetime
    evidence_directory: Path
    evidence_file_path: str
    evidence_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        fixture, _ = _source_identity(
            self.kind,
            self.source_reference,
            self.fixture_identifier,
        )
        object.__setattr__(self, "fixture_identifier", fixture)
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        object.__setattr__(
            self,
            "evidence_directory",
            _validate_receipt_directory(self.evidence_directory),
        )
        if self.evidence_file_path != RAW_FILENAME:
            raise LiveFotMobFixtureIntelligenceError(
                "evidence_file_path must be response.json"
            )
        for value in (self.evidence_sha256, self.manifest_sha256):
            if not isinstance(value, str) or _SHA.fullmatch(value) is None:
                raise LiveFotMobFixtureIntelligenceError(
                    "evidence identities must be SHA-256"
                )


def persist_live_fotmob_evidence(
    *,
    kind: str,
    fixture_identifier: str | None,
    source_reference: str,
    observed_at: dt.datetime,
    raw_bytes: bytes,
    repository_root: Path,
    output_root: Path = EVIDENCE_ROOT,
) -> LiveFotMobEvidenceReceipt:
    """Preserve one exact legacy response before compatibility normalization.

    This does not qualify the source.  In particular, the resulting manifest
    records browser impersonation and keeps all canonical/downstream authority
    false.
    """

    fixture, source_token = _source_identity(kind, source_reference, fixture_identifier)
    observed = _utc(observed_at, "observed_at")
    if type(raw_bytes) is not bytes or not raw_bytes:
        raise LiveFotMobFixtureIntelligenceError(
            "raw_bytes must be exact non-empty bytes"
        )
    if len(raw_bytes) > MAX_RESPONSE_BYTES:
        raise LiveFotMobFixtureIntelligenceError(
            "raw FotMob evidence exceeds the 8 MiB compatibility capture limit"
        )
    _strict_json(raw_bytes)
    if output_root != EVIDENCE_ROOT:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence root must be the fixed repository-local root"
        )

    root = _ensure_evidence_root(repository_root)
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    observed_text = observed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    kind_token = "fixture-list" if kind == "FIXTURE_LIST" else "match-details"
    capture_name = (
        f"{kind_token}--{source_token}--"
        f"{observed.strftime('%Y%m%dT%H%M%S%fZ')}--{raw_sha}"
    )
    relative = EVIDENCE_ROOT / capture_name
    directory = root / capture_name
    if directory.exists() or directory.is_symlink():
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence capture already exists"
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "kind": kind,
        "fixture_identifier": fixture,
        "source_reference": source_reference,
        "observed_at": observed_text,
        "raw_file_name": RAW_FILENAME,
        "raw_sha256": raw_sha,
        "raw_size": len(raw_bytes),
        "network_acquisition_performed": True,
        "browser_impersonation_performed": True,
        "reviewed_transparent_capture": False,
        "canonical_fixture_intelligence_authorized": False,
        "model_feature_authorized": False,
        "probability_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "bet_authorized": False,
    }
    manifest_bytes = _json_bytes(manifest)
    created = False
    try:
        directory.mkdir(mode=0o700)
        created = True
        for name, content in (
            (RAW_FILENAME, raw_bytes),
            (MANIFEST_FILENAME, manifest_bytes),
        ):
            path = directory / name
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        _sync_directory(directory)
        _sync_directory(root)
    except Exception as exc:
        if created:
            for name in (RAW_FILENAME, MANIFEST_FILENAME):
                path = directory / name
                try:
                    if path.exists() and not path.is_symlink():
                        path.unlink()
                except OSError:
                    pass
            try:
                directory.rmdir()
            except OSError:
                pass
        if isinstance(exc, LiveFotMobFixtureIntelligenceError):
            raise
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence publication failed"
        ) from exc

    return LiveFotMobEvidenceReceipt(
        kind=kind,
        fixture_identifier=fixture,
        source_reference=source_reference,
        observed_at=observed,
        evidence_directory=relative,
        evidence_file_path=RAW_FILENAME,
        evidence_sha256=raw_sha,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def replay_live_fotmob_evidence(
    receipt: LiveFotMobEvidenceReceipt,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Verify and replay one legacy compatibility capture.

    Successful replay proves only byte/path/manifest integrity.  It does not
    upgrade the source to reviewed Fixture Intelligence authority.
    """

    if type(receipt) is not LiveFotMobEvidenceReceipt:
        raise LiveFotMobFixtureIntelligenceError(
            "receipt must be exact LiveFotMobEvidenceReceipt"
        )
    try:
        receipt = dataclasses.replace(receipt)
    except (TypeError, ValueError, LiveFotMobFixtureIntelligenceError) as exc:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence receipt failed exact revalidation"
        ) from exc

    directory = _reject_symlink_components(
        repository_root,
        receipt.evidence_directory,
    )
    raw = _read_regular_file(directory / RAW_FILENAME, "live evidence response.json")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise LiveFotMobFixtureIntelligenceError(
            "raw FotMob evidence exceeds the 8 MiB compatibility capture limit"
        )
    manifest_bytes = _read_regular_file(
        directory / MANIFEST_FILENAME,
        "live evidence manifest.json",
    )
    if hashlib.sha256(raw).hexdigest() != receipt.evidence_sha256:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence raw SHA-256 mismatch"
        )
    if hashlib.sha256(manifest_bytes).hexdigest() != receipt.manifest_sha256:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence manifest SHA-256 mismatch"
        )
    manifest = _strict_json(manifest_bytes)
    if _json_bytes(manifest) != manifest_bytes:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence manifest is not canonical"
        )

    required = {
        "schema_version",
        "dataset_name",
        "kind",
        "fixture_identifier",
        "source_reference",
        "observed_at",
        "raw_file_name",
        "raw_sha256",
        "raw_size",
        "network_acquisition_performed",
        "browser_impersonation_performed",
        "reviewed_transparent_capture",
        "canonical_fixture_intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
    if (
        set(manifest) != required
        or manifest["schema_version"] != SCHEMA_VERSION
        or manifest["dataset_name"] != DATASET_NAME
    ):
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence manifest contract mismatch"
        )
    if manifest["network_acquisition_performed"] is not True:
        raise LiveFotMobFixtureIntelligenceError(
            "legacy runtime evidence must record actual network acquisition"
        )
    if manifest["browser_impersonation_performed"] is not True:
        raise LiveFotMobFixtureIntelligenceError(
            "legacy runtime evidence must preserve browser-impersonation provenance"
        )
    for key in (
        "reviewed_transparent_capture",
        "canonical_fixture_intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    ):
        if manifest[key] is not False:
            raise LiveFotMobFixtureIntelligenceError(
                "live evidence attempted authority upgrade"
            )

    if (
        manifest["kind"],
        manifest["fixture_identifier"],
        manifest["source_reference"],
        manifest["raw_file_name"],
        manifest["raw_sha256"],
        manifest["raw_size"],
    ) != (
        receipt.kind,
        receipt.fixture_identifier,
        receipt.source_reference,
        RAW_FILENAME,
        receipt.evidence_sha256,
        len(raw),
    ):
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence receipt/manifest identity mismatch"
        )
    observed = _utc(
        dt.datetime.fromisoformat(manifest["observed_at"].replace("Z", "+00:00")),
        "manifest observed_at",
    )
    if observed != receipt.observed_at:
        raise LiveFotMobFixtureIntelligenceError(
            "live evidence observation time mismatch"
        )
    _source_identity(
        receipt.kind,
        receipt.source_reference,
        receipt.fixture_identifier,
    )
    return _strict_json(raw)


def issue_live_fotmob_fixture_intelligence(
    *,
    fixture_evidence: LiveFotMobEvidenceReceipt,
    match_details_evidence: LiveFotMobEvidenceReceipt,
    repository_root: Path,
):
    """Fail closed at the reviewed FotMob source-authority boundary.

    The function remains as an explicit guard for callers introduced by the
    initial #242 draft.  It verifies both legacy captures, then refuses to mint
    canonical facts.  The reviewed transparent data-matches + match-details
    replay/admission chain must supply the canonical snapshot instead.
    """

    if fixture_evidence.kind != "FIXTURE_LIST":
        raise LiveFotMobFixtureIntelligenceError(
            "fixture_evidence must be FIXTURE_LIST compatibility evidence"
        )
    if match_details_evidence.kind != "MATCH_DETAILS":
        raise LiveFotMobFixtureIntelligenceError(
            "match_details_evidence must be MATCH_DETAILS compatibility evidence"
        )
    replay_live_fotmob_evidence(
        fixture_evidence,
        repository_root=repository_root,
    )
    replay_live_fotmob_evidence(
        match_details_evidence,
        repository_root=repository_root,
    )
    raise LiveFotMobFixtureIntelligenceError(
        f"{CANONICAL_ISSUER_STATUS}: legacy browser-impersonated runtime evidence "
        "cannot issue canonical Fixture Intelligence; use ATHENA's reviewed transparent "
        "data-matches capture and reviewed match-details source-replay/admission chain"
    )


__all__ = [
    "CANONICAL_ISSUER_STATUS",
    "EVIDENCE_ROOT",
    "MAX_RESPONSE_BYTES",
    "LiveFotMobEvidenceReceipt",
    "LiveFotMobFixtureIntelligenceError",
    "issue_live_fotmob_fixture_intelligence",
    "persist_live_fotmob_evidence",
    "replay_live_fotmob_evidence",
]
