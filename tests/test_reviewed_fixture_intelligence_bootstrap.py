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
    DATASET_NAME as VERIFIED_ARTIFACT_DATASET_NAME,
    canonical_verified_admission_artifact_receipt_bytes,
    sha256_verified_admission_artifact_receipt,
    verify_reviewed_fixture_catalog_admission_artifact,
)
from domain.reviewed_fixture_intelligence_bootstrap import (
    DATASET_NAME,
    SCHEMA_VERSION,
    ReviewedFixtureIntelligenceBootstrapError,
    ReviewedFixtureIntelligenceIdentity,
    build_reviewed_fixture_intelligence_bootstrap,
    canonical_reviewed_fixture_intelligence_bootstrap_bytes,
    resolve_reviewed_fixture_intelligence_identity,
    sha256_reviewed_fixture_intelligence_bootstrap,
)
from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)


UTC = datetime.timezone.utc
RAW_EVIDENCE = b"exact preserved FotMob response bytes\n"
RAW_SHA = hashlib.sha256(RAW_EVIDENCE).hexdigest()
KICKOFF = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


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


def _admission(
    tmp_path: Path,
    disposition: ReviewedFixtureCatalogAdmissionDisposition = (
        ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ),
):
    handoff, result = _compiled(tmp_path)
    decision = ReviewedFixtureCatalogAdmissionDecision(
        candidate_bundle_sha256=handoff.candidate_bundle_sha256,
        review_bundle_sha256=handoff.review_bundle_sha256,
        handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
        catalog_sha256=sha256_bytes(result.catalog_bytes),
        manifest_sha256=sha256_bytes(result.manifest_bytes),
        source_capability=REVIEWED_SOURCE_CAPABILITY,
        source_capability_sha256=sha256_reviewed_source_capability(),
        disposition=disposition,
        reviewed_at=datetime.datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        reviewer_reference="operator:catalog-admission",
        notes="catalog-level admission review",
    )
    return build_reviewed_fixture_catalog_admission(handoff, result, decision)


def _verified_artifact(
    tmp_path: Path,
    *,
    verified_at: datetime.datetime | None = None,
):
    admission = _admission(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    verified = verify_reviewed_fixture_catalog_admission_artifact(
        admission,
        artifact_bytes,
        verified_at=verified_at
        or datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
    )
    return admission, verified


def test_verified_artifact_builds_identity_only_bootstrap(tmp_path: Path) -> None:
    admission, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)

    assert SCHEMA_VERSION == 1
    assert DATASET_NAME == "athena-reviewed-fixture-intelligence-bootstrap-v1"
    assert bootstrap.verification_receipt_sha256 == (
        sha256_verified_admission_artifact_receipt(verified)
    )
    assert bootstrap.admission_sha256 == verified.admission_sha256
    assert bootstrap.source_capability == REVIEWED_SOURCE_CAPABILITY
    assert bootstrap.source_capability_sha256 == admission.decision.source_capability_sha256
    assert bootstrap.catalog_sha256 == admission.decision.catalog_sha256
    assert bootstrap.manifest_sha256 == admission.decision.manifest_sha256
    assert bootstrap.admission_reviewed_at == admission.decision.reviewed_at
    assert bootstrap.artifact_verified_at == verified.verified_at
    assert [item.fixture_identifier for item in bootstrap.fixtures] == ["FOTMOB:1001"]
    assert bootstrap.fixtures[0].kickoff == KICKOFF


def test_payload_anchors_pr46_receipt_and_full_upstream_chain(tmp_path: Path) -> None:
    admission, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)
    payload = bootstrap.to_dict()

    assert payload["verification_dataset_name"] == VERIFIED_ARTIFACT_DATASET_NAME
    assert payload["verification_receipt_sha256"] == (
        sha256_verified_admission_artifact_receipt(verified)
    )
    assert payload["admission_sha256"] == verified.admission_sha256
    assert payload["candidate_bundle_sha256"] == admission.decision.candidate_bundle_sha256
    assert payload["review_bundle_sha256"] == admission.decision.review_bundle_sha256
    assert payload["handoff_sha256"] == admission.decision.handoff_sha256
    assert payload["catalog_sha256"] == admission.decision.catalog_sha256
    assert payload["manifest_sha256"] == admission.decision.manifest_sha256
    assert payload["fixture_count"] == 1
    assert set(payload["fixtures"][0]) == {
        "fixture_identifier",
        "kickoff",
        "admission_sha256",
        "verification_receipt_sha256",
    }
    serialized = canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap)
    for forbidden in (b"home_team", b"away_team", b"competition", b"score", b"lineup"):
        assert forbidden not in serialized


def test_pr45_admission_cannot_bypass_pr46_verifier(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="verified_artifact must be exact",
    ):
        build_reviewed_fixture_intelligence_bootstrap(admission)


def test_rejected_catalog_cannot_bypass_verifier_into_bootstrap(tmp_path: Path) -> None:
    admission = _admission(
        tmp_path,
        ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    with pytest.raises(ReviewedFixtureIntelligenceBootstrapError, match="verified_artifact"):
        build_reviewed_fixture_intelligence_bootstrap(admission)


def test_wrong_domain_type_is_rejected() -> None:
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="VerifiedReviewedFixtureCatalogAdmissionArtifact",
    ):
        build_reviewed_fixture_intelligence_bootstrap(object())


def test_exact_identity_resolution_has_no_alias_or_fuzzy_fallback(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)
    identity = resolve_reviewed_fixture_intelligence_identity(bootstrap, "FOTMOB:1001")
    assert type(identity) is ReviewedFixtureIntelligenceIdentity
    assert identity is bootstrap.fixtures[0]

    for invalid in ("FOTMOB:1002", "fotmob:1001", "FOTMOB:01001", " FOTMOB:1001"):
        with pytest.raises(ReviewedFixtureIntelligenceBootstrapError):
            resolve_reviewed_fixture_intelligence_identity(bootstrap, invalid)


def test_verified_artifact_is_revalidated_not_trusted_by_frozen_type(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    object.__setattr__(verified.admission, "admitted_fixtures", ())
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="failed exact PR #46 revalidation",
    ):
        build_reviewed_fixture_intelligence_bootstrap(verified)


def test_mutated_verifier_safety_fails_closed(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    unsafe = dict(verified.safety)
    unsafe["bet_authorized"] = True
    object.__setattr__(verified, "safety", unsafe)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="failed exact PR #46 revalidation",
    ):
        build_reviewed_fixture_intelligence_bootstrap(verified)


def test_verification_at_or_after_kickoff_cannot_bootstrap(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path, verified_at=KICKOFF)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="remain prospective at PR #46 verification time",
    ):
        build_reviewed_fixture_intelligence_bootstrap(verified)


def test_direct_bootstrap_construction_cannot_change_receipt_ancestry(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    valid = build_reviewed_fixture_intelligence_bootstrap(verified)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="verification_receipt_sha256 does not anchor",
    ):
        dataclasses.replace(valid, verification_receipt_sha256="f" * 64)


def test_direct_bootstrap_construction_cannot_change_catalog_ancestry(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    valid = build_reviewed_fixture_intelligence_bootstrap(verified)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="catalog_sha256 does not anchor",
    ):
        dataclasses.replace(valid, catalog_sha256="f" * 64)


def test_direct_bootstrap_construction_cannot_omit_admitted_fixture(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    valid = build_reviewed_fixture_intelligence_bootstrap(verified)
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="fixtures must be a non-empty",
    ):
        dataclasses.replace(valid, fixtures=())


def test_canonical_bytes_and_hash_are_deterministic(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    first = build_reviewed_fixture_intelligence_bootstrap(verified)
    second = build_reviewed_fixture_intelligence_bootstrap(verified)

    first_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(first)
    second_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(second)
    assert first_bytes == second_bytes
    assert first_bytes.endswith(b"\n") and not first_bytes.endswith(b"\n\n")
    assert sha256_reviewed_fixture_intelligence_bootstrap(first) == hashlib.sha256(
        first_bytes
    ).hexdigest()


def test_historical_bootstrap_bytes_are_detached_from_nested_artifact_mutation(
    tmp_path: Path,
) -> None:
    _, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)
    before = canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap)

    object.__setattr__(verified, "admission_sha256", "f" * 64)
    after = canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap)
    assert after == before

    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="failed exact PR #46 revalidation",
    ):
        build_reviewed_fixture_intelligence_bootstrap(verified)


def test_capability_change_does_not_mutate_history_but_blocks_new_bootstrap(
    tmp_path: Path,
) -> None:
    _, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)
    before = canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap)
    receipt_before = canonical_verified_admission_artifact_receipt_bytes(verified)
    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
        original,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
    )
    try:
        assert canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap) == before
        assert canonical_verified_admission_artifact_receipt_bytes(verified) == receipt_before
        with pytest.raises(
            ReviewedFixtureIntelligenceBootstrapError,
            match="failed exact PR #46 revalidation",
        ):
            build_reviewed_fixture_intelligence_bootstrap(verified)
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original


def test_bootstrap_safety_is_immutable_and_all_false(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)
    assert bootstrap.safety
    assert set(bootstrap.safety.values()) == {False}
    assert bootstrap.safety["intelligence_fact_authorized"] is False
    assert bootstrap.safety["intelligence_snapshot_authorized"] is False
    assert bootstrap.safety["model_feature_authorized"] is False
    assert bootstrap.safety["pricing_authorized"] is False
    assert bootstrap.safety["bet_authorized"] is False
    with pytest.raises(TypeError):
        bootstrap.safety["bet_authorized"] = True


def test_safety_true_fails_closed_on_direct_construction(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)
    unsafe = dict(bootstrap.safety)
    unsafe["intelligence_snapshot_authorized"] = True
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="must be exact bool False",
    ):
        dataclasses.replace(bootstrap, safety=unsafe)


def test_source_module_has_no_fact_snapshot_model_pricing_network_or_pr45_bypass() -> None:
    path = Path("domain/reviewed_fixture_intelligence_bootstrap.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert "domain.reviewed_fixture_catalog_admission_artifact" in imported_modules
    assert "domain.fixture_intelligence" not in imported_modules
    assert "domain.fixture_model_features" not in imported_modules
    for forbidden in (
        "requests",
        "httpx",
        "aiohttp",
        "urllib.request",
        "playwright",
        "selenium",
    ):
        assert forbidden not in imported_modules
    assert "ReviewedFixtureCatalogAdmission," not in source
    assert "build_reviewed_fixture_catalog_admission(" not in source
    assert "build_snapshot(" not in source
    assert "FixtureIntelligenceFact" not in source
    assert "compile_fixture_catalog(" not in source
    assert "open(" not in source
    assert ".write_bytes(" not in source
    assert ".write_text(" not in source


def test_raw_unofficial_capability_is_not_bootstrap_identity(tmp_path: Path) -> None:
    _, verified = _verified_artifact(tmp_path)
    bootstrap = build_reviewed_fixture_intelligence_bootstrap(verified)
    assert bootstrap.source_capability == "fotmob_data_matches_reviewed_catalog"
    assert bootstrap.source_capability != "fotmob_unofficial"
