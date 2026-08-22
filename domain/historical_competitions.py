"""Athena competition hierarchy and historical source registry.

Ranks are intentionally independent between club and international scopes.
Lower rank = higher priority inside that scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class Competition:
    key: str
    name: str
    scope: str
    country: Optional[str]
    confederation: Optional[str]
    competition_type: str
    rank: int
    tier: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalSource:
    key: str
    name: str
    homepage: str
    license_name: str
    attribution: str
    redistributable: bool
    priority: int
    notes: str = ""


CLUB_COMPETITIONS: tuple[Competition, ...] = (
    Competition("uefa_ucl", "UEFA Champions League", "club", None, "UEFA", "continental_cup", 10, "A1", ("Champions League", "European Cup")),
    Competition("uefa_uel", "UEFA Europa League", "club", None, "UEFA", "continental_cup", 20, "A1", ("Europa League", "UEFA Cup")),
    Competition("uefa_uecl", "UEFA Conference League", "club", None, "UEFA", "continental_cup", 30, "A1", ("Conference League",)),
    Competition("eng_premier", "Premier League", "club", "England", "UEFA", "league", 40, "A2", ("English Premier League", "EPL", "E0")),
    Competition("esp_laliga", "La Liga", "club", "Spain", "UEFA", "league", 50, "A2", ("Primera Division", "LaLiga", "SP1")),
    Competition("ita_serie_a", "Serie A", "club", "Italy", "UEFA", "league", 60, "A2", ("I1",)),
    Competition("ger_bundesliga", "Bundesliga", "club", "Germany", "UEFA", "league", 70, "A2", ("1. Bundesliga", "D1")),
    Competition("fra_ligue1", "Ligue 1", "club", "France", "UEFA", "league", 80, "A2", ("F1",)),
    Competition("eng_fa_cup", "FA Cup", "club", "England", "UEFA", "domestic_cup", 90, "B1", ("F.A. Cup",)),
    Competition("eng_efl_cup", "EFL Cup", "club", "England", "UEFA", "domestic_cup", 91, "B1", ("League Cup", "Carabao Cup")),
    Competition("esp_copa_del_rey", "Copa del Rey", "club", "Spain", "UEFA", "domestic_cup", 92, "B1"),
    Competition("ita_coppa_italia", "Coppa Italia", "club", "Italy", "UEFA", "domestic_cup", 93, "B1"),
    Competition("ger_dfb_pokal", "DFB-Pokal", "club", "Germany", "UEFA", "domestic_cup", 94, "B1", ("DFB Pokal",)),
    Competition("fra_coupe_de_france", "Coupe de France", "club", "France", "UEFA", "domestic_cup", 95, "B1"),
    Competition("ned_eredivisie", "Eredivisie", "club", "Netherlands", "UEFA", "league", 100, "B2", ("N1",)),
    Competition("por_primeira", "Primeira Liga", "club", "Portugal", "UEFA", "league", 110, "B2", ("Liga Portugal", "P1")),
    Competition("tur_superlig", "Süper Lig", "club", "Turkey", "UEFA", "league", 120, "B2", ("Super Lig", "T1")),
    Competition("bel_proleague", "Belgian Pro League", "club", "Belgium", "UEFA", "league", 130, "B2", ("First Division A", "Jupiler Pro League", "B1")),
    Competition("nor_eliteserien", "Eliteserien", "club", "Norway", "UEFA", "league", 140, "B3"),
    Competition("den_superliga", "Danish Superliga", "club", "Denmark", "UEFA", "league", 150, "B3"),
    Competition("swe_allsvenskan", "Allsvenskan", "club", "Sweden", "UEFA", "league", 160, "B3"),
    Competition("sui_superleague", "Swiss Super League", "club", "Switzerland", "UEFA", "league", 170, "B3"),
    Competition("gre_superleague", "Super League Greece", "club", "Greece", "UEFA", "league", 180, "B3", ("Greek Super League", "G1")),
    Competition("eng_championship", "EFL Championship", "club", "England", "UEFA", "league", 190, "C1", ("Championship", "E1")),
    Competition("sau_proleague", "Saudi Pro League", "club", "Saudi Arabia", "AFC", "league", 200, "C2", ("Saudi League", "Roshn Saudi League")),
    Competition("usa_mls", "Major League Soccer", "club", "United States", "CONCACAF", "league", 210, "C2", ("MLS",)),
    Competition("other_euro_topflight", "Other European Top Flights", "club", None, "UEFA", "league", 220, "C3"),
)


INTERNATIONAL_COMPETITIONS: tuple[Competition, ...] = (
    Competition("intl_world_cup", "FIFA World Cup", "international", None, "FIFA", "tournament", 10, "I1", ("FIFA World Cup", "World Cup")),
    Competition("intl_euro", "UEFA European Championship", "international", None, "UEFA", "tournament", 20, "I1", ("UEFA Euro", "European Championship")),
    Competition("intl_copa_america", "Copa América", "international", None, "CONMEBOL", "tournament", 30, "I1", ("Copa America",)),
    Competition("intl_afcon", "Africa Cup of Nations", "international", None, "CAF", "tournament", 40, "I1", ("African Cup of Nations", "AFCON")),
    Competition("intl_asian_cup", "AFC Asian Cup", "international", None, "AFC", "tournament", 50, "I2"),
    Competition("intl_gold_cup", "CONCACAF Gold Cup", "international", None, "CONCACAF", "tournament", 60, "I2", ("Gold Cup",)),
    Competition("intl_world_cup_qual", "FIFA World Cup qualification", "international", None, "FIFA", "qualifier", 70, "I2", ("FIFA World Cup qualification", "World Cup qualification")),
    Competition("intl_continental_qual", "Continental Championship Qualification", "international", None, None, "qualifier", 80, "I3", ("UEFA Euro qualification", "Africa Cup of Nations qualification", "AFC Asian Cup qualification")),
    Competition("intl_nations_league", "Nations League", "international", None, None, "tournament", 90, "I3", ("UEFA Nations League", "CONCACAF Nations League")),
    Competition("intl_friendly", "International Friendly", "international", None, "FIFA", "friendly", 100, "I4", ("Friendly", "Friendlies")),
    Competition("intl_other", "Other Senior International", "international", None, None, "tournament", 110, "I4"),
)


SOURCES: tuple[HistoricalSource, ...] = (
    HistoricalSource(
        "martj42_international",
        "martj42 international_results",
        "https://github.com/martj42/international_results",
        "CC0-1.0",
        "martj42/international_results",
        True,
        20,
        "Senior international results from 1872 plus goalscorers and shootouts; no complete card/coach coverage.",
    ),
    HistoricalSource(
        "fjelstul_worldcup",
        "Fjelstul World Cup Database",
        "https://github.com/jfjelstul/worldcup",
        "CC BY-SA 4.0",
        "Joshua C. Fjelstul, The Fjelstul World Cup Database",
        True,
        10,
        "World Cup-specific enrichment: goals, bookings, managers, players, substitutions, referees and venues.",
    ),
    HistoricalSource(
        "football_data_uk",
        "Football-Data.co.uk",
        "https://www.football-data.co.uk/",
        "Source terms",
        "Football-Data.co.uk",
        False,
        30,
        "Local-cache only. Strong league coverage since 1993/94 with HT/FT, cards, shots, corners, referees and odds where available.",
    ),
    HistoricalSource(
        "statsbomb_open",
        "StatsBomb Open Data",
        "https://github.com/hudl/open-data",
        "StatsBomb Open Data terms",
        "StatsBomb",
        False,
        5,
        "Selected competitions/seasons only; event and lineup detail is extremely rich. Attribution required.",
    ),
    HistoricalSource(
        "openfootball",
        "OpenFootball",
        "https://github.com/openfootball",
        "CC0-1.0",
        "OpenFootball / football.db",
        True,
        40,
        "Public-domain league/cup/UEFA result backfill; detail varies by season and competition.",
    ),
)


ALL_COMPETITIONS = CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS


def iter_competitions() -> Iterable[Competition]:
    return iter(ALL_COMPETITIONS)


def _norm(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def resolve_competition(name: str, scope: Optional[str] = None) -> Competition:
    normalized = _norm(name)
    candidates = [c for c in ALL_COMPETITIONS if scope is None or c.scope == scope]

    for competition in candidates:
        names = (competition.name, competition.key, *competition.aliases)
        if normalized in {_norm(item) for item in names}:
            return competition

    if scope == "international":
        searchable = []
        for competition in INTERNATIONAL_COMPETITIONS:
            for alias in (competition.name, *competition.aliases):
                searchable.append((_norm(alias), competition))
        for alias, competition in sorted(searchable, key=lambda item: len(item[0]), reverse=True):
            if alias and alias in normalized:
                return competition
        return next(c for c in INTERNATIONAL_COMPETITIONS if c.key == "intl_other")

    return Competition(
        key="other_club_competition",
        name=name.strip() or "Unknown Club Competition",
        scope="club",
        country=None,
        confederation=None,
        competition_type="unknown",
        rank=999,
        tier="Z",
    )


FOOTBALL_DATA_CODES = {
    "E0": "eng_premier",
    "E1": "eng_championship",
    "SP1": "esp_laliga",
    "I1": "ita_serie_a",
    "D1": "ger_bundesliga",
    "F1": "fra_ligue1",
    "N1": "ned_eredivisie",
    "P1": "por_primeira",
    "T1": "tur_superlig",
    "B1": "bel_proleague",
    "G1": "gre_superleague",
}


def competition_by_key(key: str) -> Optional[Competition]:
    return next((c for c in ALL_COMPETITIONS if c.key == key), None)
