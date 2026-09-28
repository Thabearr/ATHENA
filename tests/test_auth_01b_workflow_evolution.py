from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import socket
import urllib.request

import pytest

from scripts import audit_auth_01b_workflow_evolution as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_auth_01b_workflow_transition_is_exact_and_historical_prefix_is_immutable() -> None:
    result = audit.audit()
    assert result["status"] == "PASS"
    assert result["transition_id"] == "AUTH01B_ATHENA_RUN_EXPLICIT_DELIVERY_INTENT_V1"
    assert result["workflow_before_identity"] == audit.EXPECTED_BEFORE
    assert result["environment_handoff_count"] == 1
    assert result["network_provider_side_effects"] == 0
    assert len(result["checkpoint_sha256"]) == 64
    assert len(result["receipt_sha256"]) == 64
    assert result["p44m_receipt_blob_unchanged"]
    assert result["p44m_snapshot_blob_unchanged"]


def test_auth_01b_receipt_is_offline_safe_under_network_sentinels(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def denied(*_args, **_kwargs):
        calls.append("network")
        raise AssertionError("AUTH-01B audit attempted network access")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    assert audit.audit()["status"] == "PASS"
    assert calls == []


def test_auth_01b_receipt_and_before_fixture_have_expected_exact_identities() -> None:
    fixture = audit.BEFORE_FIXTURE_PATH.read_bytes().replace(b"\r\n", b"\n")
    assert evolution.source_identity(fixture) == audit.EXPECTED_BEFORE
    receipt = json.loads(audit.RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["repository"] == "Thabearr/ATHENA"
    assert receipt["base_main_sha"] == audit.BASE_MAIN_SHA
    assert receipt["workflow_before_identity"] == audit.EXPECTED_BEFORE
    assert receipt["canonical_sha256"] == evolution.canonical_sha256(receipt)
    assert "share_code" not in json.dumps(receipt).replace("create_share_code", "")
    forbidden_fields = {"raw_share_code", "share_code_url", "token", "cookie_value", "credential", "secret"}

    def keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)

    assert not forbidden_fields.intersection(keys(receipt))


def test_v2_input_surface_contract_does_not_claim_trigger_or_authority_changes() -> None:
    contract = evolution.AUTHORITY_SURFACE_MAINTENANCE_CONTRACT_V2
    assert contract["policy_id"] == "ATHENA_P4_BASELINE_WORKFLOW_MAINTENANCE_REVISE_V2"
    assert contract["event_trigger_kinds_changed"] is False
    assert contract["workflow_dispatch_input_surface_changed"] is True
    assert contract["schedule_surface_changed"] is False
    assert contract["permissions_changed"] is False
    assert contract["concurrency_changed"] is False
    assert contract["provider_step_added"] is False
    assert contract["delivery_step_added"] is False
    assert contract["betting_authority_changed"] is False


def _reviewed_workflows() -> tuple[dict, dict]:
    before = evolution.resolve_reviewed_transition_after_source(
        audit.WORKFLOW_PATH,
        "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1",
    )
    after = Path(audit.WORKFLOW_PATH).read_bytes().replace(b"\r\n", b"\n")
    return audit._yaml(before, "P4.4M"), audit._yaml(after, "AUTH-01B")


@pytest.mark.parametrize("mutation", ["schedule", "permissions", "concurrency", "event", "provider_step", "delivery_step"])
def test_workflow_delta_rejects_any_non_input_or_handoff_change(mutation: str) -> None:
    before, after = _reviewed_workflows()
    changed = copy.deepcopy(after)
    if mutation == "schedule":
        changed["on"]["schedule"][0]["cron"] = "1 1 * * *"
    elif mutation == "permissions":
        changed["permissions"]["contents"] = "write"
    elif mutation == "concurrency":
        changed["concurrency"]["group"] = "unreviewed-group"
    elif mutation == "event":
        changed["on"]["workflow_call"] = {}
    else:
        step = {"name": "unreviewed execution", "run": "echo unexpected"}
        job = next(iter(changed["jobs"].values()))
        job["steps"].append(step)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError):
        audit.verify_workflow_revision(before, changed)


def test_workflow_delta_rejects_wrong_delivery_choice_shape() -> None:
    before, after = _reviewed_workflows()
    changed = copy.deepcopy(after)
    changed["on"]["workflow_dispatch"]["inputs"]["create_share_code"]["options"] = ["true"]
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="input contract"):
        audit.verify_workflow_revision(before, changed)


def test_auth_01b_audit_has_no_provider_or_transport_imports() -> None:
    tree = ast.parse(Path("scripts/audit_auth_01b_workflow_evolution.py").read_text(encoding="utf-8"))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    forbidden = ("provider", "sportybet", "fotmob", "requests", "httpx", "urllib", "socket")
    assert not any(token in module.lower() for module in imported for token in forbidden)
