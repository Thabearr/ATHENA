from __future__ import annotations

import pytest

from scripts.sportybet_parse_bridge import (
    SportyBetParseBridgeError,
    _match_targets,
    _validate_booking_data,
    _validate_selection_rows,
    _validate_target_rows,
)


def test_target_validation_and_exact_matching():
    targets = _validate_target_rows(
        [
            {
                "target_id": "one",
                "home_names": ["Hull", "Hull City"],
                "away_names": ["Man United", "Manchester United"],
                "desired_selection": "AWAY_1UP",
            }
        ]
    )
    matched = _match_targets(
        targets,
        [
            {
                "event_id": "sr:match:123",
                "home_team": "Hull City",
                "away_team": "Manchester United",
                "start_time": 123,
                "match_status": "Not start",
                "_tournament_id": "sr:tournament:17",
                "_tournament_name": "Premier League",
                "_category": "England",
            }
        ],
    )
    assert matched[0]["match_state"] == "UNIQUE_EXACT_NAME_MATCH"
    assert matched[0]["event_id"] == "sr:match:123"


def test_target_matching_never_fuzzy_matches():
    targets = _validate_target_rows(
        [
            {
                "target_id": "one",
                "home_names": ["Hull"],
                "away_names": ["Man United"],
                "desired_selection": "AWAY_1UP",
            }
        ]
    )
    matched = _match_targets(
        targets,
        [
            {
                "event_id": "sr:match:123",
                "home_team": "Hull City",
                "away_team": "Manchester United",
            }
        ],
    )
    assert matched[0]["match_state"] == "UNMATCHED"


def test_selection_validation_rejects_duplicate_event():
    with pytest.raises(SportyBetParseBridgeError, match="at most one selection"):
        _validate_selection_rows(
            [
                {"eventId": "sr:match:1", "marketId": "1", "outcomeId": "1"},
                {
                    "eventId": "sr:match:1",
                    "marketId": "18",
                    "outcomeId": "12",
                    "specifier": "total=2.5",
                },
            ]
        )


def test_selection_validation_preserves_only_provider_native_fields():
    rows = _validate_selection_rows(
        [
            {
                "eventId": "sr:match:123",
                "marketId": "18",
                "outcomeId": "12",
                "specifier": "total=1.5",
            }
        ]
    )
    assert rows == (
        {
            "eventId": "sr:match:123",
            "marketId": "18",
            "outcomeId": "12",
            "specifier": "total=1.5",
        },
    )


def test_booking_response_must_accept_every_selection():
    with pytest.raises(SportyBetParseBridgeError, match="unavailable"):
        _validate_booking_data(
            {
                "shareCode": "ABC123",
                "shareURL": "https://www.sportybet.com/ng/m/?shareCode=ABC123",
                "outcomes": [{}],
                "unavailableOutcomes": [{}],
            },
            1,
        )


def test_booking_response_success():
    result = _validate_booking_data(
        {
            "shareCode": "ABC123",
            "shareURL": "https://www.sportybet.com/ng/m/?shareCode=ABC123",
            "deadline": 123456,
            "outcomes": [{"odds": "1.50"}, {"odds": "1.30"}],
            "unavailableOutcomes": [],
        },
        2,
    )
    assert result["shareCode"] == "ABC123"
    assert len(result["outcomes"]) == 2
