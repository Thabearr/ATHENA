from __future__ import annotations

import copy

import pytest

from scripts import bind_fotmob_fresh_holdout_continuity_dispatch as binding


HEAD = "a" * 40
EXPECTED = (
    "ATHENA fresh-holdout workflow_dispatch "
    "source=34011389507 target=2026-09-06T04:37:00Z "
    "cron=37 * * * * confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
)


def _dispatch_step() -> dict:
    return {
        "name": binding.DISPATCH_STEP_NAME,
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-09-06T04:38:30Z",
        "completed_at": "2026-09-06T04:38:33Z",
    }


def _run(*, generic: bool = True) -> dict:
    title = binding.continuity.PRIMARY_WORKFLOW_NAME if generic else EXPECTED
    return {
        "id": 34012011312,
        "name": title,
        "display_title": title,
        "workflow_id": binding.continuity.PRIMARY_WORKFLOW_ID,
        "path": binding.continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": HEAD,
        "status": "queued" if generic else "in_progress",
        "conclusion": None,
        "run_attempt": 1,
        "pull_requests": [],
        "created_at": "2026-09-06T04:38:32Z",
        "actor": {"login": binding.BOT_LOGIN},
        "triggering_actor": {"login": binding.BOT_LOGIN},
    }


def _select(runs):
    return binding.select_dispatch_candidate(
        runs,
        expected_name=EXPECTED,
        watchdog_head_sha=HEAD,
        dispatch_step=_dispatch_step(),
    )


def test_exact_reviewed_run_name_remains_primary_binding_authority() -> None:
    result = _select([_run(generic=False)])
    assert result == binding.BoundDispatchCandidate(
        run_id=34012011312,
        generic_queued_fallback=False,
    )


def test_observed_generic_queued_bot_dispatch_binds_only_inside_dispatch_window() -> None:
    result = _select([_run()])
    assert result == binding.BoundDispatchCandidate(
        run_id=34012011312,
        generic_queued_fallback=True,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_id", 1),
        ("path", ".github/workflows/other.yml"),
        ("event", "schedule"),
        ("head_branch", "other"),
        ("head_sha", "b" * 40),
        ("status", "in_progress"),
        ("conclusion", "success"),
        ("run_attempt", 2),
        ("pull_requests", [{"number": 1}]),
        ("created_at", "2026-09-06T04:39:00Z"),
    ],
)
def test_generic_fallback_rejects_any_identity_or_execution_drift(field, value) -> None:
    run = _run()
    run[field] = value
    assert _select([run]) is None


def test_generic_fallback_rejects_non_bot_actor_or_triggering_actor() -> None:
    run = _run()
    run["actor"] = {"login": "Thabearr"}
    assert _select([run]) is None

    run = _run()
    run["triggering_actor"] = {"login": "Thabearr"}
    assert _select([run]) is None


def test_generic_fallback_fails_closed_on_duplicate_same_window_candidates() -> None:
    first = _run()
    second = copy.deepcopy(first)
    second["id"] = 34012011313
    with pytest.raises(
        binding.ContinuityDispatchBindingError,
        match="duplicate generic queued continuity dispatch candidates detected",
    ):
        _select([first, second])


def test_generic_fallback_requires_valid_successful_dispatch_step_window() -> None:
    dispatch = _dispatch_step()
    dispatch["conclusion"] = "skipped"
    with pytest.raises(
        binding.ContinuityDispatchBindingError,
        match="dispatch step is not successful",
    ):
        binding.select_dispatch_candidate(
            [_run()],
            expected_name=EXPECTED,
            watchdog_head_sha=HEAD,
            dispatch_step=dispatch,
        )


def test_exact_named_candidate_does_not_need_generic_fallback_window() -> None:
    dispatch = _dispatch_step()
    dispatch["started_at"] = None
    result = binding.select_dispatch_candidate(
        [_run(generic=False)],
        expected_name=EXPECTED,
        watchdog_head_sha=HEAD,
        dispatch_step=dispatch,
    )
    assert result == binding.BoundDispatchCandidate(
        run_id=34012011312,
        generic_queued_fallback=False,
    )


def test_generic_queued_no_execution_requires_zero_jobs_and_zero_artifacts() -> None:
    run = _run()
    binding.prove_generic_queued_no_execution(
        run_id=run["id"],
        run=run,
        jobs_payload={"total_count": 0, "jobs": []},
        artifacts_payload={"total_count": 0, "artifacts": []},
    )

    with pytest.raises(
        binding.ContinuityDispatchBindingError,
        match="already exposes execution jobs",
    ):
        binding.prove_generic_queued_no_execution(
            run_id=run["id"],
            run=run,
            jobs_payload={"total_count": 1, "jobs": [{"id": 1}]},
            artifacts_payload={"total_count": 0, "artifacts": []},
        )

    with pytest.raises(
        binding.ContinuityDispatchBindingError,
        match="already exposes artifacts",
    ):
        binding.prove_generic_queued_no_execution(
            run_id=run["id"],
            run=run,
            jobs_payload={"total_count": 0, "jobs": []},
            artifacts_payload={"total_count": 1, "artifacts": [{"id": 1}]},
        )


def test_generic_queued_no_execution_rejects_state_change_after_selection() -> None:
    run = _run()
    run["status"] = "in_progress"
    with pytest.raises(
        binding.ContinuityDispatchBindingError,
        match="escaped queued/no-conclusion state",
    ):
        binding.prove_generic_queued_no_execution(
            run_id=run["id"],
            run=run,
            jobs_payload={"total_count": 0, "jobs": []},
            artifacts_payload={"total_count": 0, "artifacts": []},
        )
