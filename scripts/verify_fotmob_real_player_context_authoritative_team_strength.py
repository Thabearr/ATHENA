"""Verify the exact PR197 real FotMob authoritative team-strength bridge."""

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

from domain.fotmob_real_player_context_authoritative_team_strength import (
    build_reviewed_real_fotmob_authoritative_team_strength_context,
    canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes,
    revalidate_reviewed_real_fotmob_authoritative_team_strength_context,
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
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

    inputs = {
        "campaign_receipt_bytes": _read(source_root, "campaign-receipt.json"),
        "manifest_bytes": _read(source_root, "match-details/manifest.json"),
        "raw_bytes": _read(source_root, "match-details/response.json"),
        "persisted_receipt_bytes": _read(
            source_root, "match-details/persisted-evidence-receipt.json"
        ),
        "structure_assessment_bytes": _read(
            source_root, "match-details/structure-assessment.json"
        ),
    }
    context = build_reviewed_real_fotmob_authoritative_team_strength_context(**inputs)
    context_bytes = canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes(
        context
    )
    rebuilt = revalidate_reviewed_real_fotmob_authoritative_team_strength_context(
        **inputs,
        context=context,
        context_bytes=context_bytes,
    )
    rebuilt_bytes = canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes(
        rebuilt
    )
    if rebuilt_bytes != context_bytes:
        raise SystemExit("authoritative context replay is not byte deterministic")

    context_path = output_root / "reviewed-real-player-context-authoritative-team-strength.json"
    context_path.write_bytes(context_bytes)
    values = {
        item.feature_id.value: item.value
        for item in context.candidate.features
        if item.feature_id.value in context.authorized_feature_ids
    }
    proof = {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-real-player-context-authoritative-team-strength-proof-v1",
        "repository_head_sha": repository_head_sha,
        "fixture_identifier": context.fixture_identifier,
        "source_match_id": context.source_match_id,
        "source_raw_sha256": context.source_raw_sha256,
        "source_structure_sha256": context.source_structure_sha256,
        "source_pr193_admission_sha256": context.source_pr193_admission_sha256,
        "source_pr194_handoff_sha256": context.source_pr194_handoff_sha256,
        "source_pr194_candidate_sha256": context.source_pr194_candidate_sha256,
        "source_pr65_artifact_sha256": context.source_pr65_artifact_sha256,
        "source_pr66_handoff_sha256": context.source_pr66_handoff_sha256,
        "source_fixture_intelligence_snapshot_sha256": context.source_fixture_intelligence_snapshot_sha256,
        "source_model_feature_snapshot_sha256": context.source_model_feature_snapshot_sha256,
        "context_sha256": _sha(context_bytes),
        "context_size": len(context_bytes),
        "authorized_feature_ids": list(context.authorized_feature_ids),
        "authorized_feature_values": values,
        "source_state_fresh_until": context.source_state_fresh_until.isoformat().replace(
            "+00:00", "Z"
        ),
        "authority": dict(context.authority),
        "same_raw_pr52_to_pr66_lineage_verified": True,
        "exact_pr193_pr194_source_replay_verified": True,
    }
    (output_root / "proof-receipt.json").write_bytes(_canonical(proof))

    print(f"fixture={context.fixture_identifier}")
    print(f"context_sha256={_sha(context_bytes)}")
    print(f"source_pr65_artifact_sha256={context.source_pr65_artifact_sha256}")
    print(f"source_pr66_handoff_sha256={context.source_pr66_handoff_sha256}")
    print("authorized_feature_ids=" + ",".join(context.authorized_feature_ids))
    for key in sorted(values):
        print(f"{key}={values[key]}")
    print("same_raw_pr52_to_pr66_lineage_verified=true")
    print("team_strength_feature_authorized=true")
    print("prospective_reuse_after_source_freshness_authorized=false")
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
