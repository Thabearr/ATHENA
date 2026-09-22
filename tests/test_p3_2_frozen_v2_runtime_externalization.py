from __future__ import annotations

import hashlib
import json
import math
import ast
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from domain import market_router_v2_direct_provider as frozen_router
from domain import portfolio_optimizer_v2_direct_provider as frozen_portfolio
from domain import price_all_v2_direct_provider as frozen_price_all
from domain._accumulator_optimizer_contracts import FragilityStatus
from domain._market_router_contracts import (
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_REVIEWED_CONTEXT_COMPLETENESS,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
)
from domain._market_router_v2_contracts import (
    calculate_market_router_v2_contract_sha256,
)
from domain._portfolio_optimizer_v2_direct_provider_contracts import (
    calculate_portfolio_optimizer_v2_contract_sha256,
)
from domain._price_all_contracts import SettlementState
from domain import (
    _market_router_v2_contracts as router_contracts,
    _portfolio_optimizer_v2_direct_provider_contracts as portfolio_contracts,
    _price_all_v2_direct_provider_contracts as price_contracts,
    market_router_canonical_adapter,
    market_router_v3_current_provider,
    portfolio_optimizer,
    portfolio_optimizer_v3_current_provider,
    price_all,
    price_all_v3_current_provider,
)
from domain.markets import MarketId, OutcomeId


ROOT = Path(__file__).resolve().parents[1]
VECTOR_PATH = ROOT / "tests/fixtures/architecture/p3_2_frozen_v2_policy_vectors_v1.json"
POLICY_ID = "ATHENA_P3_2_FROZEN_V2_POLICY_VECTORS_V1"
BASE_MAIN_SHA = "e79322c57dd9d46789c67de8c7425fa59c8640c1"


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _settlement_candidate(
    market: MarketId,
    outcome: OutcomeId,
    line: float | None,
    probabilities: dict[str, float],
    *,
    selection_outcome: str | None = None,
) -> SimpleNamespace:
    unit = {"selection_outcome": selection_outcome} if selection_outcome else {}
    return SimpleNamespace(
        market_id=market,
        outcome_id=outcome,
        line=line,
        probability_map=MappingProxyType(dict(probabilities)),
        calibration_unit=tuple(sorted(unit.items())),
    )


def _settlement_case(
    case_id: str,
    market: MarketId,
    outcome: OutcomeId,
    line: float | None,
    probabilities: dict[str, float],
    odds: float,
    *,
    selection_outcome: str | None = None,
) -> dict[str, object]:
    candidate = _settlement_candidate(
        market, outcome, line, probabilities, selection_outcome=selection_outcome
    )
    record: dict[str, object] = {
        "case_id": case_id,
        "market_id": market.value,
        "outcome_id": outcome.value,
        "line": line,
        "probabilities": dict(sorted(probabilities.items())),
        "selection_outcome": selection_outcome,
        "odds": odds,
    }
    try:
        returns, ev = frozen_price_all._settlement_ev(candidate, odds)
    except frozen_price_all.PriceAllV2DirectProviderError as exc:
        record["error"] = str(exc)
    else:
        record["settlement_returns"] = [list(item) for item in returns]
        record["expected_value"] = ev
    return record


def build_frozen_v2_policy_vectors() -> dict[str, object]:
    settlement_cases = [
        _settlement_case(
            "ordinary_match_result_partition",
            MarketId.MATCH_RESULT,
            OutcomeId.HOME,
            None,
            {"HOME": 0.55, "DRAW": 0.25, "AWAY": 0.20},
            2.0,
        ),
        _settlement_case(
            "ordinary_btts_yes_partition",
            MarketId.BTTS,
            OutcomeId.YES,
            None,
            {"YES": 0.62, "NO": 0.38},
            1.9,
        ),
        _settlement_case(
            "ordinary_btts_no_partition",
            MarketId.BTTS,
            OutcomeId.NO,
            None,
            {"YES": 0.62, "NO": 0.38},
            2.1,
        ),
        _settlement_case(
            "selection_specific_yes_no_unit",
            MarketId.DOUBLE_CHANCE,
            OutcomeId.HOME_OR_DRAW,
            None,
            {"YES": 0.73, "NO": 0.27},
            1.55,
            selection_outcome="HOME_OR_DRAW",
        ),
        _settlement_case(
            "draw_no_bet_full_settlement",
            MarketId.DRAW_NO_BET,
            OutcomeId.HOME,
            None,
            {"WIN": 0.50, "PUSH": 0.20, "LOSS": 0.30},
            2.1,
        ),
        _settlement_case(
            "asian_handicap_five_components",
            MarketId.ASIAN_HANDICAP,
            OutcomeId.HOME,
            0.25,
            {"WIN": 0.35, "HALF_WIN": 0.15, "PUSH": 0.20, "HALF_LOSS": 0.10, "LOSS": 0.20},
            2.0,
        ),
        _settlement_case(
            "total_goals_integer_line",
            MarketId.TOTAL_GOALS,
            OutcomeId.OVER,
            3.0,
            {"WIN": 0.30, "PUSH": 0.20, "LOSS": 0.50},
            2.0,
        ),
        _settlement_case(
            "total_goals_half_line",
            MarketId.TOTAL_GOALS,
            OutcomeId.UNDER,
            2.5,
            {"WIN": 0.55, "LOSS": 0.45},
            1.8,
        ),
        _settlement_case(
            "total_goals_quarter_line",
            MarketId.TOTAL_GOALS,
            OutcomeId.OVER,
            2.25,
            {"WIN": 0.30, "HALF_WIN": 0.15, "PUSH": 0.15, "HALF_LOSS": 0.10, "LOSS": 0.30},
            1.95,
        ),
        _settlement_case(
            "incomplete_ordinary_distribution",
            MarketId.MATCH_RESULT,
            OutcomeId.HOME,
            None,
            {"HOME": 0.60},
            2.0,
        ),
    ]

    below_ev = math.nextafter(
        frozen_portfolio.MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE, -math.inf
    )
    above_ev = math.nextafter(
        frozen_portfolio.MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE, math.inf
    )
    below_survival = math.nextafter(
        frozen_portfolio.MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE, -math.inf
    )
    above_survival = math.nextafter(
        frozen_portfolio.MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE, math.inf
    )
    ev_values = (below_ev, frozen_portfolio.MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE, above_ev)
    survival_values = (below_survival, frozen_portfolio.MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE, above_survival)
    fragility_cases = []
    for robust_ev in ev_values:
        for survival in survival_values:
            fragility_cases.append(
                {
                    "robust_ev": robust_ev,
                    "survival": survival,
                    "classification": frozen_portfolio._fragility(robust_ev, survival).value,
                }
            )

    policy = {
        "policy_id": POLICY_ID,
        "schema_version": 1,
        "source_main_sha": BASE_MAIN_SHA,
        "source_modules": [
            "domain.price_all_v2_direct_provider",
            "domain.market_router_v2_direct_provider",
            "domain.portfolio_optimizer_v2_direct_provider",
        ],
        "price_all": {
            "contract_sha256": frozen_price_all.calculate_price_all_v2_contract_sha256(),
            "settlement_cases": settlement_cases,
        },
        "router": {
            "contract_sha256": calculate_market_router_v2_contract_sha256(),
            "requires_ordinary_fair_market_ids": sorted(
                item.value for item in frozen_router._REQUIRES_ORDINARY_FAIR
            ),
            "blocked_specialist_market_ids": sorted(
                item.value for item in frozen_router._BLOCKED_SPECIALISTS
            ),
            "thresholds": {
                "minimum_event_probability": MINIMUM_EVENT_PROBABILITY,
                "minimum_net_expected_value": MINIMUM_NET_EXPECTED_VALUE,
                "minimum_robust_net_expected_value": MINIMUM_ROBUST_NET_EXPECTED_VALUE,
                "minimum_robust_edge": MINIMUM_ROBUST_EDGE,
                "minimum_reviewed_context_completeness": MINIMUM_REVIEWED_CONTEXT_COMPLETENESS,
            },
        },
        "portfolio": {
            "contract_sha256": calculate_portfolio_optimizer_v2_contract_sha256(),
            "dnb_settlement_components": sorted(frozen_portfolio._DNB_COMPONENTS),
            "asian_handicap_settlement_components": sorted(frozen_portfolio._AH_COMPONENTS),
            "fragility_thresholds": {
                "minimum_robust_net_expected_value_for_non_fragile": frozen_portfolio.MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE,
                "minimum_survival_floor_for_non_fragile": frozen_portfolio.MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE,
                "comparison": "STRICTLY_BELOW",
            },
            "fragility_cases": fragility_cases,
            "fragility_status_values": sorted(item.value for item in FragilityStatus),
        },
    }
    policy["canonical_sha256"] = _canonical_sha256(policy)
    return policy


def write_base_policy_vectors() -> str:
    value = build_frozen_v2_policy_vectors()
    VECTOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    VECTOR_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return value["canonical_sha256"]


def _load_frozen_vectors() -> dict[str, object]:
    value = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    expected = value["canonical_sha256"]
    unsigned = dict(value)
    del unsigned["canonical_sha256"]
    assert _canonical_sha256(unsigned) == expected
    return value


def _candidate_from_vector(case: dict[str, object]) -> SimpleNamespace:
    return _settlement_candidate(
        MarketId(case["market_id"]),
        OutcomeId(case["outcome_id"]),
        case["line"],
        case["probabilities"],
        selection_outcome=case["selection_outcome"],
    )


def _domain_module_path(module_name: str) -> Path | None:
    if not module_name.startswith("domain."):
        return None
    base = ROOT.joinpath(*module_name.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    init = base / "__init__.py"
    return init if init.is_file() else None


def _reachable_domain_imports(roots: tuple[str, ...]) -> tuple[set[str], dict[str, set[str]]]:
    pending = list(roots)
    reached: set[str] = set()
    edges: dict[str, set[str]] = {}
    while pending:
        module_name = pending.pop()
        if module_name in reached:
            continue
        path = _domain_module_path(module_name)
        if path is None:
            continue
        reached.add(module_name)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        children: set[str] = set()
        for node in ast.walk(tree):
            candidates: set[str] = set()
            if isinstance(node, ast.Import):
                candidates.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    candidates.add(node.module)
                    if node.module == "domain":
                        candidates.update(f"domain.{alias.name}" for alias in node.names)
                    else:
                        candidates.update(
                            f"{node.module}.{alias.name}"
                            for alias in node.names
                            if _domain_module_path(f"{node.module}.{alias.name}")
                        )
                elif node.level and node.module:
                    package_parts = module_name.rsplit(".", 1)[0].split(".")
                    prefix_parts = package_parts[: len(package_parts) - node.level + 1]
                    relative = ".".join(prefix_parts + node.module.split("."))
                    candidates.add(relative)
            for candidate in candidates:
                if _domain_module_path(candidate):
                    children.add(candidate)
        edges[module_name] = children
        pending.extend(sorted(children - reached))
    return reached, edges


def test_frozen_price_settlement_vectors_match_v2_and_narrow_contract_exactly():
    vectors = _load_frozen_vectors()["price_all"]
    assert vectors["contract_sha256"] == frozen_price_all.EXPECTED_CONTRACT_SHA256
    for row in vectors["settlement_cases"]:
        candidate = _candidate_from_vector(row)
        try:
            old_result = frozen_price_all._settlement_ev(candidate, row["odds"])
        except frozen_price_all.PriceAllV2DirectProviderError as old_error:
            assert row["error"] == str(old_error)
            with pytest.raises(price_contracts.PriceAllV2ContractError) as new_error:
                price_contracts.settlement_ev(candidate, row["odds"])
            assert str(new_error.value) == str(old_error)
        else:
            new_result = price_contracts.settlement_ev(candidate, row["odds"])
            assert new_result == old_result
            assert [list(item) for item in new_result[0]] == row["settlement_returns"]
            assert new_result[1] == row["expected_value"]


def test_frozen_router_and_portfolio_policy_vectors_match_runtime_and_contracts():
    vectors = _load_frozen_vectors()
    router_vectors = vectors["router"]
    assert router_vectors["contract_sha256"] == router_contracts.EXPECTED_CONTRACT_SHA256
    assert router_contracts.calculate_market_router_v2_contract_sha256() == router_vectors["contract_sha256"]
    assert router_contracts.REQUIRES_ORDINARY_FAIR == frozen_router._REQUIRES_ORDINARY_FAIR
    assert router_contracts.BLOCKED_SPECIALISTS == frozen_router._BLOCKED_SPECIALISTS
    assert router_contracts.MINIMUM_EVENT_PROBABILITY == frozen_router.MINIMUM_EVENT_PROBABILITY
    assert router_contracts.MINIMUM_NET_EXPECTED_VALUE == frozen_router.MINIMUM_NET_EXPECTED_VALUE
    assert router_contracts.MINIMUM_ROBUST_NET_EXPECTED_VALUE == frozen_router.MINIMUM_ROBUST_NET_EXPECTED_VALUE
    assert router_contracts.MINIMUM_ROBUST_EDGE == frozen_router.MINIMUM_ROBUST_EDGE
    assert sorted(item.value for item in router_contracts.REQUIRES_ORDINARY_FAIR) == router_vectors["requires_ordinary_fair_market_ids"]
    assert sorted(item.value for item in router_contracts.BLOCKED_SPECIALISTS) == router_vectors["blocked_specialist_market_ids"]
    assert router_vectors["thresholds"] == {
        "minimum_event_probability": MINIMUM_EVENT_PROBABILITY,
        "minimum_net_expected_value": MINIMUM_NET_EXPECTED_VALUE,
        "minimum_robust_net_expected_value": MINIMUM_ROBUST_NET_EXPECTED_VALUE,
        "minimum_robust_edge": MINIMUM_ROBUST_EDGE,
        "minimum_reviewed_context_completeness": MINIMUM_REVIEWED_CONTEXT_COMPLETENESS,
    }

    portfolio_vectors = vectors["portfolio"]
    assert portfolio_vectors["contract_sha256"] == portfolio_contracts.EXPECTED_CONTRACT_SHA256
    assert portfolio_contracts.calculate_portfolio_optimizer_v2_contract_sha256() == portfolio_vectors["contract_sha256"]
    assert portfolio_contracts.DNB_SETTLEMENT_COMPONENTS == frozen_portfolio._DNB_COMPONENTS
    assert portfolio_contracts.ASIAN_HANDICAP_SETTLEMENT_COMPONENTS == frozen_portfolio._AH_COMPONENTS
    assert portfolio_vectors["fragility_thresholds"]["minimum_robust_net_expected_value_for_non_fragile"] == frozen_portfolio.MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE
    assert portfolio_vectors["fragility_thresholds"]["minimum_survival_floor_for_non_fragile"] == frozen_portfolio.MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE
    for case in portfolio_vectors["fragility_cases"]:
        expected = frozen_portfolio._fragility(case["robust_ev"], case["survival"])
        actual = portfolio_contracts.classify_frozen_fragility(case["robust_ev"], case["survival"])
        assert actual is expected
        assert actual.value == case["classification"]


def test_canonical_transitive_ast_import_closure_has_no_frozen_runtime_v2():
    roots = (
        "domain.price_all",
        "domain.market_router",
        "domain.portfolio_optimizer",
    )
    forbidden = {
        "domain.price_all_v2_direct_provider",
        "domain.market_router_v2_direct_provider",
        "domain.portfolio_optimizer_v2_direct_provider",
    }
    reached, _ = _reachable_domain_imports(roots)
    assert reached.isdisjoint(forbidden)
    assert {
        "domain._price_all_current_provider",
        "domain._market_router_current_provider",
        "domain._portfolio_optimizer_current_provider",
    } <= reached
    assert reached.isdisjoint(
        {
            "domain.price_all_v3_current_provider",
            "domain.market_router_v3_current_provider",
            "domain.portfolio_optimizer_v3_current_provider",
            "domain.market_router_canonical_adapter",
        }
    )


def test_fresh_process_canonical_validation_and_offline_replay_never_load_v2_runtime():
    code = r'''\
from datetime import timedelta
import sys
from pytest import MonkeyPatch
from domain import price_all, market_router_canonical_adapter as router, portfolio_optimizer as portfolio
from domain import portfolio_optimizer_v3_current_provider as portfolio_v3
from domain.canonical_core import resolve_canonical_core
from domain.run_contracts import AuthorityManifest
from domain.price_all import validate_price_all_contract
from domain.market_router_canonical_adapter import validate_canonical_market_router_contract
from domain.portfolio_optimizer import validate_portfolio_contract
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_market_router_v3_current_provider import _fixture_state, _priced_match_result
from tests.test_portfolio_optimizer_v3_current_provider import _input as portfolio_input

for validate in (validate_price_all_contract, validate_canonical_market_router_contract, validate_portfolio_contract):
    validate()
for profile in ("MAIN", "SHADOW"):
    manifest = AuthorityManifest(
        authority_profile=profile,
        mode="p3_2_import_graph_audit",
        provider_acquisition=False,
        share_code_generation=False,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )
    resolve_canonical_core(
        manifest, regime_id="CURRENT_SPORTYBET_PROVIDER", required_schema_version=1
    )
forbidden = {
    "domain.price_all_v2_direct_provider",
    "domain.market_router_v2_direct_provider",
    "domain.portfolio_optimizer_v2_direct_provider",
}
assert not forbidden.intersection(sys.modules)
monkeypatch = MonkeyPatch()
try:
    source_decision = _priced_match_result(monkeypatch, probability=0.60)
    canonical_price = price_all.PriceAllEvaluation._from_v3(source_decision)
    router_decision = router.route(
        canonical_price,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    portfolio.optimize_portfolio_as_of(
        (), target_legs=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
    portfolio_v3.optimize_current_provider_portfolio_as_of(
        (portfolio_input(monkeypatch),), target_size=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
finally:
    monkeypatch.undo()
assert not forbidden.intersection(sys.modules)
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_contract_only_modules_are_not_registered_component_owners():
    registry = json.loads(
        (ROOT / "config/architecture/component-authority-registry-v1.json").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(registry, sort_keys=True)
    for module in (
        "domain._price_all_v2_direct_provider_contracts",
        "domain._market_router_v2_contracts",
        "domain._portfolio_optimizer_v2_direct_provider_contracts",
    ):
        assert module not in serialized


def test_price_all_contract_package_does_not_export_provider_acquisition_modules():
    assert "live" not in price_contracts.__all__
    assert "adapter" not in price_contracts.__all__
    assert not hasattr(price_contracts, "live")
    assert not hasattr(price_contracts, "adapter")


def test_current_v2_v3_contract_identities_remain_exact():
    assert price_contracts.calculate_price_all_v2_contract_sha256() == "b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599"
    assert router_contracts.calculate_market_router_v2_contract_sha256() == "071d1246ee285634af5598b66872fb27c683f2d13ab14dc25b31de90b72195de"
    assert portfolio_contracts.calculate_portfolio_optimizer_v2_contract_sha256() == "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd"
    assert price_all_v3_current_provider.calculate_price_all_v3_contract_sha256() == "30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425"
    assert market_router_v3_current_provider.calculate_market_router_v3_contract_sha256() == "61a90a29495399668e19ae4a149527abea98c172d7bdacf1a1b521776b4d771a"
    assert portfolio_optimizer_v3_current_provider.calculate_portfolio_optimizer_v3_contract_sha256() == "4dc8be4e0a9f607b6c0804048bb326c0aa342d37fe540abbcd3e1b3a5f6a6dad"


if __name__ == "__main__":
    print(write_base_policy_vectors())
