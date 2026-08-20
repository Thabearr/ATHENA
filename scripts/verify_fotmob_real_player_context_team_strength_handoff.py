"""Build the exact PR194 real FotMob player-context team-strength handoff proof."""

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

from domain.fotmob_real_player_context_team_strength_handoff import (
    build_reviewed_real_fotmob_team_strength_handoff,
    canonical_reviewed_real_fotmob_team_strength_handoff_bytes,
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

    handoff = build_reviewed_real_fotmob_team_strength_handoff(
        campaign_receipt_bytes=_read(source_root, "campaign-receipt.json"),
        manifest_bytes=_read(source_root, "match-details/manifest.json"),
        raw_bytes=_read(source_root, "match-details/response.json"),
        persisted_receipt_bytes=_read(
            source_root, "match-details/persisted-evidence-receipt.json"
        ),
        structure_assessment_bytes=_read(
            source_root, "match-details/structure-assessment.json"
        ),
    )
    handoff_bytes = canonical_reviewed_real_fotmob_team_strength_handoff_bytes(handoff)
    (output_root / "reviewed-real-player-context-team-strength-handoff.json").write_bytes(
        handoff_bytes
    )

    feature_status_counts: dict[str, int] = {}
    feature_values: dict[str, float | None] = {}
    for item in handoff.candidate.features:
        feature_status_counts[item.status.value] = feature_status_counts.get(item.status.value, 0) + 1
        if item.feature_id.value in handoff.available_feature_ids:
            feature_values[item.feature_id.value] = item.value

    proof = {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-real-player-context-team-strength-handoff-proof-v1",
        "repository_head_sha": repository_head_sha,
        "fixture_identifier": handoff.fixture_identifier,
        "source_match_id": handoff.source_match_id,
        "source_admission_sha256": handoff.source_admission_sha256,
        "source_raw_sha256": handoff.source_raw_sha256,
        "candidate_sha256": handoff.candidate_sha256,
        "candidate_size": handoff.candidate_size,
        "handoff_sha256": _sha(handoff_bytes),
        "handoff_size": len(handoff_bytes),
        "available_feature_ids": list(handoff.available_feature_ids),
        "available_feature_values": feature_values,
        "feature_status_counts": feature_status_counts,
        "source_state_fresh_until": handoff.source_state_fresh_until.isoformat().replace(
            "+00:00", "Z"
        ),
        "authority": dict(handoff.authority),
    }
    (output_root / "proof-receipt.json").write_bytes(_canonical(proof))

    print(f"fixture={handoff.fixture_identifier}")
    print(f"handoff_sha256={_sha(handoff_bytes)}")
    print(f"candidate_sha256={handoff.candidate_sha256}")
    print("available_feature_ids=" + ",".join(handoff.available_feature_ids))
    for key in sorted(feature_values):
        print(f"{key}={feature_values[key]}")
    print(f"missing_feature_count={handoff.missing_feature_count}")
    print(f"blocked_feature_count={handoff.blocked_feature_count}")
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
