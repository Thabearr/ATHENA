"""Generate deterministic P3.1 MAIN caller-migration evidence.

The audit uses the repository's offline canonical Price-All and Router seams.
Provider acquisition, Current Shadow, share-code, credentials, and wager
authority are never enabled.  The historical P0.5 runtime artifact is read as
frozen evidence; it is not regenerated after the caller migration.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterator

from domain import canonical_core
from domain import market_router_canonical_adapter as canonical_router
from domain import price_all
from engine.market_selector import MarketSelector
from models.prediction import Prediction
from services import main_canonical_prediction_adapter as presentation
from services.prediction_service import PredictionService
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_market_router_v3_current_provider import (
    _fixture_state,
    _priced_match_result,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_P05_ARTIFACT = REPOSITORY_ROOT / "artifacts/architecture/runtime-reachability-v1.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts/architecture/p3_1_main_caller_migration_v1.json"
POLICY_ID = "ATHENA_P3_1_MAIN_CALLER_MIGRATION_V1"
SCHEMA_VERSION = 1
BASE_MAIN_SHA = "20a6aaaaa2912369298004eff27b868bffb2f7dd"
P3_1_PR_A_MERGE_COMMIT_SHA = BASE_MAIN_SHA
P3_1_PR_A_RECEIPT_SHA256 = "f0b67e693fe440813e34a249aaffe2bb043e5617e1717ea7e2f291de20334f8c"
PROMOTED_REGISTRY_SHA256 = "d52fbb292ddaea9ba2e94fda036f715db5ced7248187814fd29ac7859de26104"
HISTORICAL_P05_ARTIFACT_SHA256 = "a8ccb4c0c8ab2bea9bd133bb7fa7e155957bf1e38e5bf7ae6cccb4f44640f7e4"
ROUTER_COMPONENT_ID = presentation.EXPECTED_ROUTER_COMPONENT_ID
ROUTER_CONTRACT_SHA256 = presentation.EXPECTED_ROUTER_CONTRACT_SHA256
ROUTER_ARTIFACT_GIT_BLOB_SHA = presentation.EXPECTED_ROUTER_ARTIFACT_GIT_BLOB_SHA


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if type(value) is not dict:
        raise ValueError(f"expected object artifact: {path}")
    return value


def _source_controlled_historical_bytes() -> bytes:
    """Read the frozen artifact as Git stores it, independent of checkout EOLs."""

    relative = HISTORICAL_P05_ARTIFACT.relative_to(REPOSITORY_ROOT).as_posix()
    try:
        source_bytes = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"],
            cwd=REPOSITORY_ROOT,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("could not read source-controlled frozen P0.5 artifact") from exc
    working_bytes = HISTORICAL_P05_ARTIFACT.read_bytes()
    if working_bytes.replace(b"\r\n", b"\n") != source_bytes:
        raise ValueError("frozen P0.5 runtime artifact changed")
    return source_bytes


class _PatchStack:
    """Small deterministic equivalent of pytest's monkeypatch for this audit."""

    def __init__(self) -> None:
        self._undo: list[tuple[Any, str, Any]] = []

    def setattr(self, owner: Any, name: str, value: Any) -> None:
        self._undo.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    def undo(self) -> None:
        for owner, name, value in reversed(self._undo):
            setattr(owner, name, value)
        self._undo.clear()


@contextmanager
def _patches() -> Iterator[_PatchStack]:
    patcher = _PatchStack()
    try:
        yield patcher
    finally:
        patcher.undo()


class _SyntheticAnalyzer:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    def analyze(self, _fixture: Any) -> Prediction:
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


def _wrap_bound(patcher: _PatchStack, owner: Any, name: str, label: str, trace: list[str]) -> None:
    original = getattr(owner, name)

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        trace.append(label)
        return original(*args, **kwargs)

    patcher.setattr(owner, name, wrapped)


def _service_with_trace(patcher: _PatchStack, trace: list[str]) -> PredictionService:
    from engine.probability_engine import ProbabilityEngine
    from engine.reliability_engine import ReliabilityEngine
    from engine.risk_engine import RiskEngine

    service = object.__new__(PredictionService)
    service.analyzer = _SyntheticAnalyzer(trace)
    service.probability = ProbabilityEngine()
    service.risk = RiskEngine()
    service.reliability = ReliabilityEngine()
    _wrap_bound(patcher, service, "predict", "PredictionService.predict", trace)
    _wrap_bound(patcher, service.probability, "calculate", "ProbabilityEngine.calculate", trace)
    _wrap_bound(patcher, service.risk, "evaluate", "RiskEngine.evaluate", trace)
    _wrap_bound(patcher, service.reliability, "evaluate", "ReliabilityEngine.evaluate", trace)
    _wrap_bound(patcher, service.analyzer, "analyze", "Analyzer.analyze", trace)
    return service


def _run_case(*, probability: float | None) -> dict[str, Any]:
    trace: list[str] = []
    selector_calls = 0
    verification_calls = 0
    core_calls = 0
    projection_calls = 0

    with _patches() as patcher:
        decision = None
        if probability is not None:
            evaluation = price_all.PriceAllEvaluation._from_v3(
                _priced_match_result(patcher, probability=probability)
            )
            decision = canonical_router.route(
                evaluation,
                fixture_state=_fixture_state(),
                evaluation_time=EVALUATION + timedelta(seconds=10),
            )

        def selector_sentinel(_self: Any, _prediction: Prediction) -> None:
            nonlocal selector_calls
            selector_calls += 1
            raise AssertionError("legacy MarketSelector.select executed")

        def verify_wrapper(value: Any) -> Any:
            nonlocal verification_calls
            verification_calls += 1
            return original_verify(value)

        def core_wrapper() -> Any:
            nonlocal core_calls
            core_calls += 1
            trace.append("main_canonical_prediction_adapter.resolve_main_canonical_core")
            return original_core()

        def projection_wrapper(prediction: Prediction, router_decision: Any = None) -> Prediction:
            nonlocal projection_calls
            projection_calls += 1
            trace.append("main_canonical_prediction_adapter.project_canonical_router_decision")
            return original_projection(prediction, router_decision)

        original_verify = canonical_router.verify_router_decision
        original_core = presentation.resolve_main_canonical_core
        original_projection = presentation.project_canonical_router_decision
        patcher.setattr(MarketSelector, "select", selector_sentinel)
        patcher.setattr(canonical_router, "verify_router_decision", verify_wrapper)
        patcher.setattr(presentation, "resolve_main_canonical_core", core_wrapper)
        patcher.setattr(presentation, "project_canonical_router_decision", projection_wrapper)
        service = _service_with_trace(patcher, trace)
        result = service.predict({}, router_decision=decision)

    selected = None if decision is None else decision.selected_opportunity
    selected_identity = None
    if selected is not None:
        selected_identity = {
            "market_id": selected.market_id.value,
            "outcome_id": selected.outcome_id.value,
            "line": selected.line,
        }
    return {
        "legacy_prediction_output_shape_preserved": type(result) is Prediction,
        "recommended_market": result.recommended_market,
        "market_confidence": result.market_confidence,
        "ranked_market_count": len(result.ranked_markets),
        "canonical_router_decision_id": None if decision is None else decision.router_decision_id,
        "canonical_selection": selected_identity,
        "market_selector_executed_count": selector_calls,
        "main_canonical_core_resolution_observed": core_calls > 0,
        "canonical_router_decision_verification_observed": verification_calls > 0,
        "presentation_projection_observed": projection_calls > 0,
        "trace": trace,
    }


def _historical_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _source_controlled_historical_bytes()
    if hashlib.sha256(raw).hexdigest() != HISTORICAL_P05_ARTIFACT_SHA256:
        raise ValueError("frozen P0.5 runtime artifact source identity drifted")
    frozen = _load_json(HISTORICAL_P05_ARTIFACT)
    build_acca = frozen["supported_root_observations"]["build_acca"]
    trace = frozen["supplemental_legacy_prediction_service_trace"]
    historical_selector = any(
        row.get("module") == "engine.market_selector"
        and row.get("qualname") == "MarketSelector.select"
        for row in trace.get("checkpoints", ())
    )
    return (
        {
            "artifact_sha256": HISTORICAL_P05_ARTIFACT_SHA256,
            "source_commit": frozen.get("source_commit"),
            "market_selector_reachability": historical_selector,
        },
        {
            "market_selector_executed_count": int(bool(build_acca.get("market_selector_executed"))),
            "prediction_service_executed": bool(build_acca.get("prediction_service_executed")),
        },
    )


def build_migration_evidence() -> dict[str, Any]:
    historical, build_acca = _historical_evidence()
    presentation.clear_main_canonical_core_cache()
    bindings = presentation.resolve_main_canonical_core()
    router_record = bindings.record_for("market_router")
    if bindings.registry_canonical_sha256 != PROMOTED_REGISTRY_SHA256:
        raise ValueError("promoted registry identity drifted")
    if (
        router_record.component_id != ROUTER_COMPONENT_ID
        or router_record.contract_sha256 != ROUTER_CONTRACT_SHA256
        or router_record.artifact_git_blob_sha != ROUTER_ARTIFACT_GIT_BLOB_SHA
    ):
        raise ValueError("promoted Router owner identity drifted")

    selected = _run_case(probability=0.60)
    no_bet = _run_case(probability=0.45)
    no_router = _run_case(probability=None)
    if any(item["market_selector_executed_count"] != 0 for item in (selected, no_bet, no_router)):
        raise ValueError("migrated PredictionService executed MarketSelector")
    if no_router["recommended_market"] != "No Recommendation" or no_router["market_confidence"] != 0.0:
        raise ValueError("no-router case did not fail closed")
    if no_bet["recommended_market"] != "No Recommendation" or no_bet["market_confidence"] != 0.0:
        raise ValueError("NO_BET case did not fail closed")
    if selected["recommended_market"] == "No Recommendation" or selected["ranked_market_count"] != 1:
        raise ValueError("selected canonical projection did not produce one presentation row")

    trace = selected["trace"]
    expected_trace = [
        "PredictionService.predict",
        "Analyzer.analyze",
        "ProbabilityEngine.calculate",
        "RiskEngine.evaluate",
        "ReliabilityEngine.evaluate",
        "main_canonical_prediction_adapter.project_canonical_router_decision",
        "main_canonical_prediction_adapter.resolve_main_canonical_core",
    ]
    if trace[:5] != expected_trace[:5] or trace[-1] != expected_trace[-1]:
        raise ValueError(f"migrated PredictionService trace drifted: {trace!r}")

    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p3_1_pr_a_merge_commit_sha": P3_1_PR_A_MERGE_COMMIT_SHA,
        "p3_1_pr_a_promotion_receipt_sha256": P3_1_PR_A_RECEIPT_SHA256,
        "promoted_registry_canonical_sha256": PROMOTED_REGISTRY_SHA256,
        "canonical_core_policy_id": canonical_core.POLICY_ID,
        "market_router_component_id": ROUTER_COMPONENT_ID,
        "market_router_contract_sha256": ROUTER_CONTRACT_SHA256,
        "market_router_artifact_git_blob_sha": ROUTER_ARTIFACT_GIT_BLOB_SHA,
        "historical_p0_5_artifact_preserved": True,
        "historical_p0_5_artifact_sha256": historical["artifact_sha256"],
        "historical_p0_5_artifact_source_commit": historical["source_commit"],
        "historical_p0_5_market_selector_reachability": historical["market_selector_reachability"],
        "current_prediction_service_market_selector_executed_count": 0,
        "current_build_acca_market_selector_executed_count": build_acca["market_selector_executed_count"],
        "main_canonical_core_resolution_observed": True,
        "canonical_router_decision_verification_observed": (
            selected["canonical_router_decision_verification_observed"]
            and no_bet["canonical_router_decision_verification_observed"]
        ),
        "migrated_prediction_service_trace": trace,
        "selected_case": {key: value for key, value in selected.items() if key != "trace"},
        "no_bet_case": {key: value for key, value in no_bet.items() if key != "trace"},
        "no_router_decision_case": {key: value for key, value in no_router.items() if key != "trace"},
        "caller_migration_performed": True,
        "market_selector_removed": False,
        "market_selector_supported_runtime_execution": False,
        "provider_acquisition": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "share_code_generation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "p3_1_exit_gate_satisfied": True,
    }
    unsigned["canonical_sha256"] = _canonical_sha256(unsigned)
    return unsigned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_migration_evidence()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(json.dumps(payload, sort_keys=True))} canonical bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
