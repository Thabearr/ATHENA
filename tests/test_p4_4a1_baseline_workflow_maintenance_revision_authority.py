from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4a1_baseline_workflow_maintenance_revision_authority as authority
from scripts import audit_p4_workflow_evolution_ledger as evolution


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def test_real_p44a1_phase_has_zero_revision_and_preserves_37_workflows() -> None:
    receipt = authority.check()
    current = evolution.validate_current_state()
    if current["canonical_sha256"] == receipt["current_evolution_ledger_sha256"]:
        assert current["transitions"] == []
        assert current["current_live_workflow_count"] == 37
        assert current["current_workflow_tree_sha1"] == authority.BASE_WORKFLOW_TREE_SHA1
        assert len(list(Path(".github/workflows").glob("*.yml"))) == 37
        assert not Path(".github/workflows/athena-ingest.yml").exists()
        if authority._base_commit_available():
            assert _git("diff", "--name-only", f"{authority.BASE_MAIN_SHA}...HEAD", "--", ".github/workflows") == ""
        else:
            # Hosted Tests may use a shallow checkout without the P4.4A base object.
            # The offline authority audit still verifies the exact frozen workflow tree.
            assert _git("diff", "--name-only", "HEAD", "--", ".github/workflows") == ""
    else:
        # Future reviewed phases may extend current state; P4.4A1 remains a frozen checkpoint.
        snapshot = json.loads(
            Path(authority.P44A_SNAPSHOT_PATH).read_text(encoding="utf-8")
        )
        p43_snapshot = evolution.load_retirement_snapshot_for_evolution(snapshot)
        current_p43 = retirement.validate_retirement_history()
        current_p43_snapshot = evolution.load_retirement_snapshot_for_evolution(current)
        evolution.validate_evolution_snapshot_extension(
            snapshot,
            current,
            snapshot_retirement_snapshot=p43_snapshot,
            current_retirement_snapshot=current_p43_snapshot,
            current_retirement=current_p43,
        )


def test_p44a1_receipt_is_frozen_and_binds_maintenance_only_authority() -> None:
    receipt = authority.check()
    assert receipt["canonical_sha256"] == authority.RECEIPT_SHA256
    assert evolution.canonical_sha256(receipt) == receipt["canonical_sha256"]
    assert receipt["new_transition_operation"] == "MAINTENANCE_REVISE"
    assert receipt["ordinary_revise_of_p43a_survivor_allowed"] is False
    assert receipt["maintenance_revise_of_p43a_survivor_allowed"] is True
    assert receipt["evolution_retire_of_p43a_survivor_allowed"] is False
    assert receipt["add_existing_p43a_path_allowed"] is False
    assert receipt["historical_before_fixture_required"] is True
    assert receipt["maintenance_contract_required"] is True
    assert receipt["maintenance_revision_net_workflow_count_delta"] == 0
    assert receipt["real_workflow_revision_performed"] is False
    assert receipt["workflow_yaml_changed"] is False
    assert receipt["fresh_holdout_workflow_changed"] is False
    assert receipt["permanent_fresh_holdout_hotfix_implemented"] is False
    assert receipt["next_required_step"] == "FRESH_HOLDOUT_RELEASE_VISIBILITY_RACE_HOTFIX_REQUIRED"
    assert receipt["p4_4b_started"] is False
    assert receipt["p4_4_overall_complete"] is False
    assert receipt["architecture_checkpoint_e_fully_claimed"] is False
    assert receipt["source_review_counter_while_unmerged"] == "1/5"
    assert receipt["source_review_counter_if_merged"] == "2/5"


def test_current_evolution_ledger_is_still_the_immutable_p44a_snapshot() -> None:
    ledger_raw = Path(authority.EVOLUTION_LEDGER_PATH).read_bytes()
    snapshot_raw = Path(authority.P44A_SNAPSHOT_PATH).read_bytes()
    ledger = json.loads(ledger_raw)
    if ledger["canonical_sha256"] == authority.EVOLUTION_LEDGER_SHA256:
        assert ledger_raw == snapshot_raw
        assert ledger["transitions"] == []
    else:
        snapshot = json.loads(snapshot_raw)
        p43 = retirement.validate_retirement_history()
        p43_snapshot = evolution.load_retirement_snapshot_for_evolution(ledger)
        evolution.validate_evolution_snapshot_extension(
            snapshot,
            ledger,
            snapshot_retirement_snapshot=evolution.load_retirement_snapshot_for_evolution(snapshot),
            current_retirement_snapshot=p43_snapshot,
            current_retirement=p43,
        )
    assert authority.check()["current_transition_count"] == 0


def test_p43a_matrix_and_p44a_checkpoint_remain_immutable() -> None:
    matrix = json.loads(Path("artifacts/architecture/p4_3_workflow_capability_matrix_v1.json").read_text(encoding="utf-8"))
    assert len(matrix["workflow_rows"]) == matrix["workflow_count"] == 40
    assert matrix["canonical_sha256"] == "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d"
    snapshot = json.loads(Path(authority.P44A_SNAPSHOT_PATH).read_text(encoding="utf-8"))
    assert snapshot["canonical_sha256"] == authority.P44A_SNAPSHOT_SHA256
    assert snapshot["transitions"] == []
    assert snapshot["current_live_workflow_count"] == 37
    assert snapshot["current_p4_3_retired_workflow_count"] == 3
    p44a_receipt = json.loads(Path("artifacts/architecture/p4_4a_workflow_evolution_guard_v1.json").read_text(encoding="utf-8"))
    assert p44a_receipt["canonical_sha256"] == authority.P44A_RECEIPT_SHA256


def test_p43_retirement_checkpoint_and_current_state_remain_valid() -> None:
    checkpoint = retirement._load_p43c_ledger_snapshot()
    current = retirement.validate_retirement_history()
    assert checkpoint["canonical_sha256"] == authority.P43_RETIREMENT_CHECKPOINT_SHA256
    if current["canonical_sha256"] == authority.P43_RETIREMENT_CHECKPOINT_SHA256:
        assert current["current_retired_workflow_count"] == 3
        assert current["current_live_workflow_count"] == 37
    else:
        retirement.validate_historical_snapshot_extension(checkpoint, current)
        assert current["current_retired_workflow_count"] >= 3


def test_fresh_holdout_workflow_and_mirror_pins_match_the_reviewed_base() -> None:
    expected = {
        **authority.FRESH_HOLDOUT_WORKFLOW_BLOBS,
        **authority.FRESH_HOLDOUT_SCRIPT_BLOBS,
    }
    current = evolution.validate_current_state()
    maintenance = {
        item["workflow_path"]: item
        for item in current["transitions"]
        if item["operation"] == "MAINTENANCE_REVISE"
    }
    hotfix = json.loads(
        Path("artifacts/architecture/fresh_holdout_release_visibility_race_hotfix_v1.json")
        .read_text(encoding="utf-8")
    )
    for path, blob in expected.items():
        if path in maintenance:
            historical = evolution.resolve_p43a_historical_workflow_source(
                path, evolution_ledger=current
            )
            assert evolution.source_identity(historical)["git_blob_sha1"] == blob
        elif path == "scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py":
            # The P4.4A1 transport source is now preserved by this hotfix's
            # exact before-fixture; its current live identity is independently
            # checked by the hotfix receipt/tests.
            old_transport = Path(hotfix["transport_before_fixture_path"]).read_bytes()
            assert evolution.source_identity(old_transport)["git_blob_sha1"] == blob
        else:
            identity_commit = authority.BASE_MAIN_SHA if authority._base_commit_available() else "HEAD"
            assert _git("rev-parse", f"{identity_commit}:{path}") == blob
    receipt = authority.check()
    assert receipt["fresh_holdout_workflow_blob_sha1"] == authority.FRESH_HOLDOUT_WORKFLOW_BLOBS
    assert receipt["fresh_holdout_script_blob_sha1"] == authority.FRESH_HOLDOUT_SCRIPT_BLOBS


def test_p44a1_historical_sources_and_current_maintenance_identities_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise the same mode used by shallow hosted checkouts: the immutable base
    # commit may be absent, while HEAD still carries the reviewed original fixtures.
    monkeypatch.setattr(authority, "_base_commit_available", lambda: False)
    receipt = authority.check()
    current = evolution.validate_current_state()
    assert receipt["workflow_yaml_changed"] is False
    transitions = {
        item["workflow_path"]: item
        for item in current["transitions"]
        if item["operation"] == "MAINTENANCE_REVISE"
    }
    targets = (
        ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
    )
    assert len(transitions) == 2
    for path in targets:
        transition = transitions[path]
        historical = evolution.resolve_p43a_historical_workflow_source(
            path, evolution_ledger=current
        )
        fixture_path = transition["historical_before_fixture"]["path"]
        assert Path(fixture_path).read_bytes() == historical
        assert evolution.source_identity(historical) == transition["before"]
        current_bytes = Path(path).read_bytes().replace(b"\r\n", b"\n")
        assert evolution.source_identity(current_bytes) == transition["after"]
        assert _git("rev-parse", f"HEAD:{path}") == transition["after"]["git_blob_sha1"]

    hotfix = json.loads(
        Path("artifacts/architecture/fresh_holdout_release_visibility_race_hotfix_v1.json")
        .read_text(encoding="utf-8")
    )
    old_transport_fixture = Path(hotfix["transport_before_fixture_path"]).read_bytes()
    assert hashlib.sha256(old_transport_fixture).hexdigest() == hotfix["transport_before_fixture_sha256"]
    assert retirement._git_blob_sha1(old_transport_fixture) == hotfix["transport_blob_before"]
    assert _git("rev-parse", "HEAD:scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py") == hotfix["transport_blob_after"]

    bridge = transitions[targets[0]]
    bridge_original = evolution.resolve_p43a_historical_workflow_source(
        targets[0], evolution_ledger=current
    )
    bridge_fixture_path = bridge["historical_before_fixture"]["path"]
    corrupted_original = bridge_original[:-1] + bytes([bridge_original[-1] ^ 1])
    with pytest.raises(evolution.WorkflowEvolutionError, match="differ from frozen matrix"):
        evolution.resolve_p43a_historical_workflow_source(
            targets[0],
            evolution_ledger=current,
            historical_fixture_bytes={bridge_fixture_path: corrupted_original},
        )
    changed_current = dict(current["transitions"][0]["after"])
    changed_current["source_sha256"] = "0" * 64
    with pytest.raises(evolution.WorkflowEvolutionError, match=targets[0]):
        evolution.validate_derived_tree(
            {targets[0]: changed_current},
            {targets[0]: bridge["after"]},
        )


def test_all_frozen_pre_p44a_evidence_identities_remain_exact() -> None:
    for path, expected in authority.FROZEN_ARTIFACTS.items():
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        assert value["canonical_sha256"] == expected
        assert evolution.canonical_sha256(value) == expected
    assert authority.check()["p4_3_retirement_ledger_sha256"] == authority.P43_RETIREMENT_CHECKPOINT_SHA256


def test_zero_real_operation_and_safety_flags_are_false() -> None:
    receipt = authority.check()
    false_fields = (
        "provider_acquisition",
        "workflow_dispatch_triggered",
        "current_shadow_triggered",
        "fresh_holdout_triggered",
        "p3_0_e1_triggered",
        "real_share_code_operation",
        "login",
        "cookies",
        "wallet",
        "staking",
        "wager_placed",
        "model_formula_changed",
        "router_formula_changed",
        "portfolio_formula_changed",
        "provider_semantics_changed",
        "authority_semantics_changed",
        "backfill_performed",
        "athena_ingest_created",
        "permanent_fresh_holdout_hotfix_implemented",
    )
    assert all(receipt[field] is False for field in false_fields)
    assert receipt["fresh_holdout_durability_repair_additional_provider_requests"] == 0
    assert receipt["fresh_holdout_durability_incident_source_run_id"] == 35847067175
    assert receipt["fresh_holdout_durability_bridge_run_id"] == 35847076204
    assert receipt["fresh_holdout_durability_repair_run_id"] == 35857443476
