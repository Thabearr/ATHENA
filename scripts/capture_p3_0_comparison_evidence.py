#!/usr/bin/env python3
"""Explicit offline packager for P3.0 prospective comparison evidence.

This command consumes only a caller-provided observation document.  It does not
import ATHENA application/provider modules, acquire a source, run Current
Shadow, execute a legacy prediction, or create delivery activity.  The future
post-merge collection operation is responsible for obtaining observations via
reviewed boundaries and passing their non-sensitive projections here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from domain import p3_0_comparison_evidence as evidence


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="explicit JSON capture observation")
    parser.add_argument("--output-directory", required=True, type=Path, help="new artifact directory")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        value = evidence.load_json_bytes(args.input.read_bytes())
        if type(value) is not dict:
            raise evidence.P30ComparisonEvidenceError("capture input must be a JSON object")
        bundle = evidence.build_capture_bundle(**value)
        destination = evidence.write_capture_artifact(bundle, args.output_directory)
        print(f"P3_0_COMPARISON_EVIDENCE_CAPTURED {bundle['canonical_sha256']} {destination}")
        return 0
    except (OSError, evidence.P30ComparisonEvidenceError, TypeError) as exc:
        print(f"P3_0_COMPARISON_EVIDENCE_FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
