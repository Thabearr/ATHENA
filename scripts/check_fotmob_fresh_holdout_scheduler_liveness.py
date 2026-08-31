"""Fail-closed liveness decision for the ATHENA fresh-holdout scheduler.

This module is control-plane only. It never performs provider acquisition, reconstructs
missed observations, chooses a nominal holdout slot, or changes model/production
authority. It decides only whether the reviewed GitHub Actions schedule needs to be
(re-)enabled after an extended absence of scheduled workflow deliveries.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

PRIMARY_WORKFLOW_NAME = "FotMob UTC-Native xG Fresh-Holdout Collection Runner"
PRIMARY_WORKFLOW_PATH = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
PRIMARY_SCHEDULE_RUN_NAME = "ATHENA fresh-holdout schedule source= target= cron= confirm="
DEFAULT_STALE_MINUTES = 90

HEALTHY = "HEALTHY"
ACTIVE_RUN_PRESENT = "ACTIVE_RUN_PRESENT"
ENABLE_DISABLED = "ENABLE_DISABLED"
REREGISTER_STALE_ACTIVE = "REREGISTER_STALE_ACTIVE"


class SchedulerLivenessError(RuntimeError):
    """Raised when GitHub scheduler metadata cannot be trusted exactly."""


def _error(message: str) -> SchedulerLivenessError:
    return SchedulerLivenessError(message)


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z") or value != value.strip():
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(f"{label} must be timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def _utc_text(value: dt.datetime) -> str:
    if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error("now must be timezone-aware")
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _scheduled_runs(
    value: Mapping[str, Any], *, workflow_id: int
) -> list[Mapping[str, Any]]:
    runs = value.get("workflow_runs")
    if type(runs) is not list:
        raise _error("workflow-runs response is malformed")
    out: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    for run in runs:
        if type(run) is not dict:
            raise _error("workflow run metadata must be objects")
        run_id = run.get("id")
        if type(run_id) is not int or run_id < 1 or run_id in seen_ids:
            raise _error("workflow run id is invalid or duplicated")
        seen_ids.add(run_id)
        if run.get("event") != "schedule":
            continue
        if run.get("workflow_id") != workflow_id:
            raise _error(f"scheduled workflow run {run_id} workflow id drifted")
        path = run.get("path")
        if path != PRIMARY_WORKFLOW_PATH:
            raise _error(f"scheduled workflow run {run_id} path drifted")
        status = run.get("status")
        if type(status) is not str or not status:
            raise _error(f"scheduled workflow run {run_id} status is invalid")
        _parse_utc(run.get("created_at"), f"workflow run {run_id} created_at")
        out.append(run)
    out.sort(
        key=lambda run: (
            _parse_utc(run["created_at"], f"workflow run {run['id']} created_at"),
            int(run["id"]),
        ),
        reverse=True,
    )
    return out


def _require_current_schedule_run_name(run: Mapping[str, Any]) -> None:
    run_id = run.get("id")
    if run.get("name") != PRIMARY_SCHEDULE_RUN_NAME:
        raise _error(f"scheduled workflow run {run_id} run-name drifted")


def decide_scheduler_liveness(
    *,
    workflow: Mapping[str, Any],
    runs_response: Mapping[str, Any],
    now: dt.datetime,
    stale_minutes: int = DEFAULT_STALE_MINUTES,
) -> dict[str, Any]:
    """Return an exact control-plane decision without mutating GitHub or holdout state."""
    if type(workflow) is not dict:
        raise _error("workflow metadata must be an object")
    if workflow.get("name") != PRIMARY_WORKFLOW_NAME:
        raise _error("primary workflow name drifted")
    if workflow.get("path") != PRIMARY_WORKFLOW_PATH:
        raise _error("primary workflow path drifted")
    workflow_id = workflow.get("id")
    if type(workflow_id) is not int or workflow_id < 1:
        raise _error("primary workflow id is invalid")
    state = workflow.get("state")
    if type(state) is not str or not state:
        raise _error("primary workflow state is invalid")
    if type(stale_minutes) is not int or stale_minutes < 60:
        raise _error("stale_minutes must be an integer >= 60")
    if type(now) is not dt.datetime or now.tzinfo is None or now.utcoffset() is None:
        raise _error("now must be timezone-aware")
    now_utc = now.astimezone(dt.timezone.utc)

    scheduled = _scheduled_runs(runs_response, workflow_id=workflow_id)
    active = [run for run in scheduled if run["status"] != "completed"]
    if active:
        for run in active:
            _require_current_schedule_run_name(run)
        newest_active = active[0]
        return {
            "decision": ACTIVE_RUN_PRESENT,
            "workflow_id": workflow_id,
            "workflow_state": state,
            "latest_schedule_run_id": newest_active["id"],
            "latest_schedule_created_at": newest_active["created_at"],
            "age_minutes": None,
            "control_plane_mutation_required": False,
            "provider_network_acquisition_authorized": False,
            "backfill_authorized": False,
            "production_authority_changed": False,
        }

    latest = scheduled[0] if scheduled else None
    age_minutes: float | None = None
    latest_id: int | None = None
    latest_created: str | None = None
    if latest is not None:
        latest_id = int(latest["id"])
        latest_created = str(latest["created_at"])
        created = _parse_utc(latest_created, f"workflow run {latest_id} created_at")
        delta = now_utc - created
        if delta.total_seconds() < 0:
            raise _error("latest scheduled workflow run is in the future")
        age_minutes = delta.total_seconds() / 60.0
        if age_minutes <= stale_minutes:
            _require_current_schedule_run_name(latest)

    if state != "active":
        decision = ENABLE_DISABLED
        mutate = True
    elif latest is None or (age_minutes is not None and age_minutes > stale_minutes):
        decision = REREGISTER_STALE_ACTIVE
        mutate = True
    else:
        decision = HEALTHY
        mutate = False

    return {
        "decision": decision,
        "workflow_id": workflow_id,
        "workflow_state": state,
        "latest_schedule_run_id": latest_id,
        "latest_schedule_created_at": latest_created,
        "age_minutes": age_minutes,
        "control_plane_mutation_required": mutate,
        "provider_network_acquisition_authorized": False,
        "backfill_authorized": False,
        "production_authority_changed": False,
    }


def _load(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"could not read {label} JSON") from exc
    if type(value) is not dict:
        raise _error(f"{label} JSON must be an object")
    return value


def _write_outputs(path: Path, result: Mapping[str, Any]) -> None:
    pairs = {
        "decision": result["decision"],
        "workflow_id": result["workflow_id"],
        "workflow_state": result["workflow_state"],
        "latest_schedule_run_id": (
            "null" if result["latest_schedule_run_id"] is None else result["latest_schedule_run_id"]
        ),
        "latest_schedule_created_at": (
            "null"
            if result["latest_schedule_created_at"] is None
            else result["latest_schedule_created_at"]
        ),
        "age_minutes": (
            "null"
            if result["age_minutes"] is None
            else f"{float(result['age_minutes']):.3f}"
        ),
    }
    with path.open("a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            handle.write(f"{key}={value}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-json", type=Path, required=True)
    parser.add_argument("--runs-json", type=Path, required=True)
    parser.add_argument("--now-utc")
    parser.add_argument("--stale-minutes", type=int, default=DEFAULT_STALE_MINUTES)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)

    now = (
        dt.datetime.now(dt.timezone.utc)
        if args.now_utc is None
        else _parse_utc(args.now_utc, "now_utc")
    )
    result = decide_scheduler_liveness(
        workflow=_load(args.workflow_json, "workflow"),
        runs_response=_load(args.runs_json, "workflow runs"),
        now=now,
        stale_minutes=args.stale_minutes,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    if args.github_output is not None:
        _write_outputs(args.github_output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
