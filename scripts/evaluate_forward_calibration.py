#!/usr/bin/env python3
"""Fit/evaluate ATHENA Phase 6 forward-chaining market calibrators offline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.forward_calibration import (
    FULL_CORPUS_CALIBRATION_STATUS,
    ForwardCalibrationError,
    canonical_calibration_artifact_bytes,
    run_forward_calibration,
)
from domain.goal_score_dynamics import GOAL_SCORE_MODEL_REGISTRY
from domain.goal_score_training_view import file_sha256, load_training_rows


def _atomic_write(path: Path, payload: bytes, *, replace: bool) -> None:
    if path.exists() and not replace:
        raise ForwardCalibrationError(
            f"output exists: {path}; pass --replace to overwrite"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(12)}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-view", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--total-line", type=float, action="append", default=[])
    parser.add_argument("--asian-home-line", type=float, action="append", default=[])
    parser.add_argument("--competition")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    registered = {item.model_id for item in GOAL_SCORE_MODEL_REGISTRY}
    if args.model_id not in registered:
        raise SystemExit(f"unknown Goal/Score model id: {args.model_id}")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.start_date and args.end_date and args.start_date > args.end_date:
        raise SystemExit("--start-date must not exceed --end-date")

    training_view_path = args.training_view.resolve()
    artifact_path = (
        args.output_dir / "forward_calibration_artifact.json"
    ).resolve()
    report_path = (
        args.output_dir / "forward_calibration_evaluation.json"
    ).resolve()
    if training_view_path in {artifact_path, report_path}:
        raise ForwardCalibrationError(
            "calibration output cannot collide with the canonical training view"
        )
    if artifact_path == report_path:
        raise ForwardCalibrationError("calibration outputs must be distinct")

    rows = list(load_training_rows(training_view_path))
    subset = False
    if args.competition is not None:
        rows = [row for row in rows if row.competition_key == args.competition]
        subset = True
    if args.start_date is not None:
        rows = [row for row in rows if row.match_date >= args.start_date]
        subset = True
    if args.end_date is not None:
        rows = [row for row in rows if row.match_date <= args.end_date]
        subset = True
    if args.limit is not None:
        rows = rows[: args.limit]
        subset = True
    if not rows:
        raise SystemExit("no eligible Goal/Score training rows")

    training_view_sha = file_sha256(training_view_path)
    artifact, report = run_forward_calibration(
        rows,
        model_id=args.model_id,
        source_training_view_sha256=training_view_sha,
        total_goal_lines=args.total_line,
        asian_handicap_home_lines=args.asian_home_line,
    )
    report = {
        **report,
        "experiment_scope": "SUBSET" if subset else "FULL_TRAINING_VIEW",
        "full_corpus_source_environment_status": FULL_CORPUS_CALIBRATION_STATUS,
    }

    _atomic_write(
        artifact_path,
        canonical_calibration_artifact_bytes(artifact),
        replace=args.replace,
    )
    _atomic_write(
        report_path,
        (
            json.dumps(
                report,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8"),
        replace=args.replace,
    )
    print(artifact_path)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
