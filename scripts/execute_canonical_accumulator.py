#!/usr/bin/env python3
"""Run the reviewed canonical ATHENA -> SportyBet accumulator workflow.

The factory is a reviewed repository module supplied as ``module:callable``.
It returns only source-bound ``CanonicalAccumulatorFixtureInput`` values and a
requested target size.  It cannot supply provider-native market/outcome IDs,
odds, quote timestamps, snapshot IDs, or a preselected slip.

This command performs anonymous share-code transport only.  It never logs in,
uses cookies, submits a stake, or places a wager.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import re
from typing import Any, Callable

from domain.canonical_accumulator_execution import (
    CanonicalAccumulatorExecutionError,
    CanonicalAccumulatorFixtureInput,
    execute_canonical_accumulator,
    validate_canonical_execution_contract,
    write_canonical_execution_failure_artifact,
)


_FACTORY_RE = re.compile(
    r"^(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*):"
    r"(?P<callable>[A-Za-z_][A-Za-z0-9_]*)$",
    re.ASCII,
)
_REQUEST_KEYS = frozenset({"fixture_inputs", "target_size"})


class CanonicalAccumulatorRunnerError(ValueError):
    """Raised when a trusted factory does not return the runner contract."""


def _load_factory(specification: str) -> Callable[[], Any]:
    match = _FACTORY_RE.fullmatch(specification)
    if match is None:
        raise CanonicalAccumulatorRunnerError(
            "factory must use a trusted module:callable specification"
        )
    try:
        module = importlib.import_module(match.group("module"))
        factory = getattr(module, match.group("callable"))
    except (ImportError, AttributeError) as exc:
        raise CanonicalAccumulatorRunnerError("trusted factory could not be loaded") from exc
    if not callable(factory):
        raise CanonicalAccumulatorRunnerError("trusted factory is not callable")
    return factory


def _factory_request(factory: Callable[[], Any]) -> tuple[tuple[CanonicalAccumulatorFixtureInput, ...], int]:
    try:
        request = factory()
    except Exception as exc:  # Factory errors are converted into a no-code CLI failure.
        raise CanonicalAccumulatorRunnerError("trusted factory execution failed") from exc
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        raise CanonicalAccumulatorRunnerError(
            "factory must return exactly fixture_inputs and target_size"
        )
    fixture_inputs = request["fixture_inputs"]
    target_size = request["target_size"]
    if type(fixture_inputs) is not tuple or any(
        type(item) is not CanonicalAccumulatorFixtureInput for item in fixture_inputs
    ):
        raise CanonicalAccumulatorRunnerError(
            "factory fixture_inputs must be an exact tuple of source-bound inputs"
        )
    if isinstance(target_size, bool) or not isinstance(target_size, int) or target_size < 1:
        raise CanonicalAccumulatorRunnerError(
            "factory target_size must be a positive integer"
        )
    return fixture_inputs, target_size


def _summary(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "requested_fold_count": result.requested_fold_count,
        "final_qualified_fold_count": result.final_qualified_fold_count,
        "shortfall": result.shortfall,
        "shareCode": result.share_code,
        "shareURL": result.share_url,
        "combined_odds": result.combined_odds,
        "wager_placed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute the canonical source-bound ATHENA SportyBet workflow"
    )
    parser.add_argument(
        "--factory",
        required=True,
        help="reviewed repository factory as module:callable",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-lead-seconds", type=int, default=120)
    parser.add_argument("--delay-seconds", type=float, default=0.25)
    args = parser.parse_args(argv)

    contract = None
    target_size = 0
    try:
        contract = validate_canonical_execution_contract()
        fixture_inputs, target_size = _factory_request(_load_factory(args.factory))
        result = execute_canonical_accumulator(
            fixture_inputs,
            target_size=target_size,
            output_dir=args.output_dir,
            minimum_lead_seconds=args.minimum_lead_seconds,
            delay_seconds=args.delay_seconds,
        )
    except (
        CanonicalAccumulatorExecutionError,
        CanonicalAccumulatorRunnerError,
        TypeError,
        ValueError,
    ) as exc:
        if contract is not None:
            try:
                payload = write_canonical_execution_failure_artifact(
                    output_dir=args.output_dir,
                    contract_sha256=contract[
                        "canonical_execution_contract_sha256"
                    ],
                    evaluation_time=datetime.now(timezone.utc),
                    requested_fold_count=target_size,
                    error=str(exc),
                )
            except (OSError, CanonicalAccumulatorExecutionError):
                payload = {
                    "status": "NO_CODE_EXECUTION_ERROR",
                    "wager_placed": False,
                }
        else:
            payload = {
                "status": "NO_CODE_EXECUTION_ERROR",
                "wager_placed": False,
            }
        print(json.dumps(payload, sort_keys=True))
        return 2

    print(json.dumps(_summary(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
