from __future__ import annotations

from pathlib import Path

import datetime as dt
import json
import pytest
from types import SimpleNamespace

from domain.current_fotmob_fixture_candidate_adapter import (
    CurrentFotMobFixtureCandidateAdapterError,
    build_current_fotmob_fixture_candidate_bundle,
)
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
from domain import current_shadow_all_market_runner as runner


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
    with pytest.raises(FotMobFixtureCandidateError, match="PR #39 schema assessment failed"):
        build_fotmob_fixture_candidate_bundle(((raw, manifest),))
    bundle = build_current_fotmob_fixture_candidate_bundle(raw, manifest)
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
    with pytest.raises(
        CurrentFotMobFixtureCandidateAdapterError, match="additive schema assessment failed"
    ):
        build_current_fotmob_fixture_candidate_bundle(changed, manifest)


def test_current_fixture_universe_uses_earliest_nonempty_date_only(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: dt.datetime(2026, 8, 29, 22, 0, tzinfo=dt.timezone.utc),
    )
    calls = []
    expected = SimpleNamespace()

    def issue(**kwargs):
        calls.append(kwargs["request_date"])
        if kwargs["request_date"] == "20260829":
            raise runner.current_fotmob_source.CurrentFotMobReviewedSourceError(
                runner.current_fotmob_source.STATUS_NO_FIXTURES
            )
        return expected

    monkeypatch.setattr(runner.current_fotmob_source, "issue_current_fotmob_reviewed_source", issue)
    actual, request_date = runner._issue_current_fixture_source(repository_root=tmp_path)
    assert actual is expected
    assert request_date == "20260830"
    assert calls == ["20260829", "20260830"]


def test_current_fixture_universe_does_not_step_over_other_source_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: dt.datetime(2026, 8, 29, 22, 0, tzinfo=dt.timezone.utc),
    )

    def issue(**_kwargs):
        raise runner.current_fotmob_source.CurrentFotMobReviewedSourceError("schema drift")

    monkeypatch.setattr(runner.current_fotmob_source, "issue_current_fotmob_reviewed_source", issue)
    with pytest.raises(
        runner.current_fotmob_source.CurrentFotMobReviewedSourceError,
        match="schema drift",
    ):
        runner._issue_current_fixture_source(repository_root=tmp_path)