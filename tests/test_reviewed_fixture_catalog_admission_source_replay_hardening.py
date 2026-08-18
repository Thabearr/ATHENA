from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import domain.reviewed_fixture_catalog_admission_source_replay as replay
import scripts.replay_reviewed_fixture_catalog_admission as replay_cli
from domain.fixture_catalog import compile_fixture_catalog
from domain.fotmob_data_matches_capture import DATASET_NAME as CAPTURE_DATASET_NAME, SCHEMA_VERSION as CAPTURE_SCHEMA_VERSION
from domain.fotmob_fixture_candidate_review import FixtureCandidateReviewDisposition, FotMobFixtureCandidateReviewDecision, build_fotmob_fixture_candidate_review_bundle, sha256_fotmob_fixture_candidate
from domain.fotmob_fixture_candidates import DATASET_NAME as CANDIDATE_DATASET_NAME, SCHEMA_VERSION as CANDIDATE_SCHEMA_VERSION, SOURCE_NAME, FixtureCandidateReviewStatus, FotMobFixtureCandidate, FotMobFixtureCandidateBundle, FotMobFixtureCandidateSource
from domain.fotmob_fixture_catalog_handoff import build_fotmob_fixture_catalog_handoff
from domain.reviewed_fixture_catalog_admission import ReviewedFixtureCatalogAdmissionDisposition, sha256_reviewed_fixture_catalog_admission
from domain.reviewed_fixture_catalog_admission_source_replay import build_replay_decision

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
    duplicate_count, fixture_conflicts = candidate_module._make_fixture_observations((candidate,))
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
        code_state={"evidence_git_head_sha": "a" * 40, "tracked_worktree_clean": True},
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


def test_hash_shaped_forged_decision_lineage_cannot_cross_source_replay(tmp_path: Path) -> None:
    handoff, result, decision = _decision(tmp_path)
    forged_native = dataclasses.replace(decision.decision, handoff_sha256="f" * 64)
    forged = replay.ReviewedFixtureCatalogAdmissionReplayDecision(
        decision=forged_native,
        safety={key: False for key in replay._SAFETY_KEYS},
    )
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError):
        replay.store_source_replayed_admission(
            handoff=handoff,
            fixture_catalog_result=result,
            replay_decision=forged,
            repository_root=tmp_path,
        )


def test_stored_admission_tampering_fails_semantic_verification(tmp_path: Path) -> None:
    handoff, result, decision = _decision(tmp_path)
    directory, _ = replay.store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )
    path = directory / replay.ADMISSION_FILENAME
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError, match="stale|tampered|exact source-replayed"):
        replay._verify_semantic_admission_directory(
            directory,
            handoff=handoff,
            fixture_catalog_result=result,
            repository_root=tmp_path,
        )


def test_stored_decision_tampering_fails_before_admission_authority(tmp_path: Path) -> None:
    handoff, result, decision = _decision(tmp_path)
    directory, _ = replay.store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )
    path = directory / replay.DECISION_FILENAME
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError):
        replay._verify_semantic_admission_directory(
            directory,
            handoff=handoff,
            fixture_catalog_result=result,
            repository_root=tmp_path,
        )


def test_unexpected_entry_fails_closed_and_is_not_deleted(tmp_path: Path) -> None:
    handoff, result, decision = _decision(tmp_path)
    directory, _ = replay.store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )
    foreign = directory / "foreign.txt"
    foreign.write_text("do not delete", encoding="utf-8")
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError, match="contents mismatch"):
        replay._verify_semantic_admission_directory(
            directory,
            handoff=handoff,
            fixture_catalog_result=result,
            repository_root=tmp_path,
        )
    assert foreign.read_text(encoding="utf-8") == "do not delete"


def test_mkdir_race_never_deletes_competing_writer_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handoff, result, decision = _decision(tmp_path)
    expected_admission = replay.build_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
    )
    identity = sha256_reviewed_fixture_catalog_admission(expected_admission)[:24]
    target = tmp_path / replay.ALLOWED_OUTPUT_RELATIVE / identity
    real_mkdir = Path.mkdir
    raced = False

    def competing_mkdir(self: Path, *args, **kwargs):
        nonlocal raced
        if self == target and not raced:
            raced = True
            real_mkdir(self, *args, **kwargs)
            (self / "foreign.txt").write_text("winner", encoding="utf-8")
            raise FileExistsError("competing writer won")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", competing_mkdir)
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError, match="durably store"):
        replay.store_source_replayed_admission(
            handoff=handoff,
            fixture_catalog_result=result,
            replay_decision=decision,
            repository_root=tmp_path,
        )
    assert target.is_dir()
    assert (target / "foreign.txt").read_text(encoding="utf-8") == "winner"


def test_alternate_output_root_and_traversal_fail_closed(tmp_path: Path) -> None:
    handoff, result, decision = _decision(tmp_path)
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError, match="reviewed exact source-replay root"):
        replay.store_source_replayed_admission(
            handoff=handoff,
            fixture_catalog_result=result,
            replay_decision=decision,
            repository_root=tmp_path,
            output_root=tmp_path / ".cache" / "wrong",
        )
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError, match="traversal"):
        replay.store_source_replayed_admission(
            handoff=handoff,
            fixture_catalog_result=result,
            replay_decision=decision,
            repository_root=tmp_path,
            output_root=Path("..") / "escape",
        )


def test_replay_decision_safety_remains_false_and_immutable(tmp_path: Path) -> None:
    _, _, decision = _decision(tmp_path)
    assert all(value is False for value in decision.safety.values())
    with pytest.raises(TypeError):
        decision.safety["bet_authorized"] = True
    unsafe = dict(decision.safety)
    unsafe["bet_authorized"] = True
    with pytest.raises(replay.ReviewedFixtureCatalogAdmissionSourceReplayError, match="must be exact bool False"):
        replay.ReviewedFixtureCatalogAdmissionReplayDecision(decision=decision.decision, safety=unsafe)


def test_rejected_and_admitted_decisions_have_distinct_artifact_identity(tmp_path: Path) -> None:
    handoff, result, admitted_decision = _decision(tmp_path)
    _, admitted = replay.store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=admitted_decision,
        repository_root=tmp_path,
    )
    rejected_decision = replay.build_replay_decision(
        handoff=handoff,
        fixture_catalog_result=result,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
        reviewed_at=admitted_decision.decision.reviewed_at,
        reviewer_reference="operator:catalog-admission",
        notes="catalog-level rejection review",
    )
    _, rejected = replay.store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=rejected_decision,
        repository_root=tmp_path,
    )
    assert sha256_reviewed_fixture_catalog_admission(admitted) != sha256_reviewed_fixture_catalog_admission(rejected)


def test_public_consumption_revalidator_runs_catalog_source_replay_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handoff, result, decision = _decision(tmp_path)
    directory, expected = replay.store_source_replayed_admission(
        handoff=handoff,
        fixture_catalog_result=result,
        replay_decision=decision,
        repository_root=tmp_path,
    )
    calls = []

    class Replayed:
        def __init__(self):
            self.handoff = handoff
            self.fixture_catalog_result = result

    def fake_replay_catalog_sources(**kwargs):
        calls.append(kwargs)
        return Replayed()

    monkeypatch.setattr(replay_cli, "replay_catalog_sources", fake_replay_catalog_sources)
    rebuilt = replay_cli.revalidate_stored_admission_from_sources(
        directory,
        capture_directories=("capture-a",),
        fixture_review_decision_ledger=tmp_path / "fixture-review.json",
        check_catalog=tmp_path / "catalog.json",
        check_manifest=tmp_path / "manifest.json",
        repository_root=tmp_path,
    )
    assert len(calls) == 1
    assert calls[0]["capture_directories"] == ("capture-a",)
    assert sha256_reviewed_fixture_catalog_admission(rebuilt) == sha256_reviewed_fixture_catalog_admission(expected)
    assert "verify_source_replayed_admission_directory" not in replay.__all__
