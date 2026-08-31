#!/usr/bin/env python3
"""Execute one source-bound current ATHENA all-market Shadow request."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from domain import _all_market_shadow_current_binding as current_binding
from domain import _current_shadow_quote_binding as quote_binding
from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as catalog_reconciliation
from domain import current_shadow_sportybet_upcoming_reconciliation as upcoming_reconciliation
from domain import sportybet_current_event_discovery_reconciliation as pr251_reconciliation

WORKER_ENV = "ATHENA_CURRENT_SHADOW_ALL_MARKET_WORKER"
HOSTED_SUPERVISOR_TIMEOUT_SECONDS = 50 * 60
PRICE_DIAGNOSTIC_FILENAME = "current-shadow-price-stage-diagnostic.json"
PRICE_DIAGNOSTIC_STAGES = frozenset({
    "CONTEXT_BUILD_STARTED",
    "CONTEXT_BUILD_COMPLETED",
    "PRICE_ALL_STARTED",
    "PRICE_ALL_COMPLETED",
    "ROUTER_STARTED",
    "ROUTER_COMPLETED",
    "PORTFOLIO_INPUT_STARTED",
    "PORTFOLIO_INPUT_COMPLETED",
})

# Live PR-F evidence demonstrated that the reviewed current source chain can
# legitimately consume ~20 minutes before Price-all/Router starts. Keep the
# supervisor bounded and fail-closed, but give the exact source-bound chain
# enough time to finish instead of timing out solely because of hosted runtime.
runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS = HOSTED_SUPERVISOR_TIMEOUT_SECONDS


class _PortfolioReconciliationFacade:
    """Mirror the exact current-reconciliation dispatch already used by PR-D.

    PR-E predates PR-F's reviewed upcoming/catalog reconciliation wrappers and
    imports only the original PR251 verifier. The retained PR-D context can now
    legitimately hold any one of those three exact reviewed bundle types. This
    facade changes no reconciliation semantics: it dispatches only by exact type
    to the corresponding reviewed verifier and preserves each verifier's native
    fail-closed error.
    """

    SportyBetCurrentEventDiscoveryError = (
        pr251_reconciliation.SportyBetCurrentEventDiscoveryError,
        upcoming_reconciliation.CurrentShadowSportyBetUpcomingReconciliationError,
        catalog_reconciliation.CurrentShadowSportyBetCatalogFanoutReconciliationError,
    )

    @staticmethod
    def verify_current_event_discovery_reconciliation_bundle(value):
        if type(value) is pr251_reconciliation.SportyBetCurrentEventDiscoveryReconciliationBundle:
            verifier = pr251_reconciliation.verify_current_event_discovery_reconciliation_bundle
        elif type(value) is upcoming_reconciliation.CurrentShadowSportyBetUpcomingReconciliationBundle:
            verifier = upcoming_reconciliation.verify_current_event_discovery_reconciliation_bundle
        elif type(value) is catalog_reconciliation.CurrentShadowSportyBetCatalogFanoutReconciliationBundle:
            verifier = catalog_reconciliation.verify_current_event_discovery_reconciliation_bundle
        else:
            raise pr251_reconciliation.SportyBetCurrentEventDiscoveryError(
                "value must be an exact reviewed current reconciliation bundle"
            )
        return verifier(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=int, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-all-market"),
    )
    return parser


def _lineage_reads_cache_key(expected_main_sha, reads):
    """Return an exact immutable in-process identity for captured GitHub reads."""

    if type(expected_main_sha) is not str or type(reads) is not tuple:
        return None
    rows = []
    for item in reads:
        if type(item) is not runner.latest_history.GitHubReadSnapshot:
            return None
        rows.append((item.key, item.payload_kind, item.succeeded, item.payload))
    return expected_main_sha, tuple(rows)


def _lineage_evidence_cache_key(evidence):
    if type(evidence) is not runner.latest_history.GitHubActionsLineageEvidenceBundle:
        return None
    reads_key = _lineage_reads_cache_key(evidence.expected_main_sha, evidence.reads)
    if reads_key is None:
        return None
    return reads_key, evidence.audit_result_bytes


def _install_history_validation_reuse():
    """Reuse only successful exact PR151/history validation inside one worker.

    Run #29 proved that provider/FotMob acquisition finished early while repeated
    immutable PR151 evidence and durable-prefix revalidation consumed nearly the
    whole fixed supervisor budget. The underlying dataclasses intentionally
    revalidate on ``dataclasses.replace``; PR-F creates several such copies while
    building one already-reviewed history object.

    Preserve the first exact replay for each immutable identity, cache only after
    it succeeds, and let every surrounding constructor continue its structural,
    type, SHA, timestamp and authority checks. Different GitHub reads, different
    evidence bytes, or a different current-source object cannot share a result.
    """

    original_replay = runner.latest_history._replay_audit_from_evidence
    original_success_materials = runner.latest_history._success_materials
    original_derive = runner.latest_history.prefix._derive

    replay_by_reads: dict[object, tuple[bytes, frozenset[str]]] = {}
    success_by_evidence: dict[object, object] = {}
    derive_by_source: dict[object, tuple[tuple[object, ...], object]] = {}

    def replay(*, expected_main_sha, reads):
        key = _lineage_reads_cache_key(expected_main_sha, reads)
        if key is not None:
            cached = replay_by_reads.get(key)
            if cached is not None:
                replay_raw, used = cached
                return (
                    runner.latest_history._parse_object(
                        replay_raw, "cached captured Actions lineage audit"
                    ),
                    set(used),
                )

        result, used = original_replay(
            expected_main_sha=expected_main_sha,
            reads=reads,
        )
        if key is not None:
            replay_by_reads[key] = (
                runner.latest_history._canonical(result),
                frozenset(used),
            )
        return result, used

    def success_materials(evidence):
        key = _lineage_evidence_cache_key(evidence)
        if key is not None:
            cached = success_by_evidence.get(key)
            if cached is not None:
                return cached

        result = original_success_materials(evidence)
        if key is not None:
            success_by_evidence[key] = result
        return result

    def derive(source):
        if (
            type(source)
            is not runner.latest_history.prefix.CurrentDurableFreshHistoryPrefixSourceBundle
        ):
            return original_derive(source)

        key = (
            id(source.current_bootstrap),
            id(source.source_manifest),
            id(source.source_raw_json),
            id(source.legacy_bootstrap_projection_raw),
            source.workflow_run_id,
            source.artifact_name,
            id(source.artifact_zip_bytes),
            source.artifact_zip_metadata_digest,
        )
        cached = derive_by_source.get(key)
        if cached is not None:
            refs, value = cached
            if (
                refs[0] is source.current_bootstrap
                and refs[1] is source.source_manifest
                and refs[2] is source.source_raw_json
                and refs[3] is source.legacy_bootstrap_projection_raw
                and refs[4] is source.artifact_zip_bytes
            ):
                return value

        value = original_derive(source)
        derive_by_source[key] = (
            (
                source.current_bootstrap,
                source.source_manifest,
                source.source_raw_json,
                source.legacy_bootstrap_projection_raw,
                source.artifact_zip_bytes,
            ),
            value,
        )
        return value

    runner.latest_history._replay_audit_from_evidence = replay
    runner.latest_history._success_materials = success_materials
    runner.latest_history.prefix._derive = derive
    return original_replay, original_success_materials, original_derive


def _install_history_lineage_reuse():
    """Reuse one exact reviewed PR151 GitHub snapshot across this worker run.

    Main already records every GitHub read needed to replay the PR151 lineage
    audit. PR-F's three-date horizon must not perform that same remote audit once
    per matched date. The first history build remains the reviewed live issuer;
    later date-specific prefixes replay only from its immutable captured evidence.
    """

    original = runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff
    evidence_by_main: dict[str, object] = {}

    def build(**kwargs):
        expected_main_sha = kwargs.get("expected_main_sha")
        evidence = evidence_by_main.get(expected_main_sha)
        if evidence is None:
            history = original(**kwargs)
            captured = history.source_bundle.github_evidence
            if captured.expected_main_sha != expected_main_sha:
                raise runner.CurrentShadowAllMarketRunnerError(
                    "captured PR151 lineage evidence main identity drifted"
                )
            evidence_by_main[expected_main_sha] = captured
            return history

        return runner.latest_history._build_with_readers(
            current_bootstrap=kwargs["current_bootstrap"],
            source_raw_json=kwargs["source_raw_json"],
            source_manifest=kwargs["source_manifest"],
            legacy_bootstrap_projection_raw=kwargs["legacy_bootstrap_projection_raw"],
            expected_main_sha=kwargs["expected_main_sha"],
            get_main_ref=lambda: evidence.json("main_ref"),
            get_runs_page=lambda page, per_page: evidence.json(
                f"runs:{page}:{per_page}"
            ),
            get_run_by_id=lambda run_id: evidence.json(f"run:{run_id}"),
            get_run_artifacts=lambda run_id: evidence.json(f"artifacts:{run_id}"),
            download_artifact_zip=lambda artifact_id: evidence.binary(
                f"artifact_zip:{artifact_id}"
            ),
            get_release=lambda tag: evidence.json(f"release:{tag}"),
            download_release_asset=lambda asset_id: evidence.binary(
                f"release_asset:{asset_id}"
            ),
            get_run_jobs=lambda run_id: evidence.json(f"jobs:{run_id}"),
            repository_root=kwargs.get("repository_root"),
        )

    runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = build
    return original


def _install_builder_issued_history_tracking():
    """Track only exact history objects issued by the reviewed builder in this worker."""

    original = runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff
    issued_by_identity: dict[int, object] = {}

    def build(**kwargs):
        history = original(**kwargs)
        issued_by_identity[id(history)] = history
        return history

    runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = build
    return original, issued_by_identity


def _install_builder_issued_history_xg_reuse(issued_by_identity: dict[int, object]):
    """Reuse main-style verified history only for same-worker builder outputs.

    The public PR-C boundary must replay arbitrary caller-supplied histories.
    PR-F does not accept such a history: it builds the exact PR151 handoff itself
    immediately before pricing. Main's current field-trial boundary already
    verifies a complete history once and then consumes its verified shadow row.
    Mirror that pattern narrowly here: only the exact object returned by the
    reviewed builder in this worker may skip a second deep PR151 replay. Unknown
    objects fall back to PR-C's original exact replay unchanged.

    The canonical history SHA is still derived from the exact reviewed canonical
    JSON vocabulary and the fixture row/sealed prediction are still revalidated
    by PR-C's private validated-history extractor on every fixture.
    """

    original = quote_binding.prc._research_xg_from_complete_current_history
    sha_by_identity: dict[int, tuple[object, str]] = {}

    def research(complete_current_history, fixture_identity):
        issued = issued_by_identity.get(id(complete_current_history))
        if issued is not complete_current_history:
            return original(complete_current_history, fixture_identity)
        if (
            type(complete_current_history)
            is not runner.latest_history.CurrentLatestDurableFreshHistoryHandoff
        ):
            return original(complete_current_history, fixture_identity)

        cached = sha_by_identity.get(id(complete_current_history))
        if cached is not None and cached[0] is complete_current_history:
            history_sha = cached[1]
        else:
            try:
                canonical = runner.latest_history._canonical(
                    complete_current_history.to_dict()
                )
            except Exception as exc:
                raise runner.CurrentShadowAllMarketRunnerError(
                    "builder-issued PR151 history canonicalization failed"
                ) from exc
            history_sha = hashlib.sha256(canonical).hexdigest()
            sha_by_identity[id(complete_current_history)] = (
                complete_current_history,
                history_sha,
            )

        return current_binding._research_xg_from_validated_current_history(
            complete_current_history,
            fixture_identity,
            history_sha=history_sha,
        )

    quote_binding.prc._research_xg_from_complete_current_history = research
    return original


def _install_price_context_verification_reuse():
    """Memoize one exact source replay per immutable Shadow price context.

    The public Price-all boundary verifies a freshly builder-issued context and
    exact-quote issuance verifies that same immutable context again. Run #25
    proved that repeating the full PR151/PR-C replay for the same canonical
    context across eight reconciled fixtures can exhaust the bounded live-run
    budget. Preserve the first exact verification unchanged, then reuse only its
    verified result for the same canonical SHA-256 during this worker process.
    """

    original_price_verify = runner.price_module.verify_current_shadow_price_context
    original_quote_verify = quote_binding.verify_current_shadow_price_context
    verified_by_identity: dict[str, object] = {}

    def verify(value):
        identity = value.canonical_sha256
        cached = verified_by_identity.get(identity)
        if cached is not None:
            return cached

        checked = original_quote_verify(value)
        if checked.canonical_sha256 != identity:
            raise runner.CurrentShadowAllMarketRunnerError(
                "verified Shadow price context identity drifted"
            )
        verified_by_identity[identity] = checked
        return checked

    runner.price_module.verify_current_shadow_price_context = verify
    quote_binding.verify_current_shadow_price_context = verify
    return original_price_verify, original_quote_verify


def _install_portfolio_reconciliation_dispatch():
    """Let PR-E replay exactly the reviewed reconciliation type retained by PR-D."""

    original = runner.portfolio_module.reconciliation
    runner.portfolio_module.reconciliation = _PortfolioReconciliationFacade
    return original


def _install_price_stage_diagnostics(output_dir: Path):
    """Persist the exact in-flight operation inside PRICE_ALL_ROUTER.

    This is evidence-only instrumentation. It does not change source admission,
    pricing, routing, portfolio policy, timeouts, or authority. A supervisor
    timeout leaves the last started/completed operation durable in the artifact.
    """

    original_context = runner.price_module.build_current_shadow_price_context_from_reconciliation
    original_price_all = runner.price_module.price_all_shadow_fixture
    original_router = runner.router_module.route_shadow_price_results
    original_portfolio_input = runner.portfolio_module.build_shadow_portfolio_router_input
    fixture_index_by_identity: dict[tuple[str, str], int] = {}
    next_fixture_index = 0

    def write(
        stage: str,
        *,
        fixture_index: int,
        fixture_identity: str | None,
        provider_event_id: str | None,
    ) -> None:
        if stage not in PRICE_DIAGNOSTIC_STAGES:
            raise runner.CurrentShadowAllMarketRunnerError(
                "price diagnostic stage escaped reviewed vocabulary"
            )
        runner._write(
            output_dir / PRICE_DIAGNOSTIC_FILENAME,
            {
                "schema_version": runner.SCHEMA_VERSION,
                "dataset_name": runner.DATASET_NAME,
                "stage": stage,
                "fixture_index": fixture_index,
                "fixture_identity": fixture_identity,
                "provider_event_id": provider_event_id,
                "observed_at": runner._now().isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z"),
                "wager_placed": False,
            },
        )

    def identity(value) -> tuple[str | None, str | None]:
        return (
            getattr(value, "fixture_identity", None),
            getattr(value, "provider_event_id", None),
        )

    def fixture_index(fixture_identity: str | None, provider_event_id: str | None) -> int:
        key = (fixture_identity or "", provider_event_id or "")
        return fixture_index_by_identity.get(key, 0)

    def build_context(*args, **kwargs):
        nonlocal next_fixture_index
        fixture_identity = kwargs.get("fixture_identity")
        provider_event_id = kwargs.get("provider_event_id")
        next_fixture_index += 1
        index = next_fixture_index
        fixture_index_by_identity[(fixture_identity or "", provider_event_id or "")] = index
        write(
            "CONTEXT_BUILD_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_context(*args, **kwargs)
        write(
            "CONTEXT_BUILD_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    def price_all(context, *args, **kwargs):
        fixture_identity, provider_event_id = identity(context)
        index = fixture_index(fixture_identity, provider_event_id)
        write(
            "PRICE_ALL_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_price_all(context, *args, **kwargs)
        write(
            "PRICE_ALL_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    def route(bundle, *args, **kwargs):
        context = getattr(bundle, "_context", None)
        fixture_identity, provider_event_id = identity(context)
        index = fixture_index(fixture_identity, provider_event_id)
        write(
            "ROUTER_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_router(bundle, *args, **kwargs)
        write(
            "ROUTER_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    def build_portfolio_input(*args, **kwargs):
        bundle = kwargs.get("price_all_bundle")
        if bundle is None and args:
            bundle = args[0]
        context = getattr(bundle, "_context", None)
        fixture_identity, provider_event_id = identity(context)
        index = fixture_index(fixture_identity, provider_event_id)
        write(
            "PORTFOLIO_INPUT_STARTED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        value = original_portfolio_input(*args, **kwargs)
        write(
            "PORTFOLIO_INPUT_COMPLETED",
            fixture_index=index,
            fixture_identity=fixture_identity,
            provider_event_id=provider_event_id,
        )
        return value

    runner.price_module.build_current_shadow_price_context_from_reconciliation = build_context
    runner.price_module.price_all_shadow_fixture = price_all
    runner.router_module.route_shadow_price_results = route
    runner.portfolio_module.build_shadow_portfolio_router_input = build_portfolio_input
    return original_context, original_price_all, original_router, original_portfolio_input


def _execute_once(args: argparse.Namespace) -> int:
    (
        original_history_replay,
        original_success_materials,
        original_prefix_derive,
    ) = _install_history_validation_reuse()
    original_history_builder = _install_history_lineage_reuse()
    _tracked_history_builder, issued_histories = _install_builder_issued_history_tracking()
    original_research_xg = _install_builder_issued_history_xg_reuse(issued_histories)
    original_price_verify, original_quote_verify = _install_price_context_verification_reuse()
    original_portfolio_reconciliation = _install_portfolio_reconciliation_dispatch()
    (
        original_context,
        original_price_all,
        original_router,
        original_portfolio_input,
    ) = _install_price_stage_diagnostics(args.output_dir)
    try:
        result = runner.execute_current_shadow_all_market(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
    finally:
        runner.price_module.build_current_shadow_price_context_from_reconciliation = original_context
        runner.price_module.price_all_shadow_fixture = original_price_all
        runner.router_module.route_shadow_price_results = original_router
        runner.portfolio_module.build_shadow_portfolio_router_input = original_portfolio_input
        runner.portfolio_module.reconciliation = original_portfolio_reconciliation
        runner.price_module.verify_current_shadow_price_context = original_price_verify
        quote_binding.verify_current_shadow_price_context = original_quote_verify
        quote_binding.prc._research_xg_from_complete_current_history = original_research_xg
        runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = (
            original_history_builder
        )
        runner.latest_history._replay_audit_from_evidence = original_history_replay
        runner.latest_history._success_materials = original_success_materials
        runner.latest_history.prefix._derive = original_prefix_derive
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if os.environ.get(WORKER_ENV) == "1":
        return _execute_once(args)

    env = dict(os.environ)
    env[WORKER_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        "scripts.execute_current_shadow_all_market",
        "--target-size",
        str(args.target_size),
        "--output-dir",
        str(args.output_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            env=env,
            check=False,
            timeout=runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        result = runner.write_current_shadow_timeout_receipt(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
