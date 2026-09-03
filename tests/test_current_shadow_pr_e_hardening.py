from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_share_code as share
from domain._current_shadow_price_core import AUTHORITY_FLAGS, ShadowPriceDisposition
from domain._current_shadow_price_records import (
    _issue_shadow_exact_quote,
    _issue_shadow_price_all_bundle,
    _issue_shadow_price_result,
)
from domain._current_shadow_quote_binding import CurrentShadowPriceContext
from domain.markets import MarketId, OutcomeId

NOW = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
FIXTURE = "FOTMOB:1"
EVENT = "sr:match:1"


def _leg(*, specifier=None):
    return SimpleNamespace(
        fixture_identity=FIXTURE,
        provider_event_id=EVENT,
        home_team="Home",
        away_team="Away",
        provider_market_id="1",
        provider_market_name="1X2",
        provider_specifier=specifier,
        provider_outcome_id="1",
        provider_outcome_name="Home",
        decimal_odds=2.0,
    )


def _semantic_receipt(leg):
    return {
        "caller_supplied_market_outcome_ids_accepted": False,
        "resolved": [{
            "eventId": leg.provider_event_id,
            "observed_home_team": leg.home_team,
            "observed_away_team": leg.away_team,
            "observed_market_name": leg.provider_market_name,
            "observed_outcome_name": leg.provider_outcome_name,
            "observed_specifier": leg.provider_specifier,
            "marketId": leg.provider_market_id,
            "outcomeId": leg.provider_outcome_id,
            "odds": str(leg.decimal_odds),
        }],
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }


def _direct_quote(*, mapping=None, bridge=None):
    return _issue_shadow_exact_quote(
        fixture_identity=FIXTURE,
        provider_event_id=EVENT,
        market_id=MarketId.MATCH_RESULT,
        outcome_id=OutcomeId.HOME,
        line=None,
        provider_line=None,
        provider_market_id="1",
        provider_market_name="1X2",
        provider_specifier=None,
        provider_outcome_id="1",
        provider_outcome_name="Home",
        odds_raw="2.0",
        decimal_odds=2.0,
        observed_at=NOW,
        kickoff_utc=datetime(2026, 8, 29, 23, 0, tzinfo=timezone.utc),
        source_raw_sha256=A,
        source_manifest_sha256=B,
        source_inventory_sha256=C,
        provider_semantic_status="SUPPORTED",
        provider_registry_sha256=D,
        provider_observation_sha256=E,
        fixture_reconciliation_sha256=D,
        current_mapping_rebind_sha256=mapping,
        bridge_bundle_sha256=bridge,
        bookable=True,
    )


def test_direct_current_records_allow_legacy_only_provenance_to_be_absent_as_pair():
    quote = _direct_quote()
    assert quote.current_mapping_rebind_sha256 is None
    assert quote.bridge_bundle_sha256 is None

    result = _issue_shadow_price_result(
        fixture_identity=FIXTURE,
        market_id=MarketId.MATCH_RESULT,
        outcome_id=OutcomeId.HOME,
        line=None,
        disposition=ShadowPriceDisposition.UNPRICED_NO_EXACT_QUOTE,
        model_probability=None,
        decimal_odds=None,
        implied_probability=None,
        fair_probability=None,
        overround=None,
        devig_status=None,
        net_expected_value=None,
        expected_return_multiplier=None,
        settlement_state_probabilities=(),
        settlement_unit_returns=(),
        quote_identity_sha256=None,
        provider_event_id=None,
        provider_semantic_status="SUPPORTED",
        rejection_reason="test",
        probability_method=None,
        probability_input_namespace=None,
        prc_scan_sha256=A,
        prc_assessment_sha256=B,
        sealed_prediction_sha256=None,
        history_prefix_identity=None,
        source_fixture_identity=None,
        provider_registry_sha256=C,
        source_raw_sha256=None,
        source_manifest_sha256=None,
        source_inventory_sha256=None,
        provider_observation_sha256=None,
        fixture_reconciliation_sha256=D,
        current_mapping_rebind_sha256=None,
        bridge_bundle_sha256=None,
        score_matrix_audit=None,
        specialist_evidence=None,
    )
    context = object.__new__(CurrentShadowPriceContext)
    bundle = _issue_shadow_price_all_bundle(
        fixture_identity=FIXTURE,
        evaluation_time=NOW,
        prc_scan_sha256=A,
        provider_registry_sha256=C,
        fixture_reconciliation_sha256=D,
        current_mapping_rebind_sha256=None,
        bridge_bundle_sha256=None,
        quote_count=0,
        results=(result,),
        authority=AUTHORITY_FLAGS,
        _context=context,
    )
    assert bundle.current_mapping_rebind_sha256 is None
    assert bundle.bridge_bundle_sha256 is None


def test_legacy_mapping_and_bridge_provenance_must_be_present_or_absent_together():
    with pytest.raises(Exception, match="present or absent together"):
        _direct_quote(mapping=E, bridge=None)


def test_no_specifier_semantic_selection_matches_transport_shape():
    leg = _leg(specifier=None)
    portfolio = SimpleNamespace(selected_legs=(leg,))
    selection = {
        "eventId": leg.provider_event_id,
        "marketId": leg.provider_market_id,
        "outcomeId": leg.provider_outcome_id,
    }
    assert share._verify_semantic(portfolio, (selection,), _semantic_receipt(leg)) == ()


@pytest.mark.parametrize("missing", ["market", "outcome"])
def test_accepted_provider_rows_missing_native_ids_fail_closed(missing):
    market = {
        "id": "1",
        "desc": "1X2",
        "outcomes": [{"id": "1", "desc": "Home", "odds": "2.0"}],
    }
    if missing == "market":
        market.pop("id")
    else:
        market["outcomes"][0].pop("id")
    event = {
        "eventId": EVENT,
        "homeTeamName": "Home",
        "awayTeamName": "Away",
        "markets": [market],
    }
    with pytest.raises(
        share.CurrentShadowAllMarketShareCodeError,
        match="provider-native identity is missing",
    ):
        share._accepted_row(event, "test")


def test_verified_receipt_cannot_claim_wrong_shortfall_arithmetic():
    with pytest.raises(
        share.CurrentShadowAllMarketShareCodeError,
        match="selected leg count and shortfall do not match target",
    ):
        share.ShadowAllMarketShareCodeReceipt(
            status=share.STATUS_CODE_VERIFIED,
            observed_at=NOW,
            portfolio_sha256=A,
            requested_target_size=2,
            portfolio_shortfall=0,
            selected_leg_count=1,
            reasons=(),
            semantic_resolution_receipt_sha256=B,
            transport_receipt_sha256=C,
            share_code="ABC123",
            share_url="https://example.test/ABC123",
            combined_odds="2.0",
        )


def test_verified_receipt_requires_exact_create_reload_equality():
    with pytest.raises(
        share.CurrentShadowAllMarketShareCodeError,
        match="exact create/reload equality",
    ):
        share.ShadowAllMarketShareCodeReceipt(
            status=share.STATUS_CODE_VERIFIED,
            observed_at=NOW,
            portfolio_sha256=A,
            requested_target_size=1,
            portfolio_shortfall=0,
            selected_leg_count=1,
            reasons=(),
            semantic_resolution_receipt_sha256=B,
            transport_receipt_sha256=C,
            share_code="ABC123",
            share_url="https://example.test/ABC123",
            combined_odds="2.0",
            exact_create_reload_equality=False,
        )
