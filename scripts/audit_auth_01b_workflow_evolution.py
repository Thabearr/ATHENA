#!/usr/bin/env python3
"""Offline audit for the AUTH-01B canonical workflow input-surface revision."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from scripts import audit_p4_workflow_evolution_ledger as evolution


BASE_MAIN_SHA = "396614bd722c0e1e5dd2f35adeab4d90196082f5"
WORKFLOW_PATH = ".github/workflows/athena-run.yml"
TRANSITION_ID = "AUTH01B_ATHENA_RUN_EXPLICIT_DELIVERY_INTENT_V1"
RECEIPT_PATH = Path("artifacts/architecture/auth_01b_athena_run_explicit_delivery_intent_v1.json")
SNAPSHOT_PATH = Path(
    "artifacts/architecture/p4_workflow_evolution_snapshots/auth_01b_athena_run_explicit_delivery_intent_v1.json"
)
BEFORE_FIXTURE_PATH = Path(
    "tests/fixtures/architecture/revised_workflows/athena-run-pre-auth-01b-explicit-delivery-intent.yml"
)
P44M_RECEIPT_PATH = Path("artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json")
P44M_SNAPSHOT_PATH = Path(
    "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json"
)
POLICY_ID = "ATHENA_AUTH_01B_WORKFLOW_EVOLUTION_EVIDENCE_V1"
EXPECTED_BEFORE = {
    "git_blob_sha1": "9bb6312dbe50e11c836fb5a0bd4270a537e850c1",
    "source_sha256": "45f7fe3556f892320a12b15c210637782edca60792ccbf030a714414a32f005a",
}


class Auth01BWorkflowEvolutionError(AssertionError):
    """Raised when AUTH-01B workflow history or evidence is inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Auth01BWorkflowEvolutionError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Auth01BWorkflowEvolutionError(f"AUTH-01B evidence JSON is unavailable: {path}") from exc
    if type(value) is not dict:
        raise Auth01BWorkflowEvolutionError(f"AUTH-01B evidence must be an object: {path}")
    return value


def _yaml(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = yaml.load(raw.decode("utf-8"), Loader=yaml.BaseLoader)
    except (UnicodeError, yaml.YAMLError) as exc:
        raise Auth01BWorkflowEvolutionError(f"{label} workflow YAML is invalid") from exc
    if type(value) is not dict:
        raise Auth01BWorkflowEvolutionError(f"{label} workflow YAML root must be an object")
    return value


def _strip_auth01b_additions(workflow: dict[str, Any]) -> tuple[dict[str, Any], int]:
    result = copy.deepcopy(workflow)
    try:
        inputs = result["on"]["workflow_dispatch"]["inputs"]
        _require("create_share_code" in inputs, "AUTH-01B workflow input is missing")
        del inputs["create_share_code"]
    except (KeyError, TypeError) as exc:
        raise Auth01BWorkflowEvolutionError("AUTH-01B workflow dispatch input surface is malformed") from exc

    handoffs: list[tuple[dict[str, Any], str]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "INPUT_CREATE_SHARE_CODE" in value:
                handoffs.append((value, value["INPUT_CREATE_SHARE_CODE"]))
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(result)
    _require(len(handoffs) == 1, "AUTH-01B must add exactly one explicit workflow environment handoff")
    owner, value = handoffs[0]
    _require(value == "${{ inputs.create_share_code }}", "workflow delivery-intent handoff differs")
    del owner["INPUT_CREATE_SHARE_CODE"]
    return result, len(handoffs)


def verify_workflow_revision(
    before_workflow: dict[str, Any],
    after_workflow: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    dispatch = after_workflow.get("on", {}).get("workflow_dispatch", {}).get("inputs", {}).get("create_share_code")
    _require(dispatch == {
        "description": "Explicit external share-code delivery intent",
        "required": "true",
        "default": "false",
        "type": "choice",
        "options": ["false", "true"],
    }, "AUTH-01B delivery input contract differs")
    stripped, handoff_count = _strip_auth01b_additions(after_workflow)
    _require(stripped == before_workflow, "AUTH-01B workflow changed beyond the explicit input and its environment handoff")
    _require(after_workflow.get("on", {}).keys() == before_workflow.get("on", {}).keys(), "AUTH-01B changed workflow event kinds")
    _require(after_workflow.get("on", {}).get("schedule") == before_workflow.get("on", {}).get("schedule"), "AUTH-01B changed schedule")
    _require(after_workflow.get("permissions") == before_workflow.get("permissions"), "AUTH-01B changed permissions")
    _require(after_workflow.get("concurrency") == before_workflow.get("concurrency"), "AUTH-01B changed concurrency")
    summary = {
        "event_kinds_changed": False,
        "schedule_changed": False,
        "permissions_changed": False,
        "concurrency_changed": False,
        "provider_execution_step_added": False,
        "delivery_execution_step_added": False,
        "workflow_dispatch_input_before": sorted(before_workflow["on"]["workflow_dispatch"]["inputs"]),
        "workflow_dispatch_input_after": sorted(after_workflow["on"]["workflow_dispatch"]["inputs"]),
        "explicit_delivery_input_name": "create_share_code",
    }
    return summary, handoff_count


def _verify_historical_file_unchanged(path: Path) -> str:
    try:
        before = subprocess.check_output(
            ["git", "rev-parse", f"{BASE_MAIN_SHA}:{path.as_posix()}"], text=True
        ).strip()
        after = subprocess.check_output(
            ["git", "rev-parse", f"HEAD:{path.as_posix()}"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Auth01BWorkflowEvolutionError(f"cannot verify immutable historical file: {path}") from exc
    _require(before == after, f"historical P4.4 file changed: {path}")
    return before


def audit() -> dict[str, Any]:
    ledger = evolution.validate_current_state()
    snapshot = _read_json(SNAPSHOT_PATH)
    receipt = _read_json(RECEIPT_PATH)
    p44m_snapshot = _read_json(P44M_SNAPSHOT_PATH)
    p44m_receipt = _read_json(P44M_RECEIPT_PATH)

    transitions = ledger["transitions"]
    _require(len(p44m_snapshot.get("transitions", [])) == 7, "P4.4M immutable snapshot is not seven transitions")
    _require(transitions[:7] == p44m_snapshot["transitions"], "AUTH-01B rewrote the seven-transition P4.4M prefix")
    _require(snapshot.get("transitions") == transitions[:8], "AUTH-01B snapshot is not its exact eight-transition checkpoint")
    _require(snapshot.get("canonical_sha256") == evolution.canonical_sha256(snapshot), "AUTH-01B checkpoint hash is invalid")
    try:
        evolution.validate_evolution_snapshot_extension(snapshot, ledger)
    except evolution.WorkflowEvolutionError as exc:
        raise Auth01BWorkflowEvolutionError("current ledger is not a valid AUTH-01B checkpoint extension") from exc

    matches = [item for item in transitions if item.get("transition_id") == TRANSITION_ID]
    _require(len(matches) == 1, "AUTH-01B transition id is missing or ambiguous")
    transition = matches[0]
    _require(transitions[7] == transition, "AUTH-01B is not the single append after P4.4M")
    _require(transition.get("phase_id") == "AUTH-01B" and transition.get("operation") == "MAINTENANCE_REVISE", "AUTH-01B transition phase/operation differs")
    _require(transition.get("workflow_path") == WORKFLOW_PATH and transition.get("canonical_family") == "ATHENA_RUN", "AUTH-01B transition workflow ownership differs")
    _require(transition.get("before") == EXPECTED_BEFORE, "AUTH-01B before identity differs from exact main")
    _require(transition.get("maintenance_contract") == evolution.AUTHORITY_SURFACE_MAINTENANCE_CONTRACT_V2, "AUTH-01B does not use the exact input-surface V2 contract")

    fixture_bytes = BEFORE_FIXTURE_PATH.read_bytes().replace(b"\r\n", b"\n")
    _require(evolution.source_identity(fixture_bytes) == EXPECTED_BEFORE, "AUTH-01B before fixture bytes differ from authoritative main")
    _require(transition.get("historical_before_fixture") == {"path": BEFORE_FIXTURE_PATH.as_posix(), **EXPECTED_BEFORE}, "AUTH-01B before fixture identity is not bound")
    current_bytes = Path(WORKFLOW_PATH).read_bytes().replace(b"\r\n", b"\n")
    current_identity = evolution.source_identity(current_bytes)
    _require(transition.get("after") == current_identity, "AUTH-01B after identity differs from current workflow")

    old_workflow = _yaml(evolution.resolve_reviewed_transition_after_source(
        WORKFLOW_PATH,
        "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1",
    ), "P4.4M")
    new_workflow = _yaml(current_bytes, "AUTH-01B")
    workflow_summary, handoff_count = verify_workflow_revision(old_workflow, new_workflow)

    _require(receipt.get("schema_version") == 1 and receipt.get("policy_id") == POLICY_ID, "AUTH-01B evidence policy identity differs")
    _require(receipt.get("repository") == "Thabearr/ATHENA" and receipt.get("base_main_sha") == BASE_MAIN_SHA, "AUTH-01B repository/base identity differs")
    _require(receipt.get("workflow_before_identity") == EXPECTED_BEFORE and receipt.get("workflow_after_identity") == current_identity, "AUTH-01B receipt workflow identities differ")
    _require(receipt.get("reviewed_workflow_transition") == {key: value for key, value in transition.items() if key != "evidence_body_sha256"}, "AUTH-01B receipt does not bind exact transition")
    _require(receipt.get("workflow_evolution_checkpoint_path") == SNAPSHOT_PATH.as_posix(), "AUTH-01B checkpoint backlink path differs")
    _require(snapshot.get("canonical_sha256") == receipt.get("workflow_evolution_ledger_sha256"), "AUTH-01B checkpoint backlink SHA differs")
    _require(receipt.get("canonical_sha256") == evolution.canonical_sha256(receipt), "AUTH-01B evidence self-hash is invalid")
    _require(evolution.receipt_evidence_body_sha256(receipt) == transition.get("evidence_body_sha256"), "AUTH-01B evidence body hash differs")
    _require(receipt.get("workflow_change") == workflow_summary, "AUTH-01B workflow change summary is not truthful")
    _require(receipt.get("implementation_side_effects") == {
        "provider_acquisition": 0,
        "workflow_dispatch": 0,
        "live_retry": 0,
        "share_code_action": 0,
        "email": 0,
        "login": 0,
        "cookies": 0,
        "wallet": 0,
        "staking": 0,
        "wager": 0,
    }, "AUTH-01B implementation side-effect record differs")
    governance = receipt.get("governance")
    _require(governance == {
        "p4_4_complete": False,
        "architecture_checkpoint_e_complete": False,
        "canonical_shadow_successor_proof_complete": False,
        "caller_migration_authorized": False,
        "workflow_retirement_authorized": False,
        "next_live_proof_authorized": False,
    }, "AUTH-01B evidence overclaims governance authority")

    p44m_receipt_blob = _verify_historical_file_unchanged(P44M_RECEIPT_PATH)
    p44m_snapshot_blob = _verify_historical_file_unchanged(P44M_SNAPSHOT_PATH)
    return {
        "status": "PASS",
        "policy_id": POLICY_ID,
        "transition_id": TRANSITION_ID,
        "workflow_before_identity": EXPECTED_BEFORE,
        "workflow_after_identity": current_identity,
        "checkpoint_sha256": snapshot["canonical_sha256"],
        "receipt_sha256": receipt["canonical_sha256"],
        "p44m_receipt_blob_unchanged": p44m_receipt_blob,
        "p44m_snapshot_blob_unchanged": p44m_snapshot_blob,
        "environment_handoff_count": handoff_count,
        "workflow_count": ledger["current_live_workflow_count"],
        "workflow_retirement_count": ledger["current_p4_3_retired_workflow_count"],
        "network_provider_side_effects": 0,
    }


def main() -> int:
    print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
