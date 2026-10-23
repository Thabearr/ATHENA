"""Exact Tests-only successor, composed outside frozen P4/D5/retention proofs.

This module reads tracked source evidence and evaluates a single maintenance
transition. It never invokes historical proof builders, A2, transport or Actions.
Current Python source identities are independently authenticated by current A2.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/tests.yml'
FIXTURE = 'tests/fixtures/architecture/revised_workflows/tests-pre-shard-balance-v1.yml'
RECEIPT = 'artifacts/architecture/tests_shard_balance_successor_v1.json'
SNAPSHOT = 'artifacts/architecture/p4_workflow_evolution_snapshots/tests_shard_balance_v1.json'
RECEIPT_SHA256 = '359f23499d76e6610b70fd4a07f7e5946604f3e3f25aa09c06f60c79d0345918'
BEFORE_TREE = '77c3a70e38833756766e43a4a31ba2a7cc55a45d'
AFTER_TREE = 'cd25278ee9e89459a33faeadc21f54ca2b99a6e5'
BEFORE_B4_TREE = 'dd703507488f1495767b8e0055d71a9f488390bf'
# The new B4 projected tree is pinned below by the same receipt and inverse.
AFTER_B4_TREE = '006a1a40caf2d2f934e87925f778792e686449e2'
BEFORE = {'git_blob_sha1': 'a5eafa0afebc01abe02389739abf71c9ece2d1b4', 'source_sha256': '62dc0cd30df67534f424fddc9706a0b50f9b22ea86bc5b3c6a005e8c57006606', 'byte_count': 3322}
AFTER = {'git_blob_sha1': 'e8141712880fbae707ab96e02d5d7e0edb0f085f', 'source_sha256': 'bf90a865faa6302e5d70bd36bcaea0d602bb500acd96274bf8932b5cd6ee4374', 'byte_count': 5343}
POLICY_ID = 'ATHENA_P4_TESTS_EIGHT_SHARD_BALANCE_MAINTENANCE_V1'
IDENTITY_KEYS = ('git_blob_sha1', 'source_sha256')


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical({k: v for k, v in value.items()
                                     if k != 'canonical_sha256'})).hexdigest()


def identity(raw):
    return {'git_blob_sha1': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'byte_count': len(raw)}


def read_blob(path):
    """Regular tracked bytes with no linked ancestor; safe CRLF materialization."""
    logical = Path(path)
    if logical.is_absolute() or logical.as_posix() != path or '..' in logical.parts:
        raise ValueError('Tests successor evidence path is not exact')
    target = ROOT / logical
    for node in (*reversed(target.parents), target):
        status = node.lstat()
        regular = stat.S_ISREG(status.st_mode) if node == target else stat.S_ISDIR(status.st_mode)
        if (not regular or stat.S_ISLNK(status.st_mode)
                or getattr(status, 'st_file_attributes', 0) & 0x400):
            raise ValueError('Tests successor linked/nonregular evidence: ' + path)
    mode = subprocess.check_output(['git', 'ls-tree', 'HEAD', '--', path], cwd=ROOT)
    if (type(mode) is not bytes or len(mode.splitlines()) != 1
            or mode.split(b'\t', 1)[0].split()[:2] != [b'100644', b'blob']):
        raise ValueError('Tests successor evidence Git mode drift: ' + path)
    from runtime.source_identity import read_tracked_head_blob
    raw, _ = read_tracked_head_blob(ROOT, path)
    # Fixtures are LF Git objects even in a clean Windows CRLF worktree.
    return raw


def receipt():
    raw = read_blob(RECEIPT)
    value = json.loads(raw)
    if (canonical(value) != raw or value.get('canonical_sha256') != RECEIPT_SHA256
            or digest(value) != RECEIPT_SHA256):
        raise ValueError('Tests successor receipt identity drift')
    return value


def tree_entries():
    return subprocess.check_output(['git', 'ls-tree', 'HEAD:.github/workflows'], cwd=ROOT)


def tree_identity(entries, replacements=None):
    replacements = replacements or {}
    body = b''
    seen = set()
    for line in entries.splitlines():
        header, name = line.split(b'\t', 1)
        mode, kind, blob = header.split()
        text = name.decode('utf-8')
        if text in replacements:
            if mode != b'100644' or kind != b'blob':
                raise ValueError('Tests successor workflow tree mode drift')
            blob = replacements[text].encode('ascii')
            seen.add(text)
        body += mode + b' ' + name + b'\0' + bytes.fromhex(blob.decode('ascii'))
    if seen != set(replacements):
        raise ValueError('Tests successor workflow tree is missing an exact path')
    return hashlib.sha1(b'tree ' + str(len(body)).encode() + b'\0' + body).hexdigest()


def expected_workflow(value=None):
    value = receipt() if value is None else value
    before = read_blob(FIXTURE)
    if identity(before) != BEFORE:
        raise ValueError('Tests successor predecessor workflow drift')
    old, new = value['selection_before'].encode(), value['selection_after'].encode()
    if before.count(old) != 1:
        raise ValueError('Tests successor selection predecessor seam drift')
    expected = before.replace(old, new)
    if identity(expected) != AFTER:
        raise ValueError('Tests successor recipe exceeds the exact reviewed partition')
    return expected


def predecessor_source(path, raw):
    """Restore one pinned source edge only; unknown paths/bytes gain no alias."""
    row = receipt()['source_forward'].get(path)
    if row is None:
        return raw
    if identity(raw) != row['after']:
        raise ValueError('Tests successor current source drift: ' + path)
    before = read_blob(row['fixture'])
    if identity(before) != row['before']:
        raise ValueError('Tests successor source predecessor drift: ' + path)
    expected = before
    for old, new in row['patches']:
        if expected.count(old.encode()) != 1:
            raise ValueError('Tests successor source recipe seam drift: ' + path)
        expected = expected.replace(old.encode(), new.encode())
    if raw != expected:
        raise ValueError('Tests successor source exceeds its exact recipe: ' + path)
    return before


def authenticate():
    value = receipt()
    if (value['policy_id'] != POLICY_ID or value['workflow_path'] != WORKFLOW
            or value['authority_granted'] is not False
            or value['historical_bytes_changed'] is not False
            or value['required_contexts_changed'] is not False
            or type(value['shard_count']) is not int or value['shard_count'] != 8
            or value['workflow_before'] != BEFORE or value['workflow_after'] != AFTER
            or value['workflow_tree_before_sha1'] != BEFORE_TREE
            or value['workflow_tree_after_sha1'] != AFTER_TREE
            or value['b4_projected_before_sha1'] != BEFORE_B4_TREE
            or value['b4_projected_after_sha1'] != AFTER_B4_TREE):
        raise ValueError('Tests successor scope or authority drift')
    if read_blob(WORKFLOW) != expected_workflow(value):
        raise ValueError('Tests successor current workflow drift')
    entries = tree_entries()
    if (tree_identity(entries) != AFTER_TREE
            or tree_identity(entries, {'tests.yml': BEFORE['git_blob_sha1']}) != BEFORE_TREE):
        raise ValueError('Tests successor is not the exact one-path workflow tree replacement')
    if subprocess.check_output(['git', 'diff', '--name-only', 'HEAD', '--', '.github/workflows'], cwd=ROOT).strip():
        raise ValueError('Tests successor workflow worktree drift')
    for path in value['source_forward']:
        predecessor_source(path, read_blob(path))
    for path, expected in value['added_python_sources'].items():
        if identity(read_blob(path)) != expected:
            raise ValueError('Tests successor regression source drift: ' + path)
    prior_path = value['prior_snapshot']['path']
    prior = json.loads(read_blob(prior_path))
    current = json.loads(read_blob(SNAPSHOT))
    if (digest(prior) != value['prior_snapshot']['canonical_sha256']
            or digest(prior) != prior['canonical_sha256']
            or digest(current) != current['canonical_sha256']
            or current['canonical_sha256'] != value['workflow_evolution_ledger_sha256']
            or current['transitions'][:-1] != prior['transitions']
            or current['current_workflow_tree_sha1'] != AFTER_TREE):
        raise ValueError('Tests successor P4 immutable prefix/snapshot drift')
    exempt = {'transitions', 'current_workflow_tree_sha1', 'canonical_sha256'}
    if {k: v for k, v in current.items() if k not in exempt} != {
            k: v for k, v in prior.items() if k not in exempt}:
        raise ValueError('Tests successor changed a historical P4 checkpoint')
    from scripts import audit_p4_workflow_evolution_ledger as p4
    transition = current['transitions'][-1]
    if (transition['workflow_path'] != WORKFLOW
            or transition['maintenance_contract'] != p4.TESTS_SHARD_BALANCE_CONTRACT):
        raise ValueError('Tests successor maintenance is not path-exact')
    evaluated = p4.apply_transitions(
        {WORKFLOW: {k: BEFORE[k] for k in IDENTITY_KEYS}}, [transition],
        frozen_baseline_paths={WORKFLOW}, baseline_families={WORKFLOW: 'TESTS'},
        evidence_receipts={RECEIPT: value}, historical_before_fixture_bytes={FIXTURE: read_blob(FIXTURE)})
    if evaluated != {WORKFLOW: {k: AFTER[k] for k in IDENTITY_KEYS}}:
        raise ValueError('Tests successor P4 transition does not derive its source')
    return value


def previous_workflow_context(observed_tree):
    authenticate()
    if observed_tree != AFTER_TREE:
        raise ValueError('Tests successor current workflow tree drift')
    rows = []
    for line in tree_entries().splitlines():
        header, name = line.split(b'\t', 1)
        if name == b'tests.yml':
            mode, kind, _blob = header.split()
            header = mode + b' ' + kind + b' ' + BEFORE['git_blob_sha1'].encode()
        rows.append(header + b'\t' + name + b'\n')
    return BEFORE_TREE, b''.join(rows)


def project_tree(observed):
    if observed != AFTER_TREE:
        return observed
    authenticate()
    return BEFORE_TREE


def project_b4_tree(observed):
    if observed != AFTER_B4_TREE:
        return observed
    authenticate()
    return BEFORE_B4_TREE


def previous_p4_context(observed, head_tree):
    if head_tree != AFTER_TREE:
        return observed, head_tree
    authenticate()
    result = dict(observed)
    if WORKFLOW in result:
        if result[WORKFLOW] != {k: AFTER[k] for k in IDENTITY_KEYS}:
            raise ValueError('Tests successor observed P4 workflow identity drift')
        result[WORKFLOW] = {k: BEFORE[k] for k in IDENTITY_KEYS}
    return result, BEFORE_TREE


def install_context(context):
    """Compose this source edge into existing exact historical inventory views.

    No builder/A2 import here: dependency direction is A2 -> retention -> this
    evidence-only adapter -> raw Git objects and the pure P4 evaluator.
    """
    value = receipt()
    for path, row in value['source_forward'].items():
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path] = dict(
                context['HISTORICAL_PREDECESSORS'][path], after=row['after'])
    context['HISTORICAL_PREDECESSORS'][WORKFLOW] = {
        'fixture': FIXTURE, **BEFORE, 'after': AFTER}
    metadata = {'artifacts/architecture/tests_shard_balance_successor_v1.json': {'git_blob_sha1': '78aca5f006d13f5a216b48349d575a580f33fd78', 'source_sha256': '49fb4fa1e13b62d942353199a7284b4d90c9b2e5bed87dddea6f951599a74904', 'byte_count': 14272}, 'artifacts/architecture/p4_workflow_evolution_snapshots/tests_shard_balance_v1.json': {'git_blob_sha1': '432ab5b92ee14f3bf28659aa4bbf4575d8b877ac', 'source_sha256': 'a3c07131840ec2bf01f69d71bab8e339da35f4fbc42813827d52444ec1148f7c', 'byte_count': 29604}, 'tests/fixtures/architecture/revised_workflows/tests-pre-shard-balance-v1.yml': {'git_blob_sha1': 'a5eafa0afebc01abe02389739abf71c9ece2d1b4', 'source_sha256': '62dc0cd30df67534f424fddc9706a0b50f9b22ea86bc5b3c6a005e8c57006606', 'byte_count': 3322}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt': {'git_blob_sha1': 'e37cd985d456528fc2d14595bd3238fc0e442516', 'source_sha256': 'ebaf5bcb6caabe259a8e3375b41d589b7d4b94a49f69687d0c1f75cc40ba0204', 'byte_count': 58081}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_data_01c_restore_portability.py.before.txt': {'git_blob_sha1': '48088a35086ac8c15928fd2d6d0039adf47fbd87', 'source_sha256': '834d84ef290197283b74de48b65d20c68d57f7a7e3a0121a9b23bd58b5069b84', 'byte_count': 21506}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_p4_workflow_evolution_ledger.py.before.txt': {'git_blob_sha1': '5b808f4b915fac6146b21bce76dbb578b9fa5633', 'source_sha256': '0c99fd321dbcdc6f09ffce3c7e0d62be0580d12809da3270e0a1dc82692da4e6', 'byte_count': 68531}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_core_01d_retained_workflow_status_v3.py.before.txt': {'git_blob_sha1': '5c793bafd0e9b43bcebce213b67e808ecdb12803', 'source_sha256': '823b12aa6492eb03c881d161ce9e3c20f0f6239ff89c57cb1e18d2243ea46436', 'byte_count': 42468}}
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)
    context['ADDED_PYTHON_PATHS'] |= frozenset({
        'scripts/audit_tests_shard_balance_successor.py',
        'tests/test_tests_shard_balance_successor.py'})
    context['ADDED_PYTHON_IDENTITIES'] = dict(
        context['ADDED_PYTHON_IDENTITIES'], **value['added_python_sources'])
