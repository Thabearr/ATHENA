"""Builder-only records for current research Shadow Price-all + Router (PR D)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Optional
import math
from domain.markets import MarketId, OutcomeId
from domain._current_shadow_price_core import (
    AUTHORITY_FLAGS, DATASET_NAME, ROUTER_POLICY_ID, SCHEMA_VERSION,
    ShadowDevigStatus, ShadowModelAgreementStatus, ShadowOpportunityEligibility,
    ShadowPriceDisposition, ShadowPriceError, ShadowRouterDecisionStatus,
    _EVENT_RE, _finite, _odds, _probability, _require_sha, _sha256,
)

def _set(obj: Any, values: Mapping[str, Any]):
    for k, v in values.items(): object.__setattr__(obj, k, v)
    return obj

def _utc(v: Any, label: str) -> datetime:
    if type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None:
        raise ShadowPriceError(f"{label} must be timezone-aware")
    return v.astimezone(timezone.utc)

def _text(v: Any, label: str) -> str:
    if type(v) is not str or not v.strip() or v != v.strip():
        raise ShadowPriceError(f"{label} must be exact non-empty string")
    return v

def _line(v: Any) -> Optional[float]:
    if v is None: return None
    x = _finite(v, "line")
    return 0.0 if x == 0.0 else x

@dataclass(frozen=True, init=False)
class ShadowExactQuote:
    fixture_identity: str; provider_event_id: str; market_id: MarketId; outcome_id: OutcomeId
    line: Optional[float]; provider_line: Optional[str]; provider_market_id: str
    provider_market_name: str; provider_specifier: Optional[str]; provider_outcome_id: str
    provider_outcome_name: str; odds_raw: str; decimal_odds: float; observed_at: datetime
    kickoff_utc: datetime; source_raw_sha256: str; source_manifest_sha256: str
    source_inventory_sha256: str; provider_semantic_status: str; provider_registry_sha256: str
    provider_observation_sha256: str; fixture_reconciliation_sha256: str
    current_mapping_rebind_sha256: str; bridge_bundle_sha256: str; bookable: bool
    def __init__(self, *_a: Any, **_k: Any) -> None:
        raise ShadowPriceError("ShadowExactQuote is builder-only")
    @property
    def selection_identity(self):
        return (self.provider_event_id, self.provider_market_id, self.provider_specifier, self.provider_outcome_id)
    def to_dict(self):
        return {
            "fixture_identity":self.fixture_identity,"provider_event_id":self.provider_event_id,
            "market_id":self.market_id.value,"outcome_id":self.outcome_id.value,"line":self.line,
            "provider_line":self.provider_line,"provider_market_id":self.provider_market_id,
            "provider_market_name":self.provider_market_name,"provider_specifier":self.provider_specifier,
            "provider_outcome_id":self.provider_outcome_id,"provider_outcome_name":self.provider_outcome_name,
            "odds_raw":self.odds_raw,"decimal_odds":self.decimal_odds,
            "observed_at":self.observed_at.isoformat(timespec="microseconds").replace("+00:00","Z"),
            "kickoff_utc":self.kickoff_utc.isoformat(timespec="microseconds").replace("+00:00","Z"),
            "source_raw_sha256":self.source_raw_sha256,"source_manifest_sha256":self.source_manifest_sha256,
            "source_inventory_sha256":self.source_inventory_sha256,"provider_semantic_status":self.provider_semantic_status,
            "provider_registry_sha256":self.provider_registry_sha256,"provider_observation_sha256":self.provider_observation_sha256,
            "fixture_reconciliation_sha256":self.fixture_reconciliation_sha256,
            "current_mapping_rebind_sha256":self.current_mapping_rebind_sha256,"bridge_bundle_sha256":self.bridge_bundle_sha256,
            "bookable":self.bookable,
        }
    @property
    def identity_sha256(self): return _sha256(self.to_dict())

@dataclass(frozen=True, init=False)
class ShadowPriceResult:
    fixture_identity: str; market_id: MarketId; outcome_id: OutcomeId; line: Optional[float]
    disposition: ShadowPriceDisposition; model_probability: Optional[float]; decimal_odds: Optional[float]
    implied_probability: Optional[float]; fair_probability: Optional[float]; overround: Optional[float]
    devig_status: Optional[ShadowDevigStatus]; net_expected_value: Optional[float]
    expected_return_multiplier: Optional[float]; settlement_state_probabilities: tuple[tuple[str,float],...]
    settlement_unit_returns: tuple[tuple[str,float],...]; quote_identity_sha256: Optional[str]
    provider_event_id: Optional[str]; provider_semantic_status: Optional[str]; rejection_reason: Optional[str]
    probability_method: Optional[str]; probability_input_namespace: Optional[str]; prc_scan_sha256: str
    prc_assessment_sha256: str; sealed_prediction_sha256: Optional[str]; history_prefix_identity: Optional[str]
    source_fixture_identity: Optional[str]; provider_registry_sha256: str; source_raw_sha256: Optional[str]
    source_manifest_sha256: Optional[str]; source_inventory_sha256: Optional[str]
    provider_observation_sha256: Optional[str]; fixture_reconciliation_sha256: str
    current_mapping_rebind_sha256: str; bridge_bundle_sha256: str; score_matrix_audit: Optional[Mapping[str,Any]]
    specialist_evidence: Optional[Mapping[str,Any]]
    def __init__(self, *_a: Any, **_k: Any) -> None: raise ShadowPriceError("ShadowPriceResult is builder-only")
    def to_dict(self):
        return {
            "fixture_identity":self.fixture_identity,"market_id":self.market_id.value,"outcome_id":self.outcome_id.value,
            "line":self.line,"disposition":self.disposition.value,"model_probability":self.model_probability,
            "decimal_odds":self.decimal_odds,"implied_probability":self.implied_probability,
            "fair_probability":self.fair_probability,"overround":self.overround,
            "devig_status":None if self.devig_status is None else self.devig_status.value,
            "net_expected_value":self.net_expected_value,"expected_return_multiplier":self.expected_return_multiplier,
            "settlement_state_probabilities":[{"state":s,"probability":p} for s,p in self.settlement_state_probabilities],
            "settlement_unit_returns":[{"state":s,"unit_return":r} for s,r in self.settlement_unit_returns],
            "quote_identity_sha256":self.quote_identity_sha256,"provider_event_id":self.provider_event_id,
            "provider_semantic_status":self.provider_semantic_status,"rejection_reason":self.rejection_reason,
            "probability_method":self.probability_method,"probability_input_namespace":self.probability_input_namespace,
            "prc_scan_sha256":self.prc_scan_sha256,"prc_assessment_sha256":self.prc_assessment_sha256,
            "sealed_prediction_sha256":self.sealed_prediction_sha256,"history_prefix_identity":self.history_prefix_identity,
            "source_fixture_identity":self.source_fixture_identity,"provider_registry_sha256":self.provider_registry_sha256,
            "source_raw_sha256":self.source_raw_sha256,"source_manifest_sha256":self.source_manifest_sha256,
            "source_inventory_sha256":self.source_inventory_sha256,"provider_observation_sha256":self.provider_observation_sha256,
            "fixture_reconciliation_sha256":self.fixture_reconciliation_sha256,
            "current_mapping_rebind_sha256":self.current_mapping_rebind_sha256,"bridge_bundle_sha256":self.bridge_bundle_sha256,
            "score_matrix_audit":None if self.score_matrix_audit is None else dict(self.score_matrix_audit),
            "specialist_evidence":None if self.specialist_evidence is None else dict(self.specialist_evidence),
        }
    @property
    def opportunity_id(self):
        return _sha256({"fixture":self.fixture_identity,"market":self.market_id.value,"outcome":self.outcome_id.value,
                        "line":self.line,"quote":self.quote_identity_sha256,"assessment":self.prc_assessment_sha256})

@dataclass(frozen=True, init=False)
class ShadowPriceAllBundle:
    fixture_identity: str; evaluation_time: datetime; prc_scan_sha256: str; provider_registry_sha256: str
    fixture_reconciliation_sha256: str; current_mapping_rebind_sha256: str; bridge_bundle_sha256: str
    quote_count: int; results: tuple[ShadowPriceResult,...]; authority: Mapping[str,bool]; _context: Any
    def __init__(self,*_a:Any,**_k:Any) -> None: raise ShadowPriceError("ShadowPriceAllBundle is builder-only")
    def to_dict(self):
        return {"schema_version":SCHEMA_VERSION,"dataset_name":DATASET_NAME,"fixture_identity":self.fixture_identity,
                "evaluation_time":self.evaluation_time.isoformat(timespec="microseconds").replace("+00:00","Z"),
                "prc_scan_sha256":self.prc_scan_sha256,"provider_registry_sha256":self.provider_registry_sha256,
                "fixture_reconciliation_sha256":self.fixture_reconciliation_sha256,
                "current_mapping_rebind_sha256":self.current_mapping_rebind_sha256,"bridge_bundle_sha256":self.bridge_bundle_sha256,
                "quote_count":self.quote_count,"result_count":len(self.results),"results":[x.to_dict() for x in self.results],
                "authority":dict(self.authority),"wager_placed":False}
    @property
    def canonical_sha256(self): return _sha256(self.to_dict())

@dataclass(frozen=True)
class ShadowRoutedOpportunity:
    opportunity_id: str; price_result: ShadowPriceResult; eligibility: ShadowOpportunityEligibility
    robust_net_expected_value: Optional[float]; robust_edge: Optional[float]; event_probability_floor: Optional[float]
    model_agreement: ShadowModelAgreementStatus; rejection_reasons: tuple[str,...]
    def __post_init__(self) -> None:
        _require_sha(self.opportunity_id,"opportunity_id")
        if type(self.price_result) is not ShadowPriceResult: raise ShadowPriceError("price_result type mismatch")
    def to_dict(self):
        return {"opportunity_id":self.opportunity_id,"price_result":self.price_result.to_dict(),
                "eligibility":self.eligibility.value,"robust_net_expected_value":self.robust_net_expected_value,
                "robust_edge":self.robust_edge,"event_probability_floor":self.event_probability_floor,
                "model_agreement":self.model_agreement.value,"rejection_reasons":list(self.rejection_reasons)}

@dataclass(frozen=True, init=False)
class ShadowMarketRouterDecision:
    fixture_identity: str; status: ShadowRouterDecisionStatus; selected_opportunity_id: Optional[str]
    runner_up_opportunity_id: Optional[str]; strongest_rejected_opportunity_id: Optional[str]
    opportunities: tuple[ShadowRoutedOpportunity,...]; price_all_bundle_sha256: str; router_policy_id: str
    authority: Mapping[str,bool]
    def __init__(self,*_a:Any,**_k:Any) -> None: raise ShadowPriceError("ShadowMarketRouterDecision is builder-only")
    def to_dict(self):
        return {"schema_version":SCHEMA_VERSION,"dataset_name":DATASET_NAME,"fixture_identity":self.fixture_identity,
                "status":self.status.value,"selected_opportunity_id":self.selected_opportunity_id,
                "runner_up_opportunity_id":self.runner_up_opportunity_id,
                "strongest_rejected_opportunity_id":self.strongest_rejected_opportunity_id,
                "opportunities":[x.to_dict() for x in self.opportunities],"price_all_bundle_sha256":self.price_all_bundle_sha256,
                "router_policy_id":self.router_policy_id,"authority":dict(self.authority),"wager_placed":False}
    @property
    def decision_sha256(self): return _sha256(self.to_dict())

def _issue_shadow_exact_quote(**v: Any) -> ShadowExactQuote:
    o=object.__new__(ShadowExactQuote); v=dict(v)
    v["fixture_identity"]=_text(v["fixture_identity"],"fixture_identity"); v["provider_event_id"]=_text(v["provider_event_id"],"provider_event_id")
    if _EVENT_RE.fullmatch(v["provider_event_id"]) is None: raise ShadowPriceError("provider_event_id must use sr:match:N")
    if type(v["market_id"]) is not MarketId or type(v["outcome_id"]) is not OutcomeId: raise ShadowPriceError("canonical quote identity type mismatch")
    v["line"]=_line(v.get("line")); v["decimal_odds"]=_odds(v["decimal_odds"]); v["observed_at"]=_utc(v["observed_at"],"observed_at"); v["kickoff_utc"]=_utc(v["kickoff_utc"],"kickoff_utc")
    for k in ("source_raw_sha256","source_manifest_sha256","source_inventory_sha256","provider_registry_sha256","provider_observation_sha256","fixture_reconciliation_sha256","current_mapping_rebind_sha256","bridge_bundle_sha256"): _require_sha(v[k],k)
    if v.get("bookable") is not True: raise ShadowPriceError("quote must be bookable")
    return _set(o,v)

def _issue_shadow_price_result(**v: Any) -> ShadowPriceResult:
    o=object.__new__(ShadowPriceResult); v=dict(v)
    if type(v["market_id"]) is not MarketId or type(v["outcome_id"]) is not OutcomeId or type(v["disposition"]) is not ShadowPriceDisposition: raise ShadowPriceError("price result identity type mismatch")
    v["line"]=_line(v.get("line"))
    for k in ("prc_scan_sha256","prc_assessment_sha256","provider_registry_sha256","fixture_reconciliation_sha256","current_mapping_rebind_sha256","bridge_bundle_sha256"): _require_sha(v[k],k)
    if v.get("model_probability") is not None: v["model_probability"]=_probability(v["model_probability"],"model_probability")
    if v.get("decimal_odds") is not None: v["decimal_odds"]=_odds(v["decimal_odds"])
    for k in ("implied_probability","fair_probability"):
        if v.get(k) is not None: v[k]=_probability(v[k],k)
    for k in ("overround","net_expected_value","expected_return_multiplier"):
        if v.get(k) is not None: v[k]=_finite(v[k],k)
    for k in ("quote_identity_sha256","source_raw_sha256","source_manifest_sha256","source_inventory_sha256","provider_observation_sha256"): _require_sha(v.get(k),k)
    probs=tuple(v.get("settlement_state_probabilities",())); returns=tuple(v.get("settlement_unit_returns",()))
    if probs and not math.isclose(sum(float(p) for _,p in probs),1.0,abs_tol=1e-9): raise ShadowPriceError("settlement mass must sum to 1")
    v["settlement_state_probabilities"]=probs; v["settlement_unit_returns"]=returns
    if v["disposition"] is ShadowPriceDisposition.PRICED and any(v.get(k) is None for k in ("decimal_odds","implied_probability","net_expected_value","expected_return_multiplier","quote_identity_sha256","provider_event_id","source_raw_sha256","source_manifest_sha256","source_inventory_sha256","provider_observation_sha256")): raise ShadowPriceError("PRICED result lacks exact source/value ancestry")
    return _set(o,v)

def _issue_shadow_price_all_bundle(**v: Any) -> ShadowPriceAllBundle:
    from domain._current_shadow_quote_binding import CurrentShadowPriceContext
    o=object.__new__(ShadowPriceAllBundle); v=dict(v); v["evaluation_time"]=_utc(v["evaluation_time"],"evaluation_time")
    for k in ("prc_scan_sha256","provider_registry_sha256","fixture_reconciliation_sha256","current_mapping_rebind_sha256","bridge_bundle_sha256"): _require_sha(v[k],k)
    v["results"]=tuple(v["results"])
    if any(type(x) is not ShadowPriceResult or x.fixture_identity != v["fixture_identity"] for x in v["results"]): raise ShadowPriceError("invalid price-all results")
    if len({x.opportunity_id for x in v["results"]}) != len(v["results"]): raise ShadowPriceError("duplicate price-all opportunity")
    if type(v["quote_count"]) is not int or v["quote_count"] < 0: raise ShadowPriceError("invalid quote_count")
    if type(v.get("_context")) is not CurrentShadowPriceContext: raise ShadowPriceError("price-all bundle requires exact source context")
    if dict(v.get("authority",{})) != dict(AUTHORITY_FLAGS): raise ShadowPriceError("price-all authority drifted")
    v["authority"]=MappingProxyType(dict(AUTHORITY_FLAGS)); return _set(o,v)

def _issue_shadow_router_decision(**v: Any) -> ShadowMarketRouterDecision:
    o=object.__new__(ShadowMarketRouterDecision); v=dict(v); v["opportunities"]=tuple(v["opportunities"])
    if type(v["status"]) is not ShadowRouterDecisionStatus or any(type(x) is not ShadowRoutedOpportunity for x in v["opportunities"]): raise ShadowPriceError("invalid router decision")
    ids={x.opportunity_id for x in v["opportunities"]}
    for k in ("selected_opportunity_id","runner_up_opportunity_id","strongest_rejected_opportunity_id"):
        x=v.get(k)
        if x is not None and x not in ids: raise ShadowPriceError(f"{k} absent from opportunities")
    if v["status"] is ShadowRouterDecisionStatus.SELECTED and v.get("selected_opportunity_id") is None: raise ShadowPriceError("SELECTED requires selection")
    if v["status"] is ShadowRouterDecisionStatus.NO_BET and v.get("selected_opportunity_id") is not None: raise ShadowPriceError("NO_BET cannot select")
    _require_sha(v["price_all_bundle_sha256"],"price_all_bundle_sha256")
    if v.get("router_policy_id") != ROUTER_POLICY_ID or dict(v.get("authority",{})) != dict(AUTHORITY_FLAGS): raise ShadowPriceError("router policy/authority drifted")
    v["authority"]=MappingProxyType(dict(AUTHORITY_FLAGS)); return _set(o,v)

__all__=["ShadowExactQuote","ShadowPriceResult","ShadowPriceAllBundle","ShadowRoutedOpportunity","ShadowMarketRouterDecision"]