import datetime as dt
import hashlib
import math
import types

import pytest

import domain.fotmob_utc_native_expected_goals_model_validation as m
import domain.fotmob_utc_native_expected_goals_model_validation_protocol as protocol
import domain.historical_expected_goals_successor_robustness_evaluator as pr76


def _row(
    fixture_id="1",
    kickoff="2024-01-01T12:00:00Z",
    *,
    complete=True,
    freshness_value=None,
):
    return {
        "schema_version": 1,
        "source_namespace": m.SOURCE_NAMESPACE,
        "fixture_identifier": fixture_id,
        "kickoff_utc": kickoff,
        "home_team_identifier": f"h-{fixture_id}",
        "away_team_identifier": f"a-{fixture_id}",
        "home_goals": 2,
        "away_goals": 1,
        "home_form": {
            "status": (
                "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"
                if complete
                else "MISSING"
            ),
            "value": 0.6 if complete else None,
        },
        "away_form": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 0.45,
        },
        "home_elo": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 1540,
            "matches_before": 25,
            "rating_component": "OVERALL",
        },
        "away_elo": {
            "status": "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION",
            "value": 1500,
            "matches_before": 0,
            "rating_component": "OVERALL",
        },
        "fatigue": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 0.1,
            "home_rest_days": 3,
            "away_rest_days": 5,
            "rest_day_differential": -2,
        },
        "historical_live_data_freshness": {
            "status": m.FRESHNESS_STATUS,
            "value": freshness_value,
        },
        "evidence_sha256": "a" * 64,
        "evidence_reference": "synthetic",
    }


def _fixture(identifier, kickoff, home_goals, away_goals, values):
    parsed = dt.datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    return m.ValidationFixture(
        fixture_identifier=str(identifier),
        kickoff_utc_text=kickoff,
        kickoff_utc=parsed,
        home_goals=home_goals,
        away_goals=away_goals,
        predictors=tuple(values),
    )


def test_exact_pr140_protocol_blob_and_all_false_safety_are_revalidated():
    payload = m._verify_protocol()
    assert m._git_blob_sha(protocol.Path(protocol.__file__)) == m.PROTOCOL_BLOB_SHA
    assert payload["protocol_id"] == protocol.PROTOCOL_ID
    assert payload["next_required_boundary"] == (
        "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    )
    assert set(payload["safety"]) == m.SAFETY_KEYS
    assert all(value is False for value in payload["safety"].values())


def test_projection_parser_preserves_complete_case_rule_and_predictor_math():
    first = _row("1", complete=False)
    second = _row("2", "2024-01-02T12:00:00Z", complete=True)
    raw = m._canonical(first) + m._canonical(second)
    complete, dropped = m.parse_projection_bytes(raw)
    assert dropped == 1
    assert len(complete) == 1
    assert complete[0].fixture_identifier == "2"
    assert complete[0].predictors == pytest.approx(
        (1.0, 0.1, 0.0, 0.1, -0.05, 0.1)
    )


def test_historical_freshness_must_remain_blocked_and_null():
    raw = m._canonical(_row(freshness_value=0.0))
    with pytest.raises(
        m.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="historical freshness must remain blocked/null",
    ):
        m.parse_projection_bytes(raw)


def test_projection_parser_rejects_duplicate_fixture_identity_and_noncanonical_rows():
    row = _row("7")
    raw = m._canonical(row) + m._canonical(row)
    with pytest.raises(
        m.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="duplicated",
    ):
        m.parse_projection_bytes(raw)

    malformed = b'{"schema_version": 1}\n'
    with pytest.raises(
        m.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="not canonical JSON",
    ):
        m.parse_projection_bytes(malformed)


def test_membership_hash_is_exact_ordered_kickoff_tab_fixture_newline():
    fixtures = (
        _fixture("10", "2024-01-01T12:00:00Z", 1, 0, (1, 0, 0, 0, 0, 0)),
        _fixture("11", "2024-01-02T12:00:00Z", 0, 0, (1, 0, 0, 0, 0, 0)),
    )
    raw = b"2024-01-01T12:00:00Z\t10\n2024-01-02T12:00:00Z\t11\n"
    assert m._membership_sha(fixtures) == hashlib.sha256(raw).hexdigest()


def test_reviewed_pr76_fitter_is_reused_deterministically_for_variable_designs():
    fitting = m._fitting_namespace(m._verify_protocol())
    fixtures = []
    for index in range(80):
        values = (
            1.0,
            ((index % 7) - 3) / 4.0,
            ((index % 11) - 5) / 5.0,
            ((index % 5) - 2) / 8.0,
            ((index % 13) - 6) / 12.0,
            (index % 3) * 0.1,
        )
        fixtures.append(
            _fixture(
                index,
                f"2023-01-{(index % 28) + 1:02d}T12:00:00Z",
                (index * 3) % 4,
                (index * 5) % 3,
                values,
            )
        )
    full_one = m._fit(fixtures, (0, 1, 2, 3, 4, 5), fitting)
    full_two = m._fit(fixtures, (0, 1, 2, 3, 4, 5), fitting)
    elo = m._fit(fixtures, (0, 1, 2), fitting)
    no_fatigue = m._fit(fixtures, (0, 1, 2, 3, 4), fitting)
    assert full_one == full_two
    assert len(full_one[0].coefficients) == 6
    assert len(elo[0].coefficients) == 3
    assert len(no_fatigue[0].coefficients) == 5
    assert isinstance(full_one[0], pr76.PoissonFit)


def test_calibration_uses_own_predictions_and_empty_bins_have_null_error():
    bins = m._verify_protocol()["evaluation_contract"]["calibration_contract"]["bins"]
    table, wace, wsce = m._calibration([0.2, 0.7, 3.2], [0, 1, 4], bins)
    assert sum(item["count"] for item in table) == 3
    empty = [item for item in table if item["count"] == 0]
    assert empty
    assert all(
        item["mean_predicted_goals"] is None
        and item["mean_observed_goals"] is None
        and item["calibration_error_predicted_minus_observed"] is None
        for item in empty
    )
    expected_errors = [0.2, -0.3, -0.8]
    assert wace == pytest.approx(sum(abs(value) for value in expected_errors) / 3)
    assert wsce == pytest.approx(sum(value * value for value in expected_errors) / 3)


def test_quarter_jackknife_uses_unweighted_delete_estimate_center():
    fixtures = (
        _fixture("1", "2024-07-01T12:00:00Z", 1, 0, (1, 0, 0, 0, 0, 0)),
        _fixture("2", "2024-07-02T12:00:00Z", 0, 1, (1, 0, 0, 0, 0, 0)),
        _fixture("3", "2024-10-01T12:00:00Z", 2, 1, (1, 0, 0, 0, 0, 0)),
        _fixture("4", "2024-10-02T12:00:00Z", 1, 1, (1, 0, 0, 0, 0, 0)),
    )
    native = ((1.2, 0.8), (0.9, 1.1), (1.8, 0.9), (1.1, 1.0))
    elo = ((1.0, 1.0), (1.0, 1.0), (1.4, 1.2), (1.0, 1.0))
    result = m._quarter_jackknife(
        fixtures,
        native,
        elo,
        (("2024-Q3", 2), ("2024-Q4", 2)),
    )
    deletes = [item["delete_estimate"] for item in result["delete_quarters"]]
    assert result["delete_estimate_center"] == pytest.approx(sum(deletes) / 2)
    expected_se = math.sqrt(
        0.5
        * sum(
            (value - result["delete_estimate_center"]) ** 2
            for value in deletes
        )
    )
    assert result["jackknife_standard_error"] == pytest.approx(expected_se)
    assert result["interval_upper"] == pytest.approx(
        result["full_estimate"] + 1.96 * expected_se
    )


def test_five_arm_evaluation_keeps_same_fixture_population(monkeypatch):
    train = tuple(
        _fixture(
            index,
            f"2023-02-{(index % 20) + 1:02d}T12:00:00Z",
            index % 3,
            (index + 1) % 2,
            (1.0, index / 50, -index / 60, index / 100, -index / 120, (index % 3) / 10),
        )
        for index in range(20)
    )
    evaluation_a = (
        _fixture("a", "2024-07-01T12:00:00Z", 1, 0, (1, .1, -.1, .05, -.05, .1)),
    )
    evaluation_b = (
        _fixture("b", "2025-07-01T12:00:00Z", 0, 1, (1, -.1, .1, -.05, .05, 0)),
    )

    fake_home = pr76.PoissonFit((0.0, 0.0, 0.0, 0.0, 0.0, 0.0), 0, 0.0, 1.0)
    fake_away = pr76.PoissonFit((0.0, 0.0, 0.0, 0.0, 0.0, 0.0), 0, 0.0, 1.0)

    def fake_fit(fixtures, columns, fitting):
        return (
            pr76.PoissonFit(tuple(0.0 for _ in columns), 0, 0.0, 1.0),
            pr76.PoissonFit(tuple(0.0 for _ in columns), 0, 0.0, 1.0),
        )

    monkeypatch.setattr(m, "_fit", fake_fit)
    monkeypatch.setattr(
        m,
        "_quarter_jackknife",
        lambda *args, **kwargs: {
            "population_rows": 2,
            "cluster_count": 2,
            "full_estimate": -0.1,
            "delete_estimate_center": -0.1,
            "jackknife_standard_error": 0.01,
            "interval_lower": -0.1196,
            "interval_upper": -0.0804,
            "delete_quarters": [],
        },
    )
    payload = m._verify_protocol()
    evaluation, predictions = m._evaluate(train, evaluation_a, evaluation_b, payload)
    assert set(evaluation["fits"]) == set(m.MODEL_IDS)
    for population in evaluation["populations"].values():
        counts = {
            model["fixture_count"]
            for model in population["models"].values()
        }
        assert len(counts) == 1
    assert len(predictions.splitlines()) == 2
    assert evaluation["competition_or_league_robustness_status"] == (
        "BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY"
    )


def test_source_bound_builder_rejects_wrong_projection_identity_before_training(tmp_path, monkeypatch):
    path = tmp_path / "wrong.ndjson"
    path.write_bytes(m._canonical(_row()))
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("training must not start")

    monkeypatch.setattr(m, "_evaluate", fail_if_called)
    with pytest.raises(
        m.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="projection identity changed",
    ):
        m.build_validation(path)
    assert called is False


def test_receipt_canonicalization_rejects_any_downstream_authority():
    receipt = {
        "safety": {key: False for key in sorted(m.SAFETY_KEYS)},
        "validation_state": m.WEAK_STATE,
    }
    raw = m.canonical_validation_receipt_bytes(receipt)
    assert raw.endswith(b"\n")
    receipt["safety"]["bet_authorized"] = True
    with pytest.raises(
        m.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="exact False",
    ):
        m.canonical_validation_receipt_bytes(receipt)


def test_runtime_provenance_cannot_be_mistaken_for_cross_runtime_clearance():
    assert m.NEXT_REQUIRED_BOUNDARY == (
        "REVIEW_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT"
    )
    assert m.STRONG_STATE.endswith("REVIEW_REQUIRED")
    assert m.WEAK_STATE.endswith("REVIEW_REQUIRED")
    assert "score_matrix" not in m.MODEL_IDS
