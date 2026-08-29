from __future__ import annotations

from pathlib import Path

import json
import pytest

from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
    manifest_from_mapping,
    strict_manifest_json_loads,
)
from domain.fotmob_fixture_candidates import (
    FotMobFixtureCandidateError,
    build_fotmob_fixture_candidate_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence/fotmob_data_matches/pr83_post_finish_pair"


def _reviewed_extended_capture():
    capture = EVIDENCE_ROOT / "20260814" / "a18e843fabe5aca74846b160"
    manifest = manifest_from_mapping(
        strict_manifest_json_loads((capture / "manifest.json").read_bytes())
    )
    return (capture / "response.json").read_bytes(), manifest


def test_hosted_shadow_workflow_uses_import_safe_module_entrypoint():
    workflow = (ROOT / ".github/workflows/current-shadow-all-market.yml").read_text(
        encoding="utf-8"
    )
    assert "python -m scripts.execute_current_shadow_all_market" in workflow
    assert "python scripts/execute_current_shadow_all_market.py" not in workflow


def test_current_fixture_candidate_builder_replays_reviewed_additive_schema():
    raw, manifest = _reviewed_extended_capture()
    bundle = build_fotmob_fixture_candidate_bundle(((raw, manifest),))
    assert bundle.candidate_count > 0
    assert bundle.sources[0].source_raw_sha256 == manifest.raw_sha256


def test_unreviewed_current_status_key_still_fails_closed():
    raw, original = _reviewed_extended_capture()
    payload = json.loads(raw)
    payload["leagues"][0]["matches"][0]["status"]["inventedLiveField"] = 1
    changed = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(changed),
        body=changed,
        observed_at=original.observed_at,
        network_acquisition_performed=True,
    )
    manifest = build_data_matches_capture_manifest(
        response,
        request_date=original.request_date,
        timezone=original.timezone,
        ccode3=original.ccode3,
    )
    with pytest.raises(FotMobFixtureCandidateError, match="PR39/PR89"):
        build_fotmob_fixture_candidate_bundle(((changed, manifest),))
