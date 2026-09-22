from __future__ import annotations

import json

import pytest

from domain import current_sportybet_accumulator_request as request
from scripts import execute_current_sportybet_accumulator as cli


EXPECTED_CONTRACT_IDENTITIES = {
    "price_all_v3_contract_sha256": "30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425",
    "market_router_v3_contract_sha256": "61a90a29495399668e19ae4a149527abea98c172d7bdacf1a1b521776b4d771a",
    "portfolio_optimizer_v3_contract_sha256": "4dc8be4e0a9f607b6c0804048bb326c0aa342d37fe540abbcd3e1b3a5f6a6dad",
    "current_execution_contract_sha256": "62d0f48942ca28eb9566f4803deea07e61598732198882cc515cd88c6209d359",
    "blocked_at": "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION",
}


def test_fixed_target_twenty_request_stops_at_exact_phase6_authority_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(request, "_now_utc", lambda: request.datetime(2026, 8, 28, tzinfo=request.timezone.utc))
    assert dict(request.validate_current_request_dependencies()) == EXPECTED_CONTRACT_IDENTITIES
    result = request.execute_current_accumulator_request(target_size=20, output_dir=tmp_path)
    assert result.requested_target_size == 20
    assert result.status == request.STATUS_PHASE6_AUTHORITY_REQUIRED
    assert result.blocked_at == "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION"
    assert result.real_current_provider_execution_attempted is False
    assert result.wager_placed is False
    payload = json.loads((tmp_path / "current-sportybet-accumulator-request.json").read_text())
    assert payload["contract_identities"] == EXPECTED_CONTRACT_IDENTITIES
    assert payload["authority"]["caller_factory"] is False
    assert payload["authority"]["caller_native_market_outcome_ids"] is False


@pytest.mark.parametrize("value", [0, 51, True, "20"])
def test_target_size_is_bounded_and_exact(value, tmp_path):
    with pytest.raises(request.CurrentSportyBetAccumulatorRequestError, match="target_size"):
        request.execute_current_accumulator_request(target_size=value, output_dir=tmp_path)


def test_cli_has_no_factory_native_ids_odds_or_preselected_slip_options():
    actions = {option for action in cli.build_parser()._actions for option in action.option_strings}
    assert actions == {"-h", "--help", "--target-size", "--output-dir"}
    for forbidden in ("--factory", "--event-id", "--market-id", "--outcome-id", "--odds", "--slip"):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["--target-size", "20", forbidden, "x"])


def test_cli_target_size_reaches_fixed_service(monkeypatch, tmp_path, capsys):
    observed = {}

    class Result:
        def to_dict(self):
            return {"requested_target_size": observed["target_size"], "wager_placed": False}

    def execute(*, target_size, output_dir):
        observed.update(target_size=target_size, output_dir=output_dir)
        return Result()

    monkeypatch.setattr(cli, "execute_current_accumulator_request", execute)
    assert cli.main(["--target-size", "20", "--output-dir", str(tmp_path)]) == 0
    assert observed == {"target_size": 20, "output_dir": tmp_path}
    assert json.loads(capsys.readouterr().out)["requested_target_size"] == 20
