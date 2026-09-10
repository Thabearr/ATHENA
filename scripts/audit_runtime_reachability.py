#!/usr/bin/env python3
"""Generate deterministic synthetic runtime reachability evidence for ATHENA P0.5.

The audit deliberately replaces only external/side-effect boundaries.  The
business decision functions named in the trace are the repository's real
functions and execute normally.  No live provider acquisition, Current Shadow
workflow, SMTP delivery, SportyBet create/reload, login, wallet, stake, or wager
is permitted by this audit.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Mapping

from domain.architecture_runtime_reachability import (
    POLICY_ID,
    SCHEMA_VERSION,
    RuntimeReachabilityError,
    RuntimeTrace,
    canonical_json_bytes,
    scoped_callable_checkpoint,
    validate_trace_document,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPOSITORY_ROOT / "artifacts/architecture/repository-architecture-inventory-v1.json"
AUTHORITY_PATH = REPOSITORY_ROOT / "config/architecture/main-shadow-authority-parity-v1.json"
LEGACY_CASES_PATH = REPOSITORY_ROOT / "tests/fixtures/architecture/legacy_market_selection_cases_v1.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts/architecture/runtime-reachability-v1.json"
BASELINE_MAIN = "b428dbd00380dd71456640d77b26ac79fe945c5f"
FIXED_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

EXPECTED_SUPPORTED_ROOTS = frozenset({
    "build_acca",
    "scripts.execute_current_shadow_request",
    "scripts.restore_current_shadow_history_prime_artifact",
    "scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
    "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
    "scripts.send_current_shadow_email",
})


@contextmanager
def _temporary_attribute(owner: Any, attribute: str, value: Any) -> Iterator[None]:
    original = getattr(owner, attribute)
    setattr(owner, attribute, value)
    try:
        yield
    finally:
        setattr(owner, attribute, original)


@contextmanager
def _temporary_environment(updates: Mapping[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in updates}
    for key, value in updates.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _resolve_ref(ref: str) -> str:
    if type(ref) is not str or not ref or ref != ref.strip():
        raise RuntimeReachabilityError("ref must be exact non-empty text")
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=REPOSITORY_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeReachabilityError(f"could not resolve runtime audit ref: {ref}") from exc
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise RuntimeReachabilityError("resolved runtime audit ref is not a Git commit SHA")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeReachabilityError(f"required architecture input is unreadable: {path}") from exc
    if type(value) is not dict:
        raise RuntimeReachabilityError(f"required architecture input is not an object: {path}")
    return value


def _supported_roots() -> tuple[str, ...]:
    inventory = _load_json(INVENTORY_PATH)
    rows = inventory.get("supported_roots")
    if type(rows) is not list:
        raise RuntimeReachabilityError("P0.2 inventory omitted supported_roots")
    roots: list[str] = []
    for row in rows:
        if type(row) is not dict:
            raise RuntimeReachabilityError("P0.2 supported root row is malformed")
        root = row.get("root_identifier") or row.get("root_module")
        if type(root) is not str or not root.strip():
            raise RuntimeReachabilityError("P0.2 supported root identity is malformed")
        roots.append(root)
    result = tuple(sorted(set(roots)))
    if len(result) != len(roots):
        raise RuntimeReachabilityError("P0.2 supported roots contain duplicate identities")
    if set(result) != set(EXPECTED_SUPPORTED_ROOTS):
        raise RuntimeReachabilityError(
            "P0.2 supported-root set changed; P0.5 requires reviewed scope update: "
            f"observed={result!r}"
        )
    return result


def _root_profiles() -> dict[str, str]:
    policy = _load_json(AUTHORITY_PATH)
    assignments = policy.get("reviewed_module_assignments")
    if type(assignments) is not list:
        raise RuntimeReachabilityError("P0.3 policy omitted reviewed_module_assignments")
    profiles: dict[str, str] = {}
    cleanup: dict[str, str] = {}
    for row in assignments:
        if type(row) is not dict:
            raise RuntimeReachabilityError("P0.3 module assignment is malformed")
        component = row.get("component_id")
        profile = row.get("authority_profile")
        if type(component) is str and type(profile) is str:
            profiles[component] = profile
            cleanup[component] = row.get("cleanup_disposition")
    for root in EXPECTED_SUPPORTED_ROOTS:
        if root not in profiles:
            raise RuntimeReachabilityError(f"supported root lacks reviewed P0.3 profile: {root}")
        if cleanup.get(root) != "UNCLASSIFIED":
            raise RuntimeReachabilityError(
                f"supported root cleanup disposition is no longer UNCLASSIFIED: {root}"
            )
    return profiles


def _prediction_snapshot(value: Any) -> dict[str, Any]:
    return {
        "fixture_id": value.fixture_id,
        "league": value.league,
        "home_team": value.home_team,
        "away_team": value.away_team,
        "home_win_probability": value.home_win_probability,
        "draw_probability": value.draw_probability,
        "away_win_probability": value.away_win_probability,
        "home_xg": value.home_xg,
        "away_xg": value.away_xg,
        "expected_goals": value.expected_goals,
        "recommended_market": value.recommended_market,
        "market_confidence": value.market_confidence,
        "ranked_markets": [[name, score] for name, score in value.ranked_markets],
    }


def _legacy_cases() -> list[dict[str, Any]]:
    from engine.market_selector import MarketSelector
    from models.prediction import Prediction

    dataset = _load_json(LEGACY_CASES_PATH)
    if dataset.get("schema_version") != 1:
        raise RuntimeReachabilityError("legacy market-selection evidence schema drifted")
    cases = dataset.get("cases")
    if type(cases) is not list or len(cases) < 5:
        raise RuntimeReachabilityError("P0.5 requires at least five legacy selector evidence cases")

    results: list[dict[str, Any]] = []
    for case in cases:
        if type(case) is not dict:
            raise RuntimeReachabilityError("legacy selector case is malformed")
        prediction_data = case.get("prediction")
        extras = case.get("extra_attributes")
        if type(prediction_data) is not dict or type(extras) is not dict:
            raise RuntimeReachabilityError("legacy selector case inputs are malformed")
        prediction = Prediction(**prediction_data)
        for key, value in extras.items():
            setattr(prediction, key, value)
        result = MarketSelector().select(prediction)
        expected_market = case.get("expected_current_recommended_market")
        expected_confidence = case.get("expected_current_market_confidence")
        if (
            result.recommended_market != expected_market
            or result.market_confidence != expected_confidence
        ):
            raise RuntimeReachabilityError(
                f"legacy selector evidence changed for {case.get('case_id')}: "
                f"observed={(result.recommended_market, result.market_confidence)!r}"
            )
        tied_prefix = case.get("expected_current_tied_prefix")
        if tied_prefix is not None:
            observed = [[name, score] for name, score in result.ranked_markets[: len(tied_prefix)]]
            if observed != tied_prefix:
                raise RuntimeReachabilityError(
                    f"legacy selector tie evidence changed for {case.get('case_id')}"
                )
        results.append({
            "case_id": case["case_id"],
            "current_recommended_market": result.recommended_market,
            "current_market_confidence": result.market_confidence,
            "current_ranked_markets": [[name, score] for name, score in result.ranked_markets],
            "observed_problem": case["observed_problem"],
            "future_required_property": case["future_required_property"],
            "evidence_classification": case["evidence_classification"],
        })
    return results


def _probe_build_acca(source_commit: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    import build_acca
    from domain.markets import DecisionStatus, resolve_legacy_selection, serialize_selection
    from intelligence.acca_filter import AccaFilter
    from intelligence.accumulator import AccumulatorEngine
    from services.prediction_service import PredictionService
    from engine.market_selector import MarketSelector

    trace = RuntimeTrace(
        source_commit=source_commit,
        supported_root="build_acca",
        root_authority_profile=profile,
        synthetic_case_id="BUILD_ACCA_SYNTHETIC_DOWNSTREAM_SELECTION_V1",
    )
    canonical = serialize_selection(resolve_legacy_selection("DC_1X"))
    quote_observed = (FIXED_NOW - timedelta(seconds=30)).isoformat()
    priced = {
        **canonical,
        "verdict": "DC_1X",
        "category": "DOUBLE_CHANCE",
        "prob": 0.72,
        "estimated_probability": 0.72,
        "edge": 0.10,
        "edge_is_bookmaker_value": True,
        "edge_method": "P0.5_SYNTHETIC_QUOTE_VALUE",
        "bookmaker_odds": 1.40,
        "bookmaker_quote": {
            "market_id": canonical["market_id"],
            "outcome_id": canonical["outcome_id"],
            "line": canonical["line"],
            "bookmaker_odds": 1.40,
            "source": "p0.5_synthetic_bookmaker",
            "quote_snapshot_id": "p0.5-build-acca-quote",
            "observed_at": quote_observed,
            "is_genuine": True,
            "is_current": True,
        },
        "edge_pp": 10.0,
        "kelly_stake_pct": 1.0,
    }
    analyzed = {
        "fixture_id": "P05-BUILD-1",
        "fixture": "Synthetic Alpha vs Synthetic Beta",
        "home_team": "Synthetic Alpha",
        "away_team": "Synthetic Beta",
        "league": "Premier League",
        "match_date": "2026-09-10T18:00:00+00:00",
        "decision_status": DecisionStatus.BET.value,
        "accumulator_eligible_selection": priced,
        "edge": 0.10,
        "edge_is_bookmaker_value": True,
        "edge_pp": 10.0,
        "risk_score": 10.0,
        "freshness": 0.90,
        "upset_alert": False,
        "evidence_report": {"synthetic_case_id": "BUILD_ACCA_SYNTHETIC_DOWNSTREAM_SELECTION_V1"},
    }

    builder = object.__new__(build_acca.AccaBuilder)
    builder.days_ahead = 1
    builder.min_edge = 0.05
    builder.acca_filter = AccaFilter()
    builder.acca_engine = AccumulatorEngine(
        min_edge=0.05,
        current_time_provider=lambda: FIXED_NOW,
    )
    builder.kelly_calculator = SimpleNamespace(
        calculate_acca_stake=lambda *_args, **_kwargs: 0.0
    )
    builder._fetch_live_fixtures = lambda: []
    builder._get_fixtures_from_db = lambda _days: [{"fixture_id": "P05-BUILD-1"}]
    builder._analyze_fixtures = lambda _fixtures: [dict(analyzed)]
    builder._display_safe_selections = lambda *_args, **_kwargs: None

    with ExitStack() as stack:
        stack.enter_context(_temporary_attribute(
            build_acca,
            "console",
            SimpleNamespace(print=lambda *_args, **_kwargs: None),
        ))
        stack.enter_context(scoped_callable_checkpoint(
            builder,
            "build",
            trace=trace,
            module="build_acca",
            qualname="AccaBuilder.build",
            checkpoint_kind="ENTRYPOINT",
            authority_category="NONE",
            notes=("synthetic_analysis_seam=true", "live_fixture_and_db_io=false"),
        ))
        stack.enter_context(scoped_callable_checkpoint(
            builder.acca_filter,
            "filter_and_rank_legs",
            trace=trace,
            module="intelligence.acca_filter",
            qualname="AccaFilter.filter_and_rank_legs",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="ACCUMULATOR_FILTERING",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            builder.acca_filter,
            "build_filtered_acca",
            trace=trace,
            module="intelligence.acca_filter",
            qualname="AccaFilter.build_filtered_acca",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="ACCUMULATOR_FILTERING",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            builder.acca_engine,
            "generate_accumulator",
            trace=trace,
            module="intelligence.accumulator",
            qualname="AccumulatorEngine.generate_accumulator",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="ACCUMULATOR_CONSTRUCTION",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            PredictionService,
            "predict",
            trace=trace,
            module="services.prediction_service",
            qualname="PredictionService.predict",
            checkpoint_kind="ORCHESTRATION",
            authority_category="MODEL_ANALYSIS",
            notes=("measurement_wrapper_only",),
        ))
        stack.enter_context(scoped_callable_checkpoint(
            MarketSelector,
            "select",
            trace=trace,
            module="engine.market_selector",
            qualname="MarketSelector.select",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="LEGACY_MARKET_SELECTION",
            notes=("measurement_wrapper_only",),
        ))
        result = builder.build(days=1, fold_size=1, strict=True, league=None)

    executed = {(item["module"], item["qualname"]) for item in trace.records}
    prediction_service_executed = (
        "services.prediction_service", "PredictionService.predict"
    ) in executed
    market_selector_executed = (
        "engine.market_selector", "MarketSelector.select"
    ) in executed
    token = trace.begin(
        module="build_acca",
        qualname="AccaBuilder.build.terminus",
        checkpoint_kind="TERMINUS",
        authority_category="NONE",
        notes=(
            f"prediction_service_executed={str(prediction_service_executed).lower()}",
            f"market_selector_executed={str(market_selector_executed).lower()}",
            "synthetic_analysis_result_injected_before_accumulator_gate=true",
        ),
    )
    trace.finish(token)
    document = trace.to_dict(disposition="EXECUTED_DECISION_AUTHORITY")
    validate_trace_document(document)
    return document, {
        "result_decision_status": result.get("decision_status"),
        "prediction_service_executed": prediction_service_executed,
        "market_selector_executed": market_selector_executed,
        "decision_authority_modules": sorted({
            item["module"]
            for item in document["checkpoints"]
            if item["checkpoint_kind"] == "DECISION_AUTHORITY"
        }),
    }


class _SyntheticPredictionAnalyzer:
    def analyze(self, _fixture: Any):
        from models.prediction import Prediction

        return Prediction(
            fixture_id=6001,
            league="Synthetic League",
            home_team="Legacy Home",
            away_team="Legacy Away",
            home_strength=70.0,
            away_strength=30.0,
            home_xg=1.5,
            away_xg=0.7,
            expected_goals=2.2,
        )


def _probe_prediction_service(source_commit: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from engine.market_selector import MarketSelector
    from engine.probability_engine import ProbabilityEngine
    from engine.reliability_engine import ReliabilityEngine
    from engine.risk_engine import RiskEngine
    from services.prediction_service import PredictionService

    trace = RuntimeTrace(
        source_commit=source_commit,
        supported_root="services.prediction_service",
        root_authority_profile="UNKNOWN",
        synthetic_case_id="LEGACY_PREDICTION_SERVICE_MARKET_SELECTOR_V1",
    )
    service = object.__new__(PredictionService)
    service.analyzer = _SyntheticPredictionAnalyzer()
    service.probability = ProbabilityEngine()
    service.risk = RiskEngine()
    service.reliability = ReliabilityEngine()
    service.market = MarketSelector()

    with ExitStack() as stack:
        stack.enter_context(scoped_callable_checkpoint(
            service,
            "predict",
            trace=trace,
            module="services.prediction_service",
            qualname="PredictionService.predict",
            checkpoint_kind="ORCHESTRATION",
            authority_category="MODEL_ANALYSIS",
            notes=("analyzer_input_is_deterministic_synthetic_seed",),
        ))
        stack.enter_context(scoped_callable_checkpoint(
            service.probability,
            "calculate",
            trace=trace,
            module="engine.probability_engine",
            qualname="ProbabilityEngine.calculate",
            checkpoint_kind="SUPPORTING_LOGIC",
            authority_category="MODEL_ANALYSIS",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            service.risk,
            "evaluate",
            trace=trace,
            module="engine.risk_engine",
            qualname="RiskEngine.evaluate",
            checkpoint_kind="SUPPORTING_LOGIC",
            authority_category="MODEL_ANALYSIS",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            service.reliability,
            "evaluate",
            trace=trace,
            module="engine.reliability_engine",
            qualname="ReliabilityEngine.evaluate",
            checkpoint_kind="SUPPORTING_LOGIC",
            authority_category="MODEL_ANALYSIS",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            service.market,
            "select",
            trace=trace,
            module="engine.market_selector",
            qualname="MarketSelector.select",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="LEGACY_MARKET_SELECTION",
        ))
        result = service.predict({"synthetic": True})

    document = trace.to_dict(disposition="EXECUTED_DECISION_AUTHORITY")
    validate_trace_document(document)
    return document, {
        "recommended_market": result.recommended_market,
        "market_confidence": result.market_confidence,
        "ranked_market_count": len(result.ranked_markets),
        "prediction_snapshot": _prediction_snapshot(result),
    }


def _make_shadow_context_and_quotes():
    from domain import current_all_market_shadow_probability_settlement as prc
    from domain._current_shadow_price_records import _issue_shadow_exact_quote
    from domain._current_shadow_quote_binding import CurrentShadowPriceContext
    from domain.markets import MarketId, OutcomeId

    fixture = "FOTMOB:P05-RUNTIME-1"
    event = "sr:match:905001"
    a, b, c, d, e, f = (ch * 64 for ch in "abcdef")
    research_xg = prc.ResearchXGRates(
        calibrated_home=2.8,
        calibrated_away=0.4,
        sealed_prediction_sha256=a,
        history_prefix_identity=b,
        source_fixture_identity=fixture,
    )
    scan = prc.scan_fixture_all_markets(
        fixture_identity=fixture,
        research_xg=research_xg,
        total_goals_lines=(1.5, 2.5),
        asian_handicap_home_lines=(-0.5, 0.0),
        provider_semantic_by_market={market: "SUPPORTED" for market in MarketId},
    )
    context = object.__new__(CurrentShadowPriceContext)
    fields = {
        "fixture_identity": fixture,
        "provider_event_id": event,
        "evaluation_time": FIXED_NOW,
        "scan": scan,
        "prc_scan_sha256": c,
        "provider_registry": None,
        "provider_registry_sha256": d,
        "provider_inventory": None,
        "source_raw_sha256": a,
        "source_manifest_sha256": b,
        "source_inventory_sha256": c,
        "fixture_reconciliation_sha256": d,
        "current_mapping_rebind_sha256": e,
        "bridge_bundle_sha256": f,
        "source_context_policy_id": "P0.5_RUNTIME_SYNTHETIC_CONTEXT_V1",
        "_bridge_bundle": None,
        "_event_evidence": None,
        "_complete_current_history": None,
    }
    for key, value in fields.items():
        object.__setattr__(context, key, value)

    kickoff = FIXED_NOW + timedelta(hours=3)

    def quote(outcome: OutcomeId, odds: float, oid: str):
        return _issue_shadow_exact_quote(
            fixture_identity=fixture,
            provider_event_id=event,
            market_id=MarketId.MATCH_RESULT,
            outcome_id=outcome,
            line=None,
            provider_line=None,
            provider_market_id="1",
            provider_market_name="1X2",
            provider_specifier=None,
            provider_outcome_id=oid,
            provider_outcome_name=outcome.value,
            odds_raw=str(odds),
            decimal_odds=odds,
            observed_at=FIXED_NOW,
            kickoff_utc=kickoff,
            source_raw_sha256=a,
            source_manifest_sha256=b,
            source_inventory_sha256=c,
            provider_semantic_status="SUPPORTED",
            provider_registry_sha256=d,
            provider_observation_sha256=e,
            fixture_reconciliation_sha256=d,
            current_mapping_rebind_sha256=e,
            bridge_bundle_sha256=f,
            bookable=True,
        )

    quotes = (
        quote(OutcomeId.HOME, 1.45, "1"),
        quote(OutcomeId.DRAW, 5.0, "2"),
        quote(OutcomeId.AWAY, 10.0, "3"),
    )
    return context, quotes


def _make_portfolio_source_and_leg(bundle: Any, decision: Any):
    from domain import current_shadow_all_market_portfolio as portfolio
    from domain.markets import MARKET_REGISTRY

    if decision.selected_opportunity_id is None:
        raise RuntimeReachabilityError("synthetic current Shadow Router produced no selected opportunity")
    selected = next(
        item
        for item in decision.opportunities
        if item.opportunity_id == decision.selected_opportunity_id
    )
    result = selected.price_result
    if (
        selected.prediction_confidence is None
        or selected.prediction_confidence_method is None
        or selected.prediction_first_rank is None
        or selected.robust_net_expected_value is None
        or result.decimal_odds is None
        or result.quote_identity_sha256 is None
        or result.provider_event_id is None
        or result.source_raw_sha256 is None
        or result.source_manifest_sha256 is None
        or result.source_inventory_sha256 is None
        or result.provider_observation_sha256 is None
    ):
        raise RuntimeReachabilityError("synthetic selected Shadow opportunity lacks portfolio inputs")
    survival = selected.event_probability_floor
    if survival is None:
        raise RuntimeReachabilityError("synthetic scalar Shadow opportunity lacks survival floor")

    source = object.__new__(portfolio.ShadowPortfolioRouterInput)
    for key, value in {
        "price_all_bundle": bundle,
        "router_decision": decision,
        "price_all_bundle_sha256": bundle.canonical_sha256,
        "router_decision_sha256": decision.decision_sha256,
        "fixture_identity": bundle.fixture_identity,
        "provider_event_id": result.provider_event_id,
        "home_team": "Shadow Synthetic Home",
        "away_team": "Shadow Synthetic Away",
        "competition": "Synthetic Competition",
        "kickoff_utc": FIXED_NOW + timedelta(hours=3),
        "source_observed_at": FIXED_NOW - timedelta(seconds=20),
        "fixture_reconciliation_sha256": result.fixture_reconciliation_sha256,
        "source_raw_sha256": result.source_raw_sha256,
        "source_manifest_sha256": result.source_manifest_sha256,
        "source_inventory_sha256": result.source_inventory_sha256,
    }.items():
        object.__setattr__(source, key, value)

    canonical_line = "NONE" if result.line is None else float(result.line).hex()
    leg = portfolio.ShadowPortfolioLeg(
        leg_id=selected.opportunity_id,
        price_all_bundle_sha256=bundle.canonical_sha256,
        router_decision_sha256=decision.decision_sha256,
        selected_opportunity_id=selected.opportunity_id,
        fixture_identity=bundle.fixture_identity,
        provider_event_id=result.provider_event_id,
        home_team="Shadow Synthetic Home",
        away_team="Shadow Synthetic Away",
        competition="Synthetic Competition",
        kickoff_utc=FIXED_NOW + timedelta(hours=3),
        market_id=result.market_id,
        outcome_id=result.outcome_id,
        line=result.line,
        market_family=MARKET_REGISTRY[result.market_id].family,
        quote_identity_sha256=result.quote_identity_sha256,
        provider_market_id="1",
        provider_market_name="1X2",
        provider_specifier=None,
        provider_outcome_id="1",
        provider_outcome_name=result.outcome_id.value,
        decimal_odds=result.decimal_odds,
        source_raw_sha256=result.source_raw_sha256,
        source_manifest_sha256=result.source_manifest_sha256,
        source_inventory_sha256=result.source_inventory_sha256,
        provider_registry_sha256=result.provider_registry_sha256,
        provider_observation_sha256=result.provider_observation_sha256,
        fixture_reconciliation_sha256=result.fixture_reconciliation_sha256,
        prediction_confidence=selected.prediction_confidence,
        prediction_confidence_method=selected.prediction_confidence_method,
        prediction_first_rank=selected.prediction_first_rank,
        canonical_prediction_identity=(
            f"{result.market_id.value}|{result.outcome_id.value}|{canonical_line}"
        ),
        router_policy_id=decision.router_policy_id,
        portfolio_policy_id=portfolio.PORTFOLIO_POLICY_ID,
        selection_reason="P0.5_SYNTHETIC_SOURCE_ALIGNED_SELECTION",
        robust_net_expected_value=selected.robust_net_expected_value,
        robust_edge=selected.robust_edge,
        event_probability_floor=selected.event_probability_floor,
        survival_probability_floor=survival,
        router_quote_age_seconds=10.0,
        portfolio_quote_age_seconds=20.0,
        portfolio_kickoff_lead_seconds=3 * 3600.0,
        fragility_status=portfolio._fragility(
            selected.robust_net_expected_value,
            survival,
        ),
    )
    return source, leg


def _probe_current_shadow(source_commit: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    import argparse as _argparse

    from domain import current_shadow_all_market_portfolio as portfolio
    from domain import current_shadow_all_market_price_all as price_all
    from domain import current_shadow_all_market_router as router
    from domain import current_shadow_all_market_runner as runner
    from scripts import execute_current_shadow_daily as daily
    from scripts import execute_current_shadow_request as request

    trace = RuntimeTrace(
        source_commit=source_commit,
        supported_root="scripts.execute_current_shadow_request",
        root_authority_profile=profile,
        synthetic_case_id="CURRENT_SHADOW_SYNTHETIC_DECISION_CHAIN_V1",
    )
    context, quotes = _make_shadow_context_and_quotes()
    observations: dict[str, Any] = {}
    guard_calls: list[str] = []

    def forbidden_network(name: str):
        def guard(*_args: Any, **_kwargs: Any):
            guard_calls.append(name)
            raise RuntimeReachabilityError(f"forbidden P0.5 external boundary reached: {name}")
        return guard

    def synthetic_bound_worker(_args: Any) -> int:
        bundle = price_all.price_all_shadow_fixture(context)
        decision = router.route_shadow_price_results(bundle)
        source, leg = _make_portfolio_source_and_leg(bundle, decision)
        with ExitStack() as inner:
            inner.enter_context(_temporary_attribute(
                portfolio,
                "verify_shadow_portfolio_router_input",
                lambda value: value,
            ))
            inner.enter_context(_temporary_attribute(
                portfolio,
                "_build_leg",
                lambda value, now: leg,
            ))
            optimized = portfolio.optimize_shadow_portfolio(
                (source,),
                target_size=1,
                evaluation_time=FIXED_NOW,
            )
        observations.update({
            "router_status": decision.status.value,
            "portfolio_selected_count": len(optimized.selected_legs),
            "portfolio_shortfall": optimized.shortfall,
            "real_share_code_function_executed": False,
        })
        token = trace.begin(
            module="domain.current_shadow_all_market_share_code",
            qualname="create_verified_shadow_all_market_share_code",
            checkpoint_kind="TERMINUS",
            authority_category="NONE",
            notes=(
                "real_delivery_function_intentionally_not_executed",
                "synthetic_probe_terminates_before_provider_create_reload",
            ),
        )
        trace.finish(token)
        return 0

    args = _argparse.Namespace(
        target_size=1,
        fixture_scope=daily.SCOPE_TODAY,
        fixture_dates=None,
        output_dir=Path("artifacts/p0.5-synthetic-current-shadow"),
    )

    with ExitStack() as stack:
        # Actual supported request wrapper and actual daily wrapper execute.  Their
        # external worker is replaced by the deterministic decision worker above.
        stack.enter_context(scoped_callable_checkpoint(
            request,
            "_execute_worker",
            trace=trace,
            module="scripts.execute_current_shadow_request",
            qualname="_execute_worker",
            checkpoint_kind="ENTRYPOINT",
            authority_category="NONE",
            notes=("synthetic_only=true", "live_worker_boundary_replaced=true"),
        ))
        stack.enter_context(scoped_callable_checkpoint(
            daily,
            "_execute_worker",
            trace=trace,
            module="scripts.execute_current_shadow_daily",
            qualname="_execute_worker",
            checkpoint_kind="ORCHESTRATION",
            authority_category="NONE",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            price_all,
            "price_all_shadow_fixture",
            trace=trace,
            module="domain.current_shadow_all_market_price_all",
            qualname="price_all_shadow_fixture",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="PRICE_ALL",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            router,
            "route_shadow_price_results",
            trace=trace,
            module="domain.current_shadow_all_market_router",
            qualname="route_shadow_price_results",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="MARKET_ROUTING",
        ))
        stack.enter_context(scoped_callable_checkpoint(
            portfolio,
            "optimize_shadow_portfolio",
            trace=trace,
            module="domain.current_shadow_all_market_portfolio",
            qualname="optimize_shadow_portfolio",
            checkpoint_kind="DECISION_AUTHORITY",
            authority_category="PORTFOLIO_CONSTRUCTION",
        ))

        # Only replay/verifier and external boundaries are replaced.  Price-all,
        # Router and Portfolio algorithms above are not mocked.
        stack.enter_context(_temporary_attribute(
            price_all,
            "verify_current_shadow_price_context",
            lambda value: value,
        ))
        stack.enter_context(_temporary_attribute(
            price_all,
            "build_current_shadow_exact_quotes",
            lambda value: tuple(quotes),
        ))
        stack.enter_context(_temporary_attribute(
            router,
            "verify_shadow_price_all_bundle",
            lambda value: value,
        ))
        stack.enter_context(_temporary_attribute(
            daily.bound,
            "_execute_worker",
            synthetic_bound_worker,
        ))

        # Disable wrapper-installation machinery that is irrelevant to the
        # synthetic trace and would otherwise mutate process-global replay hooks.
        stack.enter_context(_temporary_attribute(
            request,
            "_install_reconciliation_compatibility",
            lambda: (object(), {}),
        ))
        stack.enter_context(_temporary_attribute(
            request,
            "_restore_reconciliation_compatibility",
            lambda *_args, **_kwargs: None,
        ))
        stack.enter_context(_temporary_attribute(request.xg_fallback, "install", lambda: object()))
        stack.enter_context(_temporary_attribute(request.xg_fallback, "restore", lambda *_args: None))
        stack.enter_context(_temporary_attribute(request, "_write_request_policy", lambda *_args: None))
        stack.enter_context(_temporary_attribute(request, "_write_xg_diagnostic", lambda *_args: True))

        stack.enter_context(_temporary_attribute(daily.identity_recovery, "install", lambda *_args, **_kwargs: object()))
        stack.enter_context(_temporary_attribute(daily.identity_recovery, "restore", lambda *_args, **_kwargs: None))
        stack.enter_context(_temporary_attribute(daily.quote_replay, "install", lambda: object()))
        stack.enter_context(_temporary_attribute(daily.quote_replay, "restore", lambda *_args: None))
        stack.enter_context(_temporary_attribute(daily.verification_reuse, "install", lambda *_args, **_kwargs: object()))
        stack.enter_context(_temporary_attribute(daily.verification_reuse, "restore", lambda *_args, **_kwargs: None))
        stack.enter_context(_temporary_attribute(daily.builder_audit_reuse, "install", lambda *_args, **_kwargs: object()))
        stack.enter_context(_temporary_attribute(daily.builder_audit_reuse, "restore", lambda *_args, **_kwargs: None))
        stack.enter_context(_temporary_attribute(daily.semantic_replay_reuse, "install", lambda *_args, **_kwargs: object()))
        stack.enter_context(_temporary_attribute(daily.semantic_replay_reuse, "restore", lambda *_args, **_kwargs: None))

        # Guards prove an accidental live path fails instead of silently touching
        # provider or delivery infrastructure.
        stack.enter_context(_temporary_attribute(
            runner.current_fotmob_source,
            "issue_current_shadow_fotmob_reviewed_source",
            forbidden_network("current_fotmob_source"),
        ))
        stack.enter_context(_temporary_attribute(
            runner.reconciliation,
            "capture_current_catalog_fanout_discovery",
            forbidden_network("sportybet_catalog_fanout"),
        ))
        stack.enter_context(_temporary_attribute(
            runner.share_module,
            "create_verified_shadow_all_market_share_code",
            forbidden_network("sportybet_create_reload"),
        ))

        result_code = request._execute_worker(args)

    if result_code != 0:
        raise RuntimeReachabilityError(
            f"synthetic Current Shadow request wrapper returned {result_code}"
        )
    if guard_calls:
        raise RuntimeReachabilityError(
            f"synthetic Current Shadow touched forbidden external boundaries: {guard_calls}"
        )

    document = trace.to_dict(disposition="EXECUTED_DECISION_AUTHORITY")
    validate_trace_document(document)
    observations.update({
        "actual_price_all_owner": "domain.current_shadow_all_market_price_all.price_all_shadow_fixture",
        "actual_router_owner": "domain.current_shadow_all_market_router.route_shadow_price_results",
        "actual_portfolio_owner": "domain.current_shadow_all_market_portfolio.optimize_shadow_portfolio",
        "delivery_owner_observed_but_not_executed": "domain.current_shadow_all_market_share_code.create_verified_shadow_all_market_share_code",
        "forbidden_external_boundary_call_count": len(guard_calls),
    })
    return document, observations


def _probe_restore_root(source_commit: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts import current_shadow_history_github_persistent_cache as cache
    from scripts import prime_current_shadow_history_github_cache as prime
    from scripts import restore_current_shadow_history_prime_artifact as restore

    trace = RuntimeTrace(
        source_commit=source_commit,
        supported_root="scripts.restore_current_shadow_history_prime_artifact",
        root_authority_profile=profile,
        synthetic_case_id="HISTORY_PRIME_RESTORE_SYNTHETIC_TRANSPORT_V1",
    )
    trusted = "a" * 40
    with tempfile.TemporaryDirectory(prefix="athena-p05-restore-") as temporary:
        root = Path(temporary)
        artifact_dir = root / "artifact"
        history_cache = artifact_dir / "history-cache"
        cache._persist(
            history_cache,
            "/repos/Thabearr/ATHENA/actions/artifacts/123/zip",
            b"p0.5-artifact-zip",
        )
        cache._persist(
            history_cache,
            "/repos/Thabearr/ATHENA/releases/assets/456",
            b"p0.5-release-asset",
        )
        entry_count, payload_bytes, inventory_sha = prime._cache_inventory(history_cache)
        receipt = {
            "schema_version": prime.SCHEMA_VERSION,
            "status": prime.STATUS,
            "exact_commit_sha": trusted,
            "captured_run_universe_count": 2,
            "cached_immutable_binary_entry_count": entry_count,
            "cached_immutable_binary_payload_bytes": payload_bytes,
            "cache_inventory_sha256": inventory_sha,
            "evidence_authority": False,
            "model_authority": False,
            "pricing_authority": False,
            "selection_authority": False,
            "execution_authority": False,
            "bet_authority": False,
            "wager_placed": False,
        }
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / restore.PRIME_RECEIPT_FILENAME).write_bytes(prime._canonical(receipt))
        destination = root / "restored"
        synthetic_args = SimpleNamespace(
            artifact_dir=artifact_dir,
            cache_dir=destination,
            expected_prime_commit_sha=trusted,
        )
        with ExitStack() as stack:
            stack.enter_context(scoped_callable_checkpoint(
                restore,
                "main",
                trace=trace,
                module="scripts.restore_current_shadow_history_prime_artifact",
                qualname="main",
                checkpoint_kind="ENTRYPOINT",
                authority_category="NONE",
                notes=("synthetic_transport_artifact_only",),
            ))
            stack.enter_context(scoped_callable_checkpoint(
                restore,
                "restore",
                trace=trace,
                module="scripts.restore_current_shadow_history_prime_artifact",
                qualname="restore",
                checkpoint_kind="SUPPORTING_LOGIC",
                authority_category="NONE",
            ))
            stack.enter_context(_temporary_attribute(restore, "_parse_args", lambda: synthetic_args))
            result_code = restore.main()
        if result_code != 0:
            raise RuntimeReachabilityError("synthetic history prime restore failed")
    document = trace.to_dict(disposition="NO_DECISION_AUTHORITY_REACHED")
    validate_trace_document(document)
    return document, {
        "transport_restore_executed": True,
        "market_decision_authority_reached": False,
        "network_acquisition_performed": False,
    }


def _probe_fresh_tick_root(source_commit: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts import run_fotmob_utc_native_xg_fresh_holdout_tick as tick

    trace = RuntimeTrace(
        source_commit=source_commit,
        supported_root="scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
        root_authority_profile=profile,
        synthetic_case_id="FRESH_HOLDOUT_FAIL_CLOSED_NO_NETWORK_V1",
    )
    with tempfile.TemporaryDirectory(prefix="athena-p05-fresh-tick-") as temporary:
        root = Path(temporary)
        bootstrap = root / "not-the-reviewed-bootstrap.ndjson"
        bootstrap.write_bytes(b"p0.5 intentionally wrong bootstrap")
        receipt = root / "receipt.json"
        with scoped_callable_checkpoint(
            tick,
            "main",
            trace=trace,
            module="scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
            qualname="main",
            checkpoint_kind="ENTRYPOINT",
            authority_category="NONE",
            notes=(
                "execute_live_network_flag_absent",
                "invalid_bootstrap_forces_fail_closed_before_collection",
            ),
        ):
            result_code = tick.main([
                "--scheduled-for", "2026-09-10T12:07:00Z",
                "--bootstrap-projection", str(bootstrap),
                "--durable-release-tag", "p0.5-synthetic-no-release",
                "--durable-asset-name", "p0.5-synthetic-no-asset.tar.gz",
                "--state-root", str(root / "state"),
                "--receipt-output", str(receipt),
            ])
        if result_code != 1:
            raise RuntimeReachabilityError(
                "fresh-holdout synthetic fail-closed probe unexpectedly succeeded"
            )
    document = trace.to_dict(disposition="NO_DECISION_AUTHORITY_REACHED")
    validate_trace_document(document)
    return document, {
        "fail_closed_before_collection": True,
        "network_acquisition_performed": False,
        "market_decision_authority_reached": False,
    }


def _probe_receipt_mirror_root(source_commit: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts import run_fotmob_fresh_holdout_release_receipt_mirror as entry

    trace = RuntimeTrace(
        source_commit=source_commit,
        supported_root="scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
        root_authority_profile=profile,
        synthetic_case_id="FRESH_HOLDOUT_RECEIPT_MIRROR_ENTRYPOINT_NO_NETWORK_V1",
    )
    original_download = entry.mirror._gh_download
    original_mirror_run = entry.mirror.mirror_run
    try:
        with ExitStack() as stack:
            stack.enter_context(scoped_callable_checkpoint(
                entry,
                "main",
                trace=trace,
                module="scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
                qualname="main",
                checkpoint_kind="ENTRYPOINT",
                authority_category="NONE",
                notes=("transport_downstream_replaced_before_any_github_call",),
            ))
            stack.enter_context(_temporary_attribute(entry.mirror, "main", lambda _argv=None: 0))
            result_code = entry.main([])
    finally:
        entry.mirror._gh_download = original_download
        entry.mirror.mirror_run = original_mirror_run
    if result_code != 0:
        raise RuntimeReachabilityError("synthetic receipt-mirror entrypoint failed")
    document = trace.to_dict(disposition="NO_DECISION_AUTHORITY_REACHED")
    validate_trace_document(document)
    return document, {
        "receipt_transport_entrypoint_executed": True,
        "github_transport_executed": False,
        "market_decision_authority_reached": False,
    }


def _probe_email_root(source_commit: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts import send_current_shadow_email as email

    trace = RuntimeTrace(
        source_commit=source_commit,
        supported_root="scripts.send_current_shadow_email",
        root_authority_profile=profile,
        synthetic_case_id="CURRENT_SHADOW_EMAIL_UNCONFIGURED_DELIVERY_V1",
    )
    with tempfile.TemporaryDirectory(prefix="athena-p05-email-") as temporary:
        root = Path(temporary)
        receipt = root / "run.json"
        delivery = root / "delivery.json"
        receipt.write_text(json.dumps({
            "dataset_name": email.EXPECTED_DATASET,
            "status": "RESEARCH_NO_CODE_NO_BET",
            "observed_at": "2026-09-10T12:00:00Z",
            "requested_target_size": 1,
            "selected_leg_count": 0,
            "shortfall": 1,
            "shareCode": None,
            "shareURL": None,
            "share_code_receipt": None,
            "final_selected_legs": [],
            "reasons": ["P0.5_SYNTHETIC_NO_CODE"],
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }, sort_keys=True), encoding="utf-8")

        def smtp_forbidden(*_args: Any, **_kwargs: Any):
            raise RuntimeReachabilityError("P0.5 email probe attempted SMTP")

        with ExitStack() as stack:
            stack.enter_context(_temporary_environment({
                "GMAIL_ADDRESS": None,
                "GMAIL_APP_PASSWORD": None,
                "RECIPIENT_EMAIL": None,
            }))
            stack.enter_context(_temporary_attribute(email.smtplib, "SMTP", smtp_forbidden))
            stack.enter_context(scoped_callable_checkpoint(
                email,
                "main",
                trace=trace,
                module="scripts.send_current_shadow_email",
                qualname="main",
                checkpoint_kind="ENTRYPOINT",
                authority_category="DELIVERY_ONLY",
                notes=("smtp_configuration_intentionally_absent",),
            ))
            stack.enter_context(scoped_callable_checkpoint(
                email,
                "send_receipt_email",
                trace=trace,
                module="scripts.send_current_shadow_email",
                qualname="send_receipt_email",
                checkpoint_kind="DELIVERY",
                authority_category="DELIVERY_ONLY",
            ))
            result_code = email.main([
                "--receipt", str(receipt),
                "--delivery-receipt", str(delivery),
            ])
        if result_code != 0:
            raise RuntimeReachabilityError("synthetic email delivery probe failed")
        delivered = json.loads(delivery.read_text(encoding="utf-8"))
        if delivered.get("status") != email.EMAIL_SKIPPED_UNCONFIGURED:
            raise RuntimeReachabilityError("synthetic email probe did not fail closed unconfigured")
    document = trace.to_dict(disposition="EXECUTED_DELIVERY_ONLY")
    validate_trace_document(document)
    return document, {
        "delivery_status": email.EMAIL_SKIPPED_UNCONFIGURED,
        "smtp_send_executed": False,
        "market_decision_authority_reached": False,
    }


def build_runtime_evidence(source_commit: str) -> dict[str, Any]:
    roots = _supported_roots()
    profiles = _root_profiles()
    traces: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}

    trace, observation = _probe_build_acca(source_commit, profiles["build_acca"])
    traces["build_acca"] = trace
    observations["build_acca"] = observation

    trace, observation = _probe_current_shadow(
        source_commit,
        profiles["scripts.execute_current_shadow_request"],
    )
    traces["scripts.execute_current_shadow_request"] = trace
    observations["scripts.execute_current_shadow_request"] = observation

    for root, probe in (
        (
            "scripts.restore_current_shadow_history_prime_artifact",
            _probe_restore_root,
        ),
        (
            "scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
            _probe_receipt_mirror_root,
        ),
        (
            "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
            _probe_fresh_tick_root,
        ),
        ("scripts.send_current_shadow_email", _probe_email_root),
    ):
        trace, observation = probe(source_commit, profiles[root])
        traces[root] = trace
        observations[root] = observation

    if set(traces) != set(roots):
        raise RuntimeReachabilityError("runtime evidence does not cover exact P0.2 supported roots")

    prediction_trace, prediction_observation = _probe_prediction_service(source_commit)
    legacy_cases = _legacy_cases()
    ordered_traces = [traces[root] for root in roots]
    ordered_observations = {root: observations[root] for root in roots}
    for document in ordered_traces:
        validate_trace_document(document)
    validate_trace_document(prediction_trace)

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "source_commit": source_commit,
        "p0_2_supported_roots": list(roots),
        "supported_root_traces": ordered_traces,
        "supported_root_observations": ordered_observations,
        "supplemental_legacy_prediction_service_trace": prediction_trace,
        "supplemental_legacy_prediction_service_observation": prediction_observation,
        "legacy_market_selection_problem_cases": legacy_cases,
        "measurement_semantics": {
            "module_import_is_execution": False,
            "missing_checkpoint_means_wrapped_callable_not_executed_in_probe": True,
            "supporting_logic_is_automatically_decision_authority": False,
            "live_external_boundaries_are_permitted": False,
        },
        "cleanup": {
            "disposition_changes_authorized": False,
            "delete_authority_granted": False,
            "all_reviewed_cleanup_dispositions_required": "UNCLASSIFIED",
        },
        "safety": {
            "provider_network_acquisition_performed": False,
            "current_shadow_live_triggered": False,
            "fresh_holdout_live_triggered": False,
            "real_sportybet_create_reload_performed": False,
            "smtp_send_performed": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "stake_submitted": False,
            "wager_placed": False,
            "production_authority_changed": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref",
        default=BASELINE_MAIN,
        help=(
            "Git commit identity the runtime evidence describes. P0.5 changes no "
            "business-path semantics, so the committed baseline artifact targets "
            "the exact pre-P0.5 main by default."
        ),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_commit = _resolve_ref(args.ref)
    payload = build_runtime_evidence(source_commit)
    raw = canonical_json_bytes(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(f"wrote {args.output} ({len(raw)} bytes) for {source_commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
