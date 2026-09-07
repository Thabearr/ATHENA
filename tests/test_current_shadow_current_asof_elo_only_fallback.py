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
    assert fallback._with_fallback(
        lambda *_args, **_kwargs: original_result,
        history,
        "FOTMOB:42",
        history_sha="5" * 64,
    ) == original_result


def test_install_restore_is_worker_local(monkeypatch):
    sentinel = lambda *_args, **_kwargs: (None, None, (), "kickoff")
    monkeypatch.setattr(
        fallback.binding,
        "_research_xg_from_validated_current_history",
        sentinel,
    )
    hooks = fallback.install()
    try:
        assert hooks.original_research_xg is sentinel
        assert fallback.binding._research_xg_from_validated_current_history is not sentinel
    finally:
        fallback.restore(hooks)
    assert fallback.binding._research_xg_from_validated_current_history is sentinel
