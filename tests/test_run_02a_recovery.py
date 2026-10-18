"""RUN-02A cancellation, startup reconciliation, and recovery tests."""
from __future__ import annotations

import hashlib
import io
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
    bind_failure=False, acquire_sources=False,
):
    """Run the real product entry behind deterministic parent/child barriers."""
    from runtime import worker_entry, worker_startup_gate
    from services import worker_coordinator, worker_process_control
    from runtime.worker_launcher import WorkerProcessHandle

    identity, writable, repository, item, envelope = _development_shadow_run(
        tmp_path, clock, acquire_sources=acquire_sources,
    )
    run_id = _admit_run(repository, item, envelope, "startup-gate-run")
    request = RunRequest.from_json_bytes(item.request_bytes)
    run_directory = writable.data_root / "runs" / run_id / request.canonical_sha256
    run_directory.mkdir(parents=True)
    (run_directory / WORKER_REQUEST_FILENAME).write_bytes(item.request_bytes)
    operation = "CURRENT_SHADOW_REQUEST" if acquire_sources else "OFFLINE_IDENTITY_PROBE"
    command = WorkerCommand(
        operation=operation,
        mode="research_shadow" if acquire_sources else "offline_identity_probe",
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


def _run_authenticated_product_authority_case(
    tmp_path, clock, monkeypatch, action, *, release_gate=True, wait=True,
):
    """Build a real admitted gate/context and replace only the child transport."""
    from runtime.current_shadow_operation_authority import (
        CurrentShadowOperationAuthority, context_path, install_product_authority,
        read_context, reset_product_authority, worker_executable_identity,
    )
    from runtime.worker_startup_gate import read_gate_document
    from scripts import execute_current_shadow_request

    case = _product_offline_handoff(
        tmp_path, clock, monkeypatch, acquire_sources=True,
    )
    captured = {}

    class BlockedSyntheticChild:
        def __init__(self):
            self.pid = os.getpid()
            self.stdin = io.BytesIO()

        def poll(self):
            return None

        def kill(self):
            return None

        def wait(self, timeout=None):
            return 0

    def run_authenticated(_argv, *, repository, command, gate, gate_bytes):
        # The subprocess seam is synthetic, so model the child's PPID as the
        # owning process while retaining this process's actual creation identity.
        monkeypatch.setattr(os, "getppid", lambda: gate["pid"])
        executable, executable_sha = worker_executable_identity()
        process = repository.launch_current_shadow_supervisor(
            command=command,
            gate=gate,
            gate_bytes=gate_bytes,
            launch=lambda _context_path: BlockedSyntheticChild(),
            worker_executable_path=executable,
            worker_executable_sha256=executable_sha,
        )
        context_file = context_path(command)
        context, context_bytes = read_context(context_file, command=command)
        stored_gate, stored_gate_bytes = read_gate_document(case["gate_path"])
        assert stored_gate == gate and stored_gate_bytes == gate_bytes
        authority = CurrentShadowOperationAuthority._from_authenticated_child(
            repository=repository, command=command, gate=gate,
            gate_bytes=gate_bytes, context=context, context_bytes=context_bytes,
        )
        captured.update(process=process, context=context, authority=authority)
        token = install_product_authority(authority)
        try:
            try:
                captured["result"] = action(authority, repository, command, gate)
            except BaseException as exc:
                captured["error"] = exc
        finally:
            reset_product_authority(token)
        return 0

    monkeypatch.setattr(
        execute_current_shadow_request, "run_authenticated_product_worker", run_authenticated,
    )
    if release_gate:
        case["release_gate"].set()
    if wait:
        assert case["worker_finished"].wait(10)
        assert case["worker_errors"] == []
        assert "authority" in captured
        assert "CURRENT_SHADOW_SUPERVISOR_STARTED" in [
            event[2] for event in case["repository"].read_events(case["run_id"])
        ]
    return case, captured


def _fotmob_get(authority, request_date):
    from domain.fotmob_data_matches_capture import MAX_RESPONSE_BYTES
    from scripts.capture_fotmob_data_matches import (
        REQUEST_HEADERS, REQUEST_TIMEOUT_SECONDS, request_target,
    )

    return authority.perform_get(
        provider="FOTMOB_DATA_MATCHES",
        request_target=request_target(request_date, "UTC", "NGA"),
        logical_id=request_date,
        headers=tuple(REQUEST_HEADERS),
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        maximum_bytes=MAX_RESPONSE_BYTES,
    )


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


def test_cancel_after_gate_commit_before_gate_file_publication_cannot_start_worker(
    tmp_path, clock, monkeypatch,
):
    from runtime import worker_startup_gate

    gate_event_committed = threading.Event()
    cancel_committed = threading.Event()
    allow_gate_file = threading.Event()
    original_publish_gate = worker_startup_gate.publish_gate

    def pause_after_gate_event(path, raw):
        gate_event_committed.set()
        if not allow_gate_file.wait(10):
            raise AssertionError("gate-file publication barrier was not released")
        return original_publish_gate(path, raw)

    monkeypatch.setattr(worker_startup_gate, "publish_gate", pause_after_gate_event)

    def cancel_after_gate_event(repository, run_id):
        cancel_repository = DurableRunRepository.for_worker_data_root(
            ResourceResolver.for_development(repository.verified_identity), repository._data_root,
        )

        def commit_cancel():
            if not gate_event_committed.wait(10):
                raise AssertionError("startup gate event did not reach the file boundary")
            cancel_repository.record_cancel_intent(run_id)
            cancel_committed.set()
            allow_gate_file.set()

        threading.Thread(target=commit_cancel, name="cancel-after-gate-event-test").start()

    case = _product_offline_handoff(
        tmp_path, clock, monkeypatch, before_publish=cancel_after_gate_event,
    )

    assert cancel_committed.is_set()
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCEL_REQUESTED"
    # The gate file may become visible after cancellation. Its matching durable
    # event is not a start permit; the child's DB start transaction must reject it.
    assert case["gate_path"].is_file()
    case["release_gate"].set()
    assert case["worker_finished"].wait(10)
    assert len(case["worker_errors"]) == 1
    assert isinstance(case["worker_errors"][0], worker_entry_error_type())
    _assert_no_offline_worker_evidence(case)
    event_types = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert "WORKER_STARTUP_GATE_PUBLISHED" in event_types
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


def test_current_shadow_cancel_after_startup_commit_blocks_supervisor_start(
    tmp_path, clock, monkeypatch,
):
    """Cancellation after startup authorization prevents the nested Popen boundary."""
    from scripts import execute_current_shadow_request

    case = _product_offline_handoff(
        tmp_path, clock, monkeypatch, acquire_sources=True,
    )
    startup_committed = threading.Event()
    release_supervisor = threading.Event()
    supervisor_starts = []
    original_authorize = DurableRunRepository.authorize_worker_start

    def pause_after_startup_commit(repository, **kwargs):
        result = original_authorize(repository, **kwargs)
        if (repository._data_root == case["roots"].data_root
                and kwargs["command"].operation == "CURRENT_SHADOW_REQUEST"):
            startup_committed.set()
            if not release_supervisor.wait(10):
                raise AssertionError("deterministic supervisor barrier was not released")
        return result

    monkeypatch.setattr(
        DurableRunRepository, "authorize_worker_start", pause_after_startup_commit,
    )
    original_popen = execute_current_shadow_request.subprocess.Popen

    def record_supervisor_popen(*args, **kwargs):
        argv = args[0] if args else kwargs.get("args", ())
        if (type(argv) in {list, tuple}
                and "-m" in argv
                and execute_current_shadow_request.WORKER_MODULE in argv):
            supervisor_starts.append((args, kwargs))
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(execute_current_shadow_request.subprocess, "Popen", record_supervisor_popen)
    case["release_gate"].set()
    assert startup_committed.wait(10)

    # A distinct repository instance ensures cancellation commits through an
    # independent SQLite connection while the worker is paused post-commit.
    cancel_repository = DurableRunRepository.for_worker_data_root(
        ResourceResolver.for_development(case["identity"]), case["roots"].data_root,
    )
    disposition, state, _version = cancel_repository.record_cancel_intent(case["run_id"])
    assert disposition == "requested"
    assert state == "CANCEL_REQUESTED"
    release_supervisor.set()

    assert case["worker_finished"].wait(10)
    assert len(case["worker_errors"]) == 1
    assert isinstance(case["worker_errors"][0], worker_entry_error_type())
    assert supervisor_starts == []
    assert not (case["command"].run_directory / "athena-current-shadow-operation-context.json").exists()
    assert "CURRENT_SHADOW_SUPERVISOR_STARTED" not in [
        event[2] for event in case["repository"].read_events(case["run_id"])
    ]
    assert "CURRENT_SHADOW_GET_SENT" not in [
        event[2] for event in case["repository"].read_events(case["run_id"])
    ]


def test_product_worker_selector_without_context_fails_closed_but_explicit_research_route_remains(
    tmp_path, monkeypatch,
):
    from scripts import execute_current_shadow_request

    monkeypatch.setenv(execute_current_shadow_request.WORKER_ENV, "1")
    argv = ["--target-size", "3", "--create-share-code", "false",
            "--output-dir", str(tmp_path / "legacy")]
    with pytest.raises(RuntimeError, match="requires authenticated product context"):
        execute_current_shadow_request.main(argv)

    seen = []
    monkeypatch.setattr(
        execute_current_shadow_request, "_execute_worker",
        lambda args, **kwargs: seen.append((args, kwargs)) or 17,
    )
    assert execute_current_shadow_request.main(
        argv + [execute_current_shadow_request.STANDALONE_RESEARCH_WORKER_ARGUMENT]
    ) == 17
    assert len(seen) == 1
    assert seen[0][1] == {}


def test_product_provider_get_rejects_cancel_before_prepared_and_out_of_request_date(
    tmp_path, clock, monkeypatch,
):
    from runtime.current_shadow_operation_authority import ProductOperationAuthorityError
    from runtime.resources import ResourceResolver
    from database.run_repository import DurableRunRepository

    calls = []
    monkeypatch.setattr(
        "runtime.current_shadow_operation_authority._fixed_provider_get",
        lambda intent: calls.append(intent),
    )

    def cancel_then_get(authority, repository, _command, gate):
        cancel_repository = DurableRunRepository.for_worker_data_root(
            ResourceResolver.for_development(repository.verified_identity), repository._data_root,
        )
        cancel_repository.record_cancel_intent(gate["run_id"])
        return _fotmob_get(authority, "20300101")

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, cancel_then_get,
    )
    assert isinstance(captured.get("error"), RunStateConflict)
    assert calls == []
    types = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert "CURRENT_SHADOW_GET_PREPARED" not in types
    assert "CURRENT_SHADOW_GET_SENT" not in types

    def wrong_date(authority, _repository, _command, _gate):
        return _fotmob_get(authority, "20300102")

    case2, captured2 = _run_authenticated_product_authority_case(
        tmp_path / "wrong-date", clock, monkeypatch, wrong_date,
    )
    assert isinstance(captured2.get("error"), ProductOperationAuthorityError)
    assert calls == []
    assert "CURRENT_SHADOW_GET_PREPARED" not in [
        event[2] for event in case2["repository"].read_events(case2["run_id"])
    ]


def test_duplicate_product_logical_get_cannot_gain_a_second_permit(
    tmp_path, clock, monkeypatch,
):
    from runtime.current_shadow_operation_authority import ProviderGetResponse

    calls = []
    monkeypatch.setattr(
        "runtime.current_shadow_operation_authority._fixed_provider_get",
        lambda intent: calls.append(intent) or ProviderGetResponse(
            body=b"{}", status=200, observed_at="2030-01-01T00:00:00.000000Z",
            content_type="application/json", content_length=2, content_length_header="2",
        ),
    )

    def duplicate(authority, *_args):
        first = _fotmob_get(authority, "20300101")
        with pytest.raises(ExternalOperationViolation, match="already consumed"):
            _fotmob_get(authority, "20300101")
        return first

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, duplicate,
    )
    assert captured["result"].body == b"{}"
    assert len(calls) == 1
    event_types = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert event_types.count("CURRENT_SHADOW_GET_PREPARED") == 1
    assert event_types.count("CURRENT_SHADOW_GET_SENT") == 1


def test_product_github_artifact_redirect_is_a_second_secret_free_get_permit(
    tmp_path, clock, monkeypatch,
):
    from runtime import current_shadow_operation_authority as authority_module
    from runtime.current_shadow_operation_authority import ProviderGetResponse

    signed_location = (
        "https://release-assets.githubusercontent.com/download/object.zip"
        "?sig=private-signed-query"
    )
    raw_zip = b"synthetic-github-artifact-zip"
    redirect = ProviderGetResponse(
        body=b"", status=302, observed_at="2030-01-01T00:00:00.000000Z",
        content_type="application/json", content_length=0,
        content_length_header="0", location=signed_location,
    )
    transport_calls = []
    requests = []
    headers_seen = []

    class SyntheticResponse:
        status = 200

        def __init__(self):
            self._body = io.BytesIO(raw_zip)

        def read(self, count=-1):
            return self._body.read(count)

        def getheader(self, name):
            return {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(raw_zip)),
                "Location": None,
            }.get(name)

    class SyntheticConnection:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def putrequest(self, method, target, **kwargs):
            requests.append((self.host, method, target, kwargs))

        def putheader(self, name, value):
            headers_seen.append((name, value))

        def endheaders(self):
            return None

        def getresponse(self):
            return SyntheticResponse()

        def close(self):
            return None

    original_transport = authority_module._fixed_provider_get

    def synthetic_transport(intent, **kwargs):
        transport_calls.append((intent["provider"], kwargs.get("transport_target")))
        if intent["provider"] == authority_module.GITHUB_LINEAGE_ARTIFACT_ZIP:
            return redirect
        return original_transport(intent, **kwargs)

    monkeypatch.setenv("GH_TOKEN", "local-github-token-must-not-be-retained")
    monkeypatch.setattr(authority_module, "_fixed_provider_get", synthetic_transport)
    monkeypatch.setattr(authority_module.http.client, "HTTPSConnection", SyntheticConnection)

    def download(authority, *_args):
        return authority.github_lineage_binary(
            request_target="/repos/Thabearr/ATHENA/actions/artifacts/123/zip",
            accept="application/vnd.github+json",
        )

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, download,
    )

    assert captured["result"] == raw_zip
    assert [provider for provider, _target in transport_calls] == [
        authority_module.GITHUB_LINEAGE_ARTIFACT_ZIP,
        authority_module.GITHUB_LINEAGE_REDIRECT_BINARY,
    ]
    assert requests == [(
        "release-assets.githubusercontent.com", "GET",
        "/download/object.zip?sig=private-signed-query",
        {"skip_accept_encoding": True},
    )]
    assert not any(name.casefold() == "authorization" for name, _value in headers_seen)
    with case["repository"]._operation() as conn:
        operations = conn.execute(
            "SELECT state FROM app_external_operations WHERE run_id=? ORDER BY prepared_at,operation_id",
            (case["run_id"],),
        ).fetchall()
        artifact_paths = conn.execute(
            "SELECT a.logical_path FROM app_artifacts a JOIN app_run_artifacts r "
            "ON r.artifact_id=a.artifact_id WHERE r.run_id=?",
            (case["run_id"],),
        ).fetchall()
    assert [row[0] for row in operations] == ["CONFIRMED", "CONFIRMED"]
    retained = b"\n".join(
        (case["roots"].data_root / row[0]).read_bytes() for row in artifact_paths
    )
    assert signed_location.encode("ascii") not in retained
    assert b"private-signed-query" not in retained
    assert b"local-github-token-must-not-be-retained" not in retained


def test_product_github_redirect_cancellation_blocks_the_followup_get(
    tmp_path, clock, monkeypatch,
):
    from runtime import current_shadow_operation_authority as authority_module
    from runtime.current_shadow_operation_authority import ProviderGetResponse
    from runtime.resources import ResourceResolver
    from database.run_repository import DurableRunRepository

    transport_calls = []
    owner = {}
    redirect = ProviderGetResponse(
        body=b"", status=302, observed_at="2030-01-01T00:00:00.000000Z",
        content_type="application/json", content_length=0,
        content_length_header="0",
        location=("https://release-assets.githubusercontent.com/download/object.zip"
                  "?sig=cancelled-query"),
    )

    def cancel_after_parent_get(intent):
        transport_calls.append(intent["provider"])
        assert intent["provider"] == authority_module.GITHUB_LINEAGE_ARTIFACT_ZIP
        cancel_repository = DurableRunRepository.for_worker_data_root(
            ResourceResolver.for_development(owner["identity"]), owner["data_root"],
        )
        cancel_repository.record_cancel_intent(owner["run_id"])
        return redirect

    monkeypatch.setenv("GH_TOKEN", "local-github-token")
    monkeypatch.setattr(
        authority_module, "_fixed_provider_get", cancel_after_parent_get,
    )

    def cancel_between_hops(authority, repository, _command, gate):
        owner.update(
            identity=repository.verified_identity,
            data_root=repository._data_root,
            run_id=gate["run_id"],
        )
        return authority.github_lineage_binary(
            request_target="/repos/Thabearr/ATHENA/actions/artifacts/123/zip",
            accept="application/vnd.github+json",
        )

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, cancel_between_hops,
    )

    assert isinstance(captured.get("error"), RunStateConflict)
    assert transport_calls == [authority_module.GITHUB_LINEAGE_ARTIFACT_ZIP]
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCEL_REQUESTED"
    with case["repository"]._operation() as conn:
        rows = conn.execute(
            "SELECT state FROM app_external_operations WHERE run_id=?",
            (case["run_id"],),
        ).fetchall()
    assert rows == [("CONFIRMED",)]
    event_types = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert event_types.count("CURRENT_SHADOW_GET_PREPARED") == 1
    assert event_types.count("CURRENT_SHADOW_GET_SENT") == 1
    assert "CURRENT_SHADOW_GET_RESPONSE_RETAINED" in event_types


def test_product_github_unapproved_redirect_host_is_never_contacted(
    tmp_path, clock, monkeypatch,
):
    from runtime import current_shadow_operation_authority as authority_module
    from runtime.current_shadow_operation_authority import (
        ProductOperationAuthorityError, ProviderGetResponse,
    )

    transport_calls = []

    def fake_github_response(intent):
        transport_calls.append(intent["provider"])
        return ProviderGetResponse(
            body=b"", status=302, observed_at="2030-01-01T00:00:00.000000Z",
            content_type="application/json", content_length=0,
            content_length_header="0",
            location="https://unapproved.example/download.zip?sig=private-query",
        )

    monkeypatch.setenv("GH_TOKEN", "local-github-token")
    monkeypatch.setattr(
        authority_module, "_fixed_provider_get", fake_github_response,
    )

    def attempt_download(authority, *_args):
        with pytest.raises(ProductOperationAuthorityError):
            authority.github_lineage_binary(
                request_target="/repos/Thabearr/ATHENA/actions/artifacts/123/zip",
                accept="application/vnd.github+json",
            )

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, attempt_download,
    )

    assert captured["result"] is None
    assert transport_calls == [authority_module.GITHUB_LINEAGE_ARTIFACT_ZIP]
    with case["repository"]._operation() as conn:
        rows = conn.execute(
            "SELECT state,error_code FROM app_external_operations WHERE run_id=?",
            (case["run_id"],),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "OUTCOME_UNKNOWN"
    assert "unapproved.example" not in b"".join(
        path.read_bytes() for path in case["roots"].data_root.rglob("*")
        if path.is_file()
    ).decode("latin-1")


def test_product_fotmob_pc_upcoming_and_event_sources_share_the_get_port(
    tmp_path, clock, monkeypatch,
):
    from runtime import current_shadow_operation_authority as authority_module
    from runtime.current_shadow_operation_authority import ProviderGetResponse
    from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_source
    from domain import sportybet_live_event_quote_evidence as event_source
    from scripts import capture_fotmob_data_matches as fotmob_source
    from datetime import datetime, timezone

    calls = []

    def synthetic_transport(intent):
        calls.append(intent)
        return ProviderGetResponse(
            body=b"{}", status=200, observed_at="2030-01-01T00:00:00.000000Z",
            content_type="application/json", content_length=2,
            content_length_header="2",
        )

    monkeypatch.setattr(
        authority_module, "_fixed_provider_get", synthetic_transport,
    )

    def acquire_through_sources(authority, *_args):
        date = authority._context["allowed_dates"][0]
        fotmob_source.fetch_fotmob_data_matches(
            request_date=date, timezone="UTC", ccode3="NGA",
        )
        nonce = int(datetime.now(timezone.utc).timestamp() * 1000)
        pc_source._fetch_page(1, nonce, operation_epoch=1)
        event_source._network_fetch("sr:match:123456789")
        return tuple(call["provider"] for call in calls)

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, acquire_through_sources,
    )

    assert captured["result"] == (
        "FOTMOB_DATA_MATCHES", "SPORTYBET_PC_UPCOMING", "SPORTYBET_EVENT_DETAIL",
    )
    with case["repository"]._operation() as conn:
        operations = conn.execute(
            "SELECT state FROM app_external_operations WHERE run_id=?",
            (case["run_id"],),
        ).fetchall()
    assert operations == [("CONFIRMED",), ("CONFIRMED",), ("CONFIRMED",)]
    events = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert events.count("CURRENT_SHADOW_GET_PREPARED") == 3
    assert events.count("CURRENT_SHADOW_GET_SENT") == 3
    assert events.count("CURRENT_SHADOW_GET_RESPONSE_RETAINED") == 3


def test_product_pc_capture_uses_authenticated_epoch_and_cancel_blocks_next_page(
    tmp_path, clock, monkeypatch,
):
    from datetime import datetime, timezone
    from runtime.current_shadow_operation_authority import ProviderGetResponse
    from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_source
    from runtime.current_shadow_operation_authority import ProductOperationAuthorityError

    intents = []
    body = json.dumps({
        "bizCode": 10000,
        "data": {
            "totalNum": 101,
            "tournaments": [{
                "id": "sr:tournament:242",
                "name": "Synthetic League",
                "categoryId": "sr:category:26",
                "categoryName": "Synthetic",
                "events": [{
                    "eventId": "sr:match:99000000001",
                    "homeTeamId": "sr:competitor:88000000002",
                    "homeTeamName": "Synthetic Home",
                    "awayTeamId": "sr:competitor:88000000003",
                    "awayTeamName": "Synthetic Away",
                    "estimateStartTime": 1893585600000,
                    "status": 0,
                    "matchStatus": "Not start",
                    "bookingStatus": "Booked",
                }],
            }],
        },
    }, separators=(",", ":")).encode("utf-8")

    def synthetic_transport(intent):
        intents.append(intent)
        return ProviderGetResponse(
            body=body, status=200,
            observed_at=datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            content_type="application/json", content_length=len(body),
            content_length_header=str(len(body)),
        )

    monkeypatch.setattr(
        "runtime.current_shadow_operation_authority._fixed_provider_get",
        synthetic_transport,
    )

    def capture_one_epoch(authority, repository, command, gate):
        def cancel_after_first_page(page):
            assert page.page_num == 1
            repository.record_cancel_intent(gate["run_id"])

        with pytest.raises((ProductOperationAuthorityError, RunStateConflict)):
            pc_source._capture_current_pc_upcoming_discovery_once(
                evidence_root=command.run_directory / "pc-upcoming-race-test",
                execute_live_network=True,
                operation_epoch=1,
                page_observer=cancel_after_first_page,
            )
        return tuple(intent["logical_id"] for intent in intents)

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, capture_one_epoch,
    )

    assert "error" not in captured, captured.get("error")
    assert captured["result"] == ("epoch:1:page:1",)
    assert len(intents) == 1
    assert intents[0]["provider"] == "SPORTYBET_PC_UPCOMING"
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCELLED"
    with case["repository"]._operation() as conn:
        operations = conn.execute(
            "SELECT state FROM app_external_operations WHERE run_id=?",
            (case["run_id"],),
        ).fetchall()
    assert operations == [("CONFIRMED",)]


def test_product_pc_capture_requires_epoch_before_any_provider_get(
    tmp_path, clock, monkeypatch,
):
    from runtime.current_shadow_operation_authority import ProviderGetResponse
    from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_source

    calls = []
    monkeypatch.setattr(
        "runtime.current_shadow_operation_authority._fixed_provider_get",
        lambda intent: calls.append(intent) or ProviderGetResponse(
            body=b"{}", status=200, observed_at="2030-01-01T00:00:00.000000Z",
            content_type="application/json", content_length=2,
            content_length_header="2",
        ),
    )

    def capture_without_epoch(_authority, _repository, command, _gate):
        with pytest.raises(pc_source.PcUpcomingDiscoveryError, match="bounded epoch"):
            pc_source._capture_current_pc_upcoming_discovery_once(
                evidence_root=command.run_directory / "pc-upcoming-no-epoch-test",
                execute_live_network=True,
            )
        return True

    _case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, capture_without_epoch,
    )
    assert captured["result"] is True
    assert calls == []


def test_product_pr151_lineage_readers_route_every_github_get_through_authority(
    tmp_path, clock, monkeypatch,
):
    from runtime import current_shadow_operation_authority as authority_module
    from runtime.current_shadow_operation_authority import (
        ProductOperationAuthorityError, ProviderGetResponse,
    )
    from domain import current_fotmob_latest_durable_fresh_history as history

    calls = []

    def synthetic_transport(intent):
        calls.append((intent["provider"], intent["request_target"]))
        body = b"github-artifact-bytes" if intent["provider"] in {
            authority_module.GITHUB_LINEAGE_ARTIFACT_ZIP,
            authority_module.GITHUB_LINEAGE_RELEASE_ASSET,
        } else b"{}"
        return ProviderGetResponse(
            body=body, status=200, observed_at="2030-01-01T00:00:00.000000Z",
            content_type="application/json", content_length=len(body),
            content_length_header=str(len(body)),
        )

    def call_all_readers(**kwargs):
        result = {
            "main": kwargs["get_main_ref"](),
            "runs": kwargs["get_runs_page"](1, 100),
            "run": kwargs["get_run_by_id"](123),
            "artifacts": kwargs["get_run_artifacts"](123),
            "jobs": kwargs["get_run_jobs"](123),
            "artifact_zip": kwargs["download_artifact_zip"](456),
            "release": kwargs["get_release"]("PR-119"),
            "release_asset": kwargs["download_release_asset"](789),
        }
        return result

    monkeypatch.setenv("GH_TOKEN", "local-github-token-must-not-be-retained")
    monkeypatch.setattr(
        authority_module, "_fixed_provider_get", synthetic_transport,
    )
    monkeypatch.setattr(history, "_build_with_readers", call_all_readers)

    def build_history(authority, *_args):
        result = history.build_current_fotmob_latest_durable_fresh_history_handoff(
            current_bootstrap={}, source_raw_json=b"{}", source_manifest={},
            legacy_bootstrap_projection_raw=b"{}", expected_main_sha="a" * 40,
        )
        with pytest.raises(ProductOperationAuthorityError):
            authority.github_lineage_json(request_target="/repos/Thabearr/ATHENA/issues")
        return result

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, build_history, wait=False,
    )
    assert case["worker_finished"].wait(30)
    assert case["worker_errors"] == []
    assert "authority" in captured

    assert set(captured["result"]) == {
        "main", "runs", "run", "artifacts", "jobs", "artifact_zip", "release",
        "release_asset",
    }
    assert len(calls) == 8
    assert {provider for provider, _target in calls} == {
        authority_module.GITHUB_LINEAGE_JSON,
        authority_module.GITHUB_LINEAGE_ARTIFACT_ZIP,
        authority_module.GITHUB_LINEAGE_RELEASE_ASSET,
    }
    with case["repository"]._operation() as conn:
        operations = conn.execute(
            "SELECT state FROM app_external_operations WHERE run_id=?",
            (case["run_id"],),
        ).fetchall()
    assert operations == [("CONFIRMED",)] * 8
    assert "/repos/Thabearr/ATHENA/issues" not in {
        target for _provider, target in calls
    }


def test_product_runner_evidence_writer_is_cancel_fenced(
    tmp_path, clock, monkeypatch,
):
    from runtime.resources import ResourceResolver
    from database.run_repository import DurableRunRepository
    from domain import current_shadow_all_market_runner as runner
    from scripts import execute_current_shadow_request
    from types import SimpleNamespace

    output = tmp_path / "cancelled-product-output.json"
    policy_directory = tmp_path / "cancelled-request-policy"

    def cancel_then_write(_authority, repository, command, gate):
        cancel_repository = DurableRunRepository.for_worker_data_root(
            ResourceResolver.for_development(repository.verified_identity), repository._data_root,
        )
        cancel_repository.record_cancel_intent(gate["run_id"])
        with pytest.raises(RunStateConflict):
            runner._write(output, {"must_not_publish": True})
        with pytest.raises(RunStateConflict):
            execute_current_shadow_request._write_request_policy(SimpleNamespace(
                output_dir=policy_directory, fixture_dates=None,
                fixture_scope="today", create_share_code=False,
            ))
        return None

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, cancel_then_write,
    )

    assert captured["result"] is None
    assert not output.exists()
    assert not policy_directory.exists()
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCEL_REQUESTED"
    assert "CURRENT_SHADOW_EVIDENCE_PUBLISHED" not in [
        event[2] for event in case["repository"].read_events(case["run_id"])
    ]


@pytest.mark.parametrize("phase", ["PREPARED", "SENT"])
def test_provider_get_recovery_preserves_never_sent_vs_unknown_crash_boundary(
    tmp_path, clock, monkeypatch, phase,
):
    from runtime.current_shadow_operation_authority import (
        _build_provider_get_intent, provider_get_idempotency_key,
    )
    from scripts.capture_fotmob_data_matches import (
        REQUEST_HEADERS, REQUEST_TIMEOUT_SECONDS, request_target,
    )
    from domain.fotmob_data_matches_capture import MAX_RESPONSE_BYTES
    from runtime.resources import ResourceResolver
    from database.run_repository import DurableRunRepository

    monkeypatch.setattr(
        "runtime.current_shadow_operation_authority._fixed_provider_get",
        lambda _intent: pytest.fail("recovery fixture must never call a provider"),
    )

    def stop_at_boundary(authority, repository, command, gate):
        context = authority._context
        intent = _build_provider_get_intent(
            context, provider="FOTMOB_DATA_MATCHES",
            request_target=request_target("20300101", "UTC", "NGA"),
            logical_id="20300101", headers=tuple(REQUEST_HEADERS),
            timeout_seconds=REQUEST_TIMEOUT_SECONDS, maximum_bytes=MAX_RESPONSE_BYTES,
            sequence=1,
        )
        intent_bytes = canonical_json_bytes(intent)
        operation_id = repository.prepare_current_shadow_provider_get(
            context=context, command=command, gate=gate,
            gate_bytes=canonical_json_bytes(gate), intent=intent,
            intent_bytes=intent_bytes,
            idempotency_key=provider_get_idempotency_key(context, intent),
        )
        if phase == "SENT":
            assert repository.authorize_current_shadow_provider_get_sent(
                context=context, command=command, gate=gate,
                gate_bytes=canonical_json_bytes(gate), operation_id=operation_id,
            ) is True
        return operation_id

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, stop_at_boundary,
    )
    assert "error" not in captured
    case["repository"].record_cancel_intent(case["run_id"])
    with case["repository"]._operation() as conn:
        lease_token = conn.execute(
            "SELECT lease_token FROM app_run_attempts WHERE attempt_id=?",
            (captured["context"]["attempt_id"],),
        ).fetchone()[0]
    case["repository"].reconcile_dead_attempt(
        case["run_id"], captured["context"]["attempt_id"], lease_token,
    )
    with case["repository"]._operation() as conn:
        state, error_code = conn.execute(
            "SELECT state,error_code FROM app_external_operations WHERE run_id=?",
            (case["run_id"],),
        ).fetchone()
    expected = (
        ("FAILED", "PROVIDER_GET_NEVER_SENT") if phase == "PREPARED"
        else ("OUTCOME_UNKNOWN", "PROVIDER_GET_OUTCOME_UNKNOWN")
    )
    assert (state, error_code) == expected
    event_types = [event[2] for event in case["repository"].read_events(case["run_id"])]
    if phase == "PREPARED":
        assert "CURRENT_SHADOW_GET_NEVER_SENT" in event_types
    else:
        assert "CURRENT_SHADOW_GET_OUTCOME_UNKNOWN" in event_types
    assert case["repository"].run_snapshot(case["run_id"])["state"] == "CANCELLED"


def test_product_get_sent_permit_can_settle_after_cancel_but_cannot_start_next_get(
    tmp_path, clock, monkeypatch,
):
    from runtime.current_shadow_operation_authority import (
        ProductOperationAuthorityError, ProviderGetResponse,
    )
    from runtime.resources import ResourceResolver
    from database.run_repository import DurableRunRepository
    from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_source
    import time

    entered_transport = threading.Event()
    release_transport = threading.Event()
    cancel_committed = threading.Event()
    physical_attempts = []
    response = ProviderGetResponse(
        body=b"{}", status=200, observed_at="2030-01-01T00:00:00.000000Z",
        content_type="application/json", content_length=2, content_length_header="2",
    )

    def fake_transport(_intent):
        entered_transport.set()
        if not release_transport.wait(10):
            raise AssertionError("SENT/transport barrier was not released")
        physical_attempts.append(cancel_committed.is_set())
        return response

    monkeypatch.setattr(
        "runtime.current_shadow_operation_authority._fixed_provider_get", fake_transport,
    )

    def get_pc_page(authority, page_num):
        nonce = int(time.time() * 1000)
        return authority.perform_get(
            provider="SPORTYBET_PC_UPCOMING",
            request_target=pc_source.request_target(page_num, nonce),
            logical_id=f"epoch:1:page:{page_num}", headers=tuple(pc_source.REQUEST_HEADERS),
            timeout_seconds=pc_source.REQUEST_TIMEOUT_SECONDS,
            maximum_bytes=pc_source.MAX_RESPONSE_BYTES,
        )

    def settle_then_attempt_second(authority, _repository, _command, _gate):
        first = get_pc_page(authority, 1)
        try:
            from runtime.current_shadow_operation_authority import current_product_authority
            assert current_product_authority() is authority
            get_pc_page(authority, 2)
        except BaseException as exc:
            return first, exc
        return first, None

    case, captured = _run_authenticated_product_authority_case(
        tmp_path, clock, monkeypatch, settle_then_attempt_second,
        release_gate=False, wait=False,
    )
    case["release_gate"].set()
    assert entered_transport.wait(10)
    cancel_repository = DurableRunRepository.for_worker_data_root(
        ResourceResolver.for_development(case["identity"]), case["roots"].data_root,
    )
    cancel_finished = threading.Event()

    def cancel_during_get():
        cancel_repository.record_cancel_intent(case["run_id"])
        cancel_committed.set()
        cancel_finished.set()

    cancellation_thread = threading.Thread(target=cancel_during_get, name="cancel-while-get-test")
    cancellation_thread.start()
    if not cancel_finished.wait(5):
        release_transport.set()
        cancellation_thread.join(5)
        pytest.fail("provider transport held the DB or app-root lock across the GET")
    release_transport.set()
    assert case["worker_finished"].wait(10)
    assert case["worker_errors"] == []
    assert physical_attempts == [True]
    first, denied = captured["result"]
    assert first.body == b"{}"
    assert isinstance(denied, (ProductOperationAuthorityError, RunStateConflict))
    event_types = [event[2] for event in case["repository"].read_events(case["run_id"])]
    assert event_types.count("CURRENT_SHADOW_GET_PREPARED") == 1
    assert event_types.count("CURRENT_SHADOW_GET_SENT") == 1
    assert event_types.index("CURRENT_SHADOW_GET_SENT") < event_types.index("RUN_CANCEL_REQUESTED")
    assert event_types.index("RUN_CANCEL_REQUESTED") < event_types.index(
        "CURRENT_SHADOW_GET_RESPONSE_RETAINED"
    )
    with case["repository"]._operation() as conn:
        row = conn.execute(
            "SELECT state FROM app_external_operations WHERE run_id=?",
            (case["run_id"],),
        ).fetchone()
    assert row == ("CONFIRMED",)


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
