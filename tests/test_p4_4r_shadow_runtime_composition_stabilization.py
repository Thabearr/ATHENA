from __future__ import annotations

import ast
import shutil
import socket
import urllib.request
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from domain import current_all_market_shadow_probability_settlement as prc
from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_all_market_router as router_module
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as pc_upcoming
from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_source
from domain import current_sportybet_semantic_registry as prb
from domain import sportybet_live_event_quote_evidence as live
from domain._current_shadow_price_core import (
    ShadowPriceError,
    ShadowRouterDecisionStatus,
)
from domain._current_shadow_quote_binding import (
    CURRENT_RECONCILIATION_DIRECT,
    CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID,
    build_current_shadow_price_context_from_reconciliation,
)
from domain.current_shadow_runtime_bindings import fresh_reprice_current_shadow_runtime_bindings
from domain.current_shadow_fresh_reprice_runtime import _refresh_selected_inputs
from domain.current_fotmob_latest_durable_fresh_history import (
    CurrentLatestDurableFreshHistoryHandoff,
)
from domain.markets import MarketId


UTC = timezone.utc
EVENT_ID = "sr:match:66299604"
FIXTURE_ID = "FOTMOB:5071393"
BASE_MAIN_SHA = "47326a934aabe34052c804a6941a702e52710b12"
PRE_FIX_QUOTE_BINDING_SHA256 = "7f793abebe899c0a05eaf50a56dce6b97a5cb866039993d1e793a39bc97813c1"
KICKOFF = datetime(2026, 9, 27, 2, 30, tzinfo=UTC)
INITIAL_OBSERVED = datetime(2026, 9, 27, 1, 19, 5, 661325, tzinfo=UTC)
FRESH_OBSERVED = datetime(2026, 9, 27, 1, 55, 27, 176214, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "p4_4r_run_36285099805_quote_evidence"
NETWORK_ATTEMPTS: list[str] = []


def _deny_network(*_args, **_kwargs):
    NETWORK_ATTEMPTS.append("socket/http")
    raise AssertionError("offline P4.4R replay attempted an outbound network operation")


def _install_network_sentinel(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(urllib.request, "urlopen", _deny_network)
    monkeypatch.setattr(live, "capture_live_event_quote_evidence", _deny_network)
    monkeypatch.setattr(pc_source, "_fetch_page", _deny_network)


def _copy_evidence(repo_root: Path, monkeypatch):
    evidence_root = repo_root / live.ALLOWED_OUTPUT_RELATIVE
    paths = {}
    for sample, capture_id in (
        ("initial", "1aec7fa77430c1f7ab99b957"),
        ("fresh", "70e9dad393d0b396357753c2"),
    ):
        destination = evidence_root / capture_id
        destination.mkdir(parents=True)
        shutil.copyfile(FIXTURE_ROOT / sample / "event.raw.json", destination / "event.raw.json")
        shutil.copyfile(FIXTURE_ROOT / sample / "manifest.json", destination / "manifest.json")
        paths[sample] = destination
    return paths


def _offline_composition(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths = _copy_evidence(repo_root, monkeypatch)
    initial = prb.load_provider_event_evidence(
        paths["initial"],
        repository_root=repo_root,
        fixture_identity=EVENT_ID,
        fixture_identity_basis="PCUPCOMING_RUNTIME_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
    )
    fresh = prb.load_provider_event_evidence(
        paths["fresh"],
        repository_root=repo_root,
        fixture_identity=EVENT_ID,
        fixture_identity_basis="PCUPCOMING_RUNTIME_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
    )
    assert initial.inventory.observed_at == INITIAL_OBSERVED
    assert fresh.inventory.observed_at == FRESH_OBSERVED
    assert initial.inventory.event_id == fresh.inventory.event_id == EVENT_ID
    assert initial.inventory.home_team_name == fresh.inventory.home_team_name == "San Jose Earthquakes"
    assert initial.inventory.away_team_name == fresh.inventory.away_team_name == "Portland Timbers"
    assert initial.inventory.kickoff_utc == fresh.inventory.kickoff_utc == KICKOFF

    source_manifest_bytes = (FIXTURE_ROOT / "accepted-source" / "manifest.json").read_bytes()
    source_page_bytes = (FIXTURE_ROOT / "accepted-source" / "page-001.raw.json").read_bytes()
    source_manifest = json.loads(source_manifest_bytes)
    first_page = source_manifest["pages"][0]
    assert hashlib.sha256(source_manifest_bytes).hexdigest() == (
        "17436da36f2e39c3d041cb487160dffbf3a7c68115985ce83576b4e432cf2594"
    )
    assert hashlib.sha256(source_page_bytes).hexdigest() == first_page["raw_sha256"]
    parsed_page = pc_source.parse_page(
        source_page_bytes,
        page_num=first_page["page_num"],
        request_nonce_ms=first_page["request_nonce_ms"],
        observed_at=datetime.fromisoformat(first_page["observed_at"].replace("Z", "+00:00")),
    )
    observed_source_event = next(event for event in parsed_page.events if event.event_id == EVENT_ID)
    assert observed_source_event.home_team_name == initial.inventory.home_team_name
    assert observed_source_event.away_team_name == initial.inventory.away_team_name
    assert observed_source_event.kickoff_utc == KICKOFF
    assert observed_source_event.source_raw_sha256 == first_page["raw_sha256"]
    assert source_manifest["pagination_complete"] is True
    assert source_manifest["provider_total_num"] == 692

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
        _detail_directories=((EVENT_ID, paths["initial"]),),
        _repository_root=repo_root,
        canonical_sha256="c" * 64,
        evaluation_time=INITIAL_OBSERVED,
        source_fotmob_admission_sha256="e" * 64,
        fotmob_capture_identities=(),
        _fixture_stable_identity_state_sha256=None,
        _fixture_stable_identity_state_snapshot={},
        to_dict=lambda: {"synthetic_fixture_reconciliation": True},
    )
    bundle = object.__new__(pc_upcoming.CurrentShadowPcUpcomingReconciliationBundle)
    object.__setattr__(bundle, "_legacy_bundle", reconciled)
    object.__setattr__(bundle, "manifest", SimpleNamespace(canonical_sha256="f" * 64))
    object.__setattr__(bundle, "repository_root", repo_root)
    object.__setattr__(bundle, "stabilization_sha256", "d" * 64)
    monkeypatch.setattr(
        pc_upcoming,
        "verify_current_event_discovery_reconciliation_bundle",
        lambda value: bundle if value is bundle else pytest.fail("unexpected reconciliation bundle"),
    )

    # This is deliberately synthetic history/model input. Provider event bytes
    # and response manifests above are the exact retained live bytes.
    history = object.__new__(CurrentLatestDurableFreshHistoryHandoff)
    kickoff_iso = KICKOFF.isoformat().replace("+00:00", "Z")
    scan = prc.scan_fixture_all_markets(
        fixture_identity=FIXTURE_ID,
        research_xg=prc.ResearchXGRates(
            calibrated_home=2.0,
            calibrated_away=0.7,
            sealed_prediction_sha256="a" * 64,
            history_prefix_identity="b" * 64,
            source_fixture_identity=FIXTURE_ID,
        ),
        kickoff_utc_iso=kickoff_iso,
        provider_semantic_by_market={market: "SUPPORTED" for market in MarketId},
    )
    monkeypatch.setattr(
        prc,
        "scan_current_fixture_all_markets",
        lambda **_kwargs: scan,
    )
    context = build_current_shadow_price_context_from_reconciliation(
        complete_current_history=history,
        fixture_identity=FIXTURE_ID,
        provider_event_id=EVENT_ID,
        current_reconciliation_bundle=bundle,
    )
    assert context.source_context_mode == CURRENT_RECONCILIATION_DIRECT
    assert context.source_context_policy_id == CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID
    return repo_root, paths, bundle, reconciled, context, fresh


def _clone_context(value, **changes):
    clone = object.__new__(type(value))
    for field_name in value.__dataclass_fields__:
        object.__setattr__(clone, field_name, getattr(value, field_name))
    for field_name, replacement in changes.items():
        object.__setattr__(clone, field_name, replacement)
    return clone


def _load_exact_pre_p4_4r_verifier(repo_root: Path):
    """Compile only the verifier function from the pinned pre-refactor source."""

    source = subprocess.check_output(
        ["git", "show", f"{BASE_MAIN_SHA}:domain/_current_shadow_quote_binding.py"],
        cwd=repo_root,
    )
    assert hashlib.sha256(source).hexdigest() == PRE_FIX_QUOTE_BINDING_SHA256
    tree = ast.parse(source, filename="pinned-pre-p4-4r/_current_shadow_quote_binding.py")
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "verify_current_shadow_price_context"
    )
    namespace = {
        "Any": Any,
        "CurrentShadowPriceContext": _load_current_context_type(),
        "ShadowPriceError": ShadowPriceError,
        "LEGACY_PR253_FIXTURE_BRIDGE": "LEGACY_PR253_FIXTURE_BRIDGE",
        "CURRENT_RECONCILIATION_DIRECT": "CURRENT_RECONCILIATION_DIRECT",
    }
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "pinned-pre-p4-4r-verifier", "exec"), namespace)
    return namespace["verify_current_shadow_price_context"]


def _load_current_context_type():
    from domain._current_shadow_quote_binding import CurrentShadowPriceContext

    return CurrentShadowPriceContext


class _PreP44RRouterReplayBinding:
    """Test shim reproducing the exact old direct/bridge-only verifier at Router replay."""

    fresh_reprice_enabled = True

    def __init__(self, stale_verifier):
        self._stale_verifier = stale_verifier

    def verify_context(self, value):
        return self._stale_verifier(value)

    def price_all(self, context):
        from domain import current_shadow_all_market_price_all as price_all

        return price_all._price_all_shadow_fixture(context, runtime_bindings=self)

    def verify_price_all_bundle(self, value):
        from domain import current_shadow_all_market_price_all as price_all

        return price_all._verify_shadow_price_all_bundle(value, runtime_bindings=self)


def _run_single_offline_replay(monkeypatch, tmp_path: Path) -> bytes:
    NETWORK_ATTEMPTS.clear()
    _install_network_sentinel(monkeypatch)
    repo_root, paths, _bundle, _reconciled, prior_context, fresh_evidence = _offline_composition(
        monkeypatch, tmp_path
    )
    initial_price = runner.price_module.price_all_shadow_fixture(prior_context)
    initial_router = runner.router_module.route_shadow_price_results(initial_price)
    assert initial_price._context.canonical_sha256 == prior_context.canonical_sha256

    # This selection is synthetic harness control, not a claim about the live
    # run's selection. Exact provider bytes and quote observations are retained.
    selected_source = SimpleNamespace(
        price_all_bundle=initial_price,
        router_decision=SimpleNamespace(status=ShadowRouterDecisionStatus.SELECTED),
    )
    sources = SimpleNamespace(
        router_inputs=(selected_source,),
        reviewed_fixture_count=1,
        reconciled_fixture_count=1,
        provider_event_count=1,
        priced_fixture_count=1,
        router_selected_count=1,
        router_no_bet_count=0,
        source_summary={"synthetic_composition_fixture": True, "wager_placed": False},
    )
    assert initial_router.price_all_bundle_sha256 == initial_price.canonical_sha256

    from domain.current_shadow_all_market_portfolio import _canonical, optimize_shadow_portfolio
    from domain import current_shadow_all_market_portfolio as portfolio_module

    binding = fresh_reprice_current_shadow_runtime_bindings()
    replay = _refresh_selected_inputs(
        sources,
        repository_root=repo_root,
        runtime_bindings=binding,
        evidence_loader=lambda **_kwargs: paths["fresh"],
    )
    assert len(replay.router_inputs) == 1
    portfolio_input = replay.router_inputs[0]
    fresh_context = portfolio_input.price_all_bundle._context
    assert fresh_context.source_context_mode == "PRF_CURRENT_RECONCILIATION_FRESH_REPRICE"
    assert fresh_context.provider_event_id == EVENT_ID
    assert fresh_context.fixture_identity == FIXTURE_ID
    assert fresh_context.evaluation_time == FRESH_OBSERVED
    assert fresh_context.current_mapping_rebind_sha256 is None
    assert fresh_context.bridge_bundle_sha256 is None
    assert portfolio_input.source_raw_sha256 == (
        "d4f08a6f7293943e99a4a2db94d545714dee55e3d14335ad593a16f5154ff33a"
    )

    # Re-run the same retained fresh context through Router's Price-all
    # reconstruction seam with the exact pre-P4.4R direct/bridge-only verifier
    # function loaded from the pinned main commit. This is the pre-fix failure
    # class, not a direct verifier-only assertion.
    stale_verifier = _load_exact_pre_p4_4r_verifier(Path(__file__).resolve().parents[1])
    stale_binding = _PreP44RRouterReplayBinding(stale_verifier)
    with pytest.raises(ShadowPriceError, match="unknown current Shadow source-context mode"):
        router_module._route_shadow_price_results(
            portfolio_input.price_all_bundle,
            runtime_bindings=stale_binding,
        )

    from domain._current_shadow_quote_binding import (
        FRESH_REPRICE_MODE,
        build_current_shadow_price_context_for_fresh_reprice,
    )

    initial_evidence = prb.load_provider_event_evidence(
        paths["initial"],
        repository_root=repo_root,
        fixture_identity=EVENT_ID,
        fixture_identity_basis=(
            "PCUPCOMING_RUNTIME_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION"
        ),
    )
    with pytest.raises(ShadowPriceError, match="not strictly newer"):
        build_current_shadow_price_context_for_fresh_reprice(
            prior_context=prior_context,
            fresh_provider_event_evidence=initial_evidence,
            runtime_bindings=binding,
        )
    tamper_cases = (
        ("source_context_mode", "UNKNOWN", "unknown current Shadow source-context mode"),
        ("provider_event_id", "sr:match:99999999999", "lacks one exact current fixture"),
        ("fixture_identity", "FOTMOB:5071394", "fixture identity differs"),
        ("evaluation_time", INITIAL_OBSERVED, "observation differs"),
        ("source_raw_sha256", "1" * 64, "evidence ancestry drifted"),
        ("source_manifest_sha256", "2" * 64, "evidence ancestry drifted"),
        ("source_inventory_sha256", "3" * 64, "evidence ancestry drifted"),
        ("fixture_reconciliation_sha256", "4" * 64, "evidence ancestry drifted"),
        ("current_mapping_rebind_sha256", "5" * 64, "bridge or source authority"),
        ("source_context_policy_id", "UNREVIEWED", "bridge or source authority"),
    )
    assert fresh_context.source_context_mode == FRESH_REPRICE_MODE
    for field_name, replacement, error in tamper_cases:
        with pytest.raises(ShadowPriceError, match=error):
            binding.verify_context(
                _clone_context(fresh_context, **{field_name: replacement})
            )
    optimized = optimize_shadow_portfolio(
        replay.router_inputs,
        target_size=20,
        evaluation_time=FRESH_OBSERVED,
    )
    assert optimized.to_dict()["authority"]["wager_placed"] is False
    assert portfolio_module.verify_shadow_portfolio_router_input(portfolio_input).to_dict() == (
        portfolio_input.to_dict()
    )
    assert NETWORK_ATTEMPTS == []
    return _canonical({
        "pre_fix_router_replay": {
            "result": "REPRODUCED",
            "failure": "ShadowPriceError: unknown current Shadow source-context mode",
            "historical_verifier_source_sha256": PRE_FIX_QUOTE_BINDING_SHA256,
            "fixture_identity": fresh_context.fixture_identity,
            "provider_event_id": fresh_context.provider_event_id,
            "router_reconstruction_reached_stale_verifier": True,
        },
        "portfolio_router_input": portfolio_input.to_dict(),
        "portfolio_optimization": optimized.to_dict(),
        "source_summary": dict(replay.source_summary),
    })


def test_single_clean_process_retained_replay(monkeypatch, tmp_path):
    if os.environ.get("ATHENA_P4_4R_CHILD_REPLAY") != "1":
        pytest.skip("launched only by the clean-process determinism parent test")
    output = _run_single_offline_replay(monkeypatch, tmp_path)
    print("P4_4R_REPLAY_SHA256=" + hashlib.sha256(output).hexdigest())


def test_retained_failure_slice_replays_identically_in_two_clean_processes():
    """Two import orders/processes produce byte-identical offline replay output."""

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    env["ATHENA_P4_4R_CHILD_REPLAY"] = "1"
    modules = [
        "domain.current_shadow_all_market_price_all",
        "domain.current_shadow_all_market_router",
        "domain.current_shadow_all_market_portfolio",
        "domain._current_shadow_quote_binding",
        "domain.current_shadow_canonical_core_adapter",
        "domain.current_shadow_runtime_bindings",
        "domain.current_shadow_fresh_reprice_runtime",
        "domain.current_shadow_all_market_runner",
        "scripts.execute_current_shadow_all_market_fresh_reprice",
        "scripts.execute_current_shadow_all_market_fresh_reprice_bound",
        "scripts.execute_current_shadow_all_market",
    ]
    outputs = []
    for order in (modules, list(reversed(modules))):
        bootstrap = (
            "import importlib,json,sys,pytest; sys.path.insert(0,'.'); "
            f"[importlib.import_module(name) for name in json.loads({json.dumps(json.dumps(order))})]; "
            f"sys.exit(pytest.main(['-q',{str(Path(__file__).resolve())!r},"
            "'-k','single_clean_process_retained_replay','-s']))"
        )
        result = subprocess.run(
            [sys.executable, "-c", bootstrap],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, combined
        marker = next(
            (line.split("=", 1)[1] for line in combined.splitlines()
             if line.startswith("P4_4R_REPLAY_SHA256=")),
            None,
        )
        assert marker is not None, combined
        outputs.append(marker)
    assert outputs[0] == outputs[1]
    print("P4_4R_DETERMINISM_SHA256=" + outputs[0])
