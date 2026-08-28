#!/usr/bin/env python3
"""Fixed production-facing ATHENA current SportyBet accumulator request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from domain.current_sportybet_accumulator_request import execute_current_accumulator_request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-size", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/current-sportybet-accumulator"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = execute_current_accumulator_request(
        target_size=args.target_size,
        output_dir=args.output_dir,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
