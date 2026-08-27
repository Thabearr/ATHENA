from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain.reviewed_fixture_intelligence_bootstrap import (
    canonical_reviewed_fixture_intelligence_bootstrap_bytes,
)
from scripts.capture_fotmob_data_matches import write_data_matches_capture_directory
from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from scripts.issue_current_fotmob_reviewed_source import (
    NEXT_REQUIRED_BOUNDARY,
    STATUS_NO_FIXTURES,
    STATUS_READY,
    CurrentFotMobReviewedSourceError,
    build_verified_current_fotmob_bootstrap_from_capture,
    issue_current_fotmob_reviewed_source,
)


UTC = dt.timezone.utc
OBSERVED = dt.datetime(2026, 8, 27, 7, 0, tzinfo=UTC)
ISSUED = dt.datetime(2026, 8, 27, 7, 5, tzinfo=UTC)


def _epoch_ms(value: str) -> int:
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    epoch = dt.datetime(1970, 1, 1, tzinfo=UTC)
    delta = parsed - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _raw(*, league_name: str = "Premier League", ccode: str = "ENG") -> bytes:
    kickoff = "2026-08-27T15:00:00.000Z"
    payload = {
        "leagues": [
            {
                "ccode": ccode,
                "id": 47,
                "internalRank": 1,
                "matches": [
                    {
                        "away": {
                            "id": 202,
                            "score": 0,
                            "name": "Away FC",
                            "longName": "Away FC",
                        },
                        "eliminatedTeamId": None,
                        "home": {
                            "id": 101,
                            "score": 0,
                            "name": "Home FC",
                            "longName": "Home FC",
                        },
                        "id": 1001,
                        "leagueId": 47,
                        "status": {
                            "utcTime": kickoff,
                            "halfs": {"firstHalfStarted": ""},
                            "periodLength": 45,
                            "started": False,
                            "cancelled": False,
                            "finished": False,
                        },
                        "statusId": 1,
                        "time": "27.08.2026 15:00",
                        "timeTS": _epoch_ms(kickoff),
                        "tournamentStage": "",
                    }
                ],
                "name": league_name,
                "primaryId": 47,
                "simpleLeague": False,
            }
        ],
        "date": "20260827",
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _capture(tmp_path: Path, *, league_name: str = "Premier League", ccode: str = "ENG") -> Path:
    raw = _raw(league_name=league_name, ccode=ccode)
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=OBSERVED,
        network_acquisition_performed=True,
    )
    directory, _manifest = write_data_matches_capture_directory(
        response,
        request_date="20260827",
        timezone="UTC",
        ccode3="NGA",
        repository_root=tmp_path,
    )
    return directory


def _code_state() -> dict[str, object]:
    return {
        "evidence_git_head_sha": "a" * 40,
        "tracked_worktree_clean": True,
    }


def test_exact_capture_reaches_verified_current_bootstrap(tmp_path: Path) -> None:
    capture = _capture(tmp_path)
    execution = build_verified_current_fotmob_bootstrap_from_capture(
        capture,
        issued_at=ISSUED,
        minimum_lead_seconds=3600,
        repository_root=tmp_path,
        code_state=_code_state(),
    )

    assert execution.status == STATUS_READY
    assert execution.policy_result.policy_approved_count == 1
    assert [item.fixture_identifier for item in execution.bootstrap.fixtures] == [
        "FOTMOB:1001"
    ]
    assert execution.verified_bootstrap.bootstrap == execution.bootstrap
    assert execution.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    summary = execution.summary()
    assert summary["authority"] == {
        "transparent_fotmob_network_capture": True,
        "pr243_fixture_identity_policy_decisions": True,
        "reviewed_fixture_bootstrap": True,
        "fixture_intelligence_fact": False,
        "fixture_intelligence_snapshot": False,
        "model_feature": False,
        "probability": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "bet": False,
    }
    assert summary["wager_placed"] is False


def test_bootstrap_does_not_smuggle_football_facts(tmp_path: Path) -> None:
    capture = _capture(tmp_path)
    execution = build_verified_current_fotmob_bootstrap_from_capture(
        capture,
        issued_at=ISSUED,
        repository_root=tmp_path,
        code_state=_code_state(),
    )
    raw = canonical_reviewed_fixture_intelligence_bootstrap_bytes(execution.bootstrap)
    for forbidden in (
        b"home_form",
        b"away_form",
        b"home_elo",
        b"away_elo",
        b"fatigue",
        b"lineup",
        b"odds",
    ):
        assert forbidden not in raw


def test_unknown_competition_fails_with_explicit_no_fixture_status(tmp_path: Path) -> None:
    capture = _capture(tmp_path, league_name="Unknown Regional League", ccode="ZZZ")
    with pytest.raises(CurrentFotMobReviewedSourceError, match=STATUS_NO_FIXTURES):
        build_verified_current_fotmob_bootstrap_from_capture(
            capture,
            issued_at=ISSUED,
            repository_root=tmp_path,
            code_state=_code_state(),
        )


def test_dirty_code_state_still_fails_closed_in_existing_compiler(tmp_path: Path) -> None:
    capture = _capture(tmp_path)
    with pytest.raises(Exception, match="Tracked worktree must be clean"):
        build_verified_current_fotmob_bootstrap_from_capture(
            capture,
            issued_at=ISSUED,
            repository_root=tmp_path,
            code_state={
                "evidence_git_head_sha": "a" * 40,
                "tracked_worktree_clean": False,
            },
        )


def test_live_entry_point_requires_explicit_network_authorization() -> None:
    with pytest.raises(CurrentFotMobReviewedSourceError, match="execute_live_network=True"):
        issue_current_fotmob_reviewed_source(
            request_date="20260827",
            timezone="UTC",
            ccode3="NGA",
            execute_live_network=False,
        )
