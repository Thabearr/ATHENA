"""Synthetic-only write-ahead CREATE, response proof and no-resend regressions."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from urllib.error import URLError

import pytest

from database.run_repository import DurableRunRepository, ExternalOperationViolation, SHARE_CREATE_KIND
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import canonical_json_bytes
from services.athena_preview_service import AthenaPreviewAdmissionService, AdmissionCandidate
from services.durable_share_code_transport import DurableShareCodeTransport, DeliveryOutcome as Outcome
from scripts import sportybet_direct_share_bridge as bridge
from test_data_01a_app_schema import resources, roots, clock, open_repo, record_test_release
from test_data_01b_durable_run_state import development_durable, _running, _receipt

SELECTIONS = [{"eventId": "sr:match:1", "marketId": "18", "outcomeId": "12"}]


@pytest.fixture
def context(resources, roots, clock, request):
    preview = AthenaPreviewAdmissionService(resources, clock=clock)
    result = preview.preview(dates=["2030-01-01"], target_legs=3, target_total_odds=None,
                             bookie="sportybet", profile="shadow", acquire_sources=True,
                             create_share_code=getattr(request, "param", True))
    item = preview.preview_store.get(result["preview_id"], now=clock())
    envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
    app = open_repo(resources, roots)
    record_test_release(app, clock())
    app.persist_preview_bundle(item=item, envelope=envelope, release_id="test-release",
                               profile_id="local-default", now=clock())
    app.close()
    candidate = AdmissionCandidate(item.preview_id, item.request_bytes, envelope.request_sha256,
                                   item.envelope_bytes, envelope.canonical_sha256, "share-pre-test",
                                   envelope.authority_manifest_sha256,
                                   hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(),
                                   envelope.expires_at)
    repo = DurableRunRepository(resources, roots, clock=clock)
    run = repo.admit(candidate).run_id
    attempt, lease, _ = repo.claim_attempt(run, worker_instance_id="synthetic-share",
                                          process_locator={"kind": "OFFLINE_TEST", "label": "fixture"})
    repo.transition_run(run, expected_version=0, state="RUNNING", attempt_id=attempt, lease_token=lease)
    return repo, run, {"attempt_id": attempt, "lease_token": lease}, roots


def response(value, status=200):
    return bridge.HttpResponseEvidence(status, canonical_json_bytes(value))


def create_success():
    return response({"bizCode": 10000, "data": {"shareCode": "ABC123", "outcomes": [{}],
                                                "unavailableOutcomes": []}})


def reload_success():
    return response({"bizCode": 10000, "data": {"outcomes": [{}], "unavailableOutcomes": [],
                                                "ticket": {"selections": SELECTIONS}}})


def service(context, post=None, get=None):
    repo, run, owner, _ = context
    return DurableShareCodeTransport(repo, run_id=run, **owner,
                                    post_create_once=post or (lambda **_: create_success()),
                                    load_share_code_once=get or (lambda **_: reload_success()))


def operations(context):
    repo, run, _, _ = context
    with repo._operation() as conn:
        return conn.execute("SELECT operation_id,state,error_code FROM app_external_operations WHERE run_id=?", (run,)).fetchall()


def test_write_ahead_once_and_retained_response_before_confirmed(context, monkeypatch):
    repo, run, owner, _ = context
    observed = []
    transition = repo.transition_external_operation
    def tracked(*args, **kwargs):
        if kwargs["state"] == "SENT":
            assert operations(context)[0][1] == "PREPARED"
        if kwargs["state"] == "CONFIRMED":
            proven = repo.read_share_code_response(run, args[1], kwargs["response_artifact_id"], **owner)
            assert proven == create_success()
        return transition(*args, **kwargs)
    monkeypatch.setattr(repo, "transition_external_operation", tracked)
    def post(**kwargs):
        assert operations(context)[0][1] == "SENT"  # independent read after FULL commit
        assert kwargs["request_bytes"] == bridge.build_create_request(SELECTIONS)
        observed.append("POST")
        return create_success()
    def get(*, code):
        assert operations(context)[0][1] == "CONFIRMED"
        assert code == "ABC123"
        observed.append("GET")
        return reload_success()
    transport = service(context, post, get)
    result = transport.create(SELECTIONS)
    assert result.outcome == Outcome.CREATE_CONFIRMED_RELOAD_VERIFIED
    assert transport.create(SELECTIONS).outcome == Outcome.CREATE_CONFIRMED_RELOAD_UNVERIFIED
    assert observed == ["POST", "GET"]
    assert len(operations(context)) == 1


@pytest.mark.parametrize("phase", ["prepare", "sent"])
def test_pre_send_failure_never_posts(context, monkeypatch, phase):
    repo, _, _, _ = context
    calls = []
    def deny(*args, **kwargs):
        raise ValueError("secret raw exception must not persist")
    if phase == "prepare":
        monkeypatch.setattr(repo, "prepare_share_code_create", deny)
    else:
        original = repo.transition_external_operation
        def transition(*args, **kwargs):
            if kwargs["state"] == "SENT":
                deny()
            return original(*args, **kwargs)
        monkeypatch.setattr(repo, "transition_external_operation", transition)
    assert service(context, lambda **_: calls.append(1)).create(SELECTIONS).outcome == Outcome.LOCAL_PRE_SEND_BLOCKED
    assert calls == []
    if phase == "sent":
        assert operations(context)[0][1:] == ("FAILED", "SHARE_CREATE_NEVER_SENT")


@pytest.mark.parametrize("error", [RuntimeError("secret"), TimeoutError("secret"),
                                    ConnectionResetError("secret"), URLError("secret")])
def test_sent_exception_is_unknown_without_resend(context, error):
    calls = []
    def post(**_):
        calls.append(1)
        raise error
    transport = service(context, post)
    result = transport.create(SELECTIONS)
    assert result.outcome == Outcome.CREATE_OUTCOME_UNKNOWN
    assert operations(context)[0][1:] == ("OUTCOME_UNKNOWN", "SHARE_CREATE_TRANSPORT_UNKNOWN")
    transport.create(SELECTIONS)
    assert calls == [1]
    repo, run, owner, _ = context
    row = repo.share_code_operation(run, result.operation_id, **owner)
    with pytest.raises(ExternalOperationViolation):
        repo.transition_external_operation(run, result.operation_id, **owner,
                                           expected_state="OUTCOME_UNKNOWN", state="SENT")
    with pytest.raises(ExternalOperationViolation):
        repo.prepare_external_operation(run, **owner, operation_kind=SHARE_CREATE_KIND,
                                        intent_sha256=row["intent_sha256"], authority_sha256=row["authority_sha256"],
                                        input_artifact_id=row["input_artifact_id"], idempotency_key="new-key")


@pytest.mark.parametrize("evidence", [None, bridge.HttpResponseEvidence(200, b""),
    bridge.HttpResponseEvidence(200, b"{truncated"), bridge.HttpResponseEvidence(200, b'{"bizCode":10000,"bizCode":1}'),
    response({"bizCode":12345}), response({"bizCode":10000,"data":{"unavailableOutcomes":[]}}),
    create_success().__class__(503, create_success().raw), bridge.HttpResponseEvidence(302, create_success().raw)])
def test_unproven_response_is_unknown_never_failed_or_reload(context, evidence):
    gets = []
    result = service(context, lambda **_: evidence, lambda **_: gets.append(1)).create(SELECTIONS)
    assert result.outcome == Outcome.CREATE_OUTCOME_UNKNOWN
    assert operations(context)[0][1] == "OUTCOME_UNKNOWN"
    assert gets == []


@pytest.mark.parametrize("fault", ["missing", "hash", "tamper", "cross-run", "traversal", "symlink"])
def test_response_proof_failure_never_confirms(context, monkeypatch, fault):
    repo, run, owner, roots = context
    retain = repo.retain_share_code_response
    def faulty(*args, **kwargs):
        artifact = retain(*args, **kwargs)
        with repo._operation(write=True) as conn:
            locator = conn.execute("SELECT logical_path FROM app_artifacts WHERE artifact_id=?", (artifact,)).fetchone()[0]
            target = roots.data_root / locator
            if fault == "missing":
                target.unlink()
            elif fault == "hash":
                conn.execute("UPDATE app_artifacts SET byte_sha256=? WHERE artifact_id=?", ("0"*64, artifact))
            elif fault == "tamper":
                target.write_bytes(b"tampered")
            elif fault == "cross-run":
                conn.execute("DELETE FROM app_run_artifacts WHERE run_id=? AND artifact_id=?", (run, artifact))
            elif fault == "traversal":
                conn.execute("UPDATE app_artifacts SET logical_path='../escape.json' WHERE artifact_id=?", (artifact,))
            else:
                outside = roots.data_root / "outside.json"
                outside.write_bytes(target.read_bytes())
                target.unlink()
                target.symlink_to(outside)
        return artifact
    monkeypatch.setattr(repo, "retain_share_code_response", faulty)
    assert service(context).create(SELECTIONS).outcome == Outcome.CREATE_OUTCOME_UNKNOWN
    assert operations(context)[0][1] == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize("fault", ["timeout", "mismatch", "http"])
def test_reload_failure_preserves_confirmed_never_posts_twice(context, fault):
    calls = []
    def post(**_):
        calls.append("POST")
        return create_success()
    def get(*, code):
        assert code == "ABC123"
        calls.append("GET")
        if fault == "timeout":
            raise TimeoutError("secret")
        if fault == "http":
            return bridge.HttpResponseEvidence(503, b"{}");
        value = json.loads(reload_success().raw)
        value["data"]["ticket"]["selections"][0]["outcomeId"] = "13"
        return response(value)
    transport = service(context, post, get)
    result = transport.create(SELECTIONS)
    assert result.outcome == Outcome.CREATE_CONFIRMED_RELOAD_UNVERIFIED
    assert operations(context)[0][1] == "CONFIRMED"
    transport.reload(result.operation_id)
    transport.create(SELECTIONS)
    assert calls == ["POST", "GET", "GET"]


@pytest.mark.parametrize("fault", ["lease", "cancel", "cancelled", "interrupted", "request", "envelope", "input-link"])
def test_state_and_identity_fail_closed(context, fault):
    repo, run, owner, _ = context
    if fault == "lease":
        context = (repo, run, {**owner, "lease_token":"stale"}, context[3])
    elif fault == "cancel":
        repo.request_cancel(run, expected_version=1)
    elif fault == "cancelled":
        repo.request_cancel(run, expected_version=1)
        repo.transition_run(run, **owner, expected_version=2, state="CANCELLED")
    elif fault == "interrupted":
        repo.transition_run(run, **owner, expected_version=1, state="INTERRUPTED")
    elif fault in {"request", "envelope"}:
        with repo._operation(write=True) as conn:
            conn.execute("UPDATE app_runs SET " + fault + "_sha256=? WHERE run_id=?", ("0"*64, run))
    else:
        operation, _ = repo.prepare_share_code_create(run, **owner, selections=SELECTIONS)
        row = repo.share_code_operation(run, operation, **owner)
        with repo._operation(write=True) as conn:
            conn.execute("DELETE FROM app_run_artifacts WHERE artifact_id=?", (row["input_artifact_id"],))
    posts = []
    result = service(context, lambda **_: posts.append(1)).create(SELECTIONS)
    assert result.outcome in {Outcome.LOCAL_PRE_SEND_BLOCKED, Outcome.CREATE_OUTCOME_UNKNOWN}
    assert posts == []


def test_authority_fields_reauthenticated_no_caller_upgrade(context, monkeypatch):
    repo, run, owner, _ = context
    original = repo._verify_run_identity
    real = original
    envelope = repo.run_snapshot(run)["envelope_bytes"]
    envelope = ExecutionEnvelope.from_json_bytes(envelope)
    for field in ("share_code_generation", "wager", "login", "cookies", "wallet", "staking"):
        # Inject at the already-authenticated seam to directly exercise the
        # second-layer positive/negative authority guard, including impossible
        # admitted domain combinations. Real admission remains strict.
        from types import SimpleNamespace
        authority = SimpleNamespace(**{k:getattr(envelope.authority_manifest,k) for k in
                                      ("share_code_generation", "wager", "login", "cookies", "wallet", "staking")})
        setattr(authority, field, False if field == "share_code_generation" else True)
        fake = SimpleNamespace(request_bytes=envelope.request_bytes, requested_operations=envelope.requested_operations,
                               authority_manifest=authority)
        monkeypatch.setattr(repo, "_verify_run_identity", lambda *a, **k: fake)
        with repo._operation() as conn, pytest.raises(ExternalOperationViolation):
            repo._share_authority(conn, run)
    monkeypatch.setattr(repo, "_verify_run_identity", real)
    assert operations(context) == []


def test_concurrent_same_intent_one_post(context):
    calls = []
    def post(**_):
        calls.append(1)
        raise TimeoutError()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service(context, post).create(SELECTIONS), range(2)))
    assert len(calls) == 1
    assert len(operations(context)) == 1


def test_reload_unproven_operation_never_gets(context):
    calls = []
    transport = service(context, get=lambda **_: calls.append(1))
    assert transport.reload("operation-missing").outcome == Outcome.LOCAL_PRE_SEND_BLOCKED
    assert calls == []


@pytest.mark.parametrize("context", [False], indirect=True)
def test_admitted_false_cannot_prepare(context):
    calls = []
    assert service(context, lambda **_: calls.append(1)).create(SELECTIONS).outcome == Outcome.LOCAL_PRE_SEND_BLOCKED
    assert operations(context) == []
    assert calls == []


def test_prepared_is_not_resend_authority(context):
    repo, run, owner, _ = context
    operation, created = repo.prepare_share_code_create(run, **owner, selections=SELECTIONS)
    assert created is True
    posts = []
    assert service(context, lambda **_: posts.append(1)).create(SELECTIONS).outcome == Outcome.LOCAL_PRE_SEND_BLOCKED
    assert operations(context)[0][1] == "PREPARED"
    assert posts == []


def test_known_failed_after_sent_forbidden_without_future_contract(context):
    repo, run, owner, _ = context
    operation, _ = repo.prepare_share_code_create(run, **owner, selections=SELECTIONS)
    repo.transition_external_operation(run, operation, **owner, expected_state="PREPARED", state="SENT")
    artifact = repo.retain_share_code_response(run, operation, **owner, response=response({"bizCode":12345}, 400))
    with pytest.raises(ExternalOperationViolation):
        repo.transition_external_operation(run, operation, **owner, expected_state="SENT", state="FAILED",
                                           response_artifact_id=artifact)
    assert operations(context)[0][1] == "SENT"


def test_low_level_phases_exact_methods_and_no_internal_retry(monkeypatch):
    calls = []
    class Reply:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return create_success().raw
    def http(request, timeout):
        calls.append((request.get_method(), request.full_url, request.data))
        return Reply()
    monkeypatch.setattr(bridge, "_open_once", http)
    bridge.post_create_once(request_bytes=bridge.build_create_request(SELECTIONS))
    bridge.load_share_code_once(code="ABC123")
    assert [row[0] for row in calls] == ["POST", "GET"]
    assert calls[0][1] == bridge.SPORTYBET_ORIGIN + bridge.CREATE_PATH
    assert calls[1][1] == bridge.SPORTYBET_ORIGIN + bridge.LOAD_PREFIX + "ABC123"
    assert calls[1][2] is None


def test_after_sent_commit_exception_never_posts_and_is_unknown(context, monkeypatch):
    repo, _, _, _ = context
    original = repo.transition_external_operation
    def commit_then_raise(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs["state"] == "SENT":
            raise RuntimeError("lost commit acknowledgement")
    monkeypatch.setattr(repo, "transition_external_operation", commit_then_raise)
    calls = []
    assert service(context, lambda **_: calls.append(1)).create(SELECTIONS).outcome == Outcome.CREATE_OUTCOME_UNKNOWN
    assert operations(context)[0][1] == "OUTCOME_UNKNOWN"
    assert calls == []


def test_new_attempt_cannot_replace_unknown_intent(context):
    repo, run, owner, roots = context
    def unknown(**_): raise TimeoutError()
    result = service(context, unknown).create(SELECTIONS)
    row = repo.share_code_operation(run, result.operation_id, **owner)
    repo.finish_attempt(run, owner["attempt_id"], owner["lease_token"], exit_code=1)
    attempt, lease, _ = repo.claim_attempt(run, worker_instance_id="second-synthetic",
                                          process_locator={"kind":"OFFLINE_TEST","label":"fixture"})
    new_owner = {"attempt_id":attempt,"lease_token":lease}
    assert repo.prepare_share_code_create(run, **new_owner, selections=SELECTIONS) == (result.operation_id, False)
    with pytest.raises(ExternalOperationViolation):
        repo.prepare_external_operation(run, **new_owner, operation_kind=SHARE_CREATE_KIND,
                                        intent_sha256=row["intent_sha256"], authority_sha256=row["authority_sha256"],
                                        input_artifact_id=row["input_artifact_id"], idempotency_key="different-key")
    calls = []
    service((repo,run,new_owner,roots), lambda **_: calls.append(1)).create(SELECTIONS)
    assert calls == []
    assert len(operations(context)) == 1


def test_authenticated_terminal_cannot_prepare(development_durable, clock):
    repo, candidate, resources, roots = development_durable
    run, attempt, lease = _running(repo, candidate)
    receipt = _receipt(repo, candidate, run, clock)
    digest = repo.publish_terminal_receipt(run, receipt_bytes=canonical_json_bytes(receipt),
                                          expected_version=1, attempt_id=attempt, lease_token=lease)
    repo.project_terminal_receipt(digest)
    calls = []
    transport = DurableShareCodeTransport(repo, run_id=run, attempt_id=attempt, lease_token=lease,
                                         post_create_once=lambda **_: calls.append(1), load_share_code_once=lambda **_: calls.append(1))
    assert transport.create(SELECTIONS).outcome == Outcome.LOCAL_PRE_SEND_BLOCKED
    assert calls == []
    assert repo.run_snapshot(run)["state"] == "TERMINAL"


def test_product_worker_cannot_fall_back_to_live_wrapper(monkeypatch):
    from runtime.worker_entry import _run_current_shadow, WorkerEntryError
    from types import SimpleNamespace
    with pytest.raises(WorkerEntryError, match="durable transport context"):
        _run_current_shadow(SimpleNamespace(operation="CURRENT_SHADOW_REQUEST"), SimpleNamespace(create_share_code=True))


def test_redirect_response_is_retained_without_implicit_request(monkeypatch):
    from urllib.error import HTTPError
    from io import BytesIO
    calls = []
    def redirect(request, *, timeout):
        calls.append(request.get_method())
        raise HTTPError(request.full_url, 302, "redirect", {"Location":"https://unrelated.invalid/"}, BytesIO(b"ambiguous"))
    monkeypatch.setattr(bridge, "_open_once", redirect)
    evidence = bridge.post_create_once(request_bytes=bridge.build_create_request(SELECTIONS))
    assert evidence == bridge.HttpResponseEvidence(302, b"ambiguous")
    assert calls == ["POST"]
    assert bridge._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://unrelated.invalid/") is None
