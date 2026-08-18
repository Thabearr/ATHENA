from __future__ import annotations

import datetime as dt

import pytest

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control


UTC = dt.timezone.utc
ZERO = "0" * 64


def test_control_reproves_exact_pr149_merge_and_resolved_boundaries() -> None:
    control.verify_reviewed_implementation()
    assert control.PR149_MERGE_SHA == "9ba66cff0677b5952c6c931ddf3cefb7c9565187"
    assert control.pr149_merge_utc() == dt.datetime(
        2026, 8, 18, 4, 18, 35, tzinfo=UTC
    )
    assert control.holdout_start_utc() == dt.datetime(
        2026, 8, 19, 0, 0, tzinfo=UTC
    )
    assert fresh.resolve_holdout_start(control.pr149_merge_utc()) == (
        control.holdout_start_utc()
    )
    assert control.minimum_gate_utc() == dt.datetime(
        2026, 9, 16, 0, 0, tzinfo=UTC
    )
    assert control.hard_close_utc() == dt.datetime(
        2026, 11, 17, 0, 0, tzinfo=UTC
    )
    assert control.settlement_tail_end_utc() == dt.datetime(
        2026, 11, 18, 0, 0, tzinfo=UTC
    )


def test_capture_cadence_is_outcome_independent_and_supports_reviewed_repeat_gate() -> None:
    assert control.CAPTURE_INTERVAL_MINUTES == 30
    assert control.CAPTURE_MINUTES_UTC == (0, 30)
    assert control.CAPTURE_INTERVAL_MINUTES * 60 >= (
        score_adapter.MINIMUM_REPEAT_SEPARATION_SECONDS
    )


def test_prestart_tick_plans_no_request_and_no_network_authority() -> None:
    tick = dt.datetime(2026, 8, 18, 23, 30, tzinfo=UTC)
    plan = control.build_collection_tick_plan(tick)
    assert plan.phase is control.ControlPhase.PRE_START
    assert plan.request_dates == ()
    assert plan.close_state is None
    assert plan.prediction_sealing_authorized is False
    assert plan.network_acquisition_authorized is False


def test_start_tick_requests_yesterday_today_and_tomorrow_in_exact_utc_nga_identity() -> None:
    tick = dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC)
    plan = control.build_collection_tick_plan(tick)
    assert plan.phase is control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION
    assert plan.request_dates == ("20260818", "20260819", "20260820")
    assert plan.timezone == "UTC"
    assert plan.ccode3 == "NGA"
    assert plan.prediction_sealing_authorized is True
    assert plan.network_acquisition_authorized is False


def test_active_request_dates_preserve_midnight_settlement_and_future_prediction_scope() -> None:
    tick = dt.datetime(2026, 8, 31, 23, 30, tzinfo=UTC)
    assert control.request_dates_for_tick(tick) == (
        "20260830",
        "20260831",
        "20260901",
    )


def test_only_exact_half_hour_utc_boundaries_are_valid_control_ticks() -> None:
    for invalid in (
        dt.datetime(2026, 8, 19, 0, 1, tzinfo=UTC),
        dt.datetime(2026, 8, 19, 0, 0, 1, tzinfo=UTC),
        dt.datetime(2026, 8, 19, 0, 0, 0, 1, tzinfo=UTC),
        dt.datetime(2026, 8, 19, 0, 15, tzinfo=UTC),
    ):
        with pytest.raises(
            control.FreshHoldoutCollectionControlError,
            match="exact UTC :00 or :30",
        ):
            control.build_collection_tick_plan(invalid)


def test_naive_tick_fails_closed() -> None:
    with pytest.raises(
        control.FreshHoldoutCollectionControlError,
        match="timezone-aware",
    ):
        control.build_collection_tick_plan(dt.datetime(2026, 8, 19, 0, 0))


def test_minimum_gate_requires_current_count_only_close_state() -> None:
    minimum = control.minimum_gate_utc()
    with pytest.raises(
        control.FreshHoldoutCollectionControlError,
        match="close state is required",
    ):
        control.build_collection_tick_plan(minimum)

    state = control.evaluate_close_control_state((), boundary=minimum)
    assert state.decision == (
        fresh.HoldoutBoundaryDecision.OPEN_WAITING_FOR_COUNT_ONLY_COVERAGE.value
    )
    assert state.selected_close_utc is None
    plan = control.build_collection_tick_plan(minimum, close_state=state)
    assert plan.phase is control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION
    assert plan.prediction_sealing_authorized is True


def test_open_close_state_must_be_refreshed_at_each_required_utc_midnight() -> None:
    minimum = control.minimum_gate_utc()
    state = control.evaluate_close_control_state((), boundary=minimum)
    half_hour = minimum + dt.timedelta(minutes=30)
    assert control.build_collection_tick_plan(
        half_hour, close_state=state
    ).prediction_sealing_authorized is True

    next_midnight = minimum + dt.timedelta(days=1)
    with pytest.raises(
        control.FreshHoldoutCollectionControlError,
        match="stale for the latest required UTC boundary",
    ):
        control.build_collection_tick_plan(next_midnight, close_state=state)
    refreshed = control.evaluate_close_control_state((), boundary=next_midnight)
    assert control.build_collection_tick_plan(
        next_midnight, close_state=refreshed
    ).prediction_sealing_authorized is True


def test_validated_early_count_only_close_immediately_stops_prediction_sealing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minimum = control.minimum_gate_utc()

    def fake_boundary(*_args, **_kwargs):
        return {
            "decision": (
                fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value
            ),
            "coverage": {
                "complete_case_fixture_count": 1000,
                "all_count_only_gates_pass": True,
            },
            "outcome_or_performance_input_used": False,
        }

    monkeypatch.setattr(fresh, "evaluate_holdout_boundary", fake_boundary)
    state = control.evaluate_close_control_state((), boundary=minimum)
    assert state.selected_close_utc == minimum
    assert state.decision == (
        fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value
    )
    plan = control.build_collection_tick_plan(minimum, close_state=state)
    assert plan.phase is control.ControlPhase.SETTLEMENT_TAIL_ONLY
    assert plan.request_dates == ("20260915", "20260916")
    assert plan.prediction_sealing_authorized is False
    assert control.settlement_tail_end_utc(state) == minimum + dt.timedelta(days=1)


def test_hard_close_empty_population_selects_insufficient_coverage_and_settlement_tail() -> None:
    hard = control.hard_close_utc()
    state = control.evaluate_close_control_state((), boundary=hard)
    assert state.decision == (
        fresh.HoldoutBoundaryDecision.CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION.value
    )
    assert state.selected_close_utc == hard
    plan = control.build_collection_tick_plan(hard, close_state=state)
    assert plan.phase is control.ControlPhase.SETTLEMENT_TAIL_ONLY
    assert plan.request_dates == ("20261116", "20261117")
    assert plan.prediction_sealing_authorized is False
    assert plan.network_acquisition_authorized is False

    tail = control.settlement_tail_end_utc(state)
    complete = control.build_collection_tick_plan(tail, close_state=state)
    assert complete.phase is control.ControlPhase.COLLECTION_COMPLETE
    assert complete.request_dates == ()


def test_close_control_state_cannot_be_fabricated_by_normal_constructor() -> None:
    with pytest.raises(
        control.FreshHoldoutCollectionControlError,
        match="must come from reviewed count-only evaluation",
    ):
        control.CloseControlState(
            evaluated_boundary_utc=control.minimum_gate_utc(),
            decision=fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value,
            selected_close_utc=control.minimum_gate_utc(),
            coverage_sha256=ZERO,
            _token=object(),
        )


def test_receipt_preserves_broad_competition_capture_but_legacy_only_history_mutation() -> None:
    receipt = control.collection_control_receipt()
    capture = receipt["capture_control"]
    assert capture["fresh_capture_scope_limited_to_legacy_primary_ids"] is False
    assert capture["all_structurally_qualified_provider_primary_ids_retained"] is True
    assert capture["history_state_mutation_limited_to_frozen_legacy_primary_ids"] is True
    assert capture["active_request_date_offsets_days"] == [-1, 0, 1]
    assert capture["active_requests_per_tick"] == 3
    assert capture["settlement_tail_request_date_offsets_days"] == [-1, 0]
    assert capture["settlement_requests_per_tick"] == 2


def test_receipt_requires_count_only_close_freshness_and_durable_identity_evidence() -> None:
    receipt = control.collection_control_receipt()
    close = receipt["close_control"]
    assert close["outcome_or_performance_inputs_accepted"] is False
    assert close["open_state_must_be_current_through_latest_required_boundary"] is True
    assert close["selected_close_immediately_disables_prediction_sealing"] is True
    assert close["selected_close_is_irreversible"] is True
    assert close["tail_end_rule"] == "SELECTED_CLOSE_UTC_PLUS_24_HOURS"

    evidence = receipt["durable_evidence"]
    assert evidence["append_only_journals_required"] is True
    assert evidence["prediction_seal_must_be_durable_before_kickoff"] is True
    assert evidence["every_qualified_post_seal_identity_observation_must_be_retained"] is True
    assert evidence["known_change_then_reversion_remains_excluding"] is True
    assert evidence["cross_run_state_restore_required"] is True
    assert evidence["close_state_revalidation_from_prediction_journal_required"] is True
    assert evidence["exact_bootstrap_projection_required_before_prediction_sealing"] is True


def test_control_is_installed_but_not_activated_and_grants_no_downstream_authority() -> None:
    receipt = control.collection_control_receipt()
    assert receipt["control_state"] == control.CONTROL_STATE
    assert receipt["activation"] == {
        "workflow_or_scheduler_installed": False,
        "network_acquisition_performed": False,
        "fresh_holdout_collection_started": False,
        "next_required_boundary": control.NEXT_REQUIRED_BOUNDARY,
    }
    assert all(value is False for value in receipt["safety"].values())


def test_tick_dataclass_rejects_fabricated_request_identity_or_network_authority() -> None:
    tick = control.holdout_start_utc()
    dates = ("20260818", "20260819", "20260820")
    with pytest.raises(control.FreshHoldoutCollectionControlError, match="request identity"):
        control.CollectionTickPlan(
            scheduled_for_utc=tick,
            phase=control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION,
            request_dates=dates,
            timezone="Africa/Lagos",
            ccode3="NGA",
            close_state=None,
            prediction_sealing_authorized=True,
            network_acquisition_authorized=False,
        )
    with pytest.raises(control.FreshHoldoutCollectionControlError, match="may not authorize"):
        control.CollectionTickPlan(
            scheduled_for_utc=tick,
            phase=control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION,
            request_dates=dates,
            timezone="UTC",
            ccode3="NGA",
            close_state=None,
            prediction_sealing_authorized=True,
            network_acquisition_authorized=True,
        )
