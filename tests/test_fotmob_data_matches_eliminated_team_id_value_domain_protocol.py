from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from domain.fotmob_data_matches_capture import (
    sha256_data_matches_capture_manifest,
    verify_data_matches_capture_directory,
)
from domain.fotmob_data_matches_eliminated_team_id_value_domain_protocol import (
    ENDPOINT_TEAM_ID_EQUALITY_REQUIRED,
    FINAL_RESULT_SEMANTICS_QUALIFIED,
    FIRST_CAPTURE_ID,
    FIRST_NON_NULL_COUNT,
    FIRST_RAW_BLOB_SHA,
    NEXT_REQUIRED_BOUNDARY,
    NON_NULL_EXACT_TYPE,
    NON_NULL_MINIMUM,
    NULL_ALLOWED,
    OBSERVED_AWAY_TEAM_ID,
    OBSERVED_FIXTURE_ID,
    OBSERVED_HOME_TEAM_ID,
    OBSERVED_LEAGUE_ID,
    OBSERVED_NON_NULL_VALUE,
    OBSERVED_STATUS_ID,
    PROTOCOL_ID,
    PROTOCOL_SHA256,
    PROTOCOL_SCOPE,
    PROTOCOL_SIZE,
    PROTOCOL_STATE,
    QUALIFICATION_REQUIREMENTS,
    REPOSITORY_MAIN_SHA,
    SECOND_CAPTURE_ID,
    SECOND_NON_NULL_COUNT,
    SECOND_RAW_BLOB_SHA,
    SEMANTIC_MEANING_QUALIFIED,
    STATUS_REASON_SEMANTICS_QUALIFIED,
    STATUS_VOCABULARY,
    FotMobDataMatchesEliminatedTeamIdValueDomainProtocolError,
    build_fotmob_data_matches_eliminated_team_id_value_domain_protocol,
    canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes,
    revalidate_fotmob_data_matches_eliminated_team_id_value_domain_protocol,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence" / "fotmob_data_matches" / "pr83_post_finish_pair"
DATE_ROOT = EVIDENCE_ROOT / "20260814"
PR39_BLOB = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
PR85_EVIDENCE_BLOB = "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
PR86_PROTOCOL_BLOB = "71b2f1a8add05929835d469df94396375a115391"
PR87_IMPLEMENTATION_BLOB = "fc120476739293abbb5db4374a0b4d7cfe8a1fc3"
FIRST_RAW_SHA256 = "fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
SECOND_RAW_SHA256 = "175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
FIRST_MANIFEST_SHA256 = "27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"
SECOND_MANIFEST_SHA256 = "d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "eliminated_team_id_value_domain_implementation_authorized",
    "eliminated_team_id_value_domain_qualified",
    "eliminated_team_id_semantics_qualified",
    "pr39_schema_mutation_authorized",
    "pr87_implementation_mutation_authorized",
    "status_reason_semantics_qualified",
    "final_result_semantics_qualified",
    "source_capability_update_authorized",
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


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _load_capture(capture_id: str):
    capture_dir = DATE_ROOT / capture_id
    manifest = verify_data_matches_capture_directory(
        capture_dir,
        allowed_root=EVIDENCE_ROOT,
        require_network_acquisition_performed=True,
    )
    raw = (capture_dir / "response.json").read_bytes()
    return raw, manifest


def _non_null_observations(raw: bytes) -> list[dict[str, Any]]:
    payload = json.loads(raw)
    observations: list[dict[str, Any]] = []
    for league in payload["leagues"]:
        for match in league["matches"]:
            value = match["eliminatedTeamId"]
            if value is None:
                continue
            observations.append(
                {
                    "fixture_id": match["id"],
                    "league_id": match["leagueId"],
                    "home_team_id": match["home"]["id"],
                    "away_team_id": match["away"]["id"],
                    "value": value,
                    "status_id": match["statusId"],
                    "reason": dict(match["status"].get("reason", {})),
                }
            )
    return observations


def test_exact_main_and_upstream_blob_ancestry_is_frozen() -> None:
    assert REPOSITORY_MAIN_SHA == "f72ac2210945e35f04b7413e2c31480f027addf0"
    assert _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_schema.py") == PR39_BLOB
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_post_finish_capture_pair_evidence.py")
        == PR85_EVIDENCE_BLOB
    )
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_terminal_state_schema_extension_protocol.py")
        == PR86_PROTOCOL_BLOB
    )
    assert (
        _git_blob_sha(ROOT / "domain" / "fotmob_data_matches_terminal_state_schema_extension.py")
        == PR87_IMPLEMENTATION_BLOB
    )


def test_exact_pr85_raw_blob_and_manifest_lineage_is_frozen() -> None:
    expected = (
        (
            FIRST_CAPTURE_ID,
            FIRST_RAW_BLOB_SHA,
            FIRST_RAW_SHA256,
            FIRST_MANIFEST_SHA256,
        ),
        (
            SECOND_CAPTURE_ID,
            SECOND_RAW_BLOB_SHA,
            SECOND_RAW_SHA256,
            SECOND_MANIFEST_SHA256,
        ),
    )
    for capture_id, blob_sha, raw_sha, manifest_sha in expected:
        capture_dir = DATE_ROOT / capture_id
        assert _git_blob_sha(capture_dir / "response.json") == blob_sha
        raw, manifest = _load_capture(capture_id)
        assert hashlib.sha256(raw).hexdigest() == raw_sha
        assert manifest.raw_sha256 == raw_sha
        assert sha256_data_matches_capture_manifest(manifest) == manifest_sha


def test_both_exact_captures_have_one_same_non_null_observation() -> None:
    first_raw, _ = _load_capture(FIRST_CAPTURE_ID)
    second_raw, _ = _load_capture(SECOND_CAPTURE_ID)
    first = _non_null_observations(first_raw)
    second = _non_null_observations(second_raw)

    assert len(first) == FIRST_NON_NULL_COUNT == 1
    assert len(second) == SECOND_NON_NULL_COUNT == 1
    assert first == second
    assert first[0] == {
        "fixture_id": OBSERVED_FIXTURE_ID,
        "league_id": OBSERVED_LEAGUE_ID,
        "home_team_id": OBSERVED_HOME_TEAM_ID,
        "away_team_id": OBSERVED_AWAY_TEAM_ID,
        "value": OBSERVED_NON_NULL_VALUE,
        "status_id": OBSERVED_STATUS_ID,
        "reason": {
            "short": "Pen",
            "shortKey": "penalties_short",
            "long": "After penalties",
            "longKey": "afterpenalties",
        },
    }
    assert OBSERVED_NON_NULL_VALUE == OBSERVED_HOME_TEAM_ID == 6576
    assert OBSERVED_AWAY_TEAM_ID == 1218886


def test_observed_relationship_is_recorded_but_not_universalized() -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    assert value.observed_value_equals_home_team_id is True
    assert ENDPOINT_TEAM_ID_EQUALITY_REQUIRED is False
    assert value.endpoint_team_id_equality_required is False
    assert SEMANTIC_MEANING_QUALIFIED is False
    assert value.semantic_meaning_qualified is False
    assert value.penalty_relationship_qualified is False
    assert value.winner_loser_relationship_qualified is False
    assert STATUS_REASON_SEMANTICS_QUALIFIED is False
    assert FINAL_RESULT_SEMANTICS_QUALIFIED is False


def test_structural_domain_is_null_or_exact_positive_integer_only() -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    assert NULL_ALLOWED is True and value.null_allowed is True
    assert NON_NULL_EXACT_TYPE == value.non_null_exact_type == "INT_EXCLUDING_BOOL"
    assert NON_NULL_MINIMUM == value.non_null_minimum == 1
    assert "WHEN_NON_NULL_REQUIRE_EXACT_INTEGER_EXCLUDING_BOOL" in QUALIFICATION_REQUIREMENTS
    assert "WHEN_NON_NULL_REQUIRE_VALUE_GREATER_THAN_OR_EQUAL_TO_ONE" in QUALIFICATION_REQUIREMENTS


def test_exact_protocol_identity_and_state() -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    exact = canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes(value)
    assert PROTOCOL_ID == "FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION_PROTOCOL_V1"
    assert PROTOCOL_SCOPE == "PRE_REGISTERED_REVIEWED_ELIMINATED_TEAM_ID_STRUCTURAL_VALUE_DOMAIN_ONLY"
    assert PROTOCOL_STATE == "PRE_REGISTERED_NOT_IMPLEMENTED_NO_SEMANTIC_PROMOTION"
    assert hashlib.sha256(exact).hexdigest() == PROTOCOL_SHA256
    assert len(exact) == PROTOCOL_SIZE == 4276
    assert revalidate_fotmob_data_matches_eliminated_team_id_value_domain_protocol(value) == value


def test_status_vocabulary_and_next_boundary_are_exact() -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    assert value.status_vocabulary == STATUS_VOCABULARY == (
        "QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN",
        "BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT",
        "BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT",
        "BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH",
        "BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER",
    )
    assert value.next_required_boundary == NEXT_REQUIRED_BOUNDARY == (
        "IMPLEMENT_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION"
    )


def test_all_authority_stays_exact_false() -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    assert set(value.safety) == SAFETY_KEYS
    assert all(type(flag) is bool and flag is False for flag in value.safety.values())
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_data_matches_reviewed_catalog"]
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("schema_version", True),
        ("first_non_null_count", 0),
        ("second_non_null_count", 2),
        ("non_null_minimum", 0),
        ("observed_non_null_value", True),
        ("endpoint_team_id_equality_required", True),
        ("semantic_meaning_qualified", True),
        ("status_reason_semantics_qualified", True),
        ("final_result_semantics_qualified", True),
    ),
)
def test_protocol_mutation_fails_closed(field: str, bad: Any) -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainProtocolError):
        dataclasses.replace(value, **{field: bad})


def test_safety_mutation_fails_closed_and_is_detached() -> None:
    value = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    safety = dict(value.safety)
    safety["bet_authorized"] = True
    with pytest.raises(FotMobDataMatchesEliminatedTeamIdValueDomainProtocolError):
        dataclasses.replace(value, safety=safety)
    with pytest.raises(TypeError):
        value.safety["bet_authorized"] = True  # type: ignore[index]


def test_protocol_has_no_network_or_downstream_runtime_imports() -> None:
    path = ROOT / "domain" / "fotmob_data_matches_eliminated_team_id_value_domain_protocol.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(
        {"requests", "httpx", "aiohttp", "providers", "engine", "models", "services", "workers"}
    )
