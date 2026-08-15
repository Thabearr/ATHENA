"""Pre-register the reviewed FotMob ordinary-FT source-history acquisition campaign.

PR #101 freezes a bounded source-history acquisition plan and performs no
network acquisition. The protocol binds the exact reviewed data-matches
request/capture path, the six-season PR #69 replay envelope, the eleven reviewed
FotMob competition mappings, repeated-capture lineage, failure handling, and
fail-closed result/identity/chronology rules.

Historical coverage remains UNKNOWN. No source-history, model, probability,
pricing, selection, production, or betting authority is granted.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_final_result_semantics_protocol as pr83
import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_assessment as pr100
from domain import fotmob_data_matches_capture as capture_contract
from domain import fotmob_data_matches_probe as probe_contract
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_EXACT_HISTORY_ACQUISITION_CAMPAIGN_ONLY_NO_EXECUTION"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_NO_HISTORY_ACQUIRED"
REPOSITORY_MAIN_SHA = "06e180412381316b7cf521c912a6dd4dfe35ea50"

PR100_ASSESSMENT_BLOB_SHA = "dd04f44c58779337455c9c93991a24970d6b8340"
PR100_ASSESSMENT_SHA256 = "069a66ac3c10d6d1f7da24cd0219fc178328b3327cd1446efaaff3dfec9cffb3"
PR100_ASSESSMENT_SIZE = 4720
PR99_PROTOCOL_BLOB_SHA = "3dd38f5f61c20c10900fa0bee9a30a69a58a3006"
SOURCE_CAPABILITIES_BLOB_SHA = "37b919eb5efa0c931e1bf10d3f845865567ef0c4"
REVIEWED_ORDINARY_FT_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"
CAPTURE_SCRIPT_BLOB_SHA = "10b8858ab62f2708bd564d578a627c43718e5a12"
PROBE_CONTRACT_BLOB_SHA = "c39bdea2ef65b26c3212471f6996831c4c845826"
PR83_PROTOCOL_BLOB_SHA = "25f8045524badcb90239df59ac9c47f36fcffe34"
PR83_PROTOCOL_SHA256 = "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
PR83_PROTOCOL_SIZE = 3995

PR69_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
PR69_SOURCE_FILE_COUNT = 66
PR69_SOURCE_FIXTURE_COUNT = 21226
PR69_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26")

DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

ACQUISITION_START_SOURCE_LOCAL_DATE = "2020-08-01"
ACQUISITION_END_SOURCE_LOCAL_DATE = "2026-05-24"
INCLUSIVE_CALENDAR_DATE_COUNT = 2123
CAPTURE_SLOTS_PER_DATE = 2
REQUIRED_SUCCESSFUL_CAPTURE_COUNT = 4246

MAPPING_STATE = (
    "PRE_REGISTERED_REVIEWED_OFFICIAL_FOTMOB_MAPPING_REQUIRES_CAPTURE_CONFIRMATION"
)
LEAGUE_MAPPING_RULE = (
    "ALL_ELEVEN_REVIEWED_OFFICIAL_FOTMOB_MAPPINGS_ARE_FROZEN_CANDIDATES_AND_"
    "MUST_MATCH_CAPTURED_LEAGUE_ID_BEFORE_CORPUS_QUALIFICATION"
)

LINEAGE_REQUIREMENTS = (
    "EVERY_SUCCESSFUL_SLOT_MUST_USE_THE_REVIEWED_DATA_MATCHES_CAPTURE_CONTRACT_AND_SCRIPT",
    "PRESERVE_EXACT_RAW_RESPONSE_BYTES_AND_CANONICAL_CAPTURE_MANIFEST_WITH_NO_OVERWRITE",
    "VERIFY_CAPTURE_DIRECTORY_AND_MANIFEST_BEFORE_ANY_SCHEMA_OR_RESULT_INTERPRETATION",
    "CAMPAIGN_INDEX_MUST_REFERENCE_REQUEST_DATE_SLOT_CAPTURE_ID_RAW_SHA256_RAW_SIZE_MANIFEST_SHA256_AND_OBSERVED_AT_UTC",
    "CAMPAIGN_INDEX_AND_FAILURE_JOURNAL_MUST_BE_CANONICAL_APPEND_ONLY_RESEARCH_EVIDENCE_OUTSIDE_GIT",
    "NO_RAW_CAPTURE_OR_CAMPAIGN_EVIDENCE_MAY_BE_COMMITTED_TO_GIT_FOR_CONVENIENCE",
    "NO_SUCCESSFUL_CAPTURE_MAY_REPLACE_OR_ERASE_A_FAILED_ATTEMPT_RECORD",
    "THE_TWO_ADAPTER_INPUTS_FOR_A_DATE_MUST_HAVE_DISTINCT_CAPTURE_MANIFEST_SHA256_AND_DISTINCT_RAW_SHA256_OR_THAT_DATE_CANNOT_QUALIFY",
)

FAILURE_HANDLING_RULES = (
    "ANY_REQUIRED_DATE_WITHOUT_TWO_VALID_SUCCESSFUL_SLOTS_BLOCKS_CAMPAIGN_QUALIFICATION",
    "HTTP_NON_200_TIMEOUT_CONTENT_TYPE_BODY_SIZE_MANIFEST_OR_DURABILITY_FAILURE_MUST_BE_RECORDED_AND_FAIL_CLOSED",
    "RETRIES_ARE_BOUNDED_BY_THE_FROZEN_SLOT_POLICY_AND_EACH_FAILED_ATTEMPT_REMAINS_DURABLE_EVIDENCE",
    "A_LATER_SUCCESS_DOES_NOT_DELETE_REWRITE_OR_HIDE_EARLIER_FAILURE_EVIDENCE",
    "MISSING_OR_FAILED_DATES_MUST_NEVER_BE_SILENTLY_SKIPPED_OR_FILLED_FROM_ANOTHER_SOURCE",
    "NO_CROSS_SOURCE_SUBSTITUTION_FROM_LEGACY_FOTMOB_HISTORICAL_FOOTBALL_DATA_UK_OR_ANY_OTHER_PROVIDER",
)

NON_ORDINARY_FT_RULES = (
    "ONLY_RESULTS_ADMITTED_BY_THE_REUSABLE_REVIEWED_ORDINARY_FT_FINISHED_SCORE_ADAPTER_MAY_ENTER_THE_DERIVED_HISTORY",
    "EVERY_IN_SCOPE_FINISHED_FIXTURE_REJECTED_BY_THE_ADAPTER_MUST_BE_RETAINED_WITH_ITS_EXACT_BLOCKING_DISPOSITION",
    "PENALTY_EXTRA_TIME_AWARDED_OR_OTHER_NON_ORDINARY_FINISHES_MUST_NOT_BE_COERCED_INTO_ORDINARY_FT_RESULTS",
    "POSTPONED_CANCELLED_ABANDONED_OR_REARRANGED_FIXTURES_REQUIRE_EXPLICIT_SOURCE_STATE_DISPOSITION_AND_MAY_NOT_DISAPPEAR",
    "ANY_UNRESOLVED_IN_SCOPE_FINISHED_FIXTURE_OUTSIDE_THE_ORDINARY_FT_GATE_BLOCKS_COMPLETENESS_UNLESS_SEPARATELY_REVIEWED",
)

CHRONOLOGY_IDENTITY_RULES = (
    "FOTMOB_FIXTURE_AND_TEAM_IDS_REMAIN_SOURCE_SCOPED_AND_MUST_NOT_BE_PROMOTED_TO_GLOBAL_CANONICAL_IDENTITY",
    "THE_SAME_FIXTURE_ID_ACROSS_CAPTURES_MUST_HAVE_STABLE_TEAMS_COMPETITION_AND_KICKOFF_OR_RAISE_A_CONFLICT",
    "DUPLICATE_FIXTURE_ID_OR_SAME_TEAM_SAME_KICKOFF_AMBIGUITY_FAILS_CLOSED",
    "REQUEST_DATE_EUROPE_LONDON_AND_FIXTURE_KICKOFF_UTC_MUST_BE_MUTUALLY_CONSISTENT_OR_EXPLICITLY_DISPOSITIONED",
    "TEAM_IDENTITY_CONTINUITY_ACROSS_SEASONS_MUST_USE_EXACT_SOURCE_TEAM_IDS_NOT_NAME_FUZZING",
    "NO_TARGET_FIXTURE_MAY_APPEAR_IN_ITS_OWN_PRIOR_RESULT_HISTORY",
    "REPLAY_ORDER_MUST_BE_KICKOFF_UTC_ASCENDING_THEN_SOURCE_FIXTURE_ID_ASCENDING_AFTER_CHRONOLOGY_QUALIFICATION",
)

QUALIFICATION_RULES = (
    "PROTOCOL_PRE_REGISTRATION_DOES_NOT_PROVE_THE_PR69_INITIALIZATION_BOUNDARY",
    "THE_ELEVEN_OFFICIAL_FOTMOB_MAPPING_CANDIDATES_ARE_REVIEWED_AND_FROZEN_BUT_EACH_MUST_MATCH_CAPTURED_LEAGUE_ID_BEFORE_CORPUS_QUALIFICATION",
    "ALL_2123_REQUIRED_DATES_AND_4246_SUCCESSFUL_CAPTURE_SLOTS_MUST_BE_ACCOUNTED_FOR_BEFORE_DAILY_COVERAGE_CAN_PASS",
    "CAPTURE_PAIR_DRIFT_MUST_BE_RECONCILED_OR_BLOCKED_BEFORE_A_DATE_CAN_SUPPORT_HISTORY",
    "HISTORICAL_COVERAGE_REMAINS_UNKNOWN_UNTIL_A_LATER_REVIEWED_ASSESSMENT_PASSES_EVERY_PR99_COMPLETENESS_GATE",
    "NO_CAMPAIGN_RESULT_MAY_DIRECTLY_AUTHORIZE_MODEL_PROBABILITY_PRICING_SELECTION_PRODUCTION_OR_BETTING",
)

NEXT_REQUIRED_BOUNDARY = (
    "IMPLEMENT_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_RUNNER"
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_history_campaign_runner_approved",
        "source_history_acquisition_executed",
        "source_history_adapter_approved",
        "source_history_completeness_proven",
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
        "bet_authorized",
    }
)

PROTOCOL_SHA256 = "6baeb5bc8fd03fb20024a20266092c85886c21e66da493b3100510ec871b5ebb"
PROTOCOL_SIZE = 9959


class FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError(ValueError):
    """Raised when the frozen PR #101 acquisition protocol cannot be reproduced."""


def _error(message: str) -> FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError:
    return FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("source-history acquisition protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("source-history acquisition safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all source-history acquisition safety values must remain exact False")
    return _safety()


@dataclasses.dataclass(frozen=True)
class FotMobLeagueMappingCandidate:
    model_league_code: str
    fotmob_league_id: int
    expected_name: str
    expected_country: str
    official_fotmob_path: str
    mapping_state: str

    def __post_init__(self) -> None:
        if type(self.model_league_code) is not str or not self.model_league_code:
            raise _error("model_league_code must be exact non-empty text")
        if type(self.fotmob_league_id) is not int or self.fotmob_league_id <= 0:
            raise _error("fotmob_league_id must be an exact positive integer")
        for label in ("expected_name", "expected_country", "official_fotmob_path"):
            value = getattr(self, label)
            if type(value) is not str or not value or value != value.strip():
                raise _error(f"{label} must be exact non-empty text")
        if not self.official_fotmob_path.startswith(
            f"/leagues/{self.fotmob_league_id}/"
        ):
            raise _error("official_fotmob_path must bind the exact FotMob league id")
        if self.mapping_state != MAPPING_STATE:
            raise _error("league mapping state must remain reviewed and capture-confirmed")


def _league_mappings() -> tuple[FotMobLeagueMappingCandidate, ...]:
    rows = (
        ("B1", 40, "First Division A", "Belgium", "/leagues/40/overview"),
        ("D1", 54, "Bundesliga", "Germany", "/leagues/54/overview"),
        ("E0", 47, "Premier League", "England", "/leagues/47/overview"),
        ("F1", 53, "Ligue 1", "France", "/leagues/53/overview"),
        ("G1", 135, "Super League 1", "Greece", "/leagues/135/overview"),
        ("I1", 55, "Serie A", "Italy", "/leagues/55/overview"),
        ("N1", 57, "Eredivisie", "Netherlands", "/leagues/57/overview"),
        ("P1", 61, "Liga Portugal", "Portugal", "/leagues/61/overview"),
        ("SC0", 64, "Premiership", "Scotland", "/leagues/64/overview"),
        ("SP1", 87, "LaLiga", "Spain", "/leagues/87/overview"),
        ("T1", 71, "Super Lig", "Türkiye", "/leagues/71/overview"),
    )
    return tuple(
        FotMobLeagueMappingCandidate(*row, MAPPING_STATE) for row in rows
    )


def _request_identity() -> dict[str, Any]:
    return {
        "method": "GET",
        "scheme": "https",
        "host": "www.fotmob.com",
        "port": 443,
        "path": "/api/data/matches",
        "date_parameter_format": "YYYYMMDD",
        "timezone": "Europe/London",
        "ccode3": "GBR",
        "request_headers": [["Accept", "application/json"], ["User-Agent", "ATHENA/1.0"]],
        "x_mas_included": False,
        "redirects_authorized": False,
        "cookies_authorized": False,
        "browser_impersonation_authorized": False,
        "proxy_evasion_authorized": False,
    }


def _acquisition_interval() -> dict[str, Any]:
    return {
        "start_source_local_date": ACQUISITION_START_SOURCE_LOCAL_DATE,
        "end_source_local_date": ACQUISITION_END_SOURCE_LOCAL_DATE,
        "inclusive_calendar_date_count": INCLUSIVE_CALENDAR_DATE_COUNT,
        "date_order": "ASCENDING",
        "source_local_date_basis": "EXACT_REQUEST_TIMEZONE_EUROPE_LONDON",
        "start_boundary_role": (
            "FROZEN_CANDIDATE_PR69_EQUIVALENCE_LOWER_BOUND_REQUIRES_POST_ACQUISITION_PROOF"
        ),
        "end_boundary_role": (
            "FROZEN_SIX_SEASON_PR69_2020_21_THROUGH_2025_26_REPLAY_ENVELOPE_END"
        ),
        "future_extension_authorized": False,
    }


def _capture_schedule() -> dict[str, Any]:
    return {
        "capture_slots_per_date": CAPTURE_SLOTS_PER_DATE,
        "slot_labels": ["A", "B"],
        "pass_order": "ALL_SLOT_A_DATES_ASCENDING_THEN_ALL_SLOT_B_DATES_ASCENDING",
        "minimum_same_date_slot_separation_seconds": 300,
        "maximum_same_date_slot_separation_seconds": 86400,
        "minimum_inter_request_seconds": 1.0,
        "maximum_attempts_per_slot": 3,
        "retry_delays_seconds": [60, 300],
        "required_successful_capture_count": REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
        "failed_attempts_count_as_success": False,
    }


def _protocol_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr100_assessment_blob_sha": PR100_ASSESSMENT_BLOB_SHA,
        "pr100_assessment_sha256": PR100_ASSESSMENT_SHA256,
        "pr100_assessment_size": PR100_ASSESSMENT_SIZE,
        "pr99_protocol_blob_sha": PR99_PROTOCOL_BLOB_SHA,
        "source_capabilities_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "reviewed_ordinary_ft_adapter_blob_sha": REVIEWED_ORDINARY_FT_ADAPTER_BLOB_SHA,
        "capture_contract_blob_sha": CAPTURE_CONTRACT_BLOB_SHA,
        "capture_script_blob_sha": CAPTURE_SCRIPT_BLOB_SHA,
        "probe_contract_blob_sha": PROBE_CONTRACT_BLOB_SHA,
        "pr83_protocol_blob_sha": PR83_PROTOCOL_BLOB_SHA,
        "pr83_protocol_sha256": PR83_PROTOCOL_SHA256,
        "pr83_protocol_size": PR83_PROTOCOL_SIZE,
        "pr69_source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
        "pr69_source_file_count": PR69_SOURCE_FILE_COUNT,
        "pr69_source_fixture_count": PR69_SOURCE_FIXTURE_COUNT,
        "pr69_seasons": list(PR69_SEASONS),
        "derived_source_key": DERIVED_SOURCE_KEY,
        "parent_source_key": PARENT_SOURCE_KEY,
        "request_identity": _request_identity(),
        "acquisition_interval": _acquisition_interval(),
        "capture_schedule": _capture_schedule(),
        "league_mappings": [dataclasses.asdict(item) for item in _league_mappings()],
        "league_mapping_rule": LEAGUE_MAPPING_RULE,
        "lineage_requirements": list(LINEAGE_REQUIREMENTS),
        "failure_handling_rules": list(FAILURE_HANDLING_RULES),
        "non_ordinary_ft_rules": list(NON_ORDINARY_FT_RULES),
        "chronology_identity_rules": list(CHRONOLOGY_IDENTITY_RULES),
        "qualification_rules": list(QUALIFICATION_RULES),
        "network_acquisition_performed": False,
        "campaign_runner_implemented": False,
        "history_rows_materialized": 0,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def _verify_upstream() -> None:
    if (pr100.ASSESSMENT_SHA256, pr100.ASSESSMENT_SIZE) != (
        PR100_ASSESSMENT_SHA256,
        PR100_ASSESSMENT_SIZE,
    ):
        raise _error("PR100 source-history assessment constants changed")
    assessment = (
        pr100.build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment()
    )
    exact = (
        pr100.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment_bytes(
            assessment
        )
    )
    if (
        hashlib.sha256(exact).hexdigest() != PR100_ASSESSMENT_SHA256
        or len(exact) != PR100_ASSESSMENT_SIZE
    ):
        raise _error("PR100 canonical source-history assessment changed")
    if pr100.SMALLEST_MISSING_REVIEWED_BOUNDARY != (
        "PRE_REGISTER_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_PROTOCOL"
    ):
        raise _error("PR100 next acquisition boundary changed")

    if (pr83.PROTOCOL_SHA256, pr83.PROTOCOL_SIZE) != (
        PR83_PROTOCOL_SHA256,
        PR83_PROTOCOL_SIZE,
    ):
        raise _error("PR83 final-result semantics protocol identity changed")
    if pr83.MINIMUM_REPEAT_SEPARATION_SECONDS != 300:
        raise _error("PR83 repeated-capture separation changed")

    derived = SOURCE_CAPABILITY_REGISTRY.get(DERIVED_SOURCE_KEY)
    parent = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    if derived is None or parent is None:
        raise _error("required reviewed FotMob source capability is missing")
    if derived.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("derived full-time-score capability must remain CONFIRMED")
    if derived.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("derived fixture identity must remain CONFIRMED")
    if derived.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("derived historical coverage must remain UNKNOWN before acquisition")
    if parent.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("parent reviewed catalog full-time-score premise changed")
    if parent.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("parent historical coverage premise changed")

    if (
        probe_contract.ALLOWED_HOST != "www.fotmob.com"
        or probe_contract.HTTPS_PORT != 443
        or probe_contract.ALLOWED_PATH != "/api/data/matches"
        or probe_contract.REQUEST_HEADERS
        != (("Accept", "application/json"), ("User-Agent", "ATHENA/1.0"))
    ):
        raise _error("reviewed FotMob probe request identity changed")
    if (
        capture_contract.RAW_FILENAME != "response.json"
        or capture_contract.MANIFEST_FILENAME != "manifest.json"
        or capture_contract.MAX_RESPONSE_BYTES != 8 * 1024 * 1024
    ):
        raise _error("reviewed FotMob capture contract changed")

    if tuple(item.model_league_code for item in _league_mappings()) != tuple(
        assessment.frozen_model_league_codes
    ):
        raise _error("reviewed FotMob mappings do not cover the frozen eleven-league universe")


@dataclasses.dataclass(frozen=True)
class FotMobOrdinaryFtSourceHistoryAcquisitionProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    pr100_assessment_blob_sha: str
    pr100_assessment_sha256: str
    pr100_assessment_size: int
    pr99_protocol_blob_sha: str
    source_capabilities_blob_sha: str
    reviewed_ordinary_ft_adapter_blob_sha: str
    capture_contract_blob_sha: str
    capture_script_blob_sha: str
    probe_contract_blob_sha: str
    pr83_protocol_blob_sha: str
    pr83_protocol_sha256: str
    pr83_protocol_size: int
    pr69_source_corpus_sha256: str
    pr69_source_file_count: int
    pr69_source_fixture_count: int
    pr69_seasons: tuple[str, ...]
    derived_source_key: str
    parent_source_key: str
    request_identity: Mapping[str, Any]
    acquisition_interval: Mapping[str, Any]
    capture_schedule: Mapping[str, Any]
    league_mappings: tuple[FotMobLeagueMappingCandidate, ...]
    league_mapping_rule: str
    lineage_requirements: tuple[str, ...]
    failure_handling_rules: tuple[str, ...]
    non_ordinary_ft_rules: tuple[str, ...]
    chronology_identity_rules: tuple[str, ...]
    qualification_rules: tuple[str, ...]
    network_acquisition_performed: bool
    campaign_runner_implemented: bool
    history_rows_materialized: int
    next_required_boundary: str
    safety: Mapping[str, bool]

    def to_dict(self) -> dict[str, Any]:
        scalar_names = (
            "schema_version", "protocol_id", "protocol_scope", "protocol_state",
            "repository_main_sha", "pr100_assessment_blob_sha",
            "pr100_assessment_sha256", "pr100_assessment_size",
            "pr99_protocol_blob_sha", "source_capabilities_blob_sha",
            "reviewed_ordinary_ft_adapter_blob_sha", "capture_contract_blob_sha",
            "capture_script_blob_sha", "probe_contract_blob_sha",
            "pr83_protocol_blob_sha", "pr83_protocol_sha256", "pr83_protocol_size",
            "pr69_source_corpus_sha256", "pr69_source_file_count",
            "pr69_source_fixture_count", "derived_source_key", "parent_source_key",
            "league_mapping_rule", "network_acquisition_performed",
            "campaign_runner_implemented", "history_rows_materialized",
            "next_required_boundary",
        )
        return {
            **{name: getattr(self, name) for name in scalar_names},
            "pr69_seasons": list(self.pr69_seasons),
            "request_identity": dict(self.request_identity),
            "acquisition_interval": dict(self.acquisition_interval),
            "capture_schedule": {
                **dict(self.capture_schedule),
                "slot_labels": list(self.capture_schedule["slot_labels"]),
                "retry_delays_seconds": list(self.capture_schedule["retry_delays_seconds"]),
            },
            "league_mappings": [dataclasses.asdict(item) for item in self.league_mappings],
            "lineage_requirements": list(self.lineage_requirements),
            "failure_handling_rules": list(self.failure_handling_rules),
            "non_ordinary_ft_rules": list(self.non_ordinary_ft_rules),
            "chronology_identity_rules": list(self.chronology_identity_rules),
            "qualification_rules": list(self.qualification_rules),
            "safety": dict(self.safety),
        }

    def __post_init__(self) -> None:
        if self.to_dict() != _protocol_payload():
            raise _error("source-history acquisition protocol differs from frozen PR101 contract")
        if self.network_acquisition_performed is not False:
            raise _error("network_acquisition_performed must remain exact False")
        if self.campaign_runner_implemented is not False:
            raise _error("campaign_runner_implemented must remain exact False")
        if type(self.history_rows_materialized) is not int or self.history_rows_materialized != 0:
            raise _error("history_rows_materialized must remain exact integer zero")
        object.__setattr__(self, "request_identity", types.MappingProxyType(dict(self.request_identity)))
        object.__setattr__(self, "acquisition_interval", types.MappingProxyType(dict(self.acquisition_interval)))
        schedule = dict(self.capture_schedule)
        schedule["slot_labels"] = tuple(schedule["slot_labels"])
        schedule["retry_delays_seconds"] = tuple(schedule["retry_delays_seconds"])
        object.__setattr__(self, "capture_schedule", types.MappingProxyType(schedule))
        object.__setattr__(self, "safety", _checked_safety(self.safety))


def build_fotmob_ordinary_ft_source_history_acquisition_protocol(
) -> FotMobOrdinaryFtSourceHistoryAcquisitionProtocol:
    _verify_upstream()
    payload = _protocol_payload()
    schedule = dict(payload["capture_schedule"])
    schedule["slot_labels"] = tuple(schedule["slot_labels"])
    schedule["retry_delays_seconds"] = tuple(schedule["retry_delays_seconds"])
    value = FotMobOrdinaryFtSourceHistoryAcquisitionProtocol(
        schema_version=payload["schema_version"],
        protocol_id=payload["protocol_id"],
        protocol_scope=payload["protocol_scope"],
        protocol_state=payload["protocol_state"],
        repository_main_sha=payload["repository_main_sha"],
        pr100_assessment_blob_sha=payload["pr100_assessment_blob_sha"],
        pr100_assessment_sha256=payload["pr100_assessment_sha256"],
        pr100_assessment_size=payload["pr100_assessment_size"],
        pr99_protocol_blob_sha=payload["pr99_protocol_blob_sha"],
        source_capabilities_blob_sha=payload["source_capabilities_blob_sha"],
        reviewed_ordinary_ft_adapter_blob_sha=payload["reviewed_ordinary_ft_adapter_blob_sha"],
        capture_contract_blob_sha=payload["capture_contract_blob_sha"],
        capture_script_blob_sha=payload["capture_script_blob_sha"],
        probe_contract_blob_sha=payload["probe_contract_blob_sha"],
        pr83_protocol_blob_sha=payload["pr83_protocol_blob_sha"],
        pr83_protocol_sha256=payload["pr83_protocol_sha256"],
        pr83_protocol_size=payload["pr83_protocol_size"],
        pr69_source_corpus_sha256=payload["pr69_source_corpus_sha256"],
        pr69_source_file_count=payload["pr69_source_file_count"],
        pr69_source_fixture_count=payload["pr69_source_fixture_count"],
        pr69_seasons=tuple(payload["pr69_seasons"]),
        derived_source_key=payload["derived_source_key"],
        parent_source_key=payload["parent_source_key"],
        request_identity=types.MappingProxyType(dict(payload["request_identity"])),
        acquisition_interval=types.MappingProxyType(dict(payload["acquisition_interval"])),
        capture_schedule=types.MappingProxyType(schedule),
        league_mappings=tuple(FotMobLeagueMappingCandidate(**item) for item in payload["league_mappings"]),
        league_mapping_rule=payload["league_mapping_rule"],
        lineage_requirements=tuple(payload["lineage_requirements"]),
        failure_handling_rules=tuple(payload["failure_handling_rules"]),
        non_ordinary_ft_rules=tuple(payload["non_ordinary_ft_rules"]),
        chronology_identity_rules=tuple(payload["chronology_identity_rules"]),
        qualification_rules=tuple(payload["qualification_rules"]),
        network_acquisition_performed=payload["network_acquisition_performed"],
        campaign_runner_implemented=payload["campaign_runner_implemented"],
        history_rows_materialized=payload["history_rows_materialized"],
        next_required_boundary=payload["next_required_boundary"],
        safety=types.MappingProxyType(dict(payload["safety"])),
    )
    exact = _canonical(value.to_dict())
    if len(exact) != PROTOCOL_SIZE or hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256:
        raise _error("PR101 canonical acquisition protocol identity changed")
    return value


def canonical_fotmob_ordinary_ft_source_history_acquisition_protocol_bytes(
    value: FotMobOrdinaryFtSourceHistoryAcquisitionProtocol,
) -> bytes:
    if type(value) is not FotMobOrdinaryFtSourceHistoryAcquisitionProtocol:
        raise _error("acquisition protocol must be the exact PR101 protocol type")
    exact = _canonical(value.to_dict())
    if len(exact) != PROTOCOL_SIZE or hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256:
        raise _error("PR101 canonical acquisition protocol identity changed")
    return exact


def sha256_fotmob_ordinary_ft_source_history_acquisition_protocol(
    value: FotMobOrdinaryFtSourceHistoryAcquisitionProtocol,
) -> str:
    return hashlib.sha256(
        canonical_fotmob_ordinary_ft_source_history_acquisition_protocol_bytes(value)
    ).hexdigest()


__all__ = [
    "ACQUISITION_END_SOURCE_LOCAL_DATE",
    "ACQUISITION_START_SOURCE_LOCAL_DATE",
    "CAPTURE_SLOTS_PER_DATE",
    "INCLUSIVE_CALENDAR_DATE_COUNT",
    "MAPPING_STATE",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "REQUIRED_SUCCESSFUL_CAPTURE_COUNT",
    "FotMobLeagueMappingCandidate",
    "FotMobOrdinaryFtSourceHistoryAcquisitionProtocol",
    "FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError",
    "build_fotmob_ordinary_ft_source_history_acquisition_protocol",
    "canonical_fotmob_ordinary_ft_source_history_acquisition_protocol_bytes",
    "sha256_fotmob_ordinary_ft_source_history_acquisition_protocol",
]
