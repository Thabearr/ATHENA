from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from domain import sportybet_live_event_quote_evidence as live


EVENT = "sr:match:71945206"
OBSERVED = datetime(2026, 8, 31, 8, 37, 0, tzinfo=timezone.utc)


def _raw_event(*, unnamed_market_desc=None) -> bytes:
    unnamed = {
        "id": "999",
        "outcomes": [
            {
                "id": "IGNORED",
                "desc": "Ignored outcome",
                "odds": "1.50",
                "isActive": 1,
            }
        ],
    }
    if unnamed_market_desc is not None:
        unnamed["desc"] = unnamed_market_desc
    payload = {
        "bizCode": 10000,
        "data": {
            "event": {
                "eventId": EVENT,
                "homeTeamName": "Home FC",
                "awayTeamName": "Away FC",
                "estimateStartTime": int((OBSERVED + timedelta(hours=2)).timestamp() * 1000),
                "bookingStatus": "Available",
                "status": 0,
                "matchStatus": "Not Started",
                "markets": [
                    unnamed,
                    {
                        "id": "18",
                        "desc": "Total Goals",
                        "specifier": "total=2.5",
                        "outcomes": [
                            {
                                "id": "O",
                                "desc": "Over 2.5",
                                "odds": "2.05",
                                "isActive": 1,
                            },
                            {
                                "id": "U",
                                "desc": "Under 2.5",
                                "odds": "1.80",
                                "isActive": 1,
                            },
                        ],
                    },
                ],
            }
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _capture(monkeypatch, tmp_path: Path, raw: bytes):
    monkeypatch.setattr(live, "_network_fetch", lambda event_id: (raw, 200, OBSERVED))
    return live.capture_live_event_quote_evidence(
        event_id=EVENT,
        repository_root=tmp_path,
        execute_live_network=True,
    )


def test_missing_provider_market_name_cannot_gain_semantic_authority_but_does_not_poison_named_markets(
    monkeypatch, tmp_path
):
    directory, _manifest = _capture(monkeypatch, tmp_path, _raw_event())

    inventory = live.build_live_event_quote_inventory(
        directory,
        repository_root=tmp_path,
    )

    assert {(row.market_id, row.outcome_id) for row in inventory.selections} == {
        ("18", "O"),
        ("18", "U"),
    }
    assert all(row.market_id != "999" for row in inventory.selections)


def test_nonempty_untrimmed_provider_market_name_still_fails_closed(monkeypatch, tmp_path):
    directory, _manifest = _capture(
        monkeypatch,
        tmp_path,
        _raw_event(unnamed_market_desc=" "),
    )

    with pytest.raises(
        live.SportyBetLiveEventQuoteEvidenceError,
        match="provider market name must be an exact non-empty trimmed string",
    ):
        live.build_live_event_quote_inventory(
            directory,
            repository_root=tmp_path,
        )
