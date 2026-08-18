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
    fixture_id: int = 7_000_001,
    primary_id: int = 999,
    wrapper_id: int = 88_001,
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


def _features() -> dict[str, float]:
    return {
        "home_elo": 1510.0,
        "away_elo": 1490.0,
        "home_form": 0.55,
        "away_form": 0.45,
        "fatigue": 0.0,
    }


def _sealed(
    *,
    fixture_id: int = 7_000_001,
    primary_id: int = 40,
    wrapper_id: int = 88_001,
    kickoff: dt.datetime | None = None,
    observed: dt.datetime | None = None,
    holdout_start: dt.datetime | None = None,
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
    features = _features()
    return fresh.SealedFreshPrediction(
        schema_version=1,
        implementation_state=fresh.IMPLEMENTATION_STATE,
        protocol_sha256=protocol.PROTOCOL_SHA256,
        holdout_start_utc=holdout_start or _start(),
        fixture=fixture,
        bootstrap_projection_sha256=fresh.BOOTSTRAP_PROJECTION_SHA256,
        history_prefix_sha256=ZERO,
        history_prefix_count=2,
        feature_projection_sha256=ONE,
        features=features,
        rates=fresh._rates_from_features(features),
        safety={key: False for key in fresh.SAFETY_KEYS},
    )


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
    return fresh.build_fresh_history_ledger(raw)


def _real_prediction(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fixture_id: int = 7_000_001,
    primary_id: int = 40,
) -> tuple[fresh.FreshHistoryLedger, fresh.SealedFreshPrediction]:
    ledger = _synthetic_ledger(monkeypatch)
    assessment = fresh.build_fresh_prediction_assessment(
        history_ledger=ledger,
        selected_capture=_capture(fixture_id=fixture_id, primary_id=primary_id),
        holdout_start=_start(),
    )
    assert assessment.disposition is fresh.PredictionDisposition.SEALED_COMPLETE_CASE
    assert assessment.sealed_prediction is not None
    return ledger, assessment.sealed_prediction


def _adapter_result(
    prediction: fresh.SealedFreshPrediction,
    *,
    league_id: int | None = None,
    qualified: bool = True,
):
    fixture = prediction.fixture
    first_observed = fixture.kickoff_utc + dt.timedelta(hours=3)
    second_observed = first_observed + dt.timedelta(minutes=10)
    scores: tuple[score_adapter.OrdinaryFtFinishedScore, ...] = ()
    pair_status = score_adapter.AdapterPairStatus.NO_QUALIFIED_ORDINARY_FT_SCORES
    terminal_count = 0
    if qualified:
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
            first_raw_sha256=THREE,
            second_raw_sha256=FOUR,
            first_manifest_sha256=FIVE,
            second_manifest_sha256=SIX,
        )
        scores = (score,)
        pair_status = score_adapter.AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES
        terminal_count = 1
    return score_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterResult(
        schema_version=score_adapter.SCHEMA_VERSION,
        dataset_name=score_adapter.DATASET_NAME,
        adapter_scope=score_adapter.ADAPTER_SCOPE,
        adapter_state=score_adapter.ADAPTER_STATE,
        pair_status=pair_status,
        request_date=fixture.kickoff_utc.strftime("%Y%m%d"),
        timezone="UTC",
        ccode3="NGA",
        first_raw_sha256=THREE,
        second_raw_sha256=FOUR,
        first_manifest_sha256=FIVE,
        second_manifest_sha256=SIX,
        first_observed_at=first_observed,
        second_observed_at=second_observed,
        observation_separation_microseconds=600_000_000,
        first_pr89_assessment_sha256=SEVEN,
        second_pr89_assessment_sha256=EIGHT,
        terminal_candidate_union_count=terminal_count,
        qualified_count=len(scores),
        blocked_fixture_ids_by_status={},
        qualified_scores=scores,
        semantic_scope_rule=score_adapter.SEMANTIC_SCOPE_RULE,
        source_capability_registration_performed=False,
        next_required_boundary=score_adapter.NEXT_REQUIRED_BOUNDARY,
        safety=score_adapter._default_safety(),
    )


def _post_identity(
    prediction: fresh.SealedFreshPrediction,
    *,
    first: bool,
    primary_id: int | None = None,
    wrapper_id: int | None = None,
    kickoff: dt.datetime | None = None,
) -> fresh.QualifiedCaptureFixture:
    fixture = prediction.fixture
    observed = fixture.kickoff_utc + (
        dt.timedelta(hours=3) if first else dt.timedelta(hours=3, minutes=10)
    )
    return fresh.QualifiedCaptureFixture(
        fixture_id=fixture.fixture_id,
        provider_primary_id=(
            fixture.provider_primary_id if primary_id is None else primary_id
        ),
        wrapper_id=fixture.wrapper_id if wrapper_id is None else wrapper_id,
        home_team_id=fixture.home_team_id,
        away_team_id=fixture.away_team_id,
        kickoff_utc=fixture.kickoff_utc if kickoff is None else kickoff,
        capture_observed_at=observed,
        capture_manifest_sha256=FIVE if first else SIX,
        capture_raw_sha256=THREE if first else FOUR,
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


def test_implementation_pins_reviewed_dependencies_and_grants_no_authority() -> None:
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
    assert all(receipt["integrity_guards"].values())


def test_holdout_start_is_first_midnight_strictly_after_merge_and_respects_floor() -> None:
    assert fresh.resolve_holdout_start(
        dt.datetime(2026, 8, 18, 4, 10, tzinfo=UTC)
    ) == dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC)
    assert fresh.resolve_holdout_start(
        dt.datetime(2026, 8, 18, 0, 0, tzinfo=UTC)
    ) == dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC)
    assert fresh.resolve_holdout_start(
        dt.datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    ) == dt.datetime(2026, 8, 15, 0, 0, tzinfo=UTC)
    assert fresh.minimum_gate_boundary(_start()) == dt.datetime(
        2026, 9, 16, 0, 0, tzinfo=UTC
    )
    assert fresh.hard_close_boundary(_start()) == dt.datetime(
        2026, 11, 17, 0, 0, tzinfo=UTC
    )


def test_provider_identity_requires_positive_ids_and_exact_wrapper_match() -> None:
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


def test_capture_selection_uses_earliest_qualifying_capture_and_not_later_drift() -> None:
    kickoff = dt.datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    earliest = _capture(
        kickoff=kickoff,
        observed=dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
        manifest_sha=TWO,
    )
    later_drift = _capture(
        kickoff=kickoff,
        wrapper_id=88_002,
        observed=dt.datetime(2026, 8, 19, 16, 0, tzinfo=UTC),
        manifest_sha=THREE,
    )
    observations = (
        _capture(
            kickoff=kickoff,
            observed=dt.datetime(2026, 8, 18, 23, 59, tzinfo=UTC),
            manifest_sha=ONE,
        ),
        earliest,
        later_drift,
    )
    selected = fresh.select_earliest_qualifying_capture(
        observations, holdout_start=_start()
    )
    assert selected == earliest

    later_kickoff = dt.datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
    too_early = (
        _capture(
            kickoff=later_kickoff,
            observed=dt.datetime(2026, 8, 19, 17, 59, tzinfo=UTC),
        ),
    )
    assert (
        fresh.select_earliest_qualifying_capture(too_early, holdout_start=_start())
        is None
    )
    too_late = (
        _capture(
            kickoff=later_kickoff,
            observed=dt.datetime(2026, 8, 20, 17, 1, tzinfo=UTC),
        ),
    )
    assert (
        fresh.select_earliest_qualifying_capture(too_late, holdout_start=_start())
        is None
    )


def test_capture_selection_fails_when_earliest_capture_is_identity_ambiguous() -> None:
    observed = dt.datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    one = _capture(observed=observed, manifest_sha=ONE)
    two = _capture(observed=observed, wrapper_id=88_002, manifest_sha=TWO)
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="identity-ambiguous"):
        fresh.select_earliest_qualifying_capture((one, two), holdout_start=_start())

    other_fixture = _capture(fixture_id=7_000_002, manifest_sha=THREE)
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="exactly one fixture id"):
        fresh.select_earliest_qualifying_capture(
            (one, other_fixture), holdout_start=_start()
        )


def test_post_seal_change_then_reversion_remains_drifted() -> None:
    prediction = _sealed()
    drift = _post_identity(
        prediction,
        first=True,
        kickoff=prediction.fixture.kickoff_utc + dt.timedelta(hours=1),
    )
    reverted = _post_identity(prediction, first=False)
    assert fresh.post_seal_identity_drifted(prediction, (drift, reverted)) is True
    assert fresh.post_seal_identity_drifted(prediction, (reverted,)) is False


def test_history_ledger_cannot_be_forged_from_correct_metadata_only() -> None:
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="projection identity changed"):
        fresh.FreshHistoryLedger(b"{}\n")
    with pytest.raises(TypeError):
        fresh.FreshHistoryLedger(  # type: ignore[call-arg]
            bootstrap_projection_sha256=fresh.BOOTSTRAP_PROJECTION_SHA256,
            bootstrap_projection_size=fresh.BOOTSTRAP_PROJECTION_SIZE,
            bootstrap_row_count=fresh.BOOTSTRAP_PROJECTION_ROWS,
            rows=(),
        )
    assert fresh.BOOTSTRAP_PROJECTION_ROWS == 21_326
    assert fresh.BOOTSTRAP_PROJECTION_SIZE == 10_545_099
    assert fresh.BOOTSTRAP_PROJECTION_SHA256 == (
        "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
    )


def test_public_prediction_uses_reviewed_constructor_and_exact_frozen_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, sealed = _real_prediction(monkeypatch)
    assert ledger.bootstrap_row_count == 2
    assert sealed.history_prefix_count == 2
    assert sealed.bootstrap_projection_sha256 == fresh.BOOTSTRAP_PROJECTION_SHA256
    assert sealed.features["home_form"] > 0.0
    assert sealed.features["away_form"] > 0.0
    assert dict(sealed.rates) == fresh._rates_from_features(sealed.features)
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


def test_sealed_prediction_rejects_rate_tampering() -> None:
    sealed = _sealed()
    rates = dict(sealed.rates)
    rates["calibrated_home"] += 0.01
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="differs from frozen"):
        dataclasses.replace(sealed, rates=rates)


def test_history_revalidation_rejects_forged_features_even_when_rates_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, sealed = _real_prediction(monkeypatch)
    forged_features = dict(sealed.features)
    forged_features["home_elo"] += 20.0
    forged = dataclasses.replace(
        sealed,
        features=forged_features,
        rates=fresh._rates_from_features(forged_features),
    )
    with pytest.raises(
        fresh.FotMobFreshHoldoutError, match="deterministic reconstruction"
    ):
        fresh.revalidate_sealed_prediction(history_ledger=ledger, prediction=forged)


def test_settlement_reproves_primary_id_wrapper_team_and_kickoff() -> None:
    prediction = _sealed(primary_id=40)
    result = _adapter_result(prediction)
    first = _post_identity(prediction, first=True)
    second = _post_identity(prediction, first=False)
    assessment = fresh._settle_from_revalidated_pair(
        prediction=prediction,
        first_identity=first,
        second_identity=second,
        adapter_result=result,
    )
    assert assessment.disposition is fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT
    settled = assessment.settled_prediction
    assert settled is not None
    assert (settled.home_goals, settled.away_goals) == (2, 1)
    assert settled.legacy_history_state_update is not None
    assert settled.legacy_history_state_update.provider_primary_id == 40

    primary_drift = fresh._settle_from_revalidated_pair(
        prediction=prediction,
        first_identity=first,
        second_identity=_post_identity(prediction, first=False, primary_id=999),
        adapter_result=result,
    )
    assert primary_drift.disposition is (
        fresh.SettlementDisposition.EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT
    )
    assert primary_drift.settled_prediction is None

    kickoff_drift = fresh._settle_from_revalidated_pair(
        prediction=prediction,
        first_identity=first,
        second_identity=_post_identity(
            prediction,
            first=False,
            kickoff=prediction.fixture.kickoff_utc + dt.timedelta(hours=1),
        ),
        adapter_result=result,
    )
    assert kickoff_drift.disposition is (
        fresh.SettlementDisposition.EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT
    )


def test_nonlegacy_ordinary_ft_settlement_never_updates_frozen_history_state() -> None:
    prediction = _sealed(fixture_id=7_000_002, primary_id=999)
    assessment = fresh._settle_from_revalidated_pair(
        prediction=prediction,
        first_identity=_post_identity(prediction, first=True),
        second_identity=_post_identity(prediction, first=False),
        adapter_result=_adapter_result(prediction),
    )
    assert assessment.disposition is fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT
    assert assessment.settled_prediction is not None
    assert assessment.settled_prediction.legacy_history_state_update is None


def test_non_ordinary_ft_result_is_excluded_not_scored() -> None:
    prediction = _sealed()
    assessment = fresh._settle_from_revalidated_pair(
        prediction=prediction,
        first_identity=_post_identity(prediction, first=True),
        second_identity=_post_identity(prediction, first=False),
        adapter_result=_adapter_result(prediction, qualified=False),
    )
    assert assessment.disposition is fresh.SettlementDisposition.EXCLUDED_NOT_REVIEWED_ORDINARY_FT
    assert assessment.settled_prediction is None


def test_public_settlement_revalidates_prediction_before_binding_raw_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, prediction = _real_prediction(monkeypatch, primary_id=40)
    first = _post_identity(prediction, first=True)
    second = _post_identity(prediction, first=False)
    adapter = _adapter_result(prediction)

    def fake_qualify(raw, _manifest):
        return (first,) if raw == b"first" else (second,)

    monkeypatch.setattr(fresh, "qualify_capture_fixtures", fake_qualify)
    monkeypatch.setattr(
        score_adapter,
        "adapt_fotmob_data_matches_ordinary_ft_finished_scores",
        lambda *_args: adapter,
    )
    assessment = fresh.settle_sealed_prediction(
        prediction,
        history_ledger=ledger,
        post_seal_observations=(),
        first_raw_json=b"first",
        first_manifest=object(),  # type: ignore[arg-type]
        second_raw_json=b"second",
        second_manifest=object(),  # type: ignore[arg-type]
    )
    assert assessment.disposition is fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT

    forged_features = dict(prediction.features)
    forged_features["away_elo"] += 30.0
    forged = dataclasses.replace(
        prediction,
        features=forged_features,
        rates=fresh._rates_from_features(forged_features),
    )
    with pytest.raises(
        fresh.FotMobFreshHoldoutError, match="deterministic reconstruction"
    ):
        fresh.settle_sealed_prediction(
            forged,
            history_ledger=ledger,
            post_seal_observations=(),
            first_raw_json=b"first",
            first_manifest=object(),  # type: ignore[arg-type]
            second_raw_json=b"second",
            second_manifest=object(),  # type: ignore[arg-type]
        )


def test_public_settlement_excludes_observed_change_then_revert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, prediction = _real_prediction(monkeypatch, primary_id=40)
    first = _post_identity(prediction, first=True)
    second = _post_identity(prediction, first=False)
    drift = _post_identity(
        prediction,
        first=True,
        wrapper_id=prediction.fixture.wrapper_id + 1,
    )

    monkeypatch.setattr(
        fresh,
        "qualify_capture_fixtures",
        lambda raw, _manifest: (first,) if raw == b"first" else (second,),
    )
    monkeypatch.setattr(
        score_adapter,
        "adapt_fotmob_data_matches_ordinary_ft_finished_scores",
        lambda *_args: pytest.fail("adapter must not run after known post-seal drift"),
    )
    assessment = fresh.settle_sealed_prediction(
        prediction,
        history_ledger=ledger,
        post_seal_observations=(drift,),
        first_raw_json=b"first",
        first_manifest=object(),  # type: ignore[arg-type]
        second_raw_json=b"second",
        second_manifest=object(),  # type: ignore[arg-type]
    )
    assert assessment.disposition is (
        fresh.SettlementDisposition.EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT
    )
    assert assessment.settled_prediction is None


def test_append_history_accepts_only_legacy_settlement_derived_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, legacy = _real_prediction(monkeypatch, primary_id=40)
    legacy_assessment = fresh._settle_from_revalidated_pair(
        prediction=legacy,
        first_identity=_post_identity(legacy, first=True),
        second_identity=_post_identity(legacy, first=False),
        adapter_result=_adapter_result(legacy),
    )
    settled = legacy_assessment.settled_prediction
    assert settled is not None
    updated = fresh.append_fresh_legacy_history_update(ledger, settled)
    assert len(updated.fresh_updates) == 1
    assert updated.fresh_updates[0].fixture_identifier == str(legacy.fixture.fixture_id)

    with pytest.raises(fresh.FotMobFreshHoldoutError):
        fresh.append_fresh_legacy_history_update(updated, settled)

    nonlegacy_assessment = fresh.build_fresh_prediction_assessment(
        history_ledger=ledger,
        selected_capture=_capture(fixture_id=7_000_003, primary_id=999),
        holdout_start=_start(),
    )
    nonlegacy = nonlegacy_assessment.sealed_prediction
    assert nonlegacy is not None
    nonlegacy_settlement = fresh._settle_from_revalidated_pair(
        prediction=nonlegacy,
        first_identity=_post_identity(nonlegacy, first=True),
        second_identity=_post_identity(nonlegacy, first=False),
        adapter_result=_adapter_result(nonlegacy),
    )
    assert nonlegacy_settlement.settled_prediction is not None
    with pytest.raises(fresh.FotMobFreshHoldoutError, match="non-legacy"):
        fresh.append_fresh_legacy_history_update(
            ledger, nonlegacy_settlement.settled_prediction
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
    assert result["decision"] == (
        fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value
    )
    assert result["coverage"]["complete_case_fixture_count"] == 1_000
    assert len(result["coverage"]["qualifying_primary_ids"]) == 8
    assert result["coverage"]["non_legacy_qualifying_primary_ids"] == [900, 901]
    assert result["outcome_or_performance_input_used"] is False


def test_boundary_does_not_require_day_29_and_hard_close_is_exact_day_90() -> None:
    predictions = _coverage_predictions(999)
    before = fresh.evaluate_holdout_boundary(
        predictions,
        holdout_start=_start(),
        boundary=_start() + dt.timedelta(days=27),
    )
    assert before["decision"] == (
        fresh.HoldoutBoundaryDecision.OPEN_BEFORE_MINIMUM_GATE.value
    )

    minimum = fresh.evaluate_holdout_boundary(
        predictions,
        holdout_start=_start(),
        boundary=_start() + dt.timedelta(days=28),
    )
    assert minimum["decision"] == (
        fresh.HoldoutBoundaryDecision.OPEN_WAITING_FOR_COUNT_ONLY_COVERAGE.value
    )

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


def test_close_membership_is_kickoff_exclusive_and_rejects_mixed_holdout_starts() -> None:
    boundary = _start() + dt.timedelta(days=28)
    before = _sealed(
        fixture_id=9_100_001,
        primary_id=40,
        kickoff=boundary - dt.timedelta(seconds=1),
        observed=boundary - dt.timedelta(hours=2),
    )
    at = _sealed(
        fixture_id=9_100_002,
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

    other_start = _sealed(
        fixture_id=9_100_003,
        primary_id=40,
        kickoff=dt.datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
        observed=dt.datetime(2026, 8, 21, 16, 0, tzinfo=UTC),
        holdout_start=dt.datetime(2026, 8, 20, 0, 0, tzinfo=UTC),
    )
    with pytest.raises(
        fresh.FotMobFreshHoldoutError, match="mixes different holdout starts"
    ):
        fresh.coverage_at_boundary(
            (before, other_start),
            holdout_start=_start(),
            boundary=boundary,
        )
