"""Capture exact live SportyBet Nigeria markets for frozen provider event IDs.

Uses only the anonymous read-only endpoint exposed by SportyBet's own WAP
client. No cookies, login, account, wallet, stake, or wager operation exists in
this module.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ORIGIN = "https://www.sportybet.com"
OPER_ID = "2"
EVENT_PATH = "/api/ng/factsCenter/event"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

SELECTION_SPECS: dict[str, tuple[str, str | None, str]] = {
    "HOME_WIN": ("1", None, "1"),
    "AWAY_WIN": ("1", None, "3"),
    "HOME_1UP": ("60200", None, "1"),
    "AWAY_1UP": ("60200", None, "3"),
    "HOME_2UP": ("60100", None, "1"),
    "AWAY_2UP": ("60100", None, "3"),
    "TOTAL_GOALS_OVER_1_5": ("18", "total=1.5", "12"),
    "HOME_TEAM_TOTAL_OVER_0_5": ("19", "total=0.5", "12"),
    "AWAY_TEAM_TOTAL_OVER_0_5": ("20", "total=0.5", "12"),
}


class DirectMarketProbeError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _market_id(obj: dict[str, Any]) -> str | None:
    for key in ("id", "marketId", "market_id"):
        value = obj.get(key)
        if value is not None:
            return str(value)
    return None


def _specifier(obj: dict[str, Any]) -> str | None:
    value = obj.get("specifier")
    return str(value) if value is not None else None


def _outcome_id(obj: dict[str, Any]) -> str | None:
    for key in ("id", "outcomeId", "outcome_id"):
        value = obj.get(key)
        if value is not None:
            return str(value)
    return None


def _outcome_active(obj: dict[str, Any]) -> bool:
    for key in ("isActive", "is_active"):
        if key in obj:
            value = obj[key]
            return value in (1, True, "1")
    return True


def _find_market(
    payload: dict[str, Any], market_id: str, specifier: str | None, outcome_id: str
) -> dict[str, Any]:
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for obj in _walk(payload):
        outcomes = obj.get("outcomes")
        if not isinstance(outcomes, list) or _market_id(obj) != market_id:
            continue
        if _specifier(obj) != specifier:
            continue
        for outcome in outcomes:
            if isinstance(outcome, dict) and _outcome_id(outcome) == outcome_id:
                candidates.append((obj, outcome))
    if len(candidates) != 1:
        raise DirectMarketProbeError(
            f"expected one market {market_id}/{specifier}/{outcome_id}; "
            f"found {len(candidates)}"
        )
    market, outcome = candidates[0]
    if not _outcome_active(outcome):
        raise DirectMarketProbeError("target outcome is inactive")
    odds = outcome.get("odds")
    if not isinstance(odds, (str, int, float)):
        raise DirectMarketProbeError("target outcome omitted odds")
    return {
        "marketId": market_id,
        "specifier": specifier,
        "outcomeId": outcome_id,
        "market_description": market.get("desc", market.get("name")),
        "outcome_description": outcome.get("desc", outcome.get("description")),
        "odds": str(odds),
        "status": market.get("status"),
    }


def _contains_event_id(payload: dict[str, Any], event_id: str) -> bool:
    return any(obj.get("eventId") == event_id for obj in _walk(payload))


def _fetch_event(event_id: str) -> tuple[dict[str, Any], bytes, int, str]:
    query = urlencode({"productId": 3, "eventId": event_id})
    url = f"{ORIGIN}{EVENT_PATH}?{query}"
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-NG,en;q=0.9",
            "OperId": OPER_ID,
            "User-Agent": "ATHENA/1.0 direct-sportybet-market-probe",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = exc.code
    except URLError as exc:
        raise DirectMarketProbeError(f"SportyBet request failed: {exc.reason}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise DirectMarketProbeError("SportyBet event response exceeds byte bound")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DirectMarketProbeError(
            f"SportyBet returned non-JSON HTTP {status}: "
            + raw[:300].decode("utf-8", errors="replace")
        ) from exc
    if not isinstance(payload, dict):
        raise DirectMarketProbeError("SportyBet event response must be object")
    return payload, raw, status, url


def run(targets_path: Path, output_dir: Path, delay_seconds: float) -> dict[str, Any]:
    targets = json.loads(targets_path.read_text(encoding="utf-8"))
    if not isinstance(targets, list) or len(targets) != 20:
        raise DirectMarketProbeError("target file must contain exactly 20 rows")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    seen_events: set[str] = set()

    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise DirectMarketProbeError("target row must be object")
        target_id = target.get("target_id")
        event_id = target.get("eventId")
        desired = target.get("desired_selection")
        if not all(isinstance(x, str) and x for x in (target_id, event_id, desired)):
            raise DirectMarketProbeError("target identity fields must be non-empty strings")
        if event_id in seen_events:
            raise DirectMarketProbeError(f"duplicate eventId {event_id}")
        seen_events.add(event_id)
        if desired not in SELECTION_SPECS:
            raise DirectMarketProbeError(f"unsupported desired selection {desired}")
        if index and delay_seconds:
            time.sleep(delay_seconds)
        try:
            payload, raw, status, url = _fetch_event(event_id)
            raw_path = output_dir / f"{target_id}.raw.json"
            raw_path.write_bytes(raw)
            if status != 200 or payload.get("bizCode") != 10000:
                raise DirectMarketProbeError(
                    f"HTTP/bizCode failure: {status}/{payload.get('bizCode')!r}"
                )
            if not _contains_event_id(payload, event_id):
                raise DirectMarketProbeError("response did not bind requested eventId")
            market_id, specifier, outcome_id = SELECTION_SPECS[desired]
            matched = _find_market(payload, market_id, specifier, outcome_id)
            results.append(
                {
                    "target_id": target_id,
                    "eventId": event_id,
                    "desired_selection": desired,
                    "request_url": url,
                    "http_status": status,
                    "raw_sha256": _sha256(raw),
                    **matched,
                }
            )
        except DirectMarketProbeError as exc:
            failures.append(
                {
                    "target_id": str(target_id),
                    "eventId": str(event_id),
                    "desired_selection": str(desired),
                    "error": str(exc),
                }
            )

    receipt = {
        "schema": "athena-sportybet-direct-20-market-probe-v1",
        "observed_at": _now(),
        "provider": "SportyBet Nigeria",
        "provider_origin": ORIGIN,
        "event_endpoint": EVENT_PATH,
        "oper_id": OPER_ID,
        "target_count": len(targets),
        "resolved_count": len(results),
        "failure_count": len(failures),
        "results": results,
        "failures": failures,
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }
    (output_dir / "direct-20-market-probe-receipt.json").write_bytes(_canonical(receipt))
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.8)
    args = parser.parse_args(argv)
    receipt = run(args.targets, args.output_dir, args.delay_seconds)
    print(
        json.dumps(
            {
                "resolved_count": receipt["resolved_count"],
                "failure_count": receipt["failure_count"],
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["failure_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
