"""Execute PR90's reviewed FotMob ``status.reason`` gate on the exact PR85 pair."""
from __future__ import annotations

import dataclasses, datetime, hashlib, json, types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_data_matches_status_reason_semantics_protocol as pr90
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureManifest, parse_utc_timestamp, serialize_utc,
    sha256_bytes, sha256_data_matches_capture_manifest,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

SCHEMA_VERSION=1
DATASET_NAME="athena-fotmob-data-matches-status-reason-semantics-validation-v1"
EXECUTION_SCOPE="EXECUTE_PR90_AGAINST_EXACT_PR85_PAIR_ONLY"
EXECUTION_STATE="EXECUTED_ORDINARY_FT_REASON_GATE_QUALIFIED_PENALTY_BLOCKED"
REPOSITORY_MAIN_SHA="37b1d69c6543104b390d341b343588617c101902"
CANDIDATE_SOURCE_KEY="fotmob_data_matches_reviewed_catalog"
PR83_PROTOCOL_BLOB_SHA="25f8045524badcb90239df59ac9c47f36fcffe34"
PR85_EVIDENCE_BLOB_SHA="7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
PR89_IMPLEMENTATION_BLOB_SHA="f33dd31aedcd92b5691a3503914ed184d601b493"
PR90_PROTOCOL_BLOB_SHA="f9546ff05cddfe366d278d4dbdf1020bb7666951"
PR90_PROTOCOL_SHA256="08bbc2d1e53cfb1268ba71745ae80d9bc32f4bfad0f02d52225df936c7634f23"
PR90_PROTOCOL_SIZE=5602
SOURCE_CAPABILITIES_BLOB_SHA="ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
REQUEST_DATE,TIMEZONE,CCODE3="20260814","UTC","NGA"
FIRST_CAPTURE_ID="a18e843fabe5aca74846b160"
FIRST_RAW_SHA256="fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
FIRST_MANIFEST_SHA256="27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"
FIRST_RAW_SIZE=114920
FIRST_OBSERVED_AT="2026-08-14T17:12:02.437509Z"
SECOND_CAPTURE_ID="e28d9ce746c1ef9102995517"
SECOND_RAW_SHA256="175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
SECOND_MANIFEST_SHA256="d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"
SECOND_RAW_SIZE=114964
SECOND_OBSERVED_AT="2026-08-14T17:17:13.043248Z"
OBSERVATION_SEPARATION_MICROSECONDS=310605739
STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT=29
ORDINARY_FT_REASON_QUALIFIED_COUNT=28
PENALTY_REASON_BLOCKED_COUNT=1
OTHER_REASON_BLOCKED_COUNT=0
ORDINARY_FT_REASON_TUPLE=types.MappingProxyType({"short":"FT","shortKey":"fulltime_short","long":"Full-Time","longKey":"finished"})
PENALTY_REASON_TUPLE=types.MappingProxyType({"short":"Pen","shortKey":"penalties_short","long":"After penalties","longKey":"afterpenalties"})
PENALTY_FIXTURE_ID=5844873
PENALTY_HOME_SCORE,PENALTY_AWAY_SCORE=1,1
PENALTY_HOME_PEN_SCORE,PENALTY_AWAY_PEN_SCORE=5,6
PENALTY_ELIMINATED_TEAM_ID=6576
NEXT_REQUIRED_BOUNDARY="EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION_WITH_REVIEWED_REASON_GATE"
RECEIPT_SHA256="3e8537a4ddfd2d558a493ace74bd302a7d9f835c4768dc05049682e8ddf94abf"
RECEIPT_SIZE=3307
_SAFETY_KEYS=frozenset({
"network_acquisition_authorized","status_reason_semantics_execution_authorized",
"status_reason_semantics_globally_qualified","penalty_score_semantics_qualified",
"final_result_semantics_execution_authorized","final_result_semantics_qualified",
"source_capability_update_authorized","source_history_adapter_approved",
"source_history_completeness_proven","pr80_constructor_input_authorized",
"successor_live_inputs_qualified","successor_candidate_approved",
"expected_goals_transform_approved","expected_goals_production_authorized",
"score_matrix_authorized","probability_inference_authorized",
"probability_adjustment_authorized","calibration_for_production_authorized",
"pricing_authorized","market_activation_authorized","selection_authorized",
"production_approval_authorized","bet_authorized"})

class FotMobDataMatchesStatusReasonSemanticsValidationError(ValueError): pass
def _error(msg:str): return FotMobDataMatchesStatusReasonSemanticsValidationError(msg)
def _safety(): return {k:False for k in sorted(_SAFETY_KEYS)}
def _plain(v:Any)->Any:
    if isinstance(v,Mapping): return {k:_plain(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)): return [_plain(x) for x in v]
    return v
def _canonical(v:Any)->bytes:
    return (json.dumps(_plain(v),ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def _freeze_receipt(v:Mapping[str,Any])->Mapping[str,Any]:
    out=dict(v)
    out["ordinary_ft_reason_tuple"]=types.MappingProxyType(dict(out["ordinary_ft_reason_tuple"]))
    out["penalty_reason_tuple"]=types.MappingProxyType(dict(out["penalty_reason_tuple"]))
    out["safety"]=types.MappingProxyType(dict(out["safety"]))
    return types.MappingProxyType(out)

def _expected()->dict[str,Any]:
    return {
      "schema_version":1,"dataset_name":DATASET_NAME,"execution_scope":EXECUTION_SCOPE,
      "execution_state":EXECUTION_STATE,"repository_main_sha":REPOSITORY_MAIN_SHA,
      "candidate_source_key":CANDIDATE_SOURCE_KEY,"pr83_protocol_blob_sha":PR83_PROTOCOL_BLOB_SHA,
      "pr85_evidence_blob_sha":PR85_EVIDENCE_BLOB_SHA,"pr89_implementation_blob_sha":PR89_IMPLEMENTATION_BLOB_SHA,
      "pr90_protocol_blob_sha":PR90_PROTOCOL_BLOB_SHA,"source_capabilities_blob_sha":SOURCE_CAPABILITIES_BLOB_SHA,
      "request_date":REQUEST_DATE,"timezone":TIMEZONE,"ccode3":CCODE3,
      "first_capture_id":FIRST_CAPTURE_ID,"first_raw_sha256":FIRST_RAW_SHA256,
      "first_manifest_sha256":FIRST_MANIFEST_SHA256,"first_raw_size":FIRST_RAW_SIZE,"first_observed_at":FIRST_OBSERVED_AT,
      "second_capture_id":SECOND_CAPTURE_ID,"second_raw_sha256":SECOND_RAW_SHA256,
      "second_manifest_sha256":SECOND_MANIFEST_SHA256,"second_raw_size":SECOND_RAW_SIZE,"second_observed_at":SECOND_OBSERVED_AT,
      "observation_separation_microseconds":OBSERVATION_SEPARATION_MICROSECONDS,
      "stable_finished_identity_score_pair_count":29,"ordinary_ft_reason_qualified_count":28,
      "penalty_reason_blocked_count":1,"other_reason_blocked_count":0,
      "ordinary_ft_reason_tuple":dict(ORDINARY_FT_REASON_TUPLE),"penalty_reason_tuple":dict(PENALTY_REASON_TUPLE),
      "penalty_fixture_id":5844873,"penalty_home_score":1,"penalty_away_score":1,
      "penalty_home_pen_score":5,"penalty_away_pen_score":6,"penalty_eliminated_team_id":6576,
      "ordinary_ft_reason_gate_has_qualified_candidates":True,"status_reason_semantics_globally_qualified":False,
      "penalty_score_semantics_qualified":False,"final_result_semantics_qualified":False,
      "source_capability_full_time_score":"NOT_CAPTURED","historical_coverage":"UNKNOWN",
      "next_required_boundary":NEXT_REQUIRED_BOUNDARY,"safety":_safety()}

def _verify_upstream()->None:
    if (pr90.PROTOCOL_SHA256,pr90.PROTOCOL_SIZE)!=(PR90_PROTOCOL_SHA256,PR90_PROTOCOL_SIZE): raise _error("PR90 identity changed")
    if (pr90.PR83_PROTOCOL_BLOB_SHA,pr90.PR85_EVIDENCE_BLOB_SHA,pr90.PR89_IMPLEMENTATION_BLOB_SHA,pr90.SOURCE_CAPABILITIES_BLOB_SHA)!=(PR83_PROTOCOL_BLOB_SHA,PR85_EVIDENCE_BLOB_SHA,PR89_IMPLEMENTATION_BLOB_SHA,SOURCE_CAPABILITIES_BLOB_SHA): raise _error("PR90 ancestry changed")
    p=pr90.build_fotmob_data_matches_status_reason_semantics_protocol(); b=pr90.canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes(p)
    if hashlib.sha256(b).hexdigest()!=PR90_PROTOCOL_SHA256 or len(b)!=PR90_PROTOCOL_SIZE: raise _error("PR90 canonical identity changed")
    if pr90.NEXT_REQUIRED_BOUNDARY!="EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_VALIDATION": raise _error("PR90 next boundary changed")
    if pr89.NEXT_REQUIRED_BOUNDARY!="PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL": raise _error("PR89 next boundary changed")
    c=SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if c is None or c.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED or c.full_time_score is not CapabilityAvailability.NOT_CAPTURED or c.historical_coverage is not CapabilityAvailability.UNKNOWN: raise _error("source capability premise changed")

def _capture(raw:Any,m:Any,raw_sha:str,manifest_sha:str,size:int,observed:str)->FotMobDataMatchesCaptureManifest:
    if type(raw) is not bytes or not raw or not isinstance(m,FotMobDataMatchesCaptureManifest): raise _error("invalid capture input")
    try: m=dataclasses.replace(m)
    except Exception as exc: raise _error("manifest no longer revalidates") from exc
    if (m.request_date,m.timezone,m.ccode3)!=(REQUEST_DATE,TIMEZONE,CCODE3): raise _error("request identity changed")
    if sha256_bytes(raw)!=raw_sha or m.raw_sha256!=raw_sha or len(raw)!=size or m.raw_size!=size: raise _error("raw lineage changed")
    if sha256_data_matches_capture_manifest(m)!=manifest_sha or serialize_utc(m.observed_at)!=observed: raise _error("manifest lineage changed")
    return m

def _payload(raw:bytes)->dict[str,Any]:
    try: p=json.loads(raw)
    except Exception as exc: raise _error("raw JSON parse failed") from exc
    if type(p) is not dict or type(p.get("leagues")) is not list: raise _error("payload shape changed")
    return p

def _reason(status:Mapping[str,Any]):
    if "reason" not in status: return None
    r=status["reason"]; keys={"short","shortKey","long","longKey"}
    if type(r) is not dict or set(r)!=keys or any(type(r[k]) is not str or not r[k] for k in keys): raise _error("reason shape changed")
    return {k:r[k] for k in ("short","shortKey","long","longKey")}

def _index(p:Mapping[str,Any],observed:datetime.datetime)->dict[int,dict[str,Any]]:
    out={}
    for league in p["leagues"]:
      if type(league) is not dict or type(league.get("matches")) is not list: raise _error("league shape changed")
      for m in league["matches"]:
        if type(m) is not dict: raise _error("match shape changed")
        fid=m.get("id")
        if type(fid) is not int or fid<1 or fid in out: raise _error("invalid/duplicate fixture id")
        s,h,a=m.get("status"),m.get("home"),m.get("away")
        if not all(type(x) is dict for x in (s,h,a)): continue
        if s.get("finished") is not True or s.get("started") is not True or s.get("cancelled") is not False: continue
        hs,aws,hid,aid,lid,k=h.get("score"),a.get("score"),h.get("id"),a.get("id"),m.get("leagueId"),s.get("utcTime")
        if type(hs) is not int or hs<0 or type(aws) is not int or aws<0 or type(hid) is not int or hid<1 or type(aid) is not int or aid<1 or type(lid) is not int or lid<1 or type(k) is not str: continue
        try: kickoff=parse_utc_timestamp(k,"status.utcTime")
        except Exception as exc: raise _error("invalid kickoff") from exc
        if observed<=kickoff: continue
        out[fid]={"fixture_id":fid,"league_id":lid,"home_id":hid,"away_id":aid,"kickoff":k,"home_score":hs,"away_score":aws,"reason":_reason(s),"awarded":s.get("awarded"),"home_pen_score_present":"penScore" in h,"away_pen_score_present":"penScore" in a,"home_pen_score":h.get("penScore"),"away_pen_score":a.get("penScore"),"eliminated_team_id":m.get("eliminatedTeamId")}
    return out

def _classify(a:Mapping[str,Any],b:Mapping[str,Any])->str:
    if a["reason"]!=b["reason"]: return "BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL"
    if a["reason"]==ORDINARY_FT_REASON_TUPLE:
      if a["awarded"] not in (None,False) or b["awarded"] not in (None,False): return "BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW"
      if a["home_pen_score_present"] or a["away_pen_score_present"] or b["home_pen_score_present"] or b["away_pen_score_present"]: return "BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW"
      return "QUALIFIED_PR83_REASON_GATE_ORDINARY_FT_SOURCE_LABEL"
    if a["reason"]==PENALTY_REASON_TUPLE: return "BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS"
    return "BLOCKED_REASON_TUPLE_UNREVIEWED"

def execute_fotmob_data_matches_status_reason_semantics_validation(first_raw_json:bytes,first_manifest:FotMobDataMatchesCaptureManifest,second_raw_json:bytes,second_manifest:FotMobDataMatchesCaptureManifest)->Mapping[str,Any]:
    _verify_upstream()
    fm=_capture(first_raw_json,first_manifest,FIRST_RAW_SHA256,FIRST_MANIFEST_SHA256,FIRST_RAW_SIZE,FIRST_OBSERVED_AT)
    sm=_capture(second_raw_json,second_manifest,SECOND_RAW_SHA256,SECOND_MANIFEST_SHA256,SECOND_RAW_SIZE,SECOND_OBSERVED_AT)
    d=sm.observed_at-fm.observed_at; micro=d.days*86400_000_000+d.seconds*1_000_000+d.microseconds
    if micro!=OBSERVATION_SEPARATION_MICROSECONDS or micro<pr90.pr83.MINIMUM_REPEAT_SEPARATION_SECONDS*1_000_000: raise _error("repeat separation changed")
    try:
      fa=pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(first_raw_json,fm); sa=pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(second_raw_json,sm)
    except Exception as exc: raise _error("PR89 structural chain rejected exact evidence") from exc
    q=pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    if fa.status is not q or sa.status is not q or fa.status_reason_semantics_qualified or sa.status_reason_semantics_qualified: raise _error("PR89 structural authority changed")
    fi,si=_index(_payload(first_raw_json),fm.observed_at),_index(_payload(second_raw_json),sm.observed_at)
    fields=("fixture_id","league_id","home_id","away_id","kickoff","home_score","away_score")
    stable=[(fi[x],si[x]) for x in sorted(set(fi)&set(si)) if all(fi[x][f]==si[x][f] for f in fields)]
    if len(stable)!=29: raise _error("stable PR83 candidate count changed")
    counts={}; penalty=None
    for a,b in stable:
      s=_classify(a,b)
      if s not in pr90.STATUS_VOCABULARY: raise _error("disposition escaped PR90 vocabulary")
      counts[s]=counts.get(s,0)+1
      if s=="BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS": penalty=(a,b)
    ordinary=counts.get("QUALIFIED_PR83_REASON_GATE_ORDINARY_FT_SOURCE_LABEL",0); pen=counts.get("BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS",0); other=len(stable)-ordinary-pen
    if (ordinary,pen,other)!=(28,1,0) or penalty is None: raise _error("PR90 reason outcome changed")
    for x in penalty:
      if (x["fixture_id"],x["home_score"],x["away_score"],x["home_pen_score"],x["away_pen_score"],x["eliminated_team_id"],x["reason"])!=(5844873,1,1,5,6,6576,PENALTY_REASON_TUPLE): raise _error("penalty evidence changed")
    receipt=_expected(); b=_canonical(receipt)
    if hashlib.sha256(b).hexdigest()!=RECEIPT_SHA256 or len(b)!=RECEIPT_SIZE: raise _error("canonical receipt identity changed")
    return _freeze_receipt(receipt)

def canonical_fotmob_data_matches_status_reason_semantics_validation_receipt_bytes(value:Mapping[str,Any])->bytes:
    if not isinstance(value,Mapping) or _plain(value)!=_expected(): raise _error("receipt differs from exact PR91 outcome")
    return _canonical(value)
