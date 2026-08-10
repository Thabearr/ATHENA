"""Offline operator workflow from explicit FotMob reviews to PR #29 catalog outputs."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import dataclasses
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from domain.fixture_catalog import (
    FixtureCatalogError,
    FixtureCatalogResult,
    parse_utc_timestamp,
    serialize_utc,
    sha256_bytes,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewDecision,
    FotMobFixtureCandidateReviewError,
    build_fotmob_fixture_candidate_review_bundle,
    sha256_fotmob_fixture_candidate_review_bundle,
)
from domain.fotmob_fixture_candidates import (
    FotMobFixtureCandidateBundle,
    FotMobFixtureCandidateError,
    build_fotmob_fixture_candidate_bundle,
    sha256_fotmob_fixture_candidate_bundle,
)
from domain.fotmob_fixture_catalog_handoff import (
    FotMobFixtureCatalogHandoff,
    FotMobFixtureCatalogHandoffError,
    build_fotmob_fixture_catalog_handoff,
    sha256_fotmob_fixture_catalog_handoff,
)
from scripts.build_fotmob_fixture_candidates import (
    ALLOWED_ROOT_RELATIVE,
    _capture_path,
    _verified_capture,
)
from scripts.manage_fixture_catalog import (
    FixtureCatalogCLIError,
    run as run_fixture_catalog,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-fixture-catalog-workflow-v1"
DECISION_LEDGER_SCHEMA_VERSION = 1
DECISION_LEDGER_DATASET_NAME = "athena-fotmob-fixture-review-decision-ledger-v1"
MAX_DECISION_LEDGER_BYTES = 4 * 1024 * 1024
_LEDGER_KEYS = frozenset(
    {"schema_version", "dataset_name", "candidate_bundle_sha256", "decisions"}
)
_DECISION_KEYS = frozenset(
    {
        "source_capture_manifest_sha256",
        "source_match_id",
        "candidate_sha256",
        "disposition",
        "reviewed_at",
        "reviewer_reference",
        "notes",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)


class FotMobReviewedFixtureCatalogWorkflowError(ValueError):
    """Raised when the explicit reviewed-catalog workflow cannot be proven."""


@dataclasses.dataclass(frozen=True)
class FotMobReviewedFixtureCatalogWorkflowResult:
    candidate_bundle: FotMobFixtureCandidateBundle
    review_bundle_sha256: str
    handoff: FotMobFixtureCatalogHandoff
    decision_ledger_sha256: str
    fixture_catalog_result: FixtureCatalogResult
    mode: str

    @property
    def summary(self) -> dict[str, Any]:
        catalog_result = self.fixture_catalog_result
        handoff = self.handoff
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "mode": self.mode,
            "decision_ledger_sha256": self.decision_ledger_sha256,
            "candidate_bundle_sha256": sha256_fotmob_fixture_candidate_bundle(
                self.candidate_bundle
            ),
            "review_bundle_sha256": self.review_bundle_sha256,
            "handoff_sha256": sha256_fotmob_fixture_catalog_handoff(handoff),
            "handoff_catalog_input_sha256": handoff.catalog_input_sha256,
            "compiler_normalized_input_sha256": (
                catalog_result.normalized_input_sha256
            ),
            "catalog_sha256": sha256_bytes(catalog_result.catalog_bytes),
            "manifest_sha256": sha256_bytes(catalog_result.manifest_bytes),
            "source_capture_count": len(self.candidate_bundle.sources),
            "candidate_count": handoff.review_bundle.candidate_count,
            "decision_count": handoff.review_bundle.decision_count,
            "approved_count": handoff.review_bundle.approved_count,
            "rejected_count": handoff.review_bundle.rejected_count,
            "unreviewed_count": handoff.review_bundle.unreviewed_count,
            "blocked_candidate_count": handoff.review_bundle.blocked_candidate_count,
            "fixture_count": len(catalog_result.records),
            "as_of": serialize_utc(catalog_result.as_of),
            "minimum_lead_seconds": catalog_result.minimum_lead_seconds,
            "operation": {
                "network_acquisition_performed": False,
                "raw_capture_performed": False,
                "automatic_review_performed": False,
                "source_qualification_performed": False,
                "identity_resolution_performed": False,
                "fixture_catalog_compile_performed": True,
                "fixture_catalog_write_performed": self.mode == "GENERATE",
                "fixture_catalog_promotion_performed": False,
                "intelligence_performed": False,
                "model_feature_generation_performed": False,
                "probability_generation_performed": False,
                "pricing_performed": False,
                "selection_performed": False,
                "bet_decision_performed": False,
            },
        }

    @property
    def summary_bytes(self) -> bytes:
        return (
            json.dumps(
                self.summary,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FotMobReviewedFixtureCatalogWorkflowError(
                f"duplicate JSON key in decision ledger: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FotMobReviewedFixtureCatalogWorkflowError(
        f"invalid JSON constant in decision ledger: {value}"
    )


def _strict_str(
    value: Any,
    label: str,
    *,
    non_empty: bool = False,
    trimmed: bool = False,
) -> str:
    if type(value) is not str:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            f"{label} must be an exact string"
        )
    if non_empty and not value:
        raise FotMobReviewedFixtureCatalogWorkflowError(f"{label} must be non-empty")
    if trimmed and value != value.strip():
        raise FotMobReviewedFixtureCatalogWorkflowError(
            f"{label} must not contain surrounding whitespace"
        )
    return value


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor) if absolute.anchor else Path.cwd()
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise FotMobReviewedFixtureCatalogWorkflowError(
                f"{label} contains a forbidden symlink component"
            )


def _read_decision_ledger_bytes(path: Path) -> bytes:
    candidate = Path(path)
    _reject_symlink_components(candidate, "decision ledger path")
    if candidate.is_symlink():
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger must not be a symlink"
        )
    try:
        metadata_before = candidate.stat()
    except OSError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger could not be inspected"
        ) from exc
    if not stat.S_ISREG(metadata_before.st_mode):
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger must be a regular file"
        )
    if metadata_before.st_size <= 0:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger must not be empty"
        )
    if metadata_before.st_size > MAX_DECISION_LEDGER_BYTES:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger exceeds the 4 MiB limit"
        )
    try:
        with candidate.open("rb") as handle:
            raw = handle.read(MAX_DECISION_LEDGER_BYTES + 1)
        metadata_after = candidate.stat()
    except OSError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger could not be read"
        ) from exc
    if type(raw) is not bytes or not raw:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger read did not return non-empty exact bytes"
        )
    if len(raw) > MAX_DECISION_LEDGER_BYTES:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger exceeds the 4 MiB limit"
        )
    if (
        len(raw) != metadata_before.st_size
        or metadata_after.st_size != metadata_before.st_size
        or metadata_after.st_mtime_ns != metadata_before.st_mtime_ns
    ):
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger changed while it was being read"
        )
    return raw


def _parse_decision_record(
    payload: Any,
    *,
    index: int,
) -> FotMobFixtureCandidateReviewDecision:
    if type(payload) is not dict or set(payload) != _DECISION_KEYS:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            f"decision[{index}] keys do not match the exact review contract"
        )
    source_match_id = payload["source_match_id"]
    if type(source_match_id) is not int:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            f"decision[{index}].source_match_id must be an exact integer"
        )
    disposition_value = _strict_str(
        payload["disposition"],
        f"decision[{index}].disposition",
        non_empty=True,
        trimmed=True,
    )
    try:
        disposition = FixtureCandidateReviewDisposition(disposition_value)
    except ValueError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            f"decision[{index}].disposition is not APPROVED or REJECTED"
        ) from exc
    reviewed_at_raw = _strict_str(
        payload["reviewed_at"],
        f"decision[{index}].reviewed_at",
        non_empty=True,
        trimmed=True,
    )
    try:
        reviewed_at = parse_utc_timestamp(
            reviewed_at_raw,
            f"decision[{index}].reviewed_at",
        )
    except FixtureCatalogError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(str(exc)) from exc
    try:
        return FotMobFixtureCandidateReviewDecision(
            source_capture_manifest_sha256=_strict_sha256(
                payload["source_capture_manifest_sha256"],
                f"decision[{index}].source_capture_manifest_sha256",
            ),
            source_match_id=source_match_id,
            candidate_sha256=_strict_sha256(
                payload["candidate_sha256"],
                f"decision[{index}].candidate_sha256",
            ),
            disposition=disposition,
            reviewed_at=reviewed_at,
            reviewer_reference=_strict_str(
                payload["reviewer_reference"],
                f"decision[{index}].reviewer_reference",
                non_empty=True,
                trimmed=True,
            ),
            notes=_strict_str(payload["notes"], f"decision[{index}].notes"),
        )
    except FotMobFixtureCandidateReviewError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(str(exc)) from exc


def load_review_decision_ledger(
    path: Path,
    *,
    expected_candidate_bundle_sha256: str,
) -> tuple[tuple[FotMobFixtureCandidateReviewDecision, ...], str]:
    """Read a strict explicit decision ledger anchored to one candidate bundle."""

    expected_sha = _strict_sha256(
        expected_candidate_bundle_sha256,
        "expected_candidate_bundle_sha256",
    )
    raw = _read_decision_ledger_bytes(path)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger must be valid UTF-8"
        ) from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FotMobReviewedFixtureCatalogWorkflowError:
        raise
    except json.JSONDecodeError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger is not valid JSON"
        ) from exc
    if type(payload) is not dict or set(payload) != _LEDGER_KEYS:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger keys do not match the exact workflow contract"
        )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger schema_version must be exact integer 1"
        )
    if payload["dataset_name"] != DECISION_LEDGER_DATASET_NAME:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            f"decision ledger dataset_name must be {DECISION_LEDGER_DATASET_NAME}"
        )
    ledger_candidate_sha = _strict_sha256(
        payload["candidate_bundle_sha256"],
        "decision ledger candidate_bundle_sha256",
    )
    if ledger_candidate_sha != expected_sha:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger does not anchor the exact rebuilt candidate bundle"
        )
    decisions_raw = payload["decisions"]
    if type(decisions_raw) is not list:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "decision ledger decisions must be an exact JSON array"
        )
    decisions = tuple(
        _parse_decision_record(item, index=index)
        for index, item in enumerate(decisions_raw)
    )
    return decisions, hashlib.sha256(raw).hexdigest()


def _build_candidate_bundle_from_capture_directories(
    capture_directories: Sequence[str | Path],
    *,
    repository_root: Path,
) -> tuple[FotMobFixtureCandidateBundle, Path]:
    if not isinstance(capture_directories, Sequence) or isinstance(
        capture_directories,
        (str, bytes),
    ) or not capture_directories:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "at least one capture directory is required"
        )
    captures = []
    allowed_root: Path | None = None
    for value in capture_directories:
        try:
            capture, current_allowed_root = _capture_path(
                value,
                repository_root=repository_root,
            )
            verified = _verified_capture(capture, current_allowed_root)
        except (FotMobFixtureCandidateError, ValueError) as exc:
            raise FotMobReviewedFixtureCatalogWorkflowError(str(exc)) from exc
        if allowed_root is None:
            allowed_root = current_allowed_root
        elif current_allowed_root != allowed_root:
            raise FotMobReviewedFixtureCatalogWorkflowError(
                "capture directories resolved to inconsistent evidence roots"
            )
        captures.append(verified)
    assert allowed_root is not None
    try:
        return build_fotmob_fixture_candidate_bundle(captures), allowed_root
    except FotMobFixtureCandidateError as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(str(exc)) from exc


def _materialize_handoff_input(
    handoff: FotMobFixtureCatalogHandoff,
    *,
    research_root: Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    raw = handoff.catalog_input_jsonl_bytes
    if type(raw) is not bytes or not raw:
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "handoff catalog input must be non-empty exact bytes"
        )
    try:
        temporary = tempfile.TemporaryDirectory(
            prefix=".fotmob-reviewed-catalog-input-",
            dir=str(research_root),
        )
        input_path = Path(temporary.name) / "reviewed-fixtures.jsonl"
        with input_path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        try:
            temporary.cleanup()  # type: ignore[possibly-undefined]
        except Exception:
            pass
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "temporary reviewed catalog input could not be materialized"
        ) from exc
    return temporary, input_path


def _assert_compiler_matches_handoff(
    handoff: FotMobFixtureCatalogHandoff,
    result: FixtureCatalogResult,
) -> None:
    expected = {
        item.to_catalog_input_dict()["source_fixture_identifier"]: (
            item.to_catalog_input_dict()
        )
        for item in handoff.catalog_inputs
    }
    if len(expected) != len(handoff.catalog_inputs):
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "handoff contains duplicate source fixture identifiers"
        )
    if len(result.records) != len(expected):
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "compiler fixture count does not match reviewed handoff"
        )
    seen: set[str] = set()
    for record in result.records:
        payload = expected.get(record.source_fixture_identifier)
        if payload is None:
            raise FotMobReviewedFixtureCatalogWorkflowError(
                "compiler emitted a fixture absent from the reviewed handoff"
            )
        if record.source_fixture_identifier in seen:
            raise FotMobReviewedFixtureCatalogWorkflowError(
                "compiler emitted a duplicate source fixture identifier"
            )
        seen.add(record.source_fixture_identifier)
        checks = (
            record.fixture_identifier == f"FOTMOB:{record.source_fixture_identifier}",
            record.home_team == payload["home_team"],
            record.away_team == payload["away_team"],
            record.competition == payload["competition"],
            serialize_utc(record.kickoff) == payload["kickoff"],
            record.source_reference == payload["source_reference"],
            serialize_utc(record.reviewed_at) == payload["reviewed_at"],
            record.evidence_file_path == payload["evidence_file_path"],
            record.evidence_sha256 == payload["evidence_sha256"],
        )
        if not all(checks):
            raise FotMobReviewedFixtureCatalogWorkflowError(
                "compiler normalized data differs from the reviewed handoff"
            )
    if seen != set(expected):
        raise FotMobReviewedFixtureCatalogWorkflowError(
            "compiler output does not cover the exact reviewed handoff"
        )


def run(
    *,
    capture_directories: Sequence[str | Path],
    decision_ledger: Path,
    as_of: str,
    minimum_lead_seconds: int,
    catalog_output: Path | None = None,
    manifest_output: Path | None = None,
    check_catalog: Path | None = None,
    check_manifest: Path | None = None,
    force: bool = False,
    repository_root: Path | None = None,
    code_state: Mapping[str, Any] | None = None,
) -> FotMobReviewedFixtureCatalogWorkflowResult:
    """Rebuild explicit review state and invoke the hardened PR #29 compiler."""

    repository = (repository_root or Path(__file__).resolve().parents[1]).resolve(
        strict=True
    )
    try:
        candidate_bundle, evidence_root = _build_candidate_bundle_from_capture_directories(
            capture_directories,
            repository_root=repository,
        )
        candidate_sha = sha256_fotmob_fixture_candidate_bundle(candidate_bundle)
        decisions, ledger_sha = load_review_decision_ledger(
            decision_ledger,
            expected_candidate_bundle_sha256=candidate_sha,
        )
        review_bundle = build_fotmob_fixture_candidate_review_bundle(
            candidate_bundle,
            decisions,
        )
        handoff = build_fotmob_fixture_catalog_handoff(
            candidate_bundle,
            review_bundle,
        )
        research_root = evidence_root.parent
        temporary, input_path = _materialize_handoff_input(
            handoff,
            research_root=research_root,
        )
        try:
            result = run_fixture_catalog(
                input_path=input_path,
                evidence_root=evidence_root,
                as_of=as_of,
                minimum_lead_seconds=minimum_lead_seconds,
                catalog_output=catalog_output,
                manifest_output=manifest_output,
                check_catalog=check_catalog,
                check_manifest=check_manifest,
                force=force,
                code_state=code_state,
            )
            if input_path.read_bytes() != handoff.catalog_input_jsonl_bytes:
                raise FotMobReviewedFixtureCatalogWorkflowError(
                    "temporary handoff input changed during compilation"
                )
        finally:
            temporary.cleanup()
        _assert_compiler_matches_handoff(handoff, result)
    except FotMobReviewedFixtureCatalogWorkflowError:
        raise
    except (
        FotMobFixtureCandidateError,
        FotMobFixtureCandidateReviewError,
        FotMobFixtureCatalogHandoffError,
        FixtureCatalogCLIError,
        FixtureCatalogError,
        OSError,
        ValueError,
    ) as exc:
        raise FotMobReviewedFixtureCatalogWorkflowError(str(exc)) from exc

    mode = "GENERATE" if catalog_output is not None else "CHECK"
    return FotMobReviewedFixtureCatalogWorkflowResult(
        candidate_bundle=candidate_bundle,
        review_bundle_sha256=sha256_fotmob_fixture_candidate_review_bundle(
            review_bundle
        ),
        handoff=handoff,
        decision_ledger_sha256=ledger_sha,
        fixture_catalog_result=result,
        mode=mode,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild explicitly reviewed FotMob candidate state and invoke the "
            "hardened offline Fixture Catalog compiler."
        )
    )
    parser.add_argument(
        "--capture-directory",
        action="append",
        required=True,
        help=(
            "Repeatable verified PR #38 capture directory beneath "
            ".cache/athena-research/fotmob-data-matches-captures"
        ),
    )
    parser.add_argument(
        "--decision-ledger",
        required=True,
        help="Strict JSON explicit review-decision ledger",
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="Timezone-aware UTC audit timestamp for the PR #29 compiler",
    )
    parser.add_argument(
        "--minimum-lead-seconds",
        type=int,
        default=0,
        help="Minimum lead time before kickoff; default 0",
    )
    parser.add_argument("--force", action="store_true", help="Replace untracked outputs")
    parser.add_argument("--catalog-output")
    parser.add_argument("--manifest-output")
    parser.add_argument("--check-catalog")
    parser.add_argument("--check-manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(
            capture_directories=args.capture_directory,
            decision_ledger=Path(args.decision_ledger),
            as_of=args.as_of,
            minimum_lead_seconds=args.minimum_lead_seconds,
            catalog_output=Path(args.catalog_output) if args.catalog_output else None,
            manifest_output=Path(args.manifest_output) if args.manifest_output else None,
            check_catalog=Path(args.check_catalog) if args.check_catalog else None,
            check_manifest=Path(args.check_manifest) if args.check_manifest else None,
            force=args.force,
        )
        sys.stdout.buffer.write(result.summary_bytes)
        return 0
    except FotMobReviewedFixtureCatalogWorkflowError as exc:
        parser.exit(1, f"reviewed fixture catalog workflow failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
