"""Exact real FotMob player-context semantic admission for FOTMOB:5795367.

Consumes only the exact successful PR #192 artifact.  It authorizes a narrow
set of semantics for that one observation and grants no model/pricing/BET
authority.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import math
import re
import types
from typing import Any, Mapping

from domain.fotmob_reviewed_match_details_persisted_evidence import (
    canonical_persisted_match_details_evidence_receipt_bytes,
    verify_persisted_match_details_evidence,
)
from domain.fotmob_reviewed_match_details_structure import (
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)
from domain.fotmob_team_strength_fixture_intelligence import LineupState, TeamSide

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-real-player-context-array-admission-v1"
REVIEW_SCOPE = "EXACT_PR192_OBSERVATION_FOTMOB_5795367_ONLY"
SOURCE_REPOSITORY_HEAD_SHA = "46f76e8033d3d498131c6f893111b437b6b459a9"
SOURCE_WORKFLOW_RUN_ID = 32410775191
SOURCE_ARTIFACT_ID = 9422055017
SOURCE_ARTIFACT_NAME = "fotmob-prospective-player-context-evidence"
SOURCE_ARTIFACT_SIZE = 974969
SOURCE_ARTIFACT_DIGEST = "sha256:db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5"
FIXTURE_IDENTIFIER = "FOTMOB:5795367"
SOURCE_MATCH_ID = "5795367"
HOME_TEAM_ID, HOME_TEAM_NAME = 10203, "Nottingham Forest"
AWAY_TEAM_ID, AWAY_TEAM_NAME = 8463, "Leeds United"
KICKOFF = dt.datetime(2026, 8, 22, 14, 0, tzinfo=dt.timezone.utc)
OBSERVED_AT = dt.datetime(2026, 8, 20, 19, 50, 47, 714266, tzinfo=dt.timezone.utc)
REVIEWED_AT = dt.datetime(2026, 8, 20, 20, 24, 0, tzinfo=dt.timezone.utc)
CLASSIFIED_AT = REVIEWED_AT
STATE_FRESH_UNTIL = CLASSIFIED_AT
REVIEWER_REFERENCE = "ATHENA_PR193_EXACT_OBSERVATION_REVIEW"
CAMPAIGN_RECEIPT_SHA256 = "c90290c0f009097ca12df22e66e49c4b92f7dfcf8ea9c8647a49bea51f168e4d"
MANIFEST_SHA256 = "aa6922d7d8fed54823ff19cf691a858106146967b2bd98ae0dc9186172b4bb99"
RAW_SHA256 = "7b6fe187ae3dd175721f51be107f822a89359f8c6891854f4035b07b449a8e99"
RAW_SIZE = 46693
PERSISTED_RECEIPT_SHA256 = "a6e43fc21f0e3be310c0139746969841a21df35bad2b9c1e009535b3b1070c44"
STRUCTURE_SHA256 = "8ac7b767caedf427e32c142ed91dd71ab2bd64444513f906ab949f88f361bcea"
DISCOVERY_REPORT_SHA256 = "084201896c4d71f279044fab7b6256a11e111fc83872f20254d9d72103366f90"
_SHA = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_AUTHORITY = tuple(sorted({
    "availability_array_semantics_authorized": True,
    "exact_observation_array_semantics_authorized": True,
    "expected_starting_xi_semantics_authorized": True,
    "player_identity_authorized": True,
    "team_side_authorized": True,
    "bench_semantics_authorized": False,
    "position_semantics_authorized": False,
    "market_value_semantics_authorized": False,
    "expected_return_semantics_authorized": False,
    "source_wide_qualification_authorized": False,
    "team_strength_feature_authorized": False,
    "probability_inference_authorized": False,
    "probability_adjustment_authorized": False,
    "pricing_authorized": False,
    "selection_authorized": False,
    "production_approval_authorized": False,
    "bet_authorized": False,
}.items()))


class RealPlayerContextAdmissionError(ValueError):
    pass


class PlayerContextSetScope(str, enum.Enum):
    STARTING_XI = "TARGET_STARTING_XI"
    UNAVAILABLE = "TARGET_UNAVAILABLE"


class BenchEvidenceStatus(str, enum.Enum):
    MISSING_SOURCE_ROOT = "MISSING_SOURCE_ROOT"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact_hash(raw: Any, expected: str, label: str) -> bytes:
    if type(raw) is not bytes or not raw or _sha(raw) != expected:
        raise RealPlayerContextAdmissionError(f"{label} exact bytes/SHA mismatch")
    return raw


def _pairs(items):
    out = {}
    for key, value in items:
        if type(key) is not str or key in out:
            raise RealPlayerContextAdmissionError("duplicate/invalid JSON key")
        out[key] = value
    return out


def _json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda v: (_ for _ in ()).throw(
                RealPlayerContextAdmissionError(f"{label}: non-finite JSON {v}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RealPlayerContextAdmissionError(f"{label} is not strict UTF-8 JSON") from exc


def _int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise RealPlayerContextAdmissionError(f"{label} must be positive int")
    return value


def _opt_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise RealPlayerContextAdmissionError(f"{label} must be nonnegative int/null")
    return value


def _opt_num(value: Any, label: str) -> int | float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise RealPlayerContextAdmissionError(f"{label} must be finite number/null")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RealPlayerContextAdmissionError(f"{label} must be exact trimmed text")
    return value


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


@dataclasses.dataclass(frozen=True)
class ReviewedRealPlayerRecord:
    scope: PlayerContextSetScope
    team_side: TeamSide
    source_team_id: int
    provider_player_id: int
    source_position_id: int | None
    source_usual_playing_position_id: int | None
    source_market_value: int | float | None
    unavailability_type: str | None
    source_record_pointer: str
    evidence_sha256: str

    def __post_init__(self):
        if type(self.scope) is not PlayerContextSetScope or type(self.team_side) is not TeamSide:
            raise RealPlayerContextAdmissionError("record enum drift")
        _int(self.source_team_id, "source_team_id"); _int(self.provider_player_id, "provider_player_id")
        _opt_int(self.source_position_id, "source_position_id")
        _opt_int(self.source_usual_playing_position_id, "source_usual_playing_position_id")
        _opt_num(self.source_market_value, "source_market_value")
        if self.unavailability_type is not None: _text(self.unavailability_type, "unavailability_type")
        if self.scope is PlayerContextSetScope.STARTING_XI and self.unavailability_type is not None:
            raise RealPlayerContextAdmissionError("starter cannot carry unavailable semantic")
        if self.scope is PlayerContextSetScope.UNAVAILABLE and self.unavailability_type is None:
            raise RealPlayerContextAdmissionError("unavailable record requires reviewed type")
        _text(self.source_record_pointer, "source_record_pointer")
        if _SHA.fullmatch(self.evidence_sha256) is None:
            raise RealPlayerContextAdmissionError("record evidence SHA drift")

    def key(self): return (self.provider_player_id, self.scope.value)
    def to_dict(self):
        return dataclasses.asdict(self) | {
            "scope": self.scope.value,
            "team_side": self.team_side.value,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedRealPlayerRecordSet:
    scope: PlayerContextSetScope
    team_side: TeamSide
    source_team_id: int
    source_team_name: str
    array_root_pointer: str
    record_count: int
    provider_player_ids: tuple[int, ...]
    completeness_attested: bool
    lineup_state: LineupState | None
    state_fresh_until: dt.datetime
    evidence_sha256: str

    def __post_init__(self):
        if type(self.scope) is not PlayerContextSetScope or type(self.team_side) is not TeamSide:
            raise RealPlayerContextAdmissionError("set enum drift")
        _int(self.source_team_id, "source_team_id"); _text(self.source_team_name, "source_team_name")
        _text(self.array_root_pointer, "array_root_pointer")
        if self.provider_player_ids != tuple(sorted(set(self.provider_player_ids))):
            raise RealPlayerContextAdmissionError("set player IDs must be unique/sorted")
        if self.record_count != len(self.provider_player_ids) or self.completeness_attested is not True:
            raise RealPlayerContextAdmissionError("set count/completeness drift")
        if self.scope is PlayerContextSetScope.STARTING_XI:
            if self.record_count != 11 or self.lineup_state is not LineupState.EXPECTED:
                raise RealPlayerContextAdmissionError("predicted starting XI must be exact EXPECTED eleven")
        elif self.lineup_state is not None:
            raise RealPlayerContextAdmissionError("unavailable set cannot claim fixture lineup state")
        if self.state_fresh_until != STATE_FRESH_UNTIL:
            raise RealPlayerContextAdmissionError("state freshness drift")
        if _SHA.fullmatch(self.evidence_sha256) is None:
            raise RealPlayerContextAdmissionError("set evidence SHA drift")

    def key(self): return (self.team_side.value, self.scope.value)
    def to_dict(self):
        return {
            "scope": self.scope.value, "team_side": self.team_side.value,
            "source_team_id": self.source_team_id, "source_team_name": self.source_team_name,
            "array_root_pointer": self.array_root_pointer, "record_count": self.record_count,
            "provider_player_ids": list(self.provider_player_ids), "completeness_attested": True,
            "lineup_state": None if self.lineup_state is None else self.lineup_state.value,
            "state_fresh_until": self.state_fresh_until.isoformat().replace("+00:00", "Z"),
            "evidence_sha256": self.evidence_sha256,
        }


def _new(**values):
    obj = object.__new__(ReviewedRealFotMobPlayerContextAdmission)
    if set(values) != {f.name for f in dataclasses.fields(ReviewedRealFotMobPlayerContextAdmission)}:
        raise RealPlayerContextAdmissionError("internal admission field drift")
    for key, value in values.items(): object.__setattr__(obj, key, value)
    obj.__post_init__()
    return obj


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedRealFotMobPlayerContextAdmission:
    schema_version: int
    dataset_name: str
    review_scope: str
    source_repository_head_sha: str
    source_workflow_run_id: int
    source_artifact_id: int
    source_artifact_digest: str
    campaign_receipt_sha256: str
    manifest_sha256: str
    raw_sha256: str
    raw_size: int
    persisted_receipt_sha256: str
    structure_sha256: str
    fixture_identifier: str
    source_match_id: str
    kickoff: dt.datetime
    observed_at: dt.datetime
    reviewed_at: dt.datetime
    classified_at: dt.datetime
    reviewer_reference: str
    source_lineup_type: str
    source_lineup_provider: str
    record_sets: tuple[ReviewedRealPlayerRecordSet, ...]
    records: tuple[ReviewedRealPlayerRecord, ...]
    bench_evidence_status: Mapping[str, str]
    authority: Mapping[str, bool]

    def __init__(self, *_, **__):
        raise RealPlayerContextAdmissionError("authoritative wrapper only from exact PR192 replay")

    def __post_init__(self):
        if (self.schema_version, self.dataset_name, self.review_scope) != (SCHEMA_VERSION, DATASET_NAME, REVIEW_SCOPE):
            raise RealPlayerContextAdmissionError("admission identity drift")
        frozen = (
            self.source_repository_head_sha == SOURCE_REPOSITORY_HEAD_SHA
            and self.source_workflow_run_id == SOURCE_WORKFLOW_RUN_ID
            and self.source_artifact_id == SOURCE_ARTIFACT_ID
            and self.source_artifact_digest == SOURCE_ARTIFACT_DIGEST
            and self.campaign_receipt_sha256 == CAMPAIGN_RECEIPT_SHA256
            and self.manifest_sha256 == MANIFEST_SHA256 and self.raw_sha256 == RAW_SHA256
            and self.raw_size == RAW_SIZE and self.persisted_receipt_sha256 == PERSISTED_RECEIPT_SHA256
            and self.structure_sha256 == STRUCTURE_SHA256 and self.fixture_identifier == FIXTURE_IDENTIFIER
            and self.source_match_id == SOURCE_MATCH_ID and self.kickoff == KICKOFF
            and self.observed_at == OBSERVED_AT and self.reviewed_at == REVIEWED_AT
            and self.classified_at == CLASSIFIED_AT and self.reviewer_reference == REVIEWER_REFERENCE
            and self.source_lineup_type == "predicted" and self.source_lineup_provider == "enetpulse"
        )
        if not frozen: raise RealPlayerContextAdmissionError("frozen source/review identity drift")
        if self.record_sets != tuple(sorted(self.record_sets, key=lambda x: x.key())):
            raise RealPlayerContextAdmissionError("record-set ordering drift")
        if self.records != tuple(sorted(self.records, key=lambda x: x.key())):
            raise RealPlayerContextAdmissionError("record ordering drift")
        if len({x.provider_player_id for x in self.records}) != len(self.records):
            raise RealPlayerContextAdmissionError("provider player identity must be fixture-global unique")
        expected = {(TeamSide.HOME, PlayerContextSetScope.STARTING_XI),
                    (TeamSide.AWAY, PlayerContextSetScope.STARTING_XI),
                    (TeamSide.HOME, PlayerContextSetScope.UNAVAILABLE),
                    (TeamSide.AWAY, PlayerContextSetScope.UNAVAILABLE)}
        if {(x.team_side, x.scope) for x in self.record_sets} != expected:
            raise RealPlayerContextAdmissionError("reviewed set coverage drift")
        if dict(self.bench_evidence_status) != {"HOME": "MISSING_SOURCE_ROOT", "AWAY": "MISSING_SOURCE_ROOT"}:
            raise RealPlayerContextAdmissionError("bench evidence status drift")
        if tuple(self.authority.items()) != _AUTHORITY:
            raise RealPlayerContextAdmissionError("authority drift")

    def to_dict(self):
        iso = lambda x: x.isoformat().replace("+00:00", "Z")
        return {
            "schema_version": self.schema_version, "dataset_name": self.dataset_name,
            "review_scope": self.review_scope, "source_repository_head_sha": self.source_repository_head_sha,
            "source_workflow_run_id": self.source_workflow_run_id, "source_artifact_id": self.source_artifact_id,
            "source_artifact_digest": self.source_artifact_digest, "campaign_receipt_sha256": self.campaign_receipt_sha256,
            "manifest_sha256": self.manifest_sha256, "raw_sha256": self.raw_sha256, "raw_size": self.raw_size,
            "persisted_receipt_sha256": self.persisted_receipt_sha256, "structure_sha256": self.structure_sha256,
            "fixture_identifier": self.fixture_identifier, "source_match_id": self.source_match_id,
            "kickoff": iso(self.kickoff), "observed_at": iso(self.observed_at), "reviewed_at": iso(self.reviewed_at),
            "classified_at": iso(self.classified_at), "reviewer_reference": self.reviewer_reference,
            "source_lineup_type": self.source_lineup_type, "source_lineup_provider": self.source_lineup_provider,
            "record_sets": [x.to_dict() for x in self.record_sets], "records": [x.to_dict() for x in self.records],
            "bench_evidence_status": dict(self.bench_evidence_status), "authority": dict(self.authority),
        }


def _evidence(payload):
    return _sha(_canonical(payload))


def _campaign(raw: bytes):
    payload = _json(_exact_hash(raw, CAMPAIGN_RECEIPT_SHA256, "campaign receipt"), "campaign receipt")
    expected = {
        "campaign_result": "SUCCESS_PROSPECTIVE_PLAYER_CONTEXT_EVIDENCE_CAPTURED",
        "repository_head_sha": SOURCE_REPOSITORY_HEAD_SHA,
        "workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "resolved_fixture_identifier": FIXTURE_IDENTIFIER,
        "resolved_source_match_id": SOURCE_MATCH_ID,
        "match_details_raw_sha256": RAW_SHA256,
        "match_details_raw_size": RAW_SIZE,
        "match_details_manifest_sha256": MANIFEST_SHA256,
        "persisted_evidence_receipt_sha256": PERSISTED_RECEIPT_SHA256,
        "structure_assessment_sha256": STRUCTURE_SHA256,
        "player_context_report_sha256": DISCOVERY_REPORT_SHA256,
    }
    if type(payload) is not dict or any(payload.get(k) != v for k, v in expected.items()):
        raise RealPlayerContextAdmissionError("campaign receipt lineage mismatch")


def build_reviewed_real_fotmob_player_context_admission(
    *, campaign_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    persisted_receipt_bytes: Any, structure_assessment_bytes: Any,
) -> ReviewedRealFotMobPlayerContextAdmission:
    _campaign(campaign_receipt_bytes)
    manifest_bytes = _exact_hash(manifest_bytes, MANIFEST_SHA256, "manifest")
    raw_bytes = _exact_hash(raw_bytes, RAW_SHA256, "raw response")
    if len(raw_bytes) != RAW_SIZE: raise RealPlayerContextAdmissionError("raw size mismatch")
    persisted_receipt_bytes = _exact_hash(persisted_receipt_bytes, PERSISTED_RECEIPT_SHA256, "persisted receipt")
    structure_assessment_bytes = _exact_hash(structure_assessment_bytes, STRUCTURE_SHA256, "structure assessment")
    try:
        evidence = verify_persisted_match_details_evidence(manifest_bytes=manifest_bytes, raw_bytes=raw_bytes)
        exact_receipt = canonical_persisted_match_details_evidence_receipt_bytes(evidence)
        if exact_receipt != persisted_receipt_bytes: raise RealPlayerContextAdmissionError("PR52 replay mismatch")
        structure = assess_reviewed_match_details_structure(
            evidence=evidence, evidence_receipt_bytes=exact_receipt,
            manifest_bytes=manifest_bytes, raw_bytes=raw_bytes,
        )
        if canonical_reviewed_match_details_structure_bytes(structure) != structure_assessment_bytes:
            raise RealPlayerContextAdmissionError("PR53 replay mismatch")
    except RealPlayerContextAdmissionError: raise
    except Exception as exc:
        raise RealPlayerContextAdmissionError("PR52/53 full replay failed") from exc
    if (evidence.fixture_identifier, evidence.source_match_id, evidence.kickoff,
        evidence.observed_at, evidence.raw_sha256, evidence.raw_size) != (
        FIXTURE_IDENTIFIER, SOURCE_MATCH_ID, KICKOFF, OBSERVED_AT, RAW_SHA256, RAW_SIZE):
        raise RealPlayerContextAdmissionError("persisted evidence identity drift")

    payload = _json(raw_bytes, "match-details response")
    general, content = payload.get("general"), payload.get("content")
    if type(general) is not dict or type(content) is not dict:
        raise RealPlayerContextAdmissionError("required response objects missing")
    if (general.get("matchId"), general.get("matchTimeUTCDate"), general.get("started"), general.get("finished")) != (
        int(SOURCE_MATCH_ID), "2026-08-22T14:00:00.000Z", False, False):
        raise RealPlayerContextAdmissionError("fixture state drift")
    if general.get("homeTeam") != {"name": HOME_TEAM_NAME, "id": HOME_TEAM_ID} or general.get("awayTeam") != {"name": AWAY_TEAM_NAME, "id": AWAY_TEAM_ID}:
        raise RealPlayerContextAdmissionError("HOME/AWAY identity drift")
    lineup = content.get("lineup")
    if type(lineup) is not dict or (lineup.get("matchId"), lineup.get("lineupType"), lineup.get("source")) != (int(SOURCE_MATCH_ID), "predicted", "enetpulse"):
        raise RealPlayerContextAdmissionError("lineup observation identity drift")

    expected_team_keys = {"id","name","formation","starters","coach","unavailable","averageStarterAge","totalStarterMarketValue"}
    configs = ((TeamSide.HOME, "homeTeam", HOME_TEAM_ID, HOME_TEAM_NAME, 1),
               (TeamSide.AWAY, "awayTeam", AWAY_TEAM_ID, AWAY_TEAM_NAME, 5))
    records, sets = [], []
    for side, key, team_id, team_name, unavailable_count in configs:
        team = lineup.get(key)
        if type(team) is not dict or set(team) != expected_team_keys or team.get("id") != team_id or team.get("name") != team_name:
            raise RealPlayerContextAdmissionError(f"{key} exact object/identity drift")
        for scope, raw_key, count in ((PlayerContextSetScope.STARTING_XI, "starters", 11),
                                      (PlayerContextSetScope.UNAVAILABLE, "unavailable", unavailable_count)):
            rows = team.get(raw_key)
            if type(rows) is not list or len(rows) != count:
                raise RealPlayerContextAdmissionError(f"{key}/{raw_key} cardinality drift")
            ids = []
            root = f"/content/lineup/{key}/{raw_key}"
            for index, row in enumerate(rows):
                if type(row) is not dict: raise RealPlayerContextAdmissionError("player row must be object")
                player_id = _int(row.get("id"), "provider_player_id"); ids.append(player_id)
                unavailable_type = None
                if scope is PlayerContextSetScope.UNAVAILABLE:
                    u = row.get("unavailability")
                    if type(u) is not dict or u.get("type") != "injury":
                        raise RealPlayerContextAdmissionError("exact unavailable review admits observed injury only")
                    unavailable_type = "injury"
                pointer = f"{root}/{index}"
                records.append(ReviewedRealPlayerRecord(
                    scope, side, team_id, player_id, _opt_int(row.get("positionId"), "positionId"),
                    _opt_int(row.get("usualPlayingPositionId"), "usualPlayingPositionId"),
                    _opt_num(row.get("marketValue"), "marketValue"), unavailable_type, pointer,
                    _evidence({"raw_sha256": RAW_SHA256, "scope": scope.value, "side": side.value,
                               "team_id": team_id, "player_id": player_id, "pointer": pointer}),
                ))
            identities = tuple(sorted(ids))
            if len(identities) != len(set(identities)): raise RealPlayerContextAdmissionError("duplicate player in set")
            sets.append(ReviewedRealPlayerRecordSet(
                scope, side, team_id, team_name, root, len(identities), identities, True,
                LineupState.EXPECTED if scope is PlayerContextSetScope.STARTING_XI else None,
                STATE_FRESH_UNTIL,
                _evidence({"raw_sha256": RAW_SHA256, "structure_sha256": STRUCTURE_SHA256,
                           "scope": scope.value, "side": side.value, "team_id": team_id,
                           "root": root, "player_ids": list(identities), "complete": True}),
            ))
    records = tuple(sorted(records, key=lambda x: x.key()))
    if len({x.provider_player_id for x in records}) != len(records):
        raise RealPlayerContextAdmissionError("same provider player occurs in contradictory scopes")
    return _new(
        schema_version=SCHEMA_VERSION, dataset_name=DATASET_NAME, review_scope=REVIEW_SCOPE,
        source_repository_head_sha=SOURCE_REPOSITORY_HEAD_SHA, source_workflow_run_id=SOURCE_WORKFLOW_RUN_ID,
        source_artifact_id=SOURCE_ARTIFACT_ID, source_artifact_digest=SOURCE_ARTIFACT_DIGEST,
        campaign_receipt_sha256=CAMPAIGN_RECEIPT_SHA256, manifest_sha256=MANIFEST_SHA256,
        raw_sha256=RAW_SHA256, raw_size=RAW_SIZE, persisted_receipt_sha256=PERSISTED_RECEIPT_SHA256,
        structure_sha256=STRUCTURE_SHA256, fixture_identifier=FIXTURE_IDENTIFIER, source_match_id=SOURCE_MATCH_ID,
        kickoff=KICKOFF, observed_at=OBSERVED_AT, reviewed_at=REVIEWED_AT, classified_at=CLASSIFIED_AT,
        reviewer_reference=REVIEWER_REFERENCE, source_lineup_type="predicted", source_lineup_provider="enetpulse",
        record_sets=tuple(sorted(sets, key=lambda x: x.key())), records=records,
        bench_evidence_status=types.MappingProxyType({"HOME":"MISSING_SOURCE_ROOT","AWAY":"MISSING_SOURCE_ROOT"}),
        authority=types.MappingProxyType(dict(_AUTHORITY)),
    )


def canonical_reviewed_real_fotmob_player_context_admission_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedRealFotMobPlayerContextAdmission:
        raise RealPlayerContextAdmissionError("value must be exact reviewed admission")
    value.__post_init__()
    return _canonical(value.to_dict())


def sha256_reviewed_real_fotmob_player_context_admission(value: Any) -> str:
    return _sha(canonical_reviewed_real_fotmob_player_context_admission_bytes(value))
