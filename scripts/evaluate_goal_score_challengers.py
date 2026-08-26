#!/usr/bin/env python3
"""Run ATHENA Goal/Score Dynamics v2 offline challengers on a canonical training view."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy
import scipy
import sklearn

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from domain.goal_score_dynamics import (
    AUTHORITY_FLAGS,FULL_CORPUS_EVALUATION_STATUS,GOAL_SCORE_FEATURE_REGISTRY_VERSION,
    GOAL_SCORE_MODEL_REGISTRY_VERSION,LIVE_CHAMPION_REPLAY_STATUS,RANDOM_SEED,
    evaluate_challengers,validate_evaluation_contract,
)
from domain.goal_score_training_view import file_sha256,load_training_rows,validate_training_view_contract


def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-view",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--competition");parser.add_argument("--start-date");parser.add_argument("--end-date");parser.add_argument("--limit",type=int)
    args=parser.parse_args()
    rows=list(load_training_rows(args.training_view));subset=False
    if args.competition is not None: rows=[r for r in rows if r.competition_key==args.competition];subset=True
    if args.start_date is not None: rows=[r for r in rows if r.match_date>=args.start_date];subset=True
    if args.end_date is not None: rows=[r for r in rows if r.match_date<=args.end_date];subset=True
    if args.limit is not None: rows=rows[:args.limit];subset=True
    if not rows: raise SystemExit("no eligible Goal/Score training rows")
    feature_sha,model_sha,evaluation_sha=validate_evaluation_contract();_,_,_,training_contract_sha=validate_training_view_contract()
    result=evaluate_challengers(rows)
    receipt={
      "dataset":"athena_goal_score_challenger_experiment","experiment_scope":"SUBSET" if subset else "FULL_TRAINING_VIEW",
      "training_view_sha256":file_sha256(args.training_view),"training_view_generation_contract_sha256":training_contract_sha,
      "feature_registry_version":GOAL_SCORE_FEATURE_REGISTRY_VERSION,"feature_registry_sha256":feature_sha,
      "model_registry_version":GOAL_SCORE_MODEL_REGISTRY_VERSION,"model_registry_sha256":model_sha,
      "evaluation_contract_sha256":evaluation_sha,"python_version":platform.python_version(),"numpy_version":numpy.__version__,
      "scipy_version":scipy.__version__,"scikit_learn_version":sklearn.__version__,"random_seed":RANDOM_SEED,
      "live_champion_replay_status":LIVE_CHAMPION_REPLAY_STATUS,"full_corpus_source_environment_status":FULL_CORPUS_EVALUATION_STATUS,
      "result":result,"authority_flags":dict(AUTHORITY_FLAGS),
    }
    raw=canonical_bytes(receipt);receipt["receipt_sha256"]=hashlib.sha256(raw).hexdigest()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    path=args.output_dir/"goal_score_experiment_receipt.json"
    path.write_text(json.dumps(receipt,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print(path);return 0

if __name__=="__main__": raise SystemExit(main())
