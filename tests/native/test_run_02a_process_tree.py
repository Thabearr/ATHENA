"""Native, provider-free process ownership and recovery tests for RUN-02A."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from runtime.worker_launcher import (
    WORKER_OFFLINE_PROBE_FILENAME,
    WORKER_PROVENANCE_FILENAME,
    WORKER_REQUEST_FILENAME,
    WorkerCommand,
    WorkerProcessHandle,
    _process_group_options,
    _spawn_process,
    persist_worker_command,
)
from domain.run_contracts import RunRequest
from services.recovery_service import RecoveryService, _is_pid_active
from services.worker_process_control import ProcessControlError, WorkerProcessControl, owner_identity


def _owner(label: str) -> dict[str, str]:
    return owner_identity(
        run_id="run-native-" + label,
        attempt_id="attempt-native-" + label,
        worker_instance_id="native-test",
        lease_token="lease-native-" + label,
    )


def test_native_crlf_checkout_keeps_e1_v284_and_v300_exact_head_predecessors(
    tmp_path, monkeypatch,
):
    """Exercise real Git LF/CRLF filters without any ancestor or network access."""
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from scripts import audit_run_01a_durable_admission as e1
    from runtime.source_identity import read_tracked_head_blob

    source_root = Path(__file__).resolve().parents[2]
    e1_sources = (
        "services/athena_capability_service.py",
        "tests/test_data_01c_app_storage.py",
    )
    a2_paths = (
        "domain/sportybet_live_event_quote_evidence.py",
        "scripts/audit_p4_4e_current_fotmob_ingest_issuer.py",
    )
    declarations = []
    for source_path in e1_sources:
        declaration = e1.FORWARD_EVOLVED_SOURCES[source_path]
        fixture_path = declaration["predecessor_fixture"]
        raw, identity = read_tracked_head_blob(
            source_root, fixture_path, verify_worktree_filtered_identity=False,
        )
        assert identity.git_blob_sha1 == declaration["predecessor_git_blob_sha1"]
        assert hashlib.sha256(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest() == declaration["predecessor_lf_sha256"]
        declarations.append(("e1", source_path, fixture_path, raw, declaration))
    for source_path in a2_paths:
        declaration = (
            a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS[source_path]
            if source_path in a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_TRANSITIONS
            else a2.E3_PASS_A_SOURCE_FORWARD_TRANSITIONS[source_path]
        )
        fixture_path = declaration["predecessor_fixture"]
        raw, identity = read_tracked_head_blob(
            source_root, fixture_path, verify_worktree_filtered_identity=False,
        )
        assert identity.git_blob_sha1 == declaration["predecessor_git_blob_sha1"]
        sha_field = declaration["predecessor_lf_source_sha256"]
        assert hashlib.sha256(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest() == sha_field
        declarations.append(("a2", source_path, fixture_path, raw, declaration))

    fixture_root = tmp_path / "shallow-text-checkout"
    fixture_root.mkdir()

    def git(*args, check=True):
        return subprocess.run(
            ["git", "-C", os.fspath(fixture_root), *args],
            check=check, capture_output=True, timeout=10,
        )

    subprocess.run([
        "git", "init", "--quiet", "--initial-branch=main", os.fspath(fixture_root),
    ], check=True, timeout=10)
    git("config", "user.name", "ATHENA F3 Regression")
    git("config", "user.email", "f3-regression@invalid.example")
    git("config", "core.autocrlf", "false")
    (fixture_root / ".gitattributes").write_text("*.py.txt text\n", encoding="ascii")
    for _kind, _source_path, fixture_path, raw, _declaration in declarations:
        target = fixture_root.joinpath(*fixture_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    git("add", "--all")
    git("commit", "--quiet", "-m", "exact historical fixtures")
    head = git("rev-parse", "HEAD").stdout.decode("ascii").strip()
    (fixture_root / ".git" / "shallow").write_text(head + "\n", encoding="ascii")
    assert git("rev-parse", "--is-shallow-repository").stdout.strip() == b"true"
    assert git("rev-list", "--count", "HEAD").stdout.strip() == b"1"
    assert git("cat-file", "-e", "HEAD^", check=False).returncode != 0
    assert "[remote " not in (fixture_root / ".git" / "config").read_text(encoding="utf-8").lower()
    assert git("status", "--porcelain").stdout == b""

    # Authenticate the LF working tree first, then switch back to this exact
    # commit from a temporary commit that changes every fixture. Git must
    # materialize each original tracked blob through core.autocrlf on checkout.
    monkeypatch.setattr(a2, "ROOT", fixture_root)

    def verify_all():
        for kind, source_path, fixture_path, raw, declaration in declarations:
            if kind == "e1":
                assert e1._predecessor_bytes(source_path, root=fixture_root) == raw
                expected_blob = declaration["predecessor_git_blob_sha1"]
                expected_lf = declaration["predecessor_lf_sha256"]
                expected_size = len(raw)
            else:
                expected_blob = declaration["predecessor_git_blob_sha1"]
                expected_lf = declaration["predecessor_lf_source_sha256"]
                expected_size = declaration["predecessor_byte_size"]
            assert a2._e3_read_exact_head_fixture(
                fixture_path, expected_blob=expected_blob, expected_lf=expected_lf,
                expected_size=expected_size, label="native CRLF predecessor test",
            ) == raw

    verify_all()
    git("checkout", "-b", "temporary-fixture-identity-change")
    for _kind, _source_path, fixture_path, raw, _declaration in declarations:
        changed = bytearray(raw)
        index = next(i for i, byte in enumerate(changed) if 97 <= byte <= 122)
        changed[index] = ord("z") if changed[index] != ord("z") else ord("y")
        fixture_root.joinpath(*fixture_path.split("/")).write_bytes(changed)
    git("add", "--all")
    git("commit", "--quiet", "-m", "temporary fixture identity change")
    git("config", "core.autocrlf", "true")
    git("config", "core.eol", "crlf")
    git("checkout", "main")
    assert git("rev-parse", "HEAD").stdout.decode("ascii").strip() == head
    assert git("rev-parse", "--is-shallow-repository").stdout.strip() == b"true"
    assert git("rev-list", "--count", "HEAD").stdout.strip() == b"1"
    assert git("cat-file", "-e", "HEAD^", check=False).returncode != 0
    assert "[remote " not in (fixture_root / ".git" / "config").read_text(encoding="utf-8").lower()
    assert git("status", "--porcelain").stdout == b""
    for _kind, _source_path, fixture_path, raw, _declaration in declarations:
        checkout = fixture_root.joinpath(*fixture_path.split("/"))
        checkout_raw = checkout.read_bytes()
        assert b"\r\n" in checkout_raw
        assert checkout_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n") == raw
    verify_all()

    # Worktree edits, missing paths, symlinks, wrong declarations/modes, and
    # missing Git objects must fail closed instead of falling back to files.
    e1_kind, e1_source, e1_fixture, e1_raw, e1_declaration = declarations[0]
    e1_path = fixture_root.joinpath(*e1_fixture.split("/"))
    tampered = bytearray(e1_path.read_bytes())
    index = next(i for i, byte in enumerate(tampered) if 97 <= byte <= 122)
    tampered[index] = ord("z") if tampered[index] != ord("z") else ord("y")
    e1_path.write_bytes(tampered)
    with pytest.raises(AssertionError):
        e1._predecessor_bytes(e1_source, root=fixture_root)
    with pytest.raises(AssertionError):
        a2._e3_read_exact_head_fixture(
            e1_fixture, expected_blob=e1_declaration["predecessor_git_blob_sha1"],
            expected_lf=e1_declaration["predecessor_lf_sha256"], expected_size=len(e1_raw),
        )
    e1_path.write_bytes(e1_raw)

    oversized = len(e1_raw) + e1_raw.count(b"\n") + 1
    e1_path.write_bytes(b"x" * oversized)
    with pytest.raises(AssertionError):
        e1._predecessor_bytes(e1_source, root=fixture_root)
    with pytest.raises(AssertionError):
        a2._e3_read_exact_head_fixture(
            e1_fixture, expected_blob=e1_declaration["predecessor_git_blob_sha1"],
            expected_lf=e1_declaration["predecessor_lf_sha256"], expected_size=len(e1_raw),
        )
    e1_path.write_bytes(e1_raw)

    symlink_target = fixture_root.joinpath(*declarations[2][2].split("/"))
    e1_path.unlink()
    try:
        e1_path.symlink_to(symlink_target)
    except OSError:
        e1_path.write_bytes(e1_raw)
    else:
        with pytest.raises(AssertionError):
            e1._predecessor_bytes(e1_source, root=fixture_root)
        with pytest.raises(AssertionError):
            a2._e3_read_exact_head_fixture(
                e1_fixture, expected_blob=e1_declaration["predecessor_git_blob_sha1"],
                expected_lf=e1_declaration["predecessor_lf_sha256"], expected_size=len(e1_raw),
            )
        e1_path.unlink()
        e1_path.write_bytes(e1_raw)

    original_lstat = Path.lstat

    def symlink_lstat(candidate):
        if candidate == e1_path:
            return SimpleNamespace(
                st_mode=stat.S_IFLNK | 0o777, st_nlink=1, st_file_attributes=0,
            )
        return original_lstat(candidate)

    monkeypatch.setattr(Path, "lstat", symlink_lstat)
    with pytest.raises(AssertionError, match="symlink or junction"):
        e1._predecessor_bytes(e1_source, root=fixture_root)
    with pytest.raises(AssertionError, match="symlink or junction"):
        a2._e3_read_exact_head_fixture(
            e1_fixture, expected_blob=e1_declaration["predecessor_git_blob_sha1"],
            expected_lf=e1_declaration["predecessor_lf_sha256"], expected_size=len(e1_raw),
        )
    monkeypatch.setattr(Path, "lstat", original_lstat)

    _a2_kind, _a2_source, a2_fixture, a2_raw, a2_declaration = declarations[2]
    a2_path = fixture_root.joinpath(*a2_fixture.split("/"))
    a2_path.unlink()
    with pytest.raises(AssertionError):
        a2._e3_read_exact_head_fixture(
            a2_fixture, expected_blob=a2_declaration["predecessor_git_blob_sha1"],
            expected_lf=a2_declaration["predecessor_lf_source_sha256"],
            expected_size=a2_declaration["predecessor_byte_size"],
        )
    a2_path.write_bytes(a2_raw)

    e1_path.unlink()
    with pytest.raises(AssertionError):
        e1._predecessor_bytes(e1_source, root=fixture_root)
    with pytest.raises(AssertionError):
        a2._e3_read_exact_head_fixture(
            e1_fixture, expected_blob=e1_declaration["predecessor_git_blob_sha1"],
            expected_lf=e1_declaration["predecessor_lf_sha256"], expected_size=len(e1_raw),
        )
    e1_path.write_bytes(e1_raw)

    with pytest.raises(AssertionError, match="HEAD mode/path/blob mismatch"):
        a2._e3_read_exact_head_fixture(
            e1_fixture, expected_blob="0" * 40,
            expected_lf=e1_declaration["predecessor_lf_sha256"], expected_size=len(e1_raw),
        )
    with pytest.raises(AssertionError, match="HEAD object size mismatch"):
        a2._e3_read_exact_head_fixture(
            a2_fixture, expected_blob=a2_declaration["predecessor_git_blob_sha1"],
            expected_lf=a2_declaration["predecessor_lf_source_sha256"],
            expected_size=a2_declaration["predecessor_byte_size"] + 1,
        )

    original_git = a2.git

    def wrong_mode_git(*args, **kwargs):
        result = original_git(*args, **kwargs)
        if args[:1] == ("ls-tree",) and args[-1:] == (e1_fixture,):
            return result.replace(b"100644 blob ", b"100755 blob ", 1)
        return result

    monkeypatch.setattr(a2, "git", wrong_mode_git)
    with pytest.raises(AssertionError, match="HEAD mode/path/blob mismatch"):
        a2._e3_read_exact_head_fixture(
            e1_fixture, expected_blob=e1_declaration["predecessor_git_blob_sha1"],
            expected_lf=e1_declaration["predecessor_lf_sha256"], expected_size=len(e1_raw),
        )
    monkeypatch.setattr(a2, "git", original_git)

    second_e1_path = declarations[1][2]
    second_e1_blob = e1.FORWARD_EVOLVED_SOURCES[declarations[1][1]]["predecessor_git_blob_sha1"]
    second_e1_object = fixture_root / ".git" / "objects" / second_e1_blob[:2] / second_e1_blob[2:]
    assert second_e1_object.is_file(), "E1 fixture object should remain loose in this bounded test repo"
    second_e1_object.unlink()
    with pytest.raises(AssertionError, match="cannot be authenticated from HEAD"):
        e1._predecessor_bytes(declarations[1][1], root=fixture_root)
    with pytest.raises(AssertionError, match="HEAD blob is unavailable"):
        a2._e3_read_exact_head_fixture(
            second_e1_path, expected_blob=second_e1_blob,
            expected_lf=e1.FORWARD_EVOLVED_SOURCES[declarations[1][1]]["predecessor_lf_sha256"],
            expected_size=len(declarations[1][3]),
        )

    blob = git("rev-parse", "HEAD:" + a2_fixture).stdout.decode("ascii").strip()
    object_path = fixture_root / ".git" / "objects" / blob[:2] / blob[2:]
    assert object_path.is_file(), "fixture object should remain a loose object in this bounded test repo"
    object_path.unlink()
    with pytest.raises(AssertionError, match="HEAD blob is unavailable"):
        a2._e3_read_exact_head_fixture(
            a2_fixture, expected_blob=a2_declaration["predecessor_git_blob_sha1"],
            expected_lf=a2_declaration["predecessor_lf_source_sha256"],
            expected_size=a2_declaration["predecessor_byte_size"],
        )


def _spawn_tree(tmp_path: Path, *, graceful: bool, parent_exits: bool = False):
    marker = tmp_path / "descendant.pid"
    handler = "getattr(signal, 'SIGBREAK', signal.SIGTERM)"
    # Poll briefly so Python can service CTRL_BREAK on Windows instead of
    # remaining inside one long sleep until the test timeout expires.
    cooperative_wait = "[time.sleep(0.02) for _ in range(3000)]"
    child_code = (
        "import signal,time; "
        + ("signal.signal(" + handler + ", lambda *_: exit(0)); " if graceful
           else "signal.signal(" + handler + ", signal.SIG_IGN); ")
        + "signal.signal(signal.SIGTERM, lambda *_: exit(0) if " + str(graceful) + " else None); "
        + cooperative_wait
    )
    parent_code = (
        "import pathlib,signal,subprocess,sys,time; "
        + ("signal.signal(" + handler + ", lambda *_: exit(0)); " if graceful
           else "signal.signal(" + handler + ", signal.SIG_IGN); ")
        + "time.sleep(0.6); "
        + "child=subprocess.Popen([sys.executable,'-c',sys.argv[2]],"
          "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        + "pathlib.Path(sys.argv[1]).write_text(str(child.pid),encoding='ascii'); "
        + ("sys.exit(0); " if parent_exits else cooperative_wait)
    )
    process = _spawn_process(
        [sys.executable, "-c", parent_code, os.fspath(marker), child_code],
        cwd=Path.cwd(), shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **_process_group_options(),
    )
    return WorkerProcessHandle(process), marker


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def _linux_process_state(pid: int) -> str | None:
    """Read the kernel state for a test-owned PID; missing means it was reaped."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
    except FileNotFoundError:
        return None
    close = raw.rfind(b")")
    if close < 0:
        raise AssertionError("malformed Linux process stat for test-owned child")
    fields = raw[close + 2:].split()
    return fields[0].decode("ascii")


def _bind(handle: WorkerProcessHandle, label: str):
    control = WorkerProcessControl(handle, _owner(label))
    locator = control.bind()
    return control, locator


@pytest.mark.parametrize("graceful", [True, False], ids=["graceful", "force"])
def test_native_process_group_owns_leader_and_descendant(tmp_path, graceful):
    handle, marker = _spawn_tree(tmp_path, graceful=graceful)
    control, locator = _bind(handle, "tree-" + str(graceful))
    try:
        assert handle.pid > 0
        assert _wait_for(marker.exists)
        assert control.state_current() == "ACTIVE"
        assert WorkerProcessControl.state(locator, control.owner) == "ACTIVE"
        assert control.request_cancel(locator) is True
        child_pid = None
        if os.name == "posix":
            child_pid = int(_wait_for(marker.exists) and marker.read_text(encoding="ascii"))
        if not graceful:
            time.sleep(0.15)
            assert control.force_terminate(locator) is True
        if graceful or os.name == "nt":
            assert _wait_for(lambda: (handle.poll() is not None)
                             and control.state_current() == "DEAD")
        else:
            # SIGKILL may leave a terminated grandchild as a zombie when the
            # test runner's init does not reap promptly. It cannot execute,
            # while the surviving process group must remain UNKNOWN to recovery.
            assert _wait_for(lambda: handle.poll() is not None
                             and _linux_process_state(child_pid) in (None, "Z", "X"))
            state = control.state_current()
            assert state in ("DEAD", "UNKNOWN")
            if state == "UNKNOWN":
                assert _linux_process_state(child_pid) in ("Z", "X")
    finally:
        if control.state_current() != "DEAD":
            try:
                control.force_terminate(locator)
            except ProcessControlError:
                pass
        control.close()


def test_native_orphan_descendant_is_not_mistaken_for_dead_owner(tmp_path):
    handle, marker = _spawn_tree(tmp_path, graceful=False, parent_exits=True)
    control, locator = _bind(handle, "orphan")
    try:
        assert _wait_for(marker.exists)
        assert handle._process.wait(timeout=5) == 0
        if os.name == "nt":
            # The persistent per-attempt Job Object proves the remaining
            # member belongs to this exact launch and can be terminated safely.
            assert control.state_current() == "ACTIVE"
            assert control.force_terminate(locator) is True
            assert _wait_for(lambda: control.state_current() == "DEAD")
        else:
            # A dead leader plus a surviving process group is ambiguous after
            # restart; recovery must block instead of killing a reused PID.
            assert control.state_current() == "UNKNOWN"
            assert RecoveryService.process_state(locator, control.owner) == "UNKNOWN"
            assert RecoveryService._is_process_active(locator) is True
            child_pid = int(marker.read_text(encoding="ascii"))
            os.kill(child_pid, signal.SIGKILL)  # exact child created by this test
    finally:
        control.close()


def test_native_authenticated_supervisor_launch_stays_in_root_process_owner(tmp_path):
    """The exact nested Current Shadow Popen remains inside the root owner."""
    marker = tmp_path / "nested-supervisor.pid"
    context_file = tmp_path / "athena-current-shadow-operation-context.json"
    output_directory = tmp_path / "current-shadow"
    wrapper = (
        "import pathlib,sys,time; "
        "from pathlib import Path; from types import SimpleNamespace; "
        "from scripts.execute_current_shadow_request import _launch_product_child; "
        "args=SimpleNamespace(target_size=3,fixture_scope='today',"
        "fixture_dates=('20300101',),output_dir=Path(sys.argv[2]),create_share_code=False); "
        "child=_launch_product_child(args,Path(sys.argv[3])); "
        "Path(sys.argv[1]).write_text(str(child.pid),encoding='ascii'); "
        "time.sleep(60)"
    )
    process = _spawn_process(
        [sys.executable, "-c", wrapper, os.fspath(marker),
         os.fspath(output_directory), os.fspath(context_file)],
        cwd=Path.cwd(), shell=False, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **_process_group_options(),
    )
    handle = WorkerProcessHandle(process)
    control = WorkerProcessControl(handle, _owner("nested-supervisor"))
    locator = control.bind()
    try:
        assert _wait_for(marker.is_file), "root worker did not spawn its blocked nested supervisor"
        child_pid = int(marker.read_text(encoding="ascii"))
        assert child_pid > 0 and _wait_for(lambda: _is_pid_active(child_pid))
        if os.name == "posix":
            assert os.getpgid(child_pid) == locator["pgid"]
            assert os.getsid(child_pid) == locator["session_id"]
        assert control.state_current() == "ACTIVE"
        assert control.force_terminate(locator) is True
        process.wait(timeout=10)
        assert _wait_for(lambda: control.state_current() in {"DEAD", "UNKNOWN"})
        if os.name == "nt":
            assert control.state_current() == "DEAD"
            assert _wait_for(lambda: not _is_pid_active(child_pid))
        else:
            assert _wait_for(lambda: _linux_process_state(child_pid) in (None, "Z", "X"))
            if control.state_current() == "UNKNOWN":
                assert _linux_process_state(child_pid) in (None, "Z", "X")
    finally:
        if control.state_current() != "DEAD":
            try:
                control.force_terminate(locator)
            except ProcessControlError:
                pass
        control.close()


def test_native_cancelled_product_probe_is_killed_before_gate_effect(tmp_path):
    """Exercise a real Windows Job Object / POSIX group at the product gate."""
    from test_run_01b_worker_lifecycle import _development_shadow_run
    from test_run_02a_recovery import _admit_run

    identity, roots, repository, item, envelope = _development_shadow_run(
        tmp_path, lambda: datetime(2030, 1, 1, 22, 59, tzinfo=timezone.utc),
    )
    run_id = _admit_run(repository, item, envelope, "native-gate-cancel")
    attempt_id, lease_token, _number = repository.claim_attempt(
        run_id, worker_instance_id="native-gate-worker",
        process_locator={"kind": "OFFLINE_TEST", "label": "native-gate"},
    )
    repository.transition_run(
        run_id, expected_version=0, state="RUNNING",
        attempt_id=attempt_id, lease_token=lease_token,
    )
    request = RunRequest.from_json_bytes(item.request_bytes)
    run_directory = roots.data_root / "runs" / run_id / request.canonical_sha256
    run_directory.mkdir(parents=True)
    (run_directory / WORKER_REQUEST_FILENAME).write_bytes(item.request_bytes)
    command = WorkerCommand(
        operation="OFFLINE_IDENTITY_PROBE", mode="offline_identity_probe",
        run_directory=run_directory, request_artifact_id=request.canonical_sha256,
        envelope_artifact_id=None, release_identity_kind=identity.identity_kind,
        release_identity_id=identity.head_commit_sha,
    )
    command_path = persist_worker_command(command)
    ready_path = tmp_path / "worker-reached-product-gate.txt"
    wrapper = (
        "import pathlib,sys; "
        "from runtime import worker_entry,worker_startup_gate; "
        "original=worker_startup_gate.wait_for_gate; "
        "worker_startup_gate.wait_for_gate=lambda command,**kwargs: "
        "(pathlib.Path(sys.argv[1]).write_text('ready',encoding='ascii'), "
        "original(command,**kwargs))[1]; "
        "raise SystemExit(worker_entry.main(sys.argv[2:]))"
    )
    process = _spawn_process(
        [sys.executable, "-c", wrapper, os.fspath(ready_path),
         "--command-file", os.fspath(command_path),
         "--development-root", os.fspath(identity.repository_root)],
        cwd=identity.repository_root,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **_process_group_options(),
    )
    handle = WorkerProcessHandle(process)
    owner = owner_identity(
        run_id=run_id, attempt_id=attempt_id,
        worker_instance_id="native-gate-worker", lease_token=lease_token,
    )
    control = WorkerProcessControl(handle, owner)
    locator = control.bind()
    repository.bind_process_locator(run_id, attempt_id, lease_token, locator)
    try:
        assert _wait_for(ready_path.is_file), "native product child did not reach its gate barrier"
        assert not (run_directory / WORKER_OFFLINE_PROBE_FILENAME).exists()
        assert not (run_directory / WORKER_PROVENANCE_FILENAME).exists()
        repository.record_cancel_intent(run_id)
        control.abort_before_start()
        process.communicate(timeout=10)
        assert repository.run_snapshot(run_id)["state"] == "CANCEL_REQUESTED"
        assert not (run_directory / WORKER_OFFLINE_PROBE_FILENAME).exists()
        assert not (run_directory / WORKER_PROVENANCE_FILENAME).exists()
        assert repository.run_snapshot(run_id)["receipt_artifact_id"] is None
    finally:
        if process.poll() is None:
            control.abort_before_start()
            process.communicate(timeout=10)
        control.close()


def test_dead_pid_is_dead_unknown_owner_is_blocked():
    assert _is_pid_active(99999999) is False
    assert RecoveryService.process_state(
        {"kind": "OFFLINE_TEST", "label": "launch-before-bind"},
        _owner("pending"),
    ) == "UNKNOWN"
    assert RecoveryService._is_process_active(
        {"kind": "UNKNOWN", "pid": 99999999}
    ) is True


def test_inaccessible_pid_is_not_classified_as_dead(monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX permission distinction is exercised only on POSIX")

    def inaccessible(_pid, _signal):
        raise PermissionError("synthetic access denial")

    monkeypatch.setattr(os, "kill", inaccessible)
    assert _is_pid_active(99999999) is True


def test_stale_process_identity_cannot_signal_or_claim_dead_owner(tmp_path):
    handle, marker = _spawn_tree(tmp_path, graceful=False)
    control, locator = _bind(handle, "stale")
    try:
        if os.name == "posix":
            reused = dict(locator)
            reused["start_ticks"] += 1
            assert WorkerProcessControl.state(reused, control.owner) == "UNKNOWN"
            assert control.request_cancel(reused) is False
            assert handle.poll() is None
        assert control.request_cancel(locator) is True
        if handle.poll() is None:
            control.force_terminate(locator)
        assert _wait_for(lambda: handle.poll() is not None)
        assert _wait_for(lambda: control.state_current() == "DEAD")
        assert RecoveryService.process_state(locator, control.owner) == "DEAD"
        changed = dict(locator)
        changed["lease_sha256"] = "0" * 64
        assert WorkerProcessControl.state(changed, control.owner) == "UNKNOWN"
    finally:
        if control.state_current() != "DEAD":
            try:
                control.force_terminate(locator)
            except ProcessControlError:
                pass
        control.close()
