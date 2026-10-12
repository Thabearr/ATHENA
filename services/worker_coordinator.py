"""Owned, fenced local worker lifecycle for RUN-01B.

The coordinator owns each returned process handle from launch through exit.
It never parses process output, retries business work, or re-adopts a process
after restart. Only canonical typed Current Shadow artifacts can produce
progress or a terminal RunReceipt.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Callable

from database.app_migration_evidence import contained
from database.run_repository import (
    DurableRunRepository,
    RunLeaseFenced,
    RunRepositoryError,
)
from domain.execution_envelope import ExecutionEnvelope
from domain.run_contracts import RunReceipt, RunRequest, canonical_json_bytes
from runtime.resources import WritableRoots
from runtime.worker_launcher import (
    WORKER_MODE_BY_OPERATION,
    WorkerCommand,
    WorkerLaunchError,
    WorkerLauncher,
    WorkerProcessHandle,
    build_offline_probe_documents,
)

_STAGE_KEYS = {
    "schema_version", "dataset_name", "stage", "stage_index", "observed_at",
    "exact_commit_sha", "requested_target_size", "wager_placed",
}
_PROGRESS_KEYS = {
    "schema_version", "dataset_name", "stage", "stage_index", "progress_status",
    "observed_at", "exact_commit_sha", "requested_target_size", "counts",
    "source_summary", "wager_placed",
}
_PROGRESS_COUNT_NAMES = (
    "reviewed_fixture_count", "reconciled_fixture_count", "provider_event_count",
    "priced_fixture_count", "router_selected_count", "router_no_bet_count",
)
_PROGRESS_STATUSES = {"STARTED", "IN_PROGRESS", "COMPLETED"}
_LEGACY_AUTHORITY_KEYS = frozenset({
    "research_shadow_current_runner", "research_shadow_source_acquisition",
    "research_shadow_probability_consumption", "research_shadow_price_all",
    "research_shadow_market_routing", "research_shadow_portfolio", "research_shadow_shortfall",
    "research_anonymous_share_code_generation", "provider_create_reload_verification",
    "production_model", "production_probability", "phase6", "production_price_all",
    "production_market_router", "production_portfolio", "production_selection",
    "production_sportybet_execution", "login", "cookies", "wallet", "staking", "bet", "wager_placed",
})
_SHADOW_FILES = {
    "request_policy": "current-shadow-request-policy.json",
    "receipt": "current-shadow-all-market-run-receipt.json",
    "stage": "current-shadow-all-market-stage.json",
    "progress": "current-shadow-all-market-progress.json",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _strict_json(raw: bytes) -> dict:
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("non-finite JSON value")

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise ValueError("typed worker evidence is not canonical")
    return value


class WorkerCoordinator:
    """Own one claimed process at a time and publish only verified results."""

    def __init__(
        self,
        repository: DurableRunRepository,
        launcher: WorkerLauncher,
        writable_roots: WritableRoots,
        *,
        heartbeat_seconds: float = 2.0,
        poll_seconds: float = 0.1,
        initial_poll_delay: float = 0.5,
        thread_factory=threading.Thread,
        monotonic=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        if (type(repository) is not DurableRunRepository or type(launcher) is not WorkerLauncher
                or type(writable_roots) is not WritableRoots):
            raise ValueError("verified repository, launcher, and writable roots are required")
        for value, label in ((heartbeat_seconds, "heartbeat"), (poll_seconds, "poll"),
                             (initial_poll_delay, "initial poll delay")):
            if type(value) not in {int, float} or value <= 0:
                raise ValueError(label + " must be positive")
        if heartbeat_seconds < 0.05 or heartbeat_seconds > 60.0:
            raise ValueError("heartbeat cadence is outside the bounded 0.05-60 second range")
        self._repository = repository
        self._launcher = launcher
        self._roots = writable_roots
        self._heartbeat_seconds = float(heartbeat_seconds)
        self._poll_seconds = float(poll_seconds)
        self._initial_poll_delay = float(initial_poll_delay)
        self._thread_factory = thread_factory
        self._monotonic = monotonic
        self._sleep = sleeper
        self._owned: dict[str, WorkerProcessHandle] = {}
        self._owned_lock = threading.Lock()
        self._pending_projection: dict[str, str] = {}
        self._output_drainers: list[threading.Thread] = []

    def handoff(
        self,
        run_id: str,
        *,
        worker_instance_id: str,
        process_label: str,
        command_factory: Callable[[RunRequest, bytes, ExecutionEnvelope], WorkerCommand],
    ) -> bool:
        """Claim, launch, persist locator, and hand the handle to the monitor.

        Called only after a fresh durable admission. Replay never reaches this
        method. The HTTP caller waits only for this bounded launch handoff; it
        never waits for child completion.
        """
        snapshot = self._repository.run_snapshot(run_id)
        if snapshot is None:
            return False
        request_bytes = snapshot["request_bytes"]
        request = RunRequest.from_json_bytes(request_bytes)
        envelope = ExecutionEnvelope.from_json_bytes(snapshot["envelope_bytes"])
        try:
            attempt_id, lease_token, _number = self._repository.claim_attempt(
                run_id,
                worker_instance_id=worker_instance_id,
                process_locator={"kind": "OFFLINE_TEST", "label": process_label},
            )
        except RunLeaseFenced:
            # A run that loses root-wide capacity remains QUEUED. There is no
            # deferred drain when the current owner later finishes.
            return False
        try:
            self._repository.transition_run(
                run_id, expected_version=0, state="RUNNING",
                attempt_id=attempt_id, lease_token=lease_token,
            )
        except Exception:
            try:
                self._repository.recover_attempt(run_id, attempt_id, lease_token)
            except Exception:
                pass
            return False
        try:
            command = command_factory(request, request_bytes, envelope)
            if type(command) is not WorkerCommand:
                raise WorkerLaunchError("exact WorkerCommand is required")
            expected_operation = (
                "CURRENT_SHADOW_REQUEST"
                if (request.authority_profile == "SHADOW"
                    and request.mode == "research_shadow"
                    and envelope.requested_operations.acquire_sources is True
                    and envelope.authority_manifest.provider_acquisition is True)
                else "OFFLINE_IDENTITY_PROBE"
            )
            if (command.operation != expected_operation
                    or command.request_artifact_id != request.canonical_sha256
                    or command.run_directory != self._roots.data_root / "runs" / run_id / request.canonical_sha256):
                raise WorkerLaunchError("worker command differs from the committed request")
            if expected_operation == "CURRENT_SHADOW_REQUEST" and (
                    command.release_identity_kind != "DEVELOPMENT_CHECKOUT"
                    or envelope.source_identity.kind != "GIT_COMMIT"
                    or command.release_identity_id != envelope.source_identity.value):
                raise WorkerLaunchError(
                    "installed Current Shadow execution is blocked without authenticated producer provenance"
                )
        except Exception:
            # Staging failed before a launch was attempted. Preserve E1's
            # generic fenced interruption without a launch-failure diagnostic.
            try:
                self._repository.recover_attempt(run_id, attempt_id, lease_token)
            except Exception:
                pass
            return False
        try:
            handle = self._launcher.launch(command)
        except Exception:
            try:
                self._repository.record_launch_failure_and_interrupt(
                    run_id, attempt_id, lease_token,
                )
            except Exception:
                pass
            return False

        if type(handle) is not WorkerProcessHandle:
            # A launcher returned, so a child may exist. Retain the claimed
            # attempt rather than inventing a synchronous launch exception.
            return False

        with self._owned_lock:
            self._owned[attempt_id] = handle
        locator_bound = False
        locator = self._native_process_locator(handle.pid)
        if locator is not None:
            try:
                self._repository.bind_process_locator(
                    run_id, attempt_id, lease_token, locator,
                )
                locator_bound = True
            except Exception:
                locator_bound = False

        try:
            self._discard_output(handle)
        except Exception:
            # Output is never evidence. A failure to drain is not permission
            # to parse or retain logs; the coordinator still owns the handle.
            pass
        try:
            thread = self._thread_factory(
                target=self._monitor,
                kwargs={"run_id": run_id, "attempt_id": attempt_id,
                        "lease_token": lease_token, "request": request,
                        "envelope": envelope, "snapshot": snapshot,
                        "command": command, "handle": handle,
                        "locator_bound": locator_bound},
                daemon=True,
                name="athena-worker-" + attempt_id,
            )
            thread.start()
        except Exception:
            # The child exists and remains durably claimed. Do not release the
            # root or attempt a second launch; E3 owns restart reconciliation.
            return True
        return True

    @staticmethod
    def _native_process_locator(pid: object) -> dict[str, int | str] | None:
        """Return only the exact bounded native process-group locator."""
        if type(pid) is not int or pid <= 0:
            return None
        kind = "WINDOWS_PROCESS_GROUP" if os.name == "nt" else "POSIX_PROCESS_GROUP"
        return {"kind": kind, "pid": pid}

    @staticmethod
    def _drain_output(stream) -> None:
        try:
            while stream.read(65536):
                pass
        except (OSError, ValueError):
            return

    def _discard_output(self, handle: WorkerProcessHandle) -> None:
        """Drain pipes asynchronously without interpreting or retaining logs."""
        process = getattr(handle, "_process", None)
        if process is None:
            return
        for name in ("stdout", "stderr"):
            stream = getattr(process, name, None)
            if stream is None or not callable(getattr(stream, "read", None)):
                continue
            thread = self._thread_factory(
                target=self._drain_output,
                args=(stream,),
                daemon=True,
                name="athena-worker-output-drain",
            )
            thread.start()
            with self._owned_lock:
                self._output_drainers.append(thread)

    def _safe_file(self, command: WorkerCommand, relative: str) -> tuple[Path, bytes]:
        run_directory = command.run_directory
        try:
            resolved_run = run_directory.resolve(strict=True)
            resolved_root = self._roots.data_root.resolve(strict=True)
            resolved_run.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise ValueError("worker run directory escaped the data root") from exc
        if run_directory.is_symlink() or not run_directory.is_dir():
            raise ValueError("worker run directory is not a regular contained directory")
        path = run_directory / relative
        if not path.exists() and not path.is_symlink():
            raise FileNotFoundError("required typed worker evidence is missing")
        try:
            candidate = contained(self._roots.data_root, path.relative_to(self._roots.data_root).as_posix())
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError("typed worker artifact is not a regular file")
            raw = candidate.read_bytes()
        except (OSError, ValueError) as exc:
            raise ValueError("typed worker artifact is unsafe or unavailable") from exc
        return candidate, raw

    def _observe_checkpoint(self, *, run_id, attempt_id, lease_token, request,
                            envelope, command, filename, source):
        relative = "current-shadow/" + filename
        path, raw = self._safe_file(command, relative)
        del path
        payload = _strict_json(raw)
        expected_keys = _STAGE_KEYS if source == "stage" else _PROGRESS_KEYS
        if set(payload) != expected_keys:
            raise ValueError("Current Shadow checkpoint schema drift")
        if source == "progress" and payload.get("progress_status") not in _PROGRESS_STATUSES:
            raise ValueError("Current Shadow progress status is unknown")
        exact_commit = envelope.source_identity.value
        from domain import current_shadow_run_contract_adapter as adapter
        parsed = adapter._checkpoint_stage(
            payload, request=request, exact_commit_sha=exact_commit, source=source,
        )
        if parsed.stage not in adapter.CURRENT_STAGE_SEQUENCE:
            raise ValueError("Current Shadow stage is outside the exact sequence")
        counts = {name: None for name in _PROGRESS_COUNT_NAMES}
        previous = self._repository.latest_worker_progress(run_id)
        identity_refs = {
            "source_summary_sha256": None,
            "source_identity_sha256": None,
            "model_or_history_sha256": None,
            "router_diagnostics_sha256": None,
            "portfolio_sha256": None,
        }
        if source == "progress":
            if set(payload["counts"]) != set(_PROGRESS_COUNT_NAMES):
                raise ValueError("Current Shadow progress count schema drift")
            counts = dict(payload["counts"])
        elif previous is not None:
            # Stage-only checkpoints do not carry counts. Keep the last proven
            # values instead of turning previously known counts back to None.
            counts = dict(previous["counts"])
            identity_refs = dict(previous["identity_refs"])
        summary = payload.get("source_summary") if source == "progress" else None
        source_summary_sha = None if summary is None else _sha(canonical_json_bytes(summary))
        source_identity = None
        if summary is not None:
            source_values = {
                key: summary[key]
                for key in ("current_fotmob", "current_fotmob_sources", "current_reconciliation_sha256",
                            "current_reconciliation_contract_sha256")
                if key in summary
            }
            if source_values:
                source_identity = _sha(canonical_json_bytes(source_values))
        model_or_history = None
        if summary is not None:
            history_values = {
                key: summary[key]
                for key in ("complete_current_history_sha256", "complete_current_history_sha256_by_request_date")
                if key in summary
            }
            if history_values:
                model_or_history = _sha(canonical_json_bytes(history_values))
        router_value = None if summary is None else summary.get("runtime_progress_diagnostics")
        router_sha = None if router_value is None else _sha(canonical_json_bytes(router_value))
        event = {
            "stage": parsed.stage,
            "stage_index": adapter.CURRENT_STAGE_SEQUENCE.index(parsed.stage),
            "counts": counts,
            "evidence_sha256": _sha(raw),
            "identity_refs": identity_refs if source == "stage" else {
                "source_summary_sha256": source_summary_sha,
                "source_identity_sha256": source_identity,
                "model_or_history_sha256": model_or_history,
                "router_diagnostics_sha256": router_sha,
                "portfolio_sha256": None,
            },
            "observed_at": _iso(parsed.observed_at),
        }
        return self._repository.append_worker_progress(
            run_id, attempt_id, lease_token, event,
        )

    def _observe_available_checkpoints(self, **kwargs) -> None:
        command = kwargs["command"]
        current_dir = command.run_directory / "current-shadow"
        if current_dir.is_symlink():
            raise ValueError("Current Shadow output directory is a symlink")
        available = []
        for source in ("stage", "progress"):
            filename = _SHADOW_FILES[source]
            candidate = current_dir / filename
            if candidate.exists() or candidate.is_symlink():
                _path, raw = self._safe_file(command, "current-shadow/" + filename)
                payload = _strict_json(raw)
                available.append((source, filename, payload["observed_at"]))
        available.sort(key=lambda row: datetime.strptime(row[2], "%Y-%m-%dT%H:%M:%S.%fZ"))
        for source, filename, _observed in available:
            self._observe_checkpoint(source=source, filename=filename, **kwargs)

    def _build_shadow_receipt(self, *, run_id, attempt_id, request, envelope, snapshot, command):
        if command.run_directory != self._roots.data_root / "runs" / run_id / request.canonical_sha256:
            raise ValueError("Current Shadow receipt directory belongs to another run")
        policy_path, policy_raw = self._safe_file(command, "current-shadow/" + _SHADOW_FILES["request_policy"])
        receipt_path, receipt_raw = self._safe_file(command, "current-shadow/" + _SHADOW_FILES["receipt"])
        policy = _strict_json(policy_raw)
        inner = _strict_json(receipt_raw)
        if "run_id" in inner and inner["run_id"] != run_id:
            raise ValueError("Current Shadow receipt belongs to another run")
        from services.athena_run_service import _is_provisional_shadow_receipt
        if _is_provisional_shadow_receipt(inner):
            raise ValueError("Current Shadow startup marker is not terminal receipt evidence")
        source_summary = inner.get("source_summary")
        if type(source_summary) is not dict:
            raise ValueError("Current Shadow terminal receipt source summary is missing")
        portfolio = inner.get("portfolio")
        portfolio_sha = inner.get("portfolio_sha256")
        if portfolio is None:
            if portfolio_sha is not None:
                raise ValueError("Current Shadow portfolio digest exists without its portfolio")
        else:
            from domain import current_shadow_all_market_portfolio as portfolio_module
            if (type(portfolio) is not dict or type(portfolio_sha) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", portfolio_sha) is None
                    or portfolio_module._sha(portfolio) != portfolio_sha):
                raise ValueError("Current Shadow portfolio bytes do not match their exact digest")
        stage_payload = None
        progress_payload = None
        for source in ("stage", "progress"):
            try:
                _path, raw = self._safe_file(command, "current-shadow/" + _SHADOW_FILES[source])
            except FileNotFoundError:
                continue
            value = _strict_json(raw)
            expected_keys = _STAGE_KEYS if source == "stage" else _PROGRESS_KEYS
            if set(value) != expected_keys:
                raise ValueError("Current Shadow checkpoint schema drift")
            if source == "stage":
                stage_payload = value
            else:
                progress_payload = value
        from domain import current_shadow_run_contract_adapter as adapter
        adapted_request = adapter.adapt_current_shadow_request(
            target_size=request.target_legs,
            request_policy=policy,
            resolved_dates=request.dates,
            expected_create_share_code=request.create_share_code,
        )
        if adapted_request.to_dict() != request.to_dict():
            raise ValueError("Current Shadow request differs from committed identity")
        adapted = adapter.adapt_current_shadow_receipt(
            request=adapted_request,
            receipt_payload=inner,
            request_policy=policy,
            stage_payload=stage_payload,
            progress_payload=progress_payload,
        )
        # Accept only the exact capability vocabulary emitted by the reviewed
        # runner. The adapter still validates its safety and delivery semantics.
        if set(adapted.authority_manifest.additional_capabilities) != _LEGACY_AUTHORITY_KEYS:
            raise ValueError("Current Shadow legacy authority vocabulary drift")
        authority_fields = (
            "authority_profile", "mode", "provider_acquisition",
            "share_code_generation", "login", "cookies", "wallet", "staking", "wager",
        )
        if (adapted.request.to_dict() != request.to_dict()
                or adapted.exact_commit_sha != envelope.source_identity.value
                or any(getattr(adapted.authority_manifest, field)
                       != getattr(envelope.authority_manifest, field)
                       for field in authority_fields)
                or request.create_share_code != envelope.requested_operations.create_share_code
                or request.create_share_code is not False
                or adapted.wager_placed is not False
                or adapted.share_code_result is not None):
            raise ValueError("Current Shadow receipt differs from admitted authority")
        evidence = dict(adapted.evidence)
        source_identity_values = {}
        history_values = {}
        router_value = None
        if type(source_summary) is dict:
            source_identity_values = {
                key: source_summary[key]
                for key in ("current_fotmob", "current_fotmob_sources", "current_reconciliation_sha256",
                            "current_reconciliation_contract_sha256")
                if key in source_summary
            }
            history_values = {
                key: source_summary[key]
                for key in ("complete_current_history_sha256", "complete_current_history_sha256_by_request_date")
                if key in source_summary
            }
            router_value = source_summary.get("runtime_progress_diagnostics")
        # A terminal summary may omit detail already proven by the last typed
        # progress checkpoint. Both payloads were validated by the adapter and
        # are retained in the canonical receipt; keep exact checkpoint facts
        # when the terminal payload does not provide that identity category.
        if progress_payload is not None:
            checkpoint_summary = progress_payload["source_summary"]
            if not source_identity_values:
                source_identity_values = {
                    key: checkpoint_summary[key]
                    for key in ("current_fotmob", "current_fotmob_sources", "current_reconciliation_sha256",
                                "current_reconciliation_contract_sha256")
                    if key in checkpoint_summary
                }
            if not history_values:
                history_values = {
                    key: checkpoint_summary[key]
                    for key in ("complete_current_history_sha256", "complete_current_history_sha256_by_request_date")
                    if key in checkpoint_summary
                }
            if router_value is None:
                router_value = checkpoint_summary.get("runtime_progress_diagnostics")
        evidence.update({
            "legacy_authority_manifest_sha256": _sha(canonical_json_bytes(adapted.authority_manifest)),
            "admitted_authority_manifest_sha256": _sha(canonical_json_bytes(envelope.authority_manifest)),
            "run_id": run_id,
            "worker_attempt_id": attempt_id,
            "execution_envelope_sha256": envelope.canonical_sha256,
            "release_id": snapshot["release_id"],
            "run_01b_identity_refs": {
                "source_summary_sha256": _sha(canonical_json_bytes(source_summary)),
                "source_identity_sha256": None if not source_identity_values else _sha(canonical_json_bytes(source_identity_values)),
                "model_or_history_sha256": None if not history_values else _sha(canonical_json_bytes(history_values)),
                "router_diagnostics_sha256": None if router_value is None else _sha(canonical_json_bytes(router_value)),
                "portfolio_sha256": inner.get("portfolio_sha256"),
            },
            "producer_identity": {
                "kind": "CURRENT_SHADOW_TYPED_RECEIPT_ADAPTER_V1",
                "request_policy_sha256": _sha(policy_raw),
                "inner_receipt_sha256": _sha(receipt_raw),
                "stage_sha256": None if stage_payload is None else _sha(canonical_json_bytes(stage_payload)),
                "progress_sha256": None if progress_payload is None else _sha(canonical_json_bytes(progress_payload)),
            },
        })
        canonical = replace(adapted, authority_manifest=envelope.authority_manifest, evidence=evidence)
        canonical = RunReceipt.from_json_bytes(canonical_json_bytes(canonical))
        return canonical, policy_path, receipt_path

    def _observe_terminal_receipt(self, *, run_id, attempt_id, lease_token, receipt):
        """Attach verified result identities to an actual retained checkpoint."""
        legacy = receipt.evidence["legacy_current_shadow"]
        checkpoint = legacy["latest_stage_checkpoint"]
        if checkpoint is None:
            if receipt.evidence["run_01b_identity_refs"]["portfolio_sha256"] is not None:
                raise ValueError("Portfolio result lacks its typed COMPLETE checkpoint")
            return False
        from domain import current_shadow_run_contract_adapter as adapter
        parsed = adapter._checkpoint_stage(
            checkpoint, request=receipt.request,
            exact_commit_sha=receipt.exact_commit_sha, source="stage",
        )
        if receipt.evidence["run_01b_identity_refs"]["portfolio_sha256"] is not None and parsed.stage != "COMPLETE":
            raise ValueError("Portfolio result requires its typed COMPLETE checkpoint")
        if parsed.observed_at > receipt.observed_at:
            raise ValueError("terminal checkpoint postdates its typed receipt")
        previous = self._repository.latest_worker_progress(run_id)
        counts = {name: None for name in _PROGRESS_COUNT_NAMES}
        if previous is not None:
            counts = dict(previous["counts"])
        # The receipt carries these exact reviewed counts; Router counts remain
        # unavailable unless the typed progress checkpoint proved them.
        for name in _PROGRESS_COUNT_NAMES:
            if name in receipt.counts:
                counts[name] = receipt.counts[name]
        return self._repository.append_worker_progress(
            run_id, attempt_id, lease_token, {
                "stage": parsed.stage,
                "stage_index": adapter.CURRENT_STAGE_SEQUENCE.index(parsed.stage),
                "counts": counts,
                "observed_at": _iso(parsed.observed_at),
                "evidence_sha256": _sha(canonical_json_bytes(receipt)),
                "identity_refs": dict(receipt.evidence["run_01b_identity_refs"]),
            },
        )

    def _build_offline_probe_receipt(self, *, request, envelope, snapshot, command, run_id):
        """Prove only the offline identity probe; do not invent business output."""
        from runtime.worker_launcher import WORKER_OFFLINE_PROBE_FILENAME, WORKER_PROVENANCE_FILENAME
        _semantic_expected, provenance_expected = build_offline_probe_documents(command)
        _semantic_path, semantic_raw = self._safe_file(command, WORKER_OFFLINE_PROBE_FILENAME)
        _provenance_path, provenance_raw = self._safe_file(command, WORKER_PROVENANCE_FILENAME)
        semantic = _strict_json(semantic_raw)
        provenance = _strict_json(provenance_raw)
        if (semantic.get("provider_calls") != 0 or semantic.get("delivery_calls") != 0
                or semantic.get("wager") is not False or provenance != provenance_expected):
            raise ValueError("offline identity probe evidence is invalid")
        # No supported MAIN business executor is available in this E2 seam.
        # The child did not produce a canonical business receipt, so this
        # helper deliberately raises and the caller records INTERRUPTED.
        raise ValueError("offline identity probe has no business RunReceipt")

    def _monitor(self, *, run_id, attempt_id, lease_token, request, envelope,
                 snapshot, command, handle, locator_bound):
        self._sleep(self._initial_poll_delay)
        last_heartbeat = self._monotonic()
        progress_invalid = False
        owner_valid = True
        while True:
            if owner_valid and locator_bound:
                try:
                    self._observe_available_checkpoints(
                        run_id=run_id, attempt_id=attempt_id, lease_token=lease_token,
                        request=request, envelope=envelope, command=command,
                    )
                except (RunLeaseFenced, RunRepositoryError):
                    owner_valid = False
                except Exception:
                    progress_invalid = True
            now = self._monotonic()
            if owner_valid and now - last_heartbeat >= self._heartbeat_seconds:
                try:
                    self._repository.heartbeat(run_id, attempt_id, lease_token)
                    last_heartbeat = now
                except Exception:
                    owner_valid = False
            try:
                exit_code = handle.poll()
            except Exception:
                exit_code = None
                owner_valid = False
            if exit_code is not None:
                break
            self._sleep(self._poll_seconds)
        if type(exit_code) is not int or not owner_valid:
            with self._owned_lock:
                self._owned.pop(attempt_id, None)
            return
        published_digest = None
        try:
            if not locator_bound:
                raise LookupError("locator")
            if progress_invalid:
                raise ValueError("progress")
            if exit_code != 0:
                self._repository.interrupt_worker_without_receipt(
                    run_id, attempt_id, lease_token, exit_code=exit_code,
                    diagnostic_id="WORKER_EXIT_WITHOUT_VERIFIED_RECEIPT",
                    last_proven_stage=(self._repository.latest_worker_progress(run_id) or {}).get("stage"),
                )
                return
            if command.operation != "CURRENT_SHADOW_REQUEST":
                self._build_offline_probe_receipt(
                    request=request, envelope=envelope, snapshot=snapshot,
                    command=command, run_id=run_id,
                )
            receipt, _policy_path, _inner_path = self._build_shadow_receipt(
                run_id=run_id, attempt_id=attempt_id, request=request, envelope=envelope,
                snapshot=snapshot, command=command,
            )
            raw = canonical_json_bytes(receipt)
            self._observe_terminal_receipt(
                run_id=run_id, attempt_id=attempt_id, lease_token=lease_token,
                receipt=receipt,
            )
            digest = self._repository.publish_terminal_receipt(
                run_id, receipt_bytes=raw, expected_version=1,
                attempt_id=attempt_id, lease_token=lease_token,
            )
            published_digest = digest
            try:
                self._repository.project_terminal_receipt(digest)
            except Exception:
                # The retained exact receipt is the only repair input. Never
                # re-run the worker or create a second receipt.
                self._repository.project_terminal_receipt(digest)
        except LookupError:
            try:
                self._repository.interrupt_worker_without_receipt(
                    run_id, attempt_id, lease_token, exit_code=exit_code,
                    diagnostic_id="WORKER_PROCESS_LOCATOR_UNAVAILABLE",
                    last_proven_stage=(self._repository.latest_worker_progress(run_id) or {}).get("stage"),
                )
            except Exception:
                pass
        except Exception as error:
            if published_digest is not None:
                # Keep the fenced attempt/root occupied. The immutable receipt
                # is the sole input for later explicit projection repair.
                with self._owned_lock:
                    self._pending_projection[run_id] = published_digest
                return
            diagnostic = "WORKER_RECEIPT_INVALID"
            if isinstance(error, FileNotFoundError) or "receipt" in str(error).lower() and (
                    "unavailable" in str(error).lower() or "not terminal" in str(error).lower()):
                diagnostic = "WORKER_EXIT_WITHOUT_VERIFIED_RECEIPT"
            try:
                self._repository.interrupt_worker_without_receipt(
                    run_id, attempt_id, lease_token, exit_code=exit_code,
                    diagnostic_id=diagnostic,
                    last_proven_stage=(self._repository.latest_worker_progress(run_id) or {}).get("stage"),
                )
            except Exception:
                # A failed durable finalization remains inspectable and fenced;
                # this worker is never automatically retried or replaced.
                pass
        finally:
            with self._owned_lock:
                self._owned.pop(attempt_id, None)

    def repair_published_projection(self, receipt_sha256: str) -> bool:
        """Explicit idempotent receipt-only repair; this never launches work."""
        if type(receipt_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", receipt_sha256) is None:
            raise RunRepositoryError("invalid retained receipt digest")
        result = self._repository.project_terminal_receipt(receipt_sha256)
        with self._owned_lock:
            for run_id, digest in tuple(self._pending_projection.items()):
                if digest == receipt_sha256:
                    self._pending_projection.pop(run_id, None)
        return result


__all__ = ["WorkerCoordinator"]
