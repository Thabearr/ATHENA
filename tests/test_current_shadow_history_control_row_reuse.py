from __future__ import annotations

import hashlib
import re
from types import SimpleNamespace

import pytest

from scripts import current_shadow_history_github_persistent_cache as cache


RUN_ID = 99
WORKFLOW_ID = 1234
WORKFLOW_PATH = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
HEAD_SHA = "a" * 40
ZIP_BYTES = b"exact-actions-artifact-zip"
ARCHIVE_BYTES = b"exact-durable-history-archive"
ARCHIVE_SHA256 = hashlib.sha256(ARCHIVE_BYTES).hexdigest()
ARTIFACT_NAME = f"success-20260905T000700Z-run-{RUN_ID}.tar.gz"
RUN = {
    "id": RUN_ID,
    "status": "completed",
    "workflow_id": WORKFLOW_ID,
    "event": "schedule",
    "head_branch": "main",
    "head_sha": HEAD_SHA,
    "path": WORKFLOW_PATH,
}


def _latest(extract_control_rows):
    artifact = {
        "id": 777,
        "name": ARTIFACT_NAME,
        "digest": "sha256:" + hashlib.sha256(ZIP_BYTES).hexdigest(),
    }
    lineage = SimpleNamespace(
        _gh_json=lambda _endpoint: {"artifacts": [artifact]},
        _candidate_artifact=lambda payload, _run_id: payload["artifacts"][0],
        _is_exact_zero_artifact_payload=lambda payload: (
            type(payload) is dict
            and type(payload.get("artifacts")) is list
            and not payload["artifacts"]
        ),
        _extract_control_rows=extract_control_rows,
        ARTIFACT_RE=re.compile(r"(success|failure)-.*"),
    )
    projection = SimpleNamespace(
        continuity=SimpleNamespace(
            PRIMARY_WORKFLOW_ID=WORKFLOW_ID,
            PRIMARY_WORKFLOW_PATH=WORKFLOW_PATH,
        ),
        _prefetch_workflow_run_universe=lambda _reader: SimpleNamespace(runs=(RUN,)),
    )
    downloads = SimpleNamespace(
        _gh_download_compatible=lambda _endpoint: ZIP_BYTES,
    )
    mirror = SimpleNamespace(
        verify_actions_artifact_zip_digest=lambda payload, _digest: hashlib.sha256(
            payload
        ).hexdigest(),
        verify_actions_artifact_bundle=lambda **_kwargs: {
            "archive_bytes": ARCHIVE_BYTES,
            "archive_sha256": ARCHIVE_SHA256,
        },
    )
    return SimpleNamespace(
        REPOSITORY="Thabearr/ATHENA",
        lineage_audit=lineage,
        recovery_projection=projection,
        pr175_projection=downloads,
        mirror=mirror,
    )


def test_exact_archive_extraction_is_reused_only_after_successful_prewarm() -> None:
    calls: list[tuple[bytes, str, bool]] = []

    def extract(archive_bytes, expected_sha256, *, require_control):
        calls.append((archive_bytes, expected_sha256, require_control))
        assert hashlib.sha256(archive_bytes).hexdigest() == expected_sha256
        return ({"event": "TICK_COMMITTED", "require_control": require_control},)

    latest = _latest(extract)
    original_prefetch = latest.recovery_projection._prefetch_workflow_run_universe
    hooks = cache._install_control_row_reuse(latest)
    try:
        universe = latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {}
        )
        assert universe.runs == (RUN,)
        assert calls == [(ARCHIVE_BYTES, ARCHIVE_SHA256, True)]

        first = latest.lineage_audit._extract_control_rows(
            ARCHIVE_BYTES,
            ARCHIVE_SHA256,
            require_control=True,
        )
        assert calls == [(ARCHIVE_BYTES, ARCHIVE_SHA256, True)]
        first[0]["event"] = "MUTATED_CALLER_COPY"

        second = latest.lineage_audit._extract_control_rows(
            ARCHIVE_BYTES,
            ARCHIVE_SHA256,
            require_control=True,
        )
        assert second == ({"event": "TICK_COMMITTED", "require_control": True},)
        assert calls == [(ARCHIVE_BYTES, ARCHIVE_SHA256, True)]
    finally:
        cache._restore_control_row_reuse(latest, hooks)

    assert latest.lineage_audit._extract_control_rows is extract
    assert latest.recovery_projection._prefetch_workflow_run_universe is original_prefetch


def test_require_control_policy_is_part_of_reuse_identity() -> None:
    calls: list[bool] = []

    def extract(archive_bytes, expected_sha256, *, require_control):
        calls.append(require_control)
        assert hashlib.sha256(archive_bytes).hexdigest() == expected_sha256
        return ({"require_control": require_control},)

    latest = _latest(extract)
    hooks = cache._install_control_row_reuse(latest)
    try:
        latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {}
        )
        assert calls == [True]
        value = latest.lineage_audit._extract_control_rows(
            ARCHIVE_BYTES,
            ARCHIVE_SHA256,
            require_control=False,
        )
        assert value == ({"require_control": False},)
        assert calls == [True, False]
    finally:
        cache._restore_control_row_reuse(latest, hooks)


def test_speculative_extraction_failure_is_discarded_and_authoritative_call_retries() -> None:
    calls = 0

    def extract(archive_bytes, expected_sha256, *, require_control):
        nonlocal calls
        calls += 1
        assert hashlib.sha256(archive_bytes).hexdigest() == expected_sha256
        if calls == 1:
            raise RuntimeError("speculative extraction failed")
        return ({"event": "TICK_COMMITTED"},)

    latest = _latest(extract)
    hooks = cache._install_control_row_reuse(latest)
    try:
        latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {}
        )
        assert calls == 1
        assert latest.lineage_audit._extract_control_rows(
            ARCHIVE_BYTES,
            ARCHIVE_SHA256,
            require_control=True,
        ) == ({"event": "TICK_COMMITTED"},)
        assert calls == 2
    finally:
        cache._restore_control_row_reuse(latest, hooks)


def test_digest_mismatch_never_reuses_prewarmed_rows() -> None:
    calls = 0

    def extract(archive_bytes, expected_sha256, *, require_control):
        nonlocal calls
        calls += 1
        if hashlib.sha256(archive_bytes).hexdigest() != expected_sha256:
            raise ValueError("archive bytes changed before durable-state extraction")
        return ({"event": "TICK_COMMITTED"},)

    latest = _latest(extract)
    hooks = cache._install_control_row_reuse(latest)
    try:
        latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {}
        )
        assert calls == 1
        with pytest.raises(
            ValueError,
            match="archive bytes changed before durable-state extraction",
        ):
            latest.lineage_audit._extract_control_rows(
                ARCHIVE_BYTES + b"-changed",
                ARCHIVE_SHA256,
                require_control=True,
            )
        assert calls == 2
    finally:
        cache._restore_control_row_reuse(latest, hooks)
