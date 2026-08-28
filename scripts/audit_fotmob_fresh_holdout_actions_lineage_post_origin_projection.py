"""Project the reviewed fresh-holdout audit across post-origin no-acquisition failures.

The PR174 audit engine intentionally treated zero-artifact pre-acquisition control
failures as a Genesis-prefix recovery mechanism. Later campaign history contains
an exact reviewed failure shape that occurred after Genesis had already closed:
the schedule-slot resolver failed before acquisition, every acquisition and
reconciliation step was skipped, and no artifact/provider observation existed.

This projection does not infer a nominal slot for such a run and does not reopen
Genesis. It excludes a completed run from nominal source lineage only when the
already-reviewed failure-lineage helper proves the exact zero-artifact
pre-acquisition job-step shape. The existing schedule-recovery projection still
handles successful AMBIGUOUS_NO_ACQUISITION runs. All other runs remain with the
reviewed engine and fail closed normally.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as failure_lineage
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_pr175_projection as pr175
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as schedule_projection


BASE_SCHEDULE_PROJECTION_BLOB_SHA = "c1650a2c9ff55fe119d86985cc183e07531853e6"
FAILURE_LINEAGE_BLOB_SHA = "692e3fe778e43ae4157e10882158f5dae08cb096"
BASE_SCHEDULE_PROJECTION_PATH = (
    "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py"
)
FAILURE_LINEAGE_PATH = (
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage.py"
)

_BASE_COMPATIBLE_AUDIT = schedule_projection._audit_actions_lineage_compatible
_RAW_COLLECTION_CANDIDATE = audit._run_is_collection_candidate


def _git_blob_sha(path: Path) -> str:
    import hashlib

    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _exact_zero_artifacts(value: Mapping[str, Any]) -> bool:
    return (
        type(value) is dict
        and type(value.get("artifacts")) is list
        and not value["artifacts"]
    )


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
        "genesis_reopened": False,
    }


def _audit_actions_lineage_compatible(*args, **kwargs):
    """Compose exact pre-acquisition failure proof with the reviewed projections."""
    if args:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "post-origin projection requires keyword audit arguments"
        )
    get_run_artifacts = kwargs.get("get_run_artifacts")
    get_run_jobs = kwargs.get("get_run_jobs")
    if not callable(get_run_artifacts) or not callable(get_run_jobs):
        return _BASE_COMPATIBLE_AUDIT(**kwargs)

    artifact_cache: dict[int, Mapping[str, Any]] = {}
    jobs_cache: dict[int, Mapping[str, Any]] = {}
    projected_failures: dict[int, Mapping[str, Any]] = {}

    def cached_artifacts(run_id: int) -> Mapping[str, Any]:
        if run_id not in artifact_cache:
            artifact_cache[run_id] = get_run_artifacts(run_id)
        return artifact_cache[run_id]

    def cached_jobs(run_id: int) -> Mapping[str, Any]:
        if run_id not in jobs_cache:
            jobs_cache[run_id] = get_run_jobs(run_id)
        return jobs_cache[run_id]

    def post_origin_candidate(run: Mapping[str, Any]) -> bool:
        if not _RAW_COLLECTION_CANDIDATE(run):
            return False
        run_id = run.get("id")
        if (
            run.get("status") != "completed"
            or run.get("conclusion") != "failure"
            or type(run_id) is not int
            or run_id <= 0
        ):
            return True
        artifacts = cached_artifacts(run_id)
        if not _exact_zero_artifacts(artifacts):
            return True
        try:
            proved = failure_lineage._prove_preacquisition_control_failure(
                run,
                artifacts,
                cached_jobs,
            )
        except failure_lineage.FreshHoldoutFailureLineageError as exc:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "post-origin pre-acquisition control-failure proof failed for "
                f"run {run_id}: {exc}"
            ) from exc
        if not proved:
            return True
        projected_failures[run_id] = run
        return False

    previous_base_candidate = schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE
    schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE = post_origin_candidate
    projected_kwargs = dict(kwargs)
    projected_kwargs["get_run_artifacts"] = cached_artifacts
    projected_kwargs["get_run_jobs"] = cached_jobs
    try:
        result = _BASE_COMPATIBLE_AUDIT(**projected_kwargs)
    finally:
        schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE = (
            previous_base_candidate
        )

    result = dict(result)
    ordered = sorted(
        projected_failures.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    existing_count = result.get("verified_preacquisition_control_failure_count", 0)
    if type(existing_count) is not int or existing_count < 0:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "base audit pre-acquisition failure count is invalid"
        )
    result["verified_preacquisition_control_failure_count"] = (
        existing_count + len(ordered)
    )
    result["projected_post_origin_preacquisition_failure_count"] = len(ordered)
    result["projected_post_origin_preacquisition_failure_runs"] = [
        _projected_preacquisition_failure_record(run) for run in ordered
    ]
    return result


def _verify_projection_dependencies() -> None:
    repo = Path(__file__).resolve().parents[1]
    for relative, expected, label in (
        (
            BASE_SCHEDULE_PROJECTION_PATH,
            BASE_SCHEDULE_PROJECTION_BLOB_SHA,
            "reviewed schedule-recovery audit projection",
        ),
        (
            FAILURE_LINEAGE_PATH,
            FAILURE_LINEAGE_BLOB_SHA,
            "reviewed pre-acquisition failure-lineage helper",
        ),
    ):
        path = repo / relative
        if not path.is_file() or path.is_symlink():
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"{label} path is unavailable"
            )
        if _git_blob_sha(path) != expected:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"{label} blob changed"
            )
    schedule_projection._verify_projection_dependencies()


def main(argv: Sequence[str] | None = None) -> int:
    if audit.WORKFLOW_BLOB_SHA != pr175.PRE_PR175_WORKFLOW_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine workflow pin drifted before post-origin projection"
        )
    if audit.FAILURE_LINEAGE_BLOB_SHA != pr175.PRE_PREACQUISITION_FALLBACK_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine failure-lineage pin drifted before post-origin projection"
        )
    _verify_projection_dependencies()
    audit.WORKFLOW_BLOB_SHA = schedule_projection.POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA
    audit.FAILURE_LINEAGE_BLOB_SHA = pr175.POST_PREACQUISITION_FALLBACK_BLOB_SHA
    audit._gh_download = pr175._gh_download_compatible
    audit.audit_actions_lineage = _audit_actions_lineage_compatible
    return audit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
