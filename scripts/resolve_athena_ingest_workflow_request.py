"""Resolve one manual ingest input into exact persisted request bytes."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from domain.ingest_contracts import AthenaIngestContractError, AthenaIngestRequest, parse_dates_input
from services.athena_ingest_service import ARTIFACT_RELATIVE, REQUEST_NAME, _safe_directory, _write_exact


def resolve_and_persist(*, event_name: str, dates_input: str, repository_root: Path) -> AthenaIngestRequest:
    if event_name != "workflow_dispatch":
        raise AthenaIngestContractError("ingest v1 accepts workflow_dispatch only")
    request = AthenaIngestRequest.for_dates(parse_dates_input(dates_input))
    repository = Path(repository_root).resolve(strict=True)
    root = _safe_directory(ARTIFACT_RELATIVE, repository)
    _write_exact(root / REQUEST_NAME, request.canonical_bytes)
    return request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        resolve_and_persist(
            event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
            dates_input=os.environ.get("INPUT_DATES", ""),
            repository_root=Path.cwd(),
        )
        return 0
    except (AthenaIngestContractError, OSError) as exc:
        print(f"ATHENA ingest request rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
