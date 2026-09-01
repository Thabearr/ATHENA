"""Reviewed Shadow-only FotMob -> SportyBet fixture team identity aliases.

This registry exists only to bridge literal current-source display-name drift that
has been observed in retained ATHENA evidence.  It is deliberately not a fuzzy
matcher.  A fixture may use an alias only when all of the following remain exact:

* competition name;
* full UTC kickoff instant;
* home/away orientation; and
* both team identities, where each side is either literal-equal or an explicit
  competition-scoped pair below.

No suffix stripping, token similarity, substring matching, reversal, spelling
normalization, time tolerance, caller aliases, or inferred equivalence is allowed.
The registry grants fixture-reconciliation authority only inside the research
Shadow reconciliation wrapper.  It grants no model, pricing, selection, BET,
wallet, staking, login, cookie, or wager authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_EXPLICIT_FIXTURE_TEAM_ALIAS_V1"
MATCHING_BASIS = (
    "EXACT_COMPETITION_FULL_UTC_HOME_AWAY_ORIENTATION_"
    "LITERAL_OR_EXPLICIT_COMPETITION_SCOPED_TEAM_ALIAS_"
    "NO_FUZZY_NO_SUBSTRING_NO_SUFFIX_RULE_NO_REVERSAL_NO_TIME_TOLERANCE"
)
EVIDENCE_BASIS = "CURRENT_SHADOW_RUN34_RETAINED_FOTMOB_AND_SPORTYBET_SOURCE_EVIDENCE"


@dataclass(frozen=True, order=True)
class TeamAlias:
    competition: str
    fotmob_name: str
    sportybet_name: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.competition, "competition"),
            (self.fotmob_name, "fotmob_name"),
            (self.sportybet_name, "sportybet_name"),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"{label} must be exact non-empty trimmed text")
        if self.fotmob_name == self.sportybet_name:
            raise ValueError("literal-equal names do not belong in the alias registry")


# Every pair below was observed together at the same exact competition/kickoff in
# the retained run #34 current source/provider evidence.  Do not add convenient
# football synonyms here without equivalent retained evidence.
TEAM_ALIASES: tuple[TeamAlias, ...] = tuple(sorted((
    # EFL Championship
    TeamAlias("Championship", "Lincoln", "Lincoln City"),
    TeamAlias("Championship", "Blackburn", "Blackburn Rovers"),
    TeamAlias("Championship", "Portsmouth", "Portsmouth FC"),
    TeamAlias("Championship", "Derby", "Derby County"),
    TeamAlias("Championship", "Preston", "Preston North End"),
    TeamAlias("Championship", "Sheff Utd", "Sheffield United"),
    TeamAlias("Championship", "Bolton", "Bolton Wanderers"),
    TeamAlias("Championship", "Swansea", "Swansea City"),
    TeamAlias("Championship", "Birmingham", "Birmingham City"),
    TeamAlias("Championship", "Stoke", "Stoke City"),

    # EFL League One
    TeamAlias("League One", "Bradford", "Bradford City FC"),
    TeamAlias("League One", "Cambridge", "Cambridge United"),
    TeamAlias("League One", "Bromley", "Bromley FC"),
    TeamAlias("League One", "Leyton Orient", "Leyton Orient London"),
    TeamAlias("League One", "Doncaster", "Doncaster Rovers"),
    TeamAlias("League One", "Oxford Utd", "Oxford United"),
    TeamAlias("League One", "Plymouth", "Plymouth Argyle"),
    TeamAlias("League One", "Peterborough", "Peterborough United"),
    TeamAlias("League One", "Stevenage", "Stevenage FC"),
    TeamAlias("League One", "Wycombe", "Wycombe Wanderers"),
    TeamAlias("League One", "Sheff Wed", "Sheffield Wednesday"),

    # EFL League Two
    TeamAlias("League Two", "Accrington", "Accrington Stanley"),
    TeamAlias("League Two", "Grimsby", "Grimsby Town"),
    TeamAlias("League Two", "Colchester", "Colchester United"),
    TeamAlias("League Two", "Cheltenham", "Cheltenham Town"),
    TeamAlias("League Two", "York City", "York City FC"),
    TeamAlias("League Two", "Chesterfield", "Chesterfield FC"),
    TeamAlias("League Two", "Gillingham", "Gillingham FC"),
    TeamAlias("League Two", "Crewe", "Crewe Alexandra"),
    TeamAlias("League Two", "Walsall", "Walsall FC"),
    TeamAlias("League Two", "Exeter", "Exeter City"),
    TeamAlias("League Two", "Barnet", "Barnet FC"),
    TeamAlias("League Two", "Fleetwood", "Fleetwood Town"),
    TeamAlias("League Two", "Oldham", "Oldham Athletic"),
    TeamAlias("League Two", "Northampton", "Northampton Town"),
    TeamAlias("League Two", "Crawley", "Crawley Town"),
    TeamAlias("League Two", "Rochdale", "Rochdale AFC"),
    TeamAlias("League Two", "Shrewsbury", "Shrewsbury Town"),
    TeamAlias("League Two", "Salford", "Salford City"),
    TeamAlias("League Two", "Newport", "Newport County"),

    # Existing reviewed top-flight identities that also drifted in run #34
    TeamAlias("Saudi Pro League", "Al Hilal", "Al Hilal SFC"),
    TeamAlias("Saudi Pro League", "Al Ahli", "Al Ahli Saudi FC"),
    TeamAlias("Super League", "FC Zürich", "FC Zurich"),
    TeamAlias("Super League", "Young Boys", "Young Boys Bern"),
)))


def _validate_registry(rows: Sequence[TeamAlias]) -> None:
    if type(rows) is not tuple or not rows:
        raise RuntimeError("Shadow fixture alias registry must be a non-empty tuple")
    if tuple(sorted(rows)) != tuple(rows):
        raise RuntimeError("Shadow fixture alias registry must be deterministically sorted")
    if len(rows) != len(set(rows)):
        raise RuntimeError("Shadow fixture alias registry contains duplicate rows")

    source_seen: dict[tuple[str, str], str] = {}
    provider_seen: dict[tuple[str, str], str] = {}
    for row in rows:
        if type(row) is not TeamAlias:
            raise RuntimeError("Shadow fixture alias registry row type drifted")
        source_key = (row.competition, row.fotmob_name)
        provider_key = (row.competition, row.sportybet_name)
        previous_provider = source_seen.get(source_key)
        if previous_provider is not None and previous_provider != row.sportybet_name:
            raise RuntimeError("ambiguous FotMob team alias in one competition")
        previous_source = provider_seen.get(provider_key)
        if previous_source is not None and previous_source != row.fotmob_name:
            raise RuntimeError("ambiguous SportyBet team alias in one competition")
        source_seen[source_key] = row.sportybet_name
        provider_seen[provider_key] = row.fotmob_name


_validate_registry(TEAM_ALIASES)

_ALIAS_LOOKUP: Mapping[tuple[str, str], str] = MappingProxyType(
    {(row.competition, row.fotmob_name): row.sportybet_name for row in TEAM_ALIASES}
)


def registry_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "matching_basis": MATCHING_BASIS,
        "evidence_basis": EVIDENCE_BASIS,
        "aliases": [
            {
                "competition": row.competition,
                "fotmob_name": row.fotmob_name,
                "sportybet_name": row.sportybet_name,
            }
            for row in TEAM_ALIASES
        ],
        "authority": {
            "research_shadow_fixture_reconciliation": True,
            "production_model": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "staking": False,
            "bet": False,
            "wager_placed": False,
        },
    }


def registry_sha256() -> str:
    raw = json.dumps(
        registry_payload(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def team_identity_matches(
    *, competition: str, fotmob_name: str, sportybet_name: str
) -> bool:
    if type(competition) is not str or type(fotmob_name) is not str or type(sportybet_name) is not str:
        return False
    if fotmob_name == sportybet_name:
        return True
    return _ALIAS_LOOKUP.get((competition, fotmob_name)) == sportybet_name


def match_event(event: Any, reviewed_rows: Sequence[Any]) -> tuple[Any, ...]:
    """Return only exact or explicitly aliased unique-candidate inputs.

    The caller retains the existing ambiguity and direct provider-detail checks;
    this helper only changes the literal team-display-name equality boundary.
    """

    competition = getattr(event, "competition_name", None)
    kickoff = getattr(event, "kickoff_utc", None)
    provider_home = getattr(event, "home_team_name", None)
    provider_away = getattr(event, "away_team_name", None)
    if (
        type(competition) is not str
        or kickoff is None
        or type(provider_home) is not str
        or type(provider_away) is not str
    ):
        return ()

    matches: list[Any] = []
    for item in reviewed_rows:
        if getattr(item, "competition", None) != competition:
            continue
        source_kickoff = getattr(item, "kickoff", None)
        if source_kickoff is None or source_kickoff.tzinfo is None or source_kickoff.utcoffset() is None:
            continue
        if source_kickoff.astimezone(timezone.utc) != kickoff:
            continue
        source_home = getattr(item, "home_team", None)
        source_away = getattr(item, "away_team", None)
        if not team_identity_matches(
            competition=competition,
            fotmob_name=source_home,
            sportybet_name=provider_home,
        ):
            continue
        if not team_identity_matches(
            competition=competition,
            fotmob_name=source_away,
            sportybet_name=provider_away,
        ):
            continue
        matches.append(item)
    return tuple(matches)


REGISTRY_SHA256 = registry_sha256()


__all__ = [
    "EVIDENCE_BASIS",
    "MATCHING_BASIS",
    "POLICY_ID",
    "REGISTRY_SHA256",
    "SCHEMA_VERSION",
    "TEAM_ALIASES",
    "TeamAlias",
    "match_event",
    "registry_payload",
    "registry_sha256",
    "team_identity_matches",
]
