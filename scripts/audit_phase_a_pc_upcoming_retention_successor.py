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


def _safe_materialized(path, *, directory=False):
    import stat
    logical = Path(path)
    if logical.is_absolute() or ".." in logical.parts:
        raise ValueError("retention source path traversal")
    target = ROOT / logical
    for node in (*reversed(target.parents), target):
        status = node.lstat()
        regular = stat.S_ISDIR(status.st_mode) if node != target or directory else stat.S_ISREG(status.st_mode)
        if stat.S_ISLNK(status.st_mode) or getattr(status, "st_file_attributes", 0) & 0x400 or not regular:
            raise ValueError("retention source/evidence is linked or nonregular: " + path)
    return target


def _read(path):
    return _safe_materialized(path).read_bytes().replace(b"\r\n", b"\n")


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
    authenticate_main_prefix()
    authenticate_provisional_archive()
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


def checkpoint_retention_extension(chain):
    """A new canonical edge after main V347; provisional V340 is forensic only."""
    authenticate_main_prefix(chain=chain)
    before, expected = checkpoint_v2_retention_sources()
    after = identity(expected)
    return {
        "path": CHECKPOINT_V2_PATH, "generation": 348,
        "predecessor_inventory": {"path": "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v347.json",
            "generation": 347, "canonical_sha256": MAIN_LATEST_SHA256, "rewritten": False},
        "previous_successor": {"generation": 313, "canonical_sha256": _json(MAIN_PREFIX_MANIFEST, MAIN_PREFIX_MANIFEST_SHA256)["files"][312]["canonical_sha256"],
            "git_blob_sha1": V313_CHECKPOINT_BLOB, "lf_source_sha256": V313_CHECKPOINT_SHA256, "rewritten": False},
        "successor": {"git_blob_sha1": after["git_blob_sha1"], "lf_source_sha256": after["source_sha256"], "git_mode": "100644"},
        "reason_type": "PHASE_A_RETENTION_MAIN347_SOURCE_FORWARD_V348",
        "reason": "Path-exact retention projection after the unchanged V313 evaluator and canonical main V347",
        "authority_granted": False, "historical_bytes_changed": False, "rewritten": False,
    }


# Pinned historical views only; never substituted into production execution.
HISTORICAL_FORWARD_RECEIPT = 'artifacts/architecture/phase_a_retention_historical_consumers_source_forward_v1.json'
HISTORICAL_FORWARD_SHA256 = 'c21c47ae7ad6cec0b6195c92368f5bbdc9ecb53b9628f3e9622d6c849211c09e'
HISTORICAL_PREDECESSORS = {'.github/workflows/current-shadow-all-market.yml': {'fixture': 'tests/fixtures/architecture/revised_workflows/current-shadow-all-market-pre-phase-a-retention.yml', 'git_blob_sha1': 'a06a3166322ccb92b0bc3c05c87c5b3ca17298e1', 'source_sha256': '755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c', 'byte_count': 11410, 'after': {'git_blob_sha1': 'c6ca37afc8d35e9e16ccb9c66581b96b1107abf6', 'source_sha256': 'b555f7d602b5a6fc98f38d136d83ab22733c1ad9b64d7045bc1f771651551593', 'byte_count': 10830}}, 'scripts/audit_core_01d_authority_reachability_review_a.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_authority_reachability_review_a.py.txt', 'git_blob_sha1': '6597bfbe31097629cff75c5d112cb70da74fbdb0', 'source_sha256': 'd9942b3c72564ad21ae3734bb23eccc0a9bec66d133b89afa77aae6b866b6f00', 'byte_count': 46459, 'after': {'git_blob_sha1': '1156f52e9dc78b1c8071a3c7d4e1cd5876b2b2cd', 'source_sha256': '320fa11109672ae1af23ef1ee5b62c5a007de195a8f3c5ad593d1e8f7437e748', 'byte_count': 46804}}, 'scripts/audit_core_01d_checkpoint_e_completion.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion.py.txt', 'git_blob_sha1': '5276be74f83f41290b8057102dce72a5d0eac763', 'source_sha256': 'cee34e27efb29c5fa1eb0b6f2cacfe8d122146ecc05468481c9eb68e09f91557', 'byte_count': 46390, 'after': {'git_blob_sha1': '5f392a0cb5a91b6cbd4f6a4fc20af6c3011ac518', 'source_sha256': 'cb850404ee2e61b91e7f97d658d0346bd1e805a1efd141e70a33d658b88d01a6', 'byte_count': 46650}}, 'scripts/audit_core_01d_checkpoint_e_completion_v2.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion_v2.py.txt', 'git_blob_sha1': '3768669aaa4400ead8cdf63978bf6da953b0062e', 'source_sha256': 'c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1', 'byte_count': 47417, 'after': {'git_blob_sha1': '1c8eb65538550f5f196b7af4520323c391f6291b', 'source_sha256': '98608e88c84defa2dc7065a00108250bd0b891fabb503907aa7bfc82d3753773', 'byte_count': 47657}}, 'scripts/audit_core_01d_ci_offline_transport_boundary.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_ci_offline_transport_boundary.py.txt', 'git_blob_sha1': '56284d65b613efe4c1f63ae48a413cbf5e73401c', 'source_sha256': '3a42c6e50fddecd482cb8e6dd3758e8c58f453885e133ecf68798f0a51832404', 'byte_count': 173944, 'after': {'git_blob_sha1': 'db161ad45c8f8df08ab3b5e7dc0a229aff5e2378', 'source_sha256': 'f40324d351f302b1871daaae84d04dae33ae5413cac7a5166cf681bdd093342a', 'byte_count': 176062}}, 'scripts/audit_core_01d_scheduled_shadow_ownership.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_scheduled_shadow_ownership.py.txt', 'git_blob_sha1': '5b4308f82d70d9911af31893816aa438d17e5f77', 'source_sha256': '0ccc51313625e334f09ef0c2194d65273acfc47ea21bc1802bdea8a79c53d4e2', 'byte_count': 28556, 'after': {'git_blob_sha1': '9f3a9e5bd21892dbfb1345a5dcffff4afda4ca96', 'source_sha256': 'f62d574722dd101f10a89396cb03e2d1e5a507ab5fe58492312ab22feecd253a', 'byte_count': 28786}}, 'scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_sportybet_current_trigger_authority_b4.py.txt', 'git_blob_sha1': '89fb32e561660a3dcdc70ae6d1df94f9d40027c9', 'source_sha256': '8d92fa8507535b6c42620458eac1ab6a2073574bf7d483a2e2d5deba1719d05f', 'byte_count': 52479, 'after': {'git_blob_sha1': '192bf0bd3210236a38b66daf733f334b4e600a40', 'source_sha256': '33f006fedecd79ebdbcb78d08a12ea1bdf2992ea3030af49b8e85fda2ebb0638', 'byte_count': 52848}}, 'scripts/audit_data_01c_app_store_complete.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_app_store_complete.py.txt', 'git_blob_sha1': '529ac14a62467528937047f26d1a2f0283cf0969', 'source_sha256': '3c9c6cf2c2a01ccead15cd5d10c097b574e6607a8cc1d88dd752b9f557441f89', 'byte_count': 27640, 'after': {'git_blob_sha1': '68d1352e65ffb5afcb8e533a89038a2f5367a458', 'source_sha256': '1bec44314c679ebabf7908850f963f4fc7d808ca37e5e8e066d5a8bc5cfef858', 'byte_count': 27890}}, 'scripts/audit_data_01c_restore_portability.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_restore_portability.py.txt', 'git_blob_sha1': 'b6c22fd9c3bc9d120156dcc29d2dfcb4652d92da', 'source_sha256': 'bcf86a01b10255bbb629b95f16b4a13e0da9947893afb13916c6f6a0972fa89e', 'byte_count': 21223, 'after': {'git_blob_sha1': '48088a35086ac8c15928fd2d6d0039adf47fbd87', 'source_sha256': '834d84ef290197283b74de48b65d20c68d57f7a7e3a0121a9b23bd58b5069b84', 'byte_count': 21506}}, 'scripts/audit_p4_workflow_evolution_ledger.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_p4_workflow_evolution_ledger.py.txt', 'git_blob_sha1': 'caf54adbed0a16460148c8a19466d24243be8d1b', 'source_sha256': '6666440cfb69261a33bccf70a3e52a19d60c36b045163fbcc8918084958042c9', 'byte_count': 67041, 'after': {'git_blob_sha1': '5b808f4b915fac6146b21bce76dbb578b9fa5633', 'source_sha256': '0c99fd321dbcdc6f09ffce3c7e0d62be0580d12809da3270e0a1dc82692da4e6', 'byte_count': 68531}}, 'scripts/core_01d_historical_source.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--core_01d_historical_source.py.txt', 'git_blob_sha1': '7548914b31ceb832b55818e66c19b8a9bd606927', 'source_sha256': '5c46e7b5011de91c540fbbff9b7c06f15a81c87097ef07838d045123ae948865', 'byte_count': 2688, 'after': {'git_blob_sha1': 'b6dcef5aa8de68bf21ada12d9ba83779ccb87cd4', 'source_sha256': '09a05de2c61734aa8c6a7db45171894342558a12092bfaab60c59e27860abc7c', 'byte_count': 3095}}, 'tests/native/test_port_02c_audit_source_forward.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--native--test_port_02c_audit_source_forward.py.txt', 'git_blob_sha1': '2f28342ee0b692c0826de6b89cdcc480484dda03', 'source_sha256': '1433204108937e464f6ca2e9bfa8d49e5438ef25304f77630eac819d744332d1', 'byte_count': 4701, 'after': {'git_blob_sha1': '4a62daa6744ebf5e4d8478233fe2745f84603c6a', 'source_sha256': '77993d826d062330408b46982626f3a04de695ee639b473cdeea2cba10aeaa1f', 'byte_count': 5466}}, 'tests/test_core_01d_exact_pr_trigger_disposition_b1.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_exact_pr_trigger_disposition_b1.py.txt', 'git_blob_sha1': 'e12005ddef615f601bfaa6602b6896eee5e10e79', 'source_sha256': 'f737758dc591fc14474f83ef7eae6a22258d7572eeae52f02c8cacad0f3c45df', 'byte_count': 14680, 'after': {'git_blob_sha1': 'f83ec466afcbad8f40d53ea7df9532be2efe28ca', 'source_sha256': '40d34367018709e7da597ccf16f72e0b3c3355b50a8742e87c642cd9fbcf5f12', 'byte_count': 15055}}, 'tests/test_core_01d_pass_a_v300_source_predecessors.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_pass_a_v300_source_predecessors.py.txt', 'git_blob_sha1': '322f72ac3cfef2ed7ea54b8f13ec5e00bb5b590e', 'source_sha256': '19586a4e89395d3a3521dd3616e373c696d7df67896b48e5e6a4b72ce1004101', 'byte_count': 24985, 'after': {'git_blob_sha1': 'b1b84620ef6f015c5f00b8da73310b4d49c53912', 'source_sha256': '93f3a22fba369d09a3fe3e54a43267bc3d6b752a042e51233cd6216ee197d010', 'byte_count': 26220}}, 'tests/test_core_01d_sportybet_current_trigger_authority_b4.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_sportybet_current_trigger_authority_b4.py.txt', 'git_blob_sha1': '15dab8589224352f089f0c919a762cf7e2fa3bb0', 'source_sha256': '1e8697f032e3d3dc615b5cc138df1bc332d09ef6ce5303571983c393786fb775', 'byte_count': 40849, 'after': {'git_blob_sha1': '1d32931152fcb1e364d7a7aab6d4dfbe42b27173', 'source_sha256': '231af6aaecaad3a749be0acf658b642c7a927f2e186ee380e1850c6099c9aea0', 'byte_count': 41376}}, 'tests/test_p4_2_athena_run_workflow.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_2_athena_run_workflow.py.txt', 'git_blob_sha1': 'c8d83b0c39c8d8eff4abf698405e26d60bbeefbf', 'source_sha256': '9502109759e17534bc11ce2052e6fa6f7852513f8118b0194af186349f626f70', 'byte_count': 11804, 'after': {'git_blob_sha1': '92f7aa42ec917e85346d5b58c3d5a1a81965d003', 'source_sha256': '822891d4f20baf7d4b2d10fad1cb832927b44f42d30f27738278595db45c185c', 'byte_count': 12128}}, 'tests/test_p4_4a_workflow_evolution_guard.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_4a_workflow_evolution_guard.py.txt', 'git_blob_sha1': '4a4dcbd36a6f1892cdec195ed460aab95965aeee', 'source_sha256': 'cc3b5a48d658b32d4ff14bde55168b9a2f229217efffc3636de3560c97e44409', 'byte_count': 17014, 'after': {'git_blob_sha1': '22958a0db7b519892f9fb7ed676094d68f44390d', 'source_sha256': 'f8cbc395815f16736e005cd2409b3f47d9a46164580aa8f32f1abdef71a665aa', 'byte_count': 17386}}}
ADDED_PYTHON_PATHS = frozenset(['scripts/audit_phase_a_pc_upcoming_retention_successor.py', 'scripts/verify_current_shadow_pc_upcoming_archive.py', 'tests/test_current_shadow_pc_upcoming_archive_retention.py'])
ADDED_METADATA = {'artifacts/architecture/p4_workflow_evolution_snapshots/phase_a_pc_upcoming_retention_v1.json': {'git_blob_sha1': '8023cc82b910275acaaaf20c4b925b5297b0e9b8', 'source_sha256': '65ecf785ed61b9919cca48cdcddf66c9dea25fc57b73d52961cb1757ace1b329', 'byte_count': 23263}, 'artifacts/architecture/phase_a_pc_upcoming_retention_successor_v1.json': {'git_blob_sha1': '38aca4fd51efd3adc41a13d12b04755c57a19431', 'source_sha256': 'd9faba74bb89ef2513773319d3cc3e2da7da12aed9cc9b1eeea5f5b7e3f583a1', 'byte_count': 3569}, 'artifacts/architecture/phase_a_retention_b4_consumer_source_forward_v1.json': {'git_blob_sha1': '5907680d64d423402413097815b516ea6d69e392', 'source_sha256': '54dd5c5792fb9ec5c7ed76dadb2896c1a4cbf47136224b8f104886d90153f2f9', 'byte_count': 1063}, 'artifacts/architecture/phase_a_retention_historical_consumers_source_forward_v1.json': {'git_blob_sha1': '15bca7dd6e3796b1ae45eaaf3463f4c367874abf', 'source_sha256': '20ce41c0c2623b9cf67ad12f693c030e6761a6af110ad5fb73130e87b20db571', 'byte_count': 10120}, 'docs/engineering/shadow_quality_2026_10_22_provisional.txt': {'git_blob_sha1': '03ae2899be7cbb5ddadad204db3e24eaa46c4793', 'source_sha256': '0642e9e2a33d1a3a60ffb58efc0b422661d2e4b7eeffcf1d39283ae8072dbaf1', 'byte_count': 7149}, 'tests/fixtures/architecture/phase_a_retention/audit_core_01d_sportybet_current_trigger_authority_b4.py.txt': {'git_blob_sha1': '89fb32e561660a3dcdc70ae6d1df94f9d40027c9', 'source_sha256': '8d92fa8507535b6c42620458eac1ab6a2073574bf7d483a2e2d5deba1719d05f', 'byte_count': 52479}, 'tests/fixtures/architecture/phase_a_retention/audit_data_01c_restore_portability.py.txt': {'git_blob_sha1': 'b6c22fd9c3bc9d120156dcc29d2dfcb4652d92da', 'source_sha256': 'bcf86a01b10255bbb629b95f16b4a13e0da9947893afb13916c6f6a0972fa89e', 'byte_count': 21223}, 'tests/fixtures/architecture/phase_a_retention/audit_p4_workflow_evolution_ledger.py.txt': {'git_blob_sha1': 'caf54adbed0a16460148c8a19466d24243be8d1b', 'source_sha256': '6666440cfb69261a33bccf70a3e52a19d60c36b045163fbcc8918084958042c9', 'byte_count': 67041}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_authority_reachability_review_a.py.txt': {'git_blob_sha1': '6597bfbe31097629cff75c5d112cb70da74fbdb0', 'source_sha256': 'd9942b3c72564ad21ae3734bb23eccc0a9bec66d133b89afa77aae6b866b6f00', 'byte_count': 46459}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion.py.txt': {'git_blob_sha1': '5276be74f83f41290b8057102dce72a5d0eac763', 'source_sha256': 'cee34e27efb29c5fa1eb0b6f2cacfe8d122146ecc05468481c9eb68e09f91557', 'byte_count': 46390}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_checkpoint_e_completion_v2.py.txt': {'git_blob_sha1': '3768669aaa4400ead8cdf63978bf6da953b0062e', 'source_sha256': 'c376e7c55ad95d4e182b2e4c6626e0c1605bf7834e6b81abeae432e1d06212f1', 'byte_count': 47417}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_ci_offline_transport_boundary.py.txt': {'git_blob_sha1': '56284d65b613efe4c1f63ae48a413cbf5e73401c', 'source_sha256': '3a42c6e50fddecd482cb8e6dd3758e8c58f453885e133ecf68798f0a51832404', 'byte_count': 173944}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_scheduled_shadow_ownership.py.txt': {'git_blob_sha1': '5b4308f82d70d9911af31893816aa438d17e5f77', 'source_sha256': '0ccc51313625e334f09ef0c2194d65273acfc47ea21bc1802bdea8a79c53d4e2', 'byte_count': 28556}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_core_01d_sportybet_current_trigger_authority_b4.py.txt': {'git_blob_sha1': '89fb32e561660a3dcdc70ae6d1df94f9d40027c9', 'source_sha256': '8d92fa8507535b6c42620458eac1ab6a2073574bf7d483a2e2d5deba1719d05f', 'byte_count': 52479}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_app_store_complete.py.txt': {'git_blob_sha1': '529ac14a62467528937047f26d1a2f0283cf0969', 'source_sha256': '3c9c6cf2c2a01ccead15cd5d10c097b574e6607a8cc1d88dd752b9f557441f89', 'byte_count': 27640}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_data_01c_restore_portability.py.txt': {'git_blob_sha1': 'b6c22fd9c3bc9d120156dcc29d2dfcb4652d92da', 'source_sha256': 'bcf86a01b10255bbb629b95f16b4a13e0da9947893afb13916c6f6a0972fa89e', 'byte_count': 21223}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--audit_p4_workflow_evolution_ledger.py.txt': {'git_blob_sha1': 'caf54adbed0a16460148c8a19466d24243be8d1b', 'source_sha256': '6666440cfb69261a33bccf70a3e52a19d60c36b045163fbcc8918084958042c9', 'byte_count': 67041}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/scripts--core_01d_historical_source.py.txt': {'git_blob_sha1': '7548914b31ceb832b55818e66c19b8a9bd606927', 'source_sha256': '5c46e7b5011de91c540fbbff9b7c06f15a81c87097ef07838d045123ae948865', 'byte_count': 2688}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--native--test_port_02c_audit_source_forward.py.txt': {'git_blob_sha1': '2f28342ee0b692c0826de6b89cdcc480484dda03', 'source_sha256': '1433204108937e464f6ca2e9bfa8d49e5438ef25304f77630eac819d744332d1', 'byte_count': 4701}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_exact_pr_trigger_disposition_b1.py.txt': {'git_blob_sha1': 'e12005ddef615f601bfaa6602b6896eee5e10e79', 'source_sha256': 'f737758dc591fc14474f83ef7eae6a22258d7572eeae52f02c8cacad0f3c45df', 'byte_count': 14680}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_pass_a_v300_source_predecessors.py.txt': {'git_blob_sha1': '322f72ac3cfef2ed7ea54b8f13ec5e00bb5b590e', 'source_sha256': '19586a4e89395d3a3521dd3616e373c696d7df67896b48e5e6a4b72ce1004101', 'byte_count': 24985}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_core_01d_sportybet_current_trigger_authority_b4.py.txt': {'git_blob_sha1': '15dab8589224352f089f0c919a762cf7e2fa3bb0', 'source_sha256': '1e8697f032e3d3dc615b5cc138df1bc332d09ef6ce5303571983c393786fb775', 'byte_count': 40849}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_2_athena_run_workflow.py.txt': {'git_blob_sha1': 'c8d83b0c39c8d8eff4abf698405e26d60bbeefbf', 'source_sha256': '9502109759e17534bc11ce2052e6fa6f7852513f8118b0194af186349f626f70', 'byte_count': 11804}, 'tests/fixtures/architecture/phase_a_retention/historical_consumers/tests--test_p4_4a_workflow_evolution_guard.py.txt': {'git_blob_sha1': '4a4dcbd36a6f1892cdec195ed460aab95965aeee', 'source_sha256': 'cc3b5a48d658b32d4ff14bde55168b9a2f229217efffc3636de3560c97e44409', 'byte_count': 17014}, 'tests/fixtures/architecture/revised_workflows/current-shadow-all-market-pre-phase-a-retention.yml': {'git_blob_sha1': 'a06a3166322ccb92b0bc3c05c87c5b3ca17298e1', 'source_sha256': '755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c', 'byte_count': 11410}}


ADDED_PYTHON_IDENTITIES = {'tests/test_current_shadow_pc_upcoming_archive_retention.py': {'git_blob_sha1': '673f4a01cb4ef814903db152637673b53250bd5f', 'source_sha256': 'fb329b7802d355312b68671a3c1e3fdb9549d58726c9197014879b811d726d8c', 'byte_count': 20491}, 'scripts/verify_current_shadow_pc_upcoming_archive.py': {'git_blob_sha1': '5ddc03c844dcd1d3b908a59c6b52bb83d077a1e3', 'source_sha256': '760c25069c116596d351fe166a822c540287257b6aa4ba59bd5c314216ab6acc', 'byte_count': 17111}}


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
    if latest.get("generation", 0) < 348:
        raise ValueError("historical retention projection requires its A2 successor")
    authenticate_bootstrap_sources()
    predecessors = dict(HISTORICAL_PREDECESSORS)
    for path, descriptor in BOOTSTRAP_PREDECESSORS.items():
        if path not in predecessors:
            predecessors[path] = dict(descriptor, after=BOOTSTRAP_AFTER[path])
    added_metadata = dict(ADDED_METADATA, **BOOTSTRAP_METADATA)
    expected_paths = (set(predecessors) | set(ADDED_PYTHON_PATHS) | set(added_metadata)
                      | {value["fixture"] for value in predecessors.values()})
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD", "--", *sorted(expected_paths)], cwd=ROOT)
    modes = {line.split(b"\t", 1)[1].decode(): line.split(b"\t", 1)[0].split()[:2]
             for line in tree.splitlines()}
    if set(modes) != expected_paths or any(value != [b"100644", b"blob"] for value in modes.values()):
        raise ValueError("retention source/evidence inventory mode changed")
    current_rows = {row["path"]: row["lf_source_sha256"] for row in latest["source_identities"]}
    current_blobs = {}
    for path in set(predecessors) | set(ADDED_PYTHON_PATHS):
        payload, observed = read_tracked_head_blob(ROOT, path)
        payload = payload.replace(b"\r\n", b"\n")
        if path.endswith(".py") and current_rows.get(path) != hashlib.sha256(payload).hexdigest():
            raise ValueError("retention current source is not A2 authenticated: " + path)
        if path == WORKFLOW and payload != expected_workflow():
            raise ValueError("retention workflow projection source drift")
        expected_after = BOOTSTRAP_AFTER.get(path) or (predecessors[path]["after"] if path in predecessors
                          else ADDED_PYTHON_IDENTITIES.get(path))
        if expected_after is not None and identity(payload) != expected_after:
            raise ValueError("source differs from the exact reviewed retention successor: " + path)
        current_blobs[path] = observed.git_blob_sha1
    for path, descriptor in predecessors.items():
        payload, observed = read_tracked_head_blob(ROOT, descriptor["fixture"])
        if identity(payload.replace(b"\r\n", b"\n")) != {
                key: descriptor[key] for key in BEFORE} or observed.git_blob_sha1 != descriptor["git_blob_sha1"]:
            raise ValueError("retention historical predecessor drift: " + path)
    for path, expected in added_metadata.items():
        payload, observed = read_tracked_head_blob(ROOT, path)
        if identity(payload.replace(b"\r\n", b"\n")) != expected or observed.git_blob_sha1 != expected["git_blob_sha1"]:
            raise ValueError("retention additive evidence identity drift: " + path)
        current_blobs[path] = observed.git_blob_sha1
    result = []
    for line in raw.splitlines(keepends=True):
        metadata, separator, logical = line.partition(b"\t")
        path = logical.strip().decode("utf-8")
        if path in added_metadata or path in ADDED_PYTHON_PATHS:
            if metadata.split() != [b"100644", b"blob", current_blobs[path].encode()]:
                raise ValueError("retention additive inventory mode/blob drift: " + path)
            continue
        if path in predecessors and metadata.rsplit(b" ", 1)[-1].decode() == current_blobs[path]:
            if metadata.split()[:2] != [b"100644", b"blob"]:
                raise ValueError("retention predecessor inventory mode changed: " + path)
            metadata = b"100644 blob " + predecessors[path]["git_blob_sha1"].encode()
            line = metadata + separator + logical
        result.append(line)
    return b"".join(result)


# Separate owner-authorized startup edge; all earlier receipts remain immutable.
BOOTSTRAP_AUDITOR = "scripts/audit_core_01d_ci_offline_transport_boundary.py"
BOOTSTRAP_RECEIPT = 'artifacts/architecture/phase_a_retention_bootstrap_source_forward_v1.json'
BOOTSTRAP_RECEIPT_SHA256 = 'fd925937d4415315f472d2b2dee87bca494847807931808579a328e130c694f3'
BOOTSTRAP_PREDECESSORS = {'sitecustomize.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/bootstrap/sitecustomize-before.py.txt', 'git_blob_sha1': '15e3b8f1ed4f5b0ecbb216f466a730a3ad35614b', 'source_sha256': '3af9d45a4c473114939ba894b2ef11405391c14cec1dad2daef6a39ee5cdf037', 'byte_count': 2001}, 'scripts/audit_core_01d_ci_offline_transport_boundary.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/bootstrap/a2-auditor-before.py.txt', 'git_blob_sha1': 'db161ad45c8f8df08ab3b5e7dc0a229aff5e2378', 'source_sha256': 'f40324d351f302b1871daaae84d04dae33ae5413cac7a5166cf681bdd093342a', 'byte_count': 176062}, 'tests/test_core_01d_ci_offline_transport_inventory_evolution.py': {'fixture': 'tests/fixtures/architecture/phase_a_retention/bootstrap/inventory-evolution-test-before.py.txt', 'git_blob_sha1': 'e218fa76df4cb9c0c81ad8db7d3f62b880d8af14', 'source_sha256': 'ed4eb1a57ad5c0684c1ef9e24be4a34bb02ef561a91a1b25f2ae8a6c75f676ec', 'byte_count': 43004}}
BOOTSTRAP_AFTER = {'sitecustomize.py': {'git_blob_sha1': 'a8b563de7c8a7b98b8b9ca4ddeb8ebfe123f43bf', 'source_sha256': 'b9947aaee990357a1017cdb66e91218b2ab96711efc1c1c1b1556c2d8849c24a', 'byte_count': 2405}, 'scripts/audit_core_01d_ci_offline_transport_boundary.py': {'git_blob_sha1': 'c084fe5d0d124f97068490caf9d92326c3393893', 'source_sha256': '282e1b9c5258eb4fcbe51581816e7894e5c9b581f085be1162aa6f9bca864299', 'byte_count': 176538}, 'tests/test_core_01d_ci_offline_transport_inventory_evolution.py': {'git_blob_sha1': '48465f8deb54a6127decb113a5309ccc97acb60a', 'source_sha256': '886b030015eed9864064af60dc7f5ba4d1c45118955ad9d7e7ff7f2a867642d7', 'byte_count': 43961}, 'tests/test_current_shadow_pc_upcoming_archive_retention.py': {'git_blob_sha1': '9e8ee5fde96d875f4cf0a71e5a67a4d458c773e8', 'source_sha256': 'd48830dae40f9ec9cab38c2e9f055295a2d2b9f41bc7939bc28b6373f134038c', 'byte_count': 24748}}
BOOTSTRAP_METADATA = {'tests/fixtures/architecture/phase_a_retention/bootstrap/sitecustomize-before.py.txt': {'git_blob_sha1': '15e3b8f1ed4f5b0ecbb216f466a730a3ad35614b', 'source_sha256': '3af9d45a4c473114939ba894b2ef11405391c14cec1dad2daef6a39ee5cdf037', 'byte_count': 2001}, 'tests/fixtures/architecture/phase_a_retention/bootstrap/a2-auditor-before.py.txt': {'git_blob_sha1': 'db161ad45c8f8df08ab3b5e7dc0a229aff5e2378', 'source_sha256': 'f40324d351f302b1871daaae84d04dae33ae5413cac7a5166cf681bdd093342a', 'byte_count': 176062}, 'tests/fixtures/architecture/phase_a_retention/bootstrap/inventory-evolution-test-before.py.txt': {'git_blob_sha1': 'e218fa76df4cb9c0c81ad8db7d3f62b880d8af14', 'source_sha256': 'ed4eb1a57ad5c0684c1ef9e24be4a34bb02ef561a91a1b25f2ae8a6c75f676ec', 'byte_count': 43004}, 'artifacts/architecture/phase_a_retention_bootstrap_source_forward_v1.json': {'git_blob_sha1': '9579c81066acdedf8de3dc337b7114746c5221d5', 'source_sha256': '859130595f052db7dc856a9cd75eb3a793dff710cf0749d7631f9cfa171f02ff', 'byte_count': 2393}}
BOOTSTRAP_AUDITOR_OLD_BLOCK = '    require(pins == {path: identity(path)["lf_source_sha256"] for path in sorted(protected)},\n            "root bootstrap does not bind exact patchable guard/auditor source")\n'
BOOTSTRAP_AUDITOR_NEW_BLOCK = '    successor_declarations = [node for node in startup.body\n                              if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)\n                              and target.id == "ROOT_TEST_SOURCE_SUCCESSORS" for target in node.targets)]\n    if successor_declarations:\n        from scripts import audit_phase_a_pc_upcoming_retention_successor as retention\n        retention.authenticate_bootstrap_successor(startup_text, identity)\n    else:\n        require(pins == {path: identity(path)["lf_source_sha256"] for path in sorted(protected)},\n                "root bootstrap does not bind exact patchable guard/auditor source")\n'


def _bootstrap_blob(path):
    return _raw_blob(path).replace(b"\r\n", b"\n")


def bootstrap_predecessor(path):
    descriptor = BOOTSTRAP_PREDECESSORS[path]
    raw = _bootstrap_blob(descriptor["fixture"])
    if identity(raw) != {key: descriptor[key] for key in BEFORE}:
        raise ValueError("bootstrap predecessor source identity drift: " + path)
    return raw


def expected_bootstrap_source():
    before = bootstrap_predecessor("sitecustomize.py")
    marker = b'\n_args = getattr(sys, "orig_argv", ())\n'
    addition = ("\n# Owner-authorized, path-exact retention successors. Preserve the original pins\n"
                "# and the previously admitted auditor; no other guard gains an alternate identity.\n"
                "ROOT_TEST_SOURCE_SUCCESSORS = {\n"
                '    "' + BOOTSTRAP_AUDITOR + '": (\n'
                '        "' + PRIOR_ADMITTED_AUDITOR_SHA + '",\n'
                '        "' + BOOTSTRAP_AFTER[BOOTSTRAP_AUDITOR]["source_sha256"] + '",\n    ),\n}\n').encode()
    old = b"            if hashlib.sha256(_raw).hexdigest() != _expected:\n"
    new = (b"            _digest = hashlib.sha256(_raw).hexdigest()\n"
           b"            if _digest != _expected and _digest not in ROOT_TEST_SOURCE_SUCCESSORS.get(_path, ()):\n")
    if before.count(marker) != 1 or before.count(old) != 1:
        raise ValueError("bootstrap successor predecessor seam drift")
    return before.replace(marker, addition + marker).replace(old, new)


def authenticate_bootstrap_sources():
    """No historical rehash: pinned predecessors plus one exact derived edge."""
    _json(BOOTSTRAP_RECEIPT, BOOTSTRAP_RECEIPT_SHA256)
    for path in BOOTSTRAP_PREDECESSORS:
        bootstrap_predecessor(path)
    for path, expected in BOOTSTRAP_METADATA.items():
        if identity(_bootstrap_blob(path)) != expected:
            raise ValueError("bootstrap successor evidence drift: " + path)
    expected_auditor = bootstrap_predecessor(BOOTSTRAP_AUDITOR)
    for old, new in BOOTSTRAP_AUDITOR_PATCHES:
        if expected_auditor.count(old.encode()) != 1:
            raise ValueError("bootstrap predecessor auditor seam drift")
        expected_auditor = expected_auditor.replace(old.encode(), new.encode())
    if _bootstrap_blob(BOOTSTRAP_AUDITOR) != expected_auditor:
        raise ValueError("bootstrap successor auditor exceeds exact activation edge")
    if _bootstrap_blob("sitecustomize.py") != expected_bootstrap_source():
        raise ValueError("bootstrap successor root exceeds exact added pin recipe")
    for path, expected in BOOTSTRAP_AFTER.items():
        if identity(_bootstrap_blob(path)) != expected:
            raise ValueError("bootstrap successor current source identity drift: " + path)
    for path, descriptor in _CURRENT_INTEGRATION["current_source_predecessors"].items():
        raw = _bootstrap_blob(descriptor["fixture"])
        if identity(raw) != {key: descriptor[key] for key in BEFORE}:
            raise ValueError("integrated current-main source predecessor drift: " + path)
    prior = _bootstrap_blob(_CURRENT_INTEGRATION["prior_admitted_auditor_fixture"])
    if hashlib.sha256(prior).hexdigest() != PRIOR_ADMITTED_AUDITOR_SHA:
        raise ValueError("bootstrap predecessor admitted auditor identity drift")
    return True


def authenticate_bootstrap_successor(startup_text, current_identity):
    """Authenticate before guard installation policy can be treated as proven."""
    authenticate_bootstrap_sources()
    if startup_text.encode("utf-8") != expected_bootstrap_source():
        raise ValueError("bootstrap successor startup source differs from exact recipe")
    import ast
    startup = ast.parse(startup_text)
    pins = next(ast.literal_eval(node.value) for node in startup.body
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                and target.id == "ROOT_TEST_SOURCE_PINS" for target in node.targets))
    before = ast.parse(bootstrap_predecessor("sitecustomize.py").decode())
    original_pins = next(ast.literal_eval(node.value) for node in before.body
                         if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                         and target.id == "ROOT_TEST_SOURCE_PINS" for target in node.targets))
    if pins != original_pins:
        raise ValueError("bootstrap successor changed original pins")
    for path, expected in pins.items():
        permitted = BOOTSTRAP_AFTER[BOOTSTRAP_AUDITOR]["source_sha256"] if path == BOOTSTRAP_AUDITOR else expected
        if current_identity(path)["lf_source_sha256"] != permitted:
            raise ValueError("bootstrap successor patchable guard identity drift: " + path)
    return True


# Owner-authorized integration of actual merged main; earlier records above
# remain immutable forensic evidence, never alternate active generations.
MAIN_SHA = '016ae05b9f0fcc6991a5b7f28bdfea3688185729'
MAIN_LATEST_SHA256 = '55d1aa9b8899b3d680b51117e1d596204ffae8536edeed3ceb453b40611d5a29'
MAIN_PREFIX_MANIFEST = 'artifacts/architecture/phase_a_main_347_inventory_prefix_v1.json'
MAIN_PREFIX_MANIFEST_SHA256 = '6377c0ea057266fbfdd4041136915a7feee87c1fdd8720a7e52ef0f9affc426e'
ARCHIVE_MANIFEST = 'artifacts/architecture/phase_a_provisional_a2_archive_v1.json'
ARCHIVE_MANIFEST_SHA256 = '224800764858b4ed688c0aa79f42653b9e1b27704d8f7ea7ae7ac2bcc3e14e0d'
RECEIPT = 'artifacts/architecture/phase_a_pc_upcoming_retention_integrated_v1.json'
RECEIPT_SHA256 = 'f4e6d25f41298868b2bffeb3cafd602ec5645bbec38626e01361744b23f39f1f'
SNAPSHOT = 'artifacts/architecture/p4_workflow_evolution_snapshots/phase_a_pc_upcoming_retention_integrated_v1.json'
SNAPSHOT_SHA256 = '1d045539378fdaeecdae764967fa661561ec5b83d1d07e03cf60925268e43d3a'
B4_FORWARD_RECEIPT = 'artifacts/architecture/phase_a_retention_b4_integrated_source_forward_v1.json'
B4_FORWARD_SHA256 = 'f83faf1c383b0272ddde9db6f867ce36d07183da5c75de3c24dd9b1fd212c327'
BOOTSTRAP_RECEIPT = 'artifacts/architecture/phase_a_pc_upcoming_retention_integrated_v1.json'
BOOTSTRAP_RECEIPT_SHA256 = 'f4e6d25f41298868b2bffeb3cafd602ec5645bbec38626e01361744b23f39f1f'
PRIOR_ADMITTED_AUDITOR_SHA = '282e1b9c5258eb4fcbe51581816e7894e5c9b581f085be1162aa6f9bca864299'
LINKED_METADATA = {'artifacts/architecture/phase_a_pc_upcoming_retention_integrated_v1.json': {'git_blob_sha1': '6281f5fe98d34f8622875098ee2bcc3143fe5278', 'source_sha256': '3f93b2fd8f3928ee83fd7026dda277f9db9ab707f868c993d6af04be3ba1e2c7', 'byte_count': 46231}, 'artifacts/architecture/p4_workflow_evolution_snapshots/phase_a_pc_upcoming_retention_integrated_v1.json': {'git_blob_sha1': '7acef60fce6cfcb4dbc34f08770613f5d3f4e99a', 'source_sha256': 'bede6fbd85e36b45e36a80ce9676b24753f42d4c1c350654ab32d4f898499428', 'byte_count': 23283}, 'artifacts/architecture/phase_a_retention_b4_integrated_source_forward_v1.json': {'git_blob_sha1': '220bcb0267004432e07ca5626be6e1534eed5b83', 'source_sha256': '8714839aa0fe6ffe59f23fda8bc81bdb2bc0f1dd272cbcc9041144c6317b244d', 'byte_count': 1121}}
_CURRENT_INTEGRATION = _json(RECEIPT, RECEIPT_SHA256)
HISTORICAL_PREDECESSORS = _CURRENT_INTEGRATION["historical_view_predecessors"]
BOOTSTRAP_PREDECESSORS = _CURRENT_INTEGRATION["bootstrap_predecessors"]
BOOTSTRAP_AFTER = _CURRENT_INTEGRATION["current_source_after"]
BOOTSTRAP_AUDITOR_PATCHES = _CURRENT_INTEGRATION["bootstrap_auditor_patch_recipe"]
ADDED_METADATA = dict(_CURRENT_INTEGRATION["retained_metadata"], **LINKED_METADATA)
BOOTSTRAP_METADATA = {p: ADDED_METADATA[p] for p in set(LINKED_METADATA) |
                      {v["fixture"] for v in BOOTSTRAP_PREDECESSORS.values()}}



def _raw_blob(path):
    """Exact Git object bytes; filtered worktree identity is checked separately."""
    from runtime.source_identity import read_tracked_head_blob
    _safe_materialized(path)
    mode = subprocess.check_output(["git", "ls-tree", "HEAD", "--", path], cwd=ROOT)
    if len(mode.splitlines()) != 1 or mode.split(b"\t", 1)[0].split()[:2] != [b"100644", b"blob"]:
        raise ValueError("retention source/evidence Git mode drift: " + path)
    raw, _ = read_tracked_head_blob(ROOT, path)
    return raw


class RetentionSourceEvidenceError(ValueError, AssertionError):
    """Invalid retained evidence: verifier ValueError and legacy A2 assertion API."""


def authenticate_main_prefix(chain=None):
    try:
        return _authenticate_main_prefix(chain)
    except ValueError as exc:
        raise RetentionSourceEvidenceError(str(exc)) from exc


def _authenticate_main_prefix(chain=None):
    """Bind all canonical main inventory objects; provisional records are excluded."""
    prefix = _json(MAIN_PREFIX_MANIFEST, MAIN_PREFIX_MANIFEST_SHA256)
    if (prefix["main_commit"] != MAIN_SHA or prefix["latest_generation"] != 347
            or prefix["latest_canonical_sha256"] != MAIN_LATEST_SHA256
            or len(prefix["files"]) != 347):
        raise ValueError("main inventory prefix manifest scope drift")
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD", "--", "tests/fixtures/core_01d"], cwd=ROOT)
    if type(tree) is not bytes:
        raise ValueError("main inventory prefix tree proof is missing")
    modes = {line.split(b"\t", 1)[1].decode(): line.split(b"\t", 1)[0].split() for line in tree.splitlines()}
    if chain is not None:
        # A2 has parsed/self-hash-checked the chain. Bind its current main
        # anchor here; let the existing historical validators report their
        # own predecessor errors. Expected identities come from the pinned
        # manifest/HEAD, never from caller-selected source records.
        if len(chain) < 347:
            raise ValueError("main inventory prefix is missing canonical generations")
        if (chain[346][0] != prefix["files"][346]["path"]
                or chain[346][1].get("canonical_sha256") != MAIN_LATEST_SHA256):
            raise ValueError("main inventory prefix has an altered canonical main anchor")
    for index, expected in enumerate(prefix["files"]):
        path = expected["path"]
        if expected["generation"] != index + 1 or modes.get(path) != [b"100644", b"blob", expected["git_blob_sha1"].encode()]:
            raise ValueError("main inventory prefix mode/blob mismatch: " + path)
        if chain is None:
            # Canonical source files may materialize as CRLF on Windows; the
            # HEAD blob above remains exactly main's unfiltered original bytes.
            raw = _read(path)
            if len(raw) != expected["byte_count"] or hashlib.sha256(raw).hexdigest() != expected["raw_sha256"]:
                raise ValueError("main inventory prefix bytes changed: " + path)
        else:
            _safe_materialized(path)
    return prefix


def authenticate_provisional_archive():
    """Forensic evidence only: never an alternate active generation root."""
    archive = _json(ARCHIVE_MANIFEST, ARCHIVE_MANIFEST_SHA256)
    if (archive.get("authority_granted") is not False
            or archive.get("historical_bytes_changed") is not False
            or archive.get("active_chain_member") is not False
            or archive.get("source_commit") != "88d82b29bfa22aecd8a3a97c0518ae3e3ba0d848"
            or archive.get("canonical_main") != MAIN_SHA
            or [row.get("generation") for row in archive["files"]] != [338, 339, 340, 341]):
        raise ValueError("provisional archive provenance/status is not exact")
    base = "tests/fixtures/architecture/phase_a_retention/provisional-a2-88d82b29"
    directory = _safe_materialized(base, directory=True)
    if {p.name for p in directory.iterdir()} != {f"provisional-v{g}.json" for g in range(338, 342)}:
        raise ValueError("provisional archive contains missing or unexpected entries")
    prefix = _json(MAIN_PREFIX_MANIFEST, MAIN_PREFIX_MANIFEST_SHA256)
    for row in archive["files"]:
        generation = row["generation"]
        name = f"provisional-v{generation}.json"
        path = base + "/" + name
        if (row["archive_path"] != path or row["archive_basename"] != name
                or row["original_basename"] != f"ci-offline-transport-boundary-source-inventory-v{generation}.json"
                or row["original_path"] != "tests/fixtures/core_01d/" + row["original_basename"]
                or row["source_commit"] != archive["source_commit"] or row["active_chain_member"] is not False):
            raise ValueError("provisional archive path or origin mismatch")
        raw = _raw_blob(path)
        observed = identity(raw)
        if (observed != {"source_sha256": row["sha256"], "git_blob_sha1": row["git_blob_sha1"], "byte_count": row["byte_count"]}
                or json.loads(raw)["canonical_sha256"] != row["declared_canonical_sha256"]
                or row["main_canonical_sha256"] != prefix["files"][generation-1]["canonical_sha256"]
                or row["declared_canonical_sha256"] == row["main_canonical_sha256"]
                or row["diverges_from_main"] is not True):
            raise ValueError("provisional archive bytes or divergence proof changed")
    return archive
