"""Project the read-only fresh-holdout audit across no-acquisition recovery paths.

The underlying lineage audit remains the reviewed engine. This projection updates
only its pinned runtime dependency identities and makes two evidence-transparent
compatibility allowances for completed scheduled runs that provably acquired no
provider bytes:

1. a successful AMBIGUOUS_NO_ACQUISITION recovery run (the reviewed schedule
   recovery path); and
2. a failed pre-acquisition control run whose exact GitHub job-step shape is
   already proved by the reviewed failure-lineage helper.

Both run types are excluded from nominal source lineage because neither observed
provider bytes and neither can represent a nominal fixture observation. A proven
pre-acquisition failure may occur after campaign Genesis has already closed; it
must not reopen Genesis, invent a nominal slot, or block auditing later durable
campaign evidence merely because it has zero artifacts.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as failure_lineage
import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_pr175_projection as pr175


PRE_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA = pr175.POST_PR175_WORKFLOW_BLOB_SHA
POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA = "eb6cfd3966d7040f630fc3a51c6cad41b171bcfb"
SCHEDULE_RECOVERY_BLOB_SHA = "73ed6ef7cdcc79b43373a78c60b5f2b6dd601095"
SCHEDULE_RECOVERY_PATH = (
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py"
)

_ORIGINAL_AUDIT_ACTIONS_LINEAGE = audit.audit_actions_lineage
_ORIGINAL_RUN_IS_COLLECTION_CANDIDATE = audit._run_is_collection_candidate


def _git_blob_sha(path: Path) -> str:
    import hashlib

    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _projected_noop_record(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "created_at": run.get("created_at"),
        "head_sha": run.get("head_sha"),
        "conclusion": run.get("conclusion"),
        "evidence_state": "VERIFIED_AMBIGUOUS_NO_ACQUISITION",
        "nominal_slot_utc": None,
        "tick_committed": False,
        "archive_name": None,
        "archive_sha256": None,
        "release_state": "NOT_APPLICABLE_NO_ACQUISITION",
        "verification_error": None,
    }


def _projected_preacquisition_failure_record(
    run: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "created_at": run.get("created_at"),
        "head_sha": run.get("head_sha"),
        "conclusion": run.get("conclusion"),
        "evidence_state": "VERIFIED_PREACQUISITION_CONTROL_FAILURE",
        "nominal_slot_utc": None,
        "tick_committed": False,
        "archive_name": None,
        "archive_sha256": None,
        "release_state": "NOT_APPLICABLE_NO_ACQUISITION",
        "verification_error": None,
    }


def _exact_zero_artifacts(value: Mapping[str, Any]) -> bool:
    return (
        type(value) is dict
        and type(value.get("artifacts")) is list
        and not value["artifacts"]
    )


def _audit_actions_lineage_compatible(*args, **kwargs):
    """Run the unchanged engine while projecting out proven zero-evidence runs."""
    if args:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "schedule-recovery projection requires keyword audit arguments"
        )
    get_run_artifacts = kwargs.get("get_run_artifacts")
    get_run_jobs = kwargs.get("get_run_jobs")
    if not callable(get_run_artifacts) or not callable(get_run_jobs):
        return _ORIGINAL_AUDIT_ACTIONS_LINEAGE(**kwargs)

    artifact_cache: dict[int, Mapping[str, Any]] = {}
    jobs_cache: dict[int, Mapping[str, Any]] = {}
    projected_noops: dict[int, Mapping[str, Any]] = {}
    projected_preacquisition_failures: dict[int, Mapping[str, Any]] = {}

    def cached_artifacts(run_id: int) -> Mapping[str, Any]:
        if run_id not in artifact_cache:
            artifact_cache[run_id] = get_run_artifacts(run_id)
        return artifact_cache[run_id]

    def cached_jobs(run_id: int) -> Mapping[str, Any]:
        if run_id not in jobs_cache:
            jobs_cache[run_id] = get_run_jobs(run_id)
        return jobs_cache[run_id]

    def projected_candidate(run: Mapping[str, Any]) -> bool:
        if not _ORIGINAL_RUN_IS_COLLECTION_CANDIDATE(run):
            return False
        run_id = run.get("id")
        if (
            run.get("status") != "completed"
            or type(run_id) is not int
            or run_id <= 0
        ):
            return True

        artifacts = cached_artifacts(run_id)
        if run.get("conclusion") == "success":
            if recovery._prove_ambiguous_no_acquisition_success(
                run,
                artifacts,
                cached_jobs,
            ):
                projected_noops[run_id] = run
                return False
            return True

        if run.get("conclusion") == "failure" and _exact_zero_artifacts(artifacts):
            try:
                proved_preacquisition = (
                    failure_lineage._prove_preacquisition_control_failure(
                        run,
                        artifacts,
                        cached_jobs,
                    )
                )
            except failure_lineage.FreshHoldoutFailureLineageError as exc:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "pre-acquisition control-failure projection proof failed for "
                    f"run {run_id}: {exc}"
                ) from exc
            if proved_preacquisition:
                projected_preacquisition_failures[run_id] = run
                return False
        return True

    previous_candidate = audit._run_is_collection_candidate
    audit._run_is_collection_candidate = projected_candidate
    projected_kwargs = dict(kwargs)
    projected_kwargs["get_run_artifacts"] = cached_artifacts
    projected_kwargs["get_run_jobs"] = cached_jobs
    try:
        result = _ORIGINAL_AUDIT_ACTIONS_LINEAGE(**projected_kwargs)
    finally:
        audit._run_is_collection_candidate = previous_candidate

    result = dict(result)
    ordered_noops = sorted(
        projected_noops.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    ordered_failures = sorted(
        projected_preacquisition_failures.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    result["verified_ambiguous_no_acquisition_count"] = len(ordered_noops)
    result["projected_ambiguous_no_acquisition_runs"] = [
        _projected_noop_record(run) for run in ordered_noops
    ]
    base_preacquisition_count = result.get(
        "verified_preacquisition_control_failure_count", 0
    )
    if type(base_preacquisition_count) is not int or base_preacquisition_count < 0:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "base audit pre-acquisition failure count is invalid"
        )
    result["verified_preacquisition_control_failure_count"] = (
        base_preacquisition_count + len(ordered_failures)
    )
    result["projected_preacquisition_control_failure_count"] = len(
        ordered_failures
    )
    result["projected_preacquisition_control_failure_runs"] = [
        _projected_preacquisition_failure_record(run) for run in ordered_failures
    ]
    return result


def _verify_projection_dependencies() -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / SCHEDULE_RECOVERY_PATH
    if not helper.is_file() or helper.is_symlink():
        raise audit.FreshHoldoutActionsLineageAuditError(
            "schedule-recovery helper path is unavailable"
        )
    if _git_blob_sha(helper) != SCHEDULE_RECOVERY_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "schedule-recovery helper blob changed"
        )


def main(argv: Sequence[str] | None = None) -> int:
    if audit.WORKFLOW_BLOB_SHA != pr175.PRE_PR175_WORKFLOW_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine workflow pin drifted before schedule-recovery projection"
        )
    if audit.FAILURE_LINEAGE_BLOB_SHA != pr175.PRE_PREACQUISITION_FALLBACK_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine failure-lineage pin drifted before schedule-recovery projection"
        )
    _verify_projection_dependencies()
    audit.WORKFLOW_BLOB_SHA = POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA
    audit.FAILURE_LINEAGE_BLOB_SHA = pr175.POST_PREACQUISITION_FALLBACK_BLOB_SHA
    audit._gh_download = pr175._gh_download_compatible
    audit.audit_actions_lineage = _audit_actions_lineage_compatible
    return audit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
