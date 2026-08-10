"""Strict offline structural assessment of reviewed FotMob match-details bytes.

This boundary is the first permitted response-body parse after PR #52. It
inventories JSON structure only; field meanings, source qualification, and
Fixture Intelligence trust remain explicitly unauthorized.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
import types
from collections.abc import Mapping
from typing import Any

from domain.fotmob_reviewed_match_details_persisted_evidence import (
    VerifiedPersistedFotMobMatchDetailsEvidence,
    FotMobReviewedMatchDetailsPersistedEvidenceError,
    canonical_persisted_match_details_evidence_receipt_bytes,
    verify_persisted_match_details_evidence,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-structure-v1"
MAX_DEPTH = 64
MAX_NODES = 100_000
MAX_PATHS = 50_000
MAX_POINTER_LENGTH = 2048

_SAFETY_KEYS = frozenset(
    {
        "semantic_review_authorized",
        "source_qualification_authorized",
        "football_semantics_authorized",
        "field_extraction_authorized",
        "intelligence_fact_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsStructureError(ValueError):
    pass


class JsonValueKind(str, enum.Enum):
    ARRAY = "ARRAY"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    NULL = "NULL"
    NUMBER = "NUMBER"
    OBJECT = "OBJECT"
    STRING = "STRING"


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
        raise FotMobReviewedMatchDetailsStructureError(
            "structural assessment serialization failed"
        ) from exc


def _pairs(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str:
            raise FotMobReviewedMatchDetailsStructureError(
                "response JSON object keys must be strings"
            )
        if key in result:
            raise FotMobReviewedMatchDetailsStructureError(
                f"duplicate response JSON key: {key}"
            )
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise FotMobReviewedMatchDetailsStructureError(
        f"invalid response JSON constant: {value}"
    )


def _float(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsStructureError(
            "invalid response JSON number"
        ) from exc
    if not math.isfinite(parsed):
        raise FotMobReviewedMatchDetailsStructureError(
            "response JSON number must be finite"
        )
    return parsed


def _strict_response_json(raw_bytes: Any) -> dict[str, Any]:
    if type(raw_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsStructureError(
            "raw_bytes must be exact immutable bytes"
        )
    try:
        value = json.loads(
            raw_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=_float,
        )
    except FotMobReviewedMatchDetailsStructureError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsStructureError(
            "response body is not strict finite UTF-8 JSON"
        ) from exc
    if type(value) is not dict:
        raise FotMobReviewedMatchDetailsStructureError(
            "match-details response root must be a JSON object"
        )
    return value


def _kind(value: Any) -> JsonValueKind:
    if value is None:
        return JsonValueKind.NULL
    if type(value) is bool:
        return JsonValueKind.BOOLEAN
    if type(value) is int:
        return JsonValueKind.INTEGER
    if type(value) is float:
        if not math.isfinite(value):
            raise FotMobReviewedMatchDetailsStructureError(
                "response JSON number must be finite"
            )
        return JsonValueKind.NUMBER
    if type(value) is str:
        return JsonValueKind.STRING
    if type(value) is list:
        return JsonValueKind.ARRAY
    if type(value) is dict:
        return JsonValueKind.OBJECT
    raise FotMobReviewedMatchDetailsStructureError(
        f"unsupported parsed JSON value type: {type(value).__name__}"
    )


def _escape_pointer_token(value: str) -> str:
    # ATHENA reserves the literal segment '*' for array wildcards. Normal
    # RFC-6901 escaping is extended with ~2 for a literal '*' key, after ~ is
    # escaped first, so the mapping remains injective.
    return value.replace("~", "~0").replace("/", "~1").replace("*", "~2")


def _validate_pointer(value: Any) -> str:
    if type(value) is not str:
        raise FotMobReviewedMatchDetailsStructureError(
            "json_pointer must be an exact string"
        )
    if value and not value.startswith("/"):
        raise FotMobReviewedMatchDetailsStructureError(
            "json_pointer must be empty root or begin with '/'"
        )
    if len(value) > MAX_POINTER_LENGTH:
        raise FotMobReviewedMatchDetailsStructureError(
            "json_pointer exceeds maximum length"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


@dataclasses.dataclass(frozen=True)
class StructuralField:
    json_pointer: str
    kinds: tuple[JsonValueKind, ...]
    occurrences: int

    def __post_init__(self) -> None:
        pointer = _validate_pointer(self.json_pointer)
        if type(self.kinds) is not tuple or not self.kinds:
            raise FotMobReviewedMatchDetailsStructureError(
                "kinds must be a non-empty immutable tuple"
            )
        if any(not isinstance(item, JsonValueKind) for item in self.kinds):
            raise FotMobReviewedMatchDetailsStructureError(
                "kinds must contain only JsonValueKind"
            )
        expected = tuple(sorted(set(self.kinds), key=lambda item: item.value))
        if self.kinds != expected:
            raise FotMobReviewedMatchDetailsStructureError(
                "kinds must be sorted and unique"
            )
        if type(self.occurrences) is not int or self.occurrences <= 0:
            raise FotMobReviewedMatchDetailsStructureError(
                "occurrences must be an exact positive integer"
            )
        object.__setattr__(self, "json_pointer", pointer)

    def to_dict(self) -> dict[str, Any]:
        return {
            "json_pointer": self.json_pointer,
            "kinds": [item.value for item in self.kinds],
            "occurrences": self.occurrences,
        }


@dataclasses.dataclass(frozen=True)
class FotMobReviewedMatchDetailsStructureAssessment:
    schema_version: int
    dataset_name: str
    evidence_receipt_sha256: str
    manifest_sha256: str
    raw_sha256: str
    raw_size: int
    fixture_identifier: str
    source_match_id: str
    top_level_keys: tuple[str, ...]
    node_count: int
    max_depth: int
    fields: tuple[StructuralField, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsStructureError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsStructureError("dataset_name mismatch")
        for label in ("evidence_receipt_sha256", "manifest_sha256", "raw_sha256"):
            value = getattr(self, label)
            if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise FotMobReviewedMatchDetailsStructureError(
                    f"{label} must be exactly 64 lowercase hexadecimal characters"
                )
        if type(self.raw_size) is not int or self.raw_size <= 0:
            raise FotMobReviewedMatchDetailsStructureError("raw_size must be positive")
        if type(self.fixture_identifier) is not str or type(self.source_match_id) is not str:
            raise FotMobReviewedMatchDetailsStructureError("fixture/source identity must be strings")
        if type(self.top_level_keys) is not tuple or any(type(item) is not str for item in self.top_level_keys):
            raise FotMobReviewedMatchDetailsStructureError(
                "top_level_keys must be an immutable string tuple"
            )
        if self.top_level_keys != tuple(sorted(set(self.top_level_keys))):
            raise FotMobReviewedMatchDetailsStructureError(
                "top_level_keys must be sorted and unique"
            )
        if type(self.node_count) is not int or not 1 <= self.node_count <= MAX_NODES:
            raise FotMobReviewedMatchDetailsStructureError("node_count outside reviewed bounds")
        if type(self.max_depth) is not int or not 0 <= self.max_depth <= MAX_DEPTH:
            raise FotMobReviewedMatchDetailsStructureError("max_depth outside reviewed bounds")
        if type(self.fields) is not tuple or not self.fields:
            raise FotMobReviewedMatchDetailsStructureError(
                "fields must be a non-empty immutable tuple"
            )
        if any(type(item) is not StructuralField for item in self.fields):
            raise FotMobReviewedMatchDetailsStructureError(
                "fields must contain exact StructuralField values"
            )
        expected_fields = tuple(sorted(self.fields, key=lambda item: item.json_pointer))
        if self.fields != expected_fields or len({item.json_pointer for item in self.fields}) != len(self.fields):
            raise FotMobReviewedMatchDetailsStructureError(
                "fields must be sorted by unique json_pointer"
            )
        root = tuple(item for item in self.fields if item.json_pointer == "")
        if len(root) != 1 or root[0].kinds != (JsonValueKind.OBJECT,) or root[0].occurrences != 1:
            raise FotMobReviewedMatchDetailsStructureError(
                "structural inventory must contain exactly one OBJECT root"
            )
        if not isinstance(self.safety, Mapping) or set(self.safety) != _SAFETY_KEYS:
            raise FotMobReviewedMatchDetailsStructureError("safety keys mismatch")
        for key, value in self.safety.items():
            if type(value) is not bool or value is not False:
                raise FotMobReviewedMatchDetailsStructureError(
                    f"safety[{key!r}] must be exact bool False"
                )
        object.__setattr__(self, "safety", _default_safety())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "top_level_keys": list(self.top_level_keys),
            "node_count": self.node_count,
            "max_depth": self.max_depth,
            "fields": [item.to_dict() for item in self.fields],
            "safety": dict(self.safety),
        }


def _revalidate_evidence(
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
) -> tuple[VerifiedPersistedFotMobMatchDetailsEvidence, bytes]:
    if type(evidence) is not VerifiedPersistedFotMobMatchDetailsEvidence:
        raise FotMobReviewedMatchDetailsStructureError(
            "evidence must be exact VerifiedPersistedFotMobMatchDetailsEvidence"
        )
    if type(evidence_receipt_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsStructureError(
            "evidence_receipt_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_persisted_match_details_evidence_receipt_bytes(evidence)
        rebuilt = verify_persisted_match_details_evidence(
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
        )
        rebuilt_bytes = canonical_persisted_match_details_evidence_receipt_bytes(rebuilt)
    except FotMobReviewedMatchDetailsPersistedEvidenceError as exc:
        raise FotMobReviewedMatchDetailsStructureError(
            "PR #52 evidence failed exact current byte revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsStructureError(
            "supplied PR #52 evidence differs from exact byte rebuild"
        )
    if evidence_receipt_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsStructureError(
            "evidence_receipt_bytes are not the exact canonical PR #52 receipt"
        )
    return rebuilt, rebuilt_bytes


def _inventory(payload: dict[str, Any]) -> tuple[tuple[StructuralField, ...], int, int]:
    kinds: dict[str, set[JsonValueKind]] = {}
    occurrences: dict[str, int] = {}
    node_count = 0
    max_depth = 0

    def visit(value: Any, pointer: str, depth: int) -> None:
        nonlocal node_count, max_depth
        if depth > MAX_DEPTH:
            raise FotMobReviewedMatchDetailsStructureError(
                "response JSON exceeds maximum structural depth"
            )
        node_count += 1
        if node_count > MAX_NODES:
            raise FotMobReviewedMatchDetailsStructureError(
                "response JSON exceeds maximum structural node count"
            )
        pointer = _validate_pointer(pointer)
        if pointer not in kinds and len(kinds) >= MAX_PATHS:
            raise FotMobReviewedMatchDetailsStructureError(
                "response JSON exceeds maximum distinct structural paths"
            )
        kinds.setdefault(pointer, set()).add(_kind(value))
        occurrences[pointer] = occurrences.get(pointer, 0) + 1
        max_depth = max(max_depth, depth)
        if type(value) is dict:
            for key in sorted(value):
                token = _escape_pointer_token(key)
                visit(value[key], pointer + "/" + token, depth + 1)
        elif type(value) is list:
            child_pointer = pointer + "/*"
            for item in value:
                visit(item, child_pointer, depth + 1)

    visit(payload, "", 0)
    fields = tuple(
        StructuralField(
            json_pointer=pointer,
            kinds=tuple(sorted(kinds[pointer], key=lambda item: item.value)),
            occurrences=occurrences[pointer],
        )
        for pointer in sorted(kinds)
    )
    return fields, node_count, max_depth


def assess_reviewed_match_details_structure(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
) -> FotMobReviewedMatchDetailsStructureAssessment:
    rebuilt, exact_receipt_bytes = _revalidate_evidence(
        evidence,
        evidence_receipt_bytes,
        manifest_bytes,
        raw_bytes,
    )
    payload = _strict_response_json(raw_bytes)
    fields, node_count, max_depth = _inventory(payload)
    return FotMobReviewedMatchDetailsStructureAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        evidence_receipt_sha256=hashlib.sha256(exact_receipt_bytes).hexdigest(),
        manifest_sha256=rebuilt.manifest_sha256,
        raw_sha256=rebuilt.raw_sha256,
        raw_size=rebuilt.raw_size,
        fixture_identifier=rebuilt.fixture_identifier,
        source_match_id=rebuilt.source_match_id,
        top_level_keys=tuple(sorted(payload)),
        node_count=node_count,
        max_depth=max_depth,
        fields=fields,
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_structure_bytes(value: Any) -> bytes:
    if type(value) is not FotMobReviewedMatchDetailsStructureAssessment:
        raise FotMobReviewedMatchDetailsStructureError(
            "value must be exact FotMobReviewedMatchDetailsStructureAssessment"
        )
    rebuilt = dataclasses.replace(value)
    return _canonical_json_bytes(rebuilt.to_dict())


def sha256_reviewed_match_details_structure(value: Any) -> str:
    return hashlib.sha256(canonical_reviewed_match_details_structure_bytes(value)).hexdigest()


__all__ = [
    "DATASET_NAME", "MAX_DEPTH", "MAX_NODES", "MAX_PATHS", "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsStructureAssessment",
    "FotMobReviewedMatchDetailsStructureError", "JsonValueKind", "StructuralField",
    "assess_reviewed_match_details_structure",
    "canonical_reviewed_match_details_structure_bytes",
    "sha256_reviewed_match_details_structure",
]
