from __future__ import annotations

from datetime import date

import pytest

from domain import current_shadow_run_contract_adapter as adapter
from domain import run_contracts


SHA = "a" * 40
OBSERVED = "2026-09-10T12:34:56.123456Z"


def _request_policy(*, fixture_dates=None, fixture_scope="today"):
    return {
        "schema_version": 1,
        "dataset_name": adapter.CURRENT_REQUEST_DATASET,
        "fixture_scope": fixture_scope,
        "fixture_dates": fixture_dates,
        "rolling_date_policy": {"policy_id": "LEGACY_ROLLING_DATES"},
        "run199_identity_policy_id": "RUN199",
        "run199_identity_policy_sha256": "b" * 64,
        "row_local_quote_policy": {"policy_id": "ROW_LOCAL"},
        "current_asof_elo_only_policy": {"policy_id": "ELO_ONLY"},
        "authority": {
            "research_shadow_request": True,
            "production_model": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "bet": False,
            "wager_placed": False,
        },
        "wager_placed": False,
    }


def _authority():
    return {
        "research_shadow_current_runner": True,
        "research_shadow_source_acquisition": True,
        "research_shadow_probability_consumption": True,
        "research_shadow_price_all": True,
        "research_shadow_market_routing": True,
        "research_shadow_portfolio": True,
        "research_shadow_shortfall": True,
        "research_anonymous_share_code_generation": True,
        "provider_create_reload_verification": True,
        "production_model": False,
        "production_probability": False,
        "phase6": False,
        "production_price_all": False,
        "production_market_router": False,
        "production_portfolio": False,
        "production_selection": False,
        "production_sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }


def _leg(leg_id="LEG-1"):
    return {
        "leg_id": leg_id,
        "fixture_identity": "FOTMOB:123",
        "provider_event_id": "sr:match:123",
        "market_id": "MATCH_RESULT",
        "outcome_id": "HOME",
        "decimal_odds": 1.75,
        "quote_identity_sha256": "c" * 64,
    }


def _receipt(*, target=2, selected=1, include_final=True, include_portfolio=True, verified=True):
    legs = [_leg(f"LEG-{index + 1}") for index in range(selected)]
    portfolio = None
    if include_portfolio:
        portfolio = {
            "dataset_name": "athena-current-shadow-all-market-portfolio-v2",
            "requested_target_size": target,
            "selected_leg_count": selected,
            "selected_legs": legs,
            "reserve_legs": [],
            "shortfall": target - selected,
            "wager_placed": False,
        }
    share_receipt = None
    share_code = None
    share_url = None
    if verified:
        share_code = "ABC123"
        share_url = "https://example.test/ABC123"
        share_receipt = {
            "status": "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL" if selected < target else "RESEARCH_SHADOW_CODE_VERIFIED",
            "fresh_selected_legs": legs,
            "shareCode": share_code,
            "shareURL": share_url,
            "wager_placed": False,
        }
    return {
        "schema_version": 1,
        "dataset_name": adapter.CURRENT_RECEIPT_DATASET,
        "status": (
            "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL"
            if verified and selected < target
            else "RESEARCH_SHADOW_CODE_VERIFIED"
            if verified
            else "RESEARCH_NO_CODE_NO_BET"
        ),
        "observed_at": OBSERVED,
        "exact_commit_sha": SHA,
        "requested_target_size": target,
        "reviewed_fixture_count": 10,
        "reconciled_fixture_count": 6,
        "provider_event_count": 20,
        "priced_fixture_count": 6,
        "router_selected_count": 4,
        "router_no_bet_count": 2,
        "source_summary": {"source_raw_sha256": "d" * 64, "wager_placed": False},
        "portfolio": portfolio,
        "portfolio_sha256": None if portfolio is None else "e" * 64,
        "selected_leg_count": selected,
        "reserve_leg_count": 0,
        "shortfall": target - selected,
        "share_code_receipt": share_receipt,
        "fixture_funnel": {"unit": "fixture"},
        "opportunity_funnel": {"unit": "opportunity"},
        "market_diagnostics": [],
        "market_family_diagnostics": [],
        "final_selected_legs": legs if include_final else [],
        "fresh_fallback_events": [],
        "shareCode": share_code,
        "shareURL": share_url,
        "reasons": [],
        "authority": _authority(),
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }


def _stage(stage="PORTFOLIO"):
    return {
        "schema_version": 1,
        "dataset_name": adapter.CURRENT_RECEIPT_DATASET,
        "stage": stage,
        "stage_index": adapter.CURRENT_STAGE_SEQUENCE.index(stage),
        "observed_at": OBSERVED,
        "exact_commit_sha": SHA,
        "requested_target_size": 2,
        "wager_placed": False,
    }


def _progress(stage="PRICE_ALL_ROUTER"):
    return {
        "schema_version": 1,
        "dataset_name": adapter.CURRENT_RECEIPT_DATASET,
        "stage": stage,
        "stage_index": adapter.CURRENT_STAGE_SEQUENCE.index(stage),
        "progress_status": "COMPLETED",
        "observed_at": OBSERVED,
        "exact_commit_sha": SHA,
        "requested_target_size": 2,
        "counts": {
            "reviewed_fixture_count": 10,
            "reconciled_fixture_count": 6,
            "provider_event_count": 20,
            "priced_fixture_count": 6,
            "router_selected_count": 4,
            "router_no_bet_count": 2,
        },
        "source_summary": {"wager_placed": False},
        "wager_placed": False,
    }


def test_explicit_current_shadow_dates_map_to_concrete_canonical_dates():
    policy = _request_policy(fixture_dates=["20260910", "20260912"])
    request = adapter.adapt_current_shadow_request(target_size=25, request_policy=policy)
    assert request.dates == (date(2026, 9, 10), date(2026, 9, 12))
    assert request.target_legs == 25
    assert request.target_total_odds is None
    assert request.bookie == "sportybet"
    assert request.mode == "research_shadow"
    assert request.authority_profile == "SHADOW"
    assert request.create_share_code is True
    assert request.place_wager is False


def test_legacy_relative_scope_requires_caller_supplied_concrete_dates():
    policy = _request_policy(fixture_dates=None, fixture_scope="three-day")
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="resolved_dates"):
        adapter.adapt_current_shadow_request(target_size=20, request_policy=policy)
    request = adapter.adapt_current_shadow_request(
        target_size=20,
        request_policy=policy,
        resolved_dates=(date(2026, 9, 12), date(2026, 9, 10), date(2026, 9, 11)),
    )
    assert request.dates == (
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 12),
    )


def test_adapter_never_lets_resolved_dates_contradict_explicit_legacy_dates():
    policy = _request_policy(fixture_dates=["20260910", "20260912"])
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="contradict"):
        adapter.adapt_current_shadow_request(
            target_size=20,
            request_policy=policy,
            resolved_dates=(date(2026, 9, 10), date(2026, 9, 11)),
        )


def test_current_shadow_terminal_receipt_maps_without_losing_legacy_evidence():
    policy = _request_policy(fixture_dates=["20260910"])
    legacy = _receipt(target=2, selected=1)
    request = adapter.adapt_current_shadow_request(target_size=2, request_policy=policy)
    receipt = adapter.adapt_current_shadow_receipt(
        request=request,
        receipt_payload=legacy,
        request_policy=policy,
    )
    payload = receipt.to_dict()
    assert payload["counts"]["reviewed_fixture_count"] == 10
    assert payload["counts"]["selected_leg_count"] == 1
    assert payload["selected_legs"] == legacy["final_selected_legs"]
    assert payload["shortfall"] == 1
    assert payload["share_code_result"]["verified"] is True
    assert payload["share_code_result"]["share_code"] == "ABC123"
    assert payload["authority_manifest"]["authority_profile"] == "SHADOW"
    assert payload["authority_manifest"]["capabilities"]["provider_acquisition"] is True
    assert payload["authority_manifest"]["capabilities"]["share_code_generation"] is True
    assert payload["authority_manifest"]["capabilities"]["wager"] is False
    assert payload["wager_placed"] is False
    preserved = payload["evidence"]["legacy_current_shadow"]
    assert preserved["request_policy"] == policy
    assert preserved["receipt"] == legacy
    assert preserved["legacy_stage_history_complete"] is False


def test_adapter_uses_portfolio_selected_legs_when_no_final_delivery_legs_exist():
    policy = _request_policy(fixture_dates=["20260910"])
    legacy = _receipt(
        target=2,
        selected=1,
        include_final=False,
        include_portfolio=True,
        verified=False,
    )
    legacy["status"] = "RESEARCH_NO_CODE_REPRICE_REQUIRED"
    request = adapter.adapt_current_shadow_request(target_size=2, request_policy=policy)
    receipt = adapter.adapt_current_shadow_receipt(
        request=request,
        receipt_payload=legacy,
        request_policy=policy,
    )
    assert receipt.to_dict()["selected_legs"] == legacy["portfolio"]["selected_legs"]
    assert receipt.share_code_result is None


def test_positive_selected_count_without_concrete_legacy_legs_fails_closed():
    policy = _request_policy(fixture_dates=["20260910"])
    legacy = _receipt(
        target=2,
        selected=1,
        include_final=False,
        include_portfolio=False,
        verified=False,
    )
    request = adapter.adapt_current_shadow_request(target_size=2, request_policy=policy)
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="concrete selected legs"):
        adapter.adapt_current_shadow_receipt(
            request=request,
            receipt_payload=legacy,
            request_policy=policy,
        )


def test_zero_selection_no_bet_maps_to_truthful_full_shortfall():
    policy = _request_policy(fixture_dates=["20260910"])
    legacy = _receipt(
        target=25,
        selected=0,
        include_final=False,
        include_portfolio=False,
        verified=False,
    )
    legacy["router_selected_count"] = 0
    legacy["router_no_bet_count"] = 6
    request = adapter.adapt_current_shadow_request(target_size=25, request_policy=policy)
    receipt = adapter.adapt_current_shadow_receipt(
        request=request,
        receipt_payload=legacy,
        request_policy=policy,
    )
    assert receipt.selected_legs == ()
    assert receipt.shortfall == 25
    assert receipt.counts["selected_leg_count"] == 0


def test_only_actual_latest_stage_and_progress_checkpoints_are_adapted():
    policy = _request_policy(fixture_dates=["20260910"])
    legacy = _receipt(target=2, selected=1)
    request = adapter.adapt_current_shadow_request(target_size=2, request_policy=policy)
    stage = _stage()
    progress = _progress()
    receipt = adapter.adapt_current_shadow_receipt(
        request=request,
        receipt_payload=legacy,
        request_policy=policy,
        stage_payload=stage,
        progress_payload=progress,
    )
    assert [(item.stage, item.status) for item in receipt.stages] == [
        ("PORTFOLIO", "CHECKPOINTED"),
        ("PRICE_ALL_ROUTER", "COMPLETED"),
    ]
    evidence = receipt.to_dict()["evidence"]["legacy_current_shadow"]
    assert evidence["latest_stage_checkpoint"] == stage
    assert evidence["latest_progress_checkpoint"] == progress
    assert evidence["legacy_stage_history_complete"] is False


def test_adapter_rejects_target_shortfall_and_checkpoint_binding_drift():
    policy = _request_policy(fixture_dates=["20260910"])
    request = adapter.adapt_current_shadow_request(target_size=2, request_policy=policy)

    legacy = _receipt(target=3, selected=1)
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="target"):
        adapter.adapt_current_shadow_receipt(
            request=request,
            receipt_payload=legacy,
            request_policy=policy,
        )

    legacy = _receipt(target=2, selected=1)
    legacy["shortfall"] = 0
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="shortfall"):
        adapter.adapt_current_shadow_receipt(
            request=request,
            receipt_payload=legacy,
            request_policy=policy,
        )

    legacy = _receipt(target=2, selected=1)
    stage = _stage()
    stage["exact_commit_sha"] = "f" * 40
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="commit"):
        adapter.adapt_current_shadow_receipt(
            request=request,
            receipt_payload=legacy,
            request_policy=policy,
            stage_payload=stage,
        )


def test_adapter_rejects_any_legacy_wager_or_sensitive_authority_claim():
    policy = _request_policy(fixture_dates=["20260910"])
    request = adapter.adapt_current_shadow_request(target_size=2, request_policy=policy)

    for key in ("wager_placed", "stake_submitted", "sportybet_login_used"):
        legacy = _receipt(target=2, selected=1)
        legacy[key] = True
        with pytest.raises(adapter.CurrentShadowRunContractAdapterError):
            adapter.adapt_current_shadow_receipt(
                request=request,
                receipt_payload=legacy,
                request_policy=policy,
            )

    for key in ("login", "cookies", "wallet", "staking", "bet", "wager_placed", "production_selection"):
        legacy = _receipt(target=2, selected=1)
        legacy["authority"][key] = True
        with pytest.raises(adapter.CurrentShadowRunContractAdapterError):
            adapter.adapt_current_shadow_receipt(
                request=request,
                receipt_payload=legacy,
                request_policy=policy,
            )


def test_legacy_share_code_without_verification_receipt_is_never_promoted():
    policy = _request_policy(fixture_dates=["20260910"])
    legacy = _receipt(target=2, selected=1)
    legacy["share_code_receipt"] = None
    request = adapter.adapt_current_shadow_request(target_size=2, request_policy=policy)
    with pytest.raises(adapter.CurrentShadowRunContractAdapterError, match="verification receipt"):
        adapter.adapt_current_shadow_receipt(
            request=request,
            receipt_payload=legacy,
            request_policy=policy,
        )


def test_composed_adapter_produces_canonical_round_trippable_receipt():
    policy = _request_policy(fixture_dates=["20260910", "20260911"])
    legacy = _receipt(target=2, selected=1)
    receipt = adapter.adapt_current_shadow_run(
        target_size=2,
        request_policy=policy,
        receipt_payload=legacy,
    )
    raw = run_contracts.canonical_json_bytes(receipt)
    rebuilt = run_contracts.RunReceipt.from_json_bytes(raw)
    assert rebuilt.to_dict() == receipt.to_dict()
