#!/usr/bin/env python3
"""Execute the reviewed FotMob UTC-native feature qualification offline."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from domain.fotmob_utc_native_successor_feature_construction_qualification import (
    build_qualification,
    canonical_qualification_receipt_bytes,
)


DEFAULT_RECEIPT = Path(
    "artifacts/research-manifests/"
    "fotmob-utc-native-successor-feature-construction-qualification-v1.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-execute the exact preserved PR119 FotMob campaign and build "
            "the reviewed UTC-native research feature projection."
        )
    )
    parser.add_argument(
        "artifact",
        type=Path,
        help="Exact preserved FotMob GitHub Actions artifact ZIP.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RECEIPT,
        help="Canonical qualification receipt output path.",
    )
    parser.add_argument(
        "--projection-output",
        type=Path,
        default=None,
        help="Optional canonical UTC-native feature NDJSON output path.",
    )
    args = parser.parse_args()

    receipt = build_qualification(
        args.artifact,
        projection_output=args.projection_output,
    )
    raw = canonical_qualification_receipt_bytes(receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(
        f"wrote {args.output} size={len(raw)} "
        f"sha256={hashlib.sha256(raw).hexdigest()}"
    )
    if args.projection_output is not None:
        print(
            f"projection {args.projection_output} "
            f"size={receipt['projection']['size_bytes']} "
            f"sha256={receipt['projection']['sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
