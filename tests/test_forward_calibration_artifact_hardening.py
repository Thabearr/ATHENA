from __future__ import annotations

import json
from pathlib import Path

import pytest

import domain._forward_calibration_hardening as hardening
from domain.forward_calibration import (
    AUTHORITY_FLAGS,
    CALIBRATION_DATASET,
    CALIBRATION_SCHEMA_VERSION,
    CalibrationPartition,
    CalibrationVectorRow,
    ForwardCalibrationArtifact,
    ForwardCalibrationError,
    calibration_unit_specs,
    fit_forward_calibrator,
    load_forward_calibration_artifact,
    validate_calibration_contract,
)


def _rows() -> tuple[CalibrationVectorRow, ...]:
    spec = next(
        item for item in calibration_unit_specs()
        if item.unit_id == "BTTS:PARTITION"
    )
    rows = []
    for index in range(100):
        probability = 0.1 + 0.8 * ((index % 10) / 9.0)
        rows.append(CalibrationVectorRow(
            match_key=f"m{index:03d}",
            match_date=f"2024-05-{(index % 28) + 1:02d}",
            competition_key="L1",
            season="2024",
            regime="MID_EVENT",
            model_id="POISSON_GLM_SCORE_V1",
            fold_index=1,
            fit_end_date="2024-04-30",
            partition=CalibrationPartition.OOF_CALIBRATION_FIT,
            unit=spec,
            raw_probabilities=(probability, 1.0 - probability),
            observed_index=0 if index % 2 else 1,
        ))
    return tuple(rows)


def _artifact() -> ForwardCalibrationArtifact:
    return fit_forward_calibrator(
        _rows(),
        model_id="POISSON_GLM_SCORE_V1",
        source_training_view_sha256="a" * 64,
    )


def test_public_loader_revalidates_frozen_dependencies(tmp_path: Path):
    artifact = _artifact()
    path = tmp_path / "calibration.json"
    path.write_text(
        json.dumps(artifact.to_dict(), sort_keys=True),
        encoding="utf-8",
    )
    loaded = load_forward_calibration_artifact(path)
    assert loaded.artifact_sha256 == artifact.artifact_sha256
    assert dict(loaded.contract_identities) == validate_calibration_contract()


def test_loader_rejects_self_consistent_artifact_bound_to_wrong_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    artifact = _artifact()
    wrong = dict(artifact.contract_identities)
    wrong["calibration_contract_sha256"] = "f" * 64
    forged = ForwardCalibrationArtifact(
        schema_version=CALIBRATION_SCHEMA_VERSION,
        dataset=CALIBRATION_DATASET,
        model_id=artifact.model_id,
        source_training_view_sha256=artifact.source_training_view_sha256,
        fit_first_date=artifact.fit_first_date,
        fit_last_date=artifact.fit_last_date,
        oof_match_count=artifact.oof_match_count,
        contract_identities=wrong,
        unit_models=artifact.unit_models,
        authority_flags=AUTHORITY_FLAGS,
    )
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(forged.to_dict(), sort_keys=True), encoding="utf-8")
    with pytest.raises(ForwardCalibrationError, match="frozen dependency"):
        load_forward_calibration_artifact(path)


def test_loader_rejects_invalid_json_and_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ForwardCalibrationError, match="unavailable"):
        load_forward_calibration_artifact(missing)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(ForwardCalibrationError, match="invalid calibration artifact JSON"):
        load_forward_calibration_artifact(invalid)
