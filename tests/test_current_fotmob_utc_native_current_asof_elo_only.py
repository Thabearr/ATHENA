from __future__ import annotations

import datetime as dt
import math

import pytest

from domain import current_fotmob_fixture_review_policy as fixture_policy
from domain import current_fotmob_utc_native_current_asof_elo_only as elo_only
from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain import (
    fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol
    as pr148,
)


UTC = dt.timezone.utc


def _fixture() -> fresh.QualifiedCaptureFixture:
    return fresh.QualifiedCaptureFixture(
        fixture_id=9_000_001,
        provider_primary_id=40,
        wrapper_id=88_001,
        home_team_id=101,
        away_team_id=202,
        kickoff_utc=dt.datetime(2026, 9, 8, 18, 0, tzinfo=UTC),
        capture_observed_at=dt.datetime(2026, 9, 7, 12, 0, tzinfo=UTC),
        capture_manifest_sha256="1" * 64,
        capture_raw_sha256="2" * 64,
    )


def _missing_assessment() -> current_asof.CurrentAsOfXGAssessment:
    return current_asof.CurrentAsOfXGAssessment(
        schema_version=current_asof.SCHEMA_VERSION,
        dataset_name=current_asof.DATASET_NAME,
        status=current_asof.STATUS,
        disposition=current_asof.CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES,
        fixture=_fixture(),
        fixture_review_policy_id=fixture_policy.SHADOW_POLICY_ID,
        history_prefix_sha256="3" * 64,
        history_prefix_count=0,
        feature_projection_sha256="4" * 64,
        missing_feature_ids=("away_form", "fatigue", "home_form"),
        features={"home_elo": 1500.0, "away_elo": 1500.0},
        rates={},
        authority=current_asof._AUTHORITY,
    )


def test_elo_only_fallback_uses_only_reviewed_elo_and_frozen_coefficients() -> None:
    assessment = elo_only.build_current_asof_elo_only_xg_assessment(
        _missing_assessment()
    )

    assert assessment.completeness_status == elo_only.COMPLETE
    assert assessment.model_id == "FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM"
    assert assessment.features == {"home_elo": 1500.0, "away_elo": 1500.0}
    assert assessment.missing_full_model_feature_ids == (
        "away_form",
        "fatigue",
        "home_form",
    )
    assert assessment.rates["elo_only_home"] == math.exp(
        pr148.ELO_ONLY_HOME_COEFFICIENTS[0]
    )
    assert assessment.rates["elo_only_away"] == math.exp(
        pr148.ELO_ONLY_AWAY_COEFFICIENTS[0]
    )
    assert all(value is False for value in assessment.authority.values())
    payload = assessment.to_dict()
    assert payload["wager_placed"] is False
    assert payload["missing_full_model_feature_ids"] == [
        "away_form",
        "fatigue",
        "home_form",
    ]


def test_elo_only_fallback_does_not_accept_complete_full_model() -> None:
    source = _missing_assessment()
    complete = current_asof.CurrentAsOfXGAssessment(
        schema_version=source.schema_version,
        dataset_name=source.dataset_name,
        status=source.status,
        disposition=current_asof.CurrentAsOfXGDisposition.COMPLETE,
        fixture=source.fixture,
        fixture_review_policy_id=source.fixture_review_policy_id,
        history_prefix_sha256=source.history_prefix_sha256,
        history_prefix_count=source.history_prefix_count,
        feature_projection_sha256=source.feature_projection_sha256,
        missing_feature_ids=(),
        features={
            "home_elo": 1500.0,
            "away_elo": 1500.0,
            "home_form": 0.5,
            "away_form": 0.5,
            "fatigue": 0.0,
        },
        rates=fresh._rates_from_features(
            {
                "home_elo": 1500.0,
                "away_elo": 1500.0,
                "home_form": 0.5,
                "away_form": 0.5,
                "fatigue": 0.0,
            }
        ),
        authority=current_asof._AUTHORITY,
    )
    with pytest.raises(
        elo_only.CurrentAsOfEloOnlyXGError,
        match="only valid for missing full-model features",
    ):
        elo_only.build_current_asof_elo_only_xg_assessment(complete)


def test_policy_explicitly_forbids_imputation_and_history_scope_expansion() -> None:
    policy = elo_only.policy_summary()
    assert policy["missing_feature_imputation"] is False
    assert policy["historical_feature_scope_expansion"] is False
    assert policy["fresh_holdout_mutation"] is False
    assert policy["wager_placed"] is False
