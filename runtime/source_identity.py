"""Explicit byte identities for development checkouts and raw artifacts.

Development source identities are resolved only from an explicitly supplied,
local Git repository.  Raw-file and canonical-payload identities never apply
Git filters or newline normalization.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any


_GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


class SourceIdentityError(ValueError):
    """A local source or byte identity could not be proven exactly."""


@dataclass(frozen=True)
class DevelopmentSourceIdentity:
    """Exact source identity from one explicit DevelopmentCheckout."""

    repository_relative_path: str
    git_blob_sha1: str
    git_blob_payload_sha256: str
    filtered_worktree_git_blob_sha1: str | None
    raw_worktree_sha256: str | None


def validate_repository_relative_path(value: Any) -> str:
    """Validate an exact portable Git path using POSIX separators."""

    if type(value) is not str or not value:
        raise SourceIdentityError("repository-relative path must be exact non-empty text")
    if "\x00" in value or "\\" in value or ":" in value:
        raise SourceIdentityError("repository-relative path uses a forbidden separator or colon")
    if any(ord(character) < 0x20 for character in value):
        raise SourceIdentityError("repository-relative path contains a control character")
    if value.startswith("/") or value.startswith("//") or _DRIVE_PREFIX_RE.match(value):
        raise SourceIdentityError("absolute or drive-qualified repository path is forbidden")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SourceIdentityError("repository-relative path is not normalized or traverses")
    if PurePosixPath(value).as_posix() != value:
        raise SourceIdentityError("repository-relative path is not normalized POSIX text")
    return value


def read_raw_file_bytes(path: str | os.PathLike[str]) -> bytes:
    """Read the exact materialized bytes of a file, with no Git or text filters."""

    try:
        return Path(path).read_bytes()
    except (OSError, TypeError, ValueError) as exc:
        raise SourceIdentityError("raw file bytes could not be read") from exc


def raw_file_sha256(path: str | os.PathLike[str]) -> str:
    """Return SHA-256 over the exact bytes currently present at ``path``."""

    return hashlib.sha256(read_raw_file_bytes(path)).hexdigest()


def canonical_payload_sha256(payload: bytes) -> str:
    """Return SHA-256 over already-canonical payload bytes, without repair."""

    if type(payload) is not bytes:
        raise SourceIdentityError("canonical payload must already be exact bytes")
    return hashlib.sha256(payload).hexdigest()


def _run_git(repository_root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourceIdentityError("local Git source identity command failed") from exc
    if completed.returncode != 0:
        raise SourceIdentityError("local Git source identity command failed")
    return completed.stdout


def _ascii_git_output(repository_root: Path, *arguments: str) -> str:
    try:
        return _run_git(repository_root, *arguments).decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise SourceIdentityError("local Git returned malformed identity text") from exc


def _ensure_repository_root(repository_root: str | os.PathLike[str]) -> Path:
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise SourceIdentityError("repository_root must resolve to an existing directory") from exc
    if not root.is_dir():
        raise SourceIdentityError("repository_root must be a directory")
    # --show-cdup is empty only when the supplied root is the Git top level;
    # unlike --show-toplevel it does not need to decode a Unicode path emitted
    # by Git on Windows.
    if _run_git(root, "rev-parse", "--show-cdup").strip():
        raise SourceIdentityError("repository_root must be the exact Git top-level directory")
    head = _ascii_git_output(root, "rev-parse", "--verify", "HEAD^{commit}")
    if not _GIT_SHA1_RE.fullmatch(head):
        raise SourceIdentityError("repository has no exact HEAD commit")
    return root


def _tracked_worktree_path(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise SourceIdentityError("tracked source path must not contain a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise SourceIdentityError("tracked source path is missing or escapes repository_root") from exc
    if not resolved.is_file():
        raise SourceIdentityError("tracked source path must be a regular file")
    return resolved


def read_tracked_head_blob(
    repository_root: str | os.PathLike[str],
    relative_path: str,
    *,
    verify_worktree_filtered_identity: bool = True,
) -> tuple[bytes, DevelopmentSourceIdentity]:
    """Read the exact HEAD blob for a tracked path and optionally bind checkout.

    With worktree verification enabled, Git's configured path filters are used
    only to prove that the materialized file is the same tracked source.  The
    returned payload is always the exact unfiltered ``HEAD:path`` blob.  No
    newline normalization, fetch, fallback, or implicit repository discovery
    occurs.
    """

    relative = validate_repository_relative_path(relative_path)
    if type(verify_worktree_filtered_identity) is not bool:
        raise SourceIdentityError("verify_worktree_filtered_identity must be exact bool")
    root = _ensure_repository_root(repository_root)
    try:
        blob_sha1 = _ascii_git_output(root, "rev-parse", "--verify", f"HEAD:{relative}")
    except SourceIdentityError as exc:
        raise SourceIdentityError("path is not present as a tracked HEAD object") from exc
    if not _GIT_SHA1_RE.fullmatch(blob_sha1):
        raise SourceIdentityError("tracked HEAD object is not a Git blob identity")
    object_type = _ascii_git_output(root, "cat-file", "-t", blob_sha1)
    if object_type != "blob":
        raise SourceIdentityError("tracked HEAD object is not a blob")
    payload = _run_git(root, "show", f"HEAD:{relative}")
    git_header = f"blob {len(payload)}\0".encode("ascii")
    if hashlib.sha1(git_header + payload).hexdigest() != blob_sha1:
        raise SourceIdentityError("HEAD blob payload does not match its Git blob SHA-1")

    filtered_sha1: str | None = None
    raw_sha256: str | None = None
    if verify_worktree_filtered_identity:
        worktree_path = _tracked_worktree_path(root, relative)
        raw_payload = read_raw_file_bytes(worktree_path)
        raw_sha256 = hashlib.sha256(raw_payload).hexdigest()
        filtered_sha1 = _ascii_git_output(
            root,
            "hash-object",
            f"--path={relative}",
            "--filters",
            "--",
            str(worktree_path),
        )
        if not _GIT_SHA1_RE.fullmatch(filtered_sha1) or filtered_sha1 != blob_sha1:
            raise SourceIdentityError(
                "filtered worktree bytes differ from the exact HEAD Git blob"
            )

    identity = DevelopmentSourceIdentity(
        repository_relative_path=relative,
        git_blob_sha1=blob_sha1,
        git_blob_payload_sha256=hashlib.sha256(payload).hexdigest(),
        filtered_worktree_git_blob_sha1=filtered_sha1,
        raw_worktree_sha256=raw_sha256,
    )
    return payload, identity
