"""Exact static data closure; distinct from retained provider-run evidence."""
from pathlib import Path
from types import SimpleNamespace
import runpy

import pytest

from scripts import build_dev_bundle as builder
from scripts.port_02c_build_config import PYINSTALLER_REVIEWED_DATA_RESOURCES, QUALIFICATION_FIXTURE_PREFIXES, SLICE_RESOURCES

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "artifacts/research-manifests/sportybet-ng-early-payout-settlement-source-evidence-v1.json"
SHA = "af371490fb3e72dc9b5d3422a6b36af28ff4246ee6ead23b0c957e26c398afe4"


def test_exact_static_allowlist_and_tracked_clean_bytes():
    assert PYINSTALLER_REVIEWED_DATA_RESOURCES == ((SOURCE, "artifacts/research-manifests", 2059, SHA),)
    assert builder.validate_reviewed_data_resources(ROOT) == [{
        "source_path": SOURCE, "destination": "artifacts/research-manifests",
        "byte_size": 2059, "byte_sha256": SHA,
        "source_git_blob_sha1": "d74161304e154921bd9cf73230c872d60ac49805",
    }]
    assert not any(SOURCE.startswith(p) for p in QUALIFICATION_FIXTURE_PREFIXES)
    assert SOURCE not in {p for p, _ in SLICE_RESOURCES}
    registry = "config/architecture/component-authority-registry-v1.json"
    assert (registry, "AUTHORITY_REGISTRY") in SLICE_RESOURCES
    assert registry not in {p for p, _, _, _ in PYINSTALLER_REVIEWED_DATA_RESOURCES}


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_specs_collect_exact_static_data_once(platform):
    analyses = []
    def analysis(scripts, **kwargs):
        analyses.append(kwargs)
        return SimpleNamespace(pure=[], zipped_data=[], scripts=[], binaries=[], zipfiles=[], datas=kwargs["datas"])
    spec = ROOT / "packaging" / platform / "athena-port02c.spec"
    runpy.run_path(str(spec), init_globals={
        "SPECPATH": str(spec.parent), "Analysis": analysis,
        "PYZ": lambda *a, **k: None, "EXE": lambda *a, **k: None,
        "COLLECT": lambda *a, **k: None,
    })
    exact = (str(ROOT / SOURCE), "artifacts/research-manifests")
    assert analyses[2]["datas"] == [exact]
    assert sum(data.count(exact) for data in (a["datas"] for a in analyses)) == 1
    text = spec.read_text(encoding="utf-8")
    assert "collect_data_files" not in text
    assert "artifacts/**" not in text and "research-manifests/**" not in text


def test_wrong_expected_sha_rejected(monkeypatch):
    monkeypatch.setattr(builder, "PYINSTALLER_REVIEWED_DATA_RESOURCES", ((SOURCE, "artifacts/research-manifests", 2059, "0" * 64),))
    with pytest.raises(SystemExit, match="size/SHA mismatch"):
        builder.validate_reviewed_data_resources(ROOT)


def test_tampered_checkout_bytes_rejected(tmp_path, monkeypatch):
    original = (ROOT / SOURCE).read_bytes()
    path = tmp_path / SOURCE
    path.parent.mkdir(parents=True)
    path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    monkeypatch.setattr(builder, "_require_clean_tracked", lambda *a: (original, "d74161304e154921bd9cf73230c872d60ac49805"))
    with pytest.raises(SystemExit, match="checkout bytes differ"):
        builder.validate_reviewed_data_resources(tmp_path)
