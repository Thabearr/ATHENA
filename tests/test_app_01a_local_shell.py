"""Offline local control-plane proofs; only explicitly permitted loopback sockets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from api.app_factory import AppFactoryError, create_app
from runtime.local_session import LocalSession, LocalSessionError
from runtime.release_identity import canonical_release_manifest_bytes, verify_installed_release
from runtime.resources import ResourceResolver, WritableRoots
from services.athena_capability_service import AthenaCapabilityService
from services.athena_preview_service import AthenaPreviewAdmissionService
from services.athena_read_service import AthenaReadService
from run_desktop import LocalBackend, DesktopLaunchError, bootstrap_script, verify_health
import run_desktop

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def resources(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    records = []
    for path, role in (("ui/index.html", "UI"), ("ui/app.js", "UI"), ("ui/styles.css", "UI"),
                       ("config/architecture/component-authority-registry-v1.json", "AUTHORITY_REGISTRY")):
        payload = (ROOT / path).read_bytes()
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records.append({"logical_path": path, "payload_path": path, "role": role,
                        "byte_sha256": hashlib.sha256(payload).hexdigest(), "required": True,
                        "source_git_blob_sha1": None, "canonical_sha256": None})
    raw = canonical_release_manifest_bytes({"schema_version": 1, "policy_id": "ATHENA_INSTALLED_RELEASE_MANIFEST_V1",
        "release_id": "test-release", "build_id": "test-build", "platform_tag": "windows" if sys.platform == "win32" else "linux",
        "architecture_tag": {"amd64": "x86_64", "x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}[platform.machine().lower()],
        "closed_world_roots": ["config", "ui"], "resources": sorted(records, key=lambda r: r["logical_path"])})
    (root / "release-manifest.json").write_bytes(raw)
    return ResourceResolver.for_installed(verify_installed_release(root, hashlib.sha256(raw).hexdigest()))


@pytest.fixture
def writable_roots(resources, tmp_path):
    return WritableRoots(
        data_root=tmp_path / "user-data",
        cache_root=tmp_path / "user-cache",
        state_root=tmp_path / "user-state",
        installed_release_root=resources.identity.release_root,
    )


@pytest.fixture
def control(resources, writable_roots):
    session = LocalSession()
    preview_admission_service = AthenaPreviewAdmissionService(resources)
    app = create_app(release_identity=resources.identity, resource_resolver=resources, local_session=session,
                     writable_roots=writable_roots,
                     capability_service=AthenaCapabilityService(
                         resources, preview_admission_service=preview_admission_service),
                     preview_admission_service=preview_admission_service,
                     read_service=AthenaReadService.unavailable(),
                     origin="http://127.0.0.1:12345")
    client = TestClient(app, base_url="http://127.0.0.1:12345")
    return client, app, session


def headers(session):
    return {"X-Athena-Session": session.credential(), "X-Athena-Instance": session.instance_id,
            "X-Athena-Challenge": session.challenge}


def test_imports_are_provider_free():
    code = """import sys, importlib.abc
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self, name, *args):
  if name.startswith(('workers.', 'services.legacy_acca', 'api.athenizer', 'api.export')): raise AssertionError(name)
sys.meta_path.insert(0,Deny())
import api.server, api.app_factory, run_desktop
assert api.server._compatibility_app is None
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_session_secure_restart_and_redaction():
    first, second = LocalSession(), LocalSession()
    assert len(first.credential()) == 64
    assert first.credential() != second.credential()
    assert first.instance_id != second.instance_id
    assert first.credential() not in repr(first)
    for invalid in (None, "", "a" * 65, "é" * 64, second.credential(), "A" * 64):
        assert not first.accepts(invalid)
    old = first.credential()
    first.invalidate()
    assert not first.accepts(old)
    assert not second.accepts(old)
    with pytest.raises(LocalSessionError, match="closed"):
        first.credential()


def test_health_and_capabilities_offline(control, resources, writable_roots, monkeypatch):
    client, app, session = control
    original = socket.socket.connect
    external = []
    def permitted(self, address):
        if self.family == getattr(socket, "AF_UNIX", -1) or address[0] in {"127.0.0.1", "::1"}:
            return original(self, address)
        external.append(address)
        raise AssertionError("external/provider transport reached")
    monkeypatch.setattr(socket.socket, "connect", permitted)
    observed = client.get("/api/v1/health", headers=headers(session))
    assert observed.status_code == 200
    assert session.credential() not in observed.text
    verify_health(observed.json(), session=session, identity=resources.identity)
    capabilities = client.get("/api/v1/capabilities", headers=headers(session))
    assert capabilities.status_code == 200
    assert capabilities.json()["run_admission_authority"] is False
    assert {r["state"] for r in capabilities.json()["capabilities"]} == {
        "available", "blocked_authority", "blocked_implementation", "unavailable_unproven",
        "retained_compatibility", "deprecated_blocked"}
    assert not any("CORS" in str(m.cls) for m in app.user_middleware)
    assert client.get("/api/generate", headers=headers(session)).status_code == 404
    assert client.get("/").content == (ROOT / "ui/index.html").read_bytes()
    assert external == []
    sentinel = str(writable_roots.data_root)
    assert all(sentinel not in response.text for response in (observed, capabilities))
    assert sentinel.encode() not in client.get("/").content
    assert sentinel not in client.get("/api/v1/health").text
    assert not any(path.exists() for path in (
        writable_roots.data_root, writable_roots.cache_root, writable_roots.state_root
    ))


@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/capabilities"])
@pytest.mark.parametrize("token", [None, "", "a" * 64, "a" * 100000], ids=["missing", "empty", "wrong", "oversized"])
def test_wrong_session_is_safe(control, path, token):
    client, _, session = control
    supplied = {} if token is None else {"X-Athena-Session": token}
    response = client.get(path, headers=supplied)
    assert response.status_code == 401
    assert session.credential() not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize("host", ["attacker.example", "localhost:12345", "127.0.0.1:12346", "127.0.0.1"])
def test_host_is_exact(control, host):
    client, _, session = control
    assert client.get("/", headers={"Host": host}).status_code == 403
    assert client.get("/api/v1/health", headers={**headers(session), "Host": host}).status_code == 403


def test_mutation_origin_checked_before_service(control):
    client, app, session = control
    calls = []
    @app.post("/probe")
    def mutate():
        calls.append(1)
        return {"ok": True}
    for origin in (None, "null", "http://evil.example", "http://127.0.0.1:12346", "http://127.0.0.1:12345/"):
        supplied = headers(session)
        if origin is not None:
            supplied["Origin"] = origin
        assert client.post("/probe", headers=supplied).status_code == 403
    assert client.post("/probe", headers={"Origin": "http://127.0.0.1:12345"}).status_code == 401
    assert calls == []
    assert client.post("/probe", headers={**headers(session), "Origin": "http://127.0.0.1:12345"}).status_code == 200


def test_stale_challenge_release_and_restart(control, resources):
    client, _, session = control
    assert client.get("/api/v1/health", headers={**headers(session), "X-Athena-Challenge": "stale"}).status_code == 403
    observed = client.get("/api/v1/health", headers=headers(session)).json()
    for field in ("instance_id", "challenge", "server_proof", "release", "runtime"):
        mutated = {**observed, field: "attacker"}
        with pytest.raises(DesktopLaunchError):
            verify_health(mutated, session=session, identity=resources.identity)
    reflected = {**observed, "server_proof": session.proof("client")}
    with pytest.raises(DesktopLaunchError):
        verify_health(reflected, session=session, identity=resources.identity)
    supplied = headers(session)
    session.invalidate()
    assert client.get("/api/v1/health", headers=supplied).status_code == 401


def test_resource_corruption_fails_closed(resources):
    (resources.identity.release_root / "ui/app.js").write_bytes(b"corrupt")
    preview_admission_service = AthenaPreviewAdmissionService(resources)
    with pytest.raises(AppFactoryError, match="resources"):
        create_app(release_identity=resources.identity, resource_resolver=resources, local_session=LocalSession(),
                   writable_roots=WritableRoots(
                       data_root=resources.identity.release_root.parent / "user-data",
                       cache_root=resources.identity.release_root.parent / "user-cache",
                       state_root=resources.identity.release_root.parent / "user-state",
                       installed_release_root=resources.identity.release_root,
                   ), capability_service=AthenaCapabilityService(
                       resources, preview_admission_service=preview_admission_service),
                   preview_admission_service=preview_admission_service,
                   read_service=AthenaReadService.unavailable(),
                   origin="http://127.0.0.1:12345")


def test_invalid_dependencies_fail_closed(resources):
    preview_admission_service = AthenaPreviewAdmissionService(resources)
    kwargs = dict(release_identity=resources.identity, resource_resolver=resources, local_session=LocalSession(),
                  writable_roots=WritableRoots(
                      data_root=resources.identity.release_root.parent / "user-data",
                      cache_root=resources.identity.release_root.parent / "user-cache",
                      state_root=resources.identity.release_root.parent / "user-state",
                      installed_release_root=resources.identity.release_root,
                  ),
                  capability_service=AthenaCapabilityService(
                      resources, preview_admission_service=preview_admission_service),
                  preview_admission_service=preview_admission_service,
                  read_service=AthenaReadService.unavailable(),
                  origin="http://127.0.0.1:12345")
    for field, value in (("release_identity", object()), ("resource_resolver", object()),
                         ("writable_roots", object()),
                         ("local_session", object()), ("capability_service", object()),
                         ("read_service", object()),
                         ("origin", "http://localhost:12345"), ("origin", "http://127.0.0.1:99999")):
        with pytest.raises(AppFactoryError):
            create_app(**{**kwargs, field: value})


def test_factory_requires_explicit_data_root_and_rejects_resource_overlap(resources, writable_roots):
    preview_admission_service = AthenaPreviewAdmissionService(resources)
    kwargs = dict(release_identity=resources.identity, resource_resolver=resources,
                  local_session=LocalSession(), capability_service=AthenaCapabilityService(
                      resources, preview_admission_service=preview_admission_service),
                  preview_admission_service=preview_admission_service,
                  read_service=AthenaReadService.unavailable(),
                  origin="http://127.0.0.1:12345")
    with pytest.raises(TypeError):
        create_app(**kwargs)
    with pytest.raises(AppFactoryError, match="invalid trusted application dependencies"):
        create_app(**{**kwargs, "writable_roots": object()})

    inside_release = WritableRoots(
        data_root=resources.identity.release_root / "application-data",
        cache_root=resources.identity.release_root.parent / "other-cache",
        state_root=resources.identity.release_root.parent / "other-state",
    )
    with pytest.raises(AppFactoryError) as rejected:
        create_app(**{**kwargs, "writable_roots": inside_release})
    assert str(rejected.value) == "invalid trusted application dependencies"
    assert str(resources.identity.release_root) not in str(rejected.value)

    app = create_app(**{**kwargs, "writable_roots": writable_roots})
    assert app.state.writable_roots == writable_roots


def test_factory_keeps_explicit_data_root_independent_of_cwd(resources, writable_roots, monkeypatch, tmp_path):
    other_cwd = tmp_path / "unrelated-working-directory"
    other_cwd.mkdir()
    monkeypatch.chdir(ROOT)
    preview_admission_service = AthenaPreviewAdmissionService(resources)
    app = create_app(release_identity=resources.identity, resource_resolver=resources,
                     writable_roots=writable_roots, local_session=LocalSession(),
                     capability_service=AthenaCapabilityService(
                         resources, preview_admission_service=preview_admission_service),
                     preview_admission_service=preview_admission_service,
                     read_service=AthenaReadService.unavailable(),
                     origin="http://127.0.0.1:12345")
    monkeypatch.chdir(other_cwd)
    assert app.state.writable_roots.data_root == writable_roots.data_root
    assert app.state.writable_roots.data_root not in (ROOT, other_cwd)
    assert not writable_roots.data_root.exists()


def test_launcher_resolves_roots_from_os_user_locations_not_cwd(resources, monkeypatch, tmp_path):
    other_cwd = tmp_path / "different-launch-directory"
    other_cwd.mkdir()
    if sys.platform == "win32":
        local_app_data = tmp_path / "user-profile" / "AppData" / "Local"
        monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
        expected_data = local_app_data / "ATHENA" / "data"
    elif sys.platform.startswith("linux"):
        home = tmp_path / "user-profile"
        monkeypatch.setenv("HOME", str(home))
        for name in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            monkeypatch.delenv(name, raising=False)
        expected_data = home / ".local" / "share" / "athena"
    else:
        pytest.skip("supported launcher platforms are covered by PORT-02C")

    monkeypatch.chdir(ROOT)
    first = run_desktop.resolve_writable_roots(resources)
    monkeypatch.chdir(other_cwd)
    second = run_desktop.resolve_writable_roots(resources)
    assert first.data_root == second.data_root == expected_data.resolve()
    assert first.installed_release_root == resources.identity.release_root
    assert not first.data_root.exists()


def test_handshake_never_discloses_credential_and_has_distinct_roles(control, resources):
    client, _, session = control
    supplied = {"X-Athena-Handshake": session.proof("client"), "X-Athena-Instance": session.instance_id,
                "X-Athena-Challenge": session.challenge}
    result = client.get("/api/v1/health", headers=supplied)
    assert result.status_code == 200
    assert session.credential() not in result.text
    assert session.proof("client") != result.json()["server_proof"]
    verify_health(result.json(), session=session, identity=resources.identity)
    assert client.get("/api/v1/capabilities", headers=supplied).status_code == 401
    assert client.get("/api/v1/health", headers={**supplied, "X-Athena-Handshake": session.proof("server")}).status_code == 401
    assert not LocalSession().accepts_handshake(session.proof("client"))


def test_capabilities_reverify_contract_and_never_use_weights(control, resources):
    client, _, session = control
    before = client.get("/api/v1/capabilities", headers=headers(session)).json()
    (resources.identity.release_root / "model_weights.json").write_bytes(b"{}")
    assert client.get("/api/v1/capabilities", headers=headers(session)).json() == before
    (resources.identity.release_root / "config/architecture/component-authority-registry-v1.json").write_bytes(b"{}")
    assert client.get("/api/v1/capabilities", headers=headers(session)).status_code == 503


def test_owned_ephemeral_listener_offline(resources, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    original = socket.socket.connect
    calls = []
    def permitted(self, address):
        assert address[0] == "127.0.0.1", "external transport denied"
        calls.append(address)
        return original(self, address)
    monkeypatch.setattr(socket.socket, "connect", permitted)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("installed runtime called subprocess/Git"))
    if sys.platform.startswith("linux"):
        # A2's pytest seccomp policy denies every INET socket, including
        # loopback. Keep that guard intact and prove launch fails closed.
        # Real installed loopback ownership/handshake runs in the separate
        # automatic PORT-02C native smoke lane; API tests here use ASGI.
        import errno
        with pytest.raises(PermissionError) as rejected:
            LocalBackend(resources)
        assert rejected.value.errno == errno.EPERM
        assert run_desktop.main([
            "--port02c-smoke", "--release-root", str(resources.identity.release_root),
            "--trusted-manifest-sha256", resources.identity.manifest_sha256,
        ]) == 1
        assert calls == []
        return
    backend = LocalBackend(resources)
    try:
        assert backend.listener.getsockname()[0] == "127.0.0.1"
        assert backend.listener.getsockname()[1] != 0
        backend.start()
        assert calls
        assert any(address[1] == backend.listener.getsockname()[1] for address in calls)
    finally:
        backend.close()
    assert not backend.thread.is_alive()


def test_bootstrap_has_no_python_bridge_or_persistent_secret():
    source = (ROOT / "run_desktop.py").read_text(encoding="utf-8")
    js = (ROOT / "ui/app.js").read_text(encoding="utf-8")
    assert "js_api=None" in source and ".expose(" not in source
    assert "8500" not in source + js
    assert "localStorage" not in js and "sessionStorage" not in js
    assert "/api/fixtures" not in js and "/api/generate" not in js
    session = LocalSession()
    script = bootstrap_script(origin="http://127.0.0.1:12345", session=session)
    assert "location.origin!==" in script
    assert script.index("location.origin") < script.index(session.credential())


def test_malicious_responder_never_loads_ui(monkeypatch):
    calls = []
    class Rejected:
        def __init__(self, resources):
            calls.append("construct")
        def start(self):
            calls.append("challenge")
            raise DesktopLaunchError("wrong release")
        def close(self):
            calls.append("close")
    monkeypatch.setattr(run_desktop, "resolve_resources", lambda args: object())
    monkeypatch.setattr(run_desktop, "LocalBackend", Rejected)
    assert run_desktop.main([]) == 1
    assert calls == ["construct", "challenge", "close"]


def test_shutdown_failure_does_not_report_smoke_success(monkeypatch):
    class RejectedShutdown:
        def __init__(self, resources):
            pass
        def start(self):
            pass
        def close(self):
            raise DesktopLaunchError("local backend did not stop")
    monkeypatch.setattr(run_desktop, "resolve_resources", lambda args: object())
    monkeypatch.setattr(run_desktop, "LocalBackend", RejectedShutdown)
    assert run_desktop.main(["--port02c-smoke"]) == 1


def test_missing_ui_and_unsupported_platform_fail_closed(resources, monkeypatch):
    preview_admission_service = AthenaPreviewAdmissionService(resources)
    kwargs = dict(release_identity=resources.identity, resource_resolver=resources, local_session=LocalSession(),
                  writable_roots=WritableRoots(
                      data_root=resources.identity.release_root.parent / "user-data",
                      cache_root=resources.identity.release_root.parent / "user-cache",
                      state_root=resources.identity.release_root.parent / "user-state",
                      installed_release_root=resources.identity.release_root,
                  ),
                  capability_service=AthenaCapabilityService(
                      resources, preview_admission_service=preview_admission_service),
                  preview_admission_service=preview_admission_service,
                  read_service=AthenaReadService.unavailable(),
                  origin="http://127.0.0.1:12345")
    with monkeypatch.context() as change:
        change.setattr(sys, "platform", "darwin")
        with pytest.raises(AppFactoryError, match="unsupported"):
            create_app(**kwargs)
    with monkeypatch.context() as change:
        change.setattr(sys, "version_info", (3, 13))
        with pytest.raises(AppFactoryError, match="interpreter"):
            create_app(**kwargs)
    (resources.identity.release_root / "ui/index.html").unlink()
    with pytest.raises(AppFactoryError, match="resources"):
        create_app(**kwargs)


def test_existing_frozen_smoke_requires_out_of_band_pin(resources, monkeypatch):
    root = resources.identity.release_root
    exe = root / "bin/athena-bundle/athena-shell.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"synthetic executable")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setenv("MANIFEST_SHA", resources.identity.manifest_sha256)
    result = run_desktop.resolve_resources(run_desktop.parse_args(["--port02c-smoke"]))
    assert result.identity.manifest_sha256 == resources.identity.manifest_sha256
    with pytest.raises(DesktopLaunchError):
        run_desktop.resolve_resources(run_desktop.parse_args([]))
    monkeypatch.delenv("MANIFEST_SHA")
    with pytest.raises(DesktopLaunchError):
        run_desktop.resolve_resources(run_desktop.parse_args(["--port02c-smoke"]))


def test_b7_historical_generation_never_falls_back_from_broken_current(monkeypatch):
    from scripts import audit_core_01d_win_either_half_trigger_authority_b7 as b7
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    def rejected():
        raise AssertionError("broken current generation")
    monkeypatch.setattr(boundary, "authenticate_inventory", rejected)
    with pytest.raises(AssertionError, match="broken current"):
        b7.authenticated_historical_a2_v9()


def test_app_receipt_matches_exact_source():
    from scripts import audit_app_01a_local_shell as audit
    receipt = audit.validate()
    assert receipt["source_review_counter_open"] == "2/5"
    assert receipt["authority"]["run_admission"] is False
    assert receipt["contracts"]["application_data_root"] == (
        "PORT_02A_WRITABLE_ROOTS_EXACT_TYPE_SEPARATE_FROM_RESOURCES"
    )
    assert "runtime/resources.py" in receipt["source_identities"]
    assert receipt["a2_inventory"]["path"] == audit.INVENTORY
    for name, original in (("ui/legacy-index.html", "ui/index.html"), ("ui/legacy-app.js", "ui/app.js")):
        digest = hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert digest == receipt["base_identities"][original]["sha256"]


def test_historical_app_projection_rejects_broken_current(monkeypatch):
    from scripts import audit_app_01a_local_shell as audit
    from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
    def rejected():
        raise AssertionError("broken current generation")
    monkeypatch.setattr(boundary, "authenticate_inventory", rejected)
    with pytest.raises(AssertionError, match="broken current"):
        audit.historical_runtime_payload("run_desktop.py")
    with pytest.raises(AssertionError, match="broken current"):
        audit.historical_tree_projection(b"")


def test_historical_runtime_payload_is_exact_pinned_blob(monkeypatch):
    import base64
    from copy import deepcopy
    from scripts import audit_app_01a_local_shell as audit
    document = deepcopy(audit.validate())
    document["historical_runtime_payloads"]["run_desktop.py"] = base64.b64encode(b"tamper").decode()
    monkeypatch.setattr(audit, "authenticated_historical_paths", lambda: (set(), document))
    with pytest.raises(ValueError, match="payload identity"):
        audit.historical_runtime_payload("run_desktop.py")
    with pytest.raises(ValueError, match="outside"):
        audit.historical_runtime_payload("runtime/worker_launcher.py")
