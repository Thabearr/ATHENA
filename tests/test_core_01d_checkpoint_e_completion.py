"""All-criteria completion gate; incomplete evidence must remain incomplete."""
from copy import deepcopy

import pytest

from scripts import audit_core_01d_checkpoint_e_completion as completion
from scripts import audit_core_01d_historical_retention_acceptance as policy


@pytest.fixture(scope="module")
def receipt():
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as current
    return current.historical_v1_receipt()


def test_all_nineteen_green_are_required_for_complete():
    green = dict.fromkeys(completion.CRITERIA, True)
    assert completion.status_from_criteria(green) == ("COMPLETE", [])
    for criterion in completion.CRITERIA:
        changed = dict(green, **{criterion: False})
        assert completion.status_from_criteria(changed) == ("INCOMPLETE", [criterion])


def test_source_derived_receipt_does_not_manufacture_authority_review(receipt):
    # The owner's conditional rule takes precedence over the preferred all-green
    # test outcome. Existing source evidence leaves criteria 11 and 14 unproven.
    assert len(receipt["checkpoint_criteria"]) == 19
    assert sum(receipt["checkpoint_criteria"].values()) == 17
    assert receipt["remaining_blocker_ids"] == [completion.CRITERIA[10], completion.CRITERIA[13]]
    assert len(receipt["unreviewed_authority_surfaces"]) == 53
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
    assert receipt["retention_blocker_D_closed"] is True
    assert receipt["terminal"] == completion.BLOCKED_TERMINAL
    assert receipt["historical_checkpoint_e_v1"]["status"] == "INCOMPLETE"
    assert receipt["historical_forward_checkpoint_e_v2"]["status"] == "INCOMPLETE"


@pytest.mark.parametrize("criterion", completion.CRITERIA)
def test_resealed_criterion_flip_is_rejected(receipt, criterion):
    forged = deepcopy(receipt)
    forged["checkpoint_criteria"][criterion] = not forged["checkpoint_criteria"][criterion]
    status, blockers = completion.status_from_criteria(forged["checkpoint_criteria"])
    forged.update(checkpoint_e_status=status, p4_4_status=status, remaining_blocker_ids=blockers)
    policy.seal(forged)
    with pytest.raises(policy.RetentionAcceptanceError):
        completion.validate_receipt(forged, receipt)


@pytest.mark.parametrize("mutation", ["force_complete", "erase_unknown", "drop_blockers", "live_relation", "workflow_count", "trigger_count", "tree", "ledger", "transition_15", "retirement", "delete", "side_effect", "semantic_delta"])
def test_resealed_completion_authority_or_immutability_falsehoods_are_rejected(receipt, mutation):
    forged = deepcopy(receipt)
    if mutation == "force_complete":
        forged["checkpoint_criteria"] = dict.fromkeys(completion.CRITERIA, True)
        forged.update(checkpoint_e_status="COMPLETE", p4_4_status="COMPLETE", remaining_blocker_ids=[])
    elif mutation == "erase_unknown": forged["unreviewed_authority_surfaces"] = []
    elif mutation == "drop_blockers": forged["remaining_blocker_ids"] = []
    elif mutation == "live_relation": forged["live_missing_artifact_relation_count"] = 1
    elif mutation == "workflow_count": forged["workflow_count"] = 38
    elif mutation == "trigger_count": forged["trigger_surface_count"] = 56
    elif mutation == "tree": forged["workflow_tree_after_sha1"] = "0" * 40
    elif mutation == "ledger": forged["evolution_ledger_after_sha256"] = "0" * 64
    elif mutation == "transition_15": forged["transition_count"] = 15
    elif mutation == "retirement": forged["retirement_ledger_sha256"] = "0" * 64
    elif mutation == "delete": forged["deletion_authorized"] = True
    elif mutation == "side_effect": forged["actions"]["workflow_dispatch"] = 1
    else: forged["protected_semantic_delta"]["model"] = 1
    policy.seal(forged)
    with pytest.raises(policy.RetentionAcceptanceError):
        completion.validate_receipt(forged, receipt)


def test_boolean_and_inventory_criterion_contract_is_strict():
    green = dict.fromkeys(completion.CRITERIA, True)
    for malformed in ({}, {**green, "extra": True}, {**green, completion.CRITERIA[0]: 1}):
        with pytest.raises(policy.RetentionAcceptanceError):
            completion.status_from_criteria(malformed)


def test_scope_rejects_an_extra_runtime_file_without_base_commit_in_ci():
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as current
    with current.historical_v1_git_view():
        raw = policy.v4.v3._git("ls-tree", "-r", "HEAD")
    completion.validate_bounded_inventory(raw)
    forged = raw + b"100644 blob 0000000000000000000000000000000000000000\tmodels/unapproved.py\n"
    with pytest.raises(policy.RetentionAcceptanceError, match="unapproved repository change"):
        completion.validate_bounded_inventory(forged)


def test_completion_does_not_invoke_any_sender_even_a_mock(monkeypatch):
    import smtplib
    import socket
    from scripts import send_current_shadow_email as mail
    def deny(*args, **kwargs):
        raise AssertionError("sender/network invocation forbidden in evidence authentication")
    monkeypatch.setattr(mail, "send_receipt_email", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as current
    assert current.historical_v1_receipt()["checkpoint_criteria"]["notification_explicit_and_non_authoritative"] is True


def test_immutable_tree_evolution_retirement_and_false_authority(receipt):
    assert receipt["workflow_count"] == 39 and receipt["trigger_surface_count"] == 57
    assert receipt["workflow_tree_after_sha1"] == "9b08653f1a12bb1b3d964fbd910396ff955740da"
    assert receipt["evolution_ledger_after_sha256"] == "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
    assert receipt["transition_count"] == 14 and receipt["retired_workflow_count"] == 3
    assert all(receipt[k] is False for k in policy.NO_AUTHORITY)
    assert all(value == 0 for value in receipt["actions"].values())
    assert all(value == 0 for value in receipt["protected_semantic_delta"].values())


def test_master_current_status_is_independently_authenticated(receipt):
    from scripts import audit_checkpoint_e_workflows as master
    result = master.audit()
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as current
    from scripts import audit_core_01d_checkpoint_e_completion_v3 as a2
    assert result["historical_completion_v1_receipt_sha256"] == receipt["canonical_sha256"]
    assert result["current_completion_receipt_sha256"] == a2.audit()["receipt_sha256"]
    assert result["blockers"] == receipt["remaining_blocker_ids"]
    assert result["checkpoint_e"] == result["p4_4"] == "INCOMPLETE"
    with current.historical_v1_git_view():
        assert completion.audit()["result"] == "PASS"
