-- D3 / DATA-01A additive application-control core schema.
--
-- This migration creates the FIRST R1 application persistence slice in the
-- separate app-owned SQLite store (athena-app.sqlite3). It is applied exactly
-- once under the app_schema_migrations ledger by database/app_migrations.py.
--
-- Scope is limited to the nine D3 application tables. D4 run/attempt/event
-- tables (app_runs, app_run_attempts, app_run_events, app_external_operations,
-- app_run_artifacts) and D5 projection/export/backup/audit tables are
-- intentionally absent. Legacy football/history/warehouse stores retain their
-- separate reviewed ownership and are never touched here.
--
-- Foreign keys default RESTRICT. No cascading deletion of retained evidence.
-- Timestamps are timezone-aware UTC canonical text ending in Z (validated in
-- the application layer). SHA-256 columns are exact lowercase 64-hex text
-- (validated in the application layer; length enforced here as a backstop).

-- 1. Migration ledger: installed app-schema version + immutable migration and
--    pre-migration evidence identities. Authority is limited to app-schema
--    compatibility; it grants no provider/model/delivery/run authority.
CREATE TABLE app_schema_migrations (
    version INTEGER PRIMARY KEY,
    migration_sha256 TEXT NOT NULL CHECK (length(migration_sha256) = 64),
    applied_at TEXT NOT NULL,
    release_id TEXT NOT NULL,
    backup_manifest_sha256 TEXT NOT NULL CHECK (length(backup_manifest_sha256) = 64),
    CHECK (version >= 1)
);

-- 2. Local presentation identity only. There is deliberately NO authority /
--    execution / provider / delivery / wager column here. app_profiles.profile_id
--    is NOT RunRequest.authority_profile (MAIN/SHADOW lives in the envelope).
CREATE TABLE app_profiles (
    profile_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 3. Presentation-only preferences keyed to a local profile.
CREATE TABLE app_preferences (
    profile_id TEXT NOT NULL,
    preference_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, preference_key),
    FOREIGN KEY (profile_id) REFERENCES app_profiles(profile_id) ON DELETE RESTRICT
);

-- 4. Navigation shortcuts only. Not Router preference, model input, or
--    competition/market authority.
CREATE TABLE app_favorites (
    profile_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_identity TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, entity_kind, entity_identity),
    FOREIGN KEY (profile_id) REFERENCES app_profiles(profile_id) ON DELETE RESTRICT,
    CHECK (entity_kind IN ('competition', 'market'))
);

-- 5. Release provenance, truthful for the two verified identity modes. Does
--    NOT replace startup verification and does NOT fabricate signature or
--    source-commit facts. signature_key_id is NULL today (hash-pinned trust).
CREATE TABLE app_release_manifests (
    release_id TEXT PRIMARY KEY,
    source_mode TEXT NOT NULL,
    source_commit TEXT,
    platform TEXT NOT NULL,
    architecture TEXT,
    build_id TEXT NOT NULL,
    manifest_bytes BLOB,
    manifest_byte_sha256 TEXT,
    trust_mode TEXT NOT NULL,
    signature_key_id TEXT,
    verified_at TEXT NOT NULL,
    CHECK (source_mode IN ('DEVELOPMENT_CHECKOUT', 'INSTALLED_RELEASE')),
    CHECK (manifest_byte_sha256 IS NULL OR length(manifest_byte_sha256) = 64)
);

-- 6. Artifact metadata index. The database record cannot manufacture a missing
--    evidence blob; reading an artifact later must verify referenced bytes.
--    byte_sha256 (exact file bytes) and canonical_sha256 (canonical semantic
--    payload) are distinct and must never be conflated.
CREATE TABLE app_artifacts (
    artifact_id TEXT PRIMARY KEY,
    byte_sha256 TEXT NOT NULL CHECK (length(byte_sha256) = 64),
    canonical_sha256 TEXT CHECK (canonical_sha256 IS NULL OR length(canonical_sha256) = 64),
    byte_count INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    logical_path TEXT NOT NULL,
    evidence_class TEXT NOT NULL,
    verification_policy_id TEXT,
    verified_at TEXT,
    created_at TEXT NOT NULL,
    CHECK (byte_count >= 0),
    UNIQUE (logical_path),
    UNIQUE (byte_sha256)
);

-- 7. Artifact dependency edges. Self-edges and cycles are rejected in
--    transactional repository logic where a relation contract requires a DAG.
CREATE TABLE app_artifact_edges (
    parent_artifact_id TEXT NOT NULL,
    child_artifact_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    PRIMARY KEY (parent_artifact_id, child_artifact_id, relation),
    FOREIGN KEY (parent_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    FOREIGN KEY (child_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT
);

-- 8. Immutable capability evidence. report_bytes is the exact D1
--    ExecutionPreview.canonical_bytes. profile is the canonical execution
--    authority profile (MAIN/SHADOW), never app_profiles.profile_id. This is
--    evidence only, not a mutable authority registry.
CREATE TABLE app_capability_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    report_bytes BLOB NOT NULL,
    report_sha256 TEXT NOT NULL CHECK (length(report_sha256) = 64),
    evaluated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (release_id) REFERENCES app_release_manifests(release_id) ON DELETE RESTRICT
);

-- 9. Durable immutable preview record. request_bytes / envelope_bytes are the
--    exact D1 canonical RunRequest / ExecutionEnvelope bytes; the capability
--    snapshot carries the exact ExecutionPreview bytes. Persistence does not
--    grant permission to admit a run.
CREATE TABLE app_run_previews (
    preview_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    request_bytes BLOB NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    envelope_bytes BLOB NOT NULL,
    envelope_sha256 TEXT NOT NULL CHECK (length(envelope_sha256) = 64),
    capability_snapshot_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES app_profiles(profile_id) ON DELETE RESTRICT,
    FOREIGN KEY (capability_snapshot_id) REFERENCES app_capability_snapshots(snapshot_id) ON DELETE RESTRICT
);
