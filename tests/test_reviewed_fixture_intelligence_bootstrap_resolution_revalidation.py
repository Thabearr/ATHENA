from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from domain.reviewed_fixture_catalog_admission import REVIEWED_SOURCE_CAPABILITY
from domain.reviewed_fixture_intelligence_bootstrap import (
    ReviewedFixtureIntelligenceBootstrapError,
    resolve_reviewed_fixture_intelligence_identity,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


def _bootstrap_fixture(tmp_path: Path):
    helper_path = Path(__file__).with_name(
        "test_reviewed_fixture_intelligence_bootstrap.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_athena_pr47_existing_bootstrap_tests",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load existing PR #47 bootstrap fixture helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._bootstrap(tmp_path)


def test_resolver_revalidates_bootstrap_before_returning_identity(tmp_path: Path) -> None:
    _, _, _, bootstrap = _bootstrap_fixture(tmp_path)
    fake = dataclasses.replace(
        bootstrap.fixtures[0],
        fixture_identifier="FOTMOB:9999",
    )
    object.__setattr__(bootstrap, "fixtures", (fake,))

    with pytest.raises(
        ReviewedFixtureIntelligenceBootstrapError,
        match="bootstrap failed exact revalidation before fixture identity resolution",
    ):
        resolve_reviewed_fixture_intelligence_identity(bootstrap, "FOTMOB:9999")


def test_capability_revocation_blocks_new_identity_resolution_but_not_history(
    tmp_path: Path,
) -> None:
    _, _, _, bootstrap = _bootstrap_fixture(tmp_path)
    before = bootstrap.to_dict()
    original = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = dataclasses.replace(
        original,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
    )
    try:
        assert bootstrap.to_dict() == before
        with pytest.raises(
            ReviewedFixtureIntelligenceBootstrapError,
            match="bootstrap failed exact revalidation before fixture identity resolution",
        ):
            resolve_reviewed_fixture_intelligence_identity(bootstrap, "FOTMOB:1001")
    finally:
        SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY] = original
