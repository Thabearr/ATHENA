from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from domain import sportybet_fotmob_full_utc_reconciliation as full
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain._price_all_contracts import SportyBetExactQuote
from domain.accumulator_optimizer import AccumulatorFixtureInput
from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
)
from domain.fixture_state_v2 import build_fixture_state_v2_snapshot
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
from tests._market_router_helpers import phase6_variant

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc)
_CONTEXT = (
    (IntelligenceCategory.FORM, "home_form", 0.72),
    (IntelligenceCategory.FORM, "away_form", 0.61),
    (IntelligenceCategory.PERFORMANCE, "home_elo", 1612),
    (IntelligenceCategory.PERFORMANCE, "away_elo", 1548),
    (IntelligenceCategory.SCHEDULE_LOAD, "fatigue", 0.23),
    (IntelligenceCategory.FIXTURE_CONTEXT, "live_data_freshness", 0.95),
)


def _sha_row(value) -> str:
    payload = json.dumps(
        value.to_dict(), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode() + b"\n"
    return hashlib.sha256(payload).hexdigest()


def _fixture_state(fixture_id: str, kickoff: datetime = KICKOFF):
    observed = NOW - timedelta(minutes=10)
    facts = tuple(
        FixtureIntelligenceFact(
            category=category,
            field=field,
            status=IntelligenceFactStatus.SUPPORTED,
            value=value,
            source_provider="ACCUMULATOR_TEST_SOURCE",
            source_role=SourceRole.VERIFIED_EXTERNAL,
            source_reference=f"accumulator:test:{fixture_id}:{field}",
            observed_at=observed,
            evidence_file_path=f"evidence/accumulator/{fixture_id}-{field}.json",
            evidence_sha256=hashlib.sha256(f"{fixture_id}:{field}".encode()).hexdigest(),
            notes="Accumulator Optimizer synthetic source-bound test evidence.",
        )
        for category, field, value in _CONTEXT
    )
    return build_fixture_state_v2_snapshot(
        build_snapshot(fixture_id, kickoff, NOW - timedelta(minutes=5), facts)
    )


def _reconciliation(
    *,
    fixture_id: str,
    event_id: str,
    home: str,
    away: str,
    competition: str,
    kickoff: datetime,
    inventory,
):
    numeric = event_id.removeprefix("sr:match:")
    weekday = kickoff.strftime("%A")
    display = kickoff.strftime("%d/%m %A %H:%M")
    matched = full.MatchedFotMobFullUtcFixture(
        source_fixture_identifier=fixture_id,
        source_capture_manifest_sha256="1" * 64,
        candidate_sha256="2" * 64,
        evidence_sha256="3" * 64,
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff_utc=serialize_utc(kickoff),
    )
    safety = {
        "bet_authorized": False,
        "bookmaker_equivalence_authorized": False,
        "booking_code_authorized": False,
        "canonical_market_mapping_authorized": False,
        "fixture_reconciliation_authorized": True,
        "fresh_price_authorized": False,
        "model_integration_authorized": False,
        "network_acquisition_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "slip_construction_authorized": False,
        "sportradar_metadata_resolution_authorized": False,
        "sportybet_execution_authorized": False,
    }
    return full.SportyBetFotMobFullUtcReconciliation(
        schema_version=full.SCHEMA_VERSION,
        dataset_name=full.DATASET_NAME,
        provider=full.PROVIDER,
        status=full.STATUS,
        matching_basis=full.MATCHING_BASIS,
        source_promotion_sha256="4" * 64,
        source_time_basis_sha256="5" * 64,
        source_bridge_sha256="6" * 64,
        source_metadata_evidence_id="7" * 24,
        source_metadata_evidence_sha256="8" * 64,
        source_event_evidence_id=inventory.source_evidence_id,
        source_event_manifest_sha256=inventory.source_evidence_manifest_sha256,
        source_native_inventory_sha256=native.inventory_sha256(inventory),
        source_event_raw_sha256=inventory.source_raw_sha256,
        event_source_url=(
            "https://www.sportybet.com/ng/lite/preMatch/detail?" + urlencode({
                "eventId": event_id,
                "marketGroupsName": "Main",
                "sportId": "sr:sport:1",
            })
        ),
        sportybet_event_id=event_id,
        sportybet_sport_id="sr:sport:1",
        sportradar_event_id=f"sr:sport_event:{numeric}",
        competition_display=competition,
        home_display=home,
        away_display=away,
        kickoff_display=display,
        kickoff_day=kickoff.day,
        kickoff_month=kickoff.month,
        kickoff_weekday=weekday,
        kickoff_hour=kickoff.hour,
        kickoff_minute=kickoff.minute,
        sportybet_kickoff_year=kickoff.year,
        sportybet_kickoff_timezone="GMT",
        sportybet_utc_offset_seconds=0,
        sportybet_kickoff_utc=kickoff,
        provider_timestamp_subminute_precision_preserved=True,
        source_fotmob_admission_sha256="9" * 64,
        source_fotmob_candidate_bundle_sha256="a" * 64,
        source_fotmob_review_bundle_sha256="b" * 64,
        source_fotmob_handoff_sha256="c" * 64,
        source_fotmob_catalog_sha256="d" * 64,
        source_fotmob_manifest_sha256="e" * 64,
        fotmob_population_sha256="f" * 64,
        disposition=full.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED,
        exact_match_count=1,
        matched_fixture=matched,
        fixture_reconciliation_authorized=True,
        safety=safety,
    )


def _quotes(
    tmp_path: Path,
    *,
    fixture_id: str,
    event_id: str,
    market: MarketId,
    outcomes_and_odds: tuple[tuple[OutcomeId, float], ...],
    line: float | None,
    home: str,
    away: str,
    competition: str,
    kickoff: datetime,
):
    provider_market_id = f"pm-{fixture_id}-{market.value}"
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
            f'href="/ng/lite/preMatch/detail?{urlencode(query)}">{outcome.value}</a>'
        )
    raw = ("<!doctype html><html><body>" + "".join(anchors) + "</body></html>").encode()
    repo = tmp_path / f"evidence-{fixture_id}"
    repo.mkdir()
    source_url = (
        "https://www.sportybet.com/ng/lite/preMatch/detail?" + urlencode({
            "eventId": event_id,
            "marketGroupsName": "Main",
            "sportId": "sr:sport:1",
        })
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
    inventory = native.build_inventory_from_evidence(evidence, allowed_root=allowed_root)
    reconciled = _reconciliation(
        fixture_id=fixture_id,
        event_id=event_id,
        home=home,
        away=away,
        competition=competition,
        kickoff=kickoff,
        inventory=inventory,
    )
    reconciliation_sha = hashlib.sha256(
        full.canonical_reconciliation_bytes(reconciled)
    ).hexdigest()
    source_by_outcome = {item.outcome_id: item for item in inventory.selections}
    mapped_rows = []
    for outcome, _odds in outcomes_and_odds:
        source = source_by_outcome[f"po-{outcome.value}"]
        canonical = make_selection(market, outcome, line=line)
        mapped_rows.append(MappedSportyBetCanonicalSelection(
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
        ))
    mapped = tuple(mapped_rows)
    represented = tuple(item for item in TARGET_MARKET_IDS if item is market)
    missing = tuple(item for item in TARGET_MARKET_IDS if item is not market)
    mapping = SportyBetReviewedCanonicalMarketMapping(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider="SportyBet",
        status=STATUS,
        review_basis=REVIEW_BASIS,
        source_reconciliation_receipt_sha256=reconciliation_sha,
        source_native_inventory_sha256=native.inventory_sha256(inventory),
        source_event_evidence_id=inventory.source_evidence_id,
        sportybet_event_id=event_id,
        sportybet_sport_id="sr:sport:1",
        matched_fotmob_fixture_id=fixture_id,
        review_decisions_sha256=hashlib.sha256(fixture_id.encode()).hexdigest(),
        mapped_selections=mapped,
        represented_target_market_ids=represented,
        unrepresented_target_market_ids=missing,
        all_15_target_markets_represented=False,
        mapped_selection_count=len(mapped),
        unmapped_native_selection_count=0,
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
    quotes = tuple(
        SportyBetExactQuote.from_reviewed_mapping(
            mapping,
            provider_selection_sha256=row.provider_selection_sha256,
            evidence_directory=evidence,
            allowed_evidence_root=allowed_root,
        )
        for row in mapped
    )
    return reconciled, quotes


def fixture_input(
    tmp_path: Path,
    index: int,
    *,
    home: str | None = None,
    away: str | None = None,
    competition: str = "Competition A",
    market: MarketId = MarketId.MATCH_RESULT,
    outcome: OutcomeId = OutcomeId.HOME,
    line: float | None = None,
    probabilities: tuple[float, ...] = (0.60, 0.22, 0.18),
    odds: tuple[tuple[OutcomeId, float], ...] | None = None,
    kickoff: datetime = KICKOFF,
):
    fixture_id = str(1000 + index)
    event_id = f"sr:match:{2000 + index}"
    home_name = home or f"Home {index}"
    away_name = away or f"Away {index}"
    if odds is None:
        if market is MarketId.MATCH_RESULT:
            odds = ((OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0))
        elif market is MarketId.BTTS:
            odds = ((OutcomeId.YES, 2.0), (OutcomeId.NO, 2.0))
        elif market is MarketId.DRAW_NO_BET:
            odds = ((outcome, 1.8),)
        elif market is MarketId.ASIAN_HANDICAP:
            odds = ((outcome, 1.9),)
        else:
            raise AssertionError("test helper requires explicit odds for this market")
    candidate = phase6_variant(
        market,
        outcome,
        line,
        probabilities,
        fixture_id=fixture_id,
        event_id=event_id,
    )
    reconciled, quotes = _quotes(
        tmp_path,
        fixture_id=fixture_id,
        event_id=event_id,
        market=market,
        outcomes_and_odds=odds,
        line=line,
        home=home_name,
        away=away_name,
        competition=competition,
        kickoff=kickoff,
    )
    return AccumulatorFixtureInput(
        candidates=(candidate,),
        quotes=quotes,
        fixture_state=_fixture_state(fixture_id, kickoff),
        reconciliation=reconciled,
    )
