from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import current_shadow_fixture_date_request as date_request
from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
from domain import current_shadow_sportybet_tolerant_live_inventory as tolerant_inventory
from scripts import execute_current_shadow_request as request


UTC = dt.timezone.utc


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


def test_current_asof_never_expands_frozen_historical_feature_scope():
    source = Path(current_asof.__file__).read_text(encoding="utf-8")
    assert "current_shadow_paired_fotmob_history" not in source
    assert "_paired_fallback" not in source
    assert "ATHENA_CURRENT_SHADOW_PAIRED_HISTORY_ARTIFACT" not in source
