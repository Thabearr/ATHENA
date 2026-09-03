from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain.current_fotmob_fixture_candidate_adapter import (
    POLICY_ID,
    REVIEWED_EXTRA_HALFS_KEYS,
    REVIEWED_EXTRA_HALFS_RULE,
    SOURCE_ACTIONS_ARTIFACT_ID,
    SOURCE_CAPTURE_EXTRA_HALFS_OCCURRENCES,
    SOURCE_CAPTURE_MANIFEST_FILE_SHA256,
    SOURCE_CAPTURE_RAW_SHA256,
    SOURCE_CAPTURE_REQUEST_DATE,
    SOURCE_WORKFLOW_RUN_ID,
    CurrentFotMobFixtureCandidateAdapterError,
    build_current_fotmob_fixture_candidate_bundle,
)
from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
    manifest_from_mapping,
    strict_manifest_json_loads,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence/fotmob_data_matches/pr83_post_finish_pair"


def _reviewed_extended_capture():
    capture = EVIDENCE_ROOT / "20260814" / "a18e843fabe5aca74846b160"
    manifest = manifest_from_mapping(
        strict_manifest_json_loads((capture / "manifest.json").read_bytes())
    )
    return (capture / "response.json").read_bytes(), manifest


def _manifest_for_changed_raw(changed: bytes, original):
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(changed),
        body=changed,
        observed_at=original.observed_at,
        network_acquisition_performed=True,
    )
    return build_data_matches_capture_manifest(
        response,
        request_date=original.request_date,
        timezone=original.timezone,
        ccode3=original.ccode3,
    )


def _changed_raw(raw: bytes, *, first="02.09.2026 18:40:07", second="02.09.2026 18:40:17"):
    payload = json.loads(raw)
    halfs = payload["leagues"][0]["matches"][0]["status"]["halfs"]
    halfs["firstExtraHalfStarted"] = first
    halfs["secondExtraHalfStarted"] = second
    changed = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload, changed


def _identity_rows(bundle):
    return tuple(
        (
            item.source_match_id,
            item.source_league_id,
            item.source_competition_primary_id,
            item.home_source_team_id,
            item.away_source_team_id,
            item.kickoff_utc,
        )
        for item in bundle.candidates
    )


def test_v2_contract_is_bound_to_exact_live_extra_halfs_evidence():
    assert POLICY_ID == "CURRENT_FOTMOB_PR39_OR_REVIEWED_PR87_PR89_ADDITIVE_SCHEMA_V2"
    assert REVIEWED_EXTRA_HALFS_KEYS == (
        "firstExtraHalfStarted",
        "secondExtraHalfStarted",
    )
    assert REVIEWED_EXTRA_HALFS_RULE == (
        "OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_NO_EXTRA_TIME_SEMANTICS"
    )
    assert SOURCE_WORKFLOW_RUN_ID == 33690015364
    assert SOURCE_ACTIONS_ARTIFACT_ID == 9869665644
    assert SOURCE_CAPTURE_REQUEST_DATE == "20260902"
    assert SOURCE_CAPTURE_MANIFEST_FILE_SHA256 == (
        "18dc76e89be17fbd24c048b17954c22c85dab07e5daeffe203f14c2040e0cb1d"
    )
    assert SOURCE_CAPTURE_RAW_SHA256 == (
        "070c63fa4480e470ba94b2e6726ad4959c89f2bcffd6c3929304590ac8ef5973"
    )
    assert SOURCE_CAPTURE_EXTRA_HALFS_OCCURRENCES == {
        "firstExtraHalfStarted": 4,
        "secondExtraHalfStarted": 4,
    }


def test_reviewed_opaque_extra_halfs_preserve_fixture_identity_and_original_ancestry():
    raw, original = _reviewed_extended_capture()
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)
    _payload, changed = _changed_raw(raw)
    manifest = _manifest_for_changed_raw(changed, original)

    result = build_current_fotmob_fixture_candidate_bundle(changed, manifest)

    assert result.candidate_count == baseline.candidate_count
    assert _identity_rows(result) == _identity_rows(baseline)
    assert result.sources[0].source_raw_sha256 == manifest.raw_sha256
    assert result.sources[0].source_raw_size == manifest.raw_size
    assert all(item.source_raw_sha256 == manifest.raw_sha256 for item in result.candidates)
    assert all(
        item.source_capture_manifest_sha256 == result.sources[0].source_capture_manifest_sha256
        for item in result.candidates
    )


@pytest.mark.parametrize("bad_value", [None, 1, True, {}, []])
def test_reviewed_extra_halfs_require_exact_string_values(bad_value):
    raw, original = _reviewed_extended_capture()
    _payload, changed = _changed_raw(raw, first=bad_value)
    manifest = _manifest_for_changed_raw(changed, original)

    with pytest.raises(
        CurrentFotMobFixtureCandidateAdapterError,
        match="firstExtraHalfStarted must be an exact string",
    ):
        build_current_fotmob_fixture_candidate_bundle(changed, manifest)


def test_unreviewed_halfs_key_still_fails_closed():
    raw, original = _reviewed_extended_capture()
    payload = json.loads(raw)
    payload["leagues"][0]["matches"][0]["status"]["halfs"]["inventedExtraHalf"] = (
        "02.09.2026 18:40:30"
    )
    changed = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = _manifest_for_changed_raw(changed, original)

    with pytest.raises(
        CurrentFotMobFixtureCandidateAdapterError,
        match="additive schema assessment failed",
    ):
        build_current_fotmob_fixture_candidate_bundle(changed, manifest)


def test_reviewed_extra_halfs_compose_with_existing_exact_utc_request_date_projection():
    raw, original = _reviewed_extended_capture()
    payload, _changed = _changed_raw(raw)
    match = payload["leagues"][0]["matches"][0]
    kickoff = dt.datetime.fromisoformat(
        match["status"]["utcTime"].replace("Z", "+00:00")
    )
    moved = kickoff + dt.timedelta(days=1)
    match["status"]["utcTime"] = moved.isoformat().replace("+00:00", "Z")
    match["timeTS"] = int(moved.timestamp() * 1000)
    moved_match_id = match["id"]
    changed = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = _manifest_for_changed_raw(changed, original)
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)

    result = build_current_fotmob_fixture_candidate_bundle(changed, manifest)

    assert result.candidate_count == baseline.candidate_count - 1
    assert moved_match_id not in {item.source_match_id for item in result.candidates}
    assert result.sources[0].source_raw_sha256 == manifest.raw_sha256
    assert all(item.source_raw_sha256 == manifest.raw_sha256 for item in result.candidates)
