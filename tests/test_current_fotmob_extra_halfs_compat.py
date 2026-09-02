from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain.current_fotmob_fixture_candidate_adapter import (
    EXTRA_HALFS_KEYS,
    EXTRA_HALFS_RULE,
    LIVE_EXTRA_HALFS_OCCURRENCES,
    LIVE_EXTRA_HALFS_SOURCE_ARTIFACT_ID,
    LIVE_EXTRA_HALFS_SOURCE_RAW_SHA256,
    LIVE_EXTRA_HALFS_SOURCE_REQUEST_DATE,
    LIVE_EXTRA_HALFS_SOURCE_RUN_ID,
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


def _encode(payload) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _first_two_matches(payload):
    matches = [
        match
        for league in payload["leagues"]
        for match in league["matches"]
    ]
    assert len(matches) >= 2
    return matches[0], matches[1]


def _add_reviewed_extra_halfs(payload, *, target_index: int = 0):
    matches = [
        match
        for league in payload["leagues"]
        for match in league["matches"]
    ]
    target = matches[target_index]
    target["status"]["halfs"]["firstExtraHalfStarted"] = "14.08.2026 20:15:00"
    target["status"]["halfs"]["secondExtraHalfStarted"] = "14.08.2026 20:30:00"
    return target


def test_current_adapter_extra_halfs_rule_is_exact_and_live_evidence_bound():
    assert EXTRA_HALFS_KEYS == ("firstExtraHalfStarted", "secondExtraHalfStarted")
    assert EXTRA_HALFS_RULE == (
        "OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_NO_EXTRA_TIME_SEMANTICS"
    )
    assert LIVE_EXTRA_HALFS_SOURCE_RUN_ID == 33690015364
    assert LIVE_EXTRA_HALFS_SOURCE_ARTIFACT_ID == 9869665644
    assert LIVE_EXTRA_HALFS_SOURCE_REQUEST_DATE == "20260902"
    assert LIVE_EXTRA_HALFS_SOURCE_RAW_SHA256 == (
        "070c63fa4480e470ba94b2e6726ad4959c89f2bcffd6c3929304590ac8ef5973"
    )
    assert LIVE_EXTRA_HALFS_OCCURRENCES == {
        "firstExtraHalfStarted": 4,
        "secondExtraHalfStarted": 4,
    }


def test_reviewed_opaque_extra_halfs_are_validation_only_and_preserve_original_lineage():
    raw, original = _reviewed_extended_capture()
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)
    payload = json.loads(raw)
    _add_reviewed_extra_halfs(payload)
    changed = _encode(payload)
    manifest = _manifest_for_changed_raw(changed, original)

    bundle = build_current_fotmob_fixture_candidate_bundle(changed, manifest)

    assert bundle.candidate_count == baseline.candidate_count
    assert bundle.sources[0].source_raw_sha256 == manifest.raw_sha256
    assert bundle.sources[0].source_raw_size == manifest.raw_size
    assert all(item.source_raw_sha256 == manifest.raw_sha256 for item in bundle.candidates)
    assert all(
        item.source_capture_manifest_sha256
        == bundle.sources[0].source_capture_manifest_sha256
        for item in bundle.candidates
    )
    assert bundle.sources[0].schema_assessment_sha256 != baseline.sources[0].schema_assessment_sha256


@pytest.mark.parametrize("bad_value", [None, 7, False, 1.5])
def test_reviewed_extra_halfs_reject_non_string_or_null_values(bad_value):
    raw, original = _reviewed_extended_capture()
    payload = json.loads(raw)
    target = _add_reviewed_extra_halfs(payload)
    target["status"]["halfs"]["firstExtraHalfStarted"] = bad_value
    changed = _encode(payload)
    manifest = _manifest_for_changed_raw(changed, original)

    with pytest.raises(
        CurrentFotMobFixtureCandidateAdapterError,
        match="firstExtraHalfStarted must be an exact string",
    ):
        build_current_fotmob_fixture_candidate_bundle(changed, manifest)


def test_reviewed_extra_halfs_do_not_hide_any_other_unreviewed_halfs_key():
    raw, original = _reviewed_extended_capture()
    payload = json.loads(raw)
    target = _add_reviewed_extra_halfs(payload)
    target["status"]["halfs"]["inventedExtraHalfField"] = "opaque"
    changed = _encode(payload)
    manifest = _manifest_for_changed_raw(changed, original)

    with pytest.raises(
        CurrentFotMobFixtureCandidateAdapterError,
        match="additive schema assessment failed",
    ):
        build_current_fotmob_fixture_candidate_bundle(changed, manifest)


def test_reviewed_extra_halfs_compose_with_exact_utc_request_date_projection():
    raw, original = _reviewed_extended_capture()
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)
    payload = json.loads(raw)
    moved, _other = _first_two_matches(payload)
    _add_reviewed_extra_halfs(payload, target_index=1)

    kickoff = dt.datetime.fromisoformat(
        moved["status"]["utcTime"].replace("Z", "+00:00")
    )
    changed_kickoff = kickoff + dt.timedelta(days=1)
    moved["status"]["utcTime"] = changed_kickoff.isoformat().replace("+00:00", "Z")
    moved["timeTS"] = int(changed_kickoff.timestamp() * 1000)
    moved_id = moved["id"]

    changed = _encode(payload)
    manifest = _manifest_for_changed_raw(changed, original)
    bundle = build_current_fotmob_fixture_candidate_bundle(changed, manifest)

    assert bundle.candidate_count == baseline.candidate_count - 1
    assert moved_id not in {item.source_match_id for item in bundle.candidates}
    assert all(
        item.kickoff_utc.strftime("%Y%m%d") == manifest.request_date
        for item in bundle.candidates
    )
    assert bundle.sources[0].source_raw_sha256 == manifest.raw_sha256
