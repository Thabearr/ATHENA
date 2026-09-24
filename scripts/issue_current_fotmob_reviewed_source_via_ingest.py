"""Issue the exact current-reviewed FotMob lane through canonical ingest.

This workflow-facing adapter is intentionally fixed to the P4.4D/E proven
one-date FotMob/UTC/NGA subset. It is not a fallback wrapper: a canonical-lane
failure is terminal for this invocation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from domain.current_fotmob_fixture_review_policy import (
    DEFAULT_MAX_SOURCE_AGE_SECONDS,
    DEFAULT_MINIMUM_LEAD_SECONDS,
)
from services.current_fotmob_ingest_issuer import (
    CurrentFotMobIngestIssuerError,
    issue_current_reviewed_fotmob_via_canonical_ingest,
)
from scripts.issue_current_fotmob_reviewed_source import (
    DATASET_NAME,
    NEXT_REQUIRED_BOUNDARY,
    SCHEMA_VERSION,
    _write_result,
)


_LOWERCASE_COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Issue one UTC/NGA current-reviewed FotMob source via canonical ingest."
    )
    parser.add_argument("--date", required=True, help="Exact Gregorian YYYYMMDD date")
    parser.add_argument("--execute-live-network", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _failure_summary(*, failure_code: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": "CANONICAL_CURRENT_FOTMOB_INGEST_ISSUER_FAILED",
        "minimum_lead_seconds": DEFAULT_MINIMUM_LEAD_SECONDS,
        "max_source_age_seconds": DEFAULT_MAX_SOURCE_AGE_SECONDS,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "wager_placed": False,
        "failure_code": failure_code,
    }


def _emit(payload: dict[str, Any], output: Path, *, error: bool = False) -> None:
    _write_result(output, payload)
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    print(rendered, end="", file=sys.stderr if error else sys.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.execute_live_network:
        _emit(_failure_summary(failure_code="LIVE_NETWORK_FLAG_REQUIRED"), args.output, error=True)
        return 2

    github_ref = os.environ.get("GITHUB_REF")
    github_sha = os.environ.get("GITHUB_SHA")
    if github_ref != "refs/heads/main":
        _emit(_failure_summary(failure_code="MAIN_REF_REQUIRED"), args.output, error=True)
        return 1
    if not isinstance(github_sha, str) or _LOWERCASE_COMMIT_SHA.fullmatch(github_sha) is None:
        _emit(_failure_summary(failure_code="CANONICAL_GITHUB_SHA_REQUIRED"), args.output, error=True)
        return 1

    repository_root = Path(__file__).resolve().parents[1]
    try:
        result = issue_current_reviewed_fotmob_via_canonical_ingest(
            args.date,
            repository_root=repository_root,
            expected_git_sha=github_sha,
            expected_git_ref=github_ref,
            execute_live_network=True,
        )
        summary = result.execution.summary()
    except CurrentFotMobIngestIssuerError:
        _emit(_failure_summary(failure_code="CANONICAL_ISSUER_FAILED"), args.output, error=True)
        return 1
    except Exception:
        # Keep the workflow receipt useful without exposing raw input or an
        # implementation traceback as a misleading success artifact.
        _emit(_failure_summary(failure_code="CANONICAL_ISSUER_INTERNAL_FAILURE"), args.output, error=True)
        return 1

    _emit(summary, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
