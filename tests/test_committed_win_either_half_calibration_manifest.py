import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from domain.markets import MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_calibration import (
    EVALUATION_ROLE_SCOPES,
    PROBABILITY_BANDS,
    build_subgroup_evaluations,
)
from scripts.export_win_either_half_calibration_research import (
    compare_calibration_manifests,
)
from scripts.export_win_either_half_feature_dataset import canonical_json_sha256
from scripts.freeze_evidence_baseline import BaselineError, verify_revision_relationship


class CommittedWinEitherHalfCalibrationManifestTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    MANIFEST_RELATIVE_PATH = (
        "artifacts/research-manifests/win-either-half-calibration-v1.json"
    )
    TARGETS = (
        "home_win_either_half_yes",
        "away_win_either_half_yes",
    )
    ROLE_ROW_COUNTS = {
        "CALIBRATION_FIT_OOF": 172,
        "VALIDATION_SELECTION": 92,
        "FINAL_TEST": 92,
    }
    RESEARCH_ROW_ACCOUNTING = {
        "oof_calibration_fit_rows_per_target": 10635,
        "oof_excluded_season": "2020-21",
        "validation_rows_per_target": 3476,
        "final_test_rows_per_target": 4048,
    }
    FINAL_TEST_SUBGROUP_ACCOUNTING = {
        target: {
            "league_groups": 20,
            "league_rows": 4048,
            "probability_band_groups": 5,
            "probability_band_rows": 4048,
        }
        for target in TARGETS
    }

    @classmethod
    def setUpClass(cls):
        cls.manifest_path = cls.REPOSITORY_ROOT / cls.MANIFEST_RELATIVE_PATH
        cls.manifest = cls._load_json(cls.MANIFEST_RELATIVE_PATH)
        cls.baseline = cls._load_json(
            "artifacts/evidence-baselines/half-time-ready-for-research.json"
        )
        cls.label_manifest = cls._load_json(
            "artifacts/research-manifests/win-either-half-labels-v1.json"
        )
        cls.feature_manifest = cls._load_json(
            "artifacts/research-manifests/win-either-half-features-v1.json"
        )
        cls.benchmark_manifest = cls._load_json(
            "artifacts/research-manifests/win-either-half-benchmarks-v1.json"
        )

    @classmethod
    def _load_json(cls, relative_path):
        return json.loads(
            (cls.REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        )

    def test_manifest_file_and_frozen_ancestry_are_exact(self):
        self.assertEqual(self.manifest_path.stat().st_size, 6176)
        self.assertEqual(
            hashlib.sha256(self.manifest_path.read_bytes()).hexdigest(),
            "5b658f6d3e22143f06f45df535052886d2b3a1cbf2618be0be4ed7f40bda5b54",
        )
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(
            self.manifest["dataset_name"], "win-either-half-calibration-v1"
        )
        self.assertEqual(
            self.manifest["stage_2_evidence"],
            {
                "baseline_name": self.baseline["baseline_name"],
                "cache_manifest_sha256": self.baseline[
                    "football_data_uk_cache"
                ]["manifest_sha256"],
                "evidence_git_head_sha": self.baseline["code"][
                    "evidence_git_head_sha"
                ],
                "logical_evidence_sha256": self.baseline["database"][
                    "logical_evidence_sha256"
                ],
                "schema_sha256": self.baseline["database"]["schema_sha256"],
            },
        )
        self.assertEqual(
            self.manifest["stage_3_labels"],
            {
                "dataset_name": self.label_manifest["dataset_name"],
                "generator_git_head_sha": self.label_manifest["generator"][
                    "generator_git_head_sha"
                ],
                "label_manifest_logical_sha256": canonical_json_sha256(
                    self.label_manifest
                ),
            },
        )
        self.assertEqual(
            self.manifest["stage_3_features"],
            {
                "dataset_name": self.feature_manifest["dataset_name"],
                "feature_manifest_logical_sha256": canonical_json_sha256(
                    self.feature_manifest
                ),
                "generator_git_head_sha": self.feature_manifest["generator"][
                    "generator_git_head_sha"
                ],
            },
        )
        self.assertEqual(
            self.manifest["stage_4_benchmarks"],
            {
                "benchmark_manifest_logical_sha256": canonical_json_sha256(
                    self.benchmark_manifest
                ),
                "dataset_name": self.benchmark_manifest["dataset_name"],
                "generator_git_head_sha": self.benchmark_manifest["generator"][
                    "generator_git_head_sha"
                ],
                "selected_models": self.benchmark_manifest["selected_models"],
            },
        )

    def test_frozen_inputs_splits_and_numerical_contract(self):
        self.assertEqual(
            self.manifest["input_files"],
            {
                "feature_csv": {
                    "byte_size": 8032209,
                    "rows": 21791,
                    "sha256": "68547ae9670703c59d68367d8fa1ef067e7410d8beb842ad0aec2151f0777e7b",
                },
                "stage_4_benchmark_summary": {
                    "byte_size": 165692,
                    "sha256": "e6c2157f137a7d243f38d3a55a087e9b2ab9cb2536ab2a1544e1125362c9253f",
                },
                "stage_4_predictions": {
                    "byte_size": 5063993,
                    "rows": 43582,
                    "sha256": "02790fdb2c4549adb27d3a086d522491215ac7a2b9889375208cae96f32873a1",
                },
            },
        )
        self.assertEqual(
            {
                split: self.manifest["temporal_splits"][split]["rows"]
                for split in ("train", "validation", "test")
            },
            {"train": 14267, "validation": 3476, "test": 4048},
        )
        numerical = self.manifest["numerical_reproducibility"]
        self.assertEqual(numerical["canonical_decimal_places"], 12)
        self.assertEqual(numerical["random_seed"], 1729)
        self.assertEqual(numerical["thread_limit"], 1)
        self.assertEqual(numerical["runtime"]["thread_limit"], 1)

    def test_frozen_selections_and_output_identities_are_exact(self):
        self.assertEqual(
            self.manifest["selected_calibrations"],
            {
                "away_win_either_half_yes": "identity_calibration_v1",
                "home_win_either_half_yes": "isotonic_calibration_v1",
            },
        )
        expected = {
            "calibration_summary": {
                "byte_size": 65337,
                "sha256": "957ffb850354173f84f1f3b44e8e5bff83c74357bdebc90c091c1f5ca997dfda",
            },
            "calibrated_predictions": {
                "byte_size": 6705242,
                "rows": 36318,
                "sha256": "6e931ae156f7319bc9cba2647e746471422adafad8e431981bdb573ca64c44d4",
            },
            "subgroups": {
                "byte_size": 1442351,
                "rows": 356,
                "sha256": "92035cfe39d6259fe24387811ccd62575a00b114ca3e220ac19baf3985f5cdb8",
            },
        }
        for name, identity in expected.items():
            with self.subTest(name=name):
                actual = self.manifest["files"][name]
                for key, value in identity.items():
                    self.assertEqual(actual[key], value)
                self.assertRegex(actual["sha256"], re.compile(r"^[0-9a-f]{64}$"))

    def test_frozen_subgroup_role_and_final_test_accounting(self):
        # These reviewed accounting constants are bound to the exact frozen
        # subgroup CSV identity asserted above; CI does not need the ignored CSV.
        scopes = self.manifest["subgroup_policy"]["evaluation_role_scopes"]
        self.assertEqual(scopes, EVALUATION_ROLE_SCOPES)
        self.assertEqual(sum(self.ROLE_ROW_COUNTS.values()), 356)
        self.assertEqual(
            sum(self.ROLE_ROW_COUNTS.values()),
            self.manifest["files"]["subgroups"]["rows"],
        )
        frozen_league_count = len(self.label_manifest["breakdowns"]["by_league"])
        self.assertEqual(frozen_league_count, 20)
        self.assertEqual(len(PROBABILITY_BANDS), 5)
        role_season_counts = {
            "CALIBRATION_FIT_OOF": 3,
            "VALIDATION_SELECTION": 1,
            "FINAL_TEST": 1,
        }
        for role, season_count in role_season_counts.items():
            per_target = 1 + frozen_league_count + len(PROBABILITY_BANDS)
            per_target += frozen_league_count * season_count
            self.assertEqual(per_target * len(self.TARGETS), self.ROLE_ROW_COUNTS[role])
        for target in self.TARGETS:
            with self.subTest(target=target):
                accounting = self.FINAL_TEST_SUBGROUP_ACCOUNTING[target]
                self.assertEqual(accounting["league_groups"], frozen_league_count)
                self.assertEqual(
                    accounting["league_rows"],
                    self.manifest["temporal_splits"]["test"]["rows"],
                )
                self.assertEqual(
                    accounting["probability_band_groups"], len(PROBABILITY_BANDS)
                )
                self.assertEqual(
                    accounting["probability_band_rows"],
                    self.manifest["temporal_splits"]["test"]["rows"],
                )
        self.assertEqual(
            self.RESEARCH_ROW_ACCOUNTING,
            {
                "oof_calibration_fit_rows_per_target": 10635,
                "oof_excluded_season": "2020-21",
                "validation_rows_per_target": self.manifest["temporal_splits"][
                    "validation"
                ]["rows"],
                "final_test_rows_per_target": self.manifest["temporal_splits"][
                    "test"
                ]["rows"],
            },
        )

    def test_subgroup_tooling_preserves_roles_and_fit_sample_unavailability(self):
        rows = []
        role_rows = (
            ("CALIBRATION_FIT_OOF", "TRAIN", "2021-22"),
            ("VALIDATION_SELECTION", "VALIDATION", "2024-25"),
            ("FINAL_TEST", "TEST", "2025-26"),
        )
        for target in self.TARGETS:
            for role, split, season in role_rows:
                rows.append(
                    {
                        "calibrated_probability": 0.6,
                        "league": "E0",
                        "model_probability": 0.55,
                        "prediction_role": role,
                        "season": season,
                        "split": split,
                        "target_name": target,
                        "target_value": 1,
                    }
                )
        records = build_subgroup_evaluations(rows, frozen_leagues=("E0",))
        self.assertTrue(records)
        for record in records:
            self.assertEqual(
                record["evaluation_scope"],
                EVALUATION_ROLE_SCOPES[record["evaluation_role"]],
            )
        fit_records = [
            row for row in records if row["evaluation_role"] == "CALIBRATION_FIT_OOF"
        ]
        self.assertTrue(fit_records)
        for record in fit_records:
            selected = record["selected_calibration"]
            self.assertEqual(selected["evaluation_status"], "UNAVAILABLE")
            self.assertEqual(selected["evaluation_reason"], "CALIBRATION_FIT_SAMPLE")
            self.assertEqual(selected["metric_reasons"], ["CALIBRATION_FIT_SAMPLE"])
        self.assertEqual(
            {row["evaluation_scope"] for row in records},
            {
                "CALIBRATION_FIT_SAMPLE",
                "SELECTION_SAMPLE",
                "INDEPENDENT_FINAL_TEST",
            },
        )
        for target in self.TARGETS:
            final = [
                row
                for row in records
                if row["target_name"] == target
                and row["evaluation_role"] == "FINAL_TEST"
            ]
            leagues = [row for row in final if row["dimension"] == "split_and_league"]
            bands = [
                row
                for row in final
                if row["dimension"] == "split_and_model_probability_band"
            ]
            self.assertEqual(sum(row["row_count"] for row in leagues), 1)
            self.assertEqual(len(bands), 5)
            self.assertEqual(sum(row["row_count"] for row in bands), 1)

    def test_generated_timestamp_is_not_semantic_drift(self):
        changed_timestamp = deepcopy(self.manifest)
        changed_timestamp["generated_at_utc"] = "2099-01-01T00:00:00Z"
        self.assertEqual(
            compare_calibration_manifests(self.manifest, changed_timestamp), []
        )

    def test_artifact_only_descendant_revision_policy_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)

            def git(*arguments):
                result = subprocess.run(
                    ["git", *arguments],
                    cwd=repository,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                    shell=False,
                    check=True,
                )
                return result.stdout.strip()

            git("init")
            git("config", "user.email", "athena-tests@example.invalid")
            git("config", "user.name", "ATHENA Tests")
            (repository / "tool.py").write_text("# generator\n", encoding="utf-8")
            git("add", "tool.py")
            git("commit", "-m", "Add generator")
            evidence_sha = git("rev-parse", "HEAD")
            artifact = repository / self.MANIFEST_RELATIVE_PATH
            artifact.parent.mkdir(parents=True)
            artifact.write_text("{}\n", encoding="utf-8", newline="\n")
            git("add", self.MANIFEST_RELATIVE_PATH)
            git("commit", "-m", "Freeze artifact")
            artifact_sha = git("rev-parse", "HEAD")
            relationship = verify_revision_relationship(
                {"evidence_git_head_sha": evidence_sha},
                {
                    "evidence_git_head_sha": artifact_sha,
                    "tracked_worktree_clean": True,
                },
                check_path=artifact,
                repository_root=repository,
            )
            self.assertEqual(relationship["mode"], "artifact_only_descendant")

            (repository / "README.md").write_text("drift\n", encoding="utf-8")
            git("add", "README.md")
            git("commit", "-m", "Add other tracked change")
            with self.assertRaisesRegex(BaselineError, "other than the checked"):
                verify_revision_relationship(
                    {"evidence_git_head_sha": evidence_sha},
                    {
                        "evidence_git_head_sha": git("rev-parse", "HEAD"),
                        "tracked_worktree_clean": True,
                    },
                    check_path=artifact,
                    repository_root=repository,
                )

    def test_row_outputs_database_and_model_objects_are_not_tracked(self):
        tracked = set(
            subprocess.run(
                ["git", "ls-files"],
                cwd=self.REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                shell=False,
                check=True,
            ).stdout.splitlines()
        )
        self.assertIn(self.MANIFEST_RELATIVE_PATH, tracked)
        for path in (
            ".cache/athena-research/win-either-half/calibration-v1.json",
            ".cache/athena-research/win-either-half/calibrated-predictions-v1.csv",
            ".cache/athena-research/win-either-half/calibration-subgroups-v1.csv",
        ):
            self.assertNotIn(path, tracked)
        self.assertFalse(any(path.lower().endswith(".db") for path in tracked))
        object_suffixes = (".joblib", ".pickle", ".pkl")
        self.assertFalse(
            any(
                "win-either-half" in path.lower()
                and path.lower().endswith(object_suffixes)
                for path in tracked
            )
        )

    def test_market_safety_remains_disabled(self):
        self.assertEqual(
            self.manifest["market_safety"],
            {
                "away_win_either_half": "DISABLED",
                "home_win_either_half": "DISABLED",
            },
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.HOME_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[MarketId.AWAY_WIN_EITHER_HALF].status,
            ModelStatus.DISABLED,
        )


if __name__ == "__main__":
    unittest.main()
