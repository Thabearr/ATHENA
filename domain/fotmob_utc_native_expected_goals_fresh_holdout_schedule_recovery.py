"""Fail-closed scheduler recovery for the FotMob UTC-native fresh holdout.

A GitHub scheduled workflow can be delivered late enough that more than one nominal
cron occurrence is plausible. ATHENA must not guess which occurrence produced the
run. This module lets such a run finish as a proven no-acquisition control no-op,
then permits a later run to step across that no-op only when GitHub job metadata
proves the reviewed collection path never reached acquisition or persistence.

The same rule applies to the prospective continuity transport: if durable lineage
already attempted the exact future target, the continuity dispatch must become a
green zero-artifact no-op and may be stepped across only after exact job metadata
proves every acquisition/persistence step was skipped. A failed continuity dispatch
may likewise be stepped across only when its exact job steps prove failure occurred
before provider acquisition or persistence.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as lineage


AMBIGUOUS_NO_ACQUISITION_DISPOSITION = "AMBIGUOUS_NO_ACQUISITION"
CONTINUITY_ALREADY_ATTEMPTED_NO_ACQUISITION_DISPOSITION = (
    "CONTINUITY_ALREADY_ATTEMPTED_NO_ACQUISITION"
)
SCHEDULE_ALREADY_ATTEMPTED_NO_ACQUISITION_DISPOSITION = (
    "SCHEDULE_ALREADY_ATTEMPTED_NO_ACQUISITION"
)
RESOLVED_DISPOSITION = "RESOLVED"
_AMBIGUOUS_MARKER_STEP = "Acknowledge ambiguous schedule without acquisition"
_CONTINUITY_MARKER_STEP = (
    "Acknowledge continuity slot already attempted without acquisition"
)
_SCHEDULE_DUPLICATE_MARKER_STEP = (
    "Acknowledge schedule slot already attempted without acquisition"
)
_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES = {
    "Restore newest durable lineage and resolve schedule slot": "success",
    _AMBIGUOUS_MARKER_STEP: "success",
    "Restore or materialize PR119 bootstrap projection": "skipped",
    "Execute reviewed fresh-holdout collection tick": "skipped",
    "Reconcile any staged capture lineage": "skipped",
    "Package durable state archive": "skipped",
    "Upload authoritative 90-day Actions artifact": "skipped",
    "Publish and verify long-lived evidence release asset": "skipped",
}
_CONTINUITY_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES = {
    "Authenticate continuity dispatch source": "success",
    "Restore newest durable lineage and resolve schedule slot": "success",
    _AMBIGUOUS_MARKER_STEP: "skipped",
    _CONTINUITY_MARKER_STEP: "success",
    "Restore or materialize PR119 bootstrap projection": "skipped",
    "Execute reviewed fresh-holdout collection tick": "skipped",
    "Reconcile any staged capture lineage": "skipped",
    "Package durable state archive": "skipped",
    "Upload authoritative 90-day Actions artifact": "skipped",
    "Publish and verify long-lived evidence release asset": "skipped",
}
_SCHEDULE_DUPLICATE_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES = {
    "Restore newest durable lineage and resolve schedule slot": "success",
    _AMBIGUOUS_MARKER_STEP: "skipped",
    _CONTINUITY_MARKER_STEP: "skipped",
    _SCHEDULE_DUPLICATE_MARKER_STEP: "success",
    "Restore or materialize PR119 bootstrap projection": "skipped",
    "Execute reviewed fresh-holdout collection tick": "skipped",
    "Reconcile any staged capture lineage": "skipped",
    "Package durable state archive": "skipped",
    "Upload authoritative 90-day Actions artifact": "skipped",
    "Publish and verify long-lived evidence release asset": "skipped",
}
_CONTINUITY_PREACQUISITION_ALLOWED_STEP_OUTCOMES = (
    {
        "Authenticate continuity dispatch source": "failure",
        "Restore newest durable lineage and resolve schedule slot": "skipped",
        "Restore or materialize PR119 bootstrap projection": "skipped",
        "Execute reviewed fresh-holdout collection tick": "skipped",
        "Reconcile any staged capture lineage": "skipped",
    },
    {
        "Authenticate continuity dispatch source": "success",
        "Restore newest durable lineage and resolve schedule slot": "failure",
        "Restore or materialize PR119 bootstrap projection": "skipped",
        "Execute reviewed fresh-holdout collection tick": "skipped",
        "Reconcile any staged capture lineage": "skipped",
    },
    {
        "Authenticate continuity dispatch source": "success",
        "Restore newest durable lineage and resolve schedule slot": "success",
        "Restore or materialize PR119 bootstrap projection": "failure",
        "Execute reviewed fresh-holdout collection tick": "skipped",
        "Reconcile any staged capture lineage": "skipped",
    },
)


def is_ambiguous_schedule_occurrence_error(exc: BaseException) -> bool:
    """Return True only for the reviewed resolver's exact ambiguity refusal."""
    text = str(exc)
    return (
        type(exc) is runner.FreshHoldoutActivationError
        and text.startswith(
            "ambiguous schedule occurrence: multiple candidate slots ("
        )
        and ") occurred between last committed " in text
        and " and trigger " in text
    )


def _prove_green_zero_artifact_path(
    run: Mapping[str, Any],
    artifact_data: Mapping[str, Any],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
    *,
    expected_event: str,
    required_step_outcomes: Mapping[str, str],
) -> bool:
    run_id = run.get("id")
    if type(run_id) is not int or run_id < 1 or run.get("conclusion") != "success":
        return False
    created_at = lineage._run_created_at(run, run_id)
    if created_at is None or created_at < control.holdout_start_utc():
        return False
    if run.get("event") != expected_event or run.get("head_branch") != "main":
        return False
    artifacts = artifact_data.get("artifacts")
    if type(artifacts) is not list or artifacts:
        return False

    try:
        jobs_data = get_run_jobs(run_id)
    except lineage.FreshHoldoutFailureLineageError:
        raise
    except Exception as exc:
        raise lineage._error(
            f"failed to fetch jobs for completed run {run_id}"
        ) from exc
    if type(jobs_data) is not dict or type(jobs_data.get("jobs")) is not list:
        raise lineage._error(f"malformed jobs metadata for completed run {run_id}")
    jobs = [
        job
        for job in jobs_data["jobs"]
        if type(job) is dict and job.get("name") == lineage._PREACQUISITION_JOB_NAME
    ]
    if len(jobs) != 1:
        raise lineage._error(
            f"completed run {run_id} must expose exactly one reviewed collection job"
        )
    job = jobs[0]
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        return False
    steps = job.get("steps")
    if type(steps) is not list:
        raise lineage._error(f"completed run {run_id} job steps are missing")

    by_name: dict[str, Mapping[str, Any]] = {}
    for step in steps:
        if type(step) is not dict:
            raise lineage._error(
                f"completed run {run_id} job step metadata is malformed"
            )
        name = step.get("name")
        if type(name) is not str:
            raise lineage._error(f"completed run {run_id} job step name is invalid")
        if name in by_name:
            raise lineage._error(
                f"completed run {run_id} duplicated job step {name!r}"
            )
        by_name[name] = step

    for name, expected in required_step_outcomes.items():
        step = by_name.get(name)
        if step is None or step.get("status") != "completed":
            return False
        if step.get("conclusion") != expected:
            return False
    return True


def _prove_ambiguous_no_acquisition_success(
    run: Mapping[str, Any],
    artifact_data: Mapping[str, Any],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
) -> bool:
    """Prove a completed green run was the exact reviewed ambiguous no-op path."""
    return _prove_green_zero_artifact_path(
        run,
        artifact_data,
        get_run_jobs,
        expected_event="schedule",
        required_step_outcomes=_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES,
    )


def _prove_continuity_duplicate_no_acquisition_success(
    run: Mapping[str, Any],
    artifact_data: Mapping[str, Any],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
) -> bool:
    """Prove an exact workflow-dispatch continuity duplicate made no observation."""
    return _prove_green_zero_artifact_path(
        run,
        artifact_data,
        get_run_jobs,
        expected_event="workflow_dispatch",
        required_step_outcomes=_CONTINUITY_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES,
    )


def _prove_schedule_duplicate_no_acquisition_success(
    run: Mapping[str, Any],
    artifact_data: Mapping[str, Any],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
) -> bool:
    """Prove a delayed natural schedule run stopped before acquisition."""
    return _prove_green_zero_artifact_path(
        run,
        artifact_data,
        get_run_jobs,
        expected_event="schedule",
        required_step_outcomes=_SCHEDULE_DUPLICATE_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES,
    )


def _prove_continuity_preacquisition_control_failure(
    run: Mapping[str, Any],
    artifact_data: Mapping[str, Any],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
) -> bool:
    """Prove a continuity dispatch failed before provider acquisition/persistence."""
    run_id = run.get("id")
    if type(run_id) is not int or run_id < 1 or run.get("conclusion") != "failure":
        return False
    created_at = lineage._run_created_at(run, run_id)
    if created_at is None or created_at < control.holdout_start_utc():
        return False
    if run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main":
        return False
    artifacts = artifact_data.get("artifacts")
    if type(artifacts) is not list or artifacts:
        return False

    try:
        jobs_data = get_run_jobs(run_id)
    except lineage.FreshHoldoutFailureLineageError:
        raise
    except Exception as exc:
        raise lineage._error(
            f"failed to fetch jobs for completed run {run_id}"
        ) from exc
    if type(jobs_data) is not dict or type(jobs_data.get("jobs")) is not list:
        raise lineage._error(f"malformed jobs metadata for completed run {run_id}")
    jobs = [
        job
        for job in jobs_data["jobs"]
        if type(job) is dict and job.get("name") == lineage._PREACQUISITION_JOB_NAME
    ]
    if len(jobs) != 1:
        raise lineage._error(
            f"completed run {run_id} must expose exactly one reviewed collection job"
        )
    job = jobs[0]
    if job.get("status") != "completed" or job.get("conclusion") != "failure":
        return False
    steps = job.get("steps")
    if type(steps) is not list:
        raise lineage._error(f"completed run {run_id} job steps are missing")

    by_name: dict[str, Mapping[str, Any]] = {}
    for step in steps:
        if type(step) is not dict:
            raise lineage._error(
                f"completed run {run_id} job step metadata is malformed"
            )
        name = step.get("name")
        if type(name) is not str:
            raise lineage._error(f"completed run {run_id} job step name is invalid")
        if name in by_name:
            raise lineage._error(
                f"completed run {run_id} duplicated job step {name!r}"
            )
        by_name[name] = step

    reviewed_step_names = tuple(_CONTINUITY_PREACQUISITION_ALLOWED_STEP_OUTCOMES[0])
    for name in reviewed_step_names:
        step = by_name.get(name)
        if step is None or step.get("status") != "completed":
            return False
    return any(
        all(
            by_name[name].get("conclusion") == expected[name]
            for name in reviewed_step_names
        )
        for expected in _CONTINUITY_PREACQUISITION_ALLOWED_STEP_OUTCOMES
    )


def _has_pre_campaign_completed_run(
    prior_runs: Sequence[Mapping[str, Any]],
) -> bool:
    start = control.holdout_start_utc()
    for run in prior_runs:
        if type(run) is not dict or run.get("status") != "completed":
            continue
        run_id = run.get("id")
        if type(run_id) is not int:
            continue
        created_at = lineage._run_created_at(run, run_id)
        if created_at is not None and created_at < start:
            return True
    return False


def restore_latest_lineage_state(
    *,
    prior_runs: Sequence[Mapping[str, Any]],
    current_run_id: int,
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    get_run_jobs: Callable[[int], Mapping[str, Any]] | None = None,
    repository_root: Path | None = None,
) -> lineage.RestoredFailureLineage:
    """Restore lineage while stepping over exact proven zero-observation no-ops."""
    jobs_reader = get_run_jobs or lineage._github_run_jobs
    filtered: list[Mapping[str, Any]] = []
    skipped_noops: list[int] = []
    stop_scanning = False

    completed = sorted(
        (
            run
            for run in prior_runs
            if type(run) is dict
            and run.get("status") == "completed"
            and run.get("id") != current_run_id
        ),
        key=lambda run: int(run.get("id", -1))
        if type(run.get("id")) is int
        else -1,
        reverse=True,
    )
    eligible_noop_ids: set[int] = set()

    for candidate in completed:
        if stop_scanning:
            break
        run_id = candidate.get("id")
        if type(run_id) is not int or run_id < 1:
            continue
        try:
            artifact_data = get_run_artifacts(run_id)
        except Exception as exc:
            raise lineage._error(
                f"failed to fetch artifacts for newest completed run {run_id}"
            ) from exc
        if (
            type(artifact_data) is not dict
            or type(artifact_data.get("artifacts")) is not list
        ):
            raise lineage._error(
                f"malformed artifact metadata for newest completed run {run_id}"
            )
        canonical = [
            artifact
            for artifact in artifact_data["artifacts"]
            if type(artifact) is dict
            and not artifact.get("expired", False)
            and type(artifact.get("name")) is str
            and lineage._ARTIFACT_NAME.fullmatch(str(artifact.get("name")))
        ]
        if canonical:
            stop_scanning = True
            continue
        if candidate.get("conclusion") == "success":
            proven_noop = _prove_ambiguous_no_acquisition_success(
                candidate,
                artifact_data,
                jobs_reader,
            ) or _prove_continuity_duplicate_no_acquisition_success(
                candidate,
                artifact_data,
                jobs_reader,
            )
            if proven_noop:
                eligible_noop_ids.add(run_id)
                skipped_noops.append(run_id)
                continue
            stop_scanning = True
        elif candidate.get("conclusion") == "failure":
            if _prove_continuity_preacquisition_control_failure(
                candidate,
                artifact_data,
                jobs_reader,
            ):
                eligible_noop_ids.add(run_id)
                skipped_noops.append(run_id)
                continue

    for run in prior_runs:
        run_id = run.get("id") if type(run) is dict else None
        if run_id in eligible_noop_ids:
            continue
        filtered.append(run)

    restored = lineage.restore_latest_lineage_state(
        prior_runs=filtered,
        current_run_id=current_run_id,
        get_run_artifacts=get_run_artifacts,
        download_artifact_zip=download_artifact_zip,
        get_run_jobs=jobs_reader,
        repository_root=repository_root,
    )

    if (
        restored.predecessor_run_id is None
        and skipped_noops
        and len(prior_runs) >= 100
        and not _has_pre_campaign_completed_run(prior_runs)
    ):
        raise lineage._error(
            "campaign-origin recovery cannot prove Genesis because the 100-run "
            "workflow query window did not reach a pre-campaign completed run"
        )

    if not skipped_noops:
        return restored
    combined = tuple(
        sorted(
            set(restored.skipped_preacquisition_failure_run_ids).union(skipped_noops),
            reverse=True,
        )
    )
    return dataclasses.replace(
        restored,
        skipped_preacquisition_failure_run_ids=combined,
    )


def resolve_nominal_schedule_slot_from_lineage(
    schedule_expr: str,
    created_at,
    restored: lineage.RestoredFailureLineage,
):
    return lineage.resolve_nominal_schedule_slot_from_lineage(
        schedule_expr,
        created_at,
        restored,
    )


reconcile_staged_capture_lineage = lineage.reconcile_staged_capture_lineage
RestoredFailureLineage = lineage.RestoredFailureLineage
FreshHoldoutFailureLineageError = lineage.FreshHoldoutFailureLineageError


__all__ = [
    "AMBIGUOUS_NO_ACQUISITION_DISPOSITION",
    "CONTINUITY_ALREADY_ATTEMPTED_NO_ACQUISITION_DISPOSITION",
    "SCHEDULE_ALREADY_ATTEMPTED_NO_ACQUISITION_DISPOSITION",
    "RESOLVED_DISPOSITION",
    "FreshHoldoutFailureLineageError",
    "RestoredFailureLineage",
    "is_ambiguous_schedule_occurrence_error",
    "reconcile_staged_capture_lineage",
    "resolve_nominal_schedule_slot_from_lineage",
    "restore_latest_lineage_state",
]
