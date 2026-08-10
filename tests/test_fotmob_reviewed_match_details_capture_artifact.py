from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_capture import (
    CapturedFotMobReviewedMatchDetailsResponse,
    build_reviewed_match_details_raw_capture,
    canonical_reviewed_match_details_capture_manifest_bytes,
)
from domain.fotmob_reviewed_match_details_capture_artifact import (
    DATASET_NAME,
    FotMobReviewedMatchDetailsCaptureArtifact,
    FotMobReviewedMatchDetailsCaptureArtifactError,
    build_reviewed_match_details_capture_artifact,
    revalidate_reviewed_match_details_capture_artifact,
)
from domain.fotmob_reviewed_match_details_probe import (
    build_match_details_probe_plan,
    canonical_match_details_probe_plan_bytes,
)


def _capture(tmp_path: Path):
    helper = Path(__file__).with_name(
        "test_reviewed_fixture_intelligence_bootstrap_artifact.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr48_artifact_helper", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #48 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, _, verified = module._verified(tmp_path)
    request_at = module.PR48_VERIFIED_AT
    plan = build_match_details_probe_plan(
        verified,
        module.canonical_verified_bootstrap_artifact_receipt_bytes(verified),
        fixture_identifier="FOTMOB:1001",
        request_started_at=request_at,
    )
    plan_bytes = canonical_match_details_probe_plan_bytes(plan)
    body = b'{"opaque":"still-unreviewed"}'
    response = CapturedFotMobReviewedMatchDetailsResponse(
        status=200,
        content_type="application/json",
        content_length=len(body),
        body=body,
        observed_at=request_at,
        network_acquisition_performed=False,
    )
    return build_reviewed_match_details_raw_capture(
        plan=plan,
        plan_bytes=plan_bytes,
        response=response,
    )


def test_artifact_freezes_exact_manifest_bytes_and_hash(tmp_path: Path) -> None:
    capture = _capture(tmp_path)
    artifact = build_reviewed_match_details_capture_artifact(capture)

    assert DATASET_NAME == "athena-fotmob-reviewed-match-details-capture-artifact-v1"
    assert type(artifact) is FotMobReviewedMatchDetailsCaptureArtifact
    expected = canonical_reviewed_match_details_capture_manifest_bytes(capture.manifest)
    assert artifact.manifest_bytes == expected
    assert artifact.manifest_sha256 == hashlib.sha256(expected).hexdigest()
    assert artifact.raw_sha256 == capture.manifest.raw_sha256
    assert artifact.raw_size == len(capture.raw_bytes)
    assert revalidate_reviewed_match_details_capture_artifact(artifact) == artifact


def test_nested_manifest_mutation_cannot_redefine_historical_manifest_bytes(tmp_path: Path) -> None:
    artifact = build_reviewed_match_details_capture_artifact(_capture(tmp_path))
    historical = artifact.manifest_bytes

    object.__setattr__(artifact.capture.manifest, "fixture_identifier", "FOTMOB:9999")
    assert artifact.manifest_bytes == historical
    with pytest.raises(
        FotMobReviewedMatchDetailsCaptureArtifactError,
        match="raw capture failed current exact revalidation",
    ):
        revalidate_reviewed_match_details_capture_artifact(artifact)


def test_nested_raw_bytes_mutation_cannot_redefine_historical_manifest_bytes(tmp_path: Path) -> None:
    artifact = build_reviewed_match_details_capture_artifact(_capture(tmp_path))
    historical = artifact.manifest_bytes

    object.__setattr__(artifact.capture, "raw_bytes", b"tampered")
    assert artifact.manifest_bytes == historical
    with pytest.raises(
        FotMobReviewedMatchDetailsCaptureArtifactError,
        match="raw capture failed current exact revalidation",
    ):
        revalidate_reviewed_match_details_capture_artifact(artifact)


def test_changed_manifest_bytes_hash_raw_hash_or_size_fail_closed(tmp_path: Path) -> None:
    artifact = build_reviewed_match_details_capture_artifact(_capture(tmp_path))

    with pytest.raises(FotMobReviewedMatchDetailsCaptureArtifactError, match="manifest_bytes"):
        dataclasses.replace(artifact, manifest_bytes=artifact.manifest_bytes + b"\n")
    with pytest.raises(FotMobReviewedMatchDetailsCaptureArtifactError, match="manifest_sha256"):
        dataclasses.replace(artifact, manifest_sha256="f" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsCaptureArtifactError, match="raw_sha256"):
        dataclasses.replace(artifact, raw_sha256="f" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsCaptureArtifactError, match="raw_size"):
        dataclasses.replace(artifact, raw_size=artifact.raw_size + 1)
