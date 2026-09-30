"""Qualification-only retained-source composition; never an application API.

Real source verification and business owners, with an explicitly non-authoritative
retained-diagnostic mathematical scan. No complete current-history proof is made.
Only the dedicated PORT-02C qualifier imports this module.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import socket
import tempfile
from types import SimpleNamespace
import urllib.request

FIXTURE_PREFIX = "tests/fixtures/port_02c_run_36345657852"
STAGED_FIXTURE_ROOT = "retained"
FIXTURE_MANIFEST_SHA256 = "2fa98f3b43a48e752c05a5b3cce9bce307eddedef5eebf6cadd9dc04ee706372"
TIME_POLICY_ID = "ATHENA_PORT02C_EARLIEST_COMPLETE_RETAINED_SOURCE_EVALUATION_V1"
REPLAY_SCOPE = "RETAINED_SOURCE_DIRECT_FRESH_PRICE_ROUTER_PORTFOLIO_QUALIFICATION"
QUALIFICATION_SHA = "ca520f8067e23b2a583ce348f22309e8752610aa5e1b0551c778d9272aed9e5a"
HISTORICAL_SHA = "3879c81646f2d3385462824d3477bceaeb4b5e1ed09369ee41a59539f638040d"
SOURCE_HEAD = "eae938a268707f07db3da2d551ea589782902b1c"
ZIP_SHA = "f0618654b49fcd7a6a2df95260025b6c655da5aefb477102696a812e9930b18a"
ISSUED_AT = "2026-09-27T19:48:45.724323Z"
FIXTURE = "FOTMOB:5071387"
EVENT = "sr:match:66299608"
INITIAL_CAPTURES = {
    EVENT: "67bc5018a9120bc4364660e2",
    "sr:match:73220748": "bfd0436fa1158f84ef29e11a",
    "sr:match:74297872": "8ccaefb7b700d21e401de851",
}
FRESH_CAPTURE = "8225412daedb5c9a4e1e38f0"
MODULE_ORDER = (
    "domain.current_all_market_shadow_probability_settlement",
    "domain._current_shadow_quote_binding",
    "domain.current_shadow_runtime_bindings",
    "domain.current_shadow_all_market_price_all",
    "domain.current_shadow_all_market_router",
    "domain.current_shadow_all_market_portfolio",
    "domain.current_shadow_fresh_reprice_runtime",
    "domain.current_shadow_sportybet_pc_upcoming_discovery",
    "domain.current_shadow_sportybet_pc_upcoming_reconciliation",
    "scripts.issue_current_fotmob_reviewed_source",
)


class ReplayError(ValueError):
    """Qualification input or replay failed closed."""


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_fixture_manifest(root: Path) -> dict:
    raw = (root / "fixture-manifest.json").read_bytes()
    if sha(raw) != FIXTURE_MANIFEST_SHA256:
        raise ReplayError("retained fixture manifest identity mismatch")
    manifest = json.loads(raw)
    if raw != canonical(manifest):
        raise ReplayError("fixture manifest is not canonical")
    expected = {"fixture-manifest.json"}
    for record in manifest["files"]:
        relative = PurePosixPath(record["staged_path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) in expected:
            raise ReplayError("fixture member path or uniqueness invalid")
        expected.add(str(relative))
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ReplayError(f"missing/nonregular fixture member: {relative}")
        payload = path.read_bytes()
        if len(payload) != record["byte_size"] or sha(payload) != record["byte_sha256"]:
            raise ReplayError(f"retained member identity mismatch: {relative}")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != expected or any(p.is_symlink() for p in root.rglob("*")):
        raise ReplayError("retained corpus has unexpected/missing members")
    return manifest


def derive_initial_evaluation_time(*, issuance: datetime, discovery: object,
                                   initial_manifests: dict) -> datetime:
    from domain import sportybet_live_event_quote_evidence as live

    if set(initial_manifests) != set(INITIAL_CAPTURES):
        raise ReplayError("initial source set is incomplete")
    times = [issuance, discovery.last_observed_at]
    for event, manifest in initial_manifests.items():
        if manifest.event_id != event or live.capture_identifier(manifest) != INITIAL_CAPTURES[event]:
            raise ReplayError("initial/fresh semantic role mismatch")
        times.append(manifest.observed_at)
    result = max(times)
    if result.isoformat() != "2026-09-27T19:48:52.628430+00:00":
        raise ReplayError("earliest-complete initial-source time drifted")
    return result


@contextmanager
def network_guard():
    """Transport-denial instrumentation only; no verifier is substituted."""
    from domain import sportybet_live_event_quote_evidence as live
    from domain import current_shadow_sportybet_pc_upcoming_discovery as discovery
    counters = {"network_attempts": 0, "provider_acquisition_calls": 0, "delivery_calls": 0}
    def deny_network(*args, **kwargs):
        counters["network_attempts"] += 1
        raise ReplayError("qualification forbids outbound transport")
    def deny_provider(*args, **kwargs):
        counters["provider_acquisition_calls"] += 1
        raise ReplayError("qualification forbids provider acquisition")
    targets = [(socket.socket, "connect", deny_network),
               (socket.socket, "connect_ex", deny_network),
               (socket, "create_connection", deny_network),
               (urllib.request, "urlopen", deny_network),
               (live, "capture_live_event_quote_evidence", deny_provider),
               (discovery, "_fetch_page", deny_provider)]
    saved = [(owner, name, getattr(owner, name)) for owner, name, _ in targets]
    try:
        for owner, name, replacement in targets:
            setattr(owner, name, replacement)
        yield counters
    finally:
        for owner, name, original in reversed(saved):
            setattr(owner, name, original)


def replay_retained_source_reconciliation(fixture_root: Path, replay_root: Path):
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as pc
    from domain import sportybet_live_event_quote_evidence as live
    from domain.fotmob_data_matches_capture import verify_data_matches_capture_directory
    from domain.current_fotmob_fixture_review_policy import canonical_current_fotmob_fixture_review_policy_result_bytes
    from domain.fotmob_fixture_catalog_handoff import sha256_fotmob_fixture_catalog_handoff
    from scripts.issue_current_fotmob_reviewed_source import build_verified_current_shadow_fotmob_bootstrap_from_capture

    manifest = verify_fixture_manifest(fixture_root)
    for record in manifest["files"]:
        relative = record["staged_path"]
        if relative.startswith("source-evidence/"):
            destination = replay_root / ".cache/athena-research" / relative[len("source-evidence/"):]
        else:
            destination = replay_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((fixture_root / relative).read_bytes())
    state = replay_root / "identity-state/current-shadow-fixture-identity-v2-state.json"
    os.environ["ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH"] = str(state)
    fot_root = replay_root / ".cache/athena-research/fotmob-data-matches-captures"
    fot_dir = fot_root / "20260927/489d099652cf679e603dab76"
    capture_manifest = verify_data_matches_capture_directory(
        fot_dir, allowed_root=fot_root, require_network_acquisition_performed=True)
    execution = build_verified_current_shadow_fotmob_bootstrap_from_capture(
        fot_dir, issued_at=datetime.fromisoformat(ISSUED_AT.replace("Z", "+00:00")),
        repository_root=replay_root,
        code_state={"evidence_git_head_sha": SOURCE_HEAD, "tracked_worktree_clean": True})
    identities = {
        "policy_result_sha256": sha(canonical_current_fotmob_fixture_review_policy_result_bytes(execution.policy_result)),
        "handoff_sha256": sha256_fotmob_fixture_catalog_handoff(execution.handoff),
        "bootstrap_sha256": execution.verified_bootstrap.bootstrap_sha256,
        "verified_bootstrap_receipt_sha256": sha(execution.verified_bootstrap_receipt_bytes),
    }
    if identities != {
        "policy_result_sha256": "228956b87e7796e471203e9afe9b6dac2001fcd809b04cd2849257045c162145",
        "handoff_sha256": "c1258d3ee4a5fff6c69b49b0387dddcc17b0b80bd07145cd1c5279450a6e3135",
        "bootstrap_sha256": "d5b296e01f98023c4cab7aae646950bd29dbc712afd9e4f54dbb89a657174228",
        "verified_bootstrap_receipt_sha256": "2bfc9a561f623f518b7f18fcf3dec301d02d9b36cebc861155254c9837db9115",
    }:
        raise ReplayError("historical FotMob reconstruction identity mismatch")
    discovery = pc.verify_current_pc_upcoming_discovery(repository_root=replay_root)
    pc.verify_runtime_capture_stabilization(repository_root=replay_root)
    captures = pc.reviewed._materialize_fotmob_captures(((
        (fot_dir / "response.json").read_bytes(), capture_manifest),))
    admission = pc.reviewed._rederive_exact_fotmob_admission(
        execution.bootstrap.verified_artifact.admission, captures)
    details = {event: replay_root / live.ALLOWED_OUTPUT_RELATIVE / cid
               for event, cid in INITIAL_CAPTURES.items()}
    initial = {event: live.verify_live_event_quote_evidence(path, repository_root=replay_root)
               for event, path in details.items()}
    evaluation = derive_initial_evaluation_time(
        issuance=execution.issued_at, discovery=discovery, initial_manifests=initial)
    built = pc._build(repository_root=replay_root, manifest=discovery, admission=admission,
                      captures=captures, execute_live_network=False,
                      retained_details=details, evaluation_time=evaluation)
    checked = pc.verify_current_pc_upcoming_reconciliation_bundle(built)
    if canonical(checked.to_dict()) != canonical(built.to_dict()) or checked.canonical_sha256 != QUALIFICATION_SHA:
        raise ReplayError("qualification reconciliation identity differs on exact replay")
    counts = dict(Counter(r.disposition.value for r in checked.rows))
    if counts != {"DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE": 46,
                  "NO_EXACT_REVIEWED_FOTMOB_MATCH": 174,
                  "UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED": 3}:
        raise ReplayError("qualification reconciliation dispositions drifted")
    if sorted((r.event_id, r.matched_fotmob_fixture_id) for r in checked.matched_rows) != [
        (EVENT, "5071387"), ("sr:match:73220748", "5991880"), ("sr:match:74297872", "6280211")]:
        raise ReplayError("qualification reconciled fixture set drifted")
    return checked, identities


@contextmanager
def qualification_model_scan(replay_root: Path, reconciliation):
    from domain import current_all_market_shadow_probability_settlement as prc
    from domain.current_fotmob_latest_durable_fresh_history import CurrentLatestDurableFreshHistoryHandoff
    raw = (replay_root / "model-diagnostic/current-shadow-current-asof-xg-diagnostic.json").read_bytes()
    diagnostic = json.loads(raw)
    row = next(r for r in diagnostic["fixtures"] if r["fixture_identity"] == FIXTURE)
    rates = row["model_rates"]
    if rates != {
        "calibrated_home": 1.4986253114732324, "calibrated_away": 1.2486505221506203,
        "completeness_status": "CURRENT_AS_OF_RESEARCH_XG_ELO_ONLY_COMPLETE",
        "feature_projection_identity": "d2d3af35949a487b6b7731f440059e87abf8dc8344657f32deb95c7c751402f5",
        "history_prefix_identity": "954e14368f573e83993f1e30f29315a0368eee6b493f2c71c682ccd31409c98f",
        "source_fixture_identity": FIXTURE,
    }:
        raise ReplayError("retained qualification diagnostic drifted")
    original = prc.scan_current_fixture_all_markets
    def scan(*, complete_current_history, fixture_identity, provider_semantic_registry=None):
        if complete_current_history is not sentinel or fixture_identity != FIXTURE:
            raise ReplayError("qualification scan is limited to its opaque sentinel and fixture")
        registry = prc._verified_provider_registry(provider_semantic_registry)
        statuses, totals, handicaps = prc._provider_inputs(registry)
        kickoff = next(r.kickoff_utc for r in reconciliation.matched_rows if r.event_id == EVENT)
        return prc.scan_fixture_all_markets(
            fixture_identity=FIXTURE, research_xg=prc.ResearchXGRates(**rates),
            kickoff_utc_iso=kickoff.isoformat().replace("+00:00", "Z"),
            total_goals_lines=totals, asian_handicap_home_lines=handicaps,
            provider_semantic_by_market=statuses)
    try:
        prc.scan_current_fixture_all_markets = scan
        # Qualification-only exact-type opaque sentinel. No history member is read.
        sentinel = object.__new__(CurrentLatestDurableFreshHistoryHandoff)
        yield sentinel, sha(raw)
    finally:
        prc.scan_current_fixture_all_markets = original


def run_replay(*, fixture_root: Path, writable_root: Path, variant: str = "standard") -> dict:
    if variant not in {"standard", "reverse-import", "caches-disabled"}:
        raise ReplayError("unknown replay variant")
    for module in reversed(MODULE_ORDER) if variant == "reverse-import" else MODULE_ORDER:
        importlib.import_module(module)
    from domain import _current_shadow_quote_binding as qb
    from domain import current_shadow_runtime_bindings as bindings
    from domain import current_shadow_all_market_portfolio as portfolio
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as pc
    from domain import sportybet_live_event_quote_evidence as live
    from domain.current_shadow_fresh_reprice_runtime import _refresh_selected_inputs
    from domain._current_shadow_price_core import ShadowRouterDecisionStatus
    verify_fixture_manifest(fixture_root)
    writable_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="port02c-replay-", dir=writable_root))
    old_state = os.environ.get("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH")
    protected = (pc.verify_current_pc_upcoming_reconciliation_bundle,
                 pc.verify_current_event_discovery_reconciliation_bundle,
                 live.verify_live_event_quote_evidence, qb.verify_current_shadow_price_context,
                 bindings.CurrentShadowRuntimeBindings.verify_context)
    expected_verifiers = (
        (pc.__name__, "verify_current_pc_upcoming_reconciliation_bundle"),
        (pc.__name__, "verify_current_event_discovery_reconciliation_bundle"),
        (live.__name__, "verify_live_event_quote_evidence"),
        (qb.__name__, "verify_current_shadow_price_context"),
        (bindings.__name__, "verify_context"),
    )
    if any((getattr(fn, "__module__", None), getattr(fn, "__name__", None)) != expected
           for fn, expected in zip(protected, expected_verifiers, strict=True)):
        raise ReplayError("canonical verifier substitution detected at entry")
    try:
        with network_guard() as counters:
            checked, fotmob = replay_retained_source_reconciliation(fixture_root, root)
            with qualification_model_scan(root, checked) as (history, diagnostic_sha):
                direct_binding = bindings.default_current_shadow_runtime_bindings()
                context = qb.build_current_shadow_price_context_from_reconciliation(
                    complete_current_history=history, fixture_identity=FIXTURE,
                    provider_event_id=EVENT, current_reconciliation_bundle=checked,
                    runtime_bindings=direct_binding)
                direct_binding.verify_context(context)
                priced = direct_binding.price_all(context)
                routed = direct_binding.route(priced)
                if routed.status is not ShadowRouterDecisionStatus.SELECTED:
                    raise ReplayError("focused direct Router did not select retained fixture")
                sources = SimpleNamespace(
                    router_inputs=(SimpleNamespace(price_all_bundle=priced,
                        router_decision=routed),),
                    reviewed_fixture_count=1, reconciled_fixture_count=1,
                    provider_event_count=223, priced_fixture_count=1,
                    router_selected_count=1, router_no_bet_count=0,
                    source_summary={"qualification_harness_selection": True})
                def loader(*, event_id, repository_root):
                    if event_id != EVENT or repository_root != root:
                        raise ReplayError("fresh retained loader event/root mismatch")
                    return root / live.ALLOWED_OUTPUT_RELATIVE / FRESH_CAPTURE
                fresh_binding = bindings.fresh_reprice_current_shadow_runtime_bindings()
                refreshed = _refresh_selected_inputs(sources, repository_root=root,
                    runtime_bindings=fresh_binding, evidence_loader=loader)
                item = refreshed.router_inputs[0]
                fresh = item.price_all_bundle._context
                fresh_binding.verify_context(fresh)
                if fresh.evaluation_time.isoformat() != "2026-09-27T20:04:20.651079+00:00":
                    raise ReplayError("fresh clock differs from exact retained observation")
                portfolio.verify_shadow_portfolio_router_input(item)
                optimized = fresh_binding.optimize_portfolio(refreshed.router_inputs,
                    target_size=20, evaluation_time=fresh.evaluation_time)
                portfolio.verify_shadow_portfolio_optimization(optimized)
                payload = {
                    "replay_scope": REPLAY_SCOPE, "source_run_id": 36345657852,
                    "source_artifact_id": 10940728036, "source_artifact_zip_sha256": ZIP_SHA,
                    "qualification_evaluation_time_policy_id": TIME_POLICY_ID,
                    "qualification_initial_evaluation_time": context.to_dict()["evaluation_time"],
                    "qualification_reconciliation_sha256": checked.canonical_sha256,
                    "source_reconciliation_contract_sha256": checked.contract_sha256,
                    "historical_run_reconciliation_sha256": HISTORICAL_SHA,
                    "historical_evaluation_time_retained": False,
                    "historical_reconciliation_sha_reproduction_required": False,
                    "fotmob": fotmob, "fixture_identity": FIXTURE, "provider_event_id": EVENT,
                    "direct_context": context.to_dict(), "direct_context_sha256": context.canonical_sha256,
                    "direct_price_all_sha256": priced.canonical_sha256,
                    "direct_router_sha256": routed.decision_sha256, "direct_router_status": routed.status.value,
                    "fresh_context": fresh.to_dict(), "fresh_context_sha256": fresh.canonical_sha256,
                    "fresh_price_all_sha256": item.price_all_bundle.canonical_sha256,
                    "fresh_router_sha256": item.router_decision.decision_sha256,
                    "fresh_router_status": item.router_decision.status.value,
                    "portfolio_input_sha256": sha(portfolio._canonical(item.to_dict())),
                    "portfolio_result_sha256": optimized.canonical_sha256,
                    "target_size": optimized.requested_target_size,
                    "selected_count": len(optimized.selected_legs), "shortfall": optimized.shortfall,
                    "retained_model_diagnostic_sha256": diagnostic_sha,
                    "model_history_input_mode": "PORT02C_RETAINED_DIAGNOSTIC_QUALIFICATION_ONLY",
                    "complete_current_history_reconstructed": False,
                    "production_model_authority": False, "production_probability_authority": False,
                    "source_reconciliation_verifier_mode": "CANONICAL_UNPATCHED",
                    "provider_event_verifier_mode": "CANONICAL_UNPATCHED",
                    "runtime_binding_verifier_mode": "CANONICAL_UNPATCHED",
                    **counters, "wager": False,
                }
            if any(counters.values()):
                raise ReplayError("qualification safety counter is nonzero")
            if protected != (pc.verify_current_pc_upcoming_reconciliation_bundle,
                pc.verify_current_event_discovery_reconciliation_bundle,
                live.verify_live_event_quote_evidence, qb.verify_current_shadow_price_context,
                bindings.CurrentShadowRuntimeBindings.verify_context):
                raise ReplayError("canonical verifier substitution detected")
            return payload
    finally:
        if old_state is None:
            os.environ.pop("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH", None)
        else:
            os.environ["ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH"] = old_state
