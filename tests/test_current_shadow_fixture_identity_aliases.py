from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_aliases as aliases


UTC = timezone.utc
KICKOFF = datetime(2026, 9, 1, 18, 45, tzinfo=UTC)


def _event(
    *,
    home="Lincoln City",
    away="Blackburn Rovers",
    competition="Championship",
    kickoff=KICKOFF,
):
    return SimpleNamespace(
        home_team_name=home,
        away_team_name=away,
        competition_name=competition,
        kickoff_utc=kickoff,
    )


def _reviewed(
    *,
    home="Lincoln",
    away="Blackburn",
    competition="Championship",
    kickoff=KICKOFF,
):
    return SimpleNamespace(
        source_fixture_identifier="5836791",
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff=kickoff,
    )


def test_registry_identity_is_deterministic_and_pinned():
    assert aliases.POLICY_ID == "ATHENA_CURRENT_SHADOW_EXPLICIT_FIXTURE_TEAM_ALIAS_V3"
    assert aliases.REGISTRY_SHA256 == (
        "cb3573bb5d695aca8a496a50c4ad6962b88f3670175058f8239c5daf1730f0ce"
    )
    assert aliases.registry_sha256() == aliases.REGISTRY_SHA256
    assert len(aliases.TEAM_ALIASES) == 55


@pytest.mark.parametrize(
    ("competition", "fotmob_home", "sportybet_home", "fotmob_away", "sportybet_away"),
    (
        ("Premier League", "Okzhetpes Kokshetau", "FC Okzhetpes", "Zhenis", "FC Zhenis"),
        ("China League", "Yanbian Longding", "Yanbian Longding", "Guangdong GZ-Power", "Guandong GZ-Power FC"),
        ("China League", "Dalian K'un City", "Dalian Kun City", "Ningbo Professional", "Ningbo Professional FC"),
    ),
)
def test_run_35277452572_explicit_aliases_match_only_the_evidenced_pairs(
    competition, fotmob_home, sportybet_home, fotmob_away, sportybet_away
):
    row = _reviewed(
        competition=competition,
        home=fotmob_home,
        away=fotmob_away,
    )
    event = _event(
        competition=competition,
        home=sportybet_home,
        away=sportybet_away,
    )
    assert aliases.match_event(event, (row,)) == (row,)


def test_literal_identity_still_matches_without_registry_entry():
    row = _reviewed(home="West Ham", away="Wolves")
    event = _event(home="West Ham", away="Wolves")
    assert aliases.match_event(event, (row,)) == (row,)


def test_observed_championship_alias_pair_matches():
    row = _reviewed()
    assert aliases.match_event(_event(), (row,)) == (row,)


def test_observed_league_one_alias_pair_matches():
    row = _reviewed(
        home="Bradford",
        away="Cambridge",
        competition="League One",
        kickoff=KICKOFF,
    )
    event = _event(
        home="Bradford City FC",
        away="Cambridge United",
        competition="League One",
        kickoff=KICKOFF,
    )
    assert aliases.match_event(event, (row,)) == (row,)


def test_observed_league_two_alias_pair_matches():
    row = _reviewed(
        home="Accrington",
        away="Grimsby",
        competition="League Two",
        kickoff=KICKOFF,
    )
    event = _event(
        home="Accrington Stanley",
        away="Grimsby Town",
        competition="League Two",
        kickoff=KICKOFF,
    )
    assert aliases.match_event(event, (row,)) == (row,)


def test_existing_reviewed_saudi_alias_pair_matches():
    kickoff = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
    row = _reviewed(
        home="Al Hilal",
        away="Al Ahli",
        competition="Saudi Pro League",
        kickoff=kickoff,
    )
    event = _event(
        home="Al Hilal SFC",
        away="Al Ahli Saudi FC",
        competition="Saudi Pro League",
        kickoff=kickoff,
    )
    assert aliases.match_event(event, (row,)) == (row,)


def test_existing_reviewed_swiss_alias_pair_matches():
    kickoff = datetime(2026, 9, 1, 18, 30, tzinfo=UTC)
    row = _reviewed(
        home="FC Zürich",
        away="Young Boys",
        competition="Super League",
        kickoff=kickoff,
    )
    event = _event(
        home="FC Zurich",
        away="Young Boys Bern",
        competition="Super League",
        kickoff=kickoff,
    )
    assert aliases.match_event(event, (row,)) == (row,)


def test_unknown_or_convenient_suffix_alias_does_not_match():
    row = _reviewed(home="Madeup", away="Example")
    event = _event(home="Madeup FC", away="Example United")
    assert aliases.match_event(event, (row,)) == ()


def test_alias_is_competition_scoped():
    row = _reviewed(competition="League One")
    event = _event(competition="League One")
    # Lincoln/Blackburn aliases were evidenced for Championship, not League One.
    assert aliases.match_event(event, (row,)) == ()


def test_home_away_reversal_does_not_match():
    row = _reviewed()
    event = _event(home="Blackburn Rovers", away="Lincoln City")
    assert aliases.match_event(event, (row,)) == ()


def test_full_utc_kickoff_is_exact_with_no_tolerance():
    row = _reviewed()
    event = _event(kickoff=KICKOFF + timedelta(seconds=1))
    assert aliases.match_event(event, (row,)) == ()


@pytest.mark.parametrize(
    ("competition", "fotmob", "sportybet"),
    (
        ("Major League Soccer", "Red Bull New York", "New York Red Bulls"),
        ("K-League 1", "Gimcheon Sangmu", "Gimcheon Sangmu FC"),
        ("NWSL", "San Diego Wave FC (W)", "San Diego Wave FC"),
        ("NWSL", "Kansas City Current (W)", "Kansas City Current"),
        ("Liga 1", "Asociación Deportiva Tarma", "Asociacion Deportiva Tarma"),
        ("Primera Division Apertura", "Municipal Pérez Zeledón", "Perez Zeledon"),
    ),
)
def test_run_35404223536_aliases_are_exact_and_competition_scoped(competition, fotmob, sportybet):
    assert aliases.team_identity_matches(
        competition=competition, fotmob_name=fotmob, sportybet_name=sportybet
    )
    assert not aliases.team_identity_matches(
        competition="Unrelated", fotmob_name=fotmob, sportybet_name=sportybet
    )


def test_run_35404223536_aliases_do_not_create_generic_normalization():
    assert not aliases.team_identity_matches(
        competition="NWSL", fotmob_name="Example (W)", sportybet_name="Example"
    )
    assert not aliases.team_identity_matches(
        competition="Liga 1", fotmob_name="Asociación Example", sportybet_name="Asociacion Example"
    )
    assert not aliases.team_identity_matches(
        competition="Major League Soccer", fotmob_name="Bull Red New York", sportybet_name="New York Red Bulls"
    )


def test_registry_validation_rejects_ambiguous_source_mapping():
    rows = tuple(sorted((
        aliases.TeamAlias("League One", "A", "B"),
        aliases.TeamAlias("League One", "A", "C"),
    )))
    with pytest.raises(RuntimeError, match="ambiguous FotMob"):
        aliases._validate_registry(rows)


def test_registry_validation_rejects_ambiguous_provider_mapping():
    rows = tuple(sorted((
        aliases.TeamAlias("League One", "A", "C"),
        aliases.TeamAlias("League One", "B", "C"),
    )))
    with pytest.raises(RuntimeError, match="ambiguous SportyBet"):
        aliases._validate_registry(rows)
