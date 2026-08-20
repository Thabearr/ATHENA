from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_reviewed_match_details_structure as structure_module
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureError,
    validate_json_content_type,
)
from domain.fotmob_fixture_candidate_review import sha256_fotmob_fixture_candidate
from domain.fotmob_fixture_candidates import (
    FixtureCandidateReviewStatus,
    FotMobFixtureCandidate,
)
from domain.fotmob_prospective_player_context_campaign import (
    CampaignResult,
    EXPECTED_AWAY_TEAM,
    EXPECTED_HOME_TEAM,
    FotMobProspectivePlayerContextCampaignError,
    FotMobProspectivePlayerContextCampaignReceipt,
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
from domain.fotmob_reviewed_match_details_structure import (
    DATASET_NAME as STRUCTURE_DATASET,
    SCHEMA_VERSION as STRUCTURE_SCHEMA,
    FotMobReviewedMatchDetailsStructureAssessment,
    JsonValueKind,
    StructuralField,
)


UTC = datetime.timezone.utc
KICKOFF = datetime.datetime(2026, 8, 22, 14, tzinfo=UTC)


def _candidate(
    *,
    match_id: int = 12345,
    home: str = EXPECTED_HOME_TEAM,
    away: str = EXPECTED_AWAY_TEAM,
    kickoff: datetime.datetime = KICKOFF,
) -> FotMobFixtureCandidate:
    return FotMobFixtureCandidate(
        review_status=FixtureCandidateReviewStatus.UNREVIEWED,
        source="FOTMOB",
        source_match_id=match_id,
        source_league_id=47,
        source_competition_primary_id=47,
        source_competition_name="Premier League",
        source_competition_ccode="ENG",
        home_source_team_id=10203,
        home_name=home,
        home_long_name=home,
        away_source_team_id=8463,
        away_name=away,
        away_long_name=away,
        kickoff_utc=kickoff,
        source_capture_manifest_sha256="1" * 64,
        source_raw_sha256="2" * 64,
        source_request_date="20260822",
        source_observed_at=datetime.datetime(2026, 8, 20, 10, tzinfo=UTC),
    )


def _assessment() -> FotMobReviewedMatchDetailsStructureAssessment:
    fields = (
        StructuralField("", (JsonValueKind.OBJECT,), 1),
        StructuralField("/content", (JsonValueKind.OBJECT,), 1),
        StructuralField("/content/lineup", (JsonValueKind.ARRAY,), 1),
        StructuralField("/content/lineup/*", (JsonValueKind.OBJECT,), 22),
        StructuralField("/content/lineup/*/playerId", (JsonValueKind.NUMBER,), 22),
        StructuralField("/content/lineup/*/position", (JsonValueKind.STRING,), 22),
        StructuralField("/content/unavailable", (JsonValueKind.ARRAY,), 1),
        StructuralField("/content/unavailable/*/reason", (JsonValueKind.STRING,), 3),
        StructuralField("/general", (JsonValueKind.OBJECT,), 1),
    )
    return FotMobReviewedMatchDetailsStructureAssessment(
        schema_version=STRUCTURE_SCHEMA,
        dataset_name=STRUCTURE_DATASET,
        evidence_receipt_sha256="3" * 64,
        manifest_sha256="4" * 64,
        raw_sha256="5" * 64,
        raw_size=1024,
        fixture_identifier="FOTMOB:12345",
        source_match_id="12345",
        top_level_keys=("content", "general"),
        node_count=60,
        max_depth=5,
        fields=fields,
        safety=structure_module._default_safety(),
    )


def _receipt(files=None):
    if files is None:
        files = tuple(
            sorted(
                (
                    evidence_file("fixture/response.json", b"r" * 100),
                    evidence_file("fixture/manifest.json", b"manifest"),
                    evidence_file("fixture/schema-assessment.json", b"schema"),
                    evidence_file("fixture/fixture-candidates.json", b"candidates"),
                ),
                key=lambda item: item.relative_path,
            )
        )
    file_map = {item.relative_path: item for item in files}
    return FotMobProspectivePlayerContextCampaignReceipt(
        repository="Thabearr/ATHENA",
        base_sha="a" * 40,
        repository_head_sha="b" * 40,
        workflow_name="Execute FotMob Prospective Player-Context Campaign",
        workflow_run_id=100,
        workflow_run_attempt=1,
        github_actor="Thabearr",
        started_at=datetime.datetime(2026, 8, 20, 10, tzinfo=UTC),
        completed_at=datetime.datetime(2026, 8, 20, 10, 1, tzinfo=UTC),
        campaign_result=CampaignResult.FIXTURE_REVIEW_NOT_GRANTED,
        resolved_fixture_identifier="FOTMOB:12345",
        resolved_source_match_id="12345",
        resolved_home_team=EXPECTED_HOME_TEAM,
        resolved_away_team=EXPECTED_AWAY_TEAM,
        resolved_kickoff=KICKOFF,
        fixture_candidate_sha256="6" * 64,
        fixture_raw_sha256=file_map["fixture/response.json"].sha256,
        fixture_raw_size=100,
        fixture_manifest_sha256=file_map["fixture/manifest.json"].sha256,
        fixture_schema_assessment_sha256=file_map["fixture/schema-assessment.json"].sha256,
        fixture_candidate_bundle_sha256=file_map["fixture/fixture-candidates.json"].sha256,
        fixture_review_ledger_sha256=None,
        fixture_catalog_sha256=None,
        fixture_catalog_manifest_sha256=None,
        fixture_admission_sha256=None,
        fixture_bootstrap_sha256=None,
        fixture_bootstrap_receipt_sha256=None,
        match_details_raw_sha256=None,
        match_details_raw_size=None,
        match_details_manifest_sha256=None,
        persisted_evidence_receipt_sha256=None,
        structure_assessment_sha256=None,
        player_context_report_sha256=None,
        files=tuple(files),
        safety=safety_flags(),
    )


def test_exact_target_resolution_has_no_fuzzy_name_matching() -> None:
    exact = _candidate()
    assert resolve_exact_target_candidate((exact,)) is exact
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        resolve_exact_target_candidate((_candidate(home="nottingham forest"),))


def test_exact_target_resolution_uses_reviewed_long_names_not_display_abbreviations() -> None:
    real_source_shape = dataclasses.replace(
        _candidate(match_id=5795367),
        home_name="Nottm Forest",
        away_name="Leeds",
    )
    assert resolve_exact_target_candidate((real_source_shape,)) is real_source_shape
    identity = candidate_identity(real_source_shape)
    assert identity["home_team"] == EXPECTED_HOME_TEAM
    assert identity["away_team"] == EXPECTED_AWAY_TEAM

    wrong_long_name = dataclasses.replace(
        real_source_shape, home_long_name="Nottingham Forest FC"
    )
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        resolve_exact_target_candidate((wrong_long_name,))


def test_wrong_request_date_and_kickoff_fail_exact_resolution() -> None:
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        resolve_exact_target_candidate((_candidate(),), request_date="20260821")
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        resolve_exact_target_candidate(
            (_candidate(kickoff=KICKOFF + datetime.timedelta(minutes=1)),)
        )


def test_malformed_content_type_fails_existing_capture_contract() -> None:
    with pytest.raises(FotMobDataMatchesCaptureError):
        validate_json_content_type("text/html")


def test_zero_or_multiple_exact_targets_fail_closed() -> None:
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        resolve_exact_target_candidate(())
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        resolve_exact_target_candidate((_candidate(), _candidate(match_id=54321)))


def test_candidate_sha_binds_entire_exact_source_candidate() -> None:
    original = _candidate()
    changed = _candidate(match_id=12346)
    assert sha256_fotmob_fixture_candidate(original) != sha256_fotmob_fixture_candidate(changed)


def test_player_looking_paths_are_neutral_review_candidates_only() -> None:
    report = build_player_context_review_candidate_report(
        _assessment(),
        observed_at=datetime.datetime(2026, 8, 20, 10, tzinfo=UTC),
    )
    assert report["candidate_count"] == 6
    assert all(
        item["neutral_classification"] == "PLAYER_CONTEXT_REVIEW_CANDIDATE"
        for item in report["candidates"]
    )
    assert all(value is False for value in report["safety"].values())


def test_review_candidate_order_is_deterministic_and_nonsemantic() -> None:
    assessment = _assessment()
    first = build_player_context_review_candidate_report(
        assessment, observed_at=datetime.datetime(2026, 8, 20, 10, tzinfo=UTC)
    )
    second = build_player_context_review_candidate_report(
        dataclasses.replace(assessment),
        observed_at=datetime.datetime(2026, 8, 20, 10, tzinfo=UTC),
    )
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    paths = [item["json_pointer_pattern"] for item in first["candidates"]]
    assert paths == sorted(paths)
    assert "PLAYER_ID" not in canonical_json_bytes(first).decode("utf-8")
    assert "CONFIRMED_LINEUP" not in canonical_json_bytes(first).decode("utf-8")


def test_pr53_cardinality_limit_remains_explicit() -> None:
    report = build_player_context_review_candidate_report(
        _assessment(), observed_at=datetime.datetime(2026, 8, 20, 10, tzinfo=UTC)
    )
    assert report["array_cardinality_limit"].startswith("PR53_DOES_NOT_RETAIN")
    assert all(item["array_cardinality"] is None for item in report["candidates"])


def test_missing_player_context_structure_remains_explicit_zero_not_success() -> None:
    assessment = dataclasses.replace(
        _assessment(),
        node_count=2,
        max_depth=1,
        fields=(
            StructuralField("", (JsonValueKind.OBJECT,), 1),
            StructuralField("/general", (JsonValueKind.OBJECT,), 1),
        ),
    )
    report = build_player_context_review_candidate_report(
        assessment, observed_at=datetime.datetime(2026, 8, 20, 10, tzinfo=UTC)
    )
    assert report["candidate_count"] == 0
    assert report["candidates"] == []


def test_receipt_is_deterministic_canonical_json_and_all_authorities_false() -> None:
    receipt = _receipt()
    first = canonical_campaign_receipt_bytes(receipt)
    second = canonical_campaign_receipt_bytes(receipt)
    assert first == second
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    assert all(value is False for value in receipt.safety.values())
    assert campaign_receipt_from_bytes(first) == receipt


def test_evidence_receipt_detects_mutation_missing_and_extra_files() -> None:
    record = evidence_file("fixture/response.json", b'{"date":"20260822"}\n')
    verify_evidence_files((record,), {record.relative_path: b'{"date":"20260822"}\n'})
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        verify_evidence_files((record,), {record.relative_path: b"changed"})
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        verify_evidence_files((record,), {})
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        verify_evidence_files((record,), {record.relative_path: b'{"date":"20260822"}\n', "extra": b"x"})


def test_non_false_authority_is_rejected() -> None:
    changed = dict(safety_flags())
    changed["team_strength_feature_authorized"] = True
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        dataclasses.replace(_receipt(), safety=changed)


def test_success_receipt_requires_complete_pr38_through_pr53_chain() -> None:
    with pytest.raises(FotMobProspectivePlayerContextCampaignError, match="complete evidence chain"):
        dataclasses.replace(
            _receipt(),
            campaign_result=CampaignResult.SUCCESS_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAPTURED,
        )


def test_receipt_requires_exact_repository_head_sha() -> None:
    with pytest.raises(FotMobProspectivePlayerContextCampaignError, match="repository_head_sha"):
        dataclasses.replace(_receipt(), repository_head_sha="short")


def test_completed_file_without_stage_hash_fails_closed() -> None:
    extra = evidence_file("match-details/response.json", b"captured")
    files = tuple(sorted(_receipt().files + (extra,), key=lambda item: item.relative_path))
    with pytest.raises(FotMobProspectivePlayerContextCampaignError, match="lacks receipt identity"):
        dataclasses.replace(_receipt(), files=files)


def test_noncanonical_or_mutated_receipt_bytes_fail_replay() -> None:
    receipt = _receipt()
    raw = canonical_campaign_receipt_bytes(receipt)
    with pytest.raises(FotMobProspectivePlayerContextCampaignError):
        campaign_receipt_from_bytes(raw + b"\n")


def test_runner_has_no_arbitrary_source_match_id_input_and_review_defaults_closed() -> None:
    source = Path("scripts/run_fotmob_prospective_player_context_campaign.py").read_text(
        encoding="utf-8"
    )
    assert 'add_argument("--source-match-id"' not in source
    assert 'default="NOT_GRANTED"' in source
    assert 'args.campaign_mode == "CAPTURE_FIXTURE"' in source
    assert '"CONTINUE_EXACT_FIXTURE_ARTIFACT"' in source
    assert "_replay_source_fixture_artifact(" in source
    assert "capture_fotmob_reviewed_match_details(" in source


def test_continuation_replays_before_review_and_never_recaptures_fixture() -> None:
    source = Path("scripts/run_fotmob_prospective_player_context_campaign.py").read_text(
        encoding="utf-8"
    )
    continuation = source.index('if args.campaign_mode != "CONTINUE_EXACT_FIXTURE_ARTIFACT"')
    replay = source.index("_replay_source_fixture_artifact(", continuation)
    review_sha = source.index("args.fixture_review_candidate_sha != identity", replay)
    details = source.index("execution = capture_fotmob_reviewed_match_details(", review_sha)
    assert continuation < replay < review_sha < details
    continuation_source = source[continuation:details]
    assert "fetch_fotmob_data_matches(" not in continuation_source


def test_runner_reuses_exact_pr38_through_pr53_boundaries() -> None:
    source = Path("scripts/run_fotmob_prospective_player_context_campaign.py").read_text(
        encoding="utf-8"
    )
    required_calls = (
        "fetch_fotmob_data_matches(",
        "write_data_matches_capture_directory(",
        "assess_fotmob_data_matches_schema(",
        "build_fotmob_fixture_candidate_bundle(",
        "run_catalog_workflow(",
        "build_reviewed_fixture_catalog_admission(",
        "verify_reviewed_fixture_catalog_admission_artifact(",
        "build_reviewed_fixture_intelligence_bootstrap(",
        "verify_reviewed_fixture_intelligence_bootstrap_artifact(",
        "capture_fotmob_reviewed_match_details(",
        "verify_persisted_match_details_evidence(",
        "assess_reviewed_match_details_structure(",
    )
    for call in required_calls:
        assert call in source


def test_post_kickoff_guard_precedes_match_details_capture() -> None:
    source = Path("scripts/run_fotmob_prospective_player_context_campaign.py").read_text(
        encoding="utf-8"
    )
    guard = source.index("if _utc_now() >= kickoff:")
    capture = source.index("execution = capture_fotmob_reviewed_match_details(")
    assert guard < capture


def test_non_json_match_details_has_explicit_fail_closed_state() -> None:
    source = Path("scripts/run_fotmob_prospective_player_context_campaign.py").read_text(
        encoding="utf-8"
    )
    assert "json.loads(match_raw)" in source
    assert "CampaignResult.MATCH_DETAILS_NOT_JSON" in source


def test_workflow_is_owner_only_branch_bound_and_uploads_on_failure() -> None:
    workflow = Path(
        ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml"
    ).read_text(encoding="utf-8")
    assert "github.actor == 'Thabearr'" in workflow
    assert "github.event.pull_request.head.ref == 'evidence/fotmob-prospective-player-context-campaign'" in workflow
    assert "types: [edited]" in workflow
    assert "workflow_dispatch" not in workflow
    assert "CONTINUE_EXACT_FIXTURE_ARTIFACT" in workflow
    assert "actions/download-artifact@" in workflow
    assert "core.setOutput('source_run_id', sourceRun[1])" in workflow
    assert "run-id: ${{ steps.guard.outputs.source_run_id }}" in workflow
    assert "--source-campaign-artifact-directory source-campaign-artifact/fotmob-prospective-player-context-evidence" in workflow
    assert "if: always()" in workflow
    assert "persist-credentials: false" in workflow


def test_production_campaign_imports_no_sportybet_or_bypass_or_model_runtime() -> None:
    paths = (
        Path("domain/fotmob_prospective_player_context_campaign.py"),
        Path("scripts/run_fotmob_prospective_player_context_campaign.py"),
    )
    forbidden = {
        "sportybet",
        "fotmob_advanced_scraper",
        "fotmob_bypass_client",
        "score_matrix",
        "probability_engine",
        "pricing",
        "selection",
        "kelly",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.casefold() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").casefold())
        assert not any(token in name for token in forbidden for name in imports)


def test_workflow_uses_no_cookies_xmas_or_browser_impersonation() -> None:
    workflow = Path(
        ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml"
    ).read_text(encoding="utf-8").casefold()
    assert "cookie" not in workflow
    assert "x-mas" not in workflow
    assert "browser" not in workflow
    assert "fixture-review-disposition: approved" in workflow
    assert "catalog-admission-disposition: admitted" in workflow
    assert "fotmob-prospective-player-context-evidence" in workflow
