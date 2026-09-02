from __future__ import annotations
from datetime import datetime,timedelta,timezone
import pytest
from domain import current_all_market_shadow_probability_settlement as prc
from domain.markets import MarketId,OutcomeId
from domain._current_shadow_price_core import AH_PREDICTION_CONFIDENCE_METHOD, AH_SETTLEMENT_STATES, AUTHORITY_FLAGS, DNB_PREDICTION_CONFIDENCE_METHOD, DNB_SETTLEMENT_STATES, MINIMUM_DECIMAL_ODDS, MINIMUM_EVENT_PROBABILITY, MINIMUM_LEAD_SECONDS, MINIMUM_PREDICTION_CONFIDENCE, ROUTER_POLICY_ID, ShadowDevigStatus, ShadowOpportunityEligibility, ShadowPriceDisposition, ShadowPriceError, ShadowRouterDecisionStatus, settlement_unit_return
from domain._current_shadow_price_records import _issue_shadow_exact_quote, _issue_shadow_price_all_bundle, _issue_shadow_price_result
from domain._current_shadow_quote_binding import CurrentShadowPriceContext
from domain import current_shadow_all_market_price_all as price_all
from domain import current_shadow_all_market_router as router

NOW=datetime(2026,8,29,17,0,tzinfo=timezone.utc); KICKOFF=NOW+timedelta(hours=2); EVENT="sr:match:1001"; FIXTURE="FOTMOB:PRD1"
A="a"*64;B="b"*64;C="c"*64;D="d"*64;E="e"*64;F="f"*64

def _scan(home=2.8,away=.4):
    xg=prc.ResearchXGRates(calibrated_home=home,calibrated_away=away,sealed_prediction_sha256=A,history_prefix_identity=B,source_fixture_identity=FIXTURE)
    return prc.scan_fixture_all_markets(fixture_identity=FIXTURE,research_xg=xg,total_goals_lines=(1.5,2.5),asian_handicap_home_lines=(-.5,0.0),provider_semantic_by_market={m:"SUPPORTED" for m in MarketId})

def _context(scan=None):
    o=object.__new__(CurrentShadowPriceContext); scan=scan or _scan()
    fields={"fixture_identity":FIXTURE,"provider_event_id":EVENT,"evaluation_time":NOW,"scan":scan,"prc_scan_sha256":C,"provider_registry":None,"provider_registry_sha256":D,"provider_inventory":None,"source_raw_sha256":A,"source_manifest_sha256":B,"source_inventory_sha256":C,"fixture_reconciliation_sha256":D,"current_mapping_rebind_sha256":E,"bridge_bundle_sha256":F,"source_context_policy_id":"TEST","_bridge_bundle":None,"_event_evidence":None,"_complete_current_history":None}
    for k,v in fields.items(): object.__setattr__(o,k,v)
    return o

def _q(market,outcome,odds,*,line=None,mid="1",oid="1",specifier=None,kickoff=KICKOFF):
    return _issue_shadow_exact_quote(fixture_identity=FIXTURE,provider_event_id=EVENT,market_id=market,outcome_id=outcome,line=line,provider_line=None if line is None else str(line),provider_market_id=mid,provider_market_name=market.value,provider_specifier=specifier,provider_outcome_id=oid,provider_outcome_name=outcome.value,odds_raw=str(odds),decimal_odds=odds,observed_at=NOW,kickoff_utc=kickoff,source_raw_sha256=A,source_manifest_sha256=B,source_inventory_sha256=C,provider_semantic_status="SUPPORTED",provider_registry_sha256=D,provider_observation_sha256=E,fixture_reconciliation_sha256=D,current_mapping_rebind_sha256=E,bridge_bundle_sha256=F,bookable=True)

def _mr(): return (_q(MarketId.MATCH_RESULT,OutcomeId.HOME,1.45,oid="1"),_q(MarketId.MATCH_RESULT,OutcomeId.DRAW,5.0,oid="2"),_q(MarketId.MATCH_RESULT,OutcomeId.AWAY,10.0,oid="3"))
def _price(monkeypatch,quotes,scan=None):
    ctx=_context(scan); monkeypatch.setattr(price_all,"verify_current_shadow_price_context",lambda value:value); monkeypatch.setattr(price_all,"build_current_shadow_exact_quotes",lambda value:tuple(quotes)); return price_all.price_all_shadow_fixture(ctx)
def _route(monkeypatch,bundle): monkeypatch.setattr(router,"verify_shadow_price_all_bundle",lambda value:value); return router.route_shadow_price_results(bundle)

def test_price_all_preserves_all_15_markets_and_no_prefilter(monkeypatch):
    bundle=_price(monkeypatch,_mr()); assert {r.market_id for r in bundle.results}==set(MarketId); assert bundle.quote_count==3; assert bundle.authority["production_price_all"] is False

def test_complete_partition_devig_and_strongest_router_selection(monkeypatch):
    bundle=_price(monkeypatch,_mr()); home=next(r for r in bundle.results if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME)
    assert home.disposition is ShadowPriceDisposition.PRICED and home.devig_status is ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION and home.fair_probability is not None
    decision=_route(monkeypatch,bundle); assert decision.status is ShadowRouterDecisionStatus.SELECTED
    chosen=next(o for o in decision.opportunities if o.opportunity_id==decision.selected_opportunity_id); assert chosen.eligibility is ShadowOpportunityEligibility.ELIGIBLE and chosen.robust_net_expected_value>0

def test_incomplete_ordinary_partition_remains_audit_but_cannot_route(monkeypatch):
    bundle=_price(monkeypatch,(_mr()[0],)); home=next(r for r in bundle.results if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME)
    assert home.disposition is ShadowPriceDisposition.PRICED and home.devig_status is ShadowDevigStatus.INCOMPLETE_PARTITION
    decision=_route(monkeypatch,bundle); opp=next(o for o in decision.opportunities if o.opportunity_id==home.opportunity_id); assert opp.eligibility is ShadowOpportunityEligibility.ELIGIBLE and opp.value_first_eligibility is ShadowOpportunityEligibility.REJECTED

def test_overlapping_scalar_market_still_obeys_055_floor(monkeypatch):
    quote=_q(MarketId.DOUBLE_CHANCE,OutcomeId.DRAW_OR_AWAY,20.0,mid="10",oid="11")
    bundle=_price(monkeypatch,(quote,),_scan(3.0,.2)); row=next(r for r in bundle.results if r.market_id is MarketId.DOUBLE_CHANCE and r.outcome_id is OutcomeId.DRAW_OR_AWAY)
    assert row.devig_status is ShadowDevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS and row.model_probability<MINIMUM_EVENT_PROBABILITY and row.net_expected_value>0
    decision=_route(monkeypatch,bundle); opp=next(o for o in decision.opportunities if o.opportunity_id==row.opportunity_id); assert opp.eligibility is ShadowOpportunityEligibility.REJECTED and any("prediction confidence" in x for x in opp.rejection_reasons)

def test_dnb_is_full_settlement_ev_without_fake_scalar_or_fair_probability(monkeypatch):
    quotes=(_q(MarketId.DRAW_NO_BET,OutcomeId.HOME,1.5,mid="11",oid="4"),_q(MarketId.DRAW_NO_BET,OutcomeId.AWAY,4.0,mid="11",oid="5"))
    bundle=_price(monkeypatch,quotes,_scan(2.0,.7)); row=next(r for r in bundle.results if r.market_id is MarketId.DRAW_NO_BET and r.outcome_id is OutcomeId.HOME)
    assert row.disposition is ShadowPriceDisposition.PRICED and row.model_probability is None and row.fair_probability is None and row.devig_status is ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
    assert set(dict(row.settlement_state_probabilities))=={"WIN","PUSH","LOSS"}

def test_price_all_rechecks_minimum_kickoff_lead(monkeypatch):
    quote=_q(MarketId.MATCH_RESULT,OutcomeId.HOME,1.45,oid="1",kickoff=NOW+timedelta(seconds=MINIMUM_LEAD_SECONDS))
    bundle=_price(monkeypatch,(quote,)); row=next(r for r in bundle.results if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME)
    assert row.disposition is ShadowPriceDisposition.UNPRICED_TOO_CLOSE_TO_KICKOFF

def test_empty_quotes_terminal_no_bet_and_all_execution_authority_false(monkeypatch):
    bundle=_price(monkeypatch,()); decision=_route(monkeypatch,bundle); assert decision.status is ShadowRouterDecisionStatus.NO_BET and decision.selected_opportunity_id is None and decision.strongest_rejected_opportunity_id is not None
    for key in ("production_price_all","production_market_router","production_portfolio","production_selection","sportybet_execution","staking","bet","wager_placed"): assert AUTHORITY_FLAGS[key] is False and decision.authority[key] is False


def _router_result(
    market: MarketId,
    outcome: OutcomeId,
    *,
    token: str,
    confidence: float | None = 0.75,
    odds: float | None = 1.20,
    ev: float | None = 0.10,
    line: float | None = None,
    fair: float | None = 0.50,
    devig: ShadowDevigStatus | None = ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION,
    states: tuple[tuple[str, float], ...] | None = None,
    returns: tuple[tuple[str, float], ...] | None = None,
    disposition: ShadowPriceDisposition = ShadowPriceDisposition.PRICED,
    rejection_reason: str | None = None,
):
    if market is MarketId.DRAW_NO_BET:
        confidence = None
        fair = None
        states = states or (("WIN", 0.50), ("PUSH", 0.20), ("LOSS", 0.30))
    elif market is MarketId.ASIAN_HANDICAP:
        confidence = None
        fair = None
        line = 0.25 if line is None else line
        states = states or (
            ("WIN", 0.30), ("HALF_WIN", 0.15), ("PUSH", 0.10),
            ("HALF_LOSS", 0.15), ("LOSS", 0.30),
        )
    elif states is None and confidence is not None:
        states = (("WIN", confidence), ("LOSS", 1.0 - confidence))

    if returns is None and states is not None and odds is not None:
        returns = tuple((state, settlement_unit_return(state, odds)) for state, _ in states)

    priced = disposition is ShadowPriceDisposition.PRICED
    return _issue_shadow_price_result(
        fixture_identity=FIXTURE,
        market_id=market,
        outcome_id=outcome,
        line=line,
        disposition=disposition,
        model_probability=confidence,
        decimal_odds=odds if priced else None,
        implied_probability=None if odds is None or not priced else 1.0 / odds,
        fair_probability=fair if priced else None,
        overround=1.05 if priced and fair is not None else None,
        devig_status=devig if priced else None,
        net_expected_value=ev if priced else None,
        expected_return_multiplier=None if ev is None or not priced else 1.0 + ev,
        settlement_state_probabilities=() if states is None else states,
        settlement_unit_returns=() if returns is None else returns,
        quote_identity_sha256=(token * 64)[:64] if priced else None,
        provider_event_id=EVENT if priced else None,
        provider_semantic_status="SUPPORTED",
        rejection_reason=rejection_reason,
        probability_method="test_model_event_probability",
        probability_input_namespace="test.model",
        prc_scan_sha256=C,
        prc_assessment_sha256="a" * 64,
        sealed_prediction_sha256=A,
        history_prefix_identity=B,
        source_fixture_identity=FIXTURE,
        provider_registry_sha256=D,
        source_raw_sha256=A if priced else None,
        source_manifest_sha256=B if priced else None,
        source_inventory_sha256=C if priced else None,
        provider_observation_sha256=E if priced else None,
        fixture_reconciliation_sha256=D,
        current_mapping_rebind_sha256=E,
        bridge_bundle_sha256=F,
        score_matrix_audit=None,
        specialist_evidence=None,
    )


def _router_bundle(results):
    context = _context(_scan())
    return _issue_shadow_price_all_bundle(
        fixture_identity=FIXTURE,
        evaluation_time=NOW,
        prc_scan_sha256=C,
        provider_registry_sha256=D,
        fixture_reconciliation_sha256=D,
        current_mapping_rebind_sha256=E,
        bridge_bundle_sha256=F,
        quote_count=len(results),
        results=tuple(results),
        authority=AUTHORITY_FLAGS,
        _context=context,
    )


def _route_custom(monkeypatch, *results):
    bundle = _router_bundle(results)
    monkeypatch.setattr(router, "verify_shadow_price_all_bundle", lambda value: value)
    return bundle, router.route_shadow_price_results(bundle)


def test_prediction_first_selects_scalar_over_high_ev_low_confidence_ah(monkeypatch):
    ah = _router_result(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.HOME,
        token="1",
        odds=3.75,
        ev=0.90,
        states=(("WIN", 0.20), ("HALF_WIN", 0.10), ("PUSH", 0.027), ("HALF_LOSS", 0.10), ("LOSS", 0.573)),
    )
    scalar = _router_result(
        MarketId.MATCH_RESULT,
        OutcomeId.HOME,
        token="2",
        confidence=0.75,
        odds=1.20,
        ev=0.10,
        fair=0.50,
    )
    _bundle, decision = _route_custom(monkeypatch, ah, scalar)
    ah_row = next(item for item in decision.opportunities if item.price_result is ah)
    scalar_row = next(item for item in decision.opportunities if item.price_result is scalar)
    assert ah_row.prediction_confidence == pytest.approx(0.327)
    assert ah_row.prediction_confidence_method == AH_PREDICTION_CONFIDENCE_METHOD
    assert ah_row.eligibility is ShadowOpportunityEligibility.REJECTED
    assert ah_row.value_first_eligibility is ShadowOpportunityEligibility.ELIGIBLE
    assert decision.selected_opportunity_id == scalar_row.opportunity_id
    assert decision.value_first_selected_opportunity_id == ah_row.opportunity_id
    assert decision.router_policy_id == ROUTER_POLICY_ID
    assert decision.value_first_counterfactual_opportunity_id == ah_row.opportunity_id


def test_strong_ah_can_rank_first_without_family_penalty(monkeypatch):
    ah = _router_result(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.HOME,
        token="3",
        odds=1.50,
        ev=0.02,
        states=(("WIN", 0.55), ("HALF_WIN", 0.10), ("PUSH", 0.05), ("HALF_LOSS", 0.05), ("LOSS", 0.25)),
    )
    scalar = _router_result(
        MarketId.MATCH_RESULT,
        OutcomeId.AWAY,
        token="4",
        confidence=0.65,
        odds=1.20,
        ev=0.90,
        fair=0.50,
    )
    _bundle, decision = _route_custom(monkeypatch, ah, scalar)
    ah_row = next(item for item in decision.opportunities if item.price_result is ah)
    assert ah_row.prediction_confidence == pytest.approx(0.70)
    assert ah_row.eligibility is ShadowOpportunityEligibility.ELIGIBLE
    assert decision.selected_opportunity_id == ah_row.opportunity_id


def test_dnb_confidence_is_win_plus_push(monkeypatch):
    dnb = _router_result(
        MarketId.DRAW_NO_BET,
        OutcomeId.HOME,
        token="5",
        odds=1.50,
        ev=0.01,
        states=(("WIN", 0.50), ("PUSH", 0.20), ("LOSS", 0.30)),
    )
    _bundle, decision = _route_custom(monkeypatch, dnb)
    row = decision.opportunities[0]
    assert row.prediction_confidence == pytest.approx(0.70)
    assert row.prediction_confidence_method == DNB_PREDICTION_CONFIDENCE_METHOD
    assert row.eligibility is ShadowOpportunityEligibility.ELIGIBLE


def test_ah_confidence_counts_win_half_win_push_only(monkeypatch):
    ah = _router_result(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.AWAY,
        token="6",
        odds=1.50,
        ev=0.01,
        states=(("WIN", 0.30), ("HALF_WIN", 0.15), ("PUSH", 0.10), ("HALF_LOSS", 0.15), ("LOSS", 0.30)),
    )
    _bundle, decision = _route_custom(monkeypatch, ah)
    row = decision.opportunities[0]
    assert row.prediction_confidence == pytest.approx(0.55)
    assert row.prediction_confidence_method == AH_PREDICTION_CONFIDENCE_METHOD
    assert row.eligibility is ShadowOpportunityEligibility.ELIGIBLE


@pytest.mark.parametrize(
    "market,states",
    (
        (MarketId.DRAW_NO_BET, (("WIN", 0.30), ("PUSH", 0.24), ("LOSS", 0.46))),
        (MarketId.ASIAN_HANDICAP, (("WIN", 0.25), ("HALF_WIN", 0.10), ("PUSH", 0.19), ("HALF_LOSS", 0.10), ("LOSS", 0.36))),
    ),
)
def test_push_split_markets_share_prediction_confidence_floor(market, states, monkeypatch):
    outcome = OutcomeId.HOME
    _bundle, decision = _route_custom(
        monkeypatch,
        _router_result(market, outcome, token="7", states=states, odds=1.20),
    )
    row = decision.opportunities[0]
    assert row.prediction_confidence == pytest.approx(0.54)
    assert row.eligibility is ShadowOpportunityEligibility.REJECTED
    assert any("prediction confidence" in reason for reason in row.rejection_reasons)


@pytest.mark.parametrize("confidence,expected", ((MINIMUM_PREDICTION_CONFIDENCE, ShadowOpportunityEligibility.ELIGIBLE), (MINIMUM_PREDICTION_CONFIDENCE - 1e-9, ShadowOpportunityEligibility.REJECTED)))
def test_common_prediction_confidence_floor(confidence, expected, monkeypatch):
    _bundle, decision = _route_custom(
        monkeypatch,
        _router_result(MarketId.BTTS, OutcomeId.YES, token="7", confidence=confidence, odds=1.20),
    )
    assert decision.opportunities[0].eligibility is expected


@pytest.mark.parametrize("odds,expected", ((MINIMUM_DECIMAL_ODDS, ShadowOpportunityEligibility.ELIGIBLE), (MINIMUM_DECIMAL_ODDS - 1e-9, ShadowOpportunityEligibility.REJECTED)))
def test_exact_decimal_odds_floor(odds, expected, monkeypatch):
    _bundle, decision = _route_custom(
        monkeypatch,
        _router_result(MarketId.BTTS, OutcomeId.YES, token="8", confidence=0.80, odds=odds),
    )
    assert decision.opportunities[0].eligibility is expected


def test_high_confidence_below_odds_floor_falls_through(monkeypatch):
    blocked = _router_result(MarketId.MATCH_RESULT, OutcomeId.HOME, token="9", confidence=0.90, odds=1.08, ev=0.90)
    fallback = _router_result(MarketId.MATCH_RESULT, OutcomeId.AWAY, token="a", confidence=0.60, odds=1.20, ev=0.01)
    _bundle, decision = _route_custom(monkeypatch, blocked, fallback)
    assert decision.selected_opportunity_id == fallback.opportunity_id
    assert next(item for item in decision.opportunities if item.price_result is blocked).prediction_first_rank is None


def test_prediction_rank_is_deterministic_and_invariant_to_ev(monkeypatch):
    first = _router_result(MarketId.BTTS, OutcomeId.YES, token="b", confidence=0.70, odds=1.20, ev=0.90)
    second = _router_result(MarketId.BTTS, OutcomeId.NO, token="c", confidence=0.70, odds=1.20, ev=0.10)
    _bundle, first_decision = _route_custom(monkeypatch, first, second)
    changed_first = _router_result(MarketId.BTTS, OutcomeId.YES, token="b", confidence=0.70, odds=1.20, ev=0.10)
    changed_second = _router_result(MarketId.BTTS, OutcomeId.NO, token="c", confidence=0.70, odds=1.20, ev=0.90)
    _bundle, second_decision = _route_custom(monkeypatch, changed_first, changed_second)
    expected = min(first.opportunity_id, second.opportunity_id)
    assert first_decision.selected_opportunity_id == expected
    assert second_decision.selected_opportunity_id == expected


def test_incomplete_or_malformed_settlement_is_not_prediction_comparable(monkeypatch):
    missing_state = _router_result(
        MarketId.DRAW_NO_BET,
        OutcomeId.HOME,
        token="d",
        states=(("WIN", 0.70), ("PUSH", 0.30)),
    )
    malformed_name = _router_result(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.HOME,
        token="e",
        states=(("WIN", 0.30), ("HALF_WIN", 0.15), ("PUSHED", 0.10), ("HALF_LOSS", 0.15), ("LOSS", 0.30)),
        returns=(("WIN", 0.5), ("HALF_WIN", 0.25), ("PUSHED", 0.0), ("HALF_LOSS", -0.5), ("LOSS", -1.0)),
    )
    _bundle, decision = _route_custom(monkeypatch, missing_state, malformed_name)
    assert all(item.eligibility is ShadowOpportunityEligibility.REJECTED for item in decision.opportunities)
    assert all(item.prediction_confidence is None for item in decision.opportunities)
    with pytest.raises(ShadowPriceError, match="settlement mass"):
        _router_result(
            MarketId.ASIAN_HANDICAP,
            OutcomeId.HOME,
            token="f",
            states=(("WIN", 0.30), ("HALF_WIN", 0.15), ("PUSH", 0.10), ("HALF_LOSS", 0.15), ("LOSS", 0.20)),
        )


def test_missing_scalar_probability_and_unpriced_quote_fail_closed(monkeypatch):
    missing_probability = _router_result(MarketId.BTTS, OutcomeId.YES, token="1", confidence=None)
    unpriced = _router_result(
        MarketId.BTTS,
        OutcomeId.NO,
        token="2",
        confidence=0.90,
        disposition=ShadowPriceDisposition.UNPRICED_NO_EXACT_QUOTE,
        rejection_reason="no exact current quote",
    )
    missing_odds = _router_result(MarketId.MATCH_RESULT, OutcomeId.HOME, token="3", confidence=0.90)
    object.__setattr__(missing_odds, "decimal_odds", None)
    _bundle, decision = _route_custom(monkeypatch, missing_probability, unpriced, missing_odds)
    assert all(item.eligibility is ShadowOpportunityEligibility.REJECTED for item in decision.opportunities)
    assert any("decimal odds" in reason for reason in decision.opportunities[-1].rejection_reasons)


def test_router_serializes_prediction_and_value_counterfactuals_and_rejects_tampering(monkeypatch):
    low_value = _router_result(MarketId.BTTS, OutcomeId.YES, token="3", confidence=0.60, odds=1.20, ev=0.10)
    high_prediction = _router_result(MarketId.BTTS, OutcomeId.NO, token="4", confidence=0.80, odds=1.20, ev=0.01)
    bundle, decision = _route_custom(monkeypatch, low_value, high_prediction)
    payload = decision.to_dict()
    assert payload["router_policy_id"] == ROUTER_POLICY_ID
    assert payload["value_first_policy_id"] != ROUTER_POLICY_ID
    assert payload["value_first_selected_opportunity_id"] == low_value.opportunity_id
    assert all("prediction_confidence" in item for item in payload["opportunities"])
    assert all("value_first_eligibility" in item for item in payload["opportunities"])

    object.__setattr__(decision.opportunities[0], "prediction_confidence", 0.99)
    with pytest.raises(ShadowPriceError, match="exact source reconstruction"):
        router.verify_shadow_router_decision(bundle, decision)

    _bundle, clean = _route_custom(monkeypatch, low_value, high_prediction)
    object.__setattr__(clean, "router_policy_id", "SHADOW_CONSERVATIVE_FROZEN_THRESHOLDS_V1")
    with pytest.raises(ShadowPriceError, match="exact source reconstruction"):
        router.verify_shadow_router_decision(bundle, clean)


def test_router_verifies_price_all_before_selection(monkeypatch):
    bundle = _router_bundle((_router_result(MarketId.BTTS, OutcomeId.YES, token="5"),))
    calls = []

    def verify(value):
        calls.append(value)
        return value

    monkeypatch.setattr(router, "verify_shadow_price_all_bundle", verify)
    router.route_shadow_price_results(bundle)
    assert calls == [bundle]
