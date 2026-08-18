"""Fail-closed entry point for the reviewed SportyBet Lite source boundary.

The public Lite HTML shape is reviewed, but ATHENA has not proved permission for
automated/robotic acquisition. This command therefore performs no network I/O.
It preserves the exact future request identity and emits a deterministic blocked
receipt until a separately reviewed access method is authorized.
"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import json
from typing import Any

from domain.sportybet_lite_source_capture import (
    ALLOWED_HOST,
    DEFAULT_MARKET_GROUP,
    FOOTBALL_SPORT_ID,
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    request_target,
)


AUTOMATED_NETWORK_BLOCK_STATE = (
    "BLOCKED_UNTIL_EXPLICIT_SPORTYBET_AUTOMATED_ACCESS_PERMISSION"
)
TERMS_REVIEWED_AT = "2026-08-18"
TERMS_AUTOMATION_FINDING = (
    "Current SportyBet Nigeria terms do not prove permission for ATHENA's "
    "automated source capture; they reserve blocking for automated/robotic "
    "activity. Public accessibility is therefore not treated as automation "
    "authorization."
)


def build_blocked_receipt(
    *,
    request_kind: SportyBetLiteRequestKind,
    event_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(request_kind, SportyBetLiteRequestKind):
        raise SportyBetLiteCaptureError(
            "request_kind must be SportyBetLiteRequestKind"
        )
    if request_kind is SportyBetLiteRequestKind.INDEX:
        target = request_target(request_kind)
        event = None
        sport_id = None
        market_group = None
    else:
        target = request_target(
            request_kind,
            event_id=event_id,
            sport_id=FOOTBALL_SPORT_ID,
            market_groups_name=DEFAULT_MARKET_GROUP,
        )
        event = event_id
        sport_id = FOOTBALL_SPORT_ID
        market_group = DEFAULT_MARKET_GROUP
    return {
        "status": AUTOMATED_NETWORK_BLOCK_STATE,
        "provider": "SportyBet",
        "host": ALLOWED_HOST,
        "request_kind": request_kind.value,
        "request_target": target,
        "event_id": event,
        "sport_id": sport_id,
        "market_groups_name": market_group,
        "terms_reviewed_at": TERMS_REVIEWED_AT,
        "reason": TERMS_AUTOMATION_FINDING,
        "network_acquisition_performed": False,
        "network_acquisition_authorized": False,
        "bookmaker_equivalence_authorized": False,
        "fixture_reconciliation_authorized": False,
        "canonical_market_mapping_authorized": False,
        "fresh_price_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "sportybet_execution_authorized": False,
        "bet_authorized": False,
    }


def canonical_blocked_receipt_bytes(receipt: Any) -> bytes:
    if not isinstance(receipt, dict):
        raise SportyBetLiteCaptureError("blocked receipt must be a dict")
    if receipt.get("status") != AUTOMATED_NETWORK_BLOCK_STATE:
        raise SportyBetLiteCaptureError("blocked receipt status mismatch")
    if receipt.get("network_acquisition_performed") is not False:
        raise SportyBetLiteCaptureError(
            "blocked receipt must prove no network acquisition"
        )
    if receipt.get("network_acquisition_authorized") is not False:
        raise SportyBetLiteCaptureError(
            "blocked receipt must keep network authority false"
        )
    authority_keys = (
        "bookmaker_equivalence_authorized",
        "fixture_reconciliation_authorized",
        "canonical_market_mapping_authorized",
        "fresh_price_authorized",
        "pricing_authorized",
        "selection_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    )
    if any(receipt.get(key) is not False for key in authority_keys):
        raise SportyBetLiteCaptureError(
            "blocked receipt must keep every downstream authority false"
        )
    try:
        return (
            json.dumps(
                receipt,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetLiteCaptureError(
            "blocked receipt serialization failed"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Show the reviewed SportyBet Lite request identity and fail closed "
            "until automated source-access permission is separately proven."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--index", action="store_true", help="review /ng/lite identity")
    mode.add_argument("--event-id", help="review one provider-native sr:match event")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.index:
            receipt = build_blocked_receipt(
                request_kind=SportyBetLiteRequestKind.INDEX,
            )
        else:
            receipt = build_blocked_receipt(
                request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
                event_id=args.event_id,
            )
    except SportyBetLiteCaptureError as exc:
        print(
            json.dumps(
                {
                    "status": AUTOMATED_NETWORK_BLOCK_STATE,
                    "reason": str(exc),
                    "network_acquisition_performed": False,
                    "network_acquisition_authorized": False,
                    "bet_authorized": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(canonical_blocked_receipt_bytes(receipt).decode("utf-8"), end="")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
