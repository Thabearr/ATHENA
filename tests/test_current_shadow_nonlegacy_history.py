"""Synthetic mathematics tests are not real-source issuance evidence."""
import dataclasses
import datetime as dt
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_shadow_nonlegacy_history as lane


helpers = runpy.run_path(str(Path(__file__).with_name(
    "test_fotmob_utc_native_expected_goals_fresh_holdout.py")))
UTC = dt.timezone.utc


def target():
    return helpers["_capture"](
        fixture_id=900, primary_id=999,
        kickoff=dt.datetime(2026, 8, 25, 18, tzinfo=UTC),
        observed=dt.datetime(2026, 8, 25, 16, tzinfo=UTC),
    )


def result(identity=1, **changes):
    prediction = helpers["_sealed"](fixture_id=identity, primary_id=999)
    return lane.fresh.SettledFreshPrediction(**{
        "prediction": prediction,
        "home_goals": 2, "away_goals": 0,
        "settlement_observed_at": dt.datetime(2026, 8, 20, 21, tzinfo=UTC),
        "settlement_evidence_sha256": "a" * 64,
        "ordinary_ft_first_raw_sha256": "1" * 64,
        "ordinary_ft_second_raw_sha256": "2" * 64,
        "ordinary_ft_first_manifest_sha256": "3" * 64,
        "ordinary_ft_second_manifest_sha256": "4" * 64,
        "legacy_history_state_update": None, **changes,
    })


def test_exact_team_results_use_existing_one_match_minimum():
    features, coverage, evidence = lane._project((result(),), target())
    assert features == {"home_form": .95, "away_form": .1, "fatigue": 0.0}
    assert [r["history_row_count"] for r in coverage] == [1, 1]
    assert evidence[0]["fixture_id"] == 1
    assert all(not c["complete_competition_history_claimed"] for c in coverage)


def test_empty_history_never_imputes():
    features, coverage, evidence = lane._project((), target())
    assert features == {} and evidence == []
    assert all(c["coverage_status"] == "NO_REVIEWED_HISTORY" for c in coverage)


def test_fatigue_uses_reviewed_rest_differential():
    rows = []
    for identity, team, opponent, day in ((1, 101, 303, 23), (2, 202, 404, 20)):
        kickoff = dt.datetime(2026, 8, day, 18, tzinfo=UTC)
        prediction = helpers["_sealed"](fixture_id=identity, primary_id=999,
            kickoff=kickoff, observed=kickoff-dt.timedelta(hours=2))
        prediction = dataclasses.replace(prediction, fixture=dataclasses.replace(
            prediction.fixture, home_team_id=team, away_team_id=opponent))
        rows.append(result(identity, prediction=prediction,
            settlement_observed_at=kickoff+dt.timedelta(hours=3)))
    features, _, evidence = lane._project(tuple(reversed(rows)), target())
    assert features["fatigue"] == .30
    assert features == lane._project(tuple(rows), target())[0]
    assert evidence == lane._project(tuple(rows), target())[2]


@pytest.mark.parametrize("field,value", [
    ("home_team_id", 501), ("away_team_id", 502), ("provider_primary_id", 1000),
])
def test_identity_and_competition_scope(field, value):
    original = result()
    fixture = dataclasses.replace(original.prediction.fixture, **{field: value})
    changed = dataclasses.replace(original, prediction=dataclasses.replace(original.prediction, fixture=fixture))
    features, _, _ = lane._project((changed,), target())
    if field == "provider_primary_id":
        assert features == {}
    else:
        assert "fatigue" not in features
        assert ("home_form" if field == "home_team_id" else "away_form") not in features


def test_orientation_is_not_display_name_matching():
    original = result()
    fixture = dataclasses.replace(original.prediction.fixture, home_team_id=202, away_team_id=101)
    changed = dataclasses.replace(original, prediction=dataclasses.replace(original.prediction, fixture=fixture))
    features, _, _ = lane._project((changed,), target())
    assert features["home_form"] == .1 and features["away_form"] == .95


@pytest.mark.parametrize("change", ["duplicate", "conflict", "self", "future_observed", "future_kickoff"])
def test_invalid_prefix_fails_closed(change):
    rows = (result(),)
    current = target()
    if change == "duplicate": rows += rows
    if change == "conflict": rows += (result(home_goals=3),)
    if change == "self": current = dataclasses.replace(current, fixture_id=1)
    if change == "future_observed": rows = (result(settlement_observed_at=current.capture_observed_at + dt.timedelta(seconds=1)),)
    if change == "future_kickoff": current = dataclasses.replace(current, kickoff_utc=rows[0].prediction.fixture.kickoff_utc)
    with pytest.raises(lane.CurrentNonlegacyHistoryError):
        lane._project(rows, current)


@pytest.mark.parametrize("value", [-1, True, 1.5, "2", None])
def test_malformed_score_rejected(value):
    with pytest.raises(ValueError): result(home_goals=value)


def test_missing_observation_rejected():
    with pytest.raises(ValueError): result(settlement_observed_at=None)


@pytest.mark.parametrize("fake", [{}, {"odds": 2.0}, {"history_sha256": "a" * 64}, SimpleNamespace()])
def test_detached_inputs_cannot_issue_features(fake):
    with pytest.raises(lane.CurrentNonlegacyHistoryError, match="IDENTITY_UNPROVEN"):
        lane.build_current_nonlegacy_features(fake, "FOTMOB:900")


def test_contract_drift(monkeypatch):
    lane.verify_contract()
    monkeypatch.setitem(lane.CONTRACT, "minimum_matches_per_team", 0)
    with pytest.raises(lane.CurrentNonlegacyHistoryError, match="drift"):
        lane.verify_contract()


@pytest.mark.parametrize("fixture_id,home,away,primary", [
    (5107591,8127,9893,67), (5107592,10237,8349,67), (5107596,9892,9802,67),
    (5739505,8113,10202,46), (5837137,45729,158319,108), (5970127,2529,1699505,536),
])
def test_run214_identities_do_not_manufacture_coverage(fixture_id, home, away, primary):
    current = dataclasses.replace(target(), fixture_id=fixture_id,
        home_team_id=home, away_team_id=away, provider_primary_id=primary)
    features, coverage, _ = lane._project((result(),), current)
    assert not features
    assert all(c["history_row_count"] == 0 for c in coverage)


def test_worker_prefers_complete_new_issuance_before_elo(monkeypatch):
    from scripts import current_shadow_current_asof_elo_only_fallback as hook
    from domain._all_market_shadow_types import ShadowDisposition
    fixture = target()
    row = SimpleNamespace(fixture_identifier="FOTMOB:900", fixture=fixture,
        disposition=hook.current_shadow.MISSING_REVIEWED_FEATURES)
    history = SimpleNamespace(shadow_handoff=SimpleNamespace(rows=(row,),
        source_bundle=object(), fixture_review_policy_id="synthetic"))
    monkeypatch.setattr(hook.current_shadow, "_history_ledger", lambda _: (object(), 0))
    full = SimpleNamespace(disposition=hook.current_asof.CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES,
        features={"home_elo": 1500., "away_elo": 1500.},
        missing_feature_ids=("away_form", "fatigue", "home_form"))
    monkeypatch.setattr(hook.current_asof, "build_current_asof_xg_assessment", lambda **_: full)
    receipt = lane._canonical({"status": lane.COMPLETE, "history_sha256": "a"*64,
        "rates": {"calibrated_home": 1.2, "calibrated_away": .9}})
    monkeypatch.setattr(lane, "build_current_nonlegacy_features", lambda *_: receipt)
    def forbidden(*_):
        raise AssertionError("complete current issuance must precede Elo fallback")
    monkeypatch.setattr(hook.elo_only, "build_current_asof_elo_only_xg_assessment", forbidden)
    old = (None, ShadowDisposition.MISSING_REQUIRED_INPUT, full.missing_feature_ids,
        "2026-08-25T18:00:00.000000Z")
    value = hook._with_fallback(lambda *_a, **_k: old, history, "FOTMOB:900", history_sha="a"*64)
    assert value[0].completeness_status == lane.COMPLETE
    assert value[1] is None
