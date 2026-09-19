from __future__ import annotations

from types import SimpleNamespace
import pytest

from domain.current_shadow_sportybet_catalog_fanout_reconciliation import (
    CurrentShadowSportyBetCatalogFanoutReconciliationError,
    validate_fanout_request_scope,
)


def test_validate_fanout_request_scope_rejects_identical_event_sets():
    obs1 = SimpleNamespace(event_ids=("sr:match:100", "sr:match:101"))
    obs2 = SimpleNamespace(event_ids=("sr:match:100", "sr:match:101"))
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: identical 2 events returned across 2 distinct tournament requests",
    ):
        validate_fanout_request_scope([obs1, obs2])


def test_validate_fanout_request_scope_rejects_repeated_single_events():
    obs1 = SimpleNamespace(event_ids=("sr:match:100",))
    obs2 = SimpleNamespace(event_ids=("sr:match:100",))
    obs3 = SimpleNamespace(event_ids=("sr:match:100",))
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: identical event set returned across 3 distinct tournament requests",
    ):
        validate_fanout_request_scope([obs1, obs2, obs3])


def test_validate_fanout_request_scope_admits_distinct_and_partially_overlapping():
    obs1 = SimpleNamespace(event_ids=("sr:match:100", "sr:match:101"))
    obs2 = SimpleNamespace(event_ids=("sr:match:101", "sr:match:102"))
    obs3 = SimpleNamespace(event_ids=("sr:match:103",))
    obs4 = SimpleNamespace(event_ids=())
    # Should not raise
    validate_fanout_request_scope([obs1, obs2, obs3, obs4])


def test_validate_fanout_request_scope_admits_empty_or_single():
    validate_fanout_request_scope([])
    validate_fanout_request_scope([SimpleNamespace(event_ids=("sr:match:100",))])
    validate_fanout_request_scope([SimpleNamespace(event_ids=()), SimpleNamespace(event_ids=())])
