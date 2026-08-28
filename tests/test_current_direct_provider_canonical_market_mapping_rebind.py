from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_direct_provider_canonical_market_mapping_rebind as rebind
from domain import sportybet_current_event_discovery_reconciliation as current
from domain import sportybet_live_event_quote_evidence as live
from domain import sportybet_reviewed_canonical_market_mapping as legacy
from domain.markets import MarketId, OutcomeId, make_selection
from domain.sportybet_provider_native_inventory import NativeAvailability

SOURCE_EVENT = "sr:match:111"
CURRENT_EVENT = "sr:match:222"
SPORT = "sr:sport:1"
SOURCE_FIXTURE = "123456"
CURRENT_FIXTURE = "987654"
EVALUATION = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
KICKOFF = EVALUATION + timedelta(hours=2)


def _source_row(
    *,
    market_id: str = "18",
    market_name: str = "Total Goals",
    specifier: str | None = "total=2.5",
    outcome_id: str = "O",
    outcome_name: str = "Over 2.5",
    canonical_market: MarketId = MarketId.TOTAL_GOALS,
    canonical_outcome: OutcomeId = OutcomeId.OVER,
    line: float | None = 2.5,
    bookmaker_equivalence: bool = True,
):
    canonical = make_selection(canonical_market, canonical_outcome, line=line)
    if canonical_market in {MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}:
        settlement_authority = (
            legacy.SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
        )
        settlement_sha = None
        bookmaker_equivalence = False
    else:
        settlement_authority = (
            legacy.SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE
        )
        settlement_sha = None
    return legacy.MappedSportyBetCanonicalSelection(
        provider_selection_sha256="1" * 64,
        event_id=SOURCE_EVENT,
        provider_market_id=market_id,
        provider_market_name=market_name,
        provider_specifier=specifier,
        provider_outcome_id=outcome_id,
        provider_selection_label=outcome_name,
        availability=NativeAvailability.AVAILABLE.value,
        odds_raw="1.90",
        odds_decimal="1.9",
        provider_quote_at=None,
        provider_snapshot_id=None,
        canonical_market_id=canonical.market_id,
        canonical_outcome_id=canonical.outcome_id,
        canonical_line=canonical.line,
        canonical_display_label=canonical.display_label,
        canonical_selection_display_name=canonical.selection_display_name,
        settlement_equivalence_authority=settlement_authority,
        settlement_evidence_sha256=settlement_sha,
        bookmaker_equivalence_authorized=bookmaker_equivalence,
        canonical_market_mapping_authorized=True,
        fresh_price_authorized=False,
        href="/ng/lite/preMatch/detail",
    )


def _source_mapping(*rows):
    rows = tuple(rows or (_source_row(),))
    represented = tuple(
        market_id
        for market_id in legacy.TARGET_MARKET_IDS
        if any(row.canonical_market_id is market_id for row in rows)
    )
    missing = tuple(
        market_id for market_id in legacy.TARGET_MARKET_IDS if market_id not in represented
    )
    all_equivalent = all(row.bookmaker_equivalence_authorized for row in rows)
    return legacy.SportyBetReviewedCanonicalMarketMapping(
        schema_version=legacy.SCHEMA_VERSION,
        dataset_name=legacy.DATASET_NAME,
        provider=legacy.PROVIDER,
        status=legacy.STATUS,
        review_basis=legacy.REVIEW_BASIS,
        source_reconciliation_receipt_sha256="2" * 64,
        source_native_inventory_sha256="3" * 64,
        source_event_evidence_id="reviewed-source-evidence",
        sportybet_event_id=SOURCE_EVENT,
        sportybet_sport_id=SPORT,
        matched_fotmob_fixture_id=SOURCE_FIXTURE,
        review_decisions_sha256="4" * 64,
        mapped_selections=rows,
        represented_target_market_ids=represented,
        unrepresented_target_market_ids=missing,
        all_15_target_markets_represented=not missing,
        mapped_selection_count=len(rows),
        unmapped_native_selection_count=0,
        safety={
            "bet_authorized": False,
            "bookmaker_equivalence_authorized": all_equivalent,
            "booking_code_authorized": False,
            "canonical_market_mapping_authorized": True,
            "fixture_reconciliation_authorized": True,
            "fresh_price_authorized": False,
            "model_integration_authorized": False,
            "network_acquisition_authorized": False,
            "pricing_authorized": False,
            "selection_authorized": False,
            "slip_construction_authorized": False,
            "sportybet_execution_authorized": False,
        },
    )


def _decision(row=None):
    row = row or _source_row()
    return legacy.ReviewedCanonicalMappingDecision(
        event_id=SOURCE_EVENT,
        provider_market_id=row.provider_market_id,
        provider_market_name=row.provider_market_name,
        provider_specifier=row.provider_specifier,
        provider_outcome_id=row.provider_outcome_id,
        provider_selection_label=row.provider_selection_label,
        canonical_market_id=row.canonical_market_id,
        canonical_outcome_id=row.canonical_outcome_id,
        canonical_line=row.canonical_line,
    )


def _selection(
    *,
    market_id: str = "18",
    market_name: str = "Total Goals",
    specifier: str | None = "total=2.5",
    outcome_id: str = "O",
    outcome_name: str = "Over 2.5",
    bookable: bool = True,
):
    return live.SportyBetLiveEventSelection(
        event_id=CURRENT_EVENT,
        market_id=market_id,
        market_name=market_name,
        specifier=specifier,
        outcome_id=outcome_id,
        outcome_name=outcome_name,
        bookable=bookable,
        bookability_basis="EXPLICIT_ACTIVE_FLAG",
        odds_raw="2",
        odds_decimal=2.0,
    )


def _inventory(*selections, observed_at=None, kickoff=KICKOFF):
    selections = tuple(selections or (_selection(),))
    return live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=CURRENT_EVENT,
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
        selections=selections,
    )


def _current_bundle(inventory, *, discovery_observed_at=None, kickoff=None, disposition=None):
    kickoff = kickoff or inventory.kickoff_utc
    discovery_observed_at = discovery_observed_at or (
        EVALUATION - timedelta(seconds=90)
    )
    disposition = disposition or (
        current.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
    )
    authorized = (
        disposition
        is current.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
    )
    row = current.CurrentEventReconciliationRow(
        event_id=CURRENT_EVENT,
        home_team_name=inventory.home_team_name,
        away_team_name=inventory.away_team_name,
        competition_name="Premier League",
        kickoff_utc=kickoff,
        discovery_observed_at=discovery_observed_at,
        discovery_age_seconds=30.0,
        kickoff_lead_seconds=(kickoff - (EVALUATION - timedelta(seconds=30))).total_seconds(),
        disposition=disposition,
        exact_fotmob_match_count=1,
        matched_fotmob_fixture_id=(CURRENT_FIXTURE if authorized else None),
        direct_event_observed_at=(inventory.observed_at if authorized else None),
        direct_event_age_seconds=(30.0 if authorized else None),
        direct_event_manifest_sha256=(inventory.source_manifest_sha256 if authorized else None),
        direct_event_inventory_sha256=(inventory.canonical_sha256 if authorized else None),
        direct_event_raw_sha256=(inventory.source_raw_sha256 if authorized else None),
        fixture_reconciliation_authorized=authorized,
    )
    bundle = SimpleNamespace(
        evaluation_time=EVALUATION - timedelta(seconds=30),
        max_source_age_seconds=current.MAX_SOURCE_AGE_SECONDS,
        minimum_lead_seconds=current.MINIMUM_LEAD_SECONDS,
        contract_sha256=current.EXPECTED_CONTRACT_SHA256,
        rows=(row,),
        _detail_directories=((CURRENT_EVENT, Path("/tmp/current-event-detail")),),
        _repository_root=Path("/tmp/repository"),
        to_dict=lambda: {
            "dataset_name": current.DATASET_NAME,
            "event_id": CURRENT_EVENT,
            "fixture_id": CURRENT_FIXTURE,
            "contract_sha256": current.EXPECTED_CONTRACT_SHA256,
        },
    )
    return bundle


def _install_sources(monkeypatch, inventory, source_mapping=None, current_bundle=None):
    source_mapping = source_mapping or _source_mapping()
    current_bundle = current_bundle or _current_bundle(inventory)
    calls = {"current": 0, "legacy": 0, "inventory": 0}

    def verify_current(value):
        calls["current"] += 1
        assert value is current_bundle
        return current_bundle

    def rebuild_legacy(**kwargs):
        calls["legacy"] += 1
        assert kwargs["reconciliation_receipt_directory"] == "legacy-receipt"
        assert kwargs["reconciliation_source_bundle"] == "legacy-source"
        return source_mapping

    def rebuild_inventory(directory, *, repository_root):
        calls["inventory"] += 1
        assert Path(directory) == Path("/tmp/current-event-detail")
        return inventory

    monkeypatch.setattr(
        rebind.current,
        "verify_current_event_discovery_reconciliation_bundle",
        verify_current,
    )
    monkeypatch.setattr(
        rebind.legacy,
        "build_reviewed_canonical_market_mapping",
        rebuild_legacy,
    )
    monkeypatch.setattr(
        rebind.live,
        "build_live_event_quote_inventory",
        rebuild_inventory,
    )
    return current_bundle, source_mapping, calls


def _build(monkeypatch, inventory=None, source_mapping=None, current_bundle=None, evaluation=EVALUATION):
    inventory = inventory or _inventory()
    current_bundle, source_mapping, calls = _install_sources(
        monkeypatch,
        inventory,
        source_mapping=source_mapping,
        current_bundle=current_bundle,
    )
    source_row = source_mapping.mapped_selections[0]
    result = rebind.rebind_current_direct_provider_canonical_mapping_as_of(
        current_reconciliation_bundle=current_bundle,
        target_event_id=CURRENT_EVENT,
        legacy_reconciliation_receipt_directory="legacy-receipt",
        legacy_reconciliation_source_bundle="legacy-source",
        legacy_review_decisions=(_decision(source_row),),
        legacy_repository_root=Path("/tmp/legacy-repository"),
        evaluation_time=evaluation,
    )
    return result, calls


def test_contract_pins_pr251_and_exact_15_market_registry():
    assert rebind.validate_current_mapping_rebind_contract() == rebind.EXPECTED_CONTRACT_SHA256
    assert rebind.calculate_current_mapping_rebind_contract_sha256() == (
        "de022fd931313fa8d3c2c093ff0cb9b12f2c0f1ba0d9adc4b646c94dfd306e96"
    )
    assert rebind.PR251_CONTRACT_SHA256 == current.EXPECTED_CONTRACT_SHA256
    assert tuple(legacy.TARGET_MARKET_IDS) == tuple(rebind.legacy.TARGET_MARKET_IDS)
    assert set(legacy.TARGET_MARKET_IDS) == set(rebind.MARKET_REGISTRY)


def test_exact_semantics_rebind_to_different_current_event_without_copying_odds(monkeypatch):
    result, calls = _build(monkeypatch)
    assert calls == {"current": 1, "legacy": 1, "inventory": 1}
    assert result.event_id == CURRENT_EVENT
    assert result.source_legacy_event_id == SOURCE_EVENT
    assert result.fixture_id == CURRENT_FIXTURE
    assert result.source_legacy_fixture_id == SOURCE_FIXTURE
    assert result.disposition is rebind.RebindDisposition.REBOUND_EXACT_REVIEWED_SEMANTICS
    assert result.mapped_selection_count == 1
    mapped = result.mapped_selections[0]
    assert mapped.event_id == CURRENT_EVENT
    assert mapped.canonical_market_id is MarketId.TOTAL_GOALS
    assert mapped.canonical_outcome_id is OutcomeId.OVER
    assert mapped.canonical_line == 2.5
    assert mapped.bookmaker_equivalence_authorized is True
    payload = result.to_dict()
    assert "odds_raw" not in payload["mapped_selections"][0]
    assert "decimal_odds" not in payload["mapped_selections"][0]
    assert payload["provider_quote_at"] is None
    assert payload["provider_snapshot_id"] is None
    assert result.authority["fresh_price"] is False
    assert result.authority["price_all"] is False
    assert result.authority["market_router"] is False
    assert result.authority["portfolio_optimization"] is False
    assert result.authority["sportybet_execution"] is False
    assert result.authority["staking"] is False
    assert result.authority["bet"] is False
    assert result.next_boundary == rebind.NEXT_BOUNDARY


def test_current_label_drift_is_explicit_and_not_rebound(monkeypatch):
    inventory = _inventory(_selection(market_name="Different Total Goals"))
    result, _ = _build(monkeypatch, inventory=inventory)
    assert result.mapped_selections == ()
    assert result.disposition is rebind.RebindDisposition.NO_EXACT_REVIEWED_SEMANTICS
    assert result.mapping_audits[0].disposition is (
        rebind.RebindAuditDisposition.CURRENT_PROVIDER_LABEL_DRIFT_REJECTED
    )
    assert result.authority["canonical_market_mapping"] is False


def test_exact_line_is_not_generalized_to_different_current_specifier(monkeypatch):
    inventory = _inventory(_selection(specifier="total=3.5", outcome_name="Over 3.5"))
    result, _ = _build(monkeypatch, inventory=inventory)
    assert result.mapped_selections == ()
    assert result.mapping_audits[0].disposition is (
        rebind.RebindAuditDisposition.SOURCE_TEMPLATE_ABSENT_FROM_CURRENT_EVENT
    )
    assert result.unreviewed_current_selection_count == 1
    assert MarketId.TOTAL_GOALS in result.unrepresented_target_market_ids


def test_unavailable_current_selection_may_map_semantics_but_never_price(monkeypatch):
    inventory = _inventory(_selection(bookable=False))
    result, _ = _build(monkeypatch, inventory=inventory)
    mapped = result.mapped_selections[0]
    assert mapped.current_bookable_observed is False
    assert result.authority["canonical_market_mapping"] is True
    assert result.authority["fresh_price"] is False
    assert "odds_raw" not in mapped.to_dict()


def test_early_payout_unproven_settlement_authority_cannot_be_upgraded(monkeypatch):
    source_row = _source_row(
        market_id="60200",
        market_name="Match Result 1UP",
        specifier=None,
        outcome_id="1",
        outcome_name="Home",
        canonical_market=MarketId.MATCH_RESULT_1UP,
        canonical_outcome=OutcomeId.HOME,
        line=None,
    )
    source_mapping = _source_mapping(source_row)
    inventory = _inventory(
        _selection(
            market_id="60200",
            market_name="Match Result 1UP",
            specifier=None,
            outcome_id="1",
            outcome_name="Home",
        )
    )
    result, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=source_mapping,
    )
    mapped = result.mapped_selections[0]
    assert mapped.settlement_equivalence_authority is (
        legacy.SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
    )
    assert mapped.bookmaker_equivalence_authorized is False
    assert result.authority["bookmaker_equivalence"] is False


def test_current_selection_without_reviewed_template_is_reported_not_invented(monkeypatch):
    inventory = _inventory(
        _selection(),
        _selection(
            market_id="1",
            market_name="Match Result",
            specifier=None,
            outcome_id="1",
            outcome_name="Home",
        ),
    )
    result, _ = _build(monkeypatch, inventory=inventory)
    assert result.mapped_selection_count == 1
    assert result.unreviewed_current_selection_count == 1
    assert result.all_15_target_markets_represented is False
    assert len(result.unrepresented_target_market_ids) == 14


def test_rebind_rechecks_freshness_at_its_own_evaluation_time(monkeypatch):
    inventory = _inventory(observed_at=EVALUATION - timedelta(seconds=901))
    bundle = _current_bundle(
        inventory,
        discovery_observed_at=EVALUATION - timedelta(seconds=901),
    )
    _install_sources(monkeypatch, inventory, current_bundle=bundle)
    with pytest.raises(
        rebind.CurrentDirectProviderCanonicalMappingRebindError,
        match="stale",
    ):
        rebind.rebind_current_direct_provider_canonical_mapping_as_of(
            current_reconciliation_bundle=bundle,
            target_event_id=CURRENT_EVENT,
            legacy_reconciliation_receipt_directory="legacy-receipt",
            legacy_reconciliation_source_bundle="legacy-source",
            legacy_review_decisions=(_decision(),),
            legacy_repository_root=Path("/tmp/legacy-repository"),
            evaluation_time=EVALUATION,
        )


def test_rebind_rejects_exact_120_second_kickoff_lead(monkeypatch):
    kickoff = EVALUATION + timedelta(seconds=120)
    inventory = _inventory(kickoff=kickoff)
    bundle = _current_bundle(inventory, kickoff=kickoff)
    _install_sources(monkeypatch, inventory, current_bundle=bundle)
    with pytest.raises(
        rebind.CurrentDirectProviderCanonicalMappingRebindError,
        match="too close to kickoff",
    ):
        rebind.rebind_current_direct_provider_canonical_mapping_as_of(
            current_reconciliation_bundle=bundle,
            target_event_id=CURRENT_EVENT,
            legacy_reconciliation_receipt_directory="legacy-receipt",
            legacy_reconciliation_source_bundle="legacy-source",
            legacy_review_decisions=(_decision(),),
            legacy_repository_root=Path("/tmp/legacy-repository"),
            evaluation_time=EVALUATION,
        )


def test_rebind_evaluation_cannot_predate_pr251_issuance(monkeypatch):
    inventory = _inventory()
    bundle = _current_bundle(inventory)
    _install_sources(monkeypatch, inventory, current_bundle=bundle)
    with pytest.raises(
        rebind.CurrentDirectProviderCanonicalMappingRebindError,
        match="cannot predate current reconciliation issuance",
    ):
        rebind.rebind_current_direct_provider_canonical_mapping_as_of(
            current_reconciliation_bundle=bundle,
            target_event_id=CURRENT_EVENT,
            legacy_reconciliation_receipt_directory="legacy-receipt",
            legacy_reconciliation_source_bundle="legacy-source",
            legacy_review_decisions=(_decision(),),
            legacy_repository_root=Path("/tmp/legacy-repository"),
            evaluation_time=bundle.evaluation_time - timedelta(seconds=1),
        )


def test_non_authorized_pr251_row_cannot_receive_mapping(monkeypatch):
    inventory = _inventory()
    bundle = _current_bundle(
        inventory,
        disposition=current.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH,
    )
    _install_sources(monkeypatch, inventory, current_bundle=bundle)
    with pytest.raises(
        rebind.CurrentDirectProviderCanonicalMappingRebindError,
        match="lacks exact current fixture-reconciliation authority",
    ):
        rebind.rebind_current_direct_provider_canonical_mapping_as_of(
            current_reconciliation_bundle=bundle,
            target_event_id=CURRENT_EVENT,
            legacy_reconciliation_receipt_directory="legacy-receipt",
            legacy_reconciliation_source_bundle="legacy-source",
            legacy_review_decisions=(_decision(),),
            legacy_repository_root=Path("/tmp/legacy-repository"),
            evaluation_time=EVALUATION,
        )


def test_pr251_inventory_provenance_mismatch_fails_closed(monkeypatch):
    inventory = _inventory()
    bundle = _current_bundle(inventory)
    bundle.rows[0].__dict__ if False else None
    bad_row = dataclasses.replace(
        bundle.rows[0],
        direct_event_raw_sha256="c" * 64,
    )
    bundle.rows = (bad_row,)
    _install_sources(monkeypatch, inventory, current_bundle=bundle)
    with pytest.raises(
        rebind.CurrentDirectProviderCanonicalMappingRebindError,
        match="provenance differs",
    ):
        rebind.rebind_current_direct_provider_canonical_mapping_as_of(
            current_reconciliation_bundle=bundle,
            target_event_id=CURRENT_EVENT,
            legacy_reconciliation_receipt_directory="legacy-receipt",
            legacy_reconciliation_source_bundle="legacy-source",
            legacy_review_decisions=(_decision(),),
            legacy_repository_root=Path("/tmp/legacy-repository"),
            evaluation_time=EVALUATION,
        )


def test_live_issuer_uses_wall_clock_and_marks_live_current(monkeypatch):
    inventory = _inventory()
    bundle, _source, _calls = _install_sources(monkeypatch, inventory)
    monkeypatch.setattr(rebind, "_now_utc", lambda: EVALUATION)
    result = rebind.rebind_current_direct_provider_canonical_mapping(
        current_reconciliation_bundle=bundle,
        target_event_id=CURRENT_EVENT,
        legacy_reconciliation_receipt_directory="legacy-receipt",
        legacy_reconciliation_source_bundle="legacy-source",
        legacy_review_decisions=(_decision(),),
        legacy_repository_root=Path("/tmp/legacy-repository"),
    )
    assert result.proof_mode == rebind.LIVE_CURRENT
    assert result.authority["wall_clock_currentness_at_issuance"] is True


def test_builder_only_outputs_and_tampering_fail_reconstruction(monkeypatch):
    result, _ = _build(monkeypatch)
    with pytest.raises(rebind.CurrentDirectProviderCanonicalMappingRebindError):
        rebind.CurrentDirectProviderCanonicalMarketMappingRebind()
    with pytest.raises(rebind.CurrentDirectProviderCanonicalMappingRebindError):
        rebind.CurrentDirectProviderCanonicalMappedSelection()
    with pytest.raises(rebind.CurrentDirectProviderCanonicalMappingRebindError):
        dataclasses.replace(result, fixture_id="tampered")

    original_sha = result.canonical_sha256
    assert original_sha == hashlib.sha256(rebind._canonical_bytes(result.to_dict())).hexdigest()
    object.__setattr__(result, "fixture_id", "tampered")
    with pytest.raises(
        rebind.CurrentDirectProviderCanonicalMappingRebindError,
        match="differs from exact retained-source reconstruction",
    ):
        rebind.verify_current_direct_provider_canonical_mapping_rebind(result)
