"""Closed, exact successor table for the Phase A pcUpcoming retention rebuild.

PHASE_A_SUCCESSORS lists every existing file this change edits that a frozen
record pins, each with its exact BEFORE (main) and AFTER (Phase A) identities.
Every consumer that compares live bytes with a frozen record calls one of the
projections below first. A projection maps only a listed path, only from AFTER
to BEFORE, and only after that path's working-tree bytes are authenticated as
exactly AFTER. BEFORE passes unchanged. Anything else (another blob, a missing
path, a linked or nonregular file, an unlisted path) fails closed or is left to
the consumer's own unchanged check. There are no wildcards and no prefixes.

BEFORE bytes are derived offline: AFTER bytes minus the entry's exact inserted
hunks, authenticated against the BEFORE identifiers. No BEFORE object or
fixture is needed, so shallow CI checkouts work. No frozen record, receipt,
ledger or inventory generation is changed. This module grants no provider,
trigger, delivery or model authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import stat
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ".github/workflows/"
REASON = "Phase A pcUpcoming retention (rebuild of PR #465 Phase A)"
UNADMITTED = "phase A workflow successor: unadmitted current-shadow-all-market.yml blob"


@dataclasses.dataclass(frozen=True)
class Successor:
    path: str
    before_blob: str
    before_sha256: str
    after_blob: str
    after_sha256: str
    hunks: tuple[bytes, ...]
    reason: str


# The Phase A workflow delta: one copy-list line and the trailing verify block.
COPY_LINE = b"            '.cache/athena-research/current-shadow-sportybet-pc-upcoming-discovery' \\\n"
VERIFY_BLOCK = (
    b"          # Verify copied raw pages, manifests and capture epochs against the\n"
    b"          # exact source tree and the completed run receipt before artifact upload.\n"
    b"          # Runs last so a verification failure cannot skip the identity-state copy.\n"
    b"          python -m scripts.verify_current_shadow_pc_upcoming_archive\n"
    b"\n"
)
# The F1 one-call hook in scripts/core_01d_historical_source.py.
HISTORICAL_SOURCE_HOOK = (
    b"        from scripts import audit_phase_a_workflow_successor as phase_a\n"
    b"        live_identity = phase_a.project_source_identity(str(path), live, live_identity)\n"
)

PHASE_A_SUCCESSORS: tuple[Successor, ...] = (
    Successor(
        path=".github/workflows/current-shadow-all-market.yml",
        before_blob="a06a3166322ccb92b0bc3c05c87c5b3ca17298e1",
        before_sha256="755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c",
        after_blob="62dd84da0c426b0b03729cca5d9d7b4294fb0472",
        after_sha256="0ac54f9a5d2958e57d589f3e2489a0a7b505f6acc978a568906993960803c1e5",
        hunks=(COPY_LINE, VERIFY_BLOCK),
        reason=REASON,
    ),
    Successor(
        path="scripts/core_01d_historical_source.py",
        before_blob="7548914b31ceb832b55818e66c19b8a9bd606927",
        before_sha256="5c46e7b5011de91c540fbbff9b7c06f15a81c87097ef07838d045123ae948865",
        after_blob="83913347db213e0972948113f1ce8dfb2600fe15",
        after_sha256="de26bbae44894704399d9f520da478749739ca7b055b42bc5305c4f39213fd2b",
        hunks=(HISTORICAL_SOURCE_HOOK,),
        reason=REASON + ": one-call projection hook for the workflow successor",
    ),
)
_BY_PATH = {entry.path: entry for entry in PHASE_A_SUCCESSORS}
if len(_BY_PATH) != len(PHASE_A_SUCCESSORS):
    raise RuntimeError("duplicate Phase A successor path")

# Backward-compatible names for the workflow entry.
WORKFLOW = PHASE_A_SUCCESSORS[0]
PATH = WORKFLOW.path
NAME = PATH[len(WORKFLOW_DIR):]
BEFORE_BLOB = WORKFLOW.before_blob
BEFORE_SHA256 = WORKFLOW.before_sha256
AFTER_BLOB = WORKFLOW.after_blob
AFTER_SHA256 = WORKFLOW.after_sha256


class PhaseAWorkflowSuccessorError(ValueError):
    pass


def _fail(detail: str = "") -> None:
    raise PhaseAWorkflowSuccessorError(UNADMITTED + (": " + detail if detail else ""))


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _identity(raw: bytes) -> tuple[str, str]:
    raw = raw.replace(b"\r\n", b"\n")
    return _git_blob_sha1(raw), hashlib.sha256(raw).hexdigest()


def entry_for(path_or_workflow_name: str) -> Successor | None:
    """Exact lookup by repository path, or by bare name inside .github/workflows."""
    key = str(path_or_workflow_name)
    if "/" not in key:
        key = WORKFLOW_DIR + key
    return _BY_PATH.get(key)


def is_successor_path(path: str) -> bool:
    return str(path) in _BY_PATH


def authenticate_current_bytes(root: Path | None = None, path: str = PATH) -> str:
    """Return "AFTER" or "BEFORE" for a listed path's exact working-tree bytes."""
    entry = entry_for(path)
    if entry is None:
        _fail("path is not in the Phase A successor table: " + str(path))
    root = ROOT if root is None else root
    target = root / entry.path
    parts = Path(entry.path).parts
    nodes = [root.joinpath(*parts[:index]) for index in range(1, len(parts))] + [target]
    for node in nodes:
        try:
            info = node.lstat()
        except OSError:
            _fail(entry.path + " is missing")
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _fail(entry.path + " is linked")
    if not stat.S_ISREG(target.lstat().st_mode):
        _fail(entry.path + " is not a regular file")
    identity = _identity(target.read_bytes())
    if identity == (entry.after_blob, entry.after_sha256):
        return "AFTER"
    if identity == (entry.before_blob, entry.before_sha256):
        return "BEFORE"
    _fail(entry.path + " working-tree bytes are neither the admitted before nor after identity")
    raise AssertionError("unreachable")


def before_bytes(path: str = PATH, root: Path | None = None) -> bytes:
    """Main's exact bytes for a listed path; authenticates the working tree first."""
    entry = entry_for(path)
    if entry is None:
        _fail("path is not in the Phase A successor table: " + str(path))
    root = ROOT if root is None else root
    state = authenticate_current_bytes(root, entry.path)
    raw = (root / entry.path).read_bytes().replace(b"\r\n", b"\n")
    if state == "AFTER":
        for hunk in entry.hunks:
            if raw.count(hunk) != 1:
                _fail(entry.path + " after bytes do not carry exactly one copy of each hunk")
            raw = raw.replace(hunk, b"", 1)
    if _identity(raw) != (entry.before_blob, entry.before_sha256):
        _fail(entry.path + " derived before bytes are not the admitted before identity")
    return raw


def is_admitted_after(path: str, raw: bytes, *, root: Path | None = None) -> bool:
    """Non-raising for unlisted paths or other bytes: True only for exact AFTER bytes."""
    entry = entry_for(path)
    if entry is None or _identity(raw) != (entry.after_blob, entry.after_sha256):
        return False
    return authenticate_current_bytes(root, entry.path) == "AFTER"


def project_tree_blob(name: str, blob: str, *, root: Path | None = None) -> str:
    """Project one tree entry (bare workflow name or full path); others unchanged."""
    entry = entry_for(name)
    if entry is None:
        return blob
    state = authenticate_current_bytes(root, entry.path)
    if blob == entry.after_blob and state == "AFTER":
        return entry.before_blob
    if blob == entry.before_blob and state == "BEFORE":
        return blob
    _fail(entry.path + " tree entry " + blob + " does not match the authenticated working tree")
    raise AssertionError("unreachable")


def project_workflow_tree(tree: Mapping[str, str], *, root: Path | None = None) -> dict[str, str]:
    """Copy of a {path: blob} workflow mapping with only listed workflow paths projected."""
    projected = dict(tree)
    for entry in PHASE_A_SUCCESSORS:
        if not entry.path.startswith(WORKFLOW_DIR):
            continue
        if entry.path not in tree:
            _fail(entry.path + " is absent from the tree")
        projected[entry.path] = project_tree_blob(entry.path, tree[entry.path], root=root)
    return projected


def project_ls_tree(raw: bytes, *, root: Path | None = None) -> bytes:
    """Project listed paths in a ``git ls-tree -r`` listing; partial listings pass through.

    AFTER rows project to BEFORE only when the working tree is exactly AFTER;
    BEFORE rows pass unchanged; any other blob fails closed. When a full listing
    lacks a listed path, or carries BEFORE where the frozen record does not, the
    caller's own frozen hash comparison still fails. A duplicated path fails here.
    """
    lines = []
    seen: dict[str, int] = {}
    for line in raw.splitlines(keepends=True):
        meta, sep, path = line.partition(b"\t")
        name = path.strip().decode() if sep else ""
        if sep and name in _BY_PATH:
            seen[name] = seen.get(name, 0) + 1
            head, _, blob = meta.rpartition(b" ")
            blob_text = blob.decode("ascii")
            # A frozen historical listing already carries BEFORE: it passes
            # unchanged, and the caller's own frozen hash still authenticates it.
            if blob_text == _BY_PATH[name].before_blob:
                projected = blob_text
            else:
                projected = project_tree_blob(name, blob_text, root=root)
            line = head + b" " + projected.encode("ascii") + sep + path
        lines.append(line)
    if any(count > 1 for count in seen.values()):
        _fail("a listed path is duplicated in the tree listing")
    return b"".join(lines)


def is_admitted_successor(name: str, source: bytes) -> bool:
    """True only for a listed path at exact AFTER bytes, authenticated on disk."""
    entry = entry_for(name)
    if entry is None:
        return False
    identity = _identity(source)
    if identity == (entry.before_blob, entry.before_sha256):
        return False
    if identity != (entry.after_blob, entry.after_sha256) or authenticate_current_bytes(None, entry.path) != "AFTER":
        _fail(entry.path + " source bytes are not the admitted after identity")
    return True


def filter_changed_paths(changed: Iterable[str]) -> list[str]:
    """Drop listed workflow paths from a changed-path list only at exact AFTER bytes."""
    changed = list(changed)
    for entry in PHASE_A_SUCCESSORS:
        if entry.path.startswith(WORKFLOW_DIR) and entry.path in changed:
            if authenticate_current_bytes(None, entry.path) != "AFTER":
                _fail(entry.path + " changed but is not the admitted after identity")
            changed = [path for path in changed if path != entry.path]
    return changed


def project_source_identity(path: str, live: bytes, identity):
    """Project a runtime DevelopmentSourceIdentity for a listed path at exact AFTER bytes."""
    if not is_admitted_after(path, live):
        return identity
    entry = entry_for(path)
    updates = {"git_blob_sha1": entry.before_blob, "git_blob_payload_sha256": entry.before_sha256}
    if getattr(identity, "filtered_worktree_git_blob_sha1", None) == entry.after_blob:
        updates["filtered_worktree_git_blob_sha1"] = entry.before_blob
    if getattr(identity, "raw_worktree_sha256", None) == entry.after_sha256:
        updates["raw_worktree_sha256"] = entry.before_sha256
    return dataclasses.replace(identity, **updates)


def p4_workflow_forwards() -> dict[str, tuple[dict[str, str], dict[str, str]]]:
    """Admitted workflow forwards in the P4 ledger's {path: (before, after)} shape."""
    return {
        entry.path: (
            {"git_blob_sha1": entry.before_blob, "source_sha256": entry.before_sha256},
            {"git_blob_sha1": entry.after_blob, "source_sha256": entry.after_sha256},
        )
        for entry in PHASE_A_SUCCESSORS
        if entry.path.startswith(WORKFLOW_DIR)
    }
