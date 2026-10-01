"""Offline role restore/parity/tamper gates; synthetic history is explicitly labelled."""
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import smtplib
import socket
import subprocess
import urllib.request
import zipfile

import pytest

from services import athena_artifact_role_resolver as roles
from scripts import audit_core_01b_canonical_artifact_ancestry as audit
from scripts.build_athena_artifact_role_manifest import build_manifest, publish
from scripts.restore_athena_artifact_roles import extract_verified_paths, GitHubTransport, legacy_role


@pytest.fixture(autouse=True)
def deny_live(monkeypatch):
    calls = []

    def deny(*args, **kwargs):
        calls.append(True)
        raise AssertionError("CORE-01B live operation forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    monkeypatch.setattr(smtplib, "SMTP_SSL", deny)
    original = subprocess.Popen

    def git_only(args, *positional, **kwargs):
        if not isinstance(args, (list, tuple)) or args[0] != "git" or kwargs.get("shell"):
            return deny()
        return original(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", git_only)
    from services import athena_run_service
    from domain import sportybet_share_code
    from scripts import send_current_shadow_email
    monkeypatch.setattr(athena_run_service, "_run_reviewed_shadow_worker", deny)
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code", deny)
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code_as_of", deny)
    monkeypatch.setattr(send_current_shadow_email, "send_receipt_email", deny)
    yield
    assert not calls


@pytest.fixture
def identity_manifest(tmp_path):
    history, state = audit.synthetic_inputs(tmp_path)
    candidate = roles.Candidate(100, "b" * 40, roles.CANONICAL_WORKFLOW, 200, "athena-run-100")
    root = tmp_path / "canonical"
    role_id = "PERSISTENT_FIXTURE_IDENTITY_STATE"
    target = root / roles.ROLE_ROOTS[role_id]
    shutil.copytree(state, target)
    origin = {"source_kind": "LEGACY_ACTIONS", "repository": roles.REPOSITORY,
              **roles.LEGACY_PRODUCERS[role_id], "run_id": 12, "head_sha": "a" * 40,
              "inventory_sha256": roles.sha(roles.canonical(roles.inventory(target)))}
    producer = {"workflow_family": "ATHENA_RUN", "workflow_path": roles.CANONICAL_WORKFLOW,
                "run_id": 100, "head_sha": "b" * 40, "head_branch": "main",
                "event_name": "workflow_dispatch", "request_sha256": "c" * 64}
    manifest = build_manifest(root, producer=producer, origins={role_id: origin}, restore_eligible=True)
    return root, candidate, manifest


def resign(value):
    value["canonical_sha256"] = roles.self_sha(value)
    return roles.canonical(value)


def verify(root, candidate, manifest):
    return roles.validate_manifest(resign(manifest), root, candidate, current_run_id=101,
                                    role_id="PERSISTENT_FIXTURE_IDENTITY_STATE")


def test_exact_four_roles_and_policies():
    assert roles.POLICY_ID == "ATHENA_CANONICAL_ARTIFACT_ROLES_V1"
    assert roles.MANIFEST_POLICY_ID == "ATHENA_CANONICAL_RUN_ARTIFACT_ROLE_MANIFEST_V1"
    assert roles.ROLE_IDS == ("DURABLE_HISTORY_PRIME", "PERSISTENT_FIXTURE_IDENTITY_STATE",
                              "PR119_BOOTSTRAP", "RETAINED_SOURCE_EVIDENCE")
    with pytest.raises(roles.ArtifactRoleError):
        roles.select_canonical("UNKNOWN", [], lambda item: None, current_run_id=1)
    with pytest.raises(roles.ArtifactRoleError):
        roles.select_canonical("RETAINED_SOURCE_EVIDENCE", [], lambda item: None, current_run_id=1)


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("schema_version", True),
    ("policy_id", "BAD"), ("repository", "Other/Repo"), ("restore_eligible", False), ("restore_eligible", 1)])
def test_manifest_identity_eligibility_rejection(identity_manifest, field, value):
    root, candidate, manifest = identity_manifest
    manifest[field] = value
    with pytest.raises(roles.ArtifactRoleError):
        verify(root, candidate, manifest)


@pytest.mark.parametrize("field,value", [("run_id", 99), ("head_sha", "d" * 40),
    ("head_branch", "feature"), ("workflow_path", ".github/workflows/other.yml"),
    ("workflow_family", "CURRENT_SHADOW"), ("request_sha256", None), ("event_name", "push")])
def test_manifest_producer_binding_rejection(identity_manifest, field, value):
    root, candidate, manifest = identity_manifest
    manifest["producer"][field] = value
    with pytest.raises(roles.ArtifactRoleError):
        verify(root, candidate, manifest)


@pytest.mark.parametrize("field,value", [("repository", "Other/Repo"), ("head_branch", "feature"),
    ("status", "in_progress"), ("conclusion", "failure"), ("run_id", 101),
    ("head_sha", "bad"), ("workflow_path", ".github/workflows/other.yml"),
    ("artifact_name", "athena-run-999"), ("artifact_id", 0)])
def test_candidate_nonmain_self_unsuccessful_mismatch_rejection(identity_manifest, field, value):
    root, candidate, manifest = identity_manifest
    with pytest.raises(roles.ArtifactRoleError):
        verify(root, replace(candidate, **{field: value}), manifest)


@pytest.mark.parametrize("change", ["unknown", "duplicate", "path", "traversal", "absolute", "backslash",
    "file_count", "byte_count", "file_hash", "aggregate_hash", "authority", "extra_member"])
def test_role_closed_world_path_inventory_tamper_rejection(identity_manifest, change):
    root, candidate, manifest = identity_manifest
    row = manifest["roles"][0]
    if change == "unknown":
        row["role_id"] = "UNKNOWN"
    elif change == "duplicate":
        manifest["roles"].append(row.copy())
    elif change in {"path", "traversal", "absolute", "backslash"}:
        row["relative_root"] = {"path": "other", "traversal": "../outside", "absolute": "/outside",
                                 "backslash": "artifact-roles\\identity"}[change]
    elif change == "file_count":
        row["file_count"] = 2
    elif change == "byte_count":
        row["byte_count"] += 1
    elif change == "file_hash":
        row["inventory"][0]["sha256"] = "f" * 64
    elif change == "aggregate_hash":
        row["inventory_sha256"] = "f" * 64
    elif change == "authority":
        row["authority_classification"] = "EVIDENCE_AUTHORITY"
    else:
        row["inventory"].append(row["inventory"][0].copy())
    with pytest.raises(roles.ArtifactRoleError):
        verify(root, candidate, manifest)


@pytest.mark.parametrize("change", ["mutation", "missing", "extra", "symlink"])
def test_payload_mutation_missing_extra_symlink_rejection(identity_manifest, change, monkeypatch):
    root, candidate, manifest = identity_manifest
    path = root / roles.ROLE_ROOTS["PERSISTENT_FIXTURE_IDENTITY_STATE"] / roles.STATE_FILENAME
    if change == "mutation":
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "missing":
        path.unlink()
    elif change == "extra":
        path.with_name("extra.json").write_bytes(b"{}")
    else:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda item: item == path or original(item))
    with pytest.raises((roles.ArtifactRoleError, OSError)):
        verify(root, candidate, manifest)


def test_duplicate_json_key_and_noncanonical_bytes_rejected(identity_manifest):
    root, candidate, manifest = identity_manifest
    raw = resign(manifest)
    for changed in (raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
                    raw.replace(b'"schema_version":1', b'"schema_version":2'), raw.replace(b"\n", b"\r\n")):
        with pytest.raises(roles.ArtifactRoleError):
            roles.validate_manifest(changed, root, candidate, current_run_id=101,
                                    role_id="PERSISTENT_FIXTURE_IDENTITY_STATE")


def test_newest_valid_and_rejected_newest_older_fallback(identity_manifest):
    root, candidate, manifest = identity_manifest
    newest = replace(candidate, run_id=102, artifact_name="athena-run-102", artifact_id=202)
    newest_manifest = json.loads(resign(manifest))
    newest_manifest["producer"]["run_id"] = 102
    role_id = "PERSISTENT_FIXTURE_IDENTITY_STATE"
    result = roles.select_canonical(role_id, [candidate, newest], lambda item:
                                    (root, resign(newest_manifest if item == newest else manifest)), current_run_id=103)
    assert result[0] == newest
    result = roles.select_canonical(role_id, [candidate, newest], lambda item:
                                    (root, b"BAD" if item == newest else resign(manifest)), current_run_id=103)
    assert result[0] == candidate


def test_legacy_identity_history_and_real_pr119_canonical_restore_parity():
    parity = audit.offline_parity()
    assert set(parity) == set(roles.ROLE_IDS[:3])
    assert all(row["result"] == "PASS_EXACT_BYTES_AND_INVENTORY" for row in parity.values())
    assert parity["PR119_BOOTSTRAP"]["byte_count"] == 10545099
    assert parity["PR119_BOOTSTRAP"]["fixture_classification"] == "RETAINED_FIXED_RELEASE"
    assert parity["DURABLE_HISTORY_PRIME"]["fixture_classification"] == "SYNTHETIC_NO_LIVE_HISTORY_CLAIM"


def test_prime_legacy_commit_mismatch_and_malformed_identity(tmp_path):
    history, state = audit.synthetic_inputs(tmp_path)
    role_id = "DURABLE_HISTORY_PRIME"
    candidate = roles.Candidate(11, "d" * 40, roles.LEGACY_PRODUCERS[role_id]["workflow_path"],
                                111, roles.LEGACY_PRODUCERS[role_id]["artifact_name"])
    with pytest.raises(ValueError):
        legacy_role(role_id, candidate, history)
    (state / roles.STATE_FILENAME).write_bytes(b"{}")
    role_id = "PERSISTENT_FIXTURE_IDENTITY_STATE"
    candidate = replace(candidate, workflow_path=roles.LEGACY_PRODUCERS[role_id]["workflow_path"],
                        artifact_name=roles.LEGACY_PRODUCERS[role_id]["artifact_name"])
    with pytest.raises(ValueError):
        legacy_role(role_id, candidate, state)


def test_wrong_pr119_sha_and_no_fake_prime_role(tmp_path):
    root = tmp_path / "bootstrap"
    root.mkdir()
    (root / roles.BOOTSTRAP_FILENAME).write_bytes(b"SYNTHETIC_INVALID_BOOTSTRAP")
    origin = {"source_kind": "FIXED_RELEASE", "repository": roles.REPOSITORY,
              **roles.LEGACY_PRODUCERS["PR119_BOOTSTRAP"], "payload_sha256": roles.BOOTSTRAP_SHA256}
    with pytest.raises(roles.ArtifactRoleError):
        roles.validate_payload("PR119_BOOTSTRAP", root, origin)
    producer = {"workflow_family": "ATHENA_RUN", "workflow_path": roles.CANONICAL_WORKFLOW,
                "run_id": 100, "head_sha": "b" * 40, "head_branch": "main",
                "event_name": "workflow_dispatch", "request_sha256": "c" * 64}
    value = build_manifest(tmp_path, producer=producer, origins={}, restore_eligible=False)
    assert value["roles"] == [] and value["restore_eligible"] is False


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/absolute", "folder\\file", "folder/../file", "./file"])
def test_zip_path_escape_rejection(tmp_path, name):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, b"untrusted")
    raw = stream.getvalue()
    if "\\" in name:
        # ZipInfo's writer normalizes Windows separators; inject original ZIP
        # member bytes to exercise the untrusted reader, not writer convenience.
        raw = raw.replace(name.replace("\\", "/").encode(), name.encode())
    with pytest.raises(ValueError):
        extract_verified_paths(raw, tmp_path)


def test_zip_duplicate_and_symlink_rejection(tmp_path):
    for symlink in (False, True):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            if symlink:
                item = zipfile.ZipInfo("link")
                item.external_attr = 0o120777 << 16
                archive.writestr(item, b"outside")
            else:
                archive.writestr("duplicate", b"first")
                archive.writestr("duplicate", b"second")
        with pytest.raises(ValueError):
            extract_verified_paths(stream.getvalue(), tmp_path / str(symlink))


def test_publication_without_verified_receipt_is_diagnostic_not_restore_source(tmp_path):
    value = publish(tmp_path, run_id=100, head_sha="b" * 40, head_branch="main",
                    event_name="workflow_dispatch", execution_exit_code="0", preservation_result="success")
    assert value["restore_eligible"] is False and value["roles"] == []


@pytest.mark.parametrize("exit_code,preserved,branch,eligible", [
    ("0", "success", "main", True), ("1", "success", "main", False),
    ("0", "failure", "main", False), ("0", "success", "feature", False),
])
def test_verified_publication_eligibility_and_source_evidence_only(tmp_path, exit_code, preserved, branch, eligible):
    from domain.run_contracts import canonical_json_bytes
    from services.athena_run_request_parser import parse_explicit_request
    from services.athena_run_service import AthenaRunService, ExecutorResult
    now = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
    request = parse_explicit_request(days="today", target_legs=20, profile="shadow",
                                      create_share_code=False, now=now)
    engine = AthenaRunService(_test_executor_overrides={
        ("SHADOW", "research_shadow", "sportybet"): lambda *args, **kwargs:
        ExecutorResult(status="SYNTHETIC_OFFLINE_NO_BET", evidence={"synthetic": True})},
        _commit_sha_provider=lambda: "b" * 40, _clock=lambda: now)
    engine.run(request, output_root=tmp_path / "artifacts/athena-runs")
    root = tmp_path / "artifacts/athena-run-workflow"
    root.mkdir()
    (root / "resolved-run-request.json").write_bytes(canonical_json_bytes(request))
    source = root / "source-evidence"
    source.mkdir()
    (source / "SYNTHETIC.txt").write_bytes(b"synthetic retained source example; no provider acquisition")
    value = publish(tmp_path, run_id=100, head_sha="b" * 40, head_branch=branch,
                    event_name="workflow_dispatch", execution_exit_code=exit_code, preservation_result=preserved)
    assert value["restore_eligible"] is eligible
    assert [row["role_id"] for row in value["roles"]] == ["RETAINED_SOURCE_EVIDENCE"]
    assert "DURABLE_HISTORY_PRIME" not in [row["role_id"] for row in value["roles"]]


@pytest.mark.parametrize("change", ["wrong_run", "wrong_head", "nonmain", "expired", "wrong_repository", "wrong_workflow"])
def test_transport_metadata_binds_artifact_to_exact_trusted_main_run(change):
    workflow = roles.CANONICAL_WORKFLOW
    run = {"id": 100, "path": workflow, "repository": {"full_name": roles.REPOSITORY},
           "head_repository": {"full_name": roles.REPOSITORY}, "head_branch": "main",
           "status": "completed", "conclusion": "success", "head_sha": "b" * 40,
           "event": "workflow_dispatch"}
    artifact = {"id": 200, "name": "athena-run-100", "expired": False,
                "workflow_run": {"id": 100, "head_sha": "b" * 40, "head_branch": "main"}}
    class FixtureMetadata(GitHubTransport):
        def pages(self, endpoint, field):
            return [run] if field == "workflow_runs" else [artifact]
    transport = FixtureMetadata()
    assert len(transport.candidates(workflow, canonical_producer=True)) == 1
    if change == "wrong_run":
        artifact["workflow_run"]["id"] = 99
    elif change == "wrong_head":
        artifact["workflow_run"]["head_sha"] = "d" * 40
    elif change == "nonmain":
        run["head_branch"] = "feature"
    elif change == "expired":
        artifact["expired"] = True
    elif change == "wrong_repository":
        run["head_repository"]["full_name"] = "Other/Repo"
    else:
        run["path"] = ".github/workflows/other.yml"
    assert transport.candidates(workflow, canonical_producer=True) == []


def test_workflow_authority_and_exact_before_fixture():
    before = audit.tracked(audit.BEFORE_FIXTURE)[0]
    after = audit.tracked(roles.CANONICAL_WORKFLOW)[0]
    assert audit.evolution.source_identity(before) == audit.BEFORE_IDENTITY
    audit.verify_workflow_authority(before, after)
    changed = after.replace(b'cron: "0 9 * * *"', b'cron: "0 10 * * *"')
    with pytest.raises(roles.ArtifactRoleError):
        audit.verify_workflow_authority(before, changed)


def test_tenth_transition_and_immutable_ninth_checkpoint():
    predecessor = roles.strict_json(audit.tracked(audit.PREDECESSOR_PATH)[0])
    ledger = audit.evolution.validate_current_state()
    assert len(predecessor["transitions"]) == 9
    assert predecessor["transitions"][8]["transition_id"] == "PORT02C_NATIVE_RUNTIME_SLICE_ADD_V1"
    assert len(ledger["transitions"]) == 10 and ledger["transitions"][:9] == predecessor["transitions"]
    assert ledger["transitions"][9]["transition_id"] == audit.TRANSITION_ID
    assert ledger["current_live_workflow_count"] == 39 and ledger["current_p4_3_retired_workflow_count"] == 3
    snapshot = roles.strict_json(audit.tracked(audit.SNAPSHOT_PATH)[0])
    receipt = roles.strict_json(audit.tracked(audit.RECEIPT_PATH)[0])
    assert snapshot == ledger and receipt["workflow_evolution_ledger_sha256"] == snapshot["canonical_sha256"]
    transition = predecessor["transitions"][8]
    old_receipt = roles.strict_json(audit.tracked(transition["evidence_receipt_path"])[0])
    assert old_receipt["workflow_evolution_ledger_sha256"] == audit.PREDECESSOR_SHA


@pytest.mark.parametrize("change", ["delete", "reorder", "modify", "insert_before", "replace"])
def test_ninth_transition_rewrite_or_reorder_fails(change):
    predecessor = roles.strict_json(audit.tracked(audit.PREDECESSOR_PATH)[0])
    ledger = roles.strict_json(audit.tracked(audit.evolution.LEDGER_PATH.as_posix())[0])
    if change == "delete":
        del ledger["transitions"][8]
    elif change == "reorder":
        ledger["transitions"][7], ledger["transitions"][8] = ledger["transitions"][8], ledger["transitions"][7]
    elif change == "modify":
        ledger["transitions"][8]["phase_id"] = "CORE-01B"
    elif change == "insert_before":
        ledger["transitions"][8], ledger["transitions"][9] = ledger["transitions"][9], ledger["transitions"][8]
    else:
        ledger["transitions"][8] = ledger["transitions"][9]
    ledger["canonical_sha256"] = audit.evolution.canonical_sha256(ledger)
    with pytest.raises(audit.evolution.WorkflowEvolutionError):
        audit.evolution.validate_evolution_snapshot_extension(predecessor, ledger)


def test_receipt_audit_and_no_authority_expansion():
    result = audit.audit()
    assert result["result"] == "PASS" and result["provider_live_actions"] == 0
    receipt = roles.strict_json(audit.tracked(audit.RECEIPT_PATH)[0])
    assert receipt["governance"]["source_review_counter_while_open"] == "2/5"
    assert receipt["workflow_authority_delta"] == 0
    assert receipt["historical_receipts_changed"] is False
    assert all(count == 0 for count in receipt["safety_counts"].values())
