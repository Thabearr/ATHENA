"""Build the exact PR #193 real FotMob player-context semantic admission proof."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import hashlib
import json
from pathlib import Path

from domain.fotmob_real_player_context_array_admission import (
    SOURCE_ARTIFACT_DIGEST,
    SOURCE_ARTIFACT_ID,
    SOURCE_ARTIFACT_NAME,
    SOURCE_ARTIFACT_SIZE,
    SOURCE_REPOSITORY_HEAD_SHA,
    SOURCE_WORKFLOW_RUN_ID,
    build_reviewed_real_fotmob_player_context_admission,
    canonical_reviewed_real_fotmob_player_context_admission_bytes,
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read(root: Path, relative: str) -> bytes:
    base = root.resolve(strict=True)
    path = (base / relative).resolve(strict=True)
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise SystemExit(f"source evidence path escaped artifact root: {relative}") from exc
    raw = path.read_bytes()
    if not raw:
        raise SystemExit(f"source evidence file is empty: {relative}")
    return raw


def run(*, source_root: Path, output_root: Path, repository_head_sha: str) -> None:
    if (
        type(repository_head_sha) is not str
        or len(repository_head_sha) != 40
        or any(ch not in "0123456789abcdef" for ch in repository_head_sha)
    ):
        raise SystemExit("repository head must be full lowercase Git SHA")
    if output_root.exists():
        raise SystemExit("output root already exists; proof replay must be write-once")
    output_root.mkdir(parents=True)

    admission = build_reviewed_real_fotmob_player_context_admission(
        campaign_receipt_bytes=_read(source_root, "campaign-receipt.json"),
        manifest_bytes=_read(source_root, "match-details/manifest.json"),
        raw_bytes=_read(source_root, "match-details/response.json"),
        persisted_receipt_bytes=_read(source_root, "match-details/persisted-evidence-receipt.json"),
        structure_assessment_bytes=_read(source_root, "match-details/structure-assessment.json"),
    )
    admission_bytes = canonical_reviewed_real_fotmob_player_context_admission_bytes(admission)
    (output_root / "reviewed-real-player-context-admission.json").write_bytes(admission_bytes)

    set_counts = {
        f"{item.team_side.value}:{item.scope.value}": item.record_count
        for item in admission.record_sets
    }
    proof = {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-real-player-context-array-admission-proof-v1",
        "repository_head_sha": repository_head_sha,
        "source_pr_number": 192,
        "source_repository_head_sha": SOURCE_REPOSITORY_HEAD_SHA,
        "source_workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_artifact_name": SOURCE_ARTIFACT_NAME,
        "source_artifact_size": SOURCE_ARTIFACT_SIZE,
        "source_artifact_digest": SOURCE_ARTIFACT_DIGEST,
        "fixture_identifier": admission.fixture_identifier,
        "source_match_id": admission.source_match_id,
        "raw_sha256": admission.raw_sha256,
        "structure_sha256": admission.structure_sha256,
        "admission_sha256": _sha(admission_bytes),
        "admission_size": len(admission_bytes),
        "record_count": len(admission.records),
        "record_set_counts": set_counts,
        "bench_evidence_status": dict(admission.bench_evidence_status),
        "authority": dict(admission.authority),
    }
    (output_root / "proof-receipt.json").write_bytes(_canonical(proof))

    print(f"fixture={admission.fixture_identifier}")
    print(f"admission_sha256={_sha(admission_bytes)}")
    print(f"admission_size={len(admission_bytes)}")
    print(f"record_count={len(admission.records)}")
    for key in sorted(set_counts):
        print(f"{key}={set_counts[key]}")
    print("array_semantics_authorized=true")
    print("team_strength_feature_authorized=false")
    print("probability_pricing_selection_bet_authorized=false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--repository-head-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(
        source_root=args.source_root,
        output_root=args.output_root,
        repository_head_sha=args.repository_head_sha,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
