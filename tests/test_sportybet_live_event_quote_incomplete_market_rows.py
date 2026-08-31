from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from domain import sportybet_live_event_quote_evidence as live


EVENT = "sr:match:123"
OBSERVED = datetime(2026, 8, 31, 8, 38, 0, tzinfo=timezone.utc)
KICKOFF = OBSERVED + timedelta(hours=4)


def _raw_event(*, placeholder_name_marker=...):
    placeholder = {
        "id": "999",
        "outcomes": [
            {"id": "X", "desc": "Placeholder", "odds": "2.00", "isActive": 1}
        ],
    }
    if placeholder_name_marker is not ...:
        placeholder["desc"] = placeholder_name_marker

    payload = {
        "bizCode": 10000,
        "data": {
            "event": {
                "eventId": EVENT,
                "homeTeamName": "Home FC",
                "awayTeamName": "Away FC",
                "estimateStartTime": int(KICKOFF.timestamp() * 1000),
                "bookingStatus": "Available",
                "status": 0,
                "matchStatus": "Not Started",
                "markets": [
                    placeholder,
                    {
                        "id": "18",
                        "desc": "Total Goals",
                        "specifier": "total=2.5",
                        "outcomes": [
                            {"id": "O", "desc": "Over 2.5", "odds": "2.05", "isActive": 1},
                            {"id": "U", "desc": "Under 2.5", "odds": "1.80", "isActive": 1},
                        ],
                    },
                ],
            }
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _inventory(monkeypatch, tmp_path, *, raw):
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: (raw, 200, OBSERVED),
    )
    directory, _manifest = live.capture_live_event_quote_evidence(
        event_id=EVENT,
        repository_root=tmp_path,
        execute_live_network=True,
    )
    return live.build_live_event_quote_inventory(
        directory,
        repository_root=tmp_path,
    )


def test_unnamed_provider_market_placeholder_cannot_poison_named_sibling_inventory(
    monkeypatch, tmp_path
):
    inventory = _inventory(monkeypatch, tmp_path, raw=_raw_event())

    assert {selection.market_id for selection in inventory.selections} == {"18"}
    assert {selection.market_name for selection in inventory.selections} == {"Total Goals"}
    assert {selection.outcome_id for selection in inventory.selections} == {"O", "U"}
    assert all(selection.market_id != "999" for selection in inventory.selections)


def test_present_malformed_provider_market_name_still_fails_closed(monkeypatch, tmp_path):
    with pytest.raises(
        live.SportyBetLiveEventQuoteEvidenceError,
        match="provider market name must be an exact non-empty trimmed string",
    ):
        _inventory(monkeypatch, tmp_path, raw=_raw_event(placeholder_name_marker=" "))
