"""Exact, inert Pass-A source provenance for the E3 V300 continuation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import socket
import stat
from types import SimpleNamespace

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as a2


BASE_MAIN = "84d452f354dd09714db541f28488058b61e72033"
V2_CANONICAL_SHA256 = "c7b12447b7f671b2ece76d1207b404cd4555cc45d2e2ec88451682d6e0b4f14e"
V284_CANONICAL_SHA256 = "c2f31e8268eadb282465ee85132cacc6eff572de98dea6e811d42b0e74cc7a7a"
V299_CANONICAL_SHA256 = "81c47aa1bbcd55604908257fe468e5f9066d3b8cf66787dd18308dccd2c124e4"

EXPECTED = {
    "scripts/audit_p4_4e_current_fotmob_ingest_issuer.py": (
        "original-audit-p4-4e-current-fotmob-ingest-issuer.py.txt",
        "fc772ced8b8c1d0d433179fcc04765ed1b273438",
        "8be7e40aad917dcd52e79473224aff520aba9c5d3072bdd18ee52d2e1b00d0ce",
        17207,
        "0012001df95ca82853d3cd80c5dd0cd11830eec4",
        "1d07e6be402462a2cf09309111c511d80db0f35764601e77641b10ba96ac943f",
    ),
    "scripts/audit_p4_4f_current_fotmob_exact_lane_caller_migration.py": (
        "original-audit-p4-4f-current-fotmob-exact-lane-caller-migration.py.txt",
        "74dc0f87592bf956ab649070d9059075e2645989",
        "a015a817253878cc192d0ca26b99bb393ae6354e20cfa4ab418ee69bcd9d64cf",
        30193,
        "11836a56e930b71236567d84507e0f0cef51fb6b",
        "2196516b5b929d237676548de4f4fd5ca49ebcbd7d229ccb93f45c75fc347fb6",
    ),
    "scripts/audit_p4_4g_current_fotmob_canonical_only_workflow.py": (
        "original-audit-p4-4g-current-fotmob-canonical-only-workflow.py.txt",
        "0884f6837db4c27745f67601574a2a9f20e97df2",
        "94455db594506e20b23668fbd5eab187ed4d47836a82de930090ed1fd5f782f5",
        36776,
        "a49a34706038b5ed94180316fd5d0b32a2bb979d",
        "d3b7fad2ac90531b79e591f0d939a20efd4febcba9a85a54f012f05b49231542",
    ),
    "scripts/audit_p4_4h_current_shadow_canonical_run_migration_review.py": (
        "original-audit-p4-4h-current-shadow-canonical-run-migration-review.py.txt",
        "ab0f2261e0a30a165b5e48ee9643feda8e4273ab",
        "d1b9c361444f31f157dbbf011827ccda5dad8bed19f73daca32fd32c3cedddae",
        42050,
        "4ad358f9d808d7068a1dabea244912ee0c84f97f",
        "404b2b49519ecd3f5f9a2357f2d7fe8fc58fc899422ee314db83895f23865621",
    ),
    "scripts/audit_port_01_source_identity_parity.py": (
        "original-audit-port-01-source-identity-parity.py.txt",
        "ef19eedecff06268f5c2c2c1b6372d240ff39df3",
        "a9464ba8e7110a2ad6a93bffcdabe1dd8fc64ac544751edee726d67e7832d42b",
        24728,
        "da065883ddf343298e0968f04ca7ee5a28146249",
        "acad737c52226ff749a17420712fefcb67fb67747bc58cd531d06e66ba75bf8c",
    ),
    "scripts/execute_current_shadow_daily.py": (
        "original-execute-current-shadow-daily.py.txt",
        "c2ea5eb021fd7ce72bfd5447458468f75a28a101",
        "014882f29144bfa6e84437da5fb742f2a83cb253082910b834a2e24c1130cc4d",
        12262,
        "0bb82c9beff1d6e47bf010aa753973253eeb4ec4",
        "692ca308d08242cdb80c05f299fe10c107535d3c75c854d5c747e0bc4dcec0fe",
    ),
    "tests/test_issue_current_fotmob_reviewed_source.py": (
        "original-test-issue-current-fotmob-reviewed-source.py.txt",
        "4fa54db086b2689b1dd7a60ae12c64f50c8eec75",
        "9dae4210bf8e326ca87f8caa737852a07f8ca5d53e717568430473451df405c6",
        13713,
        "8b02c6c298ee598979d8d12362bd7b6eaf81880b",
        "d84b6385ecab8fdeda7cf4e4acedbafb0ce18a0e97d372ace8e9abc7c4ff78f3",
    ),
    "tests/test_p4_4h_current_shadow_canonical_run_migration_review.py": (
        "original-test-p4-4h-current-shadow-canonical-run-migration-review.py.txt",
        "204a756c040bc00c36fd676449f970537209e0cf",
        "3a57ac069fee56b2af03438050d92bd02704baa5c175e1cb4dab5a113fbb952c",
        28883,
        "09b3cc311e73d1c93c9de0e59fea9491649edcd2",
        "9b1aeab3b86d1896c845e180b7e94286712afc3f127034a6293241e26ae82a9f",
    ),
}


def _normalized(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def test_v284_public_matrix_stays_exact_and_v300_requires_its_own_generation():
    assert a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS == a2.E3_CROSS_CONTRACT_V284_SOURCE_FORWARD_PATHS
    assert len(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS) == 11
    assert set(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS) == set(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS)
    assert set(a2.E3_PASS_A_SOURCE_FORWARD_PATHS) == set(EXPECTED)
    assert len(a2.E3_PASS_A_SOURCE_FORWARD_PATHS) == 8
    assert set(a2.E3_PASS_A_SOURCE_FORWARD_PATHS).isdisjoint(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS)
    assert all(path.startswith(a2.E3_CROSS_CONTRACT_FIXTURE_DIRECTORY + "/")
               for path in a2.E3_CROSS_CONTRACT_FIXTURE_PATHS)
    assert set(a2.E3_CROSS_CONTRACT_FIXTURE_PATHS).isdisjoint(
        a2.E3_PASS_A_SOURCE_FORWARD_FIXTURE_PATHS
    )

    for path in a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS:
        assert a2.resolve_historical_source_transition(
            path, expected_generation=a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        ) is a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS[path]
    for path in a2.E3_PASS_A_SOURCE_FORWARD_PATHS:
        assert a2.resolve_historical_source_transition(
            path, expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        ) is a2.E3_PASS_A_SOURCE_FORWARD_TRANSITIONS[path]

    with pytest.raises(AssertionError):
        a2.resolve_historical_source_transition(
            next(iter(a2.E3_PASS_A_SOURCE_FORWARD_PATHS)),
            expected_generation=a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )
    with pytest.raises(AssertionError):
        a2.resolve_historical_source_transition(
            next(iter(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS)),
            expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )


@pytest.mark.parametrize("path,generation", [
    ("scripts/unreviewed_historical_source.py", 300),
    ("scripts/audit_p4_4e_current_fotmob_ingest_issuer.py", 301),
    ("scripts/audit_p4_4e_current_fotmob_ingest_issuer.py", True),
])
def test_transition_resolver_rejects_unknown_or_implicit_generation(path, generation):
    with pytest.raises(AssertionError):
        a2.resolve_historical_source_transition(path, expected_generation=generation)


def test_v300_eight_fixtures_bind_base_v2_v299_and_exact_current_successors(monkeypatch):
    def no_network(*_args, **_kwargs):
        raise AssertionError("historical source projection attempted network transport")

    monkeypatch.setattr(socket, "socket", no_network)
    chain = a2.load_inventory_generations()
    resolved = a2.read_authenticated_pass_a_source_predecessors()
    assert set(resolved) == set(EXPECTED)
    assert chain[1][0] == a2.inventory_generation_path(2)
    assert chain[1][1]["canonical_sha256"] == V2_CANONICAL_SHA256
    assert chain[283][1]["canonical_sha256"] == V284_CANONICAL_SHA256
    assert chain[298][1]["canonical_sha256"] == V299_CANONICAL_SHA256

    v300 = chain[299][1]
    authorization = v300["e3_pass_a_source_predecessor_authorization"]
    assert authorization["authorization_generation"] == 300
    assert authorization["authority_granted"] is False
    assert authorization["historical_bytes_changed"] is False
    assert authorization["source_predecessor_inventory"]["generation"] == 2
    assert authorization["source_predecessor_inventory"]["canonical_sha256"] == V2_CANONICAL_SHA256
    assert "e3_pass_a_source_predecessor_authorization" not in a2.current_corpus_fields(
        generation=299, chain=chain,
    )
    assert authorization["authorization_predecessor"] == {
        "path": a2.inventory_generation_path(299),
        "canonical_sha256": V299_CANONICAL_SHA256,
        "generation": 299,
        "rewritten": False,
    }
    authorization_rows = {row["path"]: row for row in authorization["source_identities"]}
    assert set(authorization_rows) == set(EXPECTED)

    v2_rows = {row["path"]: row["lf_source_sha256"]
               for row in chain[1][1]["source_identities"]}
    latest_rows = {row["path"]: row["lf_source_sha256"]
                   for row in chain[-1][1]["source_identities"]}
    for path, (fixture_name, predecessor_blob, predecessor_sha, size, successor_blob, successor_sha) in EXPECTED.items():
        fixture_path = a2.E3_PASS_A_SOURCE_FORWARD_FIXTURE_DIRECTORY + "/" + fixture_name
        transition = a2.resolve_historical_source_transition(
            path, expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )
        raw = resolved[path]
        assert transition["predecessor_fixture"] == fixture_path
        assert transition["predecessor_git_mode"] == "100644"
        assert transition["predecessor_byte_size"] == size
        assert transition["predecessor_git_blob_sha1"] == predecessor_blob
        assert transition["predecessor_lf_source_sha256"] == predecessor_sha
        assert transition["successor_git_mode"] == "100644"
        assert transition["successor_git_blob_sha1"] == successor_blob
        assert transition["successor_lf_source_sha256"] == successor_sha
        assert len(raw) == size
        assert _git_blob(raw) == predecessor_blob
        assert hashlib.sha256(_normalized(raw)).hexdigest() == predecessor_sha
        assert (a2.ROOT / fixture_path).read_bytes() == raw
        assert v2_rows[path] == predecessor_sha

        auth_row = authorization_rows[path]
        assert auth_row["original_source_base_main_sha"] == BASE_MAIN
        assert auth_row["predecessor"] == {
            "fixture_path": fixture_path,
            "git_mode": "100644",
            "git_blob_sha1": predecessor_blob,
            "lf_source_sha256": predecessor_sha,
            "byte_size": size,
        }
        assert auth_row["successor"] == {
            "git_mode": "100644",
            "git_blob_sha1": successor_blob,
            "lf_source_sha256": successor_sha,
        }

        current, current_identity = a2.read_tracked_head_blob(a2.ROOT, path)
        assert current_identity.git_blob_sha1 == successor_blob
        assert hashlib.sha256(_normalized(current)).hexdigest() == successor_sha
        assert latest_rows[path] == successor_sha
        tree_entry = a2.git("ls-tree", "-z", "HEAD", "--", path)
        metadata, tree_path = tree_entry.rstrip(b"\0").split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split(" ")
        assert (tree_path.decode("utf-8"), mode, kind, blob) == (path, "100644", "blob", successor_blob)

        if a2.historical_objects_available(BASE_MAIN):
            original_tree = a2.git("ls-tree", "-z", BASE_MAIN, "--", path)
            original_metadata, original_path = original_tree.rstrip(b"\0").split(b"\t", 1)
            original_mode, original_kind, original_blob = original_metadata.decode("ascii").split(" ")
            original_raw = a2.git("cat-file", "blob", original_blob)
            assert (original_path.decode("utf-8"), original_mode, original_kind, original_blob) == (
                path, "100644", "blob", predecessor_blob,
            )
            assert original_raw == raw


def test_v300_rejects_stale_latest_generation_and_tampered_v299_parent(monkeypatch):
    original = a2.load_inventory_generations

    def stale_latest():
        return original()[:-1]

    monkeypatch.setattr(a2, "load_inventory_generations", stale_latest)
    with pytest.raises(AssertionError, match="V300/V301 authorization chain"):
        a2.read_authenticated_pass_a_source_predecessor(next(iter(EXPECTED)))


@pytest.mark.parametrize("mutation", [
    "v299_hash", "v300_parent", "v300_authorization", "v301_successor_extension",
])
def test_v300_rejects_mutated_authorization_ancestry(monkeypatch, mutation):
    original = a2.load_inventory_generations

    def altered_chain():
        chain = original()
        v299_path, v299 = chain[298]
        v300_path, v300 = chain[299]
        v301_path, v301 = chain[300]
        v299 = deepcopy(v299)
        v300 = deepcopy(v300)
        v301 = deepcopy(v301)
        if mutation == "v299_hash":
            v299["canonical_sha256"] = "0" * 64
            chain[298] = (v299_path, v299)
        elif mutation == "v300_parent":
            v300["predecessor_inventory"]["canonical_sha256"] = "0" * 64
            chain[299] = (v300_path, v300)
        elif mutation == "v300_authorization":
            v300["e3_pass_a_source_predecessor_authorization"]["authority_granted"] = True
            chain[299] = (v300_path, v300)
        else:
            v301["e3_cross_contract_source_forward_successor_extensions"][1]["successor"][
                "lf_source_sha256"
            ] = "0" * 64
            chain[300] = (v301_path, v301)
        return chain

    monkeypatch.setattr(a2, "load_inventory_generations", altered_chain)
    with pytest.raises(AssertionError):
        a2.read_authenticated_pass_a_source_predecessor(next(iter(EXPECTED)))


def test_v300_rejects_unapproved_overlap_or_duplicate_fixture_binding(monkeypatch):
    v284_path = next(iter(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS))
    monkeypatch.setattr(a2, "E3_PASS_A_SOURCE_FORWARD_PATHS",
                        a2.E3_PASS_A_SOURCE_FORWARD_PATHS | {v284_path})
    with pytest.raises(AssertionError):
        a2.resolve_historical_source_transition(
            v284_path, expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )


def test_v300_rejects_fixture_path_reassignment(monkeypatch):
    path = next(iter(EXPECTED))
    transitions = deepcopy(a2.E3_PASS_A_SOURCE_FORWARD_TRANSITIONS)
    other_path = next(candidate for candidate in EXPECTED if candidate != path)
    transitions[path]["predecessor_fixture"] = transitions[other_path]["predecessor_fixture"]
    monkeypatch.setattr(a2, "E3_PASS_A_SOURCE_FORWARD_TRANSITIONS", transitions)
    with pytest.raises(AssertionError, match="duplicate or unreviewed path"):
        a2.resolve_historical_source_transition(
            path, expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )


def test_v300_rejects_extra_fixture_directory_entry(monkeypatch):
    class ExtraFixtureDirectory:
        def iterdir(self):
            return [Path("unexpected.py.txt")]

    monkeypatch.setattr(a2, "_e3_directory_path", lambda *_args, **_kwargs: ExtraFixtureDirectory())
    with pytest.raises(AssertionError, match="missing, extra, or renamed evidence"):
        a2.read_authenticated_pass_a_source_predecessor(next(iter(EXPECTED)))


def test_v300_rejects_wrong_repository_root(monkeypatch, tmp_path):
    monkeypatch.setattr(a2, "ROOT", tmp_path)
    with pytest.raises((AssertionError, OSError)):
        a2.read_authenticated_pass_a_source_predecessor(next(iter(EXPECTED)))


def test_v300_rejects_fixture_symlink_and_byte_drift(monkeypatch):
    path = next(iter(EXPECTED))
    transition = a2.resolve_historical_source_transition(
        path, expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    fixture = a2.ROOT / transition["predecessor_fixture"]
    original_lstat = Path.lstat

    def symlink_lstat(candidate):
        if candidate == fixture:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_nlink=1, st_file_attributes=0)
        return original_lstat(candidate)

    monkeypatch.setattr(Path, "lstat", symlink_lstat)
    with pytest.raises(AssertionError, match="symlink or junction"):
        a2.read_authenticated_pass_a_source_predecessor(path)

    monkeypatch.setattr(Path, "lstat", original_lstat)
    original_read_bytes = Path.read_bytes

    def altered_fixture(candidate):
        raw = original_read_bytes(candidate)
        return raw + b"\n" if candidate == fixture else raw

    monkeypatch.setattr(Path, "read_bytes", altered_fixture)
    with pytest.raises(AssertionError, match="worktree bytes differ|fixture identity|size mismatch"):
        a2.read_authenticated_pass_a_source_predecessor(path)


def test_v300_rejects_current_executable_worktree_drift(monkeypatch):
    path = next(iter(EXPECTED))
    current_path = a2.ROOT / path
    original_read_bytes = Path.read_bytes

    def altered_current(candidate):
        raw = original_read_bytes(candidate)
        return raw + b"\n" if candidate == current_path else raw

    monkeypatch.setattr(Path, "read_bytes", altered_current)
    with pytest.raises(AssertionError, match="worktree bytes differ|worktree"):
        a2.read_authenticated_pass_a_source_predecessor(path)


def test_v300_rejects_fixture_missing_from_head(monkeypatch):
    path = next(iter(EXPECTED))
    transition = a2.resolve_historical_source_transition(
        path, expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
    )
    fixture_path = transition["predecessor_fixture"]
    original_git = a2.git

    def missing_fixture(*args, **kwargs):
        if args[:3] == ("ls-tree", "-z", "HEAD") and args[-1] == fixture_path:
            return b""
        return original_git(*args, **kwargs)

    monkeypatch.setattr(a2, "git", missing_fixture)
    with pytest.raises(AssertionError, match="path is not committed"):
        a2.read_authenticated_pass_a_source_predecessor(path)


def test_v300_rejects_forged_fixture_and_successor_identities(monkeypatch):
    path = next(iter(EXPECTED))
    state = a2._authenticated_pass_a_source_inventory_state()
    monkeypatch.setattr(a2, "_authenticated_pass_a_source_inventory_state", lambda: state)
    original = a2.E3_PASS_A_SOURCE_FORWARD_TRANSITIONS
    altered = deepcopy(original)
    for field, bad_value, message in (
        ("predecessor_git_blob_sha1", "0" * 40, "predecessor fixture identity mismatch"),
        ("predecessor_lf_source_sha256", "0" * 64, "predecessor fixture identity mismatch"),
        ("predecessor_byte_size", altered[path]["predecessor_byte_size"] + 1, "predecessor fixture size mismatch"),
        ("predecessor_git_mode", "100755", "predecessor mode or size is malformed"),
        ("successor_git_blob_sha1", "0" * 40, "current successor identity mismatch"),
        ("successor_lf_source_sha256", "0" * 64, "current successor identity mismatch"),
        ("successor_git_mode", "100755", "predecessor mode or size is malformed"),
    ):
        candidate = deepcopy(original)
        candidate[path][field] = bad_value
        monkeypatch.setattr(a2, "E3_PASS_A_SOURCE_FORWARD_TRANSITIONS", candidate)
        with pytest.raises(AssertionError, match=message):
            a2.read_authenticated_pass_a_source_predecessor(path)


def test_v300_environment_flags_cannot_authorize_a_wrong_generation(monkeypatch):
    monkeypatch.setenv("ATHENA_A2_ALLOW_HISTORICAL_SOURCE_BYPASS", "1")
    monkeypatch.setenv("ATHENA_TEST_MODE", "1")
    with pytest.raises(AssertionError):
        a2.resolve_historical_source_transition(
            "scripts/unreviewed_historical_source.py",
            expected_generation=a2.E3_PASS_A_SOURCE_FORWARD_AUTHORIZATION_GENERATION,
        )
