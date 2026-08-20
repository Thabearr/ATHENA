import dataclasses
import inspect
import json

import pytest

from domain.markets import MarketId
from domain.sportybet_early_payout_settlement import (
    CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES,
    OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES,
    OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES,
    SportyBetEarlyPayoutSettlementError,
    build_sportybet_early_payout_settlement_receipt,
    canonical_sportybet_early_payout_settlement_receipt_bytes,
    revalidate_sportybet_early_payout_settlement_receipt,
    reviewed_sportybet_early_payout_settlement_receipt,
    sha256_sportybet_early_payout_settlement_receipt,
)


EXPECTED_RECEIPT_SHA256 = (
    "123868403511a175d3eccba8613f5681c56ddcb3cdb304aa132104dd90e0ca10"
)


def _build():
    return build_sportybet_early_payout_settlement_receipt(
        official_football_help_review_bytes=OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES,
        official_early_payout_help_review_bytes=(
            OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES
        ),
        captured_site_configuration_projection_bytes=(
            CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES
        ),
    )


def test_exact_source_bound_receipt_identity_and_revalidation():
    receipt = _build()
    receipt_bytes = canonical_sportybet_early_payout_settlement_receipt_bytes(receipt)

    assert receipt == reviewed_sportybet_early_payout_settlement_receipt()
    assert len(receipt_bytes) == 2029
    assert sha256_sportybet_early_payout_settlement_receipt(receipt) == (
        EXPECTED_RECEIPT_SHA256
    )
    assert (
        revalidate_sportybet_early_payout_settlement_receipt(
            receipt=receipt,
            receipt_bytes=receipt_bytes,
            official_football_help_review_bytes=OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES,
            official_early_payout_help_review_bytes=(
                OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES
            ),
            captured_site_configuration_projection_bytes=(
                CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES
            ),
        )
        == receipt
    )


@pytest.mark.parametrize(
    "field,mutated",
    (
        (
            "official_football_help_review_bytes",
            OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES + b"changed",
        ),
        (
            "official_early_payout_help_review_bytes",
            OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES.replace(b"2UP", b"3UP", 1),
        ),
        (
            "captured_site_configuration_projection_bytes",
            CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES.replace(
                b"one_x_two_two_up", b"one_x_two_three_up"
            ),
        ),
    ),
)
def test_changed_provider_source_evidence_fails_closed(field, mutated):
    values = {
        "official_football_help_review_bytes": OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES,
        "official_early_payout_help_review_bytes": (
            OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES
        ),
        "captured_site_configuration_projection_bytes": (
            CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES
        ),
    }
    values[field] = mutated
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        build_sportybet_early_payout_settlement_receipt(**values)


def test_receipt_freezes_1up_2up_settlement_and_site_configuration_keys():
    receipt = _build()
    one_up, two_up = receipt.market_rules

    assert (one_up.market_id, one_up.provider_configuration_key, one_up.lead_threshold) == (
        MarketId.MATCH_RESULT_1UP,
        "one_x_two_one_up",
        1,
    )
    assert (two_up.market_id, two_up.provider_configuration_key, two_up.lead_threshold) == (
        MarketId.MATCH_RESULT_2UP,
        "one_x_two_two_up",
        2,
    )
    for rule in receipt.market_rules:
        assert rule.event_topology == "OVERLAPPING_EVENTS"
        assert rule.selected_team_settlement == (
            "LEAD_THRESHOLD_HIT_OR_REGULATION_TIME_WIN"
        )
        assert rule.draw_settlement == "REGULATION_TIME_FULL_TIME_DRAW"
        assert rule.full_time_win_fallback is True
        assert rule.early_trigger_irreversible is True
        assert rule.triggered_selection_stands_if_abandoned is True


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
    forged = dataclasses.replace(receipt, review_scope="FORGED")
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        canonical_sportybet_early_payout_settlement_receipt_bytes(forged)
    with pytest.raises(SportyBetEarlyPayoutSettlementError):
        revalidate_sportybet_early_payout_settlement_receipt(
            receipt=receipt,
            receipt_bytes=receipt_bytes + b"\n",
            official_football_help_review_bytes=OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES,
            official_early_payout_help_review_bytes=(
                OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES
            ),
            captured_site_configuration_projection_bytes=(
                CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES
            ),
        )


def test_provider_receipt_builder_accepts_no_price_or_authority_override():
    parameters = inspect.signature(
        build_sportybet_early_payout_settlement_receipt
    ).parameters
    assert set(parameters) == {
        "official_football_help_review_bytes",
        "official_early_payout_help_review_bytes",
        "captured_site_configuration_projection_bytes",
    }
    assert not ({"odds", "price", "selection_authorized", "bet_authorized"} & set(parameters))
