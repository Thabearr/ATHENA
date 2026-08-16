"""Pre-register the PR69 formal operational-invariance qualification.

This protocol is result-free and reference-only. It freezes the exact second
route allowed by PR122 after PR132 established that direct primary clock
semantics remain ambiguous. A later execution may prove that PR69's own
pre-match time-sensitive operations are invariant across every admissible
reference-clock transformation. It must not inspect FotMob candidate rows,
infer a timezone/offset, or authorize PR80/model/probability/pricing/selection/
production/BET use.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_pr80_source_local_time_semantic_equivalence_protocol as pr120
import domain.pr69_primary_time_basis_semantic_qualification_v2 as pr132
import domain.pr69_source_local_time_basis_resolution_protocol as pr122
import domain.prospective_successor_feature_construction_candidate as pr80


SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_PR69_FORMAL_OPERATIONAL_INVARIANCE_QUALIFICATION_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_PR69_REFERENCE_ONLY_FORMAL_OPERATIONAL_INVARIANCE_PROOF"
PROTOCOL_STATE = (
    "PRE_REGISTERED_NOT_EXECUTED_PR69_FORMAL_OPERATIONAL_INVARIANCE_UNQUALIFIED"
)
STACKED_PR132_HEAD_SHA = "f275a7404bbb74ade6ba29c4ec2d7f52d3e21abf"
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_PR69_FORMAL_OPERATIONAL_INVARIANCE_QUALIFICATION"
)

PR132_RECEIPT_SHA256 = "cbdf0bbf9e31d44e0d00125bd10d714272ac6046386cf52f1d9d27b3ab84bb8d"
PR132_RECEIPT_SIZE = 5_422
PR132_RECEIPT_BLOB_SHA = "adc34350074a8cdcd447089e9d64727081a7c3b2"
PR132_QUALIFICATION_BLOB_SHA = "b9a4b109157fa704e65b0aba5c4816e178a3c168"
PR122_PROTOCOL_SHA256 = "d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a"
PR122_PROTOCOL_SIZE = 6_983
PR122_PROTOCOL_BLOB_SHA = "712ce12157ade725a60b24c4557600fc7b06e504"
PR120_PROTOCOL_SHA256 = "a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918"
PR120_PROTOCOL_SIZE = 5_242
PR120_PROTOCOL_BLOB_SHA = "e07616e99c0beaf2a95bcaec96d02616b21c378f"
PR80_CONSTRUCTOR_BLOB_SHA = "9135f056d036fd0207a3daead2599ac2520274be"

PR69_SOURCE_FILE_COUNT = 66
PR69_SOURCE_TOTAL_BYTES = 10_006_877
PR69_SOURCE_FIXTURE_COUNT = 21_226
PR69_SEASONS = (
    "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"
)
MODEL_LEAGUE_CODES = (
    "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
)

SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "calibration_for_production_authorized",
        "expected_goals_production_authorized",
        "expected_goals_transform_approved",
        "market_activation_authorized",
        "model_training_authorized",
        "pr69_source_local_time_basis_resolved",
        "pr80_constructor_input_authorized",
        "pricing_authorized",
        "probability_adjustment_authorized",
        "probability_inference_authorized",
        "production_approval_authorized",
        "score_matrix_authorized",
        "selection_authorized",
        "source_local_time_semantic_equivalence_qualified",
        "successor_candidate_approved",
        "successor_live_inputs_qualified",
    }
)

QUALIFICATION_STATUS_VOCABULARY = (
    "QUALIFIED_FORMAL_OPERATIONAL_INVARIANCE_WITHOUT_NAMED_TIMEZONE",
    "BLOCKED_INVARIANCE_ASSUMPTIONS_UNPROVEN",
    "BLOCKED_ANCESTRY_OR_SOURCE_CORPUS_MISMATCH",
    "BLOCKED_TIME_BASIS_SCOPE_OR_EFFECTIVE_PERIOD_AMBIGUOUS",
)

PROTOCOL_SHA256 = "d4cacdc85f8d2be5746853a89c00fe8d6521075234a9009469a6385f346be513"
PROTOCOL_SIZE = 5_841


class PR69FormalOperationalInvarianceProtocolError(ValueError):
    """Raised when the frozen invariance pre-registration no longer revalidates."""


def _error(message: str) -> PR69FormalOperationalInvarianceProtocolError:
    return PR69FormalOperationalInvarianceProtocolError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("formal invariance protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "stacked_pr132_head_sha": STACKED_PR132_HEAD_SHA,
        "ancestry": {
            "pr132_receipt_sha256": PR132_RECEIPT_SHA256,
            "pr132_receipt_size_bytes": PR132_RECEIPT_SIZE,
            "pr132_receipt_blob_sha": PR132_RECEIPT_BLOB_SHA,
            "pr132_qualification_blob_sha": PR132_QUALIFICATION_BLOB_SHA,
            "pr122_protocol_sha256": PR122_PROTOCOL_SHA256,
            "pr122_protocol_size_bytes": PR122_PROTOCOL_SIZE,
            "pr122_protocol_blob_sha": PR122_PROTOCOL_BLOB_SHA,
            "pr120_protocol_sha256": PR120_PROTOCOL_SHA256,
            "pr120_protocol_size_bytes": PR120_PROTOCOL_SIZE,
            "pr120_protocol_blob_sha": PR120_PROTOCOL_BLOB_SHA,
            "pr80_constructor_blob_sha": PR80_CONSTRUCTOR_BLOB_SHA,
        },
        "frozen_scope": {
            "pr69_source_file_count": PR69_SOURCE_FILE_COUNT,
            "pr69_source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
            "pr69_source_fixture_count": PR69_SOURCE_FIXTURE_COUNT,
            "pr69_seasons": list(PR69_SEASONS),
            "model_league_codes": list(MODEL_LEAGUE_CODES),
            "full_athena_competition_universe_claimed": False,
            "fotmob_candidate_rows_in_scope": False,
            "fotmob_candidate_time_basis_assessed": False,
        },
        "assumption_proof_contract": {
            "must_precede_operation_proof": True,
            "must_be_admissible_evidence_backed": True,
            "must_cover_every_pr69_reference_timestamp_and_pr69_target_boundary": True,
            "must_define_effective_period_and_version_scope": True,
            "must_define_deterministic_mapping_or_offset_schedule": True,
            "may_normalize_named_zone_or_source_rule_to_exact_offset_schedule": True,
            "may_use_global_additive_offset_only_when_proven": True,
            "may_use_piecewise_or_time_varying_offsets_only_when_each_transition_and_bound_is_proven": True,
            "unbounded_or_plausibility_only_offset_envelope_forbidden": True,
            "country_league_venue_or_cross_source_guessing_forbidden": True,
            "result_fit_or_equal_observed_output_as_assumption_evidence_forbidden": True,
            "no_proven_transformation_family_means_fail_before_operation_checks": True,
        },
        "operation_proof_contract": {
            "quantifier": (
                "FOR_EVERY_PR69_ROW_AND_EVERY_TRANSFORMATION_IN_THE_PROVEN_"
                "ADMISSIBLE_REFERENCE_FAMILY"
            ),
            "strict_prior_membership_invariance": True,
            "form_ordering_and_fixture_id_tiebreak_invariance": True,
            "elo_ordering_and_fixture_id_tiebreak_invariance": True,
            "most_recent_prior_fixture_invariance": True,
            "integer_datetime_delta_days_invariance": True,
            "home_minus_away_rest_difference_invariance": True,
            "fatigue_bucket_invariance": True,
            "ordering_interval_must_not_cross_zero_unless_exact_frozen_tiebreak_semantics_resolve_equality": True,
            "datetime_delta_days_must_be_identical_for_every_allowed_transformed_delta": True,
            "rest_difference_must_be_identical_for_every_allowed_home_away_combination": True,
            "fatigue_bucket_must_be_identical_for_every_allowed_rest_difference": True,
            "global_additive_offset_cancellation_may_be_used_only_after_global_additive_assumption_is_proven": True,
            "zero_ordering_disagreement_alone_is_insufficient": True,
            "equal_numeric_feature_outputs_alone_are_insufficient": True,
        },
        "execution_accounting_contract": {
            "must_report_pr69_reference_rows_considered": True,
            "must_report_pr69_target_boundaries_considered": True,
            "must_report_each_operation_gate_pass_fail_not_reached": True,
            "must_report_counterexample_identity_for_any_failed_gate": True,
            "must_preserve_raw_source_times_without_rewrite": True,
            "must_not_train_or_tune_model_from_invariance_execution": True,
            "must_not_inspect_fotmob_candidate_rows_for_reference_invariance_result": True,
        },
        "admissible_evidence": [
            "EXACT_PR132_V2_SEMANTIC_QUALIFICATION_RECEIPT_AND_PRIMARY_CAPTURE_LINEAGE",
            "EXACT_FROZEN_PR69_RAW_SOURCE_BYTES_AND_PR114_HASHED_REBUILD_EVIDENCE",
            "EXACT_PR120_AND_PR80_TIME_OPERATION_SEMANTICS_AS_DEFINITION_ONLY_NOT_CANDIDATE_RESULTS",
            "PRIMARY_SOURCE_TIME_SEMANTICS_WITH_PROVEN_EFFECTIVE_SCOPE",
            "MACHINE_CHECKABLE_REFERENCE_TRANSFORMATION_ASSUMPTION_PROOF_WITH_ADMISSIBLE_PROVENANCE",
        ],
        "forbidden_shortcuts": [
            "DO_NOT_ASSUME_A_FIXED_OFFSET_DST_RULE_OR_NAMED_ZONE_WITHOUT_ADMISSIBLE_EVIDENCE",
            "DO_NOT_TREAT_FOTMOB_EUROPE_OSLO_AS_PR69_REFERENCE_EVIDENCE",
            "DO_NOT_INSPECT_OR_COMPARE_FOTMOB_CANDIDATE_ROWS_IN_THIS_REFERENCE_INVARIANCE_EXECUTION",
            "DO_NOT_INFER_TIME_BASIS_FROM_COUNTRY_LEAGUE_TEAM_VENUE_OR_COMMON_PRACTICE",
            "DO_NOT_USE_EQUAL_ORDERING_OR_EQUAL_FEATURE_VALUES_TO_PROVE_TRANSFORMATION_ASSUMPTIONS",
            "DO_NOT_HIDE_DAY_BOUNDARY_OR_DST_COUNTEREXAMPLES_BEHIND_AGGREGATE_COUNTS",
            "DO_NOT_REWRITE_PR69_PR80_PR120_OR_PR132_SEMANTICS_AFTER_OBSERVING_RESULTS",
            "DO_NOT_AUTHORIZE_MODEL_PROBABILITY_PRICING_SELECTION_PRODUCTION_OR_BET_FROM_PRE_REGISTRATION",
        ],
        "qualification_status_vocabulary": list(QUALIFICATION_STATUS_VOCABULARY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in sorted(SAFETY_KEYS)},
    }


def _verify_upstream() -> None:
    pr132.validate_qualification()
    receipt_raw = pr132.canonical_receipt_bytes()
    if (hashlib.sha256(receipt_raw).hexdigest(), len(receipt_raw)) != (
        PR132_RECEIPT_SHA256,
        PR132_RECEIPT_SIZE,
    ):
        raise _error("PR132 receipt identity changed")
    receipt_path = (
        Path(pr132.__file__).resolve().parents[1]
        / "artifacts"
        / "research-manifests"
        / "pr69-primary-time-basis-semantic-qualification-v2.json"
    )
    if _git_blob_sha(receipt_path) != PR132_RECEIPT_BLOB_SHA:
        raise _error("PR132 checked-in receipt blob changed")
    if _git_blob_sha(Path(pr132.__file__)) != PR132_QUALIFICATION_BLOB_SHA:
        raise _error("PR132 qualification implementation blob changed")
    if pr132.PRIMARY_STATUS != "BLOCKED_TIME_BASIS_SCOPE_OR_EFFECTIVE_PERIOD_AMBIGUOUS":
        raise _error("PR132 direct-route blocker changed")
    if pr132.NEXT_REQUIRED_BOUNDARY != (
        "PRE_REGISTER_REVIEWED_PR69_FORMAL_OPERATIONAL_INVARIANCE_QUALIFICATION_PROTOCOL"
    ):
        raise _error("PR132 next boundary changed")

    if (
        pr122.PROTOCOL_SHA256,
        pr122.PROTOCOL_SIZE,
        _git_blob_sha(Path(pr122.__file__)),
    ) != (
        PR122_PROTOCOL_SHA256,
        PR122_PROTOCOL_SIZE,
        PR122_PROTOCOL_BLOB_SHA,
    ):
        raise _error("PR122 protocol identity changed")
    if (
        pr122.PR69_SOURCE_FILE_COUNT,
        pr122.PR69_SOURCE_TOTAL_BYTES,
        pr122.PR69_SOURCE_FIXTURE_COUNT,
        tuple(pr122.SEASONS),
        tuple(pr122.MODEL_LEAGUE_CODES),
    ) != (
        PR69_SOURCE_FILE_COUNT,
        PR69_SOURCE_TOTAL_BYTES,
        PR69_SOURCE_FIXTURE_COUNT,
        PR69_SEASONS,
        MODEL_LEAGUE_CODES,
    ):
        raise _error("PR122 frozen PR69 scope changed")
    for status in QUALIFICATION_STATUS_VOCABULARY:
        if status not in pr122.QUALIFICATION_STATUS_VOCABULARY:
            raise _error("formal invariance status is outside frozen PR122 vocabulary")

    if (
        pr120.PROTOCOL_SHA256,
        pr120.PROTOCOL_SIZE,
        _git_blob_sha(Path(pr120.__file__)),
    ) != (
        PR120_PROTOCOL_SHA256,
        PR120_PROTOCOL_SIZE,
        PR120_PROTOCOL_BLOB_SHA,
    ):
        raise _error("PR120 time-operation contract identity changed")
    if _git_blob_sha(Path(pr80.__file__)) != PR80_CONSTRUCTOR_BLOB_SHA:
        raise _error("PR80 constructor implementation blob changed")
    if pr80.SOURCE_LOCAL_TIME_BASIS != (
        "SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY"
    ):
        raise _error("PR80 source-local time basis changed")


def build_pr69_formal_operational_invariance_qualification_protocol() -> dict[str, Any]:
    """Return the exact result-free protocol after revalidating frozen ancestry."""
    _verify_upstream()
    return _payload()


def canonical_pr69_formal_operational_invariance_qualification_protocol_bytes() -> bytes:
    protocol = build_pr69_formal_operational_invariance_qualification_protocol()
    raw = _canonical(protocol)
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256 or len(raw) != PROTOCOL_SIZE:
        raise _error("formal invariance protocol differs from frozen canonical identity")
    return raw


__all__ = [
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "QUALIFICATION_STATUS_VOCABULARY",
    "SAFETY_KEYS",
    "PR69FormalOperationalInvarianceProtocolError",
    "build_pr69_formal_operational_invariance_qualification_protocol",
    "canonical_pr69_formal_operational_invariance_qualification_protocol_bytes",
]
