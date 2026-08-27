from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from database.database import Database
from domain.fixture_state_v2 import FixtureStateFieldId, FixtureStateStatus, build_fixture_state_v2_snapshot
from domain.live_fotmob_fixture_intelligence import (
    LiveFotMobFixtureIntelligenceError,
    issue_live_fotmob_fixture_intelligence,
)
from workers.fotmob_advanced_scraper import FotMobAdvancedScraper


OBSERVED = dt.datetime(2026, 8, 27, 2, 16, tzinfo=dt.timezone.utc)
KICKOFF = "2026-08-27T18:00:00Z"


class _Client:
    def __init__(self, fixture_raw: bytes, detail_raw: bytes):
        self.fixture_raw = fixture_raw
        self.detail_raw = detail_raw
        self.fixture_calls = 0

    def fetch_matches_by_date_with_raw(self, _date: str):
        self.fixture_calls += 1
        if self.fixture_calls > 1:
            return {}, b"{}", OBSERVED, "https://www.fotmob.com/api/data/matches?date=20260828"
        return json.loads(self.fixture_raw), self.fixture_raw, OBSERVED, "https://www.fotmob.com/api/data/matches?date=20260827"

    def fetch_match_details_with_raw(self, _fixture_id: int):
        return json.loads(self.detail_raw), self.detail_raw, OBSERVED, "https://www.fotmob.com/api/data/matchDetails?matchId=123456"


def _raws(include_away: bool = True) -> tuple[bytes, bytes]:
    fixture = {"leagues": [{"id": 1, "name": "Premier League", "matches": [{
        "id": 123456, "home": {"id": 10, "longName": "Home FC"},
        "away": {"id": 20, "longName": "Away FC"},
        "status": {"utcTime": KICKOFF, "started": False},
    }]}]}
    forms = [
        {"recentResults": [{"resultString": "Win", "against": "A"}, {"resultString": "Draw", "against": "B"}]},
    ]
    if include_away:
        forms.append({"recentResults": [{"resultString": "Loss", "against": "C"}]})
    detail = {"general": {"matchId": 123456}, "content": {"matchFacts": {"teamForm": forms}}}
    return json.dumps(fixture, separators=(",", ":")).encode(), json.dumps(detail, separators=(",", ":")).encode()


def _runtime(tmp_path: Path, *, include_away: bool = True):
    fixture_raw, detail_raw = _raws(include_away)
    scraper = FotMobAdvancedScraper.__new__(FotMobAdvancedScraper)
    scraper.client = _Client(fixture_raw, detail_raw)
    scraper.db = Database(str(tmp_path / "athena.db"))
    scraper.db.initialize()
    scraper._repository_root = lambda: tmp_path
    fixtures = scraper.fetch_upcoming_matches(days_ahead=1)
    assert len(fixtures) == 1
    details = scraper.enrich_match(123456)
    fixtures[0].update(details)
    assert scraper.sync_to_db(fixtures)
    return scraper, fixtures[0]


def test_actual_runtime_shape_is_preserved_then_issued_from_raw_evidence(tmp_path: Path) -> None:
    _scraper, fixture = _runtime(tmp_path)
    snapshot = issue_live_fotmob_fixture_intelligence(
        fixture_evidence=fixture["fotmob_fixture_evidence"],
        match_details_evidence=fixture["fotmob_match_details_evidence"], repository_root=tmp_path,
    )
    facts = {fact.field: fact for fact in snapshot.facts}
    canonical_values = {fact["field"]: fact["value"] for fact in snapshot.to_dict()["facts"]}
    assert fixture["home_form"] == {"matches": [{"result": "Win", "opponent": "A"}, {"result": "Draw", "opponent": "B"}], "summary": "WD"}
    assert fixture["away_form"] == {"matches": [{"result": "Loss", "opponent": "C"}], "summary": "L"}
    assert fixture["current_form_observed_at"] == OBSERVED.isoformat()
    # Facts are deliberately frozen internally; canonical serialization must
    # still preserve the exact runtime JSON extracted from the source bytes.
    assert canonical_values["home_form"] == fixture["home_form"]
    assert canonical_values["away_form"] == fixture["away_form"]
    assert facts["home_form"].evidence_sha256 == fixture["fotmob_match_details_evidence"].evidence_sha256
    assert facts["home_form"].observed_at == OBSERVED
    with sqlite3.connect(_scraper.db.db_path) as connection:
        row = connection.execute(
            "SELECT home_form, away_form, match_details_evidence_sha256 "
            "FROM fixture_extended WHERE fixture_id=123456"
        ).fetchone()
    assert json.loads(row[0]) == fixture["home_form"]
    assert json.loads(row[1]) == fixture["away_form"]
    assert row[2] == facts["home_form"].evidence_sha256
    state = build_fixture_state_v2_snapshot(snapshot)
    assert state.field_index[FixtureStateFieldId.HOME_FORM].status is FixtureStateStatus.BLOCKED


def test_db_normalized_values_are_not_canonical_authority(tmp_path: Path) -> None:
    _scraper, fixture = _runtime(tmp_path)
    with pytest.raises(LiveFotMobFixtureIntelligenceError):
        issue_live_fotmob_fixture_intelligence(
            fixture_evidence=dataclasses.replace(fixture["fotmob_fixture_evidence"], evidence_directory=Path("fixture_extended")),
            match_details_evidence=fixture["fotmob_match_details_evidence"], repository_root=tmp_path,
        )


def test_raw_hash_or_evidence_path_mutation_fails_closed(tmp_path: Path) -> None:
    _scraper, fixture = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    raw_path = tmp_path / receipt.evidence_directory / "response.json"
    raw_path.write_bytes(b'{"tampered":true}')
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="SHA"):
        issue_live_fotmob_fixture_intelligence(
            fixture_evidence=fixture["fotmob_fixture_evidence"], match_details_evidence=receipt, repository_root=tmp_path,
        )


def test_absent_form_remains_unknown_not_inferred(tmp_path: Path) -> None:
    _scraper, fixture = _runtime(tmp_path, include_away=False)
    snapshot = issue_live_fotmob_fixture_intelligence(
        fixture_evidence=fixture["fotmob_fixture_evidence"],
        match_details_evidence=fixture["fotmob_match_details_evidence"], repository_root=tmp_path,
    )
    assert {fact.field for fact in snapshot.facts} == {"home_form", "live_fixture_context"}


def test_snapshot_is_deterministic_for_exact_runtime_evidence(tmp_path: Path) -> None:
    _scraper, fixture = _runtime(tmp_path)
    first = issue_live_fotmob_fixture_intelligence(
        fixture_evidence=fixture["fotmob_fixture_evidence"], match_details_evidence=fixture["fotmob_match_details_evidence"], repository_root=tmp_path,
    )
    second = issue_live_fotmob_fixture_intelligence(
        fixture_evidence=fixture["fotmob_fixture_evidence"], match_details_evidence=fixture["fotmob_match_details_evidence"], repository_root=tmp_path,
    )
    assert first == second
