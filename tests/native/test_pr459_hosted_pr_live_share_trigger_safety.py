"""Native-portable regression for the PR-459 offline workflow boundary."""
from __future__ import annotations

from scripts import audit_core_01d_pr459_live_trigger_incident as incident


def test_direct_share_workflows_keep_pr_and_manual_lanes_offline():
    for path in (incident.CREATE_WORKFLOW, incident.PROVE_WORKFLOW):
        workflow = incident._validate_workflow(path)
        assert workflow["permissions"] == {"contents": "read"}
        assert workflow["on"]["pull_request"]["branches"] == ["main"]
        assert workflow["on"]["workflow_dispatch"]["inputs"]["validation_mode"]["options"] == [
            "offline_only"
        ]

        jobs = workflow["jobs"]
        assert set(jobs) == {"offline-validation"}
        assert jobs["offline-validation"]["runs-on"] == "ubuntu-latest"
        steps = jobs["offline-validation"]["steps"]
        assert steps[-1]["run"] == "python -m scripts.audit_core_01d_pr459_live_trigger_incident"
        assert all(step.get("continue-on-error") is None for step in steps)
