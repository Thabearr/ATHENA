"""CLI for the reviewed FotMob UTC-native expected-goals validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from domain.fotmob_utc_native_expected_goals_model_validation import (
    build_validation,
    canonical_validation_receipt_bytes,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the reviewed offline UTC-native expected-goals model validation. "
            "No network, ScoreMatrix, pricing, selection, or BET behavior is performed."
        )
    )
    parser.add_argument(
        "projection",
        type=Path,
        help="Exact preserved V2 UTC-native feature projection NDJSON",
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
        help="Path for canonical validation receipt JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt, predictions = build_validation(
        args.projection,
        predictions_output=args.predictions_output,
    )
    receipt_raw = canonical_validation_receipt_bytes(receipt)
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
        "safety": receipt["safety"],
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
