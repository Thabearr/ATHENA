"""SRC-01: standing successor registry, append-only history, chains, level tool."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from scripts import audit_phase_a_workflow_successor as phase_a
from scripts import source_successor_levels as levels
from scripts import source_successor_registry as registry

REPO = registry.ROOT
GENERATIONS = REPO / "tests" / "fixtures" / "core_01d"
GENERATION_NAME = re.compile(r"^ci-offline-transport-boundary-source-inventory-v(\d+)\.json$")
BATCH_1 = "source_successor_batch_0001_ph_a.py"
Err = registry.SuccessorRegistryError

# A synthetic two-step chain: ORIGINAL -(mission one inserts H1)-> A -(mission two inserts H2)-> B.
TARGET = "scripts/synthetic_target.py"
ORIGINAL = b"line one\nline two\n"
H1 = b"inserted by mission one\n"
STEP_A = b"line one\n" + H1 + b"line two\n"
H2 = b"inserted by mission two\n"
STEP_B = STEP_A + H2


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def ident(raw: bytes) -> tuple[str, str]:
    return phase_a._identity(raw)


def entry_src(path, before, after, hunks, *, step=1, reason="synthetic test entry", extra=""):
    b, a = ident(before), ident(after)
    return (f"Successor(path={path!r}, before_blob={b[0]!r}, before_sha256={b[1]!r}, "
            f"after_blob={a[0]!r}, after_sha256={a[1]!r}, hunks={tuple(hunks)!r}, "
            f"reason={reason!r}, step={step!r}{extra})")


def batch_src(sequence, previous, entries, mission="SYN-1", extra=""):
    return ("from scripts.source_successor_registry import Successor\n"
            f"SEQUENCE = {sequence!r}\nMISSION = {mission!r}\nPREVIOUS_BATCH_SHA256 = {previous!r}\n"
            "ENTRIES = (\n    " + ",\n    ".join(entries) + ",\n)\n" + extra)


def batch1_sha(root: Path) -> str:
    return sha((root / "scripts" / BATCH_1).read_bytes())


def write_batch(root: Path, number: int, slug: str, text: str) -> str:
    path = root / "scripts" / f"source_successor_batch_{number:04d}_{slug}.py"
    path.write_text(text, newline="\n")
    return sha(path.read_bytes())


@pytest.fixture
def tmp_registry(tmp_path):
    """A temporary repository root holding only a verbatim copy of batch 0001."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / BATCH_1).write_bytes((REPO / "scripts" / BATCH_1).read_bytes())
    return tmp_path


@pytest.fixture
def chain_root(tmp_registry, monkeypatch):
    """Batches 0002 (step 1) and 0003 (step 2) for TARGET; the working file is STEP_B."""
    previous = batch1_sha(tmp_registry)
    previous = write_batch(tmp_registry, 2, "mission_one", batch_src(
        2, previous, [entry_src(TARGET, ORIGINAL, STEP_A, (H1,), step=1)], mission="SYN-1"))
    write_batch(tmp_registry, 3, "mission_two", batch_src(
        3, previous, [entry_src(TARGET, STEP_A, STEP_B, (H2,), step=2)], mission="SYN-2"))
    monkeypatch.setattr(registry, "ROOT", tmp_registry)
    monkeypatch.setattr(phase_a, "ROOT", tmp_registry)
    work(tmp_registry, STEP_B)
    return tmp_registry


def work(root: Path, raw: bytes | None, *, path: str = TARGET) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.exists():
        target.unlink()
    if raw is not None:
        target.write_bytes(raw)


def flip(raw: bytes) -> bytes:
    index = len(raw) - 2
    return raw[:index] + bytes([raw[index] ^ 0x01]) + raw[index + 1:]


# ---------------------------------------------------------------------------
# The real registry
# ---------------------------------------------------------------------------

def test_real_registry_is_batch_one_with_the_three_pr470_entries():
    loaded = registry.current()
    assert [(b.sequence, b.mission, b.previous_sha256) for b in loaded.batches[:1]] == [(1, "PH-A", "")]
    assert [(e.path, e.step) for e in loaded.batches[0].entries] == [
        (".github/workflows/current-shadow-all-market.yml", 1),
        ("scripts/core_01d_historical_source.py", 1),
        ("scripts/audit_core_01d_retained_workflow_status_v3.py", 1),
    ]
    assert phase_a.PHASE_A_SUCCESSORS == loaded.batches[0].entries == loaded.entries_of("PH-A")
    assert (phase_a.BEFORE_BLOB, phase_a.AFTER_BLOB) == (
        "a06a3166322ccb92b0bc3c05c87c5b3ca17298e1", "62dd84da0c426b0b03729cca5d9d7b4294fb0472")
    assert loaded.batches[0].sha256 == sha((REPO / "scripts" / BATCH_1).read_bytes())


def test_every_registered_path_derives_every_chain_member_exactly():
    for path, chain in registry.current().chains.items():
        for position, (blob, digest) in enumerate(chain.identities):
            assert ident(phase_a.bytes_at(path, blob)) == (blob, digest), (path, position)
        assert phase_a.authenticate_current_bytes(None, path) == "AFTER"


def test_hook_sites_use_only_the_stable_adapter_api():
    hook_files = [
        "scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py",
        "scripts/audit_data_01c_restore_portability.py",
        "scripts/audit_data_01b_durable_run_state.py",
        "scripts/audit_core_01d_authority_reachability_review_a.py",
        "scripts/audit_core_01d_scheduled_shadow_ownership.py",
        "scripts/audit_p4_workflow_evolution_ledger.py",
        "scripts/core_01d_historical_source.py",
        "scripts/audit_core_01d_retained_workflow_status_v3.py",
        "scripts/audit_core_01d_checkpoint_e_completion.py",
    ]
    used = set()
    for relative in hook_files:
        found = set(re.findall(r"\b_?phase_a\.([A-Za-z_]\w*)", (REPO / relative).read_text()))
        assert found, relative
        used |= found
    assert used and all(hasattr(phase_a, name) for name in used), sorted(used)


def test_emitting_disables_every_projection_for_every_registered_path():
    @dataclasses.dataclass(frozen=True)
    class FakeIdentity:
        git_blob_sha1: str
        git_blob_payload_sha256: str
        filtered_worktree_git_blob_sha1: str
        raw_worktree_sha256: str

    for path, chain in registry.current().chains.items():
        raw = (REPO / path).read_bytes().replace(b"\r\n", b"\n")
        head = chain.identities[-1]
        fake = FakeIdentity(head[0], head[1], head[0], head[1])
        with phase_a.emitting():
            assert phase_a.project_source_bytes(path, head[0], raw) == (head[0], raw)
            assert phase_a.project_source_identity(path, raw, fake) == fake
        blob, projected = phase_a.project_source_bytes(path, head[0], raw)
        assert blob == chain.identities[0][0] and ident(projected) == chain.identities[0]
        assert phase_a.project_source_identity(path, raw, fake).git_blob_sha1 == chain.identities[0][0]


# ---------------------------------------------------------------------------
# Loader: every violation fails closed with its own message
# ---------------------------------------------------------------------------

def test_loader_rejects_a_sequence_gap(tmp_registry):
    write_batch(tmp_registry, 3, "gap", batch_src(3, batch1_sha(tmp_registry), [
        entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",))]))
    with pytest.raises(Err, match="batch sequence gap: expected 0002, found 0003"):
        registry.load(tmp_registry)


def test_loader_rejects_a_duplicate_sequence(tmp_registry):
    text = batch_src(2, batch1_sha(tmp_registry), [entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",))])
    write_batch(tmp_registry, 2, "first", text)
    write_batch(tmp_registry, 2, "second", text)
    with pytest.raises(Err, match="duplicate batch sequence 0002"):
        registry.load(tmp_registry)


def test_loader_rejects_a_number_that_differs_from_sequence(tmp_registry):
    write_batch(tmp_registry, 2, "mismatch", batch_src(3, batch1_sha(tmp_registry), [
        entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",))]))
    with pytest.raises(Err, match="batch 0002 declares SEQUENCE 3"):
        registry.load(tmp_registry)


def test_loader_rejects_a_wrong_previous_batch_hash(tmp_registry):
    write_batch(tmp_registry, 2, "chain", batch_src(2, "0" * 64, [
        entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",))]))
    with pytest.raises(Err, match="batch 0002 previous batch hash mismatch"):
        registry.load(tmp_registry)


def test_loader_rejects_an_unknown_field(tmp_registry):
    write_batch(tmp_registry, 2, "extra", batch_src(2, batch1_sha(tmp_registry), [
        entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",), extra=", wildcard='*'")]))
    with pytest.raises(Err, match="batch 0002 has an unknown field or malformed entry"):
        registry.load(tmp_registry)


@pytest.mark.parametrize("mutate", [
    lambda text: text.replace("before_blob='", "before_blob='Z", 1),
    lambda text: re.sub(r"after_sha256='[0-9a-f]{4}", "after_sha256='", text, count=1),
    lambda text: text.replace("scripts/a.py", "scripts/*.py"),
    lambda text: text.replace("scripts/a.py", "scripts/../a.py"),
    lambda text: text.replace("scripts/a.py", "/scripts/a.py"),
    lambda text: text.replace("scripts/a.py", "scripts/"),
])
def test_loader_rejects_a_malformed_id_or_path(tmp_registry, mutate):
    text = batch_src(2, batch1_sha(tmp_registry), [
        entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",))])
    write_batch(tmp_registry, 2, "bad_id", mutate(text))
    with pytest.raises(Err, match="malformed id in batch 0002"):
        registry.load(tmp_registry)


def test_loader_rejects_identical_before_and_after(tmp_registry):
    write_batch(tmp_registry, 2, "noop", batch_src(2, batch1_sha(tmp_registry), [
        entry_src("scripts/a.py", b"a\n", b"a\n", (b"b\n",))]))
    with pytest.raises(Err, match="before and after are identical"):
        registry.load(tmp_registry)


def test_loader_rejects_a_duplicate_path_and_step(tmp_registry):
    write_batch(tmp_registry, 2, "dup", batch_src(2, batch1_sha(tmp_registry), [
        entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",)),
        entry_src("scripts/a.py", b"a\nb\n", b"a\nb\nc\n", (b"c\n",), step=1)]))
    with pytest.raises(Err, match=r"duplicate \(path, step\): scripts/a.py step 1"):
        registry.load(tmp_registry)


def test_loader_rejects_a_repeat_of_a_batch_one_path_at_step_one(tmp_registry):
    write_batch(tmp_registry, 2, "again", batch_src(2, batch1_sha(tmp_registry), [
        entry_src(phase_a.PATH, b"x\n", b"x\ny\n", (b"y\n",))]))
    with pytest.raises(Err, match=r"duplicate \(path, step\)"):
        registry.load(tmp_registry)


@pytest.mark.parametrize("name", [
    "source_successor_batch_2_short.py", "source_successor_batch_0002_Upper.py",
    "source_successor_batch_0002_x.py.bak", "source_successor_batch_0002.py",
])
def test_loader_rejects_a_malformed_batch_file_name(tmp_registry, name):
    (tmp_registry / "scripts" / name).write_text("SEQUENCE = 2\n")
    with pytest.raises(Err, match="batch file name is malformed"):
        registry.load(tmp_registry)


def test_loader_rejects_missing_declarations_and_empty_entries(tmp_registry):
    write_batch(tmp_registry, 2, "empty", "from scripts.source_successor_registry import Successor\n"
                "SEQUENCE = 2\nMISSION = 'X'\nPREVIOUS_BATCH_SHA256 = %r\nENTRIES = ()\n" % batch1_sha(tmp_registry))
    with pytest.raises(Err, match="ENTRIES must be a non-empty tuple"):
        registry.load(tmp_registry)
    write_batch(tmp_registry, 2, "empty", "SEQUENCE = 2\n")
    with pytest.raises(Err, match="batch 0002 is missing MISSION"):
        registry.load(tmp_registry)
    write_batch(tmp_registry, 2, "empty", "raise RuntimeError('boom')\n")
    with pytest.raises(Err, match="batch 0002 failed to load: RuntimeError"):
        registry.load(tmp_registry)


def test_loader_rejects_a_non_successor_entry(tmp_registry):
    write_batch(tmp_registry, 2, "plain", "SEQUENCE = 2\nMISSION = 'X'\n"
                f"PREVIOUS_BATCH_SHA256 = {batch1_sha(tmp_registry)!r}\nENTRIES = ({{'path': 'scripts/a.py'}},)\n")
    with pytest.raises(Err, match="entry is not a Successor"):
        registry.load(tmp_registry)


def test_loader_rejects_an_empty_registry(tmp_path):
    (tmp_path / "scripts").mkdir()
    with pytest.raises(Err, match="no batch files found"):
        registry.load(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_loader_rejects_a_linked_batch_file(tmp_registry):
    real = tmp_registry / "real_batch.py"
    real.write_bytes((tmp_registry / "scripts" / BATCH_1).read_bytes())
    (tmp_registry / "scripts" / BATCH_1).unlink()
    os.symlink(real, tmp_registry / "scripts" / BATCH_1)
    with pytest.raises(Err, match="linked or not a regular file"):
        registry.load(tmp_registry)


def test_editing_an_old_batch_breaks_the_hash_chain(tmp_registry):
    write_batch(tmp_registry, 2, "next", batch_src(2, batch1_sha(tmp_registry), [
        entry_src("scripts/a.py", b"a\n", b"a\nb\n", (b"b\n",))]))
    assert len(registry.load(tmp_registry).batches) == 2
    path = tmp_registry / "scripts" / BATCH_1
    path.write_bytes(path.read_bytes() + b"# an edit\n")
    with pytest.raises(Err, match="batch 0002 previous batch hash mismatch"):
        registry.load(tmp_registry)


def test_the_loader_never_serves_a_stale_cached_registry(tmp_registry):
    first = registry.load(tmp_registry)
    path = tmp_registry / "scripts" / BATCH_1
    path.write_bytes(path.read_bytes().replace(b"SEQUENCE = 1", b"SEQUENCE = 9"))
    with pytest.raises(Err, match="declares SEQUENCE 9"):
        registry.load(tmp_registry)
    path.write_bytes((REPO / "scripts" / BATCH_1).read_bytes())
    assert registry.load(tmp_registry) is first


def test_chain_errors_gap_fork_and_break(tmp_registry):
    previous = batch1_sha(tmp_registry)
    one = entry_src(TARGET, ORIGINAL, STEP_A, (H1,), step=1)
    # gap: step 3 without step 2
    write_batch(tmp_registry, 2, "gap", batch_src(2, previous, [
        one, entry_src(TARGET, STEP_A, STEP_B, (H2,), step=3)]))
    with pytest.raises(Err, match=f"chain gap for {TARGET}: expected step 2, got 3"):
        registry.load(tmp_registry)
    # fork: step 3 starts again from step 1's after identity instead of step 2's
    other = b"line one\n" + H1 + b"line two\nother\n"
    write_batch(tmp_registry, 2, "gap", batch_src(2, previous, [
        one, entry_src(TARGET, STEP_A, STEP_B, (H2,), step=2),
        entry_src(TARGET, STEP_A, other, (b"other\n",), step=3)]))
    with pytest.raises(Err, match=f"chain fork for {TARGET} at step 3"):
        registry.load(tmp_registry)
    # break: step 2 starts from an identity that is in no earlier step
    write_batch(tmp_registry, 2, "gap", batch_src(2, previous, [
        one, entry_src(TARGET, b"unrelated\n", STEP_B, (H2,), step=2)]))
    with pytest.raises(Err, match=f"chain break for {TARGET} at step 2"):
        registry.load(tmp_registry)


# ---------------------------------------------------------------------------
# Append-only history against the frozen A2 generations (P3)
# ---------------------------------------------------------------------------

def check_append_only(root: Path, generations: Path) -> None:
    numbers = sorted(int(m.group(1)) for p in generations.iterdir() if (m := GENERATION_NAME.match(p.name)))
    assert numbers and numbers == list(range(1, numbers[-1] + 1)), "A2 generation files are not contiguous"
    batches = sorted((root / "scripts").glob("source_successor_batch_*.py"))
    assert batches, "no batch files"
    listed: dict[str, dict[int, str]] = {path.name: {} for path in batches}
    for number in numbers:
        text = (generations / f"ci-offline-transport-boundary-source-inventory-v{number}.json").read_text()
        if "source_successor_batch_" not in text:
            continue
        rows = {row["path"]: row["lf_source_sha256"] for row in json.loads(text)["source_identities"]}
        for name in listed:
            if "scripts/" + name in rows:
                listed[name][number] = rows["scripts/" + name]
    for path in batches:
        history = listed[path.name]
        current = sha(path.read_bytes())
        assert history, f"{path.name} is not listed by any A2 generation"
        first = min(history)
        assert sorted(history) == list(range(first, numbers[-1] + 1)), \
            f"{path.name} is not listed by every generation from V{first} to the latest"
        assert set(history.values()) == {current}, \
            f"{path.name} was edited after it first appeared in A2 generation V{first}"


def test_batch_files_are_append_only_against_the_a2_generations():
    check_append_only(REPO, GENERATIONS)


def fake_generations(directory: Path, rows_by_generation: list[dict[str, str]]) -> Path:
    directory.mkdir()
    for number, rows in enumerate(rows_by_generation, start=1):
        document = {"source_identities": [{"path": p, "lf_source_sha256": s} for p, s in rows.items()]}
        (directory / f"ci-offline-transport-boundary-source-inventory-v{number}.json").write_text(json.dumps(document))
    return directory


def test_append_only_history_check_accepts_an_unedited_batch(tmp_registry, tmp_path):
    name = "scripts/" + BATCH_1
    current = batch1_sha(tmp_registry)
    generations = fake_generations(tmp_path / "gens", [{}, {name: current}, {name: current}])
    check_append_only(tmp_registry, generations)


def test_append_only_history_check_rejects_an_edited_old_batch(tmp_registry, tmp_path):
    name = "scripts/" + BATCH_1
    original = batch1_sha(tmp_registry)
    generations = fake_generations(tmp_path / "gens", [{name: original}, {name: original}])
    path = tmp_registry / "scripts" / BATCH_1
    path.write_bytes(path.read_bytes() + b"# edited after merge\n")
    with pytest.raises(AssertionError, match="was edited after it first appeared in A2 generation V1"):
        check_append_only(tmp_registry, generations)


def test_append_only_history_check_rejects_a_changed_listing_between_generations(tmp_registry, tmp_path):
    name = "scripts/" + BATCH_1
    current = batch1_sha(tmp_registry)
    generations = fake_generations(tmp_path / "gens", [{name: "1" * 64}, {name: current}])
    with pytest.raises(AssertionError, match="was edited after it first appeared"):
        check_append_only(tmp_registry, generations)


def test_append_only_history_check_rejects_a_removed_and_re_added_batch(tmp_registry, tmp_path):
    name = "scripts/" + BATCH_1
    current = batch1_sha(tmp_registry)
    generations = fake_generations(tmp_path / "gens", [{name: current}, {}, {name: current}])
    with pytest.raises(AssertionError, match="not listed by every generation"):
        check_append_only(tmp_registry, generations)


def test_append_only_history_check_rejects_a_batch_missing_from_the_latest_generation(tmp_registry, tmp_path):
    name = "scripts/" + BATCH_1
    current = batch1_sha(tmp_registry)
    generations = fake_generations(tmp_path / "gens", [{name: current}, {}])
    with pytest.raises(AssertionError, match="not listed by every generation"):
        check_append_only(tmp_registry, generations)


def test_append_only_history_check_rejects_an_unlisted_batch_and_missing_generations(tmp_registry, tmp_path):
    generations = fake_generations(tmp_path / "gens", [{}, {}])
    with pytest.raises(AssertionError, match="is not listed by any A2 generation"):
        check_append_only(tmp_registry, generations)
    holes = fake_generations(tmp_path / "holes", [{}, {}])
    (holes / "ci-offline-transport-boundary-source-inventory-v1.json").unlink()
    with pytest.raises(AssertionError, match="not contiguous"):
        check_append_only(tmp_registry, holes)


# ---------------------------------------------------------------------------
# Chain semantics (P4), on a synthetic two-step chain that is never registered for real
# ---------------------------------------------------------------------------

def test_chain_head_authenticates_and_every_member_derives(chain_root):
    chain = registry.current(chain_root).chains[TARGET]
    assert [s.step for s in chain.steps] == [1, 2]
    assert chain.identities == (ident(ORIGINAL), ident(STEP_A), ident(STEP_B))
    assert phase_a.authenticate_current_bytes(chain_root, TARGET) == "AFTER"
    assert phase_a.before_bytes(TARGET, chain_root) == ORIGINAL
    assert phase_a.bytes_at(TARGET, ident(STEP_A)[0], chain_root) == STEP_A
    assert phase_a.bytes_at(TARGET, ident(STEP_B)[0], chain_root) == STEP_B
    assert phase_a.bytes_at(TARGET, None, chain_root) == ORIGINAL


def test_chain_default_target_is_the_frozen_original_and_a_middle_member_is_a_target(chain_root):
    head = ident(STEP_B)[0]
    assert phase_a.project_tree_blob(TARGET, head, root=chain_root) == ident(ORIGINAL)[0]
    assert phase_a.project_tree_blob_to(TARGET, head, ident(STEP_A)[0], root=chain_root) == ident(STEP_A)[0]
    assert phase_a.project_tree_blob_to(TARGET, head, head, root=chain_root) == head
    collapsed = phase_a.entry_for(TARGET)
    assert (collapsed.before_blob, collapsed.after_blob, collapsed.step) == (ident(ORIGINAL)[0], head, 2)


def test_chain_rejects_a_target_that_is_not_a_member_or_is_later_than_the_working_tree(chain_root):
    head = ident(STEP_B)[0]
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="not a member of the successor chain"):
        phase_a.project_tree_blob_to(TARGET, head, "0" * 40, root=chain_root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="not a member of the successor chain"):
        phase_a.bytes_at(TARGET, "0" * 40, chain_root)
    work(chain_root, STEP_A)
    assert phase_a.authenticate_current_bytes(chain_root, TARGET) == "INTERMEDIATE"
    assert phase_a.project_tree_blob(TARGET, ident(STEP_A)[0], root=chain_root) == ident(ORIGINAL)[0]
    assert phase_a.bytes_at(TARGET, None, chain_root) == ORIGINAL
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="does not match the authenticated working tree"):
        phase_a.project_tree_blob(TARGET, ident(STEP_B)[0], root=chain_root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="later than the authenticated working tree"):
        phase_a.project_tree_blob_to(TARGET, ident(STEP_A)[0], ident(STEP_B)[0], root=chain_root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="later than the authenticated working tree"):
        phase_a.bytes_at(TARGET, ident(STEP_B)[0], chain_root)
    work(chain_root, ORIGINAL)
    assert phase_a.authenticate_current_bytes(chain_root, TARGET) == "BEFORE"
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="later than the authenticated working tree"):
        phase_a.project_tree_blob_to(TARGET, ident(ORIGINAL)[0], ident(STEP_A)[0], root=chain_root)


@pytest.mark.parametrize("raw", [flip(STEP_B), flip(STEP_A), flip(ORIGINAL), STEP_B + b"x", b""])
def test_chain_one_byte_tamper_fails_closed_everywhere(chain_root, raw):
    work(chain_root, raw)
    for call in (
        lambda: phase_a.authenticate_current_bytes(chain_root, TARGET),
        lambda: phase_a.before_bytes(TARGET, chain_root),
        lambda: phase_a.bytes_at(TARGET, ident(STEP_A)[0], chain_root),
        lambda: phase_a.project_tree_blob(TARGET, ident(STEP_B)[0], root=chain_root),
        lambda: phase_a.project_tree_blob_to(TARGET, ident(STEP_B)[0], ident(STEP_A)[0], root=chain_root),
        lambda: phase_a.is_admitted_after(TARGET, STEP_B, root=chain_root),
    ):
        with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="unadmitted"):
            call()


def test_chain_deleted_and_linked_working_files_fail_closed(chain_root, tmp_path):
    work(chain_root, None)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="is missing"):
        phase_a.authenticate_current_bytes(chain_root, TARGET)
    if os.name != "nt":
        real = tmp_path / "real_target.bin"
        real.write_bytes(STEP_B)
        os.symlink(real, chain_root / TARGET)
        with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="is linked"):
            phase_a.authenticate_current_bytes(chain_root, TARGET)


def test_chain_reverse_application_verifies_the_identity_at_every_step(tmp_registry, monkeypatch):
    """A step whose hunk is not really in the bytes cannot be silently skipped."""
    previous = batch1_sha(tmp_registry)
    previous = write_batch(tmp_registry, 2, "one", batch_src(2, previous, [
        entry_src(TARGET, ORIGINAL, STEP_A, (H1,), step=1)]))
    write_batch(tmp_registry, 3, "two", batch_src(3, previous, [
        entry_src(TARGET, STEP_A, STEP_B, (b"never present\n",), step=2)]))
    monkeypatch.setattr(registry, "ROOT", tmp_registry)
    work(tmp_registry, STEP_B)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="exactly one copy of each hunk"):
        phase_a.before_bytes(TARGET, tmp_registry)
    # A hunk that is present but does not reproduce the recorded identity also fails.
    write_batch(tmp_registry, 3, "two", batch_src(3, previous, [
        entry_src(TARGET, STEP_A, STEP_B, (b"line one\n",), step=2)]))
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="not the admitted before identity"):
        phase_a.before_bytes(TARGET, tmp_registry)


def test_chain_listing_projection_and_helpers(chain_root):
    head, middle, root_blob = ident(STEP_B)[0], ident(STEP_A)[0], ident(ORIGINAL)[0]
    row = lambda blob: b"100644 blob " + blob.encode() + b"\t" + TARGET.encode() + b"\n"
    assert phase_a.project_ls_tree(row(head), root=chain_root) == row(root_blob)
    assert phase_a.project_ls_tree(row(middle), root=chain_root) == row(middle)  # frozen earlier listing
    assert phase_a.project_ls_tree(row(root_blob), root=chain_root) == row(root_blob)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_ls_tree(row("0" * 40), root=chain_root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_ls_tree(row(head) + row(head), root=chain_root)
    assert phase_a.is_admitted_after(TARGET, STEP_B, root=chain_root)
    assert not phase_a.is_admitted_after(TARGET, STEP_A, root=chain_root)
    assert phase_a.is_admitted_successor(TARGET, STEP_B) is True
    assert phase_a.is_admitted_successor(TARGET, ORIGINAL) is False
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.is_admitted_successor(TARGET, STEP_A)
    assert phase_a.project_source_bytes(TARGET, head, STEP_B) == (root_blob, ORIGINAL)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.project_source_bytes(TARGET, head, flip(STEP_B))


def test_workflow_chain_forwards_use_the_chain_root_and_head(tmp_registry, monkeypatch):
    workflow = ".github/workflows/synthetic-chain.yml"
    one, two, three = b"name: s\n", b"name: s\non: push\n", b"name: s\non: push\njobs: {}\n"
    previous = write_batch(tmp_registry, 2, "wf_one", batch_src(2, batch1_sha(tmp_registry), [
        entry_src(workflow, one, two, (b"on: push\n",), step=1)]))
    write_batch(tmp_registry, 3, "wf_two", batch_src(3, previous, [
        entry_src(workflow, two, three, (b"jobs: {}\n",), step=2)]))
    monkeypatch.setattr(registry, "ROOT", tmp_registry)
    forwards = phase_a.p4_workflow_forwards()
    assert forwards[workflow] == (
        {"git_blob_sha1": ident(one)[0], "source_sha256": ident(one)[1]},
        {"git_blob_sha1": ident(three)[0], "source_sha256": ident(three)[1]})
    assert set(forwards) == {phase_a.PATH, workflow}


# ---------------------------------------------------------------------------
# Zero new hooks: a new batch is honoured by the existing adapter functions
# ---------------------------------------------------------------------------

def test_a_new_batch_is_honoured_with_no_code_change(tmp_registry, monkeypatch):
    path = "scripts/synthetic_new_target.py"
    before, hunk = b"alpha\nomega\n", b"beta\n"
    after = b"alpha\nbeta\nomega\n"
    write_batch(tmp_registry, 2, "synthetic", batch_src(2, batch1_sha(tmp_registry), [
        entry_src(path, before, after, (hunk,))]))
    monkeypatch.setattr(registry, "ROOT", tmp_registry)
    monkeypatch.setattr(phase_a, "ROOT", tmp_registry)
    work(tmp_registry, after, path=path)
    (b_blob, _), (a_blob, _) = ident(before), ident(after)
    assert phase_a.is_successor_path(path)
    assert phase_a.authenticate_current_bytes(None, path) == "AFTER"
    assert phase_a.project_tree_blob(path, a_blob) == b_blob
    assert phase_a.before_bytes(path) == before
    assert phase_a.is_admitted_after(path, after) and phase_a.is_admitted_successor(path, after)
    assert phase_a.project_source_bytes(path, a_blob, after) == (b_blob, before)
    listing = b"100644 blob " + a_blob.encode() + b"\t" + path.encode() + b"\n"
    assert phase_a.project_ls_tree(listing) == listing.replace(a_blob.encode(), b_blob.encode())

    @dataclasses.dataclass(frozen=True)
    class FakeIdentity:
        git_blob_sha1: str
        git_blob_payload_sha256: str

    live = FakeIdentity(a_blob, ident(after)[1])
    assert phase_a.project_source_identity(path, after, live) == FakeIdentity(b_blob, ident(before)[1])
    work(tmp_registry, flip(after), path=path)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError, match="unadmitted"):
        phase_a.project_tree_blob(path, a_blob)
    # The previously registered Phase A workflow is untouched by the new batch.
    assert phase_a.entry_for(phase_a.PATH).after_blob == phase_a.AFTER_BLOB


def test_an_unregistered_path_is_never_projected(chain_root):
    other = "scripts/not_registered.py"
    assert not phase_a.is_successor_path(other)
    assert phase_a.project_tree_blob(other, "f" * 40, root=chain_root) == "f" * 40
    assert phase_a.project_source_bytes(other, "f" * 40, b"x") == ("f" * 40, b"x")
    assert not phase_a.is_admitted_after(other, b"x", root=chain_root)
    with pytest.raises(phase_a.PhaseAWorkflowSuccessorError):
        phase_a.before_bytes(other, chain_root)


# ---------------------------------------------------------------------------
# Level tool (P6): read-only, no network, temporary repository fixture
# ---------------------------------------------------------------------------

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def run_git(repo: Path, *args: str) -> str:
    # The offline transport guard only accepts -c options before -C.
    done = subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                           "-C", str(repo), *args], capture_output=True, check=True)
    return done.stdout.decode()


@pytest.fixture
def level_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    files = {
        "scripts/free.py": b"free = 1\n",
        "scripts/pinned.py": b"pinned = 2\n",
        "scripts/pinned_deep.py": b"deep = 3\n",
        "scripts/lonely_record_target.py": b"lonely = 4\n",
        "tests/conftest.py": b"# root pinned\n",
    }

    def identity(name):
        raw = files[name]
        return git_blob(raw), hashlib.sha256(raw).hexdigest()

    def holds(*names):
        return "\n".join(" ".join(identity(name)) for name in names) + "\n"

    reader_ok = b"RECORD = 'artifacts/record.json'\n"
    reader_pinned = b"RECORD = 'artifacts/record_deep.json'\n"
    files.update({"scripts/reader_ok.py": reader_ok, "scripts/reader_pinned.py": reader_pinned})
    files.update({
        "artifacts/record.json": holds("scripts/pinned.py").encode(),
        "artifacts/record_deep.json": holds("scripts/pinned_deep.py").encode(),
        "artifacts/record_lonely.json": holds("scripts/lonely_record_target.py").encode(),
        "artifacts/record_reader_pin.json": holds("scripts/reader_pinned.py").encode(),
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v1.json": holds(
            "scripts/free.py", "scripts/pinned.py", "scripts/pinned_deep.py", "scripts/lonely_record_target.py",
            "tests/conftest.py", "scripts/reader_ok.py", "scripts/reader_pinned.py").encode(),
    })
    for name, raw in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "fixture")
    return repo


def test_level_tool_reports_l0_l1_l2_and_l2_candidates(level_repo):
    assert levels.classify(level_repo, "scripts/free.py", "HEAD")["level"] == "L0"
    pinned = levels.classify(level_repo, "scripts/pinned.py", "HEAD")
    assert pinned["level"] == "L1" and pinned["records"] == ["artifacts/record.json"]
    assert pinned["readers"] == {"artifacts/record.json": ["scripts/reader_ok.py"]}
    assert pinned["a2_generations"] == 1
    deep = levels.classify(level_repo, "scripts/pinned_deep.py", "HEAD")
    assert deep["level"] == "L2?" and "scripts/reader_pinned.py" in deep["reason"]
    assert "artifacts/record_reader_pin.json" in deep["reason"]
    lonely = levels.classify(level_repo, "scripts/lonely_record_target.py", "HEAD")
    assert lonely["level"] == "L1" and "no reader found" in lonely["reason"]
    assert levels.classify(level_repo, "tests/conftest.py", "HEAD")["level"] == "L2"


def test_level_tool_cli_text_json_and_never_writes(level_repo, capsys):
    before = run_git(level_repo, "status", "--porcelain")
    assert levels.main(["scripts/free.py", "scripts/pinned.py", "--ref", "HEAD"], root=level_repo) == 0
    text = capsys.readouterr().out
    assert "scripts/free.py" in text and "suggested level: L0" in text and "suggested level: L1" in text
    assert levels.main(["scripts/pinned.py", "--ref", "HEAD", "--json"], root=level_repo) == 0
    document = json.loads(capsys.readouterr().out)
    assert document[0]["path"] == "scripts/pinned.py" and document[0]["level"] == "L1"
    assert run_git(level_repo, "status", "--porcelain") == before == ""


def test_level_tool_reports_a_missing_path_without_a_traceback(level_repo, capsys):
    assert levels.main(["scripts/does_not_exist.py", "--ref", "HEAD"], root=level_repo) == 2
    assert "source_successor_levels:" in capsys.readouterr().err


def test_level_tool_does_not_count_registry_batches_as_records(level_repo):
    batch = level_repo / "scripts" / "source_successor_batch_0001_ph_a.py"
    free = (level_repo / "scripts" / "free.py").read_bytes()
    batch.write_text(f"# mentions {git_blob(free)}\n")
    run_git(level_repo, "add", "-A")
    run_git(level_repo, "commit", "-q", "-m", "batch")
    assert levels.classify(level_repo, "scripts/free.py", "HEAD")["records"] == []
