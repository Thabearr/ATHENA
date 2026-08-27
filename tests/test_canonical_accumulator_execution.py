from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

import pytest

from domain import sportybet_fotmob_full_utc_reconciliation as full
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as receipt
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain._price_all_contracts import SportyBetExactQuote
from domain.accumulator_optimizer import AccumulatorFixtureInput
from domain.canonical_accumulator_execution import (
    CanonicalAccumulatorExecutionError,
    CanonicalAccumulatorFixtureInput,
    CanonicalPhase6CandidateInput,
    execute_canonical_accumulator,
    validate_canonical_execution_contract,
)
from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
)
from domain.markets import MarketId, OutcomeId, make_selection
from domain.sportybet_lite_source_capture import serialize_utc
from domain.sportybet_reviewed_canonical_market_mapping import (
    DATASET_NAME,
    REVIEW_BASIS,
    SCHEMA_VERSION,
    STATUS,
    TARGET_MARKET_IDS,
    MappedSportyBetCanonicalSelection,
    SettlementEquivalenceAuthority,
    SportyBetReviewedCanonicalMarketMapping,
)
from scripts import sportybet_semantic_share_bridge as semantic_bridge
from tests._accumulator_optimizer_helpers import (
    NOW,
    _reconciliation,
    _sha_row,
    source_bundle,
)
from tests._price_all_helpers import phase6_candidate


KICKOFF = NOW + timedelta(days=1)
_CONTEXT = (
    (IntelligenceCategory.FORM, "home_form", 0.72),
    (IntelligenceCategory.FORM, "away_form", 0.61),
    (IntelligenceCategory.PERFORMANCE, "home_elo", 1612),
    (IntelligenceCategory.PERFORMANCE, "away_elo", 1548),
    (IntelligenceCategory.SCHEDULE_LOAD, "fatigue", 0.23),
    (IntelligenceCategory.FIXTURE_CONTEXT, "live_data_freshness", 0.95),
)


def _fixture_snapshot(fixture_id: str, kickoff=KICKOFF):
    observed = NOW - timedelta(minutes=10)
    facts = tuple(
        FixtureIntelligenceFact(
            category=category,
            field=field,
            status=IntelligenceFactStatus.SUPPORTED,
            value=value,
            source_provider="FotMob",
            source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
            source_reference=f"fotmob:live:{fixture_id}:{field}",
            observed_at=observed,
            evidence_file_path=f"evidence/fotmob/{fixture_id}-{field}.json",
            evidence_sha256=hashlib.sha256(
                f"fotmob:{fixture_id}:{field}".encode()
            ).hexdigest(),
            notes="6aaed334 live FotMob evidence retained in the canonical snapshot.",
        )
        for category, field, value in _CONTEXT
    )
    return build_snapshot(fixture_id, kickoff, NOW - timedelta(minutes=5), facts)


def _provider_raw(
    *,
    event_id: str,
    market: MarketId,
    outcomes_and_odds: tuple[tuple[OutcomeId, float], ...],
    line: float | None,
) -> bytes:
    provider_market_id = f"pm-{event_id.removeprefix('sr:match:')}-{market.value}"
    specifier = None
    if market is MarketId.TOTAL_GOALS:
        specifier = f"total={line}"
    elif market is MarketId.ASIAN_HANDICAP:
        specifier = f"hcp={line}"
    anchors = []
    for outcome, odds in outcomes_and_odds:
        query = {
            "eventId": event_id,
            "marketId": provider_market_id,
            "outcomeId": f"po-{outcome.value}",
            "odds": f"{odds:.2f}",
            "productId": "3",
            "sportId": "sr:sport:1",
            "marketGroupsName": "Main",
        }
        if specifier is not None:
            query["specifier"] = specifier
        anchors.append(
            f'<a data-active="true" data-market-name="{market.value}" '
            f'data-outcome-name="{outcome.value}" '
            f'href="/ng/lite/preMatch/detail?{urlencode(query)}">'
            f"{outcome.value}</a>"
        )
    return ("<!doctype html><html><body>" + "".join(anchors) + "</body></html>").encode()


def _mapping_for_inventory(
    *,
    inventory,
    reconciled,
    market: MarketId,
    outcomes_and_odds: tuple[tuple[OutcomeId, float], ...],
    line: float | None,
):
    source_by_outcome = {item.outcome_id: item for item in inventory.selections}
    mapped_rows = []
    for outcome, _odds in outcomes_and_odds:
        source = source_by_outcome[f"po-{outcome.value}"]
        canonical = make_selection(market, outcome, line=line)
        mapped_rows.append(
            MappedSportyBetCanonicalSelection(
                provider_selection_sha256=_sha_row(source),
                event_id=source.event_id,
                provider_market_id=source.market_id,
                provider_market_name=source.market_name,
                provider_specifier=source.specifier,
                provider_outcome_id=source.outcome_id,
                provider_selection_label=source.selection_label,
                availability=source.availability.value,
                odds_raw=source.odds_raw,
                odds_decimal=source.odds_decimal,
                provider_quote_at=None,
                provider_snapshot_id=None,
                canonical_market_id=canonical.market_id,
                canonical_outcome_id=canonical.outcome_id,
                canonical_line=canonical.line,
                canonical_display_label=canonical.display_label,
                canonical_selection_display_name=canonical.selection_display_name,
                settlement_equivalence_authority=(
                    SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE
                ),
                settlement_evidence_sha256=None,
                bookmaker_equivalence_authorized=True,
                canonical_market_mapping_authorized=True,
                fresh_price_authorized=False,
                href=source.href,
            )
        )
    mapped = tuple(mapped_rows)
    represented = tuple(item for item in TARGET_MARKET_IDS if item is market)
    missing = tuple(item for item in TARGET_MARKET_IDS if item is not market)
    return SportyBetReviewedCanonicalMarketMapping(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider="SportyBet",
        status=STATUS,
        review_basis=REVIEW_BASIS,
        source_reconciliation_receipt_sha256=hashlib.sha256(
            full.canonical_reconciliation_bytes(reconciled)
        ).hexdigest(),
        source_native_inventory_sha256=native.inventory_sha256(inventory),
        source_event_evidence_id=inventory.source_evidence_id,
        sportybet_event_id=reconciled.sportybet_event_id,
        sportybet_sport_id=reconciled.sportybet_sport_id,
        matched_fotmob_fixture_id=reconciled.matched_fixture.source_fixture_identifier,
        review_decisions_sha256=hashlib.sha256(
            json.dumps(
                [row.to_dict() for row in mapped],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        mapped_selections=mapped,
        represented_target_market_ids=represented,
        unrepresented_target_market_ids=missing,
        all_15_target_markets_represented=False,
        mapped_selection_count=len(mapped),
        unmapped_native_selection_count=len(inventory.selections) - len(mapped),
        safety={
            "bet_authorized": False,
            "bookmaker_equivalence_authorized": True,
            "booking_code_authorized": False,
            "canonical_market_mapping_authorized": True,
            "fixture_reconciliation_authorized": True,
            "fresh_price_authorized": False,
            "model_integration_authorized": False,
            "network_acquisition_authorized": False,
            "pricing_authorized": False,
            "selection_authorized": False,
            "slip_construction_authorized": False,
            "sportybet_execution_authorized": False,
        },
    )


def _fixture_input(
    tmp_path: Path,
    index: int,
    *,
    market: MarketId = MarketId.MATCH_RESULT,
    probabilities: tuple[float, ...] | None = None,
    odds: tuple[tuple[OutcomeId, float], ...] | None = None,
    kickoff=KICKOFF,
    event_id: str | None = None,
):
    # The reviewed full-UTC reconciliation contract uses canonical decimal
    # FotMob fixture identifiers.
    fixture_id = str(100000 + index)
    provider_event_id = event_id or f"sr:match:{700000 + index}"
    home = f"Home {index}"
    away = f"Away {index}"
    if market is MarketId.MATCH_RESULT:
        probabilities = probabilities or (0.60, 0.22, 0.18)
        odds = odds or (
            (OutcomeId.HOME, 2.0),
            (OutcomeId.DRAW, 4.0),
            (OutcomeId.AWAY, 4.0),
        )
    elif market is MarketId.BTTS:
        probabilities = probabilities or (0.65, 0.35)
        odds = odds or ((OutcomeId.YES, 2.0), (OutcomeId.NO, 2.0))
    else:
        raise AssertionError("canonical test fixture supports only reviewed binary/1X2 paths")

    repo = tmp_path / f"source-{index}"
    repo.mkdir()
    raw = _provider_raw(
        event_id=provider_event_id,
        market=market,
        outcomes_and_odds=odds,
        line=None,
    )
    source_url = (
        "https://www.sportybet.com/ng/lite/preMatch/detail?"
        + urlencode(
            {
                "eventId": provider_event_id,
                "marketGroupsName": "Main",
                "sportId": "sr:sport:1",
            }
        )
    )
    evidence, _manifest = manual.store_user_controlled_evidence(
        raw,
        source_url=source_url,
        observed_at_user_attested=NOW,
        imported_at_utc=NOW + timedelta(seconds=1),
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    allowed_root = repo / manual.ALLOWED_OUTPUT_RELATIVE
    inventory = native.build_inventory_from_evidence(
        evidence, allowed_root=allowed_root
    )
    reconciled = _reconciliation(
        fixture_id=fixture_id,
        event_id=provider_event_id,
        home=home,
        away=away,
        competition=f"Competition {index // 5}",
        kickoff=kickoff,
        inventory=inventory,
    )
    mapping = _mapping_for_inventory(
        inventory=inventory,
        reconciled=reconciled,
        market=market,
        outcomes_and_odds=odds,
        line=None,
    )
    quotes = tuple(
        SportyBetExactQuote.from_reviewed_mapping(
            mapping,
            provider_selection_sha256=row.provider_selection_sha256,
            evidence_directory=evidence,
            allowed_evidence_root=allowed_root,
        )
        for row in mapping.mapped_selections
    )
    candidate, artifact, row = phase6_candidate(
        market=market,
        outcome=OutcomeId.HOME if market is MarketId.MATCH_RESULT else OutcomeId.YES,
        probabilities=probabilities,
        fixture_id=fixture_id,
        event_id=provider_event_id,
    )
    phase6_input = CanonicalPhase6CandidateInput.from_phase6_calibration(
        artifact,
        row,
        fixture_id=fixture_id,
        sportybet_event_id=provider_event_id,
        outcome_id=candidate.outcome_id,
    )
    bundle = replace(source_bundle(), event_inventory=inventory)
    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        return_value=reconciled,
    ):
        wrapper = CanonicalAccumulatorFixtureInput.from_source_replayed_receipt(
            intelligence_snapshot=_fixture_snapshot(fixture_id, kickoff),
            phase6_inputs=(phase6_input,),
            mapping=mapping,
            evidence_directory=evidence,
            allowed_evidence_root=allowed_root,
            receipt_directory=tmp_path / f"receipt-{index}",
            source_bundle=bundle,
            repository_root=tmp_path,
        )
    return wrapper, reconciled


def _semantic_receipt(intents, fixture_inputs):
    by_event = {
        item.mapping.sportybet_event_id: item for item in fixture_inputs
    }
    verification = []
    for intent in intents:
        item = by_event[intent["eventId"]]
        candidate = item.optimizer_input.candidates[0]
        quote = next(
            quote
            for quote in item.optimizer_input.quotes
            if quote.canonical_market_id is candidate.market_id
            and quote.canonical_outcome_id is candidate.outcome_id
            and quote.canonical_line == candidate.line
        )
        row = {
            "eventId": intent["eventId"],
            "homeTeamName": intent["homeTeamName"],
            "awayTeamName": intent["awayTeamName"],
            "marketId": quote.provider_market_id,
            "marketName": intent["marketName"],
            "specifier": intent["specifier"],
            "outcomeId": quote.provider_outcome_id,
            "outcomeName": intent["outcomeName"],
            "odds": str(quote.decimal_odds),
        }
        verification.append(
            {
                "eventId": intent["eventId"],
                "expected": {
                    "homeTeamName": intent["homeTeamName"],
                    "awayTeamName": intent["awayTeamName"],
                    "marketName": intent["marketName"],
                    "outcomeName": intent["outcomeName"],
                    "specifier": intent["specifier"],
                    "marketId": quote.provider_market_id,
                    "outcomeId": quote.provider_outcome_id,
                },
                "create": row,
                "reload": row,
                "exact_semantic_match": True,
            }
        )
    count = len(intents)
    return {
        "semantic_intent_count": count,
        "semantic_resolution_count": count,
        "provider_create_selection_count": count,
        "provider_reload_selection_count": count,
        "exact_roundtrip_selection_identity_verified": True,
        "semantic_roundtrip_verified": True,
        "semantic_roundtrip_verification": verification,
        "shareCode": "CANONICAL241",
        "shareURL": "https://example.invalid/CANONICAL241",
        "combined_odds": str(2.0**count),
        "wager_placed": False,
    }


def _run_with_fake_semantic(monkeypatch, tmp_path, fixture_inputs, target_size):
    captured = {}

    def fake_share(**kwargs):
        captured["intents"] = kwargs["intents"]
        return _semantic_receipt(kwargs["intents"], fixture_inputs)

    monkeypatch.setattr(
        "domain.canonical_accumulator_execution.semantic_bridge.create_semantic_share_code",
        fake_share,
    )
    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        side_effect=lambda _directory, *, source_bundle, repository_root: next(
            item.optimizer_input.reconciliation
            for item in fixture_inputs
            if item.source_native_inventory_sha256
            == native.inventory_sha256(source_bundle.event_inventory)
        ),
    ):
        result = execute_canonical_accumulator(
            tuple(fixture_inputs),
            target_size=target_size,
            output_dir=tmp_path / "artifact",
            evaluation_time=NOW + timedelta(seconds=30),
            minimum_lead_seconds=120,
            delay_seconds=0,
        )
    return result, captured


def test_contract_and_source_bound_multi_leg_path_succeed(monkeypatch, tmp_path):
    assert validate_canonical_execution_contract()[
        "canonical_execution_contract_sha256"
    ]
    first, _ = _fixture_input(tmp_path, 1)
    second, _ = _fixture_input(tmp_path, 2, market=MarketId.BTTS)

    result, captured = _run_with_fake_semantic(
        monkeypatch, tmp_path, (first, second), target_size=2
    )

    assert result.status == "CODE_VERIFIED"
    assert result.requested_fold_count == 2
    assert result.final_qualified_fold_count == 2
    assert result.router_selected_leg_count == 2
    assert result.optimizer_qualified_leg_count == 2
    assert result.semantic_intent_count == 2
    assert result.sportybet_create_selection_count == 2
    assert result.sportybet_reload_selection_count == 2
    assert result.wager_placed is False
    assert len(captured["intents"]) == 2
    assert all("marketId" not in intent and "outcomeId" not in intent for intent in captured["intents"])
    assert all(
        item["optimizer_leg"]["leg_id"] == item["semantic_intent"]["leg_id"]
        and item["optimizer_leg"]["sportybet_event_id"]
        == item["semantic_intent"]["provider_event_id"]
        for item in result.selected_legs
    )
    artifact = json.loads(
        (tmp_path / "artifact" / "canonical-accumulator-execution.json").read_text()
    )
    assert artifact["shareCode"] == "CANONICAL241"
    assert artifact["wager_placed"] is False


def test_correct_mocked_twenty_leg_flow_proves_all_semantics(monkeypatch, tmp_path):
    fixture_inputs = []
    for index in range(20):
        market = MarketId.MATCH_RESULT if index < 10 else MarketId.BTTS
        wrapper, _ = _fixture_input(tmp_path, index, market=market)
        fixture_inputs.append(wrapper)

    result, captured = _run_with_fake_semantic(
        monkeypatch, tmp_path, tuple(fixture_inputs), target_size=20
    )

    assert result.status == "CODE_VERIFIED"
    assert result.final_qualified_fold_count == 20
    assert result.router_selected_leg_count == 20
    assert result.optimizer_qualified_leg_count == 20
    assert result.semantic_intent_count == 20
    assert result.sportybet_create_selection_count == 20
    assert result.sportybet_reload_selection_count == 20
    assert len(captured["intents"]) == 20
    assert {
        (item["eventId"], item["homeTeamName"], item["awayTeamName"], item["marketName"], item["outcomeName"], item["specifier"])
        for item in captured["intents"]
    } == {
        (
            item.mapping.sportybet_event_id,
            item.optimizer_input.reconciliation.home_display,
            item.optimizer_input.reconciliation.away_display,
            item.mapping.mapped_selections[0].provider_market_name,
            item.mapping.mapped_selections[0].provider_selection_label,
            item.mapping.mapped_selections[0].provider_specifier,
        )
        for item in fixture_inputs
    }
    assert all(
        row["exact_semantic_match"] is True
        for row in result.semantic_receipt["semantic_roundtrip_verification"]
    )
    assert all(
        item["optimizer_leg"]["leg_id"] == item["semantic_intent"]["leg_id"]
        and item["optimizer_leg"]["sportybet_event_id"]
        == item["semantic_intent"]["provider_event_id"]
        for item in result.selected_legs
    )


def test_requested_twenty_with_nineteen_qualified_is_explicit_shortfall(monkeypatch, tmp_path):
    fixture_inputs = []
    for index in range(19):
        market = MarketId.MATCH_RESULT if index < 10 else MarketId.BTTS
        wrapper, _ = _fixture_input(tmp_path, index, market=market)
        fixture_inputs.append(wrapper)
    called = {"value": False}

    def should_not_call(**_kwargs):
        called["value"] = True
        raise AssertionError("shortfall must not invoke semantic SportyBet execution")

    monkeypatch.setattr(
        "domain.canonical_accumulator_execution.semantic_bridge.create_semantic_share_code",
        should_not_call,
    )
    result, _ = _run_with_fake_semantic(
        monkeypatch, tmp_path, tuple(fixture_inputs), target_size=20
    )
    assert result.status == "NO_CODE_SHORTFALL"
    assert result.requested_fold_count == 20
    assert result.final_qualified_fold_count == 19
    assert result.shortfall == 1
    assert result.share_code is None
    assert called["value"] is False


def test_stale_source_quote_fails_closed_without_dropping_into_a_code(monkeypatch, tmp_path):
    wrapper, _ = _fixture_input(tmp_path, 1)
    called = {"value": False}

    def should_not_call(**_kwargs):
        called["value"] = True
        raise AssertionError("stale source evidence must not reach provider create")

    monkeypatch.setattr(
        "domain.canonical_accumulator_execution.semantic_bridge.create_semantic_share_code",
        should_not_call,
    )
    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        return_value=wrapper.optimizer_input.reconciliation,
    ):
        result = execute_canonical_accumulator(
            (wrapper,),
            target_size=1,
            output_dir=tmp_path / "stale-artifact",
            evaluation_time=NOW + timedelta(seconds=901),
            minimum_lead_seconds=120,
            delay_seconds=0,
        )
    assert result.status == "NO_CODE_SHORTFALL"
    assert result.final_qualified_fold_count == 0
    assert called["value"] is False


def test_live_or_too_close_fixture_fails_before_semantic_execution(monkeypatch, tmp_path):
    wrapper, _ = _fixture_input(tmp_path, 1, kickoff=NOW + timedelta(seconds=60))
    called = {"value": False}

    def should_not_call(**_kwargs):
        called["value"] = True
        raise AssertionError("too-close fixture must not reach semantic execution")

    monkeypatch.setattr(
        "domain.canonical_accumulator_execution.semantic_bridge.create_semantic_share_code",
        should_not_call,
    )
    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        return_value=wrapper.optimizer_input.reconciliation,
    ), pytest.raises(CanonicalAccumulatorExecutionError, match="too close"):
        execute_canonical_accumulator(
            (wrapper,),
            target_size=1,
            output_dir=tmp_path / "too-close",
            evaluation_time=NOW + timedelta(seconds=30),
            minimum_lead_seconds=120,
            delay_seconds=0,
        )
    assert called["value"] is False


def test_candidate_input_is_source_issued_and_native_ids_cannot_be_intent_authority(tmp_path):
    with pytest.raises(CanonicalAccumulatorExecutionError, match="builder-only"):
        CanonicalPhase6CandidateInput(None, None)
    with pytest.raises(CanonicalAccumulatorExecutionError, match="builder-only"):
        CanonicalAccumulatorFixtureInput(None, None)

    # The only candidate issuance path replays the exact Phase 6 artifact and
    # row.  Native IDs and caller odds are not fields that can cross the
    # semantic adapter boundary.
    candidate, artifact, row = phase6_candidate(
        fixture_id="fixture-1",
        event_id="sr:match:700001",
    )
    request = CanonicalPhase6CandidateInput.from_phase6_calibration(
        artifact,
        row,
        fixture_id="fixture-1",
        sportybet_event_id="sr:match:700001",
        outcome_id=OutcomeId.HOME,
    )
    assert request.candidate.candidate_id == candidate.candidate_id
    with pytest.raises(
        semantic_bridge.SportyBetSemanticShareError,
        match="caller-supplied provider-native fields",
    ):
        semantic_bridge.validate_intents(
            [
                {
                    **{
                        "eventId": "sr:match:700001",
                        "homeTeamName": "Home 1",
                        "awayTeamName": "Away 1",
                        "marketName": "1X2",
                        "outcomeName": "Home",
                        "specifier": None,
                    },
                    "marketId": "caller-forged",
                    "outcomeId": "caller-forged",
                }
            ]
        )


def test_duplicate_provider_event_and_ancestry_drift_fail_closed(monkeypatch, tmp_path):
    first, _ = _fixture_input(tmp_path, 1)
    second, _ = _fixture_input(
        tmp_path, 2, event_id=first.mapping.sportybet_event_id
    )
    with pytest.raises(CanonicalAccumulatorExecutionError, match="exact tuple|Optimizer"):
        execute_canonical_accumulator(
            (first, second),
            target_size=2,
            output_dir=tmp_path / "duplicate-event",
            evaluation_time=NOW + timedelta(seconds=30),
            delay_seconds=0,
        )

    from domain import canonical_accumulator_execution as canonical
    from domain.accumulator_optimizer import optimize_accumulator

    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        return_value=first.optimizer_input.reconciliation,
    ):
        valid = optimize_accumulator(
            (first.optimizer_input,),
            target_size=1,
            evaluation_time=NOW + timedelta(seconds=30),
        )
    corrupted_leg = replace(
        valid.selected_legs[0], router_decision_sha256="f" * 64
    )
    corrupted = replace(valid, selected_legs=(corrupted_leg,))
    monkeypatch.setattr(canonical, "optimize_accumulator", lambda *args, **kwargs: corrupted)
    with pytest.raises(CanonicalAccumulatorExecutionError, match="Router ancestry"):
        execute_canonical_accumulator(
            (first,),
            target_size=1,
            output_dir=tmp_path / "ancestry-drift",
            evaluation_time=NOW + timedelta(seconds=30),
            delay_seconds=0,
        )


def test_semantic_count_and_transport_only_receipts_fail_closed(monkeypatch, tmp_path):
    first, _ = _fixture_input(tmp_path, 1)

    def wrong_count(**kwargs):
        receipt_value = _semantic_receipt(kwargs["intents"], (first,))
        receipt_value["provider_reload_selection_count"] = 0
        return receipt_value

    monkeypatch.setattr(
        "domain.canonical_accumulator_execution.semantic_bridge.create_semantic_share_code",
        wrong_count,
    )
    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        return_value=first.optimizer_input.reconciliation,
    ), pytest.raises(CanonicalAccumulatorExecutionError, match="count invariant"):
        execute_canonical_accumulator(
            (first,),
            target_size=1,
            output_dir=tmp_path / "count-drift",
            evaluation_time=NOW + timedelta(seconds=30),
            delay_seconds=0,
        )

    def wrong_semantics(**kwargs):
        receipt_value = _semantic_receipt(kwargs["intents"], (first,))
        receipt_value["semantic_roundtrip_verification"][0]["create"][
            "marketName"
        ] = "Double Chance"
        return receipt_value

    monkeypatch.setattr(
        "domain.canonical_accumulator_execution.semantic_bridge.create_semantic_share_code",
        wrong_semantics,
    )
    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        return_value=first.optimizer_input.reconciliation,
    ), pytest.raises(CanonicalAccumulatorExecutionError, match="semantics differ"):
        execute_canonical_accumulator(
            (first,),
            target_size=1,
            output_dir=tmp_path / "semantic-drift",
            evaluation_time=NOW + timedelta(seconds=30),
            delay_seconds=0,
        )

    def native_only(**_kwargs):
        return {
            "provider_create_selection_count": 1,
            "provider_reload_selection_count": 1,
            "exact_roundtrip_selection_identity_verified": True,
            "shareCode": "NATIVEONLY",
            "shareURL": "https://example.invalid/NATIVEONLY",
            "wager_placed": False,
        }

    monkeypatch.setattr(
        "domain.canonical_accumulator_execution.semantic_bridge.create_semantic_share_code",
        native_only,
    )
    with patch.object(
        receipt,
        "verify_reconciliation_receipt_directory",
        return_value=first.optimizer_input.reconciliation,
    ), pytest.raises(CanonicalAccumulatorExecutionError, match="count invariant"):
        execute_canonical_accumulator(
            (first,),
            target_size=1,
            output_dir=tmp_path / "native-only",
            evaluation_time=NOW + timedelta(seconds=30),
            delay_seconds=0,
        )


def test_fotmob_snapshot_ancestry_is_retained_in_final_artifact(monkeypatch, tmp_path):
    first, _ = _fixture_input(tmp_path, 1)
    result, _ = _run_with_fake_semantic(monkeypatch, tmp_path, (first,), 1)
    ancestry = result.fixture_ancestry[0]
    assert ancestry["intelligence_snapshot_sha256"] == first.source_snapshot_sha256
    assert ancestry["fixture_state_source_snapshot_sha256"] == first.source_snapshot_sha256
    assert ancestry["fixture_state_field_evidence"]
    assert all(
        fact.source_provider == "FotMob"
        for fact in first.intelligence_snapshot.facts
    )


def test_semantic_bridge_still_rejects_wrong_fixture_market_outcome_specifier_and_inactive():
    # These cases are the final provider-facing gate; canonical callers cannot
    # replace them with native IDs or direct-share transport.
    from tests.test_sportybet_semantic_share_bridge import _event, _intent

    intent = semantic_bridge.validate_intents([_intent()])[0]
    with pytest.raises(semantic_bridge.SportyBetSemanticShareError, match="home-team"):
        semantic_bridge.resolve_intent(
            event=_event(homeTeamName="Wrong FC"), intent=intent, minimum_lead_seconds=0
        )
    with pytest.raises(semantic_bridge.SportyBetSemanticShareError, match="expected exactly"):
        semantic_bridge.resolve_intent(
            event=_event(),
            intent=semantic_bridge.validate_intents([_intent(marketName="Double Chance")])[0],
            minimum_lead_seconds=0,
        )
    with pytest.raises(semantic_bridge.SportyBetSemanticShareError, match="expected exactly"):
        semantic_bridge.resolve_intent(
            event=_event(),
            intent=semantic_bridge.validate_intents([_intent(outcomeName="Home or Draw")])[0],
            minimum_lead_seconds=0,
        )
    with pytest.raises(semantic_bridge.SportyBetSemanticShareError, match="expected exactly"):
        semantic_bridge.resolve_intent(
            event=_event(),
            intent=semantic_bridge.validate_intents(
                [_intent(marketName="Over/Under", outcomeName="Over", specifier="total=2.5")]
            )[0],
            minimum_lead_seconds=0,
        )
