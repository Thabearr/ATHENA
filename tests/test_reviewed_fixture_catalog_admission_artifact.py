from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import domain.reviewed_fixture_catalog_admission_artifact as artifact_module
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
    sha256_reviewed_fixture_catalog_admission,
    sha256_reviewed_source_capability,
)
from domain.reviewed_fixture_catalog_admission_artifact import (
    DATASET_NAME,
    SCHEMA_VERSION,
    ReviewedFixtureCatalogAdmissionArtifactError,
    VerifiedReviewedFixtureCatalogAdmissionArtifact,
    canonical_verified_admission_artifact_receipt_bytes,
    sha256_verified_admission_artifact_receipt,
    verify_reviewed_fixture_catalog_admission_artifact,
)
from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)


UTC = datetime.timezone.utc
RAW_EVIDENCE = b"exact preserved FotMob response bytes\n"
RAW_SHA = hashlib.sha256(RAW_EVIDENCE).hexdigest()


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
        kickoff_utc=datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
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


def _decision(
    handoff,
    result,
    *,
    disposition: ReviewedFixtureCatalogAdmissionDisposition = (
        ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ),
) -> ReviewedFixtureCatalogAdmissionDecision:
    return ReviewedFixtureCatalogAdmissionDecision(
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


def _admission(
    tmp_path: Path,
    *,
    disposition: ReviewedFixtureCatalogAdmissionDisposition = (
        ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ),
):
    handoff, result = _compiled(tmp_path)
    return build_reviewed_fixture_catalog_admission(
        handoff,
        result,
        _decision(handoff, result, disposition=disposition),
    )


def _verify(tmp_path: Path):
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    verified = verify_reviewed_fixture_catalog_admission_artifact(
        admission,
        raw,
        verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
    )
    return admission, raw, verified


def test_exact_admitted_canonical_bytes_verify(tmp_path: Path) -> None:
    admission, raw, verified = _verify(tmp_path)

    assert SCHEMA_VERSION == 1
    assert DATASET_NAME == "athena-reviewed-fixture-catalog-admission-artifact-verification-v1"
    assert verified.artifact_bytes == raw
    assert verified.admission_sha256 == sha256_reviewed_fixture_catalog_admission(admission)
    assert [item.fixture_identifier for item in verified.admitted_fixtures] == [
        "FOTMOB:1001"
    ]
    payload = verified.to_dict()
    assert payload["artifact_size"] == len(raw)
    assert payload["source_capability"] == REVIEWED_SOURCE_CAPABILITY
    assert payload["source_capability_sha256"] == admission.decision.source_capability_sha256
    assert payload["disposition"] == "ADMITTED"
    assert payload["admitted_fixture_count"] == 1


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw + b"\n",
        lambda raw: raw[:-1],
        lambda raw: b" " + raw,
        lambda raw: raw.replace(b'"ADMITTED"', b'"REJECTED"', 1),
    ),
)
def test_any_noncanonical_or_changed_artifact_bytes_fail_closed(tmp_path: Path, mutate) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="exact canonical bytes",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            mutate(raw),
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )


def test_rejected_admission_cannot_produce_verified_artifact(tmp_path: Path) -> None:
    admission = _admission(
        tmp_path,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="only an ADMITTED",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            raw,
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )


def test_artifact_bytes_must_be_exact_immutable_bytes(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="exact immutable bytes",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            bytearray(raw),
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )


def test_verified_at_cannot_predate_admission_review(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="must not predate",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            raw,
            verified_at=datetime.datetime(2026, 8, 10, 3, 59, tzinfo=UTC),
        )


def test_verified_at_must_already_be_utc(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    offset = datetime.timezone(datetime.timedelta(hours=1))
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="already be normalized to UTC",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            raw,
            verified_at=datetime.datetime(2026, 8, 10, 5, 30, tzinfo=offset),
        )


def test_direct_construction_cannot_lie_about_admission_hash(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="admission_sha256 does not match",
    ):
        VerifiedReviewedFixtureCatalogAdmissionArtifact(
            admission=admission,
            artifact_bytes=raw,
            admission_sha256="f" * 64,
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
            safety={key: False for key in artifact_module._SAFETY_KEYS},
        )


def test_direct_construction_cannot_smuggle_changed_bytes(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="exact canonical bytes",
    ):
        VerifiedReviewedFixtureCatalogAdmissionArtifact(
            admission=admission,
            artifact_bytes=raw + b"\n",
            admission_sha256=sha256_reviewed_fixture_catalog_admission(admission),
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
            safety={key: False for key in artifact_module._SAFETY_KEYS},
        )


def test_capability_change_blocks_new_verification_but_not_historical_receipt_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission, raw, verified = _verify(tmp_path)
    receipt_before = canonical_verified_admission_artifact_receipt_bytes(verified)
    admission_before = canonical_reviewed_fixture_catalog_admission_bytes(admission)

    current = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    monkeypatch.setitem(
        SOURCE_CAPABILITY_REGISTRY,
        REVIEWED_SOURCE_CAPABILITY,
        dataclasses.replace(
            current,
            reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
        ),
    )

    assert canonical_reviewed_fixture_catalog_admission_bytes(admission) == admission_before
    assert canonical_verified_admission_artifact_receipt_bytes(verified) == receipt_before
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="current semantic revalidation",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            raw,
            verified_at=datetime.datetime(2026, 8, 10, 4, 31, tzinfo=UTC),
        )


def test_verification_receipt_bytes_and_hash_are_deterministic(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    verified_at = datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC)
    first = verify_reviewed_fixture_catalog_admission_artifact(
        admission, raw, verified_at=verified_at
    )
    second = verify_reviewed_fixture_catalog_admission_artifact(
        admission, raw, verified_at=verified_at
    )

    receipt = canonical_verified_admission_artifact_receipt_bytes(first)
    assert receipt == canonical_verified_admission_artifact_receipt_bytes(second)
    assert receipt.endswith(b"\n") and not receipt.endswith(b"\n\n")
    assert receipt == (
        json.dumps(
            first.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert sha256_verified_admission_artifact_receipt(first) == hashlib.sha256(receipt).hexdigest()


def test_safety_flags_remain_false_and_immutable(tmp_path: Path) -> None:
    _, _, verified = _verify(tmp_path)
    assert all(type(value) is bool and value is False for value in verified.safety.values())
    for key in (
        "artifact_write_authorized",
        "fixture_intelligence_bootstrap_authorized",
        "intelligence_fact_authorized",
        "model_feature_authorized",
        "pricing_authorized",
        "bet_authorized",
    ):
        assert verified.safety[key] is False
    with pytest.raises(TypeError):
        verified.safety["bet_authorized"] = True
    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="must be exact bool False",
    ):
        dataclasses.replace(
            verified,
            safety={**dict(verified.safety), "bet_authorized": True},
        )


def test_exact_domain_types_are_required(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    with pytest.raises(ReviewedFixtureCatalogAdmissionArtifactError, match="admission must be exact"):
        verify_reviewed_fixture_catalog_admission_artifact(
            object(),
            raw,
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )
    with pytest.raises(ReviewedFixtureCatalogAdmissionArtifactError, match="value must be exact"):
        canonical_verified_admission_artifact_receipt_bytes(object())


def test_production_module_has_no_network_filesystem_intelligence_model_pricing_or_betting_imports() -> None:
    tree = ast.parse(Path(artifact_module.__file__).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
        "os",
        "pathlib",
        "tempfile",
        "shutil",
        "requests",
        "httpx",
        "aiohttp",
        "urllib.request",
        "http.client",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
        "engine.prediction_engine",
        "providers.sportybet",
    }
    assert imports.isdisjoint(forbidden)
