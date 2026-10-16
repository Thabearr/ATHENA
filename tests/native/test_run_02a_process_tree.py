"""Native, provider-free process ownership and recovery tests for RUN-02A."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from runtime.worker_launcher import WorkerProcessHandle, _process_group_options, _spawn_process
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
    child_code = (
        "import signal,time; "
        + ("signal.signal(" + handler + ", lambda *_: exit(0)); " if graceful
           else "signal.signal(" + handler + ", signal.SIG_IGN); ")
        + "signal.signal(signal.SIGTERM, lambda *_: exit(0) if " + str(graceful) + " else None); "
        + "time.sleep(60)"
    )
    parent_code = (
        "import pathlib,signal,subprocess,sys,time; "
        + ("signal.signal(" + handler + ", lambda *_: exit(0)); " if graceful
           else "signal.signal(" + handler + ", signal.SIG_IGN); ")
        + "time.sleep(0.6); "
        + "child=subprocess.Popen([sys.executable,'-c',sys.argv[2]],"
          "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        + "pathlib.Path(sys.argv[1]).write_text(str(child.pid),encoding='ascii'); "
        + ("sys.exit(0); " if parent_exits else "time.sleep(60); ")
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
        if not graceful:
            time.sleep(0.15)
            assert control.force_terminate(locator) is True
        assert _wait_for(lambda: (handle.poll() is not None)
                         and control.state_current() == "DEAD")
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
        assert control.request_cancel(locator) is True
        if handle.poll() is None:
            control.force_terminate(locator)
        assert _wait_for(lambda: handle.poll() is not None)
        assert _wait_for(lambda: control.state_current() == "DEAD")
        assert RecoveryService.process_state(locator, control.owner) == "DEAD"
        changed = dict(locator)
        changed["lease_sha256"] = "0" * 64
        assert WorkerProcessControl.state(changed, control.owner) == "UNKNOWN"
        if os.name == "posix":
            reused = dict(locator)
            reused["start_ticks"] += 1
            assert WorkerProcessControl.state(reused, control.owner) == "UNKNOWN"
    finally:
        if control.state_current() != "DEAD":
            try:
                control.force_terminate(locator)
            except ProcessControlError:
                pass
        control.close()
