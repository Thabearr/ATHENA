"""Execute an already-resolved canonical request as workflow transport only."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable

from domain.run_contracts import RunContractError, RunReceipt, RunRequest, canonical_json_bytes
from services.athena_run_service import AthenaRunService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_OPERATIONAL_REF = "refs/heads/main"
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)


class AthenaWorkflowExecutionError(RuntimeError):
    """Raised when an exact request cannot be safely bound to this workflow run."""


def _git_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AthenaWorkflowExecutionError("could not resolve checked-out Git HEAD") from exc
    return completed.stdout.strip()


def execute_persisted_request(
    *,
    request_path: Path,
    output_root: Path,
    expected_git_sha: str,
    expected_git_ref: str,
    service: AthenaRunService | None = None,
    git_head_provider: Callable[[], str] = _git_head,
) -> RunReceipt:
    """Validate lineage/ref before service invocation; never re-resolve dates."""

    if type(expected_git_sha) is not str or _GIT_SHA_RE.fullmatch(expected_git_sha) is None:
        raise AthenaWorkflowExecutionError("expected Git SHA must be exact lowercase 40-character text")
    if expected_git_ref != CANONICAL_OPERATIONAL_REF:
        raise AthenaWorkflowExecutionError("canonical workflow execution is restricted to refs/heads/main")
    try:
        actual_head = git_head_provider()
    except AthenaWorkflowExecutionError:
        raise
    except Exception as exc:
        raise AthenaWorkflowExecutionError("could not verify exact checked-out HEAD") from exc
    if actual_head != expected_git_sha:
        raise AthenaWorkflowExecutionError("checked-out HEAD differs from expected GITHUB_SHA")

    if not isinstance(request_path, Path) or not isinstance(output_root, Path):
        raise AthenaWorkflowExecutionError("request_path and output_root must be pathlib.Path")
    try:
        raw_request = request_path.read_bytes()
        request = RunRequest.from_json_bytes(raw_request)
    except (OSError, RunContractError) as exc:
        raise AthenaWorkflowExecutionError("persisted RunRequest is missing or noncanonical") from exc
    if raw_request != canonical_json_bytes(request):
        raise AthenaWorkflowExecutionError("persisted RunRequest bytes are not canonical")

    selected_service = service if service is not None else AthenaRunService()
    receipt = selected_service.run(request, output_root=output_root)
    if type(receipt) is not RunReceipt:
        raise AthenaWorkflowExecutionError("AthenaRunService did not return exact RunReceipt")
    if (
        receipt.request != request
        or receipt.exact_commit_sha != expected_git_sha
        or receipt.wager_placed is not False
    ):
        raise AthenaWorkflowExecutionError("AthenaRunService receipt contradicts request/lineage/safety")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/athena-runs"))
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--expected-git-ref", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = execute_persisted_request(
            request_path=args.request,
            output_root=args.output_root,
            expected_git_sha=args.expected_git_sha,
            expected_git_ref=args.expected_git_ref,
        )
    except (AthenaWorkflowExecutionError, OSError) as exc:
        print(f"ATHENA workflow execution stopped: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
