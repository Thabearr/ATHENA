from __future__ import annotations

from pathlib import Path

import pytest

from scripts import sportybet_semantic_share_bridge as semantic


def _intent(**overrides):
    row = {
        "eventId": "sr:match:123456",
        "homeTeamName": "Porto",
        "awayTeamName": "FC Arouca",
        "marketName": "1X2",
        "outcomeName": "Home",
        "specifier": None,
    }
    row.update(overrides)
    return row


def _event(*, markets=None, **overrides):
    value = {
        "eventId": "sr:match:123456",
        "homeTeamName": "Porto",
        "awayTeamName": "FC Arouca",
        "estimateStartTime": 9_999_999_999_999,
        "bookingStatus": "Available",
        "status": 0,
        "matchStatus": "Not Started",
        "markets": markets
        if markets is not None
        else [
            {
                "id": "1",
                "desc": "1X2",
                "specifier": None,
                "outcomes": [
                    {"id": "1", "desc": "Home", "odds": "1.29", "isActive": 1},
                    {"id": "2", "desc": "Draw", "odds": "5.00", "isActive": 1},
                    {"id": "3", "desc": "Away", "odds": "8.00", "isActive": 1},
                ],
            }
        ],
    }
    value.update(overrides)
    return value


def test_validate_intents_rejects_caller_supplied_provider_native_ids():
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="caller-supplied provider-native fields",
    ):
        semantic.validate_intents([
            _intent(marketId="1", outcomeId="1")
        ])


def test_validate_intents_rejects_duplicate_event():
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="one intent per event",
    ):
        semantic.validate_intents([_intent(), _intent()])


def test_resolve_intent_derives_native_ids_from_semantics():
    selection, audit = semantic.resolve_intent(
        event=_event(),
        intent=semantic.validate_intents([_intent()])[0],
        minimum_lead_seconds=0,
    )
    assert selection == {
        "eventId": "sr:match:123456",
        "marketId": "1",
        "outcomeId": "1",
    }
    assert audit["observed_market_name"] == "1X2"
    assert audit["observed_outcome_name"] == "Home"
    assert audit["selection_semantics_verified"] is True


def test_resolve_intent_rejects_fixture_name_mismatch():
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="home-team semantic mismatch",
    ):
        semantic.resolve_intent(
            event=_event(homeTeamName="Benfica"),
            intent=semantic.validate_intents([_intent()])[0],
            minimum_lead_seconds=0,
        )


def test_resolve_intent_rejects_wrong_market_or_outcome_semantics():
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="expected exactly one live match",
    ):
        semantic.resolve_intent(
            event=_event(),
            intent=semantic.validate_intents([
                _intent(outcomeName="Away")
            ])[0],
            minimum_lead_seconds=0,
        )


def test_resolve_intent_requires_exact_line_specifier():
    markets = [
        {
            "id": "18",
            "desc": "Over/Under",
            "specifier": "total=1.5",
            "outcomes": [
                {"id": "12", "desc": "Over 1.5", "odds": "1.17", "isActive": 1},
                {"id": "13", "desc": "Under 1.5", "odds": "4.20", "isActive": 1},
            ],
        }
    ]
    good = semantic.validate_intents([
        _intent(
            marketName="Over/Under",
            outcomeName="Over 1.5",
            specifier="total=1.5",
        )
    ])[0]
    selection, _ = semantic.resolve_intent(
        event=_event(markets=markets),
        intent=good,
        minimum_lead_seconds=0,
    )
    assert selection == {
        "eventId": "sr:match:123456",
        "marketId": "18",
        "outcomeId": "12",
        "specifier": "total=1.5",
    }

    bad = semantic.validate_intents([
        _intent(
            marketName="Over/Under",
            outcomeName="Over 1.5",
            specifier="total=2.5",
        )
    ])[0]
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="expected exactly one live match",
    ):
        semantic.resolve_intent(
            event=_event(markets=markets),
            intent=bad,
            minimum_lead_seconds=0,
        )


def test_resolve_intent_rejects_inactive_outcome():
    markets = [
        {
            "id": "10",
            "desc": "Double Chance",
            "specifier": None,
            "outcomes": [
                {
                    "id": "9",
                    "desc": "Home or Draw",
                    "odds": "1.20",
                    "isActive": 0,
                }
            ],
        }
    ]
    intent = semantic.validate_intents([
        _intent(marketName="Double Chance", outcomeName="Home or Draw")
    ])[0]
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="expected exactly one live match",
    ):
        semantic.resolve_intent(
            event=_event(markets=markets),
            intent=intent,
            minimum_lead_seconds=0,
        )


def test_resolve_intent_fails_closed_on_ambiguous_semantic_match():
    duplicated_market = {
        "id": "1",
        "desc": "1X2",
        "specifier": None,
        "outcomes": [{"id": "1", "desc": "Home", "odds": "1.30", "isActive": 1}],
    }
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="found 2",
    ):
        semantic.resolve_intent(
            event=_event(markets=[duplicated_market, dict(duplicated_market)]),
            intent=semantic.validate_intents([_intent()])[0],
            minimum_lead_seconds=0,
        )


def test_resolve_intent_rejects_live_or_too_close_event():
    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="not safely pre-match",
    ):
        semantic.resolve_intent(
            event=_event(estimateStartTime=1),
            intent=semantic.validate_intents([_intent()])[0],
            minimum_lead_seconds=120,
        )


def test_create_semantic_share_code_binds_transport_to_resolved_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    intents = semantic.validate_intents([_intent()])

    def fake_resolve_live_intents(**kwargs):
        return (
            (
                {
                    "eventId": "sr:match:123456",
                    "marketId": "1",
                    "outcomeId": "1",
                },
            ),
            {
                "intent_count": 1,
                "resolved_count": 1,
            },
        )

    def fake_roundtrip(**kwargs):
        return {
            "selection_count": 2,
            "exact_roundtrip_selection_identity_verified": True,
            "shareCode": "ABC123",
            "shareURL": "https://example.invalid/ABC123",
            "combined_odds": "1.29",
        }

    monkeypatch.setattr(semantic, "resolve_live_intents", fake_resolve_live_intents)
    monkeypatch.setattr(semantic.transport, "create_and_roundtrip", fake_roundtrip)

    with pytest.raises(
        semantic.SportyBetSemanticShareError,
        match="selection count drifted",
    ):
        semantic.create_semantic_share_code(
            intents=intents,
            output_dir=tmp_path,
            minimum_lead_seconds=0,
            delay_seconds=0,
        )
