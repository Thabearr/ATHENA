from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import socket
import urllib.request

import pytest

from scripts import audit_auth_01b_workflow_evolution as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_auth_01b_workflow_transition_is_exact_and_historical_prefix_is_immutable() -> None:
    result = audit.audit()
    assert result["status"] == "PASS"
    assert result["transition_id"] == "AUTH01B_ATHENA_RUN_EXPLICIT_DELIVERY_INTENT_V1"
    assert result["workflow_before_identity"] == audit.EXPECTED_BEFORE
    assert result["environment_handoff_count"] == 1
    assert result["network_provider_side_effects"] == 0
    assert len(result["checkpoint_sha256"]) == 64
    assert len(result["receipt_sha256"]) == 64
    assert result["p44m_receipt_blob_unchanged"] == audit.P44M_RECEIPT_BASE_BLOB_SHA1
    assert result["p44m_snapshot_blob_unchanged"] == audit.P44M_SNAPSHOT_BASE_BLOB_SHA1


def test_historical_p44m_base_blob_is_verified_with_full_history(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = audit.P44M_RECEIPT_BASE_BLOB_SHA1
    blobs = {
        ("HEAD", audit.P44M_RECEIPT_PATH.as_posix()): expected,
        (audit.BASE_MAIN_SHA, audit.P44M_RECEIPT_PATH.as_posix()): expected,
    }
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: True)
    monkeypatch.setattr(audit, "_git_blob_sha", lambda revision, path: blobs[(revision, path.as_posix())])
    assert audit._verify_historical_file_unchanged(audit.P44M_RECEIPT_PATH) == expected


def test_historical_p44m_base_blob_is_verified_in_trusted_shallow_pr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected = audit.P44M_SNAPSHOT_BASE_BLOB_SHA1
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: False)
    _set_pr_context(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audit,
        "_git_blob_sha",
        lambda revision, _path: expected if revision == "HEAD" else pytest.fail("base lookup in shallow checkout"),
    )
    assert audit._verify_historical_file_unchanged(audit.P44M_SNAPSHOT_PATH) == expected


def test_historical_p44m_shallow_blob_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: False)
    _set_pr_context(monkeypatch, tmp_path)
    monkeypatch.setattr(audit, "_git_blob_sha", lambda _revision, _path: "0" * 40)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="historical P4.4 file changed"):
        audit._verify_historical_file_unchanged(audit.P44M_RECEIPT_PATH)


def test_historical_p44m_unknown_path_fails_closed() -> None:
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="unrecognized immutable historical file"):
        audit._verify_historical_file_unchanged(Path("artifacts/unknown.json"))


def test_historical_p44m_wrong_base_blob_constant_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: True)
    monkeypatch.setattr(audit, "_git_blob_sha", lambda revision, _path: "0" * 40 if revision == audit.BASE_MAIN_SHA else audit.P44M_RECEIPT_BASE_BLOB_SHA1)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="historical base blob identity differs"):
        audit._verify_historical_file_unchanged(audit.P44M_RECEIPT_PATH)


def _set_current_head(monkeypatch: pytest.MonkeyPatch, head_sha: str) -> None:
    monkeypatch.setattr(
        audit.subprocess,
        "check_output",
        lambda args, **_kwargs: head_sha + "\n"
        if args == ["git", "rev-parse", "HEAD"]
        else pytest.fail(f"unexpected subprocess {args}"),
    )


def _write_github_event(tmp_path: Path, event: dict) -> Path:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    return event_path


def _set_pr_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    head_sha: str = "c" * 40,
    base_ref: str = "main",
    base_sha: str = "a" * 40,
    pr_head_sha: str = "b" * 40,
    repository_name: str = "Thabearr/ATHENA",
    repository_env: str = "Thabearr/ATHENA",
) -> None:
    event_path = _write_github_event(
        tmp_path,
        {
            "repository": {"full_name": repository_name},
            "pull_request": {
                "base": {"ref": base_ref, "sha": base_sha},
                "head": {"sha": pr_head_sha},
            },
        },
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", repository_env)
    monkeypatch.setenv("GITHUB_SHA", head_sha)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    _set_current_head(monkeypatch, head_sha)


def _set_main_push_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    head_sha: str = "c" * 40,
    event_ref: str = "refs/heads/main",
    github_ref: str = "refs/heads/main",
    after: str | None = None,
    deleted: object = False,
    repository_name: str = "Thabearr/ATHENA",
    repository_env: str = "Thabearr/ATHENA",
    default_branch: str | None = "main",
) -> None:
    repository = {"full_name": repository_name}
    if default_branch is not None:
        repository["default_branch"] = default_branch
    payload = {
        "repository": repository,
        "ref": event_ref,
        "after": head_sha if after is None else after,
        "deleted": deleted,
    }
    event_path = _write_github_event(tmp_path, payload)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", repository_env)
    monkeypatch.setenv("GITHUB_SHA", head_sha)
    monkeypatch.setenv("GITHUB_REF", github_ref)
    _set_current_head(monkeypatch, head_sha)


def _set_shallow_blob(
    monkeypatch: pytest.MonkeyPatch,
    *,
    expected_head_blob: str,
) -> None:
    monkeypatch.setattr(audit, "_commit_object_available", lambda _commit: False)
    monkeypatch.setattr(
        audit,
        "_git_blob_sha",
        lambda revision, _path: expected_head_blob
        if revision == "HEAD"
        else pytest.fail("base lookup in shallow checkout"),
    )


def test_trusted_shallow_pr_binding_accepts_synthetic_merge_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_pr_context(monkeypatch, tmp_path)
    audit._require_trusted_current_github_context()


def test_trusted_shallow_main_push_verifies_exact_pinned_blob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected = audit.P44M_RECEIPT_BASE_BLOB_SHA1
    _set_main_push_context(monkeypatch, tmp_path)
    _set_shallow_blob(monkeypatch, expected_head_blob=expected)
    assert audit._verify_historical_file_unchanged(audit.P44M_RECEIPT_PATH) == expected


@pytest.mark.parametrize(
    "event_ref,github_ref,deleted,after,default_branch",
    [
        ("refs/heads/feature/x", "refs/heads/feature/x", False, None, "main"),
        ("refs/tags/v1", "refs/tags/v1", False, None, "main"),
        ("refs/heads/main", "refs/heads/main", True, None, "main"),
        ("refs/heads/main", "refs/heads/main", False, "d" * 40, "main"),
        ("refs/heads/main", "refs/heads/main", False, None, "develop"),
    ],
)
def test_untrusted_push_shapes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    event_ref: str,
    github_ref: str,
    deleted: object,
    after: str | None,
    default_branch: str,
) -> None:
    _set_main_push_context(
        monkeypatch,
        tmp_path,
        event_ref=event_ref,
        github_ref=github_ref,
        deleted=deleted,
        after=after,
        default_branch=default_branch,
    )
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


def test_push_with_github_sha_different_from_head_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_main_push_context(monkeypatch, tmp_path, head_sha="c" * 40, after="c" * 40)
    _set_current_head(monkeypatch, "d" * 40)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


@pytest.mark.parametrize("event_name", ["workflow_dispatch", "schedule", "issue_comment", "repository_dispatch"])
def test_unrecognized_github_event_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, event_name: str
) -> None:
    event_path = _write_github_event(
        tmp_path, {"repository": {"full_name": "Thabearr/ATHENA"}}
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "Thabearr/ATHENA")
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    _set_current_head(monkeypatch, "c" * 40)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


def test_missing_event_file_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Thabearr/ATHENA")
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    _set_current_head(monkeypatch, "c" * 40)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


def test_repository_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_main_push_context(monkeypatch, tmp_path, repository_name="someone/else")
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


def test_malformed_push_sha_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_main_push_context(monkeypatch, tmp_path, after="C" * 40)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


@pytest.mark.parametrize("sha", ["A" * 40, "f" * 39, "g" * 40])
def test_malformed_github_sha_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sha: str
) -> None:
    _set_main_push_context(monkeypatch, tmp_path, head_sha=sha, after=sha)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


def test_missing_repository_environment_binding_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_main_push_context(monkeypatch, tmp_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="trusted current GitHub"):
        audit._require_trusted_current_github_context()


@pytest.mark.parametrize("event_name", ["pull_request", "push"])
def test_historical_head_blob_mismatch_fails_closed_in_trusted_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    event_name: str,
) -> None:
    if event_name == "pull_request":
        _set_pr_context(monkeypatch, tmp_path)
    else:
        _set_main_push_context(monkeypatch, tmp_path)
    _set_shallow_blob(monkeypatch, expected_head_blob="0" * 40)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="historical P4.4 file changed"):
        audit._verify_historical_file_unchanged(audit.P44M_RECEIPT_PATH)


def test_auth_01b_receipt_is_offline_safe_under_network_sentinels(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def denied(*_args, **_kwargs):
        calls.append("network")
        raise AssertionError("AUTH-01B audit attempted network access")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    assert audit.audit()["status"] == "PASS"
    assert calls == []


def test_auth_01b_receipt_and_before_fixture_have_expected_exact_identities() -> None:
    fixture = audit.BEFORE_FIXTURE_PATH.read_bytes().replace(b"\r\n", b"\n")
    assert evolution.source_identity(fixture) == audit.EXPECTED_BEFORE
    receipt = json.loads(audit.RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["repository"] == "Thabearr/ATHENA"
    assert receipt["base_main_sha"] == audit.BASE_MAIN_SHA
    assert receipt["workflow_before_identity"] == audit.EXPECTED_BEFORE
    assert receipt["canonical_sha256"] == evolution.canonical_sha256(receipt)
    assert receipt["implementation_side_effects"]["share_code_action"] == 0
    forbidden_fields = {
        "raw_share_code",
        "share_code",
        "share_url",
        "share_code_url",
        "token",
        "cookie_value",
        "credential",
        "secret",
    }

    def keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)

    assert not forbidden_fields.intersection(keys(receipt))


def test_v2_input_surface_contract_does_not_claim_trigger_or_authority_changes() -> None:
    contract = evolution.AUTHORITY_SURFACE_MAINTENANCE_CONTRACT_V2
    assert contract["policy_id"] == "ATHENA_P4_BASELINE_WORKFLOW_MAINTENANCE_REVISE_V2"
    assert contract["event_trigger_kinds_changed"] is False
    assert contract["workflow_dispatch_input_surface_changed"] is True
    assert contract["schedule_surface_changed"] is False
    assert contract["permissions_changed"] is False
    assert contract["concurrency_changed"] is False
    assert contract["provider_step_added"] is False
    assert contract["delivery_step_added"] is False
    assert contract["betting_authority_changed"] is False


def _reviewed_workflows() -> tuple[dict, dict]:
    before = evolution.resolve_reviewed_transition_after_source(
        audit.WORKFLOW_PATH,
        "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1",
    )
    after = Path(audit.WORKFLOW_PATH).read_bytes().replace(b"\r\n", b"\n")
    return audit._yaml(before, "P4.4M"), audit._yaml(after, "AUTH-01B")


@pytest.mark.parametrize("mutation", ["schedule", "permissions", "concurrency", "event", "provider_step", "delivery_step"])
def test_workflow_delta_rejects_any_non_input_or_handoff_change(mutation: str) -> None:
    before, after = _reviewed_workflows()
    changed = copy.deepcopy(after)
    if mutation == "schedule":
        changed["on"]["schedule"][0]["cron"] = "1 1 * * *"
    elif mutation == "permissions":
        changed["permissions"]["contents"] = "write"
    elif mutation == "concurrency":
        changed["concurrency"]["group"] = "unreviewed-group"
    elif mutation == "event":
        changed["on"]["workflow_call"] = {}
    else:
        step = {"name": "unreviewed execution", "run": "echo unexpected"}
        job = next(iter(changed["jobs"].values()))
        job["steps"].append(step)
    with pytest.raises(audit.Auth01BWorkflowEvolutionError):
        audit.verify_workflow_revision(before, changed)


def test_workflow_delta_rejects_wrong_delivery_choice_shape() -> None:
    before, after = _reviewed_workflows()
    changed = copy.deepcopy(after)
    changed["on"]["workflow_dispatch"]["inputs"]["create_share_code"]["options"] = ["true"]
    with pytest.raises(audit.Auth01BWorkflowEvolutionError, match="input contract"):
        audit.verify_workflow_revision(before, changed)


def test_auth_01b_audit_has_no_provider_or_transport_imports() -> None:
    tree = ast.parse(Path("scripts/audit_auth_01b_workflow_evolution.py").read_text(encoding="utf-8"))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    forbidden = ("provider", "sportybet", "fotmob", "requests", "httpx", "urllib", "socket")
    assert not any(token in module.lower() for module in imported for token in forbidden)
