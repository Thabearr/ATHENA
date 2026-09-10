from __future__ import annotations

import ast
from datetime import timedelta
import inspect
from pathlib import Path

import pytest

from domain import price_all as canonical
from domain import price_all_v3_current_provider as v3
from domain._price_all_contracts import DevigStatus
from domain.markets import MarketId, OutcomeId
from domain.sportybet_reviewed_canonical_market_mapping import (
    SettlementEquivalenceAuthority,
)
from tests._price_all_helpers import phase6_candidate
from tests.test_current_direct_provider_live_quote_mapping_consumption import (
    EVALUATION,
    EVENT,
    FIXTURE,
    _build,
    _inventory,
    _mapped_row,
    _selection,
    _source_mapping,
)


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "domain/price_all.py"


def _candidate(
    market: MarketId = MarketId.TOTAL_GOALS,
    outcome: OutcomeId = OutcomeId.OVER,
    line: float | None = 2.5,
    probabilities: tuple[float, ...] = (0.58, 0.42),
):
    return phase6_candidate(
        market,
        outcome,
        line,
        probabilities,
        fixture_id=FIXTURE,
        event_id=EVENT,
    )[0]


def _assert_exact_parity(canonical_value, v3_value) -> None:
    assert canonical_value.to_dict() == v3_value.to_dict()
    assert canonical.canonical_json_bytes(canonical_value) == canonical.canonical_json_bytes(
        v3_value.to_dict()
    )
    assert canonical_value.canonical_sha256 == v3_value.canonical_sha256
    assert tuple(item.to_dict() for item in canonical_value.results) == tuple(
        item.to_dict() for item in v3_value.results
    )
    assert tuple(item.canonical_sha256 for item in canonical_value.results) == tuple(
        item.canonical_sha256 for item in v3_value.results
    )


def test_canonical_contract_pins_exact_promoted_v3_and_frozen_evidence() -> None:
    contract = canonical.validate_price_all_contract()
    assert contract["policy_id"] == "ATHENA_CANONICAL_PRICE_ALL_V1"
    assert contract["implementation_id"] == "domain.price_all_v3_current_provider"
    assert contract["implementation_contract_sha256"] == v3.EXPECTED_CONTRACT_SHA256
    assert contract["source_contract_sha256"] == v3.PR253_CONTRACT_SHA256
    assert contract["frozen_v2_contract_sha256"] == v3.PRICE_ALL_V2_CONTRACT_SHA256
    assert dict(contract["authority"]) == dict(v3._AUTHORITY)
    assert contract["authority"]["market_router"] is False
    assert contract["authority"]["sportybet_execution"] is False
    assert contract["authority"]["staking"] is False
    assert contract["authority"]["bet"] is False


def test_canonical_disposition_vocabulary_is_exact_v3_semantics() -> None:
    assert tuple(item.value for item in canonical.PriceDisposition) == tuple(
        item.value for item in v3.CurrentProviderPriceDisposition
    )


def test_exact_priced_fixture_is_byte_and_hash_identical_to_v3(monkeypatch) -> None:
    source, _ = _build(monkeypatch)
    candidate = _candidate()
    expected = v3.price_all_current_provider_candidates_as_of(
        (candidate,), source, evaluation_time=EVALUATION
    )
    actual = canonical.price_all_as_of(
        (candidate,), source, evaluation_time=EVALUATION
    )
    _assert_exact_parity(actual, expected)
    result = actual.results[0]
    assert result.disposition is canonical.PriceDisposition.PRICED
    assert result.net_expected_value == pytest.approx(0.218)
    assert actual.to_dict()["wager_placed"] is False
    assert "selected" not in actual.to_dict()
    assert "rank" not in str(actual.to_dict()).lower()


def test_unpriced_no_quote_fixture_is_identical_and_never_silently_dropped(monkeypatch) -> None:
    source, _ = _build(monkeypatch)
    candidates = (
        _candidate(),
        _candidate(MarketId.BTTS, OutcomeId.YES, None, (0.52, 0.48)),
    )
    expected = v3.price_all_current_provider_candidates_as_of(
        candidates, source, evaluation_time=EVALUATION
    )
    actual = canonical.price_all_as_of(candidates, source, evaluation_time=EVALUATION)
    _assert_exact_parity(actual, expected)
    assert len(actual.results) == len(candidates)
    by_id = {item.candidate.candidate_id: item.disposition for item in actual.results}
    assert by_id[candidates[0].candidate_id] is canonical.PriceDisposition.PRICED
    assert (
        by_id[candidates[1].candidate_id]
        is canonical.PriceDisposition.UNPRICED_NO_EXACT_QUOTE
    )


def test_stale_quote_disposition_is_identical_to_v3(monkeypatch) -> None:
    source, _ = _build(monkeypatch)
    when = EVALUATION + timedelta(seconds=841)
    candidate = _candidate()
    expected = v3.price_all_current_provider_candidates_as_of(
        (candidate,), source, evaluation_time=when
    )
    actual = canonical.price_all_as_of((candidate,), source, evaluation_time=when)
    _assert_exact_parity(actual, expected)
    assert actual.results[0].disposition is canonical.PriceDisposition.UNPRICED_STALE_QUOTE


def test_complete_partition_devig_is_identical_to_v3(monkeypatch) -> None:
    selections = (
        _selection(outcome_id="O", outcome_name="Over 2.5", odds_raw="2.10", decimal_odds=2.1),
        _selection(outcome_id="U", outcome_name="Under 2.5", odds_raw="1.80", decimal_odds=1.8),
    )
    inventory = _inventory(*selections)
    mapped = (
        _mapped_row(inventory),
        _mapped_row(
            inventory,
            outcome_id="U",
            outcome_name="Under 2.5",
            canonical_outcome=OutcomeId.UNDER,
        ),
    )
    source, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, *mapped),
    )
    candidate = _candidate()
    expected = v3.price_all_current_provider_candidates_as_of(
        (candidate,), source, evaluation_time=EVALUATION
    )
    actual = canonical.price_all_as_of((candidate,), source, evaluation_time=EVALUATION)
    _assert_exact_parity(actual, expected)
    assert actual.results[0].devig_status is DevigStatus.AVAILABLE_COMPLETE_PARTITION
    assert actual.results[0].overround == pytest.approx((1 / 2.1) + (1 / 1.8))


def test_push_split_settlement_ev_is_identical_and_not_flattened(monkeypatch) -> None:
    market = MarketId.ASIAN_HANDICAP
    line = 0.25
    probabilities = (0.30, 0.20, 0.10, 0.15, 0.25)
    selection = _selection(
        market_id="provider-ASIAN_HANDICAP",
        market_name="ASIAN_HANDICAP",
        specifier="hcp=0.25",
        outcome_id="provider-HOME",
        outcome_name="Home",
        odds_raw="2.0",
        decimal_odds=2.0,
    )
    inventory = _inventory(selection)
    mapped = _mapped_row(
        inventory,
        market_id=selection.market_id,
        market_name=selection.market_name,
        specifier="hcp=0.25",
        outcome_id=selection.outcome_id,
        outcome_name=selection.outcome_name,
        canonical_market=market,
        canonical_outcome=OutcomeId.HOME,
        line=line,
    )
    source, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, mapped),
    )
    candidate = phase6_candidate(
        market,
        OutcomeId.HOME,
        line,
        probabilities,
        fixture_id=FIXTURE,
        event_id=EVENT,
    )[0]
    expected = v3.price_all_current_provider_candidates_as_of(
        (candidate,), source, evaluation_time=EVALUATION
    )
    actual = canonical.price_all_as_of((candidate,), source, evaluation_time=EVALUATION)
    _assert_exact_parity(actual, expected)
    assert actual.results[0].net_expected_value == pytest.approx(0.075)
    assert (
        actual.results[0].devig_status
        is DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
    )


def test_unproven_settlement_equivalence_is_identical_explicit_unpriced(monkeypatch) -> None:
    inventory = _inventory()
    mapped = _mapped_row(
        inventory,
        settlement=SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN,
        bookmaker_equivalence=False,
    )
    source, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, mapped),
    )
    candidate = _candidate()
    expected = v3.price_all_current_provider_candidates_as_of(
        (candidate,), source, evaluation_time=EVALUATION
    )
    actual = canonical.price_all_as_of((candidate,), source, evaluation_time=EVALUATION)
    _assert_exact_parity(actual, expected)
    assert (
        actual.results[0].disposition
        is canonical.PriceDisposition.UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN
    )


def test_future_replay_failure_is_fail_closed_and_chains_v3_error(monkeypatch) -> None:
    source, _ = _build(monkeypatch)
    with pytest.raises(canonical.PriceAllError, match="predates PR253 issuance") as caught:
        canonical.price_all_as_of(
            (_candidate(),),
            source,
            evaluation_time=source.evaluation_time - timedelta(seconds=1),
        )
    assert isinstance(caught.value.__cause__, v3.PriceAllV3CurrentProviderError)


def test_current_lane_does_not_accept_caller_timestamp_and_preserves_live_gate(monkeypatch) -> None:
    assert "evaluation_time" not in inspect.signature(canonical.price_all_current).parameters
    source, _ = _build(monkeypatch)
    monkeypatch.setattr(v3, "_now_utc", lambda: EVALUATION)
    with pytest.raises(canonical.PriceAllError, match="LIVE_CURRENT"):
        canonical.price_all_current((_candidate(),), source)


def test_canonical_evaluation_replays_exact_v3_delegate(monkeypatch) -> None:
    source, _ = _build(monkeypatch)
    value = canonical.price_all_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    )
    rebuilt = canonical.verify_price_all_evaluation(value)
    _assert_exact_parity(rebuilt, value._delegate)
    assert canonical.unwrap_v3_evaluation(value).canonical_sha256 == value.canonical_sha256


def test_canonical_wrappers_are_builder_only_and_immutable(monkeypatch) -> None:
    with pytest.raises(canonical.PriceAllError, match="builder-only"):
        canonical.PriceAllEvaluation()
    with pytest.raises(canonical.PriceAllError, match="builder-only"):
        canonical.PriceAllResult()

    source, _ = _build(monkeypatch)
    value = canonical.price_all_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    )
    with pytest.raises(AttributeError, match="immutable"):
        value.status = "FORGED"
    with pytest.raises(AttributeError, match="immutable"):
        value.results[0].reason = "FORGED"
    with pytest.raises(TypeError):
        value.authority["bet"] = True  # type: ignore[index]


def test_canonical_module_is_facade_not_parallel_formula_or_downstream_authority() -> None:
    text = CANONICAL_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported: set[str] = set()
    defined_functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_functions.add(node.name)

    assert "domain.price_all_v3_current_provider" in imported
    assert not any(
        token in module
        for module in imported
        for token in (
            "market_router",
            "portfolio_optimizer",
            "share_code",
            "wallet",
            "staking",
            "wager",
            "prediction_service",
            "market_selector",
        )
    )
    assert not ({"_partition_quotes", "_price_one", "_settlement_ev"} & defined_functions)
    assert "def _partition_quotes" not in text
    assert "def _settlement_ev" not in text
