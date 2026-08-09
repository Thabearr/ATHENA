"""Transparent one-shot transport for FotMob's reviewed data-matches route."""

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

from domain.fotmob_data_matches_probe import (
    ALLOWED_HOST,
    HTTPS_PORT,
    MAX_SAMPLE_BYTES,
    FotMobDataMatchesProbeError,
    FotMobDataMatchesProbeReceipt,
    ProbeTransportOutcome,
    build_response_receipt,
    build_transport_error_receipt,
    canonical_data_matches_probe_receipt_bytes,
    request_headers,
    request_target,
    validate_ccode3,
    validate_request_date,
    validate_timezone,
)


REQUEST_TIMEOUT_SECONDS = 30


@dataclasses.dataclass(frozen=True)
class _ProbeExecution:
    receipt: FotMobDataMatchesProbeReceipt
    operator_error: str | None


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bounded_error(error: BaseException) -> str:
    return type(error).__name__[:80]


def _parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdigit()
    ):
        raise FotMobDataMatchesProbeError(
            "Content-Length must be a non-negative integer"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesProbeError("Content-Length is invalid") from exc
    if parsed < 0:
        raise FotMobDataMatchesProbeError("Content-Length must not be negative")
    return parsed


def _observed(clock: Callable[[], datetime.datetime]) -> datetime.datetime:
    try:
        value = clock()
        if not isinstance(value, datetime.datetime):
            raise FotMobDataMatchesProbeError(
                "probe clock must return a datetime"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobDataMatchesProbeError(
                "probe clock must be timezone-aware"
            )
        return value.astimezone(datetime.timezone.utc)
    except FotMobDataMatchesProbeError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesProbeError(
            "probe clock returned an invalid value"
        ) from exc


def probe_fotmob_data_matches(
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> _ProbeExecution:
    """Issue exactly one unsigned request and return diagnostic metadata."""

    date = validate_request_date(request_date)
    zone = validate_timezone(timezone)
    country = validate_ccode3(ccode3)
    target = request_target(date, zone, country)
    connection = None
    response_received = False
    try:
        connection = connection_factory(
            ALLOWED_HOST,
            HTTPS_PORT,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        connection.putrequest("GET", target, skip_accept_encoding=True)
        for name, value in request_headers():
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        response_received = True
        status = getattr(response, "status", None)
        if type(status) is not int or not 100 <= status <= 599:
            raise FotMobDataMatchesProbeError("HTTP response status is invalid")
        content_type = response.getheader("Content-Type")
        content_length = _parse_content_length(
            response.getheader("Content-Length")
        )
        location = response.getheader("Location")
        sample = response.read(MAX_SAMPLE_BYTES)
        if type(sample) is not bytes:
            raise FotMobDataMatchesProbeError(
                "HTTP response sample must be exact bytes"
            )
        receipt = build_response_receipt(
            request_date=date,
            timezone=zone,
            ccode3=country,
            status_code=status,
            content_type=content_type,
            content_length=content_length,
            location=location,
            observed_at=_observed(clock),
            sample=sample,
        )
        return _ProbeExecution(receipt=receipt, operator_error=None)
    except FotMobDataMatchesProbeError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        if response_received:
            raise FotMobDataMatchesProbeError(
                f"response sampling failed: {_bounded_error(exc)}"
            ) from exc
        return _ProbeExecution(
            receipt=build_transport_error_receipt(
                request_date=date,
                timezone=zone,
                ccode3=country,
                observed_at=_observed(clock),
            ),
            operator_error=f"transport error: {_bounded_error(exc)}",
        )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesProbeError(
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
            "Probe the fixed FotMob /api/data/matches route once using an "
            "unsigned, transparent ATHENA request."
        )
    )
    parser.add_argument("--date", required=True, help="Exact Gregorian YYYYMMDD date")
    parser.add_argument(
        "--timezone",
        required=True,
        help="Explicit reviewed UTC or IANA-style timezone",
    )
    parser.add_argument(
        "--ccode3",
        required=True,
        help="Exact three-letter uppercase country code",
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
            "network probing is disabled; supply --execute-live-network for one request"
        )
    try:
        execution = probe_fotmob_data_matches(
            request_date=args.date,
            timezone=args.timezone,
            ccode3=args.ccode3,
            connection_factory=connection_factory,
            clock=clock,
        )
        sys.stdout.buffer.write(
            canonical_data_matches_probe_receipt_bytes(execution.receipt)
        )
        sys.stdout.buffer.flush()
        if execution.operator_error is not None:
            print(execution.operator_error, file=sys.stderr)
        return (
            0
            if execution.receipt.transport_outcome
            is ProbeTransportOutcome.RESPONSE_RECEIVED
            else 1
        )
    except FotMobDataMatchesProbeError as exc:
        parser.exit(1, f"probe failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
