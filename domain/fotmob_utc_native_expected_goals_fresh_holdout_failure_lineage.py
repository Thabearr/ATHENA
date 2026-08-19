"""Durable carry-forward for uncommitted fresh-holdout capture evidence.

This module does not authorize acquisition, prediction, settlement, pricing, or BET.
It only reconciles exact raw captures already staged by the reviewed activation
runner and restores the newest completed workflow artifact (success or failure)
so a failed nominal tick cannot erase a real prospective source observation.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from typing import Any
import zipfile

import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control


_ARTIFACT_NAME = re.compile(
    r"^(success|failure)-(\d{8}T\d{6}Z)-run-(\d+)\.tar\.gz$"
)
_PREACQUISITION_JOB_NAME = "execute fresh holdout tick"
_PREACQUISITION_REQUIRED_STEPS = {
    "Restore newest durable lineage and resolve schedule slot": "failure",
    "Restore or materialize PR119 bootstrap projection": "skipped",
    "Execute reviewed fresh-holdout collection tick": "skipped",
    "Reconcile any staged capture lineage": "skipped",
}


class FreshHoldoutFailureLineageError(RuntimeError):
    """Raised when failed-tick evidence lineage cannot be proven exactly."""


def _error(message: str) -> FreshHoldoutFailureLineageError:
    return FreshHoldoutFailureLineageError(message)


def _utc_text(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


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


def _sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value.lower())
    ):
        raise _error(f"{label} must be a 64-character hexadecimal SHA-256")
    return value.lower()


@dataclasses.dataclass(frozen=True)
class RestoredFailureLineage:
    predecessor_run_id: int | None
    predecessor_conclusion: str | None
    predecessor_asset_name: str | None
    last_committed_utc: dt.datetime | None
    last_attempted_utc: dt.datetime | None
    skipped_preacquisition_failure_run_ids: tuple[int, ...] = ()


def _paths(root: Path) -> dict[str, Path]:
    return {
        "capture": root / control.CAPTURE_INDEX_FILENAME,
        "prediction": root / control.PREDICTION_JOURNAL_FILENAME,
        "identity": root / control.POST_SEAL_IDENTITY_JOURNAL_FILENAME,
        "settlement": root / control.SETTLEMENT_JOURNAL_FILENAME,
        "control": root / control.CONTROL_JOURNAL_FILENAME,
        "checkpoint": root / control.CHECKPOINT_FILENAME,
    }


def reconcile_staged_capture_lineage(
    *,
    durable_release_tag: str,
    durable_asset_name: str,
    state_root: Path = Path(control.CONTROL_ROOT_RELATIVE),
    repository_root: Path | None = None,
) -> dict[str, int]:
    """Journal every already-staged raw capture without committing the failed tick.

    Raw lineage is appended before qualification. Qualified observations are then
    replayed through the activation runner's exact post-seal identity rule. The
    operation is idempotent and never writes ``TICK_COMMITTED``.
    """
    runner.verify_reviewed_activation_dependencies()
    repo = (repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    root = runner.validate_state_root(state_root, repository_root=repo)
    paths = _paths(root)

    if type(durable_release_tag) is not str or not durable_release_tag.startswith(
        "athena-fresh-holdout-evidence-"
    ):
        raise _error("durable release tag is invalid")
    if type(durable_asset_name) is not str or _ARTIFACT_NAME.fullmatch(
        durable_asset_name
    ) is None:
        raise _error("durable asset name is invalid")

    capture_rows = runner._rows(paths["capture"])
    prediction_rows = runner._rows(paths["prediction"])
    identity_rows = runner._rows(paths["identity"])
    control_rows = runner._rows(paths["control"])

    capture_keys = {
        runner._sha(row.get("manifest_sha256"), "capture manifest")
        for row in capture_rows
    }
    sealed, _processed = runner._prediction_state(prediction_rows)
    _identity_map, identity_keys = runner._identity_state(identity_rows)
    qualification_failure_keys = {
        row.get("capture_manifest_sha256")
        for row in control_rows
        if row.get("event") == "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED"
    }

    captures_added = 0
    identity_rows_added = 0
    qualification_failures_added = 0
    working_root = root / runner.WORKING_CAPTURE_DIRECTORY

    for evidence in runner._working(working_root):
        manifest_sha = runner._manifest_sha(evidence)
        if manifest_sha not in capture_keys:
            try:
                relative = evidence.capture_directory.relative_to(root).as_posix()
            except ValueError as exc:
                raise _error("staged capture escaped reviewed state root") from exc
            runner._append(
                paths["capture"],
                {
                    "schema_version": 1,
                    "request_date": evidence.manifest.request_date,
                    "timezone": evidence.manifest.timezone,
                    "ccode3": evidence.manifest.ccode3,
                    "observed_at": _utc_text(evidence.manifest.observed_at),
                    "raw_sha256": evidence.manifest.raw_sha256,
                    "raw_size": evidence.manifest.raw_size,
                    "manifest_sha256": manifest_sha,
                    "working_capture_relative": relative,
                    "durable_release_tag": durable_release_tag,
                    "durable_asset_name": durable_asset_name,
                    "network_acquisition_performed": True,
                    "preserved_from_uncommitted_tick": True,
                },
            )
            capture_keys.add(manifest_sha)
            captures_added += 1

        try:
            observations = runner._qualify(evidence)
        except Exception as exc:
            if manifest_sha not in qualification_failure_keys:
                runner._append(
                    paths["control"],
                    {
                        "schema_version": 1,
                        "event": "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
                        "capture_manifest_sha256": manifest_sha,
                        "capture_raw_sha256": evidence.manifest.raw_sha256,
                        "observed_at": _utc_text(evidence.manifest.observed_at),
                        "detail": f"{type(exc).__name__}: {str(exc)[:240]}",
                        "tick_committed": False,
                        "backfill_authorized": False,
                    },
                )
                qualification_failure_keys.add(manifest_sha)
                qualification_failures_added += 1
            continue

        before = len(identity_keys)
        runner._post_seal(
            sealed,
            observations,
            paths["identity"],
            identity_keys,
        )
        identity_rows_added += len(identity_keys) - before

    return {
        "captures_added": captures_added,
        "identity_rows_added": identity_rows_added,
        "qualification_failures_added": qualification_failures_added,
    }


def _run_created_at(value: Mapping[str, Any], run_id: int) -> dt.datetime | None:
    created_at = value.get("created_at")
    if created_at is None:
        return None
    return _parse_utc(created_at, f"workflow run {run_id} created_at")


def _completed_prior_runs(
    prior_runs: Sequence[Mapping[str, Any]], current_run_id: int
) -> tuple[list[Mapping[str, Any]], bool]:
    out: list[Mapping[str, Any]] = []
    saw_pre_campaign_completed = False
    start = control.holdout_start_utc()
    for value in prior_runs:
        if type(value) is not dict:
            raise _error("workflow run metadata must be objects")
        run_id = value.get("id")
        if type(run_id) is not int:
            raise _error("workflow run id must be an integer")
        if run_id == current_run_id:
            continue
        if value.get("status") != "completed":
            continue
        conclusion = value.get("conclusion")
        if type(conclusion) is not str or not conclusion:
            raise _error(f"completed workflow run {run_id} has invalid conclusion")
        created_at = _run_created_at(value, run_id)
        if created_at is not None and created_at < start:
            saw_pre_campaign_completed = True
            continue
        out.append(value)
    out.sort(key=lambda row: int(row["id"]), reverse=True)
    return out, saw_pre_campaign_completed


def _github_run_jobs(run_id: int) -> Mapping[str, Any]:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if type(repo) is not str or repo.count("/") != 1 or not all(repo.split("/")):
        raise _error("GITHUB_REPOSITORY is unavailable for pre-acquisition proof")
    if not os.environ.get("GH_TOKEN"):
        raise _error("GH_TOKEN is unavailable for pre-acquisition proof")
    try:
        output = subprocess.check_output(
            [
                "gh",
                "api",
                f"/repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100",
            ],
            text=True,
        )
        value = json.loads(output)
    except Exception as exc:
        raise _error(f"failed to query jobs for completed run {run_id}") from exc
    if type(value) is not dict:
        raise _error(f"malformed jobs response for completed run {run_id}")
    return value


def _prove_preacquisition_control_failure(
    run: Mapping[str, Any],
    artifact_data: Mapping[str, Any],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
) -> bool:
    run_id = int(run["id"])
    if run.get("conclusion") != "failure":
        return False
    created_at = _run_created_at(run, run_id)
    if created_at is None or created_at < control.holdout_start_utc():
        return False
    if run.get("event") != "schedule" or run.get("head_branch") != "main":
        return False
    artifacts = artifact_data.get("artifacts")
    if type(artifacts) is not list or artifacts:
        return False

    try:
        jobs_data = get_run_jobs(run_id)
    except FreshHoldoutFailureLineageError:
        raise
    except Exception as exc:
        raise _error(f"failed to fetch jobs for completed run {run_id}") from exc
    if type(jobs_data) is not dict or type(jobs_data.get("jobs")) is not list:
        raise _error(f"malformed jobs metadata for completed run {run_id}")
    jobs = [
        job
        for job in jobs_data["jobs"]
        if type(job) is dict and job.get("name") == _PREACQUISITION_JOB_NAME
    ]
    if len(jobs) != 1:
        raise _error(
            f"completed run {run_id} must expose exactly one reviewed collection job"
        )
    job = jobs[0]
    if job.get("status") != "completed" or job.get("conclusion") != "failure":
        raise _error(f"completed run {run_id} collection job state is not exact failure")
    steps = job.get("steps")
    if type(steps) is not list:
        raise _error(f"completed run {run_id} job steps are missing")
    by_name: dict[str, Mapping[str, Any]] = {}
    for step in steps:
        if type(step) is not dict:
            raise _error(f"completed run {run_id} job step metadata is malformed")
        name = step.get("name")
        if type(name) is not str:
            raise _error(f"completed run {run_id} job step name is invalid")
        if name in by_name:
            raise _error(f"completed run {run_id} duplicated job step {name!r}")
        by_name[name] = step
    for name, expected_conclusion in _PREACQUISITION_REQUIRED_STEPS.items():
        step = by_name.get(name)
        if step is None:
            raise _error(f"completed run {run_id} is missing reviewed job step {name!r}")
        if step.get("status") != "completed" or step.get("conclusion") != expected_conclusion:
            return False
    return True


def _artifact_digest(metadata: Mapping[str, Any], run_id: int) -> str:
    value = metadata.get("digest")
    if type(value) is not str or not value.startswith("sha256:"):
        raise _error(f"newest predecessor run {run_id} artifact lacks SHA-256 digest")
    digest = value.removeprefix("sha256:")
    return _sha256(digest, "artifact zip digest")


def _last_committed_from_state(root: Path) -> dt.datetime | None:
    paths = _paths(root)
    rows = runner._rows(paths["control"])
    committed = [
        _parse_utc(row.get("scheduled_for_utc"), "committed scheduled_for")
        for row in rows
        if row.get("event") == "TICK_COMMITTED"
    ]
    last = max(committed) if committed else None

    if paths["checkpoint"].exists():
        try:
            checkpoint = json.loads(paths["checkpoint"].read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("checkpoint JSON is malformed") from exc
        if type(checkpoint) is not dict or checkpoint.get("schema_version") != 1:
            raise _error("checkpoint schema is invalid")
        checkpoint_last = _parse_utc(
            checkpoint.get("last_committed_scheduled_for_utc"),
            "checkpoint last committed",
        )
        if last is None or checkpoint_last != last:
            raise _error("checkpoint disagrees with append-only committed control lineage")
    elif last is not None:
        raise _error("committed control lineage exists without checkpoint")

    return last


def restore_latest_lineage_state(
    *,
    prior_runs: Sequence[Mapping[str, Any]],
    current_run_id: int,
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    get_run_jobs: Callable[[int], Mapping[str, Any]] | None = None,
    repository_root: Path | None = None,
) -> RestoredFailureLineage:
    """Restore the newest completed scheduled run, including a failed tick.

    A canonical failure artifact is never skipped: it may contain real staged source
    observations. The only exception is campaign-origin recovery when every completed
    in-campaign run has zero artifacts and GitHub job metadata proves its reviewed
    acquisition and reconciliation steps were never entered. That recovery may only
    establish Genesis; it may not fall back across such a failure to an older campaign
    artifact.
    """
    runner.verify_reviewed_activation_dependencies()
    if type(current_run_id) is not int or current_run_id < 1:
        raise _error("current run id must be a positive integer")
    repo = (repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    root = runner.validate_state_root(
        Path(control.CONTROL_ROOT_RELATIVE), repository_root=repo
    )

    completed, saw_pre_campaign_completed = _completed_prior_runs(
        prior_runs, current_run_id
    )
    if not completed:
        return RestoredFailureLineage(None, None, None, None, None)

    jobs_reader = get_run_jobs or _github_run_jobs
    skipped_preacquisition: list[int] = []
    newest: Mapping[str, Any] | None = None
    canonical: list[Mapping[str, Any]] = []
    artifact_data: Mapping[str, Any] | None = None

    for candidate in completed:
        run_id = int(candidate["id"])
        conclusion = str(candidate["conclusion"])
        try:
            candidate_artifacts = get_run_artifacts(run_id)
        except Exception as exc:
            raise _error(f"failed to fetch artifacts for newest completed run {run_id}") from exc
        if (
            type(candidate_artifacts) is not dict
            or type(candidate_artifacts.get("artifacts")) is not list
        ):
            raise _error(f"malformed artifact metadata for newest completed run {run_id}")

        candidate_canonical: list[Mapping[str, Any]] = []
        for artifact in candidate_artifacts["artifacts"]:
            if type(artifact) is not dict or artifact.get("expired", False):
                continue
            name = artifact.get("name")
            if type(name) is str and _ARTIFACT_NAME.fullmatch(name):
                candidate_canonical.append(artifact)

        if len(candidate_canonical) == 1:
            if skipped_preacquisition:
                raise _error(
                    "campaign-origin pre-acquisition recovery cannot fall back across "
                    f"runs {skipped_preacquisition} to older canonical run {run_id}"
                )
            newest = candidate
            canonical = candidate_canonical
            artifact_data = candidate_artifacts
            break

        if len(candidate_canonical) == 0 and _prove_preacquisition_control_failure(
            candidate,
            candidate_artifacts,
            jobs_reader,
        ):
            skipped_preacquisition.append(run_id)
            continue

        raise _error(
            f"newest completed run {run_id} must have exactly one canonical state "
            f"artifact, found {len(candidate_canonical)}"
        )

    if newest is None:
        if not skipped_preacquisition:
            raise _error("completed campaign lineage resolved no predecessor")
        if len(prior_runs) >= 100 and not saw_pre_campaign_completed:
            raise _error(
                "campaign-origin recovery cannot prove Genesis because the 100-run "
                "workflow query window did not reach a pre-campaign completed run"
            )
        print(
            "Campaign-origin recovery proved pre-acquisition control failures with "
            "zero artifacts; no source observation is being reconstructed or "
            f"backfilled. skipped_run_ids={','.join(map(str, skipped_preacquisition))}"
        )
        return RestoredFailureLineage(
            None,
            None,
            None,
            None,
            None,
            tuple(skipped_preacquisition),
        )

    run_id = int(newest["id"])
    conclusion = str(newest["conclusion"])
    assert artifact_data is not None and len(canonical) == 1

    artifact = canonical[0]
    artifact_name = str(artifact["name"])
    match = _ARTIFACT_NAME.fullmatch(artifact_name)
    assert match is not None
    artifact_run_id = int(match.group(3))
    if artifact_run_id != run_id:
        raise _error("canonical artifact run id does not match predecessor run")
    artifact_id = artifact.get("id")
    if type(artifact_id) is not int:
        raise _error("canonical artifact id is invalid")
    expected_zip_sha = _artifact_digest(artifact, run_id)

    try:
        zip_bytes = download_artifact_zip(artifact_id)
    except Exception as exc:
        raise _error(f"failed to download artifact for newest completed run {run_id}") from exc
    if type(zip_bytes) is not bytes or not zip_bytes:
        raise _error("downloaded artifact zip must be non-empty exact bytes")
    actual_zip_sha = hashlib.sha256(zip_bytes).hexdigest()
    if actual_zip_sha != expected_zip_sha:
        raise _error(
            f"artifact zip digest mismatch for run {run_id}: expected {expected_zip_sha}, got {actual_zip_sha}"
        )

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise _error("artifact zip contains duplicate members")
            tar_names = [name for name in names if _ARTIFACT_NAME.fullmatch(name)]
            if tar_names != [artifact_name]:
                raise _error("artifact zip must contain exactly the canonical named state tar")
            if names.count("fresh-holdout-tick-receipt.json") != 1:
                raise _error("artifact zip must contain exactly one lineage receipt")
            tar_bytes = archive.read(artifact_name)
            receipt_raw = archive.read("fresh-holdout-tick-receipt.json")
    except FreshHoldoutFailureLineageError:
        raise
    except Exception as exc:
        raise _error("newest predecessor artifact zip is malformed") from exc

    try:
        receipt = json.loads(receipt_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("lineage receipt JSON is malformed") from exc
    if type(receipt) is not dict:
        raise _error("lineage receipt must be an object")
    if receipt.get("durable_asset_name") != artifact_name:
        raise _error("lineage receipt durable asset identity changed")
    expected_tar_sha = _sha256(
        receipt.get("durable_asset_sha256"), "state tar digest"
    )
    expected_tar_size = receipt.get("durable_asset_size_bytes")
    if type(expected_tar_size) is not int or expected_tar_size < 1:
        raise _error("lineage receipt state tar size is invalid")
    if len(tar_bytes) != expected_tar_size:
        raise _error("state tar size does not match lineage receipt")
    actual_tar_sha = hashlib.sha256(tar_bytes).hexdigest()
    if actual_tar_sha != expected_tar_sha:
        raise _error("state tar digest does not match lineage receipt")

    nominal_text = receipt.get("nominal_scheduled_for_utc")
    last_attempted = _parse_utc(nominal_text, "lineage nominal scheduled_for")
    compact = last_attempted.strftime("%Y%m%dT%H%M%SZ")
    if match.group(2) != compact:
        raise _error("state artifact nominal slot disagrees with lineage receipt")
    if receipt.get("workflow_run_id") != run_id:
        raise _error("lineage receipt workflow run id changed")

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as handle:
        handle.write(tar_bytes)
        temporary = Path(handle.name)
    try:
        runner.verify_and_extract_durable_state_archive(
            temporary,
            repository_root=repo,
            expected_sha256=expected_tar_sha,
        )
    finally:
        temporary.unlink(missing_ok=True)

    # Repair any staged raw capture that the failed process acquired before it
    # exited. This is deliberately evidence-only; no nominal tick is committed.
    release_tag = receipt.get("durable_release_tag")
    if type(release_tag) is not str:
        raise _error("lineage receipt durable release tag is missing")
    reconcile_staged_capture_lineage(
        durable_release_tag=release_tag,
        durable_asset_name=artifact_name,
        repository_root=repo,
    )

    last_committed = _last_committed_from_state(root)
    if last_committed is not None and last_committed > last_attempted:
        raise _error("restored committed lineage is later than predecessor attempt")

    return RestoredFailureLineage(
        predecessor_run_id=run_id,
        predecessor_conclusion=conclusion,
        predecessor_asset_name=artifact_name,
        last_committed_utc=last_committed,
        last_attempted_utc=last_attempted,
    )


def resolve_nominal_schedule_slot_from_lineage(
    schedule_expr: str,
    created_at: dt.datetime,
    lineage: RestoredFailureLineage,
) -> tuple[dt.datetime, str, str, str, str]:
    """Resolve the next cron occurrence from the newest proven attempt lineage."""
    if type(lineage) is not RestoredFailureLineage:
        raise _error("lineage must be RestoredFailureLineage")
    anchor = lineage.last_attempted_utc
    if anchor is None:
        anchor = lineage.last_committed_utc
    return runner.resolve_nominal_schedule_slot(
        schedule_expr,
        created_at,
        last_committed_utc=anchor,
    )


__all__ = [
    "FreshHoldoutFailureLineageError",
    "RestoredFailureLineage",
    "reconcile_staged_capture_lineage",
    "resolve_nominal_schedule_slot_from_lineage",
    "restore_latest_lineage_state",
]
