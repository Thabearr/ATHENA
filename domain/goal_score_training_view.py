"""Canonical three-corpus training-view bridge for Goal/Score Dynamics v2.

Historical As-Of and Tactical Identity provide pre-match model inputs.  The
#232 coverage corpus provides only safe regulation-score targets; post-match
richness/capability metadata is never a model feature.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
from types import MappingProxyType
from typing import Any, Mapping

from domain.goal_score_dynamics import (
    AUTHORITY_FLAGS,
    GOAL_SCORE_FEATURE_REGISTRY,
    GOAL_SCORE_FEATURE_REGISTRY_VERSION,
    GOAL_SCORE_SCHEMA_VERSION,
    FeatureStatus,
    GoalScoreError,
    TrainingRow,
    validate_evaluation_contract,
)
from domain._goal_score_training_sources import (
    ReadOnlyCorpus,
    _assert_no_active_companions,
    _extract_features,
    _extract_target,
    _parse_canonical_payload,
    _target_identity,
    _validate_cross_lineage,
    file_sha256,
)

TRAINING_VIEW_DATASET = "athena_goal_score_training_view"
TRAINING_VIEW_SCHEMA_VERSION = 1
TRAINING_VIEW_GENERATION_CONTRACT_VERSION = 1
SOURCE_COMPATIBILITY_POLICY_ID = "EXACT_THREE_CORPUS_SHA_AND_FROZEN_META_BINDING_V1"
TRAINING_ROW_ISSUANCE_POLICY_ID = "SOURCE_REPLAYED_CANONICAL_ROWS_ONLY_V1"
TARGET_JOIN_POLICY_ID = "EXACT_MATCH_KEY_DATE_COMPETITION_SCOPE_V1"
OUTPUT_POLICY_ID = "SEPARATE_EXCLUSIVE_TEMP_ATOMIC_REPLACE_V1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def training_view_contract_payload(evaluation_contract_sha256: str) -> dict[str,Any]:
    return {
        "schema_version":TRAINING_VIEW_SCHEMA_VERSION,
        "goal_score_schema_version":GOAL_SCORE_SCHEMA_VERSION,
        "goal_score_feature_registry_version":GOAL_SCORE_FEATURE_REGISTRY_VERSION,
        "goal_score_evaluation_contract_sha256":evaluation_contract_sha256,
        "source_compatibility_policy_id":SOURCE_COMPATIBILITY_POLICY_ID,
        "training_row_issuance_policy_id":TRAINING_ROW_ISSUANCE_POLICY_ID,
        "target_join_policy_id":TARGET_JOIN_POLICY_ID,
        "output_policy_id":OUTPUT_POLICY_ID,
    }


def calculate_training_view_contract_sha256(evaluation_contract_sha256:str,version:int=TRAINING_VIEW_GENERATION_CONTRACT_VERSION)->str:
    return hashlib.sha256(_canonical_bytes({"version":version,"semantics":training_view_contract_payload(evaluation_contract_sha256)})).hexdigest()


EXPECTED_TRAINING_VIEW_GENERATION_CONTRACT_SHA256_BY_VERSION:Mapping[int,str]=MappingProxyType({
    1:"dc7d58e1fec2f7a27f6bb8cb8dd2849ebb6b65f0d2185c76c4ac10b5d1c4455d"
})


def validate_training_view_contract()->tuple[str,str,str,str]:
    feature_sha,model_sha,evaluation_sha=validate_evaluation_contract()
    actual=calculate_training_view_contract_sha256(evaluation_sha)
    expected=EXPECTED_TRAINING_VIEW_GENERATION_CONTRACT_SHA256_BY_VERSION.get(TRAINING_VIEW_GENERATION_CONTRACT_VERSION)
    if expected is None or actual!=expected:
        raise GoalScoreError("Goal/Score training-view generation contract drift")
    return feature_sha,model_sha,evaluation_sha,actual


def _create_output(path:Path)->sqlite3.Connection:
    conn=sqlite3.connect(path);conn.executescript("""
    PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;
    CREATE TABLE corpus_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE training_rows(
      match_key TEXT PRIMARY KEY,match_date TEXT NOT NULL,scope TEXT NOT NULL,
      competition_key TEXT,season TEXT,home_goals INTEGER NOT NULL,away_goals INTEGER NOT NULL,
      canonical_sha256 TEXT NOT NULL,payload_json TEXT NOT NULL
    );
    CREATE INDEX idx_goal_score_training_date ON training_rows(match_date,match_key);
    """);return conn


def _protected(path:Path)->set[Path]:
    p=path.resolve();return {p,*(Path(str(p)+s) for s in ("-wal","-journal","-shm"))}


def _assert_no_output_companions(output:Path)->None:
    for suffix in ("-wal","-journal","-shm"):
        if Path(str(output)+suffix).exists():
            raise GoalScoreError(f"unsafe output SQLite companion exists: {output.name}{suffix}")


def _temporary(output:Path,protected:set[Path])->Path:
    for _ in range(100):
        candidate=output.with_name(f".{output.name}.{secrets.token_hex(12)}.tmp").resolve()
        if candidate in protected or candidate.exists():continue
        fd=os.open(candidate,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd);return candidate
    raise GoalScoreError("unable to allocate exclusive training-view temporary")


def _row_payload(*,match_key:str,match_date:str,scope:str,competition_key:str|None,season:str|None,home_goals:int,away_goals:int,features:Mapping[str,tuple[FeatureStatus,float|None]],source_ids:Mapping[str,str],contract_ids:Mapping[str,str])->dict[str,Any]:
    return {
      "dataset":TRAINING_VIEW_DATASET,"schema_version":TRAINING_VIEW_SCHEMA_VERSION,
      "match_key":match_key,"match_date":match_date,"scope":scope,"competition_key":competition_key,"season":season,
      "target":{"home_goals":home_goals,"away_goals":away_goals},
      "features":{k:{"status":s.value,"value":v} for k,(s,v) in sorted(features.items())},
      "source_identities":dict(sorted(source_ids.items())),"contract_identities":dict(sorted(contract_ids.items())),
      "authority_flags":dict(AUTHORITY_FLAGS),
    }


def build_goal_score_training_view(asof_path:Path,tactical_path:Path,coverage_path:Path,output_path:Path,*,replace:bool=False,competition:str|None=None,start_date:str|None=None,end_date:str|None=None,limit:int|None=None)->int:
    output=Path(output_path).resolve();paths=[Path(p).resolve() for p in (asof_path,tactical_path,coverage_path)]
    protected=set().union(*(_protected(p) for p in paths))
    operational=(Path(__file__).resolve().parents[1]/"database"/"athena.db").resolve();protected|=_protected(operational)
    if output in protected:raise GoalScoreError("training-view output collides with protected SQLite source")
    _assert_no_output_companions(output)
    if output.exists() and not replace:raise GoalScoreError("training-view output exists; pass --replace")
    if limit is not None and limit<1:raise GoalScoreError("limit must be positive")
    if start_date is not None and end_date is not None and start_date>end_date:raise GoalScoreError("start-date must not exceed end-date")
    output.parent.mkdir(parents=True,exist_ok=True);temp=_temporary(output,protected)
    feature_sha,model_sha,evaluation_sha,training_contract_sha=validate_training_view_contract();count=0
    try:
      with ReadOnlyCorpus(paths[0],"ASOF") as asof,ReadOnlyCorpus(paths[1],"TACTICAL") as tactical,ReadOnlyCorpus(paths[2],"COVERAGE") as coverage:
        warehouse_sha=_validate_cross_lineage(asof,tactical,coverage)
        conn=sqlite3.connect(":memory:",uri=True);conn.row_factory=sqlite3.Row
        try:
          conn.execute("ATTACH DATABASE ? AS a",(f"{asof.path.as_uri()}?mode=ro",));conn.execute("ATTACH DATABASE ? AS t",(f"{tactical.path.as_uri()}?mode=ro",));conn.execute("ATTACH DATABASE ? AS c",(f"{coverage.path.as_uri()}?mode=ro",))
          query="""SELECT c.match_key,c.match_date,c.scope,c.competition_key,c.season,c.canonical_sha256 coverage_sha,c.payload_json coverage_payload,a.canonical_sha256 asof_sha,a.payload_json asof_payload,t.canonical_sha256 tactical_sha,t.payload_json tactical_payload FROM c.match_evidence_coverage c JOIN a.historical_asof_snapshots a ON a.match_key=c.match_key JOIN t.tactical_identity_snapshots t ON t.match_key=c.match_key WHERE 1=1"""
          params=[]
          if competition is not None:query+=" AND c.competition_key=?";params.append(competition)
          if start_date is not None:query+=" AND c.match_date>=?";params.append(start_date)
          if end_date is not None:query+=" AND c.match_date<=?";params.append(end_date)
          query+=" ORDER BY c.match_date,c.match_key"
          if limit is not None:query+=" LIMIT ?";params.append(limit)
          dest=_create_output(temp)
          try:
            meta={"dataset":TRAINING_VIEW_DATASET,"schema_version":TRAINING_VIEW_SCHEMA_VERSION,"source_asof_corpus_sha256":asof.sha256,"source_tactical_corpus_sha256":tactical.sha256,"source_coverage_corpus_sha256":coverage.sha256,"source_warehouse_sha256":warehouse_sha,"goal_score_feature_registry_version":GOAL_SCORE_FEATURE_REGISTRY_VERSION,"goal_score_feature_registry_sha256":feature_sha,"goal_score_model_registry_sha256":model_sha,"goal_score_evaluation_contract_sha256":evaluation_sha,"training_view_generation_contract_version":TRAINING_VIEW_GENERATION_CONTRACT_VERSION,"training_view_generation_contract_sha256":training_contract_sha,"authority_flags":dict(AUTHORITY_FLAGS)}
            dest.executemany("INSERT INTO corpus_meta VALUES(?,?)",[(k,json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)) for k,v in sorted(meta.items())])
            source_ids={"asof_corpus_sha256":asof.sha256,"tactical_corpus_sha256":tactical.sha256,"coverage_corpus_sha256":coverage.sha256,"warehouse_sha256":warehouse_sha}
            contract_ids={"feature_registry_sha256":feature_sha,"model_registry_sha256":model_sha,"evaluation_contract_sha256":evaluation_sha,"training_view_contract_sha256":training_contract_sha}
            for row in conn.execute(query,params):
              ap=_parse_canonical_payload(row["asof_payload"],row["asof_sha"],"as-of");tp=_parse_canonical_payload(row["tactical_payload"],row["tactical_sha"],"Tactical");cp=_parse_canonical_payload(row["coverage_payload"],row["coverage_sha"],"coverage")
              identities=(_target_identity(ap,"ASOF"),_target_identity(tp,"TACTICAL"),_target_identity(cp,"COVERAGE"))
              if not identities[0]==identities[1]==identities[2]:raise GoalScoreError("three-corpus target identity mismatch")
              hg,ag=_extract_target(cp);features=_extract_features(ap,tp)
              payload=_row_payload(match_key=row["match_key"],match_date=row["match_date"],scope=row["scope"],competition_key=row["competition_key"],season=row["season"],home_goals=hg,away_goals=ag,features=features,source_ids={**source_ids,"asof_row_sha256":row["asof_sha"],"tactical_row_sha256":row["tactical_sha"],"coverage_row_sha256":row["coverage_sha"]},contract_ids=contract_ids)
              raw=_canonical_bytes(payload);sha=hashlib.sha256(raw).hexdigest();dest.execute("INSERT INTO training_rows VALUES(?,?,?,?,?,?,?,?,?)",(row["match_key"],row["match_date"],row["scope"],row["competition_key"],row["season"],hg,ag,sha,raw.decode("utf-8")));count+=1
              if count%500==0:dest.commit()
            dest.commit()
          finally:dest.close()
        finally:conn.close()
        asof.assert_unchanged();tactical.assert_unchanged();coverage.assert_unchanged()
      for suffix in ("-wal","-journal","-shm"):
        if Path(str(temp)+suffix).exists():raise GoalScoreError("temporary training-view SQLite companion remains")
      _assert_no_output_companions(output)
      os.replace(temp,output);return count
    finally:
      if temp.exists():temp.unlink()
      for suffix in ("-wal","-journal","-shm"):
        p=Path(str(temp)+suffix)
        if p.exists():p.unlink()


def load_training_rows(path:Path)->tuple[TrainingRow,...]:
    feature_sha,model_sha,evaluation_sha,training_sha=validate_training_view_contract()
    source=Path(path).resolve()
    if not source.is_file(): raise GoalScoreError(f"training view unavailable: {source}")
    _assert_no_active_companions(source);before=source.stat();source_sha=file_sha256(source)
    conn=sqlite3.connect(f"{source.as_uri()}?mode=ro",uri=True);conn.row_factory=sqlite3.Row;conn.execute("PRAGMA query_only=ON")
    try:
      tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
      if not {"corpus_meta","training_rows"}.issubset(tables): raise GoalScoreError("training-view schema mismatch")
      meta={k:json.loads(v) for k,v in conn.execute("SELECT key,value FROM corpus_meta")}
      expected={"dataset":TRAINING_VIEW_DATASET,"schema_version":TRAINING_VIEW_SCHEMA_VERSION,"goal_score_feature_registry_version":GOAL_SCORE_FEATURE_REGISTRY_VERSION,"goal_score_feature_registry_sha256":feature_sha,"goal_score_model_registry_sha256":model_sha,"goal_score_evaluation_contract_sha256":evaluation_sha,"training_view_generation_contract_version":TRAINING_VIEW_GENERATION_CONTRACT_VERSION,"training_view_generation_contract_sha256":training_sha}
      if any(meta.get(k)!=v for k,v in expected.items()): raise GoalScoreError("training-view frozen identity mismatch")
      rows=[];feature_ids={item.feature_id for item in GOAL_SCORE_FEATURE_REGISTRY}
      for record in conn.execute("SELECT * FROM training_rows ORDER BY match_date,match_key"):
        payload=_parse_canonical_payload(record["payload_json"],record["canonical_sha256"],"training-view")
        if payload.get("match_key")!=record["match_key"] or payload.get("match_date")!=record["match_date"]: raise GoalScoreError("training-view row identity mismatch")
        target=payload.get("target");features=payload.get("features")
        if not isinstance(target,dict) or not isinstance(features,dict): raise GoalScoreError("training-view payload incomplete")
        if set(features)!=feature_ids: raise GoalScoreError("training-view feature registry coverage mismatch")
        converted={}
        for key,item in features.items():
          if not isinstance(item,dict): raise GoalScoreError("invalid training-view feature resolution")
          try:status=FeatureStatus(str(item.get("status")))
          except ValueError as exc: raise GoalScoreError("unknown training-view feature status") from exc
          value=item.get("value")
          if status is FeatureStatus.AVAILABLE and (isinstance(value,bool) or not isinstance(value,(int,float))):raise GoalScoreError("invalid AVAILABLE training-view feature")
          converted[key]=(status,None if status is not FeatureStatus.AVAILABLE else float(value))
        rows.append(TrainingRow(match_key=str(record["match_key"]),match_date=str(record["match_date"]),scope=str(record["scope"]),competition_key=record["competition_key"],season=record["season"],home_goals=int(target["home_goals"]),away_goals=int(target["away_goals"]),features=MappingProxyType(converted),canonical_sha256=str(record["canonical_sha256"])))
      _assert_no_active_companions(source);after=source.stat()
      if (after.st_size,after.st_mtime_ns)!=(before.st_size,before.st_mtime_ns) or file_sha256(source)!=source_sha: raise GoalScoreError("training view changed during read")
      return tuple(rows)
    finally: conn.close()


__all__=["EXPECTED_TRAINING_VIEW_GENERATION_CONTRACT_SHA256_BY_VERSION","OUTPUT_POLICY_ID","ReadOnlyCorpus","SOURCE_COMPATIBILITY_POLICY_ID","TARGET_JOIN_POLICY_ID","TRAINING_ROW_ISSUANCE_POLICY_ID","TRAINING_VIEW_DATASET","TRAINING_VIEW_GENERATION_CONTRACT_VERSION","TRAINING_VIEW_SCHEMA_VERSION","build_goal_score_training_view","calculate_training_view_contract_sha256","file_sha256","load_training_rows","validate_training_view_contract"]
