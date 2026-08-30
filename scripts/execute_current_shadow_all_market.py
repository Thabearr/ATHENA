#!/usr/bin/env python3
"""Execute one source-bound current ATHENA all-market Shadow request."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from domain import current_shadow_all_market_runner as runner

WORKER_ENV = "ATHENA_CURRENT_SHADOW_ALL_MARKET_WORKER"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=int, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    return parser


def _execute_once(args: argparse.Namespace) -> int:
    result = runner.execute_current_shadow_all_market(
        target_size=args.target_size,
        output_dir=args.output_dir,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if os.environ.get(WORKER_ENV) == "1":
        return _execute_once(args)

    env = dict(os.environ)
    env[WORKER_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        "scripts.execute_current_shadow_all_market",
        "--target-size",
        str(args.target_size),
        "--output-dir",
        str(args.output_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            env=env,
            check=False,
            timeout=runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        result = runner.write_current_shadow_timeout_receipt(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
