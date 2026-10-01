"""PORT-02C build-allowlist and staged-manifest tests (offline, dev-only)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

from scripts.port_02c_build_config import (
    BANNED_FROZEN_MODULES,
    QUALIFICATION_FIXTURE_PREFIXES,
    SLICE_CLOSED_WORLD_ROOTS,
    SLICE_RESOURCES,
)
from runtime.release_identity import (
    MANIFEST_POLICY_ID,
    MANIFEST_SCHEMA_VERSION,
    RESOURCE_ROLES,
    verify_installed_release,
)

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args], cwd=str(ROOT), shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")[:300]
    return completed.stdout


def test_slice_allowlist_is_exact_and_safe():
    assert SLICE_CLOSED_WORLD_ROOTS == tuple(sorted(set(SLICE_CLOSED_WORLD_ROOTS)))
    assert len({item.casefold() for item in SLICE_CLOSED_WORLD_ROOTS}) == len(SLICE_CLOSED_WORLD_ROOTS)
    for left_index, left in enumerate(SLICE_CLOSED_WORLD_ROOTS):
        for right in SLICE_CLOSED_WORLD_ROOTS[left_index + 1 :]:
            assert not right.startswith(left + "/")

    seen: set[str] = set()
    for rel, role in SLICE_RESOURCES:
        assert rel not in seen
        seen.add(rel)
        assert role in RESOURCE_ROLES
        parts = PurePosixPath(rel).parts
        assert ".." not in parts and not rel.startswith("/")
        lowered = rel.casefold()
        assert ".git" not in lowered and ".venv" not in lowered
        assert "/tests/" not in f"/{lowered}" and not lowered.startswith("tests/")
        assert not lowered.endswith(".env") and ".env." not in lowered
        assert (ROOT / PurePosixPath(rel)).is_file()
        assert not (ROOT / PurePosixPath(rel)).is_symlink()
        mode = _git("ls-files", "-s", "--", rel).decode("utf-8").strip().split()[0]
        assert mode in ("100644", "100755"), rel
        status = _git("status", "--porcelain", "--", rel).decode("utf-8").strip()
        assert status == "", rel


def test_banned_frozen_modules_cover_tests():
    assert "pytest" in BANNED_FROZEN_MODULES
    assert "tests" in BANNED_FROZEN_MODULES
    for spec in ("packaging/windows/athena-port02c.spec", "packaging/linux/athena-port02c.spec"):
        text = (ROOT / spec).read_text(encoding="utf-8")
        assert "exclude_binaries=True" in text
        for banned in ("pytest", "_pytest", '"tests"'):
            assert banned in text, spec
        assert "shell=True" not in text
        for hidden in (
            "domain.historical_training_coverage",
            "domain.historical_asof_features",
            "domain._historical_training_coverage_impl",
            "domain._historical_training_coverage_post_hardening",
            "domain._historical_training_coverage_row_issuance",
            "domain._historical_asof_features_impl",
        ):
            assert hidden in text, spec


def test_staged_bundle_verifies_and_tamper_fails(tmp_path: Path):
    from scripts import build_dev_bundle

    bundle = tmp_path / "bundle"
    metadata = build_dev_bundle.build(
        repo=ROOT, platform_tag="windows" if sys.platform == "win32" else "linux", output=bundle, freeze=False
    )
    manifest_bytes = (bundle / "release-manifest.json").read_bytes()
    assert metadata["trusted_manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["policy_id"] == MANIFEST_POLICY_ID
    assert manifest["platform_tag"] == ("windows" if sys.platform == "win32" else "linux")

    identity = verify_installed_release(bundle, metadata["trusted_manifest_sha256"])
    assert identity.manifest_sha256 == metadata["trusted_manifest_sha256"]
    assert any(record.role == "CANONICAL_COMPONENT_SOURCE" for record in identity.resources)
    assert any(record.role == "AUTHORITY_REGISTRY" for record in identity.resources)

    victim = bundle / manifest["resources"][0]["payload_path"]
    original = victim.read_bytes()
    try:
        victim.write_bytes(original + b"\n")
        with pytest.raises(Exception):
            verify_installed_release(bundle, metadata["trusted_manifest_sha256"])
    finally:
        victim.write_bytes(original)
    verify_installed_release(bundle, metadata["trusted_manifest_sha256"])

    assert (bundle / "build-metadata.json").is_file()
    assert (bundle / "qualification" / "qualification-manifest.json").is_file()
    assert metadata["qualification_file_count"] >= len(QUALIFICATION_FIXTURE_PREFIXES)
    from scripts.port_02c_offline_composed_replay import STAGED_FIXTURE_ROOT, verify_fixture_manifest

    verify_fixture_manifest(bundle / "qualification" / STAGED_FIXTURE_ROOT)
    assert metadata["pyinstaller_reviewed_data_resources"] == build_dev_bundle.validate_reviewed_data_resources(ROOT)
    qualification = json.loads((bundle / "qualification/qualification-manifest.json").read_bytes())
    assert all(row["staged_name"].startswith("retained/") for row in qualification["files"])
