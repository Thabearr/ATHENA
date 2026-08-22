from scripts.import_global_football_backbone import (
    backbone_match_key,
    classify,
    classify_for_import,
    season_for_import,
)


def test_non_hierarchy_global_top_flight_is_retained_in_catch_all():
    brazil = {
        "competition": "Brazil",
        "level": "national",
        "continent": "South America",
    }
    assert classify(brazil) is None
    assert classify_for_import(brazil) == ("club", "other_global_topflight")
    assert season_for_import("2023-05-10", "club", "other_global_topflight") is None


def test_named_hierarchy_and_european_catch_all_remain_distinct():
    scotland = {
        "competition": "Scotland",
        "level": "national",
        "continent": "Europe",
    }
    austria = {
        "competition": "Austria",
        "level": "national",
        "continent": "Europe",
    }
    assert classify_for_import(scotland) == ("club", "sco_premiership")
    assert classify_for_import(austria) == ("club", "other_euro_topflight")
    assert season_for_import("2023-09-10", "club", "sco_premiership") == "2023-24"
    assert season_for_import("2023-09-10", "club", "other_euro_topflight") is None


def test_catch_all_fixture_key_includes_source_competition_identity():
    match = {
        "competition_key": "other_global_topflight",
        "competition_name": "Brazil",
        "scope": "club",
        "match_date": "2023-05-10",
        "home_team": "United",
        "away_team": "City",
    }
    brazil_key = backbone_match_key(match, "Brazil")
    japan_key = backbone_match_key({**match, "competition_name": "Japan"}, "Japan")
    assert brazil_key != japan_key


def test_unknown_non_national_row_is_not_promoted_to_global_top_flight():
    unknown = {
        "competition": "Example",
        "level": "regional",
        "continent": "Asia",
    }
    assert classify_for_import(unknown) is None
