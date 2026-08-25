#!/usr/bin/env python3
"""Build a separate, offline Tactical Identity research corpus."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.tactical_identity import build_tactical_identity_corpus  # noqa: E402

DEFAULT_ASOF = ROOT / "data" / "history_features" / "athena_history_asof_features.db"
DEFAULT_WAREHOUSE = ROOT / "database" / "athena_history.db"
DEFAULT_OUTPUT = ROOT / "data" / "history_features" / "athena_tactical_identity.db"


def build_tactical_corpus(
    asof_corpus_path: Path,
    warehouse_path: Path,
    output_path: Path,
    *,
    competition: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    replace: bool = False,
) -> int:
    return build_tactical_identity_corpus(
        asof_corpus_path,
        warehouse_path,
        output_path,
        competition=competition,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        replace=replace,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof-corpus", type=Path, default=DEFAULT_ASOF)
    parser.add_argument("--warehouse", type=Path, default=DEFAULT_WAREHOUSE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--competition")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    print(build_tactical_corpus(
        args.asof_corpus,
        args.warehouse,
        args.output,
        competition=args.competition,
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
        replace=args.replace,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
