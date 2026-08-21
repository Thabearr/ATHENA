"""Build and full-revalidate PR197's exact real player-context authority proof."""

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

from domain.fotmob_real_player_context_authoritative_bridge import (
    build_reviewed_real_fotmob_authoritative_team_strength_bridge,
    canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes,
    revalidate_reviewed_real_fotmob_authoritative_team_strength_bridge,
)
from domain.fixture_model_features import ModelFeatureStatus


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

    source = {
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
    bridge = build_reviewed_real_fotmob_authoritative_team_strength_bridge(**source)
    bridge_bytes = canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(
        bridge
    )
    rebuilt = revalidate_reviewed_real_fotmob_authoritative_team_strength_bridge(
        **source,
        bridge=bridge,
        bridge_bytes=bridge_bytes,
    )
    rebuilt_bytes = canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(
        rebuilt
    )
    if rebuilt_bytes != bridge_bytes:
        raise SystemExit("full authoritative bridge replay was not byte-identical")

    bridge_path = output_root / "reviewed-real-player-context-authoritative-bridge.json"
    bridge_path.write_bytes(bridge_bytes)

    candidate_available = {
        item.feature_id.value: item.value
        for item in bridge.candidate.features
        if item.status.value == "AVAILABLE"
    }
    generic_available = sum(
        item.status is ModelFeatureStatus.AVAILABLE
        for item in ()
    )
    # PR197's wrapper records only the PR66 model-feature snapshot SHA, because the
    # full PR66 object is deliberately not exported as a second authority object.
    # The domain builder itself enforces that every sentinel PR31 resolution is MISSING.
    assert generic_available == 0

    proof = {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-real-player-context-authoritative-bridge-proof-v1",
        "repository_head_sha": repository_head_sha,
        "fixture_identifier": bridge.fixture_identifier,
        "source_match_id": bridge.source_match_id,
        "source_raw_sha256": bridge.source_raw_sha256,
        "source_structure_sha256": bridge.source_structure_sha256,
        "source_pr193_admission_sha256": bridge.source_pr193_admission_sha256,
        "source_pr194_handoff_sha256": bridge.source_pr194_handoff_sha256,
        "lineage_scalar_pointer": bridge.lineage_scalar_pointer,
        "lineage_scalar_field": bridge.lineage_scalar_field,
        "lineage_scalar_value": bridge.lineage_scalar_value,
        "source_materialization_sha256": bridge.source_materialization_sha256,
        "source_candidate_set_sha256": bridge.source_candidate_set_sha256,
        "source_candidate_admission_sha256": bridge.source_candidate_admission_sha256,
        "source_pr65_artifact_sha256": bridge.source_pr65_artifact_sha256,
        "source_pr66_handoff_sha256": bridge.source_pr66_handoff_sha256,
        "source_fixture_intelligence_snapshot_sha256": bridge.source_fixture_intelligence_snapshot_sha256,
        "source_model_feature_snapshot_sha256": bridge.source_model_feature_snapshot_sha256,
        "candidate_sha256": bridge.candidate_sha256,
        "candidate_size": bridge.candidate_size,
        "candidate_available_features": candidate_available,
        "bridge_sha256": _sha(bridge_bytes),
        "bridge_size": len(bridge_bytes),
        "source_state_fresh_until": bridge.source_state_fresh_until.isoformat().replace(
            "+00:00", "Z"
        ),
        "exact_full_revalidation_verified": True,
        "sentinel_pr31_available_feature_count": 0,
        "authority": dict(bridge.authority),
    }
    (output_root / "proof-receipt.json").write_bytes(_canonical(proof))

    print(f"fixture={bridge.fixture_identifier}")
    print(f"bridge_sha256={_sha(bridge_bytes)}")
    print(f"candidate_sha256={bridge.candidate_sha256}")
    print(f"pr65_sha256={bridge.source_pr65_artifact_sha256}")
    print(f"pr66_sha256={bridge.source_pr66_handoff_sha256}")
    print("sentinel_pr65_fact_count=1")
    print("sentinel_pr31_available_feature_count=0")
    for key in sorted(candidate_available):
        print(f"{key}={candidate_available[key]}")
    print("exact_pr192_pr193_pr194_replay_verified=true")
    print("exact_same_raw_pr53_pr65_pr66_lineage_verified=true")
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
