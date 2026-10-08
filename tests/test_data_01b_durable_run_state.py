"""Offline D4 storage proofs: no workers, transport, or production admission."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import multiprocessing
import sqlite3
import json
from threading import Barrier
from contextlib import contextmanager

import pytest

from database.run_repository import (
    DurableRunRepository, RunLeaseFenced, RunStateConflict,
    ExternalOperationViolation,
    RunRepositoryError,
    HistoricalReleaseUnavailable, ReceiptProducerUnavailable,
)
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import canonical_json_bytes, RunReceipt, RunRequest
from services.athena_preview_service import AdmissionCandidate, AdmissionReplayIdentity
from runtime.release_identity import verify_development_checkout, verify_installed_release, canonical_release_manifest_bytes
from runtime.resources import ResourceResolver, WritableRoots
from test_data_01a_app_schema import (
    resources, roots, clock, open_repo, record_test_release, make_stored_preview,
    ROOT,
)


@pytest.fixture
def durable(resources, roots, clock):
    app = open_repo(resources, roots)
    record_test_release(app, clock())
    _, item = make_stored_preview(resources, clock)
    envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
    app.persist_preview_bundle(item=item, envelope=envelope, release_id="test-release",
                               profile_id="local-default", now=clock())
    app.close()
    candidate = AdmissionCandidate(
        item.preview_id, item.request_bytes, envelope.request_sha256,
        item.envelope_bytes, envelope.canonical_sha256, "offline-key",
        envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(),
        envelope.expires_at,
    )
    return DurableRunRepository(resources, roots, clock=clock), candidate


@pytest.fixture
def development_durable(tmp_path, clock):
    """Actual verified local Git source, not an invented installed commit."""
    identity = verify_development_checkout(ROOT)
    resources = ResourceResolver.for_development(identity)
    roots = WritableRoots(data_root=tmp_path / "dev-data", cache_root=tmp_path / "dev-cache",
                          state_root=tmp_path / "dev-state")
    roots.ensure_created()
    release_id = "development-checkout:" + identity.head_commit_sha
    app = open_repo(resources, roots, release_id=release_id)
    record_test_release(app, clock())
    _, item = make_stored_preview(resources, clock)
    envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
    app.persist_preview_bundle(item=item, envelope=envelope, release_id=release_id,
                               profile_id="local-default", now=clock())
    app.close()
    candidate = AdmissionCandidate(
        item.preview_id, item.request_bytes, envelope.request_sha256, item.envelope_bytes,
        envelope.canonical_sha256, "development-key", envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(), envelope.expires_at)
    return DurableRunRepository(resources, roots, clock=clock), candidate, resources, roots


def _receipt(repo, candidate, run_id, clock, *, producer=None):
    request = RunRequest.from_json_bytes(candidate.request_bytes)
    envelope = ExecutionEnvelope.from_json_bytes(candidate.execution_envelope_bytes)
    if producer is None:
        assert envelope.source_identity.kind == "GIT_COMMIT"
        producer = envelope.source_identity.value
    return RunReceipt(
        status="OFFLINE_TEST_COMPLETE", observed_at=clock(), exact_commit_sha=producer,
        request=request, stages=(), counts={"selected_leg_count": 0}, selected_legs=(),
        shortfall=request.target_legs, share_code_result=None,
        authority_manifest=envelope.authority_manifest,
        evidence={"run_id": run_id, "execution_envelope_sha256": envelope.canonical_sha256,
                  "release_id": repo.run_snapshot(run_id)["release_id"]})


def _running(repo, candidate):
    run_id = repo.admit(candidate).run_id
    attempt, lease, number = repo.claim_attempt(
        run_id, worker_instance_id="offline-worker",
        process_locator={"kind": "OFFLINE_TEST", "label": "fixture"},
    )
    assert number == 1
    assert repo.transition_run(run_id, expected_version=0, state="RUNNING",
                               attempt_id=attempt, lease_token=lease) == 1
    return run_id, attempt, lease


def test_admission_exact_replay_conflicts_and_commit_expiry(durable, clock):
    repo, candidate = durable
    identity = AdmissionReplayIdentity(candidate.idempotency_key, candidate.preview_id,
                                       candidate.execution_envelope_sha256)
    assert repo.lookup(identity).disposition == "not_found"
    admitted = repo.admit(candidate)
    assert admitted.disposition == "admitted"
    clock.advance(timedelta(days=1))
    assert repo.admit(candidate).run_id == admitted.run_id
    assert repo.lookup(identity).disposition == "idempotent_replay"
    assert repo.admit(replace(candidate, execution_envelope_sha256="0" * 64)).disposition == "idempotency_conflict"
    assert repo.admit(replace(candidate, idempotency_key="another-key")).disposition == "preview_consumed_conflict"


def test_atomic_admission_race_independent_connections(durable, resources, roots, clock):
    repo, candidate = durable
    second = DurableRunRepository(resources, roots, clock=clock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda store: store.admit(candidate), (repo, second)))
    assert sorted(result.disposition for result in results) == ["admitted", "idempotent_replay"]
    assert len({result.run_id for result in results}) == 1


def test_expired_new_commit_creates_no_run(durable, clock):
    repo, candidate = durable
    clock.value = candidate.preview_expires_at
    assert repo.admit(candidate).disposition == "preview_expired"
    assert repo.lookup(AdmissionReplayIdentity(candidate.idempotency_key, candidate.preview_id,
                                              candidate.execution_envelope_sha256)).disposition == "not_found"


def test_attempt_lease_fencing_monotonic_claim_and_safe_locator(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    with pytest.raises(RunLeaseFenced):
        repo.heartbeat(run_id, attempt, "stale")
    with pytest.raises(RunLeaseFenced):
        repo.claim_attempt(run_id, worker_instance_id="other",
                           process_locator={"kind": "OFFLINE_TEST", "label": "fixture"})
    repo.finish_attempt(run_id, attempt, lease, exit_code=0)
    _, _, number = repo.claim_attempt(run_id, worker_instance_id="other",
                                      process_locator={"kind": "OFFLINE_TEST", "label": "fixture"})
    assert number == 2
    with pytest.raises(RunLeaseFenced):
        repo.heartbeat(run_id, attempt, lease)


def test_events_genesis_cas_and_idempotent_cancellation(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    with pytest.raises(RunStateConflict):
        repo.transition_run(run_id, expected_version=0, state="INTERRUPTED",
                            attempt_id=attempt, lease_token=lease)
    assert repo.request_cancel(run_id, expected_version=1) == 2
    assert repo.request_cancel(run_id, expected_version=1) == 2
    events = repo.read_events(run_id)
    assert [row[:3] for row in events] == [
        (1, 0, "RUN_QUEUED"), (2, 1, "RUN_RUNNING"), (3, 2, "RUN_CANCEL_REQUESTED")]


def test_external_uncertainty_is_terminal_and_production_disabled(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    with pytest.raises(ExternalOperationViolation):
        repo.prepare_external_operation(run_id, attempt_id=attempt, lease_token=lease,
                                        operation_kind="PROVIDER", intent_sha256="0" * 64,
                                        authority_sha256="1" * 64)
    operation = repo.prepare_external_operation(run_id, attempt_id=attempt, lease_token=lease,
                                                operation_kind="TESTING_SYNTHETIC",
                                                intent_sha256="0" * 64, authority_sha256="1" * 64)
    repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                       expected_state="PREPARED", state="SENT")
    repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                       expected_state="SENT", state="OUTCOME_UNKNOWN")
    with pytest.raises(ExternalOperationViolation):
        repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                           expected_state="OUTCOME_UNKNOWN", state="SENT")


def test_receipt_first_crash_reconcile_once(development_durable, clock):
    repo, candidate, resources, roots = development_durable
    run_id, attempt, lease = _running(repo, candidate)
    receipt = _receipt(repo, candidate, run_id, clock)
    digest = repo.publish_terminal_receipt(run_id, expected_version=1,
                                           receipt_bytes=canonical_json_bytes(receipt),
                                           attempt_id=attempt, lease_token=lease)
    assert repo.run_snapshot(run_id)["state"] == "RUNNING"
    reopened = DurableRunRepository(resources, roots, clock=clock)
    assert reopened.reconcile_receipt_projection(digest) is True
    assert reopened.reconcile_receipt_projection(digest) is False
    assert reopened.run_snapshot(run_id)["state"] == "TERMINAL"


def _admission_process(resources, roots, instant, candidate, barrier, queue):
    try:
        repository = DurableRunRepository(resources, roots, clock=lambda: instant)
        barrier.wait(timeout=30)
        result = repository.admit(candidate)
        queue.put((result.disposition, result.run_id))
    except BaseException as exc:
        queue.put(("ERROR", repr(exc)))


def test_two_process_atomic_admission(durable, resources, roots, clock):
    _, candidate = durable
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_admission_process,
                                 args=(resources, roots, clock(), candidate, barrier, queue))
                 for _ in range(2)]
    try:
        for process in processes:
            process.start()
        results = [queue.get(timeout=60) for _ in processes]
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        assert sorted(row[0] for row in results) == ["admitted", "idempotent_replay"]
        assert len({row[1] for row in results}) == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
        queue.close()


def test_v1_upgrade_and_noop_restart_evidence(resources, roots, monkeypatch):
    import database.app_migrations as migrations
    all_migrations = migrations.APP_MIGRATIONS
    with monkeypatch.context() as scoped:
        scoped.setattr(migrations, "APP_MIGRATIONS", all_migrations[:1])
        migrations.apply_app_migrations(resources, roots, release_id="test-release")
    migrations.apply_app_migrations(resources, roots, release_id="test-release")
    with migrations.connect_app_store(migrations.app_store_path(roots), readonly=True) as conn:
        assert migrations.current_schema_version(conn) == 2
        assert len(conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'app_%'").fetchall()) == 14
    before = {path.relative_to(roots.data_root): path.read_bytes()
              for path in (roots.data_root / "migration-evidence").rglob("*") if path.is_file()}
    migrations.apply_app_migrations(resources, roots, release_id="test-release")
    after = {path.relative_to(roots.data_root): path.read_bytes()
             for path in (roots.data_root / "migration-evidence").rglob("*") if path.is_file()}
    assert before == after


def test_concurrent_events_have_strict_per_run_sequence(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        sequences = list(pool.map(lambda index: repo.append_event(
            run_id, attempt_id=attempt, lease_token=lease,
            event_type="OFFLINE_OBSERVATION", payload={"index": index}), range(12)))
    assert sorted(sequences) == list(range(3, 15))
    assert [row[0] for row in repo.read_events(run_id)] == list(range(1, 15))


@pytest.mark.parametrize("locator", [
    {"kind": "OFFLINE_TEST", "label": "C:/secret"},
    {"kind": "OFFLINE_TEST", "label": "fixture", "command": "execute"},
    {"kind": "SHELL", "label": "fixture"},
])
def test_unsafe_process_locator_rejected(durable, locator):
    repo, candidate = durable
    run_id = repo.admit(candidate).run_id
    with pytest.raises(RunRepositoryError):
        repo.claim_attempt(run_id, worker_instance_id="offline", process_locator=locator)


def test_candidate_authority_identity_tamper_rejected(durable):
    repo, candidate = durable
    with pytest.raises(RunRepositoryError):
        repo.admit(replace(candidate, authority_manifest_sha256="0" * 64))


def test_cross_run_attempt_and_terminal_without_receipt_rejected(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    with pytest.raises(RunLeaseFenced):
        repo.heartbeat("other-run", attempt, lease)
    with pytest.raises(RunStateConflict):
        repo.transition_run(run_id, expected_version=1, state="TERMINAL",
                            attempt_id=attempt, lease_token=lease)


def test_run_artifact_bytes_and_restrict_retention(durable, resources, roots, clock):
    from database.app_migration_evidence import publish
    from database.app_migrations import connect_app_store, app_store_path
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    raw, locator = b"offline input evidence\n", "offline-fixtures/input.txt"
    publish(roots.data_root, locator, raw)
    app = open_repo(resources, roots)
    app.record_artifact(artifact_id="offline-input", byte_sha256=hashlib.sha256(raw).hexdigest(),
                        canonical_sha256=None, byte_count=len(raw), media_type="text/plain",
                        artifact_kind="EXTERNAL_INPUT", logical_path=locator, evidence_class="RETAINED",
                        verification_policy_id=None, verified_at=clock(), created_at=clock())
    app.close()
    repo.link_run_artifact(run_id, "offline-input", role="EXTERNAL_INPUT",
                           attempt_id=attempt, lease_token=lease)
    with connect_app_store(app_store_path(roots), synchronous="FULL") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM app_artifacts WHERE artifact_id='offline-input'")
    (roots.data_root / locator).write_bytes(b"tampered")
    with pytest.raises(RunRepositoryError):
        repo.prepare_external_operation(run_id, attempt_id=attempt, lease_token=lease,
                                        operation_kind="TESTING_SYNTHETIC", intent_sha256="0" * 64,
                                        authority_sha256="1" * 64, input_artifact_id="offline-input")


def test_sent_operation_recovery_fences_attempt(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    operation = repo.prepare_external_operation(run_id, attempt_id=attempt, lease_token=lease,
                                                operation_kind="TESTING_SYNTHETIC",
                                                intent_sha256="0" * 64, authority_sha256="1" * 64)
    repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                       expected_state="PREPARED", state="SENT")
    repo.recover_attempt(run_id, attempt, lease)
    assert repo.run_snapshot(run_id)["state"] == "INTERRUPTED"
    with pytest.raises(RunLeaseFenced):
        repo.heartbeat(run_id, attempt, lease)


def test_source_receipt_and_frozen_migration_identity():
    from scripts import audit_data_01b_durable_run_state as audit
    assert (audit.ROOT / audit.RECEIPT).read_bytes() == audit.canonical(audit.build_receipt())
    assert hashlib.sha256(audit.tracked_bytes("database/migrations/0001_app_control_core.sql")).hexdigest() == audit.FROZEN_MIGRATION_SHA


def test_historical_successor_needs_no_d3_ancestor_git_blob(monkeypatch):
    from scripts import audit_data_01a_app_schema_core as d3
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    original = boundary.git

    def bounded(*args, **kwargs):
        if args and args[0] == "show" and any("7e609e3d2006d2a72d9bf347cb917c0585538322:" in str(arg) for arg in args):
            raise AssertionError("D3 ancestor blob lookup forbidden in shallow fixture")
        return original(*args, **kwargs)

    monkeypatch.setattr(boundary, "git", bounded)
    assert d3.authenticate()["a2_inventory"]["path"].endswith("v68.json")


def _operation(repo, run_id, attempt, lease, *, sent=True):
    operation = repo.prepare_external_operation(
        run_id, attempt_id=attempt, lease_token=lease, operation_kind="TESTING_SYNTHETIC",
        intent_sha256="0" * 64, authority_sha256="1" * 64)
    if sent:
        repo.transition_external_operation(run_id, operation, attempt_id=attempt,
                                           lease_token=lease, expected_state="PREPARED", state="SENT")
    return operation


def _response(repo, resources, roots, clock, run_id, attempt, lease, *, role="EXTERNAL_RESPONSE"):
    from database.app_migration_evidence import publish
    artifact_id = "response-" + run_id
    raw = ("OFFLINE_ONLY " + artifact_id).encode()
    locator = "offline-responses/" + artifact_id + ".txt"
    publish(roots.data_root, locator, raw)
    app = open_repo(resources, roots)
    app.record_artifact(artifact_id=artifact_id, byte_sha256=hashlib.sha256(raw).hexdigest(),
                        canonical_sha256=None, byte_count=len(raw), media_type="text/plain",
                        artifact_kind=role, logical_path=locator, evidence_class="RETAINED",
                        verification_policy_id=None, verified_at=clock(), created_at=clock())
    app.close()
    repo.link_run_artifact(run_id, artifact_id, role=role, attempt_id=attempt, lease_token=lease)
    return artifact_id, roots.data_root / locator


def _operation_row(repo, operation):
    with repo._operation() as conn:
        return conn.execute("SELECT state,sent_at,completed_at,response_artifact_id FROM app_external_operations WHERE operation_id=?", (operation,)).fetchone()


def test_confirmed_requires_retained_response_without_mutation(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    operation = _operation(repo, run_id, attempt, lease)
    before = _operation_row(repo, operation)
    with pytest.raises(ExternalOperationViolation, match="proven response"):
        repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                           expected_state="SENT", state="CONFIRMED")
    assert _operation_row(repo, operation) == before
    repo.recover_attempt(run_id, attempt, lease)
    assert _operation_row(repo, operation)[0] == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize("fault", ["wrong-role", "tampered", "missing", "cross-run"])
def test_confirmed_rejects_unproven_response(durable, resources, roots, clock, fault):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    operation = _operation(repo, run_id, attempt, lease)
    artifact, path = _response(repo, resources, roots, clock, run_id, attempt, lease,
                               role="EXTERNAL_INPUT" if fault == "wrong-role" else "EXTERNAL_RESPONSE")
    if fault == "tampered":
        path.write_bytes(b"corrupt")
    elif fault == "missing":
        path.unlink()
    elif fault == "cross-run":
        # Another durable run owns this role; no fabricated artifact bytes.
        other = "other-" + run_id
        _, item = make_stored_preview(resources, clock)
        envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
        app = open_repo(resources, roots)
        app.persist_preview_bundle(item=item, envelope=envelope, release_id="test-release",
                                   profile_id="local-default", now=clock())
        app.close()
        other_candidate = replace(candidate, preview_id=item.preview_id,
                                  request_bytes=item.request_bytes, request_sha256=envelope.request_sha256,
                                  execution_envelope_bytes=item.envelope_bytes,
                                  execution_envelope_sha256=envelope.canonical_sha256,
                                  idempotency_key=other)
        other = repo.admit(other_candidate).run_id
        with repo._operation(write=True) as conn:
            conn.execute("UPDATE app_run_artifacts SET run_id=? WHERE artifact_id=?", (other, artifact))
    before = _operation_row(repo, operation)
    with pytest.raises(RunRepositoryError):
        repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                           expected_state="SENT", state="CONFIRMED", response_artifact_id=artifact)
    assert _operation_row(repo, operation) == before


def test_verified_response_confirms_once_after_cancellation(durable, resources, roots, clock):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    operation = _operation(repo, run_id, attempt, lease)
    artifact, _ = _response(repo, resources, roots, clock, run_id, attempt, lease)
    repo.request_cancel(run_id, expected_version=1)
    repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                       expected_state="SENT", state="CONFIRMED", response_artifact_id=artifact)
    assert _operation_row(repo, operation)[0] == "CONFIRMED"
    with pytest.raises(ExternalOperationViolation):
        repo.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                           expected_state="SENT", state="CONFIRMED", response_artifact_id=artifact)


def test_cancel_then_send_rejected_and_sent_then_cancel_recovers_unknown(durable):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    prepared = _operation(repo, run_id, attempt, lease, sent=False)
    sent = _operation(repo, run_id, attempt, lease)
    repo.request_cancel(run_id, expected_version=1)
    with pytest.raises(ExternalOperationViolation, match="cancellation"):
        repo.transition_external_operation(run_id, prepared, attempt_id=attempt, lease_token=lease,
                                           expected_state="PREPARED", state="SENT")
    assert _operation_row(repo, prepared)[0] == "PREPARED"
    repo.recover_attempt(run_id, attempt, lease)
    assert _operation_row(repo, sent)[0] == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize("iteration", range(3))
def test_cancel_send_race_independent_connections_serializes_winner(durable, resources, roots, clock, iteration):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    operation = _operation(repo, run_id, attempt, lease, sent=False)
    order, barrier = [], Barrier(2)

    class OrderedRepository(DurableRunRepository):
        @contextmanager
        def _operation(self, *, write=False):
            with super()._operation(write=write) as conn:
                if write:
                    order.append(self.label)  # Inside the actual SQLite writer lock.
                yield conn

    cancel = OrderedRepository(resources, roots, clock=clock)
    send = OrderedRepository(resources, roots, clock=clock)
    cancel.label, send.label = "cancel", "send"

    def cancel_call():
        barrier.wait(timeout=30)
        return cancel.request_cancel(run_id, expected_version=1)

    def send_call():
        barrier.wait(timeout=30)
        try:
            send.transition_external_operation(run_id, operation, attempt_id=attempt, lease_token=lease,
                                               expected_state="PREPARED", state="SENT")
            return True
        except ExternalOperationViolation:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future, send_future = pool.submit(cancel_call), pool.submit(send_call)
        assert cancel_future.result(timeout=60) == 2
        sent = send_future.result(timeout=60)
    assert order in (["cancel", "send"], ["send", "cancel"])
    assert sent == (order[0] == "send")
    row = _operation_row(repo, operation)
    assert row[0] == ("SENT" if sent else "PREPARED")
    assert (row[1] is not None) == sent
    assert repo.run_snapshot(run_id)["state"] == "CANCEL_REQUESTED"


def _release_b(resources, roots, tmp_path, clock):
    manifest = json.loads(resources.identity.manifest_bytes)
    manifest.update(release_id="test-release-b", build_id="test-build-b")
    root = tmp_path / "release-b"
    root.mkdir()
    for record in manifest["resources"]:
        path = root / record["payload_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resources.read_bytes(record["logical_path"], expected_role=record["role"]))
    raw = canonical_release_manifest_bytes(manifest)
    (root / "release-manifest.json").write_bytes(raw)
    identity = verify_installed_release(root, hashlib.sha256(raw).hexdigest())
    b = ResourceResolver.for_installed(identity)
    b_roots = replace(roots, installed_release_root=root)
    app = open_repo(b, b_roots, release_id="test-release-b")
    record_test_release(app, clock())
    app.close()
    return DurableRunRepository(b, b_roots, clock=clock)


def test_historical_release_a_read_replay_under_b_but_no_current_mutation(durable, resources, roots, tmp_path, clock):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    snapshot, events = repo.run_snapshot(run_id), repo.read_events(run_id)
    b = _release_b(resources, roots, tmp_path, clock)
    clock.advance(timedelta(days=1))
    assert b.run_snapshot(run_id) == snapshot
    assert b.read_events(run_id) == events
    assert b.admit(candidate).disposition == "idempotent_replay"
    assert b.lookup(AdmissionReplayIdentity(candidate.idempotency_key, candidate.preview_id,
                                           candidate.execution_envelope_sha256)).run_id == run_id
    with pytest.raises(RunRepositoryError, match="current verified source"):
        b.heartbeat(run_id, attempt, lease)
    with pytest.raises(RunRepositoryError, match="current verified source"):
        b.claim_attempt(run_id, worker_instance_id="new", process_locator={"kind": "OFFLINE_TEST", "label": "new"})
    assert b.run_snapshot(run_id) == snapshot


@pytest.mark.parametrize("column,value", [("manifest_byte_sha256", "0" * 64),
                                          ("manifest_bytes", b"corrupted"),
                                          ("build_id", "wrong-build")])
def test_corrupt_original_release_provenance_rejects_history(durable, resources, roots, tmp_path, clock, column, value):
    repo, candidate = durable
    run_id = repo.admit(candidate).run_id
    b = _release_b(resources, roots, tmp_path, clock)
    with repo._operation(write=True) as conn:
        conn.execute("UPDATE app_release_manifests SET " + column + "=? WHERE release_id='test-release'", (value,))
    for read in (lambda: b.run_snapshot(run_id), lambda: b.read_events(run_id), lambda: b.admit(candidate)):
        with pytest.raises(HistoricalReleaseUnavailable):
            read()


@pytest.mark.parametrize("producer", ["0" * 40, "f" * 40])
def test_unverified_receipt_producer_rejected_before_publication(development_durable, clock, producer):
    repo, candidate, _, roots = development_durable
    run_id, attempt, lease = _running(repo, candidate)
    receipt = _receipt(repo, candidate, run_id, clock, producer=producer)
    with pytest.raises(ReceiptProducerUnavailable, match="producer commit"):
        repo.publish_terminal_receipt(run_id, receipt_bytes=canonical_json_bytes(receipt),
                                       expected_version=1, attempt_id=attempt, lease_token=lease)
    assert not (roots.data_root / "run-receipts").exists()
    assert repo.run_snapshot(run_id)["state"] == "RUNNING"


def test_installed_receipt_has_no_fabricated_git_producer(durable, roots, clock):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    receipt = _receipt(repo, candidate, run_id, clock, producer="0" * 40)
    with pytest.raises(ReceiptProducerUnavailable, match="no independently verified producer"):
        repo.publish_terminal_receipt(run_id, receipt_bytes=canonical_json_bytes(receipt),
                                       expected_version=1, attempt_id=attempt, lease_token=lease)
    assert not (roots.data_root / "run-receipts").exists()


@pytest.mark.parametrize("binding", ["run_id", "release_id", "execution_envelope_sha256"])
def test_receipt_cross_identity_rejected(development_durable, clock, binding):
    repo, candidate, _, _ = development_durable
    run_id, attempt, lease = _running(repo, candidate)
    receipt = _receipt(repo, candidate, run_id, clock)
    receipt = replace(receipt, evidence={**receipt.evidence, binding: "wrong"})
    with pytest.raises(ReceiptProducerUnavailable, match="binding mismatch"):
        repo.publish_terminal_receipt(run_id, receipt_bytes=canonical_json_bytes(receipt),
                                       expected_version=1, attempt_id=attempt, lease_token=lease)


def test_receipt_projection_reauthenticates_producer_and_tamper(development_durable, clock):
    from database.app_migration_evidence import publish
    repo, candidate, _, roots = development_durable
    run_id, attempt, lease = _running(repo, candidate)
    receipt = _receipt(repo, candidate, run_id, clock)
    digest = repo.publish_terminal_receipt(run_id, receipt_bytes=canonical_json_bytes(receipt),
                                           expected_version=1, attempt_id=attempt, lease_token=lease)
    original = roots.data_root / "run-receipts" / (digest + ".json")
    value = json.loads(original.read_bytes())
    value["receipt"]["exact_commit_sha"] = "0" * 40
    forged = canonical_json_bytes(value)
    forged_sha = hashlib.sha256(forged).hexdigest()
    publish(roots.data_root, "run-receipts/" + forged_sha + ".json", forged)
    with pytest.raises(ReceiptProducerUnavailable):
        repo.reconcile_receipt_projection(forged_sha)
    assert repo.run_snapshot(run_id)["state"] == "RUNNING"
    original.write_bytes(b"tampered")
    with pytest.raises(RunRepositoryError, match="digest mismatch"):
        repo.reconcile_receipt_projection(digest)


def test_genuinely_blocked_snapshot_cannot_admit(resources, roots, clock):
    from services.athena_preview_service import AthenaPreviewAdmissionService
    from domain.execution_envelope import ExecutionPreview
    app = open_repo(resources, roots)
    record_test_release(app, clock())
    service = AthenaPreviewAdmissionService(resources, clock=clock)
    result = service.preview(dates=["2030-01-01"], target_legs=3, target_total_odds=None,
                             bookie="sportybet", profile="main", acquire_sources=True, create_share_code=False)
    item = service.preview_store.get(result["preview_id"], now=clock())
    assert ExecutionPreview.from_json_bytes(item.preview_bytes).blockers
    envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
    app.persist_preview_bundle(item=item, envelope=envelope, release_id="test-release",
                               profile_id="local-default", now=clock())
    app.close()
    candidate = AdmissionCandidate(item.preview_id, item.request_bytes, envelope.request_sha256,
        item.envelope_bytes, envelope.canonical_sha256, "blocked", envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(), envelope.expires_at)
    repo = DurableRunRepository(resources, roots, clock=clock)
    with pytest.raises(RunRepositoryError, match="blocked"):
        repo.admit(candidate)
    with repo._operation() as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_run_events").fetchone()[0] == 0


@pytest.mark.parametrize("fault", ["bytes", "digest", "expiry", "profile", "resealed"])
def test_tampered_capability_report_denies_admission_without_genesis(durable, fault):
    repo, candidate = durable
    with repo._operation(write=True) as conn:
        if fault == "resealed":
            report = json.loads(conn.execute("SELECT report_bytes FROM app_capability_snapshots").fetchone()[0])
            report["request_sha256"] = "0" * 64
            raw = canonical_json_bytes(report)
            conn.execute("UPDATE app_capability_snapshots SET report_bytes=?,report_sha256=?",
                         (raw, hashlib.sha256(raw).hexdigest()))
        else:
            column, value = {"bytes": ("report_bytes", b"tampered"), "digest": ("report_sha256", "0" * 64),
                             "expiry": ("expires_at", "2000-01-01T00:00:00.000000Z"), "profile": ("profile", "SHADOW")}[fault]
            conn.execute("UPDATE app_capability_snapshots SET " + column + "=?", (value,))
    with pytest.raises(RunRepositoryError):
        repo.admit(candidate)
    with repo._operation() as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_run_events").fetchone()[0] == 0


def test_receipt_cross_authority_rejected(development_durable, clock):
    repo, candidate, _, _ = development_durable
    run_id, attempt, lease = _running(repo, candidate)
    receipt = _receipt(repo, candidate, run_id, clock)
    receipt = replace(receipt, authority_manifest=replace(receipt.authority_manifest,
                                                         provider_acquisition=not receipt.authority_manifest.provider_acquisition))
    with pytest.raises(RunRepositoryError, match="authority mismatch"):
        repo.publish_terminal_receipt(run_id, receipt_bytes=canonical_json_bytes(receipt),
                                       expected_version=1, attempt_id=attempt, lease_token=lease)


def test_current_authority_change_denies_direct_admission(durable, monkeypatch):
    from services.athena_run_service import AthenaRunService
    repo, candidate = durable
    envelope = ExecutionEnvelope.from_json_bytes(candidate.execution_envelope_bytes)
    changed = replace(envelope.authority_manifest, provider_acquisition=not envelope.authority_manifest.provider_acquisition)
    monkeypatch.setattr(AthenaRunService, "authority_manifest_for", staticmethod(lambda _: changed))
    with pytest.raises(RunRepositoryError, match="current authority"):
        repo.admit(candidate)
    with repo._operation() as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_run_events").fetchone()[0] == 0
