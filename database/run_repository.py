"""Offline D4 durable control-plane storage; never launches or transports work.

Genesis is RUN_QUEUED, sequence 1, state_version 0. Presentation profile
identity is not MAIN/SHADOW authority. Each operation owns its connection.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import uuid

from database.app_migration_evidence import contained, publish
from database.app_root_lock import app_root_lock
from database.app_repository import release_provenance, logical_locator
from database.app_migrations import (
    app_store_path, connect_app_store, expected_schema_structure,
    read_app_migrations, verify_app_schema,
)
from domain.run_contracts import canonical_json_bytes, RunRequest, RunReceipt
from domain.execution_envelope import ExecutionEnvelope, ExecutionPreview, evaluate_execution_envelope
from runtime.release_identity import (
    DEVELOPMENT_IDENTITY_POLICY_ID, TRUST_MODE, DevelopmentCheckoutIdentity,
    _parse_manifest, _validate_manifest_shape,
)
from services.athena_run_service import AthenaRunService
from services.athena_preview_service import (
    AdmissionLookupResult, AdmissionResult, AdmissionReplayIdentity,
    _source_identity,
)

LOCAL_PROFILE_ID = "local-default"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_TRANSITIONS = {
    "QUEUED": {"RUNNING", "CANCELLED", "INTERRUPTED"},
    "RUNNING": {"CANCEL_REQUESTED", "INTERRUPTED"},
    "CANCEL_REQUESTED": {"CANCELLED", "INTERRUPTED"},
}


class RunRepositoryError(ValueError):
    """Invalid or inconsistent durable control-plane evidence."""


class RunStateConflict(RunRepositoryError):
    """Compare-and-swap or state transition rejected."""


class RunLeaseFenced(RunRepositoryError):
    """Attempt no longer owns this run."""


class ExternalOperationViolation(RunRepositoryError):
    """Operation would exceed the offline storage boundary."""


class HistoricalReleaseUnavailable(RunRepositoryError):
    """Original release evidence cannot be authenticated; never execution authority."""

    code = "HISTORICAL_RELEASE_UNAVAILABLE"


class ReceiptProducerUnavailable(RunRepositoryError):
    """Canonical receipt claims a producer the retained source cannot prove."""

    code = "RECEIPT_PRODUCER_UNAVAILABLE"


class TerminalEvidenceUnavailable(RunRepositoryError):
    """Retained terminal receipt evidence is missing, inconsistent or unverified."""

    code = "TERMINAL_EVIDENCE_UNAVAILABLE"


def _utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise RunRepositoryError("clock must return an aware UTC datetime")
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _identity(value):
    if type(value) is not str or _RUN_ID.fullmatch(value) is None:
        raise RunRepositoryError("identity outside reviewed vocabulary")
    return value


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RunRepositoryError("digest must be lowercase SHA-256")
    return value


class DurableRunRepository:
    """Explicit offline seam. Does not migrate or wire production admission."""

    def __init__(self, resources, writable_roots, *, clock=None):
        self._path = app_store_path(writable_roots)
        self._resources = resources
        self._data_root = writable_roots.data_root
        self.verified_identity = resources.identity
        migrations = read_app_migrations(resources)
        self._structure = expected_schema_structure(migrations)
        self._identities = [(version, digest) for version, _, _, digest in migrations]
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def _operation(self, *, write=False):
        with app_root_lock(self._data_root):
            migrations = read_app_migrations(self._resources)
            if [(version, digest) for version, _, _, digest in migrations] != self._identities:
                raise RunRepositoryError("runtime migration source identity drift")
            contained(self._path.parent, self._path.name)
            for suffix in ("-wal", "-shm", "-journal"):
                contained(self._path.parent, self._path.name + suffix)
            conn = connect_app_store(self._path, readonly=not write,
                                     synchronous="FULL" if write else "NORMAL")
            try:
                conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                verify_app_schema(conn, expected_structure=self._structure)
                rows = conn.execute("SELECT version, migration_sha256 FROM app_schema_migrations ORDER BY version").fetchall()
                if rows != self._identities:
                    raise RunRepositoryError("migration identity drift")
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _lookup(self, conn, identity):
        row = conn.execute(
            "SELECT run_id, preview_id, envelope_sha256 FROM app_runs WHERE profile_id=? AND idempotency_key=?",
            (LOCAL_PROFILE_ID, identity.idempotency_key),
        ).fetchone()
        if row is None:
            return AdmissionLookupResult("not_found")
        self._verify_run_identity(conn, row[0], current=False)
        if row[1:] != (identity.preview_id, identity.execution_envelope_sha256):
            return AdmissionLookupResult("idempotency_conflict")
        return AdmissionLookupResult("idempotent_replay", _identity(row[0]))

    def _verify_release(self, conn, release_id, source):
        row = conn.execute("SELECT source_mode,source_commit,platform,architecture,build_id,manifest_bytes,manifest_byte_sha256,trust_mode,signature_key_id,verified_at FROM app_release_manifests WHERE release_id=?", (release_id,)).fetchone()
        if row is None or row[8] is not None:
            raise HistoricalReleaseUnavailable("original release provenance unavailable or unsupported signature claim")
        try:
            if _utc(datetime.fromisoformat(row[9].replace("Z", "+00:00"))) != row[9]:
                raise ValueError("noncanonical verification time")
            if source.kind == "PINNED_RELEASE_MANIFEST":
                raw = row[5]
                manifest = _parse_manifest(raw)
                _validate_manifest_shape(manifest)
                if (hashlib.sha256(raw).hexdigest() != source.manifest_sha256
                        or row[6] != source.manifest_sha256
                        or row[:5] != ("INSTALLED_RELEASE", None, source.platform_tag,
                                       source.architecture_tag, source.build_id)
                        or row[7] != TRUST_MODE or row[7] != source.trust_mode
                        or release_id != source.release_id
                        or any(manifest[key] != getattr(source, field) for key, field in (
                            ("release_id", "release_id"), ("build_id", "build_id"),
                            ("platform_tag", "platform_tag"), ("architecture_tag", "architecture_tag"),
                            ("policy_id", "manifest_policy_id"), ("schema_version", "manifest_schema_version")))):
                    raise ValueError("original manifest pin/metadata mismatch")
            elif source.kind == "GIT_COMMIT":
                if (release_id != "development-checkout:" + source.value
                        or row[0] != "DEVELOPMENT_CHECKOUT" or row[1] != source.value
                        or row[4] != source.value or row[5:7] != (None, None)
                        or row[7] != DEVELOPMENT_IDENTITY_POLICY_ID
                        or row[2] not in {"windows", "linux"} or row[3] not in {"x86_64", "aarch64"}):
                    raise ValueError("original development provenance mismatch")
                if type(self.verified_identity) is not DevelopmentCheckoutIdentity:
                    raise HistoricalReleaseUnavailable("historical Git producer object unavailable in installed mode")
                result = subprocess.run(["git", "cat-file", "-t", source.value],
                                        cwd=self.verified_identity.repository_root,
                                        check=False, capture_output=True, timeout=10)
                if result.returncode or result.stdout.strip() != b"commit":
                    raise HistoricalReleaseUnavailable("historical Git commit object unavailable")
            else:
                raise HistoricalReleaseUnavailable("unsupported original release provenance")
        except HistoricalReleaseUnavailable:
            raise
        except (ValueError, TypeError, AttributeError, OSError, subprocess.SubprocessError) as exc:
            raise HistoricalReleaseUnavailable("original release provenance verification failed") from exc
        return row

    def _verify_capability(self, conn, preview_id, envelope, request_bytes, release_id, *, now=None):
        row = conn.execute("SELECT p.profile_id,p.request_bytes,p.request_sha256,p.envelope_bytes,p.envelope_sha256,p.expires_at,c.release_id,c.profile,c.report_bytes,c.report_sha256,c.evaluated_at,c.expires_at FROM app_run_previews p JOIN app_capability_snapshots c ON c.snapshot_id=p.capability_snapshot_id WHERE p.preview_id=?", (preview_id,)).fetchone()
        expected = (LOCAL_PROFILE_ID, request_bytes, envelope.request_sha256,
                    envelope.canonical_bytes, envelope.canonical_sha256, _utc(envelope.expires_at),
                    release_id, envelope.authority_manifest.authority_profile)
        if row is None or row[:8] != expected:
            raise RunRepositoryError("retained preview/capability identity mismatch")
        if type(row[8]) is not bytes or hashlib.sha256(row[8]).hexdigest() != row[9]:
            raise RunRepositoryError("retained capability report digest mismatch")
        preview = ExecutionPreview.from_json_bytes(row[8])
        if (preview.canonical_bytes != evaluate_execution_envelope(envelope).canonical_bytes
                or row[10] != _utc(envelope.issued_at) or row[11] != _utc(envelope.expires_at)):
            raise RunRepositoryError("retained capability report/expiry mismatch")
        if now is not None and now >= preview.expires_at:
            raise RunRepositoryError("capability snapshot expired")
        return preview

    @staticmethod
    def _require_current_authority(envelope):
        request = RunRequest.from_json_bytes(envelope.request_bytes)
        if (AthenaRunService.authority_manifest_for(request) != envelope.authority_manifest
                or evaluate_execution_envelope(envelope).blockers):
            raise RunRepositoryError("current authority differs or preview is blocked")

    def _verify_run_identity(self, conn, run_id, *, current=True):
        row = conn.execute("SELECT request_bytes,request_sha256,envelope_bytes,envelope_sha256,release_id,preview_id,state,state_version,receipt_artifact_id FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise RunRepositoryError("unknown run")
        request = RunRequest.from_json_bytes(row[0])
        envelope = ExecutionEnvelope.from_json_bytes(row[2])
        if (request.canonical_sha256 != row[1] or envelope.canonical_sha256 != row[3]
                or envelope.request_sha256 != row[1] or envelope.request_bytes != row[0]):
            raise RunRepositoryError("run source/request/envelope/release identity drift")
        self._verify_release(conn, row[4], envelope.source_identity)
        self._verify_capability(conn, row[5], envelope, row[0], row[4])
        self._verify_terminal_evidence(conn, run_id, row, envelope)
        if current:
            if (envelope.source_identity != _source_identity(self._resources)
                    or row[4] != release_provenance(self.verified_identity, verified_at=self._clock())["release_id"]):
                raise RunRepositoryError("active run release differs from current verified source")
            self._require_current_authority(envelope)
        return envelope

    def _verify_terminal_evidence(self, conn, run_id, row, envelope):
        """Bounded historical proof of projected terminal state on every read.

        Bidirectional integrity: TERMINAL requires a deterministic receipt
        pointer, exactly one same-run RUN_RECEIPT linkage referencing it, the
        retained receipt artifact metadata and canonical file bytes, the
        receipt's original producer/release evidence and exactly one verified
        RUN_TERMINAL projection event, with no post-terminal events. A
        nonterminal run must carry no receipt pointer, no RUN_TERMINAL event at
        any sequence and no RUN_RECEIPT linkage, so a resurrected or forged
        run fails closed before any snapshot, event page, idempotent replay or
        mutation authority is returned; a published but unprojected receipt
        stays an honest nonterminal crash gap. Historical and current authority
        stay separate: this never demands current-release eligibility and never
        invents producer provenance.
        """
        state, state_version, receipt_artifact_id = row[6], row[7], row[8]
        try:
            if state != "TERMINAL":
                if receipt_artifact_id is not None:
                    raise TerminalEvidenceUnavailable("nonterminal run carries a projected receipt pointer")
                if conn.execute("SELECT 1 FROM app_run_events WHERE run_id=? AND event_type='RUN_TERMINAL'",
                                (run_id,)).fetchone():
                    raise TerminalEvidenceUnavailable("nonterminal run carries a terminal projection event")
                if conn.execute("SELECT 1 FROM app_run_artifacts WHERE run_id=? AND role='RUN_RECEIPT'",
                                (run_id,)).fetchone():
                    raise TerminalEvidenceUnavailable("nonterminal run carries a projected receipt linkage")
                return
            if type(receipt_artifact_id) is not str or not receipt_artifact_id.startswith("receipt-"):
                raise TerminalEvidenceUnavailable("terminal receipt artifact identity is not deterministic")
            digest = receipt_artifact_id[len("receipt-"):]
            _sha(digest)
            locator = "run-receipts/" + digest + ".json"
            links = conn.execute(
                "SELECT run_id,role,retained_root FROM app_run_artifacts WHERE artifact_id=?",
                (receipt_artifact_id,)).fetchall()
            if links != [(run_id, "RUN_RECEIPT", 1)]:
                raise TerminalEvidenceUnavailable("terminal receipt linkage is missing, wrong-role or cross-run")
            if conn.execute("SELECT 1 FROM app_run_artifacts WHERE run_id=? AND role='RUN_RECEIPT' AND artifact_id<>?",
                            (run_id, receipt_artifact_id)).fetchone():
                raise TerminalEvidenceUnavailable("terminal run carries additional receipt role linkage")
            artifact = conn.execute(
                "SELECT byte_sha256,canonical_sha256,byte_count,media_type,artifact_kind,logical_path,evidence_class,verification_policy_id "
                "FROM app_artifacts WHERE artifact_id=?", (receipt_artifact_id,)).fetchone()
            if (artifact is None or artifact[:2] != (digest, digest)
                    or artifact[3] != "application/json" or artifact[4] != "RUN_RECEIPT"
                    or artifact[5] != locator or artifact[6] != "RETAINED"
                    or artifact[7] != "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1"):
                raise TerminalEvidenceUnavailable("retained receipt artifact metadata mismatch")
            raw = contained(self._data_root, logical_locator(artifact[5])).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest or len(raw) != artifact[2]:
                raise TerminalEvidenceUnavailable("retained receipt bytes/digest/count mismatch")
            value = json.loads(raw)
            keys = {"policy_id", "run_id", "request_sha256", "envelope_sha256", "release_id",
                    "expected_version", "attempt_id", "lease_token", "receipt"}
            if (type(value) is not dict or set(value) != keys or canonical_json_bytes(value) != raw
                    or value["policy_id"] != "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1"
                    or type(value["expected_version"]) is not int or value["expected_version"] < 0):
                raise TerminalEvidenceUnavailable("retained receipt wrapper is not canonical reviewed policy")
            if (value["run_id"] != run_id or value["request_sha256"] != row[1]
                    or value["envelope_sha256"] != row[3] or value["release_id"] != row[4]
                    or value["expected_version"] != state_version - 1):
                raise TerminalEvidenceUnavailable("retained receipt wrapper bindings drift")
            attempt = conn.execute("SELECT lease_token FROM app_run_attempts WHERE run_id=? AND attempt_id=?",
                                   (run_id, _identity(value["attempt_id"]))).fetchone()
            if attempt is None or attempt[0] != value["lease_token"]:
                raise TerminalEvidenceUnavailable("retained receipt attempt lease binding drift")
            receipt = RunReceipt.from_dict(value["receipt"])
            if (receipt.request.canonical_sha256 != row[1]
                    or receipt.authority_manifest != envelope.authority_manifest
                    or receipt.share_code_result is not None):
                raise TerminalEvidenceUnavailable("retained receipt contract identity drift")
            self._verify_receipt_producer(conn, run_id, receipt, envelope, row[4])
            events = conn.execute(
                "SELECT sequence,state_version,payload_bytes,payload_sha256 FROM app_run_events "
                "WHERE run_id=? AND event_type='RUN_TERMINAL'", (run_id,)).fetchall()
            if len(events) != 1:
                raise TerminalEvidenceUnavailable("terminal projection event missing or duplicated")
            sequence, event_version, payload, payload_sha = events[0]
            if (event_version != state_version or type(payload) is not bytes
                    or hashlib.sha256(payload).hexdigest() != payload_sha
                    or canonical_json_bytes(json.loads(payload)) != payload
                    or json.loads(payload) != {"receipt_sha256": digest}):
                raise TerminalEvidenceUnavailable("terminal projection event identity drift")
            if conn.execute("SELECT 1 FROM app_run_events WHERE run_id=? AND sequence>?",
                            (run_id, sequence)).fetchone():
                raise TerminalEvidenceUnavailable("events recorded after terminal projection")
        except (TerminalEvidenceUnavailable, HistoricalReleaseUnavailable,
                ReceiptProducerUnavailable, RunLeaseFenced):
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise TerminalEvidenceUnavailable("retained terminal evidence is unverified") from exc

    def lookup(self, identity):
        with self._operation() as conn:
            return self._lookup(conn, identity)

    def admit(self, candidate):
        identity = AdmissionReplayIdentity(candidate.idempotency_key, candidate.preview_id,
                                           candidate.execution_envelope_sha256)
        with self._operation(write=True) as conn:
            replay = self._lookup(conn, identity)
            if replay.disposition != "not_found":
                return AdmissionResult(replay.disposition, replay.run_id)
            if conn.execute("SELECT 1 FROM app_runs WHERE preview_id=?", (candidate.preview_id,)).fetchone():
                return AdmissionResult("preview_consumed_conflict")
            now = self._clock()
            stamp = _utc(now)
            if now >= candidate.preview_expires_at:
                return AdmissionResult("preview_expired")
            row = conn.execute(
                "SELECT p.profile_id,p.request_bytes,p.request_sha256,p.envelope_bytes,p.envelope_sha256,p.expires_at,c.release_id "
                "FROM app_run_previews p JOIN app_capability_snapshots c ON c.snapshot_id=p.capability_snapshot_id WHERE p.preview_id=?",
                (candidate.preview_id,),
            ).fetchone()
            expected = (LOCAL_PROFILE_ID, candidate.request_bytes, candidate.request_sha256,
                        candidate.execution_envelope_bytes, candidate.execution_envelope_sha256,
                        _utc(candidate.preview_expires_at))
            if row is None or row[:6] != expected:
                raise RunRepositoryError("candidate differs from retained preview")
            if row[6] != release_provenance(self.verified_identity, verified_at=now)["release_id"]:
                raise RunRepositoryError("preview release differs from runtime source")
            for raw, digest in ((row[1], row[2]), (row[3], row[4])):
                if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != digest:
                    raise RunRepositoryError("preview digest mismatch")
            request = RunRequest.from_json_bytes(row[1])
            envelope = ExecutionEnvelope.from_json_bytes(row[3])
            source = _source_identity(self._resources)
            if (envelope.request_sha256 != request.canonical_sha256
                    or envelope.authority_manifest_sha256 != candidate.authority_manifest_sha256
                    or envelope.source_identity != source
                    or hashlib.sha256(canonical_json_bytes(source)).hexdigest() != candidate.source_identity_sha256):
                raise RunRepositoryError("candidate authority/source identity mismatch")
            self._verify_release(conn, row[6], envelope.source_identity)
            preview = self._verify_capability(conn, candidate.preview_id, envelope,
                                              row[1], row[6], now=now)
            self._require_current_authority(envelope)
            if preview.blockers:
                raise RunRepositoryError("blocked capability snapshot cannot admit a run")
            run_id = _identity("run-" + uuid.uuid4().hex)
            conn.execute(
                "INSERT INTO app_runs(run_id,profile_id,preview_id,idempotency_key,request_bytes,request_sha256,envelope_bytes,envelope_sha256,release_id,state,state_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'QUEUED',0,?,?)",
                (run_id, LOCAL_PROFILE_ID, candidate.preview_id, candidate.idempotency_key,
                 row[1], row[2], row[3], row[4], row[6], stamp, stamp),
            )
            self._event(conn, run_id, 0, "RUN_QUEUED", {
                "preview_id": candidate.preview_id, "idempotency_key": candidate.idempotency_key}, stamp)
            return AdmissionResult("admitted", run_id)

    @staticmethod
    def _event(conn, run_id, version, event_type, payload, stamp):
        raw = canonical_json_bytes(payload)
        sequence = conn.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM app_run_events WHERE run_id=?", (run_id,)).fetchone()[0]
        conn.execute("INSERT INTO app_run_events VALUES(?,?,?,?,?,?,?)",
                     (run_id, sequence, version, _identity(event_type), raw,
                      hashlib.sha256(raw).hexdigest(), stamp))
        return sequence

    def _fence(self, conn, run_id, attempt_id, lease_token):
        row = conn.execute(
            "SELECT lease_token,finished_at,attempt_number FROM app_run_attempts WHERE run_id=? AND attempt_id=?",
            (run_id, attempt_id),
        ).fetchone()
        current = conn.execute("SELECT MAX(attempt_number) FROM app_run_attempts WHERE run_id=?", (run_id,)).fetchone()[0]
        if row is None or row[0] != lease_token or row[1] is not None or row[2] != current:
            raise RunLeaseFenced("stale or cross-run attempt")
        self._verify_run_identity(conn, run_id)
        state = conn.execute("SELECT state FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
        if state is None or state[0] not in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
            raise RunLeaseFenced("run no longer accepts attempt writes")

    def claim_attempt(self, run_id, *, worker_instance_id, process_locator):
        _identity(run_id)
        _identity(worker_instance_id)
        if (type(process_locator) is not dict or set(process_locator) != {"kind", "label"}
                or process_locator["kind"] != "OFFLINE_TEST"):
            raise RunRepositoryError("only safe offline process locators are accepted")
        label = process_locator["label"]
        if type(label) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", label) is None:
            raise RunRepositoryError("process label must be a bounded non-path identity")
        with self._operation(write=True) as conn:
            row = conn.execute("SELECT state FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row[0] not in {"QUEUED", "RUNNING"}:
                raise RunStateConflict("run cannot claim an attempt")
            self._verify_run_identity(conn, run_id)
            if conn.execute("SELECT 1 FROM app_run_attempts WHERE run_id=? AND finished_at IS NULL", (run_id,)).fetchone():
                raise RunLeaseFenced("unfinished attempt already owns run")
            number = conn.execute("SELECT COALESCE(MAX(attempt_number),0)+1 FROM app_run_attempts WHERE run_id=?", (run_id,)).fetchone()[0]
            attempt_id, lease = "attempt-" + uuid.uuid4().hex, uuid.uuid4().hex
            stamp = _utc(self._clock())
            conn.execute("INSERT INTO app_run_attempts(attempt_id,run_id,attempt_number,lease_token,worker_instance_id,process_locator_json,heartbeat_at,started_at) VALUES(?,?,?,?,?,?,?,?)",
                         (attempt_id, run_id, number, lease, worker_instance_id,
                          canonical_json_bytes(process_locator).decode("utf-8"), stamp, stamp))
            return attempt_id, lease, number

    def heartbeat(self, run_id, attempt_id, lease_token):
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            conn.execute("UPDATE app_run_attempts SET heartbeat_at=? WHERE attempt_id=?",
                         (_utc(self._clock()), attempt_id))

    def finish_attempt(self, run_id, attempt_id, lease_token, *, exit_code):
        if type(exit_code) is not int:
            raise RunRepositoryError("exit code must be an exact integer")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            conn.execute("UPDATE app_run_attempts SET finished_at=?,exit_code=? WHERE attempt_id=?",
                         (_utc(self._clock()), exit_code, attempt_id))

    def request_cancel(self, run_id, *, expected_version):
        if type(expected_version) is not int or expected_version < 0:
            raise RunStateConflict("invalid state version")
        with self._operation(write=True) as conn:
            row = conn.execute("SELECT state,state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise RunStateConflict("unknown run")
            self._verify_run_identity(conn, run_id)
            if row[0] in {"CANCEL_REQUESTED", "CANCELLED", "TERMINAL", "INTERRUPTED"}:
                return row[1]
            if row[1] != expected_version:
                raise RunStateConflict("cancellation CAS rejected")
            state = "CANCELLED" if row[0] == "QUEUED" else "CANCEL_REQUESTED"
            stamp = _utc(self._clock())
            conn.execute("UPDATE app_runs SET state=?,state_version=state_version+1,updated_at=? WHERE run_id=? AND state_version=?",
                         (state, stamp, run_id, expected_version))
            self._event(conn, run_id, expected_version + 1, "RUN_" + state, {}, stamp)
            return expected_version + 1

    def read_events(self, run_id, *, after_sequence=0, limit=100):
        _identity(run_id)
        if type(after_sequence) is not int or after_sequence < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise RunRepositoryError("invalid event page")
        with self._operation() as conn:
            self._verify_run_identity(conn, run_id, current=False)
            rows = conn.execute("SELECT sequence,state_version,event_type,payload_bytes,payload_sha256,observed_at FROM app_run_events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                                (run_id, after_sequence, limit)).fetchall()
            for index, row in enumerate(rows, start=1):
                if row[0] != after_sequence + index or row[1] < 0:
                    raise RunRepositoryError("event sequence/version drift")
                if row[0] == 1 and row[1:3] != (0, "RUN_QUEUED"):
                    raise RunRepositoryError("event genesis drift")
                if hashlib.sha256(row[3]).hexdigest() != row[4]:
                    raise RunRepositoryError("event evidence digest mismatch")
                if canonical_json_bytes(json.loads(row[3])) != row[3]:
                    raise RunRepositoryError("event payload is not canonical")
            return rows

    def transition_run(self, run_id, *, expected_version, state, attempt_id, lease_token):
        if type(expected_version) is not int or expected_version < 0:
            raise RunStateConflict("invalid state version")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = conn.execute("SELECT state,state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row[1] != expected_version or state not in _TRANSITIONS.get(row[0], set()):
                raise RunStateConflict("state CAS rejected; TERMINAL requires receipt projection")
            stamp = _utc(self._clock())
            conn.execute("UPDATE app_runs SET state=?,state_version=state_version+1,updated_at=? WHERE run_id=? AND state_version=?",
                         (state, stamp, run_id, expected_version))
            self._event(conn, run_id, expected_version + 1, "RUN_" + state, {}, stamp)
            return expected_version + 1

    def append_event(self, run_id, *, attempt_id, lease_token, event_type, payload):
        _identity(event_type)
        if event_type.startswith("RUN_"):
            raise RunRepositoryError("state events belong to transactional state projection")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            version = conn.execute("SELECT state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0]
            return self._event(conn, run_id, version, event_type, payload, _utc(self._clock()))

    def prepare_external_operation(self, run_id, *, attempt_id, lease_token,
                                   operation_kind, intent_sha256, authority_sha256,
                                   input_artifact_id=None, idempotency_key=None):
        if operation_kind != "TESTING_SYNTHETIC":
            raise ExternalOperationViolation("production operation kinds are disabled")
        _sha(intent_sha256)
        _sha(authority_sha256)
        if idempotency_key is not None:
            _identity(idempotency_key)
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            state = conn.execute("SELECT state FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0]
            if state != "RUNNING":
                raise ExternalOperationViolation("operation requires RUNNING offline attempt")
            if input_artifact_id is not None:
                self._require_artifact_role(conn, run_id, input_artifact_id, "EXTERNAL_INPUT")
            operation_id = "operation-" + uuid.uuid4().hex
            conn.execute("INSERT INTO app_external_operations(operation_id,run_id,attempt_id,operation_kind,intent_sha256,authority_sha256,input_artifact_id,idempotency_key,state,prepared_at) VALUES(?,?,?,?,?,?,?,?,'PREPARED',?)",
                         (operation_id, run_id, attempt_id, operation_kind, intent_sha256,
                          authority_sha256, input_artifact_id, idempotency_key, _utc(self._clock())))
            return operation_id

    def _require_artifact_role(self, conn, run_id, artifact_id, role):
        _identity(artifact_id)
        if not conn.execute("SELECT 1 FROM app_run_artifacts WHERE run_id=? AND artifact_id=? AND role=? AND retained_root=1",
                            (run_id, artifact_id, role)).fetchone():
            raise RunRepositoryError("artifact is not retained for this run/role")
        if role == "EXTERNAL_RESPONSE" and conn.execute(
                "SELECT 1 FROM app_run_artifacts WHERE artifact_id=? AND role=? AND run_id<>?",
                (artifact_id, role, run_id)).fetchone():
            raise RunRepositoryError("response artifact belongs to another run")
        row = conn.execute("SELECT logical_path,byte_sha256,byte_count,artifact_kind FROM app_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
        try:
            if row is None or row[3] != role:
                raise RunRepositoryError("retained artifact kind/role mismatch")
            raw = contained(self._data_root, logical_locator(row[0])).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row[1] or len(raw) != row[2]:
                raise RunRepositoryError("retained artifact bytes mismatch")
        except (OSError, ValueError) as exc:
            raise RunRepositoryError("retained artifact is missing, unsafe or unverified") from exc

    def link_run_artifact(self, run_id, artifact_id, *, role, attempt_id, lease_token):
        if role not in {"EXTERNAL_INPUT", "EXTERNAL_RESPONSE"}:
            raise RunRepositoryError("receipt artifacts require receipt-first projection")
        _identity(artifact_id)
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            if role == "EXTERNAL_RESPONSE" and conn.execute(
                    "SELECT 1 FROM app_run_artifacts WHERE artifact_id=? AND role=? AND run_id<>?",
                    (artifact_id, role, run_id)).fetchone():
                raise RunRepositoryError("response artifact belongs to another run")
            row = conn.execute("SELECT logical_path,byte_sha256,byte_count,artifact_kind FROM app_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
            if row is None or row[3] != role:
                raise RunRepositoryError("missing retained artifact or kind/role mismatch")
            raw = contained(self._data_root, logical_locator(row[0])).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row[1] or len(raw) != row[2]:
                raise RunRepositoryError("retained artifact bytes mismatch")
            conn.execute("INSERT OR IGNORE INTO app_run_artifacts VALUES(?,?,?,1)",
                         (run_id, artifact_id, role))

    def transition_external_operation(self, run_id, operation_id, *, attempt_id,
                                      lease_token, expected_state, state,
                                      response_artifact_id=None, error_code=None):
        transitions = {"PREPARED": {"SENT", "FAILED"},
                       "SENT": {"CONFIRMED", "FAILED", "OUTCOME_UNKNOWN"}}
        if state not in transitions.get(expected_state, set()):
            raise ExternalOperationViolation("operation transition/retry forbidden")
        if state == "CONFIRMED" and response_artifact_id is None:
            raise ExternalOperationViolation("CONFIRMED requires a retained proven response")
        if state == "FAILED" and response_artifact_id is None and error_code not in {
                "SYNTHETIC_LOCAL_FAILURE", "SYNTHETIC_CONFIRMED_FAILURE"}:
            raise ExternalOperationViolation("response-free failure requires a reviewed synthetic failure code")
        if error_code is not None:
            _identity(error_code)
            if state not in {"FAILED", "OUTCOME_UNKNOWN"}:
                raise ExternalOperationViolation("error code requires failure/uncertainty state")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = conn.execute("SELECT attempt_id,state,operation_kind FROM app_external_operations WHERE run_id=? AND operation_id=?",
                               (run_id, operation_id)).fetchone()
            if row != (attempt_id, expected_state, "TESTING_SYNTHETIC"):
                raise ExternalOperationViolation("operation owner/state mismatch")
            if expected_state == "PREPARED" and state == "SENT":
                if conn.execute("SELECT state FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0] != "RUNNING":
                    raise ExternalOperationViolation("cancellation forbids a new send transition")
            if response_artifact_id is not None:
                if state not in {"CONFIRMED", "FAILED"}:
                    raise ExternalOperationViolation("response artifact requires a known result")
                self._require_artifact_role(conn, run_id, response_artifact_id, "EXTERNAL_RESPONSE")
            stamp = _utc(self._clock())
            conn.execute("UPDATE app_external_operations SET state=?,sent_at=CASE WHEN ?='SENT' THEN ? ELSE sent_at END,completed_at=CASE WHEN ? IN ('CONFIRMED','FAILED','OUTCOME_UNKNOWN') THEN ? ELSE completed_at END,response_artifact_id=?,error_code=? WHERE operation_id=?",
                         (state, state, stamp, state, stamp, response_artifact_id, error_code, operation_id))

    def recover_attempt(self, run_id, attempt_id, lease_token):
        """Offline explicit recovery, never retries operations or launches work."""
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            stamp = _utc(self._clock())
            conn.execute("UPDATE app_external_operations SET state='OUTCOME_UNKNOWN',completed_at=?,error_code='OFFLINE_RECOVERY' WHERE run_id=? AND attempt_id=? AND state='SENT'",
                         (stamp, run_id, attempt_id))
            conn.execute("UPDATE app_run_attempts SET finished_at=?,recovery_disposition='OFFLINE_INTERRUPTED' WHERE attempt_id=?",
                         (stamp, attempt_id))
            row = conn.execute("SELECT state,state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row[0] in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
                conn.execute("UPDATE app_runs SET state='INTERRUPTED',state_version=state_version+1,updated_at=? WHERE run_id=?", (stamp, run_id))
                self._event(conn, run_id, row[1] + 1, "RUN_INTERRUPTED", {}, stamp)

    def run_snapshot(self, run_id):
        _identity(run_id)
        with self._operation() as conn:
            cursor = conn.execute("SELECT * FROM app_runs WHERE run_id=?", (run_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            self._verify_run_identity(conn, run_id, current=False)
            result = dict(zip((column[0] for column in cursor.description), row))
            for raw_key, digest_key in (("request_bytes", "request_sha256"), ("envelope_bytes", "envelope_sha256")):
                if hashlib.sha256(result[raw_key]).hexdigest() != result[digest_key]:
                    raise RunRepositoryError("run immutable identity digest mismatch")
        return result

    def read_receipt_bytes(self, run_id):
        """Return proven terminal receipt wrapper bytes, or None when absent.

        E1 durable-read port over already-verified terminal evidence. Unknown
        runs return None; nonterminal runs return None (no receipt produced).
        Any inconsistency fails closed; this never invents provenance.
        """
        _identity(run_id)
        with self._operation() as conn:
            row = conn.execute(
                "SELECT state,receipt_artifact_id FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                return None
            if row[0] != "TERMINAL":
                return None
            self._verify_run_identity(conn, run_id, current=False)
            artifact_id = row[1]
            if type(artifact_id) is not str or not artifact_id.startswith("receipt-"):
                raise RunRepositoryError("terminal receipt artifact identity drift")
            digest = artifact_id[len("receipt-"):]
            _sha(digest)
            artifact = conn.execute(
                "SELECT logical_path,byte_sha256,byte_count FROM app_artifacts WHERE artifact_id=?",
                (artifact_id,)).fetchone()
            if artifact is None or artifact[1] != digest:
                raise RunRepositoryError("retained receipt artifact mismatch")
            raw = contained(self._data_root, logical_locator(artifact[0])).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest or len(raw) != artifact[2]:
                raise RunRepositoryError("retained receipt bytes mismatch")
            value = json.loads(raw)
            if (canonical_json_bytes(value) != raw
                    or value.get("run_id") != run_id
                    or value.get("policy_id") != "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1"):
                raise RunRepositoryError("terminal receipt wrapper mismatch")
            return canonical_json_bytes(RunReceipt.from_dict(value["receipt"]))

    def list_run_history(self):
        """Return ordered durable run rows for the E1 history projection.

        Ordered by creation time then run identity for stable pagination. Each
        row carries the exact bytes needed to derive the presentation profile
        (MAIN/SHADOW) without trusting a stored label. No worker, provider, or
        delivery work is performed here.
        """
        with self._operation() as conn:
            cursor = conn.execute(
                "SELECT run_id,state,state_version,created_at,updated_at,request_bytes "
                "FROM app_runs ORDER BY created_at,run_id")
            rows = cursor.fetchall()
            history = []
            for run_id, state, version, created, updated, request_bytes in rows:
                self._verify_run_identity(conn, run_id, current=False)
                if type(request_bytes) is not bytes:
                    raise RunRepositoryError("run request bytes drift")
                history.append({
                    "run_id": _identity(run_id),
                    "state": state,
                    "state_version": version,
                    "created_at": created,
                    "updated_at": updated,
                    "request_bytes": request_bytes,
                })
            return history

    def _verify_receipt_producer(self, conn, run_id, receipt, envelope, release_id):
        provenance = self._verify_release(conn, release_id, envelope.source_identity)
        if envelope.source_identity.kind != "GIT_COMMIT" or provenance[1] is None:
            raise ReceiptProducerUnavailable("installed hash pin has no independently verified producer commit; named future dependency E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE remains open")
        if receipt.exact_commit_sha != provenance[1] or receipt.exact_commit_sha != envelope.source_identity.value:
            raise ReceiptProducerUnavailable("receipt producer commit differs from verified run source")
        expected = {"run_id": run_id, "execution_envelope_sha256": envelope.canonical_sha256,
                    "release_id": release_id}
        if any(receipt.evidence.get(key) != value for key, value in expected.items()):
            raise ReceiptProducerUnavailable("receipt run/envelope/release producer binding mismatch")

    def publish_terminal_receipt(self, run_id, *, receipt_bytes, expected_version, attempt_id, lease_token):
        """Publish immutable offline projection evidence BEFORE changing SQLite.

        A successful publish followed by a crash is reconciled explicitly. This
        is storage projection evidence, not executor completion authority.
        """
        with self._operation() as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            receipt = RunReceipt.from_json_bytes(receipt_bytes)
            row = conn.execute("SELECT request_sha256,envelope_sha256,release_id,state,state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row[3] not in {"RUNNING", "CANCEL_REQUESTED"} or row[4] != expected_version:
                raise RunStateConflict("receipt state CAS rejected")
            if receipt.request.canonical_sha256 != row[0] or receipt.share_code_result is not None:
                raise RunRepositoryError("receipt request mismatch or disabled delivery result")
            envelope_raw = conn.execute("SELECT envelope_bytes FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0]
            envelope = ExecutionEnvelope.from_json_bytes(envelope_raw)
            if receipt.authority_manifest != envelope.authority_manifest:
                raise RunRepositoryError("receipt authority mismatch")
            self._verify_receipt_producer(conn, run_id, receipt, envelope, row[2])
            value = {"policy_id": "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1",
                     "run_id": run_id, "request_sha256": row[0], "envelope_sha256": row[1],
                     "release_id": row[2], "expected_version": expected_version,
                     "attempt_id": attempt_id, "lease_token": lease_token,
                     "receipt": receipt.to_dict()}
        raw = canonical_json_bytes(value)
        digest = hashlib.sha256(raw).hexdigest()
        publish(self._data_root, "run-receipts/" + digest + ".json", raw)
        return digest

    def project_terminal_receipt(self, receipt_sha256):
        """Fenced receipt-first projection, also the single offline reconcile seam."""
        digest = _sha(receipt_sha256)
        locator = "run-receipts/" + digest + ".json"
        try:
            raw = contained(self._data_root, locator).read_bytes()
        except (OSError, ValueError) as exc:
            raise TerminalEvidenceUnavailable("published receipt evidence is missing or unsafe") from exc
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RunRepositoryError("receipt digest mismatch")
        value = json.loads(raw)
        keys = {"policy_id", "run_id", "request_sha256", "envelope_sha256", "release_id",
                "expected_version", "attempt_id", "lease_token", "receipt"}
        if (type(value) is not dict or set(value) != keys or canonical_json_bytes(value) != raw
                or value["policy_id"] != "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1"
                or type(value["expected_version"]) is not int or value["expected_version"] < 0):
            raise RunRepositoryError("invalid offline receipt")
        run_id = _identity(value["run_id"])
        receipt = RunReceipt.from_dict(value["receipt"])
        artifact_id = "receipt-" + digest
        with self._operation(write=True) as conn:
            row = conn.execute("SELECT request_sha256,envelope_sha256,release_id,state,state_version,receipt_artifact_id FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row[:3] != (value["request_sha256"], value["envelope_sha256"], value["release_id"]):
                raise RunRepositoryError("receipt run identity mismatch")
            self._verify_run_identity(conn, run_id, current=False)
            envelope_raw = conn.execute("SELECT envelope_bytes FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0]
            envelope = ExecutionEnvelope.from_json_bytes(envelope_raw)
            if (receipt.request.canonical_sha256 != row[0]
                    or receipt.authority_manifest != envelope.authority_manifest
                    or receipt.share_code_result is not None):
                raise RunRepositoryError("receipt contract identity mismatch")
            self._verify_receipt_producer(conn, run_id, receipt, envelope, row[2])
            if row[3] == "TERMINAL" and row[5] == artifact_id:
                return False
            self._fence(conn, run_id, value["attempt_id"], value["lease_token"])
            if row[3] not in {"RUNNING", "CANCEL_REQUESTED"} or row[4] != value["expected_version"]:
                raise RunStateConflict("receipt projection CAS rejected")
            stamp = _utc(self._clock())
            conn.execute("INSERT INTO app_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (artifact_id, digest, digest, len(raw), "application/json", "RUN_RECEIPT",
                          locator, "RETAINED", value["policy_id"], stamp, stamp))
            conn.execute("INSERT INTO app_run_artifacts VALUES(?,?,?,1)", (run_id, artifact_id, "RUN_RECEIPT"))
            conn.execute("UPDATE app_runs SET state='TERMINAL',state_version=state_version+1,updated_at=?,receipt_artifact_id=? WHERE run_id=?",
                         (stamp, artifact_id, run_id))
            self._event(conn, run_id, row[4] + 1, "RUN_TERMINAL", {"receipt_sha256": digest}, stamp)
            return True

    def reconcile_receipt_projection(self, receipt_sha256):
        return self.project_terminal_receipt(receipt_sha256)
