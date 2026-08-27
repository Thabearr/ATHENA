"""Fail-closed SportyBet semantic booking-code gate.

The low-level direct-share bridge proves that provider-native identities survive a
SportyBet create -> load round trip. That is transport evidence only: a wrong
``marketId``/``outcomeId`` can round-trip perfectly.

This boundary accepts only human-readable provider semantics plus fixture
identity, resolves those semantics from the current SportyBet event payload,
and only then delegates the derived provider-native identities to the existing
direct-share transport.

No caller-supplied marketId/outcomeId is accepted here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import time
import unicodedata
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts import sportybet_direct_share_bridge as transport


SPORTYBET_ORIGIN = transport.SPORTYBET_ORIGIN
SPORTYBET_OPER_ID = transport.SPORTYBET_OPER_ID
EVENT_PATH = "/api/ng/factsCenter/event"
MAX_EVENT_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_INTENTS = 50
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _name_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    return "".join(ch.lower() for ch in ascii_text if ch.isalnum())


def _exact_text(value: Any, label: str, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise SportyBetSemanticShareError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def validate_intents(value: Any) -> tuple[dict[str, Any], ...]:
    if type(value) is not list or not value:
        raise SportyBetSemanticShareError("intents must be a non-empty array")
    if len(value) > MAX_INTENTS:
        raise SportyBetSemanticShareError("SportyBet intent limit exceeded")

    allowed = {
        "eventId",
        "homeTeamName",
        "awayTeamName",
        "marketName",
        "outcomeName",
        "specifier",
    }
    forbidden_native = {"marketId", "outcomeId", "odds"}
    rows: list[dict[str, Any]] = []
    seen_events: set[str] = set()

    for index, raw in enumerate(value):
        if type(raw) is not dict:
            raise SportyBetSemanticShareError(f"intent {index} must be an object")
        present_forbidden = set(raw) & forbidden_native
        if present_forbidden:
            names = ", ".join(sorted(present_forbidden))
            raise SportyBetSemanticShareError(
                f"intent {index} contains caller-supplied provider-native fields: {names}"
            )
        extra = set(raw) - allowed
        if extra:
            raise SportyBetSemanticShareError(
                f"intent {index} has unsupported fields: {sorted(extra)!r}"
            )

        event_id = raw.get("eventId")
        if type(event_id) is not str or _EVENT_RE.fullmatch(event_id) is None:
            raise SportyBetSemanticShareError(f"intent {index} has invalid eventId")
        if event_id in seen_events:
            raise SportyBetSemanticShareError("only one intent per event is allowed")
        seen_events.add(event_id)

        home = _exact_text(raw.get("homeTeamName"), f"intent {index} homeTeamName")
        away = _exact_text(raw.get("awayTeamName"), f"intent {index} awayTeamName")
        market = _exact_text(raw.get("marketName"), f"intent {index} marketName")
        outcome = _exact_text(raw.get("outcomeName"), f"intent {index} outcomeName")
        specifier = raw.get("specifier")
        if specifier is not None:
            specifier = _exact_text(
                specifier, f"intent {index} specifier", maximum=160
            )

        rows.append(
            {
                "eventId": event_id,
                "homeTeamName": home,
                "awayTeamName": away,
                "marketName": market,
                "outcomeName": outcome,
                "specifier": specifier,
            }
        )

    return tuple(rows)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _fetch_event(event_id: str) -> tuple[dict[str, Any], bytes, int, str]:
    query = urlencode({"productId": 3, "eventId": event_id})
    url = f"{SPORTYBET_ORIGIN}{EVENT_PATH}?{query}"
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-NG,en;q=0.9",
            "OperId": SPORTYBET_OPER_ID,
            "User-Agent": "ATHENA/1.0 semantic-sportybet-share-gate",
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
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SportyBetSemanticShareError(
            f"SportyBet event returned non-JSON HTTP {status}"
        ) from exc
    if type(parsed) is not dict:
        raise SportyBetSemanticShareError("SportyBet event response must be an object")
    return parsed, raw, status, url


def _event_with_markets(payload: dict[str, Any], event_id: str) -> dict[str, Any]:
    matches = [
        obj
        for obj in _walk(payload)
        if obj.get("eventId") == event_id and isinstance(obj.get("markets"), list)
    ]
    if len(matches) != 1:
        raise SportyBetSemanticShareError(
            f"expected exactly one event object with markets for {event_id}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _market_text(value: dict[str, Any]) -> str:
    return str(
        value.get("desc")
        or value.get("description")
        or value.get("name")
        or ""
    ).strip()


def _outcome_text(value: dict[str, Any]) -> str:
    return str(
        value.get("desc")
        or value.get("description")
        or value.get("name")
        or ""
    ).strip()


def _active_outcome(value: dict[str, Any]) -> bool:
    for key in ("isActive", "is_active"):
        if key in value:
            return value[key] in (1, True, "1")
    return True


def _validate_fixture(event: dict[str, Any], intent: dict[str, Any]) -> tuple[str, str]:
    actual_home = _exact_text(event.get("homeTeamName"), "SportyBet homeTeamName")
    actual_away = _exact_text(event.get("awayTeamName"), "SportyBet awayTeamName")

    if _name_key(actual_home) != _name_key(intent["homeTeamName"]):
        raise SportyBetSemanticShareError(
            f"{intent['eventId']} home-team semantic mismatch: "
            f"expected {intent['homeTeamName']!r}, got {actual_home!r}"
        )
    if _name_key(actual_away) != _name_key(intent["awayTeamName"]):
        raise SportyBetSemanticShareError(
            f"{intent['eventId']} away-team semantic mismatch: "
            f"expected {intent['awayTeamName']!r}, got {actual_away!r}"
        )
    return actual_home, actual_away


def _validate_prematch(event: dict[str, Any], *, minimum_lead_seconds: int) -> None:
    if type(minimum_lead_seconds) is not int or minimum_lead_seconds < 0:
        raise SportyBetSemanticShareError("minimum_lead_seconds must be non-negative int")

    kickoff = event.get("estimateStartTime")
    if not isinstance(kickoff, (int, float)) or isinstance(kickoff, bool):
        raise SportyBetSemanticShareError("SportyBet event omitted numeric estimateStartTime")
    now_ms = int(time.time() * 1000)
    if kickoff <= now_ms + minimum_lead_seconds * 1000:
        raise SportyBetSemanticShareError(
            "SportyBet event is not safely pre-match for semantic booking-code mint"
        )
    if event.get("bookingStatus") == "Unavailable":
        raise SportyBetSemanticShareError("SportyBet event bookingStatus is Unavailable")

    status = event.get("status")
    if status not in (None, 0, "0"):
        raise SportyBetSemanticShareError(
            f"SportyBet event status is not pre-match: {status!r}"
        )
    match_status = str(event.get("matchStatus") or "").strip().casefold()
    if match_status and "not start" not in match_status and match_status != "ns":
        raise SportyBetSemanticShareError(
            f"SportyBet matchStatus is not pre-match: {event.get('matchStatus')!r}"
        )


def resolve_intent(
    *,
    event: dict[str, Any],
    intent: dict[str, Any],
    minimum_lead_seconds: int = 120,
) -> tuple[dict[str, str], dict[str, Any]]:
    if event.get("eventId") != intent["eventId"]:
        raise SportyBetSemanticShareError(
            f"eventId mismatch: intent {intent['eventId']!r}, "
            f"payload {event.get('eventId')!r}"
        )

    actual_home, actual_away = _validate_fixture(event, intent)
    _validate_prematch(event, minimum_lead_seconds=minimum_lead_seconds)

    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for market in event.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if _market_text(market).casefold() != intent["marketName"].casefold():
            continue
        if market.get("specifier") != intent["specifier"]:
            continue
        for outcome in market.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            if _outcome_text(outcome).casefold() != intent["outcomeName"].casefold():
                continue
            if not _active_outcome(outcome):
                continue
            matches.append((market, outcome))

    if len(matches) != 1:
        raise SportyBetSemanticShareError(
            f"{intent['eventId']} semantic selection expected exactly one live match "
            f"for market={intent['marketName']!r}, specifier={intent['specifier']!r}, "
            f"outcome={intent['outcomeName']!r}; found {len(matches)}"
        )

    market, outcome = matches[0]
    market_id = market.get("id", market.get("marketId"))
    outcome_id = outcome.get("id", outcome.get("outcomeId"))
    if market_id is None or outcome_id is None:
        raise SportyBetSemanticShareError(
            "resolved SportyBet semantic selection omitted provider-native identity"
        )

    selection: dict[str, str] = {
        "eventId": intent["eventId"],
        "marketId": str(market_id),
        "outcomeId": str(outcome_id),
    }
    if intent["specifier"] is not None:
        selection["specifier"] = intent["specifier"]
    validated_selection = transport.validate_selections([selection])[0]

    odds = outcome.get("odds")
    if not isinstance(odds, (str, int, float)) or isinstance(odds, bool):
        raise SportyBetSemanticShareError(
            "resolved SportyBet semantic selection omitted odds"
        )

    audit = {
        "eventId": intent["eventId"],
        "expected_home_team": intent["homeTeamName"],
        "expected_away_team": intent["awayTeamName"],
        "observed_home_team": actual_home,
        "observed_away_team": actual_away,
        "expected_market_name": intent["marketName"],
        "expected_outcome_name": intent["outcomeName"],
        "expected_specifier": intent["specifier"],
        "observed_market_name": _market_text(market),
        "observed_outcome_name": _outcome_text(outcome),
        "observed_specifier": market.get("specifier"),
        "marketId": validated_selection["marketId"],
        "outcomeId": validated_selection["outcomeId"],
        "odds": str(odds),
        "fixture_semantics_verified": True,
        "selection_semantics_verified": True,
    }
    return validated_selection, audit


def resolve_live_intents(
    *,
    intents: tuple[dict[str, Any], ...],
    output_dir: Path,
    minimum_lead_seconds: int = 120,
    delay_seconds: float = 0.25,
) -> tuple[tuple[dict[str, str], ...], dict[str, Any]]:
    if delay_seconds < 0:
        raise SportyBetSemanticShareError("delay_seconds must be non-negative")
    output_dir.mkdir(parents=True, exist_ok=True)
    event_dir = output_dir / "events"
    event_dir.mkdir(parents=True, exist_ok=True)

    selections: list[dict[str, str]] = []
    audits: list[dict[str, Any]] = []
    source_hashes: list[dict[str, Any]] = []

    for index, intent in enumerate(intents):
        if index and delay_seconds:
            time.sleep(delay_seconds)
        payload, raw, status, url = _fetch_event(intent["eventId"])
        event_path = event_dir / f"{intent['eventId'].replace(':', '_')}.raw.json"
        event_path.write_bytes(raw)
        if status != 200 or payload.get("bizCode") != 10000:
            raise SportyBetSemanticShareError(
                f"{intent['eventId']} SportyBet event HTTP/bizCode failure: "
                f"{status}/{payload.get('bizCode')!r}"
            )
        event = _event_with_markets(payload, intent["eventId"])
        selection, audit = resolve_intent(
            event=event,
            intent=intent,
            minimum_lead_seconds=minimum_lead_seconds,
        )
        selections.append(selection)
        audits.append(audit)
        source_hashes.append(
            {
                "eventId": intent["eventId"],
                "request_url": url,
                "http_status": status,
                "raw_sha256": _sha256(raw),
                "raw_size": len(raw),
            }
        )

    validated = transport.validate_selections(selections)
    receipt = {
        "schema": "athena-sportybet-semantic-share-gate-v1",
        "observed_at": _utc_now(),
        "provider": "SportyBet Nigeria",
        "provider_origin": SPORTYBET_ORIGIN,
        "event_endpoint": EVENT_PATH,
        "oper_id": SPORTYBET_OPER_ID,
        "intent_count": len(intents),
        "resolved_count": len(validated),
        "minimum_lead_seconds": minimum_lead_seconds,
        "fixture_semantics_verified": True,
        "selection_semantics_verified": True,
        "caller_supplied_market_outcome_ids_accepted": False,
        "resolved": audits,
        "event_sources": source_hashes,
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }
    (output_dir / "semantic-resolution-receipt.json").write_bytes(
        _canonical_json_bytes(receipt)
    )
    (output_dir / "resolved-provider-selections.json").write_bytes(
        _canonical_json_bytes(list(validated))
    )
    return validated, receipt


def _semantic_transport_row(value: Any, label: str) -> dict[str, Any]:
    """Extract one accepted provider selection without trusting native IDs.

    Direct-share transport proves native identity only.  This parser is kept in
    the semantic gate so a successful create/load cannot hide a differently
    labelled market or outcome behind a provider ID.
    """
    if type(value) is not dict:
        raise SportyBetSemanticShareError(f"{label} accepted event must be an object")
    event_id = value.get("eventId")
    if type(event_id) is not str or _EVENT_RE.fullmatch(event_id) is None:
        raise SportyBetSemanticShareError(f"{label} accepted event has invalid eventId")
    home = _exact_text(value.get("homeTeamName"), f"{label} homeTeamName")
    away = _exact_text(value.get("awayTeamName"), f"{label} awayTeamName")
    markets = value.get("markets")
    if type(markets) is not list or len(markets) != 1 or type(markets[0]) is not dict:
        raise SportyBetSemanticShareError(
            f"{label} accepted event must contain exactly one market"
        )
    market = markets[0]
    market_id = market.get("id", market.get("marketId"))
    if market_id is None:
        raise SportyBetSemanticShareError(f"{label} accepted market omitted market ID")
    market_name = _exact_text(_market_text(market), f"{label} marketName")
    specifier = market.get("specifier")
    if specifier is not None:
        specifier = _exact_text(specifier, f"{label} specifier", maximum=160)
    outcomes = market.get("outcomes")
    if type(outcomes) is not list or len(outcomes) != 1 or type(outcomes[0]) is not dict:
        raise SportyBetSemanticShareError(
            f"{label} accepted market must contain exactly one outcome"
        )
    outcome = outcomes[0]
    outcome_id = outcome.get("id", outcome.get("outcomeId"))
    if outcome_id is None:
        raise SportyBetSemanticShareError(f"{label} accepted outcome omitted outcome ID")
    outcome_name = _exact_text(_outcome_text(outcome), f"{label} outcomeName")
    odds = outcome.get("odds")
    if isinstance(odds, bool) or not isinstance(odds, (str, int, float)):
        raise SportyBetSemanticShareError(f"{label} accepted outcome omitted odds")
    try:
        decimal_odds = Decimal(str(odds))
    except (InvalidOperation, ValueError) as exc:
        raise SportyBetSemanticShareError(f"{label} accepted outcome odds are invalid") from exc
    if not decimal_odds.is_finite() or decimal_odds <= Decimal("1"):
        raise SportyBetSemanticShareError(f"{label} accepted outcome odds are invalid")
    return {
        "eventId": event_id,
        "homeTeamName": home,
        "awayTeamName": away,
        "marketId": str(market_id),
        "marketName": market_name,
        "specifier": specifier,
        "outcomeId": str(outcome_id),
        "outcomeName": outcome_name,
        "odds": format(decimal_odds, "f"),
    }


def verify_semantic_roundtrip(
    *,
    intents: tuple[dict[str, Any], ...],
    selections: tuple[dict[str, str], ...],
    audits: tuple[dict[str, Any], ...],
    transport_receipt: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Prove semantic intent == provider create == provider reload.

    ``_validate_exact_roundtrip`` remains necessary, but it is intentionally
    insufficient: provider-native IDs can be stable while pointing at a
    different human-readable market.  This gate requires both accepted
    payloads to carry and match the exact semantic intent and native identity.
    """
    if type(transport_receipt) is not dict:
        raise SportyBetSemanticShareError("transport receipt must be an object")
    if transport_receipt.get("exact_roundtrip_selection_identity_verified") is not True:
        raise SportyBetSemanticShareError("native transport round-trip was not verified")
    if type(intents) is not tuple or type(selections) is not tuple or type(audits) is not tuple:
        raise SportyBetSemanticShareError("semantic round-trip inputs must be exact tuples")
    if not intents or len(intents) != len(selections) or len(intents) != len(audits):
        raise SportyBetSemanticShareError("semantic round-trip input counts drifted")
    normalized_intents = validate_intents(list(intents))
    normalized_selections = transport.validate_selections(list(selections))

    create_rows = transport_receipt.get("create_accepted_outcomes")
    load_rows = transport_receipt.get("load_accepted_outcomes")
    if type(create_rows) is not list or type(load_rows) is not list:
        raise SportyBetSemanticShareError(
            "transport receipt omitted provider create/reload semantic outcomes"
        )
    if len(create_rows) != len(intents) or len(load_rows) != len(intents):
        raise SportyBetSemanticShareError(
            "provider create/reload semantic outcome count drifted"
        )
    if transport_receipt.get("create_accepted_selection_count") != len(intents):
        raise SportyBetSemanticShareError("provider create selection count drifted")
    if transport_receipt.get("load_accepted_selection_count") != len(intents):
        raise SportyBetSemanticShareError("provider reload selection count drifted")

    expected_by_event: dict[str, tuple[dict[str, Any], dict[str, str], dict[str, Any]]] = {}
    for intent, selection, audit in zip(normalized_intents, normalized_selections, audits):
        event_id = intent["eventId"]
        if event_id in expected_by_event:
            raise SportyBetSemanticShareError("duplicate semantic round-trip event")
        if audit.get("eventId") != event_id:
            raise SportyBetSemanticShareError("semantic resolution audit event drifted")
        expected_by_event[event_id] = (intent, selection, audit)

    parsed_create = tuple(
        _semantic_transport_row(row, f"create[{index}]")
        for index, row in enumerate(create_rows)
    )
    parsed_load = tuple(
        _semantic_transport_row(row, f"reload[{index}]")
        for index, row in enumerate(load_rows)
    )
    create_by_event = {row["eventId"]: row for row in parsed_create}
    load_by_event = {row["eventId"]: row for row in parsed_load}
    if len(create_by_event) != len(parsed_create) or len(load_by_event) != len(parsed_load):
        raise SportyBetSemanticShareError("provider create/reload contains duplicate events")
    if set(create_by_event) != set(expected_by_event) or set(load_by_event) != set(expected_by_event):
        raise SportyBetSemanticShareError(
            "provider create/reload event identities differ from semantic intent"
        )

    verified: list[dict[str, Any]] = []
    for event_id in sorted(expected_by_event):
        intent, selection, audit = expected_by_event[event_id]
        create = create_by_event[event_id]
        reload = load_by_event[event_id]
        for label, row in (("create", create), ("reload", reload)):
            if row["marketId"] != selection["marketId"] or row["outcomeId"] != selection["outcomeId"]:
                raise SportyBetSemanticShareError(
                    f"{label} provider-native identity differs from semantic resolution"
                )
            if _name_key(row["homeTeamName"]) != _name_key(intent["homeTeamName"]):
                raise SportyBetSemanticShareError(f"{label} home-team semantics differ from intent")
            if _name_key(row["awayTeamName"]) != _name_key(intent["awayTeamName"]):
                raise SportyBetSemanticShareError(f"{label} away-team semantics differ from intent")
            if row["marketName"].casefold() != intent["marketName"].casefold():
                raise SportyBetSemanticShareError(f"{label} market semantics differ from intent")
            if row["outcomeName"].casefold() != intent["outcomeName"].casefold():
                raise SportyBetSemanticShareError(f"{label} outcome semantics differ from intent")
            if row["specifier"] != intent["specifier"]:
                raise SportyBetSemanticShareError(f"{label} specifier semantics differ from intent")
        if create != reload:
            raise SportyBetSemanticShareError(
                "provider create/reload semantic/native rows differ"
            )
        if create["odds"] != reload["odds"]:
            raise SportyBetSemanticShareError("provider create/reload odds differ")
        verified.append({
            "eventId": event_id,
            "expected": {
                "homeTeamName": intent["homeTeamName"],
                "awayTeamName": intent["awayTeamName"],
                "marketName": intent["marketName"],
                "outcomeName": intent["outcomeName"],
                "specifier": intent["specifier"],
                "marketId": selection["marketId"],
                "outcomeId": selection["outcomeId"],
            },
            "resolved": {
                "observed_home_team": audit.get("observed_home_team"),
                "observed_away_team": audit.get("observed_away_team"),
                "observed_market_name": audit.get("observed_market_name"),
                "observed_outcome_name": audit.get("observed_outcome_name"),
                "observed_specifier": audit.get("observed_specifier"),
            },
            "create": create,
            "reload": reload,
            "exact_semantic_match": True,
        })
    return tuple(verified)


def create_semantic_share_code(
    *,
    intents: tuple[dict[str, Any], ...],
    output_dir: Path,
    minimum_lead_seconds: int = 120,
    delay_seconds: float = 0.25,
) -> dict[str, Any]:
    resolution_dir = output_dir / "semantic-resolution"
    transport_dir = output_dir / "transport-roundtrip"
    selections, semantic_receipt = resolve_live_intents(
        intents=intents,
        output_dir=resolution_dir,
        minimum_lead_seconds=minimum_lead_seconds,
        delay_seconds=delay_seconds,
    )
    transport_receipt = transport.create_and_roundtrip(
        selections=selections,
        output_dir=transport_dir,
    )
    if transport_receipt["selection_count"] != semantic_receipt["resolved_count"]:
        raise SportyBetSemanticShareError(
            "transport round-trip selection count drifted from semantic resolution"
        )
    semantic_roundtrip = verify_semantic_roundtrip(
        intents=intents,
        selections=selections,
        audits=tuple(semantic_receipt["resolved"]),
        transport_receipt=transport_receipt,
    )
    if len(semantic_roundtrip) != len(intents):
        raise SportyBetSemanticShareError("semantic round-trip verification count drifted")

    receipt = {
        "schema": "athena-sportybet-semantic-booking-code-proof-v1",
        "observed_at": _utc_now(),
        "semantic_intent_count": semantic_receipt["intent_count"],
        "semantic_resolution_count": semantic_receipt["resolved_count"],
        "selection_semantics_verified": True,
        "fixture_semantics_verified": True,
        "exact_roundtrip_selection_identity_verified": bool(
            transport_receipt["exact_roundtrip_selection_identity_verified"]
        ),
        "provider_create_selection_count": transport_receipt[
            "create_accepted_selection_count"
        ],
        "provider_reload_selection_count": transport_receipt[
            "load_accepted_selection_count"
        ],
        "semantic_roundtrip_verified": True,
        "semantic_roundtrip_verification": list(semantic_roundtrip),
        "provider_create_receipt": {
            "http_status": transport_receipt["create_http_status"],
            "response_sha256": transport_receipt["create_response_sha256"],
            "accepted_selection_count": transport_receipt[
                "create_accepted_selection_count"
            ],
        },
        "provider_reload_receipt": {
            "http_status": transport_receipt["load_http_status"],
            "response_sha256": transport_receipt["load_response_sha256"],
            "accepted_selection_count": transport_receipt[
                "load_accepted_selection_count"
            ],
        },
        "shareCode": transport_receipt["shareCode"],
        "shareURL": transport_receipt["shareURL"],
        "combined_odds": transport_receipt["combined_odds"],
        "wager_placed": False,
        "semantic_resolution_receipt_sha256": _sha256(
            _canonical_json_bytes(semantic_receipt)
        ),
        "transport_receipt_sha256": _sha256(
            _canonical_json_bytes(transport_receipt)
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "semantic-booking-code-receipt.json").write_bytes(
        _canonical_json_bytes(receipt)
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intents", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-lead-seconds", type=int, default=120)
    parser.add_argument("--delay-seconds", type=float, default=0.25)
    args = parser.parse_args(argv)

    intents = validate_intents(
        json.loads(args.intents.read_text(encoding="utf-8"))
    )
    receipt = create_semantic_share_code(
        intents=intents,
        output_dir=args.output_dir,
        minimum_lead_seconds=args.minimum_lead_seconds,
        delay_seconds=args.delay_seconds,
    )
    print(
        json.dumps(
            {
                "shareCode": receipt["shareCode"],
                "shareURL": receipt["shareURL"],
                "selection_count": receipt["semantic_resolution_count"],
                "combined_odds": receipt["combined_odds"],
                "selection_semantics_verified": True,
                "exact_roundtrip_selection_identity_verified": True,
                "wager_placed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
