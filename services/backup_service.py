"""Consistent app-store backup, bounded restore staging and recoverable activation.

This service operates only on synthetic/offline local storage. All supported
app-store writers and this service share the cross-process root lock. Backup
archives are stored in a stable sibling vault so a root-generation switch does
not erase backup history. Restore never merges files and never extracts into
the active root.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import unicodedata
import uuid
import zipfile

from database.app_migration_evidence import contained, verify_retained_manifest
from database.app_migrations import (
    APP_MIGRATIONS, APP_STORE_FILENAME, app_store_path, connect_app_store,
    expected_schema_structure, read_app_migrations, schema_structure, verify_app_schema,
)
from database.app_repository import LOCAL_PROFILE_ID, logical_locator, release_provenance
from database.app_root_lock import (
    app_root_lock, _fsync_directory, _recover_interrupted_switch,
    _rename_durable, _replace_durable,
)
from database.app_storage_access import app_store_connection
from database.run_repository import DurableRunRepository, ReceiptProducerUnavailable
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import RunRequest, canonical_json_bytes
from runtime.resources import ResourceResolver, WritableRoots


BACKUP_POLICY = "ATHENA_DATA_01C_COMPLETE_APP_BACKUP_V1"
RESTORE_POLICY = "ATHENA_DATA_01C_STAGED_ROOT_RESTORE_V1"
MAX_BACKUP_BYTES = 1024 * 1024 * 1024
MAX_BACKUP_MEMBER_BYTES = 512 * 1024 * 1024
MAX_BACKUP_MEMBERS = 50_000
MAX_COMPRESSION_RATIO = 1.0
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_GENERATION_NAME = re.compile(r"\.[A-Za-z0-9._-]+\.(?:history|restore|failed)\.[0-9a-f]{32}(?:\.staging)?\Z")


class BackupError(ValueError):
    """Backup snapshot or immutable archive failed authentication."""


class RestoreError(ValueError):
    """Archive is unsafe, inconsistent, or cannot be restored safely."""


@dataclass(frozen=True)
class BackupResult:
    backup_id: str
    local_locator: str
    manifest_byte_sha256: str
    archive_byte_sha256: str
    archive_byte_count: int
    app_run_ids: tuple[str, ...]
    migration_ledger: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class RestoreStage:
    backup_id: str
    staged_root: Path
    archive_path: Path
    manifest_byte_sha256: str
    archive_byte_sha256: str
    terminal_producer_authentication: str
    activation_eligible: bool
    diagnostics: tuple[str, ...]


def _stamp(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be an aware UTC datetime")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _vault(roots: WritableRoots) -> Path:
    return roots.data_root.parent / (roots.data_root.name + ".backup-vault")


def _locator(backup_id: str) -> str:
    return "backup-vault/" + backup_id + ".zip"


def _vault_path(roots: WritableRoots, backup_id: str) -> Path:
    if type(backup_id) is not str or re.fullmatch(r"bkp_[0-9a-f]{32}", backup_id) is None:
        raise BackupError("backup identity is malformed")
    root = _vault(roots)
    if root.is_symlink() or bool(getattr(root, "is_junction", lambda: False)()):
        raise BackupError("backup vault may not be a link or junction")
    root.mkdir(parents=True, exist_ok=True)
    return root / (backup_id + ".zip")


def _hash_file(path: Path, *, limit: int = MAX_BACKUP_MEMBER_BYTES) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while True:
            part = stream.read(1024 * 1024)
            if not part:
                break
            count += len(part)
            if count > limit:
                raise BackupError("retained source exceeds the per-member backup bound")
            digest.update(part)
    return digest.hexdigest(), count


def _canonical_manifest(value: dict) -> bytes:
    unsigned = dict(value)
    unsigned.pop("canonical_manifest_sha256", None)
    value["canonical_manifest_sha256"] = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    return canonical_json_bytes(value)


def _zip_info(name: str, size: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.file_size = size
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.create_system = 3
    return info


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _publish_temp(temp: Path, target: Path) -> None:
    if target.exists() or target.is_symlink() or bool(getattr(target, "is_junction", lambda: False)()):
        raise BackupError("immutable backup target already exists")
    try:
        os.link(temp, target)
    except FileExistsError as exc:
        raise BackupError("immutable backup identity collision") from exc
    _fsync_directory(target.parent)


def _retained_migration_files(root: Path, migration_rows) -> dict[str, tuple[Path, str, int]]:
    files = {}
    for _version, _sha, manifest_sha in migration_rows:
        if type(manifest_sha) is not str or _SHA.fullmatch(manifest_sha) is None:
            raise BackupError("migration ledger recovery-evidence digest is unavailable")
        manifest_locator = "migration-evidence/" + manifest_sha + ".json"
        verify_retained_manifest(root, manifest_sha)
        manifest_path = contained(root, manifest_locator)
        manifest_raw = manifest_path.read_bytes()
        files[manifest_locator] = (manifest_path, hashlib.sha256(manifest_raw).hexdigest(), len(manifest_raw))
        value = json.loads(manifest_raw)
        evidence = value["ownership_inventory_evidence"]
        inventory_locator = evidence["logical_path"]
        inventory_path = contained(root, inventory_locator)
        inventory_raw = inventory_path.read_bytes()
        if hashlib.sha256(inventory_raw).hexdigest() != evidence["byte_sha256"]:
            raise BackupError("retained ownership inventory hash mismatch")
        files[inventory_locator] = (inventory_path, hashlib.sha256(inventory_raw).hexdigest(), len(inventory_raw))
        backup = value.get("backup")
        if backup is not None:
            locator = logical_locator(backup["logical_path"])
            path = contained(root, locator)
            digest, size = _hash_file(path)
            if digest != backup["byte_sha256"] or size != backup["byte_count"]:
                raise BackupError("retained pre-migration SQLite image mismatch")
            files[locator] = (path, digest, size)
    return files


def _remove_validation_sidecars(db_path: Path) -> None:
    """Remove only regular SQLite sidecars created while validating a staged DB."""
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(db_path) + suffix)
        try:
            mode = sidecar.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise RestoreError("staged SQLite validation produced an unsafe sidecar")
        try:
            sidecar.unlink()
        except OSError as exc:
            raise RestoreError("staged SQLite validation sidecar could not be removed") from exc


def _snapshot_and_inventory(resources, roots, snapshot_path: Path, release_id: str):
    migrations = read_app_migrations(resources)
    identities = [(version, digest) for version, _path, _raw, digest in migrations]
    files: dict[str, tuple[Path, str, int]] = {}
    artifacts = []
    run_ids = []
    release_value = None
    with app_store_connection(resources, roots) as source:
        rows = source.execute(
            "SELECT version,migration_sha256,backup_manifest_sha256 "
            "FROM app_schema_migrations ORDER BY version"
        ).fetchall()
        if [(row[0], row[1]) for row in rows] != identities:
            raise BackupError("app migration ledger differs from verified source bytes")
        run_ids = [row[0] for row in source.execute("SELECT run_id FROM app_runs ORDER BY run_id")]
        artifact_rows = source.execute(
            "SELECT artifact_id,logical_path,byte_sha256,byte_count,canonical_sha256,artifact_kind "
            "FROM app_artifacts ORDER BY logical_path,artifact_id"
        ).fetchall()
        for artifact_id, logical_path, byte_sha, byte_count, canonical_sha, kind in artifact_rows:
            locator = logical_locator(logical_path)
            path = contained(roots.data_root, locator)
            if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()) or not path.is_file():
                raise BackupError("referenced artifact is absent or not a regular retained file")
            digest, size = _hash_file(path)
            if digest != byte_sha or size != byte_count:
                raise BackupError("referenced artifact bytes do not match the app index")
            if locator in files and files[locator][1:] != (digest, size):
                raise BackupError("retained evidence locator collision")
            files[locator] = (path, digest, size)
            artifacts.append({"artifact_id": artifact_id, "logical_path": locator,
                              "byte_sha256": digest, "byte_count": size,
                              "canonical_sha256": canonical_sha, "artifact_kind": kind})
        release = source.execute(
            "SELECT release_id,source_mode,source_commit,platform,architecture,build_id,"
            "manifest_byte_sha256,trust_mode,signature_key_id,manifest_bytes "
            "FROM app_release_manifests WHERE release_id=?", (release_id,),
        ).fetchone()
        if release is None:
            raise BackupError("originating release identity has no verified app provenance row")
        current_provenance = release_provenance(resources.identity, verified_at=datetime.now(timezone.utc))
        if release[0] != current_provenance["release_id"]:
            raise BackupError("backup release identity is not the active verified resolver identity")
        release_value = {
            "release_id": release[0], "source_mode": release[1], "source_commit": release[2],
            "platform": release[3], "architecture": release[4], "build_id": release[5],
            "manifest_byte_sha256": release[6], "trust_mode": release[7],
            "signature_key_id": release[8],
            "manifest_bytes_sha256": None if release[9] is None else hashlib.sha256(release[9]).hexdigest(),
            "installed_producer_git_identity": "OPEN_E2_PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE",
        }
        migration_files = _retained_migration_files(roots.data_root, rows)
        for locator, item in migration_files.items():
            if locator in files and files[locator][1:] != item[1:]:
                raise BackupError("migration and artifact evidence locator collision")
            files[locator] = item
        destination = sqlite3.connect(snapshot_path)
        try:
            destination.execute("PRAGMA foreign_keys=ON")
            if destination.execute("PRAGMA foreign_keys").fetchone() != (1,):
                raise BackupError("snapshot target did not enable foreign keys")
            if destination.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
                raise BackupError("snapshot target could not establish the app-store WAL mode")
            destination.execute("PRAGMA synchronous=FULL")
            source.backup(destination)
            destination.commit()
            if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise BackupError("SQLite online backup integrity check failed")
        finally:
            destination.close()
    digest, size = _hash_file(snapshot_path)
    files[APP_STORE_FILENAME] = (snapshot_path, digest, size)
    if sum(row[2] for row in files.values()) > MAX_BACKUP_BYTES:
        raise BackupError("complete app snapshot exceeds the reviewed backup bound")
    return migrations, rows, run_ids, artifacts, release_value, files


def _make_manifest(backup_id, migrations, rows, run_ids, artifacts, release, files, now):
    members = []
    evidence = []
    total = 0
    for locator, (_path, digest, size) in sorted(files.items()):
        archive_path = "data/" + locator
        members.append({"path": archive_path, "byte_sha256": digest, "byte_count": size})
        total += size
        if locator != APP_STORE_FILENAME:
            matching = next((row for row in artifacts if row["logical_path"] == locator), None)
            evidence.append({"logical_path": locator, "byte_sha256": digest,
                             "byte_count": size,
                             "canonical_sha256": None if matching is None else matching["canonical_sha256"],
                             "source": "APP_ARTIFACT" if matching else "PRE_MIGRATION_EVIDENCE"})
    value = {
        "schema_version": 1,
        "policy_id": BACKUP_POLICY,
        "backup_id": backup_id,
        "created_at": now,
        "snapshot_schema_version": len(migrations),
        "migration_ledger": [{"version": version, "logical_path": path,
                              "migration_sha256": digest}
                             for version, path, _raw, digest in migrations],
        "origin_release_identity": release,
        "sqlite_snapshot": {"path": "data/" + APP_STORE_FILENAME,
                            "byte_sha256": files[APP_STORE_FILENAME][1],
                            "byte_count": files[APP_STORE_FILENAME][2]},
        "app_run_ids": run_ids,
        "artifacts": artifacts,
        "referenced_evidence": evidence,
        "included_categories": ["app_sqlite_snapshot", "migration_recovery_evidence",
                                "indexed_retained_app_artifacts", "d3_d4_run_receipt_blobs"],
        "excluded_categories": ["unindexed_files", "cache_roots", "session_credentials",
                                "cookies", "transient_provider_transport", "worker_process_state"],
        "e2_dependencies": [
            {"id": "E2/VERIFIED_DECISION_PROJECTION_SOURCE_CONTRACT", "status": "OPEN"},
            {"id": "E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE", "status": "OPEN"},
        ],
        "terminal_producer_semantics": "ARCHIVE_PRESERVES_AUTHENTICATED_SOURCE_BYTES; RESTORE_REAUTHENTICATES_OR_BLOCKS_ACTIVATION",
        "membership": {"member_count": len(members), "total_byte_count": total,
                       "app_artifact_count": len(artifacts), "run_count": len(run_ids)},
        "members": members,
    }
    return _canonical_manifest(value)


def _write_archive(path: Path, manifest: bytes, files: dict[str, tuple[Path, str, int]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.writestr(_zip_info("manifest.json", len(manifest)), manifest)
        for locator, (source, expected_sha, expected_size) in sorted(files.items()):
            member = "data/" + locator
            info = _zip_info(member, expected_size)
            digest = hashlib.sha256()
            count = 0
            with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
                while True:
                    part = reader.read(1024 * 1024)
                    if not part:
                        break
                    count += len(part)
                    if count > expected_size or count > MAX_BACKUP_MEMBER_BYTES:
                        raise BackupError("retained source changed or exceeded declared size during archive write")
                    digest.update(part)
                    writer.write(part)
            if count != expected_size or digest.hexdigest() != expected_sha:
                raise BackupError("retained source changed during consistent archive write")
    if path.stat().st_size > MAX_BACKUP_BYTES:
        raise BackupError("backup archive exceeds the reviewed total byte bound")
    _fsync_file(path)


def _safe_archive_path(name: str) -> bool:
    if (type(name) is not str or not name or name.startswith("/") or "\\" in name
            or any(char in name for char in '<>:"|?*%') or "\x00" in name
            or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in name)):
        return False
    path = PurePosixPath(name)
    if path.as_posix() != name or unicodedata.normalize("NFC", name) != name:
        return False
    windows_devices = {
        "con", "prn", "aux", "nul", "conin$", "conout$",
        *(f"com{number}" for number in "123456789¹²³"),
        *(f"lpt{number}" for number in "123456789¹²³"),
    }
    for part in name.split("/"):
        if part in {"", ".", ".."} or part.endswith((".", " ")):
            return False
        device_stem = part.split(".", 1)[0].casefold()
        if device_stem in windows_devices:
            return False
    return True


def _scan_archive(archive_path: Path, *, stage_root: Path | None = None):
    """Stream-verify a store-only ZIP and optionally write into fresh staging."""
    if archive_path.is_symlink() or bool(getattr(archive_path, "is_junction", lambda: False)()):
        raise RestoreError("archive source may not be a link or junction")
    try:
        stat_result = archive_path.stat()
        if not stat.S_ISREG(stat_result.st_mode) or stat_result.st_size > MAX_BACKUP_BYTES:
            raise RestoreError("archive size or file type is outside the reviewed bound")
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_BACKUP_MEMBERS + 1:
                raise RestoreError("archive member count exceeds the reviewed bound")
            if infos[0].filename != "manifest.json":
                raise RestoreError("canonical backup manifest must be the first archive member")
            folded = set()
            total = 0
            manifest = None
            value = None
            expected = None
            for info in infos:
                name = info.filename
                norm = unicodedata.normalize("NFC", name).casefold()
                mode = (info.external_attr >> 16) & 0o170000
                dos_attributes = info.external_attr & 0xFFFF
                if (not _safe_archive_path(name) or norm in folded or info.is_dir()
                        or mode not in {0, stat.S_IFREG} or info.compress_type != zipfile.ZIP_STORED
                        or dos_attributes & 0x0400 or dos_attributes & 0x0010
                        or info.file_size > MAX_BACKUP_MEMBER_BYTES
                        or (info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO)):
                    raise RestoreError("archive contains a traversal, link, duplicate, bomb or special file")
                folded.add(norm)
                total += info.file_size
                if total > MAX_BACKUP_BYTES:
                    raise RestoreError("streamed archive members exceed total byte bound")
                digest = hashlib.sha256()
                count = 0
                is_manifest = name == "manifest.json"
                if is_manifest:
                    if info.file_size > 16 * 1024 * 1024:
                        raise RestoreError("backup manifest exceeds its reviewed metadata bound")
                    chunks = []
                    with archive.open(info, "r") as member:
                        while True:
                            part = member.read(64 * 1024)
                            if not part:
                                break
                            count += len(part)
                            if count > info.file_size:
                                raise RestoreError("manifest stream exceeds declared length")
                            chunks.append(part)
                    if count != info.file_size:
                        raise RestoreError("manifest stream length mismatch")
                    manifest = b"".join(chunks)
                    value = json.loads(manifest)
                    if type(value) is not dict or canonical_json_bytes(value) != manifest:
                        raise RestoreError("archive manifest is not canonical JSON")
                    unsigned = dict(value)
                    manifest_sha = unsigned.pop("canonical_manifest_sha256", None)
                    if manifest_sha != hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest():
                        raise RestoreError("backup manifest canonical digest mismatch")
                    declared = value.get("members")
                    if type(declared) is not list:
                        raise RestoreError("backup manifest member inventory is malformed")
                    expected = {}
                    previous = None
                    for row in declared:
                        if (type(row) is not dict or set(row) != {"path", "byte_sha256", "byte_count"}
                                or not _safe_archive_path(row["path"]) or not row["path"].startswith("data/")
                                or type(row["byte_count"]) is not int or row["byte_count"] < 0
                                or _SHA.fullmatch(row["byte_sha256"]) is None):
                            raise RestoreError("backup manifest member descriptor is malformed")
                        if previous is not None and row["path"] <= previous:
                            raise RestoreError("backup manifest members are not uniquely sorted")
                        previous = row["path"]
                        locator = row["path"][5:]
                        if locator in expected:
                            raise RestoreError("duplicate normalized manifest locator")
                        expected[locator] = (row["byte_sha256"], row["byte_count"])
                    if len(infos) != len(expected) + 1 or len(infos) - 1 > MAX_BACKUP_MEMBERS:
                        raise RestoreError("archive/manifest member count mismatch")
                    if sum(size for _sha, size in expected.values()) > MAX_BACKUP_BYTES:
                        raise RestoreError("manifest expands beyond the reviewed total byte bound")
                    if (value.get("membership", {}).get("member_count") != len(expected)
                            or value.get("membership", {}).get("total_byte_count")
                            != sum(size for _sha, size in expected.values())):
                        raise RestoreError("archive counts contradict backup summary")
                    continue
                if not name.startswith("data/") or name == "data/":
                    raise RestoreError("archive contains an unexpected member")
                locator = name[5:]
                if not _safe_archive_path(locator) or expected is None or locator not in expected:
                    raise RestoreError("archive member has no canonical manifest entry")
                expected_sha, expected_size = expected[locator]
                if info.file_size != expected_size:
                    raise RestoreError("archive declared member length disagrees with manifest")
                target = None
                writer = None
                if stage_root is not None:
                    target = contained(stage_root, locator)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() or target.is_symlink() or bool(getattr(target, "is_junction", lambda: False)()):
                        raise RestoreError("staging target collision or link")
                    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    writer = os.fdopen(descriptor, "wb")
                try:
                    with archive.open(info, "r") as member:
                        while True:
                            part = member.read(1024 * 1024)
                            if not part:
                                break
                            count += len(part)
                            if count > expected_size or count > MAX_BACKUP_MEMBER_BYTES:
                                raise RestoreError("member stream exceeds declared/reviewed length")
                            digest.update(part)
                            if writer is not None:
                                writer.write(part)
                    if count != expected_size or digest.hexdigest() != expected_sha:
                        raise RestoreError("archive member hash or length mismatch")
                    if writer is not None:
                        writer.flush()
                        os.fsync(writer.fileno())
                finally:
                    if writer is not None:
                        writer.close()
            if manifest is None or value is None or expected is None:
                raise RestoreError("archive manifest is missing")
            if {info.filename[5:] for info in infos[1:]} != set(expected):
                raise RestoreError("archive includes absent/extra files relative to its manifest")
            return value, manifest
    except RestoreError:
        raise
    except Exception as exc:
        raise RestoreError("backup archive failed bounded streaming authentication") from exc


def create_backup(
    resources: ResourceResolver,
    roots: WritableRoots,
    *,
    release_id: str,
    created_at: datetime | None = None,
) -> BackupResult:
    """Create and verify one immutable online SQLite + retained-blob backup."""
    stamp = _stamp(created_at)
    provenance = release_provenance(resources.identity, verified_at=created_at or datetime.now(timezone.utc))
    if release_id != provenance["release_id"]:
        raise BackupError("release_id does not match the verified resource identity")
    backup_id = "bkp_" + uuid.uuid4().hex
    locator = _locator(backup_id)
    vault = _vault(roots)
    if vault.is_symlink() or bool(getattr(vault, "is_junction", lambda: False)()):
        raise BackupError("backup vault may not be a link or junction")
    vault.mkdir(parents=True, exist_ok=True)
    target = _vault_path(roots, backup_id)
    with app_root_lock(roots.data_root):
        with app_store_connection(resources, roots, write=True) as conn:
            if conn.execute("SELECT 1 FROM app_profiles WHERE profile_id=?", (LOCAL_PROFILE_ID,)).fetchone() is None:
                raise BackupError("local app profile is unavailable")
            if conn.execute("SELECT 1 FROM app_release_manifests WHERE release_id=?", (release_id,)).fetchone() is None:
                raise BackupError("active release provenance is unavailable")
            conn.execute(
                "INSERT INTO app_backups(backup_id,profile_id,schema_version,release_id,local_locator,state,created_at) "
                "VALUES(?,?,3,?,?,'PREPARING',?)",
                (backup_id, LOCAL_PROFILE_ID, release_id, locator, stamp),
            )
        descriptor, snapshot_name = tempfile.mkstemp(prefix=".snapshot-", suffix=".sqlite3", dir=vault)
        os.close(descriptor)
        snapshot_path = Path(snapshot_name)
        archive_descriptor, archive_name = tempfile.mkstemp(prefix=".archive-", suffix=".zip", dir=vault)
        os.close(archive_descriptor)
        archive_temp = Path(archive_name)
        try:
            migrations, rows, run_ids, artifacts, release_value, files = _snapshot_and_inventory(
                resources, roots, snapshot_path, release_id
            )
            manifest = _make_manifest(backup_id, migrations, rows, run_ids, artifacts,
                                      release_value, files, stamp)
            manifest_sha = hashlib.sha256(manifest).hexdigest()
            _write_archive(archive_temp, manifest, files)
            manifest_read, verified_manifest = _scan_archive(archive_temp)
            if (verified_manifest != manifest or manifest_read["backup_id"] != backup_id
                    or manifest_read["canonical_manifest_sha256"] == ""):
                raise BackupError("published backup did not pass manifest/archive verification")
            archive_sha, archive_size = _hash_file(archive_temp, limit=MAX_BACKUP_BYTES)
            _publish_temp(archive_temp, target)
            with app_store_connection(resources, roots, write=True) as conn:
                conn.execute(
                    "UPDATE app_backups SET manifest_byte_sha256=?,state='VERIFIED',verified_at=?,error_code=NULL "
                    "WHERE backup_id=? AND state='PREPARING'",
                    (manifest_sha, _stamp(datetime.now(timezone.utc)), backup_id),
                )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise BackupError("backup index was not PREPARING at verification commit")
            return BackupResult(backup_id, locator, manifest_sha, archive_sha,
                                archive_size, tuple(run_ids),
                                tuple((row[0], row[1]) for row in rows))
        except Exception:
            with app_store_connection(resources, roots, write=True) as conn:
                conn.execute("UPDATE app_backups SET state='FAILED',error_code='BACKUP_VERIFY_FAILED' "
                             "WHERE backup_id=? AND state='PREPARING'", (backup_id,))
            raise
        finally:
            snapshot_path.unlink(missing_ok=True)
            archive_temp.unlink(missing_ok=True)


def verify_backup(resources, roots, backup_id: str) -> dict:
    """Authenticate index, immutable vault archive, SQLite and all indexed bytes."""
    with app_root_lock(roots.data_root):
        with app_store_connection(resources, roots) as conn:
            row = conn.execute(
                "SELECT profile_id,schema_version,release_id,manifest_byte_sha256,local_locator,state "
                "FROM app_backups WHERE backup_id=?", (backup_id,),
            ).fetchone()
        if row is None or row[5] != "VERIFIED" or row[4] != _locator(backup_id):
            raise BackupError("backup index is not a verified server-owned entry")
        path = _vault_path(roots, backup_id)
        value, manifest = _scan_archive(path)
        archive_sha, archive_size = _hash_file(path, limit=MAX_BACKUP_BYTES)
        if hashlib.sha256(manifest).hexdigest() != row[3] or value.get("backup_id") != backup_id:
            raise BackupError("backup manifest identity disagrees with app index")
        if (value.get("snapshot_schema_version") != row[1]
                or value.get("origin_release_identity", {}).get("release_id") != row[2]):
            raise BackupError("backup schema/release identity mismatch")
        snapshot = next((row for row in value["members"]
                         if row["path"] == "data/" + APP_STORE_FILENAME), None)
        if snapshot is None or snapshot["byte_sha256"] != value["sqlite_snapshot"]["byte_sha256"]:
            raise BackupError("backup SQLite member identity mismatch")
        return {"backup_id": backup_id, "manifest_byte_sha256": row[3],
                "archive_byte_sha256": archive_sha, "archive_byte_count": archive_size,
                "member_count": value["membership"]["member_count"],
                "app_run_ids": tuple(value["app_run_ids"]), "manifest": value}


def _stage_root_name(root: Path, token: str) -> str:
    return "." + root.name + ".restore." + token + ".staging"


def _build_staged_validation(resources, roots, stage: Path, manifest: dict, archive_sha: str):
    db_path = stage / APP_STORE_FILENAME
    if db_path.is_symlink() or not db_path.is_file():
        raise RestoreError("staged SQLite database missing or unsafe")
    if any(Path(str(db_path) + suffix).exists()
           or Path(str(db_path) + suffix).is_symlink()
           for suffix in ("-wal", "-shm", "-journal")):
        raise RestoreError("archive contains SQLite sidecars outside the online-backup snapshot")
    migration_rows = read_app_migrations(resources)
    identities = [(version, digest) for version, _path, _raw, digest in migration_rows]
    conn = connect_app_store(db_path, readonly=True)
    diagnostics = []
    terminal_auth = "NONE"
    eligible = True
    try:
        if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RestoreError("staged SQLite integrity_check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RestoreError("staged SQLite foreign_key_check failed")
        verify_app_schema(conn, expected_structure=expected_schema_structure(migration_rows))
        ledger = conn.execute("SELECT version,migration_sha256,backup_manifest_sha256 "
                              "FROM app_schema_migrations ORDER BY version").fetchall()
        if [(row[0], row[1]) for row in ledger] != identities:
            raise RestoreError("staged migration ledger differs from exact reviewed resources")
        run_ids = [row[0] for row in conn.execute("SELECT run_id FROM app_runs ORDER BY run_id")]
        if run_ids != manifest.get("app_run_ids"):
            raise RestoreError("staged app run identities disagree with backup manifest")
        artifacts = conn.execute("SELECT artifact_id,logical_path,byte_sha256,byte_count,canonical_sha256,artifact_kind "
                                 "FROM app_artifacts ORDER BY logical_path,artifact_id").fetchall()
        expected_files = {APP_STORE_FILENAME}
        for _artifact_id, locator, digest, size, _canonical_sha, _kind in artifacts:
            logical_locator(locator)
            expected_files.add(locator)
            path = contained(stage, locator)
            if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()) or not path.is_file():
                raise RestoreError("staged referenced artifact is missing or unsafe")
            actual_sha, actual_size = _hash_file(path)
            if actual_sha != digest or actual_size != size:
                raise RestoreError("staged referenced artifact hash/size mismatch")
        expected_files.update(_retained_migration_files(stage, ledger))
        manifest_artifacts = manifest.get("artifacts")
        expected_artifacts = [
            {"artifact_id": aid, "logical_path": locator, "byte_sha256": digest,
             "byte_count": size, "canonical_sha256": canonical_sha, "artifact_kind": kind}
            for aid, locator, digest, size, canonical_sha, kind in artifacts
        ]
        if manifest_artifacts != expected_artifacts:
            raise RestoreError("staged artifact membership differs from its backup manifest")
        release = manifest.get("origin_release_identity") or {}
        release_row = conn.execute(
            "SELECT release_id,source_mode,source_commit,platform,architecture,build_id,"
            "manifest_byte_sha256,trust_mode,signature_key_id,manifest_bytes "
            "FROM app_release_manifests WHERE release_id=?", (release.get("release_id"),)
        ).fetchone()
        if release_row is None:
            raise RestoreError("staged originating release provenance is unavailable")
        release_identity = {
            "release_id": release_row[0], "source_mode": release_row[1],
            "source_commit": release_row[2], "platform": release_row[3],
            "architecture": release_row[4], "build_id": release_row[5],
            "manifest_byte_sha256": release_row[6], "trust_mode": release_row[7],
            "signature_key_id": release_row[8],
            "manifest_bytes_sha256": None if release_row[9] is None else hashlib.sha256(release_row[9]).hexdigest(),
            "installed_producer_git_identity": "OPEN_E2_PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE",
        }
        if release_identity != release:
            raise RestoreError("staged release identity differs from authenticated app provenance")
    finally:
        conn.close()
    staging_cache = stage.parent / (stage.name + ".cache")
    staging_state = stage.parent / (stage.name + ".state")
    staged_roots = WritableRoots(stage, staging_cache, staging_state,
                                 installed_release_root=resources.identity.release_root
                                 if hasattr(resources.identity, "release_root") else None)
    repository = DurableRunRepository(resources, staged_roots)
    for run_id in run_ids:
        try:
            snapshot = repository.run_snapshot(run_id)
            if snapshot is None:
                raise RestoreError("staged run disappeared during D4 verification")
        except ReceiptProducerUnavailable:
            # Installed builds deliberately lack a verified producer commit
            # until E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE.
            terminal_auth = "UNAVAILABLE_E2_PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE"
            eligible = False
            diagnostics.append("terminal receipt producer proof remains open; activation blocked")
        except Exception as exc:
            raise RestoreError("staged D3/D4 run identity or receipt verification failed") from exc
    _remove_validation_sidecars(db_path)
    actual_files = {path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()}
    missing_files = sorted(expected_files - actual_files)
    unreferenced_files = sorted(actual_files - expected_files)
    if missing_files or unreferenced_files:
        raise RestoreError(
            "staged restore file inventory mismatch; missing=" + repr(missing_files)
            + "; unreferenced=" + repr(unreferenced_files)
        )
    return terminal_auth, eligible, tuple(diagnostics)


def stage_restore_archive(
    resources: ResourceResolver,
    roots: WritableRoots,
    archive_path: str | os.PathLike[str],
) -> RestoreStage:
    """Stream-validate an archive into a separate sibling generation root."""
    source = Path(archive_path)
    if not source.is_absolute():
        raise RestoreError("restore archive path must be absolute")
    if source.is_symlink() or bool(getattr(source, "is_junction", lambda: False)()):
        raise RestoreError("restore archive source may not be a link or junction")
    try:
        source = source.resolve(strict=True)
    except OSError as exc:
        raise RestoreError("restore archive source is unavailable") from exc
    value, manifest = _scan_archive(source)
    if value.get("schema_version") != 1 or value.get("policy_id") != BACKUP_POLICY:
        raise RestoreError("backup policy/version is not supported")
    migrations = read_app_migrations(resources)
    if value.get("migration_ledger") != [
            {"version": version, "logical_path": path, "migration_sha256": digest}
            for version, path, _raw, digest in migrations]:
        raise RestoreError("archive migration chain is not the current verified source chain")
    snapshot = next((row for row in value.get("members", [])
                     if row.get("path") == "data/" + APP_STORE_FILENAME), None)
    if snapshot is None:
        raise RestoreError("archive omits the app-owned SQLite database")
    token = uuid.uuid4().hex
    stage = roots.data_root.parent / _stage_root_name(roots.data_root, token)
    if stage.exists() or stage.is_symlink() or bool(getattr(stage, "is_junction", lambda: False)()):
        raise RestoreError("staging root identity collision")
    with app_root_lock(roots.data_root):
        stage.mkdir(mode=0o700)
        try:
            staged_value, staged_manifest = _scan_archive(source, stage_root=stage)
            if staged_manifest != manifest or staged_value != value:
                raise RestoreError("archive changed between scan and staging passes")
            expected_files = {row["path"][5:] for row in value["members"]}
            actual_files = {path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()}
            if actual_files != expected_files:
                raise RestoreError("staged root contains absent or unexpected files")
            if any(path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())
                   for path in stage.rglob("*")):
                raise RestoreError("staged root contains a link or junction")
            archive_sha, _archive_size = _hash_file(source, limit=MAX_BACKUP_BYTES)
            terminal_auth, eligible, diagnostics = _build_staged_validation(
                resources, roots, stage, value, archive_sha
            )
            return RestoreStage(value["backup_id"], stage, source,
                                hashlib.sha256(manifest).hexdigest(), archive_sha,
                                terminal_auth, eligible, diagnostics)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise


def _write_journal(path: Path, value: dict) -> None:
    raw = canonical_json_bytes(value)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_durable(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _activate_generation(root: Path, stage: Path, manifest_sha: str, *, phase_hook=None) -> Path:
    parent = root.parent
    token = uuid.uuid4().hex
    history = parent / ("." + root.name + ".history." + token)
    failed = parent / ("." + root.name + ".failed." + token)
    expected_stage_name = _stage_root_name(root, stage.name.split(".restore.", 1)[-1].removesuffix(".staging"))
    if stage.parent != parent or stage.name != expected_stage_name or not _GENERATION_NAME.fullmatch(stage.name):
        raise RestoreError("staging root is not a server-owned same-volume generation")
    if not root.exists() or root.is_symlink() or bool(getattr(root, "is_junction", lambda: False)()):
        raise RestoreError("activation requires an existing preserved regular app root")
    if stage.is_symlink() or bool(getattr(stage, "is_junction", lambda: False)()):
        raise RestoreError("staging root may not be a link or junction")
    if history.exists() or failed.exists():
        raise RestoreError("restore generation destination collision")
    journal = parent / ("." + root.name + ".restore-journal.json")
    if journal.exists():
        raise RestoreError("an earlier root switch journal requires recovery")
    value = {"schema_version": 1, "data_root": root.name,
             "history_name": history.name, "staging_name": stage.name,
             "failed_name": failed.name, "manifest_sha256": manifest_sha}
    _write_journal(journal, value)
    if phase_hook:
        phase_hook("JOURNAL_PREPARED")
    _rename_durable(root, history)
    _fsync_directory(parent)
    if phase_hook:
        phase_hook("OLD_ROOT_PRESERVED")
    _rename_durable(stage, root)
    _fsync_directory(parent)
    if phase_hook:
        phase_hook("NEW_ROOT_ACTIVE")
    return history


def activate_staged_restore(
    resources: ResourceResolver,
    roots: WritableRoots,
    staged: RestoreStage,
    *,
    phase_hook=None,
) -> Path:
    """Activate only independently verified staging, keeping a full old root."""
    if type(staged) is not RestoreStage or not staged.activation_eligible:
        raise RestoreError("staged terminal producer provenance is unavailable; activation is blocked")
    with app_root_lock(roots.data_root):
        # Recheck the stage immediately before root ownership changes.
        archive_sha, archive_size = _hash_file(staged.archive_path, limit=MAX_BACKUP_BYTES)
        if archive_sha != staged.archive_byte_sha256 or archive_size > MAX_BACKUP_BYTES:
            raise RestoreError("source archive changed after staging")
        manifest_value, manifest_raw = _scan_archive(staged.archive_path)
        if (manifest_value.get("backup_id") != staged.backup_id
                or hashlib.sha256(manifest_raw).hexdigest() != staged.manifest_byte_sha256):
            raise RestoreError("staged restore does not bind to its canonical source archive")
        for descriptor in manifest_value.get("members", []):
            locator = descriptor["path"][5:]
            file_path = contained(staged.staged_root, locator)
            if _hash_file(file_path) != (descriptor["byte_sha256"], descriptor["byte_count"]):
                raise RestoreError("staged member changed after archive verification")
        terminal_auth, eligible, _diagnostics = _build_staged_validation(
            resources, roots, staged.staged_root, manifest_value, archive_sha
        )
        if terminal_auth != staged.terminal_producer_authentication or not eligible:
            raise RestoreError("staged D4 producer evidence changed or remains unavailable")
        try:
            history = _activate_generation(roots.data_root, staged.staged_root,
                                           staged.manifest_byte_sha256,
                                           phase_hook=phase_hook)
            # Verify the active generation against the same exact runtime
            # migration source before discarding the recovery journal.
            active = connect_app_store(app_store_path(roots), readonly=True)
            try:
                verify_app_schema(active, expected_structure=expected_schema_structure(read_app_migrations(resources)))
                if active.execute("PRAGMA integrity_check").fetchone() != ("ok",) or active.execute("PRAGMA foreign_key_check").fetchall():
                    raise RestoreError("active restored generation failed post-switch verification")
            finally:
                active.close()
            _remove_validation_sidecars(app_store_path(roots))
            active_auth, active_eligible, _active_diagnostics = _build_staged_validation(
                resources, roots, roots.data_root, manifest_value, archive_sha
            )
            if active_auth != staged.terminal_producer_authentication or not active_eligible:
                raise RestoreError("active restored D3/D4 evidence failed post-switch verification")
            journal = roots.data_root.parent / ("." + roots.data_root.name + ".restore-journal.json")
            journal.unlink()
            _fsync_directory(journal.parent)
            return history
        except Exception:
            # `_recover_interrupted_switch` returns the complete preserved old
            # root and keeps a failed new generation in a sibling for review.
            try:
                _recover_interrupted_switch(roots.data_root)
            except Exception as recovery_error:
                raise RestoreError("root switch failed and automatic rollback could not verify the old root") from recovery_error
            raise


def stage_indexed_backup(resources, roots, backup_id: str) -> RestoreStage:
    """Stage an indexed local backup without changing the active app root."""
    with app_store_connection(resources, roots) as conn:
        row = conn.execute("SELECT state,local_locator,manifest_byte_sha256 FROM app_backups WHERE backup_id=?",
                           (backup_id,)).fetchone()
    if row is None or row[0] != "VERIFIED" or row[1] != _locator(backup_id):
        raise RestoreError("backup index is not a verified local archive")
    result = verify_backup(resources, roots, backup_id)
    stage = stage_restore_archive(resources, roots, _vault_path(roots, backup_id))
    if stage.manifest_byte_sha256 != row[2] or result["manifest_byte_sha256"] != row[2]:
        raise RestoreError("staged archive manifest differs from its verified index")
    return stage


__all__ = [
    "BACKUP_POLICY", "RESTORE_POLICY", "BackupError", "BackupResult", "RestoreError",
    "RestoreStage", "activate_staged_restore", "create_backup", "stage_indexed_backup",
    "stage_restore_archive", "verify_backup",
]
