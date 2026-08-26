from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain._forward_calibration_fit import fit_forward_calibrator
from domain._forward_calibration_projection import (
    CalibrationPartition,
    CalibrationVectorRow,
    calibration_unit_specs,
)
from domain._price_all_contracts import CalibratedValueCandidate, SportyBetExactQuote
from domain.markets import MarketId, OutcomeId, make_selection
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

EVENT = "sr:match:123"
SPORT = "sr:sport:1"
NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)


def _unit(market: MarketId, outcome: OutcomeId, line: float | None):
    if market is MarketId.TOTAL_GOALS:
        specs = calibration_unit_specs(total_goal_lines=(line,))
    elif market is MarketId.ASIAN_HANDICAP:
        home_line = line if outcome is OutcomeId.HOME else -line
        specs = calibration_unit_specs(asian_handicap_home_lines=(home_line,))
    else:
        specs = calibration_unit_specs()
    return next(item for item in specs if (
        item.market_id is market
        and item.line == line
        and (item.selection_outcome is None or item.selection_outcome is outcome)
    ))


def phase6_candidate(
    market: MarketId = MarketId.MATCH_RESULT,
    outcome: OutcomeId = OutcomeId.HOME,
    line: float | None = None,
    probabilities: tuple[float, ...] = (0.55, 0.25, 0.20),
    *,
    fixture_id: str = "fx",
    event_id: str = EVENT,
):
    unit = _unit(market, outcome, line)
    if len(probabilities) != len(unit.components):
        raise AssertionError("test probability vector width differs from Phase 6 unit")
    fit_row = CalibrationVectorRow(
        match_key="fit", match_date="2024-01-02", competition_key="L1",
        season="2024", regime="MID_EVENT", model_id="POISSON_GLM_SCORE_V1",
        fold_index=1, fit_end_date="2024-01-01",
        partition=CalibrationPartition.OOF_CALIBRATION_FIT,
        unit=unit, raw_probabilities=probabilities, observed_index=0,
    )
    artifact = fit_forward_calibrator(
        (fit_row,), model_id=fit_row.model_id,
        source_training_view_sha256="a" * 64,
    )
    target_row = CalibrationVectorRow(
        match_key=fixture_id, match_date="2026-08-26", competition_key="L1",
        season="2026", regime="MID_EVENT", model_id=artifact.model_id,
        fold_index=2, fit_end_date="2026-08-25",
        partition=CalibrationPartition.TERMINAL_HOLDOUT_EVALUATION,
        unit=unit, raw_probabilities=probabilities, observed_index=0,
    )
    return CalibratedValueCandidate.from_phase6_calibration(
        artifact, target_row, fixture_id=fixture_id,
        sportybet_event_id=event_id, outcome_id=outcome,
    ), artifact, target_row


def _selection_sha(value) -> str:
    payload = json.dumps(value.to_dict(), ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode() + b"\n"
    return hashlib.sha256(payload).hexdigest()


def reviewed_quote_bundle(
    tmp_path: Path,
    market: MarketId,
    outcomes_and_odds: tuple[tuple[OutcomeId, float], ...],
    line: float | None = None,
    *,
    observed_at: datetime = NOW,
    provider_market_id: str | None = None,
    provider_market_ids: dict[OutcomeId, str] | None = None,
):
    default_provider_market = provider_market_id or f"pm-{market.value}"
    specifier = None
    if market is MarketId.TOTAL_GOALS:
        specifier = f"total={line}"
    elif market is MarketId.ASIAN_HANDICAP:
        specifier = f"hcp={line}"
    anchors = []
    for outcome, odds in outcomes_and_odds:
        provider_market = (provider_market_ids or {}).get(outcome, default_provider_market)
        query = {
            "eventId": EVENT, "marketId": provider_market,
            "outcomeId": f"po-{outcome.value}", "odds": f"{odds:.2f}",
            "productId": "3", "sportId": SPORT, "marketGroupsName": "Main",
        }
        if specifier is not None:
            query["specifier"] = specifier
        anchors.append(
            f'<a data-active="true" data-market-name="{market.value}" '
            f'data-outcome-name="{outcome.value}" '
            f'href="/ng/lite/preMatch/detail?{urlencode(query)}">{outcome.value}</a>'
        )
    raw = ("<!doctype html><html><body>" + "".join(anchors) + "</body></html>").encode()
    repo = tmp_path / hashlib.sha256(raw + observed_at.isoformat().encode()).hexdigest()[:16]
    repo.mkdir(exist_ok=True)
    source_url = (
        "https://www.sportybet.com/ng/lite/preMatch/detail?" + urlencode({
            "eventId": EVENT, "marketGroupsName": "Main", "sportId": SPORT,
        })
    )
    evidence, _manifest = manual.store_user_controlled_evidence(
        raw, source_url=source_url, observed_at_user_attested=observed_at,
        imported_at_utc=observed_at + timedelta(seconds=1),
        attestation=manual.ATTESTATION, repository_root=repo,
    )
    allowed_root = repo / manual.ALLOWED_OUTPUT_RELATIVE
    inventory = native.build_inventory_from_evidence(evidence, allowed_root=allowed_root)
    source_by_outcome = {item.outcome_id: item for item in inventory.selections}
    mapped_rows = []
    for outcome, _odds in outcomes_and_odds:
        source = source_by_outcome[f"po-{outcome.value}"]
        canonical = make_selection(market, outcome, line=line)
        early = market in {MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}
        mapped_rows.append(MappedSportyBetCanonicalSelection(
            provider_selection_sha256=_selection_sha(source), event_id=source.event_id,
            provider_market_id=source.market_id, provider_market_name=source.market_name,
            provider_specifier=source.specifier, provider_outcome_id=source.outcome_id,
            provider_selection_label=source.selection_label,
            availability=source.availability.value, odds_raw=source.odds_raw,
            odds_decimal=source.odds_decimal, provider_quote_at=None,
            provider_snapshot_id=None, canonical_market_id=canonical.market_id,
            canonical_outcome_id=canonical.outcome_id, canonical_line=canonical.line,
            canonical_display_label=canonical.display_label,
            canonical_selection_display_name=canonical.selection_display_name,
            settlement_equivalence_authority=(
                SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
                if early else
                SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE
            ),
            settlement_evidence_sha256=None,
            bookmaker_equivalence_authorized=not early,
            canonical_market_mapping_authorized=True,
            fresh_price_authorized=False, href=source.href,
        ))
    mapped = tuple(mapped_rows)
    represented = tuple(item for item in TARGET_MARKET_IDS if item is market)
    missing = tuple(item for item in TARGET_MARKET_IDS if item is not market)
    all_equivalent = all(item.bookmaker_equivalence_authorized for item in mapped)
    safety = {
        "bet_authorized": False, "bookmaker_equivalence_authorized": all_equivalent,
        "booking_code_authorized": False, "canonical_market_mapping_authorized": True,
        "fixture_reconciliation_authorized": True, "fresh_price_authorized": False,
        "model_integration_authorized": False, "network_acquisition_authorized": False,
        "pricing_authorized": False, "selection_authorized": False,
        "slip_construction_authorized": False, "sportybet_execution_authorized": False,
    }
    mapping = SportyBetReviewedCanonicalMarketMapping(
        schema_version=SCHEMA_VERSION, dataset_name=DATASET_NAME,
        provider="SportyBet", status=STATUS, review_basis=REVIEW_BASIS,
        source_reconciliation_receipt_sha256="b" * 64,
        source_native_inventory_sha256=native.inventory_sha256(inventory),
        source_event_evidence_id=inventory.source_evidence_id,
        sportybet_event_id=EVENT, sportybet_sport_id=SPORT,
        matched_fotmob_fixture_id="fx", review_decisions_sha256="d" * 64,
        mapped_selections=mapped, represented_target_market_ids=represented,
        unrepresented_target_market_ids=missing,
        all_15_target_markets_represented=False,
        mapped_selection_count=len(mapped), unmapped_native_selection_count=0,
        safety=safety,
    )
    quotes = {
        row.canonical_outcome_id: SportyBetExactQuote.from_reviewed_mapping(
            mapping, provider_selection_sha256=row.provider_selection_sha256,
            evidence_directory=evidence, allowed_evidence_root=allowed_root,
        )
        for row in mapped
    }
    return mapping, inventory, evidence, allowed_root, quotes
