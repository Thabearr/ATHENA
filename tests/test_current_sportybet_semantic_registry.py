from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from domain import current_sportybet_semantic_registry as registry
from domain import sportybet_live_event_quote_evidence as live
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.model_status import (
    AnalyticalProbabilityCapability,
    MissingInputPolicy,
    PricingAuthority,
    ProbabilityInputNamespace,
    SelectionAuthority,
    SettlementCapability,
)


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _market(market_id: str, name: str, outcomes, specifier=None):
    return {
        "id": market_id,
        "desc": name,
        "specifier": specifier,
        "outcomes": [
            {"id": outcome_id, "desc": outcome_name, "odds": "2.00", "isActive": 1}
            for outcome_id, outcome_name in outcomes
        ],
    }


def _payload(
    *,
    observed_at: datetime = NOW,
    kickoff: datetime | None = None,
    event_id: str = "sr:match:99999999",
):
    kickoff = kickoff or (observed_at + timedelta(hours=2))
    rows = [
        _market("1", "1X2", (("1", "Home"), ("2", "Draw"), ("3", "Away"))),
        _market("18", "Over/Under", (("12", "Over 0.5"), ("13", "Under 0.5")), "total=0.5"),
        _market("16", "Asian Handicap -0.5", (("1714", "Home (-0.5)"), ("1715", "Away (+0.5)")), "hcp=-0.5"),
        _market("10", "Double Chance", (("9", "Home or Draw"), ("10", "Home or Away"), ("11", "Draw or Away"))),
        _market("29", "GG/NG", (("74", "Yes"), ("76", "No"))),
        _market("11", "Draw No Bet", (("4", "Home"), ("5", "Away"))),
        _market("33", "Home Team to Win to Nil", (("74", "Yes"), ("76", "No"))),
        _market("34", "Away Team to Win to Nil", (("74", "Yes"), ("76", "No"))),
        _market("50", "Home Team to Win Either Half", (("74", "Yes"), ("76", "No"))),
        _market("51", "Away Team to Win Either Half", (("74", "Yes"), ("76", "No"))),
        _market("854", "Home Team or Over 2.5", (("74", "Yes"), ("76", "No")), "total=2.5"),
        _market("856", "Draw or Over 2.5", (("74", "Yes"), ("76", "No")), "total=2.5"),
        _market("858", "Away or Over 2.5", (("74", "Yes"), ("76", "No")), "total=2.5"),
        _market("60200", "1X2 - 1UP", (("1", "Home"), ("2", "Draw"), ("3", "Away"))),
        _market("60100", "1X2 - 2UP", (("1", "Home"), ("2", "Draw"), ("3", "Away"))),
    ]
    return {
        "bizCode": 10000,
        "data": {
            "eventId": event_id,
            "homeTeamName": "Synthetic Home",
            "awayTeamName": "Synthetic Away",
            "estimateStartTime": kickoff.timestamp() * 1000,
            "bookingStatus": "Available",
            "status": 0,
            "matchStatus": "Not Started",
            "markets": rows,
        },
    }


def _evidence(tmp_path: Path, *, payload=None, observed_at: datetime = NOW):
    root = tmp_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    raw = live._canonical_json_bytes(payload or _payload(observed_at=observed_at))
    event_id = json.loads(raw)["data"]["eventId"]
    manifest = live._build_manifest(
        event_id=event_id,
        raw=raw,
        status=200,
        observed_at=observed_at,
    )
    evidence_root = live._evidence_root(root, create=True)
    directory = evidence_root / live.capture_identifier(manifest)
    directory.mkdir()
    (directory / live.RAW_FILENAME).write_bytes(raw)
    (directory / live.MANIFEST_FILENAME).write_bytes(live.canonical_manifest_bytes(manifest))
    return registry.load_provider_event_evidence(directory, repository_root=root)


def test_registry_has_exactly_the_canonical_fifteen_and_is_model_derived(tmp_path):
    evidence = _evidence(tmp_path)
    value = registry.build_registry([evidence], evaluation_time=NOW)
    assert {row.market_id for row in value.coverage} == set(MarketId)
    assert len(value.coverage) == len(set(MarketId)) == 15
    assert value.authority == {
        "production_model": False,
        "production_probability": False,
        "phase6": False,
        "production_price_all": False,
        "production_market_router": False,
        "production_portfolio": False,
        "production_selection": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
    weh = next(row for row in value.coverage if row.market_id is MarketId.HOME_WIN_EITHER_HALF)
    assert weh.probability_input_namespace is ProbabilityInputNamespace.SPECIALIZED_WEH_PRE_MATCH_FEATURES
    assert weh.missing_input_policy is MissingInputPolicy.REJECT_MARKET
    assert all(row.pricing_authority is PricingAuthority.NOT_AUTHORIZED for row in value.coverage)
    assert all(row.selection_authority is SelectionAuthority.NOT_AUTHORIZED for row in value.coverage)
    assert next(row for row in value.coverage if row.market_id is MarketId.ASIAN_HANDICAP).settlement_capability is SettlementCapability.FULL_SETTLEMENT_DISTRIBUTION
    assert next(row for row in value.coverage if row.market_id is MarketId.DRAW_NO_BET).settlement_capability is SettlementCapability.FULL_SETTLEMENT_DISTRIBUTION


def test_registry_rejects_missing_duplicate_and_unknown_coverage(tmp_path):
    evidence = _evidence(tmp_path)
    rows = list(registry.build_registry([evidence], evaluation_time=NOW).coverage)
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        registry.CurrentSportyBetSemanticRegistry(
            schema_version=1,
            dataset_name=registry.DATASET_NAME,
            contract_version=1,
            policy_id=registry.POLICY_ID,
            evaluation_time=NOW,
            scan_cap=20,
            scan_attempts=1,
            coverage=tuple(rows[:-1]),
            source_contract_identities=registry.SOURCE_CONTRACT_IDENTITIES,
            authority=registry._AUTHORITY,
        )
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        registry.CurrentSportyBetSemanticRegistry(
            schema_version=1,
            dataset_name=registry.DATASET_NAME,
            contract_version=1,
            policy_id=registry.POLICY_ID,
            evaluation_time=NOW,
            scan_cap=20,
            scan_attempts=1,
            coverage=tuple(rows[:-1] + [rows[0]]),
            source_contract_identities=registry.SOURCE_CONTRACT_IDENTITIES,
            authority=registry._AUTHORITY,
        )


def test_exact_provider_semantics_and_settlement_classes(tmp_path):
    value = registry.build_registry([_evidence(tmp_path)], evaluation_time=NOW)
    assert next(row for row in value.coverage if row.market_id is MarketId.MATCH_RESULT).ordinary_devig_partition_valid
    dc = next(row for row in value.coverage if row.market_id is MarketId.DOUBLE_CHANCE)
    assert dc.event_set_overlaps and not dc.ordinary_devig_partition_valid
    dnb = next(row for row in value.coverage if row.market_id is MarketId.DRAW_NO_BET)
    assert dnb.push_or_split_settlement and dnb.settlement_class is registry.SettlementClass.DNB_WIN_PUSH_LOSS
    ah = next(row for row in value.coverage if row.market_id is MarketId.ASIAN_HANDICAP)
    assert ah.push_or_split_settlement and ah.settlement_class is registry.SettlementClass.ASIAN_HANDICAP_FULL_SETTLEMENT
    one_up = next(row for row in value.coverage if row.market_id is MarketId.MATCH_RESULT_1UP)
    two_up = next(row for row in value.coverage if row.market_id is MarketId.MATCH_RESULT_2UP)
    assert one_up.event_set_overlaps and two_up.event_set_overlaps
    assert not one_up.ordinary_devig_partition_valid and not two_up.ordinary_devig_partition_valid


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["data"]["markets"][0].update(desc="1X2 near"),
        lambda payload: payload["data"]["markets"][0]["outcomes"][0].update(id="999"),
        lambda payload: payload["data"]["markets"][0]["outcomes"][0].update(desc="HOME"),
        lambda payload: payload["data"]["markets"][1].update(specifier="total=1.5"),
    ],
)
def test_provider_label_id_and_line_drift_fail_closed(tmp_path, mutator):
    payload = _payload()
    mutator(payload)
    value = registry.build_registry([_evidence(tmp_path, payload=payload)], evaluation_time=NOW)
    match = next(row for row in value.coverage if row.market_id is MarketId.MATCH_RESULT)
    totals = next(row for row in value.coverage if row.market_id is MarketId.TOTAL_GOALS)
    if payload["data"]["markets"][0]["desc"] != "1X2":
        assert match.provider_status is registry.ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
    if payload["data"]["markets"][1]["specifier"] != "total=0.5":
        assert totals.provider_status is registry.ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN


def test_integer_total_is_observed_but_not_model_eligible(tmp_path):
    payload = _payload()
    payload["data"]["markets"][1]["specifier"] = "total=1"
    payload["data"]["markets"][1]["outcomes"][0]["desc"] = "Over 1"
    payload["data"]["markets"][1]["outcomes"][1]["desc"] = "Under 1"
    value = registry.build_registry([_evidence(tmp_path, payload=payload)], evaluation_time=NOW)
    row = next(item for item in value.coverage if item.market_id is MarketId.TOTAL_GOALS)
    assert row.provider_status is registry.ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY
    assert row.observations[0].line_analytically_eligible is False
    assert row.ordinary_devig_partition_valid is False
    assert row.research_readiness == "SEMANTIC_READY_EXACT_LINE_MODEL_BLOCKED"


@pytest.mark.parametrize(
    ("market_index", "specifier", "market_name", "outcome_labels"),
    [
        (1, "total=0.25", "Over/Under", ("Over 0.25", "Under 0.25")),
        (2, "hcp=0.1", "Asian Handicap 0.1", ("Home (+0.1)", "Away (-0.1)")),
        (1, None, "Over/Under", ("Over 0.5", "Under 0.5")),
    ],
)
def test_unproven_or_unsupported_line_grammar_fails_closed(
    tmp_path, market_index, specifier, market_name, outcome_labels
):
    payload = _payload()
    market = payload["data"]["markets"][market_index]
    market["specifier"] = specifier
    market["desc"] = market_name
    for outcome, label in zip(market["outcomes"], outcome_labels, strict=True):
        outcome["desc"] = label
    value = registry.build_registry([_evidence(tmp_path, payload=payload)], evaluation_time=NOW)
    market_id = MarketId.TOTAL_GOALS if market_index == 1 else MarketId.ASIAN_HANDICAP
    row = next(item for item in value.coverage if item.market_id is market_id)
    assert row.provider_status is registry.ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
    assert row.blocker in {
        "CONFLICTING_CURRENT_PROVIDER_SEMANTICS",
        "NO_EXACT_CURRENT_PROVIDER_SEMANTIC_EVIDENCE",
    }


def test_asian_handicap_quarter_line_retains_split_settlement_semantics(tmp_path):
    payload = _payload()
    market = payload["data"]["markets"][2]
    market["specifier"] = "hcp=0.25"
    market["desc"] = "Asian Handicap 0.25"
    market["outcomes"][0]["desc"] = "Home (+0.25)"
    market["outcomes"][1]["desc"] = "Away (-0.25)"
    value = registry.build_registry([_evidence(tmp_path, payload=payload)], evaluation_time=NOW)
    row = next(item for item in value.coverage if item.market_id is MarketId.ASIAN_HANDICAP)
    assert row.provider_status is registry.ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY
    assert row.proven_lines == ("hcp=0.25",)
    assert row.push_or_split_settlement is True
    assert row.settlement_class is registry.SettlementClass.ASIAN_HANDICAP_FULL_SETTLEMENT


def test_stale_nonbookable_and_future_evidence_never_issues_current_support(tmp_path):
    stale = registry.build_registry([_evidence(tmp_path / "stale", observed_at=NOW - timedelta(seconds=901))], evaluation_time=NOW)
    row = next(item for item in stale.coverage if item.market_id is MarketId.MATCH_RESULT)
    assert row.provider_status is registry.ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
    assert row.evidence_freshness is registry.EvidenceFreshnessState.STALE

    future = registry.build_registry([_evidence(tmp_path / "future", observed_at=NOW + timedelta(seconds=1))], evaluation_time=NOW)
    row = next(item for item in future.coverage if item.market_id is MarketId.MATCH_RESULT)
    assert row.evidence_freshness is registry.EvidenceFreshnessState.FUTURE_DATED

    boundary_payload = _payload(kickoff=NOW + timedelta(seconds=120))
    boundary = registry.build_registry(
        [_evidence(tmp_path / "boundary", payload=boundary_payload)],
        evaluation_time=NOW,
    )
    row = next(item for item in boundary.coverage if item.market_id is MarketId.MATCH_RESULT)
    assert row.provider_status is registry.ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
    assert row.evidence_freshness is registry.EvidenceFreshnessState.TOO_CLOSE_TO_KICKOFF


def test_replay_rejects_mutated_retained_inventory_and_detached_hash(tmp_path):
    evidence = _evidence(tmp_path)
    changed = replace(evidence, inventory=replace(evidence.inventory, home_team_name="Tampered Home"))
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        registry.replay_event_evidence(changed)
    changed_hash = replace(evidence, inventory=replace(evidence.inventory, source_raw_sha256="0" * 64))
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        registry.replay_event_evidence(changed_hash)


def test_fixture_identity_and_source_contract_binding_fail_closed(tmp_path):
    evidence = _evidence(tmp_path)
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        registry.load_provider_event_evidence(
            evidence.evidence_directory,
            repository_root=evidence.repository_root,
            fixture_identity="sr:match:12345678",
        )

    value = registry.build_registry([evidence], evaluation_time=NOW)
    altered = dict(value.source_contract_identities)
    altered["event_detail"] = "0" * 64
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        registry.CurrentSportyBetSemanticRegistry(
            schema_version=value.schema_version,
            dataset_name=value.dataset_name,
            contract_version=value.contract_version,
            policy_id=value.policy_id,
            evaluation_time=value.evaluation_time,
            scan_cap=value.scan_cap,
            scan_attempts=value.scan_attempts,
            coverage=value.coverage,
            source_contract_identities=altered,
            authority=value.authority,
        )


def test_conflicting_same_native_semantics_fail_closed(tmp_path):
    first = _evidence(tmp_path / "first", payload=_payload(event_id="sr:match:99999999"))
    payload = _payload(event_id="sr:match:99999998")
    payload["data"]["markets"][0]["desc"] = "1X2 near"
    second = _evidence(tmp_path / "second", payload=payload)
    value = registry.build_registry([first, second], evaluation_time=NOW)
    row = next(item for item in value.coverage if item.market_id is MarketId.MATCH_RESULT)
    assert row.provider_status is registry.ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
    assert row.evidence_freshness is registry.EvidenceFreshnessState.CONFLICTING
    assert row.blocker == "CONFLICTING_CURRENT_PROVIDER_SEMANTICS"


def test_empty_provider_evidence_is_explicitly_unproven_for_all_markets():
    value = registry.build_registry([], evaluation_time=NOW)
    assert len(value.coverage) == len(MarketId)
    assert all(
        row.provider_status is registry.ProviderSemanticStatus.CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN
        for row in value.coverage
    )
    assert all(row.blocker == "NO_EXACT_CURRENT_PROVIDER_SEMANTIC_EVIDENCE" for row in value.coverage)


def test_authority_cannot_be_granted_through_replace(tmp_path):
    value = registry.build_registry([_evidence(tmp_path)], evaluation_time=NOW)
    row = next(item for item in value.coverage if item.market_id is MarketId.MATCH_RESULT)
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        replace(row, pricing_authority=PricingAuthority.AUTHORIZED)
    with pytest.raises(registry.CurrentSportyBetSemanticRegistryError):
        replace(value, authority={**value.authority, "bet": True})


def test_provider_policy_is_literal_and_does_not_offer_generic_aliases():
    for market_id in MarketId:
        policy = registry.provider_policy(market_id)
        assert policy["market_ids"]
        assert policy["outcomes"]
        assert "fuzzy" not in str(policy).lower()
        assert "contains" not in str(policy).lower()


def test_canonical_registry_bytes_are_deterministic_and_source_bound(tmp_path):
    value = registry.build_registry([_evidence(tmp_path)], evaluation_time=NOW)
    assert value.canonical_bytes.endswith(b"\n")
    assert registry.validate_registry(value) == value.canonical_sha256
    assert value.canonical_sha256 == registry.validate_registry(value)
    parsed = json.loads(value.canonical_bytes)
    assert set(parsed["coverage"][0]) >= {"canonical_market_id", "provider_status", "observations"}
    assert parsed["source_contract_identities"] == dict(registry.SOURCE_CONTRACT_IDENTITIES)


def test_registry_identity_is_independent_of_evidence_input_order(tmp_path):
    first = _evidence(tmp_path / "first", payload=_payload(event_id="sr:match:99999999"))
    second = _evidence(tmp_path / "second", payload=_payload(event_id="sr:match:99999998"))
    left = registry.build_registry([first, second], evaluation_time=NOW)
    right = registry.build_registry([second, first], evaluation_time=NOW)
    assert left.canonical_bytes == right.canonical_bytes
    assert left.canonical_sha256 == right.canonical_sha256


def test_provider_policy_has_no_market_alias_rescue():
    policy = registry.provider_policy(MarketId.TOTAL_GOALS)
    assert policy["market_ids"] == ("18",)
    assert policy["market_names"] == ("Over/Under", "Total Goals")
    assert "fuzzy" not in registry.POLICY_ID.lower()
