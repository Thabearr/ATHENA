"""Adversarial offline tests for B4's nine current SportyBet trigger surfaces."""
from __future__ import annotations

import hashlib
import stat
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.source_identity import SourceIdentityError
from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4


@pytest.fixture(scope="module")
def receipt():
    return b4.boundary.read(b4.RECEIPT_PATH)


def _row(receipt, path_suffix: str, event: str):
    return next(row for row in receipt["review_rows"]
                if row["identity"]["workflow_path"].endswith(path_suffix)
                and row["identity"]["trigger_kind"] == event)


def test_source_identity_tolerates_checkout_eol_conversion_without_weakening_git_blob_pin(monkeypatch):
    target = b4.TARGETS[0][0]
    original = Path.read_bytes

    def crlf_view(path):
        raw = original(path)
        if Path(path) == b4.ROOT / target:
            return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return raw

    monkeypatch.setattr(Path, "read_bytes", crlf_view)
    observed = b4._identity(target)
    expected_blob, expected_sha = b4.SOURCE_PINS[target]
    assert observed["git_blob_sha1"] == expected_blob
    assert observed["normalized_source_sha256"] == expected_sha


def test_historical_workflow_fixture_tolerates_checkout_eol_conversion(monkeypatch):
    path = b4.TARGETS[0][0]
    fixture = b4.ROOT / b4.B4_WORKFLOW_PREDECESSORS[path]
    original = Path.read_bytes

    def crlf_view(candidate):
        raw = original(candidate)
        if Path(candidate) == fixture:
            return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return raw

    monkeypatch.setattr(Path, "read_bytes", crlf_view)
    assert b4._historical_b4_workflow_bytes(path) == original(fixture)


def test_exact_nine_surface_scope_and_completion_v6_inheritance(receipt):
    keys = [(row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
            for row in receipt["review_rows"]]
    assert len(keys) == len(set(keys)) == 9
    assert set(keys) == set(b4.TARGETS)
    assert all(path != ".github/workflows/pr258-sportybet-live-transport-proof.yml"
               or event == "workflow_dispatch" for path, event in keys)
    assert receipt["scope"] == {
        "inherited_unresolved_surface_count": 16,
        "target_surface_count": 9,
        "resolved_target_count": 9,
        "partial_target_count": 0,
        "global_unresolved_before": 16,
        "global_unresolved_after": 7,
        "target_keys": [[path, event] for path, event in b4.TARGETS],
    }


@pytest.mark.parametrize("path,event", b4.TARGETS)
def test_each_target_has_source_identity_contract_reachability_and_authority(receipt, path, event):
    row = next(r for r in receipt["review_rows"]
               if (r["identity"]["workflow_path"], r["identity"]["trigger_kind"]) == (path, event))
    assert row["identity"]["git_blob_sha1"] == b4.SOURCE_PINS[path][0]
    assert row["identity"]["normalized_source_sha256"] == b4.SOURCE_PINS[path][1]
    assert row["reachability"]["physical_trigger_runtime_authority"] == b4.TARGET_REACHABILITY[(path, event)]
    assert row["reachability"]["repository_caller_state"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN"
    assert row["review"] == {"status": "RESOLVED", "blocker": None}
    assert row["authority"]["sportybet_login_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_cookie_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_wallet_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_stake_submission_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_wager_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["github_actions_artifact_write_authority"] == "RUN_SCOPED_ARTIFACT_UPLOAD"
    assert row["authority"]["github_branch_or_repository_write_authority"] == "NONE_CONTENTS_READ_ONLY_TOKEN"
    assert row["support_disposition"]["product_supported_current_operation_dependency"] == "NONE_RETAINED_RESEARCH_ONLY"
    assert row["support_disposition"]["physical_trigger_runtime_authority"] == b4.TARGET_REACHABILITY[(path, event)]


def test_path_filtered_pr_surfaces_remain_conditionally_reachable_and_manual_surfaces_remain_manual(receipt):
    for suffix in ("create-saturday-2026-08-22-sportybet-direct-20-code.yml",
                   "probe-sportybet-direct-20-markets.yml", "prove-sportybet-direct-share-code.yml"):
        row = _row(receipt, suffix, "pull_request")
        assert row["reachability"]["physical_trigger_runtime_authority"] == "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED"
        assert row["trigger_contract"]["branch_filters"] == ["main"]
        assert len(row["trigger_contract"]["path_filters"]) == 4
    for path, event in b4.TARGETS:
        if event == "workflow_dispatch":
            row = next(r for r in receipt["review_rows"] if r["identity"]["workflow_path"] == path and r["identity"]["trigger_kind"] == event)
            assert row["reachability"]["physical_trigger_runtime_authority"] == "MANUALLY_REACHABLE_WORKFLOW_DISPATCH"
            assert row["reachability"]["manual_control_plane_state"] == "DECLARED_AND_MANUALLY_REACHABLE"
    prb = _row(receipt, "prb-sportybet-semantic-registry-proof.yml", "pull_request")
    assert prb["trigger_contract"]["head_ref_guard"] == "github.head_ref == 'feat/prb-sportybet-semantic-registry'"
    assert prb["reachability"]["physical_trigger_runtime_authority"] == "CONDITIONALLY_REACHABLE_PULL_REQUEST_EXACT_HEAD_REF"
    assert "recreatable" in prb["reachability"]["reason"]


def test_direct_share_post_is_mutation_not_wager_and_probe_is_get_only(receipt):
    create = _row(receipt, "create-saturday-2026-08-22-sportybet-direct-20-code.yml", "workflow_dispatch")["authority"]
    one_leg = _row(receipt, "prove-sportybet-direct-share-code.yml", "pull_request")["authority"]
    for authority in (create, one_leg):
        assert authority["sportybet_share_code_create_authority"] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
        assert authority["sportybet_share_code_reload_authority"] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
        assert authority["sportybet_wager_authority"] == "NO_SOURCE_PATH"
    probe = _row(receipt, "probe-sportybet-direct-20-markets.yml", "workflow_dispatch")["authority"]
    assert probe["sportybet_market_read_authority"] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
    assert probe["sportybet_share_code_create_authority"] == "NO_SOURCE_PATH"
    assert probe["sportybet_share_code_reload_authority"] == "NO_SOURCE_PATH"
    assert probe["sportybet_wager_authority"] == "NO_SOURCE_PATH"


def test_pr258_and_prb_keep_distinct_read_and_mutation_authority(receipt):
    pr258 = _row(receipt, "pr258-sportybet-live-transport-proof.yml", "workflow_dispatch")
    assert pr258["reachability"]["sibling_trigger_state"] == "PR258_PULL_REQUEST_RESOLVED_BY_B1_OUT_OF_SCOPE"
    for field in ("sportybet_upcoming_discovery_read_authority", "sportybet_event_detail_read_authority",
                  "sportybet_share_code_create_authority", "sportybet_share_code_reload_authority"):
        assert pr258["authority"][field] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
    for field in ("model_authority", "production_selection_authority", "fixture_reconciliation_authority",
                  "sportybet_wager_authority"):
        assert pr258["authority"][field] == "NO_SOURCE_PATH"
    for event in ("pull_request", "workflow_dispatch"):
        prb = _row(receipt, "prb-sportybet-semantic-registry-proof.yml", event)["authority"]
        assert prb["sportybet_upcoming_discovery_read_authority"] == "BOUNDED_ANONYMOUS_DISCOVERY_GET"
        assert prb["sportybet_event_detail_read_authority"] == "BOUNDED_ANONYMOUS_EVENT_DETAIL_GET"
        assert prb["sportybet_share_code_create_authority"] == "NO_SOURCE_PATH"
        assert prb["sportybet_share_code_reload_authority"] == "NO_SOURCE_PATH"
        assert "GITHUB_GIT_LS_REMOTE_READ_ON_MANUAL_BASE_FALLBACK" in prb["network_authority_summary"]
        assert prb["github_branch_or_repository_write_authority"] == "NONE_CONTENTS_READ_ONLY_TOKEN"


def test_history_is_only_historical_metadata_and_not_current_transport_proof(receipt):
    assert len(receipt["source_inventory"]["canonical_sha256"]) == 64
    assert receipt["actions"] == b4.ZERO_ACTIONS
    for row in receipt["review_rows"]:
        observation = row["historical_run_metadata"]
        assert observation["read_only"] is True
        assert observation["interpretation"] == "HISTORICAL_RUN_METADATA_ONLY_NOT_CURRENT_AUTHORITY_OR_CURRENT_PROVIDER_PROOF"
        assert row["reachability"]["historical_actions_rerun_residual"] == "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"
    scan = b4.boundary.read(b4.SOURCE_INVENTORY_PATH)["repository_caller_scan"]
    assert scan["result"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN"
    assert scan["external_manual_dispatch_authority"] == "PRESERVED_NOT_ERASED_BY_NO_REPOSITORY_CALLER"


@pytest.mark.parametrize("mutation", [
    lambda r: r["review_rows"].pop(),
    lambda r: r["review_rows"].append(deepcopy(r["review_rows"][0])),
    lambda r: r["review_rows"][0]["reachability"].update(physical_trigger_runtime_authority="SPENT"),
    lambda r: r["review_rows"][1]["authority"].update(sportybet_wager_authority="YES"),
    lambda r: r["review_rows"][0]["authority"].update(sportybet_share_code_create_authority="NO_SOURCE_PATH"),
    lambda r: r["review_rows"][5]["authority"].update(sportybet_share_code_create_authority="YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"),
    lambda r: r["review_rows"][3]["authority"].update(sportybet_share_code_create_authority="YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"),
    lambda r: r.update(checkpoint_e_status="COMPLETE"),
])
def test_b4_receipt_mutations_are_rejected(receipt, mutation):
    mutant = deepcopy(receipt)
    mutation(mutant)
    with pytest.raises(AssertionError):
        b4.validate_receipt(mutant)


def test_source_inventory_mutations_and_workflow_source_drift_fail_closed():
    inventory = b4.boundary.read(b4.SOURCE_INVENTORY_PATH)
    mutant = deepcopy(inventory)
    mutant["target_keys"].pop()
    with pytest.raises(AssertionError):
        b4.validate_source_inventory(mutant)
    assert b4.validate_source_inventory(inventory)["source_count"] == len(b4.SOURCE_PINS)


def test_e3_event_detail_forward_source_preserves_exact_b4_identity():
    path = "domain/sportybet_live_event_quote_evidence.py"
    result = b4.audit()
    expected_blob, expected_sha = b4.SOURCE_PINS[path]
    inventory = b4.boundary.read(b4.SOURCE_INVENTORY_PATH)
    source = next(row for row in inventory["sources"] if row["path"] == path)
    assert source == {
        "path": path,
        "git_blob_sha1": expected_blob,
        "normalized_source_sha256": expected_sha,
        "role": b4.ROLES[path],
        "discovery_edges": b4.EDGE_MAP.get(path, []),
    }
    assert inventory["canonical_sha256"] == "a66f9917d3b50e4422237369304659b58c6fdec81daac614f8e83088fcf87d66"
    assert result["source_inventory_sha256"] == inventory["canonical_sha256"]
    assert result["receipt_sha256"] == "9b630ef065318eb83333ce86ab7b121a790d44c8ce6ad5c0f4f5bac527905e3c"
    transition = b4.boundary.SOURCE_FORWARD_TRANSITIONS[path]
    assert transition["predecessor_git_blob_sha1"] == expected_blob
    assert transition["predecessor_lf_source_sha256"] == expected_sha
    assert transition["a2_generation"] == 274
    assert transition["a2_authorization_sha256"] == \
        "0655816adeb22f4ec5dcdb1012ee15af5c98c08c95c0b98286d451216e5377fc"


_E3_B6_FORWARD_SOURCES = {
    "domain/current_fotmob_latest_durable_fresh_history.py": {
        "predecessor_git_blob_sha1": "4e5695711078acb06fba537f3f69ca1e2c9df470",
        "predecessor_lf_source_sha256": "2f3eb3473acdcab1bf10a0e6431708aa8225b2b2f279bf10405e669f453386ab",
        "predecessor_byte_size": 43798,
        "successor_git_blob_sha1": "8efc9d0f70e651be74bcf528119f2fc462bd7c50",
        "successor_lf_source_sha256": "bb89e01104ccf6357cba9f3e935a6ed3d32a2ab09d0a1064dd63a6221c9b9a09",
        "predecessor_fixture": "tests/fixtures/core_01d/e3_b6_three_source_forward/"
        "original-current-fotmob-latest-durable-fresh-history.py.txt",
        "reason": "E3 RUN-02A durable cancellation/operation-authorization boundary for "
        "current FotMob latest durable fresh-history provider operations",
    },
    "domain/current_shadow_sportybet_pc_upcoming_discovery.py": {
        "predecessor_git_blob_sha1": "fa2069a2ea1201a93a84b5ce3856f9d9574dea71",
        "predecessor_lf_source_sha256": "0d4d1af14a47e935bf2669c8abf6dbf6409e9f8d72f4070c3bb0b8abc7eec1a3",
        "predecessor_byte_size": 45046,
        "successor_git_blob_sha1": "2a4030b3a330637dcbfe0e688da8054c1158d157",
        "successor_lf_source_sha256": "d3b2db5331883b96b8af4a2a5520461fad774cac1d246659413527d13ba788af",
        "predecessor_fixture": "tests/fixtures/core_01d/e3_b6_three_source_forward/"
        "original-current-shadow-sportybet-pc-upcoming-discovery.py.txt",
        "reason": "E3 RUN-02A durable cancellation/operation-authorization boundary for "
        "current Shadow SportyBet PC upcoming discovery",
    },
    "scripts/issue_current_fotmob_reviewed_source.py": {
        "predecessor_git_blob_sha1": "b50689971ee20cb6800145317a0e9fcb3486f40f",
        "predecessor_lf_source_sha256": "449e83af1a8e25bf5b054b88682b8559363196ca2d6e1dad87c742949b8d0484",
        "predecessor_byte_size": 27513,
        "successor_git_blob_sha1": "432f72290bd7f10e61e13173bd89e0eed8b96aea",
        "successor_lf_source_sha256": "9dabb9e9844000509028d9933b3ee54c290d7df3de2f35b0046f8a5a0b188cfd",
        "predecessor_fixture": "tests/fixtures/core_01d/e3_b6_three_source_forward/"
        "original-issue-current-fotmob-reviewed-source.py.txt",
        "reason": "E3 RUN-02A durable cancellation/operation-authorization boundary for "
        "reviewed current FotMob source issuance",
    },
}


@pytest.mark.parametrize("path", sorted(_E3_B6_FORWARD_SOURCES))
def test_e3_three_source_forward_predecessors_bind_original_b6_and_current_a2(path):
    a2 = b4.boundary
    expected = _E3_B6_FORWARD_SOURCES[path]
    transition = a2.SOURCE_FORWARD_TRANSITIONS[path]
    for field, value in expected.items():
        assert transition[field] == value
    assert transition["a2_predecessor_generation"] == 275
    assert transition["a2_predecessor_sha256"] == \
        "8457db3718c62c42895f306818598fd0f48d6bf6f5b70a41e1a7938c59880fdc"
    assert transition["a2_generation"] == 276
    assert transition["a2_authorization_sha256"] == \
        "b648df655f80af20482ea8810aaf82a0d6d41799854908a3f3d18b697d3f3d29"
    assert transition["reason_type"] == "E3_RUN_02A_DURABLE_CANCELLATION_OPERATION_AUTHORIZATION"

    try:
        predecessor_tree = a2.git(
            "ls-tree", "-z", "5e362343b5d7423e5634186b52c934437445dd12", "--", path,
        )
    except subprocess.CalledProcessError:
        # Depth-one CI intentionally has no B6 base object or network fallback.
        # Its immutable B6 V1 row binds the original pin; the committed fixture
        # independently reproduces that exact Git blob and normalized source.
        b6_inventory = a2.read("tests/fixtures/core_01d/port02c-trigger-authority-b6-source-inventory-v1.json")
        historical = next(row for row in b6_inventory["source_identities"] if row["path"] == path)
        assert (historical["git_blob_sha1"], historical["normalized_source_sha256"], historical["byte_size"]) == (
            expected["predecessor_git_blob_sha1"], expected["predecessor_lf_source_sha256"],
            expected["predecessor_byte_size"],
        )
        original = None
    else:
        metadata, tree_path = predecessor_tree.rstrip(b"\0").split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split(" ")
        assert tree_path.decode("utf-8") == path
        assert (mode, kind, blob) == ("100644", "blob", expected["predecessor_git_blob_sha1"])
        original = a2.git("cat-file", "blob", blob)
    predecessor = a2.read_authenticated_forward_predecessor(path)
    if original is not None:
        assert predecessor == original
    assert len(predecessor) == expected["predecessor_byte_size"]
    assert hashlib.sha1(b"blob " + str(len(predecessor)).encode() + b"\0" + predecessor).hexdigest() == \
        expected["predecessor_git_blob_sha1"]
    assert hashlib.sha256(predecessor.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest() == \
        expected["predecessor_lf_source_sha256"]
    fixture_entry = a2.git("ls-tree", "-z", "HEAD", "--", transition["predecessor_fixture"])
    if fixture_entry:
        fixture_metadata, fixture_tree_path = fixture_entry.rstrip(b"\0").split(b"\t", 1)
        fixture_mode, fixture_kind, fixture_blob = fixture_metadata.decode("ascii").split(" ")
        assert fixture_tree_path.decode("utf-8") == transition["predecessor_fixture"]
        assert (fixture_mode, fixture_kind, fixture_blob) == (
            "100644", "blob", expected["predecessor_git_blob_sha1"],
        )

    current, current_identity = a2.read_tracked_head_blob(b4.ROOT, path)
    assert current_identity.git_blob_sha1 == expected["successor_git_blob_sha1"]
    assert hashlib.sha256(current.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest() == \
        expected["successor_lf_source_sha256"]


@pytest.mark.parametrize("path", sorted(b4.boundary.SOURCE_FORWARD_ALLOWED_PATHS))
def test_e3_three_source_forward_rejects_each_predecessor_byte_flip(monkeypatch, path):
    fixture = b4.ROOT / b4.boundary.SOURCE_FORWARD_TRANSITIONS[path]["predecessor_fixture"]
    original_read_bytes = Path.read_bytes

    def tampered_bytes(candidate):
        raw = original_read_bytes(candidate)
        if candidate == fixture:
            return bytes([raw[0] ^ 1]) + raw[1:]
        return raw

    monkeypatch.setattr(Path, "read_bytes", tampered_bytes)
    with pytest.raises(AssertionError, match="predecessor fixture identity mismatch"):
        b4.boundary.read_authenticated_forward_predecessor(path)


@pytest.mark.parametrize("mutation", ["missing", "invalid_encoding", "symlink", "path_traversal", "wrong_mode",
                                        "wrong_blob", "wrong_size", "wrong_digest"])
def test_e3_forward_source_rejects_fixture_path_mode_and_identity_mutations(monkeypatch, mutation):
    a2 = b4.boundary
    path = "domain/current_fotmob_latest_durable_fresh_history.py"
    fixture = b4.ROOT / a2.SOURCE_FORWARD_TRANSITIONS[path]["predecessor_fixture"]
    original_read_bytes = Path.read_bytes
    original_lstat = Path.lstat
    original_git = a2.git
    transition = deepcopy(a2.SOURCE_FORWARD_TRANSITIONS[path])
    if mutation == "path_traversal":
        transition["predecessor_fixture"] = "tests/fixtures/core_01d/../outside.py.txt"
        monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", {**a2.SOURCE_FORWARD_TRANSITIONS, path: transition})
        with pytest.raises(SourceIdentityError, match="traverses"):
            a2.read_authenticated_forward_predecessor(path)
        return
    if mutation == "wrong_blob":
        transition["predecessor_git_blob_sha1"] = "0" * 40
        monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", {**a2.SOURCE_FORWARD_TRANSITIONS, path: transition})
    elif mutation == "wrong_size":
        transition["predecessor_byte_size"] += 1
        monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", {**a2.SOURCE_FORWARD_TRANSITIONS, path: transition})
    elif mutation == "wrong_digest":
        transition["predecessor_lf_source_sha256"] = "0" * 64
        monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", {**a2.SOURCE_FORWARD_TRANSITIONS, path: transition})

    if mutation == "missing":
        def missing(candidate):
            if candidate == fixture:
                raise FileNotFoundError("deterministic missing-fixture simulation")
            return original_lstat(candidate)
        monkeypatch.setattr(Path, "lstat", missing)
        with pytest.raises(AssertionError, match="fixture is unavailable"):
            a2.read_authenticated_forward_predecessor(path)
    elif mutation == "invalid_encoding":
        def invalid_encoding(candidate):
            raw = original_read_bytes(candidate)
            if candidate == fixture:
                return b"\xff" + raw[1:]
            return raw
        monkeypatch.setattr(Path, "read_bytes", invalid_encoding)
        with pytest.raises(AssertionError, match="fixture encoding is invalid"):
            a2.read_authenticated_forward_predecessor(path)
    elif mutation == "symlink":
        def linked(candidate):
            if candidate == fixture:
                return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0)
            return original_lstat(candidate)
        monkeypatch.setattr(Path, "lstat", linked)
        with pytest.raises(AssertionError, match="symlink or junction"):
            a2.read_authenticated_forward_predecessor(path)
    elif mutation == "wrong_mode":
        def wrong_mode(*args, **kwargs):
            result = original_git(*args, **kwargs)
            if args[:3] == ("ls-tree", "-z", "HEAD") and args[-1] == transition["predecessor_fixture"]:
                metadata, tree_path = result.rstrip(b"\0").split(b"\t", 1)
                _mode, kind, blob = metadata.decode("ascii").split(" ")
                return b"100755 " + kind.encode() + b" " + blob.encode() + b"\t" + tree_path + b"\0"
            return result
        monkeypatch.setattr(a2, "git", wrong_mode)
        with pytest.raises(AssertionError, match="committed predecessor fixture identity mismatch"):
            a2.read_authenticated_forward_predecessor(path)
    elif mutation == "wrong_blob":
        monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", {**a2.SOURCE_FORWARD_TRANSITIONS, path: transition})
        with pytest.raises(AssertionError, match="predecessor fixture identity mismatch"):
            a2.read_authenticated_forward_predecessor(path)
    elif mutation in {"wrong_size", "wrong_digest"}:
        with pytest.raises(AssertionError, match="fixture (size|identity) mismatch"):
            a2.read_authenticated_forward_predecessor(path)



@pytest.mark.parametrize("mutation", [
    "unauthorized_current", "wrong_previous_generation", "wrong_successor_blob",
    "wrong_successor_digest", "wrong_fixture_path", "wrong_reason",
])
def test_e3_forward_source_rejects_unapproved_successor_or_a2_lineage(monkeypatch, mutation):
    a2 = b4.boundary
    path = "domain/sportybet_live_event_quote_evidence.py"
    original_read = a2.read_tracked_head_blob
    original_chain = a2.load_inventory_generations

    if mutation == "unauthorized_current":
        def altered_current(root, candidate, **kwargs):
            raw, identity = original_read(root, candidate, **kwargs)
            if candidate == path:
                raw += b"# unauthenticated source edit\n"
            return raw, identity
        monkeypatch.setattr(a2, "read_tracked_head_blob", altered_current)
    elif mutation == "wrong_previous_generation":
        def altered_chain():
            chain = original_chain()
            previous_path, previous = chain[-2]
            previous = deepcopy(previous)
            previous["canonical_sha256"] = "0" * 64
            chain[-2] = (previous_path, previous)
            return chain
        monkeypatch.setattr(a2, "load_inventory_generations", altered_chain)
    elif mutation in {"wrong_successor_blob", "wrong_successor_digest", "wrong_fixture_path", "wrong_reason"}:
        transition = deepcopy(a2.SOURCE_FORWARD_TRANSITIONS[path])
        if mutation == "wrong_successor_blob":
            transition["successor_git_blob_sha1"] = "0" * 40
        elif mutation == "wrong_successor_digest":
            transition["successor_lf_source_sha256"] = "0" * 64
        elif mutation == "wrong_fixture_path":
            transition["predecessor_fixture"] = "tests/fixtures/core_01d/another-predecessor.py.txt"
        else:
            transition["reason_type"] = "GENERIC_SOURCE_BYPASS"
        transitions = dict(a2.SOURCE_FORWARD_TRANSITIONS)
        transitions[path] = transition
        monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", transitions)

    with pytest.raises(AssertionError):
        a2.read_authenticated_forward_predecessor(path)


@pytest.mark.parametrize("path", sorted(b4.boundary.E3_B6_SOURCE_FORWARD_PATHS))
def test_e3_three_source_forward_rejects_unreviewed_current_source_edit(monkeypatch, path):
    a2 = b4.boundary
    original_read = a2.read_tracked_head_blob

    def altered_current(root, candidate, **kwargs):
        raw, identity = original_read(root, candidate, **kwargs)
        if candidate == path:
            raw += b"# unauthenticated source edit\n"
        return raw, identity

    monkeypatch.setattr(a2, "read_tracked_head_blob", altered_current)
    with pytest.raises(AssertionError, match="current successor identity mismatch"):
        a2.read_authenticated_forward_predecessor(path)


def test_e3_forward_source_policy_is_exactly_four_paths_and_rejects_forged_inventory_rows(monkeypatch):
    a2 = b4.boundary
    path = "domain/current_fotmob_latest_durable_fresh_history.py"
    original_chain = a2.load_inventory_generations
    with pytest.raises(AssertionError, match="unreviewed A2 source-forward path"):
        a2.read_authenticated_forward_predecessor("domain/another_module.py")

    original_transitions = a2.SOURCE_FORWARD_TRANSITIONS
    fourth = {**original_transitions, "domain/another_module.py": original_transitions[path]}
    monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", fourth)
    with pytest.raises(AssertionError, match="unreviewed A2 source-forward path"):
        a2.read_authenticated_forward_predecessor(path)
    moved = {key: value for key, value in original_transitions.items() if key != path}
    moved["domain/another_module.py"] = original_transitions[path]
    monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", moved)
    with pytest.raises(AssertionError, match="unreviewed A2 source-forward path"):
        a2.read_authenticated_forward_predecessor(path)
    monkeypatch.setattr(a2, "SOURCE_FORWARD_TRANSITIONS", original_transitions)

    def forged_current_row():
        chain = original_chain()
        latest_path, latest = chain[-1]
        latest = deepcopy(latest)
        for row in latest["source_identities"]:
            if row["path"] == path:
                row["lf_source_sha256"] = "0" * 64
        chain[-1] = (latest_path, latest)
        return chain
    monkeypatch.setattr(a2, "load_inventory_generations", forged_current_row)
    with pytest.raises(AssertionError, match="current successor row differs from authenticated latest inventory"):
        a2.read_authenticated_forward_predecessor(path)


@pytest.mark.parametrize("mutation", [
    "missing_latest_row", "stale_latest_generation", "broken_predecessor_sha",
    "broken_authorization_sha",
])
def test_e3_three_source_forward_rejects_forged_a2_authorization_chain(monkeypatch, mutation):
    a2 = b4.boundary
    path = "domain/current_fotmob_latest_durable_fresh_history.py"
    original_chain = a2.load_inventory_generations

    def altered_chain():
        chain = original_chain()
        if mutation == "stale_latest_generation":
            return chain[:-1]
        if mutation == "broken_predecessor_sha":
            index = a2.E3_B6_SOURCE_FORWARD_PREDECESSOR_GENERATION - 1
        elif mutation == "broken_authorization_sha":
            index = a2.E3_B6_SOURCE_FORWARD_AUTHORIZATION_GENERATION - 1
        else:
            index = len(chain) - 1
        row_path, value = chain[index]
        value = deepcopy(value)
        if mutation == "missing_latest_row":
            value["source_identities"] = [
                row for row in value["source_identities"] if row["path"] != path
            ]
        else:
            value["canonical_sha256"] = "0" * 64
        chain[index] = (row_path, value)
        return chain

    monkeypatch.setattr(a2, "load_inventory_generations", altered_chain)
    if mutation == "stale_latest_generation":
        with pytest.raises(AssertionError, match="latest inventory is stale against the current corpus"):
            a2.read_authenticated_forward_predecessor(path)
    else:
        with pytest.raises(AssertionError):
            a2.read_authenticated_forward_predecessor(path)


def test_audit_does_not_require_the_base_commit_object(monkeypatch):
    original = b4._git

    def reject_historical_base_lookup(*args):
        assert b4.BASE_MAIN not in args
        return original(*args)

    monkeypatch.setattr(b4, "_git", reject_historical_base_lookup)
    assert b4.audit()["result"] == "PASS"


def test_b4_never_changes_workflow_or_authorizes_live_operations(receipt):
    assert receipt["workflow_tree_sha1"] == b4.WORKFLOW_TREE
    assert receipt["workflow_edit_count"] == receipt["trigger_edit_count"] == 0
    assert receipt["retirement_count"] == receipt["deletion_count"] == receipt["caller_migration_count"] == 0
    assert set(receipt["actions"].values()) == {0}
    assert receipt["criterion_11"] is False and receipt["criterion_14"] is False
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
