"""Fail-closed binding for a watchdog-created fresh-holdout continuity dispatch.

GitHub can expose a newly-created ``workflow_dispatch`` run in the ``queued``
state under the workflow's generic name before the reviewed ``run-name`` is
materialized. The durability bridge must still be able to bind that exact run,
but it must not turn generic queued workflow metadata into a fuzzy identity.

The generic-name fallback therefore requires all of the following:

* exact primary workflow id/path/event/branch/head SHA;
* exact GitHub Actions bot actor and triggering actor;
* first run attempt, queued status, null conclusion and no pull requests;
* creation inside the exact watchdog dispatch-step execution window; and
* independent zero-job and zero-artifact proof before the fallback is accepted.

Once the run leaves the queued state, the normal reviewed run-name and
continuity provenance validators remain authoritative.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any, Mapping, Sequence

import domain.fotmob_fresh_holdout_continuity as continuity


DISPATCH_STEP_NAME = "Dispatch prospective continuity tick if primary delivery is absent"
BOT_LOGIN = "github-actions[bot]"
WINDOW_SLOP_SECONDS = 2


class ContinuityDispatchBindingError(RuntimeError):
    """Raised when queued continuity identity cannot be proved exactly."""


@dataclasses.dataclass(frozen=True)
class BoundDispatchCandidate:
    run_id: int
    generic_queued_fallback: bool


def _utc(value: Any, *, field: str) -> dt.datetime:
    if type(value) is not str:
        raise ContinuityDispatchBindingError(f"{field} is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuityDispatchBindingError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ContinuityDispatchBindingError(f"{field} is not timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def _dispatch_window(dispatch_step: Mapping[str, Any]) -> tuple[dt.datetime, dt.datetime]:
    if dispatch_step.get("name") != DISPATCH_STEP_NAME:
        raise ContinuityDispatchBindingError("watchdog dispatch step name drifted")
    if dispatch_step.get("status") != "completed" or dispatch_step.get("conclusion") != "success":
        raise ContinuityDispatchBindingError("watchdog dispatch step is not successful")
    started = _utc(dispatch_step.get("started_at"), field="watchdog dispatch started_at")
    completed = _utc(dispatch_step.get("completed_at"), field="watchdog dispatch completed_at")
    if completed < started:
        raise ContinuityDispatchBindingError("watchdog dispatch time window is inverted")
    slop = dt.timedelta(seconds=WINDOW_SLOP_SECONDS)
    return started - slop, completed + slop


def _actor_login(run: Mapping[str, Any], key: str) -> Any:
    actor = run.get(key)
    return actor.get("login") if type(actor) is dict else None


def _base_identity(run: Mapping[str, Any], *, watchdog_head_sha: str) -> bool:
    return (
        run.get("workflow_id") == continuity.PRIMARY_WORKFLOW_ID
        and run.get("event") == "workflow_dispatch"
        and run.get("head_branch") == "main"
        and run.get("head_sha") == watchdog_head_sha
        and run.get("path") == continuity.PRIMARY_WORKFLOW_PATH
    )


def select_dispatch_candidate(
    runs: Sequence[Any],
    *,
    expected_name: str,
    watchdog_head_sha: str,
    dispatch_step: Mapping[str, Any],
) -> BoundDispatchCandidate | None:
    """Select the exact reviewed run or the exact proven generic queued fallback."""

    if type(expected_name) is not str or not expected_name:
        raise ContinuityDispatchBindingError("expected continuity run-name is invalid")
    if type(watchdog_head_sha) is not str or len(watchdog_head_sha) != 40:
        raise ContinuityDispatchBindingError("watchdog head SHA is invalid")
    if not isinstance(runs, Sequence) or isinstance(runs, (str, bytes, bytearray)):
        raise ContinuityDispatchBindingError("primary workflow runs payload is malformed")

    exact = [
        run
        for run in runs
        if type(run) is dict
        and _base_identity(run, watchdog_head_sha=watchdog_head_sha)
        and run.get("name") == expected_name
        and run.get("display_title") == expected_name
    ]
    if len(exact) > 1:
        raise ContinuityDispatchBindingError("duplicate exact continuity dispatch runs detected")
    if len(exact) == 1:
        run_id = exact[0].get("id")
        if type(run_id) is not int or run_id <= 0:
            raise ContinuityDispatchBindingError("exact continuity dispatch run id is invalid")
        return BoundDispatchCandidate(run_id=run_id, generic_queued_fallback=False)

    window_start, window_end = _dispatch_window(dispatch_step)
    generic: list[Mapping[str, Any]] = []
    for value in runs:
        if type(value) is not dict:
            continue
        run = value
        if not _base_identity(run, watchdog_head_sha=watchdog_head_sha):
            continue
        if run.get("name") != continuity.PRIMARY_WORKFLOW_NAME:
            continue
        if run.get("display_title") != continuity.PRIMARY_WORKFLOW_NAME:
            continue
        if run.get("status") != "queued" or run.get("conclusion") is not None:
            continue
        if run.get("run_attempt") != 1:
            continue
        if run.get("pull_requests") != []:
            continue
        if _actor_login(run, "actor") != BOT_LOGIN:
            continue
        if _actor_login(run, "triggering_actor") != BOT_LOGIN:
            continue
        created = _utc(run.get("created_at"), field="queued continuity created_at")
        if window_start <= created <= window_end:
            generic.append(run)

    if len(generic) > 1:
        raise ContinuityDispatchBindingError(
            "duplicate generic queued continuity dispatch candidates detected"
        )
    if not generic:
        return None
    run_id = generic[0].get("id")
    if type(run_id) is not int or run_id <= 0:
        raise ContinuityDispatchBindingError("generic queued continuity run id is invalid")
    return BoundDispatchCandidate(run_id=run_id, generic_queued_fallback=True)


def prove_generic_queued_no_execution(
    *,
    run_id: int,
    run: Mapping[str, Any],
    jobs_payload: Mapping[str, Any],
    artifacts_payload: Mapping[str, Any],
) -> None:
    """Require independent zero-execution evidence for the generic queued fallback."""

    if run.get("id") != run_id:
        raise ContinuityDispatchBindingError("queued fallback run id drifted")
    if run.get("status") != "queued" or run.get("conclusion") is not None:
        raise ContinuityDispatchBindingError("queued fallback escaped queued/no-conclusion state")

    jobs = jobs_payload.get("jobs")
    job_count = jobs_payload.get("total_count")
    if jobs != [] or job_count not in (0, None):
        raise ContinuityDispatchBindingError("queued fallback already exposes execution jobs")

    artifacts = artifacts_payload.get("artifacts")
    artifact_count = artifacts_payload.get("total_count")
    if artifacts != [] or artifact_count not in (0, None):
        raise ContinuityDispatchBindingError("queued fallback already exposes artifacts")


__all__ = [
    "BOT_LOGIN",
    "BoundDispatchCandidate",
    "ContinuityDispatchBindingError",
    "DISPATCH_STEP_NAME",
    "WINDOW_SLOP_SECONDS",
    "prove_generic_queued_no_execution",
    "select_dispatch_candidate",
]
