from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from scripts import audit_p4_4m_athena_run_pc_upcoming_evidence_preservation as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution


def _workflow(raw: bytes) -> dict:
    return yaml.load(raw.decode("utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, step_id: str) -> dict:
    return next(
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("id") == step_id
    )


def test_active_pc_upcoming_root_is_added_only_to_existing_optional_preservation_loop() -> None:
    assert source.EVIDENCE_ROOT.as_posix() == audit.PC_ROOT
    before = audit._workflow_bytes(Path(audit.FIXTURE_PATH))
    current = audit._workflow_bytes(Path(audit.WORKFLOW_PATH))
    before_run = _step(_workflow(before), "preserve_shadow_evidence")["run"]
    current_run = _step(_workflow(current), "preserve_shadow_evidence")["run"]
    assert audit.PC_ROOT not in before_run
    assert current_run.count(audit.PC_ROOT) == 1
    assert current_run.replace(f"  '{audit.PC_ROOT}' \\\n", "", 1) == before_run
    assert all(current_run.count(root) == 1 for root in audit.PREVIOUS_ROOTS)
    assert "artifacts/athena-run-workflow/source-evidence" in current_run
    assert 'if [ -d "${source_dir}" ]; then' in current_run
    assert 'cp -a "${source_dir}" "${evidence_root}/"' in current_run
    assert "else" not in current_run.split("identity_path=", 1)[0]


def test_workflow_contract_is_identical_except_the_single_evidence_root() -> None:
    before = _workflow(audit._workflow_bytes(Path(audit.FIXTURE_PATH)))
    current = _workflow(audit._workflow_bytes(Path(audit.WORKFLOW_PATH)))
    restored = copy.deepcopy(current)
    _step(restored, "preserve_shadow_evidence")["run"] = _step(before, "preserve_shadow_evidence")["run"]
    assert restored == before
    assert current["on"] == before["on"]
    assert current["on"]["workflow_dispatch"]["inputs"] == before["on"]["workflow_dispatch"]["inputs"]
    assert current["on"]["schedule"] == before["on"]["schedule"]
    assert current["permissions"] == before["permissions"]
    assert current["concurrency"] == before["concurrency"]
    assert set(current["jobs"]) == set(before["jobs"])


def test_identity_state_and_canonical_artifact_upload_contract_are_unchanged() -> None:
    current = _workflow(audit._workflow_bytes(Path(audit.WORKFLOW_PATH)))
    run = _step(current, "preserve_shadow_evidence")["run"]
    assert 'identity_path="${ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH:-}"' in run
    assert "artifacts/athena-run-workflow/identity-state" in run
    upload = _step(current, "upload_evidence")["with"]
    assert upload["name"] == "athena-run-${{ github.run_id }}"
    assert upload["retention-days"] == "30"
    assert upload["path"] == "artifacts/athena-run-workflow\nartifacts/athena-runs"


def test_evolution_ledger_appends_exactly_one_maintenance_revision() -> None:
    ledger = json.loads(audit.LEDGER_PATH.read_text(encoding="utf-8"))
    prior = json.loads(audit.PREVIOUS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    snapshot = json.loads(audit.SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert ledger["transitions"][:6] == prior["transitions"]
    assert len(ledger["transitions"]) == 7
    assert snapshot == ledger
    transition = ledger["transitions"][-1]
    assert transition["phase_id"] == "P4.4M"
    assert transition["transition_id"] == "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1"
    assert transition["operation"] == "MAINTENANCE_REVISE"
    assert transition["workflow_path"] == audit.WORKFLOW_PATH
    assert transition["canonical_family"] == "ATHENA_RUN"
    assert transition["maintenance_contract"] == evolution.MAINTENANCE_CONTRACT
    assert ledger["current_live_workflow_count"] == 38
    assert ledger["current_p4_3_retired_workflow_count"] == 3


def test_receipt_hash_is_canonical_and_runtime_team_label_contracts_are_unchanged() -> None:
    receipt = audit.check()
    assert receipt["canonical_sha256"] == evolution.canonical_sha256(receipt)
    assert receipt["team_label_policy_changed"] is False
    assert receipt["fixture_identity_policy_changed"] is False
    assert receipt["pc_upcoming_source_policy_changed"] is False
    assert receipt["runtime_wrapper_policy_changed"] is False
    assert receipt["provider_acquisition_during_implementation"] == 0
    assert receipt["workflow_dispatches_during_implementation"] == 0
    assert receipt["live_retries"] == 0


def test_offline_p44m_audit_passes() -> None:
    assert audit.check()["policy_id"] == audit.POLICY_ID
