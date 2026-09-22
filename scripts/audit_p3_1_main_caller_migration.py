"""Verify the frozen deterministic P3.1 MAIN caller-migration evidence.

This receipt records the P3.1 checkpoint and must not be regenerated from the
current registry after P3.3's source/module rebind. Provider acquisition,
Current Shadow, share-code, credentials, and wager authority are not enabled.
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
    """Return the verified frozen P3.1 receipt; never rebuild it from current state."""

    return load_historical_migration_evidence()


def load_historical_migration_evidence() -> dict[str, Any]:
    """Load and validate the P3.1 checkpoint receipt without consulting live authority."""

    payload = _load_json(DEFAULT_OUTPUT)
    canonical_sha = payload.get("canonical_sha256")
    unsigned = dict(payload)
    unsigned.pop("canonical_sha256", None)
    if _canonical_sha256(unsigned) != canonical_sha:
        raise ValueError("frozen P3.1 migration receipt canonical hash drifted")
    if (
        canonical_sha != "f1fae3ed54c8afc632923156268bc4e70b748eb1ce9a8c3f1c822c965050a875"
        or payload.get("repository_base_main_sha") != BASE_MAIN_SHA
        or payload.get("p3_1_pr_a_merge_commit_sha") != P3_1_PR_A_MERGE_COMMIT_SHA
        or payload.get("p3_1_pr_a_promotion_receipt_sha256") != P3_1_PR_A_RECEIPT_SHA256
        or payload.get("promoted_registry_canonical_sha256") != PROMOTED_REGISTRY_SHA256
        or payload.get("market_router_component_id") != "domain.market_router_canonical_adapter"
        or payload.get("market_router_artifact_git_blob_sha")
        != "3011b65fcd62e5ae91fcede967b8cba4f85cdda7"
    ):
        raise ValueError("frozen P3.1 migration receipt identity drifted")
    if payload.get("p3_1_exit_gate_satisfied") is not True:
        raise ValueError("frozen P3.1 migration receipt does not record its historical gate")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    payload = load_historical_migration_evidence()
    print(f"verified frozen P3.1 migration receipt {payload['canonical_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
