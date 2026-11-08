"""VAR-05: chain work budget, balanced shards, batch-driven admissions."""
from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import ci_select_test_shard as shards
from scripts import pytest_a2_chain_share as share_plugin
from scripts import source_successor_registry as registry

REPO = registry.ROOT
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"
BATCH_1 = "source_successor_batch_0001_ph_a.py"
Err = registry.SuccessorRegistryError


# ---------------------------------------------------------------------------
# Part B: work budget (deterministic, never wall-clock)
# ---------------------------------------------------------------------------

def _real_loader():
    loader = boundary.load_inventory_generations
    return getattr(loader, "__wrapped__", loader)


def _seed(directory: Path, generations: int = 2) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for generation in range(1, generations + 1):
        source = boundary.ROOT / boundary.inventory_generation_path(generation)
        shutil.copyfile(source, directory / source.name)


def _share(directory: Path):
    module = types.ModuleType("a2_view")
    module.__dict__.update(vars(boundary))
    module.load_inventory_generations = _real_loader()
    module.INVENTORY_DIRECTORY = str(directory)
    return share_plugin._ChainShare(module)


class _Reporter:
    def __init__(self):
        self.lines: list[str] = []

    def write_line(self, line, **_):
        self.lines.append(line)


def _finish(monkeypatch, share):
    """Run the plugin's session-finish and terminal-summary hooks for ``share``."""
    monkeypatch.setattr(share_plugin, "_state", share)
    session = types.SimpleNamespace(exitstatus=0)
    share_plugin.pytest_sessionfinish(session, 0)
    reporter = _Reporter()
    share_plugin.pytest_terminal_summary(reporter)
    return session.exitstatus, reporter.lines


def _decode_times(share, other: Path, times: int, test: str = "tests/example.py::loop"):
    share.current_test = test
    for _ in range(times):
        share.load(str(other))  # another directory is never shared: a real decode each time


def test_budget_exceeded_fails_the_session_with_the_exact_line(tmp_path, monkeypatch):
    _seed(tmp_path / "chain")
    _seed(tmp_path / "other")
    share = _share(tmp_path / "chain")
    share.budget = 2
    _decode_times(share, tmp_path / "other", 3)
    status, lines = _finish(monkeypatch, share)
    assert status == 1
    assert "A2_CHAIN_SHARE_BUDGET_EXCEEDED: decodes=3 budget=2 last_test=tests/example.py::loop" in lines
    assert lines[0].startswith("A2_CHAIN_SHARE: hits=0 stores=0 unshared=3 full_checks=0 cheap_checks=0 "
                               "decodes=3 budget=2 bytes_hashed=")


def test_budget_at_the_limit_passes(tmp_path, monkeypatch):
    _seed(tmp_path / "chain")
    _seed(tmp_path / "other")
    share = _share(tmp_path / "chain")
    share.budget = 2
    _decode_times(share, tmp_path / "other", 2)
    status, lines = _finish(monkeypatch, share)
    assert status == 0
    assert not any(share_plugin.BUDGET_FAILURE in line for line in lines)
    assert "decodes=2 budget=2" in lines[0]


def test_stores_count_as_decodes_and_hits_do_not(tmp_path, monkeypatch):
    _seed(tmp_path / "chain")
    share = _share(tmp_path / "chain")
    share.budget = 1
    share.current_test = "tests/example.py::warm"
    first = share.load()
    for _ in range(5):
        share.load()
    assert (share.metrics["stores"], share.metrics["hits"], share.decodes) == (1, 5, 1)
    assert share.metrics["bytes_hashed"] > 0
    assert first == _real_loader()(str(tmp_path / "chain"))
    status, lines = _finish(monkeypatch, share)
    assert status == 0 and "decodes=1 budget=1" in lines[0]


def test_mutation_and_budget_failures_both_surface(tmp_path, monkeypatch):
    _seed(tmp_path / "chain")
    _seed(tmp_path / "other")
    share = _share(tmp_path / "chain")
    share.budget = 1
    share.current_test = "tests/example.py::mutator"
    chain = share.load()
    chain[-1][1]["source_identities"].pop()
    _decode_times(share, tmp_path / "other", 2, test="tests/example.py::heavy")
    status, lines = _finish(monkeypatch, share)
    assert status == 1
    assert any(line.startswith("A2_CHAIN_SHARE_FAILURE: " + share_plugin.MUTATION_FAILURE) for line in lines)
    assert "A2_CHAIN_SHARE_BUDGET_EXCEEDED: decodes=3 budget=1 last_test=tests/example.py::heavy" in lines


def test_budget_constant_is_twice_the_observed_maximum_rounded_up():
    assert share_plugin.BUDGET_DECODES >= 2 * share_plugin.BUDGET_OBSERVED_MAX
    assert share_plugin.BUDGET_DECODES % 100 == 0
    assert share_plugin.BUDGET_DECODES - 2 * share_plugin.BUDGET_OBSERVED_MAX < 100


def test_budget_is_active_in_this_pytest_process_and_the_kill_switch_still_disables(monkeypatch):
    if os.environ.get(share_plugin.DISABLE_ENV) == "1":
        pytest.skip("chain share disabled for this process")
    assert share_plugin._state is not None and share_plugin._state.budget == share_plugin.BUDGET_DECODES
    monkeypatch.setenv(share_plugin.DISABLE_ENV, "1")
    module = types.ModuleType("a2_view")
    module.__dict__.update(vars(boundary))
    original = module.load_inventory_generations
    assert share_plugin.install(module) is None and module.load_inventory_generations is original


# ---------------------------------------------------------------------------
# Part C: balanced, deterministic shards
# ---------------------------------------------------------------------------

def _real_files():
    return sorted((REPO / "tests").rglob("test_*.py"))


def _relative(files):
    return [Path(path).relative_to(REPO) for path in files]


def test_partition_covers_the_real_tree_exactly_once_for_eight_shards():
    files = _relative(_real_files())
    parts = shards.partition(files, 8)
    flat = [path for part in parts for path in part]
    assert len(parts) == 8 and all(parts)
    assert sorted(flat) == sorted(files) and len(flat) == len(set(flat))
    selected = [shards.select(files, number, 8) for number in range(1, 9)]
    assert selected == parts


def test_partition_is_deterministic_and_independent_of_input_order():
    files = _relative(_real_files())
    shuffled = list(files)
    random.Random(5).shuffle(shuffled)
    assert shards.partition(files, 8) == shards.partition(shuffled, 8) == shards.partition(list(files), 8)
    assert all(part == sorted(part, key=lambda p: p.as_posix()) for part in shards.partition(files, 8))


def test_lpt_greedy_example_and_unknown_files_take_the_median(monkeypatch):
    monkeypatch.setattr(shards, "DURATIONS", {"t/a.py": 10.0, "t/b.py": 8.0, "t/c.py": 6.0,
                                              "t/d.py": 5.0, "t/e.py": 4.0})
    files = ["t/e.py", "t/d.py", "t/c.py", "t/b.py", "t/a.py"]
    # a(10)->0, b(8)->1, c(6)->1 (8 < 10), d(5)->0 (10 < 14), e(4)->1 (14 < 15)
    assert shards.partition(files, 2) == [["t/a.py", "t/d.py"], ["t/b.py", "t/c.py", "t/e.py"]]
    assert shards.predicted_loads(files, 2) == [15.0, 18.0]
    # An unknown file weighs the median (6.0): it lands like c would.
    assert shards.predicted_loads(["t/a.py", "t/new.py"], 2) == [10.0, 6.0]


def test_select_refuses_bad_input_and_an_inconsistent_partition(monkeypatch):
    files = ["t/a.py", "t/b.py", "t/c.py"]
    with pytest.raises(ValueError, match="outside 1..2"):
        shards.select(files, 3, 2)
    with pytest.raises(ValueError, match="duplicate test file"):
        shards.partition(["t/a.py", "t/a.py"], 2)
    with pytest.raises(ValueError, match="positive integer"):
        shards.partition(files, 0)
    real = shards.partition
    monkeypatch.setattr(shards, "partition", lambda items, count: [list(items), list(items)[:1]])
    with pytest.raises(ValueError, match="not disjoint and complete"):
        shards.select(files, 1, 2)
    monkeypatch.setattr(shards, "partition", lambda items, count: [list(items)[1:], []])
    with pytest.raises(ValueError, match="not disjoint and complete"):
        shards.select(files, 1, 2)
    monkeypatch.setattr(shards, "partition", lambda items, count: [list(items)])
    with pytest.raises(ValueError, match="wrong number of shards"):
        shards.select(files, 1, 2)
    monkeypatch.setattr(shards, "partition", real)
    assert sorted(shards.select(files, 1, 2) + shards.select(files, 2, 2)) == files


def test_duration_table_only_names_test_files():
    assert shards.DURATIONS and all(key.startswith("tests/") and key.endswith(".py")
                                    and Path(key).name.startswith("test_") for key in shards.DURATIONS)
    assert all(isinstance(value, float) and value >= 0 for value in shards.DURATIONS.values())


def test_tests_workflow_is_unchanged_and_the_selector_is_not_wired_in_yet():
    """Part C is deferred (root-pinned check); tests.yml keeps its positional selection."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ci_select_test_shard" not in text and "timeout-minutes" not in text
    assert "          selected = files[shard_number - 1 :: shard_count]\n" in text
    assert ".github/workflows/tests.yml" not in registry.current().chains
    for kept in ("name: test shard ${{ matrix.shard }} of 8", "    name: syntax\n", "    name: test\n",
                 'test "${SHARD_RESULT}" = "success"', "shard: [1, 2, 3, 4, 5, 6, 7, 8]"):
        assert kept in text, kept
    assert shards.__doc__.splitlines()[0] == "Not yet wired into tests.yml; see Plan v2.0 ROOT-01."


def test_the_selector_is_importable_from_a_stdin_script_with_the_workspace_on_pythonpath():
    script = ("from pathlib import Path\n"
              "from scripts.ci_select_test_shard import select\n"
              "files = sorted(Path('tests').rglob('test_*.py'))\n"
              "print(sum(len(select(files, n, 8)) for n in range(1, 9)) == len(files))\n")
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    output = subprocess.run([sys.executable, "-"], input=script, cwd=REPO, env=env,
                            capture_output=True, text=True, check=True).stdout
    assert output.strip().endswith("True")


# ---------------------------------------------------------------------------
# Part D: batch-driven admissions (ADDED_PATHS, FIRST_GENERATION)
# ---------------------------------------------------------------------------

def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


@pytest.fixture
def tmp_registry(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / BATCH_1).write_bytes((REPO / "scripts" / BATCH_1).read_bytes())
    return tmp_path


def _batch(root: Path, body: str, *, entries: str = "()", number: int = 2) -> None:
    previous = _sha((root / "scripts" / BATCH_1).read_bytes())
    text = ("from scripts.source_successor_registry import Successor\n"
            f"SEQUENCE = {number}\nMISSION = 'SYN'\nPREVIOUS_BATCH_SHA256 = {previous!r}\n"
            f"ENTRIES = {entries}\n" + body)
    (root / "scripts" / f"source_successor_batch_{number:04d}_syn.py").write_text(text, newline="\n")


def _new_file(root: Path, path: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n")


def test_real_registry_declares_batch_two_and_its_added_paths():
    loaded = registry.current()
    assert [(b.sequence, b.mission) for b in loaded.batches] == [(1, "PH-A"), (2, "VAR-05")]
    assert loaded.batches[1].previous_sha256 == loaded.batches[0].sha256
    assert loaded.added_paths() == {
        "scripts/ci_select_test_shard.py": 351,
        "scripts/source_successor_batch_0002_var_05.py": 351,
        "tests/test_var_05_ci_guardrails.py": 351,
    }
    assert loaded.batches[1].entries == ()
    assert ".github/workflows/tests.yml" not in loaded.chains


def test_added_paths_are_accepted_when_well_formed(tmp_registry):
    _new_file(tmp_registry, "scripts/new_tool.py")
    _batch(tmp_registry, "ADDED_PATHS = ('scripts/new_tool.py',)\nFIRST_GENERATION = 351\n")
    assert registry.load(tmp_registry).added_paths() == {"scripts/new_tool.py": 351}


@pytest.mark.parametrize("body, message", [
    ("ADDED_PATHS = ('scripts/*.py',)\nFIRST_GENERATION = 351\n", "malformed id in batch 0002 ADDED_PATHS"),
    ("ADDED_PATHS = ('scripts/../x.py',)\nFIRST_GENERATION = 351\n", "malformed id in batch 0002 ADDED_PATHS"),
    ("ADDED_PATHS = ('scripts/new_tool.py',)\n", "without a valid FIRST_GENERATION"),
    ("ADDED_PATHS = ('scripts/new_tool.py',)\nFIRST_GENERATION = 0\n", "without a valid FIRST_GENERATION"),
    ("ADDED_PATHS = ()\nFIRST_GENERATION = 351\n", "FIRST_GENERATION without ADDED_PATHS"),
    ("ADDED_PATHS = ['scripts/new_tool.py']\nFIRST_GENERATION = 351\n", "ADDED_PATHS must be a tuple"),
    ("ADDED_PATHS = ('scripts/new_tool.py', 'scripts/new_tool.py')\nFIRST_GENERATION = 351\n", "lists a path twice"),
    ("ADDED_PATHS = ('scripts/absent.py',)\nFIRST_GENERATION = 351\n", "added path is missing: scripts/absent.py"),
    ("", "ENTRIES must be a non-empty tuple"),
])
def test_added_paths_are_rejected_when_malformed(tmp_registry, body, message):
    _new_file(tmp_registry, "scripts/new_tool.py")
    _batch(tmp_registry, body)
    with pytest.raises(Err, match=message.replace("*", r"\*").replace(".", r"\.")):
        registry.load(tmp_registry)


def test_added_paths_may_not_overlap_an_entries_path(tmp_registry):
    path = "scripts/audit_core_01d_retained_workflow_status_v3.py"  # a batch-1 ENTRIES path
    _new_file(tmp_registry, path)
    _batch(tmp_registry, f"ADDED_PATHS = ({path!r},)\nFIRST_GENERATION = 351\n")
    with pytest.raises(Err, match="ADDED_PATHS overlaps an ENTRIES path"):
        registry.load(tmp_registry)


def test_added_paths_may_not_repeat_across_batches(tmp_registry):
    _new_file(tmp_registry, "scripts/new_tool.py")
    _batch(tmp_registry, "ADDED_PATHS = ('scripts/new_tool.py',)\nFIRST_GENERATION = 351\n")
    second_previous = _sha((tmp_registry / "scripts" / "source_successor_batch_0002_syn.py").read_bytes())
    (tmp_registry / "scripts" / "source_successor_batch_0003_syn.py").write_text(
        "SEQUENCE = 3\nMISSION = 'SYN'\n"
        f"PREVIOUS_BATCH_SHA256 = {second_previous!r}\nENTRIES = ()\n"
        "ADDED_PATHS = ('scripts/new_tool.py',)\nFIRST_GENERATION = 352\n", newline="\n")
    with pytest.raises(Err, match="repeats a path added earlier"):
        registry.load(tmp_registry)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_added_path_that_is_a_symlink_fails(tmp_registry):
    real = tmp_registry / "real.py"
    real.write_text("x = 1\n")
    os.symlink(real, tmp_registry / "scripts" / "new_tool.py")
    _batch(tmp_registry, "ADDED_PATHS = ('scripts/new_tool.py',)\nFIRST_GENERATION = 351\n")
    with pytest.raises(Err, match="added path is linked"):
        registry.load(tmp_registry)


def test_added_path_existence_is_rechecked_after_caching(tmp_registry):
    _new_file(tmp_registry, "scripts/new_tool.py")
    _batch(tmp_registry, "ADDED_PATHS = ('scripts/new_tool.py',)\nFIRST_GENERATION = 351\n")
    registry.load(tmp_registry)
    (tmp_registry / "scripts" / "new_tool.py").unlink()
    with pytest.raises(Err, match="added path is missing"):
        registry.load(tmp_registry)
    (tmp_registry / "scripts" / "new_tool.py").mkdir()
    with pytest.raises(Err, match="added path is not a regular file"):
        registry.load(tmp_registry)
