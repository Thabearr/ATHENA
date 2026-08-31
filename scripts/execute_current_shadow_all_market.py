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
HOSTED_SUPERVISOR_TIMEOUT_SECONDS = 50 * 60

# Live PR-F evidence demonstrated that the reviewed current source chain can
# legitimately consume ~20 minutes before Price-all/Router starts. Keep the
# supervisor bounded and fail-closed, but give the exact source-bound chain
# enough time to finish instead of timing out solely because of hosted runtime.
runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS = HOSTED_SUPERVISOR_TIMEOUT_SECONDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=int, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    return parser


def _install_history_lineage_reuse():
    """Reuse one exact reviewed PR151 GitHub snapshot across this worker run.

    Main already records every GitHub read needed to replay the PR151 lineage
    audit. PR-F's three-date horizon must not perform that same remote audit once
    per matched date. The first history build remains the reviewed live issuer;
    later date-specific prefixes replay only from its immutable captured evidence.
    """

    original = runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff
    evidence_by_main: dict[str, object] = {}

    def build(**kwargs):
        expected_main_sha = kwargs.get("expected_main_sha")
        evidence = evidence_by_main.get(expected_main_sha)
        if evidence is None:
            history = original(**kwargs)
            captured = history.source_bundle.github_evidence
            if captured.expected_main_sha != expected_main_sha:
                raise runner.CurrentShadowAllMarketRunnerError(
                    "captured PR151 lineage evidence main identity drifted"
                )
            evidence_by_main[expected_main_sha] = captured
            return history

        return runner.latest_history._build_with_readers(
            current_bootstrap=kwargs["current_bootstrap"],
            source_raw_json=kwargs["source_raw_json"],
            source_manifest=kwargs["source_manifest"],
            legacy_bootstrap_projection_raw=kwargs["legacy_bootstrap_projection_raw"],
            expected_main_sha=kwargs["expected_main_sha"],
            get_main_ref=lambda: evidence.json("main_ref"),
            get_runs_page=lambda page, per_page: evidence.json(
                f"runs:{page}:{per_page}"
            ),
            get_run_by_id=lambda run_id: evidence.json(f"run:{run_id}"),
            get_run_artifacts=lambda run_id: evidence.json(f"artifacts:{run_id}"),
            download_artifact_zip=lambda artifact_id: evidence.binary(
                f"artifact_zip:{artifact_id}"
            ),
            get_release=lambda tag: evidence.json(f"release:{tag}"),
            download_release_asset=lambda asset_id: evidence.binary(
                f"release_asset:{asset_id}"
            ),
            get_run_jobs=lambda run_id: evidence.json(f"jobs:{run_id}"),
            repository_root=kwargs.get("repository_root"),
        )

    runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = build
    return original


def _execute_once(args: argparse.Namespace) -> int:
    original_history_builder = _install_history_lineage_reuse()
    try:
        result = runner.execute_current_shadow_all_market(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
    finally:
        runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = (
            original_history_builder
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
