"""Irreversible pytest-only Linux x86-64 transport filter.

Kernel ABI reference: https://docs.kernel.org/userspace-api/seccomp_filter.html
This constrains transport syscalls, not arbitrary information flow or the kernel.
"""
from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import stat
import sys

AUDIT_ARCH_X86_64 = 0xC000003E
X32_SYSCALL_BIT = 0x40000000
REVIEWED_ABI_CEILING = 450
ALLOW = 0x7FFF0000
DENY = 0x00050000 | errno.EPERM
SOCKET_CALLS = (41, 53)  # socket, socketpair: only AF_UNIX (1)
DENIED_SYSCALLS = (
    42, 43, 46, 47, 49, 50,  # connect/accept/sendmsg/recvmsg/bind/listen
    101, 165, 166, 272, 288, 299, 307, 308, 310, 311, 321,
    425, 426, 427, 438,  # io_uring and pidfd_getfd
)
_active = False
_syscall = None


def program() -> tuple[tuple[int, int, int, int], ...]:
    # struct seccomp_data: nr @0, arch @4, args[0] @16.
    rows = [(0x20, 0, 0, 4), (0x15, 1, 0, AUDIT_ARCH_X86_64), (0x06, 0, 0, DENY),
            (0x20, 0, 0, 0), (0x45, 0, 1, X32_SYSCALL_BIT), (0x06, 0, 0, DENY),
            (0x25, 0, 1, REVIEWED_ABI_CEILING), (0x06, 0, 0, DENY)]
    for number in DENIED_SYSCALLS:
        rows.extend(((0x15, 0, 1, number), (0x06, 0, 0, DENY)))
    # send() uses sendto with a NULL destination. It can only use anonymous
    # AF_UNIX pairs here: inherited sockets, INET creation, connect and bind are
    # all denied. Preserve asyncio's self-pipe without allowing pathname sendto.
    # Check BOTH halves of the 64-bit pointer, not just its low word.
    rows.extend(((0x15, 0, 6, 44), (0x20, 0, 0, 48), (0x15, 0, 3, 0),
                 (0x20, 0, 0, 52), (0x15, 0, 1, 0),
                 (0x06, 0, 0, ALLOW), (0x06, 0, 0, DENY)))
    for number in SOCKET_CALLS:
        rows.extend(((0x15, 0, 4, number), (0x20, 0, 0, 16),
                     (0x15, 1, 0, 1), (0x06, 0, 0, DENY), (0x06, 0, 0, ALLOW)))
    rows.append((0x06, 0, 0, ALLOW))
    return tuple(rows)


def evaluate(number: int, *, arch: int = AUDIT_ARCH_X86_64, family: int = 2,
             destination: int = 1) -> int:
    """Pure BPF interpreter for adversarial ABI/branch tests on Windows too."""
    pc = accumulator = 0
    rows = program()
    while pc < len(rows):
        code, yes, no, value = rows[pc]
        if code == 0x20:
            accumulator = {0: number, 4: arch, 16: family,
                           48: destination, 52: destination >> 32}[value] & 0xFFFFFFFF
        elif code == 0x15:
            pc += yes if accumulator == value else no
        elif code == 0x45:
            pc += yes if accumulator & value else no
        elif code == 0x25:
            pc += yes if accumulator > value else no
        elif code == 0x06:
            return value
        else:
            raise AssertionError("unreviewed BPF opcode")
        pc += 1
    raise AssertionError("unterminated BPF program")


def install() -> None:
    global _active, _syscall
    if _active or sys.platform != "linux":
        return
    if os.uname().machine != "x86_64":
        raise RuntimeError("offline kernel boundary requires reviewed Linux x86-64 ABI")
    status = Path("/proc/self/status").read_text()
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    if int(fields["CapEff"].strip(), 16) != 0 or int(fields["Threads"].strip()) != 1:
        raise RuntimeError("offline kernel boundary requires unprivileged single-thread startup")
    for item in Path("/proc/self/fd").iterdir():
        try:
            if stat.S_ISSOCK(item.stat().st_mode) or "io_uring" in os.readlink(item):
                raise RuntimeError("offline kernel boundary refuses inherited transport descriptors")
        except FileNotFoundError:
            continue

    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                    ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]

    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filters", ctypes.POINTER(Filter))]

    instructions = program()
    filters = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    compiled = Program(len(instructions), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    _syscall = libc.syscall
    _syscall.restype = ctypes.c_long
    if prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "offline no-new-privileges activation failed")
    if prctl(22, 2, ctypes.byref(compiled), 0, 0) != 0:  # PR_SET_SECCOMP, FILTER
        raise OSError(ctypes.get_errno(), "offline transport filter activation failed")
    _active = True
    if native_socket_probe() != errno.EPERM:
        raise RuntimeError("offline transport kernel proof failed")


def native_socket_probe() -> int:
    if not _active or _syscall is None:
        raise RuntimeError("kernel boundary is not active")
    ctypes.set_errno(0)
    result = _syscall(41, 2, 1, 0)  # socket(AF_INET, SOCK_STREAM, 0), never a packet
    if result >= 0:
        os.close(result)
        raise RuntimeError("unguarded native socket creation reached")
    return ctypes.get_errno()
