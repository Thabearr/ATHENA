from __future__ import annotations
from datetime import datetime,timedelta,timezone
import pytest
from domain import current_all_market_shadow_probability_settlement as prc
from domain.markets import MarketId,OutcomeId
from domain._current_shadow_price_core import AUTHORITY_FLAGS,MINIMUM_EVENT_PROBABILITY,MINIMUM_LEAD_SECONDS,ShadowDevigStatus,ShadowOpportunityEligibility,ShadowPriceDisposition,ShadowRouterDecisionStatus
from domain._current_shadow_price_records import _issue_shadow_exact_quote
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
    decision=_route(monkeypatch,bundle); opp=next(o for o in decision.opportunities if o.opportunity_id==home.opportunity_id); assert opp.eligibility is ShadowOpportunityEligibility.REJECTED

def test_overlapping_scalar_market_still_obeys_055_floor(monkeypatch):
    quote=_q(MarketId.DOUBLE_CHANCE,OutcomeId.DRAW_OR_AWAY,20.0,mid="10",oid="11")
    bundle=_price(monkeypatch,(quote,),_scan(3.0,.2)); row=next(r for r in bundle.results if r.market_id is MarketId.DOUBLE_CHANCE and r.outcome_id is OutcomeId.DRAW_OR_AWAY)
    assert row.devig_status is ShadowDevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS and row.model_probability<MINIMUM_EVENT_PROBABILITY and row.net_expected_value>0
    decision=_route(monkeypatch,bundle); opp=next(o for o in decision.opportunities if o.opportunity_id==row.opportunity_id); assert opp.eligibility is ShadowOpportunityEligibility.REJECTED and any("event probability floor" in x for x in opp.rejection_reasons)

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