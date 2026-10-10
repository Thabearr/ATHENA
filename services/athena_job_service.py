"""E1 transactional job admission: commit-first durable admission plus one offline worker.

This module is the reviewed E1 job integration. It sequences only reviewed
local seams and never performs provider, acquisition, delivery, wager, login,
cookie, wallet, stake, email, workflow, or network actions.

Ordering contract (commit-first, never dispatch-before-commit):

1. ``AthenaPreviewAdmissionService.admit`` performs the atomic durable commit
   (idempotent replay, preview-consumption fencing, commit-clock expiry) and
   returns an ``AdmissionResult``. No filesystem or worker side effect happens
   before this commit returns ``admitted``.
2. Only the single thread that observed ``admitted`` may claim attempt
   ownership, transition ``QUEUED`` -> ``RUNNING``, stage the exact canonical
   request bytes, and call ``WorkerLauncher.launch`` exactly once.
3. An ``idempotent_replay`` observation performs no claim, no staging, and no
   launch. A crash between commit and launch therefore stays an honest
   nonterminal crash gap (``QUEUED`` with no attempt), observable through the
   durable reads, exactly like the D4 receipt-projection crash gap.
4. A launch-phase failure never revokes the commit. The service best-effort
   recovers the owned attempt to ``INTERRUPTED`` and still returns the
   original ``admitted`` identity, so the caller always learns the committed
   run. Worker failure is observable via the run snapshot, never via a
   revoked admission.

Worker contract (offline only):

* Exactly one allowlisted operation: ``OFFLINE_IDENTITY_PROBE``. Its worker
  evidence declares ``provider_calls == 0``, ``delivery_calls == 0`` and
  ``wager is False``. No ``CURRENT_SHADOW_REQUEST`` is launched here; live or
  shadow execution remains out of scope for E1.
* The run directory is ``<data_root>/runs/<run_id>/<request_sha256>`` and its leaf
  name must equal the exact canonical request SHA. The staged
  ``athena-run-request.json`` bytes must equal the committed request bytes;
  contradictory existing bytes fail closed before launch.
* Attempt ownership uses the existing offline fencing port
  (``OFFLINE_TEST`` locator). A second concurrent owner is fenced by the
  repository; replay callers never attempt a second launch.

Read adapters in this module are provider-free projections of proven app
state. They return ``None`` for unknown runs and raise ``ReadBackendError``
(fail-closed, no evidence leak) for any inconsistency.
"""
from __future__ import annotations

from datetime import datetime, timezone
from database.app_migration_evidence import contained

from database.run_repository import (
    DurableRunRepository,
    RunLeaseFenced,
    RunRepositoryError,
    RunStateConflict,
)
from domain.run_contracts import RunRequest
from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    InstalledReleaseIdentity,
)
from runtime.resources import ResourceResolver, WritableRoots
from runtime.worker_launcher import (
    WORKER_MODE_BY_OPERATION,
    WORKER_REQUEST_FILENAME,
    WorkerCommand,
    WorkerLaunchError,
    WorkerLauncher,
    _publish_or_match,
)
from services.athena_preview_service import (
    AdmissionResult,
    AthenaPreviewAdmissionService,
    PreviewAdmissionError,
)
from services.athena_read_service import (
    AthenaReadService,
    CancelIntentResult,
    ReadBackendError,
    ReceiptObservation,
    RunEventPage,
    RunEventPayload,
    RunEventRecord,
    RunHistoryEntry,
    RunHistoryPage,
    RunSnapshotRecord,
)


_JOB_WORKER_INSTANCE_ID = "athena-job-worker"
_JOB_PROCESS_LABEL = "offline-probe"
_JOB_OPERATION = "OFFLINE_IDENTITY_PROBE"


def _parse_utc_text(value: object) -> datetime:
    if type(value) is not str:
        raise ReadBackendError("RUN_STORE_UNAVAILABLE")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
    return parsed.replace(tzinfo=timezone.utc)


class AthenaJobService:
    """Commit-first admission plus exactly one offline-probe worker launch."""

    def __init__(
        self,
        preview_service: AthenaPreviewAdmissionService,
        run_repository: DurableRunRepository,
        launcher,
        writable_roots: WritableRoots,
    ) -> None:
        if type(preview_service) is not AthenaPreviewAdmissionService:
            raise ValueError("exact preview admission service is required")
        if type(run_repository) is not DurableRunRepository:
            raise ValueError("exact durable run repository is required")
        if type(writable_roots) is not WritableRoots:
            raise ValueError("exact writable roots are required")
        resources = preview_service.resources
        if type(resources) is not ResourceResolver:
            raise ValueError("verified preview dependencies are required")
        if run_repository.verified_identity is not resources.identity:
            raise ValueError("job repository must share the verified source identity")
        if preview_service.admission_repository is not run_repository:
            raise ValueError("job admission must commit to the same run repository")
        if run_repository._data_root != writable_roots.data_root:
            raise ValueError("job repository must bind the same writable data root")
        if type(launcher) is not WorkerLauncher:
            raise ValueError("exact reviewed worker launcher is required")
        # The launcher type is checked structurally to avoid importing worker
        # internals at module scope beyond what is already needed. Its
        # verified identity must bind the same source as the resources.
        identity = resources.identity
        launcher_identity = getattr(launcher, "identity", None)
        if type(identity) is DevelopmentCheckoutIdentity:
            if type(launcher_identity) is not DevelopmentCheckoutIdentity:
                raise ValueError("development job launcher identity mismatch")
            if launcher_identity.head_commit_sha != identity.head_commit_sha:
                raise ValueError("development job launcher commit mismatch")
            if getattr(launcher, "worker_executable", None) is not None:
                raise ValueError("development launcher cannot pin an installed worker")
        elif type(identity) is InstalledReleaseIdentity:
            if type(launcher_identity) is not InstalledReleaseIdentity:
                raise ValueError("installed job launcher identity mismatch")
            if launcher_identity.manifest_sha256 != identity.manifest_sha256:
                raise ValueError("installed job launcher manifest mismatch")
            if getattr(launcher, "writable_roots", None) != writable_roots:
                raise ValueError("installed launcher must bind the job writable roots")
        else:
            raise ValueError("verified release identity required")
        if not callable(getattr(launcher, "launch", None)):
            raise ValueError("job launcher must expose a launch port")
        self._preview = preview_service
        self._repository = run_repository
        self._launcher = launcher
        self._roots = writable_roots

    @property
    def preview_service(self) -> AthenaPreviewAdmissionService:
        return self._preview

    @property
    def run_repository(self) -> DurableRunRepository:
        return self._repository

    def admit(
        self,
        *,
        preview_id: str,
        execution_envelope_sha256: str,
        idempotency_key: str,
    ) -> AdmissionResult:
        # Commit first: no worker, filesystem, or clock side effect precedes
        # the atomic repository commit performed inside preview admit.
        result = self._preview.admit(
            preview_id=preview_id,
            execution_envelope_sha256=execution_envelope_sha256,
            idempotency_key=idempotency_key,
        )
        if type(result) is not AdmissionResult:
            raise PreviewAdmissionError(
                503, "DURABLE_RUN_STORE_UNAVAILABLE",
                "Durable run admission is not available in this application.", "after_delay")
        if result.disposition != "admitted":
            # Idempotent replay performs no second claim, staging, or launch.
            return result
        if type(result.run_id) is not str:
            raise PreviewAdmissionError(
                503, "DURABLE_RUN_STORE_UNAVAILABLE",
                "Durable run admission is not available in this application.", "after_delay")
        self._start_offline_worker_once(result.run_id)
        return result

    def _start_offline_worker_once(self, run_id: str) -> None:
        try:
            snapshot = self._repository.run_snapshot(run_id)
        except Exception:
            # The commit stands; without proven request bytes there is
            # nothing safe to launch. The QUEUED run stays observable.
            return
        try:
            if snapshot is None:
                return
            request_bytes = snapshot["request_bytes"]
            request = RunRequest.from_json_bytes(request_bytes)
        except Exception:
            return
        try:
            attempt_id, lease_token = self._claim_and_start(run_id)
        except Exception:
            return
        try:
            command = self._stage_and_build(run_id, request, request_bytes)
        except Exception:
            self._best_effort_recover(run_id, attempt_id, lease_token)
            return
        try:
            # Exactly one launch per admitted run, by the admitting thread.
            self._launcher.launch(command)
        except Exception:
            self._best_effort_recover(run_id, attempt_id, lease_token)
            return

    def _claim_and_start(self, run_id: str) -> tuple[str, str]:
        attempt_id, lease_token, _number = self._repository.claim_attempt(
            run_id,
            worker_instance_id=_JOB_WORKER_INSTANCE_ID,
            process_locator={"kind": "OFFLINE_TEST", "label": _JOB_PROCESS_LABEL},
        )
        try:
            self._repository.transition_run(
                run_id, expected_version=0, state="RUNNING",
                attempt_id=attempt_id, lease_token=lease_token)
        except Exception:
            self._best_effort_recover(run_id, attempt_id, lease_token)
            raise
        return attempt_id, lease_token

    def _stage_and_build(self, run_id: str, request: RunRequest, request_bytes: bytes) -> WorkerCommand:
        run_directory = contained(
            self._roots.data_root, "runs/" + run_id + "/" + request.canonical_sha256)
        try:
            run_directory.mkdir(parents=True, exist_ok=True)
            contained(self._roots.data_root, run_directory.relative_to(self._roots.data_root))
        except OSError as exc:
            raise WorkerLaunchError("job run directory could not be prepared") from exc
        staged = run_directory / WORKER_REQUEST_FILENAME
        try:
            _publish_or_match(staged, request_bytes)
        except WorkerLaunchError:
            raise
        except OSError as exc:
            raise WorkerLaunchError("job request artifact could not be staged") from exc
        identity = self._preview.resources.identity
        if type(identity) is DevelopmentCheckoutIdentity:
            kind = identity.identity_kind
            identifier = identity.head_commit_sha
        elif type(identity) is InstalledReleaseIdentity:
            kind = identity.identity_kind
            identifier = identity.manifest_sha256
        else:
            raise WorkerLaunchError("verified source identity is unavailable")
        return WorkerCommand(
            operation=_JOB_OPERATION,
            mode=WORKER_MODE_BY_OPERATION[_JOB_OPERATION],
            run_directory=run_directory,
            request_artifact_id=request.canonical_sha256,
            envelope_artifact_id=None,
            release_identity_kind=kind,
            release_identity_id=identifier,
        )

    def _best_effort_recover(self, run_id: str, attempt_id: str, lease_token: str) -> None:
        try:
            self._repository.recover_attempt(run_id, attempt_id, lease_token)
        except Exception:
            # Even a damaged store during best-effort recovery cannot revoke
            # or conceal the admission identity already committed above.
            return

    def durable_read_service(self) -> AthenaReadService:
        """Provider-free reads over the durable run store.

        Fixture and export integration stays unavailable here; E1 does not
        change the separately reviewed D5 storage ports.
        """
        unavailable = AthenaReadService.unavailable()
        return AthenaReadService(
            run_repository=DurableRunReadAdapter(self._repository),
            cancel_repository=DurableCancelAdapter(self._repository),
            fixture_index=unavailable.fixture_index,
            export_repository=unavailable.export_repository,
        )


def _snapshot_record(snapshot: dict) -> RunSnapshotRecord:
    try:
        run_id = snapshot["run_id"]
        state = snapshot["state"]
        state_version = snapshot["state_version"]
        created_at = _parse_utc_text(snapshot["created_at"])
        updated_at = _parse_utc_text(snapshot["updated_at"])
        request = RunRequest.from_json_bytes(snapshot["request_bytes"])
        receipt_state = "NOT_PRODUCED" if state != "TERMINAL" else "UNKNOWN"
        return RunSnapshotRecord(
            run_id=run_id,
            state=state,
            state_version=state_version,
            created_at=created_at,
            updated_at=updated_at,
            last_proven_stage=None,
            counts=None,
            target_legs=request.target_legs,
            selected_leg_count=None,
            shortfall=None,
            execution_state=None,
            business_result=None,
            delivery_state=None,
            receipt_state=receipt_state,
            request_identity_ref=snapshot["request_sha256"],
            release_identity_ref=snapshot["release_id"],
        )
    except ReadBackendError:
        raise
    except Exception as exc:
        raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None


def _event_record(row: tuple) -> RunEventRecord:
    try:
        sequence, state_version, event_type, _payload, _digest, observed = row
        if type(sequence) is not int or sequence < 1:
            raise ValueError("bad sequence")
        if type(event_type) is not str:
            raise ValueError("bad event type")
        if event_type.startswith("RUN_"):
            kind: str = "STATE_CHANGED"
            suffix = event_type[len("RUN_"):]
            states = {"QUEUED", "RUNNING", "CANCEL_REQUESTED", "TERMINAL", "CANCELLED", "INTERRUPTED"}
            payload = RunEventPayload(state=suffix if suffix in states else None)
        else:
            kind = "DIAGNOSTIC"
            payload = RunEventPayload()
        return RunEventRecord(
            sequence=sequence,
            kind=kind,  # type: ignore[arg-type]
            observed_at=_parse_utc_text(observed),
            state_version=state_version,
            payload=payload,
        )
    except Exception as exc:
        raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None


class DurableRunReadAdapter:
    """D4-owned durable read ports over proven app state only."""

    def __init__(self, repository: DurableRunRepository) -> None:
        if type(repository) is not DurableRunRepository:
            raise ValueError("exact durable run repository is required")
        self._repository = repository

    def get_run_snapshot(self, run_id: str) -> RunSnapshotRecord | None:
        try:
            snapshot = self._repository.run_snapshot(run_id)
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        if snapshot is None:
            return None
        record = _snapshot_record(snapshot)
        if record.run_id != run_id:
            raise ReadBackendError("RUN_STORE_UNAVAILABLE")
        return record

    def list_run_events(self, run_id: str, *, after_sequence: int, limit: int) -> RunEventPage | None:
        try:
            snapshot = self._repository.run_snapshot(run_id)
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        if snapshot is None:
            return None
        try:
            rows = self._repository.read_events(run_id, after_sequence=after_sequence, limit=limit)
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        events = tuple(_event_record(row) for row in rows)
        previous = after_sequence
        for event in events:
            if event.sequence <= previous:
                raise ReadBackendError("RUN_STORE_UNAVAILABLE")
            previous = event.sequence
        return RunEventPage(events)

    def get_receipt_observation(self, run_id: str) -> ReceiptObservation | None:
        try:
            snapshot = self._repository.run_snapshot(run_id)
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        if snapshot is None:
            return None
        state = snapshot["state"]
        if state != "TERMINAL":
            return ReceiptObservation(run_id, state, None)
        try:
            receipt_bytes = self._repository.read_receipt_bytes(run_id)
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        return ReceiptObservation(run_id, state, receipt_bytes)

    def list_runs(self, *, cursor: str | None, limit: int, state, profile) -> RunHistoryPage:
        try:
            rows = self._repository.list_run_history()
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        entries: list[RunHistoryEntry] = []
        for row in rows:
            try:
                request = RunRequest.from_json_bytes(row["request_bytes"])
                entry_profile = request.authority_profile
                entries.append(RunHistoryEntry(
                    row["run_id"], row["state"],
                    state_version=row["state_version"],
                    created_at=_parse_utc_text(row["created_at"]),
                    updated_at=_parse_utc_text(row["updated_at"]),
                    profile=entry_profile,  # type: ignore[arg-type]
                ))
            except Exception as exc:
                raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        filtered = tuple(
            item for item in entries
            if (state is None or item.state == state)
            and (profile is None or item.profile == profile)
        )
        if type(cursor) is str:
            try:
                offset = int(cursor)
            except ValueError:
                raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
            if offset < 0 or (offset > 0 and offset >= len(filtered) + 1):
                raise ReadBackendError("RUN_STORE_UNAVAILABLE") from None
        elif cursor is None:
            offset = 0
        else:
            raise ReadBackendError("RUN_STORE_UNAVAILABLE")
        page = filtered[offset:offset + limit]
        end = offset + len(page)
        next_cursor = str(end) if end < len(filtered) else None
        return RunHistoryPage(tuple(page), next_cursor)


class DurableCancelAdapter:
    """Cooperative cancel intent over the durable store; never controls a process."""

    def __init__(self, repository: DurableRunRepository) -> None:
        if type(repository) is not DurableRunRepository:
            raise ValueError("exact durable run repository is required")
        self._repository = repository

    def request_cancel(self, run_id: str) -> CancelIntentResult | None:
        try:
            snapshot = self._repository.run_snapshot(run_id)
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("CANCEL_STORE_UNAVAILABLE") from None
        if snapshot is None:
            return None
        state = snapshot["state"]
        version = snapshot["state_version"]
        if state in {"CANCEL_REQUESTED", "CANCELLED", "TERMINAL", "INTERRUPTED"}:
            disposition = "already_terminal" if state in {"TERMINAL", "CANCELLED", "INTERRUPTED"} else "already_requested"
            return CancelIntentResult(run_id, disposition, state, version)  # type: ignore[arg-type]
        try:
            new_version = self._repository.request_cancel(run_id, expected_version=version)
        except RunStateConflict as exc:
            raise ReadBackendError("CANCEL_STORE_UNAVAILABLE") from None
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("CANCEL_STORE_UNAVAILABLE") from None
        try:
            updated = self._repository.run_snapshot(run_id)
        except (RunRepositoryError, OSError, ValueError):
            raise ReadBackendError("CANCEL_STORE_UNAVAILABLE") from None
        if updated is None:
            raise ReadBackendError("CANCEL_STORE_UNAVAILABLE")
        return CancelIntentResult(run_id, "requested", updated["state"], updated["state_version"])  # type: ignore[arg-type]


__all__ = [
    "AthenaJobService",
    "DurableCancelAdapter",
    "DurableRunReadAdapter",
]
