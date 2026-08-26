"""Source-qualified UEFA stage semantics for ATHENA historical research.

Stable parent competition keys remain unchanged. Stage authority is issued only
by replaying the canonical warehouse and its field/source provenance. UNKNOWN is
first-class. This module grants research stratification only; never probability,
pricing, routing, selection, accumulator, production, or BET authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from types import MappingProxyType
from typing import Any, Iterable, Mapping


DATASET = "athena_uefa_competition_stage"
SCHEMA_VERSION = 1
REGISTRY_VERSION = 1
CONTRACT_VERSION = 1

PARENTS = MappingProxyType({
    "uefa_ucl": "UEFA Champions League",
    "uefa_uel": "UEFA Europa League",
    "uefa_uecl": "UEFA Conference League",
})
SOURCE_POLICY = "WAREHOUSE_EXACT_FIELD_PROVENANCE_AND_SOURCE_LINEAGE_V1"
QUALIFIER_POLICY = "OPENFOOTBALL_SAME_SOURCE_QUALIFIER_FILE_REQUIRED_V1"
ERA_POLICY = "UEFA_STAGE_ERA_ALLOWLIST_FAIL_CLOSED_V1"
TIE_POLICY = "PRIOR_RECIPROCAL_SAME_SOURCE_STAGE_AND_FT_SECOND_LEG_ONLY_V1"
AWAY_GOALS_POLICY = "UEFA_AWAY_GOALS_THROUGH_2020_21_V1"
TRAINING_JOIN_POLICY = "EXACT_MATCH_KEY_AND_WAREHOUSE_SHA_SIDECAR_V1"
AUTHORITY_FLAGS = MappingProxyType({
    "research_stage_stratification": True,
    "historical_projection": True,
    "training_sidecar_join": True,
    "fixture_state_live_authority": False,
    "probability_inference": False,
    "calibration": False,
    "bookmaker_pricing": False,
    "market_routing": False,
    "selection": False,
    "accumulator": False,
    "production_approval": False,
    "bet": False,
})


class UEFAStageError(ValueError):
    pass


class UEFACompetitionStage(str, Enum):
    UNKNOWN = "UNKNOWN"
    QUALIFYING_R1 = "QUALIFYING_R1"
    QUALIFYING_R2 = "QUALIFYING_R2"
    QUALIFYING_R3 = "QUALIFYING_R3"
    QUALIFYING_PLAYOFF = "QUALIFYING_PLAYOFF"
    GROUP_PHASE = "GROUP_PHASE"
    LEAGUE_PHASE = "LEAGUE_PHASE"
    ROUND_OF_32 = "ROUND_OF_32"
    KNOCKOUT_PLAYOFF = "KNOCKOUT_PLAYOFF"
    ROUND_OF_16 = "ROUND_OF_16"
    QUARTER_FINAL = "QUARTER_FINAL"
    SEMI_FINAL = "SEMI_FINAL"
    FINAL = "FINAL"


class UEFATieFormat(str, Enum):
    UNKNOWN = "UNKNOWN"
    SINGLE_MATCH = "SINGLE_MATCH"
    TWO_LEG = "TWO_LEG"
    LEAGUE = "LEAGUE"


class UEFAQualificationState(str, Enum):
    UNKNOWN = "UNKNOWN"
    LEVEL = "LEVEL"
    HOME_ADVANTAGE = "HOME_ADVANTAGE"
    AWAY_ADVANTAGE = "AWAY_ADVANTAGE"


# Inclusive season-start-year eras. None means open-ended.
# Historical group phase and modern league phase are intentionally distinct.
ERA_REGISTRY: Mapping[str, Mapping[str, tuple[int, int | None]]] = MappingProxyType({
    "uefa_ucl": MappingProxyType({
        "QUALIFYING_R1": (1992, None), "QUALIFYING_R2": (1992, None),
        "QUALIFYING_R3": (1992, None), "QUALIFYING_PLAYOFF": (2009, None),
        "GROUP_PHASE": (1992, 2023), "LEAGUE_PHASE": (2024, None),
        "KNOCKOUT_PLAYOFF": (2024, None), "ROUND_OF_16": (2003, None),
        "QUARTER_FINAL": (1992, None), "SEMI_FINAL": (1992, None),
        "FINAL": (1992, None),
    }),
    "uefa_uel": MappingProxyType({
        "QUALIFYING_R1": (1971, None), "QUALIFYING_R2": (1971, None),
        "QUALIFYING_R3": (1971, None), "QUALIFYING_PLAYOFF": (2009, None),
        "GROUP_PHASE": (2004, 2023), "LEAGUE_PHASE": (2024, None),
        "ROUND_OF_32": (2004, 2020), "KNOCKOUT_PLAYOFF": (2021, None),
        "ROUND_OF_16": (1971, None), "QUARTER_FINAL": (1971, None),
        "SEMI_FINAL": (1971, None), "FINAL": (1971, None),
    }),
    "uefa_uecl": MappingProxyType({
        "QUALIFYING_R1": (2021, None), "QUALIFYING_R2": (2021, None),
        "QUALIFYING_R3": (2021, None), "QUALIFYING_PLAYOFF": (2021, None),
        "GROUP_PHASE": (2021, 2023), "LEAGUE_PHASE": (2024, None),
        "KNOCKOUT_PLAYOFF": (2021, None), "ROUND_OF_16": (2021, None),
        "QUARTER_FINAL": (2021, None), "SEMI_FINAL": (2021, None),
        "FINAL": (2021, None),
    }),
})
QUALIFIER_FILES = MappingProxyType({
    "clq.txt": "uefa_ucl", "elq.txt": "uefa_uel", "confq.txt": "uefa_uecl"
})
MAIN_FILES = MappingProxyType({
    "cl.txt": "uefa_ucl", "el.txt": "uefa_uel", "conf.txt": "uefa_uecl"
})
KNOCKOUT = frozenset({
    UEFACompetitionStage.QUALIFYING_R1, UEFACompetitionStage.QUALIFYING_R2,
    UEFACompetitionStage.QUALIFYING_R3, UEFACompetitionStage.QUALIFYING_PLAYOFF,
    UEFACompetitionStage.ROUND_OF_32, UEFACompetitionStage.KNOCKOUT_PLAYOFF,
    UEFACompetitionStage.ROUND_OF_16, UEFACompetitionStage.QUARTER_FINAL,
    UEFACompetitionStage.SEMI_FINAL, UEFACompetitionStage.FINAL,
})


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise UEFAStageError("canonical serialization failed") from exc


def _registry_payload() -> dict[str, Any]:
    return {
        comp: {stage: [lo, hi] for stage, (lo, hi) in sorted(rules.items())}
        for comp, rules in sorted(ERA_REGISTRY.items())
    }


def calculate_parent_identity_sha256() -> str:
    return hashlib.sha256(_canon({"dataset": DATASET, "parents": dict(PARENTS)})).hexdigest()


def calculate_stage_registry_sha256() -> str:
    return hashlib.sha256(_canon({
        "version": REGISTRY_VERSION, "eras": _registry_payload()
    })).hexdigest()


def calculate_stage_contract_sha256(parent_sha: str, registry_sha: str) -> str:
    return hashlib.sha256(_canon({
        "version": CONTRACT_VERSION, "schema_version": SCHEMA_VERSION,
        "parent_identity_sha256": parent_sha, "stage_registry_sha256": registry_sha,
        "source_policy": SOURCE_POLICY, "qualifier_policy": QUALIFIER_POLICY,
        "era_policy": ERA_POLICY, "tie_policy": TIE_POLICY,
        "away_goals_policy": AWAY_GOALS_POLICY,
        "training_join_policy": TRAINING_JOIN_POLICY,
        "authority_flags": dict(AUTHORITY_FLAGS),
    })).hexdigest()


EXPECTED_PARENT_IDENTITY_SHA256 = "1ec3df0b5c1a428cf92b1427929acb0c80e04143b90166fdd2e74da8516b8fec"
EXPECTED_STAGE_REGISTRY_SHA256 = "3125b6673b30a6706d9f03e335ae79ebca65a9a6c4b291504a7e5ae92a36d69b"
EXPECTED_STAGE_CONTRACT_SHA256 = "54fc67276364d8e447a95afcefcc5efdb36f7f33a8e0b69869d659e84916c943"


def validate_uefa_stage_contract() -> tuple[str, str, str]:
    parent = calculate_parent_identity_sha256()
    registry = calculate_stage_registry_sha256()
    contract = calculate_stage_contract_sha256(parent, registry)
    if parent != EXPECTED_PARENT_IDENTITY_SHA256:
        raise UEFAStageError("UEFA parent identity drift")
    if registry != EXPECTED_STAGE_REGISTRY_SHA256:
        raise UEFAStageError("UEFA stage registry drift")
    if contract != EXPECTED_STAGE_CONTRACT_SHA256:
        raise UEFAStageError("UEFA stage contract drift")
    return parent, registry, contract


def _norm(value: Any) -> str:
    if type(value) is not str:
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def season_start_year(season: Any) -> int | None:
    if type(season) is not str:
        return None
    m = re.fullmatch(r"\s*(\d{4})(?:[-/]\d{2,4})?\s*", season)
    return int(m.group(1)) if m else None


def stage_allowed_in_era(comp: str, stage: UEFACompetitionStage, season: Any) -> bool:
    if stage is UEFACompetitionStage.UNKNOWN:
        return True
    year = season_start_year(season)
    era = ERA_REGISTRY.get(comp, {}).get(stage.value)
    return bool(year is not None and era is not None
                and year >= era[0] and (era[1] is None or year <= era[1]))


def _source_path(extra_json: Any) -> str | None:
    if type(extra_json) is not str:
        return None
    try:
        data = json.loads(extra_json)
    except json.JSONDecodeError:
        return None
    path = data.get("openfootball_path") if type(data) is dict else None
    return path if type(path) is str and path.strip() else None


def _explicit(label: str, season: str) -> UEFACompetitionStage:
    n = _norm(label)
    exact = {
        "group stage": UEFACompetitionStage.GROUP_PHASE,
        "group phase": UEFACompetitionStage.GROUP_PHASE,
        "league phase": UEFACompetitionStage.LEAGUE_PHASE,
        "round of 32": UEFACompetitionStage.ROUND_OF_32,
        "round of 16": UEFACompetitionStage.ROUND_OF_16,
        "last 16": UEFACompetitionStage.ROUND_OF_16,
        "quarter final": UEFACompetitionStage.QUARTER_FINAL,
        "quarter finals": UEFACompetitionStage.QUARTER_FINAL,
        "semi final": UEFACompetitionStage.SEMI_FINAL,
        "semi finals": UEFACompetitionStage.SEMI_FINAL,
        "final": UEFACompetitionStage.FINAL,
        "knockout playoff": UEFACompetitionStage.KNOCKOUT_PLAYOFF,
        "knockout play off": UEFACompetitionStage.KNOCKOUT_PLAYOFF,
        "knockout play offs": UEFACompetitionStage.KNOCKOUT_PLAYOFF,
    }
    if n in exact:
        return exact[n]
    if n.startswith("league matchday "):
        year = season_start_year(season)
        return UEFACompetitionStage.LEAGUE_PHASE if year and year >= 2024 else UEFACompetitionStage.UNKNOWN
    if n.startswith("group "):
        return UEFACompetitionStage.GROUP_PHASE
    for prefix, stage in (
        ("round of 32 ", UEFACompetitionStage.ROUND_OF_32),
        ("round of 16 ", UEFACompetitionStage.ROUND_OF_16),
        ("quarter final ", UEFACompetitionStage.QUARTER_FINAL),
        ("semi final ", UEFACompetitionStage.SEMI_FINAL),
    ):
        if n.startswith(prefix):
            return stage
    return UEFACompetitionStage.UNKNOWN


def _path_stage(comp: str, label: str, path: str | None, season: str) -> UEFACompetitionStage:
    if not path:
        return UEFACompetitionStage.UNKNOWN
    name = Path(path).name.casefold()
    n = _norm(label)
    if QUALIFIER_FILES.get(name) == comp:
        if n in {"1 round", "first round", "qualifying round 1", "qualifying r1"}:
            return UEFACompetitionStage.QUALIFYING_R1
        if n in {"2 round", "second round", "qualifying round 2", "qualifying r2"}:
            return UEFACompetitionStage.QUALIFYING_R2
        if n in {"3 round", "third round", "qualifying round 3", "qualifying r3"}:
            return UEFACompetitionStage.QUALIFYING_R3
        if n in {"play offs", "play off", "playoffs", "playoff",
                 "qualifying play offs", "qualifying playoff"}:
            return UEFACompetitionStage.QUALIFYING_PLAYOFF
    if MAIN_FILES.get(name) == comp and n in {"play offs", "play off", "playoffs", "playoff"}:
        year = season_start_year(season)
        if year and year >= 2024:
            return UEFACompetitionStage.KNOCKOUT_PLAYOFF
    return UEFACompetitionStage.UNKNOWN


@dataclass(frozen=True, init=False)
class UEFAStageEvidence:
    match_key: str
    competition_key: str
    season: str
    match_date: str
    home_team: str
    away_team: str
    raw_stage: str | None
    raw_round_name: str | None
    stage_source: str | None
    round_source: str | None
    extra_source: str | None
    source_path: str | None
    source_match_id: str | None
    source_url: str | None
    source_payload_sha256: str | None
    source_lineage_resolved: bool
    warehouse_sha256: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise UEFAStageError("evidence is issued only from canonical warehouse replay")

    @classmethod
    def _issue(cls, **values: Any) -> "UEFAStageEvidence":
        obj = object.__new__(cls)
        for name in cls.__dataclass_fields__:
            object.__setattr__(obj, name, values[name])
        return obj

    def identity_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, init=False)
class UEFAStageProjection:
    match_key: str
    competition_key: str
    competition_stage: UEFACompetitionStage
    tie_format: UEFATieFormat
    leg_number: int | None
    aggregate_home: int | None
    aggregate_away: int | None
    qualification_state: UEFAQualificationState
    extra_time_possible: bool | None
    penalties_possible: bool | None
    stage_source_identity: str
    stage_contract_sha256: str
    warehouse_sha256: str
    stage_authorized: bool
    blocker: str | None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise UEFAStageError("projection is issued only from canonical warehouse replay")

    @classmethod
    def _issue(cls, **values: Any) -> "UEFAStageProjection":
        obj = object.__new__(cls)
        for name in cls.__dataclass_fields__:
            object.__setattr__(obj, name, values[name])
        return obj

    def stable_dict(self) -> dict[str, Any]:
        out = {name: (getattr(self, name).value if isinstance(getattr(self, name), Enum)
                      else getattr(self, name)) for name in self.__dataclass_fields__}
        out["authority_flags"] = dict(AUTHORITY_FLAGS)
        return out


def _companions(path: Path, label: str) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise UEFAStageError(f"{label} has active SQLite companion {suffix}")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _field_source(db: sqlite3.Connection, key: str, field: str) -> str | None:
    row = db.execute("SELECT source_key FROM warehouse_field_provenance "
                     "WHERE match_key=? AND field_name=?", (key, field)).fetchone()
    return str(row[0]) if row else None


def _load(db: sqlite3.Connection, key: str, warehouse_sha: str) -> UEFAStageEvidence:
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT match_key,competition_key,season,match_date,home_team,"
                     "away_team,stage,round_name,extra_json FROM warehouse_matches "
                     "WHERE match_key=?", (key,)).fetchone()
    if row is None or row["competition_key"] not in PARENTS:
        raise UEFAStageError("match is absent or not a reviewed UEFA parent")
    for field in ("match_key", "season", "match_date", "home_team", "away_team"):
        if type(row[field]) is not str or not row[field]:
            raise UEFAStageError(f"UEFA row missing exact {field}")
    stage_source = _field_source(db, key, "stage")
    round_source = _field_source(db, key, "round_name")
    extra_source = _field_source(db, key, "extra_json")
    source_key = stage_source or round_source
    source = None
    if source_key:
        rows = db.execute("SELECT source_match_id,source_url,payload_sha256 "
                          "FROM warehouse_match_sources WHERE match_key=? AND source_key=?",
                          (key, source_key)).fetchall()
        source = rows[0] if len(rows) == 1 else None
    path = _source_path(row["extra_json"]) if source_key == extra_source == "openfootball" else None
    return UEFAStageEvidence._issue(
        match_key=row["match_key"], competition_key=row["competition_key"],
        season=row["season"], match_date=row["match_date"], home_team=row["home_team"],
        away_team=row["away_team"], raw_stage=row["stage"] if type(row["stage"]) is str else None,
        raw_round_name=row["round_name"] if type(row["round_name"]) is str else None,
        stage_source=stage_source, round_source=round_source, extra_source=extra_source,
        source_path=path, source_match_id=str(source["source_match_id"]) if source and source["source_match_id"] is not None else None,
        source_url=str(source["source_url"]) if source and source["source_url"] is not None else None,
        source_payload_sha256=str(source["payload_sha256"]) if source and source["payload_sha256"] is not None else None,
        source_lineage_resolved=source is not None, warehouse_sha256=warehouse_sha,
    )


def _derive_stage(e: UEFAStageEvidence) -> tuple[UEFACompetitionStage, str | None]:
    if e.stage_source and e.round_source and e.stage_source != e.round_source:
        return UEFACompetitionStage.UNKNOWN, "STAGE_ROUND_SOURCE_CONFLICT"
    if (e.stage_source or e.round_source) and not e.source_lineage_resolved:
        return UEFACompetitionStage.UNKNOWN, "STAGE_SOURCE_LINEAGE_NOT_UNIQUE"
    for label, source, field_name in (
        (e.raw_stage, e.stage_source, "STAGE"),
        (e.raw_round_name, e.round_source, "ROUND"),
    ):
        if not label:
            continue
        if not source:
            return UEFACompetitionStage.UNKNOWN, f"{field_name}_FIELD_HAS_NO_SOURCE_PROVENANCE"
        stage = _explicit(label, e.season)
        if stage is UEFACompetitionStage.UNKNOWN and field_name == "STAGE":
            stage = _path_stage(e.competition_key, label, e.source_path, e.season)
            if stage is not UEFACompetitionStage.UNKNOWN and not (
                e.stage_source == e.extra_source == "openfootball"
            ):
                return UEFACompetitionStage.UNKNOWN, "PATH_CONTEXT_NOT_SAME_SOURCE"
        if stage is not UEFACompetitionStage.UNKNOWN:
            if stage_allowed_in_era(e.competition_key, stage, e.season):
                return stage, None
            return UEFACompetitionStage.UNKNOWN, "STAGE_NOT_ALLOWED_IN_COMPETITION_ERA"
    return UEFACompetitionStage.UNKNOWN, "UNMAPPED_OR_AMBIGUOUS_STAGE"


def _prior_leg(db: sqlite3.Connection, e: UEFAStageEvidence) -> sqlite3.Row | None:
    if not e.stage_source:
        return None
    rows = db.execute("""
        SELECT m.match_key,m.stage,m.round_name,m.home_score_ft,m.away_score_ft,
               ps.source_key,s.source_match_id,s.source_url,s.payload_sha256
        FROM warehouse_matches m
        JOIN warehouse_field_provenance ps ON ps.match_key=m.match_key AND ps.field_name='stage'
        JOIN warehouse_field_provenance ph ON ph.match_key=m.match_key AND ph.field_name='home_score_ft'
        JOIN warehouse_field_provenance pa ON pa.match_key=m.match_key AND pa.field_name='away_score_ft'
        JOIN warehouse_match_sources s ON s.match_key=m.match_key AND s.source_key=ps.source_key
        WHERE m.competition_key=? AND m.season=? AND m.match_date<?
          AND m.home_team=? AND m.away_team=?
          AND COALESCE(m.stage,'')=COALESCE(?,'')
          AND COALESCE(m.round_name,'')=COALESCE(?,'')
          AND ps.source_key=? AND ph.source_key=ps.source_key AND pa.source_key=ps.source_key
    """, (e.competition_key, e.season, e.match_date, e.away_team, e.home_team,
          e.raw_stage, e.raw_round_name, e.stage_source)).fetchall()
    return rows[0] if len(rows) == 1 and rows[0]["home_score_ft"] is not None and rows[0]["away_score_ft"] is not None else None


def _source_identity(e: UEFAStageEvidence, prior: sqlite3.Row | None = None) -> str:
    payload: dict[str, Any] = {"current": e.identity_payload()}
    if prior is not None:
        payload["prior_second_leg_ancestry"] = {
            key: prior[key] for key in ("match_key", "stage", "round_name",
                                        "home_score_ft", "away_score_ft", "source_key",
                                        "source_match_id", "source_url", "payload_sha256")
        }
    return hashlib.sha256(_canon(payload)).hexdigest()


def _project(db: sqlite3.Connection, e: UEFAStageEvidence) -> UEFAStageProjection:
    _, _, contract = validate_uefa_stage_contract()
    stage, blocker = _derive_stage(e)
    identity = _source_identity(e)
    if stage is UEFACompetitionStage.UNKNOWN:
        return UEFAStageProjection._issue(
            match_key=e.match_key, competition_key=e.competition_key, competition_stage=stage,
            tie_format=UEFATieFormat.UNKNOWN, leg_number=None, aggregate_home=None,
            aggregate_away=None, qualification_state=UEFAQualificationState.UNKNOWN,
            extra_time_possible=None, penalties_possible=None, stage_source_identity=identity,
            stage_contract_sha256=contract, warehouse_sha256=e.warehouse_sha256,
            stage_authorized=False, blocker=blocker,
        )
    tie, extra, pens = UEFATieFormat.UNKNOWN, None, None
    if stage in {UEFACompetitionStage.GROUP_PHASE, UEFACompetitionStage.LEAGUE_PHASE}:
        tie, extra, pens = UEFATieFormat.LEAGUE, False, False
    elif stage is UEFACompetitionStage.FINAL:
        tie, extra, pens = UEFATieFormat.SINGLE_MATCH, True, True
    leg = ah = aa = None
    qstate = UEFAQualificationState.UNKNOWN
    if stage in KNOCKOUT and stage is not UEFACompetitionStage.FINAL:
        prior = _prior_leg(db, e)
        if prior is not None:
            ah, aa = int(prior["away_score_ft"]), int(prior["home_score_ft"])
            if ah > aa:
                qstate = UEFAQualificationState.HOME_ADVANTAGE
            elif aa > ah:
                qstate = UEFAQualificationState.AWAY_ADVANTAGE
            elif season_start_year(e.season) is not None and season_start_year(e.season) <= 2020 and ah > 0:
                qstate = UEFAQualificationState.HOME_ADVANTAGE
            else:
                qstate = UEFAQualificationState.LEVEL
            tie, leg, extra, pens = UEFATieFormat.TWO_LEG, 2, True, True
            identity = _source_identity(e, prior)
    return UEFAStageProjection._issue(
        match_key=e.match_key, competition_key=e.competition_key, competition_stage=stage,
        tie_format=tie, leg_number=leg, aggregate_home=ah, aggregate_away=aa,
        qualification_state=qstate, extra_time_possible=extra, penalties_possible=pens,
        stage_source_identity=identity, stage_contract_sha256=contract,
        warehouse_sha256=e.warehouse_sha256, stage_authorized=True, blocker=None,
    )


def project_warehouse_uefa_stages(warehouse_path: Path) -> tuple[UEFAStageProjection, ...]:
    path = Path(warehouse_path).resolve()
    if not path.is_file():
        raise UEFAStageError("historical warehouse does not exist")
    _companions(path, "historical warehouse")
    warehouse_sha = _sha(path)
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"warehouse_matches", "warehouse_field_provenance", "warehouse_match_sources"}
        if not required <= tables:
            raise UEFAStageError("historical warehouse schema is unsupported")
        keys = [r[0] for r in db.execute(
            "SELECT match_key FROM warehouse_matches WHERE competition_key IN "
            "('uefa_ucl','uefa_uel','uefa_uecl') ORDER BY match_date,match_key"
        )]
        return tuple(_project(db, _load(db, key, warehouse_sha)) for key in keys)
    finally:
        db.close()


def stage_coverage_report(projections: Iterable[UEFAStageProjection]) -> dict[str, Any]:
    rows = tuple(projections)
    authorized = sum(row.stage_authorized for row in rows)
    by_comp: dict[str, dict[str, int]] = {}
    by_stage: dict[str, int] = {}
    blockers: dict[str, int] = {}
    for row in rows:
        bucket = by_comp.setdefault(row.competition_key, {"total": 0, "authorized": 0, "unknown": 0})
        bucket["total"] += 1
        bucket["authorized" if row.stage_authorized else "unknown"] += 1
        by_stage[row.competition_stage.value] = by_stage.get(row.competition_stage.value, 0) + 1
        if row.blocker:
            blockers[row.blocker] = blockers.get(row.blocker, 0) + 1
    return {
        "dataset": DATASET, "schema_version": SCHEMA_VERSION,
        "total_uefa_matches": len(rows), "authorized_stage_matches": authorized,
        "unknown_stage_matches": len(rows) - authorized,
        "coverage_fraction": authorized / len(rows) if rows else None,
        "by_competition": dict(sorted(by_comp.items())),
        "by_stage": dict(sorted(by_stage.items())),
        "blockers": dict(sorted(blockers.items())),
        "authority_flags": dict(AUTHORITY_FLAGS),
    }


def project_training_view_uefa_stages(training_view_path: Path, warehouse_path: Path) -> tuple[UEFAStageProjection, ...]:
    training, warehouse = Path(training_view_path).resolve(), Path(warehouse_path).resolve()
    if not training.is_file() or not warehouse.is_file():
        raise UEFAStageError("training view or historical warehouse does not exist")
    _companions(training, "Goal/Score training view")
    _companions(warehouse, "historical warehouse")
    warehouse_sha = _sha(warehouse)
    db = sqlite3.connect(f"{training.as_uri()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"corpus_meta", "training_rows"} <= tables:
            raise UEFAStageError("Goal/Score training view schema is unsupported")
        meta = db.execute("SELECT value FROM corpus_meta WHERE key='source_warehouse_sha256'").fetchone()
        if meta is None:
            raise UEFAStageError("training view lacks source warehouse identity")
        try:
            training_sha = json.loads(meta[0])
        except json.JSONDecodeError as exc:
            raise UEFAStageError("training warehouse identity is malformed") from exc
        if training_sha != warehouse_sha:
            raise UEFAStageError("training view and stage projection warehouse SHA mismatch")
        keys = {r[0] for r in db.execute(
            "SELECT match_key FROM training_rows WHERE competition_key IN "
            "('uefa_ucl','uefa_uel','uefa_uecl')"
        )}
    finally:
        db.close()
    projected = {row.match_key: row for row in project_warehouse_uefa_stages(warehouse)}
    if keys - projected.keys():
        raise UEFAStageError("UEFA training rows missing from stage projection")
    return tuple(projected[key] for key in sorted(keys))


def training_view_stage_join_report(training_view_path: Path, warehouse_path: Path) -> dict[str, Any]:
    warehouse = Path(warehouse_path).resolve()
    rows = project_training_view_uefa_stages(training_view_path, warehouse)
    report = stage_coverage_report(rows)
    report.update({
        "join_policy": TRAINING_JOIN_POLICY,
        "source_warehouse_sha256": _sha(warehouse),
        "uefa_training_rows": len(rows),
    })
    return report


__all__ = [
    "AUTHORITY_FLAGS", "AWAY_GOALS_POLICY", "DATASET", "ERA_POLICY", "ERA_REGISTRY",
    "EXPECTED_PARENT_IDENTITY_SHA256", "EXPECTED_STAGE_CONTRACT_SHA256",
    "EXPECTED_STAGE_REGISTRY_SHA256", "PARENTS", "QUALIFIER_POLICY", "REGISTRY_VERSION",
    "SCHEMA_VERSION", "SOURCE_POLICY", "TIE_POLICY", "TRAINING_JOIN_POLICY",
    "UEFACompetitionStage", "UEFAQualificationState", "UEFAStageError",
    "UEFAStageEvidence", "UEFAStageProjection", "UEFATieFormat",
    "calculate_parent_identity_sha256", "calculate_stage_contract_sha256",
    "calculate_stage_registry_sha256", "project_training_view_uefa_stages",
    "project_warehouse_uefa_stages", "season_start_year", "stage_allowed_in_era",
    "stage_coverage_report", "training_view_stage_join_report", "validate_uefa_stage_contract",
]
