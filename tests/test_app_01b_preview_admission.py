"""Offline D1 proof for immutable previews and fail-closed admission."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys
import threading

from fastapi.testclient import TestClient
import pytest

from api.app_factory import create_app
from domain.execution_envelope import ExecutionEnvelope, ExecutionPreview, SourceReleaseIdentity, evaluate_execution_envelope
from domain.run_contracts import RunRequest
from runtime.local_session import LocalSession
from runtime.release_identity import canonical_release_manifest_bytes, verify_installed_release
from runtime.resources import ResourceResolver, WritableRoots
from services.athena_capability_service import AthenaCapabilityService
from services.athena_preview_service import (
    AdmissionCandidate,
    AdmissionRepositoryUnavailable,
    AdmissionResult,
    AthenaPreviewAdmissionService,
    PREVIEW_TTL,
)
from services.athena_run_service import AthenaRunService


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:12345"
HOST = "127.0.0.1:12345"
PREVIEW_DATE = "2030-01-01"


class MutableClock:
    def __init__(self, value: datetime | None = None):
        # Lagos is UTC+1: Jan 1 22:59 UTC is one minute before local midnight.
        self.value = value or datetime(2030, 1, 1, 22, 59, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class AtomicFakeAdmissionRepository:
    """Test-only transactional fake proving the repository port semantics."""

    def __init__(self):
        self.calls: list[AdmissionCandidate] = []
        self.by_key: dict[str, tuple[tuple[object, ...], str]] = {}
        self.by_preview: dict[str, tuple[str, tuple[object, ...], str]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _identity(candidate: AdmissionCandidate) -> tuple[object, ...]:
        return (
            candidate.preview_id,
            candidate.request_bytes,
            candidate.request_sha256,
            candidate.execution_envelope_bytes,
            candidate.execution_envelope_sha256,
            candidate.authority_manifest_sha256,
            candidate.source_identity_sha256,
        )

    def admit(self, candidate: AdmissionCandidate) -> AdmissionResult:
        with self._lock:
            self.calls.append(candidate)
            identity = self._identity(candidate)
            existing_key = self.by_key.get(candidate.idempotency_key)
            if existing_key is not None:
                if existing_key[0] != identity:
                    return AdmissionResult("idempotency_conflict")
                return AdmissionResult("idempotent_replay", existing_key[1])
            existing_preview = self.by_preview.get(candidate.preview_id)
            if existing_preview is not None:
                return AdmissionResult("preview_consumed_conflict")
            run_id = f"run-{len(self.by_key) + 1}"
            self.by_key[candidate.idempotency_key] = (identity, run_id)
            self.by_preview[candidate.preview_id] = (candidate.idempotency_key, identity, run_id)
            return AdmissionResult("admitted", run_id)


class CountingUnavailableRepository:
    def __init__(self):
        self.calls: list[AdmissionCandidate] = []

    def admit(self, candidate: AdmissionCandidate) -> AdmissionResult:
        self.calls.append(candidate)
        raise AdmissionRepositoryUnavailable


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
        "closed_world_roots": ["config", "ui"],
        "resources": sorted(records, key=lambda row: row["logical_path"]),
    }
    raw = canonical_release_manifest_bytes(manifest)
    (root / "release-manifest.json").write_bytes(raw)
    identity = verify_installed_release(root, hashlib.sha256(raw).hexdigest())
    return ResourceResolver.for_installed(identity)


@pytest.fixture
def harness(resources, tmp_path):
    return make_harness(resources, tmp_path)


def make_harness(resources, tmp_path, *, repository=None, clock=None):
    session = LocalSession()
    clock = clock or MutableClock()
    service = AthenaPreviewAdmissionService(
        resources,
        admission_repository=repository,
        clock=clock,
    )
    roots = WritableRoots(
        data_root=tmp_path / "user-data",
        cache_root=tmp_path / "user-cache",
        state_root=tmp_path / "user-state",
        installed_release_root=resources.identity.release_root,
    )
    app = create_app(
        release_identity=resources.identity,
        resource_resolver=resources,
        writable_roots=roots,
        local_session=session,
        capability_service=AthenaCapabilityService(
            resources, preview_admission_service=service
        ),
        preview_admission_service=service,
        origin=ORIGIN,
    )
    return TestClient(app), service, session, roots, clock


def auth(session: LocalSession, *, origin: str | None = ORIGIN) -> dict[str, str]:
    headers = {
        "X-Athena-Session": session.credential(),
        "Host": HOST,
    }
    if origin is not None:
        headers["Origin"] = origin
    return headers


def preview_body(**overrides):
    value = {
        "dates": [PREVIEW_DATE],
        "target_legs": 3,
        "target_total_odds": None,
        "bookie": "sportybet",
        "profile": "main",
        "acquire_sources": False,
        "create_share_code": False,
    }
    value.update(overrides)
    return value


def create_preview(client, session, **overrides):
    response = client.post(
        "/api/v1/run-previews",
        headers=auth(session),
        json=preview_body(**overrides),
    )
    assert response.status_code == 200, response.text
    return response.json()


def admission_body(preview, *, key="request-1", digest=None, **overrides):
    value = {
        "preview_id": preview["preview_id"],
        "execution_envelope_sha256": digest or preview["execution_envelope_sha256"],
        "idempotency_key": key,
    }
    value.update(overrides)
    return value


def test_preview_reuses_canonical_request_envelope_and_preview_bytes(harness, resources):
    client, service, session, roots, clock = harness
    result = create_preview(client, session)
    stored = service.preview_store.get(result["preview_id"], now=clock())
    assert stored is not None
    request = RunRequest.from_json_bytes(stored.request_bytes)
    envelope = ExecutionEnvelope.from_json_bytes(stored.envelope_bytes)
    preview = ExecutionPreview.from_json_bytes(stored.preview_bytes)
    assert envelope.request_bytes == stored.request_bytes
    assert hashlib.sha256(stored.request_bytes).hexdigest() == result["request_sha256"]
    assert envelope.canonical_sha256 == result["execution_envelope_sha256"]
    assert preview.canonical_sha256 == result["preview_sha256"]
    assert evaluate_execution_envelope(envelope).canonical_bytes == stored.preview_bytes
    assert request.place_wager is False
    assert request.create_share_code is False
    assert preview.requested_operations.acquire_sources is False
    assert result["dates"] == [PREVIEW_DATE]
    assert result["allowed_operations"] == list(preview.allowed_operations)
    assert result["denied_operations"] == list(preview.denied_operations)
    assert result["blockers"] == [item.to_dict() for item in preview.blockers]
    assert result["source_identity"]["kind"] == "PINNED_RELEASE_MANIFEST"
    assert result["source_identity"]["kind"] != "SIGNED_RELEASE"
    serialized = json.dumps(result)
    assert str(resources.identity.release_root) not in serialized
    for root in (roots.data_root, roots.cache_root, roots.state_root):
        assert str(root) not in serialized
        assert not root.exists()


def test_v3_pinned_manifest_identity_round_trips_without_signing_claim(harness):
    client, _, session, _, _ = harness
    result = create_preview(client, session)
    identity = SourceReleaseIdentity.from_dict(result["source_identity"])
    assert identity.schema_version == 3
    assert identity.kind == "PINNED_RELEASE_MANIFEST"
    assert identity.manifest_sha256 == identity.value
    assert identity.trust_mode == "TRUSTED_MANIFEST_SHA256_V1"


def test_delivery_and_acquisition_intent_are_not_inferred_from_profile(harness):
    client, service, session, _, clock = harness
    result = create_preview(
        client,
        session,
        profile="shadow",
        acquire_sources=False,
        create_share_code=False,
    )
    stored = service.preview_store.get(result["preview_id"], now=clock())
    assert stored is not None
    request = RunRequest.from_json_bytes(stored.request_bytes)
    envelope = ExecutionEnvelope.from_json_bytes(stored.envelope_bytes)
    assert request.authority_profile == "SHADOW"
    assert request.create_share_code is False
    assert envelope.requested_operations.acquire_sources is False
    assert envelope.requested_operations.create_share_code is False
    assert result["allowed_operations"] == []
    assert result["denied_operations"] == []


@pytest.mark.parametrize("dates", [[], [PREVIEW_DATE] * 2, ["2030-1-1"], ["2030-02-30"], ["today"], ["tomorrow"]])
def test_preview_rejects_non_concrete_duplicate_or_invalid_dates(harness, dates):
    client, _, session, _, _ = harness
    response = client.post("/api/v1/run-previews", headers=auth(session), json=preview_body(dates=dates))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_DATE"


@pytest.mark.parametrize("target_legs", [1, 50])
def test_preview_accepts_target_leg_bounds_and_one_through_seven_dates(harness, target_legs):
    client, _, session, _, _ = harness
    dates = [f"2030-01-{day:02d}" for day in range(1, 8)]
    response = client.post(
        "/api/v1/run-previews",
        headers=auth(session),
        json=preview_body(dates=dates, target_legs=target_legs),
    )
    assert response.status_code == 200
    assert response.json()["dates"] == dates
    assert response.json()["target_legs"] == target_legs


@pytest.mark.parametrize("target_legs", [0, 51, True, 3.0, "3"])
def test_preview_target_legs_is_exact_integer_one_through_fifty(harness, target_legs):
    client, _, session, _, _ = harness
    response = client.post("/api/v1/run-previews", headers=auth(session),
                           json=preview_body(target_legs=target_legs))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_INTENT"


@pytest.mark.parametrize("field", ["acquire_sources", "create_share_code"])
@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_preview_operation_intents_are_exact_booleans(harness, field, value):
    client, _, session, _, _ = harness
    response = client.post("/api/v1/run-previews", headers=auth(session),
                           json=preview_body(**{field: value}))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_INTENT"


@pytest.mark.parametrize("profile", ["MAIN", "research_shadow", "", "arbitrary"])
def test_preview_profile_uses_exact_reviewed_vocabulary(harness, profile):
    client, _, session, _, _ = harness
    response = client.post("/api/v1/run-previews", headers=auth(session),
                           json=preview_body(profile=profile))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_INTENT"


@pytest.mark.parametrize("bookie", ["OtherBook", "SPORTYBET", "sportybet/extra"])
def test_preview_rejects_unsupported_bookie(harness, bookie):
    client, _, session, _, _ = harness
    response = client.post("/api/v1/run-previews", headers=auth(session), json=preview_body(bookie=bookie))
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_BOOKIE"


def test_preview_target_total_odds_is_null_only_and_wager_is_not_a_dto_field(harness):
    client, _, session, _, _ = harness
    unsupported = client.post("/api/v1/run-previews", headers=auth(session),
                              json=preview_body(target_total_odds="2.5"))
    assert unsupported.status_code == 422
    assert unsupported.json()["code"] == "TARGET_TOTAL_ODDS_NOT_SUPPORTED"
    wager = client.post("/api/v1/run-previews", headers=auth(session),
                        json=preview_body(place_wager=False))
    assert wager.status_code == 422
    assert wager.json()["code"] == "INVALID_INTENT"


@pytest.mark.parametrize("extra", [
    {"mode": "arbitrary"},
    {"authority_manifest": {}},
    {"source_identity": {"kind": "SIGNED_RELEASE"}},
    {"stake": 1},
    {"wager": False},
    {"wallet": "x"},
])
def test_preview_rejects_extra_or_authority_replacement_fields(harness, extra):
    client, _, session, _, _ = harness
    body = preview_body(**extra)
    response = client.post("/api/v1/run-previews", headers=auth(session), json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_INTENT"


def test_preview_freezes_dates_before_midnight_and_admission_reuses_exact_bytes(resources, tmp_path):
    repo, clock = AtomicFakeAdmissionRepository(), MutableClock()
    client, service, session, _, _ = make_harness(resources, tmp_path, repository=repo, clock=clock)
    result = create_preview(client, session)
    clock.advance(timedelta(minutes=2))
    response = client.post("/api/v1/runs", headers=auth(session),
                           json=admission_body(result, key="midnight-safe"))
    assert response.status_code == 202
    assert repo.calls[0].request_bytes == service.preview_store.get(
        result["preview_id"], now=clock()
    ).request_bytes
    assert RunRequest.from_json_bytes(repo.calls[0].request_bytes).dates[0].isoformat() == PREVIEW_DATE
    assert clock().astimezone(__import__("zoneinfo").ZoneInfo("Africa/Lagos")).date().isoformat() == "2030-01-02"


def test_preview_expiry_rejects_before_repository_call(resources, tmp_path):
    repo, clock = AtomicFakeAdmissionRepository(), MutableClock()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo, clock=clock)
    result = create_preview(client, session)
    clock.advance(PREVIEW_TTL + timedelta(microseconds=1))
    response = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_EXPIRED"
    assert repo.calls == []


def test_unknown_and_expired_preview_ids_have_the_same_non_enumerating_error(harness):
    client, _, session, _, clock = harness
    result = create_preview(client, session)
    unknown = client.post("/api/v1/runs", headers=auth(session), json=admission_body(
        result, preview_id="x" * 43))
    clock.advance(PREVIEW_TTL + timedelta(seconds=1))
    expired = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert unknown.status_code == expired.status_code == 409
    assert unknown.json() == expired.json()
    assert unknown.json()["code"] == "PREVIEW_EXPIRED"


def test_digest_mismatch_rejects_before_repository_call(resources, tmp_path):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    result = create_preview(client, session)
    response = client.post("/api/v1/runs", headers=auth(session),
                           json=admission_body(result, digest="0" * 64))
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_DIGEST_MISMATCH"
    assert repo.calls == []


def test_stale_authority_rejects_before_repository_call(resources, tmp_path, monkeypatch):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    result = create_preview(client, session)
    original = AthenaRunService.authority_manifest_for
    monkeypatch.setattr(
        AthenaRunService,
        "authority_manifest_for",
        staticmethod(lambda request: replace(original(request), provider_acquisition=True)),
    )
    response = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_STALE_AUTHORITY"
    assert repo.calls == []


def test_stale_installed_manifest_pin_rejects_before_repository_call(resources, tmp_path):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    result = create_preview(client, session)
    manifest_path = resources.identity.release_root / "release-manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    response = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_STALE_AUTHORITY"
    assert repo.calls == []


def test_blocked_operation_is_reported_at_preview_and_rejected_before_repository(resources, tmp_path):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    result = create_preview(client, session, acquire_sources=True)
    assert "ACQUIRE_SOURCES" in result["denied_operations"]
    assert result["blockers"]
    response = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_BLOCKED"
    assert repo.calls == []


def test_test_repository_proves_idempotent_commit_and_single_preview_consumption(resources, tmp_path):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    first_preview = create_preview(client, session)
    first_body = admission_body(first_preview, key="same-key")
    first = client.post("/api/v1/runs", headers=auth(session), json=first_body)
    retry = client.post("/api/v1/runs", headers=auth(session), json=first_body)
    lost_response_retry = client.post("/api/v1/runs", headers=auth(session), json=first_body)
    assert first.status_code == retry.status_code == lost_response_retry.status_code == 202
    assert first.json()["admission_state"] == "admitted"
    assert retry.json()["admission_state"] == "idempotent_replay"
    assert first.json()["run_id"] == retry.json()["run_id"] == lost_response_retry.json()["run_id"]

    different_preview = create_preview(client, session)
    same_key_different_identity = client.post(
        "/api/v1/runs", headers=auth(session),
        json=admission_body(different_preview, key="same-key"),
    )
    assert same_key_different_identity.status_code == 409
    assert same_key_different_identity.json()["code"] == "IDEMPOTENCY_CONFLICT"

    different_key_same_preview = client.post(
        "/api/v1/runs", headers=auth(session),
        json=admission_body(first_preview, key="other-key"),
    )
    assert different_key_same_preview.status_code == 409
    assert different_key_same_preview.json()["code"] == "PREVIEW_ALREADY_CONSUMED_CONFLICT"


def test_invalid_idempotency_key_is_checked_after_all_preview_rechecks(resources, tmp_path):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    result = create_preview(client, session)
    response = client.post("/api/v1/runs", headers=auth(session),
                           json=admission_body(result, key="../path"))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IDEMPOTENCY_KEY"
    assert repo.calls == []


@pytest.mark.parametrize("key", ["../path", "a/b", "line\nbreak", "é", "x" * 129])
def test_idempotency_key_rejects_path_control_unicode_and_oversized_text(resources, tmp_path, key):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    result = create_preview(client, session)
    response = client.post("/api/v1/runs", headers=auth(session),
                           json=admission_body(result, key=key))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IDEMPOTENCY_KEY"
    assert repo.calls == []


@pytest.mark.parametrize("replacement", [
    {"dates": [PREVIEW_DATE]},
    {"target_legs": 4},
    {"profile": "shadow"},
    {"acquire_sources": True},
    {"create_share_code": True},
    {"place_wager": False},
    {"authority_manifest": {}},
    {"source_identity": {}},
])
def test_admission_rejects_attempt_to_replace_preview_bound_identity(resources, tmp_path, replacement):
    repo = AtomicFakeAdmissionRepository()
    client, _, session, _, _ = make_harness(resources, tmp_path, repository=repo)
    result = create_preview(client, session)
    response = client.post("/api/v1/runs", headers=auth(session),
                           json=admission_body(result, **replacement))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_INTENT"
    assert repo.calls == []


def test_supported_default_backend_fails_closed_without_fabricated_run_id(harness):
    client, _, session, _, _ = harness
    result = create_preview(client, session)
    response = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert response.status_code == 503
    assert response.json()["code"] == "DURABLE_RUN_STORE_UNAVAILABLE"
    assert "run_id" not in response.json()
    assert "traceback" not in response.text.lower()


def test_unavailable_backend_is_called_only_after_all_checks(resources, tmp_path):
    repo = CountingUnavailableRepository()
    client, _, session, _, clock = make_harness(resources, tmp_path, repository=repo, clock=MutableClock())
    result = create_preview(client, session)
    mismatch = client.post("/api/v1/runs", headers=auth(session),
                           json=admission_body(result, digest="f" * 64))
    assert mismatch.status_code == 409
    assert repo.calls == []
    valid = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert valid.status_code == 503
    assert valid.json()["code"] == "DURABLE_RUN_STORE_UNAVAILABLE"
    assert len(repo.calls) == 1
    assert repo.calls[0].request_sha256 == hashlib.sha256(repo.calls[0].request_bytes).hexdigest()


@pytest.mark.parametrize("mutation", ["session_missing", "session_wrong", "host_wrong", "origin_missing", "origin_wrong"])
def test_c5_rejects_before_preview_service_call(harness, monkeypatch, mutation):
    client, service, session, _, _ = harness
    calls = []
    original = service.preview

    def counted(**kwargs):
        calls.append(1)
        return original(**kwargs)

    monkeypatch.setattr(service, "preview", counted)
    headers = auth(session)
    if mutation == "session_missing":
        headers.pop("X-Athena-Session")
    elif mutation == "session_wrong":
        headers["X-Athena-Session"] = "0" * 64
    elif mutation == "host_wrong":
        headers["Host"] = "attacker.example"
    elif mutation == "origin_missing":
        headers.pop("Origin")
    elif mutation == "origin_wrong":
        headers["Origin"] = "http://127.0.0.1:12346"
    response = client.post("/api/v1/run-previews", headers=headers, json=preview_body())
    assert response.status_code in {401, 403}
    assert calls == []


@pytest.mark.parametrize("mutation", ["session_missing", "session_wrong", "host_wrong", "origin_missing", "origin_wrong"])
def test_c5_rejects_admission_before_repository_or_service(harness, monkeypatch, mutation):
    client, service, session, _, _ = harness
    result = create_preview(client, session)
    calls = []
    original = service.admit

    def counted(**kwargs):
        calls.append(1)
        return original(**kwargs)

    monkeypatch.setattr(service, "admit", counted)
    headers = auth(session)
    if mutation == "session_missing":
        headers.pop("X-Athena-Session")
    elif mutation == "session_wrong":
        headers["X-Athena-Session"] = "0" * 64
    elif mutation == "host_wrong":
        headers["Host"] = "attacker.example"
    elif mutation == "origin_missing":
        headers.pop("Origin")
    elif mutation == "origin_wrong":
        headers["Origin"] = "http://127.0.0.1:12346"
    response = client.post("/api/v1/runs", headers=headers, json=admission_body(result))
    assert response.status_code in {401, 403}
    assert calls == []


def test_preview_and_admission_are_provider_free_and_errors_redact_secrets(harness, monkeypatch):
    client, service, session, roots, _ = harness
    original_connect = socket.socket.connect
    external = []

    def deny_external(self, address):
        if self.family == getattr(socket, "AF_UNIX", -1) or address[0] in {"127.0.0.1", "::1"}:
            return original_connect(self, address)
        external.append(address)
        raise AssertionError("external/provider transport reached")

    monkeypatch.setattr(socket.socket, "connect", deny_external)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("process launch attempted")
    ))
    monkeypatch.setattr(AthenaRunService, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run called")))
    result = create_preview(client, session)
    error = client.post("/api/v1/runs", headers=auth(session), json=admission_body(result))
    assert error.status_code == 503
    assert external == []
    assert service.preview_source_available() is True
    assert all(not path.exists() for path in (roots.data_root, roots.cache_root, roots.state_root))

    credential = session.credential()
    release_root = str(service.resources.identity.release_root)
    monkeypatch.setattr(service, "preview", lambda **kwargs: (_ for _ in ()).throw(
        RuntimeError(f"{credential} {release_root} traceback sentinel")
    ))
    redacted = client.post("/api/v1/run-previews", headers=auth(session), json=preview_body())
    assert redacted.status_code == 503
    for secret in (credential, release_root, "traceback sentinel", "RuntimeError"):
        assert secret not in redacted.text
    assert external == []


def test_capabilities_reflect_preview_without_granting_admission(harness):
    client, _, session, _, _ = harness
    response = client.get("/api/v1/capabilities", headers=auth(session, origin=None))
    assert response.status_code == 200
    body = response.json()
    caps = {item["capability_id"]: item for item in body["capabilities"]}
    assert caps["run_preview"]["state"] == "available"
    assert "read-only" in caps["run_preview"]["reason"]
    assert caps["run_admission"]["state"] == "blocked_implementation"
    assert body["run_admission_authority"] is False


def test_process_local_preview_store_is_bounded_and_has_no_path_ids(harness):
    client, service, session, _, clock = harness
    result = create_preview(client, session)
    assert "/" not in result["preview_id"] and "\\" not in result["preview_id"]
    assert len(service.preview_store._items) == 1
    assert service.preview_store.get(result["preview_id"], now=clock()) is not None
