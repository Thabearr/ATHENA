from __future__ import annotations

import ast
from pathlib import Path

import pytest

from domain import current_sportybet_semantic_registry as delegated
from domain import provider_market_semantics as canonical
from domain.markets import MarketId
from tests.test_current_sportybet_semantic_registry import NOW, _evidence


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "domain/provider_market_semantics.py"


def test_canonical_facade_contract_pins_exact_delegated_semantics() -> None:
    identities = canonical.validate_provider_market_semantics_contract()
    assert (
        identities["canonical_provider_market_semantics_contract_sha256"]
        == canonical.EXPECTED_CONTRACT_SHA256
    )
    assert identities["implementation_id"] == "domain.current_sportybet_semantic_registry"
    assert identities["implementation_policy_id"] == delegated.POLICY_ID
    assert dict(identities["source_contract_identities"]) == dict(
        delegated.SOURCE_CONTRACT_IDENTITIES
    )
    assert canonical.calculate_provider_market_semantics_contract_sha256() == canonical.EXPECTED_CONTRACT_SHA256


def test_facade_replay_is_exact_delegated_registry_parity(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    expected = delegated.build_registry((evidence,), evaluation_time=NOW)
    actual = canonical.build_provider_market_semantics_registry((evidence,), evaluation_time=NOW)
    assert type(actual) is delegated.CurrentSportyBetSemanticRegistry
    assert canonical.validate_provider_market_semantics_registry(actual) == delegated.validate_registry(expected)
    assert actual.canonical_bytes == expected.canonical_bytes
    assert actual.canonical_sha256 == expected.canonical_sha256
    assert tuple(item.market_id for item in actual.coverage) == tuple(item.market_id for item in expected.coverage)


def test_facade_preserves_exact_native_semantics_and_unproven_states(tmp_path: Path) -> None:
    value = canonical.build_provider_market_semantics_registry((_evidence(tmp_path),), evaluation_time=NOW)
    for market_id in MarketId:
        assert dict(canonical.provider_policy(market_id)) == dict(delegated.provider_policy(market_id))
    totals = next(item for item in value.coverage if item.market_id is MarketId.TOTAL_GOALS)
    handicap = next(item for item in value.coverage if item.market_id is MarketId.ASIAN_HANDICAP)
    one_up = next(item for item in value.coverage if item.market_id is MarketId.MATCH_RESULT_1UP)
    assert totals.settlement_class is delegated.SettlementClass.TOTALS_EXACT_LINE_SETTLEMENT
    assert handicap.settlement_class is delegated.SettlementClass.ASIAN_HANDICAP_FULL_SETTLEMENT
    assert one_up.settlement_class is delegated.SettlementClass.EARLY_PAYOUT_OVERLAPPING_EVENTS
    assert all(item.provider_status in delegated.ProviderSemanticStatus for item in value.coverage)


def test_facade_is_delegation_not_a_second_mapping_or_downstream_authority() -> None:
    text = CANONICAL_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "domain.current_sportybet_semantic_registry" not in imports
    assert "requests" not in imports
    assert "urllib" not in imports
    assert "domain.price_all" not in imports
    assert "domain.market_router_canonical_adapter" not in imports
    assert "domain.portfolio_optimizer" not in imports
    assert "domain.sportybet_share_code" not in imports
    assert "fuzzy" not in canonical.POLICY_ID.lower()
    assert canonical._contract_payload()["fuzzy_provider_mapping"] is False
    assert canonical._contract_payload()["price_all_authority"] is False
    assert canonical._contract_payload()["market_router_authority"] is False
    assert canonical._contract_payload()["portfolio_authority"] is False
    assert canonical._contract_payload()["share_code_transport_authority"] is False


def test_facade_contract_fails_closed_on_delegated_contract_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    class DriftedDelegate:
        POLICY_ID = delegated.POLICY_ID
        SCHEMA_VERSION = delegated.SCHEMA_VERSION
        DATASET_NAME = delegated.DATASET_NAME
        CONTRACT_VERSION = delegated.CONTRACT_VERSION
        SOURCE_CONTRACT_IDENTITIES = {**delegated.SOURCE_CONTRACT_IDENTITIES, "event_detail": "0" * 64}
        MarketId = delegated.MarketId
        ProviderSemanticStatus = delegated.ProviderSemanticStatus
        SettlementClass = delegated.SettlementClass
        EvidenceFreshnessState = delegated.EvidenceFreshnessState
        _AUTHORITY = delegated._AUTHORITY

    monkeypatch.setattr(canonical, "_implementation", lambda: DriftedDelegate)
    with pytest.raises(canonical.ProviderMarketSemanticsError, match="source contracts drifted"):
        canonical.validate_provider_market_semantics_contract()
