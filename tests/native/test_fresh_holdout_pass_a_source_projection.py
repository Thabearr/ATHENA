"""Native Git/filesystem authentication of the exact historical Pass-A view."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from scripts import audit_core_01d_authority_reachability_review_a as review
from scripts import audit_core_01d_ci_offline_transport_boundary as a2
from scripts import audit_checkpoint_e_workflows as checkpoint

PATHS = tuple(review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES)

@pytest.fixture(scope="module")
def sealed():
    return a2.authenticate_inventory()

@pytest.fixture
def checkout(tmp_path, monkeypatch, sealed, request):
    original = review.ROOT
    paths = set(PATHS) | {v[0] for v in review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES.values()} | {review.INVENTORY_PATH}
    for logical in paths:
        target = tmp_path / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / logical, target)
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path)
    git("init", "-q")
    params = getattr(getattr(request.node, "callspec", None), "params", {})
    omitted = params.get("path") if params.get("mutation") == "untracked" else None
    git("add", "--", *sorted(paths - {omitted}))
    git("-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "Exact current files; no historical ancestor")
    monkeypatch.setattr(review, "ROOT", tmp_path)
    monkeypatch.setattr(checkpoint, "ROOT", tmp_path)
    monkeypatch.setattr(a2, "authenticate_inventory", lambda: sealed)
    review._tracked_payloads.cache_clear()
    return tmp_path, git

@pytest.mark.parametrize("path", PATHS)
def test_exact_predecessor_without_historical_ancestor(checkout, path):
    root, git = checkout
    fixture, blob, digest = review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES[path]
    raw = review.source_bytes(path)
    assert hashlib.sha256(raw).hexdigest() == digest
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == blob
    # The exact source blobs are supplied by fixtures; no historical ancestor commit exists.
    assert git("rev-list", "--count", "HEAD").strip() == b"1"
    assert git("rev-parse", "HEAD:" + path).strip().decode() != blob
    (root / fixture).write_bytes(raw.replace(b"\n", b"\r\n"))
    assert review.source_bytes(path) == raw
    assert checkpoint.read(path) == raw

@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("mutation", ["fixture", "missing", "crosswired", "current", "committed_current", "untracked", "symlink"])
def test_tampering_cannot_hide_behind_historical_fixture(checkout, path, mutation):
    root, git = checkout
    fixture = root / review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES[path][0]
    current = root / path
    if mutation == "fixture":
        fixture.write_bytes(fixture.read_bytes() + b"# changed\n")
    elif mutation == "missing":
        fixture.unlink()
    elif mutation == "crosswired":
        other = next(p for p in PATHS if p != path)
        fixture.write_bytes((root / review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES[other][0]).read_bytes())
    elif mutation in {"current", "committed_current"}:
        current.write_bytes(current.read_bytes() + b"# unauthorized mutation\n")
        if mutation == "committed_current":
            git("add", path)
            git("-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "Unsealed mutation")
    elif mutation == "untracked":
        assert path not in git("ls-files").decode().splitlines()
    else:
        target = root / "outside.txt"
        target.write_bytes(fixture.read_bytes())
        fixture.unlink()
        try:
            fixture.symlink_to(target)
        except OSError:
            pytest.skip("Native account lacks symlink privilege")
    with pytest.raises((AssertionError, RuntimeError, ValueError, OSError)):
        review.source_bytes(path)
    with pytest.raises((AssertionError, RuntimeError, ValueError, OSError)):
        checkpoint.read(path)

@pytest.mark.parametrize("path", ["../outside.py", "/absolute.py", "domain/unclassified.py"])
def test_no_generic_historical_substitution(checkout, path):
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        review._fresh_holdout_predecessor_source(path)
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        checkpoint._fresh_holdout_20261014_source(path)

def test_frozen_inventory_rederives_without_current_edge_drift():
    assert review.build_inventory() == review.read_json(review.INVENTORY_PATH)
    for path in review.INCIDENT_20261010_PREDECESSOR_SOURCES:
        assert review.source_bytes(path)

def test_retained_capture_timestamps_match_original_manifest_bytes():
    from domain import fotmob_fresh_holdout_capture_qualification_adapter as adapter
    rows = adapter.adapter_receipt()["afc_cl2_direct_duplicate_group_20261014_reviewed_shape"]["capture_lineages"]
    directory = review.ROOT / "tests/fixtures/fotmob_fresh_holdout_20261014"
    for row in rows:
        raw = (directory / (row["capture_id"] + "-manifest.json")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["manifest_sha256"]
        retained = json.loads(raw)
        assert retained["observed_at"] == row["observed_at"]
        assert retained["raw_sha256"] == row["raw_sha256"]
    assert rows[1]["observed_at"] == "2026-10-13T08:55:14.551847Z"
