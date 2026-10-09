-- D5 / DATA-01C additive application projections, local exports and backups.
-- Decision projection tables are structurally available but remain empty until
-- E2/VERIFIED_DECISION_PROJECTION_SOURCE_CONTRACT is independently resolved.
-- These read models never become prediction, router, portfolio or execution authority.

-- Scoped artifact identity is needed by D5's composite same-run foreign keys.
-- Valid D4 writes already require a single role per (run, artifact) pair.
CREATE UNIQUE INDEX app_run_artifacts_run_artifact_unique
    ON app_run_artifacts(run_id, artifact_id);

CREATE TABLE app_fixture_projections (
    run_id TEXT NOT NULL,
    fixture_identity TEXT NOT NULL,
    provider_event_id TEXT,
    kickoff_utc TEXT NOT NULL,
    home_label TEXT NOT NULL,
    away_label TEXT NOT NULL,
    competition_identity TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('club', 'international')),
    evidence_artifact_id TEXT NOT NULL,
    projection_policy_id TEXT NOT NULL,
    PRIMARY KEY (run_id, fixture_identity),
    FOREIGN KEY (run_id) REFERENCES app_runs(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, evidence_artifact_id)
        REFERENCES app_run_artifacts(run_id, artifact_id) ON DELETE RESTRICT
);

CREATE TABLE app_opportunity_projections (
    run_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    fixture_identity TEXT NOT NULL,
    market_family TEXT NOT NULL,
    period TEXT NOT NULL,
    outcome_identity TEXT NOT NULL,
    line_text TEXT,
    decimal_odds_text TEXT,
    confidence_value REAL,
    confidence_method TEXT,
    router_disposition TEXT NOT NULL,
    reason_json TEXT NOT NULL,
    decision_artifact_id TEXT NOT NULL,
    PRIMARY KEY (run_id, opportunity_id),
    FOREIGN KEY (run_id, fixture_identity)
        REFERENCES app_fixture_projections(run_id, fixture_identity) ON DELETE RESTRICT,
    FOREIGN KEY (decision_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, decision_artifact_id)
        REFERENCES app_run_artifacts(run_id, artifact_id) ON DELETE RESTRICT,
    CHECK (confidence_value IS NULL OR
           (confidence_value >= 0.0 AND confidence_value <= 1.0))
);

CREATE TABLE app_portfolio_members (
    run_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('SELECTED', 'RESERVE')),
    rank INTEGER NOT NULL CHECK (rank >= 1),
    portfolio_artifact_id TEXT NOT NULL,
    PRIMARY KEY (run_id, role, rank),
    UNIQUE (run_id, opportunity_id),
    FOREIGN KEY (run_id, opportunity_id)
        REFERENCES app_opportunity_projections(run_id, opportunity_id) ON DELETE RESTRICT,
    FOREIGN KEY (portfolio_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, portfolio_artifact_id)
        REFERENCES app_run_artifacts(run_id, artifact_id) ON DELETE RESTRICT
);

CREATE TABLE app_exports (
    export_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    run_id TEXT,
    export_kind TEXT NOT NULL,
    redaction_policy_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PREPARING', 'VERIFIED', 'FAILED')),
    manifest_artifact_id TEXT,
    logical_path TEXT,
    created_at TEXT NOT NULL,
    error_code TEXT,
    FOREIGN KEY (profile_id) REFERENCES app_profiles(profile_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id) REFERENCES app_runs(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (manifest_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    CHECK (state != 'VERIFIED' OR
           (manifest_artifact_id IS NOT NULL AND logical_path IS NOT NULL AND error_code IS NULL))
);

CREATE TABLE app_backups (
    backup_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    release_id TEXT NOT NULL,
    manifest_byte_sha256 TEXT,
    local_locator TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PREPARING', 'VERIFIED', 'FAILED')),
    created_at TEXT NOT NULL,
    verified_at TEXT,
    error_code TEXT,
    FOREIGN KEY (profile_id) REFERENCES app_profiles(profile_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id) REFERENCES app_release_manifests(release_id) ON DELETE RESTRICT,
    CHECK (schema_version >= 1),
    CHECK (manifest_byte_sha256 IS NULL OR
           (length(manifest_byte_sha256) = 64 AND lower(manifest_byte_sha256) = manifest_byte_sha256
            AND manifest_byte_sha256 NOT GLOB '*[^0-9a-f]*')),
    CHECK (state != 'VERIFIED' OR
           (manifest_byte_sha256 IS NOT NULL AND verified_at IS NOT NULL AND error_code IS NULL))
);

CREATE TABLE app_audit_events (
    audit_id TEXT PRIMARY KEY,
    run_id TEXT,
    event_type TEXT NOT NULL,
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES app_runs(run_id) ON DELETE RESTRICT,
    CHECK (length(payload_sha256) = 64 AND lower(payload_sha256) = payload_sha256
           AND payload_sha256 NOT GLOB '*[^0-9a-f]*')
);

CREATE INDEX app_exports_profile_created_idx ON app_exports(profile_id, created_at, export_id);
CREATE INDEX app_backups_profile_created_idx ON app_backups(profile_id, created_at, backup_id);
CREATE INDEX app_audit_events_run_created_idx ON app_audit_events(run_id, created_at, audit_id);

CREATE TRIGGER app_audit_events_no_update
BEFORE UPDATE ON app_audit_events
BEGIN
    SELECT RAISE(ABORT, 'app_audit_events are append-only');
END;

CREATE TRIGGER app_audit_events_no_delete
BEFORE DELETE ON app_audit_events
BEGIN
    SELECT RAISE(ABORT, 'app_audit_events are append-only');
END;
