from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import domain.live_fotmob_fixture_intelligence as live
from domain.live_fotmob_fixture_intelligence import (
    LiveFotMobFixtureIntelligenceError,
    persist_live_fotmob_evidence,
)
from workers.fotmob_advanced_scraper import FotMobAdvancedScraper


OBSERVED = dt.datetime(2026, 8, 27, 6, 40, tzinfo=dt.timezone.utc)
KICKOFF = "2026-08-27T18:00:00Z"
FIXTURE_ID = 123456


def _fixture_payload() -> dict:
    return {
        "leagues": [
            {
                "id": 1,
                "name": "Premier League",
                "matches": [
                    {
                        "id": FIXTURE_ID,
                        "home": {"id": 10, "longName": "Home FC"},
                        "away": {"id": 20, "longName": "Away FC"},
                        "status": {"utcTime": KICKOFF, "started": False},
                    }
                ],
            }
        ]
    }


def _details_payload() -> dict:
    return {
        "general": {"matchId": FIXTURE_ID},
        "content": {
            "matchFacts": {
                "teamForm": [
                    {"recentResults": [{"resultString": "Win", "against": "A"}]},
                    {"recentResults": [{"resultString": "Loss", "against": "B"}]},
                ]
            }
        },
    }


def _scraper(client) -> FotMobAdvancedScraper:
    scraper = FotMobAdvancedScraper.__new__(FotMobAdvancedScraper)
    scraper.client = client
    return scraper


class _RawFixtureFailureClient:
    def __init__(self):
        self.raw_calls = 0
        self.legacy_calls = 0

    def fetch_matches_by_date_with_raw(self, _date: str):
        self.raw_calls += 1
        return None

    def fetch_matches_by_date(self, _date: str):
        self.legacy_calls += 1
        return _fixture_payload()


def test_raw_aware_fixture_failure_never_refetches_uncaptured_response() -> None:
    client = _RawFixtureFailureClient()
    scraper = _scraper(client)

    assert scraper.fetch_upcoming_matches(days_ahead=1) == []
    assert client.raw_calls == 2
    assert client.legacy_calls == 0


class _RawDetailsFailureClient:
    def __init__(self):
        self.raw_calls = 0
        self.legacy_calls = 0

    def fetch_match_details_with_raw(self, _fixture_id: int):
        self.raw_calls += 1
        return None

    def fetch_match_details(self, _fixture_id: int):
        self.legacy_calls += 1
        return _details_payload()


def test_raw_aware_details_failure_never_refetches_uncaptured_response() -> None:
    client = _RawDetailsFailureClient()
    scraper = _scraper(client)

    assert scraper.enrich_match(FIXTURE_ID) == {}
    assert client.raw_calls == 1
    assert client.legacy_calls == 0


class _RawClient:
    def fetch_matches_by_date_with_raw(self, date: str):
        payload = _fixture_payload()
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return (
            payload,
            raw,
            OBSERVED,
            f"https://www.fotmob.com/api/data/matches?date={date}",
        )

    def fetch_match_details_with_raw(self, fixture_id: int):
        payload = _details_payload()
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return (
            payload,
            raw,
            OBSERVED,
            f"https://www.fotmob.com/api/data/matchDetails?matchId={fixture_id}",
        )


def _raise_capture_error(**_kwargs):
    raise LiveFotMobFixtureIntelligenceError("forced capture publication failure")


def test_fixture_capture_failure_blocks_normalization() -> None:
    scraper = _scraper(_RawClient())
    scraper._capture = _raise_capture_error

    assert scraper.fetch_upcoming_matches(days_ahead=1) == []


def test_match_details_capture_failure_blocks_form_normalization() -> None:
    scraper = _scraper(_RawClient())
    scraper._capture = _raise_capture_error

    assert scraper.enrich_match(FIXTURE_ID) == {}


class _LegacyClientWithoutRawMethods:
    def __init__(self):
        self.fixture_calls = 0
        self.details_calls = 0

    def fetch_matches_by_date(self, _date: str):
        self.fixture_calls += 1
        return _fixture_payload()

    def fetch_match_details(self, _fixture_id: int):
        self.details_calls += 1
        return _details_payload()


def test_client_that_genuinely_lacks_raw_methods_keeps_legacy_fallback() -> None:
    client = _LegacyClientWithoutRawMethods()
    scraper = _scraper(client)

    fixtures = scraper.fetch_upcoming_matches(days_ahead=1)
    details = scraper.enrich_match(FIXTURE_ID)

    assert fixtures
    assert client.fixture_calls == 2
    assert all("fotmob_fixture_evidence" not in fixture for fixture in fixtures)
    assert details["home_form"]["summary"] == "W"
    assert details["away_form"]["summary"] == "L"
    assert "fotmob_match_details_evidence" not in details
    assert client.details_calls == 1


def test_compatibility_capture_rejects_oversized_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "MAX_RESPONSE_BYTES", 8)

    with pytest.raises(
        LiveFotMobFixtureIntelligenceError,
        match="8 MiB compatibility capture limit",
    ):
        persist_live_fotmob_evidence(
            kind="FIXTURE_LIST",
            fixture_identifier=None,
            source_reference="https://www.fotmob.com/api/data/matches?date=20260827",
            observed_at=OBSERVED,
            raw_bytes=b'{"long":12345}',
            repository_root=tmp_path,
        )

    assert not (tmp_path / live.EVIDENCE_ROOT).exists()


def test_runtime_evidence_root_is_git_ignored() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    ignore_lines = {
        line.strip()
        for line in (repository_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    assert ".cache/athena-runtime/" in ignore_lines
