"""Strict offline importer for ATHENA prediction field-trial audit evidence."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

import domain.markets as market_contract
import domain.prediction_postmatch_audit as audit_contract
from domain.prediction_postmatch_audit import (
    PredictionPostMatchAuditError,
    build_prediction_field_trial_from_import,
    canonical_prediction_field_trial_bytes,
)


MAX_SOURCE_BYTES = 8 * 1024 * 1024
ALLOWED_OUTPUT_RELATIVE = Path("artifacts/prediction-field-trials")
EXECUTION_CODE_PATHS = (
    Path("scripts/import_prediction_field_trial.py"),
    Path("domain/prediction_postmatch_audit.py"),
    Path("domain/markets.py"),
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", flags=re.ASCII)


class PredictionFieldTrialImportError(ValueError):
    """Raised when a local field-trial import cannot be proven safe."""


def _error(message: str) -> PredictionFieldTrialImportError:
    return PredictionFieldTrialImportError(message)


def _run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise _error("Git is required to verify importer execution provenance") from exc


def _require_git_output(
    result: subprocess.CompletedProcess[str],
    label: str,
) -> str:
    if result.returncode != 0:
        raise _error(f"could not resolve {label} for importer execution provenance")
    output = result.stdout.strip()
    if not output:
        raise _error(f"Git returned an empty {label} for importer execution provenance")
    return output


def _assert_executing_repository(repository: Path) -> None:
    expected_paths = tuple((repository / path).resolve(strict=True) for path in EXECUTION_CODE_PATHS)
    actual_paths = (
        Path(__file__).resolve(strict=True),
        Path(audit_contract.__file__).resolve(strict=True),
        Path(market_contract.__file__).resolve(strict=True),
    )
    if actual_paths != expected_paths:
        raise _error(
            "repository_root does not contain the importer/contract/market code being executed"
        )


def _assert_tracked_execution_code_clean(repository: Path) -> None:
    path_arguments = tuple(path.as_posix() for path in EXECUTION_CODE_PATHS)
    tracked = _run_git(
        repository,
        "ls-files",
        "--error-unmatch",
        "--",
        *path_arguments,
    )
    if tracked.returncode != 0:
        raise _error("importer/contract/market execution code must be tracked by Git")
    clean = _run_git(repository, "diff", "--quiet", "HEAD", "--", *path_arguments)
    if clean.returncode == 1:
        raise _error(
            "tracked importer/contract/market code differs from repository HEAD"
        )
    if clean.returncode != 0:
        raise _error("could not verify tracked importer/contract/market code cleanliness")


def _verify_execution_commit(repository_root: Path, claimed_sha: str) -> str:
    if type(claimed_sha) is not str or _GIT_SHA_RE.fullmatch(claimed_sha) is None:
        raise _error("execution_commit_sha must be 40 lowercase hexadecimal characters")
    try:
        repository = repository_root.resolve(strict=True)
    except OSError as exc:
        raise _error("repository_root could not be resolved") from exc
    top_level = Path(
        _require_git_output(
            _run_git(repository, "rev-parse", "--show-toplevel"),
            "repository top level",
        )
    ).resolve(strict=True)
    if top_level != repository:
        raise _error("repository_root must be the exact Git repository top level")
    head = _require_git_output(
        _run_git(repository, "rev-parse", "--verify", "HEAD"),
        "repository HEAD",
    )
    if _GIT_SHA_RE.fullmatch(head) is None:
        raise _error("repository HEAD is not an exact 40-character commit SHA")
    if claimed_sha != head:
        raise _error("execution_commit_sha does not equal git rev-parse HEAD")
    _assert_executing_repository(repository)
    _assert_tracked_execution_code_clean(repository)
    return head


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _error(f"invalid JSON constant: {value}")


def strict_json_loads(raw: bytes) -> Any:
    if type(raw) is not bytes or not raw:
        raise _error("source JSON must be non-empty exact bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _error("source JSON must be valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except PredictionFieldTrialImportError:
        raise
    except json.JSONDecodeError as exc:
        raise _error("source is not valid JSON") from exc


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor) if absolute.anchor else Path.cwd()
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise _error(f"{label} contains a forbidden symlink component")


def _repository_path(path: Path, *, repository_root: Path, label: str) -> tuple[Path, str]:
    repository = repository_root.resolve(strict=True)
    candidate = path if path.is_absolute() else repository / path
    if ".." in path.parts:
        raise _error(f"{label} must not contain traversal")
    _reject_symlink_components(candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(repository)
    except (OSError, ValueError) as exc:
        raise _error(f"{label} must resolve inside the repository") from exc
    return resolved, relative.as_posix()


def _read_source(path: Path, *, repository_root: Path) -> tuple[bytes, str]:
    resolved, relative = _repository_path(
        path,
        repository_root=repository_root,
        label="source path",
    )
    try:
        before = resolved.stat()
    except OSError as exc:
        raise _error("source JSON could not be inspected") from exc
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SOURCE_BYTES:
        raise _error("source JSON must be a bounded non-empty regular file")
    try:
        raw = resolved.read_bytes()
        after = resolved.stat()
    except OSError as exc:
        raise _error("source JSON could not be read") from exc
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(raw) != before.st_size:
        raise _error("source JSON changed while being read")
    return raw, relative


def _output_path(path: Path, *, repository_root: Path) -> Path:
    repository = repository_root.resolve(strict=True)
    allowed_root = repository / ALLOWED_OUTPUT_RELATIVE
    candidate = path if path.is_absolute() else repository / path
    if ".." in path.parts:
        raise _error("output path must not contain traversal")
    _reject_symlink_components(candidate.parent, "output path")
    try:
        relative = candidate.resolve(strict=False).relative_to(
            allowed_root.resolve(strict=False)
        )
    except ValueError as exc:
        raise _error("output path must be under artifacts/prediction-field-trials") from exc
    if len(relative.parts) != 1 or candidate.suffix != ".json":
        raise _error("output must be one JSON file directly under the audit artifact root")
    return candidate


def _read_existing(path: Path) -> bytes:
    _reject_symlink_components(path, "existing output")
    if path.is_symlink():
        raise _error("existing output must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise _error("existing output could not be inspected") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        raise _error("existing output is not a non-empty regular file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _error("existing output could not be read") from exc
    if len(raw) != metadata.st_size:
        raise _error("existing output changed while being read")
    return raw


def _sync_directory(path: Path) -> bool:
    if os.name == "nt":
        return False
    unsupported = {
        errno.EBADF,
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno in unsupported:
            return False
        raise _error("could not durably synchronize audit artifact directory") from exc
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno in unsupported:
                return False
            raise _error("could not durably synchronize audit artifact directory") from exc
        finally:
            os.close(descriptor)
    except PredictionFieldTrialImportError:
        raise
    return True


def _write_idempotent(path: Path, content: bytes) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _error("could not create audit artifact directory") from exc
    _reject_symlink_components(path.parent, "output directory")
    if path.exists() or path.is_symlink():
        if _read_existing(path) == content:
            return "IDENTICAL_REIMPORT_NOOP"
        raise _error("refusing to overwrite a different existing audit artifact")
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
        return "AUDIT_ARTIFACT_CREATED"
    except FileExistsError:
        if _read_existing(path) == content:
            return "IDENTICAL_REIMPORT_NOOP"
        raise _error("refusing to overwrite a concurrently created different artifact")
    except OSError as exc:
        raise _error("could not durably write audit artifact") from exc


def import_field_trial(
    *,
    source: Path,
    output: Path,
    repository_root: Path,
    execution_commit_sha: str,
) -> dict[str, Any]:
    """Import local JSON only; no provider or browser acquisition is performed."""

    verified_execution_sha = _verify_execution_commit(
        repository_root,
        execution_commit_sha,
    )
    raw, source_relative = _read_source(source, repository_root=repository_root)
    payload = strict_json_loads(raw)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        trial = build_prediction_field_trial_from_import(
            payload,
            source_repository_path=source_relative,
            source_sha256=source_sha256,
            source_size=len(raw),
            execution_commit_sha=verified_execution_sha,
        )
        artifact = canonical_prediction_field_trial_bytes(trial)
    except PredictionPostMatchAuditError as exc:
        raise _error(str(exc)) from exc
    destination = _output_path(output, repository_root=repository_root)
    operation = _write_idempotent(destination, artifact)
    return {
        "status": operation,
        "artifact_path": destination.relative_to(
            repository_root.resolve(strict=True)
        ).as_posix(),
        "canonical_sha256": trial.canonical_sha256,
        "trial_identity": trial.trial_identity,
        "reconstruction_status": trial.reconstruction_status.value,
        "declared_leg_count": trial.declared_leg_count,
        "reconstructed_leg_count": trial.reconstructed_leg_count,
        "unresolved_leg_count": trial.unresolved_leg_count,
        "contract_origin_sha": trial.creation_import_identity.contract_origin_sha,
        "execution_commit_sha": trial.creation_import_identity.execution_commit_sha,
        "source_sha256": source_sha256,
        "network_requests_performed": False,
        "model_state_modified": False,
        "pricing_state_modified": False,
        "selection_state_modified": False,
        "bet_authority_granted": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import a preserved local ATHENA prediction field trial into the "
            "immutable post-match audit ledger. No network acquisition occurs."
        )
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument(
        "--execution-commit-sha",
        required=True,
        help="Exact 40-character Git commit that executed this import",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = import_field_trial(
            source=Path(args.source),
            output=Path(args.output),
            repository_root=Path(args.repository_root),
            execution_commit_sha=args.execution_commit_sha,
        )
    except PredictionFieldTrialImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            receipt,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALLOWED_OUTPUT_RELATIVE",
    "EXECUTION_CODE_PATHS",
    "MAX_SOURCE_BYTES",
    "PredictionFieldTrialImportError",
    "import_field_trial",
    "main",
    "strict_json_loads",
]
