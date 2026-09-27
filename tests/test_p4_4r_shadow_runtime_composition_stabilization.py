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
from domain import current_direct_provider_live_quote_mapping_consumption as current_quotes
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as pc_upcoming
from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_source
from domain import current_sportybet_semantic_registry as prb
from domain import sportybet_live_event_quote_evidence as live
from domain._current_shadow_price_core import (
    SOURCE_CONTEXT_POLICY_ID,
    ShadowPriceError,
    ShadowRouterDecisionStatus,
)
from domain import _current_shadow_quote_binding as quote_binding
from domain._current_shadow_quote_binding import (
    CURRENT_RECONCILIATION_DIRECT,
    CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID,
    FRESH_REPRICE_MODE,
    FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID,
    LEGACY_PR253_FIXTURE_BRIDGE,
    build_current_shadow_price_context,
    build_current_shadow_price_context_from_reconciliation,
    build_current_shadow_price_context_for_fresh_reprice,
)
from domain.current_shadow_runtime_bindings import (
    CurrentShadowRuntimeBindings,
    _VerifiedContextMemo,
    default_current_shadow_runtime_bindings,
    fresh_reprice_current_shadow_runtime_bindings,
)
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
PRE_FIX_VERIFIER_FIXTURE_SHA256 = "7547f701e025aa6723b7b0fc181c00347292bca2dfe0a15eeeb7a9bb205f2f87"
KICKOFF = datetime(2026, 9, 27, 2, 30, tzinfo=UTC)
INITIAL_OBSERVED = datetime(2026, 9, 27, 1, 19, 5, 661325, tzinfo=UTC)
FRESH_OBSERVED = datetime(2026, 9, 27, 1, 55, 27, 176214, tzinfo=UTC)
NETWORK_ATTEMPTS: list[str] = []
_RETAINED_FIXTURE_FILES = (
    "initial/event.raw.json",
    "initial/manifest.json",
    "fresh/event.raw.json",
    "fresh/manifest.json",
    "accepted-source/manifest.json",
    "accepted-source/page-001.raw.json",
)


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


def _materialize_exact_fixture_bytes(destination_root: Path) -> Path:
    """Read immutable fixture blobs from Git to avoid autocrlf rewriting bytes."""

    source_root = Path(__file__).resolve().parents[1]
    fixture_root = destination_root / "p4-4r-exact-git-fixture-bytes"
    for relative in _RETAINED_FIXTURE_FILES:
        git_path = f"HEAD:tests/fixtures/p4_4r_run_36285099805_quote_evidence/{relative}"
        content = subprocess.check_output(["git", "show", git_path], cwd=source_root)
        output = fixture_root / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
    return fixture_root


def _copy_evidence(repo_root: Path, monkeypatch, fixture_root: Path):
    evidence_root = repo_root / live.ALLOWED_OUTPUT_RELATIVE
    paths = {}
    for sample, capture_id in (
        ("initial", "1aec7fa77430c1f7ab99b957"),
        ("fresh", "70e9dad393d0b396357753c2"),
    ):
        destination = evidence_root / capture_id
        destination.mkdir(parents=True)
        shutil.copyfile(fixture_root / sample / "event.raw.json", destination / "event.raw.json")
        shutil.copyfile(fixture_root / sample / "manifest.json", destination / "manifest.json")
        paths[sample] = destination
    return paths


def _offline_composition(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fixture_root = _materialize_exact_fixture_bytes(tmp_path)
    paths = _copy_evidence(repo_root, monkeypatch, fixture_root)
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

    source_manifest_bytes = (fixture_root / "accepted-source" / "manifest.json").read_bytes()
    source_page_bytes = (fixture_root / "accepted-source" / "page-001.raw.json").read_bytes()
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


def _synthetic_legacy_bridge_context(monkeypatch, prior_context, runtime_bindings):
    """Attach a reviewed-shape PR253 bridge to retained provider event evidence."""

    bridge_input = object.__new__(current_quotes.CurrentDirectProviderMappedQuoteBundle)
    bridge = object.__new__(current_quotes.CurrentDirectProviderMappedQuoteBundle)
    inventory = prior_context.provider_inventory
    bridge_fields = {
        "schema_version": current_quotes.SCHEMA_VERSION,
        "dataset_name": current_quotes.DATASET_NAME,
        "status": current_quotes.STATUS_LIVE,
        "proof_mode": current_quotes.LIVE_CURRENT,
        "fixture_id": prior_context.fixture_identity,
        "event_id": prior_context.provider_event_id,
        "home_team_name": inventory.home_team_name,
        "away_team_name": inventory.away_team_name,
        "kickoff_utc": inventory.kickoff_utc,
        "discovery_observed_at": prior_context.evaluation_time,
        "direct_event_observed_at": inventory.observed_at,
        "discovery_age_seconds": 0.0,
        "direct_event_age_seconds": 0.0,
        "kickoff_lead_seconds": (inventory.kickoff_utc - prior_context.evaluation_time).total_seconds(),
        "max_source_age_seconds": current_quotes.MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": current_quotes.MINIMUM_LEAD_SECONDS,
        "current_mapping_rebind_sha256": "e" * 64,
        "current_mapping_contract_sha256": current_quotes.PR252_CONTRACT_SHA256,
        "source_current_reconciliation_sha256": "c" * 64,
        "source_legacy_mapping_sha256": "b" * 64,
        "current_inventory_sha256": inventory.canonical_sha256,
        "current_manifest_sha256": prior_context.source_manifest_sha256,
        "current_raw_sha256": prior_context.source_raw_sha256,
        "evaluation_time": prior_context.evaluation_time,
        "quotes": (),
        "quote_audits": (),
        "source_mapping_audits": (),
        "authority": {
            "current_mapping_source_replay": True,
            "direct_event_source_replay": True,
            "current_provider_mapped_quote_evidence": True,
            "price_all": False,
            "market_router": False,
            "portfolio_optimization": False,
            "final_selection": False,
            "accumulator_slip_construction": False,
            "sportybet_execution": False,
            "staking": False,
            "bet": False,
        },
        "next_boundary": current_quotes.NEXT_BOUNDARY,
        "contract_sha256": current_quotes.EXPECTED_CONTRACT_SHA256,
        "_source_mapping": None,
    }
    for name, value in bridge_fields.items():
        object.__setattr__(bridge, name, value)
    monkeypatch.setattr(
        current_quotes,
        "verify_current_direct_provider_mapped_quote_bundle",
        lambda value: bridge if value is bridge_input or value is bridge else pytest.fail(
            "unexpected PR253 bridge replay input"
        ),
    )
    context = build_current_shadow_price_context(
        complete_current_history=prior_context._complete_current_history,
        fixture_identity=prior_context.fixture_identity,
        provider_event_evidence=prior_context._event_evidence,
        fixture_quote_bridge=bridge_input,
        runtime_bindings=runtime_bindings,
    )
    return context, bridge


def _load_exact_pre_p4_4r_verifier():
    """Compile the pinned pre-fix verifier slice copied from exact base main."""

    source = (
        Path(__file__).parent
        / "fixtures"
        / "p4_4r_pre_fix_quote_context_verifier.py"
    ).read_bytes()
    source = source.replace(b"\r\n", b"\n")
    assert hashlib.sha256(source).hexdigest() == PRE_FIX_VERIFIER_FIXTURE_SHA256
    tree = ast.parse(source, filename="pinned-pre-p4-4r/quote_context_verifier.py")
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
    stale_verifier = _load_exact_pre_p4_4r_verifier()
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
        ("source_context_policy_id", "UNREVIEWED", "policy does not match its mode"),
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


def test_legacy_pr253_context_replays_through_price_all_without_network(
    monkeypatch, tmp_path
):
    """The retained legacy bridge remains a working mode under the stable verifier."""

    NETWORK_ATTEMPTS.clear()
    _install_network_sentinel(monkeypatch)
    _repo, _paths, _bundle, _reconciled, direct_context, _fresh = _offline_composition(
        monkeypatch, tmp_path
    )
    binding = default_current_shadow_runtime_bindings()
    context, bridge = _synthetic_legacy_bridge_context(
        monkeypatch, direct_context, binding
    )

    assert context.source_context_mode == LEGACY_PR253_FIXTURE_BRIDGE
    assert context._runtime_bindings is binding
    assert context.bridge_bundle_sha256 == bridge.canonical_sha256
    assert len(context.bridge_bundle_sha256) == 64
    assert context.current_mapping_rebind_sha256 == bridge.current_mapping_rebind_sha256 == "e" * 64
    checked = quote_binding.verify_current_shadow_price_context(context)
    assert checked.source_context_mode == LEGACY_PR253_FIXTURE_BRIDGE
    assert checked.bridge_bundle_sha256 == bridge.canonical_sha256
    assert checked.current_mapping_rebind_sha256 == bridge.current_mapping_rebind_sha256

    price_bundle = binding.price_all(checked)
    replayed_price_bundle = binding.verify_price_all_bundle(price_bundle)
    assert replayed_price_bundle.to_dict() == price_bundle.to_dict()
    assert replayed_price_bundle._context.source_context_mode == LEGACY_PR253_FIXTURE_BRIDGE

    tampered = _clone_context(
        context,
        current_mapping_rebind_sha256="f" * 64,
    )
    with pytest.raises(ShadowPriceError, match="differs on source replay"):
        binding.verify_context(tampered)
    assert NETWORK_ATTEMPTS == []


def test_runtime_binding_memo_uses_exact_policy_identity_for_each_mode(
    monkeypatch, tmp_path
):
    NETWORK_ATTEMPTS.clear()
    _install_network_sentinel(monkeypatch)
    _repo, _paths, _bundle, _reconciled, direct_context, fresh_evidence = _offline_composition(
        monkeypatch, tmp_path
    )
    direct_binding = default_current_shadow_runtime_bindings()
    direct_binding.verify_context(direct_context)

    fresh_binding = fresh_reprice_current_shadow_runtime_bindings()
    fresh_context = build_current_shadow_price_context_for_fresh_reprice(
        prior_context=direct_context,
        fresh_provider_event_evidence=fresh_evidence,
        runtime_bindings=fresh_binding,
    )
    fresh_binding.verify_context(fresh_context)

    legacy_context, _bridge = _synthetic_legacy_bridge_context(
        monkeypatch, direct_context, direct_binding
    )
    direct_binding.verify_context(legacy_context)

    expected = {
        LEGACY_PR253_FIXTURE_BRIDGE: SOURCE_CONTEXT_POLICY_ID,
        CURRENT_RECONCILIATION_DIRECT: CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID,
        FRESH_REPRICE_MODE: FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID,
    }
    contexts = (legacy_context, direct_context, fresh_context)
    bindings = (direct_binding, direct_binding, fresh_binding)
    for context, binding in zip(contexts, bindings, strict=True):
        assert binding._verified_contexts._rows[
            (
                context.canonical_sha256,
                expected[context.source_context_mode],
                binding.canonical_sha256,
            )
        ].source is context
        assert binding._verified_contexts._rows[
            (
                context.canonical_sha256,
                expected[context.source_context_mode],
                binding.canonical_sha256,
            )
        ].verifier_policy_id == expected[context.source_context_mode]
    assert NETWORK_ATTEMPTS == []


def test_context_memo_rejects_mode_policy_mismatch_unknown_mode_and_other_binding(
    monkeypatch, tmp_path
):
    NETWORK_ATTEMPTS.clear()
    _install_network_sentinel(monkeypatch)
    _repo, _paths, _bundle, _reconciled, direct_context, _fresh = _offline_composition(
        monkeypatch, tmp_path
    )
    binding = default_current_shadow_runtime_bindings()
    binding.verify_context(direct_context)

    wrong_policy = _clone_context(
        direct_context,
        source_context_policy_id=FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID,
    )
    original_get = binding._verified_contexts.get
    monkeypatch.setattr(
        binding._verified_contexts,
        "get",
        lambda **_kwargs: pytest.fail("policy mismatch reached the memo"),
    )
    with pytest.raises(ShadowPriceError, match="policy does not match its mode"):
        binding.verify_context(wrong_policy)
    monkeypatch.setattr(binding._verified_contexts, "get", original_get)

    unknown = _clone_context(
        direct_context,
        source_context_mode="UNKNOWN_REVIEWED_MODE",
        source_context_policy_id="unreviewed-policy",
    )
    with pytest.raises(ShadowPriceError, match="unknown current Shadow source-context mode"):
        binding.verify_context(unknown)

    # Deliberately share the cache object between two otherwise valid bindings
    # to prove the binding identity is a distinct memo-key dimension.
    other_binding = fresh_reprice_current_shadow_runtime_bindings()
    object.__setattr__(other_binding, "_verified_contexts", binding._verified_contexts)
    canonical_bytes = quote_binding._canonical_bytes(direct_context.to_dict())
    canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()
    assert binding._verified_contexts.get(
        source=direct_context,
        canonical_bytes=canonical_bytes,
        canonical_sha256=canonical_sha,
        verifier_policy_id=CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID,
        binding_identity=other_binding.canonical_sha256,
    ) is None
    other_binding.verify_context(direct_context)
    assert (
        canonical_sha,
        CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID,
        other_binding.canonical_sha256,
    ) in binding._verified_contexts._rows
    assert NETWORK_ATTEMPTS == []
