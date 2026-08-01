#!/usr/bin/env python3
"""Generate deterministic Stage 4B calibration and stability research outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.win_either_half_benchmarks import (  # noqa: E402
    CANONICAL_DECIMAL_PLACES,
    DEFAULT_RANDOM_SEED,
    NUMERICAL_THREAD_LIMIT,
    TARGETS,
    ModelConfiguration,
)
from domain.win_either_half_calibration import (  # noqa: E402
    CALIBRATION_SELECTION_RULE,
    FROZEN_STAGE_4_BASE_CONFIGURATION,
    CalibrationError,
    default_calibration_configurations,
    run_calibration_research,
)
from scripts.export_win_either_half_baseline_benchmarks import (  # noqa: E402
    BenchmarkExportError,
    dependency_versions,
    load_benchmark_manifest,
    load_verified_feature_rows,
    numerical_runtime_fingerprint,
    verify_frozen_manifest_contracts,
)
from scripts.export_win_either_half_feature_dataset import (  # noqa: E402
    canonical_json_sha256,
    load_feature_manifest,
)
from scripts.export_win_either_half_research_dataset import (  # noqa: E402
    ResearchExportError,
    load_research_manifest,
    validate_market_safety,
    verify_stage_2_evidence,
)
from scripts.freeze_evidence_baseline import (  # noqa: E402
    BaselineError,
    get_code_state,
    load_baseline,
    verify_revision_relationship,
)


SCHEMA_VERSION = 1
DATASET_NAME = "win-either-half-calibration-v1"
EXPECTED_STAGE_4_MODEL = "logistic_l2_c0.1_v1"
FROZEN_STAGE_4_BENCHMARK_MANIFEST_LOGICAL_SHA256 = (
    "6b8c82be8d2920f155bf9592ea7388ba6689b0cae05995642e348cf199fd2a7d"
)
CALIBRATED_PREDICTION_COLUMNS = (
    "fixture_identity",
    "kickoff_utc",
    "league",
    "season",
    "split",
    "prediction_role",
    "target_name",
    "target_value",
    "base_model_identifier",
    "model_probability",
    "calibration_identifier",
    "calibrated_probability",
)
SUBGROUP_COLUMNS = (
    "target_name",
    "evaluation_role",
    "evaluation_scope",
    "split",
    "dimension",
    "group",
    "support_status",
    "support_reason",
    "row_count",
    "positive_count",
    "negative_count",
    "identity_metrics_json",
    "identity_evaluation_status",
    "identity_evaluation_reason",
    "selected_calibration_metrics_json",
    "selected_calibration_evaluation_status",
    "selected_calibration_evaluation_reason",
    "metric_deltas_json",
    "identity_metric_reasons_json",
    "selected_metric_reasons_json",
)


class CalibrationExportError(RuntimeError):
    """A bounded error for Stage 4B input verification or output handling."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json_bytes(value: object, *, pretty: bool = False) -> bytes:
    options = {"allow_nan": False, "ensure_ascii": False, "sort_keys": True}
    if pretty:
        text = json.dumps(value, indent=2, **options) + "\n"
    else:
        text = json.dumps(value, separators=(",", ":"), **options)
    return text.encode("utf-8")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise CalibrationExportError(f"{label} could not be read: {path}") from error


def _verify_file_identity(content: bytes, identity: Mapping, label: str) -> None:
    if len(content) != identity.get("byte_size"):
        raise CalibrationExportError(f"{label} byte size differs from frozen manifest")
    if _sha256(content) != identity.get("sha256"):
        raise CalibrationExportError(f"{label} SHA-256 differs from frozen manifest")


def verify_stage_4_manifest_contract(
    *,
    baseline: dict,
    current_evidence: dict,
    label_manifest: dict,
    feature_manifest: dict,
    benchmark_manifest: dict,
) -> tuple:
    _, predictor_names = verify_frozen_manifest_contracts(
        baseline=baseline,
        current_evidence=current_evidence,
        label_manifest=label_manifest,
        feature_manifest=feature_manifest,
    )
    if benchmark_manifest.get("dataset_name") != (
        "win-either-half-baseline-benchmarks-v1"
    ):
        raise CalibrationExportError("Unexpected Stage 4A benchmark identity")
    if canonical_json_sha256(benchmark_manifest) != (
        FROZEN_STAGE_4_BENCHMARK_MANIFEST_LOGICAL_SHA256
    ):
        raise CalibrationExportError("Stage 4A benchmark manifest identity drifted")
    if benchmark_manifest.get("stage_2_evidence") != feature_manifest.get(
        "stage_2_evidence"
    ):
        raise CalibrationExportError("Stage 4A Stage 2 ancestry drifted")
    expected_labels = {
        "dataset_name": label_manifest.get("dataset_name"),
        "generator_git_head_sha": label_manifest.get("generator", {}).get(
            "generator_git_head_sha"
        ),
        "label_manifest_logical_sha256": canonical_json_sha256(label_manifest),
    }
    if benchmark_manifest.get("stage_3_labels") != expected_labels:
        raise CalibrationExportError("Stage 4A label-manifest ancestry drifted")
    expected_features = {
        "dataset_name": feature_manifest.get("dataset_name"),
        "feature_csv": {
            key: feature_manifest.get("files", {}).get("features", {}).get(key)
            for key in ("byte_size", "rows", "sha256")
        },
        "feature_manifest_logical_sha256": canonical_json_sha256(feature_manifest),
        "generator_git_head_sha": feature_manifest.get("generator", {}).get(
            "generator_git_head_sha"
        ),
    }
    if benchmark_manifest.get("stage_3_features") != expected_features:
        raise CalibrationExportError("Stage 4A feature-manifest ancestry drifted")
    if tuple(benchmark_manifest.get("feature_columns", ())) != tuple(predictor_names):
        raise CalibrationExportError("Stage 4A feature allowlist drifted")
    if tuple(benchmark_manifest.get("targets", ())) != TARGETS:
        raise CalibrationExportError("Stage 4A target definitions drifted")
    expected_splits = {
        split: {
            "rows": feature_manifest.get("splits", {}).get(split, {}).get("rows"),
            "seasons": list(
                feature_manifest.get("splits", {}).get(split, {}).get("seasons", ())
            ),
        }
        for split in ("train", "validation", "test")
    }
    if benchmark_manifest.get("splits") != expected_splits:
        raise CalibrationExportError("Stage 4A temporal split contract drifted")
    selected = benchmark_manifest.get("selected_models", {})
    if selected != {target: EXPECTED_STAGE_4_MODEL for target in TARGETS}:
        raise CalibrationExportError("Frozen Stage 4A selected models drifted")
    numerical = benchmark_manifest.get("numerical_reproducibility", {})
    if (
        numerical.get("canonical_decimal_places") != CANONICAL_DECIMAL_PLACES
        or numerical.get("thread_limit") != NUMERICAL_THREAD_LIMIT
        or benchmark_manifest.get("random_seeds", {}).get("model_and_diagnostics")
        != DEFAULT_RANDOM_SEED
    ):
        raise CalibrationExportError("Stage 4A numerical policy drifted")
    if benchmark_manifest.get("market_safety") != current_evidence.get(
        "market_safety"
    ):
        raise CalibrationExportError("Stage 4A market safety drifted")
    validate_market_safety(benchmark_manifest)
    selected_model_configurations(benchmark_manifest)
    return tuple(predictor_names), expected_splits


def load_verified_benchmark_summary(
    path: Path,
    benchmark_manifest: Mapping,
) -> tuple:
    content = _read_bytes(path, "Stage 4A benchmark summary")
    _verify_file_identity(
        content,
        benchmark_manifest.get("files", {}).get("benchmark_summary", {}),
        "Stage 4A benchmark summary",
    )
    try:
        summary = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CalibrationExportError(
            "Stage 4A benchmark summary is not valid UTF-8 JSON"
        ) from error
    if summary.get("model_configurations") != benchmark_manifest.get(
        "model_configurations"
    ):
        raise CalibrationExportError("Stage 4A model configurations drifted")
    selected = {
        target: summary.get("targets", {}).get(target, {}).get(
            "selected_model_identifier"
        )
        for target in TARGETS
    }
    if selected != benchmark_manifest.get("selected_models"):
        raise CalibrationExportError("Stage 4A benchmark selections drifted")
    if summary.get("split_counts") != {
        split: benchmark_manifest.get("splits", {}).get(split, {}).get("rows")
        for split in ("train", "validation", "test")
    }:
        raise CalibrationExportError("Stage 4A benchmark split counts drifted")
    if summary.get("numerical_reproducibility", {}).get(
        "canonical_decimal_places"
    ) != CANONICAL_DECIMAL_PLACES:
        raise CalibrationExportError("Stage 4A benchmark precision drifted")
    return summary, {
        "byte_size": len(content),
        "sha256": _sha256(content),
    }


def _parse_probability(value: str) -> float:
    try:
        probability = float(value)
    except (TypeError, ValueError) as error:
        raise CalibrationExportError(
            "Stage 4A prediction probability is not numeric"
        ) from error
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise CalibrationExportError(
            "Stage 4A prediction probability must be finite and in [0, 1]"
        )
    if format(probability, f".{CANONICAL_DECIMAL_PLACES}f") != value:
        raise CalibrationExportError(
            "Stage 4A prediction probability is not canonically serialized"
        )
    return probability


def load_verified_stage_4_predictions(
    path: Path,
    benchmark_manifest: Mapping,
    feature_rows: Sequence[Mapping],
) -> tuple:
    content = _read_bytes(path, "Stage 4A prediction CSV")
    expected = benchmark_manifest.get("files", {}).get("predictions", {})
    _verify_file_identity(content, expected, "Stage 4A prediction CSV")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise CalibrationExportError(
            "Stage 4A prediction CSV is not valid UTF-8"
        ) from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    expected_columns = (
        "fixture_identity",
        "kickoff_utc",
        "target_name",
        "target_value",
        "split",
        "model_identifier",
        "predicted_probability",
    )
    if tuple(reader.fieldnames or ()) != expected_columns:
        raise CalibrationExportError("Stage 4A prediction columns drifted")
    features = {str(row["fixture_identity"]): row for row in feature_rows}
    rows = []
    keys = set()
    counts = Counter()
    for raw in reader:
        fixture_identity = str(raw.get("fixture_identity") or "")
        target = str(raw.get("target_name") or "")
        split = str(raw.get("split") or "")
        key = (fixture_identity, target)
        if key in keys:
            raise CalibrationExportError("Duplicate Stage 4A prediction row")
        keys.add(key)
        feature = features.get(fixture_identity)
        if feature is None or target not in TARGETS or split != feature["split"]:
            raise CalibrationExportError("Stage 4A prediction identity drifted")
        if raw.get("model_identifier") != EXPECTED_STAGE_4_MODEL:
            raise CalibrationExportError("Stage 4A prediction model drifted")
        if raw.get("target_value") not in ("0", "1") or int(
            raw["target_value"]
        ) != feature[target]:
            raise CalibrationExportError("Stage 4A prediction target drifted")
        if raw.get("kickoff_utc") != feature["kickoff_utc"]:
            raise CalibrationExportError("Stage 4A prediction kickoff drifted")
        rows.append(
            {
                "fixture_identity": fixture_identity,
                "kickoff_utc": raw["kickoff_utc"],
                "model_identifier": raw["model_identifier"],
                "predicted_probability": _parse_probability(
                    raw["predicted_probability"]
                ),
                "split": split,
                "target_name": target,
                "target_value": int(raw["target_value"]),
            }
        )
        counts[(target, split)] += 1
    if len(rows) != expected.get("rows") or len(rows) != len(feature_rows) * 2:
        raise CalibrationExportError("Stage 4A prediction row count drifted")
    for target in TARGETS:
        for split in ("TRAIN", "VALIDATION", "TEST"):
            expected_count = sum(1 for row in feature_rows if row["split"] == split)
            if counts[(target, split)] != expected_count:
                raise CalibrationExportError(
                    f"Stage 4A {target} {split} prediction count drifted"
                )
    rows.sort(key=lambda row: (row["target_name"], row["split"], row["fixture_identity"]))
    return tuple(rows), {
        "byte_size": len(content),
        "rows": len(rows),
        "sha256": _sha256(content),
    }


def selected_model_configurations(
    benchmark_manifest: Mapping,
) -> dict:
    configurations = {
        value.get("identifier"): value
        for value in benchmark_manifest.get("model_configurations", ())
    }
    result = {}
    for target in TARGETS:
        identifier = benchmark_manifest.get("selected_models", {}).get(target)
        raw = configurations.get(identifier)
        if raw != FROZEN_STAGE_4_BASE_CONFIGURATION.to_dict():
            raise CalibrationExportError(
                f"Frozen Stage 4A base configuration drifted: {target}"
            )
        result[target] = ModelConfiguration(
            identifier=identifier,
            family=raw["family"],
            complexity_rank=int(raw["complexity_rank"]),
            parameters=tuple(sorted(raw.get("parameters", {}).items())),
            preprocessing=raw["preprocessing"],
        )
    return result


def render_calibration_summary(summary: Mapping) -> bytes:
    return _canonical_json_bytes(summary, pretty=True)


def render_calibrated_predictions(rows: Sequence[Mapping]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=CALIBRATED_PREDICTION_COLUMNS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        rendered = dict(row)
        for name in ("model_probability", "calibrated_probability"):
            rendered[name] = format(
                float(rendered[name]), f".{CANONICAL_DECIMAL_PLACES}f"
            )
        writer.writerow(rendered)
    return stream.getvalue().encode("utf-8")


def render_subgroups(rows: Sequence[Mapping]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=SUBGROUP_COLUMNS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        identity = row["identity"]
        selected = row["selected_calibration"]
        writer.writerow(
            {
                "dimension": row["dimension"],
                "evaluation_role": row["evaluation_role"],
                "evaluation_scope": row["evaluation_scope"],
                "group": row["group"],
                "identity_evaluation_reason": identity["evaluation_reason"] or "",
                "identity_evaluation_status": identity["evaluation_status"],
                "identity_metric_reasons_json": _canonical_json_bytes(
                    identity["metric_reasons"]
                ).decode("utf-8"),
                "identity_metrics_json": _canonical_json_bytes(
                    identity["metrics"]
                ).decode("utf-8"),
                "metric_deltas_json": _canonical_json_bytes(
                    row["metric_deltas"]
                ).decode("utf-8"),
                "negative_count": row["negative_count"],
                "positive_count": row["positive_count"],
                "row_count": row["row_count"],
                "selected_calibration_metrics_json": _canonical_json_bytes(
                    selected["metrics"]
                ).decode("utf-8"),
                "selected_calibration_evaluation_reason": (
                    selected["evaluation_reason"] or ""
                ),
                "selected_calibration_evaluation_status": selected[
                    "evaluation_status"
                ],
                "selected_metric_reasons_json": _canonical_json_bytes(
                    selected["metric_reasons"]
                ).decode("utf-8"),
                "support_reason": row["support_reason"] or "",
                "support_status": row["support_status"],
                "split": row["split"],
                "target_name": row["target_name"],
            }
        )
    return stream.getvalue().encode("utf-8")


def _file_identity(content: bytes, relative_name: str, rows: int | None = None) -> dict:
    value = {
        "byte_size": len(content),
        "relative_name": relative_name,
        "sha256": _sha256(content),
    }
    if rows is not None:
        value["rows"] = rows
    return value


def build_calibration_manifest(
    *,
    calibration: Mapping,
    calibration_bytes: bytes,
    calibration_name: str,
    prediction_bytes: bytes,
    prediction_name: str,
    prediction_rows: int,
    subgroup_bytes: bytes,
    subgroup_name: str,
    subgroup_rows: int,
    baseline: Mapping,
    label_manifest: Mapping,
    feature_manifest: Mapping,
    benchmark_manifest: Mapping,
    feature_identity: Mapping,
    benchmark_identity: Mapping,
    stage_4_prediction_identity: Mapping,
    generator_code_state: Mapping,
    numerical_runtime: Mapping,
    generated_at_utc: Optional[str] = None,
) -> dict:
    return {
        "calibration_configurations": calibration["calibration_configurations"],
        "dataset_name": DATASET_NAME,
        "dependencies": dependency_versions(),
        "files": {
            "calibrated_predictions": _file_identity(
                prediction_bytes, prediction_name, prediction_rows
            ),
            "calibration_summary": _file_identity(
                calibration_bytes, calibration_name
            ),
            "subgroups": _file_identity(
                subgroup_bytes, subgroup_name, subgroup_rows
            ),
        },
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "generator": {
            "generator_git_head_sha": generator_code_state.get(
                "evidence_git_head_sha"
            ),
            "tracked_worktree_clean": generator_code_state.get(
                "tracked_worktree_clean"
            ),
        },
        "input_files": {
            "feature_csv": dict(feature_identity),
            "stage_4_benchmark_summary": dict(benchmark_identity),
            "stage_4_predictions": dict(stage_4_prediction_identity),
        },
        "market_safety": dict(benchmark_manifest.get("market_safety", {})),
        "numerical_reproducibility": {
            "canonical_decimal_places": CANONICAL_DECIMAL_PLACES,
            "random_seed": DEFAULT_RANDOM_SEED,
            "runtime": dict(numerical_runtime),
            "thread_limit": NUMERICAL_THREAD_LIMIT,
        },
        "schema_version": SCHEMA_VERSION,
        "selected_calibrations": {
            target: calibration["targets"][target][
                "selected_calibration_identifier"
            ]
            for target in TARGETS
        },
        "selection_rule": CALIBRATION_SELECTION_RULE,
        "stage_2_evidence": dict(benchmark_manifest.get("stage_2_evidence", {})),
        "stage_3_features": {
            "dataset_name": feature_manifest.get("dataset_name"),
            "feature_manifest_logical_sha256": canonical_json_sha256(
                feature_manifest
            ),
            "generator_git_head_sha": feature_manifest.get("generator", {}).get(
                "generator_git_head_sha"
            ),
        },
        "stage_3_labels": {
            "dataset_name": label_manifest.get("dataset_name"),
            "generator_git_head_sha": label_manifest.get("generator", {}).get(
                "generator_git_head_sha"
            ),
            "label_manifest_logical_sha256": canonical_json_sha256(label_manifest),
        },
        "stage_4_benchmarks": {
            "benchmark_manifest_logical_sha256": canonical_json_sha256(
                benchmark_manifest
            ),
            "dataset_name": benchmark_manifest.get("dataset_name"),
            "generator_git_head_sha": benchmark_manifest.get("generator", {}).get(
                "generator_git_head_sha"
            ),
            "selected_models": dict(
                benchmark_manifest.get("selected_models", {})
            ),
        },
        "subgroup_policy": {
            "evaluation_role_scopes": dict(
                calibration["evaluation_role_scopes"]
            ),
            "minimum_supported_rows": calibration["subgroup_minimum_rows"],
            "model_probability_bands": list(
                calibration["model_probability_bands"]
            ),
        },
        "targets": list(TARGETS),
        "temporal_splits": dict(benchmark_manifest.get("splits", {})),
    }


def compare_calibration_manifests(
    stored: Mapping,
    current: Mapping,
    *,
    allow_generator_revision_difference: bool = False,
) -> list:
    differences = []
    stored_numerical = dict(stored.get("numerical_reproducibility", {}))
    current_numerical = dict(current.get("numerical_reproducibility", {}))
    stored_runtime = stored_numerical.pop("runtime", None)
    current_runtime = current_numerical.pop("runtime", None)
    if stored_numerical != current_numerical:
        differences.append("canonical numerical policy differs")
    if stored_runtime != current_runtime:
        differences.append("numerical runtime contract differs")
    for key, label in (
        ("schema_version", "manifest schema version differs"),
        ("dataset_name", "dataset name differs"),
        ("stage_2_evidence", "Stage 2 evidence identity differs"),
        ("stage_3_labels", "Stage 3 label identity differs"),
        ("stage_3_features", "Stage 3 feature identity differs"),
        ("stage_4_benchmarks", "Stage 4A benchmark identity differs"),
        ("input_files", "frozen input file identities differ"),
        ("targets", "target definitions differ"),
        ("temporal_splits", "temporal split contract differs"),
        ("calibration_configurations", "calibration configurations differ"),
        ("selection_rule", "calibration selection rule differs"),
        ("selected_calibrations", "selected calibrations differ"),
        ("subgroup_policy", "subgroup policy differs"),
        ("files", "calibration output identities differ"),
        ("dependencies", "dependency versions differ"),
        ("market_safety", "market safety differs"),
    ):
        if stored.get(key) != current.get(key):
            differences.append(label)
    stored_generator = stored.get("generator", {})
    current_generator = current.get("generator", {})
    if (
        not allow_generator_revision_difference
        and stored_generator.get("generator_git_head_sha")
        != current_generator.get("generator_git_head_sha")
    ):
        differences.append("generator Git revision differs")
    if stored_generator.get("tracked_worktree_clean") != current_generator.get(
        "tracked_worktree_clean"
    ):
        differences.append("tracked worktree cleanliness differs")
    return differences


def load_calibration_manifest(path: Path) -> dict:
    content = _read_bytes(path, "Calibration manifest")
    try:
        manifest = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CalibrationExportError(
            "Calibration manifest is not valid UTF-8 JSON"
        ) from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise CalibrationExportError("Unsupported calibration manifest contract")
    return manifest


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_calibration_outputs(
    *,
    calibration_path: Path,
    prediction_path: Path,
    subgroup_path: Path,
    manifest_path: Path,
    calibration_bytes: bytes,
    prediction_bytes: bytes,
    subgroup_bytes: bytes,
    manifest: Mapping,
    force: bool = False,
) -> None:
    paths = (calibration_path, prediction_path, subgroup_path, manifest_path)
    if len({Path(os.path.abspath(path)) for path in paths}) != len(paths):
        raise CalibrationExportError("Calibration output paths must be distinct")
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise CalibrationExportError(
            "Output already exists; use --force to replace: "
            + ", ".join(str(path) for path in existing)
        )
    _atomic_write(calibration_path, calibration_bytes)
    _atomic_write(prediction_path, prediction_bytes)
    _atomic_write(subgroup_path, subgroup_bytes)
    _atomic_write(manifest_path, _canonical_json_bytes(manifest, pretty=True))


def _non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate leakage-safe Win Either Half calibration and stability."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest-output", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument(
        "--calibration-output",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/calibration-v1.json"
        ),
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/calibrated-predictions-v1.csv"
        ),
    )
    parser.add_argument(
        "--subgroups-output",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/calibration-subgroups-v1.csv"
        ),
    )
    parser.add_argument("--database", type=Path, default=Path("database/athena.db"))
    parser.add_argument(
        "--cache-directory", type=Path, default=Path(".cache/football-data-uk")
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path(
            "artifacts/evidence-baselines/half-time-ready-for-research.json"
        ),
    )
    parser.add_argument(
        "--label-manifest",
        type=Path,
        default=Path(
            "artifacts/research-manifests/win-either-half-labels-v1.json"
        ),
    )
    parser.add_argument(
        "--feature-manifest",
        type=Path,
        default=Path(
            "artifacts/research-manifests/win-either-half-features-v1.json"
        ),
    )
    parser.add_argument(
        "--benchmark-manifest",
        type=Path,
        default=Path(
            "artifacts/research-manifests/win-either-half-benchmarks-v1.json"
        ),
    )
    parser.add_argument(
        "--feature-csv",
        type=Path,
        default=Path(".cache/athena-research/win-either-half/features-v1.csv"),
    )
    parser.add_argument(
        "--benchmark-summary",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/benchmarks-v1.json"
        ),
    )
    parser.add_argument(
        "--stage-4-predictions",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/predictions-v1.csv"
        ),
    )
    parser.add_argument("--expect-feature-rows", type=_non_negative_integer)
    parser.add_argument("--expect-stage-4-prediction-rows", type=_non_negative_integer)
    parser.add_argument("--force", action="store_true")
    return parser


def main(
    argv: Optional[Iterable[str]] = None,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check is not None and args.force:
        parser.error("--force is valid only with --manifest-output")
    try:
        baseline = load_baseline(args.baseline)
        current_evidence = verify_stage_2_evidence(
            baseline,
            database_path=args.database,
            cache_directory=args.cache_directory,
            repository_root=repository_root,
        )
        label_manifest = load_research_manifest(args.label_manifest)
        feature_manifest = load_feature_manifest(args.feature_manifest)
        benchmark_manifest = load_benchmark_manifest(args.benchmark_manifest)
        predictor_names, frozen_splits = verify_stage_4_manifest_contract(
            baseline=baseline,
            current_evidence=current_evidence,
            label_manifest=label_manifest,
            feature_manifest=feature_manifest,
            benchmark_manifest=benchmark_manifest,
        )
        rows, feature_identity = load_verified_feature_rows(
            args.feature_csv,
            feature_manifest,
            predictor_names,
            expected_total_rows=args.expect_feature_rows,
            expected_split_counts={
                split.upper(): frozen_splits[split]["rows"]
                for split in ("train", "validation", "test")
            },
        )
        _, benchmark_identity = load_verified_benchmark_summary(
            args.benchmark_summary, benchmark_manifest
        )
        stage_4_predictions, prediction_input_identity = (
            load_verified_stage_4_predictions(
                args.stage_4_predictions, benchmark_manifest, rows
            )
        )
        if (
            args.expect_stage_4_prediction_rows is not None
            and len(stage_4_predictions) != args.expect_stage_4_prediction_rows
        ):
            raise CalibrationExportError(
                "Stage 4A prediction row expectation mismatch"
            )
        code_state = get_code_state(repository_root)
        if not code_state.get("tracked_worktree_clean"):
            raise CalibrationExportError("Tracked worktree is dirty")
        result = run_calibration_research(
            rows,
            predictor_names,
            selected_model_configurations=selected_model_configurations(
                benchmark_manifest
            ),
            frozen_predictions=stage_4_predictions,
            calibration_configurations=default_calibration_configurations(),
        )
        calibration_bytes = render_calibration_summary(result["calibration"])
        calibrated_prediction_bytes = render_calibrated_predictions(
            result["prediction_rows"]
        )
        subgroup_bytes = render_subgroups(result["subgroup_rows"])
        stored_manifest = (
            load_calibration_manifest(args.check) if args.check is not None else None
        )
        names = {
            "calibration": (
                stored_manifest["files"]["calibration_summary"]["relative_name"]
                if stored_manifest is not None
                else args.calibration_output.name
            ),
            "predictions": (
                stored_manifest["files"]["calibrated_predictions"]["relative_name"]
                if stored_manifest is not None
                else args.predictions_output.name
            ),
            "subgroups": (
                stored_manifest["files"]["subgroups"]["relative_name"]
                if stored_manifest is not None
                else args.subgroups_output.name
            ),
        }
        current_manifest = build_calibration_manifest(
            calibration=result["calibration"],
            calibration_bytes=calibration_bytes,
            calibration_name=names["calibration"],
            prediction_bytes=calibrated_prediction_bytes,
            prediction_name=names["predictions"],
            prediction_rows=len(result["prediction_rows"]),
            subgroup_bytes=subgroup_bytes,
            subgroup_name=names["subgroups"],
            subgroup_rows=len(result["subgroup_rows"]),
            baseline=baseline,
            label_manifest=label_manifest,
            feature_manifest=feature_manifest,
            benchmark_manifest=benchmark_manifest,
            feature_identity=feature_identity,
            benchmark_identity=benchmark_identity,
            stage_4_prediction_identity=prediction_input_identity,
            generator_code_state=code_state,
            numerical_runtime=numerical_runtime_fingerprint(),
        )
        validate_market_safety(current_manifest)
        if stored_manifest is not None:
            stored_generator = stored_manifest.get("generator", {})
            revision = verify_revision_relationship(
                {
                    "evidence_git_head_sha": stored_generator.get(
                        "generator_git_head_sha"
                    ),
                    "tracked_worktree_clean": stored_generator.get(
                        "tracked_worktree_clean"
                    ),
                },
                code_state,
                check_path=args.check,
                repository_root=repository_root,
            )
            differences = compare_calibration_manifests(
                stored_manifest,
                current_manifest,
                allow_generator_revision_difference=(
                    revision["mode"] == "artifact_only_descendant"
                ),
            )
            if differences:
                print("Calibration manifest verification failed:", file=sys.stderr)
                for difference in differences:
                    print(f"  - {difference}", file=sys.stderr)
                return 1
            print(f"Calibration manifest verified: {args.check}")
            if revision["mode"] == "artifact_only_descendant":
                print("Revision verification: " + revision["message"])
            return 0
        write_calibration_outputs(
            calibration_path=args.calibration_output,
            prediction_path=args.predictions_output,
            subgroup_path=args.subgroups_output,
            manifest_path=args.manifest_output,
            calibration_bytes=calibration_bytes,
            prediction_bytes=calibrated_prediction_bytes,
            subgroup_bytes=subgroup_bytes,
            manifest=current_manifest,
            force=args.force,
        )
        print(f"Calibration summary written: {args.calibration_output}")
        print(f"Calibrated predictions written: {args.predictions_output}")
        print(f"Subgroup stability written: {args.subgroups_output}")
        print(f"Calibration manifest written: {args.manifest_output}")
        return 0
    except (
        BaselineError,
        BenchmarkExportError,
        CalibrationError,
        CalibrationExportError,
        FileNotFoundError,
        OSError,
        ResearchExportError,
        sqlite3.Error,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
