"""Transparent one-shot transport for reviewed FotMob source-route probes."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import dataclasses
import datetime
import http.client
import sys
from typing import Any, Callable

from domain.fotmob_source_probe import (
    ALLOWED_HOST,
    HTTPS_PORT,
    MAX_SAMPLE_BYTES,
    FotMobProbeRoute,
    FotMobSourceProbeError,
    FotMobSourceProbeReceipt,
    ProbeTransportOutcome,
    build_response_receipt,
    build_transport_error_receipt,
    canonical_source_probe_bytes,
    request_headers_for_route,
    request_target_for_route,
    validate_probe_date,
)


REQUEST_TIMEOUT_SECONDS = 30


@dataclasses.dataclass(frozen=True)
class _ProbeExecution:
    receipt: FotMobSourceProbeReceipt
    operator_error: str | None


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bounded_error(error: BaseException) -> str:
    return type(error).__name__[:80]


def _parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit():
        raise FotMobSourceProbeError("Content-Length must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobSourceProbeError("Content-Length is invalid") from exc
    if parsed < 0:
        raise FotMobSourceProbeError("Content-Length must not be negative")
    return parsed


def _observed(clock: Callable[[], datetime.datetime]) -> datetime.datetime:
    try:
        value = clock()
        if not isinstance(value, datetime.datetime):
            raise FotMobSourceProbeError("probe clock must return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobSourceProbeError("probe clock must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobSourceProbeError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobSourceProbeError("probe clock returned an invalid value") from exc


def probe_fotmob_source(
    *,
    request_date: str,
    route: FotMobProbeRoute,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> _ProbeExecution:
    """Issue exactly one request for one fixed route and build a diagnostic receipt."""

    date = validate_probe_date(request_date)
    if not isinstance(route, FotMobProbeRoute):
        raise FotMobSourceProbeError("route must be FotMobProbeRoute")
    target = request_target_for_route(route, date)
    connection = None
    response_received = False
    try:
        connection = connection_factory(
            ALLOWED_HOST,
            HTTPS_PORT,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        connection.putrequest("GET", target, skip_accept_encoding=True)
        for name, value in request_headers_for_route(route):
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        response_received = True
        status = getattr(response, "status", None)
        if type(status) is not int or not 100 <= status <= 599:
            raise FotMobSourceProbeError("HTTP response status is invalid")
        content_type = response.getheader("Content-Type")
        content_length = _parse_content_length(response.getheader("Content-Length"))
        location = response.getheader("Location")
        sample = response.read(MAX_SAMPLE_BYTES)
        if type(sample) is not bytes:
            raise FotMobSourceProbeError("HTTP response sample must be exact bytes")
        observed_at = _observed(clock)
        receipt = build_response_receipt(
            route=route,
            request_date=date,
            status_code=status,
            content_type=content_type,
            content_length=content_length,
            location=location,
            observed_at=observed_at,
            sample=sample,
        )
        return _ProbeExecution(receipt=receipt, operator_error=None)
    except FotMobSourceProbeError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        if response_received:
            raise FotMobSourceProbeError(
                f"response sampling failed: {_bounded_error(exc)}"
            ) from exc
        receipt = build_transport_error_receipt(
            route=route,
            request_date=date,
            observed_at=_observed(clock),
        )
        return _ProbeExecution(
            receipt=receipt,
            operator_error=f"transport error: {_bounded_error(exc)}",
        )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobSourceProbeError(
            f"probe response handling failed: {_bounded_error(exc)}"
        ) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe exactly one reviewed public FotMob route with a transparent "
            "ATHENA request profile."
        )
    )
    parser.add_argument("--date", required=True, help="Exact Gregorian YYYYMMDD date")
    parser.add_argument(
        "--route",
        required=True,
        choices=tuple(route.value for route in FotMobProbeRoute),
        help="One fixed route per invocation",
    )
    parser.add_argument(
        "--execute-live-network",
        action="store_true",
        help="Authorize exactly one transparent diagnostic HTTPS request",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.execute_live_network:
        parser.error(
            "network probing is disabled; supply --execute-live-network for one route"
        )
    try:
        execution = probe_fotmob_source(
            request_date=args.date,
            route=FotMobProbeRoute(args.route),
            connection_factory=connection_factory,
            clock=clock,
        )
        sys.stdout.buffer.write(canonical_source_probe_bytes(execution.receipt))
        sys.stdout.buffer.flush()
        if execution.operator_error is not None:
            print(execution.operator_error, file=sys.stderr)
        return (
            0
            if execution.receipt.transport_outcome
            is ProbeTransportOutcome.RESPONSE_RECEIVED
            else 1
        )
    except FotMobSourceProbeError as exc:
        parser.exit(1, f"probe failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
