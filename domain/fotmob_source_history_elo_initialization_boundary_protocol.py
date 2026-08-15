"""Pre-register the reviewed FotMob source-history Elo initialization boundary.

PR #113 freezes only the evidence and state-seeding rules required to decide
whether a FotMob replay can begin with semantics equivalent to PR #69's
historical Elo replay. It does not execute qualification, materialize source
history, authorize model inputs, or change any source/model/pricing/betting
capability.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.historical_expected_goals_successor_protocol as successor_protocol
import domain.historical_model_feature_replay_candidate as pr69_replay
import domain.prospective_successor_source_history_completeness_protocol as pr81
from domain.fixture_model_features import ModelFeatureId

SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_PR69_EQUIVALENT_ELO_INITIALIZATION_BOUNDARY_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_INITIALIZATION_BOUNDARY_UNQUALIFIED"
REPOSITORY_MAIN_SHA = "4f99b482d4c3f3f1e3ef19e3134e235f1c4c7da8"

PR112_RECEIPT_SHA256 = "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
PR112_RECEIPT_SIZE = 7_980
PR112_QUALIFICATION_DOMAIN_BLOB_SHA = "2028c7e4d847ba293bc88ffc718a406853f96d11"
PR81_PROTOCOL_SHA256 = "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
PR81_PROTOCOL_SIZE = 4_223
PR69_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
PR69_CANONICAL_REPLAY_SHA256 = "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
PR69_CANONICAL_REPLAY_SIZE = 39_952_730
PR69_REPLAY_IMPLEMENTATION_BLOB_SHA = "b67a7e52954f47cc90c578ad193545c541984964"
PR69_SOURCE_FILE_COUNT = 66
PR69_SOURCE_FIXTURE_COUNT = 21_226
PR69_INITIAL_SEASON = "2020-21"
ELO_INITIALIZATION_SEMANTICS = "1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
FOTMOB_CAMPAIGN_START_DATE = "20200801"
FOTMOB_CAMPAIGN_END_DATE = "20260814"
FOTMOB_ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
FOTMOB_ARTIFACT_SIZE = 61_886_753

FROZEN_MODEL_FAMILIES = (
    ("B1", 40, "BEL"),
    ("D1", 54, "GER"),
    ("E0", 47, "ENG"),
    ("F1", 53, "FRA"),
    ("G1", 135, "GRE"),
    ("I1", 55, "ITA"),
    ("N1", 57, "NED"),
    ("P1", 61, "POR"),
    ("SC0", 64, "SCO"),
    ("SP1", 87, "ESP"),
    ("T1", 71, "TUR"),
)

PR69_SYNTHETIC_WITNESS = types.MappingProxyType(
    {
        "first_fixture": {
            "season": "2020-21",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "home_elo": 1500,
            "away_elo": 1500,
            "home_initial_state_assumption": True,
            "away_initial_state_assumption": True,
        },
        "cross_season_fixture": {
            "season": "2021-22",
            "home_team": "Alpha FC",
            "away_team": "Gamma FC",
            "home_elo": 1513,
            "away_elo": 1500,
            "home_initial_state_assumption": False,
            "away_initial_state_assumption": True,
        },
    }
)

BOUNDARY_REFERENCE_RULES = (
    "FOTMOB_CAMPAIGN_START_IS_A_COVERAGE_ENVELOPE_NOT_THE_ELO_INITIALIZATION_DATE",
    "DERIVE_ONE_REFERENCE_FLOOR_PER_FROZEN_MODEL_LEAGUE_FROM_THE_EARLIEST_SOURCE_LOCAL_FIXTURE_IN_ITS_EXACT_PR69_2020_21_SOURCE_FILE",
    "DERIVE_REFERENCE_FLOORS_FROM_EXACT_PR69_SOURCE_BYTES_ONLY_NEVER_FROM_FOTMOB_OBSERVATIONS_CURRENT_SCHEDULES_OR_POST_HOC_FIT",
    "REQUIRE_THE_FULL_PR69_66_FILE_REBUILD_TO_MATCH_THE_FROZEN_SOURCE_CORPUS_AND_CANONICAL_REPLAY_IDENTITIES_BEFORE_REFERENCE_FLOORS_ARE_TRUSTED",
    "COMPARE_THE_START_BOUNDARY_AT_SOURCE_CALENDAR_DATE_GRANULARITY_ONLY_BECAUSE_PR69_SOURCE_LOCAL_TIMEZONE_IS_UNRESOLVED",
    "PRESERVE_BUT_EXCLUDE_TARGET_FAMILY_FOTMOB_OBSERVATIONS_STRICTLY_BEFORE_THEIR_PR69_REFERENCE_FLOOR_FROM_PR69_EQUIVALENT_ELO_STATE",
    "DO_NOT_USE_PRE_2020_21_RESULTS_TO_PRESEED_RATINGS_EVEN_WHEN_THE_FOTMOB_CAPTURE_ENVELOPE_CONTAINS_THEM",
    "A_FROZEN_MODEL_LEAGUE_WITH_NO_REVIEWED_FOTMOB_RESULT_EVIDENCE_AT_OR_AFTER_ITS_REFERENCE_FLOOR_REMAINS_BLOCKED",
    "REFERENCE_FLOORS_ESTABLISH_REPLAY_START_SCOPE_ONLY_AND_DO_NOT_BY_THEMSELVES_PROVE_HISTORICAL_COMPLETENESS",
)

ELO_STATE_RULES = (
    "START_WITH_AN_EMPTY_SOURCE_SCOPED_FOTMOB_TEAM_STATE_AT_EACH_MODEL_LEAGUES_REFERENCE_FLOOR",
    "AN_UNSEEN_ADMITTED_TEAM_HAS_PREMATCH_OVERALL_HOME_AND_AWAY_RATINGS_1500_AND_MATCHES_0",
    "THE_1500_VALUE_IS_A_REPLAY_MODEL_INITIAL_STATE_ASSUMPTION_AND_NEVER_OBSERVED_SOURCE_EVIDENCE",
    "INITIALIZATION_OCCURS_PER_UNSEEN_SOURCE_TEAM_ON_FIRST_ADMITTED_FIXTURE_NOT_AS_A_PREPOPULATED_TEAM_LIST",
    "NO_PER_SEASON_RATING_RESET_IS_ALLOWED_AFTER_A_TEAM_HAS_ENTERED_THE_REPLAY",
    "A_TEAM_REAPPEARING_AFTER_AN_ABSENT_SEASON_RETAINS_ITS_PRIOR_ADMITTED_REPLAY_STATE_IF_THE_SAME_FOTMOB_TEAM_ID_CONTINUES",
    "A_NEWLY_PROMOTED_OR_OTHERWISE_NEW_FOTMOB_TEAM_ID_FIRST_APPEARING_LATER_STARTS_AT_1500_WITH_MATCHES_0",
    "ONLY_REVIEWED_RESULTS_FROM_THE_EXACT_ELEVEN_FROZEN_TOP_FLIGHT_MODEL_FAMILIES_MAY_UPDATE_THIS_PR69_EQUIVALENT_REPLAY_STATE",
    "LOWER_DIVISION_CUP_CONTINENTAL_INTERNATIONAL_FRIENDLY_AND_OTHER_COMPETITION_RESULTS_MUST_NOT_PRESEED_OR_UPDATE_THIS_REPLAY",
    "AWARDED_AFTER_EXTRA_TIME_AFTER_PENALTIES_ABANDONED_CANCELLED_AND_POSTPONED_SOURCE_STATES_MUST_NOT_UPDATE_ORDINARY_REGULATION_TIME_ELO_HISTORY",
    "A_CHRONOLOGY_QUALIFIED_LATER_ORDINARY_FT_TERMINAL_STATE_MAY_REACH_SEPARATE_HISTORY_MATERIALIZATION_REVIEW_AT_ITS_REVIEWED_LATER_KICKOFF_ONLY",
    "PREMATCH_ELO_IS_CAPTURED_BEFORE_THE_CURRENT_FIXTURES_RESULT_UPDATES_STATE_FOR_LATER_FIXTURES",
    "PR69_UPDATE_MECHANICS_REMAIN_HOME_EXPECTED_SCORE_BOOST_50_BASE10_400_K_32_LT20_24_LT50_16_OTHERWISE_AND_INTEGER_CONVERSION_AFTER_UPDATE",
    "NO_CROSS_SOURCE_TEAM_IDENTITY_OR_NUMERIC_PR69_VS_FOTMOB_ELO_EQUALITY_IS_REQUIRED_CLAIMED_OR_ALLOWED_AS_PROOF",
)

QUALIFICATION_REQUIREMENTS = (
    "USE_ONLY_THE_EXACT_PRESERVED_FOTMOB_CAMPAIGN_ARTIFACT_WITHOUT_FOTMOB_NETWORK_REACQUISITION",
    "REVALIDATE_THE_EXACT_PR112_CHRONOLOGY_QUALIFICATION_RECEIPT_FIRST",
    "REBUILD_PR69_FROM_ALL_66_EXACT_FOOTBALL_DATA_UK_SOURCE_FILES_AND_REQUIRE_THE_FROZEN_SOURCE_CORPUS_AND_CANONICAL_REPLAY_HASHES",
    "DERIVE_AND_RECORD_ALL_ELEVEN_PR69_2020_21_REFERENCE_FLOORS_BEFORE_CLASSIFYING_FOTMOB_PREBOUNDARY_OBSERVATIONS",
    "REQUIRE_THE_EXACT_ELEVEN_PR108_QUALIFIED_FOTMOB_PRIMARY_ID_FAMILIES_AND_NO_NAME_BASED_OR_WRAPPER_ID_FALLBACK",
    "PRESERVE_AND_COUNT_EVERY_TARGET_FAMILY_FOTMOB_OBSERVATION_BEFORE_EACH_REFERENCE_FLOOR_WITHOUT_ALLOWING_ANY_TO_UPDATE_ELO_STATE",
    "REQUIRE_AT_LEAST_ONE_REVIEWED_ORDINARY_FT_OR_REVIEWED_CHRONOLOGY_TERMINAL_ORDINARY_FT_CANDIDATE_ON_OR_AFTER_EACH_REFERENCE_FLOOR_BEFORE_QUALIFICATION",
    "VERIFY_EMPTY_STATE_AND_1500_MATCHES_0_SEED_SEMANTICS_WITH_THE_FROZEN_PR69_SYNTHETIC_WITNESS",
    "VERIFY_NO_SEASON_RESET_NO_PREBOUNDARY_STATE_LEAKAGE_AND_NO_OUT_OF_UNIVERSE_RESULT_UPDATE",
    "DO_NOT_REQUIRE_OR_INFER_CROSS_SOURCE_FIXTURE_OR_TEAM_IDENTITY_ALIGNMENT",
    "PRODUCE_A_DETERMINISTIC_CANONICAL_RECEIPT_WITH_REFERENCE_FLOORS_PREBOUNDARY_COUNTS_FIRST_ADMITTED_SOURCE_FIXTURE_IDS_AND_ALL_VIOLATION_COUNTS",
    "MUTATE_NO_SOURCE_CAPABILITY_COMPETITION_MODEL_PRICING_SELECTION_OR_BETTING_REGISTRY",
)

QUALIFICATION_STATUS_VOCABULARY = (
    "QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_BOUNDARY",
    "BLOCKED_PR69_EXACT_SOURCE_REBUILD_UNAVAILABLE_OR_CHANGED",
    "BLOCKED_PR69_REFERENCE_FLOOR_DERIVATION_FAILED",
    "BLOCKED_FOTMOB_MODEL_FAMILY_MAPPING_DRIFT",
    "BLOCKED_FOTMOB_PREBOUNDARY_STATE_LEAKAGE",
    "BLOCKED_FOTMOB_REFERENCE_FLOOR_RESULT_EVIDENCE_GAP",
    "BLOCKED_SEASON_RESET_OR_PRESEEDED_RATING",
    "BLOCKED_OUT_OF_UNIVERSE_ELO_UPDATE",
    "BLOCKED_TEAM_IDENTITY_CONTINUITY",
    "BLOCKED_UPSTREAM_CHRONOLOGY_OR_SPECIAL_RESULT_DISPOSITION_DRIFT",
)

NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION"

_SAFETY_KEYS = frozenset(
    {
        "initialization_boundary_proven",
        "ordinary_ft_history_rows_authorized",
        "special_result_history_rows_authorized",
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "historical_coverage_proven",
        "pr80_constructor_input_authorized",
        "successor_live_inputs_qualified",
        "successor_candidate_approved",
        "expected_goals_transform_approved",
        "expected_goals_production_authorized",
        "score_matrix_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "calibration_for_production_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "model_training_authorized",
        "bet_authorized",
        "competition_registry_mutation_authorized",
        "source_capability_registry_mutation_authorized",
    }
)

PROTOCOL_SHA256 = "61f62252c178fb2e87a1f704848dfadb19213a9dede8fd2925b5d938faf0186c"
PROTOCOL_SIZE = 8_405


class FotMobSourceHistoryEloInitializationBoundaryProtocolError(ValueError):
    """Raised when the frozen PR #113 protocol cannot be reproduced."""


def _error(message: str) -> FotMobSourceHistoryEloInitializationBoundaryProtocolError:
    return FotMobSourceHistoryEloInitializationBoundaryProtocolError(message)


def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("Elo initialization protocol serialization failed") from exc
    return (text + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _family_payloads() -> list[dict[str, Any]]:
    return [
        {"model_league_code": code, "fotmob_primary_id": primary_id, "country_code": country}
        for code, primary_id, country in FROZEN_MODEL_FAMILIES
    ]


def _protocol_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "upstream": {
            "pr112_receipt_sha256": PR112_RECEIPT_SHA256,
            "pr112_receipt_size_bytes": PR112_RECEIPT_SIZE,
            "pr112_qualification_domain_blob_sha": PR112_QUALIFICATION_DOMAIN_BLOB_SHA,
            "pr81_protocol_sha256": PR81_PROTOCOL_SHA256,
            "pr81_protocol_size_bytes": PR81_PROTOCOL_SIZE,
            "pr69_source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
            "pr69_canonical_replay_sha256": PR69_CANONICAL_REPLAY_SHA256,
            "pr69_canonical_replay_size_bytes": PR69_CANONICAL_REPLAY_SIZE,
            "pr69_replay_implementation_blob_sha": PR69_REPLAY_IMPLEMENTATION_BLOB_SHA,
            "pr69_source_file_count": PR69_SOURCE_FILE_COUNT,
            "pr69_source_fixture_count": PR69_SOURCE_FIXTURE_COUNT,
            "pr69_initial_season": PR69_INITIAL_SEASON,
            "elo_initialization_semantics": ELO_INITIALIZATION_SEMANTICS,
        },
        "fotmob_evidence_envelope": {
            "campaign_start_date": FOTMOB_CAMPAIGN_START_DATE,
            "campaign_end_date": FOTMOB_CAMPAIGN_END_DATE,
            "artifact_sha256": FOTMOB_ARTIFACT_SHA256,
            "artifact_size_bytes": FOTMOB_ARTIFACT_SIZE,
            "rearrangement_chronology_qualified_required": True,
            "historical_coverage_proven_required": False,
        },
        "frozen_model_families": _family_payloads(),
        "pr69_synthetic_witness": dict(PR69_SYNTHETIC_WITNESS),
        "boundary_reference_rules": list(BOUNDARY_REFERENCE_RULES),
        "elo_state_rules": list(ELO_STATE_RULES),
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "qualification_status_vocabulary": list(QUALIFICATION_STATUS_VOCABULARY),
        "initialization_boundary_execution_performed": False,
        "initialization_boundary_qualified": False,
        "source_history_mutation_performed": False,
        "historical_coverage_proven": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _feature_map(fixture: Any) -> dict[ModelFeatureId, Any]:
    return {item.feature_id: item for item in fixture.features}


def _verify_pr69_synthetic_witness() -> None:
    header = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\n"
    first = (
        header
        + "E0,12/09/2020,15:00,Alpha FC,Beta FC,1,0,H,1,0,H\n"
    ).encode("utf-8")
    second = (
        header
        + "E0,13/08/2021,20:00,Alpha FC,Gamma FC,0,0,D,0,0,D\n"
    ).encode("utf-8")
    corpus = pr69_replay.build_historical_model_feature_replay_corpus(
        (
            pr69_replay.HistoricalReplaySourceInput("2020-21", "E0", first),
            pr69_replay.HistoricalReplaySourceInput("2021-22", "E0", second),
        )
    )
    by_season = {fixture.season: fixture for fixture in corpus.fixtures}
    if set(by_season) != {"2020-21", "2021-22"}:
        raise _error("PR69 synthetic witness fixture seasons changed")
    first_features = _feature_map(by_season["2020-21"])
    second_features = _feature_map(by_season["2021-22"])
    first_home = first_features[ModelFeatureId.HOME_ELO]
    first_away = first_features[ModelFeatureId.AWAY_ELO]
    second_home = second_features[ModelFeatureId.HOME_ELO]
    second_away = second_features[ModelFeatureId.AWAY_ELO]
    observed = {
        "first_fixture": {
            "season": by_season["2020-21"].season,
            "home_team": by_season["2020-21"].home_team_name,
            "away_team": by_season["2020-21"].away_team_name,
            "home_elo": first_home.value,
            "away_elo": first_away.value,
            "home_initial_state_assumption": first_home.replay_initial_state_assumption,
            "away_initial_state_assumption": first_away.replay_initial_state_assumption,
        },
        "cross_season_fixture": {
            "season": by_season["2021-22"].season,
            "home_team": by_season["2021-22"].home_team_name,
            "away_team": by_season["2021-22"].away_team_name,
            "home_elo": second_home.value,
            "away_elo": second_away.value,
            "home_initial_state_assumption": second_home.replay_initial_state_assumption,
            "away_initial_state_assumption": second_away.replay_initial_state_assumption,
        },
    }
    if observed != dict(PR69_SYNTHETIC_WITNESS):
        raise _error("PR69 synthetic Elo initialization/carryover witness changed")


def _verify_upstream() -> None:
    pr112_receipt = pr112.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    pr112_raw = pr112.canonical_fotmob_source_history_rearrangement_chronology_qualification_receipt_bytes()
    if (len(pr112_raw), hashlib.sha256(pr112_raw).hexdigest()) != (
        PR112_RECEIPT_SIZE,
        PR112_RECEIPT_SHA256,
    ):
        raise _error("PR112 chronology qualification receipt identity changed")
    if pr112_receipt.get("rearrangement_chronology_qualified") is not True:
        raise _error("PR112 rearrangement chronology is no longer qualified")
    if pr112_receipt.get("historical_coverage_proven") is not False:
        raise _error("PR112 historical-coverage premise changed")
    if pr112_receipt.get("remaining_blockers") != [
        "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
        "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
    ]:
        raise _error("PR112 remaining blocker set changed")
    if pr112_receipt.get("next_required_boundary") != (
        "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_PROTOCOL"
    ):
        raise _error("PR112 next boundary changed")
    source = pr112_receipt.get("source_evidence")
    if not isinstance(source, dict) or (
        source.get("artifact_sha256"),
        source.get("artifact_size_bytes"),
    ) != (FOTMOB_ARTIFACT_SHA256, FOTMOB_ARTIFACT_SIZE):
        raise _error("PR112 preserved campaign artifact identity changed")

    pr81_value = pr81.build_prospective_successor_source_history_completeness_protocol()
    pr81_raw = pr81.canonical_prospective_successor_source_history_completeness_protocol_bytes(
        pr81_value
    )
    if (len(pr81_raw), hashlib.sha256(pr81_raw).hexdigest()) != (
        PR81_PROTOCOL_SIZE,
        PR81_PROTOCOL_SHA256,
    ):
        raise _error("PR81 source-history completeness protocol identity changed")
    if pr81.INITIALIZATION_BOUNDARY_RULE != (
        "MUST_BE_PROVEN_EQUIVALENT_TO_FROZEN_PR69_REPLAY_START_NOT_CHOSEN_AD_HOC"
    ):
        raise _error("PR81 initialization boundary rule changed")
    if tuple(pr81.FROZEN_MODEL_LEAGUE_CODES) != tuple(row[0] for row in FROZEN_MODEL_FAMILIES):
        raise _error("PR81 frozen model league universe changed")

    if successor_protocol.PR69_SOURCE_CORPUS_SHA256 != PR69_SOURCE_CORPUS_SHA256:
        raise _error("PR69 source-corpus ancestry changed")
    if successor_protocol.PR69_CANONICAL_SHA256 != PR69_CANONICAL_REPLAY_SHA256:
        raise _error("PR69 canonical replay ancestry changed")
    if successor_protocol.SOURCE_FILE_COUNT != PR69_SOURCE_FILE_COUNT:
        raise _error("PR69 source-file count changed")
    if successor_protocol.SOURCE_FIXTURE_COUNT != PR69_SOURCE_FIXTURE_COUNT:
        raise _error("PR69 source-fixture count changed")
    if tuple(successor_protocol.TRAIN_SEASONS)[0] != PR69_INITIAL_SEASON:
        raise _error("PR69 initial successor season changed")
    if successor_protocol.ELO_INITIALIZATION_SEMANTICS != ELO_INITIALIZATION_SEMANTICS:
        raise _error("PR69 Elo initialization semantics changed")

    _verify_pr69_synthetic_witness()


@dataclasses.dataclass(frozen=True)
class FotMobSourceHistoryEloInitializationBoundaryProtocol:
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if dict(self.payload) != _protocol_payload():
            raise _error("Elo initialization boundary protocol differs from frozen contract")
        safety = self.payload.get("safety")
        if (
            not isinstance(safety, Mapping)
            or set(safety) != _SAFETY_KEYS
            or any(value is not False for value in safety.values())
        ):
            raise _error("all Elo initialization safety values must remain exact False")
        for key in (
            "initialization_boundary_execution_performed",
            "initialization_boundary_qualified",
            "source_history_mutation_performed",
            "historical_coverage_proven",
        ):
            if self.payload.get(key) is not False:
                raise _error(f"{key} must remain exact False")
        object.__setattr__(self, "payload", types.MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def build_fotmob_source_history_elo_initialization_boundary_protocol() -> FotMobSourceHistoryEloInitializationBoundaryProtocol:
    _verify_upstream()
    value = FotMobSourceHistoryEloInitializationBoundaryProtocol(_protocol_payload())
    raw = canonical_fotmob_source_history_elo_initialization_boundary_protocol_bytes(value)
    if len(raw) != PROTOCOL_SIZE or hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise _error("Elo initialization boundary protocol canonical identity changed")
    return value


def canonical_fotmob_source_history_elo_initialization_boundary_protocol_bytes(
    value: FotMobSourceHistoryEloInitializationBoundaryProtocol,
) -> bytes:
    if type(value) is not FotMobSourceHistoryEloInitializationBoundaryProtocol:
        raise _error("value must be exact Elo initialization boundary protocol")
    return _canonical(value.to_dict())


__all__ = [
    "BOUNDARY_REFERENCE_RULES",
    "ELO_INITIALIZATION_SEMANTICS",
    "ELO_STATE_RULES",
    "FROZEN_MODEL_FAMILIES",
    "NEXT_REQUIRED_BOUNDARY",
    "PR69_SYNTHETIC_WITNESS",
    "PROTOCOL_ID",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "QUALIFICATION_REQUIREMENTS",
    "QUALIFICATION_STATUS_VOCABULARY",
    "FotMobSourceHistoryEloInitializationBoundaryProtocol",
    "FotMobSourceHistoryEloInitializationBoundaryProtocolError",
    "build_fotmob_source_history_elo_initialization_boundary_protocol",
    "canonical_fotmob_source_history_elo_initialization_boundary_protocol_bytes",
]
