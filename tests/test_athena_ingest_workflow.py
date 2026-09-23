from __future__ import annotations

from pathlib import Path

import pytest

from domain.ingest_contracts import AthenaIngestContractError
from scripts.execute_athena_ingest_workflow import execute_persisted_request
from scripts.resolve_athena_ingest_workflow_request import resolve_and_persist
from services.athena_ingest_service import ARTIFACT_RELATIVE, REQUEST_NAME, AthenaIngestServiceError


WORKFLOW = Path(".github/workflows/athena-ingest.yml")


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
    assert 'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"' in source
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in source
    assert source.count("scripts.resolve_athena_ingest_workflow_request") == 1
    assert "--execute-live-network" in source
    assert "if: always()" in source
    assert "athena-ingest-${{ github.run_id }}" in source
    assert "retention-days: 30" in source
    assert "if-no-files-found: error" in source
    for forbidden in ("issue_comment", "schedule:", "sportybet", "share-code", "wager", "current-shadow", "fresh-holdout", "p3-0-e1"):
        assert forbidden not in source.lower()


def test_resolver_persists_once_and_executor_requires_explicit_live_flag(tmp_path: Path) -> None:
    with pytest.raises(AthenaIngestContractError):
        resolve_and_persist(event_name="schedule", dates_input="20260901", repository_root=tmp_path)
    request = resolve_and_persist(
        event_name="workflow_dispatch", dates_input="20260901,20260902", repository_root=tmp_path,
    )
    path = tmp_path / ARTIFACT_RELATIVE / REQUEST_NAME
    assert path.read_bytes() == request.canonical_bytes
    with pytest.raises(AthenaIngestServiceError, match="execute-live-network"):
        execute_persisted_request(request_path=path, execute_live_network=False, repository_root=tmp_path)
    with pytest.raises(AthenaIngestServiceError, match="overwrite"):
        resolve_and_persist(event_name="workflow_dispatch", dates_input="20260903", repository_root=tmp_path)
