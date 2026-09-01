"""Evidence-backed current Shadow fixture identity V2.

This boundary prevents harmless provider display-name changes from collapsing
otherwise exact current fixture reconciliation.  It remains research/Shadow only.
No fuzzy text similarity, suffix stripping, substring inference, reversal, kickoff
rounding/tolerance, or guessed equivalence can grant fixture authority.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Sequence

from domain import current_shadow_fixture_identity_aliases as legacy_aliases
from domain import fotmob_fixture_candidates

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_EXACT_FIXTURE_IDENTITY_V2"
SOURCE_REPLAY_POLICY_ID = "RAW_FOTMOB_TEAM_IDS_SHORT_LONG_NAMES_REPLAY_V1"
PROVIDER_ID_POLICY_ID = "VERIFIED_FANOUT_RAW_HOME_AWAY_COMPETITOR_IDS_V1"
MATCHING_BASIS = (
    "EXACT_REVIEWED_COMPETITION_EQUIVALENCE_FULL_UTC_HOME_AWAY_ORIENTATION_"
    "EVIDENCE_BOUND_TEAM_IDS_OR_EXACT_SHORT_LONG_OR_EXPLICIT_ALIAS_OR_"
    "UNIQUE_ONE_SIDE_EXACT_ANCHOR_NO_FUZZY_NO_SUBSTRING_NO_SUFFIX_RULE_"
    "NO_REVERSAL_NO_ROUNDING_NO_TIME_TOLERANCE"
)
RUN34_EVIDENCE = (
    "ATHENA_RUN34_ARTIFACT_SHA256_"
    "1f3610d5bb05838b6840ce1e5d4f3771a5176289b3ed117ea38f1d1eddb33803"
)
RUN38_EVIDENCE = (
    "ATHENA_RUN38_ARTIFACT_SHA256_"
    "3ff8371b67cf4b197cdf03b5215dfd52ad45ecbfa6a65f12d7dc00a1169420f8"
)
_COMPETITOR_RE = re.compile(r"^sr:competitor:[1-9][0-9]*$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


@dataclass(frozen=True, order=True)
class CompetitionAlias:
    fotmob_name: str
    sportybet_name: str
    evidence_basis: str


@dataclass(frozen=True, order=True)
class TeamIdBinding:
    fotmob_team_id: int
    sportybet_competitor_id: str
    fotmob_observed_name: str
    sportybet_observed_name: str
    evidence_basis: str


@dataclass(frozen=True)
class SourceFixtureIdentity:
    source_fixture_identifier: str
    competition: str
    kickoff_utc: datetime
    home_team_id: int
    home_short_name: str
    home_long_name: str
    away_team_id: int
    away_short_name: str
    away_long_name: str


@dataclass(frozen=True)
class ProviderTeamIdentity:
    event_id: str
    home_competitor_id: str
    away_competitor_id: str


@dataclass(frozen=True)
class IdentityContext:
    source_by_fixture: Mapping[str, SourceFixtureIdentity]
    provider_by_event: Mapping[str, ProviderTeamIdentity]


COMPETITION_ALIASES: tuple[CompetitionAlias, ...] = tuple(sorted((
    CompetitionAlias("Belgian Pro League", "Pro League", RUN38_EVIDENCE),
    CompetitionAlias("Superligaen", "Superliga", RUN38_EVIDENCE),
)))

# Exact retained run-38 source-team/provider-competitor evidence.  The IDs are the
# durable identity; observed names are provenance/audit labels only.
_TEAM_ROWS = (
    (1773, "sr:competitor:2918", "OH Leuven", "Oud-Heverlee Leuven"),
    (7730, "sr:competitor:2446", "Lausanne", "Lausanne-Sport"),
    (7881, "sr:competitor:2688", "Venezia", "Venezia FC"),
    (7896, "sr:competitor:2443", "Lugano", "Lugano"),
    (7943, "sr:competitor:2793", "Sassuolo", "Sassuolo"),
    (7978, "sr:competitor:4860", "Union St.Gilloise", "Union Gilloise"),
    (8071, "sr:competitor:1291", "AGF", "AGF Aarhus"),
    (8113, "sr:competitor:1289", "FC Midtjylland", "FC Midtjylland"),
    (8127, "sr:competitor:1783", "Mjällby", "Mjallby AIF"),
    (8283, "sr:competitor:23", "Barnsley", "Barnsley FC"),
    (8284, "sr:competitor:2357", "Dundee FC", "Dundee FC"),
    (8344, "sr:competitor:61", "Cardiff", "Cardiff City"),
    (8346, "sr:competitor:72", "Luton", "Luton"),
    (8391, "sr:competitor:1284", "FC København", "Copenhagen"),
    (8451, "sr:competitor:47", "Charlton", "Charlton Athletic"),
    (8467, "sr:competitor:2348", "St. Johnstone", "St. Johnstone FC"),
    (8483, "sr:competitor:67", "Blackpool", "Blackpool FC"),
    (8485, "sr:competitor:2355", "Aberdeen", "Aberdeen"),
    (8529, "sr:competitor:2719", "Cagliari", "Cagliari"),
    (8540, "sr:competitor:2715", "Palermo", "Palermo FC"),
    (8548, "sr:competitor:2351", "Rangers", "Rangers"),
    (8560, "sr:competitor:2824", "Real Sociedad", "Real Sociedad"),
    (8571, "sr:competitor:4858", "Kortrijk", "KV Kortrijk"),
    (8596, "sr:competitor:2363", "Falkirk", "Falkirk FC"),
    (8597, "sr:competitor:2347", "Kilmarnock", "Kilmarnock FC"),
    (8600, "sr:competitor:2695", "Udinese", "Udinese"),
    (8635, "sr:competitor:2900", "Anderlecht", "RSC Anderlecht"),
    (8639, "sr:competitor:1643", "Lille", "Lille"),
    (8659, "sr:competitor:8", "West Brom", "West Bromwich Albion"),
    (9775, "sr:competitor:2581", "VfL Osnabrück", "VfL 1899 Osnabruck"),
    (9777, "sr:competitor:2448", "Servette", "Servette Geneva"),
    (9792, "sr:competitor:134", "Burton", "Burton Albion"),
    (9800, "sr:competitor:2359", "St. Mirren", "St Mirren FC"),
    (9802, "sr:competitor:1759", "Djurgården", "Djurgardens IF"),
    (9823, "sr:competitor:2672", "Bayern München", "Bayern Munich"),
    (9824, "sr:competitor:2463", "FC Vaduz", "FC Vaduz"),
    (9860, "sr:competitor:2353", "Hearts", "Heart of Midlothian FC"),
    (9876, "sr:competitor:2701", "Hellas Verona", "Verona"),
    (9889, "sr:competitor:2770", "Mantova", "Mantova 1911"),
    (9891, "sr:competitor:2801", "Frosinone", "Frosinone"),
    (9910, "sr:competitor:2821", "Celta Vigo", "Celta"),
    (9925, "sr:competitor:2352", "Celtic", "Celtic"),
    (9927, "sr:competitor:2346", "Motherwell", "Motherwell FC"),
    (9931, "sr:competitor:2501", "Basel", "Basel"),
    (9938, "sr:competitor:2349", "Dundee United", "Dundee United"),
    (9941, "sr:competitor:1681", "Toulouse", "Toulouse"),
    (9956, "sr:competitor:2449", "Grasshopper", "Grasshopper Club Zurich"),
    (9991, "sr:competitor:2903", "Gent", "Gent"),
    (9997, "sr:competitor:2895", "St.Truiden", "St. Truidense VV"),
    (10007, "sr:competitor:10", "Stockport County", "Stockport County FC"),
    (10172, "sr:competitor:1", "QPR", "Queens Park Rangers"),
    (10179, "sr:competitor:2452", "Sion", "FC Sion"),
    (10190, "sr:competitor:2442", "St. Gallen", "FC St. Gallen 1879"),
    (10191, "sr:competitor:2454", "Thun", "FC Thun"),
    (10199, "sr:competitor:2453", "Luzern", "FC Luzern"),
    (10202, "sr:competitor:1292", "Nordsjælland", "Nordsjaelland"),
    (10251, "sr:competitor:2354", "Hibernian", "Hibernian FC"),
    (101919, "sr:competitor:56027", "Al Qadsiah", "Al Qadsiah"),
    (158319, "sr:competitor:23957", "Wimbledon", "AFC Wimbledon"),
    (550433, "sr:competitor:167228", "Al Khaleej", "Al-Khaleej Club"),
    (582749, "sr:competitor:168094", "Al-Fayha", "Al-Fayha FC"),
    (1523706, "sr:competitor:386360", "Al Kholood", "Al-Kholood"),
    (1699505, "sr:competitor:529781", "Neom SC", "Neom SC"),
    (1787233, "sr:competitor:168082", "Al Diriyah", "Diriyah Club"),
)
TEAM_ID_BINDINGS: tuple[TeamIdBinding, ...] = tuple(sorted(
    TeamIdBinding(source_id, provider_id, source_name, provider_name, RUN38_EVIDENCE)
    for source_id, provider_id, source_name, provider_name in _TEAM_ROWS
))


def _validate_registry() -> None:
    if tuple(sorted(COMPETITION_ALIASES)) != COMPETITION_ALIASES:
        raise RuntimeError("competition aliases must be deterministically sorted")
    if tuple(sorted(TEAM_ID_BINDINGS)) != TEAM_ID_BINDINGS:
        raise RuntimeError("team ID bindings must be deterministically sorted")
    source_seen: dict[int, str] = {}
    provider_seen: dict[str, int] = {}
    for row in TEAM_ID_BINDINGS:
        if type(row.fotmob_team_id) is not int or row.fotmob_team_id <= 0:
            raise RuntimeError("FotMob team ID binding is invalid")
        if _COMPETITOR_RE.fullmatch(row.sportybet_competitor_id) is None:
            raise RuntimeError("SportyBet competitor ID binding is invalid")
        if source_seen.get(row.fotmob_team_id, row.sportybet_competitor_id) != row.sportybet_competitor_id:
            raise RuntimeError("one FotMob team ID maps to multiple SportyBet competitors")
        if provider_seen.get(row.sportybet_competitor_id, row.fotmob_team_id) != row.fotmob_team_id:
            raise RuntimeError("one SportyBet competitor maps to multiple FotMob team IDs")
        source_seen[row.fotmob_team_id] = row.sportybet_competitor_id
        provider_seen[row.sportybet_competitor_id] = row.fotmob_team_id


_validate_registry()
_COMPETITION_LOOKUP = MappingProxyType(
    {row.fotmob_name: row.sportybet_name for row in COMPETITION_ALIASES}
)
_SOURCE_TO_PROVIDER = MappingProxyType(
    {row.fotmob_team_id: row.sportybet_competitor_id for row in TEAM_ID_BINDINGS}
)
_PROVIDER_TO_SOURCE = MappingProxyType(
    {row.sportybet_competitor_id: row.fotmob_team_id for row in TEAM_ID_BINDINGS}
)
_CONTEXT: ContextVar[IdentityContext | None] = ContextVar(
    "athena_current_shadow_fixture_identity_v2_context", default=None
)


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def competition_identity_matches(fotmob_name: Any, sportybet_name: Any) -> bool:
    if type(fotmob_name) is not str or type(sportybet_name) is not str:
        return False
    return fotmob_name == sportybet_name or _COMPETITION_LOOKUP.get(fotmob_name) == sportybet_name


def _team_id_state(fotmob_team_id: int | None, sportybet_competitor_id: str | None) -> bool | None:
    if fotmob_team_id is None or sportybet_competitor_id is None:
        return None
    expected_provider = _SOURCE_TO_PROVIDER.get(fotmob_team_id)
    expected_source = _PROVIDER_TO_SOURCE.get(sportybet_competitor_id)
    if expected_provider is None and expected_source is None:
        return None
    if expected_provider is not None and expected_provider != sportybet_competitor_id:
        return False
    if expected_source is not None and expected_source != fotmob_team_id:
        return False
    return expected_provider == sportybet_competitor_id and expected_source == fotmob_team_id


def _name_matches(*, competition: str, reviewed_name: str, source_short: str | None,
                  source_long: str | None, provider_name: str) -> bool:
    return (
        reviewed_name == provider_name
        or source_short == provider_name
        or source_long == provider_name
        or legacy_aliases.team_identity_matches(
            competition=competition,
            fotmob_name=reviewed_name,
            sportybet_name=provider_name,
        )
    )


def _source_fixture_map(fotmob_captures: Sequence[Any]) -> Mapping[str, SourceFixtureIdentity]:
    bundle = fotmob_fixture_candidates.build_fotmob_fixture_candidate_bundle(fotmob_captures)
    rows: dict[str, SourceFixtureIdentity] = {}
    for candidate in bundle.candidates:
        key = str(candidate.source_match_id)
        if key in rows:
            raise RuntimeError("duplicate source fixture identifier in V2 identity context")
        rows[key] = SourceFixtureIdentity(
            key, candidate.source_competition_name, candidate.kickoff_utc,
            candidate.home_source_team_id, candidate.home_name, candidate.home_long_name,
            candidate.away_source_team_id, candidate.away_name, candidate.away_long_name,
        )
    return MappingProxyType(rows)


def _walk_dicts(root: Any) -> Iterator[dict[str, Any]]:
    stack = [root]
    visited = 0
    while stack:
        value = stack.pop()
        visited += 1
        if visited > 500_000:
            raise RuntimeError("provider fanout object graph is excessive")
        if type(value) is dict:
            yield value
            stack.extend(reversed(tuple(value.values())))
        elif type(value) is list:
            stack.extend(reversed(value))


def _canonical_pair(category_id: str, tournament_id: str) -> bytes:
    return json.dumps(
        {"category_id": category_id, "tournament_id": tournament_id},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _provider_raw_filename(observation: Any) -> str:
    category_id = getattr(observation, "category_id", None)
    tournament_id = getattr(observation, "tournament_id", None)
    raw_sha = getattr(observation, "raw_sha256", None)
    if (
        type(category_id) is not str or not category_id
        or type(tournament_id) is not str or not tournament_id
        or type(raw_sha) is not str or _SHA_RE.fullmatch(raw_sha) is None
    ):
        raise RuntimeError("verified fanout observation filename identity is invalid")
    pair_hash = hashlib.sha256(_canonical_pair(category_id, tournament_id)).hexdigest()
    return f"pair-{pair_hash[:24]}-{raw_sha[:16]}.json"


def _provider_identity_map(*, fanout_evidence_directory: Path,
                           fanout_snapshot: Any) -> Mapping[str, ProviderTeamIdentity]:
    observations = getattr(fanout_snapshot, "observations", None)
    if type(observations) is not tuple:
        raise RuntimeError("verified fanout snapshot omitted observations")
    tournament_dir = Path(fanout_evidence_directory) / "tournaments"
    rows: dict[str, ProviderTeamIdentity] = {}
    for observation in observations:
        raw_sha = getattr(observation, "raw_sha256", None)
        event_ids = getattr(observation, "event_ids", None)
        if type(raw_sha) is not str or _SHA_RE.fullmatch(raw_sha) is None or type(event_ids) is not tuple:
            raise RuntimeError("verified fanout observation identity is invalid")
        # Resolve the exact category+tournament raw filename used by the reviewed
        # fanout writer.  Raw SHA alone is not unique because distinct empty
        # tournament responses can legitimately have identical bytes/digests.
        raw_path = tournament_dir / _provider_raw_filename(observation)
        if not raw_path.is_file():
            raise RuntimeError("verified provider fanout raw file is unavailable")
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != raw_sha:
            raise RuntimeError("provider fanout raw SHA differs during identity replay")
        try:
            payload = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("provider fanout raw JSON cannot be replayed") from exc
        allowed = set(event_ids)
        for item in _walk_dicts(payload):
            event_id = item.get("eventId")
            if event_id not in allowed:
                continue
            home_id = item.get("homeTeamId")
            away_id = item.get("awayTeamId")
            if (
                type(event_id) is not str
                or type(home_id) is not str
                or type(away_id) is not str
                or _COMPETITOR_RE.fullmatch(home_id) is None
                or _COMPETITOR_RE.fullmatch(away_id) is None
                or home_id == away_id
            ):
                continue
            candidate = ProviderTeamIdentity(event_id, home_id, away_id)
            prior = rows.get(event_id)
            if prior is not None and prior != candidate:
                raise RuntimeError("provider event competitor IDs conflict in retained fanout evidence")
            rows[event_id] = candidate
    return MappingProxyType(rows)


@contextmanager
def identity_context(*, fotmob_captures: Sequence[Any], fanout_evidence_directory: Path,
                     fanout_snapshot: Any) -> Iterator[IdentityContext]:
    value = IdentityContext(
        source_by_fixture=_source_fixture_map(fotmob_captures),
        provider_by_event=_provider_identity_map(
            fanout_evidence_directory=fanout_evidence_directory,
            fanout_snapshot=fanout_snapshot,
        ),
    )
    token = _CONTEXT.set(value)
    try:
        yield value
    finally:
        _CONTEXT.reset(token)


@contextmanager
def identity_rows_context(*, source_rows: Sequence[SourceFixtureIdentity],
                          provider_rows: Sequence[ProviderTeamIdentity]) -> Iterator[IdentityContext]:
    """Deterministic unit-test seam; production uses ``identity_context``."""
    source = {item.source_fixture_identifier: item for item in source_rows}
    provider = {item.event_id: item for item in provider_rows}
    if len(source) != len(tuple(source_rows)) or len(provider) != len(tuple(provider_rows)):
        raise RuntimeError("identity test rows contain duplicate keys")
    value = IdentityContext(MappingProxyType(source), MappingProxyType(provider))
    token = _CONTEXT.set(value)
    try:
        yield value
    finally:
        _CONTEXT.reset(token)


def _source_identity(item: Any, context: IdentityContext) -> SourceFixtureIdentity | None:
    value = getattr(item, "source_fixture_identifier", None)
    return context.source_by_fixture.get(value) if type(value) is str else None


def _provider_identity(event: Any, context: IdentityContext) -> ProviderTeamIdentity | None:
    value = getattr(event, "event_id", None)
    return context.provider_by_event.get(value) if type(value) is str else None


def match_event(event: Any, reviewed_rows: Sequence[Any]) -> tuple[Any, ...]:
    """Return only exact/evidence-bound V2 candidates; caller rejects ambiguity."""
    competition = getattr(event, "competition_name", None)
    kickoff = _utc(getattr(event, "kickoff_utc", None))
    provider_home = getattr(event, "home_team_name", None)
    provider_away = getattr(event, "away_team_name", None)
    if type(competition) is not str or kickoff is None or type(provider_home) is not str or type(provider_away) is not str:
        return ()
    context = _CONTEXT.get()
    if context is None:
        return legacy_aliases.match_event(event, reviewed_rows)

    provider_identity = _provider_identity(event, context)
    bucket = tuple(
        item for item in reviewed_rows
        if competition_identity_matches(getattr(item, "competition", None), competition)
        and _utc(getattr(item, "kickoff", None)) == kickoff
    )
    strong: list[Any] = []
    anchored: list[Any] = []
    for item in bucket:
        source = _source_identity(item, context)
        source_competition = getattr(item, "competition", None)
        reviewed_home = getattr(item, "home_team", None)
        reviewed_away = getattr(item, "away_team", None)
        if type(source_competition) is not str or type(reviewed_home) is not str or type(reviewed_away) is not str:
            continue
        home_id_state: bool | None = None
        away_id_state: bool | None = None
        if source is not None and provider_identity is not None:
            home_id_state = _team_id_state(source.home_team_id, provider_identity.home_competitor_id)
            away_id_state = _team_id_state(source.away_team_id, provider_identity.away_competitor_id)
            if home_id_state is False or away_id_state is False:
                continue
            if (
                _team_id_state(source.home_team_id, provider_identity.away_competitor_id) is True
                or _team_id_state(source.away_team_id, provider_identity.home_competitor_id) is True
            ):
                continue
        home_name = _name_matches(
            competition=source_competition,
            reviewed_name=reviewed_home,
            source_short=None if source is None else source.home_short_name,
            source_long=None if source is None else source.home_long_name,
            provider_name=provider_home,
        )
        away_name = _name_matches(
            competition=source_competition,
            reviewed_name=reviewed_away,
            source_short=None if source is None else source.away_short_name,
            source_long=None if source is None else source.away_long_name,
            provider_name=provider_away,
        )
        home_match = home_id_state is True or home_name
        away_match = away_id_state is True or away_name
        if home_match and away_match:
            strong.append(item)
        elif home_match != away_match:
            anchored.append(item)
    return tuple(strong) if strong else tuple(anchored)


def registry_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "source_replay_policy_id": SOURCE_REPLAY_POLICY_ID,
        "provider_id_policy_id": PROVIDER_ID_POLICY_ID,
        "matching_basis": MATCHING_BASIS,
        "competition_aliases": [
            {"fotmob_name": row.fotmob_name, "sportybet_name": row.sportybet_name,
             "evidence_basis": row.evidence_basis}
            for row in COMPETITION_ALIASES
        ],
        "team_id_bindings": [
            {"fotmob_team_id": row.fotmob_team_id,
             "sportybet_competitor_id": row.sportybet_competitor_id,
             "fotmob_observed_name": row.fotmob_observed_name,
             "sportybet_observed_name": row.sportybet_observed_name,
             "evidence_basis": row.evidence_basis}
            for row in TEAM_ID_BINDINGS
        ],
        "legacy_alias_registry_sha256": legacy_aliases.REGISTRY_SHA256,
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
    raw = json.dumps(registry_payload(), ensure_ascii=False, allow_nan=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


REGISTRY_SHA256 = registry_sha256()

__all__ = [
    "COMPETITION_ALIASES", "IdentityContext", "MATCHING_BASIS", "POLICY_ID",
    "PROVIDER_ID_POLICY_ID", "ProviderTeamIdentity", "REGISTRY_SHA256",
    "RUN34_EVIDENCE", "RUN38_EVIDENCE", "SCHEMA_VERSION", "SOURCE_REPLAY_POLICY_ID",
    "SourceFixtureIdentity", "TEAM_ID_BINDINGS", "competition_identity_matches",
    "identity_context", "identity_rows_context", "match_event", "registry_payload",
    "registry_sha256",
]
