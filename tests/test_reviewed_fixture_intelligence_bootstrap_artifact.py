from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
from domain.fixture_catalog import compile_fixture_catalog, sha256_bytes
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as CAPTURE_DATASET_NAME,
    SCHEMA_VERSION as CAPTURE_SCHEMA_VERSION,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewDecision,
    build_fotmob_fixture_candidate_review_bundle,
    sha256_fotmob_fixture_candidate,
)
from domain.fotmob_fixture_candidates import (
    DATASET_NAME as CANDIDATE_DATASET_NAME,
    SCHEMA_VERSION as CANDIDATE_SCHEMA_VERSION,
    SOURCE_NAME,
    FixtureCandidateReviewStatus,
    FotMobFixtureCandidate,
    FotMobFixtureCandidateBundle,
    FotMobFixtureCandidateSource,
)
from domain.fotmob_fixture_catalog_handoff import (
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
    ReviewedFixtureIntelligenceBootstrapError,
    build_reviewed_fixture_intelligence_bootstrap,
    canonical_reviewed_fixture_intelligence_bootstrap_bytes,
)
from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    DATASET_NAME,
    SCHEMA_VERSION,
    ReviewedFixtureIntelligenceBootstrapArtifactError,
    VerifiedReviewedFixtureIntelligenceBootstrapArtifact,
    canonical_verified_bootstrap_artifact_receipt_bytes,
    sha256_verified_bootstrap_artifact_receipt,
    verify_reviewed_fixture_intelligence_bootstrap_artifact,
)
from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)


UTC = datetime.timezone.utc
RAW_EVIDENCE = b"exact preserved FotMob response bytes\n"
RAW_SHA = hashlib.sha256(RAW_EVIDENCE).hexdigest()
KICKOFF = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
PR46_VERIFIED_AT = datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC)
PR48_VERIFIED_AT = datetime.datetime(2026, 8, 10, 5, 0, tzinfo=UTC)


def _source() -> FotMobFixtureCandidateSource:
    return FotMobFixtureCandidateSource(
        source_capture_dataset_name=CAPTURE_DATASET_NAME,
        source_capture_schema_version=CAPTURE_SCHEMA_VERSION,
        source_capture_manifest_sha256="1" * 64,
        source_raw_sha256=RAW_SHA,
        source_raw_size=len(RAW_EVIDENCE),
        source_observed_at=datetime.datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
        request_date="20260815",
        timezone="UTC",
        ccode3="NGA",
        schema_assessment_sha256="3" * 64,
        candidate_count=1,
    )


def _candidate(source: FotMobFixtureCandidateSource) -> FotMobFixtureCandidate:
    return FotMobFixtureCandidate(
        review_status=FixtureCandidateReviewStatus.UNREVIEWED,
        source=SOURCE_NAME,
        source_match_id=1001,
        source_league_id=10,
        source_competition_primary_id=10,
        source_competition_name="League One",
        source_competition_ccode="NGA",
        home_source_team_id=101,
        home_name="Home FC",
        home_long_name="Home Football Club",
        away_source_team_id=202,
        away_name="Away FC",
        away_long_name="Away Football Club",
        kickoff_utc=KICKOFF,
        source_capture_manifest_sha256=source.source_capture_manifest_sha256,
        source_raw_sha256=source.source_raw_sha256,
        source_request_date=source.request_date,
        source_observed_at=source.source_observed_at,
    )


def _bundle(
    source: FotMobFixtureCandidateSource,
    candidate: FotMobFixtureCandidate,
) -> FotMobFixtureCandidateBundle:
    duplicate_count, fixture_conflicts = candidate_module._make_fixture_observations(
        (candidate,)
    )
    team_conflicts = candidate_module._make_team_conflicts((candidate,))
    competition_conflicts = candidate_module._make_competition_conflicts((candidate,))
    return FotMobFixtureCandidateBundle(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        dataset_name=CANDIDATE_DATASET_NAME,
        sources=(source,),
        candidate_count=1,
        candidates=(candidate,),
        duplicate_source_match_id_count=duplicate_count,
        fixture_identity_conflict_count=len(fixture_conflicts),
        fixture_identity_conflicts=fixture_conflicts,
        team_identity_conflict_count=len(team_conflicts),
        team_identity_conflicts=team_conflicts,
        competition_identity_conflict_count=len(competition_conflicts),
        competition_identity_conflicts=competition_conflicts,
        safety=candidate_module._default_safety(),
    )


def _compiled(tmp_path: Path):
    source = _source()
    candidate = _candidate(source)
    bundle = _bundle(source, candidate)
    review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (
            FotMobFixtureCandidateReviewDecision(
                source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
                source_match_id=candidate.source_match_id,
                candidate_sha256=sha256_fotmob_fixture_candidate(candidate),
                disposition=FixtureCandidateReviewDisposition.APPROVED,
                reviewed_at=datetime.datetime(2026, 8, 10, 2, 30, tzinfo=UTC),
                reviewer_reference="operator:fixture-review",
                notes="explicit fixture review",
            ),
        ),
    )
    handoff = build_fotmob_fixture_catalog_handoff(bundle, review)

    payload = handoff.catalog_inputs[0].to_catalog_input_dict()
    evidence_path = tmp_path / payload["evidence_file_path"]
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_bytes(RAW_EVIDENCE)
    input_path = tmp_path / "reviewed.jsonl"
    input_path.write_bytes(handoff.catalog_input_jsonl_bytes)
    result = compile_fixture_catalog(
        input_path=input_path,
        evidence_root=tmp_path,
        as_of=datetime.datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
        minimum_lead_seconds=3600,
        code_state={
            "evidence_git_head_sha": "a" * 40,
            "tracked_worktree_clean": True,
        },
    )
    return handoff, result


def _admission(tmp_path: Path):
    handoff, result = _compiled(tmp_path)
    decision = ReviewedFixtureCatalogAdmissionDecision(
        candidate_bundle_sha256=handoff.candidate_bundle_sha256,
        review_bundle_sha256=handoff.review_bundle_sha256,
        handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
        catalog_sha256=sha256_bytes(result.catalog_bytes),
        manifest_sha256=sha256_bytes(result.manifest_bytes),
        source_capability=REVIEWED_SOURCE_CAPABILITY,
        source_capability_sha256=sha256_reviewed_source_capability(),
        disposition=ReviewedFixtureCatalogAdmissionDisposition.ADMITTED,
        reviewed_at=datetime.datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        reviewer_reference="operator:catalog-admission",
        notes="catalog-level admission review",
    )
    return build_reviewed_fixture_catalog_admission(handoff, result, decision)


def _bootstrap(tmp_path: Path):
    admission = _admission(tmp_path)
    admission_bytes = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    verified_admission = verify_reviewed_fixture_catalog_admission_artifact(
        admission,
        admission_bytes,
        verified_at=PR46_VERIFIED_AT,
    )
    upstream_receipt = canonical_verified_admission_artifact_receipt_bytes(
        verified_admission
    )
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(
        verified_admission,
        upstream_receipt,
    )
    return bootstrap


def _verified(tmp_path: Path, *, verified_at: datetime.datetime = PR48_VERIFIED_AT):
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    verified = verify_reviewed_fixture_intelligence_bootstrap_artifact(
        bootstrap,
        artifact_bytes,
        verified_at=verified_at,
    )
    return bootstrap, artifact_bytes, verified


def test_exact_bootstrap_bytes_build_verification_receipt(tmp_path: Path) -> None:
    bootstrap, artifact_bytes, verified = _verified(tmp_path)

    assert SCHEMA_VERSION == 1
    assert DATASET_NAME == (
        "athena-reviewed-fixture-intelligence-bootstrap-artifact-verification-v1"
    )
    assert type(verified) is VerifiedReviewedFixtureIntelligenceBootstrapArtifact
    assert verified.artifact_bytes == artifact_bytes
    assert verified.bootstrap_sha256 == hashlib.sha256(artifact_bytes).hexdigest()
    assert verified.upstream_verification_receipt_sha256 == (
        bootstrap.verification_receipt_sha256
    )
    assert verified.admission_sha256 == bootstrap.admission_sha256
    assert verified.catalog_sha256 == bootstrap.catalog_sha256
    assert verified.manifest_sha256 == bootstrap.manifest_sha256
    assert verified.upstream_artifact_verified_at == bootstrap.artifact_verified_at
    assert verified.verified_at == PR48_VERIFIED_AT
    assert [item.fixture_identifier for item in verified.fixtures] == ["FOTMOB:1001"]


def test_receipt_carries_exact_detached_chain(tmp_path: Path) -> None:
    bootstrap, artifact_bytes, verified = _verified(tmp_path)
    payload = verified.to_dict()

    assert payload["bootstrap_sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert payload["artifact_size"] == len(artifact_bytes)
    assert payload["upstream_verification_receipt_sha256"] == (
        bootstrap.verification_receipt_sha256
    )
    assert payload["candidate_bundle_sha256"] == bootstrap.candidate_bundle_sha256
    assert payload["review_bundle_sha256"] == bootstrap.review_bundle_sha256
    assert payload["handoff_sha256"] == bootstrap.handoff_sha256
    assert payload["catalog_sha256"] == bootstrap.catalog_sha256
    assert payload["manifest_sha256"] == bootstrap.manifest_sha256
    assert payload["fixture_count"] == 1
    assert set(payload["fixtures"][0]) == {
        "fixture_identifier",
        "kickoff",
        "admission_sha256",
        "verification_receipt_sha256",
    }


def test_wrong_bootstrap_type_is_rejected() -> None:
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="exact ReviewedFixtureIntelligenceBootstrap",
    ):
        verify_reviewed_fixture_intelligence_bootstrap_artifact(
            object(),
            b"{}\n",
            verified_at=PR48_VERIFIED_AT,
        )


def test_artifact_bytes_must_be_exact_immutable_bytes(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="exact immutable bytes",
    ):
        verify_reviewed_fixture_intelligence_bootstrap_artifact(
            bootstrap,
            bytearray(artifact_bytes),
            verified_at=PR48_VERIFIED_AT,
        )


def test_changed_or_noncanonical_artifact_bytes_fail_closed(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    for changed in (
        artifact_bytes + b"\n",
        artifact_bytes[:-1],
        b" " + artifact_bytes,
    ):
        with pytest.raises(
            ReviewedFixtureIntelligenceBootstrapArtifactError,
            match="exact canonical bytes",
        ):
            verify_reviewed_fixture_intelligence_bootstrap_artifact(
                bootstrap,
                changed,
                verified_at=PR48_VERIFIED_AT,
            )


def test_verification_time_cannot_predate_pr46_verification(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="must not predate",
    ):
        verify_reviewed_fixture_intelligence_bootstrap_artifact(
            bootstrap,
            artifact_bytes,
            verified_at=PR46_VERIFIED_AT - datetime.timedelta(microseconds=1),
        )


def test_historical_verification_after_kickoff_is_audit_only_and_allowed(
    tmp_path: Path,
) -> None:
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    verified = verify_reviewed_fixture_intelligence_bootstrap_artifact(
        bootstrap,
        artifact_bytes,
        verified_at=KICKOFF + datetime.timedelta(hours=1),
    )
    assert verified.verified_at > verified.fixtures[0].kickoff
    assert verified.safety["match_detail_probe_authorized"] is False


def test_mutated_bootstrap_fixture_fails_semantic_revalidation(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    object.__setattr__(bootstrap, "fixtures", ())
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="failed exact PR #47 revalidation",
    ):
        verify_reviewed_fixture_intelligence_bootstrap_artifact(
            bootstrap,
            artifact_bytes,
            verified_at=PR48_VERIFIED_AT,
        )


def test_mutated_nested_pr46_object_fails_current_revalidation(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    object.__setattr__(
        bootstrap.verified_artifact,
        "admission_sha256",
        "f" * 64,
    )
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="failed exact PR #47 revalidation",
    ):
        verify_reviewed_fixture_intelligence_bootstrap_artifact(
            bootstrap,
            artifact_bytes,
            verified_at=PR48_VERIFIED_AT,
        )


def test_direct_receipt_construction_cannot_change_bootstrap_hash(tmp_path: Path) -> None:
    _, _, verified = _verified(tmp_path)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="bootstrap_sha256 does not match",
    ):
        dataclasses.replace(verified, bootstrap_sha256="f" * 64)


def test_direct_receipt_construction_cannot_change_ancestry(tmp_path: Path) -> None:
    _, _, verified = _verified(tmp_path)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="catalog_sha256 does not anchor",
    ):
        dataclasses.replace(verified, catalog_sha256="f" * 64)


def test_direct_receipt_construction_cannot_change_fixture_set(tmp_path: Path) -> None:
    _, _, verified = _verified(tmp_path)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="non-empty immutable tuple",
    ):
        dataclasses.replace(verified, fixtures=())


def test_receipt_bytes_and_hash_are_deterministic(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        bootstrap
    )
    first = verify_reviewed_fixture_intelligence_bootstrap_artifact(
        bootstrap,
        artifact_bytes,
        verified_at=PR48_VERIFIED_AT,
    )
    second = verify_reviewed_fixture_intelligence_bootstrap_artifact(
        bootstrap,
        artifact_bytes,
        verified_at=PR48_VERIFIED_AT,
    )
    first_bytes = canonical_verified_bootstrap_artifact_receipt_bytes(first)
    second_bytes = canonical_verified_bootstrap_artifact_receipt_bytes(second)
    assert first_bytes == second_bytes
    assert first_bytes.endswith(b"\n") and not first_bytes.endswith(b"\n\n")
    assert sha256_verified_bootstrap_artifact_receipt(first) == hashlib.sha256(
        first_bytes
    ).hexdigest()


def test_historical_receipt_bytes_detach_from_nested_bootstrap_mutation(
    tmp_path: Path,
) -> None:
    bootstrap, _, verified = _verified(tmp_path)
    before = canonical_verified_bootstrap_artifact_receipt_bytes(verified)

    object.__setattr__(bootstrap, "catalog_sha256", "f" * 64)
    assert canonical_verified_bootstrap_artifact_receipt_bytes(verified) == before


def test_capability_change_does_not_mutate_history_but_blocks_new_verification(
    tmp_path: Path,
) -> None:
    bootstrap, artifact_bytes, verified = _verified(tmp_path)
    before = canonical_verified_bootstrap_artifact_receipt_bytes(verified)
    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
        original,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
    )
    try:
        assert canonical_verified_bootstrap_artifact_receipt_bytes(verified) == before
        with pytest.raises(
            ReviewedFixtureIntelligenceBootstrapArtifactError,
            match="failed exact PR #47 revalidation",
        ):
            verify_reviewed_fixture_intelligence_bootstrap_artifact(
                bootstrap,
                artifact_bytes,
                verified_at=PR48_VERIFIED_AT,
            )
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original


def test_safety_is_immutable_and_all_false(tmp_path: Path) -> None:
    _, _, verified = _verified(tmp_path)
    assert verified.safety
    assert set(verified.safety.values()) == {False}
    assert verified.safety["network_acquisition_authorized"] is False
    assert verified.safety["artifact_write_authorized"] is False
    assert verified.safety["match_detail_probe_authorized"] is False
    assert verified.safety["intelligence_fact_authorized"] is False
    assert verified.safety["model_feature_authorized"] is False
    assert verified.safety["pricing_authorized"] is False
    assert verified.safety["bet_authorized"] is False
    with pytest.raises(TypeError):
        verified.safety["bet_authorized"] = True


def test_true_safety_flag_fails_closed(tmp_path: Path) -> None:
    _, _, verified = _verified(tmp_path)
    unsafe = dict(verified.safety)
    unsafe["match_detail_probe_authorized"] = True
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="must be exact bool False",
    ):
        dataclasses.replace(verified, safety=unsafe)


def test_source_module_has_no_network_write_fact_model_or_pr30_boundary() -> None:
    path = Path("domain/reviewed_fixture_intelligence_bootstrap_artifact.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert "domain.reviewed_fixture_intelligence_bootstrap" in imported_modules
    assert "domain.fixture_intelligence" not in imported_modules
    assert "domain.fixture_model_features" not in imported_modules
    for forbidden in (
        "requests",
        "httpx",
        "aiohttp",
        "urllib.request",
        "http.client",
        "playwright",
        "selenium",
    ):
        assert forbidden not in imported_modules
    assert "build_snapshot(" not in source
    assert "FixtureIntelligenceFact" not in source
    assert "compile_fixture_catalog(" not in source
    assert "open(" not in source
    assert ".write_bytes(" not in source
    assert ".write_text(" not in source
