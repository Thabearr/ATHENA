from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_direct_provider_canonical_market_mapping_rebind as mapping
from domain import current_direct_provider_live_quote_mapping_consumption as quotes
from domain import sportybet_live_event_quote_evidence as live
from domain.markets import MarketId, OutcomeId
from domain.sportybet_reviewed_canonical_market_mapping import (
    SettlementEquivalenceAuthority,
)

EVENT = "sr:match:222"
FIXTURE = "987654"
EVALUATION = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
KICKOFF = EVALUATION + timedelta(hours=2)


def _selection(
    *,
    market_id="18",
    market_name="Total Goals",
    specifier="total=2.5",
    outcome_id="O",
    outcome_name="Over 2.5",
    odds_raw="2.10",
    decimal_odds=2.1,
    bookable=True,
):
    return live.SportyBetLiveEventSelection(
        event_id=EVENT,
        market_id=market_id,
        market_name=market_name,
        specifier=specifier,
        outcome_id=outcome_id,
        outcome_name=outcome_name,
        bookable=bookable,
        bookability_basis="EXPLICIT_ACTIVE_FLAG",
        odds_raw=odds_raw,
        odds_decimal=decimal_odds,
    )


def _inventory(*rows, observed_at=None, kickoff=KICKOFF):
    return live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=EVENT,
        home_team_name="Current Home FC",
        away_team_name="Current Away FC",
        kickoff_utc=kickoff,
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        observed_at=observed_at or (EVALUATION - timedelta(seconds=60)),
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256="a" * 64,
        source_raw_sha256="b" * 64,
        selections=tuple(rows or (_selection(),)),
    )


def _mapped_row(
    inventory,
    *,
    market_id="18",
    market_name="Total Goals",
    specifier="total=2.5",
    outcome_id="O",
    outcome_name="Over 2.5",
    canonical_market=MarketId.TOTAL_GOALS,
    canonical_outcome=OutcomeId.OVER,
    line=2.5,
    bookable=True,
    bookmaker_equivalence=True,
    settlement=SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE,
):
    value = object.__new__(mapping.CurrentDirectProviderCanonicalMappedSelection)
    fields = {
        "fixture_id": FIXTURE,
        "event_id": EVENT,
        "provider_market_id": market_id,
        "provider_market_name": market_name,
        "provider_specifier": specifier,
        "provider_outcome_id": outcome_id,
        "provider_outcome_name": outcome_name,
        "canonical_market_id": canonical_market,
        "canonical_outcome_id": canonical_outcome,
        "canonical_line": line,
        "canonical_display_label": "Over 2.5" if line is not None else "Home",
        "canonical_selection_display_name": (
            "Total Goals — Over 2.5" if line is not None else "Home"
        ),
        "settlement_equivalence_authority": settlement,
        "settlement_evidence_sha256": None,
        "bookmaker_equivalence_authorized": bookmaker_equivalence,
        "current_bookable_observed": bookable,
        "current_bookability_basis": "EXPLICIT_ACTIVE_FLAG",
        "source_mapping_row_sha256": "1" * 64,
        "current_inventory_sha256": inventory.canonical_sha256,
        "canonical_market_mapping_authorized": True,
    }
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


def _source_mapping(
    inventory,
    *mapped_rows,
    proof_mode=mapping.LIVE_CURRENT,
    mapping_evaluation=None,
    discovery_observed_at=None,
    kickoff=None,
):
    mapping_evaluation = mapping_evaluation or (EVALUATION - timedelta(seconds=30))
    discovery_observed_at = discovery_observed_at or (
        inventory.observed_at - timedelta(seconds=30)
    )
    kickoff = kickoff or inventory.kickoff_utc
    mapped_rows = tuple(mapped_rows or (_mapped_row(inventory),))
    value = object.__new__(mapping.CurrentDirectProviderCanonicalMarketMappingRebind)
    represented = tuple(
        market_id
        for market_id in mapping.legacy.TARGET_MARKET_IDS
        if any(item.canonical_market_id is market_id for item in mapped_rows)
    )
    unrepresented = tuple(
        market_id
        for market_id in mapping.legacy.TARGET_MARKET_IDS
        if market_id not in represented
    )
    fields = {
        "schema_version": mapping.SCHEMA_VERSION,
        "dataset_name": mapping.DATASET_NAME,
        "status": mapping.STATUS,
        "proof_mode": proof_mode,
        "disposition": (
            mapping.RebindDisposition.REBOUND_EXACT_REVIEWED_SEMANTICS
            if mapped_rows
            else mapping.RebindDisposition.NO_EXACT_REVIEWED_SEMANTICS
        ),
        "evaluation_time": mapping_evaluation,
        "event_id": EVENT,
        "fixture_id": FIXTURE,
        "home_team_name": inventory.home_team_name,
        "away_team_name": inventory.away_team_name,
        "kickoff_utc": kickoff,
        "discovery_observed_at": discovery_observed_at,
        "direct_event_observed_at": inventory.observed_at,
        "discovery_age_seconds": (
            mapping_evaluation - discovery_observed_at
        ).total_seconds(),
        "direct_event_age_seconds": (
            mapping_evaluation - inventory.observed_at
        ).total_seconds(),
        "kickoff_lead_seconds": (kickoff - mapping_evaluation).total_seconds(),
        "max_source_age_seconds": mapping.MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": mapping.MINIMUM_LEAD_SECONDS,
        "source_current_reconciliation_sha256": "2" * 64,
        "source_current_reconciliation_contract_sha256": mapping.PR251_CONTRACT_SHA256,
        "source_legacy_mapping_sha256": "3" * 64,
        "source_legacy_review_decisions_sha256": "4" * 64,
        "source_legacy_event_id": "sr:match:111",
        "source_legacy_fixture_id": "123456",
        "current_inventory_sha256": inventory.canonical_sha256,
        "current_manifest_sha256": inventory.source_manifest_sha256,
        "current_raw_sha256": inventory.source_raw_sha256,
        "mapped_selections": mapped_rows,
        "mapping_audits": (),
        "source_template_count": len(mapped_rows),
        "mapped_selection_count": len(mapped_rows),
        "unreviewed_current_selection_count": 0,
        "represented_target_market_ids": represented,
        "unrepresented_target_market_ids": unrepresented,
        "all_source_templates_rebound": True,
        "all_15_target_markets_represented": not unrepresented,
        "authority": {
            "current_event_source_replay": True,
            "legacy_reviewed_mapping_source_replay": True,
            "exact_provider_semantic_rebind": bool(mapped_rows),
            "canonical_market_mapping": bool(mapped_rows),
            "bookmaker_equivalence": bool(mapped_rows)
            and all(item.bookmaker_equivalence_authorized for item in mapped_rows),
            "as_of_source_freshness": True,
            "wall_clock_currentness_at_issuance": proof_mode == mapping.LIVE_CURRENT,
            "fresh_price": False,
            "price_all": False,
            "market_router": False,
            "portfolio_optimization": False,
            "final_selection": False,
            "accumulator_slip_construction": False,
            "sportybet_execution": False,
            "staking": False,
            "bet": False,
        },
        "next_boundary": mapping.NEXT_BOUNDARY,
        "contract_sha256": mapping.EXPECTED_CONTRACT_SHA256,
        "_current_bundle": SimpleNamespace(
            _detail_directories=((EVENT, Path("/tmp/current-event-detail")),),
            _repository_root=Path("/tmp/repository"),
        ),
        "_target_event_id": EVENT,
        "_legacy_reconciliation_receipt_directory": "receipt",
        "_legacy_reconciliation_source_bundle": "source",
        "_legacy_review_decisions": (),
        "_legacy_repository_root": Path("/tmp/legacy"),
        "_early_payout_settlement_receipt": None,
        "_early_payout_settlement_receipt_bytes": None,
    }
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


def _install(monkeypatch, source_mapping, inventory):
    calls = {"mapping": 0, "inventory": 0}

    def verify_mapping(value):
        calls["mapping"] += 1
        assert value is source_mapping
        return source_mapping

    def build_inventory(directory, *, repository_root):
        calls["inventory"] += 1
        assert Path(directory) == Path("/tmp/current-event-detail")
        return inventory

    monkeypatch.setattr(
        quotes.mapping,
        "verify_current_direct_provider_canonical_mapping_rebind",
        verify_mapping,
    )
    monkeypatch.setattr(
        quotes.live,
        "build_live_event_quote_inventory",
        build_inventory,
    )
    return calls


def _build(monkeypatch, inventory=None, source_mapping=None, evaluation=EVALUATION):
    inventory = inventory or _inventory()
    source_mapping = source_mapping or _source_mapping(inventory)
    calls = _install(monkeypatch, source_mapping, inventory)
    result = quotes.issue_current_direct_provider_mapped_quotes_as_of(
        source_mapping=source_mapping,
        evaluation_time=evaluation,
    )
    return result, calls


def test_contract_pins_pr252_and_pr246_exactly():
    result = quotes.validate_current_live_quote_mapping_contract()
    assert result["current_live_quote_mapping_contract_sha256"] == (
        "671e6016093bc3f30141ddd13ab259bebb70086945fb30a588a185703fd128d4"
    )
    assert result["pr252_contract_sha256"] == mapping.EXPECTED_CONTRACT_SHA256
    assert result["direct_event_contract_sha256"] == live.EXPECTED_CONTRACT_SHA256
    assert quotes.calculate_current_live_quote_mapping_contract_sha256() == (
        quotes.EXPECTED_CONTRACT_SHA256
    )


def test_exact_current_quote_uses_pr246_odds_and_preserves_ancestry(monkeypatch):
    result, calls = _build(monkeypatch)
    assert calls == {"mapping": 1, "inventory": 1}
    assert result.quote_audits[0].disposition is quotes.QuoteAuditDisposition.QUOTED
    assert len(result.quotes) == 1
    quote = result.quotes[0]
    assert quote.event_id == EVENT
    assert quote.fixture_id == FIXTURE
    assert quote.odds_raw == "2.10"
    assert quote.decimal_odds == 2.1
    assert quote.current_inventory_sha256 == result.current_inventory_sha256
    assert quote.current_mapping_rebind_sha256 == result.current_mapping_rebind_sha256
    assert quote.source_current_reconciliation_sha256 == "2" * 64
    assert quote.source_legacy_mapping_sha256 == "3" * 64
    assert quote.provider_quote_at is None
    assert quote.provider_snapshot_id is None
    assert result.authority["current_provider_mapped_quote_evidence"] is True
    assert result.authority["price_all"] is False
    assert result.authority["market_router"] is False
    assert result.authority["portfolio_optimization"] is False
    assert result.authority["sportybet_execution"] is False
    assert result.authority["staking"] is False
    assert result.authority["bet"] is False


def test_currently_unavailable_mapping_is_audited_without_quote(monkeypatch):
    inventory = _inventory(_selection(bookable=False))
    row = _mapped_row(inventory, bookable=False)
    source = _source_mapping(inventory, row)
    result, _ = _build(monkeypatch, inventory=inventory, source_mapping=source)
    assert result.quotes == ()
    assert result.quote_audits[0].disposition is (
        quotes.QuoteAuditDisposition.CURRENTLY_UNAVAILABLE
    )
    assert result.authority["current_provider_mapped_quote_evidence"] is False


def test_unproven_early_payout_settlement_never_issues_quote(monkeypatch):
    inventory = _inventory(
        _selection(
            market_id="60200",
            market_name="Match Result 1UP",
            specifier=None,
            outcome_id="1",
            outcome_name="Home",
        )
    )
    row = _mapped_row(
        inventory,
        market_id="60200",
        market_name="Match Result 1UP",
        specifier=None,
        outcome_id="1",
        outcome_name="Home",
        canonical_market=MarketId.MATCH_RESULT_1UP,
        canonical_outcome=OutcomeId.HOME,
        line=None,
        bookmaker_equivalence=False,
        settlement=SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN,
    )
    source = _source_mapping(inventory, row)
    result, _ = _build(monkeypatch, inventory=inventory, source_mapping=source)
    assert result.quotes == ()
    assert result.quote_audits[0].disposition is (
        quotes.QuoteAuditDisposition.SETTLEMENT_EQUIVALENCE_UNPROVEN
    )


def test_pr252_provider_label_drift_against_replayed_inventory_fails_closed(monkeypatch):
    inventory = _inventory(_selection(market_name="Changed Total Goals"))
    row = _mapped_row(inventory, market_name="Total Goals")
    source = _source_mapping(inventory, row)
    _install(monkeypatch, source, inventory)
    with pytest.raises(
        quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError,
        match="differs from exact current provider identity",
    ):
        quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=source,
            evaluation_time=EVALUATION,
        )


def test_quote_boundary_rechecks_staleness_after_valid_earlier_mapping(monkeypatch):
    inventory = _inventory(observed_at=EVALUATION - timedelta(seconds=901))
    source = _source_mapping(
        inventory,
        mapping_evaluation=EVALUATION - timedelta(seconds=60),
        discovery_observed_at=EVALUATION - timedelta(seconds=900),
    )
    _install(monkeypatch, source, inventory)
    with pytest.raises(
        quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError,
        match="stale",
    ):
        quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=source,
            evaluation_time=EVALUATION,
        )


def test_quote_boundary_rejects_exact_120_second_kickoff_lead(monkeypatch):
    kickoff = EVALUATION + timedelta(seconds=120)
    inventory = _inventory(kickoff=kickoff)
    source = _source_mapping(
        inventory,
        mapping_evaluation=EVALUATION - timedelta(seconds=60),
        kickoff=kickoff,
    )
    _install(monkeypatch, source, inventory)
    with pytest.raises(
        quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError,
        match="too close to kickoff",
    ):
        quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=source,
            evaluation_time=EVALUATION,
        )


def test_quote_evaluation_cannot_predate_pr252_mapping_issuance(monkeypatch):
    inventory = _inventory()
    source = _source_mapping(inventory, mapping_evaluation=EVALUATION)
    _install(monkeypatch, source, inventory)
    with pytest.raises(
        quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError,
        match="cannot predate PR252",
    ):
        quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=source,
            evaluation_time=EVALUATION - timedelta(seconds=1),
        )


def test_live_issuer_requires_pr252_live_current_proof(monkeypatch):
    inventory = _inventory()
    source = _source_mapping(inventory, proof_mode=mapping.AS_OF_REPLAY)
    _install(monkeypatch, source, inventory)
    monkeypatch.setattr(quotes, "_now_utc", lambda: EVALUATION)
    with pytest.raises(
        quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError,
        match="requires a PR252 LIVE_CURRENT",
    ):
        quotes.issue_current_direct_provider_mapped_quotes(source_mapping=source)


def test_live_issuer_rechecks_now_and_marks_only_quote_currentness(monkeypatch):
    inventory = _inventory()
    source = _source_mapping(inventory, proof_mode=mapping.LIVE_CURRENT)
    _install(monkeypatch, source, inventory)
    monkeypatch.setattr(quotes, "_now_utc", lambda: EVALUATION)
    result = quotes.issue_current_direct_provider_mapped_quotes(
        source_mapping=source
    )
    assert result.proof_mode == quotes.LIVE_CURRENT
    assert result.status == quotes.STATUS_LIVE
    assert result.authority["wall_clock_currentness_at_issuance"] is True
    assert result.authority["price_all"] is False


def test_no_rebound_semantics_is_valid_zero_quote_output(monkeypatch):
    inventory = _inventory()
    source = _source_mapping(inventory)
    object.__setattr__(source, "mapped_selections", ())
    object.__setattr__(source, "source_template_count", 0)
    object.__setattr__(source, "mapped_selection_count", 0)
    object.__setattr__(
        source,
        "disposition",
        mapping.RebindDisposition.NO_EXACT_REVIEWED_SEMANTICS,
    )
    object.__setattr__(source, "represented_target_market_ids", ())
    object.__setattr__(
        source, "unrepresented_target_market_ids", tuple(mapping.legacy.TARGET_MARKET_IDS)
    )
    object.__setattr__(source, "all_15_target_markets_represented", False)
    authority = dict(source.authority)
    authority["exact_provider_semantic_rebind"] = False
    authority["canonical_market_mapping"] = False
    authority["bookmaker_equivalence"] = False
    object.__setattr__(source, "authority", authority)
    _install(monkeypatch, source, inventory)
    result = quotes.issue_current_direct_provider_mapped_quotes_as_of(
        source_mapping=source,
        evaluation_time=EVALUATION,
    )
    assert result.quotes == ()
    assert result.quote_audits == ()
    assert result.authority["current_provider_mapped_quote_evidence"] is False
    assert result.next_boundary == quotes.NEXT_BOUNDARY


def test_builder_only_and_public_tamper_fail_exact_reconstruction(monkeypatch):
    result, _ = _build(monkeypatch)
    with pytest.raises(quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError):
        quotes.CurrentDirectProviderMappedQuote()
    with pytest.raises(quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError):
        quotes.CurrentDirectProviderMappedQuoteBundle()

    object.__setattr__(result, "fixture_id", "tampered")
    with pytest.raises(
        quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError,
        match="differs from exact retained-source reconstruction",
    ):
        quotes.verify_current_direct_provider_mapped_quote_bundle(result)
