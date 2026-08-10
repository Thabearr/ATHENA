"""Reviewed one-shot diagnostic contract for FotMob match-details responses.

Only transport metadata and a bounded raw response sample may cross this
boundary. Football semantics remain unreviewed and unauthorized.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any, Tuple

from domain.fixture_catalog import serialize_utc
from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    DATASET_NAME as VERIFIED_BOOTSTRAP_DATASET_NAME,
    ReviewedFixtureIntelligenceBootstrapArtifactError,
    VerifiedReviewedFixtureIntelligenceBootstrapArtifact,
    canonical_verified_bootstrap_artifact_receipt_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-probe-v1"
ALLOWED_HOST = "www.fotmob.com"
HTTPS_PORT = 443
ALLOWED_PATH = "/api/matchDetails"
MAX_SAMPLE_BYTES = 4096
USER_AGENT = "ATHENA/1.0"
MEDIA_EXPECTATION = "application/json"
REQUEST_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("Accept", MEDIA_EXPECTATION),
    ("User-Agent", USER_AGENT),
)

_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_capture_authorized",
        "artifact_write_authorized",
        "response_body_parsing_authorized",
        "source_qualification_authorized",
        "football_semantics_authorized",
        "intelligence_fact_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsProbeError(ValueError):
    """Raised when the reviewed match-details diagnostic boundary fails closed."""


class ProbeTransportOutcome(str, enum.Enum):
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsProbeError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _strict_utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsProbeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise FotMobReviewedMatchDetailsProbeError(f"{label} must be timezone-aware")
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsProbeError(
            f"{label} must already be normalized to datetime.timezone.utc"
        )
    return value


def _optional_header(value: Any, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise FotMobReviewedMatchDetailsProbeError(
            f"{label} must be an exact string or None"
        )
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise FotMobReviewedMatchDetailsProbeError(
            f"{label} is empty or exceeds {maximum} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise FotMobReviewedMatchDetailsProbeError(
            f"{label} contains control characters"
        )
    return normalized


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsProbeError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsProbeError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def request_headers() -> Tuple[Tuple[str, str], ...]:
    return REQUEST_HEADERS


def source_match_id_from_fixture_identifier(value: Any) -> str:
    if type(value) is not str or value != value.strip():
        raise FotMobReviewedMatchDetailsProbeError(
            "fixture_identifier must be an exact unpadded string"
        )
    match = _FIXTURE_RE.fullmatch(value)
    if match is None:
        raise FotMobReviewedMatchDetailsProbeError(
            "fixture_identifier must be canonical FOTMOB:<positive decimal match id>"
        )
    return match.group(1)


def request_target(source_match_id: Any) -> str:
    if type(source_match_id) is not str or not source_match_id:
        raise FotMobReviewedMatchDetailsProbeError(
            "source_match_id must be an exact positive decimal string"
        )
    if (
        not source_match_id.isascii()
        or not source_match_id.isdigit()
        or source_match_id.startswith("0")
    ):
        raise FotMobReviewedMatchDetailsProbeError(
            "source_match_id must be canonical positive ASCII decimal digits"
        )
    return f"{ALLOWED_PATH}?matchId={source_match_id}"


def _revalidate_verified_bootstrap_artifact(
    value: Any,
    receipt_bytes: Any,
) -> tuple[VerifiedReviewedFixtureIntelligenceBootstrapArtifact, str]:
    if type(value) is not VerifiedReviewedFixtureIntelligenceBootstrapArtifact:
        raise FotMobReviewedMatchDetailsProbeError(
            "verified_bootstrap_artifact must be exact "
            "VerifiedReviewedFixtureIntelligenceBootstrapArtifact"
        )
    if type(receipt_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsProbeError(
            "verification_receipt_bytes must be exact immutable bytes"
        )
    try:
        supplied = canonical_verified_bootstrap_artifact_receipt_bytes(value)
        rebuilt = dataclasses.replace(value)
        rebuilt_bytes = canonical_verified_bootstrap_artifact_receipt_bytes(rebuilt)
    except (
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        TypeError,
        ValueError,
    ) as exc:
        raise FotMobReviewedMatchDetailsProbeError(
            "PR #48 verified bootstrap artifact failed current exact revalidation"
        ) from exc
    if supplied != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsProbeError(
            "supplied PR #48 object differs from its exact semantic rebuild"
        )
    if receipt_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsProbeError(
            "verification_receipt_bytes are not the exact canonical PR #48 receipt"
        )
    if rebuilt.dataset_name != VERIFIED_BOOTSTRAP_DATASET_NAME:
        raise FotMobReviewedMatchDetailsProbeError(
            "verified bootstrap artifact dataset identity mismatch"
        )
    return rebuilt, hashlib.sha256(receipt_bytes).hexdigest()


@dataclasses.dataclass(frozen=True)
class FotMobMatchDetailsProbePlan:
    """Detached request plan for one exact prospective reviewed fixture."""

    bootstrap_verification_receipt_sha256: str
    bootstrap_sha256: str
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    request_started_at: datetime.datetime
    host: str
    request_target: str
    request_headers: Tuple[Tuple[str, str], ...]
    media_expectation: str
    x_mas_included: bool
    cookie_included: bool
    browser_impersonation: bool

    def __post_init__(self) -> None:
        _strict_sha256(
            self.bootstrap_verification_receipt_sha256,
            "bootstrap_verification_receipt_sha256",
        )
        _strict_sha256(self.bootstrap_sha256, "bootstrap_sha256")
        source_match_id = source_match_id_from_fixture_identifier(
            self.fixture_identifier
        )
        if self.source_match_id != source_match_id:
            raise FotMobReviewedMatchDetailsProbeError(
                "source_match_id does not match fixture_identifier"
            )
        kickoff = _strict_utc(self.kickoff, "kickoff")
        started = _strict_utc(self.request_started_at, "request_started_at")
        if started >= kickoff:
            raise FotMobReviewedMatchDetailsProbeError(
                "request_started_at must be strictly before fixture kickoff"
            )
        if self.host != ALLOWED_HOST:
            raise FotMobReviewedMatchDetailsProbeError(
                "host must be exactly www.fotmob.com"
            )
        if self.request_target != request_target(source_match_id):
            raise FotMobReviewedMatchDetailsProbeError(
                "request_target does not match the reviewed match-details route"
            )
        if type(self.request_headers) is not tuple or self.request_headers != REQUEST_HEADERS:
            raise FotMobReviewedMatchDetailsProbeError(
                "request_headers do not match the transparent ATHENA profile"
            )
        if self.media_expectation != MEDIA_EXPECTATION:
            raise FotMobReviewedMatchDetailsProbeError(
                "media_expectation must be application/json"
            )
        for label, value in (
            ("x_mas_included", self.x_mas_included),
            ("cookie_included", self.cookie_included),
            ("browser_impersonation", self.browser_impersonation),
        ):
            if type(value) is not bool or value is not False:
                raise FotMobReviewedMatchDetailsProbeError(
                    f"{label} must be exact bool False"
                )
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "request_started_at", started)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bootstrap_verification_receipt_sha256": (
                self.bootstrap_verification_receipt_sha256
            ),
            "bootstrap_sha256": self.bootstrap_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": serialize_utc(self.kickoff),
            "request_started_at": serialize_utc(self.request_started_at),
            "host": self.host,
            "request_target": self.request_target,
            "request_headers": [list(item) for item in self.request_headers],
            "media_expectation": self.media_expectation,
            "x_mas_included": self.x_mas_included,
            "cookie_included": self.cookie_included,
            "browser_impersonation": self.browser_impersonation,
        }


def build_match_details_probe_plan(
    verified_bootstrap_artifact: Any,
    verification_receipt_bytes: Any,
    *,
    fixture_identifier: Any,
    request_started_at: Any,
) -> FotMobMatchDetailsProbePlan:
    """Build one request plan from an exact, currently valid PR #48 receipt."""

    rebuilt, receipt_sha = _revalidate_verified_bootstrap_artifact(
        verified_bootstrap_artifact,
        verification_receipt_bytes,
    )
    source_match_id = source_match_id_from_fixture_identifier(fixture_identifier)
    matches = tuple(
        item
        for item in rebuilt.fixtures
        if item.fixture_identifier == fixture_identifier
    )
    if len(matches) != 1:
        raise FotMobReviewedMatchDetailsProbeError(
            "fixture_identifier is not an exact fixture in the PR #48 receipt"
        )
    fixture = matches[0]
    started = _strict_utc(request_started_at, "request_started_at")
    if started < rebuilt.verified_at:
        raise FotMobReviewedMatchDetailsProbeError(
            "request_started_at must not predate PR #48 verification"
        )
    if started >= fixture.kickoff:
        raise FotMobReviewedMatchDetailsProbeError(
            "request_started_at must be strictly before fixture kickoff"
        )
    return FotMobMatchDetailsProbePlan(
        bootstrap_verification_receipt_sha256=receipt_sha,
        bootstrap_sha256=rebuilt.bootstrap_sha256,
        fixture_identifier=fixture.fixture_identifier,
        source_match_id=source_match_id,
        kickoff=fixture.kickoff,
        request_started_at=started,
        host=ALLOWED_HOST,
        request_target=request_target(source_match_id),
        request_headers=REQUEST_HEADERS,
        media_expectation=MEDIA_EXPECTATION,
        x_mas_included=False,
        cookie_included=False,
        browser_impersonation=False,
    )


@dataclasses.dataclass(frozen=True)
class FotMobReviewedMatchDetailsProbeReceipt:
    """Deterministic metadata/sample receipt for one diagnostic response."""

    schema_version: int
    dataset_name: str
    plan: FotMobMatchDetailsProbePlan
    transport_outcome: ProbeTransportOutcome
    status_code: int | None
    content_type: str | None
    content_length: int | None
    location: str | None
    observed_at: datetime.datetime
    sample_size: int
    sample_sha256: str | None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsProbeError(
                "schema_version must be exact integer 1"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsProbeError("dataset_name mismatch")
        if type(self.plan) is not FotMobMatchDetailsProbePlan:
            raise FotMobReviewedMatchDetailsProbeError(
                "plan must be exact FotMobMatchDetailsProbePlan"
            )
        try:
            plan = dataclasses.replace(self.plan)
        except (FotMobReviewedMatchDetailsProbeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsProbeError(
                "probe plan failed exact revalidation"
            ) from exc
        if not isinstance(self.transport_outcome, ProbeTransportOutcome):
            raise FotMobReviewedMatchDetailsProbeError(
                "transport_outcome must be ProbeTransportOutcome"
            )
        content_type = _optional_header(self.content_type, "content_type", 512)
        location = _optional_header(self.location, "location", 2048)
        if self.content_length is not None and (
            type(self.content_length) is not int or self.content_length < 0
        ):
            raise FotMobReviewedMatchDetailsProbeError(
                "content_length must be an exact non-negative integer or None"
            )
        observed = _strict_utc(self.observed_at, "observed_at")
        if observed < plan.request_started_at:
            raise FotMobReviewedMatchDetailsProbeError(
                "observed_at must not predate request_started_at"
            )
        if observed >= plan.kickoff:
            raise FotMobReviewedMatchDetailsProbeError(
                "observed_at must be strictly before fixture kickoff"
            )
        if type(self.sample_size) is not int or not 0 <= self.sample_size <= MAX_SAMPLE_BYTES:
            raise FotMobReviewedMatchDetailsProbeError(
                "sample_size must be between 0 and 4096"
            )
        if self.transport_outcome is ProbeTransportOutcome.RESPONSE_RECEIVED:
            if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
                raise FotMobReviewedMatchDetailsProbeError(
                    "response status_code must be an exact integer from 100 to 599"
                )
            if (
                type(self.sample_sha256) is not str
                or _SHA256_RE.fullmatch(self.sample_sha256) is None
            ):
                raise FotMobReviewedMatchDetailsProbeError(
                    "response sample_sha256 must be lowercase SHA-256"
                )
        else:
            if any(
                item is not None
                for item in (
                    self.status_code,
                    content_type,
                    self.content_length,
                    location,
                    self.sample_sha256,
                )
            ) or self.sample_size != 0:
                raise FotMobReviewedMatchDetailsProbeError(
                    "transport error receipt must not contain response metadata"
                )
        object.__setattr__(self, "plan", plan)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "location", location)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "plan": self.plan.to_dict(),
            "transport_outcome": self.transport_outcome.value,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "location": self.location,
            "observed_at": serialize_utc(self.observed_at),
            "sample_size": self.sample_size,
            "sample_sha256": self.sample_sha256,
            "safety": dict(self.safety),
        }


def build_response_receipt(
    *,
    plan: FotMobMatchDetailsProbePlan,
    status_code: Any,
    content_type: Any,
    content_length: Any,
    location: Any,
    observed_at: Any,
    sample: Any,
) -> FotMobReviewedMatchDetailsProbeReceipt:
    if type(sample) is not bytes or len(sample) > MAX_SAMPLE_BYTES:
        raise FotMobReviewedMatchDetailsProbeError(
            "sample must be exact bytes of at most 4096 bytes"
        )
    return FotMobReviewedMatchDetailsProbeReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        plan=plan,
        transport_outcome=ProbeTransportOutcome.RESPONSE_RECEIVED,
        status_code=status_code,
        content_type=content_type,
        content_length=content_length,
        location=location,
        observed_at=observed_at,
        sample_size=len(sample),
        sample_sha256=hashlib.sha256(sample).hexdigest(),
        safety=_default_safety(),
    )


def build_transport_error_receipt(
    *,
    plan: FotMobMatchDetailsProbePlan,
    observed_at: Any,
) -> FotMobReviewedMatchDetailsProbeReceipt:
    return FotMobReviewedMatchDetailsProbeReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        plan=plan,
        transport_outcome=ProbeTransportOutcome.TRANSPORT_ERROR,
        status_code=None,
        content_type=None,
        content_length=None,
        location=None,
        observed_at=observed_at,
        sample_size=0,
        sample_sha256=None,
        safety=_default_safety(),
    )


def canonical_match_details_probe_receipt_bytes(value: Any) -> bytes:
    if type(value) is not FotMobReviewedMatchDetailsProbeReceipt:
        raise FotMobReviewedMatchDetailsProbeError(
            "value must be exact FotMobReviewedMatchDetailsProbeReceipt"
        )
    try:
        return (
            json.dumps(
                value.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsProbeError(
            "match-details probe receipt serialization failed"
        ) from exc


def sha256_match_details_probe_receipt(value: Any) -> str:
    return hashlib.sha256(canonical_match_details_probe_receipt_bytes(value)).hexdigest()


__all__ = [
    "ALLOWED_HOST",
    "ALLOWED_PATH",
    "DATASET_NAME",
    "FotMobMatchDetailsProbePlan",
    "FotMobReviewedMatchDetailsProbeError",
    "FotMobReviewedMatchDetailsProbeReceipt",
    "HTTPS_PORT",
    "MAX_SAMPLE_BYTES",
    "MEDIA_EXPECTATION",
    "ProbeTransportOutcome",
    "REQUEST_HEADERS",
    "SCHEMA_VERSION",
    "USER_AGENT",
    "build_match_details_probe_plan",
    "build_response_receipt",
    "build_transport_error_receipt",
    "canonical_match_details_probe_receipt_bytes",
    "request_headers",
    "request_target",
    "sha256_match_details_probe_receipt",
    "source_match_id_from_fixture_identifier",
]
