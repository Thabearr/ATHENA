"""Frozen Stage 4A/4B Win Either Half analytical inference.

The runtime consumes only a committed, ancestry-bound inference state and the
exact frozen 74-feature mapping.  It never fits sklearn objects and grants no
pricing, selection, production, or betting authority.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from domain.win_either_half_features import PRE_MATCH_FEATURE_NAMES


SCHEMA_VERSION = 1
DATASET_NAME = "athena-win-either-half-analytical-inference-state-v1"
BASE_MODEL_IDENTIFIER = "logistic_l2_c0.1_v1"
HOME_CALIBRATION_IDENTIFIER = "isotonic_calibration_v1"
AWAY_CALIBRATION_IDENTIFIER = "identity_calibration_v1"
CANONICAL_PROBABILITY_DECIMAL_PLACES = 12
INFERENCE_STATE_ARTIFACT_SHA256 = (
    "2b2490f7270b6e69646bba59c4979cc6f2cc462b3e9ef2a745583d9fa00a4cd2"
)
INFERENCE_STATE_ARTIFACT_SIZE = 23_968
INFERENCE_STATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "model-states"
    / "win-either-half-analytical-inference-v1.json"
)

_TARGETS = (
    "home_win_either_half_yes",
    "away_win_either_half_yes",
)
FROZEN_SOURCE_ANCESTRY = {
    "stage_3_feature_csv": {
        "byte_size": 8_032_209,
        "rows": 21_791,
        "sha256": "68547ae9670703c59d68367d8fa1ef067e7410d8beb842ad0aec2151f0777e7b",
    },
    "stage_4_benchmark_summary": {
        "byte_size": 165_692,
        "sha256": "e6c2157f137a7d243f38d3a55a087e9b2ab9cb2536ab2a1544e1125362c9253f",
    },
    "stage_4_predictions": {
        "byte_size": 5_063_993,
        "rows": 43_582,
        "sha256": "02790fdb2c4549adb27d3a086d522491215ac7a2b9889375208cae96f32873a1",
    },
    "stage_4b_calibration_summary": {
        "byte_size": 65_337,
        "sha256": "957ffb850354173f84f1f3b44e8e5bff83c74357bdebc90c091c1f5ca997dfda",
    },
    "stage_4b_calibrated_predictions": {
        "byte_size": 6_705_242,
        "rows": 36_318,
        "sha256": "6e931ae156f7319bc9cba2647e746471422adafad8e431981bdb573ca64c44d4",
    },
}
FROZEN_BASE_CONFIGURATION = {
    "family": "logistic_regression",
    "identifier": BASE_MODEL_IDENTIFIER,
    "parameters": {
        "C": 0.1,
        "max_iter": 2000,
        "random_state": 1729,
        "solver": "lbfgs",
    },
    "preprocessing": "train_median_imputation_and_standard_scaling",
}
FROZEN_TRAINING_CONTRACT = {
    "base_fit_rows": 14_267,
    "base_fit_split": "TRAIN",
    "calibration_fit_oof_rows_per_target": 10_635,
    "final_test_rows": 4_048,
    "validation_rows": 3_476,
}
INFERENCE_AUTHORITY = {
    "analytical_prediction_authorized": True,
    "bet_authorized": False,
    "pricing_authorized": False,
    "production_approval_authorized": False,
    "selection_authorized": False,
    "value_authorized": False,
}


class WinEitherHalfInferenceError(ValueError):
    """Raised when frozen state or prospective predictors fail closed."""


def _canonical_json_bytes(value: Any) -> bytes:
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
    except (TypeError, ValueError) as exc:
        raise WinEitherHalfInferenceError("value is not canonical JSON") from exc


def canonical_win_either_half_inference_state_bytes(state: Mapping[str, Any]) -> bytes:
    validated = validate_win_either_half_inference_state(state)
    return _canonical_json_bytes(_deep_thaw(validated))


def sha256_win_either_half_inference_state(state: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_win_either_half_inference_state_bytes(state)
    ).hexdigest()


def _finite_vector(value: Any, label: str, length: int) -> tuple[float, ...]:
    if type(value) is not list or len(value) != length:
        raise WinEitherHalfInferenceError(f"{label} must contain exactly {length} values")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise WinEitherHalfInferenceError(f"{label} values must be numeric")
        numeric = float(item)
        if not math.isfinite(numeric):
            raise WinEitherHalfInferenceError(f"{label} values must be finite")
        result.append(numeric)
    return tuple(result)


def _exact_keys(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise WinEitherHalfInferenceError(f"{label} fields differ from frozen contract")
    return value


def _deep_freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


def _fingerprint_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(state)
    payload.pop("state_fingerprint_sha256", None)
    return payload


def fingerprint_win_either_half_inference_state(state: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(_deep_thaw(_fingerprint_payload(state)))
    ).hexdigest()


def validate_win_either_half_inference_state(
    state: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(state, Mapping):
        raise WinEitherHalfInferenceError("inference state must be a mapping")
    mutable = _deep_thaw(state)
    _exact_keys(
        mutable,
        {
            "authority",
            "base_configuration",
            "canonical_probability_decimal_places",
            "dataset_name",
            "feature_order",
            "preprocessing",
            "schema_version",
            "source_ancestry",
            "state_fingerprint_sha256",
            "targets",
            "training_contract",
        },
        "inference state",
    )
    if mutable["schema_version"] != SCHEMA_VERSION or mutable["dataset_name"] != DATASET_NAME:
        raise WinEitherHalfInferenceError("inference state identity drifted")
    if mutable["canonical_probability_decimal_places"] != CANONICAL_PROBABILITY_DECIMAL_PLACES:
        raise WinEitherHalfInferenceError("probability precision drifted")
    if mutable["source_ancestry"] != FROZEN_SOURCE_ANCESTRY:
        raise WinEitherHalfInferenceError("frozen research ancestry drifted")
    if mutable["base_configuration"] != FROZEN_BASE_CONFIGURATION:
        raise WinEitherHalfInferenceError("frozen base configuration drifted")
    if mutable["training_contract"] != FROZEN_TRAINING_CONTRACT:
        raise WinEitherHalfInferenceError("frozen training contract drifted")
    if mutable["authority"] != INFERENCE_AUTHORITY:
        raise WinEitherHalfInferenceError("inference authority metadata drifted")
    if tuple(mutable["feature_order"]) != PRE_MATCH_FEATURE_NAMES:
        raise WinEitherHalfInferenceError("frozen 74-feature order drifted")
    if len(PRE_MATCH_FEATURE_NAMES) != 74:
        raise WinEitherHalfInferenceError("frozen feature count drifted")

    preprocessing = _exact_keys(
        mutable["preprocessing"],
        {"feature_names", "means", "medians", "scales"},
        "preprocessing",
    )
    if tuple(preprocessing["feature_names"]) != PRE_MATCH_FEATURE_NAMES:
        raise WinEitherHalfInferenceError("preprocessor feature order drifted")
    for label in ("medians", "means", "scales"):
        values = _finite_vector(preprocessing[label], label, 74)
        if label == "scales" and any(item <= 0.0 for item in values):
            raise WinEitherHalfInferenceError("preprocessor scales must be positive")

    targets = _exact_keys(mutable["targets"], set(_TARGETS), "targets")
    for target in _TARGETS:
        target_state = _exact_keys(
            targets[target],
            {
                "base_model_identifier",
                "calibration",
                "coefficient_order",
                "coefficients",
                "intercept",
            },
            target,
        )
        if target_state["base_model_identifier"] != BASE_MODEL_IDENTIFIER:
            raise WinEitherHalfInferenceError("base model identifier drifted")
        if tuple(target_state["coefficient_order"]) != PRE_MATCH_FEATURE_NAMES:
            raise WinEitherHalfInferenceError("coefficient order drifted")
        _finite_vector(target_state["coefficients"], f"{target} coefficients", 74)
        _finite_vector([target_state["intercept"]], f"{target} intercept", 1)

    home_calibration = _exact_keys(
        targets["home_win_either_half_yes"]["calibration"],
        {"family", "identifier", "out_of_bounds", "x_thresholds", "y_thresholds"},
        "home calibration",
    )
    if (
        home_calibration["identifier"] != HOME_CALIBRATION_IDENTIFIER
        or home_calibration["family"] != "isotonic"
        or home_calibration["out_of_bounds"] != "clip"
    ):
        raise WinEitherHalfInferenceError("home isotonic calibration drifted")
    x_values = _finite_vector(
        home_calibration["x_thresholds"],
        "home isotonic x thresholds",
        len(home_calibration["x_thresholds"]),
    )
    y_values = _finite_vector(
        home_calibration["y_thresholds"],
        "home isotonic y thresholds",
        len(home_calibration["y_thresholds"]),
    )
    if len(x_values) < 2 or len(x_values) != len(y_values):
        raise WinEitherHalfInferenceError("home isotonic threshold dimensions drifted")
    if any(left >= right for left, right in zip(x_values, x_values[1:])):
        raise WinEitherHalfInferenceError("home isotonic x thresholds must increase")
    if any(not 0.0 <= item <= 1.0 for item in y_values) or any(
        left > right for left, right in zip(y_values, y_values[1:])
    ):
        raise WinEitherHalfInferenceError("home isotonic y thresholds are invalid")

    away_calibration = _exact_keys(
        targets["away_win_either_half_yes"]["calibration"],
        {"family", "identifier"},
        "away calibration",
    )
    if away_calibration != {
        "family": "identity",
        "identifier": AWAY_CALIBRATION_IDENTIFIER,
    }:
        raise WinEitherHalfInferenceError("away identity calibration drifted")

    fingerprint = mutable["state_fingerprint_sha256"]
    if (
        type(fingerprint) is not str
        or len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
        or fingerprint_win_either_half_inference_state(mutable) != fingerprint
    ):
        raise WinEitherHalfInferenceError("inference state fingerprint mismatch")
    return _deep_freeze(mutable)


def load_win_either_half_inference_state(
    path: Path = INFERENCE_STATE_PATH,
) -> Mapping[str, Any]:
    if not isinstance(path, Path):
        raise WinEitherHalfInferenceError("inference state path must be a Path")
    try:
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WinEitherHalfInferenceError("cannot load frozen inference state") from exc
    if (
        len(content) != INFERENCE_STATE_ARTIFACT_SIZE
        or hashlib.sha256(content).hexdigest() != INFERENCE_STATE_ARTIFACT_SHA256
    ):
        raise WinEitherHalfInferenceError("frozen inference state artifact identity drifted")
    validated = validate_win_either_half_inference_state(payload)
    if content != _canonical_json_bytes(_deep_thaw(validated)):
        raise WinEitherHalfInferenceError("inference state file is not canonical JSON")
    return validated


def _canonical_probability(value: float) -> float:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise WinEitherHalfInferenceError("probability must be finite and in [0, 1]")
    # Stage 4A/4B canonicalized arrays with numpy.round.  For probabilities,
    # its frozen operation is the equivalent scale/rint/unscale sequence, not
    # Python's direct round(value, places), which differs at some half-ULPs.
    scale = 10 ** CANONICAL_PROBABILITY_DECIMAL_PLACES
    rounded = round(value * scale) / scale
    return 0.0 if rounded == 0.0 else rounded


def _sigmoid(value: float) -> float:
    # Match the frozen sklearn/scipy expit path for finite deployed logits.
    # The algebraically equivalent negative branch e^x/(1+e^x) can differ by
    # one ULP and cross the 12-decimal canonical boundary.
    if value < -709.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def _isotonic_transform(probability: float, calibration: Mapping[str, Any]) -> float:
    x_values = tuple(float(item) for item in calibration["x_thresholds"])
    y_values = tuple(float(item) for item in calibration["y_thresholds"])
    if probability <= x_values[0]:
        return _canonical_probability(y_values[0])
    if probability >= x_values[-1]:
        return _canonical_probability(y_values[-1])
    left = bisect.bisect_right(x_values, probability) - 1
    if probability == x_values[left]:
        return _canonical_probability(y_values[left])
    fraction = (probability - x_values[left]) / (
        x_values[left + 1] - x_values[left]
    )
    value = y_values[left] + fraction * (y_values[left + 1] - y_values[left])
    return _canonical_probability(value)


def _base_probability(
    values: Sequence[float],
    target_state: Mapping[str, Any],
) -> float:
    coefficients = target_state["coefficients"]
    # Stage 4's single-threaded BLAS ddot uses its frozen five-term unroll.
    # Reproduce that association explicitly in stdlib Python: a mathematically
    # equivalent fsum can cross a canonical 12-decimal boundary by one unit.
    products = tuple(
        float(coefficient) * value
        for coefficient, value in zip(coefficients, values)
    )
    dot_product = 0.0
    for offset in range(0, len(products), 5):
        block = 0.0
        for product in products[offset : offset + 5]:
            block += product
        dot_product += block
    linear = float(target_state["intercept"]) + dot_product
    return _canonical_probability(_sigmoid(linear))


def _calibrate_base_probability(
    probability: float,
    target_state: Mapping[str, Any],
) -> float:
    """Apply the exact deployed stdlib calibration path to one base value."""

    calibration = target_state["calibration"]
    if calibration["identifier"] == HOME_CALIBRATION_IDENTIFIER:
        return _isotonic_transform(probability, calibration)
    if calibration["identifier"] == AWAY_CALIBRATION_IDENTIFIER:
        return _canonical_probability(probability)
    raise WinEitherHalfInferenceError("target calibration identifier drifted")


@dataclass(frozen=True)
class WinEitherHalfAnalyticalPrediction:
    home_yes_probability: float
    home_no_probability: float
    away_yes_probability: float
    away_no_probability: float
    home_base_yes_probability: float
    away_base_yes_probability: float
    home_base_model_identifier: str
    away_base_model_identifier: str
    home_calibration_identifier: str
    away_calibration_identifier: str
    inference_state_fingerprint_sha256: str
    analytical_prediction_authorized: bool = True
    pricing_authorized: bool = False
    value_authorized: bool = False
    selection_authorized: bool = False
    production_approval_authorized: bool = False
    bet_authorized: bool = False

    def __post_init__(self) -> None:
        probabilities = (
            self.home_yes_probability,
            self.home_no_probability,
            self.away_yes_probability,
            self.away_no_probability,
            self.home_base_yes_probability,
            self.away_base_yes_probability,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, float)
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
            for value in probabilities
        ):
            raise WinEitherHalfInferenceError(
                "analytical probabilities must be finite canonical floats"
            )
        if _canonical_probability(
            self.home_yes_probability + self.home_no_probability
        ) != 1.0 or _canonical_probability(
            self.away_yes_probability + self.away_no_probability
        ) != 1.0:
            raise WinEitherHalfInferenceError("YES/NO probabilities must complement")
        if (
            self.home_base_model_identifier != BASE_MODEL_IDENTIFIER
            or self.away_base_model_identifier != BASE_MODEL_IDENTIFIER
            or self.home_calibration_identifier != HOME_CALIBRATION_IDENTIFIER
            or self.away_calibration_identifier != AWAY_CALIBRATION_IDENTIFIER
        ):
            raise WinEitherHalfInferenceError("prediction model identity drifted")
        if (
            type(self.inference_state_fingerprint_sha256) is not str
            or len(self.inference_state_fingerprint_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.inference_state_fingerprint_sha256
            )
        ):
            raise WinEitherHalfInferenceError("prediction state fingerprint is invalid")
        if (
            self.analytical_prediction_authorized is not True
            or self.pricing_authorized is not False
            or self.value_authorized is not False
            or self.selection_authorized is not False
            or self.production_approval_authorized is not False
            or self.bet_authorized is not False
        ):
            raise WinEitherHalfInferenceError("prediction authority metadata drifted")

    def to_dict(self) -> dict[str, Any]:
        return {
            "analytical_prediction_authorized": self.analytical_prediction_authorized,
            "away_base_model_identifier": self.away_base_model_identifier,
            "away_base_yes_probability": self.away_base_yes_probability,
            "away_calibration_identifier": self.away_calibration_identifier,
            "away_no_probability": self.away_no_probability,
            "away_yes_probability": self.away_yes_probability,
            "bet_authorized": self.bet_authorized,
            "home_base_model_identifier": self.home_base_model_identifier,
            "home_base_yes_probability": self.home_base_yes_probability,
            "home_calibration_identifier": self.home_calibration_identifier,
            "home_no_probability": self.home_no_probability,
            "home_yes_probability": self.home_yes_probability,
            "inference_state_fingerprint_sha256": (
                self.inference_state_fingerprint_sha256
            ),
            "pricing_authorized": self.pricing_authorized,
            "production_approval_authorized": self.production_approval_authorized,
            "selection_authorized": self.selection_authorized,
            "value_authorized": self.value_authorized,
        }


def _predict_win_either_half_with_state(
    feature_row: Mapping[str, Any],
    state: Mapping[str, Any],
) -> WinEitherHalfAnalyticalPrediction:
    frozen = validate_win_either_half_inference_state(state)
    if not isinstance(feature_row, Mapping):
        raise WinEitherHalfInferenceError("feature_row must be a mapping")
    supplied = set(feature_row)
    expected = set(PRE_MATCH_FEATURE_NAMES)
    if supplied != expected:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        raise WinEitherHalfInferenceError(
            f"feature namespace mismatch: missing={missing}, extra={extra}"
        )

    preprocessing = frozen["preprocessing"]
    scaled = []
    for index, name in enumerate(PRE_MATCH_FEATURE_NAMES):
        value = feature_row[name]
        if value is None:
            numeric = float(preprocessing["medians"][index])
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise WinEitherHalfInferenceError(
                    f"feature {name} must be numeric or None"
                )
            numeric = float(value)
            if not math.isfinite(numeric):
                raise WinEitherHalfInferenceError(f"feature {name} must be finite")
        scaled.append(
            (numeric - float(preprocessing["means"][index]))
            / float(preprocessing["scales"][index])
        )

    home_state = frozen["targets"]["home_win_either_half_yes"]
    away_state = frozen["targets"]["away_win_either_half_yes"]
    home_base = _base_probability(scaled, home_state)
    away_base = _base_probability(scaled, away_state)
    home_yes = _calibrate_base_probability(home_base, home_state)
    away_yes = _calibrate_base_probability(away_base, away_state)
    home_no = _canonical_probability(1.0 - home_yes)
    away_no = _canonical_probability(1.0 - away_yes)
    return WinEitherHalfAnalyticalPrediction(
        home_yes_probability=home_yes,
        home_no_probability=home_no,
        away_yes_probability=away_yes,
        away_no_probability=away_no,
        home_base_yes_probability=home_base,
        away_base_yes_probability=away_base,
        home_base_model_identifier=BASE_MODEL_IDENTIFIER,
        away_base_model_identifier=BASE_MODEL_IDENTIFIER,
        home_calibration_identifier=HOME_CALIBRATION_IDENTIFIER,
        away_calibration_identifier=AWAY_CALIBRATION_IDENTIFIER,
        inference_state_fingerprint_sha256=frozen["state_fingerprint_sha256"],
    )


def predict_win_either_half(
    feature_row: Mapping[str, Any],
) -> WinEitherHalfAnalyticalPrediction:
    """Return frozen Home/Away YES/NO analytical probabilities only.

    The caller supplies predictors only. The exact committed state is always
    loaded internally, so coefficients and calibration cannot be overridden.
    """

    return _predict_win_either_half_with_state(
        feature_row,
        load_win_either_half_inference_state(),
    )


__all__ = [
    "AWAY_CALIBRATION_IDENTIFIER",
    "BASE_MODEL_IDENTIFIER",
    "CANONICAL_PROBABILITY_DECIMAL_PLACES",
    "DATASET_NAME",
    "FROZEN_BASE_CONFIGURATION",
    "FROZEN_SOURCE_ANCESTRY",
    "FROZEN_TRAINING_CONTRACT",
    "HOME_CALIBRATION_IDENTIFIER",
    "INFERENCE_STATE_PATH",
    "INFERENCE_STATE_ARTIFACT_SHA256",
    "INFERENCE_STATE_ARTIFACT_SIZE",
    "INFERENCE_AUTHORITY",
    "SCHEMA_VERSION",
    "WinEitherHalfAnalyticalPrediction",
    "WinEitherHalfInferenceError",
    "canonical_win_either_half_inference_state_bytes",
    "fingerprint_win_either_half_inference_state",
    "load_win_either_half_inference_state",
    "predict_win_either_half",
    "sha256_win_either_half_inference_state",
    "validate_win_either_half_inference_state",
]
