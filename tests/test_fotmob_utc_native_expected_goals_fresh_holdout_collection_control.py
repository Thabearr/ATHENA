from __future__ import annotations

import datetime as dt

import pytest

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control


UTC = dt.timezone.utc


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
    assert plan.prediction_sealing_authorized is False
    assert plan.network_acquisition_authorized is False


def test_start_tick_requests_today_and_tomorrow_in_exact_utc_nga_identity() -> None:
    tick = dt.datetime(2026, 8, 19, 0, 0, tzinfo=UTC)
    plan = control.build_collection_tick_plan(tick)
    assert plan.phase is control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION
    assert plan.request_dates == ("20260819", "20260820")
    assert plan.timezone == "UTC"
    assert plan.ccode3 == "NGA"
    assert plan.prediction_sealing_authorized is True
    assert plan.network_acquisition_authorized is False


def test_active_request_dates_roll_across_utc_day_without_name_mapping() -> None:
    tick = dt.datetime(2026, 8, 31, 23, 30, tzinfo=UTC)
    assert control.request_dates_for_tick(tick) == ("20260831", "20260901")


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


def test_hard_close_switches_to_settlement_only_tail_without_new_prediction_seals() -> None:
    hard = control.hard_close_utc()
    plan = control.build_collection_tick_plan(hard)
    assert plan.phase is control.ControlPhase.SETTLEMENT_TAIL_ONLY
    assert plan.request_dates == ("20261117",)
    assert plan.prediction_sealing_authorized is False
    assert plan.network_acquisition_authorized is False


def test_collection_stops_after_deterministic_settlement_tail() -> None:
    tail = control.settlement_tail_end_utc()
    plan = control.build_collection_tick_plan(tail)
    assert plan.phase is control.ControlPhase.COLLECTION_COMPLETE
    assert plan.request_dates == ()
    assert plan.prediction_sealing_authorized is False


def test_receipt_preserves_broad_competition_capture_but_legacy_only_history_mutation() -> None:
    receipt = control.collection_control_receipt()
    capture = receipt["capture_control"]
    assert capture["fresh_capture_scope_limited_to_legacy_primary_ids"] is False
    assert capture["all_structurally_qualified_provider_primary_ids_retained"] is True
    assert capture["history_state_mutation_limited_to_frozen_legacy_primary_ids"] is True
    assert capture["active_request_date_offsets_days"] == [0, 1]
    assert capture["active_requests_per_tick"] == 2


def test_receipt_requires_durable_prediction_and_every_post_seal_identity_observation() -> None:
    receipt = control.collection_control_receipt()
    evidence = receipt["durable_evidence"]
    assert evidence["append_only_journals_required"] is True
    assert evidence["prediction_seal_must_be_durable_before_kickoff"] is True
    assert evidence["every_qualified_post_seal_identity_observation_must_be_retained"] is True
    assert evidence["known_change_then_reversion_remains_excluding"] is True
    assert evidence["cross_run_state_restore_required"] is True
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
    with pytest.raises(control.FreshHoldoutCollectionControlError, match="request identity"):
        control.CollectionTickPlan(
            scheduled_for_utc=tick,
            phase=control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION,
            request_dates=("20260819", "20260820"),
            timezone="Africa/Lagos",
            ccode3="NGA",
            prediction_sealing_authorized=True,
            network_acquisition_authorized=False,
        )
    with pytest.raises(control.FreshHoldoutCollectionControlError, match="may not authorize"):
        control.CollectionTickPlan(
            scheduled_for_utc=tick,
            phase=control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION,
            request_dates=("20260819", "20260820"),
            timezone="UTC",
            ccode3="NGA",
            prediction_sealing_authorized=True,
            network_acquisition_authorized=True,
        )
