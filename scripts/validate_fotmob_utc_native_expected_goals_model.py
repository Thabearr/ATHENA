"""CLI for the reviewed source-bound FotMob UTC-native xG validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from domain.fotmob_utc_native_expected_goals_model_validation_source_bound import (
    build_source_bound_validation,
    canonical_source_bound_receipt_bytes,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the reviewed offline UTC-native expected-goals model validation "
            "from the exact preserved V2 artifact. No network, ScoreMatrix, pricing, "
            "selection, or BET behavior is performed."
        )
    )
    parser.add_argument(
        "artifact_zip",
        type=Path,
        help="Exact preserved V2 feature-qualification artifact ZIP",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        required=True,
        help="Path for hash-sealed evaluation prediction NDJSON",
    )
    parser.add_argument(
        "--receipt-output",
        type=Path,
        required=True,
        help="Path for canonical source-bound validation receipt JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt, predictions = build_source_bound_validation(
        args.artifact_zip,
        predictions_output=args.predictions_output,
    )
    receipt_raw = canonical_source_bound_receipt_bytes(receipt)
    args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_output.write_bytes(receipt_raw)
    summary = {
        "validation_state": receipt["validation_state"],
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "receipt_size_bytes": len(receipt_raw),
        "predictions_sha256": hashlib.sha256(predictions).hexdigest(),
        "predictions_size_bytes": len(predictions),
        "prediction_record_count": receipt["predictions"]["record_count"],
        "next_required_boundary": receipt["next_required_boundary"],
        "automatic_model_approval": receipt["automatic_model_approval"],
        "safety": receipt["safety"],
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
