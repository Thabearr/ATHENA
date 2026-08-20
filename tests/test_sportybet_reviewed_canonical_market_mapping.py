from __future__ import annotations

import dataclasses
import hashlib
from types import SimpleNamespace

import pytest

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_reviewed_canonical_market_mapping as mapping
from domain.sportybet_early_payout_settlement import (
    canonical_sportybet_early_payout_settlement_receipt_bytes,
    reviewed_sportybet_early_payout_settlement_receipt,
    sha256_sportybet_early_payout_settlement_receipt,
)
from domain import sportybet_user_controlled_native_inventory as native
from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId
from domain.sportybet_provider_native_inventory import NativeAvailability, NativeSelection

EVENT = "sr:match:123"
SPORT = "sr:sport:1"
INV_SHA = "1" * 64
EVIDENCE = "a" * 24


def _selection(*, market="18", name="Total Goals", spec="total=2.5", outcome="O", label="Over 2.5"):
    href = f"/ng/lite/preMatch/detail?eventId={EVENT}&marketId={market}&outcomeId={outcome}&odds=1.90&productId=3&sportId={SPORT}&marketGroupsName=Main"
    if spec is not None:
        href += f"&specifier={spec}"
    return NativeSelection(
        event_id=EVENT, sport_id=SPORT, product_id="3", market_id=market,
        market_group="Main", market_name=name, specifier=spec, outcome_id=outcome,
        selection_label=label, odds_raw="1.90", odds_decimal="1.9",
        availability=NativeAvailability.AVAILABLE, provider_quote_at=None,
        provider_snapshot_id=None, href=href,
    )


def _inventory(*rows):
    value = object.__new__(native.SportyBetUserControlledNativeInventory)
    object.__setattr__(value, "source_event_id", EVENT)
    object.__setattr__(value, "source_sport_id", SPORT)
    object.__setattr__(value, "source_evidence_id", EVIDENCE)
    object.__setattr__(value, "provider_quote_at", None)
    object.__setattr__(value, "provider_snapshot_id", None)
    object.__setattr__(value, "selections", tuple(rows))
    return value


def _reconciled(*, disposition=None, inventory_sha=INV_SHA):
    return SimpleNamespace(
        disposition=disposition or reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED,
        fixture_reconciliation_authorized=True,
        matched_fixture=SimpleNamespace(source_fixture_identifier="987654"),
        source_native_inventory_sha256=inventory_sha,
        sportybet_event_id=EVENT,
        sportybet_sport_id=SPORT,
        source_event_evidence_id=EVIDENCE,
    )


def _decision(row, *, market=MarketId.TOTAL_GOALS, outcome=OutcomeId.OVER, line=2.5):
    return mapping.ReviewedCanonicalMappingDecision(
        event_id=row.event_id, provider_market_id=row.market_id,
        provider_market_name=row.market_name or "missing", provider_specifier=row.specifier,
        provider_outcome_id=row.outcome_id, provider_selection_label=row.selection_label or "missing",
        canonical_market_id=market, canonical_outcome_id=outcome, canonical_line=line,
    )


def _build(monkeypatch, row, decision):
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(mapping.reconciliation, "canonical_reconciliation_bytes", lambda value: b"reconciliation\n")
    return mapping._build(_reconciled(), _inventory(row), (decision,))


def test_registry_is_exact_full_15_market_scope():
    mapping._assert_target_registry()
    assert len(mapping.TARGET_MARKET_IDS) == 15
    assert set(mapping.TARGET_MARKET_IDS) == set(MARKET_REGISTRY)


def test_canonical_registry_rejects_wrong_outcome_or_line():
    row = _selection()
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError):
        _decision(row, market=MarketId.TOTAL_GOALS, outcome=OutcomeId.HOME, line=2.5)
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError):
        _decision(row, market=MarketId.MATCH_RESULT, outcome=OutcomeId.HOME, line=2.5)


def test_total_goals_and_asian_handicap_bind_exact_specifier(monkeypatch):
    row = _selection()
    result = _build(monkeypatch, row, _decision(row))
    assert result.mapped_selections[0].canonical_line == 2.5
    assert result.mapped_selections[0].fresh_price_authorized is False
    bad = _selection(spec="total=3.5")
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="does not equal"):
        _build(monkeypatch, bad, _decision(bad, line=2.5))

    ah = _selection(market="16", name="Asian Handicap", spec="hcp=-2.5", outcome="H", label="Home -2.5")
    result = _build(monkeypatch, ah, _decision(ah, market=MarketId.ASIAN_HANDICAP, outcome=OutcomeId.HOME, line=-2.5))
    assert result.mapped_selections[0].canonical_line == -2.5
    wrong = _selection(market="16", name="Asian Handicap", spec="total=-2.5", outcome="H", label="Home -2.5")
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="does not prove"):
        _build(monkeypatch, wrong, _decision(wrong, market=MarketId.ASIAN_HANDICAP, outcome=OutcomeId.HOME, line=-2.5))


def test_non_line_market_cannot_hide_provider_specifier(monkeypatch):
    row = _selection(market="1", name="Match Result", outcome="1", label="Home")
    decision = _decision(row, market=MarketId.MATCH_RESULT, outcome=OutcomeId.HOME, line=None)
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="cannot be absorbed"):
        _build(monkeypatch, row, decision)


def test_exact_source_labels_and_native_identity_are_mandatory(monkeypatch):
    row = _selection()
    bad_label = dataclasses.replace(_decision(row), provider_market_name="Different")
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="labels do not exactly match"):
        _build(monkeypatch, row, bad_label)
    bad_identity = dataclasses.replace(_decision(row), provider_outcome_id="OTHER")
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="does not match an exact"):
        _build(monkeypatch, row, bad_identity)


def test_duplicate_native_and_canonical_review_identity_fail_closed():
    row = _selection()
    d1 = _decision(row)
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="duplicate provider-native"):
        mapping.canonical_review_decisions_bytes((d1, d1))
    row2 = _selection(market="19", name="Other", outcome="U", label="Under")
    d2 = _decision(row2)
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="same canonical"):
        mapping.canonical_review_decisions_bytes((d1, d2))


def test_reconciled_inventory_hash_and_unique_fixture_are_required(monkeypatch):
    row = _selection()
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="does not bind"):
        mapping._build(_reconciled(inventory_sha="2" * 64), _inventory(row), (_decision(row),))
    for disposition in (
        reconciliation.FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH,
        reconciliation.FullUtcReconciliationDisposition.AMBIGUOUS_EXACT_FULL_UTC_MATCH,
    ):
        with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError, match="unique full-UTC"):
            mapping._build(_reconciled(disposition=disposition), _inventory(row), (_decision(row),))


def test_1up_maps_identifier_without_claiming_promotion_equivalence(monkeypatch):
    row = _selection(market="1up", name="Match Result 1UP", spec=None, outcome="1", label="Home")
    decision = _decision(row, market=MarketId.MATCH_RESULT_1UP, outcome=OutcomeId.HOME, line=None)
    result = _build(monkeypatch, row, decision)
    mapped = result.mapped_selections[0]
    assert mapped.canonical_market_mapping_authorized is True
    assert mapped.bookmaker_equivalence_authorized is False
    assert mapped.settlement_equivalence_authority is mapping.SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
    assert result.safety["fresh_price_authorized"] is False
    assert result.safety["selection_authorized"] is False
    assert result.safety["bet_authorized"] is False


def test_1up_exact_settlement_receipt_upgrades_only_bookmaker_equivalence(monkeypatch):
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(mapping.reconciliation, "canonical_reconciliation_bytes", lambda value: b"reconciliation\n")
    row = _selection(market="60200", name="Match Result 1UP", spec=None, outcome="1", label="Home")
    decision = _decision(row, market=MarketId.MATCH_RESULT_1UP, outcome=OutcomeId.HOME, line=None)
    receipt = reviewed_sportybet_early_payout_settlement_receipt()
    result = mapping._build(
        _reconciled(),
        _inventory(row),
        (decision,),
        early_payout_settlement_receipt=receipt,
        early_payout_settlement_receipt_bytes=(
            canonical_sportybet_early_payout_settlement_receipt_bytes(receipt)
        ),
    )
    mapped = result.mapped_selections[0]

    assert mapped.settlement_equivalence_authority is (
        mapping.SettlementEquivalenceAuthority.REVIEWED_SPORTYBET_EARLY_PAYOUT_SETTLEMENT_EQUIVALENCE
    )
    assert mapped.settlement_evidence_sha256 == (
        sha256_sportybet_early_payout_settlement_receipt(receipt)
    )
    assert mapped.bookmaker_equivalence_authorized is True
    assert mapped.fresh_price_authorized is False
    assert result.safety["pricing_authorized"] is False
    assert result.safety["selection_authorized"] is False
    assert result.safety["bet_authorized"] is False
    with pytest.raises(
        mapping.SportyBetReviewedCanonicalMarketMappingError,
        match="exact reviewed provider mapped market identity",
    ):
        dataclasses.replace(mapped, provider_market_id="99999")


def test_early_payout_mapping_rejects_wrong_receipt_bytes(monkeypatch):
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(mapping.reconciliation, "canonical_reconciliation_bytes", lambda value: b"reconciliation\n")
    row = _selection(market="60100", name="Match Result 2UP", spec=None, outcome="2", label="Away")
    decision = _decision(row, market=MarketId.MATCH_RESULT_2UP, outcome=OutcomeId.AWAY, line=None)
    receipt = reviewed_sportybet_early_payout_settlement_receipt()
    with pytest.raises(mapping.SportyBetReviewedCanonicalMarketMappingError):
        mapping._build(
            _reconciled(),
            _inventory(row),
            (decision,),
            early_payout_settlement_receipt=receipt,
            early_payout_settlement_receipt_bytes=(
                canonical_sportybet_early_payout_settlement_receipt_bytes(receipt)
                + b"\n"
            ),
        )


@pytest.mark.parametrize(
    "canonical_market,provider_market_id",
    (
        (MarketId.MATCH_RESULT_1UP, "1up"),
        (MarketId.MATCH_RESULT_1UP, "60100"),
        (MarketId.MATCH_RESULT_2UP, "2up"),
        (MarketId.MATCH_RESULT_2UP, "60200"),
        (MarketId.MATCH_RESULT_2UP, "99999"),
    ),
)
def test_valid_receipt_cannot_upgrade_wrong_provider_market_identity(
    monkeypatch, canonical_market, provider_market_id
):
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(mapping.reconciliation, "canonical_reconciliation_bytes", lambda value: b"reconciliation\n")
    row = _selection(
        market=provider_market_id,
        name="Match Result early payout",
        spec=None,
        outcome="1",
        label="Home",
    )
    decision = _decision(
        row,
        market=canonical_market,
        outcome=OutcomeId.HOME,
        line=None,
    )
    receipt = reviewed_sportybet_early_payout_settlement_receipt()
    with pytest.raises(
        mapping.SportyBetReviewedCanonicalMarketMappingError,
        match="exact provider mapped market identity",
    ):
        mapping._build(
            _reconciled(),
            _inventory(row),
            (decision,),
            early_payout_settlement_receipt=receipt,
            early_payout_settlement_receipt_bytes=(
                canonical_sportybet_early_payout_settlement_receipt_bytes(receipt)
            ),
        )


def test_representation_report_does_not_invent_15_market_coverage(monkeypatch):
    row = _selection()
    result = _build(monkeypatch, row, _decision(row))
    assert result.represented_target_market_ids == (MarketId.TOTAL_GOALS,)
    assert len(result.unrepresented_target_market_ids) == 14
    assert result.all_15_target_markets_represented is False


def test_public_builder_calls_source_aware_receipt_verifier(monkeypatch, tmp_path):
    row = _selection()
    inv = _inventory(row)
    bundle = SimpleNamespace(event_inventory=inv)
    calls = []
    def verify(directory, *, source_bundle, repository_root):
        calls.append((directory, source_bundle, repository_root))
        return _reconciled()
    monkeypatch.setattr(mapping.receipts, "verify_reconciliation_receipt_directory", verify)
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(mapping.reconciliation, "canonical_reconciliation_bytes", lambda value: b"reconciliation\n")
    result = mapping.build_reviewed_canonical_market_mapping(
        reconciliation_receipt_directory="receipt", reconciliation_source_bundle=bundle,
        review_decisions=(_decision(row),), repository_root=tmp_path,
    )
    assert calls == [("receipt", bundle, tmp_path)]
    assert result.sportybet_event_id == EVENT


def test_canonical_output_is_deterministic(monkeypatch):
    row = _selection()
    result = _build(monkeypatch, row, _decision(row))
    payload = mapping.canonical_mapping_bytes(result)
    assert payload.endswith(b"\n")
    assert mapping.canonical_mapping_sha256(result) == hashlib.sha256(payload).hexdigest()
