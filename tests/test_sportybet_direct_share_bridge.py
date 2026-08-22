from __future__ import annotations

import pytest

from scripts.sportybet_direct_share_bridge import (
    CREATE_PATH,
    LOAD_PREFIX,
    SPORTYBET_COUNTRY_PREFIX,
    SPORTYBET_OPER_ID,
    SportyBetDirectShareError,
    _validate_exact_roundtrip,
    extract_share_code,
    validate_selections,
)


def test_contract_constants_match_preserved_client_network_contract():
    assert SPORTYBET_COUNTRY_PREFIX == "ng"
    assert SPORTYBET_OPER_ID == "2"
    assert CREATE_PATH == "/api/ng/orders/share?throwInvalidEvent=true"
    assert LOAD_PREFIX == "/api/ng/orders/share/"


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
        {
            "bizCode": 10000,
            "data": {"shareCode": "ABC123", "unavailableOutcomes": []},
        }
    ) == "ABC123"


def test_exact_roundtrip_rejects_changed_provider_identity():
    requested = (
        {
            "eventId": "sr:match:1",
            "marketId": "18",
            "outcomeId": "12",
            "specifier": "total=1.5",
        },
    )
    create_payload = {
        "bizCode": 10000,
        "data": {"outcomes": [{}], "unavailableOutcomes": []},
    }
    load_payload = {
        "bizCode": 10000,
        "data": {
            "outcomes": [{}],
            "unavailableOutcomes": [],
            "ticket": {
                "selections": [
                    {
                        "eventId": "sr:match:1",
                        "marketId": "18",
                        "outcomeId": "13",
                        "specifier": "total=1.5",
                    }
                ]
            },
        },
    }
    with pytest.raises(SportyBetDirectShareError, match="identities"):
        _validate_exact_roundtrip(
            requested=requested,
            create_payload=create_payload,
            load_payload=load_payload,
        )
