from __future__ import annotations

import ast
import datetime
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import scripts.manage_fotmob_reviewed_fixture_catalog as workflow_module
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as CAPTURE_DATASET_NAME,
    RAW_FILENAME,
    SCHEMA_VERSION as CAPTURE_SCHEMA_VERSION,
    capture_identifier,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
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
    sha256_fotmob_fixture_candidate_bundle,
)
from scripts.manage_fotmob_reviewed_fixture_catalog import (
    DATASET_NAME,
    DECISION_LEDGER_DATASET_NAME,
    SCHEMA_VERSION,
    FotMobReviewedFixtureCatalogWorkflowError,
    load_review_decision_ledger,
    run,
)


UTC = datetime.timezone.utc
CODE_STATE = {
    "evidence_git_head_sha": "a" * 40,
    "tracked_worktree_clean": True,
}


def _source(*, raw_sha: str, raw_size: int, count: int = 1) -> FotMobFixtureCandidateSource:
    return FotMobFixtureCandidateSource(
        source_capture_dataset_name=CAPTURE_DATASET_NAME,
        source_capture_schema_version=CAPTURE_SCHEMA_VERSION,
        source_capture_manifest_sha256="1" * 64,
        source_raw_sha256=raw_sha,
        source_raw_size=raw_size,
        source_observed_at=datetime.datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
        request_date="20260815",
        timezone="UTC",
        ccode3="NGA",
        schema_assessment_sha256="3" * 64,
        candidate_count=count,
    )


def _candidate(
    source: FotMobFixtureCandidateSource,
    *,
    match_id: int = 1001,
    home_id: int = 101,
    away_id: int = 202,
    hour: int = 12,
) -> FotMobFixtureCandidate:
    return FotMobFixtureCandidate(
        review_status=FixtureCandidateReviewStatus.UNREVIEWED,
        source=SOURCE_NAME,
        source_match_id=match_id,
        source_league_id=10,
        source_competition_primary_id=10,
        source_competition_name="League Omega",
        source_competition_ccode="NGA",
        home_source_team_id=home_id,
        home_name=f"Home {home_id}",
        home_long_name=f"Home {home_id}",
        away_source_team_id=away_id,
        away_name=f"Away {away_id}",
        away_long_name=f"Away {away_id}",
        kickoff_utc=datetime.datetime(2026, 8, 15, hour, tzinfo=UTC),
        source_capture_manifest_sha256=source.source_capture_manifest_sha256,
        source_raw_sha256=source.source_raw_sha256,
        source_request_date=source.request_date,
        source_observed_at=source.source_observed_at,
    )


def _bundle(
    source: FotMobFixtureCandidateSource,
    candidates: tuple[FotMobFixtureCandidate, ...],
) -> FotMobFixtureCandidateBundle:
    ordered = tuple(sorted(candidates, key=candidate_module._candidate_sort_key))
    duplicate_count, fixture_conflicts = candidate_module._make_fixture_observations(ordered)
    team_conflicts = candidate_module._make_team_conflicts(ordered)
    competition_conflicts = candidate_module._make_competition_conflicts(ordered)
    return FotMobFixtureCandidateBundle(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        dataset_name=CANDIDATE_DATASET_NAME,
        sources=(source,),
        candidate_count=len(ordered),
        candidates=ordered,
        duplicate_source_match_id_count=duplicate_count,
        fixture_identity_conflict_count=len(fixture_conflicts),
        fixture_identity_conflicts=fixture_conflicts,
        team_identity_conflict_count=len(team_conflicts),
        team_identity_conflicts=team_conflicts,
        competition_identity_conflict_count=len(competition_conflicts),
        competition_identity_conflicts=competition_conflicts,
        safety=candidate_module._default_safety(),
    )


def _decision_dict(
    candidate: FotMobFixtureCandidate,
    *,
    disposition: str = "APPROVED",
    reviewed_at: str = "2026-08-10T02:30:00Z",
    notes: str = "reviewed against preserved capture",
) -> dict[str, object]:
    return {
        "source_capture_manifest_sha256": candidate.source_capture_manifest_sha256,
        "source_match_id": candidate.source_match_id,
        "candidate_sha256": sha256_fotmob_fixture_candidate(candidate),
        "disposition": disposition,
        "reviewed_at": reviewed_at,
        "reviewer_reference": "operator:test-review",
        "notes": notes,
    }


def _write_ledger(
    path: Path,
    bundle: FotMobFixtureCandidateBundle,
    decisions: list[dict[str, object]],
) -> bytes:
    payload = {
        "schema_version": 1,
        "dataset_name": DECISION_LEDGER_DATASET_NAME,
        "candidate_bundle_sha256": sha256_fotmob_fixture_candidate_bundle(bundle),
        "decisions": decisions,
    }
    raw = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _evidence_root(
    tmp_path: Path,
    source: FotMobFixtureCandidateSource,
    raw: bytes,
) -> Path:
    root = tmp_path / ".cache" / "athena-research" / "fotmob-data-matches-captures"
    capture_name = capture_identifier(
        request_date=source.request_date,
        timezone=source.timezone,
        ccode3=source.ccode3,
        observed_at=source.source_observed_at,
        raw_sha256=source.source_raw_sha256,
    )
    capture = root / source.request_date / capture_name
    capture.mkdir(parents=True)
    (capture / RAW_FILENAME).write_bytes(raw)
    return root


def _synthetic_context(tmp_path: Path, *, count: int = 1):
    raw = b'{"preserved":"evidence"}\n'
    raw_sha = hashlib.sha256(raw).hexdigest()
    source = _source(raw_sha=raw_sha, raw_size=len(raw), count=count)
    candidates = tuple(
        _candidate(
            source,
            match_id=1001 + index,
            home_id=101 + index * 10,
            away_id=202 + index * 10,
            hour=12 + index,
        )
        for index in range(count)
    )
    bundle = _bundle(source, candidates)
    evidence_root = _evidence_root(tmp_path, source, raw)
    return bundle, candidates, evidence_root


def _patch_capture_build(monkeypatch, bundle, evidence_root):
    monkeypatch.setattr(
        workflow_module,
        "_build_candidate_bundle_from_capture_directories",
        lambda capture_directories, repository_root: (bundle, evidence_root),
    )


def test_contract_constants():
    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == "athena-fotmob-reviewed-fixture-catalog-workflow-v1"
    assert DECISION_LEDGER_DATASET_NAME == (
        "athena-fotmob-fixture-review-decision-ledger-v1"
    )


def test_decision_ledger_loads_exact_explicit_decision(tmp_path):
    bundle, candidates, _ = _synthetic_context(tmp_path)
    ledger = tmp_path / "decisions.json"
    raw = _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    decisions, ledger_sha = load_review_decision_ledger(
        ledger,
        expected_candidate_bundle_sha256=sha256_fotmob_fixture_candidate_bundle(bundle),
    )
    assert len(decisions) == 1
    assert decisions[0].disposition is FixtureCandidateReviewDisposition.APPROVED
    assert decisions[0].source_match_id == candidates[0].source_match_id
    assert ledger_sha == hashlib.sha256(raw).hexdigest()


def test_decision_ledger_wrong_candidate_bundle_anchor_fails_closed(tmp_path):
    bundle, candidates, _ = _synthetic_context(tmp_path)
    ledger = tmp_path / "decisions.json"
    _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    with pytest.raises(
        FotMobReviewedFixtureCatalogWorkflowError,
        match="exact rebuilt candidate bundle",
    ):
        load_review_decision_ledger(
            ledger,
            expected_candidate_bundle_sha256="f" * 64,
        )


def test_decision_ledger_duplicate_json_key_fails_closed(tmp_path):
    path = tmp_path / "decisions.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,'
        f'"dataset_name":"{DECISION_LEDGER_DATASET_NAME}",'
        f'"candidate_bundle_sha256":"{"1" * 64}","decisions":[]}}',
        encoding="utf-8",
    )
    with pytest.raises(
        FotMobReviewedFixtureCatalogWorkflowError,
        match="duplicate JSON key",
    ):
        load_review_decision_ledger(
            path,
            expected_candidate_bundle_sha256="1" * 64,
        )


def test_decision_ledger_rejects_schema_drift_and_bool_source_id(tmp_path):
    bundle, candidates, _ = _synthetic_context(tmp_path)
    path = tmp_path / "decisions.json"
    payload = {
        "schema_version": 1,
        "dataset_name": DECISION_LEDGER_DATASET_NAME,
        "candidate_bundle_sha256": sha256_fotmob_fixture_candidate_bundle(bundle),
        "decisions": [{**_decision_dict(candidates[0]), "source_match_id": True}],
        "unexpected": "drift",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FotMobReviewedFixtureCatalogWorkflowError, match="ledger keys"):
        load_review_decision_ledger(
            path,
            expected_candidate_bundle_sha256=sha256_fotmob_fixture_candidate_bundle(bundle),
        )

    payload.pop("unexpected")
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FotMobReviewedFixtureCatalogWorkflowError, match="exact integer"):
        load_review_decision_ledger(
            path,
            expected_candidate_bundle_sha256=sha256_fotmob_fixture_candidate_bundle(bundle),
        )


def test_decision_ledger_rejects_unknown_disposition(tmp_path):
    bundle, candidates, _ = _synthetic_context(tmp_path)
    path = tmp_path / "decisions.json"
    _write_ledger(
        path,
        bundle,
        [_decision_dict(candidates[0], disposition="MAYBE")],
    )
    with pytest.raises(FotMobReviewedFixtureCatalogWorkflowError, match="APPROVED or REJECTED"):
        load_review_decision_ledger(
            path,
            expected_candidate_bundle_sha256=sha256_fotmob_fixture_candidate_bundle(bundle),
        )


def test_generate_workflow_rebuilds_all_boundaries_and_invokes_real_pr29_compiler(
    tmp_path,
    monkeypatch,
):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    raw_ledger = _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    catalog_output = tmp_path / "out" / "catalog.json"
    manifest_output = tmp_path / "out" / "manifest.json"

    result = run(
        capture_directories=["ignored-by-test"],
        decision_ledger=ledger,
        as_of="2026-08-10T03:00:00Z",
        minimum_lead_seconds=0,
        catalog_output=catalog_output,
        manifest_output=manifest_output,
        repository_root=tmp_path,
        code_state=CODE_STATE,
    )

    assert result.mode == "GENERATE"
    assert result.decision_ledger_sha256 == hashlib.sha256(raw_ledger).hexdigest()
    assert catalog_output.read_bytes() == result.fixture_catalog_result.catalog_bytes
    assert manifest_output.read_bytes() == result.fixture_catalog_result.manifest_bytes
    assert len(result.fixture_catalog_result.records) == 1
    assert result.fixture_catalog_result.records[0].fixture_identifier == "FOTMOB:1001"
    assert result.fixture_catalog_result.normalized_input_sha256 == (
        result.summary["compiler_normalized_input_sha256"]
    )
    assert result.summary["candidate_bundle_sha256"] == (
        sha256_fotmob_fixture_candidate_bundle(bundle)
    )
    assert result.summary["approved_count"] == 1
    assert result.summary["fixture_count"] == 1
    assert result.summary["operation"]["fixture_catalog_compile_performed"] is True
    assert result.summary["operation"]["fixture_catalog_write_performed"] is True
    assert result.summary["operation"]["fixture_catalog_promotion_performed"] is False
    assert result.summary["operation"]["source_qualification_performed"] is False
    assert result.summary_bytes.endswith(b"\n")
    assert not list(evidence_root.parent.glob(".fotmob-reviewed-catalog-input-*"))


def test_check_mode_verifies_existing_catalog_without_writing_new_outputs(
    tmp_path,
    monkeypatch,
):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    catalog = tmp_path / "catalog.json"
    manifest = tmp_path / "manifest.json"
    generated = run(
        capture_directories=["ignored"],
        decision_ledger=ledger,
        as_of="2026-08-10T03:00:00Z",
        minimum_lead_seconds=0,
        catalog_output=catalog,
        manifest_output=manifest,
        repository_root=tmp_path,
        code_state=CODE_STATE,
    )
    checked = run(
        capture_directories=["ignored"],
        decision_ledger=ledger,
        as_of="2026-08-10T03:00:00Z",
        minimum_lead_seconds=0,
        check_catalog=catalog,
        check_manifest=manifest,
        repository_root=tmp_path,
        code_state=CODE_STATE,
    )
    assert checked.mode == "CHECK"
    assert checked.summary["operation"]["fixture_catalog_compile_performed"] is True
    assert checked.summary["operation"]["fixture_catalog_write_performed"] is False
    assert checked.fixture_catalog_result.catalog_bytes == generated.fixture_catalog_result.catalog_bytes
    assert checked.fixture_catalog_result.manifest_bytes == generated.fixture_catalog_result.manifest_bytes


def test_partial_review_compiles_only_explicit_approval_and_stays_visible(
    tmp_path,
    monkeypatch,
):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path, count=2)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    result = run(
        capture_directories=["ignored"],
        decision_ledger=ledger,
        as_of="2026-08-10T03:00:00Z",
        minimum_lead_seconds=0,
        catalog_output=tmp_path / "catalog.json",
        manifest_output=tmp_path / "manifest.json",
        repository_root=tmp_path,
        code_state=CODE_STATE,
    )
    assert result.summary["candidate_count"] == 2
    assert result.summary["decision_count"] == 1
    assert result.summary["approved_count"] == 1
    assert result.summary["unreviewed_count"] == 1
    assert result.summary["fixture_count"] == 1


def test_rejected_only_ledger_cannot_create_or_compile_catalog(tmp_path, monkeypatch):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    _write_ledger(
        ledger,
        bundle,
        [_decision_dict(candidates[0], disposition="REJECTED")],
    )
    catalog = tmp_path / "catalog.json"
    manifest = tmp_path / "manifest.json"
    with pytest.raises(
        FotMobReviewedFixtureCatalogWorkflowError,
        match="at least one explicit approved",
    ):
        run(
            capture_directories=["ignored"],
            decision_ledger=ledger,
            as_of="2026-08-10T03:00:00Z",
            minimum_lead_seconds=0,
            catalog_output=catalog,
            manifest_output=manifest,
            repository_root=tmp_path,
            code_state=CODE_STATE,
        )
    assert not catalog.exists()
    assert not manifest.exists()
    assert not list(evidence_root.parent.glob(".fotmob-reviewed-catalog-input-*"))


def test_decision_for_wrong_candidate_hash_fails_before_compiler_outputs(tmp_path, monkeypatch):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    decision = _decision_dict(candidates[0])
    decision["candidate_sha256"] = "f" * 64
    _write_ledger(ledger, bundle, [decision])
    catalog = tmp_path / "catalog.json"
    manifest = tmp_path / "manifest.json"
    with pytest.raises(FotMobReviewedFixtureCatalogWorkflowError, match="exact candidate"):
        run(
            capture_directories=["ignored"],
            decision_ledger=ledger,
            as_of="2026-08-10T03:00:00Z",
            minimum_lead_seconds=0,
            catalog_output=catalog,
            manifest_output=manifest,
            repository_root=tmp_path,
            code_state=CODE_STATE,
        )
    assert not catalog.exists() and not manifest.exists()


def test_pr29_as_of_gate_remains_authoritative(tmp_path, monkeypatch):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    _write_ledger(
        ledger,
        bundle,
        [_decision_dict(candidates[0], reviewed_at="2026-08-10T04:00:00Z")],
    )
    with pytest.raises(
        FotMobReviewedFixtureCatalogWorkflowError,
        match="reviewed_at must not be after as_of",
    ):
        run(
            capture_directories=["ignored"],
            decision_ledger=ledger,
            as_of="2026-08-10T03:00:00Z",
            minimum_lead_seconds=0,
            catalog_output=tmp_path / "catalog.json",
            manifest_output=tmp_path / "manifest.json",
            repository_root=tmp_path,
            code_state=CODE_STATE,
        )
    assert not list(evidence_root.parent.glob(".fotmob-reviewed-catalog-input-*"))


def test_pr29_evidence_sha_gate_remains_authoritative(tmp_path, monkeypatch):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    evidence_file = next(evidence_root.rglob(RAW_FILENAME))
    evidence_file.write_bytes(b"tampered")
    with pytest.raises(
        FotMobReviewedFixtureCatalogWorkflowError,
        match="evidence_sha256 does not match",
    ):
        run(
            capture_directories=["ignored"],
            decision_ledger=ledger,
            as_of="2026-08-10T03:00:00Z",
            minimum_lead_seconds=0,
            catalog_output=tmp_path / "catalog.json",
            manifest_output=tmp_path / "manifest.json",
            repository_root=tmp_path,
            code_state=CODE_STATE,
        )


def test_pr29_tracked_worktree_clean_gate_remains_authoritative(tmp_path, monkeypatch):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    with pytest.raises(
        FotMobReviewedFixtureCatalogWorkflowError,
        match="Tracked worktree must be clean",
    ):
        run(
            capture_directories=["ignored"],
            decision_ledger=ledger,
            as_of="2026-08-10T03:00:00Z",
            minimum_lead_seconds=0,
            catalog_output=tmp_path / "catalog.json",
            manifest_output=tmp_path / "manifest.json",
            repository_root=tmp_path,
            code_state={
                "evidence_git_head_sha": "a" * 40,
                "tracked_worktree_clean": False,
            },
        )


def test_incomplete_output_mode_fails_without_leaving_temporary_input(tmp_path, monkeypatch):
    bundle, candidates, evidence_root = _synthetic_context(tmp_path)
    _patch_capture_build(monkeypatch, bundle, evidence_root)
    ledger = tmp_path / "decisions.json"
    _write_ledger(ledger, bundle, [_decision_dict(candidates[0])])
    with pytest.raises(FotMobReviewedFixtureCatalogWorkflowError, match="Provide both catalog and manifest"):
        run(
            capture_directories=["ignored"],
            decision_ledger=ledger,
            as_of="2026-08-10T03:00:00Z",
            minimum_lead_seconds=0,
            catalog_output=tmp_path / "catalog.json",
            repository_root=tmp_path,
            code_state=CODE_STATE,
        )
    assert not list(evidence_root.parent.glob(".fotmob-reviewed-catalog-input-*"))


def test_decision_ledger_symlink_is_rejected_when_supported(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(FotMobReviewedFixtureCatalogWorkflowError, match="symlink"):
        load_review_decision_ledger(
            link,
            expected_candidate_bundle_sha256="1" * 64,
        )


def test_production_workflow_has_no_network_source_promotion_model_pricing_or_betting_path():
    path = Path(workflow_module.__file__)
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
    assert "source_qualification_performed\": True" not in source
    assert "fixture_catalog_promotion_performed\": True" not in source
    assert "intelligence_performed\": True" not in source
    assert "pricing_performed\": True" not in source
    assert "selection_performed\": True" not in source
    assert "bet_decision_performed\": True" not in source
