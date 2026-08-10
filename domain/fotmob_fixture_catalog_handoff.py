"""Self-validating offline handoff from reviewed FotMob candidates to PR #29 input."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any, Tuple

from domain.fixture_catalog import INPUT_RECORD_KEYS, canonical_json_line_bytes
from domain.fotmob_fixture_candidate_review import (
    FotMobFixtureCandidateReviewBundle,
    FotMobReviewedFixtureCatalogInput,
    build_fotmob_fixture_candidate_review_bundle,
    canonical_fotmob_fixture_candidate_review_bundle_bytes,
    sha256_fotmob_fixture_candidate_review_bundle,
)
from domain.fotmob_fixture_candidates import (
    FotMobFixtureCandidateBundle,
    sha256_fotmob_fixture_candidate_bundle,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-fixture-catalog-handoff-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_capture_authorized",
        "automatic_review_authorized",
        "source_qualified",
        "team_identity_resolution_authorized",
        "competition_identity_resolution_authorized",
        "fixture_identity_resolution_authorized",
        "fixture_catalog_compile_authorized",
        "fixture_catalog_write_authorized",
        "fixture_catalog_promotion_authorized",
        "intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobFixtureCatalogHandoffError(ValueError):
    """Raised when a reviewed-candidate handoff cannot be proven exactly."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobFixtureCatalogHandoffError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobFixtureCatalogHandoffError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobFixtureCatalogHandoffError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _review_bundle_exactly_rebuilds(
    candidate_bundle: FotMobFixtureCandidateBundle,
    review_bundle: FotMobFixtureCandidateReviewBundle,
) -> None:
    candidate_sha = sha256_fotmob_fixture_candidate_bundle(candidate_bundle)
    if review_bundle.candidate_bundle_sha256 != candidate_sha:
        raise FotMobFixtureCatalogHandoffError(
            "review bundle does not anchor the exact candidate bundle SHA-256"
        )
    try:
        rebuilt = build_fotmob_fixture_candidate_review_bundle(
            candidate_bundle,
            review_bundle.decisions,
        )
        expected = canonical_fotmob_fixture_candidate_review_bundle_bytes(rebuilt)
        supplied = canonical_fotmob_fixture_candidate_review_bundle_bytes(review_bundle)
    except ValueError as exc:
        raise FotMobFixtureCatalogHandoffError(
            f"review bundle rebuild failed closed: {exc}"
        ) from exc
    if supplied != expected:
        raise FotMobFixtureCatalogHandoffError(
            "review bundle is not the exact deterministic result of its candidate bundle and decisions"
        )


def _catalog_input_records(
    review_bundle: FotMobFixtureCandidateReviewBundle,
) -> Tuple[FotMobReviewedFixtureCatalogInput, ...]:
    records = review_bundle.approved_catalog_inputs
    if type(records) is not tuple:
        raise FotMobFixtureCatalogHandoffError(
            "approved catalog inputs must remain an immutable tuple"
        )
    if not records:
        raise FotMobFixtureCatalogHandoffError(
            "at least one explicit approved catalog input is required for handoff"
        )
    if any(type(item) is not FotMobReviewedFixtureCatalogInput for item in records):
        raise FotMobFixtureCatalogHandoffError(
            "approved catalog inputs contain an invalid value"
        )
    return records


def _catalog_input_jsonl_bytes(
    records: Tuple[FotMobReviewedFixtureCatalogInput, ...],
) -> bytes:
    chunks: list[bytes] = []
    seen_source_ids: set[str] = set()
    for item in records:
        payload = item.to_catalog_input_dict()
        if set(payload) != INPUT_RECORD_KEYS:
            raise FotMobFixtureCatalogHandoffError(
                "approved catalog input keys do not match the PR #29 contract"
            )
        source_id = payload["source_fixture_identifier"]
        if type(source_id) is not str or not source_id:
            raise FotMobFixtureCatalogHandoffError(
                "source_fixture_identifier must remain a non-empty exact string"
            )
        if source_id in seen_source_ids:
            raise FotMobFixtureCatalogHandoffError(
                "duplicate source_fixture_identifier in reviewed catalog handoff"
            )
        seen_source_ids.add(source_id)
        try:
            chunks.append(canonical_json_line_bytes(payload))
        except (TypeError, ValueError, OverflowError) as exc:
            raise FotMobFixtureCatalogHandoffError(
                "approved catalog input serialization failed"
            ) from exc
    return b"".join(chunks)


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCatalogHandoff:
    """Immutable proof that reviewed PR #41 inputs still derive from PR #40 evidence."""

    candidate_bundle: FotMobFixtureCandidateBundle
    review_bundle: FotMobFixtureCandidateReviewBundle
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.candidate_bundle) is not FotMobFixtureCandidateBundle:
            raise FotMobFixtureCatalogHandoffError(
                "candidate_bundle must be exact FotMobFixtureCandidateBundle"
            )
        if type(self.review_bundle) is not FotMobFixtureCandidateReviewBundle:
            raise FotMobFixtureCatalogHandoffError(
                "review_bundle must be exact FotMobFixtureCandidateReviewBundle"
            )
        _review_bundle_exactly_rebuilds(self.candidate_bundle, self.review_bundle)
        records = _catalog_input_records(self.review_bundle)
        _catalog_input_jsonl_bytes(records)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    @property
    def catalog_inputs(self) -> Tuple[FotMobReviewedFixtureCatalogInput, ...]:
        return self.review_bundle.approved_catalog_inputs

    @property
    def candidate_bundle_sha256(self) -> str:
        return sha256_fotmob_fixture_candidate_bundle(self.candidate_bundle)

    @property
    def review_bundle_sha256(self) -> str:
        return sha256_fotmob_fixture_candidate_review_bundle(self.review_bundle)

    @property
    def catalog_input_jsonl_bytes(self) -> bytes:
        return _catalog_input_jsonl_bytes(self.catalog_inputs)

    @property
    def catalog_input_sha256(self) -> str:
        return hashlib.sha256(self.catalog_input_jsonl_bytes).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        input_bytes = self.catalog_input_jsonl_bytes
        candidate_sha = _sha256(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        review_sha = _sha256(self.review_bundle_sha256, "review_bundle_sha256")
        input_sha = _sha256(
            hashlib.sha256(input_bytes).hexdigest(),
            "catalog_input_sha256",
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "candidate_bundle_sha256": candidate_sha,
            "review_bundle_sha256": review_sha,
            "source_capture_count": len(self.candidate_bundle.sources),
            "candidate_count": self.review_bundle.candidate_count,
            "decision_count": self.review_bundle.decision_count,
            "approved_count": self.review_bundle.approved_count,
            "rejected_count": self.review_bundle.rejected_count,
            "unreviewed_count": self.review_bundle.unreviewed_count,
            "blocked_candidate_count": self.review_bundle.blocked_candidate_count,
            "catalog_input_count": len(self.catalog_inputs),
            "catalog_input_byte_size": len(input_bytes),
            "catalog_input_sha256": input_sha,
            "catalog_inputs": [item.to_catalog_input_dict() for item in self.catalog_inputs],
            "safety": dict(self.safety),
        }


def build_fotmob_fixture_catalog_handoff(
    candidate_bundle: Any,
    review_bundle: Any,
) -> FotMobFixtureCatalogHandoff:
    """Build a handoff without compiling, writing, promoting, or qualifying a catalog."""

    if type(candidate_bundle) is not FotMobFixtureCandidateBundle:
        raise FotMobFixtureCatalogHandoffError(
            "candidate_bundle must be exact FotMobFixtureCandidateBundle"
        )
    if type(review_bundle) is not FotMobFixtureCandidateReviewBundle:
        raise FotMobFixtureCatalogHandoffError(
            "review_bundle must be exact FotMobFixtureCandidateReviewBundle"
        )
    return FotMobFixtureCatalogHandoff(
        candidate_bundle=candidate_bundle,
        review_bundle=review_bundle,
        safety=_default_safety(),
    )


def canonical_fotmob_fixture_catalog_handoff_bytes(handoff: Any) -> bytes:
    if type(handoff) is not FotMobFixtureCatalogHandoff:
        raise FotMobFixtureCatalogHandoffError(
            "handoff must be exact FotMobFixtureCatalogHandoff"
        )
    try:
        return (
            json.dumps(
                handoff.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCatalogHandoffError(
            "handoff serialization failed"
        ) from exc


def sha256_fotmob_fixture_catalog_handoff(handoff: Any) -> str:
    return hashlib.sha256(
        canonical_fotmob_fixture_catalog_handoff_bytes(handoff)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "FotMobFixtureCatalogHandoff",
    "FotMobFixtureCatalogHandoffError",
    "build_fotmob_fixture_catalog_handoff",
    "canonical_fotmob_fixture_catalog_handoff_bytes",
    "sha256_fotmob_fixture_catalog_handoff",
]
