import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.database import Database
from domain.markets import MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_features import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA,
    FeatureRole,
    HistoricalLabelMatch,
    build_pre_match_feature_dataset,
)
from domain.win_either_half_research import build_win_either_half_labels
from scripts.audit_half_time_coverage import load_observations_from_database
from scripts.export_win_either_half_feature_dataset import (
    FeatureExportError,
    build_feature_manifest,
    compare_feature_manifests,
    load_verified_label_matches,
    main,
    render_feature_csv,
    validate_label_manifest_contract,
    write_feature_outputs,
)
from scripts.export_win_either_half_research_dataset import (
    ResearchExportError,
    build_research_manifest,
    render_dataset_csv,
    verify_stage_2_evidence,
)
from scripts.freeze_evidence_baseline import (
    build_evidence_baseline,
    get_code_state,
)


class WinEitherHalfFeatureTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    BASE_KICKOFF = datetime(2023, 1, 1, 15, 0, tzinfo=timezone.utc)
    CODE_STATE = {
        "evidence_git_head_sha": "a" * 40,
        "tracked_worktree_clean": True,
    }

    def _match(
        self,
        fixture_identity,
        day,
        home_team,
        away_team,
        *,
        full_time=(2, 1),
        half_time=(1, 0),
        split="TRAIN",
        season="2023-24",
        kickoff=None,
        target_overrides=None,
    ):
        second_home = full_time[0] - half_time[0]
        second_away = full_time[1] - half_time[1]
        home_first = int(half_time[0] > half_time[1])
        away_first = int(half_time[1] > half_time[0])
        home_second = int(second_home > second_away)
        away_second = int(second_away > second_home)
        targets = {
            "home_win_first_half": home_first,
            "away_win_first_half": away_first,
            "home_win_second_half": home_second,
            "away_win_second_half": away_second,
            "home_win_either_half_yes": int(home_first or home_second),
            "away_win_either_half_yes": int(away_first or away_second),
        }
        targets["both_teams_won_a_half"] = int(
            targets["home_win_either_half_yes"]
            and targets["away_win_either_half_yes"]
        )
        targets.update(target_overrides or {})
        return HistoricalLabelMatch(
            fixture_identity=fixture_identity,
            kickoff_utc=kickoff or self.BASE_KICKOFF + timedelta(days=day),
            league="E0",
            season=season,
            split=split,
            home_team=home_team,
            away_team=away_team,
            full_time_home_goals=full_time[0],
            full_time_away_goals=full_time[1],
            half_time_home_goals=half_time[0],
            half_time_away_goals=half_time[1],
            **targets,
        )

    @staticmethod
    def _row(dataset, fixture_identity):
        return next(
            row
            for row in dataset.rows
            if row["fixture_identity"] == fixture_identity
        )

    @staticmethod
    def _feature_values(row):
        feature_names = {
            column.name
            for column in FEATURE_SCHEMA
            if column.role == FeatureRole.PRE_MATCH_FEATURE
        }
        return {name: row[name] for name in feature_names}

    @staticmethod
    def _create_cache(cache: Path):
        cache.mkdir(parents=True)
        (cache / "2324_E0.csv").write_bytes(b"Div,FTHG,FTAG,HTHG,HTAG\n")

    def _create_database(self, database: Path):
        Database(str(database)).initialize()
        fixtures = (
            (1, 1, 2, "Alpha", "Beta", "2023-24", "2023-09-01T15:00:00+00:00", 2, 1, 1, 0),
            (2, 3, 1, "Gamma", "Alpha", "2024-25", "2024-09-01T15:00:00+00:00", 0, 3, 0, 1),
            (3, 1, 4, "Alpha", "Delta", "2025-26", "2025-09-01T15:00:00+00:00", 1, 1, 0, 0),
        )
        connection = sqlite3.connect(database)
        try:
            for team_id, name in ((1, "Alpha"), (2, "Beta"), (3, "Gamma"), (4, "Delta")):
                connection.execute(
                    "INSERT INTO teams (team_id, name, league) VALUES (?, ?, ?)",
                    (team_id, name, "E0"),
                )
            for (
                fixture_id,
                home_id,
                away_id,
                home_name,
                away_name,
                season,
                kickoff,
                ft_home,
                ft_away,
                ht_home,
                ht_away,
            ) in fixtures:
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
            connection.commit()
        finally:
            connection.close()

    def _frozen_fixture(self, root: Path, code_state=None):
        root.mkdir(parents=True, exist_ok=True)
        database = root / "athena.db"
        cache = root / "cache"
        baseline_path = root / "baseline.json"
        label_manifest_path = root / "labels-manifest.json"
        labels_path = root / "labels.csv"
        self._create_database(database)
        self._create_cache(cache)
        state = deepcopy(code_state or self.CODE_STATE)
        baseline = build_evidence_baseline(
            database_path=database,
            cache_directory=cache,
            baseline_name="test-stage-2",
            code_state=state,
            generated_at_utc="2026-07-31T00:00:00Z",
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
            generated_at_utc="2026-07-31T00:00:00Z",
        )
        baseline_path.write_text(
            json.dumps(baseline, sort_keys=True), encoding="utf-8"
        )
        label_manifest_path.write_text(
            json.dumps(label_manifest, sort_keys=True), encoding="utf-8"
        )
        labels_path.write_bytes(labels_bytes)
        return {
            "baseline": baseline,
            "baseline_path": baseline_path,
            "cache": cache,
            "current": current,
            "database": database,
            "label_manifest": label_manifest,
            "label_manifest_path": label_manifest_path,
            "labels_bytes": labels_bytes,
            "labels_path": labels_path,
        }

    def test_input_order_invariance(self):
        matches = (
            self._match("past-1", 0, "Alpha", "Beta"),
            self._match("past-2", 1, "Gamma", "Alpha", full_time=(0, 3), half_time=(0, 1)),
            self._match("target", 2, "Alpha", "Beta"),
        )
        forward = build_pre_match_feature_dataset(matches)
        reverse = build_pre_match_feature_dataset(reversed(matches))
        self.assertEqual(forward, reverse)
        self.assertEqual(render_feature_csv(forward), render_feature_csv(reverse))

    def test_deterministic_utf8_lf_output(self):
        dataset = build_pre_match_feature_dataset(
            (self._match("unicode", 0, "Atlético", "Bayern"),)
        )
        first = render_feature_csv(dataset)
        second = render_feature_csv(dataset)
        self.assertEqual(first, second)
        self.assertIn("Atlético", first.decode("utf-8"))
        self.assertNotIn(b"\r\n", first)

    def test_target_score_changes_do_not_change_target_features(self):
        past = self._match("past", 0, "Alpha", "Beta")
        first_target = self._match("target", 1, "Alpha", "Gamma", full_time=(5, 0), half_time=(3, 0))
        second_target = self._match("target", 1, "Alpha", "Gamma", full_time=(0, 4), half_time=(0, 2))
        first = self._row(build_pre_match_feature_dataset((past, first_target)), "target")
        second = self._row(build_pre_match_feature_dataset((past, second_target)), "target")
        self.assertEqual(self._feature_values(first), self._feature_values(second))

    def test_target_label_changes_do_not_change_target_features(self):
        past = self._match("past", 0, "Alpha", "Beta")
        target = self._match("target", 1, "Alpha", "Gamma")
        changed = self._match(
            "target",
            1,
            "Alpha",
            "Gamma",
            target_overrides={
                "home_win_either_half_yes": 0,
                "away_win_either_half_yes": 1,
                "both_teams_won_a_half": 0,
            },
        )
        first = self._row(build_pre_match_feature_dataset((past, target)), "target")
        second = self._row(build_pre_match_feature_dataset((past, changed)), "target")
        self.assertEqual(self._feature_values(first), self._feature_values(second))

    def test_future_fixture_does_not_change_earlier_features(self):
        past = self._match("past", 0, "Alpha", "Beta")
        target = self._match("target", 1, "Alpha", "Gamma")
        future = self._match("future", 2, "Alpha", "Delta", full_time=(9, 0), half_time=(5, 0))
        without = self._row(build_pre_match_feature_dataset((past, target)), "target")
        with_future = self._row(build_pre_match_feature_dataset((future, target, past)), "target")
        self.assertEqual(self._feature_values(without), self._feature_values(with_future))

    def test_same_kickoff_fixture_is_excluded_from_target_history(self):
        kickoff = self.BASE_KICKOFF + timedelta(days=1)
        earlier = self._match("earlier", 0, "Alpha", "Beta")
        same = self._match("same", 1, "Alpha", "Gamma", kickoff=kickoff)
        target = self._match("target", 1, "Alpha", "Delta", kickoff=kickoff)
        row = self._row(build_pre_match_feature_dataset((same, target, earlier)), "target")
        self.assertEqual(row["home_team_prior_overall_matches"], 1)
        self.assertEqual(row["home_team_overall_w5_observation_count"], 1)

    def test_later_splits_never_affect_earlier_train_features(self):
        validation = self._match("validation", 0, "Alpha", "Beta", split="VALIDATION", season="2024-25")
        test = self._match("test", 1, "Alpha", "Gamma", split="TEST", season="2025-26")
        train = self._match("train", 2, "Alpha", "Delta", split="TRAIN", season="2023-24")
        row = self._row(build_pre_match_feature_dataset((validation, test, train)), "train")
        self.assertEqual(row["home_team_prior_overall_matches"], 0)
        self.assertEqual(row["home_team_no_prior_history"], 1)

    def test_rolling_formulas_team_perspective_and_venue_history_are_exact(self):
        matches = (
            self._match("past-home", 0, "Alpha", "Beta", full_time=(2, 1), half_time=(1, 0)),
            self._match("past-away", 1, "Gamma", "Alpha", full_time=(0, 3), half_time=(0, 1)),
            self._match("target", 2, "Alpha", "Beta"),
        )
        row = self._row(build_pre_match_feature_dataset(matches), "target")
        self.assertEqual(row["home_team_prior_overall_matches"], 2)
        self.assertEqual(row["home_team_prior_relevant_venue_matches"], 1)
        self.assertEqual(row["home_team_days_since_previous_fixture"], 1.0)
        self.assertEqual(row["home_team_overall_w5_observation_count"], 2)
        self.assertEqual(row["home_team_overall_w5_goals_for_per_match"], 2.5)
        self.assertEqual(row["home_team_overall_w5_goals_against_per_match"], 0.5)
        self.assertEqual(row["home_team_overall_w5_first_half_goals_for_per_match"], 1.0)
        self.assertEqual(row["home_team_overall_w5_first_half_goals_against_per_match"], 0.0)
        self.assertEqual(row["home_team_overall_w5_first_half_win_rate"], 1.0)
        self.assertEqual(row["home_team_overall_w5_second_half_win_rate"], 0.5)
        self.assertEqual(row["home_team_overall_w5_win_either_half_yes_rate"], 1.0)
        self.assertEqual(row["home_team_home_w5_observation_count"], 1)
        self.assertEqual(row["home_team_home_w5_goals_for_per_match"], 2.0)
        self.assertEqual(row["away_team_prior_overall_matches"], 1)
        self.assertEqual(row["away_team_prior_relevant_venue_matches"], 1)
        self.assertEqual(row["away_team_away_w5_goals_for_per_match"], 1.0)
        self.assertEqual(row["away_team_away_w5_goals_against_per_match"], 2.0)
        self.assertEqual(row["away_team_away_w5_first_half_goals_for_per_match"], 0.0)
        self.assertEqual(row["away_team_away_w5_first_half_goals_against_per_match"], 1.0)

    def test_no_history_and_partial_history_remain_explicitly_missing(self):
        first = self._match("first", 0, "Alpha", "Beta")
        second = self._match("second", 1, "Alpha", "Gamma")
        dataset = build_pre_match_feature_dataset((second, first))
        first_row = self._row(dataset, "first")
        second_row = self._row(dataset, "second")
        self.assertEqual(first_row["home_team_prior_overall_matches"], 0)
        self.assertEqual(first_row["home_team_no_prior_history"], 1)
        self.assertEqual(first_row["home_team_days_since_previous_missing"], 1)
        self.assertIsNone(first_row["home_team_days_since_previous_fixture"])
        self.assertEqual(first_row["home_team_overall_w5_observation_count"], 0)
        self.assertIsNone(first_row["home_team_overall_w5_goals_for_per_match"])
        self.assertEqual(second_row["home_team_overall_w10_observation_count"], 1)
        self.assertEqual(second_row["home_team_overall_w10_goals_for_per_match"], 2.0)

    def test_feature_roles_prohibit_target_and_result_leakage(self):
        roles = {column.name: column.role for column in FEATURE_SCHEMA}
        for target in (
            "home_win_either_half_yes",
            "away_win_either_half_yes",
            "both_teams_won_a_half",
        ):
            self.assertEqual(roles[target], FeatureRole.TARGET_ONLY)
        for forbidden in (
            "full_time_home_goals",
            "full_time_away_goals",
            "half_time_home_goals",
            "half_time_away_goals",
            "second_half_home_goals",
            "second_half_away_goals",
            "first_half_outcome",
            "second_half_outcome",
        ):
            self.assertNotIn(forbidden, FEATURE_COLUMNS)

    def test_frozen_season_and_split_assignments_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_fixture(Path(directory))
            split_config = validate_label_manifest_contract(
                fixture["label_manifest"],
                baseline=fixture["baseline"],
                current_evidence=fixture["current"],
            )
            matches, _ = load_verified_label_matches(
                fixture["labels_path"],
                fixture["label_manifest"],
                split_config,
            )
            expected = {
                "2023-24": "TRAIN",
                "2024-25": "VALIDATION",
                "2025-26": "TEST",
            }
            self.assertEqual(
                {match.season: match.split for match in matches},
                expected,
            )

    def test_labels_csv_hash_size_and_row_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_fixture(Path(directory))
            config = validate_label_manifest_contract(
                fixture["label_manifest"],
                baseline=fixture["baseline"],
                current_evidence=fixture["current"],
            )
            original = fixture["labels_path"].read_bytes()
            changed = bytearray(original)
            changed[-2] = ord("9") if changed[-2] != ord("9") else ord("8")
            fixture["labels_path"].write_bytes(bytes(changed))
            with self.assertRaisesRegex(FeatureExportError, "SHA-256"):
                load_verified_label_matches(
                    fixture["labels_path"], fixture["label_manifest"], config
                )
            fixture["labels_path"].write_bytes(original + b"x")
            with self.assertRaisesRegex(FeatureExportError, "byte size"):
                load_verified_label_matches(
                    fixture["labels_path"], fixture["label_manifest"], config
                )
            fixture["labels_path"].write_bytes(original)
            drifted = deepcopy(fixture["label_manifest"])
            drifted["files"]["labels"]["rows"] += 1
            with self.assertRaises(FeatureExportError):
                load_verified_label_matches(
                    fixture["labels_path"], drifted, config
                )

    def test_stage_2_evidence_and_label_manifest_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_fixture(Path(directory))
            database = fixture["database"]
            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE half_time_observations SET half_time_home_goals = 0 WHERE fixture_identity = '1'"
            )
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(
                ResearchExportError,
                "logical evidence",
            ):
                verify_stage_2_evidence(
                    fixture["baseline"],
                    database_path=database,
                    cache_directory=fixture["cache"],
                )

            drifted = deepcopy(fixture["label_manifest"])
            drifted["stage_2_baseline"]["schema_sha256"] = "drift"
            with self.assertRaisesRegex(FeatureExportError, "Stage 2"):
                validate_label_manifest_contract(
                    drifted,
                    baseline=fixture["baseline"],
                    current_evidence=fixture["current"],
                )

    def test_database_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._frozen_fixture(Path(directory))
            before = hashlib.sha256(fixture["database"].read_bytes()).hexdigest()
            config = validate_label_manifest_contract(
                fixture["label_manifest"],
                baseline=fixture["baseline"],
                current_evidence=fixture["current"],
            )
            matches, _ = load_verified_label_matches(
                fixture["labels_path"], fixture["label_manifest"], config
            )
            build_pre_match_feature_dataset(matches)
            after = hashlib.sha256(fixture["database"].read_bytes()).hexdigest()
            self.assertEqual(before, after)

    def test_feature_manifest_and_atomic_output_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._frozen_fixture(root / "frozen")
            config = validate_label_manifest_contract(
                fixture["label_manifest"],
                baseline=fixture["baseline"],
                current_evidence=fixture["current"],
            )
            matches, label_identity = load_verified_label_matches(
                fixture["labels_path"], fixture["label_manifest"], config
            )
            dataset = build_pre_match_feature_dataset(matches)
            feature_bytes = render_feature_csv(dataset)
            manifest_bytes = fixture["label_manifest_path"].read_bytes()
            manifest = build_feature_manifest(
                dataset,
                feature_bytes=feature_bytes,
                feature_relative_name="features.csv",
                baseline=fixture["baseline"],
                label_manifest=fixture["label_manifest"],
                label_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                label_csv_identity=label_identity,
                generator_code_state=deepcopy(self.CODE_STATE),
                generated_at_utc="2026-07-31T00:00:00Z",
            )
            later = deepcopy(manifest)
            later["generated_at_utc"] = "2030-01-01T00:00:00Z"
            self.assertEqual(compare_feature_manifests(manifest, later), [])
            self.assertEqual(manifest["files"]["features"]["rows"], 3)
            self.assertEqual(manifest["splits"]["train"]["rows"], 1)
            self.assertEqual(manifest["splits"]["validation"]["rows"], 1)
            self.assertEqual(manifest["splits"]["test"]["rows"], 1)
            feature_path = root / "features.csv"
            output_manifest = root / "manifest.json"
            calls = []
            original_replace = os.replace

            def recording_replace(source, destination):
                calls.append((Path(source), Path(destination)))
                original_replace(source, destination)

            with patch(
                "scripts.export_win_either_half_feature_dataset.os.replace",
                side_effect=recording_replace,
            ):
                write_feature_outputs(
                    feature_path=feature_path,
                    manifest_path=output_manifest,
                    feature_bytes=feature_bytes,
                    manifest=manifest,
                )
            self.assertEqual(len(calls), 2)
            with self.assertRaisesRegex(FeatureExportError, "--force"):
                write_feature_outputs(
                    feature_path=feature_path,
                    manifest_path=output_manifest,
                    feature_bytes=feature_bytes,
                    manifest=manifest,
                )

    def _assert_real_entrypoint(self, command_prefix):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._frozen_fixture(root / "frozen", get_code_state())
            features = root / "features.csv"
            feature_manifest = root / "features-manifest.json"
            common = [
                "--database", str(fixture["database"]),
                "--cache-directory", str(fixture["cache"]),
                "--baseline", str(fixture["baseline_path"]),
                "--label-manifest", str(fixture["label_manifest_path"]),
                "--labels-input", str(fixture["labels_path"]),
            ]
            generation = subprocess.run(
                [
                    *command_prefix,
                    *common,
                    "--features-output", str(features),
                    "--manifest-output", str(feature_manifest),
                    "--expect-rows", "3",
                ],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
                shell=False,
            )
            self.assertEqual(generation.returncode, 0, generation.stderr)
            verification = subprocess.run(
                [*command_prefix, *common, "--check", str(feature_manifest)],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
                shell=False,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            self.assertIn("Feature manifest verified", verification.stdout)

    def test_direct_script_generation_and_check(self):
        self._assert_real_entrypoint(
            [sys.executable, "scripts/export_win_either_half_feature_dataset.py"]
        )

    def test_module_generation_and_check(self):
        self._assert_real_entrypoint(
            [sys.executable, "-m", "scripts.export_win_either_half_feature_dataset"]
        )

    def test_help_invocations_require_no_network_or_database(self):
        for command in (
            [sys.executable, "scripts/export_win_either_half_feature_dataset.py", "--help"],
            [sys.executable, "-m", "scripts.export_win_either_half_feature_dataset", "--help"],
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
                self.assertIn("--labels-input", result.stdout)
                self.assertIn("--expect-rows", result.stdout)

    def test_both_markets_disabled_and_no_production_outputs_tracked(self):
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
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
        self.assertNotIn(
            "artifacts/research-manifests/win-either-half-features-v1.json",
            tracked,
        )
        self.assertFalse(any(path.endswith("features-v1.csv") for path in tracked))
        self.assertFalse(any(path.endswith("athena.db") for path in tracked))


if __name__ == "__main__":
    unittest.main()
