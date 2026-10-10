"""Offline, local-only, hash-verified export and append-only audit services."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import uuid
import zipfile

from database.app_migration_evidence import contained, publish
from database.app_root_lock import app_root_lock
from database.app_storage_access import app_store_connection
from database.run_repository import DurableRunRepository
from domain.run_contracts import RunReceipt, RunRequest, canonical_json_bytes
from runtime.resources import ResourceResolver, WritableRoots


EXPORT_POLICY = "ATHENA_DATA_01C_REDACTED_OFFLINE_EXPORT_V1"
AUDIT_POLICY = "ATHENA_DATA_01C_REDACTED_APPEND_ONLY_AUDIT_V1"
MAX_EXPORT_BYTES = 16 * 1024 * 1024
MAX_EXPORT_MEMBERS = 12
_EVENT_TYPE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|cookie|session|credential|authorization|bearer|token|wallet|"
    r"secret|api[_-]?key|provider[_-]?(?:payload|body|response)|raw[_-]?provider)", re.I
)
_SENSITIVE_VALUE = re.compile(
    r"(?:bearer\s+[A-Za-z0-9._~+/=-]{8,}|(?:set-cookie|authorization)\s*:|"
    r"(?:password|passwd|cookie|session|token|api[_-]?key)\s*[=:])", re.I
)


class ExportError(ValueError):
    """Export source, redaction or archive authentication failure."""


class AuditEventError(ValueError):
    """Audit payload is not canonical redacted metadata."""


def _now_text(value: datetime | None) -> str:
    instant = value or datetime.now(timezone.utc)
    if type(instant) is not datetime or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sensitive(value, path: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key)
            # These two false flags are capability declarations in the
            # authenticated receipt authority manifest, not cookie or wallet
            # material. Keep the receipt byte-faithful while still rejecting
            # either capability being enabled or any similarly named field
            # outside this exact reviewed location.
            safe_disabled_capability = (
                path == ("authority_manifest", "capabilities")
                and name in {"cookies", "wallet"}
                and item is False
            )
            if _SENSITIVE_KEY.search(name) and not safe_disabled_capability:
                return True
            if _sensitive(item, path + (name,)):
                return True
        return False
    if isinstance(value, list):
        return any(_sensitive(item, path + (str(index),)) for index, item in enumerate(value))
    if isinstance(value, str):
        return bool(_SENSITIVE_VALUE.search(value))
    return False


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.create_system = 3
    return info


def _manifest(files: dict[str, bytes], *, policy: str, identity: dict) -> bytes:
    descriptors = [
        {"path": path, "byte_sha256": hashlib.sha256(raw).hexdigest(), "byte_count": len(raw)}
        for path, raw in sorted(files.items())
    ]
    value = {"schema_version": 1, "policy_id": policy, "identity": identity,
             "members": descriptors, "member_count": len(descriptors),
             "total_byte_count": sum(row["byte_count"] for row in descriptors)}
    value["canonical_manifest_sha256"] = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return canonical_json_bytes(value)


def _archive(files: dict[str, bytes], manifest: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.writestr(_zip_info("manifest.json"), manifest)
        for name, raw in sorted(files.items()):
            archive.writestr(_zip_info(name), raw)
    result = stream.getvalue()
    if len(result) > MAX_EXPORT_BYTES:
        raise ExportError("export exceeds the reviewed archive bound")
    return result


def _safe_member(name: str) -> bool:
    if (type(name) is not str or not name or name.startswith("/") or "\\" in name
            or ":" in name or "%" in name or "\x00" in name
            or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in name)):
        return False
    parts = name.split("/")
    return all(part not in {"", ".", ".."} for part in parts) and unicodedata.normalize("NFC", name) == name


def _verify_archive(raw: bytes, expected_manifest: bytes | None = None) -> tuple[dict, dict[str, bytes]]:
    if type(raw) is not bytes or len(raw) > MAX_EXPORT_BYTES:
        raise ExportError("archive exceeds reviewed byte bound")
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_EXPORT_MEMBERS + 1:
                raise ExportError("archive member count is outside the reviewed bound")
            seen = set()
            contents = {}
            total = 0
            for info in infos:
                name = info.filename
                folded = unicodedata.normalize("NFC", name).casefold()
                mode = (info.external_attr >> 16) & 0o170000
                if (not _safe_member(name) or folded in seen or info.is_dir()
                        or mode not in {0, stat.S_IFREG} or info.compress_type != zipfile.ZIP_STORED
                        or info.file_size > MAX_EXPORT_BYTES):
                    raise ExportError("archive contains an unsafe or duplicate member")
                seen.add(folded)
                total += info.file_size
                if total > MAX_EXPORT_BYTES:
                    raise ExportError("archive expands beyond the reviewed byte bound")
                chunks = []
                streamed = 0
                with archive.open(info, "r") as member:
                    while True:
                        part = member.read(64 * 1024)
                        if not part:
                            break
                        streamed += len(part)
                        if streamed > info.file_size or streamed > MAX_EXPORT_BYTES:
                            raise ExportError("member streamed length exceeds its declaration")
                        chunks.append(part)
                if streamed != info.file_size:
                    raise ExportError("member declared and streamed lengths differ")
                contents[name] = b"".join(chunks)
        manifest_raw = contents.pop("manifest.json", None)
        if manifest_raw is None or (expected_manifest is not None and manifest_raw != expected_manifest):
            raise ExportError("archive manifest missing or differs from the indexed manifest")
        value = json.loads(manifest_raw)
        if type(value) is not dict or canonical_json_bytes(value) != manifest_raw:
            raise ExportError("archive manifest is not canonical JSON")
        digest = value.get("canonical_manifest_sha256")
        unsigned = dict(value)
        unsigned.pop("canonical_manifest_sha256", None)
        if digest != hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest():
            raise ExportError("archive manifest canonical digest mismatch")
        descriptors = value.get("members")
        if (type(descriptors) is not list or value.get("member_count") != len(descriptors)
                or value.get("total_byte_count") != sum(row.get("byte_count", -1) for row in descriptors)
                or set(contents) != {row.get("path") for row in descriptors}):
            raise ExportError("archive member inventory mismatch")
        for row in descriptors:
            if (type(row) is not dict or not _safe_member(row.get("path"))
                    or type(row.get("byte_count")) is not int
                    or row["byte_count"] != len(contents[row["path"]])
                    or row.get("byte_sha256") != hashlib.sha256(contents[row["path"]]).hexdigest()):
                raise ExportError("archive member hash/length mismatch")
        return value, contents
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError("archive failed bounded ZIP verification") from exc


def _run_export_files(resources, roots, run_id):
    repository = DurableRunRepository(resources, roots)
    snapshot = repository.run_snapshot(run_id)
    if snapshot is None:
        raise ExportError("run identity is not present in the authenticated app store")
    request = RunRequest.from_json_bytes(snapshot["request_bytes"])
    files = {"run/request.json": snapshot["request_bytes"]}
    included = ["canonical_run_request"]
    excluded = ["session_credentials", "cookies", "provider_secrets", "raw_provider_payloads"]
    receipt_ref = None
    if snapshot["state"] == "TERMINAL" and snapshot.get("receipt_artifact_id"):
        with app_store_connection(resources, roots) as conn:
            rows = conn.execute(
                "SELECT a.byte_sha256,a.byte_count,a.artifact_kind,a.logical_path,r.role,r.retained_root "
                "FROM app_artifacts a JOIN app_run_artifacts r USING(artifact_id) "
                "WHERE a.artifact_id=? AND r.run_id=?",
                (snapshot["receipt_artifact_id"], run_id),
            ).fetchall()
        if len(rows) != 1 or rows[0][2:] != (
                "RUN_RECEIPT", "run-receipts/" + rows[0][0] + ".json", "RUN_RECEIPT", 1):
            raise ExportError("terminal receipt role or locator does not authenticate")
        sha, count, _kind, locator, _role, _retained = rows[0]
        try:
            raw_wrapper = contained(roots.data_root, locator).read_bytes()
        except (OSError, ValueError) as exc:
            raise ExportError("terminal receipt artifact is missing") from exc
        if hashlib.sha256(raw_wrapper).hexdigest() != sha or len(raw_wrapper) != count:
            raise ExportError("terminal receipt artifact hash mismatch")
        wrapper = json.loads(raw_wrapper)
        receipt = RunReceipt.from_dict(wrapper["receipt"])
        if receipt.request.canonical_sha256 != request.canonical_sha256:
            raise ExportError("terminal RunReceipt does not bind the raw RunRequest")
        receipt_raw = canonical_json_bytes(receipt)
        if len(receipt_raw) <= 2 * 1024 * 1024 and not _sensitive(receipt.to_dict()):
            files["run/receipt.json"] = receipt_raw
            included.append("canonical_run_receipt_raw_opaque_selection_mappings")
        else:
            excluded.append("run_receipt_content_redaction_scan_rejected")
        receipt_ref = {"artifact_id": snapshot["receipt_artifact_id"],
                       "byte_sha256": sha, "byte_count": count,
                       "role": "RUN_RECEIPT", "semantic_fields_validated": False}
    metadata = {
        "run_id": run_id,
        "request_sha256": snapshot["request_sha256"],
        "envelope_sha256": snapshot["envelope_sha256"],
        "release_id": snapshot["release_id"],
        "receipt_artifact": receipt_ref,
        "selected_leg_semantics": "OPAQUE_RAW_RECEIPT_CONTENT_ONLY",
    }
    files["evidence/references.json"] = canonical_json_bytes(metadata)
    files["evidence/redaction-inventory.json"] = canonical_json_bytes({
        "policy_id": EXPORT_POLICY,
        "included_classes": included + ["canonical_hash_and_evidence_metadata"],
        "excluded_classes": excluded,
        "uploaded_or_delivered": False,
    })
    if _sensitive({path: raw.decode("utf-8", errors="ignore") for path, raw in files.items()}):
        raise ExportError("redaction scan rejected export member content")
    if sum(map(len, files.values())) > MAX_EXPORT_BYTES:
        raise ExportError("export source members exceed the reviewed byte bound")
    return snapshot, files


def create_run_export(
    resources: ResourceResolver,
    roots: WritableRoots,
    *,
    profile_id: str,
    run_id: str,
    created_at: datetime | None = None,
) -> str:
    """Create a server-named offline run export; returns only an opaque ID."""
    if type(profile_id) is not str or not profile_id or type(run_id) is not str or not run_id:
        raise ExportError("profile and run identities are required")
    stamp = _now_text(created_at)
    export_id = "exp_" + uuid.uuid4().hex
    with app_root_lock(roots.data_root):
        # Verify terminal receipt/source semantics before creating an export row.
        snapshot, files = _run_export_files(resources, roots, run_id)
        with app_store_connection(resources, roots, write=True) as conn:
            if conn.execute("SELECT 1 FROM app_profiles WHERE profile_id=?", (profile_id,)).fetchone() is None:
                raise ExportError("profile identity is unavailable")
            conn.execute(
                "INSERT INTO app_exports(export_id,profile_id,run_id,export_kind,redaction_policy_id,"
                "state,created_at) VALUES(?,?,?,'RUN_EVIDENCE',?,'PREPARING',?)",
                (export_id, profile_id, run_id, EXPORT_POLICY, stamp),
            )
        manifest = _manifest(files, policy=EXPORT_POLICY,
                             identity={"export_id": export_id, "run_id": run_id,
                                       "request_sha256": snapshot["request_sha256"]})
        archive_raw = _archive(files, manifest)
        archive_path = f"exports/{export_id}.zip"
        manifest_path = f"exports/{export_id}.manifest.json"
        try:
            publish(roots.data_root, archive_path, archive_raw)
            publish(roots.data_root, manifest_path, manifest)
            verified_manifest, verified_files = _verify_archive(
                contained(roots.data_root, archive_path).read_bytes(), manifest
            )
            if verified_files != files or verified_manifest["identity"]["export_id"] != export_id:
                raise ExportError("published export differs from its verified source")
            archive_sha = hashlib.sha256(archive_raw).hexdigest()
            manifest_sha = hashlib.sha256(manifest).hexdigest()
            manifest_artifact_id = "export-manifest-" + export_id
            with app_store_connection(resources, roots, write=True) as conn:
                conn.execute(
                    "INSERT INTO app_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    ("export-archive-" + export_id, archive_sha, None, len(archive_raw),
                     "application/zip", "LOCAL_EXPORT", archive_path, "RETAINED",
                     EXPORT_POLICY, stamp, stamp),
                )
                conn.execute(
                    "INSERT INTO app_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (manifest_artifact_id, manifest_sha, manifest_sha, len(manifest),
                     "application/json", "EXPORT_MANIFEST", manifest_path, "RETAINED",
                     EXPORT_POLICY, stamp, stamp),
                )
                conn.execute(
                    "UPDATE app_exports SET state='VERIFIED',manifest_artifact_id=?,logical_path=? "
                    "WHERE export_id=? AND state='PREPARING'",
                    (manifest_artifact_id, archive_path, export_id),
                )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ExportError("export row was not PREPARING at verification commit")
            return export_id
        except Exception:
            with app_store_connection(resources, roots, write=True) as conn:
                conn.execute("UPDATE app_exports SET state='FAILED',error_code='EXPORT_VERIFY_FAILED' "
                             "WHERE export_id=? AND state='PREPARING'", (export_id,))
            raise


def read_verified_export(resources, roots, export_id: str) -> bytes:
    """Authenticate and return the exact ZIP bytes; state alone is never trusted."""
    if type(export_id) is not str or not re.fullmatch(r"exp_[0-9a-f]{32}", export_id):
        raise ExportError("opaque export ID is malformed")
    with app_root_lock(roots.data_root):
        with app_store_connection(resources, roots) as conn:
            row = conn.execute(
                "SELECT e.state,e.logical_path,e.manifest_artifact_id,a.logical_path,"
                "a.byte_sha256,a.byte_count,x.byte_sha256,x.byte_count "
                "FROM app_exports e JOIN app_artifacts a ON a.artifact_id=e.manifest_artifact_id "
                "JOIN app_artifacts x ON x.logical_path=e.logical_path AND x.artifact_kind='LOCAL_EXPORT' "
                "WHERE e.export_id=?", (export_id,),
            ).fetchone()
        if row is None or row[0] != "VERIFIED" or row[1] != f"exports/{export_id}.zip" or row[3] != f"exports/{export_id}.manifest.json":
            raise ExportError("export state or server-owned locator is not verified")
        try:
            manifest = contained(roots.data_root, row[3]).read_bytes()
            archive = contained(roots.data_root, row[1]).read_bytes()
        except (OSError, ValueError) as exc:
            raise ExportError("verified export bytes are missing or unsafe") from exc
        if (len(manifest) != row[5] or hashlib.sha256(manifest).hexdigest() != row[4]
                or len(archive) != row[7] or hashlib.sha256(archive).hexdigest() != row[6]
                or _verify_archive(archive, manifest)[0]["identity"].get("export_id") != export_id):
            raise ExportError("export manifest or archive bytes failed reauthentication")
        return archive


def append_audit_event(
    resources: ResourceResolver,
    roots: WritableRoots,
    *,
    event_type: str,
    payload: dict,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> str:
    """Append an exact canonical redacted metadata event; updates/deletes fail."""
    if type(event_type) is not str or _EVENT_TYPE.fullmatch(event_type) is None:
        raise AuditEventError("event_type is outside the reviewed uppercase vocabulary")
    if type(payload) is not dict or _sensitive(payload):
        raise AuditEventError("audit payload must be a redacted JSON object")
    try:
        raw = canonical_json_bytes(payload)
    except Exception as exc:
        raise AuditEventError("audit payload must be finite canonical JSON") from exc
    if len(raw) > 64 * 1024:
        raise AuditEventError("audit payload exceeds the reviewed byte bound")
    audit_id = "audit_" + uuid.uuid4().hex
    digest = hashlib.sha256(raw).hexdigest()
    with app_store_connection(resources, roots, write=True) as conn:
        conn.execute(
            "INSERT INTO app_audit_events(audit_id,run_id,event_type,payload_bytes,payload_sha256,created_at) "
            "VALUES(?,?,?,?,?,?)", (audit_id, run_id, event_type, raw, digest, _now_text(created_at)),
        )
    return audit_id


def read_audit_events(resources, roots, *, run_id: str | None = None) -> list[dict]:
    with app_store_connection(resources, roots) as conn:
        if run_id is None:
            rows = conn.execute(
                "SELECT audit_id,run_id,event_type,payload_bytes,payload_sha256,created_at "
                "FROM app_audit_events ORDER BY created_at,audit_id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT audit_id,run_id,event_type,payload_bytes,payload_sha256,created_at "
                "FROM app_audit_events WHERE run_id=? ORDER BY created_at,audit_id", (run_id,)
            ).fetchall()
    result = []
    for audit_id, event_run_id, event_type, raw, digest, created_at in rows:
        if hashlib.sha256(raw).hexdigest() != digest:
            raise AuditEventError("stored audit payload digest mismatch")
        payload = json.loads(raw)
        if canonical_json_bytes(payload) != raw or _sensitive(payload):
            raise AuditEventError("stored audit payload is not canonical redacted JSON")
        result.append({"audit_id": audit_id, "run_id": event_run_id,
                       "event_type": event_type, "payload": payload,
                       "payload_sha256": digest, "created_at": created_at})
    return result


__all__ = [
    "AUDIT_POLICY", "EXPORT_POLICY", "AuditEventError", "ExportError",
    "append_audit_event", "create_run_export", "read_audit_events", "read_verified_export",
]
