"""Adversarial proofs for the append-only A2 source-inventory generation chain.

Historical A2 evidence must stay byte-identical while the current corpus is
authenticated against the latest reviewed generation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

V1_CANONICAL_SHA256 = "ca8c07c071538298ffb293027e7a0be1c5766e8a943b3d2b605627f9ffe922dd"
V1_SITECUSTOMIZE_SHA256 = "364bd75e8137dcb79dab70cc15c7c72808f069cbbaf28d0cd54e3f4a22579b32"
A2_RECEIPT_SHA256 = "5d0385f77463d3e7a9f804b431df7e2c2c9c4908c266326bf35b05a50086f8e2"
COMPLETION_V3_SHA256 = "27516b35fb5e836ac2d851fa60e4300ebf347e00b00f3858b46671cd77af9d79"
EVOLUTION_TERMINAL = "CORE_01D_A2_INVENTORY_EVOLUTION_BRIDGE_REVIEW_READY_DO_NOT_MERGE"
SCRATCH_SOURCE = b"import socket\n\ndef probe():\n    return socket.create_connection(('192.0.2.1', 9))\n"


def _lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def _name(relative_path: str) -> str:
    return Path(relative_path).name


def _committed_bytes(relative_path: str, commit: str) -> bytes:
    raw = subprocess.check_output(["git", "show", f"{commit}:{relative_path}"], cwd=boundary.ROOT)
    return _lf(raw)


def _bridge_base_ref() -> str:
    """Bridge base commit when the object database has it, else the checkout tip.

    Hosted CI checks out depth 1, so the bridge-base ancestors are absent there
    and no fetch is permitted; the exact base comparison still runs in any full
    clone (local review), while the sealed canonical assertions below hold on
    every runner.
    """
    if boundary.historical_objects_available(boundary.BRIDGE_BASE_MAIN):
        return boundary.BRIDGE_BASE_MAIN
    return "HEAD"


def _worktree_bytes(relative_path: str) -> bytes:
    return _lf((boundary.ROOT / relative_path).read_bytes())


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_generations(directory: Path, include_v2: bool = True) -> None:
    """Copy the immutable reviewed generations into an isolated directory."""
    directory.mkdir(parents=True, exist_ok=True)
    sources = [boundary.INVENTORY_PATH]
    if include_v2:
        sources.append(boundary.INVENTORY_V2_PATH)
    for relative_path in sources:
        shutil.copyfile(boundary.ROOT / relative_path, directory / _name(relative_path))


def _write_generation(directory: Path, document: dict, filename: str) -> Path:
    target = directory / filename
    target.write_bytes(boundary.canonical(document))
    return target


def _current_chain() -> list:
    return boundary.load_inventory_generations()


# --- A. V1 immutability ----------------------------------------------------
def test_v1_inventory_is_immutable_and_rederived_from_historical_git_bytes():
    value = boundary.read(boundary.INVENTORY_PATH)
    assert value["canonical_sha256"] == boundary.INVENTORY_V1_SHA256 == V1_CANONICAL_SHA256
    assert boundary.authenticate_historical_v1() == value
    pinned = {row["path"]: row["lf_source_sha256"] for row in value["source_identities"]}
    exact = boundary.historical_objects_available(boundary.A2_REVIEWED_HEAD)
    if exact:
        # Exact reviewed-head rederivation whenever the Git objects exist.
        assert boundary.build_inventory_historical() == value
    # Independent re-derivation straight from the A2 reviewed-head Git object;
    # in a depth-1 checkout (no ancestor object, no fetch) the byte-pinned
    # identity chain in the immutable inventory is the equivalent proof.
    for relative_path in (
        "sitecustomize.py",
        "scripts/audit_core_01d_ci_offline_transport_boundary.py",
        "tests/conftest.py",
        "tests/offline_transport.py",
        "tests/offline_linux.py",
    ):
        observed = boundary.historical_source(relative_path)["lf_source_sha256"]
        assert observed == pinned[relative_path]
        if exact:
            assert observed == hashlib.sha256(
                _committed_bytes(relative_path, boundary.A2_REVIEWED_HEAD)).hexdigest()


def test_any_v1_byte_change_is_rejected(tmp_path):
    directory = tmp_path / "generations"
    directory.mkdir()
    target = directory / _name(boundary.INVENTORY_PATH)
    raw = (boundary.ROOT / boundary.INVENTORY_PATH).read_bytes()

    target.write_bytes(raw + b" ")
    with pytest.raises(AssertionError, match="artifact self-hash mismatch"):
        boundary.load_inventory_generations(str(directory))

    tampered = json.loads(raw)
    tampered["proof_owner"] = "TAMPERED_HISTORICAL_OWNER"
    # Re-sealed so only the immutable generation-1 identity can reject it.
    target.write_bytes(boundary.canonical(boundary.seal(tampered)))
    with pytest.raises(AssertionError, match="immutable A2 V1 inventory"):
        boundary.load_inventory_generations(str(directory))


# --- B. A2 receipt immutability --------------------------------------------
def test_a2_receipt_is_immutable_and_reconstructed_only_from_historical_evidence():
    receipt = boundary.read(boundary.RECEIPT_PATH)
    assert receipt["canonical_sha256"] == boundary.RECEIPT_SHA256 == A2_RECEIPT_SHA256
    assert receipt == boundary.build_receipt()
    # The immutable receipt keeps binding the immutable generation-1 inventory;
    # the reviewed successor generation is never substituted into it.
    assert receipt["inventory"] == {"path": boundary.INVENTORY_PATH,
                                    "canonical_sha256": V1_CANONICAL_SHA256}
    latest = boundary.authenticate_inventory()
    assert latest["canonical_sha256"] != receipt["inventory"]["canonical_sha256"]
    assert receipt["guard_sources"] == [boundary.historical_source(path)
                                        for path in boundary.GUARD_PATHS]


# --- C. Completion V3 immutability -----------------------------------------
def test_completion_v3_and_a2_evidence_are_byte_identical_to_the_bridge_base():
    for relative_path in (
        boundary.INVENTORY_PATH,
        boundary.RECEIPT_PATH,
        boundary.COMPLETION_PATH,
        "scripts/audit_core_01d_checkpoint_e_completion_v3.py",
    ):
        assert _worktree_bytes(relative_path) == _committed_bytes(relative_path, _bridge_base_ref()), relative_path
    # On runners without the bridge-base objects, each immutable JSON artifact
    # must still be exactly the canonical serialization of its own sealed
    # document, and the pins below bind those seals to the reviewed identities.
    for relative_path in (boundary.INVENTORY_PATH, boundary.RECEIPT_PATH, boundary.COMPLETION_PATH):
        assert _worktree_bytes(relative_path) == boundary.canonical(boundary.read(relative_path)), relative_path
    value = boundary.read(boundary.COMPLETION_PATH)
    assert value["canonical_sha256"] == boundary.COMPLETION_V3_SHA256 == COMPLETION_V3_SHA256
    from scripts import audit_core_01d_checkpoint_e_completion_v3 as v3
    assert v3.audit()["result"] == "PASS"


# --- D. current latest inventory -------------------------------------------
def test_latest_generation_is_a_full_reviewed_copy_of_the_current_corpus():
    latest = boundary.authenticate_inventory()
    assert latest.get("generation") == 41
    v34 = boundary.read_generation(boundary.inventory_generation_path(34))
    assert v34["canonical_sha256"] == "7f432dc51e6ceb18becacfee06593fe33bbefc85d0417109896068e5d7d090b2"
    v35 = boundary.read_generation(boundary.inventory_generation_path(35))
    assert v35["canonical_sha256"] == "446460f116aec411284d69c65394435c9996052e9e611ae84f873d111387c4cd"
    v36 = boundary.read_generation(boundary.inventory_generation_path(36))
    assert v36["canonical_sha256"] == "04be46014ba688351f88a5fdb2b58d29455f24de6a1d0ca5a51a24c9763e1224"
    v37 = boundary.read_generation(boundary.inventory_generation_path(37))
    assert v37["canonical_sha256"] == "33ed379bb8941fbfd1672fcb2d69543c5970a17471ccde3de4d85293f822b79e"
    v38 = boundary.read_generation(boundary.inventory_generation_path(38))
    assert v38["canonical_sha256"] == "c0169b031d7451b0182a42416cf84a97687bbda47004b41c5ce5c2f022882e88"
    v39 = boundary.read_generation(boundary.inventory_generation_path(39))
    assert v39["canonical_sha256"] == "2b0f6b305f9ce77b75f1a08fc35ecc3b4cf5b952aff2a8b0b4cd701621a3f75c"
    v40 = boundary.read_generation(boundary.inventory_generation_path(40))
    assert v40["canonical_sha256"] == "64bbe0f42d0874442a39d9e35f77a100d5da17ecbc1538b25c5e4a38405e56bb"
    assert latest["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(40),
        "canonical_sha256": v40["canonical_sha256"],
        "generation": 40,
        "rewritten": False,
    }
    assert latest == boundary.build_inventory()
    assert latest["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(40),
        "canonical_sha256": "64bbe0f42d0874442a39d9e35f77a100d5da17ecbc1538b25c5e4a38405e56bb",
        "generation": 40,
        "rewritten": False,
    }
    assert boundary.read_generation(boundary.inventory_generation_path(30))["canonical_sha256"] == (
        "bd4ea91731b2819911051cea90d09cff880194022082e5bb7c3637409cdba4d0"
    )
    assert boundary.read_generation(boundary.inventory_generation_path(31))["canonical_sha256"] == (
        "92048f7c721369f409cb7ef7e09ae437e626458d2baf59738299f3db722dbdc8"
    )
    assert boundary.read_generation(boundary.inventory_generation_path(32))["canonical_sha256"] == (
        "b7421f255527285c70e671d34c029bc00a98d3e29ef0415633e8e4c990cdc0b0"
    )
    assert boundary.read_generation(boundary.inventory_generation_path(33))["canonical_sha256"] == (
        "366222cfe37299fa49365aa8566f8b60d3c401ecc0fde5535298d76304a0d7c8"
    )
    assert latest["bridge_base_main_sha"] == boundary.BRIDGE_BASE_MAIN
    assert latest["historical_a2_reviewed_head"] == boundary.A2_REVIEWED_HEAD
    current_paths = {row["path"] for row in latest["source_identities"]}
    historical_paths = {row["path"] for row in boundary.read(boundary.INVENTORY_PATH)["source_identities"]}
    assert boundary.EVOLUTION_TEST_PATH in current_paths
    assert boundary.EVOLUTION_TEST_PATH not in historical_paths
    # A full corpus, not a delta: every reviewed source identity is present.
    for relative_path in boundary.A2_PATHS:
        if relative_path.endswith(".py") and (boundary.ROOT / relative_path).exists():
            assert relative_path in current_paths
    assert latest["source_identities"] == [boundary.source(path)
                                           for path in boundary.current_source_paths()]


# --- E. additive source fails closed ---------------------------------------
def test_new_python_source_without_a_successor_inventory_fails_before_collection():
    scratch = boundary.ROOT / "tests" / "test_core_01d_unreviewed_scratch_probe.py"
    assert not scratch.exists(), "scratch residue from a previous run"
    scratch.write_bytes(SCRATCH_SOURCE)
    try:
        with pytest.raises(AssertionError, match="source or process discovery drift"):
            boundary.authenticate_inventory()
    finally:
        scratch.unlink()
    assert not scratch.exists()
    boundary.authenticate_inventory()


# --- F. successor admission -------------------------------------------------
def test_valid_successor_generation_admits_new_reviewed_source(tmp_path):
    directory = tmp_path / "generations"
    _seed_generations(directory)
    sealed_before = {name: _file_sha256(directory / name)
                     for name in sorted(path.name for path in directory.iterdir())}
    chain = boundary.load_inventory_generations(str(directory))
    assert [Path(path) for path, _ in chain] == [directory / _name(boundary.INVENTORY_PATH),
                                                 directory / _name(boundary.INVENTORY_V2_PATH)]
    corpus = boundary.current_corpus_fields()
    added = {"path": "tests/test_future_reviewed_source.py", "lf_source_sha256": "0" * 64}
    extended = dict(corpus, source_identities=[*corpus["source_identities"], added])

    # Before the reviewed successor exists, the extended corpus is rejected.
    with pytest.raises(AssertionError, match="source or process discovery drift"):
        boundary.authenticate_inventory(str(directory),
                                        current=boundary.inventory_document(chain[-1][1], extended))

    successor = boundary.build_successor_inventory(str(directory), corpus=extended)
    _write_generation(directory, successor, "ci-offline-transport-boundary-source-inventory-v3.json")
    assert len(boundary.load_inventory_generations(str(directory))) == 3
    assert boundary.authenticate_inventory(str(directory), current=successor)["generation"] == 3
    # The predecessor generations are never rewritten to admit new source.
    assert {name: _file_sha256(directory / name) for name in sealed_before} == sealed_before


# --- G. missing generation --------------------------------------------------
def test_missing_intermediate_generation_is_rejected(tmp_path):
    directory = tmp_path / "generations"
    _seed_generations(directory)
    successor = boundary.build_successor_inventory(str(directory))
    _write_generation(directory, successor, "ci-offline-transport-boundary-source-inventory-v3.json")
    (directory / _name(boundary.INVENTORY_V2_PATH)).unlink()
    with pytest.raises(AssertionError, match="missing intermediate inventory generation"):
        boundary.load_inventory_generations(str(directory))


# --- H. wrong predecessor hash ---------------------------------------------
def test_wrong_predecessor_canonical_hash_is_rejected(tmp_path):
    directory = tmp_path / "generations"
    _seed_generations(directory)
    successor = boundary.build_successor_inventory(str(directory))
    successor["predecessor_inventory"]["canonical_sha256"] = "0" * 64
    _write_generation(directory, boundary.seal(successor),
                      "ci-offline-transport-boundary-source-inventory-v3.json")
    with pytest.raises(AssertionError, match="predecessor canonical hash mismatch"):
        boundary.load_inventory_generations(str(directory))


# --- I. duplicate / forked generation --------------------------------------
def test_forked_generation_candidate_is_rejected(tmp_path):
    directory = tmp_path / "generations"
    _seed_generations(directory)
    successor = boundary.build_successor_inventory(str(directory))
    _write_generation(directory, successor, "ci-offline-transport-boundary-source-inventory-v3.json")
    _write_generation(directory, successor, "ci-offline-transport-boundary-source-inventory-v03.json")
    with pytest.raises(AssertionError, match="inventory generation"):
        boundary.load_inventory_generations(str(directory))


# --- J. partial / delta-only successor -------------------------------------
def test_partial_successor_that_omits_the_current_corpus_is_rejected(tmp_path):
    directory = tmp_path / "generations"
    _seed_generations(directory)
    corpus = boundary.current_corpus_fields()
    partial = dict(corpus, source_identities=corpus["source_identities"][:10],
                   transport_and_process_discovery_obligations=[])
    successor = boundary.build_successor_inventory(str(directory), corpus=partial)
    _write_generation(directory, successor, "ci-offline-transport-boundary-source-inventory-v3.json")
    with pytest.raises(AssertionError, match="source or process discovery drift"):
        boundary.authenticate_inventory(str(directory))


# --- K. source drift --------------------------------------------------------
def test_reviewed_source_identity_drift_is_rejected():
    value = boundary.build_inventory()
    value["source_identities"][0] = {"path": value["source_identities"][0]["path"],
                                     "lf_source_sha256": "0" * 64}
    with pytest.raises(AssertionError, match="source or process discovery drift"):
        boundary.authenticate_inventory(current=boundary.seal(value))


# --- L. obligation drift ----------------------------------------------------
def test_transport_obligation_drift_is_rejected_and_still_classified():
    rows = boundary.classified_obligations(
        "tests/test_synthetic_bridge_caller.py",
        b"import socket\nsocket.create_connection(('192.0.2.1', 9))\n")
    assert any(row["callee"] == "socket.create_connection"
               and row["classification"] == "GUARDED_BY_IN_PROCESS_TRANSPORT_DENIAL"
               for row in rows)
    value = boundary.build_inventory()
    value["transport_and_process_discovery_obligations"].append(
        {"path": "tests/test_unreviewed_bridge_caller.py", "line": 1,
         "callee": "socket.create_connection",
         "classification": "GUARDED_BY_IN_PROCESS_TRANSPORT_DENIAL"})
    with pytest.raises(AssertionError, match="source or process discovery drift"):
        boundary.authenticate_inventory(current=boundary.seal(value))


# --- M. no generic bypass ---------------------------------------------------
def test_no_environment_switch_selects_or_skips_a_generation(monkeypatch):
    for name in ("ATHENA_CORE_01D_INVENTORY_GENERATION", "ATHENA_CORE_01D_INVENTORY_DIRECTORY",
                 "CORE_01D_SKIP_INVENTORY", "ATHENA_SKIP_SOURCE_REVIEW"):
        monkeypatch.setenv(name, "1")
    assert boundary.discover_inventory_generations()[-1][0] == 41
    assert boundary.authenticate_inventory()["generation"] == 41
    scratch = boundary.ROOT / "tests" / "test_core_01d_unreviewed_scratch_probe.py"
    assert not scratch.exists()
    scratch.write_bytes(SCRATCH_SOURCE)
    try:
        with pytest.raises(AssertionError, match="source or process discovery drift"):
            boundary.authenticate_inventory()
    finally:
        scratch.unlink()
    source = (boundary.ROOT / "scripts/audit_core_01d_ci_offline_transport_boundary.py").read_text(encoding="utf-8")
    assert "import os" not in source
    assert "getenv(" not in source
    assert "environ[" not in source


# --- N. root bootstrap ------------------------------------------------------
def test_root_bootstrap_pin_binds_the_current_auditor_and_rejects_drift(monkeypatch):
    import ast
    import offline_transport
    startup = ast.parse((boundary.ROOT / "sitecustomize.py").read_text(encoding="utf-8"))
    pins = next(ast.literal_eval(node.value) for node in startup.body
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                and target.id == "ROOT_TEST_SOURCE_PINS" for target in node.targets))
    auditor = "scripts/audit_core_01d_ci_offline_transport_boundary.py"
    protected = sorted((set(boundary.GUARD_PATHS) - {"sitecustomize.py"}) | {auditor})
    assert sorted(pins) == protected
    assert pins[auditor] == boundary.source(auditor)["lf_source_sha256"]
    assert pins[auditor] == hashlib.sha256(_worktree_bytes(auditor)).hexdigest()

    original = Path.read_bytes
    def altered(path):
        if Path(path).name == Path(auditor).name:
            return b"# tampered auditor source\n"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", altered)
    monkeypatch.setattr(sys, "orig_argv", ["python", "-m", "pytest"])
    monkeypatch.setattr(offline_transport, "install", lambda: pytest.fail("UNGUARDED_INSTALL"))
    with pytest.raises(SystemExit, match="failed to activate"):
        runpy.run_path(str(boundary.ROOT / "sitecustomize.py"))


# --- O. boundary semantics --------------------------------------------------
def test_transport_boundary_semantics_and_hosted_native_markers_are_unchanged():
    tests = (boundary.ROOT / "tests" / "test_core_01d_ci_offline_transport_boundary.py").read_text(encoding="utf-8")
    for name in ("test_native_kernel_socket_denial_is_independent_of_python_monkeypatches",
                 "test_child_cannot_remove_kernel_filter"):
        assert name in tests
    assert 'skipif(sys.platform != "linux"' in tests
    conftest = (boundary.ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "audit.authenticate_predecessors()" in conftest
    assert "audit.authenticate_inventory()" in conftest
    assert "CORE_01D_A2_LINUX_NATIVE_PROOF" in conftest
    import offline_linux as kernel
    assert all(kernel.evaluate(number) == kernel.DENY for number in kernel.DENIED_SYSCALLS)
    for number in kernel.SOCKET_CALLS:
        for family in (0, 2, 10, 16, 17, 40):
            assert kernel.evaluate(number, family=family) == kernel.DENY
        assert kernel.evaluate(number, family=1) == kernel.ALLOW
    assert kernel.evaluate(44, destination=0) == kernel.ALLOW
    assert kernel.evaluate(44, destination=1) == kernel.DENY
    receipt = boundary.read(boundary.RECEIPT_PATH)
    assert receipt["resolved_target_count"] == 3
    assert receipt["new_execution_authority_granted"] is False
    assert receipt["actions"] == boundary.ZERO_ACTIONS
    assert receipt["ci_boundary"]["generic_network_opt_out"] is False
    assert receipt["ci_boundary"]["outside_pytest_production_activation"] is False


# --- P. historical / current separation -------------------------------------
def test_historical_receipt_reconstruction_is_independent_of_the_current_generation(tmp_path, monkeypatch):
    directory = tmp_path / "generations"
    _seed_generations(directory)
    successor = boundary.build_successor_inventory(str(directory))
    _write_generation(directory, successor, "ci-offline-transport-boundary-source-inventory-v3.json")
    monkeypatch.setattr(boundary, "INVENTORY_DIRECTORY", str(directory))
    assert len(boundary.load_inventory_generations()) == 3
    assert boundary.authenticate_inventory()["generation"] == 3
    assert boundary.read(boundary.RECEIPT_PATH) == boundary.build_receipt()


# --- depth-1 (hosted CI) checkout ------------------------------------------
def test_depth1_checkout_proves_historical_evidence_from_pinned_identities(monkeypatch):
    """Hosted CI checks out fetch-depth 1: no ancestor object, no fetch allowed."""
    monkeypatch.setattr(boundary, "historical_objects_available", lambda *args, **kwargs: False)
    assert boundary.audit()["historical_proof_mode"] == "PINNED_IDENTITY_CHAIN_DEPTH1"
    assert boundary.authenticate_historical_v1()["canonical_sha256"] == V1_CANONICAL_SHA256
    assert boundary.authenticate_historical_activation_and_no_bypass() is True
    assert boundary.read(boundary.RECEIPT_PATH) == boundary.build_receipt()
    assert boundary.authenticate_inventory()["generation"] == 41
    # The fallback reads pinned A2 identities rather than current worktree
    # bytes: this bridge changed sitecustomize.py, so those differ from A2.
    pinned = boundary.historical_source("sitecustomize.py")["lf_source_sha256"]
    assert pinned == V1_SITECUSTOMIZE_SHA256
    assert pinned != boundary.source("sitecustomize.py")["lf_source_sha256"]

    original = Path.read_bytes
    def altered(path):
        if Path(path) == boundary.ROOT / "tests/conftest.py":
            return b"# rewritten after A2\n"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(AssertionError, match="pinned historical text is not the reviewed A2 source"):
        boundary.historical_text("tests/conftest.py")


# --- bridge receipt invariants ---------------------------------------------
def test_bridge_receipt_declares_additive_zero_reclassification_state():
    value = boundary.read(boundary.BRIDGE_RECEIPT_PATH)
    assert value["canonical_sha256"] == hashlib.sha256(boundary.canonical(
        {key: val for key, val in value.items() if key != "canonical_sha256"})).hexdigest()
    assert value["bridge_base_main_sha"] == boundary.BRIDGE_BASE_MAIN
    assert value["bridge_base_tree_sha"] == boundary.BRIDGE_BASE_TREE
    assert value["a2_reviewed_head"] == boundary.A2_REVIEWED_HEAD
    assert value["immutable_v1_inventory"]["canonical_sha256"] == V1_CANONICAL_SHA256
    assert value["immutable_a2_receipt"]["canonical_sha256"] == A2_RECEIPT_SHA256
    assert value["immutable_completion_v3"]["canonical_sha256"] == COMPLETION_V3_SHA256
    assert value["successor_inventory"]["path"] == boundary.INVENTORY_V2_PATH
    assert value["inventory_generation_before"] == 1 and value["inventory_generation_after"] == 2
    assert value["historical_v1_rewritten"] is False
    assert value["a2_receipt_rewritten"] is False
    assert value["completion_v3_rewritten"] is False
    assert value["current_transport_boundary_semantics_changed"] is False
    assert value["authority_rows_reclassified"] == 0
    assert value["global_unknown_before"] == value["global_unknown_after"] == 32
    assert value["checkpoint_e_status"] == "INCOMPLETE"
    assert value["p4_4_status"] == "INCOMPLETE"
    assert value["criteria_11_and_14"] is False
    assert value["workflow_diff_count"] == 0
    assert value["workflow_tree"] == boundary.WORKFLOW_TREE
    assert value["evolution_ledger"] == "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
    assert value["retirement_ledger"] == "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
    assert set(value["actions"].values()) == {0}
    assert value["source_review_counter_while_open"] == "4/5"
    assert value["source_review_counter_if_owner_merges"] == "5/5"
    assert value["mandatory_source_reread_after_merge"] is True
    assert value["terminal"] == EVOLUTION_TERMINAL


# --- chain discovery itself -------------------------------------------------
def test_generation_discovery_is_contiguous_and_not_lexicographic():
    generations = [generation for generation, _ in boundary.discover_inventory_generations()]
    assert generations == list(range(1, 42))
    assert _current_chain()[-1][0] == boundary.inventory_generation_path(41)
    assert boundary.read(boundary.INVENTORY_V2_PATH)["predecessor_inventory"]["generation"] == 1
    assert boundary.read(boundary.inventory_generation_path(3))["predecessor_inventory"] == {
        "path": boundary.INVENTORY_V2_PATH,
        "canonical_sha256": boundary.read(boundary.INVENTORY_V2_PATH)["canonical_sha256"],
        "generation": 2,
        "rewritten": False,
    }
    v4 = boundary.read(boundary.inventory_generation_path(4))
    assert v4["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(3),
        "canonical_sha256": boundary.read(boundary.inventory_generation_path(3))["canonical_sha256"],
        "generation": 3,
        "rewritten": False,
    }
    v5 = boundary.read(boundary.inventory_generation_path(5))
    assert v5["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(4),
        "canonical_sha256": v4["canonical_sha256"],
        "generation": 4,
        "rewritten": False,
    }
    v6 = boundary.read(boundary.inventory_generation_path(6))
    assert v6["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(5),
        "canonical_sha256": v5["canonical_sha256"],
        "generation": 5,
        "rewritten": False,
    }
    v7 = boundary.read(boundary.inventory_generation_path(7))
    assert v7["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(6),
        "canonical_sha256": v6["canonical_sha256"],
        "generation": 6,
        "rewritten": False,
    }
    v8 = boundary.read(boundary.inventory_generation_path(8))
    assert v8["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(7),
        "canonical_sha256": v7["canonical_sha256"],
        "generation": 7,
        "rewritten": False,
    }
    assert v8["canonical_sha256"] == "856129ba6eafb0281f10a16639f26fd477b2ba6a2fb00957ee79fa539539412d"
    v9 = boundary.read(boundary.inventory_generation_path(9))
    assert v9["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(8),
        "canonical_sha256": v8["canonical_sha256"],
        "generation": 8,
        "rewritten": False,
    }


def test_app01a_v10_binds_immutable_b7_v9_and_new_control_plane():
    v9 = boundary.read(boundary.inventory_generation_path(9))
    assert v9["canonical_sha256"] == "24c350c282ca07f1efd46828b777bfc8795e0dec689dc1f91b471da099492a96"
    v10 = boundary.read_generation(boundary.inventory_generation_path(10))
    assert v10["generation"] == 10
    assert v10["predecessor_inventory"]["canonical_sha256"] == v9["canonical_sha256"]


def test_app01a_v11_appends_data_root_contract_without_rewriting_v10():
    v10 = boundary.read_generation(boundary.inventory_generation_path(10))
    assert v10["canonical_sha256"] == "9b5ca4fc23fee7f5100f3ad9d9dafce4bd1fc580c77d546ff285284a2507f475"
    v11 = boundary.read_generation(boundary.inventory_generation_path(11))
    assert v11["generation"] == 11
    assert v11["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(10),
        "canonical_sha256": v10["canonical_sha256"],
        "generation": 10,
        "rewritten": False,
    }
    assert {"api/app_factory.py", "run_desktop.py", "runtime/resources.py",
            "tests/test_app_01a_local_shell.py"} <= {row["path"] for row in v11["source_identities"]}


def test_app01a_v12_preserves_v11_and_tracks_checkpoint_projection_adapter():
    v11 = boundary.read_generation(boundary.inventory_generation_path(11))
    assert v11["canonical_sha256"] == "b1c37109487e49b305b2d65e5a2c85c95f917e2538da12a910998503abffa453"
    v12 = boundary.read_generation(boundary.inventory_generation_path(12))
    assert v12["generation"] == 12
    assert v12["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(11),
        "canonical_sha256": v11["canonical_sha256"],
        "generation": 11,
        "rewritten": False,
    }


def test_app01a_v13_preserves_v12_and_authenticates_prior_inventory_projection():
    v12 = boundary.read_generation(boundary.inventory_generation_path(12))
    assert v12["canonical_sha256"] == "3bfd2b3870b2eb946b9493a737cf7b4d658860d8a68d288be5ba3638a4f20d3c"
    v13 = boundary.read_generation(boundary.inventory_generation_path(13))
    assert v13["generation"] == 13
    assert v13["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(12),
        "canonical_sha256": v12["canonical_sha256"],
        "generation": 12,
        "rewritten": False,
    }


def test_app01a_v14_preserves_v13():
    v13 = boundary.read_generation(boundary.inventory_generation_path(13))
    assert v13["canonical_sha256"] == "b37925a19c28f375a01fb270b97de14616a2b13585e52d173d37ab521639d25f"
    v14 = boundary.read_generation(boundary.inventory_generation_path(14))
    assert v14["generation"] == 14
    assert v14["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(13),
        "canonical_sha256": v13["canonical_sha256"],
        "generation": 13,
        "rewritten": False,
    }


def test_app01a_v15_preserves_v14():
    v14 = boundary.read_generation(boundary.inventory_generation_path(14))
    assert v14["canonical_sha256"] == "fed545cba087515a0ac4213118a3a4da72d6ad95138f3702c1dcc4301770216f"
    v15 = boundary.read_generation(boundary.inventory_generation_path(15))
    assert v15["generation"] == 15
    assert v15["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(14),
        "canonical_sha256": v14["canonical_sha256"],
        "generation": 14,
        "rewritten": False,
    }


def test_app01a_v16_preserves_v15():
    v15 = boundary.read_generation(boundary.inventory_generation_path(15))
    assert v15["canonical_sha256"] == "25a5edf0aac9b67b3527e14e36d428cb975263d112a5f8f0d839ab7f833ad0d4"
    v16 = boundary.read_generation(boundary.inventory_generation_path(16))
    assert v16["generation"] == 16
    assert v16["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(15),
        "canonical_sha256": v15["canonical_sha256"],
        "generation": 15,
        "rewritten": False,
    }


def test_app01a_v17_preserves_v16():
    v16 = boundary.read_generation(boundary.inventory_generation_path(16))
    assert v16["canonical_sha256"] == "9a0c0295d7dd211631ea64b05094e4ca7215466a48fa30db70cd2a440b3711a2"
    v17 = boundary.read_generation(boundary.inventory_generation_path(17))
    assert v17["generation"] == 17
    assert v17["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(16),
        "canonical_sha256": v16["canonical_sha256"],
        "generation": 16,
        "rewritten": False,
    }


def test_app01a_v18_preserves_v17_and_binds_current_receipt_inventory():
    v17 = boundary.read_generation(boundary.inventory_generation_path(17))
    assert v17["canonical_sha256"] == "f1007c2ac4e149298027c010569ba1b802c1b71cd59f5bdbd4956f1483ee9c68"
    v18 = boundary.read_generation(boundary.inventory_generation_path(18))
    assert v18["generation"] == 18
    assert v18["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(17),
        "canonical_sha256": v17["canonical_sha256"],
        "generation": 17,
        "rewritten": False,
    }
    latest = boundary.authenticate_inventory()
    assert latest["generation"] == 41
    assert latest["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(40),
        "canonical_sha256": "64bbe0f42d0874442a39d9e35f77a100d5da17ecbc1538b25c5e4a38405e56bb",
        "generation": 40,
        "rewritten": False,
    }
