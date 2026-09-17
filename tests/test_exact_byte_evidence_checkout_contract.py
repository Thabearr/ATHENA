"""Cross-platform checkout contract for P3.0-E1-reachable frozen evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# This is intentionally a small explicit allowlist, not a broad JSON policy.  Each
# entry is imported by the P3.0-E1 pre-Router dependency closure and enforces its
# own reviewed byte identity at runtime.
BYTE_FROZEN_P3_E1_EVIDENCE = (
    (
        "artifacts/research-manifests/"
        "sportybet-ng-early-payout-settlement-source-evidence-v1.json",
        2059,
        "af371490fb3e72dc9b5d3422a6b36af28ff4246ee6ead23b0c957e26c398afe4",
    ),
)


def test_frozen_p3_e1_evidence_retains_reviewed_byte_identity() -> None:
    for relative_path, expected_size, expected_sha256 in BYTE_FROZEN_P3_E1_EVIDENCE:
        raw = (ROOT / relative_path).read_bytes()

        assert len(raw) == expected_size
        assert hashlib.sha256(raw).hexdigest() == expected_sha256
        # The evidence is canonical JSON, but logical JSON equality alone is not
        # sufficient: retain this assertion only as an additional syntax check.
        assert json.dumps(
            json.loads(raw.decode("utf-8")),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n" == raw


def test_frozen_p3_e1_evidence_is_exempt_from_checkout_text_conversion() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()

    for relative_path, _, _ in BYTE_FROZEN_P3_E1_EVIDENCE:
        assert f"{relative_path} -text" in attributes
