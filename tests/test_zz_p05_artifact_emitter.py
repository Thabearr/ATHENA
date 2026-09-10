from __future__ import annotations

import base64
import hashlib
import zlib

from domain.architecture_runtime_reachability import canonical_json_bytes
from scripts import audit_runtime_reachability as audit


def test_emit_p05_runtime_artifact_for_review_capture() -> None:
    raw = canonical_json_bytes(audit.build_runtime_evidence(audit.BASELINE_MAIN))
    encoded = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
    print("P05_ARTIFACT_SHA256=" + hashlib.sha256(raw).hexdigest())
    print("P05_ARTIFACT_ZLIB_BASE64_BEGIN")
    print(encoded)
    print("P05_ARTIFACT_ZLIB_BASE64_END")
    raise AssertionError("temporary P0.5 artifact capture gate")
