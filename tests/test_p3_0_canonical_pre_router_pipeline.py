from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
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
from domain import current_shadow_sportybet_upcoming_reconciliation as upcoming_discovery
from domain.current_shadow_sportybet_catalog_fanout_reconciliation import (
    CurrentShadowSportyBetCatalogFanoutReconciliationError,
    validate_fanout_request_scope,
)
from domain.fixture_catalog import compile_fixture_catalog, sha256_bytes
from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewDecision,
    build_fotmob_fixture_candidate_review_bundle,
    sha256_fotmob_fixture_candidate,
)
from domain.fotmob_fixture_candidates import build_fotmob_fixture_candidate_bundle
from domain.fotmob_fixture_catalog_handoff import (
    FotMobFixtureCatalogHandoffError,
    build_fotmob_fixture_catalog_handoff,
    sha256_fotmob_fixture_catalog_handoff,
)
from domain.reviewed_fixture_catalog_admission import (
    REVIEWED_SOURCE_CAPABILITY,
    ReviewedFixtureCatalogAdmissionDecision,
    ReviewedFixtureCatalogAdmissionDisposition,
    build_reviewed_fixture_catalog_admission,
    sha256_reviewed_fixture_catalog_admission,
    sha256_reviewed_source_capability,
)
from domain import sportybet_current_event_discovery_reconciliation as reviewed_discovery
from domain import sportybet_live_event_quote_evidence as live
from scripts import current_shadow_fixture_identity_reconciliation_recovery as identity_recovery
from scripts import verify_p3_0_e1_live_readiness


UTC = timezone.utc
FOTMOB_OBSERVED = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
DISCOVERY_OBSERVED = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
DETAIL_OBSERVED = datetime(2026, 9, 20, 10, 0, 30, tzinfo=UTC)
EVALUATION = datetime(2026, 9, 20, 10, 0, 35, tzinfo=UTC)
KICKOFF = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
EVENT_ID = "sr:match:9000001"
FIXTURE_ID = 5000001


def _epoch_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def _fotmob_match(
    match_id: int,
    *,
    home: str = "Arsenal",
    away: str = "Chelsea",
    kickoff: datetime = KICKOFF,
) -> dict[str, Any]:
    kickoff = kickoff.astimezone(UTC)
    return {
        "away": {"id": 8455, "score": 0, "name": away, "longName": away},
        "eliminatedTeamId": None,
        "home": {"id": 9825, "score": 0, "name": home, "longName": home},
        "id": match_id,
        "leagueId": 47,
        "status": {
            "utcTime": kickoff.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "halfs": {"firstHalfStarted": ""},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "statusId": 1,
        "time": kickoff.strftime("%d.%m.%Y %H:%M"),
        "timeTS": _epoch_ms(kickoff),
        "tournamentStage": "",
    }


def _fotmob_capture(
    *,
    match_ids: tuple[int, ...] = (FIXTURE_ID,),
    home: str = "Arsenal",
    away: str = "Chelsea",
    competition: str = "Premier League",
    kickoff: datetime = KICKOFF,
) -> tuple[bytes, Any]:
    payload = {
        "date": kickoff.astimezone(UTC).strftime("%Y%m%d"),
        "leagues": [
            {
                "ccode": "ENG",
                "id": 47,
                "internalRank": 1,
                "matches": [
                    _fotmob_match(match_id, home=home, away=away, kickoff=kickoff)
                    for match_id in match_ids
                ],
                "name": competition,
                "primaryId": 47,
                "simpleLeague": False,
            }
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=FOTMOB_OBSERVED,
        network_acquisition_performed=True,
    )
    manifest = build_data_matches_capture_manifest(
        response,
        request_date=payload["date"],
        timezone="UTC",
        ccode3="ENG",
    )
    return raw, manifest


from domain.current_fotmob_fixture_review_policy import (
    build_current_shadow_fotmob_fixture_review_policy_result,
)
from domain.markets import MarketId
from domain import current_all_market_shadow_probability_settlement as prc


def _fotmob_admission(
    tmp_path: Path,
    *,
    match_ids: tuple[int, ...] = (FIXTURE_ID,),
    home: str = "Arsenal",
    away: str = "Chelsea",
    competition: str = "Premier League",
    kickoff: datetime = KICKOFF,
    disposition: ReviewedFixtureCatalogAdmissionDisposition = (
        ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ),
):
    capture = _fotmob_capture(
        match_ids=match_ids,
        home=home,
        away=away,
        competition=competition,
        kickoff=kickoff,
    )
    candidate_bundle = build_fotmob_fixture_candidate_bundle((capture,))
    # Blocker 2: Run REAL Current Shadow review policy used by production
    policy_result = build_current_shadow_fotmob_fixture_review_policy_result(
        candidate_bundle,
        reviewed_at=datetime(2026, 9, 20, 8, 10, tzinfo=UTC),
    )
    if disposition == ReviewedFixtureCatalogAdmissionDisposition.ADMITTED:
        assert policy_result.policy_approved_count == len(match_ids)
        assert policy_result.review_bundle.approved_count == len(match_ids)
    review_bundle = policy_result.review_bundle
    handoff = build_fotmob_fixture_catalog_handoff(candidate_bundle, review_bundle)
    raw = capture[0]
    for item in handoff.catalog_inputs:
        evidence_path = tmp_path / item.evidence_file_path
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(raw)
    input_path = tmp_path / "reviewed-fotmob.jsonl"
    input_path.write_bytes(handoff.catalog_input_jsonl_bytes)
    result = compile_fixture_catalog(
        input_path=input_path,
        evidence_root=tmp_path,
        as_of=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
        minimum_lead_seconds=120,
        code_state={
            "evidence_git_head_sha": "a" * 40,
            "tracked_worktree_clean": True,
        },
    )
    decision = ReviewedFixtureCatalogAdmissionDecision(
        candidate_bundle_sha256=handoff.candidate_bundle_sha256,
        review_bundle_sha256=handoff.review_bundle_sha256,
        handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
        catalog_sha256=sha256_bytes(result.catalog_bytes),
        manifest_sha256=sha256_bytes(result.manifest_bytes),
        source_capability=REVIEWED_SOURCE_CAPABILITY,
        source_capability_sha256=sha256_reviewed_source_capability(),
        disposition=disposition,
        reviewed_at=datetime(2026, 9, 20, 9, 30, tzinfo=UTC),
        reviewer_reference="operator:pr374-catalog-admission",
        notes="catalog identity admitted before current provider reconciliation",
    )
    admission = build_reviewed_fixture_catalog_admission(handoff, result, decision)
    return admission, (capture,)


def _event(
    *,
    event_id: str = EVENT_ID,
    home: str = "Arsenal",
    away: str = "Chelsea",
    kickoff: datetime = KICKOFF,
    status: int = 0,
    booking_status: str = "Available",
    tournament_name: str | None = "Premier League",
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "eventId": event_id,
        "sportId": "sr:sport:1",
        "homeTeamName": home,
        "awayTeamName": away,
        "estimateStartTime": int(kickoff.timestamp() * 1000),
        "status": status,
        "bookingStatus": booking_status,
        "matchStatus": "Not started" if status in (0, "0", None) else "Live",
        "sport": {
            "id": "sr:sport:1",
            "name": "Football",
            "category": {
                "id": "sr:category:1",
                "name": "England",
                "tournament": {
                    "id": "sr:tournament:1",
                    "name": tournament_name or "Premier League",
                },
            },
        },
    }
    if tournament_name is not None:
        value["tournamentName"] = tournament_name
    return value


def _discovery_raw(
    events: Any,
    *,
    tournament_name: str | None = "Premier League",
    pad_to_page_size: bool = True,
) -> bytes:
    if tournament_name is None:
        data = list(events)
    else:
        data = [{"name": tournament_name, "events": list(events)}]
    if pad_to_page_size and len(data) < reviewed_discovery.PAGE_SIZE:
        data = data + [
            {"name": f"Empty Tournament {i}", "events": []}
            for i in range(reviewed_discovery.PAGE_SIZE - len(data))
        ]
    return json.dumps(
        {"bizCode": 10000, "data": data},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _empty_discovery_raw() -> bytes:
    return b'{"bizCode":10000,"data":[]}'


def _detail_raw(
    *,
    event_id: str = EVENT_ID,
    home: str = "Arsenal",
    away: str = "Chelsea",
    kickoff: datetime = KICKOFF,
    status: int = 0,
    booking_status: str = "Available",
    tournament_name: str = "Premier League",
) -> bytes:
    event = _event(
        event_id=event_id,
        home=home,
        away=away,
        kickoff=kickoff,
        status=status,
        booking_status=booking_status,
        tournament_name=tournament_name,
    )
    event["markets"] = [
        {
            "id": "1",
            "desc": "1X2",
            "outcomes": [
                {"id": "1", "desc": "Home", "odds": "2.0", "isActive": 1},
                {"id": "2", "desc": "Draw", "odds": "3.0", "isActive": 1},
                {"id": "3", "desc": "Away", "odds": "4.0", "isActive": 1},
            ],
        }
    ]
    return json.dumps(
        {"bizCode": 10000, "data": {"event": event}},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _install_discovery(
    monkeypatch: pytest.MonkeyPatch,
    events: Any,
    *,
    tournament_name: str = "Premier League",
    observed: datetime = DISCOVERY_OBSERVED,
) -> None:
    pages = {
        1: _discovery_raw(events, tournament_name=tournament_name),
        2: _empty_discovery_raw(),
    }

    def fetch(page_num: int) -> tuple[bytes, int, datetime]:
        raw = pages.get(page_num, _empty_discovery_raw())
        return raw, 200, observed + timedelta(seconds=page_num - 1)

    monkeypatch.setattr(reviewed_discovery, "_network_fetch_page", fetch)


def _install_upcoming_discovery(
    monkeypatch: pytest.MonkeyPatch,
    events: Any,
    *,
    tournament_name: str = "Premier League",
    observed: datetime = DISCOVERY_OBSERVED,
) -> None:
    raw = json.dumps(
        {"bizCode": 10000, "data": list(events)},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    nonce = _epoch_ms(observed) - 250

    def fetch() -> tuple[bytes, int, datetime, int]:
        return raw, 200, observed, nonce

    monkeypatch.setattr(upcoming_discovery, "_network_fetch_snapshot", fetch)


def _install_detail(
    monkeypatch: pytest.MonkeyPatch,
    *,
    raw: bytes | None = None,
    observed: datetime = DETAIL_OBSERVED,
) -> None:
    detail_bytes = _detail_raw() if raw is None else raw

    def fetch(event_id: str) -> tuple[bytes, int, datetime]:
        payload = json.loads(detail_bytes)
        assert event_id == payload["data"]["event"]["eventId"]
        return detail_bytes, 200, observed

    monkeypatch.setattr(live, "_network_fetch", fetch)


def _run_paginated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    events: Any = None,
    tournament_name: str = "Premier League",
    admission: Any = None,
    captures: Any = None,
    detail_raw: bytes | None = None,
    discovery_observed: datetime = DISCOVERY_OBSERVED,
    detail_observed: datetime = DETAIL_OBSERVED,
    evaluation: datetime = EVALUATION,
) -> paginated_discovery.SportyBetCurrentEventDiscoveryReconciliationBundle:
    tmp_path.mkdir(parents=True, exist_ok=True)
    if admission is None or captures is None:
        admission, captures = _fotmob_admission(tmp_path)
    _install_discovery(
        monkeypatch,
        [_event()] if events is None else events,
        tournament_name=tournament_name,
        observed=discovery_observed,
    )
    _install_detail(monkeypatch, raw=detail_raw, observed=detail_observed)
    monkeypatch.setattr(reviewed_discovery, "_now_utc", lambda: evaluation)

    discovery_dir, _manifest = paginated_discovery.capture_current_paginated_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )
    return paginated_discovery.reconcile_current_events_from_paginated_discovery(
        repository_root=tmp_path,
        discovery_evidence_directory=discovery_dir,
        fotmob_admission_value=admission,
        fotmob_captures=captures,
        execute_live_network=True,
    )


# ---------------------------------------------------------------------------
# Contract and Scoping Tests
# ---------------------------------------------------------------------------

def test_paginated_discovery_contract_is_pinned_and_zero_authority():
    contract = paginated_discovery.validate_contract()
    assert contract["contract_sha256"] == paginated_discovery.EXPECTED_CONTRACT_SHA256
    assert contract["contract_sha256"] == "c000a9b92afa616574516032ce4bb599cba0af3702f74e1219b6cbfdffbd0dbd"

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


def test_fanout_request_scope_unproven_on_run_35409481576_shape():
    """Run 35409481576 shape: observations without events or without native scope return UNPROVEN."""
    obs1 = SimpleNamespace(event_ids=("sr:match:101",), category_id="sr:category:1", tournament_id="sr:tournament:1")
    obs2 = SimpleNamespace(event_ids=("sr:match:102",), category_id="sr:category:1", tournament_id="sr:tournament:2")
    # No logical events provided
    status = validate_fanout_request_scope([obs1, obs2], events=None, require_proven=False)
    assert status == "FANOUT_REQUEST_SCOPE_UNPROVEN"

    # Events provided but missing native category/tournament IDs
    ev1 = SimpleNamespace(event_id="sr:match:101")
    ev2 = SimpleNamespace(event_id="sr:match:102")
    status = validate_fanout_request_scope([obs1, obs2], events=[ev1, ev2], require_proven=False)
    assert status == "FANOUT_REQUEST_SCOPE_UNPROVEN"


def test_fanout_request_scope_proven_on_genuinely_scoped_positive_case():
    """Genuinely scoped positive case satisfies all 6 conditions."""
    obs1 = SimpleNamespace(event_ids=("sr:match:1", "sr:match:2"), category_id="sr:category:1", tournament_id="sr:tournament:1")
    obs2 = SimpleNamespace(event_ids=("sr:match:3", "sr:match:4"), category_id="sr:category:1", tournament_id="sr:tournament:2")
    events = [
        SimpleNamespace(event_id="sr:match:1", category_id="sr:category:1", tournament_id="sr:tournament:1"),
        SimpleNamespace(event_id="sr:match:2", category_id="sr:category:1", tournament_id="sr:tournament:1"),
        SimpleNamespace(event_id="sr:match:3", category_id="sr:category:1", tournament_id="sr:tournament:2"),
        SimpleNamespace(event_id="sr:match:4", category_id="sr:category:1", tournament_id="sr:tournament:2"),
    ]
    status = validate_fanout_request_scope([obs1, obs2], events=events)
    assert status == "FANOUT_REQUEST_SCOPE_PROVEN"


def test_verify_p3_0_e1_live_readiness_runs_offline_and_passes(monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("ATHENA_EXPECTED_LINEAGE_MAIN_SHA", "c5ec9a23486a594d2df279521b6065744fa9a389")
    report = verify_p3_0_e1_live_readiness.run_all_readiness_checks(repository_root=repo_root)
    assert report["status"] == "P3_0_E1_LIVE_READINESS_VERIFIED"
    assert len(report["checks"]) == 14
    assert (repo_root / "artifacts" / "p3-0-comparison-evidence" / "p3-0-e1-live-readiness.json").exists()
    assert (repo_root / "p3-0-e1-live-readiness.json").exists()


def test_readiness_double_run_produces_identical_sha(monkeypatch: pytest.MonkeyPatch):
    """Blocker 8: verify readiness run twice under same env produces identical SHA-256 and semantic equality."""
    repo_root = Path(__file__).resolve().parents[1]
    expected_main = "c5ec9a23486a594d2df279521b6065744fa9a389"
    monkeypatch.setenv("ATHENA_EXPECTED_LINEAGE_MAIN_SHA", expected_main)
    report1 = verify_p3_0_e1_live_readiness.run_all_readiness_checks(repository_root=repo_root)
    report2 = verify_p3_0_e1_live_readiness.run_all_readiness_checks(repository_root=repo_root)

    # Exact SHA-256 digest equality
    assert report1["sha256"] == report2["sha256"]
    assert report1["exact_commit_sha"] == report2["exact_commit_sha"]
    assert report1["resolved_lineage_main_sha"] == report2["resolved_lineage_main_sha"]
    assert report1["resolved_lineage_main_sha"] == expected_main

    # Exact canonical semantic equality excluding wall-clock evaluated_at
    payload1 = {k: v for k, v in report1.items() if k != "evaluated_at"}
    payload2 = {k: v for k, v in report2.items() if k != "evaluated_at"}
    assert payload1 == payload2
    assert payload1["status"] == "P3_0_E1_LIVE_READINESS_VERIFIED"
    assert len(payload1["checks"]) == 14


def test_readiness_check_b_fails_closed_when_env_missing(monkeypatch: pytest.MonkeyPatch):
    """Blocker 4: check_b fails closed when ATHENA_EXPECTED_LINEAGE_MAIN_SHA is missing."""
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.delenv("ATHENA_EXPECTED_LINEAGE_MAIN_SHA", raising=False)
    with pytest.raises(
        verify_p3_0_e1_live_readiness.P30LiveReadinessError,
        match="ATHENA_EXPECTED_LINEAGE_MAIN_SHA environment variable is required",
    ):
        verify_p3_0_e1_live_readiness.check_b_lineage_main(repo_root)


def test_readiness_check_b_fails_closed_when_env_malformed(monkeypatch: pytest.MonkeyPatch):
    """Blocker 4: check_b fails closed when ATHENA_EXPECTED_LINEAGE_MAIN_SHA is malformed."""
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("ATHENA_EXPECTED_LINEAGE_MAIN_SHA", "not-a-valid-40-hex-sha")
    with pytest.raises(
        verify_p3_0_e1_live_readiness.P30LiveReadinessError,
        match="is not 40 hex chars",
    ):
        verify_p3_0_e1_live_readiness.check_b_lineage_main(repo_root)


def test_readiness_check_b_passes_with_valid_env(monkeypatch: pytest.MonkeyPatch):
    """Blocker 4: check_b records checked_out_head_sha and resolved_lineage_main_sha."""
    repo_root = Path(__file__).resolve().parents[1]
    expected_main = "c5ec9a23486a594d2df279521b6065744fa9a389"
    monkeypatch.setenv("ATHENA_EXPECTED_LINEAGE_MAIN_SHA", expected_main)
    res = verify_p3_0_e1_live_readiness.check_b_lineage_main(repo_root)
    assert res["status"] == "PASSED"
    assert res["resolved_lineage_main_sha"] == expected_main
    assert len(res["checked_out_head_sha"]) == 40


def test_acquire_current_shadow_pre_router_bundle_rejects_unknown_capture_mode(tmp_path: Path):
    """Blocker 8: acquire_current_shadow_pre_router_bundle fails closed on unknown capture_mode."""
    with pytest.raises(
        runner.CurrentShadowAllMarketRunnerError,
        match="unsupported pre-router capture mode: UNKNOWN_MODE",
    ):
        runner.acquire_current_shadow_pre_router_bundle(
            repository_root=tmp_path,
            lineage_main_sha="1" * 40,
            capture_mode="UNKNOWN_MODE",
        )


# ---------------------------------------------------------------------------
# Full admission-aware Pre-Router Pipeline & Equivalence Test (Blocker 1)
# ---------------------------------------------------------------------------

def test_full_admission_aware_source_to_router_pipeline_canonical_equivalence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Blocker 1: Proves SUPPORTED_REQUEST and P3_E1_PRE_ROUTER_CAPTURE produce identical

    non-zero router inputs and identical discovery strategy IDs through the complete
    pre-Router pipeline with real FotMob capture, admission, paginated discovery,
    reconciliation, direct detail inventory, Price-All, and Router.
    """
    admission, captures = _fotmob_admission(tmp_path)
    raw_fotmob_bytes, raw_manifest = captures[0]
    execution = SimpleNamespace(
        bootstrap=SimpleNamespace(
            verified_artifact=SimpleNamespace(admission=admission),
            fixtures=admission.admitted_fixtures,
        ),
        summary=lambda: {"fixture_source": "offline-premier-league"},
    )

    _install_upcoming_discovery(monkeypatch, [_event()], tournament_name="Premier League")
    _install_detail(monkeypatch)
    monkeypatch.setattr(reviewed_discovery, "_now_utc", lambda: EVALUATION)

    monkeypatch.setattr(
        runner,
        "_issue_current_fixture_sources",
        lambda **_kw: ([(execution, "20260920")], ("20260920",)),
    )
    monkeypatch.setattr(
        runner,
        "_source_capture",
        lambda *_args: (raw_fotmob_bytes, raw_manifest),
    )
    monkeypatch.setattr(runner, "_legacy_bootstrap_bytes", lambda: b"{}")
    dummy_history = object.__new__(
        runner.latest_history.CurrentLatestDurableFreshHistoryHandoff
    )
    object.__setattr__(dummy_history, "schema_version", 1)
    object.__setattr__(
        dummy_history,
        "dataset_name",
        "athena-current-fotmob-latest-durable-fresh-history-v1",
    )
    object.__setattr__(
        dummy_history,
        "status",
        "CURRENT_FOTMOB_LATEST_DURABLE_FRESH_HISTORY_VERIFIED",
    )
    object.__setattr__(dummy_history, "source_bundle", None)
    object.__setattr__(
        dummy_history, "latest_applicable_success_selection_proven", True
    )
    object.__setattr__(
        dummy_history, "current_fresh_history_prefix_complete", True
    )
    object.__setattr__(
        dummy_history, "next_required_boundary", "PRICE_ALL_CURRENT_SHADOW"
    )
    object.__setattr__(dummy_history, "evidence", {})
    object.__setattr__(dummy_history, "authority", {})
    monkeypatch.setattr(
        runner.latest_history,
        "build_current_fotmob_latest_durable_fresh_history_handoff",
        lambda **_kw: dummy_history,
    )
    monkeypatch.setattr(
        runner.latest_history,
        "sha256_current_fotmob_latest_durable_fresh_history_handoff",
        lambda _h: "h" * 64,
    )

    # Real PR-C scan provider for the price context builder
    def _mock_scan_current_fixture_all_markets(
        *,
        complete_current_history: Any,
        fixture_identity: str,
        provider_semantic_registry: Any = None,
    ) -> Any:
        return prc.scan_fixture_all_markets(
            fixture_identity=fixture_identity,
            research_xg=prc.ResearchXGRates(
                calibrated_home=2.0,
                calibrated_away=0.7,
                sealed_prediction_sha256="a" * 64,
                history_prefix_identity="b" * 64,
                source_fixture_identity=fixture_identity,
            ),
            kickoff_utc_iso=KICKOFF.isoformat().replace("+00:00", "Z"),
            provider_semantic_by_market={m: "SUPPORTED" for m in MarketId},
        )

    monkeypatch.setattr(
        "domain._current_shadow_quote_binding.prc.scan_current_fixture_all_markets",
        _mock_scan_current_fixture_all_markets,
    )
    # Price-All, Router, and Portfolio modules run with REAL production functions
    # (runner.price_module, runner.router_module, runner.portfolio_module from shadow_core_adapter)

    # Run SUPPORTED_REQUEST through real capture & reconciliation
    supported_bundle = runner.acquire_current_shadow_pre_router_bundle(
        repository_root=tmp_path,
        lineage_main_sha="1" * 40,
        capture_mode="SUPPORTED_REQUEST",
    )

    # Run P3_E1_PRE_ROUTER_CAPTURE through real capture & reconciliation
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

    # Blocker 1: Assert exact priced fixture identity, provider event identity,
    # at least one priced market/opportunity, real Router decision vocabulary,
    # and resulting router input identity.
    s_inp = supported_bundle.router_inputs[0]
    p_inp = p3_bundle.router_inputs[0]
    assert s_inp.price_all_bundle.fixture_identity == f"FOTMOB:{FIXTURE_ID}"
    assert p_inp.price_all_bundle.fixture_identity == f"FOTMOB:{FIXTURE_ID}"
    assert s_inp.price_all_bundle._context.provider_event_id == EVENT_ID
    assert p_inp.price_all_bundle._context.provider_event_id == EVENT_ID
    assert s_inp.fixture_identity == f"FOTMOB:{FIXTURE_ID}"
    assert p_inp.fixture_identity == f"FOTMOB:{FIXTURE_ID}"
    assert s_inp.provider_event_id == EVENT_ID
    assert p_inp.provider_event_id == EVENT_ID
    # At least one priced market/opportunity
    priced_results = [
        r for r in s_inp.price_all_bundle.results if r.disposition.value == "PRICED"
    ]
    assert len(priced_results) >= 1
    assert all(r.provider_event_id == EVENT_ID for r in priced_results)
    assert len({r.market_id for r in s_inp.price_all_bundle.results}) == 15
    assert len(s_inp.price_all_bundle.results) == 44

    # Real Router decision vocabulary
    assert s_inp.router_decision.status.value in {"SELECTED", "NO_BET"}
    assert p_inp.router_decision.status.value in {"SELECTED", "NO_BET"}
    assert s_inp.router_decision.status == p_inp.router_decision.status
    assert s_inp.router_decision.router_policy_id == "SHADOW_SOURCE_ALIGNED_SETTLEMENT_AWARE_ROUTER_V3"
    assert s_inp.router_decision.value_first_policy_id == "SHADOW_CONSERVATIVE_FROZEN_THRESHOLDS_V1"

    # Resulting router input identity
    assert s_inp.to_dict() == p_inp.to_dict()
    assert s_inp.price_all_bundle_sha256 == p_inp.price_all_bundle_sha256
    assert s_inp.router_decision_sha256 == p_inp.router_decision_sha256

    # Assert discovery strategy equality and truthful vocabulary
    strategy_id = "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"
    assert supported_bundle.source_summary["provider_discovery_strategy_id"] == strategy_id
    assert p3_bundle.source_summary["provider_discovery_strategy_id"] == strategy_id
    assert "provider_catalog_fanout_snapshot_sha256" not in supported_bundle.source_summary
    assert "provider_catalog_fanout_snapshot_sha256" not in p3_bundle.source_summary
    assert supported_bundle.source_summary["provider_discovery_page_count"] == 1
    assert supported_bundle.source_summary["provider_discovery_event_count"] == 1
    assert supported_bundle.source_summary["current_reconciliation_sha256"] == p3_bundle.source_summary["current_reconciliation_sha256"]
    assert supported_bundle.source_summary["current_reconciliation_sha256"] is not None


# ---------------------------------------------------------------------------
# 12 Real-Path Adversarial Variant Tests (Blocker 2)
# ---------------------------------------------------------------------------

def test_adversarial_1_unapproved_competition(tmp_path: Path):
    """1. Unapproved competition (e.g. K-League 1) is excluded by review policy before reconciliation."""
    priority = resolve_source_competition_review_priority("KOR", "K-League 1")
    assert priority is None

    # Feed unapproved KOR / K-League 1 raw capture into candidate bundle
    capture = _fotmob_capture(
        competition="K-League 1",
        home="Jeonbuk Hyundai Motors",
        away="FC Seoul",
        kickoff=KICKOFF,
    )
    candidate_bundle = build_fotmob_fixture_candidate_bundle((capture,))
    assert candidate_bundle.candidate_count == 1
    candidate = candidate_bundle.candidates[0]
    assert candidate.source_competition_name == "K-League 1"

    # Run actual production review policy path
    policy_result = build_current_shadow_fotmob_fixture_review_policy_result(
        candidate_bundle,
        reviewed_at=datetime(2026, 9, 20, 8, 10, tzinfo=UTC),
    )
    # Real policy strictly excludes unapproved competition
    assert policy_result.exact_competition_identity_count == 0
    assert policy_result.policy_approved_count == 0
    assert policy_result.review_bundle.approved_count == 0
    assert len(policy_result.review_bundle.decisions) == 0

    # Handoff construction fails closed because 0 candidates were approved by review policy
    with pytest.raises(
        FotMobFixtureCatalogHandoffError,
        match="at least one explicit approved catalog input is required for handoff",
    ):
        build_fotmob_fixture_catalog_handoff(
            candidate_bundle, policy_result.review_bundle
        )

    # Even if an unadmitted / rejected admission decision is attempted, reconciliation fails closed
    valid_admission, valid_captures = _fotmob_admission(tmp_path)
    rejected_decision = dataclasses.replace(
        valid_admission.decision,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    rejected_admission = dataclasses.replace(
        valid_admission,
        decision=rejected_decision,
        admitted_fixtures=(),
    )
    with pytest.raises(
        reviewed_discovery.SportyBetCurrentEventDiscoveryError,
        match="FotMob reviewed catalog must have exact ADMITTED disposition",
    ):
        paginated_discovery.reconcile_current_events_from_paginated_discovery(
            repository_root=tmp_path,
            discovery_evidence_directory=tmp_path,
            fotmob_admission_value=rejected_admission,
            fotmob_captures=valid_captures,
            execute_live_network=False,
        )


def test_adversarial_2_reversed_home_away(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """2. Home/away reversed produces NO_EXACT_REVIEWED_FOTMOB_MATCH on the real reconciliation path."""
    # Discovered event has Chelsea at home, Arsenal away; FotMob admission has Arsenal at home, Chelsea away.
    reversed_event = _event(home="Chelsea", away="Arsenal", kickoff=KICKOFF)
    bundle = _run_paginated(monkeypatch, tmp_path, events=[reversed_event])
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
    assert row.fixture_reconciliation_authorized is False
    assert row.matched_fotmob_fixture_id is None


def test_adversarial_3_kickoff_plus_one_second(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """3. Kickoff +1s produces NO_EXACT_REVIEWED_FOTMOB_MATCH on the real reconciliation path."""
    skewed_event = _event(kickoff=KICKOFF + timedelta(seconds=1))
    bundle = _run_paginated(monkeypatch, tmp_path, events=[skewed_event])
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
    assert row.fixture_reconciliation_authorized is False


def test_adversarial_4_duplicate_ambiguous_provider_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """4. Duplicate provider events targeting one reviewed fixture produce AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE."""
    event1 = _event(event_id="sr:match:9000001")
    event2 = _event(event_id="sr:match:9000002")
    bundle = _run_paginated(monkeypatch, tmp_path, events=[event1, event2])
    assert len(bundle.rows) == 2
    for row in bundle.rows:
        assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE
        assert row.fixture_reconciliation_authorized is False


def test_adversarial_5_duplicate_ambiguous_fotmob_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """5. Duplicate reviewed FotMob candidates produce AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH."""
    admission, captures = _fotmob_admission(tmp_path, match_ids=(5000001, 5000002))
    bundle = _run_paginated(monkeypatch, tmp_path, admission=admission, captures=captures)
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH
    assert row.fixture_reconciliation_authorized is False


def test_adversarial_6_stale_discovery_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """6. Stale discovery timestamp produces DISCOVERY_EVIDENCE_STALE on the real reconciliation path."""
    stale_observed = EVALUATION - timedelta(seconds=paginated_discovery.MAX_SOURCE_AGE_SECONDS + 10)
    bundle = _run_paginated(monkeypatch, tmp_path, discovery_observed=stale_observed)
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.DISCOVERY_EVIDENCE_STALE
    assert row.fixture_reconciliation_authorized is False


def test_adversarial_7_stale_direct_detail_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """7. Stale direct-detail timestamp produces DIRECT_EVENT_DETAIL_STALE on the real reconciliation path."""
    stale_detail = EVALUATION - timedelta(seconds=paginated_discovery.MAX_SOURCE_AGE_SECONDS + 10)
    bundle = _run_paginated(monkeypatch, tmp_path, detail_observed=stale_detail)
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_STALE
    assert row.fixture_reconciliation_authorized is False


def test_adversarial_8_direct_detail_identity_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """8. Direct detail identity mismatch produces DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH."""
    mismatched_raw = _detail_raw(home="Different Arsenal FC")
    bundle = _run_paginated(monkeypatch, tmp_path, detail_raw=mismatched_raw)
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH
    assert row.fixture_reconciliation_authorized is False


def test_adversarial_9_nonbookable_event(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """9. Nonbookable discovery event produces DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE."""
    nonbookable = _event(booking_status="Unavailable")
    bundle = _run_paginated(monkeypatch, tmp_path, events=[nonbookable])
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE
    assert row.fixture_reconciliation_authorized is False


def test_adversarial_10_unknown_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """10. Unknown alias/team label produces NO_EXACT_REVIEWED_FOTMOB_MATCH."""
    unknown_event = _event(home="Completely Unknown FC")
    bundle = _run_paginated(monkeypatch, tmp_path, events=[unknown_event])
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
    assert row.fixture_reconciliation_authorized is False


def test_adversarial_11_wrong_native_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """11. Wrong provider-native competitor identity does not authorize fixture on real reconciliation path."""
    fixture_identity.reset_runtime_evidence()
    try:
        # Provider raw discovery event with wrong competitor identity
        wrong_event = _event(
            event_id="sr:match:99999999",
            home="Completely Wrong Team FC",
            away="Other Wrong FC",
            kickoff=KICKOFF,
        )
        # Run through actual paginated discovery and reconciliation path
        bundle = _run_paginated(monkeypatch, tmp_path, events=[wrong_event])
        assert len(bundle.rows) == 1
        row = bundle.rows[0]
        # Require no fixture reconciliation authorization, exact disposition, and no matched fixture
        assert row.fixture_reconciliation_authorized is False
        assert row.matched_fotmob_fixture_id is None
        assert row.disposition == reviewed_discovery.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
        assert bundle.matched_rows == ()

        # Direct detail directory is not populated for un-reconciled event
        assert "sr:match:99999999" not in dict(bundle._detail_directories)

        # No Price-All / Router progression: acquire_current_shadow_pre_router_bundle produces 0 priced fixtures
        # and 0 router inputs
        admission, captures = _fotmob_admission(tmp_path / "case11")
        raw_fotmob_bytes, raw_manifest = captures[0]
        execution = SimpleNamespace(
            bootstrap=SimpleNamespace(
                verified_artifact=SimpleNamespace(admission=admission),
                fixtures=admission.admitted_fixtures,
            ),
            summary=lambda: {"fixture_source": "offline-premier-league"},
        )
        monkeypatch.setattr(
            runner,
            "_issue_current_fixture_sources",
            lambda **_kw: ([(execution, "20260920")], ("20260920",)),
        )
        monkeypatch.setattr(
            runner,
            "_source_capture",
            lambda *_args: (raw_fotmob_bytes, raw_manifest),
        )
        monkeypatch.setattr(runner, "_legacy_bootstrap_bytes", lambda: b"{}")

        pre_router_bundle = runner.acquire_current_shadow_pre_router_bundle(
            repository_root=tmp_path,
            lineage_main_sha="1" * 40,
            capture_mode="SUPPORTED_REQUEST",
        )
        assert pre_router_bundle.reconciled_fixture_count == 0
        assert pre_router_bundle.priced_fixture_count == 0
        assert pre_router_bundle.router_inputs == ()
    finally:
        fixture_identity.reset_runtime_evidence()


def test_adversarial_12_changed_admission_identity(tmp_path: Path):
    """12. Changed/tampered FotMob admission identity fails exact admission replay validation."""
    admission, _captures = _fotmob_admission(tmp_path / "admitted")
    other_capture = _fotmob_capture(home="Other Home FC")
    with pytest.raises(
        reviewed_discovery.SportyBetCurrentEventDiscoveryError,
        match="FotMob reviewed-catalog source replay failed closed",
    ):
        paginated_discovery.reconcile_current_events_from_paginated_discovery(
            repository_root=tmp_path,
            discovery_evidence_directory=tmp_path,
            fotmob_admission_value=admission,
            fotmob_captures=(other_capture,),
            execute_live_network=False,
        )
