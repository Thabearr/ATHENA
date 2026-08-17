"""Source-bound execution gate for the reviewed UTC-native xG validation.

The lower-level validator can evaluate an already verified projection for
synthetic/structural testing. This module is the only reviewed source-bound
entrypoint: it revalidates the exact preserved V2 artifact archive and canonical
qualification receipt before any research fitting is permitted, then augments
the result with explicit artifact ancestry and per-arm membership proof.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping
import zipfile

import domain.fotmob_utc_native_expected_goals_model_validation as evaluator
import domain.fotmob_utc_native_expected_goals_model_validation_protocol as pr140


SOURCE_BOUND_ID = "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_SOURCE_BOUND_V1"
PROJECTION_MEMBER = "utc-native-feature-projection-v2.ndjson"
QUALIFICATION_RECEIPT_MEMBER = "qualification-v2-receipt.json"
QUALIFICATION_STATUS = "QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION"
QUALIFICATION_STATE = (
    "EXECUTED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_MODEL_USE_UNREVIEWED"
)
QUALIFICATION_NEXT_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL"
)
QUALIFICATION_PROTOCOL_SHA256 = (
    "b3cc9a8e5ca05f199b7e404fa8288074e77d76fa5f21224c5bddb48ca1aac411"
)
QUALIFICATION_PROTOCOL_SIZE = 5_809
FRESHNESS_STATUS = "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"


Error = evaluator.FotMobUTCNativeExpectedGoalsModelValidationError


def _error(message: str) -> Error:
    return Error(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("source-bound canonical serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _hex_sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise _error(f"{label} must be exact lowercase SHA-256")
    return value


def _verified_qualification_receipt(
    receipt_raw: bytes,
    *,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        receipt = json.loads(receipt_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("preserved V2 qualification receipt is malformed") from exc
    if not isinstance(receipt, dict) or _canonical(receipt) != receipt_raw:
        raise _error("preserved V2 qualification receipt is not exact canonical JSON")
    if receipt.get("schema_version") != 1:
        raise _error("preserved V2 qualification receipt schema changed")
    if receipt.get("qualification_status") != QUALIFICATION_STATUS:
        raise _error("preserved V2 qualification status changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("preserved V2 qualification state changed")
    if receipt.get("next_required_boundary") != QUALIFICATION_NEXT_BOUNDARY:
        raise _error("preserved V2 qualification next boundary changed")
    if receipt.get("protocol_sha256") != QUALIFICATION_PROTOCOL_SHA256:
        raise _error("preserved V2 qualification protocol SHA changed")
    if receipt.get("protocol_size_bytes") != QUALIFICATION_PROTOCOL_SIZE:
        raise _error("preserved V2 qualification protocol size changed")

    time_basis = receipt.get("time_basis")
    if (
        not isinstance(time_basis, dict)
        or time_basis.get("coordinate") != "STATUS_UTCTIME_AWARE_UTC"
        or time_basis.get("source_local_parity_claimed") is not False
        or time_basis.get("timezone_conversion_used") is not False
    ):
        raise _error("preserved V2 qualification UTC time-basis semantics changed")

    projection = receipt.get("projection")
    if not isinstance(projection, dict):
        raise _error("preserved V2 qualification projection receipt is missing")
    exact_projection = {
        "record_count": evidence["record_count"],
        "unique_fixture_count": evidence["unique_fixture_count"],
        "same_kickoff_group_count": evidence["same_kickoff_group_count"],
        "identity_or_lineage_conflict_count": evidence[
            "identity_or_lineage_conflict_count"
        ],
        "sha256": evidence["projection_sha256"],
        "size_bytes": evidence["projection_size_bytes"],
    }
    for field, expected in exact_projection.items():
        if projection.get(field) != expected:
            raise _error(f"preserved V2 qualification receipt {field} changed")
    if projection.get("identity_or_lineage_conflicts") != []:
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
        or set(safety) != set(pr140.SAFETY_KEYS)
        or any(type(flag) is not bool or flag is not False for flag in safety.values())
    ):
        raise _error("preserved V2 qualification receipt safety boundary changed")
    return receipt


def verified_projection_from_artifact(
    artifact: Path,
) -> tuple[bytes, dict[str, Any]]:
    """Reconcile the exact preserved V2 ZIP and return its verified projection."""
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
            infos = bundle.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise _error("preserved V2 qualification artifact has duplicate members")
            if PROJECTION_MEMBER not in names or QUALIFICATION_RECEIPT_MEMBER not in names:
                raise _error("preserved V2 qualification artifact is missing reviewed members")
            corrupt = bundle.testzip()
            if corrupt is not None:
                raise _error(f"preserved V2 qualification artifact member failed CRC: {corrupt}")
            projection = bundle.read(PROJECTION_MEMBER)
            receipt_raw = bundle.read(QUALIFICATION_RECEIPT_MEMBER)
    except Error:
        raise
    except (zipfile.BadZipFile, KeyError, RuntimeError, OSError) as exc:
        raise _error("preserved V2 qualification artifact is not a readable exact ZIP") from exc

    if (hashlib.sha256(projection).hexdigest(), len(projection)) != (
        evidence["projection_sha256"],
        evidence["projection_size_bytes"],
    ):
        raise _error("preserved V2 qualification projection identity changed")
    if len(projection.splitlines()) != evidence["record_count"]:
        raise _error("preserved V2 qualification projection row count changed")

    receipt = _verified_qualification_receipt(receipt_raw, evidence=evidence)
    identity = {
        "member": QUALIFICATION_RECEIPT_MEMBER,
        "sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "size_bytes": len(receipt_raw),
        "qualification_status": receipt["qualification_status"],
        "qualification_state": receipt["qualification_state"],
        "qualification_protocol_sha256": receipt["protocol_sha256"],
        "qualification_protocol_size_bytes": receipt["protocol_size_bytes"],
    }
    return projection, identity


def _membership_entry(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(f"{label} membership receipt must be an object")
    count = value.get("count")
    digest = value.get("membership_sha256")
    if type(count) is not int or count <= 0:
        raise _error(f"{label} membership count is invalid")
    return {
        "count": count,
        "membership_sha256": _hex_sha256(digest, f"{label} membership digest"),
    }


def _arm_membership_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    input_projection = receipt.get("input_projection")
    if not isinstance(input_projection, Mapping):
        raise _error("validation receipt input projection is missing")
    common = input_projection.get("membership")
    if not isinstance(common, Mapping):
        raise _error("validation receipt common membership is missing")

    train = _membership_entry(common.get("train"), "train")
    evaluation = {
        "evaluation_a": _membership_entry(common.get("evaluation_a"), "evaluation_a"),
        "evaluation_b": _membership_entry(common.get("evaluation_b"), "evaluation_b"),
        "pooled_evaluation": _membership_entry(
            common.get("pooled_evaluation"), "pooled_evaluation"
        ),
    }

    evaluation_payload = receipt.get("evaluation")
    if not isinstance(evaluation_payload, Mapping):
        raise _error("validation receipt evaluation is missing")
    populations = evaluation_payload.get("populations")
    if not isinstance(populations, Mapping):
        raise _error("validation receipt evaluation populations are missing")
    population_map = {
        "evaluation_a": "EVALUATION_A",
        "evaluation_b": "EVALUATION_B_TERMINAL",
        "pooled_evaluation": "POOLED_A_PLUS_B",
    }
    for common_name, evaluation_name in population_map.items():
        population = populations.get(evaluation_name)
        if not isinstance(population, Mapping):
            raise _error("validation receipt evaluation population changed")
        models = population.get("models")
        if not isinstance(models, Mapping) or set(models) != set(evaluator.MODEL_IDS):
            raise _error("validation receipt model-arm population changed")
        expected_count = evaluation[common_name]["count"]
        for model_id, model in models.items():
            if not isinstance(model, Mapping) or model.get("fixture_count") != expected_count:
                raise _error(
                    f"{model_id} membership count differs from frozen common population"
                )

    result: dict[str, Any] = {}
    for model_id in evaluator.MODEL_IDS:
        result[model_id] = {
            "fit_membership": (
                None
                if model_id == "HISTORICAL_FIXED_COEFFICIENT_TRANSFER"
                else dict(train)
            ),
            **{key: dict(value) for key, value in evaluation.items()},
        }
    return result


def build_source_bound_validation(
    artifact: Path,
    *,
    predictions_output: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Execute the reviewed source-bound study only from the exact V2 artifact."""
    protocol = pr140.build_fotmob_utc_native_expected_goals_model_validation_protocol()
    evidence = protocol["v2_success_evidence"]
    projection_raw, qualification_receipt = verified_projection_from_artifact(artifact)

    with tempfile.TemporaryDirectory(prefix="athena-xg-validation-") as temp:
        projection = Path(temp) / PROJECTION_MEMBER
        projection.write_bytes(projection_raw)
        receipt, predictions = evaluator.build_validation(
            projection,
            predictions_output=predictions_output,
        )

    receipt["source_bound_id"] = SOURCE_BOUND_ID
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
        "qualification_receipt": qualification_receipt,
    }
    receipt["arm_membership"] = _arm_membership_receipt(receipt)
    receipt["automatic_model_approval"] = False
    return receipt, predictions


def canonical_source_bound_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    """Canonicalize only receipts that retain the reviewed all-false authority map."""
    if receipt.get("source_bound_id") != SOURCE_BOUND_ID:
        raise _error("source-bound validation receipt identity changed")
    if receipt.get("automatic_model_approval") is not False:
        raise _error("source-bound validation may not auto-approve a model")
    if not isinstance(receipt.get("source_evidence"), Mapping):
        raise _error("source-bound validation receipt lacks artifact ancestry")
    if not isinstance(receipt.get("arm_membership"), Mapping):
        raise _error("source-bound validation receipt lacks per-arm membership")
    return evaluator.canonical_validation_receipt_bytes(receipt)


__all__ = [
    "FRESHNESS_STATUS",
    "PROJECTION_MEMBER",
    "QUALIFICATION_RECEIPT_MEMBER",
    "QUALIFICATION_STATE",
    "QUALIFICATION_STATUS",
    "SOURCE_BOUND_ID",
    "build_source_bound_validation",
    "canonical_source_bound_receipt_bytes",
    "verified_projection_from_artifact",
]
