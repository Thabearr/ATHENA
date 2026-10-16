"""Native process tree and cancellation tests for RUN-02A."""
from __future__ import annotations

import os
import sys
import time

import pytest

from runtime.worker_launcher import (
    WorkerProcessHandle,
    _process_group_options,
    _spawn_process,
)
from services.recovery_service import RecoveryService
from services.worker_coordinator import WorkerCoordinator


def test_native_process_group_launch_and_terminate():
    """Verify worker process group launch, polling, and terminate_tree."""
    proc = _spawn_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=os.getcwd(),
        shell=False,
        **_process_group_options(),
    )
    handle = WorkerProcessHandle(proc)
    try:
        assert handle.pid > 0
        assert handle.poll() is None
        handle.terminate_tree(timeout=0.5)
        time.sleep(0.1)
        exit_code = handle.poll()
        assert exit_code is not None
    finally:
        if handle.poll() is None:
            handle.kill_tree()


def test_native_process_group_kill_tree():
    """Verify worker process group kill_tree terminates immediately."""
    proc = _spawn_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=os.getcwd(),
        shell=False,
        **_process_group_options(),
    )
    handle = WorkerProcessHandle(proc)
    try:
        assert handle.pid > 0
        assert handle.poll() is None
        handle.kill_tree()
        time.sleep(0.1)
        exit_code = handle.poll()
        assert exit_code is not None
    finally:
        if handle.poll() is None:
            handle.kill_tree()


def test_recovery_service_is_process_active():
    """Verify RecoveryService._is_process_active distinguishes live vs dead processes."""
    current_locator = WorkerCoordinator._native_process_locator(os.getpid())
    assert current_locator is not None
    assert RecoveryService._is_process_active(current_locator) is True

    dead_locator = WorkerCoordinator._native_process_locator(99999999)
    assert dead_locator is not None
    assert RecoveryService._is_process_active(dead_locator) is False

    assert RecoveryService._is_process_active({"kind": "UNKNOWN", "pid": os.getpid()}) is False
    assert RecoveryService._is_process_active({"kind": current_locator["kind"], "pid": -1}) is False
    assert RecoveryService._is_process_active("not-a-dict") is False
