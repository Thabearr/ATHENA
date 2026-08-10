from __future__ import annotations

from pathlib import Path

import pytest

import scripts.manage_fotmob_reviewed_fixture_catalog as workflow_module
from scripts.manage_fotmob_reviewed_fixture_catalog import (
    FotMobReviewedFixtureCatalogWorkflowError,
    run,
)


class _FakeHandoff:
    catalog_input_jsonl_bytes = b'{"reviewed":"handoff"}\n'


def test_preflight_reconciliation_failure_happens_before_catalog_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = tmp_path / "fotmob-data-matches-captures"
    evidence_root.mkdir()
    fake_candidate_bundle = object()
    fake_review_bundle = object()
    fake_handoff = _FakeHandoff()
    preflight_result = object()
    writer_called = False

    monkeypatch.setattr(
        workflow_module,
        "_build_candidate_bundle_from_capture_directories",
        lambda capture_directories, repository_root: (
            fake_candidate_bundle,
            evidence_root,
        ),
    )
    monkeypatch.setattr(
        workflow_module,
        "sha256_fotmob_fixture_candidate_bundle",
        lambda bundle: "a" * 64,
    )
    monkeypatch.setattr(
        workflow_module,
        "load_review_decision_ledger",
        lambda path, expected_candidate_bundle_sha256: ((), "b" * 64),
    )
    monkeypatch.setattr(
        workflow_module,
        "build_fotmob_fixture_candidate_review_bundle",
        lambda candidate_bundle, decisions: fake_review_bundle,
    )
    monkeypatch.setattr(
        workflow_module,
        "build_fotmob_fixture_catalog_handoff",
        lambda candidate_bundle, review_bundle: fake_handoff,
    )
    monkeypatch.setattr(
        workflow_module,
        "compile_fixture_catalog",
        lambda **kwargs: preflight_result,
    )

    def fail_reconciliation(handoff, result):
        assert handoff is fake_handoff
        assert result is preflight_result
        raise FotMobReviewedFixtureCatalogWorkflowError("preflight mismatch")

    monkeypatch.setattr(
        workflow_module,
        "_assert_compiler_matches_handoff",
        fail_reconciliation,
    )

    def forbidden_writer(**kwargs):
        nonlocal writer_called
        writer_called = True
        pytest.fail("PR #29 writer must not run after failed preflight reconciliation")

    monkeypatch.setattr(workflow_module, "run_fixture_catalog", forbidden_writer)

    catalog_output = tmp_path / "catalog.json"
    manifest_output = tmp_path / "manifest.json"

    with pytest.raises(
        FotMobReviewedFixtureCatalogWorkflowError,
        match="preflight mismatch",
    ):
        run(
            capture_directories=["synthetic-capture"],
            decision_ledger=tmp_path / "review.json",
            as_of="2026-08-10T03:00:00Z",
            minimum_lead_seconds=0,
            catalog_output=catalog_output,
            manifest_output=manifest_output,
            repository_root=tmp_path,
            code_state={
                "evidence_git_head_sha": "c" * 40,
                "tracked_worktree_clean": True,
            },
        )

    assert writer_called is False
    assert not catalog_output.exists()
    assert not manifest_output.exists()
    assert not list(tmp_path.glob(".fotmob-reviewed-catalog-input-*"))
