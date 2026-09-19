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
