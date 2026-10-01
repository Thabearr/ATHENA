"""Authenticated historical bytes, never executable production projections."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "tests/fixtures/core_01d_schedule/pre-cutover/identities.json"
INVENTORY_SHA = "778ad8e206e66a6c12b8e572102a1c2127978c0ad9fbf14cf380cab9332d5ec2"


def identities():
    raw = (ROOT / INVENTORY).read_bytes()
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
    raw, identity = read_tracked_head_blob(root, entry["fixture"])
    if identity.git_blob_sha1 != entry["git_blob_sha1"] or identity.git_blob_payload_sha256 != entry["source_sha256"]:
        raise ValueError("tracked pre-cutover identity drift: " + str(path))
    return raw, identity
