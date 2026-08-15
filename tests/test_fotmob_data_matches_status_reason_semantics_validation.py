from __future__ import annotations

import ast, hashlib
from pathlib import Path

import pytest

import domain.fotmob_data_matches_status_reason_semantics_validation as validation
from domain.fotmob_data_matches_capture import verify_data_matches_capture_directory
from domain.fotmob_data_matches_eliminated_team_id_value_domain_extension import (
    EliminatedTeamIdValueDomainStatus,
    assess_fotmob_data_matches_eliminated_team_id_value_domain,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE_ROOT=ROOT/"evidence"/"fotmob_data_matches"/"pr83_post_finish_pair"
DATE_ROOT=EVIDENCE_ROOT/"20260814"
FIRST="a18e843fabe5aca74846b160"
SECOND="e28d9ce746c1ef9102995517"

def _blob(path:Path)->str:
    raw=path.read_bytes(); return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def _capture(cid:str):
    d=DATE_ROOT/cid
    m=verify_data_matches_capture_directory(d,allowed_root=EVIDENCE_ROOT,require_network_acquisition_performed=True)
    return (d/"response.json").read_bytes(),m

def _execute():
    a,am=_capture(FIRST); b,bm=_capture(SECOND)
    return validation.execute_fotmob_data_matches_status_reason_semantics_validation(a,am,b,bm)

def test_exact_merged_ancestry_blobs_are_frozen():
    assert validation.REPOSITORY_MAIN_SHA=="37b1d69c6543104b390d341b343588617c101902"
    assert _blob(ROOT/"domain"/"fotmob_data_matches_final_result_semantics_protocol.py")==validation.PR83_PROTOCOL_BLOB_SHA
    assert _blob(ROOT/"domain"/"fotmob_data_matches_post_finish_capture_pair_evidence.py")==validation.PR85_EVIDENCE_BLOB_SHA
    assert _blob(ROOT/"domain"/"fotmob_data_matches_eliminated_team_id_value_domain_extension.py")==validation.PR89_IMPLEMENTATION_BLOB_SHA
    assert _blob(ROOT/"domain"/"fotmob_data_matches_status_reason_semantics_protocol.py")==validation.PR90_PROTOCOL_BLOB_SHA
    assert validation.SOURCE_CAPABILITIES_BLOB_SHA=="ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"

def test_exact_pair_still_passes_pr89_structural_chain():
    for cid in (FIRST,SECOND):
        raw,m=_capture(cid); a=assess_fotmob_data_matches_eliminated_team_id_value_domain(raw,m)
        assert a.status is EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
        assert (a.eliminated_team_id_occurrence_count,a.eliminated_team_id_null_count,a.eliminated_team_id_non_null_count)==(183,182,1)
        assert a.status_reason_semantics_qualified is False and a.final_result_semantics_qualified is False

def test_execution_reproduces_exact_pr90_outcome():
    r=_execute()
    assert r["execution_state"]==validation.EXECUTION_STATE
    assert r["stable_finished_identity_score_pair_count"]==29
    assert r["ordinary_ft_reason_qualified_count"]==28
    assert r["penalty_reason_blocked_count"]==1
    assert r["other_reason_blocked_count"]==0
    assert r["observation_separation_microseconds"]==310605739
    assert r["ordinary_ft_reason_gate_has_qualified_candidates"] is True
    assert r["status_reason_semantics_globally_qualified"] is False
    assert r["penalty_score_semantics_qualified"] is False
    assert r["final_result_semantics_qualified"] is False
    assert r["next_required_boundary"]==validation.NEXT_REQUIRED_BOUNDARY

def test_penalty_candidate_remains_explicitly_blocked():
    r=_execute()
    assert (r["penalty_fixture_id"],r["penalty_home_score"],r["penalty_away_score"])==(5844873,1,1)
    assert (r["penalty_home_pen_score"],r["penalty_away_pen_score"])==(5,6)
    assert r["penalty_eliminated_team_id"]==6576
    assert dict(r["penalty_reason_tuple"])=={"short":"Pen","shortKey":"penalties_short","long":"After penalties","longKey":"afterpenalties"}

def test_canonical_receipt_identity_is_exact():
    r=_execute(); exact=validation.canonical_fotmob_data_matches_status_reason_semantics_validation_receipt_bytes(r)
    assert hashlib.sha256(exact).hexdigest()==validation.RECEIPT_SHA256=="3e8537a4ddfd2d558a493ace74bd302a7d9f835c4768dc05049682e8ddf94abf"
    assert len(exact)==validation.RECEIPT_SIZE==3307

def test_exact_classifier_and_guards_fail_closed():
    base={"reason":dict(validation.ORDINARY_FT_REASON_TUPLE),"awarded":None,"home_pen_score_present":False,"away_pen_score_present":False}
    assert validation._classify(base,dict(base))=="QUALIFIED_PR83_REASON_GATE_ORDINARY_FT_SOURCE_LABEL"
    awarded=dict(base,awarded=True); assert validation._classify(awarded,awarded)=="BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW"
    penfield=dict(base,home_pen_score_present=True); assert validation._classify(penfield,penfield)=="BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW"
    near={**base,"reason":{**base["reason"],"short":"ft"}}; assert validation._classify(near,near)=="BLOCKED_REASON_TUPLE_UNREVIEWED"
    penalty={**base,"reason":dict(validation.PENALTY_REASON_TUPLE)}; assert validation._classify(penalty,penalty)=="BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS"
    assert validation._classify(base,penalty)=="BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL"

def test_raw_lineage_or_capture_order_mutation_fails_closed():
    a,am=_capture(FIRST); b,bm=_capture(SECOND)
    with pytest.raises(validation.FotMobDataMatchesStatusReasonSemanticsValidationError):
        validation.execute_fotmob_data_matches_status_reason_semantics_validation(a+b" ",am,b,bm)
    with pytest.raises(validation.FotMobDataMatchesStatusReasonSemanticsValidationError):
        validation.execute_fotmob_data_matches_status_reason_semantics_validation(b,bm,a,am)

def test_receipt_is_deeply_immutable_and_authority_stays_fail_closed():
    r=_execute()
    assert all(type(v) is bool and v is False for v in r["safety"].values())
    with pytest.raises(TypeError): r["final_result_semantics_qualified"]=True
    with pytest.raises(TypeError): r["safety"]["bet_authorized"]=True
    with pytest.raises(TypeError): r["ordinary_ft_reason_tuple"]["short"]="X"
    capability=SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    bad=dict(r); bad["final_result_semantics_qualified"]=True
    with pytest.raises(validation.FotMobDataMatchesStatusReasonSemanticsValidationError):
        validation.canonical_fotmob_data_matches_status_reason_semantics_validation_receipt_bytes(bad)

def test_validation_imports_no_network_or_downstream_runtime_modules():
    tree=ast.parse((ROOT/"domain"/"fotmob_data_matches_status_reason_semantics_validation.py").read_text())
    roots=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Import): roots.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n,ast.ImportFrom) and n.module: roots.add(n.module.split(".")[0])
    assert roots.isdisjoint({"requests","httpx","aiohttp","providers","engine","models","services","workers"})
