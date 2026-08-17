from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

import domain.fotmob_utc_native_expected_goals_model_validation as evaluator
import domain.fotmob_utc_native_expected_goals_model_validation_source_bound as source_bound


def _fixture_artifact():
    projection = b"{}\n"
    projection_sha = hashlib.sha256(projection).hexdigest()
    safety = {key: False for key in sorted(source_bound.pr140.SAFETY_KEYS)}
    receipt = {
        "schema_version": 1,
        "qualification_status": source_bound.QUALIFICATION_STATUS,
        "qualification_state": source_bound.QUALIFICATION_STATE,
        "next_required_boundary": source_bound.QUALIFICATION_NEXT_BOUNDARY,
        "protocol_sha256": source_bound.QUALIFICATION_PROTOCOL_SHA256,
        "protocol_size_bytes": source_bound.QUALIFICATION_PROTOCOL_SIZE,
        "time_basis": {
            "coordinate": "STATUS_UTCTIME_AWARE_UTC",
            "source_local_parity_claimed": False,
            "timezone_conversion_used": False,
        },
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
            "status": source_bound.FRESHNESS_STATUS,
            "numeric_value_produced": False,
            "training_feature_authorized": False,
        },
        "safety": safety,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr(source_bound.PROJECTION_MEMBER, projection)
        bundle.writestr(
            source_bound.QUALIFICATION_RECEIPT_MEMBER,
            source_bound._canonical(receipt),
        )
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


def test_domain_source_bound_gate_revalidates_archive_receipt_and_projection(
    tmp_path, monkeypatch
):
    archive, projection, evidence = _fixture_artifact()
    monkeypatch.setattr(
        source_bound.pr140,
        "build_fotmob_utc_native_expected_goals_model_validation_protocol",
        lambda: {"v2_success_evidence": evidence},
    )
    path = tmp_path / "artifact.zip"
    path.write_bytes(archive)
    actual, receipt_identity = source_bound.verified_projection_from_artifact(path)
    assert actual == projection
    assert receipt_identity["qualification_status"] == source_bound.QUALIFICATION_STATUS
    assert receipt_identity["qualification_state"] == source_bound.QUALIFICATION_STATE
    assert receipt_identity["size_bytes"] > 0


def test_domain_source_bound_gate_rejects_archive_drift_before_projection_use(
    tmp_path, monkeypatch
):
    archive, _, evidence = _fixture_artifact()
    monkeypatch.setattr(
        source_bound.pr140,
        "build_fotmob_utc_native_expected_goals_model_validation_protocol",
        lambda: {"v2_success_evidence": evidence},
    )
    path = tmp_path / "artifact.zip"
    path.write_bytes(archive + b"drift")
    with pytest.raises(
        evaluator.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="archive identity changed",
    ):
        source_bound.verified_projection_from_artifact(path)


def test_domain_source_bound_gate_rejects_receipt_authority_drift(tmp_path, monkeypatch):
    archive, _, evidence = _fixture_artifact()
    buffer = io.BytesIO(archive)
    with zipfile.ZipFile(buffer, "r") as original:
        projection = original.read(source_bound.PROJECTION_MEMBER)
        receipt = __import__("json").loads(
            original.read(source_bound.QUALIFICATION_RECEIPT_MEMBER)
        )
    receipt["safety"]["bet_authorized"] = True
    rebuilt = io.BytesIO()
    with zipfile.ZipFile(rebuilt, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr(source_bound.PROJECTION_MEMBER, projection)
        bundle.writestr(
            source_bound.QUALIFICATION_RECEIPT_MEMBER,
            source_bound._canonical(receipt),
        )
    drifted = rebuilt.getvalue()
    evidence = dict(evidence)
    evidence["artifact_sha256"] = hashlib.sha256(drifted).hexdigest()
    evidence["artifact_size_bytes"] = len(drifted)
    monkeypatch.setattr(
        source_bound.pr140,
        "build_fotmob_utc_native_expected_goals_model_validation_protocol",
        lambda: {"v2_success_evidence": evidence},
    )
    path = tmp_path / "authority-drift.zip"
    path.write_bytes(drifted)
    with pytest.raises(
        evaluator.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="safety boundary changed",
    ):
        source_bound.verified_projection_from_artifact(path)


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
                for model_id in evaluator.MODEL_IDS
            }
        }
    return {
        "input_projection": {"membership": membership},
        "evaluation": {"populations": populations},
    }


def test_final_receipt_explicitly_repeats_exact_common_membership_for_every_arm():
    arms = source_bound._arm_membership_receipt(_base_receipt())
    assert set(arms) == set(evaluator.MODEL_IDS)
    for model_id, membership in arms.items():
        if model_id == "HISTORICAL_FIXED_COEFFICIENT_TRANSFER":
            assert membership["fit_membership"] is None
        else:
            assert membership["fit_membership"] == {
                "count": 6,
                "membership_sha256": "b" * 64,
            }
        assert membership["evaluation_a"]["count"] == 4
        assert membership["evaluation_b"]["count"] == 4
        assert membership["pooled_evaluation"]["count"] == 8


def test_final_receipt_fails_if_any_arm_count_differs_from_common_population():
    receipt = _base_receipt()
    receipt["evaluation"]["populations"]["EVALUATION_A"]["models"][
        evaluator.MODEL_IDS[2]
    ]["fixture_count"] = 999
    with pytest.raises(
        evaluator.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="membership count differs",
    ):
        source_bound._arm_membership_receipt(receipt)


def test_source_bound_receipt_requires_artifact_ancestry_and_no_auto_approval():
    receipt = {
        "source_bound_id": source_bound.SOURCE_BOUND_ID,
        "automatic_model_approval": False,
        "source_evidence": {"artifact_id": 1},
        "arm_membership": {"a": {}},
        "safety": {key: False for key in sorted(source_bound.pr140.SAFETY_KEYS)},
    }
    raw = source_bound.canonical_source_bound_receipt_bytes(receipt)
    assert raw.endswith(b"\n")
    receipt["automatic_model_approval"] = True
    with pytest.raises(
        evaluator.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="auto-approve",
    ):
        source_bound.canonical_source_bound_receipt_bytes(receipt)
