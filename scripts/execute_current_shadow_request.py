#!/usr/bin/env python3
"""Execute Current Shadow for legacy scopes or explicit rolling seven-day dates.

The wrapper keeps the reviewed daily supervisor/worker behavior while adding two
research-only compatibility boundaries proven necessary by run #199:

* exact explicit UTC fixture dates (any 1..7 unique dates in today..today+6);
* evidence-bound Current Shadow reconciliation recovery for retained run-199
  team/competition display drift and row-local malformed provider quote rows.

It does not alter the frozen holdout, Router/Portfolio authority, provider prices,
login/wallet/stake behavior, or the wager invariant.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_date_request as fixture_dates
from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as reconciliation
from domain import current_shadow_sportybet_tolerant_live_inventory as tolerant_inventory
from domain import sportybet_current_event_discovery_reconciliation as reviewed
from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound
from scripts import execute_current_shadow_daily as daily


WORKER_ENV = "ATHENA_CURRENT_SHADOW_REQUEST_WORKER"
WORKER_MODULE = "scripts.execute_current_shadow_request"
REQUEST_POLICY_FILENAME = "current-shadow-request-policy.json"


def _fixture_dates(value: str) -> tuple[str, ...]:
    try:
        return fixture_dates.parse_fixture_dates_text(value)
    except fixture_dates.CurrentShadowFixtureDateRequestError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=daily._target_size, required=True)
    parser.add_argument(
        "--fixture-scope",
        choices=tuple(daily.SCOPE_DAY_COUNT),
        default=daily.SCOPE_TODAY,
    )
    parser.add_argument(
        "--fixture-dates",
        type=_fixture_dates,
        default=None,
        help="comma-separated UTC YYYYMMDD dates; 1..7 unique dates in today..today+6",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    return parser


def _selected_source_issuer(selected_dates: tuple[str, ...]):
    def issue(*, repository_root: Path):
        try:
            request_dates = fixture_dates.validate_fixture_dates(
                selected_dates,
                current_utc=runner._now(),
            )
        except fixture_dates.CurrentShadowFixtureDateRequestError as exc:
            raise runner.CurrentShadowAllMarketRunnerError(str(exc)) from exc

        attempted: list[str] = []
        sources: list[tuple[Any, str]] = []
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

    return issue


def _detail_inventory(directory: Path, *, repository_root: Path):
    try:
        return tolerant_inventory.build_shadow_live_event_quote_inventory(
            directory,
            repository_root=repository_root,
        )
    except tolerant_inventory.live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise reviewed.SportyBetCurrentEventDiscoveryError(str(exc)) from exc


def _install_reconciliation_compatibility() -> tuple[Any, dict[str, Any]]:
    proxy = reconciliation.legacy.reviewed
    previous = dict(getattr(proxy, "__dict__", {}))
    proxy._match_event = run199_identity.match_event
    proxy._detail_inventory_from_directory = _detail_inventory
    return proxy, previous


def _restore_reconciliation_compatibility(proxy: Any, previous: dict[str, Any]) -> None:
    current = getattr(proxy, "__dict__", {})
    for key in tuple(current):
        if key not in previous:
            try:
                delattr(proxy, key)
            except AttributeError:
                pass
    for key, value in previous.items():
        setattr(proxy, key, value)


def _write_request_policy(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected = None
    if args.fixture_dates is not None:
        selected = list(
            fixture_dates.validate_fixture_dates(
                args.fixture_dates,
                current_utc=runner._now(),
            )
        )
    runner._write(
        args.output_dir / REQUEST_POLICY_FILENAME,
        {
            "schema_version": 1,
            "dataset_name": "athena-current-shadow-request-policy-v1",
            "fixture_scope": args.fixture_scope,
            "fixture_dates": selected,
            "rolling_date_policy": fixture_dates.policy_summary(),
            "run199_identity_policy_id": run199_identity.POLICY_ID,
            "run199_identity_policy_sha256": run199_identity.POLICY_SHA256,
            "row_local_quote_policy": tolerant_inventory.policy_summary(),
            "authority": {
                "research_shadow_request": True,
                "production_model": False,
                "pricing": False,
                "selection": False,
                "sportybet_execution": False,
                "bet": False,
                "wager_placed": False,
            },
            "wager_placed": False,
        },
    )


def _execute_worker(args: argparse.Namespace) -> int:
    original_issuer = runner._issue_current_fixture_sources
    original_scope_count = daily.SCOPE_DAY_COUNT[args.fixture_scope]
    proxy, previous_proxy = _install_reconciliation_compatibility()
    if args.fixture_dates is not None:
        validated_dates = fixture_dates.validate_fixture_dates(
            args.fixture_dates,
            current_utc=runner._now(),
        )
        runner._issue_current_fixture_sources = _selected_source_issuer(validated_dates)
        # The reviewed daily worker copies the scope's day count into the runner
        # for receipt/progress diagnostics.  Bind that diagnostic count to the
        # exact explicit request while the custom issuer supplies the actual
        # non-contiguous dates, then restore the legacy scope unconditionally.
        daily.SCOPE_DAY_COUNT[args.fixture_scope] = len(validated_dates)
    _write_request_policy(args)
    try:
        daily_args = argparse.Namespace(
            target_size=args.target_size,
            fixture_scope=args.fixture_scope,
            output_dir=args.output_dir,
        )
        return daily._execute_worker(daily_args)
    finally:
        daily.SCOPE_DAY_COUNT[args.fixture_scope] = original_scope_count
        runner._issue_current_fixture_sources = original_issuer
        _restore_reconciliation_compatibility(proxy, previous_proxy)


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
    if args.fixture_dates is not None:
        command.extend(("--fixture-dates", ",".join(args.fixture_dates)))
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
