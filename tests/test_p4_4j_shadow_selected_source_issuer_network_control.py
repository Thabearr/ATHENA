from __future__ import annotations

import copy

import pytest

from scripts import audit_p4_4j_shadow_selected_source_issuer_network_control as audit


def test_p4_4j_receipt_binds_exact_live_blocker_and_offline_fix() -> None:
    receipt = audit.audit(check_live=False)
    live = receipt["prior_live_evidence"]
    correction = receipt["correction_scope"]
    governance = receipt["review_governance"]

    assert live["run_id"] == 36119049997
    assert live["exact_main_sha"] == audit.BASE_MAIN
    assert live["request"]["timezone"] == "Africa/Lagos"
    assert live["supervisor_returncode"] == 1
    assert live["failure_classification"] == "CURRENT_SHADOW_SUPERVISOR_NONZERO"
    assert live["terminal_receipt_accepted"] is False
    assert live["provisional_marker_observed"] is True
    assert live["failure_text_classification"] == (
        "SELECTED_SOURCE_ISSUER_REJECTED_EXECUTE_LIVE_NETWORK_KEYWORD"
    )
    assert live["exception_inferred"] is False
    assert live["owner_authorization_consumed"] is True
    assert live["retry_count"] == 0
    assert live["live_successor_blocker_open"] is True

    assert correction["selected_issuer_accepts_execute_live_network_keyword"] is True
    assert correction["caller_network_control_value_preserved"] is True
    assert correction["false_does_not_become_true"] is True
    assert correction["default_network_control_remains_true"] is True
    assert correction["selected_date_validation_order_and_horizon_unchanged"] is True
    assert correction["exact_no_fixtures_skip_semantics_unchanged"] is True
    assert correction["other_source_failures_propagate"] is True
    assert correction["monkeypatch_restoration_unconditional"] is True
    assert correction["provider_acquisition_during_pr"] is False
    assert correction["provider_request_count_during_pr"] == 0
    assert correction["workflow_dispatch_during_pr"] is False
    assert correction["live_proof_during_pr"] is False
    assert correction["live_retry_during_pr"] is False
    assert correction["workflow_yaml_changed"] is False
    assert correction["workflow_evolution_transition_added"] is False
    assert correction["caller_migration"] is False
    assert correction["retirement"] is False
    assert correction["new_authority"] is False
    assert correction["wager_placed"] is False
    assert correction["live_successor_proof_remains_open"] is True

    assert governance["source_review_counter_while_unmerged"] == "2/5"
    assert governance["source_review_counter_if_merged"] == "3/5"
    assert governance["mandatory_source_reread_after_merge"] is False
    assert governance["p4_4_overall_complete"] is False
    assert governance["architecture_checkpoint_e_complete"] is False


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("prior_live_evidence", "supervisor_returncode"), 0),
        (("prior_live_evidence", "exception_inferred"), True),
        (("prior_live_evidence", "live_successor_proof_complete"), True),
        (("correction_scope", "false_does_not_become_true"), False),
        (("correction_scope", "provider_request_count_during_pr"), 1),
        (("correction_scope", "workflow_dispatch_during_pr"), True),
        (("correction_scope", "workflow_yaml_changed"), True),
        (("correction_scope", "caller_migration"), True),
        (("correction_scope", "retirement"), True),
        (("review_governance", "mandatory_source_reread_after_merge"), True),
        (("review_governance", "p4_4_overall_complete"), True),
    ],
)
def test_self_rehashed_scope_mutations_fail_closed(path, replacement) -> None:
    mutated = copy.deepcopy(audit.expected_receipt())
    target = mutated
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    mutated["canonical_sha256"] = audit._canonical_sha(mutated)

    with pytest.raises(audit.P44JReviewError):
        audit._validate_receipt(mutated)


def test_source_before_after_and_architecture_backlinks_are_frozen() -> None:
    receipt = audit.expected_receipt()
    assert receipt["source_identity"]["path"] == audit.SOURCE_PATH
    assert receipt["source_identity"]["before"] == audit.SOURCE_BEFORE
    assert receipt["source_identity"]["after"] == audit.SOURCE_AFTER
    assert receipt["prior_architecture"]["p4_4h_receipt_sha256"] == audit.P44H_RECEIPT_SHA256
    assert receipt["prior_architecture"]["p4_4i_receipt_sha256"] == audit.P44I_RECEIPT_SHA256
    assert receipt["prior_architecture"]["workflow_count"] == 38
    assert receipt["prior_architecture"]["workflow_evolution_transition_count"] == 6
    assert receipt["prior_architecture"]["p4_3_retired_workflow_count"] == 3

    historical = receipt["p4_4i_historical_audit_compatibility"]
    assert historical["reviewed_head"] == "9ff94e22a161373373900a3e7744311aaab29089"
    assert historical["immutable_receipt_unchanged"] is True
    assert historical["historical_mode_skips_old_current_main_requirement"] is True
    assert historical["explicit_live_mode_remains_strict"] is True
    assert historical["source_identities"][audit.P44I_AUDIT_PATH] == {
        "before": audit.P44I_AUDIT_BEFORE,
        "after": audit.P44I_AUDIT_AFTER,
    }
    assert historical["source_identities"][audit.P44I_TEST_PATH] == {
        "before": audit.P44I_TEST_BEFORE,
        "after": audit.P44I_TEST_AFTER,
    }


def test_exact_changed_file_envelope_has_no_workflow_or_provider_code() -> None:
    assert audit.EXPECTED_CHANGED_PATHS == {
        "artifacts/architecture/p4_4j_shadow_selected_source_issuer_network_control_v1.json",
        "docs/architecture/athena_run_workflow.md",
        "scripts/audit_p4_4i_shadow_supervisor_failure_evidence.py",
        "scripts/audit_p4_4j_shadow_selected_source_issuer_network_control.py",
        "scripts/execute_current_shadow_request.py",
        "tests/test_execute_current_shadow_request.py",
        "tests/test_p4_4i_shadow_supervisor_failure_evidence.py",
        "tests/test_p4_4j_shadow_selected_source_issuer_network_control.py",
    }
    assert not any(path.startswith(".github/workflows/") for path in audit.EXPECTED_CHANGED_PATHS)
