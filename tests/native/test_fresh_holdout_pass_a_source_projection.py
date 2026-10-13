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
from scripts import audit_run_02a_pre_durable_share_send as share

PATHS = tuple(review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES)
ORIGINAL_ROOT = review.ROOT
WRAPPER_TEST = "tests/test_fotmob_fresh_holdout_duplicate_group_wrapper.py"

@pytest.fixture(scope="module")
def sealed():
    return a2.authenticate_inventory()

@pytest.fixture
def checkout(tmp_path, monkeypatch, sealed, request):
    original = review.ROOT
    paths = set(PATHS) | set(share.RETAINED_AUDIT_PREDECESSORS) | {v[0] for v in share.RETAINED_AUDIT_PREDECESSORS.values()} | {share.RECEIPT_PATH, a2.inventory_generation_path(154)} | {v[0] for v in review.FRESH_HOLDOUT_20261014_PREDECESSOR_SOURCES.values()} | {review.INVENTORY_PATH, WRAPPER_TEST}
    for logical in paths:
        target = tmp_path / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / logical, target)
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path)
    git("init", "-q")
    params = getattr(getattr(request.node, "callspec", None), "params", {})
    omitted = params.get("path") if params.get("mutation") == "untracked" else None
    if params.get("mutation") == "fixture_untracked":
        omitted = share.RETAINED_AUDIT_PREDECESSORS[params["path"]][0]
    git("add", "--", *sorted(paths - {omitted}))
    git("-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "Exact current files; no historical ancestor")
    monkeypatch.setattr(review, "ROOT", tmp_path)
    monkeypatch.setattr(checkpoint, "ROOT", tmp_path)
    monkeypatch.setattr(share, "ROOT", tmp_path)
    monkeypatch.setattr(a2, "ROOT", tmp_path)
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
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        share.historical_prerequisite_source_bytes(path)

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

@pytest.mark.parametrize("path", [WRAPPER_TEST])
@pytest.mark.parametrize("mutation", ["none", "current", "committed_current", "symlink", "untracked", "missing"])
def test_historical_wrapper_test_tree_identity_authenticates_current_source(checkout, path, mutation):
    root, git = checkout
    current = root / path
    if mutation in {"current", "committed_current"}:
        current.write_bytes(current.read_bytes() + b"# unauthorized mutation\n")
        if mutation == "committed_current":
            git("add", path)
            git("-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "Unsealed test mutation")
    elif mutation == "missing":
        current.unlink()
    elif mutation == "symlink":
        target = root / "outside.txt"
        target.write_bytes(current.read_bytes())
        current.unlink()
        try:
            current.symlink_to(target)
        except OSError:
            pytest.skip("Native account lacks symlink privilege")
    if mutation == "none":
        raw = (ORIGINAL_ROOT / checkpoint.BASE_PATH).read_bytes()
        assert checkpoint.sha(raw) == checkpoint.BASE_INPUT_SHA
        expected = checkpoint.strict(raw)["files"][path]
        assert checkpoint._fresh_holdout_20261014_test_identity() == expected
    else:
        with pytest.raises((AssertionError, RuntimeError, ValueError, OSError)):
            checkpoint._fresh_holdout_20261014_test_identity()

@pytest.mark.parametrize("path", tuple(share.RETAINED_AUDIT_PREDECESSORS))
@pytest.mark.parametrize("mutation", ["none", "fixture", "missing", "crosswired", "current", "committed_current", "untracked", "fixture_untracked", "symlink"])
def test_retained_pr459_source_cannot_hide_current_or_fixture_mutation(checkout, sealed, path, mutation):
    root, git = checkout
    fixture, blob, digest = share.RETAINED_AUDIT_PREDECESSORS[path]
    target = root / fixture
    if mutation == "fixture":
        target.write_bytes(target.read_bytes() + b"# mutation\n")
    elif mutation == "missing":
        target.unlink()
    elif mutation == "crosswired":
        other = next(p for p in share.RETAINED_AUDIT_PREDECESSORS if p != path)
        target.write_bytes((root / share.RETAINED_AUDIT_PREDECESSORS[other][0]).read_bytes())
    elif mutation in {"current", "committed_current"}:
        current = root / path
        current.write_bytes(current.read_bytes() + b"# unsealed mutation\n")
        if mutation == "committed_current":
            git("add", path)
            git("-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "Unsealed audit mutation")
    elif mutation == "symlink":
        outside = root / "outside.txt"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError:
            pytest.skip("Native account lacks symlink privilege")
    if mutation == "none":
        raw = share.historical_prerequisite_source_bytes(path, latest=sealed)
        assert hashlib.sha256(raw).hexdigest() == digest
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == blob
        receipt = json.loads((root / share.RECEIPT_PATH).read_bytes())
        assert receipt["source_identities"][path] == digest
    else:
        with pytest.raises((AssertionError, RuntimeError, ValueError, OSError)):
            share.historical_prerequisite_source_bytes(path, latest=sealed)


def test_retained_pr459_receipt_authenticates_without_repinning():
    raw = (share.ROOT / share.RECEIPT_PATH).read_bytes()
    assert share.audit()["canonical_sha256"] == "a62a8847dad208f1ed1c9bcd8cdcb36cf21b576b8528d2aaf6ca23209db5c22e"
    assert (share.ROOT / share.RECEIPT_PATH).read_bytes() == raw


def test_retained_pr459_write_mode_is_rejected_before_mutation(checkout, monkeypatch):
    import sys
    root, _ = checkout
    before = (root / share.RECEIPT_PATH).read_bytes()
    monkeypatch.setattr(sys, "argv", ["audit_run_02a_pre_durable_share_send.py", "--write"])
    with pytest.raises(SystemExit, match="immutable"):
        share.main()
    assert (root / share.RECEIPT_PATH).read_bytes() == before

@pytest.mark.parametrize("mutation", ["source_head", "counter", "generation"])
def test_retained_pr459_receipt_reseal_cannot_change_history(checkout, mutation):
    root, _ = checkout
    path = root / share.RECEIPT_PATH
    value = json.loads(path.read_bytes())
    if mutation == "source_head":
        value["source_head"] = "0" * 40
    elif mutation == "counter":
        value["source_review_counter_while_unmerged"] = "4/5"
    else:
        value["a2"]["generation"] = 161
    path.write_bytes(share.canonical(share.seal(value)))
    with pytest.raises(AssertionError, match="source/evidence drift"):
        share.audit()
