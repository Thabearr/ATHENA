from dataclasses import replace
import json
from pathlib import Path
import socket
import smtplib
import urllib.request

import pytest

from domain.current_shadow_run_contract_adapter import is_successful_canonical_shadow_terminal_status as terminal
from domain.run_contracts import RunContractError, canonical_json_bytes
from runtime import worker_launcher as worker
from runtime.release_identity import verify_development_checkout
from scripts import audit_lg_a_worker_launch_failure_remediation as audit
from scripts.restore_athena_artifact_roles import extract_verified_paths, manifest_root, verify_archive_producer_receipt
from services import athena_artifact_role_resolver as roles
from services.athena_run_service import _run_reviewed_shadow_worker


@pytest.fixture(autouse=True)
def no_live_actions(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError("Live/provider/delivery action forbidden during remediation")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    monkeypatch.setattr(smtplib, "SMTP_SSL", deny)
    monkeypatch.setattr(worker, "_spawn_process", deny)
    from domain import sportybet_share_code
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code", deny)
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code_as_of", deny)
    from scripts import send_current_shadow_email
    monkeypatch.setattr(send_current_shadow_email, "send_receipt_email", deny)


def test_production_relative_path_fixed_at_real_worker_boundary():
    assert audit.worker_boundary_proof()["worker_command_publication"] == "PASS"


def test_unadapted_production_shape_reproduces_old_rejection(tmp_path):
    with audit.production_run_directory(tmp_path) as (request, directory):
        identity = verify_development_checkout(audit.ROOT)
        with pytest.raises(worker.WorkerLaunchError, match="absolute"):
            worker.WorkerCommand(operation="CURRENT_SHADOW_REQUEST", mode="research_shadow", run_directory=directory,
                request_artifact_id=request.canonical_sha256, envelope_artifact_id=None,
                release_identity_kind=identity.identity_kind, release_identity_id=identity.head_commit_sha)
        assert not (directory / worker.WORKER_COMMAND_FILENAME).exists()


@pytest.mark.parametrize("bad", ["traversal", "symlink", "wrong_sha", "contradictory"])
def test_caller_does_not_weaken_worker_validation(tmp_path, monkeypatch, bad):
    with audit.production_run_directory(tmp_path) as (request, directory):
        identity = verify_development_checkout(audit.ROOT)
        if bad == "traversal":
            directory = directory.parent / ".." / directory.parent.name / directory.name
        elif bad == "symlink":
            # Deterministic link-component evidence on hosts without symlink privilege.
            from runtime import worker_launcher
            original = worker_launcher._is_link_or_junction
            marker = Path.cwd() / "artifacts"
            monkeypatch.setattr(worker_launcher, "_is_link_or_junction", lambda path: path == marker or original(path))
        elif bad == "wrong_sha":
            (directory / "athena-run-request.json").write_bytes(canonical_json_bytes(replace(request, target_legs=19)))
        else:
            (directory / worker.WORKER_COMMAND_FILENAME).write_bytes(b"CONTRADICTORY_EXISTING_COMMAND")
        with pytest.raises(worker.WorkerLaunchError):
            _run_reviewed_shadow_worker(request, run_directory=directory, exact_commit_sha=identity.head_commit_sha)


@pytest.mark.parametrize("status", ["RESEARCH_SHADOW_PORTFOLIO_READY", "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL",
    "RESEARCH_SHADOW_CODE_VERIFIED", "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL", "SOURCE_INCOMPLETE",
    "EXECUTOR_UNAVAILABLE", "CODE_VERIFICATION_FAILED", "SHADOW_DATE_POLICY_UNREPRESENTABLE",
    "TARGET_TOTAL_ODDS_NOT_SUPPORTED", "MAIN_PHASE6_AUTHORITY_REQUIRED", "RESEARCH_SHADOW_PORTFOLIO_READY_EXTRA", "UNKNOWN"])
@pytest.mark.parametrize("delivery", [False, True])
def test_exact_domain_status_vocabulary_and_delivery_intent(status, delivery):
    successes = ({"RESEARCH_SHADOW_CODE_VERIFIED", "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL"} if delivery else
                 {"RESEARCH_SHADOW_PORTFOLIO_READY", "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL"})
    assert terminal(status, create_share_code=delivery) == (status in successes)
    request = replace(audit.successful_receipt().request, create_share_code=delivery)
    assert roles.is_restore_eligible_shadow_receipt(audit.successful_receipt(request, status=status)) == (status in successes)


def test_invalid_status_or_delivery_type_is_not_success():
    assert not terminal([], create_share_code=False)
    assert not terminal("RESEARCH_SHADOW_PORTFOLIO_READY", create_share_code=0)


def test_builder_actual_publication_matrix():
    rows = audit.builder_proof()
    assert len(rows) == 9 and sum(row["eligible"] for row in rows) == 4


@pytest.mark.parametrize("unsafe", ["wager", "share_result", "manifest_delivery"])
def test_no_delivery_inconsistent_receipts_reject_or_are_ineligible(unsafe):
    receipt = audit.successful_receipt()
    if unsafe == "manifest_delivery":
        receipt = replace(receipt, authority_manifest=replace(receipt.authority_manifest, share_code_generation=True))
        assert not roles.is_restore_eligible_shadow_receipt(receipt)
    else:
        with pytest.raises(RunContractError):
            replace(receipt, **({"wager_placed": True} if unsafe == "wager" else {"share_code_result": {"share_code": "UNSAFE"}}))


def test_exact_historical_true_manifest_rejected_and_both_fallbacks_work():
    proof = audit.historical_producer_proof()
    assert proof["historical_manifest_true_unchanged"] is True
    assert proof["older_canonical_fallback"] == proof["fixed_pr119_fallback"] == "PASS"


@pytest.mark.parametrize("bad", ["missing", "duplicate", "tampered", "head", "request", "noncanonical", "duplicate_key", "run"])
def test_independent_archive_receipt_binding_rejections(tmp_path, bad):
    from scripts.restore_athena_artifact_roles import restore_inputs
    extract_verified_paths(audit.failed_archive(older=True), tmp_path)
    root = manifest_root(tmp_path)
    manifest = roles.strict_json((root / roles.MANIFEST_FILENAME).read_bytes())
    candidate = replace(audit.FAILED, run_id=audit.FAILED.run_id-1, artifact_name=f"athena-run-{audit.FAILED.run_id-1}")
    path = tmp_path / "athena-runs" / audit.REQUEST_SHA / "athena-run-receipt.json"
    raw = path.read_bytes()
    if bad == "missing": path.unlink()
    elif bad == "duplicate":
        other = tmp_path / "artifacts" / path.relative_to(tmp_path)
        other.parent.mkdir(parents=True)
        other.write_bytes(raw)
    elif bad == "tampered": path.write_bytes(raw.replace(b'"wager_placed":false', b'"wager_placed":true'))
    elif bad == "head": candidate = replace(candidate, head_sha="a"*40)
    elif bad == "request": path.write_bytes(canonical_json_bytes(audit.successful_receipt(replace(audit.successful_receipt().request, target_legs=19))))
    elif bad == "noncanonical": path.write_bytes(raw+b" ")
    elif bad == "duplicate_key": path.write_bytes(raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'))
    else:
        manifest["producer"]["run_id"] += 1
        manifest["canonical_sha256"] = roles.self_sha(manifest)
    with pytest.raises((ValueError, OSError)):
        verify_archive_producer_receipt(tmp_path, root, roles.canonical(manifest), candidate)
        roles.validate_manifest(roles.canonical(manifest), root, candidate,
                                current_run_id=audit.FAILED.run_id+1, role_id="PR119_BOOTSTRAP")


def test_receipt_matches_independent_audit():
    expected = audit.expected_receipt()
    assert json.loads(audit.tracked(audit.RECEIPT_PATH)) == expected
