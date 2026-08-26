#!/usr/bin/env python3
"""Build ATHENA's canonical offline Goal/Score Dynamics v2 training view."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from domain.goal_score_training_view import build_goal_score_training_view

DEFAULT_ASOF=ROOT/"data"/"history_features"/"athena_history_asof_features.db"
DEFAULT_TACTICAL=ROOT/"data"/"history_features"/"athena_tactical_identity.db"
DEFAULT_COVERAGE=ROOT/"data"/"history_features"/"athena_training_coverage_labels.db"
DEFAULT_OUTPUT=ROOT/"data"/"history_features"/"athena_goal_score_training_view.db"

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof-corpus",type=Path,default=DEFAULT_ASOF)
    parser.add_argument("--tactical-corpus",type=Path,default=DEFAULT_TACTICAL)
    parser.add_argument("--coverage-corpus",type=Path,default=DEFAULT_COVERAGE)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--competition");parser.add_argument("--start-date");parser.add_argument("--end-date")
    parser.add_argument("--limit",type=int);parser.add_argument("--replace",action="store_true")
    args=parser.parse_args()
    count=build_goal_score_training_view(args.asof_corpus,args.tactical_corpus,args.coverage_corpus,args.output,replace=args.replace,competition=args.competition,start_date=args.start_date,end_date=args.end_date,limit=args.limit)
    print(count);return 0

if __name__=="__main__": raise SystemExit(main())
