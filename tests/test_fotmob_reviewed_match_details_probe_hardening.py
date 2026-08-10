from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_probe import (
    FotMobReviewedMatchDetailsProbeError,
    canonical_match_details_probe_receipt_bytes,
)
from domain.reviewed_fixture_catalog_admission import REVIEWED_SOURCE_CAPABILITY
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY
from scripts.probe_fotmob_reviewed_match_details import probe_fotmob_reviewed_match_details


def _helpers():
    path = Path(__file__).with_name("test_fotmob_reviewed_match_details_probe.py")
    spec = importlib.util.spec_from_file_location("_athena_pr49_probe_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #49 test helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_receipt_serialization_is_detached_from_forced_plan_field_mutation(tmp_path: Path) -> None:
    h = _helpers()
    verified, receipt_bytes = h._upstream(tmp_path)
    receipt = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=h._factory(h._Connection(response=h._Response()), []),
        clock=h._Clock(h.REQUEST_AT, h.SEND_AT, h.OBSERVED_AT),
    ).receipt
    historical = canonical_match_details_probe_receipt_bytes(receipt)
    assert receipt.plan_sha256 == hashlib.sha256(receipt.plan_bytes).hexdigest()

    object.__setattr__(receipt.plan, "fixture_identifier", "FOTMOB:9999")
    object.__setattr__(receipt.plan, "source_match_id", "9999")

    assert canonical_match_details_probe_receipt_bytes(receipt) == historical
    with pytest.raises(
        FotMobReviewedMatchDetailsProbeError,
        match="probe plan failed exact current revalidation",
    ):
        dataclasses.replace(receipt)


def test_receipt_rejects_changed_canonical_plan_bytes_or_hash(tmp_path: Path) -> None:
    h = _helpers()
    verified, receipt_bytes = h._upstream(tmp_path)
    receipt = probe_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        connection_factory=h._factory(h._Connection(response=h._Response()), []),
        clock=h._Clock(h.REQUEST_AT, h.SEND_AT, h.OBSERVED_AT),
    ).receipt

    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="exact canonical bytes"):
        dataclasses.replace(receipt, plan_bytes=receipt.plan_bytes + b"\n")
    with pytest.raises(FotMobReviewedMatchDetailsProbeError, match="plan_sha256"):
        dataclasses.replace(receipt, plan_sha256="f" * 64)


def test_send_clock_mutation_is_caught_by_revalidation_before_endheaders(tmp_path: Path) -> None:
    h = _helpers()
    verified, receipt_bytes = h._upstream(tmp_path)
    connection = h._Connection(response=h._Response())
    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 1:
            return h.REQUEST_AT
        if calls == 2:
            SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
                original,
                reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
            )
            return h.SEND_AT
        return h.OBSERVED_AT

    try:
        with pytest.raises(
            FotMobReviewedMatchDetailsProbeError,
            match="final pre-send revalidation",
        ):
            probe_fotmob_reviewed_match_details(
                verified_bootstrap_artifact=verified,
                verification_receipt_bytes=receipt_bytes,
                fixture_identifier="FOTMOB:1001",
                execute_live_network=True,
                connection_factory=h._factory(connection, []),
                clock=clock,
            )
        assert connection.endheaders_calls == 0
        assert connection.closed is True
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original
