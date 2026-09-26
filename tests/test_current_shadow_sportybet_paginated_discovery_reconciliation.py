"""Contract and retention tests for sportybet paginated discovery reconciliation overlay."""
from __future__ import annotations

import pytest

from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated


def test_paginated_discovery_contract_is_pinned_and_matches_cascade() -> None:
    contract = paginated.validate_contract()
    assert paginated.calculate_contract_sha256() == paginated.EXPECTED_CONTRACT_SHA256
    assert contract["contract_sha256"] == paginated.EXPECTED_CONTRACT_SHA256
    assert paginated.EXPECTED_CONTRACT_SHA256 == "baf9d4301d56669abebf8793ecac41aa2f427094dfcf1ee7ebf2aa411996f451"


def test_paginated_discovery_zero_execution_authority() -> None:
    authority = paginated.AUTHORITY
    assert authority["login"] is False
    assert authority["cookies"] is False
    assert authority["wallet"] is False
    assert authority["staking"] is False
    assert authority["bet"] is False
    assert authority["wager_placed"] is False
    assert authority["price_all"] is False
