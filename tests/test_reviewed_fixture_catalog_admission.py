from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import domain.reviewed_fixture_catalog_admission as admission_module
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
    DATASET_NAME,
    REVIEWED_SOURCE_CAPABILITY,
    SCHEMA_VERSION,
    ReviewedFixtureCatalogAdmission,
    ReviewedFixtureCatalogAdmissionDecision,
    ReviewedFixtureCatalogAdmissionDisposition,
    ReviewedFixtureCatalogAdmissionError,
    build_reviewed_fixture_catalog_admission,
    canonical_reviewed_fixture_catalog_admission_bytes,
    sha256_reviewed_fixture_catalog_admission,
    sha256_reviewed_source_capability,
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
    reviewed_at: datetime.datetime | None = None,
    **overrides,
) -> ReviewedFixtureCatalogAdmissionDecision:
    values = {
        "candidate_bundle_sha256": handoff.candidate_bundle_sha256,
        "review_bundle_sha256": handoff.review_bundle_sha256,
        "handoff_sha256": sha256_fotmob_fixture_catalog_handoff(handoff),
        "catalog_sha256": sha256_bytes(result.catalog_bytes),
        "manifest_sha256": sha256_bytes(result.manifest_bytes),
        "source_capability": REVIEWED_SOURCE_CAPABILITY,
        "source_capability_sha256": sha256_reviewed_source_capability(),
        "disposition": disposition,
        "reviewed_at": reviewed_at
        or datetime.datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        "reviewer_reference": "operator:catalog-admission",
        "notes": "catalog-level admission review",
    }
    values.update(overrides)
    return ReviewedFixtureCatalogAdmissionDecision(**values)


def test_admitted_catalog_exposes_every_and_only_compiled_identity(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    admission = build_reviewed_fixture_catalog_admission(
        handoff,
        result,
        _decision(handoff, result),
    )

    assert SCHEMA_VERSION == 1
    assert DATASET_NAME == "athena-reviewed-fixture-catalog-admission-v1"
    assert [item.fixture_identifier for item in admission.admitted_fixtures] == [
        "FOTMOB:1001"
    ]
    payload = admission.to_dict()
    assert payload["compiled_fixture_count"] == 1
    assert payload["admitted_fixture_count"] == 1
    assert payload["source_capability"] == REVIEWED_SOURCE_CAPABILITY
    assert payload["source_capability_sha256"] == sha256_reviewed_source_capability()
    assert payload["catalog_sha256"] == sha256_bytes(result.catalog_bytes)
    assert payload["manifest_sha256"] == sha256_bytes(result.manifest_bytes)


def test_rejected_catalog_exposes_zero_admitted_identities(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    admission = build_reviewed_fixture_catalog_admission(
        handoff,
        result,
        _decision(
            handoff,
            result,
            disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
        ),
    )
    assert admission.admitted_fixtures == ()
    assert admission.to_dict()["disposition"] == "REJECTED"


@pytest.mark.parametrize(
    "field",
    (
        "candidate_bundle_sha256",
        "review_bundle_sha256",
        "handoff_sha256",
        "catalog_sha256",
        "manifest_sha256",
        "source_capability_sha256",
    ),
)
def test_decision_must_anchor_every_upstream_hash(tmp_path: Path, field: str) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(handoff, result, **{field: "f" * 64})
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match=field):
        build_reviewed_fixture_catalog_admission(handoff, result, decision)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("catalog_bytes", b"{}\n", "catalog object or canonical bytes"),
        ("manifest_bytes", b"{}\n", "manifest object or canonical bytes"),
        ("tracked_worktree_clean", False, "clean tracked worktree"),
    ),
)
def test_tampered_compiler_state_fails_closed(
    tmp_path: Path,
    field: str,
    value,
    message: str,
) -> None:
    handoff, result = _compiled(tmp_path)
    tampered = dataclasses.replace(result, **{field: value})
    decision = _decision(handoff, tampered)
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match=message):
        build_reviewed_fixture_catalog_admission(handoff, tampered, decision)


def test_tampered_compiler_record_cannot_escape_reviewed_handoff(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    changed_record = dataclasses.replace(result.records[0], home_team="Fabricated FC")
    tampered = dataclasses.replace(result, records=(changed_record,))
    decision = _decision(handoff, tampered)
    with pytest.raises(ReviewedFixtureCatalogAdmissionError):
        build_reviewed_fixture_catalog_admission(handoff, tampered, decision)


def test_admission_must_not_predate_compiler_as_of(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(
        handoff,
        result,
        reviewed_at=datetime.datetime(2026, 8, 10, 2, 59, tzinfo=UTC),
    )
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="compiler as_of"):
        build_reviewed_fixture_catalog_admission(handoff, result, decision)


def test_admitted_catalog_must_still_be_prospective(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(
        handoff,
        result,
        reviewed_at=datetime.datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="remain prospective"):
        build_reviewed_fixture_catalog_admission(handoff, result, decision)


def test_rejection_after_kickoff_still_promotes_nothing(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    admission = build_reviewed_fixture_catalog_admission(
        handoff,
        result,
        _decision(
            handoff,
            result,
            disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
            reviewed_at=datetime.datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        ),
    )
    assert admission.admitted_fixtures == ()


def test_capability_revocation_invalidates_existing_admission_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(handoff, result)
    current = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    monkeypatch.setitem(
        SOURCE_CAPABILITY_REGISTRY,
        REVIEWED_SOURCE_CAPABILITY,
        dataclasses.replace(
            current,
            reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
        ),
    )
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="identity-only PR #44 profile"):
        sha256_reviewed_source_capability()
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="identity-only PR #44 profile"):
        build_reviewed_fixture_catalog_admission(handoff, result, decision)


def test_unreviewed_capability_expansion_also_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(handoff, result)
    current = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    monkeypatch.setitem(
        SOURCE_CAPABILITY_REGISTRY,
        REVIEWED_SOURCE_CAPABILITY,
        dataclasses.replace(
            current,
            full_time_score=CapabilityAvailability.CONFIRMED,
        ),
    )
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="identity-only PR #44 profile"):
        build_reviewed_fixture_catalog_admission(handoff, result, decision)


def test_existing_canonical_bytes_do_not_re_read_later_capability_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(handoff, result)
    admission = build_reviewed_fixture_catalog_admission(handoff, result, decision)
    before = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    before_sha = sha256_reviewed_fixture_catalog_admission(admission)

    current = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    monkeypatch.setitem(
        SOURCE_CAPABILITY_REGISTRY,
        REVIEWED_SOURCE_CAPABILITY,
        dataclasses.replace(current, notes=current.notes + " Registry metadata changed."),
    )

    assert canonical_reviewed_fixture_catalog_admission_bytes(admission) == before
    assert sha256_reviewed_fixture_catalog_admission(admission) == before_sha
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="source_capability_sha256"):
        build_reviewed_fixture_catalog_admission(handoff, result, decision)


def test_raw_fotmob_unofficial_cannot_be_used_as_admission_capability(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="source_capability must be exactly"):
        _decision(handoff, result, source_capability="fotmob_unofficial")
    assert (
        SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"].reliable_fixture_identity
        is CapabilityAvailability.UNKNOWN
    )


def test_direct_rejected_construction_cannot_smuggle_admitted_fixture(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    admitted = build_reviewed_fixture_catalog_admission(
        handoff,
        result,
        _decision(handoff, result),
    )
    rejected = _decision(
        handoff,
        result,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="zero admitted"):
        ReviewedFixtureCatalogAdmission(
            handoff=handoff,
            fixture_catalog_result=result,
            decision=rejected,
            admitted_fixtures=admitted.admitted_fixtures,
            safety=dict(admitted.safety),
        )


def test_canonical_bytes_and_hash_are_deterministic(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(handoff, result)
    first = build_reviewed_fixture_catalog_admission(handoff, result, decision)
    second = build_reviewed_fixture_catalog_admission(handoff, result, decision)
    raw = canonical_reviewed_fixture_catalog_admission_bytes(first)
    assert raw == canonical_reviewed_fixture_catalog_admission_bytes(second)
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert raw == (
        json.dumps(
            first.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert sha256_reviewed_fixture_catalog_admission(first) == hashlib.sha256(raw).hexdigest()


def test_downstream_authorizations_remain_false_and_immutable(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    admission = build_reviewed_fixture_catalog_admission(
        handoff,
        result,
        _decision(handoff, result),
    )
    assert all(type(value) is bool and value is False for value in admission.safety.values())
    for key in (
        "intelligence_fact_authorized",
        "model_feature_authorized",
        "pricing_authorized",
        "bet_authorized",
    ):
        assert admission.safety[key] is False
    with pytest.raises(TypeError):
        admission.safety["bet_authorized"] = True
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="must be exact bool False"):
        dataclasses.replace(
            admission,
            safety={**dict(admission.safety), "bet_authorized": True},
        )


def test_production_module_has_no_network_intelligence_model_pricing_or_betting_imports() -> None:
    tree = ast.parse(Path(admission_module.__file__).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
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


def test_exact_domain_types_are_required(tmp_path: Path) -> None:
    handoff, result = _compiled(tmp_path)
    decision = _decision(handoff, result)
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="handoff must be exact"):
        build_reviewed_fixture_catalog_admission(object(), result, decision)
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="fixture_catalog_result must be exact"):
        build_reviewed_fixture_catalog_admission(handoff, object(), decision)
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="decision must be exact"):
        build_reviewed_fixture_catalog_admission(handoff, result, object())
    with pytest.raises(ReviewedFixtureCatalogAdmissionError, match="value must be exact"):
        canonical_reviewed_fixture_catalog_admission_bytes(object())
