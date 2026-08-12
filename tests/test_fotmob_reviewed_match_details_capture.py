from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_capture import (
    DATASET_NAME,
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    CapturedFotMobReviewedMatchDetailsResponse,
    FotMobReviewedMatchDetailsCaptureError,
    FotMobReviewedMatchDetailsRawCapture,
    build_reviewed_match_details_raw_capture,
    canonical_reviewed_match_details_capture_manifest_bytes,
    reviewed_match_details_capture_identifier,
    sha256_reviewed_match_details_capture_manifest,
)
from domain.fotmob_reviewed_match_details_probe import (
    build_match_details_probe_plan,
    canonical_match_details_probe_plan_bytes,
)
from domain.reviewed_fixture_catalog_admission import REVIEWED_SOURCE_CAPABILITY
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY
from tests.support.module_loader import load_test_module

UTC = datetime.timezone.utc
REQUEST_AT = datetime.datetime(2026, 8, 10, 6, 0, tzinfo=UTC)
OBSERVED_AT = datetime.datetime(2026, 8, 10, 6, 0, 2, tzinfo=UTC)
KICKOFF = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _upstream(tmp_path: Path):
    module = load_test_module("test_reviewed_fixture_intelligence_bootstrap_artifact")
    _, receipt_bytes, verified = module._verified(tmp_path)
    plan = build_match_details_probe_plan(
        verified,
        module.canonical_verified_bootstrap_artifact_receipt_bytes(verified),
        fixture_identifier="FOTMOB:1001",
        request_started_at=REQUEST_AT,
    )
    plan_bytes = canonical_match_details_probe_plan_bytes(plan)
    return plan, plan_bytes


def _response(
    *,
    body: bytes = b'{"still":"unreviewed"}',
    observed_at: datetime.datetime = OBSERVED_AT,
    network_acquisition_performed: bool = True,
    content_type: str = "application/json; charset=utf-8",
    content_length=None,
):
    if content_length is None:
        content_length = len(body)
    return CapturedFotMobReviewedMatchDetailsResponse(
        status=200,
        content_type=content_type,
        content_length=content_length,
        body=body,
        observed_at=observed_at,
        network_acquisition_performed=network_acquisition_performed,
    )


def test_exact_pr49_plan_and_full_raw_bytes_build_capture(tmp_path: Path) -> None:
    plan, plan_bytes = _upstream(tmp_path)
    response = _response()
    capture = build_reviewed_match_details_raw_capture(
        plan=plan,
        plan_bytes=plan_bytes,
        response=response,
    )

    assert DATASET_NAME == "athena-fotmob-reviewed-match-details-capture-v1"
    assert RAW_FILENAME == "response.json"
    assert MANIFEST_FILENAME == "manifest.json"
    assert type(capture) is FotMobReviewedMatchDetailsRawCapture
    assert capture.raw_bytes == response.body
    assert capture.manifest.fixture_identifier == "FOTMOB:1001"
    assert capture.manifest.source_match_id == "1001"
    assert capture.manifest.kickoff == KICKOFF
    assert capture.manifest.request_started_at == REQUEST_AT
    assert capture.manifest.observed_at == OBSERVED_AT
    assert capture.manifest.plan_bytes == plan_bytes
    assert capture.manifest.plan_sha256 == hashlib.sha256(plan_bytes).hexdigest()
    assert capture.manifest.raw_sha256 == hashlib.sha256(response.body).hexdigest()
    assert capture.manifest.raw_size == len(response.body)
    assert capture.manifest.network_acquisition_performed is True
    assert all(value is False for value in capture.manifest.safety.values())


def test_manifest_is_canonical_deterministic_and_does_not_embed_raw_body(tmp_path: Path) -> None:
    plan, plan_bytes = _upstream(tmp_path)
    response = _response(body=b'{"opaque":"raw-football-bytes"}')
    capture = build_reviewed_match_details_raw_capture(
        plan=plan,
        plan_bytes=plan_bytes,
        response=response,
    )
    first = canonical_reviewed_match_details_capture_manifest_bytes(capture.manifest)
    second = canonical_reviewed_match_details_capture_manifest_bytes(capture.manifest)

    assert first == second
    assert first.endswith(b"\n")
    assert response.body not in first
    assert sha256_reviewed_match_details_capture_manifest(capture.manifest) == hashlib.sha256(
        first
    ).hexdigest()
    assert reviewed_match_details_capture_identifier(capture).startswith(
        "1001--20260810T060002000000Z--"
    )
    assert reviewed_match_details_capture_identifier(capture).endswith(
        capture.manifest.raw_sha256
    )


def test_changed_or_noncanonical_pr49_plan_bytes_fail_closed(tmp_path: Path) -> None:
    plan, plan_bytes = _upstream(tmp_path)
    for changed in (plan_bytes + b"\n", plan_bytes[:-1], b" " + plan_bytes):
        with pytest.raises(
            FotMobReviewedMatchDetailsCaptureError,
            match="exact canonical PR #49 plan bytes",
        ):
            build_reviewed_match_details_raw_capture(
                plan=plan,
                plan_bytes=changed,
                response=_response(),
            )


def test_mutated_plan_or_revoked_capability_fails_current_revalidation(tmp_path: Path) -> None:
    plan, plan_bytes = _upstream(tmp_path)
    object.__setattr__(plan, "source_match_id", "9999")
    with pytest.raises(
        FotMobReviewedMatchDetailsCaptureError,
        match="PR #49 request plan failed current exact revalidation",
    ):
        build_reviewed_match_details_raw_capture(
            plan=plan,
            plan_bytes=plan_bytes,
            response=_response(),
        )

    plan, plan_bytes = _upstream(tmp_path / "revoked")
    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
        original,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
    )
    try:
        with pytest.raises(
            FotMobReviewedMatchDetailsCaptureError,
            match="PR #49 request plan failed current exact revalidation",
        ):
            build_reviewed_match_details_raw_capture(
                plan=plan,
                plan_bytes=plan_bytes,
                response=_response(),
            )
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original


def test_capture_rejects_wrong_status_content_type_empty_or_mismatched_length() -> None:
    with pytest.raises(FotMobReviewedMatchDetailsCaptureError, match="exact integer 200"):
        CapturedFotMobReviewedMatchDetailsResponse(
            status=404,
            content_type="application/json",
            content_length=2,
            body=b"{}",
            observed_at=OBSERVED_AT,
            network_acquisition_performed=True,
        )
    with pytest.raises(FotMobReviewedMatchDetailsCaptureError, match="application/json"):
        _response(content_type="text/html")
    with pytest.raises(FotMobReviewedMatchDetailsCaptureError, match="must not be empty"):
        _response(body=b"", content_length=0)
    with pytest.raises(FotMobReviewedMatchDetailsCaptureError, match="does not match"):
        _response(body=b"{}", content_length=3)


def test_capture_rejects_oversize_body_without_parsing_it() -> None:
    with pytest.raises(FotMobReviewedMatchDetailsCaptureError, match="8 MiB"):
        _response(body=b"x" * (MAX_RESPONSE_BYTES + 1))


def test_observation_must_remain_before_kickoff_and_not_predate_request(tmp_path: Path) -> None:
    plan, plan_bytes = _upstream(tmp_path)
    for observed_at, message in (
        (REQUEST_AT - datetime.timedelta(microseconds=1), "must not predate"),
        (KICKOFF, "strictly before fixture kickoff"),
        (KICKOFF + datetime.timedelta(seconds=1), "strictly before fixture kickoff"),
    ):
        with pytest.raises(FotMobReviewedMatchDetailsCaptureError, match=message):
            build_reviewed_match_details_raw_capture(
                plan=plan,
                plan_bytes=plan_bytes,
                response=_response(observed_at=observed_at),
            )


def test_raw_capture_object_revalidates_raw_hash_size_and_manifest(tmp_path: Path) -> None:
    plan, plan_bytes = _upstream(tmp_path)
    capture = build_reviewed_match_details_raw_capture(
        plan=plan,
        plan_bytes=plan_bytes,
        response=_response(),
    )
    historical_manifest = canonical_reviewed_match_details_capture_manifest_bytes(
        capture.manifest
    )

    object.__setattr__(capture, "raw_bytes", b"tampered")
    assert canonical_reviewed_match_details_capture_manifest_bytes(capture.manifest) == (
        historical_manifest
    )
    with pytest.raises(FotMobReviewedMatchDetailsCaptureError, match="raw_bytes"):
        dataclasses.replace(capture)


def test_forced_manifest_hash_mutation_is_rejected_on_new_capture_use(tmp_path: Path) -> None:
    plan, plan_bytes = _upstream(tmp_path)
    capture = build_reviewed_match_details_raw_capture(
        plan=plan,
        plan_bytes=plan_bytes,
        response=_response(),
    )
    object.__setattr__(capture.manifest, "raw_sha256", "f" * 64)
    with pytest.raises(
        FotMobReviewedMatchDetailsCaptureError,
        match="raw_bytes SHA-256",
    ):
        dataclasses.replace(capture)


def test_contract_has_no_network_filesystem_or_downstream_semantic_imports() -> None:
    path = Path(__file__).resolve().parents[1] / "domain" / "fotmob_reviewed_match_details_capture.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
        "http.client",
        "requests",
        "curl_cffi",
        "playwright",
        "os",
        "pathlib",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
        "engine.prediction_engine",
    }
    assert not (imports & forbidden)
