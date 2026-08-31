from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.parse import parse_qs, urlsplit

from domain import current_shadow_sportybet_upcoming_reconciliation as current

UTC = timezone.utc
OBSERVED = datetime(2026, 8, 29, 6, 37, 52, 774398, tzinfo=UTC)
NONCE = int(OBSERVED.timestamp() * 1000) - 250
KICKOFF_MS = int(datetime(2026, 8, 29, 7, 0, tzinfo=UTC).timestamp() * 1000)


def _pr258_shape() -> bytes:
    return json.dumps(
        {
            "bizCode": 10000,
            "message": "0#0",
            "data": [
                {
                    "eventId": "sr:match:111111113587576",
                    "estimateStartTime": KICKOFF_MS,
                    "status": 0,
                    "matchStatus": "Not start",
                    "homeTeamName": "Seosan FC",
                    "awayTeamName": "Namyangju FC",
                    "sport": {
                        "id": "sr:sport:1",
                        "name": "Football",
                        "category": {
                            "id": "sr:category:291",
                            "name": "Republic of Korea",
                            "tournament": {
                                "id": "sr:tournament:48521",
                                "name": "K4 League",
                            },
                        },
                    },
                    "markets": [
                        {
                            "id": "18",
                            "specifier": "total=1.5",
                            "desc": "Over/Under",
                            "status": 0,
                            "outcomes": [
                                {"id": "12", "odds": "1.23", "isActive": 1, "desc": "Over 1.5"},
                                {"id": "13", "odds": "3.60", "isActive": 1, "desc": "Under 1.5"},
                            ],
                        }
                    ],
                }
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def test_contract_mirrors_exact_pr258_upcoming_path_without_changing_shared_contract():
    identity = current.validate_contract()
    assert current.UPCOMING_PATH == "/api/ng/factsCenter/wapConfigurableUpcomingEvents"
    assert identity["reviewed_reconciliation_contract_sha256"] == (
        "64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee"
    )
    assert current.EXPECTED_CONTRACT_SHA256 == current.calculate_contract_sha256()


def test_request_matches_pr258_public_anonymous_upcoming_shape():
    target = current.request_target(NONCE)
    parsed = urlsplit(target)
    assert parsed.path == "/api/ng/factsCenter/wapConfigurableUpcomingEvents"
    assert parse_qs(parsed.query) == {
        "sportId": ["sr:sport:1"],
        "_t": [str(NONCE)],
    }
    headers = dict(current.REQUEST_HEADERS)
    assert headers["OperId"] == "2"
    assert "Cookie" not in headers and "Authorization" not in headers


def test_exact_pr258_upcoming_row_preserves_identity_competition_and_kickoff():
    snapshot = current._parse_snapshot(
        _pr258_shape(), request_nonce_ms=NONCE, observed_at=OBSERVED
    )
    assert len(snapshot.events) == 1
    event = snapshot.events[0]
    assert event.event_id == "sr:match:111111113587576"
    assert event.home_team_name == "Seosan FC"
    assert event.away_team_name == "Namyangju FC"
    assert event.competition_name == "K4 League"
    assert event.competition_basis == "EVENT_NESTED_TOURNAMENT_NAME"
    assert event.kickoff_utc == datetime(2026, 8, 29, 7, 0, tzinfo=UTC)
    assert event.prematch_bookable_observed is True
    assert event.source_raw_sha256 == snapshot.raw_sha256
    assert event.source_observed_at == OBSERVED
