from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from domain import current_shadow_fixture_identity_v2 as identity


UTC = timezone.utc
KICKOFF = datetime(2026, 9, 2, 18, 45, tzinfo=UTC)


def _reviewed(fid: str, *, home: str, away: str, competition: str = "Championship"):
    return SimpleNamespace(
        source_fixture_identifier=fid,
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff=KICKOFF,
    )


def _source(
    fid: str,
    *,
    home_id: int,
    home_short: str,
    home_long: str,
    away_id: int,
    away_short: str,
    away_long: str,
    competition: str = "Championship",
):
    return identity.SourceFixtureIdentity(
        source_fixture_identifier=fid,
        competition=competition,
        kickoff_utc=KICKOFF,
        home_team_id=home_id,
        home_short_name=home_short,
        home_long_name=home_long,
        away_team_id=away_id,
        away_short_name=away_short,
        away_long_name=away_long,
    )


def _event(
    event_id: str = "sr:match:72339764",
    *,
    home: str,
    away: str,
    competition: str = "Championship",
):
    return SimpleNamespace(
        event_id=event_id,
        home_team_name=home,
        away_team_name=away,
        competition_name=competition,
        kickoff_utc=KICKOFF,
    )


def test_registry_and_matching_policy_are_pinned() -> None:
    assert identity.POLICY_ID == "ATHENA_CURRENT_SHADOW_EXACT_FIXTURE_IDENTITY_V2"
    assert identity.REGISTRY_SHA256 == "c18565c9404cb45536d8d52c07ec8e511a437f6eae5590e7cf656940f9ec5e6a"
    assert "NO_FUZZY" in identity.MATCHING_BASIS
    assert "NO_SUBSTRING" in identity.MATCHING_BASIS
    assert "NO_SUFFIX_RULE" in identity.MATCHING_BASIS
    assert "NO_REVERSAL" in identity.MATCHING_BASIS
    assert "NO_TIME_TOLERANCE" in identity.MATCHING_BASIS


def test_competition_display_drift_is_explicit_not_fuzzy() -> None:
    assert identity.competition_identity_matches("Belgian Pro League", "Pro League")
    assert identity.competition_identity_matches("Superligaen", "Superliga")
    assert identity.competition_identity_matches("Championship", "Championship")
    assert not identity.competition_identity_matches("League One", "Championship")
    assert not identity.competition_identity_matches("Superligaen", "Super League")


def test_stable_team_ids_survive_future_display_name_drift() -> None:
    reviewed = _reviewed("5836800", home="QPR", away="Cardiff")
    source = _source(
        "5836800",
        home_id=10172,
        home_short="QPR",
        home_long="Queens Park Rangers",
        away_id=8344,
        away_short="Cardiff",
        away_long="Cardiff City",
    )
    provider = identity.ProviderTeamIdentity(
        "sr:match:72339764", "sr:competitor:1", "sr:competitor:61"
    )
    event = _event(home="Provider Renamed Home", away="Provider Renamed Away")
    with identity.identity_rows_context(source_rows=(source,), provider_rows=(provider,)):
        assert identity.match_event(event, (reviewed,)) == (reviewed,)


def test_known_cross_source_id_conflict_blocks_even_matching_text() -> None:
    reviewed = _reviewed("5836800", home="QPR", away="Cardiff")
    source = _source(
        "5836800",
        home_id=10172,
        home_short="QPR",
        home_long="Queens Park Rangers",
        away_id=8344,
        away_short="Cardiff",
        away_long="Cardiff City",
    )
    provider = identity.ProviderTeamIdentity(
        "sr:match:72339764", "sr:competitor:61", "sr:competitor:1"
    )
    event = _event(home="QPR", away="Cardiff")
    with identity.identity_rows_context(source_rows=(source,), provider_rows=(provider,)):
        assert identity.match_event(event, (reviewed,)) == ()


def test_fotmob_long_names_resolve_qpr_and_cardiff_without_alias_growth() -> None:
    reviewed = _reviewed("5836800", home="QPR", away="Cardiff")
    source = _source(
        "5836800",
        home_id=999001,
        home_short="QPR",
        home_long="Queens Park Rangers",
        away_id=999002,
        away_short="Cardiff",
        away_long="Cardiff City",
    )
    event = _event(home="Queens Park Rangers", away="Cardiff City")
    with identity.identity_rows_context(source_rows=(source,), provider_rows=()):
        assert identity.match_event(event, (reviewed,)) == (reviewed,)


def test_unique_one_side_exact_anchor_resolves_counterpart_without_fuzzy_text() -> None:
    reviewed_target = _reviewed(
        "6003658", home="Udinese", away="Venezia", competition="Coppa Italia"
    )
    reviewed_other = _reviewed(
        "6003999", home="Torino", away="Como", competition="Coppa Italia"
    )
    target = _source(
        "6003658",
        home_id=900001,
        home_short="Udinese",
        home_long="Udinese",
        away_id=900002,
        away_short="Venezia",
        away_long="Venezia",
        competition="Coppa Italia",
    )
    other = _source(
        "6003999",
        home_id=900003,
        home_short="Torino",
        home_long="Torino",
        away_id=900004,
        away_short="Como",
        away_long="Como",
        competition="Coppa Italia",
    )
    event = _event(
        event_id="sr:match:73786056",
        home="Udinese",
        away="Venezia FC",
        competition="Coppa Italia",
    )
    with identity.identity_rows_context(source_rows=(target, other), provider_rows=()):
        assert identity.match_event(event, (reviewed_target, reviewed_other)) == (
            reviewed_target,
        )


def test_no_zero_anchor_unique_bucket_guessing() -> None:
    reviewed = _reviewed(
        "5804251", home="Grasshopper", away="St. Gallen", competition="Super League"
    )
    source = _source(
        "5804251",
        home_id=900011,
        home_short="Grasshopper",
        home_long="Grasshopper",
        away_id=900012,
        away_short="St. Gallen",
        away_long="St. Gallen",
        competition="Super League",
    )
    event = _event(
        event_id="sr:match:72176918",
        home="Totally Different Home",
        away="Totally Different Away",
        competition="Super League",
    )
    with identity.identity_rows_context(source_rows=(source,), provider_rows=()):
        assert identity.match_event(event, (reviewed,)) == ()


def test_retained_ids_resolve_grasshopper_double_name_drift_without_text_rules() -> None:
    reviewed = _reviewed(
        "5804251", home="Grasshopper", away="St. Gallen", competition="Super League"
    )
    source = _source(
        "5804251",
        home_id=9956,
        home_short="Grasshopper",
        home_long="Grasshopper",
        away_id=10190,
        away_short="St. Gallen",
        away_long="St. Gallen",
        competition="Super League",
    )
    provider = identity.ProviderTeamIdentity(
        "sr:match:72176918", "sr:competitor:2449", "sr:competitor:2442"
    )
    event = _event(
        event_id="sr:match:72176918",
        home="Future Grasshopper Label",
        away="Future St Gallen Label",
        competition="Super League",
    )
    with identity.identity_rows_context(source_rows=(source,), provider_rows=(provider,)):
        assert identity.match_event(event, (reviewed,)) == (reviewed,)


def test_competition_alias_and_ids_resolve_superligaen_provider_superliga() -> None:
    reviewed = _reviewed(
        "5739497", home="AGF", away="FC Midtjylland", competition="Superligaen"
    )
    source = _source(
        "5739497",
        home_id=8071,
        home_short="AGF",
        home_long="AGF",
        away_id=8113,
        away_short="FC Midtjylland",
        away_long="FC Midtjylland",
        competition="Superligaen",
    )
    provider = identity.ProviderTeamIdentity(
        "sr:match:71924960", "sr:competitor:1291", "sr:competitor:1289"
    )
    event = _event(
        event_id="sr:match:71924960",
        home="AGF Aarhus",
        away="FC Midtjylland",
        competition="Superliga",
    )
    with identity.identity_rows_context(source_rows=(source,), provider_rows=(provider,)):
        assert identity.match_event(event, (reviewed,)) == (reviewed,)


def test_reversal_is_never_authorized_by_stable_ids() -> None:
    reviewed = _reviewed("5836800", home="QPR", away="Cardiff")
    source = _source(
        "5836800",
        home_id=10172,
        home_short="QPR",
        home_long="Queens Park Rangers",
        away_id=8344,
        away_short="Cardiff",
        away_long="Cardiff City",
    )
    provider = identity.ProviderTeamIdentity(
        "sr:match:72339764", "sr:competitor:61", "sr:competitor:1"
    )
    event = _event(home="Cardiff City", away="Queens Park Rangers")
    with identity.identity_rows_context(source_rows=(source,), provider_rows=(provider,)):
        assert identity.match_event(event, (reviewed,)) == ()


def test_multiple_one_side_anchors_remain_ambiguous() -> None:
    a = _reviewed("1", home="Shared", away="Away A")
    b = _reviewed("2", home="Shared", away="Away B")
    sa = _source(
        "1",
        home_id=900101,
        home_short="Shared",
        home_long="Shared",
        away_id=900102,
        away_short="Away A",
        away_long="Away A",
    )
    sb = _source(
        "2",
        home_id=900103,
        home_short="Shared",
        home_long="Shared",
        away_id=900104,
        away_short="Away B",
        away_long="Away B",
    )
    event = _event(home="Shared", away="Unknown")
    with identity.identity_rows_context(source_rows=(sa, sb), provider_rows=()):
        assert identity.match_event(event, (a, b)) == (a, b)
