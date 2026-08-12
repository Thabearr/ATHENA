from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.support.module_loader import load_test_module

import domain.reviewed_fixture_intelligence_bootstrap_artifact as artifact_module
from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    ReviewedFixtureIntelligenceBootstrapArtifactError,
    canonical_verified_bootstrap_artifact_receipt_bytes,
)


def _verified_fixture(tmp_path: Path):
    module = load_test_module("test_reviewed_fixture_intelligence_bootstrap_artifact")
    return module._verified(tmp_path)


def test_receipt_history_is_detached_from_its_stored_bootstrap(tmp_path: Path) -> None:
    _, _, verified = _verified_fixture(tmp_path)
    before = canonical_verified_bootstrap_artifact_receipt_bytes(verified)

    object.__setattr__(verified.bootstrap, "catalog_sha256", "f" * 64)

    assert canonical_verified_bootstrap_artifact_receipt_bytes(verified) == before
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="failed exact PR #47 revalidation",
    ):
        dataclasses.replace(verified)


def test_receipt_history_is_detached_from_live_pr47_contract_constants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, verified = _verified_fixture(tmp_path)
    before = canonical_verified_bootstrap_artifact_receipt_bytes(verified)

    monkeypatch.setattr(
        artifact_module,
        "BOOTSTRAP_DATASET_NAME",
        "changed-live-pr47-contract",
    )
    monkeypatch.setattr(
        artifact_module,
        "BOOTSTRAP_SCHEMA_VERSION",
        999,
    )

    assert canonical_verified_bootstrap_artifact_receipt_bytes(verified) == before
    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapArtifactError,
        match="bootstrap_schema_version does not match",
    ):
        dataclasses.replace(verified)
