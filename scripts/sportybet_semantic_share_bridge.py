"""Fail-closed semantic gate for SportyBet Nigeria share-code creation.

The lower-level :mod:`scripts.sportybet_direct_share_bridge` proves that a set of
provider-native selection identities can be created and loaded back unchanged.
That is necessary, but it is not sufficient for a user-facing ATHENA ticket: a
perfect round trip cannot prove that the supplied IDs represented the fixture,
market, outcome and line ATHENA intended.

This module closes that gap.  It accepts semantic intent only, resolves the
provider-native IDs from the current SportyBet event payload, creates the code
through the reviewed direct bridge, then resolves the semantic intent again and
requires the native identities to be unchanged.  It never logs in, uses a
cookie, touches a wallet, submits a stake or places a wager.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts import sportybet_direct_share_bridge as native_bridge

SPORTYBET_EVENT_PATH = "/api/ng/factsCenter/event"
MAX_EVENT_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_MINIMUM_LEAD_SECONDS = 60
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,160}$", re.ASCII)
_ALLOWED_MATCH_STATUS = frozenset({"", "not start", "not started", "ns"})


class SportyBetSemanticShareError(RuntimeError):
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


def _text(value: Any, label: str, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise SportyBetSemanticShareError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def validate_intents(value: Any) -> tuple[dict[str, str], ...]:
    """Validate semantic intent without accepting caller-supplied native IDs."""
    if type(value) is not list or not value:
        raise SportyBetSemanticShareError("intents must be a non-empty array")
    if len(value) > 50:
        raise SportyBetSemanticShareError("SportyBet selection limit exceeded")

    allowed = {
        "eventId",
        "homeTeamName",
        "awayTeamName",
        "marketLabel",
        "outcomeLabel",
        "specifier",
    }
    rows: list[dict[str, str]] = []
    seen_events: set[str] = set()
    for index, raw in enumerate(value):
        if type(raw) is not dict:
            raise SportyBetSemanticShareError(f"intent {index} must be an object")
        unsupported = set(raw) - allowed
        if unsupported:
            raise SportyBetSemanticShareError(
                f"intent {index} has unsupported fields: {sorted(unsupported)!r}"
            )
        if "marketId" in raw or "outcomeId" in raw:
            raise SportyBetSemanticShareError(
                "semantic intent must not supply provider-native market/outcome IDs"
            )
        event_id = raw.get("eventId")
        if type(event_id) is not str or _EVENT_RE.fullmatch(event_id) is None:
            raise SportyBetSemanticShareError(f"intent {index} has invalid eventId")
        if event_id in seen_events:
            raise SportyBetSemanticShareError("only one semantic intent per event is allowed")
        seen_events.add(event_id)

        row = {
            "eventId": event_id,
            "homeTeamName": _text(raw.get("homeTeamName"), f"intent {index} homeTeamName"),
            "awayTeamName": _text(raw.get("awayTeamName"), f"intent {index} awayTeamName"),
            "marketLabel": _text(raw.get("marketLabel"), f"intent {index} marketLabel"),
            "outcomeLabel": _text(raw.get("outcomeLabel"), f"intent {index} outcomeLabel"),
        }
        specifier = raw.get("specifier")
        if specifier is not None:
            row["specifier"] = _text(
                specifier, f"intent {index} specifier", maximum=160
            )
        rows.append(row)
    return tuple(rows)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _provider_label(value: dict[str, Any], label: str) -> str:
    for key in ("desc", "description", "name"):
        candidate = value.get(key)
        if candidate is not None:
            return _text(candidate, label)
    raise SportyBetSemanticShareError(f"{label} is absent")


def _event_object(payload: dict[str, Any], event_id: str) -> dict[str, Any]:
    if payload.get("bizCode") != 10000:
        raise SportyBetSemanticShareError(
            f"event fetch bizCode was not SUCCESS: {payload.get('bizCode')!r}"
        )
    matches = [
        obj
        for obj in _walk(payload)
        if obj.get("eventId") == event_id and isinstance(obj.get("markets"), list)
    ]
    if len(matches) != 1:
        raise SportyBetSemanticShareError(
            f"expected one event object for {event_id}; found {len(matches)}"
        )
    return matches[0]


def _assert_safely_prematch(
    event: dict[str, Any], *, now_ms: int, minimum_lead_seconds: int
) -> None:
    if minimum_lead_seconds < 0:
        raise SportyBetSemanticShareError("minimum_lead_seconds must be non-negative")
    if event.get("bookingStatus") == "Unavailable":
        raise SportyBetSemanticShareError("event booking is unavailable")
    if event.get("status") not in (None, 0):
        raise SportyBetSemanticShareError("event status is not pre-match")
    match_status = str(event.get("matchStatus") or "").strip().casefold()
    if match_status not in _ALLOWED_MATCH_STATUS:
        raise SportyBetSemanticShareError(
            f"event matchStatus is not pre-match: {event.get('matchStatus')!r}"
        )
    kickoff = event.get("estimateStartTime")
    if isinstance(kickoff, bool) or not isinstance(kickoff, (int, float)):
        raise SportyBetSemanticShareError("event kickoff is absent or invalid")
    if kickoff <= now_ms + minimum_lead_seconds * 1000:
        raise SportyBetSemanticShareError("event is not safely pre-match")


def _safe_native_id(value: Any, label: str) -> str:
    text = str(value) if value is not None else ""
    if _SAFE_ID_RE.fullmatch(text) is None:
        raise SportyBetSemanticShareError(f"{label} is not a safe provider-native ID")
    return text


def resolve_intent_from_payload(
    intent: dict[str, str],
    payload: dict[str, Any],
    *,
    now_ms: int | None = None,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Resolve one semantic intent to exactly one active provider-native selection."""
    event_id = intent["eventId"]
    event = _event_object(payload, event_id)
    if event.get("homeTeamName") != intent["homeTeamName"]:
        raise SportyBetSemanticShareError(
            f"{event_id} home fixture identity mismatch: "
            f"expected {intent['homeTeamName']!r}, got {event.get('homeTeamName')!r}"
        )
    if event.get("awayTeamName") != intent["awayTeamName"]:
        raise SportyBetSemanticShareError(
            f"{event_id} away fixture identity mismatch: "
            f"expected {intent['awayTeamName']!r}, got {event.get('awayTeamName')!r}"
        )

    checked_now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    _assert_safely_prematch(
        event,
        now_ms=checked_now_ms,
        minimum_lead_seconds=minimum_lead_seconds,
    )

    wanted_specifier = intent.get("specifier")
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for market in event.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if market.get("status") not in (None, 0):
            continue
        try:
            label = _provider_label(market, "provider market label")
        except SportyBetSemanticShareError:
            continue
        if label != intent["marketLabel"]:
            continue
        if market.get("specifier") != wanted_specifier:
            continue
        outcomes = market.get("outcomes")
        if not isinstance(outcomes, list):
            continue
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            if outcome.get("isActive") not in (None, 1, True, "1"):
                continue
            try:
                outcome_label = _provider_label(outcome, "provider outcome label")
            except SportyBetSemanticShareError:
                continue
            if outcome_label == intent["outcomeLabel"]:
                matches.append((market, outcome))

    if len(matches) != 1:
        raise SportyBetSemanticShareError(
            f"{event_id} semantic selection expected one exact active match; "
            f"found {len(matches)} for {intent['marketLabel']!r} / "
            f"{wanted_specifier!r} / {intent['outcomeLabel']!r}"
        )

    market, outcome = matches[0]
    market_id = _safe_native_id(market.get("id"), "marketId")
    outcome_id = _safe_native_id(outcome.get("id"), "outcomeId")
    selection = {
        "eventId": event_id,
        "marketId": market_id,
        "outcomeId": outcome_id,
    }
    if wanted_specifier is not None:
        selection["specifier"] = wanted_specifier
    selection = dict(native_bridge.validate_selections([selection])[0])

    try:
        odds = float(outcome.get("odds"))
    except (TypeError, ValueError) as exc:
        raise SportyBetSemanticShareError("resolved outcome has invalid odds") from exc
    if odds <= 1.0:
        raise SportyBetSemanticShareError("resolved outcome odds must exceed 1.0")

    audit = {
        "eventId": event_id,
        "homeTeamName": event["homeTeamName"],
        "awayTeamName": event["awayTeamName"],
        "marketLabel": intent["marketLabel"],
        "outcomeLabel": intent["outcomeLabel"],
        "specifier": wanted_specifier,
        "marketId": market_id,
        "outcomeId": outcome_id,
        "odds": str(outcome.get("odds")),
        "estimateStartTime": event.get("estimateStartTime"),
        "bookingStatus": event.get("bookingStatus"),
        "status": event.get("status"),
        "matchStatus": event.get("matchStatus"),
    }
    return selection, audit


def _fetch_event_payload(event_id: str) -> tuple[dict[str, Any], bytes, int, str]:
    query = urlencode({"productId": 3, "eventId": event_id})
    url = f"{native_bridge.SPORTYBET_ORIGIN}{SPORTYBET_EVENT_PATH}?{query}"
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-NG,en;q=0.9",
            "OperId": native_bridge.SPORTYBET_OPER_ID,
            "User-Agent": "ATHENA/1.0 sportybet-semantic-share-gate",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read(MAX_EVENT_RESPONSE_BYTES + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raw = exc.read(MAX_EVENT_RESPONSE_BYTES + 1)
        status = exc.code
    except URLError as exc:
        raise SportyBetSemanticShareError(
            f"SportyBet event request failed: {exc.reason}"
        ) from exc
    if len(raw) > MAX_EVENT_RESPONSE_BYTES:
        raise SportyBetSemanticShareError("SportyBet event response exceeds byte bound")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SportyBetSemanticShareError(
            f"SportyBet event response was non-JSON HTTP {status}"
        ) from exc
    if type(payload) is not dict:
        raise SportyBetSemanticShareError("SportyBet event response must be an object")
    return payload, raw, status, url


def _native_identity(row: dict[str, str]) -> tuple[str, str, str, str | None]:
    return (
        row["eventId"],
        row["marketId"],
        row["outcomeId"],
        row.get("specifier"),
    )


def _resolve_all(
    intents: tuple[dict[str, str], ...],
    *,
    output_dir: Path,
    phase: str,
    minimum_lead_seconds: int,
    fetcher: Callable[[str], tuple[dict[str, Any], bytes, int, str]],
) -> tuple[tuple[dict[str, str], ...], tuple[dict[str, Any], ...]]:
    phase_dir = output_dir / phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    selections: list[dict[str, str]] = []
    audits: list[dict[str, Any]] = []
    for index, intent in enumerate(intents, start=1):
        payload, raw, status, url = fetcher(intent["eventId"])
        raw_path = phase_dir / f"{index:02d}-{intent['eventId'].replace(':', '-')}.raw.json"
        raw_path.write_bytes(raw)
        if status != 200:
            raise SportyBetSemanticShareError(
                f"{intent['eventId']} event fetch returned HTTP {status}"
            )
        selection, audit = resolve_intent_from_payload(
            intent,
            payload,
            minimum_lead_seconds=minimum_lead_seconds,
        )
        audit = {
            **audit,
            "requestURL": url,
            "responseSha256": _sha256(raw),
        }
        selections.append(selection)
        audits.append(audit)
    return tuple(selections), tuple(audits)


def create_semantic_and_roundtrip(
    *,
    intents: tuple[dict[str, str], ...],
    output_dir: Path,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
    fetcher: Callable[[str], tuple[dict[str, Any], bytes, int, str]] = _fetch_event_payload,
) -> dict[str, Any]:
    """Resolve semantics, mint a code, then prove the semantics still bind the IDs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    intent_bytes = _canonical_json_bytes(list(intents))
    (output_dir / "semantic-intents.json").write_bytes(intent_bytes)

    pre_selections, pre_audit = _resolve_all(
        intents,
        output_dir=output_dir,
        phase="semantic-pre",
        minimum_lead_seconds=minimum_lead_seconds,
        fetcher=fetcher,
    )
    (output_dir / "semantic-pre-resolution.json").write_bytes(
        _canonical_json_bytes(list(pre_audit))
    )

    direct_receipt = native_bridge.create_and_roundtrip(
        selections=pre_selections,
        output_dir=output_dir / "native-roundtrip",
    )
    if direct_receipt.get("exact_roundtrip_selection_identity_verified") is not True:
        raise SportyBetSemanticShareError("native round-trip identity proof was not verified")

    post_selections, post_audit = _resolve_all(
        intents,
        output_dir=output_dir,
        phase="semantic-post",
        minimum_lead_seconds=minimum_lead_seconds,
        fetcher=fetcher,
    )
    (output_dir / "semantic-post-resolution.json").write_bytes(
        _canonical_json_bytes(list(post_audit))
    )

    pre_ids = tuple(_native_identity(row) for row in pre_selections)
    post_ids = tuple(_native_identity(row) for row in post_selections)
    if pre_ids != post_ids:
        raise SportyBetSemanticShareError(
            "provider-native identity changed during semantic create/load round trip"
        )

    native_receipt_path = output_dir / "native-roundtrip" / "direct-share-proof-receipt.json"
    native_receipt_bytes = native_receipt_path.read_bytes()
    receipt = {
        "schema": "athena-sportybet-semantic-share-proof-v1",
        "provider": "SportyBet Nigeria",
        "selection_count": len(intents),
        "minimum_lead_seconds": minimum_lead_seconds,
        "semantic_intent_sha256": _sha256(intent_bytes),
        "pre_resolution_sha256": _sha256(_canonical_json_bytes(list(pre_audit))),
        "post_resolution_sha256": _sha256(_canonical_json_bytes(list(post_audit))),
        "native_roundtrip_receipt_sha256": _sha256(native_receipt_bytes),
        "shareCode": direct_receipt["shareCode"],
        "shareURL": direct_receipt["shareURL"],
        "combined_odds": direct_receipt["combined_odds"],
        "semantic_fixture_market_outcome_line_verified": True,
        "post_roundtrip_semantic_revalidation_verified": True,
        "exact_roundtrip_selection_identity_verified": True,
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }
    (output_dir / "semantic-share-proof-receipt.json").write_bytes(
        _canonical_json_bytes(receipt)
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intents", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--minimum-lead-seconds",
        type=int,
        default=DEFAULT_MINIMUM_LEAD_SECONDS,
    )
    args = parser.parse_args(argv)
    intents = validate_intents(json.loads(args.intents.read_text(encoding="utf-8")))
    receipt = create_semantic_and_roundtrip(
        intents=intents,
        output_dir=args.output_dir,
        minimum_lead_seconds=args.minimum_lead_seconds,
    )
    print(
        json.dumps(
            {
                "shareCode": receipt["shareCode"],
                "shareURL": receipt["shareURL"],
                "selection_count": receipt["selection_count"],
                "combined_odds": receipt["combined_odds"],
                "semantic_fixture_market_outcome_line_verified": True,
                "post_roundtrip_semantic_revalidation_verified": True,
                "exact_roundtrip_selection_identity_verified": True,
                "wager_placed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
