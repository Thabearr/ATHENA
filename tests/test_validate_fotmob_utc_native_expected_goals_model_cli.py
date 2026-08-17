from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

import scripts.validate_fotmob_utc_native_expected_goals_model as cli


def _canonical(value):
    return cli._canonical(value)


def _fixture_artifact():
    projection = b"{}\n"
    projection_sha = hashlib.sha256(projection).hexdigest()
    receipt = {
        "schema_version": 1,
        "qualification_status": cli.QUALIFICATION_STATUS,
        "qualification_state": cli.QUALIFICATION_STATE,
        "projection": {
            "record_count": 1,
            "unique_fixture_count": 1,
            "same_kickoff_group_count": 0,
            "identity_or_lineage_conflict_count": 0,
            "identity_or_lineage_conflicts": [],
            "sha256": projection_sha,
            "size_bytes": len(projection),
        },
        "historical_live_data_freshness": {
            "status": cli.FRESHNESS_STATUS,
            "numeric_value_produced": False,
            "training_feature_authorized": False,
        },
        "safety": {"bet_authorized": False},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr(cli.PROJECTION_MEMBER, projection)
        bundle.writestr(cli.QUALIFICATION_RECEIPT_MEMBER, _canonical(receipt))
    archive = buffer.getvalue()
    evidence = {
        "artifact_id": 1,
        "artifact_name": "synthetic-reviewed-v2",
        "artifact_sha256": hashlib.sha256(archive).hexdigest(),
        "artifact_size_bytes": len(archive),
        "run_id": 2,
        "result_comment_id": 3,
        "projection_sha256": projection_sha,
        "projection_size_bytes": len(projection),
        "record_count": 1,
        "unique_fixture_count": 1,
        "same_kickoff_group_count": 0,
        "identity_or_lineage_conflict_count": 0,
    }
    return archive, projection, evidence


def test_artifact_gate_revalidates_archive_receipt_and_projection(tmp_path, monkeypatch):
    archive, projection, evidence = _fixture_artifact()
    monkeypatch.setattr(
        cli.pr140,
        "build_fotmob_utc_native_expected_goals_model_validation_protocol",
        lambda: {"v2_success_evidence": evidence},
    )
    path = tmp_path / "artifact.zip"
    path.write_bytes(archive)
    actual, receipt_identity = cli._validated_artifact(path)
    assert actual == projection
    assert receipt_identity["qualification_status"] == cli.QUALIFICATION_STATUS
    assert receipt_identity["qualification_state"] == cli.QUALIFICATION_STATE
    assert receipt_identity["size_bytes"] > 0


def test_artifact_gate_rejects_archive_drift_before_projection_use(tmp_path, monkeypatch):
    archive, _, evidence = _fixture_artifact()
    monkeypatch.setattr(
        cli.pr140,
        "build_fotmob_utc_native_expected_goals_model_validation_protocol",
        lambda: {"v2_success_evidence": evidence},
    )
    path = tmp_path / "artifact.zip"
    path.write_bytes(archive + b"drift")
    with pytest.raises(
        cli.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="archive identity changed",
    ):
        cli._validated_artifact(path)


def _base_receipt(count=4):
    membership = {
        "all_complete": {"count": 10, "membership_sha256": "a" * 64},
        "train": {"count": 6, "membership_sha256": "b" * 64},
        "evaluation_a": {"count": count, "membership_sha256": "c" * 64},
        "evaluation_b": {"count": count, "membership_sha256": "d" * 64},
        "pooled_evaluation": {"count": count * 2, "membership_sha256": "e" * 64},
    }
    populations = {}
    for name, expected in (
        ("EVALUATION_A", count),
        ("EVALUATION_B_TERMINAL", count),
        ("POOLED_A_PLUS_B", count * 2),
    ):
        populations[name] = {
            "models": {
                model_id: {"fixture_count": expected}
                for model_id in cli.MODEL_IDS
            }
        }
    return {
        "input_projection": {"membership": membership},
        "evaluation": {"populations": populations},
    }


def test_final_receipt_explicitly_repeats_exact_common_membership_for_every_arm(monkeypatch):
    evidence = {
        "artifact_id": 1,
        "artifact_name": "synthetic-reviewed-v2",
        "artifact_sha256": "1" * 64,
        "artifact_size_bytes": 10,
        "run_id": 2,
        "result_comment_id": 3,
        "projection_sha256": "2" * 64,
        "projection_size_bytes": 8,
        "record_count": 1,
    }
    monkeypatch.setattr(
        cli.pr140,
        "build_fotmob_utc_native_expected_goals_model_validation_protocol",
        lambda: {"v2_success_evidence": evidence},
    )
    receipt = cli._append_execution_evidence(
        _base_receipt(),
        artifact_receipt={"sha256": "3" * 64, "size_bytes": 5},
    )
    assert set(receipt["arm_membership"]) == set(cli.MODEL_IDS)
    first = receipt["arm_membership"][cli.MODEL_IDS[0]]
    assert all(receipt["arm_membership"][model] == first for model in cli.MODEL_IDS)
    assert receipt["automatic_model_approval"] is False
    assert receipt["source_evidence"]["artifact_id"] == 1


def test_final_receipt_fails_if_any_arm_count_differs_from_common_population(monkeypatch):
    evidence = {
        "artifact_id": 1,
        "artifact_name": "synthetic-reviewed-v2",
        "artifact_sha256": "1" * 64,
        "artifact_size_bytes": 10,
        "run_id": 2,
        "result_comment_id": 3,
        "projection_sha256": "2" * 64,
        "projection_size_bytes": 8,
        "record_count": 1,
    }
    monkeypatch.setattr(
        cli.pr140,
        "build_fotmob_utc_native_expected_goals_model_validation_protocol",
        lambda: {"v2_success_evidence": evidence},
    )
    receipt = _base_receipt()
    receipt["evaluation"]["populations"]["EVALUATION_A"]["models"][
        cli.MODEL_IDS[2]
    ]["fixture_count"] = 999
    with pytest.raises(
        cli.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="membership count differs",
    ):
        cli._append_execution_evidence(
            receipt,
            artifact_receipt={"sha256": "3" * 64, "size_bytes": 5},
        )
