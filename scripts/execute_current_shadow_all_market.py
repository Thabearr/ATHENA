#!/usr/bin/env python3
"""Execute one source-bound current ATHENA all-market Shadow request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from domain.current_shadow_all_market_runner import execute_current_shadow_all_market


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=int, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = execute_current_shadow_all_market(
        target_size=args.target_size,
        output_dir=args.output_dir,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
