from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from domain import current_shadow_sportybet_tolerant_live_inventory as tolerant
from domain import sportybet_live_event_quote_evidence as live


EVENT = "sr:match:123456"
OBSERVED = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)
KICKOFF = OBSERVED + timedelta(hours=4)


def _raw(*, good: bool = True) -> bytes:
    outcomes = []
    if good:
        outcomes.append(
            {"id": "O", "desc": "Over 2.5", "odds": "1.90", "isActive": 1}
        )
    outcomes.extend(
        (
            {"id": "BAD", "desc": "Broken price", "odds": "not-a-price", "isActive": 1},
            {"id": "BAD2", "desc": "Broken active", "odds": "1.80", "isActive": "maybe"},
        )
    )
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
                    {
                        "id": "18",
                        "desc": "Total Goals",
                        "specifier": "total=2.5",
                        "outcomes": outcomes,
                    }
                ],
            }
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _capture(monkeypatch, tmp_path, raw):
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: (raw, 200, OBSERVED),
    )
    return live.capture_live_event_quote_evidence(
        event_id=EVENT,
        repository_root=tmp_path,
        execute_live_network=True,
    )


def test_one_malformed_provider_outcome_cannot_poison_valid_fixture_quotes(monkeypatch, tmp_path):
    raw = _raw(good=True)
    directory, manifest = _capture(monkeypatch, tmp_path, raw)

    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError):
        live.build_live_event_quote_inventory(directory, repository_root=tmp_path)

    inventory = tolerant.build_shadow_live_event_quote_inventory(
        directory,
        repository_root=tmp_path,
    )
    assert inventory.event_id == EVENT
    assert inventory.source_raw_sha256 == manifest.raw_sha256
    assert inventory.source_manifest_sha256 == live.manifest_sha256(manifest)
    assert len(inventory.selections) == 1
    selection = inventory.selections[0]
    assert selection.market_id == "18"
    assert selection.outcome_id == "O"
    assert selection.odds_raw == "1.90"
    assert selection.odds_decimal == 1.9
    assert (directory / live.RAW_FILENAME).read_bytes() == raw


def test_all_malformed_provider_outcomes_still_fail_closed(monkeypatch, tmp_path):
    directory, _manifest = _capture(monkeypatch, tmp_path, _raw(good=False))
    with pytest.raises(
        live.SportyBetLiveEventQuoteEvidenceError,
        match="no valid priced selections",
    ):
        tolerant.build_shadow_live_event_quote_inventory(
            directory,
            repository_root=tmp_path,
        )


def test_tolerant_policy_never_claims_normalization_repair_or_downstream_authority():
    policy = tolerant.policy_summary()
    assert policy["schema_version"] == tolerant.SCHEMA_VERSION
    assert policy["policy_id"] == tolerant.POLICY_ID
    assert policy["event_identity_unchanged"] is True
    assert policy["raw_and_manifest_unchanged"] is True
    assert policy["normalization_performed"] is False
    assert policy["repair_performed"] is False
    assert policy["inference_performed"] is False
    assert policy["synthetic_price_allowed"] is False
    assert policy["wager_placed"] is False
