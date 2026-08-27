from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_live_event_quote_evidence as live
from domain import sportybet_reviewed_canonical_market_mapping as mapping
from domain import sportybet_user_controlled_native_inventory as native
from domain.markets import MarketId, OutcomeId
from domain.sportybet_provider_native_inventory import NativeAvailability, NativeSelection


EVENT = "sr:match:123"
SPORT = "sr:sport:1"
INV_SHA = "1" * 64
EVIDENCE = "a" * 24
OBSERVED = datetime(2026, 8, 27, 18, 0, 0, tzinfo=timezone.utc)
KICKOFF = OBSERVED + timedelta(hours=2)


def _mapping_source_selection() -> NativeSelection:
    href = (
        f"/ng/lite/preMatch/detail?eventId={EVENT}&marketId=18&outcomeId=O"
        f"&odds=1.90&productId=3&sportId={SPORT}&marketGroupsName=Main"
        "&specifier=total=2.5"
    )
    return NativeSelection(
        event_id=EVENT,
        sport_id=SPORT,
        product_id="3",
        market_id="18",
        market_group="Main",
        market_name="Total Goals",
        specifier="total=2.5",
        outcome_id="O",
        selection_label="Over 2.5",
        odds_raw="1.90",
        odds_decimal="1.9",
        availability=NativeAvailability.AVAILABLE,
        provider_quote_at=None,
        provider_snapshot_id=None,
        href=href,
    )


def _reviewed_mapping(monkeypatch):
    row = _mapping_source_selection()
    inventory = object.__new__(native.SportyBetUserControlledNativeInventory)
    object.__setattr__(inventory, "source_event_id", EVENT)
    object.__setattr__(inventory, "source_sport_id", SPORT)
    object.__setattr__(inventory, "source_evidence_id", EVIDENCE)
    object.__setattr__(inventory, "provider_quote_at", None)
    object.__setattr__(inventory, "provider_snapshot_id", None)
    object.__setattr__(inventory, "selections", (row,))
    reconciled = SimpleNamespace(
        disposition=(
            reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        ),
        fixture_reconciliation_authorized=True,
        matched_fixture=SimpleNamespace(source_fixture_identifier="987654"),
        source_native_inventory_sha256=INV_SHA,
        sportybet_event_id=EVENT,
        sportybet_sport_id=SPORT,
        source_event_evidence_id=EVIDENCE,
    )
    decision = mapping.ReviewedCanonicalMappingDecision(
        event_id=row.event_id,
        provider_market_id=row.market_id,
        provider_market_name=row.market_name,
        provider_specifier=row.specifier,
        provider_outcome_id=row.outcome_id,
        provider_selection_label=row.selection_label,
        canonical_market_id=MarketId.TOTAL_GOALS,
        canonical_outcome_id=OutcomeId.OVER,
        canonical_line=2.5,
    )
    monkeypatch.setattr(mapping.native, "inventory_sha256", lambda value: INV_SHA)
    monkeypatch.setattr(
        mapping.reconciliation,
        "canonical_reconciliation_bytes",
        lambda value: b"reconciliation\n",
    )
    return mapping._build(reconciled, inventory, (decision,))


def _raw_event(
    *,
    odds: str = "2.05",
    outcome_id: str = "O",
    outcome_name: str = "Over 2.5",
    market_name: str = "Total Goals",
    active=1,
    kickoff: datetime = KICKOFF,
    booking_status: str = "Available",
    status=0,
    match_status: str = "Not Started",
    biz_code: int = 10000,
) -> bytes:
    payload = {
        "bizCode": biz_code,
        "data": {
            "event": {
                "eventId": EVENT,
                "homeTeamName": "Home FC",
                "awayTeamName": "Away FC",
                "estimateStartTime": int(kickoff.timestamp() * 1000),
                "bookingStatus": booking_status,
                "status": status,
                "matchStatus": match_status,
                "markets": [
                    {
                        "id": "18",
                        "desc": market_name,
                        "specifier": "total=2.5",
                        "outcomes": [
                            {
                                "id": outcome_id,
                                "desc": outcome_name,
                                "odds": odds,
                                "isActive": active,
                            },
                            {
                                "id": "U",
                                "desc": "Under 2.5",
                                "odds": "1.80",
                                "isActive": 1,
                            },
                        ],
                    }
                ],
            }
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _capture(monkeypatch, tmp_path: Path, *, raw: bytes | None = None, observed=OBSERVED):
    raw_bytes = _raw_event() if raw is None else raw
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: (raw_bytes, 200, observed),
    )
    return live.capture_live_event_quote_evidence(
        event_id=EVENT,
        repository_root=tmp_path,
        execute_live_network=True,
    )


def test_contract_is_pinned_to_reviewed_direct_semantic_event_endpoint():
    result = live.validate_direct_event_source_contract()
    assert result["contract_sha256"] == live.EXPECTED_CONTRACT_SHA256
    assert result["event_path"] == "/api/ng/factsCenter/event"
    assert live.request_target(EVENT) == (
        "/api/ng/factsCenter/event?productId=3&eventId=sr%3Amatch%3A123"
    )
    assert "lite" not in live.EVENT_PATH.casefold()


def test_live_network_requires_exact_explicit_authorization(tmp_path):
    for value in (False, None, 1, "true"):
        with pytest.raises(
            live.SportyBetLiveEventQuoteEvidenceError,
            match="execute_live_network=True",
        ):
            live.capture_live_event_quote_evidence(
                event_id=EVENT,
                repository_root=tmp_path,
                execute_live_network=value,
            )


def test_exact_capture_replay_and_inventory(monkeypatch, tmp_path):
    directory, manifest = _capture(monkeypatch, tmp_path)
    replayed = live.verify_live_event_quote_evidence(
        directory, repository_root=tmp_path
    )
    assert replayed.to_dict() == manifest.to_dict()
    assert manifest.provider_quote_at is None
    assert manifest.provider_snapshot_id is None
    assert manifest.network_acquisition_performed is True
    inventory = live.build_live_event_quote_inventory(
        directory, repository_root=tmp_path
    )
    assert inventory.event_id == EVENT
    assert inventory.observed_at == OBSERVED
    assert inventory.observation_authority == live.OBSERVATION_AUTHORITY
    over = next(item for item in inventory.selections if item.outcome_id == "O")
    assert over.odds_raw == "2.05"
    assert over.odds_decimal == 2.05
    assert over.bookable is True


def test_current_live_issuer_uses_direct_response_price_not_old_mapping_price(
    monkeypatch, tmp_path
):
    reviewed = _reviewed_mapping(monkeypatch)
    assert reviewed.mapped_selections[0].odds_raw == "1.90"
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: (_raw_event(odds="2.17"), 200, OBSERVED),
    )
    monkeypatch.setattr(live, "_now_utc", lambda: OBSERVED + timedelta(seconds=5))

    bundle = live.capture_and_issue_current_mapped_quote_bundle(
        mapping=reviewed,
        repository_root=tmp_path,
        execute_live_network=True,
    )

    assert bundle.status == live.LIVE_STATUS
    assert bundle.proof_mode == live.LIVE_PROOF_MODE
    assert bundle.authority["current_observation_freshness_proven"] is True
    assert bundle.authority["price_all"] is False
    assert bundle.authority["selection"] is False
    assert bundle.authority["sportybet_execution"] is False
    assert bundle.authority["bet"] is False
    assert bundle.to_dict()["wager_placed"] is False
    assert len(bundle.quotes) == 1
    quote = bundle.quotes[0]
    assert quote.odds_raw == "2.17"
    assert quote.decimal_odds == 2.17
    assert quote.provider_quote_at is None
    assert quote.provider_snapshot_id is None
    assert quote.observation_authority == live.OBSERVATION_AUTHORITY
    assert bundle.mapping_audits[0].disposition == "QUOTED"
    assert live.verify_mapped_quote_bundle(bundle).to_dict() == bundle.to_dict()


def test_as_of_replay_can_never_claim_wall_clock_current_authority(monkeypatch, tmp_path):
    reviewed = _reviewed_mapping(monkeypatch)
    directory, _ = _capture(monkeypatch, tmp_path)
    bundle = live.issue_mapped_quote_bundle_as_of(
        mapping=reviewed,
        evidence_directory=directory,
        repository_root=tmp_path,
        evaluation_time=OBSERVED + timedelta(seconds=1),
    )
    assert bundle.status == live.REPLAY_STATUS
    assert bundle.proof_mode == live.REPLAY_PROOF_MODE
    assert bundle.authority["as_of_observation_freshness_proven"] is True
    assert bundle.authority["current_observation_freshness_proven"] is False
    assert bundle.authority["price_all"] is False


def test_builder_only_quotes_and_bundles_cannot_be_relabelled(monkeypatch, tmp_path):
    reviewed = _reviewed_mapping(monkeypatch)
    monkeypatch.setattr(
        live,
        "_network_fetch",
        lambda event_id: (_raw_event(), 200, OBSERVED),
    )
    monkeypatch.setattr(live, "_now_utc", lambda: OBSERVED + timedelta(seconds=2))
    bundle = live.capture_and_issue_current_mapped_quote_bundle(
        mapping=reviewed,
        repository_root=tmp_path,
        execute_live_network=True,
    )
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError):
        dataclasses.replace(bundle, status="FAKE")
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError):
        dataclasses.replace(bundle.quotes[0], odds_raw="9.99")

    object.__setattr__(bundle, "live_inventory_sha256", "0" * 64)
    with pytest.raises(
        live.SportyBetLiveEventQuoteEvidenceError,
        match="differs from exact source reconstruction",
    ):
        live.verify_mapped_quote_bundle(bundle)


def test_stale_future_and_near_kickoff_replay_fail_closed(monkeypatch, tmp_path):
    reviewed = _reviewed_mapping(monkeypatch)
    directory, _ = _capture(monkeypatch, tmp_path)
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError, match="stale"):
        live.issue_mapped_quote_bundle_as_of(
            mapping=reviewed,
            evidence_directory=directory,
            repository_root=tmp_path,
            evaluation_time=OBSERVED + timedelta(seconds=901),
        )
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError, match="future-dated"):
        live.issue_mapped_quote_bundle_as_of(
            mapping=reviewed,
            evidence_directory=directory,
            repository_root=tmp_path,
            evaluation_time=OBSERVED - timedelta(microseconds=1),
        )

    close_raw = _raw_event(kickoff=OBSERVED + timedelta(seconds=120))
    close_dir, _ = _capture(
        monkeypatch,
        tmp_path,
        raw=close_raw,
        observed=OBSERVED + timedelta(microseconds=1),
    )
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError, match="too close"):
        live.issue_mapped_quote_bundle_as_of(
            mapping=reviewed,
            evidence_directory=close_dir,
            repository_root=tmp_path,
            evaluation_time=OBSERVED + timedelta(microseconds=2),
        )


def test_same_native_identity_with_changed_semantics_is_not_silently_remapped(
    monkeypatch, tmp_path
):
    reviewed = _reviewed_mapping(monkeypatch)
    directory, _ = _capture(
        monkeypatch,
        tmp_path,
        raw=_raw_event(outcome_name="Provider Changed Meaning"),
    )
    with pytest.raises(
        live.SportyBetLiveEventQuoteEvidenceError,
        match="changed human-readable semantics",
    ):
        live.issue_mapped_quote_bundle_as_of(
            mapping=reviewed,
            evidence_directory=directory,
            repository_root=tmp_path,
            evaluation_time=OBSERVED + timedelta(seconds=1),
        )


def test_absent_or_unavailable_exact_mapping_is_audited_not_guessed(monkeypatch, tmp_path):
    reviewed = _reviewed_mapping(monkeypatch)
    absent_dir, _ = _capture(
        monkeypatch,
        tmp_path,
        raw=_raw_event(outcome_id="DIFFERENT"),
    )
    absent = live.issue_mapped_quote_bundle_as_of(
        mapping=reviewed,
        evidence_directory=absent_dir,
        repository_root=tmp_path,
        evaluation_time=OBSERVED + timedelta(seconds=1),
    )
    assert absent.quotes == ()
    assert absent.mapping_audits[0].disposition == "ABSENT_FROM_CURRENT_EVENT"

    unavailable_dir, _ = _capture(
        monkeypatch,
        tmp_path,
        raw=_raw_event(active=0),
        observed=OBSERVED + timedelta(microseconds=1),
    )
    unavailable = live.issue_mapped_quote_bundle_as_of(
        mapping=reviewed,
        evidence_directory=unavailable_dir,
        repository_root=tmp_path,
        evaluation_time=OBSERVED + timedelta(seconds=1),
    )
    assert unavailable.quotes == ()
    assert unavailable.mapping_audits[0].disposition == "CURRENTLY_UNAVAILABLE"


def test_invalid_active_priced_selection_and_event_status_fail_closed(monkeypatch, tmp_path):
    reviewed = _reviewed_mapping(monkeypatch)
    invalid_dir, _ = _capture(
        monkeypatch,
        tmp_path,
        raw=_raw_event(odds="1.0"),
    )
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError, match="odds"):
        live.build_live_event_quote_inventory(
            invalid_dir,
            repository_root=tmp_path,
        )

    directory, _ = _capture(
        monkeypatch,
        tmp_path,
        raw=_raw_event(status=1),
        observed=OBSERVED + timedelta(microseconds=1),
    )
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError, match="not pre-match"):
        live.issue_mapped_quote_bundle_as_of(
            mapping=reviewed,
            evidence_directory=directory,
            repository_root=tmp_path,
            evaluation_time=OBSERVED + timedelta(seconds=1),
        )


def test_duplicate_json_keys_and_wrong_biz_code_fail_closed():
    duplicate = b'{"bizCode":10000,"bizCode":10000}\n'
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError, match="duplicate JSON key"):
        live.strict_json_loads(duplicate)
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError, match="bizCode"):
        live._build_manifest(
            event_id=EVENT,
            raw=_raw_event(biz_code=9999),
            status=200,
            observed_at=OBSERVED,
        )


def test_raw_tamper_extra_file_and_path_escape_fail_closed(monkeypatch, tmp_path):
    directory, _ = _capture(monkeypatch, tmp_path)
    raw_path = directory / live.RAW_FILENAME
    original = raw_path.read_bytes()
    raw_path.write_bytes(original + b" ")
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError):
        live.verify_live_event_quote_evidence(directory, repository_root=tmp_path)

    raw_path.write_bytes(original)
    (directory / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(
        live.SportyBetLiveEventQuoteEvidenceError,
        match="contents mismatch",
    ):
        live.verify_live_event_quote_evidence(directory, repository_root=tmp_path)

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError):
        live.verify_live_event_quote_evidence(outside, repository_root=tmp_path)


def test_verify_does_not_create_missing_evidence_root(tmp_path):
    expected = tmp_path / live.ALLOWED_OUTPUT_RELATIVE
    assert not expected.exists()
    with pytest.raises(live.SportyBetLiveEventQuoteEvidenceError):
        live.verify_live_event_quote_evidence(expected / "missing", repository_root=tmp_path)
    assert not expected.exists()
