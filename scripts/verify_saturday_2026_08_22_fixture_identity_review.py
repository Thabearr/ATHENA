"""Replay the exact Saturday source bytes through an explicit 50-fixture identity review."""

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
import os
import subprocess
from pathlib import Path

from domain.fotmob_data_matches_capture import (
    canonical_data_matches_capture_manifest_bytes,
    manifest_from_mapping,
    strict_manifest_json_loads,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    build_fotmob_fixture_candidate_review_bundle,
    canonical_fotmob_fixture_candidate_review_bundle_bytes,
    sha256_fotmob_fixture_candidate_review_bundle,
)
from domain.fotmob_fixture_candidates import (
    build_fotmob_fixture_candidate_bundle,
    canonical_fotmob_fixture_candidate_bundle_bytes,
    sha256_fotmob_fixture_candidate_bundle,
)
from domain.saturday_2026_08_22_fixture_universe import build_saturday_fixture_universe
from scripts.manage_fotmob_reviewed_fixture_catalog import load_review_decision_ledger


EXPECTED_SOURCE_HEAD_SHA = "b879b2140d0bc3fb64fa8fec4c73c735240a3b41"
EXPECTED_SOURCE_RUN_ID = 32455713912
EXPECTED_SOURCE_ARTIFACT_ID = 9437181220
EXPECTED_SOURCE_ARTIFACT_DIGEST = (
    "sha256:360aac588f049fe6b0437c43e060b317edd12aaf4672db93ebe2fca42de00589"
)
EXPECTED_RAW_SHA256 = "a22e449fd7c59bee011e71230e345c733e1322311f6a9481812a23b4dcae2dc8"
EXPECTED_MANIFEST_SHA256 = "64fb631d4889dbf360af4fb988656aba579b67ca5340578df1056dc5324dc09e"
EXPECTED_CANDIDATE_BUNDLE_SHA256 = (
    "53b48ae1beabc10b638ad20f21e4807f78f0a3879ff8a21fd19a2da538a1ba3d"
)
EXPECTED_DECISION_LEDGER_SHA256 = (
    "7555b821b126a9218f9c9ec94f812eba9ad4a20440bdcd43626dc5806d62b563"
)
EXPECTED_REVIEWED_AT = "2026-08-21T07:26:00.000000Z"
EXPECTED_REVIEWER_REFERENCE = "ATHENA_PR201_EXPLICIT_IDENTITY_REVIEW"
EXPECTED_CANDIDATE_COUNT = 670
EXPECTED_APPROVED_COUNT = 50
EXPECTED_UNREVIEWED_COUNT = 620
EXPECTED_COMPETITION_COUNTS = {
    "Belgian Pro League": 3,
    "DFB-Pokal": 11,
    "Eredivisie": 4,
    "Greek Super League": 3,
    "La Liga": 3,
    "Ligue 1": 5,
    "Premier League": 5,
    "Primeira Liga": 3,
    "Scottish Premiership": 6,
    "Serie A": 4,
    "Süper Lig": 3,
}


class SaturdayFixtureIdentityReviewVerificationError(RuntimeError):
    """Raised when the frozen Saturday explicit-review proof does not replay exactly."""


def _git_head(repository: Path) -> str:
    value = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise SaturdayFixtureIdentityReviewVerificationError(
            "repository HEAD is not a full lowercase SHA"
        )
    return value


def _canonical_json_bytes(value: object) -> bytes:
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


def _write_once(path: Path, content: bytes) -> None:
    if type(content) is not bytes or not content:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "verification output must be non-empty exact bytes"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def execute(
    *,
    source_artifact_directory: Path,
    decision_ledger: Path,
    output_directory: Path,
) -> dict[str, object]:
    repository = Path(__file__).resolve().parents[1]
    head = _git_head(repository)
    source_root = Path(source_artifact_directory)
    output = Path(output_directory)
    if output.exists():
        raise SaturdayFixtureIdentityReviewVerificationError(
            "verification output directory already exists"
        )

    raw = (source_root / "fixture/response.json").read_bytes()
    manifest_bytes = (source_root / "fixture/manifest.json").read_bytes()
    source_candidate_bundle_bytes = (
        source_root / "fixture/fixture-candidates.json"
    ).read_bytes()

    manifest = manifest_from_mapping(strict_manifest_json_loads(manifest_bytes))
    if canonical_data_matches_capture_manifest_bytes(manifest) != manifest_bytes:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "source capture manifest bytes are not canonical"
        )
    if hashlib.sha256(raw).hexdigest() != EXPECTED_RAW_SHA256:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "source raw SHA-256 differs from frozen PR199 evidence"
        )
    if manifest.raw_sha256 != EXPECTED_RAW_SHA256 or manifest.raw_size != len(raw):
        raise SaturdayFixtureIdentityReviewVerificationError(
            "source manifest does not bind the exact frozen raw bytes"
        )
    if hashlib.sha256(manifest_bytes).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "source manifest SHA-256 differs from frozen PR199 evidence"
        )

    bundle = build_fotmob_fixture_candidate_bundle(((raw, manifest),))
    candidate_bundle_bytes = canonical_fotmob_fixture_candidate_bundle_bytes(bundle)
    if candidate_bundle_bytes != source_candidate_bundle_bytes:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "rebuilt PR40 candidate bundle differs from the frozen source artifact"
        )
    candidate_bundle_sha256 = sha256_fotmob_fixture_candidate_bundle(bundle)
    if candidate_bundle_sha256 != EXPECTED_CANDIDATE_BUNDLE_SHA256:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "candidate bundle SHA-256 differs from the explicit review ledger boundary"
        )

    decisions, decision_ledger_sha256 = load_review_decision_ledger(
        Path(decision_ledger),
        expected_candidate_bundle_sha256=candidate_bundle_sha256,
    )
    if decision_ledger_sha256 != EXPECTED_DECISION_LEDGER_SHA256:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "explicit review ledger SHA-256 differs from the frozen reviewed ledger"
        )

    universe = build_saturday_fixture_universe(bundle)
    if universe["candidate_count"] != EXPECTED_CANDIDATE_COUNT:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "Saturday source candidate count changed"
        )
    if universe["competition_review_source_identity_match_count"] != EXPECTED_APPROVED_COUNT:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "Saturday competition-review pool no longer contains exactly 50 fixtures"
        )
    if universe["prioritized_competition_counts"] != EXPECTED_COMPETITION_COUNTS:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "Saturday competition-review counts changed"
        )
    if any(universe["safety"].values()):
        raise SaturdayFixtureIdentityReviewVerificationError(
            "Saturday universe unexpectedly grants downstream authority"
        )

    expected_by_id = {
        item["source_match_id"]: item
        for item in universe["candidates"]
        if item["competition_review_source_identity_match"]
    }
    if len(expected_by_id) != EXPECTED_APPROVED_COUNT:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "Saturday prioritized fixture identities are not unique"
        )
    supplied_ids = {decision.source_match_id for decision in decisions}
    if len(decisions) != EXPECTED_APPROVED_COUNT or supplied_ids != set(expected_by_id):
        raise SaturdayFixtureIdentityReviewVerificationError(
            "explicit decisions do not cover exactly the 50 competition-review fixtures"
        )

    for decision in decisions:
        if decision.disposition is not FixtureCandidateReviewDisposition.APPROVED:
            raise SaturdayFixtureIdentityReviewVerificationError(
                "PR201 decision ledger must contain identity approvals only"
            )
        if decision.source_capture_manifest_sha256 != EXPECTED_MANIFEST_SHA256:
            raise SaturdayFixtureIdentityReviewVerificationError(
                "decision source manifest differs from the frozen capture"
            )
        if decision.reviewer_reference != EXPECTED_REVIEWER_REFERENCE:
            raise SaturdayFixtureIdentityReviewVerificationError(
                "decision reviewer reference differs from the explicit PR201 review"
            )
        reviewed_at = decision.reviewed_at.isoformat().replace("+00:00", "Z")
        if reviewed_at != EXPECTED_REVIEWED_AT:
            raise SaturdayFixtureIdentityReviewVerificationError(
                "decision review timestamp differs from the frozen explicit review"
            )
        expected = expected_by_id[decision.source_match_id]
        expected_note = (
            f"Saturday rank {expected['competition_review_rank']} "
            f"{expected['competition_review_name']}; identity only."
        )
        if decision.notes != expected_note:
            raise SaturdayFixtureIdentityReviewVerificationError(
                "decision note does not match the exact competition-review identity"
            )

    review_bundle = build_fotmob_fixture_candidate_review_bundle(bundle, decisions)
    if review_bundle.candidate_count != EXPECTED_CANDIDATE_COUNT:
        raise SaturdayFixtureIdentityReviewVerificationError("review candidate count mismatch")
    if review_bundle.decision_count != EXPECTED_APPROVED_COUNT:
        raise SaturdayFixtureIdentityReviewVerificationError("review decision count mismatch")
    if review_bundle.approved_count != EXPECTED_APPROVED_COUNT:
        raise SaturdayFixtureIdentityReviewVerificationError("review approval count mismatch")
    if review_bundle.rejected_count != 0:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "review ledger unexpectedly rejects a prioritized fixture"
        )
    if review_bundle.unreviewed_count != EXPECTED_UNREVIEWED_COUNT:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "review unreviewed-count mismatch"
        )
    if review_bundle.blocked_candidate_count != 0:
        raise SaturdayFixtureIdentityReviewVerificationError(
            "frozen PR199 candidate bundle unexpectedly contains review blockers"
        )
    if any(review_bundle.safety.values()):
        raise SaturdayFixtureIdentityReviewVerificationError(
            "explicit review bundle unexpectedly grants downstream authority"
        )

    approved_ids = {
        int(item.source_fixture_identifier)
        for item in review_bundle.approved_catalog_inputs
    }
    if approved_ids != set(expected_by_id):
        raise SaturdayFixtureIdentityReviewVerificationError(
            "approved catalog-input identities differ from the exact Saturday review pool"
        )

    review_bundle_bytes = canonical_fotmob_fixture_candidate_review_bundle_bytes(
        review_bundle
    )
    review_bundle_sha256 = sha256_fotmob_fixture_candidate_review_bundle(review_bundle)
    _write_once(output / "fixture-identity-review-bundle.json", review_bundle_bytes)

    receipt = {
        "schema_version": 1,
        "dataset_name": "athena-saturday-2026-08-22-fixture-identity-review-receipt-v1",
        "repository_head_sha": head,
        "source_pr199_head_sha": EXPECTED_SOURCE_HEAD_SHA,
        "source_pr199_run_id": EXPECTED_SOURCE_RUN_ID,
        "source_pr199_artifact_id": EXPECTED_SOURCE_ARTIFACT_ID,
        "source_pr199_artifact_digest": EXPECTED_SOURCE_ARTIFACT_DIGEST,
        "source_raw_sha256": EXPECTED_RAW_SHA256,
        "source_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "candidate_bundle_sha256": candidate_bundle_sha256,
        "decision_ledger_sha256": decision_ledger_sha256,
        "review_bundle_sha256": review_bundle_sha256,
        "candidate_count": review_bundle.candidate_count,
        "explicit_decision_count": review_bundle.decision_count,
        "approved_identity_count": review_bundle.approved_count,
        "rejected_identity_count": review_bundle.rejected_count,
        "unreviewed_identity_count": review_bundle.unreviewed_count,
        "blocked_candidate_count": review_bundle.blocked_candidate_count,
        "explicit_review_completed": True,
        "automatic_review_performed": False,
        "fixture_catalog_admission_performed": False,
        "fixture_intelligence_performed": False,
        "model_probability_performed": False,
        "sportybet_reconciliation_performed": False,
        "fresh_price_performed": False,
        "selection_performed": False,
        "bet_decision_performed": False,
        "safety": dict(review_bundle.safety),
    }
    receipt_bytes = _canonical_json_bytes(receipt)
    _write_once(output / "fixture-identity-review-receipt.json", receipt_bytes)

    return {
        "result": "SATURDAY_FIXTURE_IDENTITY_REVIEW_VERIFIED_EXPLICIT",
        "repository_head_sha": head,
        "approved_identity_count": review_bundle.approved_count,
        "unreviewed_identity_count": review_bundle.unreviewed_count,
        "decision_ledger_sha256": decision_ledger_sha256,
        "review_bundle_sha256": review_bundle_sha256,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-artifact-directory", required=True, type=Path)
    parser.add_argument("--decision-ledger", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = execute(
        source_artifact_directory=args.source_artifact_directory,
        decision_ledger=args.decision_ledger,
        output_directory=args.output_directory,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
