from __future__ import annotations

from collections import Counter
import copy
import re
import threading
from types import SimpleNamespace

import pytest

from scripts import current_shadow_history_github_prefetch as prefetch


REPOSITORY = "Thabearr/ATHENA"
PRIMARY_WORKFLOW_ID = 123
PRIMARY_WORKFLOW_PATH = ".github/workflows/fresh.yml"
RUN_ID = 10
ARTIFACT_ID = 100
ARCHIVE_ASSET_ID = 200
RECEIPT_ASSET_ID = 201
ARTIFACT_NAME = "success-20260904T000700Z-run-10.tar.gz"
RECEIPT_NAME = f"{ARTIFACT_NAME}.receipt.json"
RELEASE_TAG = "athena-fresh-holdout-evidence-test"


def _run(**changes):
    value = {
        "id": RUN_ID,
        "workflow_id": PRIMARY_WORKFLOW_ID,
        "event": "schedule",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "path": PRIMARY_WORKFLOW_PATH,
        "display_title": "scheduled",
    }
    value.update(changes)
    return value


def _latest_history(*, runs, fail_first_artifact_read: bool = False):
    counts: Counter[str] = Counter()
    lock = threading.Lock()
    artifact_endpoint = f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/artifacts"
    zip_endpoint = f"/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}/zip"
    release_endpoint = f"/repos/{REPOSITORY}/releases/tags/{RELEASE_TAG}"
    archive_endpoint = f"/repos/{REPOSITORY}/releases/assets/{ARCHIVE_ASSET_ID}"
    receipt_endpoint = f"/repos/{REPOSITORY}/releases/assets/{RECEIPT_ASSET_ID}"

    artifacts = {
        "total_count": 1,
        "artifacts": [
            {
                "id": ARTIFACT_ID,
                "name": ARTIFACT_NAME,
                "digest": "sha256:" + "1" * 64,
                "expired": False,
            }
        ],
    }
    release = {
        "assets": [
            {"id": ARCHIVE_ASSET_ID, "name": ARTIFACT_NAME},
            {"id": RECEIPT_ASSET_ID, "name": RECEIPT_NAME},
        ]
    }

    def record(key: str) -> int:
        with lock:
            counts[key] += 1
            return counts[key]

    def gh_json(endpoint: str):
        attempt = record(endpoint)
        if endpoint == artifact_endpoint:
            if fail_first_artifact_read and attempt == 1:
                raise RuntimeError("speculative artifact transport failure")
            return copy.deepcopy(artifacts)
        if endpoint == release_endpoint:
            return copy.deepcopy(release)
        if endpoint.endswith("/jobs?filter=latest&per_page=100"):
            return {"total_count": 1, "jobs": []}
        if re.fullmatch(rf"/repos/{re.escape(REPOSITORY)}/actions/runs/[0-9]+", endpoint):
            return {"id": int(endpoint.rsplit("/", 1)[1])}
        raise AssertionError(endpoint)

    def gh_download(endpoint: str) -> bytes:
        record(endpoint)
        if endpoint == zip_endpoint:
            return b"actions-zip"
        if endpoint == archive_endpoint:
            return b"release-archive"
        if endpoint == receipt_endpoint:
            return b"release-receipt"
        raise AssertionError(endpoint)

    def candidate_artifact(payload, run_id):
        assert run_id == RUN_ID
        return payload["artifacts"][0]

    universe = SimpleNamespace(runs=tuple(runs))
    original_universe = lambda _reader: universe
    continuity = SimpleNamespace(
        PRIMARY_WORKFLOW_ID=PRIMARY_WORKFLOW_ID,
        PRIMARY_WORKFLOW_PATH=PRIMARY_WORKFLOW_PATH,
    )
    projection = SimpleNamespace(
        continuity=continuity,
        receipt_mirror=SimpleNamespace(
            CONTINUITY_RUN_NAME_RE=re.compile(
                r"ATHENA fresh-holdout workflow_dispatch source=([1-9][0-9]*) .*"
            )
        ),
        _prefetch_workflow_run_universe=original_universe,
        _HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID=900,
        _HISTORICAL_SAME_SLOT_NATURAL_RUN_ID=901,
        _HISTORICAL_SAME_SLOT_WATCHDOG_RUN_ID=902,
        LEGACY_QUEUED_NO_EXECUTION_RUN_ID=903,
    )
    lineage = SimpleNamespace(
        _gh_json=gh_json,
        _candidate_artifact=candidate_artifact,
    )
    downloads = SimpleNamespace(_gh_download_compatible=gh_download)
    mirror = SimpleNamespace(
        verify_actions_artifact_zip_digest=lambda raw, digest: (
            "verified" if raw == b"actions-zip" and digest.startswith("sha256:") else None
        ),
        verify_actions_artifact_bundle=lambda *, run_id, artifact_name, zip_bytes: (
            {
                "release_tag": RELEASE_TAG,
                "receipt_name": RECEIPT_NAME,
            }
            if run_id == RUN_ID
            and artifact_name == ARTIFACT_NAME
            and zip_bytes == b"actions-zip"
            else (_ for _ in ()).throw(AssertionError("wrong bundle identity"))
        ),
    )
    latest = SimpleNamespace(
        REPOSITORY=REPOSITORY,
        lineage_audit=lineage,
        pr175_projection=downloads,
        recovery_projection=projection,
        mirror=mirror,
    )
    return latest, counts, {
        "artifact": artifact_endpoint,
        "zip": zip_endpoint,
        "release": release_endpoint,
        "archive": archive_endpoint,
        "receipt": receipt_endpoint,
    }


def test_prefetch_warms_exact_history_reads_without_changing_returned_bytes() -> None:
    latest, counts, endpoints = _latest_history(runs=[_run()])
    original_json = latest.lineage_audit._gh_json
    original_download = latest.pr175_projection._gh_download_compatible
    original_universe = latest.recovery_projection._prefetch_workflow_run_universe

    hooks = prefetch.install(latest)
    try:
        universe = latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {"workflow_runs": []}
        )
        assert universe.runs == (_run(),)
        assert counts[endpoints["artifact"]] == 1
        assert counts[endpoints["zip"]] == 1
        assert counts[endpoints["release"]] == 1
        assert counts[endpoints["archive"]] == 1
        assert counts[endpoints["receipt"]] == 1

        first = latest.lineage_audit._gh_json(endpoints["artifact"])
        first["artifacts"].clear()
        second = latest.lineage_audit._gh_json(endpoints["artifact"])
        assert len(second["artifacts"]) == 1
        assert latest.pr175_projection._gh_download_compatible(endpoints["zip"]) == b"actions-zip"
        assert latest.pr175_projection._gh_download_compatible(endpoints["archive"]) == b"release-archive"
        assert latest.pr175_projection._gh_download_compatible(endpoints["receipt"]) == b"release-receipt"

        # Authoritative audit reads consume the warmed exact result; they do not
        # perform a second GitHub request and therefore preserve one snapshot.
        assert counts[endpoints["artifact"]] == 1
        assert counts[endpoints["zip"]] == 1
        assert counts[endpoints["archive"]] == 1
        assert counts[endpoints["receipt"]] == 1
    finally:
        prefetch.restore(latest, hooks)

    assert latest.lineage_audit._gh_json is original_json
    assert latest.pr175_projection._gh_download_compatible is original_download
    assert latest.recovery_projection._prefetch_workflow_run_universe is original_universe


def test_speculative_transport_failure_is_discarded_before_authoritative_retry() -> None:
    latest, counts, endpoints = _latest_history(
        runs=[_run()],
        fail_first_artifact_read=True,
    )
    hooks = prefetch.install(latest)
    try:
        latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {"workflow_runs": []}
        )
        assert counts[endpoints["artifact"]] == 1

        payload = latest.lineage_audit._gh_json(endpoints["artifact"])
        assert payload["artifacts"][0]["id"] == ARTIFACT_ID
        assert counts[endpoints["artifact"]] == 2
    finally:
        prefetch.restore(latest, hooks)


def test_non_primary_run_is_not_speculatively_prefetched() -> None:
    latest, counts, _endpoints = _latest_history(
        runs=[_run(workflow_id=PRIMARY_WORKFLOW_ID + 1)]
    )
    hooks = prefetch.install(latest)
    try:
        latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {"workflow_runs": []}
        )
        assert counts == Counter()
    finally:
        prefetch.restore(latest, hooks)


def test_prefetch_worker_bound_is_explicit_and_small() -> None:
    assert prefetch.PREFETCH_WORKERS == 8
