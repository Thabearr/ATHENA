from domain.fotmob_utc_native_expected_goals_model_validation_result_review import (
    FAILED_STRONG_CHECK,
    NEXT_REQUIRED_BOUNDARY,
    REVIEW_STATE,
    build_fotmob_utc_native_expected_goals_model_validation_result_review,
    canonical_fotmob_utc_native_expected_goals_model_validation_result_review_bytes,
)


def test_review_pins_exact_execution_and_artifact_identity() -> None:
    review = build_fotmob_utc_native_expected_goals_model_validation_result_review()
    evidence = review["execution_evidence"]
    assert evidence["main_sha"] == "b8ddc00f7529c5533c9da2daad613d997498cbf2"
    assert evidence["run_id"] == 32049714066
    assert evidence["command_comment_id"] == 5318114406
    assert evidence["attempt_comment_id"] == 5318115383
    assert evidence["result_comment_id"] == 5318117332
    assert evidence["artifact"] == {
        "id": 9294215497,
        "name": "fotmob-utc-native-expected-goals-validation-32049714066",
        "size_bytes": 5441951,
        "sha256": "e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5",
    }
    assert evidence["receipt"]["sha256"] == (
        "1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a"
    )
    assert evidence["predictions"]["record_count"] == 6948
    assert evidence["predictions"]["sha256"] == (
        "2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420"
    )


def test_review_records_exact_mixed_signal_reason_without_rewriting_protocol() -> None:
    review = build_fotmob_utc_native_expected_goals_model_validation_result_review()
    signal = review["reviewed_signal"]
    assert review["review_state"] == REVIEW_STATE
    assert signal["strong_check_count"] == 10
    assert signal["strong_checks_passed"] == 9
    assert signal["sole_failed_strong_check"] == FAILED_STRONG_CHECK
    assert signal["pooled_home_wace"]["required_relation_passed"] is False
    assert signal["native_minus_elo_mean_joint_nll"]["evaluation_a"] < 0.0
    assert signal["native_minus_elo_mean_joint_nll"]["evaluation_b_terminal"] < 0.0
    assert signal["native_minus_elo_mean_joint_nll"]["pooled_a_plus_b"] < 0.0
    assert signal["quarter_jackknife_native_minus_elo"]["interval_upper_95"] < 0.0
    report_only = signal["diagnostic_report_only_comparisons"]
    assert report_only["historical_transfer_is_approval_gate"] is False
    assert report_only["no_fatigue_ablation_is_approval_gate"] is False


def test_review_refuses_successor_promotion_and_consumes_seen_holdouts() -> None:
    review = build_fotmob_utc_native_expected_goals_model_validation_result_review()
    decision = review["reviewed_decision"]
    assert decision["positive_predictive_signal_retained_for_research"] is True
    assert decision["native_refit_successor_candidate_approved"] is False
    assert decision["historical_fixed_transfer_promoted_instead"] is False
    assert decision["home_calibration_followup_required"] is True
    assert decision["competition_identity_followup_required"] is True
    assert decision["evaluation_a_and_b_labels_now_consumed_by_review"] is True
    assert decision["retune_on_a_or_b_and_reuse_same_rows_as_fresh_validation_forbidden"] is True
    assert decision["followup_validation_start_not_before_utc"] == "2026-08-15T00:00:00Z"
    assert review["next_required_boundary"] == NEXT_REQUIRED_BOUNDARY


def test_review_keeps_every_downstream_authority_false() -> None:
    review = build_fotmob_utc_native_expected_goals_model_validation_result_review()
    assert review["reviewed_decision"]["automatic_model_approval"] is False
    assert review["runtime_caveats"]["cross_runtime_bit_identity_claimed"] is False
    assert (
        review["runtime_caveats"]["known_pr77_machine_precision_canonicalization_gap_cleared"]
        is False
    )
    assert review["safety"]
    assert all(value is False for value in review["safety"].values())


def test_review_canonical_bytes_are_deterministic() -> None:
    first = canonical_fotmob_utc_native_expected_goals_model_validation_result_review_bytes()
    second = canonical_fotmob_utc_native_expected_goals_model_validation_result_review_bytes()
    assert first == second
    assert first.endswith(b"\n")
