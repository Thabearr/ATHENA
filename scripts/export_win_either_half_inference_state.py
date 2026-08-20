"""Reconstruct the frozen WEH runtime state from exact reviewed research inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.win_either_half_benchmarks import (
    TARGETS,
    canonical_float,
    fit_benchmark_candidate,
    fit_train_preprocessor,
)
from domain.win_either_half_calibration import (
    FROZEN_STAGE_4_BASE_CONFIGURATION,
    build_expanding_oof_predictions,
    default_calibration_configurations,
    fit_calibrator,
)
from domain.win_either_half_features import PRE_MATCH_FEATURE_NAMES
from domain.win_either_half_inference import (
    AWAY_CALIBRATION_IDENTIFIER,
    BASE_MODEL_IDENTIFIER,
    CANONICAL_PROBABILITY_DECIMAL_PLACES,
    DATASET_NAME,
    FROZEN_BASE_CONFIGURATION,
    FROZEN_SOURCE_ANCESTRY,
    FROZEN_TRAINING_CONTRACT,
    HOME_CALIBRATION_IDENTIFIER,
    INFERENCE_AUTHORITY,
    INFERENCE_STATE_PATH,
    SCHEMA_VERSION,
    canonical_win_either_half_inference_state_bytes,
    fingerprint_win_either_half_inference_state,
    validate_win_either_half_inference_state,
)
from scripts.export_win_either_half_baseline_benchmarks import (
    load_verified_feature_rows,
)
from scripts.export_win_either_half_calibration_research import (
    load_verified_benchmark_summary,
    load_verified_stage_4_predictions,
)


DEFAULT_CACHE_DIRECTORY = (
    REPOSITORY_ROOT / ".cache" / "athena-research" / "win-either-half"
)
FEATURE_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "win-either-half-features-v1.json"
)
BENCHMARK_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "win-either-half-benchmarks-v1.json"
)
CALIBRATION_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "win-either-half-calibration-v1.json"
)


class WinEitherHalfInferenceStateExportError(RuntimeError):
    """Raised when frozen research ancestry or numerical parity differs."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WinEitherHalfInferenceStateExportError(
            f"cannot read {label}"
        ) from exc
    if type(value) is not dict:
        raise WinEitherHalfInferenceStateExportError(f"{label} must be an object")
    return value


def _read_exact(path: Path, identity: Mapping[str, Any], label: str) -> bytes:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise WinEitherHalfInferenceStateExportError(f"cannot read {label}") from exc
    if len(content) != identity["byte_size"]:
        raise WinEitherHalfInferenceStateExportError(f"{label} byte size drifted")
    if hashlib.sha256(content).hexdigest() != identity["sha256"]:
        raise WinEitherHalfInferenceStateExportError(f"{label} SHA-256 drifted")
    return content


def _parse_canonical_probability(value: str, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise WinEitherHalfInferenceStateExportError(
            f"{label} is not numeric"
        ) from exc
    if format(numeric, ".12f") != value:
        raise WinEitherHalfInferenceStateExportError(f"{label} is not canonical")
    return numeric


def _load_calibrated_predictions(
    content: bytes,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    expected_columns = (
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
    try:
        reader = csv.DictReader(
            io.StringIO(content.decode("utf-8", errors="strict"), newline="")
        )
    except UnicodeDecodeError as exc:
        raise WinEitherHalfInferenceStateExportError(
            "Stage 4B predictions are not UTF-8"
        ) from exc
    if tuple(reader.fieldnames or ()) != expected_columns:
        raise WinEitherHalfInferenceStateExportError(
            "Stage 4B prediction columns drifted"
        )
    result = {}
    for row in reader:
        target = row["target_name"]
        role = row["prediction_role"]
        key = (row["fixture_identity"], target, role)
        if target not in TARGETS or key in result:
            raise WinEitherHalfInferenceStateExportError(
                "Stage 4B prediction identity drifted"
            )
        result[key] = {
            **row,
            "model_probability": _parse_canonical_probability(
                row["model_probability"], "Stage 4B model probability"
            ),
            "calibrated_probability": _parse_canonical_probability(
                row["calibrated_probability"],
                "Stage 4B calibrated probability",
            ),
        }
    if len(result) != FROZEN_SOURCE_ANCESTRY[
        "stage_4b_calibrated_predictions"
    ]["rows"]:
        raise WinEitherHalfInferenceStateExportError(
            "Stage 4B prediction row count drifted"
        )
    return result


def _assert_probability(actual: float, expected: float, label: str) -> None:
    if canonical_float(actual) != canonical_float(expected):
        raise WinEitherHalfInferenceStateExportError(f"{label} differs")


def _target_values(rows: Sequence[Mapping[str, Any]], target: str) -> np.ndarray:
    return np.asarray([int(row[target]) for row in rows], dtype=int)


def build_win_either_half_inference_state(
    cache_directory: Path = DEFAULT_CACHE_DIRECTORY,
) -> dict[str, Any]:
    if not isinstance(cache_directory, Path):
        raise WinEitherHalfInferenceStateExportError(
            "cache_directory must be a Path"
        )
    feature_manifest = _read_json(FEATURE_MANIFEST_PATH, "feature manifest")
    benchmark_manifest = _read_json(BENCHMARK_MANIFEST_PATH, "benchmark manifest")
    calibration_manifest = _read_json(
        CALIBRATION_MANIFEST_PATH, "calibration manifest"
    )
    if tuple(benchmark_manifest.get("feature_columns", ())) != PRE_MATCH_FEATURE_NAMES:
        raise WinEitherHalfInferenceStateExportError("frozen feature order drifted")
    if len(PRE_MATCH_FEATURE_NAMES) != 74:
        raise WinEitherHalfInferenceStateExportError("frozen feature count drifted")
    if benchmark_manifest.get("selected_models") != {
        target: BASE_MODEL_IDENTIFIER for target in TARGETS
    }:
        raise WinEitherHalfInferenceStateExportError("selected base model drifted")
    if calibration_manifest.get("selected_calibrations") != {
        "home_win_either_half_yes": HOME_CALIBRATION_IDENTIFIER,
        "away_win_either_half_yes": AWAY_CALIBRATION_IDENTIFIER,
    }:
        raise WinEitherHalfInferenceStateExportError("selected calibration drifted")

    paths = {
        "stage_3_feature_csv": cache_directory / "features-v1.csv",
        "stage_4_benchmark_summary": cache_directory / "benchmarks-v1.json",
        "stage_4_predictions": cache_directory / "predictions-v1.csv",
        "stage_4b_calibration_summary": cache_directory / "calibration-v1.json",
        "stage_4b_calibrated_predictions": (
            cache_directory / "calibrated-predictions-v1.csv"
        ),
    }
    contents = {
        name: _read_exact(paths[name], identity, name)
        for name, identity in FROZEN_SOURCE_ANCESTRY.items()
    }
    feature_rows, feature_identity = load_verified_feature_rows(
        paths["stage_3_feature_csv"],
        feature_manifest,
        PRE_MATCH_FEATURE_NAMES,
        expected_total_rows=21_791,
        expected_split_counts={
            "TRAIN": 14_267,
            "VALIDATION": 3_476,
            "TEST": 4_048,
        },
    )
    if feature_identity != FROZEN_SOURCE_ANCESTRY["stage_3_feature_csv"]:
        raise WinEitherHalfInferenceStateExportError("feature identity drifted")
    load_verified_benchmark_summary(
        paths["stage_4_benchmark_summary"], benchmark_manifest
    )
    stage_4_predictions, prediction_identity = load_verified_stage_4_predictions(
        paths["stage_4_predictions"], benchmark_manifest, feature_rows
    )
    if prediction_identity != FROZEN_SOURCE_ANCESTRY["stage_4_predictions"]:
        raise WinEitherHalfInferenceStateExportError("Stage 4 prediction identity drifted")
    calibration_summary = json.loads(
        contents["stage_4b_calibration_summary"].decode("utf-8", errors="strict")
    )
    if calibration_summary.get("targets", {}) == {}:
        raise WinEitherHalfInferenceStateExportError("calibration summary is incomplete")
    for target in TARGETS:
        summary = calibration_summary["targets"][target]
        if (
            summary["selected_calibration_identifier"]
            != calibration_manifest["selected_calibrations"][target]
            or summary["oof"]["fit_rows"] != 10_635
        ):
            raise WinEitherHalfInferenceStateExportError(
                "Stage 4B target contract drifted"
            )
    calibrated = _load_calibrated_predictions(
        contents["stage_4b_calibrated_predictions"]
    )

    ordered_rows = tuple(
        sorted(
            feature_rows,
            key=lambda row: (
                ("TRAIN", "VALIDATION", "TEST").index(row["split"]),
                row["fixture_identity"],
            ),
        )
    )
    train_rows = tuple(row for row in ordered_rows if row["split"] == "TRAIN")
    preprocessor = fit_train_preprocessor(train_rows, PRE_MATCH_FEATURE_NAMES)
    train_imputed, train_scaled, _ = preprocessor.transform(train_rows)
    frozen_predictions = {
        (row["fixture_identity"], row["target_name"]): row[
            "predicted_probability"
        ]
        for row in stage_4_predictions
    }
    calibrator_configurations = {
        value.identifier: value for value in default_calibration_configurations()
    }
    target_states = {}
    for target in TARGETS:
        fitted = fit_benchmark_candidate(
            FROZEN_STAGE_4_BASE_CONFIGURATION,
            train_imputed=train_imputed,
            train_scaled=train_scaled,
            train_targets=_target_values(train_rows, target),
            target_name=target,
        )
        all_imputed, all_scaled, _ = preprocessor.transform(ordered_rows)
        full_probabilities = fitted.predict(all_imputed, all_scaled)
        for row, probability in zip(ordered_rows, full_probabilities):
            _assert_probability(
                probability,
                frozen_predictions[(row["fixture_identity"], target)],
                f"Stage 4A {target} probability",
            )

        oof = build_expanding_oof_predictions(
            train_rows,
            PRE_MATCH_FEATURE_NAMES,
            FROZEN_STAGE_4_BASE_CONFIGURATION,
            target,
        )
        if len(oof["predictions"]) != 10_635:
            raise WinEitherHalfInferenceStateExportError("OOF row count drifted")
        selected_calibration = calibration_manifest["selected_calibrations"][target]
        calibrator = fit_calibrator(
            calibrator_configurations[selected_calibration],
            [row["model_probability"] for row in oof["predictions"]],
            [row["target_value"] for row in oof["predictions"]],
            target_name=target,
        )
        oof_transformed = calibrator.transform(
            [row["model_probability"] for row in oof["predictions"]]
        )
        for row, transformed in zip(oof["predictions"], oof_transformed):
            frozen = calibrated[(
                row["fixture_identity"],
                target,
                "CALIBRATION_FIT_OOF",
            )]
            _assert_probability(
                row["model_probability"],
                frozen["model_probability"],
                f"Stage 4B OOF {target} base probability",
            )
            _assert_probability(
                transformed,
                frozen["calibrated_probability"],
                f"Stage 4B OOF {target} calibrated probability",
            )
        full_calibrated = calibrator.transform(full_probabilities)
        for row, probability, transformed in zip(
            ordered_rows, full_probabilities, full_calibrated
        ):
            if row["split"] == "TRAIN":
                continue
            role = (
                "VALIDATION_SELECTION"
                if row["split"] == "VALIDATION"
                else "FINAL_TEST"
            )
            frozen = calibrated[(row["fixture_identity"], target, role)]
            _assert_probability(
                probability,
                frozen["model_probability"],
                f"Stage 4B {role} {target} base probability",
            )
            _assert_probability(
                transformed,
                frozen["calibrated_probability"],
                f"Stage 4B {role} {target} calibrated probability",
            )

        calibration_state: dict[str, Any]
        if selected_calibration == HOME_CALIBRATION_IDENTIFIER:
            calibration_state = {
                "family": "isotonic",
                "identifier": selected_calibration,
                "out_of_bounds": "clip",
                "x_thresholds": [
                    float(value) for value in calibrator.estimator.X_thresholds_
                ],
                "y_thresholds": [
                    float(value) for value in calibrator.estimator.y_thresholds_
                ],
            }
        else:
            calibration_state = {
                "family": "identity",
                "identifier": selected_calibration,
            }
        target_states[target] = {
            "base_model_identifier": BASE_MODEL_IDENTIFIER,
            "calibration": calibration_state,
            "coefficient_order": list(PRE_MATCH_FEATURE_NAMES),
            "coefficients": [float(value) for value in fitted.estimator.coef_[0]],
            "intercept": float(fitted.estimator.intercept_[0]),
        }

    state = {
        "authority": dict(INFERENCE_AUTHORITY),
        "base_configuration": dict(FROZEN_BASE_CONFIGURATION),
        "canonical_probability_decimal_places": (
            CANONICAL_PROBABILITY_DECIMAL_PLACES
        ),
        "dataset_name": DATASET_NAME,
        "feature_order": list(PRE_MATCH_FEATURE_NAMES),
        "preprocessing": {
            "feature_names": list(PRE_MATCH_FEATURE_NAMES),
            "means": [float(value) for value in preprocessor.means],
            "medians": [float(value) for value in preprocessor.medians],
            "scales": [float(value) for value in preprocessor.scales],
        },
        "schema_version": SCHEMA_VERSION,
        "source_ancestry": dict(FROZEN_SOURCE_ANCESTRY),
        "targets": target_states,
        "training_contract": dict(FROZEN_TRAINING_CONTRACT),
    }
    state["state_fingerprint_sha256"] = (
        fingerprint_win_either_half_inference_state(state)
    )
    validate_win_either_half_inference_state(state)
    return state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-directory", type=Path, default=DEFAULT_CACHE_DIRECTORY)
    parser.add_argument("--output", type=Path, default=INFERENCE_STATE_PATH)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    state = build_win_either_half_inference_state(arguments.cache_directory)
    content = canonical_win_either_half_inference_state_bytes(state)
    if arguments.check:
        if arguments.output.read_bytes() != content:
            raise WinEitherHalfInferenceStateExportError(
                "committed inference state differs from exact reconstruction"
            )
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_bytes(content)
    print(
        json.dumps(
            {
                "artifact_sha256": hashlib.sha256(content).hexdigest(),
                "artifact_size": len(content),
                "state_fingerprint_sha256": state["state_fingerprint_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
