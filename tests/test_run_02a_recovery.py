"""RUN-02A cancellation, startup reconciliation, and recovery tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace
import threading

import pytest

from database.run_repository import (
    DurableRunRepository,
    ExternalOperationViolation,
    MAX_TERMINAL_RECEIPT_BYTES,
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
    WORKER_COMMAND_FILENAME,
    WORKER_OFFLINE_PROBE_FILENAME,
    WORKER_PROVENANCE_FILENAME,
    WORKER_REQUEST_FILENAME,
    WorkerCommand,
    WorkerLauncher,
    WorkerProcessHandle,
    _process_group_options,
    _spawn_process,
    persist_worker_command,
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
from services.athena_read_service import ReadBackendError
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


def _product_offline_handoff(
    tmp_path, clock, monkeypatch, *, on_bind=None, before_publish=None,
    bind_failure=False,
):
    """Run the real product entry behind deterministic parent/child barriers."""
    from runtime import worker_entry, worker_startup_gate
    from services import worker_coordinator, worker_process_control
    from runtime.worker_launcher import WorkerProcessHandle

    identity, writable, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    run_id = _admit_run(repository, item, envelope, "startup-gate-run")
    request = RunRequest.from_json_bytes(item.request_bytes)
    run_directory = writable.data_root / "runs" / run_id / request.canonical_sha256
    run_directory.mkdir(parents=True)
    (run_directory / WORKER_REQUEST_FILENAME).write_bytes(item.request_bytes)
    command = WorkerCommand(
        operation="OFFLINE_IDENTITY_PROBE", mode="offline_identity_probe",
        run_directory=run_directory, request_artifact_id=request.canonical_sha256,
        envelope_artifact_id=None, release_identity_kind=identity.identity_kind,
        release_identity_id=identity.head_commit_sha,
    )

    gate_waiting = threading.Event()
    release_gate = threading.Event()
    worker_finished = threading.Event()
    handoff_finished = threading.Event()
    handoff_outcome = {}
    worker_errors = []
    launch_calls = []
    controls = []
    captured_threads = []
    real_wait_for_gate = worker_startup_gate.wait_for_gate

    def wait_at_gate(built, *, resources, **kwargs):
        gate_waiting.set()
        if not release_gate.wait(10):
            raise worker_startup_gate.StartupGateError("deterministic gate barrier was not released")
        try:
            return real_wait_for_gate(
                built, resources=resources, timeout=0.02, sleeper=lambda _seconds: None,
            )
        except worker_startup_gate.StartupGateError:
            raise

    monkeypatch.setattr(worker_startup_gate, "wait_for_gate", wait_at_gate)

    def run_worker():
        try:
            worker_entry.execute_worker_command(
                command_file=run_directory / WORKER_COMMAND_FILENAME,
                development_root=identity.repository_root,
            )
        except BaseException as exc:
            worker_errors.append(exc)
        finally:
            worker_finished.set()

    def synthetic_launch(_launcher, built):
        launch_calls.append(built)
        persist_worker_command(built)
        threading.Thread(target=run_worker, name="product-offline-probe-test").start()
        if not gate_waiting.wait(10):
            raise AssertionError("product child did not reach the deterministic gate barrier")
        return WorkerProcessHandle(_MockChild(os.getpid(), exit_code=None))

    monkeypatch.setattr(WorkerLauncher, "launch", synthetic_launch)

    class DeferredThread:
        def __init__(self, *, target, kwargs, **options):
            captured_threads.append((target, kwargs, options))

        def start(self):
            return None

    class SyntheticControl:
        def __init__(self, handle, owner):
            self.handle = handle
            self.owner = owner
            self.locator = None
            self.abort_count = 0
            controls.append(self)

        def bind(self):
            if on_bind is not None:
                on_bind(repository, run_id)
            if bind_failure:
                raise worker_process_control.ProcessControlError("injected exact bind failure")
            pid = self.handle.pid
            if os.name == "nt":
                self.locator = {
                    "kind": "WINDOWS_PROCESS_GROUP", "pid": pid,
                    "creation_time": 1, "job_name": "Local\\ATHENA-E3-test",
                    **self.owner,
                }
            else:
                self.locator = {
                    "kind": "POSIX_PROCESS_GROUP", "pid": pid, "pgid": pid,
                    "session_id": pid, "start_ticks": 1, **self.owner,
                }
            return dict(self.locator)

        def state(self, locator, owner):
            return "ACTIVE" if locator == self.locator and owner == self.owner else "UNKNOWN"

        def abort_before_start(self):
            self.abort_count += 1

        def close(self):
            return None

        def request_cancel(self, locator):
            return False

    monkeypatch.setattr(worker_coordinator, "WorkerProcessControl", SyntheticControl)
    monkeypatch.setattr(
        worker_process_control.WorkerProcessControl,
        "state",
        staticmethod(lambda locator, owner: "ACTIVE" if all(
            locator.get(key) == value for key, value in owner.items()
        ) else "UNKNOWN"),
    )
    if before_publish is not None:
        original_publish = repository.publish_worker_startup_gate

        def publish_with_boundary(**kwargs):
            before_publish(repository, run_id)
            return original_publish(**kwargs)

        monkeypatch.setattr(repository, "publish_worker_startup_gate", publish_with_boundary)

    coordinator = WorkerCoordinator(
        repository, WorkerLauncher.for_development(identity), writable,
        thread_factory=DeferredThread,
    )

    def handoff():
        try:
            handoff_outcome["value"] = coordinator.handoff(
                run_id, worker_instance_id="startup-gate-test",
                process_label="offline-probe",
                command_factory=lambda *_: command,
            )
        except BaseException as exc:
            handoff_outcome["error"] = exc
        finally:
            handoff_finished.set()

    threading.Thread(target=handoff, name="product-offline-handoff-test").start()
    assert gate_waiting.wait(10), "worker launch did not pause at the deterministic gate boundary"
    assert handoff_finished.wait(10), "coordinator did not finish the bounded handoff"
    assert "error" not in handoff_outcome, repr(handoff_outcome.get("error"))
    return {
        "identity": identity,
        "roots": writable,
        "repository": repository,
        "run_id": run_id,
        "request": request,
        "command": command,
        "gate_path": run_directory / worker_startup_gate.FILENAME,
        "coordinator": coordinator,
        "handoff_outcome": handoff_outcome,
        "launch_calls": launch_calls,
        "controls": controls,
        "worker_errors": worker_errors,
        "worker_finished": worker_finished,
        "release_gate": release_gate,
        "captured_threads": captured_threads,
    }


def _assert_no_offline_worker_evidence(case):
    directory = case["command"].run_directory
    assert not (directory / WORKER_OFFLINE_PROBE_FILENAME).exists()
    assert not (directory / WORKER_PROVENANCE_FILENAME).exists()
    assert case["repository"].run_snapshot(case["run_id"])["receipt_artifact_id"] is None


def test_cancel_queued_run_settles_immediately(tmp_path, clock, monkeypatch):
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
    launched = []
    monkeypatch.setattr(WorkerLauncher, "launch", lambda self, command: launched.append(command))
    coordinator = WorkerCoordinator(
        repository, WorkerLauncher.for_development(_identity), roots
    )
    assert coordinator.handoff(
        run_id,
        worker_instance_id="inst-1",
        process_label="test-label",
        command_factory=lambda *_: pytest.fail("should not build command"),
    ) is False
    assert launched == []
    assert not (roots.data_root / "runs" / run_id).exists()


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


def test_product_offline_probe_waits_for_exact_owned_gate_before_both_artifacts(
    tmp_path, clock, monkeypatch,
):
    case = _product_offline_handoff(tmp_path, clock, monkeypatch)
    assert case["handoff_outcome"]["value"] is True
    assert case["gate_path"].is_file()
    _assert_no_offline_worker_evidence(case)

    case["release_gate"].set()
    assert case["worker_finished"].wait(10)
    assert case["worker_errors"] == []
    directory = case["command"].run_directory
    assert (directory / WORKER_OFFLINE_PROBE_FILENAME).is_file()
    assert (directory / WORKER_PROVENANCE_FILENAME).is_file()
    events = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert events.count("WORKER_STARTUP_GATE_PUBLISHED") == 1
    assert events.count("WORKER_STARTUP_EFFECT_STARTED") == 1


def test_cancel_after_launch_before_process_control_bind_blocks_product_probe(
    tmp_path, clock, monkeypatch,
):
    def cancel_at_bind(repository, run_id):
        repository.record_cancel_intent(run_id)

    case = _product_offline_handoff(
        tmp_path, clock, monkeypatch, on_bind=cancel_at_bind,
    )
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCEL_REQUESTED"
    assert case["handoff_outcome"]["value"] is True
    assert len(case["launch_calls"]) == 1
    assert case["controls"][0].abort_count == 1
    assert not case["gate_path"].exists()
    case["release_gate"].set()
    assert case["worker_finished"].wait(10)
    assert len(case["worker_errors"]) == 1
    assert isinstance(case["worker_errors"][0], worker_entry_error_type())
    _assert_no_offline_worker_evidence(case)
    assert "WORKER_STARTUP_EFFECT_STARTED" not in [
        event[2] for event in case["repository"].read_events(case["run_id"])
    ]


def worker_entry_error_type():
    from runtime.worker_entry import WorkerEntryError

    return WorkerEntryError


def test_cancel_after_locator_binding_before_gate_publication_fails_closed(
    tmp_path, clock, monkeypatch,
):
    def cancel_before_publish(repository, run_id):
        repository.record_cancel_intent(run_id)

    case = _product_offline_handoff(
        tmp_path, clock, monkeypatch, before_publish=cancel_before_publish,
    )
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCEL_REQUESTED"
    assert case["handoff_outcome"]["value"] is True
    assert case["controls"][0].abort_count == 1
    assert not case["gate_path"].exists()
    case["release_gate"].set()
    assert case["worker_finished"].wait(10)
    assert len(case["worker_errors"]) == 1
    assert isinstance(case["worker_errors"][0], worker_entry_error_type())
    _assert_no_offline_worker_evidence(case)
    event_types = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert "WORKER_STARTUP_GATE_PUBLISHED" not in event_types
    assert "WORKER_STARTUP_EFFECT_STARTED" not in event_types


def test_locator_bind_failure_aborts_spawned_probe_without_receipt_or_relaunch(
    tmp_path, clock, monkeypatch,
):
    case = _product_offline_handoff(
        tmp_path, clock, monkeypatch, bind_failure=True,
    )
    assert case["handoff_outcome"]["value"] is True
    assert len(case["launch_calls"]) == 1
    assert case["controls"][0].abort_count == 1
    assert not case["gate_path"].exists()
    case["release_gate"].set()
    assert case["worker_finished"].wait(10)
    assert len(case["worker_errors"]) == 1
    assert isinstance(case["worker_errors"][0], worker_entry_error_type())
    _assert_no_offline_worker_evidence(case)


def test_cancel_after_gate_read_before_atomic_start_revalidation_blocks_probe(
    tmp_path, clock, monkeypatch,
):
    case = _product_offline_handoff(tmp_path, clock, monkeypatch)
    authorization_waiting = threading.Event()
    release_authorization = threading.Event()
    original = DurableRunRepository.authorize_worker_start

    def pause_before_authorization(repository, **kwargs):
        if repository._data_root == case["roots"].data_root:
            authorization_waiting.set()
            if not release_authorization.wait(10):
                raise AssertionError("deterministic authorization barrier was not released")
        return original(repository, **kwargs)

    monkeypatch.setattr(DurableRunRepository, "authorize_worker_start", pause_before_authorization)
    case["release_gate"].set()
    assert authorization_waiting.wait(10)
    case["repository"].record_cancel_intent(case["run_id"])
    release_authorization.set()
    assert case["worker_finished"].wait(10)
    assert len(case["worker_errors"]) == 1
    assert isinstance(case["worker_errors"][0], worker_entry_error_type())
    _assert_no_offline_worker_evidence(case)
    assert "WORKER_STARTUP_EFFECT_STARTED" not in [
        event[2] for event in case["repository"].read_events(case["run_id"])
    ]


def test_atomic_offline_effect_start_orders_before_a_concurrent_cancel_fence(
    tmp_path, clock, monkeypatch,
):
    from runtime import worker_entry

    case = _product_offline_handoff(tmp_path, clock, monkeypatch)
    effect_entered = threading.Event()
    release_effect = threading.Event()
    cancel_started = threading.Event()
    cancel_finished = threading.Event()
    original_probe = worker_entry._run_offline_probe

    def paused_probe(command, identity):
        effect_entered.set()
        if not release_effect.wait(10):
            raise AssertionError("deterministic offline-effect barrier was not released")
        return original_probe(command, identity)

    monkeypatch.setattr(worker_entry, "_run_offline_probe", paused_probe)
    case["release_gate"].set()
    assert effect_entered.wait(10)

    def cancel_while_effect_transaction_is_open():
        cancel_started.set()
        case["repository"].record_cancel_intent(case["run_id"])
        cancel_finished.set()

    threading.Thread(
        target=cancel_while_effect_transaction_is_open,
        name="startup-gate-cancel-race-test",
    ).start()
    assert cancel_started.wait(10)
    release_effect.set()
    assert case["worker_finished"].wait(10)
    assert cancel_finished.wait(10)
    assert case["worker_errors"] == []

    events = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert events.index("WORKER_STARTUP_EFFECT_STARTED") < events.index("RUN_CANCEL_REQUESTED")
    assert (case["command"].run_directory / WORKER_OFFLINE_PROBE_FILENAME).is_file()
    assert (case["command"].run_directory / WORKER_PROVENANCE_FILENAME).is_file()
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCEL_REQUESTED"


@pytest.mark.parametrize(
    "mutation",
    (
        "missing", "attempt", "lease", "stale_pid", "old_release",
        "forged_authenticator", "cross_run", "noncanonical_bytes", "symlink",
    ),
)
def test_startup_gate_mutations_are_typed_fail_closed_without_probe_artifacts(
    tmp_path, clock, monkeypatch, mutation,
):
    from domain.run_contracts import canonical_json_bytes

    case = _product_offline_handoff(tmp_path, clock, monkeypatch)
    path = case["gate_path"]
    if mutation == "missing":
        path.unlink()
    elif mutation == "symlink":
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path, "is_symlink",
            lambda candidate: True if candidate == path else original_is_symlink(candidate),
        )
    elif mutation == "noncanonical_bytes":
        path.write_bytes(b"{\"forged\":true}\n")
    else:
        value = json.loads(path.read_bytes())
        if mutation == "attempt":
            value["attempt_id"] = "attempt-cross-owner"
        elif mutation == "lease":
            value["lease_sha256"] = "a" * 64
        elif mutation == "stale_pid":
            value["pid"] = os.getpid() + 1000
            value["process_locator"]["pid"] = value["pid"]
        elif mutation == "old_release":
            value["release_identity_id"] = "0" * 40
        elif mutation == "forged_authenticator":
            value["authenticator_sha256"] = "f" * 64
        elif mutation == "cross_run":
            value["run_id"] = "run-cross-boundary"
        path.write_bytes(canonical_json_bytes(value))

    case["release_gate"].set()
    assert case["worker_finished"].wait(10)
    assert len(case["worker_errors"]) == 1
    assert isinstance(case["worker_errors"][0], worker_entry_error_type())
    _assert_no_offline_worker_evidence(case)
    assert "WORKER_STARTUP_EFFECT_STARTED" not in [
        event[2] for event in case["repository"].read_events(case["run_id"])
    ]


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


def test_cancel_and_terminal_receipt_publication_are_transactionally_ordered(
    tmp_path, clock, monkeypatch,
):
    from test_run_01b_worker_lifecycle import _terminal_case

    pending_root = tmp_path / "pending-first"
    pending_root.mkdir()
    coordinator, repository, run_id, envelope, monitor_info, _launches, command, _inner = _terminal_case(
        pending_root, clock, monkeypatch,
    )
    _monitor, kwargs = monitor_info
    receipt, _policy_path, _inner_path = coordinator._build_shadow_receipt(
        run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"],
        envelope=envelope, snapshot=kwargs["snapshot"], command=command,
    )
    digest = repository.publish_terminal_receipt(
        run_id, receipt_bytes=canonical_json_bytes(receipt), expected_version=1,
        attempt_id=kwargs["attempt_id"], lease_token=kwargs["lease_token"],
    )
    adapter = DurableCancelAdapter(repository)
    before_events = repository.read_events(run_id)
    with pytest.raises(ReadBackendError, match="CANCEL_STORE_UNAVAILABLE"):
        adapter.request_cancel(run_id)
    assert repository.run_snapshot(run_id)["state"] == "RUNNING"
    assert repository.run_snapshot(run_id)["state_version"] == 1
    assert repository.read_events(run_id) == before_events
    assert repository.list_pending_terminal_receipts()[0]["receipt_sha256"] == digest
    assert repository.project_terminal_receipt(digest) is True
    terminal = adapter.request_cancel(run_id)
    assert terminal.disposition == "already_terminal"
    assert terminal.state == "TERMINAL"

    cancel_first_root = tmp_path / "cancel-first"
    cancel_first_root.mkdir()
    coordinator, repository, run_id, envelope, monitor_info, _launches, command, _inner = _terminal_case(
        cancel_first_root, clock, monkeypatch,
    )
    _monitor, kwargs = monitor_info
    receipt, _policy_path, _inner_path = coordinator._build_shadow_receipt(
        run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"],
        envelope=envelope, snapshot=kwargs["snapshot"], command=command,
    )
    requested = DurableCancelAdapter(repository).request_cancel(run_id)
    assert requested.disposition == "requested"
    assert requested.state == "CANCEL_REQUESTED"
    with pytest.raises(RunStateConflict, match="receipt state CAS rejected"):
        repository.publish_terminal_receipt(
            run_id, receipt_bytes=canonical_json_bytes(receipt), expected_version=1,
            attempt_id=kwargs["attempt_id"], lease_token=kwargs["lease_token"],
        )
    assert repository.list_pending_terminal_receipts() == []
    repository.interrupt_worker_without_receipt(
        run_id, kwargs["attempt_id"], kwargs["lease_token"], exit_code=-15,
        diagnostic_id="WORKER_EXIT_WITHOUT_VERIFIED_RECEIPT", last_proven_stage=None,
    )
    assert repository.run_snapshot(run_id)["state"] == "CANCELLED"


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


def test_terminal_receipt_projection_bounds_startup_file_reads(tmp_path, clock):
    _identity, roots, repository, _item, _envelope = _development_shadow_run(tmp_path, clock)
    raw = b"x" * (MAX_TERMINAL_RECEIPT_BYTES + 1)
    digest = hashlib.sha256(raw).hexdigest()
    target = roots.data_root / "run-receipts" / (digest + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)

    with pytest.raises(RunRepositoryError, match="exceeds its reviewed byte bound"):
        repository.project_terminal_receipt(digest)


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
