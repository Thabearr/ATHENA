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
    CapturedFotMobDataMatchesResponse,
    canonical_data_matches_capture_manifest_bytes,
    manifest_from_mapping,
    sha256_data_matches_capture_manifest,
    strict_manifest_json_loads,
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
    campaign_receipt_from_bytes,
    candidate_identity,
    canonical_campaign_receipt_bytes,
    canonical_json_bytes,
    evidence_file,
    resolve_exact_target_candidate,
    safety_flags,
    verify_evidence_files,
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
    anchors: dict[str, Any],
) -> tuple[Any, bytes]:
    work = repository / ".cache/athena-research/fotmob-prospective-player-context-campaign"
    work.mkdir(parents=True, exist_ok=True)
    ledger = work / f"review-{candidate.source_match_id}.json"
    if ledger.exists():
        raise CampaignExecutionError("explicit review ledger already exists; replay forbidden")
    ledger_bytes = _review_ledger_bytes(bundle, candidate, actor=actor, at=reviewed_at)
    _write_once(ledger, ledger_bytes)
    _write_once(output_root / "fixture/review-decision-ledger.json", ledger_bytes)
    anchors["fixture_review_ledger_sha256"] = hashlib.sha256(ledger_bytes).hexdigest()
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
    _write_once(output_root / "fixture/catalog.json", result.catalog_bytes)
    _write_once(output_root / "fixture/catalog-manifest.json", result.manifest_bytes)
    anchors["fixture_catalog_sha256"] = hashlib.sha256(result.catalog_bytes).hexdigest()
    anchors["fixture_catalog_manifest_sha256"] = hashlib.sha256(
        result.manifest_bytes
    ).hexdigest()
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
    _write_once(output_root / "fixture/admission.json", admission_bytes)
    anchors["fixture_admission_sha256"] = hashlib.sha256(admission_bytes).hexdigest()
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
    _write_once(output_root / "fixture/bootstrap.json", bootstrap_bytes)
    anchors["fixture_bootstrap_sha256"] = hashlib.sha256(bootstrap_bytes).hexdigest()
    verified = verify_reviewed_fixture_intelligence_bootstrap_artifact(
        bootstrap,
        bootstrap_bytes,
        verified_at=reviewed_at,
    )
    receipt = canonical_verified_bootstrap_artifact_receipt_bytes(verified)
    _write_once(output_root / "fixture/bootstrap-verification-receipt.json", receipt)
    anchors["fixture_bootstrap_receipt_sha256"] = hashlib.sha256(receipt).hexdigest()
    return verified, receipt


def _replay_source_fixture_artifact(
    *,
    repository: Path,
    source_root: Path,
    expected_source_head_sha: str,
    output_root: Path,
) -> tuple[Path, bytes, Any, Any, dict[str, Any]]:
    """Rebuild PR38-40 from the exact first-run artifact without network."""

    source = source_root.resolve(strict=True)
    receipt_bytes = (source / "campaign-receipt.json").read_bytes()
    receipt = campaign_receipt_from_bytes(receipt_bytes)
    if receipt.campaign_result is not CampaignResult.FIXTURE_REVIEW_NOT_GRANTED:
        raise CampaignExecutionError(
            "continuation source must be an exact FIXTURE_REVIEW_NOT_GRANTED receipt"
        )
    if receipt.repository_head_sha != expected_source_head_sha:
        raise CampaignExecutionError("continuation source repository head mismatch")
    contents: dict[str, bytes] = {}
    for item in receipt.files:
        path = source / Path(item.relative_path)
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(source)
        except ValueError as exc:
            raise CampaignExecutionError("source artifact file escaped its root") from exc
        contents[item.relative_path] = resolved.read_bytes()
    verify_evidence_files(receipt.files, contents)
    fixture_raw = contents["fixture/response.json"]
    fixture_manifest_bytes = contents["fixture/manifest.json"]
    manifest = manifest_from_mapping(strict_manifest_json_loads(fixture_manifest_bytes))
    if canonical_data_matches_capture_manifest_bytes(manifest) != fixture_manifest_bytes:
        raise CampaignExecutionError("source fixture manifest is not exact canonical bytes")
    response = CapturedFotMobDataMatchesResponse(
        status=manifest.status,
        content_type=manifest.content_type,
        content_length=manifest.content_length,
        body=fixture_raw,
        observed_at=manifest.observed_at,
        network_acquisition_performed=manifest.network_acquisition_performed,
    )
    capture_directory, rebuilt_manifest = write_data_matches_capture_directory(
        response,
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        repository_root=repository,
    )
    if canonical_data_matches_capture_manifest_bytes(rebuilt_manifest) != fixture_manifest_bytes:
        raise CampaignExecutionError("replayed fixture manifest differs from source artifact")
    assessment = assess_fotmob_data_matches_schema(fixture_raw, rebuilt_manifest)
    assessment_bytes = canonical_data_matches_schema_assessment_bytes(assessment)
    if assessment_bytes != contents["fixture/schema-assessment.json"]:
        raise CampaignExecutionError("replayed PR39 assessment differs from source artifact")
    bundle = build_fotmob_fixture_candidate_bundle(((fixture_raw, rebuilt_manifest),))
    bundle_bytes = canonical_fotmob_fixture_candidate_bundle_bytes(bundle)
    if bundle_bytes != contents["fixture/fixture-candidates.json"]:
        raise CampaignExecutionError("replayed PR40 candidates differ from source artifact")
    candidate = resolve_exact_target_candidate(bundle.candidates)
    identity = candidate_identity(candidate)
    if identity["candidate_sha256"] != receipt.fixture_candidate_sha256:
        raise CampaignExecutionError("replayed candidate differs from source receipt")
    for relative, raw in (
        ("fixture/response.json", fixture_raw),
        ("fixture/manifest.json", fixture_manifest_bytes),
        ("fixture/schema-assessment.json", assessment_bytes),
        ("fixture/fixture-candidates.json", bundle_bytes),
        ("source-campaign-receipt.json", receipt_bytes),
    ):
        _write_once(output_root / relative, raw)
    return capture_directory, fixture_raw, rebuilt_manifest, bundle, identity


def _receipt(
    *,
    output_root: Path,
    base_sha: str,
    repository_head_sha: str,
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
    fixture_schema_assessment_sha256: str | None = None,
    fixture_candidate_bundle_sha256: str | None = None,
    fixture_review_ledger_sha256: str | None = None,
    fixture_catalog_sha256: str | None = None,
    fixture_catalog_manifest_sha256: str | None = None,
    fixture_admission_sha256: str | None = None,
    fixture_bootstrap_sha256: str | None = None,
    fixture_bootstrap_receipt_sha256: str | None = None,
) -> FotMobProspectivePlayerContextCampaignReceipt:
    return FotMobProspectivePlayerContextCampaignReceipt(
        repository=os.environ.get("GITHUB_REPOSITORY", "Thabearr/ATHENA"),
        base_sha=base_sha,
        repository_head_sha=repository_head_sha,
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
        fixture_schema_assessment_sha256=fixture_schema_assessment_sha256,
        fixture_candidate_bundle_sha256=fixture_candidate_bundle_sha256,
        fixture_review_ledger_sha256=fixture_review_ledger_sha256,
        fixture_catalog_sha256=fixture_catalog_sha256,
        fixture_catalog_manifest_sha256=fixture_catalog_manifest_sha256,
        fixture_admission_sha256=fixture_admission_sha256,
        fixture_bootstrap_sha256=fixture_bootstrap_sha256,
        fixture_bootstrap_receipt_sha256=fixture_bootstrap_receipt_sha256,
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
    anchors: dict[str, Any] = {
        "fixture_schema_assessment_sha256": None,
        "fixture_candidate_bundle_sha256": None,
        "fixture_review_ledger_sha256": None,
        "fixture_catalog_sha256": None,
        "fixture_catalog_manifest_sha256": None,
        "fixture_admission_sha256": None,
        "fixture_bootstrap_sha256": None,
        "fixture_bootstrap_receipt_sha256": None,
    }
    match_manifest_sha = None
    match_raw_sha = None
    match_raw_size = None
    persisted_sha = None
    structure_sha = None
    report_sha = None

    def make_receipt(result: CampaignResult) -> FotMobProspectivePlayerContextCampaignReceipt:
        return _receipt(
            output_root=output_root,
            base_sha=args.base_sha,
            repository_head_sha=head_sha,
            started_at=started_at,
            result=result,
            identity=identity,
            fixture_manifest=fixture_manifest,
            match_manifest_sha=match_manifest_sha,
            match_raw_sha=match_raw_sha,
            match_raw_size=match_raw_size,
            persisted_sha=persisted_sha,
            structure_sha=structure_sha,
            report_sha=report_sha,
            **anchors,
        )

    try:
        if args.campaign_mode == "CAPTURE_FIXTURE":
            if (
                args.source_campaign_artifact_directory is not None
                or args.source_repository_head_sha
                or args.fixture_review_candidate_sha
                or args.fixture_review_disposition != "NOT_GRANTED"
                or args.catalog_admission_disposition != "NOT_GRANTED"
            ):
                raise CampaignExecutionError(
                    "capture mode cannot carry review or continuation authority"
                )
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
            assessment_bytes = canonical_data_matches_schema_assessment_bytes(assessment)
            _write_once(output_root / "fixture/schema-assessment.json", assessment_bytes)
            anchors["fixture_schema_assessment_sha256"] = hashlib.sha256(
                assessment_bytes
            ).hexdigest()
            try:
                bundle = build_fotmob_fixture_candidate_bundle(
                    ((fixture_raw, fixture_manifest),)
                )
            except Exception:
                final = CampaignResult.FIXTURE_CANDIDATE_EXTRACTION_FAILED
                raise
            bundle_bytes = canonical_fotmob_fixture_candidate_bundle_bytes(bundle)
            _write_once(output_root / "fixture/fixture-candidates.json", bundle_bytes)
            anchors["fixture_candidate_bundle_sha256"] = hashlib.sha256(
                bundle_bytes
            ).hexdigest()
            try:
                candidate = resolve_exact_target_candidate(bundle.candidates)
            except FotMobProspectivePlayerContextCampaignError:
                final = CampaignResult.TARGET_FIXTURE_NOT_EXACTLY_RESOLVED
                raise
            identity = candidate_identity(candidate)
            final = CampaignResult.FIXTURE_REVIEW_NOT_GRANTED
            receipt = make_receipt(final)
            _write_once(output_root / "campaign-receipt.json", canonical_campaign_receipt_bytes(receipt))
            return final

        if args.campaign_mode != "CONTINUE_EXACT_FIXTURE_ARTIFACT":
            raise CampaignExecutionError("unknown campaign mode")
        if (
            args.source_campaign_artifact_directory is None
            or not args.source_repository_head_sha
            or args.fixture_review_disposition != "APPROVED"
            or args.catalog_admission_disposition != "ADMITTED"
            or not args.fixture_review_candidate_sha
        ):
            raise CampaignExecutionError(
                "continuation requires exact source artifact and both explicit review gates"
            )
        (
            capture_directory,
            fixture_raw,
            fixture_manifest,
            bundle,
            identity,
        ) = _replay_source_fixture_artifact(
            repository=repository,
            source_root=args.source_campaign_artifact_directory,
            expected_source_head_sha=args.source_repository_head_sha,
            output_root=output_root,
        )
        anchors["fixture_schema_assessment_sha256"] = hashlib.sha256(
            (output_root / "fixture/schema-assessment.json").read_bytes()
        ).hexdigest()
        anchors["fixture_candidate_bundle_sha256"] = hashlib.sha256(
            (output_root / "fixture/fixture-candidates.json").read_bytes()
        ).hexdigest()
        candidate = resolve_exact_target_candidate(bundle.candidates)
        if args.fixture_review_candidate_sha != identity["candidate_sha256"]:
            raise CampaignExecutionError(
                "explicit review SHA differs from exact replayed PR40 candidate"
            )
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
            anchors=anchors,
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
        match_raw_sha = hashlib.sha256(match_raw).hexdigest()
        match_raw_size = len(match_raw)
        match_manifest_sha = hashlib.sha256(match_manifest).hexdigest()
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
        persisted_sha = hashlib.sha256(persisted_bytes).hexdigest()
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
        structure_sha = sha256_reviewed_match_details_structure(structure)
        report = build_player_context_review_candidate_report(
            structure,
            observed_at=persisted.observed_at,
        )
        report_bytes = canonical_json_bytes(report)
        _write_once(output_root / "player-context-review-candidates.json", report_bytes)
        report_sha = hashlib.sha256(report_bytes).hexdigest()
        final = (
            CampaignResult.SUCCESS_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAPTURED
            if report["candidate_count"] > 0
            else CampaignResult.NO_PLAYER_CONTEXT_CANDIDATE_STRUCTURE_OBSERVED
        )
        receipt = make_receipt(final)
        _write_once(output_root / "campaign-receipt.json", canonical_campaign_receipt_bytes(receipt))
        return final
    except Exception as exc:
        # Preserve every successfully committed stage. Expected fail-closed
        # campaign states are evidence and still receive a canonical receipt.
        if not (output_root / "campaign-receipt.json").exists():
            receipt = make_receipt(final)
            _write_once(output_root / "campaign-receipt.json", canonical_campaign_receipt_bytes(receipt))
        print(f"campaign failed closed at {final.value}: {type(exc).__name__}: {exc}", file=os.sys.stderr)
        return final


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--repository-head-sha", required=True)
    parser.add_argument(
        "--campaign-mode",
        choices=("CAPTURE_FIXTURE", "CONTINUE_EXACT_FIXTURE_ARTIFACT"),
        required=True,
    )
    parser.add_argument("--source-campaign-artifact-directory", type=Path)
    parser.add_argument("--source-repository-head-sha", default="")
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
