"""Source-replayed durable artifacts for reviewed FotMob Fixture Catalog admission.

This boundary does not create fixture review or admission authority by itself.
It accepts one explicit catalog-admission review decision, combines it with an
already source-replayed reviewed catalog compilation, and stores the exact
canonical ReviewedFixtureCatalogAdmission bytes plus the exact canonical review
decision bytes.  Verification always requires the semantic sources again.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_catalog import (
    FixtureCatalogResult,
    parse_utc_timestamp,
    serialize_utc,
)
from domain.fotmob_fixture_catalog_handoff import (
    FotMobFixtureCatalogHandoff,
    sha256_fotmob_fixture_catalog_handoff,
)
from domain.reviewed_fixture_catalog_admission import (
    REVIEWED_SOURCE_CAPABILITY,
    ReviewedFixtureCatalogAdmission,
    ReviewedFixtureCatalogAdmissionDecision,
    ReviewedFixtureCatalogAdmissionDisposition,
    ReviewedFixtureCatalogAdmissionError,
    build_reviewed_fixture_catalog_admission,
    canonical_reviewed_fixture_catalog_admission_bytes,
    sha256_reviewed_fixture_catalog_admission,
    sha256_reviewed_source_capability,
)
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-reviewed-fixture-catalog-admission-source-replay-v1"
DECISION_DATASET_NAME = (
    "athena-reviewed-fixture-catalog-admission-source-replay-decision-v1"
)
STATUS = "SOURCE_REPLAYED_REVIEWED_FIXTURE_CATALOG_ADMISSION"
ADMISSION_FILENAME = "admission.json"
DECISION_FILENAME = "admission-decision.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/reviewed-fixture-catalog-admission-source-replay"
)
MAX_DECISION_BYTES = 256 * 1024
MAX_ADMISSION_BYTES = 2 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_DECISION_KEYS = frozenset(
    {
        "schema_version",
        "dataset_name",
        "candidate_bundle_sha256",
        "review_bundle_sha256",
        "handoff_sha256",
        "catalog_sha256",
        "manifest_sha256",
        "source_capability",
        "source_capability_sha256",
        "disposition",
        "reviewed_at",
        "reviewer_reference",
        "notes",
    }
)
_EXPECTED_DIRECTORY_FILES = tuple(sorted((ADMISSION_FILENAME, DECISION_FILENAME)))
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "automatic_review_authorized",
        "source_qualification_authorized",
        "global_identity_resolution_authorized",
        "fixture_intelligence_bootstrap_authorized",
        "intelligence_fact_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class ReviewedFixtureCatalogAdmissionSourceReplayError(ValueError):
    """Raised when source-replayed catalog admission cannot be proven."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _strict_string(
    value: Any,
    label: str,
    *,
    non_empty: bool = True,
) -> str:
    if type(value) is not str:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"{label} must be an exact string"
        )
    if non_empty and not value:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"{label} must be non-empty"
        )
    if value != value.strip():
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"{label} must not contain surrounding whitespace"
        )
    return value


def _utc(value: Any, label: str) -> dt.datetime:
    try:
        parsed = parse_utc_timestamp(value, label)
    except Exception as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc
    if serialize_utc(parsed) != value:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"{label} must use canonical UTC serialization"
        )
    return parsed


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReviewedFixtureCatalogAdmissionSourceReplayError(
        f"invalid JSON constant: {value}"
    )


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"{label} must be valid UTF-8"
        ) from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ReviewedFixtureCatalogAdmissionSourceReplayError:
        raise
    except json.JSONDecodeError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"{label} is not valid JSON"
        ) from exc


@dataclasses.dataclass(frozen=True)
class ReviewedFixtureCatalogAdmissionReplayDecision:
    """Exact human review decision anchored to one replayed catalog state."""

    decision: ReviewedFixtureCatalogAdmissionDecision
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.decision) is not ReviewedFixtureCatalogAdmissionDecision:
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                "decision must be exact ReviewedFixtureCatalogAdmissionDecision"
            )
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DECISION_DATASET_NAME,
            **self.decision.to_dict(),
        }


def canonical_replay_decision_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedFixtureCatalogAdmissionReplayDecision:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision type mismatch"
        )
    try:
        payload = (
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
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision serialization failed"
        ) from exc
    if not payload or len(payload) > MAX_DECISION_BYTES:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision size is invalid"
        )
    return payload


def replay_decision_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_replay_decision_bytes(value)).hexdigest()


def parse_replay_decision_bytes(raw: Any) -> ReviewedFixtureCatalogAdmissionReplayDecision:
    if type(raw) is not bytes or not raw or len(raw) > MAX_DECISION_BYTES:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision must be bounded non-empty exact bytes"
        )
    payload = _strict_json(raw, "replay decision")
    if type(payload) is not dict or set(payload) != _DECISION_KEYS:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision keys mismatch"
        )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision schema_version mismatch"
        )
    if payload["dataset_name"] != DECISION_DATASET_NAME:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision dataset_name mismatch"
        )
    try:
        disposition = ReviewedFixtureCatalogAdmissionDisposition(payload["disposition"])
    except (TypeError, ValueError) as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision disposition is invalid"
        ) from exc
    try:
        decision = ReviewedFixtureCatalogAdmissionDecision(
            candidate_bundle_sha256=_strict_sha256(
                payload["candidate_bundle_sha256"], "candidate_bundle_sha256"
            ),
            review_bundle_sha256=_strict_sha256(
                payload["review_bundle_sha256"], "review_bundle_sha256"
            ),
            handoff_sha256=_strict_sha256(payload["handoff_sha256"], "handoff_sha256"),
            catalog_sha256=_strict_sha256(payload["catalog_sha256"], "catalog_sha256"),
            manifest_sha256=_strict_sha256(payload["manifest_sha256"], "manifest_sha256"),
            source_capability=_strict_string(
                payload["source_capability"], "source_capability"
            ),
            source_capability_sha256=_strict_sha256(
                payload["source_capability_sha256"], "source_capability_sha256"
            ),
            disposition=disposition,
            reviewed_at=_utc(payload["reviewed_at"], "reviewed_at"),
            reviewer_reference=_strict_string(
                payload["reviewer_reference"], "reviewer_reference"
            ),
            notes=_strict_string(payload["notes"], "notes", non_empty=False),
        )
    except ReviewedFixtureCatalogAdmissionError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc
    replay = ReviewedFixtureCatalogAdmissionReplayDecision(
        decision=decision,
        safety=_default_safety(),
    )
    if raw != canonical_replay_decision_bytes(replay):
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay decision bytes are not canonical"
        )
    return replay


def build_replay_decision(
    *,
    handoff: Any,
    fixture_catalog_result: Any,
    disposition: Any,
    reviewed_at: Any,
    reviewer_reference: str,
    notes: str = "",
) -> ReviewedFixtureCatalogAdmissionReplayDecision:
    if type(handoff) is not FotMobFixtureCatalogHandoff:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "handoff must be exact FotMobFixtureCatalogHandoff"
        )
    if type(fixture_catalog_result) is not FixtureCatalogResult:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "fixture_catalog_result must be exact FixtureCatalogResult"
        )
    if not isinstance(disposition, ReviewedFixtureCatalogAdmissionDisposition):
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "disposition must be ReviewedFixtureCatalogAdmissionDisposition"
        )
    try:
        decision = ReviewedFixtureCatalogAdmissionDecision(
            candidate_bundle_sha256=handoff.candidate_bundle_sha256,
            review_bundle_sha256=handoff.review_bundle_sha256,
            handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
            catalog_sha256=hashlib.sha256(fixture_catalog_result.catalog_bytes).hexdigest(),
            manifest_sha256=hashlib.sha256(fixture_catalog_result.manifest_bytes).hexdigest(),
            source_capability=REVIEWED_SOURCE_CAPABILITY,
            source_capability_sha256=sha256_reviewed_source_capability(),
            disposition=disposition,
            reviewed_at=reviewed_at,
            reviewer_reference=reviewer_reference,
            notes=notes,
        )
    except ReviewedFixtureCatalogAdmissionError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc
    return ReviewedFixtureCatalogAdmissionReplayDecision(
        decision=decision,
        safety=_default_safety(),
    )


def build_source_replayed_admission(
    *,
    handoff: Any,
    fixture_catalog_result: Any,
    replay_decision: Any,
) -> ReviewedFixtureCatalogAdmission:
    if type(replay_decision) is not ReviewedFixtureCatalogAdmissionReplayDecision:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay_decision type mismatch"
        )
    try:
        admission = build_reviewed_fixture_catalog_admission(
            handoff,
            fixture_catalog_result,
            replay_decision.decision,
        )
    except ReviewedFixtureCatalogAdmissionError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc
    return admission


def _validate_output_root(
    output_root: Any,
    *,
    repository_root: Path,
) -> tuple[Path, Path]:
    try:
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "repository_root cannot be resolved"
        ) from exc
    if not repository.is_dir():
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "repository_root must be a directory"
        )
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        supplied = Path(output_root)
    except (TypeError, ValueError) as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "output_root is invalid"
        ) from exc
    if ".." in supplied.parts:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "output_root must not contain traversal"
        )
    supplied_abs = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(supplied_abs, "catalog admission replay root")
    except SportyBetLiteCaptureError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc
    if supplied_abs.resolve(strict=False) != expected.resolve(strict=False):
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "output_root must be the reviewed exact source-replay root"
        )
    return repository, expected


def _normalize_directory(
    value: Any,
    *,
    repository: Path,
    root: Path,
) -> Path:
    try:
        supplied = Path(value)
    except (TypeError, ValueError) as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "admission directory is invalid"
        ) from exc
    if ".." in supplied.parts:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "admission directory must not contain traversal"
        )
    directory = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(directory, "catalog admission replay directory")
        resolved_root = root.resolve(strict=True)
        resolved = directory.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "admission directory escapes or cannot resolve under reviewed root"
        ) from exc
    if directory.is_symlink() or not directory.is_dir():
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "admission directory must be a non-symlink directory"
        )
    return directory


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            f"could not durably write {path.name}"
        ) from exc


def _read_directory_payloads(directory: Path) -> tuple[bytes, bytes]:
    try:
        names = tuple(sorted(item.name for item in directory.iterdir()))
    except OSError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "admission directory cannot be enumerated"
        ) from exc
    if names != _EXPECTED_DIRECTORY_FILES:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "admission directory contents mismatch"
        )
    try:
        admission_raw = _read_regular(
            directory / ADMISSION_FILENAME,
            maximum=MAX_ADMISSION_BYTES,
            label="source-replayed catalog admission",
        )
        decision_raw = _read_regular(
            directory / DECISION_FILENAME,
            maximum=MAX_DECISION_BYTES,
            label="source-replayed catalog admission decision",
        )
    except SportyBetLiteCaptureError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc
    return admission_raw, decision_raw


def _cleanup_partial(directory: Path, root: Path) -> None:
    try:
        if not directory.exists():
            return
        if directory.is_symlink() or not directory.is_dir():
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                "partial admission path changed type during cleanup"
            )
        entries = list(directory.iterdir())
        if any(item.name not in _EXPECTED_DIRECTORY_FILES for item in entries):
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                "partial admission directory contains an unexpected entry"
            )
        for item in entries:
            if item.is_symlink() or not item.is_file():
                raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                    "partial admission directory contains a non-regular entry"
                )
            item.unlink()
        _sync_directory(directory)
        directory.rmdir()
        _sync_directory(root)
    except ReviewedFixtureCatalogAdmissionSourceReplayError:
        raise
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "could not clean partial catalog admission replay artifact"
        ) from exc


def verify_source_replayed_admission_directory(
    admission_directory: Any,
    *,
    handoff: Any,
    fixture_catalog_result: Any,
    repository_root: Path,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> ReviewedFixtureCatalogAdmission:
    repository, root = _validate_output_root(
        output_root,
        repository_root=repository_root,
    )
    directory = _normalize_directory(
        admission_directory,
        repository=repository,
        root=root,
    )
    admission_raw, decision_raw = _read_directory_payloads(directory)
    replay_decision = parse_replay_decision_bytes(decision_raw)
    admission = build_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=fixture_catalog_result,
        replay_decision=replay_decision,
    )
    expected_admission = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    if admission_raw != expected_admission:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "stored admission is stale, tampered, or not the exact source-replayed derivative"
        )
    expected_id = sha256_reviewed_fixture_catalog_admission(admission)[:24]
    if directory.name != expected_id:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "admission directory identity mismatch"
        )
    return admission


def store_source_replayed_admission(
    *,
    handoff: Any,
    fixture_catalog_result: Any,
    replay_decision: Any,
    repository_root: Path,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> tuple[Path, ReviewedFixtureCatalogAdmission]:
    if type(replay_decision) is not ReviewedFixtureCatalogAdmissionReplayDecision:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "replay_decision type mismatch"
        )
    admission = build_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=fixture_catalog_result,
        replay_decision=replay_decision,
    )
    admission_raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    if not admission_raw or len(admission_raw) > MAX_ADMISSION_BYTES:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(
            "canonical admission size is invalid"
        )
    decision_raw = canonical_replay_decision_bytes(replay_decision)
    repository, root = _validate_output_root(
        output_root,
        repository_root=repository_root,
    )
    try:
        _ensure_directory_tree_durable(root, boundary=repository)
    except SportyBetLiteCaptureError as exc:
        raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc

    directory = root / sha256_reviewed_fixture_catalog_admission(admission)[:24]
    if directory.exists():
        verified = verify_source_replayed_admission_directory(
            directory,
            handoff=handoff,
            fixture_catalog_result=fixture_catalog_result,
            repository_root=repository,
            output_root=root,
        )
        existing_admission, existing_decision = _read_directory_payloads(directory)
        if existing_admission != admission_raw or existing_decision != decision_raw:
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                "source-replayed admission identity collision"
            )
        return directory, verified

    created = False
    try:
        directory.mkdir(exist_ok=False)
        created = True
        _sync_directory(root)
        _sync_directory(directory)
        _write_exclusive(directory / ADMISSION_FILENAME, admission_raw)
        _write_exclusive(directory / DECISION_FILENAME, decision_raw)
        verified = verify_source_replayed_admission_directory(
            directory,
            handoff=handoff,
            fixture_catalog_result=fixture_catalog_result,
            repository_root=repository,
            output_root=root,
        )
        _sync_directory(directory)
        _sync_directory(root)
        return directory, verified
    except Exception as exc:
        if created:
            try:
                _cleanup_partial(directory, root)
            except Exception as cleanup_exc:
                raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                    "catalog admission replay write failed and cleanup also failed"
                ) from cleanup_exc
        if isinstance(exc, ReviewedFixtureCatalogAdmissionSourceReplayError):
            raise
        if isinstance(exc, ReviewedFixtureCatalogAdmissionError):
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(str(exc)) from exc
        if isinstance(exc, (OSError, SportyBetLiteCaptureError)):
            raise ReviewedFixtureCatalogAdmissionSourceReplayError(
                "could not durably store source-replayed catalog admission"
            ) from exc
        raise


__all__ = [
    "ADMISSION_FILENAME",
    "ALLOWED_OUTPUT_RELATIVE",
    "DATASET_NAME",
    "DECISION_DATASET_NAME",
    "DECISION_FILENAME",
    "MAX_ADMISSION_BYTES",
    "MAX_DECISION_BYTES",
    "ReviewedFixtureCatalogAdmissionReplayDecision",
    "ReviewedFixtureCatalogAdmissionSourceReplayError",
    "SCHEMA_VERSION",
    "STATUS",
    "build_replay_decision",
    "build_source_replayed_admission",
    "canonical_replay_decision_bytes",
    "parse_replay_decision_bytes",
    "replay_decision_sha256",
    "store_source_replayed_admission",
    "verify_source_replayed_admission_directory",
]
