from __future__ import annotations

from datetime import timedelta

import pytest

from domain import current_sportybet_accumulator_execution as execution
from domain import portfolio_optimizer_v3_current_provider as portfolio
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_portfolio_optimizer_v3_current_provider import _input


def _optimization(monkeypatch, target: int = 1):
    source = _input(monkeypatch)
    return portfolio.optimize_current_provider_portfolio_as_of(
        (source,), target_size=target,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )


def _provider_event_row(intent, selection, *, market_name=None, outcome_name=None, odds=None):
    return {
        "eventId": intent["eventId"],
        "homeTeamName": intent["homeTeamName"],
        "awayTeamName": intent["awayTeamName"],
        "markets": [{
            "id": selection["marketId"],
            "name": market_name or intent["marketName"],
            "specifier": intent["specifier"],
            "outcomes": [{
                "id": selection["outcomeId"],
                "name": outcome_name or intent["outcomeName"],
                "odds": odds or "2.0",
            }],
        }],
    }


def _install_success(monkeypatch, *, mutate_create=None, mutate_reload=None, accepted_count=1):
    observed = {}

    def resolve_live_intents(*, intents, output_dir, minimum_lead_seconds, delay_seconds):
        assert all(set(intent) == {"eventId", "homeTeamName", "awayTeamName", "marketName", "outcomeName", "specifier"} for intent in intents)
        observed["intents"] = intents
        selected_leg = observed["optimization"].selected_legs[0]
        selections = ({
            "eventId": intents[0]["eventId"],
            "marketId": selected_leg.provider_market_id,
            "outcomeId": selected_leg.provider_outcome_id,
            **({"specifier": intents[0]["specifier"]} if intents[0]["specifier"] is not None else {}),
        },)
        receipt = {
            "resolved_count": 1,
            "resolved": [{
                "eventId": intents[0]["eventId"],
                "observed_market_name": intents[0]["marketName"],
                "observed_outcome_name": intents[0]["outcomeName"],
                "observed_specifier": intents[0]["specifier"],
                "odds": str(selected_leg.decimal_odds),
            }],
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }
        return selections, receipt

    def create_and_roundtrip(*, selections, output_dir):
        intent = observed["intents"][0]
        leg = observed["optimization"].selected_legs[0]
        create = _provider_event_row(intent, selections[0], odds=str(leg.decimal_odds))
        reload = _provider_event_row(intent, selections[0], odds=str(leg.decimal_odds))
        if mutate_create: mutate_create(create)
        if mutate_reload: mutate_reload(reload)
        return {
            "selection_count": 1,
            "create_accepted_selection_count": accepted_count,
            "load_accepted_selection_count": accepted_count,
            "create_accepted_outcomes": [create],
            "load_accepted_outcomes": [reload],
            "create_unavailable_outcomes": 0,
            "load_unavailable_outcomes": 0,
            "exact_roundtrip_selection_identity_verified": True,
            "shareCode": "VERIFIED1",
            "shareURL": "https://www.sportybet.com/ng/share/VERIFIED1",
            "combined_odds": str(leg.decimal_odds),
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }

    monkeypatch.setattr(execution.semantic_bridge, "resolve_live_intents", resolve_live_intents)
    monkeypatch.setattr(execution.direct_bridge, "create_and_roundtrip", create_and_roundtrip)
    return observed


def test_execution_contract_pins_current_portfolio_v3():
    identities = execution.validate_current_execution_contract()
    assert identities["portfolio_optimizer_v3_contract_sha256"] == portfolio.EXPECTED_CONTRACT_SHA256
    assert identities["current_execution_contract_sha256"] == execution.calculate_current_execution_contract_sha256()


def test_exact_semantic_native_odds_create_reload_path_returns_verified_code(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    observed = _install_success(monkeypatch)
    observed["optimization"] = optimization
    result = execution.execute_current_sportybet_accumulator_as_of(
        optimization, output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=30),
    )
    assert result.status == "CODE_VERIFIED"
    assert result.router_selected_leg_count == result.optimizer_qualified_leg_count == 1
    assert result.semantic_intent_count == result.semantic_resolution_count == 1
    assert result.provider_create_selection_count == result.provider_reload_selection_count == 1
    assert result.exact_roundtrip_verification[0]["exact_semantic_native_odds_match"] is True
    assert result.share_code == "VERIFIED1"
    assert result.wager_placed is False
    assert (tmp_path / "current-sportybet-accumulator-execution.json").is_file()


def test_transport_native_success_with_wrong_human_market_is_rejected(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    observed = _install_success(
        monkeypatch,
        mutate_create=lambda row: row["markets"][0].update(name="Different Market"),
        mutate_reload=lambda row: row["markets"][0].update(name="Different Market"),
    )
    observed["optimization"] = optimization
    with pytest.raises(execution.CurrentSportyBetAccumulatorExecutionError, match="semantic/native/odds"):
        execution.execute_current_sportybet_accumulator_as_of(
            optimization, output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=30),
        )


def test_wrong_outcome_specifier_or_odds_fails_entire_execution(monkeypatch, tmp_path):
    mutations = (
        lambda row: row["markets"][0]["outcomes"][0].update(name="Different Outcome"),
        lambda row: row["markets"][0].update(specifier="wrong=1.5"),
        lambda row: row["markets"][0]["outcomes"][0].update(odds="9.99"),
    )
    for mutation in mutations:
        optimization = _optimization(monkeypatch)
        observed = _install_success(monkeypatch, mutate_create=mutation, mutate_reload=mutation)
        observed["optimization"] = optimization
        with pytest.raises(execution.CurrentSportyBetAccumulatorExecutionError):
            execution.execute_current_sportybet_accumulator_as_of(
                optimization, output_dir=tmp_path,
                evaluation_time=EVALUATION + timedelta(seconds=30),
            )


def test_create_reload_count_or_native_identity_drift_fails(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    observed = _install_success(monkeypatch, accepted_count=0)
    observed["optimization"] = optimization
    with pytest.raises(execution.CurrentSportyBetAccumulatorExecutionError, match="count"):
        execution.execute_current_sportybet_accumulator_as_of(
            optimization, output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=30),
        )

    optimization = _optimization(monkeypatch)
    observed = _install_success(
        monkeypatch,
        mutate_reload=lambda row: row["markets"][0]["outcomes"][0].update(id="different-native-id"),
    )
    observed["optimization"] = optimization
    with pytest.raises(execution.CurrentSportyBetAccumulatorExecutionError, match="semantic/native/odds"):
        execution.execute_current_sportybet_accumulator_as_of(
            optimization, output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=30),
        )


def test_provider_safety_or_unavailable_outcome_claim_fails_closed(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    observed = _install_success(monkeypatch)
    observed["optimization"] = optimization

    original = execution.direct_bridge.create_and_roundtrip

    def unsafe_transport(**kwargs):
        receipt = original(**kwargs)
        receipt["sportybet_wallet_used"] = True
        return receipt

    monkeypatch.setattr(execution.direct_bridge, "create_and_roundtrip", unsafe_transport)
    with pytest.raises(execution.CurrentSportyBetAccumulatorExecutionError, match="safety field"):
        execution.execute_current_sportybet_accumulator_as_of(
            optimization, output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=30),
        )

    observed = _install_success(monkeypatch)
    observed["optimization"] = optimization
    original = execution.direct_bridge.create_and_roundtrip

    def unavailable_transport(**kwargs):
        receipt = original(**kwargs)
        receipt["create_unavailable_outcomes"] = 1
        return receipt

    monkeypatch.setattr(execution.direct_bridge, "create_and_roundtrip", unavailable_transport)
    with pytest.raises(execution.CurrentSportyBetAccumulatorExecutionError, match="unavailable outcomes"):
        execution.execute_current_sportybet_accumulator_as_of(
            optimization, output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=30),
        )


def test_requested_twenty_qualified_one_returns_shortfall_without_provider_call(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch, target=20)
    monkeypatch.setattr(execution.semantic_bridge, "resolve_live_intents", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not resolve")))
    monkeypatch.setattr(execution.direct_bridge, "create_and_roundtrip", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not create")))
    result = execution.execute_current_sportybet_accumulator_as_of(
        optimization, output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=30),
    )
    assert result.status == "NO_CODE_SHORTFALL"
    assert result.requested_fold_count == 20
    assert result.final_qualified_fold_count == 1
    assert result.shortfall == 19
    assert result.share_code is None
    assert result.wager_placed is False


def test_execution_cannot_run_before_portfolio_evaluation_time(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    with pytest.raises(
        execution.CurrentSportyBetAccumulatorExecutionError,
        match="predates Portfolio v3",
    ):
        execution.execute_current_sportybet_accumulator_as_of(
            optimization,
            output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=15),
        )


def test_live_execution_requires_live_portfolio_status_not_only_proof_label(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    object.__setattr__(
        optimization,
        "proof_mode",
        portfolio.router_v3.price_v3.LIVE_CURRENT,
    )
    monkeypatch.setattr(
        execution.portfolio_v3,
        "verify_current_provider_portfolio_optimization",
        lambda value: value,
    )
    monkeypatch.setattr(execution, "_now_utc", lambda: EVALUATION + timedelta(seconds=30))
    with pytest.raises(
        execution.CurrentSportyBetAccumulatorExecutionError,
        match="live current ancestry",
    ):
        execution.execute_current_sportybet_accumulator(
            optimization,
            output_dir=tmp_path,
            delay_seconds=0.0,
        )


def test_final_source_replay_staleness_fails_whole_execution(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    with pytest.raises(execution.CurrentSportyBetAccumulatorExecutionError, match="stale"):
        execution.execute_current_sportybet_accumulator_as_of(
            optimization, output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=841),
        )


def test_semantic_bridge_intent_never_contains_native_ids_odds_or_preselected_slip(monkeypatch, tmp_path):
    optimization = _optimization(monkeypatch)
    observed = _install_success(monkeypatch); observed["optimization"] = optimization
    execution.execute_current_sportybet_accumulator_as_of(
        optimization, output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=30),
    )
    intent = observed["intents"][0]
    assert not ({"marketId", "outcomeId", "odds", "selections", "slip"} & set(intent))
