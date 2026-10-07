"""D3 / DATA-01A app repository: validated typed persistence for app schema.

Owns the additive R1 application-control tables in the separate app-owned SQLite
store (``athena-app.sqlite3``). This repository is deliberately distinct from the
legacy ``database.database.Database`` football / history / warehouse ownership.

Every typed field is validated fail-closed: exact text / bool / int types,
timezone-aware UTC timestamps, and exact lowercase SHA-256 identities. Foreign
keys are enforced (``PRAGMA foreign_keys = ON``) with RESTRICT semantics. A
repository record never manufactures a missing evidence blob: artifact rows
carry metadata and reference bytes that are verified separately when read.

This layer persists exact bytes and metadata only. It grants no provider, model,
delivery, wager, or run authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import platform
import re
import sqlite3
import sys
from typing import Any

from domain.run_contracts import canonical_json_bytes
from runtime.release_identity import DevelopmentCheckoutIdentity, InstalledReleaseIdentity
from runtime.resources import ResourceResolver, WritableRoots

from database.app_migrations import (
    AppSchemaMismatchError,
    app_store_path,
    apply_app_migrations,
    connect_app_store,
    verify_app_schema,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_UTC_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3,6}Z")

SOURCE_MODES = ("DEVELOPMENT_CHECKOUT", "INSTALLED_RELEASE")
FAVORITE_ENTITY_KINDS = ("competition", "market")
CAPABILITY_PROFILES = ("MAIN", "SHADOW")

LOCAL_PROFILE_ID = "local-default"


class AppValidationError(ValueError):
    """Raised on any typed-field or referential validation failure."""


# --- typed-field validation -------------------------------------------------

def _text(value: Any, label: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value:
        raise AppValidationError(f"{label} must be non-empty exact text")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise AppValidationError(f"{label} is outside the reviewed vocabulary")
    return value


def _optional_text(value: Any, label: str, *, pattern: re.Pattern[str] | None = None) -> str | None:
    if value is None:
        return None
    return _text(value, label, pattern=pattern)


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise AppValidationError(f"{label} must be an exact lowercase SHA-256")
    return value


def _optional_sha256(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, label)


def _int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise AppValidationError(f"{label} must be an exact int")
    if minimum is not None and value < minimum:
        raise AppValidationError(f"{label} must be >= {minimum}")
    return value


def _utc(value: Any, label: str) -> str:
    if type(value) is not datetime or value.tzinfo is None:
        raise AppValidationError(f"{label} must be a timezone-aware datetime")
    if value.utcoffset() != timedelta(0):
        raise AppValidationError(f"{label} must be an exact UTC instant")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _byte_sha(raw: bytes, label: str) -> str:
    if type(raw) is not bytes:
        raise AppValidationError(f"{label} must be exact bytes")
    return hashlib.sha256(raw).hexdigest()


def _require_agreement(raw: bytes, expected_sha: str, label: str) -> None:
    computed = _byte_sha(raw, label)
    if computed != expected_sha:
        raise AppValidationError(f"{label} bytes do not match their recorded SHA-256")


class AppRepository:
    """Validated typed persistence for the app-owned store."""

    def __init__(self, conn: sqlite3.Connection, store_path: Any) -> None:
        self._conn = conn
        self._store_path = store_path

    # --- lifecycle ---------------------------------------------------------

    @classmethod
    def open(
        cls,
        resources: ResourceResolver,
        writable_roots: WritableRoots,
        *,
        release_id: str,
        now: datetime | None = None,
    ) -> "AppRepository":
        """Run app-schema migrations once and open a verified connection."""
        store = apply_app_migrations(resources, writable_roots, release_id=release_id, now=now)
        conn = connect_app_store(store, synchronous="FULL")
        # Startup integrity verification: pragma + schema/ledger agreement.
        verify_app_schema(conn)
        return cls(conn, store)

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:  # pragma: no cover - best-effort teardown
            pass

    def __enter__(self) -> "AppRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _write(self) -> sqlite3.Connection:
        self._conn.execute("PRAGMA synchronous = FULL")
        return self._conn

    def _read(self) -> sqlite3.Connection:
        self._conn.execute("PRAGMA synchronous = NORMAL")
        return self._conn

    # --- release provenance (truthful) -------------------------------------

    def record_release_manifest(
        self,
        *,
        release_id: str,
        source_mode: str,
        source_commit: str | None,
        platform: str,
        architecture: str | None,
        build_id: str,
        manifest_bytes: bytes | None,
        manifest_byte_sha256: str | None,
        trust_mode: str,
        signature_key_id: str | None,
        verified_at: datetime,
    ) -> None:
        release_id = _text(release_id, "release_id")
        source_mode = _text(source_mode, "source_mode")
        if source_mode not in SOURCE_MODES:
            raise AppValidationError("source_mode is outside the reviewed vocabulary")
        source_commit = _optional_text(source_commit, "source_commit")
        platform = _text(platform, "platform")
        architecture = _optional_text(architecture, "architecture")
        build_id = _text(build_id, "build_id")
        manifest_byte_sha256 = _optional_sha256(manifest_byte_sha256, "manifest_byte_sha256")
        trust_mode = _text(trust_mode, "trust_mode")
        signature_key_id = _optional_text(signature_key_id, "signature_key_id")
        verified_text = _utc(verified_at, "verified_at")
        if manifest_bytes is not None:
            if manifest_byte_sha256 is None:
                raise AppValidationError("manifest_byte_sha256 is required with manifest_bytes")
            _require_agreement(manifest_bytes, manifest_byte_sha256, "manifest_bytes")
        elif manifest_byte_sha256 is not None:
            raise AppValidationError("manifest_bytes is required with manifest_byte_sha256")

        conn = self._write()
        conn.execute("BEGIN")
        try:
            existing = conn.execute(
                "SELECT source_mode, source_commit, platform, architecture, build_id, "
                "manifest_byte_sha256, trust_mode, signature_key_id FROM app_release_manifests "
                "WHERE release_id = ?",
                (release_id,),
            ).fetchone()
            row = (
                source_mode,
                source_commit,
                platform,
                architecture,
                build_id,
                manifest_byte_sha256,
                trust_mode,
                signature_key_id,
            )
            if existing is not None:
                if tuple(existing) != row:
                    raise AppValidationError("conflicting release provenance for release_id")
                conn.execute("COMMIT")
                return
            conn.execute(
                "INSERT INTO app_release_manifests (release_id, source_mode, source_commit, "
                "platform, architecture, build_id, manifest_bytes, manifest_byte_sha256, "
                "trust_mode, signature_key_id, verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    release_id,
                    source_mode,
                    source_commit,
                    platform,
                    architecture,
                    build_id,
                    manifest_bytes,
                    manifest_byte_sha256,
                    trust_mode,
                    signature_key_id,
                    verified_text,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_release_manifest(self, release_id: str) -> dict[str, Any] | None:
        release_id = _text(release_id, "release_id")
        conn = self._read()
        row = conn.execute(
            "SELECT release_id, source_mode, source_commit, platform, architecture, build_id, "
            "manifest_bytes, manifest_byte_sha256, trust_mode, signature_key_id, verified_at "
            "FROM app_release_manifests WHERE release_id = ?",
            (release_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row, _RELEASE_MANIFEST_COLUMNS)

    # --- local presentation profiles ---------------------------------------

    def create_profile(self, *, profile_id: str, display_name: str, created_at: datetime) -> None:
        profile_id = _text(profile_id, "profile_id")
        display_name = _text(display_name, "display_name")
        created_text = _utc(created_at, "created_at")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            conn.execute(
                "INSERT INTO app_profiles (profile_id, display_name, created_at) VALUES (?, ?, ?)",
                (profile_id, display_name, created_text),
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise AppValidationError(f"profile already exists: {profile_id}") from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        profile_id = _text(profile_id, "profile_id")
        conn = self._read()
        row = conn.execute(
            "SELECT profile_id, display_name, created_at FROM app_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        return None if row is None else _row_to_dict(row, _PROFILE_COLUMNS)

    def ensure_local_profile(self, *, now: datetime) -> str:
        """Ensure the default local presentation profile exists (idempotent)."""
        if self.get_profile(LOCAL_PROFILE_ID) is None:
            self.create_profile(profile_id=LOCAL_PROFILE_ID, display_name="Local", created_at=now)
        return LOCAL_PROFILE_ID

    # --- preferences (validated JSON round-trip) ---------------------------

    def set_preference(self, *, profile_id: str, preference_key: str, value: Any, updated_at: datetime) -> None:
        profile_id = _text(profile_id, "profile_id")
        preference_key = _text(preference_key, "preference_key")
        updated_text = _utc(updated_at, "updated_at")
        value_json = _canonical_json_text(value)
        # Fail-closed round-trip: the canonical text must reproduce the value.
        if json.loads(value_json) != value:
            raise AppValidationError("preference value does not round-trip through canonical JSON")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO app_preferences (profile_id, preference_key, value_json, updated_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(profile_id, preference_key) DO UPDATE SET "
                "value_json = excluded.value_json, updated_at = excluded.updated_at",
                (profile_id, preference_key, value_json, updated_text),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_preference(self, *, profile_id: str, preference_key: str) -> Any | None:
        profile_id = _text(profile_id, "profile_id")
        preference_key = _text(preference_key, "preference_key")
        conn = self._read()
        row = conn.execute(
            "SELECT value_json FROM app_preferences WHERE profile_id = ? AND preference_key = ?",
            (profile_id, preference_key),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    # --- favorites ---------------------------------------------------------

    def add_favorite(self, *, profile_id: str, entity_kind: str, entity_identity: str, created_at: datetime) -> None:
        profile_id = _text(profile_id, "profile_id")
        entity_kind = _text(entity_kind, "entity_kind")
        if entity_kind not in FAVORITE_ENTITY_KINDS:
            raise AppValidationError("entity_kind is outside the reviewed vocabulary")
        entity_identity = _text(entity_identity, "entity_identity")
        created_text = _utc(created_at, "created_at")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO app_favorites (profile_id, entity_kind, entity_identity, created_at) "
                "VALUES (?, ?, ?, ?)",
                (profile_id, entity_kind, entity_identity, created_text),
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise AppValidationError("favorite already exists") from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def list_favorites(self, *, profile_id: str) -> list[dict[str, Any]]:
        profile_id = _text(profile_id, "profile_id")
        conn = self._read()
        rows = conn.execute(
            "SELECT profile_id, entity_kind, entity_identity, created_at FROM app_favorites "
            "WHERE profile_id = ? ORDER BY entity_kind, entity_identity",
            (profile_id,),
        ).fetchall()
        return [_row_to_dict(row, _FAVORITE_COLUMNS) for row in rows]

    def remove_favorite(self, *, profile_id: str, entity_kind: str, entity_identity: str) -> None:
        profile_id = _text(profile_id, "profile_id")
        entity_kind = _text(entity_kind, "entity_kind")
        entity_identity = _text(entity_identity, "entity_identity")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            conn.execute(
                "DELETE FROM app_favorites WHERE profile_id = ? AND entity_kind = ? AND entity_identity = ?",
                (profile_id, entity_kind, entity_identity),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # --- artifacts + edges -------------------------------------------------

    def record_artifact(
        self,
        *,
        artifact_id: str,
        byte_sha256: str,
        canonical_sha256: str | None,
        byte_count: int,
        media_type: str,
        artifact_kind: str,
        logical_path: str,
        evidence_class: str,
        verification_policy_id: str | None,
        verified_at: datetime | None,
        created_at: datetime,
    ) -> None:
        artifact_id = _text(artifact_id, "artifact_id")
        byte_sha256 = _sha256(byte_sha256, "byte_sha256")
        canonical_sha256 = _optional_sha256(canonical_sha256, "canonical_sha256")
        byte_count = _int(byte_count, "byte_count", minimum=0)
        media_type = _text(media_type, "media_type")
        artifact_kind = _text(artifact_kind, "artifact_kind")
        logical_path = _text(logical_path, "logical_path")
        evidence_class = _text(evidence_class, "evidence_class")
        verification_policy_id = _optional_text(verification_policy_id, "verification_policy_id")
        verified_text = None if verified_at is None else _utc(verified_at, "verified_at")
        created_text = _utc(created_at, "created_at")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            conn.execute(
                "INSERT INTO app_artifacts (artifact_id, byte_sha256, canonical_sha256, byte_count, "
                "media_type, artifact_kind, logical_path, evidence_class, verification_policy_id, "
                "verified_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    byte_sha256,
                    canonical_sha256,
                    byte_count,
                    media_type,
                    artifact_kind,
                    logical_path,
                    evidence_class,
                    verification_policy_id,
                    verified_text,
                    created_text,
                ),
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise AppValidationError("artifact ID, logical path, or file SHA-256 already exists") from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        artifact_id = _text(artifact_id, "artifact_id")
        conn = self._read()
        row = conn.execute(
            "SELECT artifact_id, byte_sha256, canonical_sha256, byte_count, media_type, "
            "artifact_kind, logical_path, evidence_class, verification_policy_id, verified_at, "
            "created_at FROM app_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        return None if row is None else _row_to_dict(row, _ARTIFACT_COLUMNS)

    def link_artifact(self, *, parent_artifact_id: str, child_artifact_id: str, relation: str) -> None:
        parent_artifact_id = _text(parent_artifact_id, "parent_artifact_id")
        child_artifact_id = _text(child_artifact_id, "child_artifact_id")
        relation = _text(relation, "relation")
        if parent_artifact_id == child_artifact_id:
            raise AppValidationError("artifact self-edges are not allowed")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            self._require_artifact(conn, parent_artifact_id)
            self._require_artifact(conn, child_artifact_id)
            if self._creates_cycle(conn, parent_artifact_id, child_artifact_id):
                raise AppValidationError("artifact edge would create a cycle")
            conn.execute(
                "INSERT INTO app_artifact_edges (parent_artifact_id, child_artifact_id, relation) "
                "VALUES (?, ?, ?)",
                (parent_artifact_id, child_artifact_id, relation),
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise AppValidationError("artifact edge already exists") from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_artifact_edges(self, artifact_id: str) -> list[dict[str, Any]]:
        artifact_id = _text(artifact_id, "artifact_id")
        conn = self._read()
        rows = conn.execute(
            "SELECT parent_artifact_id, child_artifact_id, relation FROM app_artifact_edges "
            "WHERE parent_artifact_id = ? OR child_artifact_id = ? "
            "ORDER BY relation, parent_artifact_id, child_artifact_id",
            (artifact_id, artifact_id),
        ).fetchall()
        return [_row_to_dict(row, _EDGE_COLUMNS) for row in rows]

    # --- capability snapshots ---------------------------------------------

    def record_capability_snapshot(
        self,
        *,
        snapshot_id: str,
        release_id: str,
        profile: str,
        report_bytes: bytes,
        report_sha256: str,
        evaluated_at: datetime,
        expires_at: datetime,
    ) -> None:
        snapshot_id = _text(snapshot_id, "snapshot_id")
        release_id = _text(release_id, "release_id")
        profile = _text(profile, "profile")
        if profile not in CAPABILITY_PROFILES:
            raise AppValidationError("profile must be the canonical execution authority profile")
        report_sha256 = _sha256(report_sha256, "report_sha256")
        if type(report_bytes) is not bytes:
            raise AppValidationError("report_bytes must be exact bytes")
        _require_agreement(report_bytes, report_sha256, "report_bytes")
        evaluated_text = _utc(evaluated_at, "evaluated_at")
        expires_text = _utc(expires_at, "expires_at")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            self._require_release(conn, release_id)
            existing = conn.execute(
                "SELECT report_sha256, release_id, profile FROM app_capability_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (report_sha256, release_id, profile):
                    raise AppValidationError("conflicting capability snapshot identity")
                conn.execute("COMMIT")
                return
            conn.execute(
                "INSERT INTO app_capability_snapshots (snapshot_id, release_id, profile, report_bytes, "
                "report_sha256, evaluated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, release_id, profile, report_bytes, report_sha256, evaluated_text, expires_text),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_capability_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        snapshot_id = _text(snapshot_id, "snapshot_id")
        conn = self._read()
        row = conn.execute(
            "SELECT snapshot_id, release_id, profile, report_bytes, report_sha256, evaluated_at, "
            "expires_at FROM app_capability_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return None if row is None else _row_to_dict(row, _CAPABILITY_COLUMNS)

    # --- run previews (exact bytes) ---------------------------------------

    def insert_preview_record(
        self,
        *,
        preview_id: str,
        profile_id: str,
        request_bytes: bytes,
        request_sha256: str,
        envelope_bytes: bytes,
        envelope_sha256: str,
        capability_snapshot_id: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        preview_id = _text(preview_id, "preview_id")
        profile_id = _text(profile_id, "profile_id")
        request_sha256 = _sha256(request_sha256, "request_sha256")
        envelope_sha256 = _sha256(envelope_sha256, "envelope_sha256")
        capability_snapshot_id = _text(capability_snapshot_id, "capability_snapshot_id")
        if type(request_bytes) is not bytes or type(envelope_bytes) is not bytes:
            raise AppValidationError("request_bytes and envelope_bytes must be exact bytes")
        _require_agreement(request_bytes, request_sha256, "request_bytes")
        _require_agreement(envelope_bytes, envelope_sha256, "envelope_bytes")
        created_text = _utc(created_at, "created_at")
        expires_text = _utc(expires_at, "expires_at")
        conn = self._write()
        conn.execute("BEGIN")
        try:
            self._require_profile(conn, profile_id)
            self._require_capability(conn, capability_snapshot_id)
            existing = conn.execute(
                "SELECT request_sha256, envelope_sha256, capability_snapshot_id FROM app_run_previews "
                "WHERE preview_id = ?",
                (preview_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (request_sha256, envelope_sha256, capability_snapshot_id):
                    raise AppValidationError("conflicting preview identity")
                conn.execute("COMMIT")
                return
            conn.execute(
                "INSERT INTO app_run_previews (preview_id, profile_id, request_bytes, request_sha256, "
                "envelope_bytes, envelope_sha256, capability_snapshot_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    preview_id,
                    profile_id,
                    request_bytes,
                    request_sha256,
                    envelope_bytes,
                    envelope_sha256,
                    capability_snapshot_id,
                    created_text,
                    expires_text,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def fetch_preview_record(self, preview_id: str) -> dict[str, Any] | None:
        preview_id = _text(preview_id, "preview_id")
        conn = self._read()
        row = conn.execute(
            "SELECT preview_id, profile_id, request_bytes, request_sha256, envelope_bytes, "
            "envelope_sha256, capability_snapshot_id, created_at, expires_at FROM app_run_previews "
            "WHERE preview_id = ?",
            (preview_id,),
        ).fetchone()
        return None if row is None else _row_to_dict(row, _PREVIEW_COLUMNS)

    # --- referential helpers ----------------------------------------------

    @staticmethod
    def _require_profile(conn: sqlite3.Connection, profile_id: str) -> None:
        if conn.execute("SELECT 1 FROM app_profiles WHERE profile_id = ?", (profile_id,)).fetchone() is None:
            raise AppValidationError(f"unknown profile_id: {profile_id}")

    @staticmethod
    def _require_release(conn: sqlite3.Connection, release_id: str) -> None:
        if conn.execute("SELECT 1 FROM app_release_manifests WHERE release_id = ?", (release_id,)).fetchone() is None:
            raise AppValidationError(f"unknown release_id: {release_id}")

    @staticmethod
    def _require_capability(conn: sqlite3.Connection, snapshot_id: str) -> None:
        if conn.execute("SELECT 1 FROM app_capability_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone() is None:
            raise AppValidationError(f"unknown capability_snapshot_id: {snapshot_id}")

    @staticmethod
    def _require_artifact(conn: sqlite3.Connection, artifact_id: str) -> None:
        if conn.execute("SELECT 1 FROM app_artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone() is None:
            raise AppValidationError(f"unknown artifact_id: {artifact_id}")

    @staticmethod
    def _creates_cycle(conn: sqlite3.Connection, parent_id: str, child_id: str) -> bool:
        """True when parent -> child would close a cycle (child already reaches parent)."""
        frontier = [child_id]
        seen: set[str] = set()
        while frontier:
            current = frontier.pop()
            if current == parent_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            rows = conn.execute(
                "SELECT child_artifact_id FROM app_artifact_edges WHERE parent_artifact_id = ?",
                (current,),
            ).fetchall()
            frontier.extend(str(row[0]) for row in rows)
        return False


# --- row mapping -----------------------------------------------------------

_RELEASE_MANIFEST_COLUMNS = (
    "release_id", "source_mode", "source_commit", "platform", "architecture", "build_id",
    "manifest_bytes", "manifest_byte_sha256", "trust_mode", "signature_key_id", "verified_at",
)
_PROFILE_COLUMNS = ("profile_id", "display_name", "created_at")
_FAVORITE_COLUMNS = ("profile_id", "entity_kind", "entity_identity", "created_at")
_ARTIFACT_COLUMNS = (
    "artifact_id", "byte_sha256", "canonical_sha256", "byte_count", "media_type", "artifact_kind",
    "logical_path", "evidence_class", "verification_policy_id", "verified_at", "created_at",
)
_EDGE_COLUMNS = ("parent_artifact_id", "child_artifact_id", "relation")
_CAPABILITY_COLUMNS = (
    "snapshot_id", "release_id", "profile", "report_bytes", "report_sha256", "evaluated_at", "expires_at",
)
_PREVIEW_COLUMNS = (
    "preview_id", "profile_id", "request_bytes", "request_sha256", "envelope_bytes",
    "envelope_sha256", "capability_snapshot_id", "created_at", "expires_at",
)


def _row_to_dict(row: tuple[Any, ...], columns: tuple[str, ...]) -> dict[str, Any]:
    return {columns[index]: row[index] for index in range(len(columns))}


def _canonical_json_text(value: Any) -> str:
    try:
        raw = canonical_json_bytes(value)
    except Exception as exc:  # noqa: BLE001 - normalize to a validation error
        raise AppValidationError(f"value is not canonical-JSON serializable: {exc}") from exc
    text = raw.decode("utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    return text


def _running_platform_tag() -> str:
    return "windows" if sys.platform == "win32" else "linux"


def _running_architecture_tag() -> str:
    machine = platform.machine().lower()
    return {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }.get(machine, machine)


def release_provenance(identity: Any, *, verified_at: datetime) -> dict[str, Any]:
    """Truthfully map a verified release identity to app_release_manifests fields.

    Never fabricates release provenance: a built release carries its pinned
    manifest but no git commit (``source_commit`` stays NULL), a development
    checkout carries its exact git commit but no release manifest, and neither
    ever claims a signature (``signature_key_id`` stays NULL under hash-pinned
    trust). ``release_id`` is the immutable provenance key: the installed
    ``release_id`` for a built release, or the exact ``head_commit_sha`` for a
    development checkout (each commit is a distinct immutable provenance row).
    """
    if type(identity) is InstalledReleaseIdentity:
        return {
            "release_id": identity.release_id,
            "source_mode": "INSTALLED_RELEASE",
            "source_commit": None,
            "platform": identity.platform_tag,
            "architecture": identity.architecture_tag,
            "build_id": identity.build_id,
            "manifest_bytes": identity.manifest_bytes,
            "manifest_byte_sha256": identity.manifest_sha256,
            "trust_mode": identity.trust_mode,
            "signature_key_id": None,
            "verified_at": verified_at,
        }
    if type(identity) is DevelopmentCheckoutIdentity:
        return {
            "release_id": identity.head_commit_sha,
            "source_mode": "DEVELOPMENT_CHECKOUT",
            "source_commit": identity.head_commit_sha,
            "platform": _running_platform_tag(),
            "architecture": _running_architecture_tag(),
            "build_id": identity.head_commit_sha,
            "manifest_bytes": None,
            "manifest_byte_sha256": None,
            "trust_mode": identity.policy_id,
            "signature_key_id": None,
            "verified_at": verified_at,
        }
    raise AppValidationError("verified release identity is required for provenance capture")
