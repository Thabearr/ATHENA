"""Bounded startup reconciliation for unfinished attempts and terminal projection repair.

Pure orchestration over trusted ports: never executes business work, never retries
operations, and operates fully offline without network or provider calls.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from database.run_repository import DurableRunRepository


RecoveryDisposition = Literal["REPAIRED", "INTERRUPTED", "CANCELLED", "BLOCKED", "CLEAN"]


@dataclass(frozen=True)
class RecoverySummary:
    reconciled_attempts: int
    projected_receipts: int
    interrupted_runs: int
    cancelled_runs: int
    blocked_runs: int


def _is_pid_active(pid: int) -> bool:
    """Check if an OS process with the given PID is currently active."""
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        # On POSIX/Windows, PermissionError indicates the process exists but is owned by another user.
        return True
    except OSError:
        return False


class RecoveryService:
    """Orchestrate startup reconciliation over DurableRunRepository."""

    @staticmethod
    def _is_process_active(locator: object) -> bool:
        if type(locator) is not dict:
            return False
        kind = locator.get("kind")
        if kind == "OFFLINE_TEST":
            return False
        if kind not in {"WINDOWS_PROCESS_GROUP", "POSIX_PROCESS_GROUP"}:
            return False
        pid = locator.get("pid")
        if type(pid) is not int or pid <= 0:
            return False
        return _is_pid_active(pid)

    def __init__(self, repository: DurableRunRepository, data_root: Path) -> None:
        if type(repository) is not DurableRunRepository:
            raise ValueError("exact DurableRunRepository is required")
        self._repository = repository
        self._data_root = Path(data_root)

    def reconcile(self) -> RecoverySummary:
        """Scan unfinished attempts and reconcile them idempotently."""
        unfinished = self._repository.list_unfinished_attempts()
        reconciled = 0
        projected = 0
        interrupted = 0
        cancelled = 0
        blocked = 0

        receipts_dir = self._data_root / "run-receipts"

        for attempt in unfinished:
            run_id = attempt["run_id"]
            attempt_id = attempt["attempt_id"]
            lease_token = attempt["lease_token"]
            run_state = attempt["run_state"]

            # Step 1: Check if an exact verified terminal receipt exists on disk for this run
            receipt_found = False
            if receipts_dir.is_dir():
                for receipt_file in receipts_dir.glob("*.json"):
                    try:
                        raw = receipt_file.read_bytes()
                        digest = hashlib.sha256(raw).hexdigest()
                        if digest != receipt_file.stem:
                            continue
                        doc = json.loads(raw)
                        if (doc.get("run_id") == run_id
                                and doc.get("policy_id") == "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1"):
                            if self._repository.project_terminal_receipt(digest):
                                receipt_found = True
                                projected += 1
                                reconciled += 1
                                break
                    except Exception:
                        continue

            if receipt_found:
                continue

            # Step 2: Check process locator
            locator = attempt["process_locator"]
            locator_kind = locator.get("kind") if isinstance(locator, dict) else None

            if locator_kind not in {"OFFLINE_TEST", "WINDOWS_PROCESS_GROUP", "POSIX_PROCESS_GROUP"}:
                blocked += 1
                continue
            if self._is_process_active(locator):
                blocked += 1
                continue

            # Process is dead: reconcile attempt and external operations
            try:
                self._repository.reconcile_dead_attempt(run_id, attempt_id, lease_token)
                reconciled += 1
                if run_state == "CANCEL_REQUESTED":
                    cancelled += 1
                else:
                    interrupted += 1
            except Exception:
                blocked += 1

        return RecoverySummary(
            reconciled_attempts=reconciled,
            projected_receipts=projected,
            interrupted_runs=interrupted,
            cancelled_runs=cancelled,
            blocked_runs=blocked,
        )


__all__ = ["RecoveryDisposition", "RecoveryService", "RecoverySummary"]
