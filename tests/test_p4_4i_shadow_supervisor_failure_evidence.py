from __future__ import annotations

import copy

import pytest

from scripts import audit_p4_4i_shadow_supervisor_failure_evidence as audit


def test_p4_4i_receipt_binds_live_failure_without_claiming_successor_proof() -> None:
    # P4.4I is merged historical evidence; P4.4J owns current-head enforcement.
    receipt = audit.audit(check_live=False)
    live = receipt["prior_live_evidence"]
    correction = receipt["correction_scope"]
    governance = receipt["review_governance"]

    assert live["run_id"] == 36111105935
    assert live["exact_main_sha"] == audit.BASE_MAIN
    assert live["supervisor_returncode"] == 1
    assert live["inner_receipt_reasons"] == ["SOURCE_CHAIN_PENDING:STARTED"]
    assert live["exact_child_exception"] == "UNKNOWN_NOT_DURABLY_PRESERVED"
    assert live["source_exception_inferred"] is False
    assert live["live_successor_proof_complete"] is False
    assert live["owner_live_authorization_consumed"] is True
    assert live["retry_count"] == 0

    assert correction["offline_evidence_integrity_only"] is True
    assert correction["provider_acquisition_during_pr"] is False
    assert correction["provider_request_count_during_pr"] == 0
    assert correction["workflow_dispatch_during_pr"] is False
    assert correction["current_shadow_live_run_during_pr"] is False
    assert correction["workflow_yaml_changed"] is False
    assert correction["caller_migration_authorized"] is False
    assert correction["workflow_retirement_authorized"] is False
    assert correction["new_authority_added"] is False
    assert correction["retry_of_run_36111105935"] is False

    assert governance["source_review_counter_while_unmerged"] == "1/5"
    assert governance["source_review_counter_if_merged"] == "2/5"
    assert governance["mandatory_source_reread_after_merge"] is False
    assert governance["p4_4_overall_complete"] is False
    assert governance["architecture_checkpoint_e_complete"] is False


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("prior_live_evidence", "supervisor_returncode"), 0),
        (("prior_live_evidence", "exact_child_exception"), "INFERRED_PROVIDER_ERROR"),
        (("prior_live_evidence", "live_successor_proof_complete"), True),
        (("correction_scope", "provider_request_count_during_pr"), 1),
        (("correction_scope", "workflow_dispatch_during_pr"), True),
        (("correction_scope", "workflow_yaml_changed"), True),
        (("correction_scope", "caller_migration_authorized"), True),
        (("correction_scope", "workflow_retirement_authorized"), True),
        (("review_governance", "mandatory_source_reread_after_merge"), True),
        (("review_governance", "p4_4_overall_complete"), True),
    ],
)
def test_self_rehashed_semantic_mutations_fail_closed(path, replacement) -> None:
    mutated = copy.deepcopy(audit.expected_receipt())
    target = mutated
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    mutated["canonical_sha256"] = audit._canonical_sha(mutated)

    with pytest.raises(audit.P44IReviewError):
        audit._validate_receipt(mutated)


def test_current_architecture_identities_remain_frozen() -> None:
    receipt = audit.expected_receipt()
    assert receipt["workflow_tree_sha1"] == "d58f71b9ac653c8762f1d9b18eede15755ee1a76"
    assert receipt["workflow_count"] == 38
    assert receipt["workflow_evolution_ledger_sha256"] == (
        "b9ee60aa5cfa63080159cae839ca82b5662fdfbfe70a91055392a1728ed05f7a"
    )
    assert receipt["workflow_evolution_transition_count"] == 6
    assert receipt["p4_3_retirement_ledger_sha256"] == (
        "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
    )
    assert receipt["p4_3_retired_workflow_count"] == 3


def test_historical_changed_path_scope_uses_the_reviewed_p4_4i_head(monkeypatch) -> None:
    calls = []

    def fake_git(*args: str) -> bytes:
        calls.append(args)
        if args[0] == "cat-file":
            return b""
        if args[0] == "diff":
            return ("\n".join(sorted(audit.EXPECTED_CHANGED_PATHS)) + "\n").encode()
        if args[0] == "show":
            return b"frozen historical source"
        raise AssertionError(args)

    monkeypatch.setattr(audit, "_git", fake_git)
    monkeypatch.setattr(
        audit,
        "_source_identity",
        lambda _path, ref: audit.SERVICE_BEFORE if ref == audit.BASE_MAIN else audit.SERVICE_AFTER,
    )
    assert audit._historical_changed_paths() == audit.EXPECTED_CHANGED_PATHS
    assert (
        "diff",
        "--name-only",
        f"{audit.BASE_MAIN}...{audit.P44I_REVIEWED_HEAD}",
    ) in calls
    assert all("HEAD" not in arg for call in calls for arg in call)


def test_historical_changed_path_scope_rejects_source_identity_drift(monkeypatch) -> None:
    def fake_git(*args: str) -> bytes:
        if args[0] in {"cat-file", "diff"}:
            if args[0] == "diff":
                return ("\n".join(sorted(audit.EXPECTED_CHANGED_PATHS)) + "\n").encode()
            return b""
        raise AssertionError(args)

    monkeypatch.setattr(audit, "_git", fake_git)
    monkeypatch.setattr(audit, "_source_identity", lambda *_args: {"unexpected": "identity"})
    with pytest.raises(audit.P44IReviewError, match="historical before-source identity drifted"):
        audit._historical_changed_paths()


def test_historical_changed_paths_do_not_fabricate_scope_when_objects_are_missing(monkeypatch) -> None:
    def missing_object(*args: str) -> bytes:
        raise audit.P44IReviewError("historical object missing")

    monkeypatch.setattr(audit, "_git", missing_object)
    assert audit._historical_changed_paths() is None


def test_explicit_live_audit_remains_bound_to_the_original_p4_4i_base(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)

    def current_git(*args: str) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return b"9ff94e22a161373373900a3e7744311aaab29089"
        if args == ("rev-parse", "origin/main"):
            return b"301f5d13ca8f60392c52d8ff132e8740b9b979bb"
        raise AssertionError(args)

    monkeypatch.setattr(audit, "_git", current_git)
    with pytest.raises(audit.P44IReviewError, match="origin/main moved from exact P4.4I base"):
        audit._verify_base()
