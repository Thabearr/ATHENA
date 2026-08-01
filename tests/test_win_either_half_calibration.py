import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import unittest
import warnings
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from domain.markets import MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_benchmarks import (
    CANONICAL_DECIMAL_PLACES,
    ModelConfiguration,
    fit_benchmark_candidate,
    fit_train_preprocessor,
    probability_metrics,
)
from domain.win_either_half_calibration import (
    CALIBRATION_SELECTION_RULE,
    EVALUATION_ROLE_SCOPES,
    PLATT_LOGIT_EPSILON,
    PROBABILITY_BANDS,
    SUBGROUP_MINIMUM_ROWS,
    CalibrationConfiguration,
    CalibrationError,
    build_expanding_oof_predictions,
    build_subgroup_evaluations,
    default_calibration_configurations,
    fit_calibrator,
    run_calibration_research,
    select_calibration_winner,
)
from scripts.export_win_either_half_baseline_benchmarks import (
    render_prediction_csv,
)
from scripts.export_win_either_half_calibration_research import (
    CalibrationExportError,
    build_calibration_manifest,
    compare_calibration_manifests,
    load_verified_benchmark_summary,
    load_verified_stage_4_predictions,
    main,
    render_calibrated_predictions,
    render_calibration_summary,
    render_subgroups,
    selected_model_configurations,
    verify_stage_4_manifest_contract,
    write_calibration_outputs,
)


class WinEitherHalfCalibrationTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    FEATURE_NAMES = ("form", "history_missing")
    TARGETS = (
        "home_win_either_half_yes",
        "away_win_either_half_yes",
    )

    @staticmethod
    def _base_configuration(identifier="logistic_l2_c0.1_v1"):
        return ModelConfiguration(
            identifier=identifier,
            family="logistic_regression",
            complexity_rank=2,
            parameters=(
                ("C", 0.1),
                ("max_iter", 2000),
                ("random_state", 1729),
                ("solver", "lbfgs"),
            ),
            preprocessing="train_median_imputation_and_standard_scaling",
        )

    def _rows(self):
        rows = []
        specifications = (
            ("TRAIN", "2020-21", 8),
            ("TRAIN", "2021-22", 8),
            ("TRAIN", "2022-23", 8),
            ("TRAIN", "2023-24", 8),
            ("VALIDATION", "2024-25", 6),
            ("TEST", "2025-26", 6),
        )
        index = 0
        for split, season, count in specifications:
            for local in range(count):
                rows.append(
                    {
                        "away_win_either_half_yes": int(local % 4 in (0, 1)),
                        "fixture_identity": f"fixture-{index:03d}",
                        "form": ((local * 7 + index) % 17) / 16.0,
                        "history_missing": int(local == 0),
                        "home_win_either_half_yes": int(local % 2 == 0),
                        "kickoff_utc": f"{season[:4]}-08-{local + 1:02d}T12:00:00Z",
                        "league": "E0" if local % 2 == 0 else "D1",
                        "season": season,
                        "split": split,
                    }
                )
                index += 1
        return rows

    def _frozen_predictions(self, rows):
        train = tuple(row for row in rows if row["split"] == "TRAIN")
        preprocessor = fit_train_preprocessor(train, self.FEATURE_NAMES)
        train_imputed, train_scaled, _ = preprocessor.transform(train)
        predictions = []
        for target in self.TARGETS:
            fitted = fit_benchmark_candidate(
                self._base_configuration(),
                train_imputed=train_imputed,
                train_scaled=train_scaled,
                train_targets=np.asarray([row[target] for row in train]),
                target_name=target,
            )
            for split in ("TRAIN", "VALIDATION", "TEST"):
                selected = tuple(row for row in rows if row["split"] == split)
                imputed, scaled, _ = preprocessor.transform(selected)
                probabilities = fitted.predict(imputed, scaled)
                for row, probability in zip(selected, probabilities):
                    predictions.append(
                        {
                            "fixture_identity": row["fixture_identity"],
                            "kickoff_utc": row["kickoff_utc"],
                            "model_identifier": "logistic_l2_c0.1_v1",
                            "predicted_probability": float(probability),
                            "split": split,
                            "target_name": target,
                            "target_value": row[target],
                        }
                    )
        return predictions

    def _run(self, rows=None):
        rows = rows or self._rows()
        configuration = self._base_configuration()
        return run_calibration_research(
            rows,
            self.FEATURE_NAMES,
            selected_model_configurations={
                target: configuration for target in self.TARGETS
            },
            frozen_predictions=self._frozen_predictions(rows),
        )

    def test_expanding_oof_uses_only_earlier_seasons_and_excludes_2020_21(self):
        rows = tuple(row for row in self._rows() if row["split"] == "TRAIN")
        result = build_expanding_oof_predictions(
            rows,
            self.FEATURE_NAMES,
            self._base_configuration(),
            self.TARGETS[0],
        )
        self.assertEqual(
            [fold["prediction_season"] for fold in result["folds"]],
            ["2021-22", "2022-23", "2023-24"],
        )
        self.assertNotIn(
            "2020-21", {row["season"] for row in result["predictions"]}
        )
        for fold in result["folds"]:
            predicted_year = int(fold["prediction_season"][:4])
            self.assertTrue(
                all(int(season[:4]) < predicted_year for season in fold["fit_seasons"])
            )

        changed = deepcopy(rows)
        for row in changed:
            if row["season"] in ("2022-23", "2023-24"):
                row["form"] = 999999.0
                row[self.TARGETS[0]] = 1 - row[self.TARGETS[0]]
        changed_result = build_expanding_oof_predictions(
            changed,
            self.FEATURE_NAMES,
            self._base_configuration(),
            self.TARGETS[0],
        )
        original_2021 = [
            row for row in result["predictions"] if row["season"] == "2021-22"
        ]
        changed_2021 = [
            row
            for row in changed_result["predictions"]
            if row["season"] == "2021-22"
        ]
        self.assertEqual(original_2021, changed_2021)

    def test_calibrators_fit_only_oof_and_test_waits_for_both_selections(self):
        result = self._run()["calibration"]
        events = result["protocol_events"]
        freeze = events.index("both_calibrations_frozen_before_test_transform")
        selection_indexes = [
            index
            for index, event in enumerate(events)
            if event.startswith("validation_selected:")
        ]
        test_indexes = [
            index
            for index, event in enumerate(events)
            if event.startswith("test_evaluated_once:")
        ]
        self.assertEqual(len(selection_indexes), 2)
        self.assertEqual(len(test_indexes), 2)
        self.assertLess(max(selection_indexes), freeze)
        self.assertLess(freeze, min(test_indexes))
        for target in self.TARGETS:
            self.assertEqual(result["targets"][target]["oof"]["fit_rows"], 24)
            self.assertEqual(
                result["targets"][target]["oof"]["excluded_seasons"],
                ["2020-21"],
            )

    def test_test_values_and_labels_cannot_change_calibration_selection(self):
        rows = self._rows()
        original = self._run(rows)["calibration"]
        changed = deepcopy(rows)
        for row in changed:
            if row["split"] == "TEST":
                row["form"] = 1.0 - row["form"]
                for target in self.TARGETS:
                    row[target] = 1 - row[target]
        altered = self._run(changed)["calibration"]
        for target in self.TARGETS:
            self.assertEqual(
                original["targets"][target]["selected_calibration_identifier"],
                altered["targets"][target]["selected_calibration_identifier"],
            )
            self.assertEqual(
                original["targets"][target]["calibration_candidates"],
                altered["targets"][target]["calibration_candidates"],
            )

    def test_frozen_stage_4_model_is_enforced(self):
        rows = self._rows()
        with self.assertRaisesRegex(CalibrationError, "base configuration drifted"):
            run_calibration_research(
                rows,
                self.FEATURE_NAMES,
                selected_model_configurations={
                    target: self._base_configuration("logistic_l2_c1_v1")
                    for target in self.TARGETS
                },
                frozen_predictions=self._frozen_predictions(rows),
            )

    def test_every_frozen_base_configuration_field_is_enforced(self):
        rows = self._rows()
        original = self._base_configuration()

        def parameters(**changes):
            values = original.parameter_dict()
            values.update(changes)
            return tuple(sorted(values.items()))

        drifted = {
            "C": replace(original, parameters=parameters(C=0.2)),
            "complexity_rank": replace(original, complexity_rank=3),
            "extra_parameter": replace(
                original, parameters=parameters(unexpected=True)
            ),
            "family": replace(original, family="decision_tree"),
            "solver": replace(original, parameters=parameters(solver="liblinear")),
            "max_iter": replace(original, parameters=parameters(max_iter=1999)),
            "missing_parameter": replace(
                original,
                parameters=tuple(
                    (key, value)
                    for key, value in original.parameters
                    if key != "solver"
                ),
            ),
            "preprocessing": replace(original, preprocessing="train_median_imputation"),
            "random_state": replace(original, parameters=parameters(random_state=1730)),
        }
        for field, configuration in drifted.items():
            with self.subTest(field=field), self.assertRaisesRegex(
                CalibrationError, "base configuration drifted"
            ):
                run_calibration_research(
                    rows,
                    self.FEATURE_NAMES,
                    selected_model_configurations={
                        target: configuration for target in self.TARGETS
                    },
                    frozen_predictions=self._frozen_predictions(rows),
                )

        for name, configurations in (
            ("missing_target", {self.TARGETS[0]: original}),
            (
                "extra_target",
                {
                    **{target: original for target in self.TARGETS},
                    "unexpected_target": original,
                },
            ),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                CalibrationError, "target configuration set drifted"
            ):
                run_calibration_research(
                    rows,
                    self.FEATURE_NAMES,
                    selected_model_configurations=configurations,
                    frozen_predictions=self._frozen_predictions(rows),
                )

    def test_calibration_candidate_set_and_parameters_are_exact(self):
        rows = self._rows()
        defaults = list(default_calibration_configurations())

        def run(configurations):
            return run_calibration_research(
                rows,
                self.FEATURE_NAMES,
                selected_model_configurations={
                    target: self._base_configuration() for target in self.TARGETS
                },
                frozen_predictions=self._frozen_predictions(rows),
                calibration_configurations=configurations,
            )

        without_identity = [value for value in defaults if value.family != "identity"]
        extra = defaults + [
            CalibrationConfiguration("extra", "identity", 0, ())
        ]
        platt = next(value for value in defaults if value.family == "platt_logit")
        altered_parameters = platt.parameter_dict()
        altered_parameters["epsilon"] = 1e-5
        altered_epsilon = [
            replace(platt, parameters=tuple(sorted(altered_parameters.items())))
            if value.identifier == platt.identifier
            else value
            for value in defaults
        ]
        altered_complexity = [
            replace(platt, complexity_rank=9)
            if value.identifier == platt.identifier
            else value
            for value in defaults
        ]
        for name, configurations in (
            ("missing_identity", without_identity),
            ("extra_candidate", extra),
            ("platt_epsilon", altered_epsilon),
            ("calibration_complexity", altered_complexity),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                CalibrationError, "candidate configuration set drifted"
            ):
                run(configurations)

    def test_identity_platt_and_isotonic_semantics(self):
        configurations = {
            value.identifier: value for value in default_calibration_configurations()
        }
        probabilities = [0.1, 0.2, 0.35, 0.55, 0.7, 0.9]
        targets = [0, 0, 1, 0, 1, 1]
        identity = fit_calibrator(
            configurations["identity_calibration_v1"],
            probabilities,
            targets,
            target_name=self.TARGETS[0],
        )
        np.testing.assert_array_equal(
            identity.transform(probabilities),
            np.round(probabilities, CANONICAL_DECIMAL_PLACES),
        )
        platt = fit_calibrator(
            configurations["platt_logit_calibration_v1"],
            probabilities,
            targets,
            target_name=self.TARGETS[0],
        )
        transformed = platt.transform([0.0, 0.5, 1.0])
        self.assertTrue(np.isfinite(transformed).all())
        self.assertTrue(((transformed >= 0.0) & (transformed <= 1.0)).all())
        self.assertEqual(
            configurations["platt_logit_calibration_v1"].parameter_dict()[
                "epsilon"
            ],
            PLATT_LOGIT_EPSILON,
        )
        isotonic = fit_calibrator(
            configurations["isotonic_calibration_v1"],
            probabilities,
            targets,
            target_name=self.TARGETS[0],
        )
        isotonic_values = isotonic.transform([0.0, *probabilities, 1.0])
        self.assertTrue(np.all(np.diff(isotonic_values) >= 0.0))
        self.assertEqual(isotonic_values[0], isotonic.transform([0.1])[0])
        self.assertEqual(isotonic_values[-1], isotonic.transform([0.9])[0])

    def test_unavailable_and_convergence_failures_are_explicit(self):
        configurations = {
            value.identifier: value for value in default_calibration_configurations()
        }
        isotonic = fit_calibrator(
            configurations["isotonic_calibration_v1"],
            [0.4, 0.4, 0.4, 0.4],
            [0, 1, 0, 1],
            target_name=self.TARGETS[0],
        )
        self.assertEqual(isotonic.status, "UNAVAILABLE")
        self.assertEqual(isotonic.reason, "INSUFFICIENT_UNIQUE_PROBABILITIES")
        platt_single_class = fit_calibrator(
            configurations["platt_logit_calibration_v1"],
            [0.1, 0.2, 0.3],
            [1, 1, 1],
            target_name=self.TARGETS[0],
        )
        self.assertEqual(platt_single_class.status, "UNAVAILABLE")
        self.assertEqual(platt_single_class.reason, "SINGLE_CLASS")

        original_fit = LogisticRegression.fit

        def warning_fit(estimator, values, outcomes):
            fitted = original_fit(estimator, values, outcomes)
            warnings.warn("forced", ConvergenceWarning)
            return fitted

        with patch(
            "domain.win_either_half_calibration.LogisticRegression.fit",
            new=warning_fit,
        ), self.assertRaisesRegex(
            CalibrationError,
            "home_win_either_half_yes: platt_logit_calibration_v1",
        ):
            fit_calibrator(
                configurations["platt_logit_calibration_v1"],
                [0.1, 0.2, 0.4, 0.6, 0.8, 0.9],
                [0, 0, 1, 0, 1, 1],
                target_name=self.TARGETS[0],
            )

    def test_reliability_ties_probability_bounds_and_canonical_precision(self):
        metrics = probability_metrics([0, 1, 0, 1], [0.4, 0.4, 0.4, 0.4])
        self.assertEqual(metrics["calibration"]["actual_bin_count"], 1)
        self.assertEqual(len(metrics["calibration"]["bins"]), 1)
        configurations = default_calibration_configurations()
        identity = next(value for value in configurations if value.family == "identity")
        fitted = fit_calibrator(
            identity,
            [0.1234567890123, 0.8765432109877],
            [0, 1],
            target_name=self.TARGETS[0],
        )
        values = fitted.transform([0.12345678901231, 0.87654321098769])
        self.assertEqual(values.tolist(), [0.123456789012, 0.876543210988])
        with self.assertRaises(CalibrationError):
            fit_calibrator(
                identity,
                [0.2, float("nan")],
                [0, 1],
                target_name=self.TARGETS[0],
            )
        with self.assertRaises(CalibrationError):
            fit_calibrator(
                identity,
                [0.2, 1.01],
                [0, 1],
                target_name=self.TARGETS[0],
            )

    def test_selection_tie_breaks_are_deterministic(self):
        def candidate(name, log_loss, brier, complexity):
            return {
                "candidate_identifier": name,
                "complexity_rank": complexity,
                "metrics": {"brier_score": brier, "log_loss": log_loss},
                "status": "AVAILABLE",
            }

        values = (
            candidate("z", 0.5, 0.2, 0),
            candidate("b", 0.5, 0.1, 1),
            candidate("a", 0.5, 0.1, 1),
        )
        self.assertEqual(select_calibration_winner(values), "a")
        self.assertIn("VALIDATION", CALIBRATION_SELECTION_RULE)

    def test_subgroups_account_for_rows_and_expose_support_reasons(self):
        result = self._run()
        predictions = result["prediction_rows"]
        subgroups = result["subgroup_rows"]
        for target in self.TARGETS:
            role_groups = [
                row
                for row in subgroups
                if row["target_name"] == target
                and row["dimension"] == "evaluation_role"
            ]
            self.assertEqual(
                sum(row["row_count"] for row in role_groups),
                sum(row["target_name"] == target for row in predictions),
            )
            self.assertTrue(
                all(row["support_status"] == "LOW_SUPPORT" for row in role_groups)
            )
            self.assertTrue(
                all(row["support_reason"] == "INSUFFICIENT_ROWS" for row in role_groups)
            )
        band_groups = [
            row
            for row in subgroups
            if row["dimension"] == "split_and_model_probability_band"
            and row["evaluation_role"] == "FINAL_TEST"
        ]
        self.assertEqual(
            {row["group"].split("|", 1)[1] for row in band_groups},
            {band[0] for band in PROBABILITY_BANDS},
        )
        self.assertEqual(SUBGROUP_MINIMUM_ROWS, 100)

        single_class_rows = [
            {
                "calibrated_probability": 0.7,
                "fixture_identity": f"single-{index}",
                "league": "E0",
                "model_probability": 0.6,
                "prediction_role": "CALIBRATION_FIT_OOF",
                "season": "2020-21",
                "split": "TRAIN",
                "target_name": self.TARGETS[0],
                "target_value": 1,
            }
            for index in range(3)
        ]
        single = build_subgroup_evaluations(single_class_rows)
        train_group = next(
            row
            for row in single
            if row["target_name"] == self.TARGETS[0]
            and row["dimension"] == "evaluation_role"
            and row["group"] == "CALIBRATION_FIT_OOF"
        )
        self.assertIn("SINGLE_CLASS", train_group["identity"]["metric_reasons"])
        self.assertIsNone(train_group["identity"]["metrics"]["roc_auc"])
        self.assertIsNone(train_group["identity"]["metrics"]["average_precision"])

    def test_evaluation_roles_separate_fit_selection_and_final_test_evidence(self):
        result = self._run()
        subgroups = result["subgroup_rows"]
        self.assertTrue(subgroups)
        self.assertTrue(
            all(
                row["evaluation_scope"]
                == EVALUATION_ROLE_SCOPES[row["evaluation_role"]]
                for row in subgroups
            )
        )
        self.assertFalse(
            any(row["evaluation_scope"] == "ALL_PERIODS_DESCRIPTIVE" for row in subgroups)
        )
        for target in self.TARGETS:
            role_rows = {
                row["evaluation_role"]: row
                for row in subgroups
                if row["target_name"] == target
                and row["dimension"] == "evaluation_role"
            }
            self.assertEqual(set(role_rows), set(EVALUATION_ROLE_SCOPES))
            fit_sample = role_rows["CALIBRATION_FIT_OOF"]
            self.assertEqual(
                fit_sample["selected_calibration"]["evaluation_status"],
                "UNAVAILABLE",
            )
            self.assertEqual(
                fit_sample["selected_calibration"]["evaluation_reason"],
                "CALIBRATION_FIT_SAMPLE",
            )
            self.assertEqual(
                fit_sample["selected_calibration"]["metric_reasons"],
                ["CALIBRATION_FIT_SAMPLE"],
            )
            self.assertEqual(
                fit_sample["identity"]["evaluation_status"], "AVAILABLE"
            )
            self.assertEqual(
                role_rows["VALIDATION_SELECTION"]["evaluation_scope"],
                "SELECTION_SAMPLE",
            )
            self.assertEqual(
                role_rows["FINAL_TEST"]["evaluation_scope"],
                "INDEPENDENT_FINAL_TEST",
            )

    def test_final_test_leagues_and_fixed_bands_account_for_every_row(self):
        result = self._run()
        subgroups = build_subgroup_evaluations(
            result["prediction_rows"], frozen_leagues=("D1", "E0", "X0")
        )
        for target in self.TARGETS:
            league_rows = [
                row
                for row in subgroups
                if row["target_name"] == target
                and row["evaluation_role"] == "FINAL_TEST"
                and row["dimension"] == "split_and_league"
            ]
            band_rows = [
                row
                for row in subgroups
                if row["target_name"] == target
                and row["evaluation_role"] == "FINAL_TEST"
                and row["dimension"] == "split_and_model_probability_band"
            ]
            self.assertEqual(sum(row["row_count"] for row in league_rows), 6)
            missing_frozen_league = next(
                row for row in league_rows if row["group"] == "TEST|X0"
            )
            self.assertEqual(missing_frozen_league["row_count"], 0)
            self.assertEqual(
                missing_frozen_league["support_status"], "UNAVAILABLE"
            )
            self.assertEqual(sum(row["row_count"] for row in band_rows), 6)
            self.assertEqual(len(band_rows), len(PROBABILITY_BANDS))
            self.assertTrue(
                all(
                    row["support_status"] == "UNAVAILABLE"
                    for row in band_rows
                    if row["row_count"] == 0
                )
            )

    def test_real_committed_stage_4_ancestry_and_selected_models_are_exact(self):
        load = lambda path: json.loads(
            (self.REPOSITORY_ROOT / path).read_text(encoding="utf-8")
        )
        baseline = load(
            "artifacts/evidence-baselines/half-time-ready-for-research.json"
        )
        labels = load(
            "artifacts/research-manifests/win-either-half-labels-v1.json"
        )
        features = load(
            "artifacts/research-manifests/win-either-half-features-v1.json"
        )
        benchmarks = load(
            "artifacts/research-manifests/win-either-half-benchmarks-v1.json"
        )
        predictors, splits = verify_stage_4_manifest_contract(
            baseline=baseline,
            current_evidence={"market_safety": labels["market_safety"]},
            label_manifest=labels,
            feature_manifest=features,
            benchmark_manifest=benchmarks,
        )
        self.assertEqual(len(predictors), len(benchmarks["feature_columns"]))
        self.assertEqual(
            benchmarks["selected_models"],
            {target: "logistic_l2_c0.1_v1" for target in self.TARGETS},
        )
        self.assertEqual(sum(value["rows"] for value in splits.values()), 21791)
        self.assertEqual(benchmarks["files"]["predictions"]["rows"], 43582)
        configs = selected_model_configurations(benchmarks)
        self.assertTrue(
            all(config.identifier == "logistic_l2_c0.1_v1" for config in configs.values())
        )
        drifted = deepcopy(benchmarks)
        drifted["generated_at_utc"] = "2099-01-01T00:00:00Z"
        with self.assertRaisesRegex(
            CalibrationExportError, "benchmark manifest identity drifted"
        ):
            verify_stage_4_manifest_contract(
                baseline=baseline,
                current_evidence={"market_safety": labels["market_safety"]},
                label_manifest=labels,
                feature_manifest=features,
                benchmark_manifest=drifted,
            )

    def test_stage_4_local_input_verifiers_fail_closed_on_drift(self):
        rows = self._rows()
        predictions = self._frozen_predictions(rows)
        prediction_bytes = render_prediction_csv(predictions)
        summary = {
            "model_configurations": [self._base_configuration().to_dict()],
            "numerical_reproducibility": {"canonical_decimal_places": 12},
            "split_counts": {"train": 32, "validation": 6, "test": 6},
            "targets": {
                target: {"selected_model_identifier": "logistic_l2_c0.1_v1"}
                for target in self.TARGETS
            },
        }
        summary_bytes = (json.dumps(summary, sort_keys=True) + "\n").encode()
        manifest = {
            "files": {
                "benchmark_summary": {
                    "byte_size": len(summary_bytes),
                    "sha256": hashlib.sha256(summary_bytes).hexdigest(),
                },
                "predictions": {
                    "byte_size": len(prediction_bytes),
                    "rows": len(predictions),
                    "sha256": hashlib.sha256(prediction_bytes).hexdigest(),
                },
            },
            "model_configurations": summary["model_configurations"],
            "selected_models": {
                target: "logistic_l2_c0.1_v1" for target in self.TARGETS
            },
            "splits": {
                "train": {"rows": 32},
                "validation": {"rows": 6},
                "test": {"rows": 6},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary_path = root / "benchmark.json"
            prediction_path = root / "predictions.csv"
            summary_path.write_bytes(summary_bytes)
            prediction_path.write_bytes(prediction_bytes)
            loaded, identity = load_verified_benchmark_summary(summary_path, manifest)
            self.assertEqual(loaded, summary)
            self.assertEqual(identity["byte_size"], len(summary_bytes))
            loaded_predictions, _ = load_verified_stage_4_predictions(
                prediction_path, manifest, rows
            )
            self.assertEqual(len(loaded_predictions), len(predictions))
            prediction_path.write_bytes(prediction_bytes + b"x")
            with self.assertRaisesRegex(CalibrationExportError, "byte size"):
                load_verified_stage_4_predictions(prediction_path, manifest, rows)

    def test_manifest_lifecycle_runtime_drift_and_atomic_outputs(self):
        result = self._run()
        calibration_bytes = render_calibration_summary(result["calibration"])
        prediction_bytes = render_calibrated_predictions(result["prediction_rows"])
        subgroup_bytes = render_subgroups(result["subgroup_rows"])
        benchmark_manifest = {
            "dataset_name": "win-either-half-baseline-benchmarks-v1",
            "generator": {"generator_git_head_sha": "a" * 40},
            "market_safety": {
                "away_win_either_half": "DISABLED",
                "home_win_either_half": "DISABLED",
            },
            "selected_models": {
                target: "logistic_l2_c0.1_v1" for target in self.TARGETS
            },
            "splits": {},
            "stage_2_evidence": {},
        }
        manifest = build_calibration_manifest(
            calibration=result["calibration"],
            calibration_bytes=calibration_bytes,
            calibration_name="calibration.json",
            prediction_bytes=prediction_bytes,
            prediction_name="predictions.csv",
            prediction_rows=len(result["prediction_rows"]),
            subgroup_bytes=subgroup_bytes,
            subgroup_name="subgroups.csv",
            subgroup_rows=len(result["subgroup_rows"]),
            baseline={},
            label_manifest={"generator": {}},
            feature_manifest={"generator": {}},
            benchmark_manifest=benchmark_manifest,
            feature_identity={"rows": 44, "byte_size": 1, "sha256": "f" * 64},
            benchmark_identity={"byte_size": 1, "sha256": "b" * 64},
            stage_4_prediction_identity={
                "rows": 88,
                "byte_size": 1,
                "sha256": "p" * 64,
            },
            generator_code_state={
                "evidence_git_head_sha": "c" * 40,
                "tracked_worktree_clean": True,
            },
            numerical_runtime={"python_version": "test", "thread_limit": 1},
            generated_at_utc="2026-08-01T00:00:00Z",
        )
        later = deepcopy(manifest)
        later["generated_at_utc"] = "2030-01-01T00:00:00Z"
        self.assertEqual(compare_calibration_manifests(manifest, later), [])
        runtime_drift = deepcopy(manifest)
        runtime_drift["numerical_reproducibility"]["runtime"][
            "python_version"
        ] = "different"
        self.assertIn(
            "numerical runtime contract differs",
            compare_calibration_manifests(manifest, runtime_drift),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = (
                root / "calibration.json",
                root / "predictions.csv",
                root / "subgroups.csv",
                root / "manifest.json",
            )
            write_calibration_outputs(
                calibration_path=paths[0],
                prediction_path=paths[1],
                subgroup_path=paths[2],
                manifest_path=paths[3],
                calibration_bytes=calibration_bytes,
                prediction_bytes=prediction_bytes,
                subgroup_bytes=subgroup_bytes,
                manifest=manifest,
            )
            self.assertTrue(all(path.exists() for path in paths))
            with self.assertRaisesRegex(CalibrationExportError, "--force"):
                write_calibration_outputs(
                    calibration_path=paths[0],
                    prediction_path=paths[1],
                    subgroup_path=paths[2],
                    manifest_path=paths[3],
                    calibration_bytes=calibration_bytes,
                    prediction_bytes=prediction_bytes,
                    subgroup_bytes=subgroup_bytes,
                    manifest=manifest,
                )

    def test_clean_worktree_gate_and_entrypoints(self):
        with patch(
            "scripts.export_win_either_half_calibration_research.load_baseline",
            return_value={},
        ), patch(
            "scripts.export_win_either_half_calibration_research.verify_stage_2_evidence",
            return_value={"market_safety": {}},
        ), patch(
            "scripts.export_win_either_half_calibration_research.load_research_manifest",
            return_value={},
        ), patch(
            "scripts.export_win_either_half_calibration_research.load_feature_manifest",
            return_value={},
        ), patch(
            "scripts.export_win_either_half_calibration_research.load_benchmark_manifest",
            return_value={},
        ), patch(
            "scripts.export_win_either_half_calibration_research.verify_stage_4_manifest_contract",
            return_value=(self.FEATURE_NAMES, {
                "train": {"rows": 1},
                "validation": {"rows": 1},
                "test": {"rows": 1},
            }),
        ), patch(
            "scripts.export_win_either_half_calibration_research.load_verified_feature_rows",
            return_value=(({},), {}),
        ), patch(
            "scripts.export_win_either_half_calibration_research.load_verified_benchmark_summary",
            return_value=({}, {}),
        ), patch(
            "scripts.export_win_either_half_calibration_research.load_verified_stage_4_predictions",
            return_value=(({},), {}),
        ), patch(
            "scripts.export_win_either_half_calibration_research.get_code_state",
            return_value={"tracked_worktree_clean": False},
        ):
            self.assertEqual(main(["--manifest-output", "unused.json"]), 1)

        for command in (
            [sys.executable, "scripts/export_win_either_half_calibration_research.py", "--help"],
            [sys.executable, "-m", "scripts.export_win_either_half_calibration_research", "--help"],
        ):
            with self.subTest(command=command):
                completed = subprocess.run(
                    command,
                    cwd=self.REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=120,
                    shell=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("--benchmark-manifest", completed.stdout)
                self.assertIn("--check", completed.stdout)

    def test_outputs_remain_ignored_and_markets_disabled(self):
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=self.REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            shell=False,
            check=True,
        ).stdout.splitlines()
        self.assertFalse(
            any(path.startswith(".cache/athena-research/") for path in tracked)
        )
        self.assertNotIn(
            "artifacts/research-manifests/win-either-half-calibration-v1.json",
            tracked,
        )
        for market in (
            MarketId.HOME_WIN_EITHER_HALF,
            MarketId.AWAY_WIN_EITHER_HALF,
        ):
            with self.subTest(market=market):
                self.assertEqual(
                    MODEL_STATUS_REGISTRY[market].status, ModelStatus.DISABLED
                )

        with patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("network access is forbidden"),
        ):
            self._run()


if __name__ == "__main__":
    unittest.main()
