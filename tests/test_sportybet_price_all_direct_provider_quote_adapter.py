from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_live_event_quote_evidence as live
from domain import sportybet_price_all_direct_provider_quote_adapter as adapter
from domain import sportybet_reviewed_canonical_market_mapping as mapping
from domain import sportybet_user_controlled_native_inventory as native
from domain._price_all_contracts import validate_price_all_contract
from domain.markets import MarketId, OutcomeId
from domain.sportybet_provider_native_inventory import NativeAvailability, NativeSelection


EVENT = "sr:match:123"
SPORT = "sr:sport:1"
INV_SHA = "1" * 64
EVIDENCE = "a" * 24
OBSERVED = datetime(2026, 8, 27, 18, 0, 0, tzinfo=timezone.utc)
KICKOFF = OBSERVED + timedelta(hours=2)


def _mapping_source_selection() -> NativeSelection:
    href = (
        f"/ng/lite/preMatch/detail?eventId={EVENT}&marketId=18&outcomeId=O"
        f"&odds=1.90&productId=3&sportId={SPORT}&marketGroupsName=Main"
        "&specifier=total=2.5"
    )
    return NativeSelection(
        event_id=EVENT,
        sport_id=SPORT,
        product_id="3",
        market_id="18",
        market_group="Main",
        market_name="Total Goals",
        specifier="total=2.5",
        outcome_id="O",
        selection_label="Over 2.5",
        odds_raw="1.90",
        odds_decimal="1.9",
        availability=NativeAvailability.AVAILABLE,
        provider_quote_at=None,
        provider_snapshot_id=None,
        href=href,
    )


def _reviewed_mapping(monkeypatch):
    row = _mapping_source_selection()
    inventory = object.__new__(native.SportyBetUserControlledNativeInventory)
    object.__setattr__(inventory, "source_event_id", EVENT)
    object.__setattr__(inventory, "source_sport_id", SPORT)
    object.__setattr__(inventory, "source_evidence_id", EVIDENCE)
    object.__setattr__(inventory, "provider_quote_at", None)
    object.__setattr__(inventory, "provider_snapshot_id", None)
    object.__setattr__(inventory, "selections", (row,))
    reconciled = SimpleNamespace(
        disposition=(
            reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        ),
        fixture_reconciliation_authorized=True,
        matched_fixture=SimpleNamespace(source_fixture_identifier="987654"),
        source_native_inventory_sha256=INV_SHA,
        sportybet_event_id=EVENT,
        sportybet_sport_id=SPORT,
        source_event_evidence_id=EVIDENCE,
    )
    decision = mapping.ReviewedCanonicalMappingDecision(
        event_id=row.event_id,
        provider_market_id=row.market_id,
        provider_market_name=row.market_name,
        provider_specifier=row.specifier,
        provider_outcome_id=row.outcome_id,
        provider_selection_label=row.selection_label,
        canonical_market_id=MarketId.TOTAL_GOALS,
        canonical_outcome_id=OutcomeId.OVER,
        canonical_line=2.5,
    )
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(
        mapping.reconciliation,
        "canonical_reconciliation_bytes",
        lambda value: b"reconciliation\n",
    )
    return mapping._build(reconciled, inventory, (decision,))


def _raw_event(*, odds: str = "2.17", outcome_id: str = "O") -> bytes:
    payload = {
        "bizCode": 10000,
        "data": {
            "event": {
                "eventId": EVENT,
                "homeTeamName": "Home FC",
                "awayTeamName": "Away FC",
                "estimateStartTime": int(KICKOFF.timestamp() * 1000),
                "bookingStatus": "Available",
                "status": 0,
                "matchStatus": "Not Started",
                "markets": [
                    {
                        "id": "18",
                        "desc": "Total Goals",
                        "specifier": "total=2.5",
                        "outcomes": [
                            {
                                "id": outcome_id,
                                "desc": "Over 2.5",
                                "odds": odds,
                                "isActive": 1,
                            },
                            {
                                "id": "U",
                                "desc": "Under 2.5",
                                "odds": "1.80",
                                "isActive": 1,
                            },
                        ],
                    }
                ],
            }
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _live_bundle(monkeypatch, tmp_path: Path, *, raw: bytes | None = None):
    reviewed = _reviewed_mapping(monkeypatch)
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: ((_raw_event() if raw is None else raw), 200, OBSERVED),
    )
    monkeypatch.setattr(live, "_now_utc", lambda: OBSERVED + timedelta(seconds=5))
    return live.capture_and_issue_current_mapped_quote_bundle(
        mapping=reviewed,
        repository_root=tmp_path,
        execute_live_network=True,
    )


def test_adapter_contract_freezes_direct_source_and_preserves_price_all_v1():
    result = adapter.validate_adapter_contract()
    assert result["adapter_contract_sha256"] == adapter.EXPECTED_CONTRACT_SHA256
    assert result["direct_event_contract_sha256"] == live.EXPECTED_CONTRACT_SHA256
    assert result["legacy_price_all_v1_contract_sha256"] == (
        adapter.LEGACY_PRICE_ALL_V1_CONTRACT_SHA256
    )
    assert validate_price_all_contract()["price_all_contract_sha256"] == (
        "1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa"
    )


def test_live_bundle_adapts_current_direct_price_without_price_all_authority(
    monkeypatch, tmp_path
):
    bundle = _live_bundle(monkeypatch, tmp_path)
    source = adapter.adapt_current_live_quote_bundle(bundle)

    assert source.dataset_name == adapter.DATASET_NAME
    assert source.status == adapter.STATUS
    assert source.event_id == EVENT
    assert source.fixture_id == "987654"
    assert source.source_observed_at == OBSERVED
    assert source.source_evaluation_time == OBSERVED + timedelta(seconds=5)
    assert source.source_bundle_sha256 == live.verify_mapped_quote_bundle(bundle).canonical_sha256
    assert source.authority["direct_provider_quote_source_adaptation"] is True
    assert source.authority["source_live_current_issuance_required"] is True
    assert source.authority["legacy_price_all_v1_consumption_authorized"] is False
    assert source.authority["price_all_value_computation"] is False
    assert source.authority["market_router"] is False
    assert source.authority["final_selection"] is False
    assert source.authority["bet"] is False
    assert source.next_boundary == "PRICE_ALL_V2_DIRECT_PROVIDER_QUOTE_CONSUMPTION_REQUIRED"
    assert source.to_dict()["wager_placed"] is False

    assert len(source.quotes) == 1
    quote = source.quotes[0]
    assert quote.canonical_market_id is MarketId.TOTAL_GOALS
    assert quote.canonical_outcome_id is OutcomeId.OVER
    assert quote.canonical_line == 2.5
    assert quote.odds_raw == "2.17"
    assert quote.decimal_odds == 2.17
    assert quote.observed_at == OBSERVED
    assert quote.observation_authority == live.OBSERVATION_AUTHORITY
    assert quote.provider_quote_at is None
    assert quote.provider_snapshot_id is None
    assert quote.live_inventory_sha256 == bundle.live_inventory_sha256
    assert quote.reviewed_mapping_sha256 == bundle.reviewed_mapping_sha256
    assert quote.fixture_reconciliation_sha256 == (
        bundle._mapping.source_reconciliation_receipt_sha256
    )
    assert quote.source_bundle_sha256 == source.source_bundle_sha256
    assert adapter.verify_direct_provider_price_all_quote_source(source).to_dict() == (
        source.to_dict()
    )


def test_replay_bundle_cannot_be_adapted_as_live_current_source(monkeypatch, tmp_path):
    reviewed = _reviewed_mapping(monkeypatch)
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: (_raw_event(), 200, OBSERVED),
    )
    directory, _manifest = live.capture_live_event_quote_evidence(
        event_id=EVENT,
        repository_root=tmp_path,
        execute_live_network=True,
    )
    replay = live.issue_mapped_quote_bundle_as_of(
        mapping=reviewed,
        evidence_directory=directory,
        repository_root=tmp_path,
        evaluation_time=OBSERVED + timedelta(seconds=5),
    )

    with pytest.raises(
        adapter.SportyBetPriceAllDirectProviderQuoteAdapterError,
        match="LIVE_CURRENT",
    ):
        adapter.adapt_current_live_quote_bundle(replay)


def test_absent_current_mapping_stays_audited_with_zero_quote_source(
    monkeypatch, tmp_path
):
    bundle = _live_bundle(monkeypatch, tmp_path, raw=_raw_event(outcome_id="DIFFERENT"))
    assert bundle.quotes == ()
    assert bundle.mapping_audits[0].disposition == "ABSENT_FROM_CURRENT_EVENT"

    source = adapter.adapt_current_live_quote_bundle(bundle)
    assert source.quotes == ()
    assert source.to_dict()["quote_count"] == 0
    assert source.mapping_audits[0].disposition == "ABSENT_FROM_CURRENT_EVENT"
    assert source.authority["price_all_value_computation"] is False


def test_builder_only_adapter_outputs_and_reconstruction_fail_closed(
    monkeypatch, tmp_path
):
    source = adapter.adapt_current_live_quote_bundle(_live_bundle(monkeypatch, tmp_path))

    with pytest.raises(adapter.SportyBetPriceAllDirectProviderQuoteAdapterError):
        dataclasses.replace(source, status="FAKE")
    with pytest.raises(adapter.SportyBetPriceAllDirectProviderQuoteAdapterError):
        dataclasses.replace(source.quotes[0], odds_raw="9.99")

    object.__setattr__(source, "source_bundle_sha256", "0" * 64)
    with pytest.raises(
        adapter.SportyBetPriceAllDirectProviderQuoteAdapterError,
        match="differs from exact source reconstruction",
    ):
        adapter.verify_direct_provider_price_all_quote_source(source)


def test_tampered_live_source_bundle_is_rejected_before_adaptation(monkeypatch, tmp_path):
    bundle = _live_bundle(monkeypatch, tmp_path)
    object.__setattr__(bundle, "live_inventory_sha256", "0" * 64)
    with pytest.raises(
        adapter.SportyBetPriceAllDirectProviderQuoteAdapterError,
        match="source replay verification failed",
    ):
        adapter.adapt_current_live_quote_bundle(bundle)
