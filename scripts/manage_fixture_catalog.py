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


def _require_full_git_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40:
        raise FixtureCatalogCLIError(f"{label} must be a full Git SHA")
    if any(ch not in "0123456789abcdefABCDEF" for ch in value):
        raise FixtureCatalogCLIError(f"{label} must be a full Git SHA")
    return value.lower()


def _win_fsync_directory(path: Path) -> None:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateFileW(
        ctypes.wintypes.LPCWSTR(str(path)),
        0x80000000,
        0x00000007,
        None,
        3,
        0x02000000,
        None,
    )
    if handle == ctypes.wintypes.HANDLE(-1).value:
        return
    try:
        kernel32.FlushFileBuffers(handle)
    finally:
        kernel32.CloseHandle(handle)


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
    return absolute.resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_git_tracked(path: Path, repo_root: Path) -> bool:
    try:
        relative = path.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        check=False,
        shell=False,
    )
    return proc.returncode == 0


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
    return resolved


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


def _cleanup_prepared(prepared: _PreparedOutput) -> None:
    if prepared.backup_path.exists():
        prepared.backup_path.unlink()
    if prepared.staged_dir.exists():
        shutil.rmtree(prepared.staged_dir)
    if prepared.destination.parent.exists():
        _fsync_directory(prepared.destination.parent)


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
        object.__setattr__(prepared, "replaced", True)
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


def _remove_prepared_artifacts(prepared: _PreparedOutput) -> None:
    try:
        if prepared.backup_path.exists():
            prepared.backup_path.unlink()
    finally:
        if prepared.staged_dir.exists():
            shutil.rmtree(prepared.staged_dir)
    if prepared.destination.parent.exists():
        _fsync_directory(prepared.destination.parent)


def _write_outputs_atomically(
    *,
    catalog_output: Path,
    manifest_output: Path,
    catalog_bytes: bytes,
    manifest_bytes: bytes,
    force: bool,
) -> None:
    prepared_catalog = _prepare_output(catalog_output, catalog_bytes, force=force)
    prepared_manifest = _prepare_output(manifest_output, manifest_bytes, force=force)
    committed: list[_PreparedOutput] = []
    try:
        for prepared in (prepared_catalog, prepared_manifest):
            _commit_prepared(prepared)
            committed.append(prepared)
    except Exception as error:
        rollback_errors: list[str] = []
        for prepared in reversed(committed):
            try:
                _restore_original(prepared)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        for prepared in (prepared_catalog, prepared_manifest):
            try:
                _remove_prepared_artifacts(prepared)
            except Exception as cleanup_error:
                rollback_errors.append(str(cleanup_error))
        if rollback_errors:
            raise FixtureCatalogCLIError(
                "Transaction rollback could not be proven: "
                + "; ".join(rollback_errors)
            ) from error
        raise FixtureCatalogCLIError(str(error)) from error
    else:
        cleanup_errors: list[str] = []
        for prepared in (prepared_catalog, prepared_manifest):
            try:
                _remove_prepared_artifacts(prepared)
            except Exception as cleanup_error:
                cleanup_errors.append(str(cleanup_error))
        if cleanup_errors:
            raise FixtureCatalogCLIError(
                "Output cleanup could not be proven: " + "; ".join(cleanup_errors)
            )


def _compare_expected_output(expected: bytes, actual_path: Path, label: str) -> None:
    if not actual_path.is_file() or actual_path.is_symlink():
        raise FixtureCatalogCLIError(f"{label} must be a regular file: {actual_path}")
    actual = actual_path.read_bytes()
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
    "_remove_prepared_artifacts",
    "_restore_original",
    "_write_outputs_atomically",
    "build_parser",
    "main",
    "run",
]
