from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from domain import fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery


UTC = dt.timezone.utc


def _restored(slot: dt.datetime):
    return recovery.RestoredFailureLineage(
        predecessor_run_id=123,
        predecessor_conclusion="success",
        predecessor_asset_name="success-20260904T193700Z-run-123.tar.gz",
        last_committed_utc=slot,
        last_attempted_utc=slot,
        skipped_preacquisition_failure_run_ids=(),
    )


def test_delayed_natural_schedule_may_resolve_exact_already_committed_slot_for_noop() -> None:
    slot = dt.datetime(2026, 9, 4, 19, 37, tzinfo=UTC)
    created = dt.datetime(2026, 9, 4, 19, 49, 32, tzinfo=UTC)
    nominal, nominal_text, _tag, _success, _failure = (
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "37 * * * *",
            created,
            _restored(slot),
        )
    )
    assert nominal == slot
    assert nominal_text == "2026-09-04T19:37:00.000000Z"


def test_delayed_duplicate_projection_does_not_relax_backward_lineage() -> None:
    committed = dt.datetime(2026, 9, 4, 20, 7, tzinfo=UTC)
    created = dt.datetime(2026, 9, 4, 19, 49, 32, tzinfo=UTC)
    with pytest.raises(Exception, match="not after last committed slot"):
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "37 * * * *",
            created,
            _restored(committed),
        )


def _duplicate_jobs(*, execute_outcome: str = "skipped") -> dict[str, object]:
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "success",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": (
                            execute_outcome
                            if name == "Execute reviewed fresh-holdout collection tick"
                            else outcome
                        ),
                    }
                    for name, outcome in (
                        recovery._SCHEDULE_DUPLICATE_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES.items()
                    )
                ],
            }
        ]
    }


def _duplicate_run(run_id: int = 460) -> dict[str, object]:
    return {
        "id": run_id,
        "status": "completed",
        "conclusion": "success",
        "event": "schedule",
        "head_branch": "main",
        "created_at": "2026-09-04T19:49:32Z",
    }


def test_live_run_460_shape_is_a_proven_zero_artifact_duplicate() -> None:
    run = _duplicate_run(33913131575)
    assert recovery._prove_schedule_duplicate_no_acquisition_success(
        run,
        {"artifacts": []},
        lambda requested: _duplicate_jobs() if requested == run["id"] else {},
    ) is True


def test_duplicate_proof_rejects_any_acquisition_or_persistence_shape() -> None:
    run = _duplicate_run()
    assert recovery._prove_schedule_duplicate_no_acquisition_success(
        run,
        {"artifacts": [{"name": "unexpected"}]},
        lambda _requested: _duplicate_jobs(),
    ) is False
    assert recovery._prove_schedule_duplicate_no_acquisition_success(
        run,
        {"artifacts": []},
        lambda _requested: _duplicate_jobs(execute_outcome="success"),
    ) is False


def test_restore_steps_across_proven_schedule_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_restore(**kwargs):
        captured["prior_runs"] = kwargs["prior_runs"]
        return recovery.lineage.RestoredFailureLineage(
            predecessor_run_id=123,
            predecessor_conclusion="success",
            predecessor_asset_name="success-20260904T193700Z-run-123.tar.gz",
            last_committed_utc=dt.datetime(2026, 9, 4, 19, 37, tzinfo=UTC),
            last_attempted_utc=dt.datetime(2026, 9, 4, 19, 37, tzinfo=UTC),
        )

    monkeypatch.setattr(recovery.lineage, "restore_latest_lineage_state", fake_restore)
    run = _duplicate_run()
    result = recovery.restore_latest_lineage_state(
        prior_runs=[run],
        current_run_id=999,
        get_run_artifacts=lambda requested: {"artifacts": []} if requested == run["id"] else {},
        download_artifact_zip=lambda _artifact: b"unused",
        get_run_jobs=lambda requested: _duplicate_jobs() if requested == run["id"] else {},
    )
    assert captured["prior_runs"] == []
    assert result.skipped_preacquisition_failure_run_ids == (460,)


def test_skipped_noop_lineage_does_not_expand_exact_duplicate_compatibility() -> None:
    slot = dt.datetime(2026, 9, 4, 19, 37, tzinfo=UTC)
    restored = recovery.RestoredFailureLineage(
        predecessor_run_id=123,
        predecessor_conclusion="success",
        predecessor_asset_name="success-20260904T193700Z-run-123.tar.gz",
        last_committed_utc=slot,
        last_attempted_utc=slot,
        skipped_preacquisition_failure_run_ids=(460,),
    )
    # This retains the existing lineage policy; the new equality path does not
    # override the special skipped-preacquisition resolver semantics.
    nominal, *_rest = recovery.resolve_nominal_schedule_slot_from_lineage(
        "37 * * * *",
        dt.datetime(2026, 9, 4, 19, 49, 32, tzinfo=UTC),
        restored,
    )
    assert nominal == slot


def test_collection_workflow_passes_exact_jobs_reader_for_future_duplicate_recovery() -> None:
    workflow = Path(
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    ).read_text(encoding="utf-8")
    assert "def get_run_jobs(run_id: int):" in workflow
    assert "get_run_jobs=get_run_jobs" in workflow
    assert "SCHEDULE_ALREADY_ATTEMPTED_NO_ACQUISITION" in workflow
