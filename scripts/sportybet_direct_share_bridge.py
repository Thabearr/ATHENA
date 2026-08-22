"""Direct SportyBet Nigeria share-code proof.

This module reproduces the public anonymous booking/share operation exposed by
SportyBet's own web client.  It never logs in, submits a stake, touches a wallet,
or places a wager.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SPORTYBET_ORIGIN = "https://www.sportybet.com"
SPORTYBET_OPER_ID = "2"
CREATE_PATH = "/orders/share?throwInvalidEvent=true"
LOAD_PREFIX = "/orders/share/"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,160}$", re.ASCII)
_CODE_RE = re.compile(r"^[A-Za-z0-9]{3,32}$", re.ASCII)


class SportyBetDirectShareError(RuntimeError):
    pass


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def validate_selections(value: Any) -> tuple[dict[str, str], ...]:
    if type(value) is not list or not value:
        raise SportyBetDirectShareError("selections must be a non-empty array")
    if len(value) > 50:
        raise SportyBetDirectShareError("SportyBet selection limit exceeded")
    rows: list[dict[str, str]] = []
    seen_events: set[str] = set()
    for index, raw in enumerate(value):
        if type(raw) is not dict:
            raise SportyBetDirectShareError(f"selection {index} must be an object")
        if set(raw) - {"eventId", "marketId", "outcomeId", "specifier"}:
            raise SportyBetDirectShareError(f"selection {index} has unsupported fields")
        event_id = raw.get("eventId")
        market_id = raw.get("marketId")
        outcome_id = raw.get("outcomeId")
        specifier = raw.get("specifier")
        if type(event_id) is not str or _EVENT_RE.fullmatch(event_id) is None:
            raise SportyBetDirectShareError(f"selection {index} has invalid eventId")
        if event_id in seen_events:
            raise SportyBetDirectShareError("only one selection per event is allowed")
        seen_events.add(event_id)
        if type(market_id) is not str or _SAFE_ID_RE.fullmatch(market_id) is None:
            raise SportyBetDirectShareError(f"selection {index} has invalid marketId")
        if type(outcome_id) is not str or _SAFE_ID_RE.fullmatch(outcome_id) is None:
            raise SportyBetDirectShareError(f"selection {index} has invalid outcomeId")
        row = {
            "eventId": event_id,
            "marketId": market_id,
            "outcomeId": outcome_id,
        }
        if specifier is not None:
            if (
                type(specifier) is not str
                or not specifier
                or specifier != specifier.strip()
                or len(specifier) > 160
            ):
                raise SportyBetDirectShareError(
                    f"selection {index} has invalid specifier"
                )
            row["specifier"] = specifier
        rows.append(row)
    return tuple(rows)


def _request_json(
    *, path: str, method: str, payload: dict[str, Any] | None = None
) -> tuple[dict[str, Any], bytes, int]:
    if not path.startswith("/") or "//" in path:
        raise SportyBetDirectShareError("invalid SportyBet path")
    body = None if payload is None else _canonical_json_bytes(payload)
    headers = {
        "Accept": "application/json",
        "User-Agent": "ATHENA/1.0 direct-sportybet-share-proof",
        "OperId": SPORTYBET_OPER_ID,
    }
    if body is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"
    req = Request(
        SPORTYBET_ORIGIN + path,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(req, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = exc.code
    except URLError as exc:
        raise SportyBetDirectShareError(
            f"SportyBet request failed: {exc.reason}"
        ) from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SportyBetDirectShareError("SportyBet response exceeds byte bound")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        prefix = raw[:500].decode("utf-8", errors="replace")
        raise SportyBetDirectShareError(
            f"SportyBet returned non-JSON HTTP {status}: {prefix}"
        ) from exc
    if type(parsed) is not dict:
        raise SportyBetDirectShareError("SportyBet response must be an object")
    return parsed, raw, status


def extract_share_code(payload: dict[str, Any]) -> str:
    if payload.get("bizCode") != 10000:
        raise SportyBetDirectShareError(
            f"SportyBet bizCode was not SUCCESS: {payload.get('bizCode')!r}"
        )
    data = payload.get("data")
    if type(data) is not dict:
        raise SportyBetDirectShareError("SportyBet success response omitted data object")
    for key in ("shareCode", "bookingCode", "code"):
        value = data.get(key)
        if type(value) is str and _CODE_RE.fullmatch(value):
            return value
    raise SportyBetDirectShareError(
        "SportyBet success response omitted recognized share-code field"
    )


def create_and_roundtrip(
    *, selections: tuple[dict[str, str], ...], output_dir: Path
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    request_payload = {"selections": list(selections)}
    create_payload, create_raw, create_status = _request_json(
        path=CREATE_PATH, method="POST", payload=request_payload
    )
    (output_dir / "create-response.raw.json").write_bytes(create_raw)
    code = extract_share_code(create_payload)

    load_payload, load_raw, load_status = _request_json(
        path=LOAD_PREFIX + code, method="GET"
    )
    (output_dir / "load-response.raw.json").write_bytes(load_raw)
    if load_payload.get("bizCode") != 10000:
        raise SportyBetDirectShareError(
            f"round-trip load failed with bizCode {load_payload.get('bizCode')!r}"
        )

    receipt = {
        "schema": "athena-sportybet-direct-share-proof-v1",
        "observed_at": _utc_now(),
        "provider": "SportyBet Nigeria",
        "provider_origin": SPORTYBET_ORIGIN,
        "oper_id": SPORTYBET_OPER_ID,
        "create_path": CREATE_PATH,
        "load_path": LOAD_PREFIX + code,
        "selection_count": len(selections),
        "selection_request_sha256": _sha256(_canonical_json_bytes(request_payload)),
        "create_http_status": create_status,
        "create_response_sha256": _sha256(create_raw),
        "load_http_status": load_status,
        "load_response_sha256": _sha256(load_raw),
        "shareCode": code,
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
        "roundtrip_payload": load_payload,
    }
    (output_dir / "direct-share-proof-receipt.json").write_bytes(
        _canonical_json_bytes(receipt)
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selections", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    selections = validate_selections(
        json.loads(args.selections.read_text(encoding="utf-8"))
    )
    receipt = create_and_roundtrip(
        selections=selections, output_dir=args.output_dir
    )
    print(
        json.dumps(
            {
                "shareCode": receipt["shareCode"],
                "selection_count": receipt["selection_count"],
                "wager_placed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
