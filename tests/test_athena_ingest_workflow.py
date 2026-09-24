from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from domain.ingest_contracts import AthenaIngestContractError, AthenaIngestRequest, strict_json_loads
from scripts.execute_athena_ingest_workflow import execute_persisted_request
from scripts.resolve_athena_ingest_workflow_request import resolve_and_persist
from services.athena_ingest_service import (
    ARTIFACT_RELATIVE, RECEIPT_NAME, REQUEST_NAME, AthenaIngestServiceError,
)
from tests.test_athena_ingest_service import fake_response


WORKFLOW = Path(".github/workflows/athena-ingest.yml")
COMMIT_SHA = "c" * 40
MAIN_REF = "refs/heads/main"


def test_manual_only_workflow_has_bounded_reviewed_surface() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "name: ATHENA Canonical Ingest" in source
    assert "workflow_dispatch:" in source
    assert "schedule:" not in source
    assert source.count("      dates:") == 1
    assert "  contents: read" in source
    assert "contents: write" not in source
    assert "group: athena-ingest-fotmob" in source
    assert "cancel-in-progress: false" in source
    assert "timeout-minutes: 20" in source
    assert "ref: ${{ github.sha }}" in source
    assert "- name: Preflight exact main lineage" in source
    assert "id: lineage" in source
    assert "continue-on-error: true" in source
    assert 'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"' in source
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in source
    assert source.count("scripts.resolve_athena_ingest_workflow_request") == 1
    assert "--expected-git-sha \"${GITHUB_SHA}\"" in source
    assert "--expected-git-ref \"${GITHUB_REF}\"" in source
    assert source.count("--expected-git-sha \"${GITHUB_SHA}\"") == 2
    assert source.count("--expected-git-ref \"${GITHUB_REF}\"") == 2
    assert "--execute-live-network" in source
    assert "if: always()" in source
    assert "athena-ingest-${{ github.run_id }}" in source
    assert "retention-days: 30" in source
    assert "if-no-files-found: error" in source
    for forbidden in ("issue_comment", "schedule:", "sportybet", "share-code", "wager", "current-shadow", "fresh-holdout", "p3-0-e1"):
        assert forbidden not in source.lower()


def test_lineage_receipt_failure_flow_is_nonterminal_then_explicitly_fails() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    checkout = source.index("- name: Checkout exact requested commit")
    preflight_start = source.index("- name: Preflight exact main lineage")
    setup = source.index("- name: Set up Python 3.12")
    resolver = source.index("- name: Resolve request once")
    executor = source.index("- name: Execute reviewed FotMob source ingest")
    upload = source.index("- name: Preserve exact ingest evidence")
    final_failure = source.index("- name: Fail after preserving failed ingest evidence")
    assert checkout < preflight_start < setup < resolver < executor < upload < final_failure

    preflight = source[preflight_start:setup]
    assert "id: lineage" in preflight
    assert "continue-on-error: true" in preflight
    assert 'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"' in preflight
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in preflight

    resolver_step = source[resolver:executor]
    executor_step = source[executor:upload]
    upload_step = source[upload:final_failure]
    final_step = source[final_failure:]
    assert "--expected-git-sha \"${GITHUB_SHA}\"" in resolver_step
    assert "--expected-git-ref \"${GITHUB_REF}\"" in resolver_step
    assert "--expected-git-sha \"${GITHUB_SHA}\"" in executor_step
    assert "--expected-git-ref \"${GITHUB_REF}\"" in executor_step
    assert "--execute-live-network" in executor_step
    assert "if: always()" in upload_step
    assert "if-no-files-found: error" in upload_step
    assert "if: always()" in final_step
    assert "LINEAGE_OUTCOME: ${{ steps.lineage.outcome }}" in final_step
    assert "RESOLVER_OUTCOME: ${{ steps.resolve.outcome }}" in final_step
    assert "EXECUTOR_OUTCOME: ${{ steps.execute.outcome }}" in final_step
    assert '"${LINEAGE_OUTCOME}" != "success"' in final_step
    assert '"${RESOLVER_OUTCOME}" != "success"' in final_step
    assert '"${EXECUTOR_OUTCOME}" != "success"' in final_step
    assert '"${EXECUTOR_EXIT_CODE}" != "0"' in final_step
    assert "exit 1" in final_step


def test_invalid_resolution_writes_fail_closed_receipt(tmp_path: Path) -> None:
    with pytest.raises(AthenaIngestContractError):
        resolve_and_persist(
            event_name="workflow_dispatch", dates_input="20260901,not-a-date",
            repository_root=tmp_path, expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
        )
    root = tmp_path / ARTIFACT_RELATIVE
    receipt_path = root / RECEIPT_NAME
    assert root.is_dir()
    assert receipt_path.is_file()
    receipt = strict_json_loads(receipt_path.read_bytes())
    assert receipt["status"] == "FAILED"
    assert receipt["failure_code"] == "INVALID_REQUEST"
    assert receipt["stage"] == "REQUEST_RESOLUTION"
    assert receipt["exact_commit_sha"] == COMMIT_SHA
    assert receipt["request_sha256"] is None
    assert receipt["canonical_store_update_sha256"] is None
    assert receipt["raw_request_input_sha256"] == hashlib.sha256(b"20260901,not-a-date").hexdigest()
    assert receipt["provider_request_count"] == 0
    assert receipt["source_count"] == 0
    assert receipt["canonical_store_update_committed"] is False
    assert all(value is False for value in receipt["authorities"].values())
    assert b"not-a-date" not in receipt_path.read_bytes()
    assert not (root / REQUEST_NAME).exists()


def test_resolver_and_executor_bind_exact_git_lineage(tmp_path: Path) -> None:
    request = resolve_and_persist(
        event_name="workflow_dispatch", dates_input="20260901,20260902", repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
    )
    path = tmp_path / ARTIFACT_RELATIVE / REQUEST_NAME
    assert path.read_bytes() == request.canonical_bytes
    calls: list[str] = []
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        calls.append(request_date)
        return fake_response(request_date)
    assert execute_persisted_request(
        request_path=path, execute_live_network=True, repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
        git_head_provider=lambda _root: COMMIT_SHA, acquisition_callable=acquire,
    ) == 0
    assert calls == ["20260901", "20260902"]
    receipt = strict_json_loads((tmp_path / ARTIFACT_RELATIVE / RECEIPT_NAME).read_bytes())
    assert receipt["exact_commit_sha"] == COMMIT_SHA


def test_wrong_ref_writes_lineage_receipt_before_any_provider_request(tmp_path: Path) -> None:
    raw_input = "20260901,20260902"
    with pytest.raises(AthenaIngestContractError, match="refs/heads/main"):
        resolve_and_persist(
            event_name="workflow_dispatch", dates_input=raw_input, repository_root=tmp_path,
            expected_git_sha=COMMIT_SHA, expected_git_ref="refs/heads/feature/not-main",
        )

    root = tmp_path / ARTIFACT_RELATIVE
    receipt_path = root / RECEIPT_NAME
    assert root.is_dir()
    assert receipt_path.is_file()
    receipt = strict_json_loads(receipt_path.read_bytes())
    assert receipt["status"] == "FAILED"
    assert receipt["failure_code"] == "LINEAGE_MISMATCH"
    assert receipt["stage"] == "REQUEST_RESOLUTION"
    assert receipt["exact_commit_sha"] == COMMIT_SHA
    assert receipt["request_sha256"] is None
    assert receipt["canonical_store_update_sha256"] is None
    assert receipt["raw_request_input_sha256"] == hashlib.sha256(raw_input.encode("utf-8")).hexdigest()
    assert receipt["provider_request_count"] == 0
    assert receipt["source_count"] == 0
    assert receipt["canonical_store_update_committed"] is False
    assert all(value is False for value in receipt["authorities"].values())
    assert not (root / REQUEST_NAME).exists()


def test_head_mismatch_writes_typed_receipt_before_acquisition(tmp_path: Path) -> None:
    request = resolve_and_persist(
        event_name="workflow_dispatch", dates_input="20260901", repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
    )
    path = tmp_path / ARTIFACT_RELATIVE / REQUEST_NAME
    calls: list[str] = []
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        calls.append(request_date)
        return fake_response(request_date)
    actual = "d" * 40
    assert execute_persisted_request(
        request_path=path, execute_live_network=True, repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
        git_head_provider=lambda _root: actual, acquisition_callable=acquire,
    ) == 1
    assert calls == []
    receipt = strict_json_loads((tmp_path / ARTIFACT_RELATIVE / RECEIPT_NAME).read_bytes())
    assert receipt["failure_code"] == "LINEAGE_MISMATCH"
    assert receipt["stage"] == "REQUEST_RESOLUTION"
    assert receipt["exact_commit_sha"] == actual
    assert receipt["exact_commit_sha"] != COMMIT_SHA
    assert receipt["request_sha256"] == request.canonical_sha256
    assert receipt["provider_request_count"] == 0
    assert receipt["source_count"] == 0
    assert receipt["canonical_store_update_committed"] is False
    assert all(value is False for value in receipt["authorities"].values())


def test_noncanonical_persisted_request_gets_fail_closed_receipt(tmp_path: Path) -> None:
    resolve_and_persist(
        event_name="workflow_dispatch", dates_input="20260901", repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
    )
    root = tmp_path / ARTIFACT_RELATIVE
    request_path = root / REQUEST_NAME
    malformed = b"{\"not\":\"the request\"}\n"
    request_path.write_bytes(malformed)
    with pytest.raises(AthenaIngestServiceError, match="request"):
        execute_persisted_request(
            request_path=request_path, execute_live_network=True, repository_root=tmp_path,
            expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
            git_head_provider=lambda _root: COMMIT_SHA,
        )
    receipt = strict_json_loads((root / RECEIPT_NAME).read_bytes())
    assert receipt["failure_code"] == "INVALID_REQUEST"
    assert receipt["stage"] == "REQUEST_RESOLUTION"
    assert receipt["exact_commit_sha"] == COMMIT_SHA
    assert receipt["request_sha256"] is None
    assert receipt["raw_request_input_sha256"] == hashlib.sha256(malformed).hexdigest()
    assert receipt["provider_request_count"] == 0


def test_executor_without_explicit_live_flag_fails_closed(tmp_path: Path) -> None:
    request = resolve_and_persist(
        event_name="workflow_dispatch", dates_input="20260901", repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
    )
    path = tmp_path / ARTIFACT_RELATIVE / REQUEST_NAME
    assert execute_persisted_request(
        request_path=path, execute_live_network=False, repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
        git_head_provider=lambda _root: COMMIT_SHA,
    ) == 1
    receipt = strict_json_loads((tmp_path / ARTIFACT_RELATIVE / RECEIPT_NAME).read_bytes())
    assert receipt["failure_code"] == "LINEAGE_MISMATCH"
    assert receipt["stage"] == "REQUEST_RESOLUTION"
    assert receipt["exact_commit_sha"] == COMMIT_SHA
    assert receipt["request_sha256"] == request.canonical_sha256
    assert receipt["provider_request_count"] == 0
    assert receipt["source_count"] == 0
    assert receipt["canonical_store_update_committed"] is False
    assert all(value is False for value in receipt["authorities"].values())


def test_resolver_refuses_to_overwrite_existing_evidence(tmp_path: Path) -> None:
    original = resolve_and_persist(
        event_name="workflow_dispatch", dates_input="20260901", repository_root=tmp_path,
        expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
    )
    with pytest.raises(AthenaIngestContractError, match="refusing to replace"):
        resolve_and_persist(
            event_name="workflow_dispatch", dates_input="20260903", repository_root=tmp_path,
            expected_git_sha=COMMIT_SHA, expected_git_ref=MAIN_REF,
        )
    assert (tmp_path / ARTIFACT_RELATIVE / REQUEST_NAME).read_bytes() == original.canonical_bytes
