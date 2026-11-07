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
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    if raw is not None:
        if link:
            real = tmp_path / "real.yml"
            real.write_bytes(raw)
            os.symlink(real, workflows / phase_a.NAME)
        else:
            (workflows / phase_a.NAME).write_bytes(raw)
    return tmp_path


def _flip(raw: bytes) -> bytes:
    index = raw.index(b"pc-upcoming-discovery")
    return raw[:index] + b"PC" + raw[index + 2:]


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
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_ls_tree(b"100644 blob " + b"e" * 40 + b"\t.github/workflows/athena-run.yml\n")
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
