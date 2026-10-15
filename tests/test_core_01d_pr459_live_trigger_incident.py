from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import audit_core_01d_pr459_live_trigger_incident as incident
from scripts import audit_app_01a_local_shell as app_history
from scripts import audit_core_01d_checkpoint_e_completion_v2 as pass_a_v2
from scripts import audit_core_01d_ci_offline_transport_boundary as a2
from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4
from scripts import audit_data_01c_restore_portability as d5
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_checkpoint_e_workflows as checkpoint
from scripts import audit_core_01d_checkpoint_e_completion as completion_v1



def _cache_test_document(tmp_path, monkeypatch):
    monkeypatch.setattr(a2, "ROOT", tmp_path)
    path = tmp_path / "cache.json"
    value = a2.seal({"schema_version": 1, "value": 1, "nested": {"rows": ["original"]}})
    path.write_bytes(a2.canonical(value))
    a2._authenticated_json_bytes.cache_clear()
    return path, value


def test_evidence_cache_returns_isolated_objects(tmp_path, monkeypatch):
    _, expected = _cache_test_document(tmp_path, monkeypatch)
    first = a2.read_generation("cache.json")
    first["nested"]["rows"][0] = "caller mutation"
    first["canonical_sha256"] = "0" * 64
    assert a2.read_generation("cache.json") == expected
    assert a2.read("cache.json") == expected


def test_evidence_cache_rereads_same_size_same_mtime_changes(tmp_path, monkeypatch):
    path, _ = _cache_test_document(tmp_path, monkeypatch)
    a2.read_generation("cache.json")
    stamp = path.stat()
    raw = path.read_bytes()
    changed = raw.replace(b'"value":1', b'"value":2')
    assert changed != raw and len(changed) == len(raw)
    path.write_bytes(changed)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    with pytest.raises(AssertionError, match="artifact self-hash mismatch"):
        a2.read_generation("cache.json")


@pytest.mark.parametrize("corruption", ["duplicate", "nonfinite"])
def test_evidence_cache_rejects_malformed_bytes_after_warmup(tmp_path, monkeypatch, corruption):
    path, _ = _cache_test_document(tmp_path, monkeypatch)
    a2.read("cache.json")
    raw = path.read_bytes()
    replacement = (b'"value":1,"value":1' if corruption == "duplicate" else b'"value":NaN')
    path.write_bytes(raw.replace(b'"value":1', replacement))
    reason = "duplicate JSON key" if corruption == "duplicate" else "nonfinite JSON"
    with pytest.raises(AssertionError, match=reason):
        a2.read("cache.json")


def test_evidence_cache_keeps_generation_canonicality_separate(tmp_path, monkeypatch):
    path, expected = _cache_test_document(tmp_path, monkeypatch)
    path.write_text(json.dumps(expected, indent=2) + "\n")
    assert a2.read("cache.json") == expected
    with pytest.raises(AssertionError, match="artifact self-hash mismatch"):
        a2.read_generation("cache.json")


def test_evidence_cache_rechecks_lineage_after_warmup(monkeypatch):
    a2.load_inventory_generations()
    target = a2.ROOT / a2.inventory_generation_path(2)
    changed = a2.read_generation(a2.inventory_generation_path(2))
    changed["predecessor_inventory"]["canonical_sha256"] = "0" * 64
    replacement = a2.canonical(a2.seal(changed))
    original = Path.read_bytes

    def tampered(path):
        return replacement if path == target else original(path)

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(AssertionError, match="predecessor canonical hash mismatch"):
        a2.load_inventory_generations()


def test_evidence_cache_cannot_hide_current_source_mutation(monkeypatch):
    a2.authenticate_inventory()
    target = a2.ROOT / incident.CREATE_WORKFLOW
    original = Path.read_bytes

    def tampered(path):
        raw = original(path)
        return raw + b"#unreviewed\n" if path == target else raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(AssertionError, match="source or process discovery drift"):
        a2.authenticate_inventory()


def test_both_direct_share_workflows_are_offline_only():
    for path in (incident.CREATE_WORKFLOW, incident.PROVE_WORKFLOW):
        workflow = incident._validate_workflow(path)
        assert workflow["permissions"] == {"contents": "read"}
        assert workflow["on"]["workflow_dispatch"]["inputs"]["validation_mode"]["options"] == [
            "offline_only"
        ]
        assert all(
            not any(marker.casefold() in str(step.get(key, "")).casefold()
                    for marker in incident.LIVE_MARKERS)
            for step in workflow["jobs"]["offline-validation"]["steps"]
            for key in ("run", "uses")
        )


def test_offline_workflow_successor_is_authenticated_by_current_evolution_projection():
    ledger = evolution.validate_current_state()
    assert evolution.current_workflow_tree_sha1(ledger) == evolution.PR459_OFFLINE_WORKFLOW_TREE_SHA1


def test_b4_historical_workflow_identity_and_receipt_remain_unchanged():
    for path, expected in b4.B4_WORKFLOW_PREDECESSORS.items():
        raw = b4._historical_b4_workflow_bytes(path)
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == b4.SOURCE_PINS[path][0]
        assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == b4.SOURCE_PINS[path][1]
        assert Path(b4.ROOT / expected).is_file()
    assert b4.audit()["result"] == "PASS"
    assert incident.audit()["canonical_sha256"] == incident.build_receipt()["canonical_sha256"]


def test_a2_successor_workflows_keep_their_immutable_pass_a_blob_pins():
    paths = set(a2.A2_SUCCESSOR_WORKFLOWS)
    assert paths == set(b4.B4_WORKFLOW_PREDECESSORS)
    assert paths <= a2.A2_PATHS
    assert pass_a_v2.pass_a_preserved_a2_successor_paths(a2) == paths
    assert pass_a_v2.pass_a_nonhistorical_a2_generation_paths(a2, paths) == set()
    for path in paths:
        assert pass_a_v2.PASS_A_HISTORICAL_BLOBS[path] == b4.SOURCE_PINS[path][0]


def test_checkpoint_census_reads_exact_predecessor_bytes():
    for path in b4.B4_WORKFLOW_PREDECESSORS:
        assert hashlib.sha256(checkpoint.read(path)).hexdigest() == b4.SOURCE_PINS[path][1]
    path = "tests/test_p4_3d_retirement_audit_extensibility.py"
    raw = checkpoint.read(path)
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == (
        "5e7de20231b2455f15fdc20c4fd21e1720714f64"
    )


def test_historical_v1_identity_reader_preserves_exact_workflow_pins_and_restores():
    module = pass_a_v2.review.retention.v4.v3
    original = module._source_identity
    with pass_a_v2.historical_v1_git_view():
        for path in b4.B4_WORKFLOW_PREDECESSORS:
            row = module._source_identity(path)
            assert (row["git_blob_sha1"], row["source_sha256"]) == b4.SOURCE_PINS[path]
    assert module._source_identity is original


@pytest.mark.parametrize("target", ["fixture", "current"])
def test_checkpoint_test_predecessor_cannot_hide_tampering(monkeypatch, target):
    path = "tests/test_p4_3d_retirement_audit_extensibility.py"
    fixture = checkpoint.PASS1_V1_BASE_SOURCE_FIXTURES[path][0]
    candidate = checkpoint.ROOT / (fixture if target == "fixture" else path)
    original = Path.read_bytes

    def tampered(source):
        raw = original(source)
        return raw + b"#unreviewed\n" if source == candidate else raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    reason = ("pinned Checkpoint E V1 source fixture drift" if target == "fixture"
              else "source or process discovery drift")
    with pytest.raises((ValueError, AssertionError), match=reason):
        checkpoint.read(path)


def test_v1_scope_rejects_a_forged_reviewed_workflow_blob():
    raw = completion_v1.policy.v4.v3._git("ls-tree", "-r", "HEAD")
    forged = []
    altered = 0
    for line in raw.splitlines(keepends=True):
        metadata, separator, path = line.partition(b"\t")
        if path.strip().decode() in b4.B4_WORKFLOW_PREDECESSORS:
            line = b"100644 blob " + b"0" * 40 + separator + path
            altered += 1
        forged.append(line)
    assert altered == 2
    with pytest.raises(completion_v1.policy.RetentionAcceptanceError,
                       match="PR459 source inventory identity is unverified"):
        completion_v1.validate_bounded_inventory(b"".join(forged))


def test_pass_a_projection_does_not_override_authenticated_predecessors():
    app_sources = {
        "scripts/audit_checkpoint_e_workflows.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
    }
    assert app_sources <= set(app_history.PATHS)
    assert not (app_sources & set(pass_a_v2.PASS_A_HISTORICAL_BLOBS))

    # These two rows already have stronger immutable predecessor owners. The
    # first is in D5's sealed source snapshot; the second is in both D5 and
    # the exact A2 V1 source fixture. Later main-source blobs cannot replace
    # those historic identities in the Pass-A projection.
    retained_status = "scripts/audit_core_01d_retained_workflow_status_v2.py"
    p4_evolution = "scripts/audit_p4_workflow_evolution_ledger.py"
    d5_sources = d5.snapshot()["sources"]
    assert d5_sources[retained_status]["git_blob_sha1"] == "26968a425f642910991332dba87519add8a0cc19"
    assert d5_sources[p4_evolution]["git_blob_sha1"] == "fdd2932200ed4467dca902fabe01dab76d5fe451"
    assert not ({retained_status, p4_evolution} & set(pass_a_v2.PASS_A_HISTORICAL_BLOBS))
    assert p4_evolution in d5.HISTORICAL_A2_SOURCE_FIXTURES


def test_tampered_b4_predecessor_fixture_fails(monkeypatch):
    path = incident.CREATE_WORKFLOW
    fixture = b4.ROOT / b4.B4_WORKFLOW_PREDECESSORS[path]
    original = Path.read_bytes

    def tampered(source):
        raw = original(source)
        return raw + b"#tampered\n" if Path(source) == fixture else raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    for reader in (b4._historical_b4_workflow_bytes, checkpoint.read):
        with pytest.raises(AssertionError, match="predecessor fixture identity mismatch"):
            reader(path)


def test_current_workflow_tampering_cannot_hide_behind_b4_fixture(monkeypatch):
    path = incident.PROVE_WORKFLOW
    source = b4.ROOT / path
    original = Path.read_bytes

    def tampered(candidate):
        raw = original(candidate)
        return raw + b"#unreviewed\n" if Path(candidate) == source else raw

    monkeypatch.setattr(Path, "read_bytes", tampered)
    for reader in (b4._historical_b4_workflow_bytes, checkpoint.read):
        with pytest.raises(AssertionError, match="differs from latest A2"):
            reader(path)


def test_shallow_projection_does_not_request_the_historical_b4_base(monkeypatch):
    original = b4._git

    def reject_base_lookup(*args: str) -> bytes:
        assert b4.BASE_MAIN not in args
        return original(*args)

    monkeypatch.setattr(b4, "_git", reject_base_lookup)
    assert b4.audit()["result"] == "PASS"
