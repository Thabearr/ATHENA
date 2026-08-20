import csv
import hashlib
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import warnings
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from database.database import Database
from domain.markets import MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_benchmarks import (
    BenchmarkError,
    CANONICAL_DECIMAL_PLACES,
    CANONICAL_QUANTUM,
    ModelConfiguration,
    NUMERICAL_THREAD_LIMIT,
    SELECTION_RULE,
    TARGETS,
    canonicalize_probabilities,
    default_model_configurations,
    fit_train_preprocessor,
    pre_match_feature_names,
    probability_metrics,
    run_baseline_benchmarks,
    select_validation_winner,
    validate_predictor_columns,
)
from domain.win_either_half_features import build_pre_match_feature_dataset
from domain.win_either_half_research import build_win_either_half_labels
from scripts.audit_half_time_coverage import load_observations_from_database
from scripts.export_win_either_half_baseline_benchmarks import (
    BenchmarkExportError,
    build_benchmark_manifest,
    compare_benchmark_manifests,
    dependency_versions,
    load_verified_feature_rows,
    main,
    numerical_runtime_fingerprint,
    render_benchmark_summary,
    render_prediction_csv,
    verify_frozen_manifest_contracts,
    write_benchmark_outputs,
)
from scripts.export_win_either_half_feature_dataset import (
    build_feature_manifest,
    canonical_json_sha256,
    load_verified_label_matches,
    render_feature_csv,
    validate_label_manifest_contract,
)
from scripts.export_win_either_half_research_dataset import (
    build_research_manifest,
    render_dataset_csv,
    verify_stage_2_evidence,
)
from scripts.freeze_evidence_baseline import build_evidence_baseline, get_code_state


class WinEitherHalfBenchmarkTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    CODE_STATE = {
        "evidence_git_head_sha": "a" * 40,
        "tracked_worktree_clean": True,
    }
    SMALL_SCHEMA = (
        {"name": "fixture_identity", "role": "IDENTIFIER"},
        {"name": "kickoff_utc", "role": "SPLIT_METADATA"},
        {"name": "season", "role": "SPLIT_METADATA"},
        {"name": "split", "role": "SPLIT_METADATA"},
        {"name": "numeric_form", "role": "PRE_MATCH_FEATURE"},
        {"name": "days_since", "role": "PRE_MATCH_FEATURE"},
        {"name": "days_since_missing", "role": "PRE_MATCH_FEATURE"},
        {"name": "home_win_either_half_yes", "role": "TARGET_ONLY"},
        {"name": "away_win_either_half_yes", "role": "TARGET_ONLY"},
        {"name": "both_teams_won_a_half", "role": "TARGET_ONLY"},
    )
    FEATURE_NAMES = ("numeric_form", "days_since", "days_since_missing")

    def _rows(self):
        rows = []
        split_specs = (
            ("TRAIN", "2023-24", 30),
            ("VALIDATION", "2024-25", 15),
            ("TEST", "2025-26", 15),
        )
        index = 0
        for split, season, count in split_specs:
            for local in range(count):
                home = int(local % 4 in (0, 1))
                away = int(local % 5 in (0, 2))
                rows.append(
                    {
                        "away_win_either_half_yes": away,
                        "both_teams_won_a_half": int(home and away),
                        "days_since": None if local % 5 == 0 else float(local + 1),
                        "days_since_missing": int(local % 5 == 0),
                        "fixture_identity": f"fixture-{index:03d}",
                        "home_win_either_half_yes": home,
                        "kickoff_utc": (
                            datetime(2023, 1, 1, tzinfo=timezone.utc)
                            + timedelta(days=index)
                        ).isoformat(),
                        "numeric_form": float((local * 3) % 11) / 10.0,
                        "season": season,
                        "split": split,
                    }
                )
                index += 1
        return rows

    @staticmethod
    def _candidate(result, target, identifier):
        return next(
            value
            for value in result["benchmark"]["targets"][target]["candidates"]
            if value["model_identifier"] == identifier
        )

    def test_only_frozen_pre_match_columns_are_predictors(self):
        self.assertEqual(
            pre_match_feature_names(self.SMALL_SCHEMA), self.FEATURE_NAMES
        )
        self.assertEqual(
            validate_predictor_columns(self.SMALL_SCHEMA, self.FEATURE_NAMES),
            self.FEATURE_NAMES,
        )
        for forbidden in (
            "fixture_identity",
            "kickoff_utc",
            "season",
            "split",
            "home_win_either_half_yes",
            "away_win_either_half_yes",
            "both_teams_won_a_half",
        ):
            with self.subTest(forbidden=forbidden), self.assertRaisesRegex(
                BenchmarkError, "PRE_MATCH_FEATURE"
            ):
                validate_predictor_columns(
                    self.SMALL_SCHEMA, (*self.FEATURE_NAMES, forbidden)
                )

    def test_preprocessing_is_fitted_on_train_only(self):
        rows = self._rows()
        train = [row for row in rows if row["split"] == "TRAIN"]
        original = fit_train_preprocessor(train, self.FEATURE_NAMES)
        changed_validation = deepcopy(rows)
        for row in changed_validation:
            if row["split"] == "VALIDATION":
                row["numeric_form"] = 999999.0
                row["days_since"] = None
        changed_train_view = [
            row for row in changed_validation if row["split"] == "TRAIN"
        ]
        self.assertEqual(
            original,
            fit_train_preprocessor(changed_train_view, self.FEATURE_NAMES),
        )
        with self.assertRaisesRegex(BenchmarkError, "only on TRAIN"):
            fit_train_preprocessor(rows, self.FEATURE_NAMES)

    def test_test_values_and_labels_cannot_change_model_selection(self):
        rows = self._rows()
        original = run_baseline_benchmarks(rows, self.FEATURE_NAMES)
        changed = deepcopy(rows)
        for row in changed:
            if row["split"] == "TEST":
                row["numeric_form"] = 1000000.0 - float(row["numeric_form"])
                row["days_since"] = None
                row["home_win_either_half_yes"] = (
                    1 - row["home_win_either_half_yes"]
                )
                row["away_win_either_half_yes"] = (
                    1 - row["away_win_either_half_yes"]
                )
        altered = run_baseline_benchmarks(changed, self.FEATURE_NAMES)
        for target in TARGETS:
            self.assertEqual(
                original["benchmark"]["targets"][target][
                    "selected_model_identifier"
                ],
                altered["benchmark"]["targets"][target][
                    "selected_model_identifier"
                ],
            )
            original_candidates = original["benchmark"]["targets"][target][
                "candidates"
            ]
            altered_candidates = altered["benchmark"]["targets"][target][
                "candidates"
            ]
            self.assertEqual(original_candidates, altered_candidates)

    def test_test_is_evaluated_only_after_both_validation_selections(self):
        result = run_baseline_benchmarks(self._rows(), self.FEATURE_NAMES)
        events = result["benchmark"]["protocol_events"]
        test_transform = events.index(
            "test_transformed_after_all_validation_selection"
        )
        selection_positions = [
            index
            for index, event in enumerate(events)
            if event.startswith("validation_selected:")
        ]
        evaluation_positions = [
            index
            for index, event in enumerate(events)
            if event.startswith("test_evaluated_once:")
        ]
        self.assertEqual(len(selection_positions), 2)
        self.assertEqual(len(evaluation_positions), 2)
        self.assertLess(max(selection_positions), test_transform)
        self.assertLess(test_transform, min(evaluation_positions))
        for target in TARGETS:
            for candidate in result["benchmark"]["targets"][target][
                "candidates"
            ]:
                self.assertNotIn("test", candidate["metrics"])

    def test_constant_baseline_uses_train_prevalence_only(self):
        rows = self._rows()
        result = run_baseline_benchmarks(rows, self.FEATURE_NAMES)
        for target in TARGETS:
            train = [row[target] for row in rows if row["split"] == "TRAIN"]
            prevalence = sum(train) / len(train)
            constant = self._candidate(
                result, target, "constant_train_prevalence_v1"
            )
            for split in ("train", "validation"):
                diagnostics = constant["metrics"][split][
                    "probability_diagnostics"
                ]
                self.assertAlmostEqual(diagnostics["minimum"], prevalence)
                self.assertAlmostEqual(diagnostics["maximum"], prevalence)
                self.assertAlmostEqual(diagnostics["mean"], prevalence)

    def test_determinism_under_reordered_input_and_fixed_seed(self):
        rows = self._rows()
        first = run_baseline_benchmarks(rows, self.FEATURE_NAMES)
        second = run_baseline_benchmarks(
            reversed(rows), self.FEATURE_NAMES
        )
        third = run_baseline_benchmarks(rows, self.FEATURE_NAMES)
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(
            render_benchmark_summary(first["benchmark"]),
            render_benchmark_summary(second["benchmark"]),
        )
        self.assertEqual(
            render_prediction_csv(first["prediction_rows"]),
            render_prediction_csv(second["prediction_rows"]),
        )

    def test_missing_values_are_transparent_and_train_derived(self):
        rows = self._rows()
        result = run_baseline_benchmarks(rows, self.FEATURE_NAMES)
        preprocessing = result["benchmark"]["preprocessing"]
        self.assertGreater(
            preprocessing["missing_values"]["train"]["missing_before"], 0
        )
        for split in ("train", "validation", "test"):
            self.assertEqual(
                preprocessing["missing_values"][split]["missing_after"], 0
            )
        train_days = sorted(
            row["days_since"]
            for row in rows
            if row["split"] == "TRAIN" and row["days_since"] is not None
        )
        expected_median = (train_days[11] + train_days[12]) / 2
        index = self.FEATURE_NAMES.index("days_since")
        self.assertEqual(
            preprocessing["state"]["medians"][index], expected_median
        )
        self.assertIn("days_since_missing", preprocessing["state"]["feature_names"])

    def test_probabilities_and_required_metrics_are_valid(self):
        result = run_baseline_benchmarks(self._rows(), self.FEATURE_NAMES)
        for target in TARGETS:
            evaluation = result["benchmark"]["targets"][target][
                "selected_evaluation"
            ]
            for split in ("train", "validation", "test"):
                metrics = evaluation[split]
                self.assertIn("log_loss", metrics)
                self.assertIn("brier_score", metrics)
                self.assertIn("roc_auc", metrics)
                self.assertIn("average_precision", metrics)
                diagnostics = metrics["probability_diagnostics"]
                self.assertEqual(diagnostics["count_nan_or_infinite"], 0)
                self.assertEqual(diagnostics["count_outside_unit_interval"], 0)
                self.assertGreaterEqual(diagnostics["minimum"], 0.0)
                self.assertLessEqual(diagnostics["maximum"], 1.0)
                self.assertEqual(
                    tuple(metrics["threshold_diagnostics"]),
                    ("0.50", "0.60", "0.70"),
                )
                self.assertIn("expected_calibration_error", metrics["calibration"])
        with self.assertRaises(BenchmarkError):
            probability_metrics([0, 1], [0.2, float("nan")])
        with self.assertRaises(BenchmarkError):
            probability_metrics([0, 1], [0.2, 1.1])

    def test_calibration_bins_preserve_probability_ties(self):
        constant = probability_metrics([0, 1, 1, 0], [0.25] * 4)
        calibration = constant["calibration"]
        self.assertEqual(calibration["actual_bin_count"], 1)
        self.assertEqual(len(calibration["bins"]), 1)
        self.assertEqual(
            calibration["expected_calibration_error"],
            abs(0.25 - 0.5),
        )

        targets = np.asarray([0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1])
        probabilities = np.asarray([0.1] * 4 + [0.3] * 3 + [0.9] * 5)
        repeated = probability_metrics(targets, probabilities)["calibration"]
        self.assertEqual(repeated["actual_bin_count"], 3)
        for probability in np.unique(probabilities):
            containing = [
                value
                for value in repeated["bins"]
                if value["probability_minimum"]
                <= probability
                <= value["probability_maximum"]
            ]
            self.assertEqual(len(containing), 1)

    def test_calibration_bins_are_balanced_and_reorder_invariant(self):
        targets = np.asarray([index % 2 for index in range(101)])
        probabilities = np.linspace(0.01, 0.99, num=101)
        original = probability_metrics(targets, probabilities)["calibration"]
        counts = [value["count"] for value in original["bins"]]
        self.assertLessEqual(max(counts) - min(counts), 1)
        order = np.asarray(list(reversed(range(len(targets)))))
        reordered = probability_metrics(
            targets[order], probabilities[order]
        )["calibration"]
        self.assertEqual(original, reordered)

    def test_logistic_candidate_convergence_warning_fails_closed(self):
        configuration = ModelConfiguration(
            identifier="forced_non_converged_logistic",
            family="logistic_regression",
            complexity_rank=1,
            parameters=(
                ("C", 1.0),
                ("max_iter", 2000),
                ("random_state", 1729),
                ("solver", "lbfgs"),
            ),
            preprocessing="train_median_imputation_and_standard_scaling",
        )
        original_fit = LogisticRegression.fit

        def warning_fit(estimator, values, targets):
            fitted = original_fit(estimator, values, targets)
            warnings.warn("forced", ConvergenceWarning)
            return fitted

        with patch(
            "domain.win_either_half_benchmarks.LogisticRegression.fit",
            new=warning_fit,
        ), patch(
            "domain.win_either_half_benchmarks.select_validation_winner"
        ) as selection:
            with self.assertRaisesRegex(
                BenchmarkError,
                "home_win_either_half_yes: forced_non_converged_logistic",
            ):
                run_baseline_benchmarks(
                    self._rows(),
                    self.FEATURE_NAMES,
                    model_configurations=(configuration,),
                )
            selection.assert_not_called()

    def test_calibration_diagnostic_non_convergence_is_explicit(self):
        original_fit = LogisticRegression.fit

        def warning_fit(estimator, values, targets):
            fitted = original_fit(estimator, values, targets)
            warnings.warn("forced", ConvergenceWarning)
            return fitted

        targets = [0, 0, 1, 1, 0, 1]
        probabilities = [0.1, 0.2, 0.65, 0.8, 0.35, 0.7]
        with patch(
            "domain.win_either_half_benchmarks.LogisticRegression.fit",
            new=warning_fit,
        ):
            diagnostic = probability_metrics(targets, probabilities)[
                "calibration"
            ]
        self.assertEqual(diagnostic["status"], "UNAVAILABLE")
        self.assertEqual(diagnostic["reason"], "NON_CONVERGENCE")
        self.assertIsNone(diagnostic["intercept"])
        self.assertIsNone(diagnostic["slope"])
        available = probability_metrics(targets, probabilities)["calibration"]
        self.assertEqual(available["status"], "AVAILABLE")

    def test_canonical_probability_precision_and_selection_tolerance(self):
        base = np.asarray([0.2345678901234, 0.7654321098764])
        sub_precision = base + np.asarray([1e-14, -1e-14])
        above_precision = base + np.asarray([2e-12, -2e-12])
        np.testing.assert_array_equal(
            canonicalize_probabilities(base),
            canonicalize_probabilities(sub_precision),
        )
        self.assertFalse(
            np.array_equal(
                canonicalize_probabilities(base),
                canonicalize_probabilities(above_precision),
            )
        )
        self.assertEqual(CANONICAL_DECIMAL_PLACES, 12)
        self.assertEqual(CANONICAL_QUANTUM, 1e-12)

        def candidate(name, log_loss_value):
            return {
                "complexity_rank": 1,
                "metrics": {
                    "validation": {
                        "brier_score": 0.2,
                        "log_loss": log_loss_value,
                    }
                },
                "model_identifier": name,
            }

        self.assertEqual(
            select_validation_winner(
                (candidate("a", 0.3 + 1e-14), candidate("b", 0.3))
            ),
            "a",
        )
        self.assertEqual(
            select_validation_winner(
                (candidate("a", 0.3 + 2e-12), candidate("b", 0.3))
            ),
            "b",
        )

    def test_split_counts_targets_and_independence_are_preserved(self):
        result = run_baseline_benchmarks(
            self._rows(),
            self.FEATURE_NAMES,
            expected_split_counts={
                "TRAIN": 30,
                "VALIDATION": 15,
                "TEST": 15,
            },
        )
        self.assertEqual(
            result["benchmark"]["split_counts"],
            {"train": 30, "validation": 15, "test": 15},
        )
        self.assertEqual(tuple(result["benchmark"]["targets"]), TARGETS)
        self.assertEqual(len(result["prediction_rows"]), 120)
        self.assertNotIn(
            "both_teams_won_a_half",
            result["benchmark"]["preprocessing"]["state"]["feature_names"],
        )
        self.assertEqual(
            {row["target_name"] for row in result["prediction_rows"]},
            set(TARGETS),
        )
        with self.assertRaisesRegex(BenchmarkError, "TEST row count"):
            run_baseline_benchmarks(
                self._rows(),
                self.FEATURE_NAMES,
                expected_split_counts={
                    "TRAIN": 30,
                    "VALIDATION": 15,
                    "TEST": 4048,
                },
            )

    def test_committed_frozen_feature_identity_and_split_counts(self):
        manifest = json.loads(
            (
                self.REPOSITORY_ROOT
                / "artifacts/research-manifests/win-either-half-features-v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["files"]["features"]["rows"], 21791)
        self.assertEqual(manifest["files"]["features"]["byte_size"], 8032209)
        self.assertEqual(
            manifest["files"]["features"]["sha256"],
            "68547ae9670703c59d68367d8fa1ef067e7410d8beb842ad0aec2151f0777e7b",
        )
        self.assertEqual(manifest["splits"]["train"]["rows"], 14267)
        self.assertEqual(manifest["splits"]["validation"]["rows"], 3476)
        self.assertEqual(manifest["splits"]["test"]["rows"], 4048)

    def test_selection_rule_uses_log_loss_brier_complexity_then_name(self):
        def candidate(name, logloss, brier, complexity, threshold_precision=0.0):
            return {
                "complexity_rank": complexity,
                "metrics": {
                    "validation": {
                        "brier_score": brier,
                        "log_loss": logloss,
                        "threshold_diagnostics": {
                            "0.50": {"precision": threshold_precision}
                        },
                    }
                },
                "model_identifier": name,
            }

        values = (
            candidate("z", 0.4, 0.2, 1, 1.0),
            candidate("b", 0.4, 0.1, 2, 0.0),
            candidate("a", 0.4, 0.1, 2, 0.5),
        )
        self.assertEqual(select_validation_winner(values), "a")
        changed_thresholds = deepcopy(values)
        changed_thresholds[0]["metrics"]["validation"][
            "threshold_diagnostics"
        ]["0.50"]["precision"] = 0.0
        self.assertEqual(select_validation_winner(changed_thresholds), "a")
        self.assertIn("VALIDATION log loss", SELECTION_RULE)

    def test_metrics_use_the_serialized_canonical_probabilities(self):
        result = run_baseline_benchmarks(self._rows(), self.FEATURE_NAMES)
        content = render_prediction_csv(result["prediction_rows"])
        self.assertNotIn(b"\r\n", content)
        serialized_rows = list(
            csv.DictReader(io.StringIO(content.decode("utf-8")))
        )
        for target in TARGETS:
            for split in ("TRAIN", "VALIDATION", "TEST"):
                rows = [
                    row
                    for row in serialized_rows
                    if row["target_name"] == target and row["split"] == split
                ]
                metrics = probability_metrics(
                    [int(row["target_value"]) for row in rows],
                    [float(row["predicted_probability"]) for row in rows],
                )
                self.assertEqual(
                    metrics,
                    result["benchmark"]["targets"][target][
                        "selected_evaluation"
                    ][split.lower()],
                )

    def test_numerical_runtime_fingerprint_is_bounded_and_machine_readable(self):
        loaded = [
            {
                "architecture": "test-arch",
                "filepath": "C:/Users/private/library.dll",
                "internal_api": "openblas",
                "num_threads": 1,
                "prefix": "libopenblas",
                "threading_layer": "pthreads",
                "user_api": "blas",
                "version": "1.0",
            }
        ]
        with patch(
            "scripts.export_win_either_half_baseline_benchmarks.threadpool_info",
            return_value=loaded,
        ):
            runtime = numerical_runtime_fingerprint()
        self.assertEqual(runtime["thread_limit"], NUMERICAL_THREAD_LIMIT)
        for key in (
            "python_version",
            "python_implementation",
            "platform_system",
            "machine_architecture",
            "numpy_version",
            "scipy_version",
            "scikit_learn_version",
            "threadpoolctl_version",
            "libraries",
        ):
            self.assertIn(key, runtime)
        self.assertNotIn("filepath", runtime["libraries"][0])
        self.assertNotIn("C:/Users", json.dumps(runtime))

    @staticmethod
    def _create_cache(cache: Path):
        cache.mkdir(parents=True)
        (cache / "2324_E0.csv").write_bytes(b"Div,FTHG,FTAG,HTHG,HTAG\n")

    def _create_database(self, database: Path):
        Database(str(database)).initialize()
        teams = ((1, "Alpha"), (2, "Beta"), (3, "Gamma"), (4, "Delta"))
        connection = sqlite3.connect(database)
        try:
            for team_id, name in teams:
                connection.execute(
                    "INSERT INTO teams (team_id, name, league) VALUES (?, ?, ?)",
                    (team_id, name, "E0"),
                )
            specifications = (
                ("2023-24", datetime(2023, 8, 1, tzinfo=timezone.utc), 12),
                ("2024-25", datetime(2024, 8, 1, tzinfo=timezone.utc), 6),
                ("2025-26", datetime(2025, 8, 1, tzinfo=timezone.utc), 6),
            )
            fixture_id = 1
            score_patterns = (
                (2, 0, 1, 0),
                (0, 2, 0, 1),
                (2, 2, 0, 1),
                (0, 0, 0, 0),
            )
            for season, start, count in specifications:
                for local in range(count):
                    home_id = (local % 4) + 1
                    away_id = ((local + 1) % 4) + 1
                    home_name = dict(teams)[home_id]
                    away_name = dict(teams)[away_id]
                    ft_home, ft_away, ht_home, ht_away = score_patterns[
                        local % len(score_patterns)
                    ]
                    kickoff = (start + timedelta(days=local)).isoformat()
                    connection.execute(
                        """
                        INSERT INTO historical_matches (
                            fixture_id, home_id, away_id, home_goals, away_goals,
                            match_date, data_source, season_label, league_code
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fixture_id,
                            home_id,
                            away_id,
                            ft_home,
                            ft_away,
                            kickoff,
                            "football_data_uk_csv",
                            season,
                            "E0",
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO half_time_observations (
                            fixture_identity, home_team, away_team, kickoff_time,
                            full_time_home_goals, full_time_away_goals,
                            half_time_home_goals, half_time_away_goals, source,
                            observed_at, source_fixture_id,
                            half_time_score_provenance, validation_status,
                            rejection_reasons, league, season
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(fixture_id),
                            home_name,
                            away_name,
                            kickoff,
                            ft_home,
                            ft_away,
                            ht_home,
                            ht_away,
                            "football_data_uk_csv",
                            "2026-07-01T00:00:00+00:00",
                            f"source-{fixture_id}",
                            "OBSERVED",
                            "VALID",
                            "[]",
                            "E0",
                            season,
                        ),
                    )
                    fixture_id += 1
            connection.commit()
        finally:
            connection.close()

    def _frozen_stack(self, root: Path, code_state=None):
        root.mkdir(parents=True, exist_ok=True)
        database = root / "athena.db"
        cache = root / "cache"
        baseline_path = root / "baseline.json"
        label_manifest_path = root / "labels-manifest.json"
        labels_path = root / "labels.csv"
        feature_manifest_path = root / "features-manifest.json"
        feature_path = root / "features.csv"
        self._create_database(database)
        self._create_cache(cache)
        state = deepcopy(code_state or self.CODE_STATE)
        baseline = build_evidence_baseline(
            database_path=database,
            cache_directory=cache,
            baseline_name="test-stage-2",
            code_state=state,
            generated_at_utc="2026-08-01T00:00:00Z",
        )
        current = verify_stage_2_evidence(
            baseline,
            database_path=database,
            cache_directory=cache,
        )
        label_dataset = build_win_either_half_labels(
            load_observations_from_database(str(database))
        )
        labels_bytes, exclusions_bytes = render_dataset_csv(label_dataset)
        label_manifest = build_research_manifest(
            label_dataset,
            labels_bytes=labels_bytes,
            exclusions_bytes=exclusions_bytes,
            labels_relative_name="labels.csv",
            exclusions_relative_name="exclusions.csv",
            stage_2_baseline=baseline,
            current_evidence=current,
            generator_code_state=state,
            generated_at_utc="2026-08-01T00:00:00Z",
        )
        labels_path.write_bytes(labels_bytes)
        label_manifest_path.write_text(
            json.dumps(label_manifest, sort_keys=True), encoding="utf-8"
        )
        split_config = validate_label_manifest_contract(
            label_manifest,
            baseline=baseline,
            current_evidence=current,
        )
        label_matches, label_csv_identity = load_verified_label_matches(
            labels_path, label_manifest, split_config
        )
        feature_dataset = build_pre_match_feature_dataset(label_matches)
        feature_bytes = render_feature_csv(feature_dataset)
        feature_manifest = build_feature_manifest(
            feature_dataset,
            feature_bytes=feature_bytes,
            feature_relative_name="features.csv",
            baseline=baseline,
            label_manifest=label_manifest,
            label_manifest_logical_sha256=canonical_json_sha256(label_manifest),
            label_csv_identity=label_csv_identity,
            generator_code_state=state,
            generated_at_utc="2026-08-01T00:00:00Z",
        )
        baseline_path.write_text(
            json.dumps(baseline, sort_keys=True), encoding="utf-8"
        )
        feature_path.write_bytes(feature_bytes)
        feature_manifest_path.write_text(
            json.dumps(feature_manifest, sort_keys=True), encoding="utf-8"
        )
        return {
            "baseline": baseline,
            "baseline_path": baseline_path,
            "cache": cache,
            "current": current,
            "database": database,
            "feature_bytes": feature_bytes,
            "feature_manifest": feature_manifest,
            "feature_manifest_path": feature_manifest_path,
            "feature_path": feature_path,
            "label_manifest": label_manifest,
            "label_manifest_path": label_manifest_path,
        }

    def test_feature_csv_hash_size_and_row_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_stack(Path(directory))
            _, predictors = verify_frozen_manifest_contracts(
                baseline=fixture["baseline"],
                current_evidence=fixture["current"],
                label_manifest=fixture["label_manifest"],
                feature_manifest=fixture["feature_manifest"],
            )
            original = fixture["feature_path"].read_bytes()
            changed = bytearray(original)
            changed[-2] = ord("9") if changed[-2] != ord("9") else ord("8")
            fixture["feature_path"].write_bytes(bytes(changed))
            with self.assertRaisesRegex(BenchmarkExportError, "SHA-256"):
                load_verified_feature_rows(
                    fixture["feature_path"], fixture["feature_manifest"], predictors
                )
            fixture["feature_path"].write_bytes(original + b"x")
            with self.assertRaisesRegex(BenchmarkExportError, "byte size"):
                load_verified_feature_rows(
                    fixture["feature_path"], fixture["feature_manifest"], predictors
                )
            fixture["feature_path"].write_bytes(original)
            with self.assertRaisesRegex(BenchmarkExportError, "total-row"):
                load_verified_feature_rows(
                    fixture["feature_path"],
                    fixture["feature_manifest"],
                    predictors,
                    expected_total_rows=21791,
                )

    def test_stage_2_stage_3_and_feature_manifest_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_stack(Path(directory))
            changed_feature = deepcopy(fixture["feature_manifest"])
            changed_feature["stage_2_evidence"]["schema_sha256"] = "drift"
            with self.assertRaisesRegex(BenchmarkExportError, "Stage 2"):
                verify_frozen_manifest_contracts(
                    baseline=fixture["baseline"],
                    current_evidence=fixture["current"],
                    label_manifest=fixture["label_manifest"],
                    feature_manifest=changed_feature,
                )
            changed_label = deepcopy(fixture["label_manifest"])
            changed_label["semantic_marker"] = "drift"
            with self.assertRaisesRegex(BenchmarkExportError, "label-manifest"):
                verify_frozen_manifest_contracts(
                    baseline=fixture["baseline"],
                    current_evidence=fixture["current"],
                    label_manifest=changed_label,
                    feature_manifest=fixture["feature_manifest"],
                )
            changed_schema = deepcopy(fixture["feature_manifest"])
            changed_schema["feature_schema"][0]["role"] = "PRE_MATCH_FEATURE"
            with self.assertRaises(BenchmarkError):
                verify_frozen_manifest_contracts(
                    baseline=fixture["baseline"],
                    current_evidence=fixture["current"],
                    label_manifest=fixture["label_manifest"],
                    feature_manifest=changed_schema,
                )

    def test_outputs_are_atomic_deterministic_utf8_lf_and_checkable(self):
        rows = self._rows()
        result = run_baseline_benchmarks(rows, self.FEATURE_NAMES)
        benchmark_bytes = render_benchmark_summary(result["benchmark"])
        prediction_bytes = render_prediction_csv(result["prediction_rows"])
        self.assertEqual(
            benchmark_bytes, render_benchmark_summary(result["benchmark"])
        )
        self.assertEqual(
            prediction_bytes, render_prediction_csv(result["prediction_rows"])
        )
        self.assertNotIn(b"\r\n", benchmark_bytes)
        self.assertNotIn(b"\r\n", prediction_bytes)
        benchmark_bytes.decode("utf-8", errors="strict")
        prediction_bytes.decode("utf-8", errors="strict")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "schema_version": 1,
                "files": {
                    "benchmark_summary": {"relative_name": "benchmark.json"},
                    "predictions": {"relative_name": "predictions.csv"},
                },
            }
            paths = (root / "benchmark.json", root / "predictions.csv", root / "manifest.json")
            calls = []
            original_replace = os.replace

            def record_replace(source, destination):
                calls.append((Path(source), Path(destination)))
                original_replace(source, destination)

            with patch(
                "scripts.export_win_either_half_baseline_benchmarks.os.replace",
                side_effect=record_replace,
            ):
                write_benchmark_outputs(
                    benchmark_path=paths[0],
                    prediction_path=paths[1],
                    manifest_path=paths[2],
                    benchmark_bytes=benchmark_bytes,
                    prediction_bytes=prediction_bytes,
                    manifest=manifest,
                )
            self.assertEqual(len(calls), 3)
            with self.assertRaisesRegex(BenchmarkExportError, "--force"):
                write_benchmark_outputs(
                    benchmark_path=paths[0],
                    prediction_path=paths[1],
                    manifest_path=paths[2],
                    benchmark_bytes=benchmark_bytes,
                    prediction_bytes=prediction_bytes,
                    manifest=manifest,
                )

    def test_manifest_records_configs_selection_dependencies_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_stack(Path(directory))
            _, predictors = verify_frozen_manifest_contracts(
                baseline=fixture["baseline"],
                current_evidence=fixture["current"],
                label_manifest=fixture["label_manifest"],
                feature_manifest=fixture["feature_manifest"],
            )
            rows, feature_identity = load_verified_feature_rows(
                fixture["feature_path"], fixture["feature_manifest"], predictors
            )
            result = run_baseline_benchmarks(rows, predictors)
            benchmark_bytes = render_benchmark_summary(result["benchmark"])
            prediction_bytes = render_prediction_csv(result["prediction_rows"])
            manifest = build_benchmark_manifest(
                benchmark=result["benchmark"],
                benchmark_bytes=benchmark_bytes,
                benchmark_relative_name="benchmarks.json",
                prediction_bytes=prediction_bytes,
                prediction_relative_name="predictions.csv",
                prediction_rows=len(result["prediction_rows"]),
                baseline=fixture["baseline"],
                label_manifest=fixture["label_manifest"],
                feature_manifest=fixture["feature_manifest"],
                feature_csv_identity=feature_identity,
                predictor_names=predictors,
                generator_code_state=deepcopy(self.CODE_STATE),
                dependencies={"python": "test", "scikit_learn": "test"},
                numerical_runtime={
                    "python_version": "test",
                    "thread_limit": NUMERICAL_THREAD_LIMIT,
                },
                generated_at_utc="2026-08-01T00:00:00Z",
            )
            self.assertEqual(manifest["selection_rule"], SELECTION_RULE)
            self.assertEqual(manifest["targets"], list(TARGETS))
            self.assertEqual(
                manifest["files"]["benchmark_summary"]["sha256"],
                hashlib.sha256(benchmark_bytes).hexdigest(),
            )
            self.assertEqual(
                manifest["stage_3_features"]["feature_csv"], feature_identity
            )
            self.assertEqual(
                manifest["market_safety"]["home_win_either_half"], "DISABLED"
            )
            self.assertEqual(
                manifest["numerical_reproducibility"]["thread_limit"],
                NUMERICAL_THREAD_LIMIT,
            )
            self.assertEqual(
                manifest["numerical_reproducibility"][
                    "canonical_decimal_places"
                ],
                CANONICAL_DECIMAL_PLACES,
            )
            later = deepcopy(manifest)
            later["generated_at_utc"] = "2030-01-01T00:00:00Z"
            self.assertEqual(compare_benchmark_manifests(manifest, later), [])
            drifted = deepcopy(manifest)
            drifted["stage_3_features"][
                "feature_manifest_logical_sha256"
            ] = "drift"
            self.assertIn(
                "Stage 3 feature identity differs",
                compare_benchmark_manifests(manifest, drifted),
            )
            runtime_drifted = deepcopy(manifest)
            runtime_drifted["numerical_reproducibility"]["runtime"][
                "python_version"
            ] = "different"
            self.assertIn(
                "numerical runtime contract differs",
                compare_benchmark_manifests(manifest, runtime_drifted),
            )

    def test_no_network_and_frozen_files_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_stack(Path(directory))
            protected = (
                fixture["database"],
                fixture["baseline_path"],
                fixture["label_manifest_path"],
                fixture["feature_manifest_path"],
                fixture["feature_path"],
            )
            before = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in protected
            }
            _, predictors = verify_frozen_manifest_contracts(
                baseline=fixture["baseline"],
                current_evidence=fixture["current"],
                label_manifest=fixture["label_manifest"],
                feature_manifest=fixture["feature_manifest"],
            )
            rows, _ = load_verified_feature_rows(
                fixture["feature_path"], fixture["feature_manifest"], predictors
            )
            with patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access is forbidden"),
            ):
                run_baseline_benchmarks(rows, predictors)
            after = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in protected
            }
            self.assertEqual(before, after)

    def _assert_real_entrypoint(self, command_prefix):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._frozen_stack(root / "frozen", get_code_state())
            benchmark = root / "benchmarks.json"
            predictions = root / "predictions.csv"
            manifest = root / "benchmark-manifest.json"
            protected = (
                fixture["database"],
                fixture["baseline_path"],
                fixture["label_manifest_path"],
                fixture["feature_manifest_path"],
                fixture["feature_path"],
            )
            before = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in protected
            }
            common = [
                "--database", str(fixture["database"]),
                "--cache-directory", str(fixture["cache"]),
                "--baseline", str(fixture["baseline_path"]),
                "--label-manifest", str(fixture["label_manifest_path"]),
                "--feature-manifest", str(fixture["feature_manifest_path"]),
                "--feature-csv", str(fixture["feature_path"]),
                "--expect-total-rows", "24",
                "--expect-train-rows", "12",
                "--expect-validation-rows", "6",
                "--expect-test-rows", "6",
            ]
            generation = subprocess.run(
                [
                    *command_prefix,
                    *common,
                    "--benchmark-output", str(benchmark),
                    "--predictions-output", str(predictions),
                    "--manifest-output", str(manifest),
                ],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                shell=False,
            )
            self.assertEqual(generation.returncode, 0, generation.stderr)
            verification = subprocess.run(
                [*command_prefix, *common, "--check", str(manifest)],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                shell=False,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            self.assertIn("Benchmark manifest verified", verification.stdout)
            self.assertEqual(
                before,
                {
                    path: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in protected
                },
            )

    def test_direct_script_generation_and_check(self):
        self._assert_real_entrypoint(
            [
                sys.executable,
                "scripts/export_win_either_half_baseline_benchmarks.py",
            ]
        )

    def test_module_generation_and_check(self):
        self._assert_real_entrypoint(
            [
                sys.executable,
                "-m",
                "scripts.export_win_either_half_baseline_benchmarks",
            ]
        )

    def test_help_invocations_are_cross_platform_and_side_effect_free(self):
        for command in (
            [
                sys.executable,
                "scripts/export_win_either_half_baseline_benchmarks.py",
                "--help",
            ],
            [
                sys.executable,
                "-m",
                "scripts.export_win_either_half_baseline_benchmarks",
                "--help",
            ],
        ):
            with self.subTest(command=command):
                result = subprocess.run(
                    command,
                    cwd=self.REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                    shell=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--feature-csv", result.stdout)
                self.assertIn("--check", result.stdout)

    def test_no_generated_rows_or_databases_are_tracked_and_markets_unselectable(self):
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status,
            ModelStatus.EXPERIMENTAL,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status,
            ModelStatus.EXPERIMENTAL,
        )
        self.assertFalse(
            MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].selectable
        )
        self.assertFalse(
            MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].selectable
        )
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
        forbidden_paths = (
            ".cache/athena-research/win-either-half/benchmarks-v1.json",
            ".cache/athena-research/win-either-half/predictions-v1.csv",
            "database/athena.db",
        )
        self.assertFalse(
            any(
                path.startswith(".cache/athena-research/")
                or path in forbidden_paths
                for path in tracked
            )
        )


if __name__ == "__main__":
    unittest.main()
