"""Tamper matrix for the Phase A current-shadow-all-market.yml workflow successor."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as a2
from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4
from scripts import audit_data_01c_restore_portability as d5
from scripts import audit_phase_a_workflow_successor as phase_a

COPY_LINE = b"            '.cache/athena-research/current-shadow-sportybet-pc-upcoming-discovery' \\\n"
VERIFY_BLOCK = (
    b"          # Verify copied raw pages, manifests and capture epochs against the\n"
    b"          # exact source tree and the completed run receipt before artifact upload.\n"
    b"          # Runs last so a verification failure cannot skip the identity-state copy.\n"
    b"          python -m scripts.verify_current_shadow_pc_upcoming_archive\n"
    b"\n"
)


def _after_bytes() -> bytes:
    return (phase_a.ROOT / phase_a.PATH).read_bytes().replace(b"\r\n", b"\n")


def _before_bytes() -> bytes:
    """Main's exact bytes, rebuilt offline (shallow CI has no before object)."""
    after = _after_bytes()
    assert after.count(COPY_LINE) == 1 and after.count(VERIFY_BLOCK) == 1
    before = after.replace(COPY_LINE, b"", 1).replace(VERIFY_BLOCK, b"", 1)
    assert hashlib.sha256(before).hexdigest() == phase_a.BEFORE_SHA256
    return before


def _root_with(tmp_path: Path, raw: bytes | None, *, link: bool = False) -> Path:
    return _root_for(tmp_path, phase_a.PATH, raw, link=link)


def _root_for(tmp_path: Path, path: str, raw: bytes | None, *, link: bool = False) -> Path:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        if link:
            real = tmp_path / "real.bin"
            real.write_bytes(raw)
            os.symlink(real, target)
        else:
            target.write_bytes(raw)
    return tmp_path


def _flip(raw: bytes) -> bytes:
    index = raw.index(b"pc-upcoming-discovery")
    return raw[:index] + b"PC" + raw[index + 2:]


def _flip_one(raw: bytes) -> bytes:
    """Flip exactly one byte in the last line (inside every entry's own hunk-free tail)."""
    index = len(raw) - 2
    return raw[:index] + bytes([raw[index] ^ 0x01]) + raw[index + 1:]


def _patched_read_bytes(monkeypatch, path: str, mutate):
    """Serve mutated bytes for one repository path to every Path.read_bytes caller."""
    original = Path.read_bytes
    target = (phase_a.ROOT / path).resolve()

    def patched(self):
        raw = original(self)
        try:
            same = self.resolve() == target
        except OSError:
            same = False
        return mutate(raw) if same else raw

    monkeypatch.setattr(Path, "read_bytes", patched)


def test_constants_match_the_committed_after_bytes():
    raw = _after_bytes()
    assert phase_a._git_blob_sha1(raw) == phase_a.AFTER_BLOB
    assert hashlib.sha256(raw).hexdigest() == phase_a.AFTER_SHA256
    assert phase_a.authenticate_current_bytes() == "AFTER"


# a) workflow at AFTER bytes -> session-start projection passes
def test_a_after_bytes_pass_the_session_start_workflow_projection():
    a2.authenticate_predecessors()
    head = subprocess.check_output(["git", "rev-parse", "HEAD:.github/workflows"],
                                   cwd=a2.ROOT, text=True).strip()
    assert d5.historical_workflow_tree(head) == a2.WORKFLOW_TREE


def test_a_after_blob_projects_to_before_blob_only_for_this_path():
    assert phase_a.project_tree_blob(phase_a.NAME, phase_a.AFTER_BLOB) == phase_a.BEFORE_BLOB
    assert phase_a.project_tree_blob("athena-run.yml", "f" * 40) == "f" * 40


# b) one byte flipped -> fails closed
def test_b_flipped_byte_fails_closed(tmp_path):
    root = _root_with(tmp_path, _flip(_after_bytes()))
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="unadmitted"):
        phase_a.authenticate_current_bytes(root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="unadmitted"):
        phase_a.project_tree_blob(phase_a.NAME, phase_a.AFTER_BLOB, root=root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.is_admitted_successor(phase_a.NAME, _flip(_after_bytes()))


def test_b_tree_blob_that_disagrees_with_the_working_tree_fails(tmp_path):
    root = _root_with(tmp_path, _after_bytes())
    for blob in (phase_a.BEFORE_BLOB, "0" * 40):
        with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
            phase_a.project_tree_blob(phase_a.NAME, blob, root=root)


# c) workflow restored to BEFORE bytes -> projection is identity (main state)
def test_c_before_bytes_project_to_identity(tmp_path):
    root = _root_with(tmp_path, _before_bytes())
    assert phase_a.authenticate_current_bytes(root) == "BEFORE"
    tree = {phase_a.PATH: phase_a.BEFORE_BLOB, ".github/workflows/athena-run.yml": "e" * 40}
    assert phase_a.project_workflow_tree(tree, root=root) == tree
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_tree_blob(phase_a.NAME, phase_a.AFTER_BLOB, root=root)


# d) a different workflow changed while this one is at AFTER -> existing error
def test_d_other_workflow_change_still_fails_with_the_existing_error(monkeypatch):
    original = Path.read_bytes

    def tampered(self):
        raw = original(self)
        if self.name == "athena-run.yml" and self.parent.name == "workflows":
            return raw + b"# tampered\n"
        return raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(ValueError, match="unrelated workflow changed in D5 successor: athena-run.yml"):
        d5.authenticate_workflow()


def test_d_projection_never_touches_other_paths():
    tree = {phase_a.PATH: phase_a.AFTER_BLOB, ".github/workflows/athena-run.yml": "e" * 40}
    projected = phase_a.project_workflow_tree(tree)
    assert projected[".github/workflows/athena-run.yml"] == "e" * 40
    assert projected is not tree and tree[phase_a.PATH] == phase_a.AFTER_BLOB


# e) PATH deleted -> fails closed
def test_e_deleted_workflow_fails_closed(tmp_path):
    root = _root_with(tmp_path, None)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="missing"):
        phase_a.authenticate_current_bytes(root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_workflow_tree({".github/workflows/athena-run.yml": "e" * 40})
    # A listing without PATH passes through; the caller's frozen hash then fails.
    other = b"100644 blob " + b"e" * 40 + b"\t.github/workflows/athena-run.yml\n"
    assert phase_a.project_ls_tree(other) == other
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_observed_identities({})


# f) PATH replaced by a symlink to identical bytes -> fails closed
@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_f_symlink_to_identical_bytes_fails_closed(tmp_path):
    root = _root_with(tmp_path, _after_bytes(), link=True)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="linked"):
        phase_a.authenticate_current_bytes(root)


# g) composition with the B4 direct-share projection is order-independent
def test_g_projection_commutes_with_the_b4_projection():
    head = subprocess.check_output(["git", "ls-tree", "HEAD:.github/workflows"],
                                   cwd=a2.ROOT, text=True).splitlines()
    tree = {}
    for row in head:
        meta, name = row.split("\t", 1)
        tree[".github/workflows/" + name] = meta.split()[2]
    b4_map = {}
    for path in b4.B4_WORKFLOW_PREDECESSORS:
        raw = b4._historical_b4_workflow_bytes(path)
        b4_map[path] = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    assert phase_a.PATH not in b4_map

    def apply_b4(mapping):
        return {**mapping, **b4_map}

    assert apply_b4(phase_a.project_workflow_tree(tree)) == phase_a.project_workflow_tree(apply_b4(tree))


def test_ls_tree_and_identity_projections_are_exact():
    line = b"100644 blob " + phase_a.AFTER_BLOB.encode() + b"\t" + phase_a.PATH.encode() + b"\n"
    other = b"100644 blob " + b"e" * 40 + b"\t.github/workflows/athena-run.yml\n"
    projected = phase_a.project_ls_tree(other + line)
    assert projected == other + line.replace(phase_a.AFTER_BLOB.encode(), phase_a.BEFORE_BLOB.encode())
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_ls_tree(other + line + line)
    observed = {phase_a.PATH: {"git_blob_sha1": phase_a.AFTER_BLOB, "source_sha256": phase_a.AFTER_SHA256}}
    assert phase_a.project_observed_identities(observed)[phase_a.PATH] == {
        "git_blob_sha1": phase_a.BEFORE_BLOB, "source_sha256": phase_a.BEFORE_SHA256}
    forged = {phase_a.PATH: {"git_blob_sha1": phase_a.AFTER_BLOB, "source_sha256": "0" * 64}}
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_observed_identities(forged)


def test_changed_path_filter_admits_only_the_after_bytes():
    assert phase_a.filter_changed_paths(["a.py", phase_a.PATH]) == ["a.py"]
    assert phase_a.filter_changed_paths(["a.py"]) == ["a.py"]


def test_before_bytes_derivation_is_exact_and_fails_closed(tmp_path):
    assert phase_a.before_bytes() == _before_bytes()
    flipped = _root_with(tmp_path / "flipped", _flip(_after_bytes()))
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.before_bytes(root=flipped)
    main_state = _root_with(tmp_path / "main", _before_bytes())
    assert phase_a.before_bytes(root=main_state) == _before_bytes()


def test_review_a_reads_the_admitted_before_bytes():
    from scripts import audit_core_01d_authority_reachability_review_a as review
    assert review.source_bytes(phase_a.PATH) == _before_bytes()


# ---------------------------------------------------------------------------
# PH-A2 C1: the closed table and its per-entry matrix
# ---------------------------------------------------------------------------

def test_c1_table_is_closed_and_exact():
    paths = [entry.path for entry in phase_a.PHASE_A_SUCCESSORS]
    assert paths == [".github/workflows/current-shadow-all-market.yml", "scripts/core_01d_historical_source.py"]
    for entry in phase_a.PHASE_A_SUCCESSORS:
        assert "*" not in entry.path and not entry.path.endswith("/")
        assert len(entry.before_blob) == len(entry.after_blob) == 40
        assert len(entry.before_sha256) == len(entry.after_sha256) == 64
        assert entry.hunks and entry.reason
    assert not phase_a.is_successor_path(".github/workflows/athena-run.yml")
    assert not phase_a.is_successor_path(".github/workflows/")
    assert phase_a.entry_for("current-shadow-all-market.yml") is phase_a.WORKFLOW


@pytest.mark.parametrize("entry", phase_a.PHASE_A_SUCCESSORS, ids=lambda e: e.path)
def test_c4_entry_matrix(entry, tmp_path):
    after = (phase_a.ROOT / entry.path).read_bytes().replace(b"\r\n", b"\n")
    assert phase_a._identity(after) == (entry.after_blob, entry.after_sha256)
    # AFTER passes and derives BEFORE exactly.
    assert phase_a.authenticate_current_bytes(path=entry.path) == "AFTER"
    before = phase_a.before_bytes(entry.path)
    assert phase_a._identity(before) == (entry.before_blob, entry.before_sha256)
    assert phase_a.project_tree_blob(entry.path, entry.after_blob) == entry.before_blob
    # One-byte tamper fails closed.
    tampered = _root_for(tmp_path / "tampered", entry.path, _flip_one(after))
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.authenticate_current_bytes(tampered, entry.path)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.before_bytes(entry.path, tampered)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_tree_blob(entry.path, entry.after_blob, root=tampered)
    assert not phase_a.is_admitted_after(entry.path, _flip_one(after))
    # BEFORE passes unchanged.
    main_state = _root_for(tmp_path / "main", entry.path, before)
    assert phase_a.authenticate_current_bytes(main_state, entry.path) == "BEFORE"
    assert phase_a.before_bytes(entry.path, main_state) == before
    assert phase_a.project_tree_blob(entry.path, entry.before_blob, root=main_state) == entry.before_blob
    # Deleted fails closed.
    deleted = _root_for(tmp_path / "deleted", entry.path, None)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="missing"):
        phase_a.authenticate_current_bytes(deleted, entry.path)
    # Symlink to identical bytes fails closed.
    if os.name != "nt":
        linked = _root_for(tmp_path / "linked", entry.path, after, link=True)
        with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="linked"):
            phase_a.authenticate_current_bytes(linked, entry.path)


def test_c4_listing_projects_both_entries_and_nothing_else():
    rows = []
    for entry in phase_a.PHASE_A_SUCCESSORS:
        rows.append(b"100644 blob " + entry.after_blob.encode() + b"\t" + entry.path.encode() + b"\n")
    other = b"100644 blob " + b"e" * 40 + b"\ttests/test_p4_2_athena_run_workflow.py\n"
    projected = phase_a.project_ls_tree(other + b"".join(rows))
    expected = other + b"".join(
        row.replace(entry.after_blob.encode(), entry.before_blob.encode())
        for row, entry in zip(rows, phase_a.PHASE_A_SUCCESSORS))
    assert projected == expected


# ---------------------------------------------------------------------------
# PH-A2 M1: the D5 workflow skip is conditional on authenticated AFTER bytes
# ---------------------------------------------------------------------------

def test_m1_one_byte_tamper_makes_authenticate_workflow_raise(monkeypatch):
    d5.authenticate_workflow()
    _patched_read_bytes(monkeypatch, phase_a.PATH, _flip_one)
    with pytest.raises(ValueError):
        d5.authenticate_workflow()


def test_m1_other_workflow_change_raises_the_existing_message(monkeypatch):
    _patched_read_bytes(monkeypatch, ".github/workflows/athena-run.yml", lambda raw: raw + b"# tampered\n")
    with pytest.raises(ValueError, match="unrelated workflow changed in D5 successor: athena-run.yml"):
        d5.authenticate_workflow()


# ---------------------------------------------------------------------------
# PH-A2 M2: review A authenticates the current file before serving bytes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry", phase_a.PHASE_A_SUCCESSORS, ids=lambda e: e.path)
def test_m2_review_a_one_byte_tamper_raises(entry, monkeypatch):
    from scripts import audit_core_01d_authority_reachability_review_a as review
    _patched_read_bytes(monkeypatch, entry.path, _flip_one)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        review.source_bytes(entry.path)


@pytest.mark.parametrize("entry", phase_a.PHASE_A_SUCCESSORS, ids=lambda e: e.path)
def test_m2_review_a_before_state_is_identical_to_main(entry, monkeypatch, tmp_path):
    from scripts import audit_core_01d_authority_reachability_review_a as review
    before = phase_a.before_bytes(entry.path)
    main_state = _root_for(tmp_path, entry.path, before)
    monkeypatch.setattr(phase_a, "ROOT", main_state)
    served = review.source_bytes(entry.path)
    assert served == before
    assert phase_a._identity(served) == (entry.before_blob, entry.before_sha256)


# ---------------------------------------------------------------------------
# PH-A2 C4: table closure and the F1/F2 consumers
# ---------------------------------------------------------------------------

def test_c4_unlisted_pinned_test_file_change_keeps_the_original_error(monkeypatch):
    """A changed pinned file outside the table is never projected (F4 test bytes)."""
    path = "tests/test_p4_2_athena_run_workflow.py"
    assert not phase_a.is_successor_path(path)
    raw = (phase_a.ROOT / path).read_bytes()
    assert not phase_a.is_admitted_after(path, raw)
    blob = phase_a._git_blob_sha1(raw)
    line = b"100644 blob " + blob.encode() + b"\t" + path.encode() + b"\n"
    assert phase_a.project_ls_tree(line) == line
    assert phase_a.project_tree_blob(path, "0" * 40) == "0" * 40
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.before_bytes(path)


def test_c4_unlisted_producer_change_keeps_the_original_f1_error(monkeypatch):
    from scripts import core_01d_historical_source as historical
    import runtime.source_identity as source_identity
    original = source_identity.read_tracked_head_blob

    def tampered(root, path):
        raw, identity = original(root, path)
        if str(path) == ".github/workflows/athena-run.yml":
            import dataclasses
            identity = dataclasses.replace(identity, git_blob_sha1="0" * 40)
        return raw, identity

    monkeypatch.setattr(source_identity, "read_tracked_head_blob", tampered)
    with pytest.raises(ValueError, match="unreviewed current producer source: .github/workflows/athena-run.yml"):
        historical.historical_tracked(phase_a.ROOT, ".github/workflows/athena-run.yml")


def test_f1_historical_tracked_admits_only_the_exact_after_bytes():
    from scripts import core_01d_historical_source as historical
    historical.historical_tracked(phase_a.ROOT, phase_a.PATH)


def test_f2_other_legacy_edit_still_raises_legacy_change_beyond_schedule_removal(monkeypatch):
    from scripts import audit_core_01d_scheduled_shadow_ownership as ownership
    ownership.validate_workflow_source()
    assert ownership.raw(phase_a.PATH) == phase_a.before_bytes()
    # A different edit to the legacy workflow is not the admitted delta: no projection.
    _patched_read_bytes(monkeypatch, phase_a.PATH, _flip)
    with pytest.raises(ValueError, match="legacy change beyond schedule removal"):
        ownership.validate_workflow_source()


def test_f3_f4_registry_carries_only_the_exact_workflow_forward():
    from scripts import audit_p4_workflow_evolution_ledger as evolution
    before, after = evolution.CORE01D_PR119_CONTROL_WORKFLOW_FORWARD[phase_a.PATH]
    assert before == {"git_blob_sha1": phase_a.BEFORE_BLOB, "source_sha256": phase_a.BEFORE_SHA256}
    assert after == {"git_blob_sha1": phase_a.AFTER_BLOB, "source_sha256": phase_a.AFTER_SHA256}
    assert "scripts/core_01d_historical_source.py" not in evolution.CORE01D_PR119_CONTROL_WORKFLOW_FORWARD
