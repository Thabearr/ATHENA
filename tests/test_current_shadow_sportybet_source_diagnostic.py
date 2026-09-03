from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from scripts import capture_current_shadow_sportybet_source_diagnostic as diagnostic


UTC = timezone.utc
OBSERVED = datetime(2026, 9, 3, 9, 45, tzinfo=UTC)


def _raw(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _catalog():
    return _raw(
        {
            "bizCode": 10000,
            "data": [
                {
                    "id": diagnostic.fanout.FOOTBALL_SPORT_ID,
                    "name": "Football",
                    "categories": [
                        {
                            "id": "sr:category:1",
                            "name": "England",
                            "tournaments": [
                                {
                                    "id": "sr:tournament:100",
                                    "name": "League A",
                                    "eventSize": 2,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _event(event_id: str, *, home: str):
    return {
        "eventId": event_id,
        "sportId": diagnostic.fanout.FOOTBALL_SPORT_ID,
        "homeTeamName": home,
        "awayTeamName": "Away",
        "tournamentName": "League A",
        "estimateStartTime": 1788436800000,
        "bookingStatus": "Open",
        "status": 0,
        "matchStatus": "Not started",
    }


def test_diagnostic_preserves_exact_rejected_raw_without_authority(monkeypatch, tmp_path):
    catalog = _catalog()
    tournament = _raw(
        {
            "bizCode": 10000,
            "data": [
                _event("sr:match:123", home="Home"),
                _event("sr:match:124", home="Provider Name "),
            ],
        }
    )

    def fake_get(target):
        if target == diagnostic.fanout.catalog_request_target():
            return catalog, OBSERVED
        return tournament, OBSERVED

    monkeypatch.setattr(diagnostic.fanout, "_network_get", fake_get)
    monkeypatch.setattr(diagnostic.time, "time", lambda: OBSERVED.timestamp() - 1)

    output = tmp_path / "diagnostic"
    manifest = diagnostic.capture_source_diagnostic(output_dir=output)

    assert (output / "catalog.raw.json").read_bytes() == catalog
    observation = manifest["observations"][0]
    raw_path = output / observation["raw_filename"]
    assert raw_path.read_bytes() == tournament
    assert observation["raw_sha256"] == hashlib.sha256(tournament).hexdigest()
    assert observation["parse_status"] == "REVIEWED_PARSER_REJECTED"
    assert observation["fixture_reconciliation_authorized"] is False
    assert len(observation["row_failures"]) == 1
    failure = observation["row_failures"][0]
    assert failure["eventId"] == "sr:match:124"
    assert failure["homeTeamName"] == "Provider Name "
    assert failure["error_message"] == "home_team_name must be an exact non-empty trimmed string"
    assert failure["fixture_reconciliation_authorized"] is False
    assert all(value is False for value in manifest["authority"].values())

    replayed_manifest = json.loads((output / "manifest.json").read_text("utf-8"))
    assert replayed_manifest == manifest


def test_diagnostic_accepts_reviewed_parser_rows_without_promoting_authority(
    monkeypatch, tmp_path
):
    catalog = _catalog()
    tournament = _raw(
        {
            "bizCode": 10000,
            "data": [_event("sr:match:123", home="Home")],
        }
    )

    def fake_get(target):
        if target == diagnostic.fanout.catalog_request_target():
            return catalog, OBSERVED
        return tournament, OBSERVED

    monkeypatch.setattr(diagnostic.fanout, "_network_get", fake_get)
    monkeypatch.setattr(diagnostic.time, "time", lambda: OBSERVED.timestamp() - 1)

    manifest = diagnostic.capture_source_diagnostic(
        output_dir=tmp_path / "diagnostic"
    )
    observation = manifest["observations"][0]
    assert observation["parse_status"] == "REVIEWED_PARSER_ACCEPTED"
    assert observation["accepted_event_count"] == 1
    assert observation["row_failures"] == []
    assert observation["fixture_reconciliation_authorized"] is False
    assert manifest["authority"]["wager_placed"] is False
