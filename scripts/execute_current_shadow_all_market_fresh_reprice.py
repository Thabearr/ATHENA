#!/usr/bin/env python3
"""Hosted Current Shadow supervisor for the explicit fresh-reprice composition."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from domain import current_shadow_all_market_runner as runner
from domain._current_shadow_quote_binding import (
    FRESH_REPRICE_MODE,
    FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID,
)
from domain.current_shadow_runtime_bindings import fresh_reprice_current_shadow_runtime_bindings
from scripts import execute_current_shadow_all_market as cli
from scripts import execute_current_shadow_all_market_summary_reuse as summary_cli


WORKER_MODULE = "scripts.execute_current_shadow_all_market_fresh_reprice"
FRESH_REPRICE_POLICY_ID = FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID


def _execute_worker(args, *, runtime_bindings=None) -> int:
    """Run the same supervisor composition with an explicit fresh binding."""

    if runtime_bindings is None:
        runtime_bindings = fresh_reprice_current_shadow_runtime_bindings()
    return summary_cli._execute_worker(args, runtime_bindings=runtime_bindings)


def main(argv: list[str] | None = None) -> int:
    args = cli.build_parser().parse_args(argv)
    if os.environ.get(cli.WORKER_ENV) == "1":
        return _execute_worker(args)

    env = dict(os.environ)
    env[cli.WORKER_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        WORKER_MODULE,
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
