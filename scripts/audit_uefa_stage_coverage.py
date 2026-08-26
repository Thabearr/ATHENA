#!/usr/bin/env python3
"""Audit source-qualified UEFA stage coverage in ATHENA historical research."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.uefa_competition_stage import (  # noqa: E402
    EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256,
    EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256,
    EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256,
    project_warehouse_uefa_stages,
    stage_coverage_report,
    training_view_stage_join_report,
    validate_training_sidecar_contract,
    validate_uefa_stage_contract,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--warehouse",
        type=Path,
        default=ROOT / "database" / "athena_history.db",
        help="Exact canonical historical warehouse SQLite file.",
    )
    parser.add_argument(
        "--training-view",
        type=Path,
        help=(
            "Optional frozen Goal/Score training-view SQLite to audit by "
            "the exact reviewed sidecar boundary."
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path for the deterministic JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = arguments()
    parent_sha, registry_sha, contract_sha = validate_uefa_stage_contract()
    sidecar_sha = validate_training_sidecar_contract()
    if args.training_view is None:
        report = stage_coverage_report(
            project_warehouse_uefa_stages(args.warehouse)
        )
    else:
        report = training_view_stage_join_report(
            args.training_view,
            args.warehouse,
        )
    report.update({
        "uefa_parent_identity_sha256": parent_sha,
        "uefa_stage_registry_sha256": registry_sha,
        "uefa_stage_contract_sha256": contract_sha,
        "uefa_training_sidecar_contract_sha256": sidecar_sha,
        "canonical_warehouse_schema_sql_sha256": (
            EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256
        ),
        "goal_score_training_view_contract_sha256": (
            EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256
        ),
    })
    if sidecar_sha != EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256:
        raise RuntimeError("unexpected UEFA training-sidecar identity")
    text = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
