"""Prospective-only continuity planner for the FotMob fresh-holdout campaign.

This module does not acquire provider data, choose an historical missed slot,
backfill an observation, or grant model/production/pricing/selection/BET
authority. It only derives one future :07/:37 UTC slot from a real naturally
scheduled watchdog delivery and validates the provenance of a continuity
workflow dispatch for that exact future slot.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping
from typing import Any

WATCHDOG_WORKFLOW_NAME = "Watch FotMob Fresh-Holdout Scheduler Liveness"
WATCHDOG_WORKFLOW_PATH = ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml"
WATCHDOG_JOB_NAME = "verify and repair scheduler control plane"
PRIMARY_WORKFLOW_NAME = "FotMob UTC-Native xG Fresh-Holdout Collection Runner"
PRIMARY_WORKFLOW_ID = 336875088
PRIMARY_WORKFLOW_PATH = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
PRIMARY_SCHEDULE_RUN_NAME = "ATHENA fresh-holdout schedule source= target= cron= confirm="
WATCHDOG_CRON = "3,33 * * * *"
PRIMARY_CRON_BY_MINUTE = {7: "7 * * * *", 37: "37 * * * *"}
MINIMUM_ARM_LEAD_SECONDS = 90
PRIMARY_DELIVERY_GRACE_SECONDS = 90
MAXIMUM_ARM_HORIZON_SECONDS = 40 * 60
MAXIMUM_DISPATCH_LATE_SECONDS = 5 * 60
MAXIMUM_DISPATCH_EARLY_SECONDS = 30
CONTINUITY_CONFIRMATION = "PROSPECTIVE_ONLY_NO_BACKFILL_V1"
WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS = (
    "Validate exact control trigger",
    "Check out exact current main",
    "Set up Python 3.12",
    "Verify exact main and reviewed control dependencies",
    "Plan one prospective continuity slot",
    "Wait through natural primary delivery grace",
    "Dispatch prospective continuity tick if primary delivery is absent",
    "Record prospective continuity dispatch request",
)


class FreshHoldoutContinuityError(RuntimeError):
    """Raised when prospective continuity provenance cannot be proved exactly."""


def _error(message: str) -> FreshHoldoutContinuityError:
    return FreshHoldoutContinuityError(message)


def _utc(value: Any, label: str) -> dt.datetime:
    if type(value) is dt.datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise _error(f"{label} must be timezone-aware")
        return value.astimezone(dt.timezone.utc)
    if type(value) is not str or value != value.strip() or not value.endswith("Z"):
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    return parsed.astimezone(dt.timezone.utc)


def utc_text(value: dt.datetime) -> str:
    return _utc(value, "datetime").isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 40
        or any(ch not in "0123456789abcdef" for ch in value.lower())
    ):
        raise _error(f"{label} must be a 40-character hexadecimal Git SHA")
    return value.lower()


@dataclasses.dataclass(frozen=True)
class ContinuityPlan:
    source_watchdog_created_at: dt.datetime
    target_slot: dt.datetime
    target_cron: str

    def __post_init__(self) -> None:
        source = _utc(self.source_watchdog_created_at, "source_watchdog_created_at")
        target = _utc(self.target_slot, "target_slot")
        object.__setattr__(self, "source_watchdog_created_at", source)
        object.__setattr__(self, "target_slot", target)
        expected = PRIMARY_CRON_BY_MINUTE.get(target.minute)
        if (
            expected is None
            or target.second != 0
            or target.microsecond != 0
            or self.target_cron != expected
        ):
            raise _error("target slot is not an exact reviewed :07/:37 UTC occurrence")
        lead = (target - source).total_seconds()
        if lead < MINIMUM_ARM_LEAD_SECONDS:
            raise _error("continuity target does not leave the reviewed minimum arm lead")
        if lead > MAXIMUM_ARM_HORIZON_SECONDS:
            raise _error("continuity target is too far from its watchdog source delivery")

    @property
    def target_slot_text(self) -> str:
        return utc_text(self.target_slot)


def plan_from_watchdog_created_at(value: Any) -> ContinuityPlan:
    """Derive exactly one future primary-lattice slot from a watchdog delivery."""
    source = _utc(value, "watchdog created_at")
    threshold = source + dt.timedelta(seconds=MINIMUM_ARM_LEAD_SECONDS)
    base_hour = threshold.replace(minute=0, second=0, microsecond=0)
    candidates: list[dt.datetime] = []
    for hour_offset in range(3):
        hour = base_hour + dt.timedelta(hours=hour_offset)
        for minute in sorted(PRIMARY_CRON_BY_MINUTE):
            candidate = hour.replace(minute=minute)
            if candidate >= threshold:
                candidates.append(candidate)
    if not candidates:
        raise _error("could not derive a future reviewed continuity slot")
    target = min(candidates)
    return ContinuityPlan(
        source_watchdog_created_at=source,
        target_slot=target,
        target_cron=PRIMARY_CRON_BY_MINUTE[target.minute],
    )


def validate_watchdog_source_run(
    value: Mapping[str, Any],
    *,
    expected_run_id: int,
    expected_main_sha: str,
) -> dt.datetime:
    if type(value) is not dict:
        raise _error("watchdog run metadata must be an exact object")
    if type(expected_run_id) is not int or expected_run_id < 1:
        raise _error("expected watchdog run id is invalid")
    if value.get("id") != expected_run_id:
        raise _error("watchdog run id differs from requested continuity source")
    if value.get("name") != WATCHDOG_WORKFLOW_NAME:
        raise _error("watchdog workflow name drifted")
    if value.get("path") != WATCHDOG_WORKFLOW_PATH:
        raise _error("watchdog workflow path drifted")
    if value.get("event") != "schedule":
        raise _error("continuity source must be a naturally scheduled watchdog run")
    if value.get("head_branch") != "main":
        raise _error("watchdog source must execute from main")
    if _sha(value.get("head_sha"), "watchdog head_sha") != _sha(
        expected_main_sha, "expected main SHA"
    ):
        raise _error("watchdog source head differs from the pinned main SHA")
    return _utc(value.get("created_at"), "watchdog created_at")


def validate_watchdog_source_jobs(
    value: Mapping[str, Any],
    *,
    expected_run_id: int,
    expected_main_sha: str,
) -> dt.datetime:
    """Independently prove the watchdog took its reviewed scheduled dispatch path.

    GitHub's jobs metadata is a separate read from the continuity receipt. Requiring
    the schedule-only planning step and the conditional dispatch-record step to have
    succeeded proves that the reviewed watchdog, on the same exact main SHA, reached
    the branch that requested one prospective continuity dispatch.
    """
    if type(value) is not dict or type(value.get("jobs")) is not list:
        raise _error("watchdog jobs metadata must expose an exact jobs list")
    if type(expected_run_id) is not int or expected_run_id < 1:
        raise _error("expected watchdog run id is invalid")
    expected_sha = _sha(expected_main_sha, "expected main SHA")
    jobs = [
        job
        for job in value["jobs"]
        if type(job) is dict and job.get("name") == WATCHDOG_JOB_NAME
    ]
    if len(jobs) != 1:
        raise _error("watchdog source must expose exactly one reviewed control job")
    job = jobs[0]
    if job.get("run_id") != expected_run_id:
        raise _error("watchdog job run id differs from continuity source")
    if job.get("workflow_name") != WATCHDOG_WORKFLOW_NAME:
        raise _error("watchdog job workflow name drifted")
    if job.get("head_branch") != "main":
        raise _error("watchdog job must execute from main")
    if _sha(job.get("head_sha"), "watchdog job head_sha") != expected_sha:
        raise _error("watchdog job head differs from continuity dispatch head")
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        raise _error("watchdog dispatch source job did not complete successfully")
    steps = job.get("steps")
    if type(steps) is not list:
        raise _error("watchdog source job steps are missing")
    by_name: dict[str, Mapping[str, Any]] = {}
    for step in steps:
        if type(step) is not dict or type(step.get("name")) is not str:
            raise _error("watchdog source job step metadata is malformed")
        name = step["name"]
        if name in by_name:
            raise _error(f"watchdog source duplicated job step {name!r}")
        by_name[name] = step
    for name in WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS:
        step = by_name.get(name)
        if (
            step is None
            or step.get("status") != "completed"
            or step.get("conclusion") != "success"
        ):
            raise _error(f"watchdog source did not prove reviewed step {name!r}")
    return _utc(job.get("created_at"), "watchdog job created_at")


def validate_continuity_dispatch(
    *,
    watchdog_run: Mapping[str, Any],
    dispatch_run: Mapping[str, Any],
    source_watchdog_run_id: int,
    current_main_sha: str,
    requested_target_slot: Any,
    requested_target_cron: str,
    confirmation: str,
) -> ContinuityPlan:
    """Validate a primary workflow_dispatch as one prospective continuity tick."""
    if confirmation != CONTINUITY_CONFIRMATION:
        raise _error("continuity confirmation token is invalid")
    current_sha = _sha(current_main_sha, "current main SHA")
    source_created = validate_watchdog_source_run(
        watchdog_run,
        expected_run_id=source_watchdog_run_id,
        expected_main_sha=current_sha,
    )
    plan = plan_from_watchdog_created_at(source_created)
    requested_target = _utc(requested_target_slot, "requested target slot")
    if requested_target != plan.target_slot or requested_target_cron != plan.target_cron:
        raise _error("continuity dispatch target differs from deterministic watchdog plan")

    if type(dispatch_run) is not dict:
        raise _error("dispatch run metadata must be an exact object")
    if dispatch_run.get("workflow_id") != PRIMARY_WORKFLOW_ID:
        raise _error("dispatch workflow id drifted")
    expected_run_name = (
        "ATHENA fresh-holdout workflow_dispatch "
        f"source={source_watchdog_run_id} "
        f"target={plan.target_slot_text} "
        f"cron={plan.target_cron} "
        f"confirm={CONTINUITY_CONFIRMATION}"
    )
    if dispatch_run.get("name") != expected_run_name:
        raise _error("dispatch workflow run-name drifted")
    if dispatch_run.get("path") != PRIMARY_WORKFLOW_PATH:
        raise _error("dispatch workflow path drifted")
    if dispatch_run.get("event") != "workflow_dispatch":
        raise _error("continuity execution must be a workflow_dispatch run")
    if dispatch_run.get("head_branch") != "main":
        raise _error("continuity dispatch must execute from main")
    if _sha(dispatch_run.get("head_sha"), "dispatch head_sha") != current_sha:
        raise _error("continuity dispatch head differs from current main")
    dispatch_created = _utc(dispatch_run.get("created_at"), "dispatch created_at")
    earliest = plan.target_slot - dt.timedelta(seconds=MAXIMUM_DISPATCH_EARLY_SECONDS)
    latest = plan.target_slot + dt.timedelta(seconds=MAXIMUM_DISPATCH_LATE_SECONDS)
    if not earliest <= dispatch_created <= latest:
        raise _error("continuity dispatch was not created at the planned prospective slot")
    return plan


def seconds_until_target(plan: ContinuityPlan, *, now: Any) -> int:
    """Return bounded wait seconds; never permit a late dispatch to retrofill."""
    if type(plan) is not ContinuityPlan:
        raise _error("exact ContinuityPlan is required")
    current = _utc(now, "now")
    remaining = (plan.target_slot - current).total_seconds()
    if remaining < -MAXIMUM_DISPATCH_EARLY_SECONDS:
        raise _error("planned continuity slot is already in the past; no dispatch allowed")
    if remaining <= 0:
        return 0
    if remaining > MAXIMUM_ARM_HORIZON_SECONDS:
        raise _error("continuity wait exceeds reviewed prospective horizon")
    return int(remaining + 0.999999)


def seconds_until_dispatch_check(plan: ContinuityPlan, *, now: Any) -> int:
    """Wait through a short natural-primary grace period before continuity dispatch."""
    if type(plan) is not ContinuityPlan:
        raise _error("exact ContinuityPlan is required")
    current = _utc(now, "now")
    latest = plan.target_slot + dt.timedelta(seconds=MAXIMUM_DISPATCH_LATE_SECONDS)
    if current > latest:
        raise _error("continuity dispatch window already expired; no retrofill allowed")
    dispatch_check = plan.target_slot + dt.timedelta(
        seconds=PRIMARY_DELIVERY_GRACE_SECONDS
    )
    remaining = (dispatch_check - current).total_seconds()
    if remaining <= 0:
        return 0
    if remaining > MAXIMUM_ARM_HORIZON_SECONDS + PRIMARY_DELIVERY_GRACE_SECONDS:
        raise _error("continuity dispatch wait exceeds reviewed prospective horizon")
    return int(remaining + 0.999999)


def durable_targets_for_plan(
    plan: ContinuityPlan,
    *,
    run_id: int,
) -> tuple[str, str, str, str]:
    """Derive exact durable identities for one already-reviewed future target slot."""
    if type(plan) is not ContinuityPlan:
        raise _error("exact ContinuityPlan is required")
    if type(run_id) is not int or run_id < 1:
        raise _error("workflow run id must be a positive integer")
    nominal = plan.target_slot
    nominal_iso = nominal.isoformat(timespec="microseconds").replace("+00:00", "Z")
    compact = nominal.strftime("%Y%m%dT%H%M%SZ")
    iso_year, iso_week, _ = nominal.isocalendar()
    release_tag = f"athena-fresh-holdout-evidence-{iso_year}-W{iso_week:02d}"
    success_asset = f"success-{compact}-run-{run_id}.tar.gz"
    failure_asset = f"failure-{compact}-run-{run_id}.tar.gz"
    return nominal_iso, release_tag, success_asset, failure_asset


def lineage_already_attempted_target(*, last_attempted_utc: Any, target_slot: Any) -> bool:
    """Return True when durable lineage proves the exact slot was already attempted."""
    if last_attempted_utc is None:
        return False
    last = _utc(last_attempted_utc, "last_attempted_utc")
    target = _utc(target_slot, "target_slot")
    return last >= target


__all__ = [
    "CONTINUITY_CONFIRMATION",
    "MAXIMUM_ARM_HORIZON_SECONDS",
    "MAXIMUM_DISPATCH_EARLY_SECONDS",
    "MAXIMUM_DISPATCH_LATE_SECONDS",
    "MINIMUM_ARM_LEAD_SECONDS",
    "PRIMARY_CRON_BY_MINUTE",
    "PRIMARY_DELIVERY_GRACE_SECONDS",
    "PRIMARY_SCHEDULE_RUN_NAME",
    "PRIMARY_WORKFLOW_ID",
    "PRIMARY_WORKFLOW_NAME",
    "PRIMARY_WORKFLOW_PATH",
    "WATCHDOG_CRON",
    "WATCHDOG_JOB_NAME",
    "WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS",
    "WATCHDOG_WORKFLOW_NAME",
    "WATCHDOG_WORKFLOW_PATH",
    "ContinuityPlan",
    "FreshHoldoutContinuityError",
    "durable_targets_for_plan",
    "lineage_already_attempted_target",
    "plan_from_watchdog_created_at",
    "seconds_until_dispatch_check",
    "seconds_until_target",
    "utc_text",
    "validate_continuity_dispatch",
    "validate_watchdog_source_jobs",
    "validate_watchdog_source_run",
]
