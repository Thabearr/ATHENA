"""Resolve one manual ingest input into exact persisted request bytes."""

from __future__ import annotations

import argparse
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


def resolve_and_persist(
    *, event_name: str, dates_input: str, repository_root: Path,
    expected_git_sha: str, expected_git_ref: str,
) -> AthenaIngestRequest:
    repository = Path(repository_root).resolve(strict=True)
    root = _safe_directory(ARTIFACT_RELATIVE, repository)
    if any((root / name).exists() or (root / name).is_symlink() for name in (REQUEST_NAME, RECEIPT_NAME)):
        raise AthenaIngestContractError("refusing to replace existing ingest request/receipt evidence")
    exact_commit_sha = validate_exact_commit_sha(expected_git_sha)

    def fail(failure_code: str, message: str) -> None:
        receipt = make_failure_receipt(
            exact_commit_sha=exact_commit_sha, failure_code=failure_code,
            stage="REQUEST_RESOLUTION", raw_request_input_sha256=hashlib.sha256(
                dates_input.encode("utf-8")
            ).hexdigest(),
        )
        _write_exact(root / RECEIPT_NAME, receipt.canonical_bytes)
        raise AthenaIngestContractError(message)

    if expected_git_ref != CANONICAL_OPERATIONAL_REF:
        fail("LINEAGE_MISMATCH", "canonical ingest is restricted to refs/heads/main")
    if event_name != "workflow_dispatch":
        fail("INVALID_REQUEST", "ingest v1 accepts workflow_dispatch only")
    try:
        request = AthenaIngestRequest.for_dates(parse_dates_input(dates_input))
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
