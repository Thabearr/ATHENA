"""Exact additive successor for one workflow: Phase A pcUpcoming retention.

Admits exactly one change: ``.github/workflows/current-shadow-all-market.yml``
moving from main's reviewed bytes (BEFORE) to the Phase A bytes (AFTER). Every
consumer that compares the live workflow tree with a frozen record calls one of
the projections below first. The projection maps only this path, only from
AFTER to BEFORE, and only after the working-tree file itself is authenticated.
Any other blob, a missing path, or a linked or nonregular file fails closed.

No frozen record, receipt, ledger or inventory generation is changed. Only the
BEFORE identifiers are needed, never the BEFORE object, so shallow CI checkouts
work. This module grants no provider, trigger, delivery or model authority.
"""
from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
NAME = "current-shadow-all-market.yml"
PATH = ".github/workflows/" + NAME
REASON = "Phase A pcUpcoming retention (rebuild of PR #465 Phase A)"
BEFORE_BLOB = "a06a3166322ccb92b0bc3c05c87c5b3ca17298e1"
BEFORE_SHA256 = "755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c"
AFTER_BLOB = "62dd84da0c426b0b03729cca5d9d7b4294fb0472"
AFTER_SHA256 = "0ac54f9a5d2958e57d589f3e2489a0a7b505f6acc978a568906993960803c1e5"
UNADMITTED = "phase A workflow successor: unadmitted current-shadow-all-market.yml blob"


class PhaseAWorkflowSuccessorError(ValueError):
    pass


def _fail(detail: str = "") -> None:
    raise PhaseAWorkflowSuccessorError(UNADMITTED + (": " + detail if detail else ""))


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def authenticate_current_bytes(root: Path | None = None) -> str:
    """Return "AFTER" or "BEFORE" for the exact working-tree workflow bytes."""
    root = ROOT if root is None else root
    target = root / PATH
    for node in (root / ".github", root / ".github/workflows", target):
        try:
            info = node.lstat()
        except OSError:
            _fail("workflow path is missing")
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _fail("workflow path is linked")
    if not stat.S_ISREG(target.lstat().st_mode):
        _fail("workflow path is not a regular file")
    raw = target.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    blob = _git_blob_sha1(raw)
    if (blob, digest) == (AFTER_BLOB, AFTER_SHA256):
        return "AFTER"
    if (blob, digest) == (BEFORE_BLOB, BEFORE_SHA256):
        return "BEFORE"
    _fail("working-tree bytes are neither the admitted before nor after identity")
    raise AssertionError("unreachable")


def project_tree_blob(name: str, blob: str, *, root: Path | None = None) -> str:
    """Project one workflow-directory tree entry; every other entry is unchanged."""
    if name != NAME and name != PATH:
        return blob
    state = authenticate_current_bytes(root)
    if blob == AFTER_BLOB and state == "AFTER":
        return BEFORE_BLOB
    if blob == BEFORE_BLOB and state == "BEFORE":
        return blob
    _fail("tree entry " + blob + " does not match the authenticated working tree")
    raise AssertionError("unreachable")


def project_workflow_tree(tree: Mapping[str, str], *, root: Path | None = None) -> dict[str, str]:
    """Return a copy of a {path: blob} mapping with only PATH projected."""
    if PATH not in tree:
        _fail("workflow path is absent from the tree")
    projected = dict(tree)
    projected[PATH] = project_tree_blob(PATH, tree[PATH], root=root)
    return projected


def project_ls_tree(raw: bytes, *, root: Path | None = None) -> bytes:
    """Project a recursive ``git ls-tree -r`` listing; requires PATH to be present."""
    lines = []
    seen = 0
    for line in raw.splitlines(keepends=True):
        meta, sep, path = line.partition(b"\t")
        if sep and path.strip().decode() == PATH:
            seen += 1
            head, _, blob = meta.rpartition(b" ")
            projected = project_tree_blob(PATH, blob.decode("ascii"), root=root)
            line = head + b" " + projected.encode("ascii") + sep + path
        lines.append(line)
    if seen != 1:
        _fail("workflow path is absent or duplicated in the tree listing")
    return b"".join(lines)


def is_admitted_successor(name: str, source: bytes) -> bool:
    """True only for this workflow at its exact AFTER bytes (authenticated on disk)."""
    if name != NAME and name != PATH:
        return False
    raw = source.replace(b"\r\n", b"\n")
    identity = (_git_blob_sha1(raw), hashlib.sha256(raw).hexdigest())
    if identity == (BEFORE_BLOB, BEFORE_SHA256):
        return False
    if identity != (AFTER_BLOB, AFTER_SHA256) or authenticate_current_bytes() != "AFTER":
        _fail("workflow source bytes are not the admitted after identity")
    return True


def project_observed_identities(observed: Mapping[str, Mapping[str, str]]) -> dict:
    """Project a P4 {path: {git_blob_sha1, source_sha256}} mapping for PATH only."""
    if PATH not in observed:
        _fail("workflow path is absent from the observed identities")
    projected = dict(observed)
    current = dict(observed[PATH])
    state = authenticate_current_bytes()
    if current == {"git_blob_sha1": AFTER_BLOB, "source_sha256": AFTER_SHA256} and state == "AFTER":
        projected[PATH] = {"git_blob_sha1": BEFORE_BLOB, "source_sha256": BEFORE_SHA256}
    elif current != {"git_blob_sha1": BEFORE_BLOB, "source_sha256": BEFORE_SHA256} or state != "BEFORE":
        _fail("observed identity does not match the authenticated working tree")
    return projected


def filter_changed_paths(changed: Iterable[str]) -> list[str]:
    """Drop PATH from a changed-path list only when it is the admitted AFTER bytes."""
    changed = list(changed)
    if PATH not in changed:
        return changed
    if authenticate_current_bytes() != "AFTER":
        _fail("changed workflow is not the admitted after identity")
    return [path for path in changed if path != PATH]
