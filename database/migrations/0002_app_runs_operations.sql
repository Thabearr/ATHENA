-- D4 / DATA-01B durable run control-plane state. Exactly five additive R1
-- application tables. A database ledger is NOT executor authority: no row here
-- launches a worker, provider or delivery. Supported POST /api/v1/runs remains
-- typed 503 DURABLE_RUN_STORE_UNAVAILABLE until reviewed E1 job integration.

-- 1. Exact canonical run identity committed by the atomic admission port.
CREATE TABLE app_runs (
    run_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    preview_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_bytes BLOB NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    envelope_bytes BLOB NOT NULL,
    envelope_sha256 TEXT NOT NULL CHECK (length(envelope_sha256) = 64),
    release_id TEXT NOT NULL,
    state TEXT NOT NULL,
    state_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    receipt_artifact_id TEXT,
    FOREIGN KEY (profile_id) REFERENCES app_profiles(profile_id) ON DELETE RESTRICT,
    FOREIGN KEY (preview_id) REFERENCES app_run_previews(preview_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id) REFERENCES app_release_manifests(release_id) ON DELETE RESTRICT,
    FOREIGN KEY (receipt_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    UNIQUE (profile_id, idempotency_key),
    UNIQUE (preview_id),
    CHECK (state IN ('QUEUED','RUNNING','CANCEL_REQUESTED','TERMINAL','CANCELLED','INTERRUPTED')),
    CHECK (state_version >= 0)
);

-- 2. Attempt ownership with lease fencing tokens. No row is retry authority.
CREATE TABLE app_run_attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    lease_token TEXT NOT NULL UNIQUE,
    worker_instance_id TEXT NOT NULL,
    process_locator_json TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    exit_code INTEGER,
    recovery_disposition TEXT,
    FOREIGN KEY (run_id) REFERENCES app_runs(run_id) ON DELETE RESTRICT,
    UNIQUE (run_id, attempt_number)
);

-- 3. Append-only ordered event truth with exact canonical payloads.
CREATE TABLE app_run_events (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    state_version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES app_runs(run_id) ON DELETE RESTRICT
);

-- 4. External side-effect uncertainty ledger. A row is NOT transport authority
--    and never authorizes automatic resend/confirm after OUTCOME_UNKNOWN.
CREATE TABLE app_external_operations (
    operation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    operation_kind TEXT NOT NULL,
    intent_sha256 TEXT NOT NULL CHECK (length(intent_sha256) = 64),
    authority_sha256 TEXT NOT NULL CHECK (length(authority_sha256) = 64),
    input_artifact_id TEXT,
    idempotency_key TEXT,
    state TEXT NOT NULL,
    prepared_at TEXT NOT NULL,
    sent_at TEXT,
    completed_at TEXT,
    response_artifact_id TEXT,
    error_code TEXT,
    FOREIGN KEY (run_id) REFERENCES app_runs(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (attempt_id) REFERENCES app_run_attempts(attempt_id) ON DELETE RESTRICT,
    FOREIGN KEY (input_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    FOREIGN KEY (response_artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT,
    CHECK (state IN ('PREPARED','SENT','CONFIRMED','FAILED','OUTCOME_UNKNOWN'))
);

-- 5. Run artifact roles. retained_root=1 rows are never cascade-deleted.
CREATE TABLE app_run_artifacts (
    run_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    role TEXT NOT NULL,
    retained_root INTEGER NOT NULL CHECK (retained_root IN (0,1)),
    PRIMARY KEY (run_id, artifact_id, role),
    FOREIGN KEY (run_id) REFERENCES app_runs(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (artifact_id) REFERENCES app_artifacts(artifact_id) ON DELETE RESTRICT
);
