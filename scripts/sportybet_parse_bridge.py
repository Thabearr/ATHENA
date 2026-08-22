"""Parse-backed SportyBet Nigeria discovery and booking-code bridge.

This module deliberately separates:
- live public-market discovery through an independent Parse wrapper;
- exact provider-native selection review;
- booking-code creation.

It never logs or serializes PARSE_API_KEY and it does not place a wager or
interact with a SportyBet account, wallet, stake, PIN, cookie, or credential.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PARSE_API_KEY_ENV = "PARSE_API_KEY"
DISCOVERY_BASE_URL = (
    "https://api.parse.bot/scraper/8ffd9f0c-6174-43af-80dc-4898f47f074b"
)
BOOKING_BASE_URL = (
    "https://api.parse.bot/scraper/8e652912-d760-4522-85ce-071e539a9c12"
)
DEFAULT_OUTPUT_ROOT = Path(".cache/athena-research/sportybet-parse-bridge")
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
_EVENT_ID_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,160}$", re.ASCII)


class SportyBetParseBridgeError(RuntimeError):
    """Raised when the external bridge fails closed."""


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


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _required_api_key() -> str:
    value = os.environ.get(PARSE_API_KEY_ENV, "")
    if not value or value != value.strip():
        raise SportyBetParseBridgeError(
            f"{PARSE_API_KEY_ENV} must be supplied as a non-empty environment secret"
        )
    return value


def _request_json(
    *,
    base_url: str,
    endpoint: str,
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: int = 45,
) -> tuple[dict[str, Any], bytes]:
    if not endpoint or "/" in endpoint:
        raise SportyBetParseBridgeError("endpoint must be one path segment")
    url = f"{base_url}/{endpoint}"
    if query:
        url = f"{url}?{urlencode(query)}"

    body = None if payload is None else _canonical_json_bytes(payload)
    request = Request(
        url,
        data=body,
        method="POST" if body is not None else "GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "ATHENA/1.0 Parse-SportyBet-Bridge",
            "X-API-Key": _required_api_key(),
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SportyBetParseBridgeError(
                    "Parse response exceeds reviewed byte bound"
                )
            status = getattr(response, "status", 200)
            if status != 200:
                raise SportyBetParseBridgeError(f"Parse returned HTTP {status}")
    except HTTPError as exc:
        raw = exc.read(4096)
        text = raw.decode("utf-8", errors="replace")
        raise SportyBetParseBridgeError(
            f"Parse returned HTTP {exc.code}: {text[:1000]}"
        ) from exc
    except URLError as exc:
        raise SportyBetParseBridgeError(f"Parse request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SportyBetParseBridgeError("Parse returned non-JSON response") from exc
    if type(parsed) is not dict:
        raise SportyBetParseBridgeError("Parse response must be a JSON object")
    return parsed, raw


def _response_data(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != "success":
        raise SportyBetParseBridgeError(
            f"Parse response status is not success: {payload.get('status')!r}"
        )
    data = payload.get("data")
    if type(data) is not dict:
        raise SportyBetParseBridgeError("Parse response data must be an object")
    return data


def _validate_target_rows(value: Any) -> tuple[dict[str, Any], ...]:
    if type(value) is not list or not value:
        raise SportyBetParseBridgeError("targets must be a non-empty JSON array")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(value):
        if type(raw) is not dict:
            raise SportyBetParseBridgeError(f"target {index} must be an object")
        target_id = raw.get("target_id")
        home_names = raw.get("home_names")
        away_names = raw.get("away_names")
        desired_selection = raw.get("desired_selection")
        if (
            type(target_id) is not str
            or not target_id
            or target_id != target_id.strip()
        ):
            raise SportyBetParseBridgeError(f"target {index} has invalid target_id")
        if target_id in seen_ids:
            raise SportyBetParseBridgeError(f"duplicate target_id {target_id!r}")
        seen_ids.add(target_id)
        if (
            type(home_names) is not list
            or not home_names
            or any(type(x) is not str or not x.strip() for x in home_names)
        ):
            raise SportyBetParseBridgeError(
                f"target {target_id} has invalid home_names"
            )
        if (
            type(away_names) is not list
            or not away_names
            or any(type(x) is not str or not x.strip() for x in away_names)
        ):
            raise SportyBetParseBridgeError(
                f"target {target_id} has invalid away_names"
            )
        if (
            type(desired_selection) is not str
            or not desired_selection
            or desired_selection != desired_selection.strip()
        ):
            raise SportyBetParseBridgeError(
                f"target {target_id} has invalid desired_selection"
            )
        rows.append(
            {
                "target_id": target_id,
                "home_names": sorted(set(home_names)),
                "away_names": sorted(set(away_names)),
                "desired_selection": desired_selection,
            }
        )
    return tuple(rows)


def _iter_events(upcoming_data: dict[str, Any]) -> Iterable[dict[str, Any]]:
    tournaments = upcoming_data.get("tournaments")
    if type(tournaments) is not list:
        raise SportyBetParseBridgeError(
            "upcoming response tournaments must be an array"
        )
    for tournament in tournaments:
        if type(tournament) is not dict:
            raise SportyBetParseBridgeError("tournament entry must be an object")
        events = tournament.get("events")
        if type(events) is not list:
            raise SportyBetParseBridgeError("tournament events must be an array")
        for event in events:
            if type(event) is not dict:
                raise SportyBetParseBridgeError("event entry must be an object")
            copied = dict(event)
            copied["_category"] = tournament.get("category")
            copied["_tournament_id"] = tournament.get("tournament_id")
            copied["_tournament_name"] = tournament.get("tournament_name")
            yield copied


def _match_targets(
    targets: tuple[dict[str, Any], ...],
    events: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    event_rows = tuple(events)
    matched: list[dict[str, Any]] = []
    for target in targets:
        candidates = [
            event
            for event in event_rows
            if event.get("home_team") in target["home_names"]
            and event.get("away_team") in target["away_names"]
        ]
        if len(candidates) != 1:
            matched.append(
                {
                    **target,
                    "match_state": "UNMATCHED" if not candidates else "AMBIGUOUS",
                    "candidate_count": len(candidates),
                    "candidates": [
                        {
                            "event_id": item.get("event_id"),
                            "home_team": item.get("home_team"),
                            "away_team": item.get("away_team"),
                            "start_time": item.get("start_time"),
                            "tournament_id": item.get("_tournament_id"),
                            "tournament_name": item.get("_tournament_name"),
                        }
                        for item in candidates
                    ],
                }
            )
            continue
        event = candidates[0]
        event_id = event.get("event_id")
        if type(event_id) is not str or _EVENT_ID_RE.fullmatch(event_id) is None:
            raise SportyBetParseBridgeError(
                f"target {target['target_id']} matched invalid event_id"
            )
        matched.append(
            {
                **target,
                "match_state": "UNIQUE_EXACT_NAME_MATCH",
                "candidate_count": 1,
                "event_id": event_id,
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "start_time": event.get("start_time"),
                "match_status": event.get("match_status"),
                "tournament_id": event.get("_tournament_id"),
                "tournament_name": event.get("_tournament_name"),
                "category": event.get("_category"),
            }
        )
    return tuple(matched)


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def probe_today(
    *,
    targets_path: Path,
    output_dir: Path,
    delay_seconds: float,
    max_pages: int,
) -> dict[str, Any]:
    targets = _validate_target_rows(
        json.loads(targets_path.read_text(encoding="utf-8"))
    )
    if delay_seconds < 0:
        raise SportyBetParseBridgeError("delay_seconds must be non-negative")
    if max_pages < 1 or max_pages > 20:
        raise SportyBetParseBridgeError("max_pages must be between 1 and 20")

    output_dir.mkdir(parents=True, exist_ok=True)
    all_events: list[dict[str, Any]] = []
    page_receipts: list[dict[str, Any]] = []
    total_events: int | None = None

    for page in range(1, max_pages + 1):
        if page > 1 and delay_seconds:
            time.sleep(delay_seconds)
        payload, raw = _request_json(
            base_url=DISCOVERY_BASE_URL,
            endpoint="get_upcoming_events",
            query={
                "page": page,
                "sport": "football",
                "page_size": 100,
                "today_only": "true",
            },
        )
        _write_bytes(output_dir / f"upcoming-page-{page:02d}.raw.json", raw)
        data = _response_data(payload)
        if type(data.get("total_events")) is int:
            total_events = data["total_events"]
        events = list(_iter_events(data))
        all_events.extend(events)
        page_receipts.append(
            {
                "page": page,
                "raw_sha256": _sha256(raw),
                "event_count": len(events),
                "reported_total_events": total_events,
            }
        )
        if not events:
            break
        if total_events is not None and page * 100 >= total_events:
            break

    matched = _match_targets(targets, all_events)
    exact = [
        row for row in matched if row["match_state"] == "UNIQUE_EXACT_NAME_MATCH"
    ]
    details: list[dict[str, Any]] = []
    for row in exact:
        if delay_seconds:
            time.sleep(delay_seconds)
        payload, raw = _request_json(
            base_url=DISCOVERY_BASE_URL,
            endpoint="get_event_odds",
            query={"event_id": row["event_id"]},
        )
        _write_bytes(
            output_dir / f"event-{row['event_id'].replace(':', '_')}.raw.json",
            raw,
        )
        data = _response_data(payload)
        details.append(
            {
                "target_id": row["target_id"],
                "event_id": row["event_id"],
                "desired_selection": row["desired_selection"],
                "raw_sha256": _sha256(raw),
                "data": data,
            }
        )

    receipt = {
        "schema": "athena-sportybet-parse-probe-v1",
        "observed_at": _utc_now_text(),
        "provider": "SportyBet Nigeria",
        "intermediary": "Parse independent REST wrapper",
        "parse_api_key_serialized": False,
        "wager_placed": False,
        "sportybet_account_used": False,
        "booking_code_created": False,
        "target_count": len(targets),
        "unique_exact_fixture_matches": len(exact),
        "unmatched_or_ambiguous_count": len(targets) - len(exact),
        "page_receipts": page_receipts,
        "targets": list(matched),
        "event_market_details": details,
    }
    _write_bytes(output_dir / "probe-receipt.json", _canonical_json_bytes(receipt))
    return receipt


def _validate_selection_rows(value: Any) -> tuple[dict[str, str], ...]:
    if type(value) is not list or not value:
        raise SportyBetParseBridgeError("selections must be a non-empty JSON array")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str | None, str]] = set()
    for index, raw in enumerate(value):
        if type(raw) is not dict:
            raise SportyBetParseBridgeError(f"selection {index} must be an object")
        allowed = {"eventId", "marketId", "outcomeId", "specifier"}
        if set(raw) - allowed:
            raise SportyBetParseBridgeError(
                f"selection {index} contains unsupported fields"
            )
        event_id = raw.get("eventId")
        market_id = raw.get("marketId")
        outcome_id = raw.get("outcomeId")
        specifier = raw.get("specifier")
        if type(event_id) is not str or _EVENT_ID_RE.fullmatch(event_id) is None:
            raise SportyBetParseBridgeError(f"selection {index} has invalid eventId")
        if type(market_id) is not str or _SAFE_ID_RE.fullmatch(market_id) is None:
            raise SportyBetParseBridgeError(f"selection {index} has invalid marketId")
        if type(outcome_id) is not str or _SAFE_ID_RE.fullmatch(outcome_id) is None:
            raise SportyBetParseBridgeError(f"selection {index} has invalid outcomeId")
        if specifier is not None and (
            type(specifier) is not str
            or not specifier
            or specifier != specifier.strip()
            or len(specifier) > 160
        ):
            raise SportyBetParseBridgeError(f"selection {index} has invalid specifier")
        identity = (event_id, market_id, specifier, outcome_id)
        if identity in seen:
            raise SportyBetParseBridgeError("duplicate selection identity")
        seen.add(identity)
        row = {
            "eventId": event_id,
            "marketId": market_id,
            "outcomeId": outcome_id,
        }
        if specifier is not None:
            row["specifier"] = specifier
        rows.append(row)
    if len({row["eventId"] for row in rows}) != len(rows):
        raise SportyBetParseBridgeError(
            "booking bridge currently permits at most one selection per event"
        )
    return tuple(rows)


def _validate_booking_data(
    data: dict[str, Any], selection_count: int
) -> dict[str, Any]:
    code = data.get("shareCode")
    url = data.get("shareURL")
    outcomes = data.get("outcomes")
    unavailable = data.get("unavailableOutcomes")
    if type(code) is not str or not code.strip():
        raise SportyBetParseBridgeError("booking response omitted shareCode")
    if type(url) is not str or not url.startswith("https://"):
        raise SportyBetParseBridgeError("booking response omitted valid shareURL")
    if type(outcomes) is not list:
        raise SportyBetParseBridgeError("booking response outcomes must be an array")
    if type(unavailable) is not list:
        raise SportyBetParseBridgeError(
            "booking response unavailableOutcomes must be an array"
        )
    if unavailable:
        raise SportyBetParseBridgeError(
            f"booking response contains {len(unavailable)} unavailable outcomes"
        )
    if len(outcomes) != selection_count:
        raise SportyBetParseBridgeError(
            f"booking response returned {len(outcomes)} outcomes for "
            f"{selection_count} requested selections"
        )
    return {
        "shareCode": code,
        "shareURL": url,
        "deadline": data.get("deadline"),
        "outcomes": outcomes,
        "unavailableOutcomes": unavailable,
    }


def book_exact_selections(
    *,
    selections_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    selections = _validate_selection_rows(
        json.loads(selections_path.read_text(encoding="utf-8"))
    )
    payload, raw = _request_json(
        base_url=BOOKING_BASE_URL,
        endpoint="book_bet",
        payload={
            "selections": json.dumps(
                list(selections),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        },
    )
    data = _response_data(payload)
    booking = _validate_booking_data(data, len(selections))
    receipt = {
        "schema": "athena-sportybet-parse-booking-code-v1",
        "observed_at": _utc_now_text(),
        "provider": "SportyBet Nigeria",
        "intermediary": "Parse independent REST wrapper",
        "selection_count": len(selections),
        "selection_request_sha256": _sha256(
            _canonical_json_bytes(list(selections))
        ),
        "parse_response_sha256": _sha256(raw),
        "parse_api_key_serialized": False,
        "sportybet_account_used": False,
        "stake_submitted": False,
        "wager_placed": False,
        **booking,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_bytes(output_dir / "booking-response.raw.json", raw)
    _write_bytes(
        output_dir / "booking-receipt.json", _canonical_json_bytes(receipt)
    )
    return receipt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe")
    probe.add_argument("--targets", type=Path, required=True)
    probe.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT / "probe"
    )
    probe.add_argument("--delay-seconds", type=float, default=13.0)
    probe.add_argument("--max-pages", type=int, default=8)

    book = sub.add_parser("book")
    book.add_argument("--selections", type=Path, required=True)
    book.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT / "booking"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "probe":
        receipt = probe_today(
            targets_path=args.targets,
            output_dir=args.output_dir,
            delay_seconds=args.delay_seconds,
            max_pages=args.max_pages,
        )
        print(
            json.dumps(
                {
                    "target_count": receipt["target_count"],
                    "unique_exact_fixture_matches": receipt[
                        "unique_exact_fixture_matches"
                    ],
                    "unmatched_or_ambiguous_count": receipt[
                        "unmatched_or_ambiguous_count"
                    ],
                    "booking_code_created": False,
                },
                sort_keys=True,
            )
        )
        return 0 if receipt["unmatched_or_ambiguous_count"] == 0 else 2

    receipt = book_exact_selections(
        selections_path=args.selections,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "shareCode": receipt["shareCode"],
                "shareURL": receipt["shareURL"],
                "selection_count": receipt["selection_count"],
                "wager_placed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
