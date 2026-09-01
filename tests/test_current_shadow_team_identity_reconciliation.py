from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from config import current_shadow_team_identity_aliases as aliases
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout

UTC = timezone.utc
KICKOFF = datetime(2026, 9, 1, 18, 45, tzinfo=UTC)


def _row(*, fixture_id="5836791", home="Lincoln", away="Blackburn", competition="Championship"):
    return SimpleNamespace(
        source_fixture_identifier=fixture_id,
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff=KICKOFF,
    )


def _candidate(
    *,
    fixture_id=5836791,
    home="Lincoln",
    home_long="Lincoln City",
    away="Blackburn",
    away_long="Blackburn Rovers",
    competition="Championship",
):
    return SimpleNamespace(
        source_match_id=fixture_id,
        home_name=home,
        home_long_name=home_long,
        away_name=away,
        away_long_name=away_long,
        source_competition_name=competition,
        kickoff_utc=KICKOFF,
    )


def _admission(candidate):
    return SimpleNamespace(
        handoff=SimpleNamespace(
            candidate_bundle=SimpleNamespace(candidates=(candidate,)),
        )
    )


def _event(*, home, away, competition="Championship", kickoff=KICKOFF):
    return SimpleNamespace(
        home_team_name=home,
        away_team_name=away,
        competition_name=competition,
        kickoff_utc=kickoff,
    )


def test_contract_pins_source_native_and_scoped_alias_semantics():
    assert fanout.calculate_contract_sha256() == fanout.EXPECTED_CONTRACT_SHA256
    identity = fanout.validate_contract()
    assert identity["contract_sha256"] == fanout.EXPECTED_CONTRACT_SHA256
    assert identity["team_alias_registry_policy_id"] == aliases.POLICY_ID
    assert "NO_FUZZY" in fanout.MATCHING_BASIS
    assert "NO_REVERSAL" in fanout.MATCHING_BASIS


def test_exact_fotmob_long_names_reconcile_without_global_alias_guessing():
    row = _row()
    candidate = _candidate()
    event = _event(home="Lincoln City", away="Blackburn Rovers")

    assert fanout._match_event(event, (row,), _admission(candidate)) == (row,)


def test_reviewed_scoped_alias_covers_provider_only_name_variant():
    row = _row(fixture_id="5836792", home="Portsmouth", away="Derby")
    candidate = _candidate(
        fixture_id=5836792,
        home="Portsmouth",
        home_long="Portsmouth",
        away="Derby",
        away_long="Derby County",
    )
    event = _event(home="Portsmouth FC", away="Derby County")

    assert fanout._match_event(event, (row,), _admission(candidate)) == (row,)
    assert aliases.exact_provider_team_alias_matches(
        competition="Championship",
        source_name="Portsmouth",
        provider_name="Portsmouth FC",
    ) is True


def test_alias_is_competition_scoped_and_not_fuzzy():
    assert aliases.exact_provider_team_alias_matches(
        competition="Championship",
        source_name="Portsmouth",
        provider_name="Portsmouth F.C.",
    ) is False
    assert aliases.exact_provider_team_alias_matches(
        competition="League One",
        source_name="Portsmouth",
        provider_name="Portsmouth FC",
    ) is False


def test_wrong_kickoff_competition_or_orientation_remains_unmatched():
    row = _row()
    candidate = _candidate()
    admission = _admission(candidate)

    assert fanout._match_event(
        _event(home="Lincoln City", away="Blackburn Rovers", kickoff=KICKOFF + timedelta(minutes=1)),
        (row,),
        admission,
    ) == ()
    assert fanout._match_event(
        _event(home="Lincoln City", away="Blackburn Rovers", competition="League One"),
        (row,),
        admission,
    ) == ()
    assert fanout._match_event(
        _event(home="Blackburn Rovers", away="Lincoln City"),
        (row,),
        admission,
    ) == ()


def test_source_candidate_ancestry_mismatch_fails_closed():
    row = _row()
    candidate = _candidate(home="Different")

    try:
        fanout._match_event(
            _event(home="Lincoln City", away="Blackburn Rovers"),
            (row,),
            _admission(candidate),
        )
    except fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError as exc:
        assert "differs from exact source candidate ancestry" in str(exc)
    else:
        raise AssertionError("tampered source candidate ancestry did not fail closed")
