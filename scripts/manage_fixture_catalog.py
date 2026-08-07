"""Compile or verify a provenance-backed ATHENA fixture catalog."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Sequence

if __package__ in {None, ""}:
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

from domain.fixture_catalog import (  # noqa: E402
    FixtureCatalogError,
    FixtureCatalogResult,
    canonical_json_bytes,
    compile_fixture_catalog,
    parse_utc_timestamp,
    sha256_bytes,
)
from scripts.freeze_evidence_baseline import get_code_state  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_REPOSITORY_OUTPUT_ROOT = REPOSITORY_ROOT / ".cache" / "athena-research"
GENERATED_SAFETY_CONTRACT = {
    "network_requests": False,
    "scraping": False,
    "browser_automation": False,
    "credential_use": False,
    "odds_collection": False,
    "bookmaker_qualification": False,
    "market_activation": False,
    "bet_decision": False,
}


class FixtureCatalogCLIError(FixtureCatalogError):
    """Raised when the CLI cannot safely compile or verify outputs."""


@dataclass
class _PreparedOutput:
    destination: Path
    staged_dir: Path
    staged_path: Path
    existed: bool
    original_bytes: bytes | None
    original_mode: int | None
    backup_path: Path
    rollback_path: Path
    created_backup: bool = False
    created_rollback: bool = False


def _bounded_external_text(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if not value:
            continue
        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="replace")
        elif isinstance(value, str):
            text = value
        elif isinstance(value, (int, float)):
            text = str(value)
        else:
            continue
        parts.append(text)
    normalized = " ".join(" ".join(parts).split())
    return (normalized or "<no output>")[:240]


def _run_git_process(
    args: Sequence[str],
    *,
    cwd: Path,
    label: str,
    accepted_returncodes: frozenset[int] = frozenset({0}),
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            check=False,
            shell=False,
        )
    except OSError as error:
        raise FixtureCatalogCLIError(
            f"Git process execution failed ({label}): {_bounded_external_text(str(error))}"
        ) from error
    if result.returncode not in accepted_returncodes:
        raise FixtureCatalogCLIError(
            f"Git command failed ({label}, exit={result.returncode}): "
            f"{_bounded_external_text(result.stderr, result.stdout)}"
        )
    return result


def _run_git_bytes(
    args: Sequence[str],
    *,
    cwd: Path,
    label: str,
    accepted_returncodes: frozenset[int] = frozenset({0}),
) -> bytes:
    out = _run_git_process(
        args,
        cwd=cwd,
        label=label,
        accepted_returncodes=accepted_returncodes,
    ).stdout
    if isinstance(out, bytes):
        return out
    if isinstance(out, str):
        return out.encode("utf-8")
    return bytes(out or b"")


def _decode_git_token(token: bytes, label: str) -> str:
    try:
        value = token.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise FixtureCatalogCLIError(f"Git {label} was not valid UTF-8") from error
    if not value:
        raise FixtureCatalogCLIError(f"Git {label} was unexpectedly empty")
    return value


def _load_kernel32() -> Any:
    if os.name != "nt":
        return None
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE

        kernel32.FlushFileBuffers.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.FlushFileBuffers.restype = ctypes.wintypes.BOOL

        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        return kernel32
    except (AttributeError, OSError, ImportError):
        return None


def _get_last_error(kernel32: Any) -> int:
    if hasattr(kernel32, "GetLastError"):
        try:
            return int(kernel32.GetLastError())
        except Exception:
            pass
    try:
        import ctypes

        if hasattr(ctypes, "get_last_error"):
            return int(ctypes.get_last_error())
    except Exception:
        pass
    return 0


def _win_fsync_directory(path: Path) -> None:
    kernel32 = _load_kernel32()
    if kernel32 is None:
        raise FixtureCatalogCLIError("kernel32 is not available on this platform")

    # 0xC0000000 = GENERIC_READ | GENERIC_WRITE
    # 0x00000007 = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
    # 3 = OPEN_EXISTING
    # 0x02000000 = FILE_FLAG_BACKUP_SEMANTICS
    handle = kernel32.CreateFileW(
        str(path),
        0xC0000000,
        0x00000007,
        None,
        3,
        0x02000000,
        None,
    )
    invalid_handle_values: set[Any] = {0, None, -1}
    try:
        import ctypes
        import ctypes.wintypes

        if hasattr(ctypes, "c_void_p"):
            invalid_handle_values.add(ctypes.c_void_p(-1).value)
        if hasattr(ctypes, "wintypes") and hasattr(ctypes.wintypes, "HANDLE"):
            invalid_handle_values.add(ctypes.wintypes.HANDLE(-1).value)
            invalid_handle_values.add((1 << (ctypes.sizeof(ctypes.wintypes.HANDLE) * 8)) - 1)
    except Exception:
        pass

    if handle in invalid_handle_values:
        err = _get_last_error(kernel32)
        raise FixtureCatalogCLIError(
            f"CreateFileW failed for directory fsync: {path} (winerror={err})"
        )
    flush_error: str | None = None
    close_error: str | None = None
    try:
        if not kernel32.FlushFileBuffers(handle):
            err = _get_last_error(kernel32)
            flush_error = f"FlushFileBuffers failed for {path} (winerror={err})"
    finally:
        if not kernel32.CloseHandle(handle):
            err = _get_last_error(kernel32)
            close_error = f"CloseHandle failed for {path} (winerror={err})"
    if flush_error or close_error:
        raise FixtureCatalogCLIError(
            "; ".join(item for item in (flush_error, close_error) if item)
        )


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        _win_fsync_directory(path)
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(str(path), flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_file(path: Path) -> None:
    mode = "rb+" if os.name == "nt" else "rb"
    with path.open(mode) as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _walk_unresolved_path(path: Path) -> Path:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor) if absolute.anchor else Path(".")
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise FixtureCatalogCLIError(
                f"Path contains a forbidden symlink component: {path}"
            )
    return absolute


def _assert_no_symlink_components(path: Path, label: str) -> Path:
    unresolved = path.absolute()
    curr = unresolved
    while curr != curr.parent:
        if curr.is_symlink():
            raise FixtureCatalogCLIError(
                f"{label} contains forbidden symlink path component: {curr}"
            )
        curr = curr.parent
    return path.resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _find_boundary(target_directory: Path) -> Path:
    target = target_directory.resolve(strict=False)
    if _is_relative_to(target, REPOSITORY_ROOT):
        return REPOSITORY_ROOT
    curr = target
    while not curr.exists() and curr != curr.parent:
        curr = curr.parent
    return curr if curr.exists() else target


def _ensure_directory_tree_durable(
    target_directory: Path,
    boundary_directory: Path,
) -> list[Path]:
    created_dirs: list[Path] = []
    try:
        target = _assert_no_symlink_components(
            target_directory,
            "Target directory",
        )
        boundary = _assert_no_symlink_components(
            boundary_directory,
            "Boundary directory",
        )
        try:
            relative = target.relative_to(boundary)
        except ValueError as error:
            raise FixtureCatalogCLIError(
                f"Target directory {target} is outside boundary {boundary}"
            ) from error
        if not boundary.exists():
            raise FixtureCatalogCLIError(
                f"Boundary directory does not exist: {boundary}"
            )
        if boundary.is_symlink() or not boundary.is_dir():
            raise FixtureCatalogCLIError(
                f"Boundary path is not a directory: {boundary}"
            )
        current = boundary
        _fsync_directory(current)
        for part in relative.parts:
            child = current / part
            if not child.exists():
                child.mkdir()
                created_dirs.append(child)
                _fsync_directory(current)
                if child.is_symlink() or not child.is_dir():
                    raise FixtureCatalogCLIError(
                        f"Directory path component is not a directory: {child}"
                    )
                _fsync_directory(child)
                current = child
            else:
                if child.is_symlink() or not child.is_dir():
                    raise FixtureCatalogCLIError(
                        f"Directory path component is not a directory: {child}"
                    )
                _fsync_directory(child)
                current = child
        return created_dirs
    except Exception as error:
        cleanup_errors: list[str] = []
        for d in reversed(created_dirs):
            try:
                if d.exists() and not any(d.iterdir()):
                    d.rmdir()
                    _fsync_directory(d.parent)
            except Exception as d_err:
                cleanup_errors.append(_bounded_external_text(str(d_err)))
        if cleanup_errors:
            raise FixtureCatalogCLIError(
                f"Failed to ensure directory tree durability for {target_directory}: {error}; "
                + "; ".join(cleanup_errors)
            ) from error
        raise FixtureCatalogCLIError(
            f"Failed to ensure directory tree durability for {target_directory}: {error}"
        ) from error


def _is_git_tracked(path: Path, repo_root: Path) -> bool:
    repository = repo_root.resolve(strict=True)
    resolved_path = path.resolve(strict=False)
    try:
        relative_path = resolved_path.relative_to(repository).as_posix()
    except ValueError as error:
        raise FixtureCatalogCLIError(
            f"Tracked-file query is outside repository: {resolved_path}"
        ) from error
    raw = _run_git_bytes(
        ["ls-files", "-z", "--", relative_path],
        cwd=repository,
        label=f"determine tracked status for {relative_path}",
    )
    if raw == b"":
        return False
    if not raw.endswith(b"\x00"):
        raise FixtureCatalogCLIError(
            f"Malformed unterminated ls-files output for {relative_path}"
        )
    entries = raw[:-1].split(b"\x00")
    if len(entries) != 1:
        raise FixtureCatalogCLIError(
            f"Unexpected ls-files output for {relative_path}: "
            f"{_bounded_external_text(raw)}"
        )
    decoded = _decode_git_token(entries[0], "ls-files path")
    if decoded != relative_path:
        raise FixtureCatalogCLIError(
            f"Unexpected single ls-files path for {relative_path}: {decoded}"
        )
    return True


def _validate_output_destination(path: Path) -> Path:
    _walk_unresolved_path(path)
    canonical = path.resolve(strict=False)
    _walk_unresolved_path(canonical)
    if _is_relative_to(canonical, REPOSITORY_ROOT):
        if not _is_relative_to(canonical, ALLOWED_REPOSITORY_OUTPUT_ROOT):
            raise FixtureCatalogCLIError(
                "Output path inside the repository must live under .cache/athena-research/"
            )
        if _is_git_tracked(canonical, REPOSITORY_ROOT):
            raise FixtureCatalogCLIError(
                f"Refusing to overwrite tracked repository file: {canonical}"
            )
    return canonical


def _validate_transaction_paths(
    catalog_resolved: Path,
    manifest_resolved: Path,
) -> tuple[Path, Path, Path, Path]:
    if catalog_resolved == manifest_resolved:
        raise FixtureCatalogCLIError("Catalog and manifest output paths must differ")
    if (
        catalog_resolved.exists()
        and manifest_resolved.exists()
        and os.path.samefile(catalog_resolved, manifest_resolved)
    ):
        raise FixtureCatalogCLIError(
            "Catalog and manifest output destinations refer to the same file"
        )

    cat_backup = catalog_resolved.parent / f".fixture-catalog-backup-{catalog_resolved.name}"
    cat_rollback = catalog_resolved.parent / f".fixture-catalog-rollback-{catalog_resolved.name}"
    man_backup = manifest_resolved.parent / f".fixture-catalog-backup-{manifest_resolved.name}"
    man_rollback = manifest_resolved.parent / f".fixture-catalog-rollback-{manifest_resolved.name}"

    all_entries = [
        ("catalog destination", catalog_resolved),
        ("manifest destination", manifest_resolved),
        ("catalog backup", cat_backup),
        ("manifest backup", man_backup),
        ("catalog rollback", cat_rollback),
        ("manifest rollback", man_rollback),
    ]
    for i, (name_a, path_a) in enumerate(all_entries):
        res_a = path_a.resolve(strict=False)
        for j in range(i + 1, len(all_entries)):
            name_b, path_b = all_entries[j]
            res_b = path_b.resolve(strict=False)
            if res_a == res_b:
                raise FixtureCatalogCLIError(
                    f"Collision detected between {name_a} and {name_b}: {res_a}"
                )
            if path_a.exists() and path_b.exists() and os.path.samefile(path_a, path_b):
                raise FixtureCatalogCLIError(
                    f"Same-file alias collision detected between {name_a} and {name_b}: {path_a}"
                )

    for name, artifact_path in [
        ("catalog backup", cat_backup),
        ("catalog rollback", cat_rollback),
        ("manifest backup", man_backup),
        ("manifest rollback", man_rollback),
    ]:
        if artifact_path.exists() or artifact_path.is_symlink():
            raise FixtureCatalogCLIError(
                f"Stale transaction artifact exists ({name}): {artifact_path}"
            )

    return cat_backup, cat_rollback, man_backup, man_rollback


def _prepare_output(
    destination: Path,
    content: bytes,
    *,
    force: bool,
    backup_path: Path,
    rollback_path: Path,
) -> tuple[_PreparedOutput, list[Path]]:
    parent = destination.parent
    boundary = _find_boundary(parent)
    created_dirs = _ensure_directory_tree_durable(parent, boundary)
    if parent.is_symlink():
        raise FixtureCatalogCLIError(
            f"Output parent directory must not be a symlink: {parent}"
        )
    existing = destination.exists()
    if destination.is_symlink():
        raise FixtureCatalogCLIError(
            f"Output destination must be a regular non-symlink file: {destination}"
        )
    if existing:
        st = destination.lstat()
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise FixtureCatalogCLIError(
                f"Output destination must be a regular non-symlink file: {destination}"
            )
        if not force:
            raise FixtureCatalogCLIError(
                f"Output already exists: {destination}; use --force to replace untracked files"
            )
    original_bytes = None
    original_mode = None
    if existing:
        original_bytes = destination.read_bytes()
        original_mode = stat.S_IMODE(os.stat(destination).st_mode)

    staged_dir: Path | None = None
    staged_path: Path | None = None
    try:
        staged_dir = Path(tempfile.mkdtemp(prefix=".fixture-catalog-", dir=str(parent)))
        staged_path = staged_dir / destination.name
        with staged_path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as error:
        cleanup_errors: list[str] = []
        if staged_dir is not None and staged_dir.exists():
            try:
                shutil.rmtree(staged_dir)
                _fsync_directory(parent)
            except Exception as cleanup_error:
                cleanup_errors.append(_bounded_external_text(str(cleanup_error)))
        for d in reversed(created_dirs):
            try:
                if d.exists() and not any(d.iterdir()):
                    d.rmdir()
                    _fsync_directory(d.parent)
            except Exception as d_err:
                cleanup_errors.append(_bounded_external_text(str(d_err)))
        if cleanup_errors:
            raise FixtureCatalogCLIError(
                f"Preparation failed for {destination} and staging cleanup could not be proven: "
                + "; ".join([str(error)] + cleanup_errors)
            ) from error
        raise FixtureCatalogCLIError(str(error)) from error

    prepared = _PreparedOutput(
        destination=destination,
        staged_dir=staged_dir,
        staged_path=staged_path,
        existed=existing,
        original_bytes=original_bytes,
        original_mode=original_mode,
        backup_path=backup_path,
        rollback_path=rollback_path,
        created_backup=False,
        created_rollback=False,
    )
    return prepared, created_dirs


def _restore_original(prepared: _PreparedOutput) -> None:
    destination = prepared.destination
    if prepared.existed:
        if prepared.created_backup and prepared.backup_path.exists():
            os.replace(prepared.backup_path, destination)
            prepared.created_backup = False
        else:
            if prepared.original_bytes is not None:
                dest_bytes = None
                try:
                    if destination.exists() and destination.is_file():
                        dest_bytes = destination.read_bytes()
                except Exception:
                    dest_bytes = None
                if dest_bytes != prepared.original_bytes:
                    if prepared.rollback_path.exists() or prepared.rollback_path.is_symlink():
                        raise FixtureCatalogCLIError(
                            f"Stale rollback artifact exists: {prepared.rollback_path}"
                        )
                    with prepared.rollback_path.open("xb") as handle:
                        handle.write(prepared.original_bytes)
                        handle.flush()
                        os.fsync(handle.fileno())
                    prepared.created_rollback = True
                    os.replace(prepared.rollback_path, destination)
                    prepared.created_rollback = False
        if prepared.original_mode is not None and destination.exists():
            os.chmod(destination, prepared.original_mode)
        if destination.exists():
            _fsync_file(destination)
        if destination.parent.exists():
            _fsync_directory(destination.parent)
    else:
        if destination.exists():
            destination.unlink()
            if destination.parent.exists():
                _fsync_directory(destination.parent)
        if prepared.created_backup and prepared.backup_path.exists():
            prepared.backup_path.unlink()
            prepared.created_backup = False
            if destination.parent.exists():
                _fsync_directory(destination.parent)


def _commit_prepared(prepared: _PreparedOutput) -> None:
    destination = prepared.destination
    if prepared.existed:
        if prepared.backup_path.exists() or prepared.backup_path.is_symlink():
            raise FixtureCatalogCLIError(
                f"Stale backup file exists: {prepared.backup_path}"
            )
        os.replace(destination, prepared.backup_path)
        prepared.created_backup = True
        _fsync_directory(destination.parent)
    os.replace(prepared.staged_path, destination)
    _fsync_file(destination)
    _fsync_directory(destination.parent)


def _cleanup_staged_artifacts(prepared: _PreparedOutput) -> None:
    if prepared.staged_dir.exists():
        shutil.rmtree(prepared.staged_dir)
    if prepared.destination.parent.exists():
        _fsync_directory(prepared.destination.parent)


def _cleanup_safe_transient_artifacts(
    prepared_outputs: Sequence[_PreparedOutput],
    created_dirs: Sequence[Path] = (),
) -> list[str]:
    errors: list[str] = []
    for item in prepared_outputs:
        try:
            _cleanup_staged_artifacts(item)
        except Exception as error:
            errors.append(_bounded_external_text(str(error)))
    for d in reversed(created_dirs):
        try:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
                _fsync_directory(d.parent)
        except Exception as error:
            errors.append(_bounded_external_text(str(error)))
    return errors


def _cleanup_backups(prepared: _PreparedOutput) -> None:
    if prepared.created_backup and prepared.backup_path.exists():
        prepared.backup_path.unlink()
        prepared.created_backup = False
        if prepared.destination.parent.exists():
            _fsync_directory(prepared.destination.parent)
    if prepared.created_rollback and prepared.rollback_path.exists():
        prepared.rollback_path.unlink()
        prepared.created_rollback = False
        if prepared.destination.parent.exists():
            _fsync_directory(prepared.destination.parent)


def _collect_preserved_recovery_artifacts(
    prepared_outputs: Sequence[_PreparedOutput],
) -> list[Path]:
    preserved: list[Path] = []
    for item in prepared_outputs:
        if item.created_backup and item.backup_path.exists():
            preserved.append(item.backup_path)
        if item.created_rollback and item.rollback_path.exists():
            preserved.append(item.rollback_path)
    return preserved


def _cleanup_all_artifacts(
    prepared_outputs: Sequence[_PreparedOutput],
    created_dirs: Sequence[Path] = (),
) -> list[str]:
    errors = _cleanup_safe_transient_artifacts(prepared_outputs, created_dirs)
    for item in prepared_outputs:
        try:
            _cleanup_backups(item)
        except Exception as error:
            errors.append(_bounded_external_text(str(error)))
    return errors


def _rollback_prepared_outputs(prepared_outputs: Sequence[_PreparedOutput]) -> list[str]:
    errors: list[str] = []
    for prepared in reversed(prepared_outputs):
        try:
            _restore_original(prepared)
        except Exception as error:
            errors.append(_bounded_external_text(str(error)))
    return errors


def _write_outputs_atomically(
    *,
    catalog_output: Path,
    manifest_output: Path,
    catalog_bytes: bytes,
    manifest_bytes: bytes,
    force: bool,
) -> None:
    catalog_resolved = _validate_output_destination(catalog_output)
    manifest_resolved = _validate_output_destination(manifest_output)
    cat_backup, cat_rollback, man_backup, man_rollback = _validate_transaction_paths(
        catalog_resolved, manifest_resolved
    )

    prepared: list[_PreparedOutput] = []
    all_created_dirs: list[Path] = []
    try:
        catalog_prep, cat_dirs = _prepare_output(
            catalog_resolved,
            catalog_bytes,
            force=force,
            backup_path=cat_backup,
            rollback_path=cat_rollback,
        )
        prepared.append(catalog_prep)
        all_created_dirs.extend(cat_dirs)
        try:
            manifest_prep, man_dirs = _prepare_output(
                manifest_resolved,
                manifest_bytes,
                force=force,
                backup_path=man_backup,
                rollback_path=man_rollback,
            )
            prepared.append(manifest_prep)
            all_created_dirs.extend(man_dirs)
        except Exception:
            cleanup_errors = _cleanup_safe_transient_artifacts(prepared, all_created_dirs)
            if cleanup_errors:
                raise FixtureCatalogCLIError(
                    "Transaction preparation failed and transient cleanup could not be proven: "
                    + "; ".join(cleanup_errors)
                )
            raise
    except Exception as error:
        raise FixtureCatalogCLIError(str(error)) from error

    try:
        for item in prepared:
            _commit_prepared(item)
    except Exception as error:
        rollback_errors = _rollback_prepared_outputs(prepared)
        safe_cleanup_errors = _cleanup_safe_transient_artifacts(prepared, all_created_dirs)
        preserved_recovery_artifacts = _collect_preserved_recovery_artifacts(prepared)
        if rollback_errors or preserved_recovery_artifacts or safe_cleanup_errors:
            error_parts: list[str] = []
            if rollback_errors or preserved_recovery_artifacts:
                error_parts.append(
                    "Transaction rollback could not be proven; manual recovery is required"
                )
                if preserved_recovery_artifacts:
                    paths_str = ", ".join(str(p) for p in preserved_recovery_artifacts)
                    error_parts.append(f"Preserved recovery artifacts: {paths_str}")
                if rollback_errors:
                    error_parts.append("Rollback errors: " + "; ".join(rollback_errors))
            if safe_cleanup_errors:
                error_parts.append("Transient cleanup errors: " + "; ".join(safe_cleanup_errors))
            error_parts.append(f"Original failure: {_bounded_external_text(str(error))}")
            raise FixtureCatalogCLIError(". ".join(error_parts)) from error
        raise FixtureCatalogCLIError(str(error)) from error
    else:
        finalization_errors: list[str] = []
        for item in prepared:
            try:
                _cleanup_staged_artifacts(item)
                _cleanup_backups(item)
            except Exception as cleanup_error:
                finalization_errors.append(_bounded_external_text(str(cleanup_error)))
        if finalization_errors:
            rollback_errors = _rollback_prepared_outputs(prepared)
            safe_cleanup_errors = _cleanup_safe_transient_artifacts(prepared, all_created_dirs)
            preserved_recovery_artifacts = _collect_preserved_recovery_artifacts(prepared)
            if rollback_errors or preserved_recovery_artifacts or safe_cleanup_errors:
                error_parts = [
                    "Transaction finalization failed and rollback could not be proven; manual recovery is required"
                ]
                if preserved_recovery_artifacts:
                    paths_str = ", ".join(str(p) for p in preserved_recovery_artifacts)
                    error_parts.append(f"Preserved recovery artifacts: {paths_str}")
                if rollback_errors:
                    error_parts.append("Rollback errors: " + "; ".join(rollback_errors))
                if safe_cleanup_errors:
                    error_parts.append("Transient cleanup errors: " + "; ".join(safe_cleanup_errors))
                error_parts.append("Finalization errors: " + "; ".join(finalization_errors))
                raise FixtureCatalogCLIError(". ".join(error_parts))
            raise FixtureCatalogCLIError(
                "Transaction finalization failed: " + "; ".join(finalization_errors)
            )


def _compare_expected_output(expected: bytes, actual_path: Path, label: str) -> None:
    safe_path = _walk_unresolved_path(actual_path)
    canonical = actual_path.resolve(strict=False)
    _walk_unresolved_path(canonical)
    if not safe_path.is_file() or safe_path.is_symlink():
        raise FixtureCatalogCLIError(f"{label} must be a regular file: {actual_path}")
    resolved = safe_path.resolve(strict=True)
    if resolved != safe_path.resolve(strict=False):
        raise FixtureCatalogCLIError(f"{label} path resolution drifted: {actual_path}")
    actual = safe_path.read_bytes()
    if actual != expected:
        raise FixtureCatalogCLIError(f"{label} bytes differ from the expected output")


def run(
    *,
    input_path: Path,
    evidence_root: Path,
    as_of: str | datetime,
    minimum_lead_seconds: int,
    catalog_output: Path | None = None,
    manifest_output: Path | None = None,
    check_catalog: Path | None = None,
    check_manifest: Path | None = None,
    force: bool = False,
    code_state: dict[str, Any] | None = None,
) -> FixtureCatalogResult:
    if (catalog_output is None) == (check_catalog is None):
        raise FixtureCatalogCLIError(
            "Provide either generation outputs or check outputs, not both"
        )
    if (manifest_output is None) == (check_manifest is None):
        raise FixtureCatalogCLIError(
            "Provide both catalog and manifest destinations for the selected mode"
        )

    if check_catalog is not None and check_manifest is not None:
        check_cat_safe = _walk_unresolved_path(check_catalog)
        check_man_safe = _walk_unresolved_path(check_manifest)
        cat_canonical = check_catalog.resolve(strict=False)
        man_canonical = check_manifest.resolve(strict=False)
        _walk_unresolved_path(cat_canonical)
        _walk_unresolved_path(man_canonical)
        if cat_canonical == man_canonical:
            raise FixtureCatalogCLIError(
                "Check catalog and check manifest paths must differ"
            )
        if (
            check_catalog.exists()
            and check_manifest.exists()
            and os.path.samefile(check_catalog, check_manifest)
        ):
            raise FixtureCatalogCLIError(
                "Check catalog and check manifest destinations refer to the same file"
            )

    result = compile_fixture_catalog(
        input_path=input_path,
        evidence_root=evidence_root,
        as_of=parse_utc_timestamp(as_of, "as_of"),
        minimum_lead_seconds=minimum_lead_seconds,
        code_state=code_state if code_state is not None else get_code_state(REPOSITORY_ROOT),
    )
    if catalog_output is not None:
        _write_outputs_atomically(
            catalog_output=catalog_output,
            manifest_output=manifest_output or Path(),
            catalog_bytes=result.catalog_bytes,
            manifest_bytes=result.manifest_bytes,
            force=force,
        )
    else:
        assert check_catalog is not None and check_manifest is not None
        _compare_expected_output(result.catalog_bytes, check_catalog, "catalog")
        _compare_expected_output(result.manifest_bytes, check_manifest, "manifest")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile or verify a provenance-backed ATHENA fixture catalog."
    )
    parser.add_argument("--input", required=True, help="UTF-8 JSONL fixture provenance")
    parser.add_argument(
        "--evidence-root",
        required=True,
        help="Directory containing reviewed evidence files",
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="Timezone-aware UTC timestamp used for audit timing",
    )
    parser.add_argument(
        "--minimum-lead-seconds",
        type=int,
        default=0,
        help="Minimum lead time before kickoff; default 0",
    )
    parser.add_argument("--force", action="store_true", help="Replace untracked outputs")
    parser.add_argument(
        "--catalog-output",
        help="Write the strict fixture catalog JSON to this path",
    )
    parser.add_argument(
        "--manifest-output",
        help="Write the provenance manifest JSON to this path",
    )
    parser.add_argument(
        "--check-catalog",
        help="Verify the strict fixture catalog bytes against this path",
    )
    parser.add_argument(
        "--check-manifest",
        help="Verify the provenance manifest bytes against this path",
    )
    return parser


def _mode_from_args(args: argparse.Namespace) -> tuple[Path | None, Path | None, Path | None, Path | None]:
    generation = args.catalog_output or args.manifest_output
    checking = args.check_catalog or args.check_manifest
    if bool(generation) == bool(checking):
        raise FixtureCatalogCLIError(
            "Choose either generation mode or check mode, not both"
        )
    if generation and not (args.catalog_output and args.manifest_output):
        raise FixtureCatalogCLIError(
            "Generation mode requires both --catalog-output and --manifest-output"
        )
    if checking and not (args.check_catalog and args.check_manifest):
        raise FixtureCatalogCLIError(
            "Check mode requires both --check-catalog and --check-manifest"
        )
    return (
        Path(args.catalog_output) if args.catalog_output else None,
        Path(args.manifest_output) if args.manifest_output else None,
        Path(args.check_catalog) if args.check_catalog else None,
        Path(args.check_manifest) if args.check_manifest else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        catalog_output, manifest_output, check_catalog, check_manifest = _mode_from_args(args)
        run(
            input_path=Path(args.input),
            evidence_root=Path(args.evidence_root),
            as_of=args.as_of,
            minimum_lead_seconds=args.minimum_lead_seconds,
            catalog_output=catalog_output,
            manifest_output=manifest_output,
            check_catalog=check_catalog,
            check_manifest=check_manifest,
            force=args.force,
        )
    except (FixtureCatalogError, FixtureCatalogCLIError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "ALLOWED_REPOSITORY_OUTPUT_ROOT",
    "FixtureCatalogCLIError",
    "GENERATED_SAFETY_CONTRACT",
    "REPOSITORY_ROOT",
    "_cleanup_all_artifacts",
    "_cleanup_backups",
    "_cleanup_safe_transient_artifacts",
    "_cleanup_staged_artifacts",
    "_collect_preserved_recovery_artifacts",
    "_commit_prepared",
    "_compare_expected_output",
    "_ensure_directory_tree_durable",
    "_fsync_directory",
    "_fsync_file",
    "_is_git_tracked",
    "_load_kernel32",
    "_prepare_output",
    "_restore_original",
    "_rollback_prepared_outputs",
    "_win_fsync_directory",
    "_write_outputs_atomically",
    "build_parser",
    "main",
    "run",
]
