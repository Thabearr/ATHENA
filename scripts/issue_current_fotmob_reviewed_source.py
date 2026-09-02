"""Issue a reviewed current FotMob fixture bootstrap from transparent evidence.

The live entry point performs exactly one reviewed PR #38 `/api/data/matches`
request for the requested date, durably preserves it, applies the separately
reviewed PR243 fixture-identity policy, and then composes the existing
PR41->PR48 catalog/admission/bootstrap chain.

The reviewed PR243 recency and lead bounds are part of the domain policy itself.
Neither live execution nor replay can weaken them through arguments.

This script deliberately stops at verified fixture identity. It does not parse
legacy browser-impersonated evidence, create Fixture Intelligence facts, infer
probabilities, inspect bookmaker prices, select markets, generate a SportyBet
code, or place a wager.
"""
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from domain.current_fotmob_fixture_review_policy import (
    DEFAULT_MAX_SOURCE_AGE_SECONDS,
    DEFAULT_MINIMUM_LEAD_SECONDS,
    POLICY_ID,
    REVIEWER_REFERENCE,
    SHADOW_MINIMUM_LEAD_SECONDS,
    SHADOW_POLICY_ID,
    SHADOW_REVIEWER_REFERENCE,
    CurrentFotMobFixtureReviewPolicyResult,
    build_current_fotmob_fixture_review_policy_result,
    build_current_shadow_fotmob_fixture_review_policy_result,
    canonical_current_fotmob_fixture_review_policy_result_bytes,
    reviewer_reference_for_policy_id,
)
from domain.fixture_catalog import compile_fixture_catalog, sha256_bytes
from domain.fotmob_data_matches_capture import (
    RAW_FILENAME,
    FotMobDataMatchesCaptureError,
    verify_data_matches_capture_directory,
)
from domain.current_fotmob_fixture_candidate_adapter import (
    build_current_fotmob_fixture_candidate_bundle,
)
from domain.fotmob_fixture_catalog_handoff import (
    FotMobFixtureCatalogHandoff,
    build_fotmob_fixture_catalog_handoff,
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
    ReviewedFixtureIntelligenceBootstrap,
    build_reviewed_fixture_intelligence_bootstrap,
    canonical_reviewed_fixture_intelligence_bootstrap_bytes,
)
from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    VerifiedReviewedFixtureIntelligenceBootstrapArtifact,
    canonical_verified_bootstrap_artifact_receipt_bytes,
    verify_reviewed_fixture_intelligence_bootstrap_artifact,
)
from scripts.capture_fotmob_data_matches import (
    ALLOWED_OUTPUT_RELATIVE as DATA_MATCHES_CAPTURE_ROOT,
    FotMobDataMatchesNetworkError,
    fetch_fotmob_data_matches,
    write_data_matches_capture_directory,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-fotmob-reviewed-source-execution-v1"
STATUS_READY = "REVIEWED_CURRENT_FOTMOB_FIXTURE_BOOTSTRAP_VERIFIED"
STATUS_NO_FIXTURES = "NO_POLICY_APPROVED_CURRENT_FOTMOB_FIXTURES"
NEXT_REQUIRED_BOUNDARY = (
    "CURRENT_REVIEWED_FOTMOB_SEMANTIC_FACT_OR_MODEL_FEATURE_ISSUER_REQUIRED"
)
ADMISSION_REVIEWER_REFERENCE = (
    "athena-policy:pr243-current-fotmob-catalog-admission-v1"
)
SHADOW_ADMISSION_REVIEWER_REFERENCE = (
    "athena-policy:current-shadow-fotmob-catalog-admission-v2"
)
WORK_ROOT = Path(".cache/athena-research/current-fotmob-reviewed-source")


class CurrentFotMobReviewedSourceError(RuntimeError):
    """Raised when current reviewed source issuance cannot fail closed."""


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise CurrentFotMobReviewedSourceError(f"{label} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise CurrentFotMobReviewedSourceError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentFotMobReviewedSourceError(f"{label} is invalid") from exc


def _repo_root(repository_root: Path | None) -> Path:
    candidate = repository_root or Path(__file__).resolve().parents[1]
    try:
        candidate = Path(candidate)
        if candidate.is_symlink() or not candidate.is_dir():
            raise CurrentFotMobReviewedSourceError(
                "repository_root must be an existing non-symlink directory"
            )
        return candidate.resolve(strict=True)
    except CurrentFotMobReviewedSourceError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise CurrentFotMobReviewedSourceError("repository_root is invalid") from exc


def _safe_work_root(repository: Path) -> Path:
    root = repository / WORK_ROOT
    current = repository
    for part in WORK_ROOT.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise CurrentFotMobReviewedSourceError(
                    "current source work root contains a forbidden symlink/non-directory"
                )
        else:
            current.mkdir()
    return root


def _read_capture_raw(capture_directory: Path) -> bytes:
    path = capture_directory / RAW_FILENAME
    if path.is_symlink() or not path.is_file():
        raise CurrentFotMobReviewedSourceError(
            "verified data-matches response.json is unavailable"
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CurrentFotMobReviewedSourceError(
            "verified data-matches response.json could not be read"
        ) from exc


def _write_result(path: Path, payload: Mapping[str, Any]) -> None:
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


@dataclasses.dataclass(frozen=True)
class CurrentFotMobReviewedSourceExecution:
    schema_version: int
    dataset_name: str
    status: str
    policy_result: CurrentFotMobFixtureReviewPolicyResult
    handoff: FotMobFixtureCatalogHandoff
    bootstrap: ReviewedFixtureIntelligenceBootstrap
    verified_bootstrap: VerifiedReviewedFixtureIntelligenceBootstrapArtifact
    verified_bootstrap_receipt_bytes: bytes
    source_capture_directory: Path
    source_capture_manifest_sha256: str
    source_raw_sha256: str
    issued_at: dt.datetime
    next_required_boundary: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise CurrentFotMobReviewedSourceError("execution schema mismatch")
        if self.status != STATUS_READY:
            raise CurrentFotMobReviewedSourceError("execution status mismatch")
        if type(self.policy_result) is not CurrentFotMobFixtureReviewPolicyResult:
            raise CurrentFotMobReviewedSourceError("policy_result type mismatch")
        if type(self.handoff) is not FotMobFixtureCatalogHandoff:
            raise CurrentFotMobReviewedSourceError("handoff type mismatch")
        if type(self.bootstrap) is not ReviewedFixtureIntelligenceBootstrap:
            raise CurrentFotMobReviewedSourceError("bootstrap type mismatch")
        if type(self.verified_bootstrap) is not VerifiedReviewedFixtureIntelligenceBootstrapArtifact:
            raise CurrentFotMobReviewedSourceError("verified_bootstrap type mismatch")
        if type(self.verified_bootstrap_receipt_bytes) is not bytes:
            raise CurrentFotMobReviewedSourceError(
                "verified_bootstrap_receipt_bytes must be exact bytes"
            )
        expected_receipt = canonical_verified_bootstrap_artifact_receipt_bytes(
            self.verified_bootstrap
        )
        if self.verified_bootstrap_receipt_bytes != expected_receipt:
            raise CurrentFotMobReviewedSourceError(
                "verified bootstrap receipt bytes mismatch"
            )
        if self.policy_result.review_bundle != self.handoff.review_bundle:
            raise CurrentFotMobReviewedSourceError(
                "handoff does not contain exact PR243 review bundle"
            )
        if self.verified_bootstrap.bootstrap != self.bootstrap:
            raise CurrentFotMobReviewedSourceError(
                "verified bootstrap does not contain exact bootstrap"
            )
        if len(self.bootstrap.fixtures) != self.policy_result.policy_approved_count:
            raise CurrentFotMobReviewedSourceError(
                "verified bootstrap fixture count differs from policy approvals"
            )
        sources = self.handoff.candidate_bundle.sources
        if type(sources) is not tuple or len(sources) != 1:
            raise CurrentFotMobReviewedSourceError(
                "current source execution must bind exactly one PR38 capture source"
            )
        source = sources[0]
        if self.source_capture_manifest_sha256 != source.source_capture_manifest_sha256:
            raise CurrentFotMobReviewedSourceError(
                "source_capture_manifest_sha256 does not anchor the exact handoff source"
            )
        if self.source_raw_sha256 != source.source_raw_sha256:
            raise CurrentFotMobReviewedSourceError(
                "source_raw_sha256 does not anchor the exact handoff source"
            )
        for value, label in (
            (self.source_capture_manifest_sha256, "source_capture_manifest_sha256"),
            (self.source_raw_sha256, "source_raw_sha256"),
        ):
            if type(value) is not str or len(value) != 64 or any(
                ch not in "0123456789abcdef" for ch in value
            ):
                raise CurrentFotMobReviewedSourceError(f"{label} must be SHA-256")
        directory = Path(self.source_capture_directory)
        if directory.is_symlink() or not directory.is_dir():
            raise CurrentFotMobReviewedSourceError(
                "source_capture_directory must be existing non-symlink directory"
            )
        issued_at = _utc(self.issued_at, "issued_at")
        if issued_at != self.policy_result.reviewed_at:
            raise CurrentFotMobReviewedSourceError(
                "issued_at does not match the exact PR243 policy review time"
            )
        if self.verified_bootstrap.verified_at != issued_at:
            raise CurrentFotMobReviewedSourceError(
                "verified bootstrap time does not match execution issued_at"
            )
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise CurrentFotMobReviewedSourceError("next boundary mismatch")
        object.__setattr__(self, "source_capture_directory", directory)
        object.__setattr__(self, "issued_at", issued_at)

    def summary(self) -> dict[str, Any]:
        policy_id = self.policy_result.policy_id
        reviewer_reference = reviewer_reference_for_policy_id(policy_id)
        if policy_id == POLICY_ID:
            policy_authority = {
                "pr243_fixture_identity_policy_decisions": True,
            }
        elif policy_id == SHADOW_POLICY_ID:
            policy_authority = {
                "current_shadow_fixture_identity_policy_v2_decisions": True,
            }
        else:
            raise CurrentFotMobReviewedSourceError(
                "execution contains an unknown current fixture policy"
            )
        authority = {
            "transparent_fotmob_network_capture": True,
            **policy_authority,
            "reviewed_fixture_bootstrap": True,
            "fixture_intelligence_fact": False,
            "fixture_intelligence_snapshot": False,
            "model_feature": False,
            "probability": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "bet": False,
        }
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "policy_id": policy_id,
            "policy_reviewer_reference": reviewer_reference,
            "source_capture_directory": self.source_capture_directory.as_posix(),
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "issued_at": self.issued_at.isoformat().replace("+00:00", "Z"),
            "minimum_lead_seconds": self.policy_result.minimum_lead_seconds,
            "max_source_age_seconds": self.policy_result.max_source_age_seconds,
            "candidate_count": self.policy_result.candidate_count,
            "exact_competition_identity_count": (
                self.policy_result.exact_competition_identity_count
            ),
            "pr41_blocked_count": self.policy_result.pr41_blocked_count,
            "stale_source_excluded_count": (
                self.policy_result.stale_source_excluded_count
            ),
            "request_date_excluded_count": (
                self.policy_result.request_date_excluded_count
            ),
            "lead_window_excluded_count": (
                self.policy_result.lead_window_excluded_count
            ),
            "policy_approved_count": self.policy_result.policy_approved_count,
            "policy_result_sha256": hashlib.sha256(
                canonical_current_fotmob_fixture_review_policy_result_bytes(
                    self.policy_result
                )
            ).hexdigest(),
            "handoff_sha256": sha256_fotmob_fixture_catalog_handoff(self.handoff),
            "bootstrap_sha256": self.verified_bootstrap.bootstrap_sha256,
            "verified_bootstrap_receipt_sha256": hashlib.sha256(
                self.verified_bootstrap_receipt_bytes
            ).hexdigest(),
            "fixture_identifiers": [
                item.fixture_identifier for item in self.bootstrap.fixtures
            ],
            "next_required_boundary": self.next_required_boundary,
            "authority": authority,
            "wager_placed": False,
        }


def _build_verified_current_fotmob_bootstrap_from_capture(
    capture_directory: Path,
    *,
    issued_at: Any,
    repository_root: Path | None = None,
    code_state: Mapping[str, Any] | None = None,
    shadow_policy: bool,
) -> CurrentFotMobReviewedSourceExecution:
    """Replay one exact PR38 capture through one fixed reviewed current policy."""

    repository = _repo_root(repository_root)
    capture_root = repository / DATA_MATCHES_CAPTURE_ROOT
    try:
        manifest = verify_data_matches_capture_directory(
            capture_directory,
            allowed_root=capture_root,
            require_network_acquisition_performed=True,
        )
    except FotMobDataMatchesCaptureError as exc:
        raise CurrentFotMobReviewedSourceError(
            "current data-matches capture failed exact PR38 replay"
        ) from exc
    raw = _read_capture_raw(Path(capture_directory))
    candidate_bundle = build_current_fotmob_fixture_candidate_bundle(raw, manifest)
    issued = _utc(issued_at, "issued_at")
    if type(shadow_policy) is not bool:
        raise CurrentFotMobReviewedSourceError("shadow_policy must be exact bool")
    if shadow_policy:
        policy_result = build_current_shadow_fotmob_fixture_review_policy_result(
            candidate_bundle,
            reviewed_at=issued,
        )
        minimum_lead_seconds = SHADOW_MINIMUM_LEAD_SECONDS
        admission_reviewer_reference = SHADOW_ADMISSION_REVIEWER_REFERENCE
        admission_notes = (
            f"{SHADOW_POLICY_ID}; deterministic catalog admission for every and only "
            "current Shadow V2 policy-approved FotMob fixture"
        )
    else:
        policy_result = build_current_fotmob_fixture_review_policy_result(
            candidate_bundle,
            reviewed_at=issued,
        )
        minimum_lead_seconds = DEFAULT_MINIMUM_LEAD_SECONDS
        admission_reviewer_reference = ADMISSION_REVIEWER_REFERENCE
        admission_notes = (
            f"{POLICY_ID}; deterministic catalog admission for every and only "
            "PR243 policy-approved current FotMob fixture"
        )
    if policy_result.policy_approved_count == 0:
        raise CurrentFotMobReviewedSourceError(STATUS_NO_FIXTURES)

    handoff = build_fotmob_fixture_catalog_handoff(
        candidate_bundle,
        policy_result.review_bundle,
    )
    work_root = _safe_work_root(repository)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="reviewed-catalog-input-",
            suffix=".jsonl",
            dir=work_root,
            delete=False,
        ) as handle:
            handle.write(handoff.catalog_input_jsonl_bytes)
            handle.flush()
            temporary_path = Path(handle.name)
        catalog_result = compile_fixture_catalog(
            input_path=temporary_path,
            evidence_root=capture_root,
            as_of=issued,
            minimum_lead_seconds=minimum_lead_seconds,
            code_state=code_state,
        )
    finally:
        if temporary_path is not None and temporary_path.exists():
            if temporary_path.is_symlink():
                raise CurrentFotMobReviewedSourceError(
                    "temporary catalog input became a symlink"
                )
            temporary_path.unlink()

    admission_decision = ReviewedFixtureCatalogAdmissionDecision(
        candidate_bundle_sha256=handoff.candidate_bundle_sha256,
        review_bundle_sha256=handoff.review_bundle_sha256,
        handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
        catalog_sha256=sha256_bytes(catalog_result.catalog_bytes),
        manifest_sha256=sha256_bytes(catalog_result.manifest_bytes),
        source_capability=REVIEWED_SOURCE_CAPABILITY,
        source_capability_sha256=sha256_reviewed_source_capability(),
        disposition=ReviewedFixtureCatalogAdmissionDisposition.ADMITTED,
        reviewed_at=issued,
        reviewer_reference=admission_reviewer_reference,
        notes=admission_notes,
    )
    admission = build_reviewed_fixture_catalog_admission(
        handoff,
        catalog_result,
        admission_decision,
    )
    admission_bytes = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    verified_admission = verify_reviewed_fixture_catalog_admission_artifact(
        admission,
        admission_bytes,
        verified_at=issued,
    )
    verified_admission_receipt = canonical_verified_admission_artifact_receipt_bytes(
        verified_admission
    )
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(
        verified_admission,
        verified_admission_receipt,
    )
    bootstrap_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap)
    verified_bootstrap = verify_reviewed_fixture_intelligence_bootstrap_artifact(
        bootstrap,
        bootstrap_bytes,
        verified_at=issued,
    )
    receipt = canonical_verified_bootstrap_artifact_receipt_bytes(verified_bootstrap)
    return CurrentFotMobReviewedSourceExecution(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS_READY,
        policy_result=policy_result,
        handoff=handoff,
        bootstrap=bootstrap,
        verified_bootstrap=verified_bootstrap,
        verified_bootstrap_receipt_bytes=receipt,
        source_capture_directory=Path(capture_directory),
        source_capture_manifest_sha256=hashlib.sha256(
            (Path(capture_directory) / "manifest.json").read_bytes()
        ).hexdigest(),
        source_raw_sha256=manifest.raw_sha256,
        issued_at=issued,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
    )


def build_verified_current_fotmob_bootstrap_from_capture(
    capture_directory: Path,
    *,
    issued_at: Any,
    repository_root: Path | None = None,
    code_state: Mapping[str, Any] | None = None,
) -> CurrentFotMobReviewedSourceExecution:
    """Replay one exact PR38 capture through the frozen PR243 identity policy."""

    return _build_verified_current_fotmob_bootstrap_from_capture(
        capture_directory,
        issued_at=issued_at,
        repository_root=repository_root,
        code_state=code_state,
        shadow_policy=False,
    )


def build_verified_current_shadow_fotmob_bootstrap_from_capture(
    capture_directory: Path,
    *,
    issued_at: Any,
    repository_root: Path | None = None,
    code_state: Mapping[str, Any] | None = None,
) -> CurrentFotMobReviewedSourceExecution:
    """Replay one exact PR38 capture through the fixed Shadow V2 1800s policy."""

    return _build_verified_current_fotmob_bootstrap_from_capture(
        capture_directory,
        issued_at=issued_at,
        repository_root=repository_root,
        code_state=code_state,
        shadow_policy=True,
    )


def _issue_current_fotmob_reviewed_source(
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    execute_live_network: bool,
    repository_root: Path | None = None,
    connection_factory: Callable[..., Any] | None = None,
    clock: Callable[[], dt.datetime] | None = None,
    replay_builder: Callable[..., CurrentFotMobReviewedSourceExecution],
) -> CurrentFotMobReviewedSourceExecution:
    """Capture one transparent source response then apply a fixed policy."""

    if type(execute_live_network) is not bool or execute_live_network is not True:
        raise CurrentFotMobReviewedSourceError(
            "live current source issuance requires exact execute_live_network=True"
        )
    repository = _repo_root(repository_root)
    fetch_kwargs: dict[str, Any] = {
        "request_date": request_date,
        "timezone": timezone,
        "ccode3": ccode3,
    }
    if connection_factory is not None:
        fetch_kwargs["connection_factory"] = connection_factory
    if clock is not None:
        fetch_kwargs["clock"] = clock
    try:
        response = fetch_fotmob_data_matches(**fetch_kwargs)
        capture_directory, _manifest = write_data_matches_capture_directory(
            response,
            request_date=request_date,
            timezone=timezone,
            ccode3=ccode3,
            repository_root=repository,
        )
    except (FotMobDataMatchesCaptureError, FotMobDataMatchesNetworkError) as exc:
        raise CurrentFotMobReviewedSourceError(
            "transparent current FotMob data-matches acquisition failed"
        ) from exc
    issued = clock() if clock is not None else dt.datetime.now(dt.timezone.utc)
    return replay_builder(
        capture_directory,
        issued_at=issued,
        repository_root=repository,
    )


def issue_current_fotmob_reviewed_source(
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    execute_live_network: bool,
    repository_root: Path | None = None,
    connection_factory: Callable[..., Any] | None = None,
    clock: Callable[[], dt.datetime] | None = None,
) -> CurrentFotMobReviewedSourceExecution:
    """Capture one current transparent source response using frozen PR243 policy."""

    return _issue_current_fotmob_reviewed_source(
        request_date=request_date,
        timezone=timezone,
        ccode3=ccode3,
        execute_live_network=execute_live_network,
        repository_root=repository_root,
        connection_factory=connection_factory,
        clock=clock,
        replay_builder=build_verified_current_fotmob_bootstrap_from_capture,
    )


def issue_current_shadow_fotmob_reviewed_source(
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    execute_live_network: bool,
    repository_root: Path | None = None,
    connection_factory: Callable[..., Any] | None = None,
    clock: Callable[[], dt.datetime] | None = None,
) -> CurrentFotMobReviewedSourceExecution:
    """Capture one source response using the fixed current Shadow V2 policy."""

    return _issue_current_fotmob_reviewed_source(
        request_date=request_date,
        timezone=timezone,
        ccode3=ccode3,
        execute_live_network=execute_live_network,
        repository_root=repository_root,
        connection_factory=connection_factory,
        clock=clock,
        replay_builder=build_verified_current_shadow_fotmob_bootstrap_from_capture,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Issue a current reviewed FotMob fixture bootstrap from the transparent "
            "PR38 source path and frozen PR243 fixture policy."
        )
    )
    parser.add_argument("--date", required=True, help="Exact Gregorian YYYYMMDD date")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--ccode3", default="NGA")
    parser.add_argument("--execute-live-network", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.execute_live_network:
        parser.error("supply --execute-live-network for the one transparent request")
    try:
        execution = issue_current_fotmob_reviewed_source(
            request_date=args.date,
            timezone=args.timezone,
            ccode3=args.ccode3,
            execute_live_network=True,
        )
        payload = execution.summary()
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        if args.output is not None:
            _write_result(args.output, payload)
        print(raw.decode("utf-8"), end="")
        return 0
    except CurrentFotMobReviewedSourceError as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": str(exc),
            "minimum_lead_seconds": DEFAULT_MINIMUM_LEAD_SECONDS,
            "max_source_age_seconds": DEFAULT_MAX_SOURCE_AGE_SECONDS,
            "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
            "wager_placed": False,
        }
        if args.output is not None:
            _write_result(args.output, payload)
        parser.exit(1, json.dumps(payload, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
