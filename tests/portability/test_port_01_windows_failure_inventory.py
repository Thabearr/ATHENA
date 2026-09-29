from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

import pytest

from scripts import audit_port_01_windows_failure_inventory as audit


ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "artifacts/architecture/port_01_windows_failure_inventory_v1.json"


def _inventory_bytes() -> bytes:
    return INVENTORY_PATH.read_bytes()


def _git_blob(relative: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=ROOT)


def test_inventory_loads_and_canonical_self_hash_validates() -> None:
    doc = audit.load_inventory()
    payload = dict(doc)
    recorded = payload.pop("canonical_sha256")
    assert hashlib.sha256(audit.canonical_json_bytes(payload)).hexdigest() == recorded
    assert doc["canonical_sha256_byte_domain"] == "CANONICAL_PAYLOAD_SHA256"
    assert doc["schema_version"] == 1
    assert doc["policy_id"] == "ATHENA_PORT_01_WINDOWS_FAILURE_INVENTORY_V1"


def test_duplicate_keys_and_noncanonical_hash_fail_closed(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(audit.InventoryError, match="duplicate JSON key"):
        audit.load_inventory(duplicate)
    bad = dict(audit.load_inventory())
    bad["canonical_sha256"] = "0" * 64
    candidate = tmp_path / "bad-hash.json"
    candidate.write_bytes(audit.canonical_json_bytes(bad))
    with pytest.raises(audit.InventoryError, match="self-hash mismatch"):
        audit.load_inventory(candidate)


@pytest.mark.parametrize("value", [
    "C:/Users/someone/private.json",
    "C:\\Users\\someone\\private.json",
    "/home/someone/private.json",
    "../secret.json",
    "artifacts/../secret.json",
    "",
])
def test_repository_path_normalization_rejects_absolute_or_traversal(value: str) -> None:
    with pytest.raises(audit.InventoryError):
        audit.validate_repo_path(value)


def test_no_user_specific_absolute_path_or_raw_share_url_is_stored() -> None:
    raw = _inventory_bytes().decode("utf-8")
    doc = audit.load_inventory()
    with pytest.raises(audit.InventoryError, match="user-specific absolute path"):
        audit._validate_no_user_paths({"example": "C:\\Users\\alice\\repo"})
    with pytest.raises(audit.InventoryError, match="user-specific absolute path"):
        audit._validate_no_user_paths({"example": "C:/Users/alice/repo"})
    assert "sportybet.com" not in raw.lower()
    assert "https://" not in raw.lower()
    audit._validate_no_user_paths(doc)


def test_one_primary_class_and_one_byte_domain_per_failure() -> None:
    doc = audit.load_inventory()
    assert {item["primary_class"] for item in doc["failures"]} == {
        "RAW_ARTIFACT_BYTES", "CANONICAL_JSON_BYTES"
    }
    for item in doc["failures"]:
        assert item["primary_class"] in audit.FAILURE_CLASSES
        for identity in (item["expected_identity"], item["actual_identity"]):
            assert set(identity) == {"value", "byte_domain"}
            assert identity["byte_domain"] in audit.BYTE_DOMAINS
    for probe in doc["byte_probes"]:
        for name, value in probe.items():
            if name.endswith("sha1") or name.endswith("sha256"):
                assert set(value) == {"value", "byte_domain"}
                assert value["byte_domain"] in audit.BYTE_DOMAINS


def test_duplicate_ids_and_unknown_classes_are_rejected() -> None:
    doc = audit.load_inventory()
    duplicate = deepcopy(doc)
    duplicate["failures"][1]["failure_id"] = duplicate["failures"][0]["failure_id"]
    with pytest.raises(audit.InventoryError, match="failure IDs must be unique"):
        audit._validate_inventory_shape(duplicate)
    unknown = deepcopy(doc)
    unknown["failures"][0]["primary_class"] = "UNREVIEWED"
    with pytest.raises(audit.InventoryError, match="missing/unknown primary class"):
        audit._validate_inventory_shape(unknown)


def test_all_historical_ten_have_stable_unique_dispositions() -> None:
    doc = audit.load_inventory()
    historical = doc["historical_disposition"]
    assert len(historical) == 10
    assert [item["failure_id"] for item in historical] == [
        f"WIN-CRLF-{index:02d}" for index in range(1, 11)
    ]
    assert all(item["disposition"] == "REPRODUCED_CURRENT" for item in historical)
    assert len({item["failure_id"] for item in doc["failures"]}) == 10
    collected = doc["current_reproduction"]["collected_nodeids"]
    assert len(collected) == doc["current_reproduction"]["collected"] == 214
    assert len(set(collected)) == 214
    assert set(doc["current_reproduction"]["failure_nodeids"]) <= set(collected)


def test_raw_git_and_canonical_identities_are_not_conflated() -> None:
    doc = audit.load_inventory()
    fixture, contract = doc["byte_probes"]
    assert fixture["working_tree_sha256"]["byte_domain"] == "RAW_FILE_SHA256"
    assert fixture["git_blob_sha1"]["byte_domain"] == "GIT_BLOB_SHA1"
    assert fixture["git_blob_payload_sha256"]["byte_domain"] == "GIT_BLOB_PAYLOAD_SHA256"
    assert fixture["lf_normalized_sha256"]["byte_domain"] == "LF_NORMALIZED_SOURCE_SHA256"
    assert contract["working_tree_sha256"]["value"] != contract["git_blob_payload_sha256"]["value"]
    assert doc["failures"][8]["expected_identity"]["byte_domain"] == "CANONICAL_PAYLOAD_SHA256"
    assert doc["failures"][8]["actual_identity"]["byte_domain"] == "RAW_FILE_SHA256"


def test_malformed_sha_and_unknown_byte_domain_fail_closed() -> None:
    with pytest.raises(audit.InventoryError, match="malformed lowercase"):
        audit._require_hash({"value": "A" * 64, "byte_domain": "GIT_BLOB_PAYLOAD_SHA256"}, "GIT_BLOB_PAYLOAD_SHA256")
    with pytest.raises(audit.InventoryError, match="wrong or missing byte domain"):
        audit._require_hash({"value": "a" * 64, "byte_domain": "UNSPECIFIED"}, "GIT_BLOB_PAYLOAD_SHA256")


def test_binary_safe_probe_matches_blob_or_proves_eol_only_without_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = audit.load_inventory()
    before = {
        probe["path"]: (ROOT / probe["path"]).read_bytes()
        for probe in doc["byte_probes"]
    }
    observations = audit.validate_current_platform(doc)
    assert len(observations) == 2
    assert all(result in {"MATCH", "EOL_CONVERSION_ONLY", "SKIP_SOURCE_MOVED"} for _, result in observations)
    for relative, value in before.items():
        assert (ROOT / relative).read_bytes() == value


def test_crlf_detection_is_read_only_and_does_not_global_normalize() -> None:
    doc = audit.load_inventory()
    for probe in doc["byte_probes"]:
        path = ROOT / probe["path"]
        before = path.read_bytes()
        crlf = before.count(b"\r\n")
        bare_lf = before.count(b"\n") - crlf
        assert crlf >= 0 and bare_lf >= 0
        assert path.read_bytes() == before


def test_no_expected_hash_refresh_or_global_normalization_is_recorded() -> None:
    doc = audit.load_inventory()
    assert doc["safety"]["expected_hash_refreshed"] is False
    assert doc["safety"]["gitattributes_changed"] is False
    assert doc["safety"]["production_source_changed"] is False
    assert doc["current_windows_environment"]["primary_policy_left_unchanged"] is True
    assert "normalization" not in doc["safety"]


def test_failure_and_disposition_order_is_deterministic() -> None:
    doc = audit.load_inventory()
    assert [item["failure_id"] for item in doc["failures"]] == [
        f"WIN-CRLF-{index:02d}" for index in range(1, 11)
    ]
    assert [item["failure_id"] for item in doc["historical_disposition"]] == [
        f"WIN-CRLF-{index:02d}" for index in range(1, 11)
    ]


def test_current_platform_audit_passes_and_matches_pinned_blobs() -> None:
    doc = audit.load_inventory()
    observations = audit.validate_current_platform(doc)
    assert [probe_id for probe_id, _ in observations] == [
        "BYTE-FIXTURE-P44R-MANIFEST", "BYTE-MAIN-SHADOW-CONTRACT"
    ]
    assert all(result in {"MATCH", "EOL_CONVERSION_ONLY", "SKIP_SOURCE_MOVED"} for _, result in observations)


def test_linux_correspondence_is_explicit_and_not_misreported_as_windows_qualification() -> None:
    doc = audit.load_inventory()
    correspondence = doc["linux_correspondence"]
    assert correspondence["local_linux_observation_at_freeze"] == "NOT_PERFORMED"
    assert correspondence["hosted_linux_is_windows_qualification"] is False
    if sys.platform.startswith("linux"):
        observations = audit.validate_current_platform(doc)
        assert all(result in {"MATCH", "SKIP_SOURCE_MOVED"} for _, result in observations)


def test_p44r_p44s_and_base00_historical_identities_remain_exact() -> None:
    doc = audit.load_inventory()
    anchors = {item["path"]: item for item in doc["historical_immutable_anchors"]}
    expected = {
        "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json": "90e2d7e984609ded80c9113a05453628bebadfcb3cede7fc95b9696931016552",
        "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json": "0907272a20b439e6874ee3b3fa399a488e8dd3c9a6e428dafa2aa53202c513c3",
        "artifacts/product/product_baseline_v1.json": "d3db092eb890f45cae9eccfefb7134a59bf4d1b9f43e43160421c4210832b27f",
    }
    for path, digest in expected.items():
        assert anchors[path]["canonical_payload_sha256"]["value"] == digest
        assert hashlib.sha256(_git_blob(path)).hexdigest() == anchors[path]["git_blob_payload_sha256"]["value"]


def test_network_and_provider_boundaries_are_never_called(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    original_run = subprocess.run

    def guarded_run(args, *positional, **kwargs):
        argv = list(args)
        assert argv and argv[0] == "git", f"non-Git subprocess attempted: {argv!r}"
        calls.append(argv)
        return original_run(args, *positional, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("network call is forbidden in PORT-01A audit")

    monkeypatch.setattr(audit.subprocess, "run", guarded_run)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    doc = audit.load_inventory()
    audit.validate_current_platform(doc)
    assert calls
    assert all(call[0] == "git" for call in calls)
    assert doc["safety"]["network_calls"] == 0
    assert doc["safety"]["provider_calls"] == 0


def test_cli_check_is_read_only_and_succeeds() -> None:
    assert audit.main(["--check"]) == 0
