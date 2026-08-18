"""Pure offline evaluator for the frozen FotMob UTC-native xG fresh holdout.

This module is deliberately result-evaluation only.  It accepts exact reviewed
fresh-holdout objects, revalidates the outcome-independent close boundary, requires
complete terminal accounting after the settlement tail, and calculates only the
metrics/gates pre-registered by PR #148.  It performs no network acquisition,
model fitting, calibration fitting, source discovery, pricing, selection, or BET
decision.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import math
import types
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol as pr148
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control


SCHEMA_VERSION = 1
EVALUATOR_ID = "FOTMOB_UTC_NATIVE_XG_FRESH_HOLDOUT_CONFIRMATION_EVALUATOR_V1"
EVALUATOR_STATE = "IMPLEMENTED_FROZEN_FRESH_HOLDOUT_CONFIRMATION_EVALUATOR_NOT_EXECUTED"
NEXT_REQUIRED_BOUNDARY = "SOURCE_REPLAY_AND_REVIEW_FRESH_HOLDOUT_CONFIRMATION_RESULT"

PR148_PROTOCOL_BLOB_SHA = "9f45e17603a2678741ccc596d2542a0c6e29fa6c"
PR149_CORE_BLOB_SHA = "5dabab12d5205d384fd3904cda0e68661ef90791"
PR150_CONTROL_BLOB_SHA = "60865e35a92e28bb0d4360223dea42b8933bb706"
PR151_RUNNER_BLOB_SHA = "901ab137d6601a3485eac30da7e6bad7eeefa397"

RESULT_SIGNAL_REVIEW_REQUIRED = (
    "FRESH_HOLDOUT_CALIBRATION_AND_COMPETITION_ROBUSTNESS_SIGNAL_REVIEW_REQUIRED"
)
RESULT_INSUFFICIENT_COVERAGE = (
    "FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION"
)
RESULT_GATE_FAILED_REVIEW_REQUIRED = (
    "FRESH_HOLDOUT_CALIBRATION_OR_ROBUSTNESS_GATE_FAILED_REVIEW_REQUIRED"
)

CALIBRATION_BINS = (
    (0.0, 0.5),
    (0.5, 1.0),
    (1.0, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
    (2.5, 3.0),
    (3.0, None),
)

SAFETY_KEYS = tuple(sorted(pr148.SAFETY_KEYS))


class FreshHoldoutConfirmationEvaluatorError(ValueError):
    """Raised when frozen confirmation evaluation cannot fail closed."""


def _error(message: str) -> FreshHoldoutConfirmationEvaluatorError:
    return FreshHoldoutConfirmationEvaluatorError(message)


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical confirmation serialization failed") from exc


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in SAFETY_KEYS})


def _utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error(f"{label} must be timezone-aware")
    try:
        return value.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(f"{label} is invalid") from exc


def _utc_text(value: dt.datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise _error(f"{label} must be finite numeric")
    return float(value)


def _positive_rate(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result <= 0.0:
        raise _error(f"{label} must be strictly positive")
    return result


def _mean(values: Sequence[float], label: str) -> float:
    if not values:
        raise _error(f"{label} cannot be empty")
    return _finite(math.fsum(values) / len(values), label)


def verify_reviewed_dependencies() -> None:
    """Fail closed if any frozen source/control/evaluation dependency moved."""
    protocol = pr148.build_fresh_holdout_home_calibration_competition_identity_protocol()
    raw = pr148.canonical_fresh_holdout_home_calibration_competition_identity_protocol_bytes(
        protocol
    )
    if (len(raw), hashlib.sha256(raw).hexdigest()) != (
        pr148.PROTOCOL_SIZE,
        pr148.PROTOCOL_SHA256,
    ):
        raise _error("PR148 protocol canonical identity changed")
    if any(protocol["safety"].values()):
        raise _error("PR148 downstream authority changed")
    pins = (
        (Path(pr148.__file__), PR148_PROTOCOL_BLOB_SHA, "PR148 protocol"),
        (Path(fresh.__file__), PR149_CORE_BLOB_SHA, "PR149 fresh-holdout core"),
        (Path(control.__file__), PR150_CONTROL_BLOB_SHA, "PR150 collection control"),
        (Path(runner.__file__), PR151_RUNNER_BLOB_SHA, "PR151 activation runner"),
    )
    try:
        for path, expected, label in pins:
            if _git_blob_sha(path) != expected:
                raise _error(f"{label} implementation blob changed")
    except OSError as exc:
        raise _error("could not verify reviewed dependency blobs") from exc
    if control.HOLDOUT_START_UTC_TEXT != "2026-08-19T00:00:00Z":
        raise _error("reviewed holdout start changed")
    if runner.NEXT_REQUIRED_BOUNDARY != (
        "REVIEW_FRESH_HOLDOUT_COLLECTION_EVIDENCE_AND_CONFIRMATION_RESULT"
    ):
        raise _error("PR151 next boundary changed")
    if fresh.IMPLEMENTATION_STATE != (
        "IMPLEMENTED_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
        "CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP_NOT_ACTIVATED"
    ):
        raise _error("PR149 implementation state changed")


class TerminalDisposition(str, enum.Enum):
    SETTLED_REVIEWED_ORDINARY_FT = (
        fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT.value
    )
    EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT = (
        fresh.SettlementDisposition.EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT.value
    )
    EXCLUDED_OUTSIDE_SELECTED_CLOSE = "EXCLUDED_OUTSIDE_SELECTED_CLOSE"
    UNRESOLVED_AT_SETTLEMENT_TAIL = "UNRESOLVED_AT_SETTLEMENT_TAIL"


@dataclasses.dataclass(frozen=True)
class TerminalSettlementRecord:
    fixture_id: int
    disposition: TerminalDisposition
    settled_prediction: fresh.SettledFreshPrediction | None

    def __post_init__(self) -> None:
        if type(self.fixture_id) is not int or self.fixture_id < 1:
            raise _error("terminal fixture_id must be an exact positive integer")
        if not isinstance(self.disposition, TerminalDisposition):
            raise _error("terminal disposition escaped reviewed vocabulary")
        if self.disposition is TerminalDisposition.SETTLED_REVIEWED_ORDINARY_FT:
            if type(self.settled_prediction) is not fresh.SettledFreshPrediction:
                raise _error("settled terminal record requires exact settled prediction")
            value = dataclasses.replace(self.settled_prediction)
            if value.prediction.fixture.fixture_id != self.fixture_id:
                raise _error("settled terminal fixture identity changed")
            object.__setattr__(self, "settled_prediction", value)
        elif self.settled_prediction is not None:
            raise _error("excluded/unresolved terminal record cannot carry a settlement")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "disposition": self.disposition.value,
            "settled": self.settled_prediction is not None,
        }


def _poisson_nll(goals: int, rate: float) -> float:
    if type(goals) is not int or goals < 0:
        raise _error("goals must be a non-negative exact integer")
    lam = _positive_rate(rate, "Poisson rate")
    return _finite(
        lam - goals * math.log(lam) + math.lgamma(goals + 1),
        "Poisson NLL",
    )


def _joint_nll(value: fresh.SettledFreshPrediction, model: str) -> float:
    rates = value.prediction.rates
    if model == "calibrated":
        home = rates["calibrated_home"]
        away = rates["calibrated_away"]
    elif model == "native":
        home = rates["native_home"]
        away = rates["native_away"]
    elif model == "elo_only":
        home = rates["elo_only_home"]
        away = rates["elo_only_away"]
    else:
        raise _error("unknown frozen model identifier")
    return math.fsum(
        (
            _poisson_nll(value.home_goals, home),
            _poisson_nll(value.away_goals, away),
        )
    )


def _side_rate(value: fresh.SettledFreshPrediction, model: str, side: str) -> float:
    if side not in {"home", "away"}:
        raise _error("calibration side must be home or away")
    if model not in {"calibrated", "native", "elo_only"}:
        raise _error("calibration model escaped frozen vocabulary")
    return _positive_rate(value.prediction.rates[f"{model}_{side}"], "calibration rate")


def _side_goals(value: fresh.SettledFreshPrediction, side: str) -> int:
    return value.home_goals if side == "home" else value.away_goals


def _calibration_summary(
    fixtures: Sequence[fresh.SettledFreshPrediction],
    *,
    model: str,
    side: str,
) -> dict[str, Any]:
    values = tuple(fixtures)
    if not values:
        raise _error("calibration population cannot be empty")

    predictions = [_side_rate(item, model, side) for item in values]
    outcomes = [float(_side_goals(item, side)) for item in values]
    bins: list[dict[str, Any]] = []
    absolute_errors: list[float] = []
    squared_errors: list[float] = []

    for lower, upper in CALIBRATION_BINS:
        selected = [
            (_side_rate(item, model, side), _side_goals(item, side))
            for item in values
            if _side_rate(item, model, side) >= lower
            and (upper is None or _side_rate(item, model, side) < upper)
        ]
        if not selected:
            bins.append(
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
        predicted = _mean([item[0] for item in selected], "bin predicted goals")
        observed = _mean([float(item[1]) for item in selected], "bin observed goals")
        error = predicted - observed
        count = len(selected)
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": count,
                "mean_predicted_goals": predicted,
                "mean_observed_goals": observed,
                "calibration_error_predicted_minus_observed": error,
            }
        )
        absolute_errors.append(count * abs(error))
        squared_errors.append(count * error * error)

    return {
        "bins": bins,
        "absolute_overall_bias": abs(
            _mean(predictions, "prediction mean") - _mean(outcomes, "outcome mean")
        ),
        "wace": math.fsum(absolute_errors) / len(values),
        "wsce": math.fsum(squared_errors) / len(values),
    }


def _metrics(
    fixtures: Sequence[fresh.SettledFreshPrediction],
) -> dict[str, Any]:
    values = tuple(fixtures)
    if not values:
        raise _error("performance population cannot be empty")
    result: dict[str, Any] = {"fixture_count": len(values)}
    for model in ("calibrated", "native", "elo_only"):
        result[model] = {
            "mean_joint_poisson_nll": _mean(
                [_joint_nll(item, model) for item in values],
                f"{model} joint NLL",
            ),
            "home_calibration": _calibration_summary(
                values, model=model, side="home"
            ),
            "away_calibration": _calibration_summary(
                values, model=model, side="away"
            ),
        }
    return result


def _pooled_gates(metrics: Mapping[str, Any]) -> dict[str, bool]:
    calibrated = metrics["calibrated"]
    native = metrics["native"]
    elo = metrics["elo_only"]
    return {
        "calibrated_home_wace_strictly_below_uncalibrated_native": (
            calibrated["home_calibration"]["wace"]
            < native["home_calibration"]["wace"]
        ),
        "calibrated_home_wace_strictly_below_elo_only": (
            calibrated["home_calibration"]["wace"]
            < elo["home_calibration"]["wace"]
        ),
        "calibrated_home_wsce_strictly_below_uncalibrated_native": (
            calibrated["home_calibration"]["wsce"]
            < native["home_calibration"]["wsce"]
        ),
        "calibrated_home_wsce_strictly_below_elo_only": (
            calibrated["home_calibration"]["wsce"]
            < elo["home_calibration"]["wsce"]
        ),
        "calibrated_joint_nll_strictly_below_elo_only": (
            calibrated["mean_joint_poisson_nll"] < elo["mean_joint_poisson_nll"]
        ),
        "calibrated_joint_nll_not_above_uncalibrated_native": (
            calibrated["mean_joint_poisson_nll"] <= native["mean_joint_poisson_nll"]
        ),
        "native_away_wace_strictly_below_elo_only": (
            native["away_calibration"]["wace"] < elo["away_calibration"]["wace"]
        ),
        "native_away_wsce_strictly_below_elo_only": (
            native["away_calibration"]["wsce"] < elo["away_calibration"]["wsce"]
        ),
    }


def _paired_delta(value: fresh.SettledFreshPrediction) -> float:
    return _joint_nll(value, "calibrated") - _joint_nll(value, "elo_only")


def _terminal_counts(
    records: Sequence[TerminalSettlementRecord],
) -> dict[str, int]:
    counts = Counter(item.disposition.value for item in records)
    return {
        disposition.value: counts[disposition.value] for disposition in TerminalDisposition
    }


def _competition_reports(
    *,
    selected_assessments: Sequence[fresh.FreshPredictionAssessment],
    selected_predictions: Sequence[fresh.SealedFreshPrediction],
    terminals: Mapping[int, TerminalSettlementRecord],
) -> list[dict[str, Any]]:
    assessment_by_primary: dict[int, list[fresh.FreshPredictionAssessment]] = defaultdict(list)
    sealed_by_primary: dict[int, list[fresh.SealedFreshPrediction]] = defaultdict(list)
    for assessment in selected_assessments:
        assessment_by_primary[assessment.fixture.provider_primary_id].append(assessment)
    for prediction in selected_predictions:
        sealed_by_primary[prediction.fixture.provider_primary_id].append(prediction)

    reports: list[dict[str, Any]] = []
    threshold = pr148.QUALIFYING_COMPETITION_MIN_FIXTURES
    for primary_id in sorted(assessment_by_primary):
        assessments = tuple(assessment_by_primary[primary_id])
        population = tuple(sealed_by_primary.get(primary_id, ()))
        missing_assessments = tuple(
            item
            for item in assessments
            if item.disposition is fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES
        )
        missing_feature_counts: Counter[str] = Counter()
        for assessment in missing_assessments:
            missing_feature_counts.update(assessment.missing_feature_ids)
        records = tuple(terminals[item.fixture.fixture_id] for item in population)
        settled = tuple(
            record.settled_prediction
            for record in records
            if record.settled_prediction is not None
        )
        scored = tuple(item for item in settled if item is not None)
        report: dict[str, Any] = {
            "provider_primary_id": primary_id,
            "legacy_primary_id": primary_id in pr148.LEGACY_PRIMARY_IDS,
            "prediction_assessment_count": len(assessments),
            "sealed_complete_case_count": len(population),
            "missing_feature_prediction_count": len(missing_assessments),
            "missing_feature_id_counts": {
                key: missing_feature_counts[key] for key in sorted(missing_feature_counts)
            },
            "scored_ordinary_ft_count": len(scored),
            "missing_or_excluded_settlement_count": len(population) - len(scored),
            "settlement_coverage_fraction": (
                None if not population else len(scored) / len(population)
            ),
            "terminal_disposition_counts": _terminal_counts(records),
            "qualifying_for_robustness": len(population) >= threshold,
            "report_only_below_threshold": len(population) < threshold,
            "metrics": None,
            "mean_paired_delta_calibrated_minus_elo_only": None,
        }
        if scored:
            report["metrics"] = _metrics(scored)
            report["mean_paired_delta_calibrated_minus_elo_only"] = _mean(
                [_paired_delta(item) for item in scored],
                "competition paired delta",
            )
        reports.append(report)
    return reports


def _robustness(
    *,
    qualifying_primary_ids: Sequence[int],
    settled: Sequence[fresh.SettledFreshPrediction],
) -> dict[str, Any]:
    primary_ids = tuple(sorted(qualifying_primary_ids))
    if len(primary_ids) < pr148.MINIMUM_QUALIFYING_COMPETITIONS:
        raise _error("robustness called without frozen minimum qualifying clusters")

    by_primary: dict[int, list[fresh.SettledFreshPrediction]] = defaultdict(list)
    for item in settled:
        primary = item.prediction.fixture.provider_primary_id
        if primary in primary_ids:
            by_primary[primary].append(item)

    missing_scored = tuple(primary for primary in primary_ids if not by_primary[primary])
    union = tuple(
        item for primary in primary_ids for item in by_primary[primary]
    )
    if not union:
        return {
            "qualifying_primary_ids": list(primary_ids),
            "scored_fixture_count": 0,
            "qualifying_clusters_without_scored_settlement": list(missing_scored),
            "full_estimate": None,
            "delete_one_cluster_estimates": {},
            "jackknife_se": None,
            "interval_lower": None,
            "interval_upper": None,
            "negative_cluster_fraction": 0.0,
            "upper_95_strictly_below_zero": False,
            "minimum_negative_cluster_fraction_pass": False,
            "all_robustness_gates_pass": False,
        }

    deltas = [(item.prediction.fixture.provider_primary_id, _paired_delta(item)) for item in union]
    full = _mean([value for _primary, value in deltas], "full paired delta")
    delete_estimates: dict[str, float | None] = {}
    delete_values: list[float] = []
    for primary in primary_ids:
        remaining = [value for pid, value in deltas if pid != primary]
        if not remaining:
            delete_estimates[str(primary)] = None
        else:
            estimate = _mean(remaining, "delete-one paired delta")
            delete_estimates[str(primary)] = estimate
            delete_values.append(estimate)

    if len(delete_values) != len(primary_ids):
        jackknife_se = None
        lower = None
        upper = None
        upper_pass = False
    else:
        center = _mean(delete_values, "jackknife delete center")
        k = len(delete_values)
        jackknife_se = math.sqrt(
            ((k - 1) / k)
            * math.fsum((value - center) ** 2 for value in delete_values)
        )
        lower = full - 1.96 * jackknife_se
        upper = full + 1.96 * jackknife_se
        upper_pass = upper < 0.0

    negative = 0
    for primary in primary_ids:
        cluster = [value for pid, value in deltas if pid == primary]
        if cluster and _mean(cluster, "cluster paired delta") < 0.0:
            negative += 1
    fraction = negative / len(primary_ids)
    fraction_pass = fraction >= pr148.MINIMUM_NEGATIVE_COMPETITION_FRACTION
    return {
        "qualifying_primary_ids": list(primary_ids),
        "scored_fixture_count": len(union),
        "qualifying_clusters_without_scored_settlement": list(missing_scored),
        "full_estimate": full,
        "delete_one_cluster_estimates": delete_estimates,
        "jackknife_se": jackknife_se,
        "interval_lower": lower,
        "interval_upper": upper,
        "negative_cluster_fraction": fraction,
        "upper_95_strictly_below_zero": upper_pass,
        "minimum_negative_cluster_fraction_pass": fraction_pass,
        "all_robustness_gates_pass": (
            not missing_scored and upper_pass and fraction_pass
        ),
    }


def _validate_assessments(
    assessments: Sequence[fresh.FreshPredictionAssessment],
) -> tuple[fresh.FreshPredictionAssessment, ...]:
    if not isinstance(assessments, Sequence) or isinstance(assessments, (str, bytes)):
        raise _error("prediction assessments must be a sequence")
    values = tuple(assessments)
    if any(type(item) is not fresh.FreshPredictionAssessment for item in values):
        raise _error("prediction population must contain exact FreshPredictionAssessment")
    seen: set[int] = set()
    result: list[fresh.FreshPredictionAssessment] = []
    for item in values:
        fixture_id = item.fixture.fixture_id
        if fixture_id in seen:
            raise _error("prediction assessment population duplicates a fixture")
        seen.add(fixture_id)
        result.append(dataclasses.replace(item))
    result.sort(key=lambda item: (item.fixture.kickoff_utc, item.fixture.fixture_id))
    return tuple(result)


def _validate_terminals(
    records: Sequence[TerminalSettlementRecord],
    predictions: Sequence[fresh.SealedFreshPrediction],
) -> dict[int, TerminalSettlementRecord]:
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise _error("terminal records must be a sequence")
    values = tuple(records)
    if any(type(item) is not TerminalSettlementRecord for item in values):
        raise _error("terminal population contains unexpected type")
    by_fixture: dict[int, TerminalSettlementRecord] = {}
    for item in values:
        if item.fixture_id in by_fixture:
            raise _error("terminal accounting duplicates a fixture")
        by_fixture[item.fixture_id] = dataclasses.replace(item)
    expected = {item.fixture.fixture_id for item in predictions}
    if set(by_fixture) != expected:
        raise _error("terminal accounting must cover every sealed fixture exactly once")

    prediction_by_id = {item.fixture.fixture_id: item for item in predictions}
    for fixture_id, record in by_fixture.items():
        if record.settled_prediction is None:
            continue
        supplied_prediction = prediction_by_id[fixture_id]
        if (
            fresh.canonical_sealed_fresh_prediction_bytes(
                record.settled_prediction.prediction
            )
            != fresh.canonical_sealed_fresh_prediction_bytes(supplied_prediction)
        ):
            raise _error("settled terminal does not bind the exact supplied sealed prediction")
    return by_fixture


def evaluate_fresh_holdout_confirmation(
    *,
    prediction_assessments: Sequence[fresh.FreshPredictionAssessment],
    terminal_records: Sequence[TerminalSettlementRecord],
    selected_close_utc: dt.datetime,
    evaluated_at_utc: dt.datetime,
) -> dict[str, Any]:
    """Evaluate the frozen fresh confirmation only after terminal settlement accounting."""
    verify_reviewed_dependencies()
    assessments = _validate_assessments(prediction_assessments)
    values = tuple(
        item.sealed_prediction
        for item in assessments
        if item.disposition is fresh.PredictionDisposition.SEALED_COMPLETE_CASE
        and item.sealed_prediction is not None
    )
    close = _utc(selected_close_utc, "selected_close_utc")
    evaluated = _utc(evaluated_at_utc, "evaluated_at_utc")
    if close.time() != dt.time.min:
        raise _error("selected close must be an exact UTC midnight")
    if evaluated < close + dt.timedelta(hours=24):
        raise _error("confirmation cannot be evaluated before the 24-hour settlement tail")
    if evaluated < close:
        raise _error("evaluated_at cannot precede selected close")

    start = control.holdout_start_utc()
    try:
        boundary = fresh.evaluate_holdout_boundary(
            values,
            holdout_start=start,
            boundary=close,
        )
    except fresh.FotMobFreshHoldoutError as exc:
        raise _error(str(exc)) from exc

    decision = boundary["decision"]
    allowed = {
        fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value,
        fresh.HoldoutBoundaryDecision.CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION.value,
    }
    if decision not in allowed:
        raise _error("selected close is not a terminal count-only holdout boundary")

    terminals = _validate_terminals(terminal_records, values)
    selected_assessments = tuple(
        item
        for item in assessments
        if (
            start <= item.fixture.capture_observed_at
            and start <= item.fixture.kickoff_utc < close
        )
    )
    selected = tuple(
        item
        for item in values
        if (
            start <= item.fixture.capture_observed_at
            and start <= item.fixture.kickoff_utc < close
        )
    )
    selected_ids = {item.fixture.fixture_id for item in selected}
    if boundary["coverage"]["complete_case_fixture_count"] != len(selected):
        raise _error("selected population differs from revalidated count-only coverage")

    for prediction in values:
        fixture_id = prediction.fixture.fixture_id
        record = terminals[fixture_id]
        if fixture_id not in selected_ids:
            if record.disposition is not TerminalDisposition.EXCLUDED_OUTSIDE_SELECTED_CLOSE:
                raise _error(
                    "sealed fixture outside selected close must carry exact outside-close terminal"
                )
        elif record.disposition is TerminalDisposition.EXCLUDED_OUTSIDE_SELECTED_CLOSE:
            raise _error("selected population fixture cannot be marked outside selected close")

    selected_terminal_records = tuple(terminals[item.fixture.fixture_id] for item in selected)
    settled = tuple(
        record.settled_prediction
        for record in selected_terminal_records
        if record.settled_prediction is not None
    )
    scored = tuple(item for item in settled if item is not None)
    selected_missing = tuple(
        item
        for item in selected_assessments
        if item.disposition is fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES
    )
    missing_feature_counts: Counter[str] = Counter()
    for item in selected_missing:
        missing_feature_counts.update(item.missing_feature_ids)

    competition_reports = _competition_reports(
        selected_assessments=selected_assessments,
        selected_predictions=selected,
        terminals=terminals,
    )

    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evaluator_id": EVALUATOR_ID,
        "evaluator_state": EVALUATOR_STATE,
        "holdout_start_utc": _utc_text(start),
        "selected_close_utc": _utc_text(close),
        "evaluated_at_utc": _utc_text(evaluated),
        "settlement_tail_end_utc": _utc_text(close + dt.timedelta(hours=24)),
        "count_only_boundary": boundary,
        "prediction_assessment_count_before_close": len(selected_assessments),
        "selected_complete_case_count": len(selected),
        "missing_feature_prediction_count": len(selected_missing),
        "missing_feature_id_counts": {
            key: missing_feature_counts[key] for key in sorted(missing_feature_counts)
        },
        "scored_ordinary_ft_count": len(scored),
        "missing_or_excluded_settlement_count": len(selected) - len(scored),
        "terminal_disposition_counts": _terminal_counts(selected_terminal_records),
        "competition_reports": competition_reports,
        "pooled_metrics": None,
        "pooled_gates": None,
        "robustness": None,
        "result_state": None,
        "all_confirmation_gates_pass": False,
        "automatic_successor_approval": False,
        "cross_runtime_bit_identity_claimed": False,
        "known_pr77_machine_precision_canonicalization_gap_cleared": False,
        "fresh_labels_refit_performed": False,
        "outcome_or_performance_input_used_for_close": False,
        "network_acquisition_performed": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }

    if (
        decision
        == fresh.HoldoutBoundaryDecision.CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION.value
    ):
        base["result_state"] = RESULT_INSUFFICIENT_COVERAGE
        return base

    if not scored:
        base["pooled_gates"] = {
            "all_pooled_gates_pass": False,
            "reason": "NO_SCORED_REVIEWED_ORDINARY_FT_SETTLEMENTS",
        }
        base["robustness"] = {
            "all_robustness_gates_pass": False,
            "reason": "NO_SCORED_REVIEWED_ORDINARY_FT_SETTLEMENTS",
        }
        base["result_state"] = RESULT_GATE_FAILED_REVIEW_REQUIRED
        return base

    pooled = _metrics(scored)
    pooled_gate_values = _pooled_gates(pooled)
    pooled_gates = dict(pooled_gate_values)
    pooled_gates["all_pooled_gates_pass"] = all(pooled_gate_values.values())

    qualifying_values = boundary["coverage"]["qualifying_primary_ids"]
    if (
        type(qualifying_values) is not list
        or any(type(value) is not int or value < 1 for value in qualifying_values)
    ):
        raise _error("count-only qualifying primaryId payload changed")
    qualifying_primary_ids = tuple(qualifying_values)
    robustness = _robustness(
        qualifying_primary_ids=qualifying_primary_ids,
        settled=scored,
    )
    all_pass = (
        pooled_gates["all_pooled_gates_pass"]
        and robustness["all_robustness_gates_pass"]
    )
    base["pooled_metrics"] = pooled
    base["pooled_gates"] = pooled_gates
    base["robustness"] = robustness
    base["all_confirmation_gates_pass"] = all_pass
    base["result_state"] = (
        RESULT_SIGNAL_REVIEW_REQUIRED if all_pass else RESULT_GATE_FAILED_REVIEW_REQUIRED
    )
    return base


def canonical_fresh_holdout_confirmation_result_bytes(value: Mapping[str, Any]) -> bytes:
    if not isinstance(value, Mapping):
        raise _error("confirmation result must be a mapping")
    return _canonical(dict(value))


def sha256_fresh_holdout_confirmation_result(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_fresh_holdout_confirmation_result_bytes(value)
    ).hexdigest()


def implementation_receipt() -> dict[str, Any]:
    """Describe this pure evaluator without inspecting or executing fresh labels."""
    verify_reviewed_dependencies()
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluator_id": EVALUATOR_ID,
        "evaluator_state": EVALUATOR_STATE,
        "reviewed_dependency_blobs": {
            "pr148_protocol": PR148_PROTOCOL_BLOB_SHA,
            "pr149_core": PR149_CORE_BLOB_SHA,
            "pr150_control": PR150_CONTROL_BLOB_SHA,
            "pr151_runner": PR151_RUNNER_BLOB_SHA,
        },
        "result_states": {
            "all_gates_pass": RESULT_SIGNAL_REVIEW_REQUIRED,
            "coverage_insufficient": RESULT_INSUFFICIENT_COVERAGE,
            "performance_gate_failed": RESULT_GATE_FAILED_REVIEW_REQUIRED,
        },
        "fresh_holdout_result_evaluated": False,
        "fresh_labels_read": False,
        "fresh_labels_refit_performed": False,
        "network_acquisition_performed": False,
        "automatic_successor_approval": False,
        "cross_runtime_bit_identity_claimed": False,
        "known_pr77_machine_precision_canonicalization_gap_cleared": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


__all__ = [
    "EVALUATOR_ID",
    "EVALUATOR_STATE",
    "FreshHoldoutConfirmationEvaluatorError",
    "NEXT_REQUIRED_BOUNDARY",
    "RESULT_GATE_FAILED_REVIEW_REQUIRED",
    "RESULT_INSUFFICIENT_COVERAGE",
    "RESULT_SIGNAL_REVIEW_REQUIRED",
    "TerminalDisposition",
    "TerminalSettlementRecord",
    "canonical_fresh_holdout_confirmation_result_bytes",
    "evaluate_fresh_holdout_confirmation",
    "implementation_receipt",
    "sha256_fresh_holdout_confirmation_result",
    "verify_reviewed_dependencies",
]
