"""Canonical request/receipt orchestration boundary for ATHENA runs.

This module sequences reviewed executors and durable evidence only.  It does
not contain football, pricing, routing, portfolio, stake, or provider policy.
The production MAIN executor is the existing target-only fail-closed request
boundary. The production SHADOW executor is a lazy adapter to the existing
bounded Current Shadow supervisor and never runs during offline proof.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Protocol

from domain.run_contracts import (
    AuthorityManifest,
    RunContractError,
    RunReceipt,
    RunRequest,
    RunStage,
    canonical_json_bytes,
)


class AthenaRunServiceError(RuntimeError):
    """Raised when a run cannot be safely bound to canonical evidence."""


@dataclass(frozen=True)
class ExecutorResult:
    """Untrusted executor outcome which the service binds into a RunReceipt."""

    status: str
    stages: tuple[RunStage, ...] = ()
    selected_legs: tuple[Mapping[str, Any], ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)
    share_code_result: Mapping[str, Any] | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


class RunExecutor(Protocol):
    def __call__(
        self,
        request: RunRequest,
        *,
        authority_manifest: AuthorityManifest,
        run_directory: Path,
        exact_commit_sha: str,
        observed_at: datetime,
    ) -> ExecutorResult: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git_head() -> str:
    repository_root = Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AthenaRunServiceError("could not bind run to exact Git HEAD") from exc
    result = completed.stdout.strip()
    if len(result) != 40 or any(character not in "0123456789abcdef" for character in result):
        raise AthenaRunServiceError("Git HEAD is not an exact lowercase commit SHA")
    return result


def _write_new_atomically(path: Path, payload: bytes) -> None:
    """Publish a new file atomically without replacing contradictory evidence."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard-link publication is atomic and, unlike replace(), cannot
        # overwrite a concurrent or pre-existing receipt/request.
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise AthenaRunServiceError(f"refusing to overwrite existing evidence: {path.name}")
    except AthenaRunServiceError:
        raise
    except OSError as exc:
        raise AthenaRunServiceError(f"could not persist {path.name} atomically") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_for(request: RunRequest) -> AuthorityManifest:
    if (
        request.authority_profile,
        request.mode,
        request.bookie,
        request.create_share_code,
    ) == ("MAIN", "main_application", "sportybet", False):
        acquisition, share_code = False, False
    elif (
        request.authority_profile,
        request.mode,
        request.bookie,
        request.create_share_code,
    ) == ("SHADOW", "research_shadow", "sportybet", True):
        acquisition, share_code = True, True
    else:
        # Unsupported profile/mode combinations receive no capabilities.
        acquisition, share_code = False, False
    return AuthorityManifest(
        authority_profile=request.authority_profile,
        mode=request.mode,
        provider_acquisition=acquisition,
        share_code_generation=share_code,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )


def _contains_true_wager_flag(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"wager_placed", "wager", "bet", "stake_submitted"} and item is True:
                return True
            if _contains_true_wager_flag(item):
                return True
    elif type(value) in {tuple, list}:
        return any(_contains_true_wager_flag(item) for item in value)
    return False


def _check_request_authority(request: RunRequest, manifest: AuthorityManifest) -> str | None:
    if request.bookie != "sportybet":
        return "EXECUTOR_UNAVAILABLE"
    if (request.authority_profile, request.mode) == ("MAIN", "main_application"):
        if request.create_share_code is not False:
            return "REQUEST_AUTHORITY_MISMATCH"
        return None
    if (request.authority_profile, request.mode) == ("SHADOW", "research_shadow"):
        if request.create_share_code is not True:
            return "REQUEST_AUTHORITY_MISMATCH"
        return None
    return "EXECUTOR_UNAVAILABLE"


class _MainFailClosedExecutor:
    """Use only the reviewed target-only MAIN authority boundary."""

    def __call__(
        self,
        request: RunRequest,
        *,
        authority_manifest: AuthorityManifest,
        run_directory: Path,
        exact_commit_sha: str,
        observed_at: datetime,
    ) -> ExecutorResult:
        del exact_commit_sha, observed_at
        if authority_manifest.provider_acquisition or authority_manifest.share_code_generation:
            raise AthenaRunServiceError("MAIN executor received excess authority")
        # Import at invocation time. Importing the CLI/service cannot initialize
        # provider clients or any application engines.
        from domain.current_sportybet_accumulator_request import (
            execute_current_accumulator_request,
        )

        result = execute_current_accumulator_request(
            target_size=request.target_legs,
            output_dir=run_directory,
        )
        if (
            result.real_current_provider_execution_attempted is not False
            or result.wager_placed is not False
            or result.requested_target_size != request.target_legs
        ):
            raise AthenaRunServiceError("MAIN target-only boundary returned unsafe evidence")
        return ExecutorResult(
            status="MAIN_PHASE6_AUTHORITY_REQUIRED",
            stages=(RunStage(
                stage="MAIN_AUTHORITY_CHECK",
                status="BLOCKED",
                observed_at=result.evaluation_time,
                evidence={"blocked_at": result.blocked_at},
            ),),
            evidence={
                "main_target_only_request": result.to_dict(),
                "fixture_execution": False,
                "dates_are_user_intent_only": True,
                "provider_acquisition": False,
            },
        )


class _ShadowSupervisorExecutor:
    """Bounded adapter to the reviewed explicit-date Current Shadow supervisor."""

    def __call__(
        self,
        request: RunRequest,
        *,
        authority_manifest: AuthorityManifest,
        run_directory: Path,
        exact_commit_sha: str,
        observed_at: datetime,
    ) -> ExecutorResult:
        if authority_manifest.authority_profile != "SHADOW":
            raise AthenaRunServiceError("SHADOW executor received wrong profile")
        from domain import current_shadow_fixture_date_request as date_policy

        requested_text = tuple(day.strftime("%Y%m%d") for day in request.dates)
        try:
            representable = date_policy.validate_fixture_dates(
                requested_text,
                current_utc=observed_at.astimezone(timezone.utc),
            )
        except date_policy.CurrentShadowFixtureDateRequestError:
            return ExecutorResult(
                status="SHADOW_DATE_POLICY_UNREPRESENTABLE",
                evidence={
                    "reason": "Requested Lagos calendar date is outside the exact existing UTC rolling window.",
                    "request_dates_preserved": [day.isoformat() for day in request.dates],
                    "existing_policy_timezone": "UTC",
                    "provider_acquisition": False,
                },
            )
        if representable != requested_text:
            return ExecutorResult(
                status="SHADOW_DATE_POLICY_UNREPRESENTABLE",
                evidence={
                    "reason": "Existing UTC date validation did not preserve exact requested dates.",
                    "request_dates_preserved": [day.isoformat() for day in request.dates],
                    "provider_acquisition": False,
                },
            )

        shadow_output_dir = run_directory / "current-shadow"
        request_policy_path = shadow_output_dir / "current-shadow-request-policy.json"
        receipt_path = shadow_output_dir / "current-shadow-all-market-run-receipt.json"
        stage_path = shadow_output_dir / "current-shadow-all-market-stage.json"
        progress_path = shadow_output_dir / "current-shadow-all-market-progress.json"
        command = [
            sys.executable,
            "-m",
            "scripts.execute_current_shadow_request",
            "--target-size",
            str(request.target_legs),
            "--fixture-scope",
            "today",
            "--fixture-dates",
            ",".join(representable),
            "--output-dir",
            str(shadow_output_dir),
        ]
        # This code path is only reached by an actual SHADOW run request. Tests
        # and audits inject synthetic executors and never call this supervisor.
        try:
            from scripts import execute_current_shadow_all_market_fresh_reprice_bound as bound

            completed = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[1],
                check=False,
                capture_output=True,
                text=True,
                timeout=bound._supervisor_timeout_seconds(),
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutorResult(
                status="SOURCE_INCOMPLETE",
                evidence={
                    "reason": "Current Shadow supervisor exceeded its reviewed bounded runtime.",
                    "provider_acquisition": True,
                    "current_shadow_triggered": True,
                    "stdout_tail": _bounded_text(exc.stdout),
                    "stderr_tail": _bounded_text(exc.stderr),
                },
            )
        except OSError as exc:
            return ExecutorResult(
                status="EXECUTOR_UNAVAILABLE",
                evidence={
                    "reason": "Current Shadow supervisor could not be started.",
                    "error_type": type(exc).__name__,
                    "provider_acquisition": False,
                    "current_shadow_triggered": False,
                },
            )

        if not receipt_path.is_file() or not request_policy_path.is_file():
            return ExecutorResult(
                status="SOURCE_INCOMPLETE",
                evidence={
                    "reason": "Current Shadow supervisor produced no complete policy/terminal receipt pair.",
                    "supervisor_returncode": completed.returncode,
                    "provider_acquisition": True,
                    "current_shadow_triggered": True,
                    "stdout_tail": _bounded_text(completed.stdout),
                    "stderr_tail": _bounded_text(completed.stderr),
                },
            )

        try:
            request_policy = _read_json_object(request_policy_path)
            shadow_receipt = _read_json_object(receipt_path)
            stage_payload = _read_json_object(stage_path) if stage_path.is_file() else None
            progress_payload = _read_json_object(progress_path) if progress_path.is_file() else None
            from domain import current_shadow_run_contract_adapter as adapter

            adapted_request = adapter.adapt_current_shadow_request(
                target_size=request.target_legs,
                request_policy=request_policy,
                resolved_dates=request.dates,
            )
            if adapted_request.canonical_sha256 != request.canonical_sha256:
                raise AthenaRunServiceError(
                    "Current Shadow request adapter changed canonical request identity"
                )
            adapted = adapter.adapt_current_shadow_receipt(
                request=adapted_request,
                receipt_payload=shadow_receipt,
                request_policy=request_policy,
                stage_payload=stage_payload,
                progress_payload=progress_payload,
            )
            if adapted.exact_commit_sha != exact_commit_sha:
                raise AthenaRunServiceError("Current Shadow receipt commit differs from the service-bound Git HEAD")
            if adapted.wager_placed is not False:
                raise AthenaRunServiceError("Current Shadow adapter returned wager authority/result")
        except AthenaRunServiceError:
            raise
        except Exception as exc:
            return ExecutorResult(
                status="CODE_VERIFICATION_FAILED",
                evidence={
                    "reason": "Current Shadow output did not pass the canonical run-contract adapter.",
                    "error_type": type(exc).__name__,
                    "supervisor_returncode": completed.returncode,
                    "provider_acquisition": True,
                    "current_shadow_triggered": True,
                },
            )

        return ExecutorResult(
            status=adapted.status,
            stages=adapted.stages,
            selected_legs=adapted.selected_legs,
            counts=adapted.counts,
            share_code_result=adapted.share_code_result,
            evidence={
                "current_shadow_adapter": adapted.to_dict(),
                "supervisor_returncode": completed.returncode,
                "request_policy_path": request_policy_path.name,
                "terminal_receipt_path": receipt_path.name,
            },
        )


def _bounded_text(value: Any, limit: int = 2000) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if type(value) is not str:
        return None
    return value[-limit:]


def _read_json_object(path: Path) -> dict[str, Any]:
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON object key")
            value[key] = item
        return value

    payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    if type(payload) is not dict:
        raise ValueError("expected JSON object")
    return payload


_SOURCE_CONTROLLED_EXECUTORS: Mapping[tuple[str, str, str], RunExecutor] = {
    ("MAIN", "main_application", "sportybet"): _MainFailClosedExecutor(),
    ("SHADOW", "research_shadow", "sportybet"): _ShadowSupervisorExecutor(),
}


class AthenaRunService:
    """Persist and execute exact RunRequests through reviewed source mappings.

    ``_test_executor_overrides`` and ``_commit_sha_provider`` are private
    dependency-injection seams used only by deterministic offline tests.
    """

    def __init__(
        self,
        *,
        _test_executor_overrides: Mapping[tuple[str, str, str], RunExecutor] | None = None,
        _commit_sha_provider: Callable[[], str] | None = None,
        _clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if _test_executor_overrides is not None and not isinstance(_test_executor_overrides, Mapping):
            raise TypeError("test executor overrides must be a mapping")
        self._executors = dict(_SOURCE_CONTROLLED_EXECUTORS)
        if _test_executor_overrides:
            for key, executor in _test_executor_overrides.items():
                if (
                    type(key) is not tuple
                    or len(key) != 3
                    or any(type(part) is not str for part in key)
                    or not callable(executor)
                ):
                    raise TypeError("invalid test-only executor override")
                self._executors[key] = executor
        self._commit_sha_provider = _commit_sha_provider or _git_head
        self._clock = _clock

    @staticmethod
    def authority_manifest_for(request: RunRequest) -> AuthorityManifest:
        """Return the source-controlled manifest used for this exact request.

        The CLI uses this to display permissions before invoking ``run``; it
        does not independently restate profile capability rules.
        """

        if type(request) is not RunRequest:
            raise AthenaRunServiceError("request must be exact domain.run_contracts.RunRequest")
        return _manifest_for(request)

    def run(self, request: RunRequest, *, output_root: Path) -> RunReceipt:
        if type(request) is not RunRequest:
            raise AthenaRunServiceError("request must be exact domain.run_contracts.RunRequest")
        if not isinstance(output_root, Path):
            raise AthenaRunServiceError("output_root must be pathlib.Path")
        try:
            exact_commit_sha = self._commit_sha_provider()
            if (
                type(exact_commit_sha) is not str
                or len(exact_commit_sha) != 40
                or exact_commit_sha != exact_commit_sha.lower()
                or any(character not in "0123456789abcdef" for character in exact_commit_sha)
            ):
                raise AthenaRunServiceError("commit provider returned an invalid exact Git SHA")
            observed_at = self._clock()
            if type(observed_at) is not datetime or observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise AthenaRunServiceError("service clock must return aware datetime")
            observed_at = observed_at.astimezone(timezone.utc)
            manifest = self.authority_manifest_for(request)
            expected_request_bytes = canonical_json_bytes(request)
        except AthenaRunServiceError:
            raise
        except Exception as exc:
            raise AthenaRunServiceError("could not establish run identity/authority") from exc

        run_directory = output_root / request.canonical_sha256
        try:
            run_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AthenaRunServiceError("could not create deterministic request directory") from exc
        request_path = run_directory / "athena-run-request.json"
        receipt_path = run_directory / "athena-run-receipt.json"

        request_preexisted = request_path.exists()
        if request_preexisted:
            try:
                existing_request_bytes = request_path.read_bytes()
                existing_request = RunRequest.from_json_bytes(existing_request_bytes)
            except (OSError, RunContractError) as exc:
                raise AthenaRunServiceError("existing request evidence is corrupt") from exc
            if existing_request != request or existing_request_bytes != expected_request_bytes:
                raise AthenaRunServiceError("existing request evidence does not bind exact RunRequest")
        else:
            _write_new_atomically(request_path, expected_request_bytes)

        if receipt_path.exists():
            try:
                receipt_bytes = receipt_path.read_bytes()
                receipt = RunReceipt.from_json_bytes(receipt_bytes)
            except (OSError, RunContractError) as exc:
                raise AthenaRunServiceError("existing receipt evidence is corrupt") from exc
            if (
                receipt.request != request
                or receipt.exact_commit_sha != exact_commit_sha
                or receipt.authority_manifest != manifest
                or receipt.wager_placed is not False
                or receipt_bytes != canonical_json_bytes(receipt)
            ):
                raise AthenaRunServiceError("existing receipt evidence does not bind this exact run")
            return receipt

        if request_preexisted:
            # The request may have been persisted before a crash or interrupted
            # executor. Replaying could duplicate side effects, so require
            # explicit recovery rather than silently invoking it again.
            raise AthenaRunServiceError("request evidence exists without a terminal receipt; refusing rerun")

        terminal_status = _check_request_authority(request, manifest)
        executor = self._executors.get((request.authority_profile, request.mode, request.bookie))
        if request.target_total_odds is not None:
            outcome = ExecutorResult(
                status="TARGET_TOTAL_ODDS_NOT_SUPPORTED",
                evidence={
                    "reason": "No reviewed canonical target-total-odds objective is available.",
                    "executor_invoked": False,
                },
            )
        elif terminal_status is not None:
            outcome = ExecutorResult(
                status=terminal_status,
                evidence={"executor_invoked": False, "reason": "Request authority/profile is unsupported."},
            )
        elif executor is None:
            outcome = ExecutorResult(
                status="EXECUTOR_UNAVAILABLE",
                evidence={"executor_invoked": False, "reason": "No source-controlled executor is registered."},
            )
        else:
            try:
                outcome = executor(
                    request,
                    authority_manifest=manifest,
                    run_directory=run_directory,
                    exact_commit_sha=exact_commit_sha,
                    observed_at=observed_at,
                )
            except AthenaRunServiceError:
                raise
            except Exception as exc:
                raise AthenaRunServiceError("source-controlled executor failed") from exc

        if type(outcome) is not ExecutorResult:
            raise AthenaRunServiceError("executor must return exact ExecutorResult")
        if type(outcome.status) is not str or not outcome.status or outcome.status != outcome.status.strip():
            raise AthenaRunServiceError("executor returned invalid terminal status")
        if type(outcome.stages) is not tuple or any(type(stage) is not RunStage for stage in outcome.stages):
            raise AthenaRunServiceError("executor returned malformed stages")
        if type(outcome.selected_legs) is not tuple:
            raise AthenaRunServiceError("executor selected_legs must be an exact tuple")
        if len(outcome.selected_legs) > request.target_legs:
            raise AthenaRunServiceError("executor exceeded maximum desired target_legs")
        if outcome.evidence is None or not isinstance(outcome.evidence, Mapping):
            raise AthenaRunServiceError("executor evidence must be a mapping")
        if _contains_true_wager_flag(outcome.evidence):
            raise AthenaRunServiceError("executor evidence contradicts wager=false authority")
        if not outcome.selected_legs and outcome.share_code_result is not None:
            raise AthenaRunServiceError("empty selection cannot carry share-code result")

        shortfall = request.target_legs - len(outcome.selected_legs)
        if not isinstance(outcome.counts, Mapping):
            raise AthenaRunServiceError("executor counts must be a mapping")
        counts = dict(outcome.counts)
        for key, value in counts.items():
            if type(key) is not str or not key or type(value) is not int or value < 0:
                raise AthenaRunServiceError("executor counts must be non-negative exact integers")
        for name, expected in (
            ("selected_leg_count", len(outcome.selected_legs)),
            ("target_legs", request.target_legs),
            ("shortfall", shortfall),
        ):
            if name in counts and counts[name] != expected:
                raise AthenaRunServiceError(f"executor {name} contradicts canonical request/result")
            counts[name] = expected
        try:
            receipt = RunReceipt(
                status=outcome.status,
                observed_at=observed_at,
                exact_commit_sha=exact_commit_sha,
                request=request,
                stages=outcome.stages,
                counts=counts,
                selected_legs=outcome.selected_legs,
                shortfall=shortfall,
                share_code_result=outcome.share_code_result,
                authority_manifest=manifest,
                evidence=outcome.evidence,
                wager_placed=False,
            )
        except (RunContractError, TypeError, ValueError) as exc:
            raise AthenaRunServiceError("executor output could not form a safe RunReceipt") from exc

        _write_new_atomically(receipt_path, canonical_json_bytes(receipt))
        return receipt


__all__ = ["AthenaRunService", "AthenaRunServiceError", "ExecutorResult", "RunExecutor"]
