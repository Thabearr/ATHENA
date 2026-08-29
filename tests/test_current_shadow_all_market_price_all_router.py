from __future__ import annotations
from datetime import datetime,timedelta,timezone
import inspect
from pathlib import Path
from types import SimpleNamespace
import pytest
from domain import current_all_market_shadow_probability_settlement as prc
from domain import current_sportybet_semantic_registry as prb
from domain import sportybet_live_event_quote_evidence as live
from domain.current_fotmob_latest_durable_fresh_history import CurrentLatestDurableFreshHistoryHandoff
from domain.current_direct_provider_live_quote_mapping_consumption import CurrentDirectProviderMappedQuoteBundle
from domain.markets import MarketId,OutcomeId
from domain._current_shadow_price_core import ShadowPriceError
from domain._current_shadow_price_records import ShadowExactQuote,ShadowPriceResult,ShadowPriceAllBundle,ShadowMarketRouterDecision
from domain._current_shadow_quote_binding import CurrentShadowPriceContext,build_current_shadow_exact_quotes,build_current_shadow_price_context
from domain import current_shadow_all_market_price_all as price_all
from domain import current_shadow_all_market_router as router

NOW=datetime(2026,8,29,17,0,tzinfo=timezone.utc); KICKOFF=NOW+timedelta(hours=2); EVENT="sr:match:1001"; FIXTURE="FOTMOB:PRD1"
A="a"*64; B="b"*64; C="c"*64; D="d"*64; E="e"*64; F="f"*64

def _xg(): return prc.ResearchXGRates(calibrated_home=2.0,calibrated_away=.7,sealed_prediction_sha256=A,history_prefix_identity=B,source_fixture_identity=FIXTURE)
def _scan(): return prc.scan_fixture_all_markets(fixture_identity=FIXTURE,research_xg=_xg(),kickoff_utc_iso=KICKOFF.isoformat().replace("+00:00","Z"),provider_semantic_by_market={m:"SUPPORTED" for m in MarketId})

def test_prd_does_not_modify_prc_canonical_scan_schema():
    source=Path("domain/_all_market_shadow_types.py").read_text()
    assert "source_lane" not in source and "CURRENT_SOURCE_BOUND" not in source

def test_current_api_has_no_raw_scan_quote_or_subset_escape_hatch():
    assert set(inspect.signature(build_current_shadow_price_context).parameters)=={"complete_current_history","fixture_identity","provider_event_evidence","fixture_quote_bridge"}
    assert tuple(inspect.signature(price_all.price_all_shadow_fixture).parameters)==("context",)
    assert tuple(inspect.signature(router.route_shadow_price_results).parameters)==("price_all",)

def test_current_authority_records_are_builder_only():
    for cls in (CurrentShadowPriceContext,ShadowExactQuote,ShadowPriceResult,ShadowPriceAllBundle,ShadowMarketRouterDecision):
        with pytest.raises(ShadowPriceError): cls()  # type: ignore[call-arg]

def test_no_public_string_issuance_tokens():
    source=Path("domain/_current_shadow_price_core.py").read_text()
    assert "SOURCE_BOUND_ISSUANCE_TOKEN" not in source
    assert "PRICE_ALL_ISSUANCE_TOKEN" not in source

def test_context_builder_composes_verified_bridge_replayed_event_prb_and_real_prc_entrypoint(monkeypatch):
    sel=live.SportyBetLiveEventSelection(event_id=EVENT,market_id="1",market_name="1X2",specifier=None,outcome_id="1",outcome_name="Home",bookable=True,bookability_basis="EXPLICIT_ACTIVE_FLAG",odds_raw="1.45",odds_decimal=1.45)
    inv=live.SportyBetLiveEventQuoteInventory(dataset_name=live.INVENTORY_DATASET_NAME,event_id=EVENT,home_team_name="Home",away_team_name="Away",kickoff_utc=KICKOFF,booking_status="Available",event_status=0,match_status="Not Started",prematch_bookable_observed=True,observed_at=NOW,observation_authority=live.OBSERVATION_AUTHORITY,provider_quote_at=None,provider_snapshot_id=None,source_manifest_sha256=B,source_raw_sha256=A,selections=(sel,))
    bridge_input=object.__new__(CurrentDirectProviderMappedQuoteBundle); evidence_input=object.__new__(prb.ProviderEventEvidence); history=object.__new__(CurrentLatestDurableFreshHistoryHandoff)
    bridge=SimpleNamespace(proof_mode="LIVE_CURRENT",fixture_id=FIXTURE,event_id=EVENT,current_inventory_sha256=inv.canonical_sha256,current_manifest_sha256=inv.source_manifest_sha256,current_raw_sha256=inv.source_raw_sha256,kickoff_utc=KICKOFF,evaluation_time=NOW,source_current_reconciliation_sha256=D,current_mapping_rebind_sha256=E,canonical_sha256=F)
    evidence=SimpleNamespace(inventory=inv); registry=SimpleNamespace(canonical_sha256=D); scan=_scan(); calls=[]
    monkeypatch.setattr("domain._current_shadow_quote_binding.current_quotes.verify_current_direct_provider_mapped_quote_bundle",lambda value:(calls.append("bridge") or bridge))
    monkeypatch.setattr("domain._current_shadow_quote_binding.prb.replay_event_evidence",lambda value:(calls.append("event") or evidence))
    monkeypatch.setattr("domain._current_shadow_quote_binding.prb.build_registry",lambda *a,**k:(calls.append("registry") or registry))
    def current(**kwargs):
        calls.append("prc"); assert kwargs["complete_current_history"] is history; assert kwargs["provider_semantic_registry"] is registry; return scan
    monkeypatch.setattr("domain._current_shadow_quote_binding.prc.scan_current_fixture_all_markets",current)
    context=build_current_shadow_price_context(complete_current_history=history,fixture_identity=FIXTURE,provider_event_evidence=evidence_input,fixture_quote_bridge=bridge_input)
    assert calls==["bridge","event","registry","prc"] and context.scan is scan and context.fixture_reconciliation_sha256==D

def _retained_evidence(tmp_path:Path):
    payload={"bizCode":10000,"data":{"eventId":EVENT,"homeTeamName":"Home","awayTeamName":"Away","estimateStartTime":KICKOFF.timestamp()*1000,"bookingStatus":"Available","status":0,"matchStatus":"Not Started","markets":[{"id":"1","desc":"1X2","specifier":None,"outcomes":[{"id":"1","desc":"Home","odds":"1.45","isActive":1},{"id":"2","desc":"Draw","odds":"5.00","isActive":1},{"id":"3","desc":"Away","odds":"10.00","isActive":1}]}]}}
    root=tmp_path.resolve(); raw=live._canonical_json_bytes(payload); manifest=live._build_manifest(event_id=EVENT,raw=raw,status=200,observed_at=NOW); eroot=live._evidence_root(root,create=True); directory=eroot/live.capture_identifier(manifest); directory.mkdir(); (directory/live.RAW_FILENAME).write_bytes(raw); (directory/live.MANIFEST_FILENAME).write_bytes(live.canonical_manifest_bytes(manifest)); return prb.load_provider_event_evidence(directory,repository_root=root)

def test_quotes_are_derived_from_typed_prb_semantics_over_replayed_inventory(tmp_path):
    evidence=_retained_evidence(tmp_path); registry=prb.build_registry((evidence,),evaluation_time=NOW,scan_cap=1,scan_attempts=1)
    context=object.__new__(CurrentShadowPriceContext)
    fields={"fixture_identity":FIXTURE,"provider_event_id":EVENT,"provider_registry":registry,"provider_registry_sha256":registry.canonical_sha256,"provider_inventory":evidence.inventory,"source_raw_sha256":evidence.inventory.source_raw_sha256,"source_manifest_sha256":evidence.inventory.source_manifest_sha256,"source_inventory_sha256":evidence.inventory.canonical_sha256,"fixture_reconciliation_sha256":D,"current_mapping_rebind_sha256":E,"bridge_bundle_sha256":F}
    for k,v in fields.items(): object.__setattr__(context,k,v)
    quotes=build_current_shadow_exact_quotes(context)
    assert {(q.market_id,q.outcome_id) for q in quotes}=={(MarketId.MATCH_RESULT,OutcomeId.HOME),(MarketId.MATCH_RESULT,OutcomeId.DRAW),(MarketId.MATCH_RESULT,OutcomeId.AWAY)}
    assert all(q.source_inventory_sha256==evidence.inventory.canonical_sha256 for q in quotes)