"""Project the read-only fresh-holdout audit across reviewed no-acquisition recovery.

The underlying lineage audit remains the reviewed engine. This projection updates
only its pinned runtime dependency identities and makes evidence-transparent
compatibility allowances for completed scheduled runs that GitHub metadata proves
could not contain a provider observation:

* exact AMBIGUOUS_NO_ACQUISITION successes; and
* exact zero-artifact pre-acquisition failures admitted by the current reviewed
  producer-side proof.

The current producer also contains the separately source-authenticated prospective
continuity transport. This projection admits a continuity collection only after
replaying its immutable dispatch/watchdog provenance; it never relabels that run as
a natural schedule delivery.

The second allowance matches the post-PR207 producer boundary. A proven
pre-acquisition failure may be transparent even after canonical campaign evidence
exists, but projecting it out never reopens Genesis: the unchanged audit engine
still derives campaign-origin state from the remaining chronological evidence.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery
import domain.fotmob_fresh_holdout_continuity as continuity
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_pr175_projection as pr175
import scripts.run_fotmob_fresh_holdout_release_receipt_mirror as receipt_mirror


PRE_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA = pr175.POST_PR175_WORKFLOW_BLOB_SHA
POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA = "f6d3e9e5e4c7306c13b2b618788811da4d2d41f8"
SCHEDULE_RECOVERY_BLOB_SHA = "e24929813e5666c5477aa8906cf36cc7ef6ffcc4"
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


def _projected_preacquisition_record(run: Mapping[str, Any]) -> dict[str, Any]:
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


def _prove_continuity_candidate(
    run: Mapping[str, Any],
    *,
    get_run_by_id,
    get_run_jobs,
) -> continuity.ContinuityPlan:
    """Replay the immutable prospective dispatch provenance before audit admission."""
    title = run.get("display_title")
    match = (
        receipt_mirror.CONTINUITY_RUN_NAME_RE.fullmatch(title)
        if type(title) is str
        else None
    )
    if match is None:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "workflow_dispatch run escaped continuity provenance grammar"
        )
    source_run_id = int(match.group(1))
    dispatch_sha = run.get("head_sha")
    try:
        # A continuity observation remains historical evidence after main moves.
        # Its exact execution SHA, not audit-time main, binds both executions.
        continuity.validate_watchdog_source_jobs(
            get_run_jobs(source_run_id),
            expected_run_id=source_run_id,
            expected_main_sha=dispatch_sha,
        )
        return continuity.validate_continuity_dispatch(
            watchdog_run=get_run_by_id(source_run_id),
            dispatch_run=run,
            source_watchdog_run_id=source_run_id,
            current_main_sha=dispatch_sha,
            requested_target_slot=match.group(2),
            requested_target_cron=match.group(3),
            confirmation=match.group(4),
        )
    except continuity.FreshHoldoutContinuityError as exc:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity dispatch provenance replay failed"
        ) from exc


def _audit_actions_lineage_compatible(*args, **kwargs):
    """Run the unchanged engine while projecting exact zero-observation runs."""
    if args:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "schedule-recovery projection requires keyword audit arguments"
        )
    get_run_artifacts = kwargs.get("get_run_artifacts")
    get_run_jobs = kwargs.get("get_run_jobs")
    get_run_by_id = kwargs.get("get_run_by_id")
    if (
        not callable(get_run_artifacts)
        or not callable(get_run_jobs)
        or not callable(get_run_by_id)
    ):
        return _ORIGINAL_AUDIT_ACTIONS_LINEAGE(**kwargs)

    artifact_cache: dict[int, Mapping[str, Any]] = {}
    jobs_cache: dict[int, Mapping[str, Any]] = {}
    projected_noops: dict[int, Mapping[str, Any]] = {}
    projected_preacquisition: dict[int, Mapping[str, Any]] = {}
    projected_continuities: dict[int, continuity.ContinuityPlan] = {}

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
            if run.get("event") != "workflow_dispatch":
                return False
            if (
                run.get("name") != continuity.PRIMARY_WORKFLOW_NAME
                or run.get("path") not in {
                    continuity.PRIMARY_WORKFLOW_PATH,
                    f"{continuity.PRIMARY_WORKFLOW_PATH}@{run.get('head_sha', '')}",
                }
                or run.get("head_branch") != "main"
            ):
                return False
            run_id = run.get("id")
            if type(run_id) is not int or run_id <= 0:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "continuity dispatch run id is invalid"
                )
            projected_continuities[run_id] = _prove_continuity_candidate(
                run,
                get_run_by_id=get_run_by_id,
                get_run_jobs=cached_jobs,
            )
            return True
        run_id = run.get("id")
        if run.get("status") != "completed" or type(run_id) is not int or run_id <= 0:
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
        elif run.get("conclusion") == "failure":
            try:
                proved_preacquisition = (
                    audit.failure_lineage._prove_preacquisition_control_failure(
                        run,
                        artifacts,
                        cached_jobs,
                    )
                )
            except audit.failure_lineage.FreshHoldoutFailureLineageError as exc:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "pre-acquisition control-failure projection proof failed for run "
                    f"{run_id}: {exc}"
                ) from exc
            if proved_preacquisition:
                projected_preacquisition[run_id] = run
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
    for record in result.get("runs", []):
        if type(record) is not dict:
            continue
        plan = projected_continuities.get(record.get("run_id"))
        if plan is None:
            record["execution_provenance"] = "NATURAL_SCHEDULE"
            continue
        if record.get("nominal_slot_utc") != plan.target_slot_text:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "continuity artifact nominal slot differs from authenticated target"
            )
        record["execution_provenance"] = "PROSPECTIVE_CONTINUITY_DISPATCH"
        record["continuity_target_slot"] = plan.target_slot_text
        record["continuity_target_cron"] = plan.target_cron
    result["verified_prospective_continuity_dispatch_count"] = len(
        projected_continuities
    )
    ordered_noops = sorted(
        projected_noops.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    ordered_preacquisition = sorted(
        projected_preacquisition.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    result["verified_ambiguous_no_acquisition_count"] = len(ordered_noops)
    result["projected_ambiguous_no_acquisition_runs"] = [
        _projected_noop_record(run) for run in ordered_noops
    ]

    existing_preacquisition = result.get(
        "verified_preacquisition_control_failure_count", 0
    )
    if type(existing_preacquisition) is not int or existing_preacquisition < 0:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "audit engine returned invalid pre-acquisition control-failure count"
        )
    result["verified_preacquisition_control_failure_count"] = (
        existing_preacquisition + len(ordered_preacquisition)
    )
    result["projected_preacquisition_control_failure_runs"] = [
        _projected_preacquisition_record(run) for run in ordered_preacquisition
    ]
    if (
        ordered_preacquisition
        and result.get("audit_state") == "NO_COMPLETED_CAMPAIGN_EVIDENCE"
    ):
        # Preserve the base engine's historical semantics: a proven failed control
        # attempt before Genesis is verified metadata, but there is still no nominal
        # source observation to promote into completed campaign evidence.
        result["audit_state"] = "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"
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
