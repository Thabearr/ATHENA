"""RUN-02A cancellation, startup reconciliation, and recovery tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from database.run_repository import (
    DurableRunRepository,
    ExternalOperationViolation,
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


def test_recovery_service_reconciles_dead_attempt_without_receipt(tmp_path, clock):
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
    assert summary.reconciled_attempts == 1
    assert summary.interrupted_runs == 1
    assert summary.projected_receipts == 0
    assert summary.blocked_runs == 0

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "INTERRUPTED"

    # Repeated reconcile is idempotent
    summary2 = recovery.reconcile()
    assert summary2.reconciled_attempts == 0
    assert summary2.interrupted_runs == 0


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
    recovery = RecoveryService(repository, coordinator._roots.data_root)
    summary = recovery.reconcile()
    assert summary.reconciled_attempts == 1
    assert summary.projected_receipts == 1
    assert summary.interrupted_runs == 0
    assert summary.blocked_runs == 0

    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "TERMINAL"


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
