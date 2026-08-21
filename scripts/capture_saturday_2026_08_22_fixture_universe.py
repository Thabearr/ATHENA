"""Capture the exact 2026-08-22 FotMob fixture universe for ATHENA's 20-fold target."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path

from domain.fotmob_data_matches_capture import (
    MANIFEST_FILENAME,
    RAW_FILENAME,
    canonical_data_matches_capture_manifest_bytes,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_data_matches_schema import (
    assess_fotmob_data_matches_schema,
    canonical_data_matches_schema_assessment_bytes,
)
from domain.fotmob_fixture_candidates import (
    build_fotmob_fixture_candidate_bundle,
    canonical_fotmob_fixture_candidate_bundle_bytes,
    sha256_fotmob_fixture_candidate_bundle,
)
from domain.saturday_2026_08_22_fixture_universe import (
    REQUEST_CCODE3,
    REQUEST_TIMEZONE,
    TARGET_REQUEST_DATE,
    build_saturday_fixture_universe,
    canonical_saturday_fixture_universe_bytes,
    sha256_saturday_fixture_universe,
)
from scripts.capture_fotmob_data_matches import (
    fetch_fotmob_data_matches,
    write_data_matches_capture_directory,
)


OUTPUT_DIRECTORY = Path("saturday-fixture-universe-artifact")
WORKFLOW_NAME = "Capture Saturday 2026-08-22 FotMob Fixture Universe"


class SaturdayFixtureUniverseCaptureError(RuntimeError):
    pass


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _git_head(repository: Path) -> str:
    value = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise SaturdayFixtureUniverseCaptureError("repository HEAD is not a full lowercase SHA")
    return value


def _write_once(path: Path, content: bytes) -> None:
    if type(content) is not bytes or not content:
        raise SaturdayFixtureUniverseCaptureError("artifact content must be non-empty bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _copy_exact(source: Path, destination: Path) -> bytes:
    content = source.read_bytes()
    _write_once(destination, content)
    return content


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


def execute(*, repository_head_sha: str, execute_live_network: bool) -> dict[str, object]:
    repository = Path(__file__).resolve().parents[1]
    head = _git_head(repository)
    if repository_head_sha != head:
        raise SaturdayFixtureUniverseCaptureError(
            f"checked-out HEAD {head} differs from authorized {repository_head_sha}"
        )
    if not execute_live_network:
        raise SaturdayFixtureUniverseCaptureError(
            "live capture requires explicit --execute-live-network"
        )

    output = repository / OUTPUT_DIRECTORY
    if output.exists():
        raise SaturdayFixtureUniverseCaptureError("artifact output already exists")
    output.mkdir(parents=True)
    started_at = _utc_now()

    response = fetch_fotmob_data_matches(
        request_date=TARGET_REQUEST_DATE,
        timezone=REQUEST_TIMEZONE,
        ccode3=REQUEST_CCODE3,
    )
    capture_directory, manifest = write_data_matches_capture_directory(
        response,
        request_date=TARGET_REQUEST_DATE,
        timezone=REQUEST_TIMEZONE,
        ccode3=REQUEST_CCODE3,
        repository_root=repository,
    )

    raw = _copy_exact(capture_directory / RAW_FILENAME, output / "fixture/response.json")
    manifest_bytes = _copy_exact(
        capture_directory / MANIFEST_FILENAME,
        output / "fixture/manifest.json",
    )
    if manifest_bytes != canonical_data_matches_capture_manifest_bytes(manifest):
        raise SaturdayFixtureUniverseCaptureError("capture manifest read-back mismatch")

    assessment = assess_fotmob_data_matches_schema(raw, manifest)
    assessment_bytes = canonical_data_matches_schema_assessment_bytes(assessment)
    _write_once(output / "fixture/schema-assessment.json", assessment_bytes)

    bundle = build_fotmob_fixture_candidate_bundle(((raw, manifest),))
    bundle_bytes = canonical_fotmob_fixture_candidate_bundle_bytes(bundle)
    _write_once(output / "fixture/fixture-candidates.json", bundle_bytes)

    universe = build_saturday_fixture_universe(bundle)
    universe_bytes = canonical_saturday_fixture_universe_bytes(universe)
    _write_once(output / "saturday-fixture-universe.json", universe_bytes)

    completed_at = _utc_now()
    receipt = {
        "schema_version": 1,
        "dataset_name": "athena-saturday-2026-08-22-fixture-universe-capture-receipt-v1",
        "repository": os.environ.get("GITHUB_REPOSITORY", "Thabearr/ATHENA"),
        "repository_head_sha": head,
        "workflow_name": WORKFLOW_NAME,
        "workflow_run_id": int(os.environ.get("GITHUB_RUN_ID", "1")),
        "workflow_run_attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
        "github_actor": os.environ.get("GITHUB_ACTOR", "local-static-inspection"),
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "completed_at": completed_at.isoformat().replace("+00:00", "Z"),
        "request_date": TARGET_REQUEST_DATE,
        "request_timezone": REQUEST_TIMEZONE,
        "request_ccode3": REQUEST_CCODE3,
        "source_observed_at": manifest.observed_at.isoformat().replace("+00:00", "Z"),
        "source_raw_size": manifest.raw_size,
        "source_raw_sha256": manifest.raw_sha256,
        "source_manifest_sha256": sha256_data_matches_capture_manifest(manifest),
        "schema_assessment_sha256": hashlib.sha256(assessment_bytes).hexdigest(),
        "fixture_candidate_bundle_sha256": sha256_fotmob_fixture_candidate_bundle(bundle),
        "saturday_fixture_universe_sha256": sha256_saturday_fixture_universe(universe),
        "candidate_count": universe["candidate_count"],
        "bootstrap_exact_name_match_count": universe["bootstrap_exact_name_match_count"],
        "unprioritized_literal_competition_count": universe[
            "unprioritized_literal_competition_count"
        ],
        "enough_source_fixtures_for_requested_fold": universe[
            "enough_source_fixtures_for_requested_fold"
        ],
        "safety": universe["safety"],
    }
    receipt_bytes = _canonical_json_bytes(receipt)
    _write_once(output / "capture-receipt.json", receipt_bytes)

    return {
        "result": "SATURDAY_FIXTURE_UNIVERSE_CAPTURED_UNREVIEWED",
        "repository_head_sha": head,
        "candidate_count": universe["candidate_count"],
        "bootstrap_exact_name_match_count": universe["bootstrap_exact_name_match_count"],
        "unprioritized_literal_competition_count": universe[
            "unprioritized_literal_competition_count"
        ],
        "source_raw_sha256": manifest.raw_sha256,
        "source_manifest_sha256": sha256_data_matches_capture_manifest(manifest),
        "fixture_candidate_bundle_sha256": sha256_fotmob_fixture_candidate_bundle(bundle),
        "saturday_fixture_universe_sha256": sha256_saturday_fixture_universe(universe),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-head-sha", required=True)
    parser.add_argument("--execute-live-network", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = execute(
        repository_head_sha=args.repository_head_sha,
        execute_live_network=args.execute_live_network,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
