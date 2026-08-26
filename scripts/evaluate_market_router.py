"""Offline deterministic evaluator for ATHENA Market Router v1.

The CLI accepts a trusted local Python factory instead of free-form serialized
EV/edge records. The factory must return the exact builder-issued objects that
the authoritative Router requires. Network sockets are blocked while the
factory and Router execute.
"""
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

from domain._market_router_contracts import REAL_CURRENT_MARKET_ROUTER_STATUS
from domain.market_router import route_market_candidates


class OfflineRouterRunnerError(ValueError):
    pass


def _blocked_network(*_args: Any, **_kwargs: Any) -> None:
    raise OfflineRouterRunnerError("network access is disabled for offline Router evaluation")


@contextmanager
def _network_disabled():
    with patch.object(socket.socket, "connect", _blocked_network), patch.object(
        socket, "create_connection", _blocked_network
    ):
        yield


def _load_factory(specification: str):
    if type(specification) is not str or specification.count(":") != 1:
        raise OfflineRouterRunnerError("factory must be MODULE:CALLABLE")
    module_name, callable_name = specification.split(":", 1)
    if not module_name or not callable_name:
        raise OfflineRouterRunnerError("factory must be MODULE:CALLABLE")
    module = importlib.import_module(module_name)
    factory = getattr(module, callable_name, None)
    if not callable(factory):
        raise OfflineRouterRunnerError("factory callable was not found")
    return factory


def _atomic_write(path: Path, payload: bytes, *, replace: bool) -> None:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not replace:
        raise OfflineRouterRunnerError("output exists; pass --replace to overwrite")
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_factory(factory_specification: str):
    factory = _load_factory(factory_specification)
    with _network_disabled():
        values = factory()
        if not isinstance(values, Mapping):
            raise OfflineRouterRunnerError("factory must return a mapping")
        required = {"candidates", "quotes", "fixture_state", "evaluation_time"}
        if set(values) != required:
            raise OfflineRouterRunnerError(
                "factory mapping keys must be exactly candidates, quotes, fixture_state, evaluation_time"
            )
        return route_market_candidates(
            values["candidates"],
            values["quotes"],
            fixture_state=values["fixture_state"],
            evaluation_time=values["evaluation_time"],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--factory",
        required=True,
        help="trusted local MODULE:CALLABLE returning exact Router input objects",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    arguments = parser.parse_args()
    decision = run_factory(arguments.factory)
    report = {
        "real_current_market_router_status": REAL_CURRENT_MARKET_ROUTER_STATUS,
        "decision": decision.to_dict(),
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
