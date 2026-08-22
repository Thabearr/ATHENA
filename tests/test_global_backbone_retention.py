from scripts.import_global_football_backbone import classify, classify_for_import


def test_non_hierarchy_global_top_flight_is_retained_in_catch_all():
    brazil = {
        "competition": "Brazil",
        "level": "national",
        "continent": "South America",
    }
    assert classify(brazil) is None
    assert classify_for_import(brazil) == ("club", "other_global_topflight")


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


def test_unknown_non_national_row_is_not_promoted_to_global_top_flight():
    unknown = {
        "competition": "Example",
        "level": "regional",
        "continent": "Asia",
    }
    assert classify_for_import(unknown) is None
