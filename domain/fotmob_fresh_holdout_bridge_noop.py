"""Fail-closed receipt-bridge no-op proof for superseded fresh-holdout dispatches.

This module does not authorize acquisition, persistence, backfill, pricing, selection,
or wagering.  It only proves that a completed failed prospective continuity dispatch
was already superseded by a different current ``main`` and stopped before every
provider-acquisition or evidence-persistence step.  Such a run has no canonical
fresh-holdout receipt to mirror, so the durability bridge may finish as a verified
no-op instead of emitting a duplicate generic failure.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery


_DISPATCH_JOB_NAME = "execute fresh holdout tick"
_AUTH_STEP = "Authenticate continuity dispatch source"
_STATE_STEP = "Restore newest durable lineage and resolve schedule slot"
_POST_CONTROL_REQUIRED_SKIPS = (
    "Restore or materialize PR119 bootstrap projection",
    "Execute reviewed fresh-holdout collection tick",
    "Reconcile any staged capture lineage",
    "Package durable state archive",
    "Upload authoritative 90-day Actions artifact",
    "Publish and verify long-lived evidence release asset",
)
_PREACQUISITION_FAILURE_PATTERNS = (
    {_AUTH_STEP: "failure", _STATE_STEP: "skipped"},
    {_AUTH_STEP: "success", _STATE_STEP: "failure"},
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _exact_sha(value: Any) -> str | None:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        return None
    return value


def prove_superseded_preacquisition_no_mirror(
    run: Mapping[str, Any],
    artifact_data: Mapping[str, Any],
    jobs_data: Mapping[str, Any],
    *,
    expected_source_head_sha: str,
    current_main_sha: str,
) -> bool:
    """Return True only for the exact superseded pre-acquisition failure lane.

    The existing reviewed continuity pre-acquisition predicate remains the primary
    no-observation authority.  This proof narrows that predicate further: the source
    run must be on the watchdog-pinned head, live ``main`` must have moved to a
    different exact SHA, failure must occur in authentication or state resolution,
    and every bootstrap/acquisition/persistence step must be skipped.
    """

    expected_head = _exact_sha(expected_source_head_sha)
    live_head = _exact_sha(current_main_sha)
    if expected_head is None or live_head is None or expected_head == live_head:
        return False
    if not isinstance(run, Mapping) or run.get("head_sha") != expected_head:
        return False
    if not isinstance(artifact_data, Mapping) or not isinstance(jobs_data, Mapping):
        return False

    try:
        proven_preacquisition = recovery._prove_continuity_preacquisition_control_failure(
            run,
            artifact_data,
            lambda _run_id: jobs_data,
        )
    except Exception:
        return False
    if not proven_preacquisition:
        return False

    jobs = jobs_data.get("jobs")
    if type(jobs) is not list:
        return False
    reviewed_jobs = [
        job
        for job in jobs
        if type(job) is dict and job.get("name") == _DISPATCH_JOB_NAME
    ]
    if len(reviewed_jobs) != 1:
        return False
    job = reviewed_jobs[0]
    if job.get("status") != "completed" or job.get("conclusion") != "failure":
        return False
    steps = job.get("steps")
    if type(steps) is not list:
        return False

    by_name: dict[str, Mapping[str, Any]] = {}
    for step in steps:
        if type(step) is not dict:
            return False
        name = step.get("name")
        if type(name) is not str or name in by_name:
            return False
        by_name[name] = step

    for name in (_AUTH_STEP, _STATE_STEP, *_POST_CONTROL_REQUIRED_SKIPS):
        step = by_name.get(name)
        if step is None or step.get("status") != "completed":
            return False

    if not any(
        all(by_name[name].get("conclusion") == result for name, result in pattern.items())
        for pattern in _PREACQUISITION_FAILURE_PATTERNS
    ):
        return False

    return all(
        by_name[name].get("conclusion") == "skipped"
        for name in _POST_CONTROL_REQUIRED_SKIPS
    )
