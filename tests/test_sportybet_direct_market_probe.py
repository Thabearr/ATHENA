from __future__ import annotations

import pytest

from scripts.sportybet_direct_market_probe import (
    DirectMarketProbeError,
    SELECTION_SPECS,
    _find_market,
)


def test_required_market_mapping_is_exact():
    assert SELECTION_SPECS["AWAY_1UP"] == ("60200", None, "3")
    assert SELECTION_SPECS["HOME_1UP"] == ("60200", None, "1")
    assert SELECTION_SPECS["HOME_2UP"] == ("60100", None, "1")
    assert SELECTION_SPECS["TOTAL_GOALS_OVER_1_5"] == (
        "18",
        "total=1.5",
        "12",
    )
    assert SELECTION_SPECS["HOME_TEAM_TOTAL_OVER_0_5"] == (
        "19",
        "total=0.5",
        "12",
    )
    assert SELECTION_SPECS["AWAY_TEAM_TOTAL_OVER_0_5"] == (
        "20",
        "total=0.5",
        "12",
    )


def test_find_market_requires_exact_market_specifier_outcome():
    payload = {
        "data": {
            "markets": [
                {
                    "id": "18",
                    "specifier": "total=1.5",
                    "desc": "Over/Under",
                    "outcomes": [
                        {"id": "12", "desc": "Over 1.5", "odds": "1.31", "isActive": 1}
                    ],
                }
            ]
        }
    }
    result = _find_market(payload, "18", "total=1.5", "12")
    assert result["odds"] == "1.31"
    assert result["outcome_description"] == "Over 1.5"


def test_find_market_rejects_inactive_outcome():
    payload = {
        "markets": [
            {
                "id": "1",
                "outcomes": [{"id": "3", "odds": "1.40", "isActive": 0}],
            }
        ]
    }
    with pytest.raises(DirectMarketProbeError, match="inactive"):
        _find_market(payload, "1", None, "3")
