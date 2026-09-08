from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain import current_fotmob_utc_native_current_asof_xg as current_asof
from domain._all_market_shadow_types import ResearchXGRates
from scripts import current_shadow_current_asof_elo_only_fallback as fallback


def _rates() -> ResearchXGRates:
    return ResearchXGRates(
        calibrated_home=1.21,
        calibrated_away=0.97,
        feature_projection_identity="3" * 64,
        history_prefix_identity="4" * 64,
        source_fixture_identity="FOTMOB:42",
        completeness_status="CURRENT_AS_OF_RESEARCH_XG_ELO_ONLY_COMPLETE",
    )


def test_diagnostic_records_exact_model_rates_for_base_ready_path() -> None:
    rates = _rates()
    kickoff = "2026-09-08T18:00:00.000000Z"
    fallback._DIAGNOSTIC_ROWS.clear()

    result = fallback._with_fallback(
        lambda *_args, **_kwargs: (rates, None, (), kickoff),
        object(),
        "FOTMOB:42",
        history_sha="5" * 64,
    )

    assert result == (rates, None, (), kickoff)
    diagnostic = fallback.diagnostic_summary()
    assert diagnostic["schema_version"] == 4
    assert diagnostic["dataset_name"] == "athena-current-shadow-current-asof-xg-diagnostic-v4"
    row = diagnostic["fixtures"][0]
    assert row["state"] == "BASE_MODEL_READY"
    assert row["model_rates"] == {
        "calibrated_home": 1.21,
        "calibrated_away": 0.97,
        "feature_projection_identity": "3" * 64,
        "history_prefix_identity": "4" * 64,
        "source_fixture_identity": "FOTMOB:42",
        "completeness_status": "CURRENT_AS_OF_RESEARCH_XG_ELO_ONLY_COMPLETE",
    }
    assert row["full_available_feature_values"] == {}
    assert row["legacy_elo_expectation_audit"] is None
    assert row["wager_placed"] is False


def test_diagnostic_exposes_reviewed_elo_values_and_frozen_expectation_mass() -> None:
    full = SimpleNamespace(
        disposition=current_asof.CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES,
        missing_feature_ids=("away_form", "fatigue", "home_form"),
        features={"home_elo": 1512.0, "away_elo": 1488.0},
    )
    fallback._DIAGNOSTIC_ROWS.clear()
    fallback._record(
        "FOTMOB:42",
        state="ELO_ONLY_APPLIED",
        history_sha="5" * 64,
        blocker=None,
        missing=("away_form", "fatigue", "home_form"),
        full=full,
        research_xg=_rates(),
    )

    row = fallback.diagnostic_summary()["fixtures"][0]
    assert row["full_available_feature_values"] == {
        "away_elo": 1488.0,
        "home_elo": 1512.0,
    }
    audit = row["legacy_elo_expectation_audit"]
    assert audit["semantic_basis"] == "REVIEWED_FROZEN_HISTORICAL_ELO_FORMULAS"
    assert audit["home_advantage_points"] == 50
    assert audit["logistic_divisor"] == 400.0
    assert audit["home_expected_score"] == pytest.approx(0.6049129020079569)
    assert audit["away_expected_score"] == pytest.approx(0.46551605527316847)
    assert audit["expected_score_mass"] == pytest.approx(1.0704289572811254)
    assert audit["expected_score_mass_minus_one"] == pytest.approx(0.07042895728112541)
    assert audit["expected_scores_are_complements"] is False
    assert row["fallback_applied"] is True


def test_policy_marks_new_diagnostic_fields_non_authoritative() -> None:
    summary = fallback.policy_summary()
    assert summary["diagnostic_dataset_name"] == fallback.DIAGNOSTIC_DATASET_NAME
    assert summary["diagnostic_non_authoritative"] is True
    assert summary["diagnostic_exposes_model_rates"] is True
    assert summary["diagnostic_exposes_reviewed_elo_feature_values"] is True
    assert summary["diagnostic_exposes_frozen_elo_expectation_mass"] is True
    assert summary["wager_placed"] is False
