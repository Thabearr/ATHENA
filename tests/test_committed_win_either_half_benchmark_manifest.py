import json
import re
import subprocess
import unittest
from copy import deepcopy
from pathlib import Path

from domain.markets import MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from scripts.export_win_either_half_baseline_benchmarks import (
    compare_benchmark_manifests,
)
from scripts.export_win_either_half_feature_dataset import canonical_json_sha256


class CommittedWinEitherHalfBenchmarkManifestTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    MANIFEST_RELATIVE_PATH = (
        "artifacts/research-manifests/win-either-half-benchmarks-v1.json"
    )

    @classmethod
    def setUpClass(cls):
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

    @classmethod
    def _load_json(cls, relative_path):
        return json.loads(
            (cls.REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        )

    def test_dataset_schema_ancestry_and_feature_identity_are_frozen(self):
        manifest = self.manifest
        self.assertEqual(
            manifest["dataset_name"],
            "win-either-half-baseline-benchmarks-v1",
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["stage_2_evidence"],
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
            manifest["stage_3_labels"],
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
            manifest["stage_3_features"],
            {
                "dataset_name": self.feature_manifest["dataset_name"],
                "feature_csv": {
                    key: self.feature_manifest["files"]["features"][key]
                    for key in ("byte_size", "rows", "sha256")
                },
                "feature_manifest_logical_sha256": canonical_json_sha256(
                    self.feature_manifest
                ),
                "generator_git_head_sha": self.feature_manifest["generator"][
                    "generator_git_head_sha"
                ],
            },
        )

    def test_frozen_counts_models_and_numerical_contract(self):
        self.assertEqual(
            self.manifest["stage_3_features"]["feature_csv"]["rows"], 21791
        )
        self.assertEqual(
            {
                split: self.manifest["splits"][split]["rows"]
                for split in ("train", "validation", "test")
            },
            {"train": 14267, "validation": 3476, "test": 4048},
        )
        self.assertEqual(
            sum(value["rows"] for value in self.manifest["splits"].values()),
            21791,
        )
        self.assertEqual(self.manifest["files"]["predictions"]["rows"], 43582)
        self.assertEqual(
            self.manifest["selected_models"],
            {
                "away_win_either_half_yes": "logistic_l2_c0.1_v1",
                "home_win_either_half_yes": "logistic_l2_c0.1_v1",
            },
        )
        numerical = self.manifest["numerical_reproducibility"]
        self.assertEqual(numerical["canonical_decimal_places"], 12)
        self.assertEqual(numerical["thread_limit"], 1)
        self.assertEqual(numerical["runtime"]["thread_limit"], 1)

    def test_frozen_output_identities_are_complete(self):
        expected = {
            "benchmark_summary": {
                "byte_size": 165692,
                "sha256": (
                    "e6c2157f137a7d243f38d3a55a087e9b2ab9cb2536ab2a1544e1125362c9253f"
                ),
            },
            "predictions": {
                "byte_size": 5063993,
                "sha256": (
                    "02790fdb2c4549adb27d3a086d522491215ac7a2b9889375208cae96f32873a1"
                ),
            },
        }
        for name, identity in expected.items():
            with self.subTest(name=name):
                actual = self.manifest["files"][name]
                self.assertEqual(actual["byte_size"], identity["byte_size"])
                self.assertEqual(actual["sha256"], identity["sha256"])
                self.assertRegex(actual["sha256"], re.compile(r"^[0-9a-f]{64}$"))

    def test_timestamp_is_not_semantic_drift(self):
        changed_timestamp = deepcopy(self.manifest)
        changed_timestamp["generated_at_utc"] = "2099-01-01T00:00:00Z"
        self.assertEqual(
            compare_benchmark_manifests(self.manifest, changed_timestamp), []
        )

    def test_row_outputs_database_and_research_model_binaries_are_not_tracked(self):
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
        self.assertNotIn(
            ".cache/athena-research/win-either-half/benchmarks-v1.json",
            tracked,
        )
        self.assertNotIn(
            ".cache/athena-research/win-either-half/predictions-v1.csv",
            tracked,
        )
        self.assertFalse(any(path.lower().endswith(".db") for path in tracked))
        research_model_suffixes = (".joblib", ".pickle", ".pkl")
        self.assertFalse(
            any(
                "win-either-half" in path.lower()
                and path.lower().endswith(research_model_suffixes)
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


if __name__ == "__main__":
    unittest.main()
