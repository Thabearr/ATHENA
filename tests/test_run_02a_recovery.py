"""RUN-02A cancellation, startup reconciliation, and recovery tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

import pytest

from database.run_repository import (
    DurableRunRepository,
    ExternalOperationViolation,
    ReceiptProducerUnavailable,
    RunLeaseFenced,
    RunRepositoryError,
    RunStateConflict,
    SHARE_CREATE_KIND,
)
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import RunReceipt, RunRequest, canonical_json_bytes
from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    verify_development_checkout,
)
from runtime.resources import ResourceResolver, WritableRoots
from runtime.worker_launcher import (
    WorkerCommand,
    WorkerLauncher,
    WorkerProcessHandle,
    _process_group_options,
    _spawn_process,
)
from services.athena_job_service import (
    AthenaJobService,
    CancelIntentResult,
    DurableCancelAdapter,
)
from services.athena_preview_service import (
    AdmissionCandidate,
    AthenaPreviewAdmissionService,
)
from services.recovery_service import RecoveryService, RecoverySummary
from services.worker_coordinator import WorkerCoordinator
from services.worker_process_control import WorkerProcessControl, owner_identity
from test_data_01a_app_schema import (
    ROOT,
    clock,
    open_repo,
    record_test_release,
    resources,
    roots,
)
from test_run_01b_worker_lifecycle import _development_shadow_run


class _MockChild:
    def __init__(self, pid=9999, exit_code=0):
        self.pid = pid
        self._exit_code = exit_code

    def poll(self):
        return self._exit_code


def _admit_run(repository, item, envelope, run_label="test-run"):
    candidate = AdmissionCandidate(
        item.preview_id,
        item.request_bytes,
        envelope.request_sha256,
        item.envelope_bytes,
        envelope.canonical_sha256,
        run_label,
        envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(),
        envelope.expires_at,
    )
    return repository.admit(candidate).run_id


def test_cancel_queued_run_settles_immediately(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "QUEUED"
    assert snapshot["state_version"] == 0

    disposition, state, version = repository.record_cancel_intent(run_id, expected_version=0)
    assert disposition == "requested"
    assert state == "CANCELLED"
    assert version == 1

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "CANCELLED"
    assert snapshot["state_version"] == 1

    events = repository.read_events(run_id)
    assert [e[2] for e in events] == ["RUN_QUEUED", "RUN_CANCELLED"]

    # Handoff on a cancelled run must be refused
    coordinator = WorkerCoordinator(
        repository, WorkerLauncher.for_development(_identity), roots
    )
    assert coordinator.handoff(
        run_id,
        worker_instance_id="inst-1",
        process_label="test-label",
        command_factory=lambda *_: pytest.fail("should not build command"),
    ) is False


def test_cancel_running_run_and_settlement(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)

    attempt_id, lease_token, _num = repository.claim_attempt(
        run_id, worker_instance_id="worker-1",
        process_locator={"kind": "OFFLINE_TEST", "label": "offline-worker"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "RUNNING"
    assert snapshot["state_version"] == 1

    disposition, state, version = repository.record_cancel_intent(run_id, expected_version=1)
    assert disposition == "requested"
    assert state == "CANCEL_REQUESTED"
    assert version == 2

    # Duplicate cancel on CANCEL_REQUESTED returns already_requested
    disposition2, state2, version2 = repository.record_cancel_intent(run_id)
    assert disposition2 == "already_requested"
    assert state2 == "CANCEL_REQUESTED"
    assert version2 == 2

    # Worker exits and coordinator settles without receipt
    repository.interrupt_worker_without_receipt(
        run_id, attempt_id, lease_token, exit_code=143,
        diagnostic_id="WORKER_EXIT_WITHOUT_VERIFIED_RECEIPT",
        last_proven_stage=None,
    )

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "CANCELLED"
    assert snapshot["state_version"] == 3

    events = repository.read_events(run_id)
    assert [e[2] for e in events] == [
        "RUN_QUEUED", "RUN_RUNNING", "RUN_CANCEL_REQUESTED",
        "WORKER_INTERRUPTED", "RUN_CANCELLED",
    ]

    # Repeated cancel on terminal CANCELLED returns already_terminal
    disposition3, state3, version3 = repository.record_cancel_intent(run_id)
    assert disposition3 == "already_terminal"
    assert state3 == "CANCELLED"
    assert version3 == 3


def test_cancel_version_cas_mismatch_fails_closed(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)

    with pytest.raises(RunStateConflict, match="cancellation CAS rejected"):
        repository.record_cancel_intent(run_id, expected_version=99)

    with pytest.raises(RunStateConflict, match="invalid state version"):
        repository.record_cancel_intent(run_id, expected_version=-1)


def test_cancel_forbids_external_operation_send_transition(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)

    attempt_id, lease_token, _num = repository.claim_attempt(
        run_id, worker_instance_id="worker-1",
        process_locator={"kind": "OFFLINE_TEST", "label": "offline-worker"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )

    # Prepare an external operation
    intent_sha = "1" * 64
    auth_sha = "2" * 64
    op_id = repository.prepare_external_operation(
        run_id, attempt_id=attempt_id, lease_token=lease_token,
        operation_kind="TESTING_SYNTHETIC", intent_sha256=intent_sha,
        authority_sha256=auth_sha,
    )

    # Cancel is requested
    repository.record_cancel_intent(run_id)
    assert repository.run_snapshot(run_id)["state"] == "CANCEL_REQUESTED"

    # Moving PREPARED -> SENT is strictly forbidden when run is not RUNNING
    with pytest.raises(ExternalOperationViolation, match="cancellation forbids a new send transition"):
        repository.transition_external_operation(
            run_id, op_id, attempt_id=attempt_id, lease_token=lease_token,
            expected_state="PREPARED", state="SENT",
        )

    # Reconcile settles the prepared operation to FAILED and run to CANCELLED
    repository.reconcile_dead_attempt(run_id, attempt_id, lease_token)
    assert repository.run_snapshot(run_id)["state"] == "CANCELLED"


def test_recovery_keeps_sent_operation_outcome_unknown(tmp_path, clock):
    _identity, _roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)
    attempt_id, lease_token, _number = repository.claim_attempt(
        run_id, worker_instance_id="worker-sent",
        process_locator={"kind": "OFFLINE_TEST", "label": "offline-probe"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )
    operation_id = repository.prepare_external_operation(
        run_id, attempt_id=attempt_id, lease_token=lease_token,
        operation_kind="TESTING_SYNTHETIC", intent_sha256="1" * 64,
        authority_sha256="2" * 64,
    )
    repository.transition_external_operation(
        run_id, operation_id, attempt_id=attempt_id, lease_token=lease_token,
        expected_state="PREPARED", state="SENT",
    )
    repository.record_cancel_intent(run_id)
    repository.reconcile_dead_attempt(run_id, attempt_id, lease_token)

    with repository._operation() as conn:
        state, error_code = conn.execute(
            "SELECT state,error_code FROM app_external_operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
    assert (state, error_code) == ("OUTCOME_UNKNOWN", "OFFLINE_RECOVERY")
    assert repository.run_snapshot(run_id)["state"] == "CANCELLED"
    with pytest.raises(RunLeaseFenced):
        repository.reconcile_dead_attempt(run_id, attempt_id, lease_token)


def test_recovery_service_blocks_unbound_attempt_without_receipt(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)

    attempt_id, lease_token, _num = repository.claim_attempt(
        run_id, worker_instance_id="worker-dead",
        process_locator={"kind": "OFFLINE_TEST", "label": "dead-worker"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )

    # Crash scenario: attempt left unfinished in DB
    recovery = RecoveryService(repository, roots.data_root)
    summary = recovery.reconcile()
    assert summary.reconciled_attempts == 0
    assert summary.interrupted_runs == 0
    assert summary.projected_receipts == 0
    assert summary.blocked_runs == 1

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "RUNNING"

    # An OFFLINE_TEST locator proves neither a dead process nor ownership.
    summary2 = recovery.reconcile()
    assert summary2.reconciled_attempts == 0
    assert summary2.blocked_runs == 1
    assert repository.run_snapshot(run_id)["state"] == "RUNNING"


def test_recovery_reconciles_genuinely_dead_owned_process(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)
    attempt_id, lease_token, _number = repository.claim_attempt(
        run_id, worker_instance_id="worker-dead",
        process_locator={"kind": "OFFLINE_TEST", "label": "offline-probe"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )
    owner = owner_identity(
        run_id=run_id, attempt_id=attempt_id,
        worker_instance_id="worker-dead", lease_token=lease_token,
    )
    process = _spawn_process(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        cwd=Path.cwd(), shell=False, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, **_process_group_options(),
    )
    handle = WorkerProcessHandle(process)
    control = WorkerProcessControl(handle, owner)
    try:
        locator = control.bind()
        repository.bind_process_locator(run_id, attempt_id, lease_token, locator)
        assert process.wait(timeout=5) == 0
        assert control.state_current() == "DEAD"

        summary = RecoveryService(repository, roots.data_root).reconcile()
        assert summary.reconciled_attempts == 1
        assert summary.interrupted_runs == 1
        assert summary.projected_receipts == 0
        assert summary.blocked_runs == 0
        assert repository.run_snapshot(run_id)["state"] == "INTERRUPTED"
        assert RecoveryService(repository, roots.data_root).reconcile().reconciled_attempts == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        control.close()


def test_recovery_service_repairs_from_published_receipt(tmp_path_factory, clock, monkeypatch):
    from test_run_01b_worker_lifecycle import _terminal_case

    tmp_path = tmp_path_factory.mktemp("r")
    coordinator, repository, run_id, envelope, monitor_info, launches, command, inner = _terminal_case(
        tmp_path, clock, monkeypatch,
    )
    monitor, kwargs = monitor_info

    # Build and publish receipt to disk as if written just before crash
    receipt, _, _ = coordinator._build_shadow_receipt(
        run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"],
        envelope=envelope, snapshot=kwargs["snapshot"], command=command,
    )
    raw = canonical_json_bytes(receipt)
    digest = repository.publish_terminal_receipt(
        run_id, receipt_bytes=raw, expected_version=1,
        attempt_id=kwargs["attempt_id"], lease_token=kwargs["lease_token"],
    )

    # Run state in DB is still RUNNING (version 1), simulate crash before projection
    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "RUNNING"

    # Startup reconciliation detects published receipt on disk and repairs run to TERMINAL
    pending = repository.list_pending_terminal_receipts()
    assert pending == [{
        "receipt_sha256": digest, "run_id": run_id,
        "attempt_id": kwargs["attempt_id"], "lease_token": kwargs["lease_token"],
    }]
    recovery = RecoveryService(repository, coordinator._roots.data_root)
    summary = recovery.reconcile()
    assert summary.reconciled_attempts == 1
    assert summary.projected_receipts == 1
    assert summary.interrupted_runs == 0
    assert summary.blocked_runs == 0

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "TERMINAL"
    assert repository.list_pending_terminal_receipts() == []
    terminal_events = repository.read_events(run_id)
    terminal_version = snapshot["state_version"]
    cancelled = DurableCancelAdapter(repository).request_cancel(run_id)
    assert cancelled.disposition == "already_terminal"
    assert cancelled.state == "TERMINAL"
    assert repository.run_snapshot(run_id)["state_version"] == terminal_version
    assert repository.read_events(run_id) == terminal_events


def test_terminal_receipt_attempt_binding_rejects_cross_attempt_identity(
    tmp_path_factory, clock, monkeypatch,
):
    from test_run_01b_worker_lifecycle import _terminal_case

    tmp_path = tmp_path_factory.mktemp("wrong-attempt")
    coordinator, repository, run_id, envelope, monitor_info, _launches, command, _inner = _terminal_case(
        tmp_path, clock, monkeypatch,
    )
    _monitor, kwargs = monitor_info
    receipt, _policy_path, _receipt_path = coordinator._build_shadow_receipt(
        run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"],
        envelope=envelope, snapshot=kwargs["snapshot"], command=command,
    )
    evidence = dict(receipt.evidence)
    evidence["worker_attempt_id"] = "attempt-unrelated"
    tampered = replace(receipt, evidence=evidence)

    with pytest.raises(ReceiptProducerUnavailable, match="attempt"):
        repository.publish_terminal_receipt(
            run_id, receipt_bytes=canonical_json_bytes(tampered), expected_version=1,
            attempt_id=kwargs["attempt_id"], lease_token=kwargs["lease_token"],
        )
    assert repository.run_snapshot(run_id)["state"] == "RUNNING"
    assert repository.list_pending_terminal_receipts() == []


def test_recovery_ignores_receipt_file_without_exact_database_link(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope)
    attempt_id, lease_token, _number = repository.claim_attempt(
        run_id, worker_instance_id="worker-pending",
        process_locator={"kind": "OFFLINE_TEST", "label": "offline-probe"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )
    forged = {
        "policy_id": "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1",
        "run_id": run_id, "request_sha256": envelope.request_sha256,
        "envelope_sha256": envelope.canonical_sha256,
        "release_id": "cross-run-release", "expected_version": 1,
        "attempt_id": attempt_id, "lease_token": lease_token, "receipt": {},
    }
    raw = canonical_json_bytes(forged)
    digest = hashlib.sha256(raw).hexdigest()
    target = roots.data_root / "run-receipts" / (digest + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)

    summary = RecoveryService(repository, roots.data_root).reconcile()
    assert summary.projected_receipts == 0
    assert summary.blocked_runs == 1
    assert repository.run_snapshot(run_id)["state"] == "RUNNING"
    assert repository.list_pending_terminal_receipts() == []


def test_pr459_receipt_reconstructs_v154_source_without_resealing():
    from scripts import audit_run_02a_pre_durable_share_send as audit

    result = audit.audit()
    assert result == {
        "result": "PASS",
        "canonical_sha256": audit.RETAINED_RECEIPT_SHA,
        "a2_generation": audit.RETAINED_GENERATION,
        "review_ready": False,
    }
    assert audit.RUN_02A_CURRENT_SOURCE_PREDECESSORS.keys() == {
        "database/run_repository.py", "services/athena_job_service.py",
        "scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py",
        "runtime/worker_entry.py",
    }


def test_later_a2_generation_cannot_hide_pr459_predecessor_fixture_tamper(monkeypatch):
    from scripts import audit_run_02a_pre_durable_share_send as audit

    path = audit.RUN_02A_CURRENT_SOURCE_PREDECESSORS["database/run_repository.py"][0]
    target = (audit.ROOT / path).resolve()
    original = Path.read_bytes

    def tampered(candidate):
        value = original(candidate)
        if candidate.resolve() == target:
            return value + b"# altered predecessor\n"
        return value

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(AssertionError, match="predecessor fixture drift"):
        audit.historical_prerequisite_source_bytes("database/run_repository.py")


def test_athena_job_service_cancel_and_recovery_integration(tmp_path, clock):
    _identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    resources = ResourceResolver.for_development(_identity)
    preview_service = AthenaPreviewAdmissionService(
        resources, admission_repository=repository, clock=clock,
    )

    job_service = AthenaJobService(
        preview_service, repository, WorkerLauncher.for_development(_identity), roots,
    )

    candidate = AdmissionCandidate(
        item.preview_id,
        item.request_bytes,
        envelope.request_sha256,
        item.envelope_bytes,
        envelope.canonical_sha256,
        "job-cancel-test",
        envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(),
        envelope.expires_at,
    )
    run_id = repository.admit(candidate).run_id

    # Test cancel_run on job_service
    result = job_service.cancel_run(run_id)
    assert isinstance(result, CancelIntentResult)
    assert result.disposition == "requested"
    assert result.state == "CANCELLED"

    # Test reconcile_startup
    summary = job_service.reconcile_startup()
    assert isinstance(summary, RecoverySummary)
