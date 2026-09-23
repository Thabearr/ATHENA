from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import socket
from urllib import request as urllib_request

import pytest

from scripts import audit_p4_2_athena_run_workflow as p42
from scripts import audit_p4_3_workflow_retirement_ledger as ledger
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_3a_workflow_capability_census as p43a
from scripts import audit_p4_3b_current_sportybet_workflow_retirement as p43b
from scripts import audit_p4_3c_spent_v1_evidence_workflow_retirement as audit


def test_exactly_two_v1_paths_are_retired_and_successors_remain_reviewed() -> None:
    matrix, _ = ledger.load_baseline()
    current_ledger = ledger.validate_retirement_history()
    current_evolution = evolution.validate_current_state(retirement_ledger=current_ledger)
    live = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    expected = sorted({row["workflow_path"] for row in matrix["workflow_rows"]} - set(current_ledger["retired_workflow_paths"]))
    assert len(live) == current_evolution["current_live_workflow_count"]
    assert set(expected).issubset(live)
    for path, details in audit.TARGETS.items():
        assert not Path(path).exists()
        v2_raw = ledger.resolve_reviewed_workflow_source(details["successor"], ledger=current_ledger)
        assert audit._identity(v2_raw) == (
            details["successor_git_blob_sha1"], details["successor_source_sha256"]
        )
    assert not Path(".github/workflows/current-sportybet-accumulator.yml").exists()
    assert len(current_ledger["retired_workflow_paths"]) == 3


@pytest.mark.parametrize("path", sorted(audit.TARGETS))
def test_historical_v1_fixture_identity_is_exact_and_byte_drift_fails(path: str) -> None:
    details = audit.TARGETS[path]
    raw = Path(details["fixture_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == details["source_sha256"]
    assert audit._identity(raw)[0] == details["git_blob_sha1"]
    changed = bytes([raw[0] ^ 1]) + raw[1:]
    with pytest.raises(audit.P43CRetirementError, match="fixture identity drifted"):
        audit.verify_target(path, v1_fixture_bytes=changed)


def test_feature_v1_spent_guard_failure_is_reconciled_by_successful_v2() -> None:
    path = ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification.yml"
    proof = audit.verify_target(path)
    lineage = proof["v1_reconciled_attempt"]
    assert proof["supersession_type"] == "RECONCILED_V2_SUCCESSOR_AFTER_SPENT_V1_GUARD_FAILURE"
    assert lineage["run_id"] == 31987862156
    assert lineage["artifact_id"] == 9274313978
    assert lineage["state"] == audit.FIXED_V1_SPENT_STATE
    assert lineage["qualification_executed"] is False
    assert proof["successor_v2"]["success_run"]["run_id"] == 31990121181
    assert proof["successor_v2"]["success_run"]["head_sha"] == "cd67be14f6a4f09484d18a57de360b8a5d4c51d7"


def test_pr69_v1_unqualified_campaign_is_reconciled_by_successful_v2() -> None:
    path = ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml"
    proof = audit.verify_target(path)
    lineage = proof["v1_reconciled_attempt"]
    assert proof["supersession_type"] == "RECONCILED_V2_SUCCESSOR_AFTER_FAILED_V1_EVIDENCE_CAMPAIGN"
    assert lineage["run_id"] == 31953949073
    assert lineage["run_conclusion"] == "cancelled"
    assert lineage["campaign_step_conclusion"] == "success"
    assert lineage["qualification_gate_conclusion"] == "failure"
    assert lineage["artifact_id"] == 9266604353
    assert lineage["artifact_sha256"] == "ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7"
    assert lineage["state"] == audit.PR69_V1_UNQUALIFIED_STATE
    assert proof["successor_v2"]["success_run"]["run_id"] == 31974333489
    assert proof["successor_v2"]["success_run"]["head_sha"] == "4a2ca10af4b14194253ba6fc84bca780e2b03d58"


@pytest.mark.parametrize("path", sorted(audit.TARGETS))
def test_v2_reconciliation_identity_drift_fails_closed(path: str) -> None:
    details = audit.TARGETS[path]
    source = ledger.resolve_reviewed_workflow_source(details["successor"]).decode("utf-8")
    token = details["v2_source_tokens"][0]
    with pytest.raises(audit.P43CRetirementError, match="missing/changed"):
        audit.verify_target(path, v2_source=source.replace(token, "changed", 1))


@pytest.mark.parametrize("path", sorted(audit.TARGETS))
def test_historical_check_accepts_reviewed_future_retired_v2_fixture(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    details = audit.TARGETS[path]
    v2_path = details["successor"]
    live_proof = audit.verify_target(path)
    current = copy.deepcopy(ledger.validate_ledger())
    v2_raw = ledger.resolve_reviewed_workflow_source(v2_path, ledger=current)
    fixture = tmp_path / Path(v2_path).name
    fixture.write_bytes(v2_raw)
    current["retirements"].append({
        "workflow_path": v2_path,
        "git_blob_sha1": details["successor_git_blob_sha1"],
        "source_sha256": details["successor_source_sha256"],
        "fixture_path": str(fixture),
        "retirement_phase": "P4.3D_TEST_ONLY",
        "retirement_receipt_path": "artifacts/architecture/p4_3d_synthetic_test_only.json",
        "retirement_receipt_sha256": "a" * 64,
        "successor_workflow_path": ".github/workflows/athena-run.yml",
    })
    current["retirements"].sort(key=lambda item: item["workflow_path"])
    current["retired_workflow_paths"] = sorted(item["workflow_path"] for item in current["retirements"])
    current["current_retired_workflow_count"] = 4
    current["current_live_workflow_count"] = 36
    current["canonical_sha256"] = ledger.canonical_sha256(current)
    ledger.validate_historical_snapshot_extension(ledger._load_p43c_ledger_snapshot(), current)

    original_exists = Path.exists

    def future_tree_exists(candidate: Path) -> bool:
        return False if candidate.as_posix() == v2_path else original_exists(candidate)

    monkeypatch.setattr(Path, "exists", future_tree_exists)
    monkeypatch.setattr(ledger, "validate_ledger", lambda: current)
    assert audit.verify_target(path, current_ledger=current) == live_proof
    before = audit.RECEIPT_PATH.read_bytes()
    assert audit.check()["canonical_sha256"] == audit.P43C_RECEIPT_SHA
    assert audit.RECEIPT_PATH.read_bytes() == before

    fixture.write_bytes(v2_raw[:-1] + bytes([v2_raw[-1] ^ 1]))
    with pytest.raises(ledger.RetirementLedgerError, match="fixture identity differs from baseline"):
        audit.check()


@pytest.mark.parametrize("path", sorted(audit.TARGETS))
def test_new_successful_v1_history_blocks_retirement(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    latest = dict(audit.TARGETS[path]["live_latest"], conclusion="success")
    monkeypatch.setitem(audit.TARGETS[path], "live_latest", latest)
    with pytest.raises(audit.P43CRetirementError, match="new V1 success"):
        audit.verify_target(path)


def test_p4_3c_receipt_and_cumulative_ledger_bind_three_retirements() -> None:
    receipt = audit.check()
    current_ledger = ledger.validate_ledger()
    snapshot = ledger._load_p43c_ledger_snapshot()
    assert receipt["canonical_sha256"] == audit.canonical_sha256(receipt)
    assert receipt["retirement_ledger_sha256"] == snapshot["canonical_sha256"] == audit.P43C_LEDGER_SNAPSHOT_SHA
    ledger.validate_historical_snapshot_extension(snapshot, current_ledger)
    assert receipt["workflow_count_before"] == 39
    assert receipt["workflow_count_after"] == 37
    assert receipt["workflow_count_decreased_by"] == 2
    assert receipt["cumulative_retired_workflow_count"] == 3
    assert receipt["unique_required_capability_lost"] is False
    assert receipt["p4_3c_retirement_gate_satisfied"] is True
    assert receipt["architecture_checkpoint_e_fully_claimed"] is False
    assert receipt["p4_4_started"] is False


def test_prior_architecture_receipts_and_audits_remain_immutable() -> None:
    p43a.check(write_receipt=False)
    p43b.check(write_receipt=False)
    p42.verify_committed_receipt()
    p42.verify_preserved_historical_sources()
    historical = p42.verify_retired_workflow_historical_fixtures()
    assert historical == {
        path: details["git_blob_sha1"] for path, details in audit.TARGETS.items()
    }
    assert json.loads(Path(p43a.RECEIPT_PATH).read_text(encoding="utf-8"))["canonical_sha256"] == p43a.RECEIPT_SHA
    assert json.loads(p43b.RECEIPT.read_text(encoding="utf-8"))["canonical_sha256"] == p43b.P43B_SHA256


def test_no_network_is_attempted_by_retirement_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline P4.3C/ledger audit attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib_request, "urlopen", forbidden)
    assert audit.check()["network_attempt_count"] == 0
    current = ledger.validate_ledger()
    assert current["current_live_workflow_count"] == 40 - len(current["retired_workflow_paths"])


def test_p4_3c_receipt_write_mode_is_disabled_and_read_only() -> None:
    before = audit.RECEIPT_PATH.read_bytes()
    with pytest.raises(audit.P43CRetirementError, match="frozen historical evidence"):
        audit.check(write=True)
    assert audit.RECEIPT_PATH.read_bytes() == before


def test_historical_v1_tests_read_frozen_fixtures() -> None:
    feature_v1_test = Path("tests/test_execute_fotmob_utc_native_successor_feature_qualification_workflow.py").read_text(encoding="utf-8")
    pr69_v1_test = Path("tests/test_pr69_primary_time_basis_evidence_campaign_execution_lane.py").read_text(encoding="utf-8")
    assert "tests/fixtures/architecture/retired_workflows/execute-fotmob-utc-native-successor-feature-qualification.yml" in feature_v1_test
    assert "tests/fixtures/architecture/retired_workflows/execute-pr69-primary-time-basis-evidence-campaign.yml" in pr69_v1_test


def test_current_documentation_does_not_present_v1_paths_as_executable() -> None:
    docs = "\n".join(path.read_text(encoding="utf-8") for path in Path("docs").rglob("*.md"))
    for path in audit.TARGETS:
        assert path not in docs


def test_current_shadow_canonical_and_protected_workflows_are_still_live() -> None:
    for path in ledger.PROTECTED_LIVE:
        assert Path(path).is_file()
    assert Path(".github/workflows/athena-draft-ready-bridge.yml").is_file()
