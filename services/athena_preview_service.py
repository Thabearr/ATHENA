"""Immutable local previews and fail-closed run admission boundary.

Preview construction is a bounded, process-local read-only computation. The
supported application has no D3/D4 transactional run repository, so its
admission port is deliberately unavailable. No executor or provider is
reachable from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import re
import secrets
import threading
from typing import Callable, Literal, Protocol

from domain.execution_envelope import (
    DATE_RESOLUTION_POLICY_ID,
    DATE_RESOLUTION_TIMEZONE_ID,
    EXECUTION_ENVELOPE_V3_SCHEMA_VERSION,
    PREVIEW_CLOCK_POLICY_ID,
    ExecutionEnvelope,
    ExecutionPreview,
    RequestedOperationIntent,
    SourceReleaseIdentity,
    evaluate_execution_envelope,
)
from domain.run_contracts import (
    AuthorityManifest,
    RunContractError,
    RunRequest,
    canonical_json_bytes,
)
from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    InstalledReleaseIdentity,
    MANIFEST_FILENAME,
    ReleaseIdentityError,
    verify_development_checkout,
    verify_installed_release,
)
from runtime.resources import ResourceResolver
from services.athena_run_request_parser import (
    AthenaRunRequestParseError,
    parse_explicit_request,
)
from services.athena_run_service import AthenaRunService


PREVIEW_TTL = timedelta(minutes=30)
MAX_PREVIEWS_PER_APP = 1024
_DATE_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", re.ASCII)
_SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$", re.ASCII)
_PREVIEW_ID = re.compile(r"^[A-Za-z0-9_-]{32,128}$", re.ASCII)
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("preview clock must return an aware datetime")
    return value.astimezone(timezone.utc)


class PreviewAdmissionError(Exception):
    """Typed safe failure; callers serialize only these finite fields."""

    def __init__(self, status_code: int, code: str, safe_message: str, retry_class: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.safe_message = safe_message
        self.retry_class = retry_class


@dataclass(frozen=True)
class StoredPreview:
    preview_id: str
    request_bytes: bytes
    envelope_bytes: bytes
    preview_bytes: bytes
    expires_at: datetime


class ProcessLocalPreviewStore:
    """One-app bounded store; restart invalidates every opaque preview ID."""

    def __init__(self, *, max_items: int = MAX_PREVIEWS_PER_APP):
        if type(max_items) is not int or max_items < 1:
            raise ValueError("preview store limit must be a positive exact integer")
        self._max_items = max_items
        self._items: dict[str, StoredPreview] = {}
        self._lock = threading.Lock()

    def put(self, item: StoredPreview, *, now: datetime) -> None:
        checked_now = _aware_utc(now)
        if type(item) is not StoredPreview or item.expires_at <= checked_now:
            raise ValueError("preview store item is invalid")
        with self._lock:
            expired = [key for key, value in self._items.items() if value.expires_at <= checked_now]
            for key in expired:
                del self._items[key]
            if len(self._items) >= self._max_items:
                raise OverflowError("preview store capacity is full")
            if item.preview_id in self._items:
                raise ValueError("preview ID collision")
            self._items[item.preview_id] = item

    def get(self, preview_id: str, *, now: datetime) -> StoredPreview | None:
        checked_now = _aware_utc(now)
        if type(preview_id) is not str or _PREVIEW_ID.fullmatch(preview_id) is None:
            return None
        with self._lock:
            item = self._items.get(preview_id)
            if item is None:
                return None
            if item.expires_at <= checked_now:
                del self._items[preview_id]
                return None
            return item


@dataclass(frozen=True)
class AdmissionCandidate:
    """Exact immutable identity passed across the atomic repository port."""

    preview_id: str
    request_bytes: bytes
    request_sha256: str
    execution_envelope_bytes: bytes
    execution_envelope_sha256: str
    idempotency_key: str
    authority_manifest_sha256: str
    source_identity_sha256: str
    preview_expires_at: datetime

    def __post_init__(self) -> None:
        if type(self.preview_expires_at) is not datetime:
            raise ValueError("preview expiry must be an exact datetime")
        try:
            expiry = _aware_utc(self.preview_expires_at)
        except ValueError as exc:
            raise ValueError("preview expiry must be an aware UTC instant") from exc
        object.__setattr__(self, "preview_expires_at", expiry)


@dataclass(frozen=True)
class AdmissionReplayIdentity:
    """Minimal immutable key used to recover a committed response after restart."""

    idempotency_key: str
    preview_id: str
    execution_envelope_sha256: str

    def __post_init__(self) -> None:
        if type(self.idempotency_key) is not str or _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key) is None:
            raise ValueError("idempotency key is outside the reviewed vocabulary")
        if type(self.preview_id) is not str:
            raise ValueError("preview ID must be exact text")
        if type(self.execution_envelope_sha256) is not str or _SHA256_TEXT.fullmatch(
            self.execution_envelope_sha256
        ) is None:
            raise ValueError("execution envelope digest must be lowercase SHA-256 text")


@dataclass(frozen=True)
class AdmissionLookupResult:
    disposition: Literal["not_found", "idempotent_replay", "idempotency_conflict"]
    run_id: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in {"not_found", "idempotent_replay", "idempotency_conflict"}:
            raise ValueError("unknown admission lookup disposition")
        if self.disposition == "idempotent_replay":
            if type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None:
                raise ValueError("idempotent lookup must return an exact run identity")
        elif self.run_id is not None:
            raise ValueError("non-replay lookup cannot claim a run identity")


@dataclass(frozen=True)
class AdmissionResult:
    disposition: Literal[
        "admitted", "idempotent_replay", "idempotency_conflict", "preview_consumed_conflict",
        "preview_expired",
    ]
    run_id: str | None = None


class AdmissionRepository(Protocol):
    """Narrow D4-owned replay/commit port; no worker work is part of either call.

    ``lookup`` is an authoritative, read-only probe keyed by the exact
    idempotency key, preview ID and envelope digest. ``admit`` must perform its
    key-ownership check, preview-consumption check, commit-clock expiry check
    and creation of one run identity in a single transaction/critical section.
    A committed exact replay is resolved before expiry is considered, so a
    lost response remains recoverable after the preview TTL. For a new commit,
    the repository compares its current UTC commit time with the exact
    ``preview_expires_at`` carried by the candidate; a caller-side check is not
    an atomic substitute. Neither method may launch work.
    """

    def lookup(self, identity: AdmissionReplayIdentity) -> AdmissionLookupResult: ...

    def admit(self, candidate: AdmissionCandidate) -> AdmissionResult: ...


class UnavailableAdmissionRepository:
    """Supported D1 backend until the reviewed durable D3/D4 store exists."""

    def lookup(self, identity: AdmissionReplayIdentity) -> AdmissionLookupResult:
        # This backend cannot truthfully assert either presence or absence of a
        # previously committed run. The service may continue active-preview
        # checks but must fail closed if replay recovery is needed.
        raise AdmissionRepositoryUnavailable

    def admit(self, candidate: AdmissionCandidate) -> AdmissionResult:
        raise AdmissionRepositoryUnavailable


class AdmissionRepositoryUnavailable(Exception):
    """The durable run repository is intentionally absent."""


def _source_identity(resources: ResourceResolver) -> SourceReleaseIdentity:
    identity = resources.identity
    if type(identity) is DevelopmentCheckoutIdentity:
        current = verify_development_checkout(identity.repository_root)
        if current.head_commit_sha != identity.head_commit_sha:
            raise _SourceIdentityChanged
        return SourceReleaseIdentity(
            kind="GIT_COMMIT",
            value=identity.head_commit_sha,
            schema_version=EXECUTION_ENVELOPE_V3_SCHEMA_VERSION,
        )
    if type(identity) is InstalledReleaseIdentity:
        try:
            current = verify_installed_release(identity.release_root, identity.manifest_sha256)
        except Exception:
            try:
                current_manifest_sha = hashlib.sha256(
                    (identity.release_root / MANIFEST_FILENAME).read_bytes()
                ).hexdigest()
            except OSError:
                raise
            if current_manifest_sha != identity.manifest_sha256:
                raise _SourceIdentityChanged from None
            raise
        if (
            current.manifest_sha256 != identity.manifest_sha256
            or current.release_id != identity.release_id
            or current.build_id != identity.build_id
            or current.platform_tag != identity.platform_tag
            or current.architecture_tag != identity.architecture_tag
            or current.manifest_policy_id != identity.manifest_policy_id
            or current.manifest_schema_version != identity.manifest_schema_version
            or current.trust_mode != identity.trust_mode
        ):
            raise _SourceIdentityChanged
        return SourceReleaseIdentity(
            kind="PINNED_RELEASE_MANIFEST",
            value=identity.manifest_sha256,
            schema_version=EXECUTION_ENVELOPE_V3_SCHEMA_VERSION,
            manifest_sha256=identity.manifest_sha256,
            release_id=identity.release_id,
            build_id=identity.build_id,
            platform_tag=identity.platform_tag,
            architecture_tag=identity.architecture_tag,
            manifest_policy_id=identity.manifest_policy_id,
            manifest_schema_version=identity.manifest_schema_version,
            trust_mode=identity.trust_mode,
        )
    raise ReleaseIdentityError("verified source identity is unavailable")


class _SourceIdentityChanged(Exception):
    pass


def _api_error(status_code: int, code: str) -> PreviewAdmissionError:
    definitions = {
        "INVALID_INTENT": (422, "Preview intent is invalid.", "never"),
        "TARGET_TOTAL_ODDS_NOT_SUPPORTED": (422, "target_total_odds is not supported.", "never"),
        "UNSUPPORTED_BOOKIE": (422, "Only the reviewed SportyBet adapter is supported.", "never"),
        "INVALID_DATE": (422, "Dates must be one through seven unique canonical dates.", "never"),
        "INVALID_IDEMPOTENCY_KEY": (422, "The idempotency key is invalid.", "never"),
        "PREVIEW_EXPIRED": (409, "Preview is unavailable or expired.", "after_refresh"),
        "PREVIEW_DIGEST_MISMATCH": (409, "The preview identity did not match.", "never"),
        "PREVIEW_STALE_AUTHORITY": (409, "Preview authority or source identity is stale.", "after_refresh"),
        "PREVIEW_BLOCKED": (409, "A requested operation is blocked by current authority.", "never"),
        "IDEMPOTENCY_CONFLICT": (409, "The idempotency key is bound to a different admitted identity.", "never"),
        "PREVIEW_ALREADY_CONSUMED_CONFLICT": (409, "The preview is already bound to another admission.", "never"),
        "PREVIEW_SOURCE_IDENTITY_UNAVAILABLE": (503, "The verified source identity is unavailable.", "after_delay"),
        "DURABLE_RUN_STORE_UNAVAILABLE": (503, "Durable run admission is not available in this application.", "after_delay"),
        "CURRENT_AUTHORITY_UNAVAILABLE": (503, "Current request authority could not be verified.", "after_delay"),
        "PREVIEW_STORE_UNAVAILABLE": (503, "The local preview store is temporarily unavailable.", "after_delay"),
    }
    expected_status, message, retry = definitions[code]
    if status_code != expected_status:
        raise ValueError("API error status mismatch")
    return PreviewAdmissionError(status_code, code, message, retry)


class AthenaPreviewAdmissionService:
    """Compose preview memory and a narrow admission port for one app instance."""

    def __init__(
        self,
        resources: ResourceResolver,
        *,
        preview_store: ProcessLocalPreviewStore | None = None,
        admission_repository: AdmissionRepository | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ):
        if type(resources) is not ResourceResolver or not callable(clock):
            raise ValueError("verified preview dependencies are required")
        if preview_store is not None and type(preview_store) is not ProcessLocalPreviewStore:
            raise ValueError("exact process-local preview store is required")
        if admission_repository is not None and (
            not callable(getattr(admission_repository, "lookup", None))
            or not callable(getattr(admission_repository, "admit", None))
        ):
            raise ValueError("admission repository lookup and atomic commit ports are required")
        self.resources = resources
        self.preview_store = ProcessLocalPreviewStore() if preview_store is None else preview_store
        self.admission_repository = (
            UnavailableAdmissionRepository() if admission_repository is None else admission_repository
        )
        self._clock = clock

    def preview_source_available(self) -> bool:
        """Informational source check used by capability UI, never admission authority."""
        try:
            _source_identity(self.resources)
            return True
        except Exception:
            return False

    def _now(self) -> datetime:
        try:
            return _aware_utc(self._clock())
        except Exception:
            raise _api_error(503, "CURRENT_AUTHORITY_UNAVAILABLE") from None

    def _current_source(self) -> SourceReleaseIdentity:
        try:
            return _source_identity(self.resources)
        except _SourceIdentityChanged:
            raise _api_error(409, "PREVIEW_STALE_AUTHORITY") from None
        except Exception:
            raise _api_error(503, "PREVIEW_SOURCE_IDENTITY_UNAVAILABLE") from None

    def preview(
        self,
        *,
        dates: list[str],
        target_legs: int,
        target_total_odds: None,
        bookie: str,
        profile: str,
        acquire_sources: bool,
        create_share_code: bool,
    ) -> dict[str, object]:
        if target_total_odds is not None:
            raise _api_error(422, "TARGET_TOTAL_ODDS_NOT_SUPPORTED")
        if (
            type(dates) is not list
            or not 1 <= len(dates) <= 7
            or any(type(value) is not str or _DATE_TEXT.fullmatch(value) is None for value in dates)
            or len(set(dates)) != len(dates)
        ):
            raise _api_error(422, "INVALID_DATE")
        if type(bookie) is not str or bookie != "sportybet":
            raise _api_error(422, "UNSUPPORTED_BOOKIE")
        if type(target_legs) is not int or not 1 <= target_legs <= 50:
            raise _api_error(422, "INVALID_INTENT")
        if type(profile) is not str or profile not in {"main", "shadow"}:
            raise _api_error(422, "INVALID_INTENT")
        if type(acquire_sources) is not bool or type(create_share_code) is not bool:
            raise _api_error(422, "INVALID_INTENT")
        try:
            for value in dates:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("non-canonical date")
        except ValueError:
            raise _api_error(422, "INVALID_DATE") from None

        observed_at = self._now()
        try:
            request = parse_explicit_request(
                days=",".join(dates),
                target_legs=target_legs,
                bookie=bookie,
                profile=profile,
                create_share_code=create_share_code,
                target_total_odds=None,
                now=observed_at,
            )
        except AthenaRunRequestParseError:
            raise _api_error(422, "INVALID_DATE") from None
        intent = RequestedOperationIntent(
            acquire_sources=acquire_sources,
            create_share_code=create_share_code,
            place_wager=False,
        )
        if request.create_share_code != intent.create_share_code or request.place_wager is not False:
            raise _api_error(422, "INVALID_INTENT")
        try:
            authority = AthenaRunService.authority_manifest_for(request)
            if type(authority) is not AuthorityManifest:
                raise ValueError("authority contract unavailable")
        except Exception:
            raise _api_error(503, "CURRENT_AUTHORITY_UNAVAILABLE") from None
        source_identity = self._current_source()
        request_bytes = canonical_json_bytes(request)
        try:
            envelope = ExecutionEnvelope.from_request_bytes(
                request_bytes=request_bytes,
                requested_operations=intent,
                authority_manifest=authority,
                source_identity=source_identity,
                date_resolution_policy_id=DATE_RESOLUTION_POLICY_ID,
                date_resolution_timezone_id=DATE_RESOLUTION_TIMEZONE_ID,
                clock_policy_id=PREVIEW_CLOCK_POLICY_ID,
                clock_observed_at=observed_at,
                issued_at=observed_at,
                expires_at=observed_at + PREVIEW_TTL,
                schema_version=EXECUTION_ENVELOPE_V3_SCHEMA_VERSION,
            )
            preview = evaluate_execution_envelope(envelope)
        except Exception:
            raise _api_error(503, "CURRENT_AUTHORITY_UNAVAILABLE") from None

        preview_id = secrets.token_urlsafe(32)
        stored = StoredPreview(
            preview_id=preview_id,
            request_bytes=request_bytes,
            envelope_bytes=envelope.canonical_bytes,
            preview_bytes=preview.canonical_bytes,
            expires_at=envelope.expires_at,
        )
        try:
            self.preview_store.put(stored, now=observed_at)
        except Exception:
            raise _api_error(503, "PREVIEW_STORE_UNAVAILABLE") from None
        return {
            "preview_id": preview_id,
            "request_sha256": envelope.request_sha256,
            "execution_envelope_sha256": envelope.canonical_sha256,
            "preview_sha256": preview.canonical_sha256,
            "dates": [item.isoformat() for item in request.dates],
            "target_legs": request.target_legs,
            "target_total_odds": None,
            "bookie": request.bookie,
            "profile": profile,
            "acquire_sources": intent.acquire_sources,
            "create_share_code": intent.create_share_code,
            "place_wager": False,
            "allowed_operations": list(preview.allowed_operations),
            "denied_operations": list(preview.denied_operations),
            "blockers": [item.to_dict() for item in preview.blockers],
            "expires_at": preview.expires_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "source_identity": preview.source_identity.to_dict(),
            "preview_scope": "LOCAL_READ_ONLY_NO_EXECUTION_AUTHORITY",
        }

    def admit(
        self,
        *,
        preview_id: str,
        execution_envelope_sha256: str,
        idempotency_key: str,
    ) -> AdmissionResult:
        if type(idempotency_key) is not str or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise _api_error(422, "INVALID_IDEMPOTENCY_KEY")
        if type(execution_envelope_sha256) is not str or _SHA256_TEXT.fullmatch(
            execution_envelope_sha256
        ) is None:
            raise _api_error(422, "INVALID_INTENT")
        if type(preview_id) is not str:
            raise _api_error(409, "PREVIEW_EXPIRED")

        replay_identity = AdmissionReplayIdentity(
            idempotency_key=idempotency_key,
            preview_id=preview_id,
            execution_envelope_sha256=execution_envelope_sha256,
        )
        probe_unavailable = False
        try:
            lookup = self.admission_repository.lookup(replay_identity)
        except AdmissionRepositoryUnavailable:
            # The installed D1 backend cannot assert that a prior commit is
            # absent. Keep checking a live process-local preview so a new
            # admission still reaches the typed DURABLE_RUN_STORE_UNAVAILABLE
            # result at the commit port.
            probe_unavailable = True
        except Exception:
            raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE") from None
        else:
            if type(lookup) is not AdmissionLookupResult:
                raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE")
            if lookup.disposition == "idempotency_conflict":
                raise _api_error(409, "IDEMPOTENCY_CONFLICT")
            if lookup.disposition == "idempotent_replay":
                if type(lookup.run_id) is not str or _RUN_ID.fullmatch(lookup.run_id) is None:
                    raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE")
                return AdmissionResult("idempotent_replay", lookup.run_id)

        now = self._now()
        stored = self.preview_store.get(preview_id, now=now)
        # Unknown, malformed and expired IDs intentionally share one response.
        if stored is None:
            if probe_unavailable:
                raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE")
            raise _api_error(409, "PREVIEW_EXPIRED")
        envelope_digest = hashlib.sha256(stored.envelope_bytes).hexdigest()
        if (
            type(execution_envelope_sha256) is not str
            or execution_envelope_sha256 != envelope_digest
        ):
            raise _api_error(409, "PREVIEW_DIGEST_MISMATCH")

        try:
            request = RunRequest.from_json_bytes(stored.request_bytes)
            envelope = ExecutionEnvelope.from_json_bytes(stored.envelope_bytes)
            preview = ExecutionPreview.from_json_bytes(stored.preview_bytes)
            if (
                stored.preview_id != preview_id
                or envelope.expires_at != stored.expires_at
                or canonical_json_bytes(request) != stored.request_bytes
                or envelope.request_bytes != stored.request_bytes
                or hashlib.sha256(stored.request_bytes).hexdigest() != envelope.request_sha256
                or envelope.canonical_sha256 != execution_envelope_sha256
                or preview.execution_envelope_sha256 != envelope.canonical_sha256
                or preview.request_sha256 != envelope.request_sha256
                or preview.source_identity != envelope.source_identity
                or preview.authority_manifest != envelope.authority_manifest
                or preview.canonical_bytes != stored.preview_bytes
            ):
                raise ValueError("stored preview identity drifted")
        except Exception:
            raise _api_error(409, "PREVIEW_DIGEST_MISMATCH") from None

        current_source = self._current_source()
        if current_source != envelope.source_identity:
            raise _api_error(409, "PREVIEW_STALE_AUTHORITY")
        try:
            current_authority = AthenaRunService.authority_manifest_for(request)
            if type(current_authority) is not AuthorityManifest:
                raise ValueError("authority contract unavailable")
        except Exception:
            raise _api_error(503, "CURRENT_AUTHORITY_UNAVAILABLE") from None
        if (
            current_authority != envelope.authority_manifest
            or hashlib.sha256(canonical_json_bytes(current_authority)).hexdigest()
            != envelope.authority_manifest_sha256
        ):
            raise _api_error(409, "PREVIEW_STALE_AUTHORITY")

        reevaluated = evaluate_execution_envelope(envelope)
        if reevaluated.canonical_bytes != stored.preview_bytes:
            raise _api_error(409, "PREVIEW_DIGEST_MISMATCH")
        if preview.blockers:
            raise _api_error(409, "PREVIEW_BLOCKED")
        candidate = AdmissionCandidate(
            preview_id=stored.preview_id,
            request_bytes=stored.request_bytes,
            request_sha256=envelope.request_sha256,
            execution_envelope_bytes=stored.envelope_bytes,
            execution_envelope_sha256=envelope.canonical_sha256,
            idempotency_key=idempotency_key,
            authority_manifest_sha256=envelope.authority_manifest_sha256,
            source_identity_sha256=hashlib.sha256(canonical_json_bytes(current_source)).hexdigest(),
            preview_expires_at=envelope.expires_at,
        )
        try:
            result = self.admission_repository.admit(candidate)
        except AdmissionRepositoryUnavailable:
            raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE") from None
        except Exception:
            # Internal repository exceptions are never returned to the caller.
            raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE") from None
        if type(result) is not AdmissionResult:
            raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE")
        if result.disposition == "idempotency_conflict":
            raise _api_error(409, "IDEMPOTENCY_CONFLICT")
        if result.disposition == "preview_consumed_conflict":
            raise _api_error(409, "PREVIEW_ALREADY_CONSUMED_CONFLICT")
        if result.disposition == "preview_expired":
            raise _api_error(409, "PREVIEW_EXPIRED")
        if (
            result.disposition not in {"admitted", "idempotent_replay"}
            or type(result.run_id) is not str
            or _RUN_ID.fullmatch(result.run_id) is None
        ):
            raise _api_error(503, "DURABLE_RUN_STORE_UNAVAILABLE")
        return result


__all__ = [
    "AdmissionCandidate",
    "AdmissionLookupResult",
    "AdmissionRepository",
    "AdmissionRepositoryUnavailable",
    "AdmissionReplayIdentity",
    "AdmissionResult",
    "AthenaPreviewAdmissionService",
    "MAX_PREVIEWS_PER_APP",
    "PREVIEW_TTL",
    "PreviewAdmissionError",
    "ProcessLocalPreviewStore",
    "StoredPreview",
    "UnavailableAdmissionRepository",
]
