"""Source-qualified UEFA stage semantics for ATHENA historical research.

Stable parent competition keys remain unchanged. Stage authority is issued only
by replaying the canonical warehouse, its reviewed schema, and exact field/source
provenance. UNKNOWN is first-class. This module grants research stratification
only; never probability, pricing, routing, selection, accumulator, production,
or BET authority.
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
TRAINING_SIDECAR_CONTRACT_VERSION = 1

PARENTS = MappingProxyType({
    "uefa_ucl": "UEFA Champions League",
    "uefa_uel": "UEFA Europa League",
    "uefa_uecl": "UEFA Conference League",
})
REVIEWED_STAGE_SOURCES = frozenset({"openfootball"})
SOURCE_POLICY = "WAREHOUSE_SCHEMA_V1_EXACT_FIELD_PROVENANCE_REVIEWED_SOURCE_ALLOWLIST_V2"
QUALIFIER_POLICY = "OPENFOOTBALL_SAME_SOURCE_QUALIFIER_FILE_REQUIRED_V1"
ERA_POLICY = "UEFA_STAGE_ERA_ALLOWLIST_FAIL_CLOSED_V1"
TIE_POLICY = "PRIOR_RECIPROCAL_REPLAYED_STAGE_AND_SAME_SOURCE_REGULATION_FT_V2"
AWAY_GOALS_POLICY = "UEFA_AWAY_GOALS_THROUGH_2020_21_V1"
FINAL_FORMAT_POLICY = (
    "UEL_FINAL_TWO_LEG_THROUGH_1996_97_OTHER_REVIEWED_FINALS_SINGLE_MATCH_V1"
)
TRAINING_JOIN_POLICY = "EXACT_MATCH_KEY_WAREHOUSE_SHA_AND_GOAL_SCORE_CONTRACT_V2"
EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256 = (
    "d5a3b545a639c43a2b35fb18529a429ba2572d2861ac52c638cce42a8141306f"
)
EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256 = (
    "bac5380814de579dffe96d4e5daa39b0cf1e2d6144b59b5d89f2a81f7b27017b"
)
OPENFOOTBALL_URL_PREFIX = "https://github.com/openfootball/"
OPENFOOTBALL_URL_SUFFIX = "/archive/refs/heads/master.zip"

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
    """Raised when UEFA stage semantics cannot be proven safely."""


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
ERA_REGISTRY: Mapping[str, Mapping[str, tuple[int, int | None]]] = MappingProxyType({
    "uefa_ucl": MappingProxyType({
        "QUALIFYING_R1": (1992, None),
        "QUALIFYING_R2": (1992, None),
        "QUALIFYING_R3": (1992, None),
        "QUALIFYING_PLAYOFF": (2009, None),
        "GROUP_PHASE": (1992, 2023),
        "LEAGUE_PHASE": (2024, None),
        "KNOCKOUT_PLAYOFF": (2024, None),
        "ROUND_OF_16": (2003, None),
        "QUARTER_FINAL": (1992, None),
        "SEMI_FINAL": (1992, None),
        "FINAL": (1992, None),
    }),
    "uefa_uel": MappingProxyType({
        "QUALIFYING_R1": (1971, None),
        "QUALIFYING_R2": (1971, None),
        "QUALIFYING_R3": (1971, None),
        "QUALIFYING_PLAYOFF": (2009, None),
        "GROUP_PHASE": (2004, 2023),
        "LEAGUE_PHASE": (2024, None),
        "ROUND_OF_32": (2004, 2020),
        "KNOCKOUT_PLAYOFF": (2021, None),
        "ROUND_OF_16": (1971, None),
        "QUARTER_FINAL": (1971, None),
        "SEMI_FINAL": (1971, None),
        "FINAL": (1971, None),
    }),
    "uefa_uecl": MappingProxyType({
        "QUALIFYING_R1": (2021, None),
        "QUALIFYING_R2": (2021, None),
        "QUALIFYING_R3": (2021, None),
        "QUALIFYING_PLAYOFF": (2021, None),
        "GROUP_PHASE": (2021, 2023),
        "LEAGUE_PHASE": (2024, None),
        "KNOCKOUT_PLAYOFF": (2021, None),
        "ROUND_OF_16": (2021, None),
        "QUARTER_FINAL": (2021, None),
        "SEMI_FINAL": (2021, None),
        "FINAL": (2021, None),
    }),
})
QUALIFIER_FILES = MappingProxyType({
    "clq.txt": "uefa_ucl",
    "elq.txt": "uefa_uel",
    "confq.txt": "uefa_uecl",
})
MAIN_FILES = MappingProxyType({
    "cl.txt": "uefa_ucl",
    "el.txt": "uefa_uel",
    "conf.txt": "uefa_uecl",
})
KNOCKOUT = frozenset({
    UEFACompetitionStage.QUALIFYING_R1,
    UEFACompetitionStage.QUALIFYING_R2,
    UEFACompetitionStage.QUALIFYING_R3,
    UEFACompetitionStage.QUALIFYING_PLAYOFF,
    UEFACompetitionStage.ROUND_OF_32,
    UEFACompetitionStage.KNOCKOUT_PLAYOFF,
    UEFACompetitionStage.ROUND_OF_16,
    UEFACompetitionStage.QUARTER_FINAL,
    UEFACompetitionStage.SEMI_FINAL,
    UEFACompetitionStage.FINAL,
})


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise UEFAStageError("canonical serialization failed") from exc


def _registry_payload() -> dict[str, Any]:
    return {
        comp: {stage: [lo, hi] for stage, (lo, hi) in sorted(rules.items())}
        for comp, rules in sorted(ERA_REGISTRY.items())
    }


def calculate_parent_identity_sha256() -> str:
    return hashlib.sha256(
        _canon({"dataset": DATASET, "parents": dict(PARENTS)})
    ).hexdigest()


def calculate_stage_registry_sha256() -> str:
    return hashlib.sha256(
        _canon({"version": REGISTRY_VERSION, "eras": _registry_payload()})
    ).hexdigest()


def calculate_stage_contract_sha256(parent_sha: str, registry_sha: str) -> str:
    return hashlib.sha256(_canon({
        "version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "parent_identity_sha256": parent_sha,
        "stage_registry_sha256": registry_sha,
        "source_policy": SOURCE_POLICY,
        "reviewed_stage_sources": sorted(REVIEWED_STAGE_SOURCES),
        "qualifier_policy": QUALIFIER_POLICY,
        "era_policy": ERA_POLICY,
        "tie_policy": TIE_POLICY,
        "away_goals_policy": AWAY_GOALS_POLICY,
        "final_format_policy": FINAL_FORMAT_POLICY,
        "training_join_policy": TRAINING_JOIN_POLICY,
        "warehouse_schema_sql_sha256": EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256,
        "goal_score_training_view_contract_sha256": (
            EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256
        ),
        "authority_flags": dict(AUTHORITY_FLAGS),
    })).hexdigest()


def calculate_training_sidecar_contract_sha256(stage_contract_sha: str) -> str:
    return hashlib.sha256(_canon({
        "version": TRAINING_SIDECAR_CONTRACT_VERSION,
        "stage_contract_sha256": stage_contract_sha,
        "warehouse_schema_sql_sha256": EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256,
        "goal_score_training_view_contract_sha256": (
            EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256
        ),
        "join_policy": TRAINING_JOIN_POLICY,
        "authority_flags": dict(AUTHORITY_FLAGS),
    })).hexdigest()


EXPECTED_PARENT_IDENTITY_SHA256 = (
    "1ec3df0b5c1a428cf92b1427929acb0c80e04143b90166fdd2e74da8516b8fec"
)
EXPECTED_STAGE_REGISTRY_SHA256 = (
    "3125b6673b30a6706d9f03e335ae79ebca65a9a6c4b291504a7e5ae92a36d69b"
)
EXPECTED_STAGE_CONTRACT_SHA256 = (
    "a7d81fe1a316152cde10f10f488a1a3a7c455b676bcf7f55070fd87fd12dcd09"
)
EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256 = (
    "7aadf488db412a7233ffa2a885545c78eca2e6f5a9201e643215e348f42d025b"
)


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


def validate_training_sidecar_contract() -> str:
    _, _, stage_contract = validate_uefa_stage_contract()
    actual = calculate_training_sidecar_contract_sha256(stage_contract)
    if actual != EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256:
        raise UEFAStageError("UEFA training-sidecar contract drift")
    return actual


def _norm(value: Any) -> str:
    if type(value) is not str:
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def season_start_year(season: Any) -> int | None:
    if type(season) is not str:
        return None
    match = re.fullmatch(r"\s*(\d{4})(?:[-/]\d{2,4})?\s*", season)
    return int(match.group(1)) if match else None


def stage_allowed_in_era(
    competition: str,
    stage: UEFACompetitionStage,
    season: Any,
) -> bool:
    if stage is UEFACompetitionStage.UNKNOWN:
        return True
    year = season_start_year(season)
    era = ERA_REGISTRY.get(competition, {}).get(stage.value)
    return bool(
        year is not None
        and era is not None
        and year >= era[0]
        and (era[1] is None or year <= era[1])
    )


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
    normalized = _norm(label)
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
    if normalized in exact:
        return exact[normalized]
    if normalized.startswith("league matchday "):
        year = season_start_year(season)
        return (
            UEFACompetitionStage.LEAGUE_PHASE
            if year is not None and year >= 2024
            else UEFACompetitionStage.UNKNOWN
        )
    if normalized.startswith("group "):
        return UEFACompetitionStage.GROUP_PHASE
    for prefix, stage in (
        ("round of 32 ", UEFACompetitionStage.ROUND_OF_32),
        ("round of 16 ", UEFACompetitionStage.ROUND_OF_16),
        ("quarter final ", UEFACompetitionStage.QUARTER_FINAL),
        ("semi final ", UEFACompetitionStage.SEMI_FINAL),
    ):
        if normalized.startswith(prefix):
            return stage
    return UEFACompetitionStage.UNKNOWN


def _path_stage(
    competition: str,
    label: str,
    path: str | None,
    season: str,
) -> UEFACompetitionStage:
    if not path:
        return UEFACompetitionStage.UNKNOWN
    name = Path(path).name.casefold()
    normalized = _norm(label)
    if QUALIFIER_FILES.get(name) == competition:
        if normalized in {
            "1 round", "first round", "qualifying round 1", "qualifying r1",
        }:
            return UEFACompetitionStage.QUALIFYING_R1
        if normalized in {
            "2 round", "second round", "qualifying round 2", "qualifying r2",
        }:
            return UEFACompetitionStage.QUALIFYING_R2
        if normalized in {
            "3 round", "third round", "qualifying round 3", "qualifying r3",
        }:
            return UEFACompetitionStage.QUALIFYING_R3
        if normalized in {
            "play offs", "play off", "playoffs", "playoff",
            "qualifying play offs", "qualifying playoff",
        }:
            return UEFACompetitionStage.QUALIFYING_PLAYOFF
    if (
        MAIN_FILES.get(name) == competition
        and normalized in {"play offs", "play off", "playoffs", "playoff"}
    ):
        year = season_start_year(season)
        if year is not None and year >= 2024:
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
        raise UEFAStageError(
            "evidence is issued only from canonical warehouse replay"
        )

    @classmethod
    def _issue(cls, **values: Any) -> "UEFAStageEvidence":
        obj = object.__new__(cls)
        for name in cls.__dataclass_fields__:
            object.__setattr__(obj, name, values[name])
        return obj

    def identity_payload(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


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
        raise UEFAStageError(
            "projection is issued only from canonical warehouse replay"
        )

    @classmethod
    def _issue(cls, **values: Any) -> "UEFAStageProjection":
        obj = object.__new__(cls)
        for name in cls.__dataclass_fields__:
            object.__setattr__(obj, name, values[name])
        return obj

    def stable_dict(self) -> dict[str, Any]:
        out = {
            name: (
                getattr(self, name).value
                if isinstance(getattr(self, name), Enum)
                else getattr(self, name)
            )
            for name in self.__dataclass_fields__
        }
        out["authority_flags"] = dict(AUTHORITY_FLAGS)
        return out


@dataclass(frozen=True)
class _PriorLegEvidence:
    evidence: UEFAStageEvidence
    home_score_ft: int
    away_score_ft: int
    score_source: str

    def identity_payload(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence.identity_payload(),
            "home_score_ft": self.home_score_ft,
            "away_score_ft": self.away_score_ft,
            "score_source": self.score_source,
        }


def _companions(path: Path, label: str) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        companion = Path(str(path) + suffix)
        if companion.exists():
            raise UEFAStageError(
                f"{label} has active SQLite companion {suffix}"
            )


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _field_source(
    db: sqlite3.Connection,
    match_key: str,
    field: str,
) -> str | None:
    row = db.execute(
        "SELECT source_key FROM warehouse_field_provenance "
        "WHERE match_key=? AND field_name=?",
        (match_key, field),
    ).fetchone()
    return str(row[0]) if row else None


def _primary_stage_source(evidence: UEFAStageEvidence) -> str | None:
    return evidence.stage_source or evidence.round_source


def _source_lineage_is_reviewed(
    source_key: str | None,
    source_rows: list[sqlite3.Row],
) -> bool:
    if source_key not in REVIEWED_STAGE_SOURCES or len(source_rows) != 1:
        return False
    row = source_rows[0]
    source_match_id = row["source_match_id"]
    source_url = row["source_url"]
    if type(source_match_id) is not str or not source_match_id.strip():
        return False
    if type(source_url) is not str:
        return False
    return (
        source_url.startswith(OPENFOOTBALL_URL_PREFIX)
        and source_url.endswith(OPENFOOTBALL_URL_SUFFIX)
    )


def _load(
    db: sqlite3.Connection,
    match_key: str,
    warehouse_sha: str,
) -> UEFAStageEvidence:
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT match_key,competition_key,season,match_date,home_team,"
        "away_team,stage,round_name,extra_json FROM warehouse_matches "
        "WHERE match_key=?",
        (match_key,),
    ).fetchone()
    if row is None or row["competition_key"] not in PARENTS:
        raise UEFAStageError(
            "match is absent or not a reviewed UEFA parent"
        )
    for field in (
        "match_key", "season", "match_date", "home_team", "away_team",
    ):
        if type(row[field]) is not str or not row[field]:
            raise UEFAStageError(f"UEFA row missing exact {field}")
    stage_source = _field_source(db, match_key, "stage")
    round_source = _field_source(db, match_key, "round_name")
    extra_source = _field_source(db, match_key, "extra_json")
    source_key = stage_source or round_source
    source_rows: list[sqlite3.Row] = []
    if source_key:
        source_rows = db.execute(
            "SELECT source_match_id,source_url,payload_sha256 "
            "FROM warehouse_match_sources "
            "WHERE match_key=? AND source_key=?",
            (match_key, source_key),
        ).fetchall()
    source = source_rows[0] if len(source_rows) == 1 else None
    path = (
        _source_path(row["extra_json"])
        if source_key == extra_source == "openfootball"
        else None
    )
    return UEFAStageEvidence._issue(
        match_key=row["match_key"],
        competition_key=row["competition_key"],
        season=row["season"],
        match_date=row["match_date"],
        home_team=row["home_team"],
        away_team=row["away_team"],
        raw_stage=(
            row["stage"] if type(row["stage"]) is str else None
        ),
        raw_round_name=(
            row["round_name"]
            if type(row["round_name"]) is str
            else None
        ),
        stage_source=stage_source,
        round_source=round_source,
        extra_source=extra_source,
        source_path=path,
        source_match_id=(
            str(source["source_match_id"])
            if source is not None
            and source["source_match_id"] is not None
            else None
        ),
        source_url=(
            str(source["source_url"])
            if source is not None
            and source["source_url"] is not None
            else None
        ),
        source_payload_sha256=(
            str(source["payload_sha256"])
            if source is not None
            and source["payload_sha256"] is not None
            else None
        ),
        source_lineage_resolved=_source_lineage_is_reviewed(
            source_key, source_rows
        ),
        warehouse_sha256=warehouse_sha,
    )


def _derive_stage(
    evidence: UEFAStageEvidence,
) -> tuple[UEFACompetitionStage, str | None]:
    if (
        evidence.stage_source
        and evidence.round_source
        and evidence.stage_source != evidence.round_source
    ):
        return (
            UEFACompetitionStage.UNKNOWN,
            "STAGE_ROUND_SOURCE_CONFLICT",
        )
    source_key = _primary_stage_source(evidence)
    if source_key is None:
        for label, field_name in (
            (evidence.raw_stage, "STAGE"),
            (evidence.raw_round_name, "ROUND"),
        ):
            if label:
                return (
                    UEFACompetitionStage.UNKNOWN,
                    f"{field_name}_FIELD_HAS_NO_SOURCE_PROVENANCE",
                )
        return UEFACompetitionStage.UNKNOWN, "UNMAPPED_OR_AMBIGUOUS_STAGE"
    if source_key not in REVIEWED_STAGE_SOURCES:
        return UEFACompetitionStage.UNKNOWN, "UNREVIEWED_STAGE_SOURCE"
    if not evidence.source_lineage_resolved:
        return (
            UEFACompetitionStage.UNKNOWN,
            "STAGE_SOURCE_LINEAGE_NOT_UNIQUE_OR_UNREVIEWED",
        )
    for label, source, field_name in (
        (evidence.raw_stage, evidence.stage_source, "STAGE"),
        (evidence.raw_round_name, evidence.round_source, "ROUND"),
    ):
        if not label:
            continue
        if not source:
            return (
                UEFACompetitionStage.UNKNOWN,
                f"{field_name}_FIELD_HAS_NO_SOURCE_PROVENANCE",
            )
        if source not in REVIEWED_STAGE_SOURCES:
            return UEFACompetitionStage.UNKNOWN, "UNREVIEWED_STAGE_SOURCE"
        stage = _explicit(label, evidence.season)
        if (
            stage is UEFACompetitionStage.UNKNOWN
            and field_name == "STAGE"
        ):
            stage = _path_stage(
                evidence.competition_key,
                label,
                evidence.source_path,
                evidence.season,
            )
            if (
                stage is not UEFACompetitionStage.UNKNOWN
                and not (
                    evidence.stage_source
                    == evidence.extra_source
                    == "openfootball"
                )
            ):
                return (
                    UEFACompetitionStage.UNKNOWN,
                    "PATH_CONTEXT_NOT_SAME_SOURCE",
                )
        if stage is not UEFACompetitionStage.UNKNOWN:
            if stage_allowed_in_era(
                evidence.competition_key, stage, evidence.season
            ):
                return stage, None
            return (
                UEFACompetitionStage.UNKNOWN,
                "STAGE_NOT_ALLOWED_IN_COMPETITION_ERA",
            )
    return UEFACompetitionStage.UNKNOWN, "UNMAPPED_OR_AMBIGUOUS_STAGE"


def _prior_leg(
    db: sqlite3.Connection,
    evidence: UEFAStageEvidence,
    current_stage: UEFACompetitionStage,
    warehouse_sha: str,
) -> _PriorLegEvidence | None:
    current_source = _primary_stage_source(evidence)
    if current_source not in REVIEWED_STAGE_SOURCES:
        return None
    candidates = db.execute(
        """
        SELECT match_key
        FROM warehouse_matches
        WHERE competition_key=? AND season=? AND match_date<?
          AND home_team=? AND away_team=?
        ORDER BY match_date,match_key
        """,
        (
            evidence.competition_key,
            evidence.season,
            evidence.match_date,
            evidence.away_team,
            evidence.home_team,
        ),
    ).fetchall()
    qualified: list[_PriorLegEvidence] = []
    for candidate in candidates:
        prior = _load(db, str(candidate["match_key"]), warehouse_sha)
        prior_stage, blocker = _derive_stage(prior)
        if blocker is not None or prior_stage is not current_stage:
            continue
        prior_source = _primary_stage_source(prior)
        if prior_source != current_source:
            continue
        score_row = db.execute(
            "SELECT home_score_ft,away_score_ft FROM warehouse_matches "
            "WHERE match_key=?",
            (prior.match_key,),
        ).fetchone()
        if (
            score_row is None
            or type(score_row["home_score_ft"]) is not int
            or type(score_row["away_score_ft"]) is not int
            or score_row["home_score_ft"] < 0
            or score_row["away_score_ft"] < 0
        ):
            continue
        home_source = _field_source(
            db, prior.match_key, "home_score_ft"
        )
        away_source = _field_source(
            db, prior.match_key, "away_score_ft"
        )
        if not (
            home_source == away_source == prior_source
            and prior_source in REVIEWED_STAGE_SOURCES
        ):
            continue
        qualified.append(_PriorLegEvidence(
            evidence=prior,
            home_score_ft=int(score_row["home_score_ft"]),
            away_score_ft=int(score_row["away_score_ft"]),
            score_source=prior_source,
        ))
    return qualified[0] if len(qualified) == 1 else None


def _source_identity(
    evidence: UEFAStageEvidence,
    prior: _PriorLegEvidence | None = None,
) -> str:
    payload: dict[str, Any] = {
        "current": evidence.identity_payload()
    }
    if prior is not None:
        payload["prior_leg_ancestry"] = prior.identity_payload()
    return hashlib.sha256(_canon(payload)).hexdigest()


def _final_is_reviewed_single_match(
    evidence: UEFAStageEvidence,
) -> bool:
    if evidence.competition_key != "uefa_uel":
        return True
    year = season_start_year(evidence.season)
    if year is None:
        return False
    # UEFA Cup finals through 1996-97 were played over two legs.
    return year >= 1997


def _project(
    db: sqlite3.Connection,
    evidence: UEFAStageEvidence,
) -> UEFAStageProjection:
    _, _, contract = validate_uefa_stage_contract()
    stage, blocker = _derive_stage(evidence)
    identity = _source_identity(evidence)
    if stage is UEFACompetitionStage.UNKNOWN:
        return UEFAStageProjection._issue(
            match_key=evidence.match_key,
            competition_key=evidence.competition_key,
            competition_stage=stage,
            tie_format=UEFATieFormat.UNKNOWN,
            leg_number=None,
            aggregate_home=None,
            aggregate_away=None,
            qualification_state=UEFAQualificationState.UNKNOWN,
            extra_time_possible=None,
            penalties_possible=None,
            stage_source_identity=identity,
            stage_contract_sha256=contract,
            warehouse_sha256=evidence.warehouse_sha256,
            stage_authorized=False,
            blocker=blocker,
        )

    tie = UEFATieFormat.UNKNOWN
    extra: bool | None = None
    penalties: bool | None = None
    leg: int | None = None
    aggregate_home: int | None = None
    aggregate_away: int | None = None
    qualification_state = UEFAQualificationState.UNKNOWN

    if stage in {
        UEFACompetitionStage.GROUP_PHASE,
        UEFACompetitionStage.LEAGUE_PHASE,
    }:
        tie = UEFATieFormat.LEAGUE
        extra = False
        penalties = False
    elif (
        stage is UEFACompetitionStage.FINAL
        and _final_is_reviewed_single_match(evidence)
    ):
        tie = UEFATieFormat.SINGLE_MATCH
        extra = True
        penalties = True
    elif stage in KNOCKOUT:
        prior = _prior_leg(
            db, evidence, stage, evidence.warehouse_sha256
        )
        if prior is not None:
            aggregate_home = prior.away_score_ft
            aggregate_away = prior.home_score_ft
            if aggregate_home > aggregate_away:
                qualification_state = (
                    UEFAQualificationState.HOME_ADVANTAGE
                )
            elif aggregate_away > aggregate_home:
                qualification_state = (
                    UEFAQualificationState.AWAY_ADVANTAGE
                )
            else:
                year = season_start_year(evidence.season)
                if (
                    year is not None
                    and year <= 2020
                    and aggregate_home > 0
                ):
                    qualification_state = (
                        UEFAQualificationState.HOME_ADVANTAGE
                    )
                else:
                    qualification_state = UEFAQualificationState.LEVEL
            tie = UEFATieFormat.TWO_LEG
            leg = 2
            extra = True
            penalties = True
            identity = _source_identity(evidence, prior)

    return UEFAStageProjection._issue(
        match_key=evidence.match_key,
        competition_key=evidence.competition_key,
        competition_stage=stage,
        tie_format=tie,
        leg_number=leg,
        aggregate_home=aggregate_home,
        aggregate_away=aggregate_away,
        qualification_state=qualification_state,
        extra_time_possible=extra,
        penalties_possible=penalties,
        stage_source_identity=identity,
        stage_contract_sha256=contract,
        warehouse_sha256=evidence.warehouse_sha256,
        stage_authorized=True,
        blocker=None,
    )


def _validated_warehouse(path: Path):
    try:
        from domain.historical_asof_features import ReadOnlyHistoricalWarehouse
        source = ReadOnlyHistoricalWarehouse(path)
    except Exception as exc:
        if exc.__class__.__name__ == "HistoricalAsOfError":
            raise UEFAStageError(
                f"historical warehouse validation failed: {exc}"
            ) from exc
        raise
    if source.schema_sql_sha256 != EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256:
        source.close()
        raise UEFAStageError(
            "historical warehouse schema SQL identity mismatch"
        )
    return source


def project_warehouse_uefa_stages(
    warehouse_path: Path,
) -> tuple[UEFAStageProjection, ...]:
    path = Path(warehouse_path).resolve()
    if not path.is_file():
        raise UEFAStageError("historical warehouse does not exist")
    _companions(path, "historical warehouse")
    source = _validated_warehouse(path)
    try:
        db = source.connection
        db.row_factory = sqlite3.Row
        keys = [
            row[0]
            for row in db.execute(
                "SELECT match_key FROM warehouse_matches "
                "WHERE competition_key IN "
                "('uefa_ucl','uefa_uel','uefa_uecl') "
                "ORDER BY match_date,match_key"
            )
        ]
        projections = tuple(
            _project(db, _load(db, key, source.sha256))
            for key in keys
        )
        source.assert_unchanged()
        return projections
    finally:
        source.close()


def stage_coverage_report(
    projections: Iterable[UEFAStageProjection],
) -> dict[str, Any]:
    rows = tuple(projections)
    authorized = sum(row.stage_authorized for row in rows)
    by_competition: dict[str, dict[str, int]] = {}
    by_stage: dict[str, int] = {}
    blockers: dict[str, int] = {}
    for row in rows:
        bucket = by_competition.setdefault(
            row.competition_key,
            {"total": 0, "authorized": 0, "unknown": 0},
        )
        bucket["total"] += 1
        bucket[
            "authorized" if row.stage_authorized else "unknown"
        ] += 1
        by_stage[row.competition_stage.value] = (
            by_stage.get(row.competition_stage.value, 0) + 1
        )
        if row.blocker:
            blockers[row.blocker] = blockers.get(row.blocker, 0) + 1
    return {
        "dataset": DATASET,
        "schema_version": SCHEMA_VERSION,
        "stage_contract_sha256": EXPECTED_STAGE_CONTRACT_SHA256,
        "total_uefa_matches": len(rows),
        "authorized_stage_matches": authorized,
        "unknown_stage_matches": len(rows) - authorized,
        "coverage_fraction": (
            authorized / len(rows) if rows else None
        ),
        "by_competition": dict(sorted(by_competition.items())),
        "by_stage": dict(sorted(by_stage.items())),
        "blockers": dict(sorted(blockers.items())),
        "authority_flags": dict(AUTHORITY_FLAGS),
    }


def _read_meta(
    db: sqlite3.Connection,
    key: str,
) -> Any:
    row = db.execute(
        "SELECT value FROM corpus_meta WHERE key=?",
        (key,),
    ).fetchone()
    if row is None:
        raise UEFAStageError(
            f"Goal/Score training view lacks metadata {key}"
        )
    try:
        return json.loads(row[0])
    except (TypeError, json.JSONDecodeError) as exc:
        raise UEFAStageError(
            f"Goal/Score training metadata {key} is malformed"
        ) from exc


def _validate_training_view(
    training_path: Path,
    warehouse_sha: str,
) -> set[str]:
    try:
        from domain.goal_score_training_view import (
            TRAINING_VIEW_DATASET,
            TRAINING_VIEW_SCHEMA_VERSION,
            validate_training_view_contract,
        )
        (
            feature_sha,
            model_sha,
            evaluation_sha,
            training_contract_sha,
        ) = validate_training_view_contract()
    except Exception as exc:
        raise UEFAStageError(
            f"Goal/Score training-view contract validation failed: {exc}"
        ) from exc

    if (
        training_contract_sha
        != EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256
    ):
        raise UEFAStageError(
            "Goal/Score training-view contract identity mismatch"
        )
    db = sqlite3.connect(
        f"{training_path.as_uri()}?mode=ro", uri=True
    )
    try:
        objects = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }
        if not {"corpus_meta", "training_rows"} <= objects:
            raise UEFAStageError(
                "Goal/Score training view schema is unsupported"
            )
        columns = {
            row[1]
            for row in db.execute(
                "PRAGMA table_info(training_rows)"
            )
        }
        if not {"match_key", "competition_key"} <= columns:
            raise UEFAStageError(
                "Goal/Score training view lacks join columns"
            )
        expected_meta = {
            "dataset": TRAINING_VIEW_DATASET,
            "schema_version": TRAINING_VIEW_SCHEMA_VERSION,
            "source_warehouse_sha256": warehouse_sha,
            "goal_score_feature_registry_sha256": feature_sha,
            "goal_score_model_registry_sha256": model_sha,
            "goal_score_evaluation_contract_sha256": evaluation_sha,
            "training_view_generation_contract_sha256": (
                training_contract_sha
            ),
        }
        for key, expected in expected_meta.items():
            actual = _read_meta(db, key)
            if actual != expected:
                raise UEFAStageError(
                    f"Goal/Score training metadata mismatch for {key}"
                )
        return {
            str(row[0])
            for row in db.execute(
                "SELECT match_key FROM training_rows "
                "WHERE competition_key IN "
                "('uefa_ucl','uefa_uel','uefa_uecl')"
            )
        }
    finally:
        db.close()


def project_training_view_uefa_stages(
    training_view_path: Path,
    warehouse_path: Path,
) -> tuple[UEFAStageProjection, ...]:
    training = Path(training_view_path).resolve()
    warehouse = Path(warehouse_path).resolve()
    if not training.is_file() or not warehouse.is_file():
        raise UEFAStageError(
            "training view or historical warehouse does not exist"
        )
    _companions(training, "Goal/Score training view")
    _companions(warehouse, "historical warehouse")
    validate_training_sidecar_contract()

    source = _validated_warehouse(warehouse)
    try:
        warehouse_sha = source.sha256
        source.assert_unchanged()
    finally:
        source.close()

    keys = _validate_training_view(training, warehouse_sha)
    projected = {
        row.match_key: row
        for row in project_warehouse_uefa_stages(warehouse)
    }
    if keys - projected.keys():
        raise UEFAStageError(
            "UEFA training rows missing from stage projection"
        )
    return tuple(projected[key] for key in sorted(keys))


def training_view_stage_join_report(
    training_view_path: Path,
    warehouse_path: Path,
) -> dict[str, Any]:
    warehouse = Path(warehouse_path).resolve()
    rows = project_training_view_uefa_stages(
        training_view_path, warehouse
    )
    report = stage_coverage_report(rows)
    report.update({
        "join_policy": TRAINING_JOIN_POLICY,
        "training_sidecar_contract_sha256": (
            EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256
        ),
        "goal_score_training_view_contract_sha256": (
            EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256
        ),
        "source_warehouse_sha256": _sha(warehouse),
        "uefa_training_rows": len(rows),
    })
    return report


__all__ = [
    "AUTHORITY_FLAGS",
    "AWAY_GOALS_POLICY",
    "DATASET",
    "ERA_POLICY",
    "ERA_REGISTRY",
    "EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256",
    "EXPECTED_PARENT_IDENTITY_SHA256",
    "EXPECTED_STAGE_CONTRACT_SHA256",
    "EXPECTED_STAGE_REGISTRY_SHA256",
    "EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256",
    "EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256",
    "FINAL_FORMAT_POLICY",
    "PARENTS",
    "QUALIFIER_POLICY",
    "REGISTRY_VERSION",
    "REVIEWED_STAGE_SOURCES",
    "SCHEMA_VERSION",
    "SOURCE_POLICY",
    "TIE_POLICY",
    "TRAINING_JOIN_POLICY",
    "UEFACompetitionStage",
    "UEFAQualificationState",
    "UEFAStageError",
    "UEFAStageEvidence",
    "UEFAStageProjection",
    "UEFATieFormat",
    "calculate_parent_identity_sha256",
    "calculate_stage_contract_sha256",
    "calculate_stage_registry_sha256",
    "calculate_training_sidecar_contract_sha256",
    "project_training_view_uefa_stages",
    "project_warehouse_uefa_stages",
    "season_start_year",
    "stage_allowed_in_era",
    "stage_coverage_report",
    "training_view_stage_join_report",
    "validate_training_sidecar_contract",
    "validate_uefa_stage_contract",
]
