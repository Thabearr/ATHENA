"""Write-ahead anonymous CREATE transport. Not wired to product execution.

An operation row never grants authority or schedules work. Transports are explicit
dependencies; this module never selects a live adapter and never retries CREATE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from domain.run_contracts import canonical_json_bytes
from scripts import sportybet_direct_share_bridge as bridge


class DeliveryOutcome(str, Enum):
    LOCAL_PRE_SEND_BLOCKED = "LOCAL_PRE_SEND_BLOCKED"
    CREATE_PROVEN_FAILED = "CREATE_PROVEN_FAILED"  # Reserved; no reviewed provider no-create proof.
    CREATE_OUTCOME_UNKNOWN = "CREATE_OUTCOME_UNKNOWN"
    CREATE_CONFIRMED_RELOAD_UNVERIFIED = "CREATE_CONFIRMED_RELOAD_UNVERIFIED"
    CREATE_CONFIRMED_RELOAD_VERIFIED = "CREATE_CONFIRMED_RELOAD_VERIFIED"


@dataclass(frozen=True)
class DurableCreateResult:
    outcome: DeliveryOutcome
    operation_id: str | None
    code: str | None = None
    create_response_artifact_id: str | None = None
    reload_response_artifact_id: str | None = None


class DurableShareCodeTransport:
    def __init__(self, repository, *, run_id, attempt_id, lease_token,
                 post_create_once, load_share_code_once):
        if not callable(post_create_once) or not callable(load_share_code_once):
            raise ValueError("explicit transport dependencies required")
        self.repository = repository
        self.run_id = run_id
        self.owner = {"attempt_id": attempt_id, "lease_token": lease_token}
        self.post = post_create_once
        self.get = load_share_code_once

    def _row(self, operation_id):
        return self.repository.share_code_operation(self.run_id, operation_id, **self.owner)

    def _response(self, operation_id, artifact_id, **kwargs):
        return self.repository.read_share_code_response(
            self.run_id, operation_id, artifact_id, **self.owner, **kwargs)

    def _unknown(self, operation_id, error_code):
        # A storage/fence failure keeps SENT as honest uncertainty. Never mask
        # that gap with FAILED or invoke a replacement transport.
        try:
            self.repository.transition_external_operation(
                self.run_id, operation_id, **self.owner, expected_state="SENT",
                state="OUTCOME_UNKNOWN", error_code=error_code)
        except Exception:
            pass
        return DurableCreateResult(DeliveryOutcome.CREATE_OUTCOME_UNKNOWN, operation_id)

    def create(self, selections):
        operation_id = None
        try:
            operation_id, created = self.repository.prepare_share_code_create(
                self.run_id, **self.owner, selections=selections)
            row = self._row(operation_id)
            if not created:
                # Repeated invocation is evidence-only, including PREPARED.
                # It never drains PREPARED, resumes SENT, or replays a GET.
                if row["state"] == "CONFIRMED":
                    response = self._response(operation_id, row["response_artifact_id"])
                    code = bridge.extract_share_code(bridge.parse_response(response))
                    return DurableCreateResult(DeliveryOutcome.CREATE_CONFIRMED_RELOAD_UNVERIFIED,
                                               operation_id, code, row["response_artifact_id"])
                outcome = (DeliveryOutcome.LOCAL_PRE_SEND_BLOCKED
                           if row["state"] in {"PREPARED", "FAILED"}
                           else DeliveryOutcome.CREATE_OUTCOME_UNKNOWN)
                return DurableCreateResult(outcome, operation_id)
            # Returning from the repository method includes synchronous FULL
            # transaction commit. POST is unreachable if this call fails.
            self.repository.transition_external_operation(
                self.run_id, operation_id, **self.owner,
                expected_state="PREPARED", state="SENT")
        except Exception:
            # Only a still-PREPARED row can carry proven never-sent truth.
            if operation_id is not None:
                try:
                    if self._row(operation_id)["state"] in {"SENT", "OUTCOME_UNKNOWN"}:
                        return self._unknown(operation_id, "SHARE_CREATE_TRANSPORT_UNKNOWN")
                except Exception:
                    # Cannot prove PREPARED after a commit/fence gap.
                    return DurableCreateResult(DeliveryOutcome.CREATE_OUTCOME_UNKNOWN, operation_id)
                try:
                    self.repository.transition_external_operation(
                        self.run_id, operation_id, **self.owner, expected_state="PREPARED",
                        state="FAILED", error_code="SHARE_CREATE_NEVER_SENT")
                except Exception:
                    pass
            return DurableCreateResult(DeliveryOutcome.LOCAL_PRE_SEND_BLOCKED, operation_id)

        try:
            response = self.post(request_bytes=canonical_json_bytes(row["input"]["body"]))
            artifact_id = self.repository.retain_share_code_response(
                self.run_id, operation_id, **self.owner, response=response)
            proven = self._response(operation_id, artifact_id)
            if proven.status != 200:
                return self._unknown(operation_id, "SHARE_CREATE_RESPONSE_UNPROVEN")
            code = bridge.extract_share_code(bridge.parse_response(proven))
            self.repository.transition_external_operation(
                self.run_id, operation_id, **self.owner, expected_state="SENT",
                state="CONFIRMED", response_artifact_id=artifact_id)
        except BaseException as error:
            result = self._unknown(operation_id, "SHARE_CREATE_TRANSPORT_UNKNOWN")
            if not isinstance(error, Exception):
                raise
            return result
        return self.reload(operation_id)

    def reload(self, operation_id):
        """One explicit read-only verification attempt, never a second CREATE."""
        code = None
        artifact_id = None
        confirmed = False
        reload_id = None
        try:
            row = self._row(operation_id)
            if row["state"] != "CONFIRMED":
                return DurableCreateResult(DeliveryOutcome.CREATE_OUTCOME_UNKNOWN, operation_id)
            artifact_id = row["response_artifact_id"]
            create = self._response(operation_id, artifact_id)
            if create.status != 200:
                raise bridge.SportyBetDirectShareError("CREATE success not proven")
            payload = bridge.parse_response(create)
            code = bridge.extract_share_code(payload)
            confirmed = True
            # Reauthentication and durable code proof precede every GET.
            response = self.get(code=code)
            reload_id = self.repository.retain_share_code_response(
                self.run_id, operation_id, **self.owner, response=response, method="GET")
            proven = self._response(operation_id, reload_id, method="GET", code=code)
            if proven.status != 200:
                raise bridge.SportyBetDirectShareError("reload HTTP success unproven")
            bridge._validate_exact_roundtrip(
                requested=tuple(row["input"]["body"]["selections"]),
                create_payload=payload, load_payload=bridge.parse_response(proven))
            return DurableCreateResult(DeliveryOutcome.CREATE_CONFIRMED_RELOAD_VERIFIED,
                                       operation_id, code, artifact_id, reload_id)
        except Exception:
            outcome = (DeliveryOutcome.CREATE_CONFIRMED_RELOAD_UNVERIFIED if confirmed
                       else DeliveryOutcome.LOCAL_PRE_SEND_BLOCKED)
            return DurableCreateResult(outcome, operation_id, code, artifact_id, reload_id)
