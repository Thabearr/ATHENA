"""Offline implementation of the reviewed FotMob UTC-native xG validation.

This module consumes only the preserved V2 qualification artifact. It validates
the exact reviewed projection, fits/evaluates the five pre-registered model
arms, emits deterministic research predictions/receipt, and grants no
production, probability, pricing, selection, or BET authority.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import platform
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import domain.fotmob_utc_native_expected_goals_model_validation_protocol as protocol_mod
from domain.historical_expected_goals_component_validation import poisson_nll
from domain.historical_expected_goals_successor_candidate import (
    HistoricalExpectedGoalsSuccessorCandidateError,
    _gradient_and_hessian as _historical_gradient_and_hessian,
    _response_nll as _historical_response_nll,
    _solve_linear_system as _historical_solve_linear_system,
)

VALIDATION_ID = "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_V1"
IMPLEMENTATION_STATE = (
    "IMPLEMENTED_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_NOT_EXECUTED"
)
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
)
POST_EXECUTION_REVIEW_BOUNDARY = (
    "REVIEW_EXECUTED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT"
)
PROJECTION_MEMBER = "utc-native-feature-projection-v2.ndjson"
QUALIFICATION_RECEIPT_MEMBER = "qualification-v2-receipt.json"
SOURCE_NAMESPACE = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
FRESHNESS_STATUS = "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"

ARM_NATIVE = "FOTMOB_NATIVE_SAME_FAMILY_REFIT"
ARM_HISTORICAL = "HISTORICAL_FIXED_COEFFICIENT_TRANSFER"
ARM_ELO = "FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM"
ARM_NO_FATIGUE = "FOTMOB_NATIVE_NO_FATIGUE_ABLATION"
ARM_CONSTANT = "TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE"
ARM_ORDER = (ARM_NATIVE, ARM_HISTORICAL, ARM_ELO, ARM_NO_FATIGUE, ARM_CONSTANT)

SAFETY_KEYS = protocol_mod.SAFETY_KEYS


class FotMobUTCNativeExpectedGoalsModelValidationError(RuntimeError):
    """Raised when the reviewed model-validation contract cannot be reproduced."""


def _error(message: str) -> FotMobUTCNativeExpectedGoalsModelValidationError:
    return FotMobUTCNativeExpectedGoalsModelValidationError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise _error(f"{label} must be finite numeric")
    return float(value)


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(f"{label} must be an exact non-negative integer")
    return value


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error(f"{label} must be exact non-empty trimmed text")
    return value


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(SAFETY_KEYS)}


def _protocol() -> dict[str, Any]:
    payload = protocol_mod.build_fotmob_utc_native_expected_goals_model_validation_protocol()
    if payload["next_required_boundary"] != (
        "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    ):
        raise _error("reviewed protocol boundary changed")
    return payload


def _validate_feature(
    feature: Any,
    *,
    label: str,
    allow_missing: bool,
    allowed_statuses: set[str],
) -> float | None:
    if not isinstance(feature, dict):
        raise _error(f"{label} must be an object")
    if set(feature).issuperset({"status", "value"}) is False:
        raise _error(f"{label} must contain status/value")
    status = _exact_text(feature["status"], f"{label}.status")
    if status not in allowed_statuses:
        raise _error(f"{label} status is outside reviewed vocabulary")
    value = feature["value"]
    if value is None:
        if not allow_missing or status != "MISSING":
            raise _error(f"{label} null value/status mismatch")
        return None
    if status == "MISSING":
        raise _error(f"{label} MISSING may not carry numeric value")
    return _finite(value, f"{label}.value")


def _validated_projection_row(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("projection row must be an object")
    required = {
        "schema_version",
        "source_namespace",
        "fixture_identifier",
        "kickoff_utc",
        "home_team_identifier",
        "away_team_identifier",
        "home_goals",
        "away_goals",
        "home_form",
        "away_form",
        "home_elo",
        "away_elo",
        "fatigue",
        "historical_live_data_freshness",
        "evidence_sha256",
        "evidence_reference",
    }
    if not required.issubset(value):
        raise _error("projection row required fields changed")
    if value["schema_version"] != 1 or value["source_namespace"] != SOURCE_NAMESPACE:
        raise _error("projection row identity changed")
    fixture_id = _exact_text(value["fixture_identifier"], "fixture_identifier")
    kickoff = _exact_text(value["kickoff_utc"], "kickoff_utc")
    if not kickoff.endswith("Z") or len(kickoff) < 20:
        raise _error("kickoff_utc must be canonical UTC Z text")
    home_team = _exact_text(value["home_team_identifier"], "home_team_identifier")
    away_team = _exact_text(value["away_team_identifier"], "away_team_identifier")
    if home_team == away_team:
        raise _error("fixture may not use one team twice")
    home_goals = _nonnegative_int(value["home_goals"], "home_goals")
    away_goals = _nonnegative_int(value["away_goals"], "away_goals")

    home_form = _validate_feature(
        value["home_form"],
        label="home_form",
        allow_missing=True,
        allowed_statuses={"MISSING", "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"},
    )
    away_form = _validate_feature(
        value["away_form"],
        label="away_form",
        allow_missing=True,
        allowed_statuses={"MISSING", "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"},
    )
    fatigue = _validate_feature(
        value["fatigue"],
        label="fatigue",
        allow_missing=True,
        allowed_statuses={"MISSING", "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"},
    )
    home_elo = _validate_feature(
        value["home_elo"],
        label="home_elo",
        allow_missing=False,
        allowed_statuses={
            "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION",
            "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
        },
    )
    away_elo = _validate_feature(
        value["away_elo"],
        label="away_elo",
        allow_missing=False,
        allowed_statuses={
            "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION",
            "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
        },
    )
    if value["home_elo"].get("rating_component") != "OVERALL":
        raise _error("home Elo must remain OVERALL")
    if value["away_elo"].get("rating_component") != "OVERALL":
        raise _error("away Elo must remain OVERALL")

    freshness = value["historical_live_data_freshness"]
    if (
        not isinstance(freshness, dict)
        or freshness.get("status") != FRESHNESS_STATUS
        or freshness.get("value") is not None
    ):
        raise _error("historical live freshness must remain blocked/null")

    evidence_sha = _exact_text(value["evidence_sha256"], "evidence_sha256")
    if len(evidence_sha) != 64 or any(ch not in "0123456789abcdef" for ch in evidence_sha):
        raise _error("evidence_sha256 malformed")
    evidence_reference = _exact_text(value["evidence_reference"], "evidence_reference")

    return {
        "fixture_identifier": fixture_id,
        "kickoff_utc": kickoff,
        "home_team_identifier": home_team,
        "away_team_identifier": away_team,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "home_form": home_form,
        "away_form": away_form,
        "home_elo": home_elo,
        "away_elo": away_elo,
        "fatigue": fatigue,
        "evidence_sha256": evidence_sha,
        "evidence_reference": evidence_reference,
    }


def _parse_projection(raw: bytes) -> tuple[dict[str, Any], ...]:
    if type(raw) is not bytes or not raw:
        raise _error("projection must be exact non-empty bytes")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in raw.splitlines(keepends=True):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("projection contains malformed JSON") from exc
        if line != _canonical(value):
            raise _error("projection rows must remain canonical JSON")
        row = _validated_projection_row(value)
        fixture_id = row["fixture_identifier"]
        if fixture_id in seen:
            raise _error("duplicate fixture identity in projection")
        seen.add(fixture_id)
        rows.append(row)
    return tuple(rows)


def _complete(row: Mapping[str, Any]) -> bool:
    return all(row[field] is not None for field in ("home_form", "away_form", "fatigue"))


def _membership_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    ordered = sorted(rows, key=lambda item: (item["kickoff_utc"], item["fixture_identifier"]))
    return "".join(
        f"{row['kickoff_utc']}\t{row['fixture_identifier']}\n" for row in ordered
    ).encode("utf-8")


def _population(rows: Sequence[dict[str, Any]], start: str, end: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        sorted(
            (row for row in rows if start <= row["kickoff_utc"] < end),
            key=lambda item: (item["kickoff_utc"], item["fixture_identifier"]),
        )
    )


def _prepare_populations(
    rows: Sequence[dict[str, Any]], protocol: Mapping[str, Any]
) -> dict[str, tuple[dict[str, Any], ...]]:
    complete = tuple(
        sorted(
            (row for row in rows if _complete(row)),
            key=lambda item: (item["kickoff_utc"], item["fixture_identifier"]),
        )
    )
    split = protocol["chronological_split_contract"]
    train = _population(complete, split["train"]["start_inclusive"], split["train"]["end_exclusive"])
    eval_a = _population(
        complete,
        split["evaluation_a"]["start_inclusive"],
        split["evaluation_a"]["end_exclusive"],
    )
    eval_b = _population(
        complete,
        split["evaluation_b_terminal"]["start_inclusive"],
        split["evaluation_b_terminal"]["end_exclusive"],
    )
    pooled = tuple(sorted(eval_a + eval_b, key=lambda item: (item["kickoff_utc"], item["fixture_identifier"])))
    populations = {
        "ALL_COMPLETE": complete,
        "TRAIN": train,
        "EVALUATION_A": eval_a,
        "EVALUATION_B_TERMINAL": eval_b,
        "POOLED_A_PLUS_B": pooled,
    }
    contract = protocol["common_population_contract"]
    expected = {
        "ALL_COMPLETE": (contract["all_complete_rows"], contract["all_complete_membership_sha256"]),
        "TRAIN": (contract["train_rows"], contract["train_membership_sha256"]),
        "EVALUATION_A": (contract["evaluation_a_rows"], contract["evaluation_a_membership_sha256"]),
        "EVALUATION_B_TERMINAL": (contract["evaluation_b_rows"], contract["evaluation_b_membership_sha256"]),
        "POOLED_A_PLUS_B": (contract["pooled_evaluation_rows"], contract["pooled_evaluation_membership_sha256"]),
    }
    for key, population in populations.items():
        actual = (len(population), _sha256(_membership_bytes(population)))
        if actual != expected[key]:
            raise _error(f"{key} population count/hash differs from reviewed protocol")
    if len(rows) - len(complete) != protocol["frozen_input_contract"]["dropped_row_count"]:
        raise _error("complete-case missingness count changed")
    return populations


def _full_predictor(row: Mapping[str, Any]) -> tuple[float, ...]:
    if not _complete(row):
        raise _error("numeric predictor requested for incomplete row")
    return (
        1.0,
        (float(row["home_elo"]) - 1500.0) / 400.0,
        (float(row["away_elo"]) - 1500.0) / 400.0,
        float(row["home_form"]) - 0.5,
        float(row["away_form"]) - 0.5,
        float(row["fatigue"]),
    )


def _subset(matrix: Sequence[tuple[float, ...]], indices: tuple[int, ...]) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(row[index] for index in indices) for row in matrix)


def _fit_response(
    matrix: Sequence[tuple[float, ...]],
    responses: Sequence[int],
    fitter: Mapping[str, Any],
    response: str,
) -> dict[str, Any]:
    if not matrix or len(matrix) != len(responses):
        raise _error("fit requires exact non-empty paired matrix/response rows")
    response_mean = _finite(math.fsum(responses) / len(responses), "training response mean")
    if response_mean <= 0.0:
        raise _error("training response mean must be strictly positive")
    beta = [0.0] * len(matrix[0])
    beta[0] = math.log(response_mean)
    updates = 0
    converged = None
    maximum_eta = float(fitter["maximum_abs_linear_predictor"])
    tolerance = float(fitter["gradient_inf_norm_tolerance"])
    max_iterations = int(fitter["max_iterations"])
    pivot_tolerance = float(fitter["linear_solve_pivot_tolerance"])
    backtracking = float(fitter["backtracking_factor"])
    minimum_step = float(fitter["minimum_step"])
    places = int(fitter["coefficient_rounding_places"])

    while True:
        current_nll, _, mus = _historical_response_nll(matrix, responses, beta, maximum_eta)
        gradient, hessian = _historical_gradient_and_hessian(matrix, responses, mus)
        gradient_norm = max(abs(value) for value in gradient)
        if gradient_norm <= tolerance:
            converged = gradient_norm
            break
        if updates >= max_iterations:
            raise _error("frozen Newton solver did not converge")
        direction = _historical_solve_linear_system(hessian, gradient, pivot_tolerance)
        step = 1.0
        while True:
            candidate = tuple(
                _finite(value + step * delta, "candidate coefficient")
                for value, delta in zip(beta, direction)
            )
            try:
                candidate_nll, _, _ = _historical_response_nll(
                    matrix, responses, candidate, maximum_eta
                )
            except HistoricalExpectedGoalsSuccessorCandidateError as exc:
                if "linear predictor exceeds" not in str(exc):
                    raise
                candidate_nll = math.inf
            if candidate_nll <= current_nll:
                beta = list(candidate)
                updates += 1
                break
            step *= backtracking
            if step < minimum_step:
                raise _error("frozen Newton backtracking fell below minimum step")

    rounded = tuple(float(round(value, places)) for value in beta)
    rounded_nll, _, _ = _historical_response_nll(matrix, responses, rounded, maximum_eta)
    return {
        "response": response,
        "training_fixture_count": len(matrix),
        "coefficients": list(rounded),
        "newton_updates": updates,
        "convergence_gradient_inf_norm": _finite(converged, "convergence gradient"),
        "rounded_training_mean_nll": _finite(
            rounded_nll / len(matrix), "rounded training mean NLL"
        ),
    }


def fit_poisson_glm_for_testing(
    matrix: Sequence[Sequence[float]], responses: Sequence[int]
) -> dict[str, Any]:
    """Synthetic seam that executes only the frozen fitter mathematics."""
    protocol = _protocol()
    exact_matrix = tuple(tuple(_finite(v, "matrix value") for v in row) for row in matrix)
    exact_responses = tuple(_nonnegative_int(v, "response") for v in responses)
    return _fit_response(exact_matrix, exact_responses, protocol["frozen_fitter_contract"], "TEST")


def _rate(row: Sequence[float], coefficients: Sequence[float], maximum_eta: float) -> float:
    if len(row) != len(coefficients):
        raise _error("predictor/coefficient dimension mismatch")
    eta = _finite(math.fsum(a * b for a, b in zip(row, coefficients)), "linear predictor")
    if abs(eta) > maximum_eta:
        raise _error("evaluation linear predictor exceeds reviewed guard")
    return _finite(math.exp(eta), "Poisson mean")


def _calibration(
    predicted: Sequence[float],
    observed: Sequence[int],
    bins: Sequence[Sequence[float | None]],
) -> tuple[list[dict[str, Any]], float, float]:
    if len(predicted) != len(observed) or not predicted:
        raise _error("calibration requires exact paired non-empty vectors")
    table: list[dict[str, Any]] = []
    weighted_abs = 0.0
    weighted_sq = 0.0
    total_count = 0
    for lower, upper in bins:
        selected = [
            (p, y)
            for p, y in zip(predicted, observed)
            if p >= float(lower) and (upper is None or p < float(upper))
        ]
        if not selected:
            table.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": 0,
                    "mean_predicted_goals": None,
                    "mean_observed_goals": None,
                    "calibration_error_predicted_minus_observed": None,
                }
            )
            continue
        count = len(selected)
        mean_pred = math.fsum(item[0] for item in selected) / count
        mean_obs = math.fsum(float(item[1]) for item in selected) / count
        error = mean_pred - mean_obs
        weighted_abs += count * abs(error)
        weighted_sq += count * error * error
        total_count += count
        table.append(
            {
                "lower": lower,
                "upper": upper,
                "count": count,
                "mean_predicted_goals": mean_pred,
                "mean_observed_goals": mean_obs,
                "calibration_error_predicted_minus_observed": error,
            }
        )
    if total_count != len(predicted):
        raise _error("calibration bins do not cover exact population")
    return table, weighted_abs / len(predicted), weighted_sq / len(predicted)


def calibration_for_testing(
    predicted: Sequence[float], observed: Sequence[int]
) -> tuple[list[dict[str, Any]], float, float]:
    protocol = _protocol()
    bins = protocol["evaluation_contract"]["calibration_contract"]["bins"]
    return _calibration(predicted, observed, bins)


def _metrics(
    predictions: Sequence[tuple[float, float]],
    rows: Sequence[Mapping[str, Any]],
    bins: Sequence[Sequence[float | None]],
) -> dict[str, Any]:
    if len(predictions) != len(rows) or not rows:
        raise _error("metrics require exact paired predictions/rows")
    home_pred = [item[0] for item in predictions]
    away_pred = [item[1] for item in predictions]
    home_obs = [int(row["home_goals"]) for row in rows]
    away_obs = [int(row["away_goals"]) for row in rows]
    home_nll = [poisson_nll(y, p) for y, p in zip(home_obs, home_pred)]
    away_nll = [poisson_nll(y, p) for y, p in zip(away_obs, away_pred)]
    count = len(rows)
    home_cal, home_wace, home_wsce = _calibration(home_pred, home_obs, bins)
    away_cal, away_wace, away_wsce = _calibration(away_pred, away_obs, bins)
    mean_home_pred = math.fsum(home_pred) / count
    mean_away_pred = math.fsum(away_pred) / count
    mean_home_obs = math.fsum(home_obs) / count
    mean_away_obs = math.fsum(away_obs) / count
    return {
        "fixture_count": count,
        "home_nll": math.fsum(home_nll) / count,
        "away_nll": math.fsum(away_nll) / count,
        "mean_joint_poisson_nll": math.fsum(a + b for a, b in zip(home_nll, away_nll)) / count,
        "home_bias": mean_home_pred - mean_home_obs,
        "away_bias": mean_away_pred - mean_away_obs,
        "home_mae": math.fsum(abs(p - y) for p, y in zip(home_pred, home_obs)) / count,
        "away_mae": math.fsum(abs(p - y) for p, y in zip(away_pred, away_obs)) / count,
        "home_rmse": math.sqrt(math.fsum((p - y) ** 2 for p, y in zip(home_pred, home_obs)) / count),
        "away_rmse": math.sqrt(math.fsum((p - y) ** 2 for p, y in zip(away_pred, away_obs)) / count),
        "home_wace": home_wace,
        "away_wace": away_wace,
        "home_wsce": home_wsce,
        "away_wsce": away_wsce,
        "home_calibration": home_cal,
        "away_calibration": away_cal,
    }


def _quarter_key(kickoff: str) -> str:
    year = int(kickoff[0:4])
    month = int(kickoff[5:7])
    quarter = ((month - 1) // 3) + 1
    return f"{year}-Q{quarter}"


def _quarter_jackknife(
    paired_differences: Sequence[tuple[str, float]],
    expected_clusters: Sequence[Sequence[Any]],
    multiplier: float,
) -> dict[str, Any]:
    if not paired_differences:
        raise _error("jackknife requires paired evaluation values")
    grouped: dict[str, list[float]] = {}
    for kickoff, difference in paired_differences:
        grouped.setdefault(_quarter_key(kickoff), []).append(_finite(difference, "paired difference"))
    expected = [(str(key), int(count)) for key, count in expected_clusters]
    if sorted((key, len(values)) for key, values in grouped.items()) != sorted(expected):
        raise _error("UTC-quarter membership/counts differ from reviewed protocol")
    all_values = [value for _, value in paired_differences]
    full_theta = math.fsum(all_values) / len(all_values)
    deletes: list[dict[str, Any]] = []
    delete_values: list[float] = []
    for key, count in expected:
        removed = grouped[key]
        remaining_n = len(all_values) - len(removed)
        if remaining_n <= 0:
            raise _error("jackknife cluster removes whole population")
        theta = (math.fsum(all_values) - math.fsum(removed)) / remaining_n
        deletes.append({"quarter": key, "deleted_count": count, "remaining_count": remaining_n, "theta_delete": theta})
        delete_values.append(theta)
    k = len(delete_values)
    theta_bar = math.fsum(delete_values) / k
    se = math.sqrt(((k - 1) / k) * math.fsum((theta - theta_bar) ** 2 for theta in delete_values))
    lower = full_theta - multiplier * se
    upper = full_theta + multiplier * se
    return {
        "cluster_count": k,
        "full_theta": full_theta,
        "delete_estimate_center": theta_bar,
        "jackknife_standard_error": se,
        "lower_95_percent_bound": lower,
        "upper_95_percent_bound": upper,
        "delete_estimates": deletes,
    }


def quarter_jackknife_for_testing(
    paired_differences: Sequence[tuple[str, float]],
    expected_clusters: Sequence[Sequence[Any]],
) -> dict[str, Any]:
    return _quarter_jackknife(paired_differences, expected_clusters, 1.96)


def _predict_arm(
    arm: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    full_coefficients: tuple[Sequence[float], Sequence[float]] | None = None,
    reduced_coefficients: tuple[Sequence[float], Sequence[float]] | None = None,
    constant_rates: tuple[float, float] | None = None,
    maximum_eta: float,
) -> tuple[tuple[float, float], ...]:
    result: list[tuple[float, float]] = []
    for row in rows:
        full = _full_predictor(row)
        if arm in {ARM_NATIVE, ARM_HISTORICAL}:
            if full_coefficients is None:
                raise _error("full coefficient arm missing coefficients")
            home = _rate(full, full_coefficients[0], maximum_eta)
            away = _rate(full, full_coefficients[1], maximum_eta)
        elif arm == ARM_ELO:
            if reduced_coefficients is None:
                raise _error("Elo arm missing coefficients")
            vector = (full[0], full[1], full[2])
            home = _rate(vector, reduced_coefficients[0], maximum_eta)
            away = _rate(vector, reduced_coefficients[1], maximum_eta)
        elif arm == ARM_NO_FATIGUE:
            if reduced_coefficients is None:
                raise _error("no-fatigue arm missing coefficients")
            vector = full[:5]
            home = _rate(vector, reduced_coefficients[0], maximum_eta)
            away = _rate(vector, reduced_coefficients[1], maximum_eta)
        elif arm == ARM_CONSTANT:
            if constant_rates is None:
                raise _error("constant arm missing train-only rates")
            home, away = constant_rates
        else:
            raise _error("unknown model arm")
        result.append((_finite(home, "predicted home rate"), _finite(away, "predicted away rate")))
    return tuple(result)


def _evaluate_rows(
    rows: tuple[dict[str, Any], ...],
    protocol: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    populations = _prepare_populations(rows, protocol)
    train = populations["TRAIN"]
    eval_a = populations["EVALUATION_A"]
    eval_b = populations["EVALUATION_B_TERMINAL"]
    pooled = populations["POOLED_A_PLUS_B"]
    train_matrix = tuple(_full_predictor(row) for row in train)
    home_y = tuple(int(row["home_goals"]) for row in train)
    away_y = tuple(int(row["away_goals"]) for row in train)
    fitter = protocol["frozen_fitter_contract"]
    maximum_eta = float(fitter["maximum_abs_linear_predictor"])

    native_home = _fit_response(train_matrix, home_y, fitter, "HOME_GOALS")
    native_away = _fit_response(train_matrix, away_y, fitter, "AWAY_GOALS")
    elo_matrix = _subset(train_matrix, (0, 1, 2))
    elo_home = _fit_response(elo_matrix, home_y, fitter, "HOME_GOALS")
    elo_away = _fit_response(elo_matrix, away_y, fitter, "AWAY_GOALS")
    no_fatigue_matrix = _subset(train_matrix, (0, 1, 2, 3, 4))
    nf_home = _fit_response(no_fatigue_matrix, home_y, fitter, "HOME_GOALS")
    nf_away = _fit_response(no_fatigue_matrix, away_y, fitter, "AWAY_GOALS")
    historical = (
        tuple(float(v) for v in protocol_mod.HISTORICAL_HOME_COEFFICIENTS),
        tuple(float(v) for v in protocol_mod.HISTORICAL_AWAY_COEFFICIENTS),
    )
    constant_rates = (
        math.fsum(home_y) / len(home_y),
        math.fsum(away_y) / len(away_y),
    )
    fitted = {
        ARM_NATIVE: (tuple(native_home["coefficients"]), tuple(native_away["coefficients"])),
        ARM_ELO: (tuple(elo_home["coefficients"]), tuple(elo_away["coefficients"])),
        ARM_NO_FATIGUE: (tuple(nf_home["coefficients"]), tuple(nf_away["coefficients"])),
    }

    population_rows = {
        "EVALUATION_A": eval_a,
        "EVALUATION_B_TERMINAL": eval_b,
        "POOLED_A_PLUS_B": pooled,
    }
    predictions_by_population: dict[str, dict[str, tuple[tuple[float, float], ...]]] = {}
    evaluations: dict[str, Any] = {}
    bins = protocol["evaluation_contract"]["calibration_contract"]["bins"]
    for population_name, pop_rows in population_rows.items():
        arm_predictions = {
            ARM_NATIVE: _predict_arm(
                ARM_NATIVE,
                pop_rows,
                full_coefficients=fitted[ARM_NATIVE],
                maximum_eta=maximum_eta,
            ),
            ARM_HISTORICAL: _predict_arm(
                ARM_HISTORICAL,
                pop_rows,
                full_coefficients=historical,
                maximum_eta=maximum_eta,
            ),
            ARM_ELO: _predict_arm(
                ARM_ELO,
                pop_rows,
                reduced_coefficients=fitted[ARM_ELO],
                maximum_eta=maximum_eta,
            ),
            ARM_NO_FATIGUE: _predict_arm(
                ARM_NO_FATIGUE,
                pop_rows,
                reduced_coefficients=fitted[ARM_NO_FATIGUE],
                maximum_eta=maximum_eta,
            ),
            ARM_CONSTANT: _predict_arm(
                ARM_CONSTANT,
                pop_rows,
                constant_rates=constant_rates,
                maximum_eta=maximum_eta,
            ),
        }
        predictions_by_population[population_name] = arm_predictions
        arm_metrics = {
            arm: _metrics(arm_predictions[arm], pop_rows, bins) for arm in ARM_ORDER
        }
        deltas = {
            "NATIVE_REFIT_MINUS_ELO_ONLY": arm_metrics[ARM_NATIVE]["mean_joint_poisson_nll"] - arm_metrics[ARM_ELO]["mean_joint_poisson_nll"],
            "NATIVE_REFIT_MINUS_HISTORICAL_FIXED_TRANSFER": arm_metrics[ARM_NATIVE]["mean_joint_poisson_nll"] - arm_metrics[ARM_HISTORICAL]["mean_joint_poisson_nll"],
            "NATIVE_REFIT_MINUS_CONSTANT": arm_metrics[ARM_NATIVE]["mean_joint_poisson_nll"] - arm_metrics[ARM_CONSTANT]["mean_joint_poisson_nll"],
            "HISTORICAL_FIXED_TRANSFER_MINUS_CONSTANT": arm_metrics[ARM_HISTORICAL]["mean_joint_poisson_nll"] - arm_metrics[ARM_CONSTANT]["mean_joint_poisson_nll"],
            "NO_FATIGUE_MINUS_NATIVE_REFIT": arm_metrics[ARM_NO_FATIGUE]["mean_joint_poisson_nll"] - arm_metrics[ARM_NATIVE]["mean_joint_poisson_nll"],
        }
        evaluations[population_name] = {"arms": arm_metrics, "paired_deltas": deltas}

    paired: list[tuple[str, float]] = []
    prediction_records: list[dict[str, Any]] = []
    for index, row in enumerate(pooled):
        arm_payload: dict[str, Any] = {}
        for arm in ARM_ORDER:
            home_rate, away_rate = predictions_by_population["POOLED_A_PLUS_B"][arm][index]
            joint_nll = poisson_nll(row["home_goals"], home_rate) + poisson_nll(
                row["away_goals"], away_rate
            )
            arm_payload[arm] = {
                "home_expected_goals": home_rate,
                "away_expected_goals": away_rate,
                "joint_poisson_nll": joint_nll,
            }
        native_nll = arm_payload[ARM_NATIVE]["joint_poisson_nll"]
        elo_nll = arm_payload[ARM_ELO]["joint_poisson_nll"]
        paired.append((row["kickoff_utc"], native_nll - elo_nll))
        prediction_records.append(
            {
                "schema_version": 1,
                "fixture_identifier": row["fixture_identifier"],
                "kickoff_utc": row["kickoff_utc"],
                "home_goals": row["home_goals"],
                "away_goals": row["away_goals"],
                "arms": arm_payload,
            }
        )
    prediction_bytes = b"".join(_canonical(record) for record in prediction_records)

    temporal = protocol["evaluation_contract"]["temporal_robustness"]
    jackknife = _quarter_jackknife(
        paired,
        temporal["cluster_keys_and_counts"],
        float(temporal["interval_multiplier"]),
    )
    a_delta = evaluations["EVALUATION_A"]["paired_deltas"]["NATIVE_REFIT_MINUS_ELO_ONLY"]
    b_delta = evaluations["EVALUATION_B_TERMINAL"]["paired_deltas"]["NATIVE_REFIT_MINUS_ELO_ONLY"]
    pooled_delta = evaluations["POOLED_A_PLUS_B"]["paired_deltas"]["NATIVE_REFIT_MINUS_ELO_ONLY"]
    pooled_native_metrics = evaluations["POOLED_A_PLUS_B"]["arms"][ARM_NATIVE]
    pooled_elo_metrics = evaluations["POOLED_A_PLUS_B"]["arms"][ARM_ELO]
    strong = (
        a_delta < 0.0
        and b_delta < 0.0
        and pooled_delta < 0.0
        and jackknife["upper_95_percent_bound"] < 0.0
        and pooled_native_metrics["home_wace"] < pooled_elo_metrics["home_wace"]
        and pooled_native_metrics["away_wace"] < pooled_elo_metrics["away_wace"]
        and pooled_native_metrics["home_wsce"] < pooled_elo_metrics["home_wsce"]
        and pooled_native_metrics["away_wsce"] < pooled_elo_metrics["away_wsce"]
    )
    signal_state = (
        protocol["evaluation_contract"]["strong_signal_state"]
        if strong
        else protocol["evaluation_contract"]["non_strong_signal_state"]
    )
    population_receipt = {
        key: {
            "row_count": len(value),
            "membership_sha256": _sha256(_membership_bytes(value)),
        }
        for key, value in populations.items()
    }
    arm_membership = {
        arm: {
            key: dict(population_receipt[key])
            for key in ("TRAIN", "EVALUATION_A", "EVALUATION_B_TERMINAL", "POOLED_A_PLUS_B")
        }
        for arm in ARM_ORDER
    }
    result = {
        "schema_version": 1,
        "validation_id": VALIDATION_ID,
        "validation_state": signal_state,
        "automatic_model_approval": False,
        "protocol": {
            "protocol_id": protocol_mod.PROTOCOL_ID,
            "sha256": protocol_mod.PROTOCOL_SHA256,
            "size_bytes": protocol_mod.PROTOCOL_SIZE,
        },
        "population": population_receipt,
        "arm_membership": arm_membership,
        "fits": {
            ARM_NATIVE: {"home": native_home, "away": native_away},
            ARM_ELO: {"home": elo_home, "away": elo_away},
            ARM_NO_FATIGUE: {"home": nf_home, "away": nf_away},
            ARM_HISTORICAL: {
                "home_coefficients": list(historical[0]),
                "away_coefficients": list(historical[1]),
                "fit_executed": False,
            },
            ARM_CONSTANT: {
                "home_lambda": constant_rates[0],
                "away_lambda": constant_rates[1],
                "fit_population": "EXACT_COMMON_TRAIN",
            },
        },
        "evaluations": evaluations,
        "temporal_robustness": jackknife,
        "predictions": {
            "row_count": len(prediction_records),
            "sha256": _sha256(prediction_bytes),
            "size_bytes": len(prediction_bytes),
        },
        "competition_or_league_robustness_status": protocol["evaluation_contract"][
            "competition_or_league_robustness_status"
        ],
        "cross_runtime_bit_identity_qualified": False,
        "runtime_provenance_required": True,
        "safety": _default_safety(),
        "next_required_boundary": POST_EXECUTION_REVIEW_BOUNDARY,
    }
    return prediction_bytes, result


def _validated_qualification_receipt(raw: bytes, protocol: Mapping[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("qualification V2 receipt is malformed") from exc
    if not isinstance(payload, dict) or _canonical(payload) != raw:
        raise _error("qualification V2 receipt is not exact canonical JSON")
    expected = protocol["v2_success_evidence"]
    if payload.get("qualification_status") != "QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION":
        raise _error("qualification status changed")
    projection = payload.get("projection")
    if not isinstance(projection, dict):
        raise _error("qualification projection receipt missing")
    for field, value in (
        ("record_count", expected["record_count"]),
        ("unique_fixture_count", expected["unique_fixture_count"]),
        ("same_kickoff_group_count", expected["same_kickoff_group_count"]),
        ("sha256", expected["projection_sha256"]),
        ("size_bytes", expected["projection_size_bytes"]),
        ("identity_or_lineage_conflict_count", expected["identity_or_lineage_conflict_count"]),
    ):
        if projection.get(field) != value:
            raise _error(f"qualification receipt projection {field} changed")
    freshness = payload.get("historical_live_data_freshness")
    if (
        not isinstance(freshness, dict)
        or freshness.get("status") != FRESHNESS_STATUS
        or freshness.get("numeric_value_produced") is not False
        or freshness.get("training_feature_authorized") is not False
    ):
        raise _error("qualification receipt historical freshness semantics changed")
    safety = payload.get("safety")
    if not isinstance(safety, dict) or any(flag is not False for flag in safety.values()):
        raise _error("qualification receipt must grant no downstream authority")
    return payload


def build_validation(
    artifact_zip: Path,
    *,
    predictions_output: Path | None = None,
) -> dict[str, Any]:
    """Execute the reviewed model-validation study against the exact V2 artifact."""
    protocol = _protocol()
    artifact_zip = Path(artifact_zip)
    if not artifact_zip.is_file():
        raise _error("V2 qualification artifact path does not exist")
    archive = artifact_zip.read_bytes()
    expected = protocol["v2_success_evidence"]
    if (_sha256(archive), len(archive)) != (
        expected["artifact_sha256"],
        expected["artifact_size_bytes"],
    ):
        raise _error("V2 qualification artifact archive identity changed")
    try:
        with zipfile.ZipFile(io.BytesIO(archive), "r") as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)):
                raise _error("V2 artifact contains duplicate member names")
            if PROJECTION_MEMBER not in names or QUALIFICATION_RECEIPT_MEMBER not in names:
                raise _error("V2 artifact missing required projection/receipt")
            projection_raw = bundle.read(PROJECTION_MEMBER)
            receipt_raw = bundle.read(QUALIFICATION_RECEIPT_MEMBER)
    except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise _error("V2 qualification artifact is not a readable exact ZIP") from exc

    if (_sha256(projection_raw), len(projection_raw)) != (
        expected["projection_sha256"],
        expected["projection_size_bytes"],
    ):
        raise _error("V2 projection identity changed")
    _validated_qualification_receipt(receipt_raw, protocol)
    rows = _parse_projection(projection_raw)
    if len(rows) != expected["record_count"]:
        raise _error("V2 projection row count changed")

    predictions, result = _evaluate_rows(rows, protocol)
    result["source_evidence"] = {
        "artifact_id": expected["artifact_id"],
        "artifact_name": expected["artifact_name"],
        "artifact_sha256": expected["artifact_sha256"],
        "artifact_size_bytes": expected["artifact_size_bytes"],
        "projection_sha256": expected["projection_sha256"],
        "projection_size_bytes": expected["projection_size_bytes"],
        "projection_rows": expected["record_count"],
        "qualification_result_comment_id": expected["result_comment_id"],
        "qualification_run_id": expected["run_id"],
    }
    result["runtime"] = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "sys_platform": sys.platform,
    }
    if predictions_output is not None:
        output = Path(predictions_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(predictions)
    return result


def canonical_validation_receipt_bytes(value: Any) -> bytes:
    if not isinstance(value, dict):
        raise _error("validation receipt must be an object")
    safety = value.get("safety")
    if (
        not isinstance(safety, dict)
        or set(safety) != SAFETY_KEYS
        or any(type(flag) is not bool or flag is not False for flag in safety.values())
    ):
        raise _error("validation receipt safety must remain exact all-false")
    if value.get("automatic_model_approval") is not False:
        raise _error("validation receipt may not auto-approve a model")
    return _canonical(value)


__all__ = [
    "ARM_CONSTANT",
    "ARM_ELO",
    "ARM_HISTORICAL",
    "ARM_NATIVE",
    "ARM_NO_FATIGUE",
    "FRESHNESS_STATUS",
    "IMPLEMENTATION_STATE",
    "NEXT_REQUIRED_BOUNDARY",
    "POST_EXECUTION_REVIEW_BOUNDARY",
    "SOURCE_NAMESPACE",
    "VALIDATION_ID",
    "FotMobUTCNativeExpectedGoalsModelValidationError",
    "build_validation",
    "calibration_for_testing",
    "canonical_validation_receipt_bytes",
    "fit_poisson_glm_for_testing",
    "quarter_jackknife_for_testing",
]
