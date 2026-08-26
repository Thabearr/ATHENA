"""Forward-chaining calibrator fitting, evaluation, and JSON artifact protocol."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.isotonic import IsotonicRegression

from domain._forward_calibration_contracts import *
from domain._forward_calibration_projection import *
from domain._goal_score_evaluation import chronological_split, rolling_origin_folds
from domain._goal_score_models import fit_challenger
from domain.markets import MarketFamily, MarketId, OutcomeId


@dataclass(frozen=True)
class IsotonicComponentMap:
    method: str
    sample_count: int
    positive_count: int
    x_thresholds: tuple[float, ...] = ()
    y_thresholds: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.method not in {"IDENTITY", "ISOTONIC"}:
            raise ForwardCalibrationError("unknown component calibrator method")
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count < 0
            or isinstance(self.positive_count, bool)
            or not isinstance(self.positive_count, int)
            or not 0 <= self.positive_count <= self.sample_count
        ):
            raise ForwardCalibrationError("invalid component calibrator counts")
        if self.method == "IDENTITY":
            if self.x_thresholds or self.y_thresholds:
                raise ForwardCalibrationError("identity calibrator cannot retain thresholds")
            return
        if (
            len(self.x_thresholds) < 2
            or len(self.x_thresholds) != len(self.y_thresholds)
            or any(not math.isfinite(value) for value in self.x_thresholds + self.y_thresholds)
            or any(left >= right for left, right in zip(self.x_thresholds, self.x_thresholds[1:]))
            or any(left > right for left, right in zip(self.y_thresholds, self.y_thresholds[1:]))
            or any(not 0.0 <= value <= 1.0 for value in self.y_thresholds)
        ):
            raise ForwardCalibrationError("invalid isotonic threshold map")

    def predict(self, probability: float) -> float:
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ForwardCalibrationError("calibrator input must be a probability")
        if self.method == "IDENTITY":
            return float(probability)
        return float(np.interp(
            probability,
            np.asarray(self.x_thresholds, dtype=float),
            np.asarray(self.y_thresholds, dtype=float),
        ))

    def stable_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "sample_count": self.sample_count,
            "positive_count": self.positive_count,
            "x_thresholds": list(self.x_thresholds),
            "y_thresholds": list(self.y_thresholds),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IsotonicComponentMap":
        return cls(
            method=str(value["method"]),
            sample_count=int(value["sample_count"]),
            positive_count=int(value["positive_count"]),
            x_thresholds=tuple(float(item) for item in value.get("x_thresholds", ())),
            y_thresholds=tuple(float(item) for item in value.get("y_thresholds", ())),
        )


@dataclass(frozen=True)
class GroupCalibration:
    group_key: str
    sample_count: int
    component_maps: tuple[IsotonicComponentMap, ...]

    def __post_init__(self) -> None:
        if not self.group_key or self.sample_count < 1 or not self.component_maps:
            raise ForwardCalibrationError("invalid grouped calibration model")

    @property
    def shrinkage_weight(self) -> float:
        return self.sample_count / (self.sample_count + HIERARCHICAL_SHRINKAGE_K)

    def stable_dict(self) -> dict[str, Any]:
        return {
            "group_key": self.group_key,
            "sample_count": self.sample_count,
            "shrinkage_weight": self.shrinkage_weight,
            "component_maps": [item.stable_dict() for item in self.component_maps],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GroupCalibration":
        return cls(
            group_key=str(value["group_key"]),
            sample_count=int(value["sample_count"]),
            component_maps=tuple(
                IsotonicComponentMap.from_dict(item)
                for item in value["component_maps"]
            ),
        )


def _apply_component_maps(
    unit: CalibrationUnitSpec,
    raw: Sequence[float],
    maps: Sequence[IsotonicComponentMap],
) -> tuple[float, ...]:
    if unit.topology is CalibrationTopology.BINARY_PARTITION:
        if len(maps) != 1:
            raise ForwardCalibrationError("binary unit requires one primary calibrator")
        primary = min(max(maps[0].predict(float(raw[0])), PROBABILITY_CLIP), 1.0 - PROBABILITY_CLIP)
        return (primary, 1.0 - primary)
    if len(maps) != len(raw):
        raise ForwardCalibrationError("simplex component calibrator width mismatch")
    values = [
        min(max(calibrator.predict(float(probability)), PROBABILITY_CLIP), 1.0 - PROBABILITY_CLIP)
        for probability, calibrator in zip(raw, maps)
    ]
    total = math.fsum(values)
    if not math.isfinite(total) or total <= 0.0:
        raise ForwardCalibrationError("calibrated simplex cannot be normalized")
    return tuple(value / total for value in values)


def _blend_vectors(
    unit: CalibrationUnitSpec,
    parent: Sequence[float],
    child: Sequence[float],
    weight: float,
) -> tuple[float, ...]:
    if not 0.0 <= weight <= 1.0:
        raise ForwardCalibrationError("hierarchical shrinkage weight invalid")
    if unit.topology is CalibrationTopology.BINARY_PARTITION:
        primary = (1.0 - weight) * parent[0] + weight * child[0]
        return (primary, 1.0 - primary)
    blended = tuple(
        (1.0 - weight) * left + weight * right
        for left, right in zip(parent, child)
    )
    total = math.fsum(blended)
    return tuple(value / total for value in blended)


@dataclass(frozen=True)
class UnitCalibrationModel:
    unit: CalibrationUnitSpec
    sample_count: int
    global_maps: tuple[IsotonicComponentMap, ...]
    competition_maps: Mapping[str, GroupCalibration]
    regime_maps: Mapping[str, GroupCalibration]
    competition_regime_maps: Mapping[str, GroupCalibration]

    def __post_init__(self) -> None:
        expected_width = 1 if self.unit.topology is CalibrationTopology.BINARY_PARTITION else len(self.unit.components)
        if self.sample_count < 1 or len(self.global_maps) != expected_width:
            raise ForwardCalibrationError("unit calibration model width/count mismatch")
        for mapping in (
            self.competition_maps,
            self.regime_maps,
            self.competition_regime_maps,
        ):
            if not isinstance(mapping, Mapping):
                raise ForwardCalibrationError("group calibrations must be mappings")
        object.__setattr__(self, "competition_maps", MappingProxyType(dict(self.competition_maps)))
        object.__setattr__(self, "regime_maps", MappingProxyType(dict(self.regime_maps)))
        object.__setattr__(self, "competition_regime_maps", MappingProxyType(dict(self.competition_regime_maps)))

    def _shrunk(self, raw: Sequence[float], group: GroupCalibration | None) -> tuple[float, ...]:
        parent = _apply_component_maps(self.unit, raw, self.global_maps)
        if group is None:
            return parent
        child = _apply_component_maps(self.unit, raw, group.component_maps)
        return _blend_vectors(self.unit, parent, child, group.shrinkage_weight)

    def predict(self, row: CalibrationVectorRow, strategy: str = "HIERARCHICAL") -> tuple[float, ...]:
        if row.unit != self.unit:
            raise ForwardCalibrationError("unit model applied to different calibration unit")
        strategy = str(strategy).strip().upper()
        if strategy == "GLOBAL":
            return self._shrunk(row.raw_probabilities, None)
        if strategy == "COMPETITION":
            group = None if row.competition_key is None else self.competition_maps.get(row.competition_key)
            return self._shrunk(row.raw_probabilities, group)
        if strategy == "REGIME":
            group = None if row.regime == "UNKNOWN" else self.regime_maps.get(row.regime)
            return self._shrunk(row.raw_probabilities, group)
        if strategy != "HIERARCHICAL":
            raise ForwardCalibrationError("unknown calibration prediction strategy")
        group = None
        if row.competition_key is not None and row.regime != "UNKNOWN":
            group = self.competition_regime_maps.get(
                f"{row.competition_key}\x1f{row.regime}"
            )
        if group is None and row.competition_key is not None:
            group = self.competition_maps.get(row.competition_key)
        if group is None and row.regime != "UNKNOWN":
            group = self.regime_maps.get(row.regime)
        return self._shrunk(row.raw_probabilities, group)

    def stable_dict(self) -> dict[str, Any]:
        def groups(value: Mapping[str, GroupCalibration]) -> dict[str, Any]:
            return {key: item.stable_dict() for key, item in sorted(value.items())}
        return {
            "unit": self.unit.stable_dict(),
            "sample_count": self.sample_count,
            "global_maps": [item.stable_dict() for item in self.global_maps],
            "competition_maps": groups(self.competition_maps),
            "regime_maps": groups(self.regime_maps),
            "competition_regime_maps": groups(self.competition_regime_maps),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "UnitCalibrationModel":
        spec = _unit_from_dict(value["unit"])
        def groups(raw: Mapping[str, Any]) -> dict[str, GroupCalibration]:
            return {key: GroupCalibration.from_dict(item) for key, item in raw.items()}
        return cls(
            unit=spec,
            sample_count=int(value["sample_count"]),
            global_maps=tuple(IsotonicComponentMap.from_dict(item) for item in value["global_maps"]),
            competition_maps=groups(value.get("competition_maps", {})),
            regime_maps=groups(value.get("regime_maps", {})),
            competition_regime_maps=groups(value.get("competition_regime_maps", {})),
        )


def _unit_from_dict(value: Mapping[str, Any]) -> CalibrationUnitSpec:
    return CalibrationUnitSpec(
        unit_id=str(value["unit_id"]),
        market_id=MarketId(str(value["market_id"])),
        family=MarketFamily(str(value["family"])),
        topology=CalibrationTopology(str(value["topology"])),
        components=tuple(str(item) for item in value["components"]),
        selection_outcome=(
            None
            if value.get("selection_outcome") is None
            else OutcomeId(str(value["selection_outcome"]))
        ),
        line=None if value.get("line") is None else float(value["line"]),
        line_origin_policy_id=value.get("line_origin_policy_id"),
    )


@dataclass(frozen=True)
class ForwardCalibrationArtifact:
    schema_version: int
    dataset: str
    model_id: str
    source_training_view_sha256: str
    fit_first_date: str
    fit_last_date: str
    oof_match_count: int
    contract_identities: Mapping[str, str]
    unit_models: Mapping[str, UnitCalibrationModel]
    authority_flags: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_SCHEMA_VERSION or self.dataset != CALIBRATION_DATASET:
            raise ForwardCalibrationError("calibration artifact schema identity mismatch")
        if not self.model_id or len(self.source_training_view_sha256) != 64:
            raise ForwardCalibrationError("calibration artifact source identity missing")
        if not self.fit_first_date or not self.fit_last_date or self.fit_first_date > self.fit_last_date:
            raise ForwardCalibrationError("calibration fit chronology invalid")
        if self.oof_match_count < 1 or not self.unit_models:
            raise ForwardCalibrationError("calibration artifact cannot be empty")
        if dict(self.authority_flags) != dict(AUTHORITY_FLAGS):
            raise ForwardCalibrationError("calibration artifact authority drift")
        object.__setattr__(self, "contract_identities", MappingProxyType(dict(self.contract_identities)))
        object.__setattr__(self, "unit_models", MappingProxyType(dict(self.unit_models)))
        object.__setattr__(self, "authority_flags", MappingProxyType(dict(self.authority_flags)))

    def predict(self, row: CalibrationVectorRow, strategy: str = "HIERARCHICAL") -> tuple[float, ...]:
        if row.model_id != self.model_id:
            raise ForwardCalibrationError("calibration artifact model identity mismatch")
        try:
            model = self.unit_models[row.unit.unit_id]
        except KeyError as exc:
            raise ForwardCalibrationError("calibration unit absent from artifact") from exc
        return model.predict(row, strategy)

    def payload_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset": self.dataset,
            "model_id": self.model_id,
            "source_training_view_sha256": self.source_training_view_sha256,
            "fit_first_date": self.fit_first_date,
            "fit_last_date": self.fit_last_date,
            "oof_match_count": self.oof_match_count,
            "contract_identities": dict(sorted(self.contract_identities.items())),
            "unit_models": {
                key: value.stable_dict() for key, value in sorted(self.unit_models.items())
            },
            "authority_flags": dict(self.authority_flags),
        }

    @property
    def artifact_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.payload_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload_dict(), "artifact_sha256": self.artifact_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ForwardCalibrationArtifact":
        artifact = cls(
            schema_version=int(value["schema_version"]),
            dataset=str(value["dataset"]),
            model_id=str(value["model_id"]),
            source_training_view_sha256=str(value["source_training_view_sha256"]),
            fit_first_date=str(value["fit_first_date"]),
            fit_last_date=str(value["fit_last_date"]),
            oof_match_count=int(value["oof_match_count"]),
            contract_identities={str(k): str(v) for k, v in value["contract_identities"].items()},
            unit_models={
                key: UnitCalibrationModel.from_dict(item)
                for key, item in value["unit_models"].items()
            },
            authority_flags={str(k): bool(v) for k, v in value["authority_flags"].items()},
        )
        supplied = value.get("artifact_sha256")
        if supplied is not None and supplied != artifact.artifact_sha256:
            raise ForwardCalibrationError("calibration artifact SHA-256 mismatch")
        return artifact


def _fit_component_map(
    probabilities: Sequence[float],
    targets: Sequence[int],
    *,
    minimum_samples: int,
) -> IsotonicComponentMap:
    n = len(probabilities)
    positives = int(sum(targets))
    negatives = n - positives
    unique = len(set(float(value) for value in probabilities))
    if (
        n < minimum_samples
        or positives < MINIMUM_POSITIVE_SAMPLES
        or negatives < MINIMUM_POSITIVE_SAMPLES
        or unique < MINIMUM_UNIQUE_PROBABILITIES
    ):
        return IsotonicComponentMap("IDENTITY", n, positives)
    estimator = IsotonicRegression(
        y_min=PROBABILITY_CLIP,
        y_max=1.0 - PROBABILITY_CLIP,
        out_of_bounds="clip",
    )
    estimator.fit(np.asarray(probabilities, dtype=float), np.asarray(targets, dtype=float))
    return IsotonicComponentMap(
        "ISOTONIC",
        n,
        positives,
        tuple(float(value) for value in estimator.X_thresholds_),
        tuple(float(value) for value in estimator.y_thresholds_),
    )


def _fit_maps(
    rows: Sequence[CalibrationVectorRow],
    *,
    minimum_samples: int,
) -> tuple[IsotonicComponentMap, ...]:
    if not rows:
        raise ForwardCalibrationError("cannot fit calibration map on empty rows")
    unit = rows[0].unit
    if any(row.unit != unit for row in rows):
        raise ForwardCalibrationError("mixed units in one calibration fit")
    indexes = (0,) if unit.topology is CalibrationTopology.BINARY_PARTITION else range(len(unit.components))
    return tuple(
        _fit_component_map(
            [row.raw_probabilities[index] for row in rows],
            [1 if row.observed_index == index else 0 for row in rows],
            minimum_samples=minimum_samples,
        )
        for index in indexes
    )


def _fit_group_map(
    rows: Sequence[CalibrationVectorRow],
    key_getter: Any,
) -> dict[str, GroupCalibration]:
    grouped: dict[str, list[CalibrationVectorRow]] = {}
    for row in rows:
        key = key_getter(row)
        if key is None:
            continue
        grouped.setdefault(str(key), []).append(row)
    return {
        key: GroupCalibration(
            group_key=key,
            sample_count=len(values),
            component_maps=_fit_maps(values, minimum_samples=MINIMUM_LOCAL_SAMPLES),
        )
        for key, values in sorted(grouped.items())
        if len(values) >= MINIMUM_LOCAL_SAMPLES
    }


def fit_forward_calibrator(
    rows: Sequence[CalibrationVectorRow],
    *,
    model_id: str,
    source_training_view_sha256: str,
    contract_identities: Mapping[str, str] | None = None,
) -> ForwardCalibrationArtifact:
    if not rows:
        raise ForwardCalibrationError("forward calibration requires OOF rows")
    if any(row.partition is not CalibrationPartition.OOF_CALIBRATION_FIT for row in rows):
        raise ForwardCalibrationError("terminal holdout cannot enter calibrator fitting")
    if any(row.model_id != model_id for row in rows):
        raise ForwardCalibrationError("mixed model identities in calibration fit")
    identities = dict(contract_identities or validate_calibration_contract())
    if identities.get("calibration_contract_sha256") != EXPECTED_CALIBRATION_CONTRACT_SHA256_BY_VERSION[CALIBRATION_CONTRACT_VERSION]:
        raise ForwardCalibrationError("calibration contract identity mismatch")
    grouped: dict[str, list[CalibrationVectorRow]] = {}
    for row in rows:
        grouped.setdefault(row.unit.unit_id, []).append(row)
    unit_models: dict[str, UnitCalibrationModel] = {}
    for unit_id, values in sorted(grouped.items()):
        unit = values[0].unit
        unit_models[unit_id] = UnitCalibrationModel(
            unit=unit,
            sample_count=len(values),
            global_maps=_fit_maps(values, minimum_samples=MINIMUM_GLOBAL_SAMPLES),
            competition_maps=_fit_group_map(
                values,
                lambda row: row.competition_key,
            ),
            regime_maps=_fit_group_map(
                values,
                lambda row: None if row.regime == "UNKNOWN" else row.regime,
            ),
            competition_regime_maps=_fit_group_map(
                values,
                lambda row: (
                    None
                    if row.competition_key is None or row.regime == "UNKNOWN"
                    else f"{row.competition_key}\x1f{row.regime}"
                ),
            ),
        )
    match_keys = {row.match_key for row in rows}
    return ForwardCalibrationArtifact(
        schema_version=CALIBRATION_SCHEMA_VERSION,
        dataset=CALIBRATION_DATASET,
        model_id=model_id,
        source_training_view_sha256=source_training_view_sha256,
        fit_first_date=min(row.match_date for row in rows),
        fit_last_date=max(row.match_date for row in rows),
        oof_match_count=len(match_keys),
        contract_identities=identities,
        unit_models=unit_models,
        authority_flags=AUTHORITY_FLAGS,
    )


def _reliability_metrics(
    rows: Sequence[CalibrationVectorRow],
    predictions: Sequence[Sequence[float]],
) -> dict[str, Any]:
    if not rows or len(rows) != len(predictions):
        raise ForwardCalibrationError("metrics require paired calibration rows")
    width = len(rows[0].unit.components)
    if any(len(vector) != width for vector in predictions):
        raise ForwardCalibrationError("metric probability width mismatch")
    log_losses: list[float] = []
    briers: list[float] = []
    for row, vector in zip(rows, predictions):
        probability = max(float(vector[row.observed_index]), PROBABILITY_CLIP)
        log_losses.append(-math.log(probability))
        briers.append(math.fsum(
            (float(value) - (1.0 if index == row.observed_index else 0.0)) ** 2
            for index, value in enumerate(vector)
        ))
    component_ece: list[float] = []
    reliability: dict[str, list[dict[str, Any]]] = {}
    mean_gaps: list[float] = []
    for component_index, component in enumerate(rows[0].unit.components):
        bin_rows: list[dict[str, Any]] = []
        ece = 0.0
        predicted_mean = float(np.mean([vector[component_index] for vector in predictions]))
        observed_mean = float(np.mean([
            1.0 if row.observed_index == component_index else 0.0 for row in rows
        ]))
        mean_gaps.append(abs(predicted_mean - observed_mean))
        for bin_index in range(ECE_BINS):
            lower = bin_index / ECE_BINS
            upper = (bin_index + 1) / ECE_BINS
            indexes = [
                index for index, vector in enumerate(predictions)
                if (
                    lower <= vector[component_index] < upper
                    or (bin_index == ECE_BINS - 1 and vector[component_index] == 1.0)
                )
            ]
            if not indexes:
                continue
            mean_predicted = float(np.mean([predictions[index][component_index] for index in indexes]))
            observed_rate = float(np.mean([
                1.0 if rows[index].observed_index == component_index else 0.0
                for index in indexes
            ]))
            weight = len(indexes) / len(rows)
            ece += weight * abs(mean_predicted - observed_rate)
            bin_rows.append({
                "lower": lower,
                "upper": upper,
                "count": len(indexes),
                "mean_predicted": mean_predicted,
                "observed_rate": observed_rate,
            })
        component_ece.append(ece)
        reliability[component] = bin_rows
    return {
        "sample_count": len(rows),
        "log_loss": float(np.mean(log_losses)),
        "brier": float(np.mean(briers)),
        "classwise_ece": float(np.mean(component_ece)),
        "mean_abs_reliability_gap": float(np.mean(mean_gaps)),
        "reliability_bins": reliability,
    }


def _gate(raw: Mapping[str, float], calibrated: Mapping[str, float]) -> dict[str, Any]:
    n = int(calibrated["sample_count"])
    if n < MINIMUM_GLOBAL_SAMPLES:
        return {"status": "INSUFFICIENT_SAMPLE", "sample_count": n}
    ece_passed = calibrated["classwise_ece"] <= raw["classwise_ece"] + 1e-12
    log_limit = raw["log_loss"] * (1.0 + MAXIMUM_SECONDARY_RELATIVE_REGRESSION)
    brier_limit = raw["brier"] * (1.0 + MAXIMUM_SECONDARY_RELATIVE_REGRESSION)
    log_passed = calibrated["log_loss"] <= log_limit + 1e-12
    brier_passed = calibrated["brier"] <= brier_limit + 1e-12
    return {
        "status": "PASS" if ece_passed and log_passed and brier_passed else "FAIL",
        "sample_count": n,
        "ece_nonworse": ece_passed,
        "log_loss_guardrail": log_passed,
        "brier_guardrail": brier_passed,
        "maximum_secondary_relative_regression": MAXIMUM_SECONDARY_RELATIVE_REGRESSION,
        "log_loss_limit": log_limit,
        "brier_limit": brier_limit,
    }


def evaluate_calibration(
    rows: Sequence[CalibrationVectorRow],
    artifact: ForwardCalibrationArtifact,
) -> dict[str, Any]:
    if not rows:
        raise ForwardCalibrationError("calibration evaluation requires rows")
    grouped: dict[str, list[CalibrationVectorRow]] = {}
    for row in rows:
        grouped.setdefault(row.unit.unit_id, []).append(row)
    unit_results: dict[str, Any] = {}
    for unit_id, values in sorted(grouped.items()):
        raw_vectors = [row.raw_probabilities for row in values]
        strategies = {
            "RAW": raw_vectors,
            "GLOBAL": [artifact.predict(row, "GLOBAL") for row in values],
            "COMPETITION": [artifact.predict(row, "COMPETITION") for row in values],
            "REGIME": [artifact.predict(row, "REGIME") for row in values],
            "HIERARCHICAL": [artifact.predict(row, "HIERARCHICAL") for row in values],
        }
        metrics = {
            strategy: _reliability_metrics(values, vectors)
            for strategy, vectors in strategies.items()
        }
        unit_results[unit_id] = {
            "unit": values[0].unit.stable_dict(),
            "metrics": metrics,
            "gate": _gate(metrics["RAW"], metrics["HIERARCHICAL"]),
        }

    family_units: dict[str, list[dict[str, Any]]] = {}
    for result in unit_results.values():
        family_units.setdefault(result["unit"]["family"], []).append(result)
    family_results: dict[str, Any] = {}
    for family, results in sorted(family_units.items()):
        sample_count = sum(item["metrics"]["RAW"]["sample_count"] for item in results)
        def weighted(strategy: str, metric: str) -> float:
            return sum(
                item["metrics"][strategy][metric] * item["metrics"][strategy]["sample_count"]
                for item in results
            ) / sample_count
        compact = {
            strategy: {
                "sample_count": sample_count,
                "log_loss": weighted(strategy, "log_loss"),
                "brier": weighted(strategy, "brier"),
                "classwise_ece": weighted(strategy, "classwise_ece"),
                "mean_abs_reliability_gap": weighted(strategy, "mean_abs_reliability_gap"),
            }
            for strategy in ("RAW", "GLOBAL", "COMPETITION", "REGIME", "HIERARCHICAL")
        }
        family_results[family] = {
            "metrics": compact,
            "gate": _gate(compact["RAW"], compact["HIERARCHICAL"]),
            "unit_count": len(results),
        }
    considered = [
        result["gate"]["status"]
        for result in family_results.values()
        if result["gate"]["status"] != "INSUFFICIENT_SAMPLE"
    ]
    overall = (
        "INSUFFICIENT_SAMPLE"
        if not considered
        else "PASS"
        if all(status == "PASS" for status in considered)
        else "FAIL"
    )
    return {
        "unit_results": unit_results,
        "family_results": family_results,
        "overall_reliability_ece_gate": overall,
    }


def _identity_sha(rows: Sequence[CalibrationVectorRow]) -> str:
    payload = sorted({(row.match_date, row.match_key) for row in rows})
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def build_forward_oof_rows(
    rows: Sequence[TrainingRow],
    *,
    model_id: str,
    specs: Sequence[CalibrationUnitSpec],
) -> tuple[tuple[CalibrationVectorRow, ...], tuple[TrainingRow, ...], tuple[TrainingRow, ...]]:
    split = chronological_split(rows)
    folds = rolling_origin_folds(split.development_rows)
    output: list[CalibrationVectorRow] = []
    for fold_index, (train, validation) in enumerate(folds, start=1):
        fit_end_date = max(row.match_date for row in train)
        model = fit_challenger(model_id, train)
        predictions = model.predict(validation)
        for target, distribution in zip(validation, predictions):
            output.extend(project_calibration_rows(
                target,
                distribution,
                model_id=model_id,
                fold_index=fold_index,
                fit_end_date=fit_end_date,
                partition=CalibrationPartition.OOF_CALIBRATION_FIT,
                specs=specs,
            ))
    return tuple(output), split.development_rows, split.holdout_rows


def build_terminal_holdout_rows(
    development_rows: Sequence[TrainingRow],
    holdout_rows: Sequence[TrainingRow],
    *,
    model_id: str,
    specs: Sequence[CalibrationUnitSpec],
) -> tuple[CalibrationVectorRow, ...]:
    if not development_rows or not holdout_rows:
        raise ForwardCalibrationError("terminal calibration evaluation requires chronology")
    fit_end_date = max(row.match_date for row in development_rows)
    if fit_end_date >= min(row.match_date for row in holdout_rows):
        raise ForwardCalibrationError("terminal holdout chronology violation")
    model = fit_challenger(model_id, development_rows)
    predictions = model.predict(holdout_rows)
    output: list[CalibrationVectorRow] = []
    for target, distribution in zip(holdout_rows, predictions):
        output.extend(project_calibration_rows(
            target,
            distribution,
            model_id=model_id,
            fold_index=0,
            fit_end_date=fit_end_date,
            partition=CalibrationPartition.TERMINAL_HOLDOUT_EVALUATION,
            specs=specs,
        ))
    return tuple(output)


def run_forward_calibration(
    rows: Sequence[TrainingRow],
    *,
    model_id: str,
    source_training_view_sha256: str,
    total_goal_lines: Sequence[float] = (),
    asian_handicap_home_lines: Sequence[float] = (),
) -> tuple[ForwardCalibrationArtifact, dict[str, Any]]:
    contract_identities = validate_calibration_contract()
    specs = calibration_unit_specs(
        total_goal_lines=total_goal_lines,
        asian_handicap_home_lines=asian_handicap_home_lines,
    )
    oof_rows, development_rows, holdout_rows = build_forward_oof_rows(
        rows, model_id=model_id, specs=specs
    )
    artifact = fit_forward_calibrator(
        oof_rows,
        model_id=model_id,
        source_training_view_sha256=source_training_view_sha256,
        contract_identities=contract_identities,
    )
    terminal_rows = build_terminal_holdout_rows(
        development_rows,
        holdout_rows,
        model_id=model_id,
        specs=specs,
    )
    evaluation = evaluate_calibration(terminal_rows, artifact)
    report = {
        "dataset": CALIBRATION_DATASET,
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "model_id": model_id,
        "source_training_view_sha256": source_training_view_sha256,
        "calibration_artifact_sha256": artifact.artifact_sha256,
        "contract_identities": contract_identities,
        "oof_policy_id": OOF_POLICY_ID,
        "terminal_holdout_policy_id": TERMINAL_HOLDOUT_POLICY_ID,
        "oof_match_count": len({row.match_key for row in oof_rows}),
        "oof_vector_row_count": len(oof_rows),
        "oof_first_date": min(row.match_date for row in oof_rows),
        "oof_last_date": max(row.match_date for row in oof_rows),
        "oof_identity_sha256": _identity_sha(oof_rows),
        "terminal_holdout_match_count": len({row.match_key for row in terminal_rows}),
        "terminal_holdout_vector_row_count": len(terminal_rows),
        "terminal_holdout_first_date": min(row.match_date for row in terminal_rows),
        "terminal_holdout_last_date": max(row.match_date for row in terminal_rows),
        "terminal_holdout_identity_sha256": _identity_sha(terminal_rows),
        "calibrator_fit_contains_terminal_holdout": False,
        "research_line_policy_id": LINE_POLICY_ID,
        "research_total_goal_lines": sorted(float(value) for value in total_goal_lines),
        "research_asian_handicap_home_lines": sorted(float(value) for value in asian_handicap_home_lines),
        "blocked_specialist_families": {
            "WIN_EITHER_HALF": "BLOCKED_REQUIRES_VALIDATED_HALF_DYNAMICS_SPECIALIST",
            "EARLY_PAYOUT": "BLOCKED_REQUIRES_VALIDATED_LEAD_PATH_SPECIALIST",
        },
        "evaluation": evaluation,
        "authority_flags": dict(AUTHORITY_FLAGS),
    }
    return artifact, report


def canonical_calibration_artifact_bytes(artifact: ForwardCalibrationArtifact) -> bytes:
    return _canonical_bytes(artifact.to_dict()) + b"\n"


def load_forward_calibration_artifact(path: Any) -> ForwardCalibrationArtifact:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ForwardCalibrationError("calibration artifact JSON must be an object")
    return ForwardCalibrationArtifact.from_dict(raw)


__all__ = [name for name in globals() if not name.startswith("_")]
