from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from database.database import Database
from domain.live_fotmob_fixture_intelligence import (
    CANONICAL_ISSUER_STATUS,
    EVIDENCE_ROOT,
    LiveFotMobFixtureIntelligenceError,
    issue_live_fotmob_fixture_intelligence,
    replay_live_fotmob_evidence,
)
from workers.fotmob_advanced_scraper import FotMobAdvancedScraper


OBSERVED = dt.datetime(2026, 8, 27, 2, 16, tzinfo=dt.timezone.utc)
KICKOFF = "2026-08-27T18:00:00Z"


class _Client:
    def __init__(self, fixture_raw: bytes, detail_raw: bytes):
        self.fixture_raw = fixture_raw
        self.detail_raw = detail_raw
        self.fixture_calls = 0

    def fetch_matches_by_date_with_raw(self, date: str):
        self.fixture_calls += 1
        if self.fixture_calls > 1:
            return {}, b"{}", OBSERVED, f"https://www.fotmob.com/api/data/matches?date={date}"
        return (
            json.loads(self.fixture_raw),
            self.fixture_raw,
            OBSERVED,
            f"https://www.fotmob.com/api/data/matches?date={date}",
        )

    def fetch_match_details_with_raw(self, fixture_id: int):
        return (
            json.loads(self.detail_raw),
            self.detail_raw,
            OBSERVED,
            f"https://www.fotmob.com/api/data/matchDetails?matchId={fixture_id}",
        )


def _raws(include_away: bool = True) -> tuple[bytes, bytes]:
    fixture = {
        "leagues": [
            {
                "id": 1,
                "name": "Premier League",
                "matches": [
                    {
                        "id": 123456,
                        "home": {"id": 10, "longName": "Home FC"},
                        "away": {"id": 20, "longName": "Away FC"},
                        "status": {"utcTime": KICKOFF, "started": False},
                    },
                    {
                        "id": 123457,
                        "home": {"id": 30, "longName": "Second Home"},
                        "away": {"id": 40, "longName": "Second Away"},
                        "status": {"utcTime": KICKOFF, "started": False},
                    },
                ],
            }
        ]
    }
    forms = [
        {
            "recentResults": [
                {"resultString": "Win", "against": "A"},
                {"resultString": "Draw", "against": "B"},
            ]
        }
    ]
    if include_away:
        forms.append(
            {"recentResults": [{"resultString": "Loss", "against": "C"}]}
        )
    detail = {
        "general": {"matchId": 123456},
        "content": {"matchFacts": {"teamForm": forms}},
    }
    return (
        json.dumps(fixture, separators=(",", ":")).encode(),
        json.dumps(detail, separators=(",", ":")).encode(),
    )


def _runtime(tmp_path: Path, *, include_away: bool = True):
    fixture_raw, detail_raw = _raws(include_away)
    scraper = FotMobAdvancedScraper.__new__(FotMobAdvancedScraper)
    scraper.client = _Client(fixture_raw, detail_raw)
    scraper.db = Database(str(tmp_path / "athena.db"))
    scraper.db.initialize()
    scraper._repository_root = lambda: tmp_path
    fixtures = scraper.fetch_upcoming_matches(days_ahead=1)
    assert len(fixtures) == 2
    target = next(item for item in fixtures if item["fixture_id"] == 123456)
    target.update(scraper.enrich_match(123456))
    assert scraper.sync_to_db(fixtures)
    return scraper, fixtures, target, fixture_raw, detail_raw


def test_actual_runtime_shape_is_preserved_from_exact_raw_evidence(tmp_path: Path) -> None:
    scraper, _fixtures, fixture, fixture_raw, detail_raw = _runtime(tmp_path)

    assert fixture["home_form"] == {
        "matches": [
            {"result": "Win", "opponent": "A"},
            {"result": "Draw", "opponent": "B"},
        ],
        "summary": "WD",
    }
    assert fixture["away_form"] == {
        "matches": [{"result": "Loss", "opponent": "C"}],
        "summary": "L",
    }
    assert fixture["current_form_observed_at"] == OBSERVED.isoformat()

    fixture_payload = replay_live_fotmob_evidence(
        fixture["fotmob_fixture_evidence"], repository_root=tmp_path
    )
    detail_payload = replay_live_fotmob_evidence(
        fixture["fotmob_match_details_evidence"], repository_root=tmp_path
    )
    assert fixture_payload == json.loads(fixture_raw)
    assert detail_payload == json.loads(detail_raw)

    with sqlite3.connect(scraper.db.db_path) as connection:
        row = connection.execute(
            "SELECT home_form, away_form, match_details_evidence_sha256 "
            "FROM fixture_extended WHERE fixture_id=123456"
        ).fetchone()
    assert json.loads(row[0]) == fixture["home_form"]
    assert json.loads(row[1]) == fixture["away_form"]
    assert row[2] == fixture["fotmob_match_details_evidence"].evidence_sha256


def test_one_matches_response_is_captured_once_and_shared_by_fixtures(tmp_path: Path) -> None:
    _scraper, fixtures, _target, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipts = [item["fotmob_fixture_evidence"] for item in fixtures]
    assert receipts[0] == receipts[1]
    assert receipts[0].fixture_identifier is None
    capture_root = tmp_path / EVIDENCE_ROOT
    assert len(tuple(capture_root.glob("fixture-list--*"))) == 1


def test_legacy_runtime_evidence_cannot_issue_canonical_intelligence(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    with pytest.raises(
        LiveFotMobFixtureIntelligenceError,
        match=CANONICAL_ISSUER_STATUS,
    ):
        issue_live_fotmob_fixture_intelligence(
            fixture_evidence=fixture["fotmob_fixture_evidence"],
            match_details_evidence=fixture["fotmob_match_details_evidence"],
            repository_root=tmp_path,
        )


def test_db_normalized_values_are_not_canonical_authority(tmp_path: Path) -> None:
    scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    with sqlite3.connect(scraper.db.db_path) as connection:
        row = connection.execute(
            "SELECT home_form, away_form, match_details_evidence_path "
            "FROM fixture_extended WHERE fixture_id=123456"
        ).fetchone()
    assert json.loads(row[0]) == fixture["home_form"]
    assert json.loads(row[1]) == fixture["away_form"]
    assert row[2]
    with pytest.raises(
        LiveFotMobFixtureIntelligenceError,
        match=CANONICAL_ISSUER_STATUS,
    ):
        issue_live_fotmob_fixture_intelligence(
            fixture_evidence=fixture["fotmob_fixture_evidence"],
            match_details_evidence=fixture["fotmob_match_details_evidence"],
            repository_root=tmp_path,
        )


def test_raw_hash_mutation_fails_closed(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    raw_path = tmp_path / receipt.evidence_directory / "response.json"
    raw_path.write_bytes(b'{"tampered":true}')
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="SHA-256"):
        replay_live_fotmob_evidence(receipt, repository_root=tmp_path)


def test_manifest_mutation_fails_closed(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    manifest_path = tmp_path / receipt.evidence_directory / "manifest.json"
    manifest_path.write_bytes(b'{"tampered":true}\n')
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="manifest SHA-256"):
        replay_live_fotmob_evidence(receipt, repository_root=tmp_path)


def test_alternate_root_and_traversal_are_rejected(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="fixed live evidence root"):
        dataclasses.replace(
            receipt,
            evidence_directory=Path(".cache/elsewhere/capture"),
        )
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="traversal"):
        dataclasses.replace(
            receipt,
            evidence_directory=Path(
                ".cache/athena-runtime/fotmob-live-evidence/../escape"
            ),
        )


def test_parent_symlink_escape_fails_closed(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    evidence_root = tmp_path / EVIDENCE_ROOT
    moved = tmp_path / "real-live-evidence"
    evidence_root.rename(moved)
    evidence_root.symlink_to(moved, target_is_directory=True)
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="symlink"):
        replay_live_fotmob_evidence(receipt, repository_root=tmp_path)


def test_response_symlink_fails_closed(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    directory = tmp_path / receipt.evidence_directory
    response = directory / "response.json"
    target = tmp_path / "outside-response.json"
    target.write_bytes(response.read_bytes())
    response.unlink()
    response.symlink_to(target)
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="non-symlink"):
        replay_live_fotmob_evidence(receipt, repository_root=tmp_path)


def test_manifest_symlink_fails_closed(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    directory = tmp_path / receipt.evidence_directory
    manifest = directory / "manifest.json"
    target = tmp_path / "outside-manifest.json"
    target.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(target)
    with pytest.raises(LiveFotMobFixtureIntelligenceError, match="non-symlink"):
        replay_live_fotmob_evidence(receipt, repository_root=tmp_path)


def test_absent_away_form_is_not_inferred(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(
        tmp_path,
        include_away=False,
    )
    assert fixture["home_form"] == {
        "matches": [
            {"result": "Win", "opponent": "A"},
            {"result": "Draw", "opponent": "B"},
        ],
        "summary": "WD",
    }
    assert "away_form" not in fixture


def test_replay_is_deterministic_for_exact_runtime_evidence(tmp_path: Path) -> None:
    _scraper, _fixtures, fixture, _fixture_raw, _detail_raw = _runtime(tmp_path)
    receipt = fixture["fotmob_match_details_evidence"]
    first = replay_live_fotmob_evidence(receipt, repository_root=tmp_path)
    second = replay_live_fotmob_evidence(receipt, repository_root=tmp_path)
    assert first == second
