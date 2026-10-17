"""Native, provider-free process ownership and recovery tests for RUN-02A."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

import pytest

from runtime.worker_launcher import (
    WORKER_OFFLINE_PROBE_FILENAME,
    WORKER_PROVENANCE_FILENAME,
    WORKER_REQUEST_FILENAME,
    WorkerCommand,
    WorkerProcessHandle,
    _process_group_options,
    _spawn_process,
    persist_worker_command,
)
from domain.run_contracts import RunRequest
from services.recovery_service import RecoveryService, _is_pid_active
from services.worker_process_control import ProcessControlError, WorkerProcessControl, owner_identity


def _owner(label: str) -> dict[str, str]:
    return owner_identity(
        run_id="run-native-" + label,
        attempt_id="attempt-native-" + label,
        worker_instance_id="native-test",
        lease_token="lease-native-" + label,
    )


def _spawn_tree(tmp_path: Path, *, graceful: bool, parent_exits: bool = False):
    marker = tmp_path / "descendant.pid"
    handler = "getattr(signal, 'SIGBREAK', signal.SIGTERM)"
    # Poll briefly so Python can service CTRL_BREAK on Windows instead of
    # remaining inside one long sleep until the test timeout expires.
    cooperative_wait = "[time.sleep(0.02) for _ in range(3000)]"
    child_code = (
        "import signal,time; "
        + ("signal.signal(" + handler + ", lambda *_: exit(0)); " if graceful
           else "signal.signal(" + handler + ", signal.SIG_IGN); ")
        + "signal.signal(signal.SIGTERM, lambda *_: exit(0) if " + str(graceful) + " else None); "
        + cooperative_wait
    )
    parent_code = (
        "import pathlib,signal,subprocess,sys,time; "
        + ("signal.signal(" + handler + ", lambda *_: exit(0)); " if graceful
           else "signal.signal(" + handler + ", signal.SIG_IGN); ")
        + "time.sleep(0.6); "
        + "child=subprocess.Popen([sys.executable,'-c',sys.argv[2]],"
          "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        + "pathlib.Path(sys.argv[1]).write_text(str(child.pid),encoding='ascii'); "
        + ("sys.exit(0); " if parent_exits else cooperative_wait)
    )
    process = _spawn_process(
        [sys.executable, "-c", parent_code, os.fspath(marker), child_code],
        cwd=Path.cwd(), shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **_process_group_options(),
    )
    return WorkerProcessHandle(process), marker


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def _linux_process_state(pid: int) -> str | None:
    """Read the kernel state for a test-owned PID; missing means it was reaped."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
    except FileNotFoundError:
        return None
    close = raw.rfind(b")")
    if close < 0:
        raise AssertionError("malformed Linux process stat for test-owned child")
    fields = raw[close + 2:].split()
    return fields[0].decode("ascii")


def _bind(handle: WorkerProcessHandle, label: str):
    control = WorkerProcessControl(handle, _owner(label))
    locator = control.bind()
    return control, locator


@pytest.mark.parametrize("graceful", [True, False], ids=["graceful", "force"])
def test_native_process_group_owns_leader_and_descendant(tmp_path, graceful):
    handle, marker = _spawn_tree(tmp_path, graceful=graceful)
    control, locator = _bind(handle, "tree-" + str(graceful))
    try:
        assert handle.pid > 0
        assert _wait_for(marker.exists)
        assert control.state_current() == "ACTIVE"
        assert WorkerProcessControl.state(locator, control.owner) == "ACTIVE"
        assert control.request_cancel(locator) is True
        child_pid = None
        if os.name == "posix":
            child_pid = int(_wait_for(marker.exists) and marker.read_text(encoding="ascii"))
        if not graceful:
            time.sleep(0.15)
            assert control.force_terminate(locator) is True
        if graceful or os.name == "nt":
            assert _wait_for(lambda: (handle.poll() is not None)
                             and control.state_current() == "DEAD")
        else:
            # SIGKILL may leave a terminated grandchild as a zombie when the
            # test runner's init does not reap promptly. It cannot execute,
            # while the surviving process group must remain UNKNOWN to recovery.
            assert _wait_for(lambda: handle.poll() is not None
                             and _linux_process_state(child_pid) in (None, "Z", "X"))
            state = control.state_current()
            assert state in ("DEAD", "UNKNOWN")
            if state == "UNKNOWN":
                assert _linux_process_state(child_pid) in ("Z", "X")
    finally:
        if control.state_current() != "DEAD":
            try:
                control.force_terminate(locator)
            except ProcessControlError:
                pass
        control.close()


def test_native_orphan_descendant_is_not_mistaken_for_dead_owner(tmp_path):
    handle, marker = _spawn_tree(tmp_path, graceful=False, parent_exits=True)
    control, locator = _bind(handle, "orphan")
    try:
        assert _wait_for(marker.exists)
        assert handle._process.wait(timeout=5) == 0
        if os.name == "nt":
            # The persistent per-attempt Job Object proves the remaining
            # member belongs to this exact launch and can be terminated safely.
            assert control.state_current() == "ACTIVE"
            assert control.force_terminate(locator) is True
            assert _wait_for(lambda: control.state_current() == "DEAD")
        else:
            # A dead leader plus a surviving process group is ambiguous after
            # restart; recovery must block instead of killing a reused PID.
            assert control.state_current() == "UNKNOWN"
            assert RecoveryService.process_state(locator, control.owner) == "UNKNOWN"
            assert RecoveryService._is_process_active(locator) is True
            child_pid = int(marker.read_text(encoding="ascii"))
            os.kill(child_pid, signal.SIGKILL)  # exact child created by this test
    finally:
        control.close()


def test_native_cancelled_product_probe_is_killed_before_gate_effect(tmp_path):
    """Exercise a real Windows Job Object / POSIX group at the product gate."""
    from test_run_01b_worker_lifecycle import _development_shadow_run
    from test_run_02a_recovery import _admit_run

    identity, roots, repository, item, envelope = _development_shadow_run(
        tmp_path, lambda: datetime(2030, 1, 1, 22, 59, tzinfo=timezone.utc),
    )
    run_id = _admit_run(repository, item, envelope, "native-gate-cancel")
    attempt_id, lease_token, _number = repository.claim_attempt(
        run_id, worker_instance_id="native-gate-worker",
        process_locator={"kind": "OFFLINE_TEST", "label": "native-gate"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )
    request = RunRequest.from_json_bytes(item.request_bytes)
    run_directory = roots.data_root / "runs" / run_id / request.canonical_sha256
    run_directory.mkdir(parents=True)
    (run_directory / WORKER_REQUEST_FILENAME).write_bytes(item.request_bytes)
    command = WorkerCommand(
        operation="OFFLINE_IDENTITY_PROBE", mode="offline_identity_probe",
        run_directory=run_directory, request_artifact_id=request.canonical_sha256,
        envelope_artifact_id=None, release_identity_kind=identity.identity_kind,
        release_identity_id=identity.head_commit_sha,
    )
    command_path = persist_worker_command(command)
    ready_path = tmp_path / "worker-reached-product-gate.txt"
    wrapper = (
        "import pathlib,sys; "
        "from runtime import worker_entry,worker_startup_gate; "
        "original=worker_startup_gate.wait_for_gate; "
        "worker_startup_gate.wait_for_gate=lambda command,**kwargs: "
        "(pathlib.Path(sys.argv[1]).write_text('ready',encoding='ascii'), "
        "original(command,**kwargs))[1]; "
        "raise SystemExit(worker_entry.main(sys.argv[2:]))"
    )
    process = _spawn_process(
        [sys.executable, "-c", wrapper, os.fspath(ready_path),
         "--command-file", os.fspath(command_path),
         "--development-root", os.fspath(identity.repository_root)],
        cwd=identity.repository_root,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **_process_group_options(),
    )
    handle = WorkerProcessHandle(process)
    owner = owner_identity(
        run_id=run_id, attempt_id=attempt_id,
        worker_instance_id="native-gate-worker", lease_token=lease_token,
    )
    control = WorkerProcessControl(handle, owner)
    locator = control.bind()
    repository.bind_process_locator(run_id, attempt_id, lease_token, locator)
    try:
        assert _wait_for(ready_path.is_file), "native product child did not reach its gate barrier"
        assert not (run_directory / WORKER_OFFLINE_PROBE_FILENAME).exists()
        assert not (run_directory / WORKER_PROVENANCE_FILENAME).exists()
        repository.record_cancel_intent(run_id)
        control.abort_before_start()
        process.communicate(timeout=10)
        assert repository.run_snapshot(run_id)["state"] == "CANCEL_REQUESTED"
        assert not (run_directory / WORKER_OFFLINE_PROBE_FILENAME).exists()
        assert not (run_directory / WORKER_PROVENANCE_FILENAME).exists()
        assert repository.run_snapshot(run_id)["receipt_artifact_id"] is None
    finally:
        if process.poll() is None:
            control.abort_before_start()
            process.communicate(timeout=10)
        control.close()


def test_dead_pid_is_dead_unknown_owner_is_blocked():
    assert _is_pid_active(99999999) is False
    assert RecoveryService.process_state(
        {"kind": "OFFLINE_TEST", "label": "launch-before-bind"},
        _owner("pending"),
    ) == "UNKNOWN"
    assert RecoveryService._is_process_active(
        {"kind": "UNKNOWN", "pid": 99999999}
    ) is True


def test_inaccessible_pid_is_not_classified_as_dead(monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX permission distinction is exercised only on POSIX")

    def inaccessible(_pid, _signal):
        raise PermissionError("synthetic access denial")

    monkeypatch.setattr(os, "kill", inaccessible)
    assert _is_pid_active(99999999) is True


def test_stale_process_identity_cannot_signal_or_claim_dead_owner(tmp_path):
    handle, marker = _spawn_tree(tmp_path, graceful=False)
    control, locator = _bind(handle, "stale")
    try:
        if os.name == "posix":
            reused = dict(locator)
            reused["start_ticks"] += 1
            assert WorkerProcessControl.state(reused, control.owner) == "UNKNOWN"
            assert control.request_cancel(reused) is False
            assert handle.poll() is None
        assert control.request_cancel(locator) is True
        if handle.poll() is None:
            control.force_terminate(locator)
        assert _wait_for(lambda: handle.poll() is not None)
        assert _wait_for(lambda: control.state_current() == "DEAD")
        assert RecoveryService.process_state(locator, control.owner) == "DEAD"
        changed = dict(locator)
        changed["lease_sha256"] = "0" * 64
        assert WorkerProcessControl.state(changed, control.owner) == "UNKNOWN"
    finally:
        if control.state_current() != "DEAD":
            try:
                control.force_terminate(locator)
            except ProcessControlError:
                pass
        control.close()
