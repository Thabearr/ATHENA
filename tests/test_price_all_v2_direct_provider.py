from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import price_all_v2_direct_provider as v2
from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_live_event_quote_evidence as live
from domain import sportybet_price_all_direct_provider_quote_adapter as adapter
from domain import sportybet_reviewed_canonical_market_mapping as mapping
from domain import sportybet_user_controlled_native_inventory as native
from domain._price_all_contracts import DevigStatus, validate_price_all_contract
from domain.markets import MarketId, OutcomeId
from domain.sportybet_provider_native_inventory import NativeAvailability, NativeSelection
from tests._price_all_helpers import phase6_candidate


EVENT = "sr:match:123"
SPORT = "sr:sport:1"
FIXTURE = "987654"
INV_SHA = "1" * 64
EVIDENCE = "a" * 24
OBSERVED = datetime(2026, 8, 27, 18, 0, 0, tzinfo=timezone.utc)


def _market_shape(market: MarketId, line: float | None):
    if market is MarketId.MATCH_RESULT:
        return "1", "Match Result", None, {
            OutcomeId.HOME: ("H", "Home"),
            OutcomeId.DRAW: ("D", "Draw"),
            OutcomeId.AWAY: ("A", "Away"),
        }
    if market is MarketId.DRAW_NO_BET:
        return "52", "Draw No Bet", None, {
            OutcomeId.HOME: ("H", "Home"),
            OutcomeId.AWAY: ("A", "Away"),
        }
    if market is MarketId.BTTS:
        return "29", "Both Teams To Score", None, {
            OutcomeId.YES: ("Y", "Yes"),
            OutcomeId.NO: ("N", "No"),
        }
    if market is MarketId.TOTAL_GOALS:
        return "18", "Total Goals", f"total={line}", {
            OutcomeId.OVER: ("O", f"Over {line}"),
            OutcomeId.UNDER: ("U", f"Under {line}"),
        }
    raise AssertionError(f"unsupported test market: {market}")


def _native_selection(
    *,
    market: MarketId,
    outcome: OutcomeId,
    odds: float,
    line: float | None,
) -> NativeSelection:
    market_id, market_name, specifier, outcomes = _market_shape(market, line)
    provider_outcome_id, label = outcomes[outcome]
    query = (
        f"eventId={EVENT}&marketId={market_id}&outcomeId={provider_outcome_id}"
        f"&odds={odds:.2f}&productId=3&sportId={SPORT}&marketGroupsName=Main"
    )
    if specifier is not None:
        query += f"&specifier={specifier}"
    return NativeSelection(
        event_id=EVENT,
        sport_id=SPORT,
        product_id="3",
        market_id=market_id,
        market_group="Main",
        market_name=market_name,
        specifier=specifier,
        outcome_id=provider_outcome_id,
        selection_label=label,
        odds_raw=f"{odds:.2f}",
        odds_decimal=str(odds),
        availability=NativeAvailability.AVAILABLE,
        provider_quote_at=None,
        provider_snapshot_id=None,
        href=f"/ng/lite/preMatch/detail?{query}",
    )


def _reviewed_mapping(
    monkeypatch,
    *,
    market: MarketId,
    rows: tuple[tuple[OutcomeId, float], ...],
    line: float | None = None,
):
    selections = tuple(
        _native_selection(market=market, outcome=outcome, odds=odds, line=line)
        for outcome, odds in rows
    )
    inventory = object.__new__(native.SportyBetUserControlledNativeInventory)
    object.__setattr__(inventory, "source_event_id", EVENT)
    object.__setattr__(inventory, "source_sport_id", SPORT)
    object.__setattr__(inventory, "source_evidence_id", EVIDENCE)
    object.__setattr__(inventory, "provider_quote_at", None)
    object.__setattr__(inventory, "provider_snapshot_id", None)
    object.__setattr__(inventory, "selections", selections)
    reconciled = SimpleNamespace(
        disposition=(
            reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        ),
        fixture_reconciliation_authorized=True,
        matched_fixture=SimpleNamespace(source_fixture_identifier=FIXTURE),
        source_native_inventory_sha256=INV_SHA,
        sportybet_event_id=EVENT,
        sportybet_sport_id=SPORT,
        source_event_evidence_id=EVIDENCE,
    )
    decisions = tuple(
        mapping.ReviewedCanonicalMappingDecision(
            event_id=row.event_id,
            provider_market_id=row.market_id,
            provider_market_name=row.market_name,
            provider_specifier=row.specifier,
            provider_outcome_id=row.outcome_id,
            provider_selection_label=row.selection_label,
            canonical_market_id=market,
            canonical_outcome_id=outcome,
            canonical_line=line,
        )
        for row, (outcome, _odds) in zip(selections, rows)
    )
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(
        mapping.reconciliation,
        "canonical_reconciliation_bytes",
        lambda value: b"reconciliation\n",
    )
    return mapping._build(reconciled, inventory, decisions)


def _raw_event(
    *,
    market: MarketId,
    rows: tuple[tuple[OutcomeId, float], ...],
    kickoff: datetime,
    line: float | None = None,
    omit: frozenset[OutcomeId] = frozenset(),
) -> bytes:
    market_id, market_name, specifier, outcomes = _market_shape(market, line)
    native_outcomes = []
    for outcome, odds in rows:
        if outcome in omit:
            continue
        provider_outcome_id, label = outcomes[outcome]
        native_outcomes.append(
            {
                "id": provider_outcome_id,
                "desc": label,
                "odds": f"{odds:.2f}",
                "isActive": 1,
            }
        )
    market_payload = {
        "id": market_id,
        "desc": market_name,
        "outcomes": native_outcomes,
    }
    if specifier is not None:
        market_payload["specifier"] = specifier
    payload = {
        "bizCode": 10000,
        "data": {
            "event": {
                "eventId": EVENT,
                "homeTeamName": "Home FC",
                "awayTeamName": "Away FC",
                "estimateStartTime": int(kickoff.timestamp() * 1000),
                "bookingStatus": "Available",
                "status": 0,
                "matchStatus": "Not Started",
                "markets": [market_payload],
            }
        },
    }
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _quote_source(
    monkeypatch,
    tmp_path: Path,
    *,
    market: MarketId = MarketId.MATCH_RESULT,
    rows: tuple[tuple[OutcomeId, float], ...] = (
        (OutcomeId.HOME, 2.0),
        (OutcomeId.DRAW, 4.0),
        (OutcomeId.AWAY, 4.0),
    ),
    line: float | None = None,
    kickoff: datetime | None = None,
    omit: frozenset[OutcomeId] = frozenset(),
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    kickoff = kickoff or (OBSERVED + timedelta(hours=2))
    reviewed = _reviewed_mapping(
        monkeypatch, market=market, rows=rows, line=line
    )
    raw = _raw_event(
        market=market,
        rows=rows,
        kickoff=kickoff,
        line=line,
        omit=omit,
    )
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: (raw, 200, OBSERVED),
    )
    monkeypatch.setattr(
        live,
        "_now_utc",
        lambda: OBSERVED + timedelta(seconds=5),
    )
    bundle = live.capture_and_issue_current_mapped_quote_bundle(
        mapping=reviewed,
        repository_root=tmp_path,
        execute_live_network=True,
    )
    return adapter.adapt_current_live_quote_bundle(bundle), bundle


def _candidate(
    market: MarketId = MarketId.MATCH_RESULT,
    outcome: OutcomeId = OutcomeId.HOME,
    line: float | None = None,
    probabilities: tuple[float, ...] | None = None,
    *,
    fixture_id: str = FIXTURE,
):
    defaults = {
        MarketId.MATCH_RESULT: (0.55, 0.25, 0.20),
        MarketId.BTTS: (0.55, 0.45),
        MarketId.DRAW_NO_BET: (0.50, 0.20, 0.30),
        MarketId.TOTAL_GOALS: (0.55, 0.45),
    }
    return phase6_candidate(
        market,
        outcome,
        line,
        probabilities or defaults[market],
        fixture_id=fixture_id,
        event_id=EVENT,
    )[0]


def test_v2_contract_pins_adapter_and_preserves_frozen_price_all_v1():
    identities = v2.validate_price_all_v2_contract()
    assert identities["price_all_v2_contract_sha256"] == v2.EXPECTED_CONTRACT_SHA256
    assert identities["source_adapter_contract_sha256"] == adapter.EXPECTED_CONTRACT_SHA256
    assert identities["legacy_price_all_v1_contract_sha256"] == (
        "1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa"
    )
    assert validate_price_all_contract()["price_all_contract_sha256"] == (
        "1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa"
    )


def test_current_direct_provider_partition_prices_with_ev_and_devig(
    monkeypatch, tmp_path
):
    source, source_bundle = _quote_source(monkeypatch, tmp_path)
    evaluation = v2.price_all_direct_provider_candidates(
        [_candidate()],
        source,
        evaluation_time=OBSERVED + timedelta(seconds=10),
    )
    result = evaluation.results[0]

    assert evaluation.dataset_name == v2.DATASET_NAME
    assert evaluation.status == v2.STATUS
    assert evaluation.fixture_id == FIXTURE
    assert evaluation.event_id == EVENT
    assert evaluation.quote_age_seconds == 10
    assert evaluation.kickoff_lead_seconds == 2 * 3600 - 10
    assert evaluation.source_quote_source_sha256 == source.canonical_sha256
    assert evaluation.source_bundle_sha256 == source.source_bundle_sha256
    assert evaluation.source_adapter_contract_sha256 == adapter.EXPECTED_CONTRACT_SHA256
    assert evaluation.authority["verified_direct_provider_price_consumption"] is True
    assert evaluation.authority["value_record_computation"] is True
    assert evaluation.authority["market_router"] is False
    assert evaluation.authority["final_selection"] is False
    assert evaluation.authority["bet"] is False
    assert evaluation.next_boundary == (
        "MARKET_ROUTER_V2_DIRECT_PROVIDER_VALUE_CONSUMPTION_REQUIRED"
    )
    assert evaluation.to_dict()["wager_placed"] is False

    assert result.disposition is v2.DirectProviderPriceDisposition.PRICED
    assert result.quote is not None
    assert result.quote.decimal_odds == 2.0
    assert result.quote.observation_authority == live.OBSERVATION_AUTHORITY
    assert result.quote.provider_quote_at is None
    assert result.quote.provider_snapshot_id is None
    assert result.quote.source_bundle_sha256 == source_bundle.canonical_sha256
    assert result.quote_age_seconds == 10
    assert result.raw_implied_probability == pytest.approx(0.5)
    assert result.devig_status is DevigStatus.AVAILABLE_COMPLETE_PARTITION
    assert result.overround == pytest.approx(1.0)
    assert result.fair_probability == pytest.approx(0.5)
    assert result.net_expected_value == pytest.approx(0.10)
    assert result.ev_percentage == pytest.approx(10.0)
    assert v2.verify_price_all_v2_direct_provider_evaluation(evaluation).to_dict() == (
        evaluation.to_dict()
    )


def test_every_candidate_has_explicit_output_and_source_mismatch_is_not_guessed(
    monkeypatch, tmp_path
):
    source, _bundle = _quote_source(monkeypatch, tmp_path)
    home = _candidate()
    btts = _candidate(MarketId.BTTS, OutcomeId.YES)
    wrong_fixture = _candidate(fixture_id="different-fixture")
    evaluation = v2.price_all_direct_provider_candidates(
        [wrong_fixture, btts, home],
        source,
        evaluation_time=OBSERVED + timedelta(seconds=10),
    )
    by_id = {item.candidate.candidate_id: item for item in evaluation.results}
    assert by_id[home.candidate_id].disposition is v2.DirectProviderPriceDisposition.PRICED
    assert by_id[btts.candidate_id].disposition is (
        v2.DirectProviderPriceDisposition.UNPRICED_NO_EXACT_QUOTE
    )
    assert by_id[wrong_fixture.candidate_id].disposition is (
        v2.DirectProviderPriceDisposition.UNPRICED_SOURCE_MISMATCH
    )
    assert [item.candidate.candidate_id for item in evaluation.results] == sorted(by_id)
    assert all(
        "selected" not in item.to_dict() and "rank" not in item.to_dict()
        for item in evaluation.results
    )


def test_price_all_v2_rechecks_stale_and_near_kickoff_at_its_own_time(
    monkeypatch, tmp_path
):
    source, _bundle = _quote_source(monkeypatch, tmp_path / "stale")
    stale = v2.price_all_direct_provider_candidates(
        [_candidate()],
        source,
        evaluation_time=OBSERVED + timedelta(seconds=901),
    ).results[0]
    assert stale.disposition is v2.DirectProviderPriceDisposition.UNPRICED_STALE_QUOTE
    assert stale.quote_age_seconds == 901

    close_source, _close_bundle = _quote_source(
        monkeypatch,
        tmp_path / "close",
        kickoff=OBSERVED + timedelta(minutes=10),
    )
    near = v2.price_all_direct_provider_candidates(
        [_candidate()],
        close_source,
        evaluation_time=OBSERVED + timedelta(minutes=8),
    ).results[0]
    assert near.quote_age_seconds == 8 * 60
    assert near.kickoff_lead_seconds == 120
    assert near.disposition is v2.DirectProviderPriceDisposition.UNPRICED_NEAR_KICKOFF


def test_freshness_policy_can_only_be_tightened_and_time_cannot_precede_source(
    monkeypatch, tmp_path
):
    source, _bundle = _quote_source(monkeypatch, tmp_path)
    with pytest.raises(v2.PriceAllV2DirectProviderError, match="0..900"):
        v2.price_all_direct_provider_candidates(
            [_candidate()],
            source,
            evaluation_time=OBSERVED + timedelta(seconds=10),
            max_quote_age_seconds=901,
        )
    with pytest.raises(v2.PriceAllV2DirectProviderError, match="120-second"):
        v2.price_all_direct_provider_candidates(
            [_candidate()],
            source,
            evaluation_time=OBSERVED + timedelta(seconds=10),
            minimum_lead_seconds=119,
        )
    with pytest.raises(v2.PriceAllV2DirectProviderError, match="predates"):
        v2.price_all_direct_provider_candidates(
            [_candidate()],
            source,
            evaluation_time=OBSERVED + timedelta(seconds=4),
        )


def test_settlement_aware_draw_no_bet_ev_is_preserved_for_direct_provider(
    monkeypatch, tmp_path
):
    source, _bundle = _quote_source(
        monkeypatch,
        tmp_path,
        market=MarketId.DRAW_NO_BET,
        rows=((OutcomeId.HOME, 2.1), (OutcomeId.AWAY, 1.8)),
    )
    result = v2.price_all_direct_provider_candidates(
        [_candidate(MarketId.DRAW_NO_BET, OutcomeId.HOME)],
        source,
        evaluation_time=OBSERVED + timedelta(seconds=10),
    ).results[0]
    assert result.disposition is v2.DirectProviderPriceDisposition.PRICED
    assert result.net_expected_value == pytest.approx(0.5 * 1.1 - 0.3)
    assert result.devig_status is DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
    returns = dict(result.settlement_returns)
    assert returns["WIN"] == pytest.approx(1.1)
    assert returns["PUSH"] == 0.0
    assert returns["LOSS"] == -1.0


def test_absent_current_provider_outcome_preserves_mapping_audit_and_no_quote(
    monkeypatch, tmp_path
):
    source, _bundle = _quote_source(
        monkeypatch,
        tmp_path,
        omit=frozenset({OutcomeId.DRAW}),
    )
    draw = _candidate(MarketId.MATCH_RESULT, OutcomeId.DRAW)
    evaluation = v2.price_all_direct_provider_candidates(
        [draw],
        source,
        evaluation_time=OBSERVED + timedelta(seconds=10),
    )
    assert evaluation.results[0].disposition is (
        v2.DirectProviderPriceDisposition.UNPRICED_NO_EXACT_QUOTE
    )
    assert any(
        audit.canonical_outcome_id == OutcomeId.DRAW.value
        and audit.disposition == "ABSENT_FROM_CURRENT_EVENT"
        for audit in evaluation.mapping_audits
    )


def test_builder_only_outputs_and_exact_reconstruction_fail_closed(
    monkeypatch, tmp_path
):
    source, _bundle = _quote_source(monkeypatch, tmp_path)
    evaluation = v2.price_all_direct_provider_candidates(
        [_candidate()],
        source,
        evaluation_time=OBSERVED + timedelta(seconds=10),
    )
    with pytest.raises(v2.PriceAllV2DirectProviderError, match="issued only"):
        v2.PriceAllV2DirectProviderEvaluation()
    with pytest.raises(v2.PriceAllV2DirectProviderError, match="issued only"):
        v2.PriceAllV2DirectProviderResult()
    with pytest.raises(v2.PriceAllV2DirectProviderError):
        dataclasses.replace(evaluation, status="FAKE")

    object.__setattr__(evaluation, "source_bundle_sha256", "0" * 64)
    with pytest.raises(
        v2.PriceAllV2DirectProviderError,
        match="differs from exact source reconstruction",
    ):
        v2.verify_price_all_v2_direct_provider_evaluation(evaluation)


def test_tampered_adapter_source_and_duplicate_candidates_fail_closed(
    monkeypatch, tmp_path
):
    source, _bundle = _quote_source(monkeypatch, tmp_path)
    candidate = _candidate()
    with pytest.raises(v2.PriceAllV2DirectProviderError, match="candidate_id"):
        v2.price_all_direct_provider_candidates(
            [candidate, candidate],
            source,
            evaluation_time=OBSERVED + timedelta(seconds=10),
        )

    object.__setattr__(source, "source_bundle_sha256", "0" * 64)
    with pytest.raises(v2.PriceAllV2DirectProviderError, match="reconstruction failed"):
        v2.price_all_direct_provider_candidates(
            [candidate],
            source,
            evaluation_time=OBSERVED + timedelta(seconds=10),
        )
