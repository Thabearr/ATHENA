"""PORT-02C receipt audit test (runs the strict offline audit in CI)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from copy import deepcopy
import json

import pytest

from scripts import audit_port_02_native_runtime as audit

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


@pytest.mark.parametrize("mutation", ["hosted-windows", "fake-local-run", "missing-local-sha", "mixed-head", "fake-ubuntu"])
def test_native_platform_provenance_fails_closed(mutation):
    value = deepcopy(json.loads((ROOT / audit.ARTIFACT_PATH).read_bytes()))
    windows, linux = value["platforms"]
    if mutation == "hosted-windows": windows["host_os_version"] = "Windows-2025Server-10.0.26100-SP0"
    elif mutation == "fake-local-run": windows["workflow_run_id"] = 36792107722
    elif mutation == "missing-local-sha": windows["local_evidence_sha256"] = None
    elif mutation == "mixed-head": linux["qualification_head_sha"] = "0" * 40
    else: linux["evidence_source"] = "LOCAL_WINDOWS_11_NATIVE"
    with pytest.raises(audit.AuditError):
        audit._check_platforms(value)
