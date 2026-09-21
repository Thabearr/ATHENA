"""ATHENA P3.0 Legacy/Canonical Architecture Comparison Report Builder.

Builds deterministic artifacts:
- artifacts/p3-0-replay-acceptance-decision-v1.json
- artifacts/p3-0-comparator-corpus-v1.json
- artifacts/p3-0-comparison-report-v1.json

Verifies deterministic, byte-identical output across repeated generation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from domain import p3_0_legacy_canonical_comparator as comparator
from domain.p3_0_replay_corpus import canonical_json_bytes, canonical_sha256


def _load_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise comparator.ComparatorError(f"{path} must contain a JSON object")
    return value


def build_all(
    *,
    repository_root: Path,
    output_decision: Path,
    output_corpus: Path,
    output_report: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_audit_path = repository_root / "artifacts" / "p3-0-replay-source-audit-v1.json"
    proposal_path = repository_root / "artifacts" / "p3-0-replay-acceptance-amendment-proposal-v1.json"
    p0_cases_path = (
        repository_root
        / "tests"
        / "fixtures"
        / "architecture"
        / "legacy_market_selection_cases_v1.json"
    )

    source_audit = _load_json(source_audit_path)
    proposal = _load_json(proposal_path)
    p0_payload = _load_json(p0_cases_path)
    p0_cases = p0_payload.get("cases", [])

    # 1. Build decision
    decision = comparator.build_acceptance_decision()
    comparator.validate_acceptance_decision(decision)

    # 2. Build corpus
    corpus = comparator.build_comparator_corpus(
        decision_sha256=decision["canonical_sha256"],
    )
    comparator.validate_comparator_corpus(
        corpus, expected_decision_sha=decision["canonical_sha256"]
    )

    # 3. Build comparison report
    report = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=decision,
        corpus=corpus,
        p0_cases=p0_cases,
    )
    comparator.validate_comparison_report(report)

    # Write files
    comparator.write_json_artifact(output_decision, decision)
    comparator.write_json_artifact(output_corpus, corpus)
    comparator.write_json_artifact(output_report, report)

    return decision, corpus, report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--decision-output",
        type=Path,
        default=Path("artifacts/p3-0-replay-acceptance-decision-v1.json"),
    )
    parser.add_argument(
        "--corpus-output",
        type=Path,
        default=Path("artifacts/p3-0-comparator-corpus-v1.json"),
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("artifacts/p3-0-comparison-report-v1.json"),
    )
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]

    d1, c1, r1 = build_all(
        repository_root=repo_root,
        output_decision=args.decision_output,
        output_corpus=args.corpus_output,
        output_report=args.report_output,
    )

    # Second pass for deterministic byte-identical verification
    d2 = comparator.build_acceptance_decision()
    c2 = comparator.build_comparator_corpus(decision_sha256=d2["canonical_sha256"])
    source_audit = _load_json(repo_root / "artifacts" / "p3-0-replay-source-audit-v1.json")
    proposal = _load_json(
        repo_root / "artifacts" / "p3-0-replay-acceptance-amendment-proposal-v1.json"
    )
    p0_cases = _load_json(
        repo_root
        / "tests"
        / "fixtures"
        / "architecture"
        / "legacy_market_selection_cases_v1.json"
    ).get("cases", [])
    r2 = comparator.build_comparison_report(
        source_audit=source_audit,
        proposal=proposal,
        decision=d2,
        corpus=c2,
        p0_cases=p0_cases,
    )

    if canonical_json_bytes(d1) != canonical_json_bytes(d2):
        raise comparator.ComparatorError("Decision artifact not deterministic across runs")
    if canonical_json_bytes(c1) != canonical_json_bytes(c2):
        raise comparator.ComparatorError("Corpus artifact not deterministic across runs")
    if canonical_json_bytes(r1) != canonical_json_bytes(r2):
        raise comparator.ComparatorError("Report artifact not deterministic across runs")

    print(f"DECISION_CANONICAL_SHA256: {d1['canonical_sha256']}")
    print(f"CORPUS_CANONICAL_SHA256: {c1['canonical_sha256']}")
    print(f"REPORT_CANONICAL_SHA256: {r1['canonical_sha256']}")
    print("STATUS: P3_0_COMPARATOR_REPORT_BUILT_AND_DETERMINISTIC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
