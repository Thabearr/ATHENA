"""Exact successor projections over the standing successor registry.

The entries live in immutable batch files (``scripts/source_successor_batch_*.py``,
loaded and validated by ``scripts.source_successor_registry``). This module is
the single adapter every consumer hook calls; a later mission registers a new
batch and adds no hook. Public names, signatures and error messages are the ones
PR #470 shipped.

Every consumer that compares live bytes with a frozen record calls one of the
projections below first. A projection maps only a registered path, only to an
identity in that path's chain, and only after the path's working-tree bytes are
authenticated as a member of the chain. Anything else (another blob, a missing
path, a linked or nonregular file) fails closed; an unregistered path is left to
the consumer's own unchanged check. There are no wildcards and no prefixes.

Entries for one path form a chain (root identity -> step 1 -> ... -> head). The
default projection target is the chain root (the frozen original); the ``*_to``
and ``bytes_at`` functions take the identity a consumer's own frozen record pins.
BEFORE bytes are derived offline by reverse-applying each step's exact inserted
hunks from the head, verifying the identity after every step, so shallow CI
checkouts need no historical object or fixture. No frozen record, receipt,
ledger or inventory generation is changed. This module grants no provider,
trigger, delivery or model authority.
"""
from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import hashlib
import stat
from pathlib import Path
from typing import Iterable, Mapping

from scripts import source_successor_registry as registry
from scripts.source_successor_registry import Successor

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ".github/workflows/"
REASON = "Phase A pcUpcoming retention (rebuild of PR #465 Phase A)"
UNADMITTED = "phase A workflow successor: unadmitted current-shadow-all-market.yml blob"

# The PH-A batch (batch 0001), derived from the registry with identical content.
PHASE_A_SUCCESSORS: tuple[Successor, ...] = registry.current().entries_of("PH-A")

# Backward-compatible names for the Phase A entries and their hunks.
WORKFLOW = PHASE_A_SUCCESSORS[0]
PATH = WORKFLOW.path
NAME = PATH[len(WORKFLOW_DIR):]
BEFORE_BLOB = WORKFLOW.before_blob
BEFORE_SHA256 = WORKFLOW.before_sha256
AFTER_BLOB = WORKFLOW.after_blob
AFTER_SHA256 = WORKFLOW.after_sha256
COPY_LINE, VERIFY_BLOCK = WORKFLOW.hunks
HISTORICAL_SOURCE_HOOK = PHASE_A_SUCCESSORS[1].hunks[0]
RETAINED_STATUS_V3_HOOK = PHASE_A_SUCCESSORS[2].hunks[0]


class PhaseAWorkflowSuccessorError(ValueError):
    pass


def _fail(detail: str = "") -> None:
    raise PhaseAWorkflowSuccessorError(UNADMITTED + (": " + detail if detail else ""))


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _identity(raw: bytes) -> tuple[str, str]:
    raw = raw.replace(b"\r\n", b"\n")
    return _git_blob_sha1(raw), hashlib.sha256(raw).hexdigest()


def _chain(path_or_workflow_name: str) -> registry.Chain | None:
    key = str(path_or_workflow_name)
    if "/" not in key:
        key = WORKFLOW_DIR + key
    return registry.current().chains.get(key)


def _index(chain: registry.Chain, blob: str) -> int | None:
    for position, (member, _) in enumerate(chain.identities):
        if member == blob:
            return position
    return None


def entry_for(path_or_workflow_name: str) -> Successor | None:
    """Exact lookup by repository path, or by bare name inside .github/workflows.

    A one-step chain returns its registered entry. A longer chain returns one
    collapsed view: the chain root as before, the head as after.
    """
    chain = _chain(path_or_workflow_name)
    if chain is None:
        return None
    if len(chain.steps) == 1:
        return chain.steps[0]
    first, last = chain.steps[0], chain.steps[-1]
    return Successor(
        path=chain.path, before_blob=first.before_blob, before_sha256=first.before_sha256,
        after_blob=last.after_blob, after_sha256=last.after_sha256,
        hunks=tuple(hunk for step in chain.steps for hunk in step.hunks),
        reason="; ".join(step.reason for step in chain.steps), step=len(chain.steps))


def is_successor_path(path: str) -> bool:
    return str(path) in registry.current().chains


def _read_working(chain: registry.Chain, root: Path | None) -> tuple[int, bytes]:
    """(chain position, LF bytes) of the working file; raises unless it is a member."""
    root = ROOT if root is None else root
    target = root / chain.path
    parts = Path(chain.path).parts
    nodes = [root.joinpath(*parts[:index]) for index in range(1, len(parts))] + [target]
    for node in nodes:
        try:
            info = node.lstat()
        except OSError:
            _fail(chain.path + " is missing")
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _fail(chain.path + " is linked")
    if not stat.S_ISREG(target.lstat().st_mode):
        _fail(chain.path + " is not a regular file")
    raw = target.read_bytes().replace(b"\r\n", b"\n")
    identity = _identity(raw)
    for position, member in enumerate(chain.identities):
        if member == identity:
            return position, raw
    _fail(chain.path + " working-tree bytes are neither the admitted before nor after identity")
    raise AssertionError("unreachable")


def authenticate_current_bytes(root: Path | None = None, path: str = PATH) -> str:
    """Return "AFTER" (chain head), "BEFORE" (chain root) or "INTERMEDIATE" for a listed path."""
    chain = _chain(path)
    if chain is None:
        _fail("path is not in the Phase A successor table: " + str(path))
    position, _ = _read_working(chain, root)
    if position == len(chain.steps):
        return "AFTER"
    return "BEFORE" if position == 0 else "INTERMEDIATE"


def bytes_at(path: str, target: str | None = None, root: Path | None = None) -> bytes:
    """Exact bytes of chain member ``target`` (a blob id; default the chain root).

    Authenticates the working tree first, then reverse-applies each step's exact
    hunks from the working member down to ``target``, verifying the admitted
    identity after every step.
    """
    chain = _chain(path)
    if chain is None:
        _fail("path is not in the Phase A successor table: " + str(path))
    position, raw = _read_working(chain, root)
    ids = chain.identities
    wanted = 0 if target is None else _index(chain, target)
    if wanted is None:
        _fail(chain.path + " target " + str(target) + " is not a member of the successor chain")
    if wanted > position:
        _fail(chain.path + " target is later than the authenticated working tree")
    for level in range(position, wanted, -1):
        for hunk in chain.steps[level - 1].hunks:
            if raw.count(hunk) != 1:
                _fail(chain.path + " after bytes do not carry exactly one copy of each hunk")
            raw = raw.replace(hunk, b"", 1)
        if _identity(raw) != ids[level - 1]:
            _fail(chain.path + " derived before bytes are not the admitted before identity")
    return raw


def before_bytes(path: str = PATH, root: Path | None = None) -> bytes:
    """Main's exact bytes (the chain root) for a listed path; authenticates first."""
    return bytes_at(path, None, root)


def is_admitted_after(path: str, raw: bytes, *, root: Path | None = None) -> bool:
    """Non-raising for unlisted paths or other bytes: True only for exact head bytes."""
    chain = _chain(path)
    if chain is None or _identity(raw) != chain.identities[-1]:
        return False
    return authenticate_current_bytes(root, chain.path) == "AFTER"


def project_tree_blob_to(name: str, blob: str, pinned: str | None, *, root: Path | None = None) -> str:
    """Project one tree entry to the chain member ``pinned`` (default the root)."""
    chain = _chain(name)
    if chain is None:
        return blob
    position, _ = _read_working(chain, root)
    ids = chain.identities
    if blob != ids[position][0]:
        _fail(chain.path + " tree entry " + blob + " does not match the authenticated working tree")
    wanted = 0 if pinned is None else _index(chain, pinned)
    if wanted is None:
        _fail(chain.path + " pinned identity " + str(pinned) + " is not a member of the successor chain")
    if wanted > position:
        _fail(chain.path + " pinned identity is later than the authenticated working tree")
    return ids[wanted][0]


def project_tree_blob(name: str, blob: str, *, root: Path | None = None) -> str:
    """Project one tree entry (bare workflow name or full path); others unchanged."""
    return project_tree_blob_to(name, blob, None, root=root)


def project_workflow_tree(tree: Mapping[str, str], *, root: Path | None = None) -> dict[str, str]:
    """Copy of a {path: blob} workflow mapping with only listed workflow paths projected."""
    projected = dict(tree)
    for path in registry.current().chains:
        if not path.startswith(WORKFLOW_DIR):
            continue
        if path not in tree:
            _fail(path + " is absent from the tree")
        projected[path] = project_tree_blob(path, tree[path], root=root)
    return projected


def project_ls_tree(raw: bytes, *, root: Path | None = None, keep: Iterable[str] = ()) -> bytes:
    """Project listed paths in a ``git ls-tree -r`` listing; partial listings pass through.

    A head row projects to the chain root only when the working tree is exactly
    that head; a row carrying an earlier chain member (a frozen historical
    listing) passes unchanged; any other blob fails closed. When a full listing
    lacks a listed path, or carries an earlier member where the frozen record
    does not, the caller's own frozen hash comparison still fails. A duplicated
    path fails here. Paths in ``keep`` pass unchanged: the caller authenticates
    and rewrites them from the current bytes itself.
    """
    keep = frozenset(keep)
    chains = registry.current().chains
    lines = []
    seen: dict[str, int] = {}
    for line in raw.splitlines(keepends=True):
        meta, sep, path = line.partition(b"\t")
        name = path.strip().decode() if sep else ""
        if sep and name in chains:
            seen[name] = seen.get(name, 0) + 1
            if name in keep:
                lines.append(line)
                continue
            head, _, blob = meta.rpartition(b" ")
            blob_text = blob.decode("ascii")
            row = _index(chains[name], blob_text)
            # A frozen historical listing already carries an earlier member: it
            # passes unchanged, and the caller's own frozen hash still authenticates it.
            if row is not None and row < len(chains[name].steps):
                projected = blob_text
            else:
                projected = project_tree_blob(name, blob_text, root=root)
            line = head + b" " + projected.encode("ascii") + sep + path
        lines.append(line)
    if any(count > 1 for count in seen.values()):
        _fail("a listed path is duplicated in the tree listing")
    return b"".join(lines)


def is_admitted_successor(name: str, source: bytes) -> bool:
    """True only for a listed path at exact head bytes, authenticated on disk."""
    chain = _chain(name)
    if chain is None:
        return False
    identity = _identity(source)
    ids = chain.identities
    if identity == ids[0]:
        return False
    if identity != ids[-1] or authenticate_current_bytes(None, chain.path) != "AFTER":
        _fail(chain.path + " source bytes are not the admitted after identity")
    return True


def filter_changed_paths(changed: Iterable[str]) -> list[str]:
    """Drop listed workflow paths from a changed-path list only at exact head bytes."""
    changed = list(changed)
    for path in registry.current().chains:
        if path.startswith(WORKFLOW_DIR) and path in changed:
            if authenticate_current_bytes(None, path) != "AFTER":
                _fail(path + " changed but is not the admitted after identity")
            changed = [item for item in changed if item != path]
    return changed


_EMITTING: contextvars.ContextVar[bool] = contextvars.ContextVar("phase_a_emitting", default=False)


@contextlib.contextmanager
def emitting():
    """Disable every source-identity projection while a caller writes a new record.

    A receipt writer must record the true current identity (AFTER), never the
    projected BEFORE; projections exist only to validate frozen records.
    """
    token = _EMITTING.set(True)
    try:
        yield
    finally:
        _EMITTING.reset(token)


def project_source_bytes(path: str, blob: str, normalized: bytes) -> tuple[str, bytes]:
    """Return (blob, LF bytes) for a frozen-record comparison of one source.

    Unlisted paths and record emission pass unchanged. A listed path is
    authenticated on disk first: exact head -> chain-root blob and bytes; exact
    root -> unchanged; anything else (tamper, missing, linked, or bytes that
    disagree with the working tree) raises.
    """
    chain = _chain(path)
    if chain is None or str(path) != chain.path or _EMITTING.get():
        return blob, normalized
    position, _ = _read_working(chain, None)
    ids = chain.identities
    if _identity(normalized) == ids[position] and blob == ids[position][0]:
        if position == 0:
            return blob, normalized
        return ids[0][0], bytes_at(chain.path)
    _fail(chain.path + " source identity does not match the authenticated working tree")
    raise AssertionError("unreachable")


def project_source_identity(path: str, live: bytes, identity):
    """Project a runtime DevelopmentSourceIdentity for a listed path at exact head bytes."""
    if _EMITTING.get() or not is_admitted_after(path, live):
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
    forwards = {}
    for path, chain in registry.current().chains.items():
        if path.startswith(WORKFLOW_DIR):
            (root_blob, root_sha), (head_blob, head_sha) = chain.identities[0], chain.identities[-1]
            forwards[path] = (
                {"git_blob_sha1": root_blob, "source_sha256": root_sha},
                {"git_blob_sha1": head_blob, "source_sha256": head_sha},
            )
    return forwards
