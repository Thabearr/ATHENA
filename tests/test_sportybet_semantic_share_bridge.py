from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import sportybet_semantic_share_bridge as semantic


FUTURE_KICKOFF_MS = 4_102_444_800_000


def _intent(**overrides):
    row = {
        "eventId": "sr:match:12345",
        "homeTeamName": "Atletico Madrid",
        "awayTeamName": "Villarreal",
        "marketLabel": "Double Chance",
        "outcomeLabel": "Home or Draw",
    }
    row.update(overrides)
    return row


def _payload(*, market_id: str = "10", duplicate_double_chance: bool = False):
    double_chance = {
        "id": market_id,
        "desc": "Double Chance",
        "specifier": None,
        "status": 0,
        "outcomes": [
            {"id": "9", "desc": "Home or Draw", "odds": "1.24", "isActive": 1},
            {"id": "10", "desc": "Home or Away", "odds": "1.36", "isActive": 1},
            {"id": "11", "desc": "Draw or Away", "odds": "1.61", "isActive": 1},
        ],
    }
    markets = [
        double_chance,
        {
            "id": "19",
            "desc": "Atletico Madrid Over/Under",
            "specifier": "total=0.5",
            "status": 0,
            "outcomes": [
                {"id": "12", "desc": "Over 0.5", "odds": "1.16", "isActive": 1}
            ],
        },
        {
            "id": "18",
            "desc": "Over/Under",
            "specifier": "total=3.5",
            "status": 0,
            "outcomes": [
                {"id": "13", "desc": "Under 3.5", "odds": "1.21", "isActive": 1}
            ],
        },
    ]
    if duplicate_double_chance:
        markets.append(json.loads(json.dumps(double_chance)))
    event = {
        "eventId": "sr:match:12345",
        "homeTeamName": "Atletico Madrid",
        "awayTeamName": "Villarreal",
        "estimateStartTime": FUTURE_KICKOFF_MS,
        "bookingStatus": "Booked",
        "status": 0,
        "matchStatus": "Not start",
        "markets": markets,
    }
    return {"bizCode": 10000, "data": {"event": event}}


def test_validate_intents_refuses_provider_native_market_and_outcome_ids():
    raw = _intent(marketId="19", outcomeId="12")
    with pytest.raises(semantic.SportyBetSemanticShareError, match="unsupported fields"):
        semantic.validate_intents([raw])


def test_resolver_uses_exact_semantic_selection_not_an_unrelated_native_pick():
    intent = semantic.validate_intents([_intent()])[0]
    selection, audit = semantic.resolve_intent_from_payload(
        intent,
        _payload(),
        now_ms=0,
    )
    assert selection == {
        "eventId": "sr:match:12345",
        "marketId": "10",
        "outcomeId": "9",
    }
    assert audit["marketLabel"] == "Double Chance"
    assert audit["outcomeLabel"] == "Home or Draw"
    # The payload also contains a shorter-priced team-goal selection.  The semantic
    # gate must never substitute it merely because its native identity is valid.
    assert selection["marketId"] != "19"


def test_resolver_binds_exact_fixture_identity_before_market_resolution():
    intent = semantic.validate_intents(
        [_intent(homeTeamName="Wrong Atletico")]
    )[0]
    with pytest.raises(semantic.SportyBetSemanticShareError, match="home fixture identity mismatch"):
        semantic.resolve_intent_from_payload(intent, _payload(), now_ms=0)


def test_resolver_requires_exact_market_line_specifier():
    intent = semantic.validate_intents(
        [
            _intent(
                marketLabel="Over/Under",
                outcomeLabel="Under 3.5",
                specifier="total=2.5",
            )
        ]
    )[0]
    with pytest.raises(semantic.SportyBetSemanticShareError, match="found 0"):
        semantic.resolve_intent_from_payload(intent, _payload(), now_ms=0)


def test_resolver_rejects_ambiguous_duplicate_semantic_matches():
    intent = semantic.validate_intents([_intent()])[0]
    with pytest.raises(semantic.SportyBetSemanticShareError, match="found 2"):
        semantic.resolve_intent_from_payload(
            intent,
            _payload(duplicate_double_chance=True),
            now_ms=0,
        )


def test_resolver_rejects_event_without_safe_prematch_lead():
    intent = semantic.validate_intents([_intent()])[0]
    payload = _payload()
    event = payload["data"]["event"]
    event["estimateStartTime"] = 120_000
    with pytest.raises(semantic.SportyBetSemanticShareError, match="not safely pre-match"):
        semantic.resolve_intent_from_payload(
            intent,
            payload,
            now_ms=90_000,
            minimum_lead_seconds=60,
        )


def _native_stub(output_dir: Path, selections):
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "shareCode": "ABC123",
        "shareURL": "http://www.sportybet.com/ng/?shareCode=ABC123",
        "selection_count": len(selections),
        "combined_odds": "2.5",
        "exact_roundtrip_selection_identity_verified": True,
        "wager_placed": False,
    }
    (output_dir / "direct-share-proof-receipt.json").write_text(
        json.dumps(receipt, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def test_create_semantic_roundtrip_revalidates_same_native_identity_after_create(
    monkeypatch, tmp_path
):
    intents = semantic.validate_intents([_intent()])

    def fetcher(event_id):
        assert event_id == "sr:match:12345"
        raw = json.dumps(_payload(), sort_keys=True).encode()
        return _payload(), raw, 200, "https://example.invalid/event"

    def create_stub(*, selections, output_dir):
        assert selections == (
            {"eventId": "sr:match:12345", "marketId": "10", "outcomeId": "9"},
        )
        return _native_stub(output_dir, selections)

    monkeypatch.setattr(semantic.native_bridge, "create_and_roundtrip", create_stub)
    receipt = semantic.create_semantic_and_roundtrip(
        intents=intents,
        output_dir=tmp_path,
        fetcher=fetcher,
    )
    assert receipt["shareCode"] == "ABC123"
    assert receipt["semantic_fixture_market_outcome_line_verified"] is True
    assert receipt["post_roundtrip_semantic_revalidation_verified"] is True
    assert receipt["exact_roundtrip_selection_identity_verified"] is True
    assert receipt["wager_placed"] is False


def test_create_semantic_roundtrip_fails_if_semantic_native_identity_drifts(
    monkeypatch, tmp_path
):
    intents = semantic.validate_intents([_intent()])
    calls = 0

    def fetcher(event_id):
        nonlocal calls
        calls += 1
        payload = _payload(market_id="10" if calls == 1 else "99")
        raw = json.dumps(payload, sort_keys=True).encode()
        return payload, raw, 200, "https://example.invalid/event"

    def create_stub(*, selections, output_dir):
        return _native_stub(output_dir, selections)

    monkeypatch.setattr(semantic.native_bridge, "create_and_roundtrip", create_stub)
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="identity changed during semantic create/load round trip",
    ):
        semantic.create_semantic_and_roundtrip(
            intents=intents,
            output_dir=tmp_path,
            fetcher=fetcher,
        )
