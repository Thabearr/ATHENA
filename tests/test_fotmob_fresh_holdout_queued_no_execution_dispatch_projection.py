from __future__ import annotations

import pytest

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection

# This regression contract must execute; skipping it would mask the continuity blocker.


def _bot() -> dict[str, object]:
    return {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"}


def _queued_run() -> dict[str, object]:
    return {
        "id": 33931981258,
        "name": projection.continuity.PRIMARY_WORKFLOW_NAME,
        "display_title": projection.continuity.PRIMARY_WORKFLOW_NAME,
        "workflow_id": projection.continuity.PRIMARY_WORKFLOW_ID,
        "path": projection.continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": "87991228755f49f0c6c87c0e8d241c02c1b29b9d",
        "status": "queued",
        "conclusion": None,
        "run_number": 462,
        "run_attempt": 1,
        "created_at": "2026-09-05T00:08:33Z",
        "updated_at": "2026-09-05T00:08:33Z",
        "run_started_at": "2026-09-05T00:08:33Z",
        "actor": _bot(),
        "triggering_actor": _bot(),
    }


def _empty_artifacts(_run_id: int) -> dict[str, object]:
    return {"total_count": 0, "artifacts": []}


def _empty_jobs(_run_id: int) -> dict[str, object]:
    return {"total_count": 0, "jobs": []}


def test_generic_title_queued_dispatch_is_transparent_only_with_zero_execution() -> None:
    assert projection._prove_queued_no_execution_dispatch(
        _queued_run(),
        get_run_artifacts=_empty_artifacts,
        get_run_jobs=_empty_jobs,
    ) is True


def test_generic_title_queued_dispatch_rejects_manual_actor() -> None:
    changed = {**_queued_run(), "actor": {"login": "Thabearr", "type": "User"}}
    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="queued no-execution dispatch actor drifted",
    ):
        projection._prove_queued_no_execution_dispatch(
            changed,
            get_run_artifacts=_empty_artifacts,
            get_run_jobs=_empty_jobs,
        )


def test_generic_title_queued_dispatch_rejects_execution_state_or_evidence() -> None:
    for changed in (
        {**_queued_run(), "status": "in_progress"},
        {**_queued_run(), "conclusion": "success"},
        {**_queued_run(), "run_attempt": 2},
    ):
        with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
            projection._prove_queued_no_execution_dispatch(
                changed,
                get_run_artifacts=_empty_artifacts,
                get_run_jobs=_empty_jobs,
            )

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unexpectedly acquired execution jobs",
    ):
        projection._prove_queued_no_execution_dispatch(
            _queued_run(),
            get_run_artifacts=_empty_artifacts,
            get_run_jobs=lambda _run_id: {"total_count": 1, "jobs": [{"id": 1}]},
        )

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unexpectedly acquired artifact evidence",
    ):
        projection._prove_queued_no_execution_dispatch(
            _queued_run(),
            get_run_artifacts=lambda _run_id: {
                "total_count": 1,
                "artifacts": [{"id": 1}],
            },
            get_run_jobs=_empty_jobs,
        )


def test_non_generic_dispatch_does_not_consume_no_execution_readers() -> None:
    other = {
        **_queued_run(),
        "display_title": (
            "ATHENA fresh-holdout workflow_dispatch source=33931272025 "
            "target=2026-09-05T00:07:00Z cron=7 * * * * "
            "confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
        ),
        "name": (
            "ATHENA fresh-holdout workflow_dispatch source=33931272025 "
            "target=2026-09-05T00:07:00Z cron=7 * * * * "
            "confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
        ),
    }
    touched = False

    def forbidden(_run_id: int):
        nonlocal touched
        touched = True
        raise AssertionError("grammar-valid dispatch must use continuity provenance replay")

    assert projection._prove_queued_no_execution_dispatch(
        other,
        get_run_artifacts=forbidden,
        get_run_jobs=forbidden,
    ) is False
    assert touched is False


def test_projection_removes_proven_queued_transport_before_continuity_grammar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _queued_run()
    monkeypatch.setattr(
        projection,
        "_ORIGINAL_RUN_IS_COLLECTION_CANDIDATE",
        lambda _run: False,
    )

    def fake_audit(**_kwargs):
        assert audit._run_is_collection_candidate(run) is False
        return {
            "runs": [],
            "audit_state": "VERIFIED_COMPLETE_ACTIONS_LINEAGE",
            "verified_preacquisition_control_failure_count": 0,
        }

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_audit)

    def forbidden_run_reader(_run_id: int):
        raise AssertionError("proven queued run must not enter continuity provenance replay")

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        get_run_by_id=forbidden_run_reader,
        get_run_artifacts=_empty_artifacts,
        get_run_jobs=_empty_jobs,
        verify_dependencies=False,
    )

    assert result["verified_queued_no_execution_dispatch_count"] == 1
    [record] = result["projected_queued_no_execution_dispatch_runs"]
    assert record["run_id"] == 33931981258
    assert record["evidence_state"] == "VERIFIED_QUEUED_NO_EXECUTION_TRANSPORT"
    assert record["execution_provenance"] == (
        "PROSPECTIVE_CONTINUITY_DISPATCH_PENDING_NO_EXECUTION"
    )
    assert record["tick_committed"] is False
    assert record["release_state"] == "NOT_APPLICABLE_NO_ACQUISITION"


@pytest.mark.parametrize("field,value", [
    ("triggering_actor", {"login": "Thabearr", "type": "User"}),
    ("actor", {"login": "github-actions[bot]", "type": "User"}),
    ("actor", None),
    ("workflow_id", 1),
    ("path", projection.continuity.PRIMARY_WORKFLOW_PATH + "@" + "a" * 40),
    ("head_branch", "feature"),
    ("event", "push"),
    ("status", "completed"),
    ("run_attempt", True),
    ("run_attempt", 1.0),
    ("id", True),
    ("id", 0),
    ("id", "33931981258"),
    ("head_sha", "A" * 40),
    ("head_sha", "g" * 40),
    ("head_sha", "a" * 39),
    ("head_sha", "a" * 40 + "\n"),
    ("head_sha", None),
])
def test_generic_metadata_drift_fails_closed(field, value):
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._prove_queued_no_execution_dispatch(
            {**_queued_run(), field: value},
            get_run_jobs=_empty_jobs, get_run_artifacts=_empty_artifacts,
        )


@pytest.mark.parametrize("field", [
    "workflow_id", "path", "event", "head_branch", "status", "conclusion",
    "run_attempt", "id", "head_sha", "actor", "triggering_actor",
])
def test_missing_required_metadata_fails_closed(field):
    run = _queued_run()
    del run[field]
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._prove_queued_no_execution_dispatch(
            run, get_run_jobs=_empty_jobs, get_run_artifacts=_empty_artifacts,
        )


@pytest.mark.parametrize("field", ["name", "display_title"])
def test_either_non_generic_title_returns_without_reading(field):
    def forbidden(_run_id):
        pytest.fail("non-generic title consumed an execution reader")

    assert projection._prove_queued_no_execution_dispatch(
        {**_queued_run(), field: "another title"},
        get_run_jobs=forbidden, get_run_artifacts=forbidden,
    ) is False


@pytest.mark.parametrize("field", ["jobs", "artifacts"])
def test_missing_execution_list_fails_closed(field):
    readers = {"get_run_jobs": _empty_jobs, "get_run_artifacts": _empty_artifacts}
    readers["get_run_" + field] = lambda _: {"total_count": 0}
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._prove_queued_no_execution_dispatch(_queued_run(), **readers)


@pytest.mark.parametrize("field", ["jobs", "artifacts"])
@pytest.mark.parametrize("payload", [
    None, [], {},
    {"total_count": False}, {"total_count": 0.0},
    {"total_count": "0"}, {"total_count": 1},
    {"total_count": 0, "items": [{}]},
    {"total_count": 0, "items": ()},
    {"total_count": 0, "items": None},
])
def test_malformed_execution_payload_fails_closed(field, payload):
    if isinstance(payload, dict):
        payload = dict(payload)
        payload[field] = payload.pop("items", [])
    readers = {"get_run_jobs": _empty_jobs, "get_run_artifacts": _empty_artifacts}
    readers["get_run_" + field] = lambda _run_id: payload
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._prove_queued_no_execution_dispatch(_queued_run(), **readers)


@pytest.mark.parametrize("drift", ["status", "jobs", "artifacts"])
def test_previously_proven_transport_is_rechecked(monkeypatch, drift):
    run = _queued_run()
    jobs = _empty_jobs(run["id"])
    artifacts = _empty_artifacts(run["id"])

    def fake_audit(**_kwargs):
        assert audit._run_is_collection_candidate(run) is False
        if drift == "status":
            run.update(status="completed", conclusion="success")
        elif drift == "jobs":
            jobs.update(total_count=1, jobs=[{"id": 1}])
        else:
            artifacts.update(total_count=1, artifacts=[{"id": 1}])
        audit._run_is_collection_candidate(run)
        pytest.fail("execution transition was silently projected")

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_audit)
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._audit_actions_lineage_compatible(
            get_run_jobs=lambda _: dict(jobs),
            get_run_artifacts=lambda _: dict(artifacts),
        )


@pytest.mark.parametrize("field,value", [
    ("workflow_id", 1), ("path", "wrong.yml"), ("head_branch", "feature"),
])
def test_generic_identity_drift_is_not_silently_filtered(monkeypatch, field, value):
    def fake_audit(**_kwargs):
        audit._run_is_collection_candidate({**_queued_run(), field: value})
        pytest.fail("generic dispatch drift was silently filtered")

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_audit)
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._audit_actions_lineage_compatible(
            get_run_jobs=_empty_jobs, get_run_artifacts=_empty_artifacts,
        )


def test_records_are_exact_and_deterministic_without_continuity_authority(monkeypatch):
    runs = [
        {**_queued_run(), "id": 30},
        {**_queued_run(), "id": 20},
        {**_queued_run(), "id": 40, "created_at": "2026-09-04T00:08:33Z"},
    ]

    def fake_audit(**_kwargs):
        for run in runs + runs:
            assert audit._run_is_collection_candidate(run) is False
        return {"runs": [], "audit_state": "NO_COMPLETED_CAMPAIGN_EVIDENCE"}

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_audit)
    result = projection._audit_actions_lineage_compatible(
        get_run_jobs=_empty_jobs, get_run_artifacts=_empty_artifacts,
    )
    assert result["verified_queued_no_execution_dispatch_count"] == 3
    records = result["projected_queued_no_execution_dispatch_runs"]
    assert [record["run_id"] for record in records] == [40, 20, 30]
    assert records[0] == {
        "run_id": 40, "created_at": "2026-09-04T00:08:33Z",
        "head_sha": runs[0]["head_sha"], "conclusion": None,
        "evidence_state": "VERIFIED_QUEUED_NO_EXECUTION_TRANSPORT",
        "execution_provenance": "PROSPECTIVE_CONTINUITY_DISPATCH_PENDING_NO_EXECUTION",
        "nominal_slot_utc": None, "tick_committed": False,
        "archive_name": None, "archive_sha256": None,
        "release_state": "NOT_APPLICABLE_NO_ACQUISITION", "verification_error": None,
    }
    assert result["runs"] == []
    assert result["audit_state"] == "NO_COMPLETED_CAMPAIGN_EVIDENCE"
    assert not result.get("verified_continuity_dispatch_count")
