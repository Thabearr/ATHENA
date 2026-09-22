from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
from urllib import request as urllib_request

import pytest

from scripts import audit_p4_2_athena_run_workflow as p42
from scripts import audit_p4_3_workflow_retirement_ledger as ledger
from scripts import audit_p4_3a_workflow_capability_census as p43a
from scripts import audit_p4_3b_current_sportybet_workflow_retirement as p43b
from scripts import audit_p4_3c_spent_v1_evidence_workflow_retirement as audit


def test_exactly_two_v1_paths_are_retired_and_successors_remain_live() -> None:
    matrix, _ = ledger.load_baseline()
    live = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    expected = sorted({row["workflow_path"] for row in matrix["workflow_rows"]} - set(ledger.RETIRED))
    assert len(live) == 37
    assert live == expected
    for path, details in audit.TARGETS.items():
        assert not Path(path).exists()
        assert Path(details["successor"]).is_file()
    assert not Path(".github/workflows/current-sportybet-accumulator.yml").exists()
    assert len(ledger.RETIRED) == 3


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
    source = Path(details["successor"]).read_text(encoding="utf-8")
    token = details["v2_source_tokens"][0]
    with pytest.raises(audit.P43CRetirementError, match="missing/changed"):
        audit.verify_target(path, v2_source=source.replace(token, "changed", 1))


@pytest.mark.parametrize("path", sorted(audit.TARGETS))
def test_new_successful_v1_history_blocks_retirement(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    latest = dict(audit.TARGETS[path]["live_latest"], conclusion="success")
    monkeypatch.setitem(audit.TARGETS[path], "live_latest", latest)
    with pytest.raises(audit.P43CRetirementError, match="new V1 success"):
        audit.verify_target(path)


def test_p4_3c_receipt_and_cumulative_ledger_bind_three_retirements() -> None:
    receipt = audit.check()
    current_ledger = ledger.validate_ledger()
    assert receipt["canonical_sha256"] == audit.canonical_sha256(receipt)
    assert receipt["retirement_ledger_sha256"] == current_ledger["canonical_sha256"]
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
    assert ledger.validate_ledger()["current_live_workflow_count"] == 37


def test_only_historical_v1_tests_read_fixture_and_v2_tests_remain_live() -> None:
    feature_v1_test = Path("tests/test_execute_fotmob_utc_native_successor_feature_qualification_workflow.py").read_text(encoding="utf-8")
    pr69_v1_test = Path("tests/test_pr69_primary_time_basis_evidence_campaign_execution_lane.py").read_text(encoding="utf-8")
    feature_v2_test = Path("tests/test_execute_fotmob_utc_native_successor_feature_qualification_v2_workflow.py").read_text(encoding="utf-8")
    pr69_v2_test = Path("tests/test_pr69_primary_time_basis_evidence_campaign_execution_lane_v2.py").read_text(encoding="utf-8")
    assert "tests/fixtures/architecture/retired_workflows/execute-fotmob-utc-native-successor-feature-qualification.yml" in feature_v1_test
    assert "tests/fixtures/architecture/retired_workflows/execute-pr69-primary-time-basis-evidence-campaign.yml" in pr69_v1_test
    assert ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml" in feature_v2_test
    assert ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml" in pr69_v2_test


def test_current_documentation_does_not_present_v1_paths_as_executable() -> None:
    docs = "\n".join(path.read_text(encoding="utf-8") for path in Path("docs").rglob("*.md"))
    for path in audit.TARGETS:
        assert path not in docs


def test_current_shadow_canonical_and_protected_workflows_are_still_live() -> None:
    for path in ledger.PROTECTED_LIVE:
        assert Path(path).is_file()
    assert Path(".github/workflows/athena-draft-ready-bridge.yml").is_file()
