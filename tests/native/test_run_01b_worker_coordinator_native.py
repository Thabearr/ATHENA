"""Native contract tests for RUN-01B's bounded process locator."""
from __future__ import annotations

import os

import pytest

from services.worker_coordinator import WorkerCoordinator


def test_process_locator_uses_exact_native_process_group_schema():
    locator = WorkerCoordinator._native_process_locator(117)
    expected_kind = "WINDOWS_PROCESS_GROUP" if os.name == "nt" else "POSIX_PROCESS_GROUP"
    assert locator == {"kind": expected_kind, "pid": 117}
    assert type(locator["pid"]) is int
    assert set(locator) == {"kind", "pid"}


def test_native_current_process_locator_carries_no_unreviewed_fields():
    locator = WorkerCoordinator._native_process_locator(os.getpid())
    assert set(locator) == {"kind", "pid"}
    assert locator["pid"] == os.getpid()
    assert locator["kind"] == ("WINDOWS_PROCESS_GROUP" if os.name == "nt" else "POSIX_PROCESS_GROUP")


@pytest.mark.parametrize("pid", [0, -1, True, 117.0, "117", None])
def test_process_locator_rejects_nonpositive_or_inexact_pids(pid):
    assert WorkerCoordinator._native_process_locator(pid) is None
