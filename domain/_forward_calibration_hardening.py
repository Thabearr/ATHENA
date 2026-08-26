"""Load-time hardening for persisted forward-calibration artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain._forward_calibration_contracts import (
    ForwardCalibrationError,
    validate_calibration_contract,
)
from domain._forward_calibration_fit import ForwardCalibrationArtifact


def load_forward_calibration_artifact(path: Path) -> ForwardCalibrationArtifact:
    """Load one canonical JSON calibrator and revalidate every frozen dependency.

    Phase 7 must never accept an artifact merely because its self-hash is valid:
    the artifact must also bind the exact currently reviewed Goal/Score,
    training-view, label, market-semantics, and calibration contracts.
    """
    source = Path(path).resolve()
    if not source.is_file():
        raise ForwardCalibrationError(f"calibration artifact unavailable: {source}")
    try:
        raw: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ForwardCalibrationError("invalid calibration artifact JSON") from exc
    if not isinstance(raw, dict):
        raise ForwardCalibrationError("calibration artifact JSON must be an object")
    supplied_sha = raw.get("artifact_sha256")
    if (
        not isinstance(supplied_sha, str)
        or len(supplied_sha) != 64
        or any(character not in "0123456789abcdef" for character in supplied_sha)
    ):
        raise ForwardCalibrationError(
            "calibration artifact requires canonical artifact_sha256"
        )
    artifact = ForwardCalibrationArtifact.from_dict(raw)
    expected = validate_calibration_contract()
    if dict(artifact.contract_identities) != expected:
        raise ForwardCalibrationError(
            "calibration artifact frozen dependency identity mismatch"
        )
    return artifact


__all__ = ["load_forward_calibration_artifact"]
