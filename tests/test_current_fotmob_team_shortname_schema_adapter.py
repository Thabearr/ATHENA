from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess

import pytest

from domain.current_fotmob_fixture_candidate_adapter import (
    CURRENT_TEAM_SHORTNAME_AWAY_OCCURRENCES,
    CURRENT_TEAM_SHORTNAME_HOME_OCCURRENCES,
    CURRENT_TEAM_SHORTNAME_SOURCE_ACTIONS_ARTIFACT_ID,
    CURRENT_TEAM_SHORTNAME_SOURCE_ACTIONS_ARTIFACT_SHA256,
    CURRENT_TEAM_SHORTNAME_SOURCE_CAPTURE_ID,
    CURRENT_TEAM_SHORTNAME_SOURCE_MANIFEST_FILE_SHA256,
    CURRENT_TEAM_SHORTNAME_SOURCE_OBSERVED_AT,
    CURRENT_TEAM_SHORTNAME_SOURCE_RAW_SHA256,
    CURRENT_TEAM_SHORTNAME_SOURCE_REQUEST_DATE,
    CURRENT_TEAM_SHORTNAME_SOURCE_WORKFLOW_RUN_ID,
    POLICY_ID,
    TEAM_SHORTNAME_KEY,
    TEAM_SHORTNAME_RULE,
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


def _reviewed_capture():
    capture = EVIDENCE_ROOT / "20260814" / "a18e843fabe5aca74846b160"
    manifest = manifest_from_mapping(
        strict_manifest_json_loads((capture / "manifest.json").read_bytes())
    )
    return (capture / "response.json").read_bytes(), manifest


def _manifest_for(raw: bytes, original):
    return build_data_matches_capture_manifest(
        CapturedFotMobDataMatchesResponse(
            status=200,
            content_type="application/json; charset=utf-8",
            content_length=len(raw),
            body=raw,
            observed_at=original.observed_at,
            network_acquisition_performed=True,
        ),
        request_date=original.request_date,
        timezone=original.timezone,
        ccode3=original.ccode3,
    )


def _raw(payload: dict) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")


def _identity_rows(bundle):
    return tuple(
        (
            item.source_match_id,
            item.source_league_id,
            item.home_source_team_id,
            item.away_source_team_id,
            item.kickoff_utc,
        )
        for item in bundle.candidates
    )


def _with_shortnames(raw: bytes, *, home="Home opaque", away="Away opaque"):
    payload = json.loads(raw)
    match = payload["leagues"][0]["matches"][0]
    if home is not _ABSENT:
        match["home"][TEAM_SHORTNAME_KEY] = home
    if away is not _ABSENT:
        match["away"][TEAM_SHORTNAME_KEY] = away
    return payload


_ABSENT = object()


def test_v3_contract_binds_exact_current_shortname_evidence():
    assert POLICY_ID == "CURRENT_FOTMOB_PR39_OR_REVIEWED_PR87_PR89_ADDITIVE_SCHEMA_V3"
    assert TEAM_SHORTNAME_KEY == "shortName"
    assert TEAM_SHORTNAME_RULE == (
        "OPTIONAL_MATCH_TEAM_SHORTNAME_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_"
        "VALIDATION_PROJECTION_ONLY"
    )
    assert CURRENT_TEAM_SHORTNAME_SOURCE_WORKFLOW_RUN_ID == 34628860651
    assert CURRENT_TEAM_SHORTNAME_SOURCE_ACTIONS_ARTIFACT_ID == 10275611884
    assert CURRENT_TEAM_SHORTNAME_SOURCE_ACTIONS_ARTIFACT_SHA256 == (
        "d16171cb57db943e9d09462b52f33b6c8919a5a8c135d27e7785878b9fa93e04"
    )
    assert CURRENT_TEAM_SHORTNAME_SOURCE_REQUEST_DATE == "20260911"
    assert CURRENT_TEAM_SHORTNAME_SOURCE_CAPTURE_ID == "36feec8e0ce3dd8970d96cc7"
    assert CURRENT_TEAM_SHORTNAME_SOURCE_OBSERVED_AT == "2026-09-11T17:40:04.585312Z"
    assert CURRENT_TEAM_SHORTNAME_SOURCE_MANIFEST_FILE_SHA256 == (
        "292b8d5e9b8a2f44bc4696f0635f885c121ded3b200c15c62605393c944d3afd"
    )
    assert CURRENT_TEAM_SHORTNAME_SOURCE_RAW_SHA256 == (
        "820d0e6f0e783f8bd9a5f4968bcaba46dad2cc8ef637540e19bd7ce09f398ed1"
    )
    assert CURRENT_TEAM_SHORTNAME_HOME_OCCURRENCES == 5
    assert CURRENT_TEAM_SHORTNAME_AWAY_OCCURRENCES == 5


@pytest.mark.parametrize(
    ("home", "away"),
    [("Home", _ABSENT), (_ABSENT, "Away"), ("", "")],
)
def test_shortname_is_opaque_validation_only_and_preserves_original_ancestry(home, away):
    raw, original = _reviewed_capture()
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)
    changed = _raw(_with_shortnames(raw, home=home, away=away))
    manifest = _manifest_for(changed, original)

    result = build_current_fotmob_fixture_candidate_bundle(changed, manifest)

    assert _identity_rows(result) == _identity_rows(baseline)
    assert result.candidate_count == baseline.candidate_count
    assert result.sources[0].source_raw_sha256 == manifest.raw_sha256
    assert result.sources[0].source_raw_size == manifest.raw_size
    assert all(item.source_raw_sha256 == manifest.raw_sha256 for item in result.candidates)
    assert all(not hasattr(item, "short_name") for item in result.candidates)


@pytest.mark.parametrize("bad", [None, True, 1, 1.5, {}, []])
def test_shortname_requires_exact_string(bad):
    raw, original = _reviewed_capture()
    changed = _raw(_with_shortnames(raw, home=bad, away=_ABSENT))
    with pytest.raises(CurrentFotMobFixtureCandidateAdapterError, match="home.shortName must be an exact string"):
        build_current_fotmob_fixture_candidate_bundle(changed, _manifest_for(changed, original))


@pytest.mark.parametrize("side", ["home", "away"])
def test_unknown_team_keys_remain_fail_closed_even_beside_shortname(side):
    raw, original = _reviewed_capture()
    payload = _with_shortnames(raw)
    payload["leagues"][0]["matches"][0][side]["inventedTeamKey"] = "not admitted"
    changed = _raw(payload)
    with pytest.raises(CurrentFotMobFixtureCandidateAdapterError, match="unreviewed team key"):
        build_current_fotmob_fixture_candidate_bundle(changed, _manifest_for(changed, original))


def test_shortname_composes_with_reviewed_extra_halfs_and_request_date_projection():
    raw, original = _reviewed_capture()
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)
    payload = _with_shortnames(raw)
    match = payload["leagues"][0]["matches"][0]
    match["status"]["halfs"]["firstExtraHalfStarted"] = "02.09.2026 18:40:07"
    match["status"]["halfs"]["secondExtraHalfStarted"] = "02.09.2026 18:40:17"
    kickoff = dt.datetime.fromisoformat(match["status"]["utcTime"].replace("Z", "+00:00"))
    moved = kickoff + dt.timedelta(days=1)
    match["status"]["utcTime"] = moved.isoformat().replace("+00:00", "Z")
    match["timeTS"] = int(moved.timestamp() * 1000)
    changed = _raw(payload)

    result = build_current_fotmob_fixture_candidate_bundle(changed, _manifest_for(changed, original))

    assert result.candidate_count == baseline.candidate_count - 1
    assert match["id"] not in {item.source_match_id for item in result.candidates}
    assert result.sources[0].source_raw_sha256 != original.raw_sha256


def test_assessment_identity_changes_when_shortname_projection_state_changes():
    raw, original = _reviewed_capture()
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)
    one_payload = _with_shortnames(raw, home="Home", away=_ABSENT)
    two_payload = _with_shortnames(raw, home="Home", away="Away")
    one_raw = _raw(one_payload)
    two_raw = _raw(two_payload)
    one = build_current_fotmob_fixture_candidate_bundle(one_raw, _manifest_for(one_raw, original))
    two = build_current_fotmob_fixture_candidate_bundle(two_raw, _manifest_for(two_raw, original))

    assert baseline.sources[0].schema_assessment_sha256 != one.sources[0].schema_assessment_sha256
    assert one.sources[0].schema_assessment_sha256 != two.sources[0].schema_assessment_sha256


@pytest.mark.parametrize(
    ("relative_path", "expected_blob"),
    [
        ("domain/fotmob_data_matches_schema.py", "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"),
        (
            "domain/fotmob_data_matches_terminal_state_schema_extension_protocol.py",
            "71b2f1a8add05929835d469df94396375a115391",
        ),
        (
            "domain/fotmob_data_matches_terminal_state_schema_extension.py",
            "fc120476739293abbb5db4374a0b4d7cfe8a1fc3",
        ),
        (
            "domain/fotmob_data_matches_eliminated_team_id_value_domain_extension.py",
            "f33dd31aedcd92b5691a3503914ed184d601b493",
        ),
    ],
)
def test_frozen_pr39_pr86_pr87_pr89_filtered_blobs_remain_pinned(relative_path, expected_blob):
    actual = subprocess.run(
        ["git", "hash-object", "--path", relative_path, "--filters", relative_path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert actual == expected_blob
