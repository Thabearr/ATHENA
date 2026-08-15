from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import domain.fotmob_data_matches_full_time_score_capability_promotion_assessment as pr94
import domain.fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter as subject
import domain.fotmob_data_matches_full_time_score_capability_promotion_protocol as pr93
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as pr95
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter_validation as pr96
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


def _blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"HEAD:{path}"],
        text=True,
    ).strip()


def _plain_receipt() -> dict:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    exact = subject.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(
        receipt
    )
    return json.loads(exact)


def test_exact_upstream_git_blob_ancestry_is_frozen() -> None:
    assert _blob("domain/fotmob_data_matches_full_time_score_capability_promotion_protocol.py") == subject.PR93_PROTOCOL_BLOB_SHA
    assert _blob("domain/fotmob_data_matches_full_time_score_capability_promotion_assessment.py") == subject.PR94_ASSESSMENT_BLOB_SHA
    assert _blob("domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py") == subject.PR95_ADAPTER_BLOB_SHA
    assert subject.PR96_VALIDATION_BLOB_SHA == "d6ad05c778669b976c4a475080da845cc8bf47cb"
    assert subject.SOURCE_CAPABILITIES_BLOB_SHA == "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"


def test_pr93_and_pr94_canonical_ancestry_revalidate() -> None:
    protocol = pr93.build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    protocol_bytes = pr93.canonical_fotmob_data_matches_full_time_score_capability_promotion_protocol_bytes(
        protocol
    )
    assert hashlib.sha256(protocol_bytes).hexdigest() == subject.PR93_PROTOCOL_SHA256
    assert len(protocol_bytes) == subject.PR93_PROTOCOL_SIZE

    old = pr94.build_fotmob_data_matches_full_time_score_capability_promotion_assessment()
    old_bytes = pr94.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_bytes(old)
    assert hashlib.sha256(old_bytes).hexdigest() == subject.PR94_ASSESSMENT_SHA256
    assert len(old_bytes) == subject.PR94_ASSESSMENT_SIZE
    assert old.primary_status == "BLOCKED_REUSABLE_REVIEWED_SCORE_ADAPTER_NOT_IMPLEMENTED"
    assert old.registration_qualified is False
    assert old.registry_update_performed is False


def test_pr95_adapter_and_pr96_validation_exactly_resolve_old_blocker() -> None:
    assert pr95.ADAPTER_STATE == subject.PR95_ADAPTER_STATE
    assert pr95.PARENT_SOURCE_KEY == subject.PARENT_SOURCE_KEY
    assert pr95.FUTURE_DERIVED_SOURCE_KEY == subject.PROPOSED_SOURCE_KEY
    assert pr96.RECEIPT_SHA256 == subject.PR96_RECEIPT_SHA256
    assert pr96.RECEIPT_SIZE == subject.PR96_RECEIPT_SIZE
    assert pr96.ADAPTER_RESULT_SHA256 == subject.PR96_ADAPTER_RESULT_SHA256
    assert (
        pr96.QUALIFIED_SCORES_PROJECTION_SHA256
        == subject.PR96_QUALIFIED_SCORES_PROJECTION_SHA256
    )
    assert pr96.TERMINAL_CANDIDATE_UNION_COUNT == 29
    assert pr96.QUALIFIED_COUNT == 28
    assert pr96.PENALTY_FIXTURE_ID == 5844873


def test_assessment_qualifies_only_the_derived_registry_registration() -> None:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    assert receipt["assessment_state"] == subject.ASSESSMENT_STATE
    assert receipt["primary_status"] == subject.PRIMARY_STATUS
    assert subject.PRIMARY_STATUS in pr93.STATUS_VOCABULARY
    assert receipt["reusable_adapter_implemented"] is True
    assert receipt["reusable_adapter_validation_qualified"] is True
    assert receipt["parent_source_capability_matches_protocol"] is True
    assert receipt["scope_and_penalty_exclusion_match_protocol"] is True
    assert receipt["registration_qualified"] is True
    assert receipt["registry_update_performed"] is False
    assert receipt["next_required_boundary"] == (
        "REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_CAPABILITY"
    )


def test_exact_evidence_counts_and_penalty_exclusion_remain_frozen() -> None:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    assert receipt["terminal_candidate_union_count"] == 29
    assert receipt["qualified_ordinary_ft_count"] == 28
    assert receipt["excluded_penalty_count"] == 1
    assert receipt["excluded_penalty_fixture_id"] == 5844873
    validation_gate = next(
        item for item in receipt["gate_results"] if item["gate_id"] == "REUSABLE_ADAPTER_VALIDATION"
    )
    assert validation_gate["outcome"] == "PASS"
    assert "5844873" in validation_gate["reason"]


def test_parent_registry_remains_identity_only_and_pre_registration_absence_stays_historical() -> None:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    parent = SOURCE_CAPABILITY_REGISTRY[subject.PARENT_SOURCE_KEY]
    derived = SOURCE_CAPABILITY_REGISTRY[subject.PROPOSED_SOURCE_KEY]
    assert parent.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert parent.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert parent.historical_coverage is CapabilityAvailability.UNKNOWN
    assert derived.full_time_score is CapabilityAvailability.CONFIRMED
    assert receipt["proposed_source_key_present_before_registration"] is False
    assert receipt["parent_capabilities"] == {
        "full_time_score": "NOT_CAPTURED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }


def test_proposed_capability_is_exactly_pr93_scoped_contract() -> None:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    protocol = pr93.build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    assert dict(receipt["proposed_capabilities"]) == dict(protocol.proposed_capabilities)
    assert receipt["promotion_mode"] == protocol.promotion_mode
    assert receipt["promotion_scope_rule"] == protocol.promotion_scope_rule
    assert receipt["proposed_capabilities"]["full_time_score"] == "CONFIRMED"
    assert receipt["proposed_capabilities"]["historical_coverage"] == "UNKNOWN"
    assert receipt["proposed_capabilities"]["freshness_metadata"] == "NOT_CAPTURED"


def test_all_gate_results_are_explicit_and_registry_update_is_historical_not_performed() -> None:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    gates = {item["gate_id"]: item for item in receipt["gate_results"]}
    assert tuple(gates) == (
        "PR93_PROTOCOL_ANCESTRY",
        "PARENT_SOURCE_CAPABILITY",
        "PROPOSED_SOURCE_KEY_ABSENCE",
        "REUSABLE_PROSPECTIVE_SCORE_ADAPTER",
        "REUSABLE_ADAPTER_VALIDATION",
        "CAPABILITY_SCOPE_AND_PENALTY_EXCLUSION",
        "DERIVED_CAPABILITY_REGISTRATION_QUALIFICATION",
        "SOURCE_CAPABILITY_REGISTRY_UPDATE",
    )
    assert all(gates[name]["outcome"] == "PASS" for name in tuple(gates)[:-1])
    assert gates["SOURCE_CAPABILITY_REGISTRY_UPDATE"]["outcome"] == "NOT_PERFORMED"


def test_every_safety_flag_remains_exact_false() -> None:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    assert receipt["safety"]
    assert all(type(value) is bool and value is False for value in receipt["safety"].values())
    assert receipt["safety"]["source_capability_registry_update_authorized"] is False
    assert receipt["safety"]["source_capability_registry_update_performed"] is False
    assert receipt["safety"]["bet_authorized"] is False


def test_receipt_and_nested_structures_are_immutable() -> None:
    receipt = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    with pytest.raises(TypeError):
        receipt["registration_qualified"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        receipt["parent_capabilities"]["full_time_score"] = "CONFIRMED"  # type: ignore[index]
    with pytest.raises(TypeError):
        receipt["proposed_capabilities"]["historical_coverage"] = "CONFIRMED"  # type: ignore[index]
    with pytest.raises(TypeError):
        receipt["gate_results"][0]["outcome"] = "BLOCKED"  # type: ignore[index]
    with pytest.raises(TypeError):
        receipt["safety"]["bet_authorized"] = True  # type: ignore[index]


def test_canonical_receipt_identity_is_exact_and_deterministic() -> None:
    first = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    second = subject.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    first_bytes = subject.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(
        first
    )
    second_bytes = subject.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(
        second
    )
    assert first_bytes == second_bytes
    assert hashlib.sha256(first_bytes).hexdigest() == subject.ASSESSMENT_SHA256
    assert len(first_bytes) == subject.ASSESSMENT_SIZE
    assert (
        subject.sha256_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter(
            first
        )
        == subject.ASSESSMENT_SHA256
    )


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("registration_qualified",), False),
        (("registry_update_performed",), True),
        (("excluded_penalty_fixture_id",), 1),
        (("proposed_capabilities", "historical_coverage"), "CONFIRMED"),
        (("proposed_capabilities", "full_time_score"), "UNKNOWN"),
        (("gate_results", 4, "outcome"), "BLOCKED"),
        (("safety", "pricing_authorized"), True),
    ],
)
def test_mutated_receipts_fail_closed(path: tuple[object, ...], replacement: object) -> None:
    mutated = _plain_receipt()
    cursor: object = mutated
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = replacement  # type: ignore[index]
    with pytest.raises(
        subject.FotMobDataMatchesFullTimeScoreCapabilityPromotionValidatedAdapterAssessmentError
    ):
        subject.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(
            mutated
        )


def test_assessment_module_has_no_network_or_downstream_execution_imports() -> None:
    source_path = Path(subject.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith(("requests", "httpx", "urllib", "selenium", "playwright")) for name in imported)
    assert not any(
        name.startswith(
            (
                "engine",
                "models",
                "providers",
                "services.pricing",
                "workers",
                "build_acca",
            )
        )
        for name in imported
    )
