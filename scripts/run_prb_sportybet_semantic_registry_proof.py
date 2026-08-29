"""Bounded anonymous current SportyBet semantic/readiness proof for PR-B.

The command only performs the already-reviewed discovery and event-detail
GETs.  It never creates a share code, reloads a share code, logs in, or sends
an execution request.  The output contains one deterministic 15-market matrix
and every retained source identity used to derive it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from domain import current_sportybet_semantic_registry as semantic


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".cache/athena-research/prb-sportybet-semantic-registry-proof"),
    )
    parser.add_argument("--head-sha", default=None)
    parser.add_argument("--base-sha", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    registry, proof_path = semantic.scan_current_sportybet_semantic_registry(
        repository_root=args.repository_root.resolve(strict=True),
        output_directory=args.output_dir,
        head_sha=args.head_sha,
        base_sha=args.base_sha,
    )
    summary = {
        "dataset_name": registry.dataset_name,
        "policy_id": registry.policy_id,
        "registry_sha256": registry.canonical_sha256,
        "proof_path": proof_path.as_posix(),
        "scan_attempts": registry.scan_attempts,
        "scan_cap": registry.scan_cap,
        "coverage": [
            {
                "market_id": row.market_id.value,
                "provider_status": row.provider_status.value,
                "proven_lines": list(row.proven_lines),
                "blocker": row.blocker,
            }
            for row in registry.coverage
        ],
        "authority": dict(registry.authority),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by hosted proof
    raise SystemExit(main())
