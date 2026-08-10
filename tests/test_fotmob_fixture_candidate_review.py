from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import domain.fotmob_fixture_candidate_review as review_module
from domain.fixture_catalog import INPUT_RECORD_KEYS
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as CAPTURE_DATASET_NAME,
    SCHEMA_VERSION as CAPTURE_SCHEMA_VERSION,
    RAW_FILENAME,
    capture_identifier,
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
from domain.fotmob_fixture_candidate_review import (
    DATASET_NAME,
    SCHEMA_VERSION,
    FixtureCandidateReviewBlockReason,
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewDecision,
    FotMobFixtureCandidateReviewError,
    build_fotmob_fixture_candidate_review_bundle,
    canonical_fotmob_fixture_candidate_bytes,
    canonical_fotmob_fixture_candidate_review_bundle_bytes,
    sha256_fotmob_fixture_candidate,
    sha256_fotmob_fixture_candidate_review_bundle,
)
from domain.source_capabilities import SOURCE_CAPABILITY_REGISTRY, CapabilityAvailability


UTC = datetime.timezone.utc


def _source(
    *,
    manifest_sha: str = "1" * 64,
    raw_sha: str = "2" * 64,
    assessment_sha: str = "3" * 64,
    count: int = 1,
    date: str = "20260815",
    second: int = 0,
) -> FotMobFixtureCandidateSource:
    return FotMobFixtureCandidateSource(
        source_capture_dataset_name=CAPTURE_DATASET_NAME,
        source_capture_schema_version=CAPTURE_SCHEMA_VERSION,
        source_capture_manifest_sha256=manifest_sha,
        source_raw_sha256=raw_sha,
        source_raw_size=100,
        source_observed_at=datetime.datetime(2026, 8, 10, 2, 0, second, tzinfo=UTC),
        request_date=date,
        timezone="UTC",
        ccode3="NGA",
        schema_assessment_sha256=assessment_sha,
        candidate_count=count,
    )


def _candidate(
    source: FotMobFixtureCandidateSource,
    *,
    match_id: int = 1001,
    league_id: int = 10,
    primary_id: int = 10,
    competition: str = "League Ω",
    ccode: str = "NGA",
    home_id: int = 101,
    home_name: str = "Home FC",
    home_long_name: str | None = None,
    away_id: int = 202,
    away_name: str = "Away FC",
    away_long_name: str | None = None,
    hour: int = 12,
) -> FotMobFixtureCandidate:
    return FotMobFixtureCandidate(
        review_status=FixtureCandidateReviewStatus.UNREVIEWED,
        source=SOURCE_NAME,
        source_match_id=match_id,
        source_league_id=league_id,
        source_competition_primary_id=primary_id,
        source_competition_name=competition,
        source_competition_ccode=ccode,
        home_source_team_id=home_id,
        home_name=home_name,
        home_long_name=home_name if home_long_name is None else home_long_name,
        away_source_team_id=away_id,
        away_name=away_name,
        away_long_name=away_name if away_long_name is None else away_long_name,
        kickoff_utc=datetime.datetime(2026, 8, 15, hour, tzinfo=UTC),
        source_capture_manifest_sha256=source.source_capture_manifest_sha256,
        source_raw_sha256=source.source_raw_sha256,
        source_request_date=source.request_date,
        source_observed_at=source.source_observed_at,
    )


def _bundle(
    sources: tuple[FotMobFixtureCandidateSource, ...],
    candidates: tuple[FotMobFixtureCandidate, ...],
) -> FotMobFixtureCandidateBundle:
    ordered_sources = tuple(
        sorted(sources, key=lambda item: (item.request_date, item.source_capture_manifest_sha256))
    )
    ordered_candidates = tuple(sorted(candidates, key=candidate_module._candidate_sort_key))
    duplicate_count, fixture_conflicts = candidate_module._make_fixture_observations(ordered_candidates)
    team_conflicts = candidate_module._make_team_conflicts(ordered_candidates)
    competition_conflicts = candidate_module._make_competition_conflicts(ordered_candidates)
    return FotMobFixtureCandidateBundle(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        dataset_name=CANDIDATE_DATASET_NAME,
        sources=ordered_sources,
        candidate_count=len(ordered_candidates),
        candidates=ordered_candidates,
        duplicate_source_match_id_count=duplicate_count,
        fixture_identity_conflict_count=len(fixture_conflicts),
        fixture_identity_conflicts=fixture_conflicts,
        team_identity_conflict_count=len(team_conflicts),
        team_identity_conflicts=team_conflicts,
        competition_identity_conflict_count=len(competition_conflicts),
        competition_identity_conflicts=competition_conflicts,
        safety=candidate_module._default_safety(),
    )


def _single_bundle(**candidate_kwargs):
    source = _source()
    candidate = _candidate(source, **candidate_kwargs)
    return _bundle((source,), (candidate,)), candidate, source


def _decision(
    candidate: FotMobFixtureCandidate,
    *,
    disposition: FixtureCandidateReviewDisposition = FixtureCandidateReviewDisposition.APPROVED,
    reviewed_at: datetime.datetime | None = None,
    candidate_sha: str | None = None,
    reviewer_reference: str = "operator:test-review",
    notes: str = "reviewed against preserved capture",
) -> FotMobFixtureCandidateReviewDecision:
    return FotMobFixtureCandidateReviewDecision(
        source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
        source_match_id=candidate.source_match_id,
        candidate_sha256=candidate_sha or sha256_fotmob_fixture_candidate(candidate),
        disposition=disposition,
        reviewed_at=reviewed_at
        or datetime.datetime(2026, 8, 10, 2, 30, tzinfo=UTC),
        reviewer_reference=reviewer_reference,
        notes=notes,
    )


def test_contract_constants_and_empty_decisions_do_not_auto_review():
    bundle, _, _ = _single_bundle()
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == "athena-fotmob-fixture-candidate-review-v1"
    assert reviewed.candidate_count == 1
    assert reviewed.decision_count == 0
    assert reviewed.approved_count == 0
    assert reviewed.rejected_count == 0
    assert reviewed.unreviewed_count == 1
    assert reviewed.approved_catalog_inputs == ()


def test_exact_approval_maps_candidate_to_pr29_catalog_input_without_normalization():
    bundle, candidate, source = _single_bundle(
        match_id=987,
        competition="Premier League!",
        home_name="VfL Wolfsburg (W)",
        home_long_name="VfL Wolfsburg Frauen",
        away_name="Åway—Club",
        away_long_name="Åway—Club Long",
        hour=17,
    )
    decision = _decision(candidate)
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, (decision,))
    assert reviewed.approved_count == 1
    item = reviewed.approved_catalog_inputs[0]
    catalog_input = item.to_catalog_input_dict()
    assert set(catalog_input) == INPUT_RECORD_KEYS
    assert catalog_input["schema_version"] == 1
    assert catalog_input["source"] == "FOTMOB"
    assert catalog_input["source_fixture_identifier"] == "987"
    assert catalog_input["home_team"] == "VfL Wolfsburg (W)"
    assert catalog_input["away_team"] == "Åway—Club"
    assert catalog_input["competition"] == "Premier League!"
    assert catalog_input["kickoff"] == "2026-08-15T17:00:00.000000Z"
    assert catalog_input["reviewed_at"] == "2026-08-10T02:30:00.000000Z"
    assert catalog_input["evidence_sha256"] == source.source_raw_sha256
    expected_capture = capture_identifier(
        request_date=source.request_date,
        timezone=source.timezone,
        ccode3=source.ccode3,
        observed_at=source.source_observed_at,
        raw_sha256=source.source_raw_sha256,
    )
    assert catalog_input["evidence_file_path"] == (
        f"{source.request_date}/{expected_capture}/{RAW_FILENAME}"
    )
    assert source.source_capture_manifest_sha256 in catalog_input["source_reference"]
    assert "home_long_name" not in catalog_input
    assert "away_long_name" not in catalog_input
    assert "fixture_identifier" not in catalog_input


def test_candidate_hash_is_canonical_and_content_sensitive():
    bundle, candidate, _ = _single_bundle()
    canonical = canonical_fotmob_fixture_candidate_bytes(candidate)
    assert canonical == (
        json.dumps(
            candidate.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert sha256_fotmob_fixture_candidate(candidate) == hashlib.sha256(canonical).hexdigest()
    changed = dataclasses.replace(candidate, home_name="Changed")
    assert sha256_fotmob_fixture_candidate(changed) != sha256_fotmob_fixture_candidate(candidate)
    assert bundle.candidates[0].home_name == "Home FC"


def test_decision_must_match_exact_candidate_hash_and_key():
    bundle, candidate, _ = _single_bundle()
    with pytest.raises(FotMobFixtureCandidateReviewError, match="does not match an exact candidate"):
        build_fotmob_fixture_candidate_review_bundle(
            bundle,
            (_decision(candidate, candidate_sha="f" * 64),),
        )
    wrong_id = dataclasses.replace(_decision(candidate), source_match_id=999)
    with pytest.raises(FotMobFixtureCandidateReviewError, match="does not match an exact candidate"):
        build_fotmob_fixture_candidate_review_bundle(bundle, (wrong_id,))


def test_duplicate_decisions_fail_closed():
    bundle, candidate, _ = _single_bundle()
    decision = _decision(candidate)
    with pytest.raises(FotMobFixtureCandidateReviewError, match="duplicate review decision"):
        build_fotmob_fixture_candidate_review_bundle(bundle, (decision, decision))


def test_review_cannot_predate_source_observation():
    bundle, candidate, _ = _single_bundle()
    decision = _decision(
        candidate,
        reviewed_at=candidate.source_observed_at - datetime.timedelta(microseconds=1),
    )
    with pytest.raises(FotMobFixtureCandidateReviewError, match="must not precede"):
        build_fotmob_fixture_candidate_review_bundle(bundle, (decision,))


def test_rejected_candidate_is_recorded_but_never_emitted_as_catalog_input():
    bundle, candidate, _ = _single_bundle()
    reviewed = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (_decision(candidate, disposition=FixtureCandidateReviewDisposition.REJECTED),),
    )
    assert reviewed.decision_count == 1
    assert reviewed.rejected_count == 1
    assert reviewed.approved_count == 0
    assert reviewed.approved_catalog_inputs == ()
    assert reviewed.unreviewed_count == 0


def test_team_identity_conflict_blocks_both_observed_variants_from_approval():
    source = _source(count=2)
    first = _candidate(source, match_id=1, home_id=394121, home_name="VfL Wolfsburg")
    second = _candidate(
        source,
        match_id=2,
        home_id=394121,
        home_name="VfL Wolfsburg (W)",
        hour=13,
    )
    bundle = _bundle((source,), (first, second))
    assert bundle.team_identity_conflict_count == 1
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    assert reviewed.blocked_candidate_count == 2
    assert all(
        FixtureCandidateReviewBlockReason.HOME_TEAM_IDENTITY_CONFLICT in block.reasons
        for block in reviewed.blocked_candidates
    )
    with pytest.raises(FotMobFixtureCandidateReviewError, match="unresolved review blockers"):
        build_fotmob_fixture_candidate_review_bundle(bundle, (_decision(first),))
    rejected = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (_decision(first, disposition=FixtureCandidateReviewDisposition.REJECTED),),
    )
    assert rejected.rejected_count == 1


def test_competition_identity_conflict_blocks_candidates():
    source = _source(count=2)
    first = _candidate(source, match_id=1, league_id=10, competition="League A")
    second = _candidate(source, match_id=2, league_id=10, competition="League B", hour=13)
    bundle = _bundle((source,), (first, second))
    assert bundle.competition_identity_conflict_count == 1
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    assert reviewed.blocked_candidate_count == 2
    assert all(
        FixtureCandidateReviewBlockReason.COMPETITION_IDENTITY_CONFLICT in block.reasons
        for block in reviewed.blocked_candidates
    )


def test_repeated_source_match_id_is_blocked_even_when_fixture_tuple_is_identical():
    source_one = _source(manifest_sha="1" * 64, raw_sha="2" * 64, assessment_sha="3" * 64, count=1)
    source_two = _source(
        manifest_sha="4" * 64,
        raw_sha="5" * 64,
        assessment_sha="6" * 64,
        count=1,
        second=1,
    )
    first = _candidate(source_one, match_id=55)
    second = _candidate(source_two, match_id=55)
    bundle = _bundle((source_one, source_two), (first, second))
    assert bundle.duplicate_source_match_id_count == 1
    assert bundle.fixture_identity_conflict_count == 0
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    assert reviewed.blocked_candidate_count == 2
    assert all(
        FixtureCandidateReviewBlockReason.DUPLICATE_SOURCE_MATCH_ID in block.reasons
        for block in reviewed.blocked_candidates
    )


def test_fixture_identity_conflict_is_preserved_as_blocker():
    source_one = _source(manifest_sha="1" * 64, raw_sha="2" * 64, assessment_sha="3" * 64, count=1)
    source_two = _source(
        manifest_sha="4" * 64,
        raw_sha="5" * 64,
        assessment_sha="6" * 64,
        count=1,
        second=1,
    )
    first = _candidate(source_one, match_id=55, home_id=101)
    second = _candidate(source_two, match_id=55, home_id=999)
    bundle = _bundle((source_one, source_two), (first, second))
    assert bundle.fixture_identity_conflict_count == 1
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    assert any(
        FixtureCandidateReviewBlockReason.FIXTURE_IDENTITY_CONFLICT in block.reasons
        for block in reviewed.blocked_candidates
    )


@pytest.mark.parametrize(
    ("candidate_kwargs", "reason"),
    [
        ({"home_name": ""}, FixtureCandidateReviewBlockReason.CATALOG_HOME_TEAM_INVALID),
        ({"home_name": " Home FC"}, FixtureCandidateReviewBlockReason.CATALOG_HOME_TEAM_INVALID),
        ({"away_name": ""}, FixtureCandidateReviewBlockReason.CATALOG_AWAY_TEAM_INVALID),
        ({"competition": " League"}, FixtureCandidateReviewBlockReason.CATALOG_COMPETITION_INVALID),
        (
            {"home_name": "Same", "away_name": "Same"},
            FixtureCandidateReviewBlockReason.CATALOG_HOME_AWAY_EQUAL,
        ),
    ],
)
def test_pr29_incompatible_exact_source_strings_are_blocked_not_normalized(candidate_kwargs, reason):
    bundle, candidate, _ = _single_bundle(**candidate_kwargs)
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    assert reviewed.blocked_candidate_count == 1
    assert reason in reviewed.blocked_candidates[0].reasons
    with pytest.raises(FotMobFixtureCandidateReviewError, match="unresolved review blockers"):
        build_fotmob_fixture_candidate_review_bundle(bundle, (_decision(candidate),))


def test_decision_input_order_does_not_change_canonical_review_bundle():
    source = _source(count=2)
    first = _candidate(source, match_id=1)
    second = _candidate(source, match_id=2, hour=13, home_id=303, away_id=404)
    bundle = _bundle((source,), (first, second))
    first_decision = _decision(first)
    second_decision = _decision(
        second,
        disposition=FixtureCandidateReviewDisposition.REJECTED,
    )
    forward = build_fotmob_fixture_candidate_review_bundle(
        bundle, (first_decision, second_decision)
    )
    reverse = build_fotmob_fixture_candidate_review_bundle(
        bundle, (second_decision, first_decision)
    )
    assert forward == reverse
    assert (
        canonical_fotmob_fixture_candidate_review_bundle_bytes(forward)
        == canonical_fotmob_fixture_candidate_review_bundle_bytes(reverse)
    )
    assert (
        sha256_fotmob_fixture_candidate_review_bundle(forward)
        == sha256_fotmob_fixture_candidate_review_bundle(reverse)
    )


def test_canonical_review_bundle_serialization_and_hash_are_exact():
    bundle, candidate, _ = _single_bundle()
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, (_decision(candidate),))
    canonical = canonical_fotmob_fixture_candidate_review_bundle_bytes(reviewed)
    assert canonical.endswith(b"\n") and not canonical.endswith(b"\n\n")
    assert canonical == (
        json.dumps(
            reviewed.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert sha256_fotmob_fixture_candidate_review_bundle(reviewed) == hashlib.sha256(canonical).hexdigest()


def test_safety_is_immutable_exact_false_and_no_global_source_qualification_occurs():
    bundle, _, _ = _single_bundle()
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    assert all(type(value) is bool and value is False for value in reviewed.safety.values())
    with pytest.raises(TypeError):
        reviewed.safety["source_qualified"] = True
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert capability.reliable_fixture_identity is CapabilityAvailability.UNKNOWN
    assert capability.full_time_score is CapabilityAvailability.UNKNOWN
    assert capability.freshness_metadata is CapabilityAvailability.UNKNOWN


def test_review_bundle_rejects_derived_count_mutation():
    bundle, candidate, _ = _single_bundle()
    reviewed = build_fotmob_fixture_candidate_review_bundle(bundle, (_decision(candidate),))
    with pytest.raises(FotMobFixtureCandidateReviewError, match="approved_count mismatch"):
        dataclasses.replace(reviewed, approved_count=0)
    with pytest.raises(FotMobFixtureCandidateReviewError, match="candidate review counts"):
        dataclasses.replace(reviewed, unreviewed_count=1)
    with pytest.raises(FotMobFixtureCandidateReviewError):
        dataclasses.replace(reviewed, schema_version=True)


def test_exact_enum_types_and_reviewer_reference_are_required():
    bundle, candidate, _ = _single_bundle()
    decision = _decision(candidate)
    with pytest.raises(FotMobFixtureCandidateReviewError):
        dataclasses.replace(decision, disposition="APPROVED")
    with pytest.raises(FotMobFixtureCandidateReviewError):
        dataclasses.replace(decision, reviewer_reference=" operator ")
    with pytest.raises(FotMobFixtureCandidateReviewError):
        build_fotmob_fixture_candidate_review_bundle(bundle, [object()])


def test_production_module_has_no_network_catalog_compile_model_or_betting_path():
    path = Path(review_module.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden_imports = {
        "http.client",
        "urllib.request",
        "requests",
        "httpx",
        "aiohttp",
        "playwright",
        "selenium",
        "intelligence.prediction_engine",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
    }
    assert not imports & forbidden_imports
    assert "compile_fixture_catalog" not in source
    assert "SOURCE_CAPABILITY_REGISTRY" not in source
    for forbidden_term in (
        "probability_authorized\": true",
        "pricing_authorized\": true",
        "selection_authorized\": true",
        "bet_authorized\": true",
    ):
        assert forbidden_term not in source.lower()
