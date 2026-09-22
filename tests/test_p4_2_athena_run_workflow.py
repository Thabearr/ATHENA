from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pytest

from domain.run_contracts import RunReceipt, RunRequest, canonical_json_bytes
from scripts import audit_p4_2_athena_run_workflow as audit
from scripts.execute_athena_run_workflow import (
    AthenaWorkflowExecutionError,
    execute_persisted_request,
)
from scripts.resolve_athena_run_workflow_request import resolve_and_persist
from services.athena_run_service import AthenaRunService, ExecutorResult
from services.athena_run_workflow_request import resolve_workflow_request


FIXED_NOW = datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc)
FIXED_COMMIT = audit.BASE_MAIN_SHA
ROOT = Path(__file__).resolve().parents[1]


def _request() -> RunRequest:
    return resolve_workflow_request(event_name="schedule", now=FIXED_NOW)


def _synthetic_service(executor):
    return AthenaRunService(
        _test_executor_overrides={
            ("MAIN", "main_application", "sportybet"): executor,
        },
        _commit_sha_provider=lambda: FIXED_COMMIT,
        _clock=lambda: FIXED_NOW,
    )


def test_workflow_request_is_persisted_as_exact_canonical_bytes(tmp_path):
    output_root = tmp_path / "resolution"
    github_output = tmp_path / "github-output"
    request, metadata = resolve_and_persist(
        event_name="schedule",
        dispatch_inputs=None,
        github_sha=FIXED_COMMIT,
        github_ref="refs/heads/main",
        output_root=output_root,
        github_output_path=github_output,
        now=FIXED_NOW,
    )
    request_path = output_root / "resolved-run-request.json"
    metadata_path = output_root / "workflow-request-resolution.json"
    assert request_path.read_bytes() == canonical_json_bytes(request)
    assert RunRequest.from_json_bytes(request_path.read_bytes()) == request
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == metadata
    assert metadata["request_canonical_sha256"] == request.canonical_sha256
    assert metadata["exact_github_sha"] == FIXED_COMMIT
    assert metadata["exact_github_ref"] == "refs/heads/main"
    assert "=" in github_output.read_text(encoding="utf-8")


def test_resolved_request_conflict_is_not_overwritten(tmp_path):
    output_root = tmp_path / "resolution"
    request_path = output_root / "resolved-run-request.json"
    request_path.parent.mkdir(parents=True)
    request_path.write_bytes(b"contradictory evidence\n")
    with pytest.raises(ValueError, match="refusing to replace contradictory"):
        resolve_and_persist(
            event_name="schedule",
            dispatch_inputs=None,
            github_sha=FIXED_COMMIT,
            github_ref="refs/heads/main",
            output_root=output_root,
            now=FIXED_NOW,
        )
    assert request_path.read_bytes() == b"contradictory evidence\n"


def test_transport_passes_exact_persisted_request_to_service_and_returns_receipt_unchanged(tmp_path):
    request = _request()
    request_path = tmp_path / "resolved-run-request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    calls = []

    def executor(actual_request, **_kwargs):
        calls.append(actual_request)
        return ExecutorResult(status="MAIN_PHASE6_AUTHORITY_REQUIRED", evidence={"synthetic": True})

    service = _synthetic_service(executor)
    receipt = execute_persisted_request(
        request_path=request_path,
        output_root=tmp_path / "runs",
        expected_git_sha=FIXED_COMMIT,
        expected_git_ref="refs/heads/main",
        service=service,
        git_head_provider=lambda: FIXED_COMMIT,
    )
    assert calls == [request]
    assert type(receipt) is RunReceipt
    assert receipt.request == request
    assert receipt.exact_commit_sha == FIXED_COMMIT
    assert receipt.wager_placed is False


@pytest.mark.parametrize(
    ("expected_sha", "expected_ref", "head"),
    [
        ("b" * 40, "refs/heads/main", FIXED_COMMIT),
        (FIXED_COMMIT, "refs/heads/feature/test", FIXED_COMMIT),
    ],
)
def test_lineage_or_nonmain_ref_fails_before_service(tmp_path, expected_sha, expected_ref, head):
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))

    class MustNotRunService:
        def run(self, *_args, **_kwargs):
            pytest.fail("service ran before exact main/commit gate")

    with pytest.raises(AthenaWorkflowExecutionError):
        execute_persisted_request(
            request_path=request_path,
            output_root=tmp_path / "runs",
            expected_git_sha=expected_sha,
            expected_git_ref=expected_ref,
            service=MustNotRunService(),  # type: ignore[arg-type]
            git_head_provider=lambda: head,
        )


def test_noncanonical_request_bytes_fail_before_service(tmp_path):
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request.to_dict(), indent=2) + "\n", encoding="utf-8")

    class MustNotRunService:
        def run(self, *_args, **_kwargs):
            pytest.fail("service ran with noncanonical request bytes")

    with pytest.raises(AthenaWorkflowExecutionError, match="noncanonical"):
        execute_persisted_request(
            request_path=request_path,
            output_root=tmp_path / "runs",
            expected_git_sha=FIXED_COMMIT,
            expected_git_ref="refs/heads/main",
            service=MustNotRunService(),  # type: ignore[arg-type]
            git_head_provider=lambda: FIXED_COMMIT,
        )


def test_execution_transport_does_not_reparse_dates_or_include_business_or_notification_logic():
    source = (ROOT / "scripts/execute_athena_run_workflow.py").read_text(encoding="utf-8")
    assert "parse_explicit_request" not in source
    assert "resolve_workflow_request" not in source
    assert "scripts.execute_current_shadow_request" not in source
    assert "send_current_shadow_email" not in source
    assert "Kelly" not in source
    assert "stake" not in source.casefold()
    assert "wager_placed is not false" in source.casefold()
    assert "place_wager" not in source


def test_hosted_offline_p42_audit_executes_schema_parity_and_network_guard():
    proof = audit._synthetic_parity_proof()
    assert proof["network_attempt_count"] == 0
    assert proof["request_bytes_identical"] is True
    assert proof["receipt_bytes_identical"] is True
    assert proof["schema_equal"] is True
    assert proof["idempotent_replay"] is True
    assert proof["manual_shadow_dispatched"] is False
    assert proof["synthetic_executor_call_count"] == 2


def test_yaml_contract_uses_github_actions_on_key_and_exact_transport_policy():
    contract = audit._workflow_contract(audit._load_workflow())
    workflow = contract["workflow"]
    assert workflow["name"] == "ATHENA Canonical Run"
    assert contract["triggers"] == ["schedule", "workflow_dispatch"]
    assert contract["cron"] == "0 9 * * *"
    assert contract["inputs"] == ["bookie", "days", "profile", "target_legs", "target_total_odds"]
    assert contract["permissions"] == {"contents": "read", "actions": "read"}
    assert contract["job"]["timeout-minutes"] == "90"
    assert contract["concurrency_group"] == (
        "${{ github.event_name == 'workflow_dispatch' && inputs.profile == 'shadow' "
        "&& 'current-shadow-all-market' || 'athena-run-main' }}"
    )


def test_workflow_has_no_noncanonical_triggers_or_manual_sensitive_inputs():
    workflow = audit._load_workflow()
    triggers = workflow["on"]
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    input_names = set(triggers["workflow_dispatch"]["inputs"])
    assert input_names == {"days", "target_legs", "target_total_odds", "bookie", "profile"}
    assert not input_names.intersection(
        {"mode", "authority_profile", "create_share_code", "place_wager", "stake", "wallet", "login", "cookies"}
    )
    source = (ROOT / ".github/workflows/athena-run.yml").read_text(encoding="utf-8").casefold()
    assert "gmail_address" not in source
    assert "gmail_app_password" not in source
    assert "recipient_email" not in source


def test_committed_p42_receipt_hash_and_frozen_history_are_verified():
    committed = audit.verify_committed_receipt()
    assert committed["historical_file_git_blob_sha1"] == audit.verify_preserved_historical_sources()
    unsigned = dict(committed)
    stored = unsigned.pop("canonical_sha256")
    assert audit.canonical_sha256(unsigned) == stored
    assert committed["p4_2_exit_gate_satisfied"] is True
    assert committed["manual_schedule_default_request_bytes_identical"] is True
    assert committed["manual_schedule_receipt_byte_identical"] is True
    assert committed["offline_synthetic_proof"]["network_attempt_count"] == 0
    assert committed["historical_file_git_blob_sha1"] == audit.PRESERVED_FILE_GIT_BLOB_SHA1


def test_protected_and_legacy_workflows_remain_exact_base_bytes():
    for relative, expected in audit.PRESERVED_FILE_GIT_BLOB_SHA1.items():
        if relative.startswith(".github/workflows/") and relative != audit.RETIRED_WORKFLOW_PATH:
            assert audit._git_blob_sha1(relative) == expected
    assert audit.verify_preserved_historical_sources()[audit.RETIRED_WORKFLOW_PATH] == audit.PRESERVED_FILE_GIT_BLOB_SHA1[audit.RETIRED_WORKFLOW_PATH]
