"""Offline operator workflow for source-replayed reviewed Fixture Catalog admission.

No network acquisition occurs.  The command first replays the existing reviewed
FotMob catalog workflow from exact capture directories and the explicit fixture
review ledger, checks the exact catalog/manifest outputs, then either emits an
admission-review decision template or consumes such a canonical decision and
stores the exact source-replayed admission artifact.
"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import json
from pathlib import Path
import stat
import sys
from collections.abc import Sequence
from typing import Any

from domain import reviewed_fixture_catalog_admission_source_replay as replay
from domain.fixture_catalog import (
    MANIFEST_DATASET_NAME,
    SAFETY_FLAGS,
    canonical_json_bytes,
    parse_utc_timestamp,
    serialize_utc,
)
from domain.reviewed_fixture_catalog_admission import (
    ReviewedFixtureCatalogAdmissionDisposition,
    sha256_reviewed_fixture_catalog_admission,
)
from scripts.manage_fotmob_reviewed_fixture_catalog import (
    FotMobReviewedFixtureCatalogWorkflowError,
    FotMobReviewedFixtureCatalogWorkflowResult,
    run as run_reviewed_catalog,
)

MAX_CONTROL_FILE_BYTES = 4 * 1024 * 1024
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "dataset_name",
        "generator",
        "generator_commit",
        "tracked_worktree_clean",
        "source",
        "as_of",
        "minimum_lead_seconds",
        "fixture_count",
        "earliest_kickoff",
        "latest_kickoff",
        "catalog_byte_size",
        "catalog_sha256",
        "normalized_input_byte_size",
        "normalized_input_sha256",
        "deterministic_ordering_rules",
        "provenance_records",
        "safety",
    }
)
_SHA40 = frozenset("0123456789abcdef")


class ReviewedFixtureCatalogAdmissionReplayCLIError(ValueError):
    """Raised when the offline replay command fails closed."""


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewedFixtureCatalogAdmissionReplayCLIError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReviewedFixtureCatalogAdmissionReplayCLIError(
        f"invalid JSON constant: {value}"
    )


def _read_regular(path: Path, *, maximum: int, label: str) -> bytes:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            f"{label} must not be a symlink"
        )
    try:
        before = candidate.stat()
    except OSError as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            f"{label} cannot be inspected"
        ) from exc
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            f"{label} must be a bounded non-empty regular file"
        )
    try:
        with candidate.open("rb") as handle:
            raw = handle.read(maximum + 1)
        after = candidate.stat()
    except OSError as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            f"{label} cannot be read"
        ) from exc
    if (
        not raw
        or len(raw) > maximum
        or len(raw) != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            f"{label} changed while being read"
        )
    return raw


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            f"{label} must be valid UTF-8"
        ) from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ReviewedFixtureCatalogAdmissionReplayCLIError:
        raise
    except json.JSONDecodeError as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            f"{label} is not valid JSON"
        ) from exc


def _load_checked_manifest(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = _read_regular(
        path,
        maximum=MAX_CONTROL_FILE_BYTES,
        label="checked Fixture Catalog manifest",
    )
    payload = _strict_json(raw, "checked Fixture Catalog manifest")
    if type(payload) is not dict or set(payload) != _MANIFEST_KEYS:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest keys mismatch"
        )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest schema_version mismatch"
        )
    if payload["dataset_name"] != MANIFEST_DATASET_NAME:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest dataset_name mismatch"
        )
    if payload["generator"] != "scripts.manage_fixture_catalog":
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest generator mismatch"
        )
    generator_commit = payload["generator_commit"]
    if (
        type(generator_commit) is not str
        or len(generator_commit) != 40
        or any(char not in _SHA40 for char in generator_commit)
    ):
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest generator_commit is invalid"
        )
    if payload["tracked_worktree_clean"] is not True:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest must record exact clean tracked worktree"
        )
    if payload["source"] != "FOTMOB":
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest source mismatch"
        )
    try:
        as_of = parse_utc_timestamp(payload["as_of"], "manifest.as_of")
    except Exception as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(str(exc)) from exc
    if serialize_utc(as_of) != payload["as_of"]:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest as_of must be canonical UTC"
        )
    minimum = payload["minimum_lead_seconds"]
    if type(minimum) is not int or isinstance(minimum, bool) or minimum < 0:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest minimum_lead_seconds is invalid"
        )
    if payload["safety"] != SAFETY_FLAGS:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest safety block mismatch"
        )
    if raw != canonical_json_bytes(payload):
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "checked Fixture Catalog manifest bytes are not canonical"
        )
    return raw, payload


def replay_catalog_sources(
    *,
    capture_directories: Sequence[str | Path],
    fixture_review_decision_ledger: Path,
    check_catalog: Path,
    check_manifest: Path,
    repository_root: Path,
) -> FotMobReviewedFixtureCatalogWorkflowResult:
    repository = Path(repository_root).resolve(strict=True)
    manifest_raw, manifest = _load_checked_manifest(Path(check_manifest))
    try:
        result = run_reviewed_catalog(
            capture_directories=capture_directories,
            decision_ledger=Path(fixture_review_decision_ledger),
            as_of=manifest["as_of"],
            minimum_lead_seconds=manifest["minimum_lead_seconds"],
            check_catalog=Path(check_catalog),
            check_manifest=Path(check_manifest),
            repository_root=repository,
            code_state={
                "evidence_git_head_sha": manifest["generator_commit"],
                "tracked_worktree_clean": True,
            },
        )
    except FotMobReviewedFixtureCatalogWorkflowError as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(str(exc)) from exc
    if result.mode != "CHECK":
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "reviewed catalog replay must run in CHECK mode"
        )
    if result.fixture_catalog_result.manifest_bytes != manifest_raw:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "source-replayed catalog manifest differs from checked manifest bytes"
        )
    return result


def prepare_admission_decision(
    *,
    workflow_result: FotMobReviewedFixtureCatalogWorkflowResult,
    disposition: ReviewedFixtureCatalogAdmissionDisposition,
    reviewed_at: str,
    reviewer_reference: str,
    notes: str = "",
) -> replay.ReviewedFixtureCatalogAdmissionReplayDecision:
    try:
        reviewed = parse_utc_timestamp(reviewed_at, "reviewed_at")
        if serialize_utc(reviewed) != reviewed_at:
            raise ReviewedFixtureCatalogAdmissionReplayCLIError(
                "reviewed_at must use canonical UTC serialization"
            )
        return replay.build_replay_decision(
            handoff=workflow_result.handoff,
            fixture_catalog_result=workflow_result.fixture_catalog_result,
            disposition=disposition,
            reviewed_at=reviewed,
            reviewer_reference=reviewer_reference,
            notes=notes,
        )
    except replay.ReviewedFixtureCatalogAdmissionSourceReplayError:
        raise
    except Exception as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(str(exc)) from exc


def store_from_decision_file(
    *,
    workflow_result: FotMobReviewedFixtureCatalogWorkflowResult,
    admission_decision_file: Path,
    repository_root: Path,
) -> dict[str, Any]:
    raw = _read_regular(
        Path(admission_decision_file),
        maximum=replay.MAX_DECISION_BYTES,
        label="catalog admission replay decision",
    )
    try:
        decision = replay.parse_replay_decision_bytes(raw)
        directory, admission = replay.store_source_replayed_admission(
            handoff=workflow_result.handoff,
            fixture_catalog_result=workflow_result.fixture_catalog_result,
            replay_decision=decision,
            repository_root=Path(repository_root),
        )
        verified = replay.verify_source_replayed_admission_directory(
            directory,
            handoff=workflow_result.handoff,
            fixture_catalog_result=workflow_result.fixture_catalog_result,
            repository_root=Path(repository_root),
        )
    except replay.ReviewedFixtureCatalogAdmissionSourceReplayError as exc:
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(str(exc)) from exc
    if (
        sha256_reviewed_fixture_catalog_admission(admission)
        != sha256_reviewed_fixture_catalog_admission(verified)
    ):
        raise ReviewedFixtureCatalogAdmissionReplayCLIError(
            "post-store source-aware admission verification mismatch"
        )
    return {
        "status": replay.STATUS,
        "dataset_name": replay.DATASET_NAME,
        "admission_directory": directory.relative_to(
            Path(repository_root).resolve(strict=True)
        ).as_posix(),
        "admission_sha256": sha256_reviewed_fixture_catalog_admission(admission),
        "decision_sha256": replay.replay_decision_sha256(decision),
        "disposition": admission.decision.disposition.value,
        "admitted_fixture_count": len(admission.admitted_fixtures),
        "candidate_bundle_sha256": admission.decision.candidate_bundle_sha256,
        "review_bundle_sha256": admission.decision.review_bundle_sha256,
        "handoff_sha256": admission.decision.handoff_sha256,
        "catalog_sha256": admission.decision.catalog_sha256,
        "manifest_sha256": admission.decision.manifest_sha256,
        "source_capability": admission.decision.source_capability,
        "athena_network_acquisition_performed": False,
        "automatic_review_performed": False,
        "bookmaker_equivalence_authorized": False,
        "canonical_market_mapping_authorized": False,
        "fresh_price_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "slip_construction_authorized": False,
        "booking_code_authorized": False,
        "sportybet_execution_authorized": False,
        "bet_authorized": False,
    }


def _shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--capture-directory",
        action="append",
        required=True,
        help="Repeatable verified PR #38 FotMob /api/data/matches capture directory.",
    )
    parser.add_argument(
        "--fixture-review-decision-ledger",
        required=True,
        help="Exact explicit PR fixture-review decision ledger.",
    )
    parser.add_argument(
        "--check-catalog",
        required=True,
        help="Exact checked reviewed Fixture Catalog JSON.",
    )
    parser.add_argument(
        "--check-manifest",
        required=True,
        help="Exact checked reviewed Fixture Catalog manifest JSON.",
    )
    parser.add_argument(
        "--repository-root",
        default=".",
        help="ATHENA repository root.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the exact reviewed FotMob Fixture Catalog source chain and "
            "prepare or store a source-replayed catalog admission artifact. "
            "No network acquisition is performed."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser(
        "prepare-decision",
        help="Emit the exact canonical catalog-admission review decision JSON.",
    )
    _shared(prepare)
    prepare.add_argument(
        "--disposition",
        required=True,
        choices=[item.value for item in ReviewedFixtureCatalogAdmissionDisposition],
    )
    prepare.add_argument("--reviewed-at", required=True)
    prepare.add_argument("--reviewer-reference", required=True)
    prepare.add_argument("--notes", default="")

    store = sub.add_parser(
        "store",
        help="Consume a canonical admission decision and store the replayed admission.",
    )
    _shared(store)
    store.add_argument("--admission-decision", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = replay_catalog_sources(
            capture_directories=args.capture_directory,
            fixture_review_decision_ledger=Path(
                args.fixture_review_decision_ledger
            ),
            check_catalog=Path(args.check_catalog),
            check_manifest=Path(args.check_manifest),
            repository_root=Path(args.repository_root),
        )
        if args.command == "prepare-decision":
            decision = prepare_admission_decision(
                workflow_result=result,
                disposition=ReviewedFixtureCatalogAdmissionDisposition(
                    args.disposition
                ),
                reviewed_at=args.reviewed_at,
                reviewer_reference=args.reviewer_reference,
                notes=args.notes,
            )
            sys.stdout.buffer.write(replay.canonical_replay_decision_bytes(decision))
            return 0
        receipt = store_from_decision_file(
            workflow_result=result,
            admission_decision_file=Path(args.admission_decision),
            repository_root=Path(args.repository_root),
        )
        sys.stdout.write(
            json.dumps(
                receipt,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 0
    except (
        ReviewedFixtureCatalogAdmissionReplayCLIError,
        replay.ReviewedFixtureCatalogAdmissionSourceReplayError,
        OSError,
        ValueError,
    ) as exc:
        parser.exit(1, f"reviewed Fixture Catalog admission replay failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
