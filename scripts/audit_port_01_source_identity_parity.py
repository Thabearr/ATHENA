#!/usr/bin/env python3
"""Validate the PORT-01B byte/source identity contract offline and read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from runtime.source_identity import (
    SourceIdentityError,
    canonical_payload_sha256,
    read_tracked_head_blob,
    validate_repository_relative_path,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_RELATIVE_PATH = "artifacts/architecture/port_01_source_identity_parity_v1.json"
ARTIFACT_PATH = ROOT / ARTIFACT_RELATIVE_PATH
POLICY_ID = "ATHENA_PORT_01_SOURCE_IDENTITY_PARITY_V1"
BASE_MAIN_SHA = "3da28cf4ac856b2dade041bb0675fdcfc17796ea"
B1_POLICY_ID = "ATHENA_PORT_01_WINDOWS_FAILURE_INVENTORY_V1"
B1_CANONICAL_SHA256 = "78b92cde4681d3bbd71007ed4c3e434717c029f6745b3b37ecb93bb917738966"
B1_GIT_BLOB_SHA1 = "6ff6fd3153419e7dae7f789401dc1b757d207126"
B1_FAILURE_IDS = tuple(f"WIN-CRLF-{number:02d}" for number in range(1, 11))
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

IDENTITY_CONTRACT = {
    "RAW_FILE_SHA256": (
        "SHA-256 of exact materialized file bytes; no Git lookup, text translation, "
        "or newline normalization."
    ),
    "CANONICAL_PAYLOAD_SHA256": (
        "SHA-256 of bytes emitted by the named canonical serializer; bytes are not repaired."
    ),
    "GIT_BLOB_SHA1": (
        "Git object SHA-1 for the exact tracked HEAD blob after repository clean filters."
    ),
    "GIT_BLOB_PAYLOAD_SHA256": (
        "SHA-256 of exact unfiltered payload bytes returned for HEAD:path."
    ),
    "FILTERED_WORKTREE_GIT_BLOB_EQUIVALENCE": (
        "Proof that git hash-object --path=<logical-path> --filters <worktree-file> "
        "equals the HEAD blob SHA-1 before source-controlled HEAD bytes are used."
    ),
    "INSTALLED_PAYLOAD_SHA256": "NOT_IMPLEMENTED_PORT_02A",
}

EXPECTED_ANCHORS = (
    {
        "anchor_id": "P44R_RECEIPT",
        "path": "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json",
        "git_blob_sha1": "0ed10b25f57a87037bf2d786a8f2ec77b0b2f55f",
        "git_blob_payload_sha256": "965f42e56823de78013c40a5b839ea81d0d5c79aadb4a02bc122110014a51eab",
        "canonical_sha256": "90e2d7e984609ded80c9113a05453628bebadfcb3cede7fc95b9696931016552",
    },
    {
        "anchor_id": "P44S_RECEIPT",
        "path": "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json",
        "git_blob_sha1": "a8368721e2181e44a54bce25aae6171df11b6b40",
        "git_blob_payload_sha256": "78ee27a58dff7c9c22ca7aee6740d9aa35bcc7d655aa9e2ad0a6ff4047ad8d8e",
        "canonical_sha256": "0907272a20b439e6874ee3b3fa399a488e8dd3c9a6e428dafa2aa53202c513c3",
    },
    {
        "anchor_id": "BASE00_JSON",
        "path": "artifacts/product/product_baseline_v1.json",
        "git_blob_sha1": "a37c079b9175c1e24ac098b87fd6bc28e23e9527",
        "git_blob_payload_sha256": "c171cc6adf713d4c4ec97a0f23eb73ae3ac48abc472e71db9afbd33fbd0013a3",
        "canonical_sha256": "d3db092eb890f45cae9eccfefb7134a59bf4d1b9f43e43160421c4210832b27f",
    },
    {
        "anchor_id": "BASE00_MARKDOWN",
        "path": "docs/product/athena_product_baseline_v1.md",
        "git_blob_sha1": "e20bd828d3b7a3d3305021492074be111d22c096",
        "git_blob_payload_sha256": "7139bf5583273d717eb8bca32a06066ab4f4e1178e2a79acc6517b4d23f44a5b",
        "canonical_sha256": None,
    },
    {
        "anchor_id": "P05_RUNTIME_ARTIFACT",
        "path": "artifacts/architecture/runtime-reachability-v1.json",
        "git_blob_sha1": "0c840c9b245d0eb8610a62ac3cc8bbc3be1120a1",
        "git_blob_payload_sha256": "a8ccb4c0c8ab2bea9bd133bb7fa7e155957bf1e38e5bf7ae6cccb4f44640f7e4",
        "canonical_sha256": None,
    },
    {
        "anchor_id": "PORT01A_INVENTORY",
        "path": "artifacts/architecture/port_01_windows_failure_inventory_v1.json",
        "git_blob_sha1": B1_GIT_BLOB_SHA1,
        "git_blob_payload_sha256": "b6958170ab20752656d40a8809563fe939c2875a34d88366430af216536d5aec",
        "canonical_sha256": B1_CANONICAL_SHA256,
    },
    {
        "anchor_id": "PARITY_CONTRACT",
        "path": "config/architecture/main-shadow-authority-parity-v1.json",
        "git_blob_sha1": "034985b0f750550a30369b2cfa295db1ce0ec13d",
        "git_blob_payload_sha256": "d4f525a0eb8d3ffe07e5b64a3452d758bc9e180c5b1db37feecbac1faf395bfe",
        "canonical_sha256": "d4f525a0eb8d3ffe07e5b64a3452d758bc9e180c5b1db37feecbac1faf395bfe",
    },
    {
        "anchor_id": "RAW_QUOTE_VERIFIER",
        "path": "domain/sportybet_live_event_quote_evidence.py",
        "git_blob_sha1": "096d54fe7493f6d81cdf3c4af7c4a9333c75fadc",
        "git_blob_payload_sha256": "5d64143321e12313bb239b6d3973c8b5da5fb28855649e9890194f233ff0b48f",
        "canonical_sha256": None,
    },
    {
        "anchor_id": "GIT_ATTRIBUTES",
        "path": ".gitattributes",
        "git_blob_sha1": "39ccd8d38ce17c105a906e2f1416f68e64fcc862",
        "git_blob_payload_sha256": "8a9b99b2c7eadeb2562f6f5cb57f0b5523be99c8a535c83a6a86f29082dd3559",
        "canonical_sha256": None,
    },
)

EXPECTED_SOURCE_BEFORE = {
    "domain/canonical_core.py": (
        "7a693a9bc7bf869da7089d96d21f408cc7c2bf97",
        "ce077495c34508a9823d35ac649cae1ee7bfa481d6002dfb1661a676e8d4c529",
    ),
    "runtime/__init__.py": (None, None),
    "runtime/source_identity.py": (None, None),
    "scripts/audit_runtime_reachability.py": (
        "59a69a03cb89492864b5f02a6cb41de31b782d2a",
        "ebbaae44194e6fa60978c8fcd2d3ebceefba89d5c0e7f4753f57443c4667948a",
    ),
    "scripts/validate_main_shadow_authority_parity.py": (
        "b65c70ab46caa43f8fcbd8701dedbf35e12b95be",
        "61da66a3e677f8c329dca32d2ac088f2eda8f052843221a443c3a75260afa198",
    ),
}

EXPECTED_CHANGED_PATHS = {
    "artifacts/architecture/port_01_source_identity_parity_v1.json",
    "domain/canonical_core.py",
    "runtime/__init__.py",
    "runtime/source_identity.py",
    "scripts/audit_port_01_source_identity_parity.py",
    "scripts/audit_runtime_reachability.py",
    "scripts/validate_main_shadow_authority_parity.py",
    "tests/portability/test_port_01_source_identity_parity.py",
    "tests/test_main_shadow_authority_parity.py",
}


class PortabilityAuditError(ValueError):
    """The PORT-01B receipt or exact local source identities are invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PortabilityAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PortabilityAuditError(f"non-finite JSON value is forbidden: {value}")


def _read_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortabilityAuditError(f"{label} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise PortabilityAuditError(f"{label} root must be an object")
    return value


def _validate_user_paths(value: Any) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _validate_user_paths(child)
    elif isinstance(value, list):
        for child in value:
            _validate_user_paths(child)
    elif type(value) is str and re.search(
        r"(?:[A-Za-z]:[\\/]+Users[\\/]+|/home/|/Users/)", value, re.IGNORECASE
    ):
        raise PortabilityAuditError("user-specific absolute workstation path is forbidden")


def _validate_hash(value: Any, *, sha1: bool = False) -> None:
    pattern = SHA1_RE if sha1 else SHA256_RE
    if type(value) is not str or not pattern.fullmatch(value):
        raise PortabilityAuditError("malformed lowercase source identity hash")


def validate_receipt(document: dict[str, Any]) -> dict[str, Any]:
    """Validate deterministic PORT-01B receipt semantics without Git access."""

    expected_keys = {
        "schema_version",
        "policy_id",
        "repository",
        "implementation_base_main_sha",
        "predecessor",
        "windows_b1_reproduction",
        "identity_contract",
        "fixed_blockers",
        "platform_matrix",
        "immutable_anchors",
        "current_source_evolution",
        "safety",
        "governance",
        "canonical_sha256_byte_domain",
        "canonical_sha256",
    }
    if set(document) != expected_keys:
        raise PortabilityAuditError("PORT-01B receipt top-level schema changed")
    if document.get("schema_version") != 1 or document.get("policy_id") != POLICY_ID:
        raise PortabilityAuditError("wrong PORT-01B receipt schema or policy")
    if document.get("repository") != "Thabearr/ATHENA":
        raise PortabilityAuditError("wrong repository identity")
    if document.get("implementation_base_main_sha") != BASE_MAIN_SHA:
        raise PortabilityAuditError("wrong exact PORT-01B base")
    if document.get("canonical_sha256_byte_domain") != "CANONICAL_PAYLOAD_SHA256":
        raise PortabilityAuditError("receipt self-hash byte domain is not explicit")

    predecessor = document["predecessor"]
    if predecessor != {
        "mission": "PORT-01A",
        "policy_id": B1_POLICY_ID,
        "canonical_sha256": B1_CANONICAL_SHA256,
        "git_blob_sha1": B1_GIT_BLOB_SHA1,
        "fixed_blocker_ids": list(B1_FAILURE_IDS),
    }:
        raise PortabilityAuditError("PORT-01A predecessor identity or blocker list changed")
    if document["identity_contract"] != IDENTITY_CONTRACT:
        raise PortabilityAuditError("byte/source identity domains were conflated or changed")

    if document["windows_b1_reproduction"] != {
        "command": "python -m pytest -q --tb=short tests/test_architecture_runtime_reachability.py tests/test_architecture_runtime_reachability_artifact.py tests/test_main_shadow_authority_parity.py tests/test_repository_architecture_inventory.py tests/test_athena_run_authority_matrix.py",
        "before": {"collected": 214, "passed": 199, "failed": 10, "skipped": 0, "xfailed": 5, "xpassed": 0},
        "after": {"collected": 217, "passed": 211, "failed": 0, "skipped": 1, "xfailed": 5, "xpassed": 0},
        "added_regression_tests": 3,
        "all_original_ten_nodes_pass": True,
        "environment": "Windows 11 x86-64; core.autocrlf=true",
    }:
        raise PortabilityAuditError("B1 Windows before/after reproduction evidence changed")

    blockers = document["fixed_blockers"]
    if type(blockers) is not list or len(blockers) != 10:
        raise PortabilityAuditError("exactly ten PORT-01A blockers must be represented")
    if [row.get("failure_id") for row in blockers] != list(B1_FAILURE_IDS):
        raise PortabilityAuditError("PORT-01A blocker ordering or identity changed")
    for row in blockers:
        path = validate_repository_relative_path(row.get("source_path"))
        expected_class = "RAW_ARTIFACT_BYTES" if row["failure_id"] <= "WIN-CRLF-08" else "CANONICAL_JSON_BYTES"
        expected_domain = "GIT_BLOB_PAYLOAD_SHA256" if expected_class == "RAW_ARTIFACT_BYTES" else "CANONICAL_PAYLOAD_SHA256"
        if row.get("predecessor_class") != expected_class:
            raise PortabilityAuditError("predecessor failure class changed")
        if row.get("expected_byte_domain") != expected_domain:
            raise PortabilityAuditError("blocker expected byte domain changed")
        expected_path = (
            "tests/fixtures/p4_4r_run_36285099805_quote_evidence/initial/manifest.json"
            if expected_class == "RAW_ARTIFACT_BYTES"
            else "config/architecture/main-shadow-authority-parity-v1.json"
        )
        if path != expected_path:
            raise PortabilityAuditError("blocker source path changed")
        for flag in ("historical_hash_changed",):
            if row.get(flag) is not False:
                raise PortabilityAuditError("historical identity was changed")
        for result_field in ("windows_result", "linux_result"):
            if type(row.get(result_field)) is not str or not row[result_field]:
                raise PortabilityAuditError("platform result/requirement is missing")
        if row.get("status") != "CLOSED_AT_SOURCE_IDENTITY_BOUNDARY":
            raise PortabilityAuditError("a PORT-01A blocker is not recorded as closed")
        if expected_class == "RAW_ARTIFACT_BYTES":
            expected_identity = {
                "path": "tests/fixtures/p4_4r_run_36285099805_quote_evidence/initial/manifest.json",
                "git_blob_sha1": "120443830d12f2d77c6917d2e8396fab8d25c181",
                "git_blob_payload_sha256": "f2515e5f02682a05b6d3e1cd48f03b08085f0567baf56dfce38244a63e99892e",
                "windows_raw_sha256": "da7d7ec5553f0a30253644f25b5104dfe81b026564135772e63fab99b7b0ad09",
                "remediation_seam": "scripts/audit_runtime_reachability.py::_materialize_tracked_fixture",
            }
        else:
            expected_identity = {
                "path": "config/architecture/main-shadow-authority-parity-v1.json",
                "git_blob_sha1": "034985b0f750550a30369b2cfa295db1ce0ec13d",
                "git_blob_payload_sha256": "d4f525a0eb8d3ffe07e5b64a3452d758bc9e180c5b1db37feecbac1faf395bfe",
                "windows_raw_sha256": "0b2c517517c196fe92e13c8a8c7010f8e7546372c41aee37f8abdff431b0ba34",
                "remediation_seam": "scripts/validate_main_shadow_authority_parity.py::_read_contract_json",
            }
        if (
            path != expected_identity["path"]
            or row.get("predecessor_git_blob_sha1") != expected_identity["git_blob_sha1"]
            or row.get("predecessor_git_blob_payload_sha256") != expected_identity["git_blob_payload_sha256"]
            or row.get("predecessor_windows_raw_sha256") != expected_identity["windows_raw_sha256"]
            or row.get("remediation_seam") != expected_identity["remediation_seam"]
            or row.get("linux_result") != "REQUIRED_EXACT_FINAL_HEAD_HOSTED_TESTS"
        ):
            raise PortabilityAuditError("fixed blocker identity or remediation seam changed")

    platform = document["platform_matrix"]
    expected_platform_keys = {
        "windows_normal_checkout",
        "lf_native_control",
        "hosted_linux",
        "unicode_path",
        "unrelated_cwd",
        "read_only_source",
        "semantic_worktree_mutation",
    }
    if type(platform) is not dict or set(platform) != expected_platform_keys:
        raise PortabilityAuditError("platform matrix schema changed")
    if platform["windows_normal_checkout"] != {
        "os": "Windows 11 x86-64",
        "core_autocrlf": "true",
        "result": "PASS_EXACT_B1_FAILURES_CLOSED",
    }:
        raise PortabilityAuditError("normal Windows checkout evidence changed")
    if platform["lf_native_control"] != {
        "performed": False,
        "result": "NOT_USED_PRIMARY_WINDOWS_CHECKOUT_WAS_AUTHORITATIVE",
    }:
        raise PortabilityAuditError("LF-native control was misrepresented")
    if platform["hosted_linux"] != {
        "platform": "Hosted Ubuntu/Linux",
        "gate": "REQUIRED_ON_EXACT_FINAL_HEAD",
        "same_source_identity_contract": True,
    }:
        raise PortabilityAuditError("Linux correspondence gate changed")
    for field, exact in (
        ("unicode_path", "PASS_EXPLICIT_REPOSITORY_ROOT"),
        ("unrelated_cwd", "PASS_EXPLICIT_REPOSITORY_ROOT"),
        ("read_only_source", "PASS_NO_SOURCE_WRITE"),
        ("semantic_worktree_mutation", "REJECTED_FILTERED_IDENTITY_MISMATCH"),
    ):
        if platform[field] != exact:
            raise PortabilityAuditError(f"platform control result changed: {field}")

    anchors = document["immutable_anchors"]
    if anchors != list(EXPECTED_ANCHORS):
        raise PortabilityAuditError("historical immutable anchor identities changed")
    for anchor in anchors:
        validate_repository_relative_path(anchor.get("path"))
        _validate_hash(anchor.get("git_blob_sha1"), sha1=True)
        _validate_hash(anchor.get("git_blob_payload_sha256"))
        canonical = anchor.get("canonical_sha256")
        if canonical is not None:
            _validate_hash(canonical)

    source_rows = document["current_source_evolution"]
    expected_source_paths = sorted(EXPECTED_SOURCE_BEFORE)
    if type(source_rows) is not list or [row.get("path") for row in source_rows] != expected_source_paths:
        raise PortabilityAuditError("current source movement inventory changed")
    for row in source_rows:
        path = validate_repository_relative_path(row.get("path"))
        if row.get("before_git_blob_sha1") != EXPECTED_SOURCE_BEFORE[path][0]:
            raise PortabilityAuditError(f"pre-B2 source Git identity changed for {path}")
        if row.get("before_git_blob_payload_sha256") != EXPECTED_SOURCE_BEFORE[path][1]:
            raise PortabilityAuditError(f"pre-B2 source identity changed for {path}")
        _validate_hash(row.get("after_git_blob_sha1"), sha1=True)
        _validate_hash(row.get("after_git_blob_payload_sha256"))
        if row.get("after_identity_domain") != "GIT_BLOB_SHA1_AND_GIT_BLOB_PAYLOAD_SHA256":
            raise PortabilityAuditError(f"source identity domain is missing for {path}")

    safety = document["safety"]
    if safety != {
        "gitattributes_changed": False,
        "historical_hashes_repinned": False,
        "historical_receipts_rewritten": False,
        "parity_contract_content_changed": False,
        "raw_quote_verifier_changed": False,
        "installed_payload_identity_implemented": False,
        "network_calls": 0,
        "provider_calls": 0,
        "workflow_dispatches": 0,
        "share_code_actions": 0,
        "email_actions": 0,
        "login_actions": 0,
        "cookie_actions": 0,
        "wallet_actions": 0,
        "staking_actions": 0,
        "wager_actions": 0,
    }:
        raise PortabilityAuditError("unsafe action, hash refresh, or source change recorded")

    governance = document["governance"]
    if governance != {
        "source_review_counter_while_unmerged": "2/5",
        "source_review_counter_if_merged": "3/5",
        "lg_a_comment_id": 5882699153,
        "lg_a_status": "LG_A_WAITING_SEPARATE_OWNER_AUTHORIZATION",
        "lg_a_run": False,
        "p4_4_complete": False,
        "architecture_checkpoint_e_complete": False,
        "clean_successor_proof_complete": False,
        "live_proof_authorized": False,
        "caller_migration_authorized": False,
        "workflow_retirement_authorized": False,
        "port_02a_started": False,
    }:
        raise PortabilityAuditError("PORT-01B governance state changed")

    _validate_user_paths(document)
    claimed = document.get("canonical_sha256")
    _validate_hash(claimed)
    unsigned = dict(document)
    del unsigned["canonical_sha256"]
    if claimed != canonical_payload_sha256(canonical_json_bytes(unsigned)):
        raise PortabilityAuditError("PORT-01B receipt canonical self-hash mismatch")
    return {
        "canonical_sha256": claimed,
        "fixed_blocker_count": len(blockers),
        "source_evolution_count": len(source_rows),
        "immutable_anchor_count": len(anchors),
    }


def load_receipt() -> dict[str, Any]:
    try:
        raw, _identity = read_tracked_head_blob(ROOT, ARTIFACT_RELATIVE_PATH)
    except SourceIdentityError as exc:
        raise PortabilityAuditError("PORT-01B receipt must be an unchanged tracked HEAD blob") from exc
    return _read_json_bytes(raw, "PORT-01B receipt")


def validate_current_state() -> dict[str, Any]:
    document = load_receipt()
    summary = validate_receipt(document)
    for anchor in EXPECTED_ANCHORS:
        try:
            payload, identity = read_tracked_head_blob(ROOT, anchor["path"])
        except SourceIdentityError as exc:
            raise PortabilityAuditError(f"immutable tracked anchor could not be proven: {anchor['path']}") from exc
        if (
            identity.git_blob_sha1 != anchor["git_blob_sha1"]
            or identity.git_blob_payload_sha256 != anchor["git_blob_payload_sha256"]
        ):
            raise PortabilityAuditError(f"historical Git identity changed: {anchor['anchor_id']}")
        if anchor["canonical_sha256"] is not None:
            parsed = _read_json_bytes(payload, anchor["anchor_id"])
            if "canonical_sha256" in parsed:
                canonical_identity = parsed["canonical_sha256"]
            else:
                # Some canonical JSON contracts (such as the parity
                # inventory) have no embedded self-hash field; their
                # canonical identity is the exact output of their
                # source-controlled pretty JSON serializer.
                canonical_identity = canonical_payload_sha256(
                    (
                        json.dumps(
                            parsed,
                            ensure_ascii=False,
                            allow_nan=False,
                            sort_keys=True,
                            indent=2,
                        )
                        + "\n"
                    )
                )
            if canonical_identity != anchor["canonical_sha256"]:
                raise PortabilityAuditError(f"historical canonical identity changed: {anchor['anchor_id']}")

    for row in document["current_source_evolution"]:
        try:
            _payload, identity = read_tracked_head_blob(ROOT, row["path"])
        except SourceIdentityError as exc:
            raise PortabilityAuditError(f"current source identity could not be proven: {row['path']}") from exc
        if (
            identity.git_blob_sha1 != row["after_git_blob_sha1"]
            or identity.git_blob_payload_sha256 != row["after_git_blob_payload_sha256"]
        ):
            raise PortabilityAuditError(f"current source identity changed after receipt: {row['path']}")

    return {
        "result": "PORT_01B_SOURCE_IDENTITY_PARITY_PASS",
        **summary,
        "repository": "Thabearr/ATHENA",
        "network_provider_delivery_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the committed receipt and local Git identities")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required; this audit has no write mode")
    try:
        result = validate_current_state()
    except (PortabilityAuditError, SourceIdentityError) as exc:
        print(f"PORT-01B source identity audit: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
