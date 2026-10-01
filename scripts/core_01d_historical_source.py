"""Authenticated historical bytes, never executable production projections."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "tests/fixtures/core_01d_schedule/pre-cutover/identities.json"
INVENTORY_SHA = "0379809a228303031e5dd2c5c7329f3754960115535cbc08277ae87554f0dca3"
CURRENT_RECEIPT_SHA = "8e83fd5443149af74e14ceea44766809d1858ce856772a6500b8f55e073afde6"


def identities():
    raw = (ROOT / INVENTORY).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != INVENTORY_SHA:
        raise ValueError("immutable pre-cutover inventory drift")
    return json.loads(raw)["files"]


def historical_bytes(path):
    entry = identities().get(str(path))
    if entry is None:
        return (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    raw = (ROOT / entry["fixture"]).read_bytes().replace(b"\r\n", b"\n")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if hashlib.sha256(raw).hexdigest() != entry["source_sha256"] or blob != entry["git_blob_sha1"]:
        raise ValueError("immutable pre-cutover source drift: " + str(path))
    return raw


def historical_tracked(root, path):
    from runtime.source_identity import read_tracked_head_blob
    entry = identities().get(str(path))
    if entry is None:
        return read_tracked_head_blob(root, path)
    # A historical view must not conceal an arbitrary current producer edit.
    receipt_raw = (ROOT / "artifacts/architecture/core_01d_scheduled_shadow_ownership_v1.json").read_bytes().replace(b"\r\n", b"\n")
    receipt = json.loads(receipt_raw)
    body = {k: v for k, v in receipt.items() if k != "canonical_sha256"}
    digest = hashlib.sha256((json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()).hexdigest()
    if receipt.get("canonical_sha256") != CURRENT_RECEIPT_SHA or digest != CURRENT_RECEIPT_SHA:
        raise ValueError("unreviewed current cutover receipt")
    current = receipt["production_source_identities"].get(str(path))
    if current is not None:
        live, live_identity = read_tracked_head_blob(root, path)
        if live_identity.git_blob_sha1 != current["git_blob_sha1"] or live_identity.git_blob_payload_sha256 != current["source_sha256"]:
            raise ValueError("unreviewed current producer source: " + str(path))
    raw, identity = read_tracked_head_blob(root, entry["fixture"])
    if identity.git_blob_sha1 != entry["git_blob_sha1"] or identity.git_blob_payload_sha256 != entry["source_sha256"]:
        raise ValueError("tracked pre-cutover identity drift: " + str(path))
    return raw, identity
