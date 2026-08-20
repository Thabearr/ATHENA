import dataclasses
import inspect
import json

import pytest

from domain.markets import MarketId
from domain.sportybet_early_payout_settlement import (
    OFFICIAL_NIGERIA_FOOTBALL_HELP_URL,
    PRESERVED_NIGERIA_CONFIGURATION_SHA256,
    PRESERVED_NIGERIA_CONFIGURATION_SIZE,
    SOURCE_EVIDENCE_SHA256,
    SOURCE_EVIDENCE_SIZE,
    SportyBetEarlyPayoutSettlementError,
    build_sportybet_early_payout_settlement_receipt,
    canonical_sportybet_early_payout_settlement_receipt_bytes,
    revalidate_sportybet_early_payout_settlement_receipt,
    reviewed_sportybet_early_payout_settlement_receipt,
    sha256_sportybet_early_payout_settlement_receipt,
    source_evidence_manifest_bytes,
)


EXPECTED_RECEIPT_SHA256 = (
    "921db06634ba4d210f100591c0c9acda5ae44db49452936e2229095530c01f76"
)


def _build():
    return build_sportybet_early_payout_settlement_receipt(
        source_evidence_manifest_bytes=source_evidence_manifest_bytes(),
    )


def test_exact_source_bound_receipt_identity_and_revalidation():
    receipt = _build()
    receipt_bytes = canonical_sportybet_early_payout_settlement_receipt_bytes(receipt)

    assert receipt == reviewed_sportybet_early_payout_settlement_receipt()
    assert len(receipt_bytes) == 2434
    assert sha256_sportybet_early_payout_settlement_receipt(receipt) == (
        EXPECTED_RECEIPT_SHA256
    )
    assert (
        revalidate_sportybet_early_payout_settlement_receipt(
            receipt=receipt,
            receipt_bytes=receipt_bytes,
            source_evidence_manifest_bytes=source_evidence_manifest_bytes(),
        )
        == receipt
    )


def test_changed_provider_source_evidence_fails_closed():
    mutated = source_evidence_manifest_bytes().replace(b'"mapped_market_id":"60200"', b'"mapped_market_id":"99999"')
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        build_sportybet_early_payout_settlement_receipt(
            source_evidence_manifest_bytes=mutated
        )


def test_nigeria_source_manifest_binds_real_help_and_raw_configuration_ancestry():
    receipt = _build()
    assert receipt.source_evidence_manifest_sha256 == SOURCE_EVIDENCE_SHA256
    assert receipt.source_evidence_manifest_size == SOURCE_EVIDENCE_SIZE
    assert receipt.sources[0].source_identity == OFFICIAL_NIGERIA_FOOTBALL_HELP_URL
    assert receipt.sources[1].sha256 == PRESERVED_NIGERIA_CONFIGURATION_SHA256
    assert receipt.sources[1].byte_size == PRESERVED_NIGERIA_CONFIGURATION_SIZE


def test_receipt_freezes_1up_2up_settlement_and_site_configuration_keys():
    receipt = _build()
    one_up, two_up = receipt.market_rules

    assert (one_up.market_id, one_up.provider_configuration_key, one_up.provider_source_market_id, one_up.provider_mapped_market_id, one_up.lead_threshold) == (
        MarketId.MATCH_RESULT_1UP,
        "one_x_two_one_up",
        "1",
        "60200",
        1,
    )
    assert (two_up.market_id, two_up.provider_configuration_key, two_up.provider_source_market_id, two_up.provider_mapped_market_id, two_up.lead_threshold) == (
        MarketId.MATCH_RESULT_2UP,
        "one_x_two_two_up",
        "1",
        "60100",
        2,
    )
    for rule in receipt.market_rules:
        assert rule.provider_pre_match_enabled is True
        assert rule.provider_live_enabled is True
        assert rule.provider_settlement_feature_enabled is True
        assert rule.event_topology == "OVERLAPPING_EVENTS"
        assert rule.selected_team_settlement == (
            "LEAD_THRESHOLD_HIT_OR_REGULATION_TIME_WIN"
        )
        assert rule.draw_settlement == "REGULATION_TIME_FULL_TIME_DRAW"
        assert rule.full_time_win_fallback is True
        assert rule.early_trigger_irreversible is True
        assert rule.triggered_selection_stands_if_abandoned is True

    assert one_up.triggered_selection_abandonment_proof_clause_ids == (
        "1UP",
        "FOOTBALL_INTERRUPTION",
    )
    assert two_up.triggered_selection_abandonment_proof_clause_ids == (
        "2UP_ABANDONMENT",
    )


def test_1up_abandonment_cannot_outlive_its_exact_nigeria_proof_ancestry():
    one_up = _build().market_rules[0]
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        dataclasses.replace(
            one_up,
            triggered_selection_abandonment_proof_clause_ids=("1UP",),
        )
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        dataclasses.replace(one_up, triggered_selection_stands_if_abandoned=False)


def test_abandonment_semantics_do_not_invent_abandonment_probability_or_authority():
    receipt = _build()
    assert receipt.normal_completion_probability_scope == (
        "REGULATION_TIME_FOOTBALL_PATH_ONLY_ABANDONMENT_FREQUENCY_NOT_MODELED"
    )
    assert dict(receipt.safety)["abandonment_probability_modeled"] is False
    assert all(value is False for value in dict(receipt.safety).values())


def test_receipt_is_immutable_canonical_json_and_coordinated_mutation_fails():
    receipt = _build()
    receipt_bytes = canonical_sportybet_early_payout_settlement_receipt_bytes(receipt)
    assert receipt_bytes.endswith(b"\n")
    parsed = json.loads(receipt_bytes)
    assert receipt_bytes == (
        json.dumps(
            parsed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        dataclasses.replace(receipt, review_scope="FORGED")
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        revalidate_sportybet_early_payout_settlement_receipt(
            receipt=receipt,
            receipt_bytes=receipt_bytes + b"\n",
            source_evidence_manifest_bytes=source_evidence_manifest_bytes(),
        )


def test_provider_receipt_builder_accepts_no_price_or_authority_override():
    parameters = inspect.signature(
        build_sportybet_early_payout_settlement_receipt
    ).parameters
    assert set(parameters) == {
        "source_evidence_manifest_bytes",
    }
    assert not ({"odds", "price", "selection_authorized", "bet_authorized"} & set(parameters))
