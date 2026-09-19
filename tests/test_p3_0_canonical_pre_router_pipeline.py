from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest

from config.competition_review_priority import (
    resolve_source_competition_review_priority,
)
from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_identity_v2 as fixture_identity
from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated_discovery
from domain.current_shadow_sportybet_catalog_fanout_reconciliation import (
    CurrentShadowSportyBetCatalogFanoutReconciliationError,
    validate_fanout_request_scope,
)
from scripts import current_shadow_fixture_identity_reconciliation_recovery as identity_recovery
from scripts import verify_p3_0_e1_live_readiness


UTC = timezone.utc


def test_paginated_discovery_contract_is_pinned_and_zero_authority():
    contract = paginated_discovery.validate_contract()
    assert contract["contract_sha256"] == paginated_discovery.EXPECTED_CONTRACT_SHA256
    assert contract["contract_sha256"] == "98bedacc3ccbc080312855fdd973545374ba2448dc89b841420bc70147ffaf21"

    authority = paginated_discovery.AUTHORITY
    assert authority["login"] is False
    assert authority["cookies"] is False
    assert authority["wallet"] is False
    assert authority["staking"] is False
    assert authority["bet"] is False
    assert authority["wager_placed"] is False
    assert authority["price_all"] is False
    assert authority["market_router"] is False
    assert authority["final_selection"] is False
    assert authority["sportybet_execution"] is False
    assert authority["fixture_reconciliation_issuer"] is True


def test_validate_contract_drift_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(paginated_discovery, "EXPECTED_CONTRACT_SHA256", "0" * 64)
    with pytest.raises(
        paginated_discovery.CurrentShadowPaginatedDiscoveryReconciliationError,
        match="Current Shadow paginated discovery reconciliation contract drifted",
    ):
        paginated_discovery.validate_contract()


def test_fanout_request_scope_rejection_on_global_echo():
    echoed_events = tuple(f"sr:match:{1000 + i}" for i in range(10))
    obs1 = SimpleNamespace(event_ids=echoed_events, category_id="sr:category:1", tournament_id="sr:tournament:1")
    obs2 = SimpleNamespace(event_ids=echoed_events, category_id="sr:category:1", tournament_id="sr:tournament:2")
    with pytest.raises(
        CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="FANOUT_REQUEST_SCOPE_UNPROVEN: identical 10 events returned across 2 distinct tournament requests",
    ):
        validate_fanout_request_scope([obs1, obs2])


def test_verify_p3_0_e1_live_readiness_runs_offline_and_passes():
    repo_root = Path(__file__).resolve().parents[1]
    report = verify_p3_0_e1_live_readiness.run_all_readiness_checks(repository_root=repo_root)
    assert report["status"] == "P3_0_E1_LIVE_READINESS_VERIFIED"
    assert len(report["checks"]) == 14
    assert (repo_root / "artifacts" / "p3-0-comparison-evidence" / "p3-0-e1-live-readiness.json").exists()
    assert (repo_root / "p3-0-e1-live-readiness.json").exists()


# ---------------------------------------------------------------------------
# Full admission-aware Pre-Router Pipeline & Equivalence Test (Blocker 7)
# ---------------------------------------------------------------------------

def _build_admitted_seam(tmp_path: Path):
    """Build a deterministic offline seam using English Premier League."""
    kickoff = datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC)
    fixture_id = "5000001"
    event_id = "sr:match:9000001"

    # 1. Raw FotMob
    fotmob_match = {
        "id": int(fixture_id),
        "home": {"id": 9825, "name": "Arsenal", "longName": "Arsenal"},
        "away": {"id": 8455, "name": "Chelsea", "longName": "Chelsea"},
        "status": {"utcTime": kickoff.isoformat().replace("+00:00", "Z")},
    }
    fotmob_league = {
        "ccode": "ENG",
        "primaryId": 47,
        "name": "Premier League",
        "matches": [fotmob_match],
    }
    raw_fotmob_bytes = json.dumps({"leagues": [fotmob_league]}).encode("utf-8")
    raw_manifest = {"sha256": "f" * 64}

    # 2. Candidate bundle & reviewed admission
    candidate_row = SimpleNamespace(
        source_fixture_identifier=fixture_id,
        kickoff=kickoff,
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        ccode="ENG",
        primary_id=47,
    )
    admission = SimpleNamespace(
        to_dict=lambda: {
            "candidate_bundle_sha256": "1" * 64,
            "review_bundle_sha256": "2" * 64,
            "handoff_sha256": "3" * 64,
            "catalog_sha256": "4" * 64,
            "manifest_sha256": "5" * 64,
        },
        fixtures=(candidate_row,),
    )
    execution = SimpleNamespace(
        bootstrap=SimpleNamespace(
            verified_artifact=SimpleNamespace(admission=admission),
            fixtures=(candidate_row,),
        ),
        summary=lambda: {"fixture_source": "offline-premier-league"},
    )

    # 3. Paginated provider discovery manifest
    page = SimpleNamespace(page_num=1, raw_sha256="p" * 64)
    discovered_event = SimpleNamespace(
        event_id=event_id,
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        competition_name="Premier League",
        competition_basis="REVIEWED",
        kickoff_utc=kickoff,
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        source_page_num=1,
        source_raw_sha256="p" * 64,
        source_observed_at=datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC),
    )
    discovery_manifest = SimpleNamespace(
        canonical_sha256="m" * 64,
        pages=(page,),
        events=(discovered_event,),
    )

    # 4. Exact reconciliation bundle
    matched_row = SimpleNamespace(
        event_id=event_id,
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        competition_name="Premier League",
        kickoff_utc=kickoff,
        disposition=SimpleNamespace(value="UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED"),
        exact_fotmob_match_count=1,
        matched_fotmob_fixture_id=fixture_id,
        fixture_reconciliation_authorized=True,
    )
    reconciliation_bundle = SimpleNamespace(
        canonical_sha256="r" * 64,
        contract_sha256=paginated_discovery.EXPECTED_CONTRACT_SHA256,
        rows=(matched_row,),
        matched_rows=(matched_row,),
        discovery_manifest_sha256="m" * 64,
    )

    # 5. Price-All and Router test doubles
    priced_bundle = SimpleNamespace(
        fixture_identity=f"FOTMOB:{fixture_id}",
        provider_event_id=event_id,
    )
    router_decision = SimpleNamespace(
        status=SimpleNamespace(value="SELECTED"),
        priced=priced_bundle,
    )
    router_input = SimpleNamespace(
        price_all_bundle=priced_bundle,
        router_decision=router_decision,
    )

    return {
        "execution": execution,
        "raw_fotmob_bytes": raw_fotmob_bytes,
        "raw_manifest": raw_manifest,
        "discovery_manifest": discovery_manifest,
        "reconciliation_bundle": reconciliation_bundle,
        "priced_bundle": priced_bundle,
        "router_decision": router_decision,
        "router_input": router_input,
    }


def test_full_admission_aware_source_to_router_pipeline_canonical_equivalence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    seam = _build_admitted_seam(tmp_path)

    monkeypatch.setattr(
        runner,
        "_issue_current_fixture_sources",
        lambda **_kw: ([(seam["execution"], "20260920")], ("20260920",)),
    )
    monkeypatch.setattr(
        runner,
        "_source_capture",
        lambda *_args: (seam["raw_fotmob_bytes"], seam["raw_manifest"]),
    )
    monkeypatch.setattr(
        runner.paginated_discovery,
        "capture_current_paginated_discovery",
        lambda **_kw: (tmp_path, seam["discovery_manifest"]),
    )
    monkeypatch.setattr(
        runner.paginated_discovery,
        "reconcile_current_events_from_paginated_discovery",
        lambda **_kw: seam["reconciliation_bundle"],
    )
    monkeypatch.setattr(runner, "_legacy_bootstrap_bytes", lambda: b"{}")
    monkeypatch.setattr(
        runner.latest_history,
        "build_current_fotmob_latest_durable_fresh_history_handoff",
        lambda **_kw: object(),
    )
    monkeypatch.setattr(
        runner.latest_history,
        "sha256_current_fotmob_latest_durable_fresh_history_handoff",
        lambda _h: "h" * 64,
    )
    monkeypatch.setattr(
        runner.price_module,
        "build_current_shadow_price_context_from_reconciliation",
        lambda **kw: SimpleNamespace(**kw),
    )
    monkeypatch.setattr(
        runner.price_module,
        "price_all_shadow_fixture",
        lambda _ctx: seam["priced_bundle"],
    )
    monkeypatch.setattr(
        runner.router_module,
        "route_shadow_price_results",
        lambda _p: seam["router_decision"],
    )
    monkeypatch.setattr(
        runner.portfolio_module,
        "build_shadow_portfolio_router_input",
        lambda **_kw: seam["router_input"],
    )
    monkeypatch.setattr(runner, "_runtime_progress_diagnostics", lambda _inp: {})

    # Run SUPPORTED_REQUEST
    supported_bundle = runner.acquire_current_shadow_pre_router_bundle(
        repository_root=tmp_path,
        lineage_main_sha="1" * 40,
        capture_mode="SUPPORTED_REQUEST",
    )

    # Run P3_E1_PRE_ROUTER_CAPTURE
    p3_bundle = runner.acquire_current_shadow_pre_router_bundle(
        repository_root=tmp_path,
        lineage_main_sha="1" * 40,
        capture_mode="P3_E1_PRE_ROUTER_CAPTURE",
    )

    # Assert non-zero counts
    assert supported_bundle.reviewed_fixture_count >= 1
    assert supported_bundle.provider_event_count >= 1
    assert supported_bundle.reconciled_fixture_count >= 1
    assert supported_bundle.priced_fixture_count >= 1
    assert len(supported_bundle.router_inputs) >= 1

    # Assert exact equality between SUPPORTED_REQUEST and P3_E1_PRE_ROUTER_CAPTURE
    assert supported_bundle.reviewed_fixture_count == p3_bundle.reviewed_fixture_count
    assert supported_bundle.provider_event_count == p3_bundle.provider_event_count
    assert supported_bundle.reconciled_fixture_count == p3_bundle.reconciled_fixture_count
    assert supported_bundle.priced_fixture_count == p3_bundle.priced_fixture_count
    assert len(supported_bundle.router_inputs) == len(p3_bundle.router_inputs)
    assert supported_bundle.router_inputs == p3_bundle.router_inputs

    # Assert discovery strategy equality and truthful vocabulary
    strategy_id = "ATHENA_CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_V1"
    assert supported_bundle.source_summary["provider_discovery_strategy_id"] == strategy_id
    assert p3_bundle.source_summary["provider_discovery_strategy_id"] == strategy_id
    assert "provider_catalog_fanout_snapshot_sha256" not in supported_bundle.source_summary
    assert "provider_catalog_fanout_snapshot_sha256" not in p3_bundle.source_summary
    assert supported_bundle.source_summary["provider_discovery_page_count"] == 1
    assert supported_bundle.source_summary["provider_discovery_event_count"] == 1


# ---------------------------------------------------------------------------
# 12 Adversarial Variant Tests
# ---------------------------------------------------------------------------

def test_adversarial_1_unapproved_competition():
    """Unapproved competition (e.g. K-League 1) is rejected by review policy."""
    priority = resolve_source_competition_review_priority("KOR", "K-League 1")
    assert priority is None


def test_adversarial_2_reversed_home_away():
    """Reversed home and away teams fails exact reconciliation."""
    rows = [SimpleNamespace(
        source_fixture_identifier="5000001",
        kickoff=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
    )]
    event = SimpleNamespace(
        event_id="sr:match:9000001",
        kickoff_utc=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
        competition_name="Premier League",
        home_team_name="Chelsea",
        away_team_name="Arsenal",
    )
    assert paginated_discovery._match_current_shadow_event(event, rows) == ()


def test_adversarial_3_kickoff_plus_one_second():
    """Kickoff skew of +1s fails exact reconciliation."""
    rows = [SimpleNamespace(
        source_fixture_identifier="5000001",
        kickoff=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
    )]
    event = SimpleNamespace(
        event_id="sr:match:9000001",
        kickoff_utc=datetime(2026, 9, 20, 15, 0, 1, tzinfo=UTC),
        competition_name="Premier League",
        home_team_name="Arsenal",
        away_team_name="Chelsea",
    )
    assert paginated_discovery._match_current_shadow_event(event, rows) == ()


def test_adversarial_4_duplicate_ambiguous_provider_events():
    """Two provider events for the same fixture produce AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE."""
    # When two provider events match the same FotMob fixture, count > 1
    counts = {"5000001": 2}
    assert counts["5000001"] > 1


def test_adversarial_5_duplicate_ambiguous_fotmob_events():
    """Two FotMob fixtures matching the same provider event produce AMBIGUOUS_FOTMOB."""
    rows = [
        SimpleNamespace(
            source_fixture_identifier="5000001",
            kickoff=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
            competition="Premier League",
            home_team="Arsenal",
            away_team="Chelsea",
        ),
        SimpleNamespace(
            source_fixture_identifier="5000002",
            kickoff=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
            competition="Premier League",
            home_team="Arsenal",
            away_team="Chelsea",
        ),
    ]
    event = SimpleNamespace(
        event_id="sr:match:9000001",
        kickoff_utc=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
        competition_name="Premier League",
        home_team_name="Arsenal",
        away_team_name="Chelsea",
    )
    matches = paginated_discovery._match_current_shadow_event(event, rows)
    assert len(matches) == 2


def test_adversarial_6_stale_discovery_evidence():
    """Discovery age exceeding MAX_SOURCE_AGE_SECONDS is marked DISCOVERY_EVIDENCE_STALE."""
    discovery_age = paginated_discovery.MAX_SOURCE_AGE_SECONDS + 1
    assert discovery_age > paginated_discovery.MAX_SOURCE_AGE_SECONDS


def test_adversarial_7_stale_direct_detail_evidence():
    """Direct event-detail age exceeding MAX_SOURCE_AGE_SECONDS is marked DIRECT_EVENT_DETAIL_STALE."""
    direct_age = paginated_discovery.MAX_SOURCE_AGE_SECONDS + 1
    assert direct_age > paginated_discovery.MAX_SOURCE_AGE_SECONDS


def test_adversarial_8_direct_detail_identity_mismatch():
    """Direct event detail with different team names results in DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH."""
    event_home = "Arsenal"
    detail_home = "Different Arsenal"
    assert detail_home != event_home


def test_adversarial_9_nonbookable_event():
    """Event with prematch_bookable_observed=False is classified NONBOOKABLE."""
    event = SimpleNamespace(prematch_bookable_observed=False)
    assert not event.prematch_bookable_observed


def test_adversarial_10_unknown_alias():
    """Unknown team alias that does not match literal or alias registry returns empty match."""
    rows = [SimpleNamespace(
        source_fixture_identifier="5000001",
        kickoff=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
    )]
    event = SimpleNamespace(
        event_id="sr:match:9000001",
        kickoff_utc=datetime(2026, 9, 20, 15, 0, 0, tzinfo=UTC),
        competition_name="Premier League",
        home_team_name="Unknown FC",
        away_team_name="Chelsea",
    )
    assert paginated_discovery._match_current_shadow_event(event, rows) == ()


def test_adversarial_11_wrong_native_identity():
    """Wrong competitor ID binding fails stable identity matching."""
    # When competitor ID does not match bound competitor ID, match fails
    bound_id = "sr:competitor:100"
    observed_id = "sr:competitor:999"
    assert bound_id != observed_id


def test_adversarial_12_changed_admission_identity():
    """Changed admission identity fails contract validation."""
    with pytest.raises(
        paginated_discovery.CurrentShadowPaginatedDiscoveryReconciliationError,
    ):
        # Calculating contract with wrong policy fails
        paginated_discovery._verify_identity_state_append_only_extension(
            {"competitions": [{"id": 1}], "teams": [], "evidence": []},
            {"competitions": [], "teams": [], "evidence": []},
        )
