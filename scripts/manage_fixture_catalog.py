"""Compile or verify a provenance-backed ATHENA fixture catalog."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import ctypes
import ctypes.wintypes
import os
from pathlib import Path
import shutil
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


@dataclass(frozen=True)
class _PreparedOutput:
    destination: Path
    staged_dir: Path
    staged_path: Path
    existed: bool
    original_bytes: bytes | None
    original_mode: int | None
    backup_path: Path
    replaced: bool = False


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


def _require_full_git_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40:
        raise FixtureCatalogCLIError(f"{label} must be a full Git SHA")
    if any(ch not in "0123456789abcdefABCDEF" for ch in value):
        raise FixtureCatalogCLIError(f"{label} must be a full Git SHA")
    return value.lower()


def _win_fsync_directory(path: Path) -> None:
    kernel32 = getattr(ctypes.windll, "kernel32", None)
    if kernel32 is None:
        raise FixtureCatalogCLIError("kernel32 is not available on this platform")
    invalid_handle = ctypes.c_void_p(-1).value
    handle = kernel32.CreateFileW(
        str(path),
        0xC0000000,
        0x00000007,
        None,
        3,
        0x02000000,
        None,
    )
    if handle in (0, None, invalid_handle):
        err = getattr(kernel32, "GetLastError", lambda: ctypes.get_last_error())()
        raise FixtureCatalogCLIError(
            f"CreateFileW failed for directory fsync: {path} "
            f"(winerror={err})"
        )
    flush_error: str | None = None
    close_error: str | None = None
    try:
        if not kernel32.FlushFileBuffers(handle):
            err = getattr(kernel32, "GetLastError", lambda: ctypes.get_last_error())()
            flush_error = (
                f"FlushFileBuffers failed for {path} "
                f"(winerror={err})"
            )
    finally:
        if not kernel32.CloseHandle(handle):
            err = getattr(kernel32, "GetLastError", lambda: ctypes.get_last_error())()
            close_error = (
                f"CloseHandle failed for {path} "
                f"(winerror={err})"
            )
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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


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
    decoded_entries = [
        _decode_git_token(entry, "ls-files path")
        for entry in entries
    ]
    if len(decoded_entries) != 1:
        raise FixtureCatalogCLIError(
            f"Unexpected ls-files output for {relative_path}: "
            f"{_bounded_external_text(raw)}"
        )
    return decoded_entries[0] == relative_path


def _validate_output_destination(path: Path) -> Path:
    resolved = _walk_unresolved_path(path)
    if _is_relative_to(resolved, REPOSITORY_ROOT) and not _is_relative_to(
        resolved, ALLOWED_REPOSITORY_OUTPUT_ROOT
    ):
        raise FixtureCatalogCLIError(
            "Output path inside the repository must live under .cache/athena-research/"
        )
    if _is_relative_to(resolved, REPOSITORY_ROOT) and _is_git_tracked(
        resolved, REPOSITORY_ROOT
    ):
        raise FixtureCatalogCLIError(
            f"Refusing to overwrite tracked repository file: {resolved}"
        )
    return resolved.resolve(strict=False)


def _prepare_output(destination: Path, content: bytes, *, force: bool) -> _PreparedOutput:
    resolved = _validate_output_destination(destination)
    parent = resolved.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise FixtureCatalogCLIError(
            f"Output parent directory must not be a symlink: {parent}"
        )
    existing = resolved.exists()
    if resolved.is_symlink():
        raise FixtureCatalogCLIError(f"Output file must be a regular non-symlink file: {resolved}")
    if existing and not force:
        raise FixtureCatalogCLIError(
            f"Output already exists: {resolved}; use --force to replace untracked files"
        )
    original_bytes = None
    original_mode = None
    if existing:
        original_bytes = resolved.read_bytes()
        original_mode = os.stat(resolved).st_mode & 0o777
    staged_dir = Path(tempfile.mkdtemp(prefix=".fixture-catalog-", dir=str(parent)))
    staged_path = staged_dir / resolved.name
    with staged_path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return _PreparedOutput(
        destination=resolved,
        staged_dir=staged_dir,
        staged_path=staged_path,
        existed=existing,
        original_bytes=original_bytes,
        original_mode=original_mode,
        backup_path=parent / f".fixture-catalog-backup-{resolved.name}",
    )


def _restore_original(prepared: _PreparedOutput) -> None:
    destination = prepared.destination
    if prepared.existed:
        if prepared.backup_path.exists():
            if destination.exists():
                destination.unlink()
            os.replace(prepared.backup_path, destination)
        else:
            if destination.exists():
                destination.unlink()
            if prepared.original_bytes is None:
                raise FixtureCatalogCLIError(
                    f"Could not restore original output: {destination}"
                )
            rollback = destination.parent / f".fixture-catalog-rollback-{destination.name}"
            with rollback.open("xb") as handle:
                handle.write(prepared.original_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(rollback, destination)
        if prepared.original_mode is not None:
            os.chmod(destination, prepared.original_mode)
        _fsync_file(destination)
        _fsync_directory(destination.parent)
    elif destination.exists():
        destination.unlink()
        _fsync_directory(destination.parent)


def _commit_prepared(prepared: _PreparedOutput) -> None:
    destination = prepared.destination
    try:
        if prepared.existed:
            if prepared.backup_path.exists() or prepared.backup_path.is_symlink():
                raise FixtureCatalogCLIError(
                    f"Stale backup file exists: {prepared.backup_path}"
                )
            os.replace(destination, prepared.backup_path)
            _fsync_directory(destination.parent)
        os.replace(prepared.staged_path, destination)
        _fsync_file(destination)
        _fsync_directory(destination.parent)
    except Exception as error:
        try:
            if prepared.backup_path.exists():
                if destination.exists():
                    destination.unlink()
                os.replace(prepared.backup_path, destination)
                if prepared.original_mode is not None:
                    os.chmod(destination, prepared.original_mode)
                _fsync_file(destination)
                _fsync_directory(destination.parent)
        except Exception as restore_error:  # pragma: no cover - defensive
            raise FixtureCatalogCLIError(
                f"Failed to restore original output after commit failure: {restore_error}"
            ) from error
        raise FixtureCatalogCLIError(str(error)) from error


def _cleanup_staged_artifacts(prepared: _PreparedOutput) -> None:
    if prepared.staged_dir.exists():
        shutil.rmtree(prepared.staged_dir)
    if prepared.destination.parent.exists():
        _fsync_directory(prepared.destination.parent)


def _cleanup_backups(prepared: _PreparedOutput) -> None:
    if prepared.backup_path.exists():
        prepared.backup_path.unlink()
    if prepared.destination.parent.exists():
        _fsync_directory(prepared.destination.parent)


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
    if catalog_resolved == manifest_resolved:
        raise FixtureCatalogCLIError("Catalog and manifest output paths must differ")
    prepared: list[_PreparedOutput] = []
    try:
        prepared.append(_prepare_output(catalog_resolved, catalog_bytes, force=force))
        try:
            prepared.append(_prepare_output(manifest_resolved, manifest_bytes, force=force))
        except Exception:
            cleanup_errors: list[str] = []
            for item in reversed(prepared):
                try:
                    _cleanup_staged_artifacts(item)
                except Exception as cleanup_error:
                    cleanup_errors.append(_bounded_external_text(str(cleanup_error)))
            if cleanup_errors:
                raise FixtureCatalogCLIError(
                    "Transaction preparation failed and cleanup could not be proven: "
                    + "; ".join(cleanup_errors)
                )
            raise
    except Exception as error:
        raise FixtureCatalogCLIError(str(error)) from error
    committed: list[_PreparedOutput] = []
    try:
        for item in prepared:
            _commit_prepared(item)
            committed.append(item)
    except Exception as error:
        rollback_errors = _rollback_prepared_outputs(committed)
        cleanup_errors: list[str] = []
        for item in prepared:
            try:
                _cleanup_staged_artifacts(item)
                _cleanup_backups(item)
            except Exception as cleanup_error:
                cleanup_errors.append(_bounded_external_text(str(cleanup_error)))
        if rollback_errors or cleanup_errors:
            details = "; ".join(rollback_errors + cleanup_errors)
            raise FixtureCatalogCLIError(
                "Transaction rollback could not be proven: " + details
            ) from error
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
            rollback_errors = _rollback_prepared_outputs(committed)
            if rollback_errors:
                raise FixtureCatalogCLIError(
                    "Transaction rollback could not be proven: "
                    + "; ".join(finalization_errors + rollback_errors)
                )
            raise FixtureCatalogCLIError(
                "Transaction finalization failed: " + "; ".join(finalization_errors)
            )


def _compare_expected_output(expected: bytes, actual_path: Path, label: str) -> None:
    safe_path = _walk_unresolved_path(actual_path)
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
    "_compare_expected_output",
    "_commit_prepared",
    "_fsync_directory",
    "_fsync_file",
    "_prepare_output",
    "_restore_original",
    "_write_outputs_atomically",
    "build_parser",
    "main",
    "run",
]
