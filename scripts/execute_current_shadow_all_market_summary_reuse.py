#!/usr/bin/env python3
"""PR-F hosted wrapper for exact builder-issued history summary SHA reuse."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market as cli


WORKER_MODULE = "scripts.execute_current_shadow_all_market_summary_reuse"
_BASE_XG_INSTALLER = cli._install_builder_issued_history_xg_reuse
_original_history_sha = None


def _install_builder_issued_history_summary_sha_reuse(
    issued_by_identity: dict[int, object],
):
    """Reuse canonical SHA only for exact same-worker builder-issued histories.

    Run #30 completed Price-all/Router/portfolio-input work for all observed
    reconciled fixtures, then remained inside the PRICE_ALL_ROUTER stage until
    the fixed supervisor expired. The only work after that loop and before the
    next stage is receipt/source-summary materialization, which calls the public
    PR151 history SHA helper again. That helper deliberately reconstructs the
    frozen dataclass and therefore replays deep source validation.

    The PR-F worker has already built and consumed these exact frozen history
    objects through the reviewed builder and PR-C path. Reuse only the canonical
    SHA of the same object identity. Unknown or caller-supplied histories still
    execute the original public helper unchanged. Failed canonicalization is
    never cached.
    """

    original = (
        runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff
    )
    sha_by_identity: dict[int, tuple[object, str]] = {}

    def history_sha(value):
        issued = issued_by_identity.get(id(value))
        if issued is not value:
            return original(value)
        if (
            type(value)
            is not runner.latest_history.CurrentLatestDurableFreshHistoryHandoff
        ):
            return original(value)

        cached = sha_by_identity.get(id(value))
        if cached is not None and cached[0] is value:
            return cached[1]

        try:
            canonical = runner.latest_history._canonical(value.to_dict())
        except Exception as exc:
            raise runner.CurrentShadowAllMarketRunnerError(
                "builder-issued PR151 summary history canonicalization failed"
            ) from exc
        digest = hashlib.sha256(canonical).hexdigest()
        sha_by_identity[id(value)] = (value, digest)
        return digest

    runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff = (
        history_sha
    )
    return original


def _install_xg_and_summary_reuse(issued_by_identity: dict[int, object]):
    global _original_history_sha
    original_xg = _BASE_XG_INSTALLER(issued_by_identity)
    if _original_history_sha is not None:
        raise runner.CurrentShadowAllMarketRunnerError(
            "PR-F summary history SHA reuse installed more than once"
        )
    _original_history_sha = _install_builder_issued_history_summary_sha_reuse(
        issued_by_identity
    )
    return original_xg


def _execute_worker(args) -> int:
    global _original_history_sha
    original_installer = cli._install_builder_issued_history_xg_reuse
    cli._install_builder_issued_history_xg_reuse = _install_xg_and_summary_reuse
    try:
        return cli._execute_once(args)
    finally:
        cli._install_builder_issued_history_xg_reuse = original_installer
        if _original_history_sha is not None:
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff = (
                _original_history_sha
            )
            _original_history_sha = None


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
