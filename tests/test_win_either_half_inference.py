import ast
import hashlib
import inspect
import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from domain.markets import MarketId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    CalibrationStatus,
    MODEL_STATUS_REGISTRY,
    MissingInputPolicy,
    PricingAuthority,
    ProbabilityInputNamespace,
    SelectionAuthority,
)
from domain.win_either_half_features import PRE_MATCH_FEATURE_NAMES
from domain.win_either_half_inference import (
    AWAY_CALIBRATION_IDENTIFIER,
    BASE_MODEL_IDENTIFIER,
    CANONICAL_PROBABILITY_DECIMAL_PLACES,
    FROZEN_SOURCE_ANCESTRY,
    HOME_CALIBRATION_IDENTIFIER,
    INFERENCE_STATE_ARTIFACT_SHA256,
    INFERENCE_STATE_ARTIFACT_SIZE,
    INFERENCE_STATE_PATH,
    WinEitherHalfInferenceError,
    _predict_win_either_half_with_state,
    canonical_win_either_half_inference_state_bytes,
    fingerprint_win_either_half_inference_state,
    load_win_either_half_inference_state,
    predict_win_either_half,
    validate_win_either_half_inference_state,
)


class WinEitherHalfInferenceTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

    @staticmethod
    def _mutable_state():
        return json.loads(INFERENCE_STATE_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def _feature_row(value=0.0):
        return {name: value for name in PRE_MATCH_FEATURE_NAMES}

    @staticmethod
    def _refresh_fingerprint(state):
        state["state_fingerprint_sha256"] = (
            fingerprint_win_either_half_inference_state(state)
        )
        return state

    @staticmethod
    def _canonical(value):
        rounded = round(float(value), CANONICAL_PROBABILITY_DECIMAL_PLACES)
        return 0.0 if rounded == 0.0 else rounded

    @classmethod
    def _independent_isotonic(cls, probability, calibration):
        xs = calibration["x_thresholds"]
        ys = calibration["y_thresholds"]
        if probability <= xs[0]:
            return cls._canonical(ys[0])
        if probability >= xs[-1]:
            return cls._canonical(ys[-1])
        for index in range(len(xs) - 1):
            if xs[index] <= probability <= xs[index + 1]:
                fraction = (probability - xs[index]) / (xs[index + 1] - xs[index])
                return cls._canonical(
                    ys[index] + fraction * (ys[index + 1] - ys[index])
                )
        raise AssertionError("probability did not enter an isotonic interval")

    def test_artifact_is_exact_canonical_ancestry_bound_state(self):
        content = INFERENCE_STATE_PATH.read_bytes()
        state = load_win_either_half_inference_state()
        self.assertEqual(len(content), INFERENCE_STATE_ARTIFACT_SIZE)
        self.assertEqual(
            hashlib.sha256(content).hexdigest(),
            INFERENCE_STATE_ARTIFACT_SHA256,
        )
        self.assertEqual(
            content,
            canonical_win_either_half_inference_state_bytes(state),
        )
        self.assertEqual(dict(state["source_ancestry"]), FROZEN_SOURCE_ANCESTRY)
        self.assertEqual(
            state["state_fingerprint_sha256"],
            "7604203a4273e0428190ce37447437016c7a081d14e4fba8b7d16f44ec590d5b",
        )
        self.assertNotIn("fixture_identity", content.decode("utf-8"))
        self.assertNotIn("kickoff_utc", content.decode("utf-8"))

    def test_feature_preprocessor_model_and_calibrator_dimensions_are_exact(self):
        state = load_win_either_half_inference_state()
        self.assertEqual(tuple(state["feature_order"]), PRE_MATCH_FEATURE_NAMES)
        self.assertEqual(len(PRE_MATCH_FEATURE_NAMES), 74)
        for key in ("medians", "means", "scales"):
            self.assertEqual(len(state["preprocessing"][key]), 74)
        for target in (
            "home_win_either_half_yes",
            "away_win_either_half_yes",
        ):
            self.assertEqual(len(state["targets"][target]["coefficients"]), 74)
            self.assertEqual(
                tuple(state["targets"][target]["coefficient_order"]),
                PRE_MATCH_FEATURE_NAMES,
            )
        home_calibration = state["targets"]["home_win_either_half_yes"][
            "calibration"
        ]
        self.assertEqual(len(home_calibration["x_thresholds"]), 70)
        self.assertEqual(
            len(home_calibration["x_thresholds"]),
            len(home_calibration["y_thresholds"]),
        )
        self.assertEqual(
            state["targets"]["away_win_either_half_yes"]["calibration"],
            {"family": "identity", "identifier": AWAY_CALIBRATION_IDENTIFIER},
        )

    def test_runtime_accepts_no_state_or_price_override_and_cannot_refit(self):
        self.assertEqual(
            tuple(inspect.signature(predict_win_either_half).parameters),
            ("feature_row",),
        )
        source = (
            self.REPOSITORY_ROOT / "domain" / "win_either_half_inference.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            imported_roots.isdisjoint({"sklearn", "numpy", "scipy", "joblib"})
        )
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"fit", "fit_transform"}
                for node in ast.walk(tree)
            )
        )
        self.assertNotIn("bookmaker_odds", source)

    def test_missing_extra_bool_nan_and_infinite_features_fail_closed(self):
        valid = self._feature_row()
        for mutation in ("missing", "extra"):
            row = dict(valid)
            if mutation == "missing":
                row.pop(PRE_MATCH_FEATURE_NAMES[0])
            else:
                row["unknown_feature"] = 1.0
            with self.subTest(mutation=mutation):
                with self.assertRaises(WinEitherHalfInferenceError):
                    predict_win_either_half(row)
        for value in (True, False, float("nan"), float("inf"), float("-inf"), "1"):
            row = dict(valid)
            row[PRE_MATCH_FEATURE_NAMES[0]] = value
            with self.subTest(value=value):
                with self.assertRaises(WinEitherHalfInferenceError):
                    predict_win_either_half(row)

    def test_train_median_scaling_and_logistic_math_are_exact(self):
        state = self._mutable_state()
        means = state["preprocessing"]["means"]
        row = {name: means[index] for index, name in enumerate(PRE_MATCH_FEATURE_NAMES)}
        row[PRE_MATCH_FEATURE_NAMES[0]] = None
        scaled = [0.0] * 74
        scaled[0] = (
            state["preprocessing"]["medians"][0] - means[0]
        ) / state["preprocessing"]["scales"][0]

        prediction = _predict_win_either_half_with_state(row, state)
        for target, actual in (
            ("home_win_either_half_yes", prediction.home_base_yes_probability),
            ("away_win_either_half_yes", prediction.away_base_yes_probability),
        ):
            target_state = state["targets"][target]
            linear = target_state["intercept"] + math.fsum(
                coefficient * value
                for coefficient, value in zip(target_state["coefficients"], scaled)
            )
            expected = self._canonical(1.0 / (1.0 + math.exp(-linear)))
            self.assertEqual(actual, expected)
        self.assertEqual(
            prediction.home_yes_probability,
            self._independent_isotonic(
                prediction.home_base_yes_probability,
                state["targets"]["home_win_either_half_yes"]["calibration"],
            ),
        )
        self.assertEqual(
            prediction.away_yes_probability,
            prediction.away_base_yes_probability,
        )

    def test_home_isotonic_clips_and_interpolates_while_away_is_identity(self):
        for raw, expected in ((0.1, 0.1), (0.35, 0.25), (0.5, 0.4), (0.95, 0.9)):
            state = self._mutable_state()
            for target in state["targets"].values():
                target["coefficients"] = [0.0] * 74
            state["targets"]["home_win_either_half_yes"]["intercept"] = math.log(
                raw / (1.0 - raw)
            )
            state["targets"]["home_win_either_half_yes"]["calibration"] = {
                "family": "isotonic",
                "identifier": HOME_CALIBRATION_IDENTIFIER,
                "out_of_bounds": "clip",
                "x_thresholds": [0.2, 0.5, 0.8],
                "y_thresholds": [0.1, 0.4, 0.9],
            }
            away_raw = 0.1234567890124
            state["targets"]["away_win_either_half_yes"]["intercept"] = math.log(
                away_raw / (1.0 - away_raw)
            )
            self._refresh_fingerprint(state)
            prediction = _predict_win_either_half_with_state(
                self._feature_row(), state
            )
            with self.subTest(raw=raw):
                self.assertEqual(prediction.home_yes_probability, expected)
                self.assertEqual(
                    prediction.away_yes_probability,
                    self._canonical(away_raw),
                )

    def test_outputs_are_canonical_complements_with_frozen_identities_and_authority(self):
        prediction = predict_win_either_half(self._feature_row(None))
        self.assertEqual(
            prediction.home_yes_probability + prediction.home_no_probability,
            1.0,
        )
        self.assertEqual(
            prediction.away_yes_probability + prediction.away_no_probability,
            1.0,
        )
        self.assertEqual(prediction.home_base_model_identifier, BASE_MODEL_IDENTIFIER)
        self.assertEqual(prediction.away_base_model_identifier, BASE_MODEL_IDENTIFIER)
        self.assertEqual(
            prediction.home_calibration_identifier, HOME_CALIBRATION_IDENTIFIER
        )
        self.assertEqual(
            prediction.away_calibration_identifier, AWAY_CALIBRATION_IDENTIFIER
        )
        self.assertTrue(prediction.analytical_prediction_authorized)
        for field in (
            "pricing_authorized",
            "value_authorized",
            "selection_authorized",
            "production_approval_authorized",
            "bet_authorized",
        ):
            self.assertIs(getattr(prediction, field), False)

    def test_state_mutation_and_noncanonical_or_wrong_artifact_identity_fail(self):
        state = self._mutable_state()
        state["preprocessing"]["medians"][0] += 1.0
        with self.assertRaises(WinEitherHalfInferenceError):
            validate_win_either_half_inference_state(state)
        forged = self._refresh_fingerprint(state)
        content = canonical_win_either_half_inference_state_bytes(forged)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_bytes(content)
            with self.assertRaisesRegex(
                WinEitherHalfInferenceError, "artifact identity drifted"
            ):
                load_win_either_half_inference_state(path)

    def test_weh_registry_uses_only_specialized_namespace_without_authority(self):
        for market in (
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
        ):
            status = MODEL_STATUS_REGISTRY[market]
            with self.subTest(market=market):
                self.assertIs(
                    status.analytical_probability_capability,
                    AnalyticalProbabilityCapability.AVAILABLE,
                )
                self.assertIs(
                    status.probability_input_namespace,
                    ProbabilityInputNamespace.SPECIALIZED_WEH_PRE_MATCH_FEATURES,
                )
                self.assertEqual(status.probability_inputs, PRE_MATCH_FEATURE_NAMES)
                self.assertIs(status.missing_input_policy, MissingInputPolicy.REJECT_MARKET)
                self.assertIs(
                    status.calibration_status,
                    CalibrationStatus.FROZEN_STAGE_4B_CALIBRATION_RESEARCH_EVIDENCE,
                )
                self.assertIs(status.pricing_authority, PricingAuthority.NOT_AUTHORIZED)
                self.assertIs(
                    status.selection_authority, SelectionAuthority.NOT_AUTHORIZED
                )
                self.assertFalse(status.selectable)


if __name__ == "__main__":
    unittest.main()
