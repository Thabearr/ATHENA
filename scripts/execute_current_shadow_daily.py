#!/usr/bin/env python3
"""Run the reviewed current Shadow chain for a user-facing daily/on-demand request.

This wrapper changes no football, pricing, Router, Portfolio, provider, freshness,
or authority semantics.  It only makes the already-reviewed fixture search horizon
an explicit user-facing request scope:

* ``today`` -> current UTC fixture date only;
* ``three-day`` -> the existing PR-F three-date research horizon.

Requested accumulator size remains a target and is limited to the frozen 1..50
Portfolio contract.  The wrapper preserves the PR-F 55-minute supervisor and
60-minute workflow cleanup margin.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound


WORKER_ENV = "ATHENA_CURRENT_SHADOW_DAILY_WORKER"
WORKER_MODULE = "scripts.execute_current_shadow_daily"
SCOPE_TODAY = "today"
SCOPE_THREE_DAY = "three-day"
SCOPE_DAY_COUNT = {
    SCOPE_TODAY: 1,
    SCOPE_THREE_DAY: 3,
}


def _target_size(value: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("target size must be an integer from 1 through 50") from exc
    if not 1 <= result <= 50:
        raise argparse.ArgumentTypeError("target size must be an integer from 1 through 50")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=_target_size, required=True)
    parser.add_argument(
        "--fixture-scope",
        choices=tuple(SCOPE_DAY_COUNT),
        default=SCOPE_TODAY,
        help="today = UTC date only; three-day = existing PR-F research horizon",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    return parser


def _execute_worker(args: argparse.Namespace) -> int:
    day_count = SCOPE_DAY_COUNT[args.fixture_scope]
    original = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT = day_count
    try:
        return bound._execute_worker(args)
    finally:
        runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT = original


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if os.environ.get(WORKER_ENV) == "1":
        return _execute_worker(args)

    env = dict(os.environ)
    env[WORKER_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        WORKER_MODULE,
        "--target-size",
        str(args.target_size),
        "--fixture-scope",
        args.fixture_scope,
        "--output-dir",
        str(args.output_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            env=env,
            check=False,
            timeout=bound._supervisor_timeout_seconds(),
        )
    except subprocess.TimeoutExpired:
        result = bound._write_timeout_receipt(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
