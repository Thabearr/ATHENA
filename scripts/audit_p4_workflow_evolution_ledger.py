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
BASE_RETIREMENT_LEDGER_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
P43D_RECEIPT_SHA256 = "4b43e084f82f65330429388732990ed8e49abe8e05fd30fc57a319a210dfb25f"
LEDGER_PATH = Path("artifacts/architecture/p4_workflow_evolution_ledger_v1.json")
P43D_RECEIPT_PATH = Path("artifacts/architecture/p4_3d_retirement_audit_extensibility_v1.json")
WORKFLOW_DIR = Path(".github/workflows")
FAMILIES = {"ATHENA_RUN", "ATHENA_INGEST", "ATHENA_RETRAIN", "ATHENA_BACKTEST", "TESTS", "ATHENA_PR_BRIDGE"}
PROTECTED = retirement.PROTECTED_LIVE | {".github/workflows/current-shadow-sportybet-source-diagnostic.yml"}
IDENTITY_KEYS = {"git_blob_sha1", "source_sha256"}
TRANSITION_KEYS = {
    "transition_id", "operation", "workflow_path", "before", "after",
    "phase_id", "canonical_family", "evidence_receipt_path", "evidence_body_sha256",
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


def baseline_state(retirement_ledger: dict[str, Any]) -> dict[str, dict[str, str]]:
    matrix, _ = retirement.load_baseline()
    retired = set(retirement_ledger["retired_workflow_paths"])
    state = {
        row["workflow_path"]: {
            "git_blob_sha1": row["git_blob_sha1"],
            "source_sha256": row["source_sha256"],
        }
        for row in matrix["workflow_rows"] if row["workflow_path"] not in retired
    }
    if len(state) != BASE_LIVE_COUNT or retirement_ledger["canonical_sha256"] != BASE_RETIREMENT_LEDGER_SHA256:
        raise WorkflowEvolutionError("P4.3D starting workflow state changed")
    return state


def apply_transitions(
    starting_state: Mapping[str, dict[str, str]],
    transitions: list[dict[str, Any]],
    *,
    frozen_baseline_paths: Iterable[str],
    evidence_receipts: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Pure ordered evaluator; callers separately check the derived Git tree."""
    if not isinstance(transitions, list):
        raise WorkflowEvolutionError("workflow evolution transitions must be a list")
    state = {path: dict(identity) for path, identity in starting_state.items()}
    frozen = set(frozen_baseline_paths)
    introduced: set[str] = set()
    identifiers: set[str] = set()
    for transition in transitions:
        if not isinstance(transition, dict):
            raise WorkflowEvolutionError("workflow transition must be an object")
        operation = transition.get("operation")
        required = TRANSITION_KEYS | ({"historical_fixture"} if operation == "RETIRE" else set())
        if set(transition) != required or operation not in {"ADD", "REVISE", "RETIRE"}:
            raise WorkflowEvolutionError("workflow transition schema/operation is not reviewed")
        path = _workflow_path(transition["workflow_path"])
        identifier = transition["transition_id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Z0-9_.-]+", identifier) or identifier in identifiers:
            raise WorkflowEvolutionError(f"duplicate or invalid workflow transition identifier: {identifier}")
        identifiers.add(identifier)
        phase = transition["phase_id"]
        if not isinstance(phase, str) or not re.fullmatch(r"P[0-9]+(?:\.[0-9]+)?[A-Z0-9_.-]*", phase):
            raise WorkflowEvolutionError(f"workflow transition phase is invalid: {path}")
        if transition["canonical_family"] not in FAMILIES:
            raise WorkflowEvolutionError(f"workflow transition canonical family is invalid: {path}")
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
        else:
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
    return state


def validate_derived_tree(expected: Mapping[str, dict[str, str]], observed: Mapping[str, dict[str, str]]) -> None:
    if set(expected) != set(observed):
        raise WorkflowEvolutionError(f"live workflow set differs from reviewed evolution: {sorted(set(expected) ^ set(observed))}")
    for path, identity in expected.items():
        if observed[path] != identity:
            raise WorkflowEvolutionError(f"live workflow identity differs from reviewed evolution: {path}")


def _load_transition_receipts(transitions: list[dict[str, Any]], ledger_sha: str) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for index, transition in enumerate(transitions):
        path = _evidence_path(transition.get("evidence_receipt_path"))
        try:
            raw = Path(path).read_bytes()
            receipt = json.loads(raw.decode("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowEvolutionError(f"transition evidence receipt is unreadable: {path}") from exc
        worktree_blob = _git("hash-object", f"--path={path}", path).decode("ascii").strip()
        if worktree_blob != _git("rev-parse", f"HEAD:{path}").decode("ascii").strip():
            raise WorkflowEvolutionError(f"transition evidence receipt is not source-controlled at HEAD: {path}")
        backlink = receipt.get("workflow_evolution_ledger_sha256")
        if not isinstance(backlink, str) or not re.fullmatch(r"[0-9a-f]{64}", backlink):
            raise WorkflowEvolutionError(f"transition receipt lacks an evolution-ledger checkpoint: {path}")
        # Older receipts bind their immutable phase checkpoints. Only the newest
        # transition's receipt binds the current cumulative ledger, so a later
        # reviewed append does not invalidate earlier phase evidence.
        if index == len(transitions) - 1 and backlink != ledger_sha:
            raise WorkflowEvolutionError(f"latest transition receipt does not bind current evolution ledger: {path}")
        receipts[path] = receipt
    return receipts


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
        "p4_3_retirement_ledger_sha256": BASE_RETIREMENT_LEDGER_SHA256,
        "p4_3d_receipt_sha256": P43D_RECEIPT_SHA256,
    }
    if any(ledger.get(key) != value for key, value in expected_header.items()):
        raise WorkflowEvolutionError("workflow evolution base identity changed")
    if ledger.get("canonical_sha256") != canonical_sha256(ledger):
        raise WorkflowEvolutionError("workflow evolution ledger canonical SHA changed")
    p43d = json.loads(P43D_RECEIPT_PATH.read_text(encoding="utf-8"))
    if p43d.get("canonical_sha256") != P43D_RECEIPT_SHA256 or canonical_sha256(p43d) != P43D_RECEIPT_SHA256:
        raise WorkflowEvolutionError("frozen P4.3D receipt identity changed")
    baseline = baseline_state(history)
    matrix, _ = retirement.load_baseline()
    transitions = ledger.get("transitions")
    if not isinstance(transitions, list):
        raise WorkflowEvolutionError("workflow evolution transitions must be a list")
    receipts = _load_transition_receipts(transitions, ledger["canonical_sha256"])
    derived = apply_transitions(
        baseline, transitions,
        frozen_baseline_paths=(row["workflow_path"] for row in matrix["workflow_rows"]),
        evidence_receipts=receipts,
    )
    if ledger.get("current_live_workflow_count") != len(derived):
        raise WorkflowEvolutionError("workflow evolution current count does not match transitions")
    tree_sha = ledger.get("current_workflow_tree_sha1")
    if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        raise WorkflowEvolutionError("workflow evolution current tree SHA is invalid")
    if not transitions and (len(derived) != BASE_LIVE_COUNT or tree_sha != BASE_WORKFLOW_TREE_SHA1):
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
        if path in baseline:
            raw = retirement.resolve_reviewed_workflow_source(path, ledger=history)
        else:
            raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
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
