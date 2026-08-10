from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_persisted_evidence import (
    canonical_persisted_match_details_evidence_receipt_bytes,
    verify_persisted_match_details_evidence,
)
from domain.fotmob_reviewed_match_details_structure import (
    FotMobReviewedMatchDetailsStructureError,
    JsonValueKind,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
    sha256_reviewed_match_details_structure,
)


def _pr52(raw: bytes):
    helper_path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_persisted_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr52_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #52 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module._manifest_bytes(module._payload(raw))
    evidence = verify_persisted_match_details_evidence(
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    receipt = canonical_persisted_match_details_evidence_receipt_bytes(evidence)
    return evidence, receipt, manifest


def _field(assessment, pointer: str):
    return next(item for item in assessment.fields if item.json_pointer == pointer)


def test_structure_inventory_is_deterministic_and_semantics_free() -> None:
    raw = (
        b'{"events":[{"minute":1,"type":"x"},{"minute":2.5,"type":"y"}],'
        b'"general":{"flag":true,"homeTeam":{"id":1}},"nullable":null}'
    )
    evidence, receipt, manifest = _pr52(raw)
    assessment = assess_reviewed_match_details_structure(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    assert assessment.fixture_identifier == "FOTMOB:1001"
    assert assessment.top_level_keys == ("events", "general", "nullable")
    assert _field(assessment, "").kinds == (JsonValueKind.OBJECT,)
    assert _field(assessment, "/events").kinds == (JsonValueKind.ARRAY,)
    assert _field(assessment, "/events/*").occurrences == 2
    assert _field(assessment, "/events/*/minute").kinds == (
        JsonValueKind.INTEGER,
        JsonValueKind.NUMBER,
    )
    assert _field(assessment, "/events/*/minute").occurrences == 2
    assert _field(assessment, "/general/flag").kinds == (JsonValueKind.BOOLEAN,)
    assert _field(assessment, "/nullable").kinds == (JsonValueKind.NULL,)
    assert all(value is False for value in assessment.safety.values())
    canonical = canonical_reviewed_match_details_structure_bytes(assessment)
    assert canonical.endswith(b"\n")
    assert len(sha256_reviewed_match_details_structure(assessment)) == 64


def test_json_pointer_tokens_are_rfc6901_escaped() -> None:
    raw = b'{"a/b~c":{"x":1}}'
    evidence, receipt, manifest = _pr52(raw)
    assessment = assess_reviewed_match_details_structure(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    assert _field(assessment, "/a~1b~0c/x").kinds == (JsonValueKind.INTEGER,)


def test_exact_pr52_receipt_and_exact_evidence_bytes_are_required() -> None:
    raw = b'{"general":{"id":1}}'
    evidence, receipt, manifest = _pr52(raw)
    with pytest.raises(FotMobReviewedMatchDetailsStructureError, match="exact canonical PR #52"):
        assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=receipt + b"\n",
            manifest_bytes=manifest,
            raw_bytes=raw,
        )
    with pytest.raises(FotMobReviewedMatchDetailsStructureError, match="PR #52 evidence"):
        assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw + b" ",
        )


def test_forced_pr52_object_mutation_cannot_be_silently_repaired() -> None:
    raw = b'{"general":{"id":1}}'
    evidence, receipt, manifest = _pr52(raw)
    object.__setattr__(evidence, "fixture_identifier", "FOTMOB:9999")
    with pytest.raises(FotMobReviewedMatchDetailsStructureError):
        assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
        )


def test_duplicate_keys_nonfinite_numbers_invalid_utf8_and_nonobject_root_fail_closed() -> None:
    for raw, pattern in (
        (b'{"x":1,"x":2}', "duplicate response JSON key"),
        (b'{"x":NaN}', "invalid response JSON constant"),
        (b'{"x":1e400}', "number must be finite"),
        (b"\xff", "strict finite UTF-8 JSON"),
        (b"[]", "root must be a JSON object"),
    ):
        evidence, receipt, manifest = _pr52(raw)
        with pytest.raises(FotMobReviewedMatchDetailsStructureError, match=pattern):
            assess_reviewed_match_details_structure(
                evidence=evidence,
                evidence_receipt_bytes=receipt,
                manifest_bytes=manifest,
                raw_bytes=raw,
            )


def test_depth_limit_fails_closed() -> None:
    raw = ("{\"x\":" * 66 + "1" + "}" * 66).encode("utf-8")
    evidence, receipt, manifest = _pr52(raw)
    with pytest.raises(FotMobReviewedMatchDetailsStructureError, match="maximum structural depth"):
        assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
        )


def test_assessment_derived_state_cannot_be_mutated_consistently() -> None:
    raw = b'{"general":{"id":1}}'
    evidence, receipt, manifest = _pr52(raw)
    assessment = assess_reviewed_match_details_structure(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    with pytest.raises(FotMobReviewedMatchDetailsStructureError):
        dataclasses.replace(assessment, node_count=0)
