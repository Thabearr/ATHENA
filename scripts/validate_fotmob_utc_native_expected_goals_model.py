"""Controlled CLI for the reviewed FotMob UTC-native xG validation.

The CLI is the source-bound execution entrypoint.  It revalidates the exact
preserved V2 artifact archive and its canonical qualification receipt before it
allows the projection-only evaluator to fit any research model arm.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

import domain.fotmob_utc_native_expected_goals_model_validation_protocol as pr140
from domain.fotmob_utc_native_expected_goals_model_validation import (
    MODEL_IDS,
    FotMobUTCNativeExpectedGoalsModelValidationError,
    build_validation,
    canonical_validation_receipt_bytes,
)


PROJECTION_MEMBER = "utc-native-feature-projection-v2.ndjson"
QUALIFICATION_RECEIPT_MEMBER = "qualification-v2-receipt.json"
QUALIFICATION_STATUS = "QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION"
QUALIFICATION_STATE = (
    "EXECUTED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_MODEL_USE_UNREVIEWED"
)
FRESHNESS_STATUS = "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"


def _error(message: str) -> FotMobUTCNativeExpectedGoalsModelValidationError:
    return FotMobUTCNativeExpectedGoalsModelValidationError(message)


def _canonical(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("artifact receipt canonical serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _validated_artifact(artifact: Path) -> tuple[bytes, dict]:
    """Return exact projection bytes only after full V2 archive reconciliation."""
    protocol = pr140.build_fotmob_utc_native_expected_goals_model_validation_protocol()
    evidence = protocol["v2_success_evidence"]
    artifact = Path(artifact)
    if not artifact.is_file():
        raise _error("preserved V2 qualification artifact path does not exist")
    archive = artifact.read_bytes()
    if (hashlib.sha256(archive).hexdigest(), len(archive)) != (
        evidence["artifact_sha256"],
        evidence["artifact_size_bytes"],
    ):
        raise _error("preserved V2 qualification artifact archive identity changed")

    try:
        with zipfile.ZipFile(io.BytesIO(archive), "r") as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)):
                raise _error("preserved V2 qualification artifact has duplicate members")
            if PROJECTION_MEMBER not in names or QUALIFICATION_RECEIPT_MEMBER not in names:
                raise _error("preserved V2 qualification artifact is missing reviewed members")
            projection = bundle.read(PROJECTION_MEMBER)
            receipt_raw = bundle.read(QUALIFICATION_RECEIPT_MEMBER)
    except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise _error("preserved V2 qualification artifact is not a readable exact ZIP") from exc

    if (hashlib.sha256(projection).hexdigest(), len(projection)) != (
        evidence["projection_sha256"],
        evidence["projection_size_bytes"],
    ):
        raise _error("preserved V2 qualification projection identity changed")
    if len(projection.splitlines()) != evidence["record_count"]:
        raise _error("preserved V2 qualification projection row count changed")

    try:
        receipt = json.loads(receipt_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("preserved V2 qualification receipt is malformed") from exc
    if not isinstance(receipt, dict) or _canonical(receipt) != receipt_raw:
        raise _error("preserved V2 qualification receipt is not exact canonical JSON")
    if receipt.get("qualification_status") != QUALIFICATION_STATUS:
        raise _error("preserved V2 qualification status changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("preserved V2 qualification state changed")

    projection_receipt = receipt.get("projection")
    if not isinstance(projection_receipt, dict):
        raise _error("preserved V2 qualification projection receipt is missing")
    exact_projection_fields = {
        "record_count": evidence["record_count"],
        "unique_fixture_count": evidence["unique_fixture_count"],
        "same_kickoff_group_count": evidence["same_kickoff_group_count"],
        "identity_or_lineage_conflict_count": evidence[
            "identity_or_lineage_conflict_count"
        ],
        "sha256": evidence["projection_sha256"],
        "size_bytes": evidence["projection_size_bytes"],
    }
    for field, expected in exact_projection_fields.items():
        if projection_receipt.get(field) != expected:
            raise _error(f"preserved V2 qualification receipt {field} changed")
    if projection_receipt.get("identity_or_lineage_conflicts") != []:
        raise _error("preserved V2 qualification receipt gained lineage conflicts")

    freshness = receipt.get("historical_live_data_freshness")
    if (
        not isinstance(freshness, dict)
        or freshness.get("status") != FRESHNESS_STATUS
        or freshness.get("numeric_value_produced") is not False
        or freshness.get("training_feature_authorized") is not False
    ):
        raise _error("preserved V2 historical freshness semantics changed")
    safety = receipt.get("safety")
    if (
        not isinstance(safety, dict)
        or not safety
        or any(type(flag) is not bool or flag is not False for flag in safety.values())
    ):
        raise _error("preserved V2 qualification receipt grants downstream authority")

    receipt_identity = {
        "member": QUALIFICATION_RECEIPT_MEMBER,
        "sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "size_bytes": len(receipt_raw),
        "qualification_status": QUALIFICATION_STATUS,
        "qualification_state": QUALIFICATION_STATE,
    }
    return projection, receipt_identity


def _append_execution_evidence(
    receipt: dict,
    *,
    artifact_receipt: dict,
) -> dict:
    """Add archive ancestry and explicit per-arm membership reconciliation."""
    protocol = pr140.build_fotmob_utc_native_expected_goals_model_validation_protocol()
    evidence = protocol["v2_success_evidence"]
    membership = receipt.get("input_projection", {}).get("membership")
    if not isinstance(membership, dict):
        raise _error("validation receipt common membership is missing")
    required_populations = (
        "train",
        "evaluation_a",
        "evaluation_b",
        "pooled_evaluation",
    )
    if any(key not in membership for key in required_populations):
        raise _error("validation receipt common membership is incomplete")

    populations = receipt.get("evaluation", {}).get("populations")
    if not isinstance(populations, dict):
        raise _error("validation receipt evaluation populations are missing")
    population_name_map = {
        "evaluation_a": "EVALUATION_A",
        "evaluation_b": "EVALUATION_B_TERMINAL",
        "pooled_evaluation": "POOLED_A_PLUS_B",
    }
    for membership_name, evaluation_name in population_name_map.items():
        expected_count = membership[membership_name]["count"]
        population = populations.get(evaluation_name)
        if not isinstance(population, dict):
            raise _error("validation receipt evaluation population changed")
        models = population.get("models")
        if not isinstance(models, dict) or set(models) != set(MODEL_IDS):
            raise _error("validation receipt model-arm population changed")
        if any(model.get("fixture_count") != expected_count for model in models.values()):
            raise _error("model-arm membership count differs from frozen common population")

    arm_membership = {
        model_id: {
            population: dict(membership[population])
            for population in required_populations
        }
        for model_id in MODEL_IDS
    }
    receipt["source_evidence"] = {
        "artifact_id": evidence["artifact_id"],
        "artifact_name": evidence["artifact_name"],
        "artifact_sha256": evidence["artifact_sha256"],
        "artifact_size_bytes": evidence["artifact_size_bytes"],
        "qualification_run_id": evidence["run_id"],
        "qualification_result_comment_id": evidence["result_comment_id"],
        "projection_member": PROJECTION_MEMBER,
        "projection_sha256": evidence["projection_sha256"],
        "projection_size_bytes": evidence["projection_size_bytes"],
        "projection_record_count": evidence["record_count"],
        "qualification_receipt": artifact_receipt,
    }
    receipt["arm_membership"] = arm_membership
    receipt["automatic_model_approval"] = False
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the reviewed offline UTC-native expected-goals model validation "
            "from the exact preserved V2 artifact. No network, ScoreMatrix, pricing, "
            "selection, or BET behavior is performed."
        )
    )
    parser.add_argument(
        "artifact_zip",
        type=Path,
        help="Exact preserved V2 feature-qualification artifact ZIP",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        required=True,
        help="Path for hash-sealed evaluation prediction NDJSON",
    )
    parser.add_argument(
        "--receipt-output",
        type=Path,
        required=True,
        help="Path for canonical validation receipt JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    projection_raw, artifact_receipt = _validated_artifact(args.artifact_zip)
    with tempfile.TemporaryDirectory(prefix="athena-xg-validation-") as temp:
        projection = Path(temp) / PROJECTION_MEMBER
        projection.write_bytes(projection_raw)
        receipt, predictions = build_validation(
            projection,
            predictions_output=args.predictions_output,
        )
    receipt = _append_execution_evidence(
        receipt,
        artifact_receipt=artifact_receipt,
    )
    receipt_raw = canonical_validation_receipt_bytes(receipt)
    args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_output.write_bytes(receipt_raw)
    summary = {
        "validation_state": receipt["validation_state"],
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "receipt_size_bytes": len(receipt_raw),
        "predictions_sha256": hashlib.sha256(predictions).hexdigest(),
        "predictions_size_bytes": len(predictions),
        "prediction_record_count": receipt["predictions"]["record_count"],
        "next_required_boundary": receipt["next_required_boundary"],
        "safety": receipt["safety"],
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
