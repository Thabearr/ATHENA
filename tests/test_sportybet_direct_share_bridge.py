from __future__ import annotations

import pytest

from scripts.sportybet_direct_share_bridge import (
    CREATE_PATH,
    LOAD_PREFIX,
    SPORTYBET_OPER_ID,
    SportyBetDirectShareError,
    extract_share_code,
    validate_selections,
)


def test_contract_constants_match_preserved_client_contract():
    assert SPORTYBET_OPER_ID == "2"
    assert CREATE_PATH == "/orders/share?throwInvalidEvent=true"
    assert LOAD_PREFIX == "/orders/share/"


def test_validate_one_provider_native_selection():
    rows = validate_selections(
        [
            {
                "eventId": "sr:match:72221158",
                "marketId": "18",
                "outcomeId": "12",
                "specifier": "total=1.5",
            }
        ]
    )
    assert rows == (
        {
            "eventId": "sr:match:72221158",
            "marketId": "18",
            "outcomeId": "12",
            "specifier": "total=1.5",
        },
    )


def test_reject_duplicate_event():
    with pytest.raises(SportyBetDirectShareError, match="one selection per event"):
        validate_selections(
            [
                {"eventId": "sr:match:1", "marketId": "1", "outcomeId": "1"},
                {"eventId": "sr:match:1", "marketId": "18", "outcomeId": "12"},
            ]
        )


def test_reject_unreviewed_fields():
    with pytest.raises(SportyBetDirectShareError, match="unsupported fields"):
        validate_selections(
            [
                {
                    "eventId": "sr:match:1",
                    "marketId": "1",
                    "outcomeId": "1",
                    "odds": "2.00",
                }
            ]
        )


def test_extract_share_code_requires_success():
    with pytest.raises(SportyBetDirectShareError, match="bizCode"):
        extract_share_code({"bizCode": 12345, "data": {"shareCode": "ABC123"}})


def test_extract_share_code_accepts_explicit_share_code():
    assert extract_share_code(
        {"bizCode": 10000, "data": {"shareCode": "ABC123"}}
    ) == "ABC123"
