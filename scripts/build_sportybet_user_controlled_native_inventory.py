"""Build a provider-native SportyBet odds inventory from preserved manual evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Sequence

from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native


def build_user_inventory(
    *,
    evidence_directory: Path,
    repository_root: Path,
) -> dict[str, Any]:
    repository = Path(repository_root).resolve(strict=True)
    evidence_root = repository / manual.ALLOWED_OUTPUT_RELATIVE
    directory, inventory = native.store_inventory_from_evidence(
        evidence_directory,
        repository_root=repository,
        evidence_root=evidence_root,
    )
    available = sum(
        1 for item in inventory.selections if item.availability.value == "AVAILABLE"
    )
    suspended = sum(
        1 for item in inventory.selections if item.availability.value == "SUSPENDED"
    )
    unknown = len(inventory.selections) - available - suspended
    market_identities = {
        (item.event_id, item.market_id, item.specifier)
        for item in inventory.selections
    }
    return {
        "status": "USER_CONTROLLED_PROVIDER_NATIVE_INVENTORY_PRESERVED",
        "provider": inventory.provider,
        "source_evidence_id": inventory.source_evidence_id,
        "source_evidence_manifest_sha256": inventory.source_evidence_manifest_sha256,
        "source_raw_sha256": inventory.source_raw_sha256,
        "inventory_directory": directory.relative_to(repository).as_posix(),
        "inventory_sha256": native.inventory_sha256(inventory),
        "event_count": len(inventory.events),
        "selection_count": len(inventory.selections),
        "market_identity_count": len(market_identities),
        "available_selection_count": available,
        "suspended_selection_count": suspended,
        "unknown_availability_selection_count": unknown,
        "acquisition_mode": inventory.acquisition_mode,
        "observation_authority": inventory.observation_authority,
        "observed_at_user_attested": inventory.observed_at_user_attested,
        "imported_at_utc": inventory.imported_at_utc,
        "athena_network_acquisition_performed": False,
        "provider_quote_at": None,
        "provider_snapshot_id": None,
        "provider_quote_timestamp_capability": inventory.provider_quote_timestamp_capability,
        "provider_snapshot_id_capability": inventory.provider_snapshot_id_capability,
        "network_acquisition_authorized": False,
        "fixture_reconciliation_authorized": False,
        "canonical_market_mapping_authorized": False,
        "fresh_price_authorized": False,
        "pricing_authorized": False,
        "model_integration_authorized": False,
        "selection_authorized": False,
        "slip_construction_authorized": False,
        "sportybet_execution_authorized": False,
        "bet_authorized": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify preserved user-controlled SportyBet evidence and derive its "
            "provider-native selection/odds inventory offline."
        )
    )
    parser.add_argument(
        "--evidence-directory",
        required=True,
        help="Exact PR #153 evidence directory under the reviewed manual evidence root.",
    )
    parser.add_argument(
        "--repository-root",
        default=".",
        help="ATHENA repository root (default: current directory).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = build_user_inventory(
        evidence_directory=Path(args.evidence_directory),
        repository_root=Path(args.repository_root),
    )
    print(
        json.dumps(
            receipt,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
