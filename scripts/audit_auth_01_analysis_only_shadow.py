#!/usr/bin/env python3
"""Offline A5 proof of canonical SHADOW analysis with explicit no-delivery intent.

This audit is evidence-only. It consumes the retained P4.4R provider-event
fixture, supplies the already-reviewed synthetic reconciliation/history/model
seam, and executes the current source-controlled Price-all, Router, Portfolio,
adapter, service and wrapper owners. Only the operating-system supervisor and
external acquisition/transport boundaries are replaced inside this harness.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Mapping
import urllib.request


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

BASE_MAIN_SHA = "2b82f3236b786161d208d9ca3e4c8cf73ca9fac2"
POLICY_ID = "ATHENA_AUTH_01_ANALYSIS_ONLY_SHADOW_V1"
HISTORICAL_ARTIFACT_SHA256 = "7b09adb4882d49749c33efecbce0b1c8985a2d3bdec52417f7b02f8f335f4a86"
HISTORICAL_REPLAY_SHA256 = "3b792193ef813f4aab79d7c3f9d48550270f3ae008265cc9ceb9c3d629e974f5"
HISTORICAL_FALSE_REQUEST_SHA256 = "2206abcefa58a28b3ec162b8a735e20ee2b18203b832837c8da9cf2735a5b276"
HISTORICAL_TRUE_REQUEST_SHA256 = "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4"
ARTIFACT_PATH = Path("artifacts/architecture/auth_01_analysis_only_shadow_v1.json")
BASELINE_JSON = Path("artifacts/product/product_baseline_v1.json")
BASELINE_MARKDOWN = Path("docs/product/athena_product_baseline_v1.md")
BASELINE_JSON_BLOB = "a37c079b9175c1e24ac098b87fd6bc28e23e9527"
BASELINE_MARKDOWN_BLOB = "e20bd828d3b7a3d3305021492074be111d22c096"
P44R_RECEIPT_PATH = Path(
    "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json"
)
P44S_RECEIPT_PATH = Path(
    "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json"
)
P44R_RECEIPT_SHA256 = "90e2d7e984609ded80c9113a05453628bebadfcb3cede7fc95b9696931016552"
P44S_RECEIPT_SHA256 = "0907272a20b439e6874ee3b3fa399a488e8dd3c9a6e428dafa2aa53202c513c3"
P44R_FIXTURE_ROOT = Path("tests/fixtures/p4_4r_run_36285099805_quote_evidence")
P44R_FIXTURE_FILES = (
    "initial/event.raw.json",
    "initial/manifest.json",
    "fresh/event.raw.json",
    "fresh/manifest.json",
    "accepted-source/manifest.json",
    "accepted-source/page-001.raw.json",
)
EVENT_ID = "sr:match:66299604"
FIXTURE_ID = "FOTMOB:5071393"
KICKOFF = datetime(2026, 9, 27, 2, 30, tzinfo=timezone.utc)
INITIAL_OBSERVED = datetime(2026, 9, 27, 1, 19, 5, 661325, tzinfo=timezone.utc)
FRESH_OBSERVED = datetime(2026, 9, 27, 1, 55, 27, 176214, tzinfo=timezone.utc)
FIXTURE_CLASSIFICATION = (
    "REAL_RETAINED_PROVIDER_EVENT_BYTES_PLUS_SYNTHETIC_RECONCILIATION_HISTORY_MODEL"
)
IMPORT_MODULES = (
    "domain.run_contracts",
    "domain.execution_envelope",
    "services.athena_run_request_parser",
    "services.athena_run_workflow_request",
    "services.athena_run_service",
    "domain.current_shadow_run_contract_adapter",
    "domain.current_all_market_shadow_probability_settlement",
    "domain.current_shadow_sportybet_pc_upcoming_discovery",
    "domain.current_shadow_sportybet_pc_upcoming_reconciliation",
    "domain.current_sportybet_semantic_registry",
    "domain.sportybet_live_event_quote_evidence",
    "domain._current_shadow_quote_binding",
    "domain.current_shadow_all_market_price_all",
    "domain.current_shadow_all_market_router",
    "domain.current_shadow_all_market_portfolio",
    "domain.current_shadow_runtime_bindings",
    "domain.current_shadow_fresh_reprice_runtime",
    "domain.current_shadow_all_market_runner",
    "scripts.execute_current_shadow_all_market",
    "scripts.execute_current_shadow_all_market_summary_reuse",
    "scripts.execute_current_shadow_all_market_fresh_reprice",
    "scripts.execute_current_shadow_all_market_fresh_reprice_bound",
    "scripts.execute_current_shadow_daily",
    "scripts.execute_current_shadow_request",
    "runtime.worker_launcher",
    "runtime.worker_entry",
)


def _canonical(value: Any) -> bytes:
    """Use the exact architecture-receipt convention used by P4.4R/P4.4S."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    if type(value) is not dict:
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob(path: Path, *, root: Path = REPOSITORY_ROOT) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", f"HEAD:{path.as_posix()}"],
        text=True,
    ).strip()


def _load_modules(import_order: str) -> dict[str, Any]:
    if import_order not in {"forward", "reverse"}:
        raise ValueError("import order must be forward or reverse")
    names = IMPORT_MODULES if import_order == "forward" else tuple(reversed(IMPORT_MODULES))
    for name in names:
        importlib.import_module(name)
    return {name: sys.modules[name] for name in IMPORT_MODULES}


class _Patches:
    """Small reversible patch set kept private to this audit process."""

    def __init__(self) -> None:
        self._previous: list[tuple[Any, str, Any]] = []

    def set(self, owner: Any, name: str, value: Any) -> None:
        self._previous.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    def restore(self) -> None:
        for owner, name, previous in reversed(self._previous):
            setattr(owner, name, previous)
        self._previous.clear()


class HistoricalReplaySourceMoved(RuntimeError):
    """The frozen A5 replay cannot execute truthfully on a later runtime seam."""


def _current_worker_boundary_moved_paths(root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return the reviewed PORT-02B source paths that supersede the A5 launch seam."""

    service_path = root / "services/athena_run_service.py"
    launcher_path = root / "runtime/worker_launcher.py"
    entry_path = root / "runtime/worker_entry.py"
    if not (service_path.is_file() and launcher_path.is_file() and entry_path.is_file()):
        return []
    service_tree = ast.parse(service_path.read_text(encoding="utf-8"))
    helper = next(
        (
            node for node in service_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_reviewed_shadow_worker"
        ),
        None,
    )
    if helper is None:
        return []
    names = {node.id for node in ast.walk(helper) if isinstance(node, ast.Name)}
    if not {"WorkerCommand", "WorkerLauncher"}.issubset(names):
        return []
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if head == BASE_MAIN_SHA:
        return []
    return [
        "services/athena_run_service.py",
        "runtime/worker_launcher.py",
        "runtime/worker_entry.py",
    ]


def _assert_no_raw_share_material(value: Any, key_path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_no_raw_share_material(item, f"{key_path}.{key}" if key_path else str(key))
        return
    if type(value) in {list, tuple}:
        for item in value:
            _assert_no_raw_share_material(item, key_path)
        return
    if type(value) is str and re.search(r"https?://|sportybet\.com", value, re.IGNORECASE):
        raise AssertionError("A5 architecture artifact contains a share URL/domain")
    normalized_key = key_path.rsplit(".", 1)[-1].lower()
    if any(token in normalized_key for token in ("share_code", "share_url", "sharecode", "shareurl")):
        if normalized_key.endswith(("_copied", "_present")) and value is False:
            return
        if normalized_key.endswith("_calls") and type(value) is int and value == 0:
            return
        if value is not None and type(value) is not bool:
            raise AssertionError("A5 architecture artifact contains a raw share-code value")


def _validate_historical_artifact(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    artifact = _read_json(root / ARTIFACT_PATH)
    claimed = artifact.get("canonical_sha256")
    unsigned = dict(artifact)
    unsigned.pop("canonical_sha256", None)
    if claimed != HISTORICAL_ARTIFACT_SHA256 or _sha256(_canonical(unsigned)) != claimed:
        raise AssertionError("immutable A5 architecture artifact canonical identity changed")
    if artifact.get("policy_id") != POLICY_ID:
        raise AssertionError("immutable A5 policy identity changed")
    replay = artifact.get("offline_replay")
    if not isinstance(replay, dict):
        raise AssertionError("immutable A5 offline replay record is missing")
    exact_historical_values = {
        "deterministic_output_sha256": HISTORICAL_REPLAY_SHA256,
        "request_sha256": HISTORICAL_FALSE_REQUEST_SHA256,
    }
    for name, expected in exact_historical_values.items():
        if replay.get(name) != expected:
            raise AssertionError(f"immutable A5 historical value changed: {name}")
    request_vectors = replay.get("request_adapter_byte_equality")
    if not isinstance(request_vectors, dict):
        raise AssertionError("immutable A5 request vectors are missing")
    if request_vectors.get("false", {}).get("canonical_sha256") != HISTORICAL_FALSE_REQUEST_SHA256:
        raise AssertionError("immutable A5 false request identity changed")
    if request_vectors.get("true", {}).get("canonical_sha256") != HISTORICAL_TRUE_REQUEST_SHA256:
        raise AssertionError("immutable A5 true request identity changed")
    if _git_blob(BASELINE_JSON, root=root) != BASELINE_JSON_BLOB:
        raise AssertionError("BASE-00 frozen JSON blob changed")
    if _git_blob(BASELINE_MARKDOWN, root=root) != BASELINE_MARKDOWN_BLOB:
        raise AssertionError("BASE-00 frozen Markdown blob changed")
    for path, expected in (
        (P44R_RECEIPT_PATH, P44R_RECEIPT_SHA256),
        (P44S_RECEIPT_PATH, P44S_RECEIPT_SHA256),
    ):
        receipt = _read_json(root / path)
        receipt_claim = receipt.get("canonical_sha256")
        receipt_unsigned = dict(receipt)
        receipt_unsigned.pop("canonical_sha256", None)
        if receipt_claim != expected or _sha256(_canonical(receipt_unsigned)) != expected:
            raise AssertionError(f"immutable historical receipt identity changed: {path}")
    _assert_no_raw_share_material(artifact)
    return artifact


def _materialize_retained_fixture(root: Path) -> tuple[Path, dict[str, bytes]]:
    """Read exact committed fixture blobs and place them under a synthetic repo root."""

    fixture_root = root / "retained-p4-4r-fixture"
    blobs: dict[str, bytes] = {}
    for relative in P44R_FIXTURE_FILES:
        raw = subprocess.check_output(
            ["git", "-C", str(REPOSITORY_ROOT), "show", f"HEAD:{(P44R_FIXTURE_ROOT / relative).as_posix()}"]
        )
        blobs[relative] = raw
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    return fixture_root, blobs


def _offline_context_and_source(
    *, modules: Mapping[str, Any], repository_root: Path, fixture_root: Path,
    retained_blobs: Mapping[str, bytes], binding: Any, runner: Any,
    patches: _Patches,
) -> tuple[Any, dict[str, Any]]:
    """Create retained-event + synthetic-history source, then run real Price/Router."""

    prb = modules["domain.current_sportybet_semantic_registry"]
    live = modules["domain.sportybet_live_event_quote_evidence"]
    pc_source = modules["domain.current_shadow_sportybet_pc_upcoming_discovery"]
    pc_reconciliation = modules["domain.current_shadow_sportybet_pc_upcoming_reconciliation"]
    prc = modules["domain.current_all_market_shadow_probability_settlement"]
    quote_binding = modules["domain._current_shadow_quote_binding"]
    history_module = importlib.import_module("domain.current_fotmob_latest_durable_fresh_history")
    markets = importlib.import_module("domain.markets")

    evidence_root = repository_root / live.ALLOWED_OUTPUT_RELATIVE
    capture_dirs: dict[str, Path] = {}
    for sample, capture_id in (
        ("initial", "1aec7fa77430c1f7ab99b957"),
        ("fresh", "70e9dad393d0b396357753c2"),
    ):
        destination = evidence_root / capture_id
        destination.mkdir(parents=True, exist_ok=True)
        for suffix in ("event.raw.json", "manifest.json"):
            shutil.copyfile(fixture_root / sample / suffix, destination / suffix)
        capture_dirs[sample] = destination

    initial = prb.load_provider_event_evidence(
        capture_dirs["initial"],
        repository_root=repository_root,
        fixture_identity=EVENT_ID,
        fixture_identity_basis="PCUPCOMING_RUNTIME_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
    )
    fresh = prb.load_provider_event_evidence(
        capture_dirs["fresh"],
        repository_root=repository_root,
        fixture_identity=EVENT_ID,
        fixture_identity_basis="PCUPCOMING_RUNTIME_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
    )
    if (
        initial.inventory.observed_at != INITIAL_OBSERVED
        or fresh.inventory.observed_at != FRESH_OBSERVED
        or initial.inventory.event_id != EVENT_ID
        or fresh.inventory.event_id != EVENT_ID
        or initial.inventory.kickoff_utc != KICKOFF
        or fresh.inventory.kickoff_utc != KICKOFF
        or initial.inventory.home_team_name != "San Jose Earthquakes"
        or initial.inventory.away_team_name != "Portland Timbers"
    ):
        raise ValueError("retained provider-event fixture identity/time drifted")

    source_manifest_raw = retained_blobs["accepted-source/manifest.json"]
    source_page_raw = retained_blobs["accepted-source/page-001.raw.json"]
    source_manifest = json.loads(source_manifest_raw)
    first_page = source_manifest["pages"][0]
    if _sha256(source_manifest_raw) != "17436da36f2e39c3d041cb487160dffbf3a7c68115985ce83576b4e432cf2594":
        raise ValueError("retained accepted-source manifest SHA changed")
    if _sha256(source_page_raw) != first_page["raw_sha256"]:
        raise ValueError("retained accepted-source page digest mismatch")
    parsed_page = pc_source.parse_page(
        source_page_raw,
        page_num=first_page["page_num"],
        request_nonce_ms=first_page["request_nonce_ms"],
        observed_at=datetime.fromisoformat(first_page["observed_at"].replace("Z", "+00:00")),
    )
    source_event = next((event for event in parsed_page.events if event.event_id == EVENT_ID), None)
    if source_event is None or source_event.kickoff_utc != KICKOFF:
        raise ValueError("retained accepted-source page lacks exact fixture event")
    if source_manifest.get("pagination_complete") is not True or source_manifest.get("provider_total_num") != 692:
        raise ValueError("retained accepted-source page metadata is not complete/exact")

    row = SimpleNamespace(
        event_id=EVENT_ID,
        fixture_reconciliation_authorized=True,
        matched_fotmob_fixture_id="5071393",
        competition_name="MLS",
        home_team_name=initial.inventory.home_team_name,
        away_team_name=initial.inventory.away_team_name,
        kickoff_utc=initial.inventory.kickoff_utc,
        direct_event_observed_at=initial.inventory.observed_at,
        direct_event_manifest_sha256=initial.inventory.source_manifest_sha256,
        direct_event_inventory_sha256=initial.inventory.canonical_sha256,
        direct_event_raw_sha256=initial.inventory.source_raw_sha256,
    )
    reconciled = SimpleNamespace(
        rows=(row,),
        _detail_directories=((EVENT_ID, capture_dirs["initial"]),),
        _repository_root=repository_root,
        canonical_sha256="c" * 64,
        evaluation_time=INITIAL_OBSERVED,
        source_fotmob_admission_sha256="e" * 64,
        fotmob_capture_identities=(),
        _fixture_stable_identity_state_sha256=None,
        _fixture_stable_identity_state_snapshot={},
        to_dict=lambda: {"synthetic_fixture_reconciliation": True},
    )
    bundle = object.__new__(pc_reconciliation.CurrentShadowPcUpcomingReconciliationBundle)
    object.__setattr__(bundle, "_legacy_bundle", reconciled)
    object.__setattr__(bundle, "manifest", SimpleNamespace(canonical_sha256="f" * 64))
    object.__setattr__(bundle, "repository_root", repository_root)
    object.__setattr__(bundle, "stabilization_sha256", "d" * 64)
    patches.set(
        pc_reconciliation,
        "verify_current_event_discovery_reconciliation_bundle",
        lambda value: bundle if value is bundle else (_ for _ in ()).throw(
            AssertionError("unexpected reconciliation bundle")
        ),
    )

    # This input is explicitly synthetic; provider event/manifest/page bytes above
    # are the exact retained reviewed fixture bytes.
    history = object.__new__(history_module.CurrentLatestDurableFreshHistoryHandoff)
    research_xg = prc.ResearchXGRates(
        calibrated_home=2.0,
        calibrated_away=0.7,
        sealed_prediction_sha256="a" * 64,
        history_prefix_identity="b" * 64,
        source_fixture_identity=FIXTURE_ID,
    )
    scan = prc.scan_fixture_all_markets(
        fixture_identity=FIXTURE_ID,
        research_xg=research_xg,
        kickoff_utc_iso=KICKOFF.isoformat().replace("+00:00", "Z"),
        provider_semantic_by_market={market: "SUPPORTED" for market in markets.MarketId},
    )
    patches.set(prc, "scan_current_fixture_all_markets", lambda **_kwargs: scan)

    context = quote_binding.build_current_shadow_price_context_from_reconciliation(
        complete_current_history=history,
        fixture_identity=FIXTURE_ID,
        provider_event_id=EVENT_ID,
        current_reconciliation_bundle=bundle,
        runtime_bindings=binding,
    )
    checked_context = binding.verify_context(context)
    priced = runner.price_module.price_all_shadow_fixture(checked_context)
    decision = runner.router_module.route_shadow_price_results(priced)
    portfolio_input = runner.portfolio_module.build_shadow_portfolio_router_input(
        price_all_bundle=priced,
        router_decision=decision,
    )
    if decision.status.value != "SELECTED":
        raise ValueError("retained fixture did not pass the real Router selection owner")
    source_summary = {
        "fixture_evidence_classification": FIXTURE_CLASSIFICATION,
        "retained_detail_event_manifest_sha256": initial.inventory.source_manifest_sha256,
        "retained_detail_event_raw_sha256": initial.inventory.source_raw_sha256,
        "retained_fresh_event_manifest_sha256": fresh.inventory.source_manifest_sha256,
        "retained_fresh_event_raw_sha256": fresh.inventory.source_raw_sha256,
        "retained_accepted_source_manifest_sha256": _sha256(source_manifest_raw),
        "retained_accepted_source_page_sha256": _sha256(source_page_raw),
        "retained_source_page_event_count": len(parsed_page.events),
        "synthetic_reconciliation_history_model": True,
        "wager_placed": False,
    }
    source_bundle = runner.CurrentShadowRunnerSourceBundle(
        router_inputs=(portfolio_input,),
        reviewed_fixture_count=1,
        reconciled_fixture_count=1,
        provider_event_count=len(parsed_page.events),
        priced_fixture_count=1,
        router_selected_count=1,
        router_no_bet_count=0,
        source_summary=source_summary,
    )
    return source_bundle, {
        "context": checked_context,
        "price_all_bundle": priced,
        "router_decision": decision,
        "portfolio_input": portfolio_input,
        "fresh_evidence_directory": capture_dirs["fresh"],
        "initial_evidence_directory": capture_dirs["initial"],
        "source_manifest_raw": source_manifest_raw,
        "source_page_raw": source_page_raw,
    }


def _deny_counter(counters: dict[str, int], key: str):
    def deny(*_args: Any, **_kwargs: Any):
        counters[key] += 1
        raise AssertionError(f"A5 offline replay reached forbidden external operation: {key}")

    return deny


def _build_replay(
    import_order: str,
    *,
    exact_release_sha: str = BASE_MAIN_SHA,
) -> dict[str, Any]:
    counters = {
        "provider_network": 0,
        "share_transport": 0,
        "email": 0,
        "login": 0,
        "cookies": 0,
        "wallet": 0,
        "stake": 0,
        "wager": 0,
    }
    patches = _Patches()
    # Every external transport boundary fails immediately if reached.
    patches.set(socket.socket, "connect", _deny_counter(counters, "provider_network"))
    patches.set(socket.socket, "connect_ex", _deny_counter(counters, "provider_network"))
    patches.set(socket, "create_connection", _deny_counter(counters, "provider_network"))
    patches.set(urllib.request, "urlopen", _deny_counter(counters, "provider_network"))

    # Install the transport sentinels before importing any project/runtime
    # module, so import-time setup cannot silently escape this offline proof.
    modules = _load_modules(import_order)
    from domain.run_contracts import canonical_json_bytes

    envelope_module = modules["domain.execution_envelope"]
    parser = modules["services.athena_run_workflow_request"]
    service_module = modules["services.athena_run_service"]
    adapter = modules["domain.current_shadow_run_contract_adapter"]
    runner = modules["domain.current_shadow_all_market_runner"]
    request_cli = modules["scripts.execute_current_shadow_request"]
    fresh_cli = modules["scripts.execute_current_shadow_all_market_fresh_reprice"]
    fresh_runtime = modules["domain.current_shadow_fresh_reprice_runtime"]
    quote_binding = modules["domain._current_shadow_quote_binding"]
    binding_module = modules["domain.current_shadow_runtime_bindings"]
    worker_launcher = modules["runtime.worker_launcher"]
    worker_entry = modules["runtime.worker_entry"]

    live = modules["domain.sportybet_live_event_quote_evidence"]
    pc_source = modules["domain.current_shadow_sportybet_pc_upcoming_discovery"]
    patches.set(live, "capture_live_event_quote_evidence", _deny_counter(counters, "provider_network"))
    patches.set(pc_source, "_fetch_page", _deny_counter(counters, "provider_network"))
    patches.set(
        runner.current_fotmob_source,
        "issue_current_shadow_fotmob_reviewed_source",
        _deny_counter(counters, "provider_network"),
    )
    patches.set(
        runner.share_module,
        "create_verified_shadow_all_market_share_code",
        _deny_counter(counters, "share_transport"),
    )

    temp = tempfile.TemporaryDirectory(prefix="athena-auth01d-")
    created_capture_dirs: list[Path] = []
    evidence_module = modules["domain.sportybet_live_event_quote_evidence"]
    evidence_root = REPOSITORY_ROOT / evidence_module.ALLOWED_OUTPUT_RELATIVE
    evidence_root_was_present = evidence_root.exists()
    try:
        work_root = Path(temp.name)
        fixture_root, retained_blobs = _materialize_retained_fixture(work_root)
        for capture_id in ("1aec7fa77430c1f7ab99b957", "70e9dad393d0b396357753c2"):
            capture_dir = evidence_root / capture_id
            if capture_dir.exists():
                raise AssertionError(
                    "offline replay capture path already exists; refusing to overwrite user evidence"
                )
            capture_dir.mkdir(parents=True)
            created_capture_dirs.append(capture_dir)

        # Fixed source/clock identity matches the retained P4.4R observations and
        # keeps both clean-process executions identical.
        now = FRESH_OBSERVED
        patches.set(runner, "_now", lambda: now)
        patches.set(runner, "_git_head", lambda _root: exact_release_sha)
        patches.set(runner, "_expected_lineage_main_sha", lambda: exact_release_sha)
        binding = binding_module.fresh_reprice_current_shadow_runtime_bindings()
        patches.set(fresh_cli, "fresh_reprice_current_shadow_runtime_bindings", lambda: binding)

        source_holder: dict[str, Any] = {}

        def acquire_retained_source(**kwargs: Any):
            if kwargs.get("runtime_bindings") is not binding:
                raise AssertionError("offline source seam received a different runtime binding")
            source_bundle, source_parts = _offline_context_and_source(
                modules=modules,
                repository_root=REPOSITORY_ROOT,
                fixture_root=fixture_root,
                retained_blobs=retained_blobs,
                binding=binding,
                runner=runner,
                patches=patches,
            )
            source_holder.update(source_parts)
            stage_callback = kwargs.get("stage_callback")
            progress_callback = kwargs.get("progress_callback")
            if stage_callback is not None:
                stage_callback(runner.STAGE_PRICE_ALL_ROUTER)
            if progress_callback is not None:
                progress_callback(
                    runner.STAGE_PRICE_ALL_ROUTER,
                    "COMPLETED",
                    {
                        "reviewed_fixture_count": source_bundle.reviewed_fixture_count,
                        "reconciled_fixture_count": source_bundle.reconciled_fixture_count,
                        "provider_event_count": source_bundle.provider_event_count,
                        "priced_fixture_count": source_bundle.priced_fixture_count,
                        "router_selected_count": source_bundle.router_selected_count,
                        "router_no_bet_count": source_bundle.router_no_bet_count,
                    },
                    source_bundle.source_summary,
                )
            return source_bundle

        patches.set(runner, "_acquire_router_inputs", acquire_retained_source)

        original_refresh_selected_inputs = fresh_runtime.refresh_selected_inputs

        def refresh_from_retained_fixture(sources: Any, *, repository_root: Path, runtime_bindings: Any):
            return fresh_runtime._refresh_selected_inputs(
                sources,
                repository_root=repository_root,
                runtime_bindings=runtime_bindings,
                evidence_loader=lambda **_kwargs: source_holder["fresh_evidence_directory"],
            )

        patches.set(fresh_runtime, "refresh_selected_inputs", refresh_from_retained_fixture)

        request = parser.resolve_workflow_request(
            event_name="workflow_dispatch",
            dispatch_inputs={
                "days": "2026-09-27",
                "target_legs": "20",
                "target_total_odds": "",
                "bookie": "sportybet",
                "profile": "shadow",
                "create_share_code": "false",
            },
            now=now,
        )
        request_bytes = canonical_json_bytes(request)
        if request.authority_profile != "SHADOW" or request.mode != "research_shadow" or request.create_share_code is not False:
            raise AssertionError("canonical workflow resolver did not preserve explicit SHADOW no-delivery intent")
        manifest = service_module.AthenaRunService.authority_manifest_for(request)
        intent = envelope_module.RequestedOperationIntent(
            acquire_sources=True,
            create_share_code=False,
            place_wager=False,
        )
        envelope = envelope_module.ExecutionEnvelope.from_request_bytes(
            request_bytes=request_bytes,
            requested_operations=intent,
            authority_manifest=manifest,
            source_identity=envelope_module.SourceReleaseIdentity(
                kind="GIT_COMMIT", value=exact_release_sha
            ),
            date_resolution_policy_id=envelope_module.DATE_RESOLUTION_POLICY_ID,
            date_resolution_timezone_id=envelope_module.DATE_RESOLUTION_TIMEZONE_ID,
            clock_policy_id=envelope_module.PREVIEW_CLOCK_POLICY_ID,
            clock_observed_at=now,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        preview = envelope_module.evaluate_execution_envelope(envelope)
        if preview.blockers or preview.denied_operations:
            raise AssertionError("supported SHADOW no-delivery request was blocked by its V2 preview")

        # Replace only the lowest OS-process creation seam. The real service,
        # WorkerCommand validation, launcher admission, worker_entry validation,
        # request binding and Current Shadow parser/worker remain in the path.
        worker_commands: list[dict[str, Any]] = []
        worker_run_directory_bound: list[bool] = []
        child_commands: list[list[str]] = []
        child_parsed_intents: list[bool] = []
        supervisor_commands: list[list[str]] = []
        worker_entry_release_ids: list[str] = []
        child_stdout: list[str] = []
        real_request_main = request_cli.main

        def capture_request_main(argv: list[str] | None = None):
            exact_args = list(argv or [])
            child_commands.append(exact_args)
            parsed = request_cli.build_parser().parse_args(exact_args)
            if parsed.create_share_code is not False:
                raise AssertionError("worker_entry did not pass exact false intent to the real parser")
            child_parsed_intents.append(parsed.create_share_code)
            return real_request_main(argv)

        patches.set(request_cli, "main", capture_request_main)
        real_worker_entry_identity_check = worker_entry._verify_source_identity

        def capture_worker_entry_identity(command: Any, **kwargs: Any):
            identity = real_worker_entry_identity_check(command, **kwargs)
            if identity.identity_kind == "DEVELOPMENT_CHECKOUT":
                worker_entry_release_ids.append(identity.head_commit_sha)
            else:
                worker_entry_release_ids.append(identity.manifest_sha256)
            return identity

        patches.set(worker_entry, "_verify_source_identity", capture_worker_entry_identity)

        class _InProcessWorkerProcess:
            def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
                self.returncode = returncode
                self._stdout = stdout
                self._stderr = stderr
                self.pid = None

            def poll(self) -> int:
                return self.returncode

            def communicate(self):
                return self._stdout, self._stderr

        def offline_worker_spawn(argv: list[str], *, cwd: Path, shell: bool, **kwargs: Any):
            if shell is not False:
                raise AssertionError("reviewed worker launcher enabled shell execution")
            if type(argv) is not list or any(type(value) is not str for value in argv):
                raise AssertionError("reviewed worker launcher did not use an exact text argv list")
            if argv[:3] != [sys.executable, "-m", "runtime.worker_entry"]:
                raise AssertionError("development launcher did not select the reviewed worker entry")
            if set(argv[3::2]) != {"--command-file", "--development-root"}:
                raise AssertionError("development worker argv contains an unreviewed option")
            if cwd != REPOSITORY_ROOT:
                raise AssertionError("development worker cwd differs from the verified checkout root")
            if kwargs.get("stdout") != subprocess.PIPE or kwargs.get("stderr") != subprocess.PIPE:
                raise AssertionError("worker stdout/stderr are not captured")
            command_file_index = argv.index("--command-file")
            command_file = Path(argv[command_file_index + 1])
            worker_command = worker_launcher.WorkerCommand.from_json_bytes(command_file.read_bytes())
            worker_request = worker_launcher.read_bound_request(worker_command)
            current_identity = importlib.import_module("runtime.release_identity").verify_development_checkout(
                REPOSITORY_ROOT
            )
            if worker_command.operation != "CURRENT_SHADOW_REQUEST":
                raise AssertionError("worker command selected an unreviewed operation")
            if worker_command.mode != "research_shadow":
                raise AssertionError("worker command selected an unreviewed mode")
            if worker_command.request_artifact_id != request.canonical_sha256:
                raise AssertionError("worker command is not bound to the exact RunRequest")
            if worker_request != request:
                raise AssertionError("worker request artifact differs from the canonical request")
            if worker_command.envelope_artifact_id is not None:
                raise AssertionError("worker command fabricated an absent ExecutionEnvelope artifact")
            if (
                worker_command.release_identity_kind != "DEVELOPMENT_CHECKOUT"
                or worker_command.release_identity_id != current_identity.head_commit_sha
                or worker_command.release_identity_id != exact_release_sha
            ):
                raise AssertionError("worker command does not bind the exact current DevelopmentCheckout")
            command_payload = worker_command.to_dict()
            if "module" in command_payload or "function" in command_payload or "argv" in command_payload:
                raise AssertionError("WorkerCommand contains arbitrary dispatch or argv fields")
            worker_run_directory_bound.append(
                worker_command.run_directory.name == worker_command.request_artifact_id
            )
            command_payload["run_directory"] = "REQUEST_SHA_BOUND_RUN_DIRECTORY"
            worker_commands.append(command_payload)
            stdout = __import__("io").StringIO()
            stderr = __import__("io").StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                returncode = worker_entry.main(argv[3:])
            child_stdout.append(stdout.getvalue())
            return _InProcessWorkerProcess(returncode, stdout.getvalue(), stderr.getvalue())

        def offline_supervisor_child(command: list[str], *, env: dict[str, str], check: bool, timeout: float):
            supervisor_commands.append(list(command))
            if command[:3] != [sys.executable, "-m", request_cli.WORKER_MODULE]:
                raise AssertionError("Current Shadow supervisor invoked an unexpected worker command")
            if check is not False or timeout != request_cli.bound._supervisor_timeout_seconds():
                raise AssertionError("Current Shadow supervisor timeout/exit semantics changed")
            args = request_cli.build_parser().parse_args(command[3:])
            if args.create_share_code is not False or env.get(request_cli.WORKER_ENV) != "1":
                raise AssertionError("Current Shadow supervisor child lost explicit false intent")
            stdout = __import__("io").StringIO()
            stderr = __import__("io").StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                returncode = request_cli._execute_worker(args)
            if stdout.getvalue():
                print(stdout.getvalue(), end="")
            if stderr.getvalue():
                print(stderr.getvalue(), end="", file=sys.stderr)
            return SimpleNamespace(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())

        patches.set(worker_launcher, "_spawn_process", offline_worker_spawn)
        # The real worker_entry calls the existing supervisor normally. Replace
        # only that supervisor's OS child-process creation so the retained
        # _execute_worker and all reviewed offline Current Shadow owners run in
        # this process with the already-installed provider/delivery sentinels.
        patches.set(request_cli, "subprocess", SimpleNamespace(run=offline_supervisor_child))
        output_root = work_root / "canonical-service-output"
        service = service_module.AthenaRunService(
            _commit_sha_provider=lambda: exact_release_sha,
            _clock=lambda: now,
        )
        receipt = service.run(request, output_root=output_root)
        if len(worker_commands) != 1 or len(child_commands) != 1 or len(supervisor_commands) != 1:
            raise AssertionError("canonical SHADOW worker boundary was not executed exactly once")
        create_share_code_index = child_commands[0].index("--create-share-code")
        if child_commands[0][create_share_code_index + 1] != "false":
            raise AssertionError("worker_entry did not serialize exact false delivery intent")
        current_shadow_dir = output_root / request.canonical_sha256 / "current-shadow"
        policy_payload = _read_json(current_shadow_dir / request_cli.REQUEST_POLICY_FILENAME)
        inner_receipt = _read_json(current_shadow_dir / runner.RUN_RECEIPT_FILENAME)
        stage_payload = _read_json(current_shadow_dir / runner.RUN_STAGE_FILENAME)
        progress_payload = _read_json(current_shadow_dir / runner.RUN_PROGRESS_FILENAME)

        if receipt.status not in {
            runner.STATUS_PORTFOLIO_READY,
            runner.STATUS_PORTFOLIO_READY_WITH_SHORTFALL,
        }:
            raise AssertionError(f"no-delivery run did not reach a Portfolio-ready terminal: {receipt.status}")
        if inner_receipt.get("status") != receipt.status:
            raise AssertionError("service and Current Shadow terminal statuses differ")
        if policy_payload.get("create_share_code") is not False or inner_receipt.get("create_share_code") is not False:
            raise AssertionError("false delivery intent was not preserved in policy and inner receipt")
        if receipt.authority_manifest != manifest or receipt.authority_manifest.share_code_generation is not False:
            raise AssertionError("canonical service receipt authority differs from request-bound manifest")
        if receipt.share_code_result is not None or inner_receipt.get("share_code_receipt") is not None:
            raise AssertionError("no-delivery result contains share evidence")
        if inner_receipt.get("shareCode") is not None or inner_receipt.get("shareURL") is not None:
            raise AssertionError("no-delivery result contains a share code or URL")
        if inner_receipt.get("wager_placed") is not False:
            raise AssertionError("inner receipt wager invariant changed")

        portfolio_payload = inner_receipt.get("portfolio")
        if type(portfolio_payload) is not dict:
            raise AssertionError("Current Shadow receipt did not retain the real Portfolio result")
        portfolio_selected = portfolio_payload.get("selected_legs")
        if type(portfolio_selected) is not list or portfolio_selected != [dict(item) for item in receipt.selected_legs]:
            raise AssertionError("canonical adapter selected legs differ from Portfolio records/order")
        selected = len(portfolio_selected)
        target = request.target_legs
        shortfall = target - selected
        if (
            selected <= 0
            or inner_receipt.get("selected_leg_count") != selected
            or inner_receipt.get("shortfall") != shortfall
            or receipt.shortfall != shortfall
            or receipt.counts.get("shortfall") != shortfall
            or receipt.counts.get("target_legs") != target
        ):
            raise AssertionError("selected/target/shortfall counts are not truthful")
        reserve_count = len(portfolio_payload.get("reserve_legs", []))
        if inner_receipt.get("reserve_leg_count") != reserve_count:
            raise AssertionError("Portfolio reserve count differs from Current Shadow receipt")

        # Re-prove both explicit delivery intents by exact adapter byte equality.
        adapter_equality: dict[str, Any] = {}
        for create_share_code in (False, True):
            case_request = request if create_share_code is False else __import__("dataclasses").replace(
                request, create_share_code=True
            )
            policy_dir = work_root / ("policy-false" if not create_share_code else "policy-true")
            request_cli._write_request_policy(
                SimpleNamespace(
                    target_size=case_request.target_legs,
                    fixture_scope="today",
                    fixture_dates=tuple(day.strftime("%Y%m%d") for day in case_request.dates),
                    output_dir=policy_dir,
                    create_share_code=create_share_code,
                )
            )
            case_policy = _read_json(policy_dir / request_cli.REQUEST_POLICY_FILENAME)
            adapted_request = adapter.adapt_current_shadow_request(
                target_size=case_request.target_legs,
                request_policy=case_policy,
                resolved_dates=case_request.dates,
                expected_create_share_code=create_share_code,
            )
            original_bytes = canonical_json_bytes(case_request)
            adapted_bytes = canonical_json_bytes(adapted_request)
            if adapted_request.canonical_sha256 != case_request.canonical_sha256 or adapted_bytes != original_bytes:
                raise AssertionError("Current Shadow request adapter changed canonical V1 bytes")
            adapter_equality[str(create_share_code).lower()] = {
                "canonical_sha256": case_request.canonical_sha256,
                "bytes_equal": True,
            }

        if any(value != 0 for value in counters.values()):
            raise AssertionError(f"forbidden external operation counter is nonzero: {counters}")
        actual_stages = [
            {
                "stage": item.stage,
                "status": item.status,
                "observed_at": item.observed_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "counts": dict(item.counts),
            }
            for item in receipt.stages
        ]
        selected_identity = [
            {
                "fixture_identity": item.get("fixture_identity"),
                "provider_event_id": item.get("provider_event_id"),
            }
            for item in portfolio_selected
        ]
        result = {
            "schema_version": 1,
            "policy_id": "ATHENA_AUTH_01_OFFLINE_REPLAY_V1",
            "base_commit_sha": exact_release_sha,
            "request": {
                "authority_profile": request.authority_profile,
                "mode": request.mode,
                "bookie": request.bookie,
                "dates": [day.isoformat() for day in request.dates],
                "target_legs": target,
                "target_total_odds": None,
                "create_share_code": False,
                "place_wager": False,
                "canonical_sha256": request.canonical_sha256,
            },
            "envelope": {
                "policy_id": envelope_module.EXECUTION_ENVELOPE_POLICY_ID,
                "canonical_sha256": envelope.canonical_sha256,
                "requested_operations": intent.to_dict(),
                "preview": preview.to_dict(),
            },
            "authority_manifest": manifest.to_dict(),
            "adapter_request_byte_equality": adapter_equality,
            "current_shadow": {
                "status": receipt.status,
                "inner_receipt_canonical_sha256": _sha256(_canonical(inner_receipt)),
                "request_policy_delivery_intent": policy_payload["create_share_code"],
                "inner_delivery_intent": inner_receipt["create_share_code"],
                "service_child_create_share_code_argument": child_commands[0][create_share_code_index + 1],
                "stage_checkpoint": stage_payload.get("stage"),
                "progress_checkpoint": progress_payload.get("stage"),
                "share_stage_entered": False,
                "share_receipt_present": inner_receipt.get("share_code_receipt") is not None,
                "share_code_present": inner_receipt.get("shareCode") is not None,
                "share_url_present": inner_receipt.get("shareURL") is not None,
                "wager_placed": inner_receipt["wager_placed"],
                "portfolio_canonical_sha256": inner_receipt.get("portfolio_sha256"),
                "selected_leg_count": selected,
                "selected_leg_identity_order": selected_identity,
                "target_legs": target,
                "shortfall": shortfall,
                "reserve_leg_count": reserve_count,
                "runner_counts": {
                    name: inner_receipt[name]
                    for name in (
                        "reviewed_fixture_count", "reconciled_fixture_count",
                        "provider_event_count", "priced_fixture_count",
                        "router_selected_count", "router_no_bet_count",
                    )
                },
                "real_decision_owners_executed": [
                    "canonical_context_builder",
                    "source-controlled Price-all",
                    "source-controlled Router",
                    "fresh-reprice context builder",
                    "fresh-reprice Price-all",
                    "fresh-reprice Router",
                    "source-controlled Portfolio optimizer",
                    "current_shadow_run_contract_adapter",
                    "AthenaRunService production SHADOW supervisor",
                ],
                "fixture_evidence_classification": FIXTURE_CLASSIFICATION,
                "retained_fixture_sha256": {
                    relative: _sha256(raw) for relative, raw in sorted(retained_blobs.items())
                },
                "source_summary": dict(inner_receipt.get("source_summary", {})),
            },
            "canonical_run_receipt": {
                "exact_commit_sha": receipt.exact_commit_sha,
                "canonical_sha256": receipt.canonical_sha256,
                "canonical_bytes_sha256": _sha256(canonical_json_bytes(receipt)),
                "status": receipt.status,
                "wager_placed": receipt.wager_placed,
                "selected_leg_count": len(receipt.selected_legs),
                "counts": dict(receipt.counts),
                "stages": actual_stages,
            },
            "worker_boundary": {
                "command": worker_commands[0],
                "final_delivery_argument": ["--create-share-code", child_commands[0][create_share_code_index + 1]],
                "parsed_create_share_code": child_parsed_intents[0],
                "supervisor_child_create_share_code": False,
                "arbitrary_module": False,
                "arbitrary_function": False,
                "arbitrary_argv": False,
                "shell": False,
                "worker_entry_release_identity_id": worker_entry_release_ids[0],
                "run_receipt_exact_commit_sha": receipt.exact_commit_sha,
                "run_directory_bound_to_request_sha": worker_run_directory_bound[0],
                "current_head_sha": exact_release_sha,
            },
            "side_effects": dict(counters),
        }
        return result
    finally:
        patches.restore()
        for capture_dir in reversed(created_capture_dirs):
            shutil.rmtree(capture_dir)
        if not evidence_root_was_present and evidence_root.exists() and not any(evidence_root.iterdir()):
            evidence_root.rmdir()
        temp.cleanup()


def _workflow_and_contract_checks(root: Path = REPOSITORY_ROOT) -> None:
    workflow_source = (root / ".github/workflows/athena-run.yml").read_text(encoding="utf-8")
    if not re.search(
        r"(?ms)^      create_share_code:\n"
        r"        description: [^\n]*\n"
        r"        required: true\n"
        r"        default: \"false\"\n"
        r"        type: choice\n"
        r"        options:\n"
        r"          - \"false\"\n"
        r"          - \"true\"\n",
        workflow_source,
    ):
        raise AssertionError("canonical workflow delivery input is not the exact false/true choice")
    if "INPUT_CREATE_SHARE_CODE: ${{ inputs.create_share_code }}" not in workflow_source:
        raise AssertionError("canonical workflow does not hand off explicit delivery intent")
    if 'SCHEDULE_CREATE_SHARE_CODE = False' not in (root / "services/athena_run_workflow_request.py").read_text(encoding="utf-8"):
        raise AssertionError("scheduled workflow request is not no-delivery")

    parser_source = (root / "services/athena_run_request_parser.py").read_text(encoding="utf-8")
    parser_tree = ast.parse(parser_source)
    explicit = next(
        node for node in parser_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "parse_explicit_request"
    )
    names = [arg.arg for arg in explicit.args.kwonlyargs]
    if "create_share_code" not in names:
        raise AssertionError("canonical parser no longer accepts explicit delivery intent")
    index = names.index("create_share_code")
    if explicit.args.kw_defaults[index] is not None:
        raise AssertionError("canonical parser must require delivery intent without a default")
    profile_helper = next(
        node for node in parser_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_profile_fields"
    )
    if any(
        isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
        and any(
            isinstance(target, ast.Name) and target.id == "create_share_code"
            for target in (
                node.targets if isinstance(node, ast.Assign)
                else [node.target]
            )
        )
        for node in ast.walk(profile_helper)
    ):
        raise AssertionError("profile helper assigns delivery intent")
    if "SHORTHAND_LEGACY_CREATE_SHARE_CODE_DEFAULT = True" not in parser_source:
        raise AssertionError("explicit shorthand-only legacy intent default disappeared")

    resolver_source = (root / "services/athena_run_workflow_request.py").read_text(encoding="utf-8")
    if 'SCHEDULE_PROFILE = "main"' not in resolver_source or "SCHEDULE_CREATE_SHARE_CODE = False" not in resolver_source:
        raise AssertionError("schedule is not fixed to MAIN/no-delivery")
    if "_parse_create_share_code_text(values[\"create_share_code\"])" not in resolver_source:
        raise AssertionError("workflow resolver is not parsing its exact explicit delivery input")

    contract = importlib.import_module("domain.run_contracts")
    envelope = importlib.import_module("domain.execution_envelope")
    if contract.SCHEMA_VERSION != 1 or contract.POLICY_ID != "ATHENA_CANONICAL_RUN_CONTRACT_V1":
        raise AssertionError("RunRequest/RunReceipt V1 identity changed")
    if envelope.EXECUTION_ENVELOPE_SCHEMA_VERSION != 2 or envelope.EXECUTION_ENVELOPE_POLICY_ID != "ATHENA_EXECUTION_ENVELOPE_V2":
        raise AssertionError("AUTH-01A ExecutionEnvelope V2 identity changed")
    envelope_source = (root / "domain/execution_envelope.py").read_text(encoding="utf-8")
    if "intent.create_share_code is not request.create_share_code" not in envelope_source:
        raise AssertionError("V2 envelope no longer binds intent to RunRequest delivery")
    service_source = (root / "services/athena_run_service.py").read_text(encoding="utf-8")
    if "share_code = True, request.create_share_code" not in service_source:
        raise AssertionError("SHADOW delivery capability is no longer per-request")
    if re.search(r"getattr\([^\n]*create_share_code[^\n]*,\s*True\s*\)", parser_source + resolver_source + service_source):
        raise AssertionError("canonical authority contains a hidden delivery fallback")
    for path in (
        "services/athena_run_request_parser.py",
        "services/athena_run_workflow_request.py",
        "services/athena_run_service.py",
    ):
        source = (root / path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                if (
                    isinstance(node.value.value, ast.Name)
                    and node.value.value.id == "os"
                    and node.value.attr == "environ"
                ):
                    key = node.slice.value if isinstance(node.slice, ast.Constant) else None
                    if type(key) is str and "SHARE_CODE" in key.upper():
                        raise AssertionError("environment variable grants delivery authority")


def _historical_mismatch_corpus(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    baseline = _read_json(root / BASELINE_JSON)
    item = baseline["latest_live_evidence"]
    expected = {
        "run_id": 36345657852,
        "attempt": 1,
        "head_sha": "eae938a268707f07db3da2d551ea589782902b1c",
        "workflow_name": "ATHENA Canonical Run",
        "artifact_id": 10940728036,
        "artifact_name": "athena-run-36345657852",
        "artifact_sha256": "f0618654b49fcd7a6a2df95260025b6c655da5aefb477102696a812e9930b18a",
        "request_sha256": "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4",
        "run_receipt_sha256": "a8ce4f163432ebead90ee649c7297115acba0a852ceeac2beeb5ef0bdc0d4b6d",
        "inner_current_shadow_receipt_sha256": "80ce47a0965562cffd11d8dbd847740fbf57e36b8f1b173020827ea19a18b258",
        "source_manifest_canonical_sha256": "fb5412845dbed85d00396ea8f11a9343e1145dc4cba07664d54be69b260b449f",
        "stabilization_receipt_sha256": "a16860bd03f03a99087f030ed91474a57233ef3e619a36a20494c615bb15e1c7",
        "business_status": "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL",
        "classification": "POST_P4_4S_INTERNAL_SUCCESS_AUTHORIZATION_NONCOMPLIANT_SHARE_CODE_SIDE_EFFECT",
    }
    for key, value in expected.items():
        if item.get(key) != value:
            raise AssertionError(f"frozen BASE-00 historical evidence changed: {key}")
    if item["request"].get("create_share_code") is not True:
        raise AssertionError("historical mismatched request intent is no longer exact")
    if item["delivery"].get("owner_authorized_share_code_action") is not False:
        raise AssertionError("historical owner authorization is not the recorded false value")
    if item["delivery"].get("share_code_operation_attempted") is not True or item["delivery"].get("share_code_result_verified") is not True:
        raise AssertionError("historical unauthorized share-code side effect classification drifted")
    counts = item["counts"]
    if counts != {
        "priced_fixture_count": 3,
        "provider_event_count": 223,
        "reconciled_fixture_count": 3,
        "reserve_leg_count": 0,
        "reviewed_fixture_count": 3,
        "router_no_bet_count": 0,
        "router_selected_count": 3,
        "selected_leg_count": 3,
        "shortfall": 17,
        "target_legs": 20,
    }:
        raise AssertionError("frozen BASE-00 historical counts changed")
    return {
        **expected,
        "counts": dict(counts),
        "persisted_create_share_code": True,
        "owner_authorized_share_code_action": False,
        "share_code_operation_attempted": True,
        "share_code_result_verified": True,
        "login_cookies_wallet_staking_wager_place_wager_wager_placed": False,
        "raw_share_code_copied": False,
        "raw_share_url_copied": False,
        "interpretation": (
            "PRE_FIX_INTERNAL_ANALYSIS_REACHED_TERMINAL_RESULT_BUT_OWNER_PROHIBITED_DELIVERY; "
            "NOT_CLEAN_SUCCESSOR_PROOF; DOES_NOT_AUTHORIZE_MIGRATION_OR_RETIREMENT"
        ),
    }


def _capability_snapshot() -> list[dict[str, Any]]:
    return [
        {"capability_id": "CAP-RETAINED-OFFLINE-REPLAY", "state": "VERIFIED_AVAILABLE_OFFLINE"},
        {"capability_id": "CAP-SHADOW-ANALYSIS-NO-DELIVERY", "state": "OFFLINE_VERIFIED_NOT_LIVE_SUCCESSOR_PROOF"},
        {"capability_id": "CAP-SHADOW-DELIVERY-COMPATIBILITY", "state": "RETAINED_COMPATIBILITY_REQUIRES_EXPLICIT_INTENT_AND_SEPARATE_EXTERNAL_AUTHORIZATION"},
        {"capability_id": "CAP-SHADOW-PROVIDER-ACQUISITION", "state": "IMPLEMENTED_REVIEWED_CAPABILITY_NOT_EXERCISED_BY_A5"},
        {"capability_id": "CAP-MAIN-LIVE-ANALYSIS", "state": "BLOCKED_BY_AUTHORITY", "blocker": "MAIN_PHASE6_AUTHORITY_REQUIRED"},
        {"capability_id": "CAP-WAGER", "state": "NOT_AUTHORIZED"},
        {"capability_id": "CAP-CALLER-MIGRATION", "state": "NOT_AUTHORIZED"},
        {"capability_id": "CAP-WORKFLOW-RETIREMENT", "state": "NOT_AUTHORIZED"},
        {"capability_id": "CAP-CLEAN-LIVE-SUCCESSOR", "state": "NOT_RERUN_IN_A5"},
    ]


def _authority_matrix() -> list[dict[str, Any]]:
    return [
        {"profile": "MAIN", "create_share_code": False, "manifest_provider_acquisition": False, "manifest_share_code_generation": False, "admission": "ACCEPTED", "business_status": "MAIN_PHASE6_AUTHORITY_REQUIRED"},
        {"profile": "MAIN", "create_share_code": True, "manifest_provider_acquisition": False, "manifest_share_code_generation": False, "admission": "REQUEST_AUTHORITY_MISMATCH", "executor_invoked": False},
        {"profile": "SHADOW", "create_share_code": False, "manifest_provider_acquisition": True, "manifest_share_code_generation": False, "admission": "ACCEPTED", "delivery_result": None},
        {"profile": "SHADOW", "create_share_code": True, "manifest_provider_acquisition": True, "manifest_share_code_generation": True, "admission": "ACCEPTED", "real_delivery_exercised_by_a5": False},
        {"profile": "UNSUPPORTED", "create_share_code": False, "manifest_provider_acquisition": False, "manifest_share_code_generation": False, "admission": "EXECUTOR_UNAVAILABLE"},
        {"profile": "SHADOW", "place_wager": True, "admission": "CONTRACT_REJECTED"},
    ]


def _build_artifact(replay: Mapping[str, Any], replay_sha256: str) -> dict[str, Any]:
    corpus = _historical_mismatch_corpus()
    request = replay["request"]
    shadow = replay["current_shadow"]
    receipt = replay["canonical_run_receipt"]
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "implementation_base_main_sha": BASE_MAIN_SHA,
        "governing_contracts": {
            "RunRequest": {"schema_version": 1, "policy_id": "ATHENA_CANONICAL_RUN_CONTRACT_V1"},
            "RunReceipt": {"schema_version": 1, "policy_id": "ATHENA_CANONICAL_RUN_CONTRACT_V1"},
            "ExecutionEnvelope": {"schema_version": 2, "policy_id": "ATHENA_EXECUTION_ENVELOPE_V2"},
            "delivery_intent": "EXPLICIT_REQUEST_BOOL_INDEPENDENT_OF_PROFILE",
            "place_wager": False,
        },
        "historical_authorization_mismatch": corpus,
        "current_no_delivery_contract": {
            "authority_profile": "SHADOW",
            "mode": "research_shadow",
            "bookie": "sportybet",
            "create_share_code": False,
            "provider_acquisition_capability": True,
            "share_code_generation_capability": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "staking": False,
            "wager": False,
            "allowed_terminal_statuses": [
                "RESEARCH_SHADOW_PORTFOLIO_READY",
                "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL",
            ],
            "share_receipt_present": False,
            "share_code_present": False,
            "share_url_present": False,
            "SHARE_CODE_CREATE_RELOAD_reachable": False,
            "shortfall": shadow["shortfall"],
        },
        "offline_replay": {
            "fixture_evidence_classification": FIXTURE_CLASSIFICATION,
            "request_sha256": request["canonical_sha256"],
            "execution_envelope_sha256": replay["envelope"]["canonical_sha256"],
            "canonical_run_receipt_sha256": receipt["canonical_bytes_sha256"],
            "inner_current_shadow_receipt_sha256": shadow["inner_receipt_canonical_sha256"],
            "status": receipt["status"],
            "selected_leg_count": shadow["selected_leg_count"],
            "target_legs": shadow["target_legs"],
            "shortfall": shadow["shortfall"],
            "reserve_leg_count": shadow["reserve_leg_count"],
            "runner_counts": shadow["runner_counts"],
            "stage_summary": receipt["stages"],
            "decision_owners_executed": shadow["real_decision_owners_executed"],
            "provider_network_call_count": 0,
            "share_transport_call_count": 0,
            "email_login_cookies_wallet_stake_wager_call_count": 0,
            "clean_process_count": 2,
            "import_orders": ["forward", "reverse"],
            "canonical_output_bytes_identical": True,
            "deterministic_output_sha256": replay_sha256,
            "request_adapter_byte_equality": replay["adapter_request_byte_equality"],
        },
        "capability_snapshot": _capability_snapshot(),
        "authority_matrix": _authority_matrix(),
        "governance": {
            "master_issue": 337,
            "mandatory_reread_comment_id": 5881358508,
            "source_review_counter_while_unmerged": "0/5",
            "source_review_counter_if_merged": "1/5",
            "P4_4": "INCOMPLETE",
            "architecture_checkpoint_E": "INCOMPLETE",
            "clean_successor_proof": "INCOMPLETE",
            "live_proof": "NOT_AUTHORIZED",
            "caller_migration": "NOT_AUTHORIZED",
            "workflow_retirement": "NOT_AUTHORIZED",
            "clean_live_successor_proof": "NOT_RERUN_IN_A5",
        },
        "historical_sources": {
            "BASE00_json_git_blob_sha1": BASELINE_JSON_BLOB,
            "BASE00_markdown_git_blob_sha1": BASELINE_MARKDOWN_BLOB,
            "BASE00_files_rewritten": False,
            "P4_4R_receipt_sha256": P44R_RECEIPT_SHA256,
            "P4_4S_receipt_sha256": P44S_RECEIPT_SHA256,
            "historical_receipts_rewritten": False,
        },
        "safety": {
            "provider_network_calls": 0,
            "workflow_dispatches": 0,
            "share_code_create_reload_calls": 0,
            "email_sends": 0,
            "login": 0,
            "cookies": 0,
            "wallet": 0,
            "stake": 0,
            "wager": 0,
            "raw_share_code_or_url_copied": False,
        },
    }
    artifact["canonical_sha256"] = _sha256(_canonical(artifact))
    return artifact


def _clean_process_pair() -> tuple[dict[str, Any], bytes, bytes]:
    outputs: list[bytes] = []
    for order in ("forward", "reverse"):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--replay-json", "--import-order", order],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            timeout=600,
            env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)},
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"clean A5 replay process ({order}) failed: "
                + completed.stderr.decode("utf-8", errors="replace")
            )
        if completed.stderr:
            raise AssertionError(
                f"clean A5 replay process ({order}) wrote unexpected stderr: "
                + completed.stderr.decode("utf-8", errors="replace")
            )
        outputs.append(completed.stdout)
    if outputs[0] != outputs[1]:
        raise AssertionError("forward/reverse fresh-process replay bytes differ")
    replay = json.loads(outputs[0], object_pairs_hook=_strict_object)
    if _canonical(replay) != outputs[0]:
        raise AssertionError("fresh-process replay output is not canonical JSON")
    return replay, outputs[0], outputs[1]


def _git_commit_object_available(root: Path, commit_sha: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return completed.returncode == 0


def _verify_p44r_from_forward_evidence(
    root: Path,
    p44r: Any,
    p44s_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate P4.4R's immutable checkpoint without inventing shallow Git ancestry.

    P4.4S is specifically forward-compatible with shallow checkouts: it pins the
    P4.4R receipt and historical receipt inventory, and authenticates the source
    supersession. The workflow evolution ledger separately authenticates the
    current workflow and supplies P4.4M's immutable after-bytes.
    """

    receipt = p44r._read_json(root, p44r.RECEIPT_PATH)
    p44r.verify_receipt(receipt)
    receipt_sha = p44r._verify_self_hash(receipt, "P4.4R receipt")
    inventory = p44r._read_json(root, p44r.INVENTORY_PATH)
    inventory_sha = p44r._verify_self_hash(inventory, "P4.4R composition inventory")
    if receipt.get("composition_inventory_sha256") != inventory_sha:
        raise AssertionError("P4.4R receipt does not bind the exact composition inventory")

    p44r._verify_fixture_files(root)
    p44r._verify_runtime_composition(root)
    verifier_sha = _sha256(
        (root / "domain/_current_shadow_quote_binding.py")
        .read_bytes()
        .replace(b"\r\n", b"\n")
    )
    p44r.verify_context_verifier_source_supersession(root, receipt, verifier_sha)

    evolution = importlib.import_module("scripts.audit_p4_workflow_evolution_ledger")
    try:
        ledger = evolution.validate_current_state()
        historical_workflow = evolution.resolve_reviewed_transition_after_source(
            ".github/workflows/athena-run.yml",
            "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1",
        )
    except Exception as exc:
        raise AssertionError("P4.4R historical workflow/current evolution evidence is unavailable") from exc
    workflow_contract = receipt["before_after_contracts"]["canonical_workflow"]
    historical_workflow_sha = _sha256(historical_workflow.replace(b"\r\n", b"\n"))
    if not (
        historical_workflow_sha == workflow_contract.get("base_main_git_blob_sha256")
        == workflow_contract.get("after_git_blob_sha256")
        and workflow_contract.get("unchanged") is True
    ):
        raise AssertionError("P4.4R historical workflow identity does not match reviewed evolution ancestry")
    if (
        ledger.get("current_live_workflow_count") != 39
        or ledger.get("current_p4_3_retired_workflow_count") != 3
    ):
        raise AssertionError("current workflow/retirement counts differ from the P4.4R checkpoint")
    expected_receipt_count = receipt.get("historical_receipt_immutability", {}).get(
        "compared_receipt_count"
    )
    if (
        p44s_result.get("historical_p4_4r_receipt_sha256") != receipt_sha
        or p44s_result.get("p4_4r_historical_receipt_count") != expected_receipt_count
    ):
        raise AssertionError("P4.4S forward evidence does not bind P4.4R receipt/history exactly")
    return {
        "result": "PASS_VIA_P4_4S_FORWARD_EVIDENCE",
        "receipt_sha256": receipt_sha,
        "inventory_sha256": inventory_sha,
        "historical_workflow_sha256": historical_workflow_sha,
        "current_workflow_tree_sha1": ledger["current_workflow_tree_sha1"],
    }


def _run_architecture_audits(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    p44r = importlib.import_module("scripts.audit_p4_4r_shadow_runtime_composition_stabilization")
    p44s = importlib.import_module("scripts.audit_p4_4s_canonical_adapter_bound_context_builder")
    p44s_result = p44s.audit(root)
    if not isinstance(p44s_result, dict):
        raise AssertionError("P4.4R/P4.4S audits returned unexpected results")
    if _git_commit_object_available(root, p44r.BASE_MAIN_SHA):
        p44r_result = p44r.audit(root)
        if not isinstance(p44r_result, dict):
            raise AssertionError("P4.4R audit returned an unexpected result")
        p44r_summary = {"result": "PASS", "receipt_sha256": P44R_RECEIPT_SHA256}
    else:
        p44r_summary = _verify_p44r_from_forward_evidence(root, p44r, p44s_result)
    return {
        "P4_4R": p44r_summary,
        "P4_4S": {"result": "PASS", "receipt_sha256": P44S_RECEIPT_SHA256},
    }


def check_artifact(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    if root.resolve() != REPOSITORY_ROOT.resolve():
        raise ValueError("A5 audit must run at the repository root")
    artifact = _validate_historical_artifact(root)
    moved_paths = _current_worker_boundary_moved_paths(root)
    if moved_paths:
        return {
            "result": "SKIP_SOURCE_MOVED",
            "policy_id": POLICY_ID,
            "artifact_canonical_sha256": HISTORICAL_ARTIFACT_SHA256,
            "historical_integrity": "PASS",
            "historical_replay_sha256": HISTORICAL_REPLAY_SHA256,
            "historical_replay_reexecuted": False,
            "reason": "CURRENT_WORKER_BOUNDARY_REQUIRES_VERIFIED_CURRENT_RELEASE_IDENTITY",
            "moved_paths": moved_paths,
        }

    _workflow_and_contract_checks(root)
    audits = _run_architecture_audits(root)
    replay, forward, reverse = _clean_process_pair()
    output_sha = _sha256(forward)
    expected = _build_artifact(replay, output_sha)
    if artifact != expected:
        raise AssertionError("committed A5 artifact differs from recomputed historical source evidence")
    if forward != reverse:
        raise AssertionError("clean-process replay bytes differ")
    return {
        "result": "PASS",
        "policy_id": POLICY_ID,
        "artifact_canonical_sha256": HISTORICAL_ARTIFACT_SHA256,
        "replay_sha256": output_sha,
        "historical_integrity": "PASS",
        "historical_replay_reexecuted": True,
        "clean_process_count": 2,
        "P4_4R_P4_4S": audits,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--replay-json", action="store_true")
    parser.add_argument("--print-artifact", action="store_true")
    parser.add_argument("--import-order", choices=("forward", "reverse"), default="forward")
    args = parser.parse_args(argv)
    if sum((args.check, args.replay_json, args.print_artifact)) != 1:
        parser.error("select exactly one of --check, --replay-json, or --print-artifact")
    try:
        if args.replay_json:
            if _current_worker_boundary_moved_paths():
                raise HistoricalReplaySourceMoved(
                    "AUTH_01D_HISTORICAL_REPLAY_SOURCE_MOVED: current PORT-02B worker identity "
                    "cannot truthfully execute the historical BASE_MAIN_SHA replay"
                )
            sys.stdout.buffer.write(_canonical(_build_replay(args.import_order)))
            return 0
        if args.print_artifact:
            if _current_worker_boundary_moved_paths():
                raise HistoricalReplaySourceMoved(
                    "AUTH_01D_HISTORICAL_REPLAY_SOURCE_MOVED: refusing to print a new v1 artifact "
                    "from later source"
                )
            replay, forward, reverse = _clean_process_pair()
            if forward != reverse:
                raise AssertionError("forward/reverse A5 replay output differs")
            artifact = _build_artifact(replay, _sha256(forward))
            sys.stdout.write(json.dumps(artifact, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n")
            return 0
        result = check_artifact()
    except HistoricalReplaySourceMoved as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"AUTH-01D audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
