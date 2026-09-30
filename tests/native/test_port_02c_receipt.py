"""PORT-02C receipt audit test (runs the strict offline audit in CI)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_port_02c_native_runtime_receipt_audit_passes():
    completed = subprocess.run(
        [sys.executable, "scripts/audit_port_02_native_runtime.py", "--check"],
        cwd=str(ROOT),
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, (
        completed.stdout.decode("utf-8", "replace")[-2000:]
        + completed.stderr.decode("utf-8", "replace")[-2000:]
    )
    assert b"PORT_02C_RECEIPT_OK" in completed.stdout
