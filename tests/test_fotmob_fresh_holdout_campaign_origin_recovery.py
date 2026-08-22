from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as lineage


UTC = dt.timezone.utc


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return repo


def _run(
    run_id: int,
    created_at: str,
    *,
    conclusion: str = "failure",
    event: str = "schedule",
    head_branch: str = "main",
) -> dict[str, object]:
    return {
        "id": run_id,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created_at,
        "event": event,
        "head_branch": head_branch,
    }


def _preacquisition_jobs(
    *,
    restore: str = "failure",
    bootstrap: str = "skipped",
    tick: str = "skipped",
    reconcile: str = "skipped",
) -> dict[str, object]:
    conclusions = {
        "Restore newest durable lineage and resolve schedule slot": restore,
        "Restore or materialize PR119 bootstrap projection": bootstrap,
        "Execute reviewed fresh-holdout collection tick": tick,
        "Reconcile any staged capture lineage": reconcile,
    }
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "failure",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                    for name, conclusion in conclusions.items()
                ],
            }
        ]
    }


def _restore(
    tmp_path: Path,
    prior_runs,
    artifacts,
    jobs=_preacquisition_jobs(),
):
    return lineage.restore_latest_lineage_state(
        prior_runs=prior_runs,
        current_run_id=999,
        get_run_artifacts=lambda run_id: artifacts[run_id],
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_run_jobs=lambda _run_id: jobs,
        repository_root=_repo(tmp_path),
    )


def _empty_canonical_artifact(
    *,
    run_id: int,
    nominal: dt.datetime,
) -> tuple[dict[str, object], bytes]:
    asset_name = f"success-{nominal.strftime('%Y%m%dT%H%M%SZ')}-run-{run_id}.tar.gz"
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as archive:
        root = tarfile.TarInfo(control.CONTROL_ROOT_RELATIVE)
        root.type = tarfile.DIRTYPE
        root.mode = 0o700
        archive.addfile(root)
    tar_bytes = tar_buffer.getvalue()
    receipt = {
        "schema_version": 1,
        "workflow_run_id": run_id,
        "nominal_scheduled_for_utc": runner._utc_text(nominal),
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W34",
        "durable_asset_name": asset_name,
        "durable_asset_sha256": hashlib.sha256(tar_bytes).hexdigest(),
        "durable_asset_size_bytes": len(tar_bytes),
    }
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr(asset_name, tar_bytes)
        archive.writestr(
            "fresh-holdout-tick-receipt.json",
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        )
    zip_bytes = zip_buffer.getvalue()
    return (
        {
            "id": 1000 + run_id,
            "name": asset_name,
            "digest": f"sha256:{hashlib.sha256(zip_bytes).hexdigest()}",
            "expired": False,
        },
        zip_bytes,
    )


def test_pre_campaign_completed_run_cannot_poison_campaign_genesis(tmp_path: Path) -> None:
    restored = lineage.restore_latest_lineage_state(
        prior_runs=[_run(1, "2026-08-18T23:55:00Z")],
        current_run_id=999,
        get_run_artifacts=lambda _run_id: (_ for _ in ()).throw(
            AssertionError("pre-campaign artifact must not be queried")
        ),
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_run_jobs=lambda _run_id: (_ for _ in ()).throw(
            AssertionError("pre-campaign jobs must not be queried")
        ),
        repository_root=_repo(tmp_path),
    )
    assert restored.predecessor_run_id is None
    assert restored.skipped_preacquisition_failure_run_ids == ()


def test_zero_artifact_preacquisition_failures_may_establish_origin_only(
    tmp_path: Path,
) -> None:
    prior = [
        _run(12, "2026-08-19T01:48:27Z"),
        _run(11, "2026-08-19T01:18:27Z"),
        _run(10, "2026-08-18T23:55:00Z"),
    ]
    restored = _restore(
        tmp_path,
        prior,
        {12: {"artifacts": []}, 11: {"artifacts": []}},
    )
    assert restored.predecessor_run_id is None
    assert restored.last_committed_utc is None
    assert restored.last_attempted_utc is None
    assert restored.skipped_preacquisition_failure_run_ids == (12, 11)


def test_recovered_origin_records_every_elapsed_slot_as_missing_not_backfilled(
    tmp_path: Path,
) -> None:
    prior = [
        _run(12, "2026-08-19T01:48:27Z"),
        _run(11, "2026-08-19T01:18:27Z"),
        _run(10, "2026-08-18T23:55:00Z"),
    ]
    restored = _restore(
        tmp_path,
        prior,
        {12: {"artifacts": []}, 11: {"artifacts": []}},
    )
    nominal, nominal_text, _tag, _success, _failure = (
        lineage.resolve_nominal_schedule_slot_from_lineage(
            "7 * * * *",
            dt.datetime(2026, 8, 19, 8, 10, tzinfo=UTC),
            restored,
        )
    )
    assert nominal == dt.datetime(2026, 8, 19, 8, 7, tzinfo=UTC)
    assert nominal_text == "2026-08-19T08:07:00.000000Z"

    state = _repo(tmp_path / "gap") / control.CONTROL_ROOT_RELATIVE
    state.mkdir(parents=True, exist_ok=True)
    control_path = state / control.CONTROL_JOURNAL_FILENAME
    runner._gap((), nominal, control_path)
    rows = runner._rows(control_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "SCHEDULER_GAP_RANGE"
    assert row["first_missing_tick_utc"] == "2026-08-19T00:07:00.000000Z"
    assert row["last_missing_tick_utc"] == "2026-08-19T07:37:00.000000Z"
    assert row["missing_tick_count"] == 16
    assert row["backfill_authorized"] is False


def test_failure_that_entered_collection_tick_remains_hard_stop(tmp_path: Path) -> None:
    with pytest.raises(
        lineage.FreshHoldoutFailureLineageError,
        match="must have exactly one canonical state artifact, found 0",
    ):
        _restore(
            tmp_path,
            [_run(12, "2026-08-19T01:48:27Z")],
            {12: {"artifacts": []}},
            _preacquisition_jobs(tick="failure"),
        )


def test_zero_artifact_success_cannot_be_reclassified_as_preacquisition_failure(
    tmp_path: Path,
) -> None:
    with pytest.raises(lineage.FreshHoldoutFailureLineageError):
        _restore(
            tmp_path,
            [_run(12, "2026-08-19T01:48:27Z", conclusion="success")],
            {12: {"artifacts": []}},
        )


def test_any_unexpected_artifact_blocks_preacquisition_skip(tmp_path: Path) -> None:
    with pytest.raises(lineage.FreshHoldoutFailureLineageError):
        _restore(
            tmp_path,
            [_run(12, "2026-08-19T01:48:27Z")],
            {12: {"artifacts": [{"id": 1, "name": "unexpected.zip"}]}},
        )


def test_proven_preacquisition_failures_restore_nearest_older_canonical_artifact(
    tmp_path: Path,
) -> None:
    nominal = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)
    artifact, zip_bytes = _empty_canonical_artifact(run_id=11, nominal=nominal)
    prior = [
        _run(13, "2026-08-19T01:08:27Z"),
        _run(12, "2026-08-19T00:38:27Z"),
        _run(11, "2026-08-19T00:08:27Z", conclusion="success"),
        _run(10, "2026-08-18T23:55:00Z"),
    ]
    artifacts = {
        13: {"artifacts": []},
        12: {"artifacts": []},
        11: {"artifacts": [artifact]},
    }
    restored = lineage.restore_latest_lineage_state(
        prior_runs=prior,
        current_run_id=999,
        get_run_artifacts=lambda run_id: artifacts[run_id],
        download_artifact_zip=lambda artifact_id: (
            zip_bytes
            if artifact_id == artifact["id"]
            else (_ for _ in ()).throw(AssertionError("unexpected artifact id"))
        ),
        get_run_jobs=lambda _run_id: _preacquisition_jobs(),
        repository_root=_repo(tmp_path),
    )
    assert restored.predecessor_run_id == 11
    assert restored.predecessor_conclusion == "success"
    assert restored.predecessor_asset_name == artifact["name"]
    assert restored.last_attempted_utc == nominal
    assert restored.skipped_preacquisition_failure_run_ids == (13, 12)

    current, current_text, _tag, _success, _failure = (
        lineage.resolve_nominal_schedule_slot_from_lineage(
            "7 * * * *",
            dt.datetime(2026, 8, 19, 8, 10, tzinfo=UTC),
            restored,
        )
    )
    assert current == dt.datetime(2026, 8, 19, 8, 7, tzinfo=UTC)
    assert current_text == "2026-08-19T08:07:00.000000Z"


def test_job_proof_is_exact_not_name_contains_or_duplicate(tmp_path: Path) -> None:
    jobs = _preacquisition_jobs()
    jobs["jobs"][0]["steps"].append(
        {
            "name": "Execute reviewed fresh-holdout collection tick",
            "status": "completed",
            "conclusion": "skipped",
        }
    )
    with pytest.raises(
        lineage.FreshHoldoutFailureLineageError,
        match="duplicated job step",
    ):
        _restore(
            tmp_path,
            [_run(12, "2026-08-19T01:48:27Z")],
            {12: {"artifacts": []}},
            jobs,
        )
