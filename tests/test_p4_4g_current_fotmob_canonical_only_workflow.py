from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution


def _receipt() -> dict:
    return audit.expected_receipt()


def _rehash(value: dict) -> None:
    value["canonical_sha256"] = evolution.canonical_sha256(value)


def test_p4_4g_transition_and_cumulative_snapshot_are_exact() -> None:
    ledger, snapshot, receipt = audit.build_evidence()
    transition = ledger["transitions"][5]
    assert snapshot == ledger
    assert len(ledger["transitions"]) == 6
    assert ledger["current_live_workflow_count"] == 38
    assert ledger["current_p4_3_retired_workflow_count"] == 3
    assert transition["transition_id"] == audit.TRANSITION_ID
    assert transition["operation"] == "MAINTENANCE_REVISE"
    assert transition["phase_id"] == "P4.4G"
    assert transition["workflow_path"] == audit.WORKFLOW_PATH
    assert transition["canonical_family"] == "ATHENA_INGEST_FUTURE"
    assert transition["before"] == audit.WORKFLOW_BEFORE
    assert transition["after"] == audit.WORKFLOW_AFTER
    assert transition["maintenance_contract"] == evolution.MAINTENANCE_CONTRACT
    assert transition["historical_before_fixture"]["path"] == audit.FIXTURE_PATH
    assert receipt["workflow_evolution_ledger_sha256"] == ledger["canonical_sha256"]
    assert receipt["canonical_sha256"] == "af0e87fc9fc925d1c30f5f2adee699be0724fa1b68842963f25c5a1f56fe12af"
    assert ledger["canonical_sha256"] == "b9ee60aa5cfa63080159cae839ca82b5662fdfbfe70a91055392a1728ed05f7a"
    assert receipt["p4_3_retirement_ledger_sha256"] == "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
    assert receipt["workflow_tree_sha1_after"] == "d58f71b9ac653c8762f1d9b18eede15755ee1a76"
    assert receipt["workflow_count_after"] == 38
    assert evolution.receipt_evidence_body_sha256(receipt) == transition["evidence_body_sha256"]
    assert receipt["reviewed_workflow_transition"] == {
        key: value for key, value in transition.items() if key != "evidence_body_sha256"
    }


def test_p4_4g_receipt_binds_history_and_scope_narrowing() -> None:
    receipt = audit.validate_receipt(_receipt())
    assert receipt["workflow_run_history_path"] == audit.HISTORY_PATH.as_posix()
    assert receipt["workflow_run_history_sha256"] == audit.HISTORY_SHA256
    assert receipt["historical_workflow_run_count"] == 12
    assert receipt["historical_workflow_dispatch_run_count"] == 12
    assert receipt["historical_exact_utc_nga_run_count"] == 12
    assert receipt["historical_noncanonical_timezone_or_ccode3_run_count"] == 0
    assert receipt["history_is_not_future_capability_authority"] is True
    assert receipt["legacy_noncanonical_lane_retained"] is False
    assert receipt["legacy_live_issuer_still_reachable_from_workflow"] is False
    assert receipt["legacy_cli_retained"] is True
    assert receipt["legacy_cli_modified"] is False
    assert receipt["legacy_cli_deletion_authorized"] is False
    assert receipt["full_legacy_workflow_equivalence_claimed"] is False
    assert receipt["legacy_workflow_retirement_authorized"] is False
    assert receipt["noncanonical_workflow_request_policy"] == "FAIL_CLOSED_NO_PROVIDER_ACQUISITION"
    assert receipt["noncanonical_failure_receipt_binds_request"] is True
    assert receipt["noncanonical_provider_request_count"] == 0
    assert receipt["workflow_supported_provider_scope_narrowed"] is True
    assert receipt["owner_merge_required_to_activate_scope_narrowing"] is True
    assert receipt["provider_acquisition_during_pr"] is False
    assert receipt["provider_request_count_during_pr"] == 0
    assert receipt["workflow_dispatch_during_pr"] is False
    assert receipt["new_live_operational_proof_required"] is False
    assert receipt["p4_4f_operational_proof_reused"] is True
    assert receipt["source_review_counter_while_unmerged"] == "3/5"
    assert receipt["source_review_counter_if_merged"] == "4/5"
    assert receipt["p4_4_overall_complete"] is False
    assert receipt["architecture_checkpoint_e_complete"] is False
    assert all(receipt[field] is False for field in audit.FALSE_AUTHORITY_FIELDS)


def test_p4_4g_history_evidence_is_exact_utc_nga_only() -> None:
    history = audit._check_history_evidence()
    assert history["api_reported_total_count"] == 12
    assert history["all_api_returned_runs_included"] is True
    assert history["observed_run_count"] == 12
    assert history["successful_run_count"] == 11
    assert history["failed_run_count"] == 1
    assert history["run_inputs_observed_from_authenticated_job_logs"] is True
    assert history["provider_acquisition_performed_by_review"] is False
    assert history["workflow_dispatch_performed_by_review"] is False
    assert {row["timezone"] for row in history["runs"]} == {"UTC"}
    assert {row["ccode3"] for row in history["runs"]} == {"NGA"}


def test_p4_4g_reuses_frozen_p4_4f_operational_proof_without_new_live_action() -> None:
    proof = audit._check_operational_proof()
    assert proof["compositional_operational_proof_complete"] is True
    assert proof["second_live_provider_attempt_performed"] is False
    assert proof["authorization"]["provider_request_budget"] == 1
    assert proof["live_attempt"]["provider_request_count"] == 1
    assert proof["live_attempt"]["retry_count"] == 0
    assert proof["live_attempt"]["workflow_dispatch_count"] == 0
    assert proof["offline_continuation"]["provider_request_count"] == 0
    assert proof["offline_continuation"]["provider_request_count_by_adapter"] == 0
    assert proof["offline_continuation"]["approved_count"] == 26
    assert proof["offline_continuation"]["wager_placed"] is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("p4_4f_receipt_sha256", "f" * 64),
        ("p4_4f_workflow_evolution_snapshot_sha256", "f" * 64),
        ("workflow_run_history_sha256", "f" * 64),
        ("workflow_before_identity", {"git_blob_sha1": "0" * 40, "source_sha256": "0" * 64}),
        ("workflow_after_identity", {"git_blob_sha1": "0" * 40, "source_sha256": "0" * 64}),
        ("workflow_count_after", 39),
        ("workflow_tree_sha1_after", "0" * 40),
        ("workflow_evolution_transition_count_after", 5),
        ("transition_operation", "REVISE"),
        ("legacy_noncanonical_lane_retained", True),
        ("legacy_live_issuer_still_reachable_from_workflow", True),
        ("legacy_cli_retained", False),
        ("legacy_cli_deletion_authorized", True),
        ("noncanonical_workflow_request_policy", "LEGACY_NETWORK_FALLBACK"),
        ("noncanonical_failure_receipt_binds_request", False),
        ("noncanonical_provider_request_count", 1),
        ("trigger_surface_changed", True),
        ("provider_acquisition_authority_changed", True),
        ("workflow_supported_provider_scope_narrowed", False),
        ("owner_merge_required_to_activate_scope_narrowing", False),
        ("provider_acquisition_during_pr", True),
        ("provider_request_count_during_pr", 1),
        ("workflow_dispatch_during_pr", True),
        ("new_live_operational_proof_required", True),
        ("p4_4f_operational_proof_reused", False),
        ("source_review_counter_while_unmerged", "4/5"),
        ("source_review_counter_if_merged", "5/5"),
        ("p4_4_overall_complete", True),
        ("architecture_checkpoint_e_complete", True),
        ("reviewed_workflow_transition", {}),
    ] + [(field, True) for field in audit.FALSE_AUTHORITY_FIELDS],
)
def test_self_rehashed_semantic_receipt_mutations_fail(field: str, replacement) -> None:
    mutated = copy.deepcopy(_receipt())
    mutated[field] = replacement
    _rehash(mutated)
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit.validate_receipt(mutated)


def test_exact_receipt_fields_and_duplicate_json_keys_fail(tmp_path: Path) -> None:
    value = copy.deepcopy(_receipt())
    value.pop("workflow_run_history_sha256")
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit.validate_receipt(value)

    raw = audit.canonical_json_bytes(_receipt())
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(
        raw.replace(
            b'{"acquisition_retry_added":false,',
            b'{"acquisition_retry_added":false,"acquisition_retry_added":false,',
            1,
        )
    )
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit.audit(duplicate, check_live=False)


def test_mutated_history_artifact_fails_closed(monkeypatch, tmp_path: Path) -> None:
    history = copy.deepcopy(audit._check_history_evidence())
    history["runs"][0]["timezone"] = "Europe/London"
    history["canonical_sha256"] = evolution.canonical_sha256(history)
    path = tmp_path / "history.json"
    path.write_bytes(audit.canonical_json_bytes(history))
    monkeypatch.setattr(audit, "HISTORY_PATH", path)
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit._check_history_evidence()


def test_historical_before_fixture_is_exact_p4_4f_workflow_bytes() -> None:
    raw = Path(audit.FIXTURE_PATH).read_bytes()
    assert evolution.source_identity(raw) == audit.WORKFLOW_BEFORE


def test_workflow_contract_is_canonical_or_fail_closed_only() -> None:
    audit._check_workflow_contract()


def test_caller_inventory_has_no_legacy_workflow_live_reference() -> None:
    audit._check_caller_inventory()


def test_p4_4g_live_audit_passes_after_reviewed_commit() -> None:
    receipt = audit.audit()
    assert receipt["canonical_sha256"] == audit.expected_receipt()["canonical_sha256"]


def test_exact_historical_p44g_diff_matches_all_19_reviewed_paths() -> None:
    if not all(
        audit._commit_object_available(commit)
        for commit in (audit.BASE_MAIN, audit.P44G_REVIEWED_HEAD)
    ):
        pytest.skip("historical P4.4G base/reviewed-head objects are absent in this shallow checkout")
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = evolution.validate_current_state()
    paths = audit._historical_p44g_changed_paths(current_ledger, expected_ledger)
    assert paths == audit.EXPECTED_CHANGED_PATHS
    assert len(paths) == 19
    assert "tests/test_p4_4d_current_fotmob_ingest_compatibility.py" in paths


def test_historical_scope_fails_closed_if_p44d_test_path_is_omitted() -> None:
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError, match="historical changed-path set"):
        audit._assert_exact_historical_p44g_scope(
            audit.EXPECTED_CHANGED_PATHS
            - {"tests/test_p4_4d_current_fotmob_ingest_compatibility.py"}
        )


def test_historical_diff_is_pinned_to_p44g_reviewed_head_not_future_head(monkeypatch) -> None:
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = evolution.validate_current_state()
    diff_commands: list[list[str]] = []
    hypothetical_future_path = "artifacts/architecture/p4_4h_future_review.json"

    def tracking_run(args, capture_output=False):
        if args[:3] == ["git", "merge-base", "--is-ancestor"]:
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if args[:3] == ["git", "diff", "--name-only"]:
            diff_commands.append(args)
            assert args[3] == f"{audit.BASE_MAIN}...{audit.P44G_REVIEWED_HEAD}"
            assert "HEAD" not in args[3]
            return SimpleNamespace(
                returncode=0,
                stdout=("\n".join(sorted(audit.EXPECTED_CHANGED_PATHS)) + "\n").encode("utf-8"),
                stderr=b"",
            )
        raise AssertionError(args)

    original_git = audit._git

    def historical_git(*args):
        if args == ("show", "-s", "--format=%P", audit.P44G_MERGE_COMMIT):
            return f"{audit.BASE_MAIN} {audit.P44G_REVIEWED_HEAD}".encode("ascii")
        return original_git(*args)

    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: True)
    monkeypatch.setattr(audit.subprocess, "run", tracking_run)
    monkeypatch.setattr(audit, "_git", historical_git)
    paths = audit._historical_p44g_changed_paths(current_ledger, expected_ledger)
    assert paths == audit.EXPECTED_CHANGED_PATHS
    hypothetical_current_head_paths = set(paths) | {hypothetical_future_path}
    assert hypothetical_future_path in hypothetical_current_head_paths
    assert paths != hypothetical_current_head_paths
    assert len(diff_commands) == 1


def test_historical_scope_uses_available_base_and_reviewed_head_without_merge_object(
    monkeypatch,
) -> None:
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = evolution.validate_current_state()
    diff_commands: list[list[str]] = []

    def tracking_run(args, capture_output=False):
        if args[:3] == ["git", "diff", "--name-only"]:
            diff_commands.append(args)
            assert args[3] == f"{audit.BASE_MAIN}...{audit.P44G_REVIEWED_HEAD}"
            return SimpleNamespace(
                returncode=0,
                stdout=("\n".join(sorted(audit.EXPECTED_CHANGED_PATHS)) + "\n").encode("utf-8"),
                stderr=b"",
            )
        raise AssertionError(args)

    monkeypatch.setattr(
        audit,
        "_commit_object_available",
        lambda commit: commit != audit.P44G_MERGE_COMMIT,
    )
    monkeypatch.setattr(audit.subprocess, "run", tracking_run)
    for name in ("GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH", "GITHUB_SHA", "GITHUB_REF"):
        monkeypatch.delenv(name, raising=False)

    paths = audit._historical_p44g_changed_paths(current_ledger, expected_ledger)
    assert paths == audit.EXPECTED_CHANGED_PATHS
    assert len(diff_commands) == 1


def test_synthetic_reviewed_cumulative_extension_preserves_p44g_prefix_and_snapshot(
    monkeypatch,
) -> None:
    expected_ledger, expected_snapshot, _ = audit.build_evidence()
    extended = copy.deepcopy(expected_ledger)
    extended["transitions"].append(
        {
            "transition_id": "SYNTHETIC_REVIEWED_FUTURE_TRANSITION",
            "phase_id": "P4.4I",
            "operation": "MAINTENANCE_REVISE",
            "workflow_path": audit.WORKFLOW_PATH,
            "after": {"git_blob_sha1": "e" * 40, "source_sha256": "f" * 64},
        }
    )
    future_tree = "a" * 40
    extended["current_workflow_tree_sha1"] = future_tree
    extended["canonical_sha256"] = evolution.canonical_sha256(extended)
    audit._validate_p44g_evolution_prefix(extended, expected_ledger)
    assert extended["transitions"][:6] == expected_ledger["transitions"]
    assert audit._load_json(audit.SNAPSHOT_PATH) == expected_snapshot

    monkeypatch.setattr(evolution, "validate_current_state", lambda: extended)
    original_git = audit._git
    current_workflow_paths = original_git(
        "ls-tree", "-r", "--name-only", "HEAD", ".github/workflows"
    )

    def synthetic_current_git(*args):
        if args == ("rev-parse", "HEAD:.github/workflows"):
            return future_tree.encode("ascii")
        if args == ("ls-tree", "-r", "--name-only", "HEAD", ".github/workflows"):
            return current_workflow_paths
        return original_git(*args)

    monkeypatch.setattr(audit, "_git", synthetic_current_git)
    receipt = audit.audit(check_live=True)
    assert receipt["canonical_sha256"] == "af0e87fc9fc925d1c30f5f2adee699be0724fa1b68842963f25c5a1f56fe12af"


def test_mutated_p44g_transition_prefix_fails_closed() -> None:
    expected_ledger, _, _ = audit.build_evidence()
    mutated = copy.deepcopy(expected_ledger)
    mutated["transitions"][5]["transition_id"] = "MUTATED_P44G_TRANSITION"
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError, match="transition prefix"):
        audit._validate_p44g_evolution_prefix(mutated, expected_ledger)


def test_shallow_pr_historical_scope_requires_current_main_event_and_prefix(
    monkeypatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    synthetic_merge_sha = "b" * 40
    event = {
        "pull_request": {
            "base": {"ref": "main", "sha": audit.P44G_MERGE_COMMIT},
            "head": {"sha": "a" * 40},
        }
    }
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", synthetic_merge_sha)
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = copy.deepcopy(expected_ledger)
    current_ledger["transitions"].append({"transition_id": "FUTURE"})
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: False)

    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return synthetic_merge_sha.encode("ascii")
        raise AssertionError(args)

    monkeypatch.setattr(audit, "_git", fake_git)
    assert audit._historical_p44g_changed_paths(current_ledger, expected_ledger) is None

    event["pull_request"]["base"]["ref"] = "release"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    with pytest.raises(
        audit.P44GCanonicalOnlyWorkflowAuditError,
        match="trusted current main pull_request binding",
    ):
        audit._historical_p44g_changed_paths(current_ledger, expected_ledger)


def _configure_trusted_shallow_push(
    monkeypatch,
    tmp_path: Path,
    *,
    github_ref: str = "refs/heads/main",
    github_sha: str = "a" * 40,
    event_ref: str = "refs/heads/main",
    event_after: str | None = None,
    deleted: bool = False,
    repository_name: str = "Thabearr/ATHENA",
    default_branch: str = "main",
    repository_env: str | None = "Thabearr/ATHENA",
    checkout_sha: str | None = None,
) -> tuple[dict, Path]:
    event_path = tmp_path / "push-event.json"
    event = {
        "ref": event_ref,
        "after": event_after if event_after is not None else github_sha,
        "deleted": deleted,
        "repository": {
            "full_name": repository_name,
            "default_branch": default_branch,
        },
    }
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", github_ref)
    monkeypatch.setenv("GITHUB_SHA", github_sha)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    if repository_env is None:
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    else:
        monkeypatch.setenv("GITHUB_REPOSITORY", repository_env)
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: False)

    actual_checkout_sha = checkout_sha if checkout_sha is not None else github_sha

    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return actual_checkout_sha.encode("ascii")
        raise AssertionError(args)

    monkeypatch.setattr(audit, "_git", fake_git)
    return event, event_path


def test_shallow_main_push_is_trusted_only_for_exact_checked_out_main(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_trusted_shallow_push(monkeypatch, tmp_path)
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = copy.deepcopy(expected_ledger)
    current_ledger["transitions"].append({"transition_id": "LATER_REVIEWED_PREFIX"})

    assert audit._historical_p44g_changed_paths(current_ledger, expected_ledger) is None


def test_live_audit_passes_with_trusted_shallow_main_push_context(
    monkeypatch, tmp_path: Path
) -> None:
    exact_main = audit._git("rev-parse", "HEAD").decode("ascii").strip()
    event_path = tmp_path / "main-push-event.json"
    event_path.write_text(
        json.dumps(
            {
                "ref": "refs/heads/main",
                "after": exact_main,
                "deleted": False,
                "repository": {
                    "full_name": "Thabearr/ATHENA",
                    "default_branch": "main",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_SHA", exact_main)
    monkeypatch.setenv("GITHUB_REPOSITORY", "Thabearr/ATHENA")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: False)

    receipt = audit.audit(check_live=True)
    assert receipt["canonical_sha256"] == audit.expected_receipt()["canonical_sha256"]


@pytest.mark.parametrize(
    "override",
    [
        {"github_ref": "refs/heads/release"},
        {"event_ref": "refs/heads/release"},
        {"github_ref": "refs/tags/v1.0.0", "event_ref": "refs/tags/v1.0.0"},
        {"event_after": "b" * 40},
        {"checkout_sha": "c" * 40},
        {"repository_name": "attacker/ATHENA"},
        {"repository_env": "attacker/ATHENA"},
        {"default_branch": "release"},
        {"deleted": True},
        {"github_sha": "A" * 40},
        {"github_sha": "not-a-canonical-sha"},
    ],
)
def test_shallow_main_push_rejects_mismatched_event_bindings(
    monkeypatch, tmp_path: Path, override: dict
) -> None:
    _configure_trusted_shallow_push(monkeypatch, tmp_path, **override)
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = evolution.validate_current_state()

    with pytest.raises(
        audit.P44GCanonicalOnlyWorkflowAuditError,
        match="trusted current main push binding",
    ):
        audit._historical_p44g_changed_paths(current_ledger, expected_ledger)


@pytest.mark.parametrize("event_state", ["missing", "malformed"])
def test_shallow_push_rejects_missing_or_malformed_event(
    monkeypatch, tmp_path: Path, event_state: str
) -> None:
    _, event_path = _configure_trusted_shallow_push(monkeypatch, tmp_path)
    if event_state == "missing":
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "absent-event.json"))
    else:
        event_path.write_text("{not-json", encoding="utf-8")
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = evolution.validate_current_state()

    with pytest.raises(
        audit.P44GCanonicalOnlyWorkflowAuditError,
        match="trusted current main push",
    ):
        audit._historical_p44g_changed_paths(current_ledger, expected_ledger)


def test_shallow_push_rejects_local_unknown_event_without_historical_objects(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_trusted_shallow_push(monkeypatch, tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = evolution.validate_current_state()

    with pytest.raises(
        audit.P44GCanonicalOnlyWorkflowAuditError,
        match="trusted current main pull_request or push binding",
    ):
        audit._historical_p44g_changed_paths(current_ledger, expected_ledger)


def test_trusted_push_cannot_bypass_mutated_p44g_evolution_prefix(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_trusted_shallow_push(monkeypatch, tmp_path)
    expected_ledger, _, _ = audit.build_evidence()
    mutated_current = copy.deepcopy(expected_ledger)
    mutated_current["transitions"][5]["transition_id"] = "MUTATED_P44G_PREFIX"

    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError, match="transition prefix"):
        audit._historical_p44g_changed_paths(mutated_current, expected_ledger)


def test_shallow_main_push_allows_absent_repository_env_when_event_binds_repo(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_trusted_shallow_push(monkeypatch, tmp_path, repository_env=None)
    expected_ledger, _, _ = audit.build_evidence()
    current_ledger = evolution.validate_current_state()

    assert audit._historical_p44g_changed_paths(current_ledger, expected_ledger) is None
