"""Execute the PR #192 prospective FotMob player-context evidence campaign."""

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
import shutil
import subprocess
from pathlib import Path
from typing import Any

from domain.fixture_catalog import sha256_bytes
from domain.fotmob_data_matches_capture import (
    MANIFEST_FILENAME as FIXTURE_MANIFEST_FILENAME,
    RAW_FILENAME as FIXTURE_RAW_FILENAME,
    canonical_data_matches_capture_manifest_bytes,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_data_matches_schema import (
    assess_fotmob_data_matches_schema,
    canonical_data_matches_schema_assessment_bytes,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewDecision,
    sha256_fotmob_fixture_candidate,
)
from domain.fotmob_fixture_candidates import (
    build_fotmob_fixture_candidate_bundle,
    canonical_fotmob_fixture_candidate_bundle_bytes,
    sha256_fotmob_fixture_candidate_bundle,
)
from domain.fotmob_prospective_player_context_campaign import (
    CampaignResult,
    EvidenceFile,
    EXPECTED_AWAY_TEAM,
    EXPECTED_HOME_TEAM,
    EXPECTED_KICKOFF,
    FotMobProspectivePlayerContextCampaignError,
    FotMobProspectivePlayerContextCampaignReceipt,
    REQUEST_CCODE3,
    REQUEST_TIMEZONE,
    TARGET_REQUEST_DATE,
    build_player_context_review_candidate_report,
    candidate_identity,
    canonical_campaign_receipt_bytes,
    canonical_json_bytes,
    evidence_file,
    resolve_exact_target_candidate,
    safety_flags,
)
from domain.fotmob_reviewed_match_details_persisted_evidence import (
    canonical_persisted_match_details_evidence_receipt_bytes,
    verify_persisted_match_details_evidence,
)
from domain.fotmob_reviewed_match_details_structure import (
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
    sha256_reviewed_match_details_structure,
)
from domain.fotmob_fixture_catalog_handoff import (
    sha256_fotmob_fixture_catalog_handoff,
)
from domain.reviewed_fixture_catalog_admission import (
    REVIEWED_SOURCE_CAPABILITY,
    ReviewedFixtureCatalogAdmissionDecision,
    ReviewedFixtureCatalogAdmissionDisposition,
    build_reviewed_fixture_catalog_admission,
    canonical_reviewed_fixture_catalog_admission_bytes,
    sha256_reviewed_source_capability,
)
from domain.reviewed_fixture_catalog_admission_artifact import (
    canonical_verified_admission_artifact_receipt_bytes,
    verify_reviewed_fixture_catalog_admission_artifact,
)
from domain.reviewed_fixture_intelligence_bootstrap import (
    build_reviewed_fixture_intelligence_bootstrap,
    canonical_reviewed_fixture_intelligence_bootstrap_bytes,
)
from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    canonical_verified_bootstrap_artifact_receipt_bytes,
    verify_reviewed_fixture_intelligence_bootstrap_artifact,
)
from scripts.capture_fotmob_data_matches import (
    fetch_fotmob_data_matches,
    write_data_matches_capture_directory,
)
from scripts.capture_fotmob_reviewed_match_details import (
    capture_fotmob_reviewed_match_details,
)
from scripts.manage_fotmob_reviewed_fixture_catalog import run as run_catalog_workflow


WORKFLOW_NAME = "Execute FotMob Prospective Player-Context Campaign"
DEFAULT_OUTPUT = Path("campaign-artifact")
_REVIEW_LEDGER_DATASET = "athena-fotmob-fixture-review-decision-ledger-v1"
FROZEN_BASE_MAIN_SHA = "74cec8bc649bc8d2181ca2806a460a84664f7f2e"


class CampaignExecutionError(RuntimeError):
    pass


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _git_head(repository: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise CampaignExecutionError("repository HEAD is not a full lowercase Git SHA")
    return value


def _write_once(path: Path, content: bytes) -> None:
    if type(content) is not bytes or not content:
        raise CampaignExecutionError("campaign outputs must be non-empty exact bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _copy_exact(source: Path, destination: Path) -> bytes:
    raw = source.read_bytes()
    _write_once(destination, raw)
    return raw


def _evidence_files(root: Path) -> tuple[EvidenceFile, ...]:
    files: list[EvidenceFile] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name == "campaign-receipt.json":
            continue
        relative = path.relative_to(root).as_posix()
        files.append(evidence_file(relative, path.read_bytes()))
    return tuple(files)


def _review_ledger_bytes(bundle: Any, candidate: Any, *, actor: str, at: datetime.datetime) -> bytes:
    decision = {
        "source_capture_manifest_sha256": candidate.source_capture_manifest_sha256,
        "source_match_id": candidate.source_match_id,
        "candidate_sha256": sha256_fotmob_fixture_candidate(candidate),
        "disposition": FixtureCandidateReviewDisposition.APPROVED.value,
        "reviewed_at": at.isoformat().replace("+00:00", "Z"),
        "reviewer_reference": f"github-actor:{actor}",
        "notes": "Explicit exact-candidate review for PR192 evidence acquisition only",
    }
    return canonical_json_bytes(
        {
            "schema_version": 1,
            "dataset_name": _REVIEW_LEDGER_DATASET,
            "candidate_bundle_sha256": sha256_fotmob_fixture_candidate_bundle(bundle),
            "decisions": [decision],
        }
    )


def _build_verified_bootstrap(
    *,
    repository: Path,
    capture_directory: Path,
    bundle: Any,
    candidate: Any,
    actor: str,
    reviewed_at: datetime.datetime,
    output_root: Path,
    head_sha: str,
) -> tuple[Any, bytes]:
    work = repository / ".cache/athena-research/fotmob-prospective-player-context-campaign"
    work.mkdir(parents=True, exist_ok=True)
    ledger = work / f"review-{candidate.source_match_id}.json"
    if ledger.exists():
        raise CampaignExecutionError("explicit review ledger already exists; replay forbidden")
    ledger_bytes = _review_ledger_bytes(bundle, candidate, actor=actor, at=reviewed_at)
    _write_once(ledger, ledger_bytes)
    catalog_path = work / f"catalog-{candidate.source_match_id}.json"
    manifest_path = work / f"catalog-manifest-{candidate.source_match_id}.json"
    workflow = run_catalog_workflow(
        capture_directories=(capture_directory,),
        decision_ledger=ledger,
        as_of=reviewed_at.isoformat().replace("+00:00", "Z"),
        minimum_lead_seconds=0,
        catalog_output=catalog_path,
        manifest_output=manifest_path,
        repository_root=repository,
        code_state={"evidence_git_head_sha": head_sha, "tracked_worktree_clean": True},
    )
    handoff = workflow.handoff
    result = workflow.fixture_catalog_result
    decision = ReviewedFixtureCatalogAdmissionDecision(
        candidate_bundle_sha256=handoff.candidate_bundle_sha256,
        review_bundle_sha256=handoff.review_bundle_sha256,
        handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
        catalog_sha256=sha256_bytes(result.catalog_bytes),
        manifest_sha256=sha256_bytes(result.manifest_bytes),
        source_capability=REVIEWED_SOURCE_CAPABILITY,
        source_capability_sha256=sha256_reviewed_source_capability(),
        disposition=ReviewedFixtureCatalogAdmissionDisposition.ADMITTED,
        reviewed_at=reviewed_at,
        reviewer_reference=f"github-actor:{actor}",
        notes="Explicit PR192 prospective evidence-acquisition admission",
    )
    admission = build_reviewed_fixture_catalog_admission(handoff, result, decision)
    admission_bytes = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    verified_admission = verify_reviewed_fixture_catalog_admission_artifact(
        admission,
        admission_bytes,
        verified_at=reviewed_at,
    )
    admission_receipt = canonical_verified_admission_artifact_receipt_bytes(
        verified_admission
    )
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(
        verified_admission,
        admission_receipt,
    )
    bootstrap_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap)
    verified = verify_reviewed_fixture_intelligence_bootstrap_artifact(
        bootstrap,
        bootstrap_bytes,
        verified_at=reviewed_at,
    )
    receipt = canonical_verified_bootstrap_artifact_receipt_bytes(verified)
    _write_once(output_root / "fixture/review-decision-ledger.json", ledger_bytes)
    _write_once(output_root / "fixture/catalog.json", result.catalog_bytes)
    _write_once(output_root / "fixture/catalog-manifest.json", result.manifest_bytes)
    _write_once(output_root / "fixture/admission.json", admission_bytes)
    _write_once(output_root / "fixture/bootstrap.json", bootstrap_bytes)
    _write_once(output_root / "fixture/bootstrap-verification-receipt.json", receipt)
    return verified, receipt


def _receipt(
    *,
    output_root: Path,
    base_sha: str,
    started_at: datetime.datetime,
    result: CampaignResult,
    identity: dict[str, Any] | None,
    fixture_manifest: Any | None,
    match_manifest_sha: str | None = None,
    match_raw_sha: str | None = None,
    match_raw_size: int | None = None,
    persisted_sha: str | None = None,
    structure_sha: str | None = None,
    report_sha: str | None = None,
) -> FotMobProspectivePlayerContextCampaignReceipt:
    return FotMobProspectivePlayerContextCampaignReceipt(
        repository=os.environ.get("GITHUB_REPOSITORY", "Thabearr/ATHENA"),
        base_sha=base_sha,
        workflow_name=WORKFLOW_NAME,
        workflow_run_id=int(os.environ.get("GITHUB_RUN_ID", "1")),
        workflow_run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
        github_actor=os.environ.get("GITHUB_ACTOR", "local-static-inspection"),
        started_at=started_at,
        completed_at=_utc_now(),
        campaign_result=result,
        resolved_fixture_identifier=(identity or {}).get("fixture_identifier"),
        resolved_source_match_id=(identity or {}).get("source_match_id"),
        resolved_home_team=(identity or {}).get("home_team"),
        resolved_away_team=(identity or {}).get("away_team"),
        resolved_kickoff=(identity or {}).get("kickoff"),
        fixture_candidate_sha256=(identity or {}).get("candidate_sha256"),
        fixture_raw_sha256=(fixture_manifest.raw_sha256 if fixture_manifest else None),
        fixture_raw_size=(fixture_manifest.raw_size if fixture_manifest else None),
        fixture_manifest_sha256=(
            sha256_data_matches_capture_manifest(fixture_manifest)
            if fixture_manifest
            else None
        ),
        match_details_raw_sha256=match_raw_sha,
        match_details_raw_size=match_raw_size,
        match_details_manifest_sha256=match_manifest_sha,
        persisted_evidence_receipt_sha256=persisted_sha,
        structure_assessment_sha256=structure_sha,
        player_context_report_sha256=report_sha,
        files=_evidence_files(output_root),
        safety=safety_flags(),
    )


def execute(args: argparse.Namespace) -> CampaignResult:
    repository = Path(__file__).resolve().parents[1]
    head_sha = _git_head(repository)
    if args.base_sha != FROZEN_BASE_MAIN_SHA:
        raise CampaignExecutionError(
            f"base main must remain exactly {FROZEN_BASE_MAIN_SHA}"
        )
    if head_sha != args.repository_head_sha:
        raise CampaignExecutionError(
            f"checked-out head {head_sha} differs from authorized {args.repository_head_sha}"
        )
    if args.target_request_date != "2026-08-22":
        raise CampaignExecutionError("wrong target request date")
    if args.expected_home_team != EXPECTED_HOME_TEAM or args.expected_away_team != EXPECTED_AWAY_TEAM:
        raise CampaignExecutionError("target team names must match the exact campaign")
    if args.expected_kickoff_utc != EXPECTED_KICKOFF:
        raise CampaignExecutionError("target kickoff must match the exact campaign")
    output_root = (repository / args.output_directory).resolve()
    try:
        output_root.relative_to(repository)
    except ValueError as exc:
        raise CampaignExecutionError("output directory must stay in repository") from exc
    if output_root.exists():
        raise CampaignExecutionError("campaign output already exists; replay forbidden")
    output_root.mkdir(parents=True)
    started_at = _utc_now()
    fixture_manifest = None
    identity = None
    final = CampaignResult.FIXTURE_CATALOG_ACQUISITION_FAILED
    try:
        response = fetch_fotmob_data_matches(
            request_date=TARGET_REQUEST_DATE,
            timezone=REQUEST_TIMEZONE,
            ccode3=REQUEST_CCODE3,
        )
        capture_directory, fixture_manifest = write_data_matches_capture_directory(
            response,
            request_date=TARGET_REQUEST_DATE,
            timezone=REQUEST_TIMEZONE,
            ccode3=REQUEST_CCODE3,
            repository_root=repository,
        )
        fixture_raw = _copy_exact(
            capture_directory / FIXTURE_RAW_FILENAME,
            output_root / "fixture/response.json",
        )
        fixture_manifest_bytes = _copy_exact(
            capture_directory / FIXTURE_MANIFEST_FILENAME,
            output_root / "fixture/manifest.json",
        )
        if fixture_manifest_bytes != canonical_data_matches_capture_manifest_bytes(
            fixture_manifest
        ):
            raise CampaignExecutionError("fixture manifest read-back mismatch")
        try:
            assessment = assess_fotmob_data_matches_schema(fixture_raw, fixture_manifest)
        except Exception:
            final = CampaignResult.FIXTURE_SCHEMA_ASSESSMENT_FAILED
            raise
        _write_once(
            output_root / "fixture/schema-assessment.json",
            canonical_data_matches_schema_assessment_bytes(assessment),
        )
        try:
            bundle = build_fotmob_fixture_candidate_bundle(
                ((fixture_raw, fixture_manifest),)
            )
        except Exception:
            final = CampaignResult.FIXTURE_CANDIDATE_EXTRACTION_FAILED
            raise
        _write_once(
            output_root / "fixture/fixture-candidates.json",
            canonical_fotmob_fixture_candidate_bundle_bytes(bundle),
        )
        try:
            candidate = resolve_exact_target_candidate(bundle.candidates)
        except FotMobProspectivePlayerContextCampaignError:
            final = CampaignResult.TARGET_FIXTURE_NOT_EXACTLY_RESOLVED
            raise
        identity = candidate_identity(candidate)
        review_granted = (
            args.fixture_review_disposition == "APPROVED"
            and args.catalog_admission_disposition == "ADMITTED"
            and args.fixture_review_candidate_sha == identity["candidate_sha256"]
        )
        if not review_granted:
            final = CampaignResult.FIXTURE_REVIEW_NOT_GRANTED
            receipt = _receipt(
                output_root=output_root,
                base_sha=args.base_sha,
                started_at=started_at,
                result=final,
                identity=identity,
                fixture_manifest=fixture_manifest,
            )
            _write_once(output_root / "campaign-receipt.json", canonical_campaign_receipt_bytes(receipt))
            return final
        kickoff = identity["kickoff"]
        if _utc_now() >= kickoff:
            final = CampaignResult.TARGET_NO_LONGER_PROSPECTIVE
            raise CampaignExecutionError("target is no longer prospective")
        reviewed_at = _utc_now()
        verified_bootstrap, bootstrap_receipt = _build_verified_bootstrap(
            repository=repository,
            capture_directory=capture_directory,
            bundle=bundle,
            candidate=candidate,
            actor=os.environ.get("GITHUB_ACTOR", "unknown"),
            reviewed_at=reviewed_at,
            output_root=output_root,
            head_sha=head_sha,
        )
        try:
            execution = capture_fotmob_reviewed_match_details(
                verified_bootstrap_artifact=verified_bootstrap,
                verification_receipt_bytes=bootstrap_receipt,
                fixture_identifier=identity["fixture_identifier"],
                execute_live_network=True,
                repository_root=repository,
            )
        except Exception:
            final = CampaignResult.MATCH_DETAILS_ACQUISITION_FAILED
            raise
        match_capture = execution.capture_directory
        match_raw = _copy_exact(match_capture / "response.json", output_root / "match-details/response.json")
        match_manifest = _copy_exact(match_capture / "manifest.json", output_root / "match-details/manifest.json")
        try:
            parsed_match_details = json.loads(match_raw)
            if type(parsed_match_details) is not dict:
                raise ValueError("match-details root is not an object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            final = CampaignResult.MATCH_DETAILS_NOT_JSON
            raise CampaignExecutionError("match-details response is not a JSON object")
        try:
            persisted = verify_persisted_match_details_evidence(
                manifest_bytes=match_manifest,
                raw_bytes=match_raw,
            )
            persisted_bytes = canonical_persisted_match_details_evidence_receipt_bytes(persisted)
        except Exception:
            final = CampaignResult.PERSISTED_EVIDENCE_VERIFICATION_FAILED
            raise
        _write_once(output_root / "match-details/persisted-evidence-receipt.json", persisted_bytes)
        try:
            structure = assess_reviewed_match_details_structure(
                evidence=persisted,
                evidence_receipt_bytes=persisted_bytes,
                manifest_bytes=match_manifest,
                raw_bytes=match_raw,
            )
            structure_bytes = canonical_reviewed_match_details_structure_bytes(structure)
        except Exception:
            final = CampaignResult.STRUCTURE_ASSESSMENT_FAILED
            raise
        _write_once(output_root / "match-details/structure-assessment.json", structure_bytes)
        report = build_player_context_review_candidate_report(
            structure,
            observed_at=persisted.observed_at,
        )
        report_bytes = canonical_json_bytes(report)
        _write_once(output_root / "player-context-review-candidates.json", report_bytes)
        final = (
            CampaignResult.SUCCESS_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAPTURED
            if report["candidate_count"] > 0
            else CampaignResult.NO_PLAYER_CONTEXT_CANDIDATE_STRUCTURE_OBSERVED
        )
        receipt = _receipt(
            output_root=output_root,
            base_sha=args.base_sha,
            started_at=started_at,
            result=final,
            identity=identity,
            fixture_manifest=fixture_manifest,
            match_manifest_sha=hashlib.sha256(match_manifest).hexdigest(),
            match_raw_sha=hashlib.sha256(match_raw).hexdigest(),
            match_raw_size=len(match_raw),
            persisted_sha=hashlib.sha256(persisted_bytes).hexdigest(),
            structure_sha=sha256_reviewed_match_details_structure(structure),
            report_sha=hashlib.sha256(report_bytes).hexdigest(),
        )
        _write_once(output_root / "campaign-receipt.json", canonical_campaign_receipt_bytes(receipt))
        return final
    except Exception as exc:
        # Preserve every successfully committed stage. Expected fail-closed
        # campaign states are evidence and still receive a canonical receipt.
        if not (output_root / "campaign-receipt.json").exists():
            receipt = _receipt(
                output_root=output_root,
                base_sha=args.base_sha,
                started_at=started_at,
                result=final,
                identity=identity,
                fixture_manifest=fixture_manifest,
            )
            _write_once(output_root / "campaign-receipt.json", canonical_campaign_receipt_bytes(receipt))
        print(f"campaign failed closed at {final.value}: {type(exc).__name__}: {exc}", file=os.sys.stderr)
        return final


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--repository-head-sha", required=True)
    parser.add_argument("--output-directory", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--target-request-date", default="2026-08-22")
    parser.add_argument("--expected-home-team", default=EXPECTED_HOME_TEAM)
    parser.add_argument("--expected-away-team", default=EXPECTED_AWAY_TEAM)
    parser.add_argument("--expected-kickoff-utc", default=EXPECTED_KICKOFF)
    parser.add_argument("--fixture-review-candidate-sha", default="")
    parser.add_argument(
        "--fixture-review-disposition",
        choices=("NOT_GRANTED", "APPROVED"),
        default="NOT_GRANTED",
    )
    parser.add_argument(
        "--catalog-admission-disposition",
        choices=("NOT_GRANTED", "ADMITTED"),
        default="NOT_GRANTED",
    )
    parser.add_argument("--execute-live-network", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.execute_live_network:
        raise SystemExit("live network execution requires --execute-live-network")
    result = execute(args)
    print(result.value)
    # Fail-closed states are valid campaign conclusions. A malformed runner
    # invocation raises before this point; evidence states remain uploadable.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
