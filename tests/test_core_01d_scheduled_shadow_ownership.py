"""Actual source cutover contracts; every external transport is denied."""
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import smtplib
import socket
import urllib.request
import zipfile

import pytest

from domain.run_contracts import canonical_json_bytes
from scripts import audit_core_01d_scheduled_shadow_ownership as audit
from scripts import audit_lg_a_worker_launch_failure_remediation as lg
from services import athena_run_workflow_request as current


@pytest.fixture(autouse=True)
def deny_external_transport(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("live/provider/email/worker action forbidden")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    monkeypatch.setattr(smtplib, "SMTP_SSL", deny)
    from runtime import worker_launcher
    monkeypatch.setattr(worker_launcher, "_spawn_process", deny)
    from scripts import restore_athena_artifact_roles
    monkeypatch.setattr(restore_athena_artifact_roles.GitHubTransport, "api", deny)


@pytest.fixture(scope="module")
def proposal():
    return audit.actual_modules()


def clock(text="09:00"):
    return datetime.fromisoformat("2026-10-01T" + text + ":00+00:00")


@pytest.mark.parametrize("text", ["09:00", "22:59", "23:00"])
def test_main_schedule_exact_predecessor_bytes(proposal, text):
    resolve = proposal[audit.REQUEST].resolve_workflow_request
    old = audit.predecessor.parse_explicit_request(days="today", target_legs=20,
        profile="main", create_share_code=False, now=clock(text))
    for lane in (None, "main"):
        new = resolve(event_name="schedule", schedule_lane=lane, now=clock(text))
        assert canonical_json_bytes(old) == canonical_json_bytes(new)
        assert (new.authority_profile, new.mode, new.target_legs, new.bookie,
                new.target_total_odds, new.create_share_code, new.place_wager) == (
                    "MAIN", "main_application", 20, "sportybet", None, False, False)


@pytest.mark.parametrize("text", ["09:00", "22:59"])
@pytest.mark.parametrize("intent", [False, True])
def test_shadow_utc_concrete_dates_and_independent_intent(proposal, text, intent):
    request = proposal[audit.REQUEST].resolve_workflow_request(event_name="schedule", schedule_lane="shadow",
        scheduled_shadow_create_share_code=intent, now=clock(text))
    expected = audit.predecessor.parse_explicit_request(days="2026-10-01", target_legs=20,
        profile="shadow", create_share_code=intent, now=clock(text))
    assert canonical_json_bytes(request) == canonical_json_bytes(expected)
    assert request.create_share_code is intent and request.place_wager is False
    assert (request.mode, request.bookie, request.target_total_odds) == ("research_shadow", "sportybet", None)


@pytest.mark.parametrize("intent", [False, True])
def test_23z_rejects_before_persistence_no_shift(proposal, intent, tmp_path):
    module = proposal[audit.PERSIST]
    with pytest.raises(ValueError, match="horizon"):
        module.resolve_and_persist(event_name="schedule", dispatch_inputs=None, github_sha=audit.BASE,
            github_ref="refs/heads/main", output_root=tmp_path, schedule_lane="shadow",
            scheduled_shadow_create_share_code=intent, now=clock("23:00"))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", ["", "SHADOW", "shadow ", "main,shadow", 0, False, [], {}])
def test_bad_schedule_lane_rejects(proposal, bad):
    with pytest.raises(ValueError, match="lane"):
        proposal[audit.REQUEST].resolve_workflow_request(event_name="schedule", schedule_lane=bad, now=clock())


@pytest.mark.parametrize("bad", [None, "false", "true", 0, 1, [], {}])
def test_shadow_does_not_infer_delivery_from_profile(proposal, bad):
    with pytest.raises(ValueError, match="explicit"):
        proposal[audit.REQUEST].resolve_workflow_request(event_name="schedule", schedule_lane="shadow",
            scheduled_shadow_create_share_code=bad, now=clock())


@pytest.mark.parametrize("intent", [False, True])
def test_main_cannot_be_overridden_by_shadow_delivery(proposal, intent):
    with pytest.raises(ValueError, match="MAIN schedule"):
        proposal[audit.REQUEST].resolve_workflow_request(event_name="schedule", schedule_lane="main",
            scheduled_shadow_create_share_code=intent, now=clock())


@pytest.mark.parametrize("profile", ["main", "shadow"])
@pytest.mark.parametrize("intent", ["false", "true"])
@pytest.mark.parametrize("target", ["1", "20", "50"])
def test_manual_inputs_request_and_metadata_unchanged(proposal, profile, intent, target, tmp_path):
    from scripts.resolve_athena_run_workflow_request import resolve_and_persist
    inputs = dict(current.WORKFLOW_DISPATCH_DEFAULTS, profile=profile,
                  create_share_code=intent, target_legs=target, days="2026-10-01,2026-10-02")
    args = dict(event_name="workflow_dispatch", dispatch_inputs=inputs, github_sha=audit.BASE,
                github_ref="refs/heads/main", now=clock())
    old, oldmeta = resolve_and_persist(**args, output_root=tmp_path / "before")
    new, newmeta = proposal[audit.PERSIST].resolve_and_persist(**args, output_root=tmp_path / "after")
    assert canonical_json_bytes(old) == canonical_json_bytes(new)
    assert oldmeta == newmeta
    oracle = audit.predecessor.parse_explicit_request(days=inputs["days"], target_legs=int(target),
        profile=profile, create_share_code=intent == "true", now=clock())
    assert canonical_json_bytes(new) == canonical_json_bytes(oracle)
    assert newmeta == {"github_event_name": "workflow_dispatch", "exact_github_sha": audit.BASE,
        "exact_github_ref": "refs/heads/main", "request_canonical_sha256": oracle.canonical_sha256,
        "dates": ["2026-10-01", "2026-10-02"], "authority_profile": profile.upper(),
        "mode": "main_application" if profile == "main" else "research_shadow", "bookie": "sportybet",
        "create_share_code": intent == "true", "place_wager": False, "timezone": "Africa/Lagos"}
    with pytest.raises(ValueError, match="non-schedule"):
        proposal[audit.REQUEST].resolve_workflow_request(event_name="workflow_dispatch", dispatch_inputs=inputs,
            schedule_lane=profile, now=clock())


@pytest.mark.parametrize("intent", [False, True])
def test_metadata_frozen_lane_intent_dates_sha(proposal, intent, tmp_path):
    request, metadata = proposal[audit.PERSIST].resolve_and_persist(event_name="schedule", dispatch_inputs=None,
        github_sha=audit.BASE, github_ref="refs/heads/main", output_root=tmp_path,
        schedule_lane="shadow", scheduled_shadow_create_share_code=intent, now=clock())
    assert metadata["schedule_lane"] == "shadow"
    assert metadata["original_schedule_intent"] == "UTC_TODAY"
    assert metadata["dates"] == ["2026-10-01"]
    assert metadata["date_policy_status"] == "EXACT_UTC_DATE_REPRESENTABLE"
    assert metadata["request_canonical_sha256"] == request.canonical_sha256
    assert json.loads((tmp_path / "workflow-request-resolution.json").read_bytes()) == metadata


def fixtures(event="schedule"):
    run = {"id": 100, "path": audit.CANONICAL, "repository": {"full_name": "Thabearr/ATHENA"},
        "head_repository": {"full_name": "Thabearr/ATHENA"}, "head_branch": "main", "status": "completed",
        "conclusion": "success", "head_sha": audit.BASE, "event": event}
    def artifact(name, identity):
        return {"id": identity, "name": name, "expired": False,
                "workflow_run": {"id": 100, "head_sha": audit.BASE, "head_branch": "main"}}
    return run, artifact("athena-run-100", 200), artifact("athena-run-100-scheduled-shadow", 201)


def discover(proposal, run, artifacts):
    class Metadata(proposal[audit.RESTORE].GitHubTransport):
        def api(self, *args, **kwargs):
            pytest.fail("fixture transport attempted GitHub API")
        def pages(self, endpoint, field):
            return [run] if field == "workflow_runs" else artifacts
    return Metadata().candidates(audit.CANONICAL, canonical_producer=True)


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_historical_names_remain_valid(proposal, event):
    run, old, suffix = fixtures(event)
    candidate, = discover(proposal, run, [old])
    assert candidate.artifact_name == "athena-run-100"
    proposal[audit.ROLES].validate_candidate(candidate, current_run_id=101,
        role_id="PR119_BOOTSTRAP", canonical_producer=True)


def test_dual_lane_one_candidate_suffix_never_main(proposal):
    run, old, suffix = fixtures()
    candidate, = discover(proposal, run, [old, suffix])
    assert candidate.artifact_id == 201 and candidate.artifact_name.endswith("-scheduled-shadow")
    proposal[audit.ROLES].validate_candidate(candidate, current_run_id=101,
        role_id="PR119_BOOTSTRAP", canonical_producer=True)


@pytest.mark.parametrize("bad", ["suffix_duplicate", "old_duplicate", "manual_suffix"])
def test_ambiguity_and_wrong_event_fail_closed(proposal, bad):
    run, old, suffix = fixtures()
    artifacts = [old, suffix]
    if bad == "suffix_duplicate": artifacts += [dict(suffix, id=202)]
    elif bad == "old_duplicate": artifacts += [dict(old, id=202)]
    else: run["event"] = "workflow_dispatch"
    with pytest.raises(ValueError): discover(proposal, run, artifacts)


@pytest.mark.parametrize("bad", ["expired_suffix", "wrong_suffix_head", "wrong_suffix_run", "expired_old", "failed", "foreign_repo", "foreign_head", "feature", "unknown_event"])
def test_rejected_metadata_no_main_downgrade(proposal, bad):
    run, old, suffix = fixtures()
    artifacts = [old, suffix]
    if bad == "expired_suffix": suffix["expired"] = True
    elif bad == "wrong_suffix_head": suffix["workflow_run"]["head_sha"] = "d" * 40
    elif bad == "wrong_suffix_run": suffix["workflow_run"]["id"] = 99
    elif bad == "expired_old": old["expired"] = True; artifacts = [old]
    elif bad == "failed": run["conclusion"] = "failure"
    elif bad == "foreign_repo": run["repository"]["full_name"] = "Other/Repo"
    elif bad == "foreign_head": run["head_repository"]["full_name"] = "Other/Repo"
    elif bad == "feature": run["head_branch"] = "feature"
    else: run["event"] = "push"
    assert discover(proposal, run, artifacts) == []


@pytest.mark.parametrize("event,name,accepted", [
    ("schedule", "athena-run-100", True), ("schedule", "athena-run-100-scheduled-shadow", True),
    ("workflow_dispatch", "athena-run-100", True), ("workflow_dispatch", "athena-run-100-scheduled-shadow", False),
    ("schedule", "athena-run-99-scheduled-shadow", False), ("schedule", "athena-run-100-main", False),
    ("push", "athena-run-100", False), ("schedule", "athena-run-100-scheduled-shadow-extra", False)])
def test_exact_candidate_name_event_vocabulary(proposal, event, name, accepted):
    roles = proposal[audit.ROLES]
    candidate = roles.Candidate(100, audit.BASE, audit.CANONICAL, 200, name, event_name=event)
    if accepted:
        roles.validate_candidate(candidate, current_run_id=101, role_id="PR119_BOOTSTRAP", canonical_producer=True)
    else:
        with pytest.raises(ValueError):
            roles.validate_candidate(candidate, current_run_id=101, role_id="PR119_BOOTSTRAP", canonical_producer=True)


@pytest.mark.parametrize("change", [{"head_branch": "feature"}, {"conclusion": "failure"}, {"repository": "Other/Repo"}, {"workflow_path": audit.LEGACY}, {"run_id": 101}, {"head_sha": "invalid"}])
def test_suffix_does_not_bypass_trust_or_self_guard(proposal, change):
    roles = proposal[audit.ROLES]
    candidate = roles.Candidate(100, audit.BASE, audit.CANONICAL, 201, "athena-run-100-scheduled-shadow", event_name="schedule")
    with pytest.raises(ValueError):
        roles.validate_candidate(replace(candidate, **change), current_run_id=101,
            role_id="PR119_BOOTSTRAP", canonical_producer=True)


@pytest.mark.parametrize("delivery", [False, True])
@pytest.mark.parametrize("status", ["RESEARCH_SHADOW_PORTFOLIO_READY", "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL",
    "RESEARCH_SHADOW_CODE_VERIFIED", "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL", "SOURCE_INCOMPLETE", "UNKNOWN", "EXECUTOR_UNAVAILABLE"])
def test_existing_receipt_vocabulary_not_filename_grants_eligibility(proposal, delivery, status):
    request = replace(lg.successful_receipt().request, create_share_code=delivery)
    receipt = lg.successful_receipt(request, status=status)
    accepted = status in ({"RESEARCH_SHADOW_CODE_VERIFIED", "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL"} if delivery else
        {"RESEARCH_SHADOW_PORTFOLIO_READY", "RESEARCH_SHADOW_PORTFOLIO_READY_WITH_SHORTFALL"})
    assert proposal[audit.ROLES].is_restore_eligible_shadow_receipt(receipt) is accepted
    if accepted:
        proposal[audit.ROLES].validate_producer_receipt(canonical_json_bytes(receipt),
            request_sha256=request.canonical_sha256, head_sha=receipt.exact_commit_sha)
    else:
        with pytest.raises(ValueError, match="restore-ineligible"):
            proposal[audit.ROLES].validate_producer_receipt(canonical_json_bytes(receipt),
                request_sha256=request.canonical_sha256, head_sha=receipt.exact_commit_sha)


def test_scheduled_main_never_restore_eligible(proposal):
    from services.athena_run_service import AthenaRunService
    request = current.resolve_workflow_request(event_name="schedule", now=clock())
    receipt = replace(lg.successful_receipt(), request=request, status="MAIN_PHASE6_AUTHORITY_REQUIRED",
                      authority_manifest=AthenaRunService.authority_manifest_for(request))
    assert not proposal[audit.ROLES].is_restore_eligible_shadow_receipt(receipt)


def test_scheduled_suffix_archive_v1_actual_verification(proposal, tmp_path):
    # Derive a synthetic scheduled archive from the established older-canonical
    # fixture. Only producer event is changed; no historical fixture is edited.
    original = zipfile.ZipFile(io.BytesIO(lg.failed_archive(older=True)))
    members = {name: original.read(name) for name in original.namelist()}
    name = "athena-run-workflow/artifact-role-manifest-v1.json"
    manifest = json.loads(members[name])
    manifest["producer"]["event_name"] = "schedule"
    manifest["canonical_sha256"] = proposal[audit.ROLES].self_sha(manifest)
    members[name] = proposal[audit.ROLES].canonical(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items(): archive.writestr(name, content)
    transport = proposal[audit.RESTORE]
    transport.extract_verified_paths(buffer.getvalue(), tmp_path)
    roles = proposal[audit.ROLES]
    producer = manifest["producer"]
    candidate = roles.Candidate(producer["run_id"], producer["head_sha"], audit.CANONICAL, 123,
        f"athena-run-{producer['run_id']}-scheduled-shadow", event_name="schedule")
    root = transport.manifest_root(tmp_path)
    transport.verify_archive_producer_receipt(tmp_path, root, members["athena-run-workflow/artifact-role-manifest-v1.json"], candidate)
    roles.validate_manifest(members["athena-run-workflow/artifact-role-manifest-v1.json"], root, candidate,
        current_run_id=0, role_id="PR119_BOOTSTRAP")
    from scripts.build_athena_artifact_role_manifest import build_manifest
    rebuilt = build_manifest(root, producer=producer,
        origins={row["role_id"]: row["origin_provenance"] for row in manifest["roles"]}, restore_eligible=True)
    assert rebuilt == manifest  # unchanged builder / V1 producer schema suffices
    with pytest.raises(ValueError, match="producer mismatch"):
        roles.validate_manifest(members["athena-run-workflow/artifact-role-manifest-v1.json"], root,
            replace(candidate, event_name="workflow_dispatch", artifact_name=f"athena-run-{producer['run_id']}"),
            current_run_id=0, role_id="PR119_BOOTSTRAP")


def test_workflow_source_collision_concurrency_no_copy_paste():
    audit.validate_workflow_source()
    projected = audit.yaml.load(audit.raw(audit.CANONICAL), Loader=audit.yaml.BaseLoader)
    assert len(projected["jobs"]) == 1 and "concurrency" not in projected
    assert projected["jobs"]["canonical-run"]["strategy"]["fail-fast"] == "false"
    cases = [("workflow_dispatch", "main"), ("workflow_dispatch", "shadow"), ("schedule", "main"), ("schedule", "shadow")]
    names = ["athena-run-100" + ("-scheduled-shadow" if event == "schedule" and lane == "shadow" else "") for event, lane in cases]
    assert names == ["athena-run-100"] * 3 + ["athena-run-100-scheduled-shadow"]
    assert len(set(names[-2:])) == 2


def test_owner_policy_source_cutover_no_dual_live_schedule_no_history_edits():
    expected = audit.expected_receipt()
    assert expected["delivery_disposition"] == audit.DELIVERY
    assert expected["notification_disposition"] == audit.NOTIFICATION
    assert expected["canonical_scheduled_shadow_active"] and expected["legacy_schedule_trigger_removed"]
    assert not expected["deployed_on_main"] and not expected["legacy_delivery_byte_or_intention_parity_claimed"]
    assert expected["evolution"]["transition_count_after"] == 13
    assert expected["source_review_counter_while_open"] == "1/5"
    assert audit.audit()["result"] == "PASS"


def test_accepted_archive_and_failed_history_remain_truthful():
    assert audit.predecessor.accepted_evidence()["run_id"] == 36860297707
    assert lg.historical_producer_proof()["historical_manifest_true_unchanged"]


@pytest.mark.parametrize("accepted", [False, True])
def test_projected_transport_preserves_exact_accepted_and_failed_history(proposal, tmp_path, accepted):
    transport, roles = proposal[audit.RESTORE], proposal[audit.ROLES]
    if accepted:
        payload = (audit.ROOT / audit.predecessor.ZIP_PATH).read_bytes()
        candidate = roles.Candidate(36860297707, audit.predecessor.BASE, audit.CANONICAL,
                                   11163921301, "athena-run-36860297707")
    else:
        payload = lg.failed_archive()
        candidate = roles.Candidate(lg.FAILED.run_id, lg.FAILED.head_sha, audit.CANONICAL,
                                   lg.FAILED.artifact_id, lg.FAILED.artifact_name)
    transport.extract_verified_paths(payload, tmp_path)
    root = transport.manifest_root(tmp_path)
    manifest = (root / roles.MANIFEST_FILENAME).read_bytes()
    if accepted:
        transport.verify_archive_producer_receipt(tmp_path, root, manifest, candidate)
        roles.validate_manifest(manifest, root, candidate, current_run_id=0, role_id="PERSISTENT_FIXTURE_IDENTITY_STATE")
    else:
        assert json.loads(manifest)["restore_eligible"] is True
        with pytest.raises(ValueError, match="restore-ineligible"):
            transport.verify_archive_producer_receipt(tmp_path, root, manifest, candidate)


@pytest.mark.parametrize("bad", [datetime(2026, 10, 1, 9), "2026-10-01", 0])
def test_bad_shadow_clock_rejects(proposal, bad):
    with pytest.raises(ValueError, match="timezone-aware"):
        proposal[audit.REQUEST].resolve_workflow_request(event_name="schedule", schedule_lane="shadow",
            scheduled_shadow_create_share_code=False, now=bad)


def test_tampered_inventory_and_rehashed_receipt_reject(monkeypatch):
    original = audit.raw
    monkeypatch.setattr(audit, "raw", lambda path: b'{}' if path == audit.INPUT_PATH else original(path))
    with pytest.raises(ValueError, match="inventory drift"): audit.verify_inputs()
    monkeypatch.setattr(audit, "raw", original)
    value = audit.predecessor.strict(original(audit.RECEIPT_PATH))
    value["canonical_scheduled_shadow_active"] = False
    audit.predecessor.seal(value)
    monkeypatch.setattr(audit, "raw", lambda path: audit.predecessor.canonical(value) if path == audit.RECEIPT_PATH else original(path))
    with pytest.raises(ValueError, match="unreviewed"): audit.verified_receipt_path()
