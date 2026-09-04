"""Project the read-only fresh-holdout audit across reviewed no-acquisition recovery.

The underlying lineage audit remains the reviewed engine. This projection updates
only its pinned runtime dependency identities and makes evidence-transparent
compatibility allowances for GitHub runs that exact metadata proves could not
contain a provider observation:

* exact AMBIGUOUS_NO_ACQUISITION successes;
* exact zero-artifact pre-acquisition failures admitted by the current reviewed
  producer-side proof; and
* one exact historical queued workflow_dispatch that never acquired a job or
  artifact and predates the reviewed prospective-continuity run-name boundary.

The current producer also contains the separately source-authenticated prospective
continuity transport. This projection admits a continuity collection only after
replaying its immutable dispatch/watchdog provenance; it never relabels that run as
a natural schedule delivery.

The historical queued allowance is identity-bound to the exact GitHub run observed
by the post-PR293 operational proof. It is not a generic queued-run or dispatch
bypass: any metadata drift, job appearance, or artifact appearance fails closed.

The pre-acquisition allowance matches the post-PR207 producer boundary. A proven
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
POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA = "ee928ba29c7108c203402ff8efabf3d6fc3e4e00"
SCHEDULE_RECOVERY_BLOB_SHA = "7fe531dfb6bba96c7e6505016b89761f0d25428f"
SCHEDULE_RECOVERY_PATH = (
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py"
)

LEGACY_QUEUED_NO_EXECUTION_RUN_ID = 33576163735
LEGACY_QUEUED_NO_EXECUTION_HEAD_SHA = "548271e960839003d64aef79f6f27f0a1a442abf"
LEGACY_QUEUED_NO_EXECUTION_CREATED_AT = "2026-09-02T00:38:33Z"
LEGACY_QUEUED_NO_EXECUTION_RUN_NUMBER = 423
LEGACY_QUEUED_NO_EXECUTION_TITLE = "FotMob UTC-Native xG Fresh-Holdout Collection Runner"

_ORIGINAL_AUDIT_ACTIONS_LINEAGE = audit.audit_actions_lineage
_ORIGINAL_RUN_IS_COLLECTION_CANDIDATE = audit._run_is_collection_candidate


def _fixed_get_run_by_id(
    repository: str,
    run_id: int,
) -> Mapping[str, Any]:
    """Read exactly one Actions run for the direct projection CLI.

    Current-history construction supplies its own recorder-backed reader. This
    helper is only the projection-owned live CLI/workflow fallback, and is
    deliberately limited to the exact run-metadata endpoint.
    """
    if (
        type(repository) is not str
        or repository.count("/") != 1
        or repository != repository.strip()
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity exact-run reader requires an exact repository identity"
        )
    if type(run_id) is not int or run_id <= 0:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity source watchdog run id is invalid"
        )
    return audit._gh_json(f"/repos/{repository}/actions/runs/{run_id}")


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
    record = {
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
    if run.get("event") == "workflow_dispatch":
        record["execution_provenance"] = (
            "PROSPECTIVE_CONTINUITY_DISPATCH_PREACQUISITION_FAILURE"
        )
    return record


def _projected_continuity_noop_record(run: Mapping[str, Any]) -> dict[str, Any]:
    record = _projected_noop_record(run)
    record["execution_provenance"] = (
        "PROSPECTIVE_CONTINUITY_DISPATCH_NO_ACQUISITION"
    )
    return record


def _projected_legacy_queued_no_execution_record(
    run: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "created_at": run.get("created_at"),
        "head_sha": run.get("head_sha"),
        "conclusion": None,
        "evidence_state": "VERIFIED_LEGACY_QUEUED_NO_EXECUTION",
        "execution_provenance": "PRE_CONTINUITY_LEGACY_WORKFLOW_DISPATCH_NO_EXECUTION",
        "nominal_slot_utc": None,
        "tick_committed": False,
        "archive_name": None,
        "archive_sha256": None,
        "release_state": "NOT_APPLICABLE_NO_ACQUISITION",
        "verification_error": None,
    }


def _prove_exact_legacy_queued_no_execution_dispatch(
    run: Mapping[str, Any],
    *,
    get_run_artifacts,
    get_run_jobs,
) -> bool:
    """Prove the one historical queued dispatch never reached execution."""
    if run.get("id") != LEGACY_QUEUED_NO_EXECUTION_RUN_ID:
        return False
    expected = {
        "name": LEGACY_QUEUED_NO_EXECUTION_TITLE,
        "display_title": LEGACY_QUEUED_NO_EXECUTION_TITLE,
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID,
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": LEGACY_QUEUED_NO_EXECUTION_HEAD_SHA,
        "status": "queued",
        "conclusion": None,
        "run_number": LEGACY_QUEUED_NO_EXECUTION_RUN_NUMBER,
        "run_attempt": 1,
        "created_at": LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
        "updated_at": LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
        "run_started_at": LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
    }
    for key, value in expected.items():
        if run.get(key) != value:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"legacy queued dispatch metadata drifted: {key}"
            )

    artifacts = get_run_artifacts(LEGACY_QUEUED_NO_EXECUTION_RUN_ID)
    if (
        not isinstance(artifacts, Mapping)
        or artifacts.get("total_count") != 0
        or artifacts.get("artifacts") != []
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "legacy queued dispatch unexpectedly acquired artifact evidence"
        )
    jobs = get_run_jobs(LEGACY_QUEUED_NO_EXECUTION_RUN_ID)
    if (
        not isinstance(jobs, Mapping)
        or jobs.get("total_count") != 0
        or jobs.get("jobs") != []
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "legacy queued dispatch unexpectedly acquired execution jobs"
        )
    return True


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

    # get_run_by_id belongs to this compatibility projection only. Consume it
    # before any delegation so the frozen raw audit signature stays untouched.
    get_run_by_id = kwargs.pop("get_run_by_id", None)
    get_run_artifacts = kwargs.get("get_run_artifacts")
    get_run_jobs = kwargs.get("get_run_jobs")
    if not callable(get_run_artifacts) or not callable(get_run_jobs):
        return _ORIGINAL_AUDIT_ACTIONS_LINEAGE(**kwargs)
    if get_run_by_id is None:
        repository = kwargs.get("repository")
        get_run_by_id = lambda run_id: _fixed_get_run_by_id(repository, run_id)
    elif not callable(get_run_by_id):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity exact-run reader must be callable"
        )

    artifact_cache: dict[int, Mapping[str, Any]] = {}
    jobs_cache: dict[int, Mapping[str, Any]] = {}
    projected_noops: dict[int, Mapping[str, Any]] = {}
    projected_schedule_duplicates: dict[int, Mapping[str, Any]] = {}
    projected_continuity_noops: dict[int, Mapping[str, Any]] = {}
    projected_preacquisition: dict[int, Mapping[str, Any]] = {}
    projected_legacy_queued: dict[int, Mapping[str, Any]] = {}
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
                run.get("workflow_id") != continuity.PRIMARY_WORKFLOW_ID
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
            if _prove_exact_legacy_queued_no_execution_dispatch(
                run,
                get_run_artifacts=cached_artifacts,
                get_run_jobs=cached_jobs,
            ):
                projected_legacy_queued[run_id] = run
                return False
            projected_continuities[run_id] = _prove_continuity_candidate(
                run,
                get_run_by_id=get_run_by_id,
                get_run_jobs=cached_jobs,
            )
            if run.get("status") == "completed" and run.get("conclusion") == "success":
                continuity_artifacts = cached_artifacts(run_id)
                try:
                    continuity_noop = recovery._prove_continuity_duplicate_no_acquisition_success(
                        run,
                        continuity_artifacts,
                        cached_jobs,
                    )
                except recovery.FreshHoldoutFailureLineageError as exc:
                    raise audit.FreshHoldoutActionsLineageAuditError(
                        "continuity duplicate no-acquisition proof failed for run "
                        f"{run_id}"
                    ) from exc
                if continuity_noop:
                    projected_continuity_noops[run_id] = run
                    projected_continuities.pop(run_id, None)
                    return False
            elif run.get("status") == "completed" and run.get("conclusion") == "failure":
                continuity_artifacts = cached_artifacts(run_id)
                try:
                    continuity_preacquisition = (
                        recovery._prove_continuity_preacquisition_control_failure(
                            run,
                            continuity_artifacts,
                            cached_jobs,
                        )
                    )
                except recovery.FreshHoldoutFailureLineageError as exc:
                    raise audit.FreshHoldoutActionsLineageAuditError(
                        "continuity pre-acquisition failure proof failed for run "
                        f"{run_id}"
                    ) from exc
                if continuity_preacquisition:
                    projected_preacquisition[run_id] = run
                    projected_continuities.pop(run_id, None)
                    return False
            return True
        run_id = run.get("id")
        if run.get("status") != "completed" or type(run_id) is not int or run_id <= 0:
            return True

        artifacts = cached_artifacts(run_id)
        if run.get("conclusion") == "success":
            if recovery._prove_schedule_duplicate_no_acquisition_success(
                run,
                artifacts,
                cached_jobs,
            ):
                projected_schedule_duplicates[run_id] = run
                return False
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
            continue
        if record.get("nominal_slot_utc") != plan.target_slot_text:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "continuity artifact nominal slot differs from authenticated target"
            )
        record["execution_provenance"] = "PROSPECTIVE_CONTINUITY_DISPATCH"
        record["continuity_target_slot"] = plan.target_slot_text
        record["continuity_target_cron"] = plan.target_cron
    if projected_continuities:
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
    ordered_schedule_duplicates = sorted(
        projected_schedule_duplicates.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    if ordered_schedule_duplicates:
        result["verified_schedule_duplicate_no_acquisition_count"] = len(
            ordered_schedule_duplicates
        )
        result["projected_schedule_duplicate_no_acquisition_runs"] = [
            _projected_noop_record(run) for run in ordered_schedule_duplicates
        ]
    ordered_continuity_noops = sorted(
        projected_continuity_noops.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    if ordered_continuity_noops:
        result["verified_continuity_duplicate_no_acquisition_count"] = len(
            ordered_continuity_noops
        )
        result["projected_continuity_duplicate_no_acquisition_runs"] = [
            _projected_continuity_noop_record(run)
            for run in ordered_continuity_noops
        ]
    ordered_legacy_queued = sorted(
        projected_legacy_queued.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    if ordered_legacy_queued:
        result["verified_legacy_queued_no_execution_count"] = len(
            ordered_legacy_queued
        )
        result["projected_legacy_queued_no_execution_runs"] = [
            _projected_legacy_queued_no_execution_record(run)
            for run in ordered_legacy_queued
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
