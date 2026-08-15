from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_ordinary_ft_source_history_acquisition_protocol as protocol_module
from domain.fotmob_ordinary_ft_source_history_acquisition_protocol import (
    ACQUISITION_END_SOURCE_LOCAL_DATE,
    ACQUISITION_START_SOURCE_LOCAL_DATE,
    CAPTURE_SLOTS_PER_DATE,
    INCLUSIVE_CALENDAR_DATE_COUNT,
    MAPPING_STATE,
    NEXT_REQUIRED_BOUNDARY,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
    FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError,
    build_fotmob_ordinary_ft_source_history_acquisition_protocol,
    canonical_fotmob_ordinary_ft_source_history_acquisition_protocol_bytes,
)


ROOT = Path(__file__).resolve().parents[1]


def _git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def test_protocol_is_exact_canonical_pre_registration_only() -> None:
    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    exact = canonical_fotmob_ordinary_ft_source_history_acquisition_protocol_bytes(value)

    assert value.protocol_state == "PRE_REGISTERED_NOT_EXECUTED_NO_HISTORY_ACQUIRED"
    assert value.network_acquisition_performed is False
    assert value.campaign_runner_implemented is False
    assert value.history_rows_materialized == 0
    assert len(exact) == PROTOCOL_SIZE == 9959
    assert hashlib.sha256(exact).hexdigest() == PROTOCOL_SHA256
    assert PROTOCOL_SHA256 == (
        "6baeb5bc8fd03fb20024a20266092c85886c21e66da493b3100510ec871b5ebb"
    )
    assert set(value.safety.values()) == {False}


def test_protocol_binds_exact_upstream_assessment_capture_adapter_and_pr83_blobs() -> None:
    expected_blobs = {
        ROOT / "domain" / "fotmob_ordinary_ft_finished_score_source_history_completeness_assessment.py": "dd04f44c58779337455c9c93991a24970d6b8340",
        ROOT / "domain" / "fotmob_ordinary_ft_finished_score_source_history_completeness_protocol.py": "3dd38f5f61c20c10900fa0bee9a30a69a58a3006",
        ROOT / "domain" / "source_capabilities.py": "37b919eb5efa0c931e1bf10d3f845865567ef0c4",
        ROOT / "domain" / "fotmob_data_matches_ordinary_ft_finished_score_adapter.py": "868563206e09010fce74b4ba7954028930baad54",
        ROOT / "domain" / "fotmob_data_matches_capture.py": "ca2149395de868104666620173b55a880b10c729",
        ROOT / "scripts" / "capture_fotmob_data_matches.py": "10b8858ab62f2708bd564d578a627c43718e5a12",
        ROOT / "domain" / "fotmob_data_matches_probe.py": "c39bdea2ef65b26c3212471f6996831c4c845826",
        ROOT / "domain" / "fotmob_data_matches_final_result_semantics_protocol.py": "25f8045524badcb90239df59ac9c47f36fcffe34",
    }
    assert {path: _git_blob_oid(path) for path in expected_blobs} == expected_blobs

    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    assert value.repository_main_sha == "06e180412381316b7cf521c912a6dd4dfe35ea50"
    assert value.pr100_assessment_blob_sha == expected_blobs[
        ROOT / "domain" / "fotmob_ordinary_ft_finished_score_source_history_completeness_assessment.py"
    ]
    assert value.pr99_protocol_blob_sha == expected_blobs[
        ROOT / "domain" / "fotmob_ordinary_ft_finished_score_source_history_completeness_protocol.py"
    ]
    assert value.source_capabilities_blob_sha == expected_blobs[ROOT / "domain" / "source_capabilities.py"]
    assert value.reviewed_ordinary_ft_adapter_blob_sha == expected_blobs[
        ROOT / "domain" / "fotmob_data_matches_ordinary_ft_finished_score_adapter.py"
    ]
    assert value.capture_contract_blob_sha == expected_blobs[ROOT / "domain" / "fotmob_data_matches_capture.py"]
    assert value.capture_script_blob_sha == expected_blobs[ROOT / "scripts" / "capture_fotmob_data_matches.py"]
    assert value.probe_contract_blob_sha == expected_blobs[ROOT / "domain" / "fotmob_data_matches_probe.py"]
    assert value.pr83_protocol_blob_sha == expected_blobs[
        ROOT / "domain" / "fotmob_data_matches_final_result_semantics_protocol.py"
    ]
    assert value.pr83_protocol_sha256 == "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
    assert value.pr83_protocol_size == 3995


def test_six_season_interval_is_exact_daily_window_without_claiming_initialization_equivalence() -> None:
    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    start = datetime.date.fromisoformat(ACQUISITION_START_SOURCE_LOCAL_DATE)
    end = datetime.date.fromisoformat(ACQUISITION_END_SOURCE_LOCAL_DATE)

    assert (end - start).days + 1 == INCLUSIVE_CALENDAR_DATE_COUNT == 2123
    assert value.acquisition_interval == {
        "start_source_local_date": "2020-08-01",
        "end_source_local_date": "2026-05-24",
        "inclusive_calendar_date_count": 2123,
        "date_order": "ASCENDING",
        "source_local_date_basis": "EXACT_REQUEST_TIMEZONE_EUROPE_LONDON",
        "start_boundary_role": "FROZEN_CANDIDATE_PR69_EQUIVALENCE_LOWER_BOUND_REQUIRES_POST_ACQUISITION_PROOF",
        "end_boundary_role": "FROZEN_SIX_SEASON_PR69_2020_21_THROUGH_2025_26_REPLAY_ENVELOPE_END",
        "future_extension_authorized": False,
    }
    assert value.pr69_source_corpus_sha256 == "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
    assert value.pr69_source_file_count == 66
    assert value.pr69_source_fixture_count == 21226
    assert value.pr69_seasons == (
        "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"
    )
    assert "PROTOCOL_PRE_REGISTRATION_DOES_NOT_PROVE_THE_PR69_INITIALIZATION_BOUNDARY" in value.qualification_rules


def test_request_identity_matches_reviewed_data_matches_context_and_pair_schedule() -> None:
    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()

    assert value.request_identity == {
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
    assert CAPTURE_SLOTS_PER_DATE == 2
    assert REQUIRED_SUCCESSFUL_CAPTURE_COUNT == 4246
    assert INCLUSIVE_CALENDAR_DATE_COUNT * CAPTURE_SLOTS_PER_DATE == REQUIRED_SUCCESSFUL_CAPTURE_COUNT
    assert value.capture_schedule == {
        "capture_slots_per_date": 2,
        "slot_labels": ("A", "B"),
        "pass_order": "ALL_SLOT_A_DATES_ASCENDING_THEN_ALL_SLOT_B_DATES_ASCENDING",
        "minimum_same_date_slot_separation_seconds": 300,
        "maximum_same_date_slot_separation_seconds": 86400,
        "minimum_inter_request_seconds": 1.0,
        "maximum_attempts_per_slot": 3,
        "retry_delays_seconds": (60, 300),
        "required_successful_capture_count": 4246,
        "failed_attempts_count_as_success": False,
    }


def test_all_eleven_reviewed_fotmob_mapping_candidates_are_frozen_and_capture_confirmed() -> None:
    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    mappings = {
        item.model_league_code: (
            item.fotmob_league_id,
            item.expected_name,
            item.expected_country,
            item.official_fotmob_path,
            item.mapping_state,
        )
        for item in value.league_mappings
    }
    assert mappings == {
        "B1": (40, "First Division A", "Belgium", "/leagues/40/overview", MAPPING_STATE),
        "D1": (54, "Bundesliga", "Germany", "/leagues/54/overview", MAPPING_STATE),
        "E0": (47, "Premier League", "England", "/leagues/47/overview", MAPPING_STATE),
        "F1": (53, "Ligue 1", "France", "/leagues/53/overview", MAPPING_STATE),
        "G1": (135, "Super League 1", "Greece", "/leagues/135/overview", MAPPING_STATE),
        "I1": (55, "Serie A", "Italy", "/leagues/55/overview", MAPPING_STATE),
        "N1": (57, "Eredivisie", "Netherlands", "/leagues/57/overview", MAPPING_STATE),
        "P1": (61, "Liga Portugal", "Portugal", "/leagues/61/overview", MAPPING_STATE),
        "SC0": (64, "Premiership", "Scotland", "/leagues/64/overview", MAPPING_STATE),
        "SP1": (87, "LaLiga", "Spain", "/leagues/87/overview", MAPPING_STATE),
        "T1": (71, "Super Lig", "Türkiye", "/leagues/71/overview", MAPPING_STATE),
    }
    assert tuple(mappings) == ("B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1")
    assert len({item.fotmob_league_id for item in value.league_mappings}) == 11
    assert all(item.mapping_state == MAPPING_STATE for item in value.league_mappings)
    assert (
        "THE_ELEVEN_OFFICIAL_FOTMOB_MAPPING_CANDIDATES_ARE_REVIEWED_AND_FROZEN_BUT_EACH_MUST_MATCH_CAPTURED_LEAGUE_ID_BEFORE_CORPUS_QUALIFICATION"
        in value.qualification_rules
    )


def test_failure_lineage_adapter_distinctness_and_no_cross_source_substitution_are_fail_closed() -> None:
    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    assert "ANY_REQUIRED_DATE_WITHOUT_TWO_VALID_SUCCESSFUL_SLOTS_BLOCKS_CAMPAIGN_QUALIFICATION" in value.failure_handling_rules
    assert "MISSING_OR_FAILED_DATES_MUST_NEVER_BE_SILENTLY_SKIPPED_OR_FILLED_FROM_ANOTHER_SOURCE" in value.failure_handling_rules
    assert "NO_CROSS_SOURCE_SUBSTITUTION_FROM_LEGACY_FOTMOB_HISTORICAL_FOOTBALL_DATA_UK_OR_ANY_OTHER_PROVIDER" in value.failure_handling_rules
    assert "NO_SUCCESSFUL_CAPTURE_MAY_REPLACE_OR_ERASE_A_FAILED_ATTEMPT_RECORD" in value.lineage_requirements
    assert "CAMPAIGN_INDEX_AND_FAILURE_JOURNAL_MUST_BE_CANONICAL_APPEND_ONLY_RESEARCH_EVIDENCE_OUTSIDE_GIT" in value.lineage_requirements
    assert (
        "THE_TWO_ADAPTER_INPUTS_FOR_A_DATE_MUST_HAVE_DISTINCT_CAPTURE_MANIFEST_SHA256_AND_DISTINCT_RAW_SHA256_OR_THAT_DATE_CANNOT_QUALIFY"
        in value.lineage_requirements
    )


def test_non_ordinary_finished_states_and_chronology_cannot_be_silently_dropped() -> None:
    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    assert "PENALTY_EXTRA_TIME_AWARDED_OR_OTHER_NON_ORDINARY_FINISHES_MUST_NOT_BE_COERCED_INTO_ORDINARY_FT_RESULTS" in value.non_ordinary_ft_rules
    assert "POSTPONED_CANCELLED_ABANDONED_OR_REARRANGED_FIXTURES_REQUIRE_EXPLICIT_SOURCE_STATE_DISPOSITION_AND_MAY_NOT_DISAPPEAR" in value.non_ordinary_ft_rules
    assert "ANY_UNRESOLVED_IN_SCOPE_FINISHED_FIXTURE_OUTSIDE_THE_ORDINARY_FT_GATE_BLOCKS_COMPLETENESS_UNLESS_SEPARATELY_REVIEWED" in value.non_ordinary_ft_rules
    assert "THE_SAME_FIXTURE_ID_ACROSS_CAPTURES_MUST_HAVE_STABLE_TEAMS_COMPETITION_AND_KICKOFF_OR_RAISE_A_CONFLICT" in value.chronology_identity_rules
    assert "DUPLICATE_FIXTURE_ID_OR_SAME_TEAM_SAME_KICKOFF_AMBIGUITY_FAILS_CLOSED" in value.chronology_identity_rules
    assert "TEAM_IDENTITY_CONTINUITY_ACROSS_SEASONS_MUST_USE_EXACT_SOURCE_TEAM_IDS_NOT_NAME_FUZZING" in value.chronology_identity_rules
    assert "REQUEST_DATE_EUROPE_LONDON_AND_FIXTURE_KICKOFF_UTC_MUST_BE_MUTUALLY_CONSISTENT_OR_EXPLICITLY_DISPOSITIONED" in value.chronology_identity_rules


def test_protocol_mutations_fail_closed() -> None:
    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    for replacement in (
        {"network_acquisition_performed": True},
        {"campaign_runner_implemented": True},
        {"history_rows_materialized": 1},
    ):
        with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError):
            dataclasses.replace(value, **replacement)

    mutated_interval = dict(value.acquisition_interval)
    mutated_interval["future_extension_authorized"] = True
    with pytest.raises(FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError):
        dataclasses.replace(value, acquisition_interval=mutated_interval)

    with pytest.raises(
        FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError,
        match="league mapping state must remain reviewed and capture-confirmed",
    ):
        dataclasses.replace(value.league_mappings[0], mapping_state="QUALIFIED")


def test_upstream_request_and_pr83_drift_blocks_protocol(monkeypatch) -> None:
    monkeypatch.setattr(protocol_module.probe_contract, "ALLOWED_HOST", "example.invalid")
    with pytest.raises(
        FotMobOrdinaryFtSourceHistoryAcquisitionProtocolError,
        match="reviewed FotMob probe request identity changed",
    ):
        build_fotmob_ordinary_ft_source_history_acquisition_protocol()


def test_protocol_is_domain_only_and_cannot_execute_acquisition_or_downstream_paths() -> None:
    source = Path(protocol_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
            imported_modules.add(node.module)

    assert imported_roots.isdisjoint(
        {
            "requests", "httpx", "aiohttp", "playwright", "workers", "providers",
            "api", "services", "engine", "models", "database", "repositories",
            "scripts", "socket", "subprocess",
        }
    )
    assert all(
        token not in module_name
        for module_name in imported_modules
        for token in ("score_matrix", "probability", "pricing", "selection", "betting", "sportybet")
    )

    value = build_fotmob_ordinary_ft_source_history_acquisition_protocol()
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert NEXT_REQUIRED_BOUNDARY == "IMPLEMENT_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_RUNNER"
