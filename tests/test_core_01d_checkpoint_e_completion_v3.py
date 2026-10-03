"""Bounded source overlay; hosted Linux proof is a separate exact-head gate."""
from copy import deepcopy
import pytest
from scripts import audit_core_01d_checkpoint_e_completion_v3 as current
from scripts import audit_core_01d_ci_offline_transport_boundary as boundary


@pytest.fixture(scope="module")
def receipt():
    return current.build_receipt()


def test_overlay_is_exactly_three_and_other_unknowns_are_preserved(receipt):
    old = boundary.read(current.PARENT_PATH)
    assert old["canonical_sha256"] == boundary.PREDECESSORS[current.PARENT_PATH]
    keys = set(boundary.TARGETS)
    assert receipt["unreviewed_authority_surfaces"] == [
        row for row in old["unreviewed_authority_surfaces"]
        if (row["workflow_path"], row["trigger_kind"]) not in keys]
    assert receipt["resolved_a2_target_count"] == 3
    assert receipt["remaining_unreviewed_surface_count"] == 32
    for row in receipt["a2_authority_rows"]:
        before = next(r for r in old["unresolved_pass_a_rows"]
                      if (r["workflow_path"], r["trigger_kind"]) == (row["workflow_path"], row["trigger_kind"]))
        for field in ("branch_write_authority", "artifact_read_authority", "artifact_write_authority"):
            assert row[field] == before[field]
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
    assert len(receipt["checkpoint_criteria"]) == 19
    assert sum(receipt["checkpoint_criteria"].values()) == 17


@pytest.mark.parametrize("mutation", ["drop_unknown", "out_of_scope", "criterion11", "criterion14", "complete", "p44", "tree", "authority"])
def test_resealed_false_completion_rejected(receipt, mutation):
    value = deepcopy(receipt)
    if mutation == "drop_unknown": value["unreviewed_authority_surfaces"].pop()
    elif mutation == "out_of_scope": value["a2_authority_rows"][0]["workflow_path"] = ".github/workflows/athena-run.yml"
    elif mutation == "criterion11": value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] = True
    elif mutation == "criterion14": value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] = True
    elif mutation == "complete": value["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "p44": value["p4_4_status"] = "COMPLETE"
    elif mutation == "tree": value["workflow_tree_after_sha1"] = "0" * 40
    else: value["review_grants_new_execution_authority"] = True
    value = boundary.seal(value)
    with pytest.raises(AssertionError): current.validate_receipt(value, receipt)


def test_new_or_changed_caller_requires_new_source_review(monkeypatch):
    original = boundary.build_inventory
    def drift():
        value = original()
        value["transport_and_process_discovery_obligations"].append({"path": "tests/test_unreviewed.py", "classification": "UNRESOLVED"})
        return boundary.seal(value)
    monkeypatch.setattr(boundary, "build_inventory", drift)
    with pytest.raises(AssertionError, match="source or process discovery drift"):
        boundary.authenticate_inventory()


def test_source_classification_is_not_a_claim_that_hosted_gate_ran(receipt):
    a2 = boundary.read(boundary.RECEIPT_PATH)
    assert a2["proof_gates"]["linux_hosted"] == "REQUIRED_EXTERNAL_EXACT_HEAD_GATE_BEFORE_REVIEW_READY_CLAIM"
    assert "run_id" not in a2["proof_gates"]
    assert receipt["actions"] == boundary.ZERO_ACTIONS


def test_saved_factory_and_process_aliases_have_explicit_boundary_owners():
    source = b"import requests\nimport subprocess\nsession=requests.Session()\nsaved=subprocess.Popen\nsession.get('http://example.invalid')\nsaved(['curl','http://example.invalid'])\n"
    rows = boundary.classified_obligations("tests/test_synthetic_aliases.py", source)
    assert any(row["callee"] == "requests.Session.get" and row["classification"] == "GUARDED_BY_IN_PROCESS_TRANSPORT_DENIAL" for row in rows)
    assert any(row["callee"] == "subprocess.Popen" and row["classification"] == "GUARDED_NON_PYTHON_SUBPROCESS_POLICY" for row in rows)
