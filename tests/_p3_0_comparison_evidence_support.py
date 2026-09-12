from __future__ import annotations

import ast
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

from domain import p3_0_comparison_evidence as evidence
from domain.markets import DecisionStatus, MarketId
from domain.market_probabilities import (
    MarketProbabilityBundle,
    MarketProbabilityDistribution,
    ProbabilityAvailability,
)
from services.analysis_pipeline import AnalysisPipeline

FIXTURE = "FOTMOB:fixture-100"
START = "2026-09-30T12:00:00.000000Z"
QUOTE = "2026-09-30T12:01:00.000000Z"
CANONICAL = "2026-09-30T12:02:00.000000Z"
LEGACY = "2026-09-30T12:03:00.000000Z"
END = "2026-09-30T12:04:00.000000Z"
KICKOFF = "2026-10-01T15:00:00.000000Z"


def _compact_sha(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _identity(**overrides):
    value = {
        "fixture_identity": FIXTURE,
        "fixture_identity_policy": "P3_0_EXACT_FOTMOB_RECONCILED_FIXTURE_ID_V1",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "home_source_id": None,
        "away_source_id": None,
        "competition_identity": None,
        "competition_name": "Test League",
        "kickoff": KICKOFF,
        "fixture_source": "FOTMOB",
        "fixture_source_event_id": "fixture-100",
        "fixture_source_observed_at": None,
        "fixture_source_artifact_sha256": None,
        "fixture_source_manifest_sha256": None,
    }
    value.update(overrides)
    return value


def _timing(**overrides):
    value = {
        "legacy_evidence_observed_at": LEGACY,
        "legacy_evaluation_time": LEGACY,
        "probability_evaluation_time": CANONICAL,
        "provider_quote_observed_at": QUOTE,
        "canonical_price_all_evaluation_time": CANONICAL,
        "canonical_router_evaluation_time": CANONICAL,
        "kickoff_time": KICKOFF,
    }
    value.update(overrides)
    return value


def _authority(**overrides):
    records = []
    for responsibility in sorted(evidence.EXPECTED_COMPONENTS):
        # Keep immutable reviewed component identities explicit in the test
        # corpus rather than reaching through a private implementation module.
        fallback = {
            "provider_market_semantics": ("737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830", "46eaf64b6704e1b7b47123a9a182346e0403cbe6"),
            "price_all_and_de_vig": ("30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425", "cf7214a6103d91a2974e3eb00c705f65c841d458"),
            "market_router": ("85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32", "3011b65fcd62e5ae91fcede967b8cba4f85cdda7"),
            "portfolio_optimizer": ("916247c4a891e3c0a2b8205b9d33000987471a54107f2b3d508c8e5ab1e9a99c", "d600d5d88baf5628df23441a9216c2fc68352e45"),
            "delivery_share_code_transport": ("ac73deca0834187480c656482a78f9048381fe2f07abacfe10b84d30c73502cb", "28c44656915607315e0227f54bcff7cc7af103c7"),
        }[responsibility]
        contract, blob = fallback
        records.append({
            "responsibility_id": responsibility,
            "component_id": evidence.EXPECTED_COMPONENTS[responsibility],
            "contract_sha256": contract,
            "artifact_git_blob_sha": blob,
            "allowed_profiles": ["SHADOW"],
            "main_authority": False,
        })
    value = {
        "canonical_core_policy_id": "ATHENA_SHARED_CANONICAL_CORE_V1",
        "canonical_core_contract_sha256": "af4a73f8852893e7391ae85bac092105d305fa5b9e77af273809fcdcb3dc4c4a",
        "authority_manifest_sha256": "d" * 64,
        "registry_canonical_sha256": "e" * 64,
        "authority_profile": "SHADOW",
        "resolved_components": records,
    }
    value.update(overrides)
    return value


def _probability():
    markets = tuple(
        MarketProbabilityDistribution(
            market_id=market,
            availability=ProbabilityAvailability.BLOCKED,
            topology=None,
            probability_method=None,
            probability_input_namespace=None,
            calibration_status=None,
            event_probabilities=(),
            settlement_distributions=(),
            blocker_reason="TEST_BLOCKED_WITHOUT_FABRICATION",
            source_projection_sha256=(f"{index + 1:x}" * 64)[:64],
        )
        for index, market in enumerate(MarketId)
    )
    bundle = MarketProbabilityBundle(
        fixture_identity=FIXTURE,
        score_grid=None,
        markets=markets,
        specialist_outputs=(),
        model_evidence={"artifact_sha256": "1" * 64},
    )
    return {
        "policy_id": bundle.to_dict()["policy_id"],
        "canonical_sha256": bundle.canonical_sha256,
        "payload": bundle.to_dict(),
    }


def _provider():
    return {
        "canonical_contract_sha256": "737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830",
        "registry_sha256": "2" * 64,
        "registry_policy_id": "PRB_EXACT_CURRENT_SPORTYBET_SEMANTIC_POLICIES_V1",
        "registry_evaluation_time": CANONICAL,
        "provider_event_id": "100",
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
        "fixture_reconciliation_sha256": "6" * 64,
    }


def _quote_row():
    payload = {
        "fixture_identity": FIXTURE,
        "provider_event_id": "100",
        "market_id": "MATCH_RESULT",
        "outcome_id": "HOME",
        "line": None,
        "provider_line": None,
        "provider_market_id": "1",
        "provider_market_name": "1X2",
        "provider_specifier": None,
        "provider_outcome_id": "1",
        "provider_outcome_name": "Home",
        "odds_raw": "1.50",
        "decimal_odds": 1.5,
        "observed_at": QUOTE,
        "kickoff_utc": KICKOFF,
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
        "provider_semantic_status": "SUPPORTED",
        "provider_registry_sha256": "2" * 64,
        "provider_observation_sha256": "8" * 64,
        "fixture_reconciliation_sha256": "6" * 64,
        "current_mapping_rebind_sha256": None,
        "bridge_bundle_sha256": None,
        "bookable": True,
    }
    return {**payload, "quote_identity_sha256": _compact_sha(payload)}


def _quote():
    core = {
        "fixture_identity": FIXTURE,
        "provider_event_id": "100",
        "evaluation_time": CANONICAL,
        "quotes": [_quote_row()],
    }
    return {**core, "canonical_sha256": evidence.canonical_sha256(core)}


def _price_result():
    return {
        "fixture_identity": FIXTURE,
        "market_id": "MATCH_RESULT",
        "outcome_id": "HOME",
        "line": None,
        "disposition": "PRICED",
        "model_probability": 0.6,
        "decimal_odds": 1.5,
        "quote_identity_sha256": _quote_row()["quote_identity_sha256"],
        "provider_event_id": "100",
        "prc_scan_sha256": "9" * 64,
        "prc_assessment_sha256": "a" * 64,
        "provider_registry_sha256": "2" * 64,
        "fixture_reconciliation_sha256": "6" * 64,
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
    }


def _price():
    payload = {
        "schema_version": 2,
        "dataset_name": "athena-current-shadow-all-market-price-all-router-v2",
        "fixture_identity": FIXTURE,
        "evaluation_time": CANONICAL,
        "results": [_price_result()],
        "authority": {"staking": False, "bet": False, "wager_placed": False},
        "wager_placed": False,
    }
    return {
        "owner_responsibility_id": "price_all_and_de_vig",
        "owner_component_id": "domain.price_all",
        "payload_kind": evidence.PRICE_OUTPUT_KIND,
        "payload_sha256": _compact_sha(payload),
        "payload": payload,
    }


def _router():
    price = _price()
    opportunity_id = "b" * 64
    payload = {
        "schema_version": 2,
        "dataset_name": "athena-current-shadow-all-market-price-all-router-v2",
        "fixture_identity": FIXTURE,
        "status": "SELECTED",
        "selected_opportunity_id": opportunity_id,
        "runner_up_opportunity_id": None,
        "strongest_rejected_opportunity_id": None,
        "opportunities": [{
            "opportunity_id": opportunity_id,
            "price_result": _price_result(),
            "eligibility": "ELIGIBLE",
            "rejection_reasons": [],
        }],
        "price_all_bundle_sha256": price["payload_sha256"],
        "router_policy_id": "TEST_ROUTER_POLICY",
        "authority": {"staking": False, "bet": False, "wager_placed": False},
        "value_first_selected_opportunity_id": opportunity_id,
        "value_first_runner_up_opportunity_id": None,
        "value_first_counterfactual_opportunity_id": None,
        "wager_placed": False,
    }
    return {
        "owner_responsibility_id": "market_router",
        "owner_component_id": "domain.market_router_canonical_adapter",
        "payload_kind": evidence.ROUTER_OUTPUT_KIND,
        "payload_sha256": _compact_sha(payload),
        "payload": payload,
    }


def _legacy_input():
    return {
        "fixture_id": FIXTURE,
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "home_id": 1,
        "away_id": 2,
        "match_date": KICKOFF,
        "data_source": "P3_0_E1_CURRENT_SHADOW_RECONCILED",
        "is_knockout": False,
    }


def _analysis(status="ANALYTICAL_CANDIDATE"):
    return {
        "decision_status": status,
        "recommended_analytical_verdict": "HOME_WIN",
        "bookmaker_odds": None,
        "viable_markets": [{"verdict": "HOME_WIN", "prob": 0.6, "kelly_stake_pct": 5.0}],
        "accumulator_eligible_selection": None,
        "no_bet_reasons": [],
        "evidence_report": {
            "final_decision": status,
            "decision_reasons": ["test"],
            "possession": {"home": 55.0, "away": 45.0},
            "market_evaluations": [{"market_id": "MATCH_RESULT", "kelly_stake_pct": 5.0}],
        },
    }


def _legacy_output():
    return evidence.project_legacy_output(
        _analysis("BET"),
        _analysis("ANALYTICAL_CANDIDATE"),
        {
            "fixture_id": FIXTURE,
            "fixture": "Alpha FC vs Beta FC",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "league": "Test League",
            "match_date": KICKOFF,
            "decision_status": "ANALYTICAL_CANDIDATE",
            "verdict": "HOME_WIN",
            "no_bet_reasons": ["legacy runtime authorization gate"],
            "evidence_report": _analysis()["evidence_report"],
            "source": "P3_0_E1_CURRENT_SHADOW_RECONCILED",
        },
    )


def _fixture_state():
    return {
        "fixture_identity": FIXTURE,
        "provider_event_id": "100",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "competition": "Test League",
        "kickoff_utc": KICKOFF,
        "source_observed_at": QUOTE,
        "fixture_reconciliation_sha256": "6" * 64,
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
    }


def _record(**overrides):
    values = dict(
        fixture_capture_id="FOTMOB-fixture-100",
        capture_id="capture-20260930-a",
        capture_started_at=START,
        capture_completed_at=END,
        legacy_identity=_identity(),
        canonical_identity=_identity(),
        timing=_timing(),
        canonical_authority=_authority(),
        legacy_input=_legacy_input(),
        legacy_output=_legacy_output(),
        canonical_fixture_state=_fixture_state(),
        probability_bundle=_probability(),
        provider_semantics=_provider(),
        quote_snapshot=_quote(),
        price_all_output=_price(),
        router_output=_router(),
    )
    values.update(overrides)
    return evidence.build_fixture_record(**values)


def _bundle(records=None):
    return evidence.build_capture_bundle(
        repository_commit_sha="c" * 40,
        capture_id="capture-20260930-a",
        capture_started_at=START,
        capture_completed_at=END,
        requested_dates=["20261001"],
        legacy_execution_identity={"path": "AnalysisPipeline.run_pipeline_snapshot"},
        canonical_execution_identity={"path": "Current Shadow Price-All -> Router"},
        authority_state={"main_authority": False, "authority_profile": "SHADOW", "wager_placed": False},
        source_artifacts=[{
            "fixture_identity": FIXTURE,
            "provider_event_id": "100",
            "source_raw_sha256": "3" * 64,
            "source_manifest_sha256": "4" * 64,
            "source_inventory_sha256": "5" * 64,
            "fixture_reconciliation_sha256": "6" * 64,
        }],
        fixture_records=[_record()] if records is None else records,
    )



__all__ = tuple(name for name in globals() if not name.startswith("__"))
