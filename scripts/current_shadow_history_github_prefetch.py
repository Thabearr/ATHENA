"""Bounded read-only GitHub prefetch for the current Shadow history audit.

The reviewed current-history issuer records every GitHub read at the point where
its audit consumes that read and then replays the audit from those exact bytes.
This helper does not change that evidence boundary.  It only warms a private
in-process cache underneath the recorder after the exact workflow-run universe
has already been captured.  The audit still requests every authoritative value
through its original reader surface, receives the same bytes, records them, and
replays them exactly.

Speculative read failures are deliberately discarded so the authoritative audit
gets a normal retry instead of inheriting a prefetch-only transport failure.
No football-provider request, evidence mutation, model authority, pricing,
selection, execution or wager authority is added here.
"""
from __future__ import annotations

import copy
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import threading
from collections.abc import Mapping
from typing import Any


PREFETCH_WORKERS = 8


@dataclass(frozen=True)
class HistoryGitHubPrefetchHooks:
    original_gh_json: Any
    original_gh_download: Any
    original_prefetch_universe: Any
    cached_gh_json: Any
    cached_gh_download: Any
    cached_prefetch_universe: Any
    executor: ThreadPoolExecutor


def _exact_primary_run(run: Any, *, projection: Any) -> bool:
    if type(run) is not dict or run.get("status") != "completed":
        return False
    continuity = projection.continuity
    if run.get("workflow_id") != continuity.PRIMARY_WORKFLOW_ID:
        return False
    if run.get("event") not in {"schedule", "workflow_dispatch"}:
        return False
    if run.get("head_branch") != "main":
        return False
    head_sha = run.get("head_sha")
    path = run.get("path")
    return type(path) is str and path in {
        continuity.PRIMARY_WORKFLOW_PATH,
        f"{continuity.PRIMARY_WORKFLOW_PATH}@{head_sha}",
    }


def install(latest_history: Any) -> HistoryGitHubPrefetchHooks:
    """Install one worker-local cache/prefetch layer below the evidence recorder."""

    lineage = latest_history.lineage_audit
    downloads = latest_history.pr175_projection
    projection = latest_history.recovery_projection

    original_gh_json = lineage._gh_json
    original_gh_download = downloads._gh_download_compatible
    original_prefetch_universe = projection._prefetch_workflow_run_universe

    executor = ThreadPoolExecutor(
        max_workers=PREFETCH_WORKERS,
        thread_name_prefix="athena-history-github",
    )
    lock = threading.Lock()
    json_futures: dict[str, Future] = {}
    binary_futures: dict[str, Future] = {}

    def submit_json(endpoint: str) -> Future:
        with lock:
            future = json_futures.get(endpoint)
            if future is None:
                future = executor.submit(original_gh_json, endpoint)
                json_futures[endpoint] = future
            return future

    def submit_binary(endpoint: str) -> Future:
        with lock:
            future = binary_futures.get(endpoint)
            if future is None:
                future = executor.submit(original_gh_download, endpoint)
                binary_futures[endpoint] = future
            return future

    def cached_gh_json(endpoint: str):
        value = submit_json(endpoint).result()
        # A fresh ``gh api`` call returns a detached JSON object.  Preserve that
        # caller contract even though the transport bytes were prefetched once.
        return copy.deepcopy(value)

    def cached_gh_download(endpoint: str) -> bytes:
        return submit_binary(endpoint).result()

    def settle_speculative(
        *,
        cache: dict[str, Future],
        keyed: list[tuple[str, Future]],
    ) -> None:
        if not keyed:
            return
        wait([future for _key, future in keyed])
        # A speculative transport failure is not evidence.  Remove only that
        # failed future so the later authoritative recorder call retries using
        # the original transport and captures its own success/failure exactly.
        for key, future in keyed:
            try:
                future.result()
            except Exception:
                with lock:
                    if cache.get(key) is future:
                        cache.pop(key, None)

    def cached_prefetch_universe(get_runs_page):
        universe = original_prefetch_universe(get_runs_page)
        runs = getattr(universe, "runs", ())
        if type(runs) is not tuple:
            return universe

        repository = latest_history.REPOSITORY
        primary_runs = [
            run for run in runs if _exact_primary_run(run, projection=projection)
        ]

        artifact_reads: list[tuple[str, Future]] = []
        artifact_key_by_run: dict[int, str] = {}
        for run in primary_runs:
            run_id = run.get("id")
            if type(run_id) is not int or run_id < 1:
                continue
            key = f"/repos/{repository}/actions/runs/{run_id}/artifacts"
            artifact_key_by_run[run_id] = key
            artifact_reads.append((key, submit_json(key)))

        # Continuity provenance uses exact source-watchdog run/job metadata.
        provenance_reads: list[tuple[str, Future]] = []
        for run in primary_runs:
            if run.get("event") != "workflow_dispatch":
                continue
            title = run.get("display_title")
            match = (
                projection.receipt_mirror.CONTINUITY_RUN_NAME_RE.fullmatch(title)
                if type(title) is str
                else None
            )
            if match is None:
                continue
            source_run_id = int(match.group(1))
            for key in (
                f"/repos/{repository}/actions/runs/{source_run_id}",
                f"/repos/{repository}/actions/runs/{source_run_id}/jobs?filter=latest&per_page=100",
            ):
                provenance_reads.append((key, submit_json(key)))

        # The current projection cross-checks the exact historical duplicate
        # pair and its watchdog by direct run identity when those runs exist in
        # the captured universe.
        present_ids = {run.get("id") for run in runs if type(run) is dict}
        historical_ids = {
            projection._HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
            projection._HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
        }
        if historical_ids.issubset(present_ids):
            for run_id in (
                projection._HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
                projection._HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
                projection._HISTORICAL_SAME_SLOT_WATCHDOG_RUN_ID,
            ):
                key = f"/repos/{repository}/actions/runs/{run_id}"
                provenance_reads.append((key, submit_json(key)))

        settle_speculative(cache=json_futures, keyed=artifact_reads)
        settle_speculative(cache=json_futures, keyed=provenance_reads)

        job_reads: list[tuple[str, Future]] = []
        zip_reads: list[tuple[str, Future]] = []
        verified_zip_inputs: list[tuple[int, dict[str, Any], str, Future]] = []

        for run in primary_runs:
            run_id = run.get("id")
            if type(run_id) is not int or run_id < 1:
                continue
            artifact_key = artifact_key_by_run.get(run_id)
            if artifact_key is None:
                continue
            artifact_future = json_futures.get(artifact_key)
            if artifact_future is None:
                continue
            try:
                payload = artifact_future.result()
            except Exception:
                continue
            if not isinstance(payload, Mapping):
                continue
            artifacts = payload.get("artifacts")
            if type(artifacts) is not list:
                continue
            if len(artifacts) == 0:
                key = (
                    f"/repos/{repository}/actions/runs/{run_id}/jobs"
                    "?filter=latest&per_page=100"
                )
                job_reads.append((key, submit_json(key)))
                continue
            try:
                artifact = lineage._candidate_artifact(payload, run_id)
            except Exception:
                # The authoritative audit will reproduce and report the exact
                # malformed-artifact failure; prefetch never normalizes it.
                continue
            artifact_id = artifact.get("id")
            if type(artifact_id) is not int or artifact_id < 1:
                continue
            key = f"/repos/{repository}/actions/artifacts/{artifact_id}/zip"
            future = submit_binary(key)
            zip_reads.append((key, future))
            verified_zip_inputs.append((run_id, dict(artifact), key, future))

        # The exact legacy queued/no-execution proof is outside the completed
        # run filter but always consumes its artifact/job metadata if present.
        if projection.LEGACY_QUEUED_NO_EXECUTION_RUN_ID in present_ids:
            run_id = projection.LEGACY_QUEUED_NO_EXECUTION_RUN_ID
            for key in (
                f"/repos/{repository}/actions/runs/{run_id}/artifacts",
                f"/repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100",
            ):
                job_reads.append((key, submit_json(key)))

        settle_speculative(cache=json_futures, keyed=job_reads)
        settle_speculative(cache=binary_futures, keyed=zip_reads)

        # Actions ZIP verification is already part of the authoritative audit.
        # Reuse that exact verifier here only to discover the immutable Release
        # tag/sidecar names whose network reads can be warmed in parallel.  Any
        # verification failure is ignored here and remains authoritative later.
        release_inputs: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        release_reads: list[tuple[str, Future]] = []
        for run_id, artifact, zip_key, future in verified_zip_inputs:
            if binary_futures.get(zip_key) is not future:
                continue
            try:
                zip_bytes = future.result()
                latest_history.mirror.verify_actions_artifact_zip_digest(
                    zip_bytes,
                    artifact.get("digest"),
                )
                verified = latest_history.mirror.verify_actions_artifact_bundle(
                    run_id=run_id,
                    artifact_name=artifact["name"],
                    zip_bytes=zip_bytes,
                )
            except Exception:
                continue
            release_tag = verified.get("release_tag")
            if type(release_tag) is not str or not release_tag:
                continue
            key = f"/repos/{repository}/releases/tags/{release_tag}"
            release_reads.append((key, submit_json(key)))
            release_inputs.append((artifact, verified, key))

        settle_speculative(cache=json_futures, keyed=release_reads)

        release_asset_reads: list[tuple[str, Future]] = []
        for artifact, verified, release_key in release_inputs:
            release_future = json_futures.get(release_key)
            if release_future is None:
                continue
            try:
                release = release_future.result()
            except Exception:
                continue
            if not isinstance(release, Mapping):
                continue
            assets = release.get("assets")
            if type(assets) is not list:
                continue
            for name in (artifact.get("name"), verified.get("receipt_name")):
                if type(name) is not str:
                    continue
                matches = [
                    asset
                    for asset in assets
                    if type(asset) is dict and asset.get("name") == name
                ]
                if len(matches) != 1:
                    continue
                asset_id = matches[0].get("id")
                if type(asset_id) is not int or asset_id < 1:
                    continue
                key = f"/repos/{repository}/releases/assets/{asset_id}"
                release_asset_reads.append((key, submit_binary(key)))

        settle_speculative(cache=binary_futures, keyed=release_asset_reads)
        return universe

    lineage._gh_json = cached_gh_json
    downloads._gh_download_compatible = cached_gh_download
    projection._prefetch_workflow_run_universe = cached_prefetch_universe
    return HistoryGitHubPrefetchHooks(
        original_gh_json=original_gh_json,
        original_gh_download=original_gh_download,
        original_prefetch_universe=original_prefetch_universe,
        cached_gh_json=cached_gh_json,
        cached_gh_download=cached_gh_download,
        cached_prefetch_universe=cached_prefetch_universe,
        executor=executor,
    )


def restore(latest_history: Any, hooks: HistoryGitHubPrefetchHooks) -> None:
    """Restore the exact original read surfaces and close the bounded pool."""

    if type(hooks) is not HistoryGitHubPrefetchHooks:
        raise TypeError("hooks must be HistoryGitHubPrefetchHooks")
    latest_history.lineage_audit._gh_json = hooks.original_gh_json
    latest_history.pr175_projection._gh_download_compatible = hooks.original_gh_download
    latest_history.recovery_projection._prefetch_workflow_run_universe = (
        hooks.original_prefetch_universe
    )
    hooks.executor.shutdown(wait=True, cancel_futures=True)
