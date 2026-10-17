"""Focused RUN-01B lifecycle checks using synthetic local workers only."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import pytest

from database.run_repository import DurableRunRepository, RunStateConflict
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import RunRequest, canonical_json_bytes
from runtime import worker_launcher
from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    verify_development_checkout,
)
from runtime.resources import ResourceResolver, WritableRoots
from runtime.worker_launcher import (
    InstalledWorkerExecutable,
    WorkerCommand,
    WorkerLaunchError,
    WorkerLauncher,
)
from services.athena_capability_service import AthenaCapabilityService
from services.athena_job_service import AthenaJobService
from services.athena_preview_service import AthenaPreviewAdmissionService
from services.app_preview_store import DurablePreviewStore
from services.worker_coordinator import WorkerCoordinator
from test_data_01a_app_schema import (
    ROOT,
    clock,
    make_stored_preview,
    open_repo,
    record_test_release,
    resources,
    roots,
)

_PREVIEW_DATE = "2030-01-01"
_COUNT_NAMES = (
    "reviewed_fixture_count", "reconciled_fixture_count", "provider_event_count",
    "priced_fixture_count", "router_selected_count", "router_no_bet_count",
)


def _use_synthetic_process_control(monkeypatch):
    from services import worker_coordinator
    monkeypatch.setattr(worker_coordinator, "WorkerProcessControl", _SyntheticProcessControl)


def _terminal_case(tmp_path, clock, monkeypatch, *, portfolio=True):
    """Admit and hand off a real coordinator; only the child is synthetic."""
    from services.athena_preview_service import AdmissionCandidate
    from runtime.worker_launcher import WorkerProcessHandle
    from test_current_shadow_run_contract_adapter import _receipt, _request_policy, _stage, _progress
    from domain.current_shadow_all_market_portfolio import _sha

    identity, roots, repository, item, envelope = _development_shadow_run(
        tmp_path, clock, acquire_sources=True,
    )
    candidate = AdmissionCandidate(
        item.preview_id, item.request_bytes, envelope.request_sha256,
        item.envelope_bytes, envelope.canonical_sha256, "terminal-run",
        envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(),
        envelope.expires_at,
    )
    run_id = repository.admit(candidate).run_id
    request = RunRequest.from_json_bytes(item.request_bytes)
    directory = roots.data_root / "runs" / run_id / request.canonical_sha256
    output = directory / "current-shadow"
    output.mkdir(parents=True)
    command = WorkerCommand(
        operation="CURRENT_SHADOW_REQUEST", mode="research_shadow",
        run_directory=directory, request_artifact_id=request.canonical_sha256,
        envelope_artifact_id=None, release_identity_kind=identity.identity_kind,
        release_identity_id=identity.head_commit_sha,
    )
    captured, launches = [], []
    class DeferredThread:
        def __init__(self, *, target, kwargs, **unused):
            captured.append((target, kwargs))
        def start(self):
            pass
    def launch(self, built):
        launches.append(built)
        return WorkerProcessHandle(_SyntheticChild(9321, 0))
    monkeypatch.setattr(WorkerLauncher, "launch", launch)
    _use_synthetic_process_control(monkeypatch)
    coordinator = WorkerCoordinator(
        repository, WorkerLauncher.for_development(identity), roots,
        thread_factory=DeferredThread, sleeper=lambda _: None,
    )
    assert coordinator.handoff(
        run_id, worker_instance_id="terminal-test", process_label="offline-probe",
        command_factory=lambda *_: command,
    )
    policy = _request_policy(fixture_dates=["20300101"], create_share_code=False)
    inner = _receipt(target=3, selected=1 if portfolio else 0, verified=False,
                     create_share_code=False, include_portfolio=portfolio,
                     status=None if portfolio else "RESEARCH_NO_CODE_NO_BET")
    inner["exact_commit_sha"] = identity.head_commit_sha
    inner["observed_at"] = "2030-01-01T23:00:00.000002Z"
    inner["source_summary"] = {
        "wager_placed": False, "current_fotmob": {"sha256": "a" * 64},
        "complete_current_history_sha256": "b" * 64,
        "runtime_progress_diagnostics": {"router_checkpoint_sha256": "c" * 64},
    }
    if portfolio:
        inner["portfolio_sha256"] = _sha(inner["portfolio"])
    stage, progress = _stage("COMPLETE"), _progress("PORTFOLIO")
    for value in (stage, progress):
        value.update(exact_commit_sha=identity.head_commit_sha, requested_target_size=3)
    stage["observed_at"] = "2030-01-01T23:00:00.000001Z"
    progress["observed_at"] = "2030-01-01T23:00:00.000000Z"
    progress["source_summary"] = inner["source_summary"]
    for filename, value in (
        ("current-shadow-request-policy.json", policy),
        ("current-shadow-all-market-stage.json", stage),
        ("current-shadow-all-market-progress.json", progress),
        ("current-shadow-all-market-run-receipt.json", inner),
    ):
        (output / filename).write_bytes(canonical_json_bytes(value))
    return coordinator, repository, run_id, envelope, captured[0], launches, command, inner


def test_valid_no_delivery_shadow_reaches_terminal_with_admitted_authority(tmp_path, clock, monkeypatch):
    from domain.run_contracts import RunReceipt
    from services.athena_job_service import DurableRunReadAdapter
    coordinator, repository, run_id, envelope, (monitor, kwargs), launches, command, inner = _terminal_case(
        tmp_path, clock, monkeypatch,
    )
    before = DurableRunReadAdapter(repository).get_run_snapshot(run_id)
    assert before.selected_leg_count is None and before.shortfall is None and before.business_result is None
    receipt, _, _ = coordinator._build_shadow_receipt(
        run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"], envelope=envelope,
        snapshot=kwargs["snapshot"], command=command,
    )
    coordinator._observe_available_checkpoints(**{k: kwargs[k] for k in (
        "run_id", "attempt_id", "lease_token", "request", "envelope", "command")})
    args = {k: kwargs[k] for k in ("run_id", "attempt_id", "lease_token")}
    assert coordinator._observe_terminal_receipt(**args, receipt=receipt)
    count = len(repository.read_events(run_id))
    assert coordinator._observe_terminal_receipt(**args, receipt=receipt) is False
    assert len(repository.read_events(run_id)) == count
    monitor(**kwargs)
    assert repository.run_snapshot(run_id)["state"] == "TERMINAL"
    assert [e[2] for e in repository.read_events(run_id)].count("RUN_TERMINAL") == 1
    stored = RunReceipt.from_json_bytes(repository.read_receipt_bytes(run_id))
    assert stored.authority_manifest == envelope.authority_manifest
    assert dict(stored.evidence["legacy_current_shadow"]["receipt"]["authority"]) == inner["authority"]
    assert stored.request.canonical_sha256 == envelope.request_sha256
    assert stored.exact_commit_sha == envelope.source_identity.value
    assert stored.evidence["run_id"] == run_id
    assert stored.evidence["execution_envelope_sha256"] == envelope.canonical_sha256
    assert stored.evidence["release_id"] == kwargs["snapshot"]["release_id"]
    assert stored.share_code_result is None and stored.wager_placed is False
    proven = repository.latest_worker_progress(run_id)
    assert proven["stage"] == "COMPLETE"
    assert proven["identity_refs"]["portfolio_sha256"] == inner["portfolio_sha256"]
    assert all(proven["identity_refs"][k] is not None for k in (
        "source_identity_sha256", "model_or_history_sha256", "router_diagnostics_sha256"))
    snapshot = DurableRunReadAdapter(repository).get_run_snapshot(run_id)
    assert snapshot.selected_leg_count == 1 and snapshot.shortfall == 2
    assert snapshot.receipt_state == "VERIFIED" and snapshot.business_result == stored.status
    assert snapshot.delivery_state is None and snapshot.execution_state is None
    assert "shareCode" not in json.dumps(snapshot.to_dict())
    assert len(launches) == 1
    # Finished attempts remain fenced; no repair or replay can launch a child.
    assert coordinator.repair_published_projection(repository.run_snapshot(run_id)["receipt_artifact_id"][8:]) is False
    assert len(launches) == 1


@pytest.mark.parametrize("mutation", ["provider", "delivery", "sensitive", "unknown_authority", "commit", "target", "cross_run", "portfolio_bytes", "portfolio_hash"])
def test_terminal_authority_and_portfolio_mutations_reject(tmp_path, clock, monkeypatch, mutation):
    coordinator, repository, run_id, envelope, (monitor, kwargs), launches, command, inner = _terminal_case(
        tmp_path, clock, monkeypatch,
    )
    if mutation == "provider": inner["authority"]["research_shadow_source_acquisition"] = False
    elif mutation == "delivery": inner["authority"]["research_anonymous_share_code_generation"] = True
    elif mutation == "sensitive": inner["authority"]["wallet"] = True
    elif mutation == "unknown_authority": inner["authority"]["future_research_authority"] = True
    elif mutation == "commit": inner["exact_commit_sha"] = "f" * 40
    elif mutation == "target": inner["requested_target_size"] = 4
    elif mutation == "cross_run": inner["run_id"] = "run-" + "f" * 32
    elif mutation == "portfolio_bytes": inner["portfolio"]["shortfall"] = 0
    elif mutation == "portfolio_hash": inner["portfolio_sha256"] = "f" * 64
    (command.run_directory / "current-shadow/current-shadow-all-market-run-receipt.json").write_bytes(canonical_json_bytes(inner))
    with pytest.raises(ValueError):
        coordinator._build_shadow_receipt(
            run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"], envelope=envelope,
            snapshot=kwargs["snapshot"], command=command,
        )
    monitor(**kwargs)
    assert repository.run_snapshot(run_id)["state"] == "INTERRUPTED"
    assert "RUN_TERMINAL" not in [e[2] for e in repository.read_events(run_id)]
    assert len(launches) == 1


def test_no_portfolio_terminal_keeps_portfolio_identity_unavailable(tmp_path, clock, monkeypatch):
    _, repository, run_id, _, (monitor, kwargs), launches, _, _ = _terminal_case(
        tmp_path, clock, monkeypatch, portfolio=False,
    )
    monitor(**kwargs)
    assert repository.run_snapshot(run_id)["state"] == "TERMINAL"
    assert repository.latest_worker_progress(run_id)["identity_refs"]["portfolio_sha256"] is None
    assert len(launches) == 1


def test_portfolio_observation_preserves_validated_checkpoint_identities(tmp_path, clock, monkeypatch):
    coordinator, repository, run_id, envelope, (monitor, kwargs), launches, command, inner = _terminal_case(
        tmp_path, clock, monkeypatch,
    )
    coordinator._observe_available_checkpoints(**{k: kwargs[k] for k in (
        "run_id", "attempt_id", "lease_token", "request", "envelope", "command")})
    prior = repository.latest_worker_progress(run_id)["identity_refs"]
    inner["source_summary"] = {"wager_placed": False}
    (command.run_directory / "current-shadow/current-shadow-all-market-run-receipt.json").write_bytes(canonical_json_bytes(inner))
    build_args = dict(run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"],
                      envelope=envelope, snapshot=kwargs["snapshot"], command=command)
    first, _, _ = coordinator._build_shadow_receipt(**build_args)
    second, _, _ = coordinator._build_shadow_receipt(**build_args)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    monitor(**kwargs)
    assert repository.run_snapshot(run_id)["state"] == "TERMINAL"
    final = repository.latest_worker_progress(run_id)
    assert final["stage"] == "COMPLETE"
    assert final["identity_refs"]["portfolio_sha256"] == inner["portfolio_sha256"]
    for key in ("source_identity_sha256", "model_or_history_sha256", "router_diagnostics_sha256"):
        assert prior[key] is not None and final["identity_refs"][key] == prior[key]
    assert len(launches) == 1


@pytest.mark.parametrize("failure", ["staging", "launch"])
def test_staging_and_actual_launch_failures_have_distinct_evidence(resources, roots, clock, monkeypatch, failure):
    job, repository, previews, _, _ = _seed_job(resources, roots, clock, monkeypatch, specs=[{}])
    launches = []
    def fail_launch(self, command):
        launches.append(command)
        raise WorkerLaunchError("secret raw launch failure")
    monkeypatch.setattr(WorkerLauncher, "launch", fail_launch)
    if failure == "staging":
        def fail_staging(*args):
            raise ValueError("secret raw staging failure")
        monkeypatch.setattr(job, "_stage_and_build", fail_staging)
    args = dict(preview_id=previews[0][0], execution_envelope_sha256=previews[0][1], idempotency_key=previews[0][4])
    result = job.admit(**args)
    events = repository.read_events(result.run_id)
    assert repository.run_snapshot(result.run_id)["state"] == "INTERRUPTED"
    if failure == "staging":
        assert launches == []
        assert "WORKER_LAUNCH_FAILED" not in [e[2] for e in events]
    else:
        assert len(launches) == 1
        assert [e[2] for e in events] == ["RUN_QUEUED", "RUN_RUNNING", "WORKER_LAUNCH_FAILED", "RUN_INTERRUPTED"]
        assert json.loads(events[2][3]) == {"diagnostic_id": "WORKER_LAUNCH_FAILED"}
    assert all(b"secret" not in e[3] for e in events)
    assert job.admit(**args).disposition == "idempotent_replay"
    assert len(launches) == (0 if failure == "staging" else 1)


def test_terminal_snapshot_reauthenticates_retained_receipt(tmp_path, clock, monkeypatch):
    from services.athena_job_service import DurableRunReadAdapter
    from services.athena_read_service import ReadBackendError
    _, repository, run_id, _, (monitor, kwargs), _, _, _ = _terminal_case(tmp_path, clock, monkeypatch)
    monitor(**kwargs)
    adapter = DurableRunReadAdapter(repository)
    assert adapter.get_run_snapshot(run_id).selected_leg_count == 1
    artifact = repository.run_snapshot(run_id)["receipt_artifact_id"]
    path = repository._data_root / "run-receipts" / (artifact[8:] + ".json")
    path.write_bytes(b"{}\n")
    with pytest.raises(ReadBackendError, match="RUN_STORE_UNAVAILABLE"):
        adapter.get_run_snapshot(run_id)


def test_receipt_backed_progress_rejects_regression(tmp_path, clock, monkeypatch):
    from dataclasses import replace
    coordinator, repository, run_id, envelope, (_, kwargs), _, command, _ = _terminal_case(tmp_path, clock, monkeypatch)
    receipt, _, _ = coordinator._build_shadow_receipt(
        run_id=run_id, attempt_id=kwargs["attempt_id"], request=kwargs["request"],
        envelope=envelope, snapshot=kwargs["snapshot"], command=command,
    )
    args = {k: kwargs[k] for k in ("run_id", "attempt_id", "lease_token")}
    coordinator._observe_terminal_receipt(**args, receipt=receipt)
    counts = dict(receipt.counts)
    counts["reviewed_fixture_count"] -= 1
    with pytest.raises(RunStateConflict):
        coordinator._observe_terminal_receipt(**args, receipt=replace(receipt, counts=counts))
    evidence = receipt.to_dict()["evidence"]
    evidence["legacy_current_shadow"]["latest_stage_checkpoint"]["stage"] = "PORTFOLIO"
    evidence["legacy_current_shadow"]["latest_stage_checkpoint"]["stage_index"] = 5
    with pytest.raises(ValueError):
        coordinator._observe_terminal_receipt(**args, receipt=replace(receipt, evidence=evidence))
    assert repository.latest_worker_progress(run_id)["stage"] == "COMPLETE"


def test_terminal_snapshot_rejects_cross_request_receipt(tmp_path, clock, monkeypatch):
    from dataclasses import replace
    from domain.run_contracts import RunReceipt
    from services.athena_job_service import DurableRunReadAdapter
    from services.athena_read_service import ReadBackendError
    _, repository, run_id, _, (monitor, kwargs), _, _, _ = _terminal_case(tmp_path, clock, monkeypatch)
    monitor(**kwargs)
    receipt = RunReceipt.from_json_bytes(repository.read_receipt_bytes(run_id))
    other_request = replace(receipt.request, dates=(receipt.request.dates[0] + timedelta(days=1),))
    other = replace(receipt, request=other_request)
    monkeypatch.setattr(repository, "read_receipt_bytes", lambda _: canonical_json_bytes(other))
    with pytest.raises(ReadBackendError, match="RUN_STORE_UNAVAILABLE"):
        DurableRunReadAdapter(repository).get_run_snapshot(run_id)


class _SyntheticChild:
    def __init__(self, pid: int, returncode: int | None = None):
        self.pid = pid
        self.stdout = None
        self.stderr = None
        self._returncode = returncode
        self._lock = threading.Lock()

    def poll(self):
        with self._lock:
            return self._returncode

    def finish(self, returncode: int):
        with self._lock:
            self._returncode = returncode


class _SyntheticProcessControl:
    def __init__(self, process_handle, owner):
        self.handle = process_handle
        self.owner = owner
        self.locator = None
        self.cancel_count = 0

    def bind(self):
        pid = self.handle.pid
        if os.name == "nt":
            self.locator = {
                "kind": "WINDOWS_PROCESS_GROUP", "pid": pid,
                "creation_time": 1, "job_name": "Local\\ATHENA-E3-synthetic",
                **self.owner,
            }
        else:
            self.locator = {
                "kind": "POSIX_PROCESS_GROUP", "pid": pid, "pgid": pid,
                "session_id": pid, "start_ticks": 1, **self.owner,
            }
        return dict(self.locator)

    def state_current(self):
        return "DEAD" if self.handle.poll() is not None else "ACTIVE"

    @staticmethod
    def state(locator, owner):
        return "ACTIVE" if all(locator.get(key) == value for key, value in owner.items()) else "UNKNOWN"

    def request_cancel(self, locator):
        if locator != self.locator or self.cancel_count:
            return False
        self.cancel_count += 1
        return True

    def force_terminate(self, locator):
        if locator != self.locator:
            return False
        child = self.handle._process
        if child.poll() is None:
            child.finish(-9)
        return True

    def abort_before_start(self):
        child = self.handle._process
        if child.poll() is None:
            child.finish(-9)

    def close(self):
        return None


def _seed_job(resources, roots, clock, monkeypatch, *, specs, heartbeat_seconds=0.05):
    _use_synthetic_process_control(monkeypatch)
    app = open_repo(resources, roots)
    record_test_release(app, clock())
    previews = []
    for index, spec in enumerate(specs):
        service = AthenaPreviewAdmissionService(resources, clock=clock)
        result = service.preview(
            dates=[_PREVIEW_DATE],
            target_legs=3,
            target_total_odds=None,
            bookie="sportybet",
            profile=spec.get("profile", "main"),
            acquire_sources=spec.get("acquire_sources", False),
            create_share_code=spec.get("create_share_code", False),
        )
        item = service.preview_store.get(result["preview_id"], now=clock())
        assert item is not None
        envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
        app.persist_preview_bundle(
            item=item, envelope=envelope, release_id="test-release",
            profile_id="local-default", now=clock(),
        )
        previews.append((result["preview_id"], envelope.canonical_sha256, item, envelope,
                         spec.get("idempotency_key", "run-01b-" + str(index))))
    app.close()

    repository = DurableRunRepository(resources, roots, clock=clock)
    executable = resources.identity.release_root / "bin" / "athena-worker"
    executable.parent.mkdir(parents=True, exist_ok=True)
    payload = b"synthetic RUN-01B test worker pin"
    executable.write_bytes(payload)
    launcher = WorkerLauncher.for_installed(
        resources.identity,
        worker_executable=InstalledWorkerExecutable(
            path=executable, expected_sha256=hashlib.sha256(payload).hexdigest(),
        ),
        writable_roots=roots,
    )
    children = []
    calls = []

    def spawn(argv, *, cwd, shell, **kwargs):
        assert shell is False
        child = _SyntheticChild(8300 + len(children), spec_exit_code(specs, len(children)))
        children.append(child)
        calls.append((list(argv), cwd))
        return child

    monkeypatch.setattr(worker_launcher, "_spawn_process", spawn)
    preview_service = AthenaPreviewAdmissionService(
        resources,
        preview_store=DurablePreviewStore(open_repo(resources, roots), release_id="test-release"),
        admission_repository=repository,
        clock=clock,
    )
    job = AthenaJobService(preview_service, repository, launcher, roots)
    job._coordinator = WorkerCoordinator(
        repository, launcher, roots,
        heartbeat_seconds=heartbeat_seconds, poll_seconds=0.01, initial_poll_delay=0.01,
    )
    return job, repository, previews, children, calls


def spec_exit_code(specs, index):
    return specs[index].get("exit_code")


def _http_client(job, resources, roots):
    from api.app_factory import create_app
    from fastapi.testclient import TestClient
    from runtime.local_session import LocalSession

    session = LocalSession()
    reads = job.durable_read_service()
    capabilities = AthenaCapabilityService(
        resources, preview_admission_service=job.preview_service,
        read_service=reads, job_service=job,
    )
    origin = "http://127.0.0.1:12345"
    app = create_app(
        release_identity=resources.identity, resource_resolver=resources,
        writable_roots=roots, local_session=session, capability_service=capabilities,
        preview_admission_service=job.preview_service, read_service=reads,
        job_service=job, origin=origin,
    )
    return TestClient(app, base_url=origin), {
        "X-Athena-Session": session.credential(), "Origin": origin,
    }


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def test_http_returns_with_one_owned_worker_and_root_capacity_is_durable(
        resources, roots, clock, monkeypatch):
    job, repository, previews, children, calls = _seed_job(
        resources, roots, clock, monkeypatch,
        specs=[{"idempotency_key": "root-owner"}, {"idempotency_key": "root-queued"}],
    )
    client, headers = _http_client(job, resources, roots)
    with client:
        first_body = {
            "preview_id": previews[0][0],
            "execution_envelope_sha256": previews[0][1],
            "idempotency_key": previews[0][4],
        }
        first = client.post("/api/v1/runs", headers=headers, json=first_body)
        assert first.status_code == 202
        first_id = first.json()["run_id"]
        assert repository.run_snapshot(first_id)["state"] == "RUNNING"
        first_events = repository.read_events(first_id)
        assert [row[2] for row in first_events] == [
            "RUN_QUEUED", "RUN_RUNNING", "WORKER_STARTUP_GATE_PUBLISHED",
        ]
        assert children[0].poll() is None

        with repository._operation() as conn:
            attempt = conn.execute(
                "SELECT process_locator_json,started_at,heartbeat_at FROM app_run_attempts WHERE run_id=?",
                (first_id,),
            ).fetchone()
        locator = json.loads(attempt[0])
        expected_kind = "WINDOWS_PROCESS_GROUP" if os.name == "nt" else "POSIX_PROCESS_GROUP"
        assert locator["kind"] == expected_kind
        assert locator["pid"] == children[0].pid
        assert locator["run_id"] == first_id
        assert locator["attempt_id"]
        assert locator["worker_instance_id"]
        assert len(locator["lease_sha256"]) == 64

        clock.advance(timedelta(seconds=1))
        assert _wait_for(lambda: _heartbeat_advanced(repository, first_id, attempt[2]))

        second_body = {
            "preview_id": previews[1][0],
            "execution_envelope_sha256": previews[1][1],
            "idempotency_key": previews[1][4],
        }
        second = client.post("/api/v1/runs", headers=headers, json=second_body)
        assert second.status_code == 202
        second_id = second.json()["run_id"]
        assert repository.run_snapshot(second_id)["state"] == "QUEUED"
        assert len(calls) == 1

        cancel_before = repository.run_snapshot(first_id)
        cancelled = client.post("/api/v1/runs/" + first_id + "/cancel", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["state"] == "CANCEL_REQUESTED"
        after_cancel = repository.run_snapshot(first_id)
        assert after_cancel["state"] == "CANCEL_REQUESTED"
        assert after_cancel["state_version"] == cancel_before["state_version"] + 1
        attempt_id = repository.list_unfinished_attempts()[0]["attempt_id"]
        assert job.coordinator._process_controls[attempt_id].cancel_count == 1
        repeated = client.post("/api/v1/runs/" + first_id + "/cancel", headers=headers)
        assert repeated.status_code == 200
        assert repeated.json()["disposition"] == "already_requested"
        assert repository.run_snapshot(first_id)["state_version"] == after_cancel["state_version"]
        assert job.coordinator._process_controls[attempt_id].cancel_count == 1

        children[0].finish(1)
        assert _wait_for(lambda: repository.run_snapshot(first_id)["state"] == "CANCELLED")
        assert repository.run_snapshot(second_id)["state"] == "QUEUED"
        replay = client.post("/api/v1/runs", headers=headers, json=second_body)
        assert replay.status_code == 202
        assert replay.json()["admission_state"] == "idempotent_replay"
        assert len(calls) == 1


def _heartbeat_advanced(repository, run_id, previous):
    with repository._operation() as conn:
        row = conn.execute(
            "SELECT heartbeat_at FROM app_run_attempts WHERE run_id=?", (run_id,),
        ).fetchone()
    return row is not None and row[0] > previous


def test_zero_exit_without_verified_receipt_interrupts_without_retry(
        resources, roots, clock, monkeypatch):
    job, repository, previews, children, calls = _seed_job(
        resources, roots, clock, monkeypatch,
        specs=[{"idempotency_key": "no-receipt", "exit_code": 0}],
    )
    accepted = job.admit(
        preview_id=previews[0][0], execution_envelope_sha256=previews[0][1],
        idempotency_key=previews[0][4],
    )
    assert accepted.disposition == "admitted"
    assert _wait_for(lambda: repository.run_snapshot(accepted.run_id)["state"] == "INTERRUPTED")
    rows = repository.read_events(accepted.run_id)
    diagnostics = [json.loads(row[3]) for row in rows if row[2] == "WORKER_INTERRUPTED"]
    assert diagnostics == [{
        "diagnostic_id": "WORKER_EXIT_WITHOUT_VERIFIED_RECEIPT",
        "exit_code": 0,
        "last_proven_stage": None,
    }]
    assert len(calls) == 1
    replay = job.admit(
        preview_id=previews[0][0], execution_envelope_sha256=previews[0][1],
        idempotency_key=previews[0][4],
    )
    assert replay.disposition == "idempotent_replay"
    assert len(calls) == 1


def _development_shadow_run(tmp_path, clock, *, acquire_sources=False):
    identity = verify_development_checkout(ROOT)
    assert type(identity) is DevelopmentCheckoutIdentity
    resources = ResourceResolver.for_development(identity)
    roots = WritableRoots(
        data_root=tmp_path / "dev-data", cache_root=tmp_path / "dev-cache",
        state_root=tmp_path / "dev-state",
    )
    roots.ensure_created()
    release_id = "development-checkout:" + identity.head_commit_sha
    app = open_repo(resources, roots, release_id=release_id)
    record_test_release(app, clock())
    preview = AthenaPreviewAdmissionService(resources, clock=clock)
    result = preview.preview(
        dates=[_PREVIEW_DATE], target_legs=3, target_total_odds=None,
        bookie="sportybet", profile="shadow", acquire_sources=acquire_sources,
        create_share_code=False,
    )
    item = preview.preview_store.get(result["preview_id"], now=clock())
    assert item is not None
    envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
    app.persist_preview_bundle(
        item=item, envelope=envelope, release_id=release_id,
        profile_id="local-default", now=clock(),
    )
    app.close()
    repository = DurableRunRepository(resources, roots, clock=clock)
    return identity, roots, repository, item, envelope


def test_typed_progress_is_ordered_deduplicated_and_keeps_named_identities(tmp_path, clock):
    identity, roots, repository, item, envelope = _development_shadow_run(tmp_path, clock)
    from services.athena_preview_service import AdmissionCandidate

    candidate = AdmissionCandidate(
        item.preview_id, item.request_bytes, envelope.request_sha256,
        item.envelope_bytes, envelope.canonical_sha256, "progress-run",
        envelope.authority_manifest_sha256,
        hashlib.sha256(canonical_json_bytes(envelope.source_identity)).hexdigest(),
        envelope.expires_at,
    )
    run_id = repository.admit(candidate).run_id
    attempt, lease, _number = repository.claim_attempt(
        run_id, worker_instance_id="run-01b-progress",
        process_locator={"kind": "OFFLINE_TEST", "label": "offline-probe"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING", attempt_id=attempt, lease_token=lease,
    )
    request = RunRequest.from_json_bytes(item.request_bytes)
    run_directory = roots.data_root / "runs" / run_id / request.canonical_sha256
    run_directory.mkdir(parents=True)
    current_dir = run_directory / "current-shadow"
    current_dir.mkdir()
    command = WorkerCommand(
        operation="CURRENT_SHADOW_REQUEST", mode="research_shadow",
        run_directory=run_directory, request_artifact_id=request.canonical_sha256,
        envelope_artifact_id=None, release_identity_kind=identity.identity_kind,
        release_identity_id=identity.head_commit_sha,
    )
    coordinator = WorkerCoordinator(repository, WorkerLauncher.for_development(identity), roots)
    observed = "2030-01-01T23:00:00.000000Z"
    stage = {
        "schema_version": 1,
        "dataset_name": "athena-current-shadow-all-market-runner-v1",
        "stage": "STARTED", "stage_index": 0, "observed_at": observed,
        "exact_commit_sha": identity.head_commit_sha, "requested_target_size": 3,
        "wager_placed": False,
    }
    source_summary = {
        "current_fotmob": {"source_raw_sha256": "a" * 64},
        "complete_current_history_sha256": "b" * 64,
        "runtime_progress_diagnostics": {"router_checkpoint_sha256": "c" * 64},
        "wager_placed": False,
    }
    progress = {
        **{key: stage[key] for key in stage if key != "stage"},
        "stage": "STARTED", "progress_status": "IN_PROGRESS",
        "counts": {name: (1 if name == "reviewed_fixture_count" else 0) for name in _COUNT_NAMES},
        "source_summary": source_summary,
    }
    progress_raw = canonical_json_bytes(progress)
    (current_dir / "current-shadow-all-market-stage.json").write_bytes(canonical_json_bytes(stage))
    (current_dir / "current-shadow-all-market-progress.json").write_bytes(progress_raw)
    kwargs = dict(
        run_id=run_id, attempt_id=attempt, lease_token=lease, request=request,
        envelope=envelope, command=command,
    )
    coordinator._observe_checkpoint(source="stage", filename="current-shadow-all-market-stage.json", **kwargs)
    coordinator._observe_checkpoint(source="progress", filename="current-shadow-all-market-progress.json", **kwargs)
    assert coordinator._observe_checkpoint(
        source="progress", filename="current-shadow-all-market-progress.json", **kwargs,
    ) is False

    latest = repository.latest_worker_progress(run_id)
    assert latest["counts"]["reviewed_fixture_count"] == 1
    refs = latest["identity_refs"]
    assert refs["source_summary_sha256"] is not None
    assert refs["source_identity_sha256"] is not None
    assert refs["model_or_history_sha256"] is not None
    assert refs["router_diagnostics_sha256"] is not None
    assert refs["portfolio_sha256"] is None

    later_stage = {**stage, "stage": "CURRENT_FOTMOB_SOURCE", "stage_index": 1,
                   "observed_at": "2030-01-01T23:00:01.000000Z"}
    (current_dir / "current-shadow-all-market-stage.json").write_bytes(canonical_json_bytes(later_stage))
    coordinator._observe_checkpoint(
        source="stage", filename="current-shadow-all-market-stage.json", **kwargs,
    )
    assert repository.latest_worker_progress(run_id)["counts"] == latest["counts"]
    assert repository.latest_worker_progress(run_id)["stage"] == "CURRENT_FOTMOB_SOURCE"

    regressed = {**progress, "stage": "CURRENT_FOTMOB_SOURCE", "stage_index": 1,
                 "observed_at": "2030-01-01T23:00:02.000000Z",
                 "counts": {**progress["counts"], "reviewed_fixture_count": 0}}
    (current_dir / "current-shadow-all-market-progress.json").write_bytes(canonical_json_bytes(regressed))
    with pytest.raises(RunStateConflict, match="count regressed"):
        coordinator._observe_checkpoint(
            source="progress", filename="current-shadow-all-market-progress.json", **kwargs,
        )


def test_installed_shadow_source_acquisition_stays_blocked(resources, roots, clock, monkeypatch):
    job, _repository, previews, children, _calls = _seed_job(
        resources, roots, clock, monkeypatch,
        specs=[{"profile": "shadow", "acquire_sources": True,
                "create_share_code": False, "idempotency_key": "installed-shadow"}],
    )
    _preview_id, _digest, item, envelope, _key = previews[0]
    request = __import__("domain.run_contracts", fromlist=["RunRequest"]).RunRequest.from_json_bytes(
        item.request_bytes
    )
    with pytest.raises(WorkerLaunchError, match="installed Current Shadow execution is blocked"):
        job._stage_and_build("installed-shadow-run", request, item.request_bytes, envelope)
    assert children == []
