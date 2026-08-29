"""Internal exact-line pricing helpers for PR D."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Sequence
import math
from domain import current_sportybet_semantic_registry as prb
from domain.markets import MarketId, OutcomeId
from domain._all_market_shadow_types import ShadowDisposition, ShadowMarketAssessment
from domain._current_shadow_price_core import (
    MAX_QUOTE_AGE_SECONDS, MINIMUM_LEAD_SECONDS, ORDINARY_PARTITIONS, OVERLAPPING_MARKETS,
    PUSH_SPLIT_MARKETS, ShadowDevigStatus, ShadowPriceDisposition, ShadowPriceError,
    _sha256, settlement_unit_return,
)
from domain._current_shadow_price_records import ShadowExactQuote, ShadowPriceResult, _issue_shadow_price_result
from domain._current_shadow_quote_binding import CurrentShadowPriceContext

_SUPPORTED=frozenset({prb.ProviderSemanticStatus.SUPPORTED.value,prb.ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY.value})

def _utc(v:datetime):
    if type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None: raise ShadowPriceError("evaluation_time must be timezone-aware")
    return v.astimezone(timezone.utc)

def _blocked(status:Optional[str]): return status not in _SUPPORTED

def _ancestry(ctx:CurrentShadowPriceContext,a:ShadowMarketAssessment):
    xg=ctx.scan.research_xg
    return {"probability_method":a.probability_method,"probability_input_namespace":a.probability_input_namespace,
        "prc_scan_sha256":ctx.prc_scan_sha256,"prc_assessment_sha256":_sha256(a.to_dict()),
        "sealed_prediction_sha256":None if xg is None else xg.sealed_prediction_sha256,
        "history_prefix_identity":None if xg is None else xg.history_prefix_identity,
        "source_fixture_identity":None if xg is None else xg.source_fixture_identity,
        "provider_registry_sha256":ctx.provider_registry_sha256,"fixture_reconciliation_sha256":ctx.fixture_reconciliation_sha256,
        "current_mapping_rebind_sha256":ctx.current_mapping_rebind_sha256,"bridge_bundle_sha256":ctx.bridge_bundle_sha256,
        "score_matrix_audit":a.score_matrix_audit,"specialist_evidence":a.specialist_evidence}

def _empty_result(*,context:CurrentShadowPriceContext,assessment:ShadowMarketAssessment,outcome_id:OutcomeId,line:Optional[float],
        disposition:ShadowPriceDisposition,reason:str,model_probability:Optional[float]):
    return _issue_shadow_price_result(fixture_identity=context.fixture_identity,market_id=assessment.market_id,outcome_id=outcome_id,
        line=line,disposition=disposition,model_probability=model_probability,decimal_odds=None,implied_probability=None,
        fair_probability=None,overround=None,devig_status=None,net_expected_value=None,expected_return_multiplier=None,
        settlement_state_probabilities=(),settlement_unit_returns=(),quote_identity_sha256=None,provider_event_id=None,
        provider_semantic_status=assessment.provider_semantic_status,rejection_reason=reason,source_raw_sha256=None,
        source_manifest_sha256=None,source_inventory_sha256=None,provider_observation_sha256=None,**_ancestry(context,assessment))

def _match(quotes:Sequence[ShadowExactQuote],fixture:str,market:MarketId,outcome:OutcomeId,line:Optional[float]):
    rows=tuple(q for q in quotes if q.fixture_identity==fixture and q.market_id is market and q.outcome_id is outcome and q.line==line)
    if not rows: return None,ShadowPriceDisposition.UNPRICED_NO_EXACT_QUOTE,"no exact current quote"
    if len(rows)!=1: return None,ShadowPriceDisposition.UNPRICED_AMBIGUOUS_QUOTE,"duplicate exact current quotes"
    return rows[0],None,None

def _partition(quotes:Sequence[ShadowExactQuote],selected:ShadowExactQuote,outcomes:tuple[OutcomeId,...]):
    peers={}
    for q in quotes:
        if (q.fixture_identity,q.provider_event_id,q.market_id,q.provider_market_id,q.provider_specifier,q.line)!=(selected.fixture_identity,selected.provider_event_id,selected.market_id,selected.provider_market_id,selected.provider_specifier,selected.line): continue
        if (q.source_inventory_sha256,q.source_raw_sha256,q.source_manifest_sha256,q.observed_at)!=(selected.source_inventory_sha256,selected.source_raw_sha256,selected.source_manifest_sha256,selected.observed_at): return ShadowDevigStatus.CROSS_SNAPSHOT,None,None
        if q.outcome_id in peers: return ShadowDevigStatus.INCOMPLETE_PARTITION,None,None
        peers[q.outcome_id]=q
    if set(peers)!=set(outcomes): return ShadowDevigStatus.INCOMPLETE_PARTITION,None,None
    implied={o:1.0/peers[o].decimal_odds for o in outcomes}; over=math.fsum(implied.values())
    if not math.isfinite(over) or over<=0: return ShadowDevigStatus.INCOMPLETE_PARTITION,None,None
    return ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION,implied[selected.outcome_id]/over,over

def _settlement(a:ShadowMarketAssessment,outcome:OutcomeId,line:Optional[float],odds:float):
    if a.market_id in PUSH_SPLIT_MARKETS:
        rows=tuple(x for x in a.settlement_distributions if x.outcome_id is outcome and getattr(x.settlement,"line",None)==line)
        if len(rows)!=1: raise ShadowPriceError("settlement distribution missing for exact outcome/line")
        s=rows[0].settlement; states=(("WIN",float(s.full_win)),("HALF_WIN",float(s.half_win)),("PUSH",float(s.push)),("HALF_LOSS",float(s.half_loss)),("LOSS",float(s.full_loss)))
        if a.market_id is MarketId.DRAW_NO_BET: states=tuple(x for x in states if x[0] not in {"HALF_WIN","HALF_LOSS"})
        if not math.isclose(math.fsum(p for _,p in states),1.0,abs_tol=1e-9): raise ShadowPriceError("settlement mass does not sum to 1")
        returns=tuple((state,settlement_unit_return(state,odds)) for state,_ in states)
        return states,returns,math.fsum(p*settlement_unit_return(state,odds) for state,p in states)
    rows=tuple(x for x in a.event_probabilities if x.outcome_id is outcome and x.line==line)
    if len(rows)!=1: raise ShadowPriceError("event probability missing for exact outcome/line")
    p=float(rows[0].probability); states=(("WIN",p),("LOSS",1-p)); returns=(("WIN",odds-1.0),("LOSS",-1.0))
    return states,returns,p*(odds-1.0)-(1-p)

def price_one(*,context:CurrentShadowPriceContext,assessment:ShadowMarketAssessment,outcome_id:OutcomeId,line:Optional[float],
        model_probability:Optional[float],quotes:Sequence[ShadowExactQuote]) -> ShadowPriceResult:
    if assessment.disposition not in {ShadowDisposition.ANALYTICAL_READY,ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED}:
        return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=ShadowPriceDisposition.UNPRICED_UPSTREAM_BLOCKED,reason=assessment.blocker_reason or assessment.disposition.value,model_probability=model_probability)
    if assessment.disposition is ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED or _blocked(assessment.provider_semantic_status):
        return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=ShadowPriceDisposition.UNPRICED_PROVIDER_BLOCKED,reason=f"provider semantic status={assessment.provider_semantic_status}",model_probability=model_probability)
    q,bad,reason=_match(quotes,context.fixture_identity,assessment.market_id,outcome_id,line)
    if q is None: return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=bad or ShadowPriceDisposition.UNPRICED_NO_EXACT_QUOTE,reason=reason or "no exact current quote",model_probability=model_probability)
    if q.provider_semantic_status!=assessment.provider_semantic_status: return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=ShadowPriceDisposition.UNPRICED_PROVIDER_BLOCKED,reason="quote/PR-C provider semantic status mismatch",model_probability=model_probability)
    evaluation=_utc(context.evaluation_time); age=(evaluation-q.observed_at).total_seconds(); lead=(q.kickoff_utc-evaluation).total_seconds()
    if age<0: return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=ShadowPriceDisposition.UNPRICED_FUTURE_QUOTE,reason="quote is future-dated",model_probability=model_probability)
    if age>MAX_QUOTE_AGE_SECONDS: return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=ShadowPriceDisposition.UNPRICED_STALE_QUOTE,reason="quote is stale",model_probability=model_probability)
    if lead<=MINIMUM_LEAD_SECONDS: return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=ShadowPriceDisposition.UNPRICED_TOO_CLOSE_TO_KICKOFF,reason="event is too close to kickoff",model_probability=model_probability)
    try: states,returns,ev=_settlement(assessment,outcome_id,line,q.decimal_odds)
    except ShadowPriceError as exc: return _empty_result(context=context,assessment=assessment,outcome_id=outcome_id,line=line,disposition=ShadowPriceDisposition.UNPRICED_SETTLEMENT_INCOMPLETE,reason=str(exc),model_probability=model_probability)
    if assessment.market_id in OVERLAPPING_MARKETS: devig,fair,over=ShadowDevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS,None,None
    elif assessment.market_id in PUSH_SPLIT_MARKETS: devig,fair,over=ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT,None,None
    elif assessment.market_id in ORDINARY_PARTITIONS: devig,fair,over=_partition(quotes,q,ORDINARY_PARTITIONS[assessment.market_id])
    else: devig,fair,over=ShadowDevigStatus.NOT_APPLICABLE,None,None
    return _issue_shadow_price_result(fixture_identity=context.fixture_identity,market_id=assessment.market_id,outcome_id=outcome_id,
        line=line,disposition=ShadowPriceDisposition.PRICED,model_probability=model_probability,decimal_odds=q.decimal_odds,
        implied_probability=1.0/q.decimal_odds,fair_probability=fair,overround=over,devig_status=devig,net_expected_value=ev,
        expected_return_multiplier=1.0+ev,settlement_state_probabilities=states,settlement_unit_returns=returns,
        quote_identity_sha256=q.identity_sha256,provider_event_id=q.provider_event_id,provider_semantic_status=assessment.provider_semantic_status,
        rejection_reason=None,source_raw_sha256=q.source_raw_sha256,source_manifest_sha256=q.source_manifest_sha256,
        source_inventory_sha256=q.source_inventory_sha256,provider_observation_sha256=q.provider_observation_sha256,**_ancestry(context,assessment))

__all__=["_empty_result","price_one"]