"""Transparent one-shot transport for the reviewed FotMob match-details probe.

This module intentionally exposes an importable operator boundary rather than a
standalone CLI: PR #49 does not introduce a parser for persisted PR #48 Python
objects. A caller must already hold the exact in-memory PR #48 object and its
canonical receipt bytes, then explicitly authorize one diagnostic request.
"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import dataclasses
import datetime
import http.client
from typing import Any, Callable

from domain.fotmob_reviewed_match_details_probe import (
    ALLOWED_HOST,
    HTTPS_PORT,
    MAX_SAMPLE_BYTES,
    FotMobReviewedMatchDetailsProbeError,
    FotMobReviewedMatchDetailsProbeReceipt,
    build_match_details_probe_plan,
    build_response_receipt,
    build_transport_error_receipt,
)

REQUEST_TIMEOUT_SECONDS = 30


@dataclasses.dataclass(frozen=True)
class ProbeExecution:
    receipt: FotMobReviewedMatchDetailsProbeReceipt
    operator_error: str | None


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bounded_error(error: BaseException) -> str:
    return type(error).__name__[:80]


def _observed(clock: Callable[[], datetime.datetime], label: str) -> datetime.datetime:
    try:
        value = clock()
        if not isinstance(value, datetime.datetime):
            raise FotMobReviewedMatchDetailsProbeError(
                f"{label} clock value must be a datetime"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobReviewedMatchDetailsProbeError(
                f"{label} clock value must be timezone-aware"
            )
        return value.astimezone(datetime.timezone.utc)
    except FotMobReviewedMatchDetailsProbeError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsProbeError(
            f"{label} clock value is invalid"
        ) from exc


def _parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not str or not value or not value.isascii() or not value.isdigit():
        raise FotMobReviewedMatchDetailsProbeError(
            "Content-Length must be a non-negative ASCII integer"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsProbeError(
            "Content-Length is invalid"
        ) from exc
    if parsed < 0:
        raise FotMobReviewedMatchDetailsProbeError(
            "Content-Length must not be negative"
        )
    return parsed


def probe_fotmob_reviewed_match_details(
    *,
    verified_bootstrap_artifact: Any,
    verification_receipt_bytes: Any,
    fixture_identifier: Any,
    execute_live_network: Any,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> ProbeExecution:
    """Issue at most one transparent request for one exact reviewed fixture."""

    if type(execute_live_network) is not bool or execute_live_network is not True:
        raise FotMobReviewedMatchDetailsProbeError(
            "one diagnostic network request requires exact execute_live_network=True"
        )

    request_started_at = _observed(clock, "request_started_at")
    plan = build_match_details_probe_plan(
        verified_bootstrap_artifact,
        verification_receipt_bytes,
        fixture_identifier=fixture_identifier,
        request_started_at=request_started_at,
    )

    connection = None
    response_received = False
    try:
        connection = connection_factory(
            ALLOWED_HOST,
            HTTPS_PORT,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        connection.putrequest(
            "GET",
            plan.request_target,
            skip_accept_encoding=True,
        )
        for name, value in plan.request_headers:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        response_received = True

        status = getattr(response, "status", None)
        if type(status) is not int or not 100 <= status <= 599:
            raise FotMobReviewedMatchDetailsProbeError(
                "HTTP response status is invalid"
            )
        content_type = response.getheader("Content-Type")
        content_length = _parse_content_length(
            response.getheader("Content-Length")
        )
        location = response.getheader("Location")
        sample = response.read(MAX_SAMPLE_BYTES)
        if type(sample) is not bytes:
            raise FotMobReviewedMatchDetailsProbeError(
                "HTTP response sample must be exact bytes"
            )
        observed_at = _observed(clock, "observed_at")
        receipt = build_response_receipt(
            plan=plan,
            status_code=status,
            content_type=content_type,
            content_length=content_length,
            location=location,
            observed_at=observed_at,
            sample=sample,
        )
        return ProbeExecution(receipt=receipt, operator_error=None)
    except FotMobReviewedMatchDetailsProbeError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        if response_received:
            raise FotMobReviewedMatchDetailsProbeError(
                f"response sampling failed: {_bounded_error(exc)}"
            ) from exc
        observed_at = _observed(clock, "observed_at")
        receipt = build_transport_error_receipt(
            plan=plan,
            observed_at=observed_at,
        )
        return ProbeExecution(
            receipt=receipt,
            operator_error=f"transport error: {_bounded_error(exc)}",
        )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsProbeError(
            f"probe response handling failed: {_bounded_error(exc)}"
        ) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


__all__ = [
    "ProbeExecution",
    "REQUEST_TIMEOUT_SECONDS",
    "probe_fotmob_reviewed_match_details",
]
