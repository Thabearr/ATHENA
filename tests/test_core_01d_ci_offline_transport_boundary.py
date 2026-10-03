"""Non-networking adversarial probes of the test-only boundary."""
from __future__ import annotations

import os
import runpy
from pathlib import Path
import socket
import smtplib
import subprocess
import sys
import urllib.request

import pytest
import offline_transport as boundary


@pytest.mark.parametrize("operation", ["connect", "connect_ex", "sendto"])
def test_denial_precedes_original_socket_tripwire(monkeypatch, operation):
    def tripwire(*args):
        pytest.fail("UNGUARDED_EXTERNAL_CONNECT_REACHED")
    monkeypatch.setattr(boundary, "_original_" + operation, tripwire)
    class SocketShape:
        family = socket.AF_INET
    with pytest.raises(boundary.OfflineTransportDenied):
        getattr(boundary, "guarded_" + operation)(SocketShape(), ("192.0.2.1", 9))


@pytest.mark.parametrize("operation", ["connect", "connect_ex"])
def test_parent_socket_denies_before_transport(operation):
    with pytest.raises((boundary.OfflineTransportDenied, PermissionError)):
        with socket.socket() as sock:
            getattr(sock, operation)(("192.0.2.1", 9))


def test_datagram_and_raw_creation_cannot_bypass_with_sendmsg():
    with pytest.raises(boundary.OfflineTransportDenied):
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


@pytest.mark.parametrize("host", ["example.invalid", "192.0.2.1", "localhost"])
def test_dns_and_create_connection_fail_before_resolution(host):
    with pytest.raises(boundary.OfflineTransportDenied):
        socket.create_connection((host, 9))


def test_http_and_smtp_denied():
    with pytest.raises((boundary.OfflineTransportDenied, urllib.error.URLError)) as error:
        urllib.request.urlopen("http://192.0.2.1:9/")
    assert "PYTEST_EXTERNAL_TRANSPORT_DENIED" in str(error.value)
    with pytest.raises(boundary.OfflineTransportDenied):
        smtplib.SMTP("192.0.2.1", 9)


@pytest.mark.parametrize("library", ["requests", "httpx"])
def test_common_http_clients_use_denied_low_level_transport(library):
    client = pytest.importorskip(library)
    with pytest.raises(Exception) as error:
        client.get("http://192.0.2.1:9/", timeout=1)
    assert "PYTEST_EXTERNAL_TRANSPORT_DENIED" in str(error.value)


def test_child_python_inherits_guard():
    completed = subprocess.run([
        sys.executable, "-c",
        "import socket; socket.create_connection(('192.0.2.1', 9))",
    ], capture_output=True)
    assert completed.returncode != 0
    assert b"PYTEST_EXTERNAL_TRANSPORT_DENIED" in completed.stderr


@pytest.mark.parametrize("flag", ["-S", "-I", "-E", "-sS", "-X", "-W", "-Xpresite=unreviewed", "--check-hash-based-pycs"])
def test_child_bootstrap_bypass_is_denied_before_spawn(monkeypatch, flag):
    monkeypatch.setattr(boundary, "_original_popen", lambda *a, **k: pytest.fail("UNGUARDED_PROCESS_REACHED"))
    with pytest.raises(boundary.OfflineTransportDenied):
        subprocess.run([sys.executable, flag, "-c", "pass"])


def test_stripping_child_environment_is_not_an_opt_out():
    completed = subprocess.run([sys.executable, "-c",
        "import socket; socket.create_connection(('192.0.2.1',9))"], env={}, capture_output=True)
    assert completed.returncode != 0
    assert b"PYTEST_EXTERNAL_TRANSPORT_DENIED" in completed.stderr


def test_direct_original_popen_cannot_strip_child_bootstrap():
    with pytest.raises(boundary.OfflineTransportDenied):
        boundary._original_popen([sys.executable, "-c", "pass"], env={})


@pytest.mark.parametrize("command", [
    ["curl", "http://example.invalid"], ["gh", "api", "user"],
    ["git", "fetch"], ["git", "pull"], ["git", "push"],
    ["git", "clone", "https://example.invalid/repo"],
    ["git", "ls-remote"], ["git", "submodule", "update"],
    ["sh", "-c", "curl http://example.invalid"],
])
def test_external_process_denied_before_popen(monkeypatch, command):
    monkeypatch.setattr(boundary, "_original_popen", lambda *a, **k: pytest.fail("UNGUARDED_PROCESS_REACHED"))
    with pytest.raises(boundary.OfflineTransportDenied):
        subprocess.run(command)


def test_local_git_is_still_available():
    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, check=True)
    assert result.stdout.strip() == b"true"


@pytest.mark.parametrize("arguments", [["git", "commit"], ["git", "log", "--format=%G?"], ["git", "config", "core.editor", "curl"]])
def test_git_native_helper_arguments_fail_before_execution(arguments):
    with pytest.raises(boundary.OfflineTransportDenied):
        boundary.local_git_arguments(arguments)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.255.1.2", "::1"])
def test_only_literal_loopback_is_permitted(host):
    boundary.check_address((host, 9))


def test_environment_cannot_enable_transport(monkeypatch):
    monkeypatch.setenv("ATHENA_ALLOW_NETWORK", "1")
    with pytest.raises(boundary.OfflineTransportDenied):
        boundary.check_address(("192.0.2.1", 9))


def test_application_does_not_import_test_guard():
    root = Path(__file__).resolve().parents[1]
    for folder in ("domain", "runtime", "services", "providers", "api"):
        for path in (root / folder).rglob("*.py"):
            assert "import offline_transport" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("invocation, activated", [(["python", "-m", "pytest"], True), (["python", "-u", "-m", "pytest"], True), (["python", "build_acca.py"], False), (["python", "build_acca.py", "-m", "pytest"], False)])
def test_startup_is_pytest_only(monkeypatch, invocation, activated):
    calls = []
    monkeypatch.setattr(sys, "orig_argv", invocation)
    monkeypatch.setattr(boundary, "install", lambda: calls.append("installed"))
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "sitecustomize.py"))
    assert bool(calls) is activated


def test_patchable_guard_source_drift_is_denied_before_import(monkeypatch):
    calls = []
    original = Path.read_bytes
    def altered(path):
        if path.name == "offline_transport.py":
            return b"def install(): pass\n"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", altered)
    monkeypatch.setattr(sys, "orig_argv", ["python", "-m", "pytest"])
    monkeypatch.setattr(boundary, "install", lambda: calls.append("UNGUARDED_INSTALL"))
    with pytest.raises(SystemExit, match="failed to activate"):
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "sitecustomize.py"))
    assert calls == []


def test_local_git_native_filter_is_not_a_hidden_transport(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    config = tmp_path / ".git" / "config"
    with config.open("a", encoding="utf-8") as stream:
        stream.write('\n[filter "unreviewed"]\n\tclean = curl http://example.invalid\n')
    with pytest.raises(boundary.OfflineTransportDenied, match="native filter"):
        subprocess.run(["git", "-C", str(tmp_path), "status"], capture_output=True)


def test_renamed_transport_executable_cannot_impersonate_git(tmp_path, monkeypatch):
    fake = tmp_path / ("git.exe" if boundary.WINDOWS_HOST else "git")
    fake.write_bytes(b"not a reviewed Git executable")
    monkeypatch.setattr(boundary, "_original_popen", lambda *a, **k: pytest.fail("UNGUARDED_PROCESS_REACHED"))
    with pytest.raises(boundary.OfflineTransportDenied):
        subprocess.run([str(fake), "status"])


def test_kernel_program_closes_native_and_alternate_abi_paths():
    import offline_linux as kernel
    for number in kernel.DENIED_SYSCALLS:
        assert kernel.evaluate(number) == kernel.DENY
    for number in kernel.SOCKET_CALLS:
        for family in (0, 2, 10, 16, 17, 40):
            assert kernel.evaluate(number, family=family) == kernel.DENY
        assert kernel.evaluate(number, family=1) == kernel.ALLOW
    assert kernel.evaluate(0) == kernel.ALLOW  # read on anonymous local pipes
    assert kernel.evaluate(0, arch=0) == kernel.DENY
    assert kernel.evaluate(kernel.X32_SYSCALL_BIT | 41) == kernel.DENY
    assert kernel.evaluate(kernel.REVIEWED_ABI_CEILING + 1) == kernel.DENY
    assert all(kernel.evaluate(number) == kernel.DENY for number in range(512, 548))
    assert kernel.evaluate(-1) == kernel.DENY
    assert kernel.evaluate(-0x40000001) == kernel.DENY
    assert kernel.evaluate(44, destination=0) == kernel.ALLOW
    assert kernel.evaluate(44, destination=1) == kernel.DENY
    assert kernel.evaluate(44, destination=1 << 32) == kernel.DENY


@pytest.mark.skipif(sys.platform != "linux", reason="target workflow kernel proof runs on Hosted Ubuntu")
def test_native_kernel_socket_denial_is_independent_of_python_monkeypatches():
    import errno
    import offline_linux as kernel
    assert kernel._active
    assert kernel.native_socket_probe() == errno.EPERM
    left, right = socket.socketpair()
    with left, right:
        assert left.send(b"local-self-pipe") == 15
        assert right.recv(15) == b"local-self-pipe"


@pytest.mark.skipif(sys.platform != "linux", reason="target workflow kernel proof runs on Hosted Ubuntu")
def test_child_cannot_remove_kernel_filter():
    import ctypes
    import errno
    import offline_linux as kernel

    # Fork proof has NO sitecustomize reinstall: the inherited kernel boundary
    # itself must deny both removal and native INET socket creation.
    reader, writer = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reader)
        try:
            prctl = ctypes.CDLL(None, use_errno=True).prctl
            removal_denied = prctl(22, 0, 0, 0, 0) == -1
            inherited_denial = kernel.native_socket_probe() == errno.EPERM
            os.write(writer, b"inherited-denial" if removal_denied and inherited_denial else b"FAIL")
        finally:
            os._exit(0)
    os.close(writer)
    try:
        proof = os.read(reader, 64)
    finally:
        os.close(reader)
    _, status = os.waitpid(pid, 0)
    assert status == 0 and proof == b"inherited-denial"

    # Exec proof separately authenticates the ordinary child bootstrap.
    result = subprocess.run([sys.executable, "-c",
        "import offline_linux as k; import errno; assert k.native_socket_probe()==errno.EPERM"], capture_output=True)
    assert result.returncode == 0, result.stderr
