from __future__ import annotations

import dataclasses
import datetime as dt
import inspect
import json
from pathlib import Path

import pytest

import scripts.issue_current_fotmob_reviewed_source as issuer_module
from domain.current_fotmob_fixture_review_policy import (
    DEFAULT_MAX_SOURCE_AGE_SECONDS,
    DEFAULT_MINIMUM_LEAD_SECONDS,
)
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
    build_parser,
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


def _capture(
    tmp_path: Path,
    *,
    league_name: str = "Premier League",
    ccode: str = "ENG",
    observed_at: dt.datetime = OBSERVED,
) -> Path:
    raw = _raw(league_name=league_name, ccode=ccode)
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=observed_at,
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


def _execution(tmp_path: Path):
    capture = _capture(tmp_path)
    return build_verified_current_fotmob_bootstrap_from_capture(
        capture,
        issued_at=ISSUED,
        repository_root=tmp_path,
        code_state=_code_state(),
    )


def test_exact_capture_reaches_verified_current_bootstrap(tmp_path: Path) -> None:
    execution = _execution(tmp_path)

    assert execution.status == STATUS_READY
    assert execution.policy_result.minimum_lead_seconds == DEFAULT_MINIMUM_LEAD_SECONDS
    assert execution.policy_result.max_source_age_seconds == DEFAULT_MAX_SOURCE_AGE_SECONDS
    assert execution.policy_result.policy_approved_count == 1
    assert [item.fixture_identifier for item in execution.bootstrap.fixtures] == [
        "FOTMOB:1001"
    ]
    assert execution.verified_bootstrap.bootstrap == execution.bootstrap
    assert execution.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    summary = execution.summary()
    assert summary["minimum_lead_seconds"] == DEFAULT_MINIMUM_LEAD_SECONDS
    assert summary["max_source_age_seconds"] == DEFAULT_MAX_SOURCE_AGE_SECONDS
    assert summary["stale_source_excluded_count"] == 0
    assert summary["request_date_excluded_count"] == 0
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


def test_execution_receipt_cannot_relabel_source_manifest_sha(tmp_path: Path) -> None:
    execution = _execution(tmp_path)
    with pytest.raises(
        CurrentFotMobReviewedSourceError,
        match="source_capture_manifest_sha256 does not anchor",
    ):
        dataclasses.replace(execution, source_capture_manifest_sha256="f" * 64)


def test_execution_receipt_cannot_relabel_source_raw_sha(tmp_path: Path) -> None:
    execution = _execution(tmp_path)
    with pytest.raises(
        CurrentFotMobReviewedSourceError,
        match="source_raw_sha256 does not anchor",
    ):
        dataclasses.replace(execution, source_raw_sha256="f" * 64)


def test_execution_receipt_cannot_relabel_issued_time(tmp_path: Path) -> None:
    execution = _execution(tmp_path)
    with pytest.raises(
        CurrentFotMobReviewedSourceError,
        match="issued_at does not match",
    ):
        dataclasses.replace(execution, issued_at=ISSUED + dt.timedelta(seconds=1))


def test_bootstrap_does_not_smuggle_football_facts(tmp_path: Path) -> None:
    execution = _execution(tmp_path)
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


def test_stale_capture_cannot_be_replayed_as_current(tmp_path: Path) -> None:
    stale_observed = ISSUED - dt.timedelta(seconds=DEFAULT_MAX_SOURCE_AGE_SECONDS + 1)
    capture = _capture(tmp_path, observed_at=stale_observed)
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


def test_live_entry_point_does_not_expose_policy_bound_overrides() -> None:
    parameters = inspect.signature(issue_current_fotmob_reviewed_source).parameters
    assert "minimum_lead_seconds" not in parameters
    assert "max_source_age_seconds" not in parameters

    option_strings = {
        option
        for action in build_parser()._actions
        for option in action.option_strings
    }
    assert "--minimum-lead-seconds" not in option_strings
    assert "--max-source-age-seconds" not in option_strings


def test_hosted_workflow_does_not_expose_policy_bound_overrides() -> None:
    repository = Path(__file__).resolve().parents[1]
    workflow = (
        repository / ".github/workflows/issue-current-fotmob-reviewed-source.yml"
    ).read_text(encoding="utf-8")
    assert "minimum_lead_seconds:" not in workflow
    assert "max_source_age_seconds:" not in workflow
    assert "--minimum-lead-seconds" not in workflow
    assert "--max-source-age-seconds" not in workflow


def test_cli_failure_still_writes_auditable_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "execution.json"

    def fail(**_kwargs):
        raise CurrentFotMobReviewedSourceError(STATUS_NO_FIXTURES)

    monkeypatch.setattr(issuer_module, "issue_current_fotmob_reviewed_source", fail)
    with pytest.raises(SystemExit) as exc_info:
        issuer_module.main(
            [
                "--date",
                "20260827",
                "--timezone",
                "UTC",
                "--ccode3",
                "NGA",
                "--execute-live-network",
                "--output",
                str(output),
            ]
        )
    assert exc_info.value.code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == STATUS_NO_FIXTURES
    assert payload["minimum_lead_seconds"] == DEFAULT_MINIMUM_LEAD_SECONDS
    assert payload["max_source_age_seconds"] == DEFAULT_MAX_SOURCE_AGE_SECONDS
    assert payload["next_required_boundary"] == NEXT_REQUIRED_BOUNDARY
    assert payload["wager_placed"] is False
