"""Source-safe C4 regressions; no live executor, provider or SMTP transport."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import zipfile

import pytest

from domain.run_contracts import canonical_json_bytes
from services.athena_run_request_parser import parse_explicit_request
from services.athena_run_workflow_request import resolve_workflow_request
from services import athena_shadow_issue_comment_compatibility as comment
from scripts import audit_checkpoint_e_workflows as audit
from scripts.restore_athena_artifact_roles import extract_verified_paths
from runtime.source_identity import read_tracked_head_blob


@pytest.fixture(scope="module")
def documents():
    return json.loads(audit.read(audit.MATRIX_PATH)), json.loads(audit.read(audit.RECEIPT_PATH))


def test_full_source_archive_and_evolution_audit_offline():
    result = audit.audit()
    assert result["result"] == "PASS"
    assert result["checkpoint_e"] == "INCOMPLETE"
    assert result["workflow_count"] == 39
    assert set(result["live_side_effect_counts"].values()) == {0}


@pytest.mark.parametrize("path", sorted(path.relative_to(audit.ROOT).as_posix() for path in (audit.ROOT / ".github/workflows").glob("*.yml")))
def test_every_workflow_and_exact_trigger_surface_present(path, documents):
    matrix, receipt = documents
    row, = [row for row in matrix["workflow_rows"] if row["workflow_path"] == path]
    doc = audit.yaml.load(audit.read(path), Loader=audit.yaml.BaseLoader)
    assert [surface["trigger_kind"] for surface in row["trigger_surfaces"]] == sorted(doc["on"])
    assert row["deletion_eligible"] is False
    assert row["rollback"]["commit"] == audit.BASE
    assert row["last_relevant_historical_runs"] is not None
    assert all(surface["retained_reason"] for surface in row["trigger_surfaces"])


@pytest.mark.parametrize("target", range(1, 51))
def test_legacy_target_maps_exactly_without_delivery_intent_invention(target):
    now = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
    result = comment.resolve_comment(f"/athena-shadow target={target} dates=20261001,20261002", now=now)
    request = parse_explicit_request(days="2026-10-01,2026-10-02", target_legs=target,
                                     profile="shadow", create_share_code=True, now=now)
    assert result.canonical_request_bytes == canonical_json_bytes(request)
    assert not result.dispatch_authority
    # An analysis-only replacement is intentionally NOT claimed byte-equivalent.
    analysis = parse_explicit_request(days="2026-10-01,2026-10-02", target_legs=target,
                                      profile="shadow", create_share_code=False, now=now)
    assert analysis.canonical_sha256 != result.canonical_request_sha256


@pytest.mark.parametrize("hour,minute,representable", [(9, 0, True), (22, 59, True), (23, 0, False)])
@pytest.mark.parametrize("scope", ["today", "three-day"])
def test_utc_boundary_no_shift_no_fabrication(hour, minute, representable, scope):
    now = datetime(2026, 10, 1, hour, minute, tzinfo=timezone.utc)
    result = comment.resolve_comment(f"/athena-shadow target=20 scope={scope}", now=now)
    assert result.legacy_utc_resolved_dates[0] == "20261001"
    assert (result.compatibility_status == comment.REPRESENTABLE) is representable
    if not representable:
        assert result.canonical_request_bytes is result.canonical_request_sha256 is None
    scheduled = resolve_workflow_request(event_name="schedule", now=now)
    assert scheduled.authority_profile == "MAIN"
    assert scheduled.target_legs == 20 and scheduled.bookie == "sportybet"
    assert not scheduled.create_share_code and not scheduled.place_wager


@pytest.mark.parametrize("command", ["/athena-shadow target=0 scope=today", "/athena-shadow target=51 scope=today",
    "/athena-shadow target=20 scope=week", "/athena-shadow target=20 dates=20261001,20261001",
    "/athena-shadow target=20 dates=20261008", "/athena-shadow target=20 dates=2026-10-01",
    "/athena-shadow target=20 scope=today extra", "/athena-shadow target=20 scope=today\n"])
def test_malformed_legacy_input_fails_closed(command):
    with pytest.raises(ValueError):
        comment.resolve_comment(command, now=datetime(2026, 10, 1, 9, tzinfo=timezone.utc))


def test_failed_lga_stays_ineligible_with_true_historical_manifest():
    root = audit.ROOT / "tests/fixtures/lg_a_worker_launch_failure"
    manifest = json.loads((root / "artifact-role-manifest-v1.json").read_bytes())
    assert manifest["restore_eligible"] is True
    with pytest.raises(ValueError, match="restore-ineligible"):
        audit.roles.validate_producer_receipt(read_tracked_head_blob(audit.ROOT, "tests/fixtures/lg_a_worker_launch_failure/athena-run-receipt.json")[0],
            request_sha256=manifest["producer"]["request_sha256"], head_sha=manifest["producer"]["head_sha"])


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "a\\b", "C:/escape"])
def test_unsafe_zip_member_rejected(name, tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name.replace("\\", "/"), b"UNTRUSTED")
    # Windows ZipInfo normalizes backslashes while constructing a member. Build
    # the adversarial on-wire name instead; do not silently test a safe slash.
    raw = buffer.getvalue().replace(name.replace("\\", "/").encode(), name.encode())
    with pytest.raises(ValueError):
        extract_verified_paths(raw, tmp_path)


def test_duplicate_archive_member_rejected(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("same", b"first")
        with pytest.warns(UserWarning):
            archive.writestr("same", b"second")
    with pytest.raises(ValueError, match="duplicate"):
        extract_verified_paths(buffer.getvalue(), tmp_path)


@pytest.mark.parametrize("field", ["run_id", "exact_head", "artifact_id", "artifact_name", "local_zip_sha256", "attempt", "terminal"])
def test_accepted_anchor_tamper_rejected_even_after_rehash(field, documents):
    matrix, receipt = deepcopy(documents)
    receipt["accepted_lg_a"][field] = "TAMPERED"
    audit.seal(receipt)
    with pytest.raises(ValueError, match="accepted LG-A"):
        audit.validate_documents(matrix, receipt)


@pytest.mark.parametrize("mutation", ["workflow_count", "trigger_coverage", "missing_status", "deletion", "grammar", "notification", "date_shift", "false_complete", "authority", "failed_producer"])
def test_checkpoint_fail_closed_mutations(mutation, documents):
    matrix, receipt = deepcopy(documents)
    if mutation == "workflow_count": matrix["workflow_count"] += 1
    elif mutation == "trigger_coverage": matrix["workflow_rows"][0]["trigger_surfaces"].pop()
    elif mutation == "missing_status": matrix["workflow_rows"][0]["supported_status"] = ""
    elif mutation == "deletion": receipt["retired_workflows"] = [audit.SHADOW]
    elif mutation == "grammar": receipt["issue_comment_disposition"]["grammars"][0] += "|anything"
    elif mutation == "notification": receipt["notification_disposition"]["legacy"] = "AUTHORITATIVE"
    elif mutation == "date_shift": receipt["date_schedule_disposition"]["parity_evidence"][0]["date_shift"] = True
    elif mutation == "false_complete": receipt["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "authority": receipt["semantic_delta"]["provider_market"] = 1
    elif mutation == "failed_producer": receipt["historical_failed_lg_a"]["restore_eligible"] = True
    audit.seal(matrix)
    receipt["workflow_matrix_sha256"] = matrix["canonical_sha256"]
    audit.seal(receipt)
    with pytest.raises(ValueError): audit.validate_documents(matrix, receipt)


@pytest.mark.parametrize("missing", range(1, 15))
def test_every_retirement_check_is_mandatory(missing):
    row = {"deletion_eligible": True, "last_relevant_historical_runs": {"last_successful": {"id": 1}},
           "rollback": {"commit": audit.BASE}, "supported_callers_remaining": [],
           "required_restore_dependencies": [], "retirement_checklist": dict.fromkeys(range(1, 15), True)}
    row["retirement_checklist"][missing] = False
    with pytest.raises(ValueError, match="14-point"): audit.validate_retirement_row(row)


@pytest.mark.parametrize("dependency", ["supported_callers_remaining", "required_restore_dependencies"])
def test_retired_workflow_cannot_remain_required(dependency):
    row = {"deletion_eligible": True, "last_relevant_historical_runs": {"last_successful": {"id": 1}},
           "rollback": {"commit": audit.BASE}, "supported_callers_remaining": [],
           "required_restore_dependencies": [], "retirement_checklist": dict.fromkeys(range(1, 15), True)}
    row[dependency] = ["supported consumer"]
    with pytest.raises(ValueError, match="reachable/required"): audit.validate_retirement_row(row)


def test_checkpoint_completion_requires_every_boolean():
    assert audit.checkpoint_status({"a": True, "b": True}) == ("COMPLETE", [])
    assert audit.checkpoint_status({"a": True, "b": False}) == ("INCOMPLETE", ["b"])
    with pytest.raises(ValueError): audit.checkpoint_status({"a": "UNKNOWN"})


def test_mocked_notification_preserves_business_receipt_and_failure_boundary():
    from scripts.audit_core_01c_notification_comment_compatibility import notification_evidence
    rows = notification_evidence()
    assert rows[0]["status"] == "EMAIL_SKIPPED_UNCONFIGURED"
    assert rows[1]["status"] == "EMAIL_DELIVERED"
    assert all(row["status"] == "EMAIL_FAILED" and row["warning_emitted"] for row in rows[2:])
    assert all(row["source_before_sha256"] == row["source_after_sha256"] and not row["secrets_recorded"] for row in rows)


def test_unsupported_odds_fails_before_any_executor(tmp_path):
    from services.athena_run_service import AthenaRunService
    def forbidden(*args, **kwargs):
        pytest.fail("unsupported objective invoked executor")
    request = parse_explicit_request(days="today", target_legs=20, target_total_odds="100",
        profile="shadow", create_share_code=False, now=datetime(2026, 10, 1, 9, tzinfo=timezone.utc))
    service = AthenaRunService(_test_executor_overrides={
        ("SHADOW", "research_shadow", "sportybet"): forbidden}, _commit_sha_provider=lambda: audit.BASE)
    receipt = service.run(request, output_root=tmp_path)
    assert receipt.status == "TARGET_TOTAL_ODDS_NOT_SUPPORTED"
    assert not receipt.wager_placed


def test_base_input_tamper_rejected_before_any_git_scan(monkeypatch):
    original = audit.read
    monkeypatch.setattr(audit, "read", lambda path: b'{"base_main_sha":"TAMPERED"}' if path == audit.BASE_PATH else original(path))
    with pytest.raises(ValueError, match="base inventory identity drift"): audit.base_input()


@pytest.mark.parametrize("path", sorted(audit.PASS1_V1_BASE_SOURCE_FIXTURES))
def test_checkpoint_v1_base_source_fixtures_are_shallow_checkout_safe(path, monkeypatch):
    def reject_base_git_show(*args):
        if args[:1] == ("show",) and len(args) > 1 and args[1].startswith(f"{audit.BASE}:"):
            pytest.fail("immutable Checkpoint E V1 source must not require deep Git history")
        return original_git(*args)

    original_git = audit.git
    monkeypatch.setattr(audit, "git", reject_base_git_show)
    raw = audit.read(path)
    expected_blob, expected_sha = audit.PASS1_V1_BASE_SOURCE_FIXTURES[path][1:]
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected_blob
    assert audit.sha(raw) == expected_sha


def test_additive_artifacts_are_authenticated_not_blanket_excluded(monkeypatch):
    original = audit.read
    monkeypatch.setattr(audit, "read", lambda path: b'{"canonical_sha256":"forged"}' if path == audit.MATRIX_PATH else original(path))
    with pytest.raises(ValueError, match="unreviewed additive"): audit.verified_additive_artifact_paths()
