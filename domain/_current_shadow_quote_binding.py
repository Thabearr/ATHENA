"""Replayable current-source context and exact PR-B quote issuance for PR D."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from domain import current_all_market_shadow_probability_settlement as prc
from domain import current_direct_provider_live_quote_mapping_consumption as current_quotes
from domain import current_sportybet_semantic_registry as prb
from domain import sportybet_live_event_quote_evidence as live
from domain.current_fotmob_latest_durable_fresh_history import CurrentLatestDurableFreshHistoryHandoff
from domain.markets import MarketId, OutcomeId
from domain._current_shadow_price_core import SOURCE_CONTEXT_POLICY_ID, ShadowPriceError, _canonical_bytes, _sha256
from domain._current_shadow_price_records import ShadowExactQuote, _issue_shadow_exact_quote

@dataclass(frozen=True, init=False)
class CurrentShadowPriceContext:
    fixture_identity: str; provider_event_id: str; evaluation_time: datetime
    scan: prc.CurrentAllMarketShadowFixtureScan; prc_scan_sha256: str
    provider_registry: prb.CurrentSportyBetSemanticRegistry; provider_registry_sha256: str
    provider_inventory: live.SportyBetLiveEventQuoteInventory; source_raw_sha256: str
    source_manifest_sha256: str; source_inventory_sha256: str
    fixture_reconciliation_sha256: str; current_mapping_rebind_sha256: str
    bridge_bundle_sha256: str; source_context_policy_id: str
    _bridge_bundle: current_quotes.CurrentDirectProviderMappedQuoteBundle
    _event_evidence: prb.ProviderEventEvidence
    _complete_current_history: CurrentLatestDurableFreshHistoryHandoff
    def __init__(self,*_a:Any,**_k:Any) -> None: raise ShadowPriceError("CurrentShadowPriceContext is builder-only")
    def to_dict(self):
        return {"fixture_identity":self.fixture_identity,"provider_event_id":self.provider_event_id,
                "evaluation_time":self.evaluation_time.isoformat(timespec="microseconds").replace("+00:00","Z"),
                "prc_scan_sha256":self.prc_scan_sha256,"provider_registry_sha256":self.provider_registry_sha256,
                "source_raw_sha256":self.source_raw_sha256,"source_manifest_sha256":self.source_manifest_sha256,
                "source_inventory_sha256":self.source_inventory_sha256,
                "fixture_reconciliation_sha256":self.fixture_reconciliation_sha256,
                "current_mapping_rebind_sha256":self.current_mapping_rebind_sha256,
                "bridge_bundle_sha256":self.bridge_bundle_sha256,"source_context_policy_id":self.source_context_policy_id,
                "wager_placed":False}
    @property
    def canonical_sha256(self): return _sha256(self.to_dict())

def _set(obj:Any, values:Mapping[str,Any]):
    for k,v in values.items(): object.__setattr__(obj,k,v)
    return obj

def _utc(v:Any) -> datetime:
    if type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None: raise ShadowPriceError("evaluation_time must be timezone-aware")
    return v.astimezone(timezone.utc)

def _kickoff(value:str|None):
    if value is None: return None
    if type(value) is not str or not value.endswith("Z"): raise ShadowPriceError("PR-C kickoff identity is invalid")
    try: return datetime.fromisoformat(value[:-1]+"+00:00").astimezone(timezone.utc)
    except (TypeError,ValueError) as exc: raise ShadowPriceError("PR-C kickoff identity is invalid") from exc

def build_current_shadow_price_context(*, complete_current_history:CurrentLatestDurableFreshHistoryHandoff,
        fixture_identity:str, provider_event_evidence:prb.ProviderEventEvidence,
        fixture_quote_bridge:current_quotes.CurrentDirectProviderMappedQuoteBundle) -> CurrentShadowPriceContext:
    """Compose only from replayable PR151, PR253 and PR-B current sources."""
    if type(complete_current_history) is not CurrentLatestDurableFreshHistoryHandoff: raise ShadowPriceError("complete_current_history type mismatch")
    if type(fixture_identity) is not str or not fixture_identity.strip(): raise ShadowPriceError("fixture_identity must be non-empty")
    if type(provider_event_evidence) is not prb.ProviderEventEvidence: raise ShadowPriceError("provider_event_evidence type mismatch")
    if type(fixture_quote_bridge) is not current_quotes.CurrentDirectProviderMappedQuoteBundle: raise ShadowPriceError("fixture_quote_bridge type mismatch")
    try: bridge=current_quotes.verify_current_direct_provider_mapped_quote_bundle(fixture_quote_bridge)
    except current_quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError as exc: raise ShadowPriceError("fixture bridge source replay failed") from exc
    if bridge.proof_mode != current_quotes.LIVE_CURRENT: raise ShadowPriceError("current Shadow pricing requires LIVE_CURRENT fixture bridge")
    if bridge.fixture_id != fixture_identity: raise ShadowPriceError("fixture bridge does not match requested PR-C fixture")
    try: evidence=prb.replay_event_evidence(provider_event_evidence)
    except prb.CurrentSportyBetSemanticRegistryError as exc: raise ShadowPriceError("PR-B provider event replay failed") from exc
    inv=evidence.inventory
    if (bridge.event_id,bridge.current_inventory_sha256,bridge.current_manifest_sha256,bridge.current_raw_sha256,bridge.kickoff_utc) != (inv.event_id,inv.canonical_sha256,inv.source_manifest_sha256,inv.source_raw_sha256,inv.kickoff_utc):
        raise ShadowPriceError("fixture bridge and replayed PR-B event ancestry differ")
    evaluation=_utc(bridge.evaluation_time)
    try:
        registry=prb.build_registry((evidence,),evaluation_time=evaluation,scan_cap=1,scan_attempts=1)
        scan=prc.scan_current_fixture_all_markets(complete_current_history=complete_current_history,
                fixture_identity=fixture_identity,provider_semantic_registry=registry)
    except Exception as exc: raise ShadowPriceError("current PR-B/PR-C source composition failed") from exc
    scan_kickoff=_kickoff(scan.kickoff_utc_iso)
    if scan_kickoff is not None and scan_kickoff != bridge.kickoff_utc: raise ShadowPriceError("PR-C and SportyBet fixture kickoff differ")
    value=object.__new__(CurrentShadowPriceContext)
    return _set(value,{"fixture_identity":fixture_identity,"provider_event_id":inv.event_id,"evaluation_time":evaluation,
        "scan":scan,"prc_scan_sha256":_sha256(scan.to_dict()),"provider_registry":registry,
        "provider_registry_sha256":registry.canonical_sha256,"provider_inventory":inv,
        "source_raw_sha256":inv.source_raw_sha256,"source_manifest_sha256":inv.source_manifest_sha256,
        "source_inventory_sha256":inv.canonical_sha256,"fixture_reconciliation_sha256":bridge.source_current_reconciliation_sha256,
        "current_mapping_rebind_sha256":bridge.current_mapping_rebind_sha256,"bridge_bundle_sha256":bridge.canonical_sha256,
        "source_context_policy_id":SOURCE_CONTEXT_POLICY_ID,"_bridge_bundle":bridge,"_event_evidence":evidence,
        "_complete_current_history":complete_current_history})

def verify_current_shadow_price_context(value:Any) -> CurrentShadowPriceContext:
    if type(value) is not CurrentShadowPriceContext: raise ShadowPriceError("value must be exact CurrentShadowPriceContext")
    rebuilt=build_current_shadow_price_context(complete_current_history=value._complete_current_history,
        fixture_identity=value.fixture_identity,provider_event_evidence=value._event_evidence,fixture_quote_bridge=value._bridge_bundle)
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()): raise ShadowPriceError("current Shadow price context differs on source replay")
    return rebuilt

def _canonical_line(obs:prb.ProviderSemanticObservation):
    if obs.line is None: return None
    try: line=float(obs.line)
    except (TypeError,ValueError,OverflowError) as exc: raise ShadowPriceError("provider line is invalid") from exc
    if obs.canonical_market_id is MarketId.ASIAN_HANDICAP and obs.canonical_outcome_id is OutcomeId.AWAY: return -line
    return line

def build_current_shadow_exact_quotes(context:CurrentShadowPriceContext) -> tuple[ShadowExactQuote,...]:
    """Issue complete exact current quote rows from typed PR-B observations."""
    if type(context) is not CurrentShadowPriceContext: raise ShadowPriceError("context type mismatch")
    inv=context.provider_inventory; by_native={x.selection_identity:x for x in inv.selections}
    if len(by_native)!=len(inv.selections): raise ShadowPriceError("provider inventory native identities are not unique")
    out=[]
    for coverage in context.provider_registry.coverage:
        if coverage.provider_status not in {prb.ProviderSemanticStatus.SUPPORTED,prb.ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY}: continue
        for obs in coverage.observations:
            if obs.provider_event_id != context.provider_event_id or obs.bookable is not True or obs.evidence_freshness is not prb.EvidenceFreshnessState.CURRENT or obs.line_analytically_eligible is not True: continue
            if (obs.source_event_detail_raw_sha256,obs.source_manifest_sha256,obs.source_inventory_sha256)!=(context.source_raw_sha256,context.source_manifest_sha256,context.source_inventory_sha256): raise ShadowPriceError("PR-B observation ancestry differs from context")
            selected=by_native.get((obs.provider_event_id,obs.provider_market_id,obs.provider_specifier,obs.provider_outcome_id))
            if selected is None or selected.market_name != obs.provider_market_name or selected.outcome_name != obs.provider_outcome_name or selected.bookable is not True: raise ShadowPriceError("PR-B observation differs from exact provider selection")
            out.append(_issue_shadow_exact_quote(fixture_identity=context.fixture_identity,provider_event_id=context.provider_event_id,
                market_id=obs.canonical_market_id,outcome_id=obs.canonical_outcome_id,line=_canonical_line(obs),provider_line=obs.line,
                provider_market_id=selected.market_id,provider_market_name=selected.market_name,provider_specifier=selected.specifier,
                provider_outcome_id=selected.outcome_id,provider_outcome_name=selected.outcome_name,odds_raw=selected.odds_raw,
                decimal_odds=selected.odds_decimal,observed_at=inv.observed_at,kickoff_utc=inv.kickoff_utc,
                source_raw_sha256=context.source_raw_sha256,source_manifest_sha256=context.source_manifest_sha256,
                source_inventory_sha256=context.source_inventory_sha256,provider_semantic_status=coverage.provider_status.value,
                provider_registry_sha256=context.provider_registry_sha256,provider_observation_sha256=_sha256(obs.to_dict()),
                fixture_reconciliation_sha256=context.fixture_reconciliation_sha256,current_mapping_rebind_sha256=context.current_mapping_rebind_sha256,
                bridge_bundle_sha256=context.bridge_bundle_sha256,bookable=True))
    ordered=tuple(sorted(out,key=lambda x:(x.market_id.value,x.outcome_id.value,-1.0 if x.line is None else x.line,x.provider_market_id,x.provider_specifier or "",x.provider_outcome_id)))
    if len({x.identity_sha256 for x in ordered}) != len(ordered): raise ShadowPriceError("duplicate current Shadow quote identity")
    return ordered

__all__=["CurrentShadowPriceContext","build_current_shadow_exact_quotes","build_current_shadow_price_context","verify_current_shadow_price_context"]