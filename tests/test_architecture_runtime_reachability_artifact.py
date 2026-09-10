from __future__ import annotations

import hashlib

from domain.architecture_runtime_reachability import canonical_json_bytes
from scripts import audit_runtime_reachability as audit


EXPECTED_RUNTIME_ARTIFACT_SHA256 = (
    "a8ccb4c0c8ab2bea9bd133bb7fa7e155957bf1e38e5bf7ae6cccb4f44640f7e4"
)


def test_committed_runtime_reachability_artifact_is_exact_regeneration() -> None:
    committed = audit.DEFAULT_OUTPUT.read_bytes()
    regenerated = canonical_json_bytes(
        audit.build_runtime_evidence(audit.BASELINE_MAIN)
    )

    assert committed == regenerated
    assert hashlib.sha256(committed).hexdigest() == EXPECTED_RUNTIME_ARTIFACT_SHA256
