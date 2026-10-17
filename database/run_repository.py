"""Offline D4 durable control-plane storage; never launches or transports work.

Genesis is RUN_QUEUED, sequence 1, state_version 0. Presentation profile
identity is not MAIN/SHADOW authority. Each operation owns its connection.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import base64
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from database.app_migration_evidence import contained, publish
from database.app_root_lock import app_root_lock
from database.app_repository import release_provenance, logical_locator
from database.app_migrations import (
    APP_STORE_FILENAME, app_store_path, connect_app_store, expected_schema_structure,
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
SHARE_CREATE_KIND = "SPORTYBET_SHARE_CODE_CREATE_V1"
MAX_TERMINAL_RECEIPT_BYTES = 1_000_000
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


def _read_bounded(path, maximum, label):
    """Read at most one byte beyond a bounded retained evidence object."""
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise RunRepositoryError(label + " exceeds its reviewed byte bound")
    return raw


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

    @classmethod
    def for_worker_data_root(cls, resources, data_root):
        """Open the one admitted product store from a verified worker context."""
        from runtime.resources import ResourceResolver

        if type(resources) is not ResourceResolver:
            raise RunRepositoryError("verified worker resources are required")
        if not isinstance(data_root, os.PathLike) or not Path(data_root).is_absolute():
            raise RunRepositoryError("worker data root must be an absolute path")
        root = Path(data_root)
        if root.is_symlink() or not root.is_dir():
            raise RunRepositoryError("worker data root is not a regular directory")
        repository = cls.__new__(cls)
        repository._path = root.resolve(strict=True) / APP_STORE_FILENAME
        repository._resources = resources
        repository._data_root = root.resolve(strict=True)
        repository.verified_identity = resources.identity
        migrations = read_app_migrations(resources)
        repository._structure = expected_schema_structure(migrations)
        repository._identities = [(version, digest) for version, _, _, digest in migrations]
        repository._clock = lambda: datetime.now(timezone.utc)
        return repository

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
            attempt_id = _identity(value["attempt_id"])
            attempt = conn.execute("SELECT lease_token FROM app_run_attempts WHERE run_id=? AND attempt_id=?",
                                   (run_id, attempt_id)).fetchone()
            if attempt is None or attempt[0] != value["lease_token"]:
                raise TerminalEvidenceUnavailable("retained receipt attempt lease binding drift")
            receipt = RunReceipt.from_dict(value["receipt"])
            if (receipt.request.canonical_sha256 != row[1]
                    or receipt.authority_manifest != envelope.authority_manifest
                    or receipt.share_code_result is not None):
                raise TerminalEvidenceUnavailable("retained receipt contract identity drift")
            self._verify_receipt_producer(conn, run_id, receipt, envelope, row[4], attempt_id)
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
        identity_verified = False
        if row is not None and row[0] == lease_token and row[2] == current:
            # A matching current lease authenticates run evidence before the
            # finished-attempt fence. This does not grant write authority: the
            # fence below still rejects completed attempts, and stale or
            # cross-run leases never reach this check.
            self._verify_run_identity(conn, run_id)
            identity_verified = True
        if row is None or row[0] != lease_token or row[1] is not None or row[2] != current:
            raise RunLeaseFenced("stale or cross-run attempt")
        if not identity_verified:
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
            # One app store belongs to one local data root. BEGIN IMMEDIATE
            # serializes this check with every competing admission, so the
            # invariant survives multiple service objects and processes.
            if conn.execute("SELECT 1 FROM app_run_attempts WHERE finished_at IS NULL LIMIT 1").fetchone():
                raise RunLeaseFenced("local data root already has an unfinished worker attempt")
            number = conn.execute("SELECT COALESCE(MAX(attempt_number),0)+1 FROM app_run_attempts WHERE run_id=?", (run_id,)).fetchone()[0]
            attempt_id, lease = "attempt-" + uuid.uuid4().hex, uuid.uuid4().hex
            stamp = _utc(self._clock())
            conn.execute("INSERT INTO app_run_attempts(attempt_id,run_id,attempt_number,lease_token,worker_instance_id,process_locator_json,heartbeat_at,started_at) VALUES(?,?,?,?,?,?,?,?)",
                         (attempt_id, run_id, number, lease, worker_instance_id,
                          canonical_json_bytes(process_locator).decode("utf-8"), stamp, stamp))
            return attempt_id, lease, number

    def bind_process_locator(self, run_id, attempt_id, lease_token, locator):
        """Bind the one exact OS process-group identity after launch returns."""
        expected_kind = "WINDOWS_PROCESS_GROUP" if os.name == "nt" else "POSIX_PROCESS_GROUP"
        common = {"kind", "pid", "run_id", "attempt_id", "worker_instance_id", "lease_sha256"}
        platform_fields = ({"creation_time", "job_name"} if os.name == "nt"
                           else {"pgid", "session_id", "start_ticks"})
        if (type(locator) is not dict or set(locator) != common | platform_fields
                or locator.get("kind") != expected_kind
                or type(locator.get("pid")) is not int or locator["pid"] <= 0
                or type(locator.get("run_id")) is not str or locator["run_id"] != run_id
                or type(locator.get("attempt_id")) is not str or locator["attempt_id"] != attempt_id
                or type(locator.get("worker_instance_id")) is not str
                or type(locator.get("lease_sha256")) is not str
                or locator["lease_sha256"] != hashlib.sha256(lease_token.encode("utf-8")).hexdigest()):
            raise RunRepositoryError("process locator is outside the exact platform schema")
        if os.name == "nt":
            if (type(locator["creation_time"]) is not int or locator["creation_time"] <= 0
                    or type(locator["job_name"]) is not str
                    or not locator["job_name"].startswith("Local\\ATHENA-E3-")):
                raise RunRepositoryError("Windows process locator identity is invalid")
        elif (locator["pgid"] != locator["pid"] or locator["session_id"] != locator["pid"]
              or type(locator["start_ticks"]) is not int or locator["start_ticks"] <= 0):
            raise RunRepositoryError("POSIX process locator identity is invalid")
        raw = canonical_json_bytes(locator).decode("utf-8")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            state = conn.execute("SELECT state FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if state is None or state[0] != "RUNNING":
                raise RunStateConflict("process locator binding requires an active RUNNING request")
            row = conn.execute(
                "SELECT process_locator_json,worker_instance_id FROM app_run_attempts "
                "WHERE run_id=? AND attempt_id=?",
                (run_id, attempt_id),
            ).fetchone()
            if row is None or row[1] != locator["worker_instance_id"]:
                raise RunLeaseFenced("attempt locator owner is missing")
            try:
                pending = json.loads(row[0])
            except (TypeError, json.JSONDecodeError):
                raise RunRepositoryError("pending process locator is invalid") from None
            if (type(pending) is not dict or set(pending) != {"kind", "label"}
                    or pending.get("kind") != "OFFLINE_TEST"
                    or type(pending.get("label")) is not str
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", pending["label"]) is None):
                raise RunStateConflict("process locator was already bound or was not pending")
            conn.execute(
                "UPDATE app_run_attempts SET process_locator_json=? WHERE run_id=? AND attempt_id=?",
                (raw, run_id, attempt_id),
            )

    def publish_worker_startup_gate(
        self, *, command, run_id, attempt_id, lease_token, worker_instance_id,
        envelope_sha256, process_locator,
    ):
        """Publish an authenticated gate in the same DB order as cancellation."""
        from runtime.worker_launcher import WorkerCommand
        from runtime.worker_startup_gate import gate_bytes, publish_gate
        from services.worker_process_control import owner_identity

        if (type(command) is not WorkerCommand or type(run_id) is not str
                or type(attempt_id) is not str or type(lease_token) is not str
                or type(worker_instance_id) is not str):
            raise RunRepositoryError("exact product worker owner is required")
        expected_run_directory = self._data_root / "runs" / run_id / command.request_artifact_id
        if command.run_directory != expected_run_directory:
            raise RunRepositoryError("worker command is outside the exact product run directory")
        owner = owner_identity(
            run_id=run_id, attempt_id=attempt_id,
            worker_instance_id=worker_instance_id, lease_token=lease_token,
        )
        if (type(process_locator) is not dict
                or any(process_locator.get(key) != value for key, value in owner.items())):
            raise RunRepositoryError("process locator differs from the exact attempt owner")
        gate_raw = gate_bytes(
            command=command, pid=process_locator.get("pid"), owner={
                "attempt_id": attempt_id,
                "worker_instance_id": worker_instance_id,
                "lease_sha256": owner["lease_sha256"],
            },
            process_locator=process_locator,
            lease_token=lease_token,
            envelope_sha256=envelope_sha256,
        )
        from runtime.worker_startup_gate import FILENAME

        gate_path = command.run_directory / FILENAME
        gate_digest = hashlib.sha256(gate_raw).hexdigest()
        process_digest = hashlib.sha256(canonical_json_bytes(process_locator)).hexdigest()
        event_payload = {
            "attempt_id": attempt_id,
            "worker_instance_id": worker_instance_id,
            "lease_sha256": owner["lease_sha256"],
            "command_sha256": hashlib.sha256(command.canonical_bytes).hexdigest(),
            "process_locator_sha256": process_digest,
            "gate_sha256": gate_digest,
        }
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            run = conn.execute(
                "SELECT state,request_sha256,envelope_sha256 FROM app_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if (run is None or run[0] != "RUNNING"
                    or run[1] != command.request_artifact_id
                    or run[2] != envelope_sha256):
                raise RunStateConflict("cancel or request identity won before startup gate publication")
            attempt = conn.execute(
                "SELECT worker_instance_id,process_locator_json FROM app_run_attempts "
                "WHERE run_id=? AND attempt_id=? AND lease_token=? AND finished_at IS NULL",
                (run_id, attempt_id, lease_token),
            ).fetchone()
            if (attempt is None or attempt[0] != worker_instance_id
                    or attempt[1] != canonical_json_bytes(process_locator).decode("utf-8")):
                raise RunLeaseFenced("startup gate process owner is not durably bound")
            if conn.execute(
                "SELECT 1 FROM app_run_events WHERE run_id=? AND event_type='WORKER_STARTUP_GATE_PUBLISHED'",
                (run_id,),
            ).fetchone():
                raise RunStateConflict("startup gate publication is single-use")
            self._event(conn, run_id, conn.execute(
                "SELECT state_version FROM app_runs WHERE run_id=?", (run_id,),
            ).fetchone()[0], "WORKER_STARTUP_GATE_PUBLISHED", event_payload, _utc(self._clock()))
        # Make the authenticated document visible only after its matching
        # durable event commits. A child that observes the file can then
        # always validate one committed owner/event pair. Cancellation may
        # commit between these steps; the child rechecks RUNNING and fails
        # closed before starting work.
        publish_gate(gate_path, gate_raw)
        return gate_path

    def _verify_worker_startup_gate_conn(self, conn, *, command, gate, gate_bytes):
        from runtime.worker_launcher import WorkerCommand
        from runtime.worker_startup_gate import POLICY_ID, _GATE_FIELDS
        from services.worker_process_control import WorkerProcessControl, owner_identity

        if (type(command) is not WorkerCommand or type(gate) is not dict
                or set(gate) != _GATE_FIELDS or type(gate_bytes) is not bytes
                or canonical_json_bytes(gate) != gate_bytes):
            raise RunRepositoryError("startup gate bytes are not the exact typed document")
        if (gate["policy_id"] != POLICY_ID
                or type(gate["envelope_sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", gate["envelope_sha256"]) is None
                or gate["request_sha256"] != command.request_artifact_id
                or gate["command_sha256"] != hashlib.sha256(command.canonical_bytes).hexdigest()
                or gate["operation"] != command.operation or gate["mode"] != command.mode
                or gate["release_identity_kind"] != command.release_identity_kind
                or gate["release_identity_id"] != command.release_identity_id
                or gate["run_id"] != command.run_directory.parent.name
                or gate["pid"] != os.getpid()
                or type(gate["attempt_id"]) is not str or not gate["attempt_id"]
                or type(gate["worker_instance_id"]) is not str or not gate["worker_instance_id"]
                or type(gate["lease_sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", gate["lease_sha256"]) is None):
            raise RunRepositoryError("startup gate differs from the exact worker command")
        expected_directory = self._data_root / "runs" / gate["run_id"] / command.request_artifact_id
        if command.run_directory != expected_directory:
            raise RunRepositoryError("startup gate is cross-run or outside the admitted data root")
        run_id = _identity(gate["run_id"])
        self._verify_run_identity(conn, run_id)
        run = conn.execute(
            "SELECT state,request_bytes,request_sha256,envelope_bytes,envelope_sha256 "
            "FROM app_runs WHERE run_id=?", (run_id,),
        ).fetchone()
        if (run is None or run[0] != "RUNNING"
                or hashlib.sha256(run[1]).hexdigest() != run[2]
                or run[2] != command.request_artifact_id
                or run[4] != gate["envelope_sha256"]):
            raise RunStateConflict("durable RUNNING request no longer authorizes worker startup")
        request = RunRequest.from_json_bytes(run[1])
        envelope = ExecutionEnvelope.from_json_bytes(run[3])
        expected_operation = (
            "CURRENT_SHADOW_REQUEST"
            if (request.authority_profile == "SHADOW"
                and request.mode == "research_shadow"
                and envelope.requested_operations.acquire_sources is True
                and envelope.authority_manifest.provider_acquisition is True)
            else "OFFLINE_IDENTITY_PROBE"
        )
        if (command.operation != expected_operation
                or envelope.canonical_sha256 != gate["envelope_sha256"]
                or (command.operation == "CURRENT_SHADOW_REQUEST"
                    and (command.release_identity_kind != "DEVELOPMENT_CHECKOUT"
                         or envelope.source_identity.kind != "GIT_COMMIT"
                         or command.release_identity_id != envelope.source_identity.value))):
            raise RunRepositoryError("worker operation exceeds the exact admitted envelope")
        attempt = conn.execute(
            "SELECT attempt_number,lease_token,worker_instance_id,process_locator_json,finished_at "
            "FROM app_run_attempts WHERE run_id=? AND attempt_id=?",
            (run_id, gate["attempt_id"]),
        ).fetchone()
        latest_attempt = conn.execute(
            "SELECT MAX(attempt_number) FROM app_run_attempts WHERE run_id=?", (run_id,),
        ).fetchone()[0]
        if (attempt is None or attempt[0] != latest_attempt or attempt[4] is not None
                or attempt[2] != gate["worker_instance_id"]
                or hashlib.sha256(attempt[1].encode("utf-8")).hexdigest() != gate["lease_sha256"]
                or type(gate["process_locator"]) is not dict
                or attempt[3] != canonical_json_bytes(gate["process_locator"]).decode("utf-8")):
            raise RunLeaseFenced("startup gate does not bind the current owner lease and locator")
        owner = owner_identity(
            run_id=run_id, attempt_id=gate["attempt_id"],
            worker_instance_id=gate["worker_instance_id"], lease_token=attempt[1],
        )
        locator = gate["process_locator"]
        if (not all(locator.get(key) == value for key, value in owner.items())
                or locator.get("pid") != os.getpid()
                or WorkerProcessControl.state(locator, owner) != "ACTIVE"):
            raise RunRepositoryError("startup gate process identity is stale or unowned")
        payload = dict(gate)
        authenticator = payload.pop("authenticator_sha256")
        expected_authenticator = hmac.new(
            attempt[1].encode("utf-8"), canonical_json_bytes(payload), hashlib.sha256,
        ).hexdigest()
        if (type(authenticator) is not str
                or not hmac.compare_digest(authenticator, expected_authenticator)):
            raise RunRepositoryError("startup gate authenticator does not match the durable lease")
        event_payload = {
            "attempt_id": gate["attempt_id"],
            "worker_instance_id": gate["worker_instance_id"],
            "lease_sha256": gate["lease_sha256"],
            "command_sha256": gate["command_sha256"],
            "process_locator_sha256": hashlib.sha256(canonical_json_bytes(locator)).hexdigest(),
            "gate_sha256": hashlib.sha256(gate_bytes).hexdigest(),
        }
        events = conn.execute(
            "SELECT payload_bytes,payload_sha256 FROM app_run_events "
            "WHERE run_id=? AND event_type='WORKER_STARTUP_GATE_PUBLISHED'",
            (run_id,),
        ).fetchall()
        if (len(events) != 1 or events[0][0] != canonical_json_bytes(event_payload)
                or hashlib.sha256(events[0][0]).hexdigest() != events[0][1]):
            raise RunRepositoryError("startup gate has no matching durable publication")
        return event_payload

    def verify_worker_startup_gate(self, *, command, gate, gate_bytes):
        with self._operation() as conn:
            return self._verify_worker_startup_gate_conn(
                conn, command=command, gate=gate, gate_bytes=gate_bytes,
            )

    def authorize_worker_start(self, *, command, gate, gate_bytes, effect=None):
        """Linearize a single worker start against durable cancellation."""
        if effect is not None and not callable(effect):
            raise RunRepositoryError("worker effect must be callable")
        with self._operation(write=True) as conn:
            payload = self._verify_worker_startup_gate_conn(
                conn, command=command, gate=gate, gate_bytes=gate_bytes,
            )
            run_id = gate["run_id"]
            prior = conn.execute(
                "SELECT 1 FROM app_run_events WHERE run_id=? AND event_type='WORKER_STARTUP_EFFECT_STARTED'",
                (run_id,),
            ).fetchone()
            if prior is not None:
                raise RunStateConflict("product worker start was already consumed")
            version = conn.execute(
                "SELECT state_version FROM app_runs WHERE run_id=?", (run_id,),
            ).fetchone()[0]
            self._event(conn, run_id, version, "WORKER_STARTUP_EFFECT_STARTED", payload, _utc(self._clock()))
            if effect is not None:
                effect()
        return True

    @staticmethod
    def _validate_worker_progress(payload):
        from domain.current_shadow_run_contract_adapter import CURRENT_STAGE_SEQUENCE

        keys = {"stage", "stage_index", "counts", "evidence_sha256", "identity_refs", "observed_at"}
        if type(payload) is not dict or set(payload) != keys:
            raise RunRepositoryError("worker progress schema drift")
        stage = payload["stage"]
        stage_index = payload["stage_index"]
        if (type(stage) is not str or stage not in CURRENT_STAGE_SEQUENCE
                or type(stage_index) is not int
                or stage_index != CURRENT_STAGE_SEQUENCE.index(stage)):
            raise RunRepositoryError("worker progress stage is invalid")
        counts = payload["counts"]
        count_names = {
            "reviewed_fixture_count", "reconciled_fixture_count", "provider_event_count",
            "priced_fixture_count", "router_selected_count", "router_no_bet_count",
        }
        if type(counts) is not dict or set(counts) != count_names:
            raise RunRepositoryError("worker progress count vocabulary drift")
        if any(value is not None and (type(value) is not int or value < 0)
               for value in counts.values()):
            raise RunRepositoryError("worker progress counts are invalid")
        digest = payload["evidence_sha256"]
        if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise RunRepositoryError("worker progress evidence identity is invalid")
        identities = payload["identity_refs"]
        if (type(identities) is not dict
                or set(identities) != {
                    "source_summary_sha256", "source_identity_sha256",
                    "model_or_history_sha256", "router_diagnostics_sha256",
                    "portfolio_sha256",
                }
                or any(value is not None and (type(value) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", value) is None)
                    for value in identities.values())):
            raise RunRepositoryError("worker progress identity references are invalid")
        observed = payload["observed_at"]
        if type(observed) is not str:
            raise RunRepositoryError("worker progress time is invalid")
        try:
            parsed = datetime.strptime(observed, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            raise RunRepositoryError("worker progress time is invalid") from None
        return stage_index, counts, digest, parsed.replace(tzinfo=timezone.utc)

    def append_worker_progress(self, run_id, attempt_id, lease_token, payload):
        """Persist a proven typed checkpoint in order, deduplicated by evidence SHA."""
        stage_index, counts, evidence_sha, observed_at = self._validate_worker_progress(payload)
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            prior_rows = conn.execute(
                "SELECT payload_bytes,payload_sha256 FROM app_run_events "
                "WHERE run_id=? AND event_type='WORKER_PROGRESS_PROVEN' ORDER BY sequence",
                (run_id,),
            ).fetchall()
            prior = None
            for raw, digest in prior_rows:
                if (hashlib.sha256(raw).hexdigest() != digest
                        or canonical_json_bytes(json.loads(raw)) != raw):
                    raise RunRepositoryError("stored worker progress evidence drift")
                value = json.loads(raw)
                previous_index, previous_counts, previous_sha, previous_time = self._validate_worker_progress(value)
                if previous_sha == evidence_sha:
                    return False
                prior = (previous_index, previous_counts, previous_time)
            if prior is not None:
                previous_index, previous_counts, previous_time = prior
                if stage_index < previous_index or observed_at < previous_time:
                    raise RunStateConflict("worker progress moved backwards")
                if any(
                    previous_counts[key] is not None
                    and (counts[key] is None or counts[key] < previous_counts[key])
                    for key in counts
                ):
                    raise RunStateConflict("worker progress count regressed or became unavailable")
            self._event(conn, run_id,
                        conn.execute("SELECT state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0],
                        "WORKER_PROGRESS_PROVEN", payload, _utc(self._clock()))
            return True

    def latest_worker_progress(self, run_id):
        _identity(run_id)
        with self._operation() as conn:
            self._verify_run_identity(conn, run_id, current=False)
            row = conn.execute(
                "SELECT payload_bytes,payload_sha256 FROM app_run_events "
                "WHERE run_id=? AND event_type='WORKER_PROGRESS_PROVEN' ORDER BY sequence DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            raw, digest = row
            if (hashlib.sha256(raw).hexdigest() != digest
                    or canonical_json_bytes(json.loads(raw)) != raw):
                raise RunRepositoryError("stored worker progress evidence drift")
            value = json.loads(raw)
            self._validate_worker_progress(value)
            return value

    def interrupt_worker_without_receipt(self, run_id, attempt_id, lease_token, *,
                                         exit_code, diagnostic_id, last_proven_stage):
        allowed = {"WORKER_EXIT_WITHOUT_VERIFIED_RECEIPT", "WORKER_RECEIPT_INVALID",
                    "WORKER_PROCESS_LOCATOR_UNAVAILABLE"}
        if (type(exit_code) is not int or not -(2**31) <= exit_code < 2**31
                or diagnostic_id not in allowed):
            raise RunRepositoryError("worker interruption metadata is outside its bounded schema")
        if last_proven_stage is not None:
            from domain.current_shadow_run_contract_adapter import CURRENT_STAGE_SEQUENCE
            if type(last_proven_stage) is not str or last_proven_stage not in CURRENT_STAGE_SEQUENCE:
                raise RunRepositoryError("last proven stage is outside the reviewed vocabulary")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = conn.execute(
                "SELECT state,state_version,receipt_artifact_id FROM app_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None or row[0] not in {"RUNNING", "CANCEL_REQUESTED"} or row[2] is not None:
                raise RunStateConflict("worker interruption state is not eligible")
            stamp = _utc(self._clock())
            self._event(conn, run_id, row[1], "WORKER_INTERRUPTED", {
                "diagnostic_id": diagnostic_id, "exit_code": exit_code,
                "last_proven_stage": last_proven_stage,
            }, stamp)
            disposition = "CANCEL_REQUESTED_SETTLED" if row[0] == "CANCEL_REQUESTED" else "E2_NO_VERIFIED_RECEIPT"
            conn.execute(
                "UPDATE app_run_attempts SET finished_at=?,exit_code=?,recovery_disposition=? "
                "WHERE run_id=? AND attempt_id=?",
                (stamp, exit_code, disposition, run_id, attempt_id),
            )
            next_state = "CANCELLED" if row[0] == "CANCEL_REQUESTED" else "INTERRUPTED"
            conn.execute(
                "UPDATE app_runs SET state=?,state_version=state_version+1,updated_at=? "
                "WHERE run_id=? AND state_version=?",
                (next_state, stamp, run_id, row[1]),
            )
            self._event(conn, run_id, row[1] + 1, "RUN_" + next_state, {}, stamp)

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

    def record_cancel_intent(self, run_id, *, expected_version=None):
        _identity(run_id)
        if expected_version is not None and (type(expected_version) is not int or expected_version < 0):
            raise RunStateConflict("invalid state version")
        with self._operation(write=True) as conn:
            row = conn.execute("SELECT state,state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                return None
            self._verify_run_identity(conn, run_id, current=False)
            current_state, current_version = row[0], row[1]
            if current_state == "CANCEL_REQUESTED":
                return ("already_requested", current_state, current_version)
            if current_state in {"CANCELLED", "TERMINAL", "INTERRUPTED"}:
                return ("already_terminal", current_state, current_version)
            if current_state == "RUNNING" and conn.execute(
                "SELECT 1 FROM app_run_artifacts "
                "WHERE run_id=? AND role='RUN_RECEIPT_PENDING' LIMIT 1",
                (run_id,),
            ).fetchone():
                # Receipt registration wins this transaction race. Cancellation
                # must not bump the version and strand a valid published receipt.
                raise RunStateConflict("terminal receipt projection is pending")
            if expected_version is not None and current_version != expected_version:
                raise RunStateConflict("cancellation CAS rejected")
            next_state = "CANCELLED" if current_state == "QUEUED" else "CANCEL_REQUESTED"
            next_version = current_version + 1
            stamp = _utc(self._clock())
            conn.execute(
                "UPDATE app_runs SET state=?,state_version=?,updated_at=? WHERE run_id=? AND state_version=?",
                (next_state, next_version, stamp, run_id, current_version),
            )
            self._event(conn, run_id, next_version, "RUN_" + next_state, {}, stamp)
            return ("requested", next_state, next_version)

    def request_cancel(self, run_id, *, expected_version):
        if type(expected_version) is not int or expected_version < 0:
            raise RunStateConflict("invalid state version")
        result = self.record_cancel_intent(run_id, expected_version=expected_version)
        if result is None:
            raise RunStateConflict("unknown run")
        return result[2]

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
        if operation_kind == SHARE_CREATE_KIND:
            with self._operation(write=True) as conn:
                self._fence(conn, run_id, attempt_id, lease_token)
                document = self._share_input(conn, run_id, input_artifact_id)
                intent = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
                authority = document["authority_sha256"]
                if (intent_sha256, authority_sha256) != (intent, authority):
                    raise ExternalOperationViolation("admitted CREATE identity mismatch")
                return self._insert_share_create(conn, run_id, attempt_id, document,
                                                 input_artifact_id, idempotency_key)
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

    def _share_authority(self, conn, run_id):
        envelope = self._verify_run_identity(conn, run_id)
        request = RunRequest.from_json_bytes(envelope.request_bytes)
        authority = envelope.authority_manifest
        if (request.create_share_code is not True or request.place_wager is not False
                or request.bookie != "sportybet"
                or envelope.requested_operations.create_share_code is not True
                or authority.share_code_generation is not True
                or any(getattr(authority, key) is not False
                       for key in ("wager", "login", "cookies", "wallet", "staking"))):
            raise ExternalOperationViolation("admitted anonymous CREATE authority unavailable")
        return envelope

    def _share_document(self, conn, run_id, selections):
        from scripts import sportybet_direct_share_bridge as bridge
        envelope = self._share_authority(conn, run_id)
        body = bridge.build_create_request(selections)
        return {
            "schema_version": 1, "operation_kind": SHARE_CREATE_KIND,
            "run_id": run_id, "request_sha256": envelope.request_sha256,
            "envelope_sha256": envelope.canonical_sha256,
            "release_id": conn.execute("SELECT release_id FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0],
            "authority_sha256": hashlib.sha256(canonical_json_bytes(envelope.authority_manifest)).hexdigest(),
            "method": "POST", "origin": bridge.SPORTYBET_ORIGIN, "path": bridge.CREATE_PATH,
            "body": json.loads(body), "body_sha256": hashlib.sha256(body).hexdigest(),
            "login": False, "cookies": False, "wallet": False, "staking": False, "wager": False,
        }

    def _retain_share_artifact(self, conn, run_id, raw, role):
        digest = hashlib.sha256(raw).hexdigest()
        artifact_id = "share-" + role.lower().replace("_", "-") + "-" + digest
        locator = "share-create-evidence/" + digest + ".json"
        publish(self._data_root, locator, raw)
        stamp = _utc(self._clock())
        conn.execute("INSERT OR IGNORE INTO app_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (artifact_id, digest, digest, len(raw), "application/json", role,
                      locator, "RETAINED", SHARE_CREATE_KIND, stamp, stamp))
        conn.execute("INSERT OR IGNORE INTO app_run_artifacts VALUES(?,?,?,1)",
                     (run_id, artifact_id, role))
        self._require_artifact_role(conn, run_id, artifact_id, role)
        return artifact_id

    def _share_artifact(self, conn, run_id, artifact_id, role):
        _identity(artifact_id)
        metadata = conn.execute(
            "SELECT logical_path,byte_sha256,canonical_sha256,byte_count,media_type,artifact_kind,evidence_class,verification_policy_id "
            "FROM app_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
        if metadata is None:
            raise ExternalOperationViolation("CREATE artifact metadata unavailable")
        locator, digest, canonical_digest, count, media, kind, evidence_class, policy = metadata
        _sha(digest)
        expected_id = "share-" + role.lower().replace("_", "-") + "-" + digest
        if (artifact_id != expected_id or locator != "share-create-evidence/" + digest + ".json"
                or canonical_digest != digest or type(count) is not int or not 0 < count <= 3 * 1024 * 1024
                or (media, kind, evidence_class, policy) != ("application/json", role, "RETAINED", SHARE_CREATE_KIND)):
            raise ExternalOperationViolation("CREATE artifact metadata binding mismatch")
        target = contained(self._data_root, logical_locator(locator))
        if target.stat().st_size != count:
            raise ExternalOperationViolation("CREATE artifact byte count mismatch")
        self._require_artifact_role(conn, run_id, artifact_id, role)
        raw = target.read_bytes()
        if len(raw) != count or hashlib.sha256(raw).hexdigest() != digest:
            raise ExternalOperationViolation("CREATE artifact reread bytes changed")
        value = json.loads(raw)
        if canonical_json_bytes(value) != raw or value.get("run_id") != run_id:
            raise ExternalOperationViolation("CREATE evidence run/canonical binding mismatch")
        return value

    def _share_input(self, conn, run_id, artifact_id):
        value = self._share_artifact(conn, run_id, artifact_id, "EXTERNAL_INPUT")
        expected = self._share_document(conn, run_id, value["body"]["selections"])
        if value != expected:
            raise ExternalOperationViolation("CREATE input differs from admitted identity")
        return value

    def _insert_share_create(self, conn, run_id, attempt_id, document, artifact_id, key):
        if conn.execute("SELECT state FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0] != "RUNNING":
            raise ExternalOperationViolation("new CREATE requires RUNNING")
        if key is not None:
            _identity(key)
        intent = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        # BEGIN IMMEDIATE serializes all writers. No replacement, even after a
        # new attempt or a changed caller idempotency key; terminal is not retry.
        if conn.execute("SELECT 1 FROM app_external_operations WHERE run_id=? AND operation_kind=? AND intent_sha256=?",
                        (run_id, SHARE_CREATE_KIND, intent)).fetchone():
            raise ExternalOperationViolation("same CREATE intent already exists; resend forbidden")
        operation_id = "operation-" + uuid.uuid4().hex
        conn.execute("INSERT INTO app_external_operations(operation_id,run_id,attempt_id,operation_kind,intent_sha256,authority_sha256,input_artifact_id,idempotency_key,state,prepared_at) VALUES(?,?,?,?,?,?,?,?,'PREPARED',?)",
                     (operation_id, run_id, attempt_id, SHARE_CREATE_KIND, intent,
                      document["authority_sha256"], artifact_id, key, _utc(self._clock())))
        return operation_id

    def prepare_share_code_create(self, run_id, *, attempt_id, lease_token, selections):
        """Recompute admitted intent, retain it, then prepare once. Never sends."""
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            document = self._share_document(conn, run_id, selections)
            intent = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
            prior = conn.execute("SELECT operation_id FROM app_external_operations WHERE run_id=? AND operation_kind=? AND intent_sha256=?",
                                 (run_id, SHARE_CREATE_KIND, intent)).fetchone()
            if prior is not None:
                return prior[0], False
            artifact_id = self._retain_share_artifact(conn, run_id, canonical_json_bytes(document), "EXTERNAL_INPUT")
            self._share_input(conn, run_id, artifact_id)
            return self._insert_share_create(conn, run_id, attempt_id, document, artifact_id, None), True

    def _share_operation(self, conn, run_id, operation_id):
        cursor = conn.execute("SELECT * FROM app_external_operations WHERE run_id=? AND operation_id=? AND operation_kind=?",
                              (run_id, operation_id, SHARE_CREATE_KIND))
        row = cursor.fetchone()
        if row is None:
            raise ExternalOperationViolation("CREATE operation unavailable")
        result = dict(zip((column[0] for column in cursor.description), row))
        document = self._share_input(conn, run_id, result["input_artifact_id"])
        if (result["intent_sha256"] != hashlib.sha256(canonical_json_bytes(document)).hexdigest()
                or result["authority_sha256"] != document["authority_sha256"]):
            raise ExternalOperationViolation("CREATE operation immutable identity mismatch")
        result["input"] = document
        return result

    def share_code_operation(self, run_id, operation_id, *, attempt_id, lease_token):
        with self._operation() as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = self._share_operation(conn, run_id, operation_id)
            # A new attempt cannot reuse an earlier operation as transport authority.
            if row["attempt_id"] != attempt_id:
                raise RunLeaseFenced("CREATE belongs to another attempt")
            return row

    def retain_share_code_response(self, run_id, operation_id, *, attempt_id, lease_token,
                                   response, method="POST"):
        from scripts import sportybet_direct_share_bridge as bridge
        if type(response) is not bridge.HttpResponseEvidence or method not in {"POST", "GET"}:
            raise ExternalOperationViolation("exact HTTP evidence required")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = self._share_operation(conn, run_id, operation_id)
            if row["attempt_id"] != attempt_id or row["state"] != ("SENT" if method == "POST" else "CONFIRMED"):
                raise ExternalOperationViolation("HTTP evidence owner/state mismatch")
            path = bridge.CREATE_PATH
            if method == "GET":
                proven = self._share_response(conn, run_id, row, row["response_artifact_id"])
                code = bridge.extract_share_code(bridge.parse_response(proven))
                path = bridge.LOAD_PREFIX + code
            value = {"schema_version": 1, "run_id": run_id, "operation_id": operation_id,
                     "operation_kind": SHARE_CREATE_KIND, "intent_sha256": row["intent_sha256"],
                     "method": method, "origin": bridge.SPORTYBET_ORIGIN, "path": path,
                     "http_status": response.status, "raw_base64": base64.b64encode(response.raw).decode("ascii"),
                     "raw_sha256": hashlib.sha256(response.raw).hexdigest(), "raw_byte_count": len(response.raw)}
            return self._retain_share_artifact(conn, run_id, canonical_json_bytes(value), "EXTERNAL_RESPONSE")

    def _share_response(self, conn, run_id, row, artifact_id, *, method="POST", code=None):
        from scripts import sportybet_direct_share_bridge as bridge
        value = self._share_artifact(conn, run_id, artifact_id, "EXTERNAL_RESPONSE")
        keys = {"schema_version", "run_id", "operation_id", "operation_kind", "intent_sha256",
                "method", "origin", "path", "http_status", "raw_base64", "raw_sha256", "raw_byte_count"}
        if (set(value) != keys or value["schema_version"] != 1
                or value["operation_id"] != row["operation_id"] or value["operation_kind"] != SHARE_CREATE_KIND
                or value["intent_sha256"] != row["intent_sha256"] or value["method"] != method
                or value["origin"] != bridge.SPORTYBET_ORIGIN
                or value["path"] != (bridge.CREATE_PATH if method == "POST" else bridge.LOAD_PREFIX + code)):
            raise ExternalOperationViolation("HTTP evidence operation binding mismatch")
        raw = base64.b64decode(value["raw_base64"], validate=True)
        if (hashlib.sha256(raw).hexdigest() != value["raw_sha256"]
                or type(value["raw_byte_count"]) is not int or len(raw) != value["raw_byte_count"]):
            raise ExternalOperationViolation("HTTP raw evidence mismatch")
        return bridge.HttpResponseEvidence(value["http_status"], raw)

    def read_share_code_response(self, run_id, operation_id, artifact_id, *, attempt_id,
                                lease_token, method="POST", code=None):
        with self._operation() as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = self._share_operation(conn, run_id, operation_id)
            if row["attempt_id"] != attempt_id:
                raise RunLeaseFenced("HTTP evidence belongs to another attempt")
            if method == "GET":
                from scripts import sportybet_direct_share_bridge as bridge
                proven = self._share_response(conn, run_id, row, row["response_artifact_id"])
                if row["state"] != "CONFIRMED" or code != bridge.extract_share_code(bridge.parse_response(proven)):
                    raise ExternalOperationViolation("reload code is not proven")
            return self._share_response(conn, run_id, row, artifact_id, method=method, code=code)

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
                "SYNTHETIC_LOCAL_FAILURE", "SYNTHETIC_CONFIRMED_FAILURE", "SHARE_CREATE_NEVER_SENT"}:
            raise ExternalOperationViolation("response-free failure requires a reviewed synthetic failure code")
        if error_code is not None:
            _identity(error_code)
            if state not in {"FAILED", "OUTCOME_UNKNOWN"}:
                raise ExternalOperationViolation("error code requires failure/uncertainty state")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = conn.execute("SELECT attempt_id,state,operation_kind FROM app_external_operations WHERE run_id=? AND operation_id=?",
                               (run_id, operation_id)).fetchone()
            if row is None or row[:2] != (attempt_id, expected_state) or row[2] not in {"TESTING_SYNTHETIC", SHARE_CREATE_KIND}:
                raise ExternalOperationViolation("operation owner/state mismatch")
            if row[2] == SHARE_CREATE_KIND:
                operation = self._share_operation(conn, run_id, operation_id)
                if state == "FAILED":
                    if (expected_state != "PREPARED" or response_artifact_id is not None
                            or error_code != "SHARE_CREATE_NEVER_SENT"):
                        raise ExternalOperationViolation("no reviewed provider no-create failure contract")
                if state == "OUTCOME_UNKNOWN" and error_code not in {
                        "SHARE_CREATE_TRANSPORT_UNKNOWN", "SHARE_CREATE_RESPONSE_UNPROVEN"}:
                    raise ExternalOperationViolation("CREATE uncertainty requires bounded code")
                if state == "CONFIRMED":
                    from scripts import sportybet_direct_share_bridge as bridge
                    response = self._share_response(conn, run_id, operation, response_artifact_id)
                    if response.status != 200:
                        raise ExternalOperationViolation("CREATE HTTP success unproven")
                    bridge.extract_share_code(bridge.parse_response(response))
            elif error_code == "SHARE_CREATE_NEVER_SENT":
                raise ExternalOperationViolation("CREATE code is not synthetic operation vocabulary")
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

    def record_launch_failure_and_interrupt(self, run_id, attempt_id, lease_token):
        """E1 initial handoff failure: diagnostic and interruption commit together."""
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = conn.execute(
                "SELECT state,state_version,receipt_artifact_id FROM app_runs WHERE run_id=?",
                (run_id,)).fetchone()
            number = conn.execute(
                "SELECT attempt_number FROM app_run_attempts WHERE run_id=? AND attempt_id=?",
                (run_id, attempt_id)).fetchone()[0]
            if (row != ("RUNNING", 1, None) or number != 1
                    or conn.execute("SELECT 1 FROM app_run_events WHERE run_id=? AND event_type='WORKER_LAUNCH_FAILED'",
                                    (run_id,)).fetchone()
                    or conn.execute("SELECT 1 FROM app_external_operations WHERE run_id=?",
                                    (run_id,)).fetchone()):
                raise RunStateConflict("launch failure requires initial running handoff")
            stamp = _utc(self._clock())
            self._event(conn, run_id, row[1], "WORKER_LAUNCH_FAILED",
                        {"diagnostic_id": "WORKER_LAUNCH_FAILED"}, stamp)
            conn.execute("UPDATE app_run_attempts SET finished_at=?,recovery_disposition='OFFLINE_LAUNCH_FAILED' WHERE attempt_id=?",
                         (stamp, attempt_id))
            conn.execute("UPDATE app_runs SET state='INTERRUPTED',state_version=state_version+1,updated_at=? WHERE run_id=? AND state_version=1",
                         (stamp, run_id))
            self._event(conn, run_id, row[1] + 1, "RUN_INTERRUPTED", {}, stamp)

    def recover_attempt(self, run_id, attempt_id, lease_token):
        """Offline explicit recovery, never retries operations or launches work."""
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            stamp = _utc(self._clock())
            conn.execute(
                "UPDATE app_external_operations SET state='FAILED',completed_at=?,error_code='SHARE_CREATE_NEVER_SENT' "
                "WHERE run_id=? AND attempt_id=? AND state='PREPARED' AND operation_kind=?",
                (stamp, run_id, attempt_id, SHARE_CREATE_KIND),
            )
            conn.execute(
                "UPDATE app_external_operations SET state='FAILED',completed_at=?,error_code='OFFLINE_RECOVERY' "
                "WHERE run_id=? AND attempt_id=? AND state='PREPARED' AND operation_kind<>?",
                (stamp, run_id, attempt_id, SHARE_CREATE_KIND),
            )
            conn.execute("UPDATE app_external_operations SET state='OUTCOME_UNKNOWN',completed_at=?,error_code='OFFLINE_RECOVERY' WHERE run_id=? AND attempt_id=? AND state='SENT'",
                         (stamp, run_id, attempt_id))
            row = conn.execute("SELECT state,state_version FROM app_runs WHERE run_id=?", (run_id,)).fetchone()
            disposition = "CANCEL_REQUESTED_SETTLED" if row is not None and row[0] == "CANCEL_REQUESTED" else "OFFLINE_INTERRUPTED"
            conn.execute("UPDATE app_run_attempts SET finished_at=?,recovery_disposition=? WHERE attempt_id=?",
                         (stamp, disposition, attempt_id))
            if row is not None and row[0] in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
                next_state = "CANCELLED" if row[0] == "CANCEL_REQUESTED" else "INTERRUPTED"
                conn.execute("UPDATE app_runs SET state=?,state_version=state_version+1,updated_at=? WHERE run_id=?", (next_state, stamp, run_id))
                self._event(conn, run_id, row[1] + 1, "RUN_" + next_state, {}, stamp)

    def list_unfinished_attempts(self):
        with self._operation() as conn:
            cursor = conn.execute(
                "SELECT a.attempt_id, a.run_id, a.attempt_number, a.lease_token, "
                "a.worker_instance_id, a.process_locator_json, a.heartbeat_at, a.started_at, "
                "r.state, r.state_version, r.request_sha256, r.envelope_sha256, r.release_id "
                "FROM app_run_attempts a JOIN app_runs r ON r.run_id=a.run_id "
                "WHERE a.finished_at IS NULL ORDER BY a.started_at LIMIT 101"
            )
            rows = cursor.fetchall()
            if len(rows) > 100:
                raise RunRepositoryError("unfinished attempt scan exceeds its bound")
            return [
                {
                    "attempt_id": row[0],
                    "run_id": row[1],
                    "attempt_number": row[2],
                    "lease_token": row[3],
                    "worker_instance_id": row[4],
                    "process_locator": json.loads(row[5]),
                    "heartbeat_at": row[6],
                    "started_at": row[7],
                    "run_state": row[8],
                    "state_version": row[9],
                    "request_sha256": row[10],
                    "envelope_sha256": row[11],
                    "release_id": row[12],
                }
                for row in rows
            ]

    def list_pending_terminal_receipts(self, *, limit=100):
        """Return only receipt identities already linked to an exact DB run/attempt."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise RunRepositoryError("pending receipt page is outside its bound")
        with self._operation() as conn:
            rows = conn.execute(
                "SELECT a.byte_sha256,l.run_id,t.attempt_id,t.lease_token "
                "FROM app_run_artifacts l "
                "JOIN app_artifacts a ON a.artifact_id=l.artifact_id "
                "JOIN app_runs r ON r.run_id=l.run_id "
                "JOIN app_run_attempts t ON t.run_id=l.run_id AND t.finished_at IS NULL "
                "WHERE l.role='RUN_RECEIPT_PENDING' AND l.retained_root=1 "
                "AND r.receipt_artifact_id IS NULL AND r.state IN ('RUNNING','CANCEL_REQUESTED') "
                "AND a.artifact_id='receipt-'||a.byte_sha256 "
                "AND a.canonical_sha256=a.byte_sha256 "
                "AND a.logical_path='run-receipts/'||a.byte_sha256||'.json' "
                "AND a.media_type='application/json' AND a.artifact_kind='RUN_RECEIPT' "
                "AND a.evidence_class='RETAINED' "
                "AND a.verification_policy_id='ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1' "
                "AND a.byte_count BETWEEN 1 AND ? "
                "ORDER BY a.created_at,l.run_id LIMIT ?",
                (MAX_TERMINAL_RECEIPT_BYTES, limit + 1),
            ).fetchall()
            if len(rows) > limit:
                raise RunRepositoryError("pending receipt scan exceeds its bound")
            return [
                {"receipt_sha256": row[0], "run_id": row[1],
                 "attempt_id": row[2], "lease_token": row[3]}
                for row in rows
            ]

    def reconcile_dead_attempt(self, run_id, attempt_id, lease_token, *,
                               diagnostic_id="WORKER_EXIT_WITHOUT_VERIFIED_RECEIPT", exit_code=-1):
        _identity(run_id)
        _identity(attempt_id)
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            row = conn.execute(
                "SELECT state,state_version,receipt_artifact_id FROM app_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None or row[2] is not None:
                raise RunStateConflict("run is not eligible for recovery")
            stamp = _utc(self._clock())
            conn.execute(
                "UPDATE app_external_operations SET state='FAILED',completed_at=?,error_code='SHARE_CREATE_NEVER_SENT' "
                "WHERE run_id=? AND attempt_id=? AND state='PREPARED' AND operation_kind=?",
                (stamp, run_id, attempt_id, SHARE_CREATE_KIND),
            )
            conn.execute(
                "UPDATE app_external_operations SET state='FAILED',completed_at=?,error_code='OFFLINE_RECOVERY' "
                "WHERE run_id=? AND attempt_id=? AND state='PREPARED' AND operation_kind<>?",
                (stamp, run_id, attempt_id, SHARE_CREATE_KIND),
            )
            conn.execute(
                "UPDATE app_external_operations SET state='OUTCOME_UNKNOWN',completed_at=?,error_code='OFFLINE_RECOVERY' "
                "WHERE run_id=? AND attempt_id=? AND state='SENT'",
                (stamp, run_id, attempt_id),
            )
            current_state = row[0]
            next_state = "CANCELLED" if current_state == "CANCEL_REQUESTED" else "INTERRUPTED"
            disposition = "CANCEL_REQUESTED_SETTLED" if current_state == "CANCEL_REQUESTED" else "OFFLINE_INTERRUPTED"
            conn.execute(
                "UPDATE app_run_attempts SET finished_at=?,exit_code=?,recovery_disposition=? "
                "WHERE run_id=? AND attempt_id=?",
                (stamp, exit_code, disposition, run_id, attempt_id),
            )
            if current_state in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
                latest_stage = None
                progress_row = conn.execute(
                    "SELECT payload_bytes,payload_sha256 FROM app_run_events "
                    "WHERE run_id=? AND event_type='WORKER_PROGRESS_PROVEN' "
                    "ORDER BY sequence DESC LIMIT 1", (run_id,),
                ).fetchone()
                if progress_row is not None:
                    progress_raw, progress_digest = progress_row
                    if (hashlib.sha256(progress_raw).hexdigest() != progress_digest
                            or canonical_json_bytes(json.loads(progress_raw)) != progress_raw):
                        raise RunRepositoryError("stored worker progress evidence drift")
                    progress_value = json.loads(progress_raw)
                    self._validate_worker_progress(progress_value)
                    latest_stage = progress_value["stage"]
                self._event(conn, run_id, row[1], "WORKER_INTERRUPTED", {
                    "diagnostic_id": diagnostic_id, "exit_code": exit_code,
                    "last_proven_stage": latest_stage,
                }, stamp)
                conn.execute(
                    "UPDATE app_runs SET state=?,state_version=state_version+1,updated_at=? WHERE run_id=? AND state_version=?",
                    (next_state, stamp, run_id, row[1]),
                )
                self._event(conn, run_id, row[1] + 1, "RUN_" + next_state, {}, stamp)

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
            if (artifact is None or artifact[1] != digest
                    or type(artifact[2]) is not int or not 1 <= artifact[2] <= MAX_TERMINAL_RECEIPT_BYTES):
                raise RunRepositoryError("retained receipt artifact mismatch")
            raw = _read_bounded(contained(self._data_root, logical_locator(artifact[0])),
                                MAX_TERMINAL_RECEIPT_BYTES, "retained receipt")
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

    def _verify_receipt_producer(self, conn, run_id, receipt, envelope, release_id, attempt_id):
        provenance = self._verify_release(conn, release_id, envelope.source_identity)
        if envelope.source_identity.kind != "GIT_COMMIT" or provenance[1] is None:
            raise ReceiptProducerUnavailable("installed hash pin has no independently verified producer commit; named future dependency E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE remains open")
        if receipt.exact_commit_sha != provenance[1] or receipt.exact_commit_sha != envelope.source_identity.value:
            raise ReceiptProducerUnavailable("receipt producer commit differs from verified run source")
        expected = {"run_id": run_id, "execution_envelope_sha256": envelope.canonical_sha256,
                    "release_id": release_id, "worker_attempt_id": attempt_id}
        if any(receipt.evidence.get(key) != value for key, value in expected.items()):
            raise ReceiptProducerUnavailable("receipt run/attempt/envelope/release producer binding mismatch")

    def publish_terminal_receipt(self, run_id, *, receipt_bytes, expected_version, attempt_id, lease_token):
        """Register the exact run/attempt receipt identity, then publish its bytes.

        The pending database link is a lookup key only. The receipt verifier
        remains the sole terminal authority and a missing or invalid file blocks.
        """
        if type(receipt_bytes) is not bytes or len(receipt_bytes) > MAX_TERMINAL_RECEIPT_BYTES:
            raise RunRepositoryError("terminal receipt exceeds its reviewed byte bound")
        with self._operation(write=True) as conn:
            self._fence(conn, run_id, attempt_id, lease_token)
            receipt = RunReceipt.from_json_bytes(receipt_bytes)
            row = conn.execute(
                "SELECT request_sha256,envelope_sha256,release_id,state,state_version,receipt_artifact_id "
                "FROM app_runs WHERE run_id=?", (run_id,),
            ).fetchone()
            if row[3] != "RUNNING" or row[4] != expected_version:
                raise RunStateConflict("receipt state CAS rejected")
            if row[5] is not None:
                raise RunStateConflict("run already carries a terminal receipt")
            if receipt.request.canonical_sha256 != row[0] or receipt.share_code_result is not None:
                raise RunRepositoryError("receipt request mismatch or disabled delivery result")
            envelope_raw = conn.execute("SELECT envelope_bytes FROM app_runs WHERE run_id=?", (run_id,)).fetchone()[0]
            envelope = ExecutionEnvelope.from_json_bytes(envelope_raw)
            if receipt.authority_manifest != envelope.authority_manifest:
                raise RunRepositoryError("receipt authority mismatch")
            self._verify_receipt_producer(conn, run_id, receipt, envelope, row[2], attempt_id)
            value = {"policy_id": "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1",
                     "run_id": run_id, "request_sha256": row[0], "envelope_sha256": row[1],
                     "release_id": row[2], "expected_version": expected_version,
                     "attempt_id": attempt_id, "lease_token": lease_token,
                     "receipt": receipt.to_dict()}
            raw = canonical_json_bytes(value)
            if len(raw) > MAX_TERMINAL_RECEIPT_BYTES:
                raise RunRepositoryError("terminal receipt projection exceeds its reviewed byte bound")
            digest = hashlib.sha256(raw).hexdigest()
            artifact_id = "receipt-" + digest
            locator = "run-receipts/" + digest + ".json"
            stamp = _utc(self._clock())
            conn.execute(
                "INSERT OR IGNORE INTO app_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (artifact_id, digest, digest, len(raw), "application/json", "RUN_RECEIPT",
                 locator, "RETAINED", "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1", None, stamp),
            )
            metadata = conn.execute(
                "SELECT byte_sha256,canonical_sha256,byte_count,media_type,artifact_kind,"
                "logical_path,evidence_class,verification_policy_id FROM app_artifacts "
                "WHERE artifact_id=?", (artifact_id,),
            ).fetchone()
            if (metadata is None or metadata != (
                    digest, digest, len(raw), "application/json", "RUN_RECEIPT", locator,
                    "RETAINED", "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1")):
                raise RunRepositoryError("pending receipt artifact metadata conflicts")
            links = conn.execute(
                "SELECT run_id,role,retained_root FROM app_run_artifacts "
                "WHERE artifact_id=?", (artifact_id,),
            ).fetchall()
            expected_link = (run_id, "RUN_RECEIPT_PENDING", 1)
            if links and links != [expected_link]:
                raise RunRepositoryError("pending receipt is linked to another run")
            conn.execute(
                "INSERT OR IGNORE INTO app_run_artifacts VALUES(?,?,?,1)",
                (run_id, artifact_id, "RUN_RECEIPT_PENDING"),
            )
        publish(self._data_root, "run-receipts/" + digest + ".json", raw)
        return digest

    def project_terminal_receipt(self, receipt_sha256):
        """Fenced receipt-first projection, also the single offline reconcile seam."""
        digest = _sha(receipt_sha256)
        locator = "run-receipts/" + digest + ".json"
        try:
            raw = _read_bounded(contained(self._data_root, locator),
                                MAX_TERMINAL_RECEIPT_BYTES, "terminal receipt projection")
        except RunRepositoryError:
            raise
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
            self._verify_receipt_producer(conn, run_id, receipt, envelope, row[2], _identity(value["attempt_id"]))
            if row[3] == "TERMINAL" and row[5] == artifact_id:
                return False
            self._fence(conn, run_id, value["attempt_id"], value["lease_token"])
            if row[3] not in {"RUNNING", "CANCEL_REQUESTED"} or row[4] != value["expected_version"]:
                raise RunStateConflict("receipt projection CAS rejected")
            metadata = conn.execute(
                "SELECT byte_sha256,canonical_sha256,byte_count,media_type,artifact_kind,"
                "logical_path,evidence_class,verification_policy_id FROM app_artifacts "
                "WHERE artifact_id=?", (artifact_id,),
            ).fetchone()
            locator = "run-receipts/" + digest + ".json"
            if (metadata is None or metadata != (
                    digest, digest, len(raw), "application/json", "RUN_RECEIPT", locator,
                    "RETAINED", "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1")):
                raise RunRepositoryError("receipt is not linked to exact retained publication metadata")
            pending_links = conn.execute(
                "SELECT run_id,role,retained_root FROM app_run_artifacts WHERE artifact_id=?",
                (artifact_id,),
            ).fetchall()
            if pending_links != [(run_id, "RUN_RECEIPT_PENDING", 1)]:
                raise RunRepositoryError("receipt pending link is missing or cross-run")
            stamp = _utc(self._clock())
            conn.execute(
                "UPDATE app_artifacts SET verified_at=? WHERE artifact_id=?",
                (stamp, artifact_id),
            )
            conn.execute(
                "UPDATE app_run_artifacts SET role='RUN_RECEIPT' "
                "WHERE run_id=? AND artifact_id=? AND role='RUN_RECEIPT_PENDING'",
                (run_id, artifact_id),
            )
            conn.execute("UPDATE app_runs SET state='TERMINAL',state_version=state_version+1,updated_at=?,receipt_artifact_id=? WHERE run_id=?",
                         (stamp, artifact_id, run_id))
            # Receipt publication is the prerequisite for terminal projection;
            # the same fenced transaction finishes the attempt and frees the
            # root-wide slot. A published-but-unprojected receipt keeps both
            # the attempt and slot owned until explicit projection repair.
            conn.execute(
                "UPDATE app_run_attempts SET finished_at=?,exit_code=0,recovery_disposition='E2_RECEIPT_PROJECTED' "
                "WHERE run_id=? AND attempt_id=? AND lease_token=? AND finished_at IS NULL",
                (stamp, run_id, value["attempt_id"], value["lease_token"]),
            )
            self._event(conn, run_id, row[4] + 1, "RUN_TERMINAL", {"receipt_sha256": digest}, stamp)
            return True

    def reconcile_receipt_projection(self, receipt_sha256):
        return self.project_terminal_receipt(receipt_sha256)
