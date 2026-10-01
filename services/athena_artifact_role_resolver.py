"""Canonical artifact roles, not producer names, own verified restore bytes.

Pure metadata/path/integrity policy. No GitHub/provider transport or mutable
runtime identity configuration. Historical producers remain read-only adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable

from runtime.source_identity import validate_repository_relative_path

POLICY_ID = "ATHENA_CANONICAL_ARTIFACT_ROLES_V1"
MANIFEST_POLICY_ID = "ATHENA_CANONICAL_RUN_ARTIFACT_ROLE_MANIFEST_V1"
REPOSITORY = "Thabearr/ATHENA"
CANONICAL_WORKFLOW = ".github/workflows/athena-run.yml"
MANIFEST_FILENAME = "artifact-role-manifest-v1.json"
ROLE_IDS = ("DURABLE_HISTORY_PRIME", "PERSISTENT_FIXTURE_IDENTITY_STATE",
            "PR119_BOOTSTRAP", "RETAINED_SOURCE_EVIDENCE")
STATE_FILENAME = "current-shadow-fixture-identity-v2-state.json"
BOOTSTRAP_FILENAME = "pr119-materialized.ndjson"
BOOTSTRAP_SHA256 = "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
LEGACY_PRODUCERS = {
    "DURABLE_HISTORY_PRIME": {"workflow_path": ".github/workflows/current-shadow-history-cache-prime.yml",
                             "artifact_name": "current-shadow-history-cache-prime"},
    "PERSISTENT_FIXTURE_IDENTITY_STATE": {"workflow_path": ".github/workflows/current-shadow-all-market.yml",
                                           "artifact_name": "current-shadow-all-market-request"},
    "PR119_BOOTSTRAP": {"release": "athena-fresh-holdout-bootstrap-v1", "asset": BOOTSTRAP_FILENAME},
}
ROLE_ROOTS = {
    "DURABLE_HISTORY_PRIME": "artifact-roles/durable-history-prime",
    "PERSISTENT_FIXTURE_IDENTITY_STATE": "artifact-roles/persistent-fixture-identity-state",
    "PR119_BOOTSTRAP": "artifact-roles/pr119-bootstrap",
    "RETAINED_SOURCE_EVIDENCE": "source-evidence",
}
CLASSIFICATIONS = {
    "DURABLE_HISTORY_PRIME": "TRANSPORT_CACHE_NO_EVIDENCE_AUTHORITY",
    "PERSISTENT_FIXTURE_IDENTITY_STATE": "RUNTIME_IDENTITY_VERIFIER_REMAINS_AUTHORITATIVE",
    "PR119_BOOTSTRAP": "EXACT_FIXED_BOOTSTRAP_NO_NEW_AUTHORITY",
    "RETAINED_SOURCE_EVIDENCE": "PUBLICATION_ONLY_NO_RESTORE_OR_AUTHORITY",
}


class ArtifactRoleError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactRoleError(message)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def self_sha(value: dict[str, Any]) -> str:
    return sha(canonical({key: item for key, item in value.items() if key != "canonical_sha256"}))


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=_object)
    require(type(value) is dict, "JSON document must be an object")
    return value


def hex_sha(value: Any, length: int) -> bool:
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def safe_path(root: Path, relative: str) -> Path:
    relative = validate_repository_relative_path(relative)
    require(not root.is_symlink(), "symlink root forbidden")
    current = root
    for part in relative.split("/"):
        current = current / part
        require(not current.is_symlink(), "symlink path forbidden")
    require(current.resolve().is_relative_to(root.resolve()), "path escapes root")
    return current


def inventory(root: Path) -> list[dict[str, Any]]:
    require(root.is_dir() and not root.is_symlink(), "role root unavailable or symlink")
    rows = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "symlink inventory member forbidden")
        if path.is_dir():
            continue
        require(path.is_file(), "non-regular inventory member")
        relative = path.relative_to(root).as_posix()
        safe_path(root, relative)
        raw = path.read_bytes()
        rows.append({"path": relative, "size_bytes": len(raw), "sha256": sha(raw)})
    require(bool(rows), "empty role inventory")
    return sorted(rows, key=lambda row: row["path"])


@dataclass(frozen=True)
class Candidate:
    run_id: int
    head_sha: str
    workflow_path: str
    artifact_id: int
    artifact_name: str
    repository: str = REPOSITORY
    head_branch: str = "main"
    status: str = "completed"
    conclusion: str = "success"
    event_name: str = "workflow_dispatch"


def validate_candidate(candidate: Candidate, *, current_run_id: int, role_id: str,
                       canonical_producer: bool) -> None:
    require(type(candidate) is Candidate, "exact Candidate required")
    require(role_id in ROLE_IDS and role_id != "RETAINED_SOURCE_EVIDENCE", "role is not restorable")
    require(candidate.repository == REPOSITORY and candidate.head_branch == "main" and
            candidate.status == "completed" and candidate.conclusion == "success",
            "candidate must be successful trusted main")
    require(type(candidate.run_id) is int and candidate.run_id > 0 and
            candidate.run_id != current_run_id and type(candidate.artifact_id) is int and
            candidate.artifact_id > 0 and hex_sha(candidate.head_sha, 40), "invalid/self producer")
    if canonical_producer:
        require(candidate.workflow_path == CANONICAL_WORKFLOW and
                candidate.artifact_name == f"athena-run-{candidate.run_id}" and
                candidate.event_name in {"workflow_dispatch", "schedule"}, "wrong canonical producer")
    else:
        require(role_id in LEGACY_PRODUCERS and role_id != "PR119_BOOTSTRAP", "no legacy Actions producer")
        require(candidate.workflow_path == LEGACY_PRODUCERS[role_id]["workflow_path"] and
                candidate.artifact_name == LEGACY_PRODUCERS[role_id]["artifact_name"], "wrong legacy producer")


def validate_origin(role_id: str, origin: dict[str, Any]) -> None:
    require(type(origin) is dict and origin.get("repository") == REPOSITORY, "origin repository differs")
    kind = origin.get("source_kind")
    if kind == "FIXED_RELEASE":
        require(role_id == "PR119_BOOTSTRAP" and
                origin.get("release") == LEGACY_PRODUCERS[role_id]["release"] and
                origin.get("asset") == BOOTSTRAP_FILENAME and
                origin.get("payload_sha256") == BOOTSTRAP_SHA256, "fixed release origin differs")
    elif kind == "LEGACY_ACTIONS":
        require(role_id in LEGACY_PRODUCERS and role_id != "PR119_BOOTSTRAP", "wrong legacy role origin")
        require(origin.get("workflow_path") == LEGACY_PRODUCERS[role_id]["workflow_path"] and
                origin.get("artifact_name") == LEGACY_PRODUCERS[role_id]["artifact_name"] and
                type(origin.get("run_id")) is int and origin["run_id"] > 0 and
                hex_sha(origin.get("head_sha"), 40) and hex_sha(origin.get("inventory_sha256"), 64),
                "legacy origin binding differs")
    elif kind == "CANONICAL_EXECUTION":
        require(role_id in {"PERSISTENT_FIXTURE_IDENTITY_STATE", "RETAINED_SOURCE_EVIDENCE"} and
                origin.get("workflow_path") == CANONICAL_WORKFLOW and
                type(origin.get("run_id")) is int and origin["run_id"] > 0 and
                hex_sha(origin.get("head_sha"), 40), "canonical execution origin differs")
        if origin.get("restored_ancestry") is not None:
            validate_origin(role_id, origin["restored_ancestry"])
    else:
        raise ArtifactRoleError("unknown origin source kind")


def validate_payload(role_id: str, root: Path, origin: dict[str, Any]) -> None:
    """Delegate history and identity semantics to their existing authoritative validators."""
    validate_origin(role_id, origin)
    files = inventory(root)
    if origin["source_kind"] == "LEGACY_ACTIONS":
        require(origin["inventory_sha256"] == sha(canonical(files)), "legacy origin inventory mismatch")
    if role_id == "DURABLE_HISTORY_PRIME":
        from scripts import restore_current_shadow_history_prime_artifact as prime
        receipt = prime._read_receipt(root, expected_prime_commit_sha=origin["head_sha"])
        require(origin.get("receipt_sha256") == sha((root / prime.PRIME_RECEIPT_FILENAME).read_bytes()),
                "prime origin receipt mismatch")
        prime._validate_cache_tree(root / "history-cache", receipt)
        require({row["path"] for row in files} ==
                {prime.PRIME_RECEIPT_FILENAME} | {"history-cache/" + path.name for path in (root / "history-cache").iterdir()},
                "prime closed-world inventory differs")
    elif role_id == "PERSISTENT_FIXTURE_IDENTITY_STATE":
        from domain import current_shadow_fixture_identity_v2 as identity
        require([row["path"] for row in files] == [STATE_FILENAME], "identity role file set differs")
        document = strict_json((root / STATE_FILENAME).read_bytes())
        require(set(document) == {"payload", "state_sha256"} and
                hex_sha(document["state_sha256"], 64), "identity document fields differ")
        require(document["state_sha256"] == sha(identity._canonical(document["payload"])),
                "identity state hash mismatch")
        identity._validate_loaded_payload(document["payload"])
        identity._validate_loaded_bindings(document["payload"])
    elif role_id == "PR119_BOOTSTRAP":
        require([row["path"] for row in files] == [BOOTSTRAP_FILENAME] and
                files[0]["sha256"] == BOOTSTRAP_SHA256, "PR119 exact payload mismatch")
    elif role_id != "RETAINED_SOURCE_EVIDENCE":
        raise ArtifactRoleError("unknown role")


def build_role(role_id: str, artifact_root: Path, origin: dict[str, Any]) -> dict[str, Any]:
    require(role_id in ROLE_IDS, "unknown role")
    root = safe_path(artifact_root, ROLE_ROOTS[role_id])
    validate_payload(role_id, root, origin)
    rows = inventory(root)
    return {"role_id": role_id, "relative_root": ROLE_ROOTS[role_id], "file_count": len(rows),
            "byte_count": sum(row["size_bytes"] for row in rows), "inventory": rows,
            "inventory_sha256": sha(canonical(rows)), "origin_provenance": origin,
            "authority_classification": CLASSIFICATIONS[role_id]}


def validate_manifest(raw: bytes, artifact_root: Path, candidate: Candidate,
                      *, current_run_id: int, role_id: str) -> tuple[Path, dict[str, Any]]:
    validate_candidate(candidate, current_run_id=current_run_id, role_id=role_id, canonical_producer=True)
    value = strict_json(raw)
    require(set(value) == {"schema_version", "policy_id", "repository", "producer", "restore_eligible",
                           "roles", "canonical_sha256"}, "manifest fields differ")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1 and
            value["policy_id"] == MANIFEST_POLICY_ID and value["repository"] == REPOSITORY and
            value["restore_eligible"] is True, "manifest identity/eligibility differs")
    require(raw == canonical(value) and value["canonical_sha256"] == self_sha(value), "manifest canonical SHA differs")
    producer = value["producer"]
    require(type(producer) is dict and set(producer) == {"workflow_family", "workflow_path", "run_id", "head_sha",
                                                       "head_branch", "event_name", "request_sha256"}, "producer fields differ")
    require(producer["workflow_family"] == "ATHENA_RUN" and producer["workflow_path"] == CANONICAL_WORKFLOW and
            type(producer["run_id"]) is int and producer["run_id"] == candidate.run_id and
            producer["head_sha"] == candidate.head_sha and producer["head_branch"] == "main" and
            producer["event_name"] == candidate.event_name and hex_sha(producer["request_sha256"], 64),
            "manifest producer mismatch")
    require(type(value["roles"]) is list, "roles must be a list")
    ids = [row.get("role_id") for row in value["roles"] if type(row) is dict]
    require(len(ids) == len(value["roles"]) and len(ids) == len(set(ids)) and
            ids == sorted(ids) and set(ids) <= set(ROLE_IDS), "unknown/duplicate/unsorted roles")
    found = None
    for row in value["roles"]:
        expected = build_role(row["role_id"], artifact_root, row.get("origin_provenance"))
        require(canonical(row) == canonical(expected), "role inventory/hash/path/authority differs")
        if row["role_id"] == role_id:
            found = row
    require(found is not None, "requested role absent")
    return safe_path(artifact_root, found["relative_root"]), found


def select_canonical(role_id: str, candidates: Iterable[Candidate],
                     load: Callable[[Candidate], tuple[Path, bytes]], *, current_run_id: int):
    """Newest verified candidate; reject bad bytes before considering older ones."""
    require(role_id in ROLE_IDS and role_id != "RETAINED_SOURCE_EVIDENCE", "role is not restorable")
    seen = set()
    for candidate in sorted(candidates, key=lambda item: item.run_id, reverse=True):
        require(candidate.run_id not in seen, "duplicate producer run")
        seen.add(candidate.run_id)
        try:
            validate_candidate(candidate, current_run_id=current_run_id, role_id=role_id, canonical_producer=True)
            root, raw = load(candidate)
            role_root, row = validate_manifest(raw, root, candidate, current_run_id=current_run_id, role_id=role_id)
            return candidate, role_root, row
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return None
