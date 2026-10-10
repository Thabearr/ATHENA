"""E1 offline proofs: commit-first admission, replay fencing, one worker, durable reads.

No provider, acquisition, delivery, wager, login, cookie, wallet, stake,
email, workflow, or network action. Worker spawning is faked at the
``_spawn_process`` seam; no child process is created.
"""
from __future__ import annotations

import hashlib
import platform
import socket
import smtplib
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from database.app_repository import AppRepository, release_provenance
from database.run_repository import DurableRunRepository
from domain.run_contracts import canonical_json_bytes
from runtime import worker_launcher
from runtime.release_identity import canonical_release_manifest_bytes, verify_installed_release
from runtime.resources import ResourceResolver, WritableRoots
from runtime.worker_launcher import WorkerLauncher, InstalledWorkerExecutable, WorkerLaunchError
from services.athena_capability_service import AthenaCapabilityService
from services.athena_job_service import AthenaJobService
from services.athena_preview_service import AthenaPreviewAdmissionService, PreviewAdmissionError
from services.app_preview_store import DurablePreviewStore

ROOT = Path(__file__).resolve().parents[1]
PREVIEW_DATE = "2030-01-01"


class MutableClock:
    def __init__(self, value: datetime | None = None):
        self.value = value or datetime(2030, 1, 1, 22, 59, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


@pytest.fixture
def clock():
    return MutableClock()


@pytest.fixture
def resources(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    records = []
    for path, role in (
        ("ui/index.html", "UI"),
        ("ui/app.js", "UI"),
        ("ui/styles.css", "UI"),
        ("config/architecture/component-authority-registry-v1.json", "AUTHORITY_REGISTRY"),
        ("database/migrations/0001_app_control_core.sql", "MIGRATION"),
        ("database/migrations/0002_app_runs_operations.sql", "MIGRATION"),
        ("database/migrations/0003_app_projections_exports.sql", "MIGRATION"),
    ):
        payload = (ROOT / path).read_bytes()
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records.append({
            "logical_path": path,
            "payload_path": path,
            "role": role,
            "byte_sha256": hashlib.sha256(payload).hexdigest(),
            "required": True,
            "source_git_blob_sha1": None,
            "canonical_sha256": None,
        })
    architecture = {
        "amd64": "x86_64", "x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"
    }[platform.machine().lower()]
    manifest = {
        "schema_version": 1,
        "policy_id": "ATHENA_INSTALLED_RELEASE_MANIFEST_V1",
        "release_id": "test-release",
        "build_id": "test-build",
        "platform_tag": "windows" if sys.platform == "win32" else "linux",
        "architecture_tag": architecture,
        "closed_world_roots": ["config", "database/migrations", "ui"],
        "resources": sorted(records, key=lambda row: row["logical_path"]),
    }
    raw = canonical_release_manifest_bytes(manifest)
    (root / "release-manifest.json").write_bytes(raw)
    identity = verify_installed_release(root, hashlib.sha256(raw).hexdigest())
    return ResourceResolver.for_installed(identity)


@pytest.fixture
def roots(tmp_path, resources):
    r = WritableRoots(
        data_root=tmp_path / "user-data",
        cache_root=tmp_path / "user-cache",
        state_root=tmp_path / "user-state",
        installed_release_root=resources.identity.release_root,
    )
    r.ensure_created()
    return r


@pytest.fixture(autouse=True)
def no_live_actions(monkeypatch):
    original_connect = socket.socket.connect
    def deny_external(self, address):
        # Windows asyncio implements its internal self-pipe with socketpair
        # loopback. The global reviewed transport guard remains installed.
        if sys.platform == "win32" and isinstance(address, tuple) and address[0] == "127.0.0.1":
            return original_connect(self, address)
        raise AssertionError("external transport forbidden in E1 offline proof")
    def deny(*args, **kwargs):
        raise AssertionError("live/provider/delivery action forbidden in E1 offline proof")

    monkeypatch.setattr(socket.socket, "connect", deny_external)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    monkeypatch.setattr(smtplib, "SMTP_SSL", deny)
    from domain import sportybet_share_code

    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code", deny)
    monkeypatch.setattr(sportybet_share_code, "create_verified_share_code_as_of", deny)


class _FakeProcess:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.pid = 1234

    def poll(self):
        return self.returncode

    def communicate(self):
        return ("", "")


def _open_repo(resources, roots, *, release_id="test-release"):
    return AppRepository.open(resources, roots, release_id=release_id)


def _record_test_release(repo, now):
    repo.record_release_manifest(**release_provenance(repo.verified_identity, verified_at=now))


def _make_stored_preview(resources, clock):
    service = AthenaPreviewAdmissionService(resources, clock=clock)
    result = service.preview(
        dates=[PREVIEW_DATE],
        target_legs=3,
        target_total_odds=None,
        bookie="sportybet",
        profile="main",
        acquire_sources=False,
        create_share_code=False,
    )
    stored = service.preview_store.get(result["preview_id"], now=clock())
    assert stored is not None
    return service, stored


def _durable_job(resources, roots, clock, monkeypatch, *, launch_effect=None):
    app = _open_repo(resources, roots)
    _record_test_release(app, clock())
    _, item = _make_stored_preview(resources, clock)
    envelope_sha = hashlib.sha256(item.envelope_bytes).hexdigest()
    from domain.execution_envelope import ExecutionEnvelope

    envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
    app.persist_preview_bundle(
        item=item, envelope=envelope, release_id="test-release",
        profile_id="local-default", now=clock())
    app.close()
    repository = DurableRunRepository(resources, roots, clock=clock)
    preview = AthenaPreviewAdmissionService(
        resources,
        preview_store=DurablePreviewStore(_open_repo(resources, roots), release_id="test-release"),
        admission_repository=repository,
        clock=clock,
    )
    identity = resources.identity
    executable_path = resources.identity.release_root / "bin" / "athena-worker"
    executable_path.parent.mkdir(parents=True, exist_ok=True)
    executable_bytes = b"e1 synthetic worker pin"
    executable_path.write_bytes(executable_bytes)
    launcher = WorkerLauncher.for_installed(
        identity,
        worker_executable=InstalledWorkerExecutable(
            path=executable_path,
            expected_sha256=hashlib.sha256(executable_bytes).hexdigest(),
        ),
        writable_roots=roots,
    )
    calls: list = []

    def fake_spawn(argv, *, cwd, shell, **kwargs):
        # Independent read connection must see the committed admission before
        # the process seam can be reached.
        committed = repository.list_run_history()
        assert len(committed) == 1
        assert committed[0]["state"] == "RUNNING"
        calls.append((list(argv), cwd, shell))
        if launch_effect is not None:
            raise launch_effect
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(worker_launcher, "_spawn_process", fake_spawn)
    job = AthenaJobService(preview, repository, launcher, roots)
    return job, repository, item, envelope_sha, calls


def test_failed_commit_launches_no_worker(resources, roots, clock, monkeypatch):
    job, repository, item, envelope_sha, calls = _durable_job(resources, roots, clock, monkeypatch)
    clock.advance(timedelta(days=1))
    with pytest.raises(PreviewAdmissionError):
        job.admit(
            preview_id=item.preview_id,
            execution_envelope_sha256=envelope_sha,
            idempotency_key="e1-failed-commit",
        )
    assert calls == []
    from services.athena_preview_service import AdmissionReplayIdentity

    assert repository.lookup(AdmissionReplayIdentity(
        "e1-failed-commit", item.preview_id, envelope_sha)).disposition == "not_found"


def test_admitted_launches_once_and_replay_launches_never(resources, roots, clock, monkeypatch):
    job, repository, item, envelope_sha, calls = _durable_job(resources, roots, clock, monkeypatch)
    first = job.admit(
        preview_id=item.preview_id,
        execution_envelope_sha256=envelope_sha,
        idempotency_key="e1-once",
    )
    assert first.disposition == "admitted"
    assert len(calls) == 1
    assert calls[0][2] is False
    run_id = first.run_id
    snapshot = repository.run_snapshot(run_id)
    assert snapshot["state"] == "RUNNING"
    request_sha = snapshot["request_sha256"]
    run_directory = roots.data_root / "runs" / run_id / request_sha
    assert run_directory.is_dir()
    assert (run_directory / "athena-run-request.json").read_bytes() == snapshot["request_bytes"]
    second = job.admit(
        preview_id=item.preview_id,
        execution_envelope_sha256=envelope_sha,
        idempotency_key="e1-once",
    )
    assert second.disposition == "idempotent_replay" and second.run_id == run_id
    assert len(calls) == 1
    with pytest.raises(PreviewAdmissionError) as conflict:
        job.admit(
            preview_id=item.preview_id,
            execution_envelope_sha256="0" * 64,
            idempotency_key="e1-once",
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    assert len(calls) == 1
    with pytest.raises(PreviewAdmissionError) as consumed:
        job.admit(
            preview_id=item.preview_id,
            execution_envelope_sha256=envelope_sha,
            idempotency_key="e1-other-key",
        )
    assert consumed.value.code == "PREVIEW_ALREADY_CONSUMED_CONFLICT"
    assert len(calls) == 1


def test_launch_failure_keeps_commit_and_marks_interrupted(resources, roots, clock, monkeypatch):
    job, repository, item, envelope_sha, calls = _durable_job(
        resources, roots, clock, monkeypatch,
        launch_effect=WorkerLaunchError("e1 fake launch failure"),
    )
    result = job.admit(
        preview_id=item.preview_id,
        execution_envelope_sha256=envelope_sha,
        idempotency_key="e1-launch-fails",
    )
    assert result.disposition == "admitted"
    assert len(calls) == 1
    assert repository.run_snapshot(result.run_id)["state"] == "INTERRUPTED"
    rows = repository.read_events(result.run_id)
    assert [row[2] for row in rows] == [
        "RUN_QUEUED", "RUN_RUNNING", "WORKER_LAUNCH_FAILED", "RUN_INTERRUPTED"]
    assert [row[1] for row in rows] == [0, 1, 1, 2]
    assert rows[2][5] == rows[3][5]
    with repository._operation() as conn:
        finished, disposition = conn.execute(
            "SELECT finished_at,recovery_disposition FROM app_run_attempts WHERE run_id=?",
            (result.run_id,)).fetchone()
    assert finished == rows[3][5] and disposition == "OFFLINE_LAUNCH_FAILED"
    assert b"e1 fake launch failure" not in b"".join(row[3] for row in rows)
    events = job.durable_read_service().list_run_events(result.run_id, after_sequence=0, limit=50)
    assert [event.kind for event in events.events] == [
        "STATE_CHANGED", "STATE_CHANGED", "DIAGNOSTIC", "STATE_CHANGED"]
    assert events.events[2].payload.diagnostic_id == "WORKER_LAUNCH_FAILED"
    client, headers = _http_client(job, resources, roots)
    with client:
        response = client.get("/api/v1/runs/" + result.run_id + "/events", headers=headers)
        assert response.status_code == 200
        assert response.json()["events"][2]["payload"]["diagnostic_id"] == "WORKER_LAUNCH_FAILED"
        assert "e1 fake launch failure" not in response.text
    replay = job.admit(
        preview_id=item.preview_id,
        execution_envelope_sha256=envelope_sha,
        idempotency_key="e1-launch-fails",
    )
    assert replay.disposition == "idempotent_replay" and replay.run_id == result.run_id
    assert len(calls) == 1


def test_durable_reads_snapshot_events_history_and_cancel(resources, roots, clock, monkeypatch):
    job, repository, item, envelope_sha, _calls = _durable_job(resources, roots, clock, monkeypatch)
    admitted = job.admit(
        preview_id=item.preview_id,
        execution_envelope_sha256=envelope_sha,
        idempotency_key="e1-reads",
    )
    run_id = admitted.run_id
    reads = job.durable_read_service()
    snapshot = reads.get_run_snapshot(run_id)
    assert snapshot.run_id == run_id and snapshot.state == "RUNNING"
    assert snapshot.target_legs == 3
    assert snapshot.request_identity_ref == repository.run_snapshot(run_id)["request_sha256"]
    assert reads.run_repository.get_run_snapshot("run-missing-1") is None
    page = reads.list_run_events(run_id, after_sequence=0, limit=50)
    assert [event.sequence for event in page.events] == [1, 2]
    assert all(event.kind == "STATE_CHANGED" for event in page.events)
    history = reads.list_runs(cursor=None, limit=50, state=None, profile=None)
    assert any(entry.run_id == run_id and entry.profile == "MAIN" for entry in history.items)
    main_only = reads.list_runs(cursor=None, limit=50, state=None, profile="MAIN")
    assert all(entry.profile == "MAIN" for entry in main_only.items)
    from services.athena_read_service import ReadServiceError
    before = repository.run_snapshot(run_id)
    with pytest.raises(ReadServiceError) as blocked:
        reads.request_cancel(run_id)
    assert blocked.value.code == "CANCEL_STORE_UNAVAILABLE"
    assert repository.run_snapshot(run_id) == before
    assert reads.list_run_events(run_id, after_sequence=0, limit=50) == page


def test_capability_truth_follows_durable_wiring(resources, roots, clock, monkeypatch):
    unavailable_preview = AthenaPreviewAdmissionService(resources, clock=clock)
    unavailable_caps = AthenaCapabilityService(
        resources, preview_admission_service=unavailable_preview).snapshot()
    states = {row["capability_id"]: row["state"] for row in unavailable_caps["capabilities"]}
    assert states["run_admission"] == "blocked_implementation"
    assert unavailable_caps["run_admission_authority"] is False
    job, _repository, _item, _sha, _calls = _durable_job(resources, roots, clock, monkeypatch)
    durable_caps = AthenaCapabilityService(
        resources, preview_admission_service=job.preview_service,
        read_service=job.durable_read_service(), job_service=job).snapshot()
    durable_states = {row["capability_id"]: row["state"] for row in durable_caps["capabilities"]}
    assert durable_states["run_admission"] == "available"
    assert durable_states["run_history"] == "available"
    assert durable_states["cancel_intent"] == "blocked_implementation"
    assert durable_caps["run_admission_authority"] is True


def test_job_module_has_no_forbidden_transport_imports():
    raw = (ROOT / "services" / "athena_job_service.py").read_bytes().decode("utf-8")
    lowered = raw.lower()
    for token in (
        "import socket", "import smtplib", "import urllib", "import httpx",
        "import requests", "subprocess", "sportybet_share_code",
        "create_verified_share_code", "send_receipt_email",
        "fotmob",
    ):
        assert token not in lowered


def test_concurrent_identical_admission_has_one_worker(resources, roots, clock, monkeypatch):
    job, repository, item, digest, calls = _durable_job(resources, roots, clock, monkeypatch)
    def admit(_):
        return job.admit(preview_id=item.preview_id,
                         execution_envelope_sha256=digest,
                         idempotency_key="e1-concurrent")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(admit, range(4)))
    assert len({result.run_id for result in results}) == 1
    assert [result.disposition for result in results].count("admitted") == 1
    assert len(calls) == 1


def test_restart_replay_does_not_launch_again(resources, roots, clock, monkeypatch):
    job, repository, item, digest, calls = _durable_job(resources, roots, clock, monkeypatch)
    args = dict(preview_id=item.preview_id, execution_envelope_sha256=digest,
                idempotency_key="e1-restart")
    first = job.admit(**args)
    restarted_repository = DurableRunRepository(resources, roots, clock=clock)
    restarted_preview = AthenaPreviewAdmissionService(
        resources, preview_store=job.preview_service.preview_store,
        admission_repository=restarted_repository, clock=clock)
    restarted = AthenaJobService(restarted_preview, restarted_repository, job._launcher, roots)
    clock.advance(timedelta(days=1))
    replay = restarted.admit(**args)
    assert replay.run_id == first.run_id
    assert replay.disposition == "idempotent_replay"
    assert len(calls) == 1


def _http_client(job, resources, roots):
    from api.app_factory import create_app
    from runtime.local_session import LocalSession
    from fastapi.testclient import TestClient
    session = LocalSession()
    reads = job.durable_read_service()
    capabilities = AthenaCapabilityService(
        resources, preview_admission_service=job.preview_service, read_service=reads, job_service=job)
    origin = "http://127.0.0.1:12345"
    app = create_app(release_identity=resources.identity, resource_resolver=resources,
                     writable_roots=roots, local_session=session,
                     capability_service=capabilities,
                     preview_admission_service=job.preview_service,
                     read_service=reads, job_service=job, origin=origin)
    headers = {"X-Athena-Session": session.credential(), "Origin": origin}
    return TestClient(app, base_url=origin), headers


def test_http_job_admission_and_durable_reads(resources, roots, clock, monkeypatch):
    job, repository, item, digest, calls = _durable_job(resources, roots, clock, monkeypatch)
    client, headers = _http_client(job, resources, roots)
    body = dict(preview_id=item.preview_id, execution_envelope_sha256=digest,
                idempotency_key="e1-http")
    with client:
        accepted = client.post("/api/v1/runs", headers=headers, json=body)
        assert accepted.status_code == 202
        replay = client.post("/api/v1/runs", headers=headers, json=body)
        assert replay.status_code == 202
        run_id = accepted.json()["run_id"]
        assert replay.json()["run_id"] == run_id
        assert client.get("/api/v1/runs/" + run_id, headers=headers).status_code == 200
        assert client.get("/api/v1/runs/" + run_id + "/events", headers=headers).status_code == 200
        assert client.get("/api/v1/runs", headers=headers).status_code == 200
        before = repository.run_snapshot(run_id)
        events = repository.read_events(run_id)
        blocked = client.post("/api/v1/runs/" + run_id + "/cancel", headers=headers)
        assert blocked.status_code == 503
        assert "CANCEL_STORE_UNAVAILABLE" in blocked.text
        assert repository.run_snapshot(run_id) == before
        assert repository.read_events(run_id) == events
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [b'{}\n', b'{"diagnostic_id":"secret"}\n',
    b'{"diagnostic_id":"WORKER_LAUNCH_FAILED","path":"secret"}\n',
    b'{ "diagnostic_id":"WORKER_LAUNCH_FAILED" }\n'])
def test_launch_diagnostic_projection_fails_closed(payload):
    from services.athena_job_service import _event_record
    from services.athena_read_service import ReadBackendError
    with pytest.raises(ReadBackendError):
        _event_record((3, 1, "WORKER_LAUNCH_FAILED", payload,
                       hashlib.sha256(payload).hexdigest(), "2030-01-01T23:00:00.000000Z"))


@pytest.mark.parametrize("failed_event", ["WORKER_LAUNCH_FAILED", "RUN_INTERRUPTED"])
def test_atomic_launch_failure_rolls_back_all_writes(resources, roots, clock, monkeypatch, failed_event):
    job, repository, item, digest, calls = _durable_job(resources, roots, clock, monkeypatch)
    result = job.admit(preview_id=item.preview_id, execution_envelope_sha256=digest,
                       idempotency_key="e1-atomic-rollback")
    before = repository.run_snapshot(result.run_id)
    events = repository.read_events(result.run_id)
    with repository._operation() as conn:
        attempt = conn.execute("SELECT * FROM app_run_attempts WHERE run_id=?", (result.run_id,)).fetchone()
        attempt_id, lease = conn.execute("SELECT attempt_id,lease_token FROM app_run_attempts WHERE run_id=?",
                                        (result.run_id,)).fetchone()
    original = DurableRunRepository._event
    def fail_event(conn, run_id, version, event_type, payload, stamp):
        original(conn, run_id, version, event_type, payload, stamp)
        if event_type == failed_event:
            raise RuntimeError("synthetic evidence persistence failure")
    monkeypatch.setattr(DurableRunRepository, "_event", staticmethod(fail_event))
    with pytest.raises(RuntimeError):
        repository.record_launch_failure_and_interrupt(result.run_id, attempt_id, lease)
    independent = DurableRunRepository(resources, roots, clock=clock)
    assert independent.run_snapshot(result.run_id) == before
    assert independent.read_events(result.run_id) == events
    with independent._operation() as conn:
        assert conn.execute("SELECT * FROM app_run_attempts WHERE run_id=?", (result.run_id,)).fetchone() == attempt
    assert before["state"] == "RUNNING" and before["state_version"] == 1
    assert len(calls) == 1


def test_atomic_launch_failure_fences_wrong_lease(resources, roots, clock, monkeypatch):
    from database.run_repository import RunLeaseFenced
    job, repository, item, digest, calls = _durable_job(resources, roots, clock, monkeypatch)
    result = job.admit(preview_id=item.preview_id, execution_envelope_sha256=digest,
                       idempotency_key="e1-atomic-fence")
    with repository._operation() as conn:
        attempt_id, lease = conn.execute("SELECT attempt_id,lease_token FROM app_run_attempts WHERE run_id=?",
                                        (result.run_id,)).fetchone()
    before = repository.run_snapshot(result.run_id)
    events = repository.read_events(result.run_id)
    with pytest.raises(RunLeaseFenced):
        repository.record_launch_failure_and_interrupt(result.run_id, attempt_id, "wrong-lease")
    assert repository.run_snapshot(result.run_id) == before
    assert repository.read_events(result.run_id) == events
    repository.record_launch_failure_and_interrupt(result.run_id, attempt_id, lease)
    with pytest.raises(RunLeaseFenced):
        repository.record_launch_failure_and_interrupt(result.run_id, attempt_id, lease)
    assert len(repository.read_events(result.run_id)) == 4 and len(calls) == 1


def test_job_atomic_evidence_failure_never_recovers_or_retries(resources, roots, clock, monkeypatch):
    job, repository, item, digest, calls = _durable_job(
        resources, roots, clock, monkeypatch, launch_effect=WorkerLaunchError("secret fake failure"))
    original = DurableRunRepository._event
    def fail_diagnostic(conn, run_id, version, event_type, payload, stamp):
        if event_type == "WORKER_LAUNCH_FAILED":
            raise RuntimeError("synthetic diagnostic write failure")
        return original(conn, run_id, version, event_type, payload, stamp)
    recovery_calls = []
    monkeypatch.setattr(DurableRunRepository, "_event", staticmethod(fail_diagnostic))
    monkeypatch.setattr(repository, "recover_attempt", lambda *args: recovery_calls.append(args))
    args = dict(preview_id=item.preview_id, execution_envelope_sha256=digest,
                idempotency_key="e1-atomic-store-failure")
    result = job.admit(**args)
    assert result.disposition == "admitted"
    assert repository.run_snapshot(result.run_id)["state"] == "RUNNING"
    assert [row[2] for row in repository.read_events(result.run_id)] == ["RUN_QUEUED", "RUN_RUNNING"]
    with repository._operation() as conn:
        assert conn.execute("SELECT finished_at FROM app_run_attempts WHERE run_id=?", (result.run_id,)).fetchone() == (None,)
    assert job.admit(**args).run_id == result.run_id
    assert len(calls) == 1 and recovery_calls == []
