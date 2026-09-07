from __future__ import annotations

import datetime as dt
import os
from types import SimpleNamespace

import pytest

from domain import current_fotmob_fixture_review_policy as fixture_policy
from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import current_shadow_fixture_date_request as date_request
from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
from domain import current_shadow_paired_fotmob_history as paired_history
from domain import current_shadow_sportybet_tolerant_live_inventory as tolerant_inventory
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from scripts import execute_current_shadow_request as request


UTC = dt.timezone.utc


def _capture() -> fresh.QualifiedCaptureFixture:
    return fresh.QualifiedCaptureFixture(
        fixture_id=9_000_001,
        provider_primary_id=87,
        wrapper_id=87,
        home_team_id=101,
        away_team_id=202,
        kickoff_utc=dt.datetime(2026, 9, 9, 18, 0, tzinfo=UTC),
        capture_observed_at=dt.datetime(2026, 9, 6, 20, 0, tzinfo=UTC),
        capture_manifest_sha256="1" * 64,
        capture_raw_sha256="2" * 64,
    )


def test_explicit_fixture_dates_support_non_contiguous_days_inside_rolling_week():
    parsed = date_request.parse_fixture_dates_text("20260910,20260907,20260909")
    assert parsed == ("20260907", "20260909", "20260910")
    assert date_request.validate_fixture_dates(
        parsed,
        current_utc=dt.datetime(2026, 9, 6, 23, 0, tzinfo=UTC),
    ) == parsed


def test_explicit_fixture_dates_reject_duplicates_and_dates_outside_today_plus_six():
    with pytest.raises(date_request.CurrentShadowFixtureDateRequestError, match="unique"):
        date_request.parse_fixture_dates_text("20260907,20260907")
    with pytest.raises(date_request.CurrentShadowFixtureDateRequestError, match="outside"):
        date_request.validate_fixture_dates(
            ("20260913",),
            current_utc=dt.datetime(2026, 9, 6, 23, 0, tzinfo=UTC),
        )
    with pytest.raises(date_request.CurrentShadowFixtureDateRequestError, match="outside"):
        date_request.validate_fixture_dates(
            ("20260905",),
            current_utc=dt.datetime(2026, 9, 6, 23, 0, tzinfo=UTC),
        )


def test_selected_source_issuer_requests_only_chosen_dates_and_preserves_empty_date(monkeypatch, tmp_path):
    monkeypatch.setattr(
        request.runner,
        "_now",
        lambda: dt.datetime(2026, 9, 6, 23, 0, tzinfo=UTC),
    )
    calls: list[str] = []
    expected_07 = SimpleNamespace(name="seven")
    expected_10 = SimpleNamespace(name="ten")

    def issue(**kwargs):
        request_date = kwargs["request_date"]
        calls.append(request_date)
        if request_date == "20260909":
            raise request.runner.current_fotmob_source.CurrentFotMobReviewedSourceError(
                request.runner.current_fotmob_source.STATUS_NO_FIXTURES
            )
        return expected_07 if request_date == "20260907" else expected_10

    monkeypatch.setattr(
        request.runner.current_fotmob_source,
        "issue_current_shadow_fotmob_reviewed_source",
        issue,
    )
    issuer = request._selected_source_issuer(("20260910", "20260907", "20260909"))
    sources, attempted = issuer(repository_root=tmp_path)

    assert attempted == ("20260907", "20260909", "20260910")
    assert calls == ["20260907", "20260909", "20260910"]
    assert sources == ((expected_07, "20260907"), (expected_10, "20260910"))


def test_request_parent_passes_exact_explicit_dates_to_worker(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.delenv(request.WORKER_ENV, raising=False)

    def fake_run(command, *, env, check, timeout):
        seen.update(command=command, env=env, check=check, timeout=timeout)
        return SimpleNamespace(returncode=19)

    monkeypatch.setattr(request.subprocess, "run", fake_run)
    result = request.main(
        [
            "--target-size",
            "15",
            "--fixture-dates",
            "20260910,20260907,20260909",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 19
    assert seen["env"][request.WORKER_ENV] == "1"
    assert seen["check"] is False
    index = seen["command"].index("--fixture-dates")
    assert seen["command"][index + 1] == "20260907,20260909,20260910"


def test_reconciliation_compatibility_install_is_scoped_and_restored():
    proxy = request.reconciliation.legacy.reviewed
    previous = dict(getattr(proxy, "__dict__", {}))
    installed_proxy, retained = request._install_reconciliation_compatibility()
    assert installed_proxy is proxy
    assert retained == previous
    assert proxy._match_event is run199_identity.match_event
    assert proxy._detail_inventory_from_directory is request._detail_inventory
    request._restore_reconciliation_compatibility(proxy, retained)
    assert dict(getattr(proxy, "__dict__", {})) == previous


def test_run199_identity_overlay_is_evidence_bound_and_never_grants_bet_authority():
    assert run199_identity.policy_sha256() == run199_identity.POLICY_SHA256
    assert run199_identity.EVIDENCE_WORKFLOW_RUN_ID == 34052920015
    assert run199_identity.EVIDENCE_ARTIFACT_ID == 9995330762
    assert "NO_FUZZY" in run199_identity.MATCHING_BASIS
    assert "NO_REVERSAL" in run199_identity.MATCHING_BASIS
    assert run199_identity.AUTHORITY["selection"] is False
    assert run199_identity.AUTHORITY["sportybet_execution"] is False
    assert run199_identity.AUTHORITY["bet"] is False
    assert run199_identity.AUTHORITY["wager_placed"] is False


def test_row_local_quote_policy_keeps_all_execution_authority_false():
    policy = tolerant_inventory.policy_summary()
    assert policy["raw_event_mutation_performed"] is False
    assert policy["provider_value_normalization_performed"] is False
    assert policy["synthetic_quote_performed"] is False
    assert policy["selection_authority"] is False
    assert policy["sportybet_execution_authority"] is False
    assert policy["bet_authority"] is False
    assert policy["wager_placed"] is False


def test_paired_history_is_pinned_to_exact_preserved_pr117_campaign():
    assert paired_history.ARTIFACT_ID == paired_history.pr117.ARTIFACT_ID
    assert paired_history.ARTIFACT_SHA256 == paired_history.pr117.ARTIFACT_SHA256
    assert paired_history.ARTIFACT_SIZE == paired_history.pr117.ARTIFACT_SIZE
    assert paired_history.CACHE_SHA256 == paired_history.pr117.CACHE_SHA256
    assert paired_history.CACHE_SIZE == paired_history.pr117.CACHE_SIZE
    assert paired_history._AUTHORITY["research_shadow_history_fallback"] is True
    assert paired_history._AUTHORITY["production_model"] is False
    assert paired_history._AUTHORITY["pricing"] is False
    assert paired_history._AUTHORITY["selection"] is False
    assert paired_history._AUTHORITY["bet"] is False
    assert paired_history._AUTHORITY["wager_placed"] is False


def test_current_asof_paired_fallback_reuses_frozen_rate_math_and_stays_research_only(monkeypatch):
    features = {
        "home_elo": 1510.0,
        "away_elo": 1490.0,
        "home_form": 0.60,
        "away_form": 0.40,
        "fatigue": 0.0,
    }
    paired = paired_history.PairedCurrentFeatureResult(
        features=features,
        missing_feature_ids=(),
        history_identity_sha256="3" * 64,
        history_row_count=1234,
        feature_projection_sha256="4" * 64,
        authority=paired_history._AUTHORITY,
    )
    monkeypatch.setenv(paired_history.ARTIFACT_ENV, "/exact/preserved/history.zip")
    monkeypatch.setattr(
        paired_history,
        "build_current_features_from_paired_history",
        lambda **_kwargs: paired,
    )

    assessment = current_asof._paired_fallback(
        prefix=(),
        capture=_capture(),
        narrow_history_sha256="5" * 64,
    )

    assert assessment is not None
    assert assessment.fixture_review_policy_id == fixture_policy.SHADOW_POLICY_ID
    assert dict(assessment.features) == features
    assert dict(assessment.rates) == fresh._rates_from_features(features)
    assert assessment.history_prefix_count == 1234
    assert assessment.authority["production_model"] is False
    assert assessment.authority["pricing"] is False
    assert assessment.authority["selection"] is False
    assert assessment.authority["bet"] is False
    assert assessment.authority["wager_placed"] is False
