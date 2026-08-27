from __future__ import annotations

import pytest

from scripts.execute_canonical_accumulator import (
    CanonicalAccumulatorRunnerError,
    _factory_request,
)


def test_runner_factory_contract_rejects_native_or_preselected_payloads():
    with pytest.raises(CanonicalAccumulatorRunnerError, match="exactly"):
        _factory_request(
            lambda: {
                "fixture_inputs": (),
                "target_size": 1,
                "selections": [
                    {
                        "eventId": "sr:match:1",
                        "marketId": "caller-supplied",
                        "outcomeId": "caller-supplied",
                    }
                ],
            }
        )


def test_runner_factory_contract_accepts_only_source_bound_input_tuple():
    fixture_inputs, target_size = _factory_request(
        lambda: {"fixture_inputs": (), "target_size": 1}
    )
    assert fixture_inputs == ()
    assert target_size == 1
