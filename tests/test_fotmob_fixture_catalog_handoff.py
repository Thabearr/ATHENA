from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import domain.fotmob_fixture_catalog_handoff as handoff_module
from domain.fixture_catalog import INPUT_RECORD_KEYS, canonical_json_line_bytes
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
    DATASET_NAME,
    SCHEMA_VERSION,
    FotMobFixtureCatalogHandoffError,
    build_fotmob_fixture_catalog_handoff,
    canonical_fotmob_fixture_catalog_handoff_bytes,
    sha256_fotmob_fixture_catalog_handoff,
)


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
    away_id: int = 202,
    away_name: str = "Away FC",
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
        home_long_name=home_name,
        away_source_team_id=away_id,
        away_name=away_name,
        away_long_name=away_name,
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


def _decision(
    candidate: FotMobFixtureCandidate,
    *,
    disposition: FixtureCandidateReviewDisposition = FixtureCandidateReviewDisposition.APPROVED,
    minute: int = 30,
    notes: str = "reviewed against preserved capture",
) -> FotMobFixtureCandidateReviewDecision:
    return FotMobFixtureCandidateReviewDecision(
        source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
        source_match_id=candidate.source_match_id,
        candidate_sha256=sha256_fotmob_fixture_candidate(candidate),
        disposition=disposition,
        reviewed_at=datetime.datetime(2026, 8, 10, 2, minute, tzinfo=UTC),
        reviewer_reference="operator:test-review",
        notes=notes,
    )


def _approved_single():
    source = _source()
    candidate = _candidate(source)
    bundle = _bundle((source,), (candidate,))
    review = build_fotmob_fixture_candidate_review_bundle(bundle, (_decision(candidate),))
    return bundle, review, candidate


def test_contract_constants_and_exact_pr29_jsonl_emission():
    bundle, review, _ = _approved_single()
    handoff = build_fotmob_fixture_catalog_handoff(bundle, review)
    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == "athena-fotmob-fixture-catalog-handoff-v1"
    assert len(handoff.catalog_inputs) == 1
    payload = handoff.catalog_inputs[0].to_catalog_input_dict()
    assert set(payload) == INPUT_RECORD_KEYS
    expected = canonical_json_line_bytes(payload)
    assert handoff.catalog_input_jsonl_bytes == expected
    assert handoff.catalog_input_sha256 == hashlib.sha256(expected).hexdigest()


def test_handoff_rebuilds_review_bundle_from_candidate_bundle_and_exact_decisions():
    bundle, review, _ = _approved_single()
    handoff = build_fotmob_fixture_catalog_handoff(bundle, review)
    summary = handoff.to_dict()
    assert summary["candidate_bundle_sha256"] == review.candidate_bundle_sha256
    assert summary["review_bundle_sha256"]
    assert summary["candidate_count"] == 1
    assert summary["decision_count"] == 1
    assert summary["approved_count"] == 1
    assert summary["rejected_count"] == 0
    assert summary["unreviewed_count"] == 0
    assert summary["catalog_input_count"] == 1
    assert summary["catalog_input_byte_size"] == len(handoff.catalog_input_jsonl_bytes)
    assert summary["catalog_input_sha256"] == handoff.catalog_input_sha256


def test_zero_decisions_cannot_create_catalog_handoff():
    source = _source()
    candidate = _candidate(source)
    bundle = _bundle((source,), (candidate,))
    review = build_fotmob_fixture_candidate_review_bundle(bundle, ())
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="at least one explicit approved"):
        build_fotmob_fixture_catalog_handoff(bundle, review)


def test_rejected_only_review_cannot_create_catalog_handoff():
    source = _source()
    candidate = _candidate(source)
    bundle = _bundle((source,), (candidate,))
    review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (_decision(candidate, disposition=FixtureCandidateReviewDisposition.REJECTED),),
    )
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="at least one explicit approved"):
        build_fotmob_fixture_catalog_handoff(bundle, review)


def test_partial_explicit_review_is_visible_not_silently_relabelled_complete():
    source = _source(count=2)
    approved_candidate = _candidate(source, match_id=1001)
    untouched_candidate = _candidate(
        source,
        match_id=1002,
        home_id=303,
        away_id=404,
        hour=13,
    )
    bundle = _bundle((source,), (approved_candidate, untouched_candidate))
    review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (_decision(approved_candidate),),
    )
    handoff = build_fotmob_fixture_catalog_handoff(bundle, review)
    summary = handoff.to_dict()
    assert summary["candidate_count"] == 2
    assert summary["decision_count"] == 1
    assert summary["approved_count"] == 1
    assert summary["unreviewed_count"] == 1
    assert summary["catalog_input_count"] == 1


def test_candidate_bundle_sha_mutation_is_rejected_even_if_pr41_object_accepts_it():
    bundle, review, _ = _approved_single()
    tampered_review = dataclasses.replace(review, candidate_bundle_sha256="f" * 64)
    assert tampered_review.candidate_bundle_sha256 == "f" * 64
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="exact candidate bundle SHA-256"):
        build_fotmob_fixture_catalog_handoff(bundle, tampered_review)


def test_catalog_field_mutation_is_rejected_by_exact_review_rebuild():
    bundle, review, _ = _approved_single()
    original = review.approved_catalog_inputs[0]
    tampered_input = dataclasses.replace(original, home_team="Fabricated FC")
    tampered_review = dataclasses.replace(
        review,
        approved_catalog_inputs=(tampered_input,),
    )
    assert tampered_review.approved_catalog_inputs[0].home_team == "Fabricated FC"
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="exact deterministic result"):
        build_fotmob_fixture_catalog_handoff(bundle, tampered_review)


def test_evidence_sha_mutation_is_rejected_by_exact_review_rebuild():
    bundle, review, _ = _approved_single()
    original = review.approved_catalog_inputs[0]
    tampered_input = dataclasses.replace(original, evidence_sha256="e" * 64)
    tampered_review = dataclasses.replace(review, approved_catalog_inputs=(tampered_input,))
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="exact deterministic result"):
        build_fotmob_fixture_catalog_handoff(bundle, tampered_review)


def test_review_decision_metadata_mutation_cannot_be_smuggled_through_handoff():
    bundle, review, candidate = _approved_single()
    changed_decision = _decision(candidate, notes="different reviewed meaning")
    changed_input = dataclasses.replace(
        review.approved_catalog_inputs[0],
        notes="different reviewed meaning",
    )
    internally_consistent_but_fabricated = dataclasses.replace(
        review,
        decisions=(changed_decision,),
        approved_catalog_inputs=(changed_input,),
    )
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="exact deterministic result"):
        build_fotmob_fixture_catalog_handoff(bundle, internally_consistent_but_fabricated)


def test_wrong_candidate_bundle_for_valid_review_is_rejected():
    bundle, review, _ = _approved_single()
    other_source = _source(
        manifest_sha="4" * 64,
        raw_sha="5" * 64,
        assessment_sha="6" * 64,
    )
    other_bundle = _bundle((other_source,), (_candidate(other_source, match_id=9001),))
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="exact candidate bundle SHA-256"):
        build_fotmob_fixture_catalog_handoff(other_bundle, review)


def test_two_approvals_emit_deterministic_sorted_jsonl_independent_of_decision_order():
    source = _source(count=2)
    first = _candidate(source, match_id=5, hour=13)
    second = _candidate(source, match_id=2, home_id=303, away_id=404, hour=11)
    bundle = _bundle((source,), (first, second))
    first_decision = _decision(first, minute=31)
    second_decision = _decision(second, minute=32)
    forward_review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (first_decision, second_decision),
    )
    reverse_review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (second_decision, first_decision),
    )
    forward = build_fotmob_fixture_catalog_handoff(bundle, forward_review)
    reverse = build_fotmob_fixture_catalog_handoff(bundle, reverse_review)
    assert forward.catalog_input_jsonl_bytes == reverse.catalog_input_jsonl_bytes
    assert canonical_fotmob_fixture_catalog_handoff_bytes(forward) == (
        canonical_fotmob_fixture_catalog_handoff_bytes(reverse)
    )
    assert sha256_fotmob_fixture_catalog_handoff(forward) == (
        sha256_fotmob_fixture_catalog_handoff(reverse)
    )


def test_canonical_handoff_bytes_and_hash_are_exact():
    bundle, review, _ = _approved_single()
    handoff = build_fotmob_fixture_catalog_handoff(bundle, review)
    canonical = canonical_fotmob_fixture_catalog_handoff_bytes(handoff)
    assert canonical.endswith(b"\n") and not canonical.endswith(b"\n\n")
    assert canonical == (
        json.dumps(
            handoff.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert sha256_fotmob_fixture_catalog_handoff(handoff) == hashlib.sha256(canonical).hexdigest()


def test_safety_is_immutable_and_every_downstream_authorization_remains_false():
    bundle, review, _ = _approved_single()
    handoff = build_fotmob_fixture_catalog_handoff(bundle, review)
    assert all(type(value) is bool and value is False for value in handoff.safety.values())
    assert handoff.safety["fixture_catalog_compile_authorized"] is False
    assert handoff.safety["fixture_catalog_write_authorized"] is False
    assert handoff.safety["fixture_catalog_promotion_authorized"] is False
    assert handoff.safety["intelligence_authorized"] is False
    assert handoff.safety["bet_authorized"] is False
    with pytest.raises(TypeError):
        handoff.safety["bet_authorized"] = True
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="must be exact bool False"):
        dataclasses.replace(
            handoff,
            safety={**dict(handoff.safety), "fixture_catalog_compile_authorized": True},
        )


def test_exact_domain_types_are_required():
    bundle, review, _ = _approved_single()
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="candidate_bundle"):
        build_fotmob_fixture_catalog_handoff(object(), review)
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="review_bundle"):
        build_fotmob_fixture_catalog_handoff(bundle, object())
    handoff = build_fotmob_fixture_catalog_handoff(bundle, review)
    with pytest.raises(FotMobFixtureCatalogHandoffError, match="handoff must be exact"):
        canonical_fotmob_fixture_catalog_handoff_bytes(object())
    assert handoff.catalog_inputs == review.approved_catalog_inputs


def test_production_module_has_no_network_compiler_write_model_pricing_or_betting_path():
    path = Path(handoff_module.__file__)
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
        "services.selection",
    }
    assert not imports & forbidden_imports
    assert "compile_fixture_catalog" not in source
    assert "manage_fixture_catalog" not in source
    assert "open(" not in source
    assert "write_bytes" not in source
    assert "write_text" not in source
    for forbidden_true in (
        '"fixture_catalog_compile_authorized": true',
        '"fixture_catalog_promotion_authorized": true',
        '"intelligence_authorized": true',
        '"pricing_authorized": true',
        '"selection_authorized": true',
        '"bet_authorized": true',
    ):
        assert forbidden_true not in source.lower()
