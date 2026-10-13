import hashlib
import shutil

import pytest

from scripts import audit_lg_a_worker_launch_failure_remediation as audit


def test_historical_worker_entry_uses_authenticated_predecessor_and_rejects_tampering(tmp_path, monkeypatch):
    digest = "feaf4a9364fd064f081c9a4d086b65fdc31620075f0071ae1385bcbfa5cdaf94"
    predecessor = audit.ROOT / "tests/fixtures/core_01d/run_02a_pre_historical/worker-entry-predecessor.py.txt"
    assert hashlib.sha256(audit.historical_worker_boundary_bytes("runtime/worker_entry.py")).hexdigest() == digest

    root = tmp_path
    current = root / "runtime/worker_entry.py"
    current.parent.mkdir(parents=True)
    shutil.copyfile(audit.ROOT / "runtime/worker_entry.py", current)
    fixture = root / "tests/fixtures/core_01d/run_02a_pre_historical/worker-entry-predecessor.py.txt"
    fixture.parent.mkdir(parents=True)
    shutil.copyfile(predecessor, fixture)
    monkeypatch.setattr(audit, "ROOT", root)

    fixture.write_bytes(fixture.read_bytes() + b"# tampered predecessor\n")
    with pytest.raises(AssertionError, match="exact transport predecessor bytes changed"):
        audit.historical_worker_boundary_bytes("runtime/worker_entry.py")

    shutil.copyfile(predecessor, fixture)
    current.write_bytes(current.read_bytes() + b"# tampered current source\n")
    with pytest.raises(AssertionError, match="current transport differs from authenticated A2"):
        audit.historical_worker_boundary_bytes("runtime/worker_entry.py")
