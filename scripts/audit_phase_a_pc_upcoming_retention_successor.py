"""Path-exact outer P4/D5 adapter for the owner-authorized retention successor.

Frozen P4/D5 trees and ledgers are inputs, never new computed baselines. This
adapter grants no provider, delivery, trigger or model authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_P4_PHASE_A_LEGACY_PC_UPCOMING_RETENTION_MAINTENANCE_V1"
WORKFLOW = ".github/workflows/current-shadow-all-market.yml"
FIXTURE = "tests/fixtures/architecture/revised_workflows/current-shadow-all-market-pre-phase-a-retention.yml"
RECEIPT = "artifacts/architecture/phase_a_pc_upcoming_retention_successor_v1.json"
SNAPSHOT = "artifacts/architecture/p4_workflow_evolution_snapshots/phase_a_pc_upcoming_retention_v1.json"
RECEIPT_SHA256 = 'c4fbdf3e58e5c875ded1abcd15c4845477718e070ffbd095ae5c8ef7b90b2004'
SNAPSHOT_SHA256 = '6737352ea366dc4afad07d8fe65c8f742b671b7a7a3e0f9bc809da8d7cdab2a2'
BEFORE_TREE = 'dd036de270aed14acc7f587ef8148d3ddc1895f5'
AFTER_TREE = '77c3a70e38833756766e43a4a31ba2a7cc55a45d'
BEFORE_B4_TREE = '44b057e5f711cceb0f975a90ee430eaf242fdedf'
AFTER_B4_TREE = 'dd703507488f1495767b8e0055d71a9f488390bf'
BEFORE = {'git_blob_sha1': 'a06a3166322ccb92b0bc3c05c87c5b3ca17298e1', 'source_sha256': '755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c', 'byte_count': 11410}
AFTER = {'git_blob_sha1': 'c6ca37afc8d35e9e16ccb9c66581b96b1107abf6', 'source_sha256': 'b555f7d602b5a6fc98f38d136d83ab22733c1ad9b64d7045bc1f771651551593', 'byte_count': 10830}
PREDECESSORS = {'scripts/audit_data_01c_restore_portability.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/audit_data_01c_restore_portability.py.txt', 'git_blob_sha1': 'b6c22fd9c3bc9d120156dcc29d2dfcb4652d92da', 'source_sha256': 'bcf86a01b10255bbb629b95f16b4a13e0da9947893afb13916c6f6a0972fa89e', 'byte_count': 21223}, 'scripts/audit_p4_workflow_evolution_ledger.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/audit_p4_workflow_evolution_ledger.py.txt', 'git_blob_sha1': 'caf54adbed0a16460148c8a19466d24243be8d1b', 'source_sha256': '6666440cfb69261a33bccf70a3e52a19d60c36b045163fbcc8918084958042c9', 'byte_count': 67041}}


def _read(path):
    target = ROOT / path
    if target.is_symlink() or not target.is_file():
        raise ValueError("retention successor evidence is missing or linked: " + path)
    return target.read_bytes().replace(b"\r\n", b"\n")


def identity(raw):
    return {"git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
            "source_sha256": hashlib.sha256(raw).hexdigest(), "byte_count": len(raw)}


def _json(path, expected):
    from scripts import audit_p4_workflow_evolution_ledger as p4
    value = json.loads(_read(path))
    if value.get("canonical_sha256") != expected or p4.canonical_sha256(value) != expected:
        raise ValueError("retention successor receipt/snapshot identity drift: " + path)
    return value


def expected_workflow():
    before = _read(FIXTURE)
    if identity(before) != BEFORE:
        raise ValueError("retention historical workflow predecessor changed")
    start = before.index(b"      - name: Preserve exact current source evidence")
    end = before.index(b"      - name: Email durable Shadow result", start)
    replacement = b"""      - name: Preserve exact current source evidence
        id: preserve_shadow_evidence
        if: always()
        run: python -m scripts.verify_current_shadow_pc_upcoming_archive --preserve

      - name: Verify pcUpcoming archive
        id: verify_shadow_archive
        if: always()
        run: python -m scripts.verify_current_shadow_pc_upcoming_archive

"""
    after = before[:start] + replacement + before[end:]
    after = after.replace(
        b"      - name: Email durable Shadow result when configured\n        if: always()",
        b"      - name: Email durable Shadow result when configured\n        if: always() && steps.preserve_shadow_evidence.outcome == 'success' && steps.verify_shadow_archive.outcome == 'success'",
    )
    if identity(after) != AFTER:
        raise ValueError("retention successor recipe is not the exact reviewed delta")
    return after


def authenticate():
    from scripts import audit_p4_workflow_evolution_ledger as p4
    receipt = _json(RECEIPT, RECEIPT_SHA256)
    snapshot = _json(SNAPSHOT, SNAPSHOT_SHA256)
    for path, row in PREDECESSORS.items():
        if identity(_read(row["fixture"])) != {key: row[key] for key in BEFORE}:
            raise ValueError("retention audit source predecessor changed: " + path)
    original = _json(p4.LEDGER_PATH.as_posix(), receipt["historical_p4_ledger_sha256"])
    if snapshot["transitions"][:-1] != original["transitions"]:
        raise ValueError("retention successor rewrites the immutable P4 prefix")
    allowed = {"transitions", "current_workflow_tree_sha1", "canonical_sha256"}
    if {k:v for k,v in snapshot.items() if k not in allowed} != {
            k:v for k,v in original.items() if k not in allowed}:
        raise ValueError("retention successor changes a frozen checkpoint")
    transition = snapshot["transitions"][-1]
    before = {key: BEFORE[key] for key in p4.IDENTITY_KEYS}
    after = {key: AFTER[key] for key in p4.IDENTITY_KEYS}
    contract = {**p4.MAINTENANCE_CONTRACT, "policy_id": POLICY_ID}
    if transition["workflow_path"] != WORKFLOW or transition["maintenance_contract"] != contract:
        raise ValueError("retention maintenance is reserved for one exact path")
    evaluated = p4.apply_transitions(
        {WORKFLOW: before}, [transition], frozen_baseline_paths={WORKFLOW},
        baseline_families={WORKFLOW: "ATHENA_RUN"},
        evidence_receipts={RECEIPT: receipt},
        historical_before_fixture_bytes={FIXTURE: _read(FIXTURE)},
    )
    if evaluated != {WORKFLOW: after} or snapshot["current_workflow_tree_sha1"] != AFTER_TREE:
        raise ValueError("retention transition does not derive the exact successor")
    if _read(WORKFLOW) != expected_workflow():
        raise ValueError("legacy workflow differs from the path-exact retention successor")
    raw_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD:.github/workflows"], cwd=ROOT, text=True).strip()
    if raw_tree != AFTER_TREE or subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD", "--", ".github/workflows"], cwd=ROOT).strip():
        raise ValueError("retention successor tree or worktree changed")
    return receipt


def project_b4_tree(observed):
    """Add precisely one current edge; every old B4/D5 identity stays pinned."""
    if observed != AFTER_B4_TREE:
        return observed
    authenticate()
    return BEFORE_B4_TREE


def project_p4_observed(observed, head_tree):
    if head_tree != AFTER_TREE:
        return None
    authenticate()
    before = {key: BEFORE[key] for key in ("git_blob_sha1", "source_sha256")}
    after = {key: AFTER[key] for key in before}
    if observed.get(WORKFLOW) != after:
        raise ValueError("retention observed workflow identity mismatch")
    result = dict(observed)
    result[WORKFLOW] = before
    return result
