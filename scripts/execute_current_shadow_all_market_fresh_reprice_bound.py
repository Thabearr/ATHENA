#!/usr/bin/env python3
"""PR-F wrapper binding fresh reprice contexts into Price-all verification.

The fresh-reprice worker patches the quote-binding verifier so same-process
fresh direct-event contexts remain replay-checkable.  ``current_shadow_all_market_price_all``
imports that verifier by value, so its module-local alias must delegate to the
currently installed quote-binding verifier while the worker runs.  This wrapper
does only that binding; it does not alter pricing, Router, Portfolio, freshness,
provider semantics, transport, staking, or wager authority.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from domain import _current_shadow_quote_binding as quote_binding
from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market as cli
from scripts import execute_current_shadow_all_market_fresh_reprice as fresh_cli


WORKER_MODULE = "scripts.execute_current_shadow_all_market_fresh_reprice_bound"


def _execute_worker(args) -> int:
    original = runner.price_module.verify_current_shadow_price_context

    def current_quote_binding_verifier(value):
        return quote_binding.verify_current_shadow_price_context(value)

    runner.price_module.verify_current_shadow_price_context = (
        current_quote_binding_verifier
    )
    try:
        return fresh_cli._execute_worker(args)
    finally:
        runner.price_module.verify_current_shadow_price_context = original


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
            timeout=fresh_cli.runner_timeout(),
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
