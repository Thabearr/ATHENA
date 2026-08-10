"""Extract exact reviewed FotMob match-details scalars as UNVERIFIED candidates.

PR #55 consumes the exact PR #54 human field-semantics review and the same raw
bytes. It extracts only explicitly APPROVED, non-wildcard scalar paths. The
result is not a FixtureIntelligenceFact and cannot be promoted to SUPPORTED by
this boundary.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_intelligence import (
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
)
from domain.fotmob_reviewed_match_details_field_review import (
    MAX_APPROVED_POINTER_LENGTH,
    FieldReviewDisposition,
    FotMobReviewedMatchDetailsFieldReviewError,
    ReviewedMatchDetailsFieldSemantics,
    build_reviewed_match_details_field_semantics,
    canonical_reviewed_match_details_field_semantics_bytes,
)
from domain.fotmob_reviewed_match_details_persisted_evidence import (
    VerifiedPersistedFotMobMatchDetailsEvidence,
)
from domain.fotmob_reviewed_match_details_structure import (
    FotMobReviewedMatchDetailsStructureAssessment,
    JsonValueKind,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-unverified-candidates-v1"
SOURCE_PROVIDER = "fotmob_match_details_reviewed"
MAX_RAW_BYTES = 8 * 1024 * 1024

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_SCALAR_KINDS = frozenset(
    {
        JsonValueKind.BOOLEAN,
        JsonValueKind.INTEGER,
        JsonValueKind.NUMBER,
        JsonValueKind.STRING,
    }
)
_SAFETY_KEYS = frozenset(
    {
        "source_qualification_authorized",
        "supported_status_authorized",
        "intelligence_fact_promotion_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsUnverifiedCandidateError(ValueError):
    """Raised when reviewed scalar extraction cannot be proven exactly."""


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            f"{label} must use exact datetime.timezone.utc"
        )
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError("safety keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                f"safety[{key!r}] must be exact bool False"
            )
    return _default_safety()


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "raw JSON object keys must be strings"
            )
        if key in result:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                f"duplicate raw JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
        f"invalid raw JSON constant: {value}"
    )


def _parse_raw_object(raw_bytes: Any) -> dict[str, Any]:
    if type(raw_bytes) is not bytes or not raw_bytes or len(raw_bytes) > MAX_RAW_BYTES:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "raw_bytes must be exact non-empty immutable bytes within 8 MiB"
        )
    try:
        value = json.loads(
            raw_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FotMobReviewedMatchDetailsUnverifiedCandidateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "raw response is not strict UTF-8 JSON"
        ) from exc
    if type(value) is not dict:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "raw response root must be a JSON object"
        )

    def require_finite(item: Any) -> None:
        if type(item) is float and not math.isfinite(item):
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "raw response contains a non-finite number"
            )
        if type(item) is dict:
            for child in item.values():
                require_finite(child)
        elif type(item) is list:
            for child in item:
                require_finite(child)

    require_finite(value)
    return value


def _decode_pointer_token(token: str) -> str:
    """Reverse PR #53's RFC6901 escapes plus ATHENA's `~2` literal-star escape."""

    output: list[str] = []
    index = 0
    mapping = {"0": "~", "1": "/", "2": "*"}
    while index < len(token):
        if token[index] != "~":
            output.append(token[index])
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in mapping:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "invalid reviewed JSON pointer escape"
            )
        output.append(mapping[token[index + 1]])
        index += 2
    return "".join(output)


def _extract_object_path(root: dict[str, Any], pointer: Any) -> Any:
    if type(pointer) is not str or not pointer.startswith("/"):
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "approved pointer must be a non-root JSON pointer"
        )
    if len(pointer) > MAX_APPROVED_POINTER_LENGTH:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "approved pointer exceeds PR #54 extraction-safe length"
        )
    current: Any = root
    for encoded in pointer[1:].split("/"):
        if encoded == "*":
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "array wildcard cannot be extracted as one scalar value"
            )
        token = _decode_pointer_token(encoded)
        if type(current) is not dict:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "reviewed pointer traversal crossed a non-object container"
            )
        if token not in current:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "reviewed pointer is absent from exact raw response"
            )
        current = current[token]
    return current


def _json_kind(value: Any) -> JsonValueKind:
    if value is None:
        return JsonValueKind.NULL
    if type(value) is bool:
        return JsonValueKind.BOOLEAN
    if type(value) is int:
        return JsonValueKind.INTEGER
    if type(value) is float:
        if not math.isfinite(value):
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "extracted number is non-finite"
            )
        return JsonValueKind.NUMBER
    if type(value) is str:
        return JsonValueKind.STRING
    if type(value) is list:
        return JsonValueKind.ARRAY
    if type(value) is dict:
        return JsonValueKind.OBJECT
    raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
        "extracted value has unsupported JSON type"
    )


def _canonical_scalar(value: Any) -> str | int | float | bool:
    if _json_kind(value) not in _SCALAR_KINDS:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "reviewed extraction must produce a non-null scalar"
        )
    return value


@dataclasses.dataclass(frozen=True)
class UnverifiedMatchDetailsCandidate:
    category: IntelligenceCategory
    field: str
    status: IntelligenceFactStatus
    value: str | int | float | bool
    json_pointer: str
    json_kind: JsonValueKind
    source_provider: str
    source_role: SourceRole
    source_reference: str
    observed_at: datetime.datetime
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "category must be IntelligenceCategory"
            )
        field = _text(self.field, "field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "field must match the exact PR #54 Fixture Intelligence field contract"
            )
        if self.status is not IntelligenceFactStatus.UNVERIFIED:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidate status must remain exact UNVERIFIED"
            )
        value = _canonical_scalar(self.value)
        if not isinstance(self.json_kind, JsonValueKind) or _json_kind(value) is not self.json_kind:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "json_kind must exactly match candidate value"
            )
        pointer = _text(self.json_pointer, "json_pointer", MAX_APPROVED_POINTER_LENGTH)
        if not pointer.startswith("/") or "/*" in pointer or pointer.endswith("/*"):
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidate json_pointer must remain an approved non-wildcard PR #54 path"
            )
        if self.source_provider != SOURCE_PROVIDER:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError("source_provider mismatch")
        if self.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "source_role must remain PRIMARY_FOOTBALL_CONTEXT"
            )
        source_reference = _text(self.source_reference, "source_reference", 1024)
        observed = _utc(self.observed_at, "observed_at")
        evidence_sha = _sha(self.evidence_sha256, "evidence_sha256")
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "json_pointer", pointer)
        object.__setattr__(self, "source_reference", source_reference)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "evidence_sha256", evidence_sha)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "field": self.field,
            "status": self.status.value,
            "value": self.value,
            "json_pointer": self.json_pointer,
            "json_kind": self.json_kind.value,
            "source_provider": self.source_provider,
            "source_role": self.source_role.value,
            "source_reference": self.source_reference,
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "evidence_sha256": self.evidence_sha256,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsUnverifiedCandidateBundle:
    schema_version: int
    dataset_name: str
    review_sha256: str
    structure_sha256: str
    evidence_receipt_sha256: str
    manifest_sha256: str
    raw_sha256: str
    fixture_identifier: str
    source_match_id: str
    observed_at: datetime.datetime
    kickoff: datetime.datetime
    candidates: tuple[UnverifiedMatchDetailsCandidate, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError("dataset_name mismatch")
        for label in (
            "review_sha256",
            "structure_sha256",
            "evidence_receipt_sha256",
            "manifest_sha256",
            "raw_sha256",
        ):
            _sha(getattr(self, label), label)
        fixture_identifier = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        observed = _utc(self.observed_at, "observed_at")
        kickoff = _utc(self.kickoff, "kickoff")
        if observed >= kickoff:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidate evidence must remain strictly pre-kickoff"
            )
        if type(self.candidates) is not tuple or not self.candidates:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidates must be a non-empty immutable tuple"
            )
        if any(type(item) is not UnverifiedMatchDetailsCandidate for item in self.candidates):
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidates must contain exact UnverifiedMatchDetailsCandidate values"
            )

        # Reconstruct every nested candidate. This is deliberately stronger than
        # a type check: object.__setattr__ can mutate a frozen dataclass after
        # construction, and such a forged object must never survive artifact
        # canonicalization or downstream reuse.
        rebuilt_candidates = tuple(dataclasses.replace(item) for item in self.candidates)
        expected = tuple(
            sorted(
                rebuilt_candidates,
                key=lambda item: (item.category.value, item.field, item.json_pointer),
            )
        )
        if rebuilt_candidates != expected:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidates must use deterministic semantic ordering"
            )
        targets = [(item.category.value, item.field) for item in rebuilt_candidates]
        pointers = [item.json_pointer for item in rebuilt_candidates]
        if len(set(targets)) != len(targets):
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidate semantic targets must be unique"
            )
        if len(set(pointers)) != len(pointers):
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "candidate json_pointer values must be unique"
            )
        for item in rebuilt_candidates:
            if item.observed_at != observed or item.evidence_sha256 != self.raw_sha256:
                raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                    "candidate evidence lineage must match bundle exactly"
                )
            expected_reference = (
                f"FOTMOB_MATCH_DETAILS:{source_match_id}:{item.json_pointer}"
            )
            if item.source_reference != expected_reference:
                raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                    "candidate source_reference must match source fixture and reviewed path exactly"
                )
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "candidates", rebuilt_candidates)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime.datetime) -> str:
            return value.isoformat().replace("+00:00", "Z")

        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "review_sha256": self.review_sha256,
            "structure_sha256": self.structure_sha256,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "raw_sha256": self.raw_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "observed_at": iso(self.observed_at),
            "kickoff": iso(self.kickoff),
            "candidates": [item.to_dict() for item in self.candidates],
            "safety": dict(self.safety),
        }


def _revalidate_review(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
) -> tuple[ReviewedMatchDetailsFieldSemantics, bytes]:
    if type(evidence) is not VerifiedPersistedFotMobMatchDetailsEvidence:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "evidence must be exact PR #52 verified evidence"
        )
    if type(assessment) is not FotMobReviewedMatchDetailsStructureAssessment:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "assessment must be exact PR #53 structural assessment"
        )
    if type(review) is not ReviewedMatchDetailsFieldSemantics:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "review must be exact PR #54 field semantics review"
        )
    if type(review_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "review_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_field_semantics_bytes(review)
        rebuilt = build_reviewed_match_details_field_semantics(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            decisions=review.decisions,
            reviewed_at=review.reviewed_at,
            reviewer_reference=review.reviewer_reference,
        )
        rebuilt_bytes = canonical_reviewed_match_details_field_semantics_bytes(rebuilt)
    except (FotMobReviewedMatchDetailsFieldReviewError, TypeError, ValueError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "PR #54 review failed exact evidence revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "supplied PR #54 review differs from exact semantic rebuild"
        )
    if review_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "review_bytes are not exact canonical PR #54 bytes"
        )
    return rebuilt, rebuilt_bytes


def build_reviewed_match_details_unverified_candidates(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
) -> ReviewedMatchDetailsUnverifiedCandidateBundle:
    """Extract only exact PR #54-approved scalars, retaining UNVERIFIED status."""

    rebuilt_review, exact_review_bytes = _revalidate_review(
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
    )
    root = _parse_raw_object(raw_bytes)
    if hashlib.sha256(raw_bytes).hexdigest() != rebuilt_review.raw_sha256:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "exact raw bytes do not match reviewed raw evidence SHA-256"
        )
    approved = tuple(
        item
        for item in rebuilt_review.decisions
        if item.disposition is FieldReviewDisposition.APPROVED
    )
    if not approved:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "PR #55 requires at least one explicitly APPROVED scalar decision"
        )

    candidates: list[UnverifiedMatchDetailsCandidate] = []
    for decision in approved:
        if decision.category is None or decision.field is None:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "APPROVED PR #54 decision lost its exact semantic target"
            )
        value = _extract_object_path(root, decision.json_pointer)
        kind = _json_kind(value)
        if kind is not decision.expected_kind:
            raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
                "exact raw value kind differs from PR #54 approved kind"
            )
        scalar = _canonical_scalar(value)
        candidates.append(
            UnverifiedMatchDetailsCandidate(
                category=decision.category,
                field=decision.field,
                status=IntelligenceFactStatus.UNVERIFIED,
                value=scalar,
                json_pointer=decision.json_pointer,
                json_kind=kind,
                source_provider=SOURCE_PROVIDER,
                source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
                source_reference=(
                    f"FOTMOB_MATCH_DETAILS:{rebuilt_review.source_match_id}:{decision.json_pointer}"
                ),
                observed_at=evidence.observed_at,
                evidence_sha256=rebuilt_review.raw_sha256,
            )
        )

    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (item.category.value, item.field, item.json_pointer),
        )
    )
    return ReviewedMatchDetailsUnverifiedCandidateBundle(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        review_sha256=hashlib.sha256(exact_review_bytes).hexdigest(),
        structure_sha256=rebuilt_review.structure_sha256,
        evidence_receipt_sha256=rebuilt_review.evidence_receipt_sha256,
        manifest_sha256=rebuilt_review.manifest_sha256,
        raw_sha256=rebuilt_review.raw_sha256,
        fixture_identifier=rebuilt_review.fixture_identifier,
        source_match_id=rebuilt_review.source_match_id,
        observed_at=evidence.observed_at,
        kickoff=evidence.kickoff,
        candidates=ordered,
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_unverified_candidate_bundle_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsUnverifiedCandidateBundle:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "value must be exact ReviewedMatchDetailsUnverifiedCandidateBundle"
        )
    try:
        rebuilt = dataclasses.replace(value)
        return (
            json.dumps(
                rebuilt.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except FotMobReviewedMatchDetailsUnverifiedCandidateError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsUnverifiedCandidateError(
            "candidate bundle canonicalization failed"
        ) from exc


def sha256_reviewed_match_details_unverified_candidate_bundle(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_unverified_candidate_bundle_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "MAX_RAW_BYTES",
    "SCHEMA_VERSION",
    "SOURCE_PROVIDER",
    "FotMobReviewedMatchDetailsUnverifiedCandidateError",
    "ReviewedMatchDetailsUnverifiedCandidateBundle",
    "UnverifiedMatchDetailsCandidate",
    "build_reviewed_match_details_unverified_candidates",
    "canonical_reviewed_match_details_unverified_candidate_bundle_bytes",
    "sha256_reviewed_match_details_unverified_candidate_bundle",
]
