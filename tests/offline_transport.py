"""Test-only external transport denial; never imported by application code.

This is an audit-hook boundary, not a security sandbox for arbitrary native code.
The source auditor must keep native-code and process obligations explicit.
"""
from __future__ import annotations

import ipaddress
from contextvars import ContextVar
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys

FilesystemPath = type(Path())
WINDOWS_HOST = os.name == "nt"
LINUX_HOST = sys.platform == "linux"
GIT_EXECUTABLE = shutil.which("git")
UNAME_EXECUTABLE = shutil.which("uname") if LINUX_HOST else None

class OfflineTransportDenied(PermissionError):
    """A pytest transport or unclassified process was denied before execution."""


BOOTSTRAP = Path(__file__).resolve().parent / "_offline_bootstrap"
LOCAL_GIT_COMMANDS = frozenset({
    "rev-parse", "ls-tree", "ls-files", "show", "cat-file", "hash-object",
    "status", "diff", "diff-tree", "merge-base", "rev-list", "log", "config",
    "init", "add", "commit", "check-attr", "check-ignore", "write-tree",
})
_installed = False
_original_popen = subprocess.Popen
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_sendto = socket.socket.sendto
_audited_argv = ContextVar("pytest_offline_exact_argv", default=None)
GIT_PREFIX = ("--no-pager", "-c", "core.hooksPath=" + str(BOOTSTRAP),
              "-c", "core.fsmonitor=false", "-c", "protocol.allow=never",
              "-c", "submodule.recurse=false", "-c", "commit.gpgSign=false",
              "-c", "log.showSignature=false")
SAFE_GIT_CONFIG = frozenset({"core.autocrlf", "core.eol", "core.safecrlf", "core.ignorecase", "core.filemode", "core.symlinks", "user.name", "user.email"})
NATIVE_LOCAL_SYMBOLS = frozenset({
    "CreateFileW", "FlushFileBuffers", "CloseHandle", "GetLastError",
    "GetNativeSystemInfo", "GetSystemInfo", "dl_iterate_phdr",
    "GetStdHandle", "GetConsoleScreenBufferInfo", "SetConsoleTextAttribute",
    "SetConsoleCursorPosition", "FillConsoleOutputCharacterA",
    "FillConsoleOutputAttribute", "SetConsoleTitleW", "GetConsoleMode", "SetConsoleMode",
    "ReadConsoleW", "WriteConsoleW", "PyObject_GetBuffer", "PyBuffer_Release",
    "GetCommandLineW", "CommandLineToArgvW", "LocalFree",
    "FillConsoleOutputCharacterW", "GetConsoleCursorInfo", "SetConsoleCursorInfo",
    "LoadStringW",
})
NATIVE_TRANSPORT_IMPORTS = frozenset({"curl_cffi", "_cffi_backend", "playwright", "selenium", "paramiko"})


def command_name(value: object) -> str:
    return FilesystemPath(os.fsdecode(value)).name.lower()


def python_executable(value: object) -> bool:
    resolved = shutil.which(os.fsdecode(value))
    if resolved and os.path.normcase(os.path.realpath(resolved)) == os.path.normcase(os.path.realpath(sys.executable)):
        return True
    # The existing installed-mode logic test uses an exact Python shebang;
    # native frozen executables are NOT covered or permitted by this boundary.
    path = FilesystemPath(os.fsdecode(value))
    if path.is_file():
        with path.open("rb") as source:
            return source.readline().rstrip(b"\r\n") == ("#!" + sys.executable).encode()
    return False


def local_git_arguments(args: list[str]) -> list[str]:
    remaining = args[1:]
    while len(remaining) >= 2 and remaining[0] == "-c":
        if remaining[1].split("=", 1)[0] not in SAFE_GIT_CONFIG:
            deny("unreviewed Git command configuration")
        remaining = remaining[2:]
    while remaining and remaining[0] in {"-C", "--git-dir", "--work-tree"}:
        if len(remaining) < 3:
            deny("malformed local Git invocation")
        remaining = remaining[2:]
    if not remaining or remaining[0] not in LOCAL_GIT_COMMANDS:
        deny("Git command is not in the source-local allowlist")
    if any(arg in {"--textconv", "--ext-diff", "--template", "--exec-path", "--upload-pack", "--receive-pack", "--show-signature", "--gpg-sign", "-S"}
           or arg.startswith(("--template=", "--exec-path=", "--upload-pack=", "--receive-pack="))
           or "%G" in arg
           for arg in remaining[1:]):
        deny("Git argument enables native child execution")
    if remaining[0] == "commit" and not any(
        arg in {"-m", "--message", "-F", "--file"} or arg.startswith(("--message=", "--file=", "-am"))
        for arg in remaining[1:]
    ):
        deny("Git commit requires an explicit noninteractive message")
    if remaining[0] == "config":
        unsafe = ("filter.", "alias.", "include.", "includeif.", "core.hook", "core.fsmonitor", "core.ssh", "core.editor", "sequence.editor", "init.template", "diff.", "gpg.", "credential.")
        if any(arg.lower().startswith(unsafe) for arg in remaining[1:]):
            deny("Git configuration could enable native child execution")
    return remaining


def prepare_process(args, kwargs):
    if kwargs.get("shell") or kwargs.get("executable") is not None:
        deny("shell or executable override is unclassified")
    if not isinstance(args, (list, tuple)) or not args:
        deny("unclassifiable process arguments")
    args = [os.fsdecode(arg) for arg in args]
    if LINUX_HOST and command_name(args[0]) == "uname":
        candidate = shutil.which(args[0])
        if args[1:] != ["-p"] or not UNAME_EXECUTABLE or not candidate or os.path.realpath(candidate) != os.path.realpath(UNAME_EXECUTABLE):
            deny("unreviewed host-introspection command")
        # Python 3.12 platform._Processor.from_subprocess uses this exact query.
        args[0] = UNAME_EXECUTABLE
    elif command_name(args[0]) in {"git", "git.exe"}:
        candidate = shutil.which(args[0])
        if not GIT_EXECUTABLE or not candidate or os.path.normcase(os.path.realpath(candidate)) != os.path.normcase(os.path.realpath(GIT_EXECUTABLE)):
            deny("Git executable does not match trusted startup discovery")
        args[0] = GIT_EXECUTABLE
        local_git_arguments(args)
        env = dict(os.environ if kwargs.get("env") is None else kwargs["env"])
        for key in list(env):
            if key.startswith("GIT_CONFIG") or key in {"GIT_EXTERNAL_DIFF", "GIT_TEMPLATE_DIR", "GIT_EXEC_PATH"}:
                del env[key]
        # Preserve reviewed checkout EOL configuration. Configuration is read
        # below before allowing any command that could use a native helper.
        env["GIT_TEMPLATE_DIR"] = str(BOOTSTRAP)
        kwargs["env"] = env
        # Inspect local filter definitions without invoking any filter. Git's
        # EOL filters remain intact; arbitrary native filters fail closed.
        cwd_args = []
        if args[1:2] == ["-C"]:
            cwd_args = args[1:3]
        probe_args = [args[0], *GIT_PREFIX, *cwd_args, "config", "--show-scope", "--null", "--list"]
        token = _audited_argv.set(probe_args)
        try:
            probe = _original_popen(probe_args, cwd=kwargs.get("cwd"), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            _audited_argv.reset(token)
        config, _ = probe.communicate()
        entries = config.split(b"\0")
        safe = {}
        for index in range(0, len(entries) - 1, 2):
            scope, entry = entries[index:index + 2]
            key, _, value = entry.partition(b"\n")
            key = key.lower()
            if key.decode() in SAFE_GIT_CONFIG:
                safe[key.decode()] = value.decode("utf-8")
            if scope in {b"local", b"worktree"} and key.startswith(b"filter.") and key.endswith((b".clean", b".smudge", b".process")):
                deny("Git native filter is outside the reviewed EOL contract")
            if scope in {b"local", b"worktree"} and (key == b"diff.external" or key.startswith(b"diff.") and key.endswith((b".command", b".textconv"))):
                deny("Git native diff driver is outside the reviewed local contract")
            if scope in {b"local", b"worktree"} and (key == b"extensions.partialclone" or key.startswith(b"remote.") and key.endswith((b".promisor", b".partialclonefilter"))):
                deny("Git lazy-fetch configuration is outside the reviewed local contract")
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
        safe_args = [part for key, value in sorted(safe.items()) for part in ("-c", key + "=" + value)]
        args = [args[0], *GIT_PREFIX, *safe_args, *args[1:]]
    elif python_executable(args[0]):
        # Existing offline verification callers intentionally construct their
        # own environment. Mediate that environment at the test-only process
        # boundary; no caller can remove or replace the trusted child prefix.
        env = dict(os.environ if kwargs.get("env") is None else kwargs["env"])
        paths = env.get("PYTHONPATH", "").split(os.pathsep)
        suffix = [part for part in paths if part and FilesystemPath(part).resolve() != BOOTSTRAP]
        env["PYTHONPATH"] = os.pathsep.join([str(BOOTSTRAP), *suffix])
        kwargs["env"] = env
    check_process(args[0], args, kwargs.get("env"))
    return args, kwargs


class GuardedPopen(_original_popen):
    def __init__(self, args, *positional, **kwargs):
        args, kwargs = prepare_process(args, kwargs)
        token = _audited_argv.set(args)
        try:
            super().__init__(args, *positional, **kwargs)
        finally:
            _audited_argv.reset(token)


def deny(reason: str) -> None:
    raise OfflineTransportDenied("PYTEST_EXTERNAL_TRANSPORT_DENIED: " + reason)


def loopback(address: object) -> bool:
    host = address[0] if isinstance(address, tuple) and address else address
    if not isinstance(host, str):
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_address(address: object) -> None:
    # No hostname resolution is permitted, including "localhost". Only literal
    # loopback addresses are local IPC; AF_UNIX paths are handled by the caller.
    if not loopback(address):
        deny("only literal loopback transport is permitted")


def guarded_connect(sock, address):
    if sock.family in {socket.AF_INET, socket.AF_INET6}:
        check_address(address)
    return _original_connect(sock, address)


def guarded_connect_ex(sock, address):
    if sock.family in {socket.AF_INET, socket.AF_INET6}:
        check_address(address)
    return _original_connect_ex(sock, address)


def guarded_sendto(sock, *args):
    if sock.family in {socket.AF_INET, socket.AF_INET6}:
        check_address(args[-1])
    return _original_sendto(sock, *args)


def check_process(executable: object, argv: object, env: object) -> None:
    if not isinstance(argv, (tuple, list)) or not argv:
        deny("unclassifiable command or shell form")
    args = [os.fsdecode(item) for item in argv]
    name = command_name(executable)
    if LINUX_HOST and name == "uname":
        if args[1:] != ["-p"] or not UNAME_EXECUTABLE or os.path.realpath(os.fsdecode(executable)) != os.path.realpath(UNAME_EXECUTABLE):
            deny("host-introspection executable/argv drift")
        return
    if name in {"git", "git.exe"}:
        if not GIT_EXECUTABLE or os.path.normcase(os.path.realpath(os.fsdecode(executable))) != os.path.normcase(os.path.realpath(GIT_EXECUTABLE)):
            deny("Git bypassed trusted executable binding")
        if tuple(args[1:1 + len(GIT_PREFIX)]) != GIT_PREFIX:
            deny("Git bypassed the hook/filter/process mediation")
        local_git_arguments([args[0], *args[1 + len(GIT_PREFIX):]])
        return
    if not python_executable(executable):
        deny("non-Python executable is not classified as source-local")
    for flag in args[1:]:
        if not flag.startswith("-"):
            break
        if flag == "--":
            break
        if any(letter in flag[1:] for letter in "SIE"):
            deny("Python flag bypasses inherited site bootstrap")
        if flag in {"-c", "-m"}:
            break
        if flag.startswith(("-X", "-W")):
            deny("unreviewed multi-argument or pre-site Python option")
        if flag.startswith("--") and flag != "--version" and os.path.realpath(os.fsdecode(executable)) == os.path.realpath(sys.executable):
            deny("unreviewed long interpreter option")
    inherited = os.environ if env is None else env
    if not isinstance(inherited, (dict, os._Environ)):
        deny("unclassifiable child environment")
    paths = inherited.get("PYTHONPATH", "").split(os.pathsep)
    if not paths or FilesystemPath(paths[0]).resolve() != BOOTSTRAP:
        deny("child Python stripped the offline bootstrap")


def audit_hook(event: str, args: tuple) -> None:
    if not LINUX_HOST and event == "import" and args[0].split(".")[0] in NATIVE_TRANSPORT_IMPORTS:
        deny("native transport implementation is outside the Python socket boundary")
    if not LINUX_HOST and event == "ctypes.dlsym" and args[1] not in NATIVE_LOCAL_SYMBOLS:
        deny("native symbol is not in the reviewed local-file/host-introspection allowlist")
    if event == "socket.__new__" and args[1] in {socket.AF_INET, socket.AF_INET6} and args[2] != socket.SOCK_STREAM:
        # Datagram/raw sockets have address-bearing sendmsg paths without a
        # Python audit event. No such transport is required by the corpus.
        deny("INET datagram/raw sockets are not part of local IPC")
    if event in {"socket.connect", "socket.sendto", "socket.bind"}:
        sock, address = args[0], args[1]
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            check_address(address)
    elif event in {"socket.getaddrinfo", "socket.gethostbyname"}:
        check_address(args[0])
    elif event in {"socket.gethostbyaddr", "socket.getnameinfo"}:
        deny("reverse DNS is not part of local IPC")
    elif event == "subprocess.Popen":
        executable, argv, env = args[0], args[1], args[3]
        if WINDOWS_HOST and isinstance(argv, str):
            original = _audited_argv.get()
            if original is None or argv != subprocess.list2cmdline(original):
                deny("Windows process did not preserve reviewed structured argv")
            argv = original
            executable = original[0] if executable is None else executable
        check_process(executable, argv, env)
    elif event.startswith("os.exec") or event in {"os.system", "os.posix_spawn", "os.spawn"}:
        deny("unclassified alternate process creation")


def install() -> None:
    global _installed
    if _installed:
        return
    from offline_linux import install as install_kernel

    install_kernel()
    # There is no opt-out flag. The hook survives replacement/restoration of
    # Python socket methods, and is inherited by ordinary forked Python children.
    prefix = str(BOOTSTRAP)
    old = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = prefix + (os.pathsep + old if old else "")
    sys.addaudithook(audit_hook)
    # Wrappers make pre-original-call tripwire tests observable; the audit hook
    # and Linux kernel filter remain active if a test replaces these methods.
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.socket.sendto = guarded_sendto
    subprocess.Popen = GuardedPopen
    _installed = True
