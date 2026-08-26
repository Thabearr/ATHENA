from __future__ import annotations

import dataclasses

import pytest

import domain.accumulator_optimizer as optimizer
from domain._accumulator_optimizer_contracts import AccumulatorOptimizerError
from domain.accumulator_optimizer import AccumulatorFixtureInput, optimize_accumulator
from domain.model_status import MODEL_STATUS_REGISTRY
from tests._accumulator_optimizer_helpers import NOW, fixture_input


def test_authoritative_entry_replays_router_for_every_fixture(monkeypatch, tmp_path):
    first = fixture_input(tmp_path, 20, competition="Competition A")
    second = fixture_input(tmp_path, 21, competition="Competition B")
    original = optimizer.route_market_candidates
    seen = []

    def wrapped(candidates, quotes, *, fixture_state, evaluation_time):
        seen.append(fixture_state.fixture_identifier)
        return original(
            candidates,
            quotes,
            fixture_state=fixture_state,
            evaluation_time=evaluation_time,
        )

    monkeypatch.setattr(optimizer, "route_market_candidates", wrapped)
    result = optimize_accumulator(
        [second, first], target_size=2, evaluation_time=NOW
    )
    assert seen == ["1020", "1021"]
    assert len(result.route_audits) == 2


def test_caller_cannot_supply_prebuilt_router_decisions_or_free_form_edges(tmp_path):
    item = fixture_input(tmp_path, 22)
    with pytest.raises(TypeError):
        optimize_accumulator(
            [item],
            target_size=1,
            evaluation_time=NOW,
            router_decisions=[],
        )
    with pytest.raises(TypeError):
        optimize_accumulator(
            [item], target_size=1, evaluation_time=NOW, edge=1.0
        )
    with pytest.raises(TypeError):
        optimize_accumulator(
            [item], target_size=1, evaluation_time=NOW, correlation=-1.0
        )


def test_free_form_fixture_dict_is_rejected_before_portfolio_authority():
    with pytest.raises(AccumulatorOptimizerError, match="exact AccumulatorFixtureInput"):
        optimize_accumulator(
            [{"fixture_id": "fake", "edge": 1.0, "risk_score": 0}],
            target_size=1,
            evaluation_time=NOW,
        )


def test_fixture_input_constructor_requires_exact_builder_issued_types(tmp_path):
    item = fixture_input(tmp_path, 23)
    with pytest.raises(AccumulatorOptimizerError):
        AccumulatorFixtureInput(
            candidates=list(item.candidates),
            quotes=item.quotes,
            fixture_state=item.fixture_state,
            reconciliation=item.reconciliation,
        )
    with pytest.raises(AccumulatorOptimizerError):
        AccumulatorFixtureInput(
            candidates=item.candidates,
            quotes=list(item.quotes),
            fixture_state=item.fixture_state,
            reconciliation=item.reconciliation,
        )


def test_relabelled_team_cannot_evade_caps_because_reconciliation_hash_is_quote_bound(tmp_path):
    item = fixture_input(tmp_path, 24, home="Original FC")
    original = item.reconciliation
    assert original.matched_fixture is not None
    tampered_match = dataclasses.replace(
        original.matched_fixture, home_team="Relabelled FC"
    )
    tampered_reconciliation = dataclasses.replace(
        original,
        home_display="Relabelled FC",
        matched_fixture=tampered_match,
    )
    tampered = AccumulatorFixtureInput(
        candidates=item.candidates,
        quotes=item.quotes,
        fixture_state=item.fixture_state,
        reconciliation=tampered_reconciliation,
    )
    result = optimize_accumulator([tampered], target_size=1, evaluation_time=NOW)
    assert result.selected_legs == ()
    assert result.shortfall == 1
    audit = result.route_audits[0]
    assert audit.router_decision_status == "SELECTED"
    assert audit.portfolio_admitted is False
    assert any(
        "exact reconciliation bound into the selected quote" in reason
        for reason in audit.portfolio_admission_reasons
    )


def test_relabelled_competition_is_rejected_by_same_quote_bound_hash(tmp_path):
    item = fixture_input(tmp_path, 25, competition="Original League")
    original = item.reconciliation
    assert original.matched_fixture is not None
    tampered_match = dataclasses.replace(
        original.matched_fixture, competition="Other League"
    )
    tampered_reconciliation = dataclasses.replace(
        original,
        competition_display="Other League",
        matched_fixture=tampered_match,
    )
    tampered = AccumulatorFixtureInput(
        candidates=item.candidates,
        quotes=item.quotes,
        fixture_state=item.fixture_state,
        reconciliation=tampered_reconciliation,
    )
    result = optimize_accumulator([tampered], target_size=1, evaluation_time=NOW)
    assert result.selected_legs == ()
    assert result.route_audits[0].portfolio_admitted is False


def test_duplicate_fixture_and_event_inputs_fail_closed(tmp_path):
    first = fixture_input(tmp_path, 26)
    with pytest.raises(AccumulatorOptimizerError, match="duplicate fixture"):
        optimize_accumulator([first, first], target_size=2, evaluation_time=NOW)


def test_target_size_cannot_be_used_to_force_more_than_frozen_maximum():
    with pytest.raises(ValueError, match="between 1 and 50"):
        optimize_accumulator([], target_size=51, evaluation_time=NOW)
    with pytest.raises(ValueError, match="between 1 and 50"):
        optimize_accumulator([], target_size=0, evaluation_time=NOW)
    with pytest.raises(TypeError, match="integer"):
        optimize_accumulator([], target_size=True, evaluation_time=NOW)


def test_output_never_claims_slip_staking_execution_or_bet_authority():
    result = optimize_accumulator([], target_size=20, evaluation_time=NOW)
    flags = result.to_dict()["authority_flags"]
    assert flags["accumulator_optimization"] is True
    assert flags["qualified_leg_set"] is True
    assert flags["slip_construction"] is False
    assert flags["booking_code_generation"] is False
    assert flags["staking"] is False
    assert flags["bookmaker_execution"] is False
    assert flags["production_approval"] is False
    assert flags["bet"] is False


def test_no_statistical_correlation_is_fabricated(tmp_path):
    first = fixture_input(tmp_path, 27, competition="Shared Competition")
    second = fixture_input(tmp_path, 28, competition="Shared Competition")
    result = optimize_accumulator(
        [first, second], target_size=2, evaluation_time=NOW
    )
    assert result.correlation_adjusted_expected_slip_survival is None
    assert result.exposure_summary["statistical_correlation_coefficients"] is None
    assert result.flagged_exposure_pairs
    assert all(
        item["statistical_correlation"] is None
        for item in result.flagged_exposure_pairs
    )


def test_legacy_model_status_registry_remains_globally_locked():
    assert all(not definition.selectable for definition in MODEL_STATUS_REGISTRY.values())
    assert all(
        definition.selection_authority.value == "NOT_AUTHORIZED"
        for definition in MODEL_STATUS_REGISTRY.values()
    )


def test_offline_runner_blocks_network_before_factory_import(monkeypatch):
    import scripts.evaluate_accumulator_optimizer as runner

    observed = {}

    def guarded_loader(_specification):
        import socket
        sock = socket.socket()
        try:
            with pytest.raises(
                runner.OfflineAccumulatorOptimizerError,
                match="network access is disabled",
            ):
                sock.connect(("127.0.0.1", 9))
            observed["blocked_during_import"] = True
        finally:
            sock.close()

        def factory():
            return {
                "fixture_inputs": [],
                "target_size": 20,
                "evaluation_time": NOW,
            }
        return factory

    monkeypatch.setattr(runner, "_load_factory", guarded_loader)
    result = runner.run_factory("fake.module:factory")
    assert observed == {"blocked_during_import": True}
    assert result.shortfall == 20
