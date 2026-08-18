from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json

import pytest

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol as protocol


UTC = dt.timezone.utc
ZERO = "0" * 64
ONE = "1" * 64
TWO = "2" * 64
THREE = "3" * 64
FOUR = "4" * 64
FIVE = "5" * 64
SIX = "6" * 64
SEVEN = "7" * 64
EIGHT = "8" * 64


def _start() -> dt.datetime:
    return dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC)


def _capture(
    *,
    fixture_id: int = 7000001,
    primary_id: int = 999,
    wrapper_id: int = 88001,
    home_id: int = 101,
    away_id: int = 202,
    kickoff: dt.datetime | None = None,
    observed: dt.datetime | None = None,
    manifest_sha: str = ONE,
    raw_sha: str = TWO,
) -> fresh.QualifiedCaptureFixture:
    kickoff = kickoff or dt.datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
    observed = observed or dt.datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    return fresh.QualifiedCaptureFixture(
        fixture_id=fixture_id,
        provider_primary_id=primary_id,
        wrapper_id=wrapper_id,
        home_team_id=home_id,
        away_team_id=away_id,
        kickoff_utc=kickoff,
        capture_observed_at=observed,
        capture_manifest_sha256=manifest_sha,
        capture_raw_sha256=raw_sha,
    )


def _history(
    fixture_id: int,
    home: int,
    away: int,
    kickoff: dt.datetime,
    observed: dt.datetime,
    home_goals: int,
    away_goals: int,
) -> fresh.FreshHistoryResult:
    return fresh.FreshHistoryResult(
        fixture_identifier=str(fixture_id),
        home_team_id=home,
        away_team_id=away,
        kickoff_utc=kickoff,
        home_goals=home_goals,
        away_goals=away_goals,
        observed_at=observed,
        evidence_sha256=hashlib.sha256(f"history:{fixture_id}".encode()).hexdigest(),
        evidence_reference=f"synthetic-reviewed-history:{fixture_id}",
        provider_primary_id=None,
        source_kind="REVIEWED_PR119_BOOTSTRAP",
    )


def _sealed(
    *,
    fixture_id: int = 7000001,
    primary_id: int = 40,
    wrapper_id: int = 88001,
    kickoff: dt.datetime | None = None,
    observed: dt.datetime | None = None,
) -> fresh.SealedFreshPrediction:
    fixture = _capture(
        fixture_id=fixture_id,
        primary_id=primary_id,
        wrapper_id=wrapper_id,
        kickoff=kickoff,
        observed=observed,
        manifest_sha=hashlib.sha256(f"manifest:{fixture_id}".encode()).hexdigest(),
        raw_sha=hashlib.sha256(f"raw:{fixture_id}".encode()).hexdigest(),
    )
    return fresh.SealedFreshPrediction(
        schema_version=1,
        implementation_state=fresh.IMPLEMENTATION_STATE,
        protocol_sha256=protocol.PROTOCOL_SHA256,
        holdout_start_utc=_start(),
        fixture=fixture,
        history_prefix_sha256=ZERO,
        history_prefix_count=2,
        feature_projection_sha256=ONE,
        features={
            "home_elo": 1510.0,
            "away_elo": 1490.0,
            "home_form": 0.55,
            "away_form": 0.45,
            "fatigue": 0.0,
        },
        rates={
            "native_home": 1.5,
            "native_away": 1.1,
            "elo_only_home": 1.4,
            "elo_only_away": 1.0,
            "calibrated_home": 1.45,
            "calibrated_away": 1.1,
        },
        safety={key: False for key in fresh.SAFETY_KEYS},
    )


def _adapter_result(prediction: fresh.SealedFreshPrediction, *, league_id: int | None = None):
    fixture = prediction.fixture
    first_observed = fixture.kickoff_utc + dt.timedelta(hours=3)
    second_observed = first_observed + dt.timedelta(minutes=10)
    first_raw = THREE
    second_raw = FOUR
    first_manifest = FIVE
    second_manifest = SIX
    score = score_adapter.OrdinaryFtFinishedScore(
        fixture_id=fixture.fixture_id,
        league_id=league_id if league_id is not None else fixture.wrapper_id,
        home_team_id=fixture.home_team_id,
        away_team_id=fixture.away_team_id,
        kickoff_utc=fixture.kickoff_utc,
        home_score=2,
        away_score=1,
        reason=dict(score_adapter.ORDINARY_FT_REASON_TUPLE),
        first_observed_at=first_observed,
        second_observed_at=second_observed,
        first_raw_sha256=first_raw,
        second_raw_sha256=second_raw,
        first_manifest_sha256=first_manifest,
        second_manifest_sha256=second_manifest,
    )
    return score_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult(
        schema_version=score_adapter.SCHEMA_VERSION,
        dataset_name=score_adapter.DATASET_NAME,
        adapter_scope=score_adapter.ADAPTER_SCOPE,
        adapter_state=score_adapter.ADAPTER_STATE,
        pair_status=score_adapter.AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES,
        request_date=fixture.kickoff_utc.strftime("%Y%m%d"),
        timezone="UTC",
        ccode3="NGA",
        first_raw_sha256=first_raw,
        second_raw_sha256=second_raw,
        first_manifest_sha256=first_manifest,
        second_manifest_sha256=second_manifest,
        first_observed_at=first_observed,
        second_observed_at=second_observed,
        observation_separation_microseconds=600_000_000,
        first_pr89_assessment_sha256=SEVEN,
        second_pr89_assessment_sha256=EIGHT,
        terminal_candidate_union_count=1,
        qualified_count=1,
        blocked_fixture_ids_by_status={},
        qualified_scores=(score,),
        semantic_scope_rule=score_adapter.SEMANTIC_SCOPE_RULE,
        source_capability_registration_performed=False,
        next_required_boundary=score_adapter.NEXT_REQUIRED_BOUNDARY,
        safety=score_adapter._default_safety(),
    )


def _payload(
    *,
    league_id: int = 88,
    primary_id: int = 999,
    match_league_id: int | None = None,
    fixture_id: int = 7001,
):
    return {
        "leagues": [
            {
                "id": league_id,
                "primaryId": primary_id,
                "matches": [
                    {
                        "id": fixture_id,
                        "leagueId": league_id if match_league_id is None else match_league_id,
                        "home": {"id": 101},
                        "away": {"id": 202},
                        "status": {"utcTime": "2026-08-20T18:00:00Z"},
                    }
                ],
            }
        ]
    }


def _payload_bytes(payload) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def test_implementation_pins_exact_reviewed_dependencies_and_grants_no_authority() -> None:
    fresh.verify_reviewed_dependencies()
    receipt = fresh.implementation_receipt()
    assert receipt["implementation_state"] == fresh.IMPLEMENTATION_STATE
    assert receipt["protocol"] == {
        "id": protocol.PROTOCOL_ID,
        "sha256": protocol.PROTOCOL_SHA256,
        "size_bytes": protocol.PROTOCOL_SIZE,
        "blob_sha": fresh.PR148_PROTOCOL_BLOB_SHA,
    }
    assert receipt["network_acquisition_performed"] is False
    assert receipt["fresh_holdout_started"] is False
    assert receipt["next_required_boundary"] == fresh.NEXT_REQUIRED_BOUNDARY
    assert all(value is False for value in receipt["safety"].values())


def test_holdout_start_is_first_midnight_strictly_after_merge_and_respects_floor() -> None:
    assert fresh.resolve_holdout_start(dt.datetime(2026, 8, 18, 4, 10, tzinfo=UTC)) == dt.datetime(
        2026, 8, 19, 0, 0, tzinfo=UTC
    )
    assert fresh.resolve_holdout_start(dt.datetime(2026, 8, 18, 0, 0, tzinfo=UTC)) == dt.datetime(
        2026, 8, 19, 0, 0, tzinfo=UTC
    )
    assert fresh.resolve_holdout_start(dt.datetime(2026, 8, 14, 12, 0, tzinfo=UTC)) == dt.datetime(
        2026, 8, 15, 0, 0, tzinfo=UTC
    )
    assert fresh.minimum_gate_boundary(_start()) == dt.datetime(2026, 9, 16, 0, 0, tzinfo=UTC)
    assert fresh.hard_close_boundary(_start()) == dt.datetime(2026, 11, 17, 0, 0, tzinfo=UTC)


def test_provider_identity_requires_exact_positive_ids_and_wrapper_match() -> None:
    raw = _payload_bytes(_payload())
    rows = fresh._qualify_provider_identity_payload(
        raw,
        capture_observed_at=dt.datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
        capture_manifest_sha256=ONE,
        capture_raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    assert len(rows) == 1
    assert rows[0].provider_primary_id == 999
    assert rows[0].wrapper_id == 88
    assert rows[0].fixture_id == 7001

    bad = _payload_bytes(_payload(match_league_id=89))
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="match.leagueId"):
        fresh._qualify_provider_identity_payload(
            bad,
            capture_observed_at=dt.datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
            capture_manifest_sha256=ONE,
            capture_raw_sha256=hashlib.sha256(bad).hexdigest(),
        )

    zero = _payload_bytes(_payload(fixture_id=0))
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="match.id"):
        fresh._qualify_provider_identity_payload(
            zero,
            capture_observed_at=dt.datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
            capture_manifest_sha256=ONE,
            capture_raw_sha256=hashlib.sha256(zero).hexdigest(),
        )


def test_provider_identity_rejects_duplicate_wrapper_and_duplicate_json_keys() -> None:
    payload = _payload()
    payload["leagues"].append({"id": 88, "primaryId": 1000, "matches": []})
    raw = _payload_bytes(payload)
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="wrapper id duplicated"):
        fresh._qualify_provider_identity_payload(
            raw,
            capture_observed_at=dt.datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
            capture_manifest_sha256=ONE,
            capture_raw_sha256=hashlib.sha256(raw).hexdigest(),
        )

    duplicate = b'{"leagues":[],"leagues":[]}'
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="duplicate JSON key"):
        fresh._qualify_provider_identity_payload(
            duplicate,
            capture_observed_at=dt.datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
            capture_manifest_sha256=ONE,
            capture_raw_sha256=hashlib.sha256(duplicate).hexdigest(),
        )


def test_capture_selection_excludes_prestart_and_uses_earliest_qualifying_observation() -> None:
    kickoff = dt.datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    observations = (
        _capture(
            kickoff=kickoff,
            observed=dt.datetime(2026, 8, 18, 23, 59, tzinfo=UTC),
            manifest_sha=ONE,
        ),
        _capture(
            kickoff=kickoff,
            observed=dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
            manifest_sha=TWO,
        ),
        _capture(
            kickoff=kickoff,
            observed=dt.datetime(2026, 8, 19, 16, 0, tzinfo=UTC),
            manifest_sha=THREE,
        ),
    )
    selected = fresh.select_earliest_qualifying_capture(observations, holdout_start=_start())
    assert selected is not None
    assert selected.capture_observed_at == dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC)
    assert selected.capture_manifest_sha256 == TWO

    later_kickoff = dt.datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
    too_early = (
        _capture(
            kickoff=later_kickoff,
            observed=dt.datetime(2026, 8, 19, 17, 59, tzinfo=UTC),
        ),
    )
    assert fresh.select_earliest_qualifying_capture(too_early, holdout_start=_start()) is None
    too_late = (
        _capture(
            kickoff=later_kickoff,
            observed=dt.datetime(2026, 8, 20, 17, 1, tzinfo=UTC),
        ),
    )
    assert fresh.select_earliest_qualifying_capture(too_late, holdout_start=_start()) is None


def test_capture_selection_fails_closed_on_identity_drift() -> None:
    one = _capture(manifest_sha=ONE)
    two = _capture(wrapper_id=88002, manifest_sha=TWO)
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="disagree on sealed"):
        fresh.select_earliest_qualifying_capture((one, two), holdout_start=_start())


def test_public_prediction_path_requires_reviewed_history_ledger_ancestry() -> None:
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="history_ledger"):
        fresh.build_fresh_prediction_assessment(
            history_ledger=(),  # type: ignore[arg-type]
            selected_capture=_capture(),
            holdout_start=_start(),
        )


def test_prediction_uses_reviewed_utc_native_features_and_frozen_calibration() -> None:
    history = (
        _history(
            6001,
            101,
            303,
            dt.datetime(2026, 8, 17, 18, 0, tzinfo=UTC),
            dt.datetime(2026, 8, 17, 20, 0, tzinfo=UTC),
            2,
            0,
        ),
        _history(
            6002,
            202,
            404,
            dt.datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            1,
            1,
        ),
    )
    assessment = fresh._build_fresh_prediction_assessment_from_rows(
        history=history,
        selected_capture=_capture(),
        holdout_start=_start(),
    )
    assert assessment.disposition is fresh.PredictionDisposition.SEALED_COMPLETE_CASE
    assert assessment.missing_feature_ids == ()
    sealed = assessment.sealed_prediction
    assert sealed is not None
    assert sealed.history_prefix_count == 2
    assert sealed.features["home_form"] > 0.0
    assert sealed.features["away_form"] > 0.0
    assert sealed.rates["calibrated_home"] == protocol.apply_frozen_home_calibration(
        sealed.rates["native_home"]
    )
    assert sealed.rates["calibrated_away"] == sealed.rates["native_away"]
    assert all(value is False for value in sealed.safety.values())
    assert fresh.sha256_sealed_fresh_prediction(sealed) == hashlib.sha256(
        fresh.canonical_sealed_fresh_prediction_bytes(sealed)
    ).hexdigest()


def test_prediction_reports_missing_features_instead_of_imputing() -> None:
    assessment = fresh._build_fresh_prediction_assessment_from_rows(
        history=(),
        selected_capture=_capture(),
        holdout_start=_start(),
    )
    assert assessment.disposition is fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES
    assert assessment.sealed_prediction is None
    assert assessment.missing_feature_ids == ("away_form", "fatigue", "home_form")


def test_prediction_does_not_use_prior_result_not_observed_by_capture_as_of() -> None:
    capture = _capture()
    late = _history(
        6001,
        101,
        202,
        dt.datetime(2026, 8, 19, 10, 0, tzinfo=UTC),
        dt.datetime(2026, 8, 20, 17, 0, tzinfo=UTC),
        1,
        0,
    )
    assessment = fresh._build_fresh_prediction_assessment_from_rows(
        history=(late,),
        selected_capture=capture,
        holdout_start=_start(),
    )
    assert assessment.disposition is fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES
    assert assessment.sealed_prediction is None


def test_sealed_prediction_constructor_itself_enforces_holdout_and_capture_window() -> None:
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="precedes the frozen"):
        dataclasses.replace(
            _sealed(), holdout_start_utc=dt.datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
        )
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="pre-kickoff window"):
        dataclasses.replace(
            _sealed(),
            fixture=_capture(
                primary_id=40,
                kickoff=dt.datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
                observed=dt.datetime(2026, 8, 20, 17, 30, tzinfo=UTC),
            ),
        )


def test_reviewed_ordinary_ft_settlement_updates_history_only_for_legacy_primary_ids() -> None:
    legacy = _sealed(primary_id=40)
    settled = fresh.settle_sealed_prediction(legacy, _adapter_result(legacy))
    assert (settled.home_goals, settled.away_goals) == (2, 1)
    assert settled.legacy_history_state_update is not None
    assert settled.legacy_history_state_update.provider_primary_id == 40
    assert settled.legacy_history_state_update.source_kind == (
        "FRESH_REVIEWED_ORDINARY_FT_LEGACY_UPDATE"
    )

    nonlegacy = _sealed(fixture_id=7000002, primary_id=999)
    nonlegacy_settled = fresh.settle_sealed_prediction(
        nonlegacy, _adapter_result(nonlegacy)
    )
    assert nonlegacy_settled.legacy_history_state_update is None


def test_settlement_requires_exact_wrapper_team_fixture_and_kickoff_identity() -> None:
    prediction = _sealed()
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="settlement identity"):
        fresh.settle_sealed_prediction(
            prediction,
            _adapter_result(prediction, league_id=prediction.fixture.wrapper_id + 1),
        )


def _coverage_predictions(count: int) -> tuple[fresh.SealedFreshPrediction, ...]:
    primary_ids = (40, 47, 53, 54, 55, 57, 900, 901)
    start = _start()
    output = []
    for index in range(count):
        primary = primary_ids[index % len(primary_ids)]
        kickoff = start + dt.timedelta(days=1 + (index % 20), hours=12)
        observed = kickoff - dt.timedelta(hours=2)
        output.append(
            _sealed(
                fixture_id=8_000_000 + index,
                primary_id=primary,
                wrapper_id=90_000 + primary,
                kickoff=kickoff,
                observed=observed,
            )
        )
    return tuple(output)


def test_count_only_boundary_closes_at_exact_28_day_boundary_when_coverage_passes() -> None:
    predictions = _coverage_predictions(1_000)
    minimum = fresh.minimum_gate_boundary(_start())
    result = fresh.evaluate_holdout_boundary(
        predictions,
        holdout_start=_start(),
        boundary=minimum,
    )
    assert result["decision"] == fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value
    assert result["coverage"]["complete_case_fixture_count"] == 1_000
    assert len(result["coverage"]["qualifying_primary_ids"]) == 8
    assert result["coverage"]["non_legacy_qualifying_primary_ids"] == [900, 901]
    assert result["outcome_or_performance_input_used"] is False


def test_boundary_does_not_accidentally_require_day_29_and_hard_close_is_exact_day_90() -> None:
    predictions = _coverage_predictions(999)
    before = fresh.evaluate_holdout_boundary(
        predictions,
        holdout_start=_start(),
        boundary=_start() + dt.timedelta(days=27),
    )
    assert before["decision"] == fresh.HoldoutBoundaryDecision.OPEN_BEFORE_MINIMUM_GATE.value

    minimum = fresh.evaluate_holdout_boundary(
        predictions,
        holdout_start=_start(),
        boundary=_start() + dt.timedelta(days=28),
    )
    assert minimum["decision"] == fresh.HoldoutBoundaryDecision.OPEN_WAITING_FOR_COUNT_ONLY_COVERAGE.value

    hard = fresh.evaluate_holdout_boundary(
        predictions,
        holdout_start=_start(),
        boundary=_start() + dt.timedelta(days=90),
    )
    assert hard["decision"] == (
        fresh.HoldoutBoundaryDecision.CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION.value
    )
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="after the frozen hard close"):
        fresh.evaluate_holdout_boundary(
            predictions,
            holdout_start=_start(),
            boundary=_start() + dt.timedelta(days=91),
        )


def test_close_membership_is_kickoff_exclusive_at_selected_boundary() -> None:
    boundary = _start() + dt.timedelta(days=28)
    before = _sealed(
        fixture_id=9100001,
        primary_id=40,
        kickoff=boundary - dt.timedelta(seconds=1),
        observed=boundary - dt.timedelta(hours=2),
    )
    at = _sealed(
        fixture_id=9100002,
        primary_id=40,
        kickoff=boundary,
        observed=boundary - dt.timedelta(hours=2),
    )
    coverage = fresh.coverage_at_boundary(
        (before, at),
        holdout_start=_start(),
        boundary=boundary,
    )
    assert coverage["complete_case_fixture_count"] == 1
    assert coverage["primary_id_counts"] == {"40": 1}


def test_bootstrap_loader_fails_closed_on_any_non_exact_projection() -> None:
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="projection identity changed"):
        fresh.parse_reviewed_legacy_bootstrap_projection(b"{}\n")
    assert fresh.BOOTSTRAP_PROJECTION_ROWS == 21_326
    assert fresh.BOOTSTRAP_PROJECTION_SIZE == 10_545_099
    assert fresh.BOOTSTRAP_PROJECTION_SHA256 == (
        "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
    )
