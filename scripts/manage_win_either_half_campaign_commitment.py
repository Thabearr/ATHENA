"""Create, check, or validate Stage 5B4 Win Either Half campaign commitments."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
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
    if os.name == "nt":
        try:
            import ctypes

            FILE_WRITE_DATA = 2
            FILE_READ_DATA = 1
            FILE_SHARE_READ = 1
            FILE_SHARE_WRITE = 2
            FILE_SHARE_DELETE = 4
            OPEN_EXISTING = 3
            FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
            handle = ctypes.windll.kernel32.CreateFileW(
                str(path),
                FILE_WRITE_DATA | FILE_READ_DATA,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )
            if handle != -1 and handle != 0xFFFFFFFF:
                try:
                    ctypes.windll.kernel32.FlushFileBuffers(handle)
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass
    else:
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            fd = os.open(str(path), flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception:
            pass


def _fsync_file(path: Path) -> None:
    mode = "rb+" if os.name == "nt" else "rb"
    with path.open(mode) as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _is_git_tracked(path: Path, repo_root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_repo = repo_root.resolve()
    try:
        target_arg = resolved_path.relative_to(resolved_repo).as_posix()
        cwd_dir = resolved_repo
    except ValueError:
        target_arg = str(resolved_path)
        cwd_dir = resolved_path.parent

    try:
        res = subprocess.run(
            ["git", "-C", str(cwd_dir), "ls-files", "--error-unmatch", "--", target_arg],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
        )
        if res.returncode == 0:
            return True
        if res.returncode == 1 and (
            "did not match any files" in (res.stderr or "")
            or "did not match any files" in (res.stdout or "")
        ):
            return False
        err_msg = (res.stderr or res.stdout or "").strip()[:240]
        raise CampaignCommitmentExportError(
            f"Unable to determine Git tracked status for {target_arg}: {err_msg}"
        )
    except OSError as error:
        raise CampaignCommitmentExportError(
            f"Git tracked check failed for {target_arg}: {error}"
        ) from error


def _write_file_atomically(
    destination: Path,
    content: bytes,
    *,
    force: bool = False,
    is_git_tracked_check: bool = False,
) -> None:
    resolved_dest = _assert_no_symlink_components(destination, "Output destination")
    parent_dir = _assert_no_symlink_components(resolved_dest.parent, "Output parent directory")

    if resolved_dest.exists() and not force:
        raise CampaignCommitmentExportError(
            f"Output file already exists: {resolved_dest}; use --force to overwrite untracked file"
        )

    if resolved_dest.exists() and is_git_tracked_check:
        if _is_git_tracked(resolved_dest, REPOSITORY_ROOT):
            raise CampaignCommitmentExportError(
                f"Refusing to overwrite Git-tracked commitment file: {resolved_dest}"
            )

    parent_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".stage5b4-tmp-", dir=parent_dir))
    staged_path = temp_dir / resolved_dest.name
    backup_path = parent_dir / f".stage5b4-bak-{resolved_dest.name}-{os.getpid()}"
    destination_backed_up = False
    dest_existed = resolved_dest.exists()

    try:
        with staged_path.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if dest_existed:
            os.replace(resolved_dest, backup_path)
            destination_backed_up = True

        os.replace(staged_path, resolved_dest)
        _fsync_file(resolved_dest)
        _fsync_dir(parent_dir)

        if destination_backed_up and backup_path.exists():
            backup_path.unlink()
            destination_backed_up = False

    except Exception as orig_error:
        cleanup_errors: list[str] = []
        if destination_backed_up and backup_path.exists():
            try:
                os.replace(backup_path, resolved_dest)
                _fsync_file(resolved_dest)
                _fsync_dir(parent_dir)
            except Exception as rollback_err:
                cleanup_errors.append(f"failed to restore backup: {rollback_err}")
        elif not dest_existed and resolved_dest.exists():
            try:
                resolved_dest.unlink()
                _fsync_dir(parent_dir)
            except Exception as unlink_err:
                cleanup_errors.append(f"failed to unlink created dest: {unlink_err}")

        if staged_path.exists():
            try:
                staged_path.unlink()
            except Exception as staged_err:
                cleanup_errors.append(f"failed to unlink staged: {staged_err}")

        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as rmtree_err:
                cleanup_errors.append(f"failed to remove temp_dir: {rmtree_err}")

        if cleanup_errors:
            raise CampaignCommitmentExportError(
                f"Atomic file write failed for {resolved_dest} and rollback was incomplete: {orig_error}; cleanup errors: {'; '.join(cleanup_errors)}"
            ) from orig_error
        raise CampaignCommitmentExportError(
            f"Atomic file write failed for {resolved_dest}: {orig_error}"
        ) from orig_error
    finally:
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except OSError:
                pass
        if backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass


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

    # If running in a repository, verify generator commit exists and is an ancestor of current head
    try:
        check_commit = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "cat-file", "-e", generator_sha],
            capture_output=True,
            text=True,
            check=False,
        )
        if check_commit.returncode == 0:
            ancestor_res = subprocess.run(
                [
                    "git",
                    "-C",
                    str(REPOSITORY_ROOT),
                    "merge-base",
                    "--is-ancestor",
                    generator_sha,
                    current_head_sha,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if ancestor_res.returncode != 0:
                raise CampaignCommitmentExportError(
                    f"Declaration generator_git_sha {generator_sha} is not an ancestor of current head {current_head_sha}"
                )
    except OSError:
        pass

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


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    label: str,
) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", str(cwd)] + args,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            err_msg = res.stderr.strip() or res.stdout.strip()
            raise CampaignCommitmentExportError(
                f"Git command failed ({label}): {err_msg}"
            )
        return res.stdout
    except OSError as error:
        raise CampaignCommitmentExportError(
            f"Git process execution failed ({label}): {error}"
        ) from error


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

    # Verify commits exist and base is ancestor of head
    _run_git(["cat-file", "-e", v_base], cwd=repo, label="check base commit")
    _run_git(["cat-file", "-e", v_head], cwd=repo, label="check head commit")
    ancestor_res = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", v_base, v_head],
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestor_res.returncode != 0:
        raise CampaignCommitmentExportError(
            f"base_sha {v_base} is not an ancestor of head_sha {v_head}"
        )

    # Check git diff under commitment root
    diff_raw = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies",
            v_base,
            v_head,
            "--",
            str(COMMITMENT_ROOT),
        ],
        capture_output=True,
        check=False,
    )
    if diff_raw.returncode != 0:
        raise CampaignCommitmentExportError("Git diff command failed")

    tokens = [t.decode("utf-8") for t in diff_raw.stdout.split(b"\x00") if t]

    declarations_to_validate: list[Path] = []
    seen_paths: set[str] = set()
    seen_campaign_ids: set[str] = set()

    idx = 0
    while idx < len(tokens):
        status = tokens[idx]
        idx += 1
        if status.startswith("R") or status.startswith("C"):
            old_path = tokens[idx]
            new_path = tokens[idx + 1]
            idx += 2
            raise CampaignCommitmentExportError(
                f"Renames/copies forbidden in commitment root: {old_path} -> {new_path}"
            )
        path_str = tokens[idx]
        idx += 1

        if status != "A":
            raise CampaignCommitmentExportError(
                f"Forbidden git status {status} for path {path_str}; only additions (A) are permitted"
            )

        p = Path(path_str)
        if p.parent != COMMITMENT_ROOT:
            raise CampaignCommitmentExportError(
                f"Commitment file must be direct child of {COMMITMENT_ROOT}, got {path_str}"
            )

        match = CAMPAIGN_ID_PATTERN.match(p.stem)
        if not match or p.name != f"{p.stem}.json":
            raise CampaignCommitmentExportError(
                f"Commitment filename contract violated: {path_str}"
            )

        if path_str in seen_paths:
            raise CampaignCommitmentExportError(f"Duplicate path in diff: {path_str}")
        seen_paths.add(path_str)

        if p.stem in seen_campaign_ids:
            raise CampaignCommitmentExportError(
                f"Duplicate campaign_id in diff: {p.stem}"
            )
        seen_campaign_ids.add(p.stem)

        # Check git ls-tree mode
        ls_out = _run_git(
            ["ls-tree", v_head, path_str], cwd=repo, label="check ls-tree mode"
        )
        if not ls_out:
            raise CampaignCommitmentExportError(
                f"Path {path_str} not found in head tree"
            )
        file_mode = ls_out.split()[0]
        if file_mode == "120000":
            raise CampaignCommitmentExportError(
                f"Path {path_str} is a symlink in head tree (mode 120000 forbidden)"
            )
        if file_mode not in {"100644", "100755"}:
            raise CampaignCommitmentExportError(
                f"Path {path_str} has invalid file mode {file_mode}"
            )

        full_path = repo / p
        _assert_no_symlink_components(full_path, "Diff declaration path")
        declarations_to_validate.append(full_path)

    if not declarations_to_validate:
        raise CampaignCommitmentExportError(
            "Workflow triggered on commitment root but zero valid added declarations were found"
        )

    results: list[DeadlineValidationResult] = []
    for d_path in declarations_to_validate:
        rel_posix = d_path.relative_to(repo).as_posix()
        blob_cmd = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-p", f"{v_head}:{rel_posix}"],
            capture_output=True,
            check=False,
        )
        if blob_cmd.returncode != 0:
            raise CampaignCommitmentExportError(
                f"Failed to read blob for {rel_posix} at commit {v_head}"
            )
        blob_bytes = blob_cmd.stdout

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
                d_payload, expected_path=d_path
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

    proto_path = repo / "artifacts" / "research-protocols" / "win-either-half-campaign-commitment-v1.json"
    proto_bytes = _read_bytes(proto_path, "Stage 5B4 commitment protocol")

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
            "sha256": sha256_bytes(proto_bytes),
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
