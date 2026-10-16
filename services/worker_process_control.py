"""Fenced process-group control kept outside the base-pinned launcher."""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import hashlib
import os
import secrets
import signal
import threading
from typing import Any, Literal

ProcessState = Literal["ACTIVE", "DEAD", "UNKNOWN"]
_OWNER_KEYS = ("run_id", "attempt_id", "worker_instance_id", "lease_sha256")


class ProcessControlError(RuntimeError):
    """A process identity or OS control operation could not be authenticated."""


def owner_identity(*, run_id: str, attempt_id: str, worker_instance_id: str,
                   lease_token: str) -> dict[str, str]:
    values = (run_id, attempt_id, worker_instance_id, lease_token)
    if any(type(value) is not str or not value for value in values):
        raise ProcessControlError("exact run, attempt, worker and lease are required")
    return {
        "run_id": run_id, "attempt_id": attempt_id,
        "worker_instance_id": worker_instance_id,
        "lease_sha256": hashlib.sha256(lease_token.encode("utf-8")).hexdigest(),
    }


def _owner_matches(locator: object, owner: dict[str, str]) -> bool:
    return (type(locator) is dict and type(owner) is dict
            and set(owner) == set(_OWNER_KEYS)
            and all(type(owner[key]) is str and owner[key] for key in _OWNER_KEYS)
            and all(locator.get(key) == owner[key] for key in _OWNER_KEYS))


def _linux_stat(pid: int) -> tuple[int, int, int] | None:
    """Return process group, session and start ticks; None means no such PID."""
    try:
        raw = open(f"/proc/{pid}/stat", "rb").read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProcessControlError("process identity is inaccessible") from exc
    try:
        close = raw.rfind(b")")
        if close < 0:
            raise ValueError
        fields = raw[close + 2:].split()
        return int(fields[2]), int(fields[3]), int(fields[19])
    except (IndexError, ValueError) as exc:
        raise ProcessControlError("process identity record is malformed") from exc


def _windows_api():
    if os.name != "nt":
        raise ProcessControlError("Windows process control is unavailable")
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.OpenJobObjectW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.OpenJobObjectW.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD))
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p)
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.GenerateConsoleCtrlEvent.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    return wintypes, kernel


def _filetime_value(filetime: Any) -> int:
    return (int(filetime.dwHighDateTime) << 32) | int(filetime.dwLowDateTime)


def _windows_creation_time(process_handle: Any) -> int:
    wintypes, kernel = _windows_api()
    created = wintypes.FILETIME()
    exited = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    if not kernel.GetProcessTimes(process_handle, ctypes.byref(created), ctypes.byref(exited),
                                  ctypes.byref(kernel_time), ctypes.byref(user_time)):
        raise ProcessControlError("worker process creation identity is unavailable")
    return _filetime_value(created)


def _open_job(name: str):
    wintypes, kernel = _windows_api()
    access = 0x0004  # JOB_OBJECT_QUERY; restart reconciliation never terminates.
    handle = kernel.OpenJobObjectW(access, False, name)
    if not handle:
        if ctypes.get_last_error() == 2:
            return None
        raise ProcessControlError("exact worker Job Object is inaccessible")
    return handle


def _job_pids(handle: Any) -> tuple[int, ...]:
    """Query a bounded exact PID list from the owned Job Object."""
    wintypes, kernel = _windows_api()
    capacity = 4096
    pointer_size = ctypes.sizeof(ctypes.c_size_t)
    buffer = ctypes.create_string_buffer(8 + capacity * pointer_size)
    returned = wintypes.DWORD()
    if not kernel.QueryInformationJobObject(handle, 3, buffer, len(buffer), ctypes.byref(returned)):
        raise ProcessControlError("worker Job Object membership is unavailable")
    assigned = wintypes.DWORD.from_buffer(buffer, 0).value
    count = wintypes.DWORD.from_buffer(buffer, 4).value
    if assigned > capacity or count > capacity or count < assigned:
        raise ProcessControlError("worker Job Object membership exceeds its bound")
    return tuple(int(ctypes.c_size_t.from_buffer(buffer, 8 + i * pointer_size).value)
                 for i in range(count))


@dataclass
class WorkerProcessControl:
    """One run/attempt-owned control handle; this class never starts a worker."""

    process_handle: Any
    owner: dict[str, str]
    _job: Any = None
    _locator: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if type(self.owner) is not dict or set(self.owner) != set(_OWNER_KEYS):
            raise ProcessControlError("process control owner identity is not exact")
        self._signal_lock = threading.Lock()
        self._cancel_sent = False

    def bind(self) -> dict[str, Any]:
        pid = getattr(self.process_handle, "pid", None)
        if type(pid) is not int or pid <= 0:
            raise ProcessControlError("launched worker has no valid process identity")
        if os.name == "nt":
            locator = self._bind_windows(pid)
        elif os.name == "posix":
            stat_value = _linux_stat(pid)
            if stat_value is None or stat_value[:2] != (pid, pid):
                raise ProcessControlError("launched worker is not the exact session leader")
            locator = {"kind": "POSIX_PROCESS_GROUP", "pid": pid, "pgid": pid,
                       "session_id": pid, "start_ticks": stat_value[2], **self.owner}
        else:
            raise ProcessControlError("platform process-group ownership is unsupported")
        self._locator = locator
        return dict(locator)

    def _bind_windows(self, pid: int) -> dict[str, Any]:
        wintypes, kernel = _windows_api()
        process = getattr(self.process_handle, "_process", None)
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise ProcessControlError("owned Windows process handle is unavailable")
        creation_time = _windows_creation_time(process_handle)
        name = "Local\\ATHENA-E3-" + secrets.token_hex(24)
        job = kernel.CreateJobObjectW(None, name)
        if not job:
            raise ProcessControlError("worker Job Object could not be created")
        if not kernel.AssignProcessToJobObject(job, process_handle):
            kernel.CloseHandle(job)
            raise ProcessControlError("worker could not be assigned to its exact Job Object")
        try:
            if _job_pids(job) != (pid,):
                raise ProcessControlError("worker Job Object did not contain only the gated root")
        except Exception:
            kernel.TerminateJobObject(job, 2)
            kernel.CloseHandle(job)
            raise
        self._job = job
        return {"kind": "WINDOWS_PROCESS_GROUP", "pid": pid,
                "creation_time": creation_time, "job_name": name, **self.owner}

    @staticmethod
    def state(locator: object, owner: dict[str, str]) -> ProcessState:
        if not _owner_matches(locator, owner):
            return "UNKNOWN"
        kind = locator.get("kind")
        if kind == "POSIX_PROCESS_GROUP":
            keys = {"kind", "pid", "pgid", "session_id", "start_ticks", *_OWNER_KEYS}
            if (set(locator) != keys or type(locator["pid"]) is not int
                    or locator["pid"] <= 0 or locator["pgid"] != locator["pid"]
                    or locator["session_id"] != locator["pid"]
                    or type(locator["start_ticks"]) is not int or locator["start_ticks"] <= 0):
                return "UNKNOWN"
            try:
                current = _linux_stat(locator["pid"])
            except ProcessControlError:
                return "UNKNOWN"
            if current is None:
                try:
                    os.killpg(locator["pgid"], 0)
                except ProcessLookupError:
                    return "DEAD"
                except (PermissionError, OSError):
                    return "UNKNOWN"
                # A surviving group without its authenticated leader can be an
                # orphan or a reused identity. Never reconcile or signal it.
                return "UNKNOWN"
            return ("ACTIVE" if current == (locator["pgid"], locator["session_id"],
                                               locator["start_ticks"]) else "UNKNOWN")
        if kind == "WINDOWS_PROCESS_GROUP":
            keys = {"kind", "pid", "creation_time", "job_name", *_OWNER_KEYS}
            if (set(locator) != keys or type(locator["pid"]) is not int
                    or locator["pid"] <= 0 or type(locator["creation_time"]) is not int
                    or type(locator["job_name"]) is not str
                    or not locator["job_name"].startswith("Local\\ATHENA-E3-")):
                return "UNKNOWN"
            job = None
            try:
                job = _open_job(locator["job_name"])
                if job is None:
                    process = _open_windows_process(locator["pid"])
                    if process is None:
                        return "DEAD"
                    try:
                        # A missing job object cannot establish ownership while
                        # the pinned root is still running.
                        return ("UNKNOWN" if _windows_creation_time(process) == locator["creation_time"]
                                else "DEAD")
                    finally:
                        kernel = _windows_api()[1]
                        kernel.CloseHandle(process)
                pids = _job_pids(job)
                if not pids:
                    return "DEAD"
                if locator["pid"] in pids:
                    process = _open_windows_process(locator["pid"])
                    if process is None:
                        return "UNKNOWN"
                    try:
                        return ("ACTIVE" if _windows_creation_time(process) == locator["creation_time"]
                                else "UNKNOWN")
                    finally:
                        kernel = _windows_api()[1]
                        kernel.CloseHandle(process)
                # The exact named per-attempt Job Object retains any descendants.
                return "ACTIVE"
            except ProcessControlError:
                return "UNKNOWN"
            finally:
                if job:
                    _windows_api()[1].CloseHandle(job)
        return "UNKNOWN"

    def state_current(self) -> ProcessState:
        return self.state(self._locator, self.owner)

    def request_cancel(self, locator: dict[str, Any]) -> bool:
        if self._locator != locator or self.state(locator, self.owner) != "ACTIVE":
            return False
        with self._signal_lock:
            if self._cancel_sent:
                return False
            if os.name == "nt":
                _wintypes, kernel = _windows_api()
                if not kernel.GenerateConsoleCtrlEvent(1, locator["pid"]):
                    raise ProcessControlError("exact worker process group rejected CTRL_BREAK")
            else:
                current = _linux_stat(locator["pid"])
                if current != (locator["pgid"], locator["session_id"], locator["start_ticks"]):
                    return False
                os.killpg(locator["pgid"], signal.SIGTERM)
            self._cancel_sent = True
            return True

    def force_terminate(self, locator: dict[str, Any]) -> bool:
        if self._locator != locator or self.state(locator, self.owner) != "ACTIVE":
            return False
        if os.name == "nt":
            if not self._job:
                return False
            if not _windows_api()[1].TerminateJobObject(self._job, 2):
                raise ProcessControlError("exact worker Job Object could not be terminated")
            return True
        current = _linux_stat(locator["pid"])
        if current != (locator["pgid"], locator["session_id"], locator["start_ticks"]):
            return False
        os.killpg(locator["pgid"], signal.SIGKILL)
        return True

    def abort_before_start(self) -> None:
        """Without the startup gate only this exact Popen root can execute."""
        try:
            process = getattr(self.process_handle, "_process", None)
            if process is not None and process.poll() is None:
                process.kill()
        except (OSError, ValueError, AttributeError):
            return

    def close(self) -> None:
        if self._job:
            _windows_api()[1].CloseHandle(self._job)
            self._job = None


def _open_windows_process(pid: int):
    wintypes, kernel = _windows_api()
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise ProcessControlError("worker process identity is inaccessible")
    return handle


__all__ = ["ProcessControlError", "ProcessState", "WorkerProcessControl", "owner_identity"]
