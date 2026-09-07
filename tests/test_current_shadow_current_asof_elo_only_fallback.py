from __future__ import annotations

from types import SimpleNamespace

from domain import current_fotmob_utc_native_current_asof_elo_only as elo_only
from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import current_fotmob_utc_native_shadow_prediction as current_shadow
from domain._all_market_shadow_types import ShadowDisposition
from scripts import current_shadow_current_asof_elo_only_fallback as fallback


def _source_assessment():
    return SimpleNamespace(
        disposition=current_asof.CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES,
        missing_feature_ids=("fatigue", "home_form"),
        features={"home_elo": 1512.0, "away_elo": 1488.0},
    )


def test_worker_hook_recovers_only_current_asof_missing_full_model(monkeypatch):
    fixture = object()
    row = SimpleNamespace(
        fixture_identifier="FOTMOB:42",
        fixture=fixture,
        disposition=current_shadow.OUTSIDE_REVIEWED_SEAL_WINDOW,
    )
    history = SimpleNamespace(
        shadow_handoff=SimpleNamespace(
            rows=(row,),
            source_bundle=object(),
            fixture_review_policy_id="policy",
        )
    )
    original_result = (
        None,
        ShadowDisposition.MISSING_REQUIRED_INPUT,
        ("home_form",),
        "2026-09-08T18:00:00.000000Z",
    )

    monkeypatch.setattr(
        current_shadow,
        "_history_ledger",
        lambda _source: (object(), 0),
    )
    monkeypatch.setattr(
        current_asof,
        "build_current_asof_xg_assessment",
        lambda **_kwargs: _source_assessment(),
    )
    reduced = SimpleNamespace(
        rates={"elo_only_home": 1.21, "elo_only_away": 0.97},
        feature_projection_sha256="3" * 64,
        history_prefix_sha256="4" * 64,
    )
    monkeypatch.setattr(
        elo_only,
        "build_current_asof_elo_only_xg_assessment",
        lambda _source: reduced,
    )

    fallback._DIAGNOSTIC_ROWS.clear()
    result = fallback._with_fallback(
        lambda *_args, **_kwargs: original_result,
        history,
        "FOTMOB:42",
        history_sha="5" * 64,
    )
    rates, blocker, missing, kickoff = result
    assert blocker is None
    assert missing == ()
    assert kickoff == original_result[3]
    assert rates.calibrated_home == 1.21
    assert rates.calibrated_away == 0.97
    assert rates.feature_projection_identity == "3" * 64
    assert rates.history_prefix_identity == "4" * 64
    assert rates.source_fixture_identity == "FOTMOB:42"
    assert rates.completeness_status == elo_only.COMPLETE

    diagnostic = fallback.diagnostic_summary()
    assert diagnostic["fixture_count"] == 1
    assert diagnostic["state_counts"] == {"ELO_ONLY_APPLIED": 1}
    assert diagnostic["fixtures"][0]["fixture_identity"] == "FOTMOB:42"
    assert diagnostic["fixtures"][0]["full_missing_feature_ids"] == [
        "fatigue",
        "home_form",
    ]
    assert diagnostic["fixtures"][0]["full_available_feature_ids"] == [
        "away_elo",
        "home_elo",
    ]
    assert diagnostic["fixtures"][0]["fallback_applied"] is True
    assert diagnostic["wager_placed"] is False


def test_worker_hook_records_reviewed_elo_unavailable_without_broadening(monkeypatch):
    row = SimpleNamespace(
        fixture_identifier="FOTMOB:77",
        fixture=object(),
        disposition=current_shadow.OUTSIDE_REVIEWED_SEAL_WINDOW,
    )
    history = SimpleNamespace(
        shadow_handoff=SimpleNamespace(
            rows=(row,),
            source_bundle=object(),
            fixture_review_policy_id="policy",
        )
    )
    original_result = (
        None,
        ShadowDisposition.MISSING_REQUIRED_INPUT,
        ("home_elo",),
        "2026-09-08T18:00:00.000000Z",
    )
    monkeypatch.setattr(
        current_shadow,
        "_history_ledger",
        lambda _source: (object(), 0),
    )

    def fail(**_kwargs):
        raise current_asof.CurrentAsOfXGError("reviewed Elo unexpectedly became missing")

    monkeypatch.setattr(current_asof, "build_current_asof_xg_assessment", fail)
    fallback._DIAGNOSTIC_ROWS.clear()
    result = fallback._with_fallback(
        lambda *_args, **_kwargs: original_result,
        history,
        "FOTMOB:77",
        history_sha="6" * 64,
    )
    assert result == original_result
    diagnostic = fallback.diagnostic_summary()
    assert diagnostic["state_counts"] == {"CURRENT_ASOF_ASSESSMENT_ERROR": 1}
    row_value = diagnostic["fixtures"][0]
    assert row_value["error_code"] == "REVIEWED_ELO_UNAVAILABLE"
    assert row_value["error_type"] == "CurrentAsOfXGError"
    assert row_value["fallback_applied"] is False
    assert row_value["base_missing_feature_ids"] == ["home_elo"]


def test_worker_hook_does_not_override_other_missing_input_dispositions(monkeypatch):
    row = SimpleNamespace(
        fixture_identifier="FOTMOB:42",
        fixture=object(),
        disposition=current_shadow.MISSING_REVIEWED_FEATURES,
    )
    history = SimpleNamespace(
        shadow_handoff=SimpleNamespace(rows=(row,), source_bundle=object())
    )
    original_result = (
        None,
        ShadowDisposition.MISSING_REQUIRED_INPUT,
        ("home_form",),
        "2026-09-08T18:00:00.000000Z",
    )
    fallback._DIAGNOSTIC_ROWS.clear()
    assert fallback._with_fallback(
        lambda *_args, **_kwargs: original_result,
        history,
        "FOTMOB:42",
        history_sha="5" * 64,
    ) == original_result
    diagnostic = fallback.diagnostic_summary()
    assert diagnostic["state_counts"] == {"ROW_NOT_OUTSIDE_REVIEWED_SEAL_WINDOW": 1}


def test_install_restore_is_worker_local_and_install_resets_diagnostics(monkeypatch):
    sentinel = lambda *_args, **_kwargs: (None, None, (), "kickoff")
    monkeypatch.setattr(
        fallback.binding,
        "_research_xg_from_validated_current_history",
        sentinel,
    )
    fallback._DIAGNOSTIC_ROWS["FOTMOB:stale"] = {"state": "stale"}
    hooks = fallback.install()
    try:
        assert hooks.original_research_xg is sentinel
        assert fallback.binding._research_xg_from_validated_current_history is not sentinel
        assert fallback.diagnostic_summary()["fixture_count"] == 0
    finally:
        fallback.restore(hooks)
    assert fallback.binding._research_xg_from_validated_current_history is sentinel
