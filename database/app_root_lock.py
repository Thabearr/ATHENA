"""Cross-process serialization for the app data-root generation.

All ATHENA app-store operations cooperate through a stable sibling lock file.
Keeping the lock outside the replaceable data directory lets backup and restore
hold the same ownership boundary while swapping complete generations.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import json
import re
import threading
import time


_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}
_local = threading.local()
_ROOT_NAME = re.compile(r"\.[A-Za-z0-9._-]+\.(?:history|restore|failed)\.[0-9a-f]{32}(?:\.staging)?\Z")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_durable(source: Path, destination: Path) -> None:
    if os.name != "nt":
        os.rename(source, destination)
        _fsync_directory(source.parent)
        return
    import ctypes

    move = ctypes.windll.kernel32.MoveFileExW
    move.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
    move.restype = ctypes.c_int
    # MOVEFILE_WRITE_THROUGH; no copy/replace flags, so a cross-volume move
    # fails instead of copying over an active generation.
    if not move(str(source), str(destination), 0x00000008):
        raise OSError(ctypes.get_last_error(), "same-volume durable root rename failed")


def _replace_durable(source: Path, destination: Path) -> None:
    if os.name != "nt":
        os.replace(source, destination)
        _fsync_directory(source.parent)
        return
    import ctypes

    move = ctypes.windll.kernel32.MoveFileExW
    move.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
    move.restype = ctypes.c_int
    # MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH.
    if not move(str(source), str(destination), 0x00000001 | 0x00000008):
        raise OSError(ctypes.get_last_error(), "durable restore journal publication failed")


def _recover_interrupted_switch(root: Path) -> None:
    """Roll an interrupted two-rename activation back to its preserved root."""
    parent = root.parent
    journal = parent / ("." + root.name + ".restore-journal.json")
    if not journal.exists():
        return
    if journal.is_symlink() or bool(getattr(journal, "is_junction", lambda: False)()):
        raise RuntimeError("restore journal may not be a link or junction")
    try:
        raw = journal.read_bytes()
        value = json.loads(raw)
        canonical = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        expected = {"schema_version", "data_root", "history_name", "staging_name", "failed_name", "manifest_sha256"}
        if (raw != canonical or type(value) is not dict or set(value) != expected
                or value["schema_version"] != 1 or value["data_root"] != root.name
                or not isinstance(value["manifest_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", value["manifest_sha256"]) is None):
            raise ValueError("invalid restore journal")
        names = (value["history_name"], value["staging_name"], value["failed_name"])
        if any(type(name) is not str or _ROOT_NAME.fullmatch(name) is None
               or not name.startswith("." + root.name + ".") for name in names):
            raise ValueError("unsafe restore journal path")
        history, staging, failed = (parent / name for name in names)
        for candidate in (history, staging, failed, root):
            if candidate.is_symlink() or bool(getattr(candidate, "is_junction", lambda: False)()):
                raise ValueError("restore generation path may not be a link or junction")
        if history.exists():
            if root.exists():
                if failed.exists():
                    raise ValueError("restore rollback destination already exists")
            _rename_durable(root, failed)
            _rename_durable(history, root)
            _fsync_directory(parent)
        elif not root.exists():
            raise ValueError("restore journal has neither active nor preserved root")
        journal.unlink()
        _fsync_directory(parent)
    except Exception as exc:
        raise RuntimeError("interrupted restore cannot be safely recovered") from exc


def _thread_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve(strict=False)))
    with _guard:
        return _locks.setdefault(key, threading.RLock())


def _acquire_file(path: Path) -> int:
    if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
        raise RuntimeError("app root lock path may not be a link or junction")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            deadline = time.monotonic() + 600
            while True:
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("timed out waiting for the cross-process app-root lock")
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _release_file(descriptor: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


@contextmanager
def app_root_lock(data_root: str | os.PathLike[str]):
    """Take a reentrant in-process and exclusive cross-process root lock."""
    root = Path(data_root).resolve(strict=False)
    parent = root.parent
    parent.mkdir(parents=True, exist_ok=True)
    lock_path = parent / ("." + root.name + ".athena-root.lock")
    lock = _thread_lock(lock_path)
    lock.acquire()
    depths = getattr(_local, "depths", None)
    if depths is None:
        depths = {}
        _local.depths = depths
    key = os.path.normcase(str(lock_path.resolve(strict=False)))
    descriptor = None
    try:
        depth = depths.get(key, 0)
        if depth == 0:
            descriptor = _acquire_file(lock_path)
        depths[key] = depth + 1
        if depth == 0:
            _recover_interrupted_switch(root)
        yield
    finally:
        current = depths.get(key, 1) - 1
        if current:
            depths[key] = current
        else:
            depths.pop(key, None)
            if descriptor is not None:
                _release_file(descriptor)
        lock.release()


__all__ = ["app_root_lock"]
