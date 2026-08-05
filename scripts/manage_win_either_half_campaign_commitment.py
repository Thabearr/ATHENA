"""Create, check, or validate Stage 5B4 Win Either Half campaign commitments."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

from domain.win_either_half_campaign_commitment import (  # noqa: E402
    ATTESTATION_DATASET_NAME,
    CAMPAIGN_ID_PATTERN,
    COMMITMENT_ROOT,
    DECLARATION_DATASET_NAME,
    DECLARATION_STATUS,
    DEFAULT_PROTOCOL_PATH,
    DEFAULT_STAGE_5B3_PROTOCOL_PATH,
    GENERATED_SAFETY_CONTRACT,
    PROTOCOL_DATASET_NAME,
    SCHEMA_VERSION,
    STAGE_5B3_MANIFEST_FILENAME,
    STAGE_5B3_SUMMARY_FILENAME,
    STAGE_5B3_TASKS_FILENAME,
    CampaignCommitmentError,
    CommitmentDeclaration,
    DeadlineValidationResult,
    FileIdentity,
    assert_no_forbidden_fields,
    build_commitment_declaration,
    build_expected_protocol_contract,
    canonical_json_bytes,
    parse_utc,
    serialize_utc,
    sha256_bytes,
    validate_declaration_mapping,
    validate_deadline,
    validate_git_sha,
    validate_protocol_contract,
    validate_sha256,
    validate_stage_5b3_bundle,
    validate_stage_5b3_protocol,
)
from scripts.freeze_evidence_baseline import get_code_state  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRACKED_COMMITMENT_ROOT = REPOSITORY_ROOT / COMMITMENT_ROOT


class CampaignCommitmentExportError(ValueError):
    """Raised when campaign commitment export or verification fails closed."""


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise CampaignCommitmentExportError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        return path.read_bytes()
    except OSError as error:
        raise CampaignCommitmentExportError(
            f"Could not read {label}: {path}"
        ) from error


def _read_json(path: Path, label: str) -> tuple[bytes, Mapping[str, Any]]:
    raw = _read_bytes(path, label)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignCommitmentExportError(
            f"{label} must be valid UTF-8 JSON"
        ) from error
    if not isinstance(payload, Mapping):
        raise CampaignCommitmentExportError(f"{label} must be a JSON object")
    return raw, payload


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _assert_no_symlink_components(path: Path, label: str) -> Path:
    unresolved = path.absolute()
    curr = unresolved
    while curr != curr.parent:
        if curr.is_symlink():
            raise CampaignCommitmentExportError(
                f"{label} contains forbidden symlink path component: {curr}"
            )
        curr = curr.parent
    return path.resolve(strict=False)


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(str(path), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_file(path: Path) -> None:
    mode = "rb+" if os.name == "nt" else "rb"
    with path.open(mode) as handle:
        handle.flush()
        os.fsync(handle.fileno())


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
        raise CampaignCommitmentExportError(
            f"Git process execution failed ({label}): "
            f"{_bounded_external_text(str(error))}"
        ) from error
    if result.returncode not in accepted_returncodes:
        raise CampaignCommitmentExportError(
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


def _run_git_text(
    args: Sequence[str],
    *,
    cwd: Path,
    label: str,
    accepted_returncodes: frozenset[int] = frozenset({0}),
) -> str:
    raw = _run_git_bytes(
        args,
        cwd=cwd,
        label=label,
        accepted_returncodes=accepted_returncodes,
    )
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise CampaignCommitmentExportError(
            f"Git output was not valid UTF-8 ({label})"
        ) from error


def _require_commit(
    repository: Path,
    sha: str,
    label: str,
) -> str:
    validated_sha = validate_git_sha(sha, label)
    _run_git_bytes(
        ["cat-file", "-e", f"{validated_sha}^{{commit}}"],
        cwd=repository,
        label=f"verify {label} commit object",
    )
    return validated_sha


def _require_ancestor(
    repository: Path,
    ancestor_sha: str,
    descendant_sha: str,
    label: str,
) -> None:
    proc = _run_git_process(
        [
            "merge-base",
            "--is-ancestor",
            ancestor_sha,
            descendant_sha,
        ],
        cwd=repository,
        label=label,
        accepted_returncodes=frozenset({0, 1}),
    )
    if proc.returncode == 1:
        raise CampaignCommitmentExportError(
            f"{ancestor_sha} is not an ancestor of {descendant_sha}"
        )


def _decode_git_token(token: bytes, label: str) -> str:
    try:
        value = token.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise CampaignCommitmentExportError(
            f"Git {label} was not valid UTF-8"
        ) from error
    if not value:
        raise CampaignCommitmentExportError(
            f"Git {label} was unexpectedly empty"
        )
    return value


def _parse_name_status_z(
    raw: bytes,
) -> list[tuple[str, list[str]]]:
    if raw == b"":
        return []
    if not raw.endswith(b"\x00"):
        raise CampaignCommitmentExportError(
            "Malformed unterminated NUL-delimited Git diff: missing terminal NUL"
        )
    tokens = raw[:-1].split(b"\x00")
    records: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(tokens):
        status = _decode_git_token(tokens[index], "diff status")
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if index + path_count > len(tokens):
            raise CampaignCommitmentExportError(
                f"Malformed truncated NUL-delimited Git diff for status {status}"
            )
        paths = [
            _decode_git_token(
                tokens[index + offset],
                "diff path",
            )
            for offset in range(path_count)
        ]
        index += path_count
        records.append((status, paths))
    return records


def _parse_single_ls_tree_record(
    raw: bytes | str,
    expected_path: str,
    label: str = "ls-tree record",
) -> tuple[str, str]:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not raw:
        raise CampaignCommitmentExportError(
            f"File {expected_path} not found in Git tree"
        )
    if not raw.endswith(b"\x00"):
        raise CampaignCommitmentExportError(
            f"Malformed unterminated ls-tree output for {expected_path}"
        )
    records = raw[:-1].split(b"\x00")
    if len(records) > 1:
        raise CampaignCommitmentExportError(
            f"Expected exactly one ls-tree record for {expected_path}, got multiple entries ({len(records)})"
        )
    if not records[0]:
        raise CampaignCommitmentExportError(
            f"File {expected_path} not found in Git tree"
        )
    try:
        metadata, raw_path = records[0].split(b"\t", 1)
        mode, object_type, object_sha = metadata.decode(
            "ascii",
            errors="strict",
        ).split(" ")
    except (ValueError, UnicodeDecodeError) as error:
        raise CampaignCommitmentExportError(
            f"Malformed ls-tree record for {expected_path}"
        ) from error
    actual_path = _decode_git_token(raw_path, "ls-tree path")
    if actual_path != expected_path:
        raise CampaignCommitmentExportError(
            f"ls-tree path did not match requested path: expected {expected_path}, "
            f"got {actual_path}"
        )
    if object_type != "blob":
        raise CampaignCommitmentExportError(
            f"expected blob for {expected_path}, got {object_type}"
        )
    try:
        object_sha = validate_git_sha(
            object_sha,
            f"ls-tree object SHA for {expected_path}",
        )
    except CampaignCommitmentError as error:
        raise CampaignCommitmentExportError(str(error)) from error

    return mode, object_sha


def _is_git_tracked(path: Path, repo_root: Path) -> bool:
    repository = repo_root.resolve(strict=True)
    resolved_path = path.resolve(strict=False)
    try:
        relative_path = resolved_path.relative_to(repository).as_posix()
    except ValueError as error:
        raise CampaignCommitmentExportError(
            f"Tracked-file query is outside repository: {resolved_path}"
        ) from error
    raw = _run_git_bytes(
        [
            "ls-files",
            "-z",
            "--",
            relative_path,
        ],
        cwd=repository,
        label=f"determine tracked status for {relative_path}",
    )
    if raw == b"":
        return False
    if not raw.endswith(b"\x00"):
        raise CampaignCommitmentExportError(
            f"Malformed unterminated ls-files output for {relative_path}"
        )
    entries = raw[:-1].split(b"\x00")
    decoded_entries = [
        _decode_git_token(entry, "ls-files path")
        for entry in entries
    ]
    return relative_path in decoded_entries


def _remove_tree_strict(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _ensure_directory_tree_durable(
    target_directory: Path,
    boundary_directory: Path,
) -> None:
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
            raise CampaignCommitmentExportError(
                f"Target directory {target} is outside boundary {boundary}"
            ) from error
        current = boundary
        _fsync_dir(current)
        for part in relative.parts:
            current = current / part
            if not current.exists():
                current.mkdir()
            elif current.is_symlink() or not current.is_dir():
                raise CampaignCommitmentExportError(
                    f"Directory path component is not a directory: {current}"
                )
            _fsync_dir(current)
    except OSError as error:
        raise CampaignCommitmentExportError(
            f"Failed to ensure directory tree durability for {target_directory}: {error}"
        ) from error


def _write_file_atomically(
    destination: Path,
    content: bytes,
    *,
    force: bool = False,
    is_git_tracked_check: bool = False,
    boundary_directory: Path | None = None,
) -> None:
    resolved_destination = _assert_no_symlink_components(
        destination,
        "Output destination",
    )
    parent = _assert_no_symlink_components(
        resolved_destination.parent,
        "Output parent directory",
    )
    if boundary_directory is not None:
        boundary = boundary_directory
    else:
        try:
            parent.relative_to(REPOSITORY_ROOT)
            boundary = REPOSITORY_ROOT
        except ValueError:
            boundary = next(
                (p for p in [parent, *parent.parents] if p.exists()),
                parent,
            )
    _ensure_directory_tree_durable(parent, boundary)
    destination_existed = resolved_destination.exists()
    if destination_existed and not force:
        raise CampaignCommitmentExportError(
            f"Output file already exists: {resolved_destination}; "
            "use --force only for an untracked file"
        )
    if destination_existed and is_git_tracked_check:
        try:
            is_tracked = _is_git_tracked(resolved_destination, boundary)
        except CampaignCommitmentExportError:
            is_tracked = False
        if is_tracked:
            raise CampaignCommitmentExportError(
                "Refusing to overwrite Git-tracked commitment file: "
                f"{resolved_destination}"
            )
    original_bytes: bytes | None = None
    original_mode: int | None = None
    if destination_existed:
        if (
            resolved_destination.is_symlink()
            or not resolved_destination.is_file()
        ):
            raise CampaignCommitmentExportError(
                "Existing destination must be a regular non-symlink file"
            )
        original_bytes = resolved_destination.read_bytes()
        original_mode = stat.S_IMODE(
            resolved_destination.stat().st_mode
        )
    backup = parent / (
        f".stage5b4-backup-{resolved_destination.name}"
    )
    if backup.exists() or backup.is_symlink():
        raise CampaignCommitmentExportError(
            f"Stale transaction backup exists: {backup}"
        )
    temporary_directory = Path(
        tempfile.mkdtemp(
            prefix=".stage5b4-transaction-",
            dir=parent,
        )
    )
    staged = temporary_directory / resolved_destination.name
    backup_created = False
    try:
        with staged.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if destination_existed:
            os.replace(resolved_destination, backup)
            backup_created = True
            _fsync_dir(parent)
        os.replace(staged, resolved_destination)
        _fsync_file(resolved_destination)
        _fsync_dir(parent)
        _remove_tree_strict(temporary_directory)
        _fsync_dir(parent)
        if backup_created:
            backup.unlink()
            backup_created = False
            _fsync_dir(parent)
        return
    except Exception as original_error:
        rollback_errors: list[str] = []

        def record_failure(
            action: str,
            error: BaseException,
        ) -> None:
            rollback_errors.append(
                f"{action}: {_bounded_external_text(str(error))}"
            )

        if destination_existed:
            restored = False
            if backup.exists():
                try:
                    if resolved_destination.exists():
                        resolved_destination.unlink()
                        try:
                            _fsync_dir(parent)
                        except Exception as fsync_err:
                            record_failure("fsync parent during unlink", fsync_err)
                    os.replace(backup, resolved_destination)
                    backup_created = False
                    if original_mode is not None:
                        os.chmod(
                            resolved_destination,
                            original_mode,
                        )
                    restored = True
                except Exception as error:
                    record_failure("restore backup", error)
                if restored:
                    try:
                        _fsync_file(resolved_destination)
                    except Exception as error:
                        record_failure("fsync restored destination", error)
                    try:
                        _fsync_dir(parent)
                    except Exception as error:
                        record_failure("fsync parent after restore", error)
            if not restored:
                try:
                    if original_bytes is None:
                        raise RuntimeError(
                            "original bytes were not captured"
                        )
                    rollback_stage = parent / (
                        ".stage5b4-rollback-"
                        f"{resolved_destination.name}"
                    )
                    if (
                        rollback_stage.exists()
                        or rollback_stage.is_symlink()
                    ):
                        raise RuntimeError(
                            "stale rollback path exists: "
                            f"{rollback_stage}"
                        )
                    with rollback_stage.open("xb") as handle:
                        handle.write(original_bytes)
                        handle.flush()
                        os.fsync(handle.fileno())
                    if original_mode is not None:
                        os.chmod(
                            rollback_stage,
                            original_mode,
                        )
                    os.replace(
                        rollback_stage,
                        resolved_destination,
                    )
                    restored = True
                except Exception as error:
                    record_failure(
                        "recreate original destination",
                        error,
                    )
                if restored:
                    try:
                        _fsync_file(resolved_destination)
                    except Exception as error:
                        record_failure("fsync recreated destination", error)
                    try:
                        _fsync_dir(parent)
                    except Exception as error:
                        record_failure("fsync parent after recreate", error)
            if restored:
                try:
                    restored_bytes = (
                        resolved_destination.read_bytes()
                    )
                    if restored_bytes != original_bytes:
                        raise RuntimeError(
                            "restored bytes differ from original"
                        )
                except Exception as error:
                    record_failure(
                        "verify restored bytes",
                        error,
                    )
        else:
            if resolved_destination.exists():
                try:
                    resolved_destination.unlink()
                except Exception as error:
                    record_failure(
                        "remove newly installed destination",
                        error,
                    )
                try:
                    _fsync_dir(parent)
                except Exception as error:
                    record_failure(
                        "fsync parent after removing destination",
                        error,
                    )
        if staged.exists():
            try:
                staged.unlink()
            except Exception as error:
                record_failure("remove staged file", error)
        if temporary_directory.exists():
            try:
                _remove_tree_strict(temporary_directory)
                _fsync_dir(parent)
            except Exception as error:
                record_failure(
                    "remove transaction directory",
                    error,
                )
        if backup.exists():
            try:
                prior_state_proven = (
                    destination_existed
                    and original_bytes is not None
                    and resolved_destination.exists()
                    and resolved_destination.read_bytes()
                    == original_bytes
                )
                if not prior_state_proven:
                    raise RuntimeError(
                        "prior state was not proven restored"
                    )
                backup.unlink()
                _fsync_dir(parent)
            except Exception as error:
                record_failure("clean backup", error)
        if rollback_errors:
            raise CampaignCommitmentExportError(
                "Atomic file write failed and rollback was incomplete: "
                f"{_bounded_external_text(str(original_error))}; "
                + "; ".join(rollback_errors)
            ) from original_error
        raise CampaignCommitmentExportError(
            "Atomic file write failed; prior state was restored: "
            f"{_bounded_external_text(str(original_error))}"
        ) from original_error


def create_commitment(
    *,
    tasks_path: Path,
    summary_path: Path,
    manifest_path: Path,
    stage_5b3_protocol_path: Path,
    commitment_protocol_path: Path,
    output_path: Path,
    force: bool,
    code_state: Mapping[str, Any],
) -> tuple[str, bytes]:
    tracked_clean = code_state.get("tracked_worktree_clean")
    if tracked_clean is not True:
        raise CampaignCommitmentExportError(
            "Tracked worktree must be clean before commitment creation"
        )
    git_sha = validate_git_sha(
        code_state.get("evidence_git_head_sha"),
        "evidence_git_head_sha",
    )

    stage_5b3_proto_raw, stage_5b3_proto_payload = _read_json(
        stage_5b3_protocol_path, "Stage 5B3 protocol"
    )
    commitment_proto_raw, commitment_proto_payload = _read_json(
        commitment_protocol_path, "Stage 5B4 commitment protocol"
    )

    try:
        validate_stage_5b3_protocol(
            stage_5b3_proto_payload,
            stage_5b3_proto_raw,
            committed_path=DEFAULT_STAGE_5B3_PROTOCOL_PATH,
        )
        validate_protocol_contract(
            commitment_proto_payload,
            commitment_proto_raw,
            committed_path=DEFAULT_PROTOCOL_PATH,
        )
        bundle = validate_stage_5b3_bundle(
            tasks_path=tasks_path,
            summary_path=summary_path,
            manifest_path=manifest_path,
        )
    except CampaignCommitmentError as error:
        raise CampaignCommitmentExportError(str(error)) from error

    expected_target_path = REPOSITORY_ROOT / COMMITMENT_ROOT / f"{bundle.campaign_id}.json"
    resolved_output = _assert_no_symlink_components(output_path, "Output path")
    resolved_expected = expected_target_path.resolve(strict=False)

    if resolved_output != resolved_expected:
        raise CampaignCommitmentExportError(
            "Declaration output path must be exactly "
            f"artifacts/research-commitments/win-either-half/{bundle.campaign_id}.json"
        )

    declaration = build_commitment_declaration(
        bundle=bundle,
        stage_5b3_protocol_raw=stage_5b3_proto_raw,
        commitment_protocol_raw=commitment_proto_raw,
        generator_git_sha=git_sha,
    )

    declaration_bytes = canonical_json_bytes(declaration.to_mapping(), pretty=True)

    _write_file_atomically(
        resolved_output,
        declaration_bytes,
        force=force,
        is_git_tracked_check=True,
    )

    return bundle.campaign_id, declaration_bytes


def check_commitment(
    *,
    tasks_path: Path,
    summary_path: Path,
    manifest_path: Path,
    stage_5b3_protocol_path: Path,
    commitment_protocol_path: Path,
    declaration_path: Path,
    code_state: Mapping[str, Any],
) -> str:
    tracked_clean = code_state.get("tracked_worktree_clean")
    if tracked_clean is not True:
        raise CampaignCommitmentExportError(
            "Tracked worktree must be clean before commitment check"
        )
    current_head_sha = validate_git_sha(
        code_state.get("evidence_git_head_sha"),
        "evidence_git_head_sha",
    )

    stage_5b3_proto_raw, stage_5b3_proto_payload = _read_json(
        stage_5b3_protocol_path, "Stage 5B3 protocol"
    )
    commitment_proto_raw, commitment_proto_payload = _read_json(
        commitment_protocol_path, "Stage 5B4 commitment protocol"
    )
    declaration_raw, declaration_payload = _read_json(
        declaration_path, "Declaration"
    )

    try:
        validate_stage_5b3_protocol(
            stage_5b3_proto_payload,
            stage_5b3_proto_raw,
            committed_path=DEFAULT_STAGE_5B3_PROTOCOL_PATH,
        )
        validate_protocol_contract(
            commitment_proto_payload,
            commitment_proto_raw,
            committed_path=DEFAULT_PROTOCOL_PATH,
        )
        bundle = validate_stage_5b3_bundle(
            tasks_path=tasks_path,
            summary_path=summary_path,
            manifest_path=manifest_path,
        )
        decl_obj = validate_declaration_mapping(
            declaration_payload, expected_path=declaration_path
        )
    except CampaignCommitmentError as error:
        raise CampaignCommitmentExportError(str(error)) from error

    generator_sha = decl_obj.generator_git_sha

    _require_commit(
        REPOSITORY_ROOT,
        generator_sha,
        "declaration generator",
    )
    _require_commit(
        REPOSITORY_ROOT,
        current_head_sha,
        "current HEAD",
    )
    _require_ancestor(
        REPOSITORY_ROOT,
        generator_sha,
        current_head_sha,
        "verify declaration generator ancestry",
    )

    expected_declaration = build_commitment_declaration(
        bundle=bundle,
        stage_5b3_protocol_raw=stage_5b3_proto_raw,
        commitment_protocol_raw=commitment_proto_raw,
        generator_git_sha=generator_sha,
    )
    expected_bytes = canonical_json_bytes(
        expected_declaration.to_mapping(), pretty=True
    )

    if declaration_raw != expected_bytes:
        raise CampaignCommitmentExportError(
            f"Stored declaration at {declaration_path} differs from deterministic rebuild bytes"
        )

    return bundle.campaign_id


def validate_git_diff(
    *,
    repository_root: Path,
    base_sha: str,
    head_sha: str,
    server_observed_at: str,
    github_run_id: str,
    github_run_attempt: str,
    github_event_name: str,
    attestation_output: Path,
) -> tuple[int, str]:
    repo = _assert_no_symlink_components(repository_root, "Repository root")
    v_base = validate_git_sha(base_sha, "base_sha")
    v_head = validate_git_sha(head_sha, "head_sha")

    resolved_attestation = _assert_no_symlink_components(
        attestation_output, "Attestation output"
    )
    resolved_repo = repo.resolve(strict=False)
    if _is_relative_to(resolved_attestation, resolved_repo):
        raise CampaignCommitmentExportError(
            f"Attestation output path {attestation_output} must be outside repository root {repository_root}"
        )

    if github_event_name != "pull_request":
        raise CampaignCommitmentExportError(
            "GitHub event must be pull_request for commitment deadline qualification"
        )

    try:
        run_id_num = int(github_run_id)
        if str(run_id_num) != github_run_id or run_id_num <= 0:
            raise ValueError()
    except ValueError:
        raise CampaignCommitmentExportError(
            "github_run_id must be a positive decimal integer"
        )

    try:
        run_attempt_num = int(github_run_attempt)
        if str(run_attempt_num) != github_run_attempt or run_attempt_num <= 0:
            raise ValueError()
    except ValueError:
        raise CampaignCommitmentExportError(
            "github_run_attempt must be a positive decimal integer"
        )

    observed_dt = parse_utc(server_observed_at, "server_observed_at")

    _require_commit(repo, v_base, "base")
    _require_commit(repo, v_head, "head")
    _require_ancestor(
        repo,
        v_base,
        v_head,
        "verify base/head ancestry",
    )

    diff_result = _run_git_bytes(
        [
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies",
            v_base,
            v_head,
            "--",
            COMMITMENT_ROOT.as_posix(),
        ],
        cwd=repo,
        label="commitment-root name-status diff",
    )
    records = _parse_name_status_z(diff_result)
    declarations_to_validate: list[Path] = []
    seen_paths: set[str] = set()
    seen_campaign_ids: set[str] = set()
    for status, paths in records:
        if status != "A":
            if status.startswith(("R", "C")):
                raise CampaignCommitmentExportError(
                    "Renames/copies forbidden in the "
                    f"commitment root: status={status}, "
                    f"paths={paths}"
                )
            raise CampaignCommitmentExportError(
                f"Forbidden git status {status}: only file additions are permitted in the "
                f"commitment root: status={status}, paths={paths}"
            )
        if len(paths) != 1:
            raise CampaignCommitmentExportError(
                f"Addition record must contain one path: {paths}"
            )
        path_string = paths[0]
        declaration_relative_path = Path(path_string)
        if declaration_relative_path.parent != COMMITMENT_ROOT:
            raise CampaignCommitmentExportError(
                "Commitment file must be a direct child of "
                f"{COMMITMENT_ROOT}: {path_string}"
            )
        campaign_id = declaration_relative_path.stem
        if (
            not CAMPAIGN_ID_PATTERN.fullmatch(campaign_id)
            or declaration_relative_path.name
            != f"{campaign_id}.json"
        ):
            raise CampaignCommitmentExportError(
                f"Commitment filename contract violated: "
                f"{path_string}"
            )
        if path_string in seen_paths:
            raise CampaignCommitmentExportError(
                f"Duplicate path in diff: {path_string}"
            )
        if campaign_id in seen_campaign_ids:
            raise CampaignCommitmentExportError(
                f"Duplicate campaign ID: {campaign_id}"
            )
        seen_paths.add(path_string)
        seen_campaign_ids.add(campaign_id)
        ls_tree_result = _run_git_bytes(
            [
                "ls-tree",
                "-z",
                v_head,
                "--",
                path_string,
            ],
            cwd=repo,
            label=f"inspect head-tree mode for {path_string}",
        )
        file_mode, _ = _parse_single_ls_tree_record(
            ls_tree_result,
            expected_path=path_string,
        )
        if file_mode == "120000":
            raise CampaignCommitmentExportError(
                f"Symlink declarations are forbidden (mode 120000 forbidden): "
                f"{path_string}"
            )
        if file_mode not in {"100644", "100755"}:
            raise CampaignCommitmentExportError(
                f"Invalid declaration file mode {file_mode}: "
                f"{path_string}"
            )
        full_path = repo / declaration_relative_path
        _assert_no_symlink_components(
            full_path,
            "Diff declaration path",
        )
        declarations_to_validate.append(full_path)

    if not declarations_to_validate:
        raise CampaignCommitmentExportError(
            "Workflow triggered on commitment root but zero valid added declarations were found"
        )

    results: list[DeadlineValidationResult] = []
    for d_path in declarations_to_validate:
        rel_posix = d_path.relative_to(repo).as_posix()
        blob_bytes = _run_git_bytes(
            [
                "cat-file",
                "blob",
                f"{v_head}:{rel_posix}",
            ],
            cwd=repo,
            label=f"read exact head blob for {rel_posix}",
        )

        if not d_path.is_file():
            raise CampaignCommitmentExportError(
                f"Declaration {rel_posix} is missing from working tree"
            )
        worktree_bytes = d_path.read_bytes()
        if blob_bytes != worktree_bytes:
            raise CampaignCommitmentExportError(
                f"Working tree bytes for {rel_posix} differ from commit {v_head} blob bytes"
            )

        try:
            d_payload = json.loads(blob_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CampaignCommitmentExportError(
                f"Declaration {rel_posix} must be valid UTF-8 JSON"
            ) from error

        if not isinstance(d_payload, Mapping):
            raise CampaignCommitmentExportError(
                f"Declaration {rel_posix} must be a JSON object"
            )

        expected_formatted_bytes = canonical_json_bytes(d_payload, pretty=True)
        if blob_bytes != expected_formatted_bytes:
            raise CampaignCommitmentExportError(
                f"Declaration {rel_posix} does not match canonical pretty formatting"
            )

        try:
            decl = validate_declaration_mapping(
                d_payload, expected_path=d_path, repository_root=repo
            )
            commitment_sha256 = sha256_bytes(blob_bytes)
            res = validate_deadline(
                decl,
                server_observed_at=observed_dt,
                commitment_sha256=commitment_sha256,
            )
        except CampaignCommitmentError as error:
            raise CampaignCommitmentExportError(
                f"Declaration validation failed for {d_path.name}: {error}"
            ) from error

        if not res.prospective_timing_qualified:
            raise CampaignCommitmentExportError(
                f"Declaration {d_path.name} failed deadline qualification: "
                f"observed={serialize_utc(observed_dt)} > deadline={serialize_utc(decl.commitment_deadline_at)}"
            )
        results.append(res)

    results.sort(key=lambda r: r.campaign_id)

    base_protocol_bytes = _read_bytes(
        DEFAULT_PROTOCOL_PATH,
        "Base-revision Stage 5B4 commitment protocol",
    )
    head_protocol_path = (
        repo
        / "artifacts"
        / "research-protocols"
        / "win-either-half-campaign-commitment-v1.json"
    )
    head_protocol_bytes = _read_bytes(
        head_protocol_path,
        "Head Stage 5B4 commitment protocol",
    )
    if head_protocol_bytes != base_protocol_bytes:
        raise CampaignCommitmentExportError(
            "Head Stage 5B4 protocol bytes differ from "
            "base-revision verifier protocol bytes"
        )

    attestation: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": ATTESTATION_DATASET_NAME,
        "github_run_id": str(run_id_num),
        "github_run_attempt": run_attempt_num,
        "github_event_name": github_event_name,
        "time_source": "GITHUB_HOSTED_RUNNER_UTC",
        "base_sha": v_base,
        "head_sha": v_head,
        "server_observed_at": serialize_utc(observed_dt),
        "declaration_count": len(results),
        "declarations": [r.to_mapping() for r in results],
        "prospective_timing_qualified_on_success": True,
        "prospective_claim_authorized": False,
        "selected_offset_seconds": None,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "market_statuses": {
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        },
        "safety": dict(GENERATED_SAFETY_CONTRACT),
        "upstream_protocol_identity": {
            "relative_name": DEFAULT_PROTOCOL_PATH.name,
            "byte_size": len(base_protocol_bytes),
            "sha256": sha256_bytes(base_protocol_bytes),
        },
        "no_production_approval": (
            "This attestation qualifies the timing of pre-registered prospective "
            "capture campaigns only. It collects no odds, selects no offset, "
            "enables no market, and authorizes no bet."
        ),
    }

    if attestation.get("safety") != GENERATED_SAFETY_CONTRACT:
        raise CampaignCommitmentExportError(
            "Attestation safety contract drifted from exact expectation"
        )
    attestation_clean = dict(attestation)
    attestation_clean.pop("safety")
    assert_no_forbidden_fields(attestation_clean, "Attestation")

    attestation_bytes = canonical_json_bytes(attestation, pretty=True)

    _write_file_atomically(
        attestation_output,
        attestation_bytes,
        force=True,
        is_git_tracked_check=False,
    )

    summary_lines = [
        "### Win Either Half Campaign Commitment Timing Qualification",
        "",
        f"**Server Observed UTC:** `{serialize_utc(observed_dt)}`  ",
        f"**Base SHA:** `{v_base[:8]}` | **Head SHA:** `{v_head[:8]}`  ",
        f"**GitHub Run ID:** `{github_run_id}` (Attempt `{github_run_attempt}`)  ",
        "",
        "| Campaign ID | Status | Deadline UTC | Observed UTC | Timing Qualified | Claim Authorized |",
        "| :--- | :--- | :--- | :--- | :---: | :---: |",
    ]
    for r in results:
        summary_lines.append(
            f"| `{r.campaign_id}` | `TIMING_QUALIFIED` | `{serialize_utc(r.commitment_deadline_at)}` | `{serialize_utc(r.server_observed_at)}` | PASSED | FALSE |"
        )
    summary_lines.append("")
    summary_lines.append(
        "> **Notice:** Timing qualification confirms pre-registration before the "
        "earliest capture window only. Markets remain DISABLED and prospective claim "
        "authorization remains FALSE."
    )
    summary_md = "\n".join(summary_lines)

    return len(results), summary_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Stage 5B4 Win Either Half campaign commitments."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create", type=Path, help="Output path for commitment declaration JSON")
    mode.add_argument("--check", type=Path, help="Declaration path to check against Stage 5B3 bundle")
    mode.add_argument(
        "--validate-git-diff",
        action="store_true",
        help="Validate newly added commitments in GitHub Actions pull_request workflow",
    )

    parser.add_argument("--tasks", type=Path, help="Stage 5B3 tasks file path")
    parser.add_argument("--summary", type=Path, help="Stage 5B3 summary file path")
    parser.add_argument("--manifest", type=Path, help="Stage 5B3 manifest file path")
    parser.add_argument(
        "--stage-5b3-protocol",
        type=Path,
        default=DEFAULT_STAGE_5B3_PROTOCOL_PATH,
    )
    parser.add_argument(
        "--commitment-protocol",
        type=Path,
        default=DEFAULT_PROTOCOL_PATH,
    )
    parser.add_argument("--force", action="store_true", help="Allow replacing untracked declaration")

    # Arguments for --validate-git-diff
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--base-sha")
    parser.add_argument("--head-sha")
    parser.add_argument("--server-observed-at")
    parser.add_argument("--github-run-id")
    parser.add_argument("--github-run-attempt")
    parser.add_argument("--github-event-name")
    parser.add_argument("--attestation-output", type=Path)

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.create is not None or args.check is not None:
            if not (args.tasks and args.summary and args.manifest):
                raise CampaignCommitmentExportError(
                    "--tasks, --summary, and --manifest are required for --create and --check"
                )

            try:
                code_state = get_code_state(REPOSITORY_ROOT)
            except Exception as error:
                raise CampaignCommitmentExportError(
                    "Git repository state could not be determined"
                ) from error

            if args.create is not None:
                c_id, _ = create_commitment(
                    tasks_path=args.tasks,
                    summary_path=args.summary,
                    manifest_path=args.manifest,
                    stage_5b3_protocol_path=args.stage_5b3_protocol,
                    commitment_protocol_path=args.commitment_protocol,
                    output_path=args.create,
                    force=args.force,
                    code_state=code_state,
                )
                print(
                    f"Stage 5B4 commitment declaration created: campaign_id={c_id} path={args.create}"
                )
                return 0

            if args.check is not None:
                if args.force:
                    raise CampaignCommitmentExportError("--force cannot be used with --check")
                c_id = check_commitment(
                    tasks_path=args.tasks,
                    summary_path=args.summary,
                    manifest_path=args.manifest,
                    stage_5b3_protocol_path=args.stage_5b3_protocol,
                    commitment_protocol_path=args.commitment_protocol,
                    declaration_path=args.check,
                    code_state=code_state,
                )
                print(
                    f"Stage 5B4 commitment declaration verified: campaign_id={c_id} path={args.check}"
                )
                return 0

        if args.validate_git_diff:
            req_args = [
                ("base_sha", args.base_sha),
                ("head_sha", args.head_sha),
                ("server_observed_at", args.server_observed_at),
                ("github_run_id", args.github_run_id),
                ("github_run_attempt", args.github_run_attempt),
                ("github_event_name", args.github_event_name),
                ("attestation_output", args.attestation_output),
            ]
            for name, val in req_args:
                if not val:
                    raise CampaignCommitmentExportError(
                        f"--{name.replace('_', '-')} is required for --validate-git-diff"
                    )

            count, summary_md = validate_git_diff(
                repository_root=args.repository_root,
                base_sha=args.base_sha,
                head_sha=args.head_sha,
                server_observed_at=args.server_observed_at,
                github_run_id=args.github_run_id,
                github_run_attempt=args.github_run_attempt,
                github_event_name=args.github_event_name,
                attestation_output=args.attestation_output,
            )
            print(summary_md)
            return 0

        raise CampaignCommitmentExportError("Invalid command invocation mode")

    except (CampaignCommitmentError, CampaignCommitmentExportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
