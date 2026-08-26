from scripts.import_openfootball_history import (
    competition_from_title,
    parse_openfootball_text,
)


def _key(title: str) -> str | None:
    competition = competition_from_title(title)
    return competition.key if competition is not None else None


def test_reviewed_uefa_ucl_titles_remain_authorized() -> None:
    assert _key("UEFA Champions League 2025/26") == "uefa_ucl"
    assert _key("European Cup 1987/88") == "uefa_ucl"


def test_non_uefa_or_ambiguous_champions_league_titles_fail_closed() -> None:
    for title in (
        "Champions League 1999/2000",
        "CAF Champions League 2024/25",
        "CONCACAF Champions League 2025",
        "AFC Champions League 2023/24",
        "AFC Champions League Elite 2024/25",
        "OFC Champions League 2025",
        "Arab Club Champions League 2025",
        "UEFA Women's Champions League 2025/26",
        "European Cup Winners' Cup 1990/91",
    ):
        assert _key(title) is None, title


def test_rejected_non_uefa_source_cannot_emit_uefa_rows() -> None:
    caf = """= CAF Champions League 2024/25

▪ Group A
  Sat Nov 30 2024
    18:00  Example FC (EGY) v Sample FC (MAR)  2-1 (1-0)
"""
    concacaf = """= CONCACAF Champions League 2025

▪ Round 1
  Wed Feb 5 2025
    20:00  Example FC (MEX) v Sample FC (USA)  1-0 (0-0)
"""

    assert list(
        parse_openfootball_text(
            caf,
            "world-master/africa/champions-league/2024-25_cafcl.txt",
        )
    ) == []
    assert list(
        parse_openfootball_text(
            concacaf,
            "world-master/north-america/champions-league/2025_concacafcl.txt",
        )
    ) == []


def test_uefa_ucl_and_sibling_uefa_competitions_still_parse() -> None:
    ucl = """= UEFA Champions League 2025/26

▪ League, Matchday 1
  Tue Sep 16 2025
    18:45  Athletic Club (ESP) v Arsenal FC (ENG)  0-2 (0-0)
"""
    uel = """= UEFA Europa League 2025/26

▪ League phase
  Thu Sep 25 2025
    18:45  Example FC (POR) v Sample FC (NED)  1-1 (1-0)
"""
    uecl = """= UEFA Conference League 2025/26

▪ League phase
  Thu Oct 2 2025
    18:45  Example FC (SUI) v Sample FC (BEL)  2-0 (1-0)
"""

    ucl_rows = list(parse_openfootball_text(ucl, "champions-league-master/2025-26/cl.txt"))
    uel_rows = list(parse_openfootball_text(uel, "champions-league-master/2025-26/el.txt"))
    uecl_rows = list(parse_openfootball_text(uecl, "champions-league-master/2025-26/conf.txt"))

    assert [row["competition_key"] for row in ucl_rows] == ["uefa_ucl"]
    assert [row["competition_key"] for row in uel_rows] == ["uefa_uel"]
    assert [row["competition_key"] for row in uecl_rows] == ["uefa_uecl"]
