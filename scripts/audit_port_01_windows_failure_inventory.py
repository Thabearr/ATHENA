#!/usr/bin/env python3
"""Validate the frozen PORT-01A Windows byte/path failure inventory.

This audit is intentionally offline and read-only.  It reads only the local
Git object database and repository files; it never imports ATHENA runtime,
provider, workflow, delivery, or wager modules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "artifacts/architecture/port_01_windows_failure_inventory_v1.json"
POLICY_ID = "ATHENA_PORT_01_WINDOWS_FAILURE_INVENTORY_V1"
BASE_SHA = "4eebb9ffacb8e4434611ebd698170da3b1a3f79a"
FAILURE_CLASSES = {
    "RAW_ARTIFACT_BYTES",
    "GIT_FILTERED_SOURCE_IDENTITY",
    "CANONICAL_JSON_BYTES",
    "DISPLAY_TEXT",
    "FILESYSTEM_PATH_CWD",
    "EXECUTABLE_DISCOVERY",
    "TIMEZONE",
    "UNRELATED_TEST_FRAGILITY",
    "STALE_ALREADY_RESOLVED",
    "UNKNOWN",
}
BYTE_DOMAINS = {
    "RAW_FILE_SHA256",
    "CANONICAL_PAYLOAD_SHA256",
    "GIT_BLOB_SHA1",
    "GIT_BLOB_PAYLOAD_SHA256",
    "LF_NORMALIZED_SOURCE_SHA256",
    "INSTALLED_PAYLOAD_SHA256",
    "DISPLAY_ONLY_NO_IDENTITY",
}
DISPOSITIONS = {
    "REPRODUCED_CURRENT",
    "RESOLVED_BY_INTERVENING_REVIEWED_CHANGE",
    "STALE_TEST_NO_LONGER_REACHABLE",
    "NOT_REPRODUCIBLE_WITH_EVIDENCE",
    "UNKNOWN_BLOCKED",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class InventoryError(ValueError):
    """Raised when inventory evidence or current local byte probes disagree."""


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
            raise InventoryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise InventoryError(f"non-finite JSON number is forbidden: {value}")


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"inventory is unreadable or invalid JSON: {path.name}") from exc
    if type(value) is not dict:
        raise InventoryError("inventory root must be an object")
    digest = value.get("canonical_sha256")
    if type(digest) is not str or not SHA256_RE.fullmatch(digest):
        raise InventoryError("canonical_sha256 must be lowercase SHA-256")
    payload = dict(value)
    del payload["canonical_sha256"]
    actual = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    if digest != actual:
        raise InventoryError("inventory canonical self-hash mismatch")
    return value


def validate_repo_path(value: Any) -> str:
    if type(value) is not str or not value or "\\" in value:
        raise InventoryError("repository paths must be non-empty normalized POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise InventoryError(f"absolute or traversing repository path: {value}")
    if re.match(r"^[A-Za-z]:", value):
        raise InventoryError(f"drive-qualified repository path: {value}")
    return value


def _git(*args: str, check: bool = True) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=check,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InventoryError(f"local Git probe failed: git {' '.join(args)}") from exc
    return result.stdout


def _git_text(*args: str, check: bool = True) -> str:
    return _git(*args, check=check).decode("utf-8", errors="strict").strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha1(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _require_hash(record: Any, domain: str, *, sha1: bool = False) -> str:
    if type(record) is not dict or set(record) != {"value", "byte_domain"}:
        raise InventoryError("hash identity must declare value and exactly one byte_domain")
    value = record["value"]
    expected = SHA1_RE if sha1 else SHA256_RE
    if type(value) is not str or not expected.fullmatch(value):
        raise InventoryError("malformed lowercase Git/hash identity")
    if record["byte_domain"] != domain or domain not in BYTE_DOMAINS:
        raise InventoryError(f"wrong or missing byte domain; expected {domain}")
    return value


def _validate_no_user_paths(value: Any, key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            _validate_no_user_paths(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            _validate_no_user_paths(child, key)
    elif type(value) is str:
        if re.search(r"(?:[A-Za-z]:[\\/]Users[\\/]+|/home/|/Users/)", value, re.IGNORECASE):
            raise InventoryError("user-specific absolute path is forbidden")
        if key.endswith("path") or key.endswith("_path"):
            validate_repo_path(value)


def _validate_inventory_shape(doc: dict[str, Any]) -> None:
    if doc.get("schema_version") != 1 or doc.get("policy_id") != POLICY_ID:
        raise InventoryError("wrong PORT-01A inventory schema or policy")
    if doc.get("repository") != "Thabearr/ATHENA":
        raise InventoryError("wrong repository identity")
    if doc.get("canonical_sha256_byte_domain") != "CANONICAL_PAYLOAD_SHA256":
        raise InventoryError("canonical self-hash has no exact canonical-payload byte domain")
    if doc.get("implementation_base_main_sha") != BASE_SHA:
        raise InventoryError("wrong exact implementation base")
    required_sections = {
        "historical_report", "current_windows_environment", "current_reproduction",
        "byte_probes", "failures", "historical_disposition", "linux_correspondence",
        "blocking_summary", "historical_immutable_anchors", "governance", "safety",
        "canonical_sha256_byte_domain", "canonical_sha256",
    }
    if set(doc) != required_sections | {"schema_version", "policy_id", "repository", "implementation_base_main_sha"}:
        raise InventoryError("inventory top-level schema changed")
    _validate_no_user_paths(doc)
    historical = doc["historical_report"]
    if historical != {
        "source": "PR #414",
        "passed": 118,
        "xfailed": 5,
        "reported_windows_failures": 10,
        "evidence_class": "REPORTED_PRIOR_WINDOWS_LOCAL_RESULT",
        "supplemental_nodeid_corroboration": "An untracked local pytest lastfailed cache dated 2026-09-27 listed the same ten node IDs; this is corroboration only, not source-controlled historical evidence.",
    }:
        raise InventoryError("historical PR #414 aggregate report changed")
    failures = doc["failures"]
    dispositions = doc["historical_disposition"]
    if len(failures) != 10 or len(dispositions) != 10:
        raise InventoryError("all ten historical failures must remain dispositioned")
    failure_ids = [item.get("failure_id") for item in failures]
    if len(set(failure_ids)) != 10:
        raise InventoryError("failure IDs must be unique")
    disposition_by_id = {item.get("failure_id"): item for item in dispositions}
    if set(disposition_by_id) != set(failure_ids):
        raise InventoryError("historical disposition IDs do not cover exact failure inventory")
    for item in failures:
        if item.get("primary_class") not in FAILURE_CLASSES:
            raise InventoryError("failure has missing/unknown primary class")
        if item.get("current_disposition") not in DISPOSITIONS:
            raise InventoryError("failure has invalid current disposition")
        if item["current_disposition"] != "REPRODUCED_CURRENT":
            raise InventoryError("current reproduced failures must remain truthfully classified")
        if item.get("byte_probe_id") not in {p.get("probe_id") for p in doc["byte_probes"]}:
            raise InventoryError("failure references unknown byte probe")
        if type(item.get("blocks_port_01b")) is not bool or type(item.get("blocks_port_02")) is not bool:
            raise InventoryError("blocker flags must be exact booleans")
        for field in ("expected_identity", "actual_identity"):
            identity = item.get(field)
            if type(identity) is not dict or set(identity) != {"value", "byte_domain"}:
                raise InventoryError(f"{field} must identify one exact byte domain")
            domain = identity["byte_domain"]
            if domain not in BYTE_DOMAINS:
                raise InventoryError(f"{field} has an unknown byte domain")
            if domain == "GIT_BLOB_SHA1":
                if type(identity["value"]) is not str or not SHA1_RE.fullmatch(identity["value"]):
                    raise InventoryError(f"{field} has malformed Git blob SHA-1")
            elif domain != "DISPLAY_ONLY_NO_IDENTITY":
                if type(identity["value"]) is not str or not SHA256_RE.fullmatch(identity["value"]):
                    raise InventoryError(f"{field} has malformed lowercase SHA-256")
    for item in dispositions:
        if item.get("disposition") not in DISPOSITIONS:
            raise InventoryError("historical failure has invalid disposition")
        if item["disposition"] != "REPRODUCED_CURRENT":
            raise InventoryError("historical disposition does not match current reproduction")
    reproduction = doc["current_reproduction"]
    if reproduction.get("source_head") != BASE_SHA:
        raise InventoryError("reproduction source is not the exact baseline commit")
    count_fields = ("collected", "passed", "failed", "skipped", "xfailed", "xpassed")
    if any(type(reproduction.get(name)) is not int or reproduction[name] < 0 for name in count_fields):
        raise InventoryError("pytest result counts must be non-negative exact integers")
    if sum(reproduction[name] for name in count_fields[1:]) != reproduction["collected"]:
        raise InventoryError("pytest result counts do not sum to collected nodes")
    if reproduction["failed"] != len(failures):
        raise InventoryError("current failed count differs from classified failure inventory")
    if reproduction.get("failure_nodeids") != [item["pytest_nodeid"] for item in failures]:
        raise InventoryError("current failure node list differs from classified failures")
    collected_nodeids = reproduction.get("collected_nodeids")
    if (
        type(collected_nodeids) is not list
        or len(collected_nodeids) != reproduction["collected"]
        or any(type(nodeid) is not str or not nodeid.startswith("tests/") for nodeid in collected_nodeids)
        or len(set(collected_nodeids)) != len(collected_nodeids)
        or not set(reproduction["failure_nodeids"]) <= set(collected_nodeids)
    ):
        raise InventoryError("exact collected pytest node list is incomplete, duplicate, or inconsistent")
    summary = doc["blocking_summary"]
    class_counts: dict[str, int] = {}
    disposition_counts = {disposition: 0 for disposition in DISPOSITIONS}
    for item in failures:
        class_counts[item["primary_class"]] = class_counts.get(item["primary_class"], 0) + 1
        disposition_counts[item["current_disposition"]] += 1
    if summary.get("current_failures") != len(failures):
        raise InventoryError("blocking summary failure count is inconsistent")
    if summary.get("primary_class_counts") != class_counts:
        raise InventoryError("primary-class summary is inconsistent")
    if summary.get("disposition_counts") != disposition_counts:
        raise InventoryError("disposition summary is inconsistent")
    if summary.get("port_01b_blockers") != sum(item["blocks_port_01b"] for item in failures):
        raise InventoryError("PORT-01B blocker summary is inconsistent")
    if summary.get("port_02_blockers") != sum(item["blocks_port_02"] for item in failures):
        raise InventoryError("PORT-02 blocker summary is inconsistent")
    if summary.get("historical_only") != sum(item["historical_only"] for item in failures):
        raise InventoryError("historical-only summary is inconsistent")
    if summary.get("unclassified") != 0 or any(item["primary_class"] == "UNKNOWN" for item in failures):
        raise InventoryError("current failures must all have a primary cause class")
    for probe in doc["byte_probes"]:
        validate_repo_path(probe.get("path"))
        for key, domain in (
            ("git_blob_sha1", "GIT_BLOB_SHA1"),
            ("git_hash_object_default_sha1", "GIT_BLOB_SHA1"),
            ("git_blob_payload_sha256", "GIT_BLOB_PAYLOAD_SHA256"),
            ("working_tree_sha256", "RAW_FILE_SHA256"),
            ("lf_normalized_sha256", "LF_NORMALIZED_SOURCE_SHA256"),
            ("crlf_materialization_sha256", "RAW_FILE_SHA256"),
        ):
            _require_hash(probe.get(key), domain, sha1=(domain == "GIT_BLOB_SHA1"))
    for anchor in doc["historical_immutable_anchors"]:
        validate_repo_path(anchor.get("path"))
        _require_hash(anchor.get("git_blob_sha1"), "GIT_BLOB_SHA1", sha1=True)
        _require_hash(anchor.get("git_blob_payload_sha256"), "GIT_BLOB_PAYLOAD_SHA256")
        if "canonical_payload_sha256" in anchor:
            _require_hash(anchor["canonical_payload_sha256"], "CANONICAL_PAYLOAD_SHA256")
    if doc["governance"].get("source_review_counter_while_unmerged") != "1/5":
        raise InventoryError("wrong unmerged governance counter")
    if doc["governance"].get("source_review_counter_if_merged") != "2/5":
        raise InventoryError("wrong post-merge governance counter")
    governance = doc["governance"]
    for key in (
        "p4_4_complete", "architecture_checkpoint_e_complete", "clean_successor_proof_complete",
        "live_proof_authorized", "caller_migration_authorized", "workflow_retirement_authorized",
        "lg_a_run", "port_01b_started",
    ):
        if governance.get(key) is not False:
            raise InventoryError(f"unsafe or inaccurate governance state: {key}")
    if governance.get("lg_a_disposition_comment_id") != 5882699153:
        raise InventoryError("wrong LG-A disposition evidence")
    if governance.get("lg_a_status") != "LG_A_WAITING_SEPARATE_OWNER_AUTHORIZATION":
        raise InventoryError("wrong LG-A disposition")
    safety = doc["safety"]
    for key in (
        "production_source_changed", "gitattributes_changed", "historical_evidence_rewritten",
        "expected_hash_refreshed",
    ):
        if safety.get(key) is not False:
            raise InventoryError(f"forbidden change was recorded: {key}")
    for key in (
        "network_calls", "provider_calls", "workflow_dispatches", "share_code_actions",
        "email_actions", "login_actions", "cookie_actions", "wallet_actions",
        "staking_actions", "wager_actions",
    ):
        if type(safety.get(key)) is not int or safety[key] != 0:
            raise InventoryError(f"external side-effect count must remain zero: {key}")


def _probe_path(probe: dict[str, Any]) -> str:
    relative = validate_repo_path(probe["path"])
    expected_blob = _require_hash(probe["git_blob_sha1"], "GIT_BLOB_SHA1", sha1=True)
    try:
        actual_blob = _git_text("rev-parse", f"HEAD:{relative}").lower()
    except InventoryError:
        if _git_text("rev-parse", "HEAD").lower() != BASE_SHA:
            return "SKIP_SOURCE_MOVED"
        raise
    if actual_blob != expected_blob:
        return "SKIP_SOURCE_MOVED"
    blob = _git("show", f"HEAD:{relative}")
    worktree_path = ROOT.joinpath(*PurePosixPath(relative).parts)
    try:
        working = worktree_path.read_bytes()
    except OSError as exc:
        raise InventoryError(f"tracked byte probe is missing: {relative}") from exc
    if _git_blob_sha1(blob) != expected_blob:
        raise InventoryError(f"Git blob SHA-1 mismatch for {relative}")
    hash_object = _git_text("hash-object", f"--path={relative}", relative).lower()
    if hash_object != probe["git_hash_object_default_sha1"]["value"]:
        raise InventoryError(f"git hash-object path-filter identity changed for {relative}")
    if _sha256(blob) != probe["git_blob_payload_sha256"]["value"]:
        raise InventoryError(f"Git blob payload SHA-256 mismatch for {relative}")
    lf_normalized = working.replace(b"\r\n", b"\n")
    crlf_normalized = working.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if _sha256(lf_normalized) != _sha256(blob):
        raise InventoryError(f"worktree differs from Git blob beyond CRLF materialization: {relative}")
    if sys.platform == "win32" and os.name == "nt":
        auto = _git_text("config", "--get", "core.autocrlf", check=False)
        if auto.lower() == "true" and working != blob:
            if _sha256(working) != probe["working_tree_sha256"]["value"]:
                raise InventoryError(f"Windows raw materialization differs from recorded reproduction: {relative}")
            if _sha256(crlf_normalized) != probe["crlf_materialization_sha256"]["value"]:
                raise InventoryError(f"Windows CRLF observation changed for {relative}")
    eol = _git_text("ls-files", "--eol", "--", relative)
    attrs = _git_text("check-attr", "-a", "--", relative)
    if not eol.startswith("i/lf "):
        raise InventoryError(f"unexpected index line ending state for {relative}: {eol}")
    if attrs:
        raise InventoryError(f"unexpected Git attributes for {relative}: {attrs}")
    return "MATCH" if working == blob else "EOL_CONVERSION_ONLY"


def validate_current_platform(doc: dict[str, Any]) -> list[tuple[str, str]]:
    _validate_inventory_shape(doc)
    observations = [(probe["probe_id"], _probe_path(probe)) for probe in doc["byte_probes"]]
    for anchor in doc["historical_immutable_anchors"]:
        relative = validate_repo_path(anchor["path"])
        blob_sha1 = _git_text("rev-parse", f"HEAD:{relative}").lower()
        if blob_sha1 != anchor["git_blob_sha1"]["value"]:
            raise InventoryError(f"historical immutable Git blob changed: {relative}")
        blob = _git("show", f"HEAD:{relative}")
        if _sha256(blob) != anchor["git_blob_payload_sha256"]["value"]:
            raise InventoryError(f"historical immutable payload changed: {relative}")
        if "canonical_payload_sha256" in anchor:
            try:
                payload = json.loads(blob.decode("utf-8"), object_pairs_hook=_no_duplicate_pairs)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InventoryError(f"historical JSON anchor is invalid: {relative}") from exc
            if payload.get("canonical_sha256") != anchor["canonical_payload_sha256"]["value"]:
                raise InventoryError(f"historical canonical identity changed: {relative}")
    return observations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate inventory and read-only local Git/worktree probes")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required; this audit has no write mode")
    try:
        doc = load_inventory()
        observations = validate_current_platform(doc)
    except InventoryError as exc:
        print(f"PORT-01A inventory audit: FAIL: {exc}", file=sys.stderr)
        return 1
    for probe_id, result in observations:
        print(f"{probe_id}: {result}")
    print("PORT-01A inventory audit: PASS (local Git/worktree only; no network/provider access)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
