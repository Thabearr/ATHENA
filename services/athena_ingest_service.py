"""Bounded Layer-1 FotMob ingest into a replayable source artifact."""

from __future__ import annotations

import os
from pathlib import Path
import math
import time
from typing import Callable

from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    FotMobDataMatchesCaptureError,
    serialize_utc,
    verify_data_matches_capture_directory,
)
from domain.ingest_contracts import (
    AthenaCanonicalStoreUpdate, AthenaIngestContractError, AthenaIngestReceipt,
    AthenaIngestRequest, AthenaIngestSourceRecord, NOT_COMMITTED, READY,
    RECEIPT_POLICY, REPLAY_POLICY, UPDATE_POLICY, canonical_json_bytes,
    receipt_authorities, sha256_bytes, validate_exact_commit_sha,
)
from scripts.capture_fotmob_data_matches import (
    ALLOWED_OUTPUT_RELATIVE,
    fetch_fotmob_data_matches, write_data_matches_capture_directory,
)


ARTIFACT_RELATIVE = Path("artifacts/athena-ingest-workflow")
REQUEST_NAME = "resolved-ingest-request.json"
UPDATE_NAME = "canonical-store-update.json"
RECEIPT_NAME = "ingest-receipt.json"
REPLAY_NAME = "replay-manifest.json"
INGEST_SERVICE_BUDGET_SECONDS = 900


class AthenaIngestServiceError(RuntimeError):
    """The ingest artifact could not be safely produced."""


def _safe_directory(path: Path, repository: Path) -> Path:
    if ".." in path.parts:
        raise AthenaIngestServiceError("artifact path contains traversal")
    absolute = path if path.is_absolute() else repository / path
    if not absolute.is_relative_to(repository):
        raise AthenaIngestServiceError("artifact path escapes repository")
    cursor = repository
    for part in absolute.relative_to(repository).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise AthenaIngestServiceError(f"artifact path contains symlink: {cursor}")
        if cursor.exists() and not cursor.is_dir():
            raise AthenaIngestServiceError(f"artifact path is not directory: {cursor}")
    absolute.mkdir(parents=True, exist_ok=True)
    return absolute


def _write_exact(path: Path, raw: bytes, *, allow_identical: bool = False) -> None:
    if type(raw) is not bytes or path.is_symlink():
        raise AthenaIngestServiceError(f"unsafe output: {path}")
    if path.exists():
        if allow_identical and path.is_file() and path.read_bytes() == raw:
            return
        raise AthenaIngestServiceError(f"refusing to overwrite published artifact: {path}")
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise AthenaIngestServiceError(f"artifact appeared concurrently: {path}") from exc


def _copy_capture(
    capture: Path, *, request_date: str, artifact_root: Path, repository: Path,
) -> Path:
    destination = _safe_directory(
        artifact_root / "sources" / "fotmob" / request_date / capture.name,
        repository,
    )
    for name in ("response.json", "manifest.json"):
        source = capture / name
        if source.is_symlink() or not source.is_file():
            raise AthenaIngestServiceError(f"capture source is unsafe: {source}")
        _write_exact(destination / name, source.read_bytes())
    return destination


def _record_from_capture(
    capture: Path, *, artifact_root: Path, expected_date: str,
) -> AthenaIngestSourceRecord:
    manifest = verify_data_matches_capture_directory(
        capture, allowed_root=artifact_root / "sources" / "fotmob",
    )
    if manifest.request_date != expected_date or manifest.timezone != "UTC" or manifest.ccode3 != "NGA":
        raise AthenaIngestServiceError("copied capture provenance differs from request")
    manifest_raw = (capture / "manifest.json").read_bytes()
    return AthenaIngestSourceRecord(
        provider="fotmob", request_date=expected_date, timezone="UTC", ccode3="NGA",
        observed_at=serialize_utc(manifest.observed_at),
        capture_relative_path=capture.relative_to(artifact_root).as_posix(),
        manifest_sha256=sha256_bytes(manifest_raw), raw_sha256=manifest.raw_sha256,
        raw_size=manifest.raw_size, network_acquisition_performed=True,
    )


def _replay_manifest(
    request: AthenaIngestRequest, update: AthenaCanonicalStoreUpdate,
    receipt: AthenaIngestReceipt,
) -> dict[str, object]:
    return {
        "schema_version": 1, "policy_id": REPLAY_POLICY,
        "request_sha256": request.canonical_sha256,
        "canonical_store_update_sha256": update.canonical_sha256,
        "ingest_receipt_sha256": receipt.canonical_sha256,
        "source_count": len(update.source_records),
        "sources": [
            {
                "raw_relative_path": f"{item.capture_relative_path}/response.json",
                "raw_sha256": item.raw_sha256,
                "manifest_relative_path": f"{item.capture_relative_path}/manifest.json",
                "manifest_sha256": item.manifest_sha256,
            }
            for item in update.source_records
        ],
    }


def _receipt(
    *, exact_commit_sha: str, request_sha256: str, update_sha256: str,
    committed: bool, provider_requests: int, source_count: int,
    failure_code: str | None, stage: str,
) -> AthenaIngestReceipt:
    return AthenaIngestReceipt(
        schema_version=1, policy_id=RECEIPT_POLICY,
        exact_commit_sha=exact_commit_sha,
        status="SUCCESS" if failure_code is None else "FAILED",
        failure_code=failure_code, stage=stage,
        request_sha256=request_sha256,
        canonical_store_update_sha256=update_sha256,
        raw_request_input_sha256=None,
        canonical_store_update_committed=committed,
        provider_request_count=provider_requests, source_count=source_count,
        authorities=receipt_authorities(
            provider_requests=provider_requests, source_count=source_count, committed=committed,
        ),
    )


def execute_ingest_request(
    request: AthenaIngestRequest,
    *,
    repository_root: Path,
    exact_commit_sha: str,
    acquisition_callable: Callable[..., CapturedFotMobDataMatchesResponse] = fetch_fotmob_data_matches,
    monotonic_clock: Callable[[], float] = time.monotonic,
    service_budget_seconds: int | float = INGEST_SERVICE_BUDGET_SECONDS,
) -> AthenaIngestReceipt:
    validate_exact_commit_sha(exact_commit_sha)
    if not callable(monotonic_clock):
        raise AthenaIngestContractError("monotonic_clock must be callable")
    if type(service_budget_seconds) not in (int, float) or not math.isfinite(service_budget_seconds) or service_budget_seconds <= 0:
        raise AthenaIngestContractError("service_budget_seconds must be a positive finite number")
    if not isinstance(request, AthenaIngestRequest):
        raise AthenaIngestContractError("INVALID_REQUEST")
    if request.provider != "fotmob":
        raise AthenaIngestContractError("UNSUPPORTED_PROVIDER")
    repository = Path(repository_root).resolve(strict=True)
    artifact_root = _safe_directory(ARTIFACT_RELATIVE, repository)
    _write_exact(artifact_root / REQUEST_NAME, request.canonical_bytes, allow_identical=True)
    records: list[AthenaIngestSourceRecord] = []
    attempted = 0
    failure: str | None = None
    failure_stage = "SOURCE_ACQUISITION"
    started_at = monotonic_clock()
    if type(started_at) not in (int, float) or not math.isfinite(started_at):
        raise AthenaIngestContractError("monotonic_clock returned an invalid value")
    deadline = started_at + service_budget_seconds

    def over_budget() -> bool:
        now = monotonic_clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise AthenaIngestContractError("monotonic_clock returned an invalid value")
        return now >= deadline

    for date in request.dates:
        failure_stage = "SOURCE_ACQUISITION"
        try:
            if over_budget():
                failure = "TIMEOUT"
                break
        except AthenaIngestContractError:
            failure = "ARTIFACT_PERSISTENCE_FAILED"
            failure_stage = "CANONICAL_UPDATE"
            break
        attempted += 1
        try:
            response = acquisition_callable(request_date=date, timezone="UTC", ccode3="NGA")
            if not isinstance(response, CapturedFotMobDataMatchesResponse) or response.network_acquisition_performed is not True:
                raise FotMobDataMatchesCaptureError("acquisition provenance must be true")
        except Exception:
            failure = "TIMEOUT" if over_budget() else "PROVIDER_ACQUISITION_FAILED"
            break
        if over_budget():
            failure = "TIMEOUT"
            break
        failure_stage = "SOURCE_PERSISTENCE"
        try:
            capture, _ = write_data_matches_capture_directory(
                response, request_date=date, timezone="UTC", ccode3="NGA",
                output_root=ALLOWED_OUTPUT_RELATIVE, repository_root=repository,
            )
        except Exception:
            failure = "ARTIFACT_PERSISTENCE_FAILED"
            break
        try:
            verify_data_matches_capture_directory(
                capture, allowed_root=repository / ALLOWED_OUTPUT_RELATIVE,
            )
        except Exception:
            failure = "SOURCE_CAPTURE_VALIDATION_FAILED"
            break
        try:
            copied = _copy_capture(
                capture, request_date=date, artifact_root=artifact_root, repository=repository,
            )
        except Exception:
            failure = "ARTIFACT_PERSISTENCE_FAILED"
            failure_stage = "SOURCE_PERSISTENCE"
            break
        try:
            records.append(_record_from_capture(copied, artifact_root=artifact_root, expected_date=date))
        except Exception:
            failure = "SOURCE_CAPTURE_VALIDATION_FAILED"
            break
        if over_budget():
            failure = "TIMEOUT"
            break
    if failure is None:
        failure_stage = "CANONICAL_UPDATE"
        if over_budget():
            failure = "TIMEOUT"
    committed = failure is None and len(records) == len(request.dates)
    update = AthenaCanonicalStoreUpdate(
        schema_version=1, policy_id=UPDATE_POLICY, request_sha256=request.canonical_sha256,
        provider="fotmob", source_records=tuple(records), source_record_count=len(records),
        all_requested_dates_captured=committed, commit_status=READY if committed else NOT_COMMITTED,
    )
    try:
        # Reserve the finalization boundary: if the service budget expired while
        # assembling the delta, publish only a not-committed timeout receipt.
        if failure is None and over_budget():
            failure = "TIMEOUT"
            committed = False
            update = AthenaCanonicalStoreUpdate(
                schema_version=1, policy_id=UPDATE_POLICY, request_sha256=request.canonical_sha256,
                provider="fotmob", source_records=tuple(records), source_record_count=len(records),
                all_requested_dates_captured=False, commit_status=NOT_COMMITTED,
            )
        receipt = _receipt(
            exact_commit_sha=exact_commit_sha, request_sha256=request.canonical_sha256,
            update_sha256=update.canonical_sha256, committed=committed,
            provider_requests=attempted, source_count=len(records),
            failure_code=None if committed else failure or "SOURCE_CAPTURE_VALIDATION_FAILED",
            stage="COMPLETED" if committed else failure_stage,
        )
        _write_exact(artifact_root / UPDATE_NAME, update.canonical_bytes)
        _write_exact(artifact_root / REPLAY_NAME, canonical_json_bytes(_replay_manifest(request, update, receipt)))
        _write_exact(artifact_root / RECEIPT_NAME, receipt.canonical_bytes)
    except (OSError, AthenaIngestServiceError):
        # Fail closed when a top-level artifact write is rejected. Never replace
        # an existing receipt, since that may be more informative evidence.
        failure_receipt = _receipt(
            exact_commit_sha=exact_commit_sha, request_sha256=request.canonical_sha256,
            update_sha256=update.canonical_sha256, committed=False,
            provider_requests=attempted, source_count=len(records),
            failure_code="ARTIFACT_PERSISTENCE_FAILED", stage="CANONICAL_UPDATE",
        )
        try:
            _write_exact(artifact_root / RECEIPT_NAME, failure_receipt.canonical_bytes)
        except (OSError, AthenaIngestServiceError):
            pass
        return failure_receipt
    return receipt
