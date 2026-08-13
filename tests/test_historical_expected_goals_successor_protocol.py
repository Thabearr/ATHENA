from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

from domain.historical_expected_goals_successor_protocol import (
    CALIBRATION_BINS,
    EVALUATION_LABEL,
    EVALUATION_SEASONS,
    MODEL_FAMILY,
    PR69_CANONICAL_SHA256,
    PR69_SOURCE_CORPUS_SHA256,
    PR70_VALIDATION_SHA256,
    PR71_RECEIPT_SHA256,
    PROTOCOL_ID,
    PROTOCOL_SCOPE,
    TRAIN_SEASONS,
    HistoricalExpectedGoalsSuccessorProtocolError,
    build_historical_expected_goals_successor_protocol,
    canonical_historical_expected_goals_successor_protocol_bytes,
    revalidate_historical_expected_goals_successor_protocol,
    sha256_historical_expected_goals_successor_protocol,
)


RECEIPT_PATH = Path(
    "artifacts/research-manifests/"
    "historical-expected-goals-real-corpus-validation-receipt-v1.json"
)
MODULE_PATH = Path("domain/historical_expected_goals_successor_protocol.py")


def _receipt_bytes() -> bytes:
    return RECEIPT_PATH.read_bytes()


def _protocol():
    return build_historical_expected_goals_successor_protocol(
        receipt_bytes=_receipt_bytes()
    )


def test_exact_pr71_receipt_is_required_and_accepted() -> None:
    raw = _receipt_bytes()
    assert hashlib.sha256(raw).hexdigest() == PR71_RECEIPT_SHA256
    protocol = build_historical_expected_goals_successor_protocol(receipt_bytes=raw)
    assert protocol.evidence_receipt_sha256 == PR71_RECEIPT_SHA256
    assert protocol.source_corpus_sha256 == PR69_SOURCE_CORPUS_SHA256
    assert protocol.pr69_canonical_sha256 == PR69_CANONICAL_SHA256
    assert protocol.pr70_validation_sha256 == PR70_VALIDATION_SHA256


def test_receipt_byte_mutation_fails_closed() -> None:
    raw = bytearray(_receipt_bytes())
    raw[-2] = ord(" ") if raw[-2] != ord(" ") else ord("\t")
    with pytest.raises(
        HistoricalExpectedGoalsSuccessorProtocolError,
        match="receipt SHA-256 mismatch",
    ):
        build_historical_expected_goals_successor_protocol(receipt_bytes=bytes(raw))


def test_receipt_type_must_be_exact_immutable_bytes() -> None:
    with pytest.raises(HistoricalExpectedGoalsSuccessorProtocolError):
        build_historical_expected_goals_successor_protocol(  # type: ignore[arg-type]
            receipt_bytes=bytearray(_receipt_bytes())
        )


def test_protocol_identity_and_scope_are_frozen() -> None:
    protocol = _protocol()
    assert protocol.schema_version == 1
    assert protocol.protocol_id == PROTOCOL_ID
    assert protocol.scope == PROTOCOL_SCOPE
    assert protocol.model_family == MODEL_FAMILY
    assert protocol.response_distribution == "POISSON"
    assert protocol.link_function == "LOG"
    assert protocol.coefficient_sharing == "NONE_HOME_AND_AWAY_FIT_SEPARATELY"


def test_feature_set_order_and_transforms_are_frozen() -> None:
    specs = _protocol().predictors
    assert [item.name for item in specs] == [
        "intercept",
        "home_elo_centered_scaled",
        "away_elo_centered_scaled",
        "home_form_centered",
        "away_form_centered",
        "fatigue_raw",
    ]
    assert specs[0].transform == "CONSTANT_ONE"
    assert specs[1].source_feature_id == "home_elo"
    assert specs[1].center == 1500.0
    assert specs[1].scale == 400.0
    assert specs[2].source_feature_id == "away_elo"
    assert specs[2].center == 1500.0
    assert specs[2].scale == 400.0
    assert specs[3].source_feature_id == "home_form"
    assert specs[3].center == 0.5
    assert specs[3].scale is None
    assert specs[4].source_feature_id == "away_form"
    assert specs[4].center == 0.5
    assert specs[4].scale is None
    assert specs[5].source_feature_id == "fatigue"
    assert specs[5].transform == "IDENTITY"
    assert specs[5].center is None
    assert specs[5].scale is None


def test_chronological_split_is_frozen_disjoint_and_not_called_untouched() -> None:
    protocol = _protocol()
    assert protocol.train_seasons == TRAIN_SEASONS == (
        "2020-21",
        "2021-22",
        "2022-23",
        "2023-24",
    )
    assert protocol.evaluation_seasons == EVALUATION_SEASONS == (
        "2024-25",
        "2025-26",
    )
    assert not (set(protocol.train_seasons) & set(protocol.evaluation_seasons))
    assert protocol.evaluation_label == EVALUATION_LABEL
    assert "NOT_UNTOUCHED_HOLDOUT" in protocol.evaluation_label
    assert protocol.prospective_requirement == (
        "PRODUCTION_APPROVAL_REQUIRES_FUTURE_NOT_YET_OBSERVED_EVIDENCE_AFTER_PROTOCOL_FREEZE"
    )


def test_eligibility_requires_both_replay_component_paths() -> None:
    assert _protocol().eligibility_rule == (
        "PR69_FORM_PATH_COMPONENT_ELIGIBLE_AND_ELO_FALLBACK_COMPONENT_ELIGIBLE"
    )


def test_fitting_algorithm_is_frozen_without_tuning_or_refit() -> None:
    fitting = _protocol().fitting
    assert fitting.algorithm == "DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1"
    assert fitting.objective == "SUM_INDEPENDENT_POISSON_NEGATIVE_LOG_LIKELIHOOD"
    assert fitting.regularization == "NONE"
    assert fitting.response_fit_order == ("HOME_GOALS", "AWAY_GOALS")
    assert fitting.initial_intercept == "LOG_TRAINING_RESPONSE_MEAN"
    assert fitting.initial_non_intercept_coefficient == 0.0
    assert fitting.max_iterations == 200
    assert fitting.gradient_inf_norm_tolerance == 1e-8
    assert fitting.backtracking_factor == 0.5
    assert fitting.minimum_step == 2.0 ** -20
    assert fitting.maximum_abs_linear_predictor == 20.0
    assert fitting.linear_solve_pivot_tolerance == 1e-12
    assert fitting.coefficient_rounding_places == 12
    assert fitting.hyperparameter_search_authorized is False
    assert fitting.refit_after_evaluation_authorized is False


def test_evaluation_contract_compares_all_legacy_references() -> None:
    evaluation = _protocol().evaluation
    assert evaluation.primary_metric == "MEAN_JOINT_POISSON_NEGATIVE_LOG_LIKELIHOOD"
    assert evaluation.legacy_comparators == (
        "PR68_FORM_COMPONENT",
        "PR68_ELO_FALLBACK_COMPONENT",
        "PR68_FROZEN_CONSTANT_BASELINE",
        "STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_BASELINE",
    )
    assert evaluation.breakdowns == ("SEASON", "IDENTITY_LEAGUE")
    assert evaluation.calibration_bins == CALIBRATION_BINS
    assert evaluation.approval_threshold is None
    assert evaluation.production_decision == "REPORT_ONLY_NO_AUTOMATIC_APPROVAL"


def test_calibration_bins_retain_pr70_boundaries_and_open_tail() -> None:
    assert CALIBRATION_BINS == (
        (0.0, 0.5),
        (0.5, 1.0),
        (1.0, 1.5),
        (1.5, 2.0),
        (2.0, 2.5),
        (2.5, 3.0),
        (3.0, None),
    )


def test_all_safety_flags_are_exact_false() -> None:
    protocol = _protocol()
    assert protocol.safety
    assert all(type(value) is bool and value is False for value in protocol.safety.values())
    assert protocol.safety["successor_model_trained"] is False
    assert protocol.safety["expected_goals_transform_approved"] is False
    assert protocol.safety["probability_inference_authorized"] is False
    assert protocol.safety["pricing_authorized"] is False
    assert protocol.safety["selection_authorized"] is False
    assert protocol.safety["bet_authorized"] is False


def test_protocol_constructor_rejects_safety_promotion() -> None:
    protocol = _protocol()
    mutated_safety = dict(protocol.safety)
    mutated_safety["successor_model_trained"] = True
    with pytest.raises(HistoricalExpectedGoalsSuccessorProtocolError):
        dataclasses.replace(protocol, safety=mutated_safety)


def test_protocol_constructor_rejects_split_mutation() -> None:
    protocol = _protocol()
    with pytest.raises(HistoricalExpectedGoalsSuccessorProtocolError):
        dataclasses.replace(protocol, train_seasons=protocol.train_seasons + ("2024-25",))


def test_protocol_constructor_rejects_predictor_mutation() -> None:
    protocol = _protocol()
    mutated = dataclasses.replace(protocol.predictors[1], scale=800.0)
    with pytest.raises(HistoricalExpectedGoalsSuccessorProtocolError):
        dataclasses.replace(protocol, predictors=(protocol.predictors[0], mutated, *protocol.predictors[2:]))


def test_canonical_bytes_are_deterministic_utf8_json_with_one_newline() -> None:
    protocol = _protocol()
    first = canonical_historical_expected_goals_successor_protocol_bytes(protocol)
    second = canonical_historical_expected_goals_successor_protocol_bytes(_protocol())
    assert first == second
    assert first.endswith(b"\n")
    assert not first.endswith(b"\n\n")
    assert sha256_historical_expected_goals_successor_protocol(protocol) == hashlib.sha256(first).hexdigest()


def test_full_revalidator_requires_exact_object_and_bytes() -> None:
    raw = _receipt_bytes()
    protocol = _protocol()
    canonical = canonical_historical_expected_goals_successor_protocol_bytes(protocol)
    revalidate_historical_expected_goals_successor_protocol(
        receipt_bytes=raw,
        protocol=protocol,
        protocol_bytes=canonical,
    )
    with pytest.raises(
        HistoricalExpectedGoalsSuccessorProtocolError,
        match="canonical bytes mismatch",
    ):
        revalidate_historical_expected_goals_successor_protocol(
            receipt_bytes=raw,
            protocol=protocol,
            protocol_bytes=canonical + b" ",
        )


def test_protocol_has_no_learned_coefficients_or_approval_threshold() -> None:
    payload = _protocol().to_dict()
    serialized_keys = str(payload).casefold()
    assert "home_coefficients" not in serialized_keys
    assert "away_coefficients" not in serialized_keys
    assert payload["evaluation"]["approval_threshold"] is None


def test_protocol_module_has_no_io_network_database_or_model_runtime_dependencies() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert not imported_roots & {
        "sqlite3",
        "requests",
        "urllib",
        "pandas",
        "numpy",
        "scipy",
        "sklearn",
        "joblib",
    }
    forbidden_runtime_names = {
        "build_score_matrix",
        "ProbabilityEngine",
        "SportyBet",
        "price",
        "pricing",
        "selection",
        "bet",
    }
    assert not called_names & forbidden_runtime_names
