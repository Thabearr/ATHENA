"""Direct SportyBet Nigeria share-code proof.

This module reproduces the public anonymous booking/share operation exposed by
SportyBet's own web client. It never logs in, submits a stake, touches a wallet,
or places a wager.

The preserved SportyBet WAP client wraps `fetch()` and rewrites root-relative
requests beneath `/api/<country>/`. Therefore the browser call
`fetch('/orders/share?...')` is transmitted to `/api/ng/orders/share?...` in the
Nigeria environment. This module targets that actual network path directly.
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
SPORTYBET_COUNTRY_PREFIX = "ng"
CREATE_PATH = "/api/ng/orders/share?throwInvalidEvent=true"
LOAD_PREFIX = "/api/ng/orders/share/"
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
        "Accept-Language": "en-NG,en;q=0.9",
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


def _success_data(payload: dict[str, Any], label: str) -> dict[str, Any]:
    if payload.get("bizCode") != 10000:
        raise SportyBetDirectShareError(
            f"{label} bizCode was not SUCCESS: {payload.get('bizCode')!r}"
        )
    data = payload.get("data")
    if type(data) is not dict:
        raise SportyBetDirectShareError(f"{label} success response omitted data object")
    unavailable = data.get("unavailableOutcomes")
    if type(unavailable) is not list:
        raise SportyBetDirectShareError(
            f"{label} unavailableOutcomes must be an array"
        )
    if unavailable:
        raise SportyBetDirectShareError(
            f"{label} contains {len(unavailable)} unavailable outcomes"
        )
    return data


def extract_share_code(payload: dict[str, Any]) -> str:
    data = _success_data(payload, "create")
    for key in ("shareCode", "bookingCode", "code"):
        value = data.get(key)
        if type(value) is str and _CODE_RE.fullmatch(value):
            return value
    raise SportyBetDirectShareError(
        "SportyBet success response omitted recognized share-code field"
    )


def _identity(row: dict[str, Any]) -> tuple[str, str, str, str | None]:
    return (
        str(row.get("eventId")),
        str(row.get("marketId")),
        str(row.get("outcomeId")),
        None if row.get("specifier") is None else str(row.get("specifier")),
    )


def _validate_exact_roundtrip(
    *,
    requested: tuple[dict[str, str], ...],
    create_payload: dict[str, Any],
    load_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    create_data = _success_data(create_payload, "create")
    load_data = _success_data(load_payload, "load")

    create_outcomes = create_data.get("outcomes")
    load_outcomes = load_data.get("outcomes")
    if type(create_outcomes) is not list or len(create_outcomes) != len(requested):
        raise SportyBetDirectShareError(
            "create accepted-outcome count does not equal requested selection count"
        )
    if type(load_outcomes) is not list or len(load_outcomes) != len(requested):
        raise SportyBetDirectShareError(
            "load accepted-outcome count does not equal requested selection count"
        )

    ticket = load_data.get("ticket")
    if type(ticket) is not dict or type(ticket.get("selections")) is not list:
        raise SportyBetDirectShareError("load response omitted ticket selections")
    loaded_rows = ticket["selections"]
    if len(loaded_rows) != len(requested):
        raise SportyBetDirectShareError(
            "round-trip ticket selection count does not equal requested selection count"
        )
    if any(type(row) is not dict for row in loaded_rows):
        raise SportyBetDirectShareError("round-trip ticket selection must be object")

    requested_ids = sorted(_identity(row) for row in requested)
    loaded_ids = sorted(_identity(row) for row in loaded_rows)
    if requested_ids != loaded_ids:
        raise SportyBetDirectShareError(
            "round-trip provider-native selection identities do not equal request"
        )
    return create_data, load_data


def _combined_odds(outcomes: list[Any]) -> float:
    product = 1.0
    for event in outcomes:
        if type(event) is not dict:
            raise SportyBetDirectShareError("accepted outcome entry must be object")
        markets = event.get("markets")
        if type(markets) is not list or len(markets) != 1 or type(markets[0]) is not dict:
            raise SportyBetDirectShareError(
                "accepted event must contain exactly one market"
            )
        selections = markets[0].get("outcomes")
        if (
            type(selections) is not list
            or len(selections) != 1
            or type(selections[0]) is not dict
        ):
            raise SportyBetDirectShareError(
                "accepted market must contain exactly one outcome"
            )
        try:
            odds = float(selections[0]["odds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SportyBetDirectShareError("accepted outcome has invalid odds") from exc
        if odds <= 1.0:
            raise SportyBetDirectShareError("accepted outcome odds must exceed 1.0")
        product *= odds
    return product


def create_and_roundtrip(
    *, selections: tuple[dict[str, str], ...], output_dir: Path
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    request_payload = {"selections": list(selections)}
    (output_dir / "create-request.json").write_bytes(
        _canonical_json_bytes(request_payload)
    )
    create_payload, create_raw, create_status = _request_json(
        path=CREATE_PATH, method="POST", payload=request_payload
    )
    (output_dir / "create-response.raw.json").write_bytes(create_raw)
    if create_status != 200:
        raise SportyBetDirectShareError(f"create returned HTTP {create_status}")
    code = extract_share_code(create_payload)

    load_payload, load_raw, load_status = _request_json(
        path=LOAD_PREFIX + code, method="GET"
    )
    (output_dir / "load-response.raw.json").write_bytes(load_raw)
    if load_status != 200:
        raise SportyBetDirectShareError(f"load returned HTTP {load_status}")

    create_data, load_data = _validate_exact_roundtrip(
        requested=selections,
        create_payload=create_payload,
        load_payload=load_payload,
    )
    combined_odds = _combined_odds(load_data["outcomes"])
    share_url = load_data.get("shareURL") or create_data.get("shareURL")
    if type(share_url) is not str or not share_url.startswith("http"):
        raise SportyBetDirectShareError("SportyBet response omitted shareURL")

    receipt = {
        "schema": "athena-sportybet-direct-share-proof-v2",
        "observed_at": _utc_now(),
        "provider": "SportyBet Nigeria",
        "provider_origin": SPORTYBET_ORIGIN,
        "country_prefix": SPORTYBET_COUNTRY_PREFIX,
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
        "shareURL": share_url,
        "combined_odds": format(combined_odds, ".12g"),
        "exact_roundtrip_selection_identity_verified": True,
        "create_unavailable_outcomes": 0,
        "load_unavailable_outcomes": 0,
        # These are the provider's accepted event/market/outcome objects, not
        # caller input.  The semantic bridge consumes them to prove that a
        # native-ID round trip also preserved the human-readable selection.
        # Keep the direct bridge transport-only: it does not interpret them.
        "create_accepted_selection_count": len(create_data["outcomes"]),
        "load_accepted_selection_count": len(load_data["outcomes"]),
        "create_accepted_outcomes": create_data["outcomes"],
        "load_accepted_outcomes": load_data["outcomes"],
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
                "shareURL": receipt["shareURL"],
                "selection_count": receipt["selection_count"],
                "combined_odds": receipt["combined_odds"],
                "exact_roundtrip_selection_identity_verified": True,
                "wager_placed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
