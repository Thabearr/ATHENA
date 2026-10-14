from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import audit_core_01d_pr459_live_trigger_incident as incident
from scripts import audit_app_01a_local_shell as app_history
from scripts import audit_core_01d_checkpoint_e_completion_v2 as pass_a_v2
from scripts import audit_core_01d_ci_offline_transport_boundary as a2
from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4
from scripts import audit_data_01c_restore_portability as d5
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_both_direct_share_workflows_are_offline_only():
    for path in (incident.CREATE_WORKFLOW, incident.PROVE_WORKFLOW):
        workflow = incident._validate_workflow(path)
        assert workflow["permissions"] == {"contents": "read"}
        assert workflow["on"]["workflow_dispatch"]["inputs"]["validation_mode"]["options"] == [
            "offline_only"
        ]
        assert all(
            not any(marker.casefold() in str(step.get(key, "")).casefold()
                    for marker in incident.LIVE_MARKERS)
            for step in workflow["jobs"]["offline-validation"]["steps"]
            for key in ("run", "uses")
        )


def test_offline_workflow_successor_is_authenticated_by_current_evolution_projection():
    ledger = evolution.validate_current_state()
    assert evolution.current_workflow_tree_sha1(ledger) == evolution.PR459_OFFLINE_WORKFLOW_TREE_SHA1


def test_b4_historical_workflow_identity_and_receipt_remain_unchanged():
    for path, expected in b4.B4_WORKFLOW_PREDECESSORS.items():
        raw = b4._historical_b4_workflow_bytes(path)
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == b4.SOURCE_PINS[path][0]
        assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == b4.SOURCE_PINS[path][1]
        assert Path(b4.ROOT / expected).is_file()
    assert b4.audit()["result"] == "PASS"
    assert incident.audit()["canonical_sha256"] == incident.build_receipt()["canonical_sha256"]


def test_a2_successor_workflows_keep_their_immutable_pass_a_blob_pins():
    paths = set(a2.A2_SUCCESSOR_WORKFLOWS)
    assert paths == set(b4.B4_WORKFLOW_PREDECESSORS)
    assert paths <= a2.A2_PATHS
    assert pass_a_v2.pass_a_preserved_a2_successor_paths(a2) == paths
    assert pass_a_v2.pass_a_nonhistorical_a2_generation_paths(a2, paths) == set()
    for path in paths:
        assert pass_a_v2.PASS_A_HISTORICAL_BLOBS[path] == b4.SOURCE_PINS[path][0]


def test_pass_a_projection_does_not_override_authenticated_predecessors():
    app_sources = {
        "scripts/audit_checkpoint_e_workflows.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
    }
    assert app_sources <= set(app_history.PATHS)
    assert not (app_sources & set(pass_a_v2.PASS_A_HISTORICAL_BLOBS))

    # These two rows already have stronger immutable predecessor owners. The
    # first is in D5's sealed source snapshot; the second is in both D5 and
    # the exact A2 V1 source fixture. Later main-source blobs cannot replace
    # those historic identities in the Pass-A projection.
    retained_status = "scripts/audit_core_01d_retained_workflow_status_v2.py"
    p4_evolution = "scripts/audit_p4_workflow_evolution_ledger.py"
    d5_sources = d5.snapshot()["sources"]
    assert d5_sources[retained_status]["git_blob_sha1"] == "26968a425f642910991332dba87519add8a0cc19"
    assert d5_sources[p4_evolution]["git_blob_sha1"] == "fdd2932200ed4467dca902fabe01dab76d5fe451"
    assert not ({retained_status, p4_evolution} & set(pass_a_v2.PASS_A_HISTORICAL_BLOBS))
    assert p4_evolution in d5.HISTORICAL_A2_SOURCE_FIXTURES


def test_tampered_b4_predecessor_fixture_fails(monkeypatch):
    path = incident.CREATE_WORKFLOW
    fixture = b4.ROOT / b4.B4_WORKFLOW_PREDECESSORS[path]
    original = Path.read_bytes

    def tampered(source):
        raw = original(source)
        return raw + b"#tampered\n" if Path(source) == fixture else raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(AssertionError, match="predecessor fixture identity mismatch"):
        b4._historical_b4_workflow_bytes(path)


def test_current_workflow_tampering_cannot_hide_behind_b4_fixture(monkeypatch):
    path = incident.PROVE_WORKFLOW
    source = b4.ROOT / path
    original = Path.read_bytes

    def tampered(candidate):
        raw = original(candidate)
        return raw + b"#unreviewed\n" if Path(candidate) == source else raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(AssertionError, match="differs from latest A2"):
        b4._historical_b4_workflow_bytes(path)


def test_shallow_projection_does_not_request_the_historical_b4_base(monkeypatch):
    original = b4._git

    def reject_base_lookup(*args: str) -> bytes:
        assert b4.BASE_MAIN not in args
        return original(*args)

    monkeypatch.setattr(b4, "_git", reject_base_lookup)
    assert b4.audit()["result"] == "PASS"
