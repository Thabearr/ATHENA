from __future__ import annotations

from types import SimpleNamespace
import pytest

from domain.current_shadow_sportybet_catalog_fanout_reconciliation import (
    CurrentShadowSportyBetCatalogFanoutReconciliationError,
    validate_fanout_request_scope,
)


def test_validate_fanout_request_scope_rejects_identical_event_sets():
    obs1 = SimpleNamespace(event_ids=("sr:match:100", "sr:match:101"), category_id="sr:category:1", tournament_id="sr:tournament:1")
    obs2 = SimpleNamespace(event_ids=("sr:match:100", "sr:match:101"), category_id="sr:category:1", tournament_id="sr:tournament:2")
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: identical 2 events returned across 2 distinct tournament requests",
    ):
        validate_fanout_request_scope([obs1, obs2])


def test_validate_fanout_request_scope_rejects_repeated_single_events():
    obs1 = SimpleNamespace(event_ids=("sr:match:100",), category_id="sr:category:1", tournament_id="sr:tournament:1")
    obs2 = SimpleNamespace(event_ids=("sr:match:100",), category_id="sr:category:1", tournament_id="sr:tournament:2")
    obs3 = SimpleNamespace(event_ids=("sr:match:100",), category_id="sr:category:1", tournament_id="sr:tournament:3")
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: identical event set returned across 3 distinct tournament requests",
    ):
        validate_fanout_request_scope([obs1, obs2, obs3])


def test_validate_fanout_request_scope_admits_distinct_and_empty():
    obs1 = SimpleNamespace(event_ids=("sr:match:100", "sr:match:101"), category_id="sr:category:1", tournament_id="sr:tournament:1")
    obs2 = SimpleNamespace(event_ids=("sr:match:102",), category_id="sr:category:1", tournament_id="sr:tournament:2")
    obs3 = SimpleNamespace(event_ids=("sr:match:103",), category_id="sr:category:1", tournament_id="sr:tournament:3")
    obs4 = SimpleNamespace(event_ids=(), category_id="sr:category:1", tournament_id="sr:tournament:4")
    events = [
        SimpleNamespace(event_id="sr:match:100", category_id="sr:category:1", tournament_id="sr:tournament:1"),
        SimpleNamespace(event_id="sr:match:101", category_id="sr:category:1", tournament_id="sr:tournament:1"),
        SimpleNamespace(event_id="sr:match:102", category_id="sr:category:1", tournament_id="sr:tournament:2"),
        SimpleNamespace(event_id="sr:match:103", category_id="sr:category:1", tournament_id="sr:tournament:3"),
    ]
    status = validate_fanout_request_scope([obs1, obs2, obs3, obs4], events=events)
    assert status == "FANOUT_REQUEST_SCOPE_PROVEN"


def test_validate_fanout_request_scope_admits_empty_or_single():
    assert validate_fanout_request_scope([], require_proven=False) == "FANOUT_REQUEST_SCOPE_UNPROVEN"
    assert (
        validate_fanout_request_scope(
            [SimpleNamespace(event_ids=("sr:match:100",), category_id="sr:category:1", tournament_id="sr:tournament:1")],
            require_proven=False,
        )
        == "FANOUT_REQUEST_SCOPE_UNPROVEN"
    )
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: fewer than 2 observations provided",
    ):
        validate_fanout_request_scope([])


def test_fanout_request_scope_unproven_on_exact_run_35409481576_shape_reproduction():
    """Exact Run 35409481576 global-echo shape reproduction (synthetic, NOT retained raw evidence).

    Reproduces the exact shape of Run 35409481576:
    - 366 distinct request pairs across 9 native provider competition pairs
    - 366 observations, every observation echoing the exact same ordered 10-event set
    - 10 logical events
    Proves:
    - validate_fanout_request_scope returns FANOUT_REQUEST_SCOPE_UNPROVEN (require_proven=False)
    - validate_fanout_request_scope raises CurrentShadowSportyBetCatalogFanoutReconciliationError (require_proven=True)
    - Historical snapshot replay remains readable without modifying observations or events
    - Request/native IDs are never substituted
    - No runtime authority is gained
    """
    from domain import current_shadow_all_market_runner as runner

    echoed_10_events = tuple(f"sr:match:{9000 + j}" for j in range(10))
    # 9 native provider competition pairs: (f"sr:category:{c}", f"sr:tournament:{c}")
    native_comp_pairs = [(f"sr:category:{c}", f"sr:tournament:{c}") for c in range(1, 10)]

    # 366 distinct request pairs distributed across the 9 native competition pairs
    observations = []
    for i in range(366):
        cat_id, comp_tourn_id = native_comp_pairs[i % 9]
        req_tourn_id = f"{comp_tourn_id}:req:{i}"
        observations.append(
            SimpleNamespace(
                event_ids=echoed_10_events,
                category_id=cat_id,
                tournament_id=req_tourn_id,
            )
        )

    # 10 logical events matching the echoed event IDs
    logical_events = [
        SimpleNamespace(event_id=f"sr:match:{9000 + j}") for j in range(10)
    ]

    # 1. Require validate_fanout_request_scope returns FANOUT_REQUEST_SCOPE_UNPROVEN with require_proven=False
    status = validate_fanout_request_scope(
        observations, events=logical_events, require_proven=False
    )
    assert status == "FANOUT_REQUEST_SCOPE_UNPROVEN"

    # 2. Require validate_fanout_request_scope raises with require_proven=True
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: identical 10 events returned across 366 distinct tournament requests",
    ):
        validate_fanout_request_scope(observations, events=logical_events, require_proven=True)

    # 3. Prove historical snapshot replay remains readable without mutation or ID substitution
    assert len(observations) == 366
    for i, obs in enumerate(observations):
        assert obs.event_ids == echoed_10_events
        cat_id, comp_tourn_id = native_comp_pairs[i % 9]
        assert obs.category_id == cat_id
        assert obs.tournament_id == f"{comp_tourn_id}:req:{i}"

    assert len(logical_events) == 10
    for j, ev in enumerate(logical_events):
        assert ev.event_id == f"sr:match:{9000 + j}"

    # 4. Prove no runtime authority gained
    assert runner.AUTHORITY.get("production_sportybet_execution") is False
    assert runner.AUTHORITY.get("wager_placed") is False
