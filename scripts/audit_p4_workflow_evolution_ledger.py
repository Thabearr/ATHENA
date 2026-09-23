"""Offline authority for reviewed workflow changes after the P4.3D checkpoint."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from scripts import audit_p4_3_workflow_retirement_ledger as retirement


POLICY_ID = "ATHENA_P4_WORKFLOW_EVOLUTION_LEDGER_V1"
BASE_MAIN_SHA = "d762adff8eda468dc694ac1ee43578cc7851c78d"
BASE_WORKFLOW_TREE_SHA1 = "6391a5a17b9925c91849a758852915d509a64703"
BASE_LIVE_COUNT = 37
BASE_P43_RETIRED_COUNT = 3
BASE_RETIREMENT_LEDGER_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
P43D_RECEIPT_SHA256 = "4b43e084f82f65330429388732990ed8e49abe8e05fd30fc57a319a210dfb25f"
LEDGER_PATH = Path("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
P44A_SNAPSHOT_PATH = Path("artifacts/architecture/p4_workflow_evolution_snapshots/p4_4a_workflow_evolution_ledger_v1.json")
SNAPSHOT_DIR = Path("artifacts/architecture/p4_workflow_evolution_snapshots")
P43D_RECEIPT_PATH = Path("artifacts/architecture/p4_3d_retirement_audit_extensibility_v1.json")
P43_RETIREMENT_CHECKPOINT_PATH = retirement.P43C_LEDGER_SNAPSHOT_PATH
WORKFLOW_DIR = Path(".github/workflows")
FAMILIES = {"ATHENA_RUN", "ATHENA_INGEST", "ATHENA_RETRAIN", "ATHENA_BACKTEST", "TESTS", "ATHENA_PR_BRIDGE"}
MAINTENANCE_CONTRACT_POLICY = "ATHENA_P4_BASELINE_WORKFLOW_MAINTENANCE_REVISE_V1"
MAINTENANCE_CONTRACT = {
    "policy_id": MAINTENANCE_CONTRACT_POLICY,
    "baseline_origin": "P4_3A_SURVIVOR",
    "path_presence_changed": False,
    "retirement_authority_granted": False,
    "trigger_surface_changed": False,
    "permissions_changed": False,
    "concurrency_changed": False,
    "provider_acquisition_authority_changed": False,
    "model_authority_changed": False,
    "pricing_authority_changed": False,
    "selection_authority_changed": False,
    "betting_authority_changed": False,
}
MAINTENANCE_CONTRACT_FIELDS = frozenset(MAINTENANCE_CONTRACT)
REVISED_WORKFLOW_FIXTURE_ROOT = "tests/fixtures/architecture/revised_workflows/"
PROTECTED = retirement.PROTECTED_LIVE | {".github/workflows/current-shadow-sportybet-source-diagnostic.yml"}
IDENTITY_KEYS = {"git_blob_sha1", "source_sha256"}
TRANSITION_KEYS = {
    "transition_id", "operation", "workflow_path", "before", "after",
    "phase_id", "canonical_family", "evidence_receipt_path", "evidence_body_sha256",
    "checkpoint_snapshot_path",
}
EVOLUTION_LEDGER_FIELDS = {
    "schema_version", "policy_id", "base_main_sha", "base_workflow_tree_sha1",
    "base_live_workflow_count", "p4_3a_matrix_sha256",
    "base_p4_3_retirement_checkpoint_sha256", "p4_3d_receipt_sha256",
    "current_p4_3_retirement_ledger_sha256", "current_p4_3_retired_workflow_count",
    "current_p4_3_retirement_ledger_snapshot_path",
    "current_p4_3_retirement_ledger_snapshot_sha256",
    "current_live_workflow_count", "current_workflow_tree_sha1", "transitions",
    "canonical_sha256",
}


class WorkflowEvolutionError(AssertionError):
    """Raised when post-P4.3 workflow authority is missing or inconsistent."""


def canonical_json_bytes(payload: Any) -> bytes:
    return retirement.canonical_json_bytes(payload)


def canonical_sha256(payload: dict[str, Any]) -> str:
    return retirement.canonical_sha256(payload)


def source_identity(raw: bytes) -> dict[str, str]:
    return {
        "git_blob_sha1": retirement._git_blob_sha1(raw),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def receipt_evidence_body_sha256(receipt: dict[str, Any]) -> str:
    """Exclude the ledger backlink and self-hash to prevent a hash cycle."""
    body = {key: value for key, value in receipt.items() if key not in {
        "workflow_evolution_ledger_sha256", "canonical_sha256"
    }}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise WorkflowEvolutionError(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout


def _workflow_path(path: Any) -> str:
    if not isinstance(path, str) or "\\" in path:
        raise WorkflowEvolutionError("workflow transition path must be a POSIX string")
    parsed = PurePosixPath(path)
    if (
        not path.startswith(".github/workflows/")
        or parsed.as_posix() != path
        or ".." in parsed.parts
        or not path.endswith(".yml")
        or len(parsed.parts) != 3
    ):
        raise WorkflowEvolutionError(f"workflow transition path is outside .github/workflows: {path}")
    return path


def _identity(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != IDENTITY_KEYS:
        raise WorkflowEvolutionError(f"{label} requires exact Git blob and source SHA identities")
    blob, source = value["git_blob_sha1"], value["source_sha256"]
    if not isinstance(blob, str) or not re.fullmatch(r"[0-9a-f]{40}", blob):
        raise WorkflowEvolutionError(f"{label} Git blob SHA is invalid")
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{64}", source):
        raise WorkflowEvolutionError(f"{label} source SHA is invalid")
    return dict(value)


def _evidence_path(value: Any) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise WorkflowEvolutionError("transition evidence receipt path is invalid")
    parsed = PurePosixPath(value)
    if not value.startswith("artifacts/architecture/") or parsed.as_posix() != value or ".." in parsed.parts or not value.endswith(".json"):
        raise WorkflowEvolutionError("transition evidence receipt path is outside architecture artifacts")
    return value


def _checkpoint_path(value: Any) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise WorkflowEvolutionError("transition checkpoint snapshot path is invalid")
    parsed = PurePosixPath(value)
    if (
        not value.startswith("artifacts/architecture/p4_workflow_evolution_snapshots/")
        or parsed.as_posix() != value or ".." in parsed.parts or not value.endswith(".json")
    ):
        raise WorkflowEvolutionError("transition checkpoint snapshot path is outside the evolution snapshot directory")
    return value


def _historical_before_fixture_path(value: Any) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise WorkflowEvolutionError("maintenance historical-before fixture path must be POSIX")
    parsed = PurePosixPath(value)
    if (
        not value.startswith(REVISED_WORKFLOW_FIXTURE_ROOT)
        or parsed.as_posix() != value
        or ".." in parsed.parts
        or len(parsed.parts) < 5
        or not value.endswith(".yml")
    ):
        raise WorkflowEvolutionError("maintenance historical-before fixture path is invalid")
    return value


def _validate_maintenance_contract(contract: Any) -> None:
    if not isinstance(contract, dict) or set(contract) != MAINTENANCE_CONTRACT_FIELDS:
        raise WorkflowEvolutionError("MAINTENANCE_REVISE contract schema must match the exact v1 fields")
    if contract != MAINTENANCE_CONTRACT:
        raise WorkflowEvolutionError("MAINTENANCE_REVISE contract grants or misstates maintenance authority")


def _maintenance_fixture_identity(
    fixture: Any,
    before: dict[str, str],
    *,
    fixture_bytes: Mapping[str, bytes] | None,
) -> tuple[str, bytes]:
    if not isinstance(fixture, dict) or set(fixture) != {"path", *IDENTITY_KEYS}:
        raise WorkflowEvolutionError("MAINTENANCE_REVISE requires an exact historical-before fixture identity")
    fixture_path = _historical_before_fixture_path(fixture.get("path"))
    fixture_identity = _identity(
        {key: fixture.get(key) for key in IDENTITY_KEYS},
        label=f"MAINTENANCE_REVISE fixture {fixture_path}",
    )
    if fixture_identity != before:
        raise WorkflowEvolutionError(f"maintenance historical-before fixture differs from before identity: {fixture_path}")
    raw = fixture_bytes.get(fixture_path) if fixture_bytes is not None else None
    if not isinstance(raw, bytes):
        raise WorkflowEvolutionError(f"maintenance historical-before fixture bytes are unavailable: {fixture_path}")
    if source_identity(raw) != before:
        raise WorkflowEvolutionError(f"maintenance historical-before fixture bytes drifted: {fixture_path}")
    return fixture_path, raw


def baseline_state(retirement_ledger: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Resolve frozen P4.3A survivors using the separately validated current P4.3 ledger."""
    matrix, _ = retirement.load_baseline()
    checkpoint = retirement._load_p43c_ledger_snapshot()
    retirement.validate_historical_snapshot_extension(checkpoint, retirement_ledger)
    retired = set(retirement_ledger["retired_workflow_paths"])
    state = {
        row["workflow_path"]: {
            "git_blob_sha1": row["git_blob_sha1"],
            "source_sha256": row["source_sha256"],
        }
        for row in matrix["workflow_rows"] if row["workflow_path"] not in retired
    }
    if len(state) != retirement_ledger["current_live_workflow_count"]:
        raise WorkflowEvolutionError("current P4.3 retirement state arithmetic changed")
    return state


def _evolution_immutable_fields(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(snapshot.get(field) for field in (
        "schema_version", "policy_id", "base_main_sha", "base_workflow_tree_sha1",
        "base_live_workflow_count", "p4_3a_matrix_sha256",
        "base_p4_3_retirement_checkpoint_sha256", "p4_3d_receipt_sha256",
    ))


def validate_evolution_snapshot_extension(
    snapshot: dict[str, Any],
    current: dict[str, Any],
    *,
    snapshot_retirement_snapshot: dict[str, Any] | None = None,
    current_retirement_snapshot: dict[str, Any] | None = None,
    current_retirement: dict[str, Any] | None = None,
) -> None:
    """Validate immutable evolution history while allowing reviewed ledger appends.

    P4.3 retirement state is validated independently and may advance monotonically;
    the evolution snapshot records the P4.3 ledger identity/count at its phase.
    """
    if set(snapshot) != EVOLUTION_LEDGER_FIELDS or set(current) != EVOLUTION_LEDGER_FIELDS:
        raise WorkflowEvolutionError("evolution snapshot/current ledger schema fields mismatch")
    if snapshot.get("canonical_sha256") != canonical_sha256(snapshot):
        raise WorkflowEvolutionError("historical evolution snapshot canonical SHA mismatch")
    if current.get("canonical_sha256") != canonical_sha256(current):
        raise WorkflowEvolutionError("current evolution ledger canonical SHA mismatch")
    if _evolution_immutable_fields(snapshot) != _evolution_immutable_fields(current):
        raise WorkflowEvolutionError("current evolution ledger changed immutable base identity")
    old = snapshot.get("transitions")
    new = current.get("transitions")
    if not isinstance(old, list) or not isinstance(new, list) or new[:len(old)] != old:
        raise WorkflowEvolutionError("current evolution ledger rewrote or reordered a historical transition")
    old_retired = snapshot.get("current_p4_3_retired_workflow_count")
    new_retired = current.get("current_p4_3_retired_workflow_count")
    if (
        type(old_retired) is not int or type(new_retired) is not int
        or old_retired < BASE_P43_RETIRED_COUNT or new_retired < old_retired
        or new_retired > retirement.BASELINE_WORKFLOW_COUNT
    ):
        raise WorkflowEvolutionError("current P4.3 retirement state is not a monotonic extension")
    if snapshot_retirement_snapshot is not None and current_retirement_snapshot is not None and current_retirement is not None:
        p43_checkpoint = retirement._load_p43c_ledger_snapshot()
        retirement.validate_historical_snapshot_extension(p43_checkpoint, snapshot_retirement_snapshot)
        retirement.validate_historical_snapshot_extension(p43_checkpoint, current_retirement_snapshot)
        retirement.validate_historical_snapshot_extension(p43_checkpoint, current_retirement)
        retirement.validate_historical_snapshot_extension(snapshot_retirement_snapshot, current_retirement_snapshot)
        retirement.validate_historical_snapshot_extension(snapshot_retirement_snapshot, current_retirement)
        if current.get("current_p4_3_retirement_ledger_sha256") != current_retirement.get("canonical_sha256"):
            raise WorkflowEvolutionError("evolution ledger does not bind the current P4.3 retirement ledger")
        if new_retired != current_retirement.get("current_retired_workflow_count"):
            raise WorkflowEvolutionError("evolution ledger P4.3 retired count differs from current retirement ledger")
        if snapshot.get("current_p4_3_retirement_ledger_sha256") != snapshot_retirement_snapshot.get("canonical_sha256"):
            raise WorkflowEvolutionError("historical evolution checkpoint does not bind its P4.3 ledger snapshot")
        if snapshot.get("current_p4_3_retirement_ledger_snapshot_sha256") != snapshot_retirement_snapshot.get("canonical_sha256"):
            raise WorkflowEvolutionError("historical evolution checkpoint P4.3 snapshot SHA mismatch")
        if current.get("current_p4_3_retirement_ledger_snapshot_sha256") != current_retirement_snapshot.get("canonical_sha256"):
            raise WorkflowEvolutionError("current evolution ledger does not bind its P4.3 ledger snapshot")
        for label, ledger in (("historical", snapshot), ("current", current)):
            snapshot_path = ledger.get("current_p4_3_retirement_ledger_snapshot_path")
            if (
                not isinstance(snapshot_path, str)
                or not snapshot_path.startswith("artifacts/architecture/p4_3_retirement_ledger_snapshots/")
                or ".." in PurePosixPath(snapshot_path).parts
            ):
                raise WorkflowEvolutionError(f"{label} evolution ledger P4.3 snapshot path is invalid")
        if snapshot.get("current_p4_3_retired_workflow_count") != snapshot_retirement_snapshot.get("current_retired_workflow_count"):
            raise WorkflowEvolutionError("historical evolution P4.3 retired count differs from its snapshot")
        if new_retired != current_retirement_snapshot.get("current_retired_workflow_count"):
            raise WorkflowEvolutionError("current evolution P4.3 count differs from its checkpoint snapshot")
        if current.get("current_p4_3_retired_workflow_count") != current_retirement.get("current_retired_workflow_count"):
            raise WorkflowEvolutionError("current evolution P4.3 count differs from current retirement ledger")
    if type(snapshot.get("current_live_workflow_count")) is not int or type(current.get("current_live_workflow_count")) is not int:
        raise WorkflowEvolutionError("evolution snapshot/current live count is invalid")
    if snapshot["current_live_workflow_count"] != BASE_LIVE_COUNT - (old_retired - BASE_P43_RETIRED_COUNT) + _net_evolution_count(old):
        raise WorkflowEvolutionError("historical evolution snapshot count arithmetic mismatch")
    if current["current_live_workflow_count"] != BASE_LIVE_COUNT - (new_retired - BASE_P43_RETIRED_COUNT) + _net_evolution_count(new):
        raise WorkflowEvolutionError("current evolution ledger count arithmetic mismatch")
    for label, ledger in (("historical", snapshot), ("current", current)):
        tree_sha = ledger.get("current_workflow_tree_sha1")
        if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
            raise WorkflowEvolutionError(f"{label} evolution ledger tree SHA is invalid")


def _net_evolution_count(transitions: list[dict[str, Any]]) -> int:
    return sum(1 if item.get("operation") == "ADD" else -1 if item.get("operation") == "RETIRE" else 0 for item in transitions)


def load_retirement_snapshot_for_evolution(evolution_snapshot: dict[str, Any]) -> dict[str, Any]:
    path = evolution_snapshot.get("current_p4_3_retirement_ledger_snapshot_path")
    if not isinstance(path, str) or not path.startswith("artifacts/architecture/p4_3_retirement_ledger_snapshots/") or ".." in PurePosixPath(path).parts:
        raise WorkflowEvolutionError("evolution checkpoint P4.3 snapshot path is invalid")
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowEvolutionError(f"evolution checkpoint P4.3 snapshot is unreadable: {path}") from exc
    expected = evolution_snapshot.get("current_p4_3_retirement_ledger_snapshot_sha256")
    if value.get("canonical_sha256") != expected or retirement.canonical_sha256(value) != expected:
        raise WorkflowEvolutionError(f"evolution checkpoint P4.3 snapshot SHA mismatch: {path}")
    try:
        blob = _git("hash-object", f"--path={path}", path).decode("ascii").strip()
        head_blob = _git("rev-parse", f"HEAD:{path}").decode("ascii").strip()
    except WorkflowEvolutionError:
        # A not-yet-committed local P4.4A snapshot is allowed only for the
        # zero-transition construction check. Hosted CI must see it in HEAD.
        if evolution_snapshot.get("transitions"):
            raise
    else:
        if blob != head_blob:
            raise WorkflowEvolutionError(f"evolution checkpoint P4.3 snapshot is not source-controlled: {path}")
    return value


def validate_transition_checkpoints(
    transitions: list[dict[str, Any]],
    current: dict[str, Any],
    *,
    receipts: Mapping[str, dict[str, Any]],
    snapshots: Mapping[str, dict[str, Any]],
    current_retirement: dict[str, Any] | None = None,
    current_retirement_snapshot: dict[str, Any] | None = None,
) -> None:
    """Verify every receipt points to its immutable ledger-prefix snapshot."""
    for index, transition in enumerate(transitions):
        receipt_path = _evidence_path(transition.get("evidence_receipt_path"))
        snapshot_path = _checkpoint_path(transition.get("checkpoint_snapshot_path"))
        receipt = receipts.get(receipt_path)
        snapshot = snapshots.get(snapshot_path)
        if not isinstance(receipt, dict) or not isinstance(snapshot, dict):
            raise WorkflowEvolutionError(f"transition receipt or checkpoint snapshot is missing: {transition.get('transition_id')}")
        if snapshot.get("canonical_sha256") != canonical_sha256(snapshot):
            raise WorkflowEvolutionError(f"transition checkpoint snapshot hash mismatch: {snapshot_path}")
        if _evolution_immutable_fields(snapshot) != _evolution_immutable_fields(current):
            raise WorkflowEvolutionError(f"transition checkpoint base identity mismatch: {snapshot_path}")
        prefix = transitions[: index + 1]
        if snapshot.get("transitions") != prefix:
            raise WorkflowEvolutionError(f"transition checkpoint is not the exact cumulative prefix: {snapshot_path}")
        if receipt.get("workflow_evolution_ledger_sha256") != snapshot.get("canonical_sha256"):
            raise WorkflowEvolutionError(f"transition receipt backlink differs from its checkpoint snapshot: {receipt_path}")
        if receipt_evidence_body_sha256(receipt) != transition.get("evidence_body_sha256"):
            raise WorkflowEvolutionError(f"transition receipt evidence-body hash mismatch: {receipt_path}")
        if receipt.get("canonical_sha256") != canonical_sha256(receipt):
            raise WorkflowEvolutionError(f"transition receipt self-hash mismatch: {receipt_path}")
        intent = {key: value for key, value in transition.items() if key != "evidence_body_sha256"}
        if receipt.get("reviewed_workflow_transition") != intent:
            raise WorkflowEvolutionError(f"transition receipt does not bind exact transition intent: {receipt_path}")
        snapshot_retirement_snapshot = load_retirement_snapshot_for_evolution(snapshot)
        validate_evolution_snapshot_extension(
            snapshot,
            current,
            snapshot_retirement_snapshot=snapshot_retirement_snapshot,
            current_retirement_snapshot=current_retirement_snapshot,
            current_retirement=current_retirement,
        )


def apply_transitions(
    starting_state: Mapping[str, dict[str, str]],
    transitions: list[dict[str, Any]],
    *,
    frozen_baseline_paths: Iterable[str],
    evidence_receipts: Mapping[str, dict[str, Any]],
    baseline_families: Mapping[str, str] | None = None,
    historical_before_fixture_bytes: Mapping[str, bytes] | None = None,
) -> dict[str, dict[str, str]]:
    """Pure ordered evaluator; callers separately check the derived Git tree."""
    if not isinstance(transitions, list):
        raise WorkflowEvolutionError("workflow evolution transitions must be a list")
    state = {path: dict(identity) for path, identity in starting_state.items()}
    frozen = set(frozen_baseline_paths)
    introduced: set[str] = set()
    identifiers: set[str] = set()
    historical_fixture_paths: set[str] = set()
    for transition in transitions:
        if not isinstance(transition, dict):
            raise WorkflowEvolutionError("workflow transition must be an object")
        operation = transition.get("operation")
        operation_fields = (
            {"historical_fixture"} if operation == "RETIRE"
            else {"maintenance_contract", "historical_before_fixture"} if operation == "MAINTENANCE_REVISE"
            else set()
        )
        required = TRANSITION_KEYS | operation_fields
        if set(transition) != required or operation not in {"ADD", "REVISE", "RETIRE", "MAINTENANCE_REVISE"}:
            raise WorkflowEvolutionError("workflow transition schema/operation is not reviewed")
        path = _workflow_path(transition["workflow_path"])
        identifier = transition["transition_id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Z0-9_.-]+", identifier) or identifier in identifiers:
            raise WorkflowEvolutionError(f"duplicate or invalid workflow transition identifier: {identifier}")
        identifiers.add(identifier)
        phase = transition["phase_id"]
        if not isinstance(phase, str) or not re.fullmatch(r"P[0-9]+(?:\.[0-9]+)?[A-Z0-9_.-]*", phase):
            raise WorkflowEvolutionError(f"workflow transition phase is invalid: {path}")
        if operation == "MAINTENANCE_REVISE":
            if baseline_families is None or path not in baseline_families:
                raise WorkflowEvolutionError(f"MAINTENANCE_REVISE target is not a P4.3A baseline path: {path}")
            if transition["canonical_family"] != baseline_families[path]:
                raise WorkflowEvolutionError(f"MAINTENANCE_REVISE canonical family differs from P4.3A: {path}")
            _validate_maintenance_contract(transition["maintenance_contract"])
        elif transition["canonical_family"] not in FAMILIES:
            raise WorkflowEvolutionError(f"workflow transition canonical family is invalid: {path}")
        _checkpoint_path(transition["checkpoint_snapshot_path"])
        evidence_path = _evidence_path(transition["evidence_receipt_path"])
        receipt = evidence_receipts.get(evidence_path)
        digest = transition["evidence_body_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(receipt, dict):
            raise WorkflowEvolutionError(f"reviewed transition evidence receipt is required: {path}")
        if receipt_evidence_body_sha256(receipt) != digest:
            raise WorkflowEvolutionError(f"transition evidence body SHA mismatch: {path}")
        if receipt.get("canonical_sha256") != canonical_sha256(receipt):
            raise WorkflowEvolutionError(f"transition evidence receipt self-hash mismatch: {path}")
        intent = {key: value for key, value in transition.items() if key != "evidence_body_sha256"}
        if receipt.get("reviewed_workflow_transition") != intent:
            raise WorkflowEvolutionError(f"transition evidence does not authorize the exact operation: {path}")

        before = transition["before"]
        after = transition["after"]
        if operation == "ADD":
            if path in frozen or path in state or path in introduced or before is not None:
                raise WorkflowEvolutionError(f"ADD path already existed or is frozen: {path}")
            state[path] = _identity(after, label=f"ADD after {path}")
            introduced.add(path)
        elif operation == "REVISE":
            if path not in introduced or path not in state or path in frozen:
                raise WorkflowEvolutionError(f"REVISE requires a live ledger-added path: {path}")
            if _identity(before, label=f"REVISE before {path}") != state[path]:
                raise WorkflowEvolutionError(f"REVISE before identity does not chain: {path}")
            changed = _identity(after, label=f"REVISE after {path}")
            if changed == before:
                raise WorkflowEvolutionError(f"REVISE after identity did not change: {path}")
            state[path] = changed
        elif operation == "RETIRE":
            if path not in introduced or path not in state or path in frozen:
                raise WorkflowEvolutionError(f"RETIRE requires a live ledger-added path: {path}")
            if _identity(before, label=f"RETIRE before {path}") != state[path] or after is not None:
                raise WorkflowEvolutionError(f"RETIRE before/after identity is invalid: {path}")
            fixture = transition["historical_fixture"]
            if not isinstance(fixture, dict) or set(fixture) != {"path", *IDENTITY_KEYS}:
                raise WorkflowEvolutionError(f"RETIRE historical fixture identity is required: {path}")
            fixture_path = fixture["path"]
            if not isinstance(fixture_path, str) or "\\" in fixture_path or not fixture_path.startswith("tests/fixtures/architecture/retired_workflows/") or ".." in PurePosixPath(fixture_path).parts or not fixture_path.endswith(".yml"):
                raise WorkflowEvolutionError(f"RETIRE historical fixture path is invalid: {path}")
            if _identity({key: fixture[key] for key in IDENTITY_KEYS}, label=f"RETIRE fixture {path}") != before:
                raise WorkflowEvolutionError(f"RETIRE fixture identity differs from before: {path}")
            del state[path]
        else:
            if path not in frozen or path not in state or path in introduced:
                raise WorkflowEvolutionError(f"MAINTENANCE_REVISE requires a live retained P4.3A survivor: {path}")
            before_identity = _identity(before, label=f"MAINTENANCE_REVISE before {path}")
            if before_identity != state[path]:
                raise WorkflowEvolutionError(f"MAINTENANCE_REVISE before identity does not chain: {path}")
            after_identity = _identity(after, label=f"MAINTENANCE_REVISE after {path}")
            if after_identity == before_identity:
                raise WorkflowEvolutionError(f"MAINTENANCE_REVISE after identity did not change: {path}")
            fixture_path, _raw = _maintenance_fixture_identity(
                transition["historical_before_fixture"],
                before_identity,
                fixture_bytes=historical_before_fixture_bytes,
            )
            if fixture_path in historical_fixture_paths:
                raise WorkflowEvolutionError(f"maintenance revisions require a distinct immutable fixture: {fixture_path}")
            historical_fixture_paths.add(fixture_path)
            state[path] = after_identity
    return state


def _load_maintenance_before_fixtures(
    transitions: list[dict[str, Any]],
    *,
    require_source_controlled: bool,
) -> dict[str, bytes]:
    fixtures: dict[str, bytes] = {}
    for transition in transitions:
        if transition.get("operation") != "MAINTENANCE_REVISE":
            continue
        fixture = transition.get("historical_before_fixture")
        if not isinstance(fixture, dict):
            raise WorkflowEvolutionError("MAINTENANCE_REVISE historical-before fixture is required")
        path = _historical_before_fixture_path(fixture.get("path"))
        try:
            raw = Path(path).read_bytes()
        except OSError as exc:
            raise WorkflowEvolutionError(f"maintenance historical-before fixture is missing: {path}") from exc
        before = _identity(transition.get("before"), label=f"MAINTENANCE_REVISE before {transition.get('workflow_path')}")
        if source_identity(raw) != before:
            raise WorkflowEvolutionError(f"maintenance historical-before fixture source identity mismatch: {path}")
        if require_source_controlled:
            try:
                head_blob = _git("rev-parse", f"HEAD:{path}").decode("ascii").strip()
            except WorkflowEvolutionError as exc:
                raise WorkflowEvolutionError(f"maintenance historical-before fixture is not source-controlled: {path}") from exc
            if head_blob != before["git_blob_sha1"]:
                raise WorkflowEvolutionError(f"maintenance historical-before fixture Git blob mismatch: {path}")
        if path in fixtures:
            raise WorkflowEvolutionError(f"maintenance revisions require a distinct immutable fixture: {path}")
        fixtures[path] = raw
    return fixtures


def resolve_p43a_historical_workflow_source(
    path: str,
    *,
    retirement_ledger: dict[str, Any] | None = None,
    evolution_ledger: dict[str, Any] | None = None,
    historical_fixture_bytes: Mapping[str, bytes] | None = None,
) -> bytes:
    """Resolve original P4.3A bytes independently from a reviewed live revision."""
    matrix, _ = retirement.load_baseline()
    row = next((item for item in matrix["workflow_rows"] if item.get("workflow_path") == path), None)
    if row is None:
        raise WorkflowEvolutionError(f"workflow path is absent from the frozen P4.3A matrix: {path}")
    history = retirement_ledger if retirement_ledger is not None else retirement.validate_retirement_history()
    if path in set(history.get("retired_workflow_paths", [])):
        return retirement.resolve_reviewed_workflow_source(path, ledger=history)
    if evolution_ledger is None:
        try:
            evolution_ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowEvolutionError("workflow evolution ledger is unreadable") from exc
    revisions = [
        item for item in evolution_ledger.get("transitions", [])
        if item.get("operation") == "MAINTENANCE_REVISE" and item.get("workflow_path") == path
    ]
    if not revisions:
        return retirement.resolve_reviewed_workflow_source(path, ledger=history)
    first = revisions[0]
    expected = {key: row[key] for key in IDENTITY_KEYS}
    if first.get("before") != expected:
        raise WorkflowEvolutionError(f"first maintenance revision does not begin at P4.3A identity: {path}")
    fixture = first.get("historical_before_fixture")
    if not isinstance(fixture, dict):
        raise WorkflowEvolutionError(f"first maintenance revision lacks P4.3A historical bytes: {path}")
    fixture_path = _historical_before_fixture_path(fixture.get("path"))
    if {key: fixture.get(key) for key in IDENTITY_KEYS} != expected:
        raise WorkflowEvolutionError(f"first maintenance fixture identity differs from P4.3A: {path}")
    if historical_fixture_bytes is not None:
        raw = historical_fixture_bytes.get(fixture_path)
        if not isinstance(raw, bytes):
            raise WorkflowEvolutionError(f"P4.3A historical fixture bytes are unavailable: {fixture_path}")
    else:
        raw = _load_maintenance_before_fixtures([first], require_source_controlled=True)[fixture_path]
    if source_identity(raw) != expected:
        raise WorkflowEvolutionError(f"P4.3A historical fixture bytes differ from frozen matrix: {fixture_path}")
    return raw


def validate_derived_tree(expected: Mapping[str, dict[str, str]], observed: Mapping[str, dict[str, str]]) -> None:
    if set(expected) != set(observed):
        raise WorkflowEvolutionError(f"live workflow set differs from reviewed evolution: {sorted(set(expected) ^ set(observed))}")
    for path, identity in expected.items():
        if observed[path] != identity:
            raise WorkflowEvolutionError(f"live workflow identity differs from reviewed evolution: {path}")


def _load_transition_evidence(
    transitions: list[dict[str, Any]],
    current: dict[str, Any],
    *,
    current_retirement: dict[str, Any],
    current_retirement_snapshot: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    receipts: dict[str, dict[str, Any]] = {}
    snapshots: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        path = _evidence_path(transition.get("evidence_receipt_path"))
        snapshot_path = _checkpoint_path(transition.get("checkpoint_snapshot_path"))
        try:
            raw = Path(path).read_bytes()
            receipt = json.loads(raw.decode("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowEvolutionError(f"transition evidence receipt is unreadable: {path}") from exc
        receipt_blob = _git("hash-object", f"--path={path}", path).decode("ascii").strip()
        if receipt_blob != _git("rev-parse", f"HEAD:{path}").decode("ascii").strip():
            raise WorkflowEvolutionError(f"transition evidence receipt is not source-controlled at HEAD: {path}")
        receipts[path] = receipt
        try:
            snapshot_raw = Path(snapshot_path).read_bytes()
            snapshot = json.loads(snapshot_raw.decode("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowEvolutionError(f"transition checkpoint snapshot is unreadable: {snapshot_path}") from exc
        snapshot_blob = _git("hash-object", f"--path={snapshot_path}", snapshot_path).decode("ascii").strip()
        if snapshot_blob != _git("rev-parse", f"HEAD:{snapshot_path}").decode("ascii").strip():
            raise WorkflowEvolutionError(f"transition checkpoint snapshot is not source-controlled at HEAD: {snapshot_path}")
        snapshots[snapshot_path] = snapshot
    validate_transition_checkpoints(
        transitions, current, receipts=receipts, snapshots=snapshots,
        current_retirement=current_retirement,
        current_retirement_snapshot=current_retirement_snapshot,
    )
    return receipts, snapshots


def validate_current_state(
    evolution_ledger: dict[str, Any] | None = None,
    *,
    retirement_ledger: dict[str, Any] | None = None,
    workflow_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    history = retirement_ledger if retirement_ledger is not None else retirement.validate_retirement_history()
    if evolution_ledger is None:
        try:
            evolution_ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowEvolutionError("workflow evolution ledger is unreadable") from exc
    ledger = evolution_ledger
    expected_header = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "base_main_sha": BASE_MAIN_SHA,
        "base_workflow_tree_sha1": BASE_WORKFLOW_TREE_SHA1,
        "base_live_workflow_count": BASE_LIVE_COUNT,
        "p4_3a_matrix_sha256": retirement.MATRIX_SHA256,
        "base_p4_3_retirement_checkpoint_sha256": BASE_RETIREMENT_LEDGER_SHA256,
        "p4_3d_receipt_sha256": P43D_RECEIPT_SHA256,
    }
    if any(ledger.get(key) != value for key, value in expected_header.items()):
        raise WorkflowEvolutionError("workflow evolution base identity changed")
    if set(ledger) != EVOLUTION_LEDGER_FIELDS:
        raise WorkflowEvolutionError("workflow evolution ledger schema fields mismatch")
    if ledger.get("canonical_sha256") != canonical_sha256(ledger):
        raise WorkflowEvolutionError("workflow evolution ledger canonical SHA changed")
    p43d = json.loads(P43D_RECEIPT_PATH.read_text(encoding="utf-8"))
    if p43d.get("canonical_sha256") != P43D_RECEIPT_SHA256 or canonical_sha256(p43d) != P43D_RECEIPT_SHA256:
        raise WorkflowEvolutionError("frozen P4.3D receipt identity changed")
    baseline = baseline_state(history)
    matrix, _ = retirement.load_baseline()
    if ledger.get("current_p4_3_retirement_ledger_sha256") != history.get("canonical_sha256"):
        raise WorkflowEvolutionError("evolution ledger does not bind the current P4.3 retirement ledger")
    if ledger.get("current_p4_3_retired_workflow_count") != history.get("current_retired_workflow_count"):
        raise WorkflowEvolutionError("evolution ledger P4.3 retirement count differs from current validated ledger")
    p43_base_snapshot = retirement._load_p43c_ledger_snapshot()
    p43_snapshot = load_retirement_snapshot_for_evolution(ledger)
    retirement.validate_historical_snapshot_extension(p43_base_snapshot, p43_snapshot)
    retirement.validate_historical_snapshot_extension(p43_snapshot, history)
    if ledger.get("current_p4_3_retired_workflow_count") != p43_snapshot.get("current_retired_workflow_count"):
        raise WorkflowEvolutionError("evolution ledger current P4.3 retired count differs from its snapshot")
    transitions = ledger.get("transitions")
    if not isinstance(transitions, list):
        raise WorkflowEvolutionError("workflow evolution transitions must be a list")
    receipts, _snapshots = _load_transition_evidence(
        transitions, ledger, current_retirement=history,
        current_retirement_snapshot=p43_snapshot,
    )
    historical_before_fixtures = _load_maintenance_before_fixtures(
        transitions,
        require_source_controlled=True,
    )
    baseline_families = {
        row["workflow_path"]: row["successor_family"]
        for row in matrix["workflow_rows"]
    }
    derived = apply_transitions(
        baseline, transitions,
        frozen_baseline_paths=(row["workflow_path"] for row in matrix["workflow_rows"]),
        evidence_receipts=receipts,
        baseline_families=baseline_families,
        historical_before_fixture_bytes=historical_before_fixtures,
    )
    if ledger.get("current_live_workflow_count") != len(derived):
        raise WorkflowEvolutionError("workflow evolution current count does not match transitions")
    tree_sha = ledger.get("current_workflow_tree_sha1")
    if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        raise WorkflowEvolutionError("workflow evolution current tree SHA is invalid")
    if (
        not transitions
        and history["canonical_sha256"] == BASE_RETIREMENT_LEDGER_SHA256
        and (len(derived) != BASE_LIVE_COUNT or tree_sha != BASE_WORKFLOW_TREE_SHA1)
    ):
        raise WorkflowEvolutionError("zero-transition ledger differs from the P4.3D checkpoint")

    real_paths = sorted(path.as_posix() for path in WORKFLOW_DIR.glob("*.yml"))
    all_worktree_files = sorted(path.as_posix() for path in WORKFLOW_DIR.rglob("*") if path.is_file())
    if all_worktree_files != real_paths:
        raise WorkflowEvolutionError("workflow directory contains an unrepresented file")
    supplied = sorted(workflow_paths) if workflow_paths is not None else real_paths
    if supplied != sorted(derived) or real_paths != sorted(derived):
        delta = sorted((set(supplied) ^ set(derived)) | (set(real_paths) ^ set(derived)))
        raise WorkflowEvolutionError(f"live workflow set differs from reviewed evolution: {delta}")
    head_paths = sorted(item.decode("utf-8") for item in _git("ls-tree", "-r", "-z", "--name-only", "HEAD", "--", WORKFLOW_DIR.as_posix()).split(b"\0") if item)
    if head_paths != real_paths:
        raise WorkflowEvolutionError("workflow paths differ between HEAD and working tree")
    if _git("diff", "--name-only", "--", WORKFLOW_DIR.as_posix()):
        raise WorkflowEvolutionError("workflow worktree contains an unreviewed edit")
    head_tree = _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip()
    if head_tree != tree_sha:
        raise WorkflowEvolutionError("workflow tree SHA differs from the evolution ledger")
    observed: dict[str, dict[str, str]] = {}
    for path in real_paths:
        try:
            raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
        except OSError as exc:
            raise WorkflowEvolutionError(f"live workflow is unreadable: {path}") from exc
        identity = source_identity(raw)
        head_blob = _git("rev-parse", f"HEAD:{path}").decode("ascii").strip()
        if identity["git_blob_sha1"] != head_blob:
            raise WorkflowEvolutionError(f"workflow source differs from HEAD: {path}")
        observed[path] = identity
    validate_derived_tree(derived, observed)
    for path in PROTECTED:
        if path not in real_paths or path not in baseline:
            raise WorkflowEvolutionError(f"protected P4.3 workflow is missing or changed: {path}")
    for transition in transitions:
        if transition["operation"] == "RETIRE":
            fixture = transition["historical_fixture"]
            try:
                raw = Path(fixture["path"]).read_bytes()
            except OSError as exc:
                raise WorkflowEvolutionError(f"retired evolved workflow fixture is missing: {fixture['path']}") from exc
            if source_identity(raw) != {key: fixture[key] for key in IDENTITY_KEYS}:
                raise WorkflowEvolutionError(f"retired evolved workflow fixture drifted: {fixture['path']}")
    return ledger


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate committed current workflow state offline")
    parser.parse_args()
    ledger = validate_current_state()
    print(ledger["canonical_sha256"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P4_WORKFLOW_EVOLUTION_LEDGER_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
