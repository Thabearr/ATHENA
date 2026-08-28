from __future__ import annotations

import json

import pytest

from domain import current_sportybet_accumulator_request as request
from scripts import execute_current_sportybet_accumulator as cli


def test_fixed_target_twenty_request_stops_at_exact_phase6_authority_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(request, "_now_utc", lambda: request.datetime(2026, 8, 28, tzinfo=request.timezone.utc))
    result = request.execute_current_accumulator_request(target_size=20, output_dir=tmp_path)
    assert result.requested_target_size == 20
    assert result.status == request.STATUS_PHASE6_AUTHORITY_REQUIRED
    assert result.blocked_at == "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION"
    assert result.real_current_provider_execution_attempted is False
    assert result.wager_placed is False
    payload = json.loads((tmp_path / "current-sportybet-accumulator-request.json").read_text())
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
