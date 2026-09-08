"""Offline CLI for the Current Shadow Elo expectation comparison."""
import argparse
import json
from pathlib import Path
from domain.current_shadow_elo_expectation_challenger import canonical_bytes, compare_elo_replays, validate_report

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--baseline-projection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.history.read_bytes().splitlines() if line]
    report = compare_elo_replays(rows=rows, expected_baseline_projection_raw=args.baseline_projection.read_bytes())
    validate_report(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(report))
    return 0

if __name__ == "__main__": raise SystemExit(main())
