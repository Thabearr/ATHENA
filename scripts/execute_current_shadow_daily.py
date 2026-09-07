#!/usr/bin/env python3
"""Run the reviewed current Shadow chain for a user-facing daily/on-demand request.

This wrapper changes no football, pricing, Router, Portfolio, provider, freshness,
or authority semantics. It only makes the reviewed fixture search horizon an
explicit user-facing request:

* ``today`` -> current UTC fixture date only;
* ``three-day`` -> the existing PR-F three-date research horizon;
* ``--fixture-dates`` -> any 1..7 unique UTC dates inside today..today+6.

Requested accumulator size remains a target and is limited to the frozen 1..50
Portfolio contract. The wrapper preserves the PR-F 55-minute supervisor and
60-minute workflow cleanup margin.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

from domain import current_shadow_all_market_runner as runner
from domain.current_fotmob_fixture_candidate_adapter import (
    CurrentFotMobFixtureCandidateAdapterError,
)
from scripts import current_shadow_fixture_identity_reconciliation_recovery as identity_recovery
from scripts import current_shadow_history_artifact_verification_reuse as verification_reuse
from scripts import current_shadow_history_builder_audit_reuse as builder_audit_reuse
from scripts import current_shadow_history_semantic_replay_reuse as semantic_replay_reuse
from scripts import current_shadow_live_quote_row_local_replay as quote_replay
from scripts import execute_current_shadow_all_market as all_market_cli
from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound


WORKER_ENV = "ATHENA_CURRENT_SHADOW_DAILY_WORKER"
WORKER_MODULE = "scripts.execute_current_shadow_daily"
SCOPE_TODAY = "today"
SCOPE_THREE_DAY = "three-day"
SCOPE_DAY_COUNT = {
    SCOPE_TODAY: 1,
    SCOPE_THREE_DAY: 3,
}
MAX_REQUEST_DATE_COUNT = 7
HISTORY_VERIFICATION_DIAGNOSTIC_FILENAME = (
    "current-shadow-history-artifact-verification-diagnostic.json"
)
HISTORY_BUILDER_AUDIT_DIAGNOSTIC_FILENAME = (
    "current-shadow-history-builder-audit-reuse-diagnostic.json"
)
HISTORY_SEMANTIC_REPLAY_DIAGNOSTIC_FILENAME = (
    "current-shadow-history-semantic-replay-reuse-diagnostic.json"
)


def _target_size(value: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("target size must be an integer from 1 through 50") from exc
    if not 1 <= result <= 50:
        raise argparse.ArgumentTypeError("target size must be an integer from 1 through 50")
    return result


def _fixture_dates(value: str) -> tuple[str, ...]:
    if type(value) is not str or not value or value != value.strip():
        raise argparse.ArgumentTypeError(
            "fixture dates must be comma-separated YYYYMMDD values"
        )
    tokens = value.split(",")
    if not 1 <= len(tokens) <= MAX_REQUEST_DATE_COUNT:
        raise argparse.ArgumentTypeError("fixture dates must contain 1 through 7 dates")
    if len(set(tokens)) != len(tokens):
        raise argparse.ArgumentTypeError("fixture dates must be unique")

    today = runner._now().date()
    latest = today + timedelta(days=MAX_REQUEST_DATE_COUNT - 1)
    parsed: list[tuple[object, str]] = []
    for token in tokens:
        if len(token) != 8 or not token.isdigit():
            raise argparse.ArgumentTypeError(
                "fixture dates must be comma-separated YYYYMMDD values"
            )
        try:
            requested = datetime.strptime(token, "%Y%m%d").date()
        except ValueError as exc:
            raise argparse.ArgumentTypeError("fixture date is not a real UTC date") from exc
        if requested.strftime("%Y%m%d") != token:
            raise argparse.ArgumentTypeError("fixture date is not canonical YYYYMMDD")
        if requested < today or requested > latest:
            raise argparse.ArgumentTypeError(
                "fixture dates must be inside the rolling UTC today..today+6 window"
            )
        parsed.append((requested, token))
    return tuple(token for _date, token in sorted(parsed))


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
        "--fixture-dates",
        type=_fixture_dates,
        default=None,
        help="1..7 unique comma-separated UTC dates inside today..today+6",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    return parser


def _issue_exact_fixture_sources(
    *, repository_root: Path, request_dates: tuple[str, ...]
):
    attempted: list[str] = []
    sources: list[tuple[object, str]] = []
    for request_date in request_dates:
        attempted.append(request_date)
        try:
            execution = runner.current_fotmob_source.issue_current_shadow_fotmob_reviewed_source(
                request_date=request_date,
                timezone="UTC",
                ccode3="NGA",
                execute_live_network=True,
                repository_root=repository_root,
            )
        except runner.current_fotmob_source.CurrentFotMobReviewedSourceError as exc:
            if str(exc) == runner.current_fotmob_source.STATUS_NO_FIXTURES:
                continue
            raise
        sources.append((execution, request_date))
    if not sources:
        raise runner.CurrentShadowAllMarketRunnerError(
            "NO_POLICY_APPROVED_CURRENT_FOTMOB_FIXTURES_IN_REQUESTED_DATES:"
            + ",".join(attempted)
        )
    return tuple(sources), tuple(attempted)


def _finalize_source_adapter_failure(
    *,
    args: argparse.Namespace,
    exc: CurrentFotMobFixtureCandidateAdapterError,
):
    """Replace a provisional receipt when reviewed current source parsing fails closed."""

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    repository_root = Path(__file__).resolve().parents[1]
    exact_commit_sha = runner._git_head(repository_root)
    stage = runner._read_checkpoint_stage(output_dir)
    result = runner._receipt(
        status=runner.STATUS_SOURCE_INCOMPLETE,
        exact_commit_sha=exact_commit_sha,
        target_size=args.target_size,
        sources=None,
        portfolio=None,
        share_receipt=None,
        reasons=(f"SOURCE_CHAIN_FAILED:{runner._failure_chain(exc)}",),
        source_summary={
            "source_failure_stage": stage,
            "source_failure_type": type(exc).__name__,
            "wager_placed": False,
        },
    )
    runner._write(output_dir / runner.RUN_RECEIPT_FILENAME, result.to_dict())
    return result


def _execute_worker(args: argparse.Namespace) -> int:
    request_dates = args.fixture_dates
    day_count = (
        len(request_dates)
        if request_dates is not None
        else SCOPE_DAY_COUNT[args.fixture_scope]
    )
    original = runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    original_issuer = runner._issue_current_fixture_sources
    prior_all_market_worker = os.environ.get(all_market_cli.WORKER_ENV)
    identity_hooks = None
    quote_hook = None
    verification_hooks = None
    builder_audit_hooks = None
    semantic_replay_hooks = None
    runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT = day_count
    if request_dates is not None:
        runner._issue_current_fixture_sources = (
            lambda *, repository_root: _issue_exact_fixture_sources(
                repository_root=repository_root,
                request_dates=request_dates,
            )
        )
    # The daily wrapper calls the nested PR-F worker stack in-process rather than
    # entering execute_current_shadow_all_market.main(). Carry forward the exact
    # all-market worker marker that main() would have set so worker-only durable-
    # history acceleration is actually installed on the hosted daily/on-demand
    # path.
    os.environ[all_market_cli.WORKER_ENV] = "1"
    try:
        # Run #199 proved exact same-kickoff provider counterparts were being lost
        # at the V2 fixture-identity boundary. Install the Current Shadow V3
        # deterministic compatibility only inside this worker. It keeps full UTC,
        # home/away and stable provider IDs exact and binds the changed matching
        # basis into the reconciliation contract identity.
        identity_hooks = identity_recovery.install(runner.reconciliation)

        # One malformed provider market/outcome row must not poison an otherwise
        # valid direct event. The exact raw response and manifest remain unchanged;
        # the worker-local replay only omits the unusable row and is restored in
        # finally. All PR-B replay inside the worker sees the same row-local view.
        quote_hook = quote_replay.install()

        # The PR151 audit intentionally replays its exact captured bytes more than
        # once. Keep those reads and validations authoritative, but do not unzip
        # and hash the same immutable Actions artifact from scratch at every
        # replay boundary. This worker-local layer caches only successful exact
        # verifier outputs and writes non-authoritative progress diagnostics that
        # survive the outer supervisor if history still overruns its budget.
        verification_hooks = verification_reuse.install(
            runner.latest_history,
            diagnostic_path=(
                args.output_dir / HISTORY_VERIFICATION_DIAGNOSTIC_FILENAME
            ),
        )
        # The reviewed builder also performs the complete projected PR151 audit
        # once live and immediately replays that same just-recorded snapshot in
        # GitHubActionsLineageEvidenceBundle.__post_init__. Run #188 proved the
        # second projected audit remained inside CURRENT_DURABLE_FRESH_HISTORY
        # after exact artifact-verification reuse had already activated. Reuse
        # only the successful audit paired with the exact same-process immutable
        # payload objects issued by this builder; arbitrary evidence continues
        # through the untouched public replay.
        builder_audit_hooks = builder_audit_reuse.install(
            runner.latest_history,
            diagnostic_path=(
                args.output_dir / HISTORY_BUILDER_AUDIT_DIAGNOSTIC_FILENAME
            ),
        )
        # Run #189 proved that the artifact/digest verification and builder audit
        # layers had both finished roughly four minutes into the 55-minute worker,
        # while CURRENT_DURABLE_FRESH_HISTORY then consumed the rest of the budget.
        # The remaining hot path is PR245/PR244 semantic reconstruction: immutable
        # dataclass copies/canonical hashes repeatedly invoke the same expensive
        # frozen history ledger and current-shadow derivation. Preserve the first
        # reviewed execution for every exact semantic input, then reuse only that
        # successful frozen result for equivalent same-worker copies. The helper
        # also shares the date-invariant exact PR119+settlement ledger across the
        # current source dates. Arbitrary/changed inputs still execute the
        # untouched reviewed implementation and failures are never cached.
        semantic_replay_hooks = semantic_replay_reuse.install(
            runner.latest_history.prefix.shadow,
            diagnostic_path=(
                args.output_dir / HISTORY_SEMANTIC_REPLAY_DIAGNOSTIC_FILENAME
            ),
        )
        try:
            return bound._execute_worker(args)
        except CurrentFotMobFixtureCandidateAdapterError as exc:
            result = _finalize_source_adapter_failure(args=args, exc=exc)
            print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
            return 0
    finally:
        try:
            if semantic_replay_hooks is not None:
                semantic_replay_reuse.restore(
                    runner.latest_history.prefix.shadow,
                    semantic_replay_hooks,
                )
        finally:
            try:
                if builder_audit_hooks is not None:
                    builder_audit_reuse.restore(runner.latest_history, builder_audit_hooks)
            finally:
                try:
                    if verification_hooks is not None:
                        verification_reuse.restore(runner.latest_history, verification_hooks)
                finally:
                    try:
                        if quote_hook is not None:
                            quote_replay.restore(quote_hook)
                    finally:
                        try:
                            if identity_hooks is not None:
                                identity_recovery.restore(
                                    runner.reconciliation,
                                    identity_hooks,
                                )
                        finally:
                            # Restoration of request scope, issuer and exact worker
                            # marker must not depend on diagnostic I/O or cleanup.
                            runner._issue_current_fixture_sources = original_issuer
                            runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT = original
                            if prior_all_market_worker is None:
                                os.environ.pop(all_market_cli.WORKER_ENV, None)
                            else:
                                os.environ[all_market_cli.WORKER_ENV] = prior_all_market_worker


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
    ]
    if args.fixture_dates is None:
        command.extend(("--fixture-scope", args.fixture_scope))
    else:
        command.extend(("--fixture-dates", ",".join(args.fixture_dates)))
    command.extend(("--output-dir", str(args.output_dir)))
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
