from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from domain import current_fotmob_utc_native_shadow_prediction as shadow
from domain.current_fotmob_fixture_candidate_adapter import (
    build_current_fotmob_fixture_candidate_bundle,
)
from domain.current_fotmob_fixture_review_policy import (
    POLICY_ID,
    SHADOW_POLICY_ID,
)
from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from domain.fotmob_fixture_candidate_review import (
    canonical_fotmob_fixture_candidate_review_bundle_bytes,
)
from scripts.capture_fotmob_data_matches import write_data_matches_capture_directory
from scripts.issue_current_fotmob_reviewed_source import (
    build_verified_current_fotmob_bootstrap_from_capture,
    build_verified_current_shadow_fotmob_bootstrap_from_capture,
)

UTC = dt.timezone.utc


def _epoch_ms(value: dt.datetime) -> int:
    epoch = dt.datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _raw(kickoff: dt.datetime) -> bytes:
    kickoff_text = kickoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    payload = {
        "leagues": [
            {
                "ccode": "ENG",
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
                            "utcTime": kickoff_text,
                            "halfs": {"firstHalfStarted": ""},
                            "periodLength": 45,
                            "started": False,
                            "cancelled": False,
                            "finished": False,
                        },
                        "statusId": 1,
                        "time": kickoff.strftime("%d.%m.%Y %H:%M"),
                        "timeTS": _epoch_ms(kickoff),
                        "tournamentStage": "",
                    }
                ],
                "name": "Premier League",
                "primaryId": 47,
                "simpleLeague": False,
            }
        ],
        "date": kickoff.strftime("%Y%m%d"),
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _execution(
    tmp_path: Path,
    *,
    shadow_policy: bool,
    kickoff_lead_minutes: int,
):
    observed = dt.datetime(2026, 8, 27, 7, 0, tzinfo=UTC)
    issued = observed + dt.timedelta(minutes=5)
    kickoff = issued + dt.timedelta(minutes=kickoff_lead_minutes)
    raw = _raw(kickoff)
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=observed,
        network_acquisition_performed=True,
    )
    directory, manifest = write_data_matches_capture_directory(
        response,
        request_date=kickoff.strftime("%Y%m%d"),
        timezone="UTC",
        ccode3="NGA",
        repository_root=tmp_path,
    )
    builder = (
        build_verified_current_shadow_fotmob_bootstrap_from_capture
        if shadow_policy
        else build_verified_current_fotmob_bootstrap_from_capture
    )
    execution = builder(
        directory,
        issued_at=issued,
        repository_root=tmp_path,
        code_state={
            "evidence_git_head_sha": "a" * 40,
            "tracked_worktree_clean": True,
        },
    )
    return execution, raw, manifest


def _review_sha(policy) -> str:
    return hashlib.sha256(
        canonical_fotmob_fixture_candidate_review_bundle_bytes(policy.review_bundle)
    ).hexdigest()


def test_shadow_v2_bootstrap_replays_shadow_v2_policy_exactly(tmp_path: Path) -> None:
    execution, raw, manifest = _execution(
        tmp_path,
        shadow_policy=True,
        kickoff_lead_minutes=45,
    )
    assert execution.policy_result.policy_id == SHADOW_POLICY_ID
    assert execution.policy_result.minimum_lead_seconds == 1800
    candidates = build_current_fotmob_fixture_candidate_bundle(raw, manifest)

    replay = shadow._review_policy_for_bootstrap(candidates, execution.bootstrap)

    assert replay.policy_id == SHADOW_POLICY_ID
    assert replay.minimum_lead_seconds == 1800
    assert _review_sha(replay) == execution.bootstrap.review_bundle_sha256
    assert replay.policy_approved_count == len(execution.bootstrap.fixtures) == 1


def test_historical_pr243_bootstrap_replays_pr243_policy_unchanged(tmp_path: Path) -> None:
    execution, raw, manifest = _execution(
        tmp_path,
        shadow_policy=False,
        kickoff_lead_minutes=120,
    )
    assert execution.policy_result.policy_id == POLICY_ID
    assert execution.policy_result.minimum_lead_seconds == 3600
    candidates = build_current_fotmob_fixture_candidate_bundle(raw, manifest)

    replay = shadow._review_policy_for_bootstrap(candidates, execution.bootstrap)

    assert replay.policy_id == POLICY_ID
    assert replay.minimum_lead_seconds == 3600
    assert _review_sha(replay) == execution.bootstrap.review_bundle_sha256
    assert replay.policy_approved_count == len(execution.bootstrap.fixtures) == 1


@pytest.mark.parametrize(
    "reviewers",
    (
        ("athena-policy:unknown-fixture-review",),
        (shadow.PR243_REVIEWER_REFERENCE, shadow.SHADOW_REVIEWER_REFERENCE),
    ),
)
def test_unknown_or_mixed_fixture_policy_provenance_fails_closed(
    reviewers: tuple[str, ...],
) -> None:
    decisions = tuple(
        type("Decision", (), {"reviewer_reference": reviewer})()
        for reviewer in reviewers
    )
    bootstrap = type(
        "Bootstrap",
        (),
        {
            "verified_artifact": type(
                "Verified",
                (),
                {
                    "admission": type(
                        "Admission",
                        (),
                        {
                            "handoff": type(
                                "Handoff",
                                (),
                                {
                                    "review_bundle": type(
                                        "ReviewBundle",
                                        (),
                                        {"decisions": decisions},
                                    )()
                                },
                            )()
                        },
                    )()
                },
            )()
        },
    )()

    with pytest.raises(
        shadow.CurrentUtcNativeShadowPredictionError,
        match="unknown or mixed",
    ):
        shadow._review_policy_for_bootstrap(object(), bootstrap)
