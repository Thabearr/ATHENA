from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest

from domain.reviewed_fixture_catalog_admission import (
    canonical_reviewed_fixture_catalog_admission_bytes,
)
from domain.reviewed_fixture_catalog_admission_artifact import (
    ReviewedFixtureCatalogAdmissionArtifactError,
    verify_reviewed_fixture_catalog_admission_artifact,
)


UTC = datetime.timezone.utc


def _admission_fixture(tmp_path: Path):
    helper_path = Path(__file__).with_name(
        "test_reviewed_fixture_catalog_admission_artifact.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_athena_pr46_existing_artifact_tests",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load existing PR #46 admission fixture helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._admission(tmp_path)


def test_mutated_admitted_fixtures_cannot_be_silently_repaired(tmp_path: Path) -> None:
    admission = _admission_fixture(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    object.__setattr__(admission, "admitted_fixtures", ())

    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="supplied admission object differs from the exact semantic rebuild",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            artifact_bytes,
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )


def test_mutated_admission_safety_cannot_be_silently_repaired(tmp_path: Path) -> None:
    admission = _admission_fixture(tmp_path)
    artifact_bytes = canonical_reviewed_fixture_catalog_admission_bytes(admission)
    unsafe = dict(admission.safety)
    unsafe["bet_authorized"] = True
    object.__setattr__(admission, "safety", unsafe)

    with pytest.raises(
        ReviewedFixtureCatalogAdmissionArtifactError,
        match="supplied admission object differs from the exact semantic rebuild",
    ):
        verify_reviewed_fixture_catalog_admission_artifact(
            admission,
            artifact_bytes,
            verified_at=datetime.datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )
