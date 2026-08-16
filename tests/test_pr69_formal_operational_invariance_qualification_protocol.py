import hashlib

import domain.pr69_formal_operational_invariance_qualification_protocol as p
import domain.pr69_source_local_time_basis_resolution_protocol as pr122


def _protocol():
    return p.build_pr69_formal_operational_invariance_qualification_protocol()


def test_protocol_revalidates_exact_upstream_and_canonical_identity():
    protocol = _protocol()
    raw = p.canonical_pr69_formal_operational_invariance_qualification_protocol_bytes()

    assert protocol["protocol_state"] == (
        "PRE_REGISTERED_NOT_EXECUTED_PR69_FORMAL_OPERATIONAL_INVARIANCE_UNQUALIFIED"
    )
    assert protocol["protocol_scope"] == (
        "PRE_REGISTERED_PR69_REFERENCE_ONLY_FORMAL_OPERATIONAL_INVARIANCE_PROOF"
    )
    assert len(raw) == p.PROTOCOL_SIZE == 5841
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == (
        "d4cacdc85f8d2be5746853a89c00fe8d6521075234a9009469a6385f346be513"
    )


def test_scope_is_pr69_reference_only_and_excludes_fotmob_candidate_rows():
    scope = _protocol()["frozen_scope"]

    assert scope["pr69_source_file_count"] == 66
    assert scope["pr69_source_total_bytes"] == 10006877
    assert scope["pr69_source_fixture_count"] == 21226
    assert scope["fotmob_candidate_rows_in_scope"] is False
    assert scope["fotmob_candidate_time_basis_assessed"] is False


def test_assumption_proof_must_exist_before_operation_checks():
    assumptions = _protocol()["assumption_proof_contract"]

    assert assumptions["must_precede_operation_proof"] is True
    assert assumptions["must_be_admissible_evidence_backed"] is True
    assert (
        assumptions[
            "must_cover_every_pr69_reference_timestamp_and_pr69_target_boundary"
        ]
        is True
    )
    assert assumptions["must_define_effective_period_and_version_scope"] is True
    assert assumptions["unbounded_or_plausibility_only_offset_envelope_forbidden"] is True
    assert assumptions["country_league_venue_or_cross_source_guessing_forbidden"] is True
    assert assumptions["no_proven_transformation_family_means_fail_before_operation_checks"] is True


def test_protocol_does_not_pre_assume_global_or_dst_offset_model():
    assumptions = _protocol()["assumption_proof_contract"]

    assert assumptions["may_use_global_additive_offset_only_when_proven"] is True
    assert (
        assumptions[
            "may_use_piecewise_or_time_varying_offsets_only_when_each_transition_and_bound_is_proven"
        ]
        is True
    )
    assert assumptions["result_fit_or_equal_observed_output_as_assumption_evidence_forbidden"] is True


def test_every_pr122_time_sensitive_reference_operation_is_required():
    operations = _protocol()["operation_proof_contract"]

    assert operations["quantifier"] == (
        "FOR_EVERY_PR69_ROW_AND_EVERY_TRANSFORMATION_IN_THE_PROVEN_"
        "ADMISSIBLE_REFERENCE_FAMILY"
    )
    required = {
        "strict_prior_membership_invariance",
        "form_ordering_and_fixture_id_tiebreak_invariance",
        "elo_ordering_and_fixture_id_tiebreak_invariance",
        "most_recent_prior_fixture_invariance",
        "integer_datetime_delta_days_invariance",
        "home_minus_away_rest_difference_invariance",
        "fatigue_bucket_invariance",
    }
    assert all(operations[key] is True for key in required)
    assert operations["zero_ordering_disagreement_alone_is_insufficient"] is True
    assert operations["equal_numeric_feature_outputs_alone_are_insufficient"] is True


def test_day_boundary_and_fatigue_proof_is_universal_not_aggregate():
    operations = _protocol()["operation_proof_contract"]

    assert operations[
        "datetime_delta_days_must_be_identical_for_every_allowed_transformed_delta"
    ] is True
    assert operations[
        "rest_difference_must_be_identical_for_every_allowed_home_away_combination"
    ] is True
    assert operations[
        "fatigue_bucket_must_be_identical_for_every_allowed_rest_difference"
    ] is True
    assert operations[
        "global_additive_offset_cancellation_may_be_used_only_after_global_additive_assumption_is_proven"
    ] is True


def test_execution_cannot_use_fotmob_candidate_results_to_resolve_reference_gate():
    protocol = _protocol()
    accounting = protocol["execution_accounting_contract"]

    assert accounting["must_report_pr69_reference_rows_considered"] is True
    assert accounting["must_report_pr69_target_boundaries_considered"] is True
    assert accounting[
        "must_not_inspect_fotmob_candidate_rows_for_reference_invariance_result"
    ] is True
    assert (
        "DO_NOT_INSPECT_OR_COMPARE_FOTMOB_CANDIDATE_ROWS_IN_THIS_REFERENCE_INVARIANCE_EXECUTION"
        in protocol["forbidden_shortcuts"]
    )


def test_status_vocabulary_is_only_frozen_pr122_vocabulary():
    assert set(p.QUALIFICATION_STATUS_VOCABULARY).issubset(
        set(pr122.QUALIFICATION_STATUS_VOCABULARY)
    )
    assert "QUALIFIED_FORMAL_OPERATIONAL_INVARIANCE_WITHOUT_NAMED_TIMEZONE" in (
        p.QUALIFICATION_STATUS_VOCABULARY
    )
    assert "BLOCKED_INVARIANCE_ASSUMPTIONS_UNPROVEN" in (
        p.QUALIFICATION_STATUS_VOCABULARY
    )


def test_execution_accounting_requires_counterexamples_and_no_training():
    accounting = _protocol()["execution_accounting_contract"]

    assert accounting["must_report_each_operation_gate_pass_fail_not_reached"] is True
    assert accounting["must_report_counterexample_identity_for_any_failed_gate"] is True
    assert accounting["must_preserve_raw_source_times_without_rewrite"] is True
    assert accounting["must_not_train_or_tune_model_from_invariance_execution"] is True


def test_pre_registration_grants_zero_downstream_authority():
    protocol = _protocol()

    assert protocol["next_required_boundary"] == (
        "EXECUTE_REVIEWED_PR69_FORMAL_OPERATIONAL_INVARIANCE_QUALIFICATION"
    )
    assert set(protocol["safety"]) == p.SAFETY_KEYS
    assert all(value is False for value in protocol["safety"].values())
