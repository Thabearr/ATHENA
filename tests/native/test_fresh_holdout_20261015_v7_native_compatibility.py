"""Cross-platform source identity and offline V7 compatibility regression."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from domain import fotmob_data_matches_capture as capture_contract
from domain import fotmob_fresh_holdout_capture_qualification_adapter as adapter


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIRECTORY = (
    ROOT
    / "tests"
    / "fixtures"
    / "fotmob_fresh_holdout_20261015"
)
PROJECTION_PATH = FIXTURE_DIRECTORY / "afc-cl2-9469-20261015-wrappers.json"
ORIGINAL_MANIFEST_PATH = (
    FIXTURE_DIRECTORY / "7d46b089a3363f67e42f5fdc-manifest.json"
)

PROJECTION_SHA256 = "e0e824e8c8688209bcb6452e3694b20b2f1d780a795a9524f8b17493e228651d"
ORIGINAL_MANIFEST_SHA256 = "e6a794624b0c13ce1572003fe70789238d9b99e05c6594bb81215deeff0467fd"
ORIGINAL_RAW_SHA256 = "4a51a979fe4c76903e8a652685b5d06dd0fe7cb7417d19ce59f44e870dce3868"
ORIGINAL_OBSERVED_AT = "2026-10-15T04:54:59.097819Z"
EXPECTED_FIXTURE_IDS = (
    6_054_752,
    6_054_846,
    6_054_753,
    6_054_834,
    6_054_835,
    6_054_847,
)


def _canonical_checkout_bytes(path: Path) -> bytes:
    """Normalize checkout line endings to the committed LF text identity."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _original_manifest() -> tuple[bytes, capture_contract.FotMobDataMatchesCaptureManifest]:
    raw = _canonical_checkout_bytes(ORIGINAL_MANIFEST_PATH)
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL_MANIFEST_SHA256
    parsed = capture_contract.manifest_from_mapping(
        capture_contract.strict_manifest_json_loads(raw)
    )
    assert capture_contract.canonical_data_matches_capture_manifest_bytes(parsed) == raw
    assert parsed.raw_sha256 == ORIGINAL_RAW_SHA256
    assert capture_contract.serialize_utc(parsed.observed_at) == ORIGINAL_OBSERVED_AT
    return raw, parsed


def _derived_manifest(
    raw: bytes,
    source: capture_contract.FotMobDataMatchesCaptureManifest,
    *,
    request_date: str = "20261015",
) -> capture_contract.FotMobDataMatchesCaptureManifest:
    # This is a deterministic in-memory contract for the projection bytes. It
    # does not claim that these bytes are the original response or that a
    # provider was contacted.
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=source.status,
        content_type=source.content_type,
        content_length=len(raw),
        body=raw,
        observed_at=source.observed_at,
        network_acquisition_performed=True,
    )
    return capture_contract.build_data_matches_capture_manifest(
        response,
        request_date=request_date,
        timezone=source.timezone,
        ccode3=source.ccode3,
    )


def test_20261015_projection_and_original_manifest_keep_separate_identity() -> None:
    original_manifest_raw, original_manifest = _original_manifest()
    projection_raw = _canonical_checkout_bytes(PROJECTION_PATH)
    assert hashlib.sha256(projection_raw).hexdigest() == PROJECTION_SHA256

    projection = json.loads(projection_raw.decode("utf-8"))
    wrappers = [row for row in projection["leagues"] if row.get("id") == 9469]
    assert len(wrappers) == 3
    assert {row["groupName"] for row in wrappers} == {"F", "G", "H"}

    derived_manifest = _derived_manifest(projection_raw, original_manifest)
    derived_manifest_sha256 = capture_contract.sha256_data_matches_capture_manifest(
        derived_manifest
    )
    assert derived_manifest.raw_sha256 == PROJECTION_SHA256
    assert derived_manifest.raw_sha256 != original_manifest.raw_sha256
    assert derived_manifest_sha256 != hashlib.sha256(original_manifest_raw).hexdigest()

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="raw capture size",
    ):
        adapter.qualify_capture_fixtures(projection_raw, original_manifest)

    qualified = adapter.qualify_capture_fixtures(projection_raw, derived_manifest)
    assert tuple(row.fixture_id for row in qualified) == EXPECTED_FIXTURE_IDS
    assert {row.wrapper_id for row in qualified} == {9469}
    assert {row.provider_primary_id for row in qualified} == {9469}
    assert {row.capture_raw_sha256 for row in qualified} == {PROJECTION_SHA256}
    assert {row.capture_manifest_sha256 for row in qualified} == {
        derived_manifest_sha256
    }
    assert all(row.capture_raw_sha256 != ORIGINAL_RAW_SHA256 for row in qualified)
    assert all(
        row.capture_manifest_sha256 != ORIGINAL_MANIFEST_SHA256
        for row in qualified
    )


def test_20261015_projection_cannot_be_admitted_for_a_nearby_request_date() -> None:
    _, original_manifest = _original_manifest()
    projection_raw = _canonical_checkout_bytes(PROJECTION_PATH)
    nearby_manifest = _derived_manifest(
        projection_raw, original_manifest, request_date="20261016"
    )

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="escaped exact request date",
    ):
        adapter.qualify_capture_fixtures(projection_raw, nearby_manifest)
