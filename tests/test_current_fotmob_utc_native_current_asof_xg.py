from __future__ import annotations

import datetime as dt
import hashlib
from types import SimpleNamespace

import pytest

from domain import current_fotmob_fixture_review_policy as fixture_policy
from domain import current_fotmob_latest_durable_fresh_history as latest_history
from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import current_fotmob_utc_native_shadow_prediction as current_shadow
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain import _all_market_shadow_current_binding as binding
from domain._all_market_shadow_types import ShadowDisposition


UTC = dt.timezone.utc


def _bootstrap_row(
    fixture_id: int,
    home: int,
    away: int,
    kickoff: dt.datetime,
    observed: dt.datetime,
    home_goals: int,
    away_goals: int,
) -> dict[str, object]:
    return {
        "source_namespace": fresh.SOURCE_NAMESPACE,
        "fixture_identifier": str(fixture_id),
        "source_local_kickoff": kickoff.replace(tzinfo=None).isoformat(),
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "home_team_identifier": str(home),
        "away_team_identifier": str(away),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "evidence_sha256": hashlib.sha256(f"bootstrap:{fixture_id}".encode()).hexdigest(),
        "evidence_reference": f"synthetic-reviewed-bootstrap:{fixture_id}",
    }


def _synthetic_ledger(monkeypatch: pytest.MonkeyPatch) -> fresh.FreshHistoryLedger:
    rows = (
        _bootstrap_row(
            6001,
            101,
            303,
            dt.datetime(2026, 8, 17, 18, 0, tzinfo=UTC),
            dt.datetime(2026, 8, 17, 20, 0, tzinfo=UTC),
            2,
            0,
        ),
        _bootstrap_row(
            6002,
            202,
            404,
            dt.datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            1,
            1,
        ),
    )
    raw = b"".join(fresh._canonical(row) for row in rows)
    monkeypatch.setattr(
        fresh, "BOOTSTRAP_PROJECTION_SHA256", hashlib.sha256(raw).hexdigest()
    )
    monkeypatch.setattr(fresh, "BOOTSTRAP_PROJECTION_SIZE", len(raw))
    monkeypatch.setattr(fresh, "BOOTSTRAP_PROJECTION_ROWS", len(rows))
    monkeypatch.setattr(fresh, "verify_reviewed_dependencies", lambda *a, **k: None)
    return fresh.build_fresh_history_ledger(raw)


def _capture(*, observed: dt.datetime) -> fresh.QualifiedCaptureFixture:
    return fresh.QualifiedCaptureFixture(
        fixture_id=7_000_001,
        provider_primary_id=40,
        wrapper_id=88_001,
        home_team_id=101,
        away_team_id=202,
        kickoff_utc=dt.datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
        capture_observed_at=observed,
        capture_manifest_sha256="1" * 64,
        capture_raw_sha256="2" * 64,
    )


def test_current_asof_recovers_fixture_before_frozen_holdout_window(
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _synthetic_ledger(monkeypatch)
    capture = _capture(observed=dt.datetime(2026, 8, 19, 12, 0, tzinfo=UTC))

    # PR149 remains frozen: 30 hours before kickoff is outside its 24h-to-60m seal.
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="24h-to-60m"):
        fresh.build_fresh_prediction_assessment(
            history_ledger=ledger,
            selected_capture=capture,
            holdout_start=dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
        )

    assessment = current_asof.build_current_asof_xg_assessment(
        history_ledger=ledger,
        selected_capture=capture,
        fixture_review_policy_id=fixture_policy.SHADOW_POLICY_ID,
    )
    assert assessment.disposition is current_asof.CurrentAsOfXGDisposition.COMPLETE
    assert set(assessment.features) == set(fresh._FEATURE_IDS)
    assert dict(assessment.rates) == fresh._rates_from_features(assessment.features)
    assert assessment.rates["calibrated_home"] >= 0.0
    assert assessment.rates["calibrated_away"] >= 0.0
    assert all(value is False for value in assessment.authority.values())
    assert assessment.to_dict()["wager_placed"] is False


def test_current_asof_does_not_weaken_current_shadow_lead_policy(
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _synthetic_ledger(monkeypatch)
    capture = _capture(observed=dt.datetime(2026, 8, 20, 17, 40, tzinfo=UTC))
    with pytest.raises(current_asof.CurrentAsOfXGError, match="prospective lead"):
        current_asof.build_current_asof_xg_assessment(
            history_ledger=ledger,
            selected_capture=capture,
            fixture_review_policy_id=fixture_policy.SHADOW_POLICY_ID,
        )


def test_current_binding_converts_outside_holdout_row_to_current_asof_rates(
    monkeypatch: pytest.MonkeyPatch,
):
    fixture = _capture(observed=dt.datetime(2026, 8, 19, 12, 0, tzinfo=UTC))
    row = SimpleNamespace(
        fixture_identifier="FOTMOB:7000001",
        fixture=fixture,
        kickoff_utc=fixture.kickoff_utc,
        disposition=current_shadow.OUTSIDE_REVIEWED_SEAL_WINDOW,
    )
    shadow_handoff = SimpleNamespace(
        rows=(row,),
        source_bundle=object(),
        fixture_review_policy_id=fixture_policy.SHADOW_POLICY_ID,
    )
    history = object.__new__(latest_history.CurrentLatestDurableFreshHistoryHandoff)
    object.__setattr__(history, "latest_applicable_success_selection_proven", True)
    object.__setattr__(history, "current_fresh_history_prefix_complete", True)
    object.__setattr__(history, "authority", {"downstream": False})
    object.__setattr__(history, "source_bundle", SimpleNamespace(selected_prefix=SimpleNamespace(shadow_handoff=shadow_handoff)))

    fake_assessment = SimpleNamespace(
        disposition=current_asof.CurrentAsOfXGDisposition.COMPLETE,
        missing_feature_ids=(),
        feature_projection_sha256="3" * 64,
        history_prefix_sha256="4" * 64,
        rates={
            "native_home": 1.5,
            "native_away": 1.0,
            "elo_only_home": 1.4,
            "elo_only_away": 1.1,
            "calibrated_home": 1.45,
            "calibrated_away": 1.05,
        },
    )
    monkeypatch.setattr(current_shadow, "_history_ledger", lambda _source: (object(), 7))
    monkeypatch.setattr(
        current_asof,
        "build_current_asof_xg_assessment",
        lambda **_kwargs: fake_assessment,
    )

    rates, blocker, missing, kickoff = binding._research_xg_from_validated_current_history(
        history,
        "FOTMOB:7000001",
        history_sha="5" * 64,
    )
    assert blocker is None
    assert missing == ()
    assert kickoff == "2026-08-20T18:00:00.000000Z"
    assert rates is not None
    assert rates.calibrated_home == 1.45
    assert rates.calibrated_away == 1.05
    assert rates.sealed_prediction_sha256 is None
    assert rates.feature_projection_identity == "3" * 64
    assert rates.history_prefix_identity == "4" * 64
    assert rates.completeness_status == current_asof.COMPLETE
    assert blocker is not ShadowDisposition.OUTSIDE_REVIEWED_XG_WINDOW
