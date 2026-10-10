from __future__ import annotations

from typing import Any

import pytest

from domain import fotmob_fresh_holdout_continuity as continuity
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection


def _run(run_id: int, *, conclusion: str = "success") -> dict[str, Any]:
    return {
        "id": run_id,
        "name": audit.WORKFLOW_NAME,
        "path": audit.WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "status": "completed",
        "conclusion": conclusion,
        "created_at": "2026-08-24T07:15:21Z",
        "head_sha": "a" * 40,
    }


def _safe_noop_jobs() -> dict[str, Any]:
    import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery

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
                        "conclusion": conclusion,
                    }
                    for name, conclusion in recovery._NO_ACQUISITION_REQUIRED_STEP_OUTCOMES.items()
                ],
            }
        ]
    }


def test_projection_excludes_only_proven_ambiguous_no_acquisition_run(monkeypatch):
    noop = _run(101)
    normal = _run(102)
    observed: dict[str, bool] = {}

    def fake_engine(**kwargs):
        observed["noop_candidate"] = audit._run_is_collection_candidate(noop)
        observed["normal_candidate"] = audit._run_is_collection_candidate(normal)
        assert kwargs["get_run_artifacts"](101) == {"artifacts": []}
        return {"audit_state": "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN"}

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_engine)

    def artifacts(run_id: int):
        if run_id == 101:
            return {"artifacts": []}
        return {"artifacts": [{"id": 1, "name": "canonical"}]}

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha="b" * 40,
        get_main_ref=lambda: {"sha": "b" * 40},
        get_runs_page=lambda _page, _per_page: {"workflow_runs": []},
        get_run_artifacts=artifacts,
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_release=lambda _tag: {},
        download_release_asset=lambda _asset_id: b"unused",
        get_run_jobs=lambda _run_id: _safe_noop_jobs(),
        verify_dependencies=False,
    )

    assert observed == {"noop_candidate": False, "normal_candidate": True}
    assert result["verified_ambiguous_no_acquisition_count"] == 1
    assert result["projected_ambiguous_no_acquisition_runs"][0]["run_id"] == 101
    assert (
        result["projected_ambiguous_no_acquisition_runs"][0]["evidence_state"]
        == "VERIFIED_AMBIGUOUS_NO_ACQUISITION"
    )


def test_projection_keeps_unproven_green_zero_artifact_run_as_candidate(monkeypatch):
    unsafe = _run(103)
    observed: dict[str, bool] = {}

    def fake_engine(**_kwargs):
        observed["candidate"] = audit._run_is_collection_candidate(unsafe)
        return {"audit_state": "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"}

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_engine)
    jobs = _safe_noop_jobs()
    jobs["jobs"][0]["steps"] = [
        step
        for step in jobs["jobs"][0]["steps"]
        if step["name"] != "Acknowledge ambiguous schedule without acquisition"
    ]

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha="b" * 40,
        get_main_ref=lambda: {"sha": "b" * 40},
        get_runs_page=lambda _page, _per_page: {"workflow_runs": []},
        get_run_artifacts=lambda _run_id: {"artifacts": []},
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_release=lambda _tag: {},
        download_release_asset=lambda _asset_id: b"unused",
        get_run_jobs=lambda _run_id: jobs,
        verify_dependencies=False,
    )

    assert observed == {"candidate": True}
    assert result["verified_ambiguous_no_acquisition_count"] == 0
    assert result["projected_ambiguous_no_acquisition_runs"] == []


def test_projection_contains_no_provider_or_write_transport():
    from pathlib import Path

    text = Path(
        "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "urllib",
        "curl ",
        "wget ",
        "gh release",
        "rerun",
        "backfill_authorized = True",
        "pricing_authorized = True",
        "selection_authorized = True",
        "bet_authorized = True",
    ):
        assert forbidden not in text


# --- October 10 continuity in-flight deferral --------------------------------
# Incident: Current Shadow run 38031493069 (fixture date 20261010, head
# 74b07c74a946fd19a63f5695055b09668268aef2) failed its post-audit nominal check
# with nominal_slot_utc=None because continuity dispatch 38031641209
# (source watchdog 38030498435, target 2026-10-10T06:37:00Z) was observed
# in-flight: created 06:38:33Z, Shadow stage CURRENT_DURABLE_FRESH_HISTORY
# started 06:38:51Z, dispatch job ran 06:38:36-06:53:20Z, artifact 11663111136
# only appeared 06:53:15Z after Shadow finished 06:46:19Z.  Sealed evidence:
# athena-evidence-20261010/{run-38031493069,cont-38031641209,run-universe,
# watchdog-38030498435-jobs.json,continuity-artifact-name-audit.json}.
# The tests below replay that exact shape offline through the real projection
# and the real frozen audit engine (no monkeypatched engine, no network).

INCIDENT_SHA = "74b07c74a946fd19a63f5695055b09668268aef2"
INCIDENT_WATCHDOG_ID = 38030498435
INCIDENT_DISPATCH_ID = 38031641209
INCIDENT_WATCHDOG_CREATED_AT = "2026-10-10T06:18:53Z"
INCIDENT_TARGET_SLOT = "2026-10-10T06:37:00Z"
INCIDENT_TARGET_CRON = "37 * * * *"
INCIDENT_DISPATCH_CREATED_AT = "2026-10-10T06:38:33Z"


def _incident_title(
    *,
    source: int = INCIDENT_WATCHDOG_ID,
    target: str = INCIDENT_TARGET_SLOT,
    cron: str = INCIDENT_TARGET_CRON,
) -> str:
    return (
        f"ATHENA fresh-holdout workflow_dispatch source={source} "
        f"target={target} cron={cron} "
        f"confirm={continuity.CONTINUITY_CONFIRMATION}"
    )


def _incident_watchdog() -> dict[str, Any]:
    return {
        "id": INCIDENT_WATCHDOG_ID,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": INCIDENT_SHA,
        "created_at": INCIDENT_WATCHDOG_CREATED_AT,
        "status": "completed",
        "conclusion": "success",
    }


def _incident_watchdog_jobs() -> dict[str, Any]:
    return {
        "jobs": [
            {
                "run_id": INCIDENT_WATCHDOG_ID,
                "workflow_name": continuity.WATCHDOG_WORKFLOW_NAME,
                "name": continuity.WATCHDOG_JOB_NAME,
                "head_branch": "main",
                "head_sha": INCIDENT_SHA,
                "status": "completed",
                "conclusion": "success",
                "created_at": INCIDENT_WATCHDOG_CREATED_AT,
                "steps": [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in continuity.WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS
                ],
            }
        ]
    }


def _incident_dispatch(
    *,
    status: str = "in_progress",
    conclusion: Any = None,
    title: str | None = None,
    head_sha: str = INCIDENT_SHA,
    created_at: str = INCIDENT_DISPATCH_CREATED_AT,
) -> dict[str, Any]:
    name = title if title is not None else _incident_title()
    return {
        "id": INCIDENT_DISPATCH_ID,
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID,
        "name": name,
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": head_sha,
        "created_at": created_at,
        "updated_at": created_at,
        "status": status,
        "conclusion": conclusion,
        "display_title": name,
        "run_number": 814,
    }


def _incident_readers(
    dispatch: dict[str, Any],
    *,
    watchdog_jobs: dict[str, Any] | None = None,
    pages: list[list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """Offline readers with sentinels: any dispatch transport read fails."""
    calls: dict[str, list[Any]] = {
        "artifacts": [],
        "zips": [],
        "jobs": [],
        "release": [],
        "release_asset": [],
    }
    jobs_payload = (
        watchdog_jobs if watchdog_jobs is not None else _incident_watchdog_jobs()
    )
    universe = pages if pages is not None else [[dispatch]]

    def get_runs_page(page: int, per_page: int) -> dict[str, Any]:
        assert type(page) is int and type(per_page) is int
        if 1 <= page <= len(universe):
            return {"workflow_runs": universe[page - 1]}
        return {"workflow_runs": []}

    def get_run_by_id(run_id: int) -> dict[str, Any]:
        if run_id == INCIDENT_WATCHDOG_ID:
            return _incident_watchdog()
        raise AssertionError(f"unexpected exact-run read: {run_id}")

    def get_run_artifacts(run_id: int) -> dict[str, Any]:
        calls["artifacts"].append(run_id)
        raise AssertionError(
            f"transport artifact read must not occur for in-flight run {run_id}"
        )

    def download_artifact_zip(artifact_id: int) -> bytes:
        calls["zips"].append(artifact_id)
        raise AssertionError("transport ZIP read must not occur for in-flight run")

    def get_run_jobs(run_id: int) -> dict[str, Any]:
        calls["jobs"].append(run_id)
        if run_id == INCIDENT_WATCHDOG_ID:
            return jobs_payload
        raise AssertionError(
            f"jobs read must not occur for in-flight dispatch {run_id}"
        )

    def get_release(tag: str) -> dict[str, Any]:
        calls["release"].append(tag)
        raise AssertionError("release read must not occur for incomplete universe")

    def download_release_asset(asset_id: int) -> bytes:
        calls["release_asset"].append(asset_id)
        raise AssertionError("release asset read must not occur")

    return (
        {
            "repository": "Thabearr/ATHENA",
            "expected_main_sha": INCIDENT_SHA,
            "get_main_ref": lambda: {"object": {"sha": INCIDENT_SHA}},
            "get_runs_page": get_runs_page,
            "get_run_by_id": get_run_by_id,
            "get_run_artifacts": get_run_artifacts,
            "download_artifact_zip": download_artifact_zip,
            "get_release": get_release,
            "download_release_asset": download_release_asset,
            "get_run_jobs": get_run_jobs,
            "verify_dependencies": False,
        },
        calls,
    )


def _run_real_projection(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Call the real projection with the real frozen engine (no stub)."""
    assert (
        projection._ORIGINAL_AUDIT_ACTIONS_LINEAGE is audit.audit_actions_lineage
    )
    return projection._audit_actions_lineage_compatible(**kwargs)


def test_inflight_continuity_dispatch_defers_without_nominal_error():
    """As-of the incident (dispatch in-flight): defer, stay visible, no error."""
    dispatch = _incident_dispatch()
    kwargs, calls = _incident_readers(dispatch)

    result = _run_real_projection(kwargs)

    records = [
        record for record in result.get("runs", [])
        if record.get("run_id") == INCIDENT_DISPATCH_ID
    ]
    assert len(records) == 1
    record = records[0]
    assert record["evidence_state"] == "INCOMPLETE_NOT_EVIDENCE"
    assert record["nominal_slot_utc"] is None
    # Deferred runs are not labelled as prospective evidence as-of this time.
    assert "execution_provenance" not in record
    assert "verified_prospective_continuity_dispatch_count" not in result
    # Provenance replay read only the watchdog jobs; no artifact/ZIP/release
    # transport touched the in-flight dispatch.
    assert calls["artifacts"] == []
    assert calls["zips"] == []
    assert calls["jobs"] == [INCIDENT_WATCHDOG_ID]
    assert calls["release"] == []
    assert calls["release_asset"] == []


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting"])
def test_inflight_continuity_dispatch_defers_for_every_non_completed_status(
    status: str,
):
    dispatch = _incident_dispatch(status=status)
    kwargs, calls = _incident_readers(dispatch)

    result = _run_real_projection(kwargs)

    records = [
        record for record in result.get("runs", [])
        if record.get("run_id") == INCIDENT_DISPATCH_ID
    ]
    assert len(records) == 1
    assert records[0]["evidence_state"] == "INCOMPLETE_NOT_EVIDENCE"
    assert records[0]["nominal_slot_utc"] is None
    assert "verified_prospective_continuity_dispatch_count" not in result
    assert calls["artifacts"] == []
    assert calls["zips"] == []


def _mutated_incident_dispatch(mutator: str) -> dict[str, Any]:
    if mutator == "target_slot":
        return _incident_dispatch(
            title=_incident_title(target="2026-10-10T07:07:00Z", cron="7 * * * *")
        )
    if mutator == "cron":
        return _incident_dispatch(title=_incident_title(cron="7 * * * *"))
    if mutator == "source_id":
        return _incident_dispatch(title=_incident_title(source=38030498436))
    if mutator == "dispatch_sha":
        return _incident_dispatch(head_sha="b" * 40)
    if mutator == "confirmation":
        return _incident_dispatch(
            title=_incident_title().replace(
                continuity.CONTINUITY_CONFIRMATION, "BACKFILL_V1"
            )
        )
    raise AssertionError(f"unknown mutator: {mutator}")


@pytest.mark.parametrize(
    "mutator",
    ["target_slot", "cron", "source_id", "dispatch_sha", "confirmation"],
    ids=["slot", "cron", "source-id", "dispatch-sha", "confirmation"],
)
def test_inflight_malformed_provenance_still_fails_closed(mutator: str):
    """Provenance replay runs before deferral: malformed in-flight still raises."""
    dispatch = _mutated_incident_dispatch(mutator)
    kwargs, calls = _incident_readers(dispatch)
    if mutator == "source_id":
        # The title names a different watchdog; answer with the sealed incident
        # watchdog payload so provenance fails closed on identity, not on a
        # transport sentinel.
        kwargs["get_run_by_id"] = lambda run_id: _incident_watchdog()
        kwargs["get_run_jobs"] = lambda run_id: (
            calls["jobs"].append(run_id), _incident_watchdog_jobs()
        )[1]

    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        _run_real_projection(kwargs)

    assert calls["artifacts"] == []
    assert calls["zips"] == []


def test_inflight_watchdog_job_sha_drift_still_fails_closed():
    jobs = _incident_watchdog_jobs()
    jobs["jobs"][0]["head_sha"] = "b" * 40
    kwargs, calls = _incident_readers(_incident_dispatch(), watchdog_jobs=jobs)

    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        _run_real_projection(kwargs)

    assert calls["artifacts"] == []


def test_inflight_watchdog_missing_step_still_fails_closed():
    jobs = _incident_watchdog_jobs()
    jobs["jobs"][0]["steps"] = jobs["jobs"][0]["steps"][:-1]
    kwargs, _calls = _incident_readers(_incident_dispatch(), watchdog_jobs=jobs)

    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        _run_real_projection(kwargs)


def test_inflight_ambiguous_watchdog_source_still_fails_closed():
    jobs = _incident_watchdog_jobs()
    jobs["jobs"] = [dict(jobs["jobs"][0]), dict(jobs["jobs"][0])]
    kwargs, _calls = _incident_readers(_incident_dispatch(), watchdog_jobs=jobs)

    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        _run_real_projection(kwargs)


def test_inflight_watchdog_id_mismatch_still_fails_closed():
    def wrong_source(run_id: int) -> dict[str, Any]:
        watchdog = _incident_watchdog()
        watchdog["id"] = run_id + 1
        return watchdog

    dispatch = _incident_dispatch()
    kwargs, _calls = _incident_readers(dispatch)
    kwargs["get_run_by_id"] = wrong_source

    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        _run_real_projection(kwargs)


def test_inflight_deferral_independent_of_page_order():
    """Ordering permutation: noop schedule run + in-flight dispatch, both orders."""
    noop = _run(101)
    dispatch = _incident_dispatch()
    outcomes = []
    # Both orders on one page: the frozen audit stops at the first short page,
    # so a multi-page split would hide later pages instead of reordering them.
    for pages in ([[noop, dispatch]], [[dispatch, noop]]):
        kwargs, calls = _incident_readers(dispatch, pages=pages)

        def artifacts(run_id: int) -> dict[str, Any]:
            if run_id == 101:
                return {"artifacts": []}
            calls["artifacts"].append(run_id)
            raise AssertionError(
                f"transport artifact read must not occur for {run_id}"
            )

        def jobs(run_id: int) -> dict[str, Any]:
            calls["jobs"].append(run_id)
            if run_id == 101:
                return _safe_noop_jobs()
            if run_id == INCIDENT_WATCHDOG_ID:
                return _incident_watchdog_jobs()
            raise AssertionError(f"unexpected jobs read: {run_id}")

        kwargs["get_run_artifacts"] = artifacts
        kwargs["get_run_jobs"] = jobs

        result = _run_real_projection(kwargs)
        outcomes.append(
            (
                result["verified_ambiguous_no_acquisition_count"],
                "verified_prospective_continuity_dispatch_count" in result,
                [
                    (record.get("run_id"), record.get("evidence_state"))
                    for record in result.get("runs", [])
                ],
            )
        )
        assert INCIDENT_DISPATCH_ID not in calls["artifacts"]

    assert outcomes[0] == outcomes[1]
    noop_count, has_continuity_count, rows = outcomes[0]
    assert noop_count == 1
    assert has_continuity_count is False
    assert (INCIDENT_DISPATCH_ID, "INCOMPLETE_NOT_EVIDENCE") in rows


def test_completed_continuity_pairing_still_admitted_with_provenance():
    """As-of completion: the same provenance shape is admitted as evidence."""
    from tests.test_fotmob_fresh_holdout_continuity_projection_reader_integration import (
        _continuity_audit_inputs,
    )

    values = _continuity_audit_inputs()
    readers = values["readers"]

    result = _run_real_projection(
        {
            "repository": "Thabearr/ATHENA",
            "expected_main_sha": "a" * 40,
            "get_main_ref": readers["get_main_ref"],
            "get_runs_page": readers["get_runs_page"],
            "get_run_by_id": readers["get_run_by_id"],
            "get_run_artifacts": readers["get_run_artifacts"],
            "download_artifact_zip": readers["download_artifact_zip"],
            "get_release": readers["get_release"],
            "download_release_asset": readers["download_release_asset"],
            "get_run_jobs": readers["get_run_jobs"],
            "verify_dependencies": False,
        }
    )

    assert result["verified_prospective_continuity_dispatch_count"] == 1
    assert result["runs"][0]["execution_provenance"] == (
        "PROSPECTIVE_CONTINUITY_DISPATCH"
    )
    assert result["runs"][0]["nominal_slot_utc"] == "2026-08-19T00:07:00Z"


def test_completed_continuity_slot_mismatch_still_fails_closed():
    """The nominal-slot-vs-target check is unchanged for completed runs."""
    from tests.test_fotmob_fresh_holdout_actions_lineage_audit import (
        committed,
        evidence_bundle,
    )
    from domain import fotmob_fresh_holdout_continuity as continuity_module

    sha = "a" * 40
    watchdog_id = 123
    dispatch_id = 456
    # Watchdog plans 00:37, so the title target is authentic; the artifact
    # below genuinely belongs to 00:07, which must trip the nominal check.
    title_slot = "2026-08-19T00:37:00Z"
    bundle_slot = "2026-08-19T00:07:00Z"
    title = (
        f"ATHENA fresh-holdout workflow_dispatch source={watchdog_id} "
        f"target={title_slot} cron=37 * * * * "
        f"confirm={continuity_module.CONTINUITY_CONFIRMATION}"
    )
    watchdog = {
        "id": watchdog_id,
        "name": continuity_module.WATCHDOG_WORKFLOW_NAME,
        "path": continuity_module.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": sha,
        "created_at": "2026-08-19T00:18:53Z",
        "status": "completed",
        "conclusion": "success",
    }
    watchdog_jobs = {
        "jobs": [
            {
                "run_id": watchdog_id,
                "workflow_name": continuity_module.WATCHDOG_WORKFLOW_NAME,
                "name": continuity_module.WATCHDOG_JOB_NAME,
                "head_branch": "main",
                "head_sha": sha,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-08-19T00:18:55Z",
                "steps": [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in continuity_module.WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS
                ],
            }
        ]
    }
    dispatch = {
        "id": dispatch_id,
        "workflow_id": continuity_module.PRIMARY_WORKFLOW_ID,
        "name": title,
        "path": continuity_module.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": sha,
        "created_at": "2026-08-19T00:37:08Z",
        "status": "completed",
        "conclusion": "success",
        "display_title": title,
    }
    bundle = evidence_bundle(dispatch_id, bundle_slot, rows=[committed(bundle_slot)])
    artifact = {
        "id": 9001,
        "name": bundle["artifact_name"],
        "expired": False,
        "digest": bundle["zip_digest"],
    }
    release = {
        "assets": [
            {
                "id": 9101,
                "name": bundle["artifact_name"],
                "state": "uploaded",
                "size": len(bundle["archive"]),
            },
            {
                "id": 9102,
                "name": bundle["artifact_name"] + ".receipt.json",
                "state": "uploaded",
                "size": len(bundle["receipt"]),
            },
        ]
    }

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="continuity artifact nominal slot differs from authenticated target",
    ):
        _run_real_projection(
            {
                "repository": "Thabearr/ATHENA",
                "expected_main_sha": sha,
                "get_main_ref": lambda: {"object": {"sha": sha}},
                "get_runs_page": lambda _page, _per_page: {
                    "workflow_runs": [dispatch]
                },
                "get_run_by_id": lambda run_id: watchdog,
                "get_run_artifacts": lambda run_id: {"artifacts": [artifact]},
                "download_artifact_zip": lambda _artifact_id: bundle["zip"],
                "get_release": lambda _tag: release,
                "download_release_asset": lambda asset_id: (
                    bundle["archive"] if asset_id == 9101 else bundle["receipt"]
                ),
                "get_run_jobs": lambda _run_id: watchdog_jobs,
                "verify_dependencies": False,
            }
        )
