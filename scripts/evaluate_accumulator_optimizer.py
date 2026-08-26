"""Offline deterministic evaluator for ATHENA Accumulator Optimizer v2."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import socket
from typing import Any, Mapping
from unittest.mock import patch

from domain._accumulator_optimizer_contracts import (
    REAL_CURRENT_ACCUMULATOR_OPTIMIZER_STATUS,
)
from domain.accumulator_optimizer import optimize_accumulator


class OfflineAccumulatorOptimizerError(ValueError):
    pass


def _blocked_network(*_args: Any, **_kwargs: Any) -> None:
    raise OfflineAccumulatorOptimizerError(
        "network access is disabled for offline Accumulator Optimizer evaluation"
    )


@contextmanager
def _network_disabled():
    with patch.object(socket.socket, "connect", _blocked_network), patch.object(
        socket, "create_connection", _blocked_network
    ):
        yield


def _load_factory(specification: str):
    if type(specification) is not str or specification.count(":") != 1:
        raise OfflineAccumulatorOptimizerError("factory must be MODULE:CALLABLE")
    module_name, callable_name = specification.split(":", 1)
    if not module_name or not callable_name:
        raise OfflineAccumulatorOptimizerError("factory must be MODULE:CALLABLE")
    module = importlib.import_module(module_name)
    factory = getattr(module, callable_name, None)
    if not callable(factory):
        raise OfflineAccumulatorOptimizerError("factory callable was not found")
    return factory


def _atomic_write(path: Path, payload: bytes, *, replace: bool) -> None:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not replace:
        raise OfflineAccumulatorOptimizerError("output exists; pass --replace to overwrite")
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    if temporary == target:
        raise OfflineAccumulatorOptimizerError("temporary/output path collision")
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def run_factory(factory_specification: str):
    # The network guard intentionally starts BEFORE the supplied module import.
    with _network_disabled():
        factory = _load_factory(factory_specification)
        values = factory()
        if not isinstance(values, Mapping):
            raise OfflineAccumulatorOptimizerError("factory must return a mapping")
        required = {"fixture_inputs", "target_size", "evaluation_time"}
        if set(values) != required:
            raise OfflineAccumulatorOptimizerError(
                "factory mapping keys must be exactly fixture_inputs, target_size, evaluation_time"
            )
        return optimize_accumulator(
            values["fixture_inputs"],
            target_size=values["target_size"],
            evaluation_time=values["evaluation_time"],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--factory",
        required=True,
        help="trusted local MODULE:CALLABLE returning exact Phase 9 input objects",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    arguments = parser.parse_args()
    optimization = run_factory(arguments.factory)
    report = {
        "real_current_accumulator_optimizer_status": (
            REAL_CURRENT_ACCUMULATOR_OPTIMIZER_STATUS
        ),
        "optimization": optimization.to_dict(),
    }
    payload = (
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_write(arguments.output, payload, replace=arguments.replace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
