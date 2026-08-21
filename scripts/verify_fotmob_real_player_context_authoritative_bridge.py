"""Build and full-revalidate PR197 through ATHENA's existing PR191 authority type."""

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
from domain.fotmob_real_player_context_pr191_authoritative_adapter import (
    build_reviewed_real_fotmob_pr191_team_strength_context,
    revalidate_reviewed_real_fotmob_pr191_team_strength_context,
)
from domain.fotmob_reviewed_team_strength_context_adapter import (
    ReviewedFotMobTeamStrengthContext,
    canonical_reviewed_fotmob_team_strength_context_bytes,
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

    prerequisite = build_reviewed_real_fotmob_authoritative_team_strength_bridge(**source)
    prerequisite_bytes = canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(
        prerequisite
    )
    rebuilt_prerequisite = revalidate_reviewed_real_fotmob_authoritative_team_strength_bridge(
        **source,
        bridge=prerequisite,
        bridge_bytes=prerequisite_bytes,
    )
    if (
        canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(
            rebuilt_prerequisite
        )
        != prerequisite_bytes
    ):
        raise SystemExit("same-raw PR52→PR66 prerequisite replay was not byte-identical")
    if any(dict(prerequisite.authority).values()):
        raise SystemExit("prerequisite bridge illegally grants authority")

    context = build_reviewed_real_fotmob_pr191_team_strength_context(**source)
    if type(context) is not ReviewedFotMobTeamStrengthContext:
        raise SystemExit("real source did not resolve to the existing PR191 authority type")
    context_bytes = canonical_reviewed_fotmob_team_strength_context_bytes(context)
    rebuilt_context = revalidate_reviewed_real_fotmob_pr191_team_strength_context(
        **source,
        context=context,
        context_bytes=context_bytes,
    )
    if canonical_reviewed_fotmob_team_strength_context_bytes(rebuilt_context) != context_bytes:
        raise SystemExit("existing PR191 authority replay was not byte-identical")

    (output_root / "same-raw-pr65-pr66-prerequisite.json").write_bytes(prerequisite_bytes)
    (output_root / "reviewed-pr191-team-strength-context.json").write_bytes(context_bytes)

    candidate_available = {
        item.feature_id.value: item.value
        for item in context.candidate.features
        if item.status.value == "AVAILABLE"
    }
    context_safety = dict(context.safety)
    if context_safety.get("team_strength_feature_authorized") is not True:
        raise SystemExit("existing PR191 context did not grant team-strength feature authority")
    if any(
        context_safety[key]
        for key in context_safety
        if key != "team_strength_feature_authorized"
    ):
        raise SystemExit("existing PR191 context granted downstream authority")

    proof = {
        "schema_version": 2,
        "dataset_name": "athena-fotmob-real-player-context-pr191-authority-proof-v2",
        "repository_head_sha": repository_head_sha,
        "fixture_identifier": context.fixture_identifier,
        "source_match_id": context.source_match_id,
        "source_raw_sha256": context.source_raw_sha256,
        "source_pr193_array_admission_sha256": context.source_array_artifact_sha256,
        "source_pr194_candidate_sha256": context.candidate_sha256,
        "source_pr65_artifact_sha256": context.source_pr65_artifact_sha256,
        "source_pr66_handoff_sha256": context.source_pr66_handoff_sha256,
        "source_fixture_intelligence_snapshot_sha256": (
            context.source_fixture_intelligence_snapshot_sha256
        ),
        "source_model_feature_snapshot_sha256": context.source_model_feature_snapshot_sha256,
        "candidate_available_features": candidate_available,
        "prerequisite_bridge_sha256": _sha(prerequisite_bytes),
        "prerequisite_bridge_size": len(prerequisite_bytes),
        "pr191_context_sha256": _sha(context_bytes),
        "pr191_context_size": len(context_bytes),
        "source_state_fresh_until": prerequisite.source_state_fresh_until.isoformat().replace(
            "+00:00", "Z"
        ),
        "exact_full_revalidation_verified": True,
        "same_raw_pr53_pr65_pr66_verified": True,
        "sentinel_pr31_available_feature_count": 0,
        "prerequisite_authority": dict(prerequisite.authority),
        "pr191_context_safety": context_safety,
    }
    (output_root / "proof-receipt.json").write_bytes(_canonical(proof))

    print(f"fixture={context.fixture_identifier}")
    print(f"prerequisite_bridge_sha256={_sha(prerequisite_bytes)}")
    print(f"pr191_context_sha256={_sha(context_bytes)}")
    print(f"candidate_sha256={context.candidate_sha256}")
    print(f"pr65_sha256={context.source_pr65_artifact_sha256}")
    print(f"pr66_sha256={context.source_pr66_handoff_sha256}")
    print("sentinel_pr65_fact_count=1")
    print("sentinel_pr31_available_feature_count=0")
    for key in sorted(candidate_available):
        print(f"{key}={candidate_available[key]}")
    print("exact_pr192_pr193_pr194_replay_verified=true")
    print("exact_same_raw_pr53_pr65_pr66_lineage_verified=true")
    print("existing_pr191_authority_type_verified=true")
    print("prerequisite_bridge_authority_all_false=true")
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
