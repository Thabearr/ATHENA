"""Prepare the exact reviewed Saturday 2026-08-22 Fixture Catalog.

The command is offline. It replays the exact PR #199 FotMob capture plus the exact
PR #201 fixture-review ledger through the existing reviewed catalog workflow,
checks the generated catalog/manifest, and prepares the exact canonical catalog-
admission decision candidate for a later separate byte review.

It does not store an admission and grants no Fixture Intelligence, model, pricing,
selection, accumulator, execution, or BET authority.
"""

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

from domain import reviewed_fixture_catalog_admission_source_replay as admission_replay
from domain.fotmob_data_matches_capture import (
    capture_identifier,
    manifest_from_mapping,
    strict_manifest_json_loads,
)
from domain.fotmob_fixture_candidate_review import FixtureCandidateReviewDisposition
from domain.reviewed_fixture_catalog_admission import (
    ReviewedFixtureCatalogAdmissionDisposition,
)
from scripts.manage_fotmob_reviewed_fixture_catalog import (
    load_review_decision_ledger,
    run as run_reviewed_catalog,
)
from scripts.replay_reviewed_fixture_catalog_admission import prepare_admission_decision


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
EXPECTED_FIXTURE_REVIEW_LEDGER_SHA256 = (
    "7555b821b126a9218f9c9ec94f812eba9ad4a20440bdcd43626dc5806d62b563"
)
EXPECTED_SOURCE_CANDIDATE_COUNT = 670
EXPECTED_APPROVED_FIXTURE_COUNT = 50
EXPECTED_UNREVIEWED_FIXTURE_COUNT = 620
CATALOG_AS_OF = "2026-08-21T08:57:00.000000Z"
ADMISSION_REVIEWED_AT = "2026-08-21T08:57:00.000000Z"
ADMISSION_REVIEWER_REFERENCE = "ATHENA_PR202_EXACT_50_CATALOG_ADMISSION_REVIEW"
ADMISSION_NOTES = (
    "Exact Saturday 2026-08-22 50-fixture reviewed catalog; admission decision "
    "candidate only until exact canonical bytes receive separate review."
)


class SaturdayReviewedFixtureCatalogPreparationError(RuntimeError):
    """Raised when the exact Saturday reviewed catalog cannot be replayed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "prepared output must be non-empty exact bytes"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _git_head(repository: Path) -> str:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "repository HEAD is not a canonical lowercase full SHA"
        )
    return head


def _materialize_exact_source_capture(
    *,
    source_artifact_directory: Path,
    repository: Path,
) -> Path:
    source_fixture = Path(source_artifact_directory) / "fixture"
    raw = (source_fixture / "response.json").read_bytes()
    manifest_bytes = (source_fixture / "manifest.json").read_bytes()
    if _sha256(raw) != EXPECTED_RAW_SHA256:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "PR199 source raw SHA-256 mismatch"
        )
    if _sha256(manifest_bytes) != EXPECTED_MANIFEST_SHA256:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "PR199 source manifest SHA-256 mismatch"
        )
    manifest = manifest_from_mapping(strict_manifest_json_loads(manifest_bytes))
    if manifest.raw_sha256 != EXPECTED_RAW_SHA256 or manifest.raw_size != len(raw):
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "PR199 source manifest does not bind the exact raw bytes"
        )
    if manifest.request_date != "20260822" or manifest.timezone != "UTC":
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "PR199 source request date/timezone changed"
        )
    if manifest.ccode3 != "NGA" or manifest.network_acquisition_performed is not True:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "PR199 source country/provenance state changed"
        )
    capture_id = capture_identifier(
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        observed_at=manifest.observed_at,
        raw_sha256=manifest.raw_sha256,
    )
    capture = (
        repository
        / ".cache/athena-research/fotmob-data-matches-captures"
        / manifest.request_date
        / capture_id
    )
    if capture.exists():
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "deterministic source capture directory already exists"
        )
    capture.mkdir(parents=True, exist_ok=False)
    _write_once(capture / "response.json", raw)
    _write_once(capture / "manifest.json", manifest_bytes)
    return capture


def _invariant_summary(summary: dict[str, object]) -> dict[str, object]:
    value = dict(summary)
    value.pop("mode", None)
    operation = dict(value["operation"])
    operation.pop("fixture_catalog_write_performed", None)
    value["operation"] = operation
    return value


def execute(
    *,
    source_artifact_directory: Path,
    fixture_review_decision_ledger: Path,
    output_directory: Path,
) -> dict[str, object]:
    repository = Path(__file__).resolve().parents[1]
    head = _git_head(repository)
    output = Path(output_directory)
    if output.exists():
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "output directory already exists"
        )
    output.parent.mkdir(parents=True, exist_ok=True)

    ledger_raw = Path(fixture_review_decision_ledger).read_bytes()
    if _sha256(ledger_raw) != EXPECTED_FIXTURE_REVIEW_LEDGER_SHA256:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "PR201 fixture-review decision ledger SHA-256 mismatch"
        )
    decisions, ledger_sha = load_review_decision_ledger(
        Path(fixture_review_decision_ledger),
        expected_candidate_bundle_sha256=EXPECTED_CANDIDATE_BUNDLE_SHA256,
    )
    if ledger_sha != EXPECTED_FIXTURE_REVIEW_LEDGER_SHA256:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "strict PR201 fixture-review ledger parser hash mismatch"
        )
    if len(decisions) != EXPECTED_APPROVED_FIXTURE_COUNT:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "PR201 fixture-review ledger no longer contains exactly 50 decisions"
        )
    if any(
        item.disposition is not FixtureCandidateReviewDisposition.APPROVED
        for item in decisions
    ):
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "Saturday catalog boundary requires the exact 50 identity approvals"
        )

    capture = _materialize_exact_source_capture(
        source_artifact_directory=source_artifact_directory,
        repository=repository,
    )
    output.mkdir(parents=True, exist_ok=False)
    catalog_path = output / "reviewed-fixture-catalog.json"
    manifest_path = output / "reviewed-fixture-catalog.manifest.json"

    generated = run_reviewed_catalog(
        capture_directories=(capture,),
        decision_ledger=Path(fixture_review_decision_ledger),
        as_of=CATALOG_AS_OF,
        minimum_lead_seconds=0,
        catalog_output=catalog_path,
        manifest_output=manifest_path,
        repository_root=repository,
    )
    checked = run_reviewed_catalog(
        capture_directories=(capture,),
        decision_ledger=Path(fixture_review_decision_ledger),
        as_of=CATALOG_AS_OF,
        minimum_lead_seconds=0,
        check_catalog=catalog_path,
        check_manifest=manifest_path,
        repository_root=repository,
    )
    if generated.mode != "GENERATE" or checked.mode != "CHECK":
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "reviewed catalog generate/check modes were not preserved"
        )
    if _invariant_summary(generated.summary) != _invariant_summary(checked.summary):
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "generated and checked catalog replay summaries differ"
        )

    summary = generated.summary
    expected_scalars = {
        "candidate_bundle_sha256": EXPECTED_CANDIDATE_BUNDLE_SHA256,
        "candidate_count": EXPECTED_SOURCE_CANDIDATE_COUNT,
        "decision_count": EXPECTED_APPROVED_FIXTURE_COUNT,
        "approved_count": EXPECTED_APPROVED_FIXTURE_COUNT,
        "rejected_count": 0,
        "unreviewed_count": EXPECTED_UNREVIEWED_FIXTURE_COUNT,
        "blocked_candidate_count": 0,
        "fixture_count": EXPECTED_APPROVED_FIXTURE_COUNT,
    }
    for key, expected in expected_scalars.items():
        if summary[key] != expected:
            raise SaturdayReviewedFixtureCatalogPreparationError(
                f"reviewed catalog {key} mismatch: expected {expected!r}, got {summary[key]!r}"
            )

    operation = summary["operation"]
    if type(operation) is not dict:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "reviewed catalog operation summary is not a mapping"
        )
    if operation["fixture_catalog_compile_performed"] is not True:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "Fixture Catalog compilation was not proven"
        )
    if operation["fixture_catalog_write_performed"] is not True:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "generation mode did not write the reviewed catalog"
        )
    forbidden_true = {
        key
        for key, value in operation.items()
        if key not in {"fixture_catalog_compile_performed", "fixture_catalog_write_performed"}
        and value is True
    }
    if forbidden_true:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "reviewed catalog workflow unexpectedly grants downstream operation state: "
            + ", ".join(sorted(forbidden_true))
        )

    expected_ids = {item.source_match_id for item in decisions}
    actual_ids = {
        int(item.source_fixture_identifier) for item in generated.handoff.catalog_inputs
    }
    if actual_ids != expected_ids or len(actual_ids) != EXPECTED_APPROVED_FIXTURE_COUNT:
        raise SaturdayReviewedFixtureCatalogPreparationError(
            "compiled catalog identities differ from the exact PR201 50-fixture review"
        )

    admission_decision = prepare_admission_decision(
        workflow_result=checked,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.ADMITTED,
        reviewed_at=ADMISSION_REVIEWED_AT,
        reviewer_reference=ADMISSION_REVIEWER_REFERENCE,
        notes=ADMISSION_NOTES,
    )
    admission_decision_bytes = admission_replay.canonical_replay_decision_bytes(
        admission_decision
    )
    admission_decision_path = output / "catalog-admission-decision-candidate.json"
    _write_once(admission_decision_path, admission_decision_bytes)

    receipt = {
        "schema_version": 1,
        "dataset_name": "athena-saturday-2026-08-22-reviewed-fixture-catalog-prepare-v1",
        "repository_head_sha": head,
        "source_pr199_head_sha": EXPECTED_SOURCE_HEAD_SHA,
        "source_pr199_run_id": EXPECTED_SOURCE_RUN_ID,
        "source_pr199_artifact_id": EXPECTED_SOURCE_ARTIFACT_ID,
        "source_pr199_artifact_digest": EXPECTED_SOURCE_ARTIFACT_DIGEST,
        "source_raw_sha256": EXPECTED_RAW_SHA256,
        "source_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "candidate_bundle_sha256": summary["candidate_bundle_sha256"],
        "fixture_review_decision_ledger_sha256": ledger_sha,
        "review_bundle_sha256": summary["review_bundle_sha256"],
        "handoff_sha256": summary["handoff_sha256"],
        "catalog_sha256": summary["catalog_sha256"],
        "manifest_sha256": summary["manifest_sha256"],
        "catalog_admission_decision_candidate_sha256": _sha256(admission_decision_bytes),
        "capture_directory": capture.relative_to(repository).as_posix(),
        "catalog_path": catalog_path.relative_to(repository).as_posix(),
        "manifest_path": manifest_path.relative_to(repository).as_posix(),
        "admission_decision_candidate_path": admission_decision_path.relative_to(repository).as_posix(),
        "candidate_count": summary["candidate_count"],
        "explicit_fixture_review_count": summary["decision_count"],
        "approved_fixture_count": summary["approved_count"],
        "unreviewed_fixture_count": summary["unreviewed_count"],
        "compiled_fixture_count": summary["fixture_count"],
        "catalog_as_of": CATALOG_AS_OF,
        "catalog_admission_reviewed_at": ADMISSION_REVIEWED_AT,
        "catalog_admission_disposition_candidate": "ADMITTED",
        "catalog_compile_performed": True,
        "catalog_write_performed": True,
        "catalog_check_performed": True,
        "catalog_admission_decision_prepared": True,
        "catalog_admission_stored": False,
        "fixture_intelligence_performed": False,
        "model_probability_performed": False,
        "sportybet_reconciliation_performed": False,
        "fresh_price_performed": False,
        "selection_performed": False,
        "bet_decision_performed": False,
    }
    _write_once(
        output / "reviewed-fixture-catalog-prepare-receipt.json",
        _canonical_json_bytes(receipt),
    )
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-artifact-directory", required=True, type=Path)
    parser.add_argument("--fixture-review-decision-ledger", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = execute(
        source_artifact_directory=args.source_artifact_directory,
        fixture_review_decision_ledger=args.fixture_review_decision_ledger,
        output_directory=args.output_directory,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
