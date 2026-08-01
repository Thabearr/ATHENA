#!/usr/bin/env python3
"""Generate deterministic Stage 4A Win Either Half baseline benchmarks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from threadpoolctl import threadpool_info, threadpool_limits

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.win_either_half_benchmarks import (  # noqa: E402
    BenchmarkError,
    CANONICAL_DECIMAL_PLACES,
    DEFAULT_RANDOM_SEED,
    NUMERICAL_THREAD_LIMIT,
    SELECTION_RULE,
    SPLITS,
    TARGETS,
    default_model_configurations,
    pre_match_feature_names,
    run_baseline_benchmarks,
    validate_predictor_columns,
)
from scripts.export_win_either_half_feature_dataset import (  # noqa: E402
    canonical_json_sha256,
    load_feature_manifest,
    validate_label_manifest_contract,
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
DATASET_NAME = "win-either-half-baseline-benchmarks-v1"
PREDICTION_COLUMNS = (
    "fixture_identity",
    "kickoff_utc",
    "target_name",
    "target_value",
    "split",
    "model_identifier",
    "predicted_probability",
)


class BenchmarkExportError(RuntimeError):
    """A bounded user-facing frozen-input or export failure."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json_bytes(value: object, *, pretty: bool = False) -> bytes:
    options = {
        "allow_nan": False,
        "ensure_ascii": False,
        "sort_keys": True,
    }
    if pretty:
        text = json.dumps(value, indent=2, **options) + "\n"
    else:
        text = json.dumps(value, separators=(",", ":"), **options)
    return text.encode("utf-8")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise BenchmarkExportError(f"{label} could not be read: {path}") from error


def _expected_stage_2_identity(baseline: Mapping) -> dict:
    return {
        "baseline_name": baseline.get("baseline_name"),
        "cache_manifest_sha256": baseline.get(
            "football_data_uk_cache", {}
        ).get("manifest_sha256"),
        "evidence_git_head_sha": baseline.get("code", {}).get(
            "evidence_git_head_sha"
        ),
        "logical_evidence_sha256": baseline.get("database", {}).get(
            "logical_evidence_sha256"
        ),
        "schema_sha256": baseline.get("database", {}).get("schema_sha256"),
    }


def verify_frozen_manifest_contracts(
    *,
    baseline: dict,
    current_evidence: dict,
    label_manifest: dict,
    feature_manifest: dict,
) -> tuple:
    split_config = validate_label_manifest_contract(
        label_manifest,
        baseline=baseline,
        current_evidence=current_evidence,
    )
    if feature_manifest.get("dataset_name") != "win-either-half-features-v1":
        raise BenchmarkExportError("Unexpected Stage 3 feature dataset identity")
    if feature_manifest.get("stage_2_evidence") != _expected_stage_2_identity(
        baseline
    ):
        raise BenchmarkExportError("Stage 3 feature manifest Stage 2 ancestry drifted")
    expected_label_identity = {
        "dataset_name": label_manifest.get("dataset_name"),
        "generator_git_head_sha": label_manifest.get("generator", {}).get(
            "generator_git_head_sha"
        ),
        "label_manifest_logical_sha256": canonical_json_sha256(label_manifest),
        "labels_csv": dict(label_manifest.get("files", {}).get("labels", {})),
    }
    expected_label_identity["labels_csv"].pop("relative_name", None)
    if feature_manifest.get("stage_3_labels") != expected_label_identity:
        raise BenchmarkExportError("Stage 3 label-manifest ancestry drifted")
    if feature_manifest.get("market_safety") != current_evidence.get(
        "market_safety"
    ):
        raise BenchmarkExportError("Stage 3 feature market safety drifted")
    validate_market_safety(feature_manifest)
    expected_splits = {
        key: {
            "rows": label_manifest.get("splits", {}).get(key, {}).get("rows"),
            "seasons": list(
                label_manifest.get("splits", {}).get(key, {}).get("seasons", ())
            ),
        }
        for key in ("train", "validation", "test")
    }
    if feature_manifest.get("splits") != expected_splits:
        raise BenchmarkExportError("Stage 3 feature split ancestry drifted")
    schema = feature_manifest.get("feature_schema")
    if not isinstance(schema, list):
        raise BenchmarkExportError("Stage 3 feature schema is missing")
    predictor_names = pre_match_feature_names(schema)
    validate_predictor_columns(schema, predictor_names)
    return split_config, predictor_names


def _parse_binary(row: Mapping, name: str) -> int:
    raw = row.get(name)
    if raw not in ("0", "1"):
        raise BenchmarkExportError(f"Feature CSV target {name} must be 0 or 1")
    return int(raw)


def _parse_predictor(row: Mapping, name: str):
    raw = row.get(name)
    if raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise BenchmarkExportError(
            f"Feature CSV predictor {name} is not numeric"
        ) from error
    if not math.isfinite(value):
        raise BenchmarkExportError(
            f"Feature CSV predictor {name} must be finite when present"
        )
    return value


def load_verified_feature_rows(
    feature_path: Path,
    feature_manifest: Mapping,
    predictor_names: Sequence[str],
    *,
    expected_total_rows: Optional[int] = None,
    expected_split_counts: Optional[Mapping[str, int]] = None,
) -> tuple:
    content = _read_bytes(feature_path, "Feature CSV")
    expected_file = feature_manifest.get("files", {}).get("features", {})
    if len(content) != expected_file.get("byte_size"):
        raise BenchmarkExportError("Feature CSV byte size does not match manifest")
    if _sha256(content) != expected_file.get("sha256"):
        raise BenchmarkExportError("Feature CSV SHA-256 does not match manifest")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise BenchmarkExportError("Feature CSV is not valid UTF-8") from error
    schema = feature_manifest.get("feature_schema", ())
    expected_columns = tuple(entry.get("name") for entry in schema)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != expected_columns:
        raise BenchmarkExportError("Feature CSV columns differ from frozen schema")
    rows = []
    split_counts = Counter()
    season_splits = {
        season: split.upper()
        for split, contract in feature_manifest.get("splits", {}).items()
        for season in contract.get("seasons", ())
    }
    for raw_row in reader:
        split = str(raw_row.get("split") or "")
        season = str(raw_row.get("season") or "")
        if split not in SPLITS or season_splits.get(season) != split:
            raise BenchmarkExportError(
                "Feature CSV season/split assignment differs from manifest"
            )
        fixture_identity = str(raw_row.get("fixture_identity") or "").strip()
        kickoff = str(raw_row.get("kickoff_utc") or "").strip()
        if not fixture_identity or not kickoff:
            raise BenchmarkExportError("Feature CSV audit identity is incomplete")
        row = {
            "away_win_either_half_yes": _parse_binary(
                raw_row, "away_win_either_half_yes"
            ),
            "both_teams_won_a_half": _parse_binary(
                raw_row, "both_teams_won_a_half"
            ),
            "fixture_identity": fixture_identity,
            "home_win_either_half_yes": _parse_binary(
                raw_row, "home_win_either_half_yes"
            ),
            "kickoff_utc": kickoff,
            "league": str(raw_row.get("league") or "").strip(),
            "season": season,
            "split": split,
        }
        for name in predictor_names:
            row[name] = _parse_predictor(raw_row, name)
        rows.append(row)
        split_counts[split] += 1
    manifest_rows = expected_file.get("rows")
    if len(rows) != manifest_rows:
        raise BenchmarkExportError("Feature CSV row count does not match manifest")
    if expected_total_rows is not None and len(rows) != expected_total_rows:
        raise BenchmarkExportError("Feature CSV total-row expectation mismatch")
    manifest_split_counts = {
        split.upper(): feature_manifest.get("splits", {})
        .get(split, {})
        .get("rows")
        for split in ("train", "validation", "test")
    }
    if dict(split_counts) != manifest_split_counts:
        raise BenchmarkExportError("Feature CSV split counts do not match manifest")
    if expected_split_counts is not None:
        for split in SPLITS:
            if split_counts[split] != expected_split_counts.get(split):
                raise BenchmarkExportError(
                    f"Feature CSV {split} expectation mismatch"
                )
    return tuple(rows), {
        "byte_size": len(content),
        "rows": len(rows),
        "sha256": _sha256(content),
    }


def render_benchmark_summary(benchmark: Mapping) -> bytes:
    return _canonical_json_bytes(benchmark, pretty=True)


def render_prediction_csv(rows: Sequence[Mapping]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=PREDICTION_COLUMNS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        rendered = dict(row)
        rendered["predicted_probability"] = format(
            float(rendered["predicted_probability"]),
            f".{CANONICAL_DECIMAL_PLACES}f",
        )
        writer.writerow(rendered)
    return stream.getvalue().encode("utf-8")


def dependency_versions() -> dict:
    versions = {"python": platform.python_version()}
    for distribution, key in (
        ("numpy", "numpy"),
        ("scikit-learn", "scikit_learn"),
        ("scipy", "scipy"),
        ("threadpoolctl", "threadpoolctl"),
    ):
        try:
            versions[key] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as error:
            raise BenchmarkExportError(
                f"Required dependency version unavailable: {distribution}"
            ) from error
    return versions


def numerical_runtime_fingerprint() -> dict:
    """Return stable runtime details that bound numerical artifact verification."""
    normalized_libraries = []
    with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
        loaded_libraries = threadpool_info()
    for library in loaded_libraries:
        normalized_libraries.append(
            {
                "architecture": library.get("architecture"),
                "internal_api": library.get("internal_api"),
                "num_threads": library.get("num_threads"),
                "prefix": library.get("prefix"),
                "threading_layer": library.get("threading_layer"),
                "user_api": library.get("user_api"),
                "version": library.get("version"),
            }
        )
    normalized_libraries.sort(
        key=lambda value: _canonical_json_bytes(value)
    )
    versions = dependency_versions()
    return {
        "libraries": normalized_libraries,
        "machine_architecture": platform.machine(),
        "numpy_version": versions["numpy"],
        "platform_system": platform.system(),
        "python_implementation": platform.python_implementation(),
        "python_version": versions["python"],
        "scikit_learn_version": versions["scikit_learn"],
        "scipy_version": versions["scipy"],
        "thread_limit": NUMERICAL_THREAD_LIMIT,
        "threadpoolctl_version": versions["threadpoolctl"],
    }


def build_benchmark_manifest(
    *,
    benchmark: Mapping,
    benchmark_bytes: bytes,
    benchmark_relative_name: str,
    prediction_bytes: bytes,
    prediction_relative_name: str,
    prediction_rows: int,
    baseline: Mapping,
    label_manifest: Mapping,
    feature_manifest: Mapping,
    feature_csv_identity: Mapping,
    predictor_names: Sequence[str],
    generator_code_state: Mapping,
    dependencies: Mapping,
    numerical_runtime: Mapping,
    generated_at_utc: Optional[str] = None,
) -> dict:
    selected_models = {
        target: benchmark["targets"][target]["selected_model_identifier"]
        for target in TARGETS
    }
    return {
        "dataset_name": DATASET_NAME,
        "dependencies": dict(dependencies),
        "feature_columns": list(predictor_names),
        "files": {
            "benchmark_summary": {
                "byte_size": len(benchmark_bytes),
                "relative_name": benchmark_relative_name,
                "sha256": _sha256(benchmark_bytes),
            },
            "predictions": {
                "byte_size": len(prediction_bytes),
                "relative_name": prediction_relative_name,
                "rows": prediction_rows,
                "sha256": _sha256(prediction_bytes),
            },
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
        "market_safety": dict(feature_manifest.get("market_safety", {})),
        "model_configurations": benchmark["model_configurations"],
        "numerical_reproducibility": {
            **dict(benchmark["numerical_reproducibility"]),
            "runtime": dict(numerical_runtime),
        },
        "preprocessing": {
            "fit_split": benchmark["preprocessing"]["fit_split"],
            "imputation": benchmark["preprocessing"]["imputation"],
            "scaling": benchmark["preprocessing"]["scaling"],
        },
        "random_seeds": {"model_and_diagnostics": benchmark["random_seed"]},
        "schema_version": SCHEMA_VERSION,
        "selected_models": selected_models,
        "selection_rule": SELECTION_RULE,
        "splits": {
            split: {
                "rows": feature_manifest.get("splits", {})
                .get(split, {})
                .get("rows"),
                "seasons": list(
                    feature_manifest.get("splits", {})
                    .get(split, {})
                    .get("seasons", ())
                ),
            }
            for split in ("train", "validation", "test")
        },
        "stage_2_evidence": dict(feature_manifest.get("stage_2_evidence", {})),
        "stage_3_features": {
            "dataset_name": feature_manifest.get("dataset_name"),
            "feature_csv": dict(feature_csv_identity),
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
            "label_manifest_logical_sha256": canonical_json_sha256(
                label_manifest
            ),
        },
        "targets": list(TARGETS),
    }


def compare_benchmark_manifests(
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
        differences.append("canonical numerical precision or thread policy differs")
    if stored_runtime != current_runtime:
        differences.append("numerical runtime contract differs")
    for key, label in (
        ("schema_version", "manifest schema version differs"),
        ("dataset_name", "dataset name differs"),
        ("stage_2_evidence", "Stage 2 evidence identity differs"),
        ("stage_3_labels", "Stage 3 label identity differs"),
        ("stage_3_features", "Stage 3 feature identity differs"),
        ("feature_columns", "predictor allowlist differs"),
        ("targets", "research targets differ"),
        ("splits", "frozen split contract differs"),
        ("model_configurations", "model configurations differ"),
        ("random_seeds", "random seeds differ"),
        ("preprocessing", "preprocessing configuration differs"),
        ("selection_rule", "validation selection rule differs"),
        ("selected_models", "selected models differ"),
        ("files", "benchmark output identities differ"),
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


def load_benchmark_manifest(path: Path) -> dict:
    content = _read_bytes(path, "Benchmark manifest")
    try:
        manifest = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BenchmarkExportError(
            "Benchmark manifest is not valid UTF-8 JSON"
        ) from error
    if not isinstance(manifest, dict) or manifest.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        raise BenchmarkExportError("Unsupported benchmark manifest contract")
    for key in ("benchmark_summary", "predictions"):
        relative_name = manifest.get("files", {}).get(key, {}).get(
            "relative_name"
        )
        if (
            not isinstance(relative_name, str)
            or not relative_name
            or Path(relative_name).is_absolute()
            or Path(relative_name).name != relative_name
        ):
            raise BenchmarkExportError(
                f"Benchmark manifest {key} relative_name must be a plain file name"
            )
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


def write_benchmark_outputs(
    *,
    benchmark_path: Path,
    prediction_path: Path,
    manifest_path: Path,
    benchmark_bytes: bytes,
    prediction_bytes: bytes,
    manifest: Mapping,
    force: bool = False,
) -> None:
    paths = (benchmark_path, prediction_path, manifest_path)
    if len({Path(os.path.abspath(path)) for path in paths}) != len(paths):
        raise BenchmarkExportError("Benchmark output paths must be distinct")
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise BenchmarkExportError(
            "Output already exists; use --force to replace: "
            + ", ".join(str(path) for path in existing)
        )
    _atomic_write(benchmark_path, benchmark_bytes)
    _atomic_write(prediction_path, prediction_bytes)
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
        description=(
            "Benchmark deterministic leakage-safe Win Either Half research baselines."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest-output", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--benchmark-output", type=Path)
    parser.add_argument("--predictions-output", type=Path)
    parser.add_argument("--database", type=Path, default=Path("database/athena.db"))
    parser.add_argument(
        "--cache-directory",
        type=Path,
        default=Path(".cache/football-data-uk"),
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
        "--feature-csv",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/features-v1.csv"
        ),
    )
    parser.add_argument("--expect-total-rows", type=_non_negative_integer)
    parser.add_argument("--expect-train-rows", type=_non_negative_integer)
    parser.add_argument("--expect-validation-rows", type=_non_negative_integer)
    parser.add_argument("--expect-test-rows", type=_non_negative_integer)
    parser.add_argument("--random-seed", type=_non_negative_integer, default=DEFAULT_RANDOM_SEED)
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
    if args.manifest_output is not None and (
        args.benchmark_output is None or args.predictions_output is None
    ):
        parser.error(
            "--benchmark-output and --predictions-output are required for generation"
        )
    if args.check is not None and (
        args.benchmark_output is not None or args.predictions_output is not None
    ):
        parser.error("Output paths are valid only during generation")
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
        _, predictor_names = verify_frozen_manifest_contracts(
            baseline=baseline,
            current_evidence=current_evidence,
            label_manifest=label_manifest,
            feature_manifest=feature_manifest,
        )
        expected_split_counts = None
        supplied_split_expectations = (
            args.expect_train_rows,
            args.expect_validation_rows,
            args.expect_test_rows,
        )
        if any(value is not None for value in supplied_split_expectations):
            if any(value is None for value in supplied_split_expectations):
                raise BenchmarkExportError(
                    "All three split expectations must be supplied together"
                )
            expected_split_counts = {
                "TRAIN": args.expect_train_rows,
                "VALIDATION": args.expect_validation_rows,
                "TEST": args.expect_test_rows,
            }
        rows, feature_csv_identity = load_verified_feature_rows(
            args.feature_csv,
            feature_manifest,
            predictor_names,
            expected_total_rows=args.expect_total_rows,
            expected_split_counts=expected_split_counts,
        )
        code_state = get_code_state(repository_root)
        if not code_state.get("tracked_worktree_clean"):
            raise BenchmarkExportError("Tracked worktree is dirty")
        frozen_split_counts = {
            split.upper(): feature_manifest.get("splits", {})
            .get(split, {})
            .get("rows")
            for split in ("train", "validation", "test")
        }
        result = run_baseline_benchmarks(
            rows,
            predictor_names,
            model_configurations=default_model_configurations(args.random_seed),
            random_seed=args.random_seed,
            expected_split_counts=frozen_split_counts,
        )
        benchmark = result["benchmark"]
        benchmark_bytes = render_benchmark_summary(benchmark)
        prediction_bytes = render_prediction_csv(result["prediction_rows"])
        stored_manifest = (
            load_benchmark_manifest(args.check) if args.check is not None else None
        )
        benchmark_name = (
            stored_manifest["files"]["benchmark_summary"]["relative_name"]
            if stored_manifest is not None
            else args.benchmark_output.name
        )
        prediction_name = (
            stored_manifest["files"]["predictions"]["relative_name"]
            if stored_manifest is not None
            else args.predictions_output.name
        )
        current_manifest = build_benchmark_manifest(
            benchmark=benchmark,
            benchmark_bytes=benchmark_bytes,
            benchmark_relative_name=benchmark_name,
            prediction_bytes=prediction_bytes,
            prediction_relative_name=prediction_name,
            prediction_rows=len(result["prediction_rows"]),
            baseline=baseline,
            label_manifest=label_manifest,
            feature_manifest=feature_manifest,
            feature_csv_identity=feature_csv_identity,
            predictor_names=predictor_names,
            generator_code_state=code_state,
            dependencies=dependency_versions(),
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
            differences = compare_benchmark_manifests(
                stored_manifest,
                current_manifest,
                allow_generator_revision_difference=(
                    revision["mode"] == "artifact_only_descendant"
                ),
            )
            if differences:
                print("Benchmark manifest verification failed:", file=sys.stderr)
                for difference in differences:
                    print(f"  - {difference}", file=sys.stderr)
                return 1
            print(f"Benchmark manifest verified: {args.check}")
            if revision["mode"] == "artifact_only_descendant":
                print("Revision verification: " + revision["message"])
            return 0
        write_benchmark_outputs(
            benchmark_path=args.benchmark_output,
            prediction_path=args.predictions_output,
            manifest_path=args.manifest_output,
            benchmark_bytes=benchmark_bytes,
            prediction_bytes=prediction_bytes,
            manifest=current_manifest,
            force=args.force,
        )
        print(f"Benchmark summary written: {args.benchmark_output}")
        print(f"Prediction audit written: {args.predictions_output}")
        print(f"Benchmark manifest written: {args.manifest_output}")
        return 0
    except (
        BaselineError,
        BenchmarkError,
        BenchmarkExportError,
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
