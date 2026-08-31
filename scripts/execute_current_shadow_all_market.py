#!/usr/bin/env python3
"""Execute one source-bound current ATHENA all-market Shadow request."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from domain import _current_shadow_quote_binding as quote_binding
from domain import current_shadow_all_market_runner as runner

WORKER_ENV = "ATHENA_CURRENT_SHADOW_ALL_MARKET_WORKER"
HOSTED_SUPERVISOR_TIMEOUT_SECONDS = 50 * 60
PRICE_DIAGNOSTIC_FILENAME = "current-shadow-price-stage-diagnostic.json"
PRICE_DIAGNOSTIC_STAGES = frozenset({
    "CONTEXT_BUILD_STARTED",
    "CONTEXT_BUILD_COMPLETED",
    "PRICE_ALL_STARTED",
    "PRICE_ALL_COMPLETED",
    "ROUTER_STARTED",
    "ROUTER_COMPLETED",
    "PORTFOLIO_INPUT_STARTED",
    "PORTFOLIO_INPUT_COMPLETED",
})

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


def _install_price_context_verification_reuse():
    """Memoize one exact source replay per immutable Shadow price context.

    The public Price-all boundary verifies a freshly builder-issued context and
    exact-quote issuance verifies that same immutable context again. Run #25
    proved that repeating the full PR151/PR-C replay for the same canonical
    context across eight reconciled fixtures can exhaust the bounded live-run
    budget. Preserve the first exact verification unchanged, then reuse only its
    verified result for the same canonical SHA-256 during this worker process.
    """

    original_price_verify = runner.price_module.verify_current_shadow_price_context
    original_quote_verify = quote_binding.verify_current_shadow_price_context
    verified_by_identity: dict[str, object] = {}

    def verify(value):
        identity = value.canonical_sha256
        cached = verified_by_identity.get(identity)
        if cached is not None:
            return cached

        checked = original_quote_verify(value)
        if checked.canonical_sha256 != identity:
            raise runner.CurrentShadowAllMarketRunnerError(
                "verified Shadow price context identity drifted"
            )
        verified_by_identity[identity] = checked
        return checked

    runner.price_module.verify_current_shadow_price_context = verify
    quote_binding.verify_current_shadow_price_context = verify
    return original_price_verify, original_quote_verify


def _install_price_stage_diagnostics(output_dir: Path):
    """Persist the exact in-flight operation inside PRICE_ALL_ROUTER.

    This is evidence-only instrumentation. It does not change source admission,
    pricing, routing, portfolio policy, timeouts, or authority. A supervisor
    timeout leaves the last started/completed operation durable in the artifact.
    """

    original_context = runner.price_module.build_current_shadow_price_context_from_reconciliation
    original_price_all = runner.price_module.price_all_shadow_fixture
    original_router = runner.router_module.route_shadow_price_results
    original_portfolio_input = runner.portfolio_module.build_shadow_portfolio_router_input
    fixture_index_by_identity: dict[tuple[str, str], int] = {}
    next_fixture_index = 0

    def write(
        stage: str,
        *,
        fixture_index: int,
        fixture_identity: str | None,
        provider_event_id: str | None,
    ) -> None:
        if stage not in PRICE_DIAGNOSTIC_STAGES:
            raise runner.CurrentShadowAllMarketRunnerError(
                "price diagnostic stage escaped reviewed vocabulary"
            )
        runner._write(
            output_dir / PRICE_DIAGNOSTIC_FILENAME,
            {
                "schema_version": runner.SCHEMA_VERSION,
                "dataset_name": runner.DATASET_NAME,
                "stage": stage,
                "fixture_index": fixture_index,
                "fixture_identity": fixture_identity,
                "provider_event_id": provider_event_id,
                "observed_at": runner._now().isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z"),
                "wager_placed": False,
            },
        )

    def identity(value) -> tuple[str | None, str | None]:
        return (
            getattr(value, "fixture_identity", None),
            getattr(value, "provider_event_id", None),
        )

    def fixture_index(fixture_identity: str | None, provider_event_id: str | None) -> int:
        key = (fixture_identity or "", provider_event_id or "")
        return fixture_index_by_identity.get(key, 0)

    def build_context(*args, **kwargs):
        nonlocal next_fixture_index
        fixture_identity = kwargs.get("fixture_identity")
        provider_event_id = kwargs.get("provider_event_id")
        next_fixture_index += 1
        index = next_fixture_index
        fixture_index_by_identity[(fixture_identity or "", provider_event_id or "")] = index
        write(
            "CONTEXT_BUILD_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_context(*args, **kwargs)
        write(
            "CONTEXT_BUILD_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    def price_all(context, *args, **kwargs):
        fixture_identity, provider_event_id = identity(context)
        index = fixture_index(fixture_identity, provider_event_id)
        write(
            "PRICE_ALL_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_price_all(context, *args, **kwargs)
        write(
            "PRICE_ALL_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    def route(bundle, *args, **kwargs):
        context = getattr(bundle, "_context", None)
        fixture_identity, provider_event_id = identity(context)
        index = fixture_index(fixture_identity, provider_event_id)
        write(
            "ROUTER_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_router(bundle, *args, **kwargs)
        write(
            "ROUTER_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    def build_portfolio_input(*args, **kwargs):
        bundle = kwargs.get("price_all_bundle")
        if bundle is None and args:
            bundle = args[0]
        context = getattr(bundle, "_context", None)
        fixture_identity, provider_event_id = identity(context)
        index = fixture_index(fixture_identity, provider_event_id)
        write(
            "PORTFOLIO_INPUT_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_portfolio_input(*args, **kwargs)
        write(
            "PORTFOLIO_INPUT_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    runner.price_module.build_current_shadow_price_context_from_reconciliation = build_context
    runner.price_module.price_all_shadow_fixture = price_all
    runner.router_module.route_shadow_price_results = route
    runner.portfolio_module.build_shadow_portfolio_router_input = build_portfolio_input
    return original_context, original_price_all, original_router, original_portfolio_input


def _execute_once(args: argparse.Namespace) -> int:
    original_history_builder = _install_history_lineage_reuse()
    original_price_verify, original_quote_verify = _install_price_context_verification_reuse()
    (
        original_context,
        original_price_all,
        original_router,
        original_portfolio_input,
    ) = _install_price_stage_diagnostics(args.output_dir)
    try:
        result = runner.execute_current_shadow_all_market(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
    finally:
        runner.price_module.build_current_shadow_price_context_from_reconciliation = original_context
        runner.price_module.price_all_shadow_fixture = original_price_all
        runner.router_module.route_shadow_price_results = original_router
        runner.portfolio_module.build_shadow_portfolio_router_input = original_portfolio_input
        runner.price_module.verify_current_shadow_price_context = original_price_verify
        quote_binding.verify_current_shadow_price_context = original_quote_verify
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
