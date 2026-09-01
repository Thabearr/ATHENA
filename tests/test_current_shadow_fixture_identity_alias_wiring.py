from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from domain import current_shadow_fixture_identity_aliases as aliases
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout


UTC = timezone.utc


def test_shadow_reconciliation_contract_binds_exact_alias_registry():
    identity = fanout.validate_contract()
    assert fanout.MATCHING_BASIS == aliases.MATCHING_BASIS
    assert fanout.FIXTURE_TEAM_ALIAS_POLICY_ID == aliases.POLICY_ID
    assert fanout.FIXTURE_TEAM_ALIAS_REGISTRY_SHA256 == aliases.REGISTRY_SHA256
    assert identity["contract_sha256"] == fanout.EXPECTED_CONTRACT_SHA256
    assert identity["fixture_team_alias_policy_id"] == aliases.POLICY_ID
    assert identity["fixture_team_alias_registry_sha256"] == aliases.REGISTRY_SHA256


def test_candidate_local_shadow_module_uses_alias_matcher_without_mutating_frozen_reviewed_module():
    kickoff = datetime(2026, 9, 1, 18, 45, tzinfo=UTC)
    event = SimpleNamespace(
        competition_name="Championship",
        home_team_name="Lincoln City",
        away_team_name="Blackburn Rovers",
        kickoff_utc=kickoff,
    )
    reviewed_row = SimpleNamespace(
        competition="Championship",
        home_team="Lincoln",
        away_team="Blackburn",
        kickoff=kickoff,
    )

    assert fanout.legacy.reviewed._match_event(event, (reviewed_row,)) == (reviewed_row,)
    # The frozen non-Shadow matcher remains literal and therefore rejects the same drift.
    assert fanout.reviewed._match_event(event, (reviewed_row,)) == ()
