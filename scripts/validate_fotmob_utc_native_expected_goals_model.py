#!/usr/bin/env python3
"""CLI for the reviewed FotMob UTC-native expected-goals model validation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from domain.fotmob_utc_native_expected_goals_model_validation import (
    build_validation,
    canonical_validation_receipt_bytes,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute the reviewed offline UTC-native expected-goals validation."
    )
    parser.add_argument(
        "artifact_zip",
        type=Path,
        help="Exact preserved V2 qualification artifact ZIP",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        required=True,
        help="Write canonical pooled evaluation predictions as NDJSON.",
    )
    parser.add_argument(
        "--receipt-output",
        type=Path,
        required=True,
        help="Write canonical model-validation receipt JSON.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    receipt = build_validation(
        args.artifact_zip,
        predictions_output=args.predictions_output,
    )
    raw = canonical_validation_receipt_bytes(receipt)
    args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_output.write_bytes(raw)
    sys.stdout.write(raw.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
