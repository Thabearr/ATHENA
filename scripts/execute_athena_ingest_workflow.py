"""Execute a previously resolved manual ingest request with explicit authority."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from domain.ingest_contracts import AthenaIngestContractError, AthenaIngestRequest, strict_json_loads
from services.athena_ingest_service import (
    ARTIFACT_RELATIVE, REQUEST_NAME, AthenaIngestServiceError, execute_ingest_request,
)


def execute_persisted_request(*, request_path: Path, execute_live_network: bool, repository_root: Path) -> int:
    if execute_live_network is not True:
        raise AthenaIngestServiceError("explicit --execute-live-network is required")
    repository = Path(repository_root).resolve(strict=True)
    expected = repository / ARTIFACT_RELATIVE / REQUEST_NAME
    if Path(request_path).resolve(strict=True) != expected:
        raise AthenaIngestServiceError("executor requires the exact resolved ingest request")
    raw = expected.read_bytes()
    request = AthenaIngestRequest.from_mapping(strict_json_loads(raw))
    if raw != request.canonical_bytes:
        raise AthenaIngestServiceError("resolved ingest request is not canonical")
    receipt = execute_ingest_request(request, repository_root=repository)
    return 0 if receipt.status == "SUCCESS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--execute-live-network", action="store_true")
    args = parser.parse_args(argv)
    try:
        return execute_persisted_request(
            request_path=args.request, execute_live_network=args.execute_live_network,
            repository_root=Path.cwd(),
        )
    except (AthenaIngestServiceError, AthenaIngestContractError, OSError) as exc:
        print(f"ATHENA ingest execution rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
