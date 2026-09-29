from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from domain.run_contracts import RunRequest, canonical_json_bytes
from runtime import worker_entry, worker_launcher
from runtime.release_identity import verify_development_checkout, verify_installed_release
from runtime.resources import WritableRoots
from runtime.worker_launcher import (
    WORKER_COMMAND_FILENAME,
    WORKER_COMMAND_POLICY_ID,
    WORKER_COMMAND_SCHEMA_VERSION,
    WORKER_ENVELOPE_FILENAME,
    WORKER_OFFLINE_PROBE_FILENAME,
    WORKER_PROVENANCE_FILENAME,
    InstalledWorkerExecutable,
    WorkerCommand,
    WorkerLaunchError,
    WorkerLauncher,
    WorkerProcessHandle,
    WorkerProcessResult,
    build_offline_probe_documents,
    persist_worker_command,
)
from scripts import audit_port_02_worker_launch_boundary as port02b_audit


ROOT = Path(__file__).resolve().parents[1]


def _request(*, shadow: bool = False, create_share_code: bool = False) -> RunRequest:
    return RunRequest(
        dates=(date(2026, 9, 23),),
        target_legs=2,
        target_total_odds=None,
        bookie="sportybet",
        mode="research_shadow" if shadow else "main_application",
        authority_profile="SHADOW" if shadow else "MAIN",
        create_share_code=create_share_code,
        place_wager=False,
    )


def _stage_request(run_directory: Path, request: RunRequest) -> None:
    run_directory.mkdir(parents=True, exist_ok=True)
    (run_directory / "athena-run-request.json").write_bytes(canonical_json_bytes(request))


def _command(
    run_directory: Path,
    request: RunRequest,
    *,
    operation: str = "OFFLINE_IDENTITY_PROBE",
    kind: str = "DEVELOPMENT_CHECKOUT",
    identity_id: str | None = None,
    envelope_id: str | None = None,
) -> WorkerCommand:
    if identity_id is None:
        identity_id = (
            verify_development_checkout(ROOT).head_commit_sha
            if kind == "DEVELOPMENT_CHECKOUT"
            else "a" * 64
        )
    if run_directory.name != request.canonical_sha256:
        run_directory = run_directory / request.canonical_sha256
    _stage_request(run_directory, request)
    return WorkerCommand(
        operation=operation,
        mode=("offline_identity_probe" if operation == "OFFLINE_IDENTITY_PROBE" else "research_shadow"),
        run_directory=run_directory,
        request_artifact_id=request.canonical_sha256,
        envelope_artifact_id=envelope_id,
        release_identity_kind=kind,
        release_identity_id=identity_id,
    )


class _FakeProcess:
    def __init__(self, *, returncode=0, stdout="captured stdout", stderr="captured stderr"):
        self.pid = 1234
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.signals: list[int] = []

    def poll(self):
        return self.returncode

    def communicate(self):
        if self.returncode is None:
            self.returncode = 0
        return self.stdout, self.stderr

    def send_signal(self, value):
        self.signals.append(value)


def test_worker_command_canonical_bytes_and_explicit_absent_envelope(tmp_path: Path):
    request = _request()
    command = _command(tmp_path / "run", request)
    raw = command.canonical_bytes
    decoded = WorkerCommand.from_json_bytes(raw)
    assert decoded == command
    assert raw.endswith(b"\n")
    assert json.loads(raw)["policy_id"] == WORKER_COMMAND_POLICY_ID
    assert json.loads(raw)["schema_version"] == WORKER_COMMAND_SCHEMA_VERSION
    assert json.loads(raw)["envelope_artifact_id"] is None


def test_worker_command_rejects_duplicate_keys_and_noncanonical_json(tmp_path: Path):
    command = _command(tmp_path / "run", _request())
    raw = command.canonical_bytes
    with pytest.raises(WorkerLaunchError, match="duplicate"):
        WorkerCommand.from_json_bytes(b'{"policy_id":"x",' + raw[1:])
    with pytest.raises(WorkerLaunchError, match="not canonical"):
        WorkerCommand.from_json_bytes(raw.replace(b"{", b"{ ", 1))


@pytest.mark.parametrize(
    "operation",
    (
        "scripts.execute_current_shadow_request",
        "python -c print(1)",
        "../../module",
        "CURRENT_SHADOW_REQUEST;remove",
        "--help",
        "",
    ),
)
def test_worker_operation_is_exact_allowlist(tmp_path: Path, operation: str):
    with pytest.raises(WorkerLaunchError, match="allowlist"):
        WorkerCommand(
            operation=operation,
            mode="research_shadow",
            run_directory=tmp_path,
            request_artifact_id="a" * 64,
            envelope_artifact_id=None,
            release_identity_kind="DEVELOPMENT_CHECKOUT",
            release_identity_id="b" * 40,
        )


def test_worker_command_rejects_extra_arbitrary_argv_module_and_envelope_values(tmp_path: Path):
    command = _command(tmp_path / "run", _request())
    document = command.to_dict()
    document["module"] = "user.code"
    with pytest.raises(WorkerLaunchError, match="fields"):
        WorkerCommand.from_dict(document)
    document = command.to_dict()
    document["argv"] = ["--user-choice"]
    with pytest.raises(WorkerLaunchError, match="fields"):
        WorkerCommand.from_dict(document)
    with pytest.raises(WorkerLaunchError, match="envelope_artifact_id"):
        WorkerCommand(
            operation="OFFLINE_IDENTITY_PROBE",
            mode="offline_identity_probe",
            run_directory=command.run_directory,
            request_artifact_id=command.request_artifact_id,
            envelope_artifact_id="not-a-sha",
            release_identity_kind="DEVELOPMENT_CHECKOUT",
            release_identity_id=command.release_identity_id,
        )


def test_worker_command_requires_absolute_resolved_nontraversing_run_root(tmp_path: Path):
    request_sha = _request().canonical_sha256
    with pytest.raises(WorkerLaunchError, match="absolute"):
        WorkerCommand(
            operation="OFFLINE_IDENTITY_PROBE", mode="offline_identity_probe",
            run_directory=Path("relative-run"), request_artifact_id=request_sha,
            envelope_artifact_id=None, release_identity_kind="DEVELOPMENT_CHECKOUT",
            release_identity_id="a" * 40,
        )
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(WorkerLaunchError, match="traversal"):
        WorkerCommand(
            operation="OFFLINE_IDENTITY_PROBE", mode="offline_identity_probe",
            run_directory=run / ".." / "run", request_artifact_id=request_sha,
            envelope_artifact_id=None, release_identity_kind="DEVELOPMENT_CHECKOUT",
            release_identity_id="a" * 40,
        )


def test_worker_command_rejects_run_directory_symlink_where_supported(tmp_path: Path):
    target = tmp_path / "actual"
    target.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink is unavailable: {type(exc).__name__}")
    with pytest.raises(WorkerLaunchError, match="symlink|junction"):
        WorkerCommand(
            operation="OFFLINE_IDENTITY_PROBE", mode="offline_identity_probe",
            run_directory=link, request_artifact_id="a" * 64,
            envelope_artifact_id=None, release_identity_kind="DEVELOPMENT_CHECKOUT",
            release_identity_id="b" * 40,
        )


def test_request_artifact_is_canonical_and_sha_bound(tmp_path: Path):
    request = _request()
    command = _command(tmp_path / "run", request)
    assert worker_launcher.read_bound_request(command) == request
    path = command.run_directory / "athena-run-request.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(WorkerLaunchError, match="canonical RunRequest"):
        worker_launcher.read_bound_request(command)


def test_request_mismatch_fails_before_process_spawn(monkeypatch, tmp_path: Path):
    identity = verify_development_checkout(ROOT)
    request = _request()
    command = _command(tmp_path / "run", request, identity_id=identity.head_commit_sha)
    path = command.run_directory / "athena-run-request.json"
    other = _request(shadow=True)
    path.write_bytes(canonical_json_bytes(other))
    calls = []
    monkeypatch.setattr(worker_launcher, "_spawn_process", lambda *args, **kwargs: calls.append(args))
    launcher = WorkerLauncher.for_development(identity)
    with pytest.raises(WorkerLaunchError, match="identity"):
        launcher.launch(command)
    assert calls == []


def test_development_identity_and_exact_argv_shell_and_process_ownership(monkeypatch, tmp_path: Path):
    identity = verify_development_checkout(ROOT)
    request = _request()
    command = _command(tmp_path / "run", request, identity_id=identity.head_commit_sha)
    calls = []

    def spawn(argv, *, cwd, shell, **kwargs):
        calls.append((list(argv), cwd, shell, dict(kwargs)))
        return _FakeProcess(returncode=7, stdout="out", stderr="err")

    monkeypatch.setattr(worker_launcher, "_spawn_process", spawn)
    handle = WorkerLauncher.for_development(identity).launch(command)
    assert len(calls) == 1
    argv, cwd, shell, options = calls[0]
    assert argv == [
        sys.executable,
        "-m",
        "runtime.worker_entry",
        "--command-file",
        os.fspath(command.run_directory / WORKER_COMMAND_FILENAME),
        "--development-root",
        os.fspath(ROOT),
    ]
    assert shell is False
    assert cwd == ROOT
    assert options["stdout"] == subprocess.PIPE
    assert options["stderr"] == subprocess.PIPE
    assert options["text"] is True
    assert "timeout" not in options
    assert handle.poll() == 7
    assert handle.communicate() == WorkerProcessResult(7, "out", "err")
    assert handle.request_cancel() is False


def test_development_head_mismatch_fails_before_child(monkeypatch, tmp_path: Path):
    identity = verify_development_checkout(ROOT)
    request = _request()
    command = _command(tmp_path / "run", request, identity_id="f" * 40)
    calls = []
    monkeypatch.setattr(worker_launcher, "_spawn_process", lambda *a, **k: calls.append(a))
    with pytest.raises(WorkerLaunchError, match="identity mismatch"):
        WorkerLauncher.for_development(identity).launch(command)
    assert calls == []
    assert not (command.run_directory / WORKER_COMMAND_FILENAME).exists()


def test_command_artifact_is_exact_and_contradictory_bytes_are_not_overwritten(tmp_path: Path):
    command = _command(tmp_path / "run", _request())
    path = persist_worker_command(command)
    assert path.read_bytes() == command.canonical_bytes
    assert persist_worker_command(command) == path
    path.write_bytes(b"contradictory")
    with pytest.raises(WorkerLaunchError, match="contradictory"):
        persist_worker_command(command)


def _installed_setup(tmp_path: Path, *, request: RunRequest | None = None):
    from tests.portability.test_port_02_release_identity import build_synthetic_release

    tmp_path.mkdir(parents=True, exist_ok=True)
    release_root, trusted_sha, _manifest = build_synthetic_release(tmp_path)
    bin_root = release_root / "bin"
    bin_root.mkdir()
    exe_path = bin_root / ("athena-worker.exe" if os.name == "nt" else "athena-worker")
    executable_bytes = b"synthetic worker executable identity pin"
    exe_path.write_bytes(executable_bytes)
    identity = verify_installed_release(release_root, trusted_sha)
    roots = WritableRoots(
        data_root=tmp_path / "user-data",
        cache_root=tmp_path / "user-cache",
        state_root=tmp_path / "user-state",
        installed_release_root=release_root,
    ).ensure_created()
    request = request or _request()
    run_directory = roots.data_root / "runs" / request.canonical_sha256
    command = _command(
        run_directory,
        request,
        kind="INSTALLED_RELEASE",
        identity_id=identity.manifest_sha256,
    )
    executable = InstalledWorkerExecutable(
        path=exe_path,
        expected_sha256=hashlib.sha256(executable_bytes).hexdigest(),
    )
    return release_root, trusted_sha, identity, roots, run_directory, command, executable


def test_installed_exact_argv_hash_pin_shell_false_and_no_python_bridge(monkeypatch, tmp_path: Path):
    root, _trusted, identity, roots, run_directory, command, executable = _installed_setup(tmp_path)
    calls = []

    def spawn(argv, *, cwd, shell, **kwargs):
        calls.append((list(argv), cwd, shell, dict(kwargs)))
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(worker_launcher, "_spawn_process", spawn)
    launcher = WorkerLauncher.for_installed(identity, worker_executable=executable, writable_roots=roots)
    launcher.launch(command)
    argv, cwd, shell, options = calls[0]
    assert argv == [
        os.fspath(executable.path),
        "--command-file",
        os.fspath(run_directory / WORKER_COMMAND_FILENAME),
        "--release-root",
        os.fspath(root),
        "--trusted-manifest-sha256",
        identity.manifest_sha256,
    ]
    assert sys.executable not in argv
    assert "-m" not in argv
    assert shell is False
    assert cwd == root
    assert "timeout" not in options


@pytest.mark.parametrize("mutate", ("missing", "wrong_sha", "directory", "relative", "outside_bin"))
def test_installed_executable_invalidity_fails_before_child(monkeypatch, tmp_path: Path, mutate: str):
    root, _trusted, identity, roots, run_dir, command, good = _installed_setup(tmp_path)
    calls = []
    monkeypatch.setattr(worker_launcher, "_spawn_process", lambda *a, **k: calls.append(a))
    if mutate == "missing":
        executable = InstalledWorkerExecutable(good.path.parent / "missing.exe", good.expected_sha256)
    elif mutate == "wrong_sha":
        executable = InstalledWorkerExecutable(good.path, "0" * 64)
    elif mutate == "directory":
        executable = InstalledWorkerExecutable(good.path.parent, good.expected_sha256)
    elif mutate == "relative":
        with pytest.raises(WorkerLaunchError, match="absolute"):
            InstalledWorkerExecutable(Path("worker.exe"), good.expected_sha256)
        assert calls == []
        return
    else:
        outside = tmp_path / "outside-worker.exe"
        outside.write_bytes(good.path.read_bytes())
        executable = InstalledWorkerExecutable(outside, good.expected_sha256)
    launcher = WorkerLauncher.for_installed(identity, worker_executable=executable, writable_roots=roots)
    with pytest.raises(WorkerLaunchError):
        launcher.launch(command)
    assert calls == []
    assert not (run_dir / WORKER_COMMAND_FILENAME).exists()


def test_installed_executable_tamper_and_symlink_fail_before_child(monkeypatch, tmp_path: Path):
    root, _trusted, identity, roots, run_dir, command, executable = _installed_setup(tmp_path)
    calls = []
    monkeypatch.setattr(worker_launcher, "_spawn_process", lambda *a, **k: calls.append(a))
    executable.path.write_bytes(b"tampered")
    with pytest.raises(WorkerLaunchError, match="SHA-256"):
        WorkerLauncher.for_installed(identity, worker_executable=executable, writable_roots=roots).launch(command)
    assert calls == []
    assert not (run_dir / WORKER_COMMAND_FILENAME).exists()

    # A second independent release proves the symlink check rather than merely
    # observing the expected-digest mismatch from the preceding tamper.
    root2, _trusted2, identity2, roots2, run_dir2, command2, executable2 = _installed_setup(
        tmp_path / "second"
    )
    link = executable2.path.with_name("linked-worker.exe")
    try:
        link.symlink_to(executable2.path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlink is unavailable: {type(exc).__name__}")
    linked = InstalledWorkerExecutable(link, executable2.expected_sha256)
    with pytest.raises(WorkerLaunchError, match="symlink|junction"):
        WorkerLauncher.for_installed(identity2, worker_executable=linked, writable_roots=roots2).launch(command2)
    assert calls == []


def test_installed_release_and_writable_root_mismatch_fails_before_child(monkeypatch, tmp_path: Path):
    root, _trusted, identity, roots, run_dir, command, executable = _installed_setup(tmp_path)
    calls = []
    monkeypatch.setattr(worker_launcher, "_spawn_process", lambda *a, **k: calls.append(a))
    wrong = WorkerCommand(
        operation=command.operation, mode=command.mode, run_directory=run_dir,
        request_artifact_id=command.request_artifact_id, envelope_artifact_id=None,
        release_identity_kind="INSTALLED_RELEASE", release_identity_id="f" * 64,
    )
    with pytest.raises(WorkerLaunchError, match="identity mismatch"):
        WorkerLauncher.for_installed(identity, worker_executable=executable, writable_roots=roots).launch(wrong)
    outside_run = _command(tmp_path / "outside-run", _request(), kind="INSTALLED_RELEASE", identity_id=identity.manifest_sha256)
    with pytest.raises(WorkerLaunchError, match="writable roots"):
        WorkerLauncher.for_installed(identity, worker_executable=executable, writable_roots=roots).launch(outside_run)
    with pytest.raises(WorkerLaunchError, match="same installed release root"):
        WorkerLauncher.for_installed(
            identity,
            worker_executable=executable,
            writable_roots=WritableRoots(
                data_root=tmp_path / "other-data",
                cache_root=tmp_path / "other-cache",
                state_root=tmp_path / "other-state",
                installed_release_root=tmp_path / "other-release",
            ),
        )
    assert calls == []


def test_installed_launcher_requires_port02a_writable_roots(tmp_path: Path):
    _root, _trusted, identity, _roots, _run, _command_value, executable = _installed_setup(tmp_path)
    with pytest.raises(WorkerLaunchError, match="WritableRoots"):
        WorkerLauncher.for_installed(identity, worker_executable=executable, writable_roots=None)  # type: ignore[arg-type]


def test_process_handle_captures_and_cancels_without_retry():
    process = _FakeProcess(returncode=None)
    handle = WorkerProcessHandle(process)
    assert handle.pid == 1234
    assert handle.poll() is None
    assert handle.request_cancel() is True
    assert process.signals == [signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM]
    result = handle.communicate()
    assert result == WorkerProcessResult(0, "captured stdout", "captured stderr")


@pytest.mark.parametrize("platform_name,expected", (("nt", "creationflags"), ("posix", "start_new_session")))
def test_platform_process_group_ownership_interface(monkeypatch, platform_name: str, expected: str):
    monkeypatch.setattr(worker_launcher.os, "name", platform_name)
    options = worker_launcher._process_group_options()
    assert tuple(options) == (expected,)
    assert expected != "kill_tree"


def test_development_offline_probe_is_a_real_zero_external_process(tmp_path: Path):
    request = _request()
    identity = verify_development_checkout(ROOT)
    command = _command(
        tmp_path / "development-run",
        request,
        operation="OFFLINE_IDENTITY_PROBE",
        identity_id=identity.head_commit_sha,
    )
    result = WorkerLauncher.for_development(identity).launch(command).communicate()
    assert result.returncode == 0
    semantic = (command.run_directory / WORKER_OFFLINE_PROBE_FILENAME).read_bytes()
    provenance = json.loads((command.run_directory / WORKER_PROVENANCE_FILENAME).read_bytes())
    semantic_document = json.loads(semantic)
    assert semantic_document["provider_calls"] == 0
    assert semantic_document["delivery_calls"] == 0
    assert semantic_document["wager"] is False
    assert provenance["release_identity_kind"] == "DEVELOPMENT_CHECKOUT"


def test_installed_offline_probe_semantics_equal_development_but_provenance_differs(tmp_path: Path):
    request = _request()
    dev_identity = verify_development_checkout(ROOT)
    dev_command = _command(
        tmp_path / "development-run",
        request,
        operation="OFFLINE_IDENTITY_PROBE",
        identity_id=dev_identity.head_commit_sha,
    )
    dev_semantic, dev_provenance = build_offline_probe_documents(dev_command)
    dev_semantic_path = dev_command.run_directory / WORKER_OFFLINE_PROBE_FILENAME
    dev_provenance_path = dev_command.run_directory / WORKER_PROVENANCE_FILENAME
    dev_semantic_path.write_bytes(canonical_json_bytes(dev_semantic))
    dev_provenance_path.write_bytes(canonical_json_bytes(dev_provenance))

    root, trusted, identity, roots, run_dir, installed_command, _exe = _installed_setup(
        tmp_path / "synthetic-installed", request=request
    )
    persist_worker_command(installed_command)
    assert worker_entry.execute_worker_command(
        command_file=run_dir / WORKER_COMMAND_FILENAME,
        release_root=root,
        trusted_manifest_sha256=trusted,
    ) == 0
    installed_semantic = (run_dir / WORKER_OFFLINE_PROBE_FILENAME).read_bytes()
    installed_provenance = json.loads((run_dir / WORKER_PROVENANCE_FILENAME).read_bytes())
    assert installed_semantic == dev_semantic_path.read_bytes()
    assert hashlib.sha256(installed_semantic).hexdigest() == hashlib.sha256(dev_semantic_path.read_bytes()).hexdigest()
    assert installed_provenance["release_identity_kind"] == "INSTALLED_RELEASE"
    assert installed_provenance["release_identity_id"] == identity.manifest_sha256
    assert installed_provenance["canonical_sha256"] != dev_provenance["canonical_sha256"]


def test_port_02b_receipt_and_audit_pin_offline_probe_vector(tmp_path: Path):
    result = port02b_audit.validate_current_state()
    assert result["canonical_sha256"] == "6cb75d5e5097b64e06d9c1dca4d1a475524dc5b4cc2ad8e5e975d22fab65b2f0"
    assert result["network_provider_delivery_calls"] == 0

    request = RunRequest(
        dates=(date(2026, 9, 23),),
        target_legs=2,
        target_total_odds=None,
        bookie="sportybet",
        mode="main_application",
        authority_profile="MAIN",
        create_share_code=False,
        place_wager=False,
    )
    assert request.canonical_sha256 == port02b_audit.OFFLINE_PROBE_VECTOR["request_artifact_id"]
    run_directory = tmp_path / request.canonical_sha256
    run_directory.mkdir()
    commands = (
        WorkerCommand(
            operation="OFFLINE_IDENTITY_PROBE",
            mode="offline_identity_probe",
            run_directory=run_directory,
            request_artifact_id=request.canonical_sha256,
            envelope_artifact_id=None,
            release_identity_kind="DEVELOPMENT_CHECKOUT",
            release_identity_id=port02b_audit.BASE_MAIN_SHA,
        ),
        WorkerCommand(
            operation="OFFLINE_IDENTITY_PROBE",
            mode="offline_identity_probe",
            run_directory=run_directory,
            request_artifact_id=request.canonical_sha256,
            envelope_artifact_id=None,
            release_identity_kind="INSTALLED_RELEASE",
            release_identity_id=port02b_audit.OFFLINE_PROBE_VECTOR["installed_release_identity_id"],
        ),
    )
    documents = tuple(build_offline_probe_documents(command) for command in commands)
    semantic_payloads = tuple(canonical_json_bytes(pair[0]) for pair in documents)
    provenance_payloads = tuple(canonical_json_bytes(pair[1]) for pair in documents)
    assert semantic_payloads[0] == semantic_payloads[1]
    assert hashlib.sha256(semantic_payloads[0]).hexdigest() == port02b_audit.OFFLINE_PROBE_VECTOR["semantic_probe_sha256"]
    assert documents[0][0]["canonical_sha256"] == port02b_audit.OFFLINE_PROBE_VECTOR[
        "semantic_probe_inner_canonical_sha256"
    ]
    assert hashlib.sha256(provenance_payloads[0]).hexdigest() == port02b_audit.OFFLINE_PROBE_VECTOR[
        "development_provenance_sha256"
    ]
    assert documents[0][1]["canonical_sha256"] == port02b_audit.OFFLINE_PROBE_VECTOR[
        "development_provenance_inner_canonical_sha256"
    ]
    assert hashlib.sha256(provenance_payloads[1]).hexdigest() == port02b_audit.OFFLINE_PROBE_VECTOR[
        "installed_provenance_sha256"
    ]
    assert documents[1][1]["canonical_sha256"] == port02b_audit.OFFLINE_PROBE_VECTOR[
        "installed_provenance_inner_canonical_sha256"
    ]


def test_worker_entry_derives_current_shadow_arguments_only_from_bound_request(monkeypatch, tmp_path: Path):
    request = _request(shadow=True, create_share_code=False)
    command = _command(
        tmp_path / "run", request, operation="CURRENT_SHADOW_REQUEST"
    )
    captured = {}
    def fake_main(argv):
        captured["argv"] = list(argv)
        return 0

    fake_module = SimpleNamespace(
        WORKER_ENV="ATHENA_CURRENT_SHADOW_REQUEST_WORKER",
        main=fake_main,
    )
    monkeypatch.setitem(sys.modules, "scripts.execute_current_shadow_request", fake_module)
    monkeypatch.setenv("ATHENA_CURRENT_SHADOW_REQUEST_WORKER", "1")
    result = worker_entry._run_current_shadow(command, request)
    assert result == 0
    assert captured["argv"] == [
        "--target-size", "2", "--fixture-scope", "today", "--fixture-dates", "20260923",
        "--output-dir", os.fspath(command.run_directory / "current-shadow"),
        "--create-share-code", "false",
    ]
    assert os.environ["ATHENA_CURRENT_SHADOW_REQUEST_WORKER"] == "1"


def test_worker_entry_rejects_extra_cli_and_wrong_fixed_command_path(tmp_path: Path):
    request = _request()
    command = _command(tmp_path / "run", request)
    persist_worker_command(command)
    with pytest.raises(SystemExit):
        worker_entry.build_parser().parse_args(
            ["--command-file", os.fspath(command.run_directory / WORKER_COMMAND_FILENAME),
             "--development-root", os.fspath(ROOT), "--module", "arbitrary"]
        )
    with pytest.raises(worker_entry.WorkerEntryError, match="fixed inside"):
        (command.run_directory / "unrelated.json").write_bytes(command.canonical_bytes)
        worker_entry._read_command_file(command.run_directory / "unrelated.json")


def test_nonnull_envelope_must_be_an_actual_exact_request_bound_artifact(tmp_path: Path):
    request = _request()
    command = _command(tmp_path / "run", request, envelope_id="c" * 64)
    with pytest.raises(WorkerLaunchError, match="execution envelope artifact"):
        worker_launcher.read_bound_request(command)


def test_exact_existing_execution_envelope_may_be_bound_without_reconstruction(tmp_path: Path):
    from tests.test_execution_envelope import _envelope

    request = _request(shadow=True, create_share_code=False)
    envelope = _envelope(request=request)
    run_directory = tmp_path / "run" / request.canonical_sha256
    command = _command(
        run_directory,
        request,
        operation="CURRENT_SHADOW_REQUEST",
        envelope_id=envelope.canonical_sha256,
    )
    (command.run_directory / WORKER_ENVELOPE_FILENAME).write_bytes(envelope.canonical_bytes)
    assert worker_launcher.read_bound_request(command) == request


def test_command_and_run_directory_paths_reject_nul_and_drive_text(tmp_path: Path):
    request = _request()
    for bad in ("C:relative", str(tmp_path / "run") + "\x00bad"):
        with pytest.raises((WorkerLaunchError, ValueError, OSError)):
            WorkerCommand(
                operation="OFFLINE_IDENTITY_PROBE", mode="offline_identity_probe",
                run_directory=Path(bad), request_artifact_id=request.canonical_sha256,
                envelope_artifact_id=None, release_identity_kind="DEVELOPMENT_CHECKOUT",
                release_identity_id="a" * 40,
            )


def test_worker_audit_process_options_have_no_business_timeout():
    source = (ROOT / "runtime" / "worker_launcher.py").read_text(encoding="utf-8")
    assert "communicate(timeout=" not in source
    assert "wait(timeout=" not in source
    assert "timeout=4500" not in source
    assert "shell=False" in source
