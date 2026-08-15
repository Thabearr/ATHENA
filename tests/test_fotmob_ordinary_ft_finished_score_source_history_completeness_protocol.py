from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_protocol as protocol
import domain.prospective_successor_source_history_completeness_protocol as pr81
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]


def test_protocol_is_exact_canonical_preregistered_evidence() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()
    exact = protocol.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(value)

    assert value["protocol_state"] == "PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN"
    assert value["current_pre_execution_disposition"] == "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
    assert len(exact) == protocol.PROTOCOL_SIZE == 5048
    assert hashlib.sha256(exact).hexdigest() == protocol.PROTOCOL_SHA256 == (
        "ac922634b999a4e8bdb186df3ac2fc1291c130aca405956ea611c5cc582d9e15"
    )
    assert set(value["safety"].values()) == {False}


def test_protocol_binds_registered_derived_source_without_mutating_parent() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()
    derived = SOURCE_CAPABILITY_REGISTRY[protocol.DERIVED_SOURCE_KEY]
    parent = SOURCE_CAPABILITY_REGISTRY[protocol.PARENT_SOURCE_KEY]

    assert derived.full_time_score is CapabilityAvailability.CONFIRMED
    assert derived.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert derived.historical_coverage is CapabilityAvailability.UNKNOWN
    assert parent.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert parent.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert parent.historical_coverage is CapabilityAvailability.UNKNOWN

    assert value["derived_source_facts"] == {
        "full_time_score": "CONFIRMED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
    assert value["parent_source_facts"]["full_time_score"] == "NOT_CAPTURED"
    assert value["parent_source_facts"]["historical_coverage"] == "UNKNOWN"


def test_protocol_reuses_pr81_completeness_contract_without_weakening_it() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()

    assert tuple(value["frozen_model_league_codes"]) == tuple(pr81.FROZEN_MODEL_LEAGUE_CODES)
    assert value["elo_initialization_semantics"] == pr81.ELO_INITIALIZATION_SEMANTICS
    assert tuple(value["pr81_history_adapter_requirements"]) == tuple(pr81.HISTORY_ADAPTER_REQUIREMENTS)
    assert tuple(value["pr81_completeness_requirements"]) == tuple(pr81.COMPLETENESS_REQUIREMENTS)
    assert (
        "NO_SILENT_FILTERING_TO_ONLY_TARGET_TEAMS_BECAUSE_ELO_REPLAY_DEPENDS_ON_OPPONENT_STATE"
        in value["pr81_completeness_requirements"]
    )
    assert (
        "COVER_EVERY_CALENDAR_DATE_FROM_INITIALIZATION_BOUNDARY_THROUGH_TARGET_SOURCE_LOCAL_DATE"
        in value["pr81_completeness_requirements"]
    )


def test_ordinary_ft_score_registration_is_not_historical_completeness() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()

    assert value["historical_coverage_rule"] == "HISTORICAL_COVERAGE_REMAINS_UNKNOWN"
    assert value["current_pre_execution_disposition"] == "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
    assert "QUALIFIED_COMPLETE_REVIEWED_ORDINARY_FT_HISTORY" in value["qualification_status_vocabulary"]
    assert "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN" in value["qualification_status_vocabulary"]
    assert value["safety"]["source_history_adapter_approved"] is False
    assert value["safety"]["source_history_completeness_proven"] is False
    assert value["safety"]["pr80_constructor_input_authorized"] is False


def test_protocol_keeps_penalty_and_nonordinary_results_fail_closed() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()

    assert value["penalty_exclusion_rule"] == (
        "PENALTY_OR_OTHER_UNREVIEWED_REASON_FIXTURES_MUST_NOT_ENTER_DERIVED_CAPABILITY"
    )
    assert value["semantic_exclusion_rule"] == (
        "DO_NOT_INFER_REGULATION_TIME_EXTRA_TIME_PENALTY_SCORE_BOOKMAKER_SETTLEMENT_OR_GLOBAL_STATUS_REASON_SEMANTICS"
    )
    assert (
        "ANY_IN_SCOPE_FINISHED_FIXTURE_OUTSIDE_THE_ORDINARY_FT_GATE_BLOCKS_COMPLETENESS_UNLESS_SEPARATELY_REVIEWED"
        in value["derived_source_additional_requirements"]
    )
    assert (
        "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW"
        in value["qualification_status_vocabulary"]
    )


def test_protocol_forbids_legacy_or_cross_source_substitution() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()

    assert value["derived_source_key"] == "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
    assert value["derived_source_key"] != "fotmob_historical"
    assert (
        "DO_NOT_SUBSTITUTE_LEGACY_FOTMOB_HISTORICAL_OR_ANY_OTHER_SOURCE_FOR_THE_REGISTERED_DERIVED_SOURCE"
        in value["derived_source_additional_requirements"]
    )
    assert "NO_CROSS_SOURCE_IDENTITY_INFERENCE" in value["pr81_history_adapter_requirements"]


def test_protocol_binds_exact_reviewed_ancestry_and_next_boundary() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()

    assert value["repository_main_sha"] == "db8bc1eb1b4a5b35751d70a14e0fe07157fe149f"
    assert value["pr81_protocol_sha256"] == "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
    assert value["pr93_protocol_sha256"] == "8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009"
    assert value["pr96_receipt_sha256"] == "09dd9fdff1eddb7b421e968c8de93262b09ce526adeb3d3b95050ddf1f2d4562"
    assert value["pr97_assessment_sha256"] == "edec152475a4c964084cdee1ba7c6a7385457297b63acf4a81e683dc74e99e03"
    assert value["pr98_source_capabilities_blob_sha"] == "37b919eb5efa0c931e1bf10d3f845865567ef0c4"
    assert value["next_required_boundary"] == protocol.NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_ORDINARY_FT_FINISHED_SCORE_SOURCE_HISTORY_COMPLETENESS_ASSESSMENT"
    )


def test_protocol_is_deeply_immutable_and_mutation_fails_closed() -> None:
    value = protocol.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()

    with pytest.raises(TypeError):
        value["protocol_state"] = "EXECUTED"
    with pytest.raises(TypeError):
        value["derived_source_facts"]["historical_coverage"] = "CONFIRMED"
    with pytest.raises(TypeError):
        value["safety"]["bet_authorized"] = True

    mutated = dict(value)
    mutated["current_pre_execution_disposition"] = "QUALIFIED_COMPLETE_REVIEWED_ORDINARY_FT_HISTORY"
    with pytest.raises(protocol.FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessProtocolError):
        protocol.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(mutated)


def test_protocol_is_domain_only_and_imports_no_acquisition_or_downstream_runtime_layers() -> None:
    source = (
        ROOT / "domain" / "fotmob_ordinary_ft_finished_score_source_history_completeness_protocol.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
            modules.add(node.module)

    assert roots.isdisjoint(
        {
            "requests",
            "httpx",
            "aiohttp",
            "playwright",
            "workers",
            "providers",
            "api",
            "services",
            "engine",
            "models",
            "database",
            "repositories",
        }
    )
    assert all(
        token not in module_name
        for module_name in modules
        for token in ("score_matrix", "probability", "pricing", "selection", "betting", "sportybet")
    )
