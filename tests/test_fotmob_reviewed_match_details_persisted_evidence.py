from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json

import pytest

from domain.fotmob_reviewed_match_details_capture import DATASET_NAME as CAPTURE_DATASET_NAME
from domain.fotmob_reviewed_match_details_persisted_evidence import (
    FotMobReviewedMatchDetailsPersistedEvidenceError,
    canonical_persisted_match_details_evidence_receipt_bytes,
    sha256_persisted_match_details_evidence_receipt,
    verify_persisted_match_details_evidence,
)

UTC = datetime.timezone.utc
RAW = b"not-yet-parsed-football-json"
SAFETY = {
    "network_transport_authorized": False,
    "filesystem_write_authorized": False,
    "response_body_parsing_authorized": False,
    "source_qualification_authorized": False,
    "football_semantics_authorized": False,
    "intelligence_fact_authorized": False,
    "intelligence_snapshot_authorized": False,
    "model_feature_authorized": False,
    "probability_authorized": False,
    "pricing_authorized": False,
    "selection_authorized": False,
    "bet_authorized": False,
}


def _payload(raw: bytes = RAW) -> dict:
    return {
        "schema_version": 1,
        "dataset_name": CAPTURE_DATASET_NAME,
        "plan_sha256": "1" * 64,
        "plan_size": 123,
        "plan": {"historical": "provenance-only"},
        "fixture_identifier": "FOTMOB:1001",
        "source_match_id": "1001",
        "kickoff": "2026-08-15T12:00:00Z",
        "request_started_at": "2026-08-10T10:00:00Z",
        "status": 200,
        "content_type": "application/json",
        "content_length": len(raw),
        "observed_at": "2026-08-10T10:00:01Z",
        "network_acquisition_performed": True,
        "raw_file_name": "response.json",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size": len(raw),
        "safety": dict(SAFETY),
    }


def _manifest_bytes(payload: dict | None = None) -> bytes:
    return (
        json.dumps(
            payload or _payload(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def test_exact_persisted_bytes_verify_without_parsing_raw_body() -> None:
    manifest = _manifest_bytes()
    verified = verify_persisted_match_details_evidence(
        manifest_bytes=manifest,
        raw_bytes=RAW,
    )
    assert verified.fixture_identifier == "FOTMOB:1001"
    assert verified.source_match_id == "1001"
    assert verified.raw_sha256 == hashlib.sha256(RAW).hexdigest()
    assert verified.manifest_sha256 == hashlib.sha256(manifest).hexdigest()
    assert verified.observed_at == datetime.datetime(2026, 8, 10, 10, 0, 1, tzinfo=UTC)
    assert all(value is False for value in verified.safety.values())

    canonical = canonical_persisted_match_details_evidence_receipt_bytes(verified)
    assert canonical.endswith(b"\n")
    assert sha256_persisted_match_details_evidence_receipt(verified) == hashlib.sha256(
        canonical
    ).hexdigest()


def test_manifest_must_be_exact_canonical_bytes() -> None:
    canonical = _manifest_bytes()
    with pytest.raises(
        FotMobReviewedMatchDetailsPersistedEvidenceError,
        match="exact canonical PR #50",
    ):
        verify_persisted_match_details_evidence(
            manifest_bytes=canonical + b"\n",
            raw_bytes=RAW,
        )


def test_duplicate_manifest_keys_fail_closed() -> None:
    raw_sha = hashlib.sha256(RAW).hexdigest()
    manifest = (
        '{"schema_version":1,"schema_version":1,"dataset_name":"'
        + CAPTURE_DATASET_NAME
        + '","plan_sha256":"'
        + "1" * 64
        + '","plan_size":123,"plan":{},"fixture_identifier":"FOTMOB:1001",'
        '"source_match_id":"1001","kickoff":"2026-08-15T12:00:00Z",'
        '"request_started_at":"2026-08-10T10:00:00Z","status":200,'
        '"content_type":"application/json","content_length":27,'
        '"observed_at":"2026-08-10T10:00:01Z","network_acquisition_performed":true,'
        '"raw_file_name":"response.json","raw_sha256":"'
        + raw_sha
        + '","raw_size":27,"safety":'
        + json.dumps(SAFETY, separators=(",", ":"))
        + "}\n"
    ).encode("utf-8")
    with pytest.raises(
        FotMobReviewedMatchDetailsPersistedEvidenceError,
        match="duplicate manifest JSON key",
    ):
        verify_persisted_match_details_evidence(
            manifest_bytes=manifest,
            raw_bytes=RAW,
        )


def test_raw_tamper_size_and_hash_fail_closed() -> None:
    manifest = _manifest_bytes()
    with pytest.raises(
        FotMobReviewedMatchDetailsPersistedEvidenceError,
        match="size does not match",
    ):
        verify_persisted_match_details_evidence(
            manifest_bytes=manifest,
            raw_bytes=RAW + b"x",
        )

    payload = _payload()
    payload["raw_sha256"] = "f" * 64
    with pytest.raises(
        FotMobReviewedMatchDetailsPersistedEvidenceError,
        match="SHA-256",
    ):
        verify_persisted_match_details_evidence(
            manifest_bytes=_manifest_bytes(payload),
            raw_bytes=RAW,
        )


def test_fixture_identity_timing_and_safety_are_fail_closed() -> None:
    payload = _payload()
    payload["source_match_id"] = "1002"
    with pytest.raises(FotMobReviewedMatchDetailsPersistedEvidenceError, match="mismatch"):
        verify_persisted_match_details_evidence(
            manifest_bytes=_manifest_bytes(payload), raw_bytes=RAW
        )

    payload = _payload()
    payload["observed_at"] = payload["kickoff"]
    with pytest.raises(FotMobReviewedMatchDetailsPersistedEvidenceError, match="timing"):
        verify_persisted_match_details_evidence(
            manifest_bytes=_manifest_bytes(payload), raw_bytes=RAW
        )

    payload = _payload()
    payload["safety"]["football_semantics_authorized"] = True
    with pytest.raises(FotMobReviewedMatchDetailsPersistedEvidenceError, match="exact bool False"):
        verify_persisted_match_details_evidence(
            manifest_bytes=_manifest_bytes(payload), raw_bytes=RAW
        )


def test_manifest_extra_or_missing_keys_fail_closed() -> None:
    payload = _payload()
    payload["invented"] = "field"
    with pytest.raises(FotMobReviewedMatchDetailsPersistedEvidenceError, match="top-level keys"):
        verify_persisted_match_details_evidence(
            manifest_bytes=_manifest_bytes(payload), raw_bytes=RAW
        )

    payload = _payload()
    del payload["plan"]
    with pytest.raises(FotMobReviewedMatchDetailsPersistedEvidenceError, match="top-level keys"):
        verify_persisted_match_details_evidence(
            manifest_bytes=_manifest_bytes(payload), raw_bytes=RAW
        )


def test_receipt_revalidation_rejects_forced_mutation() -> None:
    verified = verify_persisted_match_details_evidence(
        manifest_bytes=_manifest_bytes(), raw_bytes=RAW
    )
    object.__setattr__(verified, "raw_sha256", "f" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsPersistedEvidenceError):
        canonical_persisted_match_details_evidence_receipt_bytes(verified)


def test_network_flag_must_record_real_pr51_acquisition() -> None:
    payload = _payload()
    payload["network_acquisition_performed"] = False
    with pytest.raises(
        FotMobReviewedMatchDetailsPersistedEvidenceError,
        match="network acquisition performed",
    ):
        verify_persisted_match_details_evidence(
            manifest_bytes=_manifest_bytes(payload), raw_bytes=RAW
        )
