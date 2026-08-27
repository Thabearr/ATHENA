"""Explicit manual entry point for the reviewed direct SportyBet event GET."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from domain.sportybet_live_event_quote_evidence import (
    capture_live_event_quote_evidence,
    manifest_sha256,
    validate_direct_event_source_contract,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--execute-live-network", action="store_true")
    args = parser.parse_args(argv)

    contract = validate_direct_event_source_contract()
    directory, manifest = capture_live_event_quote_evidence(
        event_id=args.event_id,
        repository_root=args.repository_root,
        execute_live_network=args.execute_live_network,
    )
    print(
        json.dumps(
            {
                "status": "SPORTYBET_LIVE_EVENT_EVIDENCE_CAPTURED",
                "event_id": manifest.event_id,
                "observed_at": manifest.observed_at.isoformat().replace("+00:00", "Z"),
                "observation_authority": manifest.observation_authority,
                "provider_quote_at": None,
                "provider_snapshot_id": None,
                "evidence_directory": str(directory),
                "manifest_sha256": manifest_sha256(manifest),
                "raw_sha256": manifest.raw_sha256,
                "contract_sha256": contract["contract_sha256"],
                "athena_network_acquisition_performed": True,
                "price_all_authorized": False,
                "selection_authorized": False,
                "sportybet_execution_authorized": False,
                "bet_authorized": False,
                "wager_placed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
