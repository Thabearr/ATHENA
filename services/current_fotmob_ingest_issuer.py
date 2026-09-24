"""Activation-ready one-date canonical-ingest issuer for current FotMob review.

This service is deliberately not wired to a workflow or live caller. It composes
the shared ingest service with the P4.4D offline compatibility projection; it
does not own provider transport, retry, or PR243 policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from domain.ingest_contracts import (
    AthenaIngestContractError,
    AthenaIngestReceipt,
    AthenaIngestRequest,
    validate_exact_commit_sha,
)
from services.athena_ingest_service import (
    ARTIFACT_RELATIVE,
    execute_ingest_request,
)
from services.current_fotmob_ingest_compatibility import (
    CurrentFotMobIngestCompatibilityError,
    CurrentFotMobIngestCompatibilityResult,
    project_current_reviewed_fotmob_source_from_ingest_artifact,
)


class CurrentFotMobIngestIssuerError(RuntimeError):
    """The canonical current-FotMob issuer could not proceed safely."""


class CurrentFotMobIngestIssuerFailure(CurrentFotMobIngestIssuerError):
    """Canonical ingest failed; the typed receipt is retained on the exception."""

    def __init__(self, receipt: AthenaIngestReceipt):
        self.ingest_receipt = receipt
        super().__init__(
            f"canonical ingest failed: {receipt.failure_code} at {receipt.stage}"
        )


@dataclass(frozen=True)
class CurrentFotMobIngestIssuerResult:
    """Bound access to the canonical ingest receipt and P4.4D/PR243 result."""

    ingest_receipt: AthenaIngestReceipt
    compatibility_result: CurrentFotMobIngestCompatibilityResult

    @property
    def execution(self) -> Any:
        """The existing PR243 current-reviewed execution, without new authority."""

        return self.compatibility_result.execution


def _actual_git_head(repository_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CurrentFotMobIngestIssuerError(
            "could not establish the checked-out Git commit"
        ) from exc
    return completed.stdout.strip()


def _safe_repository_root(value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise CurrentFotMobIngestIssuerError("repository root is unavailable") from exc
    if not root.is_dir():
        raise CurrentFotMobIngestIssuerError("repository root must be a directory")
    return root


def _validate_unused_artifact_root(repository_root: Path) -> Path:
    """Reject symlinked, escaped, or already-published canonical output."""

    relative = ARTIFACT_RELATIVE
    if relative.is_absolute() or ".." in relative.parts:
        raise CurrentFotMobIngestIssuerError("canonical artifact root is not repository-relative")
    root = repository_root / relative
    cursor = repository_root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise CurrentFotMobIngestIssuerError("canonical artifact root contains a symlink")
    try:
        if root.exists():
            if not root.is_dir():
                raise CurrentFotMobIngestIssuerError(
                    "canonical artifact root is not a directory"
                )
            if any(root.iterdir()):
                raise CurrentFotMobIngestIssuerError(
                    "canonical artifact root contains prior evidence"
                )
    except OSError as exc:
        raise CurrentFotMobIngestIssuerError(
            "canonical artifact root cannot be inspected"
        ) from exc
    return root


def _issued_at_utc(clock: Callable[[], datetime]) -> datetime:
    if not callable(clock):
        raise CurrentFotMobIngestIssuerError("clock must be callable")
    try:
        value = clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(datetime_timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentFotMobIngestIssuerError("clock must return valid UTC-aware time") from exc


def issue_current_reviewed_fotmob_via_canonical_ingest(
    request_date: str,
    *,
    repository_root: Path,
    expected_git_sha: str,
    expected_git_ref: str,
    execute_live_network: bool,
    timezone: str = "UTC",
    ccode3: str = "NGA",
    acquisition_callable: Callable[..., CapturedFotMobDataMatchesResponse] | None = None,
    git_head_provider: Callable[[Path], str] = _actual_git_head,
    clock: Callable[[], datetime] = lambda: datetime.now(datetime_timezone.utc),
    code_state: Mapping[str, Any] | None = None,
) -> CurrentFotMobIngestIssuerResult:
    """Acquire one canonical date then project it through the frozen PR243 path.

    ``acquisition_callable``, ``git_head_provider`` and ``clock`` are dependency
    seams for deterministic offline tests, not workflow or CLI inputs. The
    default acquisition implementation remains exclusively in the canonical
    ingest service.
    """

    if type(execute_live_network) is not bool or execute_live_network is not True:
        raise CurrentFotMobIngestIssuerError("explicit execute_live_network=True is required")
    if timezone != "UTC" or ccode3 != "NGA":
        raise CurrentFotMobIngestIssuerError("only the canonical UTC/NGA request is supported")
    if expected_git_ref != "refs/heads/main":
        raise CurrentFotMobIngestIssuerError("expected Git ref must be refs/heads/main")
    try:
        validate_exact_commit_sha(expected_git_sha)
        request = AthenaIngestRequest.for_dates((request_date,))
    except (AthenaIngestContractError, TypeError, ValueError) as exc:
        raise CurrentFotMobIngestIssuerError("request or expected commit is invalid") from exc
    if (
        request.provider != "fotmob"
        or len(request.dates) != 1
        or request.timezone != "UTC"
        or request.ccode3 != "NGA"
    ):
        raise CurrentFotMobIngestIssuerError("request is outside one-date FotMob UTC/NGA scope")

    repository = _safe_repository_root(repository_root)
    artifact_root = _validate_unused_artifact_root(repository)
    if not callable(git_head_provider):
        raise CurrentFotMobIngestIssuerError("Git-head provider must be callable")
    try:
        actual_git_sha = git_head_provider(repository)
        validate_exact_commit_sha(actual_git_sha)
    except (AthenaIngestContractError, OSError, TypeError, ValueError) as exc:
        raise CurrentFotMobIngestIssuerError("actual checked-out Git commit is invalid") from exc
    if actual_git_sha != expected_git_sha:
        raise CurrentFotMobIngestIssuerError(
            "checked-out HEAD differs from expected Git commit"
        )

    service_kwargs: dict[str, Any] = {
        "repository_root": repository,
        "exact_commit_sha": actual_git_sha,
    }
    if acquisition_callable is not None:
        if not callable(acquisition_callable):
            raise CurrentFotMobIngestIssuerError("acquisition seam must be callable")
        service_kwargs["acquisition_callable"] = acquisition_callable
    try:
        ingest_receipt = execute_ingest_request(request, **service_kwargs)
    except Exception as exc:
        # The shared service owns persistence of any partial receipt it can
        # safely emit. Do not retry or fabricate a competing business receipt.
        raise CurrentFotMobIngestIssuerError(
            "shared canonical ingest service failed before returning a receipt"
        ) from exc
    if not isinstance(ingest_receipt, AthenaIngestReceipt):
        raise CurrentFotMobIngestIssuerError(
            "shared canonical ingest service returned an invalid receipt"
        )
    if ingest_receipt.status != "SUCCESS":
        raise CurrentFotMobIngestIssuerFailure(ingest_receipt)
    if (
        ingest_receipt.stage != "COMPLETED"
        or ingest_receipt.failure_code is not None
        or ingest_receipt.exact_commit_sha != actual_git_sha
        or ingest_receipt.request_sha256 != request.canonical_sha256
        or not ingest_receipt.canonical_store_update_committed
        or ingest_receipt.provider_request_count != 1
        or ingest_receipt.source_count != 1
    ):
        raise CurrentFotMobIngestIssuerError(
            "canonical ingest receipt does not satisfy the one-source completion contract"
        )

    try:
        compatibility = project_current_reviewed_fotmob_source_from_ingest_artifact(
            artifact_root,
            issued_at=_issued_at_utc(clock),
            repository_root=repository,
            code_state=code_state,
        )
    except CurrentFotMobIngestCompatibilityError as exc:
        raise CurrentFotMobIngestIssuerError(
            "P4.4D canonical source projection failed"
        ) from exc
    if (
        compatibility.receipt.get("ingest_request_sha256") != request.canonical_sha256
        or compatibility.receipt.get("canonical_ingest_receipt_sha256")
        != ingest_receipt.canonical_sha256
        or compatibility.receipt.get("original_ingest_exact_commit_sha") != actual_git_sha
        or compatibility.receipt.get("provider_request_count_by_adapter") != 0
        or compatibility.receipt.get("source_count") != 1
    ):
        raise CurrentFotMobIngestIssuerError(
            "P4.4D result is not bound to the exact canonical ingest receipt"
        )
    return CurrentFotMobIngestIssuerResult(
        ingest_receipt=ingest_receipt,
        compatibility_result=compatibility,
    )
