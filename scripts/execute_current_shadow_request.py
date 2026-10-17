#!/usr/bin/env python3
"""Execute Current Shadow for legacy scopes or explicit rolling seven-day dates.

The wrapper keeps the reviewed daily supervisor/worker behavior while adding
research-only compatibility boundaries proven necessary by run #199:

* exact explicit UTC fixture dates (any 1..7 unique dates in today..today+6);
* evidence-bound Current Shadow reconciliation recovery for retained run-199
  team/competition display drift and row-local malformed provider quote rows;
* a reviewed Elo-only current-as-of xG fallback when the full five-feature model
  is incomplete because form/fatigue remain correctly missing.

It does not alter the frozen holdout, impute missing features, broaden historical
feature scope, change Router/Portfolio authority or provider prices, or touch
login/wallet/stake behavior or the wager invariant.
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
from domain import current_shadow_sportybet_upcoming_reconciliation as reconciliation
from domain import current_shadow_sportybet_tolerant_live_inventory as tolerant_inventory
from domain import sportybet_current_event_discovery_reconciliation as reviewed
from scripts import current_shadow_current_asof_elo_only_fallback as xg_fallback
from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound
from scripts import execute_current_shadow_daily as daily


WORKER_ENV = "ATHENA_CURRENT_SHADOW_REQUEST_WORKER"
WORKER_MODULE = "scripts.execute_current_shadow_request"
REQUEST_POLICY_FILENAME = "current-shadow-request-policy.json"
XG_DIAGNOSTIC_FILENAME = "current-shadow-current-asof-xg-diagnostic.json"
PRODUCT_CONTEXT_ARGUMENT = "--product-context-file"
STANDALONE_RESEARCH_WORKER_ARGUMENT = "--standalone-research-worker"


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
        "--create-share-code",
        type=runner.parse_create_share_code_text,
        default=runner.LEGACY_CREATE_SHARE_CODE_DEFAULT,
        metavar="true|false",
        help="explicit delivery intent; omission preserves legacy delivery-enabled behavior",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    parser.add_argument(
        PRODUCT_CONTEXT_ARGUMENT,
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        STANDALONE_RESEARCH_WORKER_ARGUMENT,
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )
    return parser


def _selected_source_issuer(selected_dates: tuple[str, ...]):
    def issue(*, repository_root: Path, execute_live_network: bool = True):
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
                    execute_live_network=execute_live_network,
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
    if hasattr(reconciliation, "legacy"):
        proxy = reconciliation.legacy.reviewed
        previous = dict(getattr(proxy, "__dict__", {}))
        proxy._match_event = run199_identity.match_event
        proxy._detail_inventory_from_directory = _detail_inventory
        return proxy, previous
    return None, {}


def _restore_reconciliation_compatibility(proxy: Any, previous: dict[str, Any]) -> None:
    if proxy is None:
        return
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
            "create_share_code": args.create_share_code,
            "fixture_scope": args.fixture_scope,
            "fixture_dates": selected,
            "rolling_date_policy": fixture_dates.policy_summary(),
            "run199_identity_policy_id": run199_identity.POLICY_ID,
            "run199_identity_policy_sha256": run199_identity.POLICY_SHA256,
            "row_local_quote_policy": tolerant_inventory.policy_summary(),
            "current_asof_elo_only_policy": xg_fallback.policy_summary(),
            "authority": {
                "research_shadow_request": True,
                "research_anonymous_share_code_generation": args.create_share_code,
                "provider_create_reload_verification": args.create_share_code,
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


def _write_xg_diagnostic(args: argparse.Namespace) -> bool:
    """Persist bounded model-readiness evidence without making it run authority."""

    try:
        runner._write(
            args.output_dir / XG_DIAGNOSTIC_FILENAME,
            xg_fallback.diagnostic_summary(),
        )
    except (OSError, TypeError, ValueError, runner.CurrentShadowAllMarketRunnerError):
        return False
    return True


def _execute_worker(args: argparse.Namespace, *, product_authority: Any = None) -> int:
    original_issuer = runner._issue_current_fixture_sources
    original_scope_count = daily.SCOPE_DAY_COUNT[args.fixture_scope]
    proxy = None
    previous_proxy = None
    xg_hooks = None
    try:
        proxy, previous_proxy = _install_reconciliation_compatibility()
        xg_hooks = xg_fallback.install()
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
        daily_args = argparse.Namespace(
            target_size=args.target_size,
            fixture_scope=args.fixture_scope,
            output_dir=args.output_dir,
            create_share_code=args.create_share_code,
        )
        try:
            return daily._execute_worker(daily_args)
        finally:
            _write_xg_diagnostic(args)
    finally:
        try:
            if xg_hooks is not None:
                xg_fallback.restore(xg_hooks)
        finally:
            daily.SCOPE_DAY_COUNT[args.fixture_scope] = original_scope_count
            runner._issue_current_fixture_sources = original_issuer
            if proxy is not None and previous_proxy is not None:
                _restore_reconciliation_compatibility(proxy, previous_proxy)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    worker_selected = os.environ.get(WORKER_ENV) == "1"
    if args.product_context_file is not None:
        if not worker_selected or args.standalone_research_worker:
            raise RuntimeError("product context requires the fixed product child selector")
        authority = _authenticate_product_child(args)
        from runtime.current_shadow_operation_authority import (
            install_product_authority, reset_product_authority,
        )
        token = install_product_authority(authority)
        try:
            return _execute_worker(args, product_authority=authority)
        finally:
            reset_product_authority(token)
    if worker_selected:
        if not args.standalone_research_worker:
            raise RuntimeError(
                "nested worker selector requires authenticated product context or explicit standalone intent"
            )
        return _execute_worker(args)
    if args.standalone_research_worker:
        raise RuntimeError("standalone worker intent is valid only at the fixed wrapper boundary")

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
        "--create-share-code",
        runner.create_share_code_cli_text(args.create_share_code),
        STANDALONE_RESEARCH_WORKER_ARGUMENT,
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
            create_share_code=args.create_share_code,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    return completed.returncode


def _authenticate_product_child(args: argparse.Namespace):
    """Consume the one-use parent pipe and authenticate the nested worker."""
    from runtime.current_shadow_operation_authority import (
        CurrentShadowOperationAuthority, ProductOperationAuthorityError,
        context_path, read_context,
    )
    from runtime.release_identity import verify_development_checkout
    from runtime.resources import ResourceResolver
    from runtime.worker_entry import _read_command_file
    from runtime.worker_launcher import read_bound_request
    from runtime.worker_startup_gate import read_gate_document, _data_root_from_path
    from database.run_repository import DurableRunRepository

    try:
        # Do not inspect or use the capability until the owner commits the
        # exact child PID/context event and releases this one-byte pipe.
        ready = sys.stdin.buffer.read(1)
        if ready != b"\x01" or sys.stdin.buffer.read(1) != b"":
            raise ProductOperationAuthorityError("nested supervisor handshake is missing or replayed")
        command_path = args.product_context_file.parent / "athena-worker-command.json"
        command, _ = _read_command_file(command_path)
        if args.product_context_file != context_path(command):
            raise ProductOperationAuthorityError("product context selector is not the fixed run path")
        if command.release_identity_kind != "DEVELOPMENT_CHECKOUT":
            raise ProductOperationAuthorityError("Current Shadow product child requires the admitted source release")
        identity = verify_development_checkout(Path(__file__).resolve().parents[1])
        if identity.head_commit_sha != command.release_identity_id:
            raise ProductOperationAuthorityError("nested Current Shadow source release changed")
        resources = ResourceResolver.for_development(identity)
        request = read_bound_request(command)
        context, context_bytes = read_context(args.product_context_file, command=command)
        gate, gate_bytes = read_gate_document(
            command.run_directory / "athena-worker-startup-gate.json"
        )
        data_root = _data_root_from_path(command.run_directory)
        repository = DurableRunRepository.for_worker_data_root(resources, data_root)
        expected_dates = tuple(day.strftime("%Y%m%d") for day in request.dates)
        if (command.operation != "CURRENT_SHADOW_REQUEST"
                or request.authority_profile != "SHADOW"
                or request.mode != "research_shadow"
                or request.create_share_code is not False or request.place_wager is not False
                or args.target_size != request.target_legs
                or args.fixture_scope != daily.SCOPE_TODAY
                or args.fixture_dates != expected_dates
                or args.output_dir != command.run_directory / "current-shadow"
                or args.create_share_code is not False):
            raise ProductOperationAuthorityError("nested supervisor arguments differ from the admitted request")
        return CurrentShadowOperationAuthority._from_authenticated_child(
            repository=repository, command=command, gate=gate,
            gate_bytes=gate_bytes, context=context, context_bytes=context_bytes,
        )
    except Exception as exc:
        raise RuntimeError("nested Current Shadow context authentication failed") from exc


def _launch_product_child(args: argparse.Namespace, context_file: Path):
    """Launch only this fixed worker module with its stdin authority gate closed."""
    env = dict(os.environ)
    env[WORKER_ENV] = "1"
    command = [
        sys.executable, "-m", WORKER_MODULE,
        "--target-size", str(args.target_size),
        "--fixture-scope", args.fixture_scope,
        "--fixture-dates", ",".join(args.fixture_dates),
        "--output-dir", os.fspath(args.output_dir),
        "--create-share-code", "false",
        PRODUCT_CONTEXT_ARGUMENT, os.fspath(context_file),
    ]
    return subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=None,
        stderr=None,
        text=True,
    )


def run_authenticated_product_worker(
    argv: list[str], *, repository: Any, command: Any,
    gate: dict[str, Any], gate_bytes: bytes,
) -> int:
    """Keep the existing bounded 75-minute supervisor under a DB start fence."""
    from runtime.current_shadow_operation_authority import worker_executable_identity

    args = build_parser().parse_args(argv)
    if (args.product_context_file is not None or args.create_share_code is not False
            or args.fixture_dates is None):
        raise RuntimeError("authenticated product supervisor arguments are outside policy")
    executable_path, executable_sha256 = worker_executable_identity()
    process = repository.launch_current_shadow_supervisor(
        command=command, gate=gate, gate_bytes=gate_bytes,
        launch=lambda context_file: _launch_product_child(args, context_file),
        worker_executable_path=executable_path,
        worker_executable_sha256=executable_sha256,
    )
    try:
        process.stdin.write("\x01")
        process.stdin.flush()
        process.stdin.close()
    except (BrokenPipeError, OSError) as exc:
        try:
            process.kill()
            process.communicate(timeout=5)
        except Exception:
            pass
        raise RuntimeError("authenticated nested supervisor handshake failed") from exc
    try:
        process.wait(timeout=bound._supervisor_timeout_seconds())
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        result = bound._write_timeout_receipt(
            target_size=args.target_size,
            output_dir=args.output_dir,
            create_share_code=False,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
