from __future__ import annotations

import copy

import pytest

from scripts import audit_p4_4l_current_shadow_international_source_hierarchy as audit


def test_p4_4l_receipt_audits_full_hierarchy_and_p4_4k_replay() -> None:
    receipt = audit.audit(check_live=False)
    assert receipt["repository_base_main_sha"] == audit.BASE_MAIN
    assert receipt["policy"]["policy_id"] == (
        "ATHENA_CURRENT_SHADOW_FOTMOB_INTERNATIONAL_SOURCE_HIERARCHY_V1"
    )
    assert receipt["policy"]["policy_sha256"] == (
        "2c6f0a8737520166aa1226e2b2ff0377bc418d4c93856fcef9afc0aacbb884dd"
    )
    coverage = receipt["policy"]["coverage"]
    assert len(coverage) == 12
    assert {row["priority_band"] for row in coverage} == {
        "INT-S", "INT-A", "INT-B", "INT-C", "INT-D", "INT-E", "INT-F", "INT-G"
    }
    active = {
        (item["ccode"], item["primary_id"])
        for row in coverage
        for item in row["active_source_identities"]
    }
    assert active == audit.EXPECTED_ACTIVE_KEYS
    for row in coverage:
        for item in row["active_source_identities"]:
            assert item["evidence"]["workflow_run_id"] == 36136878384
            assert item["evidence"]["artifact_id"] == 10865656841
            assert item["evidence"]["artifact_sha256"] == (
                "3d8733e2bd9ed1ad4eef94b877e22603e1043fa5a658801548223b5c298c48b8"
            )
    assert receipt["policy"]["observed_unqualified_identities"][0]["primary_id"] == 13287

    replay = receipt["p4_4k_offline_replay"]
    assert replay["total_international_candidate_count"] == 44
    assert replay["active_mapped_international_candidate_count"] == 42
    assert replay["source_unqualified_international_candidate_count"] == 2
    assert replay["six_senior_family_candidate_count"] == 30
    assert replay["six_senior_family_lead_eligible_count"] == 23
    assert replay["six_senior_family_lead_excluded_count"] == 7
    assert replay["candidate_counts_by_primary_id"] == {
        "114": 2,
        "9806": 2,
        "9807": 4,
        "9808": 2,
        "9821": 6,
        "9833": 2,
        "10437": 10,
        "10608": 14,
        "13287": 2,
    }
    assert replay["lead_eligible_counts_by_primary_id"] == {
        "114": 1,
        "9806": 2,
        "9807": 4,
        "9808": 2,
        "9821": 2,
        "9833": 0,
        "10437": 10,
        "10608": 12,
        "13287": 0,
    }
    assert replay["current_shadow_policy_approved_count"] == 33
    assert replay["current_shadow_policy_lead_excluded_count"] == 9
    assert replay["current_shadow_policy_pr41_blocked_count"] == 0
    assert replay["current_shadow_policy_stale_source_excluded_count"] == 0
    assert replay["current_shadow_policy_request_date_excluded_count"] == 0


def test_current_architecture_identity_uses_checked_out_head_in_shallow_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_git = audit._git
    calls: list[tuple[str, ...]] = []

    def shallow_git(*args: str) -> bytes:
        calls.append(args)
        if audit.BASE_MAIN in args or any(
            argument.startswith(f"{audit.BASE_MAIN}:") for argument in args
        ):
            raise AssertionError("shallow hosted audit must not require the base object")
        return original_git(*args)

    monkeypatch.setattr(audit, "_git", shallow_git)

    architecture = audit._current_architecture_identity()

    assert ("rev-parse", "HEAD:.github/workflows") in calls
    assert ("ls-tree", "-r", "--name-only", "HEAD", ".github/workflows") in calls
    assert architecture["workflow_tree_sha1"] == audit.WORKFLOW_TREE_SHA1
    assert architecture["workflow_count"] == audit.WORKFLOW_COUNT


@pytest.mark.parametrize(
    ("section", "key", "replacement"),
    [
        ("policy", "policy_sha256", "0" * 64),
        ("scope_semantics", "mixed_club_international_source_card_supported", False),
        ("scope_semantics", "display_name_identity_authority", True),
        ("scope_semantics", "production_source_authority_expanded", True),
        ("scope_semantics", "model_authority_expanded", True),
        ("implementation_scope", "workflow_yaml_changed", True),
        ("implementation_scope", "provider_request_count", 1),
        ("review_governance", "p4_4_overall_complete", True),
        ("review_governance", "architecture_checkpoint_e_complete", True),
    ],
)
def test_receipt_semantic_mutations_fail_closed(section, key, replacement) -> None:
    mutated = copy.deepcopy(audit.expected_receipt())
    mutated[section][key] = replacement
    mutated["canonical_sha256"] = audit._canonical_sha(mutated)
    with pytest.raises(audit.P44LReviewError):
        audit._validate_receipt(mutated)


def test_exact_changed_file_envelope_has_no_workflow_or_runtime_source() -> None:
    assert audit.EXPECTED_CHANGED_PATHS == {
        "artifacts/architecture/p4_4l_current_shadow_international_source_hierarchy_v1.json",
        "domain/current_fotmob_fixture_review_policy.py",
        "domain/current_shadow_fotmob_international_source_identity.py",
        "scripts/audit_p4_4l_current_shadow_international_source_hierarchy.py",
        "tests/test_current_fotmob_fixture_review_policy.py",
        "tests/test_current_shadow_fotmob_international_source_identity.py",
        "tests/test_p4_4l_current_shadow_international_source_hierarchy.py",
    }
    assert not any(path.startswith(".github/workflows/") for path in audit.EXPECTED_CHANGED_PATHS)
    assert "domain/accumulator_priority.py" not in audit.EXPECTED_CHANGED_PATHS
    assert "scripts/execute_current_shadow_request.py" not in audit.EXPECTED_CHANGED_PATHS


def test_architecture_authority_and_governance_stay_bounded() -> None:
    receipt = audit.audit(check_live=False)
    semantics = receipt["scope_semantics"]
    assert semantics["existing_club_resolution_path_unchanged"] is True
    assert semantics["mixed_club_international_source_card_supported"] is True
    assert semantics["pure_club_behavior_unchanged"] is True
    assert semantics["pure_international_current_source_review_supported"] is True
    assert semantics["international_break_mode_introduced"] is False
    assert semantics["calendar_switching_introduced"] is False
    assert semantics["club_international_rank_mixing_introduced"] is False
    assert all(value is False for key, value in semantics.items() if key.endswith("authority") or key.endswith("expanded"))
    gov = receipt["review_governance"]
    assert gov["source_review_counter_while_unmerged"] == "4/5"
    assert gov["source_review_counter_if_merged"] == "5/5"
    assert gov["mandatory_source_reread_after_merge"] is True
    assert gov["p4_4_overall_complete"] is False
    assert gov["architecture_checkpoint_e_complete"] is False
    assert gov["next_live_proof_authorized"] is False
