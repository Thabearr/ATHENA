"""P3.0 offline canonical synthetic acceptance harness.

Executes real canonical pricing and routing components without test module imports.
Used by the P3.0 offline replay comparator to evaluate synthetic P0 defect classes.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from domain import current_direct_provider_canonical_market_mapping_rebind as mapping
from domain import current_direct_provider_live_quote_mapping_consumption as quotes
from domain import market_router_canonical_adapter as canonical_router
from domain import price_all as canonical_price
from domain import sportybet_live_event_quote_evidence as live
from domain._forward_calibration_fit import fit_forward_calibrator
from domain._forward_calibration_projection import (
    CalibrationPartition,
    CalibrationVectorRow,
    calibration_unit_specs,
)
from domain._market_router_contracts import OpportunityEligibility, RouterDecisionStatus
from domain._price_all_contracts import CalibratedValueCandidate
from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
)
from domain.fixture_state_v2 import build_fixture_state_v2_snapshot
from domain.markets import (
    MarketId,
    OutcomeId,
    UnknownMarketError,
    UnknownSelectionError,
    canonicalize_market_id,
    resolve_legacy_selection,
)
from domain.price_all import PriceDisposition
from domain.sportybet_reviewed_canonical_market_mapping import SettlementEquivalenceAuthority

SYNTHETIC_EVENT_ID = "sr:match:71945268"
SYNTHETIC_FIXTURE_ID = "FOTMOB:5749683"
SYNTHETIC_EVALUATION_TIME = datetime(2026, 9, 20, 9, 34, 57, tzinfo=timezone.utc)
SYNTHETIC_KICKOFF_TIME = datetime(2026, 9, 20, 10, 30, 0, tzinfo=timezone.utc)
SYNTHETIC_OBSERVED_TIME = SYNTHETIC_EVALUATION_TIME - timedelta(minutes=10)


def _make_candidate(
    market: MarketId,
    outcome: OutcomeId,
    line: float | None = None,
    raw_probabilities: tuple[float, ...] = (0.60, 0.25, 0.15),
) -> CalibratedValueCandidate:
    """Construct a production CalibratedValueCandidate via phase 6 calibration fit."""
    specs = calibration_unit_specs()
    unit = next(
        u
        for u in specs
        if u.market_id is market
        and u.line == line
        and (u.selection_outcome is None or u.selection_outcome is outcome)
    )
    fit_row = CalibrationVectorRow(
        match_key="fit",
        match_date="2024-01-02",
        competition_key="L1",
        season="2024",
        regime="MID_EVENT",
        model_id="POISSON_GLM_SCORE_V1",
        fold_index=1,
        fit_end_date="2024-01-01",
        partition=CalibrationPartition.OOF_CALIBRATION_FIT,
        unit=unit,
        raw_probabilities=raw_probabilities,
        observed_index=0,
    )
    artifact = fit_forward_calibrator(
        (fit_row,),
        model_id=fit_row.model_id,
        source_training_view_sha256="a" * 64,
    )
    target_row = CalibrationVectorRow(
        match_key=SYNTHETIC_FIXTURE_ID,
        match_date="2026-09-20",
        competition_key="L1",
        season="2026",
        regime="MID_EVENT",
        model_id=artifact.model_id,
        fold_index=2,
        fit_end_date="2026-09-19",
        partition=CalibrationPartition.TERMINAL_HOLDOUT_EVALUATION,
        unit=unit,
        raw_probabilities=raw_probabilities,
        observed_index=0,
    )
    return CalibratedValueCandidate.from_phase6_calibration(
        artifact,
        target_row,
        fixture_id=SYNTHETIC_FIXTURE_ID,
        sportybet_event_id=SYNTHETIC_EVENT_ID,
        outcome_id=outcome,
    )


def _make_selection(
    market_id: str,
    market_name: str,
    specifier: str | None,
    outcome_id: str,
    outcome_name: str,
    odds_raw: str,
    decimal_odds: float,
    bookable: bool = True,
) -> live.SportyBetLiveEventSelection:
    return live.SportyBetLiveEventSelection(
        event_id=SYNTHETIC_EVENT_ID,
        market_id=market_id,
        market_name=market_name,
        specifier=specifier,
        outcome_id=outcome_id,
        outcome_name=outcome_name,
        bookable=bookable,
        bookability_basis="EXPLICIT_ACTIVE_FLAG",
        odds_raw=odds_raw,
        odds_decimal=decimal_odds,
    )


def _make_mapped_selection(
    inventory: live.SportyBetLiveEventQuoteInventory,
    market_id: str,
    market_name: str,
    specifier: str | None,
    outcome_id: str,
    outcome_name: str,
    canonical_market: MarketId,
    canonical_outcome: OutcomeId,
    line: float | None = None,
    bookable: bool = True,
) -> mapping.CurrentDirectProviderCanonicalMappedSelection:
    mapped = object.__new__(mapping.CurrentDirectProviderCanonicalMappedSelection)
    fields = {
        "fixture_id": SYNTHETIC_FIXTURE_ID,
        "event_id": SYNTHETIC_EVENT_ID,
        "provider_market_id": market_id,
        "provider_market_name": market_name,
        "provider_specifier": specifier,
        "provider_outcome_id": outcome_id,
        "provider_outcome_name": outcome_name,
        "canonical_market_id": canonical_market,
        "canonical_outcome_id": canonical_outcome,
        "canonical_line": line,
        "canonical_display_label": outcome_name,
        "canonical_selection_display_name": f"{market_name} - {outcome_name}",
        "settlement_equivalence_authority": SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE,
        "settlement_evidence_sha256": None,
        "bookmaker_equivalence_authorized": True,
        "current_bookable_observed": bookable,
        "current_bookability_basis": "EXPLICIT_ACTIVE_FLAG",
        "source_mapping_row_sha256": "1" * 64,
        "current_inventory_sha256": inventory.canonical_sha256,
        "canonical_market_mapping_authorized": True,
    }
    for k, v in fields.items():
        object.__setattr__(mapped, k, v)
    return mapped


def _make_source_mapping(
    inventory: live.SportyBetLiveEventQuoteInventory,
    mapped_selections: tuple[mapping.CurrentDirectProviderCanonicalMappedSelection, ...],
) -> mapping.CurrentDirectProviderCanonicalMarketMappingRebind:
    source_mapping = object.__new__(mapping.CurrentDirectProviderCanonicalMarketMappingRebind)
    represented = tuple(
        m
        for m in (MarketId.MATCH_RESULT, MarketId.BTTS)
        if any(item.canonical_market_id is m for item in mapped_selections)
    )
    fields = {
        "schema_version": mapping.SCHEMA_VERSION,
        "dataset_name": mapping.DATASET_NAME,
        "status": mapping.STATUS,
        "proof_mode": mapping.LIVE_CURRENT,
        "disposition": (
            mapping.RebindDisposition.REBOUND_EXACT_REVIEWED_SEMANTICS
            if mapped_selections
            else mapping.RebindDisposition.NO_EXACT_REVIEWED_SEMANTICS
        ),
        "evaluation_time": SYNTHETIC_EVALUATION_TIME - timedelta(seconds=30),
        "event_id": SYNTHETIC_EVENT_ID,
        "fixture_id": SYNTHETIC_FIXTURE_ID,
        "home_team_name": inventory.home_team_name,
        "away_team_name": inventory.away_team_name,
        "kickoff_utc": SYNTHETIC_KICKOFF_TIME,
        "discovery_observed_at": inventory.observed_at - timedelta(seconds=30),
        "direct_event_observed_at": inventory.observed_at,
        "discovery_age_seconds": 30.0,
        "direct_event_age_seconds": 30.0,
        "kickoff_lead_seconds": (SYNTHETIC_KICKOFF_TIME - SYNTHETIC_EVALUATION_TIME).total_seconds(),
        "max_source_age_seconds": mapping.MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": mapping.MINIMUM_LEAD_SECONDS,
        "source_current_reconciliation_sha256": "2" * 64,
        "source_current_reconciliation_contract_sha256": mapping.PR251_CONTRACT_SHA256,
        "source_legacy_mapping_sha256": "3" * 64,
        "source_legacy_review_decisions_sha256": "4" * 64,
        "source_legacy_event_id": "sr:match:111",
        "source_legacy_fixture_id": "123456",
        "current_inventory_sha256": inventory.canonical_sha256,
        "current_manifest_sha256": inventory.source_manifest_sha256,
        "current_raw_sha256": inventory.source_raw_sha256,
        "mapped_selections": mapped_selections,
        "mapping_audits": (),
        "source_template_count": len(mapped_selections),
        "mapped_selection_count": len(mapped_selections),
        "unreviewed_current_selection_count": 0,
        "represented_target_market_ids": represented,
        "unrepresented_target_market_ids": (),
        "all_source_templates_rebound": True,
        "all_15_target_markets_represented": True,
        "authority": {
            "current_event_source_replay": True,
            "legacy_reviewed_mapping_source_replay": True,
            "exact_provider_semantic_rebind": bool(mapped_selections),
            "canonical_market_mapping": bool(mapped_selections),
            "bookmaker_equivalence": bool(mapped_selections),
            "as_of_source_freshness": True,
            "wall_clock_currentness_at_issuance": True,
            "fresh_price": False,
            "price_all": False,
            "market_router": False,
            "portfolio_optimization": False,
            "final_selection": False,
            "accumulator_slip_construction": False,
            "sportybet_execution": False,
            "staking": False,
            "bet": False,
        },
        "next_boundary": mapping.NEXT_BOUNDARY,
        "contract_sha256": mapping.EXPECTED_CONTRACT_SHA256,
        "_current_bundle": SimpleNamespace(
            _detail_directories=((SYNTHETIC_EVENT_ID, Path("/tmp/current-event-detail")),),
            _repository_root=Path("/tmp/repository"),
        ),
        "_target_event_id": SYNTHETIC_EVENT_ID,
        "_legacy_reconciliation_receipt_directory": "receipt",
        "_legacy_reconciliation_source_bundle": "source",
        "_legacy_review_decisions": (),
        "_legacy_repository_root": Path("/tmp/legacy"),
        "_early_payout_settlement_receipt": None,
        "_early_payout_settlement_receipt_bytes": None,
    }
    for k, v in fields.items():
        object.__setattr__(source_mapping, k, v)
    return source_mapping


@contextlib.contextmanager
def synthetic_harness_scope(
    source_mapping: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    inventory: live.SportyBetLiveEventQuoteInventory,
):
    """Scoped context manager stubbing verification and bundle builder for offline evaluation."""
    orig_verify = quotes.mapping.verify_current_direct_provider_canonical_mapping_rebind
    orig_build = quotes.live.build_live_event_quote_inventory
    quotes.mapping.verify_current_direct_provider_canonical_mapping_rebind = lambda v: source_mapping
    quotes.live.build_live_event_quote_inventory = lambda d, repository_root=None: inventory
    try:
        yield
    finally:
        quotes.mapping.verify_current_direct_provider_canonical_mapping_rebind = orig_verify
        quotes.live.build_live_event_quote_inventory = orig_build


def _make_fixture_state():
    """Construct a production FixtureStateV2Snapshot with all supported context facts."""
    facts = (
        FixtureIntelligenceFact(
            category=IntelligenceCategory.FORM,
            field="home_form",
            status=IntelligenceFactStatus.SUPPORTED,
            value=0.72,
            source_provider="ROUTER_TEST_SOURCE",
            source_role=SourceRole.VERIFIED_EXTERNAL,
            source_reference="router:test:home_form:1",
            observed_at=SYNTHETIC_OBSERVED_TIME,
            evidence_file_path="evidence/router/1.json",
            evidence_sha256="1" * 64,
            notes="Router test evidence.",
        ),
        FixtureIntelligenceFact(
            category=IntelligenceCategory.FORM,
            field="away_form",
            status=IntelligenceFactStatus.SUPPORTED,
            value=0.61,
            source_provider="ROUTER_TEST_SOURCE",
            source_role=SourceRole.VERIFIED_EXTERNAL,
            source_reference="router:test:away_form:2",
            observed_at=SYNTHETIC_OBSERVED_TIME,
            evidence_file_path="evidence/router/2.json",
            evidence_sha256="2" * 64,
            notes="Router test evidence.",
        ),
        FixtureIntelligenceFact(
            category=IntelligenceCategory.PERFORMANCE,
            field="home_elo",
            status=IntelligenceFactStatus.SUPPORTED,
            value=1612,
            source_provider="ROUTER_TEST_SOURCE",
            source_role=SourceRole.VERIFIED_EXTERNAL,
            source_reference="router:test:home_elo:3",
            observed_at=SYNTHETIC_OBSERVED_TIME,
            evidence_file_path="evidence/router/3.json",
            evidence_sha256="3" * 64,
            notes="Router test evidence.",
        ),
        FixtureIntelligenceFact(
            category=IntelligenceCategory.PERFORMANCE,
            field="away_elo",
            status=IntelligenceFactStatus.SUPPORTED,
            value=1548,
            source_provider="ROUTER_TEST_SOURCE",
            source_role=SourceRole.VERIFIED_EXTERNAL,
            source_reference="router:test:away_elo:4",
            observed_at=SYNTHETIC_OBSERVED_TIME,
            evidence_file_path="evidence/router/4.json",
            evidence_sha256="4" * 64,
            notes="Router test evidence.",
        ),
        FixtureIntelligenceFact(
            category=IntelligenceCategory.SCHEDULE_LOAD,
            field="fatigue",
            status=IntelligenceFactStatus.SUPPORTED,
            value=0.23,
            source_provider="ROUTER_TEST_SOURCE",
            source_role=SourceRole.VERIFIED_EXTERNAL,
            source_reference="router:test:fatigue:5",
            observed_at=SYNTHETIC_OBSERVED_TIME,
            evidence_file_path="evidence/router/5.json",
            evidence_sha256="5" * 64,
            notes="Router test evidence.",
        ),
        FixtureIntelligenceFact(
            category=IntelligenceCategory.FIXTURE_CONTEXT,
            field="live_data_freshness",
            status=IntelligenceFactStatus.SUPPORTED,
            value=0.95,
            source_provider="ROUTER_TEST_SOURCE",
            source_role=SourceRole.VERIFIED_EXTERNAL,
            source_reference="router:test:live_data_freshness:6",
            observed_at=SYNTHETIC_OBSERVED_TIME,
            evidence_file_path="evidence/router/6.json",
            evidence_sha256="6" * 64,
            notes="Router test evidence.",
        ),
    )
    return build_fixture_state_v2_snapshot(
        build_snapshot(
            SYNTHETIC_FIXTURE_ID,
            SYNTHETIC_KICKOFF_TIME,
            SYNTHETIC_EVALUATION_TIME - timedelta(minutes=1),
            facts,
        )
    )


def run_p0_1_acceptance() -> dict[str, Any]:
    """P0-1: Execute real canonical Price-All when exact provider quote is absent.

    Demonstrates that absence of an exact quote produces the fail-closed
    disposition UNPRICED_NO_EXACT_QUOTE from Price-All, and routing the verified
    evaluation results in NO_BET with selected_opportunity_id=None.
    """
    sel_1 = _make_selection("1", "Match Result", None, "1", "Home", "2.00", 2.0)
    inventory = live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=SYNTHETIC_EVENT_ID,
        home_team_name="Fiorentina",
        away_team_name="Napoli",
        kickoff_utc=SYNTHETIC_KICKOFF_TIME,
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        observed_at=SYNTHETIC_EVALUATION_TIME - timedelta(seconds=60),
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256="a" * 64,
        source_raw_sha256="b" * 64,
        selections=(sel_1,),
    )
    mapped_1 = _make_mapped_selection(
        inventory, "1", "Match Result", None, "1", "Home", MarketId.MATCH_RESULT, OutcomeId.HOME, None
    )
    source_mapping = _make_source_mapping(inventory, (mapped_1,))

    with synthetic_harness_scope(source_mapping, inventory):
        bundle = quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=source_mapping,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        # Candidate is BTTS YES, for which no quote exists in inventory
        candidate = _make_candidate(MarketId.BTTS, OutcomeId.YES, None, (0.52, 0.48))
        eval_result = canonical_price.price_all_as_of(
            (candidate,),
            bundle,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        first_result = eval_result.results[0]
        disposition = first_result.disposition
        verified_eval = canonical_price.verify_price_all_evaluation(eval_result)
        fixture_state = _make_fixture_state()
        decision = canonical_router.route(
            verified_eval,
            fixture_state=fixture_state,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )

    avoids_defect = (
        disposition is PriceDisposition.UNPRICED_NO_EXACT_QUOTE
        and decision.decision_status is RouterDecisionStatus.NO_BET
        and decision.selected_opportunity_id is None
    )

    return {
        "canonical_avoids_defect": avoids_defect,
        "canonical_property": "Absence of exact provider quote causes canonical Price-All to produce UNPRICED_NO_EXACT_QUOTE and Router to output NO_BET without selection.",
        "case_id": "LEGACY_SELECTOR_NO_QUOTE_RECOMMENDATION",
        "execution_evidence": {
            "disposition": disposition.value,
            "router_status": decision.decision_status.value,
            "selected_opportunity_id": decision.selected_opportunity_id,
            "production_apis_executed": [
                "domain.price_all.price_all_as_of",
                "domain.price_all.verify_price_all_evaluation",
                "domain.market_router_canonical_adapter.route",
            ],
        },
        "label": "SYNTHETIC_P0_DEFECT_CLASS",
        "observed_canonical_behavior": (
            f"Real Price-All evaluated candidate without quote to {disposition.value}; "
            f"subsequent canonical routing confirmed {decision.decision_status.value} "
            f"with selected_opportunity_id=None."
        ),
        "result": "PASS" if avoids_defect else "FAIL",
    }


def run_p0_2_acceptance() -> dict[str, Any]:
    """P0-2: Execute real canonical Price-All and Router under two distinct provider price states.

    Demonstrates that net expected value, verified Price-All evaluations, and downstream
    Router selection change as a direct consequence of provider quote pricing:
    - State A (odds 1.50): EV = -0.025, verified Price-All, Router NO_BET (non-selectable).
    - State B (odds 2.10): EV = +0.365, verified Price-All, Router SELECTED.
    """
    candidate = _make_candidate(MarketId.MATCH_RESULT, OutcomeId.HOME, None, (0.65, 0.20, 0.15))

    # State A: Odds 1.50 (with complete partition for de-vig)
    sel_a1 = _make_selection("1", "Match Result", None, "1", "Home", "1.50", 1.50)
    sel_ax = _make_selection("1", "Match Result", None, "2", "Draw", "4.00", 4.00)
    sel_a2 = _make_selection("1", "Match Result", None, "3", "Away", "6.00", 6.00)
    inv_a = live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=SYNTHETIC_EVENT_ID,
        home_team_name="Fiorentina",
        away_team_name="Napoli",
        kickoff_utc=SYNTHETIC_KICKOFF_TIME,
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        observed_at=SYNTHETIC_EVALUATION_TIME - timedelta(seconds=60),
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256="a" * 64,
        source_raw_sha256="b" * 64,
        selections=(sel_a1, sel_ax, sel_a2),
    )
    map_a1 = _make_mapped_selection(inv_a, "1", "Match Result", None, "1", "Home", MarketId.MATCH_RESULT, OutcomeId.HOME, None)
    map_ax = _make_mapped_selection(inv_a, "1", "Match Result", None, "2", "Draw", MarketId.MATCH_RESULT, OutcomeId.DRAW, None)
    map_a2 = _make_mapped_selection(inv_a, "1", "Match Result", None, "3", "Away", MarketId.MATCH_RESULT, OutcomeId.AWAY, None)
    sm_a = _make_source_mapping(inv_a, (map_a1, map_ax, map_a2))

    with synthetic_harness_scope(sm_a, inv_a):
        bundle_a = quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=sm_a,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        eval_a = canonical_price.price_all_as_of(
            (candidate,),
            bundle_a,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        res_a = eval_a.results[0]
        verified_eval_a = canonical_price.verify_price_all_evaluation(eval_a)
        fixture_state = _make_fixture_state()
        dec_a = canonical_router.route(
            verified_eval_a,
            fixture_state=fixture_state,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )

    # State B: Odds 2.10 (with complete partition for de-vig)
    sel_b1 = _make_selection("1", "Match Result", None, "1", "Home", "2.10", 2.10)
    sel_bx = _make_selection("1", "Match Result", None, "2", "Draw", "3.20", 3.20)
    sel_b2 = _make_selection("1", "Match Result", None, "3", "Away", "3.50", 3.50)
    inv_b = live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=SYNTHETIC_EVENT_ID,
        home_team_name="Fiorentina",
        away_team_name="Napoli",
        kickoff_utc=SYNTHETIC_KICKOFF_TIME,
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        observed_at=SYNTHETIC_EVALUATION_TIME - timedelta(seconds=60),
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256="c" * 64,
        source_raw_sha256="d" * 64,
        selections=(sel_b1, sel_bx, sel_b2),
    )
    map_b1 = _make_mapped_selection(inv_b, "1", "Match Result", None, "1", "Home", MarketId.MATCH_RESULT, OutcomeId.HOME, None)
    map_bx = _make_mapped_selection(inv_b, "1", "Match Result", None, "2", "Draw", MarketId.MATCH_RESULT, OutcomeId.DRAW, None)
    map_b2 = _make_mapped_selection(inv_b, "1", "Match Result", None, "3", "Away", MarketId.MATCH_RESULT, OutcomeId.AWAY, None)
    sm_b = _make_source_mapping(inv_b, (map_b1, map_bx, map_b2))

    with synthetic_harness_scope(sm_b, inv_b):
        bundle_b = quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=sm_b,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        eval_b = canonical_price.price_all_as_of(
            (candidate,),
            bundle_b,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        res_b = eval_b.results[0]
        verified_eval_b = canonical_price.verify_price_all_evaluation(eval_b)
        dec_b = canonical_router.route(
            verified_eval_b,
            fixture_state=fixture_state,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )

    ev_a = round(res_a.net_expected_value, 6) if res_a.net_expected_value is not None else None
    ev_b = round(res_b.net_expected_value, 6) if res_b.net_expected_value is not None else None
    quote_sha_a = res_a.quote.quote_identity[-1] if (res_a.quote and res_a.quote.quote_identity) else None
    quote_sha_b = res_b.quote.quote_identity[-1] if (res_b.quote and res_b.quote.quote_identity) else None

    price_derived_behavior_valid = (
        quote_sha_a != quote_sha_b
        and res_a.quote.decimal_odds != res_b.quote.decimal_odds
        and ev_a != ev_b
        and ev_a == -0.025
        and ev_b == 0.365
        and verified_eval_a is not None
        and verified_eval_b is not None
        and dec_a.decision_status is RouterDecisionStatus.NO_BET
        and dec_a.selected_opportunity_id is None
        and dec_b.decision_status is RouterDecisionStatus.SELECTED
        and dec_b.selected_opportunity_id is not None
    )

    selected_pred_id_b = (
        dec_b.selected_opportunity.prediction_identity_sha256
        if dec_b.selected_opportunity
        else None
    )

    return {
        "canonical_avoids_defect": price_derived_behavior_valid,
        "canonical_property": "Provider pricing directly participates in canonical Price-All net-expected-value calculation, verification, and downstream Router selection.",
        "case_id": "LEGACY_SELECTOR_QUOTE_INDEPENDENT_OUTPUT",
        "execution_evidence": {
            "state_a": {
                "decimal_odds": res_a.quote.decimal_odds if res_a.quote else None,
                "disposition": res_a.disposition.value,
                "net_expected_value": ev_a,
                "quote_identity": quote_sha_a,
                "router_status": dec_a.decision_status.value,
                "selected_opportunity_id": dec_a.selected_opportunity_id,
                "selected_prediction_identity": None,
                "verified_evaluation": True,
            },
            "state_b": {
                "decimal_odds": res_b.quote.decimal_odds if res_b.quote else None,
                "disposition": res_b.disposition.value,
                "net_expected_value": ev_b,
                "quote_identity": quote_sha_b,
                "router_status": dec_b.decision_status.value,
                "selected_opportunity_id": dec_b.selected_opportunity_id,
                "selected_prediction_identity": selected_pred_id_b,
                "verified_evaluation": True,
            },
            "price_derived_ev_change": (ev_a != ev_b),
            "production_apis_executed": [
                "domain.price_all.price_all_as_of",
                "domain.price_all.verify_price_all_evaluation",
                "domain.market_router_canonical_adapter.route",
            ],
        },
        "label": "SYNTHETIC_P0_DEFECT_CLASS",
        "observed_canonical_behavior": (
            f"Under quote A (odds 1.50), real Price-All derived EV={ev_a} bound to {quote_sha_a} "
            f"producing Router {dec_a.decision_status.value}; under quote B (odds 2.10), real "
            f"Price-All derived EV={ev_b} bound to {quote_sha_b} producing Router {dec_b.decision_status.value} "
            f"with selected_opportunity_id={dec_b.selected_opportunity_id}. Net expected value and "
            f"downstream routing respond directly to provider pricing."
        ),
        "result": "PASS" if price_derived_behavior_valid else "FAIL",
    }


def run_p0_3_acceptance() -> dict[str, Any]:
    """P0-3: Execute real canonical Price-All when provider market is currently unavailable.

    Demonstrates that a bookable=False quote goes through the real Price-All seam
    and produces UNPRICED_CURRENTLY_UNAVAILABLE, which cannot become a selected opportunity.
    """
    sel_unavail = _make_selection(
        "1", "Match Result", None, "1", "Home", "2.00", 2.00, bookable=False
    )
    inv_unavail = live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=SYNTHETIC_EVENT_ID,
        home_team_name="Fiorentina",
        away_team_name="Napoli",
        kickoff_utc=SYNTHETIC_KICKOFF_TIME,
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        observed_at=SYNTHETIC_EVALUATION_TIME - timedelta(seconds=60),
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256="e" * 64,
        source_raw_sha256="f" * 64,
        selections=(sel_unavail,),
    )
    mapped_unavail = _make_mapped_selection(
        inv_unavail, "1", "Match Result", None, "1", "Home", MarketId.MATCH_RESULT, OutcomeId.HOME, None, bookable=False
    )
    sm_unavail = _make_source_mapping(inv_unavail, (mapped_unavail,))

    with synthetic_harness_scope(sm_unavail, inv_unavail):
        bundle_unavail = quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=sm_unavail,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        cand_unavail = _make_candidate(MarketId.MATCH_RESULT, OutcomeId.HOME, None, (0.60, 0.25, 0.15))
        eval_unavail = canonical_price.price_all_as_of(
            (cand_unavail,),
            bundle_unavail,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        res_u = eval_unavail.results[0]
        disposition = res_u.disposition
        verified_eval = canonical_price.verify_price_all_evaluation(eval_unavail)
        fixture_state = _make_fixture_state()
        decision = canonical_router.route(
            verified_eval,
            fixture_state=fixture_state,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )

    avoids_defect = (
        disposition is PriceDisposition.UNPRICED_CURRENTLY_UNAVAILABLE
        and decision.decision_status is RouterDecisionStatus.NO_BET
        and decision.selected_opportunity_id is None
    )

    return {
        "canonical_avoids_defect": avoids_defect,
        "canonical_property": "Provider market unavailability produces explicit UNPRICED_CURRENTLY_UNAVAILABLE disposition through real Price-All, preventing selection in Router.",
        "case_id": "LEGACY_SELECTOR_NO_PROVIDER_FAIL_CLOSED_DISPOSITION",
        "execution_evidence": {
            "disposition": disposition.value,
            "router_status": decision.decision_status.value,
            "selected_opportunity_id": decision.selected_opportunity_id,
            "production_apis_executed": [
                "domain.price_all.price_all_as_of",
                "domain.price_all.verify_price_all_evaluation",
                "domain.market_router_canonical_adapter.route",
            ],
        },
        "label": "SYNTHETIC_P0_DEFECT_CLASS",
        "observed_canonical_behavior": (
            f"Provider-unavailable quote evaluated through real Price-All to {disposition.value}; "
            f"Router produced {decision.decision_status.value} with selected_opportunity_id=None."
        ),
        "result": "PASS" if avoids_defect else "FAIL",
    }


def run_p0_4_acceptance() -> dict[str, Any]:
    """P0-4: Attempt to resolve ad-hoc noncanonical composite label through canonical market contracts."""
    legacy_label = "Home or Over 1.5"
    rejected_by_canonical = False
    rejection_error_type = ""
    try:
        resolve_legacy_selection(legacy_label)
    except UnknownSelectionError as exc:
        rejected_by_canonical = True
        rejection_error_type = type(exc).__name__
    except Exception as exc:
        rejected_by_canonical = True
        rejection_error_type = type(exc).__name__

    try:
        canonicalize_market_id(legacy_label)
        rejected_by_market_canonicalizer = False
    except UnknownMarketError:
        rejected_by_market_canonicalizer = True

    combos_strictly_rejected = rejected_by_canonical and rejected_by_market_canonicalizer
    return {
        "canonical_avoids_defect": combos_strictly_rejected,
        "canonical_property": "Decision authority requires exact registered canonical MarketId and OutcomeId identities.",
        "case_id": "LEGACY_SELECTOR_NONCANONICAL_OVER15_COMBO",
        "execution_evidence": {
            "rejected_by_legacy_resolver": rejected_by_canonical,
            "rejected_by_market_canonicalizer": rejected_by_market_canonicalizer,
            "rejection_error_type": rejection_error_type,
        },
        "label": "SYNTHETIC_P0_DEFECT_CLASS",
        "observed_canonical_behavior": (
            f"Ad-hoc label '{legacy_label}' was rejected by canonical market contracts with "
            f"{rejection_error_type}; non-registered composite labels cannot enter canonical authority."
        ),
        "result": "PASS" if combos_strictly_rejected else "FAIL",
    }


def run_p0_5_acceptance() -> dict[str, Any]:
    """P0-5: Evaluate tie resolution order independence via narrow rank key and public route integration."""
    # 1. Narrow unit-level rank key proof
    def _make_opp(token: str, market: MarketId, outcome: OutcomeId, line: float | None, odds: float, opp_id: str, quote_sha: str, quote_age: float):
        return canonical_router.RouterOpportunity(
            opportunity_id=opp_id,
            prediction_identity_sha256=canonical_router._prediction_identity_sha256(
                SYNTHETIC_FIXTURE_ID, market, outcome, line
            ),
            fixture_id=SYNTHETIC_FIXTURE_ID,
            event_id=SYNTHETIC_EVENT_ID,
            market_id=market,
            outcome_id=outcome,
            line=line,
            provider_market_id="pm1",
            provider_outcome_id="po1",
            provider_specifier=None,
            provider_market_name="pm",
            provider_outcome_name="po",
            decimal_odds=odds,
            quote_sha256=quote_sha,
            quote_observed_at=None,
            router_quote_age_seconds=quote_age,
            current_inventory_sha256="1" * 64,
            source_manifest_sha256="2" * 64,
            source_raw_sha256="3" * 64,
            current_mapping_rebind_sha256="4" * 64,
            current_mapping_contract_sha256="5" * 64,
            source_current_reconciliation_sha256="6" * 64,
            source_legacy_mapping_sha256="7" * 64,
            fair_probability=0.5,
            variants=(),
            robust_net_expected_value=0.10,
            best_net_expected_value=0.10,
            ev_spread=0.0,
            event_probability_floor=0.70,
            robust_edge=0.20,
            prediction_confidence=0.70,
            prediction_confidence_method="SCALAR",
            model_agreement_status=None,
            context_gate_passed=True,
            route_source_freshness_passed=True,
            source_v3_eligibility=OpportunityEligibility.ELIGIBLE,
            eligibility=OpportunityEligibility.ELIGIBLE,
            rejection_reasons=(),
        )

    opp_narrow_x = _make_opp(
        "x", MarketId.MATCH_RESULT, OutcomeId.HOME, None, 1.50, "zzz" * 21 + "z", "1" * 64, 800.0
    )
    opp_narrow_y = _make_opp(
        "y", MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.5, 2.20, "aaa" * 21 + "a", "2" * 64, 1.0
    )

    ranked_ab, eligible_ab, _ = canonical_router._rank_opportunities([opp_narrow_x, opp_narrow_y])
    ranked_ba, eligible_ba, _ = canonical_router._rank_opportunities([opp_narrow_y, opp_narrow_x])

    narrow_rank_ok = (
        len(eligible_ab) == 2
        and len(eligible_ba) == 2
        and eligible_ab[0].market_id is MarketId.MATCH_RESULT
        and eligible_ba[0].market_id is MarketId.MATCH_RESULT
    )

    # 2. Public route integration proof with complete partitions priced via real Price-All
    # Candidate X (Match Result Home @ 2.00, prob 0.60 -> EV 0.20, confidence 0.60)
    # Candidate Y (BTTS Yes @ 2.00, prob 0.60 -> EV 0.20, confidence 0.60)
    # Both are priced via real Price-All and verified, yielding a genuine equal tie on rank inputs.
    sel_1 = _make_selection("1", "Match Result", None, "1", "Home", "2.00", 2.0)
    sel_x = _make_selection("1", "Match Result", None, "2", "Draw", "4.00", 4.0)
    sel_2 = _make_selection("1", "Match Result", None, "3", "Away", "4.00", 4.0)
    sel_btts_y = _make_selection("29", "GG/NG", None, "74", "Yes", "2.00", 2.0)
    sel_btts_n = _make_selection("29", "GG/NG", None, "76", "No", "2.00", 2.0)

    inventory = live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=SYNTHETIC_EVENT_ID,
        home_team_name="Fiorentina",
        away_team_name="Napoli",
        kickoff_utc=SYNTHETIC_KICKOFF_TIME,
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        observed_at=SYNTHETIC_EVALUATION_TIME - timedelta(seconds=60),
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256="a" * 64,
        source_raw_sha256="b" * 64,
        selections=(sel_1, sel_x, sel_2, sel_btts_y, sel_btts_n),
    )

    map_1 = _make_mapped_selection(inventory, "1", "Match Result", None, "1", "Home", MarketId.MATCH_RESULT, OutcomeId.HOME, None)
    map_x = _make_mapped_selection(inventory, "1", "Match Result", None, "2", "Draw", MarketId.MATCH_RESULT, OutcomeId.DRAW, None)
    map_2 = _make_mapped_selection(inventory, "1", "Match Result", None, "3", "Away", MarketId.MATCH_RESULT, OutcomeId.AWAY, None)
    map_by = _make_mapped_selection(inventory, "29", "GG/NG", None, "74", "Yes", MarketId.BTTS, OutcomeId.YES, None)
    map_bn = _make_mapped_selection(inventory, "29", "GG/NG", None, "76", "No", MarketId.BTTS, OutcomeId.NO, None)

    source_mapping = _make_source_mapping(inventory, (map_1, map_x, map_2, map_by, map_bn))

    with synthetic_harness_scope(source_mapping, inventory):
        bundle = quotes.issue_current_direct_provider_mapped_quotes_as_of(
            source_mapping=source_mapping,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        cand_mr = _make_candidate(MarketId.MATCH_RESULT, OutcomeId.HOME, None, (0.60, 0.25, 0.15))
        cand_btts = _make_candidate(MarketId.BTTS, OutcomeId.YES, None, (0.60, 0.40))

        eval_xy = canonical_price.price_all_as_of((cand_mr, cand_btts), bundle, evaluation_time=SYNTHETIC_EVALUATION_TIME)
        eval_yx = canonical_price.price_all_as_of((cand_btts, cand_mr), bundle, evaluation_time=SYNTHETIC_EVALUATION_TIME)

        verified_xy = canonical_price.verify_price_all_evaluation(eval_xy)
        verified_yx = canonical_price.verify_price_all_evaluation(eval_yx)

        fixture_state = _make_fixture_state()
        dec_xy = canonical_router.route(
            verified_xy,
            fixture_state=fixture_state,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )
        dec_yx = canonical_router.route(
            verified_yx,
            fixture_state=fixture_state,
            evaluation_time=SYNTHETIC_EVALUATION_TIME,
        )

    # Extract the two routed opportunities from dec_xy to verify genuine tie inputs
    opps_by_market = {opp.market_id: opp for opp in dec_xy.opportunities}
    opp_mr = opps_by_market[MarketId.MATCH_RESULT]
    opp_btts = opps_by_market[MarketId.BTTS]

    cand_x_info = {
        "market": opp_mr.market_id.value,
        "outcome": opp_mr.outcome_id.value,
        "line": opp_mr.line,
        "robust_net_expected_value": opp_mr.robust_net_expected_value,
        "prediction_confidence": opp_mr.prediction_confidence,
        "prediction_identity_sha256": opp_mr.prediction_identity_sha256,
        "opportunity_id": opp_mr.opportunity_id,
        "quote_identity": opp_mr.quote_sha256,
    }
    cand_y_info = {
        "market": opp_btts.market_id.value,
        "outcome": opp_btts.outcome_id.value,
        "line": opp_btts.line,
        "robust_net_expected_value": opp_btts.robust_net_expected_value,
        "prediction_confidence": opp_btts.prediction_confidence,
        "prediction_identity_sha256": opp_btts.prediction_identity_sha256,
        "opportunity_id": opp_btts.opportunity_id,
        "quote_identity": opp_btts.quote_sha256,
    }

    tie_inputs_equal = (
        opp_mr.robust_net_expected_value is not None
        and opp_btts.robust_net_expected_value is not None
        and opp_mr.robust_net_expected_value == opp_btts.robust_net_expected_value
        and opp_mr.prediction_confidence == opp_btts.prediction_confidence
    )
    distinct_predictions = (opp_mr.prediction_identity_sha256 != opp_btts.prediction_identity_sha256)

    selected_pred_id_xy = dec_xy.selected_opportunity.prediction_identity_sha256 if dec_xy.selected_opportunity else None
    selected_pred_id_yx = dec_yx.selected_opportunity.prediction_identity_sha256 if dec_yx.selected_opportunity else None

    # Deterministic tie-breaking winner:
    # Under equal robust EV and equal confidence, canonical prediction key decides:
    # ("BTTS", "YES", "NONE") < ("MATCH_RESULT", "HOME", "NONE"), so BTTS YES must win under both orders.
    public_route_ok = (
        tie_inputs_equal
        and distinct_predictions
        and dec_xy.decision_status is RouterDecisionStatus.SELECTED
        and dec_yx.decision_status is RouterDecisionStatus.SELECTED
        and dec_xy.selected_opportunity_id is not None
        and dec_yx.selected_opportunity_id is not None
        and selected_pred_id_xy is not None
        and selected_pred_id_xy == selected_pred_id_yx
        and selected_pred_id_xy == opp_btts.prediction_identity_sha256
    )

    avoids_defect = narrow_rank_ok and public_route_ok

    return {
        "canonical_avoids_defect": avoids_defect,
        "canonical_property": "Deterministic tie-breaking prioritizes canonical prediction identity key (market_id, outcome_id, line), independent of construction order, opportunity ID, or quote attributes.",
        "case_id": "LEGACY_SELECTOR_CONSTRUCTION_ORDER_TIE",
        "execution_evidence": {
            "candidate_x": cand_x_info,
            "candidate_y": cand_y_info,
            "narrow_rank_ok": narrow_rank_ok,
            "public_route_ok": public_route_ok,
            "ranking_authority": [
                "robust_net_expected_value (descending)",
                "prediction_confidence (descending)",
                "canonical prediction key (market_id, outcome_id, line) (ascending)",
            ],
            "selected_opportunity_id_xy": dec_xy.selected_opportunity_id,
            "selected_opportunity_id_yx": dec_yx.selected_opportunity_id,
            "selected_prediction_identity_xy": selected_pred_id_xy,
            "selected_prediction_identity_yx": selected_pred_id_yx,
            "tie_inputs_equal": tie_inputs_equal,
            "production_apis_executed": [
                "domain.price_all.price_all_as_of",
                "domain.price_all.verify_price_all_evaluation",
                "domain.market_router_canonical_adapter.route",
            ],
        },
        "label": "SYNTHETIC_P0_DEFECT_CLASS",
        "observed_canonical_behavior": (
            f"Public integration constructed true-tie candidates (robust_ev={opp_mr.robust_net_expected_value}, "
            f"confidence={opp_mr.prediction_confidence}). Real Price-All and Router execution confirmed identical "
            f"selection {selected_pred_id_xy} dictated by canonical prediction key under both [X, Y] and [Y, X] "
            f"construction orders; candidate construction order has zero authority."
        ),
        "result": "PASS" if avoids_defect else "FAIL",
    }
