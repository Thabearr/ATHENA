#!/usr/bin/env python3
"""Hosted P3.0-E1 capture wrapper with reviewed Current Shadow runtime reuse.

This module changes no source, evidence, probability, pricing, Router, Portfolio,
or authority semantics.  The P3.0-E1 collector intentionally calls the reviewed
Current Shadow source/Price-All/Router boundary directly.  Hosted Current Shadow
uses worker-local exact-success reuse around expensive immutable PR151 history
validation; bypassing those computation-only layers caused run 34700175969 to
consume the workflow's 75-minute hard ceiling before the collector could write
an artifact.

Install only the same reviewed exact-success history/verification reuse needed
through Router, then invoke the unchanged collector.  Every hook is restored in
LIFO order.  No Portfolio, delivery, authentication, account-state, or betting
operation is introduced.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import os
import signal
from typing import Iterator, Sequence

from domain import _current_shadow_quote_binding as quote_binding
from domain import current_shadow_all_market_runner as runner
from scripts import capture_p3_0_paired_evidence as collector
from scripts import current_shadow_history_artifact_verification_reuse as verification_reuse
from scripts import current_shadow_history_builder_audit_reuse as builder_audit_reuse
from scripts import current_shadow_history_github_persistent_cache as history_github_cache
from scripts import current_shadow_history_semantic_replay_reuse as semantic_replay_reuse
from scripts import execute_current_shadow_all_market as all_market_cli
from scripts import execute_current_shadow_all_market_summary_reuse as summary_cli


PRE_CAPTURE_BUDGET_SECONDS = 15 * 60
HOSTED_CAPTURE_TIMEOUT_SECONDS = 90 * 60
ARTIFACT_UPLOAD_MARGIN_SECONDS = 15 * 60
WORKFLOW_JOB_TIMEOUT_SECONDS = 120 * 60


class P30HostedCaptureTimeoutError(RuntimeError):
    """Raised inside the collector so its existing fail-closed receipt is written."""


def _restore_history_validation(originals: tuple[object, object, object]) -> None:
    original_replay, original_success_materials, original_prefix_derive = originals
    runner.latest_history._replay_audit_from_evidence = original_replay
    runner.latest_history._success_materials = original_success_materials
    runner.latest_history.prefix._derive = original_prefix_derive


def _restore_history_builder(original: object) -> None:
    runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = original


def _restore_research_xg(original: object) -> None:
    quote_binding.prc._research_xg_from_complete_current_history = original


def _restore_history_sha(original: object) -> None:
    runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff = original


def _restore_price_verification(originals: tuple[object, object]) -> None:
    original_price_verify, original_quote_verify = originals
    runner.price_module.verify_current_shadow_price_context = original_price_verify
    quote_binding.verify_current_shadow_price_context = original_quote_verify


def _install_history_cache_with_worker_reuse():
    """Activate only the cache layer's reviewed worker-local computation reuses.

    The persistent-cache installer gates its control-row and durable-prefix
    computation caches on the Current Shadow worker marker.  The P3.0 hosted
    wrapper is not a Current Shadow execution worker, so expose that marker only
    for the duration of installer construction, then restore the environment
    before any capture code runs.  The installed hooks themselves are the same
    exact-success/fail-closed hooks used by the reviewed worker.
    """

    key = history_github_cache.CURRENT_SHADOW_WORKER_ENV
    prior = os.environ.get(key)
    os.environ[key] = "1"
    try:
        return history_github_cache.install(runner.latest_history)
    finally:
        if prior is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prior


@contextmanager
def _current_shadow_runtime_reuse() -> Iterator[None]:
    """Mirror only reviewed exact-success computation reuse through Router."""

    with ExitStack() as stack:
        verification_hooks = verification_reuse.install(runner.latest_history)
        stack.callback(verification_reuse.restore, runner.latest_history, verification_hooks)

        builder_audit_hooks = builder_audit_reuse.install(runner.latest_history)
        stack.callback(builder_audit_reuse.restore, runner.latest_history, builder_audit_hooks)

        semantic_replay_hooks = semantic_replay_reuse.install(
            runner.latest_history.prefix.shadow
        )
        stack.callback(
            semantic_replay_reuse.restore,
            runner.latest_history.prefix.shadow,
            semantic_replay_hooks,
        )

        history_cache_hooks = _install_history_cache_with_worker_reuse()
        stack.callback(history_github_cache.restore, runner.latest_history, history_cache_hooks)

        validation_originals = all_market_cli._install_history_validation_reuse()
        stack.callback(_restore_history_validation, validation_originals)

        original_history_builder = summary_cli._install_captured_history_lineage_reuse()
        stack.callback(_restore_history_builder, original_history_builder)

        _tracked_history_builder, issued_histories = (
            all_market_cli._install_builder_issued_history_tracking()
        )

        original_research_xg = all_market_cli._install_builder_issued_history_xg_reuse(
            issued_histories
        )
        stack.callback(_restore_research_xg, original_research_xg)

        original_history_sha = summary_cli._install_builder_issued_history_summary_sha_reuse(
            issued_histories
        )
        stack.callback(_restore_history_sha, original_history_sha)

        price_originals = all_market_cli._install_price_context_verification_reuse()
        stack.callback(_restore_price_verification, price_originals)

        yield


@contextmanager
def _hosted_deadline() -> Iterator[None]:
    """Raise inside Python before the Actions hard ceiling so failure evidence survives."""

    if (
        PRE_CAPTURE_BUDGET_SECONDS
        + HOSTED_CAPTURE_TIMEOUT_SECONDS
        + ARTIFACT_UPLOAD_MARGIN_SECONDS
        != WORKFLOW_JOB_TIMEOUT_SECONDS
    ):
        raise RuntimeError("P3.0-E1 hosted runtime budget no longer closes exactly")
    if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
        raise RuntimeError("P3.0-E1 hosted deadline requires the reviewed Linux Actions runtime")

    def expire(_signum, _frame):
        raise P30HostedCaptureTimeoutError(
            "hosted P3.0-E1 capture exceeded the 90-minute bounded runtime"
        )

    prior_handler = signal.getsignal(signal.SIGALRM)
    prior_timer = signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, HOSTED_CAPTURE_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)
        if prior_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, prior_timer[0], prior_timer[1])


def main(argv: Sequence[str] | None = None) -> int:
    with _current_shadow_runtime_reuse():
        with _hosted_deadline():
            return collector.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
