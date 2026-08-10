"""Review-gated UNVERIFIED Fixture Intelligence candidates from match details.

This boundary replays the exact PR #52→#54 chain and resolves only explicitly
approved, non-wildcard scalar paths. It never emits SUPPORTED facts and does not
qualify the FotMob source for semantic use.
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
from pathlib import PurePosixPath
from typing import Any

from domain.fixture_intelligence import (
    FixtureIntelligenceError,
    FixtureIntelligenceFact,
    IntelligenceFactStatus,
    SourceRole,
)
from domain.fotmob_reviewed_match_details_field_review import (
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
DATASET_NAME = "athena-fotmob-reviewed-match-details-fact-candidates-v1"
SOURCE_PROVIDER = "fotmob_match_details_reviewed"
CAPTURE_ROOT = PurePosixPath(
    ".cache/athena-research/fotmob-reviewed-match-details-captures"
)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)

_SAFETY_KEYS = frozenset(
    {
        "supported_fact_authorized",
        "source_qualification_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsFactCandidateError(ValueError):
    """Raised when reviewed match-details fact candidates fail closed."""


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "fact candidate serialization failed"
        ) from exc


def _pairs(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "response JSON object keys must be strings"
            )
        if key in result:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                f"duplicate response JSON key: {key}"
            )
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise FotMobReviewedMatchDetailsFactCandidateError(
        f"invalid response JSON constant: {value}"
    )


def _float(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "invalid response JSON number"
        ) from exc
    if not math.isfinite(parsed):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "response JSON number must be finite"
        )
    return parsed


def _strict_json_object(raw_bytes: Any) -> dict[str, Any]:
    if type(raw_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "raw_bytes must be exact immutable bytes"
        )
    try:
        payload = json.loads(
            raw_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=_float,
        )
    except FotMobReviewedMatchDetailsFactCandidateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "response body is not strict finite UTF-8 JSON"
        ) from exc
    if type(payload) is not dict:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "match-details response root must be a JSON object"
        )
    return payload


def _strict_utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _strict_sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _decode_token(token: str) -> str:
    if token == "*":
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "array wildcard segments are forbidden for scalar extraction"
        )
    result: list[str] = []
    index = 0
    while index < len(token):
        char = token[index]
        if char != "~":
            result.append(char)
            index += 1
            continue
        if index + 1 >= len(token):
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "malformed structural pointer escape"
            )
        code = token[index + 1]
        replacement = {"0": "~", "1": "/", "2": "*"}.get(code)
        if replacement is None:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "malformed structural pointer escape"
            )
        result.append(replacement)
        index += 2
    return "".join(result)


def _validate_scalar(value: Any, label: str) -> None:
    if type(value) not in (str, int, float, bool):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            f"{label} must be an exact non-null JSON scalar"
        )
    if type(value) is float and not math.isfinite(value):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            f"{label} numeric scalar must be finite"
        )


def _resolve_scalar(payload: dict[str, Any], pointer: str) -> Any:
    if type(pointer) is not str or not pointer.startswith("/"):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "approved json_pointer must be a non-root absolute structural path"
        )
    current: Any = payload
    for encoded in pointer[1:].split("/"):
        key = _decode_token(encoded)
        if type(current) is not dict:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "approved path traversed a non-object value"
            )
        if key not in current:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "approved path is missing from exact response bytes"
            )
        current = current[key]
    _validate_scalar(current, "resolved value")
    return current


def _actual_kind(value: Any) -> JsonValueKind:
    if type(value) is bool:
        return JsonValueKind.BOOLEAN
    if type(value) is int:
        return JsonValueKind.INTEGER
    if type(value) is float:
        return JsonValueKind.NUMBER
    if type(value) is str:
        return JsonValueKind.STRING
    raise FotMobReviewedMatchDetailsFactCandidateError(
        "resolved value is not a reviewed scalar kind"
    )


def _capture_identifier_parts(
    source_match_id: str,
    observed_at: datetime.datetime,
    raw_sha256: str,
) -> str:
    timestamp = observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{source_match_id}--{timestamp}--{raw_sha256}"


def _capture_identifier(evidence: VerifiedPersistedFotMobMatchDetailsEvidence) -> str:
    return _capture_identifier_parts(
        evidence.source_match_id,
        evidence.observed_at,
        evidence.raw_sha256,
    )


def _evidence_path_parts(
    source_match_id: str,
    observed_at: datetime.datetime,
    raw_sha256: str,
) -> str:
    return str(
        CAPTURE_ROOT
        / _capture_identifier_parts(source_match_id, observed_at, raw_sha256)
        / "response.json"
    )


def _evidence_path(evidence: VerifiedPersistedFotMobMatchDetailsEvidence) -> str:
    return _evidence_path_parts(
        evidence.source_match_id,
        evidence.observed_at,
        evidence.raw_sha256,
    )


def _source_reference(source_match_id: str, pointer: str) -> str:
    value = f"/api/matchDetails?matchId={source_match_id}#{pointer}"
    if len(value) > 512:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "reviewed source_reference exceeds Fixture Intelligence limit"
        )
    return value


def _validate_source_reference(value: Any, source_match_id: str) -> str:
    if type(value) is not str:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "fact source_reference must be an exact string"
        )
    prefix = f"/api/matchDetails?matchId={source_match_id}#/"
    if not value.startswith(prefix):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "fact source_reference does not match reviewed match-details identity"
        )
    pointer = value.split("#", 1)[1]
    if "/*" in pointer or pointer.endswith("/*"):
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "fact source_reference must not contain an array wildcard"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _fact_to_dict(fact: FixtureIntelligenceFact) -> dict[str, Any]:
    return {
        "category": fact.category.value,
        "field": fact.field,
        "status": fact.status.value,
        "value": fact.value,
        "source_provider": fact.source_provider,
        "source_role": fact.source_role.value,
        "source_reference": fact.source_reference,
        "observed_at": fact.observed_at.isoformat().replace("+00:00", "Z"),
        "evidence_file_path": fact.evidence_file_path,
        "evidence_sha256": fact.evidence_sha256,
        "notes": fact.notes,
    }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsFactCandidates:
    """Detached, internally self-consistent bundle of UNVERIFIED facts only."""

    schema_version: int
    dataset_name: str
    field_review_sha256: str
    structure_sha256: str
    evidence_receipt_sha256: str
    manifest_sha256: str
    raw_sha256: str
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    observed_at: datetime.datetime
    reviewed_at: datetime.datetime
    evidence_file_path: str
    facts: tuple[FixtureIntelligenceFact, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsFactCandidateError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsFactCandidateError("dataset_name mismatch")
        for label in (
            "field_review_sha256",
            "structure_sha256",
            "evidence_receipt_sha256",
            "manifest_sha256",
            "raw_sha256",
        ):
            _strict_sha(getattr(self, label), label)

        if type(self.fixture_identifier) is not str or type(self.source_match_id) is not str:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "fixture/source identity must be exact strings"
            )
        match = _FIXTURE_RE.fullmatch(self.fixture_identifier)
        if match is None or match.group(1) != self.source_match_id:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "fixture_identifier/source_match_id mismatch"
            )

        kickoff = _strict_utc(self.kickoff, "kickoff")
        observed_at = _strict_utc(self.observed_at, "observed_at")
        reviewed_at = _strict_utc(self.reviewed_at, "reviewed_at")
        if observed_at >= kickoff:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "observed_at must be strictly before kickoff"
            )
        if reviewed_at < observed_at or reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "reviewed_at must follow observation and remain strictly before kickoff"
            )

        expected_path = _evidence_path_parts(
            self.source_match_id,
            observed_at,
            self.raw_sha256,
        )
        if self.evidence_file_path != expected_path:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "evidence_file_path does not match deterministic PR #51 capture identity"
            )

        if type(self.facts) is not tuple or not self.facts:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "facts must be a non-empty immutable tuple"
            )
        if any(type(item) is not FixtureIntelligenceFact for item in self.facts):
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "facts must contain exact FixtureIntelligenceFact values"
            )
        expected = tuple(
            sorted(
                self.facts,
                key=lambda item: (
                    item.category.value,
                    item.field,
                    item.source_reference,
                ),
            )
        )
        if self.facts != expected:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "facts must be deterministically sorted"
            )

        semantic_targets: set[tuple[str, str]] = set()
        for fact in self.facts:
            if fact.status is not IntelligenceFactStatus.UNVERIFIED:
                raise FotMobReviewedMatchDetailsFactCandidateError(
                    "PR #55 may emit UNVERIFIED facts only"
                )
            if fact.source_provider != SOURCE_PROVIDER:
                raise FotMobReviewedMatchDetailsFactCandidateError(
                    "fact source_provider mismatch"
                )
            if fact.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
                raise FotMobReviewedMatchDetailsFactCandidateError(
                    "fact source_role mismatch"
                )
            if fact.observed_at != observed_at:
                raise FotMobReviewedMatchDetailsFactCandidateError(
                    "fact observed_at must equal exact evidence observation time"
                )
            _validate_scalar(fact.value, "fact value")
            _validate_source_reference(fact.source_reference, self.source_match_id)
            if (
                fact.evidence_sha256 != self.raw_sha256
                or fact.evidence_file_path != self.evidence_file_path
            ):
                raise FotMobReviewedMatchDetailsFactCandidateError(
                    "fact evidence identity mismatch"
                )
            target = (fact.category.value, fact.field)
            if target in semantic_targets:
                raise FotMobReviewedMatchDetailsFactCandidateError(
                    "fact semantic targets must be unique"
                )
            semantic_targets.add(target)

        if not isinstance(self.safety, Mapping) or set(self.safety) != _SAFETY_KEYS:
            raise FotMobReviewedMatchDetailsFactCandidateError("safety keys mismatch")
        for key, value in self.safety.items():
            if type(value) is not bool or value is not False:
                raise FotMobReviewedMatchDetailsFactCandidateError(
                    f"safety[{key!r}] must be exact bool False"
                )
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "reviewed_at", reviewed_at)
        object.__setattr__(self, "safety", _default_safety())

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime.datetime) -> str:
            return value.isoformat().replace("+00:00", "Z")

        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "field_review_sha256": self.field_review_sha256,
            "structure_sha256": self.structure_sha256,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "raw_sha256": self.raw_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": iso(self.kickoff),
            "observed_at": iso(self.observed_at),
            "reviewed_at": iso(self.reviewed_at),
            "evidence_file_path": self.evidence_file_path,
            "facts": [_fact_to_dict(item) for item in self.facts],
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
) -> tuple[VerifiedPersistedFotMobMatchDetailsEvidence, ReviewedMatchDetailsFieldSemantics, bytes]:
    if type(evidence) is not VerifiedPersistedFotMobMatchDetailsEvidence:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "evidence must be exact PR #52 verified evidence"
        )
    if type(assessment) is not FotMobReviewedMatchDetailsStructureAssessment:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "assessment must be exact PR #53 structural assessment"
        )
    if type(review) is not ReviewedMatchDetailsFieldSemantics:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "review must be exact PR #54 field semantics review"
        )
    if type(review_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "review_bytes must be exact immutable bytes"
        )
    try:
        supplied = canonical_reviewed_match_details_field_semantics_bytes(review)
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
    except FotMobReviewedMatchDetailsFieldReviewError as exc:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "PR #54 field review failed exact current byte revalidation"
        ) from exc
    if supplied != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "supplied PR #54 review differs from exact semantic rebuild"
        )
    if review_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "review_bytes are not exact canonical PR #54 bytes"
        )
    return evidence, rebuilt, rebuilt_bytes


def build_reviewed_match_details_fact_candidates(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
) -> ReviewedMatchDetailsFactCandidates:
    evidence, rebuilt_review, exact_review_bytes = _revalidate_review(
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
    )
    approved = tuple(
        item
        for item in rebuilt_review.decisions
        if item.disposition is FieldReviewDisposition.APPROVED
    )
    if not approved:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "at least one explicit PR #54 APPROVED scalar decision is required"
        )

    payload = _strict_json_object(raw_bytes)
    evidence_file_path = _evidence_path(evidence)
    facts: list[FixtureIntelligenceFact] = []
    for decision in approved:
        value = _resolve_scalar(payload, decision.json_pointer)
        actual_kind = _actual_kind(value)
        if actual_kind is not decision.expected_kind:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "resolved scalar kind differs from explicit PR #54 review"
            )
        notes = (
            f"PR #54 mapping reviewed under {rebuilt_review.reviewer_reference}; "
            "source semantic capability remains unqualified; value remains UNVERIFIED."
        )
        try:
            fact = FixtureIntelligenceFact(
                category=decision.category,
                field=decision.field,
                status=IntelligenceFactStatus.UNVERIFIED,
                value=value,
                source_provider=SOURCE_PROVIDER,
                source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
                source_reference=_source_reference(
                    evidence.source_match_id,
                    decision.json_pointer,
                ),
                observed_at=evidence.observed_at,
                evidence_file_path=evidence_file_path,
                evidence_sha256=evidence.raw_sha256,
                notes=notes,
            )
        except FixtureIntelligenceError as exc:
            raise FotMobReviewedMatchDetailsFactCandidateError(
                "Fixture Intelligence UNVERIFIED fact construction failed closed"
            ) from exc
        facts.append(fact)

    sorted_facts = tuple(
        sorted(
            facts,
            key=lambda item: (
                item.category.value,
                item.field,
                item.source_reference,
            ),
        )
    )
    return ReviewedMatchDetailsFactCandidates(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        field_review_sha256=hashlib.sha256(exact_review_bytes).hexdigest(),
        structure_sha256=rebuilt_review.structure_sha256,
        evidence_receipt_sha256=rebuilt_review.evidence_receipt_sha256,
        manifest_sha256=rebuilt_review.manifest_sha256,
        raw_sha256=rebuilt_review.raw_sha256,
        fixture_identifier=rebuilt_review.fixture_identifier,
        source_match_id=rebuilt_review.source_match_id,
        kickoff=evidence.kickoff,
        observed_at=evidence.observed_at,
        reviewed_at=rebuilt_review.reviewed_at,
        evidence_file_path=evidence_file_path,
        facts=sorted_facts,
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_fact_candidates_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsFactCandidates:
        raise FotMobReviewedMatchDetailsFactCandidateError(
            "value must be exact ReviewedMatchDetailsFactCandidates"
        )
    rebuilt = dataclasses.replace(value)
    return _canonical_json_bytes(rebuilt.to_dict())


def sha256_reviewed_match_details_fact_candidates(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_fact_candidates_bytes(value)
    ).hexdigest()


__all__ = [
    "CAPTURE_ROOT",
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "SOURCE_PROVIDER",
    "FotMobReviewedMatchDetailsFactCandidateError",
    "ReviewedMatchDetailsFactCandidates",
    "build_reviewed_match_details_fact_candidates",
    "canonical_reviewed_match_details_fact_candidates_bytes",
    "sha256_reviewed_match_details_fact_candidates",
]
