from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import domain.fotmob_fresh_holdout_bridge_noop as bridge_noop


OLD_HEAD = "b428dbd00380dd71456640d77b26ac79fe945c5f"
NEW_HEAD = "bbe542dc7c4f086707b4fe939e8b6a15bd0b215d"
WORKFLOW = Path(
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml"
)


def _run() -> dict:
    return {
        "id": 34477871615,
        "status": "completed",
        "conclusion": "failure",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": OLD_HEAD,
        "created_at": "2026-09-10T12:38:34Z",
    }


def _steps(*, auth: str = "success", state: str = "failure") -> list[dict]:
    return [
        {
            "name": "Authenticate continuity dispatch source",
            "status": "completed",
            "conclusion": auth,
        },
        {
            "name": "Restore newest durable lineage and resolve schedule slot",
            "status": "completed",
            "conclusion": state,
        },
        {
            "name": "Restore or materialize PR119 bootstrap projection",
            "status": "completed",
            "conclusion": "skipped",
        },
        {
            "name": "Execute reviewed fresh-holdout collection tick",
            "status": "completed",
            "conclusion": "skipped",
        },
        {
            "name": "Reconcile any staged capture lineage",
            "status": "completed",
            "conclusion": "skipped",
        },
        {
            "name": "Package durable state archive",
            "status": "completed",
            "conclusion": "skipped",
        },
        {
            "name": "Upload authoritative 90-day Actions artifact",
            "status": "completed",
            "conclusion": "skipped",
        },
        {
            "name": "Publish and verify long-lived evidence release asset",
            "status": "completed",
            "conclusion": "skipped",
        },
    ]


def _jobs(*, auth: str = "success", state: str = "failure") -> dict:
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "failure",
                "steps": _steps(auth=auth, state=state),
            }
        ]
    }


def _prove(run=None, artifacts=None, jobs=None, *, current_main=NEW_HEAD) -> bool:
    return bridge_noop.prove_superseded_preacquisition_no_mirror(
        _run() if run is None else run,
        {"artifacts": []} if artifacts is None else artifacts,
        _jobs() if jobs is None else jobs,
        expected_source_head_sha=OLD_HEAD,
        current_main_sha=current_main,
    )


def test_observed_state_resolution_failure_is_verified_superseded_no_mirror() -> None:
    assert _prove() is True


def test_authentication_failure_is_also_safe_only_when_every_later_step_skipped() -> None:
    assert _prove(jobs=_jobs(auth="failure", state="skipped")) is True


def test_same_current_main_is_not_suppressed() -> None:
    assert _prove(current_main=OLD_HEAD) is False


def test_source_head_mismatch_is_not_suppressed() -> None:
    run = _run()
    run["head_sha"] = NEW_HEAD
    assert _prove(run=run) is False


def test_artifact_presence_is_not_suppressed() -> None:
    assert _prove(artifacts={"artifacts": [{"id": 1}]}) is False


def test_bootstrap_failure_remains_alerting_even_though_it_is_preacquisition() -> None:
    jobs = _jobs(auth="success", state="success")
    jobs["jobs"][0]["steps"][2]["conclusion"] = "failure"
    assert _prove(jobs=jobs) is False


def test_any_acquisition_or_persistence_step_execution_is_not_suppressed() -> None:
    jobs = deepcopy(_jobs())
    for step in jobs["jobs"][0]["steps"]:
        if step["name"] == "Execute reviewed fresh-holdout collection tick":
            step["conclusion"] = "success"
    assert _prove(jobs=jobs) is False


def test_malformed_or_duplicate_step_evidence_fails_closed() -> None:
    jobs = _jobs()
    jobs["jobs"][0]["steps"].append(
        {
            "name": "Restore newest durable lineage and resolve schedule slot",
            "status": "completed",
            "conclusion": "failure",
        }
    )
    assert _prove(jobs=jobs) is False


def test_bridge_wires_exact_noop_proof_and_keeps_mirror_gated() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "import domain.fotmob_fresh_holdout_bridge_noop as bridge_noop" in workflow
    assert "88f97ecb4ae626be9d10e3561f1e52eaebe89242" in workflow
    assert "bridge_noop.prove_superseded_preacquisition_no_mirror(" in workflow
    assert "SUPERSEDED_HEAD_PREACQUISITION_NO_MIRROR" in workflow
    assert 'fh.write("bridge_required=false\\n")' in workflow
    assert "Acknowledge verified receipt bridge no-op" in workflow
    assert "No evidence mutation, provider acquisition, backfill, pricing, selection, or wager authority." in workflow
    assert "if: steps.source.outputs.bridge_required == 'true'" in workflow
