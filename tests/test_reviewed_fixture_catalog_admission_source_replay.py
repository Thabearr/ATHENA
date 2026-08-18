from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
from domain.fixture_catalog import compile_fixture_catalog
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
)
from domain.reviewed_fixture_catalog_admission import (
    ReviewedFixtureCatalogAdmissionDisposition,
    sha256_reviewed_fixture_catalog_admission,
)
from domain.reviewed_fixture_catalog_admission_source_replay import (
    ADMISSION_FILENAME,
    DECISION_FILENAME,
    ReviewedFixtureCatalogAdmissionSourceReplayError,
    build_replay_decision,
    canonical_replay_decision_bytes,
    parse_replay_decision_bytes,
    replay_decision_sha256,
    store_source_replayed_admission,
    verify_source_replayed_admission_directory,
)


UTC = dt.timezone.utc
RAW_EVIDENCE = b"exact preserved FotMob response bytes\n"
RAW_SHA = hashlib.sha256(RAW_EVIDENCE).hexdigest()


def _compiled(tmp_path: Path):
    source = FotMobFixtureCandidateSource(
        source_capture_dataset_name=CAPTURE_DATASET_NAME,
        source_capture_schema_version=CAPTURE_SCHEMA_VERSION,
        source_capture_manifest_sha256="1" * 64,
        source_raw_sha256=RAW_SHA,
        source_raw_size=len(RAW_EVIDENCE),
        source_observed_at=dt.datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
        request_date="20260815",
        timezone="UTC",
        ccode3="NGA",
        schema_assessment_sha256="3" * 64,
        candidate_count=1,
    )
    candidate = FotMobFixtureCandidate(
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
        kickoff_utc=dt.datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        source_capture_manifest_sha256=source.source_capture_manifest_sha256,
        source_raw_sha256=source.source_raw_sha256,
        source_request_date=source.request_date,
        source_observed_at=source.source_observed_at,
    )
    duplicate_count, fixture_conflicts = candidate_module._make_fixture_observations(
        (candidate,)
    )
    team_conflicts = candidate_module._make_team_conflicts((candidate,))
    competition_conflicts = candidate_module._make_competition_conflicts((candidate,))
    bundle = FotMobFixtureCandidateBundle(
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
    review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (
            FotMobFixtureCandidateReviewDecision(
                source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
                source_match_id=candidate.source_match_id,
                candidate_sha256=sha256_fotmob_fixture_candidate(candidate),
                disposition=FixtureCandidateReviewDisposition.APPROVED,
                reviewed_at=dt.datetime(2026, 8, 10, 2, 30, tzinfo=UTC),
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
        as_of=dt.datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
        minimum_lead_seconds=3600,
        code_state={
            "evidence_git_head_sha": "a" * 40,
            "tracked_worktree_clean": True,
        },
    )
    return handoff, result


def _decision(tmp_path: Path, *, disposition=ReviewedFixtureCatalogAdmissionDisposition.ADMITTED):
    handoff, result = _compiled(tmp_path)
    decision = build_replay_decision(
        handoff=handoff,
        fixture_catalog_result=result,
        disposition=disposition,
        reviewed_at=dt.datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        reviewer_reference="operator:catalog-admission",
        notes="catalog-level admission review",
    )
    return handoff, result, decision


def test_replay_decision_round_trips_canonical_bytes(tmp_path: Path) -> None:
    _, _, decision = _decision(tmp_path)
    raw = canonical_replay_decision_bytes(decision)
    rebuilt = parse_replay_decision_bytes(raw)

    assert canonical_replay_decision_bytes(rebuilt) == raw
    assert replay_decision_sha256(rebuilt) == hashlib.sha256(raw).hexdigest()
    assert rebuilt.decision.disposition.value == "ADMITTED"


def test_source_replayed_admission_store_and_verify(tmp_path: Path) -> None:
    handoff, result, decision = _decision(tmp_path)

    directory, admission = store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )

    assert sorted(item.name for item in directory.iterdir()) == sorted(
        [ADMISSION_FILENAME, DECISION_FILENAME]
    )
    assert directory.name == sha256_reviewed_fixture_catalog_admission(admission)[:24]
    assert admission.decision.disposition.value == "ADMITTED"
    assert [item.fixture_identifier for item in admission.admitted_fixtures] == [
        "FOTMOB:1001"
    ]

    verified = verify_source_replayed_admission_directory(
        directory,
        handoff=handoff,
        fixture_catalog_result=result,
        repository_root=tmp_path,
    )
    assert (
        sha256_reviewed_fixture_catalog_admission(verified)
        == sha256_reviewed_fixture_catalog_admission(admission)
    )


def test_exact_replay_is_idempotent(tmp_path: Path) -> None:
    handoff, result, decision = _decision(tmp_path)
    first_dir, first = store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )
    second_dir, second = store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )
    assert second_dir == first_dir
    assert (
        sha256_reviewed_fixture_catalog_admission(second)
        == sha256_reviewed_fixture_catalog_admission(first)
    )


def test_rejected_review_can_be_preserved_without_admitted_fixtures(tmp_path: Path) -> None:
    handoff, result, decision = _decision(
        tmp_path,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    _, admission = store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )
    assert admission.decision.disposition.value == "REJECTED"
    assert admission.admitted_fixtures == ()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw + b"\n",
        lambda raw: b" " + raw,
        lambda raw: raw.replace(b'"ADMITTED"', b'"REJECTED"', 1),
    ),
)
def test_noncanonical_or_changed_decision_bytes_fail_closed(
    tmp_path: Path,
    mutate,
) -> None:
    _, _, decision = _decision(tmp_path)
    raw = canonical_replay_decision_bytes(decision)
    with pytest.raises(ReviewedFixtureCatalogAdmissionSourceReplayError):
        parse_replay_decision_bytes(mutate(raw))
