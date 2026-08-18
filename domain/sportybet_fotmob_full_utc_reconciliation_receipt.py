"""Durable source-aware receipts for SportyBet/FotMob full-UTC reconciliation.

The receipt boundary executes PR #163's exact deterministic reconciliation from
its complete preserved source bundle and stores only the canonical result bytes.
There is deliberately no storage-only verifier: every verification rebuilds the
result from the original SportyBet/Terms/Sportradar/FotMob sources first.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from pathlib import Path
from typing import Any

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain.sportybet_lite_source_capture import (
    SportyBetLiteCaptureError,
    _ensure_directory_tree_durable,
    _read_regular,
    _reject_symlink_components,
    _sync_directory,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-fotmob-full-utc-reconciliation-receipt-v1"
STATUS = "SOURCE_REPLAYED_FULL_UTC_RECONCILIATION_RECEIPT"
RECONCILIATION_FILENAME = "reconciliation.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-fotmob-full-utc-reconciliation-receipts"
)
MAX_RECEIPT_BYTES = 512 * 1024


class SportyBetFotMobFullUtcReconciliationReceiptError(ValueError):
    """Raised when a reconciliation receipt cannot be executed or verified."""


@dataclasses.dataclass(frozen=True)
class FullUtcReconciliationSourceBundle:
    """Complete in-memory source chain required to execute PR #163 exactly."""

    kickoff_promotion: Any
    event_time_basis: Any
    event_manifest: Any
    event_inventory: Any
    event_raw_html: bytes
    terms_qualification: Any
    terms_raw_html: bytes
    event_bridge: Any
    sportradar_evidence: Any
    sportradar_raw_response: bytes
    fotmob_admission_value: Any
    fotmob_captures: tuple[Any, ...]

    def __post_init__(self) -> None:
        for label in (
            "event_raw_html",
            "terms_raw_html",
            "sportradar_raw_response",
        ):
            if type(getattr(self, label)) is not bytes:
                raise SportyBetFotMobFullUtcReconciliationReceiptError(
                    f"{label} must be exact bytes"
                )
        if type(self.fotmob_captures) is not tuple or not self.fotmob_captures:
            raise SportyBetFotMobFullUtcReconciliationReceiptError(
                "fotmob_captures must be a non-empty exact tuple"
            )

    def build_kwargs(self) -> dict[str, Any]:
        return {
            "kickoff_promotion": self.kickoff_promotion,
            "event_time_basis": self.event_time_basis,
            "event_manifest": self.event_manifest,
            "event_inventory": self.event_inventory,
            "event_raw_html": self.event_raw_html,
            "terms_qualification": self.terms_qualification,
            "terms_raw_html": self.terms_raw_html,
            "event_bridge": self.event_bridge,
            "sportradar_evidence": self.sportradar_evidence,
            "sportradar_raw_response": self.sportradar_raw_response,
            "fotmob_admission_value": self.fotmob_admission_value,
            "fotmob_captures": self.fotmob_captures,
        }


def _execute_exact_reconciliation(
    source_bundle: Any,
) -> tuple[reconciliation.SportyBetFotMobFullUtcReconciliation, bytes]:
    if type(source_bundle) is not FullUtcReconciliationSourceBundle:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "source_bundle must be exact FullUtcReconciliationSourceBundle"
        )
    try:
        rebuilt = reconciliation.build_full_utc_reconciliation(
            **source_bundle.build_kwargs()
        )
        payload = reconciliation.canonical_reconciliation_bytes(rebuilt)
    except reconciliation.SportyBetFotMobFullUtcReconciliationError as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(str(exc)) from exc
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "canonical reconciliation receipt size is invalid"
        )
    return rebuilt, payload


def receipt_sha256_from_bytes(payload: Any) -> str:
    if type(payload) is not bytes or not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt payload must be bounded non-empty exact bytes"
        )
    return hashlib.sha256(payload).hexdigest()


def receipt_identifier_from_bytes(payload: Any) -> str:
    return receipt_sha256_from_bytes(payload)[:24]


def _validate_output_root(
    output_root: Any,
    *,
    repository_root: Path,
) -> tuple[Path, Path]:
    try:
        repository = Path(repository_root).resolve(strict=True)
    except (TypeError, ValueError, OSError) as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "repository_root cannot be resolved"
        ) from exc
    if not repository.is_dir():
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "repository_root must be a directory"
        )
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        supplied = Path(output_root)
    except (TypeError, ValueError) as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "output_root is invalid"
        ) from exc
    if ".." in supplied.parts:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "output_root must not contain traversal"
        )
    supplied_abs = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(supplied_abs, "reconciliation receipt root")
    except SportyBetLiteCaptureError as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(str(exc)) from exc
    if supplied_abs.resolve(strict=False) != expected.resolve(strict=False):
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "output_root must be the reviewed exact reconciliation receipt root"
        )
    return repository, expected


def _normalize_receipt_directory(
    receipt_directory: Any,
    *,
    repository: Path,
    root: Path,
) -> Path:
    try:
        supplied = Path(receipt_directory)
    except (TypeError, ValueError) as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt_directory is invalid"
        ) from exc
    if ".." in supplied.parts:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt_directory must not contain traversal"
        )
    directory = supplied if supplied.is_absolute() else repository / supplied
    try:
        _reject_symlink_components(directory, "reconciliation receipt directory")
        resolved_root = root.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        resolved_directory.relative_to(resolved_root)
    except (SportyBetLiteCaptureError, OSError, ValueError) as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt_directory escapes or cannot resolve under reviewed root"
        ) from exc
    if directory.is_symlink() or not directory.is_dir():
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt_directory must be a non-symlink directory"
        )
    return directory


def _read_stored_payload(directory: Path) -> bytes:
    try:
        names = tuple(sorted(item.name for item in directory.iterdir()))
    except OSError as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt_directory cannot be enumerated"
        ) from exc
    if names != (RECONCILIATION_FILENAME,):
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt_directory contents mismatch"
        )
    try:
        return _read_regular(
            directory / RECONCILIATION_FILENAME,
            maximum=MAX_RECEIPT_BYTES,
            label="full-UTC reconciliation receipt",
        )
    except SportyBetLiteCaptureError as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(str(exc)) from exc


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            f"refusing to overwrite {path.name}"
        ) from exc
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            f"could not durably write {path.name}"
        ) from exc


def _cleanup_partial_directory(directory: Path, root: Path) -> None:
    try:
        if not directory.exists():
            return
        if directory.is_symlink() or not directory.is_dir():
            raise SportyBetFotMobFullUtcReconciliationReceiptError(
                "partial receipt path changed type during cleanup"
            )
        entries = list(directory.iterdir())
        if any(entry.name != RECONCILIATION_FILENAME for entry in entries):
            raise SportyBetFotMobFullUtcReconciliationReceiptError(
                "partial receipt directory contains an unexpected entry"
            )
        for entry in entries:
            if entry.is_symlink() or not entry.is_file():
                raise SportyBetFotMobFullUtcReconciliationReceiptError(
                    "partial receipt directory contains a non-regular entry"
                )
            entry.unlink()
        _sync_directory(directory)
        directory.rmdir()
        _sync_directory(root)
    except SportyBetFotMobFullUtcReconciliationReceiptError:
        raise
    except (OSError, SportyBetLiteCaptureError) as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "could not clean partial reconciliation receipt"
        ) from exc


def verify_reconciliation_receipt_directory(
    receipt_directory: Any,
    *,
    source_bundle: FullUtcReconciliationSourceBundle,
    repository_root: Path,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> reconciliation.SportyBetFotMobFullUtcReconciliation:
    """Rebuild PR #163 from source bytes and require exact stored-byte equality."""

    rebuilt, expected_payload = _execute_exact_reconciliation(source_bundle)
    repository, root = _validate_output_root(
        output_root,
        repository_root=repository_root,
    )
    directory = _normalize_receipt_directory(
        receipt_directory,
        repository=repository,
        root=root,
    )
    expected_identifier = receipt_identifier_from_bytes(expected_payload)
    if directory.name != expected_identifier:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "receipt directory identity does not match source-replayed reconciliation"
        )
    stored = _read_stored_payload(directory)
    if stored != expected_payload:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(
            "stored reconciliation is stale, tampered, or not the exact deterministic derivative of preserved sources"
        )
    return rebuilt


def store_reconciliation_receipt(
    *,
    source_bundle: FullUtcReconciliationSourceBundle,
    repository_root: Path,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
) -> tuple[Path, reconciliation.SportyBetFotMobFullUtcReconciliation]:
    """Execute PR #163 from preserved sources and durably publish its exact result."""

    rebuilt, payload = _execute_exact_reconciliation(source_bundle)
    repository, root = _validate_output_root(
        output_root,
        repository_root=repository_root,
    )
    try:
        _ensure_directory_tree_durable(root, boundary=repository)
    except SportyBetLiteCaptureError as exc:
        raise SportyBetFotMobFullUtcReconciliationReceiptError(str(exc)) from exc

    directory = root / receipt_identifier_from_bytes(payload)
    if directory.exists():
        verified = verify_reconciliation_receipt_directory(
            directory,
            source_bundle=source_bundle,
            repository_root=repository,
            output_root=root,
        )
        return directory, verified

    try:
        directory.mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(directory)
        _write_exclusive(directory / RECONCILIATION_FILENAME, payload)
        verified = verify_reconciliation_receipt_directory(
            directory,
            source_bundle=source_bundle,
            repository_root=repository,
            output_root=root,
        )
        _sync_directory(directory)
        _sync_directory(root)
    except Exception as exc:
        try:
            _cleanup_partial_directory(directory, root)
        except Exception as cleanup_exc:
            raise SportyBetFotMobFullUtcReconciliationReceiptError(
                "reconciliation receipt failed and partial cleanup also failed"
            ) from cleanup_exc
        if isinstance(exc, SportyBetFotMobFullUtcReconciliationReceiptError):
            raise
        if isinstance(exc, (OSError, SportyBetLiteCaptureError)):
            raise SportyBetFotMobFullUtcReconciliationReceiptError(
                "could not durably publish reconciliation receipt"
            ) from exc
        raise
    return directory, verified


__all__ = [
    "ALLOWED_OUTPUT_RELATIVE",
    "DATASET_NAME",
    "FullUtcReconciliationSourceBundle",
    "MAX_RECEIPT_BYTES",
    "RECONCILIATION_FILENAME",
    "SCHEMA_VERSION",
    "STATUS",
    "SportyBetFotMobFullUtcReconciliationReceiptError",
    "receipt_identifier_from_bytes",
    "receipt_sha256_from_bytes",
    "store_reconciliation_receipt",
    "verify_reconciliation_receipt_directory",
]
