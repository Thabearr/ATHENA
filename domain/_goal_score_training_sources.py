"""Read-only source replay helpers for the Goal/Score training view."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sqlite3
from types import MappingProxyType
from typing import Any, Mapping

from domain.goal_score_dynamics import FeatureStatus, GOAL_SCORE_FEATURE_REGISTRY, GoalScoreError


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_no_active_companions(path:Path)->None:
    for suffix in ("-wal","-journal"):
        companion=Path(str(path)+suffix)
        if companion.exists() and companion.stat().st_size:
            raise GoalScoreError(f"unsafe active SQLite companion: {companion.name}")


class ReadOnlyCorpus:
    def __init__(self,path:Path,kind:str)->None:
        self.path=Path(path).resolve();self.kind=kind
        if not self.path.is_file(): raise GoalScoreError(f"{kind} corpus unavailable: {self.path}")
        _assert_no_active_companions(self.path);self._stat=self.path.stat();self.sha256=file_sha256(self.path);_assert_no_active_companions(self.path)
        self.connection=sqlite3.connect(f"{self.path.as_uri()}?mode=ro",uri=True)
        self.connection.row_factory=sqlite3.Row;self.connection.execute("PRAGMA query_only=ON")
        try:self._validate()
        except Exception:self.close();raise

    def _meta(self)->Mapping[str,Any]:
        try:return MappingProxyType({k:json.loads(v) for k,v in self.connection.execute("SELECT key,value FROM corpus_meta")})
        except Exception as exc: raise GoalScoreError(f"invalid {self.kind} corpus metadata") from exc

    def _validate(self)->None:
        tables={r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected={"ASOF":"historical_asof_snapshots","TACTICAL":"tactical_identity_snapshots","COVERAGE":"match_evidence_coverage"}.get(self.kind)
        if expected is None: raise GoalScoreError(f"unknown Goal/Score source kind: {self.kind}")
        if "corpus_meta" not in tables or expected not in tables: raise GoalScoreError(f"{self.kind} corpus schema mismatch")
        self.meta=self._meta()
        if self.kind=="ASOF":
            from domain.historical_asof_features import (HISTORICAL_ASOF_DATASET,HISTORICAL_ASOF_SCHEMA_VERSION,HISTORICAL_FEATURE_REGISTRY_VERSION,HISTORICAL_GENERATION_CONTRACT_VERSION,validate_historical_feature_registry,validate_historical_generation_contract)
            checks={"dataset":HISTORICAL_ASOF_DATASET,"generation_schema_version":HISTORICAL_ASOF_SCHEMA_VERSION,"feature_registry_version":HISTORICAL_FEATURE_REGISTRY_VERSION,"feature_registry_sha256":validate_historical_feature_registry(),"generation_contract_version":HISTORICAL_GENERATION_CONTRACT_VERSION,"generation_contract_sha256":validate_historical_generation_contract()}
        elif self.kind=="TACTICAL":
            from domain.tactical_identity import (TACTICAL_IDENTITY_DATASET,TACTICAL_IDENTITY_SCHEMA_VERSION,TACTICAL_IDENTITY_REGISTRY_VERSION,TACTICAL_GENERATION_CONTRACT_VERSION,validate_tactical_identity_registry,validate_tactical_generation_contract)
            rsha=validate_tactical_identity_registry();gsha=validate_tactical_generation_contract(tactical_registry_sha256=rsha)
            checks={"dataset":TACTICAL_IDENTITY_DATASET,"schema_version":TACTICAL_IDENTITY_SCHEMA_VERSION,"tactical_registry_version":TACTICAL_IDENTITY_REGISTRY_VERSION,"tactical_registry_sha256":rsha,"tactical_generation_contract_version":TACTICAL_GENERATION_CONTRACT_VERSION,"tactical_generation_contract_sha256":gsha}
        else:
            from domain.historical_training_coverage import (DATASET,SCHEMA_VERSION,MARKET_LABEL_REGISTRY_VERSION,LABEL_GENERATION_CONTRACT_VERSION,validate_contracts)
            rsha,msha,gsha=validate_contracts()
            checks={"dataset":DATASET,"schema_version":SCHEMA_VERSION,"market_label_registry_version":MARKET_LABEL_REGISTRY_VERSION,"market_label_registry_sha256":rsha,"canonical_market_semantics_sha256":msha,"generation_contract_version":LABEL_GENERATION_CONTRACT_VERSION,"generation_contract_sha256":gsha}
        if any(self.meta.get(k)!=v for k,v in checks.items()): raise GoalScoreError(f"{self.kind} frozen corpus identity mismatch")

    def assert_unchanged(self)->None:
        _assert_no_active_companions(self.path);after=self.path.stat()
        if (after.st_size,after.st_mtime_ns)!=(self._stat.st_size,self._stat.st_mtime_ns) or file_sha256(self.path)!=self.sha256: raise GoalScoreError(f"{self.kind} corpus changed during construction")
        _assert_no_active_companions(self.path)

    def close(self)->None:
        if getattr(self,"connection",None) is not None:self.connection.close();self.connection=None

    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def _validate_cross_lineage(asof:ReadOnlyCorpus,tactical:ReadOnlyCorpus,coverage:ReadOnlyCorpus)->str:
    warehouse=asof.meta.get("source_warehouse_sha256")
    if not isinstance(warehouse,str) or not warehouse: raise GoalScoreError("as-of warehouse ancestry missing")
    if tactical.meta.get("source_warehouse_sha256")!=warehouse or coverage.meta.get("source_warehouse_sha256")!=warehouse: raise GoalScoreError("three-corpus warehouse ancestry mismatch")
    if tactical.meta.get("source_asof_corpus_sha256")!=asof.sha256: raise GoalScoreError("Tactical corpus is not bound to supplied as-of corpus")
    if coverage.meta.get("source_asof_corpus_sha256")!=asof.sha256: raise GoalScoreError("#232 coverage corpus is not bound to supplied as-of corpus")
    if coverage.meta.get("source_tactical_corpus_sha256")!=tactical.sha256: raise GoalScoreError("#232 coverage corpus is not bound to supplied Tactical corpus")
    return warehouse


def _parse_canonical_payload(raw:str,expected_sha:str,label:str)->Mapping[str,Any]:
    try:payload=json.loads(raw)
    except Exception as exc:raise GoalScoreError(f"invalid {label} payload") from exc
    canonical=_canonical_bytes(payload)
    if canonical!=raw.encode("utf-8"):raise GoalScoreError(f"noncanonical {label} payload")
    if hashlib.sha256(canonical).hexdigest()!=expected_sha:raise GoalScoreError(f"{label} row identity mismatch")
    return MappingProxyType(payload)


def _resolution_map(payload:Mapping[str,Any],side:str)->dict[tuple[str,str,str],Mapping[str,Any]]:
    key="home_resolutions" if side=="HOME" else "away_resolutions";result={}
    values=payload.get(key)
    if not isinstance(values,list):raise GoalScoreError("historical resolution list missing")
    for item in values:
        if not isinstance(item,dict):raise GoalScoreError("invalid historical resolution")
        identity=(str(item.get("feature_id")),str(item.get("scope")),str(item.get("window")))
        if identity in result:raise GoalScoreError("duplicate historical feature resolution")
        result[identity]=item
    return result


def _source_status_value(item:Mapping[str,Any]|None)->tuple[FeatureStatus,float|None]:
    if item is None:return FeatureStatus.MISSING,None
    try:status=FeatureStatus(str(item.get("status")))
    except ValueError as exc:raise GoalScoreError("unknown upstream feature status") from exc
    value=item.get("value") if "value" in item else item.get("continuous_score")
    if status is FeatureStatus.AVAILABLE:
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)):raise GoalScoreError("AVAILABLE upstream feature lacks finite value")
        return status,float(value)
    return status,None


def _tactical_map(payload:Mapping[str,Any],side:str,scope:str)->dict[str,Mapping[str,Any]]:
    profile=payload.get("home_profile" if side=="HOME" else "away_profile")
    if not isinstance(profile,dict):raise GoalScoreError("Tactical profile missing")
    key="overall_dimensions" if scope=="OVERALL" else "venue_dimensions"
    values=profile.get(key);result={}
    if not isinstance(values,list):raise GoalScoreError("Tactical dimension list missing")
    for item in values:
        if not isinstance(item,dict):raise GoalScoreError("invalid Tactical dimension")
        dimension=str(item.get("dimension_id"))
        if dimension in result:raise GoalScoreError("duplicate Tactical dimension")
        result[dimension]=item
    return result


def _extract_features(asof_payload:Mapping[str,Any],tactical_payload:Mapping[str,Any])->Mapping[str,tuple[FeatureStatus,float|None]]:
    history={side:_resolution_map(asof_payload,side) for side in ("HOME","AWAY")}
    tactical={(side,scope):_tactical_map(tactical_payload,side,scope) for side in ("HOME","AWAY") for scope in ("OVERALL","HOME_ONLY" if side=="HOME" else "AWAY_ONLY")}
    features={}
    for definition in GOAL_SCORE_FEATURE_REGISTRY:
        if definition.upstream_corpus=="HISTORICAL_ASOF":
            item=history[definition.side].get((definition.upstream_feature_id,definition.scope,definition.window))
        elif definition.upstream_corpus=="TACTICAL_IDENTITY":
            item=tactical[(definition.side,definition.scope)].get(definition.upstream_feature_id)
        else:raise GoalScoreError("unreviewed Goal/Score upstream corpus")
        features[definition.feature_id]=_source_status_value(item)
    return MappingProxyType(features)


def _extract_target(coverage_payload:Mapping[str,Any])->tuple[int,int]:
    labels=coverage_payload.get("labels")
    if not isinstance(labels,dict):raise GoalScoreError("#232 canonical labels missing")
    out=[]
    for label in ("HOME_GOALS","AWAY_GOALS"):
        item=labels.get(label)
        if not isinstance(item,dict) or item.get("status")!="AVAILABLE":raise GoalScoreError("training target lacks AVAILABLE canonical regulation score")
        value=item.get("value")
        if isinstance(value,bool) or not isinstance(value,int) or value<0:raise GoalScoreError("invalid canonical regulation-score target")
        out.append(value)
    return out[0],out[1]


def _target_identity(payload:Mapping[str,Any],kind:str)->tuple[Any,...]:
    if kind in {"ASOF","TACTICAL"}:
        target=payload.get("target")
        if not isinstance(target,dict):raise GoalScoreError(f"{kind} target identity missing")
        return target.get("match_key"),target.get("match_date"),target.get("scope"),target.get("competition_key")
    return payload.get("match_key"),payload.get("match_date"),payload.get("scope"),payload.get("competition_key")


__all__=["ReadOnlyCorpus","file_sha256"]
