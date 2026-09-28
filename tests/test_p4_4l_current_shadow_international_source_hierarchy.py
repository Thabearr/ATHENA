from __future__ import annotations

import copy
import json
import socket
import urllib.request

import pytest

from scripts import audit_p4_4l_current_shadow_international_source_hierarchy as audit
from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as p44g
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_p4_4l_receipt_audits_full_hierarchy_and_p4_4k_replay() -> None:
    receipt = audit.audit(check_live=False)
    assert receipt["repository_base_main_sha"] == audit.BASE_MAIN
    assert receipt["policy"]["policy_id"] == (
        "ATHENA_CURRENT_SHADOW_FOTMOB_INTERNATIONAL_SOURCE_HIERARCHY_V1"
    )
    assert receipt["policy"]["policy_sha256"] == (
        "f4a50b836540d4dd797631f50215598d852aab05a9c2e9a65ff8069afcde570b"
    )
    assert receipt["policy"]["cross_path_identity_conflict_rule"] == (
        "FAIL_CLOSED_WHEN_KNOWN_P4_4L_PRIMARY_ID_CONFLICTS_WITH_EXISTING_SOURCE_NAME_RESOLUTION"
    )
    assert receipt["policy"]["unknown_primary_id_preserves_existing_reviewed_source_name_path"] is True
    assert receipt["policy"]["observed_unqualified_primary_id_cannot_be_reclassified_by_source_name"] is True
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
    assert architecture["workflow_tree_sha1"] == original_git(
        "rev-parse", "HEAD:.github/workflows"
    ).decode("ascii").strip()
    assert architecture["workflow_count"] == audit.WORKFLOW_COUNT
    ledger = evolution.validate_current_state()
    assert architecture["workflow_evolution_transition_count"] == len(ledger["transitions"])
    assert architecture["workflow_evolution_ledger_sha256"] == ledger["canonical_sha256"]
    assert architecture["workflow_tree_sha1"] == ledger["current_workflow_tree_sha1"]
    assert architecture["workflow_count"] == ledger["current_live_workflow_count"]


def test_source_identity_hashes_committed_blob_bytes_across_checkout_line_endings() -> None:
    path = "domain/current_shadow_fotmob_international_source_identity.py"
    committed_bytes = audit._git("show", f"HEAD:{path}")

    source_identity = audit._source_identity(path)

    assert source_identity["git_blob_sha1"] == audit._git(
        "rev-parse", f"HEAD:{path}"
    ).decode("ascii").strip()
    assert source_identity["source_sha256"] == audit._sha256(committed_bytes)


def test_historical_p44l_source_identities_are_not_derived_from_current_head() -> None:
    receipt = audit.audit(check_live=False)
    assert receipt["canonical_sha256"] == (
        "15f8b85ba2ef5c9a8dd65fa262eb44a49b61070040cd7ea09985416c063cd91f"
    )
    assert receipt["source_identity"] == audit.P44L_HISTORICAL_SOURCE_IDENTITIES
    for path, expected in audit.P44L_HISTORICAL_SOURCE_IDENTITIES.items():
        audit._verify_historical_source_identity(
            path,
            expected,
            trusted_current_ci=True,
            receipt=receipt,
        )


def test_current_source_change_does_not_rewrite_historical_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit,
        "_source_identity",
        lambda *_args: pytest.fail("historical receipt must not be rebuilt from current source"),
    )
    receipt = audit.expected_receipt()
    assert receipt["canonical_sha256"] == (
        "15f8b85ba2ef5c9a8dd65fa262eb44a49b61070040cd7ea09985416c063cd91f"
    )


def test_historical_six_transition_checkpoint_is_an_exact_prefix_with_later_revisions() -> None:
    historical = p44g._load_json(p44g.SNAPSHOT_PATH)
    current = evolution.validate_current_state()
    later = copy.deepcopy(current)
    later["transitions"].append({"transition_id": "synthetic-later-reviewed-revision"})

    audit._verify_historical_evolution_prefix(later, historical)

    rewritten = copy.deepcopy(later)
    rewritten["transitions"][0]["transition_id"] = "rewritten-history"
    with pytest.raises(audit.P44LReviewError, match="exact P4.4L prefix"):
        audit._verify_historical_evolution_prefix(rewritten, historical)


def test_historical_evolution_checkpoint_hash_and_count_remain_exact() -> None:
    historical = p44g._load_json(p44g.SNAPSHOT_PATH)
    current = evolution.validate_current_state()
    wrong_hash = copy.deepcopy(historical)
    wrong_hash["canonical_sha256"] = "0" * 64
    with pytest.raises(audit.P44LReviewError, match="checkpoint identity"):
        audit._verify_historical_evolution_prefix(current, wrong_hash)

    wrong_count = copy.deepcopy(historical)
    wrong_count["transitions"].pop()
    with pytest.raises(audit.P44LReviewError, match="checkpoint identity"):
        audit._verify_historical_evolution_prefix(current, wrong_count)


def test_current_workflow_tree_and_count_are_bound_to_cumulative_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = evolution.validate_current_state()
    calls: list[tuple[str, ...]] = []

    def git(*args: str) -> bytes:
        calls.append(args)
        if args == ("rev-parse", "HEAD:.github/workflows"):
            return (current["current_workflow_tree_sha1"] + "\n").encode()
        if args[:4] == ("ls-tree", "-r", "--name-only", "HEAD"):
            return b"\n".join(
                [b".github/workflows/workflow.yml"] * current["current_live_workflow_count"]
            )
        raise AssertionError(args)

    monkeypatch.setattr(audit, "_git", git)
    audit._verify_current_workflow_state(current)
    assert ("rev-parse", "HEAD:.github/workflows") in calls

    with pytest.raises(audit.P44LReviewError, match="current workflow tree"):
        audit._verify_current_workflow_state(
            {**current, "current_workflow_tree_sha1": "0" * 40}
        )


def test_historical_workflow_tree_is_checked_at_reviewed_revision_not_current_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit, "_commit_object_available", lambda ref: ref == audit.P44L_REVIEWED_HEAD
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: (audit.WORKFLOW_TREE_SHA1 + "\n").encode()
        if args == ("rev-parse", f"{audit.P44L_REVIEWED_HEAD}:.github/workflows")
        else pytest.fail(f"unexpected Git command {args}"),
    )
    audit._verify_historical_workflow_tree(trusted_current_ci=False)

    monkeypatch.setattr(
        audit,
        "_git",
        lambda *_args: ("0" * 40 + "\n").encode(),
    )
    with pytest.raises(audit.P44LReviewError, match="historical workflow tree differs"):
        audit._verify_historical_workflow_tree(trusted_current_ci=False)


def test_historical_source_mutation_fails_without_substituting_current_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, expected = next(iter(audit.P44L_HISTORICAL_SOURCE_IDENTITIES.items()))
    monkeypatch.setattr(
        audit, "_commit_object_available", lambda ref: ref == audit.P44L_REVIEWED_HEAD
    )
    seen_refs: list[str] = []

    def historical_identity(source_path: str, ref: str) -> dict[str, str]:
        assert source_path == path
        seen_refs.append(ref)
        return dict(expected)

    monkeypatch.setattr(audit, "_source_identity", historical_identity)
    audit._verify_historical_source_identity(
        path,
        expected,
        trusted_current_ci=False,
        receipt={"source_identity": {path: expected}},
    )
    assert seen_refs == [audit.P44L_REVIEWED_HEAD]

    monkeypatch.setattr(audit, "_source_identity", lambda *_args: {**expected, "source_sha256": "0" * 64})
    with pytest.raises(audit.P44LReviewError, match="historical source identity differs"):
        audit._verify_historical_source_identity(
            path,
            expected,
            trusted_current_ci=False,
            receipt={"source_identity": {path: expected}},
        )


def test_trusted_shallow_pull_request_does_not_bind_to_historical_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "repository": {"full_name": "Thabearr/ATHENA"},
                "pull_request": {
                    "base": {"ref": "main", "sha": "a" * 40},
                    "head": {"sha": "b" * 40},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "Thabearr/ATHENA")
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    monkeypatch.setattr(audit, "_git", lambda *args: ("c" * 40 + "\n").encode())

    audit._require_trusted_current_ci_context()


def test_untrusted_missing_historical_ancestry_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setattr(audit, "_commit_object_available", lambda _ref: False)
    with pytest.raises(audit.P44LReviewError, match="unavailable outside trusted shallow CI"):
        audit._verify_historical_review_ancestry(trusted_current_ci=False)


def test_historical_changed_file_scope_uses_reviewed_head_not_current_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audit, "_commit_object_available", lambda _ref: True)
    seen: list[tuple[str, ...]] = []

    def git(*args: str) -> bytes:
        seen.append(args)
        assert args == ("diff", "--name-only", f"{audit.BASE_MAIN}...{audit.P44L_REVIEWED_HEAD}")
        return ("\n".join(sorted(audit.EXPECTED_CHANGED_PATHS)) + "\n").encode()

    monkeypatch.setattr(audit, "_git", git)
    audit._verify_historical_changed_paths(trusted_current_ci=False)
    assert seen == [("diff", "--name-only", f"{audit.BASE_MAIN}...{audit.P44L_REVIEWED_HEAD}")]

    monkeypatch.setattr(audit, "_git", lambda *_args: b"unexpected.py\n")
    with pytest.raises(audit.P44LReviewError, match="historical changed-file scope"):
        audit._verify_historical_changed_paths(trusted_current_ci=False)


def test_historical_merge_parents_and_current_ancestry_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit,
        "_commit_object_available",
        lambda ref: ref == audit.P44L_MERGE_COMMIT,
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: f"{audit.BASE_MAIN} {audit.P44L_REVIEWED_HEAD}\n".encode()
        if args == ("show", "-s", "--format=%P", audit.P44L_MERGE_COMMIT)
        else pytest.fail(f"unexpected Git command {args}"),
    )
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda args, **_kwargs: type("Result", (), {"returncode": 0})()
        if args == ["git", "merge-base", "--is-ancestor", audit.P44L_MERGE_COMMIT, "HEAD"]
        else pytest.fail(f"unexpected subprocess {args}"),
    )
    audit._verify_historical_review_ancestry(trusted_current_ci=False)

    monkeypatch.setattr(
        audit,
        "_git",
        lambda *_args: f"{audit.BASE_MAIN} {'0' * 40}\n".encode(),
    )
    with pytest.raises(audit.P44LReviewError, match="exact reviewed base/head"):
        audit._verify_historical_review_ancestry(trusted_current_ci=False)


def test_p44l_offline_audit_performs_no_network_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def denied(*_args, **_kwargs):
        calls.append("network")
        raise AssertionError("P4.4L audit attempted network access")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    assert audit.audit(check_live=False)["canonical_sha256"] == (
        "15f8b85ba2ef5c9a8dd65fa262eb44a49b61070040cd7ea09985416c063cd91f"
    )
    assert calls == []


def test_qualification_evidence_hash_uses_committed_blob_bytes() -> None:
    receipt = audit.expected_receipt()
    committed_bytes = audit._git(
        "show", f"HEAD:{audit.PRIMARY_ID_QUALIFICATION_PATH}"
    )

    assert receipt["evidence_inventory"]["checked_in_primary_id_qualification"][
        "file_sha256"
    ] == audit._sha256(committed_bytes)


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
