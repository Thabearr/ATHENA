from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import pytest

from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated_discovery
from domain.current_shadow_sportybet_catalog_fanout_reconciliation import (
    CurrentShadowSportyBetCatalogFanoutReconciliationError,
    validate_fanout_request_scope,
)
from scripts import verify_p3_0_e1_live_readiness


def test_paginated_discovery_contract_is_pinned_and_zero_authority():
    contract = paginated_discovery.validate_contract()
    assert contract["contract_sha256"] == paginated_discovery.EXPECTED_CONTRACT_SHA256
    assert contract["contract_sha256"] == "98bedacc3ccbc080312855fdd973545374ba2448dc89b841420bc70147ffaf21"

    authority = paginated_discovery.AUTHORITY
    assert authority["login"] is False
    assert authority["cookies"] is False
    assert authority["wallet"] is False
    assert authority["staking"] is False
    assert authority["bet"] is False
    assert authority["wager_placed"] is False
    assert authority["price_all"] is False
    assert authority["market_router"] is False
    assert authority["final_selection"] is False
    assert authority["sportybet_execution"] is False
    assert authority["fixture_reconciliation_issuer"] is True


def test_validate_contract_drift_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(paginated_discovery, "EXPECTED_CONTRACT_SHA256", "0" * 64)
    with pytest.raises(
        paginated_discovery.CurrentShadowPaginatedDiscoveryReconciliationError,
        match="Current Shadow paginated discovery reconciliation contract drifted",
    ):
        paginated_discovery.validate_contract()


def test_fanout_request_scope_rejection_on_global_echo():
    # 10 identical events returned across multiple distinct tournaments (run 35409481576 pattern)
    echoed_events = tuple(f"sr:match:{1000 + i}" for i in range(10))
    obs1 = SimpleNamespace(event_ids=echoed_events)
    obs2 = SimpleNamespace(event_ids=echoed_events)
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: identical 10 events returned across 2 distinct tournament requests",
    ):
        validate_fanout_request_scope([obs1, obs2])


def test_verify_p3_0_e1_live_readiness_runs_offline_and_passes():
    repo_root = Path(__file__).resolve().parents[1]
    report = verify_p3_0_e1_live_readiness.run_all_readiness_checks(repository_root=repo_root)
    assert report["status"] == "P3_0_E1_LIVE_READINESS_VERIFIED"
    assert len(report["checks"]) == 14
    assert (repo_root / "p3-0-e1-live-readiness.json").exists()
