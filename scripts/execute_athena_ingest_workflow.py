"""Execute a previously resolved manual ingest request with explicit authority."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Callable

from domain.ingest_contracts import (
    AthenaIngestContractError, AthenaIngestRequest, make_failure_receipt,
    sha256_bytes, strict_json_loads, validate_exact_commit_sha,
)
from services.athena_ingest_service import (
    ARTIFACT_RELATIVE, RECEIPT_NAME, REQUEST_NAME, AthenaIngestServiceError,
    _safe_directory, _write_exact, execute_ingest_request,
)

CANONICAL_OPERATIONAL_REF = "refs/heads/main"


def _git_head(repository_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return completed.stdout.strip()


def _write_pre_service_failure(
    *, repository: Path, exact_commit_sha: str, failure_code: str,
    request: AthenaIngestRequest | None = None, invalid_request_bytes: bytes | None = None,
) -> None:
    artifact_root = _safe_directory(ARTIFACT_RELATIVE, repository)
    receipt_path = artifact_root / RECEIPT_NAME
    if receipt_path.exists() or receipt_path.is_symlink():
        return
    receipt = make_failure_receipt(
        exact_commit_sha=exact_commit_sha, failure_code=failure_code,
        stage="REQUEST_RESOLUTION" if failure_code in {"INVALID_REQUEST", "LINEAGE_MISMATCH"} else "SOURCE_PERSISTENCE",
        request_sha256=request.canonical_sha256 if request is not None else None,
        raw_request_input_sha256=(
            sha256_bytes(invalid_request_bytes)
            if request is None and invalid_request_bytes is not None else None
        ),
    )
    _write_exact(receipt_path, receipt.canonical_bytes)


def execute_persisted_request(
    *, request_path: Path, execute_live_network: bool, repository_root: Path,
    expected_git_sha: str, expected_git_ref: str,
    git_head_provider: Callable[[Path], str] = _git_head,
    acquisition_callable: Callable[..., object] | None = None,
) -> int:
    repository = Path(repository_root).resolve(strict=True)
    expected = repository / ARTIFACT_RELATIVE / REQUEST_NAME
    try:
        actual_sha = git_head_provider(repository)
        validate_exact_commit_sha(actual_sha)
    except Exception as exc:
        raise AthenaIngestServiceError("could not resolve exact checked-out Git HEAD") from exc

    try:
        validate_exact_commit_sha(expected_git_sha)
        lineage_valid = expected_git_ref == CANONICAL_OPERATIONAL_REF and actual_sha == expected_git_sha
    except AthenaIngestContractError:
        lineage_valid = False

    request: AthenaIngestRequest | None = None
    raw: bytes | None = None
    try:
        path_matches = Path(request_path).resolve(strict=True) == expected
        raw = expected.read_bytes()
        request = AthenaIngestRequest.from_mapping(strict_json_loads(raw))
        if raw != request.canonical_bytes:
            raise AthenaIngestServiceError("resolved ingest request is not canonical")
        if not path_matches:
            _write_pre_service_failure(
                repository=repository, exact_commit_sha=actual_sha,
                failure_code="LINEAGE_MISMATCH", request=request,
            )
            raise AthenaIngestServiceError("executor requires the exact resolved ingest request")
    except (AthenaIngestServiceError, AthenaIngestContractError, OSError) as exc:
        if raw is not None:
            _write_pre_service_failure(
                repository=repository, exact_commit_sha=actual_sha,
                failure_code="INVALID_REQUEST", invalid_request_bytes=raw,
            )
        raise AthenaIngestServiceError(str(exc)) from exc

    if not lineage_valid:
        _write_pre_service_failure(
            repository=repository, exact_commit_sha=actual_sha,
            failure_code="LINEAGE_MISMATCH", request=request,
        )
        return 1
    if execute_live_network is not True:
        _write_pre_service_failure(
            repository=repository, exact_commit_sha=actual_sha,
            failure_code="LINEAGE_MISMATCH", request=request,
        )
        return 1
    try:
        kwargs = {"repository_root": repository, "exact_commit_sha": actual_sha}
        if acquisition_callable is not None:
            kwargs["acquisition_callable"] = acquisition_callable
        receipt = execute_ingest_request(request, **kwargs)
        return 0 if receipt.status == "SUCCESS" else 1
    except Exception as exc:
        try:
            _write_pre_service_failure(
                repository=repository, exact_commit_sha=actual_sha,
                failure_code="ARTIFACT_PERSISTENCE_FAILED", request=request,
            )
        except (OSError, AthenaIngestServiceError, AthenaIngestContractError):
            pass
        raise AthenaIngestServiceError(f"ingest service stopped: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--execute-live-network", action="store_true")
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--expected-git-ref", required=True)
    args = parser.parse_args(argv)
    try:
        return execute_persisted_request(
            request_path=args.request, execute_live_network=args.execute_live_network,
            repository_root=Path.cwd(),
            expected_git_sha=args.expected_git_sha,
            expected_git_ref=args.expected_git_ref,
        )
    except (AthenaIngestServiceError, AthenaIngestContractError, OSError) as exc:
        print(f"ATHENA ingest execution rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
