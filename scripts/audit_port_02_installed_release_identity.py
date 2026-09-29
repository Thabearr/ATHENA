#!/usr/bin/env python3
"""Validate the PORT-02A release-identity receipt offline and read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence

from runtime.release_identity import (
    MANIFEST_POLICY_ID,
    MANIFEST_SCHEMA_VERSION,
    RESOURCE_ROLES,
    TRUST_MODE,
)
from runtime.source_identity import (
    SourceIdentityError,
    canonical_payload_sha256,
    read_tracked_head_blob,
    validate_repository_relative_path,
)
from scripts import audit_port_01_source_identity_parity as port01b


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = "artifacts/architecture/port_02_installed_release_identity_v1.json"
POLICY_ID = "ATHENA_PORT_02_INSTALLED_RELEASE_IDENTITY_V1"
BASE_MAIN_SHA = "dd8813b3b30d2fd252acf81b8c08ac7016873df3"
PORT01B_CANONICAL_SHA256 = "14d1c6e71f2f01aea720c451bf226efd9e667092c9d8a72062d966e59c2e9219"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "repository",
        "implementation_base_main_sha",
        "predecessor",
        "identity_contract",
        "manifest_contract",
        "development_proof",
        "installed_proof",
        "resource_proof",
        "canonical_core_parity",
        "tamper_matrix",
        "writable_roots",
        "immutable_anchors",
        "current_source_evolution",
        "safety",
        "governance",
        "canonical_sha256",
    }
)
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
        "anchor_id": "P05_RUNTIME_ARTIFACT",
        "path": "artifacts/architecture/runtime-reachability-v1.json",
        "git_blob_sha1": "0c840c9b245d0eb8610a62ac3cc8bbc3be1120a1",
        "git_blob_payload_sha256": "a8ccb4c0c8ab2bea9bd133bb7fa7e155957bf1e38e5bf7ae6cccb4f44640f7e4",
        "canonical_sha256": None,
    },
    {
        "anchor_id": "PORT01A_INVENTORY",
        "path": "artifacts/architecture/port_01_windows_failure_inventory_v1.json",
        "git_blob_sha1": "6ff6fd3153419e7dae7f789401dc1b757d207126",
        "git_blob_payload_sha256": "b6958170ab20752656d40a8809563fe939c2875a34d88366430af216536d5aec",
        "canonical_sha256": "78b92cde4681d3bbd71007ed4c3e434717c029f6745b3b37ecb93bb917738966",
    },
    {
        "anchor_id": "PORT01B_RECEIPT",
        "path": "artifacts/architecture/port_01_source_identity_parity_v1.json",
        "git_blob_sha1": "4ad2dd77cc95a82410aa973387f81c00175f04a8",
        "git_blob_payload_sha256": "a307f5a002c533ff25db62634329c27e772b7e441aab8d3583c719c60a9a614e",
        "canonical_sha256": PORT01B_CANONICAL_SHA256,
    },
)
EXPECTED_BEFORE_SOURCE = {
    "domain/canonical_core.py": (
        "cb241f82069ca8f6904b3779b704b0ed5583ddb8",
        "9608d9b57e89055710080ee104e3462c423a52bead38b2fc0660d7af91c8c148",
    ),
    "runtime/release_identity.py": (None, None),
    "runtime/resources.py": (None, None),
    "config/release_manifest.schema.json": (None, None),
}
EXPECTED_SOURCE_PATHS = tuple(sorted(EXPECTED_BEFORE_SOURCE))
EXPECTED_ROLES = list(RESOURCE_ROLES)
EXPECTED_CLOSED_ROOTS = ["config", "contracts", "database/migrations", "models", "ui"]


class Port02AuditError(ValueError):
    """The PORT-02A evidence or current source identity is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, OverflowError) as exc:
        raise Port02AuditError("PORT-02A receipt cannot be serialized canonically") from exc


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Port02AuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise Port02AuditError(f"non-finite JSON constant is forbidden: {value}")


def _load_strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except Port02AuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Port02AuditError("PORT-02A receipt is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise Port02AuditError("PORT-02A receipt root must be an object")
    if raw != canonical_json_bytes(value):
        raise Port02AuditError("PORT-02A receipt file bytes are not canonical")
    return value


def _require_sha(value: Any, *, sha1: bool = False, label: str) -> str:
    pattern = SHA1_RE if sha1 else SHA256_RE
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise Port02AuditError(f"{label} must be lowercase exact {'SHA-1' if sha1 else 'SHA-256'}")
    return value


def _walk_strings(value: Any, path: str = "$"):
    if type(value) is dict:
        for key, item in value.items():
            yield from _walk_strings(item, f"{path}.{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}[{index}]")
    elif type(value) is str:
        yield path, value


def _validate_no_secrets_or_absolute_paths(document: dict[str, Any]) -> None:
    forbidden_keys = {"token", "cookie", "credential", "password", "share_code", "share_url", "secret"}
    for parent_path, text in _walk_strings(document):
        leaf = parent_path.rsplit(".", 1)[-1].split("[", 1)[0].lower()
        if leaf in forbidden_keys:
            raise Port02AuditError("receipt contains a forbidden secret-bearing field")
        if re.match(r"^[A-Za-z]:[\\/]|^/(?:Users|home|tmp)/", text):
            raise Port02AuditError("receipt contains a workstation-specific absolute path")


def load_receipt() -> dict[str, Any]:
    try:
        raw, _identity = read_tracked_head_blob(ROOT, ARTIFACT_PATH)
    except SourceIdentityError as exc:
        raise Port02AuditError("PORT-02A receipt must be an unchanged tracked HEAD blob") from exc
    return _load_strict_json(raw)


def validate_receipt(document: dict[str, Any]) -> dict[str, Any]:
    if type(document) is not dict or set(document) != RECEIPT_FIELDS:
        raise Port02AuditError("PORT-02A receipt fields are not exact")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise Port02AuditError("PORT-02A receipt schema version drifted")
    if document["policy_id"] != POLICY_ID or document["repository"] != "Thabearr/ATHENA":
        raise Port02AuditError("PORT-02A receipt identity drifted")
    if document["implementation_base_main_sha"] != BASE_MAIN_SHA:
        raise Port02AuditError("PORT-02A base identity drifted")
    _require_sha(document["implementation_base_main_sha"], sha1=True, label="base main SHA")

    predecessor = document["predecessor"]
    if predecessor != {
        "policy_id": port01b.POLICY_ID,
        "canonical_sha256": PORT01B_CANONICAL_SHA256,
        "fixed_blocker_count": 10,
        "fixed_blocker_ids": [f"WIN-CRLF-{index:02d}" for index in range(1, 11)],
    }:
        raise Port02AuditError("PORT-01B predecessor identity or blocker list drifted")

    identity_contract = document["identity_contract"]
    if identity_contract != {
        "development_type": "DevelopmentCheckoutIdentity",
        "installed_type": "InstalledReleaseIdentity",
        "development_git_required": True,
        "installed_git_required": False,
        "trust_mode": TRUST_MODE,
        "dummy_git_sha_forbidden": True,
        "cwd_is_identity_authority": False,
        "installed_payload_identity_domain": "RAW_FILE_SHA256",
    }:
        raise Port02AuditError("PORT-02A source identity contract drifted")

    manifest = document["manifest_contract"]
    if manifest != {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "policy_id": MANIFEST_POLICY_ID,
        "canonical_encoding": "UTF-8_SORTED_COMPACT_JSON_ONE_LF",
        "duplicate_keys_rejected": True,
        "resource_roles": EXPECTED_ROLES,
        "closed_world_roots": EXPECTED_CLOSED_ROOTS,
        "closed_world_extra_files": "REJECTED",
        "install_root_writes": False,
        "signature_claimed": False,
    }:
        raise Port02AuditError("release manifest policy or resource vocabulary drifted")

    dev = document["development_proof"]
    if dev.get("base_head_sha") != BASE_MAIN_SHA or dev.get("identity_kind") != "DEVELOPMENT_CHECKOUT":
        raise Port02AuditError("DevelopmentCheckout proof is not bound to exact base")
    if dev.get("explicit_repository_root") is not True or dev.get("filtered_worktree_to_head_blob_verified") is not True:
        raise Port02AuditError("DevelopmentCheckout source verification was weakened")
    if dev.get("missing_git") != "FAIL_CLOSED":
        raise Port02AuditError("DevelopmentCheckout missing-Git behavior drifted")

    installed = document["installed_proof"]
    _require_sha(installed.get("trusted_manifest_sha256"), label="trusted manifest digest")
    if installed.get("classification") != "SYNTHETIC_INSTALLED_RELEASE_IDENTITY_VERIFIED":
        raise Port02AuditError("installed proof classification is overstated or unknown")
    if installed.get("native_packaged_runtime_proven") is not False:
        raise Port02AuditError("synthetic installed proof was mislabeled as native packaging")
    if installed.get("git_calls") != 0 or installed.get("unrelated_cwd") is not True:
        raise Port02AuditError("installed no-Git or unrelated-cwd proof is missing")
    if installed.get("unicode_release_root") is not True or installed.get("read_only_resources") is not True:
        raise Port02AuditError("installed platform-path proof is incomplete")
    if (
        installed.get("platform_tag") not in {"windows", "linux"}
        or installed.get("architecture_tag") not in {"x86_64", "aarch64"}
        or installed.get("windows_local_result") != "PASS"
        or installed.get("hosted_linux_gate") != "REQUIRED_ON_EXACT_FINAL_HEAD"
    ):
        raise Port02AuditError("installed platform evidence is not accurately classified")

    resources = document["resource_proof"]
    expected_resource_paths = {
        "config/architecture/component-authority-registry-v1.json",
        "config/architecture/main-shadow-authority-parity-v1.json",
        "config/model_weights.json",
        "ui/index.html",
        "ui/app.js",
        "ui/styles.css",
        "models/over25_model.joblib",
        "database/migrations/002_add_elo_columns.sql",
        "domain/provider_market_semantics.py",
        "domain/price_all.py",
        "domain/market_router.py",
        "domain/portfolio_optimizer.py",
        "domain/sportybet_share_code.py",
    }
    if set(resources.get("logical_paths", ())) != expected_resource_paths:
        raise Port02AuditError("synthetic installed resource set changed")
    if resources.get("canonical_component_source_count") != 5:
        raise Port02AuditError("canonical component source resource count changed")

    parity = document["canonical_core_parity"]
    _require_sha(parity.get("development_bindings_sha256"), label="development bindings SHA")
    _require_sha(parity.get("installed_bindings_sha256"), label="installed bindings SHA")
    _require_sha(parity.get("registry_canonical_sha256"), label="registry canonical SHA")
    if parity.get("development_bindings_sha256") != parity.get("installed_bindings_sha256"):
        raise Port02AuditError("DevelopmentCheckout and installed canonical bindings differ")
    if parity.get("exact_equality") is not True or parity.get("same_five_owners") is not True:
        raise Port02AuditError("canonical core parity proof is incomplete")
    if parity.get("owner_responsibilities") != [
        "provider_market_semantics",
        "price_all_and_de_vig",
        "market_router",
        "portfolio_optimizer",
        "delivery_share_code_transport",
    ]:
        raise Port02AuditError("canonical owner set changed")

    tamper = document["tamper_matrix"]
    expected_cases = {
        "manifest_digest",
        "manifest_canonical_bytes",
        "duplicate_key",
        "path_traversal",
        "missing_config",
        "config_bytes",
        "model_bytes",
        "ui_bytes",
        "canonical_component_bytes",
        "source_git_blob_metadata",
        "canonical_contract_metadata",
        "extra_closed_world_file",
        "symlink_payload",
        "wrong_platform",
        "wrong_architecture",
        "resource_role",
        "identity_resolver_mismatch",
        "development_missing_git",
    }
    if type(tamper) is not dict or set(tamper) != expected_cases or any(value != "REJECTED" for value in tamper.values()):
        raise Port02AuditError("installed release tamper matrix is incomplete")

    writable = document["writable_roots"]
    if writable != {
        "install_root_read_only": True,
        "writable_roots_separate": True,
        "windows_policy": "LOCALAPPDATA/ATHENA/{data,cache,state}",
        "linux_policy": "XDG_OR_HOME/athena",
        "unsupported_platform": "FAIL_CLOSED",
        "cwd_fallback": False,
    }:
        raise Port02AuditError("writable-root policy drifted")

    anchors = document["immutable_anchors"]
    if type(anchors) is not list or tuple(anchors) != EXPECTED_ANCHORS:
        raise Port02AuditError("historical P4.4/BASE/runtime/PORT anchors changed")
    for item in anchors:
        validate_repository_relative_path(item.get("path"))
        _require_sha(item.get("git_blob_sha1"), sha1=True, label=f"{item.get('anchor_id')} Git SHA")
        _require_sha(item.get("git_blob_payload_sha256"), label=f"{item.get('anchor_id')} payload SHA")

    source_rows = document["current_source_evolution"]
    if type(source_rows) is not list or tuple(row.get("path") for row in source_rows) != EXPECTED_SOURCE_PATHS:
        raise Port02AuditError("PORT-02A current source identity path list changed")
    for row in source_rows:
        path = validate_repository_relative_path(row.get("path"))
        before_blob, before_payload = EXPECTED_BEFORE_SOURCE[path]
        if row.get("before_git_blob_sha1") != before_blob:
            raise Port02AuditError(f"PORT-02A before identity changed for {path}")
        if row.get("before_git_blob_payload_sha256") != before_payload:
            raise Port02AuditError(f"PORT-02A before payload identity changed for {path}")
        if before_blob is not None:
            _require_sha(before_blob, sha1=True, label=f"{path} before Git SHA")
            _require_sha(before_payload, label=f"{path} before payload SHA")
        _require_sha(row.get("after_git_blob_sha1"), sha1=True, label=f"{path} after Git SHA")
        _require_sha(row.get("after_git_blob_payload_sha256"), label=f"{path} after payload SHA")

    if document["safety"] != {
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
        "gitattributes_changed": False,
        "historical_hashes_repinned": False,
        "historical_receipts_rewritten": False,
        "execution_envelope_changed": False,
        "packaging_implemented": False,
    }:
        raise Port02AuditError("PORT-02A side-effect or non-goal evidence drifted")
    if document["governance"] != {
        "source_review_counter_while_unmerged": "3/5",
        "source_review_counter_if_merged": "4/5",
        "port_02b_started": False,
        "reread_due_after_port_02b_merge": True,
        "reread_required_before_port_02c": True,
        "lg_a_run": False,
        "lg_a_authorized": False,
        "lg_a_status": "LG_A_WAITING_SEPARATE_OWNER_AUTHORIZATION",
        "p4_4_complete": False,
        "architecture_checkpoint_e_complete": False,
        "clean_successor_proof_complete": False,
        "caller_migration_authorized": False,
        "workflow_retirement_authorized": False,
    }:
        raise Port02AuditError("PORT-02A governance state drifted")

    _validate_no_secrets_or_absolute_paths(document)
    claimed = _require_sha(document.get("canonical_sha256"), label="receipt canonical SHA")
    unsigned = dict(document)
    del unsigned["canonical_sha256"]
    if claimed != canonical_payload_sha256(canonical_json_bytes(unsigned)):
        raise Port02AuditError("PORT-02A receipt canonical self-hash mismatch")
    return {
        "canonical_sha256": claimed,
        "resource_count": len(expected_resource_paths),
        "component_source_count": 5,
        "immutable_anchor_count": len(anchors),
        "source_evolution_count": len(source_rows),
    }


def validate_current_state() -> dict[str, Any]:
    document = load_receipt()
    summary = validate_receipt(document)
    try:
        historical = port01b.validate_current_state()
    except (ValueError, SourceIdentityError) as exc:
        raise Port02AuditError("PORT-01B historical identity or immutable anchor validation failed") from exc
    if historical.get("fixed_blocker_count") != 10:
        raise Port02AuditError("PORT-01B predecessor validation did not retain all ten blockers")
    for row in document["current_source_evolution"]:
        try:
            _payload, identity = read_tracked_head_blob(ROOT, row["path"])
        except SourceIdentityError as exc:
            raise Port02AuditError(f"PORT-02A current source identity could not be verified: {row['path']}") from exc
        if (
            identity.git_blob_sha1 != row["after_git_blob_sha1"]
            or identity.git_blob_payload_sha256 != row["after_git_blob_payload_sha256"]
        ):
            raise Port02AuditError(f"PORT-02A source identity changed after receipt: {row['path']}")
    try:
        schema, schema_identity = read_tracked_head_blob(ROOT, "config/release_manifest.schema.json")
    except SourceIdentityError as exc:
        raise Port02AuditError("release manifest JSON schema is not a verified tracked file") from exc
    schema_record = next(
        row for row in document["current_source_evolution"]
        if row["path"] == "config/release_manifest.schema.json"
    )
    if schema_identity.git_blob_sha1 != schema_record["after_git_blob_sha1"]:
        raise Port02AuditError("release manifest schema Git identity changed")
    try:
        schema_document = json.loads(schema.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, Port02AuditError) as exc:
        raise Port02AuditError("release manifest schema is not strict UTF-8 JSON") from exc
    if schema_document.get("properties", {}).get("policy_id", {}).get("const") != MANIFEST_POLICY_ID:
        raise Port02AuditError("release manifest schema policy identity drifted")
    return {
        "result": "PORT_02A_INSTALLED_RELEASE_IDENTITY_PASS",
        **summary,
        "port_01b_result": historical.get("result"),
        "port_01b_moved_paths": historical.get("moved_paths", []),
        "network_provider_delivery_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the committed receipt and exact local source identities")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required; this audit has no write mode")
    try:
        result = validate_current_state()
    except (Port02AuditError, SourceIdentityError) as exc:
        print(f"PORT-02A installed release audit: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
