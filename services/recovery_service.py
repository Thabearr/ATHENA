"""Bounded, provider-free startup reconciliation for fenced worker attempts."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal

from database.run_repository import DurableRunRepository
from services.worker_process_control import ProcessState, WorkerProcessControl, owner_identity


RecoveryDisposition = Literal["REPAIRED", "INTERRUPTED", "CANCELLED", "BLOCKED", "CLEAN"]


@dataclass(frozen=True)
class RecoverySummary:
    reconciled_attempts: int
    projected_receipts: int
    interrupted_runs: int
    cancelled_runs: int
    blocked_runs: int


def _is_pid_active(pid: int) -> bool:
    """Compatibility liveness probe: unknown is conservatively active."""
    if type(pid) is not int or pid <= 0:
        return True
    if os.name == "posix":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            return True
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return ctypes.get_last_error() != 87  # invalid PID is dead; access denied is unknown.
            kernel.CloseHandle(handle)
            return True
        except Exception:
            return True
    return True


class RecoveryService:
    """Reconcile only exact DB-linked receipts and verifiably dead owners."""

    @staticmethod
    def process_state(locator: object, owner: dict[str, str]) -> ProcessState:
        return WorkerProcessControl.state(locator, owner)

    @staticmethod
    def _is_process_active(locator: object) -> bool:
        if type(locator) is not dict:
            return True
        pid = locator.get("pid")
        if type(pid) is not int or pid <= 0:
            return True
        # This legacy boolean surface is conservative: UNKNOWN stays active.
        return _is_pid_active(pid) or WorkerProcessControl.state(
            locator,
            {key: locator.get(key) for key in
             ("run_id", "attempt_id", "worker_instance_id", "lease_sha256")},
        ) != "DEAD"

    def __init__(self, repository: DurableRunRepository, data_root: Path) -> None:
        if type(repository) is not DurableRunRepository:
            raise ValueError("exact DurableRunRepository is required")
        self._repository = repository
        self._data_root = Path(data_root)

    def reconcile(self) -> RecoverySummary:
        """Verify bounded receipt links before considering exact owner death."""
        unfinished = self._repository.list_unfinished_attempts()
        reconciled = projected = interrupted = cancelled = blocked = 0
        try:
            pending_receipts = self._repository.list_pending_terminal_receipts(limit=100)
        except Exception:
            return RecoverySummary(0, 0, 0, 0, len(unfinished))

        projected_attempts: set[tuple[str, str]] = set()
        for candidate in pending_receipts:
            try:
                self._repository.project_terminal_receipt(candidate["receipt_sha256"])
                projected += 1
                reconciled += 1
                projected_attempts.add((candidate["run_id"], candidate["attempt_id"]))
            except Exception:
                # A bad/missing publication is never authority. The process
                # owner still has to prove DEAD before any interruption.
                continue

        for attempt in unfinished:
            run_id = attempt["run_id"]
            attempt_id = attempt["attempt_id"]
            if (run_id, attempt_id) in projected_attempts:
                continue
            owner = owner_identity(
                run_id=run_id,
                attempt_id=attempt_id,
                worker_instance_id=attempt["worker_instance_id"],
                lease_token=attempt["lease_token"],
            )
            state = self.process_state(attempt["process_locator"], owner)
            if state != "DEAD":
                blocked += 1
                continue
            try:
                self._repository.reconcile_dead_attempt(run_id, attempt_id, attempt["lease_token"])
                reconciled += 1
                if attempt["run_state"] == "CANCEL_REQUESTED":
                    cancelled += 1
                else:
                    interrupted += 1
            except Exception:
                blocked += 1

        return RecoverySummary(reconciled, projected, interrupted, cancelled, blocked)


__all__ = ["RecoveryDisposition", "RecoveryService", "RecoverySummary"]
