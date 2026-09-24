"""Resolve one manual ingest input into exact persisted request bytes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys

from domain.ingest_contracts import (
    AthenaIngestContractError, AthenaIngestRequest, make_failure_receipt,
    parse_dates_input, validate_exact_commit_sha,
)
from services.athena_ingest_service import (
    ARTIFACT_RELATIVE, RECEIPT_NAME, REQUEST_NAME, AthenaIngestServiceError,
    _safe_directory, _write_exact,
)

CANONICAL_OPERATIONAL_REF = "refs/heads/main"
SCHEDULE_FAILURE_MARKER = b"ATHENA_INGEST_SCHEDULE_EVENT_RESOLUTION_V1\n"
UNSUPPORTED_EVENT_MARKER = b"ATHENA_INGEST_UNSUPPORTED_EVENT_V1\n"


def resolve_ingest_workflow_request(
    *, event_name: str, dates_input: str | None, now: datetime | None = None,
) -> AthenaIngestRequest:
    """Resolve supported GitHub events through one pure canonical request boundary."""
    if event_name == "workflow_dispatch":
        if not isinstance(dates_input, str):
            raise AthenaIngestContractError("workflow_dispatch requires the dates input")
        return AthenaIngestRequest.for_dates(parse_dates_input(dates_input))
    if event_name == "schedule":
        if dates_input not in (None, ""):
            raise AthenaIngestContractError("schedule does not accept dispatch date input")
        instant = datetime.now(timezone.utc) if now is None else now
        if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
            raise AthenaIngestContractError("scheduled ingest clock must be timezone-aware")
        utc_date = instant.astimezone(timezone.utc).strftime("%Y%m%d")
        return AthenaIngestRequest.for_dates((utc_date,))
    raise AthenaIngestContractError(f"unsupported ingest workflow event: {event_name!r}")


def resolution_input_sha256(*, event_name: str, dates_input: str | None) -> str:
    """Hash unresolved request material without retaining user input in a receipt.

    Manual dispatch preserves the established digest of exact UTF-8 `dates` bytes.
    A schedule has no user input, so its failure digest is a versioned event marker;
    unexpected schedule input is domain-separated and hashed but never persisted.
    """
    if event_name == "workflow_dispatch":
        material = (dates_input if isinstance(dates_input, str) else "").encode("utf-8")
    elif event_name == "schedule":
        extra = (dates_input if isinstance(dates_input, str) else "").encode("utf-8")
        material = SCHEDULE_FAILURE_MARKER + extra
    else:
        event = event_name.encode("utf-8") if isinstance(event_name, str) else b""
        extra = (dates_input if isinstance(dates_input, str) else "").encode("utf-8")
        material = UNSUPPORTED_EVENT_MARKER + event + b"\n" + extra
    return hashlib.sha256(material).hexdigest()


def resolve_and_persist(
    *, event_name: str, dates_input: str | None, repository_root: Path,
    expected_git_sha: str, expected_git_ref: str,
    now: datetime | None = None,
) -> AthenaIngestRequest:
    repository = Path(repository_root).resolve(strict=True)
    root = _safe_directory(ARTIFACT_RELATIVE, repository)
    if any((root / name).exists() or (root / name).is_symlink() for name in (REQUEST_NAME, RECEIPT_NAME)):
        raise AthenaIngestContractError("refusing to replace existing ingest request/receipt evidence")
    exact_commit_sha = validate_exact_commit_sha(expected_git_sha)

    def fail(failure_code: str, message: str) -> None:
        receipt = make_failure_receipt(
            exact_commit_sha=exact_commit_sha, failure_code=failure_code,
            stage="REQUEST_RESOLUTION",
            raw_request_input_sha256=resolution_input_sha256(
                event_name=event_name, dates_input=dates_input,
            ),
        )
        _write_exact(root / RECEIPT_NAME, receipt.canonical_bytes)
        raise AthenaIngestContractError(message)

    if expected_git_ref != CANONICAL_OPERATIONAL_REF:
        fail("LINEAGE_MISMATCH", "canonical ingest is restricted to refs/heads/main")
    try:
        request = resolve_ingest_workflow_request(
            event_name=event_name, dates_input=dates_input, now=now,
        )
    except AthenaIngestContractError as exc:
        fail("INVALID_REQUEST", str(exc))
    _write_exact(root / REQUEST_NAME, request.canonical_bytes)
    return request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--expected-git-ref", required=True)
    args = parser.parse_args(argv)
    try:
        resolve_and_persist(
            event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
            dates_input=os.environ.get("INPUT_DATES", ""),
            repository_root=Path.cwd(),
            expected_git_sha=args.expected_git_sha,
            expected_git_ref=args.expected_git_ref,
        )
        return 0
    except (AthenaIngestContractError, AthenaIngestServiceError, OSError) as exc:
        print(f"ATHENA ingest request rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
