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

B4_FORWARD_RECEIPT = 'artifacts/architecture/phase_a_retention_b4_consumer_source_forward_v1.json'
B4_FORWARD_SHA256 = 'be8b3b433e821bdf6d173478b360bb0d526b23a45496d98148625c6508c6406e'
B4_FORWARD_BEFORE = {'git_blob_sha1': '89fb32e561660a3dcdc70ae6d1df94f9d40027c9', 'source_sha256': '8d92fa8507535b6c42620458eac1ab6a2073574bf7d483a2e2d5deba1719d05f', 'byte_count': 52479}
B4_FORWARD_AFTER = {'git_blob_sha1': '192bf0bd3210236a38b66daf733f334b4e600a40', 'source_sha256': '33f006fedecd79ebdbcb78d08a12ea1bdf2992ea3030af49b8e85fda2ebb0638', 'byte_count': 52848}
B4_FORWARD_FIXTURE = 'tests/fixtures/architecture/phase_a_retention/audit_core_01d_sportybet_current_trigger_authority_b4.py.txt'
B4_FORWARD_SOURCE = 'scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py'


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
    forward = _json(B4_FORWARD_RECEIPT, B4_FORWARD_SHA256)
    if (forward["retention_receipt_sha256"] != RECEIPT_SHA256
            or identity(_read(B4_FORWARD_FIXTURE)) != B4_FORWARD_BEFORE
            or identity(_read(B4_FORWARD_SOURCE)) != B4_FORWARD_AFTER):
        raise ValueError("retention B4 consumer source-forward drift")
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
    if raw_tree != AFTER_TREE:
        raise ValueError("retention successor tree changed")
    # Recompute the one-path inverse from HEAD; no ancestor object or mutable
    # newly computed baseline is trusted, including in depth-one hosted CI.
    entries = subprocess.check_output(["git", "ls-tree", raw_tree], cwd=ROOT)
    body = b""
    replaced = 0
    for line in entries.splitlines():
        header, name = line.split(b"\t", 1)
        mode, kind, blob = header.split()
        if name.decode("utf-8") == Path(WORKFLOW).name:
            if mode != b"100644" or kind != b"blob" or blob.decode() != AFTER["git_blob_sha1"]:
                raise ValueError("retention successor workflow mode/blob mismatch")
            blob = BEFORE["git_blob_sha1"].encode()
            replaced += 1
        body += mode + b" " + name + b"\0" + bytes.fromhex(blob.decode())
    inverse = hashlib.sha1(b"tree " + str(len(body)).encode() + b"\0" + body).hexdigest()
    if replaced != 1 or inverse != BEFORE_TREE:
        raise ValueError("retention successor is not the exact one-path replacement")
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
    if WORKFLOW not in observed:
        return dict(observed)  # authenticated partial evaluator view
    if observed.get(WORKFLOW) != after:
        raise ValueError("retention observed workflow identity mismatch")
    result = dict(observed)
    result[WORKFLOW] = before
    return result


CHECKPOINT_V2_PATH = "scripts/audit_core_01d_checkpoint_e_completion_v2.py"
V313_CHECKPOINT_BLOB = "3768669aaa4400ead8cdf63978bf6da953b0062e"
V313_CHECKPOINT_SHA256 = "c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1"


def checkpoint_v2_retention_sources():
    """Exact old V313 source and one bounded, independently derived successor."""
    from runtime.source_identity import read_tracked_head_blob
    descriptor = HISTORICAL_PREDECESSORS[CHECKPOINT_V2_PATH]
    modes = subprocess.check_output(
        ["git", "ls-tree", "-r", "HEAD", "--", CHECKPOINT_V2_PATH, descriptor["fixture"]], cwd=ROOT)
    if len(modes.splitlines()) != 2 or any(
            line.split(b"\t", 1)[0].split()[:2] != [b"100644", b"blob"] for line in modes.splitlines()):
        raise ValueError("V313 retention source/fixture mode changed")
    before, old_identity = read_tracked_head_blob(ROOT, descriptor["fixture"])
    before = before.replace(b"\r\n", b"\n")
    if (old_identity.git_blob_sha1 != V313_CHECKPOINT_BLOB
            or hashlib.sha256(before).hexdigest() != V313_CHECKPOINT_SHA256):
        raise ValueError("frozen V313 checkpoint predecessor drift")
    old = b" return b''.join(rows)\n"
    new = b""" from scripts import audit_phase_a_pc_upcoming_retention_successor as forward
 try:
  return forward.project_retention_inventory(b''.join(rows), latest=latest)
 except ValueError as exc:
  review.require(False, 'retention inventory projection failed: '+str(exc))
"""
    if before.count(old) != 1:
        raise ValueError("V313 source-forward seam is not exact")
    expected = before.replace(old, new)
    current, observed = read_tracked_head_blob(ROOT, CHECKPOINT_V2_PATH)
    if current.replace(b"\r\n", b"\n") != expected or observed.git_blob_sha1 != identity(expected)["git_blob_sha1"]:
        raise ValueError("current checkpoint exceeds the exact retention source-forward")
    return before, expected


def checkpoint_v340_extension(chain):
    """Append only after independently pinned V339; V313 remains unchanged."""
    if len(chain) < 339 or chain[338][1]["canonical_sha256"] != "615df8a5c9af6eecdd95476010f9aa6ed238cc0d0fdb02874b0c1040ea992098":
        raise ValueError("retention source-forward does not extend exact V339")
    before, expected = checkpoint_v2_retention_sources()
    after = identity(expected)
    return {
        "path": CHECKPOINT_V2_PATH, "generation": 340,
        "predecessor_inventory": {"path": "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v339.json",
            "generation": 339, "canonical_sha256": chain[338][1]["canonical_sha256"], "rewritten": False},
        "previous_successor": {"generation": 313, "canonical_sha256": chain[312][1]["canonical_sha256"],
            "git_blob_sha1": V313_CHECKPOINT_BLOB, "lf_source_sha256": V313_CHECKPOINT_SHA256, "rewritten": False},
        "successor": {"git_blob_sha1": after["git_blob_sha1"], "lf_source_sha256": after["source_sha256"], "git_mode": "100644"},
        "reason_type": "PHASE_A_RETENTION_HISTORICAL_CONSUMER_SOURCE_FORWARD_V340",
        "reason": "Authenticate the exact retention-only outer projection after the unchanged V313 historical evaluator",
        "authority_granted": False, "historical_bytes_changed": False, "rewritten": False,
    }


# Pinned historical views only; never substituted into production execution.
HISTORICAL_FORWARD_RECEIPT = 'artifacts/architecture/phase_a_retention_historical_consumers_source_forward_v1.json'
HISTORICAL_FORWARD_SHA256 = '981e295c0b640e23f90a688fb90d041a85be9498774e4a2a6f67acf60201ca82'
HISTORICAL_PREDECESSORS = {'.github/workflows/current-shadow-all-market.yml': {'fixture': 'tests/fixtures/architecture/revised_workflows/current-shadow-all-market-pre-phase-a-retention.yml', 'git_blob_sha1': 'a06a3166322ccb92b0bc3c05c87c5b3ca17298e1', 'source_sha256': '755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c', 'byte_count': 11410}, 'scripts/audit_core_01d_authority_reachability_review_a.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_authority_reachability_review_a.py.txt', 'git_blob_sha1': '6597bfbe31097629cff75c5d112cb70da74fbdb0', 'source_sha256': 'd9942b3c72564ad21ae3734bb23eccc0a9bec66d133b89afa77aae6b866b6f00', 'byte_count': 46459}, 'scripts/audit_core_01d_checkpoint_e_completion.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion.py.txt', 'git_blob_sha1': '5276be74f83f41290b8057102dce72a5d0eac763', 'source_sha256': 'cee34e27efb29c5fa1eb0b6f2cacfe8d122146ecc05468481c9eb68e09f91557', 'byte_count': 46390}, 'scripts/audit_core_01d_checkpoint_e_completion_v2.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion_v2.py.txt', 'git_blob_sha1': '3768669aaa4400ead8cdf63978bf6da953b0062e', 'source_sha256': 'c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1', 'byte_count': 47417}, 'scripts/audit_core_01d_ci_offline_transport_boundary.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_ci_offline_transport_boundary.py.txt', 'git_blob_sha1': '56284d65b613efe4c1f63ae48a413cbf5e73401c', 'source_sha256': '3a42c6e50fddecd482cb8e6dd3758e8c58f453885e133ecf68798f0a51832404', 'byte_count': 173944}, 'scripts/audit_core_01d_scheduled_shadow_ownership.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_scheduled_shadow_ownership.py.txt', 'git_blob_sha1': '5b4308f82d70d9911af31893816aa438d17e5f77', 'source_sha256': '0ccc51313625e334f09ef0c2194d65273acfc47ea21bc1802bdea8a79c53d4e2', 'byte_count': 28556}, 'scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_sportybet_current_trigger_authority_b4.py.txt', 'git_blob_sha1': '89fb32e561660a3dcdc70ae6d1df94f9d40027c9', 'source_sha256': '8d92fa8507535b6c42620458eac1ab6a2073574bf7d483a2e2d5deba1719d05f', 'byte_count': 52479}, 'scripts/audit_data_01c_app_store_complete.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_app_store_complete.py.txt', 'git_blob_sha1': '529ac14a62467528937047f26d1a2f0283cf0969', 'source_sha256': '3c9c6cf2c2a01ccead15cd5d10c097b574e6607a8cc1d88dd752b9f557441f89', 'byte_count': 27640}, 'scripts/audit_data_01c_restore_portability.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_restore_portability.py.txt', 'git_blob_sha1': 'b6c22fd9c3bc9d120156dcc29d2dfcb4652d92da', 'source_sha256': 'bcf86a01b10255bbb629b95f16b4a13e0da9947893afb13916c6f6a0972fa89e', 'byte_count': 21223}, 'scripts/audit_p4_workflow_evolution_ledger.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_p4_workflow_evolution_ledger.py.txt', 'git_blob_sha1': 'caf54adbed0a16460148c8a19466d24243be8d1b', 'source_sha256': '6666440cfb69261a33bccf70a3e52a19d60c36b045163fbcc8918084958042c9', 'byte_count': 67041}, 'scripts/core_01d_historical_source.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--core_01d_historical_source.py.txt', 'git_blob_sha1': '7548914b31ceb832b55818e66c19b8a9bd606927', 'source_sha256': '5c46e7b5011de91c540fbbff9b7c06f15a81c87097ef07838d045123ae948865', 'byte_count': 2688}, 'tests/native/test_port_02c_audit_source_forward.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--native--test_port_02c_audit_source_forward.py.txt', 'git_blob_sha1': '2f28342ee0b692c0826de6b89cdcc480484dda03', 'source_sha256': '1433204108937e464f6ca2e9bfa8d49e5438ef25304f77630eac819d744332d1', 'byte_count': 4701}, 'tests/test_core_01d_exact_pr_trigger_disposition_b1.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_exact_pr_trigger_disposition_b1.py.txt', 'git_blob_sha1': 'e12005ddef615f601bfaa6602b6896eee5e10e79', 'source_sha256': 'f737758dc591fc14474f83ef7eae6a22258d7572eeae52f02c8cacad0f3c45df', 'byte_count': 14680}, 'tests/test_core_01d_pass_a_v300_source_predecessors.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_pass_a_v300_source_predecessors.py.txt', 'git_blob_sha1': '322f72ac3cfef2ed7ea54b8f13ec5e00bb5b590e', 'source_sha256': '19586a4e89395d3a3521dd3616e373c696d7df67896b48e5e6a4b72ce1004101', 'byte_count': 24985}, 'tests/test_core_01d_sportybet_current_trigger_authority_b4.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_sportybet_current_trigger_authority_b4.py.txt', 'git_blob_sha1': '15dab8589224352f089f0c919a762cf7e2fa3bb0', 'source_sha256': '1e8697f032e3d3dc615b5cc138df1bc332d09ef6ce5303571983c393786fb775', 'byte_count': 40849}, 'tests/test_p4_2_athena_run_workflow.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_2_athena_run_workflow.py.txt', 'git_blob_sha1': 'c8d83b0c39c8d8eff4abf698405e26d60bbeefbf', 'source_sha256': '9502109759e17534bc11ce2052e6fa6f7852513f8118b0194af186349f626f70', 'byte_count': 11804}, 'tests/test_p4_4a_workflow_evolution_guard.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_4a_workflow_evolution_guard.py.txt', 'git_blob_sha1': '4a4dcbd36a6f1892cdec195ed460aab95965aeee', 'source_sha256': 'cc3b5a48d658b32d4ff14bde55168b9a2f229217efffc3636de3560c97e44409', 'byte_count': 17014}}
ADDED_PYTHON_PATHS = frozenset(['scripts/audit_phase_a_pc_upcoming_retention_successor.py', 'scripts/verify_current_shadow_pc_upcoming_archive.py', 'tests/test_current_shadow_pc_upcoming_archive_retention.py'])
ADDED_METADATA = {'artifacts/architecture/p4_workflow_evolution_snapshots/phase_a_pc_upcoming_retention_v1.json': {'git_blob_sha1': '8023cc82b910275acaaaf20c4b925b5297b0e9b8', 'source_sha256': '65ecf785ed61b9919cca48cdcddf66c9dea25fc57b73d52961cb1757ace1b329', 'byte_count': 23263}, 'artifacts/architecture/phase_a_pc_upcoming_retention_successor_v1.json': {'git_blob_sha1': '38aca4fd51efd3adc41a13d12b04755c57a19431', 'source_sha256': 'd9faba74bb89ef2513773319d3cc3e2da7da12aed9cc9b1eeea5f5b7e3f583a1', 'byte_count': 3569}, 'artifacts/architecture/phase_a_retention_b4_consumer_source_forward_v1.json': {'git_blob_sha1': '5907680d64d423402413097815b516ea6d69e392', 'source_sha256': '54dd5c5792fb9ec5c7ed76dadb2896c1a4cbf47136224b8f104886d90153f2f9', 'byte_count': 1063}, 'artifacts/architecture/phase_a_retention_historical_consumers_source_forward_v1.json': {'git_blob_sha1': 'eee13122ef58baccf7105ea5721c1bfd1ffe72ac', 'source_sha256': '7fa365d8473724b1270d8947cb02109439af45b371e3d057ec82cbeb84067f0a', 'byte_count': 6744}, 'docs/engineering/shadow_quality_2026_10_22_provisional.txt': {'git_blob_sha1': '03ae2899be7cbb5ddadad204db3e24eaa46c4793', 'source_sha256': '0642e9e2a33d1a3a60ffb58efc0b422661d2e4b7eeffcf1d39283ae8072dbaf1', 'byte_count': 7149}, 'tests/fixtures/architecture/phase_a_retention/audit_core_01d_sportybet_current_trigger_authority_b4.py.txt': {'git_blob_sha1': '89fb32e561660a3dcdc70ae6d1df94f9d40027c9', 'source_sha256': '8d92fa8507535b6c42620458eac1ab6a2073574bf7d483a2e2d5deba1719d05f', 'byte_count': 52479}, 'tests/fixtures/architecture/phase_a_retention/audit_data_01c_restore_portability.py.txt': {'git_blob_sha1': 'b6c22fd9c3bc9d120156dcc29d2dfcb4652d92da', 'source_sha256': 'bcf86a01b10255bbb629b95f16b4a13e0da9947893afb13916c6f6a0972fa89e', 'byte_count': 21223}, 'tests/fixtures/architecture/phase_a_retention/audit_p4_workflow_evolution_ledger.py.txt': {'git_blob_sha1': 'caf54adbed0a16460148c8a19466d24243be8d1b', 'source_sha256': '6666440cfb69261a33bccf70a3e52a19d60c36b045163fbcc8918084958042c9', 'byte_count': 67041}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_authority_reachability_review_a.py.txt': {'git_blob_sha1': '6597bfbe31097629cff75c5d112cb70da74fbdb0', 'source_sha256': 'd9942b3c72564ad21ae3734bb23eccc0a9bec66d133b89afa77aae6b866b6f00', 'byte_count': 46459}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion.py.txt': {'git_blob_sha1': '5276be74f83f41290b8057102dce72a5d0eac763', 'source_sha256': 'cee34e27efb29c5fa1eb0b6f2cacfe8d122146ecc05468481c9eb68e09f91557', 'byte_count': 46390}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion_v2.py.txt': {'git_blob_sha1': '3768669aaa4400ead8cdf63978bf6da953b0062e', 'source_sha256': 'c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1', 'byte_count': 47417}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_ci_offline_transport_boundary.py.txt': {'git_blob_sha1': '56284d65b613efe4c1f63ae48a413cbf5e73401c', 'source_sha256': '3a42c6e50fddecd482cb8e6dd3758e8c58f453885e133ecf68798f0a51832404', 'byte_count': 173944}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_scheduled_shadow_ownership.py.txt': {'git_blob_sha1': '5b4308f82d70d9911af31893816aa438d17e5f77', 'source_sha256': '0ccc51313625e334f09ef0c2194d65273acfc47ea21bc1802bdea8a79c53d4e2', 'byte_count': 28556}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_sportybet_current_trigger_authority_b4.py.txt': {'git_blob_sha1': '89fb32e561660a3dcdc70ae6d1df94f9d40027c9', 'source_sha256': '8d92fa8507535b6c42620458eac1ab6a2073574bf7d483a2e2d5deba1719d05f', 'byte_count': 52479}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_app_store_complete.py.txt': {'git_blob_sha1': '529ac14a62467528937047f26d1a2f0283cf0969', 'source_sha256': '3c9c6cf2c2a01ccead15cd5d10c097b574e6607a8cc1d88dd752b9f557441f89', 'byte_count': 27640}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_restore_portability.py.txt': {'git_blob_sha1': 'b6c22fd9c3bc9d120156dcc29d2dfcb4652d92da', 'source_sha256': 'bcf86a01b10255bbb629b95f16b4a13e0da9947893afb13916c6f6a0972fa89e', 'byte_count': 21223}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_p4_workflow_evolution_ledger.py.txt': {'git_blob_sha1': 'caf54adbed0a16460148c8a19466d24243be8d1b', 'source_sha256': '6666440cfb69261a33bccf70a3e52a19d60c36b045163fbcc8918084958042c9', 'byte_count': 67041}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--core_01d_historical_source.py.txt': {'git_blob_sha1': '7548914b31ceb832b55818e66c19b8a9bd606927', 'source_sha256': '5c46e7b5011de91c540fbbff9b7c06f15a81c87097ef07838d045123ae948865', 'byte_count': 2688}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--native--test_port_02c_audit_source_forward.py.txt': {'git_blob_sha1': '2f28342ee0b692c0826de6b89cdcc480484dda03', 'source_sha256': '1433204108937e464f6ca2e9bfa8d49e5438ef25304f77630eac819d744332d1', 'byte_count': 4701}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_exact_pr_trigger_disposition_b1.py.txt': {'git_blob_sha1': 'e12005ddef615f601bfaa6602b6896eee5e10e79', 'source_sha256': 'f737758dc591fc14474f83ef7eae6a22258d7572eeae52f02c8cacad0f3c45df', 'byte_count': 14680}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_pass_a_v300_source_predecessors.py.txt': {'git_blob_sha1': '322f72ac3cfef2ed7ea54b8f13ec5e00bb5b590e', 'source_sha256': '19586a4e89395d3a3521dd3616e373c696d7df67896b48e5e6a4b72ce1004101', 'byte_count': 24985}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_sportybet_current_trigger_authority_b4.py.txt': {'git_blob_sha1': '15dab8589224352f089f0c919a762cf7e2fa3bb0', 'source_sha256': '1e8697f032e3d3dc615b5cc138df1bc332d09ef6ce5303571983c393786fb775', 'byte_count': 40849}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_2_athena_run_workflow.py.txt': {'git_blob_sha1': 'c8d83b0c39c8d8eff4abf698405e26d60bbeefbf', 'source_sha256': '9502109759e17534bc11ce2052e6fa6f7852513f8118b0194af186349f626f70', 'byte_count': 11804}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_4a_workflow_evolution_guard.py.txt': {'git_blob_sha1': '4a4dcbd36a6f1892cdec195ed460aab95965aeee', 'source_sha256': 'cc3b5a48d658b32d4ff14bde55168b9a2f229217efffc3636de3560c97e44409', 'byte_count': 17014}, 'tests/fixtures/architecture/revised_workflows/current-shadow-all-market-pre-phase-a-retention.yml': {'git_blob_sha1': 'a06a3166322ccb92b0bc3c05c87c5b3ca17298e1', 'source_sha256': '755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c', 'byte_count': 11410}}


def project_retention_inventory(raw, *, latest=None):
    """Compose only this exact successor AFTER older historical projections.

    New files disappear only after their precise identities are verified. An
    existing row is restored only if it still names the current HEAD blob;
    already-authenticated older views remain untouched. Unknown rows survive
    and are rejected by the caller's unchanged historical inventory digest.
    """
    from runtime.source_identity import read_tracked_head_blob
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    authenticate()
    _json(HISTORICAL_FORWARD_RECEIPT, HISTORICAL_FORWARD_SHA256)
    if latest is None:
        latest = a2.authenticate_inventory()
    if latest.get("generation", 0) < 340:
        raise ValueError("historical retention projection requires its A2 successor")
    expected_paths = (set(HISTORICAL_PREDECESSORS) | set(ADDED_PYTHON_PATHS) | set(ADDED_METADATA)
                      | {value["fixture"] for value in HISTORICAL_PREDECESSORS.values()})
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD", "--", *sorted(expected_paths)], cwd=ROOT)
    modes = {line.split(b"\t", 1)[1].decode(): line.split(b"\t", 1)[0].split()[:2]
             for line in tree.splitlines()}
    if set(modes) != expected_paths or any(value != [b"100644", b"blob"] for value in modes.values()):
        raise ValueError("retention source/evidence inventory mode changed")
    current_rows = {row["path"]: row["lf_source_sha256"] for row in latest["source_identities"]}
    current_blobs = {}
    for path in set(HISTORICAL_PREDECESSORS) | set(ADDED_PYTHON_PATHS):
        payload, observed = read_tracked_head_blob(ROOT, path)
        payload = payload.replace(b"\r\n", b"\n")
        if path.endswith(".py") and current_rows.get(path) != hashlib.sha256(payload).hexdigest():
            raise ValueError("retention current source is not A2 authenticated: " + path)
        if path == WORKFLOW and payload != expected_workflow():
            raise ValueError("retention workflow projection source drift")
        current_blobs[path] = observed.git_blob_sha1
    for path, descriptor in HISTORICAL_PREDECESSORS.items():
        payload, observed = read_tracked_head_blob(ROOT, descriptor["fixture"])
        if identity(payload.replace(b"\r\n", b"\n")) != {
                key: descriptor[key] for key in BEFORE} or observed.git_blob_sha1 != descriptor["git_blob_sha1"]:
            raise ValueError("retention historical predecessor drift: " + path)
    for path, expected in ADDED_METADATA.items():
        payload, observed = read_tracked_head_blob(ROOT, path)
        if identity(payload.replace(b"\r\n", b"\n")) != expected or observed.git_blob_sha1 != expected["git_blob_sha1"]:
            raise ValueError("retention additive evidence identity drift: " + path)
        current_blobs[path] = observed.git_blob_sha1
    result = []
    for line in raw.splitlines(keepends=True):
        metadata, separator, logical = line.partition(b"\t")
        path = logical.strip().decode("utf-8")
        if path in ADDED_METADATA or path in ADDED_PYTHON_PATHS:
            if metadata.split() != [b"100644", b"blob", current_blobs[path].encode()]:
                raise ValueError("retention additive inventory mode/blob drift: " + path)
            continue
        if path in HISTORICAL_PREDECESSORS and metadata.rsplit(b" ", 1)[-1].decode() == current_blobs[path]:
            if metadata.split()[:2] != [b"100644", b"blob"]:
                raise ValueError("retention predecessor inventory mode changed: " + path)
            metadata = b"100644 blob " + HISTORICAL_PREDECESSORS[path]["git_blob_sha1"].encode()
            line = metadata + separator + logical
        result.append(line)
    return b"".join(result)
