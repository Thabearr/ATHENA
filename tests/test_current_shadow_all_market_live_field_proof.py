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
from domain.current_fotmob_provider_native_qualification import (
    qualify_current_fotmob_capture,
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
from domain import sportybet_current_event_discovery_reconciliation as reconciliation


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


def _move_first_match_off_request_utc_date(raw: bytes):
    payload = json.loads(raw)
    match = payload["leagues"][0]["matches"][0]
    kickoff = dt.datetime.fromisoformat(match["status"]["utcTime"].replace("Z", "+00:00"))
    moved = kickoff + dt.timedelta(days=1)
    match["status"]["utcTime"] = moved.isoformat().replace("+00:00", "Z")
    match["timeTS"] = int(moved.timestamp() * 1000)
    changed = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload, changed, match["id"]


def test_hosted_shadow_workflow_uses_import_safe_module_entrypoint():
    workflow = (ROOT / ".github/workflows/current-shadow-all-market.yml").read_text(
        encoding="utf-8"
    )
    assert "python -m scripts.execute_current_shadow_daily" in workflow
    assert "python scripts/execute_current_shadow_daily.py" not in workflow
    assert "python scripts/execute_current_shadow_all_market.py" not in workflow


def test_current_fixture_candidate_builder_replays_reviewed_additive_schema():
    raw, manifest = _reviewed_extended_capture()
    with pytest.raises(FotMobFixtureCandidateError, match="PR #39 schema assessment failed"):
        build_fotmob_fixture_candidate_bundle(((raw, manifest),))
    bundle = build_current_fotmob_fixture_candidate_bundle(raw, manifest)
    assert bundle.candidate_count > 0
    assert bundle.sources[0].source_raw_sha256 == manifest.raw_sha256


def test_current_provider_native_qualification_consumes_reviewed_candidate_subset():
    raw, original = _reviewed_extended_capture()
    _payload, changed, moved_match_id = _move_first_match_off_request_utc_date(raw)
    manifest = _manifest_for_changed_raw(changed, original)
    candidates = build_current_fotmob_fixture_candidate_bundle(changed, manifest)

    qualified = qualify_current_fotmob_capture(
        candidates,
        raw_json=changed,
        manifest=manifest,
    )

    assert len(qualified) == candidates.candidate_count
    by_id = {item.fixture_id: item for item in qualified}
    assert moved_match_id not in by_id
    assert set(by_id) == {item.source_match_id for item in candidates.candidates}
    for candidate in candidates.candidates:
        fixture = by_id[candidate.source_match_id]
        assert fixture.provider_primary_id == candidate.source_competition_primary_id
        assert fixture.wrapper_id == candidate.source_league_id
        assert fixture.home_team_id == candidate.home_source_team_id
        assert fixture.away_team_id == candidate.away_source_team_id
        assert fixture.kickoff_utc == candidate.kickoff_utc
        assert fixture.capture_raw_sha256 == manifest.raw_sha256


def test_current_sportybet_replay_reuses_single_capture_current_adapter():
    raw, manifest = _reviewed_extended_capture()
    expected = build_current_fotmob_fixture_candidate_bundle(raw, manifest)
    actual = reconciliation._build_replayed_fotmob_candidates(((raw, manifest),))
    assert actual == expected
    assert actual.sources[0].source_raw_sha256 == manifest.raw_sha256


def test_current_sportybet_replay_keeps_multicapture_on_frozen_builder(monkeypatch):
    sentinel = object()
    rows = ((b"one", object()), (b"two", object()))

    def frozen_builder(value):
        assert value is rows
        return sentinel

    def current_builder(*_args, **_kwargs):
        raise AssertionError("current adapter must be singleton-only")

    monkeypatch.setattr(
        reconciliation.fotmob_candidates,
        "build_fotmob_fixture_candidate_bundle",
        frozen_builder,
    )
    monkeypatch.setattr(
        reconciliation.current_fotmob_candidates,
        "build_current_fotmob_fixture_candidate_bundle",
        current_builder,
    )
    assert reconciliation._build_replayed_fotmob_candidates(rows) is sentinel


def test_current_fixture_candidate_builder_excludes_live_cross_date_rows_only():
    raw, original = _reviewed_extended_capture()
    baseline = build_current_fotmob_fixture_candidate_bundle(raw, original)
    _payload, changed, moved_match_id = _move_first_match_off_request_utc_date(raw)
    manifest = _manifest_for_changed_raw(changed, original)

    with pytest.raises(FotMobFixtureCandidateError, match="PR #39 schema assessment failed"):
        build_fotmob_fixture_candidate_bundle(((changed, manifest),))

    bundle = build_current_fotmob_fixture_candidate_bundle(changed, manifest)
    assert bundle.candidate_count == baseline.candidate_count - 1
    assert moved_match_id not in {item.source_match_id for item in bundle.candidates}
    assert all(
        item.kickoff_utc.strftime("%Y%m%d") == manifest.request_date
        for item in bundle.candidates
    )
    assert bundle.sources[0].source_raw_sha256 == manifest.raw_sha256
    assert all(item.source_raw_sha256 == manifest.raw_sha256 for item in bundle.candidates)


def test_cross_date_projection_does_not_hide_unreviewed_status_drift():
    raw, original = _reviewed_extended_capture()
    payload, _changed, _moved_match_id = _move_first_match_off_request_utc_date(raw)
    payload["leagues"][0]["matches"][0]["status"]["inventedLiveField"] = 1
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
    manifest = _manifest_for_changed_raw(changed, original)
    with pytest.raises(
        CurrentFotMobFixtureCandidateAdapterError, match="additive schema assessment failed"
    ):
        build_current_fotmob_fixture_candidate_bundle(changed, manifest)


def test_current_fixture_universe_scans_entire_fixed_horizon(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: dt.datetime(2026, 8, 29, 22, 0, tzinfo=dt.timezone.utc),
    )
    calls = []
    expected_30 = SimpleNamespace()
    expected_31 = SimpleNamespace()

    def issue(**kwargs):
        request_date = kwargs["request_date"]
        calls.append(request_date)
        if request_date == "20260829":
            raise runner.current_fotmob_source.CurrentFotMobReviewedSourceError(
                runner.current_fotmob_source.STATUS_NO_FIXTURES
            )
        return expected_30 if request_date == "20260830" else expected_31

    monkeypatch.setattr(runner.current_fotmob_source, "issue_current_fotmob_reviewed_source", issue)
    actual, searched = runner._issue_current_fixture_sources(repository_root=tmp_path)
    assert actual == (
        (expected_30, "20260830"),
        (expected_31, "20260831"),
    )
    assert searched == ("20260829", "20260830", "20260831")
    assert calls == ["20260829", "20260830", "20260831"]


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
        runner._issue_current_fixture_sources(repository_root=tmp_path)


def test_current_fixture_universe_all_empty_dates_fail_with_exact_horizon(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "_now",
        lambda: dt.datetime(2026, 8, 29, 22, 0, tzinfo=dt.timezone.utc),
    )
    calls = []

    def issue(**kwargs):
        calls.append(kwargs["request_date"])
        raise runner.current_fotmob_source.CurrentFotMobReviewedSourceError(
            runner.current_fotmob_source.STATUS_NO_FIXTURES
        )

    monkeypatch.setattr(runner.current_fotmob_source, "issue_current_fotmob_reviewed_source", issue)
    with pytest.raises(
        runner.CurrentShadowAllMarketRunnerError,
        match=(
            "NO_POLICY_APPROVED_CURRENT_FOTMOB_FIXTURES_IN_FIXED_HORIZON:"
            "20260829,20260830,20260831"
        ),
    ):
        runner._issue_current_fixture_sources(repository_root=tmp_path)
    assert calls == ["20260829", "20260830", "20260831"]
