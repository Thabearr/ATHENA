"""Offline D4 storage proofs: no workers, transport, or production admission."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import multiprocessing
import sqlite3

import pytest

from database.run_repository import (
    DurableRunRepository, RunLeaseFenced, RunStateConflict,
    ExternalOperationViolation,
    RunRepositoryError,
)
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import canonical_json_bytes, RunReceipt, RunRequest
from services.athena_preview_service import AdmissionCandidate, AdmissionReplayIdentity
from test_data_01a_app_schema import (
    resources, roots, clock, open_repo, record_test_release, make_stored_preview,
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


def test_receipt_first_crash_reconcile_once(durable, resources, roots, clock):
    repo, candidate = durable
    run_id, attempt, lease = _running(repo, candidate)
    request = RunRequest.from_json_bytes(candidate.request_bytes)
    envelope = ExecutionEnvelope.from_json_bytes(candidate.execution_envelope_bytes)
    receipt = RunReceipt(
        status="OFFLINE_TEST_COMPLETE", observed_at=clock(), exact_commit_sha="0" * 40,
        request=request, stages=(), counts={"selected_leg_count": 0}, selected_legs=(),
        shortfall=request.target_legs, share_code_result=None,
        authority_manifest=envelope.authority_manifest,
    )
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
