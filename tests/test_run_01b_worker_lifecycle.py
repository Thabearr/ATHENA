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


def _seed_job(resources, roots, clock, monkeypatch, *, specs, heartbeat_seconds=0.05):
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
        assert [row[2] for row in first_events] == ["RUN_QUEUED", "RUN_RUNNING"]
        assert children[0].poll() is None

        with repository._operation() as conn:
            attempt = conn.execute(
                "SELECT process_locator_json,started_at,heartbeat_at FROM app_run_attempts WHERE run_id=?",
                (first_id,),
            ).fetchone()
        locator = json.loads(attempt[0])
        expected_kind = "WINDOWS_PROCESS_GROUP" if os.name == "nt" else "POSIX_PROCESS_GROUP"
        assert locator == {"kind": expected_kind, "pid": children[0].pid}

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
        blocked = client.post("/api/v1/runs/" + first_id + "/cancel", headers=headers)
        assert blocked.status_code == 503
        assert "CANCEL_STORE_UNAVAILABLE" in blocked.text
        assert repository.run_snapshot(first_id) == cancel_before

        children[0].finish(1)
        assert _wait_for(lambda: repository.run_snapshot(first_id)["state"] == "INTERRUPTED")
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


def _development_shadow_run(tmp_path, clock):
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
        bookie="sportybet", profile="shadow", acquire_sources=False,
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
