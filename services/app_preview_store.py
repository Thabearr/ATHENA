"""D3 / DATA-01A durable app-backed PreviewStore adapter.

Implements the D1 ``StoredPreview`` persistence contract (``put`` / ``get``)
against the app-owned SQLite store via :class:`database.app_repository.AppRepository`.
This is a tightly-scoped adapter: it never regenerates ``request_bytes``,
``envelope_bytes`` or the exact ``ExecutionPreview`` bytes from formatted strings
and never grants run authority.

On both ``put`` and ``get`` the adapter verifies that the request, envelope,
preview and capability-report digests agree (the D1 "stored preview identity
drifted" contract). Persistence preserves exact D1 bytes and round-trips them
through :class:`StoredPreview` with equal ``preview_id``, ``request_bytes``,
``envelope_bytes``, ``preview_bytes`` and ``expires_at``.

``ProcessLocalPreviewStore`` remains the required default; this durable store is
constructed and injected separately (lazily) at the composition root. This
module is not imported by ``services.athena_preview_service`` at import time.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from domain.execution_envelope import ExecutionEnvelope, ExecutionPreview
from domain.run_contracts import RunRequest, canonical_json_bytes

from database.app_repository import (
    AppRepository,
    AppValidationError,
    CAPABILITY_PROFILES,
)
from services.athena_preview_service import StoredPreview


class DurablePreviewStore:
    """Durable PreviewStore backed by the app-owned store."""

    def __init__(
        self,
        repository: AppRepository,
        *,
        release_id: str,
        local_profile_id: str = "local-default",
    ) -> None:
        if not isinstance(repository, AppRepository):
            raise ValueError("an AppRepository is required")
        if type(release_id) is not str or not release_id:
            raise ValueError("release_id must be non-empty exact text")
        if type(local_profile_id) is not str or not local_profile_id:
            raise ValueError("local_profile_id must be non-empty exact text")
        self._repository = repository
        self._release_id = release_id
        self._local_profile_id = local_profile_id

    def put(self, item: StoredPreview, *, now: datetime) -> None:
        checked_now = _aware_utc(now)
        if type(item) is not StoredPreview or item.expires_at <= checked_now:
            raise ValueError("preview store item is invalid")

        # Validate request / envelope / preview digests agree before persisting.
        request, envelope, preview = _verify_stored_identity(item)

        profile = envelope.authority_manifest.authority_profile
        if profile not in CAPABILITY_PROFILES:
            raise ValueError("capability profile is outside the reviewed vocabulary")

        # Mirror ProcessLocalPreviewStore: a preview ID collision is an error.
        if self._repository.fetch_preview_record(item.preview_id) is not None:
            raise ValueError("preview ID collision")

        report_bytes = item.preview_bytes
        report_sha256 = hashlib.sha256(report_bytes).hexdigest()
        snapshot_id = f"capability-{report_sha256}"
        evaluated_at = envelope.issued_at

        # Ensure the local presentation profile exists (idempotent).
        self._repository.ensure_local_profile(now=checked_now)
        # Capability evidence is attributed to the running, verified release.
        self._repository.record_capability_snapshot(
            snapshot_id=snapshot_id,
            release_id=self._release_id,
            profile=profile,
            report_bytes=report_bytes,
            report_sha256=report_sha256,
            evaluated_at=evaluated_at,
            expires_at=envelope.expires_at,
        )
        self._repository.insert_preview_record(
            preview_id=item.preview_id,
            profile_id=self._local_profile_id,
            request_bytes=item.request_bytes,
            request_sha256=hashlib.sha256(item.request_bytes).hexdigest(),
            envelope_bytes=item.envelope_bytes,
            envelope_sha256=hashlib.sha256(item.envelope_bytes).hexdigest(),
            capability_snapshot_id=snapshot_id,
            created_at=evaluated_at,
            expires_at=envelope.expires_at,
        )

    def get(self, preview_id: str, *, now: datetime) -> StoredPreview | None:
        checked_now = _aware_utc(now)
        if type(preview_id) is not str or not preview_id:
            return None
        try:
            record = self._repository.fetch_preview_record(preview_id)
        except AppValidationError:
            return None
        if record is None:
            return None

        request_bytes = record["request_bytes"]
        envelope_bytes = record["envelope_bytes"]
        report_bytes = self._capability_report(record["capability_snapshot_id"])
        if report_bytes is None:
            return None

        # Validate stored column identities against the exact bytes.
        try:
            if (
                hashlib.sha256(request_bytes).hexdigest() != record["request_sha256"]
                or hashlib.sha256(envelope_bytes).hexdigest() != record["envelope_sha256"]
            ):
                return None
        except Exception:
            return None

        candidate = StoredPreview(
            preview_id=record["preview_id"],
            request_bytes=request_bytes,
            envelope_bytes=envelope_bytes,
            preview_bytes=report_bytes,
            expires_at=_parse_utc_text(record["expires_at"]),
        )
        try:
            _verify_stored_identity(candidate)
        except Exception:
            # Fail-closed: corrupted or drifted records are indistinguishable
            # from unknown IDs and are never returned.
            return None

        if candidate.expires_at <= checked_now:
            return None
        return candidate

    def _capability_report(self, snapshot_id: str) -> bytes | None:
        try:
            snapshot = self._repository.get_capability_snapshot(snapshot_id)
        except AppValidationError:
            return None
        if snapshot is None:
            return None
        report_bytes = snapshot["report_bytes"]
        if type(report_bytes) is not bytes:
            return None
        if hashlib.sha256(report_bytes).hexdigest() != snapshot["report_sha256"]:
            return None
        return report_bytes


# --- shared identity verification -----------------------------------------

def _verify_stored_identity(
    item: StoredPreview,
) -> tuple[RunRequest, ExecutionEnvelope, ExecutionPreview]:
    """Verify request / envelope / preview digests agree (D1 drift contract).

    Returns the parsed contracts. Raises ``ValueError`` on any drift.
    """
    try:
        request = RunRequest.from_json_bytes(item.request_bytes)
        envelope = ExecutionEnvelope.from_json_bytes(item.envelope_bytes)
        preview = ExecutionPreview.from_json_bytes(item.preview_bytes)
        if (
            envelope.expires_at != item.expires_at
            or canonical_json_bytes(request) != item.request_bytes
            or envelope.request_bytes != item.request_bytes
            or hashlib.sha256(item.request_bytes).hexdigest() != envelope.request_sha256
            or preview.execution_envelope_sha256 != envelope.canonical_sha256
            or preview.request_sha256 != envelope.request_sha256
            or preview.source_identity != envelope.source_identity
            or preview.authority_manifest != envelope.authority_manifest
            or preview.canonical_bytes != item.preview_bytes
        ):
            raise ValueError("stored preview identity drifted")
    except ValueError:
        raise
    except Exception:
        raise ValueError("stored preview identity drifted") from None
    return request, envelope, preview


def _aware_utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError("preview store clock must be an aware UTC instant")
    return value.astimezone(timezone.utc)


def _parse_utc_text(text: str) -> datetime:
    if type(text) is not str or not text.endswith("Z"):
        raise ValueError("stored timestamp must be canonical UTC text")
    base = text[:-1]
    if "." in base:
        head, frac = base.split(".", 1)
        micro = int(frac.ljust(6, "0")[:6])
    else:
        head, micro = base, 0
    parsed = datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").replace(microsecond=micro, tzinfo=timezone.utc)
    return parsed
